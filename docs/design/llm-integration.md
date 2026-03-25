| 버전 | 변경내용 | 작성자 | 수정일 |
| --- | --- | --- | --- |
| v1.0 | 초기 작성 | 김진범 | 2026-03-25 |

# LLM 연동 설계

## 1 설계 원칙

| 원칙 | 근거 |
|---|---|
| LLM은 매매 실행 권한 없음 | Alpha Arena 대회: Claude -30.8%, GPT-5 -62.7%. 직접 매매는 실패 |
| 거부권 + 보조 판단만 부여 | categorical 출력(bullish/bearish/neutral)으로 할루시네이션 영향 최소화 |
| 파일 기반 비동기 연동 | sentiment.json. 레이턴시 무관, 장애 격리 |
| neutral fallback | sentiment.json 없거나 stale → NFI 원본 그대로 동작 |
| 비용 $0 | Claude Max 구독 활용, API 호출 없음 |

---

## 2 현재 구조 (Phase 2)

```
[OpenClaw] ── 1~4시간마다 ──> sentiment.json
                                    │
[LLMSentimentNFI]                   │
    └── confirm_trade_entry()       │
            ├── super() (NFI X7 원본 로직)
            └── sentiment.json 읽기
                    ├── bearish → 롱 진입 거부
                    ├── bullish → 숏 진입 거부
                    └── neutral / 없음 → 통과
```

### 2.1 sentiment.json 스키마

```json
{
    "BTC/USDT:USDT": {
        "sentiment": "bullish",
        "confidence": 0.7,
        "reasoning": "분석 근거",
        "updated_at": "2026-03-25T12:00:00Z"
    }
}
```

| 필드 | 타입 | 필수 | 용도 |
|---|---|---|---|
| sentiment | string | Y | "bullish" / "bearish" / "neutral" |
| confidence | float | N | 0.0~1.0 (Phase 3에서 포지션 사이징에 활용) |
| reasoning | string | N | 디버깅/로깅용 |
| updated_at | ISO 8601 | Y | 4시간 초과 시 neutral fallback |

---

## 3 확장 계획

### Phase 3: 센티먼트 생성 + Confidence 포지션 사이징

OpenClaw가 실제로 sentiment.json을 생성하는 단계.

#### 3.1 데이터 소스

| 소스 | 수집 방법 | 효과 |
|---|---|---|
| Fear & Greed Index | alternative.me API (무료) | 시장 전체 온도 |
| 크립토 뉴스 헤드라인 | RSS / 크롤링 | 이벤트 감지 |
| 펀딩비 | Binance API (Freqtrade 경유) | 롱/숏 편향 판단 |
| 24h/7d 가격 변화 | Binance API | 모멘텀 |

#### 3.2 LLM 프롬프트 설계

```
You are a cryptocurrency market analyst.
Analyze the following data and determine the market sentiment for {pair}.

Data:
- 24h price change: {price_change}%
- 7d price change: {price_change_7d}%
- Fear & Greed Index: {fng_value} ({fng_label})
- Funding rate: {funding_rate}%
- Recent news: {headlines}

Respond in JSON:
{
    "sentiment": "bullish" | "bearish" | "neutral",
    "confidence": 0.0-1.0,
    "reasoning": "1-2 sentences"
}

Rules:
- Insufficient or contradictory data → "neutral", confidence < 0.5
- confidence > 0.8 requires strong agreement across multiple indicators
- Never predict specific prices
```

#### 3.3 Confidence 기반 포지션 사이징

`custom_stake_amount()` 오버라이드로 구현.

| confidence | stake 비율 | 근거 |
|---|---|---|
| 0.8+ | 100% | LLM 확신 높음 |
| 0.6~0.8 | 70% | 보통 확신 |
| 0.4~0.6 | 50% | 불확실 |
| 0.4 미만 | 30% | 거의 확신 없음 |

#### 3.4 확장된 sentiment.json 스키마

```json
{
    "BTC/USDT:USDT": {
        "sentiment": "bullish",
        "confidence": 0.75,
        "regime": "trending_up",
        "risk_level": "medium",
        "key_events": ["ETF 순유입 증가", "펀딩비 정상 범위"],
        "reasoning": "...",
        "data_sources": ["fear_greed", "news", "funding_rate"],
        "updated_at": "2026-03-25T08:00:00Z"
    }
}
```

추가 필드:

| 필드 | 타입 | 용도 |
|---|---|---|
| regime | string | 시장 국면 (trending_up/down, ranging, high_volatility) |
| risk_level | string | 리스크 수준 (low/medium/high/critical) |
| key_events | string[] | 주요 이벤트 목록 |
| data_sources | string[] | 분석에 사용된 데이터 소스 |

---

### Phase 4: 긴급 이벤트 감지

#### 4.1 긴급 이벤트 분류

| 카테고리 | 예시 | 대응 |
|---|---|---|
| critical | 거래소 해킹, 스테이블코인 디페그 | 전체 거래 중단 |
| high | 대규모 청산 캐스케이드, 규제 발표 | 신규 진입 차단 |
| medium | 고래 대량 이동, 펀딩비 급등 | 포지션 축소 |

#### 4.2 구현 방식

별도 파일 `emergency.json`:

```json
{
    "emergency": true,
    "severity": "critical",
    "event_type": "exchange_hack",
    "action": "halt_trading",
    "reason": "Binance hot wallet compromise reported",
    "updated_at": "2026-03-25T14:30:00Z"
}
```

`confirm_trade_entry()`에서 emergency.json 먼저 확인 → critical이면 모든 진입 거부.

---

### Phase 5: 과거 매매 반성 (Reflection)

CryptoTrade 논문(EMNLP 2024) 참고.

#### 5.1 구조

```
[Freqtrade] ── 거래 종료 ──> trade_history.json
                                    │
[OpenClaw] ── 매일 ──> 과거 거래 분석
    ├── 손실 거래 원인 분석
    ├── 유사 시장 상황 패턴 추출
    └── 다음 센티먼트 생성 시 반영
```

#### 5.2 효과

- 동일 패턴에서 반복 손실 방지
- 시간이 갈수록 센티먼트 정확도 향상
- LLM에 과거 컨텍스트 제공 → 판단 품질 개선

---

## 4 하지 않는 것

| 항목 | 이유 |
|---|---|
| LLM 직접 매매 실행 | 대회 결과 6개 중 4개 손실, Claude -30.8% |
| 실시간 API 호출 | 레이턴시 0.5~3초, 비용 증가, 장애 전파 |
| 가격 예측 | LLM은 시계열 예측에 부적합 |
| 고빈도 센티먼트 갱신 | 1~4시간 주기면 충분. 과도한 갱신은 노이즈 |

---

## 5 참고 자료

| 자료 | 내용 |
|---|---|
| Alpha Arena (2025.10) | LLM 직접 매매 대회. 범용 LLM 대부분 손실 |
| CryptoTrade (EMNLP 2024) | Reflective LLM Agent. 과거 매매 반성 메커니즘 |
| claude-trader | Multi-Agent 심사단 방식 (3인 리뷰 + 판사) |
| LLM_trader | Vision AI 차트 분석 + 벡터 DB 매매 기억 |
| openclaw-trader | Fear&Greed + 뉴스 + 긴급 키워드 스캔 |
