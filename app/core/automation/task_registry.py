import asyncio
from abc import ABC, abstractmethod

from app.domain.automation.contracts import Task


class TaskHandler(ABC):
    @abstractmethod
    async def execute(self, task: Task) -> dict[str, object]: ...


class RespondHandler(TaskHandler):
    async def execute(self, task: Task) -> dict[str, object]:
        return {"status": "completed", "action": "respond"}


class QueryKnowledgeHandler(TaskHandler):
    async def execute(self, task: Task) -> dict[str, object]:
        return {"status": "completed", "action": "query_knowledge"}


class EscalateHandler(TaskHandler):
    async def execute(self, task: Task) -> dict[str, object]:
        return {"status": "completed", "action": "escalate", "target": task.target}


class DelayHandler(TaskHandler):
    async def execute(self, task: Task) -> dict[str, object]:
        raw = task.parameters.get("seconds", 1.0)
        seconds = float(raw) if isinstance(raw, (int, float)) else 1.0
        await asyncio.sleep(seconds)
        return {
            "status": "completed",
            "action": "delay",
            "duration_seconds": seconds,
        }


class HttpCallHandler(TaskHandler):
    async def execute(self, task: Task) -> dict[str, object]:
        return {
            "status": "completed",
            "action": "http_call",
            "target": task.target,
        }


class TaskRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, TaskHandler] = {}

    def register(self, action: str, handler: TaskHandler) -> None:
        self._handlers[action] = handler

    def resolve(self, action: str) -> TaskHandler:
        handler = self._handlers.get(action)
        if handler is None:
            raise ValueError(f"No handler registered for action: '{action}'")
        return handler


def create_default_registry() -> TaskRegistry:
    registry = TaskRegistry()
    registry.register("respond", RespondHandler())
    registry.register("query_knowledge", QueryKnowledgeHandler())
    registry.register("escalate", EscalateHandler())
    registry.register("delay", DelayHandler())
    registry.register("http_call", HttpCallHandler())
    return registry
