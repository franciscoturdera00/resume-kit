---
name: resume-kit
description: Keep a stateful master resume and generate tailored one-page resumes from it, as an editable .docx plus a matching PDF. Handles first-run setup by importing an existing resume or interviewing the user, then tailors to a specific job posting (URL or pasted text) and renders locally. Self-contained, with no API keys, no external services, and no messaging integrations. Use when someone asks to tailor a resume for a job, set up or import their resume, or record new work on their master resume.
---

# resume-kit

Two long-lived things, one throwaway thing:

- **The master resume** (`master_resume.json`), everything true about the user's career, tagged. Grows over time. Never trimmed to fit a page.
- **The state directory**, where the master, backups, and generated resumes live. Outside this skill directory, so updating or re-sharing the skill never touches the user's data.
- **A tailored resume**, one job, one document, derived from the master. Disposable; regenerate rather than hand-edit.

You are the writer and the reviewer. `scripts/render.py` owns the page: it lays out the document, guarantees one page, and reports how full it is. Never ask the user for an API key, there isn't one.

## Every invocation starts here

```bash
for d in ~/.claude/skills/resume-kit ./.claude/skills/resume-kit .claude/skills/resume-kit; do
  [ -f "$d/scripts/kit.py" ] && python3 "$d/scripts/kit.py" paths && break
done
```

(If you already know this skill's directory, just run `python3 <that-dir>/scripts/kit.py paths`.)

Stdlib only, always runs. It prints `master`, `master_exists`, `output_dir`, and `kit_root`. **`kit_root` is this skill's absolute directory; substitute it for `<skill-dir>` everywhere below.** Surface any `warnings` it returns.

- `master_exists: false` means **first run**. Read `references/onboarding.md` and build the master before anything else. Do not tailor against a resume that doesn't exist yet, and do not invent one.
- `master_exists: true` means route by what was asked:
  - tailor for a job, see **Tailoring** below
  - record new work or fix a detail, see `references/master-resume.md`
  - "is this working?" or something broke, run `python3 <skill-dir>/scripts/kit.py doctor`

## Tailoring

**1. Get the job description.** For a URL, try WebFetch first; if it returns JS or boilerplate instead of the posting, use a browser tool; if that fails, ask the user to paste it. Pasted text is already fine. Strip site chrome (nav, "Apply now", related jobs) but keep the posting's own wording verbatim, since you are about to match its vocabulary.

**2. Read the whole master resume.** Not a grep. Selection quality depends on seeing every bullet, tag, and project version.

**3. Write the tailored JSON.** Rules, voice, and output schema: `references/tailoring.md`. Save to
`<output_dir>/<company-slug>/<role-slug>/tailored_resume.json`, and the cleaned posting next to it as `job_description.txt`.

**4. Render.**

```bash
uv run <skill-dir>/scripts/render.py \
  --tailored <out>/tailored_resume.json --out-dir <out> [--verify-docx]
```

`uv` installs the dependencies on first use. No uv? See **Dependencies** below. This writes `resume.docx` (the deliverable, editable by the user), `resume.pdf` (the same document, proof of fit, and what most applications want), `resume.page1.png`, and `fit.json`.

Pass `--verify-docx` on the final render: where LibreOffice is installed it lays the .docx out and confirms the page count, and it says so when it can't.

**A non-zero exit code means the output is not deliverable.** Check `deliverable` in the metrics; never hand over a resume when it is `false`.

**5. Review before showing anything.** Read the PNG (actually look at it) and work through `references/review.md`, which dispatches the content half to a separate reviewer where the host supports one. Skipping this step is how a resume that reads as generic reaches the user.

**6. Revise at most twice.** Fix content, re-render, re-review. Then stop and report honestly, including what you couldn't fix.

**7. Report** the .docx path, the PDF beside it, company and role, page fill, and anything the review flagged. Don't paste the JSON.

### Reading the metrics

| Signal | Meaning | Action |
|---|---|---|
| `warnings: []`, `fill` 0.90-1.00 | Page is full, nothing was dropped | Ship it |
| `prose[]` non-empty | Em dash or filler words in the text | Rewrite those fields, they are house-style violations |
| `UNDERFILLED` | Thin content, empty space at the bottom | Add a bullet or project; `lines_of_room` says how much fits |
| `TRIMMED` | The renderer dropped content to fit | Rewrite shorter yourself, you choose better than it does |
| `OVERFLOW` | Doesn't fit even trimmed | Cut a whole entry, re-render |
| `docx_pages` > 1 | Word lays it out longer than the PDF does | Cut content; do not hand over the .docx |
| `fill` < 0.85 after two revisions | Master is thin | Say so, and offer to enrich the master |

`scale` is the typographic size the fitter settled on. Low values (0.88-0.91) mean the page is packed, which is a signal to write tighter, not a defect.

## Dependencies

`uv` is the zero-setup path (`uv run` reads the deps declared inside `render.py`). Otherwise:

```bash
bash <skill-dir>/scripts/setup.sh    # builds <home>/.venv, prints the python to use
```

Both need network access once. `reportlab` is required. `python-docx` writes the editable copy and `pypdfium2` produces the PNG preview; without either, rendering still works and `render.py` says what was skipped.

## Rules

- **The master is the only source of facts.** Tailoring rewrites emphasis and wording, never facts. No invented metrics, employers, dates, or technologies, not even plausible ones.
- **No em dashes, no filler words**, in the resume and in anything written to the master. See `references/tailoring.md`; `render.py` and `kit.py validate` both lint for it.
- **Back up before editing the master**: `python3 <skill-dir>/scripts/kit.py backup`, then edit, then `validate`.
- **Never write user data into the skill directory.** Everything stateful goes to the home directory `kit.py paths` reports. `assets/*.example.json` are read-only references, not the user's resume.
- **One page.** Not a preference, the renderer enforces it.
- Generated resumes are disposable; the master is not.
