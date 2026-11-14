# ADR-0005: Janela do mascote pequena que acompanha o pato

**Status:** aceita (2026-11-14)

## Contexto

Opções: (a) uma faixa transparente da largura da tela, renderizada inteira a cada quadro; ou
(b) uma janela quadrada do tamanho do pato que se move com ele.

## Decisão

(b). Renderizar e compor uma área de cerca de 190×190 px lógicos em vez de 2560×190 reduz o
custo de renderização, de leitura e de `UpdateLayeredWindow` por mais de 10×.

## Consequências

- A janela é movida a cada quadro em que o x em pixels muda.
- A câmera precisa ser recentrada em sincronia com a janela (05 §3) para o pato não tremer.
