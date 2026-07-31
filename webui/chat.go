package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"net/http"
	"strings"
	"time"
	"unicode/utf8"

	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo/options"
)

const maxChatMessageLength = 2000

type chatRequest struct {
	Message string `json:"message"`
}

type chatMessage struct {
	ID        string `json:"id"`
	Role      string `json:"role"`
	Content   string `json:"content"`
	Source    string `json:"source"`
	GroupID   any    `json:"group_id,omitempty"`
	CreatedAt any    `json:"created_at,omitempty"`
}

// chat 处理 POST /api/chat:把网页消息作为 web 事件写入 Redis 队列,
// 与 QQ 消息共用同一个 agent_tasks 队列与同一个 LLM 上下文(单决策中心)。
func (s *server) chat(response http.ResponseWriter, request *http.Request) {
	var body chatRequest
	if err := json.NewDecoder(http.MaxBytesReader(response, request.Body, 64<<10)).Decode(&body); err != nil {
		writeJSON(response, http.StatusBadRequest, map[string]string{"error": "无效的 JSON 请求体"})
		return
	}
	message := strings.TrimSpace(body.Message)
	if message == "" {
		writeJSON(response, http.StatusBadRequest, map[string]string{"error": "消息不能为空"})
		return
	}
	if utf8.RuneCountInString(message) > maxChatMessageLength {
		writeJSON(response, http.StatusBadRequest, map[string]string{"error": fmt.Sprintf("消息过长(最多 %d 字)", maxChatMessageLength)})
		return
	}

	ctx, cancel := context.WithTimeout(request.Context(), 3*time.Second)
	defer cancel()

	event := map[string]any{
		"event_type": "web",
		"payload": map[string]any{
			"user_id":     s.chatUserID,
			"group_id":    nil,
			"raw_message": message,
			"source":      "web",
		},
	}
	encoded, err := json.Marshal(event)
	if err != nil {
		writeJSON(response, http.StatusInternalServerError, map[string]string{"error": "消息编码失败"})
		return
	}
	if err := s.redis.LPush(ctx, s.queueName, encoded).Err(); err != nil {
		slog.Error("publish chat message", "error", err)
		writeJSON(response, http.StatusServiceUnavailable, map[string]string{"error": "消息队列不可用"})
		return
	}
	writeJSON(response, http.StatusAccepted, map[string]string{"status": "queued"})
}

// chatHistory 处理 GET /api/chat/history:返回聊天页要展示的会话消息。
// qq/web 事件作为用户消息,web_reply 事件作为 Agent 回复(按时间正序)。
func (s *server) chatHistory(response http.ResponseWriter, request *http.Request) {
	limit, err := queryInt(request, "limit", 100, 1, 500)
	if err != nil {
		writeJSON(response, http.StatusBadRequest, map[string]string{"error": err.Error()})
		return
	}
	ctx, cancel := context.WithTimeout(request.Context(), 5*time.Second)
	defer cancel()

	filter := bson.M{"event_type": bson.M{"$in": []string{"qq", "web", "web_reply"}}}
	cursor, err := s.history.Find(
		ctx, filter,
		options.Find().SetProjection(bson.D{{Key: "_id", Value: 0}}).SetSort(bson.D{{Key: "created_at", Value: -1}}).SetLimit(limit),
	)
	if err != nil {
		writeJSON(response, http.StatusServiceUnavailable, map[string]string{"error": "聊天历史不可用"})
		return
	}
	defer cursor.Close(ctx)

	var items []bson.M
	if err := cursor.All(ctx, &items); err != nil {
		writeJSON(response, http.StatusServiceUnavailable, map[string]string{"error": "聊天历史读取失败"})
		return
	}

	messages := make([]chatMessage, 0, len(items))
	for index := len(items) - 1; index >= 0; index-- {
		item := items[index]
		createdAt := item["created_at"]
		delete(item, "created_at")
		eventType, _ := item["event_type"].(string)
		payload, _ := item["payload"].(bson.M)
		msg := chatMessage{ID: eventFingerprint(map[string]any(item)) + "-" + fmt.Sprint(createdAt), CreatedAt: createdAt}
		switch eventType {
		case "web_reply":
			msg.Role = "assistant"
			msg.Source = "web"
			if content, ok := payload["content"].(string); ok {
				msg.Content = content
			}
		default: // qq / web → 用户消息
			msg.Role = "user"
			if source, ok := payload["source"].(string); ok && source != "" {
				msg.Source = source
			} else {
				msg.Source = "qq"
			}
			msg.GroupID = payload["group_id"]
			if content, ok := payload["raw_message"].(string); ok {
				msg.Content = content
			}
		}
		messages = append(messages, msg)
	}
	writeJSON(response, http.StatusOK, messages)
}
