from uuid import UUID

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session

from app.application.knowledge_management.repository import KnowledgeEntryRepository
from app.domain.knowledge_management.contracts import KnowledgeEntryStatus
from app.infrastructure.models.knowledge_entry import KnowledgeEntryModel


class SqlAlchemyKnowledgeEntryRepository(KnowledgeEntryRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, entry: KnowledgeEntryModel) -> None:
        self._session.add(entry)

    def get_scoped(
        self,
        entry_id: UUID,
        organization_id: UUID,
        bot_id: UUID,
    ) -> KnowledgeEntryModel | None:
        stmt = select(KnowledgeEntryModel).where(
            KnowledgeEntryModel.id == entry_id,
            KnowledgeEntryModel.organization_id == organization_id,
            KnowledgeEntryModel.bot_id == bot_id,
        )
        return self._session.scalars(stmt).first()

    @staticmethod
    def _filters(
        organization_id: UUID,
        bot_id: UUID,
        status: KnowledgeEntryStatus | None,
        search: str | None,
    ) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = [
            KnowledgeEntryModel.organization_id == organization_id,
            KnowledgeEntryModel.bot_id == bot_id,
        ]
        if status is not None:
            filters.append(KnowledgeEntryModel.status == status)
        if search:
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    KnowledgeEntryModel.title.ilike(pattern),
                    KnowledgeEntryModel.content.ilike(pattern),
                ),
            )
        return filters

    def list_scoped(
        self,
        organization_id: UUID,
        bot_id: UUID,
        *,
        status: KnowledgeEntryStatus | None,
        search: str | None,
        offset: int,
        limit: int,
    ) -> list[KnowledgeEntryModel]:
        stmt = (
            select(KnowledgeEntryModel)
            .where(*self._filters(organization_id, bot_id, status, search))
            .order_by(KnowledgeEntryModel.created_at, KnowledgeEntryModel.id)
            .offset(offset)
            .limit(limit)
        )
        return list(self._session.scalars(stmt).all())

    def count_scoped(
        self,
        organization_id: UUID,
        bot_id: UUID,
        *,
        status: KnowledgeEntryStatus | None,
        search: str | None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(KnowledgeEntryModel)
            .where(*self._filters(organization_id, bot_id, status, search))
        )
        return int(self._session.execute(stmt).scalar_one())

    def list_published(
        self,
        organization_id: UUID,
        bot_id: UUID,
        *,
        search: str | None,
        limit: int,
    ) -> list[KnowledgeEntryModel]:
        return self.list_scoped(
            organization_id,
            bot_id,
            status="published",
            search=search,
            offset=0,
            limit=limit,
        )

    def delete(self, entry: KnowledgeEntryModel) -> None:
        self._session.delete(entry)


class InMemoryKnowledgeEntryRepository(KnowledgeEntryRepository):
    def __init__(self) -> None:
        self.entries: dict[UUID, KnowledgeEntryModel] = {}

    def add(self, entry: KnowledgeEntryModel) -> None:
        self.entries[entry.id] = entry

    def get_scoped(
        self,
        entry_id: UUID,
        organization_id: UUID,
        bot_id: UUID,
    ) -> KnowledgeEntryModel | None:
        entry = self.entries.get(entry_id)
        if (
            entry is None
            or entry.organization_id != organization_id
            or entry.bot_id != bot_id
        ):
            return None
        return entry

    @staticmethod
    def _matches(
        entry: KnowledgeEntryModel,
        organization_id: UUID,
        bot_id: UUID,
        status: KnowledgeEntryStatus | None,
        search: str | None,
    ) -> bool:
        if entry.organization_id != organization_id or entry.bot_id != bot_id:
            return False
        if status is not None and entry.status != status:
            return False
        if search:
            text = search.lower()
            return text in entry.title.lower() or text in entry.content.lower()
        return True

    def list_scoped(
        self,
        organization_id: UUID,
        bot_id: UUID,
        *,
        status: KnowledgeEntryStatus | None,
        search: str | None,
        offset: int,
        limit: int,
    ) -> list[KnowledgeEntryModel]:
        matches = [
            entry
            for entry in self.entries.values()
            if self._matches(entry, organization_id, bot_id, status, search)
        ]
        matches.sort(key=lambda entry: (entry.created_at, entry.id))
        return matches[offset : offset + limit]

    def count_scoped(
        self,
        organization_id: UUID,
        bot_id: UUID,
        *,
        status: KnowledgeEntryStatus | None,
        search: str | None,
    ) -> int:
        return sum(
            self._matches(entry, organization_id, bot_id, status, search)
            for entry in self.entries.values()
        )

    def list_published(
        self,
        organization_id: UUID,
        bot_id: UUID,
        *,
        search: str | None,
        limit: int,
    ) -> list[KnowledgeEntryModel]:
        return self.list_scoped(
            organization_id,
            bot_id,
            status="published",
            search=search,
            offset=0,
            limit=limit,
        )

    def delete(self, entry: KnowledgeEntryModel) -> None:
        self.entries.pop(entry.id, None)
