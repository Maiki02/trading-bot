"""
Centralized bootstrapper for the pyquotex library.
Standardizes the prioritization of local versus remote versions.
"""

import sys
import logging
from pathlib import Path
from config import Config

logger = logging.getLogger(__name__)

def _bootstrap_local_pyquotex() -> None:
    """
    Checks if USE_QUOTEX_LOCAL is enabled in development.
    If so, inserts the sibling ../pyquotex directory into sys.path.
    """
    if Config.APP_ENV != "development":
        return

    if not getattr(Config, "USE_QUOTEX_LOCAL", False):
        return

    # Repository root (trading-bot)
    repo_root = Path(__file__).resolve().parents[2]
    # Sibling directory (../pyquotex)
    local_pyquotex_dir = repo_root.parent / "pyquotex"

    if local_pyquotex_dir.is_dir():
        local_repo_root = str(local_pyquotex_dir)
        if local_repo_root not in sys.path:
            sys.path.insert(0, local_repo_root)
            logger.info(f"Prioritizing local pyquotex from: {local_repo_root}")
    else:
        logger.warning(
            f"USE_QUOTEX_LOCAL is true, but directory '{local_pyquotex_dir}' was not found. "
            "Falling back to installed library."
        )

# Run bootstrap on module import
_bootstrap_local_pyquotex()

# Export common pyquotex components
try:
    from pyquotex.stable_api import Quotex
    from pyquotex.utils.processor import process_tick
except ImportError as exc:
    logger.error(f"Failed to import pyquotex: {exc}")
    # Re-raise to alert the user that the dependency is missing
    raise ImportError(
        "pyquotex is required for Quotex operations. "
        "Ensure it is installed from requirements.txt or available at ../pyquotex."
    ) from exc
