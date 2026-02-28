# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| latest  | ✅        |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Email: **hyatt.yonatan@gmail.com**  
Subject: `[SECURITY] ClawBack — <brief description>`

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

You'll receive an acknowledgement within 48 hours and a resolution timeline within 7 days.

## Scope

Areas of concern include:
- Arbitrary code execution via crafted expense strings
- Google Sheets credential exposure
- Path traversal in state/audit file handling
- Denial of service via parser input

## Out of Scope

- Issues in dependencies (report to the relevant upstream project)
- Missing security headers in non-web contexts
- Rate limiting (ClawBack is a local CLI, not a public API)
