"""Bounded local parsers for already-scanned source bytes."""

import io
import zipfile
from xml.etree import ElementTree


def parse_source(raw: bytes, extension: str) -> str:
    """Extract normalized text without performing network or authority checks."""

    if extension in {"txt", "md"}:
        return raw.decode("utf-8", errors="replace")
    if extension == "docx":
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > 5_000_000 or info.compress_size == 0:
                raise ValueError("document.xml exceeds parser safety limits")
            xml = archive.read("word/document.xml")
        root = ElementTree.fromstring(xml)
        return "\n".join(
            "".join(node.itertext()).strip()
            for node in root.iter()
            if node.tag.endswith("}p") and "".join(node.itertext()).strip()
        )
    if extension == "pdf":
        if not raw.lstrip().startswith(b"%PDF-"):
            return ""
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(raw))
            return "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception:
            return ""
    return ""
