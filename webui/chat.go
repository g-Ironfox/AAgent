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
	if err := s.redis.LPush(ctx, s.queueName, encoded).Err(); err != nil {
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
