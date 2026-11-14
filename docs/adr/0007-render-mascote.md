# ADR-0007: Renderização do mascote: ortográfica 3/4, altura medida, transparência pela profundidade

**Status:** aceita (2026-11-14, revisão pós-M7). Substitui as decisões das dúvidas #8, #9 e #10.

## Contexto

O mascote entregue no M5 ficou ruim na tela. A revisão encontrou quatro causas:

1. **Cabeça cortada.** `H_m` foi medido como a altura do **tronco** (0,1155 m), não do chão ao
   topo da cabeça (~0,27 m). A janela tinha menos da metade da altura necessária. O critério
   "pés na borda" passou, e ninguém olhou o resto da imagem: o próprio
   `m5_pe_na_borda_100.png` mostra o pato sem cabeça.
2. **Pouco fluido.** Para caber em 15 % de CPU, a renderização caiu para 15 fps andando e 12
   parado.
3. **Pedaços pretos e cortes.** A máscara de segmentação era recalculada só a cada 4 quadros,
   enquanto a cor mudava em todos, então a silhueta ficava atrasada.
4. **Câmera "quase ortográfica".** Para uma câmera ortográfica, o MuJoCo lê `fovy` como altura em
   **metros**; passado em graus, sai tudo preto. Daí veio a câmera de longe com fovy estreito.
   Além disso, o perfil puro escondia uma perna atrás da outra.

Também havia um desvio de tamanho não registrado: 80/120/180 era a altura do **pato**, mas o
código usou esses valores como o lado da janela, e o pato saiu com ~75 px no tamanho Médio.

## Decisão

- Câmera ortográfica de verdade (`orthographic = 1`, `fovy = 1.6 × H_m` em metros), em vista 3/4
  (azimute 140°, elevação −10°).
- `H_m` medido em tempo de execução a partir dos vértices das malhas, ao longo do eixo "para
  cima" da câmera (`duck_screen_height_m`): 0,270 m.
- Mapeamento com o eixo horizontal da câmera (`rx ≈ 0.64`, `ry ≈ 0.77`). O enquadramento por
  quadro compensa o arredondamento da posição da janela, então o pato não treme.
- Só o grupo 2 (malhas visuais) é desenhado, sem céu nem efeitos. A transparência vem da
  profundidade do **mesmo quadro**. Superamostragem 2× com MSAA desligado, e só o retângulo do
  pato é processado.
- 30 fps sempre. A meta de CPU sobe para ≤ 30 % de um núcleo.
- `S = 1.6 × H`, com H = 80/120/180 px.

## Medições (Windows 11, revisão)

| | Antes (M5) | Depois |
|---|---|---|
| Pato inteiro na janela | não (cabeça cortada) | sim |
| fps | 15 andando / 12 parado | 31 |
| Silhueta | atualizada a cada 4 quadros | todo quadro |
| Custo de um quadro (S = 192) | — | 2,4 ms |
| CPU do app no modo mascote | 14,4 % (a 15 fps) | ~25 % de um núcleo (a 31 fps) |

## Consequências

- A vista 3/4 mostra o pato de costas quando ele anda para a esquerda. É o comportamento
  correto de um modelo 3D.
- `tests/unit/test_mascot_map.py` cobre a projeção 3/4 e tem um teste de regressão para a
  cabeça cortada.
