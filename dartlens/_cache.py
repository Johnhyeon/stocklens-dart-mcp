"""TTL 캐시 — 공시는 사실상 불변(정정공시 제외)이라 길게 잡는다.

기본 정책:
- 공시 목록 / 검색 결과: 5분 (신규 공시 반영 위해 짧게)
- 공시 본문 / 재무제표 / 기업개황: 24시간 (불변에 가까움)

stocklens처럼 장중/장마감 구분이 필요 없다 — 공시는 시간대 무관.
"""

from __future__ import annotations

import asyncio
import time
from functools import wraps
from typing import Any, Awaitable, Callable

_cache: dict[str, tuple[float, Any]] = {}
_lock = asyncio.Lock()


def _make_key(func_name: str, args: tuple, kwargs: dict) -> str:
    parts = [func_name]
    parts.extend(repr(a) for a in args)
    parts.extend(f"{k}={v!r}" for k, v in sorted(kwargs.items()))
    return "|".join(parts)


def cached(ttl_seconds: int):
    """async 함수 결과를 고정 TTL로 캐싱."""

    def decorator(func: Callable[..., Awaitable[Any]]):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            key = _make_key(func.__name__, args, kwargs)

            async with _lock:
                entry = _cache.get(key)
                if entry is not None:
                    expiry, value = entry
                    if time.time() < expiry:
                        return value
                    del _cache[key]

            result = await func(*args, **kwargs)

            async with _lock:
                _cache[key] = (time.time() + ttl_seconds, result)

            return result

        return wrapper

    return decorator


def clear_cache() -> None:
    _cache.clear()


def cache_stats() -> dict:
    now = time.time()
    active = sum(1 for exp, _ in _cache.values() if exp > now)
    return {
        "total_entries": len(_cache),
        "active_entries": active,
        "expired_entries": len(_cache) - active,
    }
