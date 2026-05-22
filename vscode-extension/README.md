# Crucible VSCode Extension

Scaffold inicial da extensão VSCode do Crucible.

## Comandos

- `Crucible: Validate Prompt`
- `Crucible: Optimize Prompt`
- `Crucible: Open Dashboard`
- `Crucible: Open Latest HTML Report`
- `Crucible: Select Prompt, Gabarito and Config`

## Configurações

- `crucible.command`: prefixo do comando, padrão `uv run crucible`.
- `crucible.configPath`: caminho do `config.yaml`.
- `crucible.promptPath`: caminho do `prompt.txt`.
- `crucible.gabaritoPath`: caminho do `gabarito.yaml`.

## Desenvolvimento

```bash
npm install
npm run compile
npm run package
```

Abra esta pasta no VSCode e execute a extensão em modo debug.
