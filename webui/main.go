package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	"github.com/redis/go-redis/v9"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

type server struct {
	redis           *redis.Client
	mongo           *mongo.Client
	history         *mongo.Collection
	queueName       string
	workerStatusKey string
	chatUserID      string
}

func main() {
	redisDB, err := strconv.Atoi(env("REDIS_DB", "0"))
	if err != nil {
		slog.Error("invalid REDIS_DB", "error", err)
		os.Exit(1)
	}
	redisAddress := env("REDIS_ADDR", env("REDIS_HOST", "redis")+":"+env("REDIS_PORT", "6379"))
	redisClient := redis.NewClient(&redis.Options{
		Addr: redisAddress, Password: os.Getenv("REDIS_PASSWORD"), DB: redisDB,
		DialTimeout: 5 * time.Second, ReadTimeout: 5 * time.Second, WriteTimeout: 5 * time.Second,
	})
	defer redisClient.Close()

	mongoOptions := options.Client().SetHosts([]string{env("MONGO_HOST", "mongodb") + ":" + env("MONGO_PORT", "27017")}).SetServerSelectionTimeout(5 * time.Second)
	if mongoUser := os.Getenv("MONGO_USER"); mongoUser != "" {
		mongoOptions.SetAuth(options.Credential{AuthSource: "admin", Username: mongoUser, Password: os.Getenv("MONGO_PASS")})
	}
	mongoClient, err := mongo.Connect(context.Background(), mongoOptions)
	if err != nil {
		slog.Error("create MongoDB client", "error", err)
		os.Exit(1)
	}
	defer mongoClient.Disconnect(context.Background())

	app := &server{
		redis: redisClient, mongo: mongoClient,
		history:   mongoClient.Database(env("MONGO_DATABASE", "agent")).Collection(env("MONGO_HISTORY_COLLECTION", "event_history")),
		queueName: env("AGENT_QUEUE_NAME", "agent_tasks"), workerStatusKey: env("AGENT_WORKER_STATUS_KEY", "aagent:worker:status"),
		chatUserID: env("WEBUI_USER_ID", env("QQ_TARGET_USER_ID", "web")),
	}
	httpServer := &http.Server{
		Addr: ":" + env("PORT", "8080"), Handler: requestLogger(securityHeaders(app.routes())),
		ReadHeaderTimeout: 5 * time.Second, IdleTimeout: 60 * time.Second,
	}

	go func() {
		slog.Info("event console started", "address", httpServer.Addr, "redis", redisAddress, "queue", app.queueName)
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

func env(name, fallback string) string {
	if value := os.Getenv(name); value != "" {
		return value
	}
	return fallback
}
