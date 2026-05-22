# Crucible — Prompt Optimization Framework

> Framework agnóstico de domínio para otimização iterativa de prompts em LLMs/SLMs, dirigida por reasoning models e validada empiricamente contra gabaritos versionados.

**Versão:** 1.0 — Documento de Arquitetura
**Autor:** Darci
**Status:** Especificação inicial / MVP design

---

## Sumário

1. [Visão e Posicionamento](#1-visão-e-posicionamento)
2. [Conceitos Centrais](#2-conceitos-centrais)
3. [O Loop de Otimização](#3-o-loop-de-otimização)
4. [Sistema de Scoring](#4-sistema-de-scoring)
5. [Arquitetura (Clean Architecture + DDD)](#5-arquitetura-clean-architecture--ddd)
6. [Modelos de Domínio (Pydantic v2)](#6-modelos-de-domínio-pydantic-v2)
7. [Refinement Engine](#7-refinement-engine)
8. [Decisões Técnicas](#8-decisões-técnicas)
9. [UX e Interfaces](#9-ux-e-interfaces)
10. [Estrutura de Projeto](#10-estrutura-de-projeto)
11. [Roadmap MVP](#11-roadmap-mvp)
12. [Riscos e Mitigações](#12-riscos-e-mitigações)
13. [Posicionamento Competitivo](#13-posicionamento-competitivo)

---

## 1. Visão e Posicionamento

### 1.1 Tese

Crucible é um **compilador iterativo de prompts**. Dado um prompt rascunho, um gabarito de entrada/saída esperada, um modelo-alvo (LLM menor ou SLM) e um modelo de raciocínio, o framework executa um loop de execução → avaliação → diagnóstico → refinamento até atingir um threshold de qualidade ou exaurir budget.

### 1.2 Job-to-be-done primário

**Prompt optimization dirigida por reasoning model contra gabarito empírico, agnóstica de domínio e provider.**

### 1.3 Diferenciação

- **Multi-provider real**: Ollama, llama.cpp, vLLM como cidadãos de primeira classe (não afterthought)
- **Separação arquitetural entre Target Model e Reasoning Model**: dois papéis distintos, configuráveis independentemente
- **Loop com memória entre iterações**: o refiner vê histórico completo de tentativas, não single-shot
- **Score operacional + qualitativo no mesmo plano**: qualidade × custo × latência como trade-off explícito
- **Gabarito como entidade versionada de primeira classe**: separação prompt/gabarito permite regressão trivial

### 1.4 O que NÃO é

- Não é observability/tracing platform (Langfuse, Phoenix)
- Não é prompt management UI (Promptlayer, Humanloop)
- Não é fine-tuning framework
- Não é agentic orchestration (Langgraph, AgentForge)
- Não é serving infrastructure

---

## 2. Conceitos Centrais

| Conceito | Definição |
|----------|-----------|
| **Prompt** | Template versionado com placeholders e metadata. Identificado por hash de conteúdo. |
| **Gabarito** | Coleção versionada de TestCases (input → expected_output + assertion). |
| **TestCase** | Tripla (input, expected_output, assertion) + peso opcional + tags. |
| **TargetModel** | Modelo a ser otimizado (LLM menor ou SLM). Roda muitas vezes. |
| **ReasoningModel** | Modelo crítico/refator. Roda poucas vezes mas é caro. |
| **OptimizationRun** | Aggregate root. Encapsula todo o loop de uma otimização. |
| **Iteration** | Uma volta do loop: (prompt_version, execução, score, refinamento). |
| **Assertion** | Regra de validação aplicada a um par (expected, actual). |
| **Verdict** | Resultado de uma execução individual: pass/fail + score + métricas operacionais. |
| **Budget** | Limites combinados: max_iterations, max_cost_usd, max_wallclock_seconds. |

---

## 3. O Loop de Otimização

### 3.1 Fluxo Conceitual

```
┌─────────────────────────────────────────────────────────────┐
│  INPUT                                                      │
│  - prompt_v0 (template inicial)                             │
│  - gabarito (lista de TestCases)                            │
│  - target_model (ex: gemma3:4b via Ollama)                  │
│  - reasoning_model (ex: gpt-5 ou gemini-2.5-pro)            │
│  - config (threshold, budget, stopping criteria)            │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  EXECUTION             │
              │  Para cada TestCase:   │
              │  - render(prompt, input)│
              │  - call(target_model)  │
              │  - capturar output,    │
              │    latência, tokens    │
              │  (paralelo respeitando │
              │   rate limits)         │
              └───────────┬────────────┘
                          │
                          ▼
              ┌────────────────────────┐
              │  SCORING               │
              │  Para cada execução:   │
              │  - aplicar assertion   │
              │  - calcular score      │
              │  Agregar:              │
              │  - score global        │
              │  - breakdown por tag   │
              │  - custo total         │
              └───────────┬────────────┘
                          │
                          ▼
                  ┌───────┴───────┐
                  │ Stop?         │
                  │ - score≥thresh│
                  │ - plateau     │
                  │ - budget out  │
                  └─┬───────────┬─┘
                Sim │           │ Não
                    ▼           ▼
              ┌────────┐  ┌──────────────────┐
              │ RETURN │  │  DIAGNOSIS       │
              │ best   │  │  Reasoning model │
              │ prompt │  │  analisa erros:  │
              └────────┘  │  - padrão        │
                          │  - hipótese      │
                          │  - root cause    │
                          └─────────┬────────┘
                                    │
                                    ▼
                          ┌──────────────────┐
                          │  REFINEMENT      │
                          │  Reasoning model │
                          │  propõe:         │
                          │  - prompt_v(N+1) │
                          │  - rationale     │
                          │  - mudanças diff │
                          └─────────┬────────┘
                                    │
                                    └──→ volta para EXECUTION
```

### 3.2 Critérios de Parada (combinados)

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

### 3.3 Seleção de Casos Divergentes

Mandar todos os erros ao reasoning model é desperdício. Estratégia híbrida:

```python
def select_failures_for_refinement(
    verdicts: list[Verdict],
    max_cases: int = 10,
    max_tokens: int = 8000,
) -> list[Verdict]:
    failures = [v for v in verdicts if not v.passed]
    
    # 1. Regressões (passavam antes, falham agora) — prioridade máxima
    regressions = [v for v in failures if v.is_regression]
    
    # 2. Top-K piores por score
    worst = sorted(failures, key=lambda v: v.score)[:max_cases]
    
    # 3. Stratified sampling por tag/categoria
    stratified = stratified_sample(failures, by="tags", k=max_cases)
    
    # 4. Merge respeitando token budget
    selected = merge_dedupe([*regressions, *worst, *stratified])
    return truncate_by_tokens(selected, max_tokens)
```

### 3.4 Memória Entre Iterações

O refiner recebe **histórico completo de tentativas** para evitar repetir sugestões falhas:

```python
class IterationMemory(BaseModel):
    version: int
    prompt_hash: str
    score_before: float
    score_after: float
    delta: float
    proposed_change: str  # rationale do refiner
    diff_summary: str     # diff resumido do prompt
    failure_pattern: str  # padrão de falha identificado
```

### 3.5 Best-Ever Tracking

Sempre retornar o **melhor prompt já visto**, não o último:

```python
class OptimizationRun:
    best_iteration: Iteration  # high-water mark
    last_iteration: Iteration  # última executada
    
    def update_best(self, candidate: Iteration) -> None:
        if candidate.score > self.best_iteration.score:
            self.best_iteration = candidate
```

---

## 4. Sistema de Scoring

### 4.1 Hierarquia de Assertions (custo crescente)

#### Tier 1 — Determinísticas

| Assertion | Descrição | Uso típico |
|-----------|-----------|------------|
| `ExactMatch` | Igualdade literal (com opções de normalize) | IDs, valores formatados |
| `NumericMatch` | Igualdade numérica com tolerância | Valores monetários, cálculos |
| `Regex` | Pattern matching | Validação de formato |
| `JsonEqual` | Deep equal de JSON | Outputs estruturados |
| `JsonSchema` | Validação por schema Pydantic | Conformidade estrutural |
| `Contains` | Substring/keyword presence | Verificações pontuais |

#### Tier 2 — Estruturais

| Assertion | Descrição |
|-----------|-----------|
| `FieldByField` | Compara campos de JSON com pesos individuais |
| `PydanticModel` | Valida + compara via modelo Pydantic com tolerância por campo |

#### Tier 3 — Semânticas

| Assertion | Descrição | Modelo |
|-----------|-----------|--------|
| `EmbeddingSimilarity` | Cosine similarity sobre embeddings | text-embedding-3, BGE, etc. |
| `BertScore` | F1 sobre tokens contextualizados | Modelo BERT |

#### Tier 4 — LLM-as-Judge

| Assertion | Descrição |
|-----------|-----------|
| `LLMJudge` | Reasoning model avalia expected vs actual com rubrica explícita |
| `LLMJudgeWithRationale` | Idem + retorna justificativa estruturada |

### 4.2 Declaração no Gabarito

Assertions são **por TestCase**, não globais:

```python
gabarito = Gabarito(
    name="extracao-cnpj-v1",
    cases=[
        TestCase(
            id="case-001",
            input="Extraia o CNPJ desta minuta: ABC SA, CNPJ 12.345.678/0001-90...",
            expected_output="12.345.678/0001-90",
            assertion=ExactMatch(normalize=True),
            weight=1.0,
            tags=["extraction", "cnpj"],
        ),
        TestCase(
            id="case-002",
            input="Resuma este contrato em 3 frases: ...",
            expected_output="O contrato estabelece os termos de prestação...",
            assertion=EmbeddingSimilarity(threshold=0.85),
            weight=2.0,
            tags=["summarization"],
        ),
        TestCase(
            id="case-003",
            input="Avalie o risco desta operação: ...",
            expected_output="Alto risco devido a...",
            assertion=LLMJudge(
                rubric="Avalie se a resposta identifica corretamente o nível de risco e justifica.",
                pass_threshold=0.7,
            ),
            weight=3.0,
            tags=["reasoning", "risk-assessment"],
        ),
    ],
)
```

### 4.3 Agregação

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

## 5. Arquitetura (Clean Architecture + DDD)

### 5.1 Bounded Contexts

```
┌─────────────────────────────────────────────────────────────┐
│  AUTHORING CONTEXT                                          │
│  Responsabilidade: definir prompts, gabaritos, configs      │
│  Agregados: Prompt, Gabarito, OptimizationConfig            │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  OPTIMIZATION CONTEXT                                       │
│  Responsabilidade: executar o loop, refinar prompts         │
│  Agregados: OptimizationRun, Iteration                      │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│  ANALYSIS CONTEXT                                           │
│  Responsabilidade: comparar runs, gerar relatórios          │
│  Agregados: ComparisonReport, EvolutionReport               │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 Camadas (Clean Architecture)

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
│  Entities: Prompt, TestCase, Gabarito, OptimizationRun   │
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
│  Telemetry: OTelExporter, LangfuseExporter (opcional)    │
└──────────────────────────────────────────────────────────┘
```

### 5.3 Dependency Rule

Domínio não importa Application, Application não importa Infrastructure. Adapters implementam ports (Protocols) definidos no Domínio/Application.

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
        # implementação concreta
        ...
```

---

## 6. Modelos de Domínio (Pydantic v2)

### 6.1 Núcleo

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
    """Base para todas as assertions. Polimorfismo via type discriminator."""
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


class Gabarito(BaseModel):
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
        "Gabarito", "Gabarito", "Gabarito"
    ]:
        """Split estratificado em train/val/test."""
        ...
```

### 6.2 Modelos e Execução

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
    is_regression: bool = False  # passou na iter anterior, falhou agora
```

### 6.3 Otimização

```python
class OptimizationConfig(BaseModel):
    threshold: float = 95.0
    max_iterations: int = 10
    max_cost_usd: float = 5.00
    max_wallclock_seconds: int = 1800
    plateau_window: int = 3
    plateau_min_delta: float = 0.5
    parallelism: int = 4
    n_runs_per_case: int = 1  # para SLMs não-determinísticos
    
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
    gabarito_hash: str
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

### 7.1 Separação Diagnose + Refactor

Dois calls separados ao reasoning model para melhor qualidade:

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

### 7.2 Meta-prompt do Diagnose

```
Você é um especialista em prompt engineering avaliando falhas de um modelo {target_model_provider}/{target_model_id}.

CONTEXTO DO MODELO-ALVO:
- Provider: {provider}
- Model ID: {model_id}
- Context window: {context_window}
- Capacidades conhecidas: {capabilities}
- Limitações conhecidas: {known_limitations}

PROMPT ATUAL (v{version}):
---
{current_prompt}
---

HISTÓRICO DE TENTATIVAS:
{history_summary}

CASOS QUE FALHARAM NESTA ITERAÇÃO ({n_failures} casos):

{for each failure:}
─── Caso {id} (tags: {tags}, score: {score}) ───
INPUT:
{input}

OUTPUT ESPERADO:
{expected}

OUTPUT OBTIDO:
{actual}

TIPO DE ASSERTION: {assertion_type}
DETALHE DA FALHA: {assertion_detail}

SUA TAREFA:
1. Identifique o PADRÃO DE FALHA dominante (não liste cada falha individualmente)
2. Formule uma HIPÓTESE causal sobre o porquê o modelo falha
3. Categorize a falha:
   - INSTRUCTION_AMBIGUITY (prompt ambíguo)
   - MISSING_CONSTRAINT (falta constraint explícito)
   - WRONG_FORMAT (formato de saída mal especificado)
   - MISSING_EXAMPLES (falta few-shot)
   - WRONG_EXAMPLES (few-shots inadequados)
   - MODEL_CAPABILITY (limitação do modelo, não do prompt)
   - INPUT_COMPLEXITY (input excede capacidade)
   - OUTPUT_LENGTH (limite de tokens)

Retorne JSON estritamente neste schema:
{
  "pattern": "descrição do padrão",
  "hypothesis": "hipótese causal",
  "category": "INSTRUCTION_AMBIGUITY|MISSING_CONSTRAINT|...",
  "confidence": 0.0-1.0,
  "is_model_limitation": boolean
}
```

### 7.3 Meta-prompt do Refactor

```
Você é um especialista em prompt engineering refatorando um prompt para o modelo {target_model_id}.

PROMPT ATUAL:
---
{current_prompt}
---

DIAGNÓSTICO:
- Padrão de falha: {pattern}
- Hipótese: {hypothesis}
- Categoria: {category}

HISTÓRICO DE MUDANÇAS (NÃO REPITA):
{for each past iteration:}
- v{n}: {proposed_change} → score {before}→{after} ({delta:+.1f})

CONSTRAINTS:
- Mantenha as variáveis: {variables}
- Não exceda {max_tokens_prompt} tokens no prompt
- O modelo-alvo NÃO suporta: {unsupported_features}

SUA TAREFA:
Proponha um NOVO prompt (v{next_version}) que aborde o padrão de falha identificado.

PRINCÍPIOS:
- Mudança mínima necessária (não reescreva tudo)
- Justifique cada alteração
- Se já tentou abordagem similar e falhou, tente direção diferente
- Para SLMs: prefira instruções mais explícitas e few-shots concretos

Retorne JSON:
{
  "new_prompt": "...",
  "diff_summary": "lista de mudanças concretas",
  "rationale": "por que essa mudança aborda o diagnóstico",
  "expected_improvement": "predição qualitativa do impacto",
  "confidence": 0.0-1.0
}
```

### 7.4 Validação do Output do Refiner

```python
class RefinementProposal(BaseModel):
    new_prompt: str
    diff_summary: str
    rationale: str
    expected_improvement: str
    confidence: float = Field(ge=0.0, le=1.0)
    
    def validate_against(self, current: Prompt) -> list[str]:
        """Retorna lista de violações. Vazio = OK."""
        violations = []
        new = Prompt(template=self.new_prompt)
        
        # Variáveis preservadas?
        if set(current.variables) != set(new.variables):
            violations.append("variáveis alteradas")
        
        # Hash diferente? (não é idêntico ao atual)
        if new.content_hash == current.content_hash:
            violations.append("prompt idêntico ao atual")
        
        return violations
```

---

## 8. Decisões Técnicas

### 8.1 Concorrência

- **Asyncio nativo** em todo o pipeline
- **Semáforo por provider** para rate limiting
- **Ollama local**: fila sequencial (1 request/vez na GPU)
- **Cloud APIs**: paralelismo agressivo respeitando RPM declarado por adapter

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

### 8.2 Cache e Idempotência

Hash de `(prompt_hash, input, model_id, params_hash)` → cached `ExecutionResult`. Permite re-análise sem re-inferência.

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

### 8.3 Determinismo e Variância

SLMs em `temperature=0` ainda têm variância (especialmente quantizados). Suporte a `n_runs_per_case`:

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

Tracking de custo em USD em tempo real, hard stop quando exceder:

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

### 8.5 Persistência

- **SQLite default** (zero-config, ideal para CLI/dev)
- **Postgres opcional** (para uso colaborativo/CI)
- **Parquet exports** para análise offline (pandas, polars)

Schema simplificado:

```sql
CREATE TABLE prompts (
    hash TEXT PRIMARY KEY,
    template TEXT NOT NULL,
    metadata JSON,
    created_at TIMESTAMP
);

CREATE TABLE gabaritos (
    hash TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    payload JSON NOT NULL,
    created_at TIMESTAMP
);

CREATE TABLE optimization_runs (
    id TEXT PRIMARY KEY,
    config JSON NOT NULL,
    gabarito_hash TEXT NOT NULL,
    initial_prompt_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    stop_reason TEXT,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    FOREIGN KEY (gabarito_hash) REFERENCES gabaritos(hash),
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

OpenTelemetry nativo. Cada `OptimizationRun` é um trace, cada `Iteration` um span, cada execução um sub-span.

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

## 9. UX e Interfaces

### 9.1 CLI

```bash
# Inicializar projeto
crucible init meu-projeto

# Estrutura gerada:
# meu-projeto/
#   gabarito.yaml
#   prompt.txt
#   config.yaml

# Otimizar
crucible optimize --config config.yaml

# Output em tempo real (Rich/Textual):
# 
# Crucible v0.1.0 — Optimizing prompt for gemma3:4b
# Gabarito: extracao-cnpj-v1 (47 cases)
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

# Comparar iterações
crucible diff v0 v4 --run latest

# Re-rodar sem refinamento (validação)
crucible validate --prompt prompt_v4.txt --gabarito gabarito.yaml --model gemma3:4b

# Dashboard local
crucible serve  # → http://localhost:7777

# Exportar relatório
crucible report --run <run_id> --format html|pdf|json
```

### 9.2 Python SDK

```python
from crucible import Optimizer, Gabarito, ModelSpec, OptimizationConfig
from crucible.assertions import ExactMatch, EmbeddingSimilarity, LLMJudge

# Carrega gabarito
gabarito = Gabarito.from_yaml("gabarito.yaml")
# ou programaticamente:
gabarito = Gabarito(
    name="meu-gabarito",
    version="1.0",
    cases=[
        TestCase(id="c1", input="...", expected_output="...", 
                 assertion=ExactMatch()),
        ...
    ],
)

# Configura otimização
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
    prompt="Extraia o CNPJ desta minuta: {input}",
    gabarito=gabarito,
)

# Resultados
print(f"Best score: {result.best_score}")
print(f"Best prompt: {result.best_prompt.template}")
print(f"Iterations: {len(result.iterations)}")
print(f"Total cost: ${result.total_cost_usd:.2f}")

# Acesso ao histórico
for iter in result.iterations:
    print(f"v{iter.version}: {iter.score:.1f}% — {iter.refinement_rationale}")
```

### 9.3 Formato de Configuração (YAML)

```yaml
# config.yaml
name: extracao-cnpj
description: Otimização do prompt de extração de CNPJ para Gemma 3 4B

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

gabarito:
  path: gabarito.yaml

prompt:
  path: prompt.txt
```

### 9.4 Formato de Gabarito (YAML)

```yaml
# gabarito.yaml
name: extracao-cnpj-v1
version: "1.0"
description: Casos de teste para extração de CNPJ de minutas

cases:
  - id: case-001
    input: |
      Extraia o CNPJ desta minuta:
      
      ABC SERVIÇOS LTDA, CNPJ 12.345.678/0001-90, com sede em...
    expected_output: "12.345.678/0001-90"
    assertion:
      type: exact_match
      normalize: true
    weight: 1.0
    tags: [extraction, cnpj, formatted]
  
  - id: case-002
    input: |
      Resuma o objeto deste contrato em até 3 frases:
      
      O presente instrumento tem por objeto a prestação de serviços...
    expected_output: |
      O contrato estabelece a prestação de serviços de consultoria
      pela ABC Ltda à XYZ SA, com vigência de 12 meses e valor mensal
      de R$ 50.000,00.
    assertion:
      type: embedding_similarity
      threshold: 0.85
      model: text-embedding-3-small
    weight: 2.0
    tags: [summarization]
```

---

## 10. Estrutura de Projeto

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
│   ├── domain/                       # Camada de domínio (pura)
│   │   ├── __init__.py
│   │   ├── entities/
│   │   │   ├── prompt.py
│   │   │   ├── test_case.py
│   │   │   ├── gabarito.py
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
│   │   │   ├── optimizer.py         # facade pública
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

### Fase 1 — Core Executor (1-2 semanas)

**Objetivo:** rodar gabarito contra prompt+modelo e gerar score, sem loop.

- [ ] Domain models (Prompt, TestCase, Gabarito, Verdict)
- [ ] Assertions Tier 1 (ExactMatch, Regex, JsonEqual, NumericMatch)
- [ ] Assertion Tier 2 (PydanticModel, FieldByField)
- [ ] OllamaAdapter (primeiro provider)
- [ ] ScoringService básico
- [ ] CLI mínimo: `crucible validate --prompt --gabarito --model`
- [ ] Persistência SQLite (verdict history)

**Saída:** ferramenta funcional para "rodar gabarito e ver score". Já tem valor isolado.

### Fase 2 — Optimization Loop (1-2 semanas)

**Objetivo:** loop completo end-to-end.

- [ ] OpenAIAdapter / AnthropicAdapter (reasoning models)
- [ ] DiagnoseFailuresUseCase + meta-prompt
- [ ] RefinePromptUseCase + meta-prompt
- [ ] OptimizationOrchestrator (o loop)
- [ ] Stopping criteria (threshold, max_iter, budget, plateau)
- [ ] BudgetTracker
- [ ] FailureSelector (priorização)
- [ ] IterationMemory + histórico no refiner
- [ ] CLI: `crucible optimize --config config.yaml`
- [ ] Rich-based progress display

**Saída:** produto utilizável end-to-end. Já é vendável para early adopters.

### Fase 3 — Multi-Provider + Assertions Avançadas (2 semanas)

**Objetivo:** robustez e cobertura.

- [ ] GoogleAdapter (Gemini)
- [ ] OpenRouterAdapter (acesso a múltiplos modelos)
- [ ] llama.cpp / vLLM adapter
- [ ] Assertion Tier 3 (EmbeddingSimilarity com BGE local + OpenAI)
- [ ] Assertion Tier 4 (LLMJudge com mitigação de viés)
- [ ] ExecutionCache (disk-based)
- [ ] Rate limiting por provider
- [ ] Paralelismo asyncio com semáforos
- [ ] n_runs_per_case + agregação estatística
- [ ] Train/val/test split do gabarito

**Saída:** produto competitivo. Aqui já está acima do Promptfoo em otimização.

### Fase 4 — Dashboard + Analytics (2-3 semanas)

**Objetivo:** experiência de análise profissional.

- [ ] Web dashboard (FastAPI + HTMX ou Next.js)
- [ ] Visualização de runs (timeline, score history)
- [ ] Diff visual entre iterações
- [ ] Comparação multi-run (modelo A vs B no mesmo gabarito)
- [ ] Plot custo × qualidade × latência
- [ ] Export HTML/PDF report
- [ ] OpenTelemetry integration
- [ ] Langfuse integration (opcional)

**Saída:** produto polido, pronto para uso em equipe / vendável.

### Fase 5+ — Pós-MVP

- Plugin system para custom assertions
- Importadores (Promptfoo, LangSmith, DSPy)
- Multi-objective optimization (Pareto frontier qualidade × custo)
- Active learning para expansão de gabarito
- Distributed execution (Ray/Dask)
- VSCode extension
- API REST + multi-tenant

---

## 12. Riscos e Mitigações

### 12.1 Overfitting ao Gabarito

**Risco:** reasoning model otimiza prompt para passar nos testes específicos, perdendo generalização.

**Mitigações:**
- Split obrigatório train/validation/test (default 70/15/15)
- Otimização usa apenas train; reporta score paralelo no val
- Test set só é tocado na validação final
- Warning explícito quando gap train↔val excede threshold (ex: 5pp)
- Diversidade do gabarito como métrica de saúde

### 12.2 Custo Descontrolado

**Risco:** loop de reasoning model queima fatura silenciosamente.

**Mitigações:**
- `max_cost_usd` é parâmetro obrigatório (não tem default unlimited)
- Hard stop com exception clara ao exceder
- Estimativa prévia: `crucible estimate-cost --config X` mostra custo esperado antes de rodar
- Display em tempo real do custo acumulado
- Cache de execução agressivo

### 12.3 Prompt Drift (versões piores)

**Risco:** refiner gera v5 pior que v3.

**Mitigações:**
- Best-ever tracking (high-water mark)
- Sempre retornar `best_iteration`, não `last_iteration`
- Detecção de plateau interrompe loop improdutivo
- Histórico de mudanças no contexto do refiner para evitar caminhos já testados

### 12.4 Viés do LLM-as-Judge

**Risco:** judge favorece outputs verbosos, formais, ou similares ao próprio estilo do modelo judge.

**Mitigações:**
- Position swap (rodar expected/actual em ambas as ordens)
- Multiple judges (consenso entre N modelos)
- Calibration set (casos com ground truth conhecido para auditar o judge)
- Rubricas explícitas e estruturadas, não scoring livre
- Preferir tiers determinísticos quando possível

### 12.5 Não-determinismo de SLMs

**Risco:** mesmo prompt, mesmo input, scores variam entre runs.

**Mitigações:**
- `n_runs_per_case` configurável (default 1, recomendado 3-5 para SLMs)
- Agregação por majority vote + std reportado
- Warning quando std excede threshold ("scoring instável")
- Seed quando suportado pelo provider

### 12.6 Lock-in de Provider

**Risco:** dependência forte de um provider quebra portabilidade.

**Mitigações:**
- Domain layer 100% agnóstico de provider
- ModelProvider como Protocol/Port
- Testes de contrato por adapter
- Sempre suportar ao menos 1 alternativa local (Ollama) + 1 cloud

---

## 13. Posicionamento Competitivo

### 13.1 Mapa de Concorrentes

| Produto | Foco | Lacuna que Crucible preenche |
|---------|------|------------------------------|
| **Promptfoo** | Regression testing, YAML-driven | Não otimiza prompts; foco em LLMs cloud |
| **DeepEval** | Pytest-like eval, métricas | Sem loop de otimização; sem foco em SLM |
| **DSPy** | Compilação programática de prompts | API acadêmica; sem UX pragmática; sem SLM-first |
| **Braintrust / Langfuse** | Observability + eval | Não otimiza; foco em produção, não em iteração |
| **OpenAI Evals** | Benchmark framework | Lock-in OpenAI; sem refinamento automático |
| **Inspect AI** | Safety evals (AISI) | Foco em capability/safety, não em prompt opt |
| **PromptAgent / OPRO** | Papers de otimização | Sem produto vendável; sem multi-provider |

### 13.2 Tese de Posicionamento

> **"O compilador de prompts para quem leva SLMs a sério."**

Subposicionamentos derivados:
- Para times de ML que rodam edge/on-prem: "otimize Gemma 3 4B sem chutar"
- Para devs full-stack: "Promptfoo + DSPy num produto pragmático"
- Para AI engineers em startups: "valide cost vs quality antes de migrar de GPT-4 para gpt-4o-mini"

### 13.3 Use Cases-Âncora

Casos de uso reais que validam o produto:

1. **Migração cloud → edge**: empresa quer trocar GPT-4 por Gemma3 local; Crucible otimiza prompt e mostra trade-off
2. **Multi-modelo selection**: dado um gabarito, qual modelo dá melhor custo/qualidade
3. **Regression em produção**: prompt em prod precisa mudança; valida que não quebrou nada
4. **Domain prompt engineering**: equipe jurídica/médica/financeira sem expertise em prompts itera empiricamente

---

## Apêndice A — Glossário

- **SLM** (Small Language Model): modelo ≤ ~10B parâmetros, geralmente rodável em hardware modesto
- **LLM-as-Judge**: usar um LLM para avaliar a saída de outro LLM
- **Few-shot**: prompt que inclui exemplos demonstrativos
- **High-water mark**: melhor valor já observado em uma série
- **Plateau detection**: identificar que métrica parou de melhorar
- **Bounded Context** (DDD): fronteira semântica dentro da qual um modelo é consistente
- **Port/Adapter**: padrão hexagonal — Port é interface no domínio, Adapter implementa na infra

## Apêndice B — Referências

- DSPy (Khattab et al.) — programmatic prompt optimization
- OPRO (Yang et al., DeepMind) — "Large Language Models as Optimizers"
- PromptAgent (Wang et al.) — strategic planning para prompt opt
- Promptfoo — referência de UX para eval
- Anthropic Cookbook — prompt engineering best practices
- "The Prompt Report" (Schulhoff et al., 2024) — taxonomia de técnicas

---

**Próximos passos sugeridos após este documento:**

1. Decidir naming definitivo (Crucible, Anvil, Refinaria, etc.)
2. Validar tese com 2-3 use cases reais (idealmente do seu portfolio: Sponsio, Huginn)
3. Spike técnico: implementar Fase 1 em ~3 dias para validar viabilidade
4. Decisão de modelo de distribuição: open source puro / open-core / proprietário
