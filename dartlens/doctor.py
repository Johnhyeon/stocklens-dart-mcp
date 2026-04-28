"""dartlens 설치·설정 진단 도구.

실행: `dartlens-doctor` 또는 `python -m dartlens.doctor`

체크 항목:
- uv 설치 여부 (Python 런타임 관리자)
- dartlens-mcp 패키지 import 가능 여부
- dartlens 실행 명령 탐색 (PATH / uv tool bin / sysconfig)
- Claude Desktop config 파일
- config 내 dartlens entry 유효성 (command resolvable)
- Legacy 키 잔존 여부
- DART API 키 출처 (env / keychain) — 키 자체는 출력하지 않음
"""

import json
import os
import shutil
import sys
import sysconfig
from pathlib import Path

try:
    from dartlens.setup_claude import (
        get_config_path,
        SERVER_KEY,
        LEGACY_KEYS,
        _uv_tool_bin_dirs,
        _find_store_config_path,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from dartlens.setup_claude import (
        get_config_path,
        SERVER_KEY,
        LEGACY_KEYS,
        _uv_tool_bin_dirs,
        _find_store_config_path,
    )


class Check:
    def __init__(self, name: str):
        self.name = name
        self.status = None  # "ok" / "warn" / "fail"
        self.lines: list[str] = []
        self.fix: str | None = None

    def ok(self, msg: str):
        self.status = "ok"
        self.lines.append(msg)
        return self

    def warn(self, msg: str, fix: str | None = None):
        if self.status != "fail":
            self.status = "warn"
        self.lines.append(msg)
        if fix:
            self.fix = fix
        return self

    def fail(self, msg: str, fix: str | None = None):
        self.status = "fail"
        self.lines.append(msg)
        if fix:
            self.fix = fix
        return self

    def info(self, msg: str):
        self.lines.append(msg)
        return self


def check_uv() -> Check:
    c = Check("uv (Python runtime manager)")
    uv = shutil.which("uv")
    if uv:
        c.ok("uv is installed")
        c.info(f"Path:       {uv}")
    else:
        c.warn(
            "uv not found in PATH",
            fix=(
                "Install uv (recommended):\n"
                "  Windows: irm https://astral.sh/uv/install.ps1 | iex\n"
                "  macOS/Linux: curl -LsSf https://astral.sh/uv/install.sh | sh"
            ),
        )
    return c


def check_package() -> Check:
    c = Check("Package (dartlens-mcp)")
    try:
        import dartlens  # noqa: F401
        c.ok("dartlens-mcp is importable")
        c.info(f"Location:   {Path(dartlens.__file__).parent}")
        c.info(f"Version:    {dartlens.__version__}")
        c.info(f"Python:     {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
        c.info(f"Executable: {sys.executable}")
    except ImportError:
        c.fail(
            "dartlens-mcp NOT importable in current interpreter",
            fix="uv tool install --force dartlens-mcp",
        )
    return c


def check_dartlens_command() -> Check:
    c = Check("Command (dartlens)")
    exe = shutil.which("dartlens")
    if exe:
        c.ok("'dartlens' found in PATH")
        c.info(f"Path:       {exe}")
        return c

    for bin_dir in _uv_tool_bin_dirs():
        for name in ("dartlens.exe", "dartlens"):
            candidate = bin_dir / name
            if candidate.exists():
                c.warn(
                    "'dartlens' exists but not on PATH",
                    fix=(
                        f'Add to PATH: "{bin_dir}"\n'
                        f"(or proceed — setup_claude will use absolute path)"
                    ),
                )
                c.info(f"Path:       {candidate}")
                return c

    try:
        scripts_dir = Path(sysconfig.get_paths()["scripts"])
        for name in ("dartlens.exe", "dartlens"):
            candidate = scripts_dir / name
            if candidate.exists():
                c.warn(
                    "'dartlens' exists in sysconfig scripts but not on PATH",
                    fix=f'Add to PATH: "{scripts_dir}"',
                )
                c.info(f"Path:       {candidate}")
                return c
    except Exception:
        pass

    c.fail(
        "'dartlens' command NOT found anywhere",
        fix="uv tool install --force dartlens-mcp",
    )
    return c


def check_config() -> Check:
    c = Check("Claude Desktop Config")
    config_path = get_config_path()

    if "Packages" in str(config_path) and "LocalCache" in str(config_path):
        c.info("Detected: Microsoft Store version (sandboxed path)")
    c.info(f"Path:       {config_path}")

    store = _find_store_config_path()
    std_appdata = os.environ.get("APPDATA")
    std_path = (
        Path(std_appdata) / "Claude" / "claude_desktop_config.json"
        if std_appdata
        else None
    )
    if (
        store
        and std_path
        and store.exists()
        and std_path.exists()
        and store != std_path
    ):
        c.warn(
            f"Both Store and standard config files exist. Active: {config_path}",
            fix=f"Remove unused: {std_path if config_path == store else store}",
        )

    if not config_path.exists():
        c.fail(
            "Config file does not exist",
            fix="dartlens-setup",
        )
        return c

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except json.JSONDecodeError as e:
        c.fail(
            f"Config is not valid JSON: {e}",
            fix="Back up and re-run dartlens-setup",
        )
        return c
    except Exception as e:
        c.fail(f"Cannot read config: {e}")
        return c

    servers = cfg.get("mcpServers", {}) or {}
    entry = servers.get(SERVER_KEY)

    legacy_found = [k for k in LEGACY_KEYS if k in servers]
    if legacy_found:
        c.warn(
            f"Legacy entries present: {legacy_found}",
            fix="dartlens-setup (auto-removes)",
        )

    if not entry:
        c.fail(
            f"'{SERVER_KEY}' entry missing in mcpServers",
            fix="dartlens-setup",
        )
        return c

    cmd = entry.get("command")
    args = entry.get("args", [])
    c.info(f"Command:    {cmd}")
    if args:
        c.info(f"Args:       {args}")

    if not cmd:
        c.fail("Entry has no 'command' field")
        return c

    if Path(cmd).is_absolute():
        if Path(cmd).exists():
            c.ok("Command points to existing file")
        else:
            c.fail(
                f"Command file missing: {cmd}",
                fix="dartlens-setup",
            )
    else:
        resolved = shutil.which(cmd)
        if resolved:
            c.ok(f"Command resolvable via PATH: {resolved}")
        else:
            c.fail(
                f"Command '{cmd}' not in PATH — Claude Desktop will fail to launch",
                fix="dartlens-setup",
            )

    return c


def check_api_key() -> Check:
    """DART_API_KEY 출처 점검. 키 값 자체는 출력하지 않음 (마지막 4자리만)."""
    c = Check("DART API Key")
    env_key = (os.environ.get("DART_API_KEY") or "").strip()
    if env_key:
        c.ok("Found in DART_API_KEY environment variable")
        c.info(f"Tail4:      ***{env_key[-4:]}")
        return c

    try:
        from dartlens import _keyring as keyring_helper

        stored = (keyring_helper.load() or "").strip()
        if stored:
            c.ok(f"Found in OS keychain ({keyring_helper.backend_name()})")
            c.info(f"Tail4:      ***{stored[-4:]}")
            return c
    except Exception as e:
        c.warn(f"keyring lookup failed: {e}")

    c.fail(
        "No DART API key found (env or keychain)",
        fix="dartlens-setup <YOUR_DART_API_KEY>",
    )
    return c


STATUS_ICON = {"ok": "[ OK ]", "warn": "[WARN]", "fail": "[FAIL]", None: "[ ?  ]"}


def print_check(c: Check):
    icon = STATUS_ICON.get(c.status, "[ ?  ]")
    print(f"{icon} {c.name}")
    for line in c.lines:
        print(f"       {line}")
    if c.fix:
        print(f"       Fix: {c.fix}")
    print()


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("=" * 60)
    print("  dartlens Doctor - Installation Diagnosis")
    print("=" * 60)
    print()

    checks = [
        check_uv(),
        check_package(),
        check_dartlens_command(),
        check_config(),
        check_api_key(),
    ]

    for c in checks:
        print_check(c)

    any_fail = any(c.status == "fail" for c in checks)
    any_warn = any(c.status == "warn" for c in checks)

    print("=" * 60)
    if any_fail:
        print("  [FAIL] One or more critical issues found.")
        print("  Apply the 'Fix:' commands above, then re-run dartlens-doctor.")
        sys.exit(1)
    elif any_warn:
        print("  [WARN] Installation works but some warnings exist.")
        print("  If MCP appears in Claude Desktop, you're fine.")
    else:
        print("  [ OK ] All checks passed!")
        print("  If MCP still doesn't appear, FULLY QUIT Claude Desktop")
        print("  (tray icon -> Quit) and restart.")
    print("=" * 60)


if __name__ == "__main__":
    main()
