from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from app.application.knowledge_management.service import (
    KnowledgeEntryConflictError,
    KnowledgeManagementService,
)
from app.domain.knowledge_management.contracts import KnowledgeEntryCreate
from app.domain.user.contracts import User
from app.infrastructure.repositories.knowledge_entry_repository import (
    InMemoryKnowledgeEntryRepository,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.plan_support import allow_all_plan_enforcement


def test_integrity_error_rolls_back_and_becomes_domain_conflict() -> None:
    organization_id = uuid4()
    bot_id = uuid4()
    actor = User(
        organization_id=organization_id,
        email="owner@example.com",
        role="organization_owner",
    )
    session = MagicMock(spec=Session)
    session.commit.side_effect = IntegrityError("insert", {}, Exception("conflict"))
    bot_repository = MagicMock()
    bot_repository.get.return_value = SimpleNamespace(
        organization_id=organization_id,
    )
    organization_repository = MagicMock()
    organization_repository.get.return_value = SimpleNamespace(status="active")
    service = KnowledgeManagementService(
        repository=InMemoryKnowledgeEntryRepository(),
        bot_repository=bot_repository,
        organization_repository=organization_repository,
        session=session,
        plan_enforcement=allow_all_plan_enforcement(),
        audit_writer=MagicMock(),
    )

    with pytest.raises(KnowledgeEntryConflictError):
        service.create(
            organization_id,
            bot_id,
            KnowledgeEntryCreate(title="Title", content="Content"),
            actor,
        )

    session.rollback.assert_called_once_with()
