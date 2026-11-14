# 08: Plano de tarefas (marcos M0–M7)

Cada marco é um branch e um PR, na ordem abaixo. Um marco só começa depois que o anterior for
aprovado na revisão, exceto quando indicado. Cada PR traz `docs/relatorios/Mx.md` (veja
AGENTS.md). Mídias: GIF ou MP4 de até **10 MB** cada, em `docs/relatorios/midia/`.

Todo critério marcado como **[duro]** reprova o marco se falhar. Os outros são metas de
sanidade: se falharem, explique com dados se é limitação da política (confirme rodando o mesmo
cenário no `infer_policy.py`) ou bug nosso.

---

## M0: Base do projeto (`m0-bootstrap`)

- `pyproject.toml` completo (o esqueleto já existe), `uv.lock`, `.python-version` = 3.12.
- Esqueleto de `src/duckdesk/` conforme 02, com o ponto de entrada `duckdesk` (pode só abrir
  uma janela vazia).
- `scripts/fetch_assets.py` (07): baixa os commits e a tag fixados, copia só o necessário e gera
  `assets/lock.json`; `--verify` confere.
- `THIRD_PARTY_NOTICES.md` e `licenses/` com os textos completos (Apache-2.0, CC BY-NC-SA 4.0,
  MIT, LGPLv3, BSD-3).
- `ruff` configurado; `pytest` configurado com os marcadores `unit`, `parity` e `behavior`.
- CI no GitHub Actions em `windows-latest`: `uv sync --frozen`, `fetch_assets.py --verify`,
  `ruff` e `pytest -m "unit or parity"`.
- Clonar o upstream em `vendor/` também é tarefa do `fetch_assets.py` (`--vendor`), nos mesmos
  commits.

**Aceite**
1. **[duro]** `uv sync` numa máquina limpa com Windows 11 instala tudo, e
   `uv run python -c "import mujoco, onnxruntime, bam, PySide6"` passa.
2. **[duro]** As versões de `mujoco`, `onnxruntime` e `numpy` no `uv.lock` são as de 02.
3. **[duro]** `fetch_assets.py --verify` passa; o `assets/` tem só o necessário.
4. **[duro]** Teste: `scene_ball.xml` carrega pelo caminho do BAM; `model.nu == 14`; as 6
   políticas do escopo têm entrada `[1,61]` e saída `[1,14]`.
5. CI verde.

---

## M1: Núcleo sem janela (`m1-headless-core`)

- `policy/contract.py`, `policy/manager.py`, `policy/validate.py`, `sim/core.py`,
  `sim/clock.py` e o watchdog (02).
- `tests/parity/`: o teste de paridade de 03 §10.
- `tests/behavior/`: os ensaios abaixo, sem janela.
- `scripts/headless_run.py --policy walk --script <roteiro.json> --seconds N`: imprime as
  métricas e, opcionalmente, grava um MP4 pela renderização offscreen (para o relatório).

**Aceite**
1. **[duro]** Paridade: os 3 roteiros de 03 §10 dentro das tolerâncias.
2. **[duro]** Nenhum import de PySide6 em `sim/`, `policy/` ou `brain/` (teste que confere).
3. **[duro]** Tempo por passo de controle: média e p99 medidos em 3000 passos e relatados.
   Meta: p99 ≤ 5 ms.
4. Ensaios de comportamento, com semente fixa (cada um relata o valor medido):

| Ensaio | Meta |
|---|---|
| Em pé 10 s, comando zero | inclinação < 10°; deriva em x e em y < 0.05 m |
| Andar vx = 0.2 por 8 s | não cai; vx médio nos últimos 5 s entre 0.12 e 0.28 |
| Girar wz = 1.0 por 4 s | taxa de guinada média entre 0.6 e 1.4 rad/s |
| Sentar 5 s → levantar | o tronco desce ≥ 3 cm sentado; depois da subida, volta ao `walk` e anda |
| Bicar o chão | termina em pé, de volta ao `walk` |
| Cambalhota (5 tentativas, pequena perturbação inicial) | termina em pé em ≥ 4 de 5 |
| Chute esq./dir. (5 cada) | a bola anda ≥ 0.3 m em ≥ 4 de 5 |
| Empurrão forte (até cair) | a velstand levanta sozinha em ≤ 6 s, em ≥ 4 de 5 |

5. Medir `H_m` (altura do pato em pé) e registrar no relatório.
6. Opcional: investigação da ADR-0001 (configuração do `robotd` × a do `infer_policy`).

---

## M2: Cérebro e regras (`m2-brain`)

- `brain/commands.py`, `brain/keyboard.py` (independente do Qt), `brain/autopilot.py`.
- O motor de regras de 03 §8, centralizado (um lugar só decide se um pedido é aceito).
- `scripts/headless_run.py --autopilot --seconds 600 --x-range -2.5 2.5`.

**Aceite**
1. **[duro]** Testes de unidade das regras: cada combinação estado × pedido do 03 §8 tem um
   teste.
2. **[duro]** Testes do piloto automático com RNG fixo: transições, controle de rumo (o erro de
   y converge), virada nas bordas.
3. **[duro]** 10 min de piloto automático sem janela: nunca sai da faixa de x; |y| < 0.3 m;
   nenhum estado preso por mais de 60 s; relatório com o histograma do tempo em cada estado e
   quantas quedas e resets houve.

---

## M3: Modo simulador (`m3-simulator`)

Tudo de 04, exceto o envio para a barra de tarefas (o item de menu existe, mas fica
desabilitado até o M5).

**Aceite**
1. **[duro]** Vídeo de 60–90 s: andar, girar, passo lateral, sentar/levantar, bicar,
   cambalhota, os dois chutes, empurrão e recuperação, sliders de cabeça e corpo.
2. **[duro]** Carregar um ONNX inválido (feito no teste, com outra forma) mostra uma mensagem em
   português e não derruba o app; carregar a própria `velstand.onnx` pelo menu funciona.
3. **[duro]** Fechar a janela só esconde; "Sair" encerra o processo (confira que não sobra
   `python.exe` nem `duckdesk.exe`).
4. Fps de renderização e CPU relatados, em 1280×800.

---

## M4: App, bandeja e configurações (`m4-app-shell`)

- `AppController`, `ui/tray.py`, `ui/about.py`, `settings.py`, `platform/autostart.py`,
  instância única.

**Aceite**
1. **[duro]** Abrir o app duas vezes traz a instância existente para frente, em vez de abrir
   outra.
2. **[duro]** As configurações persistem; um `settings.json` corrompido não derruba o app
   (volta ao padrão e registra no log).
3. **[duro]** "Iniciar com o Windows" escreve e apaga a chave certa (teste com `winreg`).
4. **[duro]** A tela "Sobre" tem o texto de 07.
5. Log em `%APPDATA%\DuckDesk\logs\duckdesk.log`, com rotação de 5 × 1 MB.

---

## M5: Modo mascote (`m5-mascot`)

Tudo de 05 e a troca nos dois sentidos (04 §7, 05 §8).

**Aceite**
1. **[duro]** Testes de unidade do mapeamento (05 §3) com geometrias de tela sintéticas: 100 %,
   125 % e 150 % de escala; barra embaixo, oculta e no topo.
2. **[duro]** Vídeo mostrando os 6 critérios visuais de 05 §10 (pode ser mais de um vídeo).
3. **[duro]** A troca simulador → mascote → simulador funciona 20 vezes seguidas sem vazar
   memória (RSS final ≤ RSS inicial + 30 MB) e sem erro no log.
4. **[duro]** CPU no modo mascote ≤ 15 % de um núcleo (média de 60 s, piloto automático
   ligado); relatório com o modelo da CPU.
5. Print com 125 % ou 150 % de escala mostrando os pés na borda da barra.

---

## M6: Instalador (`m6-installer`)

Tudo de 06. Critérios de aceite em 06.

---

## M7: Acabamento (`m7-hardening`)

- `scripts/measure_perf.py`: amostra CPU e RSS do processo a cada 5 s e grava CSV.
- Teste de 2 h no modo mascote, com o instalador da M6.
- README de release (como instalar, o aviso do SmartScreen, limitações conhecidas).

**Aceite**
1. **[duro]** 2 h sem travar; RSS final ≤ RSS aos 5 min + 10 %; CSV e gráfico no relatório.
2. **[duro]** Tempo de abertura ≤ 6 s (média de 5 aberturas a frio).
3. Lista de problemas conhecidos e ideias para a v2.
