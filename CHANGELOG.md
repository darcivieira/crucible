# Changelog

All notable changes to Crucible will be documented in this file.

The format follows Keep a Changelog conventions and the project uses semantic
versioning once the first public release is tagged.

## Unreleased

### Added

- Local-first prompt optimization CLI, SDK, dashboard and REST API.
- SQLite run history, file artifacts, static reports and exports.
- Provider adapters for local and cloud LLM endpoints.
- Plugin system for custom assertions and importers.
- Persistent API task state and cancellation request support.
- Multi-objective iteration scoring and Pareto frontier tracking.
- Active learning suggestions from failing, regressing and unstable cases.
- Optional Ray/Dask execution backends.
- Optional live provider smoke test harness.
- VSCode extension scaffold.
- MIT license for open source distribution.

### Changed

- Standardized code, comments, internal prompts, interface text, examples, and all
  documentation on English.
- Renamed the public benchmark model, SDK arguments, CLI commands/options, API
  fields, configuration keys, and example files to English names. This is a
  breaking change: existing integrations, configuration files, and saved run
  payloads must be updated before use. No automatic data migration is included.
