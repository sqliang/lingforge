# 灵构 LingForge — AI Coding Guide

This repository is an AI development workbench, not a static UI demo. Generated code must preserve the product's trust boundary: users create constrained React apps; the platform validates, builds, versions, and previews them safely.

## 1. Read first and respect the source of truth

Read these documents before changing a non-trivial feature:

1. `docs/0-task.md` — assignment and delivery constraints.
2. `docs/1-PRD.md` — product scope and acceptance criteria.
3. `docs/2-设计文档.md` — architecture and security boundaries.
4. `docs/3-运行时与数据设计.md` — data model, state machine, Saga, and SSE contract.
5. `docs/4-目录与前端模块设计.md` — target directory layout, frontend state ownership, and migration order.

When code, a request, and these documents disagree, do not silently invent a new architecture. Identify the conflict, propose the smallest compatible change, and update the relevant design document when the architecture or contract truly changes.

## 2. Working style

- Think before coding: inspect the relevant code, contracts, and tests; state the intended touched surface and success criteria for non-trivial work.
- Prefer the simplest design that satisfies the stated requirement and existing boundaries. Do not add abstractions, dependencies, flags, configuration, or background services without a concrete need.
- Make surgical changes. Do not refactor unrelated code, rewrite working UI merely for style, or overwrite user changes.
- Keep a feature complete across its user path: input validation, authorization, loading/error/cancellation behavior, persistence, and verification must agree.
- Never claim a feature works because it compiles or renders. Verify the actual user-facing path and report what was run and what remains unverified.

## 3. Architecture invariants

- Git is the source of truth for generated source code and real version history. PostgreSQL is the source of truth for product state and Run events. Object Storage holds immutable artifacts, long logs, and exports.
- A failed or cancelled Run must never move `stable_version_id`, replace the stable preview, or rewrite Git history.
- Browser code may use Supabase Auth for identity only. Business data, Git, Build Runner, Storage, and service credentials are server-side concerns behind FastAPI.
- Do not put Service Role keys, Docker sockets, host paths, Git credentials, preview tickets, full tool traces, or secrets in browser code, logs, SSE payloads, or Zustand persistence.
- Deep Agents are restricted reasoning components. They do not own validation, TypeScript/Vite build, Git commits, artifact upload, or stable-version promotion. Those are deterministic Worker steps.
- Generated code is untrusted: preserve allowlisted paths/dependencies, AST/security validation, rootless network-isolated builds, and the separate preview Origin.
- Use the approved Run lifecycle and event contract. Repair is a single stage of an existing Run, not an independent Run type. Do not replace persisted SSE with simulated timers or Supabase Realtime.

## 4. Module and state rules

- Follow the target layout in `docs/4-目录与前端模块设计.md`. Keep page components thin; place feature behavior in `features/<name>/`; use `shared/` only for genuinely cross-feature utilities.
- `shared/platform/` is the only frontend module allowed to sense host (web/desktop) differences; desktop IPC may be exposed only through the preload whitelist.
- Frontend state ownership is strict:
  - Supabase Auth + `AuthProvider`: user/session only.
  - TanStack Query: all server facts (Project, Contract, messages, Run, files, builds, versions, preview tickets).
  - Zustand project-scoped vanilla store: editor tabs, layout, selection, and SSE connection UI only.
  - Component state: local input, popover, scroll, and display-only interaction.
- Never duplicate full server entities in React Query and Zustand. SSE reducers update Query projections; Zustand stores only transport/UI metadata such as connection state and last applied sequence.
- Do not add production mock writes. Development fixtures must be explicit, isolated in `mocks/`, and impossible to activate accidentally in production.
- Prefer small cohesive modules. If a file starts owning unrelated UI, data access, state transitions, and parsing, split it by responsibility rather than adding another large Context or utility grab-bag.

## 5. API, database, and SSE rules

- Validate authentication and project ownership in every FastAPI command/query before reading or changing project data.
- Use request idempotency, project-level write exclusion, short database transactions, leases, and the Saga rules from the data design. Never hold a DB lock while calling a model or building Docker code.
- Treat API/SSE/Build Contract schemas in `contracts/` as versioned public contracts. Change producer and consumer together, with migration/compatibility behavior made explicit.
- Browser SSE must be accessed only through the local `SseTransport` adapter around `@microsoft/fetch-event-source`; feature UI must not import that library directly.
- Send Bearer tokens in headers, never query parameters. Validate `200` plus `text/event-stream`; handle 401 refresh once, 403/404 terminally, 410 by fetching a snapshot then reconnecting, and transient failures with bounded exponential backoff.
- Verify SSE `id`, `runId`, `sequence`, and schema before applying an event. Ignore duplicates; resolve gaps by reading the server snapshot rather than guessing state.

## 6. Quality gates: static checks and dynamic tests are mandatory

Every code change requires the relevant checks before handoff. Run the narrowest useful tests during iteration, then the applicable full checks before completion.

| Change area | Minimum static validation | Minimum dynamic validation |
| --- | --- | --- |
| Frontend | `pnpm run lint`, TypeScript check, `pnpm run build` | Test the changed route/interaction in a browser or component/E2E test |
| FastAPI/domain/data | formatter/linter/type checks configured by `pyproject.toml` | Unit tests plus API/database integration test for changed behavior |
| Worker/Git/Build/Saga | static checks for touched Python | Success, build failure, cancellation, retry/repair limit, and stable-pointer protection tests |
| SSE | Type/schema checks | Authorization, reconnect, duplicate/gap sequence, 401/403/404/410, abort and terminal Run tests |
| Migration/security | migration validation and policy review | Ownership isolation and negative-path tests with a second user/session |

- Add or update tests when behavior changes or a regression could recur. A bug fix needs a regression test unless it is impossible to automate; say why if so.
- Do not weaken, skip, or delete tests to make a change pass. Do not hide errors behind mock success states.
- If a required check cannot run, report the exact command, blocker, and residual risk. Do not call the work verified.

## 7. Comments and documentation standard

- Write comments for **why**, invariants, security boundaries, state transitions, non-obvious data transformations, and failure/compensation semantics—not for syntax that is already obvious from readable code.
- Every non-trivial source file starts with a concise header comment/docstring describing its responsibility, boundaries, and key collaborators.
- Exported TypeScript hooks, stores, public DTO mappers, and complex UI/streaming functions use JSDoc where callers need contract or lifecycle context.
- Python modules, public functions/classes, Worker stages, database transactions, and security-sensitive code use clear docstrings. Explain side effects, transaction boundary, authorization assumption, and error behavior where relevant.
- Keep comments accurate as code changes. Remove stale comments; never use comments to excuse dead code or unfinished behavior.
- Update README/design docs when commands, architecture, public API/SSE schemas, data retention, security boundaries, or user-visible workflows change.

## 8. Completion report

At handoff, state:

1. What changed and the user-visible result.
2. Key architectural/security decisions made or preserved.
3. Static checks and dynamic tests run, with outcomes.
4. Any unverified behavior, blocked dependency, or deliberately deferred work.

