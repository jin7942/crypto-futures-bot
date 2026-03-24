# Crypto Futures Bot

Freqtrade + Claude LLM 하이브리드 암호화폐 선물 자동매매 시스템.

## Architecture

```
[Freqtrade] ──── Claude API ────▶ LLM Sentiment Filter
     │
     ▼
[Binance Futures]
     │
     ▼
[Telegram Alert]

[Freqtrade] ──── REST API (read-only) ────▶ [OpenClaw] ──▶ [Telegram Briefing]
```

- **Freqtrade**: 매매 실행 엔진 (선물 롱/숏 + 레버리지 + 리스크 관리)
- **Claude LLM**: 전략 내부 시장 국면 필터 (거부권만 보유, 실행 권한 없음)
- **OpenClaw**: 리서치 어시스턴트 (브리핑, 모니터링, Phase 4)

## Quick Start

### 1. Clone & Configure

```bash
git clone https://github.com/jin7942/crypto-futures-bot.git
cd crypto-futures-bot
cp .env.example .env
# Edit .env with your API keys
```

### 2. Run (Dry-Run Mode)

```bash
docker-compose up -d
```

### 3. Check Status

```bash
docker-compose logs -f freqtrade
```

## Configuration

| File | Description |
|---|---|
| `.env` | API keys (Binance, Anthropic, Telegram) |
| `freqtrade/user_data/config.json` | Freqtrade settings (exchange, risk, pairs) |
| `freqtrade/user_data/strategies/LLMHybridStrategy.py` | Trading strategy |

## Risk Settings

| Parameter | Value |
|---|---|
| Leverage | 3x (isolated) |
| Stoploss | -5% (본금 기준, 레버 반영 시 -15%) |
| Trailing Stop | +2% (offset +3%) |
| Max Open Trades | 5 |
| Initial Wallet | $1,000 (dry-run) |

## License

GPL-3.0
