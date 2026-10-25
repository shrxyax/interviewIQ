"""
Executable Whiteboard: compiles a candidate's system-design graph into an
analysable queueing network.

Pure algorithmic core (no LLM imports):
    catalog.py     component type defaults (capacity, latency, availability)
    compiler.py    JSON graph -> validated internal graph
    structural.py  articulation points, min-cut (networkx)
    queueing.py    traffic propagation, M/M/c, Erlang C, availability
    simulation.py  discrete-event simulation (SimPy) with time-scaling
    failures.py    failure scenarios (kill node, lose replica, spike, cold cache)
    findings.py    deterministic ranking of saturation/SPOF/SLO violations
    allocator.py   greedy reference allocation (cost-efficiency baseline)

Language layer:
    interviewer.py  phrase one question grounded in the top finding (LLM)

Orchestration:
    models.py, seed.py, service.py, api.py
"""
