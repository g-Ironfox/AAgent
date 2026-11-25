"""Experiment-only JSON audit records with objects, not JSON-in-string snapshots.

Keep root status/checkpoints under summary; raw JSON fragments are exclusively
from the environment's JSON envelope or workflow runtime JSON serialization.
Never unescape user/model text: turn actions/reasoning remain typed strings.
"""
from __future__ import annotations

import copy
import json

from build_tool_loop_workflow import Graph
from restricted_workflow_graph import parse, result, text

RECORD_FORMAT = "alfworld-episode/v2"
PACKED_RECORDS = ("initial_record", "progress_record", "episode_progress", "task_record", "completed_record")
RAW_FIELDS = {"task", "result", "workspace_before", "workspace_after", "iterator_result", "events"}


def _add_event_encoder(g):
    fi = g.function("audit_encode_event", [("event", "struct:EpisodeEvent")], [("json", "content")])
    kind = g.get("audit_event_kind", "EpisodeEvent", "type", fi, "function:event")
    route = g.node("audit_event_route", "router", arguments={"branches": [{"id": "observation", "name": "observation"}]})
    g.data(kind, "value-out", route, "content-in")
    observation = g.get("audit_event_observation", "EpisodeEvent", "observation", fi, "function:event")
    parse(g, "audit_validate_observation", (observation, "value-out"), [("type", "content")])
    text(g, "audit_observation_json", ['{"type":"observation","observation":', (observation, "value-out"), '}'])
    obs_return = result(g, "audit_observation_return", "audit_encode_event", {"json": ("audit_observation_json", "content-out")})
    turn = g.node("audit_turn_json", "struct_to_json", arguments={"value_type": "struct:EpisodeEvent"})
    g.data(fi, "function:event", turn, "value-in", "struct:EpisodeEvent")
    turn_return = result(g, "audit_turn_return", "audit_encode_event", {"json": (turn, "content-out")})
    g.chain(fi, kind, route)
    g.control(route, observation, "observation")
    g.chain(observation, "audit_validate_observation", "audit_observation_json", obs_return)
    g.control(route, turn, "branch$others")
    g.control(turn, turn_return)

    fi = g.function("audit_append_event", [("event", "struct:EpisodeEvent"), ("buffer", "content"), ("separator", "content")])
    g.call("audit_encode_one", "audit_encode_event", {"event": (fi, "function:event", "struct:EpisodeEvent")})
    for field in ("buffer", "separator"):
        g.ctx("audit_read_" + field, "read", "content")
        g.data(fi, "function:" + field, "audit_read_" + field, "context-id")
    text(g, "audit_join_event", [("audit_read_buffer", "value-out"), ("audit_read_separator", "value-out"), ("audit_encode_one", "function:json")])
    g.ctx("audit_write_buffer", "write", "content")
    g.data(fi, "function:buffer", "audit_write_buffer", "context-id")
    g.data("audit_join_event", "content-out", "audit_write_buffer", "value-in")
    comma = g.const("audit_comma", ",")
    g.ctx("audit_write_separator", "write", "content")
    g.data(fi, "function:separator", "audit_write_separator", "context-id")
    g.data(comma, "content-out", "audit_write_separator", "value-in")
    end = result(g, "audit_append_return", "audit_append_event", {})
    g.chain(fi, "audit_encode_one", "audit_read_buffer", "audit_read_separator", "audit_join_event", "audit_write_buffer", comma, "audit_write_separator", end)

    fi = g.function("audit_encode_events", [("events", "list-struct:EpisodeEvent")], [("json", "content")])
    begin = g.const("audit_array_open", "[")
    empty = g.const("audit_separator_empty", "")
    for field, initial in (("buffer", begin), ("separator", empty)):
        g.ctx("audit_create_" + field, "create", "content")
        g.data(initial, "content-out", "audit_create_" + field, "initial-value")
    loop = g.node("audit_event_loop", "foreach", arguments={"item_type": "struct:EpisodeEvent"})
    g.data(fi, "function:events", loop, "list-in", "list-struct:EpisodeEvent")
    g.call("audit_append_one", "audit_append_event", {
        "event": (loop, "item-out", "struct:EpisodeEvent"),
        "buffer": ("audit_create_buffer", "context-id"), "separator": ("audit_create_separator", "context-id")})
    g.control(loop, "audit_append_one", "loop-out")
    g.control("audit_append_one", loop, in_port="loop-in")
    g.ctx("audit_array_read", "read", "content")
    g.data("audit_create_buffer", "context-id", "audit_array_read", "context-id")
    text(g, "audit_array_close", [("audit_array_read", "value-out"), "]"])
    end = result(g, "audit_array_return", "audit_encode_events", {"json": ("audit_array_close", "content-out")})
    g.chain(fi, begin, empty, "audit_create_buffer", "audit_create_separator", loop, "audit_array_read", "audit_array_close", end)


def patch_recording(document):
    """Replace only persistence/iterator record serializers in a fresh base graph.

    Internal Run/Outcome/LLM message interfaces are untouched. No new tool,
    capability, runtime module or blanket escaping replacement is introduced.
    """
    g = Graph()
    g.doc = copy.deepcopy(document)
    if any(n["id"] == "audit_event_loop" for n in g.doc["nodes"]):
        return g.doc
    _add_event_encoder(g)
    for prefix in PACKED_RECORDS:
        value_id = prefix + "_value"
        node = next(n for n in g.doc["nodes"] if n["id"] == value_id)
        fields = {e["toPortId"]: (e["fromId"], e["fromPortId"], e["type"]) for e in g.doc["connections"]
                  if e["toId"] == value_id and e["type"] != "control"}
        raw = {key: value for key, value in fields.items() if key in RAW_FIELDS}
        summary = {key: value for key, value in fields.items() if key not in RAW_FIELDS}
        definition = next(s for s in g.doc["metadata"]["structs"] if s["id"] == node["arguments"]["struct_id"])
        definition["fields"] = [f for f in definition["fields"] if f["name"] in summary]
        node["dataInputPorts"] = list(summary)
        # Keep incoming control and outgoing consumer edges; replace only the
        # obsolete struct-to-JSON serialization and its incoming dependencies.
        g.doc["connections"] = [e for e in g.doc["connections"]
            if not (e["toId"] == value_id and e["toPortId"] in raw)
            and not (e["toId"] == prefix)]
        g.doc["nodes"] = [n for n in g.doc["nodes"] if n["id"] != prefix]
        serialized = g.node(prefix + "_summary", "struct_to_json", arguments={"value_type": "struct:" + definition["id"]})
        g.data(value_id, "struct-out", serialized, "value-in", "struct:" + definition["id"])
        chain = [value_id, serialized]
        if "events" in raw:
            encode = g.call(prefix + "_events", "audit_encode_events", {"events": raw["events"]})
            raw["events"] = (encode, "function:json", "content")
            chain.append(encode)
        parts = ['{"format":' + json.dumps(RECORD_FORMAT) + ',"summary":', (serialized, "content-out")]
        for key, value in raw.items():
            if key in {"task", "result"}:
                # Parse the whole object before raw embedding. Invalid JSON must
                # abort before the record write, not corrupt a stored document.
                validate = parse(g, prefix + "_validate_" + key, value[:2], [("type", "content")])
                chain.append(validate)
            parts += ["," + json.dumps(key) + ":", value[:2]]
        parts.append("}")
        text(g, prefix, parts)
        g.chain(*chain, prefix)
    g.doc["description"] += " Audit v2: structured JSON records without JSON-in-string snapshots."
    return g.doc
