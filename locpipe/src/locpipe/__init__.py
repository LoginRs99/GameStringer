"""locpipe — a reusable, multi-project localization pipeline.

Design rule that everything else in this package follows:
the LLM translates and repairs language. Python does the rest
(extraction, batching, caching, translation memory, validation,
merging, statistics). No project name, language pair, or format
is hardcoded anywhere in this package — those live in a project's
project.yaml under projects/<name>/.
"""

__version__ = "0.1.0"
