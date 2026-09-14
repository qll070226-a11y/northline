from __future__ import annotations

import json
from importlib.resources import files
from typing import Any, Literal

from jsonschema import Draft202012Validator

SchemaKind = Literal["mission", "contract", "receipt", "escalation", "escalationDecision"]


def protocol_schema() -> dict[str, Any]:
    path = files("northline").joinpath("schemas/protocol.schema.json")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_payload(kind: SchemaKind, payload: dict[str, Any]) -> None:
    schema = protocol_schema()
    reference = {"$ref": f"#/$defs/{kind}"}
    Draft202012Validator({**schema, **reference}).validate(payload)
