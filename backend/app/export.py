"""Markdown export (DOC-028) and export packaging (DOC-030, DOC-033; ADR-012).

``to_markdown`` turns the canonical Tiptap JSON (ADR-001) into CommonMark that the importer
(``app.imports.convert_md``) reads back to the same structure, so an export can be re-imported.
Formatting Markdown cannot express is handled explicitly:

- underline becomes ``<u>…</u>`` (GitHub, Obsidian and most viewers render it; our importer
  keeps the text and drops the tag, with a warning);
- text alignment and font sizes are dropped;
- empty paragraphs are dropped (Markdown has no empty paragraph).
"""

import re
import unicodedata
from collections.abc import Iterable
from typing import Any

Node = dict[str, Any]

# Characters that could start Markdown syntax anywhere in a line. Backslash-escaping ASCII
# punctuation is always allowed in CommonMark, so over-escaping is harmless.
_INLINE_SPECIAL = re.compile(r"([\\`*_\[\]<>&|~])")
# Patterns that only matter at the start of a line (headings, lists, quotes, rules).
_LINE_START = re.compile(r"^(\s*)(#{1,6}(?=\s|$)|[-+=](?=\s|$)|>|(\d{1,9})([.)])(?=\s|$))")

_MARK_SYNTAX = {"bold": ("**", "**"), "italic": ("*", "*"), "underline": ("<u>", "</u>")}
_MARK_ORDER = ("bold", "italic", "underline")


def escape_text(text: str) -> str:
    return _INLINE_SPECIAL.sub(r"\\\1", text)


def _escape_line_start(line: str) -> str:
    match = _LINE_START.match(line)
    if not match:
        return line
    indent, token, number, delimiter = (
        match.group(1),
        match.group(2),
        match.group(3),
        match.group(4),
    )
    if number is not None:  # "1. " would start an ordered list
        escaped = f"{number}\\{delimiter}"
    else:
        escaped = "\\" + token
    return indent + escaped + line[match.end() :]


def _marks(node: Node) -> tuple[str, ...]:
    names = {m.get("type") for m in node.get("marks") or [] if isinstance(m, dict)}
    return tuple(m for m in _MARK_ORDER if m in names)


def _inline(nodes: Iterable[Node]) -> str:
    """Inline content with properly nested emphasis.

    Marks are opened and closed as a stack; whitespace at a run's edges is moved outside the
    delimiters, because CommonMark does not treat ``** text**`` as emphasis.
    """
    out: list[str] = []
    open_marks: list[str] = []

    def close_to(depth: int) -> None:
        while len(open_marks) > depth:
            out.append(_MARK_SYNTAX[open_marks.pop()][1])

    for node in nodes:
        if node.get("type") == "hardBreak":
            close_to(0)
            out.append("\\\n")
            continue
        text = node.get("text")
        if node.get("type") != "text" or not isinstance(text, str) or not text:
            continue
        wanted = list(_marks(node))
        common = 0
        while common < min(len(open_marks), len(wanted)) and open_marks[common] == wanted[common]:
            common += 1
        stripped = text.strip()
        if not stripped:  # whitespace only: close marks first so no run ends in a space
            close_to(0)
            out.append(text)
            continue
        lead, trail = text[: len(text) - len(text.lstrip())], text[len(text.rstrip()) :]
        close_to(common)
        out.append(lead)
        for mark in wanted[common:]:
            out.append(_MARK_SYNTAX[mark][0])
            open_marks.append(mark)
        out.append(escape_text(stripped))
        if trail:
            close_to(0)
            out.append(trail)
    close_to(0)
    joined = "".join(out)
    return "\n".join(_escape_line_start(line) for line in joined.split("\n"))


def _block(node: Node) -> str | None:
    kind = node.get("type")
    if kind == "paragraph":
        text = _inline(node.get("content") or [])
        return text if text.strip() else None
    if kind == "heading":
        level = (node.get("attrs") or {}).get("level", 1)
        level = level if level in (1, 2, 3) else 1
        text = _inline(node.get("content") or []).replace("\\\n", " ")
        return "#" * level + (" " + text.lstrip() if text.strip() else "")
    if kind in ("bulletList", "orderedList"):
        return _list(node)
    return None


def _list(node: Node) -> str:
    ordered = node.get("type") == "orderedList"
    start = (node.get("attrs") or {}).get("start") or 1 if ordered else 1
    lines: list[str] = []
    for index, item in enumerate(node.get("content") or []):
        marker = f"{start + index}. " if ordered else "- "
        pad = " " * len(marker)
        parts: list[str] = []
        previous_kind: str | None = None
        for child in item.get("content") or []:
            rendered = _block(child)
            if rendered is None:
                continue
            kind = child.get("type")
            if parts:
                # A nested list can follow directly; a second paragraph needs a blank line.
                is_list = kind in ("bulletList", "orderedList")
                parts.append("\n" if is_list and previous_kind == "paragraph" else "\n\n")
            parts.append(rendered)
            previous_kind = kind
        body = "".join(parts)
        if not body:
            lines.append(marker.rstrip())
            continue
        first, *rest = body.split("\n")
        lines.append(marker + first)
        lines.extend(pad + line if line else "" for line in rest)
    return "\n".join(lines)


def to_markdown(title: str, content: Node, attachments: list[str] | None = None) -> str:
    """The document as Markdown: the title as a level-1 heading, then its content.

    ``attachments`` are relative paths inside an export archive, listed at the end.
    """
    blocks = [f"# {_inline([{'type': 'text', 'text': title}])}"]
    for node in content.get("content") or []:
        rendered = _block(node)
        if rendered is not None:
            blocks.append(rendered)
    if attachments:
        listing = "\n".join(
            f"- [{escape_text(path.rsplit('/', 1)[-1])}](<{path}>)" for path in attachments
        )
        blocks.append("## Attachments\n\n" + listing)
    return "\n\n".join(blocks) + "\n"


def slug(title: str, fallback: str = "document") -> str:
    """A portable file name stem: ASCII letters, digits and hyphens, at most 60 characters."""
    ascii_title = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", ascii_title).strip("-").lower()[:60].strip("-")
    return cleaned or fallback


def safe_file_name(name: str) -> str:
    """An attachment's original name, safe as a single path segment inside a zip."""
    cleaned = "".join(c for c in name if c.isprintable() and c not in '/\\:*?"<>|').strip()
    cleaned = cleaned.lstrip(".").strip()
    return cleaned[:150] or "attachment"


def unique(name: str, taken: set[str]) -> str:
    """``name``, or ``name (2)``, ``name (3)``… keeping the extension, not yet in ``taken``."""
    candidate, n = name, 2
    stem, dot, ext = name.rpartition(".")
    if not stem:
        stem, dot, ext = name, "", ""
    while candidate.lower() in taken:
        candidate = f"{stem} ({n}){dot}{ext}"
        n += 1
    taken.add(candidate.lower())
    return candidate
