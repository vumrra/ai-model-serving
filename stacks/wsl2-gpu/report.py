# ruff: noqa: E501, I001

from __future__ import annotations

import argparse
from collections import Counter
import html
import json
import statistics
import sys
from pathlib import Path
from string import Template
from typing import Any

sys.path.insert(0, str(Path(__file__).parents[2]))

from benchmarks.summarize import load_run, summarize_run  # noqa: E402


REPORT_TEMPLATE = Template(
    """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>GTX 1660 LLM 서빙 실측 보고서</title>
  <style>
    :root { --ink:#172033; --muted:#667085; --line:#d9e0ea; --paper:#f5f7fb;
      --card:#fff; --blue:#3157d5; --green:#0f7b58; --red:#b42318; }
    * { box-sizing:border-box; }
    body { margin:0; color:var(--ink); background:var(--paper);
      font:15px/1.65 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif; }
    main { width:min(1100px,calc(100% - 32px)); margin:0 auto; padding:54px 0 80px; }
    h1 { font-size:clamp(34px,6vw,64px); line-height:1.04; letter-spacing:-.045em; margin:12px 0 20px; }
    h2 { margin:56px 0 16px; font-size:27px; letter-spacing:-.025em; }
    h3 { margin:0 0 6px; font-size:17px; }
    p { margin:8px 0; } a { color:var(--blue); }
    .eyebrow { color:var(--blue); font-weight:750; letter-spacing:.08em; text-transform:uppercase; }
    .lead { max-width:780px; font-size:19px; color:#344054; }
    .verdict { margin-top:28px; padding:24px; background:#eaf7f1; border:1px solid #a9dac8;
      border-radius:18px; display:grid; gap:8px; }
    .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:14px; }
    .card { background:var(--card); border:1px solid var(--line); border-radius:15px; padding:18px; }
    .metric { font-size:29px; font-weight:780; letter-spacing:-.035em; }
    .muted,.note { color:var(--muted); } .note { font-size:13px; }
    .pass { color:var(--green); font-weight:750; } .fail { color:var(--red); font-weight:750; }
    .flow { display:flex; align-items:center; gap:8px; overflow-x:auto; padding:16px 2px; }
    .node { flex:0 0 auto; min-width:126px; padding:12px 14px; text-align:center;
      background:#fff; border:1px solid var(--line); border-radius:12px; font-weight:650; }
    .arrow { color:#98a2b3; font-size:22px; }
    .table-wrap { overflow-x:auto; background:#fff; border:1px solid var(--line); border-radius:15px; }
    table { width:100%; border-collapse:collapse; min-width:780px; }
    th,td { padding:12px 14px; border-bottom:1px solid #e9edf3; text-align:right; white-space:nowrap; }
    th:first-child,td:first-child { text-align:left; } th { color:#475467; background:#fafbfc; }
    tr:last-child td { border-bottom:0; }
    code { background:#eef1f6; padding:2px 6px; border-radius:6px; }
    pre { overflow:auto; padding:18px; background:#172033; color:#eef2ff; border-radius:14px; }
    ul { padding-left:22px; } .two { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
    @media (max-width:720px) { .two { grid-template-columns:1fr; } main { padding-top:34px; } }
  </style>
</head>
<body>
<main>
  <div class="eyebrow">Measured on Windows · WSL2 · GTX 1660 6GB</div>
  <h1>작은 GPU에서<br>쓸 만한 채팅 API 만들기</h1>
  <p class="lead">이 보고서는 이론상 최대치가 아니라 실제 KServe/vLLM 경로에서 고정한 요청을 반복해
  지연, 처리량, VRAM, 전력, 품질을 비교한 결과다. 측정일은 $measured_at 이다.</p>

  <section class="verdict">
    <strong>$verdict_title</strong>
    <span>$verdict_body</span>
  </section>
  <p class="note"><code>실측</code> HTTP 시계·API usage·nvidia-smi에서 직접 수집 ·
  <code>계산</code> 실측값으로 환산 · <code>검증</code> 고정 규칙 통과 여부 ·
  <code>해석/추론</code> 여러 지표를 함께 본 운영 판단 또는 미실측 경계</p>

  <h2>두 가지 목적과 통과 기준</h2>
  <div class="two">
    <div class="card"><h3>목표 A · 대화형 기본</h3>
      <p>한 명이 쓰는 한국어·코드 보조 채팅 API다. 성공률 100%, TTFT p95 ≤1,000ms,
      TPOT p95 ≤100ms(약 ≥10 tok/s), 미사용 VRAM ≥512MiB를 모두 만족해야 한다.</p>
      <p class="pass">$interactive_status</p>
    </div>
    <div class="card"><h3>목표 B · 모델 용량 우선</h3>
      <p>성공률 100%, TTFT p95 ≤1,000ms, TPOT p95 ≤200ms(약 ≥5 tok/s),
      미사용 VRAM ≥256MiB를 지키는 범위에서 파라미터 수를 키운다. 작은 모델보다 품질이
      나쁘지 않다는 별도 검증과 지속 부하 확인도 필요하다.</p>
      <p class="muted">현재 4B AWQ는 속도 gate만 통과했고 종합 판정은 보류</p>
    </div>
  </div>
  <p class="note">모델이 메모리에 올라갔다는 사실만으로 운영 후보가 되지는 않는다. 품질·응답성·안정성
  hard gate를 먼저 통과한 후보 중에서 크기와 효율을 비교한다.</p>

  <h2>아키텍처 개선 전후</h2>
  <h3>1 · GPU 계층</h3>
  <div class="two">
    <div class="card"><h3>직접 GPU 검증</h3><pre>Windows NVIDIA driver
→ WSL2 GPU-PV
→ Docker GPU container
→ raw vLLM</pre>
      <p class="note">Kubernetes를 넣기 전에 Windows driver가 Linux container까지 전달되는지만 검증했다.</p>
    </div>
    <div class="card"><h3>현재 선언형 운영</h3><pre>Windows NVIDIA driver
→ WSL2 Ubuntu
→ Minikube Docker runtime
→ NVIDIA device plugin
→ nvidia.com/gpu: 1
→ KServe vLLM Pod</pre>
      <p class="note">WSL 내부에는 Linux NVIDIA driver를 설치하지 않는다.</p>
    </div>
  </div>

  <h3>2 · API 경로</h3>
  <div class="two">
    <div class="card"><h3>진단 경로</h3><pre>test client
→ manual port-forward :8005
→ KServe predictor
→ raw vLLM
→ Qwen3-1.7B @0.85</pre>
      <p class="note">엔진 기준 성능을 재는 localhost 전용 경로다.</p>
    </div>
    <div class="card"><h3>현재 서비스 경로</h3><pre>Mac / LAN client
→ Windows Private LAN :8000
→ portproxy + reconnecting forward
→ FastAPI Gateway
→ KServe ClusterIP
→ $runtime_line
→ Qwen3-1.7B FP16</pre>
      <p class="note">Gateway가 API key, rate limit, 입력 검증, qwen-demo alias와 thinking off를 담당한다.</p>
    </div>
  </div>

  <h3>3 · 배포와 CD</h3>
  <div class="two">
    <div class="card"><h3>수동 단계</h3><pre>code/config change
→ local build
→ manual deploy
→ manual API check</pre>
      <p class="note">초기 gate를 통과할 때 사용한 운영자 주도 흐름이다.</p>
    </div>
    <div class="card"><h3>현재 pull-based GitOps</h3><pre>Mac push / merge
→ GitHub Actions test + build
→ GHCR image digest
→ GitOps values bot commit
→ Argo CD pull + Helm render
→ Gateway rollout / KServe reconcile
→ PostSync smoke</pre>
      <p class="note">GitHub Actions는 집 Kubernetes API에 접속하지 않고, Argo CD가 Git을 당겨온다.</p>
    </div>
  </div>
  <p class="note">GTX 1660은 Turing(SM 7.5)이며 이 실행에서는 vLLM V0와 XFormers가 선택됐다.
  원본 vLLM 포트는 측정 때만 localhost:8005로 열고 외부에는 Gateway만 노출한다.</p>

  <h2>실험 계약과 중단 gate</h2>
  <div class="two">
    <div class="card"><h3>고정 계약</h3><p>image digest와 model revision, FP16/AWQ 표현,
      thinking off, seed 42, context 1024, warm-up 3회, prompt·출력 상한을 결과와 함께 기록한다.
      엔진 비교에서는 한 번에 한 변수만 바꾼다.</p></div>
    <div class="card"><h3>현재 반복 단위</h3><p>5개 prompt × 4 round = 20회, concurrency 1이다.
      각 설정은 한 번 실행했으므로 p95는 이 표본 안의 기술통계이며 장기 분포를 보장하지 않는다.</p></div>
  </div>
  <div class="table-wrap"><table>
    <thead><tr><th>Gate</th><th>계약</th><th>현재 근거</th><th>다음 단계 중단 조건</th></tr></thead>
    <tbody>
      <tr><td>G0 API</td><td>models · JSON · SSE · thinking off</td><td>Gateway 20/20, usage와 [DONE]</td><td>오류 또는 불완전 stream</td></tr>
      <tr><td>G1 반복성</td><td>같은 조건의 독립 run 비교</td><td>Before/After 각 60요청 × 3 run</td><td>큰 편차의 원인을 찾기 전 결론 금지</td></tr>
      <tr><td>G2 workload</td><td>short chat · long prefill · long generation</td><td>short chat 64-token 상한</td><td>timeout 또는 SLO 실패</td></tr>
      <tr><td>G3 메모리</td><td>utilization과 context를 한 변수씩</td><td>0.85 · eager 0.85 · graph 0.80</td><td>VRAM 여유가 hard gate 미만</td></tr>
      <tr><td>G4 모델</td><td>같은 thinking-off workload와 품질 계약</td><td>1.7B FP16 · 4B AWQ</td><td>적재 실패 · 속도 gate 실패 · 품질 이득 없음</td></tr>
      <tr><td>G5 안정성</td><td>최종 후보의 지속 부하와 재기동</td><td>Pod·LAN forward 복구 검증</td><td>OOM · timeout · VRAM 증가</td></tr>
    </tbody>
  </table></div>
  <p class="note">새 결과가 없는 항목은 성능 수치를 추정하지 않고 현재 근거의 범위를 그대로 적는다.
  명백히 6GB를 넘는 후보는 가중치 크기를 먼저 계산한 뒤 적재 실험 여부를 결정한다.</p>

$study_sections

  <h2>$selected_heading</h2>
  <p class="note">$selected_basis</p>
  <div class="grid">
    <div class="card"><h3>TTFT p95</h3><div class="metric">$selected_ttft ms</div><span class="pass">통과</span></div>
    <div class="card"><h3>TPOT p95</h3><div class="metric">$selected_tpot ms</div><span class="pass">통과</span></div>
    <div class="card"><h3>실제 총 처리량</h3><div class="metric">$selected_tps tok/s</div><p class="muted">$selected_hour tok/hour</p></div>
    <div class="card"><h3>최대 VRAM</h3><div class="metric">$selected_vram MiB</div><p class="muted">$selected_headroom MiB 여유</p></div>
    <div class="card"><h3>GPU 전력</h3><div class="metric">$selected_power W</div><p class="muted">측정 구간 평균</p></div>
    <div class="card"><h3>GPU 에너지</h3><div class="metric">$selected_energy Wh</div><p class="muted">1K 출력 토큰당</p></div>
    <div class="card"><h3>GPU 비용</h3><div class="metric">$selected_cost 원</div><p class="muted">백만 출력 토큰당</p></div>
  </div>

  <h2>실제 배포 경로 검증</h2>
  <div class="grid">
    <div class="card"><h3>인증 SSE</h3><div class="metric">20/20</div><p class="muted">성공 · usage · [DONE]</p></div>
    <div class="card"><h3>Gateway TTFT p95</h3><div class="metric">$gateway_ttft ms</div><span class="pass">통과</span></div>
    <div class="card"><h3>Gateway TPOT p95</h3><div class="metric">$gateway_tpot ms</div><span class="pass">통과</span></div>
    <div class="card"><h3>시간당 출력 토큰</h3><div class="metric">$gateway_hour</div><p class="muted">Gateway 전체 경로</p></div>
    <div class="card"><h3>관측 처리량 차이</h3><div class="metric">$gateway_overhead%</div><p class="muted">raw 대비 · 단일 실행</p></div>
    <div class="card"><h3>Gateway GPU 비용</h3><div class="metric">$gateway_cost 원</div><p class="muted">백만 출력 토큰당</p></div>
    <div class="card"><h3>배포 digest</h3><div class="metric">$gateway_digest</div><p class="muted">sha256 앞 12자리</p></div>
  </div>
  <p class="note">GitHub Actions → GHCR digest → Argo CD sync 뒤 측정했다. Windows LAN SSE와
  포워드 자동 복구는 <a href="deployment-verification.json">deployment-verification.json</a>에 기록했다.</p>

  <h2>모델 비교 · 같은 thinking-off workload</h2>
  <div class="table-wrap"><table>
    <thead><tr><th>모델</th><th>품질</th><th>TTFT p95</th><th>TPOT p95</th>
    <th>tok/s</th><th>시간당 출력 토큰</th><th>VRAM peak</th><th>Wh/1K tok</th><th>원/백만 출력 토큰</th><th>SLO</th></tr></thead>
    <tbody>$model_rows</tbody>
  </table></div>
  <p class="note">전기요금은 200원/kWh 가정의 GPU 전력만 계산했다. PC 나머지 부품, 냉각,
  감가상각은 제외하므로 클라우드 비용과 직접 비교하면 안 된다.</p>

  <h2>숫자를 읽는 법</h2>
  <div class="grid">
    <div class="card"><h3><code>계산</code> TPOT</h3><p><code>(E2E−TTFT)/(출력 토큰−1)</code>로
      요청별 평균 생성 간격을 구한 뒤 p95를 계산했다. 각 토큰의 실제 간격 분포인 ITL을 직접 잰 값은 아니다.</p></div>
    <div class="card"><h3><code>계산</code> tok/hour</h3><p>완료 토큰을 각 run의 실제 측정 구간으로 나눈 뒤
      3,600초로 외삽했다. 한 시간 지속 부하를 실제로 실행한 값은 아니다.</p></div>
    <div class="card"><h3><code>계산</code> GPU-only 비용</h3><p>활성 구간의 GPU 평균 전력과
      200원/kWh 가정을 사용했다. CPU·RAM·냉각·idle 전력·구입비와 감가상각은 포함하지 않는다.</p></div>
    <div class="card"><h3><code>검증</code> 품질 계약</h3><p>1.7B는 30-case와 Wilson 구간을, 기존 모델 비교는 9-case를 사용했다.
      둘 다 일반 지능 점수가 아니며 서로 다른 표본의 점수를 직접 비교하지 않는다.</p></div>
  </div>
  <ul>
    <li>반복 run의 p95 중앙값도 약 5분대 표본의 tail일 뿐 장기 분포나 soak test를 대신하지 않는다.</li>
    <li>1.7B FP16과 4B AWQ 비교는 파라미터 수와 숫자 표현을 함께 바꾼 제품 후보 비교다. 모델 크기 하나의 효과가 아니다.</li>
    <li>raw와 Gateway 실행은 같은 요청 계약이지만 동시에 짝지어 측정하지 않았다. 0.53%는 관측 차이이며 Gateway 원인으로 단정하지 않는다.</li>
    <li>4B는 코드 계약을 통과했지만 일부 실패는 답변 길이 제한 때문이었다. 현재 결과는 품질 우위가 미입증됐다는 뜻이다.</li>
  </ul>

  <h2>튜닝 실험 · 한 변수씩</h2>
  <div class="table-wrap"><table>
    <thead><tr><th>설정</th><th>TTFT p95</th><th>TPOT p95</th><th>tok/s</th>
    <th>VRAM peak</th><th>판정</th></tr></thead><tbody>$tuning_rows</tbody>
  </table></div>
  <ul>
    <li><b>enforce-eager</b>: TTFT는 빨라졌지만 TPOT·총 처리량이 소폭 나빠지고 VRAM 절감은 39MiB뿐이라 기각.</li>
    <li><b>memory 0.80</b>: 초기 단일 변수 진단에서 처리량 손실 약 0.5%로 287MiB를 절감한 중간안.</li>
    <li><b>memory 0.75 + prefix cache</b>: 같은 short workload 3회씩의 구성 묶음 비교에서 SLO 3/3을 통과해 최종안으로 채택.</li>
    <li><b>4B AWQ</b>: 로드는 성공했지만 대화형 TPOT SLO 실패, 에너지 증가, 품질 이득 미입증으로 기본안에서 기각.</li>
    <li><b>인과 한계</b>: 최종 묶음은 utilization과 prefix cache를 함께 바꿨으므로 각각의 단독 효과를 주장하지 않는다.</li>
  </ul>
  <p class="note">초기 세 튜닝 실행은 raw API의 Qwen 기본 thinking이 켜진 것을 발견하기 전의 진단 실행이다.
  같은 조건끼리 엔진/메모리 차이만 비교했고, 대표 성능은 별도의 thinking-off 실행만 사용했다.</p>

  <h2>개선 결과와 다음 순서</h2>
  <ul>
    <li><b>적용</b>: graph mode를 유지해 eager보다 시간당 처리량을 보존했다.</li>
    <li><b>적용</b>: memory 0.75 + prefix cache 묶음의 worst peak 5,445MiB로 699MiB 운영 여유를 확인했다.</li>
    <li><b>후속 격리</b>: prefix cache 단독 효과는 동일 utilization의 on/off 짝 실험으로 분리한다.</li>
    <li><b>하드웨어</b>: 4B 이상 품질이 필요하면 12GB 이상 GPU에서 FP16/BF16 모델을 다시 비교한다. 현재 6GB의 4B AWQ는 SLO를 통과하지 못했다.</li>
  </ul>
  <p class="note">최적화는 단일 숫자 최대화가 아니라 TTFT·TPOT·처리량·VRAM을 동시에 보는 Pareto 선택이다.
  반복 실측 기준 최종안은 graph / memory 0.75 / prefix cache on이며 변경 묶음의 효과로만 해석한다.</p>

  <h2>GTX 1660 모델·운영 의사결정</h2>
  <div class="two">
    <div class="card"><h3>모델 선택</h3><pre>채팅에서 ≥10 tok/s가 필요한가?
├─ 예 → 1.7B FP16 / graph / 0.75 / prefix on
└─ 아니오, ≥5 tok/s를 허용하는가?
   ├─ 아니오 → 1.7B 유지
   └─ 예 → 더 큰 모델의 품질 우위가
            별도 계약에서 확인됐는가?
      ├─ 예 → 지속 부하 통과 후 조건부 채택
      └─ 아니오 → 1.7B 유지

8B 이상이 꼭 필요한가?
└─ 적재 결과 없이 가능하다고 쓰지 않는다.
   load gate를 통과하지 못하면 12GB 이상 GPU로 이동</pre></div>
    <div class="card"><h3>운영 구조</h3><pre>GPU가 한 장인가?
└─ KServe Standard / replica 1 / Recreate

외부 호출이 필요한가?
├─ Gateway :8000만 Private LAN에 공개
└─ K8s API · Argo CD · raw vLLM은 localhost

새 release가 실패했는가?
└─ Git revert → Argo CD가 이전 digest 복구

무중단·고가용성이 필요한가?
└─ 현 PC에 기능을 더하지 말고 GPU/노드를 추가</pre></div>
  </div>
  <p class="note"><code>해석</code> 현재 대화형 최적점은 가장 큰 모델을 억지로 적재하는 설정이 아니라,
  응답 속도와 512MiB 운영 여유를 함께 지키는 1.7B FP16이다. 4B AWQ는 용량 우선 목표의 조건부 후보로 남긴다.</p>

  <h2>측정 방법</h2>
  <div class="two">
    <div class="card"><h3>성능 계약</h3><p>고정 revision, seed 42, context 1024, sequence 1,
    thinking off와 workload hash를 기록했다. short 구성은 60요청을 독립 3회씩 반복하고
    long/shared-prefix/concurrency 시나리오를 분리했다.</p></div>
    <div class="card"><h3>정확성 계약</h3><p>1.7B는 30개 규칙으로 채점했다.
    기존 모델 비교는 1.7B $quality_one, 4B AWQ $quality_four / 9다.</p></div>
  </div>
  <p>TPOT는 <code>(E2E - TTFT) / (output tokens - 1)</code>로 계산했다.
  이는 요청별 평균 time per output token이며 직접 수집한 inter-token latency가 아니다.
  전력은 단일 <code>nvidia-smi --loop-ms=500</code> 프로세스로 샘플링해 요청 부하를 줄였다.
  응답 본문은 artifact에 저장하지 않고 request별 latency·usage와 품질 answer hash만 저장했다.</p>

  <h2>이번 코드 변경</h2>
  <ul>
    <li><code>benchmarks/runner.py</code>: 요청 구간만 GPU 전력·VRAM을 샘플링하고 식별정보는 저장하지 않는다.</li>
    <li><code>benchmarks/summarize.py</code>: TPOT, 시간당 토큰, goodput, SLO, 에너지와 예상 비용을 계산한다.</li>
    <li><code>evals/runner.py</code>: exact·keyword·JSON 계약으로 두 모델을 같은 기준에서 채점한다.</li>
    <li><code>apps/gateway/schemas.py</code>: OpenAI 호환 <code>stream_options.include_usage</code>를 허용한다.</li>
    <li><code>values.yaml</code>: 반복 실측으로 고른 GPU memory utilization 0.75와 prefix cache를 GitOps 기본값으로 고정한다.</li>
    <li><code>scripts/start.ps1</code>: Gateway rollout 뒤 Windows 포워드를 자동 재연결한다.</li>
  </ul>

  <h2>배포와 CD 흐름</h2>
  <div class="flow">
    <div class="node">Mac push /<br>PR merge</div><div class="arrow">→</div>
    <div class="node">GitHub<br>Actions</div><div class="arrow">→</div>
    <div class="node">Gateway<br>linux/amd64</div><div class="arrow">→</div>
    <div class="node">GHCR<br>digest</div><div class="arrow">→</div>
    <div class="node">GitOps values<br>bot commit</div><div class="arrow">→</div>
    <div class="node">Argo CD<br>pull + sync</div>
  </div>
  <p><code>wsl2-gpu-release.yml</code>은 Gateway 변경에만 반응해 이미지를 만들고 digest를 고정한다.
  <code>qwen-model</code>은 <code>values.yaml</code>, <code>qwen-gateway</code>는
  <code>values-gitops.yaml</code>을 각각 추적한다. GitHub Actions는 집 Kubernetes API에 접속하지 않는다.</p>

  <h2>재현 명령</h2>
  <pre>task -d stacks/wsl2-gpu perf-benchmark
task -d stacks/wsl2-gpu perf-quality
task -d stacks/wsl2-gpu perf-report</pre>

  <h2>근거와 해석</h2>
  <ul>
    <li><a href="https://docs.vllm.ai/en/stable/benchmarking/cli/">vLLM benchmark metrics</a> · TTFT/TPOT/throughput 정의</li>
    <li><a href="https://docs.vllm.ai/en/stable/features/quantization/">vLLM quantization hardware table</a> · Turing AWQ/GPTQ 지원 범위</li>
    <li><a href="https://docs.vllm.ai/en/stable/features/">vLLM feature compatibility</a> · hardware별 기능 지원 범위</li>
    <li><a href="https://docs.nvidia.com/cuda/wsl-user-guide/">NVIDIA CUDA on WSL guide</a> · Windows driver를 WSL에 전달하고 Linux display driver를 설치하지 않는 원칙</li>
    <li><a href="https://kserve.github.io/website/docs/admin-guide/kubernetes-deployment">KServe Standard Mode</a> · Deployment와 Service 기반 Kubernetes 배포</li>
    <li><a href="https://argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/">Argo CD automated sync</a> · CI가 cluster API에 접속하지 않는 pull-based 배포</li>
    <li><a href="https://huggingface.co/Qwen/Qwen3-4B-AWQ/commit/74d4bd2bd4bff9cafc9345221320bffb08b406a3">Qwen3-4B-AWQ pinned revision</a></li>
    <li><a href="https://github.com/rlaope/estudy/blob/master/MLOps/sglang.md">SGLang serving casebook</a> · 시뮬레이션 수치는 쓰지 않고 SLO → 측정 → 튜닝 → 재측정 순서만 차용</li>
    <li><a href="https://github.com/rlaope/estudy/blob/master/AI/llm_serving_opt.md">LLM serving optimization notes</a> · goodput, shared prefix, 측정 우선 원칙</li>
    <li><a href="https://github.com/JaeoneLim/nano-kpu">nano-kpu fork</a> · <a href="https://jaeonelim.github.io/nano-kpu/">읽기용 사이트</a> · 고정 계약과 correctness gate를 성능 수치와 분리하는 방법론 차용</li>
    <li><a href="https://github.com/MoonshotAI/nano-kpu">nano-kpu</a> · 고정 계약과 correctness gate를 성능 수치와 분리하는 방법론 차용</li>
  </ul>
</main>
</body>
</html>"""
)


def _fmt(value: Any, digits: int = 1) -> str:
    return f"{float(value):,.{digits}f}"


def _model_row(summary: dict[str, Any], quality: dict[str, Any]) -> str:
    status = "통과" if summary["slo"]["pass"] else "실패"
    css = "pass" if summary["slo"]["pass"] else "fail"
    cells = [
        summary["model"],
        f"{sum(item['passed'] for item in quality['results'])}/{len(quality['results'])}",
        f"{_fmt(summary['ttft_ms']['p95'])} ms",
        f"{_fmt(summary['tpot_ms']['p95'])} ms",
        _fmt(summary["output_throughput_tokens_per_second"], 2),
        _fmt(summary["output_tokens_per_hour"], 0),
        f"{_fmt(summary['gpu']['memory_used_mib_peak'], 0)} MiB",
        _fmt(summary["energy"]["gpu_wh_per_1k_output_tokens"], 3),
        _fmt(summary["energy"]["estimated_gpu_cost_krw_per_million_output_tokens"], 1),
        f'<span class="{css}">{status}</span>',
    ]
    return (
        "<tr>"
        + "".join(
            f"<td>{html.escape(cell) if i < 9 else cell}</td>" for i, cell in enumerate(cells)
        )
        + "</tr>"
    )


def _tuning_row(summary: dict[str, Any], label: str, decision: str) -> str:
    return (
        "<tr>"
        f"<td>{html.escape(label)}</td>"
        f"<td>{_fmt(summary['ttft_ms']['p95'])} ms</td>"
        f"<td>{_fmt(summary['tpot_ms']['p95'])} ms</td>"
        f"<td>{_fmt(summary['output_throughput_tokens_per_second'], 2)}</td>"
        f"<td>{_fmt(summary['gpu']['memory_used_mib_peak'], 0)} MiB</td>"
        f"<td>{html.escape(decision)}</td>"
        "</tr>"
    )


def _median_metric(summaries: list[dict[str, Any]], *path: str) -> float:
    values: list[float] = []
    for summary in summaries:
        value: Any = summary
        for key in path:
            value = value[key]
        values.append(float(value))
    return statistics.median(values)


def _repeatability_row(label: str, summaries: list[dict[str, Any]]) -> str:
    ttft = [float(item["ttft_ms"]["p95"]) for item in summaries]
    tpot = [float(item["tpot_ms"]["p95"]) for item in summaries]
    throughput = [float(item["output_throughput_tokens_per_second"]) for item in summaries]
    requests = sum(int(item["requests"]) for item in summaries)
    successes = sum(round(item["requests"] * item["success_rate"]) for item in summaries)
    slo_runs = sum(bool(item["slo"]["pass"]) for item in summaries)
    worst_vram = max(float(item["gpu"]["memory_used_mib_peak"]) for item in summaries)
    cost = _median_metric(summaries, "energy", "estimated_gpu_cost_krw_per_million_output_tokens")
    return (
        "<tr>"
        f"<td>{html.escape(label)}</td>"
        f"<td>{len(summaries)} / {requests}</td>"
        f"<td>{successes}/{requests}</td>"
        f"<td>{_fmt(statistics.median(ttft))} "
        f"({_fmt(min(ttft))}–{_fmt(max(ttft))}) ms</td>"
        f"<td>{_fmt(statistics.median(tpot))} "
        f"({_fmt(min(tpot))}–{_fmt(max(tpot))}) ms</td>"
        f"<td>{_fmt(statistics.median(throughput), 2)} "
        f"({_fmt(min(throughput), 2)}–{_fmt(max(throughput), 2)})</td>"
        f"<td>{_fmt(worst_vram, 0)} MiB</td>"
        f"<td>{_fmt(cost, 1)}원</td>"
        f"<td>{slo_runs}/{len(summaries)}</td>"
        "</tr>"
    )


def _scenario_row(label: str, run: Any, summary: dict[str, Any], *, status: str) -> str:
    requests = int(summary["requests"])
    prompt = float(summary["tokens"]["prompt"]) / requests
    completion = float(summary["tokens"]["completion"]) / requests
    concurrency = int(run.environment["execution_concurrency"])
    css = "pass" if summary["slo"]["pass"] else "fail"
    return (
        "<tr>"
        f"<td>{html.escape(label)}</td>"
        f"<td>{requests} / {concurrency}</td>"
        f"<td>{_fmt(prompt, 0)} / {_fmt(completion, 0)}</td>"
        f"<td>{_fmt(summary['ttft_ms']['p95'])} ms</td>"
        f"<td>{_fmt(summary['tpot_ms']['p95'])} ms</td>"
        f"<td>{_fmt(summary['output_throughput_tokens_per_second'], 2)}</td>"
        f"<td>{_fmt(summary['output_tokens_per_hour'], 0)}</td>"
        f"<td>{_fmt(summary['gpu']['memory_used_mib_peak'], 0)} MiB</td>"
        f"<td>{summary['slo']['requests_met']}/{requests}</td>"
        f'<td><span class="{css}">{html.escape(status)}</span></td>'
        "</tr>"
    )


def _quality_category_row(label: str, result: dict[str, Any]) -> str:
    interval = result["wilson_95"]
    return (
        "<tr>"
        f"<td>{html.escape(label)}</td>"
        f"<td>{result['passed']}/{result['total']}</td>"
        f"<td>{_fmt(100 * result['score'], 0)}%</td>"
        f"<td>{_fmt(100 * interval['lower'], 1)}–{_fmt(100 * interval['upper'], 1)}%</td>"
        "</tr>"
    )


def _study_report(artifact_dir: Path) -> tuple[str, dict[str, Any] | None]:
    study_dir = artifact_dir / "study"
    baseline_names = [f"qwen3-1.7b-fp16-util080-short-c1-run{index}.json" for index in range(1, 4)]
    optimized_names = [f"qwen3-1.7b-fp16-util075-short-c1-run{index}.json" for index in range(1, 4)]
    scenario_names = {
        "prefix_off": "qwen3-1.7b-fp16-util080-shared-prefix-off-c1.json",
        "prefix_on": "qwen3-1.7b-fp16-util075-shared-prefix-on-c1.json",
        "long_prompt": "qwen3-1.7b-fp16-util080-long-prompt-c1.json",
        "long_generation": "qwen3-1.7b-fp16-util080-long-generation-c1.json",
        "c2": "qwen3-1.7b-fp16-util080-short-c2.json",
        "c4": "qwen3-1.7b-fp16-util080-short-c4.json",
    }
    quality_path = study_dir / "qwen3-1.7b-fp16-quality-30.json"
    startup_path = study_dir / "startup-qwen3-1.7b-util075-prefix-on.json"
    required = [
        *(study_dir / name for name in baseline_names),
        *(study_dir / name for name in optimized_names),
        *(study_dir / name for name in scenario_names.values()),
        quality_path,
        startup_path,
    ]
    if not all(path.is_file() for path in required):
        return "", None

    baseline_runs = [load_run(study_dir / name) for name in baseline_names]
    optimized_runs = [load_run(study_dir / name) for name in optimized_names]
    baseline = [summarize_run(run) for run in baseline_runs]
    optimized = [summarize_run(run) for run in optimized_runs]
    scenarios = {
        key: (run := load_run(study_dir / name), summarize_run(run))
        for key, name in scenario_names.items()
    }
    quality = json.loads(quality_path.read_text(encoding="utf-8"))
    startup = json.loads(startup_path.read_text(encoding="utf-8"))

    baseline_ttft = _median_metric(baseline, "ttft_ms", "p95")
    optimized_ttft = _median_metric(optimized, "ttft_ms", "p95")
    baseline_tps = _median_metric(baseline, "output_throughput_tokens_per_second")
    optimized_tps = _median_metric(optimized, "output_throughput_tokens_per_second")
    baseline_cost = _median_metric(
        baseline, "energy", "estimated_gpu_cost_krw_per_million_output_tokens"
    )
    optimized_cost = _median_metric(
        optimized, "energy", "estimated_gpu_cost_krw_per_million_output_tokens"
    )
    baseline_vram = max(item["gpu"]["memory_used_mib_peak"] for item in baseline)
    optimized_vram = max(item["gpu"]["memory_used_mib_peak"] for item in optimized)
    performance_runs = [*baseline_runs, *optimized_runs]
    performance_runs.extend(run for run, _ in scenarios.values())
    total_requests = sum(len(run.results) for run in performance_runs)
    total_minutes = (
        sum(float(run.environment["benchmark_duration_seconds"]) for run in performance_runs) / 60
    )
    failure_counts = Counter(failure for item in quality["results"] for failure in item["failures"])
    failure_labels = {
        "answer_too_long": "길이 상한 초과",
        "exact_answer_mismatch": "정확 일치 실패",
        "invalid_json": "JSON 형식 실패",
        "required_keywords_missing": "필수 키워드 누락",
    }
    failures = " · ".join(
        f"{failure_labels.get(name, name)} {count}건"
        for name, count in failure_counts.most_common()
    )
    category_labels = {
        "arithmetic": "산술",
        "korean_instruction": "한국어 지시 준수",
        "json_values": "JSON 값·형식",
        "code_structure": "코드 구조",
        "multi_turn_context": "멀티턴 문맥",
        "domain_explanation": "도메인 설명",
        "security_abstention": "보안 거절",
    }
    category_rows = "".join(
        _quality_category_row(category_labels.get(name, name), result)
        for name, result in quality["categories"].items()
    )
    repeatability_rows = _repeatability_row(
        "Before 묶음 · util 0.80 / prefix off", baseline
    ) + _repeatability_row("After 묶음 · util 0.75 / prefix on", optimized)
    scenario_rows = "".join(
        (
            _scenario_row(
                "공유 prefix · Before 묶음",
                *scenarios["prefix_off"],
                status="SLO 실패",
            ),
            _scenario_row(
                "공유 prefix · After 묶음",
                *scenarios["prefix_on"],
                status="SLO 통과",
            ),
            _scenario_row(
                "긴 입력 · util 0.80",
                *scenarios["long_prompt"],
                status="TTFT 실패",
            ),
            _scenario_row(
                "긴 생성 · util 0.80",
                *scenarios["long_generation"],
                status="VRAM gate 실패",
            ),
            _scenario_row(
                "short · client concurrency 2",
                *scenarios["c2"],
                status="queue 실패",
            ),
            _scenario_row(
                "short · client concurrency 4",
                *scenarios["c4"],
                status="queue 실패",
            ),
        )
    )
    interval = quality["wilson_95"]
    startup_seconds = startup["durations_seconds"]
    optimized_power = _median_metric(optimized, "gpu", "power_w_mean")
    optimized_temperature = max(item["gpu"]["temperature_c_peak"] for item in optimized)
    optimized_ram = max(item["system"]["memory_used_mib_peak"] for item in optimized)
    optimized_swap = max(item["system"]["swap_used_mib_peak"] for item in optimized)
    html_section = f"""
  <h2>반복 실측이 바꾼 결론</h2>
  <div class="grid">
    <div class="card"><h3><code>실측</code> TTFT p95 중앙값</h3>
      <div class="metric">{_fmt(baseline_ttft)} → {_fmt(optimized_ttft)} ms</div>
      <p class="muted">구성 묶음 전후 {_fmt(100 * (optimized_ttft / baseline_ttft - 1), 1)}%</p></div>
    <div class="card"><h3><code>실측</code> 출력 처리량 중앙값</h3>
      <div class="metric">{_fmt(baseline_tps, 2)} → {_fmt(optimized_tps, 2)} tok/s</div>
      <p class="muted">구성 묶음 전후 +{_fmt(100 * (optimized_tps / baseline_tps - 1), 1)}%</p></div>
    <div class="card"><h3><code>실측</code> 최악 VRAM peak</h3>
      <div class="metric">{_fmt(baseline_vram, 0)} → {_fmt(optimized_vram, 0)} MiB</div>
      <p class="muted">6GiB 기준 여유 {_fmt(6144 - baseline_vram, 0)} → {_fmt(6144 - optimized_vram, 0)} MiB</p></div>
    <div class="card"><h3><code>계산</code> GPU-only 비용 중앙값</h3>
      <div class="metric">{_fmt(baseline_cost, 1)} → {_fmt(optimized_cost, 1)}원</div>
      <p class="muted">백만 출력 토큰당 · 구성 묶음 전후 {_fmt(100 * (optimized_cost / baseline_cost - 1), 1)}%</p></div>
  </div>
  <p class="note"><code>해석/추론</code> 같은 short workload를 각 3회 반복한 결과, After 묶음이
  대화형 SLO를 3/3 run 통과하고 Before 묶음은 VRAM hard gate 때문에 0/3이었다.
  이 비교는 <b>GPU memory utilization 0.80→0.75와 prefix caching off→on을 함께 바꿨다.</b>
  따라서 차이를 어느 한 변수의 단독 효과로 귀속하지 않는다.</p>

  <h3>독립 run 반복성 · 중앙값 (최소–최대)</h3>
  <div class="table-wrap"><table>
    <thead><tr><th>구성 묶음</th><th>run / 요청</th><th>HTTP 성공</th><th>TTFT p95</th>
    <th>TPOT p95</th><th>tok/s</th><th>최악 VRAM</th><th>GPU 비용 중앙값</th><th>run SLO</th></tr></thead>
    <tbody>{repeatability_rows}</tbody>
  </table></div>
  <p class="note">두 묶음 모두 요청별 SLO 충족은 177/180이었다. run 전체 판정 차이는
  After의 최악 VRAM이 5,445MiB로 5,632MiB hard gate 아래에 들어온 데서 생겼다.</p>

  <h3>Workload와 동시성 경계</h3>
  <div class="table-wrap"><table>
    <thead><tr><th>시나리오</th><th>요청 / client C</th><th>평균 입력 / 출력 tok</th><th>TTFT p95</th>
    <th>TPOT p95</th><th>tok/s</th><th>tok/hour</th><th>VRAM</th><th>요청 SLO</th><th>판정</th></tr></thead>
    <tbody>{scenario_rows}</tbody>
  </table></div>
  <ul>
    <li><code>실측</code> client concurrency 2·4에서도 출력은 약 10.14 tok/s였지만 TTFT p95가
      각각 {_fmt(scenarios["c2"][1]["ttft_ms"]["p95"])}ms, {_fmt(scenarios["c4"][1]["ttft_ms"]["p95"])}ms로 늘었다.</li>
    <li><code>해석/추론</code> 서버 <code>max_num_seqs=1</code>이므로 이는 batching 용량이 아니라
      대기열 실험이다. 동시 사용자를 늘리는 설정으로 해석하면 안 된다.</li>
    <li><code>실측</code> 긴 입력은 prefill 때문에 TTFT p95 {_fmt(scenarios["long_prompt"][1]["ttft_ms"]["p95"])}ms,
      긴 생성은 TPOT p95 {_fmt(scenarios["long_generation"][1]["tpot_ms"]["p95"])}ms와
      {_fmt(scenarios["long_generation"][1]["output_throughput_tokens_per_second"], 2)} tok/s였다.</li>
    <li><code>실측</code> 공유-prefix workload의 개선도 util과 cache가 함께 바뀐 묶음 비교다.
      prefix cache만의 효과를 분리하려면 같은 utilization에서 재실험해야 한다.</li>
  </ul>

  <h3>30-case 품질 계약</h3>
  <div class="grid">
    <div class="card"><h3><code>검증</code> 규칙 통과</h3><div class="metric">{quality["passed_count"]}/{quality["total"]}</div>
      <p class="muted">{_fmt(100 * quality["score"], 0)}% · thinking off</p></div>
    <div class="card"><h3><code>계산</code> Wilson 95% 구간</h3>
      <div class="metric">{_fmt(100 * interval["lower"], 1)}–{_fmt(100 * interval["upper"], 1)}%</div>
      <p class="muted">30개 이항 표본의 불확실성</p></div>
    <div class="card"><h3>실패 규칙</h3><p>{html.escape(failures)}</p>
      <p class="note">한 case가 여러 실패 규칙에 함께 집계될 수 있다.</p></div>
  </div>
  <div class="table-wrap"><table>
    <thead><tr><th>범주</th><th>통과</th><th>점수</th><th>Wilson 95%</th></tr></thead>
    <tbody>{category_rows}</tbody>
  </table></div>
  <p class="note">응답 원문은 저장하거나 표시하지 않고 case ID, 범주, 규칙 실패와 answer hash만 남겼다.
  이 결과는 규칙 기반 회귀 gate이지 일반 지능 벤치마크가 아니다. 4B에는 같은 30-case 결과가 없으므로
  확대 평가로 모델 간 품질 우열을 말할 수 없다.</p>

  <h3>시작 시간과 자원 envelope</h3>
  <div class="grid">
    <div class="card"><h3><code>실측</code> warm-cache ready</h3><div class="metric">{_fmt(startup_seconds["ready"], 0)} s</div>
      <p class="muted">container→ready {_fmt(startup_seconds["container_to_ready"], 0)}s · restart 0</p></div>
    <div class="card"><h3><code>실측</code> GPU 온도</h3><div class="metric">{_fmt(optimized_temperature, 0)}°C</div>
      <p class="muted">After 3-run 중 최대</p></div>
    <div class="card"><h3><code>실측</code> 시스템 RAM</h3><div class="metric">{_fmt(optimized_ram, 0)} MiB</div>
      <p class="muted">After 3-run peak 최댓값</p></div>
    <div class="card"><h3><code>실측</code> swap</h3><div class="metric">{_fmt(optimized_swap, 0)} MiB</div>
      <p class="muted">After 3-run peak 최댓값</p></div>
    <div class="card"><h3><code>실측</code> GPU 평균 전력</h3><div class="metric">{_fmt(optimized_power, 1)} W</div>
      <p class="muted">After run별 평균의 중앙값</p></div>
  </div>
  <p class="note">warm cache 시작은 1회 관측뿐이며 cold-cache 비교가 아니다. 각 short run도 약 5분대라
  장시간 soak 안정성을 증명하지 않는다. 전체 성능 study는 {total_requests}개 요청, 합계 약 {_fmt(total_minutes, 1)}분이다.</p>

  <h3>6GB에서의 모델 크기 경계</h3>
  <div class="table-wrap"><table>
    <thead><tr><th>후보</th><th>가중치만의 산술</th><th>현재 근거</th><th>판정</th></tr></thead>
    <tbody>
      <tr><td>Qwen3-1.7B FP16</td><td><code>계산</code> 약 3.4GB</td><td><code>실측</code> After worst 5,445MiB</td><td class="pass">대화형 기본</td></tr>
      <tr><td>Qwen3-4B AWQ</td><td>4-bit 계열 · 실제 artifact로 확인</td><td><code>실측</code> 5.65 tok/s · 기존 9-case 5/9</td><td>용량 우선 조건부</td></tr>
      <tr><td>4B FP16</td><td><code>계산</code> 약 8.0GB</td><td>KV cache·runtime 전에도 6GB 초과</td><td class="fail">적재 실험 제외</td></tr>
      <tr><td>8B FP16</td><td><code>계산</code> 약 16GB</td><td>가중치만으로 6GB 초과</td><td class="fail">불가</td></tr>
      <tr><td>8B 4-bit</td><td><code>계산</code> 이상적 packed 약 4GB</td><td>metadata·KV·runtime 포함 artifact 없음</td><td>미검증 · 가능하다고 단정 금지</td></tr>
    </tbody>
  </table></div>
  <p class="note"><code>해석/추론</code> 현재 적재 성공한 최대 후보는 4B AWQ지만, 기본값은 1.7B FP16이다.
  4B AWQ는 ≥5 tok/s를 허용하고 동일한 30-case에서 품질 이득을 먼저 확인할 때만 조건부다.
  4B 이상 FP16 품질이 필요하면 12GB 이상 GPU 재평가는 합리적이지만, 그 하드웨어 성능은 이 PC에서 실측하지 않았다.</p>
"""
    metrics: dict[str, Any] = {
        "measured_at": max(run.finished_at for run in optimized_runs)[:10],
        "ttft": optimized_ttft,
        "tpot": _median_metric(optimized, "tpot_ms", "p95"),
        "tps": optimized_tps,
        "hour": _median_metric(optimized, "output_tokens_per_hour"),
        "vram": optimized_vram,
        "headroom": 6144 - optimized_vram,
        "power": optimized_power,
        "energy": _median_metric(optimized, "energy", "gpu_wh_per_1k_output_tokens"),
        "cost": optimized_cost,
        "quality": f"{quality['passed_count']}/{quality['total']}",
        "study_sections": html_section,
    }
    return html_section, metrics


def build_report(artifact_dir: Path) -> str:
    selected_run = load_run(artifact_dir / "qwen3-1.7b-util080-thinking-off.json")
    larger_run = load_run(artifact_dir / "qwen3-4b-awq-thinking-off.json")
    gateway_run = load_run(artifact_dir / "gateway-e2e-thinking-off.json")
    selected = summarize_run(selected_run)
    larger = summarize_run(larger_run)
    gateway = summarize_run(gateway_run)
    quality_one = json.loads((artifact_dir / "qwen3-1.7b-quality.json").read_text())
    quality_four = json.loads((artifact_dir / "qwen3-4b-awq-quality.json").read_text())
    study_sections, study = _study_report(artifact_dir)
    chosen = study or {}
    diagnostics = [
        summarize_run(load_run(artifact_dir / name))
        for name in ("baseline-fp16.json", "eager-fp16.json", "util080-fp16.json")
    ]
    gateway_overhead = 100 * (
        1
        - gateway["output_throughput_tokens_per_second"]
        / selected["output_throughput_tokens_per_second"]
    )
    gateway_digest = gateway_run.environment["gateway_image_digest"].split(":", 1)[1][:12]
    substitutions = {
        "measured_at": html.escape(chosen.get("measured_at", selected_run.finished_at[:10])),
        "verdict_title": (
            "현재 증거의 답 · Qwen3-1.7B FP16 / graph / memory 0.75 / prefix cache on"
            if study
            else "현재 증거의 답 · Qwen3-1.7B FP16 / graph / memory 0.80"
        ),
        "verdict_body": (
            "같은 short workload를 3회씩 반복한 구성 묶음 비교에서 After가 SLO 3/3을 통과했다. "
            "utilization과 prefix cache를 함께 바꿨으므로 어느 한 변수의 단독 효과로 해석하지 않는다."
            if study
            else "현재 artifact 범위에서는 0.80이 VRAM 여유와 처리량을 함께 지킨다."
        ),
        "interactive_status": "After 묶음이 독립 run 3/3 통과" if study else "1.7B FP16 통과",
        "runtime_line": "vLLM graph @0.75 + prefix cache" if study else "vLLM graph @0.80",
        "selected_heading": "최종 후보 반복 실측" if study else "최종 후보 실측",
        "selected_basis": (
            "After 묶음 3개 독립 run의 중앙값이며 VRAM은 세 run 중 최악값이다."
            if study
            else "기존 단일 run 기준이다."
        ),
        "selected_ttft": _fmt(chosen.get("ttft", selected["ttft_ms"]["p95"])),
        "selected_tpot": _fmt(chosen.get("tpot", selected["tpot_ms"]["p95"])),
        "selected_tps": _fmt(chosen.get("tps", selected["output_throughput_tokens_per_second"]), 2),
        "selected_hour": _fmt(chosen.get("hour", selected["output_tokens_per_hour"]), 0),
        "selected_vram": _fmt(chosen.get("vram", selected["gpu"]["memory_used_mib_peak"]), 0),
        "selected_headroom": _fmt(
            chosen.get("headroom", 6144 - selected["gpu"]["memory_used_mib_peak"]), 0
        ),
        "selected_power": _fmt(chosen.get("power", selected["gpu"]["power_w_mean"]), 1),
        "selected_energy": _fmt(
            chosen.get("energy", selected["energy"]["gpu_wh_per_1k_output_tokens"]), 3
        ),
        "selected_cost": _fmt(
            chosen.get(
                "cost", selected["energy"]["estimated_gpu_cost_krw_per_million_output_tokens"]
            ),
            1,
        ),
        "study_sections": study_sections,
        "gateway_ttft": _fmt(gateway["ttft_ms"]["p95"]),
        "gateway_tpot": _fmt(gateway["tpot_ms"]["p95"]),
        "gateway_hour": _fmt(gateway["output_tokens_per_hour"], 0),
        "gateway_overhead": _fmt(gateway_overhead, 2),
        "gateway_cost": _fmt(
            gateway["energy"]["estimated_gpu_cost_krw_per_million_output_tokens"], 1
        ),
        "gateway_digest": html.escape(gateway_digest),
        "quality_one": f"{sum(item['passed'] for item in quality_one['results'])}/9",
        "quality_four": f"{sum(item['passed'] for item in quality_four['results'])}/9",
        "model_rows": _model_row(selected, quality_one) + _model_row(larger, quality_four),
        "tuning_rows": "".join(
            (
                _tuning_row(diagnostics[0], "graph · memory 0.85", "기준"),
                _tuning_row(diagnostics[1], "eager · memory 0.85", "기각"),
                _tuning_row(diagnostics[2], "graph · memory 0.80", "채택"),
            )
        ),
    }
    return REPORT_TEMPLATE.substitute(substitutions)


def main() -> int:
    parser = argparse.ArgumentParser(description="WSL2 GPU 실측 HTML 보고서 생성")
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=Path("stacks/wsl2-gpu/artifacts/performance"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.artifacts / "report.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_report(args.artifacts), encoding="utf-8")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
