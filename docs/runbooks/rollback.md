# Rollback Runbook

1. 현재 `/version`과 실패한 release ID를 기록합니다.
2. 이전 RunPod engine의 `/v1/models`가 정상인지 확인합니다.
3. Cloud Run Gateway를 이전 engine URL과 release ID로 새 revision 배포합니다.
4. `/readyz`, JSON, SSE smoke test를 실행합니다.
5. stable URL이 이전 release를 가리키는지 확인합니다.
6. 실패한 GPU Pod를 terminate합니다.
7. 시작부터 복구까지 걸린 시간을 기록합니다.

Fast rollback window가 끝났다면 이전 runtime digest로 새 GPU Pod를 먼저 만들어야 합니다. GPU capacity 대기 시간은 별도로 기록합니다.
