# Docker

Crucible can be executed as Docker image to expose the dashboard, REST API or any CLI command.

## Build Local

```bash
docker build -t crucible:local .
```

Smoke test:

```bash
docker run --rm crucible:local --help
```

By default, the image executes:

```bash
crucible serve --host 0.0.0.0 --port 7777
```

## Docker Compose for Normal Use

Use the compose runtime to pull the image published in the Docker Hub:

```bash
docker compose -f docker-compose.runtime.yml pull
docker compose -f docker-compose.runtime.yml up -d
```

By default, it uses:

```text
darcivieirajr/crucible:latest
```

Default URLs:

- Dashboard: `http://127.0.0.1:7777`
- API: `http://127.0.0.1:7788`

The state is in the volume named `crucible-data`. Work files are in `./workspace`, mounted inside
the container in `/workspace`. Place prompts, benchmarks and configs there. The root `.env` file is
mounted as `/workspace/.env`, which is where the Crucible seeks secrets inside the container.

Example:

```text
workspace/
  prompt.txt
  benchmark.yaml
  config.yaml
```

## Docker Compose for Development

The `docker-compose.yml` file is focused on local development: it builds the image from the current
code and mounts the repository root as `/workspace`.

```bash
docker compose up --build
```

Default URLs:

- Dashboard: `http://127.0.0.1:7777`
- API: `http://127.0.0.1:7788`

The development Compose configuration also uses the volume named `crucible-data` to persist SQLite,
reports,
runs and cache in `/data`.

To use external providers in the compose runtime, keep the variables in the `.env` of the root of
the directory where the compose is run. The file is mounted as read-only inside the container,
without using `env_file`; so `docker compose config` does not print the values of the secrets.

Examples:

```env
CRUCIBLE_OPENAI_API_KEY=...
CRUCIBLE_GOOGLE_API_KEY=...
```

When the target is Ollama, vLLM or llama.cpp running on the host, the Compose configuration points
to
`host.docker.internal` by default:

```env
CRUCIBLE_OLLAMA_URL=http://host.docker.internal:11434
CRUCIBLE_VLLM_URL=http://host.docker.internal:8000/v1
CRUCIBLE_LLAMACPP_URL=http://host.docker.internal:8080
```

## Use Image As CLI

```bash
docker run --rm \
  -v "$PWD:/workspace" \
  -v crucible-data:/data \
  crucible:local validate \
  --prompt prompt.txt \
  --benchmark benchmark.yaml \
  --config config.yaml
```

## Publishing to Docker Hub

The workflow `.github/workflows/publish-docker.yml` runs lint, typecheck, tests, local image build
and publishes in the Docker Hub.

Configure these secrets in GitHub:

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

Optionally configure the repository variable:

- `DOCKERHUB_REPOSITORY`: for example `your-username/crucible`.

If `DOCKERHUB_REPOSITORY` is not configured, workflow uses:

```text
<DOCKERHUB_USERNAME>/crucible
```

Published Tags:

- `latest` in versioned releases/tags;
- `X.Y.Z` and `X.Y` for `vX.Y.Z` tags;
- `edge` when run manually without a tag input;
- `sha-<commit>` for traceability.
