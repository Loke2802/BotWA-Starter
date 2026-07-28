from uuid import uuid4

import pytest
from app.core.automation.task_registry import (
    DelayHandler,
    EscalateHandler,
    HttpCallHandler,
    QueryKnowledgeHandler,
    RespondHandler,
    TaskHandler,
    TaskRegistry,
    create_default_registry,
)
from app.domain.automation.contracts import Task


@pytest.mark.asyncio
async def test_respond_handler() -> None:
    handler = RespondHandler()
    task = Task(task_id=uuid4(), action="respond")
    result = await handler.execute(task)
    assert result["status"] == "completed"
    assert result["action"] == "respond"


@pytest.mark.asyncio
async def test_query_knowledge_handler() -> None:
    handler = QueryKnowledgeHandler()
    task = Task(task_id=uuid4(), action="query_knowledge")
    result = await handler.execute(task)
    assert result["status"] == "completed"
    assert result["action"] == "query_knowledge"


@pytest.mark.asyncio
async def test_escalate_handler() -> None:
    handler = EscalateHandler()
    task = Task(
        task_id=uuid4(),
        action="escalate",
        target="support@example.com",
    )
    result = await handler.execute(task)
    assert result["status"] == "completed"
    assert result["action"] == "escalate"
    assert result["target"] == "support@example.com"


@pytest.mark.asyncio
async def test_delay_handler() -> None:
    handler = DelayHandler()
    task = Task(
        task_id=uuid4(),
        action="delay",
        parameters={"seconds": 0.01},
    )
    result = await handler.execute(task)
    assert result["status"] == "completed"
    assert result["action"] == "delay"
    assert result["duration_seconds"] == 0.01


@pytest.mark.asyncio
async def test_http_call_handler() -> None:
    handler = HttpCallHandler()
    task = Task(
        task_id=uuid4(),
        action="http_call",
        target="https://api.example.com/webhook",
    )
    result = await handler.execute(task)
    assert result["status"] == "completed"
    assert result["action"] == "http_call"
    assert result["target"] == "https://api.example.com/webhook"


def test_registry_register_and_resolve() -> None:
    registry = TaskRegistry()
    handler = RespondHandler()
    registry.register("respond", handler)
    resolved = registry.resolve("respond")
    assert resolved is handler


def test_registry_resolve_unregistered_raises() -> None:
    registry = TaskRegistry()
    with pytest.raises(ValueError, match="No handler registered for action: 'unknown'"):
        registry.resolve("unknown")


def test_registry_implements_handler_abc() -> None:
    assert issubclass(RespondHandler, TaskHandler)
    assert issubclass(QueryKnowledgeHandler, TaskHandler)
    assert issubclass(EscalateHandler, TaskHandler)
    assert issubclass(DelayHandler, TaskHandler)
    assert issubclass(HttpCallHandler, TaskHandler)


def test_create_default_registry_resolves_all_actions() -> None:
    registry = create_default_registry()
    assert registry.resolve("respond") is not None
    assert registry.resolve("query_knowledge") is not None
    assert registry.resolve("escalate") is not None
    assert registry.resolve("delay") is not None
    assert registry.resolve("http_call") is not None


@pytest.mark.asyncio
async def test_delay_handler_default_seconds() -> None:
    handler = DelayHandler()
    task = Task(task_id=uuid4(), action="delay")
    result = await handler.execute(task)
    assert result["duration_seconds"] == 1.0


@pytest.mark.asyncio
async def test_http_call_handler_empty_target() -> None:
    handler = HttpCallHandler()
    task = Task(task_id=uuid4(), action="http_call")
    result = await handler.execute(task)
    assert result["target"] == ""
