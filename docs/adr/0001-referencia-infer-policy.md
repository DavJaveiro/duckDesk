# ADR-0001: A referência de comportamento é o `infer_policy.py`

**Status:** aceita (2026-11-14)

## Contexto

Existem duas implementações oficiais que ligam as políticas a um corpo:

1. `microduck_rl/scripts/infer_policy.py`: ensaio em MuJoCo na CPU, com o mesmo atuador BAM do
   treino, escala de ação 1.0 e sem filtro.
2. `microduck/robotd/src/control.rs`: o daemon do robô real. Aplica ajustes para o hardware:
   escala de ação 0.9, passa-baixa (cabeça 0.5, pernas 0.7), ganho de 80 % em pé e comando
   suavizado.

O AGENTS.md do `microduck_rl` diz que as políticas são treinadas **sem filtro** e que o
`infer_policy.py` é o ensaio de implantação. O comentário do `robotd` diz que os filtros
"must match training" para as políticas *alpha*, que são mais antigas.

## Decisão

- Física, observação, ação e atuador: **iguais ao `infer_policy.py`** (escala 1.0, sem filtro).
  Nossa física é a do treino, então os ajustes que compensam o hardware real não se aplicam.
- Orquestração dos comportamentos (subida do `sitstand` de 1.0 s, "um movimento por vez",
  "nada a partir do assento", durações do manifesto): **igual ao `robotd`**, porque o
  `infer_policy.py` não cobre esses casos (fica preso no `sitstand` ao usar só a velstand).

## Consequências

- O teste de paridade compara com o `infer_policy.py`.
- **Investigação opcional no M1** (não muda o padrão): rodar o ensaio headless da velstand também
  com a configuração do `robotd` (escala 0.9 e filtros) e relatar se o andar fica mais ou menos
  estável. Se ficar claramente melhor, abrimos uma ADR nova.
