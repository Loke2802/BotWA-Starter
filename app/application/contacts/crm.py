from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.application.audit.writer import append_user_audit
from app.application.contacts.identity import ContactIdentityHasher
from app.domain.contacts.crm_contracts import (
    CrmAssignee,
    CrmSummary,
    CustomerCreate,
    CustomerDetail,
    CustomerItem,
    CustomerList,
    CustomerUpdate,
)
from app.domain.user.contracts import User
from app.infrastructure.models.contact import ContactModel
from app.infrastructure.models.customer_profile import CustomerProfileModel
from app.infrastructure.models.user import UserModel
from app.infrastructure.repositories.audit_repository import SqlAlchemyAuditRepository
from app.security.authorization import has_permission, require_scoped_permission
from app.security.secret_cipher import SecretCipher
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


class CrmNotFound(ValueError):
    pass


class CrmConflict(ValueError):
    pass


class CrmService:
    def __init__(
        self, session: Session, cipher: SecretCipher, hasher: ContactIdentityHasher
    ) -> None:
        self.session = session
        self.cipher = cipher
        self.hasher = hasher

    def _query(self, org: UUID) -> Select[tuple[ContactModel, CustomerProfileModel]]:
        return (
            select(ContactModel, CustomerProfileModel)
            .outerjoin(
                CustomerProfileModel,
                (CustomerProfileModel.contact_id == ContactModel.id)
                & (
                    CustomerProfileModel.organization_id == ContactModel.organization_id
                ),
            )
            .where(ContactModel.organization_id == org)
        )

    def _item(
        self, contact: ContactModel, profile: CustomerProfileModel | None
    ) -> CustomerItem:
        return CustomerItem(
            id=contact.id,
            display_name=(
                self.cipher.decrypt(contact.display_name_ciphertext)
                if contact.display_name_ciphertext
                else None
            ),
            channel_type=contact.channel_type,
            status=contact.status,
            classification=profile.classification if profile else "lead",
            service_interest=profile.service_interest if profile else "undecided",
            assigned_user_id=profile.assigned_user_id if profile else None,
            next_follow_up_at=profile.next_follow_up_at if profile else None,
            version=profile.version if profile else 0,
            created_at=contact.created_at,
            updated_at=contact.updated_at,
        )

    def list_customers(
        self,
        org: UUID,
        actor: User,
        *,
        classification: str | None,
        status: str,
        due: bool,
        identifier: str | None,
        page: int,
        page_size: int,
    ) -> CustomerList:
        require_scoped_permission(actor, "contacts.read", org)
        query = self._query(org).where(ContactModel.status == status)
        if classification:
            query = query.where(
                func.coalesce(CustomerProfileModel.classification, "lead")
                == classification
            )
        if due:
            query = query.where(
                CustomerProfileModel.next_follow_up_at <= datetime.now(UTC)
            )
        if identifier:
            require_scoped_permission(actor, "contacts.read_sensitive", org)
            identity = self.hasher.identify(org, "whatsapp", identifier)
            query = query.where(
                ContactModel.channel_type == "whatsapp",
                ContactModel.external_identifier_hash
                == identity.external_identifier_hash,
            )
        total = (
            self.session.scalar(select(func.count()).select_from(query.subquery())) or 0
        )
        rows = self.session.execute(
            query.order_by(ContactModel.created_at.desc(), ContactModel.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return CustomerList(
            items=[self._item(c, p) for c, p in rows],
            total=total,
            page=page,
            page_size=page_size,
            has_next=page * page_size < total,
        )

    def summary(self, org: UUID, actor: User) -> CrmSummary:
        require_scoped_permission(actor, "contacts.read", org)
        query = self._query(org).where(ContactModel.status == "active")
        counts = {}
        for classification in ("lead", "customer", "inactive"):
            filtered = query.where(
                func.coalesce(CustomerProfileModel.classification, "lead")
                == classification
            )
            counts[classification] = (
                self.session.scalar(
                    select(func.count()).select_from(filtered.subquery())
                )
                or 0
            )
        due = (
            self.session.scalar(
                select(func.count()).select_from(
                    query.where(
                        CustomerProfileModel.next_follow_up_at <= datetime.now(UTC)
                    ).subquery()
                )
            )
            or 0
        )
        return CrmSummary(
            leads=counts["lead"],
            customers=counts["customer"],
            inactive=counts["inactive"],
            follow_ups_due=due,
            can_edit=has_permission(actor, "contacts.update"),
            can_create=has_permission(actor, "contacts.update")
            and has_permission(actor, "contacts.read_sensitive"),
            can_archive=has_permission(actor, "contacts.archive"),
        )

    def assignees(self, org: UUID, actor: User) -> list[CrmAssignee]:
        require_scoped_permission(actor, "contacts.read", org)
        users = self.session.scalars(
            select(UserModel)
            .where(UserModel.organization_id == org, UserModel.status == "active")
            .order_by(UserModel.first_name, UserModel.id)
        ).all()
        return [
            CrmAssignee(
                id=u.id,
                name=" ".join(filter(None, [u.first_name, u.last_name]))
                or "Miembro del equipo",
            )
            for u in users
        ]

    def detail(self, org: UUID, contact_id: UUID, actor: User) -> CustomerDetail:
        require_scoped_permission(actor, "contacts.read", org)
        row = self.session.execute(
            self._query(org).where(ContactModel.id == contact_id)
        ).first()
        if row is None:
            raise CrmNotFound()
        c, p = row
        sensitive = has_permission(actor, "contacts.read_sensitive")
        return CustomerDetail(
            **self._item(c, p).model_dump(),
            external_identifier=(
                self.cipher.decrypt(c.external_identifier_ciphertext)
                if sensitive
                else None
            ),
            notes=(
                self.cipher.decrypt(c.notes_ciphertext)
                if sensitive and c.notes_ciphertext
                else None
            ),
            can_edit=has_permission(actor, "contacts.update"),
            can_read_sensitive=sensitive,
        )

    def _validate_assignee(self, org: UUID, user_id: UUID | None) -> None:
        if (
            user_id is not None
            and self.session.scalar(
                select(UserModel.id).where(
                    UserModel.id == user_id,
                    UserModel.organization_id == org,
                    UserModel.status == "active",
                )
            )
            is None
        ):
            raise ValueError(
                "El responsable debe pertenecer al equipo activo de esta empresa."
            )

    def create(self, org: UUID, actor: User, data: CustomerCreate) -> CustomerDetail:
        require_scoped_permission(actor, "contacts.update", org)
        require_scoped_permission(actor, "contacts.read_sensitive", org)
        self._validate_assignee(org, data.assigned_user_id)
        identity = self.hasher.identify(org, "whatsapp", data.whatsapp)
        existing = self.session.scalar(
            select(ContactModel.id).where(
                ContactModel.organization_id == org,
                ContactModel.channel_type == "whatsapp",
                ContactModel.external_identifier_hash
                == identity.external_identifier_hash,
            )
        )
        if existing:
            raise CrmConflict(
                "Este WhatsApp ya está registrado. Búscalo también en Archivados."
            )
        contact = ContactModel(
            id=uuid4(),
            organization_id=org,
            channel_type="whatsapp",
            external_identifier_hash=identity.external_identifier_hash,
            external_identifier_ciphertext=self.cipher.encrypt(
                identity.normalized_identifier
            ),
            display_name_ciphertext=self.cipher.encrypt(data.display_name),
            notes_ciphertext=self.cipher.encrypt(data.notes) if data.notes else None,
            created_by_user_id=actor.id,
            updated_by_user_id=actor.id,
        )
        self.session.add(contact)
        try:
            self.session.flush()
            self.session.add(
                CustomerProfileModel(
                    contact_id=contact.id,
                    organization_id=org,
                    classification=data.classification,
                    service_interest=data.service_interest,
                    assigned_user_id=data.assigned_user_id,
                    next_follow_up_at=data.next_follow_up_at,
                )
            )
            self._audit(org, actor, contact.id)
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise CrmConflict(
                "No se guardó el contacto. Puede haberse registrado al mismo tiempo; "
                "actualiza la lista."
            ) from exc
        return self.detail(org, contact.id, actor)

    def update(
        self, org: UUID, contact_id: UUID, actor: User, data: CustomerUpdate
    ) -> CustomerDetail:
        require_scoped_permission(actor, "contacts.update", org)
        if data.notes is not None:
            require_scoped_permission(actor, "contacts.read_sensitive", org)
        self._validate_assignee(org, data.assigned_user_id)
        # Serialize creation/update of the optional profile on the existing contact.
        contact = self.session.scalar(
            select(ContactModel)
            .where(ContactModel.id == contact_id, ContactModel.organization_id == org)
            .with_for_update()
        )
        if contact is None:
            raise CrmNotFound()
        profile = self.session.scalar(
            select(CustomerProfileModel).where(
                CustomerProfileModel.contact_id == contact_id,
                CustomerProfileModel.organization_id == org,
            )
        )
        if (profile.version if profile else 0) != data.version:
            raise CrmConflict(
                "Otra persona actualizó esta ficha. "
                "Cierra y vuelve a abrirla antes de guardar."
            )
        if profile is None:
            profile = CustomerProfileModel(
                contact_id=contact_id, organization_id=org, version=0
            )
            self.session.add(profile)
        profile.classification = data.classification
        profile.service_interest = data.service_interest
        profile.assigned_user_id = data.assigned_user_id
        profile.next_follow_up_at = data.next_follow_up_at
        profile.version += 1
        profile.updated_at = datetime.now(UTC)
        contact.display_name_ciphertext = self.cipher.encrypt(data.display_name)
        if data.notes is not None:
            contact.notes_ciphertext = self.cipher.encrypt(data.notes)
        contact.updated_at = datetime.now(UTC)
        contact.updated_by_user_id = actor.id
        self._audit(org, actor, contact_id)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise CrmConflict(
                "No se pudo guardar la ficha. Actualiza e inténtalo nuevamente."
            ) from exc
        return self.detail(org, contact_id, actor)

    def _audit(self, org: UUID, actor: User, contact_id: UUID) -> None:
        append_user_audit(
            SqlAlchemyAuditRepository(self.session),
            organization_id=org,
            actor=actor,
            action="contact.updated",
            resource_type="contact",
            resource_id=contact_id,
        )
