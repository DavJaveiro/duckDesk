# ADR-0009: Mascote sempre virado para a câmera

**Status:** aceita (2026-11-14, pós-M7)

## Contexto

A câmera 3/4 do mascote (azimute 140°, ADR-0007) favorece um lado: com o controle de rumo
original de 05 §5 (`base = 0 ou π`), o pato andava para a direita mostrando a frente, mas
andava para a esquerda **de costas** — metade do tempo de caminhada, além de ficar parado de
costas depois de uma caminhada, queda ou empurrão. O dono pediu que o pato tente ficar
sempre virado para quem olha a tela.

## Decisão

- `yaw_ref` fica sempre em ~0 rad (a frente para a câmera). Para alvos à esquerda o pato anda
  **de ré** (`vx < 0`): a velstand treinou vx em [-0.3, 0.3] (upstream `infer_policy.py`
  L1369-1373) e o `PolicyManager` já clampa nesse intervalo, então nenhum contrato muda.
- A correção de profundidade inverte junto com o sinal de vx
  (`yaw_ref = clip(-0.8*y*vx_sign)`), mantendo `y → 0` nos dois sentidos da marcha.
- A regra de borda passa a olhar a **direção do movimento** (sinal de vx), não a cara do pato.
- `IDLE` verifica o rumo a cada tick: erro > 0,5 rad dispara `TURN` de volta para a frente
  (também cobre pós-queda/empurrão). `TURN` continua sendo "girar até a frente".
- O spawn do mascote sorteia a guinada em [-0,7 rad, 0] — do ângulo exato da câmera até o
  eixo +x — nunca de costas.

## Alternativas descartadas

- **Virar para a esquerda normalmente (status quo):** rejeitada pelo dono — deixa o pato de
  costas metade do tempo.
- **Andar de lado com `vy`:** o strafe está treinado só até ±0,2 m/s e lê como caranguejo;
  andar de ré é um movimento natural da marcha e tem folga de comando.
- **Andar na diagonal alternando rumo (ziguezague):** mantém a frente parcialmente visível,
  mas derrapa em `y` e parece indeciso; o `y → 0` ficaria oscilante.

## Consequências

- O pato anda para a esquerda de marcha à ré ("moonwalk"). Se a velstand+BAM-CPU não sair do
  lugar com `vx` negativo em algum hardware, o guarda de "sem progresso" (25 s → `IDLE`) já
  limita o estrago.
- Após `RECOVER`, `SIT`, `PECK`, `ROLL` ou empurrão, o pato gira para a câmera antes de
  voltar a ficar parado.
- `x_limits_for_y`/`_soft_clamp` e o enquadramento da janela não mudam: o pato continua na
  linha `y ≈ 0`.
- Testes: `tests/unit/test_autopilot.py` (moonwalk, borda à esquerda, IDLE→TURN) e o ensaio
  de 600 s em `tests/behavior/test_autopilot_run.py`.
