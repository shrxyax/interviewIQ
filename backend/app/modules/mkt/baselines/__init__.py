"""
Literature-baseline comparisons for MKT.

bkt.py      standard 2-state Bayesian Knowledge Tracing (Corbett & Anderson,
            1995) -- a self-contained reference implementation, independent
            of app.modules.mkt.belief.
compare.py  head-to-head harness: BKT vs the real MKT engine on the same
            simulated-candidate population used by app.modules.mkt.simulate.

See results/README.md for the comparison design and findings.
"""
