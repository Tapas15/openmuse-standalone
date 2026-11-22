<div align="center">

# OpenMuse Standalone

**Self-hosted OpenMuse: a personal AI agent whose conversations live in your own Postgres, not a hosted chat cloud.**

*A standalone personal AI agent: conversations live in your own Postgres, no hosted chat cloud required.*

**Standalone is the open-source root of [Yuki](https://github.com/caspianchan31/yuki)**: AI teammates, each with its own computer.<br>
*Standalone is the open-source foundation of [Yuki](https://github.com/caspianchan31/yuki). Yuki: AI teammates, each with their own computer.*

[![CI](https://github.com/caspianchan31/openmuse-standalone/actions/workflows/ci.yml/badge.svg)](https://github.com/caspianchan31/openmuse-standalone/actions/workflows/ci.yml)
[![MIT license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/caspianchan31/openmuse-standalone)](https://github.com/caspianchan31/openmuse-standalone/releases)
![Status: alpha](https://img.shields.io/badge/status-alpha-orange.svg)

[Quick start](#quick-start-no-key) · [Upstream vs Standalone](#upstream-vs-standalone) · [Postgres guide](docs/POSTGRES.md) · [Known limits](#known-limits) · [How it is built](docs/STANDALONE.md) · [Roadmap](ROADMAP.md) · [Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md)

<img src="assets/openmuse-demo.gif" alt="OpenMuse running on iPhone in the fictional sample workspace: chat, agent computer, files, a PDF form, a finance summary, goals and ideas" width="300">

</div>

**In one line:** a fork of [CopilotKit's OpenMuse](https://github.com/CopilotKit/openmuse) that stores every conversation in your own Postgres (embedded PGlite by default), streams replies over SSE from your own server, and runs without a CopilotKit Intelligence key.

<p align="center">
  <img src="assets/document.png" alt="A filled PDF form open in the OpenMuse app" width="240">
  &nbsp;&nbsp;
  <img src="assets/finance.png" alt="OpenMuse finance summary card with a plan, income, spending and remaining balance" width="240">
</p>

<p align="center"><sub>The demo and screenshots show the OpenMuse app in its fictional sample workspace (iPhone). They show the app as a whole, not the chat storage that Standalone changes. <a href="assets/openmuse-demo.mp4">Full-quality MP4</a>.</sub></p>

> **Alpha.** This is v0.1.0 of a fork of an alpha project. Expect rough edges; see [Status](#status) and [Known limits](#known-limits).

> Looking for the full OpenMuse guide (demo, features, Render, Google, browser worker, Linux computer)? It is kept as [docs/UPSTREAM-README.md](docs/UPSTREAM-README.md). This page covers what OpenMuse Standalone changes.

[OpenMuse](https://github.com/CopilotKit/openmuse) is a personal agent with a browser, a cloud desktop, files and background work. Upstream, its chat layer stores every conversation in CopilotKit Intelligence, a hosted service: when that service is down, you cannot talk to your agent, and your conversation text lives on someone else's servers.

This fork keeps everything OpenMuse does and moves the chat layer in-house:

- Conversations, thread lists and the main chat are stored in your own Postgres (embedded PGlite by default).
- The agent streams replies straight from your server to your browser (SSE), with no relay through a hosted gateway.
- The model call, the cloud desktop (E2B), mail, calendar and files already ran on your own keys upstream; they are unchanged.
- Everything else tracks upstream OpenMuse. Set `CPK_INTELLIGENCE_API_KEY` and it behaves exactly like upstream.

## Status

**v0.1.0, released 2026-10-11.** Alpha, like upstream. Based on upstream OpenMuse `main` at `1ac68f3` (2026-10-06). See the [changelog](CHANGELOG.md) and [how it is built](docs/STANDALONE.md).

## Upstream vs Standalone

Compared against upstream OpenMuse `main` at `1ac68f3` (2026-10-06), the commit this fork is based on. Upstream may have changed since; see [issue #73](https://github.com/CopilotKit/openmuse/issues/73) for its current discussion.

| | Upstream OpenMuse | OpenMuse Standalone |
|---|---|---|
| Where conversations are stored | CopilotKit Intelligence (hosted) | Your own Postgres or embedded PGlite (no key). With `CPK_INTELLIGENCE_API_KEY` set: Intelligence, as upstream |
| `CPK_INTELLIGENCE_API_KEY` | Required to chat | Optional |
| Chat without the key | Fails: "Main conversation is unavailable", "Failed to initialize thread" | Works: local mode |
| If the hosted chat service is down | You cannot talk to your agent | Local mode does not use it |
| How replies stream | Intelligence runtime | SSE straight from your server |
| Reload mid-reply resumes the reply | Yes | Yes |
| Thread list updates live on other devices | Yes | No: refreshes when the menu opens |
| Memories | Yes | Not served in local mode |
| Browser, Linux computer, Gmail/Calendar, tasks, ideas, goals | Yes | Unchanged from upstream |
| Replies interrupted by a crash | n/a | Recovered at startup (PGlite) or after the lock goes stale (Postgres) |
| Optional retention | n/a | `CHAT_RETENTION_DAYS` |
| Maturity | Alpha | Alpha (v0.1.0, 2026-10-11); `render.yaml` has not been exercised on Render |
| License | MIT | MIT (Intelligence is a separate service, not covered) |

Local mode removes the hosted *chat* layer only. Model calls, optional Gmail/Calendar/E2B, default web search and SDK telemetry still behave as upstream; see [What still leaves your server](#what-still-leaves-your-server).

## Quick start (no key)

**Requirements:** Node 24 LTS and pnpm 11.19.0. The sample workspace needs no model, Google account, Docker or CopilotKit Intelligence key.

```sh
git clone https://github.com/caspianchan31/openmuse-standalone.git openmuse
cd openmuse
pnpm install --frozen-lockfile
cp .env.example .env   # leave CPK_INTELLIGENCE_API_KEY unset
pnpm dev               # API on http://localhost:8787
```

In another terminal:

```sh
pnpm dev:web           # app on http://localhost:8081
```

Send a message, reload the page mid-reply, and the reply resumes; open the thread menu to list, rename, archive or restore conversations. All of it is served by your API from its own database.

**Production build:**

```sh
pnpm build:server && pnpm start   # API (and the in-process task worker)
pnpm build:web                     # static web export in apps/mobile/dist/web
```

Set `EXPO_PUBLIC_API_URL` to the API's public URL when building the web app. A server reachable from other machines needs live mode (`WORKSPACE_MODE=live`, `OPENMUSE_ACCESS_KEY`, `TOKEN_ENCRYPTION_KEY`) and a model; see [Configure the agent and Google](docs/UPSTREAM-README.md#configure-the-agent-and-google). [render.yaml](render.yaml) is upstream's Blueprint with the key marked optional; it has not been exercised on Render for this release.

### Chat settings

| Variable | Default | Effect |
|---|---|---|
| `CPK_INTELLIGENCE_API_KEY` | unset | Unset or blank: **local mode**, conversations in this server's database. Set: upstream's CopilotKit Intelligence mode, unchanged. A wrong key reports errors; it never falls back to local mode. |
| `DATABASE_URL` | unset | Unset: embedded PGlite in `DATA_DIR/postgres`. Set: that Postgres server. |
| `DATA_DIR` | `.openmuse` | Embedded database, documents, signing key and browser profiles. Keep it private and back it up. |
| `CHAT_RETENTION_DAYS` | unset (keep forever) | Local mode only: delete finished replies older than this many days. A whole number from 1 to 36500. |

Everything else (model, provider keys, Google, browser worker, computer) is configured as upstream: [.env.example](.env.example).

### PGlite or Postgres

- **Embedded PGlite (default).** Nothing to install. One process owns the database, so run the task worker inside the API (the default). A reply cut off by a crash is recovered as soon as the API starts again.
- **Postgres (`DATABASE_URL`).** Recommended for a server you depend on. Back it up like any application data. A separate task worker (`pnpm start:worker`) can share it. A reply cut off by a crash is recovered after its lock goes stale, within about 30 to 45 seconds.

The chat tables (`chat_threads`, `chat_runs`, `chat_events`) are created on startup in either database. A step-by-step walkthrough for `DATABASE_URL`, including the separate task worker, is in [docs/POSTGRES.md](docs/POSTGRES.md).

### With and without `CPK_INTELLIGENCE_API_KEY`

| | No key (local mode) | Key set (Intelligence) |
|---|---|---|
| Where conversations live | This server's Postgres or PGlite | CopilotKit Intelligence |
| How replies stream | SSE from this server | Upstream's Intelligence runtime |
| Thread menu: list, rename, archive, restore | Served by this API (`/api/copilotkit/threads*`, which also deletes a thread) | Intelligence |
| Main conversation (`/api/main-thread`) | Recorded in this database | Intelligence |
| Reload replays the conversation; reload mid-reply resumes it | Yes | Yes |
| Send while a reply is running | Held by the app (`409 agent_thread_locked`) | Held by the app (`AgentThreadLockedError`) |
| Thread list updates live on other devices | No: refreshes when the menu opens | Yes |
| `GET /api/workspace` → `runtime.threads` | `"local"` | `"intelligence"` |

### Moving from CopilotKit Intelligence

Remove `CPK_INTELLIGENCE_API_KEY` (or leave it blank) and restart the API. **Cloud threads are not imported automatically.** They stay in Intelligence and reappear if you set the key again. In local mode the main conversation keeps its id but starts empty, and new conversations are saved locally. Conversations saved locally are likewise never uploaded to Intelligence.

### What still leaves your server

Local mode removes the hosted chat layer. These are separate and work as upstream:

- Model calls go to the provider you configure.
- Public web search uses Parallel's keyless Search MCP by default; set `WEB_SEARCH_ENABLED=false` to turn it off.
- The CopilotKit SDK sends runtime telemetry by default; set `COPILOTKIT_TELEMETRY_DISABLED=true` or `DO_NOT_TRACK=1` to opt out ([details](docs/TELEMETRY.md)).
- Gmail, Calendar and the E2B cloud desktop, only if you enable them.

### Known limits

- **No cross-device live thread metadata sync.** Another device's thread list refreshes when its menu opens, not live.
- **Single-instance run lock.** Run one API process. A reply resumes live only from the API process that runs it; a reload served by another process shows the reply's progress so far, then ends.
- A message held because another device was replying is sent later with this device's copy of the conversation, so the model does not see the other device's turn (the saved history is in order, and a reload shows it).
- Memories are not served in local mode; automatic thread names are off in both modes, as upstream.

## How it works

Without a key, the CopilotKit runtime runs in SSE mode on OpenMuse's own `AgentRunner`, backed by the app's database. The API serves the thread routes itself, refuses a second run on a busy thread with `409` before any stream starts, recovers replies interrupted by a crash, and can expire old history. Architecture and upstream merging: [docs/STANDALONE.md](docs/STANDALONE.md). Configuration, routes, schema and validation: [docs/STANDALONE-THREADS.md](docs/STANDALONE-THREADS.md).

## Why not just patch the config

The upstream runtime has no local fallback: without the hosted service, opening the chat fails with "Main conversation is unavailable" and every message fails with "Failed to initialize thread". Switching the runtime to SSE mode requires a thread store of its own, which is what this fork adds.

## Relationship to upstream

MIT, like upstream. Changes are kept small and marked (`// Standalone:` comments, new logic in `apps/server/src/standalone/`), so the fork can keep merging upstream. Upstream is discussing the same need in [issue #73](https://github.com/CopilotKit/openmuse/issues/73), with proposals in [#94](https://github.com/CopilotKit/openmuse/pull/94) and [#166](https://github.com/CopilotKit/openmuse/pull/166). If upstream adds a first-party local thread store, this fork will adopt it.

CopilotKit Intelligence is a separate service and is not part of this repository or its MIT license.

## License

[MIT](LICENSE), Copyright (c) 2026 OpenMuse contributors.

---

## English summary

**OpenMuse Standalone: runs entirely on your own server, no third-party chat cloud required.**

Upstream OpenMuse stores its chat layer in the CopilotKit Intelligence hosted service: if it goes down, you cannot talk to your agent; conversation text also lives on someone else’s servers. This fork brings the chat layer back under your control (Postgres stores threads, the server streams replies to the browser via SSE). All other features remain consistent with upstream and continue to track upstream. When `CPK_INTELLIGENCE_API_KEY` is set, behavior is identical to upstream.

**Status**: v0.1.0, released 2026-10-11, alpha (same as upstream). Based on upstream `main` at `1ac68f3` (2026-10-06). See the full upstream guide at [docs/UPSTREAM-README.md](docs/UPSTREAM-README.md).

### Quick start (no key required)

Requires Node 24 LTS and pnpm 11.19.0; the sample workspace does not need a model, Google account, Docker, or Intelligence key.

```sh
git clone https://github.com/caspianchan31/openmuse-standalone.git openmuse
cd openmuse
pnpm install --frozen-lockfile
cp .env.example .env   # do not set CPK_INTELLIGENCE_API_KEY
pnpm dev               # API: http://localhost:8787
pnpm dev:web           # in another terminal, app: http://localhost:8081
```

Production: `pnpm build:server && pnpm start`; build the web app with `pnpm build:web` (set `EXPO_PUBLIC_API_URL` during build). A server exposed to the public needs live mode (`WORKSPACE_MODE=live`, `OPENMUSE_ACCESS_KEY`, `TOKEN_ENCRYPTION_KEY`) and model configuration; see the upstream guide.

### Environment variables

- `CPK_INTELLIGENCE_API_KEY`: leave unset or blank for **local mode**, where conversations live in this server’s database; when set, uses upstream Intelligence mode with unchanged behavior. A wrong key reports an error and does not fall back to local mode.
- `DATABASE_URL`: unset uses embedded PGlite (`DATA_DIR/postgres`); when set, connects to that Postgres.
- `DATA_DIR`: defaults to `.openmuse`; stores database, files, and signing keys; back it up yourself.
- `CHAT_RETENTION_DAYS`: local mode only; deletes completed replies older than this many days (integer 1–36500); unset keeps them forever.

### PGlite vs Postgres

- **PGlite (default)**: no installation needed; the database can only be opened by one process, so the task worker runs in the API process. Replies interrupted by a crash recover immediately on API restart.
- **Postgres**: recommended for long-term use; allows a separate task worker to share it. Replies interrupted by a crash recover after the lock expires, about 30–45 seconds. For step-by-step `DATABASE_URL` setup, see [docs/POSTGRES.md](docs/POSTGRES.md).

### With and without the key

Without key: conversations, thread menu (list, rename, archive, restore), and main conversation are all served by this server (thread deletion uses `DELETE /api/copilotkit/threads/:id`); refresh replays the conversation, and refreshing mid-reply resumes playback; sending a message while a reply is in progress returns `409 agent_thread_locked`, and the app stages the message. With key: everything goes through Intelligence, same as upstream, with cross-device real-time thread lists.

### Migrating from the cloud

Remove `CPK_INTELLIGENCE_API_KEY` and restart. **Existing cloud threads are not imported automatically**; they remain in Intelligence and reappear if you set the key again. In local mode the main conversation id stays the same but starts blank. Conversations saved locally are not uploaded to Intelligence.

### Data that still leaves the server

Model calls (sent to the model provider you configure); public web search defaults to Parallel (`WEB_SEARCH_ENABLED=false` to disable); CopilotKit SDK telemetry is enabled by default (`COPILOTKIT_TELEMETRY_DISABLED=true` or `DO_NOT_TRACK=1` to disable); Gmail, Calendar, and E2B cloud desktop are used only when you enable them.

### Known limitations

- **No cross-device real-time thread metadata sync**: other devices refresh the thread list when opening the menu.
- **Single-instance run lock**: run only one API process; replies can only resume live from the process running them.
- A message staged because another device was replying will be sent later with this device’s conversation copy; the model won’t see that turn from the other device (saved history order is correct, visible on refresh).
- Local mode does not provide Memories; neither mode auto-names threads (same as upstream).

For architecture and how to track upstream, see [docs/STANDALONE.zh-CN.md](docs/STANDALONE.zh-CN.md) (English original: [docs/STANDALONE.md](docs/STANDALONE.md)). MIT licensed, same as upstream; CopilotKit Intelligence is a separate service, not within this repository or its MIT license scope.
