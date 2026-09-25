"""Parse the YAML frontmatter + TL;DR header that rag-ai-local/ knowledge docs carry
(see rag-ai-local/template/_METADATA_SCHEMA.md and .claude/rules/file-organization.md).

The frontmatter must be the very first block of the file ("---" on line 1). A missing
or malformed block is not an error: the document is simply indexed as plain text.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)
_TLDR_RE = re.compile(
    r"^##[ \t]+TL;?DR[ \t]*\r?\n(.*?)(?=^##[ \t]|\Z)", re.MULTILINE | re.DOTALL | re.IGNORECASE
)


@dataclass
class DocumentFrontmatter:
    fields: dict[str, Any]
    # Length of the frontmatter block, so section offsets can point into the original text.
    body_offset: int
    body: str
    title: str | None = None
    doc_type: str | None = None
    doc_date: date | None = None
    area: str | None = None
    classification: str | None = None
    tags: list[str] = field(default_factory=list)
    tldr: str | None = None


def _as_str(value: Any) -> str | None:
    return (str(value).strip() or None) if value is not None else None


def _as_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def _as_tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(tag).strip() for tag in value if str(tag).strip()]
    if isinstance(value, str):
        return [tag.strip() for tag in value.split(",") if tag.strip()]
    return []


def parse_frontmatter(text: str) -> DocumentFrontmatter | None:
    match = _FRONTMATTER_RE.match(text)
    if match is None:
        return None
    try:
        fields = yaml.safe_load(match.group(1))
    except yaml.YAMLError as error:
        logger.warning("Ignoring malformed YAML frontmatter: %s", error)
        return None
    if not isinstance(fields, dict):
        return None

    body = text[match.end() :]
    tldr_match = _TLDR_RE.search(body)
    return DocumentFrontmatter(
        fields=fields,
        body_offset=match.end(),
        body=body,
        title=_as_str(fields.get("title")),
        doc_type=_as_str(fields.get("type")),
        doc_date=_as_date(fields.get("date")),
        area=_as_str(fields.get("area")),
        classification=_as_str(fields.get("classification")),
        tags=_as_tags(fields.get("tags")),
        tldr=(tldr_match.group(1).strip() or None) if tldr_match else None,
    )


def classification_hint(raw_bytes: bytes, mime_type: str) -> str | None:
    """The `classification:` a markdown upload declares about itself, if any."""
    if mime_type != "text/markdown":
        return None
    parsed = parse_frontmatter(raw_bytes.decode("utf-8", errors="replace"))
    return parsed.classification if parsed is not None else None
