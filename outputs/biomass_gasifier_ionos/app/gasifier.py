"""High-level gasifier model orchestration."""

from __future__ import annotations

from dataclasses import dataclass

from empirical import semi_empirical_targets, stoichiometric_targets
from energy_balance import cold_gas_efficiency, syngas_lhv_mj_nm3
from equilibrium import equilibrium_targets
from feedstock import Feedstock
from reactions import (
    build_balanced_products,
    check_atomic_balance,
    check_mass_balance,
    gas_volume_nm3_h,
    inlet_atoms_kmol_h,
    mol_percent,
    oxidant_from_er,
    stoichiometric_o2_kmol_h,
)
from utils import MOLECULAR_WEIGHTS, NM3_PER_KMOL


@dataclass(slots=True)
class GasifierConditions:
    """Operating conditions and model selection."""

    temperature_c: float
    pressure_bar: float = 1.0
    residence_time_s: float = 1.0
    er: float | None = None
    o2_flow_kmol_h: float | None = None
    agent: str = "air"
    steam_biomass_ratio: float = 0.0
    model: str = "semi_empirical"

    def __post_init__(self) -> None:
        if self.temperature_c <= 0:
            raise ValueError("temperature_c must be positive")
        if self.pressure_bar <= 0:
            raise ValueError("pressure_bar must be positive")
        if self.residence_time_s <= 0:
            raise ValueError("residence_time_s must be positive")
        if self.agent not in {"air", "oxygen", "steam", "air+steam"}:
            raise ValueError("agent must be air, oxygen, steam, or air+steam")
        if self.model not in {"stoichiometric_equilibrium", "semi_empirical", "hybrid"}:
            raise ValueError("model must be stoichiometric_equilibrium, semi_empirical, or hybrid")
        if self.er is None and self.o2_flow_kmol_h is None and self.agent != "steam":
            raise ValueError("Either er or o2_flow_kmol_h is required unless agent='steam'")


class Gasifier:
    """Run simplified biomass gasification simulations."""

    def __init__(self, feedstock: Feedstock, conditions: GasifierConditions):
        self.feedstock = feedstock
        self.conditions = conditions

    def simulate(self) -> dict:
        """Run the selected model and return a serializable result dictionary."""
        warnings = list(self.feedstock.warnings)
        o2_stoich = stoichiometric_o2_kmol_h(self.feedstock)
        if self.conditions.o2_flow_kmol_h is not None:
            er = self.conditions.o2_flow_kmol_h / max(o2_stoich, 1e-12)
        else:
            er = self.conditions.er or 0.0

        oxidant = oxidant_from_er(self.feedstock, er, self.conditions.agent)
        if self.conditions.o2_flow_kmol_h is not None:
            oxidant["O2"] = self.conditions.o2_flow_kmol_h
            oxidant["N2"] = oxidant["O2"] * 3.76 if self.conditions.agent in {"air", "air+steam"} else 0.0

        steam_kg_h = 0.0
        if self.conditions.agent in {"steam", "air+steam"} or self.conditions.steam_biomass_ratio > 0:
            steam_kg_h = self.conditions.steam_biomass_ratio * self.feedstock.dry_mass_flow_kg_h
        steam_kmol_h = steam_kg_h / MOLECULAR_WEIGHTS["H2O"]

        if self.conditions.model == "semi_empirical":
            targets = semi_empirical_targets(
                self.feedstock,
                self.conditions.temperature_c,
                er,
                self.conditions.residence_time_s,
                self.conditions.steam_biomass_ratio,
            )
        elif self.conditions.model == "stoichiometric_equilibrium":
            targets = stoichiometric_targets(self.conditions.temperature_c, er)
            warnings.append("Stoichiometric-equilibrium mode is a simplified stoichiometric slate, not a rigorous equilibrium solution.")
        else:
            targets, eq_warnings = equilibrium_targets(
                self.feedstock,
                self.conditions.temperature_c,
                er,
                self.conditions.residence_time_s,
                self.conditions.steam_biomass_ratio,
            )
            warnings.extend(eq_warnings)

        slate = build_balanced_products(
            self.feedstock,
            targets,
            self.conditions.temperature_c,
            er,
            oxidant,
            steam_kmol_h,
        )
        warnings.extend(slate.warnings)

        dry_pct = mol_percent(slate.gas_kmol_h, wet=False)
        wet_pct = mol_percent(slate.gas_kmol_h, wet=True)
        dry_kmol = sum(v for k, v in slate.gas_kmol_h.items() if k != "H2O")
        lhv = syngas_lhv_mj_nm3(dry_pct)
        cge = cold_gas_efficiency(self.feedstock, dry_kmol, lhv)
        inlet_atoms = inlet_atoms_kmol_h(self.feedstock, oxidant, steam_kmol_h)
        stoich_air_kmol_h = o2_stoich * (1.0 + 3.76)
        stoich_air_kg_h = o2_stoich * (MOLECULAR_WEIGHTS["O2"] + 3.76 * MOLECULAR_WEIGHTS["N2"])
        gasification_air_kmol_h = oxidant.get("O2", 0.0) + oxidant.get("N2", 0.0)
        gasification_air_kg_h = oxidant.get("O2", 0.0) * MOLECULAR_WEIGHTS["O2"] + oxidant.get("N2", 0.0) * MOLECULAR_WEIGHTS["N2"]
        hhv_estimated = self.feedstock.estimated_hhv_mj_kg()
        lhv_feed = self.feedstock.estimated_lhv_mj_kg()

        return {
            "input_normalized": self.feedstock.normalized_input(),
            "feedstock_energy": {
                "hhv_pcs_mj_kg_dry": hhv_estimated,
                "lhv_pci_mj_kg_dry": lhv_feed,
                "hhv_pcs_method": "user_supplied" if self.feedstock.hhv_mj_kg is not None else "Channiwala-Parikh ultimate-analysis correlation",
                "lhv_pci_method": "user_supplied" if self.feedstock.lhv_mj_kg is not None else "HHV minus water-of-combustion correction",
                "hhv_correlation_comparison": self.feedstock.hhv_correlations_mj_kg(),
                "hhv_pcs_mj_h": hhv_estimated * self.feedstock.dry_mass_flow_kg_h,
                "lhv_pci_mj_h": lhv_feed * self.feedstock.dry_mass_flow_kg_h,
            },
            "operating_conditions": {
                "temperature_c": self.conditions.temperature_c,
                "pressure_bar": self.conditions.pressure_bar,
                "residence_time_s": self.conditions.residence_time_s,
                "agent": self.conditions.agent,
                "model": self.conditions.model,
                "steam_biomass_ratio": self.conditions.steam_biomass_ratio,
            },
            "oxidant": {
                "o2_stoich_kmol_h": o2_stoich,
                "stoich_air_kmol_h": stoich_air_kmol_h,
                "stoich_air_kg_h": stoich_air_kg_h,
                "stoich_air_nm3_h": stoich_air_kmol_h * NM3_PER_KMOL,
                "stoich_air_kg_per_kg_dry_feed": stoich_air_kg_h / self.feedstock.dry_mass_flow_kg_h,
                "o2_in_kmol_h": oxidant.get("O2", 0.0),
                "n2_in_kmol_h": oxidant.get("N2", 0.0),
                "air_in_kmol_h": gasification_air_kmol_h,
                "air_in_kg_h": gasification_air_kg_h,
                "air_in_nm3_h": gasification_air_kmol_h * NM3_PER_KMOL,
                "air_in_kg_per_kg_dry_feed": gasification_air_kg_h / self.feedstock.dry_mass_flow_kg_h,
                "air_calculation_method": "Ultimate-analysis stoichiometric air, actual gasification air = ER * stoichiometric air.",
                "er": er,
                "steam_in_kg_h": steam_kg_h,
            },
            "yields": {
                "char_kg_h": slate.char_kg_h,
                "char_pct_dry_feed": 100.0 * slate.char_kg_h / self.feedstock.dry_mass_flow_kg_h,
                "tar_cnhm_kg_h": slate.tar_kg_h,
                "tar_pct_dry_feed": 100.0 * slate.tar_kg_h / self.feedstock.dry_mass_flow_kg_h,
                "tar_formula": slate.tar_formula,
            },
            "gas": {
                "species_kmol_h": slate.gas_kmol_h,
                "dry_flow_nm3_h": gas_volume_nm3_h(slate.gas_kmol_h, wet=False),
                "wet_flow_nm3_h": gas_volume_nm3_h(slate.gas_kmol_h, wet=True),
                "dry_composition_mol_pct": dry_pct,
                "wet_composition_mol_pct": wet_pct,
                "trace_pollutants": slate.trace_pollutants,
                "lhv_mj_nm3_dry": lhv,
                "cold_gas_efficiency_pct": cge,
            },
            "char": slate.char_composition,
            "balances": {
                "mass": check_mass_balance(self.feedstock, oxidant, steam_kmol_h, slate),
                "atomic": check_atomic_balance(inlet_atoms, slate.gas_kmol_h, slate.char_carbon_kmol_h, slate.tar_kmol_h),
            },
            "uncertainty": {
                "char_yield_relative_range_pct": [-30, 40],
                "tar_yield_relative_range_pct": [-50, 100],
                "major_gas_species_absolute_mol_pct_range": [-5, 5],
                "note": "Screening uncertainty placeholders; replace with validation statistics for a specific reactor/feedstock.",
            },
            "warnings": sorted(set(warnings)),
        }
