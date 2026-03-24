# ADR-003: 센티먼트 통신 방식 결정

- **상태**: 확정
- **일자**: 2026-03-24
- **결정자**: 김진범

## 배경

OpenClaw가 생성한 센티먼트 데이터를 Freqtrade에 전달하는 통신 방식을 결정해야 한다.

## 검토 선택지

### 1. JSON 파일 (sentiment.json)
- 장점: 가장 단순, 추가 인프라 불필요, 디버깅 용이 (파일 직접 확인 가능)
- 단점: 파일 I/O, 동시 쓰기/읽기 경합 가능성

### 2. Redis
- 장점: 빠른 읽기, TTL 자동 만료, pub/sub 가능
- 단점: 추가 컨테이너 필요, 운영 복잡도 증가

### 3. SQLite
- 장점: 쿼리 가능, 히스토리 보존
- 단점: 단순 key-value에 과잉, 파일 잠금 이슈

### 4. REST API (OpenClaw → Freqtrade)
- 장점: 실시간
- 단점: OpenClaw에 API 서버 필요, 양방향 의존성 발생

## 결정

**선택지 1: JSON 파일**을 채택한다.

## 근거

1. **KISS 원칙**: 5개 페어의 센티먼트 데이터에 Redis/SQLite는 과잉
2. **동시 접근 안전**: OpenClaw는 1~4시간에 1회 쓰기, Freqtrade는 60초에 1회 읽기. 경합 확률 극히 낮음. JSON 파일은 atomic write (임시 파일 → rename)로 안전하게 처리 가능
3. **디버깅**: `cat sentiment.json`으로 즉시 상태 확인. 운영 중 문제 파악이 가장 빠름
4. **인프라 최소화**: 추가 컨테이너 없음. VPS 비용 절감

## 영향

- sentiment.json 스키마 고정 (pair → {sentiment, confidence, updated_at})
- Docker 볼륨 공유로 두 컨테이너가 같은 파일 접근
- OpenClaw는 atomic write 패턴 사용 권장 (write to .tmp → rename)
- Freqtrade는 60초 캐시로 파일 I/O 최소화
