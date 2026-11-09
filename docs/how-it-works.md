# How It Works

This document was kept as a shortcut to old links.

The operation of Crucible is now documented in:

- [Concepts](concepts.md)
- [Benchmarks and Assertions](benchmarks-and-assertions.md)
- [Architecture and Implementation](architecture.md)
- [Operations](operations.md)

The practical summary: Crucible executes the prompt against a benchmark, calculates score, diagnoses
flaws with a reasoning model, refines the prompt and preserves the best prompt seen during the run.

Before refining, Crucible builds a task contract based on the initial prompt, the `config.yaml` and
the benchmark. This contract preserves critical rules such as output format, JSON fields, literal
extraction, restrictions on "do not invent" and patterns observed in expected outputs.

If a prompt proposal violates this contract, it is rejected before calling the `target_model` again.
Crucible then asks `reasoning_model` to remake the proposal using the concrete reasons for
rejection. This repair happens within the same iteration, so there is no new execution with
identical prompt.

After `max_refinement_repair_attempts` attempts without a valid prompt, the run stops with
`stop_reason: reasoning_failed_to_refine`. This prevents loops in which the reasoning model degrades
the prompt or repeatedly removes critical rules such as literal extraction, `{input}`, or the
prohibition on inventing information.
