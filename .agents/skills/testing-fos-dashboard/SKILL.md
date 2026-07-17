---
name: testing-fos-dashboard
description: Test the ФОС (fund of assessment tools) dashboard end-to-end. Use when verifying index.html + fos-data.json UI changes — teacher cards, matrix, drawer, load recompute.
---

# Testing the ФОС dashboard (Onco_education)

Static single-page app: `index.html` + `fos-data.json` (+ real ФОС texts in `fos/*.md`).
No backend, no build. GitHub Pages at `https://evdokimov-onco1.github.io/Onco_education/`.

## How to run locally
From the repo root:
```
python3 -m http.server 8099
```
Open `http://localhost:8099/index.html`. The page `fetch`es `fos-data.json` (cache: no-store),
so it MUST be served over http — opening the file via `file://` will fail the fetch.

## State / gotcha
- UI state (owner reassignments, approvals) is persisted to **localStorage** under a versioned key
  (e.g. `fos-state-v4`). Reassignments made while testing DO NOT touch the repo, but they DO persist
  across reloads. After a reassignment test, revert the owner via the dropdown or clear localStorage,
  so screenshots elsewhere show the canonical distribution.
- The key state version may change between versions — if the UI looks stale after a data change,
  a bumped state key or a hard reload clears it.

## Golden-path checks (T1–T7)
1. **T1 load** — exactly 7 teacher cards render, incl. Левицкий А.В. and Степанюк И.В. Each shows
   a load bar + "N тем / N заданий". Loads are computed live from `fos-data.json` themes, so
   card numbers must equal the sum of `load` over themes where `owner` matches.
2. **T2 filter** — click a teacher card: it gets active state, others dim, "сбросить фильтр ✕"
   appears; matrix cells the teacher owns show green "ваших заданий: N", others dim.
3. **T3 matrix** — 5 cells "есть файл" (onk1–4, mam2), 3 cells "нет ФОС" (him1, hir2, lt2), rest "—".
4. **T4 drawer (core)** — click a cell: title, 80 тестов / 30 вопросов / 15 задач, themes with
   EXACT question numbers (tests/theory/tasks) + owner dropdown. ФОС with `cross:true` blocks show
   a "Дефект ФОС: N заданий не относятся ни к одной теме" warning (onk3 = 32).
5. **T5 recompute** — change a theme's owner dropdown: teacher cards recompute instantly
   (old owner −load, new owner +load). Verify then revert.
6. **T6 missing FOS** — click a "нет ФОС" cell: stats show 0/80, 0/30, 0/15, themes carry "план"
   flag, note about "плановые квоты" + physician review.
7. **T7 console** — only a `favicon.ico` 404 is expected (cosmetic); no JS errors.

## Expected-not-a-failure
- `drive` fields may be empty → UI shows "ссылка на документ ещё не задана". This is expected until
  the Google Drive task is done; do NOT flag as a bug.
- Medical mapping (тема→номера) and plan quotas are DRAFT — always note physician review is required.

## Recording
Record browser interactions; annotate with `test_start`/`assertion` (Russian assertions are fine).
Maximize the window first (`wmctrl -r :ACTIVE: -b add,maximized_vert,maximized_horz`).

## Devin Secrets Needed
- None for local UI testing. Google Drive upload task (separate) would need Drive credentials.
