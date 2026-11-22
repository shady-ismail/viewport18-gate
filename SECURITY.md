# Security Policy

## Scope

`viewport18-gate` is a local, deterministic developer CLI utility that inspects HTML layout geometry and browser console/network events using headless Chromium via Playwright.

- It runs strictly locally and does **not** transmit telemetry, analytics, or user data.
- It processes **no** PII, credentials, authentication tokens, or payment data.
- It is provided **AS-IS** as a non-commercial personal research utility with **No SLA** and **No Support Guarantees**.

## Reporting a Vulnerability

If you discover a security bug in `viewport18-gate` itself (for example, in local static server path handling, URL validation, or output path sanitization), please open a minimal reproducible report via the repository's issue tracker without including sensitive third-party URLs or private data.

Because this is a maintenance-only personal utility, triage and patches are strictly best-effort with no response-time SLA.
