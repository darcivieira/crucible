# Guia Do Usuário

Este guia explica o Crucible do ponto de vista de quem quer melhorar ou comparar
prompts, sem precisar conhecer a arquitetura interna do projeto.

## Para Que Serve

O Crucible ajuda você a responder perguntas práticas:

- meu prompt está entregando a resposta esperada?
- qual modelo responde melhor para meu caso?
- vale a pena trocar de modelo por custo ou qualidade?
- o prompt melhorou de uma versão para outra?
- quais exemplos ainda falham?
- qual foi o melhor prompt encontrado?

Ele faz isso executando um prompt contra um conjunto de exemplos esperados, chamado
`gabarito`.

## Os Três Arquivos Principais

Um projeto Crucible normalmente tem:

```text
my-prompt/
  prompt.txt
  gabarito.yaml
  config.yaml
```

`prompt.txt` é a instrução enviada ao modelo. Use `{input}` onde o texto de cada caso
deve entrar:

```text
Classifique o texto abaixo.

Texto:
{input}
```

`gabarito.yaml` contém os casos de teste. Cada caso tem um input, uma resposta
esperada e uma regra de comparação:

```yaml
name: exemplo
version: v1
cases:
  - id: caso-001
    input: "Intime-se a parte para manifestação no prazo de 5 dias."
    expected_output: |
      {"classification": "Prazo", "text_validation": "prazo de 5 dias"}
    assertion:
      type: field_by_field
      weights:
        classification: 95
        text_validation: 5
      field_assertions:
        classification:
          type: exact
        text_validation:
          type: contains
```

`config.yaml` diz quais modelos serão usados e quais limites a execução deve
respeitar:

```yaml
threshold: 95.0
max_iterations: 3
max_cost_usd: 2.0

target_model:
  provider: ollama
  model_id: gemma3:4b
  role: target

reasoning_model:
  provider: openai
  model_id: gpt-5
  role: reasoning
```

## Fluxo Recomendado

1. Escreva um gabarito pequeno com exemplos representativos.
2. Rode `validate` para saber se o prompt atual funciona.
3. Se estiver escolhendo modelo, rode `compare-models`.
4. Rode `optimize` para tentar melhorar o prompt automaticamente.
5. Abra o dashboard para entender falhas, diffs e melhor prompt.
6. Exporte o melhor prompt e os verdicts.

## Usando Pelo CLI

Crie um projeto:

```bash
uv run crucible init ./my-prompt
```

Valide o prompt atual:

```bash
uv run crucible validate \
  --prompt ./my-prompt/prompt.txt \
  --gabarito ./my-prompt/gabarito.yaml \
  --config ./my-prompt/config.yaml
```

Compare modelos candidatos:

```bash
uv run crucible compare-models \
  --prompt ./examples/model-comparison/prompt.txt \
  --gabarito ./examples/model-comparison/gabarito.yaml \
  --config ./examples/model-comparison/config.yaml
```

Otimize o prompt:

```bash
uv run crucible optimize --config ./my-prompt/config.yaml
```

Gere relatório:

```bash
uv run crucible report --run latest --format html
```

Exporte o melhor prompt:

```bash
uv run crucible export --run latest --format prompt --output ./best_prompt.txt
```

## Usando Pelo Dashboard

Suba o servidor local:

```bash
uv run crucible serve
```

Abra no navegador:

```text
http://127.0.0.1:7777
```

Na tela `Nova run`, escolha:

- `Validate`: para medir o prompt atual.
- `Optimize`: para pedir ao Crucible que tente melhorar o prompt.
- `Compare`: para comparar os modelos de `comparison_models`.

Você pode informar caminhos locais para `prompt.txt`, `gabarito.yaml` e
`config.yaml`, ou colar o conteúdo diretamente nos editores da tela.

## Usando Pela API Com Curl

Suba a API:

```bash
uv run crucible api --port 7788
```

Crie uma run de validação:

```bash
curl -s -X POST http://127.0.0.1:7788/runs \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "validate",
    "prompt": {"template": "Responda apenas: {input}", "variables": ["input"]},
    "gabarito": {
      "name": "smoke",
      "version": "v1",
      "cases": [
        {
          "id": "case-001",
          "input": "ok",
          "expected_output": "ok",
          "assertion": {"type": "contains"}
        }
      ]
    },
    "config": {
      "target_model": {"provider": "fake", "model_id": "target", "role": "target"},
      "reasoning_model": {"provider": "fake", "model_id": "reasoning", "role": "reasoning"}
    }
  }'
```

A resposta traz um `task_id`. Consulte o status:

```bash
curl -s http://127.0.0.1:7788/tasks/<task-id>
```

Quando a task terminar, use o `run_id` retornado para ver a run:

```bash
curl -s http://127.0.0.1:7788/runs/<run-id>
```

## Usando Pelo SDK Python

Crie um arquivo `run_crucible.py`:

```python
import asyncio

from crucible import Gabarito, OptimizationConfig, Optimizer, Prompt


async def main():
    config = OptimizationConfig.model_validate({
        "target_model": {"provider": "fake", "model_id": "target", "role": "target"},
        "reasoning_model": {"provider": "fake", "model_id": "reasoning", "role": "reasoning"},
    })
    prompt = Prompt(template="Responda apenas: {input}", variables=["input"])
    gabarito = Gabarito.model_validate({
        "name": "smoke",
        "version": "v1",
        "cases": [
            {
                "id": "case-001",
                "input": "ok",
                "expected_output": "ok",
                "assertion": {"type": "contains"},
            }
        ],
    })

    optimizer = Optimizer(config)
    iteration = await optimizer.validate(prompt, gabarito)
    print(iteration.score)


asyncio.run(main())
```

Execute:

```bash
uv run python run_crucible.py
```

## Entendendo O Score

O score vai de `0` a `100`.

Em respostas estruturadas, use `field_by_field` para pontuar campo a campo. Exemplo:

```yaml
assertion:
  type: field_by_field
  weights:
    classification: 95
    text_validation: 5
  field_assertions:
    classification:
      type: exact
    text_validation:
      type: contains
```

Nesse exemplo, `classification` vale 95% do caso e deve bater exatamente.
`text_validation` vale 5% e aceita quando o trecho esperado aparece na resposta ou a
resposta aparece no trecho esperado.

## Onde Ficam Os Resultados

O Crucible grava estado local em `.crucible/`:

```text
.crucible/
  crucible.sqlite
  runs/
  reports/
  cache/
```

Isso permite abrir histórico, comparar runs, gerar relatórios e recuperar o melhor
prompt depois.

## Próximos Passos

- Para configurar modelos: [Providers](providers.md).
- Para escrever gabaritos melhores: [Gabaritos e Assertions](gabaritos-and-assertions.md).
- Para comparar modelos: [Comparação de modelos](guides/model-comparison.md).
- Para usar API em integração: [REST API](api.md).
- Para usar em Python: [SDK Python](sdk.md).
