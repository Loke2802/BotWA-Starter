from uuid import uuid4

import pytest
from app.domain.knowledge_management.contracts import (
    KnowledgeEntry,
    KnowledgeEntryCreate,
    KnowledgeEntryUpdate,
)
from pydantic import ValidationError


def test_knowledge_entry_contract_defaults_to_manual_draft() -> None:
    entry = KnowledgeEntry(
        organization_id=uuid4(),
        bot_id=uuid4(),
        title="  Returns  ",
        content="  Returns are accepted for 30 days.  ",
        created_by_user_id=uuid4(),
    )

    assert entry.title == "Returns"
    assert entry.content == "Returns are accepted for 30 days."
    assert entry.status == "draft"
    assert entry.source_type == "manual"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", " "),
        ("content", " "),
        ("title", "x" * 201),
        ("content", "x" * 20_001),
    ],
)
def test_knowledge_entry_create_rejects_invalid_content(
    field: str,
    value: str,
) -> None:
    payload = {"title": "Title", "content": "Content", field: value}
    with pytest.raises(ValidationError):
        KnowledgeEntryCreate.model_validate(payload)


def test_knowledge_entry_update_forbids_state_and_scope_changes() -> None:
    with pytest.raises(ValidationError):
        KnowledgeEntryUpdate.model_validate({"status": "published"})
    with pytest.raises(ValidationError):
        KnowledgeEntryUpdate.model_validate({"bot_id": str(uuid4())})
