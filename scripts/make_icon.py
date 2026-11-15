"""Generate the app icon from a render of the real MuJoCo duck.

    uv run python scripts/make_icon.py

Renders the duck offscreen with the mascot renderer (transparent
background, no floor), saves a full-body PNG for reference, then a head
close-up that becomes assets/icons/duckdesk.png (256 px) and the
multi-size assets/icons/duckdesk.ico used by the exe, shortcuts and the
installer (duckdesk.spec / duckdesk.iss).
"""

from __future__ import annotations

import sys
from pathlib import Path

import mujoco
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from duckdesk import assets
from duckdesk.render.mascot import VISUAL_GROUP, MascotRenderer
from duckdesk.sim.core import SimCore

ROBOT_DIR = assets.assets_dir() / "upstream" / "microduck_rl" / "robot" / "microduck"
SCENE = ROBOT_DIR / "scene.xml"
ICONS_DIR = assets.assets_dir() / "icons"
MEDIA_DIR = Path(__file__).resolve().parents[1] / "docs" / "relatorios" / "midia"

SIZE = 1024  # output side; rendered internally at 2x and box-filtered
HEAD_BODY = "jaw_soft"  # the whole head assembly (shell, face, eye, beak)
# Only the outer-shell meshes frame the icon: jaw_soft also carries the PCB,
# speaker and lens holder, which hang below the shell and would drag the
# bounding box down into the neck.
HEAD_MESHES = {
    "top_head_shell",
    "bottom_head_shell",
    "face_part",
    "jaw",
    "jaw_soft",
    "soft_mouth_top",
    "noenoeil",
}
MARGIN = 1.12  # extra frame around the subject bbox
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]


def _geom_world_verts(model: mujoco.MjModel, data: mujoco.MjData, g: int) -> np.ndarray:
    """World-space vertices of a geom (mesh verts or primitive AABB corners)."""
    if model.geom_type[g] == mujoco.mjtGeom.mjGEOM_MESH and model.geom_dataid[g] >= 0:
        mesh = model.geom_dataid[g]
        a, n = model.mesh_vertadr[mesh], model.mesh_vertnum[mesh]
        rot = data.geom_xmat[g].reshape(3, 3)
        return data.geom_xpos[g] + model.mesh_vert[a : a + n] @ rot.T
    ctr, half = model.geom_aabb[g, :3], model.geom_aabb[g, 3:]
    corners = np.array([[sx, sy, sz] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)])
    rot = data.geom_xmat[g].reshape(3, 3)
    return data.geom_xpos[g] + (ctr + corners * half) @ rot.T


def _subject_geoms(
    model: mujoco.MjModel, body_name: str | None, mesh_names: set[str] | None = None
) -> np.ndarray:
    """Visual geoms: the whole duck (body_name None) or one body's worth,
    optionally filtered to a set of mesh names."""
    trunk = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "trunk_base")
    keep_root = trunk if body_name is None else -1
    body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body_name) if body_name else -1
    out = []
    for g in range(model.ngeom):
        if model.geom_group[g] != VISUAL_GROUP:
            continue
        if body_name is None:
            if model.body_rootid[model.geom_bodyid[g]] != keep_root:
                continue
        elif model.geom_bodyid[g] != body:
            continue
        if mesh_names is not None:
            name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_MESH, model.geom_dataid[g])
            if name not in mesh_names:
                continue
        out.append(g)
    return np.array(out, dtype=int)


def _screen_bbox(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    geoms: np.ndarray,
    ref: np.ndarray,
    right: np.ndarray,
    up: np.ndarray,
) -> tuple[float, float, float, float]:
    """(rmin, rmax, umin, umax) of the geoms projected on the camera plane."""
    rmin, rmax, umin, umax = np.inf, -np.inf, np.inf, -np.inf
    for g in geoms:
        rel = _geom_world_verts(model, data, g) - ref
        rr, uu = rel @ right, rel @ up
        rmin, rmax = min(rmin, rr.min()), max(rmax, rr.max())
        umin, umax = min(umin, uu.min()), max(umax, uu.max())
    return float(rmin), float(rmax), float(umin), float(umax)


def _render(
    rend: MascotRenderer,
    data: mujoco.MjData,
    ref: np.ndarray,
    bbox: tuple[float, float, float, float],
    margin: float,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Frame the bbox and render.

    Returns (rgba, lookat_ru, view_h): rgba is (S, S, 4) straight RGBA;
    lookat_ru is the frame center in (right, up) coords for pixel cropping.
    """
    rmin, rmax, umin, umax = bbox
    lookat = ref + rend.right * ((rmin + rmax) / 2) + rend.up * ((umin + umax) / 2)
    # Square frame: the wider of the two axes sets the view height (the head
    # is ~2x wider than tall, so height alone clipped the beak).
    view_h = max(rmax - rmin, umax - umin) * margin
    rend.set_view_height(view_h)
    bgra = rend.frame(data, lookat)
    rgb_p, a = bgra[..., 2::-1].astype(np.float32), bgra[..., 3:4].astype(np.float32)
    rgba = np.concatenate([rgb_p / np.maximum(a, 1) * 255.0, a], axis=-1)
    lookat_ru = np.array([(lookat - ref) @ rend.right, (lookat - ref) @ rend.up])
    return rgba.clip(0, 255).astype(np.uint8), lookat_ru, view_h


def _crop_bbox(
    img: np.ndarray,
    bbox: tuple[float, float, float, float],
    lookat_ru: np.ndarray,
    view_h: float,
    margin_px: int,
) -> np.ndarray:
    """Crop to the projected (right, up) bbox in pixels — cuts context the
    alpha crop would keep (e.g. the neck under the head)."""
    s = img.shape[0]
    rmin, rmax, umin, umax = bbox
    c0 = (rmin - lookat_ru[0]) / view_h * s + s / 2 - margin_px
    c1 = (rmax - lookat_ru[0]) / view_h * s + s / 2 + margin_px
    r0 = s / 2 - (umax - lookat_ru[1]) / view_h * s - margin_px
    r1 = s / 2 - (umin - lookat_ru[1]) / view_h * s + margin_px
    c0, c1 = max(0, int(c0)), min(s, int(np.ceil(c1)))
    r0, r1 = max(0, int(r0)), min(s, int(np.ceil(r1)))
    return img[r0:r1, c0:c1]


def _crop_alpha(img: np.ndarray, margin_px: int) -> np.ndarray:
    rows = np.flatnonzero((img[..., 3] > 0).any(axis=1))
    cols = np.flatnonzero((img[..., 3] > 0).any(axis=0))
    r0, r1 = max(0, rows[0] - margin_px), min(img.shape[0], rows[-1] + 1 + margin_px)
    c0, c1 = max(0, cols[0] - margin_px), min(img.shape[1], cols[-1] + 1 + margin_px)
    return img[r0:r1, c0:c1]


def _square_pad(img: np.ndarray) -> Image.Image:
    h, w = img.shape[:2]
    side = max(h, w)
    out = np.zeros((side, side, 4), np.uint8)
    y0, x0 = (side - h) // 2, (side - w) // 2
    out[y0 : y0 + h, x0 : x0 + w] = img
    return Image.fromarray(out, "RGBA")


def main() -> int:
    sim = SimCore(SCENE)
    model, data = sim.model, sim.data
    # The scene caps the offscreen buffer at 1920x1080; the icon renders at
    # 2*SIZE. Bumping the model field is render-only — MJCF untouched.
    model.vis.global_.offwidth = model.vis.global_.offheight = 2 * SIZE

    rend = MascotRenderer(model, SIZE)
    trunk = sim.trunk_base_id
    ref = np.array([data.xpos[trunk][0], data.xpos[trunk][1], 0.0])

    duck = _subject_geoms(model, None)
    head = _subject_geoms(model, HEAD_BODY, HEAD_MESHES)
    if duck.size == 0 or head.size == 0:
        print("no geoms found", file=sys.stderr)
        return 1

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    ICONS_DIR.mkdir(parents=True, exist_ok=True)

    full, _, _ = _render(
        rend, data, ref, _screen_bbox(model, data, duck, ref, rend.right, rend.up), 1.15
    )
    full_png = MEDIA_DIR / "duck_full.png"
    Image.fromarray(_crop_alpha(full, 12)).save(full_png)
    print(f"pato inteiro -> {full_png}")

    head_bbox = _screen_bbox(model, data, head, ref, rend.right, rend.up)
    close, lookat_ru, view_h = _render(rend, data, ref, head_bbox, MARGIN)
    icon = _square_pad(_crop_bbox(close, head_bbox, lookat_ru, view_h, 8))
    png_path = ICONS_DIR / "duckdesk.png"
    icon.resize((256, 256), Image.LANCZOS).save(png_path)
    ico_path = ICONS_DIR / "duckdesk.ico"
    icon.save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in ICO_SIZES],
        resample=Image.LANCZOS,
    )
    print(f"icone -> {ico_path} ({' '.join(str(s) for s in ICO_SIZES)} px), png -> {png_path}")
    rend.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
