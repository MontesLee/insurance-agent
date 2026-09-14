"""Shared helpers for the Canonical Contract tests (Phase 1)."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
CONTRACTS_DIR = os.path.join(REPO, "contracts")
FIXTURES_DIR = os.path.join(HERE, "fixtures")

if REPO not in sys.path:
    sys.path.insert(0, REPO)

from jsonschema import Draft7Validator  # noqa: E402


def load_schema(name):
    with open(os.path.join(CONTRACTS_DIR, name), encoding="utf-8") as f:
        return json.load(f)


def load_fixture(name):
    with open(os.path.join(FIXTURES_DIR, name), encoding="utf-8") as f:
        return json.load(f)


def validate(artifact, schema_name):
    """Return (ok, list_of_error_messages)."""
    schema = load_schema(schema_name)
    Draft7Validator.check_schema(schema)
    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(artifact), key=lambda e: list(e.path))
    msgs = [f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors]
    return (len(msgs) == 0, msgs)
