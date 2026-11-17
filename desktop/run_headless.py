import asyncio
import logging
import logging.handlers
import os
import sys

from appdir import (ensure_env, fatal, log_path, notify_already_running,
                    single_instance)
from i18n import t


def _setup_logging():
    handlers = [logging.StreamHandler()]
    path = log_path('tgrelay.log')
    if path:
        try:
            handlers.append(logging.handlers.RotatingFileHandler(
                path, maxBytes=1_000_000, backupCount=2, encoding='utf-8'))
        except OSError:
            pass
    logging.basicConfig(
        level=logging.DEBUG if os.environ.get('TGRELAY_DEBUG') else logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=handlers,
    )


def main():
    if ensure_env() == 'created':
        return
    if not single_instance():
        notify_already_running()
        return
    if sys.platform == 'win32' and sys.version_info < (3, 14):
        asyncio.set_event_loop_policy(
            asyncio.WindowsSelectorEventLoopPolicy())
    _setup_logging()
    from server import start_server
    try:
        asyncio.run(start_server())
    except KeyboardInterrupt:
        print("\n" + t('stopped'))
    except Exception as exc:            # нет прокси, занят порт и т.п.
        logging.getLogger(__name__).exception("server failed")
        fatal(str(exc))
        sys.exit(1)


if __name__ == '__main__':
    main()
