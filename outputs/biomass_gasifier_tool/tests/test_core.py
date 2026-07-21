"""Unit tests for the simplified gasification model."""

from __future__ import annotations

import math
import json
import tempfile
import unittest
from dataclasses import replace

from feedstock import Feedstock
from gasifier import Gasifier, GasifierConditions
from reactions import check_atomic_balance, inlet_atoms_kmol_h, oxidant_from_er, stoichiometric_o2_kmol_h
from utils import AIR_N2_O2_MOLAR_RATIO, ATOMIC_WEIGHTS, MOLECULAR_WEIGHTS
from tracker import record_request


def sample_feedstock() -> Feedstock:
    """Return the example feedstock from the project request."""
    return Feedstock(
        mass_flow_kg_h=100.0,
        mass_basis="dry",
        moisture_pct=10.0,
        C_pct=50.0,
        H_pct=6.0,
        O_pct=42.0,
        N_pct=1.0,
        S_pct=0.1,
        Cl_pct=0.05,
        ash_pct=0.85,
        cellulose_pct=40.0,
        hemicellulose_pct=25.0,
        lignin_pct=25.0,
        extractives_pct=10.0,
    )


def run_case(temperature: float = 850.0, er: float = 0.30) -> dict:
    """Run a standard semi-empirical case."""
    return Gasifier(
        sample_feedstock(),
        GasifierConditions(
            temperature_c=temperature,
            pressure_bar=1.0,
            residence_time_s=2.0,
            er=er,
            agent="air",
            model="semi_empirical",
        ),
    ).simulate()


class CoreModelTests(unittest.TestCase):
    """Core model regression tests."""

    def test_stoichiometric_o2_calculation(self) -> None:
        """O2 stoichiometric demand follows C + H/4 + S - O/2."""
        feed = sample_feedstock()
        atoms = feed.elemental_kmol_h()
        expected = atoms["C"] + atoms["H"] / 4.0 + atoms["S"] - atoms["O"] / 2.0
        self.assertTrue(math.isclose(stoichiometric_o2_kmol_h(feed), expected, rel_tol=1e-12))

    def test_mass_to_moles_conversion(self) -> None:
        """Elemental kg/h convert to atomic kmol/h with atomic weights."""
        feed = sample_feedstock()
        atoms = feed.elemental_kmol_h()
        self.assertTrue(math.isclose(atoms["C"], 50.0 / ATOMIC_WEIGHTS["C"], rel_tol=1e-12))
        self.assertTrue(math.isclose(atoms["H"], 6.0 / ATOMIC_WEIGHTS["H"], rel_tol=1e-12))

    def test_atomic_balance_closure(self) -> None:
        """The simulator closes C/H/O/N/S/Cl balances within numerical tolerance."""
        feed = sample_feedstock()
        result = run_case()
        oxidant = oxidant_from_er(feed, result["oxidant"]["er"], "air")
        inlet_atoms = inlet_atoms_kmol_h(feed, oxidant, 0.0)
        gas = result["gas"]["species_kmol_h"]
        char_c = result["yields"]["char_kg_h"] - feed.ash_mass_flow_kg_h
        char_c /= ATOMIC_WEIGHTS["C"]
        tar_kmol = result["yields"]["tar_cnhm_kg_h"] / (6.0 * ATOMIC_WEIGHTS["C"] + 6.0 * ATOMIC_WEIGHTS["H"])
        balance = check_atomic_balance(inlet_atoms, gas, char_c, tar_kmol)
        self.assertTrue(balance["ok"], balance)
        self.assertTrue(result["balances"]["mass"]["ok"], result["balances"]["mass"])

    def test_temperature_reduces_char_and_tar(self) -> None:
        """Higher temperature qualitatively lowers char and tar yields."""
        low = run_case(temperature=750.0, er=0.30)
        high = run_case(temperature=950.0, er=0.30)
        self.assertLess(high["yields"]["char_kg_h"], low["yields"]["char_kg_h"])
        self.assertLess(high["yields"]["tar_cnhm_kg_h"], low["yields"]["tar_cnhm_kg_h"])

    def test_er_increases_co2_and_air_n2(self) -> None:
        """Higher ER raises CO2 tendency and N2 dilution for air gasification."""
        low = run_case(temperature=850.0, er=0.20)
        high = run_case(temperature=850.0, er=0.40)
        self.assertGreater(high["gas"]["dry_composition_mol_pct"]["CO2"], low["gas"]["dry_composition_mol_pct"]["CO2"])
        self.assertGreater(high["oxidant"]["n2_in_kmol_h"], low["oxidant"]["n2_in_kmol_h"])

    def test_gas_species_flow_table_reports_volume_and_mass(self) -> None:
        """Gas tables expose mol percent, normal volume, and mass per species."""
        result = run_case()
        co = result["gas"]["dry_species_flows"]["CO"]
        co_kmol = result["gas"]["species_kmol_h"]["CO"]
        self.assertTrue(math.isclose(co["nm3_h"], co_kmol * 22.414, rel_tol=1e-12))
        self.assertTrue(math.isclose(co["kg_h"], co_kmol * MOLECULAR_WEIGHTS["CO"], rel_tol=1e-12))
        self.assertNotIn("H2O", result["gas"]["dry_species_flows"])
        self.assertIn("H2O", result["gas"]["wet_species_flows"])

    def test_hhv_channiwala_parikh_correlation(self) -> None:
        """HHV/PCS fallback follows the Channiwala-Parikh ultimate correlation."""
        feed = sample_feedstock()
        expected = (
            0.3491 * feed.C_pct
            + 1.1783 * feed.H_pct
            + 0.1005 * feed.S_pct
            - 0.1034 * feed.O_pct
            - 0.0151 * feed.N_pct
            - 0.0211 * feed.ash_pct
        )
        self.assertTrue(math.isclose(feed.estimated_hhv_mj_kg(), expected, rel_tol=1e-12))

    def test_stoichiometric_and_gasification_air(self) -> None:
        """Stoichiometric air and actual gasification air scale with ER."""
        feed = sample_feedstock()
        result = run_case(er=0.30)
        o2 = stoichiometric_o2_kmol_h(feed)
        expected_air_kg_h = o2 * (MOLECULAR_WEIGHTS["O2"] + AIR_N2_O2_MOLAR_RATIO * MOLECULAR_WEIGHTS["N2"])
        self.assertTrue(math.isclose(result["oxidant"]["stoich_air_kg_h"], expected_air_kg_h, rel_tol=1e-12))
        self.assertTrue(math.isclose(result["oxidant"]["air_in_kg_h"], 0.30 * expected_air_kg_h, rel_tol=1e-12))

    def test_allothermal_overall_efficiency_definition(self) -> None:
        """Overall efficiency includes external heat in the denominator."""
        result = Gasifier(
            sample_feedstock(),
            GasifierConditions(
                temperature_c=850.0,
                er=0.30,
                agent="air",
                thermal_mode="allothermal",
                external_heat_input_kw=100.0,
                syngas_cooler_outlet_c=40.0,
                heat_exchanger_effectiveness=0.75,
            ),
        ).simulate()
        energy = result["energy_balance"]
        expected = 100.0 * (
            energy["syngas_chemical_power_lhv_kw"] + energy["thermal_recovery_kw"]
        ) / (
            energy["feedstock_chemical_power_lhv_kw"] + energy["external_thermal_input_kw"]
        )
        self.assertTrue(math.isclose(energy["overall_efficiency_pct"], expected, rel_tol=1e-12))
        self.assertEqual(energy["external_thermal_input_kw"], 100.0)

    def test_heat_recovery_scales_with_effectiveness(self) -> None:
        """Recovered power scales linearly with exchanger effectiveness."""
        base = dict(temperature_c=850.0, er=0.30, agent="air", syngas_cooler_outlet_c=40.0)
        low = Gasifier(sample_feedstock(), GasifierConditions(**base, heat_exchanger_effectiveness=0.50)).simulate()
        high = Gasifier(sample_feedstock(), GasifierConditions(**base, heat_exchanger_effectiveness=0.80)).simulate()
        self.assertGreater(high["energy_balance"]["thermal_recovery_kw"], low["energy_balance"]["thermal_recovery_kw"])
        self.assertTrue(
            math.isclose(
                high["energy_balance"]["thermal_recovery_kw"] / low["energy_balance"]["thermal_recovery_kw"],
                0.80 / 0.50,
                rel_tol=1e-12,
            )
        )

    def test_olivine_reduces_tar_and_reports_efficiency_impact(self) -> None:
        """Catalyst screening lowers tar while preserving model balances."""
        baseline = run_case()
        catalyzed = Gasifier(
            sample_feedstock(),
            GasifierConditions(
                temperature_c=850.0,
                residence_time_s=2.0,
                er=0.30,
                agent="air",
                catalyst_type="olivine",
                catalyst_to_biomass_ratio=0.20,
                catalyst_activity=1.0,
            ),
        ).simulate()
        self.assertLess(catalyzed["yields"]["tar_cnhm_kg_h"], baseline["yields"]["tar_cnhm_kg_h"])
        self.assertTrue(catalyzed["balances"]["mass"]["ok"])
        self.assertTrue(catalyzed["balances"]["atomic"]["ok"])
        comparison = catalyzed["catalyst"]["comparison_vs_no_catalyst"]
        self.assertLess(comparison["tar_yield_change_pct"], 0.0)
        self.assertIn("cge_percentage_point_change", comparison)

    def test_updraft_has_more_tar_than_downdraft(self) -> None:
        """Reactor screening profiles reproduce the expected tar ordering."""
        common = dict(
            temperature_c=850.0,
            residence_time_s=2.0,
            er=0.30,
            agent="air",
        )
        updraft = Gasifier(
            sample_feedstock(),
            GasifierConditions(**common, gasifier_type="updraft"),
        ).simulate()
        downdraft = Gasifier(
            sample_feedstock(),
            GasifierConditions(**common, gasifier_type="downdraft"),
        ).simulate()
        self.assertGreater(updraft["yields"]["tar_cnhm_kg_h"], downdraft["yields"]["tar_cnhm_kg_h"])
        self.assertTrue(updraft["balances"]["atomic"]["ok"])
        self.assertTrue(downdraft["balances"]["atomic"]["ok"])

    def test_plastics_raise_hydrocarbon_and_tar_tendency(self) -> None:
        """Plastic structural descriptors affect empirical product tendencies."""
        biomass = run_case()
        rdf_feed = replace(
            sample_feedstock(),
            cellulose_pct=20.0,
            hemicellulose_pct=10.0,
            lignin_pct=15.0,
            extractives_pct=5.0,
            plastics_pct=45.0,
            pe_pp_pct=30.0,
            ps_pct=10.0,
            pet_pct=3.0,
            pvc_pct=2.0,
            other_organics_pct=5.0,
        )
        rdf = Gasifier(
            rdf_feed,
            GasifierConditions(temperature_c=850.0, residence_time_s=2.0, er=0.30, agent="air"),
        ).simulate()
        self.assertGreater(rdf["yields"]["tar_cnhm_kg_h"], biomass["yields"]["tar_cnhm_kg_h"])
        self.assertGreater(
            rdf["gas"]["dry_composition_mol_pct"]["C2H4"],
            biomass["gas"]["dry_composition_mol_pct"]["C2H4"],
        )

    def test_pcdd_f_temperature_profile_peaks_in_de_novo_window(self) -> None:
        """PCDD/F screening separates hot-zone destruction from cooling formation."""
        low_temperature = run_case(temperature=700.0)
        high_temperature = run_case(temperature=900.0)
        low_trace = low_temperature["gas"]["trace_pollutants"]["temperature_sensitivity"]
        high_trace = high_temperature["gas"]["trace_pollutants"]["temperature_sensitivity"]
        profile = high_trace["post_gasifier_de_novo_risk_index_by_temperature_c"]
        self.assertEqual(max(profile, key=profile.get), "325")
        self.assertLess(
            high_trace["in_reactor_pcdd_f_survival_index_0_1"],
            low_trace["in_reactor_pcdd_f_survival_index_0_1"],
        )

    def test_reduction_zone_lowers_nitrogen_trace_species(self) -> None:
        """Reducing-zone severity suppresses NOx and NH3/HCN trace estimates."""
        common = dict(temperature_c=850.0, residence_time_s=2.0, er=0.35, agent="air")
        weak = Gasifier(
            sample_feedstock(),
            GasifierConditions(**common, reduction_zone_severity=0.0),
        ).simulate()
        strong = Gasifier(
            sample_feedstock(),
            GasifierConditions(**common, reduction_zone_severity=0.90),
        ).simulate()
        weak_species = weak["gas"]["species_kmol_h"]
        strong_species = strong["gas"]["species_kmol_h"]
        self.assertLess(strong_species.get("NO", 0.0), weak_species.get("NO", 0.0))
        self.assertLess(strong_species.get("NO2", 0.0), weak_species.get("NO2", 0.0))
        self.assertLess(strong_species.get("NH3", 0.0), weak_species.get("NH3", 0.0))
        self.assertLess(strong_species.get("HCN", 0.0), weak_species.get("HCN", 0.0))

    def test_request_tracker_counts_and_logs_ip(self) -> None:
        """Tracker persists counts and appends structured access events."""
        with tempfile.TemporaryDirectory() as log_dir:
            first = record_request(log_dir, "192.0.2.10", "test-agent", "/api/simulate", "200 OK")
            second = record_request(log_dir, "192.0.2.11", "test-agent", "/api/simulate", "400 Bad Request")
            self.assertEqual((first, second), (1, 2))
            with open(f"{log_dir}/access.jsonl", encoding="utf-8") as log_file:
                events = [json.loads(line) for line in log_file]
            self.assertEqual(len(events), 2)
            self.assertEqual(events[0]["remote_ip"], "192.0.2.10")
            self.assertEqual(events[1]["request_count"], 2)

    def test_composition_sums_are_strictly_validated(self) -> None:
        """Elemental and main structural fractions must close to 100%."""
        with self.assertRaisesRegex(ValueError, "elemental composition"):
            replace(sample_feedstock(), C_pct=48.0)
        with self.assertRaisesRegex(ValueError, "Structural composition"):
            replace(sample_feedstock(), cellulose_pct=35.0)
        with self.assertRaisesRegex(ValueError, "Plastic subtypes"):
            replace(
                sample_feedstock(),
                cellulose_pct=0.0,
                hemicellulose_pct=0.0,
                lignin_pct=0.0,
                extractives_pct=0.0,
                plastics_pct=100.0,
                pe_pp_pct=80.0,
                ps_pct=30.0,
            )


if __name__ == "__main__":
    unittest.main()
