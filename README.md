# resume-kit

A Claude skill that keeps a **master resume** for you and generates **tailored one-page
resumes** for specific job postings, as an editable `.docx` with a matching PDF.

You give it a job posting (URL or pasted text). It selects from everything it knows
about your career, rewrites it in that posting's vocabulary, renders the document, looks
at the rendered page, and revises. The master resume persists between sessions and grows
as you ship things, so the fifth resume is better than the first.

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

If you have a resume, have it ready as a **PDF** (or text you can paste). The skill
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
    resume.docx                          # the deliverable, edit it however you like
    resume.pdf                           # same document, and what most applications want
    resume.page1.png, fit.json, tailored_resume.json, job_description.txt
```

Point it elsewhere with `python3 scripts/kit.py set-home <dir>` (or `$RESUME_KIT_HOME`).

## Day to day

- *"Tailor my resume for this posting: <url>"* is the main loop.
- *"Add this to my resume: I shipped X"* does an additive update, with a backup first.
- *"Is my resume kit working?"* runs `python3 scripts/kit.py doctor`.

## How the page gets to one page

`scripts/render.py` does the layout itself: it measures the content, picks the
typographic scale that fills exactly one page, and only trims if the writing can't be
made to fit, reporting whatever it dropped. So "one page" is a property of the renderer,
not a thing the model has to keep re-checking. The model's job is content: what goes on
the page, and whether the page answers the posting.

The .docx is built from the same solved geometry and names Calibri, which is
metric-compatible with the Carlito the PDF embeds, so Word breaks the lines where the
measured layout broke them. Where LibreOffice is installed, `--verify-docx` confirms the
page count rather than assuming it.

## Where it runs

| | Works? |
|---|---|
| Claude Code (CLI, desktop, IDE) | Yes, the primary target |
| Cowork | Yes, with one setup step: see below |
| claude.ai chat | No. Nothing persists between conversations, so there's no master resume to build on |

Requirements: Python 3.10+, and network access the first time dependencies install.

**Cowork:** sub-agents are supported, so the review step gets an independent reviewer.
The thing to get right is where the master lives. Cowork sessions run in the cloud by
default and each session gets its own sandbox that is destroyed when the session ends, so
a master resume written to `~/.resume-kit` inside that sandbox does not survive. Point the
home at a location that persists (a connected folder in local execution, or a folder in
your Claude account's files) before onboarding:

```bash
python3 scripts/kit.py set-home <persisted-folder>
```

Run `python3 scripts/kit.py paths` at the start of a later session; if `master_exists` is
false when you know you built one, the home is pointing at ephemeral storage.

## Layout

```
SKILL.md                          entry point: routing and the tailoring loop
references/
  onboarding.md                   first run: import a resume, or interview
  master-resume.md                schema + additive update rules
  tailoring.md                    how to write the tailored JSON
  review.md                       the checklist before anything is delivered
scripts/
  render.py                       tailored JSON -> one-page .docx + PDF (+ PNG, metrics)
  docx_out.py                     the editable copy, from the same solved geometry
  prose.py                        house-style lint: no em dashes, no filler
  kit.py                          paths, validate, backup, doctor (stdlib only)
  setup.sh                        dependency install without uv
assets/
  master_resume.example.json      complete valid master (fictional person)
  tailored_resume.example.json    complete valid tailored input
  fonts/                          Carlito (SIL OFL 1.1), embedded in every PDF
```

## Credits

Bundles the [Carlito](https://github.com/googlefonts/carlito) typeface, licensed under
the SIL Open Font License 1.1 (`assets/fonts/OFL.txt`). Rendering uses
[reportlab](https://www.reportlab.com/) and [pypdfium2](https://github.com/pypdfium2-team/pypdfium2).
