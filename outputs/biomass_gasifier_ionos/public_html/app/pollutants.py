"""Semi-empirical pollutant partitioning and qualitative risk indicators."""

from __future__ import annotations

import math
from dataclasses import dataclass

from utils import clamp


@dataclass(slots=True)
class PollutantSplit:
    """Minor-species kmol/h estimates and qualitative warnings."""

    species_kmol_h: dict[str, float]
    dioxin_furan_risk: str
    dioxin_furan_index: float
    trace_indicators: dict[str, object]
    warnings: list[str]


def estimate_pollutants(
    feed_atoms_kmol_h: dict[str, float],
    temperature_c: float,
    er: float,
    cooling_window_200_450_c: bool = True,
    residual_carbon_factor: float = 0.3,
    cooling_residence_time_s: float = 2.0,
    plastics_pct: float = 0.0,
    ps_pct: float = 0.0,
    pvc_pct: float = 0.0,
    reduction_zone_severity: float = 0.75,
) -> PollutantSplit:
    """Estimate minor species with deliberately coarse partition factors.

    These are placeholders for screening. Replace the split factors with
    calibrated kinetic or plant-specific correlations before using the output
    for permitting, compliance, or detailed design.
    """
    warnings = [
        "Minor nitrogen/sulfur/chlorine species are screening estimates after a lumped reducing-zone correction, not validated emission predictions."
    ]
    n = feed_atoms_kmol_h.get("N", 0.0)
    s = feed_atoms_kmol_h.get("S", 0.0)
    cl = feed_atoms_kmol_h.get("Cl", 0.0)

    oxidizing = clamp((er - 0.15) / 0.45, 0.0, 1.0)
    hot = clamp((temperature_c - 750.0) / 350.0, 0.0, 1.0)

    h2s_frac = clamp(0.85 - 0.55 * oxidizing, 0.15, 0.90)
    so2_frac = 1.0 - h2s_frac

    hcl_frac = clamp(0.95 - 0.20 * oxidizing, 0.65, 0.98)
    cl2_frac = 1.0 - hcl_frac

    nh3_frac = clamp(0.10 * (1.0 - hot) * (1.0 - oxidizing), 0.005, 0.12)
    hcn_frac = clamp(0.05 * (1.0 - oxidizing) * (0.4 + 0.6 * hot), 0.002, 0.07)
    no_frac = clamp(0.025 * oxidizing * hot, 0.0, 0.05)
    no2_frac = clamp(0.006 * oxidizing * hot, 0.0, 0.015)
    n2o_frac = clamp(0.004 * oxidizing * (1.0 - hot), 0.0, 0.01)

    # Gasifiers have reducing zones where char, CO, H2, and residence time tend
    # to convert nitrogen oxides and part of NH3/HCN toward N2. This is still a
    # screening closure: real conversion depends on hydrodynamics, tar/char
    # contact, catalysts, temperature history, and downstream air ingress.
    reduction = clamp(reduction_zone_severity, 0.0, 1.0)
    nox_reduction_factor = 1.0 - 0.95 * reduction
    precursor_reduction_factor = 1.0 - 0.55 * reduction
    nh3_frac *= precursor_reduction_factor
    hcn_frac *= precursor_reduction_factor
    no_frac *= nox_reduction_factor
    no2_frac *= nox_reduction_factor
    n2o_frac *= nox_reduction_factor

    species = {
        "H2S": s * h2s_frac,
        "SO2": s * so2_frac,
        "HCl": cl * hcl_frac,
        "Cl2": cl * cl2_frac / 2.0,
        "NH3": n * nh3_frac,
        "HCN": n * hcn_frac,
        "NO": n * no_frac,
        "NO2": n * no2_frac,
        "N2O": n * n2o_frac / 2.0,
    }

    cl_pct_like = clamp(cl / max(sum(feed_atoms_kmol_h.values()), 1e-12) * 100.0, 0.0, 1.0)
    cooling_factor = 1.0 if cooling_window_200_450_c else 0.10
    cooling_time_factor = clamp(cooling_residence_time_s / 4.0, 0.05, 1.5)
    plastic_precursor_factor = clamp((plastics_pct + 1.5 * ps_pct + 2.0 * pvc_pct) / 50.0, 0.0, 1.5)
    chlorine_factor = clamp(cl_pct_like / 0.08, 0.0, 1.5)
    oxygen_factor = clamp(er / 0.40, 0.0, 1.5)
    cooling_exposure = cooling_factor * cooling_time_factor
    in_reactor_survival = clamp(math.exp(-max(temperature_c - 450.0, 0.0) / 150.0), 0.0, 1.0)
    risk_index = clamp(
        0.12 * chlorine_factor
        + 0.15 * oxygen_factor
        + 0.13 * residual_carbon_factor
        + 0.10 * plastic_precursor_factor
        + 0.50 * cooling_exposure * (0.40 + 0.60 * chlorine_factor)
        + 0.08 * in_reactor_survival,
        0.0,
        1.0,
    )
    profile_temperatures = (200, 250, 300, 325, 350, 400, 450, 500)
    temperature_profile = {}
    base_without_temperature = clamp(
        0.18 * chlorine_factor
        + 0.18 * oxygen_factor
        + 0.16 * residual_carbon_factor
        + 0.13 * plastic_precursor_factor,
        0.0,
        1.0,
    )
    for profile_temperature in profile_temperatures:
        formation_window = math.exp(-0.5 * ((profile_temperature - 325.0) / 62.0) ** 2)
        temperature_profile[str(profile_temperature)] = clamp(
            base_without_temperature
            + formation_window * cooling_time_factor * (0.25 + 0.30 * chlorine_factor),
            0.0,
            1.0,
        )
    if risk_index < 0.33:
        risk = "low"
        teq_range = [0.0, 0.01]
        total_pcdd_f_range = [0.0, 0.10]
    elif risk_index < 0.66:
        risk = "medium"
        teq_range = [0.01, 0.10]
        total_pcdd_f_range = [0.10, 1.0]
    else:
        risk = "high"
        teq_range = [0.10, 1.0]
        total_pcdd_f_range = [1.0, 10.0]
    trace_indicators = {
        "dioxins_furans_risk": risk,
        "dioxins_furans_index_0_1": risk_index,
        "pcdd_f_teq_ng_i_teq_nm3_screening_range": teq_range,
        "total_pcdd_f_ng_nm3_screening_range": total_pcdd_f_range,
        "basis": "Indicative screening range only; not a validated concentration prediction.",
        "main_drivers": {
            "chlorine_feed_factor": cl_pct_like,
            "oxygen_er_factor": er,
            "residual_carbon_factor": residual_carbon_factor,
            "cooling_window_200_450_c": cooling_window_200_450_c,
            "cooling_residence_time_s": cooling_residence_time_s,
            "plastic_precursor_factor": plastic_precursor_factor,
            "reduction_zone_severity": reduction,
            "nox_reduction_factor": nox_reduction_factor,
            "nh3_hcn_reduction_factor": precursor_reduction_factor,
        },
        "temperature_sensitivity": {
            "in_reactor_pcdd_f_survival_index_0_1": in_reactor_survival,
            "post_gasifier_de_novo_risk_index_by_temperature_c": temperature_profile,
            "peak_temperature_c": 325,
            "interpretation": "Relative risk profile only; values are not concentrations or emission factors.",
        },
    }
    warnings.append(
        "Dioxins/furans use only a qualitative risk index and broad screening ranges; do not use as measured emissions."
    )
    return PollutantSplit(species, risk, risk_index, trace_indicators, warnings)
