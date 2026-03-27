# ADR-006: 선물(Futures) → 현물(Spot) 전환

- **상태**: 확정
- **일자**: 2026-03-28
- **결정자**: 김진범

## 배경

Binance Futures + NFI X7 조합으로 3일간 dry-run 운영 결과, 거래 0건 발생.
원인 분석 과정에서 선물 모드의 구조적 문제와 NFI의 설계 의도를 재검토.

## 검토 선택지

1. **선물(Futures) 유지** → 숏 가능, 레버리지 가능
2. **현물(Spot) 전환** → 숏 불가, 레버리지 불가, NFI 본래 설계

## 결정

현물(Spot)으로 전환.

## 근거

데이터 기반 근거:

| 항목 | 근거 |
|---|---|
| 선물 트레이더 손실률 | 90-95% (Binance 커뮤니티), 연간 수익자 1.6%만 |
| 레버리지 효과 | 2x에서 거래당 -1.9bp 수익 감소 (NBER, 20만명 데이터) |
| Funding rate 비용 | 연 10.95~54.75% 숨겨진 비용 (현물은 0) |
| 2025년 강제 청산 | $150B (2025.10.10 단일: $19.3B, 160만명) |
| NFI 설계 대상 | 현물(spot) — can_short은 조건부 추가 기능 |
| Freqtrade 공식 권장 | "spot에서 수익 증명 후에만 futures 고려하라" |
| Freqtrade #8700 | 숏 추가가 기존 전략 성과를 파괴하는 사례 보고 |
| Futures 백테스트 | funding rate/청산 수수료 미반영으로 낙관적 |

## 영향

- docker-compose.yml: trading_mode-futures.json → trading_mode-spot.json
- 페어 형식: BTC/USDT:USDT → BTC/USDT
- 숏 포지션 불가
- 레버리지 불가 (1x 고정)
- funding rate 비용 제거
- 청산 리스크 제거
