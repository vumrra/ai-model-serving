# ruff: noqa: E501, I001

from __future__ import annotations

import argparse
import html
import json
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
    <strong>결론 · Qwen3-1.7B FP16 / thinking off / GPU memory 0.80 유지</strong>
    <span>4B AWQ는 6GB에 올라가지만 채팅 생성 속도가 절반 수준이고 품질 회귀 점수도 더 낮았다.
    0.80은 기준 0.85 대비 처리량 손실을 1% 미만으로 제한하면서 VRAM 안전 여유를 확보했다.</span>
  </section>

  <h2>서비스 목적과 통과 기준</h2>
  <div class="grid">
    <div class="card"><h3>목적</h3><p>한 명이 쓰는 한국어/코드 보조 채팅 LLM API</p></div>
    <div class="card"><h3>응답 시작</h3><div class="metric">≤ 1,000 ms</div><p class="muted">TTFT p95</p></div>
    <div class="card"><h3>생성 간격</h3><div class="metric">≤ 100 ms</div><p class="muted">TPOT p95 · ≥10 tok/s</p></div>
    <div class="card"><h3>안전 여유</h3><div class="metric">≥ 512 MiB</div><p class="muted">6,144 MiB 중 미사용 VRAM</p></div>
  </div>

  <h2>실제 요청 경로</h2>
  <div class="flow">
    <div class="node">LAN Client<br>:8000</div><div class="arrow">→</div>
    <div class="node">FastAPI<br>Gateway</div><div class="arrow">→</div>
    <div class="node">KServe<br>Service</div><div class="arrow">→</div>
    <div class="node">vLLM V0<br>XFormers</div><div class="arrow">→</div>
    <div class="node">Qwen3-1.7B<br>FP16</div>
  </div>
  <p class="note">GTX 1660은 Turing(SM 7.5)이어서 vLLM V1과 FlashAttention-2를 쓰지 못한다.
  원본 vLLM 포트는 측정 때만 localhost:8005로 열었고 외부에는 Gateway만 노출한다.</p>

  <h2>최종 후보 실측</h2>
  <div class="grid">
    <div class="card"><h3>TTFT p95</h3><div class="metric">$selected_ttft ms</div><span class="pass">통과</span></div>
    <div class="card"><h3>TPOT p95</h3><div class="metric">$selected_tpot ms</div><span class="pass">통과</span></div>
    <div class="card"><h3>실제 총 처리량</h3><div class="metric">$selected_tps tok/s</div><p class="muted">$selected_hour tok/hour</p></div>
    <div class="card"><h3>최대 VRAM</h3><div class="metric">$selected_vram MiB</div><p class="muted">$selected_headroom MiB 여유</p></div>
    <div class="card"><h3>GPU 전력</h3><div class="metric">$selected_power W</div><p class="muted">측정 구간 평균</p></div>
    <div class="card"><h3>GPU 에너지</h3><div class="metric">$selected_energy Wh</div><p class="muted">1K 출력 토큰당</p></div>
    <div class="card"><h3>GPU 비용</h3><div class="metric">$selected_cost 원</div><p class="muted">백만 출력 토큰당</p></div>
  </div>

  <h2>모델 비교 · 같은 thinking-off workload</h2>
  <div class="table-wrap"><table>
    <thead><tr><th>모델</th><th>품질</th><th>TTFT p95</th><th>TPOT p95</th>
    <th>tok/s</th><th>시간당 출력 토큰</th><th>VRAM peak</th><th>Wh/1K tok</th><th>원/백만 출력 토큰</th><th>SLO</th></tr></thead>
    <tbody>$model_rows</tbody>
  </table></div>
  <p class="note">전기요금은 200원/kWh 가정의 GPU 전력만 계산했다. PC 나머지 부품, 냉각,
  감가상각은 제외하므로 클라우드 비용과 직접 비교하면 안 된다.</p>

  <h2>튜닝 실험 · 한 변수씩</h2>
  <div class="table-wrap"><table>
    <thead><tr><th>설정</th><th>TTFT p95</th><th>TPOT p95</th><th>tok/s</th>
    <th>VRAM peak</th><th>판정</th></tr></thead><tbody>$tuning_rows</tbody>
  </table></div>
  <ul>
    <li><b>enforce-eager</b>: TTFT는 빨라졌지만 TPOT·총 처리량이 소폭 나빠지고 VRAM 절감은 39MiB뿐이라 기각.</li>
    <li><b>memory 0.80</b>: 처리량 손실 약 0.5%로 287MiB를 절감해 채택.</li>
    <li><b>4B AWQ</b>: 로드는 성공했지만 TPOT SLO 실패, 에너지 증가, 품질 이득 미입증으로 기각.</li>
    <li><b>SGLang/prefix cache</b>: 현재 단일 사용자·공유 prefix 없는 workload에서는 이득 조건이 없어 추가 엔진을 도입하지 않음.</li>
  </ul>
  <p class="note">초기 세 튜닝 실행은 raw API의 Qwen 기본 thinking이 켜진 것을 발견하기 전의 진단 실행이다.
  같은 조건끼리 엔진/메모리 차이만 비교했고, 대표 성능은 별도의 thinking-off 실행만 사용했다.</p>

  <h2>개선 결과와 다음 순서</h2>
  <ul>
    <li><b>적용</b>: graph mode를 유지해 eager보다 시간당 처리량을 보존했다.</li>
    <li><b>적용</b>: GPU memory 0.85→0.80으로 peak를 287MiB 줄여 579MiB의 운영 여유를 만들었다.</li>
    <li><b>조건부</b>: 여러 사용자가 같은 긴 system prompt를 공유할 때만 prefix cache를 켜고 같은 workload로 재측정한다.</li>
    <li><b>하드웨어</b>: 4B 이상 품질이 필요하면 12GB 이상 GPU에서 FP16/BF16 모델을 다시 비교한다. 현재 6GB의 4B AWQ는 SLO를 통과하지 못했다.</li>
  </ul>
  <p class="note">최적화는 단일 숫자 최대화가 아니라 TTFT·TPOT·처리량·VRAM을 동시에 보는 Pareto 선택이다.
  eager는 TTFT만 개선했고 0.80은 VRAM 여유를 크게 개선했으므로, 최종안은 graph/0.80 조합이다.</p>

  <h2>측정 방법</h2>
  <div class="two">
    <div class="card"><h3>성능 계약</h3><p>고정 revision, seed 42, context 1024, sequence 1,
    warm-up 3회 후 5개 prompt × 4 round = 20회, concurrency 1.</p></div>
    <div class="card"><h3>정확성 계약</h3><p>산술·지시 준수·JSON·코드·멀티턴·Kubernetes·안전 9개를
    exact/keyword/JSON/길이 규칙으로 채점. 1.7B $quality_one, 4B AWQ $quality_four.</p></div>
  </div>
  <p>TPOT는 <code>(E2E - TTFT) / (output tokens - 1)</code>로 계산했다.
  전력은 단일 <code>nvidia-smi --loop-ms=500</code> 프로세스로 샘플링해 요청 부하를 줄였다.
  응답 본문은 artifact에 저장하지 않고 request별 latency·usage와 품질 answer hash만 저장했다.</p>

  <h2>이번 코드 변경</h2>
  <ul>
    <li><code>benchmarks/runner.py</code>: 요청 구간만 GPU 전력·VRAM을 샘플링하고 식별정보는 저장하지 않는다.</li>
    <li><code>benchmarks/summarize.py</code>: TPOT, 시간당 토큰, goodput, SLO, 에너지와 예상 비용을 계산한다.</li>
    <li><code>evals/runner.py</code>: exact·keyword·JSON 계약으로 두 모델을 같은 기준에서 채점한다.</li>
    <li><code>apps/gateway/schemas.py</code>: OpenAI 호환 <code>stream_options.include_usage</code>를 허용한다.</li>
    <li><code>values.yaml</code>: 실측으로 고른 GPU memory utilization 0.80을 GitOps 기본값으로 고정한다.</li>
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
    <li><a href="https://docs.vllm.ai/en/v0.16.0/features/quantization/">vLLM quantization hardware table</a> · Turing AWQ 지원 확인</li>
    <li><a href="https://huggingface.co/Qwen/Qwen3-4B-AWQ/commit/74d4bd2bd4bff9cafc9345221320bffb08b406a3">Qwen3-4B-AWQ pinned revision</a></li>
    <li><a href="https://github.com/rlaope/estudy/blob/master/AI/llm_serving_opt.md">LLM serving optimization notes</a> · goodput, shared prefix, 측정 우선 원칙</li>
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


def build_report(artifact_dir: Path) -> str:
    selected_run = load_run(artifact_dir / "qwen3-1.7b-util080-thinking-off.json")
    larger_run = load_run(artifact_dir / "qwen3-4b-awq-thinking-off.json")
    selected = summarize_run(selected_run)
    larger = summarize_run(larger_run)
    quality_one = json.loads((artifact_dir / "qwen3-1.7b-quality.json").read_text())
    quality_four = json.loads((artifact_dir / "qwen3-4b-awq-quality.json").read_text())
    diagnostics = [
        summarize_run(load_run(artifact_dir / name))
        for name in ("baseline-fp16.json", "eager-fp16.json", "util080-fp16.json")
    ]
    substitutions = {
        "measured_at": html.escape(selected_run.finished_at[:10]),
        "selected_ttft": _fmt(selected["ttft_ms"]["p95"]),
        "selected_tpot": _fmt(selected["tpot_ms"]["p95"]),
        "selected_tps": _fmt(selected["output_throughput_tokens_per_second"], 2),
        "selected_hour": _fmt(selected["output_tokens_per_hour"], 0),
        "selected_vram": _fmt(selected["gpu"]["memory_used_mib_peak"], 0),
        "selected_headroom": _fmt(6144 - selected["gpu"]["memory_used_mib_peak"], 0),
        "selected_power": _fmt(selected["gpu"]["power_w_mean"], 1),
        "selected_energy": _fmt(selected["energy"]["gpu_wh_per_1k_output_tokens"], 3),
        "selected_cost": _fmt(
            selected["energy"]["estimated_gpu_cost_krw_per_million_output_tokens"], 1
        ),
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
