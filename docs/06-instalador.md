# 06: Instalador

## Resultado

`DuckDesk-Setup-<versão>.exe`, que:

- instala **por usuário**, sem administrador, em `%LOCALAPPDATA%\Programs\DuckDesk`;
- cria um atalho no Menu Iniciar ("DuckDesk") e, opcionalmente, um na Área de Trabalho;
- tem uma caixa marcável "Iniciar com o Windows" (desmarcada por padrão), que grava a mesma
  chave que o app usa (05 §7);
- mostra uma página de licença com `THIRD_PARTY_NOTICES.md` (convertido para `.txt` ou `.rtf`);
- registra o desinstalador em "Aplicativos instalados". O desinstalador remove a pasta do app e
  a chave `Run`, mas **pergunta** antes de apagar `%APPDATA%\DuckDesk` (configurações);
- funciona sem internet.

## Passo 1: PyInstaller (`installer/duckdesk.spec`)

- Modo **onedir** (não onefile: abre mais rápido e o antivírus reclama menos).
- `console=False`, ícone `assets/icons/duckdesk.ico` (desenho próprio, nada da Pollen).
- Inclua como dados:
  - `assets/upstream/**` (XML + STL);
  - `assets/policies/v10/**` (ONNX + manifesto);
  - `assets/icons/**`, `assets/lock.json`, `THIRD_PARTY_NOTICES.md` e as licenças em
    `licenses/`.
- Dependências binárias que costumam faltar e precisam ser conferidas no build:
  - `mujoco`: a DLL e a pasta `plugin/`; `glfw` (`glfw3.dll`);
  - `onnxruntime`: `onnxruntime.dll` e `onnxruntime_providers_shared.dll`;
  - PySide6: o plugin de plataforma `platforms/qwindows.dll` e `styles/`.
- Exclua o que não usamos: `tkinter`, módulos de teste do numpy e os módulos Qt pesados
  (WebEngine, Multimedia, QML, 3D). Use `PySide6-Essentials`.
- Os caminhos dos assets em tempo de execução passam por `duckdesk.assets`, que resolve dev ×
  congelado (`sys.frozen`, `sys._MEIPASS`). Nenhum caminho fixo no código.

## Passo 2: Inno Setup (`installer/duckdesk.iss`)

- `PrivilegesRequired=lowest`, `DefaultDirName={localappdata}\Programs\DuckDesk`,
  `ArchitecturesAllowed=x64compatible` e `ArchitecturesInstallIn64BitMode=x64compatible`.
- `AppId` fixo (gere um GUID uma vez e nunca mude), `AppName=DuckDesk`, versão lida de
  `pyproject.toml` pelo script de build.
- Idioma: português do Brasil (`compiler:Languages\BrazilianPortuguese.isl`).
- Na instalação por cima (atualização), feche o app antes (`CloseApplications=yes`, ou um mutex
  com o mesmo nome da instância única do app).

## Passo 3: script de build

`scripts/build_installer.ps1`, de ponta a ponta numa máquina limpa:

```
uv sync --frozen
uv run python scripts/fetch_assets.py --verify
uv run pyinstaller installer/duckdesk.spec --noconfirm --clean
& "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe" installer\duckdesk.iss
```

No fim, imprime o caminho do `.exe`, o tamanho e o SHA-256.

## Assinatura

Fora do escopo da v1. O SmartScreen vai mostrar "O Windows protegeu o computador" → "Mais
informações" → "Executar assim mesmo". Documente isso no README do release.

## Critérios de aceite (M6)

1. Build de ponta a ponta com o script, numa VM ou máquina Windows 11 **sem Python
   instalado**.
2. Instala sem pedir administrador. Abre do Menu Iniciar. Os dois modos funcionam. Funciona com
   a rede desligada.
3. Tamanho do instalador ≤ 350 MB. Pasta instalada ≤ 900 MB.
4. A desinstalação remove tudo, exceto as configurações, se o usuário escolher mantê-las.
5. "Iniciar com o Windows" funciona: reinicie a VM e confira que o pato aparece.
6. Relatório com o tamanho, o SHA-256 e os prints de cada etapa.
