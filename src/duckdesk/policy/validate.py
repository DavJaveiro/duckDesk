"""Validation of a user-supplied ONNX policy (docs/03 section 9)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import onnxruntime as ort

from duckdesk.policy.contract import ACTION_LEN, OBS_LEN


def _dim_is_n(shape) -> bool:
    """First dim may be 1, N or symbolic; only the feature dim is checked."""
    return len(shape) == 2 and shape[-1] in (OBS_LEN,)


def validate_user_onnx(path: str | Path) -> tuple[bool, str]:
    """Return (ok, message_pt). Messages are user-facing, in pt-BR."""
    path = Path(path)
    try:
        session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    except Exception:  # noqa: BLE001 - any load failure means "not a valid ONNX" for the user
        return False, f"'{path.name}' nao e um arquivo ONNX valido."

    inputs = session.get_inputs()
    outputs = session.get_outputs()
    if len(inputs) != 1 or len(outputs) != 1:
        return False, "a politica precisa de exatamente uma entrada e uma saida."
    in_shape = inputs[0].shape
    out_shape = outputs[0].shape
    if len(in_shape) != 2 or in_shape[-1] != OBS_LEN:
        return False, f"entrada deve ser [N, {OBS_LEN}]; recebido {in_shape}."
    if len(out_shape) != 2 or out_shape[-1] != ACTION_LEN:
        return False, f"saida deve ser [N, {ACTION_LEN}]; recebido {out_shape}."

    # Smoke test: zeros and a standing-like obs must produce finite, non-constant output.
    zeros_obs = np.zeros((1, OBS_LEN), dtype=np.float32)
    stand_obs = zeros_obs.copy()
    stand_obs[0, 3:6] = [0.0, 0.0, -1.0]  # projected gravity, upright trunk
    in_name = inputs[0].name
    out_name = outputs[0].name
    try:
        out_zero = session.run([out_name], {in_name: zeros_obs})[0]
        out_stand = session.run([out_name], {in_name: stand_obs})[0]
    except Exception as exc:  # noqa: BLE001 - surface any runtime failure to the user
        return False, f"a inferencia de teste falhou: {exc}"
    if not (np.isfinite(out_zero).all() and np.isfinite(out_stand).all()):
        return False, "a inferencia de teste produziu NaN/Inf."
    if np.allclose(out_zero, out_stand):
        return False, "a saida da politica e constante (nao responde a observacao)."

    manifest_path = path.parent / "manifest.json"
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - JSONDecodeError plus read errors all mean invalid
            return False, "o manifest.json ao lado do ONNX nao e um JSON valido."
        if manifest.get("model_api", 1) > 1:
            return False, "politicas recorrentes (model_api > 1) nao sao suportadas."
        if (
            manifest.get("obs_len", OBS_LEN) != OBS_LEN
            or manifest.get("action_len", ACTION_LEN) != ACTION_LEN
        ):
            return (
                False,
                f"o manifest.json declara um contrato diferente de {OBS_LEN}->{ACTION_LEN}.",
            )

    return True, "politica valida"
