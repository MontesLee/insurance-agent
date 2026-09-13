#!/usr/bin/env python3
"""校验 Knowledge Search 的 input / output JSON 是否符合 draft-07 schema。"""
import json
import os
import sys

from jsonschema import Draft7Validator

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
SCHEMA_DIR = os.path.join(SKILL_DIR, "schemas")


def _load(name):
    return json.load(open(os.path.join(SCHEMA_DIR, name), encoding="utf-8-sig"))


def validate_input(data):
    errs = sorted(Draft7Validator(_load("knowledge-search-input.schema.json")).iter_errors(data),
                   key=lambda e: list(e.path))
    if errs:
        raise ValueError("INPUT_INVALID: " + "; ".join(
            f"{list(e.path)}: {e.message}" for e in errs[:5]))
    return True


def validate_output(data):
    errs = sorted(Draft7Validator(_load("knowledge-search-output.schema.json")).iter_errors(data),
                   key=lambda e: list(e.path))
    if errs:
        raise ValueError("OUTPUT_INVALID: " + "; ".join(
            f"{list(e.path)}: {e.message}" for e in errs[:5]))
    return True


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: validate_retrieval.py <input|output> <json_file>")
        sys.exit(2)
    kind, path = sys.argv[1], sys.argv[2]
    data = json.load(open(path, encoding="utf-8-sig"))
    (validate_input if kind == "input" else validate_output)(data)
    print("OK", kind)
