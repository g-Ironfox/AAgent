"""Sequential evaluation with one Workflow and terminal per episode."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from importlib.metadata import PackageNotFoundError, version
from uuid import uuid4


def observation(episode_id, step, text, score, done, success, truncated=False,
                reason=None, commands=None):
    message = {"type": "observation", "episode_id": episode_id, "step": step,
               "text": str(text), "score": float(score), "done": bool(done),
               "success": bool(success), "truncated": bool(truncated), "reason": reason}
    if commands is not None:
        message["admissible_commands"] = list(commands)
    return message


def run_episode(env, client, workflow_file_id, inputs, max_steps, action_timeout,
                startup_timeout, include_commands, journal, episode_id=None):
    episode_id = episode_id or uuid4().hex
    terminal_id = "alfworld-" + episode_id
    result = {"episode_id": episode_id, "terminal_id": terminal_id,
              "steps": 0, "success": False, "score": 0.0, "status": "error"}
    started = time.monotonic()
    last_message = None
    terminal_started = False
    try:
        observations, infos = env.reset()
        result["gamefile"] = infos.get("extra.gamefile", [None])[0]
        client.start(workflow_file_id, terminal_id, inputs, startup_timeout)
        terminal_started = True
        last_message = observation(
            episode_id, 0, observations[0], 0, False, False,
            commands=infos["admissible_commands"][0] if include_commands else None,
        )
        journal({"direction": "observation", "message": last_message})
        client.send(terminal_id, last_message)
        for step in range(max_steps):
            action = client.action(terminal_id, episode_id, step, action_timeout)
            # Persist before executing; interrupted runs are recorded, not resumed.
            journal({"direction": "action", "step": step, "text": action})
            observations, scores, dones, infos = env.step([action])
            success = bool(infos.get("won", [False])[0])
            truncated = not success and step + 1 >= max_steps
            done = bool(dones[0]) or success or truncated
            reason = "success" if success else "max_steps" if truncated else "environment_done" if done else None
            result.update(steps=step + 1, success=success, score=float(scores[0]))
            last_message = observation(
                episode_id, step + 1, observations[0], scores[0], done, success,
                truncated=truncated, reason=reason,
                commands=infos["admissible_commands"][0] if include_commands else None,
            )
            journal({"direction": "observation", "message": last_message})
            client.send(terminal_id, last_message)
            if done:
                result["status"] = reason
                break
    except Exception as error:
        result.update(status="error", error=f"{type(error).__name__}: {error}")
        if terminal_started and last_message is not None:
            try:
                client.send(terminal_id, dict(last_message, done=True, truncated=True, reason="runner_error"))
            except Exception as cleanup_error:
                result["cleanup_error"] = str(cleanup_error)
    finally:
        result["duration_seconds"] = round(time.monotonic() - started, 3)
        journal({"direction": "result", "result": result})
    return result


def evaluate(env, games, client, args):
    if args.episodes > len(games):
        raise ValueError(f"Requested {args.episodes} episodes but split contains only {len(games)} games")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    output = Path(args.results_dir) / run_id
    output.mkdir(parents=True)
    packages = {}
    for name in ("alfworld", "textworld", "numpy", "requests", "PyYAML"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    metadata = {
        "versions": packages,
        "workflow_inputs": args.inputs,
        "run_id": run_id, "workflow_file_id": args.workflow_file_id, "split": args.split,
        "seed": args.seed, "max_steps": args.max_steps, "episodes": args.episodes,
        "include_admissible_commands": args.admissible_commands,
        "game_files": games, "results": [],
    }
    (output / "manifest.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    for index in range(args.episodes):
        with (output / f"episode-{index:04d}.jsonl").open("w", encoding="utf-8") as trace:
            def journal(record):
                trace.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                trace.flush()
            result = run_episode(
                env, client, args.workflow_file_id, args.inputs, args.max_steps,
                args.action_timeout, args.startup_timeout, args.admissible_commands, journal,
            )
        metadata["results"].append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
        (output / "manifest.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        if result["status"] == "error":
            break
    results = metadata["results"]
    summary = {
        "run_id": run_id, "requested": args.episodes, "completed": len(results),
        "successes": sum(item["success"] for item in results),
        "errors": sum(item["status"] == "error" for item in results),
        "success_rate": sum(item["success"] for item in results) / len(results) if results else 0,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary), flush=True)
    return 1 if summary["errors"] else 0
