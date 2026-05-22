# Release

Crucible será distribuído como projeto open source sob licença MIT.

## Checklist

1. Atualize `CHANGELOG.md`.
2. Rode:

```bash
bash scripts/release-check.sh
```

3. Rode quickstart com provider real:

```bash
bash scripts/quickstart-real-provider.sh .crucible-quickstart-real
```

Para smoke local sem provider externo:

```bash
CRUCIBLE_QUICKSTART_PROVIDER=fake bash scripts/quickstart-real-provider.sh .crucible-quickstart-fake
```

4. Opcionalmente rode smoke tests de providers reais:

```bash
CRUCIBLE_RUN_PROVIDER_SMOKE=1 \
CRUCIBLE_SMOKE_PROVIDER=ollama \
CRUCIBLE_SMOKE_MODEL=gemma3:4b \
uv run pytest tests/test_provider_smoke.py
```

5. Gere tag semver quando estiver pronto:

```bash
git tag v0.1.0
```

## Artefatos Esperados

- `.crucible/crucible.sqlite`
- `.crucible/reports/<run-id>.html`
- diretório do quickstart com `best_prompt.txt`
- changelog atualizado
