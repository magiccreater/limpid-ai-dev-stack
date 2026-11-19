# Sydney Bedrock chat gateway pilot

This profile gives an IDE or local relay an IAM-authenticated OpenAI Chat Completions endpoint. A Regional REST API Gateway streams responses from Lambda. Lambda forwards requests to Qwen3 Coder Next on the Sydney Bedrock runtime. The worker, its tools, and any repository files stay on the WSL machine. Send only approved, sanitized context.

The first route is `POST /v1/chat/completions`, with the `private-coder` model alias. It accepts text and function tools. The Codex WSL worker uses the Responses API, so wiring that worker needs a separately tested protocol adapter. The optional public route can fall back to OpenRouter free-auto.

## Check the project from WSL

Use an AWS CLI profile created with `aws login`. Verify the selected Region in AWS Settings under the project's **Additional info**. From this directory run:

```bash
python3 infra.py preflight --profile YOUR_PROFILE --account-id YOUR_PROJECT_ID
```

This read-only check confirms the project's identity and Free Plan, the Sydney model authorization, that Bedrock invocation logging is off, and the model's applied requests-per-minute and tokens-per-minute quotas. An authorized model can still reject every request with HTTP 429 if either quota is zero. Check the applied values in **Service Quotas > Amazon Bedrock** before deploying.

## Optional public fallback

The gateway's **free-auto** fallback calls [OpenRouter's Free Models Router](https://openrouter.ai/openrouter/free) as `openrouter/free`. It requires support for the requested parameters and sets the input, output, and per-request price limits to zero. OpenRouter free routes can be rate-limited and can have different data policies.

Choose the `private-coder-public` alias only for public or synthetic prompts, code, and tool outputs. Bedrock remains the first attempt. The gateway can switch to free-auto on an upstream quota error or transient failure before it sends any response bytes. `private-coder` routes only to Bedrock. The `X-Limpid-Route` response header identifies the backend that produced a successful response.

To enable it, create a **Standard SecureString** in Sydney using the AWS-managed SSM key. For a new parameter, run in WSL Bash with the selected project profile:

```bash
export AWS_PROFILE=YOUR_PROFILE AWS_REGION=ap-southeast-2
export OPENROUTER_PARAMETER=/limpid/chat-gateway/openrouter
read -rsp 'OpenRouter API key: ' OPENROUTER_KEY
printf '\n'
printf '%s' "$OPENROUTER_KEY" | aws ssm put-parameter \
  --name "$OPENROUTER_PARAMETER" --type SecureString --tier Standard \
  --key-id alias/aws/ssm --value file:///dev/stdin
unset OPENROUTER_KEY
```

The preflight checks the parameter metadata. CloudFormation records its name, and the Lambda role can read only that parameter. A project with zero Bedrock quota can pass preflight with a valid fallback parameter. Use `private-coder-public` for that pilot.

## Validate and deploy

Run these commands from WSL once preflight passes. Leave `OPENROUTER_PARAMETER` empty for a Bedrock-only deployment. The rendered template embeds the small gateway handler, so deployment needs no artifact bucket.

```bash
export AWS_PROFILE=YOUR_PROFILE AWS_REGION=ap-southeast-2
python3 infra.py preflight --profile "$AWS_PROFILE" --account-id YOUR_PROJECT_ID \
  --openrouter-parameter "${OPENROUTER_PARAMETER:-}" &&
  python3 infra.py render > /tmp/limpid-chat-gateway.json &&
  aws cloudformation validate-template --template-body file:///tmp/limpid-chat-gateway.json &&
  aws cloudformation deploy --template-file /tmp/limpid-chat-gateway.json \
    --stack-name limpid-chat-gateway --capabilities CAPABILITY_IAM \
    --parameter-overrides "OpenRouterKeyParameter=${OPENROUTER_PARAMETER:-}"
```

Use the stack's `BaseUrl` output for the client. Sign the HTTPS request with AWS SigV4 for service `execute-api` in `ap-southeast-2`. Use temporary credentials in the local relay. An IDE using a plain API key can connect through a local signing relay. The endpoint rejects invocations from outside the AWS project.

## Pilot limits

The gateway caps requests at 64 KiB and responses at 2,048 model tokens. It atomically reserves a call in DynamoDB before contacting Bedrock and stops if the usage store is unavailable. The default is 20 reservations per UTC calendar month, with a maximum of 50 per stack. Each accepted gateway request reserves one call, including failed attempts. A public request can make one Bedrock attempt and one OpenRouter fallback attempt. Manage overall usage in AWS Settings under **Billing**. The request cap and your AWS Budget measure different things. A dollar ceiling covering multiple services requires separate cost accounting.

No application logs include prompts, token bodies, credentials, or raw upstream errors. Model invocation logging can be changed at the project level, so verify it again before using private repository context. This pilot uses a single foundation model ARN in Sydney with no cross-Region Bedrock fallback.

From this directory, run the local gateway tests with Node 22:

```bash
node --test gateway.test.cjs
```
