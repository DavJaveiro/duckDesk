#!/usr/bin/env python3
"""Fetch pinned upstream assets into assets/ and verify their SHA-256 hashes.

Development-only script — the DuckDesk app never downloads anything at runtime.

Usage:
    python scripts/fetch_assets.py            Fetch everything, write assets/lock.json.
    python scripts/fetch_assets.py --verify   Ensure assets/ matches lock.json,
                                              re-downloading missing or stale files.
    python scripts/fetch_assets.py --vendor   Also clone the upstream repos into
                                              vendor/ at the pinned commits.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = ROOT / "assets"
LOCK_PATH = ASSETS_DIR / "lock.json"
VENDOR_DIR = ROOT / "vendor"

# Pinned upstream versions — docs/07-licencas.md. Changing any of these requires
# an ADR (AGENTS.md rule 4).
MICRODUCK_RL_REPO = "pollen-robotics/microduck_rl"
MICRODUCK_RL_REF = "0daab160d3fb1c2cbaba16a4a19052f36709dd9e"
MICRODUCK_REPO = "pollen-robotics/microduck"  # reference clone only (docs, robotd)
MICRODUCK_REF = "094d4bb4af31ec181156e1ea772437fdd7a55978"
POLICIES_REPO = "pollen-robotics/microduck-policies"  # Hugging Face model repo
POLICIES_REF = "v10"

# Offline pt-BR speech model for voice commands (ADR-0012). Apache-2.0, from
# alphacephei.com/vosk/models. The zip ships in the installer; the app extracts
# it once to the user cache (platform/ears.py).
VOSK_MODEL = "vosk-model-small-pt-0.3"
VOSK_MODEL_ZIP = f"{VOSK_MODEL}.zip"
VOSK_MODEL_URL = f"https://alphacephei.com/vosk/models/{VOSK_MODEL_ZIP}"

# docs/07 says "robot/microduck"; the real path in the repo is
# src/mjlab_microduck/robot/microduck (see docs/relatorios/duvidas.md).
ROBOT_DIR = "src/mjlab_microduck/robot/microduck"
# Files below this prefix land in assets/upstream/microduck_rl/ preserving the
# tail of the path (docs/02 folder layout).
ROBOT_PREFIX = "src/mjlab_microduck/"
SCENE_FILES = ("scene.xml", "scene_ball.xml")

# The six in-scope policies and their roles (docs/03 section 8). The roller
# policies and the legacy alpha_* set are out of scope.
IN_SCOPE_POLICIES = (
    "velstand.onnx",
    "alpha_sitstand.onnx",
    "alpha_ground_pick.onnx",
    "roulade.onnx",
    "ball_kick_left.onnx",
    "ball_kick_right.onnx",
)

USER_AGENT = "duckdesk-fetch-assets/0.1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, dest: Path, retries: int = 3) -> None:
    """Download url to dest (atomic via a temp file in the same directory)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=60) as response, tmp.open("wb") as fh:
                shutil.copyfileobj(response, fh)
            tmp.replace(dest)
            return
        except Exception as error:  # noqa: BLE001 - report and retry below
            last_error = error
            print(f"  download failed ({attempt + 1}/{retries}): {url}: {error}")
    raise SystemExit(f"error: could not download {url}: {last_error}")


def github_raw_url(repo: str, ref: str, path: str) -> str:
    # github.com/<repo>/raw/ resolves Git LFS objects transparently
    # (raw.githubusercontent.com would return the pointer file instead).
    return f"https://github.com/{repo}/raw/{ref}/{path}"


def hf_resolve_url(repo: str, ref: str, path: str) -> str:
    return f"https://huggingface.co/{repo}/resolve/{ref}/{path}"


def is_lfs_pointer(path: Path) -> bool:
    if path.stat().st_size > 1024:
        return False
    try:
        return path.read_bytes().startswith(b"version https://git-lfs")
    except OSError:
        return False


def collect_robot_files(src_root: Path) -> list[str]:
    """Return the upstream-relative paths needed by the two scenes.

    Walks <include file="..."> recursively from SCENE_FILES, then collects the
    file= references (meshes, textures, ...) honoring <compiler meshdir=...>.
    """
    robot_root = src_root / ROBOT_DIR
    queue = [robot_root / scene for scene in SCENE_FILES]
    xml_seen: set[Path] = set()
    file_refs: set[Path] = set()

    def asset_path(xml_dir: Path, meshdir: str, texturedir: str, tag: str, ref: str) -> Path:
        base = texturedir if tag in ("texture", "hfield") else meshdir
        for candidate in (xml_dir / base / ref, xml_dir / ref):
            if candidate.is_file():
                return candidate
        raise SystemExit(f"error: asset '{ref}' referenced from {xml_dir} not found")

    while queue:
        xml_path = queue.pop()
        xml_path = xml_path.resolve()
        if xml_path in xml_seen:
            continue
        xml_seen.add(xml_path)
        tree = ET.parse(xml_path)
        meshdir = ""
        texturedir = ""
        for compiler in tree.iter("compiler"):
            meshdir = compiler.get("meshdir", meshdir)
            texturedir = compiler.get("texturedir", texturedir)
        for element in tree.iter():
            ref = element.get("file")
            if not ref:
                continue
            if element.tag == "include":
                queue.append(xml_path.parent / ref)
            else:
                file_refs.add(asset_path(xml_path.parent, meshdir, texturedir, element.tag, ref))

    needed = {p.relative_to(src_root).as_posix() for p in xml_seen | file_refs}

    # BAM/export configs pairing each shipped robot_*.xml (docs/07 ships
    # config_mjcf_*.json in the installer): robot_<v>.xml -> config_mjcf_<v>.json.
    for rel in list(needed):
        name = Path(rel).name
        if name.startswith("robot_") and name.endswith(".xml"):
            config = Path(rel).parent / f"config_mjcf_{name[6:-4]}.json"
            if (src_root / config).is_file():
                needed.add(config.as_posix())

    return sorted(needed)


def fetch_microduck_rl(files: dict[str, dict]) -> None:
    """Download the pinned tarball and copy only the needed files into assets/."""
    url = f"https://github.com/{MICRODUCK_RL_REPO}/archive/{MICRODUCK_RL_REF}.tar.gz"
    print(f"fetching {MICRODUCK_RL_REPO}@{MICRODUCK_RL_REF[:12]}")
    with tempfile.TemporaryDirectory() as tmp_dir:
        tarball = Path(tmp_dir) / "repo.tar.gz"
        download(url, tarball)
        with tarfile.open(tarball) as tar:
            tar.extractall(tmp_dir, filter="data")
        src_root = next(Path(tmp_dir).glob("microduck_rl-*"))

        for rel in collect_robot_files(src_root):
            src = src_root / rel
            if is_lfs_pointer(src):
                download(github_raw_url(MICRODUCK_RL_REPO, MICRODUCK_RL_REF, rel), src)
            dest = ASSETS_DIR / "upstream" / "microduck_rl" / rel.removeprefix(ROBOT_PREFIX)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            files[dest.relative_to(ASSETS_DIR).as_posix()] = {
                "sha256": sha256_file(dest),
                "size": dest.stat().st_size,
                "source": "microduck_rl",
                "url": github_raw_url(MICRODUCK_RL_REPO, MICRODUCK_RL_REF, rel),
            }
    print(f"  copied {len(files)} files")


def fetch_policies(files: dict[str, dict]) -> None:
    """Download manifest.json, the six in-scope ONNX policies and README.md."""
    print(f"fetching {POLICIES_REPO}@{POLICIES_REF}")

    def policy_url(name: str) -> str:
        return hf_resolve_url(POLICIES_REPO, POLICIES_REF, name)

    manifest_dest = ASSETS_DIR / "policies" / POLICIES_REF / "manifest.json"
    download(policy_url("manifest.json"), manifest_dest)
    manifest = json.loads(manifest_dest.read_text(encoding="utf-8"))
    available = {entry["file"] for entry in manifest.get("policies", [])}
    missing = [name for name in IN_SCOPE_POLICIES if name not in available]
    if missing:
        raise SystemExit(f"error: in-scope policies missing from v10 manifest: {missing}")

    for name in ("manifest.json", "README.md", *IN_SCOPE_POLICIES):
        dest = ASSETS_DIR / "policies" / POLICIES_REF / name
        download(policy_url(name), dest)
        files[dest.relative_to(ASSETS_DIR).as_posix()] = {
            "sha256": sha256_file(dest),
            "size": dest.stat().st_size,
            "source": "policies",
            "url": policy_url(name),
        }
    print(f"  copied {len(IN_SCOPE_POLICIES) + 2} files")


def fetch_vosk(files: dict[str, dict]) -> None:
    """Download the pinned Vosk pt-BR command-recognition model (ADR-0012)."""
    print(f"fetching {VOSK_MODEL_ZIP}")
    dest = ASSETS_DIR / "models" / VOSK_MODEL_ZIP
    download(VOSK_MODEL_URL, dest)
    files[dest.relative_to(ASSETS_DIR).as_posix()] = {
        "sha256": sha256_file(dest),
        "size": dest.stat().st_size,
        "source": "vosk",
        "url": VOSK_MODEL_URL,
    }


def write_lock(files: dict[str, dict]) -> None:
    lock = {
        "version": 1,
        "sources": {
            "microduck_rl": {"repo": MICRODUCK_RL_REPO, "ref": MICRODUCK_RL_REF},
            "policies": {"repo": POLICIES_REPO, "ref": POLICIES_REF},
            "vosk": {"model": VOSK_MODEL, "url": VOSK_MODEL_URL},
        },
        "files": dict(sorted(files.items())),
    }
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCK_PATH.write_text(json.dumps(lock, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"wrote {LOCK_PATH.relative_to(ROOT)} ({len(files)} files)")


def verify() -> int:
    """Ensure every file in lock.json exists with a matching SHA-256."""
    if not LOCK_PATH.is_file():
        raise SystemExit("error: assets/lock.json not found; run fetch_assets.py first")
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    expected: dict[str, dict] = lock.get("files", {})

    problems: list[str] = []
    repaired = 0
    for rel, meta in expected.items():
        dest = ASSETS_DIR / rel
        if dest.is_file() and sha256_file(dest) == meta["sha256"]:
            continue
        print(f"  re-downloading {rel}")
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        download(meta["url"], tmp)
        if sha256_file(tmp) != meta["sha256"]:
            problems.append(f"{rel}: sha256 mismatch after re-download")
            tmp.unlink(missing_ok=True)
            continue
        tmp.replace(dest)
        repaired += 1

    managed = expected.keys()
    managed_roots = {rel.split("/", 1)[0] for rel in managed}
    for root in managed_roots:
        for path in (ASSETS_DIR / root).rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(ASSETS_DIR).as_posix()
            if path.suffix == ".part" or path.suffix == ".tmp":
                problems.append(f"{rel}: unexpected {path.suffix} file")
            elif rel not in expected:
                problems.append(f"{rel}: not listed in lock.json")

    if problems:
        for problem in problems:
            print(f"  FAIL {problem}", file=sys.stderr)
        raise SystemExit(f"error: {len(problems)} asset problem(s)")
    print(f"verify OK: {len(expected)} files ({repaired} repaired)")
    return 0


def vendor() -> None:
    """Clone the upstream repos into vendor/ at the pinned commits."""
    for repo, ref in ((MICRODUCK_RL_REPO, MICRODUCK_RL_REF), (MICRODUCK_REPO, MICRODUCK_REF)):
        name = repo.rsplit("/", 1)[1]
        dest = VENDOR_DIR / name
        if (dest / ".git").exists():
            head = subprocess.run(
                ["git", "-C", str(dest), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            if head == ref:
                print(f"vendor/{name} already at {ref[:12]}")
                continue
            subprocess.run(["git", "-C", str(dest), "fetch", "--quiet", "origin"], check=True)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "clone", "--quiet", f"https://github.com/{repo}.git", str(dest)],
                check=True,
            )
        subprocess.run(["git", "-C", str(dest), "checkout", "--quiet", ref], check=True)
        print(f"vendor/{name} @ {ref[:12]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--verify", action="store_true", help="verify hashes, repair via download")
    parser.add_argument(
        "--vendor", action="store_true", help="also clone upstream repos into vendor/"
    )
    args = parser.parse_args()

    if args.verify:
        verify()
    else:
        files: dict[str, dict] = {}
        fetch_microduck_rl(files)
        fetch_policies(files)
        fetch_vosk(files)
        write_lock(files)
        verify()
    if args.vendor:
        vendor()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
