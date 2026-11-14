# DuckDesk

Um Microduck virtual para Windows. O pato é simulado com física de verdade (MuJoCo) e se move
com **as mesmas redes neurais (políticas ONNX) que rodam no robô real** da Pollen Robotics /
Hugging Face.

Dois modos no mesmo app:

| Modo | O que é |
|---|---|
| **Simulador** | Janela 3D com menus. Você dirige o pato pelo teclado, aciona comportamentos (sentar, bicar o chão, cambalhota, chute) e testa políticas novas. |
| **Mascote** | O pato sai da janela e passa a andar **sozinho sobre a barra de tarefas do Windows**, com fundo transparente, sempre por cima das outras janelas. |

Do simulador, o menu **Modo → Enviar para a barra de tarefas** leva o pato para o modo mascote.
Pelo ícone na bandeja do sistema (ou com duplo clique no pato), ele volta para o simulador.

> **Projeto não oficial.** Não tem vínculo com a Pollen Robotics nem com a Hugging Face. Usa o
> software aberto deles nos termos das licenças: veja [docs/07-licencas.md](docs/07-licencas.md).
> **Uso não comercial**, por causa da licença dos modelos 3D.

## Status

Fase de especificação. O código será escrito pelo Devin, seguindo [AGENTS.md](AGENTS.md) e o
plano em [docs/08-plano-de-tarefas.md](docs/08-plano-de-tarefas.md). A revisão é feita contra
[docs/09-checklist-revisao.md](docs/09-checklist-revisao.md).

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
