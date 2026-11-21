"""Mode B (estimated) arithmetic: sampling, labels with uncertainty, confidence intervals.

Used when an answer needs more records than can be read in full, or when the labels
themselves are LLM judgements. The LLM only labels sampled records; every estimate and
interval here is computed in code, with a fixed seed so results are reproducible.

- `stratified_sample` draws a proportional random sample per stratum (entity / period scope).
- `soft_labels` turns several labelling passes into a probability per record.
- `share_estimate` / `mean_estimate` / `difference_estimate` give a point estimate with a
  95% interval: Wilson for hard 0/1 shares, bootstrap otherwise, with a finite-population
  correction when a large part of the population was sampled.
"""
from __future__ import annotations
import math
import random
from collections import Counter

Z95 = 1.959963984540054
BOOTSTRAP = 2000


def stratified_sample(strata: dict, total: int, seed: int = 42, min_per_stratum: int = 1):
    """Proportional random sample of about `total` items across strata.

    strata: {label: [items]}. Returns ({label: [sampled items]}, {label: population size}).
    Each non-empty stratum gets at least `min_per_stratum` items (when it has them); a
    stratum smaller than its share is taken whole.
    """
    rng = random.Random(seed)
    sizes = {k: len(v) for k, v in strata.items()}
    population = sum(sizes.values())
    if population == 0:
        return {k: [] for k in strata}, sizes
    if total >= population:
        return {k: list(v) for k, v in strata.items()}, sizes
    alloc = {k: min(n, max(min_per_stratum if n else 0, round(total * n / population))) for k, n in sizes.items()}
    sample = {}
    for k, items in strata.items():
        idx = sorted(rng.sample(range(len(items)), alloc[k]))
        sample[k] = [items[i] for i in idx]
    return sample, sizes


def soft_labels(passes):
    """Per-record probability that the label is positive, from several labelling passes.

    passes: one list per pass, aligned by record, of True/False/None (None = no answer).
    """
    out = []
    for votes in zip(*passes):
        known = [bool(v) for v in votes if v is not None]
        out.append(sum(known) / len(known) if known else None)
    return out


def majority_category(passes):
    """Per-record (category, agreement) from several categorical labelling passes."""
    out = []
    for votes in zip(*passes):
        known = [v for v in votes if v not in (None, "")]
        if not known:
            out.append((None, 0.0))
            continue
        cat, n = Counter(known).most_common(1)[0]
        out.append((cat, n / len(known)))
    return out


def wilson_interval(successes: float, n: int, z: float = Z95):
    if n == 0:
        return (float("nan"), float("nan"))
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _fpc(n, population):
    """Finite-population correction factor for the interval half-width."""
    if not population or population <= 1 or n >= population:
        return 0.0 if population and n >= population else 1.0
    return math.sqrt((population - n) / (population - 1))


def _shrink(estimate, lo, hi, factor):
    return (estimate - (estimate - lo) * factor, estimate + (hi - estimate) * factor)


def _bootstrap(values, stat, seed=42, b=BOOTSTRAP):
    rng = random.Random(seed)
    n = len(values)
    draws = sorted(stat([values[rng.randrange(n)] for _ in range(n)]) for _ in range(b))
    return draws[int(0.025 * b)], draws[int(0.975 * b) - 1]


def _mean(xs):
    return sum(xs) / len(xs)


def share_estimate(probs, population=None, seed=42):
    """Share of positive records, from hard (0/1) or soft (probability) labels."""
    probs = [p for p in probs if p is not None]
    n = len(probs)
    if n == 0:
        return {"estimate": None, "ci_low": None, "ci_high": None, "n": 0, "population": population, "method": "none"}
    est = _mean(probs)
    if all(p in (0, 1, 0.0, 1.0) for p in probs):
        lo, hi = wilson_interval(sum(probs), n); method = "wilson"
    else:
        lo, hi = _bootstrap(probs, _mean, seed); method = "bootstrap (soft labels)"
    factor = _fpc(n, population)
    if factor < 1:
        lo, hi = _shrink(est, lo, hi, factor); method += " + finite-population correction"
    return {"estimate": est, "ci_low": lo, "ci_high": hi, "n": n, "population": population, "method": method,
            "exact": bool(population) and n >= population and all(p in (0, 1) for p in probs)}


def mean_estimate(values, population=None, seed=42):
    values = [float(v) for v in values if v is not None]
    n = len(values)
    if n == 0:
        return {"estimate": None, "ci_low": None, "ci_high": None, "n": 0, "population": population, "method": "none"}
    est = _mean(values)
    lo, hi = _bootstrap(values, _mean, seed) if n > 1 else (est, est)
    method = "bootstrap"
    factor = _fpc(n, population)
    if factor < 1:
        lo, hi = _shrink(est, lo, hi, factor); method += " + finite-population correction"
    return {"estimate": est, "ci_low": lo, "ci_high": hi, "n": n, "population": population, "method": method,
            "exact": bool(population) and n >= population}


def difference_estimate(a, b, seed=42, b_draws=BOOTSTRAP):
    """Difference of means b − a (e.g. after − before) with a bootstrap 95% interval."""
    a = [float(x) for x in a if x is not None]
    b = [float(x) for x in b if x is not None]
    if not a or not b:
        return {"estimate": None, "ci_low": None, "ci_high": None, "n_a": len(a), "n_b": len(b)}
    rng = random.Random(seed)
    draws = sorted(_mean([b[rng.randrange(len(b))] for _ in b]) - _mean([a[rng.randrange(len(a))] for _ in a])
                   for _ in range(b_draws))
    return {"estimate": _mean(b) - _mean(a), "ci_low": draws[int(0.025 * b_draws)],
            "ci_high": draws[int(0.975 * b_draws) - 1], "n_a": len(a), "n_b": len(b), "method": "bootstrap"}


def category_shares(categories, population=None):
    """Share of each category with Wilson intervals, most common first."""
    known = [c for c in categories if c not in (None, "")]
    n = len(known)
    out = []
    for cat, k in Counter(known).most_common():
        lo, hi = wilson_interval(k, n)
        factor = _fpc(n, population)
        est = k / n
        if factor < 1:
            lo, hi = _shrink(est, lo, hi, factor)
        out.append({"category": cat, "count": k, "estimate": est, "ci_low": lo, "ci_high": hi})
    return {"n": n, "population": population, "categories": out}


def stratified_estimate(strata: dict, seed: int = 42, b: int = BOOTSTRAP):
    """Population-weighted mean over strata, with a stratified bootstrap 95% interval.

    strata: {label: (values, population)} where values are 0/1 labels, soft-label
    probabilities or numbers for one stratum (e.g. one country or period). Each stratum is
    weighted by its population share, so an over- or under-sampled stratum doesn't bias the
    pooled estimate.
    """
    usable = {k: ([float(v) for v in vals if v is not None], pop) for k, (vals, pop) in strata.items()}
    usable = {k: (v, pop) for k, (v, pop) in usable.items() if v and pop}
    if not usable:
        return {"estimate": None, "ci_low": None, "ci_high": None, "n": 0, "population": 0, "method": "none"}
    total = sum(pop for _, pop in usable.values())
    weights = {k: pop / total for k, (_, pop) in usable.items()}
    est = sum(weights[k] * _mean(v) for k, (v, _) in usable.items())
    rng = random.Random(seed)
    draws = sorted(sum(weights[k] * _mean([v[rng.randrange(len(v))] for _ in v]) for k, (v, _) in usable.items())
                   for _ in range(b))
    n = sum(len(v) for v, _ in usable.values())
    lo, hi = draws[int(0.025 * b)], draws[int(0.975 * b) - 1]
    factor = _fpc(n, total)
    if factor < 1:
        lo, hi = _shrink(est, lo, hi, factor)
    return {"estimate": est, "ci_low": lo, "ci_high": hi, "n": n, "population": total,
            "method": "stratified bootstrap", "exact": n >= total}


def stratified_difference(group_a: dict, group_b: dict, seed: int = 42, b: int = BOOTSTRAP):
    """Difference b − a of two stratified estimates (e.g. after − before), bootstrap 95% interval."""
    ea, eb = stratified_estimate(group_a, seed), stratified_estimate(group_b, seed + 1)
    if ea["estimate"] is None or eb["estimate"] is None:
        return {"estimate": None, "ci_low": None, "ci_high": None, "before": ea, "after": eb}
    rng = random.Random(seed)
    def draw(group):
        usable = {k: ([float(x) for x in v if x is not None], pop) for k, (v, pop) in group.items()}
        usable = {k: (v, pop) for k, (v, pop) in usable.items() if v and pop}
        total = sum(pop for _, pop in usable.values())
        return sum(pop / total * _mean([v[rng.randrange(len(v))] for _ in v]) for v, pop in usable.values())
    diffs = sorted(draw(group_b) - draw(group_a) for _ in range(b))
    return {"estimate": eb["estimate"] - ea["estimate"], "ci_low": diffs[int(0.025 * b)],
            "ci_high": diffs[int(0.975 * b) - 1], "before": ea, "after": eb, "method": "stratified bootstrap"}

