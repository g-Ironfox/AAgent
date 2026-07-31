package main

import (
	"context"
	"embed"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/redis/go-redis/v9"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

//go:embed static/*
var staticFiles embed.FS

type server struct {
	redis           *redis.Client
	mongo           *mongo.Client
	history         *mongo.Collection
	queueName       string
	workerStatusKey string
}

type queueItem struct {
	Index     int64  `json:"index"`
	Raw       string `json:"raw"`
	ValidJSON bool   `json:"valid_json"`
	Data      any    `json:"data,omitempty"`
}

type queueSnapshot struct {
	Queue     string      `json:"queue"`
	Length    int64       `json:"length"`
	Offset    int64       `json:"offset"`
	Limit     int64       `json:"limit"`
	FetchedAt time.Time   `json:"fetched_at"`
	Items     []queueItem `json:"items"`
}

type workerStatus struct {
	State     string         `json:"state"`
	Event     map[string]any `json:"event,omitempty"`
	StartedAt string         `json:"started_at,omitempty"`
	UpdatedAt string         `json:"updated_at,omitempty"`
}

type historySnapshot struct {
	FetchedAt time.Time `json:"fetched_at"`
	Items     []bson.M  `json:"items"`
}

func main() {
	redisAddress := env("REDIS_ADDR", env("REDIS_HOST", "redis")+":"+env("REDIS_PORT", "6379"))
	redisDB, err := strconv.Atoi(env("REDIS_DB", "0"))
	if err != nil {
		slog.Error("invalid REDIS_DB", "error", err)
		os.Exit(1)
	}

	redisClient := redis.NewClient(&redis.Options{
		Addr:         redisAddress,
		Password:     os.Getenv("REDIS_PASSWORD"),
		DB:           redisDB,
		DialTimeout:  5 * time.Second,
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 5 * time.Second,
	})
	defer redisClient.Close()

	mongoAddress := env("MONGO_HOST", "mongodb") + ":" + env("MONGO_PORT", "27017")
	mongoOptions := options.Client().SetHosts([]string{mongoAddress}).SetServerSelectionTimeout(5 * time.Second)
	if mongoUser := os.Getenv("MONGO_USER"); mongoUser != "" {
		mongoOptions.SetAuth(options.Credential{
			AuthSource: "admin",
			Username:   mongoUser,
			Password:   os.Getenv("MONGO_PASS"),
		})
	}
	mongoClient, err := mongo.Connect(context.Background(), mongoOptions)
	if err != nil {
		slog.Error("create MongoDB client", "error", err)
		os.Exit(1)
	}
	defer func() {
		if err := mongoClient.Disconnect(context.Background()); err != nil {
			slog.Warn("close MongoDB client", "error", err)
		}
	}()

	app := &server{
		redis:           redisClient,
		mongo:           mongoClient,
		history:         mongoClient.Database(env("MONGO_DATABASE", "agent")).Collection(env("MONGO_HISTORY_COLLECTION", "event_history")),
		queueName:       env("AGENT_QUEUE_NAME", "agent_tasks"),
		workerStatusKey: env("AGENT_WORKER_STATUS_KEY", "aagent:worker:status"),
	}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /api/health", app.health)
	mux.HandleFunc("GET /api/queue", app.queue)
	mux.HandleFunc("GET /api/status", app.status)
	mux.HandleFunc("GET /api/history", app.historyEvents)

	staticRoot, err := fs.Sub(staticFiles, "static")
	if err != nil {
		slog.Error("load static files", "error", err)
		os.Exit(1)
	}
	mux.Handle("GET /", http.FileServer(http.FS(staticRoot)))

	httpServer := &http.Server{
		Addr:              ":" + env("PORT", "8080"),
		Handler:           requestLogger(securityHeaders(mux)),
		ReadHeaderTimeout: 5 * time.Second,
		IdleTimeout:       60 * time.Second,
	}

	go func() {
		slog.Info("queue monitor started", "address", httpServer.Addr, "redis", redisAddress, "queue", app.queueName)
		if err := httpServer.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			slog.Error("http server stopped", "error", err)
			os.Exit(1)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	<-stop

	shutdownContext, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := httpServer.Shutdown(shutdownContext); err != nil {
		slog.Error("graceful shutdown failed", "error", err)
	}
}

func (s *server) health(response http.ResponseWriter, request *http.Request) {
	ctx, cancel := context.WithTimeout(request.Context(), 2*time.Second)
	defer cancel()

	if err := s.redis.Ping(ctx).Err(); err != nil {
		writeJSON(response, http.StatusServiceUnavailable, map[string]string{"status": "unavailable", "error": err.Error()})
		return
	}
	writeJSON(response, http.StatusOK, map[string]string{"status": "ok"})
}

func (s *server) queue(response http.ResponseWriter, request *http.Request) {
	offset, err := queryInt(request, "offset", 0, 0, 1_000_000)
	if err != nil {
		writeJSON(response, http.StatusBadRequest, map[string]string{"error": err.Error()})
		return
	}
	limit, err := queryInt(request, "limit", 100, 1, 200)
	if err != nil {
		writeJSON(response, http.StatusBadRequest, map[string]string{"error": err.Error()})
		return
	}

	ctx, cancel := context.WithTimeout(request.Context(), 4*time.Second)
	defer cancel()

	// offset 从队列尾部(BRPOP 消费端)起算,保证 offset=0 时能看到下一个被消费的事件。
	// 注意:QQ 消息经 LPUSH 从头部进入,tool_return 经 RPUSH 从尾部进入,消费永远发生在尾部。
	length, err := s.redis.LLen(ctx, s.queueName).Result()
	if err != nil {
		slog.Warn("redis length failed", "error", err)
		writeJSON(response, http.StatusServiceUnavailable, map[string]string{"error": "Redis queue is unavailable"})
		return
	}

	var rawItems []string
	start := int64(0)
	stop := length - 1 - offset
	if stop >= 0 {
		start = stop - limit + 1
		if start < 0 {
			start = 0
		}
		rawItems, err = s.redis.LRange(ctx, s.queueName, start, stop).Result()
		if err != nil {
			slog.Warn("redis snapshot failed", "error", err)
			writeJSON(response, http.StatusServiceUnavailable, map[string]string{"error": "Redis queue is unavailable"})
			return
		}
	}

	items := make([]queueItem, 0, len(rawItems))
	for index, raw := range rawItems {
		item := queueItem{Index: start + int64(index), Raw: raw}
		var parsed any
		if json.Unmarshal([]byte(raw), &parsed) == nil {
			item.ValidJSON = true
			item.Data = parsed
		}
		items = append(items, item)
	}

	writeJSON(response, http.StatusOK, queueSnapshot{
		Queue: s.queueName, Length: length, Offset: offset,
		Limit: limit, FetchedAt: time.Now().UTC(), Items: items,
	})
}

func (s *server) status(response http.ResponseWriter, request *http.Request) {
	ctx, cancel := context.WithTimeout(request.Context(), 2*time.Second)
	defer cancel()

	raw, err := s.redis.Get(ctx, s.workerStatusKey).Result()
	if errors.Is(err, redis.Nil) {
		writeJSON(response, http.StatusOK, workerStatus{State: "unknown"})
		return
	}
	if err != nil {
		writeJSON(response, http.StatusServiceUnavailable, map[string]string{"error": "Worker status is unavailable"})
		return
	}

	var status workerStatus
	if err := json.Unmarshal([]byte(raw), &status); err != nil {
		writeJSON(response, http.StatusInternalServerError, map[string]string{"error": "Worker status is invalid"})
		return
	}
	writeJSON(response, http.StatusOK, status)
}

func (s *server) historyEvents(response http.ResponseWriter, request *http.Request) {
	limit, err := queryInt(request, "limit", 100, 1, 200)
	if err != nil {
		writeJSON(response, http.StatusBadRequest, map[string]string{"error": err.Error()})
		return
	}

	ctx, cancel := context.WithTimeout(request.Context(), 4*time.Second)
	defer cancel()
	cursor, err := s.history.Find(
		ctx,
		bson.D{},
		options.Find().SetProjection(bson.D{{Key: "_id", Value: 0}}).SetSort(bson.D{{Key: "created_at", Value: -1}}).SetLimit(limit),
	)
	if err != nil {
		slog.Warn("MongoDB history query failed", "error", err)
		writeJSON(response, http.StatusServiceUnavailable, map[string]string{"error": "MongoDB history is unavailable"})
		return
	}
	defer cursor.Close(ctx)

	items := make([]bson.M, 0, limit)
	if err := cursor.All(ctx, &items); err != nil {
		writeJSON(response, http.StatusServiceUnavailable, map[string]string{"error": "MongoDB history could not be decoded"})
		return
	}
	writeJSON(response, http.StatusOK, historySnapshot{FetchedAt: time.Now().UTC(), Items: items})
}

func queryInt(request *http.Request, name string, fallback, minimum, maximum int64) (int64, error) {
	value := request.URL.Query().Get(name)
	if value == "" {
		return fallback, nil
	}
	parsed, err := strconv.ParseInt(value, 10, 64)
	if err != nil || parsed < minimum || parsed > maximum {
		return 0, fmt.Errorf("%s must be between %d and %d", name, minimum, maximum)
	}
	return parsed, nil
}

func writeJSON(response http.ResponseWriter, status int, value any) {
	response.Header().Set("Content-Type", "application/json; charset=utf-8")
	response.WriteHeader(status)
	if err := json.NewEncoder(response).Encode(value); err != nil {
		slog.Warn("write response", "error", err)
	}
}

func securityHeaders(next http.Handler) http.Handler {
	return http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		response.Header().Set("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:")
		response.Header().Set("X-Content-Type-Options", "nosniff")
		response.Header().Set("X-Frame-Options", "DENY")
		response.Header().Set("Referrer-Policy", "no-referrer")
		next.ServeHTTP(response, request)
	})
}

func requestLogger(next http.Handler) http.Handler {
	return http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		startedAt := time.Now()
		next.ServeHTTP(response, request)
		if strings.HasPrefix(request.URL.Path, "/api/") {
			slog.Info("request", "method", request.Method, "path", request.URL.Path, "duration", time.Since(startedAt))
		}
	})
}

func env(name, fallback string) string {
	if value := os.Getenv(name); value != "" {
		return value
	}
	return fallback
}
