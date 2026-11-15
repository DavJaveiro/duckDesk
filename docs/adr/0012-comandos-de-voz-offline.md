# ADR-0012: Comandos de voz pt-BR offline — Vosk + gramática restrita

**Status:** aceita (2026-11-14, pós-M7)

## Contexto

O dono pediu falar no microfone e o pato obedecer comandos ("senta" → senta).
Primeiro, o fato: **o MicroDuck real não entende palavras** — o `pet-detect`
(`vendor/microduck/pet-detect/`) é uma CNN de ~20 KB sobre log-mel a 16 kHz que
detecta *cafuné* na cabeça, e o `autod` classifica sons ambiente em `Noise`/
`Voice` por heurística RMS. O robô reage a *sons*; nenhum reconhecimento de
fala existe no upstream. Comandos falados são, portanto, um recurso novo do
DuckDesk — mas natural: as ações já têm nomes e caminhos (`Request`, piloto,
comandos de cabeça).

Restrições do projeto: sem rede em runtime (regra 7 — corta APIs de nuvem),
CPU-only (regra 5 — corta Whisper/torch) e uma única thread Qt (ADR-0003).

## Decisão

**Vosk `vosk-model-small-pt-0.3`** (Apache-2.0, alphacephei.com, ~31 MB zip) com
**gramática restrita** — o `KaldiRecognizer` só reconhece as ~30 frases de
`brain/voice_commands.py`; ditado livre não existe, o que aumenta precisão e
zera o risco de o pato "obedecer" uma conversa alheia.

Pipeline: `sounddevice.RawInputStream` (mic padrão, mono, 16 kHz) →
`AcceptWaveform` → frase reconhecida → sinal Qt `DuckEars.heard` →
`AppController.on_voice_command` → o **mesmo caminho dos cliques e teclas**
(`on_request`, `on_autopilot_toggled`, impulso de `twist`, `voice.play`) —
nenhum comando toca a ponte da política (regra 1).

Mapeamento (`voice_commands.py`, testável sem microfone): `senta`/`levanta` →
SIT/STAND; `anda`/`vai` → impulso de avanço de 2 s no simulador ou piloto no
mascote; `para`/`quieto` → cancela o impulso / desliga o piloto; `vem` → impulso
maior (3 s) / piloto; `pirueta`/`cambalhota`/`rola`/`mortal` → ROLL; `bica` →
PECK; `chuta` → KICK alternando pernas (como o duplo clique); `pia`/`grasna`/
`fala` → `chirp`; `dorme` → SIT + bocejo + `coo`; `olha` → olhada + `inquire`;
`pato`/`oi pato` → ack `inquire`; `tchau`/`adeus` → PECK de despedida (ritual
do robotd). Todo comando aceito pisca o bico (ack "ouvi").

**Threads:** o callback de áudio mora na thread interna do PortAudio — ele
aceita blocos (~ms) e só emite o sinal; todo trabalho Qt/sim continua na thread
Qt. É a exceção sancionada à ADR-0003: nenhuma thread *nova* é criada pela app
e o reconhecimento em si (Vosk processa 0,5 s de áudio por callback) também
roda lá dentro — medido em ms por bloco na máquina de referência.

**Modelo como asset:** o zip é pinado em `assets/lock.json` (sha256
`6e1ce909…`), baixado só por `scripts/fetch_assets.py` e empacotado pelo
instalador; em runtime o app extrai uma vez para `%APPDATA%/DuckDesk/vosk/`
(o diretório instalado é read-only). Sem modelo, sem microfone ou com
`settings["ears"]` falso → o pato fica surdo, sem erro e sem custo.

**Controle do usuário:** "Ouvido do pato" na bandeja (ligado por padrão)
agarra/solta o microfone ao vivo e persiste em `settings["ears"]`. O Windows
pode ainda exigir permissão de microfone por app — fora do nosso alcance; o
degrade é mudo como nos demais caminhos.

## Alternativas descartadas

- **Windows `Media.SpeechRecognition` (WinRT):** zero modelo embutido e
  gramática de lista nativa — mas `SpeechRecognizer()` falhou com
  `0x800455a0` (`SPERR_WINRT_INTERNAL_ERROR`) até no construtor padrão neste
  ambiente, inviabilizando qualquer teste; exigiria ainda o pacote de fala
  pt-BR do Windows em cada máquina alvo. Registrado em `duvidas.md`.
- **SAPI 5.4:** sem engine SAPI pt-BR instalada aqui; API COM pesada.
- **whisper.cpp:** transcrição livre é overkill para ~30 comandos — modelo
  maior, latência maior, e ditado livre é exatamente o que *não* queremos.
- **Portar o pet-detect do upstream:** detecção de cafuné pressupõe microfone
  *no corpo do pato* — num desktop o mic ouve o ambiente; soaria como copiar o
  sensor sem o fenômeno. Fica como ideia para "bata na mesa → ele acorda".

## Consequências

- Novas deps de runtime: `vosk` + `sounddevice` (CPU, offline — regras 5 e 7
  respeitadas); `installer/duckdesk.spec` coleta `vosk` e `_sounddevice_data`
  (DLLs nativas).
- Instalador cresce ~33 MB (o zip do modelo); extração única de ~45 MB no
  perfil do usuário no primeiro uso.
- Ouvido ligado consome a entrada de áudio padrão — conflita com apps que
  exigem mic exclusivo; desligar na bandeja resolve ao vivo.
- Testes: `tests/unit/test_ears.py` (gramática, `ensure_model`, ciclo de vida
  com `sd`/Vosk falsos, emissão de `heard`) e `test_voice_wiring.py` (dispatch
  de cada comando + toggle da bandeja) — nenhum teste precisa de microfone.
