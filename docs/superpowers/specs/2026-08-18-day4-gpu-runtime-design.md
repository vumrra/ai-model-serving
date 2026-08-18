# Day 4 GPU Runtime Design

## 목표

Qwen3-4B를 동일한 조건으로 vLLM과 SGLang에서 실행할 수 있는 GPU 이미지를 만들고,
RunPod L40S에서 각 이미지를 한 번에 하나씩 검증한다. 4일차는 성능 우열을 판단하지 않고
모델 로딩, 인증, JSON 응답과 SSE streaming이 실제 GPU에서 동작하는지만 확인한다.

## 범위

- vLLM과 SGLang runtime image를 서로 다른 GHCR repository에 build하고 digest로 식별한다.
- 선택한 엔진 하나를 RunPod L40S 한 대에 배포한다.
- `/v1/models` readiness와 Chat Completions JSON·SSE smoke를 수행한다.
- 실행 결과와 정제된 Pod metadata를 GitHub Actions artifact로 남긴다.
- 성공·실패와 관계없이 생성한 Pod를 종료하며, 예약 cleanup workflow를 안전망으로 둔다.
- GitHub Actions는 현재 필요한 `ci`, `gpu-runtime`, `cleanup-runpod` 세 개만 유지한다.

다음 항목은 제외한다.

- vLLM과 SGLang 성능 비교: 7일차
- Kubernetes와 KServe 배포: 5~6일차
- staging, promotion, rollback: 8~9일차
- 로컬 Mac에서 CUDA image 실행: NVIDIA GPU가 없으므로 정적 검증까지만 수행

## 구성

```text
workflow_dispatch(engine)
  -> engine별 digest 고정 base image 검증
  -> qwen-vllm 또는 qwen-sglang image build/push
  -> RunPod L40S Pod 생성
  -> auth proxy :8000
  -> engine :8001
  -> readiness -> JSON smoke -> SSE smoke
  -> artifact upload
  -> always Pod delete
```

`gpu-runtime.yaml` 하나가 이미지 build와 smoke를 묶는다. build 결과의 digest가 곧 smoke 대상이므로
별도 workflow 사이에서 run ID와 artifact를 전달하지 않는다. 입력은 `vllm` 또는 `sglang` 한 개만
받는다. 두 엔진을 비교하려면 workflow를 각각 실행해 GPU가 동시에 점유되지 않게 한다.

## 동일 실행 조건

두 엔진은 아래 값을 공유한다.

| 항목 | 값 |
| --- | --- |
| GPU | NVIDIA L40S 1장 |
| 모델 | `Qwen/Qwen3-4B` |
| revision | `1cfa9a7208912126459214e8b04321603b3df60c` |
| dtype | `bfloat16` |
| context length | `8192` |
| tensor parallel | `1` |
| GPU memory utilization | `0.90` |
| 공개 port | auth proxy `8000` |
| 내부 engine port | `8001` |

엔진별 CLI 차이는 각 `entrypoint.sh`가 담당한다. workflow와 RunPod 코드는 공통 환경변수만 전달한다.

## 이미지 규칙

- vLLM image: `ghcr.io/<owner>/qwen-vllm:<git-sha>`
- SGLang image: `ghcr.io/<owner>/qwen-sglang:<git-sha>`
- RunPod에는 tag가 아닌 `@sha256:<digest>`를 전달한다.
- upstream base image도 `tag@sha256:<digest>` 형식만 허용한다.
- Dockerfile은 upstream runtime에 auth proxy만 얹으며 CUDA나 엔진을 다시 설치하지 않는다.

## 보안과 비용

- `ENGINE_API_KEY` 값은 image, Pod metadata와 artifact에 기록하지 않는다.
- RunPod secret reference만 Pod 환경변수에 전달한다.
- Pod 이름에 만료 시각을 넣고 scheduled cleanup이 기한 초과 Pod를 삭제한다.
- workflow의 마지막 삭제 단계는 `if: always()`로 실행한다.
- 생성 직후 시간당 비용과 예상 총비용이 상한을 넘으면 즉시 삭제하고 실패한다.
- 공개 proxy는 `/v1/models`와 `/v1/chat/completions`만 노출한다.

## 실패 처리

- 잘못된 image digest, model revision, TTL 또는 secret 이름은 Pod 생성 전에 거부한다.
- readiness timeout은 어떤 단계도 실행하지 않고 cleanup으로 이동한다.
- JSON 또는 SSE smoke 실패 시 결과를 artifact에 남긴 뒤 cleanup한다.
- Pod 삭제는 파일이 없을 때 성공으로 처리해 생성 이전 실패를 가리지 않는다.
- scheduled cleanup은 workflow 강제 취소나 runner 장애로 마지막 단계가 실행되지 않은 경우를 처리한다.

## 테스트와 완료 조건

로컬 자동 테스트는 다음을 검증한다.

- engine별 image 이름과 immutable digest 조합
- RunPod payload의 L40S, 공통 모델 설정, secret reference와 비용 상한
- readiness polling의 성공과 timeout
- JSON·SSE smoke가 OpenAI 호환 응답을 확인함
- workflow에 `always()` cleanup과 engine별 image 이름이 존재함
- 제거한 미래 workflow를 README가 현재 기능처럼 안내하지 않음

실제 4일차 완료 증거는 vLLM과 SGLang 각각의 GitHub Actions 실행에서 다음 artifact가 생성되는 것이다.

- immutable runtime image digest
- engine 이름과 model revision
- JSON·SSE smoke 결과
- secret이 제거된 RunPod metadata
- Pod 삭제 성공 기록
