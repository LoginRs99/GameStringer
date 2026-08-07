"""
Logging configuration for GameStringer CLI.
"""

import logging
import sys

logger = logging.getLogger("gamestringer")


def setup_logger(verbose: bool = False, quiet: bool = False):
    """
    Configure root logger for GameStringer CLI.

    :param verbose: Enable DEBUG logging level
    :param quiet: Show ERROR logging level only
    """
    logger.setLevel(logging.DEBUG if verbose else (logging.ERROR if quiet else logging.INFO))
    logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logger.level)

    formatter = logging.Formatter("[%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
