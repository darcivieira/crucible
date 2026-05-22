# Arquitetura

Crucible usa uma arquitetura em camadas pragmática, inspirada no projeto `oneai`.

```text
src/crucible/
  core/
  modules/
    optimizer/
      domain/
      application/
      adapters/
      presentation/
      plugins/
```

## Direção Das Dependências

```text
presentation -> application -> domain
adapters     -> domain
application  -> adapters apenas para wiring padrão
```

O domínio não conhece:

- HTTP;
- SQLite;
- CLI;
- FastAPI;
- filesystem.

## Domain

Arquivos:

- `domain/models.py`
- `domain/assertions.py`
- `domain/scoring.py`
- `domain/protocols.py`

Responsabilidades:

- modelos Pydantic;
- assertions;
- agregação de score;
- protocolos de provider/cache/store.

## Application

Arquivos:

- `application/optimizer.py`
- `application/estimates.py`
- `application/reports.py`
- `application/exports.py`
- `application/execution_backends.py`

Responsabilidades:

- loop de otimização;
- prompts internos de diagnóstico/refinamento;
- estimativa de custo;
- geração de reports/exports;
- seleção de backend de execução.

## Adapters

Arquivos:

- `adapters/providers/*`
- `adapters/storage.py`
- `adapters/cache.py`
- `adapters/importers.py`

Responsabilidades:

- payloads e parsing de providers;
- rate limiting;
- SQLite e storage em arquivos;
- cache;
- conversão de formatos externos.

## Presentation

Arquivos:

- `presentation/cli/app.py`
- `presentation/web/app.py`
- `presentation/api/app.py`

Responsabilidades:

- parsear input do usuário;
- chamar serviços de aplicação;
- renderizar terminal, HTML ou JSON.

Regra de otimização não deve morar nessa camada.

## Plugins

Arquivo:

- `plugins/registry.py`

Plugins registram handlers em um registry local do processo.

## Fluxo De Otimização

1. `Optimizer.optimize(prompt, gabarito)`.
2. Opcionalmente divide gabarito em train/val/test.
3. Executa iteração `v0`.
4. Agrega score.
5. Para se atingir threshold/budget/tempo/plateau/sem falhas.
6. Seleciona falhas.
7. Diagnostica com o reasoning model.
8. Refina prompt com o reasoning model.
9. Repete.
10. Persiste iterações e run final.

## Fluxo De Storage

Store padrão:

```python
CompositeRunStore(
    SQLiteRunStore(".crucible/crucible.sqlite"),
    FileRunStore(".crucible/runs"),
)
```

SQLite alimenta consultas de CLI/API/dashboard. Arquivos ficam para inspeção humana
e debugging.

## Fluxo Da API

`POST /runs`:

1. valida request como modelos Pydantic;
2. cria `task_id`;
3. agenda `Optimizer.optimize(...)` em background task do FastAPI;
4. persiste a run em SQLite.

Task state e estado de run concluída são persistidos no SQLite.
