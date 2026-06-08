"""Materials Project 检索结果本地缓存与超时降级。"""

from __future__ import annotations

import json
import os
import time
from typing import Any

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'mp_search_cache')
CACHE_TTL_SEC = int(os.environ.get('MP_CACHE_TTL_SEC', str(7 * 24 * 3600)))
MP_TIMEOUT_SEC = float(os.environ.get('MP_SEARCH_TIMEOUT_SEC', '3.0'))


def _cache_path(query: str) -> str:
    safe = ''.join(c if c.isalnum() or c in '-_' else '_' for c in query.strip().lower())[:80]
    return os.path.join(CACHE_DIR, f'{safe or "empty"}.json')


def load_cache(query: str) -> list[dict[str, Any]] | None:
    path = _cache_path(query)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            blob = json.load(f)
        if time.time() - blob.get('ts', 0) > CACHE_TTL_SEC:
            return None
        return blob.get('materials') or []
    except Exception:
        return None


def save_cache(query: str, materials: list[dict[str, Any]]) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(query)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'ts': time.time(), 'query': query, 'materials': materials}, f, ensure_ascii=False, default=str)


def search_mp_with_fallback(query: str, search_fn, search_in: str = 'property') -> tuple[list, str]:
    """
    search_fn: callable returning list
    返回 (materials, source_tag)  source_tag: live | cache | empty
    """
    try:
        import signal

        def _timeout_handler(signum, frame):
            raise TimeoutError('MP search timeout')

        if hasattr(signal, 'SIGALRM'):
            signal.signal(signal.SIGALRM, _timeout_handler)
            signal.setitimer(signal.ITIMER_REAL, MP_TIMEOUT_SEC)
        try:
            results = search_fn()
        finally:
            if hasattr(signal, 'SIGALRM'):
                signal.setitimer(signal.ITIMER_REAL, 0)
        if results:
            try:
                save_cache(query, results)
            except Exception:
                pass
            return results, 'live'
    except Exception:
        pass

    cached = load_cache(query)
    if cached is not None:
        return cached, 'cache'
    return [], 'empty'
