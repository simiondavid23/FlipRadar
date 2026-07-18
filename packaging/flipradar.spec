# -*- mode: python ; coding: utf-8 -*-
# PyInstaller onedir pentru FlipRadar (PKG-3b).
# Rulat prin packaging/build_exe.py cu cwd=packaging/, deci caile sunt relative
# la packaging/ (../backend etc.).
from PyInstaller.utils.hooks import collect_all

# collect_all agrega datas + binaries + hiddenimports pentru pachete care isi
# aduc resurse la runtime (drivere, .dll/.pyd, metadate), pe care analiza statica
# a PyInstaller le rateaza. Le folosim pentru:
#  - curl_cffi: aduce libcurl-impersonate (.dll) + certifi; fara ele scraperele
#    .ro (OLX/Okazii/LaJumate/Publi24) pica la runtime.
#  - patchright / playwright: aduc driverul Node (package/driver) — exact ce
#    lipseste tipic dintr-un bundle; de aceea il validam cu --selfcheck.
datas = []
binaries = []
# pystray isi importa backend-ul de platforma dinamic (pe Windows: pystray._win32),
# invizibil analizei statice.
hiddenimports = ["pystray._win32"]

for _pkg in ("curl_cffi", "patchright", "playwright"):
    _d, _b, _h = collect_all(_pkg)
    datas += _d
    binaries += _b
    hiddenimports += _h


a = Analysis(
    ["../backend/launcher.py"],
    pathex=["../backend"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,          # onedir: binariile stau in folderul COLLECT
    name="FlipRadar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                  # windowed — print-urile merg in log (vezi launcher)
    disable_windowed_traceback=False,
    icon="flipradar.ico",           # generat de build_exe.py daca lipseste
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="FlipRadar",               # -> dist/FlipRadar/
)
