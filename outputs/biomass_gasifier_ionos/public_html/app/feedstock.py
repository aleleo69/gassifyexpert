"""Feedstock input model and elemental bookkeeping."""

from __future__ import annotations

from dataclasses import dataclass, field

from utils import ATOMIC_WEIGHTS, percent_to_fraction


ELEMENTS = ("C", "H", "O", "N", "S", "Cl")
COMPOSITION_TOLERANCE_PCT = 0.5


@dataclass(slots=True)
class Feedstock:
    """Biomass feedstock specification.

    Percent compositions are mass percentages on a dry biomass basis, except
    moisture, which is percent of the as-received stream when
    ``mass_basis="wet"`` and an added water fraction when ``mass_basis="dry"``.
    """

    mass_flow_kg_h: float
    mass_basis: str = "dry"
    moisture_pct: float = 0.0
    C_pct: float = 0.0
    H_pct: float = 0.0
    O_pct: float = 0.0
    N_pct: float = 0.0
    S_pct: float = 0.0
    Cl_pct: float = 0.0
    ash_pct: float = 0.0
    cellulose_pct: float = 0.0
    hemicellulose_pct: float = 0.0
    lignin_pct: float = 0.0
    extractives_pct: float = 0.0
    plastics_pct: float = 0.0
    pe_pp_pct: float = 0.0
    ps_pct: float = 0.0
    pet_pct: float = 0.0
    pvc_pct: float = 0.0
    other_organics_pct: float = 0.0
    lhv_mj_kg: float | None = None
    hhv_mj_kg: float | None = None
    warnings: list[str] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        if self.mass_flow_kg_h <= 0:
            raise ValueError("mass_flow_kg_h must be positive")
        if self.mass_basis not in {"dry", "wet"}:
            raise ValueError("mass_basis must be 'dry' or 'wet'")
        for name in (
            "moisture_pct",
            "C_pct",
            "H_pct",
            "O_pct",
            "N_pct",
            "S_pct",
            "Cl_pct",
            "ash_pct",
            "cellulose_pct",
            "hemicellulose_pct",
            "lignin_pct",
            "extractives_pct",
            "plastics_pct",
            "pe_pp_pct",
            "ps_pct",
            "pet_pct",
            "pvc_pct",
            "other_organics_pct",
        ):
            value = getattr(self, name)
            if value < 0:
                raise ValueError(f"{name} cannot be negative")
        dry_sum = self.C_pct + self.H_pct + self.O_pct + self.N_pct + self.S_pct + self.Cl_pct + self.ash_pct
        if abs(dry_sum - 100.0) > COMPOSITION_TOLERANCE_PCT:
            raise ValueError(
                f"Dry elemental composition C+H+O+N+S+Cl+ash must sum to 100% "
                f"(current sum {dry_sum:.2f}%, tolerance +/-{COMPOSITION_TOLERANCE_PCT:.1f}%)."
            )
        structural_sum = (
            self.cellulose_pct
            + self.hemicellulose_pct
            + self.lignin_pct
            + self.extractives_pct
            + self.plastics_pct
            + self.other_organics_pct
        )
        if abs(structural_sum - 100.0) > COMPOSITION_TOLERANCE_PCT:
            raise ValueError(
                f"Structural composition cellulose+hemicellulose+lignin+extractives+plastics+other organics "
                f"must sum to 100% (current sum {structural_sum:.2f}%, "
                f"tolerance +/-{COMPOSITION_TOLERANCE_PCT:.1f}%)."
            )
        plastic_subtypes = self.pe_pp_pct + self.ps_pct + self.pet_pct + self.pvc_pct
        if plastic_subtypes > self.plastics_pct + 1e-9:
            raise ValueError(
                f"Plastic subtypes sum to {plastic_subtypes:.2f}%, above total plastics {self.plastics_pct:.2f}%."
            )
        if self.pvc_pct > 0 and self.Cl_pct <= 0:
            self.warnings.append(
                "PVC is present but elemental chlorine is zero; enter measured Cl because elemental analysis controls HCl and PCDD/F screening."
            )

    @property
    def dry_mass_flow_kg_h(self) -> float:
        """Dry biomass mass flow."""
        if self.mass_basis == "dry":
            return self.mass_flow_kg_h
        dry_fraction = 1.0 - percent_to_fraction(self.moisture_pct)
        if dry_fraction <= 0:
            raise ValueError("wet feed has no dry material")
        return self.mass_flow_kg_h * dry_fraction

    @property
    def moisture_mass_flow_kg_h(self) -> float:
        """Water carried with the as-fed biomass."""
        if self.mass_basis == "dry":
            return self.dry_mass_flow_kg_h * percent_to_fraction(self.moisture_pct)
        return self.mass_flow_kg_h - self.dry_mass_flow_kg_h

    @property
    def ash_mass_flow_kg_h(self) -> float:
        """Ash mass flow on the dry-feed basis."""
        return self.dry_mass_flow_kg_h * percent_to_fraction(self.ash_pct)

    def elemental_mass_flows_kg_h(self) -> dict[str, float]:
        """Return dry-feed elemental mass flows in kg/h."""
        return {
            "C": self.dry_mass_flow_kg_h * percent_to_fraction(self.C_pct),
            "H": self.dry_mass_flow_kg_h * percent_to_fraction(self.H_pct),
            "O": self.dry_mass_flow_kg_h * percent_to_fraction(self.O_pct),
            "N": self.dry_mass_flow_kg_h * percent_to_fraction(self.N_pct),
            "S": self.dry_mass_flow_kg_h * percent_to_fraction(self.S_pct),
            "Cl": self.dry_mass_flow_kg_h * percent_to_fraction(self.Cl_pct),
        }

    def elemental_kmol_h(self) -> dict[str, float]:
        """Return atomic kmol/h in the dry organic/inorganic feed."""
        masses = self.elemental_mass_flows_kg_h()
        return {element: masses[element] / ATOMIC_WEIGHTS[element] for element in ELEMENTS}

    def moisture_kmol_h(self) -> float:
        """Return kmol/h of inlet moisture water."""
        return self.moisture_mass_flow_kg_h / 18.015

    def estimated_lhv_mj_kg(self) -> float:
        """Return feed LHV in MJ/kg dry, using a Dulong-style fallback.

        The fallback is approximate and intended only for cold-gas-efficiency
        screening when a measured PCI/LHV is not supplied.
        """
        if self.lhv_mj_kg is not None:
            return self.lhv_mj_kg
        hhv = self.estimated_hhv_mj_kg()
        h = self.H_pct / 100.0
        lhv = hhv - 2.442 * 9.0 * h
        self.warnings.append("Feedstock LHV not supplied; estimated from empirical HHV minus water-of-combustion correction.")
        return max(lhv, 1.0)

    def estimated_hhv_mj_kg(self) -> float:
        """Return feed HHV/PCS in MJ/kg dry.

        Uses supplied HHV/PCS when available. Otherwise applies the
        Channiwala-Parikh ultimate-analysis correlation, widely used for solid
        fuels and often cited in biomass gasification texts such as Basu:

        HHV = 0.3491*C + 1.1783*H + 0.1005*S - 0.1034*O
              - 0.0151*N - 0.0211*Ash

        where all inputs are dry-basis mass percentages.
        """
        if self.hhv_mj_kg is not None:
            return self.hhv_mj_kg
        hhv = (
            0.3491 * self.C_pct
            + 1.1783 * self.H_pct
            + 0.1005 * self.S_pct
            - 0.1034 * self.O_pct
            - 0.0151 * self.N_pct
            - 0.0211 * self.ash_pct
        )
        self.warnings.append("Feedstock HHV/PCS not supplied; estimated with Channiwala-Parikh ultimate-analysis correlation.")
        return max(hhv, 1.0)

    def hhv_correlations_mj_kg(self) -> dict[str, float]:
        """Return multiple empirical HHV/PCS estimates for comparison."""
        channiwala_parikh = (
            0.3491 * self.C_pct
            + 1.1783 * self.H_pct
            + 0.1005 * self.S_pct
            - 0.1034 * self.O_pct
            - 0.0151 * self.N_pct
            - 0.0211 * self.ash_pct
        )
        dulong = 0.3386 * self.C_pct + 1.444 * (self.H_pct - self.O_pct / 8.0) + 0.0943 * self.S_pct
        return {
            "channiwala_parikh_mj_kg_dry": max(channiwala_parikh, 1.0),
            "dulong_mj_kg_dry": max(dulong, 1.0),
        }

    def normalized_input(self) -> dict[str, float | str | None]:
        """Return normalized feedstock values for result reporting."""
        return {
            "mass_flow_kg_h": self.mass_flow_kg_h,
            "mass_basis": self.mass_basis,
            "dry_mass_flow_kg_h": self.dry_mass_flow_kg_h,
            "moisture_mass_flow_kg_h": self.moisture_mass_flow_kg_h,
            "moisture_pct": self.moisture_pct,
            "C_pct_dry": self.C_pct,
            "H_pct_dry": self.H_pct,
            "O_pct_dry": self.O_pct,
            "N_pct_dry": self.N_pct,
            "S_pct_dry": self.S_pct,
            "Cl_pct_dry": self.Cl_pct,
            "ash_pct_dry": self.ash_pct,
            "elemental_ash_sum_pct_dry": self.C_pct + self.H_pct + self.O_pct + self.N_pct + self.S_pct + self.Cl_pct + self.ash_pct,
            "cellulose_pct_dry": self.cellulose_pct,
            "hemicellulose_pct_dry": self.hemicellulose_pct,
            "lignin_pct_dry": self.lignin_pct,
            "extractives_pct_dry": self.extractives_pct,
            "plastics_pct_dry": self.plastics_pct,
            "pe_pp_pct_dry": self.pe_pp_pct,
            "ps_pct_dry": self.ps_pct,
            "pet_pct_dry": self.pet_pct,
            "pvc_pct_dry": self.pvc_pct,
            "other_organics_pct_dry": self.other_organics_pct,
            "structural_sum_pct_dry": (
                self.cellulose_pct
                + self.hemicellulose_pct
                + self.lignin_pct
                + self.extractives_pct
                + self.plastics_pct
                + self.other_organics_pct
            ),
            "lhv_mj_kg_dry": self.lhv_mj_kg,
            "hhv_mj_kg_dry": self.hhv_mj_kg,
        }
