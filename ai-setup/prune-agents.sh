#!/usr/bin/env bash
# Убирает лишние определения агентов из ~/.claude/agents/.
#
#   ./prune-agents.sh              показать, что будет сделано
#   ./prune-agents.sh --применить  перенести в ~/.claude/agents-archive/
#
# Ничего не удаляется: файлы переезжают в архив рядом. Вернуть — mv обратно.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENTS="$HOME/.claude/agents"
ARCHIVE="$HOME/.claude/agents-archive"
KEEP="$ROOT/agents/keep.txt"
APPLY=0
[ "${1:-}" = "--применить" ] && APPLY=1

[ -d "$AGENTS" ] || { echo "Папки $AGENTS нет — агенты не установлены."; exit 0; }
[ -f "$KEEP" ] || { echo "Нет списка $KEEP" >&2; exit 1; }

mapfile -t patterns < <(grep -vE '^\s*(#|$)' "$KEEP")

keep_list=(); drop_list=()
while IFS= read -r file; do
  name="$(basename "$file")"
  matched=0
  for p in "${patterns[@]}"; do
    case "$name" in *"$p"*) matched=1; break ;; esac
  done
  if [ "$matched" = 1 ]; then keep_list+=("$name"); else drop_list+=("$name"); fi
done < <(find "$AGENTS" -maxdepth 1 -name '*.md' | sort)

echo "Остаются (${#keep_list[@]}):"
for n in "${keep_list[@]:-}"; do [ -n "$n" ] && echo "  $n"; done
echo
echo "В архив (${#drop_list[@]}):"
for n in "${drop_list[@]:-}"; do [ -n "$n" ] && echo "  $n"; done

if [ "${#keep_list[@]}" -eq 0 ]; then
  echo
  echo "Ни один агент не совпал со списком. Перенос отменён —" >&2
  echo "проверьте имена в $KEEP, иначе уедет всё." >&2
  exit 1
fi

if [ "$APPLY" = 0 ]; then
  echo
  echo "Это предварительный просмотр. Перенести:  $0 --применить"
  exit 0
fi

mkdir -p "$ARCHIVE"
for n in "${drop_list[@]:-}"; do
  [ -n "$n" ] || continue
  mv "$AGENTS/$n" "$ARCHIVE/$n"
done
echo
echo "Перенесено в $ARCHIVE — файлы целы."
echo "Вернуть один:  mv $ARCHIVE/<имя>.md $AGENTS/"
echo "Вернуть все:   mv $ARCHIVE/*.md $AGENTS/"
