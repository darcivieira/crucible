from __future__ import annotations

from crucible.modules.optimizer.domain.models import (
    CostEstimate,
    Gabarito,
    ModelSpec,
    OptimizationConfig,
    Prompt,
)


def estimate_cost(prompt: Prompt, gabarito: Gabarito, config: OptimizationConfig) -> CostEstimate:
    if config.target_model is None:
        raise ValueError("target_model is required for estimate-cost")
    if config.reasoning_model is None:
        raise ValueError("reasoning_model is required for estimate-cost")
    rendered_prompts = [prompt.render(input_text=case.input) for case in gabarito.cases]
    target_input_tokens_per_iteration = sum(_rough_tokens(item) for item in rendered_prompts)
    target_output_tokens_per_iteration = len(gabarito.cases) * config.target_model.params.max_tokens
    target_multiplier = config.max_iterations * config.n_runs_per_case

    reasoning_input_tokens = (
        _rough_tokens(prompt.template)
        + sum(
            _rough_tokens(case.input) + _rough_tokens(case.expected_output)
            for case in gabarito.cases
        )
    ) * max(0, config.max_iterations - 1)
    reasoning_output_tokens = (
        config.reasoning_model.params.max_tokens * 2 * max(0, config.max_iterations - 1)
    )

    target_input = target_input_tokens_per_iteration * target_multiplier
    target_output = target_output_tokens_per_iteration * target_multiplier
    target_cost = _model_cost(config.target_model, target_input, target_output)
    reasoning_cost = _model_cost(
        config.reasoning_model, reasoning_input_tokens, reasoning_output_tokens
    )

    return CostEstimate(
        cases_count=len(gabarito.cases),
        max_iterations=config.max_iterations,
        target_input_tokens=target_input,
        target_output_tokens=target_output,
        reasoning_input_tokens=reasoning_input_tokens,
        reasoning_output_tokens=reasoning_output_tokens,
        estimated_target_cost_usd=target_cost,
        estimated_reasoning_cost_usd=reasoning_cost,
        estimated_total_cost_usd=target_cost + reasoning_cost,
    )


def _model_cost(model: ModelSpec, tokens_in: int, tokens_out: int) -> float:
    return (
        tokens_in / 1_000_000 * model.cost_per_million_input_tokens_usd
        + tokens_out / 1_000_000 * model.cost_per_million_output_tokens_usd
    )


def _rough_tokens(text: str) -> int:
    return max(1, len(text) // 4)
