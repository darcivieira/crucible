# Docker

Crucible pode ser executado como imagem Docker para expor o dashboard, a REST API ou
qualquer comando do CLI.

## Build Local

```bash
docker build -t crucible:local .
```

Smoke test:

```bash
docker run --rm crucible:local --help
```

Por padrão, a imagem executa:

```bash
crucible serve --host 0.0.0.0 --port 7777
```

## Docker Compose

Suba dashboard e API:

```bash
docker compose up --build
```

URLs padrão:

- Dashboard: `http://127.0.0.1:7777`
- API: `http://127.0.0.1:7788`

O compose usa um volume nomeado `crucible-data` para persistir SQLite, reports, runs
e cache em `/data`. O diretório do projeto também é montado em `/workspace`, então
arquivos locais como `prompt.txt`, `gabarito.yaml`, `config.yaml` e `.env` ficam
disponíveis dentro do container.

Para usar providers externos, mantenha as variáveis no `.env` local ou passe `-e` no
`docker run`. Exemplos:

```env
CRUCIBLE_OPENAI_API_KEY=...
CRUCIBLE_GOOGLE_API_KEY=...
```

Quando o target for Ollama, vLLM ou llama.cpp rodando no host, o compose aponta para
`host.docker.internal` por padrão:

```env
CRUCIBLE_OLLAMA_URL=http://host.docker.internal:11434
CRUCIBLE_VLLM_URL=http://host.docker.internal:8000/v1
CRUCIBLE_LLAMACPP_URL=http://host.docker.internal:8080
```

## Usar A Imagem Como CLI

```bash
docker run --rm \
  -v "$PWD:/workspace" \
  -v crucible-data:/data \
  crucible:local validate \
  --prompt prompt.txt \
  --gabarito gabarito.yaml \
  --config config.yaml
```

## Publicação No Docker Hub

O workflow `.github/workflows/publish-docker.yml` roda lint, typecheck, testes,
build local da imagem e publica no Docker Hub.

Configure estes secrets no GitHub:

- `DOCKERHUB_USERNAME`
- `DOCKERHUB_TOKEN`

Opcionalmente configure a variável de repositório:

- `DOCKERHUB_REPOSITORY`: por exemplo `seu-usuario/crucible`.

Se `DOCKERHUB_REPOSITORY` não for configurada, o workflow usa:

```text
<DOCKERHUB_USERNAME>/crucible
```

Tags publicadas:

- `latest` em releases/tags versionadas;
- `X.Y.Z` e `X.Y` para tags `vX.Y.Z`;
- `edge` quando acionado manualmente sem alterar o input;
- `sha-<commit>` para rastreabilidade.
