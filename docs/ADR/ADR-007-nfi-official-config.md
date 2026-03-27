# ADR-007: NFI 공식 설정 방식 채택

- **상태**: 확정
- **일자**: 2026-03-28
- **결정자**: 김진범

## 배경

커스텀 config.json + CLI --config 플래그 방식으로 운영 중 3일간 거래 0건 발생.
config 값이 여러 번 잘못 변경되면서 (pricing, timeout, ccxt 등) NFI 공식 설정과 괴리 발생.

## 검토 선택지

1. **커스텀 config 유지** → config.json에 모든 설정 직접 작성, --config 플래그로 로드
2. **NFI 공식 방식 채택** → add_config_files + .env 환경변수, NFI 레포 config 파일 그대로 사용

## 결정

NFI 공식 방식 채택. NFI 레포의 config 파일을 수정하지 않고 그대로 사용.

## 근거

- NFI 공식 docker-compose.yml은 --config 플래그를 사용하지 않음
- add_config_files로 config 계층을 순차 로드하는 것이 공식 방식
- .env로 API 키/서버 설정을 주입하는 것이 공식 방식
- 커스텀 config 작성 시 설정값 오류 위험 (실제로 3일간 거래 0건 유발)
- NFI 레포 파일을 수정하지 않으면 git pull로 업데이트 시 충돌 없음

## 영향

- config.json: add_config_files만 포함하는 최소 구조
- .env: API 키, 서버 설정, trading_mode 등 환경변수
- docker-compose.yml: --strategy-path . 사용, --config 플래그 제거
- nfi/user_data: NFI 디렉토리 구조 그대로 사용
- nfi/configs: 수정 없이 원본 사용

### Config 로딩 순서 (NFI 공식)

1. user_data/config.json (strategy + add_config_files)
2. trading_mode-spot.json
3. pairlist-volume-binance-usdt.json
4. blacklist-binance.json
5. exampleconfig.json (핵심 트레이딩 파라미터)
6. exampleconfig_secret.json (API 서버, 텔레그램)
7. .env 환경변수 (최종 오버라이드)
