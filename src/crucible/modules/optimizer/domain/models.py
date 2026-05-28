from __future__ import annotations

import json
import re
from collections.abc import Callable
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
ModelApiMode = Literal["chat_completions", "responses"]
OutputFormatType = Literal["text", "json_object", "json_schema"]
RunStatus = Literal["running", "completed", "failed", "aborted"]
RunMode = Literal["validate", "optimize", "compare"]
ProviderCacheOnError = Literal["fail", "fallback"]
OpenAIPromptCacheRetention = Literal["in_memory", "24h"]
TaskContractSource = Literal["prompt", "config", "gabarito", "heuristic"]
StopReason = Literal[
    "threshold_reached",
    "max_iterations",
    "budget_exhausted",
    "time_exhausted",
    "plateau",
    "no_failures",
    "cancelled",
    "validation_only",
    "reasoning_failed_to_refine",
    "comparison_completed",
]


def _literal_replacement(value: str) -> Callable[[re.Match[str]], str]:
    def replace(_match: re.Match[str]) -> str:
        return value

    return replace


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
        rendered = self.template
        for variable, value in values.items():
            replacement = str(value)
            rendered = re.sub(
                r"\{\s*" + re.escape(variable) + r"\s*\}",
                _literal_replacement(replacement),
                rendered,
            )
        return rendered

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


class ModelOutputFormat(BaseModel):
    type: OutputFormatType = "text"
    name: str = "crucible_output"
    strict: bool = True
    schema_: dict[str, Any] = Field(default_factory=dict, alias="schema")
    provider_options: dict[str, Any] = Field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        payload = json.dumps(self.model_dump(by_alias=True), sort_keys=True, default=str)
        return sha256(payload.encode()).hexdigest()[:12]


class ModelSpec(BaseModel):
    provider: ProviderName
    model_id: str
    role: ModelRole
    api_mode: ModelApiMode = "chat_completions"
    params: ModelParams = Field(default_factory=ModelParams)
    output_format: ModelOutputFormat = Field(default_factory=ModelOutputFormat)
    rate_limit: ProviderRateLimit = Field(default_factory=ProviderRateLimit)
    cost_per_million_input_tokens_usd: float = 0.0
    cost_per_million_cached_input_tokens_usd: float = 0.0
    cost_per_million_output_tokens_usd: float = 0.0
    context_window: int = 8192
    supports_json_mode: bool = False
    supports_tool_use: bool = False


class CompletionResult(BaseModel):
    text: str
    tokens_in: int = 0
    cached_tokens_in: int = 0
    tokens_out: int = 0
    finish_reason: str = "stop"
    raw: dict[str, Any] = Field(default_factory=dict)


class ExecutionResult(BaseModel):
    test_case_id: str
    actual_output: str
    latency_ms: float
    tokens_in: int = 0
    cached_tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    provider_cache_id: str | None = None
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
    cached_tokens: int = 0


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


class ContractRule(BaseModel):
    text: str
    source: TaskContractSource
    critical: bool = True


class TaskContract(BaseModel):
    objective: str = ""
    output_contract: dict[str, Any] = Field(default_factory=dict)
    invariants: list[ContractRule] = Field(default_factory=list)
    literal_extraction_fields: list[str] = Field(default_factory=list)
    negative_rules: list[ContractRule] = Field(default_factory=list)
    examples: list[dict[str, Any]] = Field(default_factory=list)


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
    preserved_invariants: list[str] = Field(default_factory=list)
    changed_behavior: list[str] = Field(default_factory=list)
    risk_of_regression: str = "unknown"
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


class RefinementRepairAttempt(BaseModel):
    attempt: int = Field(ge=1)
    violations: list[str] = Field(default_factory=list)
    proposed_prompt: str = ""
    diff_summary: str = ""
    rationale: str = ""


class ProviderCacheConfig(BaseModel):
    enabled: bool = False
    ttl_seconds: int = Field(default=3600, gt=0)
    cache_inputs: bool = True
    on_error: ProviderCacheOnError = "fail"
    openai_retention: OpenAIPromptCacheRetention = "in_memory"


class ComparisonTarget(BaseModel):
    label: str
    model: ModelSpec


class ComparisonWinner(BaseModel):
    label: str | None = None
    score: float = 0.0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    value_score: float = 0.0


class ComparisonCaseWinner(BaseModel):
    test_case_id: str
    best_score: str | None = None
    lowest_cost: str | None = None
    best_value: str | None = None


class ComparisonSummary(BaseModel):
    best_score: ComparisonWinner = Field(default_factory=ComparisonWinner)
    lowest_cost: ComparisonWinner = Field(default_factory=ComparisonWinner)
    best_value: ComparisonWinner = Field(default_factory=ComparisonWinner)
    case_winners: list[ComparisonCaseWinner] = Field(default_factory=list)


class IterationMemory(BaseModel):
    version: int
    prompt_hash: str
    score: float
    proposed_change: str | None = None
    diff_summary: str | None = None
    failure_pattern: str | None = None
    rejected_refinement_reason: str | None = None


class Iteration(BaseModel):
    version: int
    prompt: Prompt
    verdicts: list[Verdict]
    score_report: ScoreReport
    comparison_label: str | None = None
    target_model: ModelSpec | None = None
    refinement_rationale: str | None = None
    diagnosis: Diagnosis | None = None
    diff_summary: str | None = None
    refinement_rejected_reason: str | None = None
    refinement_repair_attempts: list[RefinementRepairAttempt] = Field(default_factory=list)
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
    max_refinement_repair_attempts: int = Field(default=5, ge=1)
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
    provider_cache: ProviderCacheConfig = Field(default_factory=ProviderCacheConfig)
    comparison_models: list[ComparisonTarget] = Field(default_factory=list)
    comparison_value_quality_weight: float = Field(default=0.8, ge=0.0)
    comparison_value_cost_weight: float = Field(default=0.2, ge=0.0)
    comparison_value_latency_weight: float = Field(default=0.0, ge=0.0)

    target_model: ModelSpec | None = None
    reasoning_model: ModelSpec | None = None
    judge_model: ModelSpec | None = None
    judge_models: list[ModelSpec] = Field(default_factory=list)
    embedding_model: ModelSpec | None = None


class OptimizationRun(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    run_mode: RunMode = "optimize"
    config: OptimizationConfig
    task_contract: TaskContract | None = None
    gabarito_hash: str
    initial_prompt_hash: str
    iterations: list[Iteration] = Field(default_factory=list)
    status: RunStatus = "running"
    stop_reason: StopReason | None = None
    validation_scores: dict[str, float] = Field(default_factory=dict)
    comparison_summary: ComparisonSummary | None = None
    provider_cache_warnings: list[str] = Field(default_factory=list)
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
