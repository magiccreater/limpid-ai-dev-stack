# Gatekeeper Agent (defensive security)

Helps you review **your own** apps and environment. It does **not** provide offensive attack techniques.

## What it checks

| Command | Purpose |
|---------|---------|
| `scan <path>` | Heuristic scan for XSS / SQL injection / secret patterns in source, then LLM prioritization |
| `password <candidate>` | Local password strength heuristics |
| `wifi` | Advisory notes on open/insecure Wi-Fi (check Windows/WSL host settings) |
| `ddos "<service desc>"` | Defensive hardening ideas (rate limits, timeouts, CDN/WAF placement) |
| `report "<stack desc>"` | Full defensive checklist for your described stack |

## Examples

```bash
just agent gatekeeper scan ~/dev-stack
just agent gatekeeper password 'MyCandidatePass!'
just agent gatekeeper wifi
just agent gatekeeper ddos "Public nginx + PHP-FPM API"
just agent gatekeeper report "LAMP with user login and admin panel"
```

## Scope & limits

- Pattern scan is **heuristic**, not a full SAST/DAST product (pair with tools like Composer audit, npm audit, OWASP ZAP on *your* staging sites).
- DDoS section is **prevention/hardening advice only**.
- Wi-Fi checks are **awareness** — actual radio/network state is managed by Windows on WSL2.
- Never point this at systems you do not own or have permission to test.

## Monetization idea

Offer “pre-launch security checklist + code scan” as an add-on when you deliver LAMP/PHP or agent products to clients.
