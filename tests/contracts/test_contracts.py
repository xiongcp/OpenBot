import hashlib
import json
import socket
from pathlib import Path

import pytest
from openbot.contracts import (
    CanonicalDocument,
    ContractError,
    SchemaRegistry,
    canonicalize,
    strict_json,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "raw",
    [
        '{"x":1,"x":2}',
        '{"a":{"b":1,"b":2}}',
        '{"x":NaN}',
        '{"x":Infinity}',
        '{"x":1e999}',
        '{"x":"\\ud800"}',
        '"\\udfff"',
        '{"x":9007199254740992}',
    ],
)
def test_ambiguous_or_unsupported_json_is_rejected(raw):
    with pytest.raises(ContractError):
        strict_json(raw)


def test_json_limits_apply_before_validation():
    with pytest.raises(ContractError):
        strict_json("[" * 80 + "0" + "]" * 80)
    with pytest.raises(ContractError):
        strict_json('"' + "x" * 1_048_576 + '"')


@pytest.mark.parametrize(
    ("value", "want"),
    [
        ({"b": -0.0, "a": 1e-7}, b'{"a":1e-7,"b":0}'),
        (
            {"n": [333333333.33333329, 4.50, 2e-3, 1e-27]},
            b'{"n":[333333333.3333333,4.5,0.002,1e-27]}',
        ),
        ({"\ue000": 1, "\U00010000": 2}, '{"\U00010000":2,"\ue000":1}'.encode()),
        ({"z": {"b": 2, "a": 1}}, b'{"z":{"a":1,"b":2}}'),
        ({"n": 9007199254740991}, b'{"n":9007199254740991}'),
    ],
)
def test_jcs_vectors(value, want):
    assert canonicalize(value) == want


def test_jcs_sha256_independent_known_answer():
    doc = CanonicalDocument.create({})
    assert doc.canonical == b"{}"
    assert doc.digest == "sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"


@pytest.mark.parametrize("value", [{1: "x"}, {"x": float("nan")}, {"x": "\ud800"}])
def test_canonicalizer_rejects_non_json_values(value):
    with pytest.raises(ContractError):
        canonicalize(value)


def test_approved_bytes_survive_nested_external_mutation():
    value = {"args": {"argv": ["safe"]}}
    doc = CanonicalDocument.create(value)
    value["args"]["argv"][0] = "unsafe"
    copy = doc.value()
    copy["args"]["argv"][0] = "also-unsafe"
    assert doc.canonical == b'{"args":{"argv":["safe"]}}'
    assert doc.digest == "sha256:" + hashlib.sha256(doc.canonical).hexdigest()


def test_existing_golden_examples_use_complete_validator():
    registry = SchemaRegistry.from_directory(ROOT / "contracts")
    for path in (ROOT / "contracts/examples").glob("*.json"):
        name, outcome = path.name.split(".")[:2]
        schema = name + ".schema.json"
        if outcome == "valid":
            registry.validate(schema, path.read_bytes())
        else:
            with pytest.raises(ContractError):
                registry.validate(schema, path.read_bytes())


def test_local_refs_composition_and_formats_are_enforced():
    schemas = {
        "common.json": {"$defs": {"id": {"type": "string", "format": "uuid"}}},
        "test.json": {
            "type": "object",
            "properties": {
                "id": {"$ref": "common.json#/$defs/id"},
                "at": {"type": "string", "format": "date-time"},
                "n": {"allOf": [{"type": "integer"}, {"minimum": 1}]},
            },
            "required": ["id", "at", "n"],
            "additionalProperties": False,
        },
    }
    registry = SchemaRegistry(schemas)
    data = {"id": "22f89c2b-342e-460d-8ab3-0d5c8e6ba098", "at": "2026-11-04T00:00:00Z", "n": 1}
    registry.validate("test.json", json.dumps(data))
    for key, value in [("id", "not-uuid"), ("at", "today"), ("n", "1"), ("role", "owner")]:
        with pytest.raises(ContractError):
            registry.validate("test.json", json.dumps(data | {key: value}))


@pytest.mark.parametrize(
    "ref", ["https://example.invalid/x.json", "missing.json", "file:///etc/passwd"]
)
def test_unregistered_refs_never_request_network(ref, monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("Schema resolution attempted network")

    monkeypatch.setattr(socket, "getaddrinfo", deny)
    monkeypatch.setattr(socket.socket, "connect", deny)
    with pytest.raises(ContractError):
        SchemaRegistry({"test.json": {"$ref": ref}})


def test_schema_depth_cycles_and_unknown_formats_are_rejected():
    schema = {"type": "string"}
    for _ in range(70):
        schema = {"allOf": [schema]}
    for value in [schema, {"$ref": "#"}, {"type": "string", "format": "unreviewed-format"}]:
        with pytest.raises(ContractError):
            SchemaRegistry({"test.json": value})


def test_schema_keywords_inside_property_names_and_constants_are_data():
    registry = SchemaRegistry(
        {
            "test.json": {
                "type": "object",
                "properties": {"format": {"type": "string"}, "$ref": {"type": "string"}},
                "const": {"format": "data", "$ref": "https://example.invalid/never-a-schema"},
            }
        }
    )
    registry.validate(
        "test.json", '{"format":"data","$ref":"https://example.invalid/never-a-schema"}'
    )


@pytest.mark.parametrize(
    "loop",
    [
        {"$defs": {"loop": {"$anchor": "loop", "allOf": [{"$ref": "#loop"}]}}, "$ref": "#loop"},
        {"$defs": {"loop": {"$ref": "#/%24defs/loop"}}, "$ref": "#/$defs/loop"},
    ],
)
def test_anchor_and_encoded_ref_cycles_fail_during_registration(loop):
    with pytest.raises(ContractError):
        SchemaRegistry({"test.json": loop})


@pytest.mark.parametrize("raw", ["1e20", "1e21", "9007199254740993.0", "9007199254740992e0"])
def test_unsafe_integral_floats_are_rejected_consistently(raw):
    with pytest.raises(ContractError):
        strict_json(raw)


def test_huge_integer_is_a_contract_error():
    with pytest.raises(ContractError):
        strict_json("1" + "0" * 5000)


def test_document_constructor_rejects_mutable_or_noncanonical_bytes():
    for value in [bytearray(b"{}"), b'{"z":1,"a":2}']:
        with pytest.raises(ContractError):
            CanonicalDocument(value)


@pytest.mark.parametrize(
    "hidden",
    [
        {"format": "not-a-reviewed-format"},
        {"$ref": "https://example.invalid/schema"},
        {"$ref": "#/hidden"},
    ],
)
def test_ref_targets_in_annotation_positions_are_reviewed_as_schemas(hidden):
    with pytest.raises(ContractError):
        SchemaRegistry({"test.json": {"$ref": "#/hidden", "hidden": hidden}})
