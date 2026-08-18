# 모델과 추론 옵션

이 문서는 이 저장소에서 선택할 수 있는 모델, 양자화 형식, 생성 옵션과 엔진 실행 옵션을 한곳에 정리한다.
Hugging Face의 모든 모델을 나열하는 목록이 아니라, 현재 엔진에서 보편적으로 사용하는 주요 계열과 선택 기준을 다룬다.

## 현재 저장소 설정

| 용도 | 엔진 | 모델 | 형식 | 현재 설정 | 설명 |
| --- | --- | --- | --- | --- | --- |
| CPU 계약 테스트 | Transformers | `Qwen/Qwen3-0.6B` | FP32 | thinking off | 실제 모델을 CPU에 올려 API 계약과 생성 여부를 확인한다. 성능 측정용은 아니다. |
| macOS 로컬 추론 | llama.cpp | `ggml-org/Qwen3-0.6B-GGUF` | `Q4_0` GGUF | `qwen3-0.6b` | 작은 메모리로 로컬 실행을 확인하는 smoke 모델이다. |
| Apple Silicon 로컬 추론 | MLX-LM | `mlx-community/Qwen3-0.6B-4bit` | 4-bit MLX | `default_model` | Apple Silicon의 통합 메모리와 Metal을 사용하는 로컬 모델이다. |
| GPU 엔진 비교 | vLLM / SGLang | `Qwen/Qwen3-4B` | BF16 | thinking off, context 8192 | L40S 한 대에서 같은 조건으로 두 엔진을 비교한다. |

모델과 revision의 기준값은 [`models/manifest.yaml`](../models/manifest.yaml)에 고정되어 있다. 현재 작업 트리의 로컬 MLX 실행기와 Gateway는 `enable_thinking: true`로 변경되어 있지만, manifest와 벤치마크 workload는 재현 가능한 비교를 위해 `false`를 유지한다.

## Qwen3 모델 크기 선택

아래 메모리는 4-bit 가중치만 단순 계산한 대략적인 값이다. 실제 실행에는 KV cache, 활성값, 런타임과 context 메모리가 추가된다.

| 모델 | 구조 | 4-bit 가중치 약값 | 적합한 용도 | 설명 |
| --- | --- | ---: | --- | --- |
| Qwen3-0.6B | Dense | 0.3 GB | CPU smoke, API 개발 | 가장 가볍지만 복잡한 추론과 한국어 품질은 낮다. |
| Qwen3-1.7B | Dense | 0.9 GB | 저사양 로컬 채팅 | 0.6B보다 낫지만 품질보다 실행 편의가 우선인 크기다. |
| Qwen3-4B | Dense | 2 GB | 일반 로컬 채팅, GPU 비교 | 로컬 실행 비용과 답변 품질의 균형이 좋다. |
| Qwen3-8B | Dense | 4 GB | 품질 중심 로컬 채팅 | 메모리와 지연이 늘지만 작은 모델보다 안정적이다. |
| Qwen3-14B | Dense | 7 GB | 고품질 단일 GPU 추론 | 충분한 통합 메모리나 GPU VRAM이 필요하다. |
| Qwen3-32B | Dense | 16 GB | 고품질 GPU 추론 | KV cache까지 고려하면 24 GB 이상 환경이 안전하다. |
| Qwen3-30B-A3B | MoE | 15 GB | 효율적인 대형 모델 실험 | 전체 가중치는 크지만 토큰마다 일부 expert만 활성화한다. |
| Qwen3-235B-A22B | MoE | 118 GB | 다중 GPU 서버 | 개인 PC보다 대규모 GPU 서빙 환경에 맞는다. |

이 저장소의 현실적인 변경안은 llama.cpp의 `Qwen3-4B` GGUF `Q4_K_M`, MLX-LM의 `Qwen3-4B-4bit`이다. 현재 0.6B는 실행 확인에는 빠르지만 산술·지시 수행 품질을 판단하기에는 너무 작다.

## 주요 모델 계열과 엔진 호환성

`가능`은 일반적인 지원 방향이며, 정확한 모델 버전·아키텍처는 각 엔진 릴리스의 지원 목록을 확인해야 한다.

| 모델 계열 | Transformers | llama.cpp | MLX-LM | vLLM | SGLang | 특징 |
| --- | --- | --- | --- | --- | --- | --- |
| Qwen / Qwen3 | 가능 | 가능 | 가능 | 가능 | 가능 | 다국어, 코딩, thinking 모드를 함께 실험하기 좋다. |
| Llama | 가능 | 가능 | 가능 | 가능 | 가능 | 생태계와 변환 모델이 가장 넓은 범용 계열이다. |
| Mistral / Mixtral | 가능 | 가능 | 가능 | 가능 | 가능 | Dense와 MoE 선택지가 있고 서빙 지원이 넓다. |
| Gemma | 가능 | 가능 | 가능 | 가능 | 버전 확인 | Google 계열의 비교적 작은 공개 가중치 모델이다. |
| Phi | 가능 | 가능 | 가능 | 가능 | 버전 확인 | 작은 크기와 로컬 실행에 초점을 둔 계열이다. |
| DeepSeek / R1 distill | 가능 | 가능 | 변환본 확인 | 가능 | 가능 | reasoning 모델과 distill 변형이 많다. |
| Yi | 가능 | 가능 | 변환본 확인 | 가능 | 버전 확인 | 다국어 공개 가중치 계열이다. |
| Command-R | 가능 | 가능 | 변환본 확인 | 가능 | 버전 확인 | RAG와 tool 사용에 초점을 둔 계열이다. |
| OLMo | 가능 | 가능 | 변환본 확인 | 가능 | 버전 확인 | 학습 데이터와 과정을 공개한 연구용 계열이다. |
| Granite | 가능 | 가능 | 변환본 확인 | 가능 | 버전 확인 | IBM의 기업·코드 용도 계열이다. |
| Falcon | 가능 | 가능 | 변환본 확인 | 가능 | 버전 확인 | 비교적 오래된 공개 가중치 계열이다. |
| StarCoder / CodeLlama | 가능 | 가능 | 변환본 확인 | 가능 | 버전 확인 | 코드 생성에 특화된 계열이다. |

MLX-LM은 Apple Silicon용으로 변환된 저장소가 필요하고, llama.cpp는 GGUF 파일이 필요하다. 이름이 같은 모델이라도 tokenizer, chat template, 라이선스와 지원 버전을 반드시 확인한다.

## 모델 파일과 양자화 형식

| 형식 | 주 사용 엔진 | 크기·품질 | 설명 |
| --- | --- | --- | --- |
| FP32 safetensors | Transformers | 가장 큼, 기준 정밀도 | CPU smoke에는 단순하지만 대형 모델 서빙에는 비효율적이다. |
| FP16 safetensors | Transformers, vLLM, SGLang | FP32의 약 절반 | 범용 GPU 추론에서 널리 쓰는 16-bit 형식이다. |
| BF16 safetensors | Transformers, vLLM, SGLang | FP16과 비슷 | 넓은 지수 범위로 최신 GPU에서 안정적인 기본 선택이다. |
| AWQ | vLLM, SGLang 등 | 보통 4-bit | GPU 추론용 weight-only 양자화로 메모리를 줄인다. |
| GPTQ | Transformers, vLLM 등 | 보통 4-bit | 사전 양자화된 GPU 모델에 널리 쓰이는 형식이다. |
| GGUF Q8 | llama.cpp | 큼, 품질 손실 작음 | 메모리가 충분하고 원본 품질에 가깝게 쓰고 싶을 때 선택한다. |
| GGUF Q6 / Q5 | llama.cpp | 중간 | Q8보다 작고 Q4보다 품질 보존이 좋은 절충안이다. |
| GGUF Q4_K_M | llama.cpp | 작음, 균형형 | 일반 로컬 채팅에서 우선 추천하는 4-bit K-quant이다. |
| GGUF Q4_0 | llama.cpp | 작음 | 단순하고 빠른 smoke 용도에 적합하지만 Q4_K_M보다 품질이 불리할 수 있다. |
| GGUF Q2 / Q3 | llama.cpp | 매우 작음, 손실 큼 | 메모리가 매우 부족할 때만 고려한다. |
| MLX 8 / 6-bit | MLX-LM | 큼, 품질 보존 우수 | Apple Silicon에서 품질을 더 보존하려는 선택이다. |
| MLX 4-bit | MLX-LM | 작음, 균형형 | Apple Silicon 로컬 실행의 일반적인 기본 선택이다. |
| MLX 2 / 3-bit | MLX-LM | 매우 작음, 손실 큼 | 메모리 절감이 품질보다 중요한 경우에만 사용한다. |
| MXFP4 / NVFP4 / MXFP8 | 지원 런타임 확인 | 하드웨어 의존 | 최신 저정밀 형식이며 모델과 하드웨어 지원 여부를 먼저 확인한다. |

## 공통 요청·생성 옵션

| 옵션 | 역할 | 값의 영향 | 현재 Gateway / UI |
| --- | --- | --- | --- |
| `model` | 사용할 모델 또는 엔진의 alias를 지정한다. | 실제 저장소 ID가 아니라 서버가 공개한 이름일 수 있다. | UI가 선택한 엔진의 공개 alias를 Gateway가 실제 alias로 바꾼다. |
| `messages` | 대화 기록을 role과 content 배열로 전달한다. | 이전 문맥이 길수록 메모리와 prefill 시간이 증가한다. | 지원하며 UI가 전체 대화를 보낸다. |
| `role: system` | 모델의 행동 원칙과 답변 형식을 지정한다. | 모델·template에 따라 지시 우선순위가 달라진다. | schema에서 지원한다. |
| `role: user` | 사용자의 현재 또는 이전 질문을 표시한다. | 실제 답변 대상이 되는 입력이다. | schema에서 지원한다. |
| `role: assistant` | 이전 모델 답변을 대화 문맥에 넣는다. | 다중 턴 일관성을 유지하지만 context를 소비한다. | schema에서 지원한다. |
| `chat_template_kwargs.enable_thinking` | Qwen3 같은 지원 모델의 reasoning 출력을 켜거나 끈다. | 켜면 품질이 좋아질 수 있지만 토큰·지연이 증가한다. | 현재 작업 트리의 Gateway는 강제로 `true`; UI 토글은 없다. |
| `stream` | 생성 토큰을 SSE 조각으로 즉시 보낸다. | 첫 화면 응답은 빨라지지만 총 생성 시간은 크게 줄지 않는다. | 지원하며 UI는 `true`를 보낸다. |
| `max_tokens` | 새로 생성할 최대 토큰 수를 제한한다. | 크면 긴 답변이 가능하지만 시간과 비용 상한이 커진다. | UI 256, Gateway 기본 256, 런타임 상한 기본 512이다. |
| `temperature` | 다음 토큰 확률 분포의 무작위성을 조절한다. | `0`은 재현성, 높은 값은 다양성이 커진다. | UI와 Gateway 기본 0.7이다. |
| `top_p` | 누적 확률 상위 후보만 남기는 nucleus sampling이다. | 낮을수록 안전하고 반복적인 답변이 되기 쉽다. | UI와 Gateway 기본 0.8이다. |
| `top_k` | 확률 상위 K개 토큰만 후보로 남긴다. | `0`은 보통 제한 없음을 뜻한다. | Gateway schema에는 없고 MLX 직접 호출에서 지원한다. |
| `min_p` | 최고 확률에 비해 너무 낮은 후보를 제거한다. | 낮은 품질의 꼬리 후보를 줄일 수 있다. | Gateway schema에는 없고 MLX 직접 호출에서 지원한다. |
| `seed` | 난수 생성의 시작값을 고정한다. | 같은 엔진·버전·설정에서 재현성을 높인다. | Gateway에서 지원한다. |
| `stop` | 지정 문자열이 생성되면 출력을 끝낸다. | 불필요한 꼬리 문장이나 구분자 이후 생성을 막는다. | Gateway schema에는 없고 엔진 직접 호출에서 사용한다. |
| `repetition_penalty` | 이미 나온 토큰의 재등장을 억제한다. | 반복 문장을 줄이지만 과하면 문장이 부자연스럽다. | Gateway schema에는 없고 MLX 직접 호출에서 지원한다. |
| `presence_penalty` | 한 번이라도 나온 토큰에 동일한 벌점을 준다. | 새 주제로 확장하도록 유도한다. | Gateway schema에는 없고 MLX 직접 호출에서 지원한다. |
| `frequency_penalty` | 나온 횟수에 비례해 토큰에 벌점을 준다. | 같은 표현의 잦은 반복을 줄인다. | Gateway schema에는 없고 MLX 직접 호출에서 지원한다. |
| `logit_bias` | 특정 토큰의 생성 확률을 직접 올리거나 내린다. | 금지어 또는 강제 후보를 세밀하게 제어한다. | Gateway schema에는 없고 MLX 직접 호출에서 지원한다. |
| `logprobs` | 생성 토큰의 로그 확률을 반환한다. | 평가와 디버깅에 유용하지만 응답 크기가 늘어난다. | Gateway schema에는 없고 MLX 직접 호출에서 지원한다. |
| `top_logprobs` | 각 위치의 상위 후보 토큰 확률도 반환한다. | 모델의 후보 선택을 분석할 때 사용한다. | Gateway schema에는 없고 MLX 직접 호출에서 지원한다. |
| `tools` | 모델이 호출할 수 있는 함수 schema를 전달한다. | tool calling을 지원하는 모델과 template이 필요하다. | 현재 Gateway schema에는 없다. |
| `adapters` | 요청에 적용할 LoRA adapter를 지정한다. | 한 base model에서 작업별 미세조정 결과를 선택할 수 있다. | 현재 Gateway schema에는 없고 MLX 직접 호출에서 지원한다. |

`temperature: 0`은 비교 실험에 적합하다. Transformers 구현은 이때 greedy decoding을 사용하며, 0보다 클 때만 `temperature`와 `top_p` sampling을 적용한다.

## MLX-LM 직접 호출 옵션

아래 옵션은 현재 설치된 MLX-LM 서버를 Gateway 없이 직접 호출할 때 사용할 수 있다. 엔진 버전에 따라 세부 지원은 바뀔 수 있다.

| 옵션 | 기본값 | 설명 |
| --- | ---: | --- |
| `stream` | `false` | `true`이면 SSE로 토큰 조각을 순차 전송한다. |
| `max_tokens` | `512` | 생성할 새 토큰 수의 상한이다. |
| `max_completion_tokens` | 없음 | `max_tokens`와 같은 목적의 OpenAI 호환 이름이다. |
| `temperature` | `0.0` | 무작위성을 조절하며 0이면 결정적 생성에 가깝다. |
| `top_p` | `1.0` | 누적 확률 기준으로 sampling 후보를 제한한다. |
| `top_k` | `0` | 상위 K개 후보만 유지하며 0이면 제한하지 않는다. |
| `min_p` | `0.0` | 최고 확률 대비 최소 후보 확률을 정한다. |
| `repetition_penalty` | 엔진 기본 | 반복 토큰을 억제하는 배율이다. |
| `repetition_context_size` | 엔진 기본 | 반복 벌점을 계산할 이전 토큰 범위다. |
| `presence_penalty` | 엔진 기본 | 이미 등장한 토큰에 고정 벌점을 준다. |
| `presence_context_size` | 엔진 기본 | presence penalty를 계산할 문맥 범위다. |
| `frequency_penalty` | 엔진 기본 | 등장 횟수에 비례해 벌점을 준다. |
| `frequency_context_size` | 엔진 기본 | frequency penalty를 계산할 문맥 범위다. |
| `xtc_probability` | 엔진 기본 | XTC sampling을 적용할 확률이다. |
| `xtc_threshold` | 엔진 기본 | XTC가 제거할 고확률 후보의 기준값이다. |
| `logit_bias` | 없음 | 토큰 ID별 logit을 직접 조정한다. |
| `logprobs` | `false` | 생성 토큰의 로그 확률 반환 여부다. |
| `top_logprobs` | 없음 | 각 토큰 위치에서 반환할 상위 후보 수다. |
| `seed` | 없음 | sampling 난수 seed를 고정한다. |
| `chat_template_kwargs` | `{}` | chat template에 thinking 같은 추가 인자를 전달한다. |
| `stop` | 없음 | 해당 문자열이 나오면 생성을 종료한다. |
| `draft_model` | 없음 | speculative decoding에 사용할 작은 초안 모델이다. |
| `num_draft_tokens` | `3` | 한 번에 초안 모델이 제안할 토큰 수다. |
| `adapters` | 없음 | 적용할 LoRA adapter 경로 또는 설정이다. |

### MLX에서 thinking 켜기

서버 시작 전체에 적용하려면:

```bash
mlx_lm.server \
  --model mlx-community/Qwen3-0.6B-4bit \
  --port 8004 \
  --chat-template-args '{"enable_thinking":true}'
```

직접 요청마다 선택하려면:

```bash
curl -N http://127.0.0.1:8004/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "default_model",
    "messages": [{"role": "user", "content": "12와 18의 최대공약수를 설명해줘"}],
    "max_tokens": 512,
    "temperature": 0,
    "stream": true,
    "chat_template_kwargs": {"enable_thinking": true}
  }'
```

요청의 `chat_template_kwargs`가 서버 시작 기본값보다 우선한다. 현재 웹 UI에는 on/off 토글이 없고 Gateway가 값을 정한다. thinking 과정을 UI에 별도로 표시하려면 streaming 응답의 `reasoning_content` 처리도 추가해야 한다.

## 엔진 실행 옵션

| 옵션 | 주 대상 | 설명 | 현재 저장소 |
| --- | --- | --- | --- |
| 모델 경로 / repo ID | 전체 | 불러올 가중치 위치를 지정한다. | manifest에서 revision과 함께 고정한다. |
| quantization | 전체 | 정밀도를 낮춰 메모리와 전송량을 줄이고 일부 품질을 교환한다. | llama.cpp Q4_0, MLX 4-bit, GPU BF16이다. |
| context length | 전체 | prompt와 생성 토큰을 합친 최대 문맥 길이다. | GPU 비교는 8192이다. |
| CPU threads | llama.cpp | CPU 연산에 사용할 thread 수다. 너무 높으면 경합이 생긴다. | 명시하지 않아 엔진 기본값을 쓴다. |
| GPU offload layers | llama.cpp | 일부 또는 전체 layer를 GPU로 보내 속도를 높인다. | 명시하지 않아 엔진 기본값을 쓴다. |
| batch size | 전체 | prefill 또는 decode에서 함께 처리할 토큰·요청 규모다. | 로컬 실행은 엔진 기본값을 쓴다. |
| concurrency | 전체 | 동시에 처리할 요청 수다. 높이면 처리량이 늘지만 개별 지연과 메모리도 늘 수 있다. | Transformers 기본 1, MLX 서버 decode 32 / prompt 8이다. |
| tensor parallel size | vLLM, SGLang | 모델 tensor를 여러 GPU로 나누는 수다. | L40S 단일 GPU 비교는 1이다. |
| GPU memory utilization | vLLM, SGLang | 엔진이 사용할 GPU 메모리 비율의 목표치다. | 두 엔진 모두 0.90이다. |
| prefix cache | vLLM, SGLang | 같은 prompt prefix의 KV 계산을 재사용한다. | vLLM 비교 설정에서 활성화한다. |
| KV cache dtype / size | GPU 엔진 | 이전 토큰의 attention 상태 저장 형식과 크기다. | 엔진 기본값을 사용한다. |
| speculative decoding | 지원 엔진 | 작은 draft 모델의 여러 토큰을 큰 모델이 검증해 decode를 가속한다. | 기본 비교에서는 끈다. |
| LoRA adapter | 지원 엔진 | base model을 복제하지 않고 미세조정 차이만 적용한다. | 현재 기본 서빙에는 연결하지 않았다. |
| API key | HTTP 서버 | 허가되지 않은 API 호출을 막는 공유 secret이다. | GPU 엔진과 Gateway에 환경변수로 주입한다. 로컬 MLX/llama 서버 자체 인증과는 별개다. |
| host / port | 전체 | 서버가 수신할 주소와 포트를 정한다. | llama.cpp 8003, MLX 8004, 공개 Gateway 8000을 사용한다. |

## 목적별 권장값

| 목적 | 모델 | thinking | temperature / top_p | max tokens | 설명 |
| --- | --- | --- | --- | ---: | --- |
| 빠른 실행 확인 | Qwen3-0.6B 4-bit | off | `0 / 1` | 16~128 | 품질보다 모델 로딩과 API 계약 성공을 확인한다. |
| 로컬 일반 채팅 | Qwen3-4B 4-bit | 필요할 때 on | `0.6~0.8 / 0.8~0.95` | 256~512 | 다양성과 응답 시간을 균형 있게 잡는다. |
| 산술·추론 질문 | Qwen3-4B 이상 | on | `0 / 1`부터 확인 | 512 이상 | reasoning 토큰이 답변 전에 사용되므로 상한을 넉넉히 둔다. |
| 엔진 성능 비교 | Qwen3-4B BF16 | off | `0 / 1` | workload별 동일값 | 모델 생성의 무작위성과 thinking 토큰을 제거해 엔진 차이를 비교한다. |
| 품질 회귀 평가 | 배포 대상과 동일 | 정책 고정 | seed와 sampling 고정 | 질문별 고정 | 이전 release와 같은 입력·조건으로 답변 품질을 비교한다. |

## 참고 자료

- [Qwen3 공식 모델 모음](https://huggingface.co/collections/Qwen/qwen3)
- [llama.cpp 공식 저장소와 지원 모델](https://github.com/ggml-org/llama.cpp)
- [MLX-LM 공식 저장소](https://github.com/ml-explore/mlx-lm)
- [MLX-LM OpenAI 호환 서버](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/SERVER.md)
- [vLLM 공식 Docker 배포 문서](https://docs.vllm.ai/en/stable/deployment/docker/)
- [SGLang serving benchmark 문서](https://docs.sglang.ai/developer_guide/bench_serving)
