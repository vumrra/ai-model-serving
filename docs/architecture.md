# Architecture

## 현재 요청 경로

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

## 목표 Kubernetes 요청 경로

```text
Git → Argo CD → Helm release → KServe manifest
                    ↓
Client → Gateway → InferenceService → GPU Pod → vLLM 또는 SGLang
```

- Argo CD는 Git에 고정된 image digest와 Helm values를 동기화합니다.
- KServe는 `ServingRuntime`의 실행 방법과 `InferenceService`의 모델·GPU 요구사항을 조합합니다.
- Kubernetes는 GPU Pod 배치, 재시작, Service 연결과 replica 유지를 담당합니다.
- vLLM과 SGLang은 실제 token generation을 수행합니다.
- Prometheus와 Grafana는 요청 지연, queue, GPU와 KV cache 상태를 관측합니다.

엔진 비교 중에는 KServe Standard Mode에서 replica를 1로 고정하고 autoscaling을 끕니다.
엔진을 선택한 뒤 KEDA autoscaling과 canary를 적용합니다. Knative는 scale-to-zero의 비용 절감이
모델·GPU cold start보다 중요한 환경에서만 추가합니다.

## Production-shaped의 의미

현재 구현은 단일 GPU replica이므로 HA와 autoscaling을 보장하지 않습니다. 목표 단계에서는
KServe와 Kubernetes로 복구·확장·배포를 실험하되, immutable artifact, staging gate,
telemetry, rollback, incident drill과 비용 통제를 계속 검증합니다.
