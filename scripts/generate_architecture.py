# pyright: reportPrivateUsage=false, reportUnusedExpression=false

from pathlib import Path

from diagrams import Cluster, Diagram, Edge
from diagrams.gcp.compute import GKE, GPU
from diagrams.gcp.devtools import ContainerRegistry
from diagrams.gcp.network import LoadBalancing
from diagrams.gcp.security import SecretManager
from diagrams.gcp.storage import Storage
from diagrams.k8s.compute import Pod
from diagrams.k8s.ecosystem import Helm
from diagrams.k8s.network import Service
from diagrams.k8s.others import CRD
from diagrams.onprem.ci import GithubActions
from diagrams.onprem.client import User
from diagrams.onprem.gitops import ArgoCD
from diagrams.onprem.monitoring import Grafana, Prometheus
from diagrams.onprem.vcs import Github
from diagrams.programming.flowchart import Decision

ASSET_DIR = Path(__file__).resolve().parents[1] / "docs" / "assets"

GRAPH = {
    "bgcolor": "#ffffff",
    "dpi": "150",
    "fontname": "Arial",
    "fontsize": "22",
    "labelloc": "t",
    "labeljust": "l",
    "pad": "0.35",
    "nodesep": "0.55",
    "ranksep": "0.8",
    "splines": "spline",
}
NODE = {"fontname": "Arial", "fontsize": "12"}
EDGE = {"fontname": "Arial", "fontsize": "10", "color": "#2563eb", "penwidth": "2"}


def output(name: str) -> str:
    return str(ASSET_DIR / name)


def serving_architecture() -> None:
    with Diagram(
        "Qwen Model Serving Architecture",
        filename=output("final-serving-architecture"),
        outformat="png",
        show=False,
        direction="LR",
        graph_attr=GRAPH,
        node_attr=NODE,
        edge_attr=EDGE,
    ):
        user = User("User\nBrowser / API")

        with Cluster("Google Cloud"):
            load_balancer = LoadBalancing("HTTPS\nLoad Balancer")

            with Cluster("GKE Standard Cluster"):
                with Cluster("CPU Node Pool"):
                    gateway_service = Service("Gateway Service")
                    gateway = Pod("Gateway Pod\nFastAPI + Chat UI")
                    kserve = CRD("KServe\nInferenceService")
                    argo = ArgoCD("Argo CD")
                    helm = Helm("Helm Chart")

                with Cluster("GPU Node Pool"):
                    predictor_service = Service("Predictor Service")
                    model = Pod("Model Pod 1..N\nvLLM / SGLang\nQwen")
                    gpu = GPU("NVIDIA L40S")

                prometheus = Prometheus("Prometheus")
                grafana = Grafana("Grafana / Alert")

            secrets = SecretManager("Secret Manager")
            models = Storage("Model Storage\nHF / Object Storage")

        user >> Edge(label="HTTPS") >> load_balancer
        load_balancer >> gateway_service >> gateway
        gateway >> Edge(label="OpenAI JSON / SSE") >> predictor_service >> model >> gpu

        argo >> Edge(label="sync", color="#ea580c", style="dashed") >> helm
        helm >> Edge(label="desired state", color="#ea580c", style="dashed") >> kserve
        kserve >> Edge(label="reconcile", color="#ea580c", style="dashed") >> model

        secrets >> Edge(color="#059669", style="dotted") >> gateway
        secrets >> Edge(color="#059669", style="dotted") >> model
        models >> Edge(color="#059669", style="dotted") >> model
        model >> Edge(label="metrics", color="#059669", style="dotted") >> prometheus >> grafana


def cicd_architecture() -> None:
    with Diagram(
        "CI/CD and GitOps Deployment Architecture",
        filename=output("final-serving-cicd"),
        outformat="png",
        show=False,
        direction="TB",
        graph_attr=GRAPH,
        node_attr=NODE,
        edge_attr=EDGE,
    ):
        developer = User("Developer")

        with Cluster("CI - Build and Verify") as ci:
            github = Github("GitHub\nSource + Helm Values")
            actions = GithubActions("GitHub Actions\nTest + Build")
            registry = ContainerRegistry("Artifact Registry\nImage Digest")
            gpu_gate = GPU("L40S Runtime Gate\nSmoke + Benchmark")
            quality_gate = Decision("Quality Gate")
            deploy_config = Github("Deploy Config\nHelm Values + Digest")

            ci_rank = ci.dot.subgraph()
            assert ci_rank is not None
            with ci_rank as rank:
                rank.attr(rank="same")
                for node in (github, actions, registry, gpu_gate, quality_gate, deploy_config):
                    rank.node(node._id)

        with Cluster("CD - GitOps Deploy and Operate") as cd:
            argo = ArgoCD("Argo CD\nSync + Drift Recovery")
            helm = Helm("Helm Render")
            staging = GKE("GKE Staging\nAPI Smoke + Metrics")
            promotion = Decision("Promotion Gate\nSLO")
            production = GKE("GKE Production\nCanary + SLO")
            rollback = Github("Rollback\nGit Revert")

            cd_rank = cd.dot.subgraph()
            assert cd_rank is not None
            with cd_rank as rank:
                rank.attr(rank="same")
                for node in (argo, helm, staging, promotion, production, rollback):
                    rank.node(node._id)

        developer >> github >> actions >> registry >> gpu_gate >> quality_gate
        quality_gate >> Edge(label="write image digest", color="#ea580c") >> deploy_config
        deploy_config >> Edge(label="Git desired state", color="#ea580c", style="dashed") >> argo
        argo >> helm >> staging >> promotion >> production
        production >> Edge(label="SLO failure", color="#dc2626", style="dashed") >> rollback


if __name__ == "__main__":
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    serving_architecture()
    cicd_architecture()
