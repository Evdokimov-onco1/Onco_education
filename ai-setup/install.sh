#!/usr/bin/env bash
# Глобальная настройка Claude Code и git на этой машине.
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

echo "Правила и настройки Claude:"
link "$ROOT/rules.md"             "$CLAUDE_DIR/CLAUDE.md"
link "$ROOT/claude/settings.json" "$CLAUDE_DIR/settings.json"
link "$ROOT/commands"             "$CLAUDE_DIR/commands"

echo
echo "Git — защита от случайной публикации данных пациентов:"

# Глобальный gitignore. Прежний, если был, не теряем — подключаем оба.
PREV="$(git config --global --get core.excludesfile || true)"
if [ -n "$PREV" ] && [ "$PREV" != "$ROOT/git/gitignore_global" ]; then
  echo "  внимание: уже был подключён $PREV"
  echo "  перенесите нужные строки в $ROOT/git/gitignore_global — заменяю"
fi
git config --global core.excludesfile "$ROOT/git/gitignore_global"
echo "  core.excludesfile -> $ROOT/git/gitignore_global"

# Хук pre-commit. core.hooksPath действует на все репозитории сразу.
PREVH="$(git config --global --get core.hooksPath || true)"
if [ -n "$PREVH" ] && [ "$PREVH" != "$ROOT/git/hooks" ]; then
  echo "  внимание: core.hooksPath уже указывал на $PREVH — заменяю"
fi
git config --global core.hooksPath "$ROOT/git/hooks"
echo "  core.hooksPath    -> $ROOT/git/hooks"
echo "  (хук предупреждает и спрашивает, а не запрещает; обход — PDN_OK=1 git commit)"

cat <<'TXT'

Готово. Claude Code читает эти правила во всех проектах на этой машине,
команды /graph, /deident и /otkat доступны везде.
Файлы — симлинки, поэтому `git pull` в этом репозитории применяется сразу.

Скиллы ставить НЕ нужно: они живут на аккаунте claude.ai и синхронизируются сами
(проверить: ls ~/.claude/skills/synced/*/).

Осталось два шага, которые делаются только через интерфейс:

  1. Cursor → Settings → Rules → User Rules — вставить содержимое rules.md
  2. Devin  → Settings → Knowledge → запись со scope «все репозитории», туда же

     Положить rules.md в буфер обмена:  ./copy-rules.sh

MCP-серверы и плагины восстанавливаются командами из claude/restore.md

Важно про core.hooksPath: он отключает собственные хуки .git/hooks во ВСЕХ
репозиториях. Если в каком-то проекте появится свой pre-commit — положите его
рядом, в git/hooks/, или скажите, и сделаем иначе.
TXT
