| 버전 | 변경내용 | 작성자 | 수정일 |
| --- | --- | --- | --- |
| v1.2 | 재검토: NFI 중심 재정립, 과대 설계 제거, LLM 역할 범위 명확화 | 김진범 | 2026-03-25 |
| v1.1 | 검토 반영: Phase 번호 정리, emergency 만료 정책, confidence 사이징 NFI 충돌 방지 | 김진범 | 2026-03-25 |
| v1.0 | 초기 작성 | 김진범 | 2026-03-25 |

# LLM 연동 설계

## 1 전제

**매매 판단의 주체는 NostalgiaForInfinityX7(NFI)이다.** LLM은 보조 필터일 뿐이다.

NFI는 76,627줄, 7개 트레이딩 모드(normal, pump, quick, rebuy, rapid, grind, derisk), 수백 개의 시그널 조건, 자체 포지션 관리(grinding, rebuy, derisking)를 가진 검증된 전략이다. LLM이 이 로직을 대체하거나 간섭해서는 안 된다.

| 영역 | 담당 | LLM 개입 |
|---|---|---|
| 시그널 생성 | NFI | 없음 |
| 포지션 사이징 | NFI (grinding, rebuy) | 없음 |
| 청산 판단 | NFI (custom_exit, derisking) | 없음 |
| 레버리지 | NFI (모드별 동적 조절) | 없음 |
| **진입 필터** | LLM | **거부권만** |
| **긴급 이벤트 감지** | LLM | **전체 진입 차단** |

---

## 2 설계 원칙

| 원칙 | 근거 |
|---|---|
| NFI 로직 간섭 금지 | NFI의 포지션 관리, 모드 전환, 청산 로직은 건드리지 않는다 |
| LLM은 거부만 가능 | 진입 시그널 생성 권한 없음. "이 진입을 막을지"만 판단 |
| 파일 기반 비동기 연동 | sentiment.json. 레이턴시 무관, 장애 격리 |
| neutral fallback | sentiment.json 없거나 stale → NFI 원본 그대로 동작 |
| 비용 $0 | Claude Max 구독 + OpenClaw 경유. API 호출 없음 |

Alpha Arena 대회(2025.10) 근거: Claude -30.8%, GPT-5 -62.7%. LLM 직접 매매는 실패.

---

## 3 현재 구조

```
[OpenClaw] ── 1~4시간마다 ──> sentiment.json
                                    │
[LLMSentimentNFI]                   │
    └── confirm_trade_entry()       │
            ├── super() (NFI X7 원본 로직 전체 실행)
            ├── NFI가 False 반환 → 그대로 거부
            └── NFI가 True 반환 → sentiment 체크
                    ├── bearish → 롱 진입 거부
                    ├── bullish → 숏 진입 거부
                    └── neutral / 없음 → NFI 판단 존중 (통과)
```

NFI가 먼저 판단하고, NFI가 허용한 진입에 대해서만 LLM이 거부권을 행사한다.

### 3.1 sentiment.json 스키마

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
| confidence | float | N | 0.0~1.0 (로깅/분석용. 매매 로직에 사용하지 않음) |
| reasoning | string | N | 디버깅/로깅용 |
| updated_at | ISO 8601 | Y | 4시간 초과 시 neutral fallback |

---

## 4 확장 계획

### 단계 1: 센티먼트 생성 (planning.md Phase 3)

OpenClaw가 실제로 sentiment.json을 생성하는 단계.

#### 4.1 데이터 소스

| 소스 | 수집 방법 | 용도 |
|---|---|---|
| Fear & Greed Index | alternative.me API (무료) | 시장 전체 온도 |
| 크립토 뉴스 헤드라인 | RSS / 크롤링 | 이벤트 감지 |
| 펀딩비 | Binance API (Freqtrade REST API 경유) | 롱/숏 편향 판단 |

#### 4.2 LLM 프롬프트 설계

```
You are a cryptocurrency market analyst.
Analyze the following data and determine the market sentiment for {pair}.

Data:
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

#### 4.3 LLM 역할의 한계

LLM은 sentiment 필드만 매매에 영향을 준다. confidence, reasoning은 로깅/분석 전용이다.

NFI가 자체적으로 시장 국면(7개 모드), 포지션 크기(grinding/rebuy), 리스크(derisking)를 관리하므로, LLM이 이 영역에 개입하지 않는다.

---

### 단계 2: 긴급 이벤트 감지 (planning.md Phase 4)

센티먼트와는 별개로, 거래 자체를 멈춰야 하는 긴급 상황 감지.

#### 4.4 긴급 이벤트 분류

| 카테고리 | 예시 | 대응 |
|---|---|---|
| critical | 거래소 해킹, 스테이블코인 디페그 | 전체 진입 차단 |
| high | 대규모 청산 캐스케이드, 규제 발표 | 전체 진입 차단 |

medium 이하는 NFI 자체 derisking 모드가 처리하므로 LLM이 개입하지 않는다.

#### 4.5 구현 방식

별도 파일 `emergency.json`:

```json
{
    "emergency": true,
    "severity": "critical",
    "event_type": "exchange_hack",
    "reason": "Binance hot wallet compromise reported",
    "updated_at": "2026-03-25T14:30:00Z",
    "expires_at": "2026-03-25T18:30:00Z"
}
```

만료 정책:
- `expires_at` 필드로 자동 만료. 초과 시 emergency 무시.
- `expires_at` 없으면 기본 4시간 후 만료.
- OpenClaw가 상황 해제 시 `"emergency": false`로 갱신.

`confirm_trade_entry()`에서 emergency.json 먼저 확인 → emergency이면 모든 진입 거부.

---

### 단계 3: 과거 매매 반성 (Reflection)

CryptoTrade 논문(EMNLP 2024) 참고. 센티먼트 생성 품질 개선용.

```
[Freqtrade] ── 거래 종료 ──> trade_history (REST API)
                                    │
[OpenClaw] ── 매일 ──> 과거 거래 분석
    ├── 손실 거래 시점의 센티먼트와 실제 결과 비교
    └── 다음 센티먼트 생성 프롬프트에 과거 오판 사례 포함
```

LLM이 "지난번 이런 상황에서 bullish라고 했는데 실제로는 하락했다"를 인지하면, 유사 상황에서 더 신중한 판단을 내릴 수 있다.

매매 로직 자체를 변경하는 것이 아니라, 센티먼트 생성 프롬프트의 컨텍스트를 풍부하게 하는 것이다.

---

## 5 하지 않는 것

| 항목 | 이유 |
|---|---|
| LLM 직접 매매 실행 | Alpha Arena: 6개 중 4개 손실 |
| LLM 포지션 사이징 | NFI가 grinding/rebuy로 자체 관리. 간섭 시 충돌 |
| LLM 청산 판단 | NFI가 custom_exit/derisking으로 자체 관리 |
| LLM 시장 국면 판단 → 매매 반영 | NFI가 7개 모드로 자체 판단. 이중 판단은 혼란 |
| 실시간 API 호출 | 레이턴시, 비용, 장애 전파 |
| 가격 예측 | LLM은 시계열 예측에 부적합 |
| 고빈도 센티먼트 갱신 | 1~4시간 주기면 충분 |

---

## 6 참고 자료

| 자료 | 내용 |
|---|---|
| Alpha Arena (2025.10) | LLM 직접 매매 대회. 범용 LLM 대부분 손실 |
| CryptoTrade (EMNLP 2024) | Reflective LLM Agent. 과거 매매 반성 메커니즘 |
| claude-trader | Multi-Agent 심사단 방식 (3인 리뷰 + 판사) |
| openclaw-trader | Fear&Greed + 뉴스 + 긴급 키워드 스캔 |
