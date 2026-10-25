"""
Metamorphic Knowledge Testing (MKT).

Pure algorithmic core (no LLM imports):
    states.py      state / outcome / relation vocabularies
    emissions.py   P(outcome | state, relation) tables
    belief.py      Bayesian updates, entropy, information gain, graph priors
    selection.py   expected-information-gain probe selection
    simulate.py    simulated candidates for offline evaluation

Language layer:
    extraction.py  answer -> atomic propositions (LLM, with fallback)
    consistency.py NLI + symbolic checks -> discrete outcome

Orchestration:
    models.py, seed.py, service.py, api.py
"""
