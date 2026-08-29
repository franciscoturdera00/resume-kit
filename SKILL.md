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

- `master_exists: true` means route by what was asked:
  - tailor for a job, see **Tailoring** below
  - record new work or fix a detail, see `references/master-resume.md`
  - "is this working?" or something broke, run `python3 <skill-dir>/scripts/kit.py doctor`
- `master_exists: false` does **not** mean first run. Go to **When the master is missing** first.

## When the master is missing

`master_exists: false` means the master is not in the home directory *right now*. That is not the same as the user never having built one, and the two get confused constantly, because a home directory is only as durable as the machine under it. Cloud agent sessions, containers, CI runners, and reinstalls all hand you an empty filesystem that looks exactly like a fresh install.

Rebuilding a master that already exists is the worst thing this skill can do. It costs the user an hour of interview they already sat through, and the replacement is worse than the original, because they will not remember every number the first pass captured.

So look before you conclude:

```bash
python3 <skill-dir>/scripts/kit.py locate
```

It searches the home, the working directory, the usual document and cloud-sync folders, and the staging paths agent sandboxes use for connected folders. Route on `verdict`:

| `verdict` | What it means | Do this |
|---|---|---|
| `adopt` | One usable master found outside the home | `kit.py adopt <path>`, then carry on with what was asked |
| `ambiguous` | Several usable masters | Show the user paths, dates, and role counts. Let them choose. Never merge silently |
| `found_but_invalid` | Files exist, none validate | Read the errors and repair. A broken master is worth more than a fresh interview |
| `none_found` | Nothing on this filesystem | Keep going below. Do not onboard yet |

`none_found` still isn't proof. `locate` only sees this filesystem, and the user's own storage may not be on it. Before onboarding, check whatever this host gives you: folders the user connected to the session, mounted or synced directories, anything they have attached to the conversation. Then ask them plainly: *have you used this before, and is there a `master_resume.json` somewhere I should load?* One question costs a sentence. Guessing wrong costs an hour.

Only when that comes back empty is it a genuine first run. Then read `references/onboarding.md` and build the master. Do not tailor against a resume that doesn't exist, and do not invent one.

**If the home is ephemeral, fix that before filling it.** When the session's filesystem will not survive (a cloud sandbox, a container), the master must live somewhere the user keeps: a connected folder, a synced directory, anywhere they store documents.

```bash
python3 <skill-dir>/scripts/kit.py set-home <that-folder>
```

Where the skill can only reach the user's storage through a file-transfer bridge rather than a real path, the home stays local and every edit has to be written back to the user's copy before the session ends. Say so out loud when you finish.

**Then leave a note in that folder, every time.** This is what stops the next session repeating the search you just did:

```bash
python3 <skill-dir>/scripts/kit.py note <the-durable-folder>
# folder only reachable over a bridge? write it locally and transfer it yourself:
python3 <skill-dir>/scripts/kit.py note <the-durable-folder> --out ./CLAUDE.md
```

It writes a `CLAUDE.md` explaining where the master is, that an empty home is not a first run, and how to load and save it. Running it again updates its own block and leaves the rest of an existing `CLAUDE.md` alone, so it is safe to call on every session that touches the master. Do it after onboarding, after adopting, and after any session where the master's location changed.

## Tailoring

**1. Get the job description.** For a URL, try WebFetch first; if it returns JS or boilerplate instead of the posting, use a browser tool; if that fails, ask the user to paste it. Pasted text is already fine. Strip site chrome (nav, "Apply now", related jobs) but keep the posting's own wording verbatim, since you are about to match its vocabulary.

**2. Read the whole master resume.** Not a grep. Selection quality depends on seeing every bullet, tag, and project version.

**3. Write the tailored JSON.** Rules, voice, and output schema: `references/tailoring.md`.
The summary is written fresh for every posting, never copied from the master. The
Highlights block is your call per posting: on when it puts the posting's top three facts
where a top-down reader meets them first, off when the lead role already does that.
Ask the user once whether they want the posting's keywords bolded on the page; if yes,
include the optional top-level `bold_keywords` list (4-8 exact terms that appear in your
prose), and if not, leave the field out. Save to
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

**6. Fill the page, then revise at most twice.** A `ROOM` warning means the page still has capacity: add the next strongest content from the master and re-render, repeating until the warning clears or the next addition causes a trim. Filling the page is not a revision, it is finishing the draft, so it does not count against the two. Then fix content, re-render, re-review, and stop, reporting honestly what you couldn't fix.

**7. Log it.**

```bash
python3 <skill-dir>/scripts/kit.py log --dir <out> --url <posting-url>
```

This records company, role, headline and keywords in `<home>/applications.json` with
status `generated`. When the user says they actually sent it, update the status:
`kit.py log --company X --role Y --status applied`. Statuses run `generated`, `applied`,
`screen`, `interview`, `onsite`, `offer`, `rejected`, `ghosted`, `withdrawn`.

The log is the only thing in the kit that knows what happened *after* the page was
rendered. Read it (`kit.py applications`) before tailoring, so a job already applied to
is not silently redone, and so the resumes that drew replies are visible when choosing
how to frame the next one. `kit.py backfill` seeds it from resumes generated before the
log existed.

**8. Report** the .docx path, the PDF beside it, company and role, page fill, and anything the review flagged. Don't paste the JSON.

### Reading the metrics

| Signal | Meaning | Action |
|---|---|---|
| `warnings: []`, `page_is_full: true` | Nothing was dropped, nothing more fits | Ship it |
| `ROOM` | The page has capacity left | Add content from the master and re-render, until it clears |
| `prose[]` non-empty | Em dash or filler words in the text | Rewrite those fields, they are house-style violations |
| `UNDERFILLED` | Thin content, empty space at the bottom | Add a bullet or project; `room_at_min_body` says how much fits |
| `TRIMMED` | The renderer dropped content to fit | Rewrite shorter yourself, you choose better than it does |
| `BOLD` | A bold keyword never matches, or the list is too long | Drop the keyword or rewrite the text; keep 4-8 terms |
| `OVERFLOW` | Doesn't fit even trimmed | Cut a whole entry, re-render |
| `docx_pages` > 1 | Word lays it out longer than the PDF does | Cut content; do not hand over the .docx |
| `ROOM` still set after adding everything relevant | Master is thin | Say so, and offer to enrich the master |
| `PARSE` (structure) | An entry carries facts in a field that names nothing, usually an umbrella company like "Earlier Co-Ops" | Rewrite that entry with the `roles` list; see `tailoring.md` |
| `PARSE` (missing) | A fact in the JSON does not come back out of the PDF text | The layout welded it to a neighbour. Report it; do not hand the file over as ATS-safe |
| `HIGHLIGHTS` | More than three given, one has no `source`, or one restates a bullet below it | Cut to three, add the source, or rewrite it to say something the chronology does not |
| `SUMMARY` | Missing, one sentence, or more than five | Write it to the shape in `tailoring.md`: title and years, strengths with one number, what you bring |

`scale` is the typographic size the fitter settled on, and `body_pt` is what that means in points. Body text never renders below `min_body_pt` (9.5pt by default, override with `--min-body-pt`). Once the floor is reached the renderer trims content instead of shrinking type, so `TRIMMED` at the lowest scale means the page is genuinely too full: cut content, do not reach for smaller type. Margins are 0.5in on all four sides, in both the PDF and the .docx.

**Read `room_at_min_body`, not `fill`.** The fitter takes the largest scale that fits, so `fill` measures the page against whatever size it settled on, and a page at `fill` 0.96 can still have four or five lines of unused capacity: the fitter will drop a rung and buy that space with type size once there is content to justify it. `room_at_min_body` is the honest number, the lines that still fit at the floor, and `page_is_full` is that number being under two. A page is done when `page_is_full` is `true` and `trimmed` is empty. Do not stop earlier because `fill` looked high.

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
- **One page, and a full one.** Both halves are enforced: the renderer guarantees the page, and `ROOM` says when it is not yet full. An underfilled page wastes the only page the candidate gets, so keep adding the strongest remaining content until the next item would trim. Full never means padded: everything on the page still has to earn its line against the posting.
- Generated resumes are disposable; the master is not.
