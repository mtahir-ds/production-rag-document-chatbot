"""Token-aware recursive text chunking with full source metadata preservation."""

import uuid
from dataclasses import dataclass

import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.ingestion.extract import ExtractedSection

_ENCODING = tiktoken.get_encoding("cl100k_base")


@dataclass(slots=True)
class DocumentChunk:
    """Single chunk prepared for embedding and Qdrant vector storage."""

    chunk_id: str
    document_id: str
    user_id: str
    filename: str
    page_or_section: str
    chunk_position: int
    text: str
    token_count: int
    has_injection_signal: bool = False


def count_tokens(text: str) -> int:
    """Count tokens using cl100k_base encoding."""
    return len(_ENCODING.encode(text))


def chunk_sections(
    *,
    sections: list[ExtractedSection],
    document_id: str,
    user_id: str,
    filename: str,
    chunk_size_tokens: int,
    chunk_overlap_tokens: int,
) -> list[DocumentChunk]:
    """Split extracted sections into overlapping token-bounded chunks with metadata."""
    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name="cl100k_base",
        chunk_size=chunk_size_tokens,
        chunk_overlap=chunk_overlap_tokens,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks: list[DocumentChunk] = []
    position = 0

    for section in sections:
        cleaned_section_text = section.text.strip()
        if not cleaned_section_text:
            continue

        split_texts = splitter.split_text(cleaned_section_text)
        for piece in split_texts:
            piece_clean = piece.strip()
            # Skip tiny isolated fragments unless the section itself has no other chunks.
            if len(piece_clean) < 20 and len(split_texts) > 1:
                continue

            position += 1
            chunk_uuid = str(
                uuid.uuid5(uuid.NAMESPACE_DNS, f"{document_id}:{position}")
            )
            chunks.append(
                DocumentChunk(
                    chunk_id=chunk_uuid,
                    document_id=document_id,
                    user_id=user_id,
                    filename=filename,
                    page_or_section=section.page_or_section,
                    chunk_position=position,
                    text=piece_clean,
                    token_count=count_tokens(piece_clean),
                    has_injection_signal=section.has_injection_signal,
                )
            )

    return chunks
