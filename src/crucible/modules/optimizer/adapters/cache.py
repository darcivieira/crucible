from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

from crucible.modules.optimizer.domain.models import ExecutionResult, ModelSpec, Prompt


class JsonlExecutionCache:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    async def get(self, key: str) -> ExecutionResult | None:
        if not self.path.exists():
            return None
        with self.path.open(encoding="utf-8") as file:
            for line in file:
                payload = json.loads(line)
                if payload["key"] == key:
                    return ExecutionResult.model_validate(payload["value"])
        return None

    async def set(self, key: str, value: ExecutionResult) -> None:
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps({"key": key, "value": value.model_dump(mode="json")}) + "\n")


def execution_cache_key(prompt: Prompt, input_text: str, model: ModelSpec) -> str:
    model_payload = json.dumps(model.model_dump(mode="json", by_alias=True), sort_keys=True)
    payload = "|".join(
        [
            prompt.content_hash,
            input_text,
            sha256(model_payload.encode()).hexdigest(),
        ]
    )
    return sha256(payload.encode()).hexdigest()
