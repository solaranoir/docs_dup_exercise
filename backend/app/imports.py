"""Convert .txt / .md / .docx into the editor's Tiptap JSON subset, with fidelity warnings.

Conversion is best-effort (see README): anything outside the supported subset is dropped or
flattened and reported as a warning so the user can review before saving.
"""

import io
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from docx import Document as DocxDocument
from docx.oxml.ns import qn
from markdown_it import MarkdownIt
from markdown_it.token import Token

from app.content import validate_content
from app.uploads import ValidatedUpload

Node = dict[str, Any]


@dataclass
class Conversion:
    content: Node
    warnings: list[str] = field(default_factory=list)


class _Warnings:
    def __init__(self) -> None:
        self._seen: dict[str, None] = {}

    def add(self, message: str) -> None:
        self._seen.setdefault(message, None)

    def list(self) -> list[str]:
        return list(self._seen)


def _text(text: str, marks: Iterable[str] = ()) -> Node:
    node: Node = {"type": "text", "text": text}
    mark_list = [{"type": m} for m in marks]
    if mark_list:
        node["marks"] = mark_list
    return node


def _para(inline: list[Node]) -> Node:
    return {"type": "paragraph", "content": inline} if inline else {"type": "paragraph"}


def _doc(blocks: list[Node]) -> Node:
    return {"type": "doc", "content": blocks or [{"type": "paragraph"}]}


# --- plain text -------------------------------------------------------------------------


def convert_txt(data: bytes) -> Conversion:
    text = data.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\t", "    ")
    blocks: list[Node] = []
    for chunk in re.split(r"\n\s*\n", text):
        lines = [ln for ln in chunk.split("\n")]
        while lines and not lines[-1].strip():
            lines.pop()
        while lines and not lines[0].strip():
            lines.pop(0)
        if not lines:
            continue
        inline: list[Node] = []
        for i, line in enumerate(lines):
            if i:
                inline.append({"type": "hardBreak"})
            if line:
                inline.append(_text(line))
        blocks.append(_para(inline))
    return Conversion(_doc(blocks))


# --- markdown ---------------------------------------------------------------------------

_md = MarkdownIt("commonmark", {"html": True})


def _md_inline(children: list[Token] | None, warn: _Warnings) -> list[Node]:
    out: list[Node] = []
    marks: list[str] = []
    for tok in children or []:
        t = tok.type
        if t == "text" and tok.content:
            out.append(_text(tok.content, marks))
        elif t == "code_inline":
            out.append(_text(tok.content, marks))
            warn.add("Inline code was converted to plain text.")
        elif t in ("strong_open", "em_open"):
            marks.append("bold" if t == "strong_open" else "italic")
        elif t in ("strong_close", "em_close"):
            mark = "bold" if t == "strong_close" else "italic"
            if mark in marks:
                marks.remove(mark)
        elif t in ("softbreak",):
            out.append(_text(" ", marks))
        elif t == "hardbreak":
            out.append({"type": "hardBreak"})
        elif t == "link_open":
            warn.add("Links were converted to plain text.")
        elif t == "image":
            warn.add("Images are not supported and were removed.")
        elif t == "html_inline":
            warn.add("Embedded HTML was removed.")
    return _merge_text(out)


def _merge_text(nodes: list[Node]) -> list[Node]:
    merged: list[Node] = []
    for node in nodes:
        prev = merged[-1] if merged else None
        if (
            prev
            and node["type"] == "text"
            and prev["type"] == "text"
            and prev.get("marks") == node.get("marks")
        ):
            prev["text"] += node["text"]
        else:
            merged.append(dict(node))
    return [n for n in merged if n["type"] != "text" or n["text"]]


def convert_md(data: bytes) -> Conversion:
    warn = _Warnings()
    tokens = _md.parse(data.decode("utf-8-sig"))
    root: list[Node] = []
    stack: list[list[Node]] = [root]  # block containers
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        t = tok.type
        if t == "heading_open":
            level = int(tok.tag[1])
            if level > 3:
                warn.add("Headings below level 3 were converted to Heading 3.")
            inline = _md_inline(tokens[i + 1].children, warn)
            stack[-1].append(
                {"type": "heading", "attrs": {"level": min(level, 3)}, "content": inline}
                if inline
                else {"type": "heading", "attrs": {"level": min(level, 3)}}
            )
            i += 3
            continue
        if t == "paragraph_open":
            stack[-1].append(_para(_md_inline(tokens[i + 1].children, warn)))
            i += 3
            continue
        if t in ("bullet_list_open", "ordered_list_open"):
            lst: Node = {
                "type": "bulletList" if t == "bullet_list_open" else "orderedList",
                "content": [],
            }
            if t == "ordered_list_open":
                start = tok.attrGet("start")
                lst["attrs"] = {"start": int(start) if start else 1, "type": None}
            stack[-1].append(lst)
            stack.append(lst["content"])
        elif t == "list_item_open":
            item: Node = {"type": "listItem", "content": []}
            stack[-1].append(item)
            stack.append(item["content"])
        elif t == "list_item_close":
            items = stack.pop()
            if not items:
                items.append({"type": "paragraph"})
        elif t in ("bullet_list_close", "ordered_list_close"):
            stack.pop()
        elif t in ("fence", "code_block"):
            warn.add("Code blocks were converted to plain paragraphs.")
            for line in tok.content.rstrip("\n").split("\n"):
                stack[-1].append(_para([_text(line)] if line else []))
        elif t == "blockquote_open":
            warn.add("Block quotes were converted to plain paragraphs.")
        elif t == "hr":
            warn.add("Horizontal rules were removed.")
        elif t == "html_block":
            warn.add("Embedded HTML was removed.")
        i += 1
    return Conversion(_doc(root), warn.list())


# --- docx -------------------------------------------------------------------------------


def _docx_list_kind(paragraph: Any, numbering: Any) -> tuple[str, int] | None:
    """Return (list type, level) for a list paragraph, or None."""
    style = (paragraph.style.name or "") if paragraph.style is not None else ""
    ppr = paragraph._p.pPr
    num_pr = ppr.numPr if ppr is not None else None
    if num_pr is None or num_pr.numId is None:
        if style.startswith("List Number"):
            return "orderedList", 0
        if style.startswith("List Bullet") or style == "List Paragraph":
            return "bulletList", 0
        return None
    level = int(num_pr.ilvl.val) if num_pr.ilvl is not None else 0
    kind = "orderedList" if "Number" in style else "bulletList"
    try:
        num = numbering.num_having_numId(num_pr.numId.val)
        abstract_id = num.abstractNumId.val
        for abstract in numbering.findall(qn("w:abstractNum")):
            if int(abstract.get(qn("w:abstractNumId"))) != abstract_id:
                continue
            for lvl in abstract.findall(qn("w:lvl")):
                if int(lvl.get(qn("w:ilvl"))) == level:
                    fmt = lvl.find(qn("w:numFmt"))
                    value = fmt.get(qn("w:val")) if fmt is not None else "bullet"
                    kind = "bulletList" if value in ("bullet", "none") else "orderedList"
    except (AttributeError, KeyError, TypeError, ValueError):
        pass
    return kind, level


def _docx_inline(paragraph: Any, warn: _Warnings) -> list[Node]:
    out: list[Node] = []
    for run in paragraph.runs:
        if run._r.xpath(".//w:drawing | .//w:pict"):
            warn.add("Images and embedded objects were removed.")
        text = run.text
        if not text:
            continue
        marks = [
            m
            for m, on in (("bold", run.bold), ("italic", run.italic), ("underline", run.underline))
            if on
        ]
        parts = text.split("\n")
        for idx, part in enumerate(parts):
            if idx:
                out.append({"type": "hardBreak"})
            if part:
                out.append(_text(part.replace("\t", "    "), marks))
    return _merge_text(out)


def convert_docx(data: bytes) -> Conversion:
    warn = _Warnings()
    document = DocxDocument(io.BytesIO(data))
    body = document.element.body
    if body.xpath(".//w:ins | .//w:del"):
        warn.add("Tracked changes were flattened; review the text.")
    if body.findall(qn("w:tbl")):
        warn.add("Tables are not supported and were removed.")
    if document.sections and len(document.sections) > 1:
        warn.add("Section breaks and page layout were removed.")
    try:
        numbering = document.part.numbering_part.element
    except (KeyError, NotImplementedError):
        numbering = None

    blocks: list[Node] = []
    current_list: Node | None = None
    for paragraph in document.paragraphs:
        style = (paragraph.style.name or "") if paragraph.style is not None else ""
        inline = _docx_inline(paragraph, warn)
        list_info = _docx_list_kind(paragraph, numbering)
        if list_info:
            kind, level = list_info
            if level > 0:
                warn.add("Nested list levels were flattened.")
            if current_list is None or current_list["type"] != kind:
                current_list = {"type": kind, "content": []}
                if kind == "orderedList":
                    current_list["attrs"] = {"start": 1, "type": None}
                blocks.append(current_list)
            current_list["content"].append({"type": "listItem", "content": [_para(inline)]})
            continue
        current_list = None
        heading = re.fullmatch(r"Heading (\d)", style)
        if style == "Title" or heading:
            level = 1 if style == "Title" else int(heading.group(1)) if heading else 1
            if level > 3:
                warn.add("Headings below level 3 were converted to Heading 3.")
            node: Node = {"type": "heading", "attrs": {"level": min(level, 3)}}
            if inline:
                node["content"] = inline
            blocks.append(node)
        elif inline:
            blocks.append(_para(inline))
        elif blocks and blocks[-1] != {"type": "paragraph"}:
            blocks.append({"type": "paragraph"})
    while blocks and blocks[-1] == {"type": "paragraph"}:
        blocks.pop()
    warn.add("Fonts, colours and page formatting are not preserved.")
    return Conversion(_doc(blocks), warn.list())


_CONVERTERS = {"txt": convert_txt, "md": convert_md, "docx": convert_docx}


class ConversionError(ValueError):
    pass


def convert(upload: ValidatedUpload) -> Conversion:
    try:
        result = _CONVERTERS[upload.kind](upload.data)
    except Exception as exc:  # noqa: BLE001 - any parser failure is a user-facing 422
        raise ConversionError(f"Could not read this {upload.kind} file.") from exc
    validate_content(result.content)  # defence in depth: converters emit the editor subset
    return result
