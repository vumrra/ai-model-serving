# 보안 경계

- 공개 사용자는 Cloud Run Gateway의 `PUBLIC_API_KEY`로 인증합니다.
- Gateway만 RunPod engine의 `ENGINE_API_KEY`를 사용합니다.
- vLLM과 SGLang은 `/v1` endpoint에서 bearer key를 검사합니다.
- request body, prompt, response는 application log와 benchmark 결과에 기록하지 않습니다.
- Cloud Run은 engine key를 Secret Manager에서 읽습니다.

RunPod Pod proxy는 인터넷에서 접근 가능한 주소입니다. vLLM 공식 보안 문서가 설명하듯
`--api-key`는 OpenAI 호환 endpoint를 보호하지만 서버의 모든 endpoint를 보호하는 방화벽은
아닙니다. 따라서 이 구성은 짧은 demo와 benchmark용입니다. 장기 운영에서는 private network,
인증 reverse proxy 또는 Kubernetes NetworkPolicy가 있는 KServe 단계로 옮깁니다.
