# ADR-0003: Física, rede neural e interface na thread do Qt

**Status:** aceita (2026-11-14)

## Contexto

Um passo de controle (inferência ONNX de uma MLP pequena + 4 × BAM + `mj_step`) leva da ordem de
1 ms. Com o GIL, threads em Python não dariam paralelismo real, e trariam travas, cópias de
estado e condições de corrida entre a física e a renderização.

## Decisão

Tudo roda na thread principal, num `QTimer` (`PreciseTimer`, 8 ms), com um acumulador de passo
fixo (`SimClock`): no máximo 5 passos de controle por tick. O atraso acima disso é descartado.

## Consequências

- Determinístico e simples de testar: o núcleo roda sem Qt nos testes.
- Se um quadro de renderização demorar, a física recupera no tick seguinte, até o limite.
- **Medir no M1:** tempo médio e p99 de um passo de controle. Se o p99 passar de 5 ms, reabra
  esta ADR.
