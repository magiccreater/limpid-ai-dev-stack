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

async function run(input, { reserve, invoke }) {
  let status;
  let contentType;
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
    startResponse(raw, responseStatus, responseType) {
      status = responseStatus;
      contentType = responseType;
      return raw;
    },
  });
  await handler(input, stream);
  await finished(stream);
  return { status, contentType, payload };
}

test("forces the Sydney model and clamps the output limit", () => {
  const request = parseRequest(event({ max_completion_tokens: 9000 }));
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
