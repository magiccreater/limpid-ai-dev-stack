# limpid-ai-dev-stack

The optional [Oracle inference profile](dev-stack-template/oracle/profile) runs a pinned llama.cpp build and Qwen coder model on an Ampere A1 VM. The WSL `god` launcher from the accompanying coding kit handles provisioning, tunnelling and diagnostics. Its default route stays on the VM.

An AI dev stack for a Windows 11 + WSL2 laptop. One LiteLLM gateway (`127.0.0.1:4000`) gives
your coding tools and agents two kinds of model:

- **Private**: Amazon Bedrock in **Sydney**, for client code, finances and personal documents.
  Qwen3 Coder Next, Qwen3 Coder 30B, Qwen3 235B, DeepSeek V3.2 and GLM 5. Data stays in
  Australia, and a private model never falls back to anything outside Bedrock.
- **Open**: OpenRouter, only from providers that keep no data, for public work. DeepSeek V4
  Flash, Qwen3 Coder Next, GLM 5.3, and Claude Sonnet 5.5 (opt-in).

It also includes OpenClaw (WhatsApp/Telegram), local RAG, MySQL and example agents. No model runs
on the laptop, and every service listens on `127.0.0.1` only.

```bash
git clone https://github.com/magiccreater/limpid-ai-dev-stack
./limpid-ai-dev-stack/install_dev_stack.sh            # installs to ~/dev-stack
./limpid-ai-dev-stack/install_dev_stack.sh --dry-run  # show what an upgrade would change
```

The installer is safe to re-run: it never deletes your folder, `.env` or data, and backs up
anything it replaces.

- **Full guide** (setup, models, costs, region, tools, troubleshooting):
  [dev-stack-template/README.md](dev-stack-template/README.md)
- **AWS setup for the private models** (about 15 minutes):
  [dev-stack-template/aws/README.md](dev-stack-template/aws/README.md)

Typical cost: a few dollars a month for light use; about $13 for a heavy month on
`private-coder`. Daily caps in LiteLLM, an AWS Budget email and the OpenRouter key's credit
limit guard spending.

Tests: `python3 -m unittest discover -s tests` (installer) and `just test` inside the stack
(unit tests plus LiteLLM against fake Bedrock and OpenRouter). CI runs both, plus ShellCheck
and cfn-lint.
