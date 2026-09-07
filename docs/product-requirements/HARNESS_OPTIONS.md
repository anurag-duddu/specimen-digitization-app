# Agent Harness Options for the Specimen Digitization Platform

| Document field | Value |
|---|---|
| Status | Accepted architecture decision; implementation spike pending |
| Date | 2026-09-07 |
| Pilot | Field Museum Insects |
| Related document | [Product Requirements Document](./PRD.md) |

## Selected architecture

The project will use a two-layer architecture:

1. **Temporal** as the durable outer workflow for each specimen.
2. **Pydantic AI** as the typed inner agent harness for collection-specific enrichment, evidence gathering, resolution, and verification.

Keep both behind application-owned interfaces so the database schema and collection profiles do not depend directly on either framework.

This is the strongest current fit because the application needs both kinds of capability:

- a workflow that can survive worker crashes, deployments, provider outages, long retry windows, and human-review pauses; and
- a model/provider-neutral Python harness with strict structured outputs, typed tools, validation, usage limits, and direct AWS Bedrock support.

Temporal is responsible for **when and whether work executes**. Pydantic AI is responsible for **how a bounded agent reasons and calls approved tools inside an agentic stage**. Firestore remains the product-facing record and status store; Cloud Storage holds images and large immutable payloads. Temporal owns durable execution history, not specimen business data.

The selection must be validated with a short technical spike before production implementation expands. The spike must use approved Insects fixtures and include a provider rate limit, process crash, human pause, replay, Bedrock call, typed lookup failure, and idempotency test.

## Why not use a single unconstrained agent framework for everything?

Most of this pipeline is not agentic:

```text
ingest -> classify -> select profile -> segment -> fan out model reads
       -> store raw observations -> calculate disagreements
       -> run bounded enrichment agents -> deterministic validation
       -> policy-controlled queue disposition
```

Image storage, SAM 3 execution, independent transcription fan-out, retries, queue assignment, and export should be deterministic workflow activities. Agents add value for ambiguous taxonomy, geography, parties, historical context, and evidence reconciliation. This boundary makes failures reproducible and prevents a free-form model from deciding whether its own work is complete.

## Option comparison

Scores are directional for this product, from 1 (poor fit) to 5 (strong fit). They must be validated in a spike.

| Option | Durability | Typed evidence contracts | BYOK/provider flexibility | Human review | Operational burden | Fit |
|---|---:|---:|---:|---:|---:|---|
| **Pydantic AI + Temporal** | 5 | 5 | 5 | 5 | 3 | Recommended production architecture. |
| **Pydantic AI + Google Cloud Workflows** | 4 | 5 | 5 | 4 | 4 | Best GCP-native simplification if agent runs remain short and bounded. |
| **LangGraph with persistent checkpoints** | 4 | 4 | 5 | 5 | 3 | Strong graph-centric alternative when dynamic branching dominates. |
| **Google ADK + durable outer workflow** | 3 | 4 | 4 | 4 | 4 | Good when Vertex/Gemini and Google Agent Runtime become strategic. |
| **OpenAI Agents SDK + durable outer workflow** | 3 | 4 | 3 | 4 | 4 | Good lightweight option when OpenAI is the primary model platform. |
| **AWS Strands/Bedrock + Step Functions** | 4 | 3 | 3 | 4 | 2 | Good for an AWS-first product; weaker fit with the chosen Firebase/GCP center. |
| **CrewAI or Mastra** | 3 | 3 | 4 | 4 | 4 | Useful prototyping alternatives; require a deeper reliability and governance spike before core use. |

`Operational burden` is scored so 5 means simplest for this Firebase/GCP-oriented team.

## Option 1 — Pydantic AI with Temporal

### Strengths

- Pydantic AI provides validated structured outputs and typed Python models, which align well with the Insects field schema and typed lookup/error contracts.
- It supports multiple model providers and has direct Bedrock integrations, so a collection profile can resolve a logical capability to museum BYOK or a platform-managed model.
- Pydantic AI officially supports durable execution through Temporal. Model requests, I/O tools, and MCP calls can execute as Temporal activities while the agent coordination remains in the durable workflow.
- Temporal is built for execution that resumes after process, network, or infrastructure failure.
- Python is a natural backend language for segmentation, computer vision, parsing, scientific-data adapters, and Pydantic schemas.

### Tradeoffs

- Temporal adds a service and a programming model that the team must operate or purchase as Temporal Cloud.
- Workflow code must follow deterministic replay constraints; model and tool I/O must be isolated in activities.
- Versioning activity names and running long-lived workflows across deployments requires discipline.
- Images and large model payloads cannot ride inside workflow history. Only stable references and compact typed results should pass through it.

### Best use here

Use one Temporal workflow per specimen run. It invokes deterministic activities for classification, segmentation, transcription fan-out, scoring, export, and queue policy. It invokes Pydantic AI agents only within profile-defined enrichment and adjudication stages.

Official references: [Pydantic AI durable execution](https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/), [Pydantic AI Temporal integration](https://pydantic.dev/docs/ai/capabilities/durable_execution/temporal/), [Pydantic AI Bedrock provider](https://pydantic.dev/docs/ai/models/bedrock/), and [Temporal documentation](https://docs.temporal.io/).

## Option 2 — Pydantic AI with Google Cloud Workflows

### Strengths

- Fits the Firebase/Google Cloud boundary with fewer vendors.
- Google Cloud Workflows provides retries, parallel steps, callbacks, and long-running execution. Google publishes a human-in-the-loop pattern connecting Workflows, Firestore, Cloud Run functions, and a Firebase web client.
- Cloud Run services/jobs can host the Python model and harness workers.
- Pydantic AI still provides the typed provider/tool layer, including Bedrock.

### Tradeoffs

- There is no first-party Pydantic AI durable integration with Google Cloud Workflows in the current Pydantic AI durable-execution list.
- A Pydantic AI loop running inside one Cloud Run invocation is not automatically checkpointed at each model/tool boundary. The application must keep loops short or externalize every meaningful tool/model step.
- Workflow definitions and in-workflow data have size limits, so all images, raw responses, and evidence captures still require Cloud Storage pointers.

### Best use here

Choose this if infrastructure simplicity is more important than fine-grained agent replay for the P0 pilot. Constrain each agent invocation to a small, idempotent task and let Workflows orchestrate those tasks. Do not run an unbounded research agent inside one HTTP step.

Official references: [Google Cloud Workflows best practices](https://docs.cloud.google.com/workflows/docs/best-practice), [Workflows callbacks](https://docs.cloud.google.com/workflows/docs/creating-callback-endpoints), [Firestore human-in-the-loop tutorial](https://docs.cloud.google.com/workflows/docs/tutorials/callbacks-firestore), and [Workflows limits](https://docs.cloud.google.com/workflows/quotas).

## Option 3 — LangGraph

### Strengths

- Explicit state graphs are a good match for collection-specific branching and specialist nodes.
- Persistent checkpointers support recovery, fault tolerance, time travel, and human-in-the-loop interrupts.
- Reviewers can pause a graph, edit state, and resume it.
- Broad LangChain model/tool integrations offer provider flexibility.

### Tradeoffs

- Production checkpointing normally introduces a supported persistent store such as PostgreSQL; Firestore is not the default production path described in the official persistence documentation.
- The team must define strong schemas and deterministic validation around graph state; flexibility can otherwise become opaque graph logic.
- If LangGraph is placed inside Temporal, the team must define which layer owns retries, persistence, and human pauses to avoid two competing execution histories.

### Best use here

This is the strongest alternative if the collection harness becomes a highly dynamic reasoning graph and visual graph debugging is more valuable than Pydantic AI's simpler typed-agent model. It should still use application-owned evidence schemas and a durable outer boundary for non-agent image processing.

Official references: [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence), [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts), and [LangGraph fault tolerance](https://docs.langchain.com/oss/python/langgraph/fault-tolerance).

## Option 4 — Google Agent Development Kit (ADK)

### Strengths

- Strong alignment with Google Cloud and Cloud Run.
- Supports graph, dynamic, collaborative, sequential, loop, and parallel workflow patterns.
- Supports deterministic nodes mixed with LLM agents.
- Offers model connectors for Google and non-Google models, including OpenAI, Ollama, vLLM, and LiteLLM-based integrations.
- Includes sessions, tools, callbacks, observability, and evaluation concepts.

### Tradeoffs

- Its main advantage is strongest when Google Agent Runtime, Vertex, or Gemini is the strategic center; this product explicitly needs Bedrock BYOK and open-model neutrality.
- Session/workflow state should not be assumed to replace a crash-proof specimen workflow. Pair it with Google Cloud Workflows or Temporal until recovery behavior is proven.
- The current ADK surface is broad and evolving, increasing migration and framework-learning risk for a narrowly scoped pilot.

### Best use here

Choose ADK if the organization decides to standardize on Google-hosted agent infrastructure and accepts provider routing through its supported connector layer.

Official references: [ADK agents and deterministic/agent workflows](https://github.com/google/adk-docs/blob/main/docs/agents/index.md), [ADK workflow types](https://github.com/google/adk-docs/blob/main/docs/workflows/index.md), and [ADK model integrations](https://adk.dev/agents/models/).

## Option 5 — OpenAI Agents SDK

### Strengths

- Lightweight Python and TypeScript SDK.
- Built-in agent loops, specialists-as-tools, handoffs, sessions, guardrails, resumable approvals, and tracing.
- Server-owned tools and storage can integrate cleanly with the application's evidence model.

### Tradeoffs

- It is most natural for an OpenAI-centered model strategy. Bedrock and platform-managed open models would require additional provider/adaptor validation.
- The SDK manages an agent run, but the server still owns deployment, durable business storage, and approval decisions. A separate durable workflow remains necessary for this specimen lifecycle.
- Default tracing requires a collection data-policy review; sensitive payload capture must be disabled or routed appropriately.

### Best use here

Choose this if OpenAI becomes the primary agent provider and the team wants a small abstraction layer. It is not the first choice for a provider-neutral, Bedrock-friendly pilot.

Official reference: [OpenAI Agents SDK](https://developers.openai.com/api/docs/guides/agents).

## Option 6 — AWS Strands/Bedrock with Step Functions

### Strengths

- Direct alignment with grant-funded AWS Bedrock deployments.
- Step Functions supports retry/catch behavior and callback-based human approval.
- AWS service identities, budgets, and Bedrock access remain inside one cloud boundary for BYOK tenants.

### Tradeoffs

- The application control plane is Firebase/Google Cloud, creating a two-cloud operational, identity, networking, logging, and data-residency design.
- It makes the platform architecture follow one BYOK provider rather than treating Bedrock as one provider adapter.
- Open-model and non-AWS routing require more abstraction work.

### Best use here

Use this only if the museum decides the entire processing plane—not just its keys and model calls—must run in AWS.

Official references: [AWS guidance on agent frameworks](https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-frameworks/), [Step Functions error handling](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-error-handling.html), and [Step Functions human approval](https://docs.aws.amazon.com/step-functions/latest/dg/tutorial-human-approval.html).

## Secondary options

CrewAI and Mastra both document persistent flows and human-in-the-loop suspend/resume behavior. They can produce a fast prototype, but they should not be selected for the evidence-critical core until the same crash, replay, schema, provider, audit, and version-migration tests are run against them. Mastra is TypeScript-first, while most of this processing plane is likely to be Python because of the image/ML workload.

References: [CrewAI documentation](https://docs.crewai.com/), [Mastra workflow snapshots](https://mastra.ai/en/reference/workflows/snapshots), and [Mastra workflows](https://mastra.ai/ai-workflows).

## Proposed reference architecture

```text
Flutter client
    |
    v
Firebase Auth + application API
    |
    +--> Firestore: specimen, review, and current-status records
    +--> Cloud Storage: originals, crops, raw outputs, evidence, exports
    |
    v
Temporal specimen workflow
    |
    +--> Cloud Run activity: image quality/classification
    +--> GPU worker activity: SAM 3 segmentation
    +--> provider activities: independent vision transcriptions
    +--> deterministic activity: disagreement calculation
    +--> Pydantic AI harness activities
    |       +--> taxonomy verifier adapters
    |       +--> geography adapters
    |       +--> parties/evidence adapters
    |       +--> bounded specialist agents
    +--> deterministic activity: schema and cross-field validation
    +--> wait for Flutter reviewer when required
    +--> deterministic activity: final queue policy and export
```

### Required application-owned interfaces

The following contracts should belong to this codebase, not a framework:

- `WorkflowEngine`: start, signal, cancel, query, and replay a specimen run.
- `HarnessRunner`: run a named, versioned collection-profile phase.
- `ModelGateway`: resolve a logical capability to an approved model/provider/BYOK connection.
- `ToolRegistry`: expose versioned, allow-listed, typed tools.
- `EvidenceStore`: persist query, source, result digest, locator, and derived claims.
- `CheckpointStore`: map workflow state to specimen/pipeline status visible in Firestore.
- `DispositionPolicy`: evaluate deterministic clearance, review, and deferred gates.

These interfaces make a future framework change possible without migrating the specimen record model.

## Insects pilot spike

Build the same narrow scenario with the top two options before final selection:

1. Start from an adjudicated label transcript fixture.
2. Validate an FMNH-INS identifier.
3. Call a fake Global Names Verifier adapter, then the real sandbox/public API if approved.
4. Fan out Catalogue of Life and GBIF lookups.
5. Return an ambiguous taxon and pause for a reviewer decision through Flutter/Firestore.
6. Resume and perform a geography lookup.
7. Simulate a `429`, provider timeout, worker termination, credential failure, and oversized raw response.
8. Prove no tool side effect or model observation is duplicated after replay.
9. Run once through a platform model and once through a museum-scoped Bedrock connection.
10. Produce a complete evidence graph and deterministic queue decision.

### Decision gates

- Exact recovery point after a worker crash.
- No duplicate external effects under retry/replay.
- Typed output and error fidelity.
- Human pause/resume that survives deployment.
- Bedrock and platform-provider parity behind one logical capability.
- Raw/evidence payload offloading to Cloud Storage.
- Firestore status consistency and conflict behavior.
- Trace redaction and restricted-data controls.
- Framework upgrade/versioning behavior for active runs.
- Measured development effort, processing latency, and infrastructure cost.

## Current decision status

| Decision | Status | Rationale |
|---|---|---|
| Use separate durable workflow and agent-harness layers | Accepted | The product has long-running deterministic and agentic stages with different reliability needs. |
| Use Pydantic AI for the first harness spike | Accepted | Strong typed outputs, Python fit, provider breadth, Bedrock integration, and first-party durable-execution options. |
| Use Temporal for the production-reference spike | Accepted | Strongest fine-grained recovery and replay fit. |
| Test Google Cloud Workflows as the simpler alternative | Recommended | It aligns with Firebase and has native callback/human-review patterns. |
| Select the final stack without a failure-injection spike | Rejected | Documentation alone cannot establish behavior under this application's evidence and replay requirements. |
