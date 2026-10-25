"""
Deterministic findings: turn raw metrics into a ranked list of problems.
No LLM involved; severities are fixed arithmetic rules so two runs of the
same design always produce the same findings (a property we specifically
evaluate against LLM-based critique, which does not have it).
"""

from dataclasses import dataclass

from app.modules.whiteboard.compiler import CompiledGraph
from app.modules.whiteboard.queueing import (
    NodeMetrics,
    bottleneck_capacity,
    capacity_runway_months,
    end_to_end_availability,
    end_to_end_latency_ms,
)
from app.modules.whiteboard.structural import single_points_of_failure


SATURATION = "saturation"
SPOF = "spof"
LATENCY_SLO = "latency_slo"
AVAILABILITY_SLO = "availability_slo"
NO_HEADROOM = "no_headroom"


@dataclass
class Finding:
    type: str
    node_id: str | None
    metric: str
    value: float
    threshold: float | None
    severity: float
    message: str

    def to_dict(self):
        return {
            "type": self.type,
            "node_id": self.node_id,
            "metric": self.metric,
            "value": round(self.value, 3) if self.value not in (float("inf"),) else None,
            "threshold": self.threshold,
            "severity": round(self.severity, 3),
            "message": self.message,
        }


def build_findings(
    graph: CompiledGraph,
    metrics: dict[str, NodeMetrics],
    requirements: dict,
    client_id: str,
) -> list[Finding]:
    findings: list[Finding] = []
    total_traffic = sum(m.lambda_ for m in metrics.values() if m.node_id != client_id) or 1.0

    for node_id, m in metrics.items():
        node = graph.nodes[node_id]

        if node.type == "client":
            continue

        if m.saturated or m.rho >= 1.0:
            share = m.lambda_ / total_traffic
            findings.append(
                Finding(
                    SATURATION, node_id, "utilisation", m.rho if m.rho != float("inf") else 999, 1.0,
                    severity=min(10.0, 5 + 5 * share + max(0, (m.rho - 1) if m.rho != float("inf") else 5)),
                    message=f"'{node.label}' is saturated (utilisation {m.rho * 100:.0f}% of capacity) and its latency grows without bound.",
                )
            )
        elif m.rho >= 0.80:
            findings.append(
                Finding(
                    SATURATION, node_id, "utilisation", m.rho, 0.80,
                    severity=3 + 10 * (m.rho - 0.80),
                    message=f"'{node.label}' is at {m.rho * 100:.0f}% utilisation; little headroom before queueing delay grows sharply.",
                )
            )

    for spof in single_points_of_failure(graph):
        node = graph.nodes[spof["node_id"]]
        share = sum(metrics[c].lambda_ for c in spof["blast_radius"] if c in metrics) or 1.0
        findings.append(
            Finding(
                SPOF, spof["node_id"], "blast_radius", len(spof["blast_radius"]), 0,
                severity=min(10.0, 4 + 2 * len(spof["blast_radius"])),
                message=f"'{node.label}' has only 1 replica and is a single point of failure; its loss would cut off {len(spof['blast_radius'])} client path(s).",
            )
        )

    p99_slo = requirements.get("p99_slo_ms")
    if p99_slo:
        p99 = end_to_end_latency_ms(graph, metrics, client_id, percentile="p99")
        if p99 > p99_slo:
            findings.append(
                Finding(
                    LATENCY_SLO, None, "p99_latency_ms", p99, p99_slo,
                    severity=min(10.0, 3 + 7 * min(1.0, (p99 - p99_slo) / max(p99_slo, 1))),
                    message=f"Estimated end-to-end p99 latency is {p99:.0f} ms against an SLO of {p99_slo:.0f} ms.",
                )
            )

    availability_slo = requirements.get("availability_slo")
    if availability_slo:
        data_stores = [n.id for n in graph.nodes.values() if n.catalog.role == "data"]
        worst = min(
            (end_to_end_availability(graph, client_id, store) for store in data_stores),
            default=1.0,
        )
        if worst < availability_slo:
            findings.append(
                Finding(
                    AVAILABILITY_SLO, None, "availability", worst, availability_slo,
                    severity=min(10.0, 3 + 20 * (availability_slo - worst)),
                    message=f"Estimated availability is {worst * 100:.2f}% against an SLO of {availability_slo * 100:.2f}%.",
                )
            )

    growth = requirements.get("growth_per_month")
    peak_rps = requirements.get("peak_rps")
    if growth and peak_rps:
        max_rps, bottleneck = bottleneck_capacity(graph, {k: v.lambda_ for k, v in metrics.items()}, client_id)
        runway = capacity_runway_months(peak_rps, max_rps, growth)
        if runway is not None and runway < 6:
            node = graph.nodes.get(bottleneck)
            findings.append(
                Finding(
                    NO_HEADROOM, bottleneck, "capacity_runway_months", runway, 6,
                    severity=min(10.0, 3 + (6 - runway)),
                    message=f"At {growth * 100:.0f}% monthly growth, '{node.label if node else bottleneck}' runs out of headroom in about {max(runway, 0):.1f} months.",
                )
            )

    findings.sort(key=lambda f: f.severity, reverse=True)
    return findings
