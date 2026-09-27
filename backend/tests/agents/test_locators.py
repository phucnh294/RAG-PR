from __future__ import annotations

from rag_backend.agents.locators import matching_elements, suggest_locator
from rag_backend.agents.schemas import Locator
from tests.agents.fakes import register_dom


def _by_id(element_id: str):  # type: ignore[no-untyped-def]
    return next(e for e in register_dom() if e.id == element_id)


def test_suggest_locator_prefers_label_without_required_marker() -> None:
    assert suggest_locator(_by_id("firstName")) == Locator(strategy="label", value="First name")


def test_suggest_locator_uses_role_and_name_for_buttons() -> None:
    assert suggest_locator(_by_id("register")) == Locator(
        strategy="role", value="button", name="Register"
    )


def test_suggest_locator_falls_back_to_testid_then_css_id() -> None:
    assert suggest_locator(_by_id("success-banner")) == Locator(
        strategy="testid", value="success-banner"
    )
    assert suggest_locator(_by_id("email-error")) == Locator(strategy="css", value="#email-error")


def test_matching_elements_finds_label_role_testid_and_id_selectors() -> None:
    dom = register_dom()

    assert [
        e.id for e in matching_elements(Locator(strategy="label", value="Email"), dom) or []
    ] == ["email"]
    role = Locator(strategy="role", value="button", name="Back")
    assert [e.id for e in matching_elements(role, dom) or []] == ["back"]
    testid = Locator(strategy="css", value='[data-testid="success-banner"]')
    assert len(matching_elements(testid, dom) or []) == 1


def test_matching_elements_reports_hallucinated_locator_as_no_match() -> None:
    assert matching_elements(Locator(strategy="label", value="Phone number"), register_dom()) == []


def test_matching_elements_cannot_check_complex_css() -> None:
    locator = Locator(strategy="css", value="form > div:nth-child(2) input")

    assert matching_elements(locator, register_dom()) is None
