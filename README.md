# Crucible

[![CI](https://github.com/darcijunior/crucible/actions/workflows/ci.yml/badge.svg)](https://github.com/darcijunior/crucible/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/crucible.svg)](https://pypi.org/project/crucible/)
[![Python](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Crucible é um framework pragmático para otimização empírica de prompts. Ele executa
um prompt contra um gabarito versionado, mede qualidade/custo/latência, usa um modelo
de raciocínio para diagnosticar falhas, refina o prompt e mantém o melhor prompt
encontrado durante a run.

O projeto é local-first: CLI e SDK são as interfaces principais, SQLite guarda o
histórico consultável, relatórios são artefatos estáticos, e dashboard/API são
interfaces locais opcionais sobre os mesmos dados.

## O Que Ele Faz

- Valida prompts contra casos de teste ponderados.
- Otimiza prompts usando um `target_model` e um `reasoning_model`.
- Suporta Ollama, OpenAI-compatible APIs, Anthropic, Google, OpenRouter, vLLM,
  llama.cpp e provider fake para testes.
- Persiste runs em `.crucible/` para auditoria, comparação e reprodutibilidade.
- Gera relatórios HTML, JSON e PDF.
- Exporta verdicts em CSV/Parquet e o melhor prompt em texto.
- Registra Pareto frontier para otimização qualidade x custo x latência.
- Sugere novos casos de gabarito a partir de falhas, regressões e instabilidade.
- Oferece CLI, SDK Python, dashboard local e REST API.
- Permite assertions e importadores customizados via plugins.
- Inclui scaffold de extensão VSCode.

## Quickstart

O fluxo normal não começa otimizando. Primeiro você valida se o prompt, o gabarito e
os providers estão funcionando; depois estima custo; só então roda a otimização.

```bash
uv sync
uv run crucible init ./my-prompt
uv run crucible validate --prompt ./my-prompt/prompt.txt --gabarito ./my-prompt/gabarito.yaml --config ./my-prompt/config.yaml
uv run crucible estimate-cost --config ./my-prompt/config.yaml
uv run crucible optimize --config ./my-prompt/config.yaml
uv run crucible serve
```

Abra `http://127.0.0.1:7777` para inspecionar o histórico local.

O template criado pelo `init` usa Ollama como modelo alvo e OpenAI como modelo de
raciocínio. Ajuste `config.yaml` antes de rodar se esses providers não estiverem
disponíveis.

## Como Pensar No Fluxo

`validate` responde: "o prompt atual passa no meu gabarito?".

Ele executa apenas a versão atual do prompt, calcula score e mostra se o setup está
correto. Use para depurar gabarito, provider, assertion e formato de saída.

`optimize` responde: "o Crucible consegue melhorar este prompt?".

Ele executa o prompt, encontra falhas, pede ao `reasoning_model` um diagnóstico,
gera uma nova versão do prompt e repete até bater threshold, budget ou outro critério
de parada. A run sempre preserva o melhor prompt encontrado, não necessariamente o
último.

## Uso Mínimo Via SDK

```python
from crucible import Gabarito, Optimizer, OptimizationConfig, Prompt

config = OptimizationConfig.model_validate({...})
prompt = Prompt.from_file("prompt.txt")
gabarito = Gabarito.from_yaml("gabarito.yaml")

optimizer = Optimizer(config)
estimate = optimizer.estimate_cost(prompt, gabarito)
run = await optimizer.optimize(prompt, gabarito)
report_path = await optimizer.report(run.id, format="html")
```

## Estado Local

Crucible escreve estado local em `.crucible/`:

- `.crucible/crucible.sqlite`: índice consultável de runs, iterações e verdicts.
- `.crucible/runs/`: payloads completos, JSONL de iterações/verdicts e melhor prompt.
- `.crucible/reports/`: relatórios gerados.
- `.crucible/cache/`: cache de execuções.

Isso é intencional. Histórico de run é dado de produto, não arquivo temporário.
Use `/tmp` apenas para execuções descartáveis.

## Comandos Comuns

```bash
uv run crucible estimate-cost --config ./my-prompt/config.yaml
uv run crucible validate --prompt prompt.txt --gabarito gabarito.yaml --config config.yaml
uv run crucible optimize --config config.yaml
uv run crucible list-runs
uv run crucible show-run --run latest
uv run crucible report --run latest --format html
uv run crucible export --run latest --format csv --output ./verdicts.csv
uv run crucible split-gabarito --gabarito gabarito.yaml --output-dir ./splits
uv run crucible serve
uv run crucible api --port 7788
```

## Documentação

Comece por aqui:

- [Índice da documentação](docs/index.md)
- [Quickstart](docs/quickstart.md)
- [Tutorial end-to-end](docs/tutorials/customer-support-end-to-end.md)
- [Conceitos](docs/concepts.md)
- [Referência CLI](docs/cli.md)
- [Configuração](docs/configuration.md)
- [Gabaritos e Assertions](docs/gabaritos-and-assertions.md)
- [Scoring](docs/scoring.md)
- [Providers](docs/providers.md)
- [SDK Python](docs/sdk.md)
- [Dashboard](docs/dashboard.md)
- [REST API](docs/api.md)
- [Plugins](docs/plugins.md)
- [Importadores e Exports](docs/importers-and-exports.md)
- [Operação](docs/operations.md)
- [Release](docs/release.md)
- [Arquitetura e Implementação](docs/architecture.md)
- [Decisões Técnicas](docs/technical-decisions.md)
- [UX e Interfaces](docs/interfaces.md)
- [Desenvolvimento](docs/development.md)
- [Contribuição](CONTRIBUTING.md)
- [Segurança](SECURITY.md)

Exemplos:

- [Projeto básico](examples/basic/)
- [Triagem de suporte](examples/customer-support-triage/)
- [LLM-as-judge para risco](examples/llm-judge-risk/)
- [Train/val/test](examples/train-val-test/)
- [Saída estruturada com JSON Schema](examples/structured-output/)

## Licença

Crucible é open source sob licença MIT.
