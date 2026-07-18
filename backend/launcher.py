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


# ── UI (PKG-4): fereastra nativa pywebview/WebView2 cu fallback pe browser ───────
def _window_mode_enabled() -> bool:
    """Fereastra nativa (pywebview) e activa cand NU e fortat browserul
    (FLIPRADAR_NO_WINDOW != "1") SI fie suntem sub PyInstaller (frozen), fie in
    dev cu FLIPRADAR_WINDOW=1. In dev fara flag ramane comportamentul istoric
    (browser), ca sa nu deranjeze fluxul de dezvoltare."""
    if os.environ.get("FLIPRADAR_NO_WINDOW") == "1":
        return False
    if getattr(sys, "frozen", False):
        return True
    return os.environ.get("FLIPRADAR_WINDOW") == "1"


def _run_tray_browser(url: str, app_version: str, server_thread) -> None:
    """Ramura clasica (fallback + FLIPRADAR_NO_WINDOW + dev implicit): deschide
    UI-ul in browserul implicit + tray pystray BLOCANT (icon.run()). Logica e
    EXACT cea de dinainte de PKG-4; blocheaza pana la Iesire/Ctrl+C, apoi revine
    ca main() sa faca shutdown-ul comun."""
    webbrowser.open(url)
    try:
        import pystray
        icon = pystray.Icon(
            "flipradar", _make_icon_image(), f"FlipRadar v{app_version}",
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
            while server_thread.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            pass


def _open_window(url: str, app_version: str, on_exit) -> None:
    """Ramura fereastra nativa (pywebview/WebView2) peste ACELASI server local.
    X = ascunde fereastra in tray (procesul + scanerele raman vii); Iesire din
    tray inchide efectiv. Orice esec de import/creare ridica exceptie -> apelantul
    (main) face fallback pe browser. webview.start() e BLOCANT pe main thread;
    dupa revenire (destroy la Iesire) cheama on_exit() (shutdown-ul comun)."""
    import webview  # import in interior: fail -> fallback la apelant

    window = webview.create_window(
        f"FlipRadar v{app_version}", url,
        width=1280, height=800, min_size=(1024, 640))

    exiting = threading.Event()

    def _on_closing():
        # X pe fereastra: daca nu iesim efectiv, ascundem in tray si ANULAM
        # inchiderea. pywebview 5 pe WebView2 (winforms): return False ->
        # args.Cancel=True (evenimentul `closing` e locking, deci valoarea conteaza).
        if not exiting.is_set():
            window.hide()
            return False
        return True

    window.events.closing += _on_closing

    # Tray-ul porneste INAINTE de webview.start() (blocant) si ruleaza detasat.
    import pystray

    def _show(icon, item):
        try:
            window.show()
        except Exception:
            webbrowser.open(url)  # fereastra a murit -> deschidem browserul

    def _exit(icon, item):
        exiting.set()
        try:
            window.destroy()
        except Exception:
            pass
        icon.stop()

    icon = pystray.Icon(
        "flipradar", _make_icon_image(), f"FlipRadar v{app_version}",
        menu=pystray.Menu(
            pystray.MenuItem("Deschide FlipRadar", _show, default=True),
            pystray.MenuItem("Ieșire", _exit),
        ))
    icon.run_detached()

    try:
        webview.start()  # blocant pe MAIN THREAD pana la destroy
    except Exception:
        try:
            icon.stop()
        except Exception:
            pass
        raise  # -> fallback browser in main
    try:
        icon.stop()  # daca fereastra s-a inchis fara Iesire, oprim si tray-ul
    except Exception:
        pass
    on_exit()


def _open_viewer(url: str, app_version: str) -> None:
    """A doua instanta: doar o fereastra-viewer catre instanta existenta. Fara
    tray, fara server; webview.start() blocheaza pana la inchidere, apoi return."""
    import webview
    webview.create_window(
        f"FlipRadar v{app_version}", url,
        width=1280, height=800, min_size=(1024, 640))
    webview.start()


def _selfcheck() -> int:
    """Diagnostic per componenta (PKG-3b). Rulat la validarea build-ului si
    pentru suport DUPA release (`FlipRadar.exe --selfcheck`). Fiecare
    componenta in try/except cu [OK]/[FAIL]. Exit 0 daca ESENTIALELE merg
    (Chrome real e informativ — exista fallback pe Chromium/patchright).
    Sub frozen scrie rezultatul si in <data_dir>/selfcheck_result.txt, usor
    de gasit de utilizator la suport."""
    results = []
    total = 0
    ok = 0
    essential_ok = True

    def run(name, fn, essential=True):
        nonlocal total, ok, essential_ok
        total += 1
        try:
            detail = fn()
            results.append(f"[OK]   {name}" + (f" — {detail}" if detail else ""))
            ok += 1
        except Exception as exc:
            results.append(f"[FAIL] {name} — {type(exc).__name__}: {str(exc)[:140]}")
            if essential:
                essential_ok = False

    def _env():
        from app.version import APP_VERSION
        from app.paths import get_data_dir
        dd = get_data_dir()
        try:
            from app.main import FRONTEND_OUT
            fo = f"frontend_out={FRONTEND_OUT} (exista={FRONTEND_OUT.is_dir()})"
        except Exception as exc:
            fo = f"frontend_out=EROARE:{exc}"
        return (f"FlipRadar v{APP_VERSION}, Python {sys.version.split()[0]}, "
                f"frozen={getattr(sys, 'frozen', False)}, data_dir={dd}; {fo}")

    def _curl_cffi():
        from curl_cffi import requests as cffi_req
        code = cffi_req.get("https://www.olx.ro", impersonate="chrome110",
                            timeout=10).status_code
        if code >= 500:
            raise RuntimeError(f"status {code}")
        return f"olx.ro -> HTTP {code}"

    def _patchright():
        from patchright.sync_api import sync_playwright
        p = sync_playwright().start()
        p.stop()
        return "driver Node pornit"

    def _playwright():
        from playwright.sync_api import sync_playwright
        p = sync_playwright().start()
        p.stop()
        return "driver Node pornit"

    def _chrome():
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch(headless=True, channel="chrome")
            b.close()
        return "Google Chrome real pornit"

    run("mediu", _env)
    run("curl_cffi (HTTP live)", _curl_cffi)
    run("patchright", _patchright)
    run("playwright", _playwright)
    run("chrome (informativ)", _chrome, essential=False)

    summary = f"SELFCHECK: {ok}/{total} componente OK"
    report = "\n".join(["===== FlipRadar --selfcheck ====="] + results + [summary])
    print(report)

    if getattr(sys, "frozen", False):
        try:
            from app.paths import get_data_dir
            out = get_data_dir() / "selfcheck_result.txt"
            out.write_text(report + "\n", encoding="utf-8")
            print(f"[Selfcheck] Rezultat scris si in {out}")
        except Exception as exc:
            print(f"[Selfcheck] Nu am putut scrie selfcheck_result.txt: {exc}")

    return 0 if essential_ok else 1


def main() -> None:
    _setup_frozen_logging()
    if "--selfcheck" in sys.argv:
        sys.exit(_selfcheck())
    port, already = _choose_port()
    url = f"http://127.0.0.1:{port}"
    if already:
        # A doua instanta: NU pornim server. In mod fereastra deschidem un viewer
        # catre instanta existenta (inchiderea lui nu atinge prima instanta);
        # altfel (mod browser sau esec) deschidem browserul, ca inainte.
        print(f"[Launcher] FlipRadar ruleaza deja la {url}.")
        if _window_mode_enabled():
            try:
                from app.version import APP_VERSION
                _open_viewer(url, APP_VERSION)
                return
            except Exception as exc:
                print(f"[Launcher] Fereastra indisponibilă ({exc}) — deschid browserul.")
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

    def _finalize():
        # Secventa finala UNICA si comuna ambelor ramuri (fereastra si browser).
        # Fortam terminarea: dupa oprirea uvicorn (portul e deja eliberat),
        # joburile scheduler-ului (scrapere in ThreadPoolExecutor) pot lasa
        # thread-uri non-daemon care, prin atexit-join din concurrent.futures, ar
        # tine procesul viu la nesfarsit. os._exit ocoleste asta si inchide efectiv.
        _shutdown(server)
        t.join(timeout=10)
        os._exit(0)

    if _window_mode_enabled():
        try:
            _open_window(url, APP_VERSION, on_exit=_finalize)
            return  # _open_window -> on_exit=_finalize -> os._exit(0); nu se mai revine
        except Exception as exc:
            print(f"[Launcher] Fereastra indisponibilă ({exc}) — deschid browserul.")

    # Mod browser: FLIPRADAR_NO_WINDOW / dev implicit, sau fallback dupa esecul ferestrei.
    _run_tray_browser(url, APP_VERSION, t)
    _finalize()


if __name__ == "__main__":
    main()
