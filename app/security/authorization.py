from uuid import UUID

from app.domain.access.contracts import (
    ASSIGNABLE_ROLES_BY_ROLE,
    ROLE_PERMISSIONS,
    Permission,
    Role,
)
from app.domain.user.contracts import User


class AuthorizationError(ValueError):
    pass


def get_permissions(role: Role) -> frozenset[Permission]:
    return ROLE_PERMISSIONS[role]


def has_permission(user: User, permission: Permission) -> bool:
    return permission in get_permissions(user.role)


def is_platform_admin(user: User) -> bool:
    return user.role == "platform_admin"


def can_access_organization(user: User, organization_id: UUID) -> bool:
    return is_platform_admin(user) or user.organization_id == organization_id


def require_permission(user: User, permission: Permission) -> None:
    if user.status != "active" or not has_permission(user, permission):
        raise AuthorizationError("permission denied")


def require_organization_access(user: User, organization_id: UUID) -> None:
    if not can_access_organization(user, organization_id):
        raise AuthorizationError("permission denied")


def require_scoped_permission(
    user: User,
    permission: Permission,
    organization_id: UUID,
) -> None:
    require_permission(user, permission)
    require_organization_access(user, organization_id)


def can_assign_role(actor: User, target_role: Role) -> bool:
    return (
        has_permission(actor, "roles.assign")
        and target_role in ASSIGNABLE_ROLES_BY_ROLE[actor.role]
    )


def require_role_assignment(actor: User, target_role: Role) -> None:
    if not can_assign_role(actor, target_role):
        raise AuthorizationError("permission denied")
