# Crypto Futures Bot — 프로젝트 규칙

## 프로젝트 개요

- **Crypto Futures Bot**: Freqtrade + OpenClaw + Claude LLM 하이브리드 암호화폐 선물 자동매매 시스템
- **기획안**: `docs/planning.md` (참고용)
- **아키텍처**: `docs/design/architecture.md`
- **기술스택**: Freqtrade (Docker) / OpenClaw + Claude LLM / Binance Futures / Docker Compose

---

## 아키텍처: 3계층 분리 (Execution / Intelligence / Monitoring)

### 원칙

- Freqtrade만 거래소 API 키를 보유. 유일한 매매 실행 주체.
- OpenClaw은 센티먼트 생성 + 모니터링 담당. 매매 권한 없음.
- LLM은 거부권만 보유. 시그널 생성 권한 없음.
- 센티먼트 연동은 파일 기반 (sentiment.json). API 호출 아님.
- OpenClaw 장애 시에도 Freqtrade는 neutral fallback으로 정상 작동.

### 디렉토리 구조

```
crypto-futures-bot/
├── docker-compose.yml                # Freqtrade + OpenClaw 컨테이너
├── .env.example                      # 환경변수 템플릿
├── docs/
│   ├── planning.md                   # 기획안
│   ├── design/
│   │   └── architecture.md           # 아키텍처 설계
│   └── ADR/                          # Architecture Decision Records
│       ├── README.md
│       ├── ADR-001-*.md
│       └── ...
├── freqtrade/
│   └── user_data/
│       ├── config.json               # Binance Futures 설정 (dry-run)
│       ├── sentiment.json            # OpenClaw → Freqtrade 센티먼트 (런타임 생성)
│       ├── sentiment.example.json    # 센티먼트 파일 형식 예시
│       ├── strategies/
│       │   └── LLMHybridStrategy.py  # 메인 전략
│       ├── data/                     # OHLCV 캔들 데이터 (gitignore)
│       ├── logs/                     # Freqtrade 로그 (gitignore)
│       └── notebooks/                # 분석 노트북
└── openclaw/                         # OpenClaw 설정 (Phase 3~4)
```

### 데이터 흐름

```
[OpenClaw] ── 1~4시간마다 ──> sentiment.json 파일 저장
[Freqtrade] ── 매 캔들마다 ──> sentiment.json 읽기 → 진입 필터 적용 → Binance Futures 매매
[Freqtrade REST API] ── 읽기 전용 ──> [OpenClaw] ──> [Telegram 브리핑]
```

---

## 코딩 컨벤션

### 전략 파일 (Python)

- Freqtrade `IStrategy` 인터페이스 v3 사용
- docstring 필수 (Google style)
- 타입 힌트 필수
- 지표 계산은 `populate_indicators()`에 집중
- LLM 센티먼트는 파일 읽기만. API 직접 호출 금지
- Hyperoptable 파라미터는 `IntParameter`, `DecimalParameter` 사용

### 설정 파일

- API 키는 코드/설정에 하드코딩 금지. `.env` 파일로 관리
- config.json의 `key`, `secret` 필드는 항상 빈 문자열 유지 (런타임에 환경변수 주입)

---

## 환경변수

- `.env.example`로 필요한 변수 목록 문서화
- 민감 정보(API 키, JWT 시크릿)는 `.env`에만 저장
- `.env`는 `.gitignore`에 포함 (절대 커밋 금지)

---

## 문서화

### 문서 디렉토리 구조

```
docs/
├── planning.md                 # 기획안
├── design/                     # 설계 문서
│   └── architecture.md
└── ADR/                        # Architecture Decision Records
    ├── README.md               # ADR 목록
    └── ADR-NNN-*.md
```

### Changelog

모든 문서 상단에 테이블 형식의 changelog를 작성한다.

```markdown
| 버전 | 변경내용 | 작성자 | 수정일 |
| --- | --- | --- | --- |
| v1.1 | 변경 내용 요약 | 김진범 | 2026-03-24 |
| v1.0 | 초기 작성 | 김진범 | 2026-03-24 |
```

- 작성자: 김진범
- 최신 버전이 상단

---

## ADR (Architecture Decision Record)

프로젝트의 모든 주요 의사결정은 `docs/ADR/` 폴더에 기록한다.

### 작성 기준

다음 중 하나에 해당하면 ADR을 작성한다:

- 기술/라이브러리 선정 또는 변경
- 아키텍처, 프로토콜, 인터페이스 방식 결정
- 기존 결정을 번복하는 경우

### 파일 규칙

- 경로: `docs/ADR/ADR-NNN-제목.md`
- 번호: 순차 부여 (001, 002, ...)
- 상태: `제안` → `확정` → `대체됨` / `폐기`
- 확정된 ADR은 수정하지 않는다. 변경 시 새 ADR을 작성하고 기존 ADR 상태를 `대체됨`으로 변경.
- 새 ADR 작성 시 `docs/ADR/README.md` 목록에 추가.

### 템플릿

```markdown
# ADR-NNN: 제목

- **상태**: 제안 / 확정 / 대체됨 / 폐기
- **일자**: YYYY-MM-DD
- **결정자**: 이름

## 배경
왜 이 결정이 필요한지

## 검토 선택지
1. **선택지 A** → 장단점
2. **선택지 B** → 장단점

## 결정
최종 선택

## 근거
왜 이것을 선택했는지

## 영향
이 결정으로 인해 변경되거나 추가 확인이 필요한 사항
```

---

## 버전 관리

- 커밋: `<type>: <subject>` (feat, fix, refactor, docs, test, chore)

---

## 핵심 설계 결정 (확정)

| 항목 | 결정 | 근거 |
|---|---|---|
| 트레이딩 프레임워크 | Freqtrade (Docker 이미지) | FreqAI 내장, 최대 커뮤니티, 선물 완전 지원 (ADR-001) |
| LLM 연동 | OpenClaw → sentiment.json → Freqtrade | 비용 $0, 장애 격리, 단순함 (ADR-002) |
| 센티먼트 통신 | JSON 파일 (sentiment.json) | KISS, 인프라 최소화, 디버깅 용이 (ADR-003) |
| 배포 | Docker Compose (로컬 서버 + jin-net) | 비용 $0, 기존 인프라 활용, nginx 리버스 프록시 (ADR-005) |
| 매매 전략 | NostalgiaForInfinityX7 + LLMSentimentNFI 서브클래스 | 커뮤니티 검증 전략, X7이 공식 권장, NFI 원본 수정 없음 |
| Freqtrade 코어 | 수정 안 함. Docker 이미지 사용 | upstream 업데이트 용이, 유지보수 최소화 |
| LLM 역할 | 거부권만 보유 (시그널 생성 권한 없음) | 할루시네이션 리스크 최소화 |
