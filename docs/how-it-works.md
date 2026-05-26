# Funcionamento

Este documento foi mantido como atalho para links antigos.

O funcionamento do Crucible agora está documentado em:

- [Conceitos](concepts.md)
- [Gabaritos e Assertions](gabaritos-and-assertions.md)
- [Arquitetura e Implementação](architecture.md)
- [Operação](operations.md)

O resumo prático: Crucible executa o prompt contra um gabarito, calcula score,
diagnostica falhas com um modelo de raciocínio, refina o prompt e preserva o melhor
prompt visto durante a run.

Antes do refino, o Crucible constrói um contrato da tarefa com base no prompt inicial,
no `config.yaml` e no gabarito. Esse contrato preserva regras críticas, como formato
de saída, campos JSON, extração literal, restrições de "não inventar" e padrões
observados nos expected outputs.

Se uma proposta de prompt violar esse contrato, ela é rejeitada antes de chamar o
`target_model` novamente. O Crucible então pede ao `reasoning_model` que refaça a
proposta usando os motivos concretos da rejeição. Esse reparo acontece dentro da
mesma iteração, então não há uma nova execução com prompt idêntico.

Depois de `max_refinement_repair_attempts` tentativas sem um prompt válido, a run
encerra com `stop_reason: reasoning_failed_to_refine`. Isso evita loops em que o
reasoning degrada o prompt ou insiste em remover regras críticas, como extração
literal, `{input}` ou "não inventar".
