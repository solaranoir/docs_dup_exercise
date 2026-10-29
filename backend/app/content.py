"""Server-side validation of the canonical Tiptap/ProseMirror JSON (ADR-001).

Only the node types, marks and attributes the editor can produce are accepted, so stored
content can never carry HTML, scripts or unknown structures into the renderer.
"""

import json
from typing import Any

MAX_CONTENT_BYTES = 1_000_000
MAX_DEPTH = 32
FONT_SIZES = frozenset({"0.875rem", "1rem", "1.25rem", "1.5rem"})

# node type -> (allowed attrs, allowed child node types; None = leaf)
_INLINE = frozenset({"text", "hardBreak"})
_BLOCKS = frozenset({"paragraph", "heading", "bulletList", "orderedList"})
NODES: dict[str, tuple[frozenset[str], frozenset[str] | None]] = {
    "doc": (frozenset(), _BLOCKS),
    "paragraph": (frozenset({"textAlign"}), _INLINE),
    "heading": (frozenset({"level", "textAlign"}), _INLINE),
    "bulletList": (frozenset(), frozenset({"listItem"})),
    "orderedList": (frozenset({"start", "type"}), frozenset({"listItem"})),
    "listItem": (frozenset(), _BLOCKS),
    "text": (frozenset(), None),
    "hardBreak": (frozenset(), None),
}
MARKS: dict[str, frozenset[str]] = {
    "bold": frozenset(),
    "italic": frozenset(),
    "underline": frozenset(),
    "textStyle": frozenset({"fontSize"}),
}


class ContentError(ValueError):
    pass


def _check_attrs(where: str, attrs: Any, allowed: frozenset[str]) -> dict[str, Any]:
    if attrs is None:
        return {}
    if not isinstance(attrs, dict):
        raise ContentError(f"{where}: attrs must be an object")
    unknown = set(attrs) - allowed
    if unknown:
        raise ContentError(f"{where}: unsupported attrs {sorted(unknown)}")
    for key, value in attrs.items():
        if isinstance(value, bool) or not isinstance(value, str | int | None):
            raise ContentError(f"{where}: attr {key} must be a string or integer")
    return attrs


def _check_marks(marks: Any) -> None:
    if marks is None:
        return
    if not isinstance(marks, list):
        raise ContentError("marks must be a list")
    for mark in marks:
        if not isinstance(mark, dict) or mark.get("type") not in MARKS:
            raise ContentError(
                f"unsupported mark {mark.get('type') if isinstance(mark, dict) else mark!r}"
            )
        attrs = _check_attrs(f"mark {mark['type']}", mark.get("attrs"), MARKS[mark["type"]])
        size = attrs.get("fontSize")
        if size is not None and size not in FONT_SIZES:
            raise ContentError(f"unsupported font size {size!r}")


def _check_node(node: Any, allowed_types: frozenset[str], depth: int) -> None:
    if depth > MAX_DEPTH:
        raise ContentError("document is nested too deeply")
    if not isinstance(node, dict):
        raise ContentError("node must be an object")
    node_type = node.get("type")
    if node_type not in allowed_types:
        raise ContentError(f"unsupported node {node_type!r}")
    unknown_keys = set(node) - {"type", "attrs", "content", "marks", "text"}
    if unknown_keys:
        raise ContentError(f"{node_type}: unexpected keys {sorted(unknown_keys)}")
    allowed_attrs, children = NODES[node_type]
    attrs = _check_attrs(node_type, node.get("attrs"), allowed_attrs)
    if node_type == "heading" and attrs.get("level") not in (1, 2, 3):
        raise ContentError("heading level must be 1, 2 or 3")
    if node_type == "text":
        if not isinstance(node.get("text"), str) or not node["text"]:
            raise ContentError("text node requires non-empty text")
        _check_marks(node.get("marks"))
        return
    if "text" in node or "marks" in node:
        raise ContentError(f"{node_type}: only text nodes may carry text or marks")
    content = node.get("content", [])
    if not isinstance(content, list):
        raise ContentError(f"{node_type}: content must be a list")
    if children is None:
        if content:
            raise ContentError(f"{node_type}: must not have content")
        return
    for child in content:
        _check_node(child, children, depth + 1)


def validate_content(doc: Any) -> dict[str, Any]:
    if len(json.dumps(doc)) > MAX_CONTENT_BYTES:
        raise ContentError("document exceeds 1 MB")
    _check_node(doc, frozenset({"doc"}), 0)
    assert isinstance(doc, dict)
    return doc
