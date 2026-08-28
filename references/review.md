# Review before delivering

You wrote the draft, so an inline review is self-review, which is exactly the setup
where "looks good" gets typed without anything being checked.

## Use a separate reviewer whenever you can

**Default to dispatching part A to a subagent** (Claude Code's Task tool, or any
equivalent in the host). Give it exactly three things and nothing else:

> You are a hiring manager reviewing a candidate's tailored resume against a specific
> job posting. You did not write it. Attached: the posting, the tailored resume JSON,
> and the candidate's master resume (the full pool the draft was selected from).
> Answer questions 1-5 in `references/review.md` in writing, quoting specific bullets
> and naming specific master entries. Be concrete and unsparing. Return your answers
> and a verdict: ship, or revise (with what to change).

Do not send your reasoning, your draft rationale, or a summary of what you were going
for. A reviewer told what to think finds what it was told. Its verdict replaces your
part A answers; you still do part B yourself, since you are the one who can see the
rendered page.

If the host has no subagents, run part A yourself and defeat rubber-stamping
mechanically: **answer every question in writing, with the specific evidence**. A
verdict with no quoted bullet, no named requirement, and no line count is not an answer.

Answers are for you, not the user. Report only the outcome and what you changed.

## A. Content: against the posting and the master

Open the posting and the tailored JSON side by side.

1. **Requirement coverage.** List the posting's top 5 requirements. For each, quote the
   bullet or skill line that answers it, or write MISSING. For every MISSING, search the
   master: is there content that covers it? Name the entry and pull it in, or state
   explicitly that the user's background doesn't cover it.
2. **Wasted lines.** Quote any bullet that maps to no requirement in the posting. Each
   one is a line the recruiter spends learning something irrelevant. Replace or cut it.
3. **Fidelity.** For every number, title, date, and technology in the draft, name the
   master entry it came from. Anything you cannot trace is a fabrication. Remove it now.
   (Merged short roles are fine, but only through the `roles` list; an umbrella company
   like "Earlier Co-Ops" is a fabricated employer, and `fit.json`'s `parse.structure[]`
   will say so. See `tailoring.md`.)
4. **Positioning.** Read only the name, headline, and summary. Do they read as a
   candidate for *this* posting, or as a generic engineer? If a competing applicant's
   page would open identically, rewrite it.
5. **Voice.** No em dashes anywhere. No filler words (`actually`, `honestly`,
   `genuinely`, `really`, `leverage`, `successfully`, `passionate`, and friends),
   worst of all in the summary. Every sentence carries a fact. `fit.json`'s `prose[]`
   lists what the linter caught, but it only catches the known offenders: read the
   summary yourself and cut any word that could be deleted without losing information.

## B. Visual: against the rendered page

Read `resume.page1.png`. Look at it; don't infer it from the JSON.

6. **Fill.** Is the bottom margin the same as the top, or is there a dead band? Check
   against `fit.json`'s `page_is_full` and `room_at_min_body`, not `fill`: `fill`
   measures the page against the size the fitter happened to choose, so it reads high
   on a page that still has room. If `page_is_full` is `false`, name the specific
   master entry going in next and re-render before reviewing anything else.
7. **Bullet shape.** Any bullet running to three lines? Any one-line orphan trailing a
   long bullet? Any line ending with a single dangling word?
8. **Balance.** Does one section dominate for no reason? Does the most relevant role
   have the most bullets?
9. **Hierarchy.** Name > sections > entries > bullets, readable at a glance in that
   order?
10. **Scan test.** Look at the page for five seconds. Which three facts land? If they
    aren't the three the posting cares most about, the page is ordered wrong.

## Fix, then re-render

Fix content: bullets, wording, what's included. Never fix by editing the PDF, and never
by fiddling with layout. The renderer owns spacing, sizing, and the one-page guarantee.

Re-render, re-run this checklist, and stop after the second revision even if something
is still imperfect. Then tell the user plainly what's still off. "The posting wants
Kubernetes depth and your master has one bullet on it" is useful; silently shipping a
weak match is not.

## Then report

One short message: the .docx path (the editable deliverable), the PDF next to it,
company and role, page fill, what you'd flag. If a gap traces to the master being thin,
say so and offer to update it.
