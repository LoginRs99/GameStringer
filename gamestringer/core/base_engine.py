"""
BaseEngine Abstract Interface for GameStringer Engine Extensions.
"""

import re
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

SMART_TOKEN_PATTERN = re.compile(r"(\{[^{}]+\})")


@dataclass
class TransUnit:
    """
    Represents a single translatable text entry.
    """
    id: str
    source: str
    target: str = ""
    file_path: str = ""
    line_number: Optional[int] = None
    namespace: Optional[str] = None
    key: Optional[str] = None
    speaker: Optional[str] = None
    context_note: Optional[str] = None
    extra_metadata: Dict[str, Any] = field(default_factory=dict)


def validate_smart_tokens(source: str, target: str) -> List[str]:
    """
    Check if smart tokens in source text (e.g. {0}, {player_name}) are missing in target text.

    :return: List of missing token strings
    """
    if not source or not target:
        return []

    src_tokens = set(SMART_TOKEN_PATTERN.findall(source))
    tgt_tokens = set(SMART_TOKEN_PATTERN.findall(target))
    missing = list(src_tokens - tgt_tokens)
    return missing


class BaseEngine(ABC):
    """
    Abstract Base Class for all game engine extractors and patchers.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier name for the engine (e.g. 'renpy', 'unreal')."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of the engine."""
        pass

    @property
    @abstractmethod
    def supported_extensions(self) -> List[str]:
        """List of file extensions supported by this engine (e.g. ['.rpy'], ['.locres'])."""
        pass

    @abstractmethod
    def detect(self, input_path: str) -> bool:
        """
        Check whether this engine can handle the given file or directory.

        :param input_path: Path to file or directory
        :return: True if supported, False otherwise
        """
        pass

    @abstractmethod
    def extract(self, input_path: str, output_xliff_path: str, dry_run: bool = False) -> str:
        """
        Extract strings from game files and save to XLIFF 1.2 format.

        :param input_path: Path to game file or directory
        :param output_xliff_path: Target path for the output .xliff file
        :param dry_run: If True, scan files and report counts without writing files
        :return: Summary report message or output path
        """
        pass

    @abstractmethod
    def patch(self, input_path: str, xliff_path: str, output_path: Optional[str] = None) -> str:
        """
        Repatch game files using translated strings from an XLIFF file.

        :param input_path: Path to original game file or directory
        :param xliff_path: Path to translated .xliff file
        :param output_path: Optional output directory or path
        :return: Status message or path to patched files
        """
        pass
