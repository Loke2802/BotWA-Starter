from uuid import uuid4

from app.core.automation.event_publisher import AutomationEventPublisher
from app.infrastructure.models.business_event import BusinessEventModel


class FakeEventRepo:
    def __init__(self) -> None:
        self.events: list[BusinessEventModel] = []

    def add(self, event: BusinessEventModel) -> None:
        self.events.append(event)


def test_event_publisher_no_repo_does_not_crash() -> None:
    publisher = AutomationEventPublisher()
    publisher.publish("automation.execution.started", uuid4())


def test_event_publisher_with_repo_stores_event() -> None:
    fake_repo = FakeEventRepo()
    publisher = AutomationEventPublisher(event_repository=fake_repo)
    execution_id = uuid4()

    publisher.publish("automation.execution.started", execution_id)

    assert len(fake_repo.events) == 1
    event = fake_repo.events[0]
    assert event.event_type == "automation.execution.started"
    assert event.source == "automation_engine"
    assert event.payload is not None
    assert event.payload.get("execution_id") == str(execution_id)


def test_event_publisher_multiple_events() -> None:
    fake_repo = FakeEventRepo()
    publisher = AutomationEventPublisher(event_repository=fake_repo)
    execution_id = uuid4()

    publisher.publish("automation.task.started", execution_id, task_id=str(uuid4()))
    publisher.publish("automation.task.completed", execution_id)
    publisher.publish("automation.execution.completed", execution_id)

    assert len(fake_repo.events) == 3
    assert fake_repo.events[0].event_type == "automation.task.started"
    assert fake_repo.events[1].event_type == "automation.task.completed"
    assert fake_repo.events[2].event_type == "automation.execution.completed"


def test_event_publisher_extra_payload() -> None:
    fake_repo = FakeEventRepo()
    publisher = AutomationEventPublisher(event_repository=fake_repo)
    execution_id = uuid4()

    publisher.publish(
        "automation.task.failed",
        execution_id,
        task_id=str(uuid4()),
        error="Something went wrong",
    )

    event = fake_repo.events[0]
    assert event.payload is not None
    assert event.payload.get("error") == "Something went wrong"
