#!/usr/bin/env bash
# Install or upgrade the dev stack in ~/dev-stack (or --target DIR).
#
# Safe to re-run. It never deletes your folder, .env, data or git history:
#   - files missing from the target are added
#   - identical files are left alone
#   - files that differ are backed up to .dev-stack-backup/<time>/ and then replaced,
#     except litellm_config.yaml, which you are expected to edit: its new version is
#     written next to it as litellm_config.yaml.dev-stack-new for you to merge
#   - .env is created with random secrets, or upgraded in place (missing keys added,
#     published default keys replaced); see dev-stack-template/scripts/devstack_env.py
set -euo pipefail

usage() {
  echo "Usage: $0 [--target DIR] [--dry-run]"
  echo "  --target DIR  install location (default: ~/dev-stack)"
  echo "  --dry-run     show what would change, change nothing"
}

TARGET="$HOME/dev-stack"
DRY_RUN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --target) TARGET="${2:?--target needs a directory}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE="$SCRIPT_DIR/dev-stack-template"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$TARGET/.dev-stack-backup/$STAMP"

# Files you are expected to customise: never replaced, new version written alongside.
KEEP_FILES=("litellm_config.yaml")
# Files from earlier versions of this stack that no longer exist (moved to the backup).
OBSOLETE_FILES=(
  "vscode/continue-config.json"   # held the published LiteLLM key; now clients/*.tmpl
  "vscode/extensions.json"        # now .vscode/extensions.json
  "openclaw/openclaw.json.example"
  "shared/llm.py"                 # now shared/devstack_shared/
  "shared/jev_client.py"
)

added=0; updated=0; same=0; side_by_side=0; retired=0

say() { echo "$*"; }
act() { if [ "$DRY_RUN" = 1 ]; then echo "  [dry-run] $*"; else "$@"; fi; }

is_keep() {
  local f
  for f in "${KEEP_FILES[@]}"; do [ "$1" = "$f" ] && return 0; done
  return 1
}

backup_file() {  # backup_file REL
  act mkdir -p "$BACKUP/$(dirname "$1")"
  act cp -p "$TARGET/$1" "$BACKUP/$1"
}

say "=== Dev Stack: $( [ -d "$TARGET" ] && echo upgrading || echo installing ) $TARGET ==="
[ "$DRY_RUN" = 1 ] && say "(dry run: nothing will be changed)"
act mkdir -p "$TARGET"

while IFS= read -r -d '' src; do
  rel="${src#"$TEMPLATE"/}"
  dst="$TARGET/$rel"
  if [ ! -e "$dst" ]; then
    say "  add      $rel"
    act mkdir -p "$(dirname "$dst")"
    act cp -p "$src" "$dst"
    added=$((added + 1))
  elif cmp -s "$src" "$dst"; then
    same=$((same + 1))
  elif is_keep "$rel" && ! grep -q 'sk-dev-proxy-key' "$dst"; then
    say "  keep     $rel (new version: $rel.dev-stack-new)"
    act cp -p "$src" "$dst.dev-stack-new"
    side_by_side=$((side_by_side + 1))
  else
    # A kept file that still contains the old published key is replaced too:
    # leaving it would keep the gateway open to anyone who knows that key.
    say "  update   $rel (old copy in .dev-stack-backup/$STAMP/)"
    backup_file "$rel"
    act cp -p "$src" "$dst"
    updated=$((updated + 1))
  fi
done < <(find "$TEMPLATE" \( -name .venv -o -name __pycache__ -o -name node_modules \) -prune \
            -o -type f ! -name '*.pyc' ! -name uv.lock ! -name .env -print0 | sort -z)

for rel in "${OBSOLETE_FILES[@]}"; do
  if [ -f "$TARGET/$rel" ]; then
    say "  retire   $rel (moved to .dev-stack-backup/$STAMP/)"
    backup_file "$rel"
    act rm -f "$TARGET/$rel"
    act rmdir --ignore-fail-on-non-empty "$(dirname "$TARGET/$rel")"
    retired=$((retired + 1))
  fi
done

if [ "$DRY_RUN" = 1 ]; then
  say ""
  say "Dry run: $added to add, $updated to update, $side_by_side to merge by hand, $retired to retire, $same unchanged."
  say ".env would be created or upgraded by scripts/devstack_env.py init."
  exit 0
fi

chmod +x "$TARGET/setup.sh" "$TARGET/scripts/"*.sh

say ""
say "=== .env ==="
python3 "$TARGET/scripts/devstack_env.py" init --env "$TARGET/.env" --example "$TARGET/.env.example"

if [ ! -d "$TARGET/.git" ]; then
  git -C "$TARGET" init -q -b main
  git -C "$TARGET" add -A
  if ! git -C "$TARGET" commit -q -m "Initial commit: local multi-agent dev stack"; then
    say "note: initial git commit skipped (set git user.name and user.email, then commit)."
  fi
fi

say ""
say "=== Done: $added added, $updated updated, $side_by_side to merge by hand, $retired retired, $same unchanged ==="
if [ "$side_by_side" -gt 0 ]; then
  say "Merge each *.dev-stack-new into your file, then delete the .dev-stack-new copy."
fi
if [ "$updated" -gt 0 ] || [ "$retired" -gt 0 ]; then
  say "Your previous versions are in $BACKUP"
fi
cat <<EOF

Next steps:
  cd $TARGET
  ./setup.sh && source ~/.bashrc     # first time only
  # put OPENROUTER_API_KEY in .env (create the key with a credit limit)
  # local model, pick one:
  #   Windows (faster on Intel Arc):  scripts\\windows\\llama-server.ps1
  #   WSL:                            ./scripts/install_llama.sh && just llama
  just litellm                       # gateway on 127.0.0.1:4000
  just client-configs                # Continue + OpenClaw configs with your key
  just doctor
EOF
