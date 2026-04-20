# DART MCP Server

금융감독원 **전자공시(DART) OpenAPI**를 Claude에서 자연어로 조회할 수 있게 해주는 MCP 서버입니다.

> "삼성전자 최근 분기보고서 요약해줘" · "카카오 최근 1개월 공시 목록" · "LG에너지솔루션 영업이익 추이" · "삼성전자 5% 이상 보유한 주주 변동" · "현대차 임원들 자사주 매매 보여줘"

자매 프로젝트 [stocklens-mcp](https://github.com/Johnhyeon/stocklens-mcp)(네이버 증권 기반 시세·차트·수급)와 **독립**입니다. Claude가 두 MCP를 조합해 종목 분석을 수행합니다.

---

## 빠른 시작

```bash
pip install stocklens-dart-mcp
dartmcp-setup
```

`dartmcp-setup`은:

1. DART API 키를 입력받아 **유효성 검증**한 뒤
2. Claude Desktop의 `claude_desktop_config.json`에 자동 등록

API 키가 없다면 먼저 [DART OpenAPI 발급](https://opendart.fss.or.kr/uss/umt/EgovMberInsertView.do) (무료, 분당 1,000건 / 일 20,000건).

설치 후 Claude Desktop을 완전히 종료했다가 다시 실행하세요.

---

## 키 보관 정책

`dartmcp-setup`은 **DART API 키를 `claude_desktop_config.json`에 평문으로 박지 않습니다.**

- 기본: 키를 OS 키체인에 저장
  - Windows → Credential Manager (DPAPI · 사용자 계정 단위 자동 암호화)
  - macOS → Keychain
  - Linux → Secret Service (GNOME Keyring / KDE Wallet)
- config 파일에는 `mcpServers.dart-mcp.command` 만 들어가고 키는 들어가지 않음
- 서버는 부팅 시 `DART_API_KEY` 환경변수를 먼저 보고, 없으면 키체인에서 자동 조회

JSON config에 평문 `DART_API_KEY`가 박혀있는 환경에서 `dartmcp-setup`을 다시 실행하면 자동으로 키체인으로 이전되고 JSON에서 제거됩니다.

### 평문 모드 (헤드리스 환경 fallback)

OS 키체인을 쓸 수 없는 환경(서버, 일부 WSL/Docker)에서는 `--plaintext`로 명시적 옵트아웃:

```bash
dartmcp-setup --plaintext <KEY>
```

이 경우 기존처럼 `env.DART_API_KEY`가 JSON에 평문 저장됩니다.

---

## 도구

| 도구 | 목적 |
|---|---|
| `search_company` | 종목명/종목코드 → corp_code + 기업개황 |
| `list_disclosures` | 기간·유형별 공시 목록 (rcept_no 반환) |
| `get_disclosure_detail` | rcept_no → 본문 발췌 + DART viewer URL + 첨부 목록 |
| `get_major_accounts` | 정기보고서 핵심 재무 (매출/영업이익/순이익/자산/부채/자본 — 당기·전기·전전기 비교) |
| `get_full_financial` | 전체 재무제표. sj_div(BS/IS/CIS/CF/SCE) 필수 |
| `get_major_holders` | 5%룰 대량보유 변동 — 외인/펀드/행동주의 진입 추적 |
| `get_insider_trades` | 임원·주요주주 특정증권 소유 — 내부자 매매 시그널 |

### 권장 워크플로우

```
# 공시 흐름
search_company("삼성전자") → corp_code "00126380"
list_disclosures(corp_code="00126380", days=30) → rcept_no 목록
get_disclosure_detail(rcept_no="20240315001234") → 본문 발췌

# 재무 흐름
search_company("삼성전자") → corp_code
get_major_accounts(corp_code, bsns_year=2024, reprt_code="annual") → 핵심 수치
get_full_financial(corp_code, bsns_year=2024, reprt_code="annual",
                   fs_div="CFS", sj_div="IS") → 손익 전체

# 지분 흐름 (시세에 안 나오는 자본 움직임)
search_company("삼성전자") → corp_code
get_major_holders(corp_code, limit=10) → 5%룰 보고서 (외인/펀드/행동주의)
get_insider_trades(corp_code, limit=10) → 임원·주요주주 자사주 매매
```

---

## 원칙

- **DART OpenAPI만** 사용합니다. 네이버·다음 등 스크래핑 일절 없음.
- 시세·차트·수급은 stocklens가, **공시·재무제표 정형 데이터**는 dart-mcp가 담당.
- 두 서버는 서로 호출하지 않습니다. **Claude가 조정자**입니다.
- 투자 추천·매매 시그널을 만들지 않습니다. 데이터 제공만.

---

## 라이선스

MIT
