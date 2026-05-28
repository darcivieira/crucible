# Quickstart

Este guia leva você de um diretório vazio até uma run otimizada e visível no
dashboard local.

Se você está chegando agora e quer uma explicação mais guiada, leia também o
[Guia do usuário](user-guide.md).

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

## Comparar Modelos

Se você ainda está escolhendo o modelo alvo, configure `comparison_models` e rode:

```bash
uv run crucible compare-models --config ./my-prompt/config.yaml
```

Esse comando executa o mesmo prompt contra o mesmo gabarito, uma vez por modelo
candidato. Ele não otimiza prompt. O objetivo é decidir o melhor target por score,
custo e custo-benefício antes de iniciar uma run mais cara de `optimize`.

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

Na tela inicial você pode abrir `Nova run` para executar pelo navegador.

Use `Validate` quando quiser medir rapidamente o prompt atual. Use `Optimize` quando
quiser que o Crucible proponha versões melhores. Use `Compare` quando quiser avaliar
os modelos de `comparison_models`. A tela aceita caminhos locais para `prompt.txt`,
`gabarito.yaml` e `config.yaml`, ou conteúdo colado nos editores.

Também é possível escolher host e porta:

```bash
uv run crucible serve --host 0.0.0.0 --port 7777
```

Use `0.0.0.0` apenas em rede confiável. O dashboard não tem autenticação.

## Usar API Local

Se você quer integrar o Crucible com outro sistema, suba a API:

```bash
uv run crucible api --port 7788
```

Teste com `curl`:

```bash
curl -s http://127.0.0.1:7788/runs
```

Veja exemplos completos em [REST API](api.md).

## Exportar Artefatos

```bash
uv run crucible export --run latest --format prompt --output ./best_prompt.txt
uv run crucible export --run latest --format csv --output ./verdicts.csv
uv run crucible export --run latest --format parquet --output ./verdicts.parquet
uv run crucible report --run latest --format pdf
```

## Saída Estruturada

Quando o modelo deve responder em JSON seguindo um schema, use o exemplo em
`examples/structured-output/`. O exemplo padrão cobre o caso em que o gabarito traz
o payload esperado em `expected_output`, enquanto o schema fica no `config.yaml`.

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

Esse exemplo usa três camadas:

- `target_model.output_format`: solicita o JSON Schema ao provider.
- `expected_output`: guarda o payload esperado para aquele caso.
- `assertion.type: json_schema`: valida expected/actual contra o schema do config e
  compara os campos parseados.

Quando você quer validar apenas o contrato estrutural, sem comparar valores
esperados, use:

```bash
uv run crucible validate \
  --prompt ./examples/structured-output/prompt.txt \
  --gabarito ./examples/structured-output/gabarito.schema.yaml \
  --config ./examples/structured-output/config.openai-responses.yaml
```

Quando você está escrevendo o gabarito manualmente e quer deixar a intenção explícita,
use `field_by_field`:

```bash
uv run crucible validate \
  --prompt ./examples/structured-output/prompt.txt \
  --gabarito ./examples/structured-output/gabarito.field-by-field.yaml \
  --config ./examples/structured-output/config.openai-responses.yaml
```

## Workflow Recomendado

1. Escreva ou importe um gabarito.
2. Rode `validate` até setup, providers e assertions estarem corretos.
3. Rode `estimate-cost`.
4. Se houver dúvida sobre o target, rode `compare-models`.
5. Rode `optimize`.
6. Inspecione falhas e regressões no dashboard.
7. Exporte o melhor prompt e os verdicts.
8. Versione prompt/gabarito/config, mas não versiona `.crucible/`.
