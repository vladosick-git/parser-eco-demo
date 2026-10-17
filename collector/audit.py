"""Таблицы из docs/AUDIT.md -> data/sources.json для вкладки «Источники» на витрине.

Аудит остаётся единственным местом, где описаны источники: витрина его просто показывает.
"""

import re


def _cells(line: str) -> list[str]:
    return [c.strip().replace("**", "").replace("`", "") for c in line.strip().strip("|").split("|")]


def parse(markdown: str) -> dict:
    checked = re.search(r"(\d{4}-\d{2}-\d{2})", markdown)
    tables = []
    heading = ""
    lines = markdown.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("## "):
            heading = line[3:].strip()
        is_table = line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1])
        if is_table and heading.startswith("Раздел"):
            columns = _cells(line)
            rows = []
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(dict(zip(columns, _cells(lines[i]))))
                i += 1
            tables.append({"title": heading, "columns": columns, "rows": rows})
            continue
        i += 1
    return {"checked": checked.group(1) if checked else None, "tables": tables}
