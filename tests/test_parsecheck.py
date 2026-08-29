#!/usr/bin/env python3
"""Tests for the parse gate.

Run:  python3 tests/test_parsecheck.py
      uv run --with reportlab --with pypdfium2 --with python-docx \\
             python tests/test_parsecheck.py     # includes the round trip

A gate that silently stops firing is worse than no gate, because the clean
`parse` block in fit.json goes on saying the page is fine. Every check here
exists to prove one half of that: the gate fires when it should, and stays quiet
when it should. The second half matters as much as the first, since a check that
cries wolf gets ignored within a week.

The structural tests are standard library. The round trip needs the renderer's
dependencies and skips itself, loudly, when they are missing.
"""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import parsecheck as pc  # noqa: E402
import prose  # noqa: E402

FAILURES = []

# render.py imports reportlab at module scope, so anything reaching into it is
# gated on the renderer's dependencies being present. parsecheck and prose are
# standard library and always run, which is what keeps this file useful as a
# quick local check.
try:
    import reportlab  # noqa: F401
    import pypdfium2  # noqa: F401
    HAVE_DEPS = True
except ImportError:
    HAVE_DEPS = False


def check(name: str, condition: bool, detail: str = ""):
    if condition:
        print(f"  ok    {name}")
    else:
        print(f"  FAIL  {name}{(': ' + detail) if detail else ''}")
        FAILURES.append(name)

check("a pronoun in the summary is flagged",
      any("pronoun" in m for m in prose.lint({"summary": "Leaves them able to build without him."})))
check("a pronoun-free summary is quiet",
      prose.lint({"summary": "Engineer who ships. Its API stays up."}) == [])
check("highlight objects lint their text, not their source",
      prose.lint({"highlights": [{"text": "Fine text", "source": "My Company"}]}) == [])


# --- structure: the umbrella-company shape ---------------------------------
#
# The exact shape tailoring.md used to recommend. A human reads it correctly and
# a parser records "Earlier Co-Ops" as the employer of three real companies.

MERGED = {"experience": [{
    "company": "Earlier Co-Ops",
    "title": "Backend Engineer (Spotify) · Data Engineer (NBCUniversal)",
    "location": "Boston and New York", "start": "Jan 2020", "end": "Jul 2022",
}]}

ROLES = {"experience": [{
    "group": "Earlier Co-Ops",
    "roles": [
        {"title": "Data Engineer Co-Op", "company": "NBCUniversal",
         "location": "New York City, NY", "start": "Jan 2022", "end": "Jul 2022"},
        {"title": "Backend Software Engineer Co-Op", "company": "Spotify",
         "location": "Boston, MA", "start": "Jan 2021", "end": "Aug 2021",
         "bullets": ["Raised user retention by 12% on the Java backend."]},
    ],
}]}

GOOD = {"experience": [{
    "company": "Sectra Inc", "title": "AI Enablement Lead",
    "location": "Shelton, CT", "start": "Feb 2026", "end": "Present",
    "bullets": ["Taught a company-wide Claude series."],
}]}

issues = pc.structure_issues(MERGED)
check("umbrella company is reported", any("names no employer" in i for i in issues),
      repr(issues))
check("multi-role title is reported", any("several roles" in i for i in issues),
      repr(issues))
check("the roles shape passes", pc.structure_issues(ROLES) == [],
      repr(pc.structure_issues(ROLES)))
check("an ordinary entry passes", pc.structure_issues(GOOD) == [],
      repr(pc.structure_issues(GOOD)))

check("a role without a company is caught",
      any("no company" in i for i in pc.structure_issues(
          {"experience": [{"roles": [{"title": "X", "start": "2020", "end": "2021"}]}]})))
check("a role without dates is caught",
      any("no dates" in i for i in pc.structure_issues(
          {"experience": [{"roles": [{"title": "X", "company": "Y"}]}]})))

# --- extraction: facts that do not come back out ---------------------------

check("a fact absent from the text is reported",
      len(pc.missing_facts(GOOD, "FRANCISCO TURDERA")) > 0)
check("a fact present in the text is not reported",
      pc.missing_facts(GOOD, "Sectra Inc AI Enablement Lead Shelton, CT Feb 2026 - Present "
                             "Taught a company-wide Claude series.") == [])

# The normalizer earns its keep here: an extractor that returns a different dash,
# different case, or a lost space has not lost the fact, and reporting it as
# missing would train the reader to skim past this check.
check("an en dash in the extracted text still matches",
      pc.missing_facts(GOOD, "Sectra Inc AI Enablement Lead Shelton, CT Feb 2026 – Present") == [])
check("a lost space still matches",
      pc.missing_facts(GOOD, "SectraInc AI Enablement Lead Shelton,CT Feb 2026 - Present") == [])

# --- bullets living on a role must not be invisible ------------------------
#
# Three separate things used to read job["bullets"] and nothing else. A bullet
# the trimmer cannot see cannot be dropped to save a page; one the linter cannot
# see ships with an em dash in it. Both fail silently, which is the only reason
# these are worth a test.

import prose  # noqa: E402

dirty = {"experience": [{"group": "Earlier Co-Ops", "roles": [
    {"title": "Co-Op", "company": "Spotify",
     "bullets": ["Raised retention, leveraging a truly seamless pipeline."]}]}]}
check("the linter reads role bullets", len(prose.lint(dirty, "tailored")) > 0)

if HAVE_DEPS:
    import render  # noqa: E402

    lists = render.bullet_lists(ROLES["experience"][0])
    check("role bullets are walkable", len(lists) == 1 and lists[0][1] == "Spotify",
          repr(lists))
    check("entry and role bullets are both walkable",
          len(render.bullet_lists({"company": "X", "bullets": ["a"],
                                   "roles": [{"company": "Y", "bullets": ["b"]}]})) == 2)

    fat = {"experience": [{"roles": [{"title": "T", "company": "C",
                                      "bullets": ["one", "two", "three"]}]}]}
    dropped = render._trim_once(fat)
    check("the trimmer can drop a role bullet", dropped is not None and "C" in dropped,
          repr(dropped))
    check("the trimmer actually removed it",
          len(fat["experience"][0]["roles"][0]["bullets"]) == 2)

    # Two bold keywords with only a space between them. split_runs hands the
    # wrapper a whitespace-only run for the gap; a tokenizer that skips it
    # welded "agentic workflows" into "agenticworkflows" on the page.
    gap = [("agentic", render.BOLD, 10, "c"), (" ", render.REG, 10, "c"),
           ("workflows", render.BOLD, 10, "c")]
    line = render.wrap_runs(gap, 500)[0]
    drawn = "".join(piece[1] for piece in line)
    check("a space between adjacent bold keywords survives wrapping",
          drawn == "agentic workflows", repr(drawn))
    check("the bold pieces are not merged across the gap",
          [piece[2] for piece in line] == [render.BOLD, render.REG, render.BOLD],
          repr([piece[2] for piece in line]))
    narrow = render.wrap_runs(gap, 40)
    check("a line break at the gap leaves no leading space on the next line",
          narrow[1][0][1] == "workflows", repr(narrow))

    # Highlights carry a source and must not restate the chronology.
    hl = {
        "summary": "Engineer with three years. Ships things. Brings depth.",
        "highlights": [
            {"text": "Cut demo infrastructure cost by $230K annually", "source": "Sectra Inc"},
            {"text": "Built a thing nobody below mentions", "source": "Nowhere Corp"},
            "Bare string with no source at all",
        ],
        "experience": [{"company": "Sectra Inc", "bullets": [
            "Cut demo infrastructure cost by $230K annually through savings plans."]}],
    }
    msgs = render.highlight_checks(hl)
    check("a highlight that restates a bullet is flagged",
          any("highlights[0]" in m and "restates" in m for m in msgs), repr(msgs))
    check("a source that matches nothing on the page is flagged",
          any("highlights[1]" in m and "matches no employer" in m for m in msgs), repr(msgs))
    check("a highlight with no source is flagged",
          any("highlights[2]" in m and "no source" in m for m in msgs), repr(msgs))
    check("a sourced, original highlight passes",
          not any("highlights[0]" in m and "source" in m for m in msgs), repr(msgs))
    check("the summary shape check is quiet on 2-5 sentences",
          render.summary_checks(hl["summary"]) == [])
    check("a one-sentence summary is flagged",
          any("one sentence" in m for m in render.summary_checks("Just one.")))
    check("a missing summary is flagged",
          any("no summary" in m for m in render.summary_checks("")))
    lay = render.Layout(render.ctx_for(1.0), kw=None)
    lay.bullet("fact", source="Sectra Inc")
    texts = [op[3] for op in lay.ops if op[0] == "text"]
    check("the source tag leads the highlight in its own gray piece",
          any(t.startswith("Sectra Inc") for t in texts), repr(texts))

    lay = render.Layout(render.ctx_for(1.0), kw=None)
    lay.bullet("word " * 40 + "end.")  # wraps; whether the tail is short depends on width
    lay2 = render.Layout(render.ctx_for(1.0), kw=None)
    lay2.bullet("short one-line bullet")
    check("a one-line bullet is never an orphan", lay2.orphans == [], repr(lay2.orphans))
    orphan_lay = render.Layout(render.ctx_for(1.0), kw=None)
    # Build a bullet whose wrap leaves exactly one word on the second line.
    text = "x" * 5
    while True:
        orphan_lay.orphans.clear()
        orphan_lay.ops.clear()
        orphan_lay.y = 0.0
        orphan_lay.bullet(text + " tail")
        if orphan_lay.orphans:
            break
        text += " xxxx"
        if len(text) > 2000:
            break
    check("a bullet that wraps one word onto its last line is reported",
          orphan_lay.orphans and orphan_lay.orphans[0][1] == "tail", repr(orphan_lay.orphans))

# --- round trip: render, read it back, expect silence ----------------------

if not HAVE_DEPS:
    print("  SKIP  renderer checks and round trip (reportlab or pypdfium2 not "
          "installed). Run under uv to include them.")
else:
    example = json.loads((ROOT / "assets" / "tailored_resume.example.json").read_text())
    example["experience"].append(ROLES["experience"][0])  # exercise the roles path

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "resume.pdf"
        lay, ctx, trimmed = render.solve(example)
        pages = render.draw(lay, out)
        result = pc.check(example, out)
        check("the example renders to one page", pages == 1, f"pages={pages}")
        check("a rendered page yields its own facts back",
              result["missing"] == [], repr(result["missing"]))
        check("a rendered page has no structural complaints",
              result["structure"] == [], repr(result["structure"]))
        check("text extraction actually ran", result["extracted"] is True)

print()
if FAILURES:
    print(f"{len(FAILURES)} failed: {', '.join(FAILURES)}")
    raise SystemExit(1)
print("all checks passed")
