from app.core.knowledge.normalizer import ContentNormalizer
from app.domain.knowledge.contracts import KnowledgeItem


def test_content_normalizer_cleans_html() -> None:
    normalizer = ContentNormalizer()
    items = [
        KnowledgeItem(
            source_id="src-1",
            content="<p>Some <b>content</b></p>",
            confidence="high",
        ),
    ]

    normalized = normalizer.normalize(items)

    assert len(normalized) == 1
    assert normalized[0].canonical_content == "Some content"


def test_content_normalizer_normalizes_whitespace() -> None:
    normalizer = ContentNormalizer()
    items = [
        KnowledgeItem(
            source_id="src-1",
            content="  Too   much   space  ",
            confidence="high",
        ),
    ]

    normalized = normalizer.normalize(items)

    assert normalized[0].canonical_content == "Too much space"


def test_content_normalizer_preserves_metadata() -> None:
    normalizer = ContentNormalizer()
    items = [
        KnowledgeItem(
            source_id="src-1",
            content="Some content",
            confidence="high",
            source_trust_level=0.8,
        ),
    ]

    normalized = normalizer.normalize(items)

    assert normalized[0].source_id == "src-1"
    assert normalized[0].confidence == "high"
    assert normalized[0].source_trust_level == 0.8


def test_content_normalizer_multiple_items() -> None:
    normalizer = ContentNormalizer()
    items = [
        KnowledgeItem(source_id="src-1", content="Content 1", confidence="high"),
        KnowledgeItem(source_id="src-2", content="Content 2", confidence="medium"),
    ]

    normalized = normalizer.normalize(items)

    assert len(normalized) == 2
    assert normalized[1].source_id == "src-2"
    assert normalized[1].canonical_content == "Content 2"


def test_content_normalizer_empty_list() -> None:
    normalizer = ContentNormalizer()

    normalized = normalizer.normalize([])

    assert normalized == []


def test_content_normalizer_strips_html_and_whitespace() -> None:
    normalizer = ContentNormalizer()
    items = [
        KnowledgeItem(
            source_id="src-1",
            content="  <div>Hello  <span>world</span></div>  ",
            confidence="high",
        ),
    ]

    normalized = normalizer.normalize(items)

    assert normalized[0].canonical_content == "Hello world"
