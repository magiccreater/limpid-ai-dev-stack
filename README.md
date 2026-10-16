# limpid-ai-dev-stack

Local AI dev stack for a Windows 11 + WSL2 laptop: llama.cpp for local models, a LiteLLM
gateway in front of local and OpenRouter models, TypeSafe Jev for cheap routing, OpenClaw for
chat channels, and example agents.

```bash
git clone https://github.com/magiccreater/limpid-ai-dev-stack
./limpid-ai-dev-stack/install_dev_stack.sh            # installs to ~/dev-stack
./limpid-ai-dev-stack/install_dev_stack.sh --dry-run  # show what an upgrade would change
```

The installer is safe to re-run: it never deletes your folder, `.env` or data, and backs up
anything it replaces. Full guide: [dev-stack-template/README.md](dev-stack-template/README.md).

Tests: `python3 -m unittest discover -s tests` (installer) and `just test` inside the stack.
