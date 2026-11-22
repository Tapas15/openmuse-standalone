# OpenMuse Standalone: Architecture (English translation)

> This is an English translation of [STANDALONE.md](STANDALONE.md). The English original is authoritative; code, file names, table names, error codes, and identifiers in mermaid diagrams are kept in English.

OpenMuse Standalone = upstream [OpenMuse](https://github.com/CopilotKit/openmuse) + a self-hosted chat layer. One setting decides which chat layer is used:

- **`CPK_INTELLIGENCE_API_KEY` unset or blank (local mode).** The CopilotKit runtime runs in SSE mode on OpenMuse’s own persistent `AgentRunner`. Conversations live in the app’s own database (embedded PGlite or `DATABASE_URL`), and thread routes are served by the API itself.
- **Key set.** The runtime runs in Intelligence mode, identical to upstream, so this repo can continue merging upstream without drift.

This page explains how local mode is built and how to keep merging upstream. For the operations reference (routes, response codes, tables, timing parameters, verification), see [STANDALONE-THREADS.md](STANDALONE-THREADS.md).

## Design choices

The CopilotKit runtime provides two integration points for self-hosted thread storage. `LocalThreadEndpointRunner` can let the runtime serve thread lists itself, but its methods are synchronous, while a Postgres-backed store cannot respond synchronously. Therefore OpenMuse Standalone:

1. Implements only the async `AgentRunner` contract (`run`, `connect`, `isRunning`, `stop`), backed by the app’s own database;
2. Serves all `/api/copilotkit/threads*` routes at the Hono layer before the runtime handler, filters by authenticated owner, and rewrites `/info.threadEndpoints` so clients use these routes.

Nothing is kept only in memory: thread locks, in-progress replies, and completed history are all in the database.

## Components

All new server-side logic lives in `apps/server/src/standalone/`. When no key is set, `createStandaloneChat` (`index.ts`) builds it once per app.

| File | Role |
|---|---|
| `chat-store.ts` | `ChatStore`: the `chat_threads`, `chat_runs`, and `chat_events` tables, created at startup in PGlite or Postgres. Any change involving multiple rows is a single SQL statement. |
| `runner.ts` | `LocalAgentRunner`: runs the agent, logs in-progress reply events, saves replies, replays history on connect, stops, and recovers expired locks. Semantics follow the runtime’s `InMemoryAgentRunner` (1.70.1). |
| `runtime-hooks.ts` | `onBeforeHandler` / `onResponse` hooks wrapped around the runtime’s own routes: owner checks, 409 when thread is busy, claim release, `/info` rewrite. |
| `thread-routes.ts` | List, messages, events, state, rename, archive/restore, and delete, scoped to the session owner. |
| `events.ts` | Pure functions for AG-UI events: compaction, message/state reconstruction, replay cleanup. |
| `types.ts` | Contracts between store, runner, and HTTP layers. |

`/api/main-thread` records the owner’s main thread in `chat_threads` instead of calling Intelligence’s `getOrCreateThread`. `/api/workspace` reports mode via `runtime.threads` (`"local"` or `"intelligence"`), and `runtime.richThreads` is `true` in both modes, so the app shows the same thread menu, main conversation, and replay in both modes.

On the client (`apps/mobile/src/`), local mode still uses `copilotkit.connectAgent`, so refreshing the page can attach to an in-progress reply. `local-thread.ts` clears the agent before each connect (the server replays the whole thread because there is no replay cursor); `conversation-run.ts` recognizes HTTP 409 as the same thread lock reported by Intelligence, so queued messages are staged instead of failing.

## Step-by-step of a run

1. The app initiates a run. The runtime routes it; the `onBeforeHandler` hook runs before any response bytes are sent.
2. The hook claims the thread in `chat_threads` for the session owner (`run_id`, holder, heartbeat). A thread belonging to someone else answers `404`; missing, empty, or too-long `threadId`/`runId` answers `400`; database failures answer `503`. Nothing is claimed in these cases.
3. **Thread busy:** if the thread is already replying, the hook answers `409 {"error": "...", "code": "agent_thread_locked"}` before any `200` SSE response. The app already recognizes this error code (it’s the one Intelligence reports as `AgentThreadLockedError`), so queued messages are staged instead of shown as errors.
4. The runtime calls `LocalAgentRunner.run`. Events stream to the app via SSE while the runner logs them to `chat_events` every 250 ms (or every 64 events) and refreshes the lock heartbeat every 5 seconds.
5. After the agent completes, the runner compacts the reply and saves it to `chat_runs`. Only then does the app receive `RUN_FINISHED` (or `RUN_ERROR`). If saving fails, the stream ends with a `RUN_ERROR` whose code is `persistence_failed`; there is never a reply shown to the app but lost on the server.
6. If the runtime answers non-`200` (bad request body, unknown agent), `onResponse` releases the claim and deletes thread rows that never ran.

`connect` replays saved replies for the thread, then follows an in-progress reply if it is running in this process. `stop` aborts the agent, saves what it said so far as `stopped`, and ends the stream.

## Crash recovery

Replies whose lock heartbeat has not updated for more than 30 seconds are recovered by a sweep task running every 15 seconds: the log is saved as an `interrupted` reply and the thread is unlocked. With embedded PGlite, no other process can hold the lock, so all locks left by the previous process are recovered on startup. With `DATABASE_URL`, recovery waits for heartbeat expiry (about 30–45 seconds after a crash). On `SIGINT`/`SIGTERM`, the API saves in-progress replies as interrupted before shutdown.

## Retention and compaction

Each completed reply is stored once, compacted: text and tool-call chunks are merged, state deltas collapse into one `STATE_SNAPSHOT`, and the first event of that run carries only messages new to that thread. The `chat_events` log only holds replies still running and is cleared after the reply is saved or recovered. With `CHAT_RETENTION_DAYS=N`, the sweep task deletes completed replies older than N days; thread rows and names are kept. Deleting a thread deletes its replies and logs.

## Owner isolation

Every thread belongs to the owner corresponding to the session that created it. On thread routes and on run, connect, stop, another owner’s thread id gets the exact same response as a non-existent thread (`404`), and rejected runs do not acquire a lock. Owner fields in request bodies are ignored; owner always comes from the verified session. The runtime’s debug event stream answers `404` in local mode because it carries events for all owners.

## Tracking upstream

This repo = upstream OpenMuse + Standalone commits. Changes to upstream files are small and marked with `// Standalone:` comments; new logic lives in new files.

On conflicts:

| File | What to do |
|---|---|
| `README.md` | Keep this repo’s README. Port upstream README changes to [UPSTREAM-README.md](UPSTREAM-README.md) and adjust relative links pointing to `docs/`. |
| `apps/server/src/config.ts`, `tests/config.test.ts` | Keep the key optional (`chatBackend`, no-op `assertApiDeploymentConfig`, `CHAT_RETENTION_DAYS`). Keep upstream assertions for the key-present path; keyless tests are additions. |
| `apps/server/src/app.ts`, `agent.ts`, `index.ts`, `worker-entry.ts`, `workspace.ts`, `db.ts`, `demo/entry.ts` | Reapply each `// Standalone:` block around upstream changes. Each block is a branch on whether the key is set. |
| `apps/mobile/src/chat.tsx`, `conversation-run.ts`, `screens.tsx`, `packages/domain/src/index.ts` | Reapply `// Standalone:` blocks: `connectThread`, HTTP 409 lock check, the Settings line, `runtime.threads`. |
| `.env.example`, `render.yaml`, `CONTRIBUTING.md`, `docs/*.md` | Keep “key optional” wording. |

When upgrading `@copilotkit/runtime` or `@ag-ui/*`, check the `AgentRunner` contract, `CopilotRuntimeHooks`, the shape of `threadEndpoints` in `/info`, and the `agent_thread_locked` error code. Standalone tests (`tests/standalone-*.test.ts`, `apps/mobile/test/*`) run through the real runtime and the app’s real CopilotKit client, so breaking upgrades will fail the test suite.

Upstream is discussing the same need in [issue #73](https://github.com/CopilotKit/openmuse/issues/73), with proposals in [#94](https://github.com/CopilotKit/openmuse/pull/94) and [#166](https://github.com/CopilotKit/openmuse/pull/166). If upstream ships an official local thread store, this repo will migrate to it and provide a migration for the `chat_*` tables.
