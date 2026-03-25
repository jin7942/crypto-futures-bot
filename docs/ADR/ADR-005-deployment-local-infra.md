# ADR-005: 배포 전략 변경 (로컬 서버 인프라 활용)

- **상태**: 확정
- **일자**: 2026-03-24
- **결정자**: 김진범
- **대체 대상**: ADR-004

## 배경

ADR-004에서 "단일 VPS에 Docker Compose 배포"로 결정했으나, 실제로는 192.168.0.66 로컬 서버에 Docker 인프라(jin-net, nginx 리버스 프록시, dnsmasq, Prometheus/Grafana 모니터링)가 이미 구축되어 있다. VPS를 별도로 구매할 필요가 없다.

## 검토 선택지

### 1. 기존 로컬 서버 인프라 활용
- 장점: 비용 $0, 인프라 이미 구축됨, 모니터링 통합 가능
- 단점: 정전/네트워크 장애 시 중단 (stoploss_on_exchange로 완화)

### 2. 별도 VPS 구매
- 장점: 24/7 안정성, 거래소 DC 근접 가능
- 단점: 월 $5~15 비용, 인프라 이중 관리

## 결정

**선택지 1: 기존 로컬 서버 인프라 활용**을 채택한다.

## 근거

1. **비용 $0**: 이미 운영 중인 서버 활용. 수익 검증 전 추가 비용 불필요
2. **인프라 재사용**: jin-net, nginx 리버스 프록시, dnsmasq, Prometheus/Grafana 모니터링이 이미 구축되어 있음
3. **통합 모니터링**: 기존 Prometheus/Grafana에 Freqtrade 메트릭 추가 가능
4. **안전장치**: `stoploss_on_exchange: true`로 서버 다운 시에도 거래소에서 손절 처리
5. **접근성**: `http://freqtrade.internal`로 내부망 어디서든 접근

## 영향

- 배포 위치: 192.168.0.66 로컬 서버
- 네트워크: jin-net 외부 브릿지 네트워크에 참여
- 접근: nginx 리버스 프록시 경유 (freqtrade.internal)
- 모니터링: 기존 Prometheus/Grafana 스택 활용 가능
- 설정 분리: config.json (공개) + config.local.json (비밀, gitignore)
