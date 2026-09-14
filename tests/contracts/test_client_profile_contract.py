"""ClientProfile contract test: real CanonicalClientState -> client-intake adapter -> schema."""
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from adapters.client_intake_adapter import to_canonical
from _common import load_fixture, validate


def run():
    data = load_fixture("client_profile.json")
    artifact = to_canonical(data)
    ok, msgs = validate(artifact, "client-profile.schema.json")
    return ("client-profile", ok, "valid" if ok else "; ".join(msgs))
