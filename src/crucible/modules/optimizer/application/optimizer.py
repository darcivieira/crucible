from __future__ import annotations

import asyncio
import json
from collections import Counter
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, pstdev
from time import perf_counter
from typing import Any

from crucible.core.exceptions import InvalidRefinement
from crucible.core.settings import get_settings
from crucible.modules.optimizer.adapters.cache import JsonlExecutionCache, execution_cache_key
from crucible.modules.optimizer.adapters.providers.factory import (
    ModelProviderFactory,
    get_provider_factory,
)
from crucible.modules.optimizer.adapters.storage import (
    CompositeRunStore,
    FileRunStore,
    SQLiteRunStore,
)
from crucible.modules.optimizer.application.active_learning import suggest_cases
from crucible.modules.optimizer.application.estimates import estimate_cost
from crucible.modules.optimizer.application.execution_backends import execution_backend
from crucible.modules.optimizer.application.multi_objective import update_multi_objective
from crucible.modules.optimizer.application.reports import write_report
from crucible.modules.optimizer.domain.assertions import AssertionContext
from crucible.modules.optimizer.domain.models import (
    CompletionResult,
    Diagnosis,
    ExecutionResult,
    Gabarito,
    Iteration,
    IterationMemory,
    ModelSpec,
    OptimizationConfig,
    OptimizationRun,
    Prompt,
    RefinementProposal,
    StopReason,
    TestCase,
    Verdict,
)
from crucible.modules.optimizer.domain.protocols import ExecutionCache, ModelProvider, RunStore
from crucible.modules.optimizer.domain.scoring import aggregate_score


class Optimizer:
    def __init__(
        self,
        config: OptimizationConfig,
        provider_factory: ModelProviderFactory | None = None,
        store: RunStore | None = None,
        cache: ExecutionCache | None = None,
        target_provider: ModelProvider | None = None,
        reasoning_provider: ModelProvider | None = None,
        judge_provider: ModelProvider | None = None,
        judge_providers: list[ModelProvider] | None = None,
        should_cancel: Callable[[], bool | Awaitable[bool]] | None = None,
    ):
        settings = get_settings()
        self.config = config
        self.provider_factory = provider_factory or get_provider_factory()
        self.store = store or CompositeRunStore(
            SQLiteRunStore(settings.sqlite_path),
            FileRunStore(settings.runs_dir),
        )
        self.cache = cache or JsonlExecutionCache(settings.cache_dir / "executions.jsonl")
        self.execution_backend = execution_backend(
            config.execution_backend, config.distributed_workers
        )
        self.target_provider = target_provider or self.provider_factory.get(config.target_model)
        self.reasoning_provider = reasoning_provider or self.provider_factory.get(
            config.reasoning_model
        )
        self.judge_specs = config.judge_models or [config.judge_model or config.reasoning_model]
        self.judge_providers = judge_providers or [
            self.provider_factory.get(spec) for spec in self.judge_specs
        ]
        self.judge_provider = judge_provider or self.judge_providers[0]
        self.embedding_provider = (
            self.provider_factory.get_embedding(config.embedding_model)
            if config.embedding_model is not None
            else None
        )
        self.should_cancel = should_cancel

    async def validate(self, prompt: Prompt, gabarito: Gabarito) -> Iteration:
        return await self._run_iteration(
            version=0,
            prompt=prompt,
            gabarito=gabarito,
            previous_verdicts=None,
            diagnosis=None,
            proposal=None,
        )

    def estimate_cost(self, prompt: Prompt, gabarito: Gabarito):
        return estimate_cost(prompt, gabarito, self.config)

    async def load_run(self, run_id: str) -> OptimizationRun:
        return await self.store.load_run(run_id)

    async def report(
        self, run_id: str, format: str = "html", reports_dir: Path | None = None
    ) -> Path:
        settings = get_settings()
        run = await self.load_run(run_id)
        return write_report(run, reports_dir or settings.reports_dir, format)

    async def optimize(self, prompt: Prompt, gabarito: Gabarito) -> OptimizationRun:
        if self.config.use_gabarito_split:
            train_set, val_set, test_set = gabarito.split(
                train=self.config.train_ratio,
                val=self.config.val_ratio,
            )
            run = await self._optimize_loop(prompt, train_set)
            best = run.best_iteration
            if best is not None:
                val_iteration = await self.validate(best.prompt, val_set)
                test_iteration = await self.validate(best.prompt, test_set)
                run.validation_scores = {
                    "train": best.score,
                    "val": val_iteration.score,
                    "test": test_iteration.score,
                    "train_val_gap": best.score - val_iteration.score,
                }
                await self.store.save_run(run)
            return run
        return await self._optimize_loop(prompt, gabarito)

    async def _optimize_loop(self, prompt: Prompt, gabarito: Gabarito) -> OptimizationRun:
        run = OptimizationRun(
            config=self.config,
            gabarito_hash=gabarito.content_hash,
            initial_prompt_hash=prompt.content_hash,
        )
        current_prompt = prompt
        previous_verdicts: list[Verdict] | None = None
        pending_diagnosis: Diagnosis | None = None
        pending_proposal: RefinementProposal | None = None

        while True:
            if await self._cancel_requested():
                run.status = "aborted"
                run.stop_reason = "cancelled"
                run.ended_at = datetime.now(UTC)
                update_multi_objective(run)
                run.active_learning_suggestions = suggest_cases(
                    run, self.config.active_learning_suggestions
                )
                await self.store.save_run(run)
                return run
            try:
                iteration = await self._run_iteration(
                    version=len(run.iterations),
                    prompt=current_prompt,
                    gabarito=gabarito,
                    previous_verdicts=previous_verdicts,
                    diagnosis=pending_diagnosis,
                    proposal=pending_proposal,
                )
            except asyncio.CancelledError:
                run.status = "aborted"
                run.stop_reason = "cancelled"
                run.ended_at = datetime.now(UTC)
                update_multi_objective(run)
                run.active_learning_suggestions = suggest_cases(
                    run, self.config.active_learning_suggestions
                )
                await self.store.save_run(run)
                return run
            run.iterations.append(iteration)
            update_multi_objective(run)
            await self.store.save_iteration(run)

            stop_reason = self._stop_reason(run)
            if stop_reason is not None:
                run.status = "completed"
                run.stop_reason = stop_reason
                run.ended_at = datetime.now(UTC)
                update_multi_objective(run)
                run.active_learning_suggestions = suggest_cases(
                    run, self.config.active_learning_suggestions
                )
                await self.store.save_run(run)
                return run

            failures = select_failures_for_refinement(
                iteration.verdicts,
                max_cases=self.config.max_failures_for_refinement,
            )
            if not failures:
                run.status = "completed"
                run.stop_reason = "no_failures"
                run.ended_at = datetime.now(UTC)
                update_multi_objective(run)
                run.active_learning_suggestions = suggest_cases(
                    run, self.config.active_learning_suggestions
                )
                await self.store.save_run(run)
                return run

            diagnosis = await self._diagnose(current_prompt, failures, run.iterations)
            proposal = await self._refine(current_prompt, diagnosis, run.iterations)
            violations = proposal.violations(current_prompt)
            if violations:
                raise InvalidRefinement(", ".join(violations))

            current_prompt = Prompt(
                template=proposal.new_prompt,
                variables=current_prompt.variables,
                metadata=current_prompt.metadata,
            )
            previous_verdicts = iteration.verdicts
            pending_diagnosis = diagnosis
            pending_proposal = proposal

    async def _run_iteration(
        self,
        version: int,
        prompt: Prompt,
        gabarito: Gabarito,
        previous_verdicts: list[Verdict] | None,
        diagnosis: Diagnosis | None,
        proposal: RefinementProposal | None,
    ) -> Iteration:
        started = datetime.now(UTC)
        previous_by_case = {v.test_case.id: v for v in previous_verdicts or []}
        semaphore = asyncio.Semaphore(self.config.parallelism)

        async def run_case(test_case: TestCase) -> Verdict:
            async with semaphore:
                if await self._cancel_requested():
                    raise asyncio.CancelledError
                return await self._execute_case(prompt, test_case, previous_by_case)

        def job_for(test_case: TestCase) -> Callable[[], Awaitable[Verdict]]:
            async def job() -> Verdict:
                return await run_case(test_case)

            return job

        jobs: list[Callable[[], Awaitable[Verdict]]] = []
        for test_case in gabarito.cases:
            jobs.append(job_for(test_case))
        verdicts = await self.execution_backend.gather(jobs)
        return Iteration(
            version=version,
            prompt=prompt,
            verdicts=verdicts,
            score_report=aggregate_score(verdicts),
            refinement_rationale=proposal.rationale if proposal else None,
            diagnosis=diagnosis,
            diff_summary=proposal.diff_summary if proposal else None,
            timestamp_started=started,
            timestamp_ended=datetime.now(UTC),
        )

    async def _execute_case(
        self,
        prompt: Prompt,
        test_case: TestCase,
        previous_by_case: dict[str, Verdict],
    ) -> Verdict:
        rendered = prompt.render(input_text=test_case.input)
        runs = await asyncio.gather(
            *(
                self._cached_call_target(prompt, test_case, rendered, run_index)
                for run_index in range(self.config.n_runs_per_case)
            )
        )
        execution, run_details = _aggregate_executions(
            test_case.id,
            runs,
            instability_std_threshold_ms=self.config.instability_std_threshold_ms,
        )

        context = AssertionContext(
            judge_provider=self.judge_provider,
            judge_providers=self.judge_providers,
            embedding_provider=self.embedding_provider,
            judge_params=(self.config.judge_model or self.config.reasoning_model).params,
            judge_params_list=[spec.params for spec in self.judge_specs],
        )
        assertion = await test_case.assertion.evaluate(
            test_case.expected_output,
            execution.actual_output,
            context,
        )
        detail = dict(assertion.detail)
        if run_details:
            detail["runs"] = run_details
        previous = previous_by_case.get(test_case.id)
        return Verdict(
            test_case=test_case,
            execution=execution,
            score=assertion.score,
            passed=assertion.passed,
            assertion_detail=detail,
            is_regression=bool(previous and previous.passed and not assertion.passed),
        )

    async def _cached_call_target(
        self,
        prompt: Prompt,
        test_case: TestCase,
        rendered: str,
        run_index: int,
    ) -> ExecutionResult:
        cache_input = (
            test_case.input
            if self.config.n_runs_per_case == 1
            else f"{test_case.input}\n\n__crucible_run_index__={run_index}"
        )
        cache_key = execution_cache_key(prompt, cache_input, self.config.target_model)
        execution = await self.cache.get(cache_key)
        if execution is None:
            execution = await self._call_target(rendered, test_case.id)
            await self.cache.set(cache_key, execution)
        return execution

    async def _call_target(self, rendered_prompt: str, test_case_id: str) -> ExecutionResult:
        started = perf_counter()
        try:
            result = await self.target_provider.complete(
                rendered_prompt, self.config.target_model.params
            )
            error = None
        except Exception as exc:
            result = CompletionResult(text="", finish_reason="error")
            error = str(exc)
        latency_ms = result.raw.get("latency_ms") or ((perf_counter() - started) * 1000)
        return ExecutionResult(
            test_case_id=test_case_id,
            actual_output=result.text,
            latency_ms=latency_ms,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            cost_usd=_cost_usd(result, self.config.target_model),
            finish_reason=result.finish_reason,
            error=error,
        )

    async def _diagnose(
        self,
        prompt: Prompt,
        failures: list[Verdict],
        iterations: list[Iteration],
    ) -> Diagnosis:
        completion = await self.reasoning_provider.complete(
            _diagnosis_prompt(prompt, self.config.target_model, failures, _memory(iterations)),
            self.config.reasoning_model.params,
        )
        payload = _json_payload(completion.text)
        return Diagnosis(
            pattern=str(payload.get("pattern", "Falhas sem padrão estruturado.")),
            hypothesis=str(
                payload.get("hypothesis", "O prompt atual não especifica a resposta esperada.")
            ),
            category=str(payload.get("category", "INSTRUCTION_AMBIGUITY")),
            confidence=float(payload.get("confidence", 0.5)),
            is_model_limitation=bool(payload.get("is_model_limitation", False)),
        )

    async def _refine(
        self,
        prompt: Prompt,
        diagnosis: Diagnosis,
        iterations: list[Iteration],
    ) -> RefinementProposal:
        completion = await self.reasoning_provider.complete(
            _refinement_prompt(prompt, self.config.target_model, diagnosis, _memory(iterations)),
            self.config.reasoning_model.params,
        )
        payload = _json_payload(completion.text)
        return RefinementProposal(
            new_prompt=str(payload.get("new_prompt", prompt.template)),
            diff_summary=str(payload.get("diff_summary", "")),
            rationale=str(payload.get("rationale", "")),
            expected_improvement=str(payload.get("expected_improvement", "")),
            confidence=float(payload.get("confidence", 0.5)),
        )

    def _stop_reason(self, run: OptimizationRun) -> StopReason | None:
        best = run.best_iteration
        if best is not None and best.score >= self.config.threshold:
            return "threshold_reached"
        if len(run.iterations) >= self.config.max_iterations:
            return "max_iterations"
        if run.total_cost_usd >= self.config.max_cost_usd:
            return "budget_exhausted"
        elapsed = (datetime.now(UTC) - run.started_at).total_seconds()
        if elapsed >= self.config.max_wallclock_seconds:
            return "time_exhausted"
        if _plateau(run.score_history, self.config.plateau_window, self.config.plateau_min_delta):
            return "plateau"
        return None

    async def _cancel_requested(self) -> bool:
        if self.should_cancel is None:
            return False
        result = self.should_cancel()
        if asyncio.iscoroutine(result):
            return bool(await result)
        return bool(result)


def select_failures_for_refinement(verdicts: list[Verdict], max_cases: int = 10) -> list[Verdict]:
    failures = [verdict for verdict in verdicts if not verdict.passed]
    regressions = [verdict for verdict in failures if verdict.is_regression]
    worst = sorted(failures, key=lambda verdict: verdict.score)
    by_tag: dict[str, Verdict] = {}
    for verdict in worst:
        for tag in verdict.test_case.tags:
            by_tag.setdefault(tag, verdict)
    selected: list[Verdict] = []
    seen: set[str] = set()
    for verdict in [*regressions, *worst, *by_tag.values()]:
        if verdict.test_case.id not in seen:
            selected.append(verdict)
            seen.add(verdict.test_case.id)
        if len(selected) >= max_cases:
            break
    return selected


def _cost_usd(result: CompletionResult, model: ModelSpec) -> float:
    input_cost = result.tokens_in / 1_000_000 * model.cost_per_million_input_tokens_usd
    output_cost = result.tokens_out / 1_000_000 * model.cost_per_million_output_tokens_usd
    return input_cost + output_cost


def _plateau(scores: list[float], window: int, min_delta: float) -> bool:
    if window <= 1 or len(scores) < window:
        return False
    recent = scores[-window:]
    return max(recent) - min(recent) < min_delta


def _aggregate_executions(
    test_case_id: str,
    runs: list[ExecutionResult],
    instability_std_threshold_ms: float = 250.0,
) -> tuple[ExecutionResult, dict[str, Any] | None]:
    if len(runs) == 1:
        return runs[0], None
    output_counts = Counter(run.actual_output for run in runs)
    majority_output, majority_count = output_counts.most_common(1)[0]
    latencies = [run.latency_ms for run in runs]
    execution = ExecutionResult(
        test_case_id=test_case_id,
        actual_output=majority_output,
        latency_ms=mean(latencies),
        tokens_in=sum(run.tokens_in for run in runs),
        tokens_out=sum(run.tokens_out for run in runs),
        cost_usd=sum(run.cost_usd for run in runs),
        finish_reason="majority_vote",
        error="; ".join(run.error for run in runs if run.error) or None,
    )
    latency_std = pstdev(latencies) if len(latencies) > 1 else 0.0
    unique_outputs = len(output_counts)
    return execution, {
        "count": len(runs),
        "majority_count": majority_count,
        "latency_std_ms": latency_std,
        "unique_outputs": unique_outputs,
        "unstable": unique_outputs > 1 or latency_std > instability_std_threshold_ms,
        "outputs": dict(output_counts),
    }


def _memory(iterations: list[Iteration]) -> list[IterationMemory]:
    return [
        IterationMemory(
            version=iteration.version,
            prompt_hash=iteration.prompt.content_hash,
            score=iteration.score,
            proposed_change=iteration.refinement_rationale,
            diff_summary=iteration.diff_summary,
            failure_pattern=iteration.diagnosis.pattern if iteration.diagnosis else None,
        )
        for iteration in iterations
    ]


def _json_payload(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned.removeprefix("```json").removesuffix("```").strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(cleaned[start:end])
        raise


def _diagnosis_prompt(
    prompt: Prompt,
    target_model: ModelSpec,
    failures: list[Verdict],
    history: list[IterationMemory],
) -> str:
    target = f"{target_model.provider}/{target_model.model_id}"
    cases = "\n\n".join(
        (
            f"Caso {verdict.test_case.id} tags={verdict.test_case.tags} score={verdict.score}\n"
            f"INPUT:\n{verdict.test_case.input}\n"
            f"EXPECTED:\n{verdict.test_case.expected_output}\n"
            f"ACTUAL:\n{verdict.execution.actual_output}\n"
            f"ASSERTION:\n{verdict.test_case.assertion.type}\n"
            f"DETAIL:\n{verdict.assertion_detail}"
        )
        for verdict in failures
    )
    return (
        f"Você é especialista em prompt engineering para {target}.\n\n"
        f"PROMPT ATUAL:\n---\n{prompt.template}\n---\n\n"
        f"HISTÓRICO:\n{[item.model_dump() for item in history]}\n\n"
        f"CASOS FALHOS:\n{cases}\n\n"
        "Retorne JSON estrito com pattern, hypothesis, category, confidence e is_model_limitation."
    )


def _refinement_prompt(
    prompt: Prompt,
    target_model: ModelSpec,
    diagnosis: Diagnosis,
    history: list[IterationMemory],
) -> str:
    return (
        f"Você está refatorando um prompt para {target_model.provider}/{target_model.model_id}.\n\n"
        f"PROMPT ATUAL:\n---\n{prompt.template}\n---\n\n"
        f"VARIÁVEIS OBRIGATÓRIAS: {prompt.variables}\n"
        f"DIAGNÓSTICO: {diagnosis.model_dump()}\n"
        f"HISTÓRICO: {[item.model_dump() for item in history]}\n\n"
        "Retorne JSON estrito com new_prompt, diff_summary, rationale, "
        "expected_improvement e confidence. "
        "Mantenha todas as variáveis obrigatórias no novo prompt."
    )
