# limpid-ai-dev-stack

AI dev stack for a Windows 11 + WSL2 laptop: a LiteLLM gateway in front of private models on
Amazon Bedrock (Sydney) and open models on OpenRouter, optional TypeSafe Jev routing, OpenClaw
for chat channels, and example agents. No model runs on the laptop.

```bash
git clone https://github.com/magiccreater/limpid-ai-dev-stack
./limpid-ai-dev-stack/install_dev_stack.sh            # installs to ~/dev-stack
./limpid-ai-dev-stack/install_dev_stack.sh --dry-run  # show what an upgrade would change
```

The installer is safe to re-run: it never deletes your folder, `.env` or data, and backs up
anything it replaces. Full guide: [dev-stack-template/README.md](dev-stack-template/README.md).
AWS setup for the private models: [dev-stack-template/aws/README.md](dev-stack-template/aws/README.md).

Tests: `python3 -m unittest discover -s tests` (installer) and `just test` inside the stack.
