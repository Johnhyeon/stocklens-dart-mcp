"""각 MCP tool을 실제 DART에 호출해 출력을 덤프 — 라벨/포맷/엣지 케이스 육안 검토용.

사용:
    python tests/smoke_outputs.py
    python tests/smoke_outputs.py --quick   # 핵심 happy path만
    python tests/smoke_outputs.py --section disclosures  # 한 섹션만

DART_API_KEY는 환경변수 또는 OS 키체인(dartmcp-setup으로 등록)에서 자동 로드됨.
출력은 토큰 폭발 방지로 각 호출마다 첫 N줄/N자만 보여줌.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# 패키지 import 가능하게 (editable install 안 된 환경에서도)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from dart_mcp_server.server import (
    get_disclosure_detail,
    get_full_financial,
    get_insider_trades,
    get_major_accounts,
    get_major_holders,
    list_disclosures,
    search_company,
)

# 테스트 표준 fixture — DART에 항상 존재하는 안정적 회사
SAMSUNG_CORP = "00126380"   # 삼성전자
SAMSUNG_STOCK = "005930"
LG_ENERGY_CORP = "01515323"  # LG에너지솔루션 (참고용)


def banner(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"=== {title}")
    print("=" * 70)


def show(text: str, *, head_lines: int = 25, head_chars: int = 1500) -> None:
    """긴 출력 잘라서 보여주기."""
    if not isinstance(text, str):
        print(repr(text))
        return
    if len(text) <= head_chars:
        print(text)
        return
    lines = text.splitlines()
    if len(lines) > head_lines:
        snippet = "\n".join(lines[:head_lines])
        print(snippet)
        print(f"... [+{len(lines) - head_lines} more lines, total {len(text)} chars]")
    else:
        print(text[:head_chars] + f"\n... [+{len(text) - head_chars} more chars]")


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

async def section_search() -> None:
    banner("search_company('삼성전자') — 정확 한글명 → 단건 + 기업개황")
    show(await search_company("삼성전자"))

    banner("search_company('005930') — 6자리 종목코드")
    show(await search_company("005930"))

    banner("search_company('00126380') — 8자리 corp_code")
    show(await search_company("00126380"))

    banner("search_company('삼성') — 부분 매칭(다중) → 후보 리스트")
    show(await search_company("삼성"))

    banner("search_company('xyz존재안함zzzqqq') — 매칭 없음")
    show(await search_company("xyz존재안함zzzqqq"))

    banner("search_company('카카오') — 일반 케이스")
    show(await search_company("카카오"))


async def section_disclosures() -> None:
    banner("list_disclosures(corp_code=삼성, days=14) — 기본")
    show(await list_disclosures(corp_code=SAMSUNG_CORP, days=14, limit=5))

    banner("list_disclosures(corp_code=삼성, days=180, kind='regular') — 정기보고서만")
    show(await list_disclosures(corp_code=SAMSUNG_CORP, days=180, kind="regular", limit=5))

    banner("list_disclosures(corp_code=삼성, days=180, kind='지분') — 한글 라벨")
    show(await list_disclosures(corp_code=SAMSUNG_CORP, days=180, kind="지분", limit=5))

    banner("list_disclosures(days=2, limit=5) — 전체회사 최근 2일")
    show(await list_disclosures(days=2, limit=5))

    banner("list_disclosures(corp_code='123') — 잘못된 corp_code 길이 → 친절 에러")
    show(await list_disclosures(corp_code="123"))

    banner("list_disclosures(corp_code=삼성, kind='wrong_kind') — 알 수 없는 kind → 친절 에러")
    show(await list_disclosures(corp_code=SAMSUNG_CORP, kind="wrong_kind"))

    banner("list_disclosures(corp_code=삼성, days=999999) — days 범위 초과 → 친절 에러")
    show(await list_disclosures(corp_code=SAMSUNG_CORP, days=999999))


async def section_major_accounts() -> None:
    banner("get_major_accounts(삼성, 2024, 'annual') — 사업보고서")
    show(await get_major_accounts(corp_code=SAMSUNG_CORP, bsns_year=2024, reprt_code="annual"))

    banner("get_major_accounts(삼성, 2024, 'H1') — 반기 친근 라벨")
    show(await get_major_accounts(corp_code=SAMSUNG_CORP, bsns_year=2024, reprt_code="H1"))

    banner("get_major_accounts(삼성, 2024, '반기') — 한글 라벨")
    show(await get_major_accounts(corp_code=SAMSUNG_CORP, bsns_year=2024, reprt_code="반기"))

    banner("get_major_accounts(삼성, 1900, 'annual') — bsns_year 비정상 → 친절 에러")
    show(await get_major_accounts(corp_code=SAMSUNG_CORP, bsns_year=1900, reprt_code="annual"))

    banner("get_major_accounts(삼성, 2024, 'wrong_code') — reprt_code 비정상 → 친절 에러")
    show(await get_major_accounts(corp_code=SAMSUNG_CORP, bsns_year=2024, reprt_code="wrong_code"))


async def section_full_financial() -> None:
    banner("get_full_financial(삼성, 2024, annual, CFS, sj_div=None) — 요약 모드")
    show(await get_full_financial(corp_code=SAMSUNG_CORP, bsns_year=2024, reprt_code="annual", fs_div="CFS"))

    banner("get_full_financial(삼성, 2024, annual, CFS, sj_div='IS') — 손익만")
    show(await get_full_financial(corp_code=SAMSUNG_CORP, bsns_year=2024, reprt_code="annual", fs_div="CFS", sj_div="IS"))

    banner("get_full_financial(삼성, 2024, annual, CFS, sj_div='재무상태표') — 한글 라벨")
    show(await get_full_financial(corp_code=SAMSUNG_CORP, bsns_year=2024, reprt_code="annual", fs_div="CFS", sj_div="재무상태표"))

    banner("get_full_financial(삼성, 2024, annual, CFS, sj_div='WRONG') — 잘못된 sj_div → 친절 에러")
    show(await get_full_financial(corp_code=SAMSUNG_CORP, bsns_year=2024, reprt_code="annual", fs_div="CFS", sj_div="WRONG"))

    banner("get_full_financial(삼성, 2024, annual, fs_div='연결') — 한글 fs_div alias")
    show(await get_full_financial(corp_code=SAMSUNG_CORP, bsns_year=2024, reprt_code="annual", fs_div="연결", sj_div="IS"), head_lines=8)


async def section_disclosure_detail() -> None:
    banner("get_disclosure_detail — list_disclosures에서 첫 rcept_no 동적 추출")
    listing = await list_disclosures(corp_code=SAMSUNG_CORP, days=30, limit=3)
    show(listing, head_lines=15)
    # listing에서 `rcept_no` 패턴 추출
    import re
    m = re.search(r"`(\d{14})`", listing)
    if not m:
        print("[SKIP] rcept_no 추출 실패")
        return
    no = m.group(1)
    banner(f"get_disclosure_detail(rcept_no={no})")
    show(await get_disclosure_detail(rcept_no=no), head_lines=20)

    banner("get_disclosure_detail('123') — 잘못된 길이 rcept_no → 친절 에러")
    show(await get_disclosure_detail(rcept_no="123"))


async def section_holders() -> None:
    banner("get_major_holders(삼성, limit=5) — 5%룰 대량보유")
    show(await get_major_holders(corp_code=SAMSUNG_CORP, limit=5), head_lines=15)

    banner("get_major_holders(corp_code='123') — 잘못된 corp_code → 친절 에러")
    show(await get_major_holders(corp_code="123"))

    banner("get_major_holders(삼성, limit=999) — limit 초과 → 친절 에러")
    show(await get_major_holders(corp_code=SAMSUNG_CORP, limit=999))


async def section_insiders() -> None:
    banner("get_insider_trades(삼성, limit=5) — 임원·주요주주")
    show(await get_insider_trades(corp_code=SAMSUNG_CORP, limit=5), head_lines=15)

    banner("get_insider_trades(corp_code='abc') — 비숫자 → 친절 에러")
    show(await get_insider_trades(corp_code="abcdefgh"))


async def section_cache_check() -> None:
    """동일 호출 두 번 → 두 번째가 빠르게 반환되는지 (캐시 동작 확인)."""
    import time

    banner("캐시 동작 — search_company('삼성전자') 두 번 (corp_code 인덱스 + company.json 캐시)")
    t0 = time.monotonic()
    await search_company("삼성전자")
    d1 = (time.monotonic() - t0) * 1000

    t0 = time.monotonic()
    await search_company("삼성전자")
    d2 = (time.monotonic() - t0) * 1000

    print(f"1회차: {d1:.1f} ms")
    print(f"2회차: {d2:.1f} ms (캐시 히트면 < 50ms 기대)")
    print("PASS" if d2 < 100 else "WARN: 캐시 히트가 약함")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

SECTIONS = {
    "search": section_search,
    "disclosures": section_disclosures,
    "major": section_major_accounts,
    "full": section_full_financial,
    "detail": section_disclosure_detail,
    "holders": section_holders,
    "insiders": section_insiders,
    "cache": section_cache_check,
}

QUICK = ["search", "disclosures", "major", "holders", "insiders"]


async def run(section_names: list[str]) -> None:
    for name in section_names:
        fn = SECTIONS.get(name)
        if not fn:
            print(f"[SKIP] unknown section: {name}")
            continue
        try:
            await fn()
        except Exception as e:
            print(f"[EXCEPTION in {name}] {type(e).__name__}: {e}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--quick", action="store_true", help="핵심 happy path 섹션만")
    p.add_argument(
        "--section",
        action="append",
        choices=list(SECTIONS.keys()),
        help="특정 섹션만 (반복 가능)",
    )
    args = p.parse_args()

    if args.section:
        sections = args.section
    elif args.quick:
        sections = QUICK
    else:
        sections = list(SECTIONS.keys())

    asyncio.run(run(sections))
    print("\n" + "=" * 70)
    print(f"=== Done. Sections: {', '.join(sections)}")
    print("=" * 70)


if __name__ == "__main__":
    main()
