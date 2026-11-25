"""Preview or install a fixed ALFWorld three-workflow bundle."""
import argparse
import json

from build_alfworld_bundle import build_bundle
from install_restricted_workflows import install_files, request


def install_bundle(api, model, prefix="alfworld-agent"):
    return install_files(api, model, prefix, build_bundle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="enabled model ID for ReAct and experience review")
    parser.add_argument("--url", default="http://127.0.0.1:8081")
    parser.add_argument("--prefix", default="alfworld-agent")
    parser.add_argument("--install", action="store_true", help="create five files and a baseline checkpoint")
    args = parser.parse_args()
    if not args.install:
        preview = [{key: value for key, value in item.items() if key != "content"}
                   for item in build_bundle(model=args.model, prefix=args.prefix)]
        print(json.dumps({"preview": preview, "install": False}, ensure_ascii=False, indent=2))
        return
    try:
        result = install_bundle(lambda method, path, payload=None: request(args.url, method, path, payload),
                                args.model, args.prefix)
    except (RuntimeError, ValueError) as error:
        parser.exit(1, f"Installation stopped: {error}\nAny created files were retained. Resolve the problem and use a new prefix.\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("ALFWorld workflow_file_id: " + result["files"]["bootstrap"]["file_id"] + "; workflow_inputs: {}")


if __name__ == "__main__":
    main()
