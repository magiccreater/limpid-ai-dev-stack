# Dev Stack & Agent Playground

**Windows 11 + WSL2 + VS Code + Docker + LiteLLM + Amazon Bedrock (Sydney) + OpenRouter + OpenClaw**

One environment for:

- Daily coding helpers and agents through one gateway, with **private** models on Amazon
  Bedrock in Sydney and cheap **open** models on OpenRouter for non-sensitive work
- Local document and image search (RAG)
- Optional cheap routing decisions with TypeSafe Jev
- Example agents to learn from and build on (coding helper, scraper, WhatsApp, social, trends, stock notes, mentor, study planner, security checks)

No model runs on your laptop: it only runs the gateway, Docker and the agents.

The example agents are starting points: each is a short script with one prompt. They have
no tools, memory or verification of their own. Treat them as templates, not products.

---

## Quick start

```bash
# 1. Windows: copy .wslconfig.example to C:\Users\<You>\.wslconfig, then in PowerShell: wsl --shutdown
# 2. Inside Ubuntu (WSL2):
git clone https://github.com/magiccreater/limpid-ai-dev-stack
./limpid-ai-dev-stack/install_dev_stack.sh        # installs to ~/dev-stack; safe to re-run
cd ~/dev-stack
./setup.sh && source ~/.bashrc                    # first time only

# 3. Private models: one-time AWS setup (about 15 minutes), see aws/README.md.
#    Then put AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY in .env.
# 4. Optional, open models: put OPENROUTER_API_KEY in .env (create it WITH A CREDIT LIMIT,
#    and turn on Zero Data Retention at https://openrouter.ai/settings/privacy).

# 5. Gateway and clients
just litellm            # 127.0.0.1:4000
just client-configs     # Continue + OpenClaw configs with your key
just doctor             # checks env, AWS keys, gateway, exposure
just check-models       # one tiny answer + tool call per private model
```

Upgrading later: pull this repo and run `install_dev_stack.sh` again. It adds new files,
backs up and replaces changed ones (in `.dev-stack-backup/`), never touches your data, and
writes `litellm_config.yaml.dev-stack-new` instead of overwriting your gateway config.
`--dry-run` shows what it would do.

---

## Architecture

```
VS Code (Cline / Continue / Aider)   OpenClaw (WhatsApp, Telegram…)   example agents
                    \                         |                          /
                     ▼                        ▼                         ▼
              LiteLLM gateway  127.0.0.1:4000  (key required, daily budgets)
                 │                                     │
   PRIVATE: Amazon Bedrock, Sydney              OPEN: OpenRouter, zero data retention
   Qwen3 Coder Next · Qwen3 Coder 30B           DeepSeek V4 Flash · Qwen3 Coder Next · GLM 5.1
   Qwen3 235B · DeepSeek V3.2                   Claude Sonnet 5.5 (opt-in, capped)
   (falls back only within Bedrock)             (non-sensitive work only)

   Jev decisions (OpenRouter Decisions API) ← off unless JEV_ENABLED=1
```

Every service binds `127.0.0.1`, so nothing is reachable from your network.

---

## Models (litellm_config.yaml)

| Name | Where | Model | Use for | Cost per M tokens in/out |
|---|---|---|---|---|
| `private-coder` | Bedrock Sydney | Qwen3 Coder Next | coding, agents (default) | ~$0.50–0.60 / $1.20–1.50 |
| `private-coder-lite` | Bedrock Sydney | Qwen3 Coder 30B A3B | cheaper coding; fallback | $0.15 / $0.62 |
| `private-general` | Bedrock Sydney | Qwen3 235B A22B | writing, summaries, chat | $0.23 / $0.91 |
| `private-reasoner` | Bedrock Sydney | DeepSeek V3.2 | harder reasoning | $0.64 / $1.91 |
| `open-deepseek` | OpenRouter | DeepSeek V4 Flash | public data, drafts | $0.14 / $1.28 |
| `open-qwen` | OpenRouter | Qwen3 Coder Next | public code | $0.12 / $0.80 |
| `open-glm` | OpenRouter | GLM 5.1 | stronger, public work | $1.40 / $4.40 |
| `cloud-reasoner` | OpenRouter | Claude Sonnet 5.5 | rarely; needs `ALLOW_FRONTIER=1` | $2 / $10 |

`local-coder` and `hybrid-agent` (names from earlier versions) are aliases of `private-coder`.

**Private means:** AWS says Bedrock does not store or log prompts, does not train on them,
and does not share them with the model makers. The region is pinned to Sydney in the config.
A private model only falls back to another private model: if all of them fail, the request
fails instead of going to OpenRouter.

**Open means:** OpenRouter sends each request only to providers with a zero-data-retention
policy. That is a promise from each provider, with one more company in the path, so keep
client code and personal data on the private models.

Fallbacks react to errors, not to weak answers. When a task needs a stronger model, ask
for it by name.

**Money guards, strongest first:**
1. The AWS Budget alarm (`aws/bedrock-access.yaml`) and the credit limit on your OpenRouter key.
2. LiteLLM's daily caps: $3/day for Bedrock and $3/day for OpenRouter, kept in memory, so they
   reset when LiteLLM restarts.
3. No paid Claude anywhere in a fallback chain. For interactive work with Claude, use your
   Claude subscription in Claude Code instead of paying per token here.

---

## Jev routing and privacy

`devstack_shared.jev_client.route_request()` asks Jev which agent fits a request and how
complex it is. It sends the request text to OpenRouter, so it is **off by default**
(`JEV_ENABLED=0`). When off, has no key or fails, agents fall back to local defaults and
keep working. Turn it on only for agents that never see client or private data.

---

## Key commands

```bash
just env              # create/upgrade .env (random secrets; replaces published defaults)
just litellm          # gateway on 127.0.0.1:4000 (refuses to start without a real key)
just check-models     # call each private model (or: just check-models open-deepseek ...)
just client-configs   # Continue + OpenClaw configs with your key
just mysql            # MySQL on 127.0.0.1:3306
just rag              # AnythingLLM on 127.0.0.1:3001
just openclaw         # OpenClaw gateway
just agent <name>     # coding|scraper|social|trend|stock|mentor|study|gatekeeper
just status           # which ports are open, and on which address
just doctor           # end-to-end health check
just test             # unit + gateway tests
```

---

## Example agents

| Agent | Path | Does |
|---|---|---|
| Coding | `examples/coding-agent` | answers on `private-coder` (or `private-reasoner` when Jev is on and rates it complex); text only (does not edit files or run tests) |
| Scraper | `examples/scraper-agent` | Playwright page fetch + LLM extraction to JSON |
| WhatsApp | `examples/whatsapp-agent` | OpenClaw skill for a support bot |
| Social poster | `examples/social-poster` | drafts posts |
| Trend | `examples/trend-agent` | research-style digest (uses `open`: public data only) |
| Stock | `examples/stock-agent` | yfinance data + an educational note (not financial advice) |
| Mentor | `examples/mentor-agent` | coaching replies |
| Study planner | `examples/study-planner` | weekly plan as JSON |
| Gatekeeper | `examples/gatekeeper-agent` | regex scan of your own code for XSS/SQLi/secrets + defensive advice |

Each agent is its own uv project and depends on the shared package in `shared/`
(`devstack_shared.llm`, `devstack_shared.jev_client`). Agents use `tier="private"` unless
noted; `get_llm("open")` and `get_llm("frontier")` are the only tiers that leave Bedrock.

---

## VS Code

Open the folder with Remote – WSL. Recommended extensions are in `.vscode/extensions.json`.
`just client-configs` writes `~/.continue/config.yaml`. For Cline, choose the
"OpenAI Compatible" provider with base URL `http://127.0.0.1:4000/v1`, your
`LITELLM_MASTER_KEY`, and a model name from the table above (`private-coder` for client code).

---

## Security notes

- Never commit `.env` (it is gitignored and created with mode 600).
- Everything listens on `127.0.0.1`; `just doctor` warns if a port is open on all interfaces.
- The AWS user can only call the four private models, only in Sydney. Never put root or
  admin keys in `.env`; rotate the key every few months.
- Tools are pinned (LiteLLM, OpenClaw, Docker images). LiteLLM's PyPI package was
  compromised in March 2026, so bump versions deliberately and check release notes.
- Keep OpenClaw DM policies on allowlist / pairing; treat inbound messages as untrusted.
- The stock agent is for research and education, not financial advice.

---

## License

MIT
