# ADR-0002: Uma cena e um `MjModel` para os dois modos

**Status:** aceita (2026-11-14)

## Contexto

O simulador precisa da bola (chutes). O mascote não precisa. Recarregar o modelo ao trocar de
modo custa tempo (malhas, compilação, BAM) e perde o estado.

## Decisão

Carregar `scene_ball.xml` uma vez. No mascote, a bola fica estacionada em `(0, 50, 0.035)` e
some da renderização pela máscara de segmentação (só a árvore de `trunk_base` aparece).

## Consequências

- Trocar de modo é instantâneo e não aloca nada.
- A bola continua sendo simulada no mascote (custo desprezível: uma esfera parada).
- O teste de paridade também usa `scene_ball.xml` dos dois lados.
