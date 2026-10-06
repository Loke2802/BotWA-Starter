"""Customer-scoped reads and atomic, idempotent activity recording."""

import hashlib
import hmac
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select

from app.application.audit.writer import append_user_audit
from app.application.crm.presentation import aware
from app.application.crm.service import OpportunityService
from app.domain.crm.contracts import CrmConflict
from app.domain.crm.customer_contracts import (
    ActivityInput,
    ActivityList,
    CustomerAction,
    CustomerActionList,
    CustomerActivity,
    CustomerConversation,
    CustomerWorkspace,
    MergedOrigin,
)
from app.domain.user.contracts import User
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.crm_customer_activity import CrmCustomerActivityModel
from app.infrastructure.models.crm_opportunity import (
    OpportunityActivityModel,
    OpportunityModel,
)
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.crm_identity import canonical, family
from app.security.authorization import has_permission


class CustomerWorkspaceService:
    def __init__(self, commercial: OpportunityService) -> None:
        self.commercial = commercial
        self.session = commercial.session

    def workspace(
        self, org: UUID, contact: UUID, actor: User, page: int, conversation_page: int
    ) -> CustomerWorkspace:
        self.commercial._read(org, actor)
        organization = self.commercial.repository.organization(org)
        self.commercial.repository.contact(org, contact)
        permitted = has_permission(actor, "conversation.read")
        query = select(ConversationModel).where(
            ConversationModel.organization_id == org,
            ConversationModel.contact_id.in_(family(self.session, org, contact)),
            ConversationModel.management_status.is_not(None),
            ConversationModel.bot_id.is_not(None),
        )
        total = (
            int(
                self.session.scalar(select(func.count()).select_from(query.subquery()))
                or 0
            )
            if permitted
            else 0
        )
        rows = (
            self.session.scalars(
                query.order_by(
                    ConversationModel.created_at.desc(), ConversationModel.id
                )
                .offset((conversation_page - 1) * 10)
                .limit(10)
            ).all()
            if permitted
            else []
        )
        return CustomerWorkspace(
            contact_id=canonical(self.session, org, contact),
            timezone=str(organization.settings.get("timezone") or "UTC"),
            can_write=has_permission(actor, "crm.opportunities.write")
            and has_permission(actor, "crm.opportunities.read_content"),
            can_read_conversations=permitted,
            opportunities=self.commercial.list_opportunities(
                org, actor, contact_id=contact, page=page, page_size=10
            ),
            conversations=[
                CustomerConversation(
                    id=r.id, status=r.status, created_at=aware(r.created_at)
                )
                for r in rows
            ],
            conversation_total=total,
            conversation_page=conversation_page,
            conversations_has_next=conversation_page * 10 < total,
            stages=self.commercial.stages(org, actor),
            merged_origins=[
                MergedOrigin(
                    id=origin,
                    name=(
                        self.commercial.cipher.decrypt(row.display_name_ciphertext)
                        if row.display_name_ciphertext
                        else "Sin nombre"
                    ),
                )
                for origin in family(self.session, org, contact)
                if origin != canonical(self.session, org, contact)
                for row in [self.commercial.repository.contact(org, origin)]
            ],
        )

    def _record(self, row: CrmCustomerActivityModel, actor: User) -> CustomerActivity:
        return CustomerActivity(
            id=row.id,
            contact_id=row.contact_id,
            opportunity_id=row.opportunity_id,
            kind=row.kind,
            description=(
                self.commercial.cipher.decrypt(row.description_ciphertext)
                if has_permission(actor, "crm.opportunities.read_content")
                else "Contenido restringido"
            ),
            occurred_at=aware(row.occurred_at),
            created_at=aware(row.created_at),
            actor_user_id=row.actor_user_id,
        )

    def activities(
        self, org: UUID, contact: UUID, actor: User, page: int
    ) -> ActivityList:
        self.commercial._read(org, actor)
        self.commercial.repository.organization(org)
        self.commercial.repository.contact(org, contact)
        query = select(CrmCustomerActivityModel).where(
            CrmCustomerActivityModel.organization_id == org,
            CrmCustomerActivityModel.contact_id.in_(family(self.session, org, contact)),
        )
        total = int(
            self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        )
        rows = self.session.scalars(
            query.order_by(
                CrmCustomerActivityModel.occurred_at.desc(), CrmCustomerActivityModel.id
            )
            .offset((page - 1) * 20)
            .limit(20)
        ).all()
        return ActivityList(
            items=[self._record(r, actor) for r in rows],
            total=total,
            page=page,
            has_next=page * 20 < total,
        )

    def record_activity(
        self, org: UUID, contact: UUID, actor: User, data: ActivityInput, key: str
    ) -> CustomerActivity:
        self.commercial._write(org, actor)
        digest = hmac.new(
            self.commercial.digest_key.encode(),
            (str(contact) + data.model_dump_json()).encode(),
            hashlib.sha256,
        ).hexdigest()
        try:
            self.commercial.repository.organization(org, lock=True)
            self.commercial.repository.contact(org, contact, lock=True)
            previous = self.session.scalar(
                select(CrmCustomerActivityModel).where(
                    CrmCustomerActivityModel.organization_id == org,
                    CrmCustomerActivityModel.actor_user_id == actor.id,
                    CrmCustomerActivityModel.idempotency_key == key,
                )
            )
            if previous:
                if previous.request_digest != digest:
                    raise CrmConflict("La clave ya se utilizó con otra actividad.")
                return self._record(previous, actor)
            if data.opportunity_id:
                opportunity = self.commercial.repository.opportunity(
                    org, data.opportunity_id
                )
                if canonical(self.session, org, opportunity.contact_id) != canonical(
                    self.session, org, contact
                ):
                    raise CrmConflict("La oportunidad debe pertenecer a este cliente.")
            if data.occurred_at.astimezone(UTC) > datetime.now(UTC):
                raise ValueError(
                    "record completed activities; schedule actions in opportunity"
                )
            row = CrmCustomerActivityModel(
                organization_id=org,
                contact_id=(
                    opportunity.contact_id
                    if data.opportunity_id
                    else canonical(self.session, org, contact)
                ),
                opportunity_id=data.opportunity_id,
                actor_user_id=actor.id,
                kind=data.kind,
                description_ciphertext=self.commercial.cipher.encrypt(data.description),
                occurred_at=data.occurred_at.astimezone(UTC),
                idempotency_key=key,
                request_digest=digest,
            )
            self.session.add(row)
            append_user_audit(
                SqlAlchemyAuditRepository(self.session),
                organization_id=org,
                actor=actor,
                action="crm.activity_recorded",
                resource_type="contact",
                resource_id=contact,
            )
            self.session.commit()
            return self._record(row, actor)
        except Exception:
            self.session.rollback()
            raise

    def actions(
        self, org: UUID, contact: UUID, actor: User, page: int
    ) -> CustomerActionList:
        self.commercial._read(org, actor)
        self.commercial.repository.organization(org)
        self.commercial.repository.contact(org, contact)
        query = (
            select(OpportunityActivityModel)
            .join(
                OpportunityModel,
                (OpportunityActivityModel.opportunity_id == OpportunityModel.id)
                & (
                    OpportunityActivityModel.organization_id
                    == OpportunityModel.organization_id
                ),
            )
            .where(
                OpportunityModel.organization_id == org,
                OpportunityModel.contact_id.in_(family(self.session, org, contact)),
            )
        )
        total = int(
            self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        )
        rows = self.session.scalars(
            query.order_by(
                func.coalesce(
                    OpportunityActivityModel.resolved_at,
                    OpportunityActivityModel.due_at,
                ).desc(),
                OpportunityActivityModel.id,
            )
            .offset((page - 1) * 20)
            .limit(20)
        ).all()
        content = has_permission(actor, "crm.opportunities.read_content")
        return CustomerActionList(
            items=[
                CustomerAction(
                    id=r.id,
                    opportunity_id=r.opportunity_id,
                    description=(
                        self.commercial.cipher.decrypt(r.description_ciphertext)
                        if content
                        else "Contenido restringido"
                    ),
                    due_at=aware(r.due_at),
                    status=r.status,
                    resolved_at=aware(r.resolved_at) if r.resolved_at else None,
                    assigned_user_id=r.assigned_user_id,
                )
                for r in rows
            ],
            total=total,
            page=page,
            has_next=page * 20 < total,
        )
