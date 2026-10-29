# Lessons

- Canonicalize both the imported package path and the expected installation root before checking containment. macOS scratch paths may use `/var` or `/tmp` aliases while Python reports `/private/var` or `/private/tmp`. Reproduce install gates through an alias and keep a negative check rejecting imports outside the installed environment. Sources: the initial PR5 macOS install job logs and `tests/test_ci_install_check.py`.
