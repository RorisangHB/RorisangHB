# Security

## Secrets

Never commit `.env`, an OpenAI API key, the website password, the session secret, conversation exports, or the SQLite database. Keep all permanent API credentials server-side.

For an internet deployment, set `SESSION_COOKIE_SECURE=true`, use HTTPS, keep `APP_PASSWORD` enabled, and use a long random `SESSION_SECRET`. Rotate any credential immediately if it is exposed.

## Reporting a problem

Do not post passwords, API keys, transcripts, or personal memory notes in a public GitHub issue. Remove sensitive values and describe only the minimum technical details needed to reproduce the problem.

## Supported deployment

This is a single-user personal application. It is not designed as a multi-tenant service, identity provider, medical system, emergency service, or high-risk decision system.
