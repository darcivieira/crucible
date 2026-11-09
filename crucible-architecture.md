# Crucible — Prompt Optimization Framework

> Domain agnostic framework for iterative optimization of prompts in LLMs/SLMs, driven by reasoning
  models and empirically validated against versioned benchmarks.

**Version:** 1.0 — Architecture Document
**Author:** Darci
**Status:** Initial specification / MVP design

---

## Contents

1. [Vision and Positioning](#1-vision-and-positioning)
2. [Central Concepts](#2-central-concepts)
3. [The Optimization Loop](#3-the-optimization-loop)
4. [Scoring System](#4-scoring-system)
5. [Architecture (Clean Architecture + DDD)](#5-architecture-clean-architecture--ddd)
6. [Domain Models (Pydantic v2)](#6-domain-models-pydantic-v2)
7. [Refinement Engine](#7-refinement-engine)
8. [Technical Decisions](#8-technical-decisions)
9. [UX and Interfaces](#9-ux-and-interfaces)
10. [Project Structure](#10-project-structure)
11. [Roadmap MVP](#11-roadmap-mvp)
12. [Risks and Mitigations](#12-risks-and-mitigations)
13. [Competitive Positioning](#13-competitive-positioning)

---

## 1. Vision and Positioning

### 1.1 Thesis

 Crucible is an **iterative prompt compiler**. Given a draft prompt, an expected input/output
benchmark, a target model (smaller LLM or SLM) and a reasoning model, the framework executes an
execution loop → evaluation → diagnosis → refinement until reaching a quality threshold or
exhausting the budget.

### 1.2 Primary Job-to-be-done

**Reasoning-driven prompt optimization against an empirical benchmark, independent of domain and
provider.**

### 1.3 Differentiation

- **Real multi-provider support**: Ollama, llama.cpp, vLLM as first-class citizens (not
  afterthought)
- **Architecture separation between Target Model and reasoning model**: two distinct roles,
  independently configurable
- **Loop with memory between iterations**: Refiner sees complete history of attempts, not
  single-shot
- **Operational + qualitative scores together**: quality × cost × latency as explicit trade-off
- **Benchmark as first class versioned entity**: Prompt/benchmark separation allows trivial
  regression

### 1.4 What IS NOT

- Not observability/tracing platform (Langfuse, Phoenix)
- Not prompt management UI (Promptlayer, Humanloop)
- Not fine-tuning framework
- Not agentic orchestration (Langgraph, AgentForge)
- It's not serving infrastructure

---

## 2. Central Concepts

| Concept | Definition |
| ---------- | ----------- |
| **Prompt** | Template versioned with placeholders and metadata. Identified by content hash. |
| **Benchmark** | Versioned collection of TestCases (input → expected_output + assertion). |
| **TestCase** | Triple (input, expected_output, assertion) + optional weight + tags. |
| **TargetModel** | Model to be optimized (smaller LLM or SLM). Runs many times. |
| **ReasoningModel** | Critic/refiner model. Runs fewer times but is expensive. |
| **OptimizationRun** | Aggregate root. Encapsulates the entire loop of an optimization. |
| **Iteration** | One pass through the loop: (prompt_version, run, score, refinement). |
| **Assertion** | Validation rule applied to a pair (expected, current). |
| **Verdict** | Result of an individual execution: pass/fail + score + operational metrics. |
| **Budget** | Combined limits: max_iterations, max_cost_usd, max_wallclock_seconds. |

---

## 3. The Optimization Loop

### 3.1 Conceptual Flow

```
┌─────────────────────────────────────────────────────────────┐
│  INPUT                                                      │
│  - prompt_v0 (initial template)                             │
│  - benchmark (list of TestCases)                            │
│  - target_model (ex: gemma3:4b via Ollama)                  │
│  - reasoning_model (ex: gpt-5 or gemini-2.5-pro)            │
│  - config (threshold, budget, stopping criteria)            │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  EXECUTION             │
              │  For each TestCase:    │
              │  - render(prompt, input)│
              │  - call(target_model)  │
              │  - capture output,     │
              │    latency, tokens     │
              │  (parallel, respecting │
              │   rate limits)         │
              └───────────┬────────────┘
                          │
                          ▼
              ┌────────────────────────┐
              │  SCORING               │
              │  For each execution:   │
              │  - apply assertion     │
              │  - calculate score     │
              │  Aggregate:            │
              │  - global score        │
              │  - breakdown by tag    │
              │  - total cost          │
              └───────────┬────────────┘
                          │
                          ▼
                  ┌───────┴───────┐
                  │ Stop?         │
                  │ - score≥thresh│
                  │ - plateau     │
                  │ - budget out  │
                  └─┬───────────┬─┘
                Yes │           │ No
                    ▼           ▼
              ┌────────┐  ┌──────────────────┐
              │ RETURN │  │  DIAGNOSIS       │
              │ best   │  │  Reasoning model │
              │ prompt │  │  analyzes errors:│
              └────────┘  │  - pattern       │
                          │  - hypothesis    │
                          │  - root cause    │
                          └─────────┬────────┘
                                    │
                                    ▼
                          ┌──────────────────┐
                          │  REFINEMENT      │
                          │  Reasoning model │
                          │  proposes:       │
                          │  - prompt_v(N+1) │
                          │  - rationale     │
                          │  - diff changes  │
                          └─────────┬────────┘
                                    │
                                    └──→ back to EXECUTION
```

### 3.2 Stop Criteria (combined)

```python
def should_stop(run: OptimizationRun) -> StopReason | None:
    if run.best_score >= run.config.threshold:
        return StopReason.THRESHOLD_REACHED
    if run.iterations_count >= run.config.max_iterations:
        return StopReason.MAX_ITERATIONS
    if run.total_cost_usd >= run.config.max_cost_usd:
        return StopReason.BUDGET_EXHAUSTED
    if run.wallclock_seconds >= run.config.max_wallclock_seconds:
        return StopReason.TIME_EXHAUSTED
    if detect_plateau(run.score_history, window=3, min_delta=0.5):
        return StopReason.PLATEAU
    return None
```

### 3.3 Divergent Case Selection

Sending all errors to the reasoning model is wasteful. Hybrid strategy:

```python
def select_failures_for_refinement(
    verdicts: list[Verdict],
    max_cases: int = 10,
    max_tokens: int = 8000,
) -> list[Verdict]:
    failures = [v for v in verdicts if not v.passed]

    # 1. Regressions (previously passed, now fail) — highest priority
    regressions = [v for v in failures if v.is_regression]

    # 2. Top-K worst cases by score
    worst = sorted(failures, key=lambda v: v.score)[:max_cases]

    # 3. Stratified sampling by tag/category
    stratified = stratified_sample(failures, by="tags", k=max_cases)

    # 4. Merge respeitando token budget
    selected = merge_dedupe([*regressions, *worst, *stratified])
    return truncate_by_tokens(selected, max_tokens)
```

### 3.4 Memory Between Iterations

The refiner receives **complete history of attempts** to avoid repeating faulty suggestions:

```python
class IterationMemory(BaseModel):
    version: int
    prompt_hash: str
    score_before: float
    score_after: float
    delta: float
    proposed_change: str  # refiner rationale
    diff_summary: str     # summarized prompt diff
    failure_pattern: str  # identified failure pattern
```

### 3.5 Best-Ever Tracking

Always return **best prompt ever seen**, not the last:

```python
class OptimizationRun:
    best_iteration: Iteration  # high-water mark
    last_iteration: Iteration  # last executed

    def update_best(self, candidate: Iteration) -> None:
        if candidate.score > self.best_iteration.score:
            self.best_iteration = candidate
```

---

## 4. Scoring System

### 4.1 Assertions Hierarchy (growing cost)

#### Tier 1 — Deterministics

| Assertion | Description | Typical use |
| ----------- | ----------- | ------------ |
| `ExactMatch` | literal equality (with normalize options) | IDs, formatted values |
| `NumericMatch` | Numerical equality with tolerance | Monetary values, calculations |
| `Regex` | Pattern matching | Format validation |
| `JsonEqual` | JSON Deep equal | Structured outputs |
| `JsonSchema` | Validation by schema Pydantic | Structural compliance |
| `Contains` | Substring/keyword presence | One-off checks |

#### Tier 2 — Structural

| Assertion | Description |
| ----------- | ----------- |
| `FieldByField` | Compare JSON fields with individual weights |
| `PydanticModel` | Valid + compare via Pydantic model with field tolerance |

#### Tier 3 — Semantics

| Assertion | Description | Model |
| ----------- | ----------- | -------- |
| `EmbeddingSimilarity` | Cosine similarity on embeddings | text-embedding-3, BGE, etc. |
| `BertScore` | F1 on contextualized tokens | BERT model |

#### Tier 4 — LLM-as-Judge

| Assertion | Description |
| ----------- | ----------- |
| `LLMJudge` | Reasoning model evaluates expected vs actual with an explicit rubric |
| `LLMJudgeWithRationale` | Idem + returns structured justification |

### 4.2 Declaration in Benchmark

Assertions are **by TestCase**, not global:

```python
benchmark = Benchmark(
    name="extracao-cnpj-v1",
    cases=[
        TestCase(
            id="case-001",
            input="Extract the CNPJ from this draft: ABC SA, CNPJ 12.345.678/0001-90...",
            expected_output="12.345.678/0001-90",
            assertion=ExactMatch(normalize=True),
            weight=1.0,
            tags=["extraction", "cnpj"],
        ),
        TestCase(
            id="case-002",
            input="Summarize this contract in 3 sentences: ...",
            expected_output="The contract establishes the terms of service...",
            assertion=EmbeddingSimilarity(threshold=0.85),
            weight=2.0,
            tags=["summarization"],
        ),
        TestCase(
            id="case-003",
            input="Evaluate the risk of this transaction: ...",
            expected_output="High risk due to...",
            assertion=LLMJudge(
                rubric="Evaluate whether the response correctly identifies the risk level and justifies it.",
                pass_threshold=0.7,
            ),
            weight=3.0,
            tags=["reasoning", "risk-assessment"],
        ),
    ],
)
```

### 4.3 Aggregation

```python
def aggregate_score(verdicts: list[Verdict]) -> ScoreReport:
    total_weight = sum(v.test_case.weight for v in verdicts)
    weighted_sum = sum(v.score * v.test_case.weight for v in verdicts)
    global_score = (weighted_sum / total_weight) * 100

    return ScoreReport(
        global_score=global_score,
        pass_rate=sum(1 for v in verdicts if v.passed) / len(verdicts),
        by_tag=group_by_tag(verdicts),
        by_assertion_type=group_by_assertion(verdicts),
        worst_cases=sorted(verdicts, key=lambda v: v.score)[:10],
        operational=OperationalMetrics(
            total_cost_usd=sum(v.cost_usd for v in verdicts),
            p50_latency_ms=percentile([v.latency_ms for v in verdicts], 50),
            p95_latency_ms=percentile([v.latency_ms for v in verdicts], 95),
            total_tokens=sum(v.tokens_in + v.tokens_out for v in verdicts),
        ),
    )
```

---

## 5. Architecture (Clean Architecture + DDD)

### 5.1 Bounded Contexts

```
┌─────────────────────────────────────────────────────────────┐
│  AUTHORING CONTEXT                                          │
│  Role: define prompts, benchmarks, configs                   │
│  Aggregates:Prompt, Benchmark, OptimizationConfig            │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  OPTIMIZATION CONTEXT                                       │
│  Role: run the loop, refine prompts                         │
│  Aggregates:OptimizationRun, Iteration                      │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  ANALYSIS CONTEXT                                           │
│  Role: compare runs, generate reports                       │
│  Aggregates:ComparisonReport, EvolutionReport               │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 Layers (Clean Architecture)

```
┌──────────────────────────────────────────────────────────┐
│  INTERFACES                                              │
│  CLI (Typer)  │  Python SDK  │  Web Dashboard (FastAPI)  │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────┐
│  APPLICATION (Use Cases)                                 │
│  OptimizePromptUseCase                                   │
│  RunSingleIterationUseCase                               │
│  ScoreExecutionUseCase                                   │
│  DiagnoseFailuresUseCase                                 │
│  RefinePromptUseCase                                     │
│  CompareIterationsUseCase                                │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────┐
│  DOMAIN (Pure)                                           │
│  Entities: Prompt, TestCase, Benchmark, OptimizationRun   │
│  Value Objects: Score, Verdict, Budget, Assertion        │
│  Domain Services: ScoringService, StoppingCriteria       │
│  Domain Events: IterationCompleted, ThresholdReached     │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────┐
│  INFRASTRUCTURE (Adapters)                               │
│  Providers: OllamaAdapter, OpenAIAdapter, AnthropicAd... │
│  Storage: SqliteRepo, PostgresRepo                       │
│  Embeddings: OpenAIEmbedder, LocalBgeEmbedder            │
│  Telemetry: OTelExporter, LangfuseExporter (optional)    │
└──────────────────────────────────────────────────────────┘
```

### 5.3 Dependency Rule

Domain does not import Application; Application does not import Infrastructure. Adapters implement
ports (Protocols) defined in Domain/Application.

```python
# domain/ports/model_provider.py
from typing import Protocol

class ModelProvider(Protocol):
    async def complete(
        self, prompt: str, params: ModelParams
    ) -> CompletionResult: ...

# infrastructure/providers/ollama.py
class OllamaAdapter:
    async def complete(self, prompt, params) -> CompletionResult:
        # concrete implementation
        ...
```

---

## 6. Domain Models (Pydantic v2)

### 6.1 Core

```python
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal
from datetime import datetime
from hashlib import sha256

class Prompt(BaseModel):
    model_config = ConfigDict(frozen=True)

    template: str
    variables: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        return sha256(self.template.encode()).hexdigest()[:12]

    def render(self, **kwargs) -> str:
        return self.template.format(**kwargs)


class Assertion(BaseModel):
    """Base for all assertions. Polymorphism through a type discriminator."""
    type: str

    async def evaluate(
        self, expected: str, actual: str, context: "AssertionContext"
    ) -> "AssertionResult":
        raise NotImplementedError


class TestCase(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    input: str
    expected_output: str
    assertion: Assertion
    weight: float = 1.0
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


class Benchmark(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    version: str
    cases: list[TestCase]
    description: str | None = None

    @property
    def content_hash(self) -> str:
        payload = self.model_dump_json()
        return sha256(payload.encode()).hexdigest()[:12]

    def split(self, train: float = 0.7, val: float = 0.15) -> tuple[
        "Benchmark", "Benchmark", "Benchmark"
    ]:
        """Stratified train/val/test split."""
        ...
```

### 6.2 Models and Execution

```python
ProviderName = Literal["ollama", "openai", "anthropic", "google", "openrouter"]
ModelRole = Literal["target", "reasoning", "judge", "embedding"]


class ModelParams(BaseModel):
    temperature: float = 0.0
    max_tokens: int = 1024
    top_p: float | None = None
    seed: int | None = None
    extra: dict[str, object] = Field(default_factory=dict)


class ModelSpec(BaseModel):
    provider: ProviderName
    model_id: str
    role: ModelRole
    params: ModelParams = Field(default_factory=ModelParams)

    # Operational metadata
    cost_per_million_input_tokens_usd: float = 0.0
    cost_per_million_output_tokens_usd: float = 0.0
    context_window: int = 8192
    supports_json_mode: bool = False
    supports_tool_use: bool = False


class ExecutionResult(BaseModel):
    test_case_id: str
    actual_output: str
    latency_ms: float
    tokens_in: int
    tokens_out: int
    cost_usd: float
    finish_reason: str
    timestamp: datetime
    error: str | None = None


class Verdict(BaseModel):
    test_case: TestCase
    execution: ExecutionResult
    score: float  # 0.0 - 1.0
    passed: bool
    assertion_detail: dict[str, object] = Field(default_factory=dict)
    is_regression: bool = False  # passed in the previous iteration, failed now
```

### 6.3 Optimization

```python
class OptimizationConfig(BaseModel):
    threshold: float = 95.0
    max_iterations: int = 10
    max_cost_usd: float = 5.00
    max_wallclock_seconds: int = 1800
    plateau_window: int = 3
    plateau_min_delta: float = 0.5
    parallelism: int = 4
    n_runs_per_case: int = 1  # for non-deterministic SLMs

    target_model: ModelSpec
    reasoning_model: ModelSpec
    judge_model: ModelSpec | None = None  # default = reasoning_model


class Iteration(BaseModel):
    version: int
    prompt: Prompt
    verdicts: list[Verdict]
    score_report: "ScoreReport"
    refinement_rationale: str | None = None
    diagnosis: str | None = None
    timestamp_started: datetime
    timestamp_ended: datetime

    @property
    def score(self) -> float:
        return self.score_report.global_score


class OptimizationRun(BaseModel):
    id: str
    config: OptimizationConfig
    benchmark_hash: str
    initial_prompt_hash: str
    iterations: list[Iteration] = Field(default_factory=list)
    status: Literal["running", "completed", "failed", "aborted"] = "running"
    stop_reason: str | None = None
    started_at: datetime
    ended_at: datetime | None = None

    @property
    def best_iteration(self) -> Iteration:
        return max(self.iterations, key=lambda it: it.score)

    @property
    def total_cost_usd(self) -> float:
        return sum(
            v.execution.cost_usd
            for it in self.iterations
            for v in it.verdicts
        )

    @property
    def score_history(self) -> list[float]:
        return [it.score for it in self.iterations]
```

---

## 7. Refinement Engine

### 7.1 Separation Diagnosis + Refactor

Two calls separated to the reasoning model for Best Quality:

```python
class DiagnoseFailuresUseCase:
    def __init__(self, reasoning_provider: ModelProvider):
        self._provider = reasoning_provider

    async def execute(
        self,
        prompt: Prompt,
        target_model: ModelSpec,
        failures: list[Verdict],
        history: list[IterationMemory],
    ) -> Diagnosis:
        diagnose_prompt = self._build_diagnose_prompt(
            prompt, target_model, failures, history
        )
        response = await self._provider.complete(diagnose_prompt, ...)
        return Diagnosis.parse(response)


class RefinePromptUseCase:
    def __init__(self, reasoning_provider: ModelProvider):
        self._provider = reasoning_provider

    async def execute(
        self,
        current_prompt: Prompt,
        diagnosis: Diagnosis,
        target_model: ModelSpec,
        history: list[IterationMemory],
    ) -> RefinementProposal:
        refine_prompt = self._build_refine_prompt(
            current_prompt, diagnosis, target_model, history
        )
        response = await self._provider.complete(refine_prompt, ...)
        return RefinementProposal.parse(response)
```

### 7.2 Diagnose Meta-Prompt

```
You are a prompt engineering expert evaluating failures of a {target_model_provider}/{target_model_id} model.

TARGET MODEL CONTEXT:
- Provider: {provider}
- Model ID: {model_id}
- Context window: {context_window}
- Known capabilities: {capabilities}
- Known limitations: {known_limitations}

CURRENT PROMPT (v{version}):
---
{current_prompt}
---

ATTEMPT HISTORY:
{history_summary}

CASES THAT FAILED IN THIS ITERATION ({n_failures} cases):

{for each failure:}
─── Case {id} (tags: {tags}, score: {score}) ───
INPUT:
{input}

EXPECTED OUTPUT:
{expected}

ACTUAL OUTPUT:
{actual}

ASSERTION TYPE: {assertion_type}
FAILURE DETAIL: {assertion_detail}

YOUR TASK:
1. Identify the dominant FAILURE PATTERN (do not list each failure individually)
2. Formulate a causal HYPOTHESIS about why the model fails
3. Categorize the failure:
   - INSTRUCTION_AMBIGUITY (ambiguous prompt)
   - MISSING_CONSTRAINT (missing explicit constraint)
   - WRONG_FORMAT (poorly specified output format)
   - MISSING_EXAMPLES (missing few-shot examples)
   - WRONG_EXAMPLES (inadequate few-shot examples)
   - MODEL_CAPABILITY (limitation of the model rather than the prompt)
   - INPUT_COMPLEXITY (input exceeds capacity)
   - OUTPUT_LENGTH (token limit)

Return JSON strictly following this schema:
{
  "pattern": "pattern description",
  "hypothesis": "causal hypothesis",
  "category": "INSTRUCTION_AMBIGUITY|MISSING_CONSTRAINT|...",
  "confidence": 0.0-1.0,
  "is_model_limitation": boolean
}
```

### 7.3 Refactor Meta-Prompt

```
You are a prompt engineering expert refactoring a prompt for the {target_model_id} model.

CURRENT PROMPT:
---
{current_prompt}
---

DIAGNOSIS:
- Failure pattern: {pattern}
- Hypothesis: {hypothesis}
- Category: {category}

CHANGE HISTORY (DO NOT REPEAT):
{for each past iteration:}
- v{n}: {proposed_change} → score {before}→{after} ({delta:+.1f})

CONSTRAINTS:
- Preserve the variables: {variables}
- Do not exceed {max_tokens_prompt} tokens in the prompt
- The target model DOES NOT support: {unsupported_features}

YOUR TASK:
Propose a NEW prompt (v{next_version}) that addresses the identified failure pattern.

PRINCIPLES:
- Make the smallest necessary change (do not rewrite everything)
- Justify every change
- If you tried a similar approach and it failed, try a different direction
- For SLMs: prefer more explicit instructions and concrete few-shot examples

Return JSON:
{
  "new_prompt": "...",
  "diff_summary": "list of concrete changes",
  "rationale": "why this change addresses the diagnosis",
  "expected_improvement": "qualitative prediction of the impact",
  "confidence": 0.0-1.0
}
```

### 7.4 Refiner Output Validation

```python
class RefinementProposal(BaseModel):
    new_prompt: str
    diff_summary: str
    rationale: str
    expected_improvement: str
    confidence: float = Field(ge=0.0, le=1.0)

    def validate_against(self, current: Prompt) -> list[str]:
        """Return a list of violations. Empty = OK."""
        violations = []
        new = Prompt(template=self.new_prompt)

        # Variables preserved?
        if set(current.variables) != set(new.variables):
            violations.append("variables changed")

        # Different hash? (differs from the current prompt)
        if new.content_hash == current.content_hash:
            violations.append("prompt is identical to the current one")

        return violations
```

---

## 8. Technical Decisions

### 8.1 Concurrency

- **Asyncio native** throughout the pipeline
- **Semaphore per provider** for rate limiting
- **Ollama local**: sequential queue (1 request/time in GPU)
- **Cloud APIs**: aggressive parallelism respecting RPM declared by adapter

```python
class ProviderRateLimit(BaseModel):
    max_concurrent: int = 4
    requests_per_minute: int | None = None
    tokens_per_minute: int | None = None


class RateLimitedProvider:
    def __init__(self, provider: ModelProvider, limits: ProviderRateLimit):
        self._provider = provider
        self._sem = asyncio.Semaphore(limits.max_concurrent)
        self._rpm_limiter = TokenBucket(limits.requests_per_minute) if limits.requests_per_minute else None

    async def complete(self, *args, **kwargs):
        async with self._sem:
            if self._rpm_limiter:
                await self._rpm_limiter.acquire()
            return await self._provider.complete(*args, **kwargs)
```

### 8.2 Cache and Idempotence

Hash of `(prompt_hash, input, model_id, params_hash)` → cached `ExecutionResult`. Allows re-analysis
without re-inference.

```python
class ExecutionCache(Protocol):
    async def get(self, key: str) -> ExecutionResult | None: ...
    async def set(self, key: str, value: ExecutionResult, ttl: int | None = None) -> None: ...

def execution_cache_key(
    prompt: Prompt, input_text: str, model: ModelSpec
) -> str:
    payload = f"{prompt.content_hash}|{input_text}|{model.model_id}|{hash_params(model.params)}"
    return sha256(payload.encode()).hexdigest()
```

### 8.3 Determinism and Variance

SLMs in `temperature=0` still have variance (especially quantized). `n_runs_per_case` support:

```python
async def execute_case_with_runs(
    case: TestCase, prompt: Prompt, model: ModelSpec, n_runs: int
) -> AggregatedExecution:
    runs = await asyncio.gather(*[
        execute_single(case, prompt, model) for _ in range(n_runs)
    ])
    return AggregatedExecution(
        runs=runs,
        majority_output=majority_vote([r.actual_output for r in runs]),
        score_mean=mean([score(r) for r in runs]),
        score_std=std([score(r) for r in runs]),
    )
```

### 8.4 Budget Enforcement

Cost tracking in USD in real time, hard stop when exceeding:

```python
class BudgetTracker:
    def __init__(self, max_cost_usd: float):
        self._max = max_cost_usd
        self._current = 0.0

    def record(self, execution: ExecutionResult) -> None:
        self._current += execution.cost_usd
        if self._current >= self._max:
            raise BudgetExhausted(spent=self._current, limit=self._max)
```

### 8.5 Persistence

- **SQLite default** (zero-config, ideal for CLI/dev)
- **Optional Postgres** (for collaborative use/CI)
- **Parquet exports** for offline analysis (pandas, polars)

Simplified scheme:

```sql
CREATE TABLE prompts (
    hash TEXT PRIMARY KEY,
    template TEXT NOT NULL,
    metadata JSON,
    created_at TIMESTAMP
);

CREATE TABLE benchmarks (
    hash TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    payload JSON NOT NULL,
    created_at TIMESTAMP
);

CREATE TABLE optimization_runs (
    id TEXT PRIMARY KEY,
    config JSON NOT NULL,
    benchmark_hash TEXT NOT NULL,
    initial_prompt_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    stop_reason TEXT,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    FOREIGN KEY (benchmark_hash) REFERENCES benchmarks(hash),
    FOREIGN KEY (initial_prompt_hash) REFERENCES prompts(hash)
);

CREATE TABLE iterations (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    prompt_hash TEXT NOT NULL,
    score REAL NOT NULL,
    rationale TEXT,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES optimization_runs(id),
    FOREIGN KEY (prompt_hash) REFERENCES prompts(hash)
);

CREATE TABLE verdicts (
    id TEXT PRIMARY KEY,
    iteration_id TEXT NOT NULL,
    test_case_id TEXT NOT NULL,
    actual_output TEXT,
    score REAL,
    passed BOOLEAN,
    latency_ms REAL,
    tokens_in INTEGER,
    tokens_out INTEGER,
    cost_usd REAL,
    payload JSON,
    FOREIGN KEY (iteration_id) REFERENCES iterations(id)
);

CREATE INDEX idx_verdicts_iteration ON verdicts(iteration_id);
CREATE INDEX idx_iterations_run ON iterations(run_id);
```

### 8.6 Observability

OpenTelemetry native. Each `OptimizationRun` is a trace, each `Iteration` a span, each run a
sub-span.

```python
from opentelemetry import trace
tracer = trace.get_tracer(__name__)

async def run_optimization(config):
    with tracer.start_as_current_span("optimization.run") as root:
        root.set_attribute("target_model", config.target_model.model_id)
        root.set_attribute("threshold", config.threshold)

        for iter_n in range(config.max_iterations):
            with tracer.start_as_current_span(f"iteration.{iter_n}") as it_span:
                ...
```

---

## 9. UX and Interfaces

### 9.1 CLI

```bash
# Initialize project
crucible init meu-projeto

# Generated structure:
# meu-projeto/
#   benchmark.yaml
#   prompt.txt
#   config.yaml

# Otimizar
crucible optimize --config config.yaml

# Real-time output (Rich/Textual):
#
# Crucible v0.1.0 — Optimizing prompt for gemma3:4b
# Benchmark: extracao-cnpj-v1 (47 cases)
# Reasoning model: gpt-5
# Budget: $5.00 | Max iterations: 10 | Threshold: 95.0
#
# ┌─────────────────────────────────────────────────────────┐
# │ Iter │ Score   │ Δ      │ Cost   │ Time  │ Status      │
# ├──────┼─────────┼────────┼────────┼───────┼─────────────┤
# │  v0  │  67.5%  │   --   │ $0.04  │  23s  │ ❌ below     │
# │  v1  │  81.2%  │ +13.7  │ $0.18  │  45s  │ ❌ refining  │
# │  v2  │  88.9%  │  +7.7  │ $0.31  │  41s  │ ❌ refining  │
# │  v3  │  94.8%  │  +5.9  │ $0.47  │  38s  │ ❌ refining  │
# │  v4  │  97.3%  │  +2.5  │ $0.62  │  35s  │ ✓ PASSED    │
# └──────┴─────────┴────────┴────────┴───────┴─────────────┘
#
# ✓ Optimization complete
# Best prompt: prompt_v4.txt (97.3%)
# Total cost: $0.62 | Total time: 3m 42s
# Report: ./runs/2026-05-22T14-30/report.html

# Compare iterations
crucible diff v0 v4 --run latest

# Rerun without refinement (validation)
crucible validate --prompt prompt_v4.txt --benchmark benchmark.yaml --model gemma3:4b

# Dashboard local
crucible serve  # → http://localhost:7777

# Export report
crucible report --run <run_id> --format html|pdf|json
```

### 9.2 Python SDK

```python
from crucible import Optimizer, Benchmark, ModelSpec, OptimizationConfig
from crucible.assertions import ExactMatch, EmbeddingSimilarity, LLMJudge

# Load benchmark
benchmark = Benchmark.from_yaml("benchmark.yaml")
# or programmatically:
benchmark = Benchmark(
    name="meu-benchmark",
    version="1.0",
    cases=[
        TestCase(id="c1", input="...", expected_output="...",
                 assertion=ExactMatch()),
        ...
    ],
)

# Configure optimization
config = OptimizationConfig(
    target_model=ModelSpec.ollama("gemma3:4b"),
    reasoning_model=ModelSpec.openai("gpt-5"),
    threshold=95.0,
    max_iterations=10,
    max_cost_usd=5.00,
)

# Executa
optimizer = Optimizer(config)
result = await optimizer.run(
    prompt="Extract the CNPJ from this draft: {input}",
    benchmark=benchmark,
)

# Resultados
print(f"Best score: {result.best_score}")
print(f"Best prompt: {result.best_prompt.template}")
print(f"Iterations: {len(result.iterations)}")
print(f"Total cost: ${result.total_cost_usd:.2f}")

# Access history
for iter in result.iterations:
    print(f"v{iter.version}: {iter.score:.1f}% — {iter.refinement_rationale}")
```

### 9.3 Configuration Format (YAML)

```yaml
# config.yaml
name: extracao-cnpj
description: CNPJ extraction prompt optimization for Gemma 3 4B

target_model:
  provider: ollama
  model_id: gemma3:4b
  params:
    temperature: 0.0
    max_tokens: 512

reasoning_model:
  provider: openai
  model_id: gpt-5
  params:
    temperature: 0.2
    max_tokens: 4096

optimization:
  threshold: 95.0
  max_iterations: 10
  max_cost_usd: 5.00
  max_wallclock_seconds: 1800
  plateau_window: 3
  plateau_min_delta: 0.5
  parallelism: 4
  n_runs_per_case: 1

benchmark:
  path: benchmark.yaml

prompt:
  path: prompt.txt
```

### 9.4 Benchmark format (YAML)

```yaml
# benchmark.yaml
name: extracao-cnpj-v1
version: "1.0"
description: Test cases for CNPJ extraction from drafts

cases:
  - id: case-001
    input: |
      Extract the CNPJ from this draft:

      ABC SERVICES LTD, CNPJ 12.345.678/0001-90, headquartered in...
    expected_output: "12.345.678/0001-90"
    assertion:
      type: exact_match
      normalize: true
    weight: 1.0
    tags: [extraction, cnpj, formatted]

  - id: case-002
    input: |
      Summarize the purpose of this contract in up to 3 sentences:

      This agreement covers the provision of services...
    expected_output: |
      The contract establishes the provision of consulting services
      by ABC Ltd to XYZ SA for 12 months at a monthly rate
      of BRL 50,000.00.
    assertion:
      type: embedding_similarity
      threshold: 0.85
      model: text-embedding-3-small
    weight: 2.0
    tags: [summarization]
```

---

## 10. Project Structure

```
crucible/
├── pyproject.toml
├── README.md
├── LICENSE
├── CHANGELOG.md
│
├── src/crucible/
│   ├── __init__.py
│   │
│   ├── domain/                       # Domain layer (pure)
│   │   ├── __init__.py
│   │   ├── entities/
│   │   │   ├── prompt.py
│   │   │   ├── test_case.py
│   │   │   ├── benchmark.py
│   │   │   ├── iteration.py
│   │   │   └── optimization_run.py
│   │   ├── value_objects/
│   │   │   ├── score.py
│   │   │   ├── verdict.py
│   │   │   ├── budget.py
│   │   │   └── execution_result.py
│   │   ├── assertions/
│   │   │   ├── base.py
│   │   │   ├── deterministic.py     # ExactMatch, Regex, JsonEqual...
│   │   │   ├── structural.py        # FieldByField, PydanticModel
│   │   │   ├── semantic.py          # EmbeddingSimilarity
│   │   │   └── llm_judge.py
│   │   ├── services/
│   │   │   ├── scoring_service.py
│   │   │   ├── stopping_criteria.py
│   │   │   └── failure_selector.py
│   │   ├── events/
│   │   │   ├── iteration_completed.py
│   │   │   ├── threshold_reached.py
│   │   │   └── budget_exhausted.py
│   │   └── ports/
│   │       ├── model_provider.py
│   │       ├── repository.py
│   │       ├── execution_cache.py
│   │       └── embedder.py
│   │
│   ├── application/                  # Use cases
│   │   ├── __init__.py
│   │   ├── use_cases/
│   │   │   ├── optimize_prompt.py
│   │   │   ├── run_single_iteration.py
│   │   │   ├── score_execution.py
│   │   │   ├── diagnose_failures.py
│   │   │   ├── refine_prompt.py
│   │   │   └── compare_iterations.py
│   │   ├── orchestration/
│   │   │   └── optimization_orchestrator.py
│   │   └── meta_prompts/
│   │       ├── diagnose.py
│   │       └── refine.py
│   │
│   ├── infrastructure/               # Adapters
│   │   ├── __init__.py
│   │   ├── providers/
│   │   │   ├── ollama.py
│   │   │   ├── openai.py
│   │   │   ├── anthropic.py
│   │   │   ├── google.py
│   │   │   ├── openrouter.py
│   │   │   └── rate_limited.py
│   │   ├── persistence/
│   │   │   ├── sqlite/
│   │   │   │   ├── repository.py
│   │   │   │   ├── migrations/
│   │   │   │   └── models.py
│   │   │   └── postgres/
│   │   ├── cache/
│   │   │   ├── memory.py
│   │   │   └── disk.py
│   │   ├── embedders/
│   │   │   ├── openai.py
│   │   │   └── local_bge.py
│   │   └── telemetry/
│   │       ├── otel.py
│   │       └── langfuse.py
│   │
│   ├── interfaces/                   # Entry points
│   │   ├── cli/
│   │   │   ├── main.py              # Typer app
│   │   │   ├── commands/
│   │   │   │   ├── init.py
│   │   │   │   ├── optimize.py
│   │   │   │   ├── validate.py
│   │   │   │   ├── diff.py
│   │   │   │   ├── report.py
│   │   │   │   └── serve.py
│   │   │   └── display/
│   │   │       └── rich_renderer.py
│   │   ├── sdk/
│   │   │   ├── optimizer.py         # public facade
│   │   │   └── builders.py
│   │   └── web/
│   │       ├── api/                 # FastAPI
│   │       ├── static/
│   │       └── templates/
│   │
│   └── config/
│       ├── loader.py
│       └── defaults.py
│
├── tests/
│   ├── unit/
│   │   ├── domain/
│   │   ├── application/
│   │   └── infrastructure/
│   ├── integration/
│   └── e2e/
│
├── examples/
│   ├── 01-basic-optimization/
│   ├── 02-multi-model-comparison/
│   ├── 03-llm-judge-assertions/
│   └── 04-custom-assertion/
│
└── docs/
    ├── getting-started.md
    ├── concepts.md
    ├── assertions.md
    ├── providers.md
    └── architecture.md
```

---

## 11. Roadmap MVP

### Phase 1 — Core Executor (1-2 weeks)

**Objective:** run benchmark against prompt+model and generate score without loop.

- [ ] Domain models (Prompt, TestCase, Benchmark, Verdict)
- [ ] Assertions Tier 1 (ExactMatch, Regex, JsonEqual, NumericMatch)
- [ ] assertion Tier 2 (PydanticModel, FieldByField)
- [ ] OllamaAdapter (first provider)
- [ ] Basic ScoringService
- [ ] Minimum CLI: `crucible validate --prompt --benchmark --model`
- [ ] SQLite Persistence (verdict history)

**Output:** functional tool to "run a benchmark and see its score". It already has isolated value.

### Phase 2 — Optimization Loop (1-2 weeks)

**Objective:** complete loop end-to-end.

- [ ] OpenAIAdapter / AnthropicAdapter (reasoning models)
- [ ] Diagnosis FailuresUseCase + meta-prompt
- [ ] RefinePromptUseCase + meta-prompt
- [ ] Optimization Orchestrator (the loop)
- [ ] Stopping criteria (threshold, max_iter, budget, plateau)
- [ ] BudgetTracker
- [ ] FailureSelector (priorisation)
- [ ] IterationMemory + History in Refiner
- [ ] CLI: `crucible optimize --config config.yaml`
- [ ] Rich-based progress display

**Output:** usable end-to-end product. It is already sellable for early adopters.

### Phase 3 — Multi-Provider + Advanced Assertions (2 weeks)

**Objective:** robustness and coverage.

- [ ] GoogleAdapter (Gemini)
- [ ] OpenRouterAdapter (access to multiple models)
- [ ] llama.cpp / vLLM adapter
- [ ] Assertion Tier 3 (EmbeddingSimilarity with local BGE + OpenAI)
- [ ] assertion Tier 4 (LLMJudge with bias mitigation)
- [ ] Execution Cache (disk-based)
- [ ] Rate limiting by provider
- [ ] Asyncio parallelism with semaphores
- [ ] n_runs_per_case + statistical aggregation
- [ ] Benchmark Train/val/test split

**Output:** competitive product. Here is already above Promptfoo in optimization.

### Phase 4 — Dashboard + Analytics (2-3 weeks)

**Objective:** professional analysis experience.

- [ ] Web dashboard (FastAPI + HTMX or Next.js)
- [ ] Runs preview (timeline, score history)
- [ ] Visual diff between iterations
- [ ] Multi-run comparison (model A vs B on the same benchmark)
- [ ] Plot cost × quality × latency
- [ ] Export HTML/PDF report
- [ ] OpenTelemetry integration
- [ ] Langfuse integration (optional)

**Output:** polished product, ready for team use/sales.

### Phase 5+ — Post-MVP

- Plugin system for custom assertions
- Importers (Promptfoo, LangSmith, DSPy)
- Multi-objective optimization
- Active learning for benchmark expansion
- Distributed execution (Ray/Dask)
- VSCode extension
- REST + multi-tenant API

---

## 12. Risks and Mitigations

### 12.1 Overfitting to Benchmark

**Risk:** reasoning model optimizes prompt to pass specific tests, losing generalization.

**Mitigations:**
- Mandatory train/validation/test split (default 70/15/15)
- Optimization uses only train; reports parallel score in val
- The test set is only run in the final validation
- Explicit Warning when gap train↔val exceeds threshold (e.g. 5pp)
- Benchmark Diversity as a Health Metric

### 12.2 Uncontrolled Cost

**Risk:** reasoning model loop silently runs up the bill.

**Mitigations:**
- `max_cost_usd` is mandatory parameter (no default unlimited)
- Hard stop with clear exception when exceeding
- Previous estimate: `crucible estimate-cost --config X` shows expected cost before running
- Real-time display of the accumulated cost
- Aggressive execution cache

### 12.3 Prompt Drift (worst versions)

**Risk:** refiner generates v5 worse than v3.

**Mitigations:**
- Best-ever tracking (high-water mark)
- Always return `best_iteration`, not `last_iteration`
- Plateau detection interrupts unproductive loop
- History of changes in the context of the refiner to avoid paths already tested

### 12.4 LLM-as-Judge biases

**Risk:** judge favors verbose, formal, or similar outputs to the style of the judge model itself.

**Mitigations:**
- Position swap (run expected/actual on both orders)
- Multiple judges (consensus between N models)
- Calibration set (cases with ground truth known to audit the judge)
- Explicit, structured rubrics instead of unrestricted scoring
- Prefer deterministic tiers when possible

### 12.5 Non-determinism of SLMs

**Risk:** same prompt, same input, scores vary between runs.

**Mitigations:**
- `n_runs_per_case` configurable (default 1, recommended 3-5 for SLMs)
- Aggregation by majority vote + std reported
- Warning when std exceeds threshold ("unstable scoring")
- Seed when supported by provider

### 12.6 Lock-in of Provider

**Risk:** strong dependence on a provider breaks portability.

**Mitigations:**
- Domain layer 100% provider-agnostic
- ModelProvider as Protocol/Port
- Adapter contract tests
- Always support at least 1 local alternative (Ollama) + 1 cloud

---

## 13. Competitive Positioning

### 13.1 Competitor Map

| Product | Focus | Gap that Crucible fills |
| --------- | ------ | ------------------------------ |
| **Promptfoo** | Regression testing, YAML-driven | Do not optimize prompts; focus on LLMs cloud |
| **DeepEval** | Pytest-like eval, metrics | No optimization loop; no SLM focus |
| **DSPy** | Programmatic compilation of prompts | Academic API; no pragmatic UX; no SLM-first |
| **Braintrust / Langfuse** | Observability + eval | Not optimize; focus on production, not iteration |
| **OpenAI Evals** | Benchmark framework | Lock-in OpenAI; no automatic refinement |
| **Inspect AI** | Safety evals (AISI) | Focus on capability/safety, not on prompt opt |
| **PromptAgent / OPRO** | Optimization Papers | No saleable product; no multi-provider |

### 13.2 Positioning Thesis

> **"The prompt compiler for those who take SLMs seriously."**

Derivative subpositions:
- For ML teams that run edge/on-prem: "optimize Gemma 3 4B without guesswork"
- For full-stack devs: "Promptfoo + DSPy in a pragmatic product"
- For AI engineers in startups: "validate cost vs quality before migrating from GPT-4 to
  gpt-4o-mini"

### 13.3 Use Cases-Anchor

Real use cases validating the product:

1. **Migration cloud → edge**: company wants to exchange GPT-4 for local Gemma3; Crucible optimizes
   prompt and shows trade-off
2. **Multi-model selection**: given a benchmark, which model gives best cost/quality
3. **Regression in production**: a production prompt needs to change; validate that nothing broke
4. **Domain prompt engineering**: legal/medical/financial team without expertise iterates on prompts
   empirically

---

## Appendix A — Glossary

- **SLM** (Small Language Model): model ≤ ~10B parameters, usually runnable on modest hardware
- **LLM-as-Judge**: use an LLM to evaluate the output of another LLM
- **Few-shot**: prompt that includes demonstrative examples
- **High-water mark**: best value ever observed in a series
- **Plateau detection**: identify which metric has stopped improving
- **Bounded Context** (DDD): semantic boundary within which a model is consistent
- **Port/Adapter**: hexagonal pattern — Port is domain interface, the adapter implements it outside
  the domain

## Appendix B — References

- DSPy (Khattab et al.) — programmatic prompt optimization
- OPRO (Yang et al., DeepMind) — "Large Language Models as Optimizers"
- PromptAgent (Wang et al.) — strategic planning for prompt opt
- Promptfoo — UX reference for eval
- Anthropic Cookbook — prompt engineering best practices
- "The Prompt Report" (Schulhoff et al., 2024) — technical taxonomy

---

**Next suggested steps after this document:**

1. Decide definitive naming (Crucible, Anvil, Refinery, etc.)
2. Validate thesis with 2–3 real use cases (ideally from your portfolio: Sponsio, Huginn)
3. Technical Spike: implement Phase 1 in ~3 days to validate feasibility
4. Distribution model decision: pure open source / open-core / proprietary
