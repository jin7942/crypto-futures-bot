# ADR-002: LLM 연동 방식 결정

- **상태**: 확정
- **일자**: 2026-03-24
- **결정자**: 김진범

## 배경

LLM을 트레이딩 전략에 통합하는 방식을 결정해야 한다. LLM의 역할은 시장 국면 판단 및 진입 시그널 필터링이다.

## 검토 선택지

### 1. Freqtrade 전략 내부에서 Claude API 직접 호출
- 장점: 단순한 구조, 지연 없음
- 단점: API 비용 발생 (월 $2~5), Freqtrade 프로세스에 API 의존성 추가

### 2. OpenClaw가 센티먼트 생성 → 파일로 전달 → Freqtrade가 읽기
- 장점: 비용 $0 (Claude Max 구독 활용), 장애 격리, Freqtrade에 외부 의존성 없음
- 단점: 1~4시간 지연 (실시간 아님)

### 3. OpenClaw REST API를 Freqtrade에서 호출
- 장점: 실시간에 가까움
- 단점: OpenClaw에 API 서버 구현 필요, OpenClaw 장애 시 Freqtrade 영향

## 결정

**선택지 2: OpenClaw → sentiment.json → Freqtrade 파일 기반 연동**을 채택한다.

## 근거

1. **비용 $0**: Claude Max 구독을 OpenClaw가 그대로 사용. 별도 API 비용 없음
2. **장애 격리**: OpenClaw가 죽어도 마지막 sentiment.json이 남아있음. Freqtrade는 neutral fallback으로 정상 작동
3. **단순함**: 파일 하나로 통신. API 연동, 인증, 에러 핸들링 불필요
4. **지연 수용 가능**: 시장 국면(bullish/bearish)은 분 단위로 바뀌지 않음. 1~4시간 주기로 충분

## 영향

- OpenClaw에 sentiment.json 생성 스킬 구현 필요
- Freqtrade 전략에 파일 읽기 로직 구현 (완료)
- Docker 볼륨 공유 설정 필요
- anthropic 패키지가 Freqtrade 의존성에서 제거됨
