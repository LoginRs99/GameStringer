"""Shells out to the `agy` (Antigravity CLI) binary directly, for
people who only have Antigravity CLI access and no separate
GEMINI_API_KEY for providers/gemini_provider.py.

Read this before using it for a real 50k+ row run:

`agy -p` / `--print` (non-interactive mode) has a real, currently open
bug: under a non-TTY context — exactly what a subprocess call from
Python is — it can complete a full model round trip and print NOTHING
to stdout, while still exiting 0. A pipeline that trusts exit code
alone will report success while silently translating nothing. This
isn't a one-off report; it shows up across multiple independent
write-ups from the last couple of months, with the same shape each
time ("worked in my terminal, empty in CI/subprocess").

Given that, this wrapper:
  1. never trusts exit code alone — every call requires the actual
     response text to parse as the expected JSON shape before it's
     accepted, matching the "two-stage gate" pattern the workaround
     writeups converge on;
  2. raises loudly (RuntimeError) on empty/unparseable output instead
     of returning a hollow success;
  3. uses ANTIGRAVITY_TOKEN for auth, not GEMINI_API_KEY -- agy
     ignores the latter entirely;
  4. does retry transient failures (rate limit, timeout, empty output --
     the silent-empty-output bug included, since a fixed short backoff is
     cheap insurance even though it isn't guaranteed to help with a
     harness-level bug) up to 5 attempts with backoff, but does NOT retry
     a non-zero exit with output on stderr -- that's treated as a real
     error (bad model name, auth failure, ...) worth surfacing immediately
     rather than burning attempts on something a retry can't fix;
   5. passes the prompt as a positional CLI argument to `agy --print`;
  6. asks pipeline.py for a per-batch pruned prompt instead of the
     category-level full-context one other providers get
     (`prefers_per_batch_context = True`) -- there's no persistent
     client here to cache the full glossary or character-voices file
     against, so sending them in full on every one-shot subprocess call
     would just be paying more tokens for nothing. Covers both: a
     dialogue batch only gets the voice-bible rows for the characters
     actually speaking in it, not the whole cast.

Flags below (`--print`, an auto-approve flag) are current as of the
sources checked while building this, but this CLI is genuinely
mid-flight — run `agy --help` and diff before trusting this against a
real 50k-row run, and validate with --limit 1 first (see the plan
command in cli.py) rather than finding out on batch 40.

If you can get a GEMINI_API_KEY at all (aistudio.google.com/apikey,
behavior to work around.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time

from .base import TranslationProvider

logger = logging.getLogger(__name__)

_BINARY = (
    shutil.which("agy")
    or shutil.which("agy.cmd")
    or shutil.which("agy.exe")
    or shutil.which("antigravity")
    or os.environ.get("ANTIGRAVITY_AGENTAPI_EXE")
    or os.environ.get("ANTIGRAVITY_CLI_EXE")
)


class AntigravityCLIProvider(TranslationProvider):
    #: No persistent client/cache between calls (each call is a fresh
    #: subprocess) -- get a per-batch pruned prompt (glossary and
    #: character voices both), not the category-level full-context one
    #: other providers benefit from caching.
    prefers_per_batch_context = True

    def __init__(
        self,
        model: str = "gemini-3.7-flash",
        max_concurrency: int = 2,
        timeout_s: int = 300,
        effort: str = "low",
    ):
        if _BINARY is None:
            raise RuntimeError(
                "agy not found on PATH. Install: curl -fsSL https://antigravity.google/cli/install.sh | bash"
            )
        if not os.environ.get("ANTIGRAVITY_TOKEN") and not os.environ.get("ANTIGRAVITY_CLI_AUTHENTICATED"):
            # best-effort check only -- agy may also be authenticated via system
            # keyring from an interactive `agy auth login`, which this can't see.
            pass
        self.model = model
        self.timeout_s = timeout_s
        self.effort = effort or "low"
        self._semaphore = asyncio.Semaphore(max_concurrency)

    def _run_agy(self, full_prompt: str, effort: Optional[str] = None) -> str:
        # To avoid Windows command-line character length limit (32,767 chars),
        # write the full prompt to a temporary UTF-8 text file and pass its path to `agy --print`.
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as temp_file:
            temp_file.write(full_prompt)
            temp_prompt_path = temp_file.name

        effective_effort = effort or self.effort
        args = [
            _BINARY,
            "--print",
            temp_prompt_path,
            "--model", self.model,
            "--dangerously-skip-permissions",
        ]

        if ("gemini-3" in self.model or "gemini-2" in self.model) and effective_effort:
            args.extend(["--effort", effective_effort])

        max_attempts = 5
        last_exit_code = None
        last_stderr = ""
        last_stdout = ""

        try:
            for attempt in range(max_attempts):
                attempt_num = attempt + 1
                try:
                    proc = subprocess.run(
                        args,
                        capture_output=True,
                        timeout=self.timeout_s,
                    )
                except subprocess.TimeoutExpired:
                    logger.warning(
                        "agy subprocess timed out after %ds on attempt %d/%d",
                        self.timeout_s,
                        attempt_num,
                        max_attempts,
                    )
                    if attempt == max_attempts - 1:
                        logger.error(
                            "agy timed out after %ds on all %d attempts",
                            self.timeout_s,
                            max_attempts,
                        )
                        raise RuntimeError(f"agy timed out after {self.timeout_s}s on every attempt ({max_attempts})")
                    time.sleep(3 * attempt_num)
                    continue

                stdout = proc.stdout.decode("utf-8", errors="replace").strip() if proc.stdout else ""
                stderr = proc.stderr.decode("utf-8", errors="replace").strip() if proc.stderr else ""
                last_exit_code = proc.returncode
                last_stderr = stderr
                last_stdout = stdout

                if proc.returncode == 0 and stdout:
                    return stdout

                if "RESOURCE_EXHAUSTED" in stderr or "429" in stderr:
                    logger.warning(
                        "agy rate limited on attempt %d/%d (exit code: %s, stderr: %r). Backing off...",
                        attempt_num,
                        max_attempts,
                        proc.returncode,
                        stderr[:300],
                    )
                    time.sleep(5 * attempt_num)
                    continue

                if proc.returncode != 0:
                    logger.error(
                        "agy subprocess failed on attempt %d/%d (exit code: %s, stderr: %r)",
                        attempt_num,
                        max_attempts,
                        proc.returncode,
                        stderr,
                    )
                    raise RuntimeError(f"agy exited {proc.returncode}: {stderr[:500]}")

                # If exit code was 0 but stdout is empty or whitespace-only (headless drop bug)
                if not stdout:
                    logger.warning(
                        "agy returned empty/silent stdout on attempt %d/%d (exit code: %s, stderr: %r). Retrying with backoff...",
                        attempt_num,
                        max_attempts,
                        proc.returncode,
                        stderr[:300],
                    )
                    time.sleep(2 * attempt_num)
                    continue

            logger.error(
                "agy failed after %d attempts. Last exit code: %s, stderr: %r, stdout length: %d",
                max_attempts,
                last_exit_code,
                last_stderr,
                len(last_stdout),
            )
            raise RuntimeError(
                f"agy failed after {max_attempts} attempts due to empty/silent output, timeout, or rate limit. "
                f"Last exit code: {last_exit_code}, stderr: {last_stderr[:500]!r}"
            )
        finally:
            if os.path.exists(temp_prompt_path):
                try:
                    os.unlink(temp_prompt_path)
                except Exception:
                    pass

    async def complete(
        self,
        system_prompt: str,
        user_payload: str,
        *,
        max_tokens: int = 8192,
        effort: Optional[str] = None,
    ) -> str:
        full_prompt = (
            f"{system_prompt}\n\n--- INPUT ---\n{user_payload}\n\n"
            "Respond with ONLY the JSON array described above. No other text."
        )
        if len(full_prompt) > 30000 and os.name == "nt":
            import warnings
            warnings.warn(
                f"Prompt length ({len(full_prompt)} chars) is close to the Windows 32,767 command-line limit. "
                "Consider reducing category batch_size in project.yaml."
            )
        async with self._semaphore:
            stdout = await asyncio.to_thread(self._run_agy, full_prompt, effort)

        # Gate 3: does it actually parse as the shape we asked for? An agent
        # harness is more likely than a raw completion API to wrap output in
        # commentary despite instructions -- strip a leading/trailing fence
        # and confirm before handing it back.
        text = stdout.strip().strip("`")
        if text.startswith("json"):
            text = text[4:].strip()

        start_idx = text.find("[")
        end_idx = text.rfind("]")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            text = text[start_idx : end_idx + 1]

        try:
            json.loads(text)
        except json.JSONDecodeError:
            import re
            text_clean = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", text)
            try:
                json.loads(text_clean, strict=False)
                text = text_clean
            except json.JSONDecodeError as e:
                raise RuntimeError(f"agy output didn't parse as JSON: {e}\nRaw output: {stdout[:500]!r}")
        return text
