# Documentação Crucible

Crucible é um framework local-first para otimizar prompts empiricamente contra
gabaritos versionados.

Use este índice conforme o que você precisa fazer.

## Primeiros Passos

- [Quickstart](quickstart.md): crie um projeto, rode uma otimização e inspecione os
  resultados.
- [Tutorial end-to-end](tutorials/customer-support-end-to-end.md): fluxo completo de
  triagem de suporte, report e exports.
- [Conceitos](concepts.md): entenda prompt, gabarito, test case, assertion e run.
- [Referência CLI](cli.md): comandos e flags disponíveis.
- [Configuração](configuration.md): referência completa do `config.yaml`.

## Guias Por Cenário

- [Prompt simples](guides/simple-prompt.md): avaliação e otimização de texto livre.
- [Saída JSON estruturada](guides/structured-json.md): `output_format` mais
  assertions estruturais.
- [LLM-as-judge](guides/llm-as-judge.md): avaliação subjetiva com rubrica.
- [Train/val/test](guides/train-val-test.md): reduzir overfitting ao gabarito.
- [Comparação de modelos](guides/model-comparison.md): escolher target por score,
  custo e custo-benefício.
- [Cache do provider](guides/provider-cache.md): reduzir custo com contexto cacheado.
- [Uso em CI](guides/ci.md): validação de regressões em pull requests.
- [Uso via SDK](guides/sdk.md): integração Python programática.
- [Plugins](guides/plugins.md): assertions e importadores de domínio.

## Autores De Avaliação

- [Gabaritos e Assertions](gabaritos-and-assertions.md): escreva casos de teste
  robustos.
- [Scoring](scoring.md): entenda score global, pesos, breakdowns e métricas
  operacionais.
- [Providers](providers.md): configure Ollama, OpenAI, Anthropic, Google, OpenRouter,
  vLLM e llama.cpp.
- [Importadores e Exports](importers-and-exports.md): mova dados para dentro e fora
  do Crucible.

## Python, API E Produto

- [SDK Python](sdk.md): use Crucible programaticamente.
- [REST API](api.md): crie runs e consulte histórico via HTTP.
- [Dashboard](dashboard.md): inspecione runs, verdicts, diffs e regressões.
- [Docker](docker.md): rode dashboard/API/CLI em container e publique imagem.
- [Operação](operations.md): estado local, custos, segredos, CI e limpeza.
- [Release](release.md): checks, smoke tests e artefatos para publicação open source.
- [UX e Interfaces](interfaces.md): visão prática das superfícies CLI, SDK, API,
  dashboard, reports e exports.

## Extensibilidade E Contribuição

- [Plugins](plugins.md): assertions e importadores customizados.
- [Arquitetura e Implementação](architecture.md): organização do código e fluxo.
- [Decisões Técnicas](technical-decisions.md): concorrência, cache, variância,
  budgets, persistência e limites atuais.
- [Desenvolvimento](development.md): testes, lint, tipagem e workflow.
- [Extensão VSCode](../vscode-extension/): scaffold da extensão do editor.

## Mapeamento Da Especificação Original

- Item 2, Conceitos Centrais: [Conceitos](concepts.md).
- Item 4, Sistema de Scoring: [Scoring](scoring.md) e
  [Gabaritos e Assertions](gabaritos-and-assertions.md).
- Item 5, Arquitetura: [Arquitetura e Implementação](architecture.md).
- Item 8, Decisões Técnicas: [Decisões Técnicas](technical-decisions.md).
- Item 9, UX e Interfaces: [UX e Interfaces](interfaces.md).

## Exemplos

- [Projeto básico local](../examples/basic/)
- [Saída estruturada com JSON Schema](../examples/structured-output/): contrato,
  payload esperado e comparação campo a campo.
- [Triagem de suporte](../examples/customer-support-triage/)
- [LLM-as-judge para risco](../examples/llm-judge-risk/)
- [Train/val/test](../examples/train-val-test/)
- [Comparação de modelos](../examples/model-comparison/)

## Comunidade

- [Contributing](../CONTRIBUTING.md)
- [Code of Conduct](../CODE_OF_CONDUCT.md)
- [Security](../SECURITY.md)
