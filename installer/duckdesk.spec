# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for DuckDesk (docs/06 step 1): onedir, console off,
own icon, all bundled assets, heavy Qt modules excluded."""

import os

from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
SRC = os.path.join(ROOT, "src")
ICON = os.path.join(ROOT, "assets", "icons", "duckdesk.ico")

datas = [
    (os.path.join(ROOT, "assets"), "assets"),
    (os.path.join(ROOT, "licenses"), "licenses"),
    (os.path.join(ROOT, "THIRD_PARTY_NOTICES.md"), "."),
]
binaries = []
hiddenimports = []

# binary deps that PyInstaller's import scan misses (docs/06 checklist):
# mujoco -> DLL + plugin/, glfw -> glfw3.dll, onnxruntime -> provider DLLs,
# bam -> params/*.json actuator models (load_model resolves them at runtime)
for pkg in ("mujoco", "glfw", "onnxruntime", "bam"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

EXCLUDES = [
    "tkinter",
    # unused heavy Qt modules (docs/06); PySide6-Essentials is installed anyway
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtSpatialAudio",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "PySide6.QtRemoteObjects",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtPositioning",
    "PySide6.QtLocation",
    "PySide6.QtSerialPort",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtScxml",
    "PySide6.QtStateMachine",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "numpy.tests",
    "numpy._core.tests",
    "numpy.testing",
    "pytest",
    "PIL",
    "imageio",
    "psutil",
]

a = Analysis(
    [os.path.join(SPECPATH, "run_duckdesk.py")],
    pathex=[SRC],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DuckDesk",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=ICON,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="DuckDesk",
)
