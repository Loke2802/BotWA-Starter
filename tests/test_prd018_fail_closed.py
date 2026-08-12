import ast
import inspect
from pathlib import Path

import pytest
from app.application.analytics.service import AnalyticsQueryService
from app.application.audit.service import AuditQueryService
from app.application.automation_management.service import ManagedAutomationService
from app.application.bots.service import BotService
from app.application.business_calendar.service import BusinessCalendarService
from app.application.human_handoff.service import HumanHandoffService
from app.application.integration_management.service import IntegrationManagementService
from app.application.knowledge_management.service import KnowledgeManagementService
from app.application.organizations.service import OrganizationService
from app.application.users.service import UserService
from app.application.whatsapp_configuration.service import WhatsAppConfigurationService

ROOT = Path(__file__).parents[1]
PLAN_GATED_SERVICES = (
    AnalyticsQueryService,
    AuditQueryService,
    BotService,
    UserService,
    ManagedAutomationService,
    IntegrationManagementService,
    BusinessCalendarService,
    KnowledgeManagementService,
    WhatsAppConfigurationService,
    HumanHandoffService,
)


@pytest.mark.parametrize("service_type", PLAN_GATED_SERVICES)
def test_plan_gated_constructor_requires_enforcement(
    service_type: type[object],
) -> None:
    parameter = inspect.signature(service_type).parameters["plan_enforcement"]
    assert parameter.default is inspect.Parameter.empty
    assert "None" not in str(parameter.annotation)


def test_organization_bootstrap_requires_plan_repository() -> None:
    parameter = inspect.signature(OrganizationService).parameters["plan_repository"]
    assert parameter.default is inspect.Parameter.empty
    assert "None" not in str(parameter.annotation)


def test_no_application_service_contains_optional_enforcement_bypass() -> None:
    for service_type in PLAN_GATED_SERVICES:
        source = inspect.getsource(service_type)
        assert "PlanEnforcementService | None" not in source
        assert "plan_enforcement is not None" not in source


def test_every_production_service_construction_satisfies_required_contract() -> None:
    signatures = {
        service_type.__name__: inspect.signature(service_type)
        for service_type in (*PLAN_GATED_SERVICES, OrganizationService)
    }
    found = {name: 0 for name in signatures}
    for path in (ROOT / "app").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr if isinstance(node.func, ast.Attribute) else None
            )
            if name not in signatures:
                continue
            assert not any(isinstance(argument, ast.Starred) for argument in node.args)
            assert all(keyword.arg is not None for keyword in node.keywords)
            signatures[name].bind(
                *([object()] * len(node.args)),
                **{keyword.arg: object() for keyword in node.keywords if keyword.arg},
            )
            found[name] += 1
    assert all(count > 0 for count in found.values()), found


@pytest.mark.parametrize(
    "relative_path",
    (
        "app/api/dependencies.py",
        "app/api/analytics_dependencies.py",
        "app/api/audit_dependencies.py",
        "app/api/automation_management_dependencies.py",
        "app/api/business_calendar_dependencies.py",
        "app/api/dashboard_dependencies.py",
        "app/api/human_handoff_dependencies.py",
        "app/api/integration_management_dependencies.py",
        "app/api/knowledge_dependencies.py",
        "app/api/whatsapp_configuration_dependencies.py",
        "app/api/whatsapp_live_dependencies.py",
        "app/operations/automation_worker.py",
    ),
)
def test_production_composition_root_builds_session_bound_enforcement(
    relative_path: str,
) -> None:
    source = (ROOT / relative_path).read_text(encoding="utf-8")
    assert "PlanEnforcementService" in source
    assert "SqlAlchemyPlanRepository(session)" in source


def test_audit_write_path_remains_independent_from_plans() -> None:
    source = (ROOT / "app/application/audit/writer.py").read_text(encoding="utf-8")
    assert "PlanEnforcement" not in source
    assert "SqlAlchemyPlanRepository" not in source
