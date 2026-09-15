import asyncio
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket

from models import RegisterMessage, ToolSchema


@dataclass
class ProviderConnection:
    provider_id: str
    revision: int
    tools: dict[str, ToolSchema]
    websocket: WebSocket
    outgoing: asyncio.Queue[dict[str, Any] | None]
    writer: asyncio.Task[None]


class ProviderRegistry:
    def __init__(self):
        self._providers: dict[str, ProviderConnection] = {}
        self._tools: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def register(self, message: RegisterMessage, websocket: WebSocket) -> ProviderConnection:
        async with self._lock:
            current = self._providers.get(message.provider_id)
            if current and message.revision <= current.revision:
                raise ValueError("provider revision must increase")

            for tool in message.tools:
                owner = self._tools.get(tool.name)
                if owner and owner != message.provider_id:
                    raise ValueError(f"tool is already registered: {tool.name}")

            if current:
                await self._remove_locked(current)

            outgoing: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=1024)
            connection = ProviderConnection(
                provider_id=message.provider_id,
                revision=message.revision,
                tools={tool.name: tool for tool in message.tools},
                websocket=websocket,
                outgoing=outgoing,
                writer=asyncio.create_task(self._write_messages(websocket, outgoing)),
            )
            self._providers[message.provider_id] = connection
            for tool in message.tools:
                self._tools[tool.name] = message.provider_id
            return connection

    async def unregister(self, connection: ProviderConnection) -> None:
        async with self._lock:
            if self._providers.get(connection.provider_id) is connection:
                await self._remove_locked(connection)

    async def _remove_locked(self, connection: ProviderConnection) -> None:
        self._providers.pop(connection.provider_id, None)
        for tool_name in connection.tools:
            if self._tools.get(tool_name) == connection.provider_id:
                self._tools.pop(tool_name, None)
        await connection.outgoing.put(None)

    async def send(self, tool_name: str, message: dict[str, Any]) -> bool:
        async with self._lock:
            provider_id = self._tools.get(tool_name)
            connection = self._providers.get(provider_id) if provider_id else None
            if connection is None:
                return False
            try:
                connection.outgoing.put_nowait(message)
            except asyncio.QueueFull:
                return False
            return True

    async def list_tools(self) -> list[dict[str, Any]]:
        async with self._lock:
            return [
                {
                    **tool.model_dump(),
                    "provider_id": provider_id,
                    "revision": self._providers[provider_id].revision,
                }
                for tool_name, provider_id in sorted(self._tools.items())
                for tool in [self._providers[provider_id].tools[tool_name]]
            ]

    async def list_providers(self) -> list[dict[str, Any]]:
        async with self._lock:
            return [
                {
                    "provider_id": provider.provider_id,
                    "revision": provider.revision,
                    "tools": sorted(provider.tools),
                    "queued_messages": provider.outgoing.qsize(),
                }
                for provider in sorted(self._providers.values(), key=lambda item: item.provider_id)
            ]

    async def get_tool(self, tool_name: str) -> ToolSchema | None:
        async with self._lock:
            provider_id = self._tools.get(tool_name)
            provider = self._providers.get(provider_id) if provider_id else None
            return provider.tools.get(tool_name) if provider else None

    @staticmethod
    async def _write_messages(
        websocket: WebSocket,
        outgoing: asyncio.Queue[dict[str, Any] | None],
    ) -> None:
        while True:
            message = await outgoing.get()
            if message is None:
                return
            await websocket.send_json(message)