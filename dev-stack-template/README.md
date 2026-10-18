# Dev Stack & Agent Playground

**Windows 11 + WSL2 + VS Code + Docker + LiteLLM + Amazon Bedrock (Sydney) + OpenRouter + OpenClaw**

One gateway on your laptop that gives every tool and agent the right model for the job:

- **Private models** on Amazon Bedrock in **Sydney** for client code, finances and personal
  documents. AWS says Bedrock does not store or log prompts, does not train on them, and does
  not share them with the model makers. Your data stays in Australia.
- **Open models** on OpenRouter, only from providers that keep no data, for public or
  non-sensitive work.
- Local document search (RAG), MySQL, OpenClaw chat channels (WhatsApp, Telegram) and example
  agents to build on.

No model runs on your laptop. It runs only the gateway, Docker and the agents, so WSL needs
about 8 GB of RAM and no GPU.

The example agents are starting points: each is a short script with one prompt. They have no
tools, memory or verification of their own. Treat them as templates, not products.

**Contents:**
[How it works](#how-it-works) ·
[Setup](#setup) ·
[Models](#models) ·
[Costs](#costs) ·
[Why Sydney](#why-sydney) ·
[Connect your tools](#connect-your-tools) ·
[Use from code](#use-from-code) ·
[Example agents](#example-agents) ·
[Commands](#commands) ·
[Upgrading](#upgrading) ·
[Troubleshooting](#troubleshooting) ·
[Security](#security) ·
[Files](#files)

---

## How it works

```
VS Code (Cline / Continue / Aider)   OpenClaw (WhatsApp, Telegram…)   example agents
                    \                         |                          /
                     ▼                        ▼                         ▼
              LiteLLM gateway  127.0.0.1:4000  (key required, daily budgets)
                 │                                     │
   PRIVATE: Amazon Bedrock, Sydney              OPEN: OpenRouter, zero data retention
   Qwen3 Coder Next · Qwen3 Coder 30B           DeepSeek V4 Flash · Qwen3 Coder Next · GLM 5.3
   Qwen3 235B · DeepSeek V3.2 · GLM 5           Claude Sonnet 5.5 (opt-in, capped)
   (falls back only within Bedrock)             (non-sensitive work only)

   Jev decisions (OpenRouter Decisions API) ← off unless JEV_ENABLED=1
```

Every tool talks to one OpenAI-compatible endpoint, `http://127.0.0.1:4000/v1`, and picks a
model by name. LiteLLM checks the key, sends the request to Bedrock or OpenRouter, retries or
falls back on errors, and counts spending.

| | Private (`private-*`) | Open (`open-*`, `cloud-reasoner`) |
|---|---|---|
| Runs on | Amazon Bedrock, Sydney (ap-southeast-2) | OpenRouter → a provider with zero data retention |
| Who sees prompts | AWS only; not stored, not used for training, not shared with model makers | OpenRouter + the provider; each promises not to keep data |
| Region | Pinned to Sydney in the config | Wherever the provider runs |
| If it fails | Falls back to another private model, never to OpenRouter | Returns the error |
| Use for | Client code, finances, personal documents, anything you'd mind leaking | Public data, research, drafts, open-source code |

Everything listens on `127.0.0.1`, so nothing is reachable from your network.

---

## Setup

You need Windows 11 with WSL2 (Ubuntu), an AWS account for the private models, and optionally
an OpenRouter key for the open models. Allow about 45 minutes the first time.

### 1. WSL settings

Copy `.wslconfig.example` to `C:\Users\<You>\.wslconfig`, then in PowerShell run
`wsl --shutdown`. It gives WSL 8 GB of RAM and keeps WSL's default networking, in which
Windows apps reach WSL services at `127.0.0.1`.

### 2. Install the stack

Inside Ubuntu (WSL2):

```bash
git clone https://github.com/magiccreater/limpid-ai-dev-stack
./limpid-ai-dev-stack/install_dev_stack.sh            # installs to ~/dev-stack
cd ~/dev-stack
```

The installer copies the stack to `~/dev-stack` (or `--target DIR`), creates `.env` with random
secrets (mode 600), and makes a git repo so you can see your own changes. It is safe to re-run
(see [Upgrading](#upgrading)).

### 3. System tools

```bash
./setup.sh && source ~/.bashrc      # first time only; safe to re-run
```

It installs, with pinned versions: build tools, mise (runtime manager), Node 24, Python 3.12,
uv, just, LiteLLM 1.102.2, PHP 8.3 + Composer (checksum-verified) and Docker. It stops at the
first error and tells you the line, rather than carrying on half-installed.

### 4. Private models: Amazon Bedrock (about 15 minutes)

Follow **[aws/README.md](aws/README.md)**. In short:

1. Create an AWS account (needs a card; new accounts get free-plan credit) and switch the
   console to **Asia Pacific (Sydney)**.
2. In the Bedrock playground, send "hi" to each of the five models once.
3. Deploy `aws/bedrock-access.yaml` in CloudFormation. It creates the user `devstack-bedrock`,
   which can call only those five models and only in Sydney, plus a monthly budget that
   emails you at 50%, 100% and forecast 100%.
4. Create an access key for that user and put it in `.env`:

```
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
```

Never put root or admin keys here. An AWS Builder ID (the Kiro / Amazon Q login) is a
different account type and cannot use Bedrock.

### 5. Open models: OpenRouter (optional)

1. Create a key at https://openrouter.ai/settings/keys **with a credit limit**. That limit is
   the hard stop on OpenRouter spending.
2. Turn on **Zero Data Retention** for all models at https://openrouter.ai/settings/privacy.
   The config also asks for it on every request, but the account setting covers everything.
3. Put it in `.env` as `OPENROUTER_API_KEY=...`.

Skip this step to run with private models only.

### 6. Start and check

```bash
just litellm            # terminal 1: the gateway on 127.0.0.1:4000
just doctor             # terminal 2: env, AWS keys, gateway, exposed ports
just check-models       # one tiny answer + one tool call per private model (a fraction of a cent)
```

Each `check-models` line should read `answer ok` and `tools ok`. `tools NOT USED` means that
model answered without calling the tool: fine for chat, weaker for agents. A `FAIL` line names
the error; see [Troubleshooting](#troubleshooting).

### 7. Connect your tools

```bash
just client-configs     # writes ~/.continue/config.yaml and ~/.openclaw/openclaw.json
```

Then see [Connect your tools](#connect-your-tools) for Cline, Aider and AnythingLLM.

### What `.env` holds

| Variable | Set by | Purpose |
|---|---|---|
| `LITELLM_MASTER_KEY` | generated | key every client uses for the gateway |
| `LITELLM_BASE_URL` | default | `http://127.0.0.1:4000/v1` |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | you (step 4) | the limited Bedrock user |
| `OPENROUTER_API_KEY` | you (step 5) | open models; empty = private only |
| `ALLOW_FRONTIER` | default `0` | `1` lets code use paid Claude (`cloud-reasoner`) |
| `JEV_ENABLED` | default `0` | `1` sends agent requests to Jev for routing (see below) |
| `MYSQL_*`, `ANYTHINGLLM_JWT_SECRET` | generated | local MySQL and RAG |
| `OPENCLAW_GATEWAY_PORT` | default | OpenClaw |

`just env` creates or upgrades `.env`: it adds missing keys and replaces old published
defaults. It never removes or changes your own values.

---

## Models

All prices are per million tokens (input / output), on-demand, checked on AWS's pricing page
and openrouter.ai in October 2026.

| Name | Where | Model | Use for | Price in / out |
|---|---|---|---|---|
| `private-coder` | Bedrock Sydney | Qwen3 Coder Next | coding and agents (**default**) | $0.515 / $1.236 |
| `private-coder-lite` | Bedrock Sydney | Qwen3 Coder 30B A3B | cheaper coding; fallback for `private-coder` | $0.155 / $0.618 |
| `private-general` | Bedrock Sydney | Qwen3 235B A22B 2507 | writing, summaries, chat | $0.227 / $0.906 |
| `private-reasoner` | Bedrock Sydney | DeepSeek V3.2 | harder reasoning | $0.639 / $1.906 |
| `private-glm` | Bedrock Sydney | GLM 5 | hardest private work | $1.03 / $3.30 |
| `open-deepseek` | OpenRouter | DeepSeek V4 Flash | public data, drafts | ~$0.14 / $1.28 |
| `open-qwen` | OpenRouter | Qwen3 Coder Next | public or open-source code | ~$0.12 / $0.80 |
| `open-glm` | OpenRouter | GLM 5.3 | strongest open model; always reasons, so many output tokens | up to $1.68 / $5.28 |
| `cloud-reasoner` | OpenRouter | Claude Sonnet 5.5 | rarely; needs `ALLOW_FRONTIER=1`; capped at $1/day | $2 / $10 |

`local-coder` and `hybrid-agent` (names from earlier versions) are aliases of `private-coder`.
OpenRouter prices vary by provider; the config counts them at or above list price so the daily
cap errs on the safe side.

### Which one to pick

- **Client or personal data?** Always a `private-*` model.
- **Everyday coding and agent steps:** `private-coder`. For lots of small, routine steps,
  `private-coder-lite` costs about a third as much.
- **Writing, summarising, answering questions:** `private-general` (the cheapest private model
  per output token).
- **A hard bug, a design decision, multi-step reasoning:** `private-reasoner`, then
  `private-glm` if that is not enough.
- **Public material** (news, open-source code, research): `open-deepseek` for cheap,
  `open-glm` for the best answer.
- **Interactive pair-programming with Claude:** use Claude Code with your subscription, not
  `cloud-reasoner`, which charges per token.

### Fallbacks

| If this fails | LiteLLM tries |
|---|---|
| `private-coder` (and its aliases) | `private-coder-lite` |
| `private-general` | `private-coder` |
| `private-reasoner` | `private-general` |
| `private-glm` | `private-reasoner` |

Fallbacks react to errors (model down, throttled, timeout), not to weak answers. A private
model never falls back to OpenRouter: if every private model fails, you get the error.

### Why some newer models are not private

- **GLM 5.3** is on Bedrock only through a *global* profile, which may process requests in
  any of 26 regions worldwide, and only for accounts AWS approves. That breaks "data stays in
  Australia", so it is offered as `open-glm` via OpenRouter instead. GLM 5 runs in Sydney.
- **DeepSeek V4** is not on AWS's Bedrock model list or pricing page (V3.2 is the newest in
  Sydney). It is available as `open-deepseek` (V4 Flash) via OpenRouter.

To see what your account can use in Sydney (needs the AWS CLI):

```bash
aws bedrock list-foundation-models --region ap-southeast-2 \
  --query "modelSummaries[].[providerName,modelId]" --output table
```

### Adding or swapping a private model

1. Check it is offered **in-region** in ap-southeast-2 on its Bedrock model card (not only
   through a global profile).
2. Add or change it in `litellm_config.yaml` (`bedrock/converse/<model-id>`,
   `aws_region_name: ap-southeast-2`, Sydney prices in `model_info`).
3. Add the same model ID to the `Resource` list in `aws/bedrock-access.yaml` and update the
   CloudFormation stack.
4. Restart LiteLLM and run `just check-models <name>`.

The tests (`just test`) fail if the config and the IAM policy disagree, or if a private model
points outside Sydney or falls back to OpenRouter.

---

## Costs

**Example month**, fairly heavy use of `private-coder` (20 million tokens in, 2 million out):
about **$12.80** in Sydney. The same work on `private-coder-lite` is about $4.30, and on
`private-general` about $6.35. Light use is a few dollars. New AWS accounts start with
free-plan credit that covers months of this.

**Money guards, strongest first:**
1. The **AWS Budget** email (from `aws/bedrock-access.yaml`) and the **credit limit on your
   OpenRouter key**.
2. **LiteLLM daily caps:** $3/day for Bedrock and $3/day for OpenRouter. Above that, requests
   get HTTP 429 "crossed budget". They are kept in memory, so they reset when LiteLLM restarts.
   Change them under `provider_budget_config` in `litellm_config.yaml`.
3. **No paid Claude** in any fallback chain, and `cloud-reasoner` has its own $1/day cap.

**Ways to spend less:**
- Use `private-coder-lite` or `private-general` for routine steps; keep the bigger models for
  the hard parts.
- Keep prompts short: agents that resend whole files on every step pay for them every time.
- **Batch and Flex** on Bedrock cost 50% less than on-demand, for models that support them,
  in exchange for slower answers. They suit overnight jobs (summarising or classifying many
  documents), not interactive coding. This stack does not use them yet.

---

## Why Sydney

Sydney costs about **3% more** than the US regions (for example `private-coder` is $0.515
in Sydney and $0.50 in the US), which is under 40 cents in the example month above. In return:

- **Privacy:** prompts and answers stay in Australia.
- **Speed:** typical round trips from Auckland, which you pay once or twice per request:

| Region | Round trip | Extra wait per request |
|---|---|---|
| Sydney (ap-southeast-2) | ~25–35 ms | ~0.03–0.07 s |
| US West (us-west-2) | ~130–150 ms | ~0.15–0.3 s |
| US East (us-east-1) | ~200–230 ms | ~0.2–0.45 s |

The model's own thinking (0.5–3 s before the first word, longer for reasoning models) is far
larger, so a single chat feels about the same. Agents that make 30 calls per task save several
seconds per task in Sydney. Streaming speed after the first word depends on the model, not the
distance.

The US makes sense only for a model Sydney does not have, and only for non-sensitive work.
If you later run the gateway on a cloud server, put that server in Sydney too.

To measure your own connection:

```bash
for r in ap-southeast-2 us-west-2 us-east-1; do
  curl -o /dev/null -s -w "$r  connect %{time_connect}s  tls %{time_appconnect}s\n" \
    https://bedrock-runtime.$r.amazonaws.com/
done
```

---

## Connect your tools

Every tool uses the same three values:

| Setting | Value |
|---|---|
| Base URL | `http://127.0.0.1:4000/v1` (from Windows or WSL) |
| API key | `LITELLM_MASTER_KEY` from `.env` |
| Model | a name from the [Models](#models) table, e.g. `private-coder` |

- **Continue (VS Code):** `just client-configs` writes `~/.continue/config.yaml` with
  `private-coder`, `private-reasoner` and `open-deepseek`. No autocomplete model is set,
  because it would send a request on every pause while typing.
- **Cline (VS Code):** provider *OpenAI Compatible*, the base URL and key above, model ID
  `private-coder`.
- **Aider:**
  ```bash
  aider --openai-api-base http://127.0.0.1:4000/v1 --openai-api-key "$LITELLM_MASTER_KEY" \
        --model openai/private-coder
  ```
- **OpenClaw:** `just client-configs` writes `~/.openclaw/openclaw.json`. Its agents default
  to `private-general` with `private-coder` as fallback, because inbound WhatsApp or Telegram
  messages can contain private data. Install with `./scripts/setup_openclaw.sh`. Keep DM
  policies on pairing or an allowlist.
- **AnythingLLM (RAG):** `just rag`, then in its settings choose *Generic OpenAI* with base
  URL `http://host.docker.internal:4000/v1`, model `private-general` and your key. Whether a
  container can reach `127.0.0.1` on the host depends on your Docker setup; test it in
  AnythingLLM's settings and do not rebind LiteLLM to `0.0.0.0` to make it work.

If a client config already exists, `just client-configs` keeps yours and writes the new
version next to it as `*.dev-stack-new` for you to merge.

---

## Use from code

The shared package (`shared/devstack_shared`) gives agents a LangChain chat model by **tier**:

```python
from devstack_shared.llm import get_llm

llm = get_llm()                       # "private": private-coder (default)
llm = get_llm("private-general")      # private-general
llm = get_llm("private-reasoner")     # private-reasoner
llm = get_llm("open")                 # open-deepseek: public data only
llm = get_llm("frontier")             # cloud-reasoner: refused unless ALLOW_FRONTIER=1

reply = await llm.ainvoke("Summarise this contract clause: ...")
print(reply.content)
```

`"local"` and `"hybrid"` from earlier versions still work and mean `"private"`. Only `"open"`
and `"frontier"` leave Bedrock.

### Jev routing (optional)

`devstack_shared.jev_client.route_request(text)` asks TypeSafe Jev which agent fits a request
and how complex it is; the coding agent uses the complexity to choose between `private-coder`
and `private-reasoner`. Jev sends the request text to OpenRouter, so it is **off by default**
(`JEV_ENABLED=0`). When it is off, has no key or fails, agents use local defaults and keep
working. Turn it on only for agents that never see client or private data.

---

## Example agents

```bash
just agent <name> [args]     # coding | scraper | social | trend | stock | mentor | study | gatekeeper
```

| Agent | Path | Model | Does |
|---|---|---|---|
| Coding | `examples/coding-agent` | `private-coder` (or `private-reasoner` when Jev rates it complex) | answers in text; does not edit files or run tests |
| Scraper | `examples/scraper-agent` | `private-coder` | Playwright page fetch + LLM extraction to JSON |
| WhatsApp | `examples/whatsapp-agent` | via OpenClaw | OpenClaw skill for a support bot |
| Social poster | `examples/social-poster` | `private-coder` | drafts posts |
| Trend | `examples/trend-agent` | `open-deepseek` | research digest of public trends |
| Stock | `examples/stock-agent` | `private-coder` | yfinance data + an educational note (not financial advice) |
| Mentor | `examples/mentor-agent` | `private-coder` | coaching replies |
| Study planner | `examples/study-planner` | `private-coder` | weekly plan as JSON |
| Gatekeeper | `examples/gatekeeper-agent` | `private-coder` | regex scan of your own code for XSS/SQLi/secrets + defensive advice |

Each agent is its own uv project that depends on the shared package (no `sys.path` tricks).
Copy one to start a new agent.

---

## Commands

```bash
just env              # create/upgrade .env (random secrets; replaces published defaults)
just litellm          # gateway on 127.0.0.1:4000 (refuses to start without a real key)
just doctor           # env, AWS keys, gateway, exposed ports
just check-models     # each private model: answer + tool call (or: just check-models open-glm ...)
just client-configs   # Continue + OpenClaw configs with your key
just mysql            # MySQL on 127.0.0.1:3306
just rag              # AnythingLLM on 127.0.0.1:3001
just openclaw         # OpenClaw gateway
just agent <name>     # run an example agent
just status           # which ports are open, and on which address
just test             # unit tests + LiteLLM gateway tests
```

---

## Upgrading

Pull the repo and run the installer again:

```bash
cd ~/limpid-ai-dev-stack && git pull
./install_dev_stack.sh --dry-run     # see what would change
./install_dev_stack.sh
```

- New files are added; identical files are left alone.
- Changed files are backed up to `.dev-stack-backup/<time>/`, then replaced.
- `litellm_config.yaml` is yours to edit: if you changed it, the new version is written next to
  it as `litellm_config.yaml.dev-stack-new` to merge. If you never edited it, it is upgraded.
- Files from older versions (for example the old local-model scripts) are moved to the backup.
- `.env` gets any new keys; your values are kept.
- Your folder, data and git history are never deleted.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `just litellm` says the key is missing or a published default | `.env` not created or old | `just env` |
| `AccessDeniedException ... not authorized to perform: bedrock:InvokeModel` | model not in the IAM policy, or wrong keys | check `aws/bedrock-access.yaml` lists the model; check the keys in `.env` |
| `AccessDeniedException ... don't have access to the model` | model never enabled on the account | send "hi" to it once in the Bedrock playground (Sydney) as the admin user |
| `ValidationException ... model identifier is invalid` | model ID wrong or not offered in Sydney | check the Bedrock model card; see [Adding or swapping a private model](#adding-or-swapping-a-private-model) |
| `ThrottlingException` or 429 from Bedrock | per-minute quota in Sydney | wait, use a lighter model, or request a higher quota in Service Quotas |
| 429 `crossed budget` | LiteLLM daily cap reached | wait for the next day or raise `provider_budget_config` (restart resets it) |
| `tools NOT USED` in `check-models` | that model did not call the tool | use it for chat; use `private-coder` or `private-glm` for agents |
| Open model errors with no providers | no zero-data-retention provider serves that model | pick another open model, or check the model page on openrouter.ai |
| VS Code on Windows cannot reach the gateway | WSL networking | keep `localhostForwarding=true` in `.wslconfig`; check `just status` shows `127.0.0.1:4000` |
| `just doctor` reports a port open on all interfaces | something bound to `0.0.0.0` | stop it and bind it to `127.0.0.1` |

---

## Security

- `.env` is gitignored and created with mode 600. Never commit it.
- Every service binds `127.0.0.1`; `just doctor` warns if a stack port is open on all
  interfaces.
- The gateway needs `LITELLM_MASTER_KEY` (random per install); the old published key is
  refused everywhere.
- The AWS user can call only the five private models, only in Sydney: no console, no other
  services. Rotate its key every few months and deactivate it at once if it leaks. Leave
  Bedrock's model invocation logging off; CloudTrail records that a call happened, not the
  prompt.
- Do not route your Claude or Google AI subscriptions through third-party gateways or
  proxies (tools like OmniRoute offer this). Anthropic's terms forbid using subscription
  logins outside its own apps, and Google suspended accounts for it in 2026.
- Tools are pinned (LiteLLM, OpenClaw, Docker images). LiteLLM's PyPI package was compromised
  in March 2026, so bump versions deliberately and check release notes.
- Treat inbound OpenClaw messages as untrusted. The stock agent is for research and education,
  not financial advice.

---

## Files

```
dev-stack/
├── litellm_config.yaml        models, fallbacks, budgets (edit this)
├── .env                       your secrets (generated; never commit)
├── .env.example               every setting, documented
├── justfile                   the commands above
├── setup.sh                   system tools for WSL Ubuntu (pinned versions)
├── aws/
│   ├── README.md              Bedrock setup, step by step
│   └── bedrock-access.yaml    CloudFormation: limited IAM user + budget
├── clients/                   Continue and OpenClaw config templates
├── scripts/
│   ├── devstack_env.py        creates/upgrades .env, renders client configs
│   ├── check_models.py        just check-models
│   └── setup_openclaw.sh      installs OpenClaw (pinned) and its config
├── shared/devstack_shared/    get_llm() tiers, Jev client, .env loading
├── examples/                  example agents (one uv project each)
├── docker/                    MySQL and AnythingLLM (127.0.0.1 only)
├── tests/                     unit tests + LiteLLM gateway tests (just test)
└── .wslconfig.example         WSL memory and networking
```

**Tests:** `just test` runs the unit tests and starts the pinned LiteLLM against fake Bedrock
and OpenRouter servers. It checks that the key is required, requests are signed for Sydney,
private models never fall back to OpenRouter, tool calls work, OpenRouter requests ask for zero
data retention, and the budget blocks spending. CI runs these plus ShellCheck, cfn-lint and the
installer tests on every push.

---

## License

MIT
