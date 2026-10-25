import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.models import EvidenceEvent, User
from app.modules.whiteboard.allocator import reference_allocation
from app.modules.whiteboard.catalog import catalog_public
from app.modules.whiteboard.compiler import DesignError, compile_graph
from app.modules.whiteboard.failures import (
    GRAPH_SCENARIOS,
    SCENARIO_CATALOG,
    TRAFFIC_SPIKE,
    ScenarioError,
    apply_graph_scenario,
    apply_requirements_scenario,
)
from app.modules.whiteboard.findings import (
    AVAILABILITY_SLO,
    LATENCY_SLO,
    SATURATION,
    build_findings,
)
from app.modules.whiteboard.models import (
    AnalysisRun,
    DesignDialogue,
    DesignPrompt,
    DesignSession,
    DesignVersion,
)
from app.modules.whiteboard.queueing import (
    bottleneck_capacity,
    capacity_runway_months,
    compute_traffic,
    end_to_end_availability,
    end_to_end_latency_ms,
    node_metrics,
)
from app.modules.whiteboard.simulation import simulate as run_simulation


class WhiteboardError(ValueError):
    pass


BLOCKING_TYPES = (SATURATION, LATENCY_SLO, AVAILABILITY_SLO)


def finding_key(f) -> str:
    return f"{f.type}:{f.node_id}:{f.metric}"


# --------------------------------------------------------------------------
# Prompts
# --------------------------------------------------------------------------

def get_catalog():
    return catalog_public()


def list_prompts(db: Session, subtopic_id: str | None = None, simulatable_only: bool = False) -> list[dict]:
    q = db.query(DesignPrompt)

    if subtopic_id:
        q = q.filter(DesignPrompt.subtopic_id == subtopic_id)
    if simulatable_only:
        q = q.filter(DesignPrompt.simulatable.is_(True))

    return [
        {
            "id": p.id,
            "subtopic_id": p.subtopic_id,
            "subtopic_name": p.subtopic_name,
            "title": p.title,
            "scenario": p.scenario,
            "difficulty": p.difficulty,
            "tags": p.tags,
            "simulatable": p.simulatable,
        }
        for p in q.order_by(DesignPrompt.subtopic_id, DesignPrompt.id).all()
    ]


def list_subtopics(db: Session) -> list[dict]:
    rows = db.query(DesignPrompt.subtopic_id, DesignPrompt.subtopic_name).distinct().all()
    seen = {}
    for sid, name in rows:
        seen[sid] = name
    return [{"id": k, "name": v} for k, v in sorted(seen.items())]


# --------------------------------------------------------------------------
# Sessions & versions
# --------------------------------------------------------------------------

def start_session(db: Session, user: User, prompt_id: str) -> dict:
    prompt = db.get(DesignPrompt, prompt_id)

    if prompt is None:
        raise WhiteboardError("Prompt not found.")

    if not prompt.simulatable:
        raise WhiteboardError("This prompt is a lightweight card and is not wired into the simulation engine.")

    session = DesignSession(
        id=str(uuid.uuid4()),
        user_id=user.id,
        prompt_id=prompt.id,
        requirements=prompt.requirements,
    )
    db.add(session)
    db.flush()

    version = DesignVersion(session_id=session.id, version_no=1, graph=prompt.starter_graph)
    db.add(version)
    db.commit()

    return {
        "session_id": session.id,
        "prompt": {"id": prompt.id, "title": prompt.title, "scenario": prompt.scenario, "tags": prompt.tags},
        "requirements": session.requirements,
        "version": {"id": version.id, "version_no": 1, "graph": version.graph},
    }


def save_version(db: Session, user: User, session_id: str, graph: dict) -> dict:
    session = _get_session(db, user, session_id)

    try:
        compile_graph(graph)  # validate before persisting
    except DesignError as exc:
        raise WhiteboardError(str(exc))

    last = db.query(DesignVersion).filter_by(session_id=session.id).order_by(DesignVersion.version_no.desc()).first()
    version = DesignVersion(session_id=session.id, version_no=(last.version_no + 1 if last else 1), graph=graph)
    db.add(version)
    db.commit()

    return {"version_id": version.id, "version_no": version.version_no}


def _get_session(db: Session, user: User, session_id: str) -> DesignSession:
    session = db.get(DesignSession, session_id)

    if session is None or session.user_id != user.id:
        raise WhiteboardError("Design session not found.")

    return session


def _get_version(db: Session, user: User, version_id: int) -> tuple[DesignVersion, DesignSession]:
    version = db.get(DesignVersion, version_id)

    if version is None:
        raise WhiteboardError("Design version not found.")

    session = _get_session(db, user, version.session_id)
    return version, session


# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------

def _analyze_graph(graph_json: dict, requirements: dict, client_id: str = "client", strict: bool = True) -> dict:
    try:
        graph = compile_graph(graph_json, strict=strict)
    except DesignError as exc:
        raise WhiteboardError(str(exc)) from exc

    if client_id not in graph.nodes:
        client_id = next(n.id for n in graph.nodes.values() if n.type == "client")

    lambdas = compute_traffic(graph, requirements["peak_rps"])
    metrics = node_metrics(graph, lambdas)
    findings = build_findings(graph, metrics, requirements, client_id)

    p99 = end_to_end_latency_ms(graph, metrics, client_id, percentile="p99")
    mean_lat = end_to_end_latency_ms(graph, metrics, client_id, percentile="mean")
    max_rps, bottleneck = bottleneck_capacity(graph, lambdas, client_id)
    runway = capacity_runway_months(requirements["peak_rps"], max_rps, requirements.get("growth_per_month", 0))

    from app.modules.whiteboard.catalog import DURABLE_STORE_TYPES

    data_stores = [n.id for n in graph.nodes.values() if n.type in DURABLE_STORE_TYPES]
    availability = {
        store: round(end_to_end_availability(graph, client_id, store), 6)
        for store in data_stores
    }

    return {
        "graph": graph,
        "metrics": metrics,
        "findings": findings,
        "summary": {
            "end_to_end_latency_mean_ms": round(mean_lat, 2) if mean_lat != float("inf") else None,
            "end_to_end_latency_p99_ms": round(p99, 2) if p99 != float("inf") else None,
            "max_sustainable_rps": round(max_rps, 1) if max_rps != float("inf") else None,
            "bottleneck_node": bottleneck,
            "capacity_runway_months": round(runway, 1) if runway is not None else None,
            "availability_by_store": availability,
        },
        "node_metrics": {
            node_id: {
                "lambda_rps": round(m.lambda_, 2),
                "capacity_rps": None if m.capacity == float("inf") else round(m.capacity, 1),
                "utilisation": None if m.rho == float("inf") else round(m.rho, 4),
                "p_wait": round(m.p_wait, 4),
                "response_mean_ms": None if m.response_mean_ms == float("inf") else round(m.response_mean_ms, 2),
                "response_p99_ms": None if m.response_p99_ms == float("inf") else round(m.response_p99_ms, 2),
                "saturated": m.saturated,
            }
            for node_id, m in metrics.items()
        },
    }


def analyze(db: Session, user: User, version_id: int, requirements: dict | None, scenario: dict | None) -> dict:
    version, session = _get_version(db, user, version_id)
    reqs = requirements or session.requirements
    graph_json = version.graph
    strict = True

    if scenario:
        try:
            if scenario.get("type") in GRAPH_SCENARIOS:
                graph_json = apply_graph_scenario(graph_json, scenario)
                strict = False
            elif scenario.get("type") == TRAFFIC_SPIKE:
                reqs = apply_requirements_scenario(reqs, scenario)
            else:
                raise WhiteboardError(f"Unknown scenario type '{scenario.get('type')}'.")
        except ScenarioError as exc:
            raise WhiteboardError(str(exc))

    result = _analyze_graph(graph_json, reqs, strict=strict)
    findings = result["findings"]

    run = AnalysisRun(
        version_id=version.id,
        mode="analytic",
        scenario=scenario,
        result={"summary": result["summary"], "node_metrics": result["node_metrics"]},
        findings=[f.to_dict() for f in findings],
    )
    db.add(run)

    if scenario is None:
        _update_resolved_findings(db, session, findings)

    db.commit()

    return {
        "version_id": version.id,
        "summary": result["summary"],
        "node_metrics": result["node_metrics"],
        "findings": [f.to_dict() for f in findings],
        "resolved_since_last_version": session.resolved_findings,
    }


def _update_resolved_findings(db: Session, session: DesignSession, findings) -> None:
    prior_run = (
        db.query(AnalysisRun)
        .join(DesignVersion, AnalysisRun.version_id == DesignVersion.id)
        .filter(DesignVersion.session_id == session.id, AnalysisRun.scenario.is_(None))
        .order_by(AnalysisRun.id.desc())
        .first()
    )

    if prior_run is None:
        return

    prior_keys = {f"{f['type']}:{f['node_id']}:{f['metric']}" for f in prior_run.findings}
    current_keys = {finding_key(f) for f in findings}
    newly_resolved = prior_keys - current_keys

    if newly_resolved:
        session.resolved_findings = sorted(set(session.resolved_findings) | newly_resolved)


def simulate(db: Session, user: User, version_id: int, requirements: dict | None, scenario: dict | None, n_requests: int, replications: int) -> dict:
    version, session = _get_version(db, user, version_id)
    reqs = requirements or session.requirements
    graph_json = version.graph
    delay_at = None
    strict = True

    if scenario:
        if scenario.get("type") == "latency_injection":
            # Applied dynamically inside the DES (scenario_delay_at) rather
            # than by mutating the graph, so each request pays the extra
            # delay only when it actually visits that node.
            delay_at = (scenario["node_id"], scenario.get("extra_ms", 100))
        elif scenario.get("type") in GRAPH_SCENARIOS:
            graph_json = apply_graph_scenario(graph_json, scenario)
            strict = False
        elif scenario.get("type") == TRAFFIC_SPIKE:
            reqs = apply_requirements_scenario(reqs, scenario)

    try:
        graph = compile_graph(graph_json, strict=strict)
    except DesignError as exc:
        raise WhiteboardError(str(exc))

    client_id = next((n.id for n in graph.nodes.values() if n.type == "client"), None)

    result = run_simulation(
        graph, reqs["peak_rps"], client_id,
        n_requests=n_requests, replications=replications,
        scenario_delay_at=delay_at,
    )

    run = AnalysisRun(version_id=version.id, mode="simulation", scenario=scenario, result=result, findings=[])
    db.add(run)
    db.commit()

    return result


def run_scenario_suite(db: Session, user: User, version_id: int) -> dict:
    """
    Resilience %: fraction of a canonical failure-scenario battery the
    design survives without a blocking (saturation/latency/availability)
    finding.
    """

    version, session = _get_version(db, user, version_id)
    reqs = session.requirements
    graph_json = version.graph

    try:
        graph = compile_graph(graph_json)
    except DesignError as exc:
        raise WhiteboardError(str(exc))

    scenarios = []
    for node in graph.nodes.values():
        if node.type != "client" and node.replicas == 1:
            scenarios.append({"type": "kill_node", "node_id": node.id})
        elif node.type != "client" and node.replicas > 1:
            scenarios.append({"type": "lose_replica", "node_id": node.id, "count": 1})

    scenarios.append({"type": TRAFFIC_SPIKE, "multiplier": 2.0})

    if any(n.type == "cache" for n in graph.nodes.values()):
        cache_id = next(n.id for n in graph.nodes.values() if n.type == "cache")
        scenarios.append({"type": "cold_cache", "node_id": cache_id})

    results = []
    for scenario in scenarios:
        try:
            if scenario["type"] in GRAPH_SCENARIOS:
                mutated = apply_graph_scenario(graph_json, scenario)
                r = _analyze_graph(mutated, reqs, strict=False)
            else:
                r = _analyze_graph(graph_json, apply_requirements_scenario(reqs, scenario))
        except (WhiteboardError, DesignError, ScenarioError, KeyError) as exc:
            results.append({"scenario": scenario, "survived": False, "error": str(exc)})
            continue

        blocking = [f for f in r["findings"] if f.type in BLOCKING_TYPES]
        results.append({
            "scenario": scenario,
            "survived": len(blocking) == 0,
            "findings": [f.to_dict() for f in blocking],
        })

    survived = sum(1 for r in results if r["survived"])

    return {
        "scenarios_run": len(results),
        "scenarios_survived": survived,
        "resilience_pct": round(100 * survived / len(results), 1) if results else None,
        "results": results,
    }


# --------------------------------------------------------------------------
# Grounded interviewer
# --------------------------------------------------------------------------

def next_question(db: Session, user: User, session_id: str) -> dict:
    session = _get_session(db, user, session_id)

    latest_version = db.query(DesignVersion).filter_by(session_id=session.id).order_by(DesignVersion.version_no.desc()).first()
    latest_run = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.version_id == latest_version.id, AnalysisRun.scenario.is_(None))
        .order_by(AnalysisRun.id.desc())
        .first()
    )

    if latest_run is None:
        raise WhiteboardError("Run /analyze on the current version before asking for a question.")

    unresolved = [
        f for f in latest_run.findings
        if f"{f['type']}:{f['node_id']}:{f['metric']}" not in session.resolved_findings
    ]

    if not unresolved:
        return {"question": None, "message": "No unresolved findings; the design currently satisfies its requirements."}

    from app.modules.whiteboard.findings import Finding

    top = unresolved[0]
    finding = Finding(top["type"], top["node_id"], top["metric"], top["value"] or 0, top["threshold"], top["severity"], top["message"])

    node = latest_version.graph and next((n for n in latest_version.graph["nodes"] if n["id"] == finding.node_id), None)
    node_label = node.get("label") if node else None

    from app.modules.whiteboard.interviewer import grounded_question

    question = grounded_question(finding, node_label)
    seq = db.query(DesignDialogue).filter_by(session_id=session.id).count() + 1

    db.add(DesignDialogue(session_id=session.id, seq=seq, role="interviewer", text=question, finding_key=finding_key(finding)))
    db.commit()

    return {"question": question, "finding": top}


def respond(db: Session, user: User, session_id: str, text: str) -> dict:
    session = _get_session(db, user, session_id)
    seq = db.query(DesignDialogue).filter_by(session_id=session.id).count() + 1
    db.add(DesignDialogue(session_id=session.id, seq=seq, role="candidate", text=text))
    db.commit()
    return {"ok": True}


def get_dialogue(db: Session, user: User, session_id: str) -> list[dict]:
    session = _get_session(db, user, session_id)
    rows = db.query(DesignDialogue).filter_by(session_id=session.id).order_by(DesignDialogue.seq).all()
    return [{"role": r.role, "text": r.text, "finding_key": r.finding_key} for r in rows]


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def get_report(db: Session, user: User, session_id: str) -> dict:
    session = _get_session(db, user, session_id)
    versions = db.query(DesignVersion).filter_by(session_id=session.id).order_by(DesignVersion.version_no).all()
    latest = versions[-1]

    analysis = _analyze_graph(latest.graph, session.requirements)
    resilience = run_scenario_suite(db, user, latest.id)

    try:
        allocation = reference_allocation(latest.graph, session.requirements, client_id="client")
    except Exception as exc:
        allocation = {"error": str(exc)}

    blocking_left = [f for f in analysis["findings"] if f.type in BLOCKING_TYPES]

    db.add(
        EvidenceEvent(
            user_id=user.id,
            domain="system_design",
            source="whiteboard",
            signal="session_report",
            value={
                "session_id": session.id,
                "prompt_id": session.prompt_id,
                "revisions": len(versions),
                "slo_satisfied": len(blocking_left) == 0,
                "resilience_pct": resilience["resilience_pct"],
                "cost_efficiency": allocation.get("cost_efficiency"),
            },
        )
    )

    session.status = "completed"
    session.ended_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "session_id": session.id,
        "revisions": len(versions),
        "slo_satisfied": len(blocking_left) == 0,
        "remaining_findings": [f.to_dict() for f in blocking_left],
        "summary": analysis["summary"],
        "resilience": resilience,
        "cost_efficiency": allocation.get("cost_efficiency"),
        "reference_cost": allocation.get("reference_cost"),
        "candidate_cost": allocation.get("candidate_cost"),
    }


def scenario_catalog() -> list[dict]:
    return SCENARIO_CATALOG
