"""Screening corrections for common biomass gasifier configurations."""

from __future__ import annotations

from dataclasses import dataclass

from reactions import ProductTargets
from utils import clamp, normalize


# Relative corrections around the generic semi-empirical model. They encode
# qualitative reactor tendencies and must be calibrated for a specific design.
GASIFIER_TYPE_PROFILES = {
    "generic": {
        "char_multiplier": 1.00,
        "tar_multiplier": 1.00,
        "species_multipliers": {},
    },
    "updraft": {
        "char_multiplier": 1.08,
        "tar_multiplier": 2.20,
        "species_multipliers": {"CO": 0.95, "CO2": 1.05, "CH4": 1.25, "C2H4": 1.35, "C2H6": 1.35},
    },
    "downdraft": {
        "char_multiplier": 0.88,
        "tar_multiplier": 0.45,
        "species_multipliers": {"CO": 1.08, "CO2": 0.95, "CH4": 0.85, "C2H4": 0.50, "C2H6": 0.50},
    },
    "bubbling_fluidized_bed": {
        "char_multiplier": 0.82,
        "tar_multiplier": 1.00,
        "species_multipliers": {"CO": 1.02, "CO2": 1.00, "CH4": 1.05, "C2H4": 0.95, "C2H6": 0.90},
    },
    "circulating_fluidized_bed": {
        "char_multiplier": 0.70,
        "tar_multiplier": 0.72,
        "species_multipliers": {"CO": 1.06, "CO2": 0.98, "CH4": 0.90, "C2H4": 0.72, "C2H6": 0.65},
    },
    "entrained_flow": {
        "char_multiplier": 0.18,
        "tar_multiplier": 0.08,
        "species_multipliers": {"CO": 1.15, "CO2": 1.00, "CH4": 0.10, "C2H4": 0.05, "C2H6": 0.03},
    },
}


@dataclass(slots=True)
class ReactorTypeEffect:
    """Corrections applied to generic product targets."""

    gasifier_type: str
    char_multiplier: float
    tar_multiplier: float
    species_multipliers: dict[str, float]


def apply_gasifier_type(
    targets: ProductTargets,
    gasifier_type: str,
) -> tuple[ProductTargets, ReactorTypeEffect]:
    """Apply gasifier-configuration screening multipliers."""
    profile = GASIFIER_TYPE_PROFILES[gasifier_type]
    fractions = {
        species: value * profile["species_multipliers"].get(species, 1.0)
        for species, value in targets.gas_carbon_fractions.items()
    }
    modified = ProductTargets(
        char_carbon_fraction_of_feed_c=clamp(
            targets.char_carbon_fraction_of_feed_c * profile["char_multiplier"],
            0.0,
            0.75,
        ),
        tar_carbon_fraction_of_feed_c=clamp(
            targets.tar_carbon_fraction_of_feed_c * profile["tar_multiplier"],
            0.0,
            0.40,
        ),
        gas_carbon_fractions=normalize(fractions),
    )
    effect = ReactorTypeEffect(
        gasifier_type,
        profile["char_multiplier"],
        profile["tar_multiplier"],
        dict(profile["species_multipliers"]),
    )
    return modified, effect
