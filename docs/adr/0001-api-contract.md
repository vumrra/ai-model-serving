# ADR-0001: OpenAI-compatible chat API

## 결정

외부 API를 `/v1/chat/completions` 하나로 고정하고 `stream` 값으로 JSON과 SSE를 구분합니다.

## 이유

client와 inference engine 모두 널리 쓰는 계약을 사용하면 별도 전용 SDK 없이 engine을 교체할 수 있습니다.

## 결과

Gateway adapter가 engine 차이를 흡수하며, contract test가 compatibility를 보호합니다.
