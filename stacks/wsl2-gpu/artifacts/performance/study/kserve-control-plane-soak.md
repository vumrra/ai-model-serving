# KServe 제어면 15분 soak

측정 시각은 2026-08-28 13:32:04~13:47:22 KST(04:32:04~04:47:22 UTC)다. 최종 Qwen3-1.7B FP16 모델 부하가 실행되는 동안 20회, 45~54초 간격으로 라이브 클러스터를 읽기 전용 관찰했다. 리소스 수정·삭제와 Argo CD sync는 수행하지 않았다.

## 판정

| 영역 | 판정 | 근거 |
| --- | --- | --- |
| 모델 데이터면 | 통과 | predictor와 Gateway가 모든 표본에서 Ready였고 restart는 모두 0이었다. GPU는 시작·종료 모두 사용률 98%로 모델 부하를 처리했다. |
| Kubernetes 제어면 | 위험 미해결 | KServe manager와 storage-provisioner가 같은 시각에 두 번씩 재시작했다. 자동 회복했지만 15분 안정성 gate는 통과하지 못했다. |

이 판정은 15분 창에 한정된다. 데이터면 통과는 장기 가용성이나 제어면 안정성을 보증하지 않는다.

## 시작과 종료 상태

| 대상 컨테이너 | 13:32:04 Ready / restart | 13:47:22 Ready / restart | 변화 |
| --- | ---: | ---: | ---: |
| Qwen predictor `kserve-container` | True / 0 | True / 0 | 0 |
| FastAPI Gateway `gateway` | True / 0 | True / 0 | 0 |
| KServe controller `manager` | True / 2 | True / 4 | **+2** |
| KServe `kube-rbac-proxy` | True / 0 | True / 0 | 0 |
| Minikube `storage-provisioner` | True / 107 | True / 109 | **+2** |
| `kube-apiserver` | True / 6 | True / 6 | 0 |

- HPA는 시작과 종료 모두 0개였다. InferenceService의 `autoscalerClass: none` 계약이 유지됐다.
- 노드는 시작과 종료 모두 Ready=True, MemoryPressure=False, DiskPressure=False, PIDPressure=False였다.
- restart 수는 누적값이다. 이 창에서 새로 발생한 변화는 표의 `+2` 두 건뿐이다.

## 시각별 관측

| KST | 직접 관측 |
| --- | --- |
| 13:32:04 | 기준선: 모든 대상 Ready. manager 2회, storage-provisioner 107회, 나머지 대상은 위 표의 시작값. |
| 13:34:31 | etcd `slow fdatasync` 6.989초와 5초를 넘는 read transaction들이 기록됐다. |
| 13:36:07~15 | manager의 leader lease 갱신이 5초 timeout을 반복한 뒤 `leader election lost`로 exit 1. storage-provisioner도 1초 앞서 exit 255. |
| 13:36:56 | manager 2→3, storage-provisioner 107→108. manager Pod는 일시적으로 1/2 Ready. |
| 13:37:41 | manager Pod가 2/2 Ready로 자동 회복. predictor와 Gateway 변화 없음. |
| 13:39:20 | etcd `slow fdatasync` 7.517초 기록. |
| 13:39:23 | API handler timeout과 etcd DeadlineExceeded가 기록된 시각에 manager와 storage-provisioner가 함께 종료. |
| 13:40:06 | manager 3→4, storage-provisioner 108→109. manager Pod는 다시 일시적으로 1/2 Ready. |
| 13:40:52 | manager Pod가 2/2 Ready로 자동 회복. predictor와 Gateway restart는 계속 0. |
| 13:45:30 | manager leader lease PUT에서 API handler timeout이 다시 기록됐지만 종료 표본 전 추가 restart는 없었다. |
| 13:47:22 | 종료선: 모든 대상 Ready, HPA 0, 노드 pressure 조건 모두 False. |

두 재시작은 manager와 storage-provisioner가 1초 이내에 함께 종료됐고 kube-apiserver 자체 restart 수는 변하지 않았다. 이는 개별 controller 프로세스 OOM보다 공통 API/etcd 지연과 더 잘 맞는다.

## etcd와 API stall 근거

기존 보고서가 보존한 이전 관측의 `fdatasync` 최대값은 3.891초였다. 이번 재확인에서는 그보다 큰 값이 나왔으므로 3.891초를 현재 최대값으로 해석하면 안 된다.

- 이번 15분 창 안 최대 `slow fdatasync`: 7.517초(13:39:20 KST)
- 현재 etcd 24시간 로그 재확인 최대: 7.826초(11:59:44 KST, 측정 창 밖)
- 같은 장애 구간의 etcd read transaction은 5초를 넘겼고 API server는 handler timeout 및 etcd `DeadlineExceeded`를 기록했다.
- manager 직전 로그는 5초짜리 leader lease 요청 timeout, lease 갱신 실패, `leader election lost` 순서를 보였다.

관측된 시간 순서는 `fdatasync 지연 → etcd transaction 지연 → API timeout → leader lease 상실 → controller 재시작`이다. WSL 가상 디스크 지연이 시작점이라는 설명이 가장 일관되지만, 이 soak는 통제 실험이 아니므로 단일 원인으로 확정하지 않는다.

## GPU와 WSL 자원

| 지표 | 시작 | 종료 | 변화 |
| --- | ---: | ---: | ---: |
| GPU VRAM used | 5,415 MiB | 5,418 MiB | +3 MiB |
| GPU VRAM free | 552 MiB | 549 MiB | -3 MiB |
| GPU utilization | 98% | 98% | 0%p |
| GPU temperature | 53°C | 71°C | +18°C |
| GPU power | 50.22 W | 53.78 W | +3.56 W |
| WSL RAM used | 4,604.9 MiB | 4,651.3 MiB | +46.3 MiB |
| WSL RAM available | 5,338.7 MiB | 5,292.4 MiB | -46.3 MiB |
| WSL swap used | 214.2 MiB | 216.2 MiB | +2.0 MiB |

GPU VRAM과 WSL RAM/swap은 작은 범위에서 유지됐고 predictor는 재시작하지 않았다. 동시에 MemoryPressure와 DiskPressure가 False였다는 사실은 kubelet eviction 압력이 없었다는 뜻이지, 짧은 디스크 latency spike가 없었다는 뜻은 아니다.

## 관측과 해석의 경계

### 관측

- predictor와 Gateway: 전 표본 Ready, restart 0.
- manager와 storage-provisioner: 두 번 동시 재시작, 이후 자동 회복.
- manager resource: CPU request 100m, limit 500m. HPA: 0개.
- OOMKilled, MemoryPressure, DiskPressure는 관측되지 않았다.

### 해석/추론

- **모델 데이터면은 이 창에서 통과**했다. 모델 Pod, Gateway, GPU 메모리 상태에 누수나 crash 징후가 없다.
- **제어면 위험은 미해결**이다. 자동 회복은 안정성 통과가 아니며 GitOps reconcile과 향후 rollout을 지연시킬 수 있다.
- manager CPU limit 500m과 HPA 비활성은 controller/HPA 부하를 제한하는 완화책이다. etcd persistence와 API stall의 근본 해결은 아니다.
- 다음 검증은 모델 부하를 고정한 채 Minikube 데이터 디스크 latency와 etcd WAL latency를 함께 수집하는 통제 실험이어야 한다.

## 재현 가능한 읽기 전용 확인 명령

다음 명령은 WSL Ubuntu에서 실행하며 클러스터 상태를 바꾸지 않는다.

```bash
kubectl get pods -A \
  -o custom-columns='NS:.metadata.namespace,NAME:.metadata.name,READY:.status.containerStatuses[*].ready,RESTARTS:.status.containerStatuses[*].restartCount,PHASE:.status.phase'

kubectl -n qwen-serving get hpa
kubectl get node qwen-wsl2-gpu -o jsonpath='{.status.conditions}'

kubectl -n kserve logs deployment/kserve-controller-manager \
  -c manager --previous --tail=120
kubectl -n kube-system logs etcd-qwen-wsl2-gpu --since=30m \
  | grep -E 'slow fdatasync|apply request took too long|ReadIndex response took too long'
kubectl -n kube-system logs kube-apiserver-qwen-wsl2-gpu --since=30m \
  | grep -E 'Handler timeout|DeadlineExceeded|leader-lock'

nvidia-smi \
  --query-gpu=timestamp,name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu,power.draw \
  --format=csv,noheader,nounits
free --bytes
swapon --show --bytes
```

## Appendix: 최종 benchmark 전체 soak

15분 공식 창의 수치는 위에 그대로 보존한다. 이 appendix는 같은 시작점부터 360-request benchmark 종료 직후까지 확장한 2026-08-28 13:32:04~14:05:00 KST, 총 32분 56초 구간이다. benchmark 결과는 360 requests, failed 0이었다.

### 전체 구간 restart와 종료 상태

| 대상 컨테이너 | 13:32:04 Ready / restart | 14:05:00 Ready / restart | 전체 변화 |
| --- | ---: | ---: | ---: |
| Qwen predictor `kserve-container` | True / 0 | True / 0 | 0 |
| FastAPI Gateway `gateway` | True / 0 | True / 0 | 0 |
| KServe controller `manager` | True / 2 | True / 6 | **+4** |
| KServe `kube-rbac-proxy` | True / 0 | True / 0 | 0 |
| Minikube `storage-provisioner` | True / 107 | True / 110 | **+3** |
| `kube-apiserver` | True / 6 | True / 6 | 0 |

- 15분 창 뒤 13:50:15경 manager가 다시 leader election을 잃어 restart 5가 됐고 storage-provisioner는 이때 변하지 않았다.
- 13:52:10 storage-provisioner가 exit 255, 13:52:13 manager가 exit 1로 종료해 restart가 각각 110과 6이 됐다.
- 13:53:06에는 둘 다 Ready로 회복했고 14:05:00 종료 표본까지 추가 restart는 없었다.
- 종료 시 모든 대상은 Ready, HPA는 0개, 노드는 Ready=True이며 MemoryPressure=False, DiskPressure=False, PIDPressure=False였다.

360개 모델 요청은 모두 성공했지만 제어면에서는 manager 4회와 storage-provisioner 3회의 신규 재시작이 있었다. 따라서 **모델 데이터면 통과 / 제어면 위험 미해결** 판정은 전체 구간에서도 바뀌지 않는다.

### 전체 구간 자원 시작/종료

| 지표 | 13:32:04 | 14:05:00 | 변화 |
| --- | ---: | ---: | ---: |
| GPU VRAM used | 5,415 MiB | 5,412 MiB | -3 MiB |
| GPU VRAM free | 552 MiB | 555 MiB | +3 MiB |
| GPU utilization | 98% | 27% | -71%p |
| GPU temperature | 53°C | 52°C | -1°C |
| GPU power | 50.22 W | 7.99 W | -42.23 W |
| WSL RAM used | 4,604.9 MiB | 4,510.5 MiB | -94.4 MiB |
| WSL RAM available | 5,338.7 MiB | 5,433.1 MiB | +94.4 MiB |
| WSL swap used | 214.2 MiB | 232.8 MiB | +18.6 MiB |

종료 스냅샷은 benchmark 완료 직후라 GPU utilization과 power가 내려갔다. VRAM은 약 5.4GiB로 유지돼 모델은 계속 적재된 상태였고 predictor restart는 0이었다.

### etcd 저장 경로 확인

직접 확인한 etcd data directory는 `/var/lib/minikube/etcd`이고, Minikube node의 `/var`와 Docker data path는 `/dev/sdd`에 있다. 측정 당시 etcd directory는 약 256MiB, WAL은 약 245MiB, snapshot DB는 약 12MiB였다.

- **관측:** DB 크기는 작고 node DiskPressure는 False였다. 단순 디스크 용량 고갈이나 대형 DB만으로 이번 stall을 설명하기 어렵다.
- **해석/추론:** 작은 DB에서도 WAL `fdatasync`가 7초 이상 지연됐으므로 용량보다 `/dev/sdd`까지의 storage latency/path 가설을 지지한다. 다만 경로와 시간 상관은 단독 원인 증명이 아니며 디스크 latency를 동시 계측하는 통제 실험이 필요하다.

## 후속 관찰 · 누적 재시작 11

Soak 종료 시 manager container 누적 restart는 6이었다. 이후 동일 Pod의 manager container가 **11**로 증가한 것을 확인했다. 같은 Pod의 kube-rbac-proxy container restart는 0이므로, container 이름을 구분하지 않고 Pod의 첫 상태만 보면 0으로 잘못 읽을 수 있다. 같은 시점에 Minikube storage-provisioner는 114, qwen predictor와 Gateway는 Ready이며 restart 0이었다.

이 후속 관찰은 data plane 성능 결론을 바꾸지 않지만, control-plane 문제가 자동 회복만 했을 뿐 해결되지 않았다는 판단을 강화한다. 동일 Pod manager container의 장기 안정성은 별도 관찰 gate가 필요하다.

### 후속 로그 진단 · 직접 원인과 미확정 원인

- **직접 확인된 manager 종료 경로:** KServe manager의 leader lease renew 요청이 timeout되고, 이어 leader election lost가 기록된 뒤 exit 1로 종료됐다. 같은 요청 구간에 kube-apiserver는 etcd DeadlineExceeded와 handler timeout을 기록했다.
- **동시에 확인된 저장 지연 상관:** 해당 구간의 etcd slow fdatasync는 2.4~3.4초였고, lifetime WAL fsync 평균은 206ms, 1.024초 초과 5.91%, 2.048초 초과 1.41%, 8.192초 초과 6회였다. 기존 24시간 로그 최대 7.826초 관측도 함께 보존한다.
- **구성 요소 이름 교정:** 약 12초 뒤 재시작한 대상은 storage-initializer가 아니라 Minikube storage-provisioner다.
- **약화된 가설:** etcd data directory 256MiB, disk 사용률 약 7%, node pressure false이며 OOMKilled나 CPU limit 초과 근거는 보이지 않았다. 따라서 단순 용량 고갈, OOM, CPU limit만으로 설명할 근거는 없다.
- **미확정:** 최종 backing storage latency가 WSL VHDX, Docker 경로, host I/O 중 어디에서 시작됐는지는 이 관찰만으로 구분하지 못했다. 원인 확정 전에는 별도 storage latency A/B와 WAL fsync 계측이 필요하다.
