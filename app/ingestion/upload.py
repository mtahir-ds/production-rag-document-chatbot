"""File upload validation, sanitization, SHA-256 hashing, and disk persistence."""

import hashlib
import re
from pathlib import Path

from fastapi import HTTPException, status

SUPPORTED_EXTENSIONS: dict[str, set[str]] = {
    ".pdf": {"application/pdf"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
    },
    ".pptx": {
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/octet-stream",
    },
    ".txt": {"text/plain", "application/octet-stream"},
    ".md": {"text/markdown", "text/plain", "application/octet-stream"},
}

_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._\- ]+")


def sanitize_filename(filename: str | None) -> str:
    """Strip directory components and unsafe characters from an uploaded filename."""
    if not filename or not filename.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file must have a valid filename.",
        )
    base_name = Path(filename).name.strip()
    cleaned = _SAFE_FILENAME_RE.sub("_", base_name).strip(" .")
    if not cleaned:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded filename contains no valid characters.",
        )
    return cleaned


def validate_upload_file(
    *,
    filename: str | None,
    content_type: str | None,
    content: bytes,
    max_file_size_bytes: int,
) -> tuple[str, str]:
    """Validate filename, extension, magic bytes, and size; return (safe_name, file_type)."""
    safe_name = sanitize_filename(filename)
    ext = Path(safe_name).suffix.lower()

    if ext not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{ext or 'unknown'}'. Supported types: {supported}.",
        )

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty (0 bytes).",
        )

    if len(content) > max_file_size_bytes:
        max_mb = max_file_size_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds maximum allowed size of {max_mb} MB.",
        )

    # Verify magic bytes / content structure so spoofed extensions are rejected.
    if ext == ".pdf" and not content.lstrip().startswith(b"%PDF-"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File extension is .pdf, but file header is not a valid PDF.",
        )

    if ext in {".docx", ".pptx"} and not content.startswith((b"PK\x03\x04", b"PK\x05\x06")):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File extension is {ext}, but file is not a valid Office Open XML archive.",
        )

    if ext in {".txt", ".md"}:
        if b"\x00" in content:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Binary content is not allowed in {ext} files.",
            )
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File '{safe_name}' is not valid UTF-8 text.",
            ) from exc

    # Reject clearly mismatched explicit MIME types when provided by clients.
    if content_type:
        normalized_mime = content_type.split(";")[0].strip().lower()
        allowed_mimes = SUPPORTED_EXTENSIONS[ext]
        if normalized_mime and normalized_mime not in allowed_mimes:
            # Allow generic text/plain for .md or missing browser MIME edge cases, reject obvious mismatches.
            if not (ext == ".md" and normalized_mime.startswith("text/")):
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail=f"MIME type '{normalized_mime}' does not match '{ext}' file.",
                )

    return safe_name, ext.lstrip(".")


def compute_sha256(content: bytes) -> str:
    """Compute the SHA-256 hex digest of raw file bytes for duplicate detection."""
    return hashlib.sha256(content).hexdigest()


def save_uploaded_file(
    *,
    upload_dir: str,
    user_id: str,
    document_id: str,
    safe_filename: str,
    content: bytes,
) -> Path:
    """Persist raw uploaded bytes under a user-scoped directory."""
    user_dir = Path(upload_dir) / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    target_path = user_dir / f"{document_id}_{safe_filename}"
    target_path.write_bytes(content)
    return target_path


def remove_uploaded_file(storage_path: str) -> None:
    """Remove a stored upload file from disk if it exists."""
    path = Path(storage_path)
    if path.exists() and path.is_file():
        path.unlink()
