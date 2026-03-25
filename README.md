# Crypto Futures Bot

Freqtrade + OpenClaw + Claude LLM 하이브리드 암호화폐 선물 자동매매 시스템.

## Architecture

```
[OpenClaw] ── 1~4시간마다 ──> sentiment.json 파일 저장
                                        │
[Freqtrade] ── 매 캔들(5분)마다 ──> sentiment.json 읽기
     │                                  (거부권 필터)
     ├── 기술적 지표 (RSI, BB, EMA, MACD)
     └── Binance Futures 매매 실행
     │
[Freqtrade REST API] ── 읽기 전용 ──> [OpenClaw] ──> [Telegram 브리핑]
```

- **Freqtrade**: 매매 실행 엔진 (선물 롱/숏 + 레버리지 + 리스크 관리)
- **OpenClaw**: 센티먼트 생성 + 모니터링 (Phase 3~4)
- **Claude LLM**: 시장 국면 필터 (거부권만 보유, 실행 권한 없음)

## Quick Start

### 1. Clone & Configure

```bash
git clone https://github.com/jin7942/crypto-futures-bot.git
cd crypto-futures-bot

# 환경변수 설정
cp .env.example .env
# .env에 Binance API 키, Telegram 설정 입력

# API 키 설정 (config.json을 오버라이드)
cp freqtrade/user_data/config.local.json.example freqtrade/user_data/config.local.json
# config.local.json에 Binance API 키, API 서버 인증 정보 입력
```

### 2. Run (Dry-Run Mode)

```bash
docker compose up -d
docker exec nginx-proxy nginx -s reload  # freqtrade.internal 라우팅 활성화
```

### 3. Check Status

```bash
docker compose logs -f freqtrade
# 또는 브라우저에서 http://freqtrade.internal
```

## Configuration

| File | Description |
|---|---|
| `freqtrade/user_data/config.json` | Freqtrade 공개 설정 (거래소, 리스크, 페어) |
| `freqtrade/user_data/config.local.json` | API 키, 인증 정보 (gitignore) |
| `freqtrade/user_data/strategies/LLMHybridStrategy.py` | 매매 전략 |
| `.env` | 환경변수 (gitignore) |

## Network

로컬 서버 (192.168.0.66) 내부망 인프라 위에서 동작한다.

- **jin-net**: Docker 외부 브릿지 네트워크 (nginx, monitoring과 공유)
- **nginx**: `freqtrade.internal` → `freqtrade:8080` 리버스 프록시
- **dnsmasq**: `*.internal` → 192.168.0.66 DNS 해석

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
