"""Reviewed consolidation; source identities, notes and immutable histories survive."""

import hashlib
import hmac
import json
import re
from collections import defaultdict
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import delete, select, update

from app.application.audit.writer import append_user_audit
from app.application.crm.service import OpportunityService
from app.domain.crm.contracts import CrmConflict
from app.domain.crm.growth_contracts import (
    DuplicateCandidate,
    DuplicateList,
    MergeContact,
    MergeInput,
    MergePreview,
    MergeResult,
)
from app.domain.user.contracts import User
from app.infrastructure.models.contact import ContactModel
from app.infrastructure.models.conversation import ConversationModel
from app.infrastructure.models.crm_contact_merge import ContactMergeModel
from app.infrastructure.models.crm_customer_activity import CrmCustomerActivityModel
from app.infrastructure.models.crm_opportunity import (
    OpportunityConversationModel,
    OpportunityModel,
)
from app.infrastructure.models.customer_profile import CustomerProfileModel
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.infrastructure.repositories.crm_identity import canonical, family
from app.security.authorization import require_scoped_permission


class DuplicateService:
    def __init__(self, commercial: OpportunityService) -> None:
        self.commercial, self.session = commercial, commercial.session

    def _access(self, org: UUID, actor: User) -> None:
        self.commercial._write(org, actor)
        for permission in (
            "contacts.read_sensitive",
            "contacts.update",
            "contacts.archive",
        ):
            require_scoped_permission(actor, permission, org)
        self.commercial.repository.organization(org)

    def candidates(self, org: UUID, actor: User, page: int) -> DuplicateList:
        self._access(org, actor)
        rows = self.session.scalars(
            select(ContactModel)
            .where(
                ContactModel.organization_id == org,
                ContactModel.status == "active",
                ContactModel.id.not_in(
                    select(ContactMergeModel.source_id).where(
                        ContactMergeModel.organization_id == org
                    )
                ),
            )
            .order_by(ContactModel.created_at, ContactModel.id)
            .limit(2001)
        ).all()
        limited = len(rows) > 2000
        rows = rows[:2000]
        cipher = self.commercial.cipher
        groups: dict[tuple[str, str], list[ContactModel]] = defaultdict(list)
        names = {}
        for row in rows:
            name = (
                cipher.decrypt(row.display_name_ciphertext)
                if row.display_name_ciphertext
                else "Sin nombre"
            )
            names[row.id] = name
            values = (
                [("nombre", " ".join(name.casefold().split()))]
                if row.display_name_ciphertext and len(name.strip()) >= 3
                else []
            )
            identity = cipher.decrypt(row.external_identifier_ciphertext)
            if row.channel_type in {"whatsapp", "phone", "sms"}:
                phone = re.sub(r"\D", "", identity)
                if len(phone) >= 8:
                    values.append(("teléfono", phone))
            if row.channel_type == "email":
                values.append(("correo", identity.strip().casefold()))
            if row.registration_ciphertext:
                registration = json.loads(cipher.decrypt(row.registration_ciphertext))
                if isinstance(registration, dict):
                    for key in ("email", "correo"):
                        value = registration.get(key)
                        if isinstance(value, str) and "@" in value:
                            values.append(("correo", value.strip().casefold()))
            for kind, value in set(values):
                groups[(kind, hashlib.sha256(value.encode()).hexdigest())].append(row)
        pairs: dict[tuple[UUID, UUID], list[str]] = defaultdict(list)
        for (reason, _), members in groups.items():
            for row in members[1:]:
                pairs[(row.id, members[0].id)].append(reason)
        items = [
            DuplicateCandidate(
                source_id=a,
                target_id=b,
                source_name=names[a],
                target_name=names[b],
                reasons=sorted(reasons),
            )
            for (a, b), reasons in pairs.items()
        ]
        return DuplicateList(
            items=items[(page - 1) * 20 : page * 20],
            page=page,
            has_next=page * 20 < len(items),
            scanned=len(rows),
            scan_limited=limited,
        )

    def _state(self, org: UUID, contact: UUID) -> tuple[MergeContact, str]:
        row = self.commercial.repository.contact(org, contact)
        profile = self.session.get(CustomerProfileModel, contact)
        ids = family(self.session, org, contact)
        cipher = self.commercial.cipher
        related = {}
        for model in (OpportunityModel, ConversationModel, CrmCustomerActivityModel):
            related[model.__tablename__] = [
                str(
                    cast(
                        OpportunityModel | ConversationModel | CrmCustomerActivityModel,
                        r,
                    ).id
                )
                + ":"
                + str(getattr(r, "version", getattr(r, "updated_at", "")))
                for r in self.session.scalars(
                    select(model)
                    .where(model.organization_id == org, model.contact_id.in_(ids))
                    .order_by(model.id)
                )
            ]
        profile_data = (
            {
                "classification": profile.classification,
                "service_interest": profile.service_interest,
                "assigned_user_id": (
                    str(profile.assigned_user_id) if profile.assigned_user_id else None
                ),
                "version": profile.version,
                "next_follow_up_at": (
                    str(profile.next_follow_up_at)
                    if profile.next_follow_up_at
                    else None
                ),
            }
            if profile
            else {}
        )
        detail = MergeContact(
            id=contact,
            name=(
                cipher.decrypt(row.display_name_ciphertext)
                if row.display_name_ciphertext
                else "Sin nombre"
            ),
            channel=row.channel_type,
            identifier=cipher.decrypt(row.external_identifier_ciphertext),
            notes=(
                cipher.decrypt(row.notes_ciphertext) if row.notes_ciphertext else None
            ),
            profile=profile_data,
            opportunities=len(related["crm_opportunity"]),
            conversations=len(related["conversation"]),
            activities=len(related["crm_customer_activity"]),
        )
        state = json.dumps(
            {
                "contact": {
                    c.name: str(getattr(row, c.name)) for c in row.__table__.columns
                },
                "detail": detail.model_dump(mode="json"),
                "related": related,
            },
            sort_keys=True,
        )
        return detail, state

    def preview(
        self, org: UUID, actor: User, source: UUID, target: UUID
    ) -> MergePreview:
        self._access(org, actor)
        if (
            source == target
            or canonical(self.session, org, source) != source
            or canonical(self.session, org, target) != target
        ):
            raise CrmConflict("Elige dos clientes principales distintos.")
        for contact in (source, target):
            if self.commercial.repository.contact(org, contact).status != "active":
                raise CrmConflict("Revisa dos clientes activos.")
        a, sa = self._state(org, source)
        b, sb = self._state(org, target)
        token = hmac.new(
            self.commercial.digest_key.encode(),
            (str(org) + sa + sb).encode(),
            hashlib.sha256,
        ).hexdigest()
        return MergePreview(
            source=a,
            target=b,
            token=token,
            explanation=(
                "El cliente principal conserva su ficha y sus notas. Se "
                "reúnen conversaciones, oportunidades y actividades; el "
                "origen queda archivado con su ficha original y la evidencia "
                "de unión. No se borran identidades ni historial."
            ),
        )

    def merge(self, org: UUID, actor: User, data: MergeInput) -> MergeResult:
        self._access(org, actor)
        try:
            self.commercial.repository.organization(org, lock=True)
            for contact in sorted((data.source_id, data.target_id), key=str):
                self.commercial.repository.contact(org, contact, lock=True)
            previous = self.session.get(ContactMergeModel, data.source_id)
            if previous:
                if (
                    previous.organization_id != org
                    or previous.target_id != data.target_id
                    or previous.review_token != data.review_token
                ):
                    raise CrmConflict(
                        "Este cliente ya fue unido; actualiza la revisión."
                    )
                return MergeResult(
                    source_id=data.source_id, target_id=data.target_id, replayed=True
                )
            review = self.preview(org, actor, data.source_id, data.target_id)
            if not hmac.compare_digest(review.token, data.review_token):
                raise CrmConflict(
                    "Los datos cambiaron; vuelve a revisar antes de unir."
                )
            ids = family(self.session, org, data.source_id)
            links = self.session.scalars(
                select(OpportunityConversationModel).where(
                    OpportunityConversationModel.organization_id == org,
                    OpportunityConversationModel.contact_id.in_(ids),
                )
            ).all()
            copies = [
                {c.name: getattr(row, c.name) for c in row.__table__.columns}
                for row in links
            ]
            journals = self.session.scalars(
                select(CrmCustomerActivityModel).where(
                    CrmCustomerActivityModel.organization_id == org,
                    CrmCustomerActivityModel.contact_id.in_(ids),
                )
            ).all()
            restore = [(r.id, r.opportunity_id) for r in journals if r.opportunity_id]
            # Remove only constrained links inside this transaction, then restore
            # their exact IDs, actors and dates after both parents move.
            self.session.execute(
                delete(OpportunityConversationModel).where(
                    OpportunityConversationModel.organization_id == org,
                    OpportunityConversationModel.contact_id.in_(ids),
                )
            )
            self.session.execute(
                update(CrmCustomerActivityModel)
                .where(
                    CrmCustomerActivityModel.organization_id == org,
                    CrmCustomerActivityModel.contact_id.in_(ids),
                )
                .values(opportunity_id=None)
            )
            for model in (
                OpportunityModel,
                ConversationModel,
                CrmCustomerActivityModel,
            ):
                command = (
                    update(model)
                    .where(model.organization_id == org, model.contact_id.in_(ids))
                    .values(contact_id=data.target_id)
                )
                if model is ConversationModel:
                    # Commercial attribution must not simulate a transport update.
                    command = command.values(updated_at=ConversationModel.updated_at)
                self.session.execute(command)
            for ident, op in restore:
                self.session.execute(
                    update(CrmCustomerActivityModel)
                    .where(
                        CrmCustomerActivityModel.organization_id == org,
                        CrmCustomerActivityModel.id == ident,
                    )
                    .values(opportunity_id=op)
                )
            for fields in copies:
                fields["contact_id"] = data.target_id
                self.session.add(OpportunityConversationModel(**fields))
            source = self.commercial.repository.contact(org, data.source_id)
            source.status = "archived"
            source.updated_by_user_id = actor.id
            source.updated_at = datetime.now(UTC)
            self.session.add(
                ContactMergeModel(
                    source_id=data.source_id,
                    target_id=data.target_id,
                    organization_id=org,
                    actor_user_id=actor.id,
                    review_token=data.review_token,
                    snapshot_ciphertext=self.commercial.cipher.encrypt(
                        review.model_dump_json()
                    ),
                )
            )
            append_user_audit(
                SqlAlchemyAuditRepository(self.session),
                organization_id=org,
                actor=actor,
                action="crm.customers_merged",
                resource_type="contact",
                resource_id=data.target_id,
            )
            self.session.commit()
            return MergeResult(
                source_id=data.source_id, target_id=data.target_id, replayed=False
            )
        except Exception:
            self.session.rollback()
            raise
