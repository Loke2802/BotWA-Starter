# I3 - Topic Detector Technical Plan

**Increment:** I3 - Topic Detector  
**Implementation status:** Implemented / Closed  
**Closure evidence:** `app/core/conversation/topic_detector.py`, `app/domain/conversation/topics.py`, `ConversationContext.topics`, `tests/test_topic_detector.py`, and full Core quality gates passing.  
**Historical note:** This document is retained as the original implementation plan.  
**Source of Truth:** Blueprint D-009 - Conversation Engine; ARCHITECTURE_RESOLUTION_REPORT.md; CONVERSATION_ENGINE_GAP_ANALYSIS.md  
**Architecture Resolution:** AR-002 - Topic belongs to Conversation Engine; Intent belongs to Business Brain  
**CTO constraint:** Do not modify Business Brain or IntentClassifier in I3

## 0. Executive Summary

I3 introduces the Topic Detector as a Conversation Engine component without changing Business Brain behavior.

The objective is to enrich `ConversationContext` with conversational topic information before the context is routed to the Business Brain. This prepares the codebase for AR-002 while preserving the current Vertical Slice.

I3 does not move greeting/farewell out of `IntentClassifier`. That separation is acknowledged as future AR-002 cleanup, but not part of this increment.

## 1. Topic Model

### 1.1 Contract: ConversationTopic

`ConversationTopic` is a Conversation Engine domain object.

Fields:

| Field | Type | Required | Description |
|---|---|---:|---|
| `name` | string | yes | Canonical conversational topic name |
| `confidence` | string | yes | Deterministic confidence label: `high`, `medium`, or `low` |
| `is_primary` | boolean | no | Marks whether this is the primary topic for the message |

Ownership:

- Owned by ENG-002 Conversation Engine.
- Not produced by Business Brain.
- Not interpreted as a business intent.

### 1.2 Contract: ConversationTopics

`ConversationTopics` is the topic envelope attached to a conversation context.

Fields:

| Field | Type | Required | Description |
|---|---|---:|---|
| `primary` | ConversationTopic or null | no | Dominant topic detected for the current message/context |
| `secondary` | list of ConversationTopic | no | Additional topics detected with lower priority |

### 1.3 Initial Topic Set

I3 defines a conservative deterministic topic set:

| Topic | Meaning |
|---|---|
| `greeting` | Conversation opening, greeting, salutation |
| `farewell` | Conversation closing or goodbye |
| `complaint` | Complaint, dissatisfaction, reported issue |
| `purchase` | Product, price, purchase, quote, commercial inquiry |
| `support` | Help, support, assistance, technical problem |
| `information` | General information request: schedule, address, contact, how/what/when questions |
| `general` | Default topic when no specific rule matches |

### 1.4 Representation Inside ConversationContext

`ConversationContext` receives one new field:

| Field | Type | Default | Description |
|---|---|---|---|
| `topics` | ConversationTopics or null | null | Topics detected by the Conversation Engine |

This field enriches the context but does not change the inter-engine contract with Business Brain in I3.

### 1.5 Enums

No enum is required for I3.

Rationale:

- Blueprint D-009 names Conversation Topics as a conversational object, but does not mandate a fixed enum.
- A string-based topic name avoids premature contract hardening.
- The initial deterministic topic list remains documented and testable.

If a future CTO decision requires stronger contracts, a topic enum can be introduced later without changing I3 behavior.

## 2. TopicDetector

### 2.1 Responsibility

The Topic Detector answers:

> What is the customer talking about?

It does not answer:

> What business goal should BotWA execute?

That second question remains the responsibility of Business Brain / Intent Analyzer.

### 2.2 Interface

The Topic Detector exposes one public operation:

| Operation | Input | Output |
|---|---|---|
| Detect topics | ConversationContext | ConversationContext enriched with ConversationTopics |

The operation must be deterministic and side-effect free in I3.

### 2.3 Inputs

The detector may read:

- Current message content.
- Conversation history from `ConversationContext`.
- Conversation state if present.
- Channel metadata if present.
- Customer profile if present.

I3 should start with current message content as the primary signal and keep history/state usage minimal to avoid scope expansion.

### 2.4 Outputs

The detector produces:

- One primary topic.
- Zero or more secondary topics.
- Confidence labels derived from rule strength.

It must always produce a valid topic envelope. If no specific topic matches, the primary topic is `general` with low confidence.

### 2.5 Initial Algorithm

The first implementation must be deterministic rule matching.

Algorithm outline:

1. Normalize message content.
2. Evaluate topic rules in a stable priority order.
3. Collect all matched topics.
4. Select primary topic by rule priority and match strength.
5. Preserve remaining matches as secondary topics.
6. Fall back to `general` when no rule matches.
7. Return a new context instance enriched with topics.

No AI, LLM call, embeddings, external lookup, or model inference is allowed in I3.

### 2.6 Suggested Rule Priority

Priority order for I3:

1. `complaint`
2. `support`
3. `purchase`
4. `information`
5. `greeting`
6. `farewell`
7. `general`

Rationale:

- Operationally sensitive topics should win when a message contains mixed signals.
- Example: "Hola, tengo un problema" should be `support` or `complaint`, not merely `greeting`.

### 2.7 Confidence Rules

Initial confidence labels:

| Confidence | Meaning |
|---|---|
| `high` | Multiple strong keywords or direct phrase match |
| `medium` | One clear keyword match |
| `low` | Default/fallback or weak generic match |

Confidence remains conversational, not business confidence.

## 3. Integration Pipeline

### 3.1 Official Blueprint Pipeline

Blueprint D-009 defines:

Message Receiver  
-> Conversation Context Builder  
-> Topic Detector  
-> Conversation State Manager  
-> Business Brain  
-> Response Composer  
-> Channel Adapter  
-> Response

### 3.2 I3 Implementation Pipeline

Given I1 and I2 are already in place, the practical I3 pipeline is:

ConversationService  
-> StateManager get/create current state  
-> ContextBuilder builds enriched ConversationContext  
-> TopicDetector enriches context with ConversationTopics  
-> MessageRouter sends context toward Business Brain  
-> Business Brain keeps current behavior  
-> Response flow remains unchanged

### 3.3 Exact Execution Point

The Topic Detector must run after `ConversationContextBuilder` and before routing to Business Brain.

This placement satisfies AR-002:

- Topic detection happens inside Conversation Engine.
- Business Brain still receives the message through the existing route.
- Intent remains owned by Business Brain.

## 4. Required Changes

### 4.1 New Files

| File | Purpose |
|---|---|
| `app/domain/conversation/topics.py` | ConversationTopic and ConversationTopics contracts |
| `app/core/conversation/topic_detector.py` | Deterministic TopicDetector component |
| `tests/test_topic_detector.py` | Unit tests for deterministic topic detection |

### 4.2 Modified Files

| File | Change |
|---|---|
| `app/domain/conversation/contracts.py` | Add optional `topics` field to ConversationContext |
| `app/core/conversation/service.py` | Run TopicDetector after ContextBuilder and before Business Brain route |
| `app/api/dependencies.py` | Instantiate and inject TopicDetector into ConversationService |
| `tests/test_conversation_contracts.py` | Verify ConversationContext can hold topics |
| `tests/test_conversation_service.py` | Verify TopicDetector is called in pipeline |
| `tests/test_vs1_integration.py` | Regression: existing vertical slice remains green |

### 4.3 New Contracts

- `ConversationTopic`
- `ConversationTopics`
- `ConversationContext.topics`

### 4.4 Dependencies

No external dependency is required.

I3 uses:

- Pydantic domain models already used by the project.
- Existing ConversationContext.
- Existing ConversationService dependency wiring.

## 5. Compatibility With Current IntentClassifier

### 5.1 Temporary Coexistence

During I3, Topic Detector and IntentClassifier will operate in parallel:

- Topic Detector identifies conversational topic inside ENG-002.
- IntentClassifier continues to classify current intents inside ENG-001.

This means `greeting` and `farewell` may temporarily exist both as:

- Conversation topics from ENG-002.
- Current intent outputs from ENG-001.

This duplication is intentional for compatibility and must not be fixed in I3.

### 5.2 No Business Brain Changes

I3 must not:

- Modify `IntentClassifier`.
- Rename existing intents.
- Remove greeting/farewell from Business Brain.
- Change BusinessRequest.
- Change BusinessDecision.
- Change BusinessBrainService behavior.

### 5.3 AR-002 Preparation

I3 prepares AR-002 by creating the correct Conversation Engine topic object and pipeline position.

Future cleanup can later move pure conversational categories out of Business Brain, but that is outside I3 scope.

## 6. Tests

### 6.1 Unit Tests

Add focused tests for `TopicDetector`.

Required cases:

| Case | Expected primary topic |
|---|---|
| "Hola" | `greeting` |
| "Adios / hasta luego" | `farewell` |
| "Tengo un problema / no funciona" | `support` or `complaint`, according to chosen rule |
| "Quiero saber el precio / cuanto cuesta" | `purchase` |
| "Cual es el horario / direccion" | `information` |
| Unknown text | `general` |
| Mixed greeting + issue | operational topic wins over `greeting` |

Also test:

- Secondary topics are preserved when multiple rules match.
- Confidence label is stable.
- The detector does not mutate the original context.

### 6.2 Contract Tests

Update conversation contract tests to verify:

- `ConversationTopic` can be created.
- `ConversationTopics` supports primary and secondary topics.
- `ConversationContext` accepts optional topics.
- Existing contexts without topics remain valid.

### 6.3 Integration Tests

Add or update ConversationService tests to verify:

- ContextBuilder runs before TopicDetector.
- TopicDetector runs before MessageRouter/Business Brain.
- The context sent to the router contains topics.
- Existing response behavior remains unchanged.

### 6.4 Regression Tests

Run existing Vertical Slice tests unchanged:

- Greeting flow remains accepted.
- Price inquiry flow remains accepted.
- Support/question flows remain accepted.
- WhatsApp webhook flow remains unaffected.

I3 is successful only if Topic Detector is present and the existing Vertical Slice remains green.

## 7. Risks

### R1 - Topic/Intent Confusion

Risk: Developers may treat topic as intent or start using topics to drive business decisions.

Mitigation:

- Keep Topic contracts under `app/domain/conversation`.
- Do not feed topics into Business Brain logic in I3.
- Document AR-002 in tests and plan.

### R2 - Vertical Slice Regression

Risk: Adding a pipeline step may alter existing responses.

Mitigation:

- TopicDetector must enrich context only.
- Business Brain behavior remains unchanged.
- VS1 regression tests must remain green.

### R3 - Overfitting Topic Rules

Risk: Too many keywords or complex rules could create unstable behavior.

Mitigation:

- Keep the first ruleset small and deterministic.
- Prefer broad, explainable categories.
- Do not add AI/LLM logic in I3.

### R4 - Premature Thread Modeling

Risk: Blueprint mentions Conversation Threads, but implementing full multi-thread management would expand scope.

Mitigation:

- I3 introduces `ConversationTopics`.
- Full `ConversationThreads` management remains out of scope unless CTO explicitly authorizes it.
- The plan leaves room for threads later without implementing them now.

## 8. Out Of Scope

I3 does not include:

- Business Brain changes.
- IntentClassifier changes.
- BusinessRequest changes.
- BusinessDecision changes.
- Response Composer implementation.
- Channel Adapter changes.
- ConversationThreads implementation beyond preserving the concept for future work.
- AI-based topic detection.
- New engines.
- ADR or Blueprint edits.

## 9. Acceptance Criteria

I3 implementation can be considered complete when:

- Topic contracts exist under Conversation Engine domain.
- TopicDetector exists under Conversation Engine core.
- ConversationContext can carry topics.
- ConversationService executes TopicDetector after ContextBuilder and before Business Brain routing.
- Existing Vertical Slice behavior remains unchanged.
- Unit, contract, integration, and regression tests are green.
- No Business Brain or IntentClassifier behavior has changed.

## 10. CTO Review Status

READY FOR CTO REVIEW
