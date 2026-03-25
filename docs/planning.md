| 버전 | 변경내용 | 작성자 | 수정일 |
| --- | --- | --- | --- |
| v1.1 | VPS → 로컬 서버 인프라 반영, Phase 1 내용 수정 | 김진범 | 2026-03-24 |
| v1.0 | 초기 작성 | 김진범 | 2026-03-24 |

# Crypto Futures Auto-Trading System — 기획안

## 1 개요

|항목|내용|
|---|---|
|문서 버전|v1.0|
|작성일|2026-03-24|
|작성자|Jin (김진범)|
|거래소|Binance Futures|
|대상 자산|암호화폐 선물 (Perpetual Futures)|
|핵심 스택|Freqtrade + OpenClaw + Claude LLM|

---

## 2 배경 및 목적

OpenClaw AI 에이전트를 활용한 암호화폐 선물 자동매매 시스템을 구축한다. LLM에게 직접 매매 권한을 부여하지 않는 안전한 계층 분리 아키텍처를 채택한다.

- **Freqtrade**: 매매 실행 엔진 (선물 롱/숏 + 레버리지 + 리스크 관리)
- **OpenClaw**: 리서치 어시스턴트 (시장 분석, 브리핑, 모니터링) + LLM 센티먼트 생성
- **Claude LLM**: 전략 분석 모듈 (시그널 필터링, 시장 국면 판단)

---

## 3 핵심 설계 원칙

|원칙|설명|
|---|---|
|LLM 비실행|LLM은 분석/판단만 담당. 거래소 API 키를 LLM에게 절대 부여하지 않음|
|파일 기반 연동|OpenClaw → sentiment.json → Freqtrade (단방향, 비동기)|
|장애 격리|OpenClaw 장애 시에도 Freqtrade 매매는 정상 작동 (neutral fallback)|
|비용 최적화|Claude Max 구독 활용 ($0 추가), 별도 API 비용 없음|

---

## 4 시스템 계층 구조

|계층|담당 시스템|역할|매매 권한|
|---|---|---|---|
|Execution|Freqtrade (Docker)|선물 매매 실행, 리스크 관리|거래소 API 직접 접근|
|Intelligence|OpenClaw + Claude LLM|시장 분석, 센티먼트 생성|없음 (파일 쓰기만)|
|Monitoring|OpenClaw|브리핑, 리포트, 이상 징후 감지|없음 (읽기 전용)|

---

## 5 데이터 흐름

```
[OpenClaw] ── 1~4시간마다 ──> 시장 분석 ──> sentiment.json 파일 저장
                                                    │
[Freqtrade] ── 매 캔들(5분)마다 ──> sentiment.json 읽기
     │
     ├── 기술적 지표 (RSI, BB, EMA, MACD) 계산
     ├── LLM 센티먼트 필터 적용 (거부권)
     └── Binance Futures 매매 실행
     │
     ▼
[Freqtrade REST API] ── 읽기 전용 ──> [OpenClaw] ──> [Telegram 브리핑]
```

### OpenClaw가 조회하는 Freqtrade API

- `GET /api/v1/profit` — 수익 현황
- `GET /api/v1/status` — 오픈 포지션
- `GET /api/v1/daily` — 일간 PnL
- `GET /api/v1/trades` — 거래 내역

---

## 6 Freqtrade 선물 거래 설정

### 6.1 거래소 설정

|항목|설정값|
|---|---|
|거래소|Binance Futures|
|trading_mode|futures|
|margin_mode|isolated|
|stake_currency|USDT|
|레버리지|3x 고정|
|can_short|True (롱/숏 양방향)|
|stoploss_on_exchange|True|
|max_open_trades|5|

### 6.2 리스크 관리

|항목|설정|
|---|---|
|손절 (stoploss)|-0.05 (-5%, 본금 기준. 3x레버 시 실제 -15%)|
|트레일링 스탑|trailing_stop_positive: 0.02, offset: 0.03|
|ROI (익절)|0분: 10%, 30분: 5%, 60분: 3%, 120분: 1%|
|긴급 정지|포트폴리오 드로다운 15% 초과 시 전체 거래 중단|
|초기 자본|$1,000 (dry-run)|

### 6.3 전략 구성

기술적 지표 기반 전략 + OpenClaw LLM 분석 필터 하이브리드 구조.

- **기술적 지표**: RSI, Bollinger Bands, EMA(9/21/50/200), MACD, Volume Ratio, ATR
- **LLM 시장 국면 필터**: bearish 판단 시 롱 진입 보류, bullish 판단 시 숏 진입 보류
- **Hyperopt**: RSI, BB factor 파라미터 최적화

---

## 7 OpenClaw 역할

|기능|설명|스케줄|
|---|---|---|
|센티먼트 생성|시장 분석 후 sentiment.json 파일 생성|1~4시간마다|
|아침 브리핑|시장 요약, 전일 수익, 주요 이벤트 정리|매일 08:00|
|포트폴리오 리포트|수익/손실, 승률, 페어별 성과 분석|매일 22:00|
|펀딩비 모니터링|펀딩비 급등 시 알림|실시간|
|이상 징후 경고|드로다운 10% 초과, 연속 손절 등|실시간|

---

## 8 비용 구조

|항목|월 비용|
|---|---|
|서버 (기존 로컬 인프라)|$0 (기존 장비 활용)|
|LLM (OpenClaw via Claude Max)|$0 (기존 구독 활용)|
|**추가 비용 합계**|**$0/월**|

---

## 9 구축 로드맵

|단계|기간|작업 내용|완료 조건|
|---|---|---|---|
|Phase 1|1주차|Freqtrade Docker 실행, 바이낸스 API 연동, jin-net 연결|Dry-run 정상 작동|
|Phase 2|1~2주차|전략 적용, 백테스트, 파라미터 튜닝|백테스트 양수 수익률|
|Phase 3|1주차|OpenClaw 설치, sentiment.json 연동, 브리핑 스킬|센티먼트 파일 정상 생성|
|Phase 4|1주차|Freqtrade API 연동, 모니터링, 텔레그램|브리핑 수신 확인|
|Phase 5|2주차|Dry-run 종합 테스트|2주간 안정 작동|
|Phase 6|진행중|소액 실전 전환, 점진적 스케일업|월간 양수 수익|

**예상 총 구축 기간: 6~8주**

---

## 10 리스크

### 기술적 리스크

- **LLM 할루시네이션**: 거부권만 부여하여 위험 최소화
- **OpenClaw 장애**: sentiment.json이 없거나 stale이면 neutral fallback
- **API 응답 지연**: stoploss_on_exchange로 거래소에서 직접 손절

### 재무적 리스크

- **레버리지 청산**: 3x레버 시 -33% 하락으로 청산 → 손절 -5%로 사전 차단
- **펀딩비 리스크**: 선물 포지션 유지 시 8시간마다 펀딩비 발생
- **절대 원칙: 잃어도 생활에 지장 없는 금액만 투입**

---

## 11 성공 기준

|기준|목표값|
|---|---|
|시스템 안정성|2주간 무장애 Dry-run|
|백테스트 수익률|6개월 백테스트 양수, Sharpe Ratio > 1.0|
|최대 드로다운|15% 이하|
|모니터링|매일 정시 브리핑 수신|
