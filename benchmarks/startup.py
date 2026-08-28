"""Summarize Kubernetes Pod startup timing from a captured Pod JSON."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _seconds(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    return round((end - start).total_seconds(), 3)


def summarize_pod(pod: dict[str, Any]) -> dict[str, Any]:
    """Return privacy-safe startup milestones and durations for one Pod."""
    metadata = pod.get("metadata", {})
    status = pod.get("status", {})
    created = _timestamp(metadata.get("creationTimestamp"))
    conditions = {
        condition.get("type"): _timestamp(condition.get("lastTransitionTime"))
        for condition in status.get("conditions", [])
    }
    container_statuses = status.get("containerStatuses", [])
    running_starts = [
        _timestamp(item.get("state", {}).get("running", {}).get("startedAt"))
        for item in container_statuses
    ]
    running_starts = [item for item in running_starts if item is not None]
    container_started = min(running_starts) if running_starts else None
    ready = conditions.get("Ready")

    return {
        "schema_version": 1,
        "pod": {
            "name": metadata.get("name"),
            "namespace": metadata.get("namespace"),
            "phase": status.get("phase"),
            "container_count": len(container_statuses),
            "restart_count": sum(int(item.get("restartCount", 0)) for item in container_statuses),
        },
        "milestones": {
            "created_at": metadata.get("creationTimestamp"),
            "scheduled_at": _format_timestamp(conditions.get("PodScheduled")),
            "container_started_at": _format_timestamp(container_started),
            "containers_ready_at": _format_timestamp(conditions.get("ContainersReady")),
            "ready_at": _format_timestamp(ready),
        },
        "durations_seconds": {
            "scheduling": _seconds(created, conditions.get("PodScheduled")),
            "container_start": _seconds(created, container_started),
            "containers_ready": _seconds(created, conditions.get("ContainersReady")),
            "ready": _seconds(created, ready),
            "container_to_ready": _seconds(container_started, ready),
        },
    }


def _format_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def _parse_labels(values: list[str]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for value in values:
        key, separator, item = value.partition("=")
        if not separator or not key:
            raise ValueError(f"label must be KEY=VALUE: {value}")
        labels[key] = item
    return labels


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pod_json", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label", action="append", default=[])
    args = parser.parse_args()

    pod = json.loads(args.pod_json.read_text(encoding="utf-8"))
    summary = summarize_pod(pod)
    summary["labels"] = _parse_labels(args.label)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
