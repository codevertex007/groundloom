"""Deterministic, content-safe renderers for export worker artifacts."""

import io
import zipfile
from html import escape

from ...models import ContentBlock


def render_content(title: str, blocks: list[ContentBlock], format: str) -> bytes:
    lines = [title, "=" * max(len(title), 3)]
    for block in blocks:
        text = block.payload.get("text", block.payload.get("title", ""))
        if block.block_type == "heading":
            lines.extend(["", str(text), "-" * max(len(str(text)), 3)])
        else:
            lines.extend(["", str(text)])
    markdown = "\n".join(lines) + "\n"
    if format == "md":
        return markdown.encode()
    if format == "html":
        body = "".join(
            f"<h1>{escape(line, quote=False)}</h1>"
            if i == 0
            else f"<p>{escape(line, quote=False)}</p>"
            for i, line in enumerate(lines)
            if line
        )
        return (
            "<!doctype html><html><head><meta charset='utf-8'><title>"
            f"{escape(title, quote=False)}</title></head><body>{body}</body></html>"
        ).encode()
    if format == "docx":
        return _minimal_docx(lines)
    return _minimal_pdf(lines)


def _minimal_docx(lines: list[str]) -> bytes:
    document = "".join(
        f"<w:p><w:r><w:t xml:space='preserve'>{escape(line, quote=False)}</w:t></w:r></w:p>"
        for line in lines
    )
    files = {
        "[Content_Types].xml": "<?xml version='1.0'?><Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'><Default Extension='rels' ContentType='application/vnd.openxmlformats-package.relationships+xml'/><Default Extension='xml' ContentType='application/xml'/><Override PartName='/word/document.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'/></Types>",
        "_rels/.rels": "<?xml version='1.0'?><Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'><Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument' Target='word/document.xml'/></Relationships>",
        "word/document.xml": f"<?xml version='1.0'?><w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body>{document}</w:body></w:document>",
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return output.getvalue()


def _minimal_pdf(lines: list[str]) -> bytes:
    content = (
        "BT /F1 11 Tf 50 760 Td "
        + " ".join(
            f"({line.replace('(', '[').replace(')', ']')}) Tj 0 -16 Td" for line in lines[:45]
        )
        + " ET"
    )
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(content.encode())} >>\nstream\n{content}\nendstream",
    ]
    result = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(result))
        result.extend(f"{index} 0 obj\n{obj}\nendobj\n".encode())
    xref = len(result)
    result.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    result.extend("".join(f"{offset:010d} 00000 n \n" for offset in offsets[1:]).encode())
    result.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    )
    return bytes(result)
