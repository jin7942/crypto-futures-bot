# ADR-009: Trade DB 호스트 볼륨 마운트

- **상태**: 확정
- **일자**: 2026-05-05
- **결정자**: 김진범

## 배경

dry-run/실거래 시 거래 이력은 sqlite DB에 저장됨. 기본값은 컨테이너 내부 `/freqtrade/tradesv3.dryrun.sqlite`로 호스트 마운트되지 않음.

문제:
- `docker compose down/up`, 컨테이너 재생성, 이미지 업데이트 시 거래 이력 전부 손실
- 운영 중 우발적 컨테이너 재생성 발생 시 38일치 dry-run 데이터가 한 번에 사라짐 (실제 발생 사례)
- 실거래 전환 후에도 동일 리스크 → 세금 신고/감사용 거래 이력 보존 불가

## 검토 선택지

1. **현재 방식 유지** → 컨테이너 내부 DB, 재생성마다 초기화
2. **DB 파일을 호스트 볼륨 안으로 이동** → `--db-url`로 user_data 경로 지정

## 결정

NFI 공식 docker-compose 방식 채택. `--db-url sqlite:////freqtrade/user_data/tradesv3.dryrun.sqlite` 명시.

## 근거

- `./nfi/user_data:/freqtrade/user_data`는 이미 마운트되어 있음
- DB 파일을 user_data 안에 두면 호스트(`./nfi/user_data/tradesv3.dryrun.sqlite`)에 자동 영속화
- NFI 공식 docker-compose도 동일 방식 사용 (line 35)
- 추가 볼륨 정의 불필요, 기존 마운트 재활용
- `.gitignore`에 `*.sqlite*` 추가하여 거래 이력은 git 제외

## 영향

- `docker-compose.yml`: command에 `--db-url sqlite:////freqtrade/user_data/tradesv3.dryrun.sqlite` 추가
- `.gitignore`: `*.sqlite`, `*.sqlite-shm`, `*.sqlite-wal` 추가
- DB 파일 위치: `nfi/user_data/tradesv3.dryrun.sqlite` (호스트)
- 컨테이너 재생성/이미지 업데이트 시 거래 이력 보존
- 실거래 전환 시 동일 패턴으로 `tradesv3.sqlite` 사용 (NFI 공식 방식)
