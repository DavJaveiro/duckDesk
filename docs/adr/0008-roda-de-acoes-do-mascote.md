# ADR-0008: Roda radial de ações no clique direito do pato

**Status:** aceita (2026-11-14, pós-M7)

## Contexto

O botão direito sobre o pato abria `tray.contextMenu()`, o mesmo `QMenu` nativo da bandeja:
um menu vertical com itens de app ("Tamanho", "Sobre", "Iniciar com o Windows") misturados
com os comportamentos do pato. O dono pediu que o pato tivesse uma **roda de ações própria,
logo acima da cabeça**, e que o menu nativo ficasse **apenas no ícone da bandeja** (inclusive
quando ele está na área de ícones ocultos).

## Decisão

- Novo módulo `ui/radial_menu.py` com `RadialMenu`, um `QWidget` de primeiro nível com
  `Qt.Popup | FramelessWindowHint | NoDropShadowWindowHint | WindowStaysOnTopHint` e fundo
  translúcido, pintado com `QPainter`: 8 setores e um botão central (✕) para fechar.
- A roda é ancorada 10 px acima do topo da cabeça, lido da máscara alfa do último quadro
  (`MascotWindow.duck_head_point`); raio de 100–128 px conforme o tamanho do pato (§2).
- Os rótulos e o estado de cada ação são reconstruídos a cada abertura; ações recusadas pelas
  regras de 03 §8 aparecem desabilitadas.
- O `QMenu` da bandeja fica **intocado**, aberto pelo próprio `QSystemTrayIcon` (05 §7).
- Mesma thread do Qt (ADR-0003); sem dependência nova.

## Alternativas descartadas

- **Reutilizar o `QMenu`** com uma geometria radial: o `QMenu` é uma lista vertical e depende
  da geometria das ações para navegação e teclado; forçar setores nele seria mais frágil do
  que pintar um widget próprio.
- **Menu nativo do Windows**: não desenha roda e não é estilizável.
- **Janela com `WA_ShowWithoutActivating`**: sem ativação não há como garantir o fechamento
  no clique fora e no `Esc` como um menu de verdade.

## Consequências

- O clique direito sobre o pato não abre mais "Tamanho", "Sobre" ou "Iniciar com o Windows":
  esses itens continuam na bandeja (05 §7). A roda tem só ações sobre o pato e a volta ao
  simulador.
- A roda aceita no máximo 8 ações (45° por setor); mais do que isso exige repensar o desenho.
- Testes: `tests/ui/test_radial_menu.py` (setores, ancoragem, cliques, ação desabilitada) e
  casos de integração com o `AppController` em `tests/ui/test_simulator_window.py`.
- A roda precisa roubar o foco do app ativo enquanto está aberta, como qualquer menu do
  Windows; ao fechar, o foco volta para a janela anterior.
