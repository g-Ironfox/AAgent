package main

import (
	"testing"

	"go.mongodb.org/mongo-driver/bson"
)

func TestLatestMatchingHistoryIndexUsesNewestDuplicate(t *testing.T) {
	running := map[string]any{"event_type": "active", "payload": map[string]any{"user_id": "42"}}
	items := []bson.M{
		{"event_type": "active", "payload": bson.M{"user_id": "42"}, "created_at": "newest"},
		{"event_type": "response", "payload": bson.M{"content": "done"}, "created_at": "middle"},
		{"event_type": "active", "payload": bson.M{"user_id": "42"}, "created_at": "oldest"},
	}

	index := latestMatchingHistoryIndex(items, eventFingerprint(running))
	if index != 0 {
		t.Fatalf("expected newest matching history index 0, got %d", index)
	}
}

func TestWorkerSourceStatus(t *testing.T) {
	tests := map[string]string{
		"idle":        "ok",
		"processing":  "ok",
		"unknown":     "missing",
		"unavailable": "unavailable",
		"invalid":     "invalid",
		"unexpected":  "invalid",
	}
	for state, want := range tests {
		if got := workerSourceStatus(state); got != want {
			t.Errorf("workerSourceStatus(%q) = %q, want %q", state, got, want)
		}
	}
}

func TestValidateWorkerStatus(t *testing.T) {
	valid := []workerStatus{
		{State: "idle"},
		{State: "processing", Event: map[string]any{"event_type": "active"}},
	}
	for _, status := range valid {
		if err := validateWorkerStatus(status); err != nil {
			t.Errorf("validateWorkerStatus(%q) returned unexpected error: %v", status.State, err)
		}
	}

	invalid := []workerStatus{
		{State: "unknown"},
		{State: "processing"},
	}
	for _, status := range invalid {
		if err := validateWorkerStatus(status); err == nil {
			t.Errorf("validateWorkerStatus(%q) accepted invalid status", status.State)
		}
	}
}

