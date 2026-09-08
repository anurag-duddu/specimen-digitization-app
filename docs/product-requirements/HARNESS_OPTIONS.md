# Durable Workflow and Agent Harness Decision

| Document field | Value |
|---|---|
| Status | Architecture boundary accepted; workflow engine selection pending comparative spike |
| Date | 2026-09-07 |
| Pilot | Field Museum Insects |
| Related document | [Product Requirements Document](./PRD.md) |

## Decision summary

The project will use two application-owned layers:

1. A **durable workflow engine** for each specimen. Temporal is the production-reference candidate; Google Cloud Workflows is the Firebase/GCP-native comparator.
2. **Pydantic AI** as the first typed inner-harness candidate for collection-specific enrichment, evidence gathering, resolution, and verification.

Keep both behind application-owned interfaces so the database schema and collection profiles do not depend directly on either framework.

This is the strongest current fit because the application needs both kinds of capability:

- a workflow that can survive worker crashes, deployments, provider outages, long retry windows, and human-review pauses; and
- a model/provider-neutral Python harness with strict structured outputs, typed tools, validation, usage limits, and an application-owned BYOK adapter boundary.

The workflow engine is responsible for **when and whether work executes**. Pydantic AI is responsible for **how a bounded agent reasons and calls approved tools inside an agentic stage**. Firebase SQL Connect backed by Cloud SQL for PostgreSQL remains the product-facing record and status store; Cloud Storage holds images and large immutable payloads. A workflow engine owns execution history, not specimen business data.

The workflow-engine selection must be validated with a short, bounded technical spike before any Temporal Cloud resource is provisioned or production implementation expands. Exercise Temporal locally first, then run the same approved Insects scenario against Temporal and Google Cloud Workflows, including a provider rate limit, process crash, human pause, replay, provider-authenticated call, typed lookup failure, and idempotency test.

## What a workflow engine adds to Firebase

Firebase remains sufficient for identity, authorization, relational product data, object storage, realtime UI state, short event handlers, and individual queued jobs. Firebase task queues add per-task retries, rate limits, and asynchronous dispatch, but the application would still have to own the end-to-end specimen state machine, recovery point, and human-resumption protocol.

| Concern | Firebase/GCP application layer | Additive workflow-engine role |
|---|---|---|
| Identity and access | Firebase Authentication and App Check | None |
| Product truth | SQL Connect/Cloud SQL | None; write only application-owned records and summaries |
| Images and large evidence | Cloud Storage | Carry immutable references, never image bytes or large raw payloads |
| Individual background work | Cloud Functions, Cloud Run, and Cloud Tasks | Coordinate dependencies, parallelism, retries, cancellation, and compensation across jobs |
| Long human review | UI and persisted review records | Wait durably, accept a decision, and resume the same run |
| Failure recovery | Idempotent handlers and application-authored checkpoints | Reconstruct execution progress after worker or infrastructure failure |

Temporal provides the finer-grained execution history and native Pydantic AI durability path. Google Cloud Workflows provides retries, parallel steps, and callback-based human waits inside the existing GCP boundary. Temporal earns its added service, cost, deterministic-code constraints, and versioning burden only if the spike proves materially simpler or safer recovery for this pipeline.

Official references: [Firebase task queue functions](https://firebase.google.com/docs/functions/task-functions), [Temporal Workflows and replay](https://docs.temporal.io/workflows), [Pydantic AI with Temporal](https://pydantic.dev/docs/ai/capabilities/durable_execution/temporal/), and [Google Cloud Workflows human-in-the-loop callbacks](https://docs.cloud.google.com/workflows/docs/tutorials/callbacks-firestore).

## Why not use a single unconstrained agent framework for everything?

Most of this pipeline is not agentic:

```text
ingest -> classify -> select profile -> segment -> fan out model reads
       -> store raw observations -> calculate disagreements
       -> run bounded enrichment agents -> deterministic validation
       -> policy-controlled queue disposition
```

Image storage, SAM 3 execution, independent transcription fan-out, retries, and queue assignment should be deterministic workflow activities. Agents add value for ambiguous taxonomy, geography, parties, historical context, and evidence reconciliation. This boundary makes failures reproducible and prevents a free-form model from deciding whether its own work is complete. EMu projection and export are deferred until after the internal application works end-to-end.

## Option comparison

Scores are directional for this product, from 1 (poor fit) to 5 (strong fit). They must be validated in a spike.

| Option | Durability | Typed evidence contracts | BYOK/provider flexibility | Human review | Operational burden | Fit |
|---|---:|---:|---:|---:|---:|---|
| **Pydantic AI + Temporal** | 5 | 5 | 5 | 5 | 3 | Production-reference candidate for fine-grained recovery; not yet selected. |
| **Pydantic AI + Google Cloud Workflows** | 4 | 5 | 5 | 4 | 4 | Required GCP-native comparator for short, bounded agent stages. |

`Operational burden` is scored so 5 means simplest for this Firebase/GCP-oriented team.

## Option 1 — Pydantic AI with Temporal

### Strengths

- Pydantic AI provides validated structured outputs and typed Python models, which align well with the Insects field schema and typed lookup/error contracts.
- It supports multiple model providers, so a collection profile can resolve a logical capability to an approved museum BYOK connection or a platform-managed model behind an application-owned interface.
- Pydantic AI officially supports durable execution through Temporal. Model requests, I/O tools, and MCP calls can execute as Temporal activities while the agent coordination remains in the durable workflow.
- Temporal is built for execution that resumes after process, network, or infrastructure failure.
- Python is a natural backend language for segmentation, computer vision, parsing, scientific-data adapters, and Pydantic schemas.

### Tradeoffs

- Temporal adds a service and a programming model that the team must operate or purchase as Temporal Cloud.
- Workflow code must follow deterministic replay constraints; model and tool I/O must be isolated in activities.
- Versioning activity names and running long-lived workflows across deployments requires discipline.
- Images and large model payloads cannot ride inside workflow history. Only stable references and compact typed results should pass through it.

### Best use here

Use one Temporal workflow per specimen run. It invokes deterministic activities for classification, segmentation, transcription fan-out, scoring, persistence, and queue policy. It invokes Pydantic AI agents only within profile-defined enrichment and adjudication stages.

Official references: [Pydantic AI durable execution](https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/), [Pydantic AI Temporal integration](https://pydantic.dev/docs/ai/capabilities/durable_execution/temporal/), [Pydantic AI model providers](https://ai.pydantic.dev/models/overview/), and [Temporal documentation](https://docs.temporal.io/).

## Option 2 — Pydantic AI with Google Cloud Workflows

### Strengths

- Fits the Firebase/Google Cloud boundary with fewer vendors.
- Google Cloud Workflows provides retries, parallel steps, callbacks, and long-running execution.
- Cloud Run services/jobs can host the Python model and harness workers.
- Pydantic AI still provides the typed provider/tool layer behind application-owned routing.

### Tradeoffs

- There is no first-party Pydantic AI durable integration with Google Cloud Workflows in the current Pydantic AI durable-execution list.
- A Pydantic AI loop running inside one Cloud Run invocation is not automatically checkpointed at each model/tool boundary. The application must keep loops short or externalize every meaningful tool/model step.
- Workflow definitions and in-workflow data have size limits, so all images, raw responses, and evidence captures still require Cloud Storage pointers.

### Best use here

Choose this if infrastructure simplicity is more important than fine-grained agent replay for the P0 pilot. Constrain each agent invocation to a small, idempotent task and let Workflows orchestrate those tasks. Do not run an unbounded research agent inside one HTTP step.

Official references: [Google Cloud Workflows best practices](https://docs.cloud.google.com/workflows/docs/best-practice), [Workflows callbacks](https://docs.cloud.google.com/workflows/docs/creating-callback-endpoints), and [Workflows limits](https://docs.cloud.google.com/workflows/quotas).

## Pruned alternatives

LangGraph, Google ADK, OpenAI Agents SDK, AWS Step Functions, CrewAI, and Mastra are not active workflow-engine comparators for Phase 0. Reopen one only if the product's cloud boundary, model strategy, or workflow shape changes materially; do not combine multiple systems that each try to own retries, checkpoints, or human pauses.

## Proposed reference architecture

```text
Flutter client
    |
    v
Firebase Auth + application API
    |
    +--> SQL Connect/Cloud SQL: specimen, review, and current-status records
    +--> Cloud Storage: originals, crops, raw outputs, evidence
    |
    v
Durable specimen workflow (Temporal or Google Cloud Workflows)
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
    +--> deterministic activity: persistence and final queue policy
```

### Required application-owned interfaces

The following contracts should belong to this codebase, not a framework:

- `WorkflowEngine`: start, signal, cancel, query, and replay a specimen run.
- `HarnessRunner`: run a named, versioned collection-profile phase.
- `ModelGateway`: resolve a logical capability to an approved model/provider/BYOK connection.
- `ToolRegistry`: expose versioned, allow-listed, typed tools.
- `EvidenceStore`: persist query, source, result digest, locator, and derived claims.
- `CheckpointStore`: map workflow state to specimen/pipeline status visible through SQL Connect.
- `DispositionPolicy`: evaluate deterministic clearance, review, and deferred gates.

These interfaces make a future framework change possible without migrating the specimen record model.

## Insects pilot spike

Build the same narrow scenario with the top two options before final selection:

1. Start from an adjudicated label transcript fixture.
2. Validate an FMNH-INS identifier.
3. Call a fake Global Names Verifier adapter, then the real sandbox/public API if approved.
4. Fan out Catalogue of Life and GBIF lookups.
5. Return an ambiguous taxon and pause for a reviewer decision through Flutter/SQL Connect.
6. Resume and perform a geography lookup.
7. Simulate a `429`, provider timeout, worker termination, credential failure, and oversized raw response.
8. Prove no tool side effect or model observation is duplicated after replay.
9. Run once through a platform model and once through a museum-scoped BYOK connection for an approved adapter.
10. Produce a complete evidence graph and deterministic queue decision.

### Decision gates

- Exact recovery point after a worker crash.
- No duplicate external effects under retry/replay.
- Typed output and error fidelity.
- Human pause/resume that survives deployment.
- BYOK and platform-provider parity behind one logical capability.
- Raw/evidence payload offloading to Cloud Storage.
- SQL Connect transaction consistency and conflict behavior.
- Trace redaction and restricted-data controls.
- Framework upgrade/versioning behavior for active runs.
- Measured development effort, processing latency, and infrastructure cost.

## Current decision status

| Decision | Status | Rationale |
|---|---|---|
| Use separate durable workflow and agent-harness layers | Accepted | The product has long-running deterministic and agentic stages with different reliability needs. |
| Use Pydantic AI for the first harness spike | Accepted | Strong typed outputs, Python fit, provider breadth, and first-party durable-execution options. |
| Use Temporal for the production-reference spike | Accepted | Strongest fine-grained recovery and replay candidate; this does not select it for production. |
| Test Google Cloud Workflows with the same scenario | Accepted | It aligns with Firebase/GCP and has native callback/human-review patterns. |
| Treat Temporal as a replacement for Firebase | Rejected | Firebase remains the identity, product-data, object-storage, and UI-state platform. |
| Provision Temporal Cloud before the bounded comparison passes | Rejected | Cloud setup creates another billable service before its value is demonstrated. |
| Select the final stack without a failure-injection spike | Rejected | Documentation alone cannot establish behavior under this application's evidence and replay requirements. |
| Use Hugging Face as the initial platform model gateway | Accepted for spike | One server-side token supports explicit Qwen and Muse routes; representative quality, privacy, and failure testing remain required. |
| Allow Hugging Face automatic provider routing in published profiles | Rejected | Versioned runs must pin and record the infrastructure provider; fallback cannot happen silently. |
| Treat SAM 3 and Nemotron as ordinary routed chat models | Rejected | Neither selected Hub asset is currently served by the routed API; keep them behind pinned GPU/self-hosted adapters. |
