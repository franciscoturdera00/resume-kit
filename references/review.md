# Review before delivering

You wrote the draft, so you are reviewing your own work — which is exactly the setup
where "looks good" gets typed without anything being checked. Defeat that mechanically:
**answer every question below in writing, with the specific evidence**. A verdict with
no quoted bullet, no named requirement, and no line count is not an answer.

Answers are for you, not the user. Report only the outcome and what you changed.

**If subagents are available** (Claude Code's Task tool, or any equivalent), dispatch
part A to a fresh agent with the posting, the tailored JSON, and the master — an agent
that didn't write the draft finds things you won't. Its verdict replaces your part A
answers.

## A. Content — against the posting and the master

Open the posting and the tailored JSON side by side.

1. **Requirement coverage.** List the posting's top 5 requirements. For each, quote the
   bullet or skill line that answers it, or write MISSING. For every MISSING, search the
   master: is there content that covers it? Name the entry and pull it in, or state
   explicitly that the user's background doesn't cover it.
2. **Wasted lines.** Quote any bullet that maps to no requirement in the posting. Each
   one is a line the recruiter spends learning something irrelevant — replace or cut it.
3. **Fidelity.** For every number, title, date, and technology in the draft, name the
   master entry it came from. Anything you cannot trace is a fabrication — remove it now.
   (Merged short roles are fine; see `tailoring.md`.)
4. **Positioning.** Read only the name, headline, and summary. Do they read as a
   candidate for *this* posting, or as a generic engineer? If a competing applicant's
   page would open identically, rewrite it.
5. **Vocabulary.** Does the draft use the posting's words for the things it asks about,
   where the underlying fact genuinely matches?

## B. Visual — against the rendered page

Read `resume.page1.png`. Look at it; don't infer it from the JSON.

6. **Fill.** Is the bottom margin the same as the top, or is there a dead band? Check
   against `fit.json`'s `fill` and `lines_of_room`.
7. **Bullet shape.** Any bullet running to three lines? Any one-line orphan trailing a
   long bullet? Any line ending with a single dangling word?
8. **Balance.** Does one section dominate for no reason? Does the most relevant role
   have the most bullets?
9. **Hierarchy.** Name > sections > entries > bullets, readable at a glance in that
   order?
10. **Scan test.** Look at the page for five seconds. Which three facts land? If they
    aren't the three the posting cares most about, the page is ordered wrong.

## Fix, then re-render

Fix content — bullets, wording, what's included. Never fix by editing the PDF, and never
by fiddling with layout: the renderer owns spacing, sizing, and the one-page guarantee.

Re-render, re-run this checklist, and stop after the second revision even if something
is still imperfect. Then tell the user plainly what's still off — "the posting wants
Kubernetes depth and your master has one bullet on it" is useful; silently shipping a
weak match is not.

## Then report

One short message: the PDF path, company and role, page fill, what you'd flag. If a
gap traces to the master being thin, say so and offer to update it.
