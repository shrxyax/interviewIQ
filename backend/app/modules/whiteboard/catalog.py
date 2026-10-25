"""
Component catalog: default performance/reliability parameters per node type.

Every number here is a rough, order-of-magnitude assumption for a single
instance of commodity cloud hardware circa the mid-2020s, not a measured
fact about any real product. `assumptions` is shown in the UI so the
candidate (and the judges) can see exactly what the model is assuming,
rather than pretending false precision.

mu            = requests this ONE instance can serve per second (service rate)
base_latency_ms = fixed processing time per request, before queueing delay
availability  = probability a single instance is up at any moment
role          = client | edge | compute | data | queue  (used by the compiler
                for schema validation, e.g. "a cache needs a backing store")
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ComponentType:
    id: str
    label: str
    role: str
    mu: float
    base_latency_ms: float
    availability: float
    assumptions: str
    extra_params: dict = field(default_factory=dict)


CATALOG: dict[str, ComponentType] = {
    "client": ComponentType(
        id="client",
        label="Client",
        role="client",
        mu=float("inf"),
        base_latency_ms=0,
        availability=1.0,
        assumptions="Traffic source. Not a served resource; never a bottleneck itself.",
    ),
    "load_balancer": ComponentType(
        id="load_balancer",
        label="Load Balancer",
        role="edge",
        mu=50_000,
        base_latency_ms=0.5,
        availability=0.9995,
        assumptions="L7 LB (e.g. nginx/ELB-class), simple round robin, negligible CPU cost per request.",
    ),
    "api_service": ComponentType(
        id="api_service",
        label="API Service",
        role="compute",
        mu=800,
        base_latency_ms=8,
        availability=0.999,
        assumptions="Stateless app server, 4 vCPU, JSON over HTTP, simple business logic (no heavy computation).",
    ),
    "cache": ComponentType(
        id="cache",
        label="Cache (Redis-class)",
        role="data",
        mu=50_000,
        base_latency_ms=0.5,
        availability=0.999,
        assumptions="In-memory KV store, single node, small values (<10KB). hit_ratio defaults to 0.8.",
        extra_params={"hit_ratio": 0.8},
    ),
    "sql_primary": ComponentType(
        id="sql_primary",
        label="SQL Database (Primary)",
        role="data",
        mu=5_000,
        base_latency_ms=4,
        availability=0.999,
        assumptions="Postgres-class, 8 vCPU, indexed point reads/writes. Full scans are far slower than this models.",
        extra_params={"read_ratio": 0.8},
    ),
    "read_replica": ComponentType(
        id="read_replica",
        label="SQL Read Replica",
        role="data",
        mu=5_000,
        base_latency_ms=4,
        availability=0.999,
        assumptions="Async replica of a sql_primary. Serves reads only; writes must route to the primary.",
    ),
    "queue": ComponentType(
        id="queue",
        label="Message Queue",
        role="queue",
        mu=20_000,
        base_latency_ms=1,
        availability=0.999,
        assumptions="Kafka/SQS-class durable queue. Decouples producers from consumers (async edge).",
    ),
    "worker": ComponentType(
        id="worker",
        label="Background Worker",
        role="compute",
        mu=200,
        base_latency_ms=20,
        availability=0.999,
        assumptions="Consumes from a queue; heavier per-task cost than a request/response API service.",
    ),
}

DATA_STORE_ROLES = {"data"}

# Durable stores of record, for SPOF/availability purposes. A cache has
# role="data" too (the compiler needs that to require a backing store),
# but losing a cache is a performance problem, not a loss of the canonical
# data, so it is deliberately excluded here.
DURABLE_STORE_TYPES = {"sql_primary", "read_replica"}


def get(type_id: str) -> ComponentType:
    if type_id not in CATALOG:
        raise KeyError(f"Unknown component type '{type_id}'. Known: {sorted(CATALOG)}")

    return CATALOG[type_id]


def catalog_public() -> list[dict]:
    return [
        {
            "id": c.id,
            "label": c.label,
            "role": c.role,
            "defaults": {
                "mu": None if c.mu == float("inf") else c.mu,
                "base_latency_ms": c.base_latency_ms,
                "availability": c.availability,
                **c.extra_params,
            },
            "assumptions": c.assumptions,
        }
        for c in CATALOG.values()
    ]
