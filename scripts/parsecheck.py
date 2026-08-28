#!/usr/bin/env python3
"""What a machine sees when it reads the finished page.

The fit solver proves the resume fits and the prose lint proves it reads like a
person wrote it. Neither one opens the PDF afterwards and asks the question an
applicant tracking system asks: *can the facts be recovered from this file at
all?*

Two failures are worth catching, and they fail differently.

**Extraction.** Text that was laid out is not necessarily text that comes back
out. Emphasis splits a sentence into runs, the layout draws each run at its own
coordinate, and an extractor rejoins them with its own idea of where the spaces
go. A phone number, a date range, or an employer can come back welded to its
neighbour. So the check is empirical: render, read the PDF back, and confirm
every fact the JSON claims is still findable.

**Structure.** Some facts survive extraction perfectly and still tell the reader
nothing, because the value itself is not a fact. An entry whose employer reads
"Earlier Co-Ops" parses cleanly into a company field that names no company, and
three real employers go missing while every text-level check passes. That one is
caught by looking at the JSON, not the PDF.

Both are advisory. A resume that trips these is still a valid document, and a
human reading the page may not notice anything wrong, which is exactly why the
warning has to come from here rather than from a person proofreading.

Standard library plus pypdfium2, which the renderer already depends on for the
PNG preview. No service, no upload, no account.
"""

import re
import unicodedata

# Employer fields that parse into nothing. These are the umbrella labels a
# writer reaches for when merging short roles to save a line: they read fine to
# a human, who sees the real employers in the title beside them, and they erase
# those employers for anything reading the fields.
_UMBRELLA = re.compile(
    r"\b(earlier|previous|prior|various|assorted|multiple|several|other|misc"
    r"|additional|early[- ]career)\b|^(co[- ]?ops?|internships?|roles?|positions?)$",
    re.IGNORECASE,
)

# A title carrying more than one role. "Data Engineer (NBCUniversal) · Cloud
# Engineer (Travelers)" is the shape: separators between roles, employers in
# parentheses where no parser looks for them.
_MULTI_ROLE = re.compile(r"\s[·•/]\s|\s\|\s.*\s\|\s")
_PAREN_EMPLOYER = re.compile(r"\([A-Z][\w&.\- ]{2,}\)")


def _norm(s: str) -> str:
    """Case, dash and space differences are the extractor's, not the author's."""
    s = unicodedata.normalize("NFKC", str(s))
    for dash in "‐‑‒–—−":
        s = s.replace(dash, "-")
    s = s.replace(" ", " ")
    return re.sub(r"\s+", " ", s).strip().lower()


def _squash(s: str) -> str:
    """Last resort: only the characters that carry meaning.

    An extractor that drops the space in "New Haven" or adds one inside a phone
    number has not lost the fact, and reporting it as missing would train the
    reader to ignore this check.
    """
    return re.sub(r"[^a-z0-9]", "", _norm(s))


def _daterange(entry) -> str:
    start, end = entry.get("start"), entry.get("end")
    if start and end:
        return f"{start} - {end}"
    return start or end or ""


def pdf_text(pdf_path) -> str | None:
    """All text in the PDF, or None when pypdfium2 is not installed."""
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return None
    doc = pdfium.PdfDocument(str(pdf_path))
    try:
        return "\n".join(page.get_textpage().get_text_range() for page in doc)
    finally:
        doc.close()


def required_facts(data: dict):
    """(label, value) for everything a reader must be able to recover.

    Deliberately not everything on the page. Bullet prose is long, wraps, and is
    read as prose anyway; what has to survive is the skeleton: who, where, when,
    how to make contact, and the skill names a keyword search will look for.
    """
    meta = data.get("meta") or {}
    for key in ("name", "email", "phone"):
        if meta.get(key):
            yield f"meta.{key}", meta[key]

    def _role(label, r):
        for key in ("title", "company", "location"):
            if r.get(key):
                yield f"{label}.{key}", r[key]
        if _daterange(r):
            yield f"{label}.dates", _daterange(r)

    for i, job in enumerate(data.get("experience") or []):
        who = job.get("company") or job.get("group") or f"experience[{i}]"
        if job.get("roles"):
            for j, r in enumerate(job["roles"]):
                yield from _role(f"{who}.roles[{j}]", r)
        else:
            yield from _role(who, job)

    for label, items in (data.get("skills") or {}).items():
        if isinstance(items, list):
            for item in items:
                yield f"skills.{label}", item

    for i, edu in enumerate(data.get("education") or []):
        for key in ("institution", "degree"):
            if edu.get(key):
                yield f"education[{i}].{key}", edu[key]


def missing_facts(data: dict, text: str) -> list[str]:
    hay_n, hay_s = _norm(text), _squash(text)
    out = []
    for label, value in required_facts(data):
        if _norm(value) in hay_n or _squash(value) in hay_s:
            continue
        out.append(f"{label}: {value!r} does not come back out of the PDF")
    return out


def structure_issues(data: dict) -> list[str]:
    out = []
    for i, job in enumerate(data.get("experience") or []):
        if job.get("roles"):
            for j, r in enumerate(job["roles"]):
                if not r.get("company"):
                    out.append(f"experience[{i}].roles[{j}] has no company")
                if not _daterange(r):
                    out.append(f"experience[{i}].roles[{j}] has no dates")
            continue

        company, title = job.get("company") or "", job.get("title") or ""
        if company and _UMBRELLA.search(company):
            out.append(
                f"experience[{i}].company is {company!r}, which names no employer. "
                "Use the 'roles' list so each employer keeps its own company, title "
                "and dates on one line."
            )
        if _MULTI_ROLE.search(title) or len(_PAREN_EMPLOYER.findall(title)) >= 2:
            out.append(
                f"experience[{i}].title packs several roles into one field: {title!r}. "
                "Employers named inside a title are not read as employers. Use the "
                "'roles' list instead."
            )
        if not company:
            out.append(f"experience[{i}] has no company")
        if not _daterange(job):
            out.append(f"experience[{i}] ({company or 'no company'}) has no dates")
    return out


def check(data: dict, pdf_path) -> dict:
    """{'missing': [...], 'structure': [...], 'extracted': bool}."""
    text = pdf_text(pdf_path)
    return {
        "extracted": text is not None,
        "missing": missing_facts(data, text) if text is not None else [],
        "structure": structure_issues(data),
    }


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 3:
        raise SystemExit("usage: parsecheck.py <tailored.json> <resume.pdf>")
    result = check(json.loads(open(sys.argv[1]).read()), sys.argv[2])
    print(json.dumps(result, indent=2))
    raise SystemExit(1 if result["missing"] or result["structure"] else 0)
