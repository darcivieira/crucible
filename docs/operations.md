# Operação

## Estado Local

Crucible escreve em `.crucible/` por padrão:

```text
.crucible/
  crucible.sqlite
  cache/
  reports/
  runs/
```

Não versione `.crucible/`, exceto se a intenção for versionar artefatos de run.

## Limpeza

Limpeza manual:

```bash
rm -rf .crucible/cache
rm -rf .crucible/reports
```

Remova `.crucible/crucible.sqlite` apenas se quiser apagar o histórico indexado de
runs.

## Segredos

Use variáveis de ambiente:

```bash
export CRUCIBLE_OPENAI_API_KEY=...
export CRUCIBLE_ANTHROPIC_API_KEY=...
export CRUCIBLE_GOOGLE_API_KEY=...
export CRUCIBLE_OPENROUTER_API_KEY=...
```

Evite guardar API keys em `config.yaml`.

## Controle De Custo

Configure sempre:

```yaml
max_cost_usd: 5.0
max_iterations: 5
max_wallclock_seconds: 1800
```

Rode:

```bash
uv run crucible estimate-cost --config config.yaml
```

antes de runs caras.

## Rate Limits

Para providers em GPU local:

```yaml
rate_limit:
  max_concurrent: 1
```

Para providers cloud:

```yaml
rate_limit:
  max_concurrent: 4
  requests_per_minute: 60
  retry_attempts: 2
  retry_backoff_seconds: 0.5
```

## Uso Em CI

Fluxo típico:

```bash
uv sync
uv run crucible validate --prompt prompt.txt --gabarito gabarito.yaml --config config.yaml
uv run crucible report --run latest --format html
```

Guarde `.crucible/reports/*.html` como artefato de CI.

Em CI, prefira assertions determinísticas e seeds fixas quando o provider suportar.

## Segurança

Reports podem conter:

- prompts;
- inputs de usuário;
- expected outputs;
- outputs de modelo;
- racionales de judges.

Não publique reports se gabaritos tiverem dados sensíveis.

## Exposição De API/Dashboard

`crucible serve` e `crucible api` são local-first. Eles não implementam auth.

Mantenha o bind em `127.0.0.1` salvo em rede confiável:

```bash
uv run crucible serve --host 127.0.0.1
uv run crucible api --host 127.0.0.1
```

## Troubleshooting

Provider não conecta:

- verifique API keys;
- verifique URL do servidor local;
- rode `validate` antes de `optimize`;
- reduza `rate_limit.max_concurrent`.

Scores instáveis:

- configure `n_runs_per_case: 3`;
- confira `assertion_detail["runs"]["unstable"]`;
- reduza temperatura;
- configure seed quando suportado.

Overfitting:

- habilite `use_gabarito_split`;
- inspecione `validation_scores`;
- adicione casos mais diversos;
- não copie exemplos de teste para o prompt.
