# Build with:
#   pyinstaller --clean --noconfirm app.spec
#
# The build script places the executable at:
#   dist/project/app.exe
#
# Copy trained models to:
#   dist/project/models/*.pth
#
# End-user deployment folder:
#   project/app.exe
#   project/models/*.pth

from PyInstaller.utils.hooks import collect_submodules
from pathlib import Path


hiddenimports = (
    collect_submodules("torch")
    + collect_submodules("torchvision")
    + collect_submodules("pywt")
    + collect_submodules("cv2")
    + collect_submodules("scipy")
    + collect_submodules("skimage")
    + [
        "photo_process.format_converter",
        "photo_process.batch_crop",
        "photo_process.image_RB",
        "photo_process.auto_mask",
        "photo_process.auto_assort",
        "photo_process.image_enhance",
    ]
)

datas = []
# Never package the local clinical workbook: it may contain identifiers or PHI.
# The desktop fallback only needs the non-identifying normalization statistics.
for path in (Path("features") / "train_stats.json",):
    if path.exists():
        datas.append((str(path), "features"))

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pandas", "sklearn", "xgboost", "joblib"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="app",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
