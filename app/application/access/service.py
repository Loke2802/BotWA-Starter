from app.domain.access.contracts import (
    ALL_ROLES,
    ASSIGNABLE_ROLES_BY_ROLE,
    ROLE_PERMISSIONS,
    EffectivePermissionsResponse,
    Permission,
    RoleListResponse,
    RoleResponse,
)
from app.domain.user.contracts import User
from app.security.authorization import is_platform_admin


class AccessService:
    def list_roles(self) -> RoleListResponse:
        roles = [
            RoleResponse(
                role=role,
                permissions=sorted(ROLE_PERMISSIONS[role]),
                assignable_roles=sorted(ASSIGNABLE_ROLES_BY_ROLE[role]),
            )
            for role in ALL_ROLES
        ]
        return RoleListResponse(roles=roles, total=len(roles))

    def effective_permissions(self, user: User) -> EffectivePermissionsResponse:
        permissions: list[Permission] = sorted(ROLE_PERMISSIONS[user.role])
        return EffectivePermissionsResponse(
            user_id=user.id,
            organization_id=user.organization_id,
            role=user.role,
            permissions=permissions,
            can_access_all_organizations=is_platform_admin(user),
        )
