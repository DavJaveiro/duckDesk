# 07: Licenças, atribuição e versões fixadas do upstream

> Isto não é parecer jurídico. É o resumo do que os arquivos de licença do upstream dizem e de
> como o projeto vai cumpri-los.

## O que usamos e sob qual licença

| Componente | Origem | Licença | Vai no instalador? |
|---|---|---|---|
| Descrição do robô (MJCF `.xml`, `config_mjcf_*.json`) | `pollen-robotics/microduck_rl` | Apache-2.0 | Sim |
| **Malhas 3D** (`robot/microduck/assets/*.stl`) | `pollen-robotics/microduck_rl` | **CC BY-NC-SA 4.0** | Sim |
| Lógica portada do `infer_policy.py` | `pollen-robotics/microduck_rl` | Apache-2.0 | Sim (como código derivado) |
| Políticas `*.onnx` + `manifest.json` | `pollen-robotics/microduck-policies` (Hugging Face Hub), tag `v10` | Apache-2.0 | Sim |
| BAM (`better-actuator-models`) | `Rhoban/bam` | Apache-2.0 | Sim |
| MuJoCo | Google DeepMind | Apache-2.0 | Sim |
| ONNX Runtime | Microsoft | MIT | Sim |
| PySide6 / Qt | The Qt Company | LGPLv3 (Qt) / LGPLv3 (PySide6) | Sim, como DLLs separadas (onedir), sem modificação |
| NumPy | NumPy | BSD-3-Clause | Sim |

### Consequências

1. **Uso não comercial.** As malhas são CC BY-NC-SA 4.0. Um instalador que as inclui não pode
   ser vendido nem usado comercialmente. Para um uso comercial, seria preciso pedir licença à
   Pollen Robotics ou trocar as malhas por um modelo próprio.
2. **Atribuição obrigatória** (texto do `LICENSE-MODELS.md` do upstream): dar crédito à
   **Pollen Robotics**, linkar `https://github.com/pollen-robotics/microduck_rl`, linkar a
   licença CC BY-NC-SA 4.0 e dizer se os arquivos foram modificados (não serão).
3. **ShareAlike:** se um dia modificarmos ou convertermos as malhas (por exemplo, decimar para
   o mascote ficar mais leve), o resultado também é CC BY-NC-SA 4.0.
4. **Apache-2.0:** manter os avisos de copyright e o texto da licença, e indicar no código
   portado que ele deriva de `infer_policy.py` (cabeçalho de arquivo com origem e commit).
5. **LGPL (Qt):** usar as DLLs do Qt sem modificar e permitir a substituição. O modo onedir já
   permite. Incluir o texto da LGPL em `licenses/`.
6. **Nome e marca:** "Microduck", "Pollen Robotics" e "Hugging Face" são de seus donos. O app se
   chama **DuckDesk**, usa ícone próprio e diz na tela "Sobre" que é **não oficial**.

### Licença do código do DuckDesk

**Apache-2.0** (decisão do dono do projeto em 2026-11-14), no arquivo [LICENSE](../LICENSE) na
raiz. Vale para o código do DuckDesk. Os arquivos do upstream mantêm as licenças deles (tabela
acima): em especial, as malhas continuam CC BY-NC-SA 4.0, então o **instalador** como um todo
continua sendo de uso não comercial.

## Tela "Sobre" (texto mínimo)

> DuckDesk: um Microduck virtual para Windows. Projeto não oficial, sem vínculo com a Pollen
> Robotics ou a Hugging Face.
>
> Modelo 3D do Microduck © Pollen Robotics, licenciado sob CC BY-NC-SA 4.0
> (creativecommons.org/licenses/by-nc-sa/4.0), de github.com/pollen-robotics/microduck_rl, sem
> modificações. Descrição do robô e políticas de controle © Pollen Robotics, Apache-2.0.
> Atuador BAM © Rhoban, Apache-2.0. MuJoCo © Google DeepMind, Apache-2.0. Qt/PySide6, LGPLv3.
>
> Uso não comercial.

E um botão "Ver avisos completos" que abre o `THIRD_PARTY_NOTICES.md`.

## Versões fixadas

| Item | Valor |
|---|---|
| `pollen-robotics/microduck_rl` | commit `0daab160d3fb1c2cbaba16a4a19052f36709dd9e` (branch `develop`, 2026-11-10) |
| `pollen-robotics/microduck` | commit `094d4bb4af31ec181156e1ea772437fdd7a55978` (2026-11-13), **só referência** (`robotd/src/control.rs`, docs) |
| `pollen-robotics/microduck-policies` | tag **`v10`** (a mesma fixada em `[workspace.metadata.policies]` no `Cargo.toml` do `microduck`) |
| `Rhoban/bam` | commit `57d13ead53206a6bf0db3d66f86506ae8c2ce01a` (branch `mjlab_frictionloss`) |

`scripts/fetch_assets.py` baixa exatamente esses commits e essa tag, copia os arquivos para
`assets/` e escreve `assets/lock.json` com o SHA-256 de cada arquivo. Com `--verify`, só confere
os hashes e falha se algo não bater. **Copie só o necessário:** de `robot/microduck/`, as cenas
`scene.xml` e `scene_ball.xml`, os XMLs incluídos por elas (siga os `<include>`
recursivamente) e as malhas referenciadas. Nada de `.part`, nem os assets da bancada de teste.

`assets/upstream/` e `assets/policies/` **não vão para o git** (`.gitignore`). Só o
`assets/lock.json` é versionado. O CI e o build do instalador rodam
`fetch_assets.py --verify`, que baixa e confere os hashes. Assim o repositório não redistribui
as malhas por conta própria; só o instalador as inclui, com a atribuição.
