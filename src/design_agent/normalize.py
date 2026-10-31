"""Name normalization for origin matching (Stage 8 checks 6 and 7)."""

import re

from .constants import SAFE_SUFFIXES


def norm_entity(name: str) -> str:
    """lowercase, strip spaces/underscores/hyphens. Entities never lose suffixes."""
    return re.sub(r"[\s_\-]+", "", name.lower())


def field_variants(name: str) -> set[str]:
    """Return {full, suffix-stripped} normalized forms.

    Both sides of a comparison are expanded the same way, so `accountId`,
    `account_id` and `account` all meet at "account" or "accountid".
    """
    base = re.sub(r"[\s\-]+", "_", name.lower())
    variants = {base.replace("_", "")}
    for suffix in SAFE_SUFFIXES:
        if base.endswith(suffix) and len(base) > len(suffix):
            variants.add(base[: -len(suffix)].replace("_", ""))
            break
    return variants
