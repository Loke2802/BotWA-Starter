from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.application.audit.writer import append_non_user_audit, append_user_audit
from app.application.plans.service import PlanEnforcementService
from app.domain.access.contracts import Role
from app.domain.audit.contracts import (
    ChangedFieldsMetadata,
    CredentialRotationMetadata,
    RoleAssignmentMetadata,
    StatusTransitionMetadata,
)
from app.domain.audit.ports import AuditWriter
from app.domain.organization.contracts import Organization
from app.domain.user.contracts import User, UserCreate, UserUpdate
from app.infrastructure.models.organization import OrganizationModel
from app.infrastructure.models.user import UserModel
from app.infrastructure.repositories.organization_repository import (
    OrganizationRepository,
)
from app.infrastructure.repositories.user_repository import UserRepository
from app.security.authorization import (
    AuthorizationError,
    can_access_organization,
    require_permission,
    require_role_assignment,
    require_scoped_permission,
)
from app.security.passwords import PasswordService


class UserNotFoundError(ValueError):
    pass


class UserConflictError(ValueError):
    pass


class OrganizationInactiveError(ValueError):
    pass


class UserAuthenticationRequiredError(ValueError):
    pass


class UserForbiddenError(ValueError):
    pass


class LastOwnerProtectionError(ValueError):
    pass


class UserService:
    def __init__(
        self,
        repository: UserRepository,
        organization_repository: OrganizationRepository,
        password_service: PasswordService,
        session: Session,
        audit_writer: AuditWriter,
        plan_enforcement: PlanEnforcementService,
    ) -> None:
        self._repository = repository
        self._organization_repository = organization_repository
        self._password_service = password_service
        self._session = session
        self._audit_writer = audit_writer
        self._plan_enforcement = plan_enforcement

    def create(self, request: UserCreate, actor: User | None = None) -> User:
        organization = self._organization_repository.get_for_update(
            request.organization_id
        )
        if organization is None:
            raise UserNotFoundError("organization not found")
        if organization.status != "active":
            raise OrganizationInactiveError("organization is inactive")

        user_count = self._repository.count_by_organization(request.organization_id)
        role: Role = (
            "organization_owner" if user_count == 0 else request.role or "viewer"
        )
        if user_count > 0:
            if actor is None:
                raise UserAuthenticationRequiredError("authentication required")
            try:
                require_scoped_permission(
                    actor,
                    "users.create",
                    request.organization_id,
                )
                if role != "viewer":
                    require_role_assignment(actor, role)
            except AuthorizationError as exc:
                raise UserForbiddenError("permission denied") from exc

        self._plan_enforcement.require_consuming_action(
            request.organization_id, limit="max_active_users"
        )

        if self._repository.find_by_email(request.email) is not None:
            raise UserConflictError("user email already exists")

        now = datetime.now(UTC)
        model = UserModel(
            id=uuid4(),
            organization_id=request.organization_id,
            email=request.email,
            password_hash=self._password_service.hash(request.password),
            first_name=request.first_name,
            last_name=request.last_name,
            role=role,
            status="active",
            auth_version=1,
            created_at=now,
            updated_at=now,
        )
        self._repository.add(model)
        if actor is None:
            append_non_user_audit(
                self._audit_writer,
                organization_id=model.organization_id,
                actor_type="system",
                action="user.created",
                resource_type="user",
                resource_id=model.id,
                occurred_at=now,
            )
        else:
            append_user_audit(
                self._audit_writer,
                organization_id=model.organization_id,
                actor=actor,
                action="user.created",
                resource_type="user",
                resource_id=model.id,
                occurred_at=now,
            )
        self._commit()
        self._session.refresh(model)
        return self._to_domain(model)

    def get(self, user_id: UUID, actor: User) -> User:
        try:
            require_permission(actor, "users.read")
        except AuthorizationError as exc:
            raise UserForbiddenError("permission denied") from exc
        model = self._get_visible_model(user_id, actor)
        return self._to_domain(model)

    def list(self, actor: User) -> list[User]:
        try:
            require_permission(actor, "users.read")
        except AuthorizationError as exc:
            raise UserForbiddenError("permission denied") from exc
        models = [
            model
            for model in self._repository.list_ordered()
            if actor.role == "platform_admin"
            or model.organization_id == actor.organization_id
        ]
        return [self._to_domain(model) for model in models]

    def update(self, user_id: UUID, request: UserUpdate, actor: User) -> User:
        try:
            require_permission(actor, "users.update")
        except AuthorizationError as exc:
            raise UserForbiddenError("permission denied") from exc
        if request.organization_id is not None:
            raise UserForbiddenError("organization_id cannot be changed")

        model = self._get_visible_model(user_id, actor)
        changed_fields = tuple(
            field
            for field in ("first_name", "last_name")
            if field in request.model_fields_set
        )
        if "first_name" in request.model_fields_set:
            model.first_name = request.first_name
        if "last_name" in request.model_fields_set:
            model.last_name = request.last_name
        model.updated_at = datetime.now(UTC)
        self._repository.update(model)
        if changed_fields:
            append_user_audit(
                self._audit_writer,
                organization_id=model.organization_id,
                actor=actor,
                action="user.updated",
                resource_type="user",
                resource_id=model.id,
                metadata=ChangedFieldsMetadata(changed_fields=changed_fields),
                occurred_at=model.updated_at,
            )
        self._commit()
        self._session.refresh(model)
        return self._to_domain(model)

    def deactivate(self, user_id: UUID, actor: User) -> User:
        try:
            require_permission(actor, "users.deactivate")
        except AuthorizationError as exc:
            raise UserForbiddenError("permission denied") from exc
        model = self._get_visible_model(user_id, actor)
        self._lock_organization(model.organization_id)
        if self._is_last_active_owner(model):
            raise LastOwnerProtectionError("last organization owner cannot be changed")
        if model.status != "inactive":
            now = datetime.now(UTC)
            model.status = "inactive"
            model.deactivated_at = now
            model.updated_at = now
            model.auth_version += 1
            self._repository.update(model)
            append_user_audit(
                self._audit_writer,
                organization_id=model.organization_id,
                actor=actor,
                action="user.deactivated",
                resource_type="user",
                resource_id=model.id,
                metadata=StatusTransitionMetadata(
                    from_status="active", to_status="inactive"
                ),
                occurred_at=now,
            )
            self._commit()
            self._session.refresh(model)
        return self._to_domain(model)

    def assign_role(self, user_id: UUID, role: Role, actor: User) -> User:
        try:
            require_permission(actor, "roles.assign")
            require_role_assignment(actor, role)
        except AuthorizationError as exc:
            raise UserForbiddenError("permission denied") from exc

        model = self._get_visible_model(user_id, actor)
        self._lock_organization(model.organization_id)
        if actor.id == user_id and role != actor.role:
            raise UserForbiddenError("users cannot change their own role")
        if self._is_last_active_owner(model) and role != "organization_owner":
            raise LastOwnerProtectionError("last organization owner cannot be changed")

        previous_role = model.role
        model.role = role
        model.updated_at = datetime.now(UTC)
        self._repository.update(model)
        if previous_role != role:
            append_user_audit(
                self._audit_writer,
                organization_id=model.organization_id,
                actor=actor,
                action="user.role_changed",
                resource_type="user",
                resource_id=model.id,
                metadata=RoleAssignmentMetadata(from_role=previous_role, to_role=role),
                occurred_at=model.updated_at,
            )
        self._commit()
        self._session.refresh(model)
        return self._to_domain(model)

    def get_model(self, user_id: UUID) -> UserModel | None:
        return self._repository.get(user_id)

    def find_by_email(self, email: str) -> UserModel | None:
        return self._repository.find_by_email(email)

    def verify_password(self, password: str, password_hash: str) -> bool:
        return self._password_service.verify(password, password_hash)

    def verify_dummy_password(self, password: str) -> None:
        self._password_service.verify_dummy(password)

    def organization_is_active(self, organization_id: UUID) -> bool:
        organization = self._organization_repository.get(organization_id)
        return organization is not None and organization.status == "active"

    def record_login(self, model: UserModel) -> User:
        model.last_login_at = datetime.now(UTC)
        model.updated_at = model.last_login_at
        self._repository.update(model)
        self._session.commit()
        self._session.refresh(model)
        return self._to_domain(model)

    def change_password(
        self,
        user_id: UUID,
        current_password: str,
        new_password: str,
        actor: User | None = None,
    ) -> User:
        model = self._repository.get(user_id)
        if model is None:
            raise UserNotFoundError("user not found")
        if not self._password_service.verify(current_password, model.password_hash):
            raise UserAuthenticationRequiredError("invalid credentials")

        model.password_hash = self._password_service.hash(new_password)
        model.auth_version += 1
        model.updated_at = datetime.now(UTC)
        self._repository.update(model)
        effective_actor = actor
        if effective_actor is None:
            effective_actor = self._to_domain(model)
        append_user_audit(
            self._audit_writer,
            organization_id=model.organization_id,
            actor=effective_actor,
            action="user.password_changed",
            resource_type="user",
            resource_id=model.id,
            metadata=CredentialRotationMetadata(),
            occurred_at=model.updated_at,
        )
        self._commit()
        self._session.refresh(model)
        return self._to_domain(model)

    def _commit(self) -> None:
        try:
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise UserConflictError("user persistence failed") from exc

    def _get_visible_model(self, user_id: UUID, actor: User) -> UserModel:
        model = self._repository.get(user_id)
        if model is None:
            raise UserNotFoundError("user not found")
        if not can_access_organization(actor, model.organization_id):
            raise UserForbiddenError("user belongs to another organization")
        return model

    @staticmethod
    def _to_domain(model: UserModel) -> User:
        return User(
            id=model.id,
            organization_id=model.organization_id,
            email=model.email,
            first_name=model.first_name,
            last_name=model.last_name,
            role=model.role,
            status=model.status,
            created_at=model.created_at,
            updated_at=model.updated_at,
            last_login_at=model.last_login_at,
            deactivated_at=model.deactivated_at,
        )

    def _is_last_active_owner(self, model: UserModel) -> bool:
        if model.status != "active" or model.role != "organization_owner":
            return False
        return (
            self._repository.count_active_owners_by_organization(model.organization_id)
            <= 1
        )

    def _lock_organization(self, organization_id: UUID) -> None:
        if self._organization_repository.get_for_update(organization_id) is None:
            raise UserNotFoundError("organization not found")

    @staticmethod
    def _organization_to_domain(model: OrganizationModel) -> Organization:
        return Organization(
            id=model.id,
            name=model.name,
            slug=model.slug,
            status=model.status,
            created_at=model.created_at,
            updated_at=model.updated_at,
            deactivated_at=model.deactivated_at,
        )
