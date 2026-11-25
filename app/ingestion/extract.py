"""Document text extraction with page/section metadata and table preservation."""

import io
import logging
import re
from dataclasses import dataclass

import fitz  # PyMuPDF
from docx import Document as DocxDocument
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph
from fastapi import HTTPException, status
from pptx import Presentation

logger = logging.getLogger(__name__)

# Patterns that may indicate indirect prompt injection hidden inside documents (Bonus B6).
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(your\s+)?(system|safety|developer)\s+(prompt|rules)", re.IGNORECASE),
    re.compile(r"reveal\s+(your\s+)?(system\s+prompt|api\s*key|secret)", re.IGNORECASE),
    re.compile(r"</?(system|assistant|instruction)>", re.IGNORECASE),
]


@dataclass(slots=True)
class ExtractedSection:
    """Extracted text segment tied to its source page or section label."""

    page_or_section: str
    text: str
    has_injection_signal: bool = False


@dataclass(slots=True)
class ExtractionResult:
    """Complete extraction output for a single uploaded document."""

    sections: list[ExtractedSection]
    page_count: int
    suspicious_patterns_detected: int = 0


def _detect_injection_signals(text: str) -> int:
    """Count suspicious instruction-override patterns inside document text."""
    return sum(1 for pattern in _INJECTION_PATTERNS if pattern.search(text))


def _format_table_rows(rows: list[list[str | None]]) -> str:
    """Render table cells as readable pipe-delimited Markdown rows."""
    cleaned_rows: list[str] = []
    for row in rows:
        cells = [re.sub(r"\s+", " ", (cell or "")).strip() for cell in row]
        if any(cells):
            cleaned_rows.append("| " + " | ".join(cells) + " |")
    if len(cleaned_rows) >= 2:
        col_count = len(rows[0])
        separator = "| " + " | ".join(["---"] * col_count) + " |"
        cleaned_rows.insert(1, separator)
    return "\n".join(cleaned_rows)


def extract_pdf(content: bytes, max_pages: int) -> ExtractionResult:
    """Extract text and tables page-by-page from a text-based PDF using PyMuPDF."""
    try:
        doc = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Corrupt or unreadable PDF file.",
        ) from exc

    try:
        if doc.is_encrypted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password-protected or encrypted PDFs are not supported.",
            )

        page_count = doc.page_count
        if page_count == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="PDF document contains 0 pages.",
            )
        if page_count > max_pages:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"PDF has {page_count} pages, exceeding the {max_pages}-page limit.",
            )

        sections: list[ExtractedSection] = []
        suspicious_count = 0

        for idx in range(page_count):
            page = doc.load_page(idx)
            raw_text = (page.get_text("text") or "").strip()

            table_blocks: list[str] = []
            try:
                tables = page.find_tables()
                for table in tables.tables:
                    extracted_rows = table.extract()
                    if extracted_rows:
                        formatted = _format_table_rows(extracted_rows)
                        if formatted:
                            table_blocks.append(formatted)
            except Exception:
                # Fall back cleanly to plain page text if table layout detection fails.
                pass

            combined_parts = [part for part in [raw_text, *table_blocks] if part]
            combined_text = "\n\n".join(combined_parts).strip()

            if combined_text:
                signals = _detect_injection_signals(combined_text)
                suspicious_count += signals
                sections.append(
                    ExtractedSection(
                        page_or_section=f"Page {idx + 1}",
                        text=combined_text,
                        has_injection_signal=signals > 0,
                    )
                )

        if not sections:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "No extractable text found in PDF. Scanned or image-only PDFs "
                    "require OCR, which is currently disabled in this configuration."
                ),
            )

        if suspicious_count > 0:
            logger.warning(
                "Detected %d potential indirect prompt-injection pattern(s) in PDF content.",
                suspicious_count,
            )

        return ExtractionResult(
            sections=sections,
            page_count=page_count,
            suspicious_patterns_detected=suspicious_count,
        )
    finally:
        doc.close()


def extract_docx(content: bytes) -> ExtractionResult:
    """Extract paragraphs and tables in reading order from a DOCX file."""
    try:
        doc = DocxDocument(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Corrupt or unreadable DOCX file.",
        ) from exc

    sections_map: dict[str, list[str]] = {}
    section_order: list[str] = []
    current_section = "Section: Introduction"

    def add_to_section(label: str, text_block: str) -> None:
        if label not in sections_map:
            sections_map[label] = []
            section_order.append(label)
        sections_map[label].append(text_block)

    for child in doc.element.body.iterchildren():
        if isinstance(child, CT_P):
            para = Paragraph(child, doc)
            text = para.text.strip()
            if not text:
                continue
            style_name = (para.style.name if para.style else "") or ""
            if style_name.lower().startswith("heading"):
                current_section = f"Section: {text}"
            add_to_section(current_section, text)
        elif isinstance(child, CT_Tbl):
            table = Table(child, doc)
            rows = [[cell.text for cell in row.cells] for row in table.rows]
            formatted = _format_table_rows(rows)
            if formatted:
                add_to_section(current_section, formatted)

    sections: list[ExtractedSection] = []
    suspicious_count = 0
    for label in section_order:
        joined = "\n\n".join(sections_map[label]).strip()
        if joined:
            signals = _detect_injection_signals(joined)
            suspicious_count += signals
            sections.append(
                ExtractedSection(
                    page_or_section=label,
                    text=joined,
                    has_injection_signal=signals > 0,
                )
            )

    if not sections:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No extractable text found in DOCX document.",
        )

    if suspicious_count > 0:
        logger.warning(
            "Detected %d potential indirect prompt-injection pattern(s) in DOCX content.",
            suspicious_count,
        )

    return ExtractionResult(
        sections=sections,
        page_count=len(sections),
        suspicious_patterns_detected=suspicious_count,
    )


def extract_pptx(content: bytes) -> ExtractionResult:
    """Extract slide text and tables per slide from a PPTX presentation (Bonus B5)."""
    try:
        prs = Presentation(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Corrupt or unreadable PPTX file.",
        ) from exc

    sections: list[ExtractedSection] = []
    suspicious_count = 0

    for idx, slide in enumerate(prs.slides, start=1):
        parts: list[str] = []
        title_text = ""
        if slide.shapes.title and slide.shapes.title.text:
            title_text = slide.shapes.title.text.strip()

        for shape in slide.shapes:
            if shape.has_text_frame:
                text = "\n".join(
                    p.text.strip() for p in shape.text_frame.paragraphs if p.text.strip()
                )
                if text:
                    parts.append(text)
            elif shape.has_table:
                rows = [[cell.text for cell in row.cells] for row in shape.table.rows]
                formatted = _format_table_rows(rows)
                if formatted:
                    parts.append(formatted)

        combined = "\n\n".join(parts).strip()
        if combined:
            label = f"Slide {idx}: {title_text}" if title_text else f"Slide {idx}"
            signals = _detect_injection_signals(combined)
            suspicious_count += signals
            sections.append(
                ExtractedSection(
                    page_or_section=label,
                    text=combined,
                    has_injection_signal=signals > 0,
                )
            )

    if not sections:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No extractable text found in PPTX presentation.",
        )

    return ExtractionResult(
        sections=sections,
        page_count=len(prs.slides),
        suspicious_patterns_detected=suspicious_count,
    )


def extract_text_or_markdown(content: bytes, file_type: str) -> ExtractionResult:
    """Extract plain text or heading-grouped Markdown sections (Bonus B5)."""
    raw = content.decode("utf-8-sig").strip()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Uploaded {file_type.upper()} file contains no readable text.",
        )

    sections: list[ExtractedSection] = []
    suspicious_count = 0

    if file_type == "md":
        current_label = "Section: Overview"
        buffer: list[str] = []
        for line in raw.splitlines():
            heading_match = re.match(r"^(#{1,4})\s+(.+)$", line.strip())
            if heading_match:
                if buffer and "\n".join(buffer).strip():
                    block = "\n".join(buffer).strip()
                    signals = _detect_injection_signals(block)
                    suspicious_count += signals
                    sections.append(
                        ExtractedSection(
                            page_or_section=current_label,
                            text=block,
                            has_injection_signal=signals > 0,
                        )
                    )
                    buffer = []
                current_label = f"Section: {heading_match.group(2).strip()}"
                buffer.append(line)
            else:
                buffer.append(line)

        if buffer and "\n".join(buffer).strip():
            block = "\n".join(buffer).strip()
            signals = _detect_injection_signals(block)
            suspicious_count += signals
            sections.append(
                ExtractedSection(
                    page_or_section=current_label,
                    text=block,
                    has_injection_signal=signals > 0,
                )
            )
    else:
        signals = _detect_injection_signals(raw)
        suspicious_count += signals
        sections.append(
            ExtractedSection(
                page_or_section="Section: Document Body",
                text=raw,
                has_injection_signal=signals > 0,
            )
        )

    return ExtractionResult(
        sections=sections,
        page_count=len(sections),
        suspicious_patterns_detected=suspicious_count,
    )


def extract_document(content: bytes, file_type: str, max_pdf_pages: int) -> ExtractionResult:
    """Dispatch document extraction based on validated file_type."""
    if file_type == "pdf":
        return extract_pdf(content, max_pages=max_pdf_pages)
    if file_type == "docx":
        return extract_docx(content)
    if file_type == "pptx":
        return extract_pptx(content)
    if file_type in {"txt", "md"}:
        return extract_text_or_markdown(content, file_type=file_type)
    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail=f"Unsupported file type '{file_type}'.",
    )
