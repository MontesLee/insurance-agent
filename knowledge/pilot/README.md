# Real Knowledge Pilot (Phase 14.7)

Scope: a SMALL set of REAL, publicly published insurance/medical-security
documents exercising the existing knowledge architecture end-to-end.

## Contents

```text
documents/   real partial-verbatim copies, each with an honest
             provenance header (official URL, 文号, dates, copy status)
registry/pilot_sources.json   metadata table (real values; license
             grounded in 《著作权法》第五条, never "official-site ⇒ ALLOWED")
registry/pilot_registry.json  generated: chunk-level sha256 anchors
manifests/pilot_manifest.json generated: document-level hashes + stats
ingest_pilot.py               one-time OFFLINE ingestion (no network)
```

## Honest data notes

- Every document is a PARTIAL copy: the automated retrieval truncated
  long texts, so each fixture retains only its contiguous verbatim
  block; omitted articles are omitted, never reconstructed.
- Real documents loaded: **3** (国务院令第735号条例; 医保局令第2号/第3号).
  The phase minimum was 10 — the shortfall is an acquisition
  constraint of this environment, recorded in the phase report.
- No personal data of any kind; no client data; no product catalog
  changes.

## Access rule

The pilot corpus is reachable ONLY through explicit provider fixture
configuration (`MockKnowledgeProvider(kb_dir=knowledge/pilot/documents)`
+ the pilot registry). No runtime mode reads it by default — asserted
by tests/runtime/test_p14_pilot.py.
