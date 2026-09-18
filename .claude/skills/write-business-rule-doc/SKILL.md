---
name: write-business-rule-doc
description: Extract business rules out of source code and document them with trust levels and code evidence, into rag-ai-local/functionality-docs/MMDDYYYY/. Use when the user says "what are the business rules", "reverse engineer the rules from this code", "document the validation logic", or when onboarding onto an undocumented legacy system.
---

# Extract and document business rules from code

This produces the most dangerous kind of document in the corpus: rules read out of an
implementation. It describes **what the system does**, which is not necessarily
**what the business intended**. The whole skill exists to keep that distinction visible.

## Steps

1. **Resolve today's date once** as `MMDDYYYY` (Rule A).
2. **Path:** `rag-ai-local/functionality-docs/<MMDDYYYY>/NN_<slug>-business-rules.md`
   (`NN` = next prefix in that date folder — list it first).
3. **Copy** `rag-ai-local/template/business_rule_template.md`.
4. **Capture the code version FIRST** — `git rev-parse --short HEAD`. A business-rule
   doc without the commit it was extracted from cannot be re-verified later, and
   becomes untrustworthy the moment the code changes.
5. **Read the actual code.** Validators, guards, `if` branches, DB constraints,
   defaults, and error paths. Do not infer rules from names or comments alone.
6. **Write one `BR-NNN` block per rule** with: the rule in *business* language,
   a trust tag, the source `file:line`, the minimal code snippet as evidence,
   and the edge cases observed.
7. **Fill the rules index table** at the bottom.

## Trust tags — required on every rule

| Tag | Meaning | When to use |
|-----|---------|-------------|
| `CONFIRMED` | verified against a spec, ticket, or stakeholder | you have a non-code source |
| `INFERRED` | read from code only — plausible, unverified | the default; be honest |
| `SUSPECT` | looks like a bug rather than an intended rule | behaviour is inconsistent, or an edge case is clearly unhandled |

**`SUSPECT` is the most valuable output of this skill.** Reverse-engineering is the
moment latent bugs become visible — a rule that makes no business sense is usually a
defect that has been running in production unnoticed. Never silently normalise it
into a sensible-sounding rule.

## Write rules in business language, not code language

- ❌ "If `status != null && status.equals("A")` then `setEligible(true)`"
- ✅ "An account is eligible only while its status is Active. A missing status is
  treated as not eligible." — `INFERRED`, `AccountValidator.java:88`

## Do not

- Do not present inferred rules as fact — the trust tag is mandatory.
- Do not omit the code snippet; the evidence is what makes the doc auditable.
- Do not extract rules without recording `source_code_version`.
