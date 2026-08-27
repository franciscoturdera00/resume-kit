#!/usr/bin/env python3
"""Keyword emphasis shared by the PDF and DOCX emitters. Standard library only.

A tailored resume may carry an optional top-level `bold_keywords` list: exact
terms lifted from the job posting that the user asked to see bolded on the
page. Both renderers split prose text (summary, experience bullets, project
descriptions) into regular/bold runs with the same rules, so the PDF and the
DOCX emphasize the same characters:

    case-insensitive     the posting says "Kubernetes", the bullet may not
    whole words only     "Go" never matches inside "Google"
    longest match wins   "distributed systems" beats "systems"
    every occurrence     restraint comes from keeping the list short

No `bold_keywords`, or an empty list, means no matcher and untouched output.
"""

import re


def compile_keywords(keywords):
    """Compile [str, ...] into one matcher, or None when there is nothing to do."""
    kws = sorted(
        {k.strip() for k in (keywords or []) if isinstance(k, str) and k.strip()},
        key=len, reverse=True,  # longest first, so phrases win over their words
    )
    if not kws:
        return None
    # Explicit lookarounds instead of \b: keywords may start or end with
    # non-word characters ("C++", ".NET"), where \b points the wrong way.
    # Hyphens count as joiners so "tracing" stays plain inside
    # "distributed-tracing", matching how prose.py bounds its filler words.
    body = "|".join(re.escape(k) for k in kws)
    return re.compile(r"(?<![\w-])(?:" + body + r")(?![\w-])", re.IGNORECASE)


def split_runs(text, matcher):
    """Split text into [(chunk, bold), ...] in order. Chunks concatenate back
    to exactly the input; with no matcher the whole text is one regular run."""
    if not matcher or not text:
        return [(text, False)]
    out, pos = [], 0
    for m in matcher.finditer(text):
        if m.start() > pos:
            out.append((text[pos:m.start()], False))
        out.append((m.group(0), True))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], False))
    return out


def unmatched_keywords(keywords, texts):
    """Keywords that never hit any of the given texts. For the render warning:
    a keyword nobody can see bolded is either a typo or a missing rewrite."""
    misses = []
    joined = "\n".join(t for t in texts if t)
    for k in keywords or []:
        if compile_keywords([k]) and not compile_keywords([k]).search(joined):
            misses.append(k)
    return misses
