# Dependency & SPDX License Audit

`viewport18-gate` keeps its dependency tree minimal and strictly permissive. Zero copyleft (`GPL`, `AGPL`, `SSPL`) or source-available (`BSL`) dependencies are used.

## Runtime Dependencies

| Package | Version Constraint | Verified SPDX License | Purpose |
|---|---|---|---|
| Python stdlib (`argparse`, `http.server`, `json`, `pathlib`, `threading`, `urllib.parse`) | Python `>=3.10` | `PSF-2.0` | CLI, ephemeral static server, report serialization |
| `playwright` | `>=1.40,<2.0` | `Apache-2.0` | Headless Chromium layout & network instrumentation |
| `greenlet` *(transitive via `playwright`)* | `<4.0.0,>=3.1.1` | `MIT AND PSF-2.0` | Coroutine runtime required by Playwright Python |

## Development / Test Dependencies (Optional)

| Package | Version Constraint | Verified SPDX License | Purpose |
|---|---|---|---|
| `pytest` | `>=8.0` | `MIT` | Automated unit and Playwright smoke tests |

See [sbom.spdx.json](sbom.spdx.json) for the machine-readable SPDX bill of materials.
