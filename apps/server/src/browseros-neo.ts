import { randomUUID } from "node:crypto";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { CallToolResultSchema } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";
import project from "../../../package.json" with { type: "json" };
import type { Config } from "./config.ts";

const timeoutMs = 45000;
const maxResponseBytes = 1024 * 1024;
const maxText = 30000;

function textResult(result: z.infer<typeof CallToolResultSchema>): string {
  if (result.isError) {
    const text = result.content.find((block) => block.type === "text");
    throw new Error(text?.type === "text" ? text.text.slice(0, 500) : "BrowserOS Neo tool failed");
  }
  const text = result.content.find((block) => block.type === "text");
  if (text?.type === "text") return text.text;
  if (result.structuredContent) return JSON.stringify(result.structuredContent);
  throw new Error("BrowserOS Neo returned no text result");
}

function parseJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return undefined;
  }
}

function extractUrl(text: string): string | undefined {
  const m = text.match(/https?:\/\/[^\s)"\]]+/i);
  return m?.[0];
}

function extractTitle(text: string): string | undefined {
  const patterns = [/^#\s+(.+)$/m, /title[:\s]+(.+)$/im, /^(.{8,120})$/m];
  for (const p of patterns) {
    const m = text.match(p);
    if (m?.[1]) return m[1].trim().slice(0, 300);
  }
  return undefined;
}

export class BrowserOSNeoService {
  constructor(private readonly config: Config) {}

  configured() {
    return Boolean(this.config.browserosNeoMcpUrl);
  }

  async observe(url: string, signal?: AbortSignal) {
    signal?.throwIfAborted();
    if (!this.config.browserosNeoMcpUrl) throw new Error("BrowserOS Neo MCP is not configured");
    const deadline = AbortSignal.timeout(timeoutMs);
    const requestSignal = signal ? AbortSignal.any([signal, deadline]) : deadline;
    const client = new Client({ name: project.name, version: project.version });
    const transport = new StreamableHTTPClientTransport(new URL(this.config.browserosNeoMcpUrl), {
      requestInit: { headers: { "User-Agent": `${project.name}/${project.version}` } },
      reconnectionOptions: {
        maxRetries: 0,
        initialReconnectionDelay: 1000,
        maxReconnectionDelay: 1000,
        reconnectionDelayGrowFactor: 1,
      },
      fetch: async (input, init) => {
        const response = await fetch(input, {
          ...init,
          redirect: "error",
          signal: init?.signal ? AbortSignal.any([requestSignal, init.signal]) : requestSignal,
        });
        if (!response.body) return response;
        let bytes = 0;
        const body = response.body.pipeThrough(
          new TransformStream<Uint8Array, Uint8Array>({
            transform(chunk, controller) {
              bytes += chunk.byteLength;
              if (bytes > maxResponseBytes) throw new Error("BrowserOS Neo response exceeded 1 MiB");
              controller.enqueue(chunk);
            },
          }),
        );
        return new Response(body, {
          status: response.status,
          statusText: response.statusText,
          headers: response.headers,
        });
      },
    });
    const options = { signal: requestSignal, timeout: timeoutMs };
    try {
      await client.connect(transport, options);
      const tools = await client.listTools(undefined, options);
      const names = new Set(tools.tools.map((t) => t.name));
      let sessionId = `neo:${randomUUID()}`;
      let finalUrl = url;
      let title = "";
      let text = "";

      const call = async (name: string, args: Record<string, unknown>) => {
        const result = await client.request(
          { method: "tools/call", params: { name, arguments: args } },
          CallToolResultSchema,
          options,
        );
        return textResult(result);
      };

      if (names.has("browseros-neo_navigate")) {
        // Open in existing/default context; Neo tools may require page id - prefer run fallback below on failure.
        const nav = await call("browseros-neo_navigate", { action: "url", url, page: 1 }).catch(() => "");
        if (nav) text = nav;
      }

      if (names.has("browseros-neo_tabs")) {
        const tabsText = await call("browseros-neo_tabs", { action: "new", url }).catch(() => "");
        const parsed = parseJson(tabsText);
        const obj = typeof parsed === "object" && parsed ? (parsed as Record<string, unknown>) : undefined;
        const page = typeof obj?.page === "number" ? obj.page : typeof obj?.pageId === "number" ? obj.pageId : undefined;
        if (page !== undefined) {
          sessionId = `neo:${page}`;
          if (names.has("browseros-neo_read")) {
            text = await call("browseros-neo_read", { page, format: "markdown" });
          } else if (names.has("browseros-neo_snapshot")) {
            text = await call("browseros-neo_snapshot", { page, mode: "interactive", depth: 12 });
          }
          if (names.has("browseros-neo_tabs")) {
            const list = await call("browseros-neo_tabs", { action: "list" }).catch(() => "");
            const m = list.match(new RegExp(`\\[${page}\\]\\s+(\\S+)\\s+\\(([^)]+)\\)`));
            if (m?.[1]) finalUrl = m[1];
            if (m?.[2]) title = m[2];
          }
        }
      }

      if (!text && names.has("browseros-neo_run")) {
        const code = `const p = await browser.open(${JSON.stringify(url)});\nawait p.waitForTime(1500);\nconst title = await p.evaluateInPage(() => document.title).catch(() => "");\nconst urlNow = await p.evaluateInPage(() => location.href).catch(() => ${JSON.stringify(url)});\nconst text = await p.read().catch(() => "");\nreturn { pageId: p.id, title: title?.value ?? title, url: urlNow?.value ?? urlNow, text: String(text).slice(0, ${maxText}) };`;
        const runText = await call("browseros-neo_run", { code, timeout: 30000, maxChars: 40000 });
        const parsed = parseJson(runText);
        const obj = typeof parsed === "object" && parsed ? (parsed as Record<string, unknown>) : undefined;
        const v = typeof obj?.value === "object" && obj.value ? (obj.value as Record<string, unknown>) : obj;
        if (typeof v?.pageId === "number") sessionId = `neo:${v.pageId}`;
        if (typeof v?.url === "string") finalUrl = v.url;
        if (typeof v?.title === "string") title = v.title;
        if (typeof v?.text === "string") text = v.text;
        if (!text) text = runText;
      }

      if (!text) throw new Error("BrowserOS Neo could not read the page");
      requestSignal.throwIfAborted();
      const clipped = text.slice(0, maxText);
      return {
        sessionId,
        url: extractUrl(finalUrl) ?? finalUrl,
        title: (title || extractTitle(clipped) || new URL(url).hostname).slice(0, 300),
        text: clipped,
        truncated: text.length > maxText,
        provider: "browseros-neo" as const,
      };
    } catch (error) {
      signal?.throwIfAborted();
      if (deadline.aborted) throw new Error("BrowserOS Neo timed out after 45 seconds");
      throw new Error(
        `BrowserOS Neo failed: ${error instanceof Error ? error.message.slice(0, 500) : "Unknown error"}`,
      );
    } finally {
      await client.close().catch(() => {});
    }
  }
}
