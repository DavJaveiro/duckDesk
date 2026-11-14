# 04: Modo simulador (janela 3D)

## 1. Janela

- `QMainWindow`, título "DuckDesk: Simulador", 1280×800 por padrão; lembra o tamanho e a posição
  em `settings.json`.
- Área central: viewport com a imagem do MuJoCo (cena `scene_ball.xml` como vem do upstream: céu
  em gradiente, chão quadriculado, luz).
- Painel lateral recolhível à direita, com botões de comportamento e controles deslizantes de
  cabeça e corpo (§4).
- Barra de status: política ativa, `vx/vy/wz` comandado × obtido (média de 1 s no
  referencial do corpo, igual ao bloco `[vel 1s avg]` do `infer_policy.py`), fps de renderização e "passos atrasados".
- Fechar a janela **não** encerra o app se o ícone da bandeja estiver ativo: a janela só se
  esconde (aviso na primeira vez). "Sair" pelo menu encerra.

## 2. Câmera

| Ação | Efeito |
|---|---|
| Arrastar com o botão esquerdo | Orbitar (`mjv_moveCamera` com `mjMOUSE_ROTATE_V/H`) |
| Arrastar com o botão direito | Deslocar (`mjMOUSE_MOVE_V/H`) |
| Roda do mouse | Zoom (`mjMOUSE_ZOOM`) |
| Duplo clique | Centralizar no pato |
| Tecla `C` | Alterna câmera livre ↔ seguir o pato (padrão: seguir, com `trackbodyid = trunk_base`) |

A câmera inicial é a da cena: azimute 160°, elevação −20°, a uns 0,8 m do pato.

## 3. Teclado

O mapeamento segue o espírito do `infer_policy.py`, com uma diferença: lá cada tecla soma um
degrau ao comando; aqui o comando vale **enquanto a tecla está pressionada**, que é mais natural
numa janela. Não implemente o degrau.

| Tecla | Efeito |
|---|---|
| `W` / `↑` | vx = +0.30 enquanto pressionada (abaixo de ~0,25 a velstand não anda, ADR-0006) |
| `S` / `↓` | vx = −0.30 |
| `A` / `D` | wz = +1.5 / −1.5 (girar; abaixo de ~1,0 a velstand parada não gira, ADR-0006) |
| `Q` / `E` | vy = +0.20 / −0.20 (passo lateral) |
| `Shift` + direção | Velocidade máxima da faixa (03 §8) |
| `Y` | Sentar ↔ levantar |
| `G` | Bicar o chão |
| `R` | Cambalhota |
| `K` / `L` | Chute com o pé esquerdo / direito (a bola é colocada na frente do pé) |
| `Espaço` | Zera cabeça e corpo |
| `Backspace` | Reset: pato em pé na origem |
| `P` | Pausar / continuar |
| `Ctrl+M` | Enviar para a barra de tarefas |

O comando muda com rampa de **1.5 m/s²** (linear) e **6 rad/s²** (giro), para não dar degraus
bruscos. O robô real também suaviza o comando ("the caller's smoothed command", `robotd`).

Teclas de comportamento respeitam as regras de 03 §8. Quando um pedido é recusado, a barra de
status mostra o motivo por 2 s (por exemplo, "Levante o pato primeiro").

### 3a. Controle (gamepad)

Qualquer controle funciona no modo simulador (`platform/gamepad.py`, sondado no próprio timer do
Qt — sem threads nem dependências): **XInput** cobre Xbox e compatíveis; **WinMM
`joyGetPosEx`** cobre o restante (DualShock/DualSense, Switch Pro, genéricos HID). Com um
controle conectado, a barra de status mostra `· controle` junto do nome da política.

| Entrada | Efeito |
|---|---|
| Analógico esquerdo ↑/↓ | vx (andar); a magnitude é escalada no piso de 0,26 (abaixo de ~0,25 a velstand não anda, ADR-0006) |
| Analógico esquerdo ←/→ | wz (girar); piso de 1,0 rad/s pelo mesmo motivo |
| Analógico direito ←/→ | `head_yaw` ±0,9 (olhar para os lados) |
| Analógico direito ↑/↓ | `neck_pitch` ±0,4 (olhar para cima/baixo) |
| D-pad ←/→ | vy = ±0,20 (passo lateral, como `Q`/`E`) |
| `A` / `B` / `X` / `Y` | Bicar · Cambalhota · Chute esq. · Chute dir. |
| `Back` | Sentar ↔ levantar |
| `Start` | Pausar / continuar |
| `L3` (clique esq.) | Zera cabeça e corpo |
| `R3` (clique dir.) | Reset: pato em pé na origem |

Botões disparam **uma vez por aperto** (detecção de borda); o analógico comanda enquanto
defletido, com a mesma rampa do teclado, e a zona morta é 0,18. Soltar o analógico devolve o
canal ao teclado.

## 4. Painel lateral

- Botões: **Sentar/Levantar**, **Bicar**, **Cambalhota**, **Chutar (esq.)**, **Chutar (dir.)**,
  **Reset**. Ficam desabilitados quando a regra não permite.
- **Cabeça**: 4 sliders (neck_pitch, head_pitch, head_yaw, head_roll), com as faixas de 03 §8.
- **Corpo**: 6 sliders (x, y, z, roll, pitch, yaw), com as faixas de 03 §8.
- Os sliders escrevem nos slots de comando (head e body). Os comportamentos episódicos ignoram
  esses slots (comando todo zerado, 03 §8).

## 5. Menus

| Menu | Itens |
|---|---|
| **Arquivo** | Carregar política de caminhada (.onnx)… · Voltar à política oficial · Sair |
| **Simulação** | Pausar (`P`) · Reiniciar (`Backspace`) · Velocidade ▸ 0.25× / 0.5× / 1× · Empurrar o pato (aplica um impulso lateral, para ver a recuperação) |
| **Comportamentos** | Sentar/Levantar · Bicar o chão · Cambalhota · Chutar (esq./dir.) |
| **Visualização** | Seguir o pato (`C`) · Mostrar contatos · Mostrar juntas · Painel lateral |
| **Modo** | **Enviar para a barra de tarefas** (`Ctrl+M`) |
| **Ajuda** | Atalhos de teclado · Sobre e licenças |

"Carregar política de caminhada" valida o arquivo (03 §9). Se passar, a política substitui
`velstand.onnx` no papel `walk` e o pato é reiniciado. A barra de status mostra
"Política: <nome do arquivo>". A escolha **não** é salva entre sessões na v1.

"Empurrar o pato" aplica `xfrc_applied` no `trunk_base`: 2 N laterais por 0,1 s.

## 6. Ícone na bandeja (enquanto o simulador está aberto)

Mesmo menu do mascote (05 §7), com "Abrir simulador" em negrito.

## 7. Enviar para a barra de tarefas

Ao escolher **Modo → Enviar para a barra de tarefas**:

1. a janela do simulador se esconde (não fecha);
2. o estado é reiniciado para o mascote (05 §4): pato em pé, de lado, numa posição x calculada;
3. a janela do mascote aparece com um fade-in de 300 ms;
4. `settings.last_mode = "mascot"`.

A volta ao simulador está em 05 §8.
