---
name: write-handoff-doc
description: Write a session handoff document that lets the NEXT session start cold and resume the work without asking questions. Use at the end of a work session, before compacting or clearing context, or when the user says "handoff", "wrap up this session", "save where we are", or "I'm going to start a new session".
---

# Write a session handoff document

**Purpose: kill the long chat session.** Context is finite. A session that runs for
hours degrades, and its knowledge dies when the window closes. The fix is not a longer
session — it is a handoff doc that makes the next session *session-free*.

## When to run this

- At the end of a work session — **before** compacting/clearing, not after.
- Whenever work is being paused with anything unfinished.
- Before a risky refactor, so there is a known-good description of the current state.

## Steps

1. **Resolve today's date once** as `MMDDYYYY` from `currentDate` (Rule A in
   `.claude/rules/file-organization.md`). Never guess it.
2. **Pick the path:** `rag-ai-local/functionality-docs/<MMDDYYYY>/NN_handoff-<slug>.md`
   where `NN` = `max(existing NN_ prefix in that folder) + 1`, zero-padded.
   List the folder first — do not assume `01`.
3. **Copy** `rag-ai-local/template/session_handoff_template.md` and fill it in.
4. **Gather the real state — do not write from memory:**
   - `git status` + `git log --oneline -5` → `branch`, `commit`, files changed
   - the last test/build command and its ACTUAL output → verification table
   - the open items, each with `file:line`
5. **Fill the frontmatter completely.** `type: session-handoff`, honest `status`,
   `next_action` as one concrete sentence, `supersedes:` = the previous handoff
   filename (and set that older file's `status: superseded`).
6. **Write the TL;DR** (What / Why / Where / Impact) — four real sentences.
7. **Add the one-line pointer** to any index the project keeps.

## The section that actually matters

Everything except **"CONTEXT THE NEXT SESSION CANNOT DERIVE FROM CODE"** can be
re-read from the repo. That section is the only irreplaceable one. Put in it:

- **Decisions + the reason**, and the alternative that was rejected and why.
- **Traps**: the thing that looks right but isn't, and what actually happens.
- **Ground truth**: a fact verified from logs/DB, and *where* it was verified.

## Quality bar

> A new session, given ONLY this file and the repo, can resume the work without
> asking a single question.

Reject these:
- "Made good progress" → give a metric: `56/67 (83.6%)`.
- "Some tests fail" → list them with file:line and the suspected cause.
- "Continue the refactor" → name the ONE first action and the exact command.

## Do not

- Do not write it after compacting — the details are already gone.
- Do not delete the previous handoff; mark it `superseded` so history survives.
- Do not put it anywhere except the date folder (Rule C).
