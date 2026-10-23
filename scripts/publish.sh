#!/usr/bin/env bash
# Publish this directory to GitHub under the currently authenticated account.
#
#   ./scripts/publish.sh [repo-name] [public|private]
#
# Requires git and the GitHub CLI (https://cli.github.com/). The script logs in
# through gh if needed, sets a local noreply commit identity for this repo,
# creates the repository, and pushes main. It never stores a token in the repo.
set -euo pipefail

REPO="${1:-twrpscrcpy}"
VISIBILITY="${2:-public}"

cd "$(dirname "$0")/.."

if ! command -v git >/dev/null 2>&1; then
    echo "git is required." >&2
    exit 1
fi
if ! command -v gh >/dev/null 2>&1; then
    cat >&2 <<'EOF'
GitHub CLI (gh) is required. Install it first:
  macOS:   brew install gh
  Windows: winget install GitHub.cli
  Linux:   use your package manager (pacman -S github-cli, apt install gh, ...)
Then run this script again.
EOF
    exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
    echo "Logging in to GitHub..."
    gh auth login
fi

LOGIN="$(gh api user --jq .login)"
NAME="$(gh api user --jq '.name // .login')"
ID="$(gh api user --jq .id)"
URL="https://github.com/$LOGIN/$REPO.git"

if [ ! -d .git ]; then
    git init -b main
fi

git config user.name "$NAME"
git config user.email "${ID}+${LOGIN}@users.noreply.github.com"

git add -A
if ! git diff --cached --quiet; then
    git commit -m "twrpscrcpy 1.0.0"
else
    echo "Nothing new to commit."
fi

if gh repo view "$LOGIN/$REPO" >/dev/null 2>&1; then
    if git remote get-url origin >/dev/null 2>&1; then
        git remote set-url origin "$URL"
    else
        git remote add origin "$URL"
    fi
    git push -u origin main
else
    case "$VISIBILITY" in
        public) FLAG="--public" ;;
        private) FLAG="--private" ;;
        *) echo "visibility must be public or private" >&2; exit 1 ;;
    esac
    gh repo create "$REPO" "$FLAG" --source=. --remote=origin --push \
        --description "scrcpy-like screen mirroring and control for TWRP recovery"
fi

gh repo edit "$LOGIN/$REPO" \
    --add-topic twrp,scrcpy,android,recovery,adb,screen-mirroring >/dev/null 2>&1 || true

echo
echo "Published: https://github.com/$LOGIN/$REPO"
echo "To publish a release build, tag a version after this first push:"
echo "  git tag -a v1.0.0 -m 'twrpscrcpy 1.0.0' && git push origin v1.0.0"
