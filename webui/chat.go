package main

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
	"time"
	"unicode/utf8"

	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/bson/primitive"
	"go.mongodb.org/mongo-driver/mongo/options"
)

const (
	maxChatBodyBytes = 16 * 1024
	maxChatRunes     = 4000
)

type chatRequest struct {
	Message string   `json:"message"`
	Files   []string `json:"files"`
}

type chatPayload struct {
	Message string   `json:"message"`
	Files   []string `json:"files"`
}

type chatEvent struct {
	EventType string      `json:"event_type"`
	Time      string      `json:"time"`
	Payload   chatPayload `json:"payload"`
}

type chatHistoryItem struct {
	ID        string         `json:"id"`
	CreatedAt any            `json:"created_at"`
	Event     map[string]any `json:"event"`
}

func (s *server) chatHistory(response http.ResponseWriter, request *http.Request) {
	limit, err := queryInt(request, "limit", 150, 1, 300)
	if err != nil {
		writeJSON(response, http.StatusBadRequest, map[string]string{"error": err.Error()})
		return
	}

	ctx, cancel := context.WithTimeout(request.Context(), 5*time.Second)
	defer cancel()
	cursor, err := s.history.Find(
		ctx,
		bson.M{"event_type": bson.M{"$in": []string{"webui", "response"}}},
		options.Find().SetSort(bson.D{{Key: "_id", Value: -1}}).SetLimit(limit),
	)
	if err != nil {
		writeJSON(response, http.StatusServiceUnavailable, map[string]string{"error": "终端历史暂时不可用"})
		return
	}
	defer cursor.Close(ctx)

	var documents []bson.M
	if err := cursor.All(ctx, &documents); err != nil {
		writeJSON(response, http.StatusServiceUnavailable, map[string]string{"error": "无法读取终端历史"})
		return
	}
	items := make([]chatHistoryItem, 0, len(documents))
	for index := len(documents) - 1; index >= 0; index-- {
		document := documents[index]
		id := historyDocumentID(document["_id"])
		createdAt := document["created_at"]
		delete(document, "_id")
		delete(document, "created_at")
		items = append(items, chatHistoryItem{ID: id, CreatedAt: createdAt, Event: map[string]any(document)})
	}
	writeJSON(response, http.StatusOK, map[string]any{"fetched_at": time.Now().UTC(), "items": items})
}

func historyDocumentID(value any) string {
	if objectID, ok := value.(primitive.ObjectID); ok {
		return objectID.Hex()
	}
	return ""
}

func (s *server) submitChat(response http.ResponseWriter, request *http.Request) {
	request.Body = http.MaxBytesReader(response, request.Body, maxChatBodyBytes)
	decoder := json.NewDecoder(request.Body)
	decoder.DisallowUnknownFields()

	var input chatRequest
	if err := decoder.Decode(&input); err != nil {
		writeJSON(response, http.StatusBadRequest, map[string]string{"error": "请求必须是有效的 JSON"})
		return
	}
	if err := ensureJSONEnd(decoder); err != nil {
		writeJSON(response, http.StatusBadRequest, map[string]string{"error": "请求只能包含一个 JSON 对象"})
		return
	}

	message := strings.TrimSpace(input.Message)
	if message == "" {
		writeJSON(response, http.StatusBadRequest, map[string]string{"error": "消息不能为空"})
		return
	}
	if utf8.RuneCountInString(message) > maxChatRunes {
		writeJSON(response, http.StatusBadRequest, map[string]string{"error": "消息不能超过 4000 个字符"})
		return
	}
	if len(input.Files) != 0 {
		writeJSON(response, http.StatusBadRequest, map[string]string{"error": "暂不支持文件附件"})
		return
	}

	event := chatEvent{
		EventType: "webui",
		Time:      time.Now().UTC().Format(time.RFC3339Nano),
		Payload: chatPayload{
			Message: message,
			Files:   []string{},
		},
	}
	encoded, err := json.Marshal(event)
	if err != nil {
		writeJSON(response, http.StatusInternalServerError, map[string]string{"error": "无法编码消息事件"})
		return
	}

	ctx, cancel := context.WithTimeout(request.Context(), 3*time.Second)
	defer cancel()
	if err := s.redis.RPush(ctx, s.queueName, encoded).Err(); err != nil {
		writeJSON(response, http.StatusServiceUnavailable, map[string]string{"error": "消息队列暂时不可用"})
		return
	}

	writeJSON(response, http.StatusCreated, map[string]any{"event": event, "queue": s.queueName})
}

func ensureJSONEnd(decoder *json.Decoder) error {
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		if err == nil {
			return errors.New("unexpected trailing JSON value")
		}
		return err
	}
	return nil
}
