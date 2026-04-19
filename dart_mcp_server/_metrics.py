"""MCP 도구 호출 메트릭 (JSONL).

저장 위치: ~/.dart-mcp-server/logs/metrics_YYYYMMDD.jsonl

stocklens 메트릭과 호환되는 스키마로 기록한다 (timestamp/tool/duration_ms/output_chars/error).
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from functools import wraps
from pathlib import Path
from typing import Any, Awaitable, Callable


def get_data_dir() -> Path:
    """사용자 홈 아래 dart-mcp-server 데이터 디렉토리."""
    folder = Path.home() / ".dart-mcp-server"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def get_metrics_dir() -> Path:
    folder = get_data_dir() / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def get_metrics_file() -> Path:
    return get_metrics_dir() / f"metrics_{datetime.now():%Y%m%d}.jsonl"


def _sanitize_kwargs(kwargs: dict) -> dict:
    out = {}
    for k, v in kwargs.items():
        if isinstance(v, (str, int, float, bool, type(None))):
            out[k] = v[:47] + "..." if isinstance(v, str) and len(v) > 50 else v
        elif isinstance(v, (list, tuple)):
            out[k] = f"<list len={len(v)}>"
        elif isinstance(v, dict):
            out[k] = f"<dict keys={list(v.keys())}>"
        else:
            out[k] = f"<{type(v).__name__}>"
    return out


def track_metrics(tool_name: str) -> Callable:
    def decorator(func: Callable[..., Awaitable[Any]]):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.monotonic()
            error_type: str | None = None
            result_text = ""
            try:
                result = await func(*args, **kwargs)
                if result is not None:
                    result_text = str(result)
                return result
            except Exception as e:
                error_type = type(e).__name__
                raise
            finally:
                duration_ms = round((time.monotonic() - start) * 1000, 1)
                try:
                    record = {
                        "timestamp": datetime.now().isoformat(timespec="seconds"),
                        "tool": tool_name,
                        "kwargs": _sanitize_kwargs(kwargs),
                        "duration_ms": duration_ms,
                        "output_chars": len(result_text),
                        "cache_hit": duration_ms < 10.0,
                        "error": error_type,
                    }
                    with open(get_metrics_file(), "a", encoding="utf-8") as f:
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
                except Exception:
                    pass

        return wrapper

    return decorator
