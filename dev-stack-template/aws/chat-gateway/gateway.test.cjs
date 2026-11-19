"use strict";

const assert = require("node:assert/strict");
const { Writable } = require("node:stream");
const { finished } = require("node:stream/promises");
const test = require("node:test");
const { createHandler, parseRequest } = require("./gateway.cjs");

function event(body = {}) {
  return {
    httpMethod: "POST",
    resource: "/v1/chat/completions",
    body: JSON.stringify({
      model: "private-coder",
      messages: [{ role: "user", content: "Call status for the sample." }],
      ...body,
    }),
  };
}

async function run(input, { reserve, invoke, invokeFree }) {
  let status;
  let contentType;
  let route;
  let payload = "";
  const stream = new Writable({
    write(chunk, encoding, done) {
      payload += chunk.toString();
      done();
    },
  });
  const handler = createHandler({
    reserve,
    invoke,
    invokeFree,
    startResponse(raw, responseStatus, responseType, selectedRoute) {
      status = responseStatus;
      contentType = responseType;
      route = selectedRoute;
      return raw;
    },
  });
  await handler(input, stream);
  await finished(stream);
  return { status, contentType, route, payload };
}

test("forces the Sydney model and clamps the output limit", () => {
  const { request } = parseRequest(event({ max_completion_tokens: 9000 }));
  assert.equal(request.model, "qwen.qwen3-coder-next");
  assert.equal(request.max_tokens, 2048);
  assert.equal(request.max_completion_tokens, undefined);
});

test("rejects unapproved models, images, and requests above the size limit before reserving", async () => {
  for (const input of [
    event({ model: "external" }),
    event({ messages: [{ role: "user", content: [{ type: "image_url" }] }] }),
    event({ messages: [{ role: "user", content: "x".repeat(65536) }] }),
  ]) {
    const result = await run(input, {
      reserve: () => assert.fail("unexpected reservation"),
      invoke: () => assert.fail("unexpected invocation"),
    });
    assert.equal(result.status, 400);
  }
});

test("stops when the monthly limit or usage store prevents a reservation", async () => {
  for (const [reserve, status] of [
    [() => false, 429],
    [() => { throw new Error("ledger detail"); }, 503],
  ]) {
    const result = await run(event(), { reserve, invoke: () => assert.fail("unexpected invocation") });
    assert.equal(result.status, status);
    assert.doesNotMatch(result.payload, /ledger detail/);
  }
});

test("passes through streamed tool calls after reserving usage", async () => {
  const sse = 'data: {"choices":[{"delta":{"tool_calls":[{"function":{"name":"status"}}]}}]}\n\ndata: [DONE]\n\n';
  let reserved = false;
  const result = await run(event({ stream: true }), {
    reserve() { reserved = true; return true; },
    invoke(request) {
      assert.equal(reserved, true);
      assert.equal(request.stream, true);
      return new Response(sse, { headers: { "content-type": "text/event-stream" } });
    },
  });
  assert.equal(result.status, 200);
  assert.equal(result.contentType, "text/event-stream");
  assert.equal(result.payload, sse);
});

test("converts upstream throttling to a safe response", async () => {
  const result = await run(event({ stream: true }), {
    reserve: () => true,
    invoke: () => new Response("private upstream details", { status: 429 }),
  });
  assert.equal(result.status, 429);
  assert.doesNotMatch(result.payload, /private upstream details/);
});

test("private requests keep the Bedrock 429 even when free-auto is configured", async () => {
  let freeCalls = 0;
  const result = await run(event(), {
    reserve: () => true,
    invoke: () => new Response("quota", { status: 429 }),
    invokeFree: () => { freeCalls++; },
  });
  assert.equal(result.status, 429);
  assert.equal(freeCalls, 0);
});

test("explicit public route falls back to a zero-priced OpenRouter stream on Bedrock 429", async () => {
  const sse = 'data: {"choices":[{"delta":{"tool_calls":[{"function":{"name":"status"}}]}}]}\n\ndata: [DONE]\n\n';
  let reservations = 0;
  let primarySignal;
  const result = await run(event({
    model: "private-coder-public", stream: true,
    tools: [{ type: "function", function: { name: "status" } }],
  }), {
    reserve() { reservations++; return true; },
    invoke(body, signal) {
      assert.equal(body.model, "qwen.qwen3-coder-next");
      primarySignal = signal;
      return new Response("quota", { status: 429 });
    },
    invokeFree(body, signal) {
      assert.equal(signal, primarySignal);
      assert.equal(body.model, "openrouter/free");
      assert.equal(body.tools[0].function.name, "status");
      assert.deepEqual(body.provider, {
        require_parameters: true,
        max_price: { prompt: 0, completion: 0, request: 0 },
      });
      return new Response(sse, { headers: { "content-type": "text/event-stream" } });
    },
  });
  assert.equal(reservations, 1);
  assert.equal(result.status, 200);
  assert.equal(result.route, "free-auto");
  assert.equal(result.payload, sse);
});

test("public route requires configuration and preserves Bedrock success or authorization errors", async () => {
  const input = event({ model: "private-coder-public" });
  let reservations = 0;
  const reserve = () => { reservations++; return true; };
  const off = await run(input, { reserve, invoke: () => assert.fail("Bedrock called while disabled") });
  assert.equal(off.status, 503);
  assert.equal(reservations, 0);
  let freeCalls = 0;
  for (const status of [200, 403]) {
    const result = await run(input, {
      reserve,
      invoke: () => new Response("{}", { status, headers: { "content-type": "application/json" } }),
      invokeFree: () => { freeCalls++; },
    });
    assert.equal(result.status, status === 200 ? 200 : 502);
  }
  assert.equal(freeCalls, 0);
});
