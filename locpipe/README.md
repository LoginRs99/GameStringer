# locpipe

A deterministic, multi-project localization pipeline for games and
software. The LLM translates strings and repairs the ones flagged as
risky. Python does everything else — extraction, deduplication,
translation memory, batching, validation, merging, checkpointing,
statistics.

Practical step-by-step usage guide (Hungarian): see `HASZNALAT.md`.
This file covers the architecture and the reasoning behind it.
`CHANGELOG.md` has the full version-by-version history.

**Nothing under `locpipe/` references any specific project, engine,
language pair, or game.** `projects/<name>/project.yaml` is what makes
one project that project — glossary, style guide, character voices,
categories, batch location, format, all external config and data, none
of it in code. `locpipe init <name>` scaffolds one from scratch.

## Quick start

```bash
pip install -e .   # antigravity_cli (default provider) needs no extra -- it shells out
                    # to an existing `agy` binary. Add ".[gemini]" for the optional
                    # fallback provider -- see Providers below.

# new project
locpipe init myproject
# edit projects/myproject/project.yaml, drop batch files in batches/,
# fill in resources/glossary.md etc.

# dry run against the mock provider, no API key needed
locpipe run --project projects/myproject --dry-run

# check real numbers before spending anything -- no LLM calls either
locpipe plan --project projects/myproject

# uabea_json only: what would extraction keep vs. filter as engine noise?
# also no LLM calls -- see "Formats" below
locpipe audit --project projects/myproject

# for real (antigravity_cli needs `agy auth login`; gemini needs GEMINI_API_KEY)
locpipe run --project projects/myproject
```

## Pipeline phases

| Phase | Module |
|---|---|
| 1. Extract | `adapters/*.py` (`extract()`) |
| 2. Normalize | `normalize.py` |
| 3. Translation memory lookup | `tm.py` |
| 4. Duplicate detection | `dedupe.py` |
| 5. Incremental (content hash) | `normalize.py` (`content_hash`) + `tm.py` |
| 6. Glossary | `glossary.py` |
| 7. Context classification | `classify.py`, `config.py` (`CategoryRule`) |
| 8. Batching | `batcher.py` |
| 9. Bulk translate | `schemas.py`, `providers/*.py`, `pipeline.py` |
| 10. Structured-output parsing | `schemas.py` |
| 11. Validation | `validators/*.py` |
| 12. Confidence scoring | `confidence.py` |
| 13. Review queue | `review_queue.py` |
| 14. Tier-1 mechanical repair + review/repair call | `pipeline.py` (`_tier1_repair`), `reviewer.py` |
| 15. Merge + commit to TM + stats | `merge.py`, `adapters/*.py` (`merge()`), `dedupe.commit_to_tm`, `output.py` |

`pipeline.py` (`run()`, `plan()`) is the orchestrator that calls all of
these in order, per pending batch file.

**Phases 11-14 are a 3-tier QA loop, cheapest first.** Tier 1
(`pipeline._tier1_repair`): a deterministic validation failure — a
concrete, mechanical defect like a missing tag or placeholder, never a
judgment call — gets `confidence.tier1_repair_attempts` cheap retries
through the *bulk-translate* model, with the validator's own message
attached verbatim as the correction request, before it's allowed to
reach the review step at all. Tier 2 (`confidence.py`): heuristics —
expansion-ratio, disputed glossary terms, identity passthrough, source
length, structural complexity — score everything else, and only what's
still flagged after that reaches Tier 3 (`reviewer.py`,
`agents/review.md`), the one stage that costs a full LLM call per
flagged item (chunked, and run concurrently across chunks — see
"Concurrency" below). A random, deterministic sample of otherwise-clean
translations is also pulled into Tier 3 regardless of confidence, as a
fidelity check the confidence heuristics alone can't provide. Tier 3's
own output isn't trusted blindly either — it's re-validated after being
applied, and a small, uncertain, or structurally-complex-source subset
of it gets escalated to a separate (usually stronger-effort)
`escalation_model` rather than accepted outright. Whatever survives all
three tiers still broken lands in `review/needs_review.json` for a
human, without ever stopping the run for anything else in the project.

## Formats

Set `format:` in project.yaml. Adapter status, honestly:

| Format | Adapter | Notes |
|---|---|---|
| `generic_kv` | done | flat key to value JSON/YAML |
| `po_gettext` | done | standard GNU gettext, via `polib` |
| `ue4_5_po` | done | aliases straight to the po_gettext adapter (Unreal's Localization Dashboard export is standard gettext with `msgctxt` carrying the Unreal identity/namespace) -- but gets its own extra validator, see below |
| `unity` | done | official Unity Localization Package CSV export |
| `uabea_json` | done | raw UABEA asset-dump export (MonoBehaviour typetree, CSV-in-`m_Script`, or a flat JSON array) -- see "uabea_json noise filtering" below |
| `xliff` / `weblate_xliff` | done | both alias to the same XLIFF adapter |
| `renpy`, `ue3` | not implemented | no adapter, no validator, `get_adapter()` raises `NotImplementedError` naming the gap. Add both together (extract/merge + `validate_file`) if a project actually needs one -- carrying a validator with nothing to feed it is dead weight, not a head start. |

**`ue4_5_po`'s extra check:** Unreal's `{Arg}|plural(...)`/`gender(...)`/
`ordinal(...)` argument-modifier syntax isn't something a generic
placeholder check can see past the `{Arg}` part of. `validators/
validate_ue4_5_po.py` parses the modifier structure (respecting
Unreal's own quote-escaping inside clause values) and flags a missing
modifier or a dropped plural/ordinal branch as critical -- layered on
top of the same base checks `po_gettext` uses, not duplicating them,
and only registered for `ue4_5_po` so a plain gettext project pays
nothing for a check it will never trigger.

**`uabea_json` noise filtering:** its typetree/array-walk extraction
path (as opposed to the CSV-in-`m_Script` path, which reads a known,
validated column and needs none of this) has to guess which
string-valued fields in an arbitrary Unity object graph are narrative
text versus engine plumbing -- GUIDs, asset paths, enum constants,
indexed node names. `adapters/engine_noise.py` is a conservative,
one-sided filter (only ever says "this is definitely not translatable
text"; never guesses the other direction) that runs before an `Entry`
is even created. `format_options.uabea_json_path_exclude` is the
project-specific escape hatch (regex against the dotted json path,
skips the whole matched subtree) for whatever the built-in filter
doesn't catch. `locpipe audit` reports what got kept vs. filtered by
each mechanism, with examples, before you spend anything translating --
build the exclude list from one read of the report instead of guessing.

## Category routing

`project.yaml`'s `categories:` list matches entries via, in this
priority order: `match_speaker_present`, `match_key_regex`,
`match_notes_regex`, `match_source_regex` (checked against the actual
translatable text -- e.g. routing Unreal's argument-modifier syntax to
its own smaller-batch category). The `unity` adapter also writes a
`Type`/`content_type` CSV column's value into `entry.notes` as
`type:<value>`, reachable via `match_notes_regex`.

## Providers

Two, chosen via `provider.name` in project.yaml. The pipeline code
never changes -- only which one you point at.

- **`antigravity_cli`** -- the default. Shells out to the `agy` binary
  itself; nothing to configure beyond `agy auth login` if you're
  already using Antigravity CLI. `agy`'s non-interactive mode
  (`--print`) has a real, documented bug: called from a non-TTY
  context -- exactly what a subprocess call from Python is -- it can
  complete a full model round trip and print nothing to stdout while
  still exiting 0. `providers/antigravity_cli_provider.py` is hardened
  against this specifically: it never trusts exit code alone, and
  raises loudly on empty output instead of returning a hollow success.
  It also has no persistent client between calls, so it can't benefit
  from server-side prompt caching the way `gemini` can -- pipeline.py
  compensates by sending it a per-batch-pruned glossary and character-
  voice bible (just the terms/speakers actually in that batch) instead
  of the full category-level one, via
  `TranslationProvider.prefers_per_batch_context`.
- **`gemini`** -- direct Gemini API access via `google-genai`. Sync or
  Batch mode, with real server-side prompt caching (the full glossary
  and character-voice bible are sent once per category and reused,
  cheaper than per-batch pruning for any project with more than a
  couple of batches per category). Get a free-tier key at
  aistudio.google.com/apikey -- the same Google account `agy` itself
  authenticates against.

Switch anytime by editing `provider.name` -- nothing else in
project.yaml has to change. Worth switching to `gemini` if you want
batch-mode job submission (`antigravity_cli` doesn't support it, no
`submit_batch()`) or the prompt-caching cost benefit on a large,
many-batches-per-category project; `antigravity_cli` is otherwise a
perfectly fine default, hardened against its one known risk, and needs
no separate API key if you're already set up for `agy`.

`model` is the bulk-translate model. `review_model`/`review_effort`
(falls back to `model`/`effort` if unset) is used for the Tier-3
review/repair call; `escalation_model`/`escalation_effort` (falls back
to `review_model`, then `"high"`) is used for the small
uncertain/structurally-complex subset of that. See `locpipe init`'s
scaffolded project.yaml for current recommended defaults and the
reasoning behind them.

## Concurrency

- **Within a translate pass**, batches run concurrently
  (`asyncio.as_completed`, not `gather` -- one batch timing out doesn't
  discard every other batch's already-finished work), bounded by
  `provider.max_concurrency`.
- **Across files, in sync mode**: batches from up to
  `translate_file_window` pending files are pooled into one concurrent
  translate pass before any of them are validated/reviewed/merged --
  see `config.py`'s `translate_file_window` docstring for why this is
  windowed rather than whole-project (bounded memory, files still land
  within roughly one window instead of only after the entire project's
  translation finishes).
- **Review and Tier-1 repair calls** also run concurrently
  (`asyncio.gather`) rather than one chunk/category at a time -- the
  provider's own concurrency limit governs actual throttling either
  way, so awaiting them sequentially bought nothing.

## Caching

Two independent kinds, worth not confusing:

- **Server-side prompt caching** (`gemini` provider only --
  `antigravity_cli` has no persistent client to attach a cache to, see
  Providers above): `schemas.build_system_prompt_for_category()` builds
  one system prompt per category -- full glossary, style guide,
  anti-fabrication rules, character voices -- byte-identical for every
  batch sharing a category, which is what makes it a stable prefix
  `client.caches.create()` can reuse instead of re-paying for it on
  every batch. `GeminiProvider.cache_stats()` reports what it saved,
  and `locpipe run` prints it after a real run.
- **Local, in-process caching of static resources** (both providers):
  prompt templates (`translate.md`/`review.md`), `lang-style.md`,
  `anti-fabrication-checklist.md`, and `character-voices.md` are read
  from disk once per run (`functools.lru_cache`) rather than on every
  single batch call -- these are static project resources that don't
  change mid-run, so re-reading and re-parsing them per batch was pure
  overhead, most visible on `antigravity_cli`'s per-batch-pruned path
  since that one re-derives the character-voice subset every call
  regardless.

## Dedup and context keys

Every reuse/dedup decision -- both the persistent TM lookup and
within-run grouping -- is keyed on `(content_hash, category,
context_key)`, never on source text alone. Two entries with identical
source text are still different translation problems if a different
character says one of them, or if the same word means something
different in two contexts (a glossary can carry dual entries for
exactly this). `context_key.py` derives a context key from speaker to
notes to key-pattern to none, in that priority order, for formats that
don't carry one natively; `po_gettext.py` feeds gettext's own
`msgctxt` in directly instead of guessing, since that field already
*is* a context key.

Classification runs before deduplication in `pipeline.py`, and that
order is load-bearing: the dedup/TM key depends on category and
context_key, so deduping first would silently fall back to
raw-source-text keys, reintroducing the exact cross-context collision
this design exists to prevent.

## Translation memory

SQLite-backed (`tm.py`), keyed as above, and it persists -- a run's
fresh MT and reviewed output are committed back into it at the end of
`run()`, not just consulted at the start, so cross-run reuse is real,
not just within-run dedup. Writes are batched into one transaction per
file (`upsert_many`/`mark_used_many`) rather than one commit per
string.

## Scheduler / checkpoint (resuming a long run)

The unit of crash recovery is one input batch *file*. Each file goes
through extract, translate, validate, Tier-1 repair, review, merge,
commit-to-TM as one self-contained pass. `checkpoint.json`'s
`completed_files` list means a resumed run skips an already-finished
file entirely -- doesn't even re-extract it.

If anything raises unexpectedly while processing one file -- a bad
validator subprocess, malformed input, whatever -- that file is left
unfinished and the run **continues with the rest**, not halted
outright; recoverable on the next `locpipe run`.

- **Sync mode** -- a failed batch is logged, and the file(s) it belongs
  to are left unfinished rather than partially committed. Committing
  successfully-translated-but-not-yet-validated strings early, just to
  save re-translating them, would let unvalidated output get reused by
  unrelated future strings via the TM -- a worse trade than the extra
  retranslation cost. `checkpoint.get_batch_drafts()`/
  `save_batch_drafts()` give this finer-than-file granularity within a
  translate pass: a crash mid-pass resumes by skipping already-drafted
  batches, not re-translating the whole file's worth again.
- **Batch mode** -- covers every pending file in one submission (a
  Message Batch / Gemini Batch job can take up to 24-48h; waiting that
  out once per file, serially, would defeat the point). The job id is
  saved to `checkpoint.json` *before* the blocking wait, so a process
  restart reattaches to the exact job instead of resubmitting -- both
  providers document that batch creation isn't idempotent, so
  resubmitting is a duplicate charge, not a safe retry. The reattach is
  verified against a fingerprint of the batch content before trusting
  it. Once the job resolves, validating/reviewing/merging/committing
  still happens per file, so a crash during that pass isn't
  all-or-nothing either.

`locpipe run` prints progress as it goes rather than staying silent
until the end.

## Prompt templates

`locpipe/agents/translate.md` and `locpipe/agents/review.md` are the
actual instruction text sent to the model -- externalized rather than
hardcoded in `schemas.py`/`reviewer.py`. Tuning how the translator or
reviewer is instructed is a markdown edit; `%%TOKEN%%` placeholders get
filled in by `prompt_builder.py` at call time, and `translate.md`'s
character-voice section is wrapped in
`%%CHARACTER_VOICE_SECTION_START/END%%` markers kept or stripped per
category.

## Narrative-context batching (optional, per category)

```yaml
categories:
  - name: dialogue
    narrative_boundary_field: context_screen   # or any field a project's entries carry
    narrative_context_window: 4                # last N lines as {speaker, source} context
```

Two independent things, both opt-in:

- **Batching keeps a boundary group together.** Entries sharing the
  same value for `narrative_boundary_field` (a scene, a quest, whatever
  a project's format actually carries) get packed into the same batch
  instead of being split wherever a flat entry-count happened to land.
  A group bigger than `batch_size` still splits -- no way around that
  without breaking the size cap.
- **Preceding context.** Each entry can carry the last N lines *from
  the same boundary group* as `{speaker, source}` pairs -- surrounding
  dialogue for pronoun resolution and tone continuity. Deliberately
  scoped to the boundary group, not global file order, so a short
  scene's context can't get pulled from an unrelated scene that
  happened to precede it in the file. Never affects TM/dedup keys
  (still `content_hash + category + context_key`) -- prompt context
  only.

Both fields default to off -- a category that doesn't set them behaves
exactly as before.

## Adding a new format adapter

1. Implement `FormatAdapter.extract()` / `.merge()` in
   `adapters/<name>.py`. Reuse a real parser library if the format has
   fiddly syntax (see `po_gettext.py` using `polib` instead of
   hand-rolling .po parsing).
2. If the format has a native context/disambiguation field (gettext's
   `msgctxt`; some engines have similar), set `Entry.context_key`
   directly in `extract()` -- `classify.py` only falls back to guessing
   when an adapter hasn't already supplied one.
3. Write `validators/validate_<name>.py` -- `validate_file(path,
   glossary_entries) -> (critical, major, minor, info)` (four lists of
   message strings) for the common case; see `validators/registry.py`
   for the subprocess-wrapped alternative if a format needs
   command-line flags the shared signature has no room for.
4. Register both in `adapters/registry.py` and
   `validators/registry.py`.

## Running the tests

```bash
python3 -m pytest tests/ -q
```

Fixture-based (`tests/fixtures/demo_project` and similar -- each test
gets its own throwaway copy, never mutates the committed fixture) and
unit tests together, asserting on actual output, not just "it didn't
crash": dedup/context-scoping, broken-translation to review to repair,
plan()/run() agreement, TM entries surviving into a second run,
batch-mode job reattachment on a simulated restart, format-adapter
round trips (Unity CSV composite keys, UABEA noise filtering, Unreal
argument-modifier validation), narrative-boundary grouping, and
CLI-level smoke tests for `init`/`plan`/`run`/`audit`.
