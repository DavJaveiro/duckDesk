# Dúvidas e desvios em aberto

Registre aqui tudo o que a documentação não respondeu, ou em que você precisou fazer diferente.
Uma entrada por item. Não apague as entradas resolvidas: marque como resolvidas e diga como.

| # | Data | Marco | Documento/seção | Dúvida ou desvio | Proposta | Status |
|---|---|---|---|---|---|---|
| 1 | 2026-11-14 | M0 | 02 §"Versões fixadas" / 03 §2 / 07 | O bam fixado (`57d13ea`) não tem o parâmetro `vin_drop_gain` que o `infer_policy.py@0daab16` usa: a partir de `Rhoban/bam@e4bf1aa` o nome virou `vin_drop_resistance` (Ω), com queda `R·Σ\|τ\|/kt`. O `uv.lock` do próprio upstream fixa bam `62bd8ce` (anterior à renomeação), não `57d13ea`. | Em `sim/core.py` mantive a assinatura do upstream (`vin_drop_gain`) e traduzi com `vin_drop_resistance = gain·kt`, que produz a mesma queda de tensão. Alternativa: fixar bam em `62bd8ce` via ADR. | Aberto — aguardando revisão (afeta a paridade do M1) |
| 2 | 2026-11-14 | M0 | 07 | O doc diz copiar "de `robot/microduck/`", mas no repositório o caminho é `src/mjlab_microduck/robot/microduck/`. | `fetch_assets.py` usa o caminho real e grava em `assets/upstream/microduck_rl/robot/microduck/` (layout do 02). | Resolvida |
| 3 | 2026-11-14 | M0 | 07 ("`config_mjcf_*.json` vão no instalador") | Há 7 `config_mjcf_*.json` no upstream (walk, allcollisions, rollers, backlash…). O `infer_policy.py` não usa nenhum — constrói o modelo BAM via `bam.model.load_model`. | Copiei só `config_mjcf_groundcontact.json`, que pareia com o `robot_groundcontact.xml` enviado. Se a revisão quiser todos (ou nenhum), ajusto o filtro. | Aberto — aguardando revisão |
| 4 | 2026-11-14 | M0 | 03 §2 | O `load_mujoco_with_bam` do upstream imprime um resumo dos atuadores na carga (L96-102). | Não portei o `print`; um log estruturado vem no M1/M4. Sem efeito na física. | Resolvida |
