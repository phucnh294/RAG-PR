---
name: write-qanda-doc
description: Write a Q&A knowledge document into rag-ai-local/QandA/ with RAG-ready metadata and specific, searchable questions. Use after investigating and answering a question, debugging an issue, or when the user says "write this up as Q&A", "document what we found", or "save this answer".
---

# Write a Q&A document

Q&A files are the highest-traffic part of the RAG corpus — they are what people
actually search. A Q&A written with vague questions pollutes the index instead of
serving it.

## Steps

1. **Resolve today's date once** as `MMDDYYYY` (Rule A). Never guess.
2. **Path:** `rag-ai-local/QandA/<MMDDYYYY>_<Title_Case_Topic>.md`
   - The topic goes in the filename. Do **not** put "QandA" in it — the folder says that.
   - ✅ `07042026_Agentic_Crawler_Replay_Trap.md`
   - ❌ `QandA_07042026.md`
3. **ONE file per distinct topic.** A day can have several. Never append to another
   topic's file — make a new one. Number questions `Q1, Q2, …` **per file**.
4. **Copy** `rag-ai-local/template/QandA_template.md`.
5. **Fill the frontmatter** — the full core block plus the Q&A extras
   (`issue_type`, `severity`, `resolution_date`). Frontmatter is **line 1** of the file.
6. **Write the TL;DR** (What / Why / Where / Impact).
7. **Write the questions** under the rule below.
8. **Fill `related_docs`** with paths that actually exist.

## The rule that makes or breaks the file: SPECIFIC, SEARCHABLE QUESTIONS

Replace every "this", "it", "the problem", `[SPECIFIC ISSUE]` with:

- **Real technology names** — `AtomicLong`, `JPA`, `Playwright`, `pgvector`
- **Real components** — `Tester_Assertion_Corrector`, `MockInformaticaService`
- **Concrete error types** — `ORA-01031`, `NoSuchElementException`, `404`
- **Actual behaviours** — Deal Number Duplication, Button Disabled, Thread Leak

**Why:** RAG retrieval matches on keywords. A generic question like
*"Why did this happen?"* matches EVERY Q&A doc in the corpus — because every doc
contains those words — so retrieval returns noise and the answer is useless.

| ❌ Rejected | ✅ Accepted |
|------------|------------|
| "Why did this happen?" | "Why did `AtomicLong` cause Deal Number duplication under concurrent submits?" |
| "How did we fix it?" | "How did scoping the ground-truth check to `assert_*` steps stop the healer discarding valid fill fixes?" |
| "What was the config issue?" | "Why does `env_file` NOT interpolate `${POSTGRES_HOST}` in Docker Compose?" |

## Answer shape

Lead with the conclusion, then the proof:

```markdown
**Answer:** [conclusion first]

**Evidence:**
​```
[the log line / error / query output that PROVES it]
​```

**Root cause:** [one sentence]
**Fix:** `path/to/file.py:123` — [what changed]
```

## Do not

- Do not write a Q&A with no evidence block — an unverified answer in a RAG corpus
  is worse than no answer, because it will be retrieved and cited confidently.
- Do not create the file anywhere except `rag-ai-local/QandA/`.
- Do not skip the frontmatter — an unindexed doc is invisible to the RAG.
