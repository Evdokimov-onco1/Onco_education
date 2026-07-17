---
name: testing-fos-dashboard
description: Test the ФОС (fund of assessment tools) dashboard end-to-end. Use when verifying index.html + fos-data.json UI changes — teacher roster, matrix, drawer, activity/productivity, load recompute.
---

# Testing the ФОС dashboard (Onco_education)

Static single-page app: `index.html` + `fos-data.json`. No backend, no build.
GitHub Pages at `https://evdokimov-onco1.github.io/Onco_education/`.

NOTE: the project has gone through more than one design. Always read the CURRENT `index.html`
and `fos-data.json` before testing — the schema/teacher list/localStorage keys may differ from a
prior version. This file documents the version live as of the "простая схема" swap; treat specifics
(teacher count, KPI numbers) as things to re-derive from the code, not hard truths.

## Current version (simple schema)
- `fos-data.json` top-level keys `onk:1..mam:2` (+ `_meta`); each FOS has `owners[]`, `approved`, `drive`.
- `index.html` hardcodes `DISCIPLINES` (themes + seed owners) and `TEACHERS` (5: Ронзин, Петухов,
  Евдокимов, Кобзев, Глазкова; Петухов = HEAD «руководитель»). `fos-data.json` overrides owners/drive.
- Offline mode when `const WEBAPP_URL=""` → localStorage. Online mode (Apps Script backend) if a URL is set.

## How to run
Prefer the live GitHub Pages URL (that is what the user clicks). To test a branch locally, from repo root:
```
python3 -m http.server 8099
```
Open `http://localhost:8099/index.html`. The page `fetch`es `fos-data.json`, so it MUST be served over
http — `file://` fails the fetch.

## State / gotcha
- localStorage keys in this version: `fos-matrix-v2` (owners/drive), `fos-live-v1` (theme statuses/
  approvals), `fos-me` (selected teacher). Old versions used other keys (e.g. `fos-state-v4`).
- Clear these before testing for a fresh state derived from `fos-data.json`:
  `['fos-matrix-v2','fos-live-v1','fos-me','fos-state-v4'].forEach(k=>localStorage.removeItem(k));location.reload()`
- Reassignments/status changes persist across reloads but do NOT touch the repo. Revert or clear after.

## Golden-path checks
1. **Version renders** — tab title `Матрица ФОС · Онкология`, H1 «Матрица ФОС · распределение по темам`,
   roster of 5 teachers, Петухов marked «руководитель направления». (If old title «ФОС · Кафедра
   онкологии» shows, the swap/deploy did not take.)
2. **KPI/hero** — counts are computed from `DISCIPLINES`: «ФОС требуется» = total cells, «файл есть» =
   status `exists`, «создать с нуля» = status `missing`. In this version: 8 / 5 / 3.
3. **Matrix** — 8 FOS cells: 5 exists (onk1-4, mam2) at 100%/«на приёмку», 3 missing (him1, hir2, lt2)
   showing «нет ФОС» + «＋ Создать ФОС»; empty semesters render as «—» hatched cells.
4. **Activity/productivity** — section «Активность и продуктивность»: empty feed on fresh state,
   mode «○ локальный режим» (offline), progress bars for all teachers. «Нагрузка по преподавателям»
   shows a card per teacher with theme count.
5. **Drawer + drive** — click an exists cell (e.g. Онкология 1 сем): title, meta with `.docx` file,
   themes with owner `<select>` + status seg(не начато/черновик/готово). «📄 Открыть ФОС в Google
   Docs →» button and the prefilled drive field must equal that FOS's `drive` URL from `fos-data.json`.
6. **Recompute** — change a theme owner dropdown: roster/productivity/«Нагрузка» recompute live. Revert.
7. **Console** — no JS errors (a `favicon.ico` 404 is cosmetic, acceptable).

## Expected-not-a-failure / escalate
- `.github/workflows/deploy-timeweb.yml` (Deploy to Timeweb) FAILS without secrets
  `TIMEWEB_FTP_HOST/USER/PASSWORD`. Unrelated to Pages render; report it, don't block.
- Empty `drive` → button «Документ не привязан». Fine unless the task was to fill drive links.
- Theme→owner distribution and medical content are DRAFT — note physician review is required.

## Recording
Record browser interactions; annotate with `test_start`/`assertion` (Russian is fine).
Maximize the window first (`wmctrl -r :ACTIVE: -b add,maximized_vert,maximized_horz`).

## Devin Secrets Needed
- None for UI testing.
- Timeweb auto-deploy (repo Actions secrets, not Devin secrets): `TIMEWEB_FTP_HOST`, `TIMEWEB_FTP_USER`,
  `TIMEWEB_FTP_PASSWORD` (+ optional var `TIMEWEB_SERVER_DIR`).
