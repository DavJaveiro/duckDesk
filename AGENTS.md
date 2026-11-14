# AGENTS.md: instruções para o agente que implementa o DuckDesk (Devin)

Você vai escrever **todo o código** e **todos os testes** do DuckDesk. Outra pessoa (Claude) vai
revisar cada entrega contra esta documentação. Se a documentação estiver errada, ambígua ou
impossível de seguir, **pare e registre a dúvida** em `docs/relatorios/duvidas.md` em vez de
inventar uma solução. Desvios sem registro serão reprovados na revisão.

## Ordem de leitura

1. [docs/01-visao-e-escopo.md](docs/01-visao-e-escopo.md)
2. [docs/03-contrato-politicas.md](docs/03-contrato-politicas.md): a parte que mais quebra
3. [docs/02-arquitetura.md](docs/02-arquitetura.md)
4. O documento do marco em que você está trabalhando ([04](docs/04-modo-simulador.md), [05](docs/05-modo-mascote.md), [06](docs/06-instalador.md))
5. [docs/08-plano-de-tarefas.md](docs/08-plano-de-tarefas.md) e [docs/09-checklist-revisao.md](docs/09-checklist-revisao.md)

## Regras que não podem ser quebradas

1. **Não reescreva a ponte simulador ↔ rede neural de memória.** A construção da observação, a
   escala das ações, a pose padrão, o atuador BAM, o passo de 5 ms e a decimação 4 vêm de
   `microduck_rl/scripts/infer_policy.py` no commit fixado. Porte o código, cite a linha de
   origem em comentário e prove a equivalência com o **teste de paridade** (M1). Se algo
   parecer errado no upstream, registre em `duvidas.md`. Não "conserte" por conta própria.
2. **Só políticas de 61 entradas → 14 saídas.** Recuse qualquer ONNX com outro formato, com
   mensagem clara. Não existe "modo legado de 51D" neste projeto.
3. **Não modifique os arquivos do upstream** (MJCF `.xml`, malhas `.stl`, políticas `.onnx`).
   Se precisar mudar algo no modelo (por exemplo, esconder o chão no modo mascote), faça em
   tempo de execução via `mujoco.MjSpec` ou opções de renderização, nunca editando o arquivo.
4. **Versões fixadas.** Commits do upstream, tag das políticas e versões de pacotes estão em
   [docs/07-licencas.md](docs/07-licencas.md) e [docs/02-arquitetura.md](docs/02-arquitetura.md).
   Para mudar qualquer uma delas, registre o motivo num ADR novo em `docs/adr/`.
5. **Nada de torch, warp, mjlab ou CUDA** no app nem no instalador. O app roda só em CPU. O
   treino de políticas está fora do escopo (veja 01).
6. **Uma thread de simulação e de interface só** (a thread do Qt). Veja a ADR-0003. Não crie
   threads para física ou renderização sem um ADR aprovado.
7. **Sem rede em tempo de execução.** O app não baixa nada sozinho. Os assets vêm no instalador.
   Download só no script de desenvolvimento `scripts/fetch_assets.py`.
8. **Licenças.** Toda cópia de arquivo do upstream entra em `THIRD_PARTY_NOTICES.md`, e a tela
   "Sobre" mostra a atribuição exigida. Não use logotipos nem imagens da Pollen ou da Hugging
   Face.
9. **Textos da interface em português do Brasil.** Código, nomes de arquivos, identificadores,
   commits e comentários em inglês.

## Fluxo de trabalho

- Um **branch por marco** (`m0-bootstrap`, `m1-headless-core`, ...) e um **PR por marco**, na
  ordem de [08](docs/08-plano-de-tarefas.md). Não junte marcos num PR só.
- **Todo PR aponta para `main`.** Nunca abra um PR contra o branch de outro marco: na primeira
  rodada, os PRs #13–#18 foram mesclados uns nos outros e a `main` ficou parada no M1. Comece
  cada marco a partir da `main` atualizada.
- **Não mescle sem revisão.** Abra o PR e espere a aprovação; dúvidas "aguardando revisão"
  bloqueiam a mesclagem.
- **Evidência visual é olhada inteira.** Um critério como "pés na borda" não vale se a mesma
  imagem mostra o pato cortado: confira a imagem toda antes de marcar ✅.
- Cada PR inclui `docs/relatorios/Mx.md` com:
  - o que foi feito, item por item, apontando o critério de aceite correspondente;
  - a saída do `uv run pytest` (resumida) e de cada script de verificação pedido;
  - evidência visual quando o marco for visual: GIF ou MP4 curto em `docs/relatorios/midia/`
    (o tamanho máximo está no plano);
  - os desvios e as dúvidas em aberto.
- Rode `uv run ruff check` e `uv run ruff format --check` antes de abrir o PR.
- Não marque um critério de aceite como cumprido sem evidência. "Funciona na minha máquina" não
  conta: diga o comando, a saída e a máquina (CPU e GPU).

## Ambiente

- Windows 10 ou 11, x64. Python **3.12** (o BAM exige `<3.13`), gerenciado por `uv`.
- A máquina de referência do dono tem Python 3.15 instalado no sistema. Use o Python 3.12
  gerenciado pelo uv (`.python-version`), nunca o do sistema.
- Para o teste de paridade, o `infer_policy.py` do upstream importa `termios`, `tty` e `select`
  (só existem no Unix). No teste, crie módulos falsos em `sys.modules` antes de importar. Não
  rode o teste em WSL só para fugir disso.

## Onde buscar a verdade

| Assunto | Fonte |
|---|---|
| Observação, ações, troca de políticas | `vendor/microduck_rl/scripts/infer_policy.py` (classe `PolicyInference`, função `main`) |
| Atuador BAM | `load_bam_model` e `load_mujoco_with_bam` no mesmo arquivo |
| O que cada política espera (duração, codificação do comando) | `manifest.json` da tag `v10` de `pollen-robotics/microduck-policies` |
| Esquema do manifesto | `vendor/microduck/docs/policy-manifest.md` |
| Invariantes do treino | `vendor/microduck_rl/AGENTS.md` |
