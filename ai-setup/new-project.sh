#!/usr/bin/env bash
# Подключает новый проект к глобальной настройке.
#   ./new-project.sh ~/code/мой-проект
#
# Глобальные правила Claude берёт сам. Здесь кладётся только то, чего он не покрывает:
# AGENTS.md для Cursor и заготовка карты проекта.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${1:-}"

if [ -z "$TARGET" ]; then
  echo "Использование: $0 <путь-к-проекту>" >&2
  exit 1
fi
if [ ! -d "$TARGET" ]; then
  echo "Нет такой папки: $TARGET" >&2
  exit 1
fi

NAME="$(basename "$TARGET")"

copy() {   # copy <шаблон> <назначение>
  if [ -e "$2" ]; then
    echo "  уже есть, пропускаю: $2"
  else
    mkdir -p "$(dirname "$2")"
    sed "s|<НАЗВАНИЕ ПРОЕКТА>|$NAME|" "$1" > "$2"
    echo "  создан: $2"
  fi
}

echo "Подключаю $NAME:"
copy "$ROOT/templates/AGENTS.md" "$TARGET/AGENTS.md"
copy "$ROOT/templates/graph.md"  "$TARGET/.ai/graph.md"

cat <<TXT

Готово. Дальше:
  1. Заполнить $TARGET/AGENTS.md — что за проект и чего в нём не делать.
  2. Открыть проект в Cursor, запустить в терминале \`claude\` и попросить:
     «построй карту проекта в .ai/graph.md»

Правила языка, стиля и дисциплины мышления копировать НЕ нужно —
они уже глобальные и работают в этом проекте с первой секунды.
TXT
