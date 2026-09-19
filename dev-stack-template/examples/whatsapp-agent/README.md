# WhatsApp Agent (OpenClaw)

This agent runs inside **OpenClaw**. OpenClaw already has first-class WhatsApp support.

## Setup

1. Install & onboard OpenClaw (see root README / `scripts/setup_openclaw.sh`).
2. Pair WhatsApp:
   ```bash
   openclaw channels login whatsapp
   # or follow the Control UI pairing flow
   ```
3. Copy the skill into your OpenClaw workspace:
   ```bash
   mkdir -p ~/.openclaw/workspace/skills/whatsapp-support
   cp SKILL.md ~/.openclaw/workspace/skills/whatsapp-support/
   ```
4. Make sure your `~/.openclaw/openclaw.json` points at LiteLLM (see `openclaw/openclaw.json.example`).

## Behaviour

- Uses Jev (via a small skill or custom tool) for urgency / department routing.
- Replies only to allow-listed numbers (configure `channels.whatsapp.allowFrom`).
- Long-term memory stays on your machine.

## Monetization

Package as a “WhatsApp customer-support bot” for local businesses.  
Charge monthly for the bot + optional human hand-off.
