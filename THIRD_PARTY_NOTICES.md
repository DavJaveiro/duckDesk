# Avisos de terceiros

O DuckDesk é um projeto **não oficial**, sem vínculo com a Pollen Robotics ou a Hugging
Face. Esta página lista os componentes de terceiros distribuídos com o aplicativo e as
licenças correspondentes. Os textos completos de cada licença estão em [`licenses/`](licenses/).

O código do DuckDesk em si é Apache-2.0 (veja [LICENSE](LICENSE)). Como as malhas 3D do
Microduck são CC BY-NC-SA 4.0, o instalador como um todo é de **uso não comercial**.

## Componentes

### Descrição do robô Microduck (MJCF) — Apache-2.0

Arquivos `.xml` e `config_mjcf_*.json` em `assets/upstream/microduck_rl/`, do repositório
`pollen-robotics/microduck_rl` (commit `0daab160d3fb1c2cbaba16a4a19052f36709dd9e`).

Copyright Pollen Robotics. Licenciado sob a Apache License 2.0 —
[licenses/Apache-2.0.txt](licenses/Apache-2.0.txt). Arquivos distribuídos sem modificação.

### Malhas 3D do Microduck — CC BY-NC-SA 4.0

Arquivos `.stl` em `assets/upstream/microduck_rl/robot/microduck/assets/`, do mesmo
repositório.

Modelo 3D do Microduck © Pollen Robotics, licenciado sob
[Creative Commons Atribuição-NãoComercial-CompartilhaIgual 4.0 Internacional](https://creativecommons.org/licenses/by-nc-sa/4.0/)
(texto legal em [licenses/CC-BY-NC-SA-4.0.txt](licenses/CC-BY-NC-SA-4.0.txt)),
obtido de https://github.com/pollen-robotics/microduck_rl, **sem modificações**.

O uso comercial destes arquivos é proibido pela licença. Adaptações, se um dia forem
feitas, também deverão ser licenciadas sob CC BY-NC-SA 4.0 com a mesma atribuição.

### Políticas de controle (ONNX) — Apache-2.0

Arquivos `.onnx` e `manifest.json` em `assets/policies/v10/`, do repositório
`pollen-robotics/microduck-policies` no Hugging Face Hub, tag `v10`.

Copyright Pollen Robotics. Licenciado sob a Apache License 2.0 —
[licenses/Apache-2.0.txt](licenses/Apache-2.0.txt).

### Síntese de voz portada — Apache-2.0

`src/duckdesk/platform/voice/` deriva do daemon `sounds/` do repositório
`pollen-robotics/microduck` (RNG xoshiro256++/splitmix64, DSP a 48 kHz, personalidade
por semente, receitas de vocalização e o streaming do theremin), cada arquivo com
cabeçalho indicando a fonte original. O sintetizador original, por sua vez, é um porte
de `apirrone/microduck_sounds`.

Copyright Pollen Robotics. Licenciado sob a Apache License 2.0 —
[licenses/Apache-2.0.txt](licenses/Apache-2.0.txt).

### Lógica de inferência portada — Apache-2.0

Partes de `src/duckdesk/` derivam de `scripts/infer_policy.py` do repositório
`pollen-robotics/microduck_rl` (commit `0daab160d3fb1c2cbaba16a4a19052f36709dd9e`), cada
uma com cabeçalho indicando a origem.

Copyright Pollen Robotics. Licenciado sob a Apache License 2.0 —
[licenses/Apache-2.0.txt](licenses/Apache-2.0.txt).

### better-actuator-models (BAM) — Apache-2.0

Biblioteca `bam`, de `Rhoban/bam` (commit `62bd8ce12154340be97e06f7f41a0ca8f116d967`,
branch `mjlab_frictionloss`), instalada como dependência.

Copyright Rhoban. Licenciado sob a Apache License 2.0 —
[licenses/Apache-2.0.txt](licenses/Apache-2.0.txt).

### MuJoCo — Apache-2.0

Copyright Google DeepMind. Licenciado sob a Apache License 2.0 —
[licenses/Apache-2.0.txt](licenses/Apache-2.0.txt).

### ONNX Runtime — MIT

Copyright Microsoft Corporation. Licenciado sob a MIT License —
[licenses/MIT.txt](licenses/MIT.txt).

### Qt / PySide6 — LGPLv3

Copyright The Qt Company. Qt e PySide6 são licenciados sob a GNU Lesser General Public
License v3 — [licenses/LGPL-3.0.txt](licenses/LGPL-3.0.txt) (que incorpora a
[GPL-3.0](licenses/GPL-3.0.txt) por referência).

O DuckDesk usa as DLLs do Qt **sem modificação**, distribuídas como arquivos separados
no formato onedir: é possível substituí-las por outra build do Qt, conforme a LGPL exige.

### NumPy — BSD-3-Clause

Copyright NumPy Developers. Licenciado sob a BSD 3-Clause License —
[licenses/BSD-3-Clause.txt](licenses/BSD-3-Clause.txt).

### Som de grasno — fornecido pelo dono do projeto

Arquivo `assets/sounds/quack.mp3` (som de reserva quando a voz gerada está desligada,
05 §6, ADR-0011), fornecido pelo dono do projeto. **Atribuição/licença a confirmar** —
ver `docs/relatorios/duvidas.md`.

## Marcas

"Microduck", "Pollen Robotics" e "Hugging Face" são marcas de seus respectivos donos.
O DuckDesk usa nome e ícone próprios e se apresenta como projeto não oficial.
