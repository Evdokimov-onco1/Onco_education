#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Легальная выкачка полных текстов по списку источников (references.json).

Конвейер на трёх открытых API, без Sci-Hub и прочих пиратских зеркал:

    1. Crossref      — название статьи -> DOI (с проверкой совпадения, чтобы не скачать чужую работу)
    2. Unpaywall     — DOI -> ссылка на легальный OA-PDF, если он существует
    3. Europe PMC    — DOI -> PMCID -> полный текст, депонированный в PMC/Europe PMC
    4. Всё остальное — попадает в отчёт как «взять через институциональный доступ / запросить у авторов»

Запуск:

    python3 fetch_papers.py --email you@example.com                 # весь список
    python3 fetch_papers.py --email you@example.com --level A       # только уровень А
    python3 fetch_papers.py --email you@example.com --dry-run       # только отрезолвить DOI, ничего не качать
    python3 fetch_papers.py --email you@example.com --only A4.1 A5.1

Email обязателен: это требование «вежливого» доступа Crossref и Unpaywall.
Скрипт можно перезапускать — уже скачанные файлы пропускаются (если не задан --force).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
import unicodedata
from dataclasses import dataclass, field, asdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:  # pragma: no cover
    sys.exit("Нужна библиотека requests:  pip install -r requirements.txt")

VERSION = "1.0"

CROSSREF_API = "https://api.crossref.org/works"
UNPAYWALL_API = "https://api.unpaywall.org/v2"
EUROPEPMC_SEARCH = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
EUROPEPMC_PDF = "https://www.ebi.ac.uk/europepmc/webservices/rest/{src}/{pid}/fullTextPDF"
PMC_PDF = "https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/"

# Порог, ниже которого найденный Crossref результат считается «не той статьёй».
TITLE_MATCH_THRESHOLD = 0.72

# Сокращения из исходного списка, которые мешают текстовому поиску.
ABBREVIATIONS = {
    "mcrpc": "metastatic castration resistant prostate cancer",
    "crpc": "castration resistant prostate cancer",
    "nmcrpc": "nonmetastatic castration resistant prostate cancer",
    "mcspc": "metastatic castration sensitive prostate cancer",
    "mhspc": "metastatic hormone sensitive prostate cancer",
    "adt": "androgen deprivation therapy",
    "rct": "randomized controlled trial",
    "rcts": "randomized controlled trials",
    "gnrh": "gonadotropin releasing hormone",
    "lhrh": "luteinizing hormone releasing hormone",
    "asco": "american society of clinical oncology",
    "aha": "american heart association",
    "acs": "american cancer society",
    "aua": "american urological association",
    "esc": "european society of cardiology",
    "psma": "prostate specific membrane antigen",
    "pet": "positron emission tomography",
}

STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "for", "with", "and", "or", "to", "at",
    "by", "from", "versus", "vs", "study", "trial", "analysis", "patients",
    "men", "among", "after", "plus",
}


# --------------------------------------------------------------------------- #
# Нормализация и сопоставление названий
# --------------------------------------------------------------------------- #

def normalize(text: str) -> str:
    """Приводит строку к сравнимому виду: без диакритики, пунктуации и регистра."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[‐-―]", "-", text)          # разные виды тире
    text = re.sub(r"[^a-z0-9\s\-]", " ", text)
    text = re.sub(r"[\s\-]+", " ", text)
    return text.strip()


def expand_abbreviations(text: str) -> str:
    """Раскрывает mCRPC/ADT/RCT и подобное — иначе Crossref-поиск промахивается."""
    tokens = normalize(text).split()
    out: list[str] = []
    for tok in tokens:
        out.extend(ABBREVIATIONS.get(tok, tok).split())
    return " ".join(out)


def content_tokens(text: str) -> set[str]:
    return {t for t in expand_abbreviations(text).split() if t not in STOPWORDS and len(t) > 2}


def title_score(reference_title: str, candidate_title: str) -> float:
    """
    Насколько кандидат из Crossref похож на нашу запись.

    В исходном списке названия часто урезаны («…: Final overall survival analysis»
    вместо полного заголовка), поэтому одной посимвольной похожести мало.
    Берём максимум из двух метрик:
      * посимвольное сходство (ловит полные совпадения);
      * доля наших значимых слов, найденных у кандидата (ловит урезанные названия).
    """
    ref_norm = expand_abbreviations(reference_title)
    cand_norm = expand_abbreviations(candidate_title)
    if not ref_norm or not cand_norm:
        return 0.0

    seq = SequenceMatcher(None, ref_norm, cand_norm).ratio()

    ref_tokens = content_tokens(reference_title)
    cand_tokens = content_tokens(candidate_title)
    recall = len(ref_tokens & cand_tokens) / len(ref_tokens) if ref_tokens else 0.0

    return max(seq, recall * 0.95)


def journal_matches(abbrev: str, full_name: str) -> bool:
    """
    'N Engl J Med' и 'The New England Journal of Medicine' — один журнал.
    Проверяем, что каждое слово сокращения является префиксом слова полного названия,
    в том же порядке.
    """
    a = [t for t in normalize(abbrev).split() if t not in {"the"}]
    f = [t for t in normalize(full_name).split() if t not in {"the"}]
    if not a or not f:
        return False
    if " ".join(a) in " ".join(f) or " ".join(f) in " ".join(a):
        return True
    i = 0
    for token in f:
        if i < len(a) and token.startswith(a[i]):
            i += 1
    return i == len(a)


# --------------------------------------------------------------------------- #
# Результат по одной записи
# --------------------------------------------------------------------------- #

@dataclass
class Outcome:
    id: str
    level: str
    block: str
    citation: str
    doi: str = ""
    doi_source: str = ""          # crossref | preset | —
    match_score: float = 0.0
    matched_title: str = ""
    is_oa: bool | None = None
    oa_status: str = ""           # gold | green | hybrid | bronze | closed
    pmcid: str = ""
    pdf_url: str = ""
    pdf_source: str = ""          # unpaywall | europepmc | pmc
    landing_url: str = ""
    file: str = ""
    status: str = "pending"       # ok | skipped | no_oa | no_doi | manual | failed
    note: str = ""
    tried: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #

def build_session(email: str, timeout: int) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=8)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({
        # Crossref просит контакт в User-Agent — за это пускают в "polite pool".
        "User-Agent": f"onco-education-fetch/{VERSION} (+https://github.com/Evdokimov-onco1/Onco_education; mailto:{email})",
        "Accept": "application/json",
    })
    session.request_timeout = timeout  # type: ignore[attr-defined]
    return session


def get_json(session: requests.Session, url: str, params: dict | None = None) -> Any:
    response = session.get(url, params=params, timeout=session.request_timeout)  # type: ignore[attr-defined]
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


# --------------------------------------------------------------------------- #
# Шаг 1. Crossref: название -> DOI
# --------------------------------------------------------------------------- #

def resolve_doi(session: requests.Session, ref: dict, email: str) -> tuple[str, float, str, str]:
    """Возвращает (doi, score, matched_title, note)."""
    if ref.get("doi"):
        return ref["doi"], 1.0, ref.get("title", ""), "DOI задан в references.json"

    query = f'{ref.get("title", "")} {ref.get("authors", "")}'.strip()
    params = {
        "query.bibliographic": query,
        "rows": 5,
        "select": "DOI,title,container-title,issued,author,volume,page,type",
        "mailto": email,
    }
    data = get_json(session, CROSSREF_API, params)
    items = ((data or {}).get("message") or {}).get("items") or []
    if not items:
        return "", 0.0, "", "Crossref не вернул ни одного кандидата"

    best: tuple[float, dict, str] | None = None
    for item in items:
        cand_title = (item.get("title") or [""])[0]
        score = title_score(ref["title"], cand_title)

        # Небольшие бонусы за совпадение года и журнала — разводят похожие работы
        # одной группы авторов (например, промежуточный и финальный анализ).
        parts = (item.get("issued") or {}).get("date-parts") or [[None]]
        cand_year = parts[0][0] if parts and parts[0] else None
        if ref.get("year") and cand_year and abs(int(cand_year) - int(ref["year"])) <= 1:
            score += 0.05
        cand_journal = (item.get("container-title") or [""])[0]
        if ref.get("journal") and cand_journal and journal_matches(ref["journal"], cand_journal):
            score += 0.05

        if best is None or score > best[0]:
            best = (score, item, cand_title)

    assert best is not None
    score, item, cand_title = best
    if score < TITLE_MATCH_THRESHOLD:
        return "", score, cand_title, f"лучший кандидат Crossref не прошёл проверку (score {score:.2f}) — проверить вручную"
    return item.get("DOI", ""), min(score, 1.0), cand_title, ""


# --------------------------------------------------------------------------- #
# Шаг 2. Unpaywall: DOI -> легальный OA-PDF
# --------------------------------------------------------------------------- #

def query_unpaywall(session: requests.Session, doi: str, email: str) -> dict:
    data = get_json(session, f"{UNPAYWALL_API}/{doi}", {"email": email})
    if not data:
        return {}
    best = data.get("best_oa_location") or {}
    locations = data.get("oa_locations") or []
    pdf_urls: list[str] = []
    for loc in [best] + locations:
        for key in ("url_for_pdf", "url"):
            url = loc.get(key)
            if url and url not in pdf_urls:
                pdf_urls.append(url)
    return {
        "is_oa": bool(data.get("is_oa")),
        "oa_status": data.get("oa_status") or "",
        "pdf_urls": pdf_urls,
        "landing": best.get("url_for_landing_page") or data.get("doi_url") or "",
        "title": data.get("title") or "",
    }


# --------------------------------------------------------------------------- #
# Шаг 3. Europe PMC: то, что депонировано в PMC
# --------------------------------------------------------------------------- #

def query_europepmc(session: requests.Session, doi: str) -> dict:
    params = {"query": f'DOI:"{doi}"', "format": "json", "resultType": "core", "pageSize": 1}
    data = get_json(session, EUROPEPMC_SEARCH, params)
    results = ((data or {}).get("resultList") or {}).get("result") or []
    if not results:
        return {}
    rec = results[0]
    pmcid = rec.get("pmcid") or ""
    urls: list[str] = []

    for item in ((rec.get("fullTextUrlList") or {}).get("fullTextUrl") or []):
        if item.get("documentStyle") == "pdf" and item.get("availability") in {"Free", "Open access"}:
            url = item.get("url")
            if url and url not in urls:
                urls.append(url)

    if pmcid:
        urls.append(EUROPEPMC_PDF.format(src="PMC", pid=pmcid))
        urls.append(PMC_PDF.format(pmcid=pmcid))

    return {
        "pmcid": pmcid,
        "pmid": rec.get("pmid") or "",
        "is_oa": rec.get("isOpenAccess") == "Y",
        "pdf_urls": urls,
    }


# --------------------------------------------------------------------------- #
# Шаг 4. Скачивание
# --------------------------------------------------------------------------- #

def safe_filename(ref: dict) -> str:
    author = normalize(ref.get("first_author") or "unknown").replace(" ", "-")
    year = ref.get("year") or "nd"
    trial = ref.get("trial")
    parts = [ref["id"].replace(".", "-"), author or "unknown", str(year)]
    if trial:
        parts.append(normalize(trial).replace(" ", "-"))
    return "_".join(parts) + ".pdf"


def looks_like_pdf(chunk: bytes, content_type: str) -> bool:
    if chunk.startswith(b"%PDF"):
        return True
    # Некоторые репозитории отдают PDF без корректного Content-Type,
    # но HTML-заглушку («требуется подписка») пропускать нельзя.
    return "pdf" in content_type.lower() and not chunk.lstrip()[:15].lower().startswith(b"<!doctype")


def download_pdf(session: requests.Session, url: str, destination: Path) -> tuple[bool, str]:
    try:
        with session.get(
            url,
            timeout=session.request_timeout,  # type: ignore[attr-defined]
            stream=True,
            allow_redirects=True,
            headers={"Accept": "application/pdf,*/*"},
        ) as response:
            if response.status_code != 200:
                return False, f"HTTP {response.status_code}"
            content_type = response.headers.get("Content-Type", "")
            iterator = response.iter_content(chunk_size=65536)
            try:
                first = next(iterator)
            except StopIteration:
                return False, "пустой ответ"
            if not looks_like_pdf(first, content_type):
                return False, f"не PDF (Content-Type: {content_type or 'нет'})"

            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(".part")
            with open(temporary, "wb") as handle:
                handle.write(first)
                for chunk in iterator:
                    handle.write(chunk)
            size = temporary.stat().st_size
            if size < 10_000:
                temporary.unlink(missing_ok=True)
                return False, f"подозрительно маленький файл ({size} байт) — вероятно, заглушка"
            temporary.replace(destination)
            human = f"{size / 1024:.0f} КБ" if size < 1024 * 1024 else f"{size / 1024 / 1024:.1f} МБ"
            return True, human
    except requests.RequestException as exc:
        return False, f"сетевая ошибка: {exc.__class__.__name__}"


# --------------------------------------------------------------------------- #
# Обработка одной записи
# --------------------------------------------------------------------------- #

def citation_of(ref: dict) -> str:
    bits = [ref.get("authors", ""), ref.get("title", "")]
    tail = ref.get("journal", "")
    if ref.get("year"):
        tail += f" {ref['year']}"
    if ref.get("volume"):
        tail += f"; {ref['volume']}"
    if ref.get("pages"):
        tail += f":{ref['pages']}"
    bits.append(tail.strip())
    return ". ".join(b.strip().rstrip(".") for b in bits if b.strip()) + "."


def process(session: requests.Session, ref: dict, args, out_dir: Path) -> Outcome:
    result = Outcome(
        id=ref["id"], level=ref["level"], block=ref["block"], citation=citation_of(ref)
    )

    if ref.get("manual"):
        result.status = "manual"
        result.landing_url = ref.get("manual_url", "")
        result.note = "нет в Crossref/PubMed — забирается вручную с указанного портала"
        return result

    target = out_dir / "pdf" / safe_filename(ref)
    if target.exists() and not args.force:
        result.status = "skipped"
        result.file = str(target.relative_to(out_dir))
        result.note = "файл уже скачан"
        return result

    # 1. DOI
    try:
        doi, score, matched, note = resolve_doi(session, ref, args.email)
    except requests.RequestException as exc:
        result.status = "failed"
        result.note = f"Crossref недоступен: {exc.__class__.__name__}"
        return result

    result.doi, result.match_score, result.matched_title = doi, round(score, 3), matched
    result.doi_source = "preset" if ref.get("doi") else "crossref"
    if not doi:
        result.status = "no_doi"
        result.note = note
        return result
    result.landing_url = f"https://doi.org/{doi}"
    time.sleep(args.sleep)

    # 2. Unpaywall
    candidates: list[tuple[str, str]] = []
    try:
        unpaywall = query_unpaywall(session, doi, args.email)
        if unpaywall:
            result.is_oa = unpaywall["is_oa"]
            result.oa_status = unpaywall["oa_status"]
            if unpaywall.get("landing"):
                result.landing_url = unpaywall["landing"]
            candidates += [("unpaywall", u) for u in unpaywall["pdf_urls"]]
    except requests.RequestException as exc:
        result.note = f"Unpaywall недоступен ({exc.__class__.__name__}); "
    time.sleep(args.sleep)

    # 3. Europe PMC
    try:
        epmc = query_europepmc(session, doi)
        if epmc:
            result.pmcid = epmc["pmcid"]
            if epmc["is_oa"]:
                result.is_oa = True
            candidates += [("europepmc", u) for u in epmc["pdf_urls"]]
    except requests.RequestException as exc:
        result.note += f"Europe PMC недоступен ({exc.__class__.__name__}); "
    time.sleep(args.sleep)

    if not candidates:
        result.status = "no_oa"
        result.note += "легального открытого PDF не найдено"
        return result

    if args.dry_run:
        result.status = "no_oa" if not candidates else "pending"
        result.pdf_url = candidates[0][1]
        result.pdf_source = candidates[0][0]
        result.note += "--dry-run: скачивание не выполнялось"
        return result

    # 4. Скачивание — пробуем ссылки по очереди
    seen: set[str] = set()
    for source, url in candidates:
        if url in seen:
            continue
        seen.add(url)
        ok, detail = download_pdf(session, url, target)
        result.tried.append(f"{source}: {url} -> {'OK ' + detail if ok else detail}")
        if ok:
            result.status = "ok"
            result.file = str(target.relative_to(out_dir))
            result.pdf_url = url
            result.pdf_source = source
            result.note += detail
            return result
        time.sleep(args.sleep)

    result.status = "no_oa"
    result.note += f"все {len(seen)} ссылок отдали не PDF (пейволл или заглушка)"
    return result


# --------------------------------------------------------------------------- #
# Отчёты
# --------------------------------------------------------------------------- #

STATUS_LABEL = {
    "ok": "скачано",
    "skipped": "уже было",
    "no_oa": "нет открытого доступа",
    "no_doi": "DOI не найден",
    "manual": "вручную",
    "failed": "ошибка",
    "pending": "не качалось (dry-run)",
}


def write_csv(results: list[Outcome], path: Path) -> None:
    fields = [f for f in Outcome.__dataclass_fields__ if f != "tried"]
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for item in results:
            writer.writerow({k: v for k, v in asdict(item).items() if k in fields})


def write_report(results: list[Outcome], path: Path, args) -> None:
    by_status: dict[str, list[Outcome]] = {}
    for item in results:
        by_status.setdefault(item.status, []).append(item)

    got = by_status.get("ok", []) + by_status.get("skipped", [])
    lines: list[str] = []
    add = lines.append

    add("# Отчёт о выкачке источников\n")
    add(f"Запуск: уровни `{args.level}`, всего обработано записей — **{len(results)}**.\n")
    add("| Итог | Штук |")
    add("|---|---|")
    for status in ("ok", "skipped", "no_oa", "no_doi", "manual", "failed", "pending"):
        count = len(by_status.get(status, []))
        if count:
            add(f"| {STATUS_LABEL[status]} | {count} |")
    add("")
    non_manual = [r for r in results if r.status != "manual"]
    if non_manual:
        add(f"**Покрытие полными текстами: {len(got)} из {len(non_manual)} "
            f"({100 * len(got) / len(non_manual):.0f}%).**\n")

    add("---\n")
    add("## Скачано\n")
    if got:
        add("| # | Файл | OA | Источник | Ссылка |")
        add("|---|---|---|---|---|")
        for item in sorted(got, key=lambda x: x.id):
            add(f"| {item.id} | `{item.file}` | {item.oa_status or '—'} | "
                f"{item.pdf_source or '—'} | {item.landing_url} |")
    else:
        add("_Пусто._")
    add("")

    add("## Осталось добыть вручную\n")
    manual = (by_status.get("no_oa", []) + by_status.get("no_doi", [])
              + by_status.get("failed", []) + by_status.get("manual", []))
    if manual:
        add("Порядок действий: институциональный доступ / ЭБС → сайт журнала → "
            "запрос PDF у автора по e-mail (corresponding author указан в статье).\n")
        add("| # | Библиография | Причина | Куда идти |")
        add("|---|---|---|---|")
        for item in sorted(manual, key=lambda x: x.id):
            where = item.landing_url or (f"https://doi.org/{item.doi}" if item.doi else "поиск в PubMed по названию")
            reason = STATUS_LABEL[item.status]
            if item.note:
                reason += f" — {item.note.strip('; ')}"
            citation = item.citation.replace("|", "/")
            add(f"| {item.id} | {citation} | {reason} | {where} |")
    else:
        add("_Пусто — взялось всё._")
    add("")

    low = [r for r in results if r.doi and r.match_score < 0.85]
    if low:
        add("## Проверить сопоставление вручную\n")
        add("Crossref подобрал DOI с неполным совпадением названия — стоит "
            "убедиться, что это та самая работа.\n")
        add("| # | Ожидалось | Найдено | Score | DOI |")
        add("|---|---|---|---|---|")
        for item in sorted(low, key=lambda x: x.match_score):
            expected = item.citation.split(". ")[1][:80] if ". " in item.citation else item.citation[:80]
            add(f"| {item.id} | {expected.replace('|', '/')} | "
                f"{item.matched_title[:80].replace('|', '/')} | {item.match_score} | {item.doi} |")
        add("")

    path.write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------- #

def select(refs: Iterable[dict], args) -> list[dict]:
    chosen = list(refs)
    if args.only:
        wanted = {x.upper() for x in args.only}
        return [r for r in chosen if r["id"].upper() in wanted]
    if args.level != "all":
        levels = set(args.level.upper())
        chosen = [r for r in chosen if r["level"] in levels]
    return chosen


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Легальная выкачка полных текстов по references.json (Crossref + Unpaywall + Europe PMC)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--email", required=True,
                        help="ваш e-mail — обязателен для Crossref polite pool и Unpaywall")
    parser.add_argument("--refs", default=str(Path(__file__).with_name("references.json")))
    parser.add_argument("--out", default=str(Path(__file__).with_name("downloads")))
    parser.add_argument("--level", default="A", choices=["A", "B", "E", "AB", "ABE", "all"],
                        help="какие уровни качать (по умолчанию A)")
    parser.add_argument("--only", nargs="*", help="конкретные ID, например A4.1 A5.1")
    parser.add_argument("--dry-run", action="store_true",
                        help="только отрезолвить DOI и OA-статус, ничего не скачивать")
    parser.add_argument("--force", action="store_true", help="перекачать даже то, что уже есть")
    parser.add_argument("--sleep", type=float, default=1.0, help="пауза между запросами, сек")
    parser.add_argument("--timeout", type=int, default=60, help="таймаут HTTP, сек")
    args = parser.parse_args()

    if "@" not in args.email:
        return _fail("--email должен быть настоящим адресом: он уходит в Crossref и Unpaywall")

    refs_path = Path(args.refs)
    if not refs_path.exists():
        return _fail(f"не найден файл со списком: {refs_path}")

    data = json.loads(refs_path.read_text(encoding="utf-8"))
    refs = select(data["references"], args)
    if not refs:
        return _fail("под заданный фильтр не попало ни одной записи")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    session = build_session(args.email, args.timeout)

    print(f"Записей к обработке: {len(refs)}. Папка: {out_dir}")
    if args.dry_run:
        print("Режим --dry-run: только резолвинг DOI и проверка OA-статуса.\n")

    results: list[Outcome] = []
    for index, ref in enumerate(refs, 1):
        prefix = f"[{index:>2}/{len(refs)}] {ref['id']:<6}"
        print(f"{prefix} {ref['title'][:64]}...", flush=True)
        try:
            outcome = process(session, ref, args, out_dir)
        except Exception as exc:  # одна плохая запись не должна ронять весь прогон
            outcome = Outcome(id=ref["id"], level=ref["level"], block=ref["block"],
                              citation=citation_of(ref), status="failed",
                              note=f"{exc.__class__.__name__}: {exc}")
        results.append(outcome)
        print(f"{' ' * len(prefix)} -> {STATUS_LABEL[outcome.status]}"
              f"{' | ' + outcome.doi if outcome.doi else ''}"
              f"{' | ' + outcome.note if outcome.note else ''}", flush=True)

    write_csv(results, out_dir / "results.csv")
    write_report(results, out_dir / "report.md", args)
    (out_dir / "manifest.json").write_text(
        json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2), encoding="utf-8"
    )

    ok = sum(1 for r in results if r.status in {"ok", "skipped"})
    total = sum(1 for r in results if r.status != "manual")
    print(f"\nГотово: {ok} из {total} полных текстов.")
    print(f"Отчёт: {out_dir / 'report.md'}")
    print(f"Таблица: {out_dir / 'results.csv'}")
    return 0


def _fail(message: str) -> int:
    print(f"Ошибка: {message}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
