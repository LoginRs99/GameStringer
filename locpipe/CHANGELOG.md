# Changelog

All notable changes to `locpipe` will be documented in this file.

## [0.18.0] - 2026-08-16

Full final-review pass before treating the pipeline as ready for real
production translation work: documentation accuracy, provider
reliability, a real end-to-end run against a UE4/5 fixture, and an
architectural evaluation of ideas from a separate translation project
(not adopted wholesale -- evaluated against locpipe's actual
architecture, most already covered better, one flagged as a real gap
and fixed, one flagged as actively wrong for Hungarian). Full findings
in the audit response; this entry covers what actually changed.

**Must-fix reliability bugs found and fixed (all four are instances of
the same root cause: a config value or provider capability that was
declared/loaded but never actually wired to anything):**

- `GeminiProvider.max_retries` was stored on `self` and never used --
  zero explicit retry/timeout for the `gemini` provider, silently
  relying on whatever the installed `google-genai` SDK version
  defaults to. Now wired into explicit `http_options` (retry_options +
  timeout) at client construction.
- `AntigravityCLIProvider._run_agy()`'s retry loop caught rate-limit
  and empty-output failures but not `subprocess.TimeoutExpired` -- a
  single slow call failed immediately with zero retries, unlike every
  other transient failure mode the same loop handles. Now retried with
  backoff like the others.
- `cli._build_provider()` never passed `config.provider.max_retries` to
  either provider constructor (both always used their class-level
  default of 5 regardless of project.yaml), and there was no way at
  all to configure a sync-mode per-call timeout from project.yaml --
  `provider.timeout_s` exists but is wired only to batch-mode's
  job-wait timeout (correctly, 24h default). New, distinctly-named
  `provider.sync_call_timeout_s` (default 300s) added and both values
  now actually threaded through to both providers.
- `pipeline.translate_one()` accepted a syntactically-valid JSON
  response that only covered SOME of a batch's entries as a full
  success -- the missing entries silently stayed `NOT_STARTED`, only
  caught much later by the file-level "unresolved" check, at which
  point the WHOLE file (including entries that translated fine) was
  marked unfinished and none of it reached the TM. Now treated the
  same as an invalid response, triggering the existing
  retry-with-correction loop within the same call.

**Silent TM corruption from `--dry-run` -- the most serious find.**
`locpipe run --dry-run` executes the real pipeline against
`MockProvider`, including committing "translated" output to the
TM -- with the exact same `origin="mt"`/`"reviewed"` tags a genuine
translation gets. A later real run's TM lookup couldn't tell the
difference, and would silently reuse `"[MOCK-HU] ..."` placeholder
text as if it were an actual translation. New
`TranslationProvider.persists_to_tm` flag (default `True`, `False` on
`MockProvider`) gates the TM-write calls in `_finalize_file()`.
Output-file writing during `--dry-run` is intentionally unchanged --
existing tests assert on it, and it's the file the user is directly
looking at (unlike a SQLite database most people would never think to
inspect), so the actual output-correctness check dry-run exists for
still works; only the TM's silent, persistent side effect is
suppressed.

**Documentation:** `README.md` fully rewritten -- the previous version
referenced a "MindsEye" project, `.agents/context/`, and several
`format-*.md` spec files that don't exist anywhere in this repo (an
inherited-from-elsewhere legacy narrative), undercounted providers as
"three" (it's two), mentioned `ANTHROPIC_API_KEY` for a provider
removed several versions ago, and had a Status section describing "7
tests" against the current 66. `PROJECT_SUMMARY.md` deleted outright --
duplicated README's job at version 0.8.0-level staleness (a `pip
install -e ".[all]"` instruction referencing an extra removed in
0.14.0, a module listing missing half the actual `adapters/`/
`validators/` files). `HASZNALAT.md`: removed a literally false claim
("if you already have an existing MindsEye project, this is your
situation") asserting the reader already had project data that doesn't
exist; genericized every `mindseye` example reference; documented the
new `sync_call_timeout_s`/`max_retries` fields, the `--dry-run`
TM-safety fix, and a real gap an end-to-end test surfaced (below).

**Found via an actual end-to-end run, not a unit test:**
`match_speaker_present` category rules never match anything for
`po_gettext`/`ue4_5_po` projects -- that adapter has no concept of a
"speaker" field (PO has no native one), so a project routing dialogue
via `match_speaker_present: true` would silently dump every entry,
narrative included, into the default/`ui` category with no
character-voice injection. Not a code bug to fix (there's no safe,
universal way to guess a speaker out of an arbitrary msgctxt naming
convention across different UE projects) -- documented with the actual
workaround (`match_key_regex` against the msgctxt, which IS present in
`entry.key`), confirmed working against a real fixture.

**Architecture: series/multi-game TM and glossary reuse.** Evaluated
whether previous games in a series should feed later ones. Verdict:
exact TM reuse and a shared glossary are both worth doing and both
already fully supported with zero code changes -- `tm.db_path` and
`resources.glossary` already accept paths outside a project's own
directory, so pointing every game in a series at the same shared TM
database and glossary file already works via the existing config
loader, no new mechanism needed.
Confirmed empirically (two throwaway mini-projects sharing one TM
file: the second project's identical string resolved from the first
project's TM with zero LLM calls) and confirmed the per-batch glossary
pruning (`prune_for_batch()`) means a shared, ever-growing series-wide
glossary costs no extra tokens per batch regardless of how large it
gets. Context retrieval from previous games (embeddings/RAG) evaluated
and rejected -- real ongoing engineering cost for an uncertain quality
benefit, versus the deterministic, already-available wins of TM +
glossary. Documented as a new HASZNALAT.md section with a working
example.

**Evaluated, not adopted, from a separate reference project:**
- Its TM idea: equivalent to what locpipe already has, and locpipe's
  version is more correct (context-key-scoped, so identical source
  text spoken by two different characters doesn't collapse into one
  reused translation the way a flat source-to-target TM would).
- Its "force-substitute glossary terms" idea: actively wrong for
  Hungarian specifically. `validators/glossary_terms.py`'s protected-
  term check deliberately does a prefix-only match on the target side
  (no trailing word boundary) because Hungarian glues grammatical
  suffixes directly onto words -- mechanical substitution can't
  produce a correctly-inflected sentence, only the current
  prompt-guided-translation-plus-morphology-aware-validation approach
  can.
- Its "AI refiner" second-pass idea: this is what `reviewer.py`
  already is, and locpipe's version is more capable -- it receives
  structured validator findings and confidence-flag reasons rather
  than just source-plus-context, runs a strict priority-ordered fix
  list, and (per the user's own stated cost concern) is applied
  selectively to flagged/sampled items, not every line.
- Its placeholder-tokenization idea (replace protected spans with
  opaque tokens like `[[T0]]` before sending to the model): correct
  and worth doing for pure substitution variables, but would silently
  break Unreal's `{Arg}|plural(...)/gender(...)` and Unity's SmartFormat
  plural syntax specifically, since the "protected" span there contains
  real translatable prose interleaved with structure, not an opaque
  value. Logged as a legitimate future idea IF measured repair-retry
  costs justify the real engineering effort to do the split correctly
  -- not implemented speculatively.
- Its reliability/bounded-run concern: already addressed by the
  retry/timeout fixes above, prompted directly by this same review.

## [0.17.2] - 2026-08-15

Review-tier model default: `gemini-3.1-pro` -> `gemini-3.7-flash` at
`review_effort: high` (unchanged -- was already `high`). Bulk stays
`gemini-3.7-flash` / `effort: low`, untouched.

Checked before switching, not assumed: Artificial Analysis's Intelligence
Index (Aug 2026, 9-benchmark composite covering knowledge work and
reasoning, not just coding) scores gemini-3.7-flash at high effort *above*
gemini-3.1-pro (56 vs 48), while gemini-3.1-pro's per-token output cost
runs roughly 3-5x higher. "Pro" isn't the automatic stronger-model pick
for review/repair anymore with this model generation -- same family at
high effort tests out ahead on both quality and cost for this specific
comparison.

`escalation_model` (the ~5% random-QA-sample + failed-repair tier) falls
back to `review_model` when left unset in project.yaml, as it always has
-- so this change also moves escalation onto gemini-3.7-flash unless a
project explicitly sets `escalation_model` to something else. Documented
explicitly in HASZNALAT.md and the `locpipe init` template's comments,
since it's an easy thing to miss (the cascade isn't visible from
`review_model` alone).

## [0.17.1] - 2026-08-15

Bulk-translate model default: `gemini-3.6-flash` -> `gemini-3.7-flash`
(released 2026-08-13, three weeks after 3.6 Flash). Verified before
switching: same 65,536-token output ceiling as 3.6 Flash (so
`max_output_tokens: 16384` needed no change), no removed/renamed API
parameters affecting how `antigravity_cli_provider.py` calls it. Updated
everywhere the old default was hardcoded (provider class default,
ProjectConfig default, config loader fallback, `locpipe init`'s scaffolded
project.yaml, docs, test fixtures) -- CHANGELOG entries before this one
are left alone since they're a historical record of what was true when
written, not the current default. `review_model` (`gemini-3.1-pro`) is
unrelated and untouched.

## [0.17.0] - 2026-08-15

Full-repo review specifically for Unreal Engine 4/5 and Unity translation
work, per direct request. Two categories of change: making UE4/5 a real,
tested first-class format, and fixing a default-config mismatch that was
already live for every format, not just UE/Unity.

**New: `format: ue4_5_po`.** Verified against Epic's own localization docs
that Unreal's Localization Dashboard .po export (both of its non-Crowdin
collapse modes) is standard gettext with msgctxt carrying Unreal's
identity/namespace -- the existing `po_gettext` adapter (polib-based)
already parses and round-trips it correctly with zero UE-specific code, so
`ue4_5_po` aliases straight to it (adapters/registry.py). What's genuinely
UE-specific: the `{Arg}|plural(...)/gender(...)/ordinal(...)` argument-
modifier syntax, which the existing placeholder check can't see past the
`{Arg}` part of -- so a translation that strips the entire `|plural(...)`
clause, or drops one plural/ordinal branch (e.g. "few" vanishes), passed
clean before and would only have broken at runtime in-game. New
`validators/validate_ue4_5_po.py` parses the argument-modifier structure
(with Unreal's own quote-escaping inside clause values handled correctly,
verified against real syntax examples including the quoted-comma edge
case) and flags missing modifiers/plural-keys as critical, gender-form-
count mismatches as major -- layered on top of validate_po_gettext.py's
existing checks, not duplicating them, and only registered for ue4_5_po so
plain po_gettext projects (Weblate, etc.) pay zero cost for a check they'll
never trigger.

Found and fixed in the process: `validate_po_gettext.validate_file()`
returned a 3-tuple (`critical, major, info`) while `validators/registry.py`
unconditionally unpacked 4 (`critical, major, minor, info`) for every
direct-import validator -- a crash, not a wrong-result bug. No test had
ever called `run_validator("po_gettext", ...)` or any format built on it
end to end, so this had been latent since po_gettext was first wired into
the registry. Fixed by adding the missing `minor` list.

**New: `CategoryRule.match_source_regex`.** Category rules could only match
on an entry's key, notes, or speaker-presence -- never the actual
translatable text. Needed for routing Unreal's argument-modifier syntax to
its own category (smaller batch = smaller blast radius per bad response),
but generically useful beyond that.

**Fixed: Unity CSV's `Type`/`content_type` column was extracted into
`entry.extra` and then never read by anything.** `CategoryRule.matches()`
never looks at `.extra`, so a project with an explicit type column --
common in real Unity exports, and a far more reliable classification
signal than guessing from speaker-presence or key patterns -- had no way
to actually use it. Now also written into `.notes` as `type:<value>`,
reachable via the existing `match_notes_regex`.

**Fixed: default `batch_size` (2000, 3000 for the init template's `ui`
category) violated config.py's own documented sizing rule** (`batch_size *
~25-35 tokens/entry` should stay under `max_output_tokens`) against the
old `max_output_tokens` default of 8192 -- by a factor of 6-10x. This
wasn't a hypothetical: it meant any new project created via `locpipe init`
using default settings would hit output-truncation failures (wasted
retries, then a whole file left unfinished) on any category with more than
roughly 250-300 entries. Verified `gemini-3.6-flash`/`gemini-3.1-pro`'s
actual output ceiling (65536 tokens) directly against their model cards
rather than assuming, then reconciled both sides: `max_output_tokens`
8192 -> **16384** (three call sites that had each hardcoded the same
number independently -- translate sync, translate batch-mode, review --
now all read the one config value), default `batch_size` 2000 ->
**350** (every place that number was duplicated: the dataclass default,
the config loader's fallback, and the single-implicit-category default),
init template's `dialogue` 800 -> **200** and `ui` 3000 -> **350**. This
is a project-type-agnostic fix, not UE/Unity-specific -- it was already
live for every format.

Also updated: `locpipe init`'s scaffolded project.yaml now lists every
currently-ported format by name (was a bare pointer to adapters/
registry.py) and includes two commented-out, ready-to-uncomment category
examples -- one for Unreal's argument-modifier routing, one for Unity's
`type:` note-based routing.

## [0.16.0] - 2026-08-14

`uabea_json`'s typetree/array walk (Case 2/3 -- e.g. LocalizedTextBank-style
MonoBehaviour exports) had no way to tell narrative/UI text apart from
Unity/UABEA internal plumbing (GUIDs, asset paths, enum constants, indexed
node names, ...) beyond a small fixed key-name denylist -- every other
string-valued field, regardless of content, was sent to the LLM as
"translatable." Case 1 (CSV inside m_Script) was and remains unaffected --
it already reads a known, validated column and never needed this.

**New: a conservative, one-sided engine-noise filter** (`adapters/
engine_noise.py`). Only ever answers "this is DEFINITELY not translatable
text" (GUIDs, hex colors, pure numbers/booleans, dotted type names like
`UnityEngine.UI.Button`, asset-file references, ALL_CAPS enum constants,
`name_001`-style indexed identifiers, and long spaceless PascalCase
compounds) -- anything it's not confident about, including every common
single-word UI label (Cancel, OK, Settings, ...), is left alone. On by
default; disable per-project with `format_options.noise_filter: false`.

**New: `format_options.uabea_json_path_exclude`** -- a project-specific
regex denylist matched against the dotted json_path (e.g.
`"^entries\\.internal_metadata"`). A match skips that field's whole
subtree, not just one leaf -- for whatever the built-in heuristic can't
(and, being deliberately conservative, won't) catch on its own.

**New: `locpipe audit --project <dir>`** -- read-only, no LLM calls, no
writes besides the report itself. Runs uabea_json's extraction across every
pending batch file and writes `<project>/audit_report.md` (or `--out`),
grouped by asset + path prefix, showing exactly what would be kept vs.
filtered as engine noise vs. filtered by an exclude pattern -- with
examples -- so a project's exclude list can be built from one read instead
of guessing, and the noise filter's false-positive risk can be checked
before spending a single real translation call on it. Formats without this
support (everything except uabea_json, for now) get a clear "not supported
yet" report instead of a crash or a silent no-op.

All three integrate the same way: extraction is unaffected for entries
that don't match either filter, `merge()` never touches a field that was
never extracted (nothing to reconstruct), and both filters are visible
end-to-end in the new `locpipe audit` report.

## [0.15.0] - 2026-08-13

Speed/token-efficiency pass on the actual hot paths of a real run, not
the architecture around them (dedup/TM/glossary-pruning/escalation
tiers are unchanged — they're the whole point of the token budget,
not overhead to trim). No format's behavior changed; all 29 tests
pass throughout.

**Cross-file translation concurrency in sync mode (biggest change).**
`run()`'s sync-mode file loop used to translate one file's batches at
a time -- concurrency (`provider.max_concurrency`) only ever applied
*within* a single file. A project made of many small files (one per
quest/level/asset, common) left most of that concurrency idle, since
most files don't even fill one batch. Batches from up to
`translate_file_window` pending files (new project.yaml key, default
8) are now pooled and translated in one concurrent pass before any of
them are validated/reviewed/merged/committed. Windowed rather than
whole-project on purpose: bounds peak memory to the window instead of
the whole project, and files still finish and land on disk within
roughly one window's time instead of only after every file in the
project has translated.

Found and fixed in the process: the file-done check (`unresolved =
[... e.status == NOT_STARTED ...]`) treated any file mixing
already-translated (human-provided) entries with new ones as
permanently unfinished, since an already-translated entry's `.status`
never leaves its dataclass default of NOT_STARTED even though it has
a perfectly good target. This existed identically in the pre-existing
batch-mode branch too, not just the new windowed code -- fixed in
both by also requiring `e.is_empty_or_stub` (only entries that
actually needed MT and still have no result count as unresolved).

**Review and Tier-1 repair calls run concurrently, not sequentially.**
`reviewer.review_batch()` chunked flagged entries and awaited each
chunk's LLM call one at a time in a `for` loop; `pipeline._tier1_repair()`
did the same per category. Both are now `asyncio.gather()` over
independent calls -- the provider's own concurrency limit (e.g.
AntigravityCLIProvider's internal semaphore) already governs actual
throttling, so the sequential `await` was pure idle wall-clock time
with zero benefit, on the same phase the bulk-translate step already
parallelizes.

**Prompt-building resource reads are cached.** `translate.md`/`review.md`
templates, `lang-style.md`, `anti-fabrication-checklist.md`, and
`character-voices.md` were re-read and re-parsed off disk on *every*
batch call (not once per category -- once per batch, unconditionally),
including a full character-voices.md table re-parse per batch for
antigravity_cli's per-batch-pruned path specifically. All now cached
(`functools.lru_cache`) for the run's lifetime -- these are static
project resources that don't change mid-run.

**TM writes batched into one transaction.** `TranslationMemory.upsert()`
and `.mark_used()` each committed (and fsynced) individually;
`dedupe.commit_to_tm()` and `enrich_and_dedupe()`'s TM-hit marking
called them once per entry. A large already-translated dump (a big
Unity/UABEA export) meant one disk sync per string. New `upsert_many()`
/ `mark_used_many()` wrap a whole file's worth of TM writes in a
single transaction; `dedupe.py` now uses them.

**Also fixed in passing:** the "nothing to do, already committed"
message always printed "1 file(s)" regardless of the actual count.

## [0.14.0] - 2026-08-12

Repo/scope cleanup pass — no pipeline behavior changed for any format
that already had a working adapter. Two goals: (1) strip everything
that was leftover from one specific translation job rather than part
of the reusable tool, (2) drop code paths the actual toolchain
(Antigravity CLI on a Gemini subscription, no separate paid API)
never exercises.

**Removed — one-off project artifacts, not part of locpipe itself:**
- `scripts/` — five ad-hoc scripts hardcoded to a single past project's
  paths (`projects/com/...`); not reusable, not project-agnostic.
- `tests/fixtures/test_fidelity/` — orphaned fixture, referenced by
  no test.
- `tests/test_uabea_json_adapter.py` — 4 of its tests depended on a
  local, non-portable Windows path outside the repo and could never
  pass elsewhere; rewritten against small inline fixtures instead,
  same coverage (adapter extraction, round-trip merge, translation
  round-trip, protected-token validation), zero external dependency.
- `__pycache__/`, `*.egg-info/` — build/runtime artifacts.
- A stray hardcoded fallback path to a different machine's `agy.EXE`
  location in `antigravity_cli_provider.py`.

**Removed — unused capability surface:**
- `providers/anthropic_provider.py` and the `anthropic` /
  `all` optional-dependency extras. Direct Claude API access; not
  part of the actual toolchain (Antigravity CLI / Gemini only), and
  every reference was in comments/docs, not load-bearing logic —
  removing it touched no pipeline behavior. `gemini` remains as the
  supported opt-in fallback for antigravity_cli's known headless-
  stdout bug (free-tier key, no separate paid subscription).
- `validators/validate_renpy.py`, `validate_ue3_int.py`,
  `validate_ue_po.py` — validators for formats (Ren'Py, UE3, UE4/5 PO)
  that never had a working extract/merge adapter to begin with, so
  they were unreachable from `locpipe run` regardless (`get_adapter()`
  raises `NotImplementedError` before validation would ever run).
  Carrying a validator with no adapter behind it isn't a head start,
  it's dead code with a docstring. Add both together if/when one of
  these formats is actually needed for a real project.

Net effect: same behavior for every format and provider actually in
use (generic_kv, po_gettext, xliff/weblate_xliff, unity, uabea_json ×
antigravity_cli/gemini), smaller surface area everywhere else.
All 29 tests pass after the cut.

## [0.13.0] - 2026-08-06

### The likely root cause of a real, reported quota problem
User reported a real run: 13,358 strings, only 27 LLM calls, consumed 70-80% of a Gemini
Pro session. Investigated with concrete math before proposing anything, rather than guessing.

- **`max_tokens` was hardcoded to `8192` in every single provider call site (5 of them),
  never scaled to the configured `batch_size`.** Computed the actual output budget needed
  for this project's own `batch_size` values: even the smallest (600, dialogue) needed an
  estimated ~9,750 tokens against the 8192 cap; the larger categories (3000/4000) needed
  6-8x more. A batch that can't fit gets a truncated, invalid-JSON response, which
  `parse_and_validate_response` correctly detects as an error -- which triggers a retry that
  resends the ENTIRE batch's input again (confirmed by reading `_translate_batches_sync`'s
  retry loop directly), up to `max_retries` (5) times, before giving up. For an
  undersized-relative-to-batch_size setup, this means paying for up to 5x the input tokens
  and 5x a full 8192-token (wasted, unparseable) output, for a batch that may never even
  succeed -- and this was **completely invisible**: `llm_calls_made` only ever counted
  batches attempted, never retry attempts within them, so nothing in `stats.json` could have
  told the user this was happening even if they'd looked.

### Added
- **`provider.max_output_tokens`** in `project.yaml` (default 8192, matching prior hardcoded
  behavior exactly -- no silent behavior change for anyone not touching this). Wired through
  all 5 call sites that were hardcoded before (`pipeline.py` x3 -- sync translate, batch-mode
  submission, Tier 1 repair; `reviewer.py` x1 for Tier 3; `review_batch()`'s own default).
- **`RunStats.wasted_retry_attempts`**: the actual instrumentation closing the visibility gap
  above. Every full-payload retry increments this, surfaced in both `stats.json` and the
  printed summary (only when non-zero, so a healthy run's output stays uncluttered) with a
  direct pointer to the likely fix (`batch_size` too large for `max_output_tokens`). Also
  prints inline the moment a batch succeeds after 1+ wasted attempts, naming which category
  and how many entries were in it, so this is visible during a live run, not just after.
- New test `test_wasted_retry_attempts_are_tracked_accurately`: a provider that fails a
  configurable number of times before succeeding, asserting the count is exactly right (3 --
  one wasted attempt per this project's 3 category batches), not just "some positive number."

### Changed
- **Demo `project.yaml`'s `batch_size` values reduced from 600/3000/4000 to 100/175/175**,
  computed (not guessed) from `max_output_tokens=8192`, a ~75% safety margin, and a
  conservative ~35-tokens-per-translated-entry estimate -- the same math now documented
  inline in `ProviderConfig.max_output_tokens`'s docstring so it doesn't have to be
  rederived next time. Counterintuitive but correct trade-off, stated explicitly in the
  comments: this means MORE separate calls for the same content, each paying the (already
  per-batch-pruned, for `antigravity_cli`) system-prompt overhead again -- but eliminates the
  far larger cost of batches that need multiple full-payload retries or fail outright.
  `dialogue` set tighter than `ui`/`developer_text` since natural dialogue lines, especially
  with `preceding_context` enabled, run longer per entry than a UI label.
- `provider.max_output_tokens: 8192` written out explicitly in the demo project.yaml (matches
  this file's existing convention of documenting fields even at their default) with a note
  that `batch_size` was sized against this specific number -- raising one should scale the
  other, not be tuned independently.

### Verified
- Full test suite: 15/15 passing, `pyflakes` clean, real CLI run clean -- confirmed the
  summary line correctly stays silent about wasted retries on a healthy run (no `⚠` line)
  rather than always printing a zero.
- Concrete math shown, not asserted: computed real estimated-output-tokens-needed for this
  project's actual (pre-fix) `batch_size` values against the actual hardcoded cap before
  proposing any fix, and computed the replacement values the same way rather than picking
  round numbers.

## [0.12.0] - 2026-08-06

### Went through every remaining resource/config section systematically, not just the two files explicitly requested

### Fixed — the significant one
- **`parse_glossary()` (`validators/glossary_terms.py`) has been silently non-functional for
  this entire project, since before this conversation started.** Found while writing a test
  to prove the `mechanic`/`lore` protected-term broadening from last version actually works
  end-to-end -- it didn't, and investigating why turned up a much bigger root cause than the
  test itself. The header-detection logic required the literal Hungarian string "Forrás
  kifejezés" to appear in the file before it would recognize any table rows at all;
  `glossary.md`'s actual header is in English ("Source term | Target translation | ...").
  Confirmed directly: `parse_glossary()` returned 0 entries, 0 issues for the real file.
  This function is a *shared* dependency of every format's validator (unity, po_gettext, ue3,
  renpy, weblate_xliff) and of `validate_glossary.py` (which checks the glossary file's own
  structural integrity) -- all of them were returning a false "clean, no issues" result
  because there was nothing to check, not because nothing was wrong. Fixed by accepting
  either language's header convention (matching how `glossary.py`'s own separate loader
  already correctly handled this), verified by re-parsing the real file afterward (4 entries
  found, not 0) and by the new end-to-end test below actually catching a violation for the
  first time.
- Docstrings and the violation message text itself (`glossary_terms.py`,
  `validate_generic_kv.py`) still said "brand name" specifically -- stale relative to last
  version's broadening to `mechanic`/`lore`. Reworded to "protected term" generally.

### Added
- **`glossary.md`**: two clean example rows (`Emberlight`/lore, `Overdrive`/mechanic, both
  marked "not translated") -- the file had zero entries demonstrating the "not translated"
  protected-term pattern at all before this, in either the original `brand` category or the
  newly broadened ones, which is exactly why the parser bug above went unnoticed for so long.
- **`test_broadened_protected_terms_catches_mistranslated_mechanic_term`**: real end-to-end
  proof, not a unit test of the filter logic in isolation -- a provider that mistranslates
  "Overdrive" (present in the new glossary entry) gets caught by the full pipeline and
  correctly appears in `needs_review.json` with the right message. This is what actually
  surfaced the parser bug above; it failed for a completely different reason than expected
  on the first run, which is what prompted digging into why instead of adjusting the
  assertion to match.
- **`anti-fabrication-checklist.md`**: one clarifying line distinguishing content fabrication
  (the checklist's actual concern) from the structural restructuring `lang-style.md`
  explicitly asks for -- otherwise the two resources could read as pulling in opposite
  directions on the same output.

### Fixed — caught before it shipped
- The anti-fabrication clarification above initially used a `%%TARGET_LANG%%` placeholder,
  by analogy with how `translate.md`/`review.md` handle language pairs. Checked whether it
  would actually get substituted before trusting it, rather than assuming: it would not have
  -- resource files (`glossary.md`, `lang-style.md`, `character-voices.md`,
  `anti-fabrication-checklist.md`) are read raw via `_read()` and inserted into the *already*
  `fill()`-processed template, so a placeholder inside their content is never touched and
  would have leaked into the live prompt as a literal, unfilled string -- confirmed this
  directly by rendering the prompt before fixing it. Fixed by using "Hungarian" directly,
  matching `lang-style.md`'s own established convention for this class of file (project-
  specific content correctly hardcodes the language; only the reusable, project-agnostic
  templates use placeholders).

### Checked, no change needed
- `translate.md`'s existing GENDER MARKER & TAG RULES (mechanical: fill both slots, preserve
  tag syntax) against `lang-style.md`'s new gender-neutrality section (content: usually
  identical Hungarian in both slots) -- complementary, not contradictory. Verified by reading
  both rather than assuming.
- `project.yaml`'s `batches`/`tm` sections -- purely mechanical, no language dependency.

### Changed
- Demo `project.yaml`'s own `provider` section still pinned `gemini-2.5-pro` with no
  `effort`/`review_model`/`review_effort` -- stale relative to every phase since the Phase 0
  default change. Confirmed safe to update before doing so: grepped for any test reading
  `provider.model`/`effort`/`review_model`/`review_effort` and found none, since
  `MockProvider`-based tests never go through `_build_provider()` at all (unlike
  `max_expansion_ratio`, which last version's investigation showed *does* affect real
  test-visible routing behavior and was correctly left as guidance instead of applied here).

### Verified
- Full test suite: 14/14 passing, `pyflakes` clean, real CLI run clean.
- `parse_glossary()` re-run directly against the real file post-fix: 4 entries, 0 issues
  (was 0 entries, 0 issues -- the dangerous kind of "clean").
- Rendered prompt confirmed to contain zero unfilled `%%...%%` placeholders anywhere.

## [0.11.0] - 2026-08-06

### Shift: content, not code
Confirmed last version that the pipeline itself is structurally complete; this pass is
entirely about the resource content that actually drives Hungarian output quality, plus one
small, deliberately narrow code change. No architecture changes.

### Changed
- **`resources/lang-style.md`** rewritten from one line to a real Hungarian style guide:
  register defaults by content type (this is now the authoritative source for it, not
  character-voices.md -- see Notes), gender-neutral handling of `{ms|...}{fs|...}` slots
  (default to identical Hungarian text, with a clear semantic-vs-grammatical test for when
  they should legitimately differ), focus/word-order guidance (Hungarian's topic-focus
  structure and preverb detachment, with verified example sentences), and agglutination/stem
  alternation (ló→lovak, kéz→kezet) with the practical implication for glossary terms spelled
  out explicitly.
- **`resources/character-voices.md`** rewritten to a full register system: UI/tutorial/system
  → magázás, dialogue → tegezés by default, per-character override table. Kael and Narrator
  preserved (existing tests reference these names) with enriched, more actionable trait
  descriptions.
- **`validators/glossary_terms.py`**: protected-term enforcement (the agglutination-aware
  prefix-matching check) broadened from `category: brand` only to also `mechanic` and `lore`
  -- categories where an inconsistent term is just as player-facing a problem as an
  inconsistent brand name. Only one internal caller, confirmed before changing it.

### Notes
- **Architecture detail that shaped how the content above is split**: `character-voices.md`
  is only ever injected into a prompt when a category has `needs_character_voice: true`
  (dialogue, in the demo project) -- confirmed this by checking `schemas.py` before writing
  anything, not assumed. A `ui`-category prompt never sees it at all. So the UI/tutorial/
  system → magázás rule had to live in `lang-style.md` (injected into every category
  unconditionally) to actually reach UI translations -- putting it only in
  character-voices.md would have made it dead instruction for every category except dialogue.
  Verified directly: rendered both a `ui` and a `dialogue` prompt and confirmed the register
  table reaches `ui` while Kael/Narrator's specific traits correctly don't (and that
  per-batch character pruning still works against the richer table).
- **Scope of the broadened protected-term check, stated precisely**: it only enforces terms
  the glossary marks "(not translated)" -- i.e. invented terms deliberately kept in the
  source language, not "always translate X as the same Hungarian word." Most mechanic/lore
  terms *are* meant to be translated, and enforcing consistency for a translated Hungarian
  form hits the exact stem-alternation problem `lang-style.md` describes above (a correctly-
  inflected form legitimately won't contain the dictionary-form term as a substring) -- so
  that broader guarantee isn't safe to add this way, and wasn't built.
- **`max_expansion_ratio`/`default_max_length` per-category config**: given as guidance in
  conversation rather than applied to the demo `project.yaml`. Checked first whether it was
  safe to bake illustrative numbers into the shipped fixture -- it isn't: the fixture's
  `ui`-category entries sit close enough to a plausible tightened threshold (verified one at
  a 1.4545 ratio specifically) that an invented "reasonable-sounding" value could flip
  `test_dedup_and_context_scoping`'s exact-count assertions for no real benefit, since actual
  UI-measured numbers can only come from the real game this pipeline is pointed at.

### Verified
- Full test suite: 13/13 passing, `pyflakes` clean, after both content rewrites and the
  code change.
- Parser-level check: `character_voices.py` still correctly parses the richer table and
  prunes per-batch (confirmed Kael-only pruning drops Narrator's row, keeps the shared
  register-system preamble).
- Prompt-level check: rendered an actual `ui` category prompt and confirmed it contains the
  style guide's register table but not `character-voices.md` content at all; rendered a
  `dialogue` prompt pruned to Kael and confirmed it contains both files' content with
  Narrator's traits correctly absent.

## [0.10.0] - 2026-08-05

### Fixed — a real bug, not a judgment call
- **`review.md` hardcoded "avoid calques from English sentence structure"**, regardless of
  the project's actual source language, and wasn't even routed through `fill()` -- so it
  couldn't have used a `%%SOURCE_LANG%%` placeholder even if it had had one. Accidentally
  correct for the demo fixture specifically (`source_lang: en`), which is why nothing caught
  it -- would have silently given wrong, misdirected guidance for any other language pair
  (the `children_of_morta` German-sourced project noticed at the very start of this whole
  effort would have been exactly such a case, had it ever been run through this). Fixed:
  `reviewer.review_batch()` now takes `source_lang`/`target_lang` and renders `review.md`
  through `fill()` like `translate.md` already does; the template states the actual
  language pair explicitly (it previously stated neither language at all) and phrases the
  naturalness rule generically instead of naming one specific source language.

### Added — the genuinely missing piece for dialogue naturalness
- **`translate.md` had extensive guidance on fidelity, glossary, tags, and length, but
  nothing telling the model to prioritize natural phrasing over a literal structural mirror
  of the source at all.** New `NATURALNESS` section: restructuring word order, splitting or
  joining clauses, and choosing an idiomatic phrase over a literal one are explicitly
  encouraged, and explicitly distinguished from the anti-fabrication rules (those are about
  *content*, this is about *sentence shape* -- restructuring freely while preserving meaning
  is not the same thing as inventing or dropping meaning). Calls out dialogue specifically:
  a short quip should usually get a short natural reply, not a grammatically correct but
  stiff full sentence just because the source wrote one.
- **Broadened `preceding_context`'s stated purpose** to match: previously scoped narrowly to
  disambiguation only (pronoun gender/number, tone continuity, agree/disagree), now also
  explicitly used to make a line read like a real next turn in the conversation, in the same
  register as what came before it -- not just grammatically consistent with it.
- `review.md`'s own naturalness priority (6) reworded to match: restructuring is fair game,
  distinguished from priority-3 fidelity, style guide's specific rules still take precedence
  where it has them.

### Verified
- New regression test confirms the fix is real, not just visually correct: renders `review.md`
  through `fill()` with the fixture's actual configured language pair and asserts "English"
  is no longer present and the correct source/target language is; separately renders
  `translate.md` for the `dialogue` category and confirms the new `NATURALNESS` section is
  present with the language pair correctly substituted in. Full suite: 13/13 passing,
  `pyflakes` clean, real CLI run clean.

### Notes — what this does and doesn't fix
This raises the ceiling; it doesn't replace what's actually the deepest lever for quality.
The demo fixture's `lang-style.md` is one line ("Default register: informal (tegező), unless
a character's voice entry says otherwise"). Prompt-level naturalness instructions can only
push a translation toward using natural sentence *shapes*; genuinely idiomatic word choice
and register for a *specific* language pair is exactly what a real, filled-out style guide
is for, and the pipeline's own architecture already treats that as project content, not
something to hardcode into the shared template. If the real project's `lang-style.md` is
similarly thin, that's very likely a higher-leverage next step than further prompt tuning --
happy to help draft one for the actual source language in use, once known.

## [0.9.0] - 2026-08-05

### Final audit pass — "connect everything, no dead code"
A systematic sweep of the whole package, not just the phases worked on so far, using
programmatic tools rather than eyeballing: an AST-based scan of every top-level function/class
for zero-reference definitions, a dataclass-field-by-field usage audit of every config class,
and `pyflakes` across the full source tree. Findings, each investigated individually before
being fixed or dismissed:

### Fixed
- **`RunStats.strings_saved_by_dedup_and_tm`** — a real, correctly-computed `@property` that
  was never actually reachable: not used in `summary()`, and invisible in `stats.json` too,
  since `write_stats()` used a plain `asdict()` which silently drops `@property` fields (only
  real dataclass fields get serialized). Wired into both instead of left orphaned.
- **Unused `Severity` import** in `pipeline.py`, and a **genuinely dead local variable**
  (`base_msgid`) in `adapters/po_gettext.py`'s `merge()` — leftover from an earlier version of
  the plural-form matching logic that got replaced by the OR-based lookup a few lines below,
  which already handles both plural indices correctly without it. Verified the actual matching
  logic first, to be sure removing it wouldn't silently break plural-form merging.
- **Documentation drift, actively contradicting current behavior** — the more serious kind of
  "not connected," found in three files:
  - `README.md`'s Providers section and `HASZNALAT.md`'s (the Hungarian day-to-day guide)
    provider table both still said "use `gemini`, not `antigravity_cli`" — directly
    contradicting 0.3.0's decision to make `antigravity_cli` the default. `HASZNALAT.md`'s
    example `project.yaml` also still showed `gemini-3.5-flash` with no `effort`/`review_model`/
    `tier1_repair_attempts` fields at all. Both rewritten to match current reality.
  - `README.md`'s Scheduler/checkpoint section described neither the pre-0.5.0 behavior
    (correctly) nor the post-0.5.0 one — it claimed per-*batch* TM commits, which was proven
    false back in 0.5.0's own audit and then replaced with genuine per-*file* granularity.
    Rewritten to describe what's actually true now, including 0.8.0's circuit-breaker
    isolation. Same fix applied to `HASZNALAT.md`'s section 8 (Hungarian).
  - `README.md`'s own "bugs found and fixed" narrative referenced `prefers_per_batch_glossary`
    by its pre-rename name (renamed in 0.6.0 to `prefers_per_batch_context`) — a stale symbol
    reference to something that no longer exists in the code.
  - `PROJECT_SUMMARY.md`'s "Release Notes" section was frozen at v0.2.0, six versions behind,
    with no mention of the provider-default change, per-file checkpointing, the 3-tier QA loop,
    or dynamic context assembly. Updated to a current high-level snapshot that points to this
    changelog for full detail rather than duplicating it inline.
  - Added a short paragraph to `README.md`'s phase table introducing the 3-tier QA/circuit-
    breaker system as a concept, which the table alone didn't surface anywhere.

### Investigated and confirmed NOT a bug
- UE3's `ref_path` gap (flagged in 0.6.0, left unfixed) turned out to be moot, not deferred:
  `adapters/registry.py` has no UE3 adapter at all yet (`get_adapter("ue3", ...)` raises
  `NotImplementedError` by design) — confirmed by actually calling it. Wiring `ref_path`
  in isolation, without an adapter to ever reach that code path, would be pointless. This is
  honestly-documented unfinished scaffolding (the module's own docstring says so plainly), not
  a silent disconnect in something that's supposed to already work — left alone on purpose.
- Two dataclass fields (`CategoryRule.match_speaker_present`, `ProjectConfig.batch_glob`)
  initially flagged by a naive cross-file usage count came back as false positives: both are
  correctly read, just from *within* `config.py` itself (as `CategoryRule.matches()` /
  `ProjectConfig.batch_files` methods), which a search excluding that file's own usage
  couldn't see. Confirmed by direct inspection before concluding either way.

### Verified — the actual "final test"
- Full test suite: 12/12 passing, `pyflakes` clean across `src/locpipe/`.
- One hand-built integration scenario exercising several systems together in a single run,
  not in isolation: three batch files, a string duplicated across files 1 and 2, a Tier-1-
  repairable placeholder defect in file 2, and file 3 deliberately malformed. Confirmed in one
  pass: cross-file TM dedup (the duplicate string sent to the LLM exactly once across the
  whole run, reused from the TM the second time), Tier 1 auto-repair (fixed without a review
  call), circuit-breaker isolation (file 3's crash didn't stop files 1/2 from completing), and
  crash-resume (a second run touched only file 3, zero calls referencing files 1/2's content).
  One assertion in this scenario initially failed and was investigated before concluding
  anything: it counted "Confirm" sent to the LLM across the *entire* run and expected zero,
  which was wrong -- file 1's own first-ever translation of "Confirm" is legitimate and
  necessary; the correct check is that it's sent *exactly once* overall, not resent for file
  2's duplicate. Fixed the assertion, not the pipeline, after confirming which one was wrong.
- Real CLI (`locpipe plan`, `locpipe run --dry-run`, then `run` again) against a fresh scratch
  project, confirming the full user-facing path -- not just the Python API -- still works
  end to end, including the resume-does-nothing-when-already-done case.

## [0.8.0] - 2026-08-04

### Audited — Phase 4 (Circuit Breaker / Self-Healing), against the actual run() code
Two real gaps found by tracing the code and reproducing each one before fixing it, plus one
config change honoring the phase's explicit numeric ask.

- **A crash in one file silently halted the entire run, not just that file — reproduced
  before fixing.** Built a minimal repro: three batch files, the second deliberately
  malformed. Confirmed `run()` raised all the way out and the third file -- perfectly fine,
  alphabetically after the broken one -- was never even attempted in that invocation. This
  directly contradicted "the pipeline must... continue processing the rest of the project":
  it only continued on the *next* invocation, not the current one, and only because 0.5.0's
  per-file checkpointing happened to make that recoverable. Fixed by wrapping each file's
  processing (both the sync-mode loop and both of batch-mode's loops) in a try/except that
  logs the failure, leaves that one file unfinished, and continues to the next file in the
  same run. Re-ran the exact repro after the fix: run() no longer raises, and the third file
  is correctly translated in the same invocation.
- **Tier 3's own repaired output was never re-validated — trusted on the review agent's
  word alone.** Traced the review-application code: the instant a repair came back without
  `flag_for_human`, it was merged, marked REVIEWED, and committed to the TM at that trust
  level, with no check that the repair itself actually passes the deterministic validators.
  A review agent that's wrong about having fixed something (e.g. still drops a placeholder
  while fixing tone) would ship that error AND propagate it to every future duplicate string
  via the TM, with nothing anywhere flagging it. Fixed: after applying and merging review
  repairs, re-run the real validator (cheap, deterministic, no LLM cost) on exactly the
  entries review touched. Anything still failing gets downgraded to BLOCKED instead of
  REVIEWED, excluded from the TM commit, and `needs_review.json` is updated to show the
  *current* still-failing issue rather than silently going quiet just because Tier 3 was
  attempted. Same verify-don't-trust principle 0.7.0's Tier 1 already applied to its own
  output, now applied consistently to Tier 3's.
- **`confidence.tier1_repair_attempts` default bumped from 1 to 2**, per the phase's explicit
  "2 or 3" ask. Documented the reasoning for picking 2 over 3 in the config comment (first
  retry catches the common case, a second has real if diminishing value, a third rarely earns
  its cost) -- easy one-line override to 3 if you'd rather lean further into exhausting cheap
  options before paying for review.

### Added
- Two new regression tests. `test_unexpected_file_crash_does_not_halt_the_run` reproduces the
  bug directly (a malformed batch file, then asserts a file after it still gets processed in
  the same run) rather than just asserting the fix in the abstract.
  `test_review_output_is_reverified_not_trusted` uses a review provider that always claims
  success while returning a still-broken repair, and asserts the entry ends up BLOCKED (not
  REVIEWED), the specific still-failing issue is visible in `needs_review.json`, and --
  checked directly against the TM's own sqlite table, not inferred -- the broken translation
  never got committed there.

### Verified
- Full pipeline exercised through the actual CLI again this phase, clean.
- Full test suite: 12/12 passing (10 previous + the two new tests above).

## [0.7.0] - 2026-08-04

### Audited — Phase 3 (Multi-Tiered QA Loop), against the actual routing code
- **Tier 1 (deterministic validation, reject-and-retry): real gap, now implemented.**
  Before this, EVERY validation failure -- a missing HTML tag, a dropped placeholder, the
  exact kind of thing a validator pins down with zero ambiguity -- was routed straight to
  Tier 3 (the expensive review agent), identically to a genuinely ambiguous glossary
  judgment call. There was no cheap, deterministic "reject and ask again" step at all.
- **Tier 2 (heuristic validation): the length-ratio half already existed** (0.4.0's
  configurable `max_expansion_ratio`). BLEU/chrF-against-TM does not, and after weighing it,
  recommending against building it for now -- see Notes below for the reasoning; open to
  revisiting if it turns out to matter in practice.
- **Tier 3 (LLM review agent): was receiving everything undifferentiated.** Now only
  receives what Tier 1 couldn't fix (after its bounded retry budget) or what Tier 1 never
  applied to in the first place (heuristic/fidelity flags) -- matches the phase's intended
  routing exactly, and no longer pays for the mechanical case.

### Added
- **`pipeline._tier1_repair()`**: on a validation failure (critical/major -- format, tags,
  placeholders, protected terms), retries the CHEAP bulk-translate call with the validator's
  own message attached verbatim as the correction request (no new message-generation logic
  needed -- the validator's message already ~~is~~ the "hard-coded error", since it's fully
  deterministic and involves zero LLM judgment to produce). Bounded to
  `confidence.tier1_repair_attempts` (default 1, configurable, 0 disables it) specifically so
  a stubborn defect can't become the unbounded self-correction loop this phase exists to
  prevent. Re-validates by re-merging to disk and re-running the real validator after each
  attempt rather than trusting the model's own claim that it fixed something.
- **`schemas.build_retry_payload()`**: same shape as the normal translate payload, plus
  `previous_attempt` and `issue` per item. New `CORRECTION MODE` section in `translate.md`
  explains these fields and instructs a surgical fix (change only what's flagged) rather than
  a full retranslation.
- **`entry.extra['_tier1_retry_exhausted']`**: set when Tier 1's retry budget runs out without
  fixing the issue. Surfaced as a `confidence_flags` entry so Tier 3 (if it's reached at all)
  knows a plain retry was already tried and failed -- `review.md` now explicitly tells the
  reviewer not to just attempt the identical fix again, but to read the source for why a naive
  fix wouldn't work (malformed source tags, an ambiguous double-use placeholder) before
  deciding whether this genuinely needs a human.
- **`RunStats.tier1_repaired`**, surfaced in `stats.json` and the run summary line, so it's
  visible how much Tier 1 is actually saving on a given project, not just that it exists.
- Two new tests: `test_tier1_repair_fixes_without_review_call` (the actual point of Tier 1 --
  proves a mechanical defect gets fixed without ever routing to the review agent for that
  reason) and an updated `test_broken_translation_gets_reviewed` (now documents and asserts
  the Tier-1-attempted-and-correctly-failed-then-fell-through-to-Tier-3 path explicitly,
  instead of leaving it as an untested side effect of the new code).

### Notes — why BLEU/chrF-against-TM isn't built
BLEU/chrF need a *reference* translation to score against. The TM only holds this pipeline's
own prior MT/reviewed output, not an independent ground truth, so the comparison would only
catch "this reads differently than how we translated something very similar before" -- a
real but narrow case, and one that needs fuzzy near-duplicate matching against the TM (not
just the exact-hash matching dedupe.py already does) to even find a comparison target. Given
this project's content is short UI/dialogue strings rather than long parallel prose, where
near-duplicates are the common case metric-based tools are built for, the
engineering-cost-to-value ratio looked poor next to what length-ratio + glossary consistency
+ exact-dedup reuse already cover. Flagging this reasoning explicitly rather than silently
skipping it, since it's a real option, just one that didn't clear the bar for this project as-is.

### Verified
- Full pipeline exercised through the actual CLI again this phase (`locpipe run --dry-run`
  against a scratch copy of the demo project), not just pytest -- confirmed `stats.json`'s new
  `tier1_repaired` field and the updated summary line both render correctly end to end.
- Full test suite: 10/10 passing (9 previous + `test_tier1_repair_fixes_without_review_call`).
  One assertion in that new test needed a fix mid-development: it initially asserted the
  Tier-1-fixed entry could never appear in the review queue at all, which was wrong --
  fidelity sampling independently guarantees at least one quality spot-check per category
  regardless of Tier 1, so it can legitimately land there for an unrelated reason. Fixed to
  check the precise claim instead (an empty `issues` list if it does appear there), verified
  by inspecting the actual review-queue JSON before deciding which assertion was correct.

## [0.6.0] - 2026-08-04

### Verified — full pipeline health check
- Ran the real CLI (`locpipe plan`, `locpipe run --dry-run`), not just pytest, against a
  scratch copy of the demo project: clean `plan` output, clean `run`, all output artifacts
  inspected by hand (`checkpoint.json` -- both `completed_batches` and the new
  `completed_files`, `stats.json`, the merged batch file, `review/needs_review.json`) and
  all correct. Ran `run` a second time against the now-fully-committed project and confirmed
  it does zero work ("1 file(s) already fully committed in a previous run -- skipping"),
  proving 0.5.0's checkpointing works end-to-end through the actual CLI, not just in tests.

### Audited — Phase 2 (Context Optimization), against the actual code
- **Dynamic glossary assembly: already implemented, confirmed correct, no changes needed.**
  `glossary.prune_for_batch()` already existed and was already wired into the translate
  path -- gated behind a provider flag so cache-capable providers (Anthropic, Gemini) still
  get the full glossary once (cheaper under caching) while `antigravity_cli` -- the current
  default, which has no caching at all -- already got a correctly pruned per-batch glossary.
  Traced this all the way through before concluding it needed no work.
- **Smart batching (group by content type, not file order): already implemented, no changes
  needed.** `batcher.py` has never batched by file order -- it's always grouped by category
  first (ui/dialogue/developer_text), with narrative-boundary-aware sub-grouping (packs
  whole scenes together) on top of that where a category defines one.
- **Character-voice profiles: real gap, found and fixed.** Unlike glossary, character-voices
  content had no per-batch pruning at all -- it was all-or-nothing per *category*
  (`needs_character_voice`), so a dialogue batch with lines from 2 characters still got the
  entire cast's voice bible every time, even on the no-caching default provider. Verified
  the gap directly against the demo fixture's own prompt output before fixing it.

### Added
- **`character_voices.py`**: parses `character-voices.md` into per-character rows (same
  table-row-filter spirit as `glossary.prune_for_batch`) and prunes to just the speakers
  present in a given batch.
- **`schemas.build_system_prompt_for_category()`** takes an optional `speakers` set now.
  `None` (default) = full voice bible, for the caching path. An actual set = pruned to those
  characters, for the no-caching path -- mirrors the existing glossary None-vs-pruned split
  exactly, including who calls it with which: batch-mode's category-level prompt cache still
  passes `None` (unchanged), sync mode's per-batch call passes the batch's actual speakers.
- Verified directly against the demo fixture: a `dialogue`-category prompt built for a
  Kael-only batch no longer contains "Narrator" at all, while the unpruned (`speakers=None`)
  version still does.

### Changed
- **Renamed `TranslationProvider.prefers_per_batch_glossary` -> `prefers_per_batch_context`**
  (`providers/base.py`, `antigravity_cli_provider.py`, `pipeline.py`'s check). The old name
  undersold what the flag now controls -- it always meant "no caching, so trim what you send
  me," and that now covers character voices as well as glossary, not glossary alone. Purely
  an internal implementation-detail rename; nothing in `project.yaml` changes.

### Notes
- Full test suite: 9/9 passing, unaffected (`MockProvider` doesn't set
  `prefers_per_batch_context`, so existing tests exercise the unchanged `speakers=None` path;
  the new pruning path was verified separately, directly against the demo fixture).

## [0.5.0] - 2026-08-04

### Changed — real per-file crash recovery, not just a progress log
- **`pipeline.run()` restructured around one input batch file as the unit of work.**
  Previously the whole run did three full passes over every file (translate everything,
  then validate everything, then review everything) with a single `commit_to_tm()` call
  at the very end -- so a crash or exhausted-retries failure anywhere in that window threw
  away every already-translated file's work, because nothing had reached the TM yet.
  Verified this was really happening (not just theoretically possible) before changing it.
  Now each file goes extract -> translate -> validate -> review/repair -> merge ->
  commit-to-TM as one self-contained unit before the next file starts.
- **`checkpoint.json` gained a real skip-list**, not just a log: `Checkpoint.mark_file_done()`
  / `is_file_done()`, backed by a new `completed_files` array. A resumed run skips
  already-finished files entirely (doesn't even re-extract them) rather than relying on
  the TM to make reprocessing them cheap-but-not-free.
- **Corrected `checkpoint.py`'s own module docstring**, which claimed sync mode already
  committed per-batch "not just once at the very end, which was the old behavior" -- traced
  the actual code and found that was describing intended behavior that was never actually
  implemented; the real behavior *was* "the old behavior" the comment said had been fixed.
  Docstring now describes what's actually true after this change.
- **Batch-mode (async job) submission deliberately stays project-wide, not per-file.**
  A Message Batch / Gemini Batch job can take up to 24-48h to resolve; submitting one job
  per file would mean waiting out that window once per file, serially -- the opposite of
  what batch mode is for. What's now per-file in batch mode is everything *after* the one
  job resolves: validate/review/merge/commit, protecting the (potentially large) post-
  resolution processing pass instead of the submission itself.
- **Fidelity sampling and narrative-context grouping are now scoped per file** (previously
  computed once across every file in the run). Disclosed trade-off: if a single narrative
  scene/boundary group is deliberately split across two separate batch input files, only
  within-file preceding-context will be available to the translator now. Not a concern for
  the common case (one file = one natural chunk like a quest/chapter), but worth knowing if
  your project's batch files are cut mid-scene.
- **Within a single file, a partially-failed batch still means the whole file retries next
  run**, not just the failed batch. Deliberate: committing a file's successfully-translated-
  but-not-yet-validated strings to the TM early, just to save that sub-file work, would let
  a translation that hasn't passed validation yet get reused by unrelated future strings --
  worse trade than the extra retranslation cost. File-level granularity was chosen as the
  safe boundary, not string-level.

### Added
- **`test_file_level_crash_resume`**: a real regression test, not just a prose claim.
  Two batch files; run #1 uses a provider that fails every request for file 2 (simulating
  a crash/rate-limit mid-run) but succeeds for file 1; run #2 uses a provider that never
  fails. Asserts file 1 is fully merged+committed+marked-done after run #1 despite file 2
  failing, and that run #2 never re-sends file 1's actual content to the provider (checked
  against the real per-item `source`/`current_translation` fields, not a raw substring
  match against the whole payload -- an early version of this test false-failed because the
  shared glossary text legitimately contains "Confirm", which isn't the same as re-sending
  file 1's entries).

### Notes
- Full test suite: 9/9 passing (8 previous + this new one).

## [0.4.1] - 2026-08-03

### Fixed
- **Restored the missing `tests/fixtures/demo_project/batches/batch_001.json`.** This file
  never shipped in the package (root cause of the 4 test failures noted in 0.3.0/0.4.0's
  changelog entries -- confirmed pre-existing on the untouched original zip, not introduced
  by this project). Reconstructed from the assertions in `test_pipeline.py` (8 entries: a
  3-way dedup group, a placeholder string with `max_length`, two identical-text dialogue
  lines from different speakers that must NOT dedupe together, one developer_text-category
  string, one already-translated string) and verified all 8 tests now pass, including the
  two real end-to-end pipeline tests that were failing before (`test_dedup_and_context_scoping`,
  `test_broken_translation_gets_reviewed`).
- **Ratio check in `confidence.py` now exempts source strings under 10 characters.**
  Restoring the fixture surfaced a real edge case in 0.4.0's new configurable expansion-ratio
  logic: `MockProvider`'s literal `"[MOCK-HU] "` prefix alone pushed a 7-character source
  string like "Confirm" to a 2.4x ratio, well past the new 1.6x default, and every short
  string in the demo project got routed to review. Investigated further and this isn't just
  a mock-provider artifact -- ratio math is inherently noisy on short strings even for real
  translations ("OK" -> "Rendben" is a completely normal Hungarian translation at a 3.5x
  ratio). Below 10 source characters, the ratio ceiling/floor check is now skipped entirely;
  `max_length` (an absolute, known limit) is the correct guard for short strings, not a ratio.

### Notes
- Full test suite: 8/8 passing, up from 4/8 in every prior zip handed over this project
  (0.2.0 through 0.4.0), all confirmed against the same fixture-restoration fix.

## [0.4.0] - 2026-08-03

### Changed
- **Expansion-ratio ceiling is now configurable, was a hardcoded `3.0`.** New
  `confidence.max_expansion_ratio` in `project.yaml` (default `1.6`), overridable per
  category via `CategoryRule.max_expansion_ratio` (e.g. `ui: 1.3`, `dialogue: 1.8`).
  `confidence.score()` / `needs_review()` now take an optional `config` argument to
  resolve the right limit; `pipeline.py`'s two call sites were previously calling both
  without passing `config` at all, so this is also a real wiring fix, not just a new knob.
- **`translate.md` now explains the `max_length` field.** It was already being sent to the
  LLM in the per-item JSON payload (`schemas.py`) but nothing in the prompt ever told the
  model what it meant or that it should be respected — a silently-inert field. Added a
  `LENGTH RULES` section: respect `max_length` when present, and generally prefer concise
  phrasing over padding regardless of whether a hard limit is known.
- **`review.md` gets a new priority-4 "Length" repair step** and now explicitly tells the
  reviewer to check the new `confidence_flags` array, not just `issues`.

### Added
- **`confidence_flags()`** in `confidence.py`: turns every heuristic deduction (length
  overrun, disputed glossary term, speaker uncertainty, unchanged-from-source) into a
  plain-text reason. Previously these deductions lowered an entry's score with zero trace
  of *why* anywhere in the review queue -- `ReviewItem`/`review_queue.py` could carry an
  empty `issues` list and confidence 0.7 with no explanation. Now surfaced as
  `ReviewItem.confidence_flags` and written into `review_queue.json`.
- **`CategoryRule.default_max_length`**: a static per-category fallback length limit,
  applied once in `classify.py` right after category assignment, for any entry whose
  adapter had no real per-row length data. Exists because Unity CSV and `.po` -- the two
  ported formats besides `generic_kv` -- have no native notion of a UI character limit at
  all, so `max_length` was structurally dead for every entry that came through them.
- **Unity CSV adapter can now read a real per-row length column**, via the new
  `format_options.max_length_column_names` (also auto-detects `max_length`/`char_limit`/
  `character_limit` column names heuristically, same style as the existing id/source/
  target detection in this adapter). Opt-in and additive to `default_max_length` above --
  use the real column when your export has one, the static fallback when it doesn't.

### Notes
- Audited for the same class of gap elsewhere: found that UE3's validator only runs
  glossary/protected-term checks when given a `--ref` (original-file) path, and
  `pipeline.py` never supplies one for the `ue3` format -- so glossary validation silently
  never runs on UE3 projects at all. Not fixed in this pass (only matters once UE3 is
  actually in use; the adapter itself isn't ported yet either, per `adapters/registry.py`).
  Flagged here rather than left for someone to rediscover.
- Ran the full test suite before and after this change -- same 4 pre-existing failures
  both times (a fixture/path issue unrelated to this work, first confirmed against the
  untouched 0.3.0 zip), nothing new broken.

## [0.3.0] - 2026-08-03

### Changed
- **`antigravity_cli` is now the default provider** (was `anthropic`). `ProviderConfig.name`
  defaults to `antigravity_cli`, and the `locpipe init` scaffold template now writes it as the
  first, uncommented choice. `anthropic` and `gemini` are unchanged and fully supported --
  purely opt-in now, switched by editing `provider.name` in `project.yaml`, no code touched.
- **Default bulk-translate model → `gemini-3.6-flash`** (was `claude-sonnet-5`).
- **Default review/QA model → `gemini-3.1-pro`**, wired through the same `review_model`
  fallback path that already existed (defaults to `model` if left unset).

### Added
- **Configurable `--effort` level for `antigravity_cli`**: new `provider.effort` and
  `provider.review_effort` fields in `project.yaml` (`low` | `high`). Previously this was
  hardcoded to `--effort low` for every `gemini-3.x` model regardless of which model or
  phase was running. Bulk-translate now defaults to `effort: low` (throughput), review/QA
  defaults to `effort: high` (Phase 13 repair is low-volume, so the extra reasoning cost is
  cheap) -- both are one-line overrides in `project.yaml`, `low` is equally valid for review
  if you'd rather optimize for cost/speed there instead.
- `cmd_run` now builds a separate review provider whenever *either* `review_model` or
  `review_effort` differs from the bulk-translate settings (previously only checked
  `review_model`), so a review-only effort bump no longer silently gets ignored.
- Ignored by `anthropic`/`gemini` providers -- `effort` is an `antigravity_cli`-only CLI flag,
  not a universal concept, so it's a no-op (not an error) if set while using another provider.

### Notes
- No `projects/` directories ship in this package -- this changelog entry applies to the
  tool's defaults only. Existing per-project `project.yaml` files are untouched by this
  change; only new projects created via `locpipe init` (or configs missing these keys
  entirely) pick up the new defaults.

## [0.2.0] - 2026-07-27

### Added
- **Gemini 3.6 Flash Support**: Upgraded `mindseye` project configuration to `gemini-3.6-flash`, improving output token efficiency by ~17% and agentic reasoning speed.
- **Antigravity CLI Effort Flagging**: Added automatic `--effort low` argument for Flash model CLI invocations.

### Fixed
- **Windows UTF-8 Encoding Crash**: Enforced `utf-8` decoding on `stdout` and `stderr` in `AntigravityCLIProvider` to prevent Windows `cp1252` charmap crashes on special characters (e.g. `⚠`).
- **Positional CLI Argument Handling**: Aligned `AntigravityCLIProvider` argument passing with `agy --print` positional requirements.

### Changed
- **Production Config Alignment**: Updated default provider configuration to `antigravity_cli` in `sync` mode.
