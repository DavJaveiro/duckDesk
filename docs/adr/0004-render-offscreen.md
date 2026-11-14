# ADR-0004: Renderização offscreen do MuJoCo → `QImage`

**Status:** aceita (2026-11-14)

## Contexto

O `mujoco.viewer` nativo abre uma janela GLFW própria, onde não dá para pôr menus do Qt, e a
janela do mascote precisa de alfa por pixel. Compartilhar um contexto OpenGL entre o Qt
(`QOpenGLWidget`) e o MuJoCo é frágil no Windows.

## Decisão

Usar `mujoco.Renderer` (contexto próprio, offscreen), ler a imagem para a CPU e pintar como
`QImage`. Nas duas vistas.

## Consequências

- Custo de leitura da GPU: aceitável até 1920×1080 a 60 fps no simulador e 2S×2S a 30 fps no
  mascote. Medir no M3 e no M5.
- Funciona igual nos dois modos e permite a máscara de segmentação.
