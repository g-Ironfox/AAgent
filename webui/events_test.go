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