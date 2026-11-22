import assert from "node:assert/strict";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { createApp } from "../apps/server/src/app.ts";
import { createStore } from "../apps/server/src/db.ts";
import type { ActionProposal } from "../packages/domain/src/index.ts";
import { modelFixture } from "./helpers/model.ts";

for (const scenario of [
  {
    name: "finish_task",
    arguments: { summary: "The requested work is complete." },
    status: "succeeded",
  },
  {
    name: "ask_user",
    sequence: [
      {
        name: "ask_user",
        arguments: {
          question: "Which date should I use?",
          suggestions: ["Use tomorrow", "Use next Monday", "Let me pick a date"],
        },
      },
      { name: "finish_task", arguments: { summary: "Completed using a reasonable assumption." } },
    ],
    status: "succeeded",
  },
  {
    name: "prepare_event",
    arguments: {
      title: "Sample walk",
      start: "2026-10-10T10:00:00-07:00",
      end: "2026-10-10T11:00:00-07:00",
    },
    status: "waiting_approval",
  },
  {
    name: "prepare_email",
    arguments: { to: ["friend@example.com"], subject: "Sample plan", body: "A walk tomorrow?" },
    status: "waiting_approval",
  },
]) {
  test(`${scenario.name} settles the task as expected`, async (t) => {
    const { requests } = await modelFixture(
      t,
      scenario.sequence
        ? (index) => scenario.sequence[index]
        : () => scenario,
      {
        // A provider failure after the outcome must not replace it with a failed task.
        errorStatus: (index) =>
          scenario.sequence ? undefined : index > 0 ? 503 : undefined,
      },
    );
    const directory = await mkdtemp(join(tmpdir(), "openmuse-model-outcome-"));
    const db = await createStore();
    const server = await createApp(db, {
      mode: "sample",
      port: 8787,
      host: "127.0.0.1",
      publicUrl: "http://localhost:8787",
      dataDir: directory,
      agentBackend: "model",
      model: "openai/fixture",
      intelligenceApiKey: "test-project-key-never-sent",
      googleRedirectUri: "http://localhost:8787/api/google/callback",
      allowedOrigins: [],
    });
    try {
      const task = await server.agent.createTask("owner", { prompt: "Make a sample plan" });
      await server.agent.worker.tick();
      const saved = await server.agent.getTask("owner", task.id);
      assert.equal(saved.status, scenario.status, saved.error ?? saved.question);
      assert.equal(
        requests.length,
        scenario.sequence ? scenario.sequence.length : 1,
        "the task should settle as expected without extra model loops",
      );
      if (scenario.status === "succeeded" && scenario.name === "finish_task")
        assert.equal(saved.result, scenario.arguments.summary);
      if (scenario.name === "ask_user") {
        const assumptions = Array.isArray(saved.state.assumptions) ? saved.state.assumptions : [];
        assert.ok(assumptions.length > 0, "ask_user should record an assumption");
        assert.match(saved.result ?? "", /Completed|assumption|available/i);
      }
      if (scenario.status === "waiting_input") {
        assert.equal(saved.question, scenario.arguments.question);
        assert.deepEqual(saved.suggestions, scenario.arguments.suggestions);
      }
      if (scenario.status === "waiting_approval") {
        assert.ok(saved.actionId);
        const proposal = await db.get<ActionProposal>("owner", "actions", saved.actionId);
        assert.equal(proposal?.status, "awaiting_review", "a model never approves the action");
      }
    } finally {
      await server.agent.stop();
      await db.close();
      await rm(directory, { recursive: true, force: true });
    }
  });
}
