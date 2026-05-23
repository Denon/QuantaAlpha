from __future__ import annotations

from collections.abc import Iterable


def normalize_instrument_set(instruments: Iterable[object] | None) -> set[str]:
    if instruments is None:
        return set()
    return {str(instrument) for instrument in instruments if instrument is not None}


def instrument_overlap_count(
    cached_instruments: Iterable[object] | None,
    target_instruments: Iterable[object] | None,
) -> int:
    return len(
        normalize_instrument_set(cached_instruments)
        & normalize_instrument_set(target_instruments)
    )


def should_reject_cached_factor(
    cached_instruments: Iterable[object] | None,
    target_instruments: Iterable[object] | None,
    min_overlap: float = 0.80,
) -> bool:
    """Reject cached factor when instrument overlap is below threshold.

    Overlap = len(cached ∩ target) / len(cached).
    Rejects when cached and target are both non-empty and overlap < min_overlap.
    """
    cached_set = normalize_instrument_set(cached_instruments)
    target_set = normalize_instrument_set(target_instruments)
    if not cached_set or not target_set:
        return False
    overlap = len(cached_set & target_set) / len(cached_set)
    return overlap < min_overlap
