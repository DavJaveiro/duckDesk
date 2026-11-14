# 09: Checklist de revisão

Este é o roteiro que o revisor (Claude) segue em cada PR. Ele está aqui para que o Devin saiba
exatamente o que será conferido.

## Em todo PR

- [ ] Um marco só, no branch certo, com `docs/relatorios/Mx.md` completo.
- [ ] Cada critério de aceite tem evidência: comando + saída, teste ou mídia.
- [ ] `uv sync --frozen`, `ruff check`, `ruff format --check` e `pytest` rodam limpos **na
      máquina do revisor**, não só no relatório.
- [ ] Nada fora do escopo de 01 (sem funcionalidade extra "de brinde").
- [ ] Nenhum arquivo de `assets/upstream/` ou `assets/policies/` foi modificado (`lock.json`
      bate com o upstream).
- [ ] `vendor/` continua fora do git; nenhum import de `vendor/` fora de `tests/parity/`.
- [ ] Sem dependência nova que não esteja em 02. Se tiver, há uma ADR.
- [ ] Sem segredos, caminhos absolutos da máquina do Devin ou prints de debug esquecidos.
- [ ] Os desvios foram registrados em `docs/relatorios/duvidas.md` ou numa ADR.
- [ ] Textos da interface em pt-BR; código e commits em inglês.

## Contrato com as políticas (M1, e sempre que `policy/` ou `sim/` mudar)

- [ ] `DEFAULT_POSE` igual a 03 §3, literalmente.
- [ ] Índices de `qpos`/`qvel` pela transmissão dos atuadores, sem números fixos.
- [ ] Ordem da observação 3+3+14+14+14+13, gravidade projetada, `float32`, sem normalização.
- [ ] `last_action` = saída crua, preservada na troca de política.
- [ ] Alvos em `bam_ctrl.q_target`, nunca em `data.ctrl`; `bam_ctrl.update()` antes de cada
      `mj_step`; 4 subpassos; `timestep = 0.005`.
- [ ] Timers avançam com dt = 0.02 **antes** da inferência.
- [ ] Comandos dos episódicos todos zerados; `posture_flag` no `cmd[0]`; fase do `ground_pick`
      em cos/sin, terminando em 0.7.
- [ ] Durações vindas do manifesto (roulade 1.0, kicks 0.5); subida do sitstand de 1.0 s.
- [ ] Regras de transição centralizadas e testadas.
- [ ] O teste de paridade realmente importa o upstream (não uma cópia) e compara passo a passo.
- [ ] Comentários de origem (arquivo, commit, linhas) no código portado.

## Interface e plataforma (M3–M5)

- [ ] `sim/`, `policy/`, `brain/` e `render/` sem PySide6.
- [ ] Nenhuma thread extra (ADR-0003).
- [ ] Física com passo fixo: pausar e retomar não faz o pato "teleportar"; o limite de 5
      passos por tick existe.
- [ ] Janela do mascote: flags e estilos de 05 §2; reafirma `TOPMOST`; esconde em tela cheia;
      não rouba o foco (teste: digitar num editor enquanto o pato anda).
- [ ] Conversão de pixels físicos ↔ lógicos feita uma vez, num lugar só.
- [ ] Máscara pela árvore de `trunk_base`; sem halo; superamostragem 2×.
- [ ] Reproduzir o vídeo do relatório **localmente** com o código do PR (o revisor roda o app).

## Instalador (M6)

- [ ] Build pelo script numa máquina sem Python; tamanhos dentro do limite.
- [ ] Sem administrador; atalhos; desinstalação limpa; autostart funcionando.
- [ ] `THIRD_PARTY_NOTICES` na página de licença e na pasta instalada.
