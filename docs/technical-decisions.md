# Decisões Técnicas

Este documento registra as principais decisões de implementação do Crucible e o
estado atual de cada uma.

## Asyncio Como Base

O pipeline é async-first:

- providers expõem `complete(...)` assíncrono;
- o optimizer executa casos em paralelo;
- CLI chama o fluxo async com `asyncio.run`;
- API e dashboard rodam em FastAPI.

Isso mantém o core simples e funciona tanto para providers locais quanto cloud.

## Rate Limit Por Provider

Cada `ModelSpec` declara limites:

```yaml
rate_limit:
  max_concurrent: 4
  requests_per_minute: 60
  retry_attempts: 2
  retry_backoff_seconds: 0.5
```

`RateLimitedProvider` aplica concorrência e requests por minuto ao redor do provider
real. Para GPU local, use `max_concurrent: 1`; para cloud, aumente conforme o limite
da conta.

## Retry Em Erros Transitórios

Providers HTTP fazem retry em respostas transitórias:

- `429`
- `500`
- `502`
- `503`
- `504`

O backoff é exponencial:

```text
retry_backoff_seconds * 2 ** attempt
```

Erros finais sobem como `ProviderError`.

## Cache Local

O cache evita pagar novamente por execuções idênticas. A chave considera:

- hash do prompt;
- input do caso;
- provider/modelo;
- hash dos parâmetros do modelo.

O adapter atual usa JSONL em `.crucible/cache/`, coerente com o modelo local-first.

## SQLite Como Índice Persistente

SQLite é o default porque:

- não exige serviço externo;
- funciona bem com CLI e SDK local;
- alimenta dashboard/API sem parsing de arquivos;
- preserva histórico de runs para comparação.

Arquivos em `.crucible/runs/` continuam existindo para inspeção e debugging. Postgres
é uma evolução possível atrás do mesmo contrato de store.

## Reports Estáticos

HTML, JSON e PDF são artefatos gerados a partir da run persistida. Isso permite:

- compartilhar resultado sem subir dashboard;
- anexar reports em CI;
- arquivar snapshots de decisão.

Reports podem conter dados sensíveis; trate como artefato privado quando o gabarito
contiver dados reais.

## Variância E Determinismo

Mesmo com `temperature: 0.0`, modelos locais quantizados ou providers remotos podem
variar. O Crucible oferece:

- `seed` em `ModelParams`, quando o provider suporta;
- `n_runs_per_case` para repetição;
- flag de instabilidade em detalhes da assertion;
- train/val/test para reduzir overfitting.

## Budget Enforcement

O optimizer para por:

- `threshold_reached`;
- `max_iterations`;
- `budget_exhausted`;
- `time_exhausted`;
- `plateau`;
- `no_failures`.

`max_cost_usd`, `max_iterations` e `max_wallclock_seconds` devem ser configurados em
toda run real.

## Backend De Execução

Backends disponíveis:

- `local`: `asyncio.gather` direto.
- `distributed`: pool assíncrono local limitado por `distributed_workers`.
- `ray`: executor opcional via Ray.
- `dask`: executor opcional via Dask Distributed.

Ray/Dask rodam atrás do mesmo contrato de `ExecutionBackend`. Como jobs Python
precisam ser serializáveis para esses executores, workloads com providers customizados
devem ser testados antes de uso pesado.

## Limites Atuais

- Não há migração formal de schema SQLite.
- API não tem autenticação.
- Dashboard é server-side simples, sem frontend SPA.
- Observability estruturada existe via logs; OpenTelemetry ainda não foi implementado.
