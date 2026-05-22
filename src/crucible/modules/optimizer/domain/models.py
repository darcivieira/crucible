from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from crucible.modules.optimizer.domain.assertions import Assertion

ProviderName = Literal[
    "ollama",
    "openai",
    "anthropic",
    "google",
    "openrouter",
    "vllm",
    "llamacpp",
    "fake",
]
ModelRole = Literal["target", "reasoning", "judge", "embedding"]
ExecutionBackendName = Literal["local", "distributed", "ray", "dask"]
SelectionStrategy = Literal["quality", "multi_objective"]
RunStatus = Literal["running", "completed", "failed", "aborted"]
StopReason = Literal[
    "threshold_reached",
    "max_iterations",
    "budget_exhausted",
    "time_exhausted",
    "plateau",
    "no_failures",
    "cancelled",
]


class Prompt(BaseModel):
    model_config = ConfigDict(frozen=True)

    template: str
    variables: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        return sha256(self.template.encode()).hexdigest()[:12]

    def render(self, input_text: str | None = None, **kwargs: Any) -> str:
        values = dict(kwargs)
        if input_text is not None:
            values.setdefault("input", input_text)
        return self.template.format(**values)

    @classmethod
    def from_file(cls, path: str | Path) -> Prompt:
        return cls(template=Path(path).read_text(encoding="utf-8"))


class TestCase(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    input: str
    expected_output: str
    assertion: Assertion
    weight: float = Field(default=1.0, gt=0.0)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


class Gabarito(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    version: str
    cases: list[TestCase]
    description: str | None = None

    @field_validator("cases")
    @classmethod
    def require_cases(cls, value: list[TestCase]) -> list[TestCase]:
        if not value:
            raise ValueError("gabarito must contain at least one case")
        return value

    @property
    def content_hash(self) -> str:
        payload = self.model_dump_json()
        return sha256(payload.encode()).hexdigest()[:12]

    @classmethod
    def from_yaml(cls, path: str | Path) -> Gabarito:
        with Path(path).open(encoding="utf-8") as file:
            return cls.model_validate(yaml.safe_load(file))

    @classmethod
    def from_json(cls, path: str | Path) -> Gabarito:
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))

    def split(self, train: float = 0.7, val: float = 0.15) -> tuple[Gabarito, Gabarito, Gabarito]:
        if train <= 0 or val < 0 or train + val >= 1:
            raise ValueError("split ratios must satisfy train > 0, val >= 0 and train + val < 1")
        if len(self.cases) < 3:
            raise ValueError("gabarito split requires at least 3 cases")
        cases = sorted(self.cases, key=lambda case: case.id)
        train_end = min(len(cases) - 2, max(1, int(len(cases) * train)))
        val_end = min(len(cases) - 1, max(train_end + 1, train_end + int(len(cases) * val)))
        return (
            self.model_copy(
                update={"cases": cases[:train_end], "version": f"{self.version}-train"}
            ),
            self.model_copy(
                update={"cases": cases[train_end:val_end], "version": f"{self.version}-val"}
            ),
            self.model_copy(update={"cases": cases[val_end:], "version": f"{self.version}-test"}),
        )


class ModelParams(BaseModel):
    temperature: float = 0.0
    max_tokens: int = 1024
    top_p: float | None = None
    seed: int | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        payload = json.dumps(self.model_dump(), sort_keys=True, default=str)
        return sha256(payload.encode()).hexdigest()[:12]


class ProviderRateLimit(BaseModel):
    max_concurrent: int = Field(default=4, gt=0)
    requests_per_minute: int | None = Field(default=None, gt=0)
    retry_attempts: int = Field(default=2, ge=0)
    retry_backoff_seconds: float = Field(default=0.5, ge=0.0)


class ModelSpec(BaseModel):
    provider: ProviderName
    model_id: str
    role: ModelRole
    params: ModelParams = Field(default_factory=ModelParams)
    rate_limit: ProviderRateLimit = Field(default_factory=ProviderRateLimit)
    cost_per_million_input_tokens_usd: float = 0.0
    cost_per_million_output_tokens_usd: float = 0.0
    context_window: int = 8192
    supports_json_mode: bool = False
    supports_tool_use: bool = False


class CompletionResult(BaseModel):
    text: str
    tokens_in: int = 0
    tokens_out: int = 0
    finish_reason: str = "stop"
    raw: dict[str, Any] = Field(default_factory=dict)


class ExecutionResult(BaseModel):
    test_case_id: str
    actual_output: str
    latency_ms: float
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    finish_reason: str = "stop"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    error: str | None = None


class Verdict(BaseModel):
    test_case: TestCase
    execution: ExecutionResult
    score: float = Field(ge=0.0, le=1.0)
    passed: bool
    assertion_detail: dict[str, Any] = Field(default_factory=dict)
    is_regression: bool = False


class OperationalMetrics(BaseModel):
    total_cost_usd: float = 0.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    total_tokens: int = 0


class ScoreReport(BaseModel):
    global_score: float = Field(ge=0.0, le=100.0)
    pass_rate: float = Field(ge=0.0, le=1.0)
    by_tag: dict[str, float] = Field(default_factory=dict)
    by_assertion_type: dict[str, float] = Field(default_factory=dict)
    worst_case_ids: list[str] = Field(default_factory=list)
    operational: OperationalMetrics = Field(default_factory=OperationalMetrics)


class ActiveLearningSuggestion(BaseModel):
    test_case_id: str
    input: str
    reason: str
    expected_output_hint: str | None = None
    tags: list[str] = Field(default_factory=list)
    score: float
    unstable: bool = False


class Diagnosis(BaseModel):
    pattern: str
    hypothesis: str
    category: str
    confidence: float = Field(ge=0.0, le=1.0)
    is_model_limitation: bool = False


class RefinementProposal(BaseModel):
    new_prompt: str
    diff_summary: str
    rationale: str
    expected_improvement: str = ""
    confidence: float = Field(ge=0.0, le=1.0)

    def violations(self, current: Prompt) -> list[str]:
        new = Prompt(template=self.new_prompt, variables=current.variables)
        violations: list[str] = []
        if new.content_hash == current.content_hash:
            violations.append("prompt idêntico ao atual")
        for variable in current.variables:
            if "{" + variable + "}" not in self.new_prompt:
                violations.append(f"variável ausente: {variable}")
        return violations


class IterationMemory(BaseModel):
    version: int
    prompt_hash: str
    score: float
    proposed_change: str | None = None
    diff_summary: str | None = None
    failure_pattern: str | None = None


class Iteration(BaseModel):
    version: int
    prompt: Prompt
    verdicts: list[Verdict]
    score_report: ScoreReport
    refinement_rationale: str | None = None
    diagnosis: Diagnosis | None = None
    diff_summary: str | None = None
    objective_score: float | None = None
    pareto_dominated: bool = False
    timestamp_started: datetime = Field(default_factory=lambda: datetime.now(UTC))
    timestamp_ended: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def score(self) -> float:
        return self.score_report.global_score


class OptimizationConfig(BaseModel):
    threshold: float = 95.0
    max_iterations: int = 10
    max_cost_usd: float = 5.0
    max_wallclock_seconds: int = 1800
    plateau_window: int = 3
    plateau_min_delta: float = 0.5
    parallelism: int = 4
    n_runs_per_case: int = 1
    max_failures_for_refinement: int = 10
    instability_std_threshold_ms: float = 250.0
    use_gabarito_split: bool = False
    train_ratio: float = 0.7
    val_ratio: float = 0.15
    execution_backend: ExecutionBackendName = "local"
    distributed_workers: int = Field(default=4, gt=0)
    selection_strategy: SelectionStrategy = "quality"
    objective_quality_weight: float = Field(default=1.0, ge=0.0)
    objective_cost_weight: float = Field(default=0.0, ge=0.0)
    objective_latency_weight: float = Field(default=0.0, ge=0.0)
    active_learning_suggestions: int = Field(default=0, ge=0)

    target_model: ModelSpec
    reasoning_model: ModelSpec
    judge_model: ModelSpec | None = None
    judge_models: list[ModelSpec] = Field(default_factory=list)
    embedding_model: ModelSpec | None = None


class OptimizationRun(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    config: OptimizationConfig
    gabarito_hash: str
    initial_prompt_hash: str
    iterations: list[Iteration] = Field(default_factory=list)
    status: RunStatus = "running"
    stop_reason: StopReason | None = None
    validation_scores: dict[str, float] = Field(default_factory=dict)
    pareto_frontier_versions: list[int] = Field(default_factory=list)
    active_learning_suggestions: list[ActiveLearningSuggestion] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ended_at: datetime | None = None

    @property
    def best_iteration(self) -> Iteration | None:
        if not self.iterations:
            return None
        if self.config.selection_strategy == "multi_objective":
            return max(
                self.iterations,
                key=lambda iteration: (
                    iteration.objective_score if iteration.objective_score is not None else -1e9,
                    iteration.score,
                ),
            )
        return max(self.iterations, key=lambda iteration: iteration.score)

    @property
    def total_cost_usd(self) -> float:
        return sum(
            verdict.execution.cost_usd
            for iteration in self.iterations
            for verdict in iteration.verdicts
        )

    @property
    def score_history(self) -> list[float]:
        return [iteration.score for iteration in self.iterations]


class CostEstimate(BaseModel):
    cases_count: int
    max_iterations: int
    target_input_tokens: int
    target_output_tokens: int
    reasoning_input_tokens: int
    reasoning_output_tokens: int
    estimated_target_cost_usd: float
    estimated_reasoning_cost_usd: float
    estimated_total_cost_usd: float
