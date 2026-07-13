"""Configurable screening model for catalytic bed additives."""

from __future__ import annotations

import math
from dataclasses import dataclass

from reactions import ProductTargets
from utils import clamp, normalize


# Maximum effects are screening placeholders, not universal catalyst data.
# Replace these profiles with reactor-specific experimental regressions.
CATALYST_PROFILES = {
    "olivine": {
        "reference_loading": 0.20,
        "max_tar_conversion": 0.45,
        "max_char_conversion": 0.025,
        "methane_reforming": 0.10,
        "c2_reforming": 0.20,
        "co_selectivity": 0.70,
    },
    "calcined_olivine": {
        "reference_loading": 0.18,
        "max_tar_conversion": 0.62,
        "max_char_conversion": 0.030,
        "methane_reforming": 0.16,
        "c2_reforming": 0.30,
        "co_selectivity": 0.72,
    },
    "limestone": {
        "reference_loading": 0.16,
        "max_tar_conversion": 0.32,
        "max_char_conversion": 0.015,
        "methane_reforming": 0.06,
        "c2_reforming": 0.12,
        "co_selectivity": 0.45,
    },
    "dolomite": {
        "reference_loading": 0.15,
        "max_tar_conversion": 0.58,
        "max_char_conversion": 0.025,
        "methane_reforming": 0.14,
        "c2_reforming": 0.26,
        "co_selectivity": 0.58,
    },
    "nickel_based": {
        "reference_loading": 0.08,
        "max_tar_conversion": 0.82,
        "max_char_conversion": 0.035,
        "methane_reforming": 0.38,
        "c2_reforming": 0.65,
        "co_selectivity": 0.75,
    },
}


@dataclass(slots=True)
class CatalystEffect:
    """Effective severity and predicted changes applied to product targets."""

    catalyst_type: str
    severity: float
    tar_conversion_fraction: float
    char_carbon_conversion_fraction: float
    methane_reforming_fraction: float
    c2_reforming_fraction: float


def apply_catalyst(
    targets: ProductTargets,
    catalyst_type: str,
    catalyst_to_biomass_ratio: float,
    catalyst_activity: float,
    temperature_c: float,
    steam_biomass_ratio: float,
) -> tuple[ProductTargets, CatalystEffect]:
    """Apply a transparent catalytic severity correction to product targets.

    Catalyst mass is treated as circulating bed inventory and is therefore not
    added to the process mass balance. The model represents tar cracking,
    limited char conversion, and hydrocarbon reforming only.
    """
    if catalyst_type == "none":
        return targets, CatalystEffect("none", 0.0, 0.0, 0.0, 0.0, 0.0)

    profile = CATALYST_PROFILES[catalyst_type]
    loading_factor = 1.0 - math.exp(
        -catalyst_to_biomass_ratio / max(profile["reference_loading"], 1e-12)
    )
    temperature_factor = clamp((temperature_c - 650.0) / 250.0, 0.0, 1.0)
    steam_factor = 0.75 + 0.25 * clamp(steam_biomass_ratio / 0.6, 0.0, 1.0)
    severity = clamp(catalyst_activity * loading_factor * temperature_factor * steam_factor, 0.0, 1.0)

    tar_conversion = profile["max_tar_conversion"] * severity
    char_conversion = profile["max_char_conversion"] * severity
    methane_reforming = profile["methane_reforming"] * severity
    c2_reforming = profile["c2_reforming"] * severity

    fractions = dict(targets.gas_carbon_fractions)
    reformed_carbon = 0.0
    for species, conversion in (
        ("CH4", methane_reforming),
        ("C2H4", c2_reforming),
        ("C2H6", c2_reforming),
    ):
        removed = fractions.get(species, 0.0) * conversion
        fractions[species] = max(fractions.get(species, 0.0) - removed, 0.0)
        reformed_carbon += removed

    co_share = profile["co_selectivity"]
    fractions["CO"] = fractions.get("CO", 0.0) + reformed_carbon * co_share
    fractions["CO2"] = fractions.get("CO2", 0.0) + reformed_carbon * (1.0 - co_share)

    modified = ProductTargets(
        char_carbon_fraction_of_feed_c=clamp(
            targets.char_carbon_fraction_of_feed_c * (1.0 - char_conversion),
            0.0,
            0.75,
        ),
        tar_carbon_fraction_of_feed_c=clamp(
            targets.tar_carbon_fraction_of_feed_c * (1.0 - tar_conversion),
            0.0,
            0.40,
        ),
        gas_carbon_fractions=normalize(fractions),
    )
    return modified, CatalystEffect(
        catalyst_type,
        severity,
        tar_conversion,
        char_conversion,
        methane_reforming,
        c2_reforming,
    )
