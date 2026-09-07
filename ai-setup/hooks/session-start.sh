#!/usr/bin/env bash
# SessionStart: короткая сводка в начале сессии Claude Code.
# Ничего не блокирует и не спрашивает — только печатает то, что стоит знать до начала работы.
set -uo pipefail

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

notes=""
note() { notes="${notes}$1"$'\n'; }

# --- карта проекта ---
if [ -f .ai/graph.md ]; then
  last_code=$(git log -1 --format=%ct 2>/dev/null || echo 0)
  last_map=$(git log -1 --format=%ct -- .ai/graph.md 2>/dev/null || echo 0)
  if [ -n "$last_map" ] && [ "$last_map" -gt 0 ] 2>/dev/null; then
    if [ "$last_code" -gt "$last_map" ]; then
      days=$(( (last_code - last_map) / 86400 ))
      note "Карта .ai/graph.md отстаёт от кода на ${days} дн. Сверить перед работой: /graph"
    fi
  fi
else
  note "Карты проекта нет. Построить: /graph"
fi

# --- папка с данными ---
if [ -d data ] || [ -d "выгрузки" ]; then
  note "В проекте есть папка с данными. Перед коммитом проверить, что сырые файлы не уходят в git."
fi

# --- защита от ПДн подключена? ---
hooks_path=$(git config --get core.hooksPath || true)
if [ -z "$hooks_path" ] && [ ! -x .git/hooks/pre-commit ]; then
  note "Проверка на персональные данные не подключена. Включить: ~/ai-setup/install.sh"
fi

[ -z "$notes" ] && exit 0
printf '%s' "$notes"
