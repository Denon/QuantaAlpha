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
) -> bool:
    cached_set = normalize_instrument_set(cached_instruments)
    target_set = normalize_instrument_set(target_instruments)
    return bool(cached_set and target_set and cached_set.isdisjoint(target_set))
