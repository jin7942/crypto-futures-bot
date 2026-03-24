| 버전 | 변경내용 | 작성자 | 수정일 |
| --- | --- | --- | --- |
| v1.0 | 초기 작성 | 김진범 | 2026-03-24 |

# 시스템 아키텍처 설계

## 1 전체 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                        Docker Host (VPS)                     │
│                                                              │
│  ┌──────────────────────┐    ┌───────────────────────────┐  │
│  │   Freqtrade Container │    │   OpenClaw Container       │  │
│  │                        │    │                             │  │
│  │  ┌──────────────────┐ │    │  ┌───────────────────────┐ │  │
│  │  │ LLMHybridStrategy │ │    │  │ Sentiment Generator   │ │  │
│  │  │  - RSI, BB, EMA   │ │    │  │  - Claude LLM 호출    │ │  │
│  │  │  - MACD, Volume   │ │    │  │  - 시장 데이터 분석   │ │  │
│  │  │  - Sentiment Read  │◀┼────┼──│  - sentiment.json 쓰기│ │  │
│  │  └──────────────────┘ │    │  └───────────────────────┘ │  │
│  │           │            │    │             │               │  │
│  │  ┌────────▼─────────┐ │    │  ┌──────────▼────────────┐ │  │
│  │  │ Order Execution   │ │    │  │ Monitoring & Briefing │ │  │
│  │  │  - Binance Futures│ │    │  │  - Freqtrade API 조회 │ │  │
│  │  │  - Risk Mgmt      │ │    │  │  - Telegram 전송      │ │  │
│  │  └──────────────────┘ │    │  └───────────────────────┘ │  │
│  │           │            │    │             ▲               │  │
│  │  ┌────────▼─────────┐ │    │             │               │  │
│  │  │ REST API :8080    │─┼────┼─────────────┘               │  │
│  │  └──────────────────┘ │    │                             │  │
│  └──────────────────────┘    └───────────────────────────┘  │
│              │                                               │
└──────────────┼───────────────────────────────────────────────┘
               │
               ▼
        [Binance Futures]
```

---

## 2 계층 분리

### 2.1 Execution Layer (Freqtrade)

매매 실행의 유일한 주체. 거래소 API 키를 보유한 유일한 컴포넌트.

| 책임 | 설명 |
|---|---|
| 지표 계산 | RSI, BB, EMA, MACD, Volume, ATR |
| 센티먼트 읽기 | sentiment.json 파일 읽기 (60초 캐시) |
| 매매 결정 | 기술적 지표 + 센티먼트 필터 조합 |
| 주문 실행 | Binance Futures API 통한 롱/숏 주문 |
| 리스크 관리 | stoploss, trailing stop, ROI, max trades |

### 2.2 Intelligence Layer (OpenClaw + Claude LLM)

시장 분석 및 센티먼트 생성. 매매 권한 없음.

| 책임 | 설명 |
|---|---|
| 시장 분석 | Claude LLM으로 시장 국면 판단 |
| 센티먼트 생성 | sentiment.json 파일 쓰기 (1~4시간 주기) |
| 비용 | $0 (Claude Max 구독 활용) |

### 2.3 Monitoring Layer (OpenClaw)

상태 모니터링 및 알림. 읽기 전용.

| 책임 | 설명 |
|---|---|
| 포트폴리오 조회 | Freqtrade REST API (GET only) |
| 브리핑 생성 | 일간 리포트, 아침 브리핑 |
| 이상 징후 감지 | 드로다운, 연속 손절 경고 |
| 알림 전송 | Telegram |

---

## 3 데이터 흐름

### 3.1 센티먼트 파이프라인

```
OpenClaw (1~4h 주기)
    │
    ├── 시장 데이터 수집 (가격, 거래량, 뉴스)
    ├── Claude LLM에 분석 요청
    ├── 응답 파싱 및 검증
    └── sentiment.json 파일 쓰기
            │
            ▼
Freqtrade (5분 캔들마다)
    │
    ├── sentiment.json 파일 읽기 (60초 캐시)
    ├── staleness 체크 (4시간 초과 → neutral)
    └── 진입 시그널에 거부권 적용
```

### 3.2 sentiment.json 스키마

```json
{
    "BTC/USDT:USDT": {
        "sentiment": "bullish|bearish|neutral",
        "confidence": 0.0-1.0,
        "reasoning": "분석 근거 (선택)",
        "updated_at": "2026-03-24T12:00:00Z"
    }
}
```

| 필드 | 타입 | 필수 | 설명 |
|---|---|---|---|
| sentiment | string | Y | "bullish", "bearish", "neutral" |
| confidence | float | N | 0.0~1.0 신뢰도 |
| reasoning | string | N | 분석 근거 (로깅/디버깅용) |
| updated_at | string (ISO 8601) | Y | 생성 시각 (staleness 판단용) |

### 3.3 장애 시나리오

| 장애 | 영향 | 대응 |
|---|---|---|
| OpenClaw 다운 | sentiment.json 미갱신 | 4시간 후 neutral fallback |
| sentiment.json 파싱 에러 | 센티먼트 읽기 실패 | neutral fallback |
| sentiment.json 파일 없음 | 첫 실행 또는 삭제됨 | neutral fallback |
| Freqtrade 다운 | 매매 중단 | stoploss_on_exchange가 거래소에서 손절 처리 |
| Binance API 장애 | 주문 불가 | 거래소 stoploss가 안전장치 |

---

## 4 Docker 구성

### 4.1 컨테이너 구조

| 컨테이너 | 이미지 | 포트 | 볼륨 |
|---|---|---|---|
| freqtrade | freqtradeorg/freqtrade:stable | 127.0.0.1:8080 | ./freqtrade/user_data |
| openclaw | openclaw/openclaw:latest | - | 공유 볼륨 (sentiment.json) |

### 4.2 볼륨 공유

OpenClaw와 Freqtrade는 `user_data/` 디렉토리를 공유 볼륨으로 마운트한다. OpenClaw는 `sentiment.json`을 쓰고, Freqtrade는 읽는다.

```yaml
volumes:
  shared_data:
    driver: local

services:
  freqtrade:
    volumes:
      - ./freqtrade/user_data:/freqtrade/user_data
      - shared_data:/freqtrade/user_data/shared

  openclaw:
    volumes:
      - shared_data:/app/shared
```

---

## 5 보안

| 항목 | 방침 |
|---|---|
| 거래소 API 키 | Freqtrade 컨테이너만 접근. .env 파일로 관리 |
| Freqtrade REST API | 127.0.0.1만 바인딩 (외부 접근 차단) |
| OpenClaw | 거래소 API 키 접근 불가. 읽기 전용 |
| Claude LLM | 거래소 API 키 접근 불가. OpenClaw 경유 |
| sentiment.json | 검증 후 사용 (유효값 체크 + staleness 체크) |

---

## 6 모니터링

### 6.1 Freqtrade 내장

- 거래 로그: `user_data/logs/freqtrade.log`
- Telegram 알림: 진입/청산/경고
- REST API: 실시간 상태 조회

### 6.2 OpenClaw 브리핑

| 브리핑 | 시간 | 내용 |
|---|---|---|
| 아침 브리핑 | 08:00 | 시장 요약, 전일 PnL, 오픈 포지션, 주요 이벤트 |
| 저녁 리포트 | 22:00 | 일간 성과, 승률, 페어별 분석, 센티먼트 요약 |
| 긴급 경고 | 즉시 | 드로다운 10%+, 연속 손절 3회+, 펀딩비 급등 |
