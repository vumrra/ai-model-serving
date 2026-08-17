# Architecture

## 요청 경로

```text
Client → Cloud Run Gateway → RunPod Qwen Engine
```

Gateway는 사용자-facing API 계약과 보안을 담당하고, engine은 token generation과 GPU scheduling을 담당합니다. 이 경계를 지키면 vLLM과 SGLang을 교체해도 client 코드는 변하지 않습니다.

## 환경별 구조

- Local mock: API 개발과 PR 테스트
- Local CPU: 실제 Qwen tokenizer/chat template smoke
- RunPod GPU: raw engine benchmark와 staging
- Cloud Run: 변하지 않는 공개 HTTPS URL과 release 전환

Local Compose의 Prometheus는 Gateway `/metrics`를 10초마다 수집하고 alert rule을 읽습니다.
Cloud Run demo는 `/metrics`와 smoke gate까지 포함하지만 외부 metrics backend 연결은 계정별
선택 사항입니다. 장기 운영 단계에서는 Google Managed Service for Prometheus나 같은 역할의
backend를 연결해야 dashboard와 alert가 지속 동작합니다.

## Production-shaped의 의미

이 프로젝트는 단일 GPU replica이므로 HA와 autoscaling을 보장하지 않습니다. 대신 실제 운영에서 중요한 immutable artifact, staging gate, telemetry, rollback, incident drill과 비용 통제를 검증합니다.
