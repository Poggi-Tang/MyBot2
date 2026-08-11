# Versioning

MyBot2 uses exactly three numeric version levels: `2.x.x`.

- Patch release (`2.3.0` -> `2.3.1`): bug fixes only.
- Minor release (`2.3.0` -> `2.4.0`): new user-facing functionality; reset patch to zero.
- Major release (`2.x.x` -> `3.0.0`): only when the project owner explicitly requests it.

Every iteration must update `mybot_ui.__version__` and `CHANGELOG.md`. A published Git tag must be `v` followed by the exact application version.
