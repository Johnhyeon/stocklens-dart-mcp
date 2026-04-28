"""Configure Claude Desktop to use dartlens.

Run `dartlens-setup` after `pip install dartlens-mcp`.

기본 동작 (권장):
    1. 키 입력받기 (인자 / 대화형 / DART_API_KEY env fallback)
    2. DART에 1회 호출해 키 유효성 검증 (삼성전자 corp_code 기준)
    3. 키를 OS 키체인에 저장 (Windows DPAPI / macOS Keychain / Secret Service)
    4. claude_desktop_config.json의 mcpServers.dartlens 엔트리 등록 — env에는 키를 두지 않음
    5. (마이그레이션) legacy `dart-mcp` 엔트리·평문 키는 자동 제거

평문 모드 (`--plaintext`):
    OS 키체인을 쓸 수 없는 환경(헤드리스 / 공유 계정 / 키체인이 막힌 정책)을 위한 fallback.
    이 경우 기존 동작처럼 env.DART_API_KEY를 JSON에 박는다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import sysconfig
from pathlib import Path

import httpx

from dartlens import _keyring as keyring_helper

SERVER_KEY = "dartlens"
LEGACY_KEYS: list[str] = ["dart-mcp"]

# 검증용: 삼성전자(00126380) — DART에 항상 존재하는 안정적 corp_code
_VALIDATE_URL = "https://opendart.fss.or.kr/api/company.json"
_VALIDATE_CORP_CODE = "00126380"


# ---------------------------------------------------------------------------
# 키 입력 / 검증
# ---------------------------------------------------------------------------

def _prompt_for_key() -> str:
    print()
    print("DART OpenAPI 키를 입력하세요.")
    print("(키가 없다면 https://opendart.fss.or.kr 에서 무료 발급)")
    print()
    try:
        key = input("DART_API_KEY: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit("입력이 취소되었습니다.")
    return key


async def _validate_key_async(api_key: str) -> tuple[bool, str]:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                _VALIDATE_URL,
                params={"crtfc_key": api_key, "corp_code": _VALIDATE_CORP_CODE},
            )
        resp.raise_for_status()
        data = resp.json()
        status = str(data.get("status", "")).strip()
        if status == "000":
            corp_name = data.get("corp_name", "(unknown)")
            return True, f"검증 성공 — {corp_name}"
        return False, f"DART 응답 [{status}]: {data.get('message', '알 수 없는 오류')}"
    except httpx.HTTPError as e:
        return False, f"네트워크 오류: {type(e).__name__}: {e}"
    except Exception as e:
        return False, f"오류: {type(e).__name__}: {e}"


def validate_key(api_key: str) -> tuple[bool, str]:
    return asyncio.run(_validate_key_async(api_key))


# ---------------------------------------------------------------------------
# Claude Desktop config 위치 / entry 결정
# ---------------------------------------------------------------------------

def _uv_tool_bin_dirs() -> list[Path]:
    """`uv tool install`이 entry point를 배치하는 경로 후보.

    uv는 `~/.local/bin` (Unix·Windows 공통)을 표준으로 쓰지만, 사용자가
    `UV_TOOL_BIN_DIR` / `XDG_BIN_HOME`로 재정의할 수 있다. 두 경우 다 커버.
    """
    candidates: list[Path] = []
    env = os.environ.get("UV_TOOL_BIN_DIR")
    if env:
        candidates.append(Path(env))
    xdg = os.environ.get("XDG_BIN_HOME")
    if xdg:
        candidates.append(Path(xdg))
    candidates.append(Path.home() / ".local" / "bin")
    return [p for p in candidates if p.exists()]


def resolve_server_entry(preferred_command: str = "dartlens") -> dict:
    """PATH 의존 없이 확실히 실행되는 MCP server config entry를 생성.

    우선순위:
    1. 절대 경로가 명시되면 그대로 사용
    2. PATH 탐색 (shutil.which)
    3. uv tool bin 디렉토리 직접 탐색 (`~/.local/bin` 등) — install 직후 PATH 미반영 케이스
    4. sysconfig scripts 디렉토리 직접 탐색 (pip 호환)
    5. 최후 fallback: `python -m dartlens`
    """
    if os.path.isabs(preferred_command) and Path(preferred_command).exists():
        return {"command": preferred_command}

    found = shutil.which(preferred_command)
    if found:
        return {"command": found}

    for bin_dir in _uv_tool_bin_dirs():
        for candidate_name in (f"{preferred_command}.exe", preferred_command):
            candidate = bin_dir / candidate_name
            if candidate.exists():
                return {"command": str(candidate)}

    try:
        scripts_dir = Path(sysconfig.get_paths()["scripts"])
        for candidate_name in (f"{preferred_command}.exe", preferred_command):
            candidate = scripts_dir / candidate_name
            if candidate.exists():
                return {"command": str(candidate)}
    except Exception:
        pass

    return {
        "command": sys.executable,
        "args": ["-m", "dartlens"],
    }


def _find_store_config_path() -> Path | None:
    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        return None
    packages_dir = Path(local_appdata) / "Packages"
    if not packages_dir.exists():
        return None
    for pattern in ("Claude_*", "*Claude*"):
        for pkg in packages_dir.glob(pattern):
            candidate = pkg / "LocalCache" / "Roaming" / "Claude" / "claude_desktop_config.json"
            if candidate.parent.exists():
                return candidate
    return None


def get_claude_desktop_config_path() -> Path:
    """Claude Desktop 앱의 mcpServers config 파일 경로."""
    if sys.platform == "win32":
        store = _find_store_config_path()
        if store is not None:
            return store
        appdata = os.environ.get("APPDATA")
        if not appdata:
            raise RuntimeError("APPDATA environment variable not found.")
        return Path(appdata) / "Claude" / "claude_desktop_config.json"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    else:
        return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def get_claude_code_config_path() -> Path:
    """Claude Code CLI의 사용자 스코프 config (`~/.claude.json`).

    Claude Code도 Claude Desktop과 동일하게 mcpServers 객체를 사용한다.
    파일에는 사용자 설정·세션 등 다른 키가 같이 들어있을 수 있어 mcpServers
    부분만 patching 한다.
    """
    return Path.home() / ".claude.json"


# 하위 호환 — 기존 import 자리 유지
def get_config_path() -> Path:
    return get_claude_desktop_config_path()


# (target name, 경로 함수, 사람이 읽는 라벨)
TARGETS: dict[str, tuple] = {
    "claude-desktop": (get_claude_desktop_config_path, "Claude Desktop"),
    "claude-code": (get_claude_code_config_path, "Claude Code CLI"),
}


# ---------------------------------------------------------------------------
# config 갱신
# ---------------------------------------------------------------------------

def _backup_and_load(config_path: Path) -> dict:
    if not config_path.exists():
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        backup = config_path.with_suffix(".json.backup")
        with open(backup, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(f"  [OK] Backup saved: {backup}")
        return config
    except json.JSONDecodeError:
        print("  [WARN] Existing config is corrupted. Creating new one.")
        return {}


def _store_api_key(api_key: str, *, plaintext: bool, env_for_entry: dict) -> dict | None:
    """API 키 저장 정책. 반환값은 entry에 박을 env dict (없으면 None).

    keyring 모드: env에서 DART_API_KEY 제거, keyring에 저장.
    plaintext 모드: env에 DART_API_KEY 박고 keyring 항목 삭제 (일관성).
    """
    env = dict(env_for_entry)
    if plaintext:
        env["DART_API_KEY"] = api_key
        if keyring_helper.delete():
            print("  [OK] Removed previous keyring entry (plaintext mode chosen)")
        print("  [WARN] PLAINTEXT mode — DART_API_KEY is stored unencrypted in JSON config")
        return env or None

    had_plain = "DART_API_KEY" in env
    env.pop("DART_API_KEY", None)
    if had_plain:
        print("  [OK] Migrated: removed plaintext DART_API_KEY from JSON config")

    try:
        backend = keyring_helper.save(api_key)
        print(f"  [OK] Stored in OS keychain ({backend})")
    except keyring_helper.KeyringUnavailableError as e:
        print(f"  [ERROR] {e}", file=sys.stderr)
        print(
            "  키체인을 쓸 수 없는 환경입니다. 평문 모드로 강제 저장하려면\n"
            "    dartlens-setup --plaintext <KEY>\n"
            "  를 사용하세요. (단, JSON 파일이 유출되면 키도 함께 노출됩니다.)",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return env or None


def _configure_one_target(
    config_path: Path,
    label: str,
    *,
    api_key: str,
    command: str,
    plaintext: bool,
    save_key: bool,
) -> None:
    """단일 config 파일(Claude Desktop 또는 Claude Code)에 mcpServers.dartlens 등록."""
    print()
    print(f"  → {label}")

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config = _backup_and_load(config_path)
    config.setdefault("mcpServers", {})

    for legacy in LEGACY_KEYS:
        if legacy in config["mcpServers"]:
            del config["mcpServers"][legacy]
            print(f"  [OK] Removed legacy entry: {legacy}")

    entry = resolve_server_entry(command)
    existing = config["mcpServers"].get(SERVER_KEY) or {}
    existing_env = dict(existing.get("env") or {})

    # 키 저장은 첫 타겟에서만 (여러 타겟이라도 keyring 한 번이면 충분)
    if save_key:
        env = _store_api_key(api_key, plaintext=plaintext, env_for_entry=existing_env)
    else:
        env = existing_env if plaintext else (
            {k: v for k, v in existing_env.items() if k != "DART_API_KEY"} or None
        )
        # plaintext 모드에서 동일 키를 모든 타겟 entry에 박아두기
        if plaintext:
            env = dict(env or {})
            env["DART_API_KEY"] = api_key

    if env:
        entry["env"] = env

    config["mcpServers"][SERVER_KEY] = entry

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    print(f"  [OK] Config updated (key: {SERVER_KEY})")
    print(f"  Path:    {config_path}")
    print(f"  Command: {entry['command']}")
    if "args" in entry:
        print(f"  Args:    {' '.join(entry['args'])}")
    if "env" in entry and entry["env"]:
        if plaintext:
            print(f"  Env:     DART_API_KEY=***{api_key[-4:]} (plaintext)")
        else:
            print(f"  Env:     {list(entry['env'].keys())} (no DART_API_KEY — keychain)")
    else:
        print("  Env:     (none — DART_API_KEY in keychain)")

    cmd = entry["command"]
    if Path(cmd).is_absolute() and not Path(cmd).exists():
        print(f"  [WARN] Recorded command file does not exist: {cmd}")
    elif not Path(cmd).is_absolute() and not shutil.which(cmd):
        print(f"  [WARN] '{cmd}' not found in PATH.")


def configure(
    api_key: str,
    *,
    command: str = "dartlens",
    plaintext: bool,
    targets: list[str] | None = None,
) -> None:
    """선택된 모든 타겟에 dartlens MCP 등록.

    targets: ["claude-desktop"], ["claude-code"], 또는 ["claude-desktop", "claude-code"].
    기본값은 ["claude-desktop"] (하위 호환).
    """
    targets = targets or ["claude-desktop"]
    unknown = [t for t in targets if t not in TARGETS]
    if unknown:
        raise ValueError(f"Unknown target(s): {unknown}. Valid: {list(TARGETS.keys())}")

    for i, target in enumerate(targets):
        path_func, label = TARGETS[target]
        _configure_one_target(
            path_func(),
            label,
            api_key=api_key,
            command=command,
            plaintext=plaintext,
            save_key=(i == 0),  # 키 저장은 첫 타겟에서만
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dartlens-setup",
        description="Register dartlens in Claude config (Desktop and/or Code CLI) and store the DART API key.",
    )
    p.add_argument(
        "api_key",
        nargs="?",
        help="DART OpenAPI 키. 생략 시 대화형 입력 또는 DART_API_KEY 환경변수.",
    )
    p.add_argument(
        "--target",
        choices=["claude-desktop", "claude-code", "both", "auto"],
        default="auto",
        help=(
            "MCP 등록 대상. "
            "claude-desktop=Claude Desktop 앱, claude-code=Claude Code CLI, "
            "both=둘 다, auto=환경 자동 감지 (기본: auto). "
            "DARTLENS_TARGET 환경변수로도 지정 가능."
        ),
    )
    p.add_argument(
        "--command",
        default="dartlens",
        help="MCP 클라이언트가 실행할 커맨드 (기본: dartlens).",
    )
    p.add_argument(
        "--plaintext",
        action="store_true",
        help="OS 키체인 대신 config env에 키를 평문 저장 (헤드리스 환경 fallback).",
    )
    return p


def _resolve_targets(arg: str) -> list[str]:
    """`--target` 인자를 실제 타겟 리스트로 해석. `auto`는 환경 감지."""
    if arg == "both":
        return ["claude-desktop", "claude-code"]
    if arg in TARGETS:
        return [arg]
    if arg == "auto":
        # env 우선
        env_target = (os.environ.get("DARTLENS_TARGET") or "").strip().lower()
        if env_target and env_target != "auto":
            return _resolve_targets(env_target)

        # 자동 감지:
        #   1. `claude` CLI 존재 = Claude Code 사용 환경
        #   2. Claude Desktop config 디렉토리 존재 = Desktop 사용 환경
        #   3. 둘 다면 both, 둘 다 아니면 claude-desktop (가장 흔한 케이스)
        has_code = shutil.which("claude") is not None
        desktop_dir = get_claude_desktop_config_path().parent
        has_desktop = desktop_dir.exists()

        if has_code and has_desktop:
            return ["claude-desktop", "claude-code"]
        if has_code:
            return ["claude-code"]
        return ["claude-desktop"]
    raise ValueError(f"Invalid target: {arg}")


def main() -> None:
    print("==============================================")
    print("  dartlens — MCP Setup")
    print("==============================================")

    args = _build_parser().parse_args()
    targets = _resolve_targets(args.target)
    target_labels = ", ".join(TARGETS[t][1] for t in targets)
    print(f"  Targets: {target_labels}")

    api_key = (args.api_key or os.environ.get("DART_API_KEY", "")).strip()
    if not api_key:
        api_key = _prompt_for_key()
    if not api_key:
        print("  [ERROR] DART API 키가 입력되지 않았습니다.", file=sys.stderr)
        sys.exit(1)

    print()
    print("  Validating API key against DART...")
    ok, msg = validate_key(api_key)
    if not ok:
        print(f"  [ERROR] 키 검증 실패: {msg}", file=sys.stderr)
        print(
            "  키가 올바른지, DART(https://opendart.fss.or.kr)에서 발급받은 키인지 확인하세요.",
            file=sys.stderr,
        )
        sys.exit(2)
    print(f"  [OK] {msg}")

    try:
        configure(
            api_key,
            command=args.command,
            plaintext=args.plaintext,
            targets=targets,
        )
    except SystemExit:
        raise
    except Exception as e:
        print(f"  [ERROR] {e}", file=sys.stderr)
        sys.exit(3)

    print()
    if "claude-desktop" in targets:
        print("Done! Claude Desktop을 완전히 종료(트레이→Quit) 후 다시 실행하세요.")
    if "claude-code" in targets:
        print("Done! Claude Code 세션에서 자동 적용 — 새 세션부터 dartlens 도구 사용 가능.")


if __name__ == "__main__":
    main()
