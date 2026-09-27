"""Deterministic locator helpers: suggest a stable locator for a captured DOM element, and
check whether an agent-produced locator points at an element that really exists.

Priority follows .claude/agents/ui-analysis.md: label > role(+name) > test id > id (css).
"""

from __future__ import annotations

import re

from rag_backend.agents.schemas import DomElement, Locator

_FORM_CONTROL_TAGS = frozenset({"input", "select", "textarea"})
_NAMED_ROLES = frozenset({"button", "link", "heading", "checkbox", "radio"})
_ID_SELECTOR = re.compile(r"^#([A-Za-z][\w-]*)$")
_TESTID_SELECTOR = re.compile(r"""^\[data-testid=["']?([^"'\]]+)["']?\]$""")


def clean_label(label: str) -> str:
    """ "First name *" -> "First name": the required marker is not part of the name a
    human (or getByLabel) uses for the field."""
    return label.rstrip(" *:").strip()


def suggest_locator(element: DomElement) -> Locator | None:
    if element.tag in _FORM_CONTROL_TAGS and element.label:
        return Locator(strategy="label", value=clean_label(element.label))
    if element.role in _NAMED_ROLES and element.accessible_name:
        return Locator(strategy="role", value=element.role, name=element.accessible_name)
    if element.test_id:
        return Locator(strategy="testid", value=element.test_id)
    if element.id:
        return Locator(strategy="css", value=f"#{element.id}")
    return None


def with_suggested_locators(elements: list[DomElement]) -> list[DomElement]:
    return [
        element.model_copy(update={"suggested_locator": suggest_locator(element)})
        for element in elements
    ]


def _contains(needle: str, haystack: str | None, exact: bool) -> bool:
    if not haystack:
        return False
    if exact:
        return needle.strip() == clean_label(haystack) or needle.strip() == haystack.strip()
    return needle.strip().lower() in haystack.lower()


def matching_elements(locator: Locator, elements: list[DomElement]) -> list[DomElement] | None:
    """The captured elements a locator would hit, or None when the locator can't be
    checked statically (an arbitrary CSS selector)."""
    if locator.strategy == "label":
        return [e for e in elements if _contains(locator.value, e.label, locator.exact)]
    if locator.strategy == "role":
        return [
            e
            for e in elements
            if e.role == locator.value
            and (locator.name is None or _contains(locator.name, e.accessible_name, locator.exact))
        ]
    if locator.strategy == "testid":
        return [e for e in elements if e.test_id == locator.value]
    if locator.strategy == "text":
        return [e for e in elements if _contains(locator.value, e.text, locator.exact)]
    id_match = _ID_SELECTOR.match(locator.value.strip())
    if id_match:
        return [e for e in elements if e.id == id_match.group(1)]
    testid_match = _TESTID_SELECTOR.match(locator.value.strip())
    if testid_match:
        return [e for e in elements if e.test_id == testid_match.group(1)]
    return None


def describe(locator: Locator) -> str:
    if locator.strategy == "role":
        return f"role={locator.value}" + (f' name="{locator.name}"' if locator.name else "")
    return f'{locator.strategy}="{locator.value}"'
