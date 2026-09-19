# Local Full-Stack Dev Stack & Multi-Agent Platform

**Intel Arc + WSL2 + VS Code + Docker + Local AI + OpenRouter + OpenClaw**

One productive environment for:

- Daily coding with local + cloud AI (Cline / Continue / Aider)
- Local document & image intelligence (RAG)
- Hybrid inference (llama.cpp on Arc → LiteLLM → OpenRouter)
- Decision routing with TypeSafe Jev
- Production-ready agents you can monetize:
  - Coding agent
  - Web scraping agent
  - WhatsApp agent
  - Social media poster
  - Trending / research agent
  - Stock / signals agent
  - Mentor / coaching agent
  - Study planner (for your son + productizable)
  - Gatekeeper (defensive security: XSS / SQLi patterns, passwords, hardening)

---

## Quick Start

```bash
# 1. Copy .wslconfig.example → C:\Users\<You>\.wslconfig  then  wsl --shutdown
# 2. Inside Ubuntu WSL2:
curl -fsSL https://raw.githubusercontent.com/YOUR_REPO/main/init_full_dev_stack.sh | bash
# or run the local script after cloning

cd ~/dev-stack
./setup.sh
source ~/.bashrc

# 3. Copy secrets
cp .env.example .env
# edit OPENROUTER_API_KEY and any other keys

# 4. Start core services
just llama          # or ./scripts/start_llama_server.sh
just litellm
just mysql
just openclaw       # after openclaw onboard
```

---

## Architecture

```
VS Code (Cline + Continue + Aider)
        │
        ▼
LiteLLM :4000  ←── llama.cpp (Arc Vulkan) :8080
        │              + OpenRouter (DeepSeek V4 Flash, GLM, Claude…)
        │              + Jev Decisions API (routing / classification)
        ▼
OpenClaw Gateway  +  Custom Python agents (LangGraph / CrewAI)
        │
        ├── WhatsApp / Telegram / Discord channels
        ├── Skills + MCP tools
        └── Dockerized products (scraper, trading, study planner…)
```

---

## Agents Included

| Agent | Path | Purpose | Monetization angle |
|-------|------|---------|--------------------|
| Coding | `examples/coding-agent` | Repo-aware coding + Aider/Cline | AI pair-programmer SaaS |
| Scraper | `examples/scraper-agent` | Playwright / Scrapy pipelines | Data-as-a-service |
| WhatsApp | `examples/whatsapp-agent` | OpenClaw WhatsApp bot | Customer support bots |
| Social Poster | `examples/social-poster` | Multi-platform content | Content agency tools |
| Trend | `examples/trend-agent` | Trends + research digests | Newsletter / signals |
| Stock | `examples/stock-agent` | Market data + simple signals | Signal service (comply with regs) |
| Mentor | `examples/mentor-agent` | Long-term coaching memory | 1:1 coaching bots |
| Study Planner | `examples/study-planner` | Spaced repetition + calendar | Family → B2C study app |
| Gatekeeper | `examples/gatekeeper-agent` | Defensive security scans & hardening advice | Security audit add-on for client apps |

All agents share the same LiteLLM endpoint and can call Jev for cheap routing decisions.

---

## Key Commands (justfile)

```bash
just setup          # full system provisioning
just llama          # start local model server
just litellm        # start unified gateway
just mysql          # start MySQL
just openclaw       # start OpenClaw gateway
just rag            # start local RAG (docs + images)
just agent <name>   # run an example agent
just status         # health of all services
```

---

## VS Code

Open the folder in VS Code (Remote – WSL).  
Recommended extensions are listed in `.vscode/extensions.json`.  
Continue + Cline are pre-configured to talk to `http://localhost:4000/v1`.

---

## Security Notes

- Never commit `.env`
- Keep OpenClaw DM policies on allowlist / pairing
- Treat inbound WhatsApp/Telegram messages as untrusted
- Stock agent is for research/education — not financial advice

---

## License

MIT — build products, sell services, keep the stack.
