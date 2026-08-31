#!/usr/bin/env python3
"""Proportions from a stratified sample, with honest error bars.

Stage 2 draws different fractions of different strata: 7 of 7 from one cell,
8 of 46 from another. A raw hit rate over the pooled sample would therefore
answer a question nobody asked, weighting each cell by how many pages we chose
to label rather than by how many pages exist.

This module exists so that the weighting and the correction are written down
once, before any label exists, and cannot be adjusted after seeing a number.
See docs/labeling-protocol-stage2.md.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Stratum:
    """One cell of the sample: how big it is, how much of it we labelled."""

    name: str
    frame_size: int      # N, pages in the whole stratum
    sampled: int         # n, pages drawn and labelled
    hits: int            # how many of those n satisfied the property

    def __post_init__(self) -> None:
        if self.frame_size < 1:
            raise ValueError(f"{self.name}: frame_size must be positive")
        if self.sampled > self.frame_size:
            raise ValueError(
                f"{self.name}: sampled {self.sampled} of a {self.frame_size}-page "
                "frame. A sample larger than its own stratum means the frame "
                "was recomputed after the draw.")
        if not 0 <= self.hits <= self.sampled:
            raise ValueError(
                f"{self.name}: {self.hits} hits in {self.sampled} sampled")
        if self.sampled < 2 and self.sampled != self.frame_size:
            raise ValueError(
                f"{self.name}: {self.sampled} page sampled from {self.frame_size}. "
                "A single draw has no estimable within-stratum variance; merge "
                "the stratum or take the whole cell.")

    @property
    def proportion(self) -> float:
        return self.hits / self.sampled

    @property
    def variance(self) -> float:
        """Variance of this stratum's proportion under SRS without replacement.

        The finite-population correction is not a nicety here. Stratum A draws
        22 of 43 pages; ignoring it overstates the error bar by a third, and
        stratum D is drawn whole, where the correct answer is that there is no
        sampling error at all.
        """
        if self.sampled == self.frame_size:
            return 0.0
        p = self.proportion
        fpc = 1 - self.sampled / self.frame_size
        return fpc * p * (1 - p) / (self.sampled - 1)


@dataclass(frozen=True)
class Estimate:
    proportion: float
    standard_error: float
    frame_size: int
    sampled: int
    hits: int

    def as_percent(self, places: int = 1) -> str:
        return (f"{self.proportion * 100:.{places}f}% "
                f"+/- {self.standard_error * 100:.{places}f}pp")


def stratified_proportion(strata: list[Stratum]) -> Estimate:
    """Combine strata into one proportion, weighted by frame size.

    Weighting by frame size rather than by sample size is the whole point.
    Stage 2 labels 8 of 46 corroborated W-2 faces and 25 of 113 uncorroborated
    ones; pooling those raw would let the cheaper half of the design speak for
    a quarter of the answer.
    """
    if not strata:
        raise ValueError("no strata")
    names = [s.name for s in strata]
    if len(set(names)) != len(names):
        raise ValueError(f"duplicate stratum names: {sorted(names)}")

    total = sum(s.frame_size for s in strata)
    proportion = sum(s.frame_size / total * s.proportion for s in strata)
    variance = sum((s.frame_size / total) ** 2 * s.variance for s in strata)
    return Estimate(
        proportion=proportion,
        standard_error=math.sqrt(variance),
        frame_size=total,
        sampled=sum(s.sampled for s in strata),
        hits=sum(s.hits for s in strata),
    )


def design_standard_error(plan: list[tuple[str, int, int, float]]) -> float:
    """What an allocation is worth, before any page is labelled.

    `plan` is (name, frame_size, sampled, assumed_proportion). Used to write a
    number into the protocol that the design has to live up to, rather than
    discovering the error bar after spending a day labelling.

    The assumed proportion is used as it stands and never rounded to a whole
    number of pages. Rounding it looks harmless and is not: 0.95 across 8 draws
    rounds to 8 hits, an observed proportion of exactly 1.0, and a stratum that
    reports no sampling error at all. The design would then flatter itself
    precisely where it is thinnest.
    """
    if not plan:
        raise ValueError("no strata")
    total = sum(frame for _, frame, _, _ in plan)
    variance = 0.0
    for name, frame, n, p in plan:
        Stratum(name, frame, n, 0)          # same validation, hits unused
        if not 0.0 <= p <= 1.0:
            raise ValueError(f"{name}: assumed proportion {p} is not a proportion")
        within = 0.0 if n == frame else (1 - n / frame) * p * (1 - p) / (n - 1)
        variance += (frame / total) ** 2 * within
    return math.sqrt(variance)
