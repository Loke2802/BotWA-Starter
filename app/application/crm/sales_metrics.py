"""Historical closure events and clipped time in stage, without editing history."""

from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from itertools import groupby
from uuid import UUID

from sqlalchemy import select

from app.application.crm.presentation import aware
from app.application.crm.service import OpportunityService
from app.domain.crm.contracts import OpportunityRecord
from app.domain.crm.growth_contracts import ClosingMetric, SalesMetrics, StageDuration
from app.domain.user.contracts import User
from app.infrastructure.models.crm_opportunity import OpportunityHistoryModel
from app.security.authorization import has_permission


class SalesMetricsService:
    def __init__(self, commercial: OpportunityService) -> None:
        self.commercial = commercial

    def report(
        self,
        org: UUID,
        actor: User,
        start: datetime | None,
        end: datetime | None,
        assigned: UUID | None,
    ) -> SalesMetrics:
        self.commercial._read(org, actor)
        organization = self.commercial.repository.organization(org)
        now = datetime.now(UTC)
        if any(d is not None and d.utcoffset() is None for d in (start, end)) or (
            start and end and start >= end
        ):
            raise ValueError("Use an aware half-open date range")
        upper = min(end or now, now)
        lower = start or datetime.min.replace(tzinfo=UTC)
        content = has_permission(actor, "crm.opportunities.read_content")
        query = (
            select(OpportunityHistoryModel)
            .where(
                OpportunityHistoryModel.organization_id == org,
                OpportunityHistoryModel.occurred_at <= upper,
            )
            .order_by(
                OpportunityHistoryModel.opportunity_id, OpportunityHistoryModel.version
            )
            .execution_options(yield_per=100)
        )
        counts: dict[tuple[UUID, str | None], list[int]] = defaultdict(lambda: [0, 0])
        amounts: dict[tuple[UUID, str | None], Decimal] = defaultdict(
            lambda: Decimal(0)
        )
        hours: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
        visits: dict[str, set[UUID]] = defaultdict(set)
        for ident, versions in groupby(
            self.commercial.session.scalars(query), key=lambda r: r.opportunity_id
        ):
            states = [
                (
                    aware(r.occurred_at),
                    OpportunityRecord.model_validate_json(
                        self.commercial.cipher.decrypt(r.snapshot_ciphertext)
                    ),
                )
                for r in versions
            ]
            previous_kind = "open"
            for i, (at, state) in enumerate(states):
                if (
                    state.stage_kind != previous_kind
                    and state.stage_kind in {"won", "lost"}
                    and lower <= at < upper
                    and (assigned is None or state.assigned_user_id == assigned)
                ):
                    key = (state.assigned_user_id, state.currency if content else None)
                    counts[key][0 if state.stage_kind == "won" else 1] += 1
                    if (
                        content
                        and state.stage_kind == "won"
                        and state.amount is not None
                    ):
                        amounts[key] += state.amount
                previous_kind = state.stage_kind
                stop = states[i + 1][0] if i + 1 < len(states) else upper
                seconds = (min(stop, upper) - max(at, lower)).total_seconds()
                if (
                    seconds > 0
                    and state.stage_kind == "open"
                    and (assigned is None or state.assigned_user_id == assigned)
                ):
                    hours[state.stage_code] += Decimal(str(seconds)) / Decimal(3600)
                    visits[state.stage_code].add(ident)
        return SalesMetrics(
            date_from=start,
            date_to=end or now,
            as_of=now,
            timezone=str(organization.settings.get("timezone") or "UTC"),
            can_read_amounts=content,
            closings=[
                ClosingMetric(
                    assigned_user_id=owner,
                    currency=currency,
                    won=value[0],
                    lost=value[1],
                    conversion_percent=(
                        Decimal(value[0]) * 100 / Decimal(sum(value))
                    ).quantize(Decimal("0.01")),
                    won_amount=(
                        amounts[(owner, currency)] if content and currency else None
                    ),
                )
                for (owner, currency), value in sorted(
                    counts.items(), key=lambda v: (str(v[0][0]), v[0][1] or "")
                )
            ],
            durations=[
                StageDuration(
                    stage_code=code,
                    opportunity_count=len(visits[code]),
                    total_hours=total.quantize(Decimal("0.01")),
                    average_hours=(total / len(visits[code])).quantize(Decimal("0.01")),
                )
                for code, total in sorted(hours.items())
            ],
            explanation=(
                "Eventos de cierre ocurridos en el periodo, con responsable e "
                "importe en el momento del cierre. Conversión = ganadas / "
                "(ganadas + perdidas); una reapertura puede originar otro "
                "cierre. Tiempo en etapas abiertas recortado al periodo, "
                "hasta la hora de referencia, incluido el tiempo aún abierto. "
                "Importes separados por moneda; solo historial registrado."
            ),
        )
