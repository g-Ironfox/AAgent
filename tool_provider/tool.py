from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable


ProgressReporter = Callable[[float, str | None], None]


@dataclass(frozen=True)
class ToolContext:
    task_id: str
    deadline: str | None
    cancelled: Callable[[], bool]
    report_progress: ProgressReporter


class Tool(ABC):
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    annotations: dict[str, Any] = {}

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "outputSchema": self.output_schema,
            "annotations": self.annotations,
        }

    @abstractmethod
    def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        raise NotImplementedError