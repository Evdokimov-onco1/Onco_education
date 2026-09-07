#!/usr/bin/env bash
# Подключает новый проект к глобальной настройке.
#
#   ./new-project.sh ~/code/мой-сайт            обычный проект
#   ./new-project.sh ~/code/разбор-сроков анализ  разбор клинических данных
#
# Глобальные правила Claude берёт сам. Здесь кладётся только то, чего он не покрывает:
# AGENTS.md для Cursor, заготовка карты и — для разбора данных — структура папок.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="${1:-}"
KIND="${2:-сайт}"

if [ -z "$TARGET" ]; then
  echo "Использование: $0 <путь-к-проекту> [сайт|анализ]" >&2
  exit 1
fi
if [ ! -d "$TARGET" ]; then
  echo "Нет такой папки: $TARGET" >&2
  exit 1
fi
case "$KIND" in
  сайт|анализ) ;;
  *) echo "Неизвестный тип: $KIND. Бывает: сайт, анализ" >&2; exit 1 ;;
esac

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

echo "Подключаю $NAME (тип: $KIND):"
copy "$ROOT/templates/graph.md" "$TARGET/.ai/graph.md"

if [ "$KIND" = "анализ" ]; then
  copy "$ROOT/templates/analiz/AGENTS.md"  "$TARGET/AGENTS.md"
  copy "$ROOT/templates/analiz/README.md"  "$TARGET/README.md"
  copy "$ROOT/templates/analiz/gitignore"  "$TARGET/.gitignore"
  for d in data/raw data/public scripts out; do
    mkdir -p "$TARGET/$d"
    echo "  папка: $TARGET/$d"
  done
  # data/raw не должна опустеть и исчезнуть из виду, но и в git ей нельзя
  [ -f "$TARGET/data/raw/СЮДА-КЛАСТЬ-ВЫГРУЗКУ.txt" ] || \
    printf 'Сырые выгрузки кладите сюда.\nЭта папка не попадает в git — так и задумано.\nОбезличить перед работой: /deident <файл>\n' \
      > "$TARGET/data/raw/СЮДА-КЛАСТЬ-ВЫГРУЗКУ.txt"
else
  copy "$ROOT/templates/AGENTS.md" "$TARGET/AGENTS.md"
fi

echo
echo "Готово. Дальше:"
echo "  1. Заполнить $TARGET/AGENTS.md — что за проект и чего в нём не делать."
if [ "$KIND" = "анализ" ]; then
  echo "  2. Положить выгрузку в data/raw/ и обезличить: /deident data/raw/<файл>"
  echo "  3. Построить карту: /graph"
  echo
  echo "  Репозиторий для клинических данных заводить ПРИВАТНЫМ."
else
  echo "  2. Построить карту проекта: /graph"
fi
echo
echo "Правила языка, стиля и дисциплины мышления копировать НЕ нужно —"
echo "они уже глобальные и работают в этом проекте с первой секунды."
