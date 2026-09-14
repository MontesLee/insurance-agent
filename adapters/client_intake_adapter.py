"""client-intake -> ClientProfile canonical artifact.

client-intake produces the CanonicalClientState (client-state.schema.json) as the single
fact source. This adapter wraps that artifact into the ClientProfile contract envelope.
No facts are modified; downstream must consume via this contract, not raw fields.
"""
from __future__ import annotations

from .base import make_envelope, build_provenance


def to_canonical(client_state: dict, generated_at: str = None) -> dict:
    return make_envelope(
        artifact_type="client-profile",
        skill="client-intake",
        legacy_skill="client-intake",
        payload=client_state,
        provenance=build_provenance(client_state, default_source_id="client-intake"),
        generated_at=generated_at,
    )
