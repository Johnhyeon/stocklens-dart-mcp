"""_validate.py 순수 함수 단위 테스트 — 네트워크 없이 빠르게 회귀 잡기.

pytest 또는 `python tests/test_validate.py` 둘 다 동작.
의존성 추가 없음 (assert + 카운터).
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dart_mcp_server._validate import (
    days_to_range,
    normalize_bsns_year,
    normalize_corp_code,
    normalize_fs_div,
    normalize_rcept_no,
    normalize_reprt_code,
    normalize_sj_div,
    normalize_stock_code,
    normalize_yyyymmdd,
    reprt_code_label,
)


# ---------------------------------------------------------------------------
# Test runner — pytest 없이도 동작
# ---------------------------------------------------------------------------

_PASS = 0
_FAIL = 0
_FAILED_NAMES: list[str] = []


def expect(name: str, condition: bool, hint: str = "") -> None:
    global _PASS, _FAIL
    if condition:
        _PASS += 1
        print(f"  PASS {name}")
    else:
        _FAIL += 1
        _FAILED_NAMES.append(name)
        print(f"  FAIL {name}{' — ' + hint if hint else ''}")


def expect_raises(name: str, exc_type: type, fn, *args, **kwargs) -> None:
    global _PASS, _FAIL
    try:
        result = fn(*args, **kwargs)
        _FAIL += 1
        _FAILED_NAMES.append(name)
        print(f"  FAIL {name} — expected {exc_type.__name__}, got result {result!r}")
    except exc_type:
        _PASS += 1
        print(f"  PASS {name}")
    except Exception as e:
        _FAIL += 1
        _FAILED_NAMES.append(name)
        print(f"  FAIL {name} — expected {exc_type.__name__}, got {type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_corp_code() -> None:
    print("\n[normalize_corp_code]")
    expect("ok 8자리", normalize_corp_code("00126380") == "00126380")
    expect("strip 공백", normalize_corp_code("  00126380  ") == "00126380")
    expect_raises("None reject", ValueError, normalize_corp_code, None)
    expect_raises("7자리 reject", ValueError, normalize_corp_code, "1234567")
    expect_raises("9자리 reject", ValueError, normalize_corp_code, "123456789")
    expect_raises("문자 포함 reject", ValueError, normalize_corp_code, "0012638A")


def test_stock_code() -> None:
    print("\n[normalize_stock_code]")
    expect("숫자 6자리", normalize_stock_code("005930") == "005930")
    expect("영문 포함 6자리", normalize_stock_code("0088M0") == "0088M0")  # 메쥬
    expect_raises("5자리 reject", ValueError, normalize_stock_code, "12345")
    expect_raises("7자리 reject", ValueError, normalize_stock_code, "1234567")
    expect_raises("특수문자 reject", ValueError, normalize_stock_code, "12-345")


def test_yyyymmdd() -> None:
    print("\n[normalize_yyyymmdd]")
    expect("ok 8자리", normalize_yyyymmdd("20240315") == "20240315")
    expect("dash 정규화", normalize_yyyymmdd("2024-03-15") == "20240315")
    expect("slash 정규화", normalize_yyyymmdd("2024/03/15") == "20240315")
    expect("dot 정규화", normalize_yyyymmdd("2024.03.15") == "20240315")
    expect_raises("None reject", ValueError, normalize_yyyymmdd, None)
    expect_raises("invalid month", ValueError, normalize_yyyymmdd, "20241315")
    expect_raises("not a date string", ValueError, normalize_yyyymmdd, "abcdefgh")


def test_bsns_year() -> None:
    print("\n[normalize_bsns_year]")
    expect("ok int", normalize_bsns_year(2024) == "2024")
    expect("ok str", normalize_bsns_year("2024") == "2024")
    expect_raises("3자리 reject", ValueError, normalize_bsns_year, "202")
    expect_raises("문자 reject", ValueError, normalize_bsns_year, "abcd")
    expect_raises("1900 reject (1980 미만)", ValueError, normalize_bsns_year, 1900)
    expect_raises("미래 너무 멀리 reject", ValueError, normalize_bsns_year, 2099)


def test_reprt_code() -> None:
    print("\n[normalize_reprt_code]")
    expect("annual → 11011", normalize_reprt_code("annual") == "11011")
    expect("Annual case-insensitive", normalize_reprt_code("ANNUAL") == "11011")
    expect("Q1 → 11013", normalize_reprt_code("Q1") == "11013")
    expect("H1 → 11012", normalize_reprt_code("H1") == "11012")
    expect("Q3 → 11014", normalize_reprt_code("Q3") == "11014")
    expect("한글 사업 → 11011", normalize_reprt_code("사업") == "11011")
    expect("한글 반기 → 11012", normalize_reprt_code("반기") == "11012")
    expect("한글 1분기 → 11013", normalize_reprt_code("1분기") == "11013")
    expect("한글 3분기 → 11014", normalize_reprt_code("3분기") == "11014")
    expect("raw 11011 그대로", normalize_reprt_code("11011") == "11011")
    expect_raises("None reject", ValueError, normalize_reprt_code, None)
    expect_raises("unknown reject", ValueError, normalize_reprt_code, "Q5")
    expect_raises("raw invalid reject", ValueError, normalize_reprt_code, "99999")


def test_reprt_label() -> None:
    print("\n[reprt_code_label]")
    expect("11011 → 사업보고서", reprt_code_label("11011") == "사업보고서")
    expect("11012 → 반기보고서", reprt_code_label("11012") == "반기보고서")
    expect("11013 → 1분기보고서", reprt_code_label("11013") == "1분기보고서")
    expect("11014 → 3분기보고서", reprt_code_label("11014") == "3분기보고서")
    expect("unknown → passthrough", reprt_code_label("99999") == "99999")


def test_rcept_no() -> None:
    print("\n[normalize_rcept_no]")
    expect("ok 14자리", normalize_rcept_no("20240315001234") == "20240315001234")
    expect_raises("None reject", ValueError, normalize_rcept_no, None)
    expect_raises("13자리 reject", ValueError, normalize_rcept_no, "2024031500123")
    expect_raises("15자리 reject", ValueError, normalize_rcept_no, "202403150012345")
    expect_raises("문자 포함 reject", ValueError, normalize_rcept_no, "2024031500123A")


def test_fs_div() -> None:
    print("\n[normalize_fs_div]")
    expect("None → CFS 기본", normalize_fs_div(None) == "CFS")
    expect("CFS 그대로", normalize_fs_div("CFS") == "CFS")
    expect("OFS 그대로", normalize_fs_div("OFS") == "OFS")
    expect("연결 → CFS", normalize_fs_div("연결") == "CFS")
    expect("별도 → OFS", normalize_fs_div("별도") == "OFS")
    expect("consolidated → CFS", normalize_fs_div("consolidated") == "CFS")
    expect("separate → OFS", normalize_fs_div("separate") == "OFS")
    expect("case-insensitive cfs", normalize_fs_div("cfs") == "CFS")
    expect_raises("unknown reject", ValueError, normalize_fs_div, "WRONG")


def test_sj_div() -> None:
    print("\n[normalize_sj_div]")
    expect("None → None", normalize_sj_div(None) is None)
    expect("빈 문자열 → None", normalize_sj_div("") is None)
    expect("BS 그대로", normalize_sj_div("BS") == "BS")
    expect("재무상태표 → BS", normalize_sj_div("재무상태표") == "BS")
    expect("손익계산서 → IS", normalize_sj_div("손익계산서") == "IS")
    expect("balance_sheet → BS", normalize_sj_div("balance_sheet") == "BS")
    expect("cash_flow → CF", normalize_sj_div("cash_flow") == "CF")
    expect("자본변동표 → SCE", normalize_sj_div("자본변동표") == "SCE")
    expect_raises("unknown reject", ValueError, normalize_sj_div, "WRONG")


def test_days_to_range() -> None:
    print("\n[days_to_range]")
    today = date(2024, 3, 15)
    bgn, end = days_to_range(30, today=today)
    expect("end == today", end == "20240315")
    expect("bgn == 30일 전", bgn == "20240214")

    bgn, end = days_to_range(1, today=today)
    expect("days=1: bgn = 어제", bgn == "20240314")

    expect_raises("0 reject", ValueError, days_to_range, 0)
    expect_raises("음수 reject", ValueError, days_to_range, -1)
    expect_raises("3651 reject", ValueError, days_to_range, 3651)
    expect_raises("float reject", ValueError, days_to_range, 30.5)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    test_corp_code()
    test_stock_code()
    test_yyyymmdd()
    test_bsns_year()
    test_reprt_code()
    test_reprt_label()
    test_rcept_no()
    test_fs_div()
    test_sj_div()
    test_days_to_range()

    print("\n" + "=" * 60)
    print(f"PASS: {_PASS}   FAIL: {_FAIL}")
    if _FAILED_NAMES:
        print("Failed:")
        for n in _FAILED_NAMES:
            print(f"  - {n}")
    print("=" * 60)
    return 0 if _FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
