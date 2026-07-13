"""Configurable semi-empirical correlations for biomass gasification."""

from __future__ import annotations

from feedstock import Feedstock
from reactions import ProductTargets
from utils import clamp, normalize


EMPIRICAL_COEFFICIENTS = {
    "char_c_base": 0.22,
    "char_temp_slope_per_c": 0.00018,
    "char_residence_slope_per_s": 0.018,
    "char_er_slope": 0.10,
    "char_lignin_slope": 0.12,
    "tar_c_base": 0.080,
    "tar_temp_slope_per_c": 0.00016,
    "tar_er_slope": 0.11,
    "tar_residence_slope_per_s": 0.014,
    "steam_h2_boost": 0.18,
}


def semi_empirical_targets(
    feedstock: Feedstock,
    temperature_c: float,
    er: float,
    residence_time_s: float,
    steam_biomass_ratio: float = 0.0,
    coefficients: dict[str, float] | None = None,
) -> ProductTargets:
    """Return product targets from transparent qualitative correlations.

    The coefficients are deliberately exposed in ``EMPIRICAL_COEFFICIENTS``.
    Replace them with literature- or pilot-calibrated values for a given
    biomass, reactor design, and operating envelope.
    """
    c = coefficients or EMPIRICAL_COEFFICIENTS
    temp_delta = temperature_c - 750.0
    lignin = feedstock.lignin_pct / 100.0

    char_c = (
        c["char_c_base"]
        - c["char_temp_slope_per_c"] * temp_delta
        - c["char_residence_slope_per_s"] * max(residence_time_s - 1.0, 0.0)
        - c["char_er_slope"] * max(er - 0.25, 0.0)
        + c["char_lignin_slope"] * max(lignin - 0.20, 0.0)
    )
    tar_c = (
        c["tar_c_base"]
        - c["tar_temp_slope_per_c"] * temp_delta
        - c["tar_er_slope"] * max(er - 0.15, 0.0)
        - c["tar_residence_slope_per_s"] * max(residence_time_s - 1.0, 0.0)
    )

    hot = clamp((temperature_c - 650.0) / 450.0, 0.0, 1.0)
    er_moderate = 1.0 - abs(er - 0.30) / 0.30
    steam = clamp(steam_biomass_ratio / 0.8, 0.0, 1.0)

    fractions = {
        "CO": 0.36 + 0.20 * hot + 0.15 * clamp(er_moderate, 0.0, 1.0),
        "CO2": 0.18 + 0.85 * clamp(er, 0.0, 0.8),
        "CH4": 0.11 * (1.0 - 0.65 * hot),
        "C2H4": 0.035 * (1.0 - 0.70 * hot),
        "C2H6": 0.018 * (1.0 - 0.80 * hot),
    }
    # Steam mainly changes H/O closure, but a small carbon shift away from
    # methane is included to mimic steam reforming.
    fractions["CO"] += 0.05 * steam
    fractions["CH4"] *= 1.0 - 0.25 * steam

    return ProductTargets(
        char_carbon_fraction_of_feed_c=clamp(char_c, 0.03, 0.45),
        tar_carbon_fraction_of_feed_c=clamp(tar_c, 0.005, 0.18),
        gas_carbon_fractions=normalize(fractions),
    )


def stoichiometric_targets(temperature_c: float, er: float) -> ProductTargets:
    """Return a simple stoichiometric product target for screening."""
    hot = clamp((temperature_c - 700.0) / 400.0, 0.0, 1.0)
    oxidizing = clamp(er / 0.6, 0.0, 1.0)
    fractions = {
        "CO": 0.48 + 0.12 * hot - 0.10 * max(oxidizing - 0.55, 0.0),
        "CO2": 0.28 + 0.22 * oxidizing,
        "CH4": 0.06 * (1.0 - 0.5 * hot),
        "C2H4": 0.015 * (1.0 - hot),
        "C2H6": 0.006 * (1.0 - hot),
    }
    return ProductTargets(
        char_carbon_fraction_of_feed_c=clamp(0.18 - 0.10 * hot - 0.04 * oxidizing, 0.04, 0.24),
        tar_carbon_fraction_of_feed_c=clamp(0.04 - 0.03 * hot - 0.02 * oxidizing, 0.003, 0.08),
        gas_carbon_fractions=normalize(fractions),
    )
