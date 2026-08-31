from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AlignmentResult:
    start_offset_ms: float
    end_offset_ms: float
    clock_ratio: float
    residual_offsets_ms: list[float]
    confidence: float
    method: str
    low_confidence: bool


def estimate_from_sync_peaks(
    *,
    pc_start_ms: float,
    pc_end_ms: float,
    watch_start_ms: float,
    watch_end_ms: float,
    residual_offsets_ms: list[float] | None = None,
) -> AlignmentResult:
    """Map WatchTime = a * PcTime + b using SYNC_START/END peaks."""
    pc_span = pc_end_ms - pc_start_ms
    watch_span = watch_end_ms - watch_start_ms
    if pc_span <= 0 or watch_span <= 0:
        return AlignmentResult(
            start_offset_ms=watch_start_ms - pc_start_ms,
            end_offset_ms=0,
            clock_ratio=1.0,
            residual_offsets_ms=residual_offsets_ms or [],
            confidence=0.0,
            method="sync_tone",
            low_confidence=True,
        )
    ratio = watch_span / pc_span
    start_offset = watch_start_ms - ratio * pc_start_ms
    residuals = residual_offsets_ms or []
    # confidence heuristic
    conf = 0.95
    if residuals:
        max_abs = max(abs(x) for x in residuals)
        if max_abs > 500:
            conf = 0.4
        elif max_abs > 200:
            conf = 0.7
    low = conf < 0.6
    return AlignmentResult(
        start_offset_ms=start_offset,
        end_offset_ms=watch_end_ms - ratio * pc_end_ms,
        clock_ratio=ratio,
        residual_offsets_ms=residuals,
        confidence=conf,
        method="sync_tone",
        low_confidence=low,
    )


def watch_to_pc_ms(watch_ms: float, *, ratio: float, start_offset_ms: float) -> float:
    # WatchTime = a * PcTime + b  => PcTime = (WatchTime - b) / a
    if abs(ratio) < 1e-9:
        return watch_ms
    return (watch_ms - start_offset_ms) / ratio


def cross_correlate_offset(a: list[float], b: list[float]) -> tuple[int, float]:
    """Naive NCC peak index for envelope fingerprints (dev/test scale)."""
    if not a or not b:
        return 0, 0.0
    n = len(a)
    m = len(b)
    best_i = 0
    best = float("-inf")
    mean_a = sum(a) / n
    denom_a = sum((x - mean_a) ** 2 for x in a) ** 0.5 or 1.0
    for lag in range(-(m - 1), n):
        num = 0.0
        denom_b = 0.0
        count = 0
        mean_b_acc = []
        for i in range(n):
            j = i - lag
            if 0 <= j < m:
                mean_b_acc.append(b[j])
        if not mean_b_acc:
            continue
        mean_b = sum(mean_b_acc) / len(mean_b_acc)
        for i in range(n):
            j = i - lag
            if 0 <= j < m:
                num += (a[i] - mean_a) * (b[j] - mean_b)
                denom_b += (b[j] - mean_b) ** 2
                count += 1
        if count < 3:
            continue
        score = num / (denom_a * (denom_b**0.5 or 1.0))
        if score > best:
            best = score
            best_i = lag
    return best_i, float(best)
