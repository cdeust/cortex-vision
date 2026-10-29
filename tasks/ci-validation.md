# Native CI rollout validation

Renderer source: cdeust/zetetic-team-subagents commit `1b7ad1f63dbe38b51a5f5576f3a57f0c35b52847`, invoked through `scripts/setup.sh render-ci <target> --native-review`. Generated assets were not edited.

Before: `ci.json`, `tests/test_adapter.py`, and `requirements-ci.txt` absent.

Final local environment: macOS arm64, CPython 3.14.4. Commands from ci.json ran with `CI_WORK` pointing to registered disposable scratch.

- `python3 scripts/ci.py unit`: exit 0; generated reviewer readers 96 tests OK; adapter 37 passed; coverage 99.48% (shared floor 90%).
- `python3 scripts/ci.py regression`: exit 0; 15 selected adapter tests passed.
- `python3 scripts/ci.py e2e`: exit 0; console entrypoint initialized over real MCP stdio and exposed expected tools/schemas.
- `python3 scripts/ci.py environment`: exit 0; plugin manifest launcher and expanded userConfig defaults initialized over MCP stdio.
- `python3 scripts/ci.py install`: exit 0; built wheel installed into clean venv, import resolved inside that venv, installed console entrypoint handshake passed from scratch cwd. Final protocol script rerun against that installed wheel also exited 0.
- `actionlint .github/workflows/*.yml`: exit 0.
- `git diff --check`: exit 0.

Mutation control: an ephemeral pytest plugin replaced production `intent.classify` in memory with an always-remember function. The routing tests rejected it:

```text
E AssertionError: assert 'remember' == 'recall'
FAILED tests/test_adapter.py::test_routing[auto-What changed?-recall]
1 failed, 4 passed
exit 1
```

Unmutated final suite passed as above; application source was never edited.

Hosted exact-head results, native Claude/Codex review, and workflow bootstrap acceptance remain to be inspected by the orchestrator. Linux/Windows platform rejection is encoded in the protocol tests but was not locally run on those hosts. Synthetic helper fixtures exercise Python boundaries; they do not prove native Swift compilation, physical capture, recognition accuracy, or TCC permission readiness. The wheel validates Python startup; the Swift helper remains supplied by the plugin checkout, as on main.

## macOS installation path follow-up

Initial hosted macOS jobs failed after wheel installation: vision job 123229831617 in run 40807238994; voice job 123230175425 in run 40807245535. The original containment assertion compared canonical imported paths under `/private/var` against lexical scratch roots under `/var`.

Reproduction using actual installed wheels and `CI_WORK=/tmp/...` reproduced exit 1 in both packages before the fix. The checker now canonicalizes both paths and takes the expected installation as a subprocess argument; unrelated roots are still rejected. The exact install command then exits 0 through the same alias and completes the installed MCP handshake.

Three new import-location regressions cover normalized paths, POSIX symlink aliases and outside-root rejection. Removing canonicalization gives `2 failed, 1 passed`; restoring it gives `3 passed`. Direct checks using the actual installed wheel return 0 for its alias root and 1 for the checkout root.

Final local unit suite: 40 passed plus 96 generated reviewer tests; application coverage unchanged. Regression, e2e, environment and install commands pass; actionlint and diff checks pass. Pytest scratch now lives inside CI_WORK so the runner owns and disposes its test outputs. Hosted results for the updated head remain pending.
