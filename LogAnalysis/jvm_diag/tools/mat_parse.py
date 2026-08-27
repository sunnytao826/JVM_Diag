from __future__ import annotations

import logging
import re
from pathlib import Path

from bs4 import BeautifulSoup

from jvm_diag.tools.mat_report import generate_mat_html_report

logger = logging.getLogger(__name__)


def _clean_text(text) -> str:
    if not text:
        return ""
    return re.sub(r"\[.*?\]", "", str(text)).strip()


def _table_to_dict_list(table) -> list[dict]:
    if not table:
        return []
    rows = table.find_all("tr")
    if not rows:
        return []
    headers = [_clean_text(th.get_text()) for th in rows[0].find_all(["th", "td"])]
    data = []
    for row in rows[1:]:
        cells = row.find_all(["td", "th"])
        if len(cells) != len(headers):
            continue
        data.append({headers[i]: _clean_text(cell.get_text()) for i, cell in enumerate(cells)})
    return data


def _detect_page_type(soup) -> str:
    title = soup.title.string if soup.title else ""
    body_text = soup.get_text()
    if "Problem Suspect" in title or ("Description" in body_text and "occupy" in body_text):
        return "problem_suspect"
    if "Top Consumers" in title or "Biggest Objects" in body_text:
        return "top_consumers"
    if "Class Histogram" in title or ("Class Name" in body_text and "Objects" in body_text):
        return "class_histogram"
    return "unknown"


def _parse_problem_suspect(soup) -> dict:
    data = {
        "description": "",
        "keywords": [],
        "suspect_objects_by_class": [],
        "all_objects_retained_by_suspects": [],
        "reference_pattern": [],
    }
    desc_label = soup.find(string=re.compile(r"Description", re.IGNORECASE))
    if desc_label and desc_label.parent:
        next_td = desc_label.parent.find_next_sibling()
        if next_td:
            data["description"] = _clean_text(next_td.get_text())
    kw_label = soup.find(string=re.compile(r"Keywords", re.IGNORECASE))
    if kw_label and kw_label.parent:
        next_td = kw_label.parent.find_next_sibling()
        if next_td:
            data["keywords"] = [k.strip() for k in next_td.get_text().split() if k.strip()]
    tables = soup.find_all("table")
    if len(tables) >= 1:
        data["suspect_objects_by_class"] = _table_to_dict_list(tables[0])
    if len(tables) >= 2:
        data["all_objects_retained_by_suspects"] = _table_to_dict_list(tables[1])
    if len(tables) >= 3:
        data["reference_pattern"] = _table_to_dict_list(tables[2])
    return data


def _parse_top_consumers(soup) -> dict:
    labels = [
        "biggest_objects",
        "biggest_top_level_dominator_classes",
        "biggest_top_level_dominator_class_loaders",
        "biggest_top_level_dominator_packages",
    ]
    tables = soup.find_all("table")
    return {key: _table_to_dict_list(tables[i]) if i < len(tables) else [] for i, key in enumerate(labels)}


def _parse_class_histogram(soup) -> dict:
    tables = soup.find_all("table")
    return {"class_histogram": _table_to_dict_list(tables[0]) if tables else []}


def parse_mat_pages(heap_file: str, mat_script: str | None = None) -> dict:
    pages_dir = Path(generate_mat_html_report(heap_file, mat_script=mat_script))
    all_results = {}
    for html_file in pages_dir.glob("*.html"):
        try:
            soup = BeautifulSoup(html_file.read_text(encoding="utf-8", errors="ignore"), "html.parser")
        except OSError as exc:
            logger.warning("Failed to read %s: %s", html_file, exc)
            continue
        page_type = _detect_page_type(soup)
        parsers = {
            "problem_suspect": _parse_problem_suspect,
            "top_consumers": _parse_top_consumers,
            "class_histogram": _parse_class_histogram,
        }
        parser = parsers.get(page_type)
        if not parser:
            continue
        all_results[html_file.name] = {"page_type": page_type, "data": parser(soup)}
    return {
        "source_directory": str(pages_dir.resolve()),
        "files_parsed": len(all_results),
        "results": all_results,
    }
