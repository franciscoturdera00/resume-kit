# resume-kit

A Claude skill that keeps a **master resume** for you and generates **tailored one-page
resume PDFs** for specific job postings.

You give it a job posting (URL or pasted text). It selects from everything it knows
about your career, rewrites it in that posting's vocabulary, renders a PDF, looks at the
rendered page, and revises. The master resume persists between sessions and grows as you
ship things — so the fifth resume is better than the first.

No API keys. No accounts. No services. Your resume never leaves your machine.

## Install

Copy this directory into your skills folder:

```bash
# available in every project
cp -r resume-kit ~/.claude/skills/resume-kit

# or just one project
cp -r resume-kit <project>/.claude/skills/resume-kit
```

Then start a session and say *"set up my resume"* or *"tailor my resume for this job:
<url>"*.

Recommended: install [`uv`](https://docs.astral.sh/uv/) (`curl -LsSf
https://astral.sh/uv/install.sh | sh`). The renderer's dependencies then install
themselves on first run. Without uv, run `bash scripts/setup.sh` once.

## First run

If you have a resume, have it ready as a **PDF** (or text you can paste) — the skill
reads it and converts it. If you don't, it interviews you. Either way it ends with a
validated `master_resume.json` and tells you what's in it.

The master holds more than a resume does: 2-3 headline and summary variants for
different kinds of roles, tags on every bullet, and priorities. That's what makes
tailoring produce something specific rather than a reformat.

## Where your data lives

Everything stateful lives outside the skill, so updating or re-sharing the skill never
touches your data:

```
~/.resume-kit/
  master_resume.json                     # the source of truth
  backups/                               # a snapshot before every edit
  output/<company>/<role>/
    resume.pdf                           # the deliverable
    resume.page1.png, fit.json, tailored_resume.json, job_description.txt
```

Point it elsewhere with `python3 scripts/kit.py set-home <dir>` (or `$RESUME_KIT_HOME`).

## Day to day

- *"Tailor my resume for this posting: <url>"* — the main loop.
- *"Add this to my resume: I shipped X"* — additive update, with a backup first.
- *"Is my resume kit working?"* — `python3 scripts/kit.py doctor`.

## How the page gets to one page

`scripts/render.py` does the layout itself: it measures the content, picks the
typographic scale that fills exactly one page, and only trims if writing can't be made
to fit — reporting whatever it dropped. So "one page" is a property of the renderer, not
a thing the model has to keep re-checking. The model's job is content: what goes on the
page, and whether the page answers the posting.

## Where it runs

| | Works? |
|---|---|
| Claude Code (CLI, desktop, IDE) | Yes — the primary target |
| Cowork | Yes, if the workspace persists files and can run Python |
| claude.ai chat | No — nothing persists between conversations, so there's no master resume to build on |

Requirements: Python 3.10+, and network access the first time dependencies install.

## Layout

```
SKILL.md                          entry point — routing and the tailoring loop
references/
  onboarding.md                   first run: import a resume, or interview
  master-resume.md                schema + additive update rules
  tailoring.md                    how to write the tailored JSON
  review.md                       the checklist before anything is delivered
scripts/
  render.py                       tailored JSON -> one-page PDF (+ PNG, metrics)
  kit.py                          paths, validate, backup, doctor (stdlib only)
  setup.sh                        dependency install without uv
assets/
  master_resume.example.json      complete valid master (fictional person)
  tailored_resume.example.json    complete valid tailored input
  fonts/                          Carlito (SIL OFL 1.1) — embedded in every PDF
```

## Credits

Bundles the [Carlito](https://github.com/googlefonts/carlito) typeface, licensed under
the SIL Open Font License 1.1 (`assets/fonts/OFL.txt`). Rendering uses
[reportlab](https://www.reportlab.com/) and [pypdfium2](https://github.com/pypdfium2-team/pypdfium2).
