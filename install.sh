#!/bin/bash
# dartlens Installer (macOS / Linux)
# Usage:
#   curl -LsSf https://raw.githubusercontent.com/Johnhyeon/dartlens-mcp/main/install.sh | sh
#
# Or with API key prefilled (no prompt):
#   curl -LsSf https://raw.githubusercontent.com/Johnhyeon/dartlens-mcp/main/install.sh | DART_API_KEY=xxxx sh
#
# 3 steps:
#   1) uv (Python package manager) — auto-installs Python runtime if missing
#   2) dartlens-mcp via `uv tool install`
#   3) Claude Desktop config + DART API key validation via `dartlens-setup`

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macOS"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="Linux"
else
    OS="Unknown"
fi

echo ""
echo "=============================================="
echo "  dartlens Installer ($OS)"
echo "=============================================="
echo ""

LOCAL_BIN="$HOME/.local/bin"

# ── [1/3] uv ─────────────────────────────────────────────
echo -e "${CYAN}[1/3] Checking uv...${NC}"
if ! command -v uv > /dev/null 2>&1; then
    echo "      uv not found. Installing from astral.sh..."
    if ! curl -LsSf https://astral.sh/uv/install.sh | sh; then
        echo -e "      ${RED}[FAIL] uv installation failed.${NC}"
        echo "      Manual install: https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    fi
    if [ -d "$LOCAL_BIN" ]; then
        export PATH="$LOCAL_BIN:$PATH"
    fi
    if ! command -v uv > /dev/null 2>&1; then
        echo -e "      ${RED}[FAIL] uv installed but not on PATH. Open a new terminal and re-run.${NC}"
        exit 1
    fi
    echo -e "      ${GREEN}uv installed: $(command -v uv)${NC}"
else
    echo -e "      ${GREEN}uv found: $(command -v uv)${NC}"
fi
echo ""

# ── [2/3] dartlens-mcp ─────────────────────────────
echo -e "${CYAN}[2/3] Installing dartlens-mcp...${NC}"

if ! uv tool install --force dartlens-mcp; then
    echo -e "      ${RED}[FAIL] uv tool install failed.${NC}"
    exit 1
fi
echo -e "      ${GREEN}dartlens-mcp installed via uv tool${NC}"
echo ""

case ":$PATH:" in
    *":$LOCAL_BIN:"*) ;;
    *) [ -d "$LOCAL_BIN" ] && export PATH="$LOCAL_BIN:$PATH" ;;
esac

# ── [3/3] DART API key + Claude Desktop config ───────────
echo -e "${CYAN}[3/3] Configuring Claude Desktop (DART API key required)...${NC}"
echo "      DART API 키가 없다면 https://opendart.fss.or.kr 에서 무료 발급 (분당 1,000건 / 일 20,000건)"
echo ""

# curl | sh 로 실행되면 stdin이 파이프라 input() 이 막힌다.
# /dev/tty 가 있으면 거기에 연결해서 키 입력을 받게 한다.
# DART_API_KEY env var 가 이미 있으면 setup 이 prompt 없이 진행함.
if [ -x "$LOCAL_BIN/dartlens-setup" ]; then
    SETUP_CMD=("$LOCAL_BIN/dartlens-setup")
else
    SETUP_CMD=(uv tool run --from dartlens-mcp dartlens-setup)
fi

if [ -n "$DART_API_KEY" ] || [ ! -e /dev/tty ]; then
    "${SETUP_CMD[@]}"
else
    "${SETUP_CMD[@]}" < /dev/tty
fi

if [ $? -ne 0 ]; then
    echo ""
    echo -e "${RED}[FAIL] dartlens-setup failed. 키를 직접 다시 등록하려면:${NC}"
    echo -e "${RED}       dartlens-setup <YOUR_DART_API_KEY>${NC}"
    exit 1
fi
echo ""

echo "=============================================="
echo -e "${GREEN}  Installation complete${NC}"
echo "=============================================="
echo ""
echo "Next steps:"
echo "  1. Fully quit Claude Desktop"
if [[ "$OS" == "macOS" ]]; then
    echo "     (Cmd+Q or menu bar -> Claude -> Quit)"
fi
echo "  2. Restart Claude Desktop"
echo "  3. Try: '삼성전자 최근 공시 보여줘'"
echo ""
echo "Update later:    uv tool upgrade dartlens-mcp"
echo "Re-register key: dartlens-setup <KEY>"
echo ""
