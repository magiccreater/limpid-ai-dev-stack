"use strict";

const { Readable } = require("node:stream");
const { pipeline } = require("node:stream/promises");

const REGION = "ap-southeast-2";
const HOST = "bedrock-runtime.ap-southeast-2.amazonaws.com";
const PATH = "/openai/v1/chat/completions";
const MODEL = "qwen.qwen3-coder-next";
const ROUTE = "/v1/chat/completions";
const REQUEST_BYTES = 65536;
const OUTPUT_TOKENS = 2048;
const INPUT_KEYS = new Set([
  "model", "messages", "stream", "max_tokens", "max_completion_tokens",
  "temperature", "top_p", "tools", "tool_choice", "stream_options",
]);

function parseRequest(event) {
  if (event.isBase64Encoded || typeof event.body !== "string" ||
      Buffer.byteLength(event.body) > REQUEST_BYTES) {
    throw new Error("Expected a JSON request of at most 64 KiB.");
  }
  const body = JSON.parse(event.body);
  if (!body || typeof body !== "object" || Array.isArray(body) ||
      Object.keys(body).some(key => !INPUT_KEYS.has(key))) {
    throw new Error("Unsupported chat completion fields.");
  }
  if (body.model !== "private-coder" && body.model !== MODEL) {
    throw new Error("Select private-coder for this gateway.");
  }
  if (!Array.isArray(body.messages) || !body.messages.length ||
      body.messages.some(message => !message || typeof message !== "object" ||
        !["system", "user", "assistant", "tool"].includes(message.role) ||
        !(typeof message.content === "string" ||
          (message.role === "assistant" && message.content == null &&
            Array.isArray(message.tool_calls))))) {
    throw new Error("Only text messages and function tool calls are supported.");
  }
  if (body.tools !== undefined && (!Array.isArray(body.tools) ||
      body.tools.some(tool => !tool || tool.type !== "function" ||
        typeof tool.function?.name !== "string"))) {
    throw new Error("Only function tools are supported.");
  }
  const maxTokens = body.max_completion_tokens ?? body.max_tokens ?? OUTPUT_TOKENS;
  if (!Number.isInteger(maxTokens) || maxTokens < 1 ||
      (body.stream !== undefined && typeof body.stream !== "boolean")) {
    throw new Error("Invalid output limit or streaming mode.");
  }
  const { max_completion_tokens, ...request } = body;
  return {
    ...request,
    model: MODEL,
    max_tokens: Math.min(maxTokens, OUTPUT_TOKENS),
  };
}

let bedrock;
async function invokeBedrock(body, signal) {
  const { BedrockRuntimeClient } = require("@aws-sdk/client-bedrock-runtime");
  bedrock ??= new BedrockRuntimeClient({ region: REGION });
  const signer = await bedrock.config.signer();
  const signed = await signer.sign({
    protocol: "https:",
    hostname: HOST,
    method: "POST",
    path: PATH,
    headers: { host: HOST, "content-type": "application/json" },
    body: JSON.stringify(body),
  }, { signingRegion: REGION, signingService: "bedrock" });
  return fetch("https://" + HOST + PATH, {
    method: signed.method,
    headers: signed.headers,
    body: signed.body,
    signal,
    redirect: "error",
  });
}

let dynamodb;
async function reserveCall() {
  const { DynamoDBClient, UpdateItemCommand } = require("@aws-sdk/client-dynamodb");
  dynamodb ??= new DynamoDBClient({ region: REGION, maxAttempts: 1 });
  try {
    await dynamodb.send(new UpdateItemCommand({
      TableName: process.env.USAGE_TABLE,
      Key: { month: { S: new Date().toISOString().slice(0, 7) } },
      UpdateExpression: "ADD calls :one",
      ConditionExpression: "attribute_not_exists(calls) OR calls < :limit",
      ExpressionAttributeValues: {
        ":one": { N: "1" },
        ":limit": { N: process.env.MONTHLY_REQUESTS },
      },
    }), { abortSignal: AbortSignal.timeout(3000) });
    return true;
  } catch (error) {
    if (error.name === "ConditionalCheckFailedException") return false;
    throw error;
  }
}

function createHandler({ reserve, invoke, startResponse }) {
  return async (event, rawStream) => {
    const reject = (status, message) => {
      const out = startResponse(rawStream, status, "application/json");
      out.end(JSON.stringify({ error: { message } }));
    };
    if (event.httpMethod !== "POST" || event.resource !== ROUTE) {
      return reject(404, "Unknown gateway route.");
    }
    let request;
    try {
      request = parseRequest(event);
    } catch (error) {
      return reject(400, error instanceof SyntaxError ? "Invalid JSON body." : error.message);
    }
    try {
      if (!await reserve()) return reject(429, "Monthly gateway request limit reached.");
    } catch {
      return reject(503, "Gateway usage accounting unavailable.");
    }

    let upstream;
    try {
      upstream = await invoke(request, AbortSignal.timeout(24000));
    } catch {
      return reject(502, "Sydney Bedrock is unavailable.");
    }
    const type = request.stream ? "text/event-stream" : "application/json";
    if (!upstream.ok || !upstream.body || !upstream.headers.get("content-type")?.startsWith(type)) {
      await upstream.body?.cancel().catch(() => {});
      if (upstream.status === 429) return reject(429, "Sydney Bedrock rejected the request due to its inference quota.");
      return reject(502, "Sydney Bedrock did not return a usable response.");
    }
    const out = startResponse(rawStream, 200, type);
    await pipeline(Readable.fromWeb(upstream.body), out);
  };
}

exports.createHandler = createHandler;
exports.parseRequest = parseRequest;
if (typeof awslambda !== "undefined") {
  exports.handler = awslambda.streamifyResponse(createHandler({
    reserve: reserveCall,
    invoke: invokeBedrock,
    startResponse: (stream, statusCode, contentType) => awslambda.HttpResponseStream.from(stream, {
      statusCode, headers: { "Content-Type": contentType, "Cache-Control": "no-store" },
    }),
  }));
}
