#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${1:-.crucible-quickstart-real}"
CONFIG_PATH="$PROJECT_DIR/config.yaml"

uv run crucible init "$PROJECT_DIR"

if [[ "${CRUCIBLE_QUICKSTART_PROVIDER:-ollama}" == "fake" ]]; then
  python - <<PY
from pathlib import Path
import yaml

path = Path("$CONFIG_PATH")
config = yaml.safe_load(path.read_text())
config["target_model"] = {"provider": "fake", "model_id": "target", "role": "target"}
config["reasoning_model"] = {"provider": "fake", "model_id": "reasoning", "role": "reasoning"}
path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
PY
fi

uv run crucible validate \
  --prompt "$PROJECT_DIR/prompt.txt" \
  --gabarito "$PROJECT_DIR/gabarito.yaml" \
  --config "$CONFIG_PATH"

uv run crucible estimate-cost --config "$CONFIG_PATH"
uv run crucible optimize --config "$CONFIG_PATH"
uv run crucible report --run latest --format html
uv run crucible export --run latest --format prompt --output "$PROJECT_DIR/best_prompt.txt"

echo "Quickstart artifacts written to $PROJECT_DIR and .crucible/reports"
