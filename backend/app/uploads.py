"""Upload validation shared by imports and attachments: allowlist, size, content sniffing."""

import io
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import Literal

from fastapi import HTTPException, UploadFile, status

FileKind = Literal["txt", "md", "docx"]
MIME_TYPES: dict[FileKind, str] = {
    "txt": "text/plain",
    "md": "text/markdown",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_EXTENSIONS: dict[str, FileKind] = {".txt": "txt", ".md": "md", ".markdown": "md", ".docx": "docx"}
_CHUNK = 1024 * 1024


@dataclass(frozen=True)
class ValidatedUpload:
    name: str
    kind: FileKind
    data: bytes

    @property
    def mime_type(self) -> str:
        return MIME_TYPES[self.kind]


def safe_filename(raw: str | None) -> str:
    """Basename only, no control/path characters, bounded length. Display use only."""
    name = PureWindowsPath(PurePosixPath(raw or "").name).name
    name = unicodedata.normalize("NFC", name)
    name = re.sub(r"[\x00-\x1f\x7f<>:\"/\\|?*]", "_", name).strip(" .")
    if len(name) > 200:
        stem, dot, ext = name.rpartition(".")
        name = (stem[: 200 - len(ext) - 1] + dot + ext) if dot else name[:200]
    return name or "upload"


def _unsupported(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail)


async def read_upload(file: UploadFile, max_bytes: int) -> ValidatedUpload:
    name = safe_filename(file.filename)
    kind = _EXTENSIONS.get(PurePosixPath(name).suffix.lower())
    if kind is None:
        raise _unsupported("Unsupported file type. Use .txt, .md or .docx.")

    buf = bytearray()
    while chunk := await file.read(_CHUNK):
        buf.extend(chunk)
        if len(buf) > max_bytes:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                f"File is larger than {max_bytes // (1024 * 1024)} MB.",
            )
    data = bytes(buf)
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "File is empty.")

    if kind == "docx":
        if not _looks_like_docx(data):
            raise _unsupported("File is not a valid .docx document.")
    else:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise _unsupported("Text files must be UTF-8 encoded.") from None
        if "\x00" in text:
            raise _unsupported("File appears to be binary, not text.")
    return ValidatedUpload(name=name, kind=kind, data=data)


def _looks_like_docx(data: bytes) -> bool:
    if not data.startswith(b"PK\x03\x04"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = set(zf.namelist())
            if "word/document.xml" not in names or "[Content_Types].xml" not in names:
                return False
            # Zip-bomb guard: refuse archives that expand far beyond the upload limit.
            return sum(i.file_size for i in zf.infolist()) < 200 * 1024 * 1024
    except zipfile.BadZipFile:
        return False
