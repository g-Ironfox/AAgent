# Tool Provider

该容器提供同步 `Tool` 抽象基类和线程化 `ToolProvider`。工具实现只负责声明 Schema 并实现 `execute`，注册、队列、并发、心跳、取消和结果回传由运行时处理。

## 创建工具

在 `tools` 目录增加模块，并继承 `Tool`：

```python
from typing import Any

from tool import Tool, ToolContext


class SearchTool(Tool):
    name = "web.search"
    description = "搜索公开网页"
    input_schema = {
        "type": "object",
        "properties": {"keyword": {"type": "string"}},
        "required": ["keyword"],
        "additionalProperties": False,
    }
    output_schema = {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {"type": "string"},
                "x-workflow-port-type": "list-content",
            }
        },
        "required": ["results"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, list[str]]:
        context.report_progress(0.5, "正在搜索")
        return {"results": [arguments["keyword"]]}
```

每个工具必须显式声明 `output_schema`。输出统一使用具名对象，一级属性对应 Workflow 的输出端口；对象必须声明 `required` 并设置 `additionalProperties: False`。可通过 `x-workflow-port-type` 将属性标记为 `content`、`message`、`list-content` 或 `list-message`。

## 实例化并启动

`start()` 内部使用 `threading.Thread` 启动 Provider，适合嵌入已有 Python 进程：

```python
from runtime import ToolProvider
from tools.search import SearchTool


provider = ToolProvider(
    tools=[SearchTool()],
    server_url="ws://localhost:8083/ws/providers",
    provider_id="provider-web-01",
    consumers=2,
)
provider_thread = provider.start()

# 主程序退出时：
provider.stop()
```

也可以自行创建线程：

```python
import threading


provider_thread = threading.Thread(target=provider.run, daemon=True)
provider_thread.start()
```

将模块加入 `TOOL_MODULES`，多个模块使用逗号分隔：

```text
TOOL_MODULES=tools.search
```

修改工具 Schema 后必须递增 `TOOL_PROVIDER_REVISION`。`TOOL_PROVIDER_CONSUMERS` 控制并发 Consumer 数量，`TOOL_PROVIDER_QUEUE_SIZE` 控制内部有界队列容量。

## ToolContext

- `task_id`：当前 Tool Server 任务 ID。
- `deadline`：调用方提供的 ISO 时间期限。
- `cancelled()`：协作式取消状态；长循环应定期检查。
- `report_progress(progress, message)`：同步上报 $0$ 到 $1$ 的执行进度。

取消是协作式的。运行时间较长的工具应在循环或阶段边界调用 `context.cancelled()` 并尽快返回；Python 线程不会被框架强制终止。

