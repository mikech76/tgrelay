"""Счётчики активности для строки состояния в меню трея.

Считаем то, что реально проходит через прокси:
  * байты по каждому направлению (получено/отправлено);
  * сколько соединений открыто прямо сейчас и всего с момента запуска;
  * скорость за последние секунды (сглаженная).

Всё под одним замком: счётчики дёргаются из event loop, а читает их
поток трея.
"""
import threading
import time

import i18n
from i18n import t

_lock = threading.Lock()
_up_total = 0                   # байт отправлено клиентам..→наружу
_down_total = 0                 # байт получено извне → клиенту
_open_conns = 0
_conns_total = 0
_pool = None
_started = time.time()

_up_rate = 0.0                  # байт/с
_down_rate = 0.0
_last_sample = None             # (up, down, monotonic)

_sampler_started = False


def register(pool):
    """Пул прокси для строки состояния (достаточно одного — список общий)."""
    global _pool
    with _lock:
        if _pool is None:
            _pool = pool


def _pool_stats():
    pool = _pool
    if pool is None:
        return 0, 0
    try:
        return pool.alive_count, pool.count
    except Exception:
        proxies = getattr(pool, 'proxies', None) or []
        return sum(1 for p in proxies if getattr(p, 'alive', True)), len(proxies)


def conn_open():
    global _open_conns, _conns_total
    with _lock:
        _open_conns += 1
        _conns_total += 1


def conn_close():
    global _open_conns
    with _lock:
        if _open_conns > 0:
            _open_conns -= 1


def add(up=0, down=0):
    """Учесть прошедшие байты. up — от клиента, down — клиенту."""
    global _up_total, _down_total
    if not up and not down:
        return
    with _lock:
        _up_total += up
        _down_total += down
    _ensure_sampler()


def _ensure_sampler():
    global _sampler_started
    if _sampler_started:
        return
    _sampler_started = True
    threading.Thread(target=_sample_loop, daemon=True,
                     name='tgrelay-stats').start()


def _sample_loop():
    """Раз в секунду пересчитываем скорость (среднее по последним отсчётам)."""
    global _up_rate, _down_rate, _last_sample
    with _lock:
        _last_sample = (_up_total, _down_total, time.monotonic())
    history = []
    while True:
        time.sleep(1.0)
        now = time.monotonic()
        with _lock:
            up, down = _up_total, _down_total
            last_up, last_down, last_t = _last_sample
            _last_sample = (up, down, now)
        dt = max(now - last_t, 0.001)
        history.append(((up - last_up) / dt, (down - last_down) / dt))
        del history[:-6]                       # ~6 секунд сглаживания
        with _lock:
            _up_rate = sum(h[0] for h in history) / len(history)
            _down_rate = sum(h[1] for h in history) / len(history)


def snapshot():
    """Текущее состояние одним словарём (для меню трея)."""
    with _lock:
        up_total, down_total = _up_total, _down_total
        up_rate, down_rate = _up_rate, _down_rate
        conns, conns_total = _open_conns, _conns_total
    alive, total = _pool_stats()
    if not _sampler_started and (up_total or down_total):
        _ensure_sampler()
    return {
        'up_total': up_total,
        'down_total': down_total,
        'up_rate': up_rate,
        'down_rate': down_rate,
        'conns': conns,
        'conns_total': conns_total,
        'proxies_alive': alive,
        'proxies_total': total,
        'uptime': time.time() - _started,
    }


def human(n):
    """Байты по-человечески: 987 Б, 12,4 КБ, 3,1 МБ, 1,2 ГБ."""
    n = float(n)
    if n < 1024:
        return f'{int(n)} ' + t('unit_b')
    for key, size in (('unit_kb', 1024.0), ('unit_mb', 1024.0 ** 2),
                      ('unit_gb', 1024.0 ** 3)):
        if n < size * 1024:
            return _num(n / size) + ' ' + t(key)
    return _num(n / 1024.0 ** 3) + ' ' + t('unit_gb')


def _num(value):
    if i18n.lang() == 'ru':
        text = f'{value:.1f}' if value < 100 else f'{value:.0f}'
        return text.replace('.', ',')
    return f'{value:.1f}' if value < 100 else f'{value:.0f}'
