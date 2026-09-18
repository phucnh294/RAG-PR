---
name: write-functionality-doc
description: Write a functionality, architecture, design, investigation or post-mortem document into rag-ai-local/functionality-docs/MMDDYYYY/ with RAG-ready metadata. Use when documenting how a feature works, writing an implementation plan or design note, or when the user says "document this feature", "write a design doc", or "write up the investigation".
---

# Write a functionality / architecture document

Everything that is project knowledge but is **not** a Q&A and **not** a handoff
lands here: implementation plans, design notes, investigations, post-mortems.

## Steps

1. **Resolve today's date once** as `MMDDYYYY` (Rule A). Never guess.
2. **Path:** `rag-ai-local/functionality-docs/<MMDDYYYY>/NN_<slug>.md`
   - Under `functionality-docs/` there are **ONLY date folders** — no feature
     subfolder. The feature name goes in the **slug** and in the `area:` metadata.
   - `NN` = `max(existing NN_ prefix in that date folder) + 1`, zero-padded, starting `01`.
     **List the folder first** — never assume `01`.
   - ✅ `rag-ai-local/functionality-docs/07042026/02_handoff-fixing-test-runner-issues.md`
   - ❌ `rag-ai-local/functionality-docs/corrector-agents/07042026/01_design.md`
3. **Copy** `rag-ai-local/template/functionality_template.md`.
4. **Fill the frontmatter** — core block plus `files`, `version`, `last_updated`,
   `extraction_method`. Frontmatter is **line 1** of the file.
5. **Write the TL;DR** (What / Why / Where / Impact).
6. **Write the body** using the template's sections: what it does → how it works →
   key decisions and why → configuration → gotchas → verification.
7. **Fill `related_docs`** with paths that exist.

## What makes this doc worth indexing

A doc that only restates the code is dead weight — the code is already in the repo
and is more accurate. Put in the things the code **cannot** tell a reader:

- **Key decisions and the alternative that was rejected**, with the reason.
- **Gotchas** — the thing that looks right but isn't, and what actually happens.
- **Configuration effects** — what each setting actually changes at runtime.
- **Verification** — the exact command that proves it works, and the expected output.

## Section self-containment

Each `##` heading becomes a retrieval chunk. Write every section so it still makes
sense **on its own**, without the sections above it. Repeat the subject noun instead
of writing "it" at the start of a section.

## Do not

- Do not create a feature-named subfolder — the date folder is the only level.
- Do not write knowledge `.md` at the repo root or in a code folder (Rule 0).
- Do not skip the `NN_` prefix — it encodes the order work happened that day.
