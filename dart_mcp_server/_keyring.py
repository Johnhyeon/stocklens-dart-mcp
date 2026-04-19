"""OS 키체인(Windows Credential Manager / macOS Keychain / Secret Service)을 통한
DART API 키 보관.

목적:
- claude_desktop_config.json에 키를 평문으로 박지 않기 위함.
- Windows DPAPI / macOS Keychain은 사용자 계정 단위로 자동 암호화하므로
  config 파일이 유출되어도 키는 노출되지 않는다.

헤드리스 환경(SSH, WSL, Docker)에는 keyring 백엔드가 없을 수 있다.
그 경우 KeyringUnavailableError를 발생시켜, 호출자가 fallback(예: 평문 모드 안내)을
제공할 수 있게 한다.
"""

from __future__ import annotations

# keyring은 startup-cost가 있을 수 있으므로 사용 시점에 import
SERVICE_NAME = "dart-mcp-server"
USERNAME = "DART_API_KEY"


class KeyringUnavailableError(RuntimeError):
    """OS keyring 백엔드가 없거나 접근 불가 (헤드리스 환경 등)."""


def _get_backend():
    """사용 가능한 keyring 모듈을 반환. 백엔드가 없거나 fail 백엔드면 예외."""
    try:
        import keyring
        from keyring.errors import NoKeyringError
        from keyring.backends import fail as fail_backend
    except ImportError as e:
        raise KeyringUnavailableError(
            f"keyring 라이브러리를 import할 수 없습니다: {e}"
        ) from e

    try:
        backend = keyring.get_keyring()
    except Exception as e:
        raise KeyringUnavailableError(f"keyring 백엔드 조회 실패: {e}") from e

    # fail.Keyring은 "no usable backend" 의미
    if isinstance(backend, fail_backend.Keyring):
        raise KeyringUnavailableError(
            "이 환경에서는 OS 키체인을 사용할 수 없습니다 "
            "(헤드리스/원격 세션 가능성). "
            "claude_desktop_config.json의 env에 DART_API_KEY를 직접 두려면 "
            "'dartmcp-setup --plaintext <KEY>' 를 사용하세요."
        )

    return keyring


def save(api_key: str) -> str:
    """키체인에 키 저장. 사용된 backend 이름 반환."""
    keyring = _get_backend()
    keyring.set_password(SERVICE_NAME, USERNAME, api_key)
    return type(keyring.get_keyring()).__name__


def load() -> str | None:
    """키체인에서 키 조회. 없거나 백엔드 부재면 None."""
    try:
        keyring = _get_backend()
    except KeyringUnavailableError:
        return None
    try:
        return keyring.get_password(SERVICE_NAME, USERNAME)
    except Exception:
        return None


def delete() -> bool:
    """키체인에서 키 삭제. 삭제 시도 성공 여부 반환 (없었으면 False)."""
    try:
        keyring = _get_backend()
    except KeyringUnavailableError:
        return False
    try:
        keyring.delete_password(SERVICE_NAME, USERNAME)
        return True
    except Exception:
        return False


def backend_name() -> str:
    """현재 활성 backend의 사람이 읽을 수 있는 이름. 사용 불가면 'unavailable'."""
    try:
        import keyring
        return type(keyring.get_keyring()).__name__
    except Exception:
        return "unavailable"
