"""토큰 핫스팟 측정 — 각 도구의 대표 시나리오를 라이브 호출해 응답 크기 측정.

목적: dart-mcp 호출이 Claude 컨텍스트에서 차지하는 토큰을 도구·시나리오별로
정량화. 핫스팟을 식별해 표적 최적화 (단위 변환, 행 필터, 표 압축 등) 우선순위 결정.

측정 방식:
- 각 도구 N개 시나리오 호출
- 응답 char 수 + tiktoken으로 토큰 수 측정 (cl100k_base; Claude 토크나이저와 근사)
- 도구별 통계 + 가장 큰 응답 top 10
- 권장 사항 자동 출력

사용:
    python tests/measure_tokens.py
    python tests/measure_tokens.py --section heavy   # 큰 응답만
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from pathlib import Path

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

# tiktoken 사용 (Claude 토크나이저와 정확히 일치하진 않지만 비례 관계는 매우 가까움)
try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")

    def count_tokens(text: str) -> int:
        return len(_enc.encode(text))
    _TOKENIZER = "tiktoken/cl100k_base"
except ImportError:
    def count_tokens(text: str) -> int:
        # 한국어 1자 ≈ 0.6 토큰, 영문은 0.25. 평균적으로 0.5.
        return int(len(text) * 0.55)
    _TOKENIZER = "approx (chars × 0.55)"


SAMSUNG_CORP = "00126380"
LG_ENERGY_CORP = "01515323"
HYUNDAI_MOTOR_CORP = "00164742"


# ---------------------------------------------------------------------------
# 시나리오 정의 (도구, 라벨, async 호출자)
# ---------------------------------------------------------------------------

SCENARIOS = [
    # search_company — 작을 것으로 예상
    ("search_company", "exact name", lambda: search_company("삼성전자")),
    ("search_company", "stock_code 6", lambda: search_company("005930")),
    ("search_company", "corp_code 8", lambda: search_company("00126380")),
    ("search_company", "partial 다중", lambda: search_company("삼성")),

    # list_disclosures — 표 형식, limit이 변수
    ("list_disclosures", "30d limit=10", lambda: list_disclosures(corp_code=SAMSUNG_CORP, days=30, limit=10)),
    ("list_disclosures", "30d limit=20", lambda: list_disclosures(corp_code=SAMSUNG_CORP, days=30, limit=20)),
    ("list_disclosures", "180d limit=50", lambda: list_disclosures(corp_code=SAMSUNG_CORP, days=180, limit=50)),
    ("list_disclosures", "전체사 2d limit=20", lambda: list_disclosures(days=2, limit=20)),

    # get_major_accounts — 4 섹션 (CFS/OFS × BS/IS) × 행 ≈ 큼
    ("get_major_accounts", "삼성 2024 annual", lambda: get_major_accounts(corp_code=SAMSUNG_CORP, bsns_year=2024, reprt_code="annual")),
    ("get_major_accounts", "삼성 2024 H1", lambda: get_major_accounts(corp_code=SAMSUNG_CORP, bsns_year=2024, reprt_code="H1")),
    ("get_major_accounts", "LG에너지 2024 annual", lambda: get_major_accounts(corp_code=LG_ENERGY_CORP, bsns_year=2024, reprt_code="annual")),

    # get_full_financial — sj_div별 행 수 차이 큼
    ("get_full_financial", "summary mode (sj_div=None)", lambda: get_full_financial(corp_code=SAMSUNG_CORP, bsns_year=2024, reprt_code="annual", fs_div="CFS")),
    ("get_full_financial", "IS 17행", lambda: get_full_financial(corp_code=SAMSUNG_CORP, bsns_year=2024, reprt_code="annual", fs_div="CFS", sj_div="IS")),
    ("get_full_financial", "BS 52행", lambda: get_full_financial(corp_code=SAMSUNG_CORP, bsns_year=2024, reprt_code="annual", fs_div="CFS", sj_div="BS")),
    ("get_full_financial", "CF 40행", lambda: get_full_financial(corp_code=SAMSUNG_CORP, bsns_year=2024, reprt_code="annual", fs_div="CFS", sj_div="CF")),
    ("get_full_financial", "SCE 91행", lambda: get_full_financial(corp_code=SAMSUNG_CORP, bsns_year=2024, reprt_code="annual", fs_div="CFS", sj_div="SCE")),

    # get_disclosure_detail — 본문 발췌 (짧은 공시/긴 보고서/find 모드)
    ("get_disclosure_detail", "대량보유 보고서 (짧음)", lambda: get_disclosure_detail(rcept_no="20260417000682")),
    ("get_disclosure_detail", "임원 소유 보고서 (짧음)", lambda: get_disclosure_detail(rcept_no="20260417000440")),
    ("get_disclosure_detail", "find='보유주식수'", lambda: get_disclosure_detail(rcept_no="20260417000682", find="보유주식수")),

    # get_major_holders / insider — 표
    ("get_major_holders", "삼성 limit=10", lambda: get_major_holders(corp_code=SAMSUNG_CORP, limit=10)),
    ("get_major_holders", "삼성 limit=50", lambda: get_major_holders(corp_code=SAMSUNG_CORP, limit=50)),

    ("get_insider_trades", "삼성 limit=10", lambda: get_insider_trades(corp_code=SAMSUNG_CORP, limit=10)),
    ("get_insider_trades", "삼성 limit=50", lambda: get_insider_trades(corp_code=SAMSUNG_CORP, limit=50)),
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run_scenarios(filter_min_tokens: int = 0) -> list[dict]:
    results = []
    for tool, label, fn in SCENARIOS:
        t0 = time.monotonic()
        try:
            out = await fn()
            err = None
        except Exception as e:
            out = f"[EXCEPTION] {type(e).__name__}: {e}"
            err = type(e).__name__
        dt_ms = (time.monotonic() - t0) * 1000
        text = str(out) if out is not None else ""
        chars = len(text)
        tokens = count_tokens(text)
        results.append({
            "tool": tool,
            "label": label,
            "chars": chars,
            "tokens": tokens,
            "duration_ms": round(dt_ms, 1),
            "error": err,
        })
    return [r for r in results if r["tokens"] >= filter_min_tokens]


def fmt_int(n: int | float) -> str:
    return f"{int(n):,}"


def section_summary_by_tool(results: list[dict]) -> None:
    print("\n" + "=" * 80)
    print("도구별 요약 (calls / 평균 / 중간값 / 최대 토큰)")
    print("=" * 80)
    tools: dict[str, list[dict]] = {}
    for r in results:
        tools.setdefault(r["tool"], []).append(r)

    print(f"{'도구':<25}{'호출':>6}{'평균':>10}{'중간':>10}{'최대':>10}{'합계':>12}")
    print("-" * 80)
    grand_total = 0
    for tool, rows in sorted(tools.items(), key=lambda kv: -sum(r["tokens"] for r in kv[1])):
        toks = [r["tokens"] for r in rows]
        avg = statistics.mean(toks)
        med = statistics.median(toks)
        mx = max(toks)
        total = sum(toks)
        grand_total += total
        print(f"{tool:<25}{len(rows):>6}{fmt_int(avg):>10}{fmt_int(med):>10}{fmt_int(mx):>10}{fmt_int(total):>12}")
    print("-" * 80)
    print(f"{'전체':<25}{len(results):>6}{'':>10}{'':>10}{'':>10}{fmt_int(grand_total):>12}")


def section_top_responses(results: list[dict], top_n: int = 10) -> None:
    print("\n" + "=" * 80)
    print(f"가장 토큰 많이 쓴 응답 top {top_n}")
    print("=" * 80)
    print(f"{'순위':<4}{'토큰':>8}{'문자':>10}{'ms':>8}  {'도구':<25}{'시나리오'}")
    print("-" * 80)
    sorted_r = sorted(results, key=lambda r: -r["tokens"])[:top_n]
    for i, r in enumerate(sorted_r, 1):
        print(f"{i:<4}{fmt_int(r['tokens']):>8}{fmt_int(r['chars']):>10}{r['duration_ms']:>8.1f}  {r['tool']:<25}{r['label']}")


def section_recommendations(results: list[dict]) -> None:
    print("\n" + "=" * 80)
    print("권장 사항 (heuristic)")
    print("=" * 80)
    HOT_THRESHOLD = 2000  # 단일 호출 2,000 토큰 이상이면 핫스팟
    BIG_NUMBER_TOOLS = {"get_major_accounts", "get_full_financial"}

    hot = [r for r in results if r["tokens"] >= HOT_THRESHOLD]
    if not hot:
        print(f"단일 호출 {HOT_THRESHOLD} 토큰 이상 없음 — 핫스팟 없습니다.")
        return

    # 도구별 핫 케이스 합산
    by_tool_hot: dict[str, list[dict]] = {}
    for r in hot:
        by_tool_hot.setdefault(r["tool"], []).append(r)

    for tool, rows in sorted(by_tool_hot.items(), key=lambda kv: -sum(r["tokens"] for r in kv[1])):
        max_r = max(rows, key=lambda r: r["tokens"])
        print(f"\n[{tool}]")
        print(f"  핫 케이스: {len(rows)}건, 최대 {fmt_int(max_r['tokens'])} 토큰 ({max_r['label']})")
        if tool in BIG_NUMBER_TOOLS:
            print("  → '300,870,903,000,000' 같은 콤마 큰 숫자가 토큰 폭발 주범. ")
            print("    '300조 8,709억' 단위 변환으로 50%+ 절감 기대.")
        if tool == "get_full_financial":
            print("  → sj_div='SCE'(자본변동표)는 91행으로 가장 큼. limit/페이지네이션 도입 또는 핵심 행만.")
            print("  → 빈/0 행이 있다면 필터로 추가 절감.")
        if tool == "get_disclosure_detail":
            print("  → 본문 4000자 cap을 2000~2500자로 줄이면 비례 절감.")
            print("    중요한 본문은 viewer URL로 안내 (이미 함).")
        if tool == "list_disclosures":
            print("  → 행당 메타가 작아 limit으로 통제 가능. limit 기본 20 → 10 검토.")
        if tool == "get_major_accounts":
            print("  → CFS+OFS 두 섹션 동시 출력 = 2배. fs_div 필수화로 한쪽만 기본 반환 검토.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-tokens", type=int, default=0, help="N 토큰 미만 시나리오 제외")
    args = parser.parse_args()

    print(f"Tokenizer: {_TOKENIZER}")
    print(f"시나리오 수: {len(SCENARIOS)}")
    print("측정 시작...")

    t_start = time.monotonic()
    results = asyncio.run(run_scenarios(filter_min_tokens=args.min_tokens))
    t_elapsed = time.monotonic() - t_start

    print(f"\n측정 완료: {len(results)}개 호출, 총 {t_elapsed:.1f}초")

    section_summary_by_tool(results)
    section_top_responses(results)
    section_recommendations(results)

    grand_total = sum(r["tokens"] for r in results)
    print()
    print("=" * 80)
    print(f"⚠️ 전체 시나리오 합계 {fmt_int(grand_total)} 토큰")
    print(f"   (Claude Pro 5시간 한도 ≈ 200,000 토큰 가정 시 {grand_total / 200000 * 100:.1f}%)")
    print("=" * 80)


if __name__ == "__main__":
    main()
