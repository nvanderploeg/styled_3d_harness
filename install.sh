#!/usr/bin/env bash
# install.sh [target] — link pipeline/ and the skills into target (default: this repo's parent)
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
target="$(cd "${1:-$here/..}" && pwd)"

if [[ "$target" == "$here" ]]; then
  echo "install: target is the harness itself; pick its parent or another project" >&2
  exit 1
fi

# Relative links keep working when target and harness move together, e.g. as a submodule.
rel() {
  realpath --relative-to="$2" "$1" 2>/dev/null || echo "$1"
}

link() {
  local src="$1" dst="$2"
  if [[ -L "$dst" ]]; then
    rm "$dst"
  elif [[ -e "$dst" ]]; then
    echo "install: $dst exists and is not a symlink; leaving it" >&2
    failed=1
    return
  fi
  ln -s "$(rel "$src" "$(dirname "$dst")")" "$dst"
  echo "  $dst -> $(readlink "$dst")"
}

failed=0
echo "Installing into $target"
link "$here/pipeline" "$target/pipeline"
mkdir -p "$target/.claude/skills"
for skill in "$here"/.claude/skills/*/; do
  skill="${skill%/}"
  link "$skill" "$target/.claude/skills/$(basename "$skill")"
done
exit "$failed"
