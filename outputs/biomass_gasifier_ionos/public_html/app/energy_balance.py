"""Heating value, cold-gas-efficiency, and heat-recovery calculations."""

from __future__ import annotations

from feedstock import Feedstock
from utils import LHV_MJ_PER_NM3, NM3_PER_KMOL

# Mean ideal-gas heat capacities over a broad 40-850 C interval [kJ/kmol/K].
# These screening constants should be replaced by temperature-dependent Cp
# integrations (for example NASA polynomials) for exchanger design work.
MEAN_CP_KJ_KMOL_K = {
    "H2": 29.3,
    "CO": 30.0,
    "CO2": 45.0,
    "CH4": 55.0,
    "C2H4": 72.0,
    "C2H6": 82.0,
    "H2O": 37.5,
    "N2": 31.0,
    "O2": 32.5,
    "H2S": 38.0,
    "SO2": 44.0,
    "HCl": 30.0,
    "Cl2": 37.0,
    "NH3": 44.0,
    "HCN": 34.0,
    "NO": 31.0,
    "NO2": 43.0,
    "N2O": 43.0,
}


def syngas_lhv_mj_nm3(dry_mol_pct: dict[str, float]) -> float:
    """Return dry syngas LHV in MJ/Nm3 from mol percent composition."""
    return sum((dry_mol_pct.get(species, 0.0) / 100.0) * lhv for species, lhv in LHV_MJ_PER_NM3.items())


def cold_gas_efficiency(
    feedstock: Feedstock,
    dry_gas_kmol_h: float,
    dry_gas_lhv_mj_nm3: float,
) -> float:
    """Estimate cold gas efficiency on dry biomass LHV basis."""
    gas_energy = dry_gas_kmol_h * NM3_PER_KMOL * dry_gas_lhv_mj_nm3
    feed_energy = feedstock.dry_mass_flow_kg_h * feedstock.estimated_lhv_mj_kg()
    return 100.0 * gas_energy / max(feed_energy, 1e-12)


def syngas_chemical_power_kw(
    dry_gas_kmol_h: float,
    dry_gas_lhv_mj_nm3: float,
) -> float:
    """Return syngas chemical power on dry-gas LHV basis [kW]."""
    return dry_gas_kmol_h * NM3_PER_KMOL * dry_gas_lhv_mj_nm3 / 3.6


def feedstock_chemical_power_kw(feedstock: Feedstock) -> float:
    """Return dry-feed chemical power on LHV basis [kW]."""
    return feedstock.dry_mass_flow_kg_h * feedstock.estimated_lhv_mj_kg() / 3.6


def syngas_sensible_heat_kw(
    gas_kmol_h: dict[str, float],
    inlet_temperature_c: float,
    outlet_temperature_c: float,
) -> float:
    """Estimate wet-syngas sensible heat released during cooling [kW].

    The estimate uses constant mean ideal-gas heat capacities and excludes
    latent heat from steam or tar condensation.
    """
    delta_t_k = max(inlet_temperature_c - outlet_temperature_c, 0.0)
    heat_kj_h = sum(
        amount * MEAN_CP_KJ_KMOL_K.get(species, 35.0) * delta_t_k
        for species, amount in gas_kmol_h.items()
    )
    return heat_kj_h / 3600.0


def energy_performance(
    feedstock: Feedstock,
    gas_kmol_h: dict[str, float],
    dry_gas_kmol_h: float,
    dry_gas_lhv_mj_nm3: float,
    gas_temperature_c: float,
    cooler_outlet_c: float,
    exchanger_effectiveness: float,
    external_heat_input_kw: float,
) -> dict[str, float]:
    """Return chemical powers, heat recovery, and overall efficiency."""
    feed_kw = feedstock_chemical_power_kw(feedstock)
    syngas_kw = syngas_chemical_power_kw(dry_gas_kmol_h, dry_gas_lhv_mj_nm3)
    sensible_kw = syngas_sensible_heat_kw(gas_kmol_h, gas_temperature_c, cooler_outlet_c)
    recovered_kw = sensible_kw * exchanger_effectiveness
    denominator_kw = feed_kw + external_heat_input_kw
    overall_pct = 100.0 * (syngas_kw + recovered_kw) / max(denominator_kw, 1e-12)
    return {
        "feedstock_chemical_power_lhv_kw": feed_kw,
        "syngas_chemical_power_lhv_kw": syngas_kw,
        "external_thermal_input_kw": external_heat_input_kw,
        "syngas_sensible_heat_available_kw": sensible_kw,
        "thermal_recovery_kw": recovered_kw,
        "overall_efficiency_pct": overall_pct,
    }
