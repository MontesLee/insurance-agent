"""Dual-end event-vocabulary contract (Phase 28.B prep, Step 2).

Guard #1 (backend side): runtime/events.py EVENT_TYPES must EQUAL
schema/event-vocabulary.json "vocabulary" — one canonical list, no drift
in either direction. The schema's "reserved" list documents frontend-
known types with NO backend emission yet (contract-first for the router
migration: grounding_started / grounding_completed ride inside
qa_answered data today); the guard asserts that disjointness so a future
backend addition must consciously graduate a type out of reserved.

Mirror guard #2 (frontend side) lives at web/src/types/runtime.test.ts
(vitest): the EventType union must equal vocabulary + reserved.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from jsonschema import Draft7Validator  # noqa: E402

SCHEMA_PATH = os.path.join(REPO, "schema", "event-vocabulary.json")


def _doc() -> dict:
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def test_schema_self_valid():
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        schema = json.load(fh)
    errs = [e.message for e in Draft7Validator(schema).iter_errors(schema)]
    # the document carries its data alongside its schema; validate the data
    # portion against the declared properties
    data = {"vocabulary": schema["vocabulary"], "reserved": schema["reserved"]}
    errs = [e.message for e in Draft7Validator(schema).iter_errors(data)]
    assert not errs, errs


def test_vocabulary_equals_backend_exactly():
    from runtime import events
    doc = _doc()
    backend = set(events.EVENT_TYPES)
    schema = set(doc["vocabulary"])
    missing_in_schema = backend - schema
    extra_in_schema = schema - backend
    assert not missing_in_schema, (
        "backend EVENT_TYPES not in schema/event-vocabulary.json (silent "
        "frontend swallow risk): %s" % sorted(missing_in_schema))
    assert not extra_in_schema, (
        "schema vocabulary not emitted by the backend (graduate it via a "
        "runtime-authorized change or remove): %s" % sorted(extra_in_schema))


def test_reserved_types_have_no_backend_emission_yet():
    from runtime import events
    doc = _doc()
    overlap = set(doc["reserved"]) & set(events.EVENT_TYPES)
    assert not overlap, (
        "reserved types now emitted by the backend — graduate them into "
        "'vocabulary' and drop from 'reserved' in the same change: %s"
        % sorted(overlap))


def test_intent_and_qa_events_are_in_the_contract():
    from runtime import events
    doc = _doc()
    for t in ("intent_classified", "qa_answered"):
        assert t in events.EVENT_TYPES
        assert t in doc["vocabulary"]


if __name__ == "__main__":
    failures = 0
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        try:
            fn()
            print("PASS %s" % fn.__name__)
        except AssertionError as exc:
            failures += 1
            print("FAIL %s :: %s" % (fn.__name__, exc))
    print("\n%d test(s), %d failure(s)" % (len(fns), failures))
    sys.exit(1 if failures else 0)
