"""DART MCP Server — 금융감독원 OpenDART API 래퍼."""
try:
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("stocklens-dart-mcp")
except Exception:
    __version__ = "0.0.0"
