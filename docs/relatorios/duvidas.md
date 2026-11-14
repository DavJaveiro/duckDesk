# Dúvidas e desvios em aberto

Registre aqui tudo o que a documentação não respondeu, ou em que você precisou fazer diferente.
Uma entrada por item. Não apague as entradas resolvidas: marque como resolvidas e diga como.

| # | Data | Marco | Documento/seção | Dúvida ou desvio | Proposta | Status |
|---|---|---|---|---|---|---|
| 1 | 2026-11-14 | M0 | 02 §"Versões fixadas" / 03 §2 / 07 | O bam fixado (`57d13ea`) não tem o parâmetro `vin_drop_gain` que o `infer_policy.py@0daab16` usa: a partir de `Rhoban/bam@e4bf1aa` o nome virou `vin_drop_resistance` (Ω), com queda `R·Σ\|τ\|/kt`. O `uv.lock` do próprio upstream fixa bam `62bd8ce` (anterior à renomeação), não `57d13ea`. | Em `sim/core.py` mantive a assinatura do upstream (`vin_drop_gain`) e traduzi com `vin_drop_resistance = gain·kt`, que produz a mesma queda de tensão. Alternativa: fixar bam em `62bd8ce` via ADR. | Resolvida (revisão): erro da especificação. BAM fixado em `62bd8ce`, o commit do `uv.lock` do upstream; a tradução foi removida e o código chama `vin_drop_gain` como o upstream. ADR-0006. |
| 2 | 2026-11-14 | M0 | 07 | O doc diz copiar "de `robot/microduck/`", mas no repositório o caminho é `src/mjlab_microduck/robot/microduck/`. | `fetch_assets.py` usa o caminho real e grava em `assets/upstream/microduck_rl/robot/microduck/` (layout do 02). | Resolvida |
| 3 | 2026-11-14 | M0 | 07 ("`config_mjcf_*.json` vão no instalador") | Há 7 `config_mjcf_*.json` no upstream (walk, allcollisions, rollers, backlash…). O `infer_policy.py` não usa nenhum — constrói o modelo BAM via `bam.model.load_model`. | Copiei só `config_mjcf_groundcontact.json`, que pareia com o `robot_groundcontact.xml` enviado. Se a revisão quiser todos (ou nenhum), ajusto o filtro. | Resolvida (revisão): só `config_mjcf_groundcontact.json` está certo; é o par do XML enviado. |
| 4 | 2026-11-14 | M0 | 03 §2 | O `load_mujoco_with_bam` do upstream imprime um resumo dos atuadores na carga (L96-102). | Não portei o `print`; um log estruturado vem no M1/M4. Sem efeito na física. | Resolvida |
| 5 | 2026-11-14 | M1 | 03 §4 + §5 vs §10 | Contradição interna: §4 manda gravidade projetada ("não o acelerômetro bruto") e §5 manda delay desligado — mas nessa config o `velstand` não anda (vx≈0) e o aceite §10 (marcha vx∈[0.12,0.28]) é inalcançável. O cfg de treino (`microduck_velocity_env_cfg.py`) usa `USE_PROJECTED_GRAVITY=True` e DR de delay de atuador `3..6` passos. Varredura pg×lag em MuJoCo+BAM-CPU: pg+lag0 → vx≈0; pg+lag3 → vx≈0.108 (marcha estável); acelerômetro cru → até 0.209 mas instável (57°+ de tilt parado) — fora de distribuição. O `infer_policy.py` upstream real reproduz o mesmo travamento sob BAM (`--no-bam` anda). | Config adotada: gravidade projetada (fiel ao §4) + delay fixo lag=3 (mínimo do DR de treino — desvio do §5, documentado). Sobra um near-miss: marcha 0.108 vs piso 0.12. O teste fica `xfail` não-estrito até a revisão decidir entre (a) aceitar ~0.11, (b) ajustar o critério, ou (c) apontar outra config/policy. | Resolvida (revisão): o `infer_policy.py` oficial também não anda com vx = 0.2 (medido: 0.000). O atraso do treino é de 3–6 passos de **física** (15–30 ms), não de controle; os 60 ms ficavam fora. Decisão: atraso 0 (padrão do upstream) e comando de 0,3 m/s → 0,113 m/s, 5/5 recuperações. Critério do M1 ajustado. ADR-0006. |
| 6 | 2026-11-14 | M2 | 08 §M2 vs 05 §5 | O aceite [duro] "|y| < 0,3 m" nos 10 min de piloto é inalcançável com a lei de rumo do 05 §5 + a física real: a cambalhota falha ~20 % das vezes (ensaio M1: 4/5) e a queda desloca o pato em y; o retorno é lento porque a correção de rumo é limitada a ±0,3 rad e a marcha anda ~0,11 m/s (dúvida #5). Medido: |y| máx 0,83 m numa semente, excursões sempre após RECOVER; na semente do teste de aceite |y| máx 0,276 m (passa — depende de quantas quedas ocorrem). Também usei dois desvios documentados no módulo: "wiggle" de giro de 0,35 s na entrada do WALK (sem ele o comando vx num pato assentado é ignorado — histerese da bacia) e bail-out de 25 s sem progresso → IDLE. | Implementei a lei do §5 à risca; o assert |y|<0,3 fica `xfail` não-estrito (XPASS na semente fixa, documentando a fragilidade). Alternativas p/ revisão: (a) interpretar o limite fora de janelas pós-RECOVER, (b) afrouxar para |y|<1,0 m, (c) afrouxar o clip de rumo via ADR (mudaria 05 §5). | Resolvida (revisão): com a ADR-0006, a semente fixa dá |y| máx 0,121 m e 1 queda em 10 min; o `xfail` foi removido. O "wiggle" e o bail-out de 25 s ficam aceitos. |
| 7 | 2026-11-14 | M3 | 04 §6 + 08 §M3/M4 | O doc 04 define a bandeja completa (menu com estados) mas o plano coloca o "app shell/bandeja/settings" no M4. No M3 precisava-se decidir como a janela esconde sem sair. | Bandeja mínima no M3 (ícone + "Abrir simulador" + "Sair") só para sustentar o ciclo de vida; menu completo fica no M4. Sem ADR: só antecipei o mínimo necessário. | Resolvida (revisão): aceito; o mínimo antecipado era necessário. |
| 8 | 2026-11-14 | M5 | 05 §3 "ortográfica" | `model.vis.global_.orthographic` com `mjCAMERA_FREE` renderiza frame todo preto no mujoco 3.10 (nem com `mjRND_*` ajustados sai imagem). | Câmera livre a D=3 m + fovy estreito (~3,5°) aproximando a ortográfica: deriva de escala ~2 % entre frente/fundo — invisível em 80–180 px. O critério do próprio doc é o resultado (perfil, sem perspectiva, chão fixo). Se a revisão exigir orto exata, precisamos de outra rota (ex.: câmera fixa ortográfica compilada no spec). | Resolvida (revisão): na câmera ortográfica, o `fovy` é a altura em **metros**; em graus sai preto. Agora é ortográfica de verdade, em vista 3/4. ADR-0007. |
| 9 | 2026-11-14 | M5 | 05 §9 "supersampling 2×" | O doc pede render em 2× físico + downsample para a borda suave; mas o framebuffer GL já sai com MSAA (`vis.quality.offsamples=4`) e a máscara de segmentação é binária por construção — supersample manual dobrava ~1,5 ms/quadro de CPU (60 % do orçamento) sem ganho visível. | Render na resolução física final + MSAA do GL + feather 3×3 na máscara seg (aproxima cobertura real). Resultado: CPU 24,5 % → 14,4 % (alvo ≤15 %) e bordas suaves verificadas nos PNGs. A máscara seg é atualizada a cada 4 quadros (silhueta muda devagar). | Resolvida (revisão): a máscara a cada 4 quadros causava os pedaços pretos. Agora a transparência vem da profundidade do mesmo quadro, com 2× SSAA processando só o retângulo do pato (2,4 ms/quadro). ADR-0007. |
| 10 | 2026-11-14 | M5 | 05 §2 "clique atravessa" + §9 "30 fps" | Duas dependências de plataforma: (a) o clique-através usa o hit-test nativo de janela em camadas do Windows (`WA_TranslucentBackground` → `UpdateLayeredWindow`, pixels alpha=0 passam o clique) — o fallback `WM_NCHITTEST→HTTRANSPARENT` ficou só comentado, não implementado; (b) o doc permite até 30 fps / 15 ocioso, mas o alvo de CPU ≤15 % só fecha a 15 fps andando / 12 ocioso. | (a) Verificado programaticamente na máquina real: `WindowFromPoint` em pixel alpha=0 devolve o hwnd da janela atrás e em pixel opaco devolve o do mascote. Se algum Windows/driver falhar no hit-test nativo, implementa-se o `nativeEvent` com `HTTRANSPARENT`. (b) 15/12 fps medido; subir para 30/15 fica a critério da revisão se o alvo de CPU for afrouxado. | Resolvida (revisão): (a) aceito o hit-test nativo, já verificado; (b) 30 fps sempre, com a meta de CPU em ≤ 30 % de um núcleo (medido ~25 %). ADR-0007. |
| 11 | 2026-11-14 | M7 | 08 §M7 "tempo de abertura" + "2 h sem travar" | O aceite não define os proxies: "abertura" medida como? (clique→janela? spawn→primeiro quadro?) e "sem travar" observado como? | Proxies adotados: abertura = spawn do exe → linha `modo mascote` no log (última etapa do arranque antes do 1º quadro; erro < ~100 ms). "Sem travar" = processo vivo em todas as amostras + pato visível/móvel em screenshots periódicos + CPU/RSS sãos. CPU em "% de 1 núcleo" (cpu_times/wall), não em % do sistema como o Gerenciador de Tarefas. | Resolvida (revisão): proxies aceitos. |
| 12 | 2026-11-14 | M7 | 08 §M7 aceite 1 [duro] "2 h sem travar" | O soak foi encerrado aos ~13,9 min (835 s) por decisão explícita do usuário ("tá ótimo o soak, já"), antes das 2 h pedidas. | Registrado como parcial em M7.md: na janela observada o processo ficou vivo nas 166 amostras, RSS estável (final 623,9 MB = @5min, teto 686,3 MB) e o pato respondeu na barra. A evidência curta não prova a ausência de vazamento em 2 h — fica a critério da revisão aceitar ou repetir o ensaio completo. | Aceita pelo dono como parcial. Recomendação da revisão: repetir as 2 h com o instalador gerado depois da ADR-0007, porque o custo por quadro mudou. |

## Revisão pós-M7 (2026-11-14)

Itens que **não** estavam nesta lista e foram corrigidos na revisão:

- **Cabeça cortada no mascote:** `H_m` era a altura do tronco (0,1155 m); o certo é do chão ao
  topo da cabeça (0,270 m, medido nas malhas). ADR-0007.
- **Tamanho:** 80/120/180 px é a altura do pato; o código usava como lado da janela. Agora
  `S = 1.6 × H`.
- **PRs encadeados:** os PRs #13–#18 foram mesclados uns nos outros e a `main` ficou no M1. Eles
  foram mesclados na `main` na revisão. Daqui para frente, **todo PR aponta para `main`**.
- **Pato saindo do monitor (rodada da roda de ações):** o botão "Empurrar" da roda aplicava
  `xfrc_applied` e o `_apply_push` só rodava no laço do simulador, então no modo mascote a força
  lateral de 2 N ficava aplicada para sempre e o pato deslizava para fora da tela. Corrigido:
  o passo de controle do mascote também expira o empurrão em 0,1 s e o `exit_mascot` limpa a
  força. Como reforço, o enquadramento prende a janela em `[band.left, band.right]` e os limites
  de x do piloto automático passam a depender de `y` (vista 3/4), então o pato nunca sai do
  monitor mesmo com queda/cambalhota/empurrão na borda (05 §3).
- **Pato voltava ao centro ao soltar o arrasto:** `_mascot_drag_finish` escrevia o `x` solto no
  `qpos` e **depois** pedia `RESET` — e `mgr.request(RESET, sim)` roda `sim.reset()`
  internamente, zerando o `x` (origem do mundo = centro da banda). O mesmo bug fazia
  `mascot_last_x` nunca sobreviver em `enter_mascot`. Corrigido: o `RESET` vem antes da
  escrita da posição, e o drop preserva a guinada ("mesmo sentido", 05 §6). Cursor de
  mãozinha (aberta/fechada) no hover e durante o arrasto.
- **Pato de costas (pedido do dono):** com a lei `base = 0 ou π` de 05 §5, o pato andava para
  a esquerda de costas para a câmera e ficava parado assim depois de quedas/empurrões. Na
  ADR-0009 ele passa a andar de ré (`vx < 0`, faixa treinada) com `yaw_ref ≈ 0`, e
  `IDLE`/`TURN` sempre o giram de volta para a frente.
- **Duplo clique (pedido do dono):** não abre mais o simulador — emite "Quack! Quack!".
  Abrir o simulador fica só na bandeja e na roda de ações. O som é o MP3 fornecido pelo dono
  em `assets/sounds/quack.mp3` (vai no instalador), tocado via MCI `mciSendStringW` — o
  `winsound` não toca MP3 nem toca som da memória de forma assíncrona (foi por isso que a
  primeira versão sintetizada saiu muda: `SND_MEMORY | SND_ASYNC` levanta `RuntimeError`).
- **Bico do pato (pedido do dono):** o robô real tem servo de boca (`MOUTH_INDEX = 9`, fora
  das políticas), mas o MJCF empacotado modela a mandíbula como geometria rígida — a jaw
  linkage do "modelo novo" ficou de fora. Sem junta possível sem alterar o arquivo, adotada
  a pose cinemática dos geoms `jaw`/`jaw_soft`/`mouth_tip` em runtime (regra 3), com lip-sync
  da envolvente do `quack.mp3`, olhada "um tiquinho" e bocejo por quietude — parâmetros
  verbatim de `idle_head.rs`/`robotd-params` (`glance_mouth 0,4`, `yawn_after 45 s`,
  `yawn_every 90 s`, `yawn_open 0,6`, `yawn_pitch −0,15`). ADR-0010.
- **"Abrir simulador" travava e fechava o pato (relato do dono):** a bandeja chamava
  `show_simulator` puro, que só mostrava a janela sem sair do modo mascote — como
  `self.mascot` continuava vivo, o `_tick` seguia no laço do mascote e a viewport do
  simulador nunca renderizava (janela "congelada"). Corrigido com `open_simulator()`:
  sai do mascote (`exit_mascot`, que já mostra a janela) ou só a mostra quando já está
  no simulador; `listen_for_raise` usa o mesmo caminho. O clique simples no ícone da
  bandeja também estava errado: a spec (05 §7) pede "mostra ou esconde o pato" e ele
  chamava `show_simulator` — agora chama `toggle_mascot`.
- **Roda → "Abrir simulador" travava o app inteiro (relato do dono, 2.ª ocorrência):** o
  caminho da bandeja já estava corrigido, mas o setor da roda seguia travando — só na
  tela real (offscreen nunca reproduziu). O `deleteLater()` da roda, uma `QWidget`
  Python-subclassed com `Qt.Popup` + filtro de evento no `QApplication`, corrompia o
  interpretador durante o desmanche do grab de mouse: `duckdesk.app.__dict__` era
  esvaziado (`sys.modules['duckdesk.app']` chegava a ser substituído por um objeto de
  arquivo — corrupção de heap, não finalização), e a partir daí cada `_tick` morria em
  `NameError` num ciclo de 8 ms — simulador zumbi. Diagnosticado por bissecção:
  todos os passos de `exit_mascot` eram inocentes; só a deleção do menu matava o
  módulo (a do mascote, não). Nem `QTimer.singleShot(0, callback)` bastava. Corrigido:
  a roda nunca é deletada — `_close_duck_wheel` só esconde (o widget já era reusado em
  `_show_duck_wheel`); o callback continua diferido para fora do `mousePressEvent`.
  Repro de tela real: `scripts/probe_wheel_death.py`; regressão offscreen:
  `test_wheel_open_simulator_sector_leaves_a_healthy_app` (clique real via QTest +
  `appmod.__dict__` íntegro).
