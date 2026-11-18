import asyncio
import logging
import logging.handlers
import os
import sys
import threading
import traceback

from appdir import (ensure_env, fatal, log_path, notify_already_running,
                    single_instance)


def _setup_logging():
    handlers = []
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler())

    path = log_path('tgrelay.log')
    if path:
        try:
            handlers.append(logging.handlers.RotatingFileHandler(
                path, maxBytes=1_000_000, backupCount=2, encoding='utf-8'))
        except OSError:
            pass

    logging.basicConfig(
        level=logging.DEBUG if os.environ.get('MTPROXY_DEBUG') else logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=handlers,
    )


def run_server():
    if sys.platform == 'win32' and sys.version_info < (3, 14):
        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy())

    from server import start_server
    try:
        asyncio.run(start_server())
    except Exception as exc:            # нет прокси, занят порт и т.п.
        logging.getLogger(__name__).exception("server failed")
        fatal(str(exc))
        os._exit(1)


def _log_unhandled(exc_type, exc, tb):
    """В windowed-сборке stderr нет — любую ошибку кладём в tgrelay.log."""
    logging.getLogger('tgrelay').error(
        'Unhandled exception:\n%s',
        ''.join(traceback.format_exception(exc_type, exc, tb)))


def main():
    if ensure_env() == 'created':
        return
    wait = 15.0 if os.environ.get('TGRELAY_HANDOFF') else 0.0
    if not single_instance(wait):
        notify_already_running()
        return

    _setup_logging()
    sys.excepthook = _log_unhandled
    threading.excepthook = lambda args: _log_unhandled(
        args.exc_type, args.exc_value, args.exc_traceback)

    t = threading.Thread(target=run_server, daemon=True)
    t.start()

    from tray_app import TrayApp
    TrayApp().run()


if __name__ == '__main__':
    main()
