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

## Docker Compose Para Uso Normal

Use o compose runtime para puxar a imagem publicada no Docker Hub:

```bash
docker compose -f docker-compose.runtime.yml pull
docker compose -f docker-compose.runtime.yml up -d
```

Por padrão ele usa:

```text
darcivieirajr/crucible:latest
```

URLs padrão:

- Dashboard: `http://127.0.0.1:7777`
- API: `http://127.0.0.1:7788`

O estado fica no volume nomeado `crucible-data`. Arquivos de trabalho ficam em
`./workspace`, montado dentro do container em `/workspace`. Coloque ali prompts,
gabaritos e configs. O arquivo `.env` da raiz é montado como `/workspace/.env`, que
é onde o Crucible procura secrets dentro do container.

Exemplo:

```text
workspace/
  prompt.txt
  gabarito.yaml
  config.yaml
```

## Docker Compose Para Desenvolvimento

O arquivo `docker-compose.yml` é voltado a desenvolvimento local: ele faz build da
imagem a partir do código atual e monta a raiz do repositório como `/workspace`.

```bash
docker compose up --build
```

URLs padrão:

- Dashboard: `http://127.0.0.1:7777`
- API: `http://127.0.0.1:7788`

O compose de desenvolvimento também usa o volume nomeado `crucible-data` para
persistir SQLite, reports, runs e cache em `/data`.

Para usar providers externos no compose runtime, mantenha as variáveis no `.env` da
raiz do diretório onde o compose é executado. O arquivo é montado como read-only
dentro do container, sem usar `env_file`; assim `docker compose config` não imprime
os valores dos secrets.

Exemplos:

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
