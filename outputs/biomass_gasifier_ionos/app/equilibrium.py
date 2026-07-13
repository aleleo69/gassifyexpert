"""Optional simplified equilibrium adjustment using scipy.optimize."""

from __future__ import annotations

import math

from empirical import semi_empirical_targets
from feedstock import Feedstock
from reactions import ProductTargets
from utils import clamp, normalize


def equilibrium_targets(
    feedstock: Feedstock,
    temperature_c: float,
    er: float,
    residence_time_s: float,
    steam_biomass_ratio: float = 0.0,
) -> tuple[ProductTargets, list[str]]:
    """Return equilibrium-like targets when SciPy is installed.

    This is not a full thermodynamic database calculation. It minimizes a
    compact surrogate objective favoring water-gas-shift and methanation trends
    near gasification temperatures, then leaves exact atom closure to
    ``build_balanced_products``. Replace this module with a Gibbs minimizer
    using species chemical potentials for rigorous work.
    """
    warnings = [
        "Equilibrium mode uses a simplified surrogate objective, not a full Gibbs free-energy database."
    ]
    base = semi_empirical_targets(feedstock, temperature_c, er, residence_time_s, steam_biomass_ratio)
    try:
        from scipy.optimize import minimize
    except Exception:
        warnings.append("scipy.optimize is unavailable; equilibrium mode fell back to semi-empirical targets.")
        return base, warnings

    t_k = temperature_c + 273.15
    # Approximate trend targets: high T favors CO/H2 over CH4 and lower CO2.
    k_wgs_like = math.exp(4200.0 / t_k - 3.2)
    methane_penalty = clamp((temperature_c - 650.0) / 450.0, 0.0, 1.0)
    base_vec = [
        base.gas_carbon_fractions.get("CO", 0.0),
        base.gas_carbon_fractions.get("CO2", 0.0),
        base.gas_carbon_fractions.get("CH4", 0.0),
        base.gas_carbon_fractions.get("C2H4", 0.0),
        base.gas_carbon_fractions.get("C2H6", 0.0),
    ]

    def objective(x: list[float]) -> float:
        co, co2, ch4, c2h4, c2h6 = x
        if min(x) < 0:
            return 1e6
        total = sum(x)
        ratio_penalty = (total - 1.0) ** 2 * 100.0
        wgs_penalty = (co2 / max(co, 1e-8) - k_wgs_like) ** 2
        hydrocarbon_penalty = methane_penalty * (ch4 + c2h4 + c2h6) ** 2 * 4.0
        regularization = sum((xi - bi) ** 2 for xi, bi in zip(x, base_vec))
        return ratio_penalty + 0.15 * wgs_penalty + hydrocarbon_penalty + regularization

    result = minimize(objective, base_vec, bounds=[(0.001, 0.95)] * 5, method="SLSQP")
    if not result.success:
        warnings.append(f"SciPy optimizer did not converge ({result.message}); semi-empirical targets retained.")
        return base, warnings

    labels = ["CO", "CO2", "CH4", "C2H4", "C2H6"]
    fractions = normalize(dict(zip(labels, map(float, result.x))))
    targets = ProductTargets(
        char_carbon_fraction_of_feed_c=clamp(base.char_carbon_fraction_of_feed_c * 0.85, 0.02, 0.35),
        tar_carbon_fraction_of_feed_c=clamp(base.tar_carbon_fraction_of_feed_c * 0.55, 0.001, 0.12),
        gas_carbon_fractions=fractions,
    )
    return targets, warnings
