# GTX 1660 추론 최적화와 아티클 실험 계획

이 문서는 6GB VRAM GTX 1660에서 Qwen 모델의 실용 성능을 최대한 끌어내고, RunPod L40S와
재현 가능하게 비교하기 위한 실험 계획입니다. 특정 설정이 빠를 것이라고 가정하지 않고 같은
workload를 반복 측정해 결론을 냅니다.

## 아티클의 핵심 질문

> Tensor Core가 없는 6GB Turing GPU에서 Qwen3를 안정적으로 API serving하려면 모델 크기,
> dtype, context, batching과 engine을 어떻게 선택해야 하는가?

다음 세 결과를 분리해서 설명합니다.

1. GTX 1660 안에서 설정을 바꿨을 때의 개선
2. 동일 설정에서 GTX 1660과 L40S의 순수 hardware 차이
3. 각 GPU가 감당할 수 있는 최대 실용 workload의 차이

## Hardware와 기준 구성

| 항목 | GTX 1660 | RunPod L40S |
| --- | --- | --- |
| architecture | Turing | Ada Lovelace |
| VRAM | 6GB GDDR5 | 48GB GDDR6 ECC |
| memory bandwidth | 약 192GB/s | 864GB/s |
| CUDA cores | 1,408 | 18,176 |
| Tensor cores | 없음 | 568 |
| 기본 모델 | Qwen3-1.7B | 기존 계획은 Qwen3-4B |
| 기본 dtype | FP16 | BF16 |
| 기본 context | 1024 | 기존 계획은 8192 |

GTX 1660의 첫 serving 기준값은 다음과 같습니다.

```text
engine                 vLLM
model                  Qwen/Qwen3-1.7B
dtype                  float16
max model length       1024
max sequences          1
GPU memory utilization 0.85
thinking               off
```

Qwen3-4B FP16은 가중치만으로 6GB를 넘으므로 GTX 1660의 비양자화 기준 모델로 사용하지
않습니다. 4bit AWQ/GPTQ는 기본 배포를 완성한 뒤 별도 실험으로만 추가합니다.

## 공정한 비교 규칙

아래처럼 모델과 context가 다른 결과를 직접 속도 비교하지 않습니다.

```text
GTX 1660: Qwen3-1.7B FP16, context 1024
L40S:     Qwen3-4B BF16, context 8192
```

순수 hardware 비교는 양쪽에서 다음 값을 동일하게 고정합니다.

```text
model revision
engine image digest
dtype FP16
context 1024
max sequences 1
thinking off
prompt dataset
requested output tokens
warm-up 횟수와 반복 횟수
```

그다음 별도의 capacity 비교에서 각 GPU에 적합한 모델, context와 concurrency를 사용합니다.

## 측정 지표

| 지표 | 의미 |
| --- | --- |
| cold startup | image/model/compile cache가 없는 최초 시작 |
| warm startup | cache가 있는 Pod 재시작 |
| TTFT | 요청부터 첫 token까지 시간 |
| TPOT | 첫 token 이후 token 간 평균 시간 |
| E2E latency | 요청부터 마지막 token까지 시간 |
| output tokens/sec | 단일 요청 생성 속도 |
| total throughput | 모든 동시 요청의 token 처리량 |
| p50/p95 | 반복 요청의 중앙값과 tail latency |
| VRAM peak | OOM 여유 확인 |
| system RAM peak | WSL/Kubernetes 안정성 확인 |
| power | GPU 소비전력 |
| joule/token | 전력 효율 비교 |
| success rate | timeout과 OOM을 포함한 성공 비율 |

각 조합은 warm-up 3회 후 최소 20회 측정합니다. 평균만 쓰지 않고 p50, p95와 표준편차를
함께 남깁니다. Prompt token 수와 실제 생성 token 수도 결과에 기록합니다.

## Workload

세 가지 workload를 구분합니다.

| workload | prompt | output | 목적 |
| --- | ---: | ---: | --- |
| short chat | 약 64 tokens | 64 | 대화형 체감 지연 |
| long prompt | 약 512 tokens | 64 | prefill과 TTFT |
| generation | 약 64 tokens | 256 | decode와 tokens/sec |

Concurrency는 `1 → 2 → 4` 순서로 올립니다. 이전 단계에서 OOM, timeout 또는 심각한 tail latency가
발생하면 다음 단계는 실행하지 않습니다.

## 최적화 실험 순서

한 번에 한 변수만 바꿉니다. 각 단계에서 가장 좋은 값을 다음 단계의 기준값으로 사용합니다.

### 1. GPU memory utilization

```text
0.75 / 0.80 / 0.85 / 0.90
```

높이면 KV cache 공간이 늘지만 Windows와 다른 GPU 사용량, engine overhead 때문에 OOM 여유가
줄어듭니다. 최고 수치가 아니라 반복 요청에서 안정적인 최고 수치를 선택합니다.

### 2. Context length

```text
512 / 1024 / 2048
```

필요 이상으로 긴 context는 KV cache를 차지합니다. 실제 대화 요구를 만족하는 가장 작은 값을
기본으로 선택합니다.

### 3. Concurrency와 batching

```text
max-num-seqs 1 / 2 / 4
```

단일 사용자 latency와 전체 throughput을 따로 판단합니다. GTX 1660에서는 concurrency 증가가
throughput보다 p95와 OOM을 악화시킬 수 있습니다.

### 4. Compile과 eager mode

```text
기본 compile mode
vs
--enforce-eager
```

Cold start, warm start와 반복 추론 속도를 모두 비교합니다. 짧게 켰다 끄는 개발 환경과 장시간
운영 환경의 최적값이 다를 수 있습니다. compile cache는 PVC에 보존합니다.

### 5. Prefix caching

동일한 system prompt와 긴 대화 prefix가 반복되는 workload에서만 비교합니다. 일회성 prompt로
효과를 주장하지 않습니다.

### 6. Engine 비교

```text
vLLM
SGLang
llama.cpp CUDA
```

모델 표현과 sampling 값을 최대한 동일하게 맞춥니다. llama.cpp GGUF와 FP16 engine 비교는
모델 표현이 다르므로 결과에 그 차이를 명시합니다.

### 7. 선택적 양자화

기본 비양자화 배포가 안정화된 뒤에만 진행합니다.

```text
Qwen3-1.7B FP16
vs
Qwen3-4B AWQ/GPTQ 4bit
```

속도와 VRAM뿐 아니라 고정된 질문 세트의 답변 품질도 비교합니다. 4bit가 작다고 항상 빠른 것은
아니며 GTX 1660에서 사용하는 quantization kernel의 실제 결과로 판단합니다.

## 피해야 할 최적화

- GPU에 들어가지 않는 모델을 상시 CPU offload하여 token마다 PCIe 전송 발생
- 모델, dtype와 context를 동시에 변경한 뒤 원인을 하나로 설명
- 한 요청만 실행하고 tokens/sec를 결론으로 사용
- warm-up과 compile 시간을 숨김
- 서로 다른 engine version 또는 mutable image tag 비교
- GTX 1660 결과를 L40S의 BF16/Tensor Core 결과와 단순 비율로 일반화
- OOM 직전 설정을 production 기본값으로 선택

## CI/CD 연결

PR CI는 benchmark 코드와 설정 계약만 검증합니다. 실제 GPU benchmark는 다음 두 실행기로
나눕니다.

```text
Windows GTX 1660
└── Argo CD PostSync smoke
    └── 수동 또는 예약 benchmark Job

RunPod L40S
└── gpu-runtime workflow_dispatch
    └── 동일 benchmark package와 artifact format
```

결과 artifact에는 다음 식별자를 반드시 포함합니다.

```json
{
  "git_sha": "...",
  "engine": "vllm",
  "engine_image_digest": "sha256:...",
  "model_id": "Qwen/Qwen3-1.7B",
  "model_revision": "...",
  "gpu": "GTX 1660",
  "dtype": "float16",
  "max_model_len": 1024,
  "max_num_seqs": 1,
  "thinking": false
}
```

배포 gate는 정답 품질을 완전히 판단하지 않습니다. API 성공률, 모델/revision 일치, TTFT와 E2E
p95의 급격한 회귀만 차단합니다. 품질 평가는 고정 질문 세트와 별도 평가 결과로 기록합니다.

## 결과 표 형식

| GPU | engine | model | dtype | context | concurrency | TTFT p50/p95 | tok/s | VRAM | power |
| --- | --- | --- | --- | ---: | ---: | --- | ---: | ---: | ---: |
| GTX 1660 | vLLM | Qwen3-1.7B | FP16 | 1024 | 1 | TBD | TBD | TBD | TBD |
| GTX 1660 | SGLang | Qwen3-1.7B | FP16 | 1024 | 1 | TBD | TBD | TBD | TBD |
| L40S | vLLM | Qwen3-1.7B | FP16 | 1024 | 1 | TBD | TBD | TBD | TBD |
| L40S | SGLang | Qwen3-1.7B | FP16 | 1024 | 1 | TBD | TBD | TBD | TBD |

## 아티클 구성

1. 왜 GTX 1660과 6GB VRAM을 선택했는가
2. Windows/WSL2/CUDA/vLLM 환경 구성
3. 측정 방법과 재현성 규칙
4. 최초 기준값과 병목 확인
5. memory, context, concurrency 실험
6. compile, cache와 engine 비교
7. 최종 GTX 1660 권장 설정
8. 동일 workload의 RunPod L40S 비교
9. 성능·비용·전력·운영 복잡도 결론
10. KServe와 Argo CD로 설정을 재현한 방법

글의 결론은 GTX 1660이 L40S를 대체한다는 주장이 아닙니다. 반복 개발과 단일 사용자 서비스는
보유 GPU로 비용 없이 수행하고, 큰 모델·긴 context·고동시성 검증만 시간 단위 L40S로 수행하는
혼합 전략의 기준을 제시하는 것이 목표입니다.

## 참고 자료

- [NVIDIA GeForce 16 series specifications](https://www.nvidia.com/en-eu/geforce/graphics-cards/compare/)
- [NVIDIA L40S specifications](https://www.nvidia.com/en-us/data-center/l40s/)
- [vLLM quantization hardware support](https://docs.vllm.ai/en/stable/features/quantization/index.html)
- [RunPod GPU models and prices](https://www.runpod.io/gpu-models)
