from datetime import UTC, datetime, timedelta

from app.core.knowledge.resolver import BestMatchResolver
from app.domain.knowledge.contracts import NormalizedKnowledgeItem


def _item(
    source_id: str,
    content: str,
    confidence: str = "high",
    trust_level: float = 1.0,
    **kwargs: object,
) -> NormalizedKnowledgeItem:
    return NormalizedKnowledgeItem(
        source_id=source_id,
        canonical_content=content,
        confidence=confidence,
        source_trust_level=trust_level,
        **kwargs,
    )


def test_best_match_resolver_selects_highest_confidence() -> None:
    resolver = BestMatchResolver()
    items = [
        _item("src-1", "Low confidence answer", confidence="low"),
        _item("src-2", "High confidence answer", confidence="high"),
    ]

    resolved = resolver.resolve(items)

    assert resolved.content == "High confidence answer"
    assert resolved.confidence == "high"
    assert resolved.resolution_strategy == "best_match"


def test_best_match_resolver_prefers_higher_trust() -> None:
    resolver = BestMatchResolver()
    items = [
        _item("src-1", "From untrusted source", trust_level=0.3),
        _item("src-2", "From trusted source", trust_level=1.0),
    ]

    resolved = resolver.resolve(items)

    assert resolved.content == "From trusted source"


def test_best_match_resolver_prefers_fresher_content() -> None:
    resolver = BestMatchResolver()
    now = datetime.now(UTC)
    items = [
        _item(
            "src-1",
            "Old content",
            retrieved_at=now - timedelta(hours=48),
        ),
        _item(
            "src-2",
            "Fresh content",
            retrieved_at=now - timedelta(hours=1),
        ),
    ]

    resolved = resolver.resolve(items)

    assert resolved.content == "Fresh content"


def test_best_match_resolver_lists_all_sources() -> None:
    resolver = BestMatchResolver()
    items = [
        _item("src-1", "Answer A"),
        _item("src-2", "Answer B"),
    ]

    resolved = resolver.resolve(items)

    assert resolved.sources == ["src-1", "src-2"]
    assert resolved.content == "Answer A"


def test_best_match_resolver_empty_list() -> None:
    resolver = BestMatchResolver()

    resolved = resolver.resolve([])

    assert resolved.content == ""
    assert resolved.sources == []
    assert resolved.resolution_strategy == "best_match"


def test_best_match_resolver_single_source() -> None:
    resolver = BestMatchResolver()
    items = [_item("src-1", "Only source")]

    resolved = resolver.resolve(items)

    assert resolved.content == "Only source"
    assert resolved.sources == ["src-1"]
