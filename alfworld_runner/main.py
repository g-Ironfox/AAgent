"""ALFWorld container commands: download, smoke, and run."""

import argparse
import json
import math
import os
from pathlib import Path

if __package__:
    from .client import TerminalClient
    from .environment import make_environment, download_data
    from .runner import evaluate
else:
    from client import TerminalClient
    from environment import make_environment, download_data
    from runner import evaluate


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("download", help="Download text-only ALFWorld data (cached in the data volume)")
    for name in ("smoke", "run"):
        command = commands.add_parser(name)
        command.add_argument("--config", default=str(Path(__file__).with_name("config.yaml")))
        command.add_argument("--split", choices=("train", "valid_seen", "valid_unseen"), default="valid_unseen")
        command.add_argument("--max-steps", type=positive, default=50)
        command.add_argument("--seed", type=int, default=42)
        if name == "run":
            command.add_argument("--workflow-file-id", default=os.getenv("ALFWORLD_WORKFLOW_FILE_ID"))
            command.add_argument("--inputs", type=json.loads, default={})
            command.add_argument("--api-url", default=os.getenv("AAGENT_API_URL", "http://agent_environment:8080"))
            command.add_argument("--episodes", type=positive, default=1)
            command.add_argument("--action-timeout", type=positive, default=180)
            command.add_argument("--startup-timeout", type=positive, default=60)
            command.add_argument("--poll-interval", type=float, default=0.5)
            command.add_argument("--admissible-commands", action="store_true")
            command.add_argument("--results-dir", default="/results")
    args = parser.parse_args()
    if args.command == "download":
        download_data()
        return 0
    if args.command == "run":
        if not args.workflow_file_id:
            parser.error("run requires --workflow-file-id or ALFWORLD_WORKFLOW_FILE_ID")
        if not isinstance(args.inputs, dict):
            parser.error("--inputs must be a JSON object")
        if not math.isfinite(args.poll_interval) or args.poll_interval <= 0:
            parser.error("--poll-interval must be finite and positive")
    env, games = make_environment(args.config, args.split, args.max_steps, args.seed)
    try:
        if args.command == "smoke":
            observations, infos = env.reset()
            action = "look"
            next_observations, scores, dones, next_infos = env.step([action])
            print(json.dumps({"games": len(games), "gamefile": infos["extra.gamefile"][0],
                              "observation": observations[0], "action": action,
                              "next_observation": next_observations[0], "score": float(scores[0]),
                              "done": bool(dones[0]), "success": bool(next_infos["won"][0])}))
            return 0
        client = TerminalClient(args.api_url, poll_interval=args.poll_interval)
        try:
            return evaluate(env, games, client, args)
        finally:
            client.close()
    finally:
        env.close()


if __name__ == "__main__":
    raise SystemExit(main())
