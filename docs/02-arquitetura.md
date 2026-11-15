# 02: Arquitetura

## Visão geral

```
┌──────────────────────────── processo único (thread do Qt) ────────────────────────────┐
│                                                                                       │
│  CommandSource ──► DuckBrain ──► PolicyManager ──► SimCore (MuJoCo + BAM, 200 Hz)     │
│  (teclado │ piloto     (pedidos,     (61D obs, ONNX,     (MjModel/MjData únicos)      │
│   automático)          regras)      troca de políticas)          │                    │
│                                                                  ▼                    │
│                                         SimClock (passo fixo de 20 ms, acumulador)    │
│                                                                  │                    │
│                       ┌──────────────────────────┬───────────────┴───────┐            │
│                       ▼                          ▼                       ▼            │
│              SimulatorView (QMainWindow)   MascotView (janela      TrayIcon           │
│              renderização 3D offscreen     transparente sobre      (QSystemTrayIcon)  │
│              → QImage                      a barra de tarefas)    + RadialMenu       │
│                                            (roda de ações do pato, 05 §11)            │
│                                                                                       │
│                         AppController: modo atual, troca, configurações               │
└───────────────────────────────────────────────────────────────────────────────────────┘
```

## Módulos (`src/duckdesk/`)

| Módulo | Responsabilidade | Depende de |
|---|---|---|
| `assets.py` | Localiza os assets (dev: `assets/`; instalado: `sys._MEIPASS`/pasta do app), lê `assets/lock.json` e confere SHA-256 | — |
| `sim/core.py` — `SimCore` | Carrega a cena com BAM (porte de `load_mujoco_with_bam`), `reset(x, y, yaw)`, `step_control(targets)` (4 × `bam.update` + `mj_step`), estacionar a bola, `snapshot()` (qpos, qvel, time) | mujoco, bam |
| `sim/clock.py` — `SimClock` | Acumulador de passo fixo: dado o tempo real decorrido, diz quantos passos de 20 ms rodar. Máximo de 5 passos por tick (se ficar para trás, descarta o atraso em vez de entrar em espiral). Pausa e velocidade 0.5×/1×. | — |
| `policy/contract.py` | `DEFAULT_POSE`, `quat_rotate_inverse`, `build_obs(...)`: funções puras, portadas do upstream | numpy |
| `policy/manager.py` — `PolicyManager` | Carrega o manifesto e os ONNX, valida 61→14, mantém `last_action`, papel ativo, timers e fase; implementa as regras de transição de 03 §8 | onnxruntime |
| `policy/validate.py` | Validação de ONNX do usuário (03 §9) | onnxruntime |
| `brain/commands.py` | Dataclass `DuckCommand` (twist, head, body) e `Request` (`SIT`, `STAND`, `PECK`, `ROLL`, `KICK_L`, `KICK_R`, `RESET`) | — |
| `brain/autopilot.py` — `Autopilot` | Máquina de estados do mascote (05 §5). Recebe o estado do pato e a faixa de x permitida e devolve comando e pedidos. Sem Qt. | numpy |
| `brain/beak.py` — `BeakAnimator` | Animação do bico: lip-sync do grasno, olhada "um tiquinho" e bocejo por quietude — porte dos `idle_head.rs`/`robotd-params` do upstream (05 §6, ADR-0010). Sem Qt. | numpy |
| `brain/keyboard.py` | Mapeia teclas para `DuckCommand` e `Request` (04 §3). Sem Qt: recebe códigos de tecla abstratos. | — |
| `render/offscreen.py` | Envolve `mujoco.Renderer`: renderização RGB e de segmentação, máscara do pato, superamostragem 2× e saída em array RGBA pré-multiplicado | mujoco |
| `render/camera.py` | Câmera orbital livre e câmera que segue o pato (simulador) | mujoco |
| `render/mascot.py` | Câmera ortográfica 3/4 do mascote, altura do pato medida nas malhas, transparência pela profundidade (05 §9, ADR-0007) | mujoco |
| `ui/simulator_window.py` | `QMainWindow` com menus, viewport, HUD e barra de status (04) | PySide6 |
| `ui/mascot_window.py` | Janela transparente, sem borda, sempre no topo, sem botão na barra de tarefas; arrastar e clicar (05) | PySide6 |
| `ui/radial_menu.py` | Roda radial de ações do pato no clique direito, ancorada acima da cabeça (05 §11, ADR-0008) | PySide6 |
| `ui/tray.py` | Ícone na bandeja e menu (04 §6, 05 §7) | PySide6 |
| `ui/about.py` | Diálogo "Sobre" com a atribuição e as licenças (07) | PySide6 |
| `platform/win_taskbar.py` | `SHAppBarMessage(ABM_GETTASKBARPOS)`, estado de ocultação automática, monitor, DPI | ctypes |
| `platform/win_topmost.py` | Reafirma `HWND_TOPMOST`; detecta app em tela cheia (`SHQueryUserNotificationState`) | ctypes |
| `platform/autostart.py` | Liga e desliga "Iniciar com o Windows" (`HKCU\...\Run`) | winreg |
| `platform/sound.py` | Fallback do "Quack! Quack!" quando a voz está desligada: toca `assets/sounds/quack.mp3` (empacotado) via MCI `mciSendStringW`, assíncrono por natureza (05 §6) | ctypes/winmm |
| `platform/voice/` | Voz gerada por semente — porte do daemon `sounds/` upstream: `rng.py` (xoshiro256++/splitmix64/CRC-32), `synth.py` (DSP 48 kHz), `personality.py` (traços por semente), `voices.py` (7 tags), `__init__.py` (banco WAV lazy + facade `Voice`) (05 §6, ADR-0011) | numpy, winsound |
| `settings.py` | Configurações em `%APPDATA%\DuckDesk\settings.json`: tamanho do mascote, último modo, autostart, velocidade. Se o perfil não for gravável, o app continua rodando sem persistir (e os logs caem para `%TEMP%\DuckDesk\logs`) | — |
| `app.py` — `AppController` | Monta tudo, laço do `QTimer`, troca de modos | todos |
| `__main__.py` | Ponto de entrada (`duckdesk`). Instância única (`QLockFile` ou mutex nomeado). | app |

Regra de dependência: `sim`, `policy`, `brain` e `render` **não importam PySide6**. Só `ui/`,
`app.py` e `platform/` (este com ctypes) conhecem a interface. Assim o núcleo é testável sem
janela.

## Laço principal

Um `QTimer` com `Qt.PreciseTimer`, intervalo de 8 ms:

```
on_tick():
    n = clock.steps_due(now)                        # 0..5 passos de 20 ms
    for _ in range(n):
        cmd, reqs = command_source.poll(state)      # teclado ou piloto automático
        brain.apply(reqs)                           # regras de 03 §8
        targets = policy_manager.step(sim, cmd)     # timers → obs → onnx → alvos
        sim.step_control(targets)                   # 4 × (bam.update + mj_step)
        watchdog.check(sim)                         # NaN, pato fora dos limites, caído há muito tempo
    if n > 0 or view_needs_redraw:
        active_view.render(sim.snapshot())          # no máximo a 60 fps (simulador) / 30 fps (mascote)
```

- A física **nunca** espera a renderização, e a renderização nunca roda mais vezes que o
  necessário.
- Watchdog: `NaN` em `qpos` → reset imediato e aviso no log. Tronco inclinado mais de 60° por
  mais de 6 s seguidos (a velstand não conseguiu se levantar) → reset em pé.

## Renderização

- Um `mujoco.Renderer` por vista, criado sob demanda e reaproveitado. Os dois usam o contexto
  OpenGL do próprio MuJoCo (GLFW invisível no Windows), na thread do Qt.
- O resultado vira `QImage` (`Format_RGB888` no simulador, `Format_ARGB32_Premultiplied` no
  mascote) e é pintado num `QWidget`. Não use `QOpenGLWidget`: contexto compartilhado entre Qt e
  MuJoCo dá mais problema do que resolve (ADR-0004).
- O simulador renderiza com o tamanho do viewport (limitado a 1920×1080) e o mascote com o
  tamanho da janela × 2 (superamostragem).

## Estrutura de pastas

```
DuckDesk/
├── AGENTS.md, README.md, THIRD_PARTY_NOTICES.md
├── pyproject.toml, uv.lock, .python-version
├── assets/
│   ├── lock.json                         # commits, URLs, SHA-256 de cada arquivo
│   ├── upstream/microduck_rl/robot/microduck/   # XMLs + assets/*.stl, sem modificação
│   ├── policies/v10/                     # *.onnx + manifest.json + README.md
│   └── icons/                            # ícones próprios do DuckDesk (não da Pollen)
├── src/duckdesk/ ...                     # (tabela acima)
├── tests/
│   ├── unit/                             # contrato, relógio, piloto automático, mapeamento, validação
│   ├── parity/                           # paridade com o upstream (03 §10)
│   └── behavior/                         # ensaios headless de comportamento (08, M1)
├── scripts/
│   ├── fetch_assets.py                   # baixa e confere os assets (dev)
│   ├── headless_run.py                   # roda N segundos sem janela e imprime métricas
│   └── measure_perf.py                   # CPU/RSS do app rodando (M6)
├── installer/
│   ├── duckdesk.spec                     # PyInstaller
│   └── duckdesk.iss                      # Inno Setup
├── docs/ ...
└── vendor/                               # clones de referência (fora do git)
```

## Versões fixadas

| Pacote | Versão | Motivo |
|---|---|---|
| Python | 3.12.x | o BAM exige `>=3.12,<3.13` |
| mujoco | 3.10.0 | a mesma do `uv.lock` do `microduck_rl` no commit fixado |
| onnxruntime | 1.24.4 | idem |
| numpy | 2.4.1 | idem |
| better-actuator-models | git `62bd8ce…` com o extra `[mujoco]` | o mesmo commit do `uv.lock` do `microduck_rl` (ADR-0006) |
| PySide6-Essentials | a 6.x mais recente com wheel para cp312 win_amd64, fixada em `uv.lock` | Qt sem os módulos pesados (WebEngine etc.) |
| pyinstaller | a mais recente estável, fixada em `uv.lock` | — |
| pytest, ruff | grupo `dev` | — |

O `pyproject.toml` inicial já declara essas dependências. Ao rodar `uv lock`, confira se o
resolvedor não mudou `mujoco`, `onnxruntime` ou `numpy`.

## ADRs

| ADR | Decisão |
|---|---|
| [0001](adr/0001-referencia-infer-policy.md) | A referência de comportamento é o `infer_policy.py` (simulação de ensaio), não o `robotd` |
| [0002](adr/0002-uma-cena-dois-modos.md) | Uma cena (`scene_ball.xml`) e um `MjModel` para os dois modos |
| [0003](adr/0003-thread-unica.md) | Física, rede e interface na thread do Qt, com passo fixo |
| [0004](adr/0004-render-offscreen.md) | Renderização offscreen do MuJoCo → QImage, sem `QOpenGLWidget` |
| [0005](adr/0005-janela-mascote-pequena.md) | Janela do mascote pequena que acompanha o pato, em vez de uma faixa da largura da tela |
| [0006](adr/0006-bam-atraso-velocidades.md) | BAM no commit do upstream, atraso zero e comando de caminhada de 0,3 m/s |
| [0007](adr/0007-render-mascote.md) | Mascote com câmera ortográfica 3/4, altura medida nas malhas e transparência pela profundidade |
| [0008](adr/0008-roda-de-acoes-do-mascote.md) | Roda radial de ações no clique direito do pato; menu nativo só no ícone da bandeja |
| [0009](adr/0009-mascote-sempre-de-frente.md) | Mascote sempre virado para a câmera: esquerda de ré (vx < 0), IDLE/TURN voltam à frente |
| [0010](adr/0010-bico-articulado-em-runtime.md) | Bico do mascote: pose cinemática dos geoms da mandíbula (sem junta/atuador novos); lip-sync do grasno, olhada e bocejo do upstream |
| [0011](adr/0011-voz-gerada-por-semente.md) | Voz gerada por semente: porte do daemon `sounds/` (sintetizador procedural, não TTS), tags por evento, banco WAV lazy |
