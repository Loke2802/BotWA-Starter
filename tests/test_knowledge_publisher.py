from app.core.knowledge.publisher import InMemoryKnowledgePublisher
from app.domain.knowledge.contracts import ValidatedKnowledgeItem


def test_publish_found_item() -> None:
    publisher = InMemoryKnowledgePublisher()
    item = ValidatedKnowledgeItem(
        source_id="src-1",
        content="Published content",
        confidence="high",
    )

    response = publisher.publish(item)

    assert response.found is True
    assert response.content == "Published content"
    assert response.confidence == "high"
    assert response.sources == ["src-1"]
    assert response.version == 1


def test_publish_empty_content() -> None:
    publisher = InMemoryKnowledgePublisher()
    item = ValidatedKnowledgeItem(content="")

    response = publisher.publish(item)

    assert response.found is False


def test_publish_multiple_sources() -> None:
    publisher = InMemoryKnowledgePublisher()
    item = ValidatedKnowledgeItem(
        source_id="src-2",
        content="Multi-source content",
        confidence="medium",
    )

    response = publisher.publish(item)

    assert response.found is True
    assert response.sources == ["src-2"]


def test_publish_version_increments_for_same_source() -> None:
    publisher = InMemoryKnowledgePublisher()
    v1 = ValidatedKnowledgeItem(
        source_id="src-1",
        content="Version 1",
        confidence="high",
        version=1,
    )
    v2 = ValidatedKnowledgeItem(
        source_id="src-1",
        content="Version 2",
        confidence="high",
        version=2,
    )

    r1 = publisher.publish(v1)
    r2 = publisher.publish(v2)

    assert r1.version == 1
    assert r2.version == 2
