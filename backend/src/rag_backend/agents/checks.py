"""Deterministic contract checks run on every agent's output.

LLM agents are validated twice: llm_json.py enforces the JSON *shape*, and these checks
verify the *content* against facts the pipeline already knows (the captured DOM, the
rule ids that exist, the requirement text). Failed "error" checks stop the run; failed
"warning" checks are logged next to the step's output for review.
"""

from __future__ import annotations

from rag_backend.agents.locators import describe, matching_elements
from rag_backend.agents.schemas import (
    BusinessRules,
    CheckResult,
    DomElement,
    Locator,
    TestCase,
    UiAnalysis,
)
from rag_backend.exceptions import AgentsError


def check(name: str, passed: bool, detail: str = "", severity: str = "warning") -> CheckResult:
    return CheckResult(name=name, passed=passed, severity=severity, detail=detail)  # type: ignore[arg-type]


def raise_on_errors(step: str, checks: list[CheckResult]) -> None:
    failed = [c for c in checks if c.severity == "error" and not c.passed]
    if failed:
        details = "; ".join(f"{c.name}: {c.detail}" for c in failed)
        raise AgentsError(f"{step} failed its contract checks: {details}")


def _locator_status(locator: Locator, dom: list[DomElement]) -> tuple[bool, str]:
    matches = matching_elements(locator, dom)
    if matches is None:
        return True, f"{describe(locator)} (css selector, not checked statically)"
    if not matches:
        return False, f"{describe(locator)} matches no captured element"
    return True, f"{describe(locator)} -> {len(matches)} element(s)"


def ui_analysis_checks(ui: UiAnalysis, dom: list[DomElement]) -> list[CheckResult]:
    results = [
        check("has_elements", bool(ui.elements), f"{len(ui.elements)} element(s)", "error"),
    ]
    unknown: list[str] = []
    required_mismatch: list[str] = []
    for element in ui.elements:
        ok, detail = _locator_status(element.locator, dom)
        if element.source == "observed" and not ok:
            unknown.append(f"{element.element_id}: {detail}")
        dom_matches = matching_elements(element.locator, dom) or []
        controls = [e for e in dom_matches if e.tag in ("input", "select", "textarea")]
        if controls and controls[0].required != element.required:
            required_mismatch.append(
                f"{element.element_id}: agent says required={element.required}, "
                f"DOM says {controls[0].required}"
            )
    results.append(
        check(
            "observed_elements_exist_in_dom",
            not unknown,
            "; ".join(unknown) or "every observed element's locator matches the DOM",
        )
    )
    results.append(
        check(
            "required_flags_match_dom",
            not required_mismatch,
            "; ".join(required_mismatch) or "required flags agree with the DOM",
        )
    )
    dom_controls = [e for e in dom if e.tag in ("input", "select", "textarea")]
    covered = {id(e) for el in ui.elements for e in (matching_elements(el.locator, dom) or [])}
    missing = [e.id or e.name or e.tag for e in dom_controls if id(e) not in covered]
    results.append(
        check(
            "all_form_fields_reported",
            not missing,
            f"missing: {', '.join(missing)}" if missing else "every DOM form field is reported",
        )
    )
    return results


def _normalize(text: str) -> str:
    return " ".join(text.lower().replace('"', "").replace("'", "").split())


def business_rules_checks(
    rules: BusinessRules, requirement: str, ui: UiAnalysis
) -> list[CheckResult]:
    ids = [rule.rule_id for rule in rules.rules]
    duplicates = sorted({rule_id for rule_id in ids if ids.count(rule_id) > 1})
    element_ids = {element.element_id for element in ui.elements}
    unknown_fields = [
        f"{rule.rule_id}: {rule.field}"
        for rule in rules.rules
        if rule.field and rule.field not in element_ids
    ]
    normalized_requirement = _normalize(requirement)
    unquoted = [
        rule.rule_id
        for rule in rules.rules
        if _normalize(rule.source_quote) not in normalized_requirement
    ]
    return [
        check("has_rules", bool(rules.rules), f"{len(rules.rules)} rule(s)", "error"),
        check("unique_rule_ids", not duplicates, f"duplicates: {duplicates}" if duplicates else ""),
        check(
            "fields_exist_in_ui",
            not unknown_fields,
            "; ".join(unknown_fields) or "every rule field is a UI element_id",
        ),
        check(
            "source_quotes_in_requirement",
            not unquoted,
            (
                f"quote not found verbatim for: {', '.join(unquoted)}"
                if unquoted
                else "every source_quote appears in the requirement"
            ),
        ),
    ]


def design_checks(
    cases: list[TestCase], rules: BusinessRules, dom: list[DomElement]
) -> list[CheckResult]:
    rule_ids = {rule.rule_id for rule in rules.rules}
    ids = [case.case_id for case in cases]
    duplicates = sorted({case_id for case_id in ids if ids.count(case_id) > 1})
    unknown_rules: list[str] = []
    bad_locators: list[str] = []
    for case in cases:
        missing = [r for r in case.source_rule_ids if r not in rule_ids]
        if missing or not case.source_rule_ids:
            unknown_rules.append(f"{case.case_id}: {missing or 'no rule ids'}")
        for index, step in enumerate(case.steps):
            if step.locator is None:
                continue
            ok, detail = _locator_status(step.locator, dom)
            # expect_text/visible targets may only appear after an action (validation
            # messages are hidden at capture time but their elements exist).
            if not ok:
                bad_locators.append(f"{case.case_id} step {index}: {detail}")
    covered = {r for case in cases for r in case.source_rule_ids}
    uncovered = sorted(rule_ids - covered)
    return [
        check("has_cases", bool(cases), f"{len(cases)} case(s)", "error"),
        check("unique_case_ids", not duplicates, f"duplicates: {duplicates}" if duplicates else ""),
        check(
            "source_rules_exist",
            not unknown_rules,
            "; ".join(unknown_rules) or "every case cites existing rule ids",
        ),
        check(
            "locators_match_dom",
            not bad_locators,
            "; ".join(bad_locators) or "every step locator matches a captured element",
        ),
        check(
            "all_rules_covered",
            not uncovered,
            f"uncovered: {', '.join(uncovered)}" if uncovered else "every rule has a case",
        ),
    ]
