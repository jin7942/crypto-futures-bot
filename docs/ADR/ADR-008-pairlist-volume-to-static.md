# ADR-008: VolumePairList → 메이저 Static PairList 전환

- **상태**: 확정
- **일자**: 2026-05-05
- **결정자**: 김진범

## 배경

NFI X6 + spot + VolumePairList 조합으로 38일 dry-run 운영 결과 -29.28% 손실.

원인 추적을 위해 동일 38일 기간 백테스트 3종 비교 실시:

| 시나리오 | 페어풀 | 거래 | 수익률 | 승률 | DD |
|---|---|---:|---:|---:|---:|
| A. Dry-run 운영 결과 | VolumePairList 자동 | 40 | **-29.28%** | 실질 -29% | -29% |
| B. Backtest, dry-run과 동일 6페어 | StaticPairList | 4 | -18.09% | 25% | 18.09% |
| C. Backtest, NFI 공식 메이저 페어 | StaticPairList 160 | 28 | **+10.18%** | **96.4%** | 2.27% |

**같은 NFI X6 전략 + 같은 spot + 같은 38일이지만 페어풀에 따라 -29%와 +10%로 나뉨.**

## 검토 선택지

1. **VolumePairList 유지** → 거래량 상위 자동 선정 (현재 방식)
2. **NFI 공식 메이저 Static PairList 채택** → BTC/ETH/ADA/DOT/MATIC/SOL 등 70~160개 메이저 알트만 거래

## 결정

NFI 공식 운영용 static pairlist (`pairlist-static-binance-spot-usdt.json`, 70페어) 채택.

## 근거

- VolumePairList는 거래량 상위만 보고 페어를 자동 선정 → 펌프 진행 중인 잡코인이 자동 진입
- Dry-run에서 잡힌 6페어 중 5개(NOM/UTK/PNUT/STO/MDT)는 NFI 공식 페어리스트에 없는 비메이저 코인
- 펌프 끝물 진입 → 덤프 시작 → NFI grind 로직으로 -90% 끌고 가도 회복 불가
- NFI 공식 페어풀 백테스트 결과: Sharpe 6.67, Profit factor 4.98, 단 1페어만 손실
- 백테스트와 dry-run 결과 차이는 11%p로 시뮬 한계는 작음 → 페어 선택이 본질적 문제
- NFI 공식 운영용(70개)은 백테스트용(160개)에 더해 SpreadFilter, FullTradesFilter, VolumePairList 보조필터를 추가해 호가 스프레드 큰 페어 자동 제거

## 영향

- `nfi/user_data/config.json`: `pairlist-volume-binance-usdt.json` → `pairlist-static-binance-spot-usdt.json`
- 신규 진입은 NFI 권장 메이저 페어풀에서만 발생
- 기존 잡코인 6포지션은 컨테이너 재생성으로 정리 (dry-run DB 초기화)
- `dry_run_wallet`: 10000 USDT로 리셋
- 1주일 dry-run 검증 후 실거래 가능성 검토
