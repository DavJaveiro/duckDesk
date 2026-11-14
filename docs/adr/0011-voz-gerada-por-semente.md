# ADR-0011: Voz gerada por semente — porte do daemon `sounds/` do upstream

**Status:** aceita (2026-11-14, pós-M7)

## Contexto

O MicroDuck real não tem TTS nem arquivos de som: o daemon `sounds/`
(`vendor/microduck/sounds/`, ele próprio um porte em Rust de `apirrone/microduck_sounds`
em numpy) **sintetiza proceduralmente** cada vocalização a 48 kHz. Uma semente derivada do
serial do hardware alimenta `Personality::from_seed`, que sorteia ~20 traços — registro,
inclinação harmônica, formante, nasalidade, quackiness, vibrato, warble, tempo — e assim
**cada robô tem uma voz só sua**, estável para sempre. As receitas (`voices.rs`) desenham
7 tags: `greet` (boot), `chirp` (grasno/gatilho), `peck` (bicada e "tchau"), `coo`
(soninho), `inquire` (curioso), `alarm` (queda) e `wheee` (passeio segurado, em
start/loop/end). Há ainda o **theremin** (`stream.rs`): um sintetizador contíguo cujo
tom acompanha a distância da mão, e o coro (chorale, fora de escopo — um pato só).

O dono escolheu "tudo + theremin" e pediu o `chirp` gerado no duplo clique em vez do MP3
(enviado por ele e usado desde então).

## Decisão

Porte arquivo a arquivo do daemon em `src/duckdesk/platform/voice/`:

| Módulo | Origem | Papel |
|---|---|---|
| `rng.py` | `sounds/src/rng.rs` | xoshiro256++ + splitmix64 + Box-Muller + CRC-32 (a voz **é** a sequência — nunca pode mudar) |
| `synth.py` | `sounds/src/synth.rs` | primitivas DSP 48 kHz em numpy (envolventes, oscilador harmônico, ruído rosa, int16) |
| `personality.py` | `sounds/src/personality.rs` | ~20 traços derivados da semente, ranges verbatim; `variant_rng` por CRC-32 |
| `voices.py` | `sounds/src/voices.rs` | as 7 receitas + `wheee_segments` (loop com crossfade na emenda) |
| `stream.py` | `sounds/src/stream.rs` | sintetizador contíguo por blocos (slew de tom/nível/boca, jitter e breath com carry) |
| `waveout.py` | — | `winmm waveOut` por ctypes para o streaming (QtMultimedia não existe no venv) |
| `__init__.py` | `sounds/src/lib.rs` | `seed_from_id`/`resolve_seed` (`DUCK_IDENTITY` primeiro), `VoiceBank` lazy + marca `.seed`, `envelope_of`, facade `Voice` |

Identidade do DuckDesk: `settings["voice_seed"]`, sorteada e persistida no primeiro boot
(o substituto do serial do SoC, que não existe num desktop); `DUCK_IDENTITY` continua
valendo como override de desenvolvimento. Desligável ao vivo por **"Voz do pato"** na
bandeja (`settings["voice"]`).

**Reprodução:** WAVs renderizados lazy num banco ao lado do `settings.json`
(`%APPDATA%/DuckDesk/voice/`), tocados com `winsound.PlaySound(..., SND_ASYNC)` em
arquivo — a limitação que mutou o primeiro grasno era só memória+async; arquivo funciona.
`wheee` toca o segmento de loop com `SND_LOOP` durante o arrasto e aterrissa com o
segmento `end` (o `start` foi fundido ao loop por não haver encadeamento no winsound).
O theremin bombeia blocos de 20 ms pela thread do Qt (regra 6/ADR-0003) para um anel de
buffers do `waveOut`.

**Eventos (mapeamento do `robotd/main.rs`):** `greet` ao entrar no mascote, `chirp` no
duplo clique (substitui o MP3, que vira fallback sem voz), `peck` na bicada e antes de
sair, `coo` no bocejo, `inquire` nas olhadas do IDLE (moeda ~15 %, para não virar
metrônomo) e na olhada por clique, `alarm` na queda (RECOVER), `wheee` no arrasto.
**Theremin:** cursor a menos de ~2 larguras de pato ergue uma nota cujo tom varre
geometricamente o alcance do pato (`hz_at` do `stream.rs`).

**Lip-sync:** `envelope_of` extrai os quadros RMS de 40 ms do WAV tocado (o mesmo
método que gerou `QUACK_ENV`), e `BeakAnimator.vocalise(frames)` generaliza o `quack()`
— qualquer vocalização abre o bico no ritmo do som (ADR-0010, composição por máximo
inalterada).

## Desvios conscientes (registrados também em `duvidas.md`)

- **f64 vs f32:** o Rust usa `f32` no sinal; o porte calcula em `f64` e só converte no
  fim — bit-paridade já seria impossível (libm difere), e o contrato que importa é
  "mesma semente, mesma voz", pinado nos testes.
- **`wheee` sem `start`:** winsound não encadeia "toca isto e depois faz loop naquilo";
  o arrasto entra direto no loop (que já carrega a subida por crossfade) e o `end` toca
  ao soltar. O pato em "passeio" curto faz "ui!" em vez de "uêêê~" — aceitável.
- **Coro fora de escopo:** `chorale/` precisa de partitura e de *vários* patos.
- **Theremin por cursor** (não por câmera/mão): sem câmera no desktop, a distância do
  cursor ao pato é o análogo da distância da mão.

## Alternativas descartadas

- **TTS neural / modelos de voz:** pesado, precisaria de runtime novo, e não é o que o
  pato real faz — o sintetizador procedural é mais leve, offline e fiel.
- **`QtMultimedia` para o theremin:** `PySide6.QtMultimedia` não está no venv
  (PySide6-Essentials); `waveOut` por ctypes cobre o streaming sem dependência nova.
- **Renderizar todo o banco no boot:** ~70 WAVs × síntese atrasaria a entrada; lazy por
  primeiro uso, com o marcador `<seed>:<versão>` regenerando só quando a voz muda.
- **MCI (mciSendString) para os WAVs:** funciona, mas `winsound` é stdlib, toca arquivo
  assíncrono, e corta o som anterior sozinho — exatamente a semântica das tags.

## Consequências

- Cada instalação soa diferente — "o seu pato tem uma voz só dele", como no hardware.
- Nenhum arquivo de som novo entra no instalador (só o `quack.mp3` de fallback, já
  empacotado): o banco mora no perfil do usuário e se auto-regenera.
- `Sair`/Ctrl+C toca o `peck` de despedida e atrasa o fechamento ~350 ms; a suíte e o
  SIGINT passam pelo mesmo caminho (`on_quit` → `_finish_quit`).
- Testes: `tests/unit/test_voice.py` (RNG pinado, CRC-32 do teste upstream, ranges de
  personalidade, receitas, banco/cache, fachada, theremin) e
  `tests/ui/test_voice_wiring.py` (greet/chirp/peck/coo/inquire/alarm/wheee/theremin).
- Custo de CPU: síntese lazy na entrada do mascote (~ms por tag); o theremin consome
  ~1–2 % de um núcleo enquanto toca.
