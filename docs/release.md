# Release

Crucible será distribuído como projeto open source sob licença MIT.

## Versionamento

O projeto usa versionamento semântico:

- `MAJOR`: mudanças incompatíveis de API, formato de storage ou configuração.
- `MINOR`: novas features compatíveis.
- `PATCH`: correções compatíveis.

Releases públicas devem ser criadas como GitHub Release com tag `vX.Y.Z`. A publicação
no PyPI e nos marketplaces da extensão VSCode é feita por GitHub Actions após os
testes passarem.

## Publicação Automática

Workflows:

- `.github/workflows/ci.yml`: testes, lint, build Python e pacote VSIX em PR/push.
- `.github/workflows/publish-python.yml`: publica no PyPI em release publicada.
- `.github/workflows/publish-vscode.yml`: publica a extensão em release publicada.
- `.github/workflows/publish-docker.yml`: publica imagem Docker no Docker Hub em
  release/tag versionada ou execução manual.

Segredos/ambiente esperados:

- PyPI: Trusted Publishing/OIDC configurado para o environment `pypi`.
- VSCode Marketplace: `VSCE_PAT`.
- Open VSX: `OVSX_PAT`.
- Docker Hub: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN` e, opcionalmente,
  variável de repositório `DOCKERHUB_REPOSITORY`.

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
git push origin v0.1.0
```

## Artefatos Esperados

- `.crucible/crucible.sqlite`
- `.crucible/reports/<run-id>.html`
- diretório do quickstart com `best_prompt.txt`
- changelog atualizado
