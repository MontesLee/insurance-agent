# ADR-014: Production Identity

## Status: APPROVED (design only — implementation in Phase 27)

## Context

Current: API-key bearer (runtime/auth.py), 3 roles (OWNER/REVIEWER/
OPERATOR), env-var identities. Works for single-node pilot.

## Decision

Migrate to OIDC/OAuth2 + JWT for production.

## Identity Provider

- External IdP (Keycloak, Auth0, Azure AD, or corporate SSO)
- OIDC for user authentication
- OAuth2 client-credentials for service-to-service

## Token Model

- Short-lived JWT access tokens (15 min)
- Refresh tokens for user sessions
- JWT claims: sub (user_id), org_id, role, scopes

## RBAC Extension

Current rank-based: OPERATOR < REVIEWER < OWNER.
Production adds org-scoped ABAC:
- Per-project permissions (read/write/approve)
- Per-KB access (already in WeKnora API keys)
- Data classification (real client PII requires REVIEWER+)

## Service-to-Service

- Agent Runtime ↔ WeKnora: existing API key (scoped, rotated)
- Agent Runtime ↔ LLM Gateway: internal JWT
- Agent Runtime ↔ PostgreSQL: connection string from secret manager

## Secret Management

Current: env vars. Production: external secret manager (Vault,
AWS Secrets Manager, or Kubernetes Secrets). Rotation: automated.
The runtime reads secrets at startup; no secrets in code or config
files.
