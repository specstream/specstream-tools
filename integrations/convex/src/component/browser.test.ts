/// <reference types="vite/client" />
import { afterEach, describe, expect, test, vi } from "vitest";
import { api } from "./_generated/api.js";
import { fakeSpecStream, initConvexTest } from "./setup.test.js";

// Browser sessions: open with an Idempotency-Key that holds across retries, steps,
// read, close, and the connect address only when asked for.

afterEach(() => {
  vi.unstubAllGlobals();
});

const SESSION = {
  id: "bs_1",
  status: "running",
  connect_url: "wss://browser.specstream.ai/bs_1?token=secret",
  live_url: "https://specstream.ai/live/bs_1",
  expires_at: "2026-11-13T17:00:00Z",
  timeout_s: 300,
  seconds: 0,
  actions: 0,
  charged_usd: 0,
  price: { per_second_usd: 0.0000277, per_action_usd: 0.001 },
};

describe("openBrowser", () => {
  test("sends the defaults and leaves the connect address out", async () => {
    const t = initConvexTest();
    const { calls } = fakeSpecStream({
      "POST /v1/browser/sessions": { status: 201, body: { data: SESSION } },
    });
    const session = await t.action(api.browser.openBrowser, {});
    expect(calls[0].body).toEqual({ timeout_s: 300, idle_timeout_s: 120, keep_alive: true });
    expect(calls[0].headers["Idempotency-Key"]).toMatch(/.+/);
    expect(session.sessionId).toBe("bs_1");
    expect(session.live_url).toBe(SESSION.live_url);
    expect(session.connect_url).toBeUndefined();
  });

  test("returns the connect address when asked and passes the options", async () => {
    const t = initConvexTest();
    const { calls } = fakeSpecStream({
      "POST /v1/browser/sessions": { status: 201, body: { data: SESSION } },
    });
    const session = await t.action(api.browser.openBrowser, {
      timeoutSeconds: 600,
      allowedDomains: ["example.com"],
      blockMedia: true,
      headless: false,
      includeConnectUrl: true,
      idempotencyKey: "job-7",
    });
    expect(session.connect_url).toBe(SESSION.connect_url);
    expect(calls[0].body).toMatchObject({
      timeout_s: 600,
      allowed_domains: ["example.com"],
      block_media: true,
      headless: false,
    });
    expect(calls[0].headers["Idempotency-Key"]).toBe("job-7");
  });

  test("a retried open sends the same key, so one browser opens", async () => {
    const t = initConvexTest();
    const { calls } = fakeSpecStream({
      "POST /v1/browser/sessions": (_call, index) =>
        index === 0
          ? { status: 503, body: { error: { code: "unavailable", message: "busy" } } }
          : { status: 201, body: { data: SESSION } },
    });
    await t.action(api.browser.openBrowser, {});
    expect(calls).toHaveLength(2);
    expect(calls[1].headers["Idempotency-Key"]).toBe(calls[0].headers["Idempotency-Key"]);
  });

  test("refuses a time limit out of range without a call", async () => {
    const t = initConvexTest();
    const { calls } = fakeSpecStream({});
    await expect(t.action(api.browser.openBrowser, { timeoutSeconds: 30 })).rejects.toThrow(
      /60 to 3600/,
    );
    expect(calls).toHaveLength(0);
  });
});

describe("browserStep", () => {
  test("sends the tool and its arguments and joins the text", async () => {
    const t = initConvexTest();
    const { calls } = fakeSpecStream({
      "POST /v1/browser/sessions/bs_1/actions": {
        body: {
          data: {
            result: [
              { type: "text", text: "Example Domain" },
              { type: "image", mime_type: "image/png", data: "AAAA" },
              { type: "text", text: "More information" },
            ],
            url: "https://example.com/",
            title: "Example Domain",
            price_usd: 0.001,
          },
        },
      },
    });
    const step = await t.action(api.browser.browserStep, {
      sessionId: "bs_1",
      tool: "browser_navigate",
      arguments: { url: "https://example.com", ignored: null },
    });
    expect(calls[0].body).toEqual({ tool: "browser_navigate", arguments: { url: "https://example.com" } });
    expect(step).toEqual({
      sessionId: "bs_1",
      text: "Example Domain\n\nMore information",
      images: [{ mime_type: "image/png", base64_chars: 4 }],
      url: "https://example.com/",
      title: "Example Domain",
      price_usd: 0.001,
    });
  });

  test("refuses a tool that is not a browser step", async () => {
    const t = initConvexTest();
    const { calls } = fakeSpecStream({});
    await expect(
      t.action(api.browser.browserStep, { sessionId: "bs_1", tool: "rm -rf" }),
    ).rejects.toThrow(/browser step name/);
    expect(calls).toHaveLength(0);
  });
});

describe("browserSession and closeBrowser", () => {
  test("read the session and release it", async () => {
    const t = initConvexTest();
    const { calls } = fakeSpecStream({
      "GET /v1/browser/sessions/bs_1": { body: { data: { ...SESSION, seconds: 12 } } },
      "POST /v1/browser/sessions/bs_1/release": {
        body: { data: { ...SESSION, status: "ended", ended_reason: "released" } },
      },
    });
    const read = await t.action(api.browser.browserSession, { sessionId: "bs_1" });
    expect(read.seconds).toBe(12);
    expect(read.connect_url).toBeUndefined();
    const closed = await t.action(api.browser.closeBrowser, { sessionId: " bs_1 " });
    expect(closed).toMatchObject({ sessionId: "bs_1", status: "ended", ended_reason: "released" });
    expect(calls.map((c) => `${c.method} ${c.path}`)).toEqual([
      "GET /v1/browser/sessions/bs_1",
      "POST /v1/browser/sessions/bs_1/release",
    ]);
  });
});
