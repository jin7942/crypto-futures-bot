# Crypto Futures Bot

## Project Overview
Freqtrade + Claude LLM 하이브리드 암호화폐 선물 자동매매 시스템.

## Architecture
- **Execution**: Freqtrade Docker 컨테이너 (Binance Futures)
- **Intelligence**: Claude LLM API (전략 내부 시장 국면 필터)
- **Assistant**: OpenClaw (Phase 4, 읽기 전용 모니터링)

## Key Principles
- LLM은 분석/판단만 담당. 거래소 API 키를 LLM에게 절대 부여하지 않음
- LLM은 거부권만 보유 (시그널 생성 권한 없음)
- OpenClaw 장애 시에도 Freqtrade 매매는 정상 작동
- LLM API 호출: 1~4시간 캐시, 월 $5 이하 목표

## Project Structure
```
crypto-futures-bot/
├── docker-compose.yml              # Freqtrade + OpenClaw 컨테이너
├── .env.example                    # 환경변수 템플릿
├── freqtrade/
│   └── user_data/
│       ├── config.json             # Binance Futures 설정 (dry-run)
│       └── strategies/
│           └── LLMHybridStrategy.py  # 메인 전략
└── openclaw/                       # Phase 4
```

## Rules
- config.json의 API 키는 비워두고 .env로 관리
- 전략 수정 시 반드시 백테스트 수행 후 커밋
- Freqtrade 코어는 수정하지 않음 (Docker 이미지 사용)
- dry_run: true 상태에서 충분히 테스트 후 실전 전환

## Tech Stack
- Freqtrade (Docker: freqtradeorg/freqtrade:stable)
- Python 3.11+
- Anthropic Claude API (Sonnet)
- Binance Futures API
- Docker Compose
