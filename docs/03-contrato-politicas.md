# 03: Contrato com as políticas (redes neurais)

Este é o documento mais importante do projeto. Se qualquer item abaixo for diferente do que foi
usado no treino, o pato cai, treme ou anda de lado. A fonte da verdade é
`microduck_rl/scripts/infer_policy.py` no commit `0daab160d3fb1c2cbaba16a4a19052f36709dd9e`
(abaixo, "upstream"). Os números de linha se referem a esse commit.

## 1. Modelo físico

| Item | Valor | Origem |
|---|---|---|
| Cena do simulador | `scene_ball.xml` (robô `robot_groundcontact.xml` + bola de 70 mm) | upstream L27, L1269 |
| Cena do mascote | A **mesma** `scene_ball.xml`, com a bola estacionada longe (veja 05) | decisão ADR-0002 |
| Passo da física | `model.opt.timestep = 0.005` (200 Hz) | L1281 e L1285 |
| Decimação | 4 passos de física por passo de controle → **50 Hz** | L1432 |
| Corpo do tronco | `trunk_base`, junta livre `trunk_base_freejoint` | L365, L369 |
| Sensor de giro | `imu_ang_vel` | L364 |

A ADR-0002 registra por que usamos uma cena só nos dois modos: um único `MjModel`, sem recarregar
nada ao trocar de modo.

## 2. Atuador BAM (obrigatório)

As políticas foram treinadas com o modelo BAM M6 do servo Dynamixel XL330 (controle por tensão,
força contraeletromotriz e atrito dependente de carga). Usar os atuadores de posição do próprio
XML (`--no-bam` no upstream) **não** é o que a rede viu no treino. Porte exatamente:

- `load_bam_model` (L49–56): `motor_name="xl330"`, `model="m6"`, `kp = 200.0`, `vin = 7.4`,
  `max_current = None`.
- `load_mujoco_with_bam` (L59–105), sem mudar nada:
  - converte cada atuador não `passive_` em motor de torque com `forcerange = ±vin·kt/R`;
  - zera o amortecimento e a `frictionloss` das juntas;
  - aplica `solref_friction = (-5.0e4, -2.0e2)` e
    `solimp_friction = (0.99, 0.9999, 0.001, 0.5, 2.0)`;
  - cria um `bam.mujoco.MujocoController(..., vin_drop_gain=0.1, vin_min=6.0)`.
- A cada passo de física: `bam_ctrl.update()` e depois `mujoco.mj_step(model, data)` (L1770–1777).
- O alvo dos motores vai em `bam_ctrl.q_target[:]`, nunca em `data.ctrl` (L885–894).
- No reset: `bam_ctrl.reset(data.qpos)` (L1385).

Pacote: `better-actuator-models` (importado como `bam`), do Git
`https://github.com/Rhoban/bam.git` no commit `57d13ead53206a6bf0db3d66f86506ae8c2ce01a` (branch
`mjlab_frictionloss`), com o extra `[mujoco]`. As dependências são só `numpy`, `colorama` e
`mujoco`. **Não** instale o extra `[mjlab]`.

## 3. Pose padrão (`DEFAULT_POSE`)

Ordem das 14 juntas (índice do controle = índice da junta neste modelo):

| idx | junta | valor (rad) |
|---|---|---|
| 0 | left_hip_yaw | 0.0 |
| 1 | left_hip_roll | -0.0873 |
| 2 | left_hip_pitch | -0.4579 |
| 3 | left_knee | -0.0049 |
| 4 | left_ankle | 0.4530 |
| 5 | neck_pitch | 0.3491 |
| 6 | head_pitch | 0.3491 |
| 7 | head_yaw | 0.0 |
| 8 | head_roll | 0.0 |
| 9 | right_hip_yaw | 0.0 |
| 10 | right_hip_roll | 0.0873 |
| 11 | right_hip_pitch | 0.4579 |
| 12 | right_knee | 0.0049 |
| 13 | right_ankle | -0.4530 |

Copie o array de L126–141 **literalmente** (float32). Não use a keyframe `STAND` da cena: os
valores têm mais casas decimais e o teste de paridade vai pegar a diferença.

Os índices de `qpos` e `qvel` das juntas atuadas **devem** ser calculados pela transmissão dos
atuadores (`model.actuator_trnid`), como em L390–395. Nunca fixe os índices no código.

## 4. Observação: vetor de 61 floats, nesta ordem

| Faixa | Tam. | Conteúdo | Origem |
|---|---|---|---|
| 0–2 | 3 | Velocidade angular do tronco, do sensor `imu_ang_vel` | L642–645 |
| 3–5 | 3 | **Gravidade projetada** no referencial do tronco: `quat_rotate_inverse(xquat[trunk_base], [0,0,-1])` | L636–640 |
| 6–19 | 14 | Posição das juntas **menos** `DEFAULT_POSE` | L647–650 |
| 20–33 | 14 | Velocidade das juntas | L652–654 |
| 34–47 | 14 | Última ação **crua** que a rede devolveu (antes da escala) | L863 |
| 48–60 | 13 | Comando: `[vx, vy, wz, neck_pitch, head_pitch, head_yaw, head_roll, body_x, body_y, body_z, body_roll, body_pitch, body_yaw]` | L461–495 |

- Use a gravidade projetada, **não** o acelerômetro bruto. No upstream,
  `use_projected_gravity = not args.raw_accelerometer`, que é `True` por padrão (L1333).
- `quat_rotate_inverse` deve ser exatamente a de L612–617, com quaternion `[w, x, y, z]`.
- Tudo em `float32`, formato `[1, 61]`. A normalização das observações já vem **embutida no
  ONNX**. Não normalize nada.
- `last_action` começa em zeros e é atualizada a cada inferência, **também** quando a política
  ativa muda: o upstream não zera `last_action` na troca. Faça igual.

## 5. Ação

- A rede devolve `[1, 14]`. Alvo dos motores: `DEFAULT_POSE + action * action_scale`.
- `action_scale = 1.0` para todas as políticas da v1 (o manifesto só define outro valor para as
  de patins, que estão fora do escopo). Leia `action_scale` do manifesto mesmo assim.
- **Sem filtro** de suavização. As políticas foram treinadas sem filtro (AGENTS.md do upstream).
- Sem atraso artificial (`delay` desligado), que é o padrão do upstream.

## 6. Laço de controle (uma iteração a 50 Hz)

```
advance_timers(0.02)                       # fase do ground_pick, timers dos comportamentos (L1679–1680)
obs    = build_obs()                       # 61 floats, com o comando atual
action = session.run(obs)                  # [14]
last_action = action
bam_ctrl.q_target[:] = DEFAULT_POSE + action * scale
repeat 4:
    bam_ctrl.update()
    mujoco.mj_step(model, data)
```

Repare na ordem: os timers avançam **antes** da inferência, e a observação é lida **antes** dos 4
passos de física, com o estado resultante do passo anterior. É isso que o upstream faz
(L1662–1777).

**Diferença intencional:** o upstream avança os timers pelo tempo de relógio medido
(`actual_dt`). Nós usamos o tempo **simulado**, sempre exatamente 0.02 s por passo, para o
resultado ser determinístico e independente da carga do PC. O teste de paridade chama os métodos
do upstream com `dt = 0.02` explícito, sem rodar o `main()` dele.

**Ajustes do robô real que NÃO aplicamos:** o daemon do robô (`robotd/src/control.rs`) usa escala
de ação 0.9, filtros passa-baixa (cabeça 0.5, pernas 0.7) e ganho mais suave quando parado. Isso
compensa o hardware. O simulador oficial (`infer_policy.py`, "deployment rehearsal ... as in
training") não usa nada disso, e o AGENTS.md do upstream diz que as políticas são treinadas sem
filtro. Seguimos o simulador oficial. Veja a ADR-0001.

## 7. Estado inicial e reset

Igual ao de L1375–1387:

- tronco em `(x, y, 0.125)`, com quaternion de guinada (yaw) apontando para a direção desejada
  (no upstream é `[1,0,0,0]`; outra guinada é permitida, mas só gire em torno de z);
- juntas em `DEFAULT_POSE`, velocidades zeradas;
- `bam_ctrl.reset(data.qpos)` e depois os alvos dos motores em `DEFAULT_POSE`;
- `mj_forward`;
- `last_action = 0`, comando zerado, política ativa = `velstand`.

## 8. Políticas e como alimentar o comando

Leia o `manifest.json` da tag `v10` (vai no instalador) e use os campos dele. O app conhece estes
**papéis**:

| Papel | Arquivo | Tipo (`kind`) | Comando (bloco 48–60) | Fim |
|---|---|---|---|---|
| `walk` (padrão) | `velstand.onnx` | perpetual | `twist = [vx, vy, wz]`, `head = 4 valores`, `body = 6 valores` | — |
| `sitstand` | `alpha_sitstand.onnx` | scripted, `posture_flag` | `cmd[0] = 1.0` sentado / `0.0` em pé; o resto do twist zerado; head e body valem | Ao mandar levantar: `cmd[0] = 0.0` por **1.0 s** (`sitstand_rise_s`), depois volta ao `walk` com comando zerado. |
| `ground_pick` | `alpha_ground_pick.onnx` | episodic, `phase` | `cmd[0] = cos 2πφ`, `cmd[1] = sin 2πφ`, `cmd[2] = 0`; φ avança `dt/4.0` | Quando φ ≥ 0.7 → volta ao `walk` com comando zerado (L717–730) |
| `roulade` | `roulade.onnx` | episodic | **os 13 valores zerados** | `duration_s` do manifesto (**1.0 s**) → volta ao `walk` |
| `kick_left` / `kick_right` | `ball_kick_*.onnx` | episodic | **os 13 valores zerados** | `duration_s` (**0.5 s**) → `walk`. Antes, posiciona a bola como em L765–781. |

Regras de transição (as do daemon do robô real, `robotd/src/control.rs`: "one move at a time,
and none from the seat"):

- **Um movimento por vez.** Durante um comportamento episódico ou durante a subida do
  `sitstand`, recuse qualquer outro pedido de comportamento.
- **Nada a partir do assento.** Sentado, o pato só aceita "levantar". Pedidos de movimento
  (twist ≠ 0) enquanto sentado são ignorados e a interface mostra "Levante o pato primeiro".
- Ao terminar qualquer episódio ou a subida: `vel_cmd = 0`, política `walk`.
- Mesmo com uma só política de caminhada, o `infer_policy.py` nunca sai do `sitstand` depois de
  levantar: em L515–517 a troca só acontece com walking **e** standing carregadas. É uma
  limitação do script de ensaio. O robô real sai após `sitstand_rise_s = 1.0` s
  (`robotd/src/control.rs` L95–97, L114 e L832). Seguimos o robô real nesse ponto.

> **Atenção às durações:** o `infer_policy.py` usa 3.0 s (chute) e 2.0 s (cambalhota) como
> padrão de linha de comando, enquanto o manifesto `v10` diz 0.5 s e 1.0 s. O robô real segue o
> manifesto. **Use o manifesto.** No teste de paridade, passe as durações do manifesto para os
> dois lados.

### Limites de comando (velstand)

| Comando | Faixa |
|---|---|
| vx | −0.3 … +0.3 m/s |
| vy | −0.2 … +0.2 m/s |
| wz | −1.5 … +1.5 rad/s |
| head (cada um) | −1.4 … +1.4 rad (head_roll na prática ±0.31) |
| body x, y | ±0.02 m |
| body z | ±0.03 m |
| body roll, pitch, yaw | ±30° (a velstand responde a cerca de ±10° de inclinação) |

Satura (clip) qualquer comando nessas faixas antes de montar a observação.

## 9. Validação de um ONNX carregado pelo usuário

Ao carregar um ONNX personalizado (modo simulador, slot `walk`):

1. a entrada tem formato `[1, 61]` (ou `[N, 61]` / dimensão simbólica) e a saída `[1, 14]`;
2. roda uma inferência com zeros e com uma observação de "em pé" → sem NaN/Inf e com saída não
   constante;
3. se houver `manifest.json` ao lado com `obs_len` ou `action_len` divergentes, ou com
   `model_api` > 1 (LSTM), recuse com mensagem em português.

## 10. Teste de paridade (critério de aceite do M1)

Prove que o núcleo do DuckDesk é numericamente igual ao upstream:

1. importe `PolicyInference`, `load_bam_model` e `load_mujoco_with_bam` de
   `vendor/microduck_rl/scripts/infer_policy.py`, com `termios` e `tty` falsos em
   `sys.modules` (`select` existe no Windows);
2. monte os dois lados com a mesma cena, a mesma `velstand.onnx`, `new_cmd_obs=True`, BAM ligado,
   `vin=7.4` e `vin_drop_gain=0.1`;
3. rode 500 passos de controle (10 s) com um roteiro fixo de comandos: parado 2 s, vx = 0.2 por
   4 s, wz = 1.0 por 2 s, parado 2 s;
4. compare `obs` e `action` em todos os passos e `qpos` no fim. Tolerância: `atol = 1e-5` em
   obs/action e `atol = 1e-4` em qpos. Diferenças acima disso **reprovam** o marco.
5. repita com uma sequência `walk → ground_pick → walk` e `walk → roulade → walk`.
