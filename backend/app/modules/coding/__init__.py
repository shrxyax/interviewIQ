"""
Coding IDE: Python-only run/submit against curated problems with real
hidden test cases.

Sandboxing note: this runs submitted code in a separate OS process with
a wall-clock timeout and a static AST check that blocks obviously unsafe
imports/calls (file/network/process access, eval/exec). That is enough
isolation for a local, single-user student project demo. It is NOT a
hardened sandbox (no seccomp/cgroups/container boundary) and must not be
exposed to untrusted users on a shared or public deployment - a real
deployment should run submissions in Judge0 or an equivalent container
sandbox instead.
"""
