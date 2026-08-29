# The master resume: schema and update rules

The master is append-mostly career state. Tailoring selects from it; nothing selects
*into* it except deliberate updates. `assets/master_resume.example.json` is a complete
valid instance. Read it when the shape is unclear.

## Schema

```jsonc
{
  "meta":    { "name", "title", "email", "phone", "location", "linkedin", "github" },

  "titles":    [ { "id", "text", "tags" } ],              // 2-3 headline variants
  "summaries": [ { "id", "text", "tags", "priority" } ],  // optional; raw material only, never copied onto a page

  "skills": { "<category>": ["item", ...] },              // categories are free-form

  "experience": [ {
    "id", "company", "title", "location", "start", "end", "priority", "tags",
    "bullets": [ { "id", "text", "tags", "priority" } ]   // objects, never bare strings
  } ],

  "projects": [ {
    "id", "name", "tech": [], "description", "tags", "priority",
    "versions": [ { "label", "name", "description", "tech", "tags" } ]  // optional
  } ],

  "education":      [ { "id", "institution", "degree", "honors", "location", "start", "end", "priority" } ],
  "certifications": [ { "name", "issuer", "year" } ]
}
```

`id` values are stable handles. Never renumber or reuse them. `priority`: 1
career-defining, 2 solid, 3 filler. Dates are display strings (`"Mar 2022"`,
`"Present"`), rendered as written.

**Tags are a closed vocabulary.** Before adding a tag, look at what the file already
uses and reuse it. Coining `ci-cd` when the file says `cicd` doesn't add a tag, it
splits one concept into two half-dead ones. `kit.py validate` flags near-duplicates.

**`versions`** is for one project that genuinely changed shape (a CLI that became a
hosted service). Tailoring picks the version that matches the posting rather than
listing both. Adding a version keeps the history; overwriting the description destroys
it.

## Updating

```bash
python3 <skill-dir>/scripts/kit.py backup      # always first
# edit with Edit, never Write. A full rewrite of a file this large loses sections
python3 <skill-dir>/scripts/kit.py validate    # always last
```

Then tell the user in one line what changed and where. No JSON dumps.

### Rules

1. **Additive by default.** Add bullets, projects, versions, tech, tags. Don't delete
   history. An old role or a superseded architecture is range, and tailoring already
   ignores what doesn't match. Deletion is for things that are *wrong*, and for
   corrections the user explicitly asked for.
2. **Strongest honest framing.** Lead with impact, use active verbs, quantify with real
   numbers. Never "helped with" or "assisted in": say what was built and what changed.
3. **House voice: no em dashes, no filler.** This text ends up on resumes verbatim, so
   the rule that governs a tailored page governs what you write here. Use a comma or a
   colon instead of an em dash; cut `actually`, `leverage`, `successfully`, `seamless`,
   and the rest. `kit.py validate` flags what it can detect.
4. **Truth is the constraint.** Positive framing is not invention. Every claim traces to
   something the user actually did. No fabricated metrics, customers, or scale. Without
   a real number, use qualitative strength ("production", "multi-tenant", "end-to-end").
5. **Tag every addition** (3-6 tags: technology, domain, kind of work). Untagged content
   is invisible to tailoring.
6. **Mirror the existing shape.** Match field names and nesting exactly; don't invent
   top-level fields.
7. **When a versioned project evolves**, append to `versions` *and* merge any new tech
   and tags into the project's top-level `tech`/`tags` (deduped). Both are read.
8. **Don't rewrite existing entries to match a new tone**, and don't lower a `priority`
   just because something newer exists.
9. **`meta`, `education`, and `certifications` change only when the user says so.**

### When to offer an update

If the user mentions shipping something, a new number becoming real, a role or title
change, or a technology they've now used in earnest, offer to record it in one line.
Don't wait to be asked, and don't edit without a yes.

### Tone

Weak: "Helped build a resume tool." · "Worked on a trading bot." · "Made improvements."

Strong: "Shipped a resume-tailoring pipeline with a deterministic one-page layout engine
and a writer/critic loop." · "Built an event-driven trading system that parses earnings
transcripts with an LLM and calibrates position sizing on backtested win rates."
