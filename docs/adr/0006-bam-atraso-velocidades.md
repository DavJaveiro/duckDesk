# ADR-0006: BAM no commit do upstream, atraso zero e caminhada a 0,3 m/s

**Status:** aceita (2026-11-14, revisão pós-M7)

## Contexto

Na entrega M0–M7, a velstand "não andava" (dúvida #5): com vx = 0.2 o pato ficava parado. O
Devin contornou isso com um atraso de 3 passos de controle (60 ms) nos motores. Na revisão,
três fatos foram medidos **só com o código oficial** (`microduck_rl/scripts/infer_policy.py`,
cena `scene.xml`, BAM ligado, 10 s, média de vx entre 5 e 10 s):

| Política | vx comandado | Atraso | vx obtido |
|---|---|---|---|
| velstand | 0.2 | 0 | **0.000** |
| velstand | 0.3 | 0 | 0.112 |
| velstand | 0.2 | 20 ms | 0.000 |
| velstand | 0.3 | 20 ms | 0.147 |
| alpha_walking | 0.2 | 0 / 60 ms | 0.000 |

1. **A especificação fixou o BAM errado.** O `uv.lock` do `microduck_rl@0daab16` usa
   `Rhoban/bam@62bd8ce`; eu tinha fixado `57d13ea` (a ponta do branch), que renomeou
   `vin_drop_gain` para `vin_drop_resistance`. Com o commit certo o resultado acima não muda,
   mas o código volta a chamar a API exatamente como o upstream (sem tradução).
2. **A velstand não sai do lugar com |vx| abaixo de ~0,25** neste simulador. Ela obedece com
   cerca de 40 % do comando. É comportamento da política, não bug do DuckDesk.
3. **O atraso do treino é de 3 a 6 passos de física** (15–30 ms; `_BAM_ACTUATOR_KWARGS` e
   `bam.mjlab`: "delay in simulation steps"), não de 3 a 6 passos de controle. Os 60 ms do
   Devin estavam fora dessa faixa.

Ensaios do DuckDesk com cada atraso (velstand, 5 sementes de empurrão forte):

| Atraso | Andar (vx = 0.3) | Levanta e continua em pé |
|---|---|---|
| 0 | 0.113 m/s | **5/5** |
| 20 ms | 0.149 m/s | 3/5 (cai de novo em 2) |
| 60 ms | 0.152 m/s | 5/5, mas fora da faixa do treino |

## Decisão

- BAM em `62bd8ce12154340be97e06f7f41a0ca8f116d967`, chamando
  `MujocoController(..., vin_drop_gain=...)` como o upstream.
- `delay_lag = 0`, o padrão do `infer_policy.py` (03 §5).
- Comando de caminhada de **0,3 m/s**: teclado W/S = ±0.3, vy = ±0.2; piloto automático com vx
  entre 0.28 e 0.30.
- Virar no lugar com **wz = ±1,5**: a mesma zona morta vale para o giro (código oficial, atraso
  0: 0,013 rad/s com wz = 1,0 e 0,73 rad/s com wz = 1,5). O `TURN` do piloto automático passa a
  ser liga-desliga a ±1,5 até o erro ficar abaixo de 0,15 rad.
- Ensaio do M1: andar com vx = 0.3, aceitando entre 0.10 e 0.25 m/s.

## Consequências

- O pato anda devagar (~0,11 m/s, ou ~30 px/s na tela no tamanho Médio). Para um bichinho na
  barra, isso é aceitável e parece um passinho de pato.
- Se a Pollen publicar uma velstand que acompanhe melhor o comando, basta trocar o ONNX; esta
  ADR não muda o contrato.
- O "wiggle" de 0,35 s na entrada do `WALK` (dúvida #6) foi mantido. Ele é inofensivo, mas pode
  ser removido se um ensaio mostrar que, com vx = 0.3, o pato sempre arranca sem ele.
