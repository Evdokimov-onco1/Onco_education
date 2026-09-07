#!/usr/bin/env bash
# Глобальная настройка Claude Code на этой машине.
# Запускать один раз на каждой новой машине. Повторный запуск безопасен.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$HOME/.claude"
mkdir -p "$CLAUDE_DIR"

link() {   # link <источник> <назначение>
  local src="$1" dst="$2"
  if [ -e "$dst" ] && [ ! -L "$dst" ]; then
    local bak="$dst.backup-$(date +%Y%m%d%H%M%S)"
    mv "$dst" "$bak"
    echo "  сохранён прежний файл: $bak"
  fi
  ln -sfn "$src" "$dst"
  echo "  $dst -> $src"
}

echo "Подключаю правила и настройки:"
link "$ROOT/rules.md"             "$CLAUDE_DIR/CLAUDE.md"
link "$ROOT/claude/settings.json" "$CLAUDE_DIR/settings.json"

cat <<'TXT'

Готово. Claude Code теперь читает эти правила во всех проектах на этой машине.
Файлы — симлинки, поэтому `git pull` в этом репозитории применяется сразу,
переустанавливать ничего не нужно.

Скиллы ставить НЕ нужно: они живут на аккаунте claude.ai и синхронизируются сами
(проверить: ls ~/.claude/skills/synced/*/).

Осталось два шага, которые делаются только через интерфейс:

  1. Cursor → Settings → Rules → User Rules — вставить содержимое rules.md
  2. Devin  → Settings → Knowledge → создать запись со scope «все репозитории»,
     вставить туда же

     Положить rules.md в буфер обмена:  ./copy-rules.sh

MCP-серверы и плагины восстанавливаются командами из claude/restore.md
TXT
