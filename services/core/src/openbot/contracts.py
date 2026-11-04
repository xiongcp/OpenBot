"""Strict JSON, bounded local Schema registry and the authority's JCS adapter."""

import hashlib
import json
import math
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag, urljoin

import rfc8785
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError
from referencing import Registry
from referencing.exceptions import Unresolvable
from referencing.jsonschema import DRAFT202012

MAX_BYTES = 1_048_576
MAX_DEPTH = 64
MAX_NODES = 50_000
BASE = "https://openbot.invalid/contracts/"
DIALECT = "https://json-schema.org/draft/2020-12/schema"


class ContractError(ValueError):
    """Untrusted input does not satisfy the bounded contract."""


def _check_json(value: Any, depth: int = 0, count: list[int] | None = None) -> None:
    count = [0] if count is None else count
    count[0] += 1
    if depth > MAX_DEPTH or count[0] > MAX_NODES:
        raise ContractError("JSON complexity limit exceeded")
    if value is None or type(value) is bool:
        return
    if type(value) is str:
        try:
            value.encode("utf-8")
        except UnicodeError as exc:
            raise ContractError("Invalid Unicode") from exc
    elif type(value) is int:
        if not -(2**53 - 1) <= value <= 2**53 - 1:
            raise ContractError("Integer outside supported I-JSON range")
    elif type(value) is float:
        if not math.isfinite(value) or abs(value) > 2**53 - 1:
            raise ContractError("Number outside supported finite range")
    elif type(value) is list:
        for child in value:
            _check_json(child, depth + 1, count)
    elif type(value) is dict:
        for key, child in value.items():
            if type(key) is not str:
                raise ContractError("Non-string key")
            _check_json(key, depth + 1, count)
            _check_json(child, depth + 1, count)
    else:
        raise ContractError("Unsupported JSON type")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("Duplicate JSON key")
        result[key] = value
    return result


def strict_json(raw: str | bytes) -> Any:
    try:
        encoded = raw.encode("utf-8") if isinstance(raw, str) else raw
        if len(encoded) > MAX_BYTES:
            raise ContractError("JSON byte limit exceeded")
        result = json.loads(
            encoded.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_int=_parse_int,
            parse_float=_parse_float,
        )
        _check_json(result)
        return result
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ContractError("Invalid JSON") from exc


def _parse_int(token: str) -> int:
    if len(token.lstrip("-")) > 16:
        raise ContractError("Integer outside supported I-JSON range")
    return int(token)


def _parse_float(token: str) -> float:
    if abs(Decimal(token)) > 2**53 - 1:
        raise ContractError("Number outside supported finite range")
    return float(token)


def canonicalize(value: Any) -> bytes:
    _check_json(value)
    try:
        result = rfc8785.dumps(value)
    except rfc8785.CanonicalizationError as exc:
        raise ContractError("Invalid canonical JSON") from exc
    if len(result) > MAX_BYTES:
        raise ContractError("Canonical byte limit exceeded")
    return result


@dataclass(frozen=True, slots=True)
class CanonicalDocument:
    canonical: bytes

    def __post_init__(self) -> None:
        if type(self.canonical) is not bytes:
            raise ContractError("Canonical bytes must be immutable")
        if canonicalize(strict_json(self.canonical)) != self.canonical:
            raise ContractError("Noncanonical document")

    @classmethod
    def create(cls, value: Any) -> "CanonicalDocument":
        return cls(canonicalize(value))

    @property
    def digest(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical).hexdigest()

    def value(self) -> Any:
        return strict_json(self.canonical)


class SchemaRegistry:
    """Only preloaded reviewed schemas. No URL/file retrieval or recursive refs."""

    def __init__(self, schemas: dict[str, Any]) -> None:
        if not schemas or len(schemas) > 128:
            raise ContractError("Schema count limit")
        self._schemas: dict[str, Any] = {}
        self._formats = FormatChecker()
        edges: dict[int, set[int]] = {}
        for name, original in schemas.items():
            if not name or "/" in name or ":" in name or "#" in name:
                raise ContractError("Invalid local schema name")
            _check_json(original)
            schema = strict_json(canonicalize(original))
            if type(schema) is not dict:
                raise ContractError("Root schema must be an object")
            if schema.get("$schema", DIALECT) != DIALECT:
                raise ContractError("Unsupported dialect")
            schema["$id"] = BASE + name
            try:
                Draft202012Validator.check_schema(schema)
            except SchemaError as exc:
                raise ContractError("Invalid schema") from exc
            self._schemas[name] = schema
        # Registry's default retriever refuses unknown resources; it does not fetch URLs.
        self._registry = Registry().with_resources(
            (BASE + name, DRAFT202012.create_resource(schema))
            for name, schema in self._schemas.items()
        )
        # Traverse only vocabulary-defined schema locations. Property names and
        # const/default values may themselves contain "$ref" or "format".
        single = {
            "additionalProperties",
            "unevaluatedProperties",
            "propertyNames",
            "contains",
            "unevaluatedItems",
            "items",
            "not",
            "if",
            "then",
            "else",
            "contentSchema",
        }
        arrays = {"allOf", "anyOf", "oneOf", "prefixItems"}
        mappings = {"properties", "patternProperties", "dependentSchemas", "$defs", "definitions"}

        def visit(node: Any, base: str, root: bool = False) -> None:
            here = id(node)
            if here in edges:
                return
            edges.setdefault(here, set())
            if isinstance(node, dict):
                if "$id" in node and not root:
                    raise ContractError("Nested schema identifiers are not admitted")
                if "$dynamicRef" in node or "$recursiveRef" in node:
                    raise ContractError("Dynamic references are not admitted")
                if "format" in node and node["format"] not in self._formats.checkers:
                    raise ContractError("Format has no installed checker")
                if "$ref" in node:
                    target = urljoin(base, node["$ref"])
                    target_base, fragment = urldefrag(target)
                    if target_base not in {BASE + n for n in self._schemas}:
                        raise ContractError("Unregistered schema reference")
                    try:
                        resolved = self._registry.resolver(base).lookup(node["$ref"])
                    except Unresolvable as exc:
                        raise ContractError("Unresolvable local reference") from exc
                    edges[here].add(id(resolved.contents))
                    try:
                        Draft202012Validator.check_schema(resolved.contents)
                    except SchemaError as exc:
                        raise ContractError("Reference target is not a valid schema") from exc
                    visit(
                        resolved.contents,
                        target_base,
                        resolved.contents is self._schemas[target_base.removeprefix(BASE)],
                    )
                children = []
                for key, child in node.items():
                    if key in single:
                        children.append(child)
                    elif key in arrays:
                        children.extend(child)
                    elif key in mappings:
                        children.extend(child.values())
                for child in children:
                    edges[here].add(id(child))
                    visit(child, base)

        for name, schema in self._schemas.items():
            visit(schema, BASE + name, True)
        finished: set[int] = set()

        def acyclic(node: int, active: set[int]) -> None:
            if node in active:
                raise ContractError("Recursive reference exceeds admitted schema subset")
            if node in finished:
                return
            for target in edges.get(node, ()):
                acyclic(target, active | {node})
            finished.add(node)

        for node in edges:
            acyclic(node, set())

    @classmethod
    def from_directory(cls, directory: Path) -> "SchemaRegistry":
        return cls({p.name: strict_json(p.read_bytes()) for p in directory.glob("*.schema.json")})

    def validate(self, name: str, raw: str | bytes) -> CanonicalDocument:
        if name not in self._schemas:
            raise ContractError("Unknown schema")
        value = strict_json(raw)
        try:
            Draft202012Validator(
                self._schemas[name], registry=self._registry, format_checker=self._formats
            ).validate(value)
        except (ValidationError, Unresolvable, RecursionError):
            # Do not put input values, paths or secrets in public exception messages.
            raise ContractError("Schema validation failed") from None
        return CanonicalDocument.create(value)
