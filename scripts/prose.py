#!/usr/bin/env python3
"""Prose lint shared by the renderer and the validator. Standard library only.

Two house rules, checked mechanically because they are exactly the kind of
thing that survives a self-review:

    no em dashes   they read as LLM output; a comma, colon, or period is
                   always available
    no filler      hedges and intensifiers that add length without adding a
                   fact, worst of all in the summary

Date ranges the renderer builds itself use an en dash and are not content, so
only text carried in the JSON is scanned.
"""

import re

DASHES = {
    "—": "em dash",
    "–": "en dash",
    "--": "double hyphen",
}

FILLER = [
    "actually", "honestly", "genuinely", "truly", "really", "basically",
    "essentially", "simply", "quite", "very", "arguably", "notably",
    "clearly", "obviously", "certainly", "definitely", "literally",
    "significantly", "substantially", "leverage", "leveraged", "leveraging",
    "utilize", "utilized", "utilizing", "seamless", "seamlessly", "robustly",
    "successfully", "responsible for", "helped with", "assisted in",
    "worked on", "various", "numerous", "cutting-edge", "state-of-the-art",
    "passionate", "proven track record", "results-driven", "team player",
    "detail-oriented", "self-starter", "synergy", "world-class",
]

_FILLER_RE = re.compile(
    r"(?<![\w-])(" + "|".join(re.escape(w) for w in FILLER) + r")(?![\w-])",
    re.IGNORECASE,
)


def lint_text(label: str, text: str) -> list[str]:
    if not isinstance(text, str) or not text:
        return []
    found = []
    for glyph, name in DASHES.items():
        if glyph in text:
            found.append(f"{label}: {name} ({glyph!r}). Rewrite with a comma, colon, or period.")
    hits = sorted({m.group(1).lower() for m in _FILLER_RE.finditer(text)})
    if hits:
        found.append(f"{label}: filler word(s) {', '.join(hits)}. Cut, or replace with a fact.")
    return found


def _walk_tailored(data: dict):
    yield "meta.title", (data.get("meta") or {}).get("title")
    yield "summary", data.get("summary")
    for i, h in enumerate(data.get("highlights") or []):
        yield f"highlights[{i}]", h
    for i, job in enumerate(data.get("experience") or []):
        who = job.get("company", f"experience[{i}]")
        for j, b in enumerate(job.get("bullets") or []):
            yield f"{who} bullet {j + 1}", b
    for i, p in enumerate(data.get("projects") or []):
        yield f"project[{i}].name", p.get("name")
        yield f"project '{p.get('name', i)}'", p.get("description")
    for i, job in enumerate(data.get("experience") or []):
        yield f"experience[{i}].title", job.get("title")


def _walk_master(data: dict):
    for i, t in enumerate(data.get("titles") or []):
        yield f"titles[{t.get('id', i)}]", t.get("text")
    for i, s in enumerate(data.get("summaries") or []):
        yield f"summaries[{s.get('id', i)}]", s.get("text")
    for i, job in enumerate(data.get("experience") or []):
        who = job.get("company", f"experience[{i}]")
        for b in job.get("bullets") or []:
            if isinstance(b, dict):
                yield f"{who}.{b.get('id', '?')}", b.get("text")
    for i, p in enumerate(data.get("projects") or []):
        name = p.get("name", i)
        yield f"projects[{i}].name", name
        yield f"project '{name}'", p.get("description")
        for v in p.get("versions") or []:
            label = v.get("label", v.get("id", "?"))
            yield f"project '{name}' / {label}.name", v.get("name")
            yield f"project '{name}' / {label}", v.get("description")


def lint(data: dict, kind: str = "tailored") -> list[str]:
    """Return one message per offending field. Empty means clean."""
    walker = _walk_tailored if kind == "tailored" else _walk_master
    out = []
    for label, text in walker(data):
        out += lint_text(label, text)
    return out


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        raise SystemExit("usage: prose.py <json-file> [tailored|master]")
    kind = sys.argv[2] if len(sys.argv) > 2 else "tailored"
    problems = lint(json.loads(open(sys.argv[1]).read()), kind)
    print(json.dumps(problems, indent=2))
    raise SystemExit(1 if problems else 0)
