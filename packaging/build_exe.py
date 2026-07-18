"""Build reproductibil al exe-ului FlipRadar (PKG-3b, PyInstaller onedir).

Ruleaza din radacina repo-ului cu python-ul din venv (are pyinstaller):
    backend/venv/Scripts/python.exe packaging/build_exe.py

Pasi: (1) verifica pyinstaller, (2) genereaza flipradar.ico daca lipseste,
(3) verifica frontend/out (build daca lipseste), (4) curata build/ + dist/,
(5) ruleaza PyInstaller cu spec-ul (cwd=packaging/), (6) copiaza frontend/out
langa exe (frontend_out/), (7) raport de marime (total + top 10 fisiere).
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

PACKAGING = Path(__file__).resolve().parent
REPO = PACKAGING.parent
FRONTEND_OUT = REPO / "frontend" / "out"
DIST = PACKAGING / "dist"
BUILD = PACKAGING / "build"
ICO = PACKAGING / "flipradar.ico"
FAVICON = REPO / "frontend" / "src" / "app" / "favicon.ico"


def _ensure_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        sys.exit("[build] PyInstaller lipseste din acest Python. Ruleaza cu "
                 "backend/venv/Scripts/python.exe (unde e instalat).")


def _ensure_icon():
    if ICO.exists():
        print(f"[build] ico exista: {ICO}")
        return
    from PIL import Image, ImageDraw
    if FAVICON.exists():
        # PKG-3c: icon REAL din favicon-ul aplicatiei, re-esantionat la marimile
        # standard de icon Windows (exe + setup arata identic cu app-ul).
        print(f"[build] generez flipradar.ico din favicon-ul real ({FAVICON})...")
        img = Image.open(FAVICON).convert("RGBA")
        img.save(ICO, sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
    else:
        print("[build] favicon lipseste — fallback pe desenul PIL...")
        base = Image.new("RGB", (256, 256), "#0f172a")
        d = ImageDraw.Draw(base)
        d.rectangle([24, 24, 232, 232], outline="#60a5fa", width=18)
        d.text((104, 88), "F", fill="#60a5fa")
        base.save(ICO, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"[build] ico scris: {ICO}")


def _ensure_frontend_out():
    if (FRONTEND_OUT / "index.html").exists():
        print(f"[build] frontend/out exista: {FRONTEND_OUT}")
        return
    print("[build] frontend/out lipseste — rulez `npm run build`...")
    subprocess.run(["npm", "run", "build"], cwd=str(REPO / "frontend"),
                   check=True, shell=True)
    if not (FRONTEND_OUT / "index.html").exists():
        sys.exit("[build] frontend/out tot lipseste dupa build — opresc.")


def _clean():
    for p in (BUILD, DIST):
        if p.exists():
            print(f"[build] curat {p}")
            shutil.rmtree(p, ignore_errors=True)


def _run_pyinstaller():
    print("[build] rulez PyInstaller (flipradar.spec)...")
    subprocess.run([sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm",
                    "flipradar.spec"], cwd=str(PACKAGING), check=True)


def _copy_frontend():
    dst = DIST / "FlipRadar" / "frontend_out"
    print(f"[build] copiez frontend/out -> {dst}")
    shutil.copytree(FRONTEND_OUT, dst)


def _report_size():
    root = DIST / "FlipRadar"
    files = [f for f in root.rglob("*") if f.is_file()]
    total = sum(f.stat().st_size for f in files)
    print(f"\n[build] onedir total: {total / 1024 / 1024:.1f} MB  ({root})")
    top = sorted(files, key=lambda f: f.stat().st_size, reverse=True)[:10]
    print("[build] top 10 cele mai mari fisiere:")
    for f in top:
        print(f"    {f.stat().st_size / 1024 / 1024:6.1f} MB  {f.relative_to(root)}")


def _read_app_version() -> str:
    """APP_VERSION din backend/app/version.py, parsat simplu (fara import de app)."""
    txt = (REPO / "backend" / "app" / "version.py").read_text(encoding="utf-8")
    m = re.search(r"""APP_VERSION\s*=\s*["']([^"']+)["']""", txt)
    if not m:
        sys.exit("[build] nu am gasit APP_VERSION in backend/app/version.py")
    return m.group(1)


def _find_iscc() -> str:
    """ISCC.exe (Inno Setup 6) — instalarea per-user (winget) sau cea globala."""
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Inno Setup 6" / "ISCC.exe",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    sys.exit("[build] ISCC.exe (Inno Setup 6) nu a fost gasit. Instaleaza cu "
             "`winget install -e --id JRSoftware.InnoSetup`.")


def _build_installer(version: str):
    iscc = _find_iscc()
    print(f"[build] rulez Inno Setup ({iscc}) pentru v{version}...")
    subprocess.run([iscc, f"/DAppVersion={version}", "installer.iss"],
                   cwd=str(PACKAGING), check=True)
    setup = DIST / f"FlipRadar-Setup-{version}.exe"
    if not setup.exists():
        sys.exit(f"[build] Setup-ul nu a aparut la {setup}")
    print(f"\n[build] SETUP GATA: {setup} ({setup.stat().st_size / 1024 / 1024:.1f} MB)")


def main():
    skip_installer = "--skip-installer" in sys.argv
    _ensure_pyinstaller()
    _ensure_icon()
    _ensure_frontend_out()
    _clean()
    _run_pyinstaller()
    _copy_frontend()
    _report_size()
    exe = DIST / "FlipRadar" / "FlipRadar.exe"
    print(f"\n[build] EXE GATA: {exe} (exista={exe.exists()})")
    if skip_installer:
        print("[build] --skip-installer -> nu construiesc installer-ul Inno.")
        return
    _build_installer(_read_app_version())


if __name__ == "__main__":
    main()
