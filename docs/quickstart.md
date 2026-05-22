# Quickstart

Este guia leva você de um diretório vazio até uma run otimizada e visível no
dashboard local.

## Pré-Requisitos

- Python 3.13.
- `uv`.
- Pelo menos um provider para o modelo alvo.
- Um provider de raciocínio para `optimize`; `validate` precisa apenas do target.

Para uma primeira execução local com Ollama:

```bash
ollama pull gemma3:4b
```

Para modelos cloud, exporte a chave correspondente:

```bash
export CRUCIBLE_OPENAI_API_KEY=...
```

## Instalar Dependências

Na raiz do repositório:

```bash
uv sync
```

## Criar Um Projeto

```bash
uv run crucible init ./my-prompt
```

Isso cria:

```text
my-prompt/
  prompt.txt
  gabarito.yaml
  config.yaml
```

Esses três arquivos são o núcleo do Crucible:

- `prompt.txt`: o prompt que será avaliado e depois otimizado.
- `gabarito.yaml`: os casos de teste que dizem o que é uma resposta boa.
- `config.yaml`: modelos, budget, paralelismo e critérios de parada.

## Configurar Modelos

Edite `./my-prompt/config.yaml`:

```yaml
target_model:
  provider: ollama
  model_id: gemma3:4b
  role: target

reasoning_model:
  provider: openai
  model_id: gpt-5
  role: reasoning
```

Se ainda não quiser chamar um modelo de raciocínio cloud, comece validando:

```bash
uv run crucible validate \
  --prompt ./my-prompt/prompt.txt \
  --gabarito ./my-prompt/gabarito.yaml \
  --config ./my-prompt/config.yaml
```

`validate` é o check de sanidade do projeto. Ele executa o prompt atual contra o
gabarito e mostra score, pass rate, custo e latência. Se esse comando falhar, corrija
provider, prompt, gabarito ou assertion antes de rodar `optimize`.

## Estimar Custo

```bash
uv run crucible estimate-cost --config ./my-prompt/config.yaml
```

A estimativa é aproximada. Ela usa uma heurística simples de tokens e os preços
declarados em cada `ModelSpec`.

## Otimizar

```bash
uv run crucible optimize --config ./my-prompt/config.yaml
```

`optimize` é a etapa em que o Crucible passa de avaliação para melhoria automática.
Ele usa o `reasoning_model` para olhar os casos que falharam, identificar padrões de
erro e propor uma nova versão do prompt.

O Crucible irá:

1. Executar o prompt inicial.
2. Avaliar todos os casos do gabarito.
3. Diagnosticar falhas com o modelo de raciocínio.
4. Gerar um prompt refinado.
5. Repetir até atingir threshold, budget, tempo, plateau ou máximo de iterações.

O resultado final aponta sempre para o melhor prompt visto durante a run.

Isso importa porque uma iteração posterior pode piorar. O histórico fica guardado,
mas o "best prompt" continua sendo a melhor versão encontrada.

## Inspecionar Resultados

```bash
uv run crucible list-runs
uv run crucible show-run --run latest
uv run crucible report --run latest --format html
uv run crucible diff --run latest --from 0 --to best
```

Relatórios são escritos em `.crucible/reports/`.

Use `diff` para entender o que mudou entre o prompt inicial e o melhor prompt. Use
`report` ou o dashboard para ver quais casos continuaram falhando e quais viraram
regressão.

## Abrir Dashboard

```bash
uv run crucible serve
```

Abra:

```text
http://127.0.0.1:7777
```

## Exportar Artefatos

```bash
uv run crucible export --run latest --format prompt --output ./best_prompt.txt
uv run crucible export --run latest --format csv --output ./verdicts.csv
uv run crucible export --run latest --format parquet --output ./verdicts.parquet
uv run crucible report --run latest --format pdf
```

## Saída Estruturada

Quando o modelo deve responder em JSON seguindo um schema, use o exemplo em
`examples/structured-output/`.

OpenAI Responses API:

```bash
uv run crucible validate \
  --prompt ./examples/structured-output/prompt.txt \
  --gabarito ./examples/structured-output/gabarito.yaml \
  --config ./examples/structured-output/config.openai-responses.yaml
```

Ollama:

```bash
uv run crucible validate \
  --prompt ./examples/structured-output/prompt.txt \
  --gabarito ./examples/structured-output/gabarito.yaml \
  --config ./examples/structured-output/config.ollama.yaml
```

Esse exemplo usa duas camadas: `target_model.output_format` solicita o JSON Schema ao
provider, e a assertion `json_schema` mede se a resposta cumpriu o contrato.

## Workflow Recomendado

1. Escreva ou importe um gabarito.
2. Rode `validate` até setup, providers e assertions estarem corretos.
3. Rode `estimate-cost`.
4. Rode `optimize`.
5. Inspecione falhas e regressões no dashboard.
6. Exporte o melhor prompt e os verdicts.
7. Versione prompt/gabarito/config, mas não versiona `.crucible/`.
