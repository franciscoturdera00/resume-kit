# First run: building the master resume

**Stop if you have not run `kit.py locate` yet.** An empty home directory is not evidence
of a first run, only of an empty home directory. Follow **When the master is missing** in
`SKILL.md` first: search, check any connected or synced folders this host exposes, and ask
the user outright whether they have used this kit before. Everything below assumes all
three came back empty. Re-running this interview on top of a master that already exists
destroys work the user has already done, and they will not remember the details well
enough to reproduce it.

Goal: a validated `master_resume.json` in the state directory. Everything else in this
skill depends on it, so this step is worth doing slowly and asking real questions.

Two paths. Ask which one applies:

- **Import.** They have a resume already (PDF, or text they can paste). Fastest, and
  usually better, because the facts are already settled.
- **Interview.** No resume, or the one they have is badly out of date.

Either way, run `python3 <skill-dir>/scripts/kit.py init` first to create the directories.

**Check that the home survives the session before you fill it.** Some hosts give each
session a fresh sandbox that is destroyed when the session ends (Cowork cloud sessions
work this way), and a master resume written there is gone by the next conversation. If
the host works like that, ask the user for a folder that persists (a connected folder, a
synced directory, anywhere they keep documents) and pin it first:

```bash
python3 <skill-dir>/scripts/kit.py set-home <folder>
```

Where the host can only reach the user's storage through a file-transfer bridge rather
than a real path, `set-home` cannot help. Keep the home local, and write the finished
master back to the user's folder before the session ends, every time it changes. Leave a
short note in that folder saying where the master is and that an empty home is not a
first run, so the next session loads it instead of asking these questions again.

An interview that has to be repeated because the file evaporated is the worst outcome
this skill has.

## Path A: import an existing resume

1. Ask for the file path or the pasted text. **PDF is the format to ask for**, because you can
   read PDFs directly. You cannot read `.docx`; if that's all they have, ask them to
   export a PDF (Word/Pages/Google Docs all do this in one step) or paste the text.
2. Read the file. Extract every fact: contact details, each role with exact company,
   title, location, and dates, every bullet, projects, education, certifications.
3. Convert to the schema in `master-resume.md`. This is a transcription job. Do not
   improve, embellish, or invent numbers while converting. If a bullet is weak, keep it
   weak for now and flag it in step 5.
4. Fill the parts a one-page resume doesn't contain (see **What the file needs beyond a
   resume** below). This is where the interview questions come back.
5. Show the user anything you had to guess or drop, and ask about weak bullets: "your
   resume says 'helped with deployments'. What actually happened, and did it change a
   number?" Their answer is the bullet worth keeping.

## Path B: interview

Work through these in order. Keep it conversational, one topic at a time, and stop when
you have enough. A thin honest master beats a padded one.

1. **Contact.** Name, email, phone, location, LinkedIn/GitHub/portfolio (whichever they
   actually use).
2. **Each role, most recent first.** Company, title, location, start and end (month +
   year), then: what did you own, what did you build, what broke and how did you fix it,
   what got faster/cheaper/bigger and by how much? Push once for numbers, accept "I don't
   know" the second time.
3. **Projects.** Anything they'd point at in an interview: side projects, open source,
   big internal systems. Tech used and what it does.
4. **Education.** Degree, institution, location, years, honors.
5. **Skills.** Group by category (languages, infrastructure, data, practices, whatever
   fits them). Only things they'd defend in an interview.
6. **Certifications.** Optional, skip if none.

Ask about numbers as a matter of course ("how many users?", "how long did it take
before?"), but never fabricate one to fill the gap. A qualitative bullet
("multi-tenant", "production", "end-to-end") is honest; an invented metric is a lie the
user has to defend in an interview.

## What the file needs beyond a resume

The master isn't a resume. It's the pool a resume gets selected from. Three things a
normal resume doesn't have, and all three are load-bearing:

**Title and summary variants (2-3 of each).** Different roles need different framing.
Someone applying to both platform and AI roles needs a headline for each. One variant
means every tailored resume opens the same way and positions them for nothing in
particular. Derive them from the directions the user wants to apply in, so ask.

**Tags, on everything.** Bullets, projects, titles, and summaries all get `tags`.
Selection runs on tags; an untagged bullet is invisible to tailoring, no matter how good
it is. Use lowercase-hyphenated tags, reuse a tag the file already has rather than
coining a synonym (`ci-cd` and `cicd` split one concept into two dead ones), and give
each bullet 3-6 tags: technologies, domain, and the kind of work.

**Priorities.** `priority: 1` is career-defining, `2` is solid, `3` is filler for a thin
page. Used to break ties when several entries match equally.

## Finishing

```bash
python3 <skill-dir>/scripts/kit.py validate
```

Fix every error; read the warnings and fix the ones that are real (a flagged tag typo is
always real, since it quietly removes that content from every future tailoring pass).

Then leave the note, so the work you just did is findable next time:

```bash
python3 <skill-dir>/scripts/kit.py note <the-folder-holding-the-master>
```

If that folder is only reachable over a file-transfer bridge, add `--out ./CLAUDE.md` and
transfer the result yourself. Skipping this is how the next session ends up running this
interview again.

Then show the user a short summary of what's in the file: how many roles, bullets,
projects, and which title variants exist. Offer to generate a resume for a specific job
if they have one in mind.

`assets/master_resume.example.json` is a complete, valid file to check shape against.
Never copy its content into a real master. That person doesn't exist.
