# Local Dev Stack & Agent Playground

**Windows 11 + WSL2 + VS Code + Docker + local llama.cpp + LiteLLM + OpenRouter + OpenClaw**

One environment for:

- Daily coding with local and cheap cloud models (Cline, Continue, Aider) through one gateway
- Local document and image search (RAG)
- Cheap routing decisions with TypeSafe Jev
- Example agents to learn from and build on (coding helper, scraper, WhatsApp, social, trends, stock notes, mentor, study planner, security checks)

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

# 3. Secrets: .env already has random keys. Add your OpenRouter key:
#    create it at https://openrouter.ai/settings/keys WITH A CREDIT LIMIT, then edit .env

# 4. Local model (pick one; see "Local model" below)
#    Windows PowerShell:  powershell -ExecutionPolicy Bypass -File scripts\windows\llama-server.ps1
#    or WSL:              ./scripts/install_llama.sh && just llama

# 5. Gateway and clients
just litellm            # 127.0.0.1:4000
just client-configs     # Continue + OpenClaw configs with your key
just doctor             # checks env, model server, gateway, exposure
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
              LiteLLM gateway  127.0.0.1:4000  (key required, daily budget)
                 │                                  │
   llama-server 127.0.0.1:8080              OpenRouter (pay per token)
   (Windows native or WSL)                  DeepSeek · Qwen · GLM · Claude (opt-in)

   Jev decisions (OpenRouter Decisions API) ← agents call it directly for routing
```

Every service binds `127.0.0.1`. With WSL mirrored networking, anything bound to
`0.0.0.0` would be reachable from your Wi-Fi, so don't change that.

---

## Models (litellm_config.yaml)

| Name | What | Cost |
|---|---|---|
| `local-coder` | your llama-server | free |
| `hybrid-agent` | local first; **if the call fails** (down, overloaded, prompt too long) → `open-deepseek` → `open-qwen` | free, else cheap |
| `open-deepseek` | DeepSeek V4 Flash | very cheap |
| `open-qwen` | Qwen3 Coder Next | cheap |
| `open-glm` | GLM 5.1 | moderate |
| `cloud-reasoner` | Claude Sonnet 5.5 | expensive; refused by `devstack_shared.llm` unless `ALLOW_FRONTIER=1`; capped at $1/day |

Fallbacks react to errors, not to weak answers. When a task needs a stronger model, ask
for it by name.

**Money guards, strongest first:**
1. The credit limit on your OpenRouter key (set it when you create the key).
2. LiteLLM's daily OpenRouter budget (`provider_budget_config`, default $3/day). It is
   kept in memory, so it resets when LiteLLM restarts.
3. No paid Claude anywhere in a fallback chain. For interactive work with Claude, use your
   Claude subscription in Claude Code instead of paying per token here.

---

## Local model

Two presets (set `LLAMA_PRESET` in `.env`, or `-Preset` on Windows):

| Preset | Model | Size | Notes |
|---|---|---|---|
| `qwen36` | Qwen3.6-35B-A3B Q4_K_M | ~20 GB | mixture-of-experts, fast for its size; best local quality |
| `small` | Qwen2.5-Coder-7B Q4_K_M | ~5 GB | fits anywhere; weak at agent tool use |

Context is 32k tokens (`LLAMA_CTX`). Agent tools send long prompts; 4k is not enough.

**Windows native (recommended on Intel Arc / Core Ultra laptops).** WSL2 reaches the GPU
through a translation layer that is often slow or falls back to the CPU on Intel graphics.
`scripts\windows\llama-server.ps1` downloads the pinned llama.cpp release (Vulkan by default,
`-Backend sycl` to try Intel's SYCL build) and serves on `127.0.0.1:8080`, which WSL reaches
through mirrored networking. Run `-ListDevices` to check that your GPU is listed.

If `qwen36` fails to load, either raise *Shared GPU Memory* in Intel Graphics Software
(newer drivers allow most of system RAM), set `-NCpuMoe 10` (`LLAMA_N_CPU_MOE=10`) to keep
some experts on the CPU, or use `-Preset small`.

**Inside WSL.** `./scripts/install_llama.sh` installs the pinned prebuilt Vulkan build and
prints the devices it sees. If it lists only `llvmpipe`, there is no GPU acceleration;
use the Windows script. `./scripts/build_llama.sh` builds the same tag from source.

Both scripts pin the llama.cpp release (`b11600`); bump it deliberately.

---

## Jev routing and privacy

`devstack_shared.jev_client.route_request()` asks Jev which agent fits a request and how
complex it is. It sends the request text to OpenRouter. It never raises: when Jev is off,
has no key or fails, agents fall back to local defaults and keep working.

Set `JEV_ENABLED=0` in `.env` whenever agents handle client or private data.

---

## Key commands

```bash
just env            # create/upgrade .env (random secrets; replaces published defaults)
just litellm        # gateway on 127.0.0.1:4000 (refuses to start without a real key)
just llama          # local model inside WSL
just client-configs # Continue + OpenClaw configs with your key
just mysql          # MySQL on 127.0.0.1:3306
just rag            # AnythingLLM on 127.0.0.1:3001
just openclaw       # OpenClaw gateway
just agent <name>   # coding|scraper|social|trend|stock|mentor|study|gatekeeper
just status         # which ports are open, and on which address
just doctor         # end-to-end health check
just test           # unit + gateway tests
```

---

## Example agents

| Agent | Path | Does |
|---|---|---|
| Coding | `examples/coding-agent` | routes a question to the cheapest fitting tier and answers in text (does not edit files or run tests) |
| Scraper | `examples/scraper-agent` | Playwright page fetch + LLM extraction to JSON |
| WhatsApp | `examples/whatsapp-agent` | OpenClaw skill for a support bot |
| Social poster | `examples/social-poster` | drafts posts |
| Trend | `examples/trend-agent` | research-style digest |
| Stock | `examples/stock-agent` | yfinance data + an educational note (not financial advice) |
| Mentor | `examples/mentor-agent` | coaching replies |
| Study planner | `examples/study-planner` | weekly plan as JSON |
| Gatekeeper | `examples/gatekeeper-agent` | regex scan of your own code for XSS/SQLi/secrets + defensive advice |

Each agent is its own uv project and depends on the shared package in `shared/`
(`devstack_shared.llm`, `devstack_shared.jev_client`).

---

## VS Code

Open the folder with Remote – WSL. Recommended extensions are in `.vscode/extensions.json`.
`just client-configs` writes `~/.continue/config.yaml`. For Cline, choose the
"OpenAI Compatible" provider with base URL `http://127.0.0.1:4000/v1`, your
`LITELLM_MASTER_KEY`, and a model name from the table above.

---

## Security notes

- Never commit `.env` (it is gitignored and created with mode 600).
- Everything listens on `127.0.0.1`; `just doctor` warns if a port is open on all interfaces.
- Tools are pinned (LiteLLM, llama.cpp, OpenClaw, Docker images). LiteLLM's PyPI package was
  compromised in March 2026, so bump versions deliberately and check release notes.
- Keep OpenClaw DM policies on allowlist / pairing; treat inbound messages as untrusted.
- The stock agent is for research and education, not financial advice.

---

## License

MIT
