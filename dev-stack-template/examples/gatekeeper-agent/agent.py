"""
Gatekeeper Agent — defensive security checks for your own apps and environment.

Focus: find common issues in YOUR code/config, suggest hardening.
Not for attacking third-party systems.

Checks covered:
  - XSS-prone patterns in frontend/templates
  - SQL injection risk patterns in code
  - Weak password policy / common passwords
  - Basic dependency / config hygiene hints
  - DDoS-oriented hardening recommendations (rate limits, timeouts)
  - Open / insecure Wi-Fi awareness (local environment)

Usage:
  uv sync
  uv run python agent.py scan ./path/to/project
  uv run python agent.py password "candidate-password"
  uv run python agent.py wifi
  uv run python agent.py report "Describe my PHP/MySQL app stack"
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

from devstack_shared.llm import get_llm

# ---------------------------------------------------------------------------
# Heuristic scanners (fast, local, no network)
# ---------------------------------------------------------------------------

XSS_PATTERNS = [
    (r"innerHTML\s*=", "Assigning to innerHTML can enable XSS if data is untrusted"),
    (r"document\.write\s*\(", "document.write with untrusted input is an XSS risk"),
    # Only the raw (unescaped) output forms; plain {{ }} is auto-escaped in Blade, Twig, Jinja, Vue.
    (r"\{!!.*?!!\}", "Blade {!! !!} prints raw HTML — escape or sanitize untrusted data"),
    (r"\{\{\{.*?\}\}\}", "Triple-brace {{{ }}} prints raw HTML in Handlebars/Mustache"),
    (r"\{\{[^}\n]*\|\s*(safe|raw)\b[^}\n]*\}\}", "Jinja/Twig |safe or |raw disables escaping"),
    (r"\{%\s*autoescape\s+(false|off)\s*%\}", "Template auto-escaping turned off"),
    (r"v-html\s*=", "Vue v-html renders raw HTML — sanitize untrusted content"),
    (r"dangerouslySetInnerHTML", "React dangerouslySetInnerHTML requires sanitization"),
    (r"echo\s+\$_(GET|POST|REQUEST|COOKIE)", "PHP echo of superglobals without escaping"),
    (r"<\?=\s*\$_(GET|POST|REQUEST)", "PHP short echo of user input without htmlspecialchars"),
]

SQLI_PATTERNS = [
    (r'query\s*\(\s*[f"\'].*\$', "String interpolation in SQL query — prefer prepared statements"),
    (r'execute\s*\(\s*[f"\'].*\+', "String concatenation in SQL — prefer bound parameters"),
    (r"WHERE.*=\s*['\"].*\$_(GET|POST|REQUEST)", "PHP SQL built from superglobals"),
    (r"mysql_query\s*\(", "Deprecated mysql_query — use PDO/mysqli with prepared statements"),
    (r"\bSELECT\b.*\+.*\b(req|request|params|input)\b", "Possible dynamic SQL from request data"),
]

SECRET_PATTERNS = [
    (r"(?i)(api[_-]?key|secret|password|token)\s*=\s*['\"][^'\"]{8,}", "Possible hardcoded secret"),
    (r"(?i)BEGIN (RSA |OPENSSH )?PRIVATE KEY", "Private key material in source"),
]

SKIP_DIRS = {".git", "node_modules", "vendor", ".venv", "dist", "build", "__pycache__", ".next"}


def scan_path(root: Path) -> dict:
    findings: list[dict] = []
    root = root.resolve()
    if not root.exists():
        return {"error": f"Path not found: {root}"}

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if not any(name.endswith(ext) for ext in (
                ".php", ".js", ".ts", ".tsx", ".jsx", ".py", ".html", ".vue", ".twig", ".blade.php"
            )):
                continue
            path = Path(dirpath) / name
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            rel = str(path.relative_to(root))
            for pattern, msg in XSS_PATTERNS + SQLI_PATTERNS + SECRET_PATTERNS:
                for m in re.finditer(pattern, text):
                    line = text[: m.start()].count("\n") + 1
                    findings.append({
                        "file": rel,
                        "line": line,
                        "issue": msg,
                        "snippet": text[max(0, m.start() - 40): m.end() + 40].replace("\n", " ")[:120],
                    })
                    if len(findings) >= 80:
                        return {"findings": findings, "truncated": True}

    return {"findings": findings, "truncated": False}


def check_password(candidate: str) -> dict:
    """Local password strength heuristics (not a substitute for a proper password manager)."""
    issues = []
    score = 0
    if len(candidate) >= 12:
        score += 2
    elif len(candidate) >= 8:
        score += 1
    else:
        issues.append("Shorter than 8 characters")
    if re.search(r"[a-z]", candidate) and re.search(r"[A-Z]", candidate):
        score += 1
    else:
        issues.append("Missing mixed case")
    if re.search(r"\d", candidate):
        score += 1
    else:
        issues.append("Missing digit")
    if re.search(r"[^A-Za-z0-9]", candidate):
        score += 1
    else:
        issues.append("Missing special character")
    common = {"password", "123456", "qwerty", "admin", "letmein", "welcome", "password1"}
    if candidate.lower() in common:
        score = 0
        issues.append("Matches a very common password")
    strength = "weak" if score <= 2 else ("medium" if score <= 4 else "strong")
    return {"strength": strength, "score": score, "issues": issues}


def wifi_awareness() -> dict:
    """
    Defensive notes only. Actual interface names vary by OS.
    Encourages checking for open/unencrypted networks on the host.
    """
    tips = [
        "Prefer WPA3 or WPA2-AES networks; avoid open (no password) Wi-Fi for work.",
        "On open networks, use a trusted VPN before accessing admin panels or production.",
        "Disable auto-join for unknown SSIDs on laptops and phones.",
        "In WSL2, Wi-Fi is managed by Windows — check Windows network settings for 'Open' or 'Public' profiles.",
        "Never send production credentials over unencrypted HTTP on public Wi-Fi.",
    ]
    return {
        "status": "advisory",
        "tips": tips,
        "check_manually": [
            "Windows: Settings → Network & internet → Wi-Fi → properties (security type)",
            "Linux host: nmcli device wifi list  (look for Security: -- or Open)",
        ],
    }


# ---------------------------------------------------------------------------
# LLM-assisted review
# ---------------------------------------------------------------------------

SYSTEM = """You are Gatekeeper, a defensive application security assistant.
You help developers secure THEIR own code and infrastructure.
You do NOT provide offensive exploit techniques, attack payloads, or guidance for harming third-party systems.
Focus on: secure coding patterns, input validation, prepared statements, CSP/headers, rate limiting,
password policy, dependency hygiene, and safe network practices.
Be concrete and actionable. Prefer short checklists.
"""


async def llm_review(context: str) -> str:
    llm = get_llm(tier="private")
    res = await llm.ainvoke([
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": context},
    ])
    return res.content


async def run_scan(project: str) -> dict:
    data = scan_path(Path(project))
    summary = json.dumps(data, indent=2)[:6000]
    advice = await llm_review(
        f"Static scan results for my project path `{project}`:\n{summary}\n\n"
        "Prioritize the findings, explain risk briefly, and give fix guidance "
        "(prepared statements, escaping, CSP, etc.). Group by severity."
    )
    return {"scan": data, "advice": advice}


async def run_ddos_hardening(description: str) -> str:
    return await llm_review(
        f"My service description:\n{description}\n\n"
        "Give DEFENSIVE recommendations only to reduce impact of volumetric and application-layer floods: "
        "rate limiting, connection limits, timeouts, caching, WAF/CDN placement, health checks, "
        "and what to monitor. No attack methods."
    )


async def run_report(description: str) -> str:
    return await llm_review(
        f"Stack / app description:\n{description}\n\n"
        "Produce a practical security checklist covering: XSS, SQL injection, auth/passwords, "
        "headers, secrets handling, dependency updates, and basic availability hardening. "
        "Defensive only."
    )


async def main(argv: list[str]) -> None:
    if len(argv) < 2:
        print(__doc__)
        return

    cmd = argv[1].lower()
    if cmd == "scan":
        path = argv[2] if len(argv) > 2 else "."
        result = await run_scan(path)
        print(json.dumps(result["scan"], indent=2))
        print("\n=== Gatekeeper advice ===\n")
        print(result["advice"])
    elif cmd == "password":
        pw = argv[2] if len(argv) > 2 else ""
        print(json.dumps(check_password(pw), indent=2))
    elif cmd == "wifi":
        print(json.dumps(wifi_awareness(), indent=2))
    elif cmd == "ddos":
        desc = " ".join(argv[2:]) or "Public PHP/MySQL web app behind nginx"
        print(await run_ddos_hardening(desc))
    elif cmd == "report":
        desc = " ".join(argv[2:]) or "LAMP stack with public forms and admin panel"
        print(await run_report(desc))
    else:
        print(f"Unknown command: {cmd}")
        print("Use: scan | password | wifi | ddos | report")


if __name__ == "__main__":
    asyncio.run(main(sys.argv))
