#!/usr/bin/env python3
"""resume-kit state + integrity helper. Standard library only, so it always runs.

Commands:
    paths                 Resolve where the master resume and outputs live
    locate                Search the machine for an existing master before onboarding
    adopt <path>          Copy a located master into the home directory
    note <folder>         Leave a CLAUDE.md in the folder that holds the master
    set-home <dir>        Pin a different home directory (writes a config file)
    validate [master]     Structural check of master_resume.json
    backup [master]       Timestamped copy into <home>/backups/
    doctor                Check deps, fonts, state, and render the example
    init                  Create the home directory layout

The home directory holds everything stateful:
    <home>/master_resume.json      the single source of truth
    <home>/backups/                every pre-edit snapshot
    <home>/output/<company>/<role> generated resumes
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prose import lint as prose_lint  # noqa: E402

KIT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path.home() / ".config" / "resume-kit" / "config.json"
DEFAULT_HOME = Path.home() / ".resume-kit"
MAX_BACKUPS = 20


# ---------------------------------------------------------------------------
# Home resolution, never depends on the current working directory
# ---------------------------------------------------------------------------

def resolve_home() -> tuple[Path, list[str]]:
    """Return (home, warnings).

    Order: $RESUME_KIT_HOME, then the config file, then ~/.resume-kit.
    Deliberately not cwd-sensitive: picking a state dir because one happens to
    exist next to you is how you end up with two diverging master resumes.
    """
    warnings = []
    env = os.environ.get("RESUME_KIT_HOME")
    cfg = None
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text()).get("home")
        except (json.JSONDecodeError, OSError) as e:
            warnings.append(f"config at {CONFIG_PATH} is unreadable ({e}); ignoring it")
    if env and cfg and Path(env).expanduser() != Path(cfg).expanduser():
        warnings.append(
            f"CONFLICT: $RESUME_KIT_HOME={env} overrides config home={cfg}. "
            "Two master resumes may exist: reconcile them before editing."
        )
    home = Path(env or cfg or DEFAULT_HOME).expanduser()
    return home, warnings


def master_path(home: Path) -> Path:
    return home / "master_resume.json"


# ---------------------------------------------------------------------------
# Locating an existing master
#
# The home directory is not always the place the master survives in. Ephemeral
# sandboxes (cloud agent sessions, CI, a rebuilt container) hand you a fresh
# filesystem every run, so `master_exists: false` means "not here right now",
# which is not the same as "this person has never used the kit". Redoing the
# onboarding interview on top of an existing master is the worst outcome this
# skill has, so look before concluding.
# ---------------------------------------------------------------------------

MASTER_GLOB = "master_resume*.json"
SEARCH_BUDGET_S = 6.0
SEARCH_SKIP = {
    ".git", "node_modules", "__pycache__", "venv", ".venv", "env", ".env",
    "site-packages", "dist", "build", ".next", ".cache", ".Trash", "Applications",
    "Library", "System", "target", ".terraform", ".gradle", ".npm", ".tox",
}


def _search_roots() -> list[tuple[Path, int]]:
    """(directory, max_depth) pairs, most likely first. Depth 1 = that dir only."""
    hm, _ = resolve_home()
    home_dir = Path.home()
    roots: list[tuple[Path, int]] = [
        (hm, 2),
        (DEFAULT_HOME, 2),
        # Agent sandboxes stage the user's connected folders under these.
        (Path("/mnt/user-data/uploads"), 5),
        (Path("/mnt/user-data/outputs"), 4),
        (Path("/mnt/user-data"), 3),
        (Path("/workspace"), 3),
    ]
    cwd = Path.cwd()
    roots.append((cwd, 3))
    roots += [(p, 2) for p in list(cwd.parents)[:3]]
    for name in ("resume-kit", "Documents", "Desktop", "Dropbox", "OneDrive",
                 "Google Drive", "My Drive", "Sync", "Nextcloud", "iCloud Drive",
                 "Projects", "projects", "src", "Developer", "work"):
        roots.append((home_dir / name, 3))
    # iCloud on macOS lives under Library, which the general walk skips.
    roots.append((home_dir / "Library/Mobile Documents/com~apple~CloudDocs", 3))
    roots.append((home_dir, 1))
    return roots


def _walk_for_masters(root: Path, max_depth: int, deadline: float, seen: set) -> list[Path]:
    hits = []
    if not root.is_dir():
        return hits
    root_depth = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        if time.monotonic() > deadline:
            break
        here = Path(dirpath)
        if here.resolve() == KIT_ROOT:      # the shipped example is not a user's master
            dirnames[:] = []
            continue
        depth = len(here.parts) - root_depth + 1
        if depth >= max_depth:
            dirnames[:] = []
        else:
            dirnames[:] = [
                d for d in dirnames
                if d == ".resume-kit" or (d not in SEARCH_SKIP and not d.startswith("."))
            ]
        for fn in filenames:
            if fn.endswith(".example.json"):
                continue
            p = here / fn
            if p.match(MASTER_GLOB):
                rp = str(p.resolve())
                if rp not in seen:
                    seen.add(rp)
                    hits.append(p)
    return hits


def _describe_candidate(path: Path, home_master: Path) -> dict:
    info = {
        "path": str(path),
        "is_home": path.resolve() == home_master.resolve() if home_master.exists() else False,
        "modified": None,
        "bytes": None,
        "parses": False,
        "valid": False,
        "name": None,
        "roles": 0,
        "bullets": 0,
        "errors": [],
    }
    try:
        st = path.stat()
        info["bytes"] = st.st_size
        info["modified"] = datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat()
    except OSError:
        return info
    try:
        data = json.loads(path.read_text())
        info["parses"] = True
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        info["errors"] = [f"unreadable: {e}"]
        return info
    errors, _ = validate_master(data)
    info["valid"] = not errors
    info["errors"] = errors[:5]
    if isinstance(data, dict):
        info["name"] = (data.get("meta") or {}).get("name")
        exp = data.get("experience") or []
        info["roles"] = len(exp)
        info["bullets"] = sum(len(j.get("bullets") or []) for j in exp if isinstance(j, dict))
    return info


def find_masters() -> list[dict]:
    """Every plausible master_resume.json on this machine, best candidate first."""
    home, _ = resolve_home()
    hm = master_path(home)
    deadline = time.monotonic() + SEARCH_BUDGET_S
    seen: set = set()
    found: list[Path] = []
    for root, depth in _search_roots():
        if time.monotonic() > deadline:
            break
        found += _walk_for_masters(root, depth, deadline, seen)
    cands = [_describe_candidate(p, hm) for p in found]
    # Stable two-pass sort: newest first, then usable candidates to the top.
    cands.sort(key=lambda c: c["modified"] or "", reverse=True)
    cands.sort(key=lambda c: (not c["valid"], not c["parses"], -(c["bullets"] or 0)))
    return cands


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _require(cond, msg, bucket):
    if not cond:
        bucket.append(msg)


def validate_master(data) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Errors mean the tailoring step will misbehave."""
    errors, warns = [], []
    if not isinstance(data, dict):
        return ["master_resume.json is not a JSON object"], []

    meta = data.get("meta") or {}
    _require(isinstance(meta, dict) and meta.get("name"), "meta.name is missing", errors)
    _require(meta.get("email"), "meta.email is missing", errors)
    for optional in ("phone", "location", "linkedin", "github"):
        if not meta.get(optional):
            warns.append(f"meta.{optional} is empty, the contact line will omit it")

    titles = data.get("titles") or []
    summaries = data.get("summaries") or []
    _require(len(titles) >= 1, "titles[] is empty: need at least one headline variant", errors)
    _require(len(summaries) >= 1, "summaries[] is empty: need at least one summary variant", errors)
    if len(titles) == 1:
        warns.append("only one title variant: 2-3 variants let tailoring position you per role")
    if len(summaries) == 1:
        warns.append("only one summary variant: 2-3 variants give tailoring room to reposition")

    all_tags = []
    for i, t in enumerate(titles):
        _require(t.get("text"), f"titles[{i}].text is missing", errors)
        _require(t.get("tags"), f"titles[{i}].tags is missing: untagged variants never get picked", errors)
        all_tags += t.get("tags") or []
    for i, s in enumerate(summaries):
        _require(s.get("text"), f"summaries[{i}].text is missing", errors)
        _require(s.get("tags"), f"summaries[{i}].tags is missing", errors)
        all_tags += s.get("tags") or []

    skills = data.get("skills") or {}
    _require(isinstance(skills, dict) and skills, "skills must be a non-empty object of category -> [items]", errors)
    for label, items in (skills.items() if isinstance(skills, dict) else []):
        _require(isinstance(items, list) and items, f"skills.{label} must be a non-empty list", errors)

    experience = data.get("experience") or []
    _require(len(experience) >= 1, "experience[] is empty", errors)
    for i, job in enumerate(experience):
        for field in ("company", "title", "start", "end"):
            _require(job.get(field), f"experience[{i}].{field} is missing", errors)
        if not job.get("location"):
            warns.append(f"experience[{i}] ({job.get('company', '?')}) has no location")
        bullets = job.get("bullets") or []
        _require(bullets, f"experience[{i}] ({job.get('company', '?')}) has no bullets", errors)
        for j, b in enumerate(bullets):
            if not isinstance(b, dict):
                errors.append(f"experience[{i}].bullets[{j}] must be an object with text/tags, not a bare string")
                continue
            _require(b.get("text"), f"experience[{i}].bullets[{j}].text is missing", errors)
            if not b.get("tags"):
                warns.append(
                    f"experience[{i}].bullets[{j}] is untagged: tailoring will rarely select it"
                )
            all_tags += b.get("tags") or []

    for i, p in enumerate(data.get("projects") or []):
        _require(p.get("name"), f"projects[{i}].name is missing", errors)
        _require(p.get("description"), f"projects[{i}].description is missing", errors)
        if not p.get("tags"):
            warns.append(f"projects[{i}] ({p.get('name', '?')}) is untagged: it will rarely be selected")
        all_tags += p.get("tags") or []
        for k, v in enumerate(p.get("versions") or []):
            _require(v.get("description"), f"projects[{i}].versions[{k}].description is missing", errors)
            all_tags += v.get("tags") or []

    for i, e in enumerate(data.get("education") or []):
        for field in ("institution", "degree"):
            _require(e.get(field), f"education[{i}].{field} is missing", errors)

    # Tag hygiene: a rare tag that looks like a common one is a typo, and a
    # typo'd tag silently removes its content from every future tailoring pass.
    import difflib
    counts = {}
    for tag in all_tags:
        counts[tag] = counts.get(tag, 0) + 1
    for tag, n in sorted(counts.items()):
        if n > 1:
            continue
        others = [t for t, c in counts.items() if t != tag and c > 1]
        near = difflib.get_close_matches(tag, others, n=1, cutoff=0.85)
        if near:
            warns.append(
                f"tag '{tag}' (used once) looks like a typo of '{near[0]}' "
                f"(used {counts[near[0]]}x). Unify them, or tailoring will skip that content."
            )

    # House style: content written here propagates into every future resume.
    warns += prose_lint(data, "master")
    return errors, warns


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_paths(args):
    home, warnings = resolve_home()
    mp = master_path(home)
    info = {
        "home": str(home),
        "master": str(mp),
        "master_exists": mp.exists(),
        "output_dir": str(home / "output"),
        "backups_dir": str(home / "backups"),
        "kit_root": str(KIT_ROOT),
        "source": ("env:RESUME_KIT_HOME" if os.environ.get("RESUME_KIT_HOME")
                   else "config" if CONFIG_PATH.exists() else "default"),
        "warnings": warnings,
    }
    if not info["master_exists"]:
        info["next_step"] = (
            "Do NOT assume this is a first run. Run `kit.py locate` to search for an "
            "existing master, and check any connected or synced folders, before onboarding."
        )
    print(json.dumps(info, indent=2))
    return 0


def cmd_locate(args):
    home, _ = resolve_home()
    hm = master_path(home)
    cands = find_masters()
    usable = [c for c in cands if c["valid"] and not c["is_home"]]
    if hm.exists():
        verdict = "home_master_present"
        advice = f"A master is already in place at {hm}. Nothing to adopt."
    elif not cands:
        verdict = "none_found"
        advice = (
            "Nothing on this filesystem. Before treating it as a first run, check anywhere "
            "this machine cannot see by itself: connected or shared folders in an agent "
            "session, cloud storage that is not synced locally, another machine, or a backup. "
            "Ask the user whether they have used this kit before. Only onboard after that."
        )
    elif len(usable) == 1:
        verdict = "adopt"
        advice = f"Run: kit.py adopt {usable[0]['path']}"
    elif len(usable) > 1:
        verdict = "ambiguous"
        advice = (
            "More than one usable master found. Show the user the paths, dates, and role "
            "counts, and let them pick. Never merge them silently."
        )
    else:
        verdict = "found_but_invalid"
        advice = (
            "Candidates exist but none validate. Read the errors: a repairable file is worth "
            "far more than a re-interview. Adopt with --force only after you have fixed it."
        )
    print(json.dumps({
        "home": str(home),
        "home_master_exists": hm.exists(),
        "verdict": verdict,
        "advice": advice,
        "found": len(cands),
        "candidates": cands,
    }, indent=2))
    return 0


NOTE_BEGIN = "<!-- resume-kit:begin (managed by kit.py note, edits inside are overwritten) -->"
NOTE_END = "<!-- resume-kit:end -->"


def _note_body(folder: str) -> str:
    """The block left in the folder that holds the master.

    Written for whatever agent opens that folder next, which may be months later
    with none of this session's context. It answers the only two questions that
    matter there: is this a first run, and how do I load the file.
    """
    master = f"{folder.rstrip('/')}/master_resume.json"
    return f"""{NOTE_BEGIN}
## Resume kit

`master_resume.json` in this folder is the source of truth for this person's career. It
was built once, in an interview that took a full session, and must not be rebuilt.

**An empty `~/.resume-kit` is not a first run.** Sandboxes, containers, and reinstalls all
start empty. Load the master from here instead:

- If this folder is a real path this session can read, pin it once and you are done:
  `python3 <skill-dir>/scripts/kit.py set-home {folder}`
- If this session reaches the folder only through a file-transfer bridge, copy
  `{master}` into the session first, then
  `python3 <skill-dir>/scripts/kit.py adopt <the-copied-path>`. Staging is the one step
  `kit.py locate` cannot do for itself, which is why this note exists.

**Every edit has to come back here.** `kit.py backup`, edit, `kit.py validate`, then write
the file back to `{master}`. An edit left in an ephemeral home dies with the session.

Tailored resumes are disposable and do not belong here unless the user asks. Regenerate
them from the master rather than keeping copies.
{NOTE_END}"""


def cmd_note(args):
    folder = args.folder.rstrip("/")
    out = Path(args.out).expanduser() if args.out else Path(folder).expanduser() / "CLAUDE.md"
    block = _note_body(folder)

    mode = "created"
    if out.exists():
        try:
            existing = out.read_text()
        except (OSError, UnicodeDecodeError) as e:
            print(json.dumps({"written": False, "error": f"{out} exists but is unreadable: {e}"}, indent=2))
            return 1
        if NOTE_BEGIN in existing and NOTE_END in existing:
            head = existing.split(NOTE_BEGIN)[0]
            tail = existing.split(NOTE_END, 1)[1]
            text = head + block + tail
            mode = "updated"
        else:
            # Someone else's file. Append, never overwrite: it may be a project's
            # own CLAUDE.md carrying instructions that matter more than ours.
            text = existing.rstrip("\n") + "\n\n" + block + "\n"
            mode = "appended"
    else:
        text = block + "\n"

    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
    except OSError as e:
        print(json.dumps({
            "written": False,
            "error": f"cannot write {out}: {e}",
            "hint": "If the folder is only reachable over a bridge, pass --out to write the "
                    "file locally, then transfer it to the folder yourself.",
        }, indent=2))
        return 1

    print(json.dumps({
        "written": True,
        "path": str(out),
        "mode": mode,
        "describes_folder": folder,
        "reminder": None if out.parent == Path(folder).expanduser()
        else f"Written locally. Transfer it to {folder}/CLAUDE.md, or the next session will not see it.",
    }, indent=2))
    return 0


def cmd_adopt(args):
    src = Path(args.path).expanduser()
    home, _ = resolve_home()
    dest = master_path(home)
    if not src.exists():
        print(json.dumps({"adopted": False, "error": f"no file at {src}"}, indent=2))
        return 1
    try:
        data = json.loads(src.read_text())
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        print(json.dumps({"adopted": False, "error": f"{src} is not readable JSON: {e}"}, indent=2))
        return 1
    errors, warns = validate_master(data)
    if errors and not args.force:
        print(json.dumps({
            "adopted": False,
            "error": "source does not validate; fix it or re-run with --force",
            "errors": errors,
        }, indent=2))
        return 1

    replaced = None
    if dest.exists():
        if not args.force:
            print(json.dumps({
                "adopted": False,
                "error": f"a master already exists at {dest}. Reconcile the two by hand, or "
                         f"re-run with --force to overwrite (the current one is backed up first).",
            }, indent=2))
            return 1
        backups = home / "backups"
        backups.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        replaced = backups / f"master_resume.replaced.{stamp}.json"
        shutil.copy2(dest, replaced)

    dest.parent.mkdir(parents=True, exist_ok=True)
    (home / "output").mkdir(parents=True, exist_ok=True)
    (home / "backups").mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    print(json.dumps({
        "adopted": True,
        "source": str(src),
        "master": str(dest),
        "previous_backed_up_to": str(replaced) if replaced else None,
        "valid": not errors,
        "errors": errors,
        "warnings": warns,
        "reminder": "This copy lives in the session's home directory. If that home is "
                    "ephemeral, write edits back to the source path before the session ends.",
    }, indent=2))
    return 0


def cmd_set_home(args):
    target = Path(args.dir).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps({"home": str(target)}, indent=2))
    print(f"resume-kit home pinned to {target} (config: {CONFIG_PATH})")
    if os.environ.get("RESUME_KIT_HOME"):
        print("NOTE: $RESUME_KIT_HOME is set and still takes precedence over this config.")
    return 0


def cmd_init(args):
    home, _ = resolve_home()
    (home / "output").mkdir(parents=True, exist_ok=True)
    (home / "backups").mkdir(parents=True, exist_ok=True)
    print(json.dumps({"home": str(home), "master_exists": master_path(home).exists()}, indent=2))
    return 0


def _load_master(arg):
    home, _ = resolve_home()
    path = Path(arg).expanduser() if arg else master_path(home)
    if not path.exists():
        print(f"ERROR: no master resume at {path}. Run `kit.py locate` before assuming this "
              f"is a first run: an existing master may be sitting somewhere this home cannot see.")
        raise SystemExit(1)
    return path, json.loads(path.read_text())


def cmd_validate(args):
    path, data = _load_master(args.master)
    errors, warns = validate_master(data)
    print(json.dumps({
        "master": str(path),
        "valid": not errors,
        "errors": errors,
        "warnings": warns,
    }, indent=2))
    return 1 if errors else 0


def cmd_backup(args):
    path, _ = _load_master(args.master)
    home, _ = resolve_home()
    backups = home / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = backups / f"master_resume.{stamp}.json"
    shutil.copy2(path, dest)
    existing = sorted(backups.glob("master_resume.*.json"))
    pruned = []
    for old in existing[:-MAX_BACKUPS]:
        old.unlink()
        pruned.append(old.name)
    print(json.dumps({"backup": str(dest), "pruned": pruned}, indent=2))
    return 0


def cmd_doctor(args):
    home, warnings = resolve_home()
    report = {"checks": [], "warnings": list(warnings), "ok": True}

    def check(name, ok, detail=""):
        report["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
        if not ok:
            report["ok"] = False

    check("python>=3.10", sys.version_info >= (3, 10), sys.version.split()[0])

    uv = shutil.which("uv")
    have_reportlab = _importable("reportlab")
    check(
        "renderer deps",
        bool(uv) or have_reportlab,
        f"uv={'yes' if uv else 'no'} reportlab-in-this-python={'yes' if have_reportlab else 'no'}"
        + ("" if (uv or have_reportlab) else " install uv, or run scripts/setup.sh"),
    )
    check("png preview (optional)", bool(uv) or _importable("pypdfium2"),
          "without uv or pypdfium2 the visual review step is skipped")
    check("docx output", bool(uv) or _importable("docx"),
          "python-docx writes the editable deliverable")

    fonts = KIT_ROOT / "assets" / "fonts"
    check("bundled fonts", (fonts / "Carlito-Regular.ttf").exists()
          and (fonts / "Carlito-Bold.ttf").exists(), str(fonts))

    mp = master_path(home)
    check("home writable", os.access(home.parent, os.W_OK), str(home))
    if mp.exists():
        try:
            errors, warns = validate_master(json.loads(mp.read_text()))
            check("master resume valid", not errors, "; ".join(errors) or "ok")
            report["warnings"] += warns
        except json.JSONDecodeError as e:
            check("master resume valid", False, f"not parseable JSON: {e}")
    else:
        elsewhere = [c for c in find_masters() if c["valid"]]
        report["checks"].append({
            "check": "master resume present", "ok": False,
            "detail": (
                f"none at {mp}, but {len(elsewhere)} usable master(s) found elsewhere: "
                + ", ".join(c["path"] for c in elsewhere[:3])
                + ". Adopt one rather than onboarding."
            ) if elsewhere else (
                f"none at {mp}, and `locate` found none on this filesystem. Expected on a "
                f"fresh install. If the home is ephemeral, check connected folders first."
            ),
        })

    # End-to-end: render the shipped example.
    example = KIT_ROOT / "assets" / "master_resume.example.json"
    tailored_example = KIT_ROOT / "assets" / "tailored_resume.example.json"
    if tailored_example.exists() and (uv or have_reportlab):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            cmd = ([uv, "run", str(KIT_ROOT / "scripts" / "render.py")] if uv
                   else [sys.executable, str(KIT_ROOT / "scripts" / "render.py")])
            cmd += ["--tailored", str(tailored_example), "--out-dir", tmp]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            ok = (proc.returncode == 0 and (Path(tmp) / "resume.pdf").exists()
                  and (Path(tmp) / "resume.docx").exists())
            check("example renders", ok,
                  (proc.stderr or proc.stdout).strip().splitlines()[-1] if not ok else "one-page PDF + editable DOCX produced")
    check("example master present", example.exists(), str(example))

    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


def _importable(mod: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(mod) is not None


def main():
    ap = argparse.ArgumentParser(description="resume-kit state helper")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("paths").set_defaults(fn=cmd_paths)
    sub.add_parser("locate").set_defaults(fn=cmd_locate)
    p = sub.add_parser("note")
    p.add_argument("folder", help="the durable folder holding the master, as the user sees it")
    p.add_argument("--out", help="write here instead of <folder>/CLAUDE.md, for folders "
                                 "reachable only over a file-transfer bridge")
    p.set_defaults(fn=cmd_note)
    p = sub.add_parser("adopt")
    p.add_argument("path")
    p.add_argument("--force", action="store_true",
                   help="overwrite an existing master (backed up first), or accept one that fails validation")
    p.set_defaults(fn=cmd_adopt)
    sub.add_parser("init").set_defaults(fn=cmd_init)
    p = sub.add_parser("set-home")
    p.add_argument("dir")
    p.set_defaults(fn=cmd_set_home)
    p = sub.add_parser("validate")
    p.add_argument("master", nargs="?")
    p.set_defaults(fn=cmd_validate)
    p = sub.add_parser("backup")
    p.add_argument("master", nargs="?")
    p.set_defaults(fn=cmd_backup)
    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)

    args = ap.parse_args()
    raise SystemExit(args.fn(args))


if __name__ == "__main__":
    main()
