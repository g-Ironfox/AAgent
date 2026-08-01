package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strconv"
	"time"

	"github.com/redis/go-redis/v9"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo/options"
)

type workerStatus struct {
	State     string         `json:"state"`
	Event     map[string]any `json:"event,omitempty"`
	StartedAt string         `json:"started_at,omitempty"`
	UpdatedAt string         `json:"updated_at,omitempty"`
}

type unifiedEvent struct {
	ID        string         `json:"id"`
	Status    string         `json:"status"`
	Source    string         `json:"source"`
	Position  int64          `json:"position,omitempty"`
	StartedAt string         `json:"started_at,omitempty"`
	CreatedAt any            `json:"created_at,omitempty"`
	Event     map[string]any `json:"event"`
}

type eventSummary struct {
	Pending int64 `json:"pending"`
	Running int64 `json:"running"`
	History int64 `json:"history"`
}

type sourceStatus struct {
	MongoDB string `json:"mongodb"`
	Redis   string `json:"redis"`
	Worker  string `json:"worker"`
}

type eventsSnapshot struct {
	Queue     string            `json:"queue"`
	FetchedAt time.Time         `json:"fetched_at"`
	Worker    workerStatus      `json:"worker"`
	Summary   eventSummary      `json:"summary"`
	Sources   sourceStatus      `json:"sources"`
	Items     []unifiedEvent    `json:"items"`
	Warnings  map[string]string `json:"warnings,omitempty"`
}

func (s *server) eventSnapshot(ctx context.Context, limit int64) eventsSnapshot {
	snapshot := eventsSnapshot{
		Queue: s.queueName, FetchedAt: time.Now().UTC(),
		Sources: sourceStatus{MongoDB: "unavailable", Redis: "unavailable", Worker: "unavailable"},
		Items:   make([]unifiedEvent, 0, limit*2+1), Warnings: map[string]string{},
	}
	pendingItems := make([]unifiedEvent, 0, limit)

	status, err := s.readWorkerStatus(ctx)
	var runningFingerprint string
	var runningItem *unifiedEvent
	if err != nil {
		snapshot.Worker = status
		snapshot.Sources.Worker = workerSourceStatus(status.State)
		snapshot.Warnings["worker"] = err.Error()
	} else {
		snapshot.Worker = status
		snapshot.Sources.Worker = workerSourceStatus(status.State)
		if status.State == "processing" {
			snapshot.Summary.Running = 1
			if status.Event != nil {
				runningFingerprint = eventFingerprint(status.Event)
				running := unifiedEvent{
					ID: "running-" + runningFingerprint, Status: "running", Source: "worker",
					StartedAt: status.StartedAt, Event: status.Event,
				}
				runningItem = &running
			}
		}
	}

	queueLength, err := s.redis.LLen(ctx, s.queueName).Result()
	if err != nil {
		snapshot.Warnings["redis"] = "Redis queue is unavailable"
	} else {
		snapshot.Sources.Redis = "ok"
		snapshot.Summary.Pending = queueLength
		start := queueLength - limit
		if start < 0 {
			start = 0
		}
		rawItems, queueErr := s.redis.LRange(ctx, s.queueName, start, queueLength-1).Result()
		if queueErr != nil {
			snapshot.Sources.Redis = "unavailable"
			snapshot.Warnings["redis"] = "Redis queue is unavailable"
		} else {
			seen := map[string]int{}
			for index := len(rawItems) - 1; index >= 0; index-- {
				event := decodeQueueEvent(rawItems[index])
				fingerprint := eventFingerprint(event)
				seen[fingerprint]++
				position := int64(len(rawItems) - index)
				pendingItems = append(pendingItems, unifiedEvent{
					// 用"内容指纹 + 弹出顺序计数"做稳定 ID:新任务 LPUSH 到队头
					// 不会改变已有 pending 事件的相对弹出顺序,ID 不变,前端无需重建行
					ID:     fmt.Sprintf("pending-%s-%d", fingerprint, seen[fingerprint]),
					Status: "pending", Source: "redis", Position: position, Event: event,
				})
			}
		}
	}

	cursor, err := s.history.Find(
		ctx, bson.D{},
		options.Find().SetProjection(bson.D{{Key: "_id", Value: 0}}).SetSort(bson.D{{Key: "_id", Value: -1}}).SetLimit(limit),
	)
	if err != nil {
		snapshot.Warnings["mongodb"] = "MongoDB history is unavailable"
	} else {
		snapshot.Sources.MongoDB = "ok"
		defer cursor.Close(ctx)
		var historyItems []bson.M
		if err := cursor.All(ctx, &historyItems); err != nil {
			snapshot.Sources.MongoDB = "unavailable"
			snapshot.Warnings["mongodb"] = "MongoDB history could not be decoded"
		} else {
			runningIndex := latestMatchingHistoryIndex(historyItems, runningFingerprint)
			for index := len(historyItems) - 1; index >= 0; index-- {
				item := historyItems[index]
				createdAt := item["created_at"]
				delete(item, "created_at")
				event := map[string]any(item)
				fingerprint := eventFingerprint(event)
				if index == runningIndex {
					continue
				}
				snapshot.Items = append(snapshot.Items, unifiedEvent{
					ID: "done-" + fingerprint + "-" + fmt.Sprint(createdAt), Status: "done",
					Source: "mongodb", CreatedAt: createdAt, Event: event,
				})
				snapshot.Summary.History++
			}
		}
	}

	if runningItem != nil {
		snapshot.Items = append(snapshot.Items, *runningItem)
	}
	snapshot.Items = append(snapshot.Items, pendingItems...)

	if len(snapshot.Warnings) == 0 {
		snapshot.Warnings = nil
	}
	return snapshot
}

func (s *server) readWorkerStatus(ctx context.Context) (workerStatus, error) {
	raw, err := s.redis.Get(ctx, s.workerStatusKey).Result()
	if errors.Is(err, redis.Nil) {
		return workerStatus{State: "unknown"}, nil
	}
	if err != nil {
		return workerStatus{State: "unavailable"}, errors.New("Worker status is unavailable")
	}
	var status workerStatus
	if err := json.Unmarshal([]byte(raw), &status); err != nil {
		return workerStatus{State: "invalid"}, errors.New("Worker status is invalid")
	}
	if err := validateWorkerStatus(status); err != nil {
		return workerStatus{State: "invalid"}, err
	}
	return status, nil
}

func validateWorkerStatus(status workerStatus) error {
	if status.State != "idle" && status.State != "processing" {
		return errors.New("Worker status has an unknown state")
	}
	if status.State == "processing" && status.Event == nil {
		return errors.New("Worker processing status has no event")
	}
	return nil
}

func workerSourceStatus(state string) string {
	switch state {
	case "idle", "processing":
		return "ok"
	case "unknown":
		return "missing"
	case "unavailable":
		return "unavailable"
	default:
		return "invalid"
	}
}

func decodeQueueEvent(raw string) map[string]any {
	var event map[string]any
	if json.Unmarshal([]byte(raw), &event) == nil {
		return event
	}
	return map[string]any{"event_type": "raw", "payload": map[string]any{"raw": raw}}
}

func eventFingerprint(event map[string]any) string {
	encoded, _ := json.Marshal(event)
	var hash uint64 = 1469598103934665603
	for _, value := range encoded {
		hash ^= uint64(value)
		hash *= 1099511628211
	}
	return strconv.FormatUint(hash, 36)
}

func latestMatchingHistoryIndex(items []bson.M, fingerprint string) int {
	if fingerprint == "" {
		return -1
	}
	for index, item := range items {
		event := make(map[string]any, len(item))
		for key, value := range item {
			if key != "created_at" {
				event[key] = value
			}
		}
		if eventFingerprint(event) == fingerprint {
			return index
		}
	}
	return -1
}
