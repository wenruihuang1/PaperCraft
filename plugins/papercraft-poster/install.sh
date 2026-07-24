#!/usr/bin/env bash
# Install this repository-local PaperCraft plugin into the current Codex profile.
set -euo pipefail

plugin_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd "${plugin_root}/../.." && pwd)"
marketplace_root="${project_root}"

codex_bin="${CODEX_BIN:-}"
if [ -z "${codex_bin}" ] && command -v codex >/dev/null 2>&1; then
  codex_bin="$(command -v codex)"
fi
if [ -z "${codex_bin}" ]; then
  for candidate in \
    /Applications/ChatGPT.app/Contents/Resources/codex \
    /Applications/Codex.app/Contents/Resources/codex \
    /Applications/Codex.app/Contents/MacOS/codex \
    "${HOME}/.local/bin/codex" \
    "${HOME}/.codex/bin/codex"; do
    if [ -x "${candidate}" ]; then
      codex_bin="${candidate}"
      break
    fi
  done
fi
if [ -z "${codex_bin}" ] || [ ! -x "${codex_bin}" ]; then
  echo "Codex CLI is required. Install or update Codex, then run this script again." >&2
  echo "Tip: if Codex is installed but not on PATH, rerun with CODEX_BIN=/absolute/path/to/codex." >&2
  exit 1
fi

marketplaces="$("${codex_bin}" plugin marketplace list --json 2>/dev/null || true)"
if ! printf '%s' "${marketplaces}" | grep -Fq "${marketplace_root}"; then
  "${codex_bin}" plugin marketplace add "${marketplace_root}"
fi

"${codex_bin}" plugin add papercraft-poster@papercraft

echo
echo "PaperCraft Poster is installed. Open a new Codex task in: ${project_root}"
echo 'Then use: Use $papercraft-poster to turn /absolute/path/to/paper.pdf into a reviewed poster.'
