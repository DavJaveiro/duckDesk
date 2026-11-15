# DuckDesk

[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![MuJoCo 3.10](https://img.shields.io/badge/MuJoCo-3.10-0A6EBD)](https://mujoco.org/)
[![ONNX Runtime 1.24](https://img.shields.io/badge/ONNX_Runtime-1.24-005CED?logo=onnx&logoColor=white)](https://onnxruntime.ai/)
[![NumPy 2.4](https://img.shields.io/badge/NumPy-2.4-013243?logo=numpy&logoColor=white)](https://numpy.org/)
[![BAM](https://img.shields.io/badge/BAM-atuador_XL330-6E4C9E)](https://github.com/Rhoban/bam)
[![PySide6 (Qt 6)](https://img.shields.io/badge/PySide6-Qt_6-41CD52?logo=qt&logoColor=white)](https://doc.qt.io/qtforpython-6/)
[![uv](https://img.shields.io/badge/uv-gerenciador-DE5FE9?logo=uv&logoColor=white)](https://docs.astral.sh/uv/)
[![PyInstaller](https://img.shields.io/badge/PyInstaller-empacotamento-2F6DB5)](https://pyinstaller.org/)
[![Inno Setup](https://img.shields.io/badge/Inno_Setup-instalador-264B99)](https://jrsoftware.org/isinfo.php)
[![Windows 10/11](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D6)](https://www.microsoft.com/windows)
[![Licença Apache 2.0](https://img.shields.io/badge/Licen%C3%A7a-Apache_2.0-D22128?logo=apache&logoColor=white)](LICENSE)

Um Microduck virtual para Windows. O pato é simulado com física de verdade (MuJoCo) e se move
com **as mesmas redes neurais (políticas ONNX) que rodam no robô real** da Pollen Robotics /
Hugging Face.

Dois modos no mesmo app:

| Modo | O que é |
|---|---|
| **Simulador** | Janela 3D com menus. Você dirige o pato pelo teclado, aciona comportamentos (sentar, bicar o chão, cambalhota, chute) e testa políticas novas. |
| **Mascote** | O pato sai da janela e passa a andar **sozinho sobre a barra de tarefas do Windows**, com fundo transparente, sempre por cima das outras janelas. |

Do simulador, o menu **Modo → Enviar para a barra de tarefas** leva o pato para o modo mascote.
Pelo ícone na bandeja do sistema (ou "Abrir simulador" na roda de ações), ele volta para o
simulador; o duplo clique no pato o faz grasnar — e o grasno é a **voz gerada da sua
instalação** (`chirp`, como no pato real: cada instalação tem uma voz só sua, derivada de
uma semente; veja ADR-0011).
Com o pato na barra, o **botão direito sobre ele** abre uma roda de ações (bicar, sentar,
cambalhota, empurrar, pausar, piloto automático, voltar ao simulador e sair); o menu completo
continua no ícone da bandeja, inclusive na área de ícones ocultos.

A voz cobre os outros momentos também: o pato cumprimenta ao acordar (`greet`), bicar toca
`peck` (que também é o "tchau" ao sair), bocejo toca `coo`, olhadas curiosas tocam
`inquire`, queda toca `alarm`, e segurá-lo faz "uêê" (`wheee`). **"Voz do pato"** na
bandeja liga/desliga ao vivo.

Ele também **obedece comandos falados em português**, reconhecidos offline no PC
(Vosk + gramática restrita — ADR-0012): "senta", "levanta", "anda", "vem",
"cambalhota", "bica", "chuta", "pia", "dorme", "olha", "tchau". **"Ouvido do
pato"** na bandeja liga/desliga o microfone ao vivo.

> **Projeto não oficial.** Não tem vínculo com a Pollen Robotics nem com a Hugging Face. Usa o
> software aberto deles nos termos das licenças: veja [docs/07-licencas.md](docs/07-licencas.md).
> **Uso não comercial**, por causa da licença dos modelos 3D.

## Instalação (Windows)

1. Baixe `DuckDesk-Setup-<versão>.exe` da página de releases.
2. Execute o instalador. Ele instala **por usuário**, sem pedir administrador, em
   `%LOCALAPPDATA%\Programs\DuckDesk`, e cria o grupo **DuckDesk** no Menu Iniciar.
3. Na primeira execução, o Windows pode mostrar o aviso **"O Windows protegeu o computador"**
   (SmartScreen): o executável é assinado apenas com certificado autoassinado. Clique em
   **"Mais informações" → "Executar assim mesmo"**.
4. Para abrir com o Windows, ative **"Iniciar com o Windows"** no menu da bandeja do sistema.

Desinstalação: "Adicionar ou remover programas" → DuckDesk, ou
`%LOCALAPPDATA%\Programs\DuckDesk\unins000.exe`.

## Limitações conhecidas

- **Windows 10/11 x64 apenas.** Não há versão para macOS, Linux ou ARM.
- **Só CPU.** A física e as redes neurais rodam sem GPU; o pato anda a ~55 % da velocidade
  comandada (comportamento da política `velstand` sob o modelo de atuador BAM em CPU — o
  mesmo resultado do `infer_policy.py` oficial, medido em M1).
- **Barra de tarefas na parte de baixo.** No modo mascote, a barra precisa estar visível e na
  borda inferior; com barra no topo/lateral ou com ocultação automática, o pato usa a borda
  inferior da área de trabalho como referência.
- **Apps em tela cheia.** O mascote se esconde enquanto um app está em tela cheia e volta
  quando ele sai.
- **Políticas 61D apenas.** Arquivos ONNX de outros formatos são recusados.
- **Uso não comercial** (licença CC BY-NC-SA 4.0 das malhas 3D). O executável é autoassinado;
  o aviso do SmartScreen é esperado.

## Documentação

| Documento | Conteúdo |
|---|---|
| [AGENTS.md](AGENTS.md) | Regras para quem escreve o código (Devin). **Leia primeiro.** |
| [docs/01-visao-e-escopo.md](docs/01-visao-e-escopo.md) | Objetivos, o que está fora do escopo, requisitos não funcionais |
| [docs/02-arquitetura.md](docs/02-arquitetura.md) | Módulos, laço principal, fluxo de dados, estrutura de pastas |
| [docs/03-contrato-politicas.md](docs/03-contrato-politicas.md) | **O contrato com as redes neurais** (observação 61D, ações, pose padrão, atuador BAM, 50 Hz). A parte mais delicada. |
| [docs/04-modo-simulador.md](docs/04-modo-simulador.md) | Janela 3D: câmera, controles, menus, HUD |
| [docs/05-modo-mascote.md](docs/05-modo-mascote.md) | Pato na barra de tarefas: janela transparente, mapeamento de coordenadas, piloto automático |
| [docs/06-instalador.md](docs/06-instalador.md) | Empacotamento (PyInstaller + Inno Setup) |
| [docs/07-licencas.md](docs/07-licencas.md) | Licenças, atribuição, versões fixadas do upstream |
| [docs/08-plano-de-tarefas.md](docs/08-plano-de-tarefas.md) | Marcos M0–M7, com critérios de aceite |
| [docs/09-checklist-revisao.md](docs/09-checklist-revisao.md) | O que a revisão vai conferir em cada entrega |
| [docs/adr/](docs/adr/) | Registro das decisões de arquitetura |

## Stack

Python 3.12 · MuJoCo 3.10 · onnxruntime · BAM (modelo de atuador XL330) · PySide6 (Qt) ·
PyInstaller · Inno Setup. As versões fixadas e os motivos estão em
[docs/02-arquitetura.md](docs/02-arquitetura.md).

## Desenvolvimento (depois do M0)

```bash
uv sync
```

```bash
uv run python scripts/fetch_assets.py
```

```bash
uv run duckdesk
```

`Ctrl+C` no terminal fecha o aplicativo (passa pela saída normal: salva o
modo, a geometria da janela e a posição do pato).

```bash
uv run pytest
```

## Licença

O código do DuckDesk é licenciado sob a [Apache License 2.0](LICENSE). Os arquivos de terceiros
incluídos no instalador mantêm as licenças deles. As malhas 3D do Microduck são
CC BY-NC-SA 4.0 (uso não comercial). Detalhes em [docs/07-licencas.md](docs/07-licencas.md).

## Pasta `vendor/`

Clones de referência dos repositórios oficiais (`microduck`, `microduck_rl`), usados só para
leitura e para o teste de paridade. A pasta fica fora do git (`.gitignore`). O app nunca importa
nada dela em tempo de execução.
