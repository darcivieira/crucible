# Release

Crucible will be distributed as open source project under MIT license.

## Version

The project uses semantic versioning:

- `MAJOR`: incompatible API changes, storage format or configuration.
- `MINOR`: new compatible features.
- `PATCH`: Compatible fixes.

Public releases should be created as GitHub Release with `vX.Y.Z` tag. Posting in PyPI and VSCode
extension marketplaces is done by GitHub Actions after the tests have passed.

## Automatic Publication

Workflows:

- `.github/workflows/ci.yml`: tests, lint, Python build and VSIX package in PR/push.
- `.github/workflows/publish-python.yml`: publishes in PyPI in published release.
- `.github/workflows/publish-vscode.yml`: publishes the published release extension.
- `.github/workflows/publish-docker.yml`: publishes Docker image in Docker Hub in release/tag
  versioned or manual execution.

Secrets/environment expected:

- PyPI: Trusted Publishing/OIDC configured for `pypi` environment.
- VSCode Marketplace: `VSCE_PAT`.
- Open VSX: `OVSX_PAT`.
- Docker Hub: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN` and optionally `DOCKERHUB_REPOSITORY`
  repository variable.

## Checklist

1. Update `CHANGELOG.md`.
2. Run:

```bash
bash scripts/release-check.sh
```

3. Run the quickstart with a real provider:

```bash
bash scripts/quickstart-real-provider.sh .crucible-quickstart-real
```

For a local smoke test without an external provider:

```bash
CRUCIBLE_QUICKSTART_PROVIDER=fake bash scripts/quickstart-real-provider.sh .crucible-quickstart-fake
```

4. Optionally run smoke tests from real providers:

```bash
CRUCIBLE_RUN_PROVIDER_SMOKE=1 \
CRUCIBLE_SMOKE_PROVIDER=ollama \
CRUCIBLE_SMOKE_MODEL=gemma3:4b \
uv run pytest tests/test_provider_smoke.py
```

5. Create and push the tag when you are ready:

```bash
git tag v0.1.0
git push origin v0.1.0
```

## Expected artifacts

- `.crucible/crucible.sqlite`
- `.crucible/reports/<run-id>.html`
- quickstart directory with `best_prompt.txt`
- changelog updated
