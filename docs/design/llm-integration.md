| 버전 | 변경내용 | 작성자 | 수정일 |
| --- | --- | --- | --- |
| v2.0 | OpenClaw 조사 반영: 배포 구조, 비용, 데이터 흐름 구체화 | 김진범 | 2026-03-25 |
| v1.2 | 재검토: NFI 중심 재정립, 과대 설계 제거, LLM 역할 범위 명확화 | 김진범 | 2026-03-25 |
| v1.0 | 초기 작성 | 김진범 | 2026-03-25 |

# LLM 연동 설계

## 1 전제

**매매 판단의 주체는 NostalgiaForInfinityX7(NFI)이다.** LLM은 NFI가 볼 수 없는 정보(뉴스, 소셜, 거시 지표)를 보는 보조 필터다.

NFI는 순수 기술적 지표(가격, 거래량, RSI, BB 등)만 본다. "Binance 해킹" 뉴스가 터져도 차트에 반영되기 전까지 모른다. LLM의 가치는 이 맹점을 보완하는 것이다.

| 영역 | 담당 | LLM 개입 |
|---|---|---|
| 시그널 생성 | NFI | 없음 |
| 포지션 사이징 | NFI (grinding, rebuy) | 없음 |
| 청산 판단 | NFI (custom_exit, derisking) | 없음 |
| 레버리지 | NFI (모드별 동적 조절) | 없음 |
| **진입 필터 (뉴스/거시 기반)** | LLM | **거부권** |
| **긴급 이벤트 감지** | LLM | **전체 진입 차단** |
| **모니터링/브리핑** | LLM | **Telegram 리포트** |

---

## 2 설계 원칙

| 원칙 | 근거 |
|---|---|
| NFI 로직 간섭 금지 | NFI의 포지션 관리, 모드 전환, 청산 로직은 건드리지 않는다 |
| LLM은 NFI가 못 보는 것만 본다 | 뉴스, Fear & Greed, 소셜 센티먼트 등 비기술적 데이터 |
| 파일 기반 비동기 연동 | `/opt/openclaw/shared/sentiment/` 경로로 파일 공유 |
| neutral fallback | sentiment.json 없거나 stale → NFI 원본 그대로 동작 |
| 비용 최소화 | Anthropic API 종량제. Sonnet 4.5 사용, isolated cron으로 토큰 절약 |

Alpha Arena 대회(2025.10) 근거: Claude -30.8%, GPT-5 -62.7%. LLM 직접 매매는 실패.

---

## 3 시스템 구조

### 3.1 배포 구조

```
로컬 서버 (192.168.0.66)
├── Freqtrade (Docker, jin-net)
│     └── /freqtrade/user_data/shared/ ← 볼륨 마운트
│
├── OpenClaw (네이티브, systemd)
│     └── /opt/openclaw/shared/sentiment/ → sentiment.json 쓰기
│
└── /opt/openclaw/shared/sentiment/  ← 호스트 바인드 마운트 (양쪽 공유)
```

- OpenClaw: 네이티브(systemd) 배포. `/factory/openclaw-agent/`에서 관리
- Freqtrade: Docker 컨테이너. 바인드 마운트로 sentiment 디렉토리 공유
- 두 프로세스가 같은 호스트 디렉토리를 통해 파일 교환

### 3.2 데이터 흐름

```
[OpenClaw cron (4시간마다)]
    ├── Fear & Greed Index 수집 (alternative.me API)
    ├── 크립토 뉴스 수집 (RSS/크롤링)
    ├── Freqtrade REST API 조회 (포지션, 수익)
    ├── Claude Sonnet 4.5에 분석 요청
    └── /opt/openclaw/shared/sentiment/sentiment.json 쓰기
                    │
                    ▼
[LLMSentimentNFI - confirm_trade_entry()]
    ├── super() → NFI X7 원본 로직 전체 실행
    ├── NFI가 False → 그대로 거부
    └── NFI가 True → sentiment.json 읽기
            ├── bearish → 롱 진입 거부
            ├── bullish → 숏 진입 거부
            └── neutral / 없음 → NFI 판단 존중

[OpenClaw heartbeat (30분마다)]
    ├── Freqtrade REST API로 포지션/수익 조회
    └── Telegram 브리핑 전송
```

### 3.3 sentiment.json

경로: `/opt/openclaw/shared/sentiment/sentiment.json`

```json
{
    "BTC/USDT:USDT": {
        "sentiment": "bullish",
        "confidence": 0.7,
        "reasoning": "Fear & Greed 72 (Greed), 펀딩비 정상, ETF 유입 증가 뉴스",
        "updated_at": "2026-03-25T12:00:00Z"
    }
}
```

| 필드 | 타입 | 필수 | 용도 |
|---|---|---|---|
| sentiment | string | Y | "bullish" / "bearish" / "neutral". **유일하게 매매에 영향** |
| confidence | float | N | 0.0~1.0. 로깅/분석 전용 |
| reasoning | string | N | 디버깅/로깅용 |
| updated_at | ISO 8601 | Y | 4시간 초과 시 neutral fallback |

---

## 4 OpenClaw 구성

### 4.1 스킬 구조

```
/factory/openclaw-agent/
├── SOUL.md                          # 에이전트 인격/행동 규칙
├── AGENTS.md                        # 에이전트 지침
├── skills/
│   └── crypto-sentiment/
│       └── SKILL.md                 # 센티먼트 생성 스킬
└── workspace/
    └── shared/sentiment/            # → /opt/openclaw/shared/sentiment/
```

### 4.2 Cron 설정

```bash
# 센티먼트 생성 (4시간마다)
openclaw cron add \
  --name "sentiment-update" \
  --cron "0 */4 * * *" \
  --tz "Asia/Seoul" \
  --session isolated \
  --model "anthropic/claude-sonnet-4-5" \
  --message "시장 센티먼트 분석 후 sentiment.json 생성"

# 긴급 이벤트 스캔 (30분마다)
openclaw cron add \
  --name "emergency-scan" \
  --cron "*/30 * * * *" \
  --tz "Asia/Seoul" \
  --session isolated \
  --model "anthropic/claude-sonnet-4-5" \
  --message "긴급 이벤트 스캔 후 필요 시 emergency.json 생성"
```

- `isolated` 세션: 매 실행마다 새 히스토리. 토큰 누적 방지
- Sonnet 4.5: Opus 대비 ~60% 저렴

### 4.3 데이터 소스

| 소스 | API | 비용 | 갱신 주기 |
|---|---|---|---|
| Fear & Greed Index | alternative.me/crypto/fear-and-greed-index/ | 무료 | 일 1회 |
| 크립토 뉴스 | CoinDesk/CoinTelegraph RSS | 무료 | 실시간 |
| Freqtrade 상태 | http://freqtrade:8080/api/v1/ (jin-net) | 무료 | 요청 시 |

### 4.4 LLM 프롬프트

```
You are a cryptocurrency market analyst.
Analyze the following data for each pair and determine market sentiment.

Data:
- Fear & Greed Index: {fng_value} ({fng_label})
- Recent crypto news headlines:
{headlines}

For each pair in [BTC/USDT:USDT, ETH/USDT:USDT, ...], respond in JSON:
{
    "PAIR": {
        "sentiment": "bullish" | "bearish" | "neutral",
        "confidence": 0.0-1.0,
        "reasoning": "1-2 sentences"
    }
}

Rules:
- Insufficient or contradictory data → "neutral", confidence < 0.5
- confidence > 0.8 requires strong agreement across multiple indicators
- Never predict specific prices
- If no pair-specific news, use general market sentiment
```

---

## 5 비용

2026년 1월, Anthropic이 Claude 구독의 서드파티 사용을 차단. API 종량제 필수.

| 항목 | 월 예상 비용 |
|---|---|
| 센티먼트 생성 (4시간, 6회/일, Sonnet) | $2~5 |
| 긴급 이벤트 스캔 (30분, 48회/일, Sonnet) | $3~8 |
| 브리핑 생성 (일 2회, Sonnet) | $1~2 |
| **합계** | **$6~15/월** |

비용 절감 방안:
- Sonnet 4.5 사용 (Opus 대비 ~60% 저렴)
- isolated cron으로 컨텍스트 누적 방지
- 페어별 개별 호출 대신 한 번에 전체 페어 분석

---

## 6 긴급 이벤트 감지

센티먼트와 별개로, 거래 자체를 멈춰야 하는 긴급 상황 감지.

### 6.1 분류

| 카테고리 | 예시 | 대응 |
|---|---|---|
| critical | 거래소 해킹, 스테이블코인 디페그 | 전체 진입 차단 |
| high | 대규모 청산 캐스케이드, 규제 발표 | 전체 진입 차단 |

medium 이하는 NFI 자체 derisking이 처리.

### 6.2 emergency.json

경로: `/opt/openclaw/shared/sentiment/emergency.json`

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
- `expires_at` 초과 시 무시
- `expires_at` 없으면 기본 4시간 후 만료
- OpenClaw가 상황 해제 시 `"emergency": false`로 갱신

---

## 7 모니터링/브리핑

OpenClaw heartbeat (30분)로 Freqtrade REST API 조회 후 Telegram 전송.

| 브리핑 | 시간 | 내용 |
|---|---|---|
| 아침 브리핑 | 08:00 | 시장 요약, 전일 PnL, 오픈 포지션 |
| 저녁 리포트 | 22:00 | 일간 성과, 승률, 센티먼트 요약 |
| 긴급 경고 | 즉시 | emergency 감지 시 |

---

## 8 장애 시나리오

| 장애 | 영향 | 대응 |
|---|---|---|
| OpenClaw 다운 | sentiment.json 미갱신 | 4시간 후 neutral fallback → NFI 그대로 동작 |
| Anthropic API 장애 | 센티먼트 생성 실패 | 기존 sentiment.json 유지, 4시간 후 neutral |
| sentiment.json 파싱 에러 | 읽기 실패 | neutral fallback |
| Freqtrade 다운 | 매매 중단 | stoploss_on_exchange가 거래소에서 손절 |

모든 장애에서 NFI는 독립적으로 동작한다. OpenClaw는 "있으면 좋고, 없어도 된다."

---

## 9 하지 않는 것

| 항목 | 이유 |
|---|---|
| LLM 직접 매매 실행 | Alpha Arena: 6개 중 4개 손실 |
| LLM 포지션 사이징 | NFI grinding/rebuy와 충돌 |
| LLM 청산 판단 | NFI custom_exit/derisking과 충돌 |
| LLM 시장 국면 판단 → 매매 반영 | NFI 7개 모드와 이중 판단 |
| 실시간 API 호출 | 레이턴시, 비용, 장애 전파 |
| 가격 예측 | LLM은 시계열 예측에 부적합 |

---

## 10 참고 자료

| 자료 | 내용 |
|---|---|
| Alpha Arena (2025.10) | LLM 직접 매매 대회. 범용 LLM 대부분 손실 |
| CryptoTrade (EMNLP 2024) | Reflective LLM Agent. 과거 매매 반성 메커니즘 |
| openclaw-trader | OpenClaw 기반 크립토 봇 (직접 매매 방식, 우리와 다름) |
| OpenClaw Docs | cron, heartbeat, skills, Docker 배포 가이드 |
