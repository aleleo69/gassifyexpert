"""Heating value and cold-gas-efficiency calculations."""

from __future__ import annotations

from feedstock import Feedstock
from utils import LHV_MJ_PER_NM3, NM3_PER_KMOL


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
