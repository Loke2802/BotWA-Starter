from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

Role = Literal[
    "platform_admin",
    "organization_owner",
    "organization_admin",
    "operator",
    "viewer",
]

Permission = Literal[
    "organizations.read",
    "organizations.update",
    "users.create",
    "users.read",
    "users.update",
    "users.deactivate",
    "roles.read",
    "roles.assign",
    "bots.create",
    "bots.read",
    "bots.update",
    "bots.activate",
    "bots.deactivate",
    "business_configuration.create",
    "business_configuration.read",
    "business_configuration.update",
    "platform.organizations.read",
    "platform.organizations.manage",
]

ALL_ROLES: tuple[Role, ...] = (
    "platform_admin",
    "organization_owner",
    "organization_admin",
    "operator",
    "viewer",
)

ALL_PERMISSIONS: tuple[Permission, ...] = (
    "organizations.read",
    "organizations.update",
    "users.create",
    "users.read",
    "users.update",
    "users.deactivate",
    "roles.read",
    "roles.assign",
    "bots.create",
    "bots.read",
    "bots.update",
    "bots.activate",
    "bots.deactivate",
    "business_configuration.create",
    "business_configuration.read",
    "business_configuration.update",
    "platform.organizations.read",
    "platform.organizations.manage",
)

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    "platform_admin": frozenset(ALL_PERMISSIONS),
    "organization_owner": frozenset(
        (
            "organizations.read",
            "organizations.update",
            "users.create",
            "users.read",
            "users.update",
            "users.deactivate",
            "roles.read",
            "roles.assign",
            "bots.create",
            "bots.read",
            "bots.update",
            "bots.activate",
            "bots.deactivate",
            "business_configuration.create",
            "business_configuration.read",
            "business_configuration.update",
        )
    ),
    "organization_admin": frozenset(
        (
            "organizations.read",
            "users.create",
            "users.read",
            "users.update",
            "users.deactivate",
            "roles.read",
            "roles.assign",
            "bots.create",
            "bots.read",
            "bots.update",
            "bots.activate",
            "bots.deactivate",
            "business_configuration.create",
            "business_configuration.read",
            "business_configuration.update",
        )
    ),
    "operator": frozenset(
        (
            "organizations.read",
            "users.read",
            "bots.read",
            "business_configuration.read",
        )
    ),
    "viewer": frozenset(
        (
            "organizations.read",
            "bots.read",
            "business_configuration.read",
        )
    ),
}

ASSIGNABLE_ROLES_BY_ROLE: dict[Role, frozenset[Role]] = {
    "platform_admin": frozenset(ALL_ROLES),
    "organization_owner": frozenset(
        (
            "organization_owner",
            "organization_admin",
            "operator",
            "viewer",
        )
    ),
    "organization_admin": frozenset(("organization_admin", "operator", "viewer")),
    "operator": frozenset(),
    "viewer": frozenset(),
}


class RoleAssignmentRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Role


class RoleResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Role
    permissions: list[Permission]
    assignable_roles: list[Role]


class RoleListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    roles: list[RoleResponse]
    total: int


class EffectivePermissionsResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: UUID
    organization_id: UUID
    role: Role
    permissions: list[Permission]
    can_access_all_organizations: bool
