from app.core.knowledge.validator import QualityValidator
from app.domain.knowledge.contracts import ResolvedKnowledgeItem


def test_quality_validator_approves_high_confidence() -> None:
    validator = QualityValidator()
    item = ResolvedKnowledgeItem(
        sources=["src-1"],
        content="This is a valid long content for testing",
        confidence="high",
    )

    validated = validator.validate(item)

    assert validated.health_score == 1.0
    assert validated.validity_status == "approved"


def test_quality_validator_quarantines_empty_content() -> None:
    validator = QualityValidator()
    item = ResolvedKnowledgeItem(content="")

    validated = validator.validate(item)

    assert validated.health_score == 0.0
    assert validated.validity_status == "quarantined"


def test_quality_validator_quarantines_short_content() -> None:
    validator = QualityValidator()
    item = ResolvedKnowledgeItem(
        sources=["src-1"],
        content="Short",
        confidence="high",
    )

    validated = validator.validate(item)

    assert validated.health_score == 0.3
    assert validated.validity_status == "quarantined"


def test_quality_validator_medium_confidence() -> None:
    validator = QualityValidator()
    item = ResolvedKnowledgeItem(
        sources=["src-1"],
        content="This is a valid medium confidence content",
        confidence="medium",
    )

    validated = validator.validate(item)

    assert validated.health_score == 0.7
    assert validated.validity_status == "approved"


def test_quality_validator_low_confidence() -> None:
    validator = QualityValidator()
    item = ResolvedKnowledgeItem(
        sources=["src-1"],
        content="This is a valid long content for testing low confidence",
        confidence="low",
    )

    validated = validator.validate(item)

    assert validated.health_score == 0.5
    assert validated.validity_status == "quarantined"


def test_quality_validator_empty_sources() -> None:
    validator = QualityValidator()
    item = ResolvedKnowledgeItem(content="Valid content here for testing")

    validated = validator.validate(item)

    assert validated.source_id == ""
    assert validated.content == "Valid content here for testing"
