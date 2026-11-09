# Crucible VSCode Extension

Initial scaffold of the Crucible VSCode extension.

## Commands

- `Crucible: Validate Prompt`
- `Crucible: Optimize Prompt`
- `Crucible: Open Dashboard`
- `Crucible: Open Latest HTML Report`
- `Crucible: Select Prompt, Benchmark and Config`

## Settings

- `crucible.command`: command prefix, default `uv run crucible`.
- `crucible.configPath`: `config.yaml` path.
- `crucible.promptPath`: `prompt.txt` path.
- `crucible.benchmarkPath`: `benchmark.yaml` path.

## Development

```bash
npm install
npm run compile
npm run package
```

Open this folder in VSCode and run the extension in debug mode.
