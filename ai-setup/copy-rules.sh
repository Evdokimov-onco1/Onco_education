#!/usr/bin/env bash
# Кладёт rules.md в буфер обмена — чтобы вставить в Cursor User Rules и Devin Knowledge.
set -euo pipefail
F="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/rules.md"
if   command -v pbcopy  >/dev/null 2>&1; then pbcopy  < "$F"
elif command -v wl-copy >/dev/null 2>&1; then wl-copy < "$F"
elif command -v xclip   >/dev/null 2>&1; then xclip -selection clipboard < "$F"
elif command -v clip.exe >/dev/null 2>&1; then clip.exe < "$F"
else echo "Буфер обмена недоступен, откройте файл вручную: $F" >&2; exit 1
fi
echo "rules.md скопирован. Вставьте в Cursor User Rules или Devin Knowledge."
