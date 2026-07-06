# Security Policy

## Supported versions

Stepwise is pre-1.0 and under active development. Security fixes land on the
latest release and on `main`.

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Reporting a vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Report privately through either channel:

1. **GitHub Security Advisories** (preferred) — go to the
   [Security tab](https://github.com/Padraigobrien08/MultiModal_Rag/security/advisories/new)
   and choose **Report a vulnerability**.
2. **Email** — padraigobrien00@gmail.com with the subject line
   `SECURITY: Stepwise`.

Please include:

- A description of the issue and its impact.
- Steps to reproduce (proof-of-concept if possible).
- Affected version or commit.
- Any suggested remediation.

## Responsible disclosure

- We will acknowledge your report within **5 business days**.
- We aim to provide an assessment and remediation plan within **30 days**,
  depending on severity and complexity.
- Please give us a reasonable window to release a fix before any public
  disclosure. We're happy to credit you in the release notes unless you'd
  rather stay anonymous.

## Automated scanning

CI runs several security scans on every push and pull request to `main`, plus a
weekly scheduled sweep to catch newly published advisories in unchanged code:

- **CodeQL** ([`codeql.yml`](.github/workflows/codeql.yml)) — static analysis of
  the Python and JavaScript/TypeScript code. Findings appear as alerts in the
  repository's **Security** tab. Advisory-only; it does not block merges.
- **Dependency review**
  ([`dependency-review.yml`](.github/workflows/dependency-review.yml)) — runs on
  pull requests and **fails the check** when a dependency introducing a
  high-or-greater severity vulnerability (or a non-permitted license) is added.
  This is a required-quality gate.
- **Container scan** ([`trivy.yml`](.github/workflows/trivy.yml)) — Trivy scans
  the built application and web images for HIGH/CRITICAL, fixable
  vulnerabilities and reports to the **Security** tab. It is intentionally
  non-blocking, since base-image OS packages often carry unfixed CVEs that would
  otherwise be false-positive failures.

Triage code-scanning alerts from the Security tab. Vulnerabilities found in
Stepwise's own code should follow the private reporting process above.

## Handling secrets

Stepwise depends on secrets — most notably `ANTHROPIC_API_KEY`, and optionally
Google Drive OAuth tokens and Notion credentials.

- **Never commit secrets.** `.env` is git-ignored; use `.env.example` as the
  template for required variables.
- Provide secrets via environment variables or the `.env` file at runtime.
  In Docker they are injected via `env_file` / `environment` in
  `docker-compose.yml`.
- OAuth tokens (e.g. `DRIVE_TOKEN_PATH`, default `./data/drive_token.json`)
  live under `data/`, which is git-ignored. Keep it that way.
- If you believe a secret has been committed or leaked, **rotate it
  immediately** and report it through the private channels above.
