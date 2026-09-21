# ADR-012: Object Storage

## Status: APPROVED (design only — implementation in Phase 22)

## Context

Artifacts, reports, and snapshots are currently local files under
`<root>/<project_id>/`. PostgreSQL should not store large blobs.

## Decision

Use Object Storage (S3/MinIO) for content > 64KB.
PostgreSQL stores metadata + hash + storage URI.

## What Goes to Object Storage

| Data | Current location | Target |
|---|---|---|
| Artifact content (JSON blobs) | artifacts/*.json | s3://artifacts/{project_id}/{artifact_type}/{artifact_id} |
| Report rendered content | insurance-report JSON | s3://reports/{project_id}/{report_id} |
| Checkpoint state snapshots | in checkpoints.jsonl | s3://snapshots/{project_id}/{checkpoint_id} |
| Knowledge source documents | knowledge/pilot/documents/ | s3://knowledge/{source_id}/{version} |
| LLM raw logs (if enabled) | not stored | s3://llm-logs/{org_id}/{request_id} (after redaction) |

## Object Metadata

Every object records:
- content_hash (sha256) for tamper detection
- content_type
- created_at, created_by
- encryption flag (server-side or client-side)
- retention_policy (days, or "until project deleted")
- deletion marker (soft delete, then lifecycle rule)

## Access Control

- Objects are private by default
- Access via presigned URLs (time-limited)
- Per-org bucket or prefix isolation
- Encryption at rest (SSE-S3 or client-side for regulated data)

## Why not store everything in PostgreSQL?

- Artifact JSON can be 100KB+ per artifact; 50+ artifacts per case
- Reports with evidence chains can be MB
- PostgreSQL TOAST compresses but doesn't deduplicate
- Object Storage is cheaper per GB and scales independently
