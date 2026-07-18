"""FlipRadar launcher — entrypoint-ul executabilului distribuit (PKG-3a).

Ruleaza identic in dev: `python launcher.py` din backend/ (data dir = cwd,
per app.paths). Sub PyInstaller (sys.frozen): data dir = LOCALAPPDATA,
stdout/stderr -> <data_dir>/logs/flipradar.log (fara consola, print-urile
altfel crapa), frontend-ul static de langa exe.
"""
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # `import app.*` si din alt cwd

READY_TIMEOUT_S = 30
PORT_RANGE = range(8000, 8011)


def _setup_frozen_logging() -> None:
    """Sub PyInstaller fara consola, sys.stdout/err sunt None si print()
    arunca. Redirectam totul intr-un log persistent, truncat la 5MB —
    si fraza de suport devine: trimite-mi flipradar.log."""
    if not getattr(sys, "frozen", False):
        return
    from app.paths import get_data_dir  # stdlib-only la import, safe aici
    logdir = get_data_dir() / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    logfile = logdir / "flipradar.log"
    try:
        if logfile.exists() and logfile.stat().st_size > 5 * 1024 * 1024:
            logfile.unlink()
    except OSError:
        pass
    f = open(logfile, "a", encoding="utf-8", buffering=1)
    sys.stdout = f
    sys.stderr = f
    print(f"\n===== FlipRadar pornit {time.strftime('%Y-%m-%d %H:%M:%S')} =====")


def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _flipradar_at(port: int) -> bool:
    """True daca la port raspunde chiar FlipRadar (nu alt server)."""
    import requests
    try:
        r = requests.get(f"http://127.0.0.1:{port}/api/health", timeout=1)
        return r.status_code == 200 and "status" in r.json()
    except Exception:
        return False


def _choose_port():
    """(port, already_running). Prefera 8000; daca acolo e FlipRadar ->
    refolosim instanta; daca e altceva -> urmatorul port liber."""
    for port in PORT_RANGE:
        if _flipradar_at(port):
            return port, True
        if _port_is_free(port):
            return port, False
    raise RuntimeError(f"Niciun port liber in {PORT_RANGE.start}-{PORT_RANGE.stop - 1}")


def _wait_ready(port: int, timeout_s: int) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if _flipradar_at(port):
            return True
        time.sleep(0.5)
    return False


def _make_icon_image():
    """Placeholder programatic (PKG-3c aduce .ico real)."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (64, 64), "#0f172a")
    d = ImageDraw.Draw(img)
    d.rectangle([6, 6, 58, 58], outline="#60a5fa", width=5)
    d.text((24, 18), "F", fill="#60a5fa")
    return img


def _shutdown(server) -> None:
    server.should_exit = True


def main() -> None:
    _setup_frozen_logging()
    port, already = _choose_port()
    url = f"http://127.0.0.1:{port}"
    if already:
        print(f"[Launcher] FlipRadar ruleaza deja la {url} — deschid browserul si ies.")
        webbrowser.open(url)
        return

    import uvicorn
    from app.main import app as fastapi_app
    from app.version import APP_VERSION

    server = uvicorn.Server(uvicorn.Config(
        fastapi_app, host="127.0.0.1", port=port, log_level="info"))
    t = threading.Thread(target=server.run, daemon=True, name="uvicorn")
    t.start()

    if not _wait_ready(port, READY_TIMEOUT_S):
        print(f"[Launcher] Serverul nu a raspuns in {READY_TIMEOUT_S}s — vezi log-ul.")
        _shutdown(server)
        sys.exit(1)
    print(f"[Launcher] FlipRadar v{APP_VERSION} gata la {url}")
    webbrowser.open(url)

    try:
        import pystray
        icon = pystray.Icon(
            "flipradar", _make_icon_image(), f"FlipRadar v{APP_VERSION}",
            menu=pystray.Menu(
                pystray.MenuItem("Deschide FlipRadar",
                                 lambda icon, item: webbrowser.open(url), default=True),
                pystray.MenuItem("Ieșire", lambda icon, item: icon.stop()),
            ))
        icon.run()  # blocant pana la Iesire
        print("[Launcher] Iesire din tray — opresc serverul.")
    except KeyboardInterrupt:
        print("[Launcher] Ctrl+C — opresc serverul.")
    except Exception as exc:
        print(f"[Launcher] Tray indisponibil ({exc}) — mod consola, Ctrl+C pentru oprire.")
        try:
            while t.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            pass

    _shutdown(server)
    t.join(timeout=10)
    # Fortam terminarea: dupa oprirea uvicorn (portul e deja eliberat), joburile
    # scheduler-ului (scrapere in ThreadPoolExecutor) pot lasa thread-uri
    # non-daemon care, prin atexit-join din concurrent.futures, ar tine procesul
    # in viata la nesfarsit. os._exit ocoleste asta si inchide efectiv aplicatia.
    os._exit(0)


if __name__ == "__main__":
    main()
