from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.audit.writer import append_user_audit
from app.application.crm.presentation import aware, record, redact
from app.domain.crm.contracts import (
    DEFAULT_STAGES,
    CommercialContext,
    CrmConflict,
    HistoryRecord,
    OpportunityCreate,
    OpportunityInput,
    OpportunityList,
    OpportunityRecord,
    OpportunityUpdate,
    Stage,
    StageConfiguration,
)
from app.domain.user.contracts import User
from app.infrastructure.models.crm_opportunity import (
    CrmStageModel,
    OpportunityActivityModel,
    OpportunityConversationModel,
    OpportunityHistoryModel,
    OpportunityModel,
)
from app.infrastructure.models.whatsapp_channel_configuration import (
    WhatsAppChannelConfigurationModel,
)
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.crm_identity import canonical
from app.infrastructure.repositories.crm_opportunity_repository import (
    OpportunityRepository,
)
from app.security.authorization import has_permission, require_scoped_permission
from app.security.secret_cipher import SecretCipher


class OpportunityService:
    def __init__(self, session: Session, cipher: SecretCipher, digest_key: str) -> None:
        self.session = session
        self.cipher = cipher
        self.digest_key = digest_key
        self.repository = OpportunityRepository(session)

    def _read(self, org: UUID, actor: User) -> None:
        require_scoped_permission(actor, "crm.opportunities.read", org)
        require_scoped_permission(actor, "contacts.read", org)

    def _write(self, org: UUID, actor: User) -> None:
        self._read(org, actor)
        require_scoped_permission(actor, "crm.opportunities.write", org)
        require_scoped_permission(actor, "crm.opportunities.read_content", org)

    def _record(self, row: OpportunityModel, actor: User) -> OpportunityRecord:
        return record(
            self.repository,
            self.cipher,
            row,
            content=has_permission(actor, "crm.opportunities.read_content"),
        )

    def stages(self, org: UUID, actor: User) -> list[Stage]:
        self._read(org, actor)
        self.repository.organization(org)
        rows = self.repository.stages(org)
        return (
            [
                Stage(code=r.code, name=r.name, kind=r.kind, position=r.position)
                for r in rows
            ]
            if rows
            else [
                Stage(code=code, name=name, kind=kind, position=i)
                for i, (code, name, kind) in enumerate(DEFAULT_STAGES)
            ]
        )

    def _initialize_stages(self, org: UUID) -> None:
        if not self.repository.stages(org):
            self.session.add_all(
                [
                    CrmStageModel(
                        organization_id=org, code=code, name=name, kind=kind, position=i
                    )
                    for i, (code, name, kind) in enumerate(DEFAULT_STAGES)
                ]
            )
            self.session.flush()

    def configure_stages(
        self, org: UUID, actor: User, data: StageConfiguration
    ) -> list[Stage]:
        require_scoped_permission(actor, "crm.stages.manage", org)
        self._read(org, actor)
        try:
            self.repository.organization(org, lock=True)
            self._initialize_stages(org)
            existing = {s.code: s for s in self.repository.stages(org)}
            if data.expected_stages is not None:
                expected = {s.code: s.model_dump() for s in data.expected_stages}
                actual = {
                    s.code: Stage(
                        code=s.code, name=s.name, kind=s.kind, position=s.position
                    ).model_dump()
                    for s in existing.values()
                }
                if expected != actual:
                    raise CrmConflict(
                        "Las etapas cambiaron en otra sesión. "
                        "Actualiza antes de guardar."
                    )
            if not set(existing).issubset({s.code for s in data.stages}):
                raise CrmConflict("Conserva los códigos de las etapas existentes.")
            for stage in data.stages:
                if stage.code in existing:
                    row = existing[stage.code]
                    if row.kind != stage.kind:
                        raise CrmConflict(
                            "El tipo de una etapa existente no puede cambiar."
                        )
                    row.name, row.position = stage.name, stage.position
                else:
                    self.session.add(
                        CrmStageModel(organization_id=org, **stage.model_dump())
                    )
            append_user_audit(
                SqlAlchemyAuditRepository(self.session),
                organization_id=org,
                actor=actor,
                action="crm.stages_updated",
                resource_type="organization",
                resource_id=org,
            )
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return self.stages(org, actor)

    def context(
        self, org: UUID, conversation_id: UUID, actor: User
    ) -> CommercialContext:
        self._read(org, actor)
        require_scoped_permission(actor, "conversation.read", org)
        row = self.repository.conversation(org, conversation_id)
        if row.contact_id:
            self.repository.contact(org, row.contact_id)
        account = self.session.scalar(
            select(WhatsAppChannelConfigurationModel).where(
                WhatsAppChannelConfigurationModel.id == row.channel_configuration_id,
                WhatsAppChannelConfigurationModel.organization_id == org,
            )
        )
        organization = self.repository.organization(org)
        return CommercialContext(
            conversation_id=row.id,
            contact_id=(
                canonical(self.session, org, row.contact_id) if row.contact_id else None
            ),
            channel_type=row.channel,
            channel_configuration_id=row.channel_configuration_id,
            account_name=account.display_name if account else None,
            timezone=str(organization.settings.get("timezone") or "UTC"),
            can_write=has_permission(actor, "crm.opportunities.write")
            and has_permission(actor, "crm.opportunities.read_content"),
        )

    def list_opportunities(
        self,
        org: UUID,
        actor: User,
        *,
        contact_id: UUID | None = None,
        conversation_id: UUID | None = None,
        assigned_user_id: UUID | None = None,
        stage_code: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> OpportunityList:
        self._read(org, actor)
        self.repository.organization(org)
        if contact_id:
            self.repository.contact(org, contact_id)
        if conversation_id:
            require_scoped_permission(actor, "conversation.read", org)
            self.repository.conversation(org, conversation_id)
        rows, total = self.repository.page(
            org,
            contact_id=contact_id,
            conversation_id=conversation_id,
            assigned_user_id=assigned_user_id,
            stage_code=stage_code,
            page=page,
            page_size=page_size,
        )
        return OpportunityList(
            items=[self._record(r, actor) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
            has_next=page * page_size < total,
        )

    def get(self, org: UUID, opportunity_id: UUID, actor: User) -> OpportunityRecord:
        self._read(org, actor)
        return self._record(self.repository.opportunity(org, opportunity_id), actor)

    def history(
        self,
        org: UUID,
        opportunity_id: UUID,
        actor: User,
        page: int,
        page_size: int,
        *,
        through_version: int | None = None,
    ) -> list[HistoryRecord]:
        self._read(org, actor)
        self.repository.opportunity(org, opportunity_id)
        rows = self.repository.history(
            org, opportunity_id, page, page_size, through_version=through_version
        )
        result = []
        for row in rows:
            snapshot = OpportunityRecord.model_validate_json(
                self.cipher.decrypt(row.snapshot_ciphertext)
            )
            if not has_permission(actor, "crm.opportunities.read_content"):
                snapshot = redact(snapshot)
            result.append(
                HistoryRecord(
                    version=row.version,
                    actor_user_id=row.actor_user_id,
                    occurred_at=aware(row.occurred_at),
                    snapshot=snapshot,
                )
            )
        return result

    def _validate(
        self, org: UUID, data: OpportunityInput, *, creating: bool = False
    ) -> str:
        self.repository.validate_assignee(org, data.assigned_user_id)
        stage = next(
            (s for s in self.repository.stages(org) if s.code == data.stage_code), None
        )
        if stage is None:
            raise ValueError("unknown stage")
        if creating and stage.kind != "open":
            raise ValueError("create an open opportunity")
        if stage.kind == "open":
            if not data.next_action and not data.no_action_reason:
                raise ValueError("next action or reason required")
            if data.close_reason:
                raise ValueError("open opportunities cannot have a close reason")
        elif not data.close_reason or data.next_action or data.no_action_reason:
            raise ValueError("closed opportunity requires reason and no next action")
        return stage.kind

    def _apply(self, row: OpportunityModel, data: OpportunityInput, kind: str) -> None:
        def encrypt(value: str | None) -> str | None:
            return self.cipher.encrypt(value) if value else None

        row.title_ciphertext = self.cipher.encrypt(data.title)
        row.need_ciphertext = encrypt(data.need)
        row.stage_code, row.assigned_user_id = data.stage_code, data.assigned_user_id
        row.amount, row.currency = data.amount, data.currency
        row.no_action_reason_ciphertext = encrypt(data.no_action_reason)
        row.close_reason_ciphertext = encrypt(data.close_reason)
        row.updated_at = datetime.now(UTC)
        row.closed_at = row.updated_at if kind != "open" else None
        if data.next_action:
            self.session.add(
                OpportunityActivityModel(
                    opportunity_id=row.id,
                    organization_id=row.organization_id,
                    version=row.version,
                    assigned_user_id=row.assigned_user_id,
                    description_ciphertext=self.cipher.encrypt(
                        data.next_action.description
                    ),
                    due_at=data.next_action.due_at.astimezone(UTC),
                    status="pending",
                )
            )

    def _history(self, row: OpportunityModel, actor: User) -> None:
        self.session.flush()
        snapshot = record(self.repository, self.cipher, row, content=True)
        self.session.add(
            OpportunityHistoryModel(
                opportunity_id=row.id,
                version=row.version,
                organization_id=row.organization_id,
                actor_user_id=actor.id,
                snapshot_ciphertext=self.cipher.encrypt(snapshot.model_dump_json()),
            )
        )
        append_user_audit(
            SqlAlchemyAuditRepository(self.session),
            organization_id=row.organization_id,
            actor=actor,
            action="crm.opportunity_saved",
            resource_type="crm_opportunity",
            resource_id=row.id,
        )

    def _link(self, row: OpportunityModel, conversation_id: UUID, actor: User) -> None:
        require_scoped_permission(actor, "conversation.read", row.organization_id)
        conversation = self.repository.conversation(
            row.organization_id, conversation_id
        )
        if (
            conversation.contact_id != row.contact_id
            and conversation.contact_id
            and canonical(self.session, row.organization_id, conversation.contact_id)
            == row.contact_id
        ):
            conversation.contact_id = row.contact_id
            self.session.flush()
        if conversation.contact_id != row.contact_id:
            raise CrmConflict(
                "La conversación y la oportunidad deben tener el mismo contacto."
            )
        existing = self.session.get(
            OpportunityConversationModel, (row.id, conversation_id)
        )
        if existing:
            return
        self.session.add(
            OpportunityConversationModel(
                opportunity_id=row.id,
                conversation_id=conversation_id,
                organization_id=row.organization_id,
                contact_id=row.contact_id,
                actor_user_id=actor.id,
            )
        )
        append_user_audit(
            SqlAlchemyAuditRepository(self.session),
            organization_id=row.organization_id,
            actor=actor,
            action="crm.conversation_linked",
            resource_type="crm_opportunity",
            resource_id=row.id,
        )

    def create(
        self, org: UUID, actor: User, data: OpportunityCreate, key: str
    ) -> OpportunityRecord:
        self._write(org, actor)
        digest = hmac.new(
            self.digest_key.encode(), data.model_dump_json().encode(), hashlib.sha256
        ).hexdigest()
        try:
            # Serialize keys across contacts and initialize stages under one lock.
            self.repository.organization(org, lock=True)
            self.repository.contact(org, data.contact_id, lock=True)
            duplicate = self.repository.duplicate(org, actor.id, key)
            if duplicate:
                if duplicate.request_digest != digest:
                    raise CrmConflict("La clave ya se utilizó con otros datos.")
                # Return current authorized state; no writes or duplicate audit.
                return self._record(duplicate, actor)
            self._initialize_stages(org)
            kind = self._validate(org, data, creating=True)
            row = OpportunityModel(
                id=uuid4(),
                organization_id=org,
                contact_id=canonical(self.session, org, data.contact_id),
                version=1,
                created_by_user_id=actor.id,
                idempotency_key=key,
                request_digest=digest,
            )
            self.session.add(row)
            # Flush parent before inserting the separately constrained activity.
            self._apply(row, data.model_copy(update={"next_action": None}), kind)
            self.session.flush()
            self._apply(row, data, kind)
            if data.conversation_id:
                self._link(row, data.conversation_id, actor)
            self._history(row, actor)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return self._record(row, actor)

    def update(
        self, org: UUID, opportunity_id: UUID, actor: User, data: OpportunityUpdate
    ) -> OpportunityRecord:
        self._write(org, actor)
        try:
            self.repository.organization(org, lock=True)
            row = self.repository.opportunity(org, opportunity_id, lock=True)
            if row.version != data.version:
                raise CrmConflict(
                    "Otra persona actualizó la oportunidad. "
                    "Actualiza antes de guardar."
                )
            kind = self._validate(org, data)
            previous = self.repository.action(row)
            if previous:
                previous.status = (
                    "completed" if data.complete_previous_action else "cancelled"
                )
                previous.resolved_at = datetime.now(UTC)
            row.version += 1
            self._apply(row, data, kind)
            self._history(row, actor)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return self._record(row, actor)

    def link(
        self, org: UUID, opportunity_id: UUID, conversation_id: UUID, actor: User
    ) -> OpportunityRecord:
        self._write(org, actor)
        try:
            self.repository.organization(org, lock=True)
            row = self.repository.opportunity(org, opportunity_id, lock=True)
            self._link(row, conversation_id, actor)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return self._record(row, actor)
