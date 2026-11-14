# 01: Visão e escopo

## Objetivo

Ter um Microduck no computador que **se mova igual ao robô real**, sem comprar o robô. "Igual"
aqui tem um sentido preciso: o mesmo modelo físico (MJCF + malhas oficiais), o mesmo modelo de
atuador (BAM M6 do servo XL330) e as mesmas redes neurais (ONNX oficiais, tag `v10`), ligados
pelo mesmo contrato de observação e ação usado pelo script oficial de ensaio
(`infer_policy.py`). Não desenhamos nem animamos nada: o movimento sai da física e das redes.

## Usuário

O dono do projeto, num PC com Windows 11 x64. Quer:

1. abrir o simulador, dirigir o pato e ver os comportamentos;
2. mandar o pato para a barra de tarefas e deixar ele "morando" ali enquanto usa o PC;
3. testar políticas novas (ONNX treinados por ele ou baixados do Hugging Face Hub), mais tarde.

## Dentro do escopo (v1)

- **Modo simulador**: janela 3D com menus, câmera orbital ou seguindo o pato, controle por
  teclado, comportamentos, HUD e carregamento de ONNX personalizado no slot de caminhada.
- **Modo mascote**: pato com fundo transparente andando sobre a barra de tarefas do monitor
  principal, com piloto automático, clique para interagir e arrastar para reposicionar.
- **Alternância entre os modos** sem fechar o app, com o mesmo processo e o mesmo modelo.
- **Ícone na bandeja do sistema** com o menu principal.
- **Instalador** `.exe` por usuário (sem pedir administrador), com desinstalador e a opção
  "Iniciar com o Windows".
- **Políticas incluídas** (todas da tag `v10`, todas de 61 → 14):

| Arquivo | Uso no app |
|---|---|
| `velstand.onnx` | Andar, ficar parado e **se levantar sozinho depois de cair**. Política principal. |
| `alpha_sitstand.onnx` | Sentar e levantar |
| `alpha_ground_pick.onnx` | Bicar o chão |
| `roulade.onnx` | Cambalhota para frente |
| `ball_kick_left.onnx`, `ball_kick_right.onnx` | Chutar a bola (só no simulador, que tem bola) |

## Fora do escopo (v1)

- Treinar políticas (precisa de GPU NVIDIA, mjlab e warp). Pode virar uma v2 com WSL2.
- Modo patins (`roller*.onnx`): exige outro modelo físico, com rodas.
- `alpha_walking.onnx` e `alpha_stand.onnx`: são substituídas pela `velstand.onnx` no conjunto
  oficial desde a v5. Não as carregue por padrão.
- Câmera, lidar, visão, voz, "quack" e os daemons Rust do robô real (`robotd` etc.).
- Barra de tarefas lateral ou superior, oculta automaticamente, e vários monitores: na v1 basta
  degradar bem (veja 05). Suporte completo fica para depois.
- macOS e Linux.
- Assinatura de código do instalador (o SmartScreen vai avisar; aceitável na v1).

## Requisitos não funcionais

| Requisito | Meta (medida no relatório do marco) |
|---|---|
| Física em tempo real | Controle a 50 Hz estáveis, sem acumular atraso, com o modo mascote ativo e o PC em uso normal |
| CPU no modo mascote | ≤ 15 % de **um** núcleo em média (Task Manager ou `psutil`, 60 s de medição) |
| CPU no modo simulador | Sem meta rígida; informe o valor |
| Memória | ≤ 400 MB de RSS |
| Tempo de abertura | ≤ 6 s até o pato aparecer (instalado, SSD) |
| Instalador | ≤ 350 MB; instala sem administrador |
| Estabilidade | 2 h no modo mascote sem travar, sem vazar memória (RSS final ≤ RSS em 5 min + 10 %) e sem o pato "fugir" da barra |
| Sem rede | Funciona com a internet desligada |
