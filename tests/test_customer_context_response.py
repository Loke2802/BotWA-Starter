"""Authored context/review fixtures, not live model-quality evaluations."""

import json

import pytest
from app.application.generative_ai.response_context import build_context
from app.application.generative_ai.response_validation import (
    validate_draft,
)
from app.domain.generative_ai.contracts import (
    AdviserResult,
    AIConfig,
    Generation,
    ProviderError,
    Usage,
)
from app.domain.generative_ai.response_contracts import (
    ConversationalDraft,
    CustomerTurn,
)
from app.infrastructure.models.ai_generation import (
    AIAttemptModel,
    AIResponseCheckpointModel,
)
from app.infrastructure.models.whatsapp_message_transport import (
    OutboundMessageAttemptModel,
)
from app.operations.ai_consumer import dispatch_one
from pydantic import BaseModel
from sqlalchemy import select

from tests.test_conversational_response import segment
from tests.test_generative_ai import Runtime, runtime
from tests.test_knowledge_paraphrase import ParaphraseProvider, policy, prepare
from tests.test_whatsapp_live_processor_repository import cipher

__all__ = ["runtime"]

SOURCE = "El catálogo presenta servicios de forma ordenada."


def test_customer_situation_and_goal_do_not_create_provider_facts() -> None:
    result = AdviserResult(
        tone="understood",
        question_key=None,
        handoff_requested=False,
        recommendations=[],
        knowledge=[{"source_ref": "catalog", "quote": SOURCE}],
    )
    memory = {
        "negocio": {"value": "un taller", "message_ref": "earlier"},
        "objetivo": {"value": "mostrar mis servicios", "message_ref": "earlier"},
    }
    context = build_context(
        "customer-situation",
        result,
        AIConfig(),
        memory,
        {
            "catalog": {
                "content": SOURCE,
                "version": "v1",
                "response_expression": policy(SOURCE),
            }
        },
        customer_turn=CustomerTurn(
            message_ref="latest", text="Quiero reservas y pagos, ¿los incluye?"
        ),
    )
    assert context.business_facts[0].authorized_text == SOURCE
    assert len(context.authorized_claims) == 1
    assert context.validated_relationships == context.authorized_comparisons == []
    assert context.authorized_claims[0].need_refs == []
    assert {n.evidence_ref for n in context.customer_needs} == {"earlier"}
    assert "reservas" not in json.dumps(
        [f.model_dump() for f in context.business_facts]
    )
    draft = ConversationalDraft.model_validate(
        {
            "schema_version": "1",
            "context_id": context.context_id,
            "segments": [
                segment(
                    id="private_draft_identifier",
                    kind="recommendation",
                    text="Para mostrar los servicios de tu taller, el catálogo "
                    "permite presentarlos de forma ordenada.",
                    claim_refs=["claim_knowledge_0"],
                    need_refs=["need_negocio", "need_objetivo"],
                )
            ],
        }
    )
    expanded = validate_draft(context, draft, 3500)
    assert "taller" in expanded and "reservas" not in expanded
    forged = draft.model_copy(
        update={
            "segments": [
                draft.segments[0].model_copy(
                    update={"need_refs": ["other_customer_need"]}
                )
            ]
        }
    )
    with pytest.raises(ProviderError, match="INVALID_REFERENCE"):
        validate_draft(context, forged, 3500)


class CustomerContextProvider(ParaphraseProvider):
    """Scripted rendering/review, to exercise existing durable controls only."""

    async def generate(
        self, *, stage: str, context: str, schema: type[BaseModel]
    ) -> Generation:
        if stage != "conversational_render":
            return await super().generate(stage=stage, context=context, schema=schema)
        data = json.loads(context)
        self.stages.append(stage)
        self.calls.append(data)
        text = (
            "Por lo que cuentas de tu sobrino, este recurso permite explorar "
            "historias jugando."
        )
        if self.reject:
            text += " También podría enseñarle a leer."
        draft = {
            "schema_version": "1",
            "context_id": data["context_id"],
            "segments": [
                segment(
                    id="private_draft_identifier",
                    kind="recommendation",
                    text=text,
                    claim_refs=[data["authorized_claims"][0]["id"]],
                )
            ],
        }
        return Generation(
            data=json.dumps(draft),
            usage=Usage(input_tokens=10, output_tokens=10, model="gpt-6-luna"),
        )


@pytest.mark.parametrize("reject", [False, True])
async def test_contextualized_draft_still_requires_review_and_delivers_once(
    runtime: Runtime, reject: bool
) -> None:
    prepare(runtime)
    provider = CustomerContextProvider()
    provider.reject = reject
    runtime.service.provider = provider
    await runtime.inbound()
    await runtime.service.run_once()
    await dispatch_one(runtime.service)
    await dispatch_one(runtime.service)
    with runtime.sessions() as session:
        cp = session.scalars(select(AIResponseCheckpointModel)).one()
        assert cp.outcome == ("fallback" if reject else "approved")
        assert cp.reason_code == ("REVIEW_UNSUPPORTED_CLAIM" if reject else None)
        out = session.scalars(select(OutboundMessageAttemptModel)).one()
        reply = cipher().decrypt(out.message_ciphertext)
        assert "enseñarle a leer" not in reply
        assert ("tu sobrino" in reply) is not reject
        assert out.attempt_count == 1
        attempts = list(session.scalars(select(AIAttemptModel)))
        assert len(attempts) == 4
        assert {
            a.prompt_version for a in attempts if a.stage == "conversational_render"
        } == {"luri-response-7"}
        assert {a.prompt_version for a in attempts if a.stage == "semantic_review"} == {
            "luri-review-5"
        }
        summary = next(a for a in attempts if a.stage == "semantic_review").parameters[
            "review_summary"
        ]
        assert isinstance(summary, dict)
        assert summary["rejected_segments"] == (
            [
                {
                    "position": 0,
                    "kind": "recommendation",
                    "reason_code": "UNSUPPORTED_CLAIM",
                }
            ]
            if reject
            else []
        )
        assert "private_draft_identifier" not in json.dumps(summary)
        assert "sobrino" not in json.dumps(summary)
    render = next(c for c in provider.calls if "authorized_claims" in c)
    review = next(c for c in provider.calls if "expanded_text" in c)
    assert render == review["context"]
    assert render["customer_turn"]["text"].startswith("Mi sobrino")
    assert "sobrino" not in json.dumps(render["business_facts"])
    assert provider.stages == [
        "discovery",
        "adviser",
        "conversational_render",
        "semantic_review",
    ]
