#!/usr/bin/env bash
set -euo pipefail

uv sync
uv run ruff check .
uv run mypy src
uv run pytest

python - <<'PY'
from pathlib import Path
import re

files = [Path("README.md"), *sorted(Path("docs").glob("*.md"))]
missing = []
for file in files:
    text = file.read_text(encoding="utf-8")
    for match in re.finditer(r"\[[^\]]+\]\(([^)]+)\)", text):
        target = match.group(1).split("#", 1)[0]
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        path = (file.parent / target).resolve()
        ok = path.is_dir() if target.endswith("/") else path.exists()
        if not ok:
            missing.append(f"{file}: {target}")
if missing:
    raise SystemExit("\n".join(missing))
print("markdown links ok")
PY
