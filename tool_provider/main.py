import logging
import os

from runtime import ToolProvider


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def main() -> None:
    modules = [
        name.strip()
        for name in os.getenv(
            "TOOL_MODULES", "tools.system,tools.qq,tools.bilibili,tools.documents"
        ).split(",")
        if name.strip()
    ]
    provider = ToolProvider(
        server_url=os.getenv("TOOL_SERVER_WS_URL", "ws://tool_server:8083/ws/providers"),
        provider_id=os.getenv("TOOL_PROVIDER_ID", "provider-default-01"),
        revision=env_int("TOOL_PROVIDER_REVISION", 3),
        tools=ToolProvider.discover(modules),
        consumers=env_int("TOOL_PROVIDER_CONSUMERS", 1),
        queue_size=env_int("TOOL_PROVIDER_QUEUE_SIZE", 128),
        heartbeat_seconds=float(os.getenv("TOOL_PROVIDER_HEARTBEAT_SECONDS", "20")),
    )
    provider_thread = provider.start(daemon=False)
    try:
        provider_thread.join()
    except KeyboardInterrupt:
        provider.stop()


if __name__ == "__main__":
    main()