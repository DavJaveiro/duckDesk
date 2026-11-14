# ADR-0010: Bico articulado por pose cinemática (sem junta nova)

**Status:** aceita (2026-11-14, pós-M7)

## Contexto

O MicroDuck real tem **15 servos**: 14 nas políticas + a boca (`duck-control model.rs`:
`MOUTH_INDEX = 9`, Dynamixel id 34), dirigida pelo daemon fora de qualquer rede — abertura
0..1 via `robot.mouth`, usada nos grasnos ("quack bursts — one to four chirps, **with the
mouth and a head toss**", `autonomous.md`), nas olhadas ("the beak opens a touch") e no
bocejo (`robotd/idle_head.rs`). No MJCF empacotado (`robot_groundcontact.xml`) a mandíbula é
**geometria rígida**: `jaw`, `jaw_soft` e `soft_mouth_top` são geoms fixos dentro do corpo
`jaw_soft` — a jaw linkage do modelo novo ficou de fora. O dono pediu o movimento do bico do
projeto original.

## Decisão

**Pose cinemática das geoms do bico** (`SimCore.set_beak(0..1)`): `geom_pos`/`geom_quat` e
`site_pos`/`site_quat` são campos de modelo editáveis em tempo de execução — a regra 3
permite exatamente isso (mudar o modelo em runtime, nunca o arquivo). O conjunto `jaw`
(visual+collision) + `jaw_soft` + o site `mouth_tip` gira em torno de uma dobradiça na
traseira-superior do AABB da mandíbula, eixo lateral +y do `jaw_soft` (sinal positivo abre,
máx. 0,30 rad — pivô e sinal medidos por sonda e conferidos em render). O servo real também
só segura uma posição comandada, então cinemático é **mais** fiel que uma junta solta.

Sem junta nova: `nq`/`nv`/`nu` e a observação de 61 D ficam byte a byte iguais — o teste de
paridade nem percebe. `reset()` devolve o bico a fechado.

**`brain/beak.py` (`BeakAnimator`)** produz `mouth` (0..1) e `head` (offset de head_pitch),
espelhando o upstream com as fontes citadas em comentário:

- **Grasno**: lip-sync — a abertura segue a envolvente RMS de `quack.mp3` em quadros de
  40 ms (`QUACK_ENV`), como o coro que mapeia vogal → boca (`robotd/main.rs`); mais o sacode
  de cabeça leve (`head_pitch` negativo) do `autonomous.md`.
- **Olhada**: abre "um tiquinho" por olhada — `glance_mouth 0,4 × rng(0,5, 1)`
  (`idle_head.rs`), acompanhando o progresso da olhada do `IDLE`.
- **Bocejo**: após ~45 s de quietude (`IDLE`/`SIT`; clique/arrasto/movimento zeram o
  relógio — "any motion wakes it"), uma moeda por tick dá um bocejo a cada ~90 s: curva
  `yawn_shape` (abre em 40 %, sustenta 30 %, fecha em 30 %), `yawn_open = 0,6`,
  `yawn_pitch = -0,15` — parâmetros verbatim de `robotd-params`.
- **Composição** por máximo (`robotd/main.rs`: `mouth = max(intent, idle)`): o grasno vence;
  senão olhada + bocejo somam, limitado a 1.

O toss/bocejo chega à cabeça **pela política** (slot head_pose do comando 13 D), somado em
`_send` — nada de pose extra-fora.

## Alternativas descartadas

- **Junta passiva via MjSpec** (`passive_beak` + reparentar geoms): funciona, mas adiciona
  um DOF que a física integra (precisa de mola/amortecimento ou reescrita de qpos a cada
  passo) e muda `nq`/`nv` — risco de paridade sem ganho visual.
- **Atuador MuJoCo na junta**: `nu` viraria 15 e quebraria o contrato 14-ações — fora.
- **Editar o XML/malhas**: proibido pela regra 3.
- **Só o grasno, sem olhada/bocejo**: o dono pediu ambos os comportamentos do original.

## Consequências

- O duplo clique agora toca o MP3 **e** o bico trabalha no ritmo do som (05 §6).
- Depois de ~45 s parado o pato boceja sozinho — Easter egg de "cochilando", raro e fiel.
- `set_beak` escreve `geom_pos` a cada tick de controle — custo desprezível (4 transformações
  + um `mj_forward` só quando o ângulo muda).
- Na traseira do bico abre-se uma fresta pequena ao máximo (a dobradiça é idealizada) —
  invisível no tamanho do mascote.
- Testes: `tests/unit/test_beak.py` (envolventes, composição, olhada, bocejo, pose e restauração).
