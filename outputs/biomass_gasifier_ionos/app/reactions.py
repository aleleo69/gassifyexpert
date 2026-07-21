"""Stoichiometric calculations, product construction, and balance checks."""

from __future__ import annotations

from dataclasses import dataclass

from feedstock import Feedstock
from pollutants import estimate_pollutants
from utils import (
    AIR_N2_O2_MOLAR_RATIO,
    ATOMIC_WEIGHTS,
    MOLECULAR_WEIGHTS,
    NM3_PER_KMOL,
    SPECIES_ATOMS,
    clamp,
    normalize,
)


@dataclass(slots=True)
class ProductTargets:
    """Desired product distribution before atom-balance closure."""

    char_carbon_fraction_of_feed_c: float
    tar_carbon_fraction_of_feed_c: float
    gas_carbon_fractions: dict[str, float]


@dataclass(slots=True)
class ProductSlate:
    """Balanced product slate."""

    gas_kmol_h: dict[str, float]
    char_kg_h: float
    char_carbon_kmol_h: float
    char_composition: dict[str, object]
    tar_kg_h: float
    tar_kmol_h: float
    tar_formula: str
    trace_pollutants: dict[str, object]
    warnings: list[str]


def stoichiometric_o2_kmol_h(feedstock: Feedstock) -> float:
    """Return complete-combustion O2 demand in kmol/h.

    Formula: O2 = C + H/4 + S - O/2, using atomic kmol/h in the dry feed.
    Nitrogen and chlorine are ignored in the oxygen demand.
    """
    atoms = feedstock.elemental_kmol_h()
    return max(atoms["C"] + atoms["H"] / 4.0 + atoms["S"] - atoms["O"] / 2.0, 0.0)


def oxidant_from_er(feedstock: Feedstock, er: float, agent: str) -> dict[str, float]:
    """Calculate inlet O2/N2 from ER and gasifying agent."""
    if er < 0:
        raise ValueError("ER cannot be negative")
    o2 = er * stoichiometric_o2_kmol_h(feedstock)
    n2 = o2 * AIR_N2_O2_MOLAR_RATIO if agent in {"air", "air+steam"} else 0.0
    return {"O2": o2, "N2": n2}


def inlet_atoms_kmol_h(feedstock: Feedstock, oxidant: dict[str, float], steam_kmol_h: float = 0.0) -> dict[str, float]:
    """Return all inlet atoms including moisture, steam, O2, and air nitrogen."""
    atoms = feedstock.elemental_kmol_h().copy()
    water = feedstock.moisture_kmol_h() + steam_kmol_h
    atoms["H"] += 2.0 * water
    atoms["O"] += water
    atoms["O"] += 2.0 * oxidant.get("O2", 0.0)
    atoms["N"] += 2.0 * oxidant.get("N2", 0.0)
    return atoms


def build_balanced_products(
    feedstock: Feedstock,
    targets: ProductTargets,
    temperature_c: float,
    er: float,
    oxidant: dict[str, float],
    steam_kmol_h: float = 0.0,
    cooling_residence_time_s: float = 2.0,
    reduction_zone_severity: float = 0.75,
) -> ProductSlate:
    """Build a product slate that closes C/H/O/N/S/Cl atom balances.

    The empirical/equilibrium layers provide desired carbon partitioning. This
    function then uses H2O, H2, N2, and O2 residual as balancing species.
    """
    warnings: list[str] = []
    feed_atoms = feedstock.elemental_kmol_h()
    inlet_atoms = inlet_atoms_kmol_h(feedstock, oxidant, steam_kmol_h)
    c_feed = feed_atoms["C"]

    char_c = c_feed * clamp(targets.char_carbon_fraction_of_feed_c, 0.0, 0.75)
    tar_c = c_feed * clamp(targets.tar_carbon_fraction_of_feed_c, 0.0, 0.40)
    if char_c + tar_c > c_feed * 0.95:
        scale = c_feed * 0.95 / (char_c + tar_c)
        char_c *= scale
        tar_c *= scale
        warnings.append("Char/tar carbon targets were scaled to keep at least 5% of carbon in gas.")

    tar_kmol = tar_c / 6.0
    tar_h = 6.0 * tar_kmol
    tar_kg = tar_kmol * (6.0 * ATOMIC_WEIGHTS["C"] + 6.0 * ATOMIC_WEIGHTS["H"])
    char_kg = char_c * ATOMIC_WEIGHTS["C"] + feedstock.ash_mass_flow_kg_h

    pollutants = estimate_pollutants(
        feed_atoms,
        temperature_c,
        er,
        residual_carbon_factor=char_c / max(c_feed, 1e-12),
        cooling_residence_time_s=cooling_residence_time_s,
        plastics_pct=feedstock.plastics_pct,
        ps_pct=feedstock.ps_pct,
        pvc_pct=feedstock.pvc_pct,
        reduction_zone_severity=reduction_zone_severity,
    )
    gas = {name: 0.0 for name in MOLECULAR_WEIGHTS}
    gas.update(pollutants.species_kmol_h)

    gas_c = max(c_feed - char_c - tar_c - gas.get("HCN", 0.0), 0.0)
    carbon_fractions = normalize(targets.gas_carbon_fractions)
    gas["CO"] = gas_c * carbon_fractions.get("CO", 0.0)
    gas["CO2"] = gas_c * carbon_fractions.get("CO2", 0.0)
    gas["CH4"] = gas_c * carbon_fractions.get("CH4", 0.0)
    gas["C2H4"] = gas_c * carbon_fractions.get("C2H4", 0.0) / 2.0
    gas["C2H6"] = gas_c * carbon_fractions.get("C2H6", 0.0) / 2.0

    # If the target slate requests more oxygen than available, convert CO2 to CO.
    used = product_atoms_kmol_h(gas, char_c, tar_kmol)
    oxygen_deficit = used["O"] - inlet_atoms["O"]
    if oxygen_deficit > 1e-10:
        shift = min(gas["CO2"], oxygen_deficit)
        gas["CO2"] -= shift
        gas["CO"] += shift
        warnings.append("CO2 target reduced to close oxygen balance; check ER/feed oxygen inputs.")

    used = product_atoms_kmol_h(gas, char_c, tar_kmol)
    oxygen_deficit = used["O"] - inlet_atoms["O"]
    if oxygen_deficit > 1e-10:
        shift = min(gas["CO"], oxygen_deficit)
        gas["CO"] -= shift
        char_c += shift
        char_kg += shift * ATOMIC_WEIGHTS["C"]
        warnings.append("CO target reduced and carbon assigned to char to close severe oxygen deficit.")

    used = product_atoms_kmol_h(gas, char_c, tar_kmol)
    h_rem = inlet_atoms["H"] - used["H"]
    o_rem = inlet_atoms["O"] - used["O"]
    if h_rem < -1e-9:
        warnings.append("Hydrogen deficit detected; hydrocarbon/tar correlations may be too high.")
        gas["CH4"] = max(0.0, gas["CH4"] + h_rem / 4.0)
        h_rem = 0.0
    if o_rem < -1e-9:
        warnings.append("Oxygen deficit remains after corrections; balance check will expose residual.")
        o_rem = 0.0

    water = min(o_rem, h_rem / 2.0)
    gas["H2O"] += max(water, 0.0)
    h_rem -= 2.0 * water
    o_rem -= water
    gas["H2"] += max(h_rem / 2.0, 0.0)
    gas["O2"] += max(o_rem / 2.0, 0.0)

    used = product_atoms_kmol_h(gas, char_c, tar_kmol)
    n_rem = inlet_atoms["N"] - used["N"]
    if n_rem >= 0:
        gas["N2"] += n_rem / 2.0
    else:
        warnings.append("Nitrogen minor-species split exceeded available nitrogen.")

    char_composition = estimate_char_composition(
        char_kg_h=char_kg,
        char_carbon_kmol_h=char_c,
        ash_kg_h=feedstock.ash_mass_flow_kg_h,
        tar_kg_h=tar_kg,
        temperature_c=temperature_c,
        er=er,
        residence_time_s=1.0,
    )

    warnings.extend(pollutants.warnings)
    warnings.append(
        f"Dioxin/furan qualitative risk: {pollutants.dioxin_furan_risk} "
        f"(index {pollutants.dioxin_furan_index:.2f})."
    )

    gas = {k: v for k, v in gas.items() if v > 1e-12}
    return ProductSlate(
        gas,
        char_kg,
        char_c,
        char_composition,
        tar_kg,
        tar_kmol,
        "C6H6 pseudo-tar",
        pollutants.trace_indicators,
        warnings,
    )


def estimate_char_composition(
    char_kg_h: float,
    char_carbon_kmol_h: float,
    ash_kg_h: float,
    tar_kg_h: float,
    temperature_c: float,
    er: float,
    residence_time_s: float,
) -> dict[str, object]:
    """Estimate char component composition from operating severity.

    The mass components are closed to the modeled char mass. PAH/IPA and
    organic-carbon fractions are placeholders for screening and should be
    replaced by proximate/ultimate analysis or GC-MS data when available.
    """
    carbon_kg_h = char_carbon_kmol_h * ATOMIC_WEIGHTS["C"]
    severity = clamp((temperature_c - 650.0) / 450.0 + 0.35 * er + 0.06 * residence_time_s, 0.0, 1.25)
    organic_fraction_of_carbon = clamp(0.20 - 0.11 * severity, 0.03, 0.22)
    ipa_fraction_of_char = clamp(0.012 * (1.0 - clamp((temperature_c - 750.0) / 350.0, 0.0, 1.0)) + 0.002 * tar_kg_h / max(char_kg_h, 1e-12), 0.0005, 0.02)

    organic_carbon_kg_h = organic_fraction_of_carbon * carbon_kg_h
    ipa_kg_h = min(ipa_fraction_of_char * char_kg_h, organic_carbon_kg_h * 0.65)
    organic_non_ipa_kg_h = max(organic_carbon_kg_h - ipa_kg_h, 0.0)
    fixed_carbon_kg_h = max(carbon_kg_h - organic_carbon_kg_h, 0.0)
    inerts_kg_h = ash_kg_h
    closure = fixed_carbon_kg_h + organic_non_ipa_kg_h + ipa_kg_h + inerts_kg_h

    return {
        "basis": "Semi-empirical char screening composition; components are not a substitute for proximate/ultimate char analysis.",
        "total_char_kg_h": char_kg_h,
        "component_breakdown_kg_h": {
            "fixed_carbon": fixed_carbon_kg_h,
            "organic_carbon_non_ipa": organic_non_ipa_kg_h,
            "ipa_pah": ipa_kg_h,
            "inerts_ash": inerts_kg_h,
        },
        "component_breakdown_wt_pct": {
            "fixed_carbon": 100.0 * fixed_carbon_kg_h / max(char_kg_h, 1e-12),
            "organic_carbon_non_ipa": 100.0 * organic_non_ipa_kg_h / max(char_kg_h, 1e-12),
            "ipa_pah": 100.0 * ipa_kg_h / max(char_kg_h, 1e-12),
            "inerts_ash": 100.0 * inerts_kg_h / max(char_kg_h, 1e-12),
        },
        "elemental_summary_kg_h": {
            "total_carbon": carbon_kg_h,
            "organic_carbon": organic_carbon_kg_h,
            "inerts": inerts_kg_h,
        },
        "surface_group_indicators": {
            "oxygenated_groups": "low" if severity > 0.8 else "medium",
            "nitrogen_sulfur_chlorine_retention": "trace/screening only",
            "ipa_speciation": "lumped PAH/IPA mass, no individual compounds predicted",
        },
        "closure_kg_h": closure,
        "closure_error_kg_h": closure - char_kg_h,
    }


def product_atoms_kmol_h(gas_kmol_h: dict[str, float], char_c_kmol_h: float, tar_kmol_h: float) -> dict[str, float]:
    """Calculate product atoms from gas, char carbon, and pseudo-tar C6H6."""
    atoms = {element: 0.0 for element in ("C", "H", "O", "N", "S", "Cl")}
    atoms["C"] += char_c_kmol_h
    atoms["C"] += 6.0 * tar_kmol_h
    atoms["H"] += 6.0 * tar_kmol_h
    for species, kmol in gas_kmol_h.items():
        for element, count in SPECIES_ATOMS.get(species, {}).items():
            atoms[element] += count * kmol
    return atoms


def check_atomic_balance(
    inlet_atoms: dict[str, float],
    gas_kmol_h: dict[str, float],
    char_c_kmol_h: float,
    tar_kmol_h: float,
    tolerance: float = 1e-6,
) -> dict[str, dict[str, float] | bool]:
    """Compare inlet and product atoms in kmol/h."""
    outlet = product_atoms_kmol_h(gas_kmol_h, char_c_kmol_h, tar_kmol_h)
    details = {}
    ok = True
    for element in ("C", "H", "O", "N", "S", "Cl"):
        diff = outlet[element] - inlet_atoms.get(element, 0.0)
        rel = diff / max(abs(inlet_atoms.get(element, 0.0)), 1e-12)
        details[element] = {"in_kmol_h": inlet_atoms.get(element, 0.0), "out_kmol_h": outlet[element], "diff_kmol_h": diff, "rel_error": rel}
        ok = ok and abs(diff) <= tolerance * max(abs(inlet_atoms.get(element, 0.0)), 1.0)
    return {"ok": ok, "details": details}


def check_mass_balance(
    feedstock: Feedstock,
    oxidant: dict[str, float],
    steam_kmol_h: float,
    slate: ProductSlate,
    tolerance: float = 1e-6,
) -> dict[str, float | bool]:
    """Compare total inlet and outlet mass flows in kg/h."""
    inlet = (
        feedstock.dry_mass_flow_kg_h
        + feedstock.moisture_mass_flow_kg_h
        + oxidant.get("O2", 0.0) * MOLECULAR_WEIGHTS["O2"]
        + oxidant.get("N2", 0.0) * MOLECULAR_WEIGHTS["N2"]
        + steam_kmol_h * MOLECULAR_WEIGHTS["H2O"]
    )
    gas_mass = sum(kmol * MOLECULAR_WEIGHTS[species] for species, kmol in slate.gas_kmol_h.items())
    outlet = gas_mass + slate.char_kg_h + slate.tar_kg_h
    diff = outlet - inlet
    rel = diff / max(abs(inlet), 1e-12)
    return {"ok": abs(rel) <= tolerance, "in_kg_h": inlet, "out_kg_h": outlet, "diff_kg_h": diff, "rel_error": rel}


def mol_percent(gas_kmol_h: dict[str, float], wet: bool) -> dict[str, float]:
    """Return mol percent for dry or wet gas."""
    excluded = set() if wet else {"H2O"}
    total = sum(v for k, v in gas_kmol_h.items() if k not in excluded)
    if total <= 0:
        return {}
    return {k: 100.0 * v / total for k, v in gas_kmol_h.items() if k not in excluded}


def gas_volume_nm3_h(gas_kmol_h: dict[str, float], wet: bool) -> float:
    """Return normal volume flow in Nm3/h."""
    excluded = set() if wet else {"H2O"}
    return sum(v for k, v in gas_kmol_h.items() if k not in excluded) * NM3_PER_KMOL
