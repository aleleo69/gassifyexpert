"""Command-line interface for the biomass gasification simulator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from feedstock import Feedstock
from gasifier import Gasifier, GasifierConditions
from utils import write_csv, write_json


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser."""
    parser = argparse.ArgumentParser(description="Simplified biomass gasification simulator")
    parser.add_argument("--mass", type=float, default=100.0, help="Biomass mass flow [kg/h]")
    parser.add_argument("--mass-basis", choices=["dry", "wet"], default="dry")
    parser.add_argument("--moisture", type=float, default=10.0, help="Moisture [%%]")
    parser.add_argument("--C", type=float, default=50.0)
    parser.add_argument("--H", type=float, default=6.0)
    parser.add_argument("--O", type=float, default=42.0)
    parser.add_argument("--N", type=float, default=1.0)
    parser.add_argument("--S", type=float, default=0.1)
    parser.add_argument("--Cl", type=float, default=0.05)
    parser.add_argument("--ash", type=float, default=0.85)
    parser.add_argument("--cellulose", type=float, default=40.0)
    parser.add_argument("--hemicellulose", type=float, default=25.0)
    parser.add_argument("--lignin", type=float, default=25.0)
    parser.add_argument("--extractives", type=float, default=10.0)
    parser.add_argument("--plastics", type=float, default=0.0)
    parser.add_argument("--pe-pp", type=float, default=0.0)
    parser.add_argument("--ps", type=float, default=0.0)
    parser.add_argument("--pet", type=float, default=0.0)
    parser.add_argument("--pvc", type=float, default=0.0)
    parser.add_argument("--other-organics", type=float, default=0.0)
    parser.add_argument("--lhv", type=float, default=None, help="Dry feed LHV/PCI [MJ/kg]")
    parser.add_argument("--hhv", type=float, default=None, help="Dry feed HHV/PCS [MJ/kg]")
    parser.add_argument("--temperature", type=float, default=850.0, help="Gasification temperature [C]")
    parser.add_argument("--pressure", type=float, default=1.0, help="Pressure [bar]")
    parser.add_argument("--residence-time", type=float, default=2.0, help="Residence time [s]")
    parser.add_argument("--er", type=float, default=0.30, help="Equivalence ratio")
    parser.add_argument("--o2-flow-kmol-h", type=float, default=None, help="Direct O2 flow [kmol/h]")
    parser.add_argument("--agent", choices=["air", "oxygen", "steam", "air+steam"], default="air")
    parser.add_argument("--steam-biomass-ratio", type=float, default=0.0, help="Steam/dry-biomass mass ratio")
    parser.add_argument("--model", choices=["stoichiometric_equilibrium", "semi_empirical", "hybrid"], default="semi_empirical")
    parser.add_argument("--thermal-mode", choices=["autothermal", "allothermal"], default="autothermal")
    parser.add_argument("--external-heat-kw", type=float, default=0.0, help="External thermal input [kW], allothermal mode")
    parser.add_argument("--syngas-cooler-outlet", type=float, default=40.0, help="Syngas cooler outlet [C]")
    parser.add_argument("--heat-exchanger-effectiveness", type=float, default=0.75, help="Gas-air exchanger effectiveness [0-1]")
    parser.add_argument("--catalyst", choices=["none", "olivine", "calcined_olivine", "limestone", "dolomite", "nickel_based"], default="none")
    parser.add_argument("--catalyst-ratio", type=float, default=0.0, help="Catalyst/dry-biomass ratio [kg/kg]")
    parser.add_argument("--catalyst-activity", type=float, default=1.0, help="Relative catalyst activity [0-1]")
    parser.add_argument(
        "--gasifier-type",
        choices=["generic", "updraft", "downdraft", "bubbling_fluidized_bed", "circulating_fluidized_bed", "entrained_flow"],
        default="generic",
    )
    parser.add_argument("--syngas-cooling-time", type=float, default=2.0, help="Residence time through syngas cooling train [s]")
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--csv-out", type=Path, default=None)
    return parser


def run_from_args(args: argparse.Namespace) -> dict:
    """Build inputs from parsed CLI args and run the simulation."""
    feedstock = Feedstock(
        mass_flow_kg_h=args.mass,
        mass_basis=args.mass_basis,
        moisture_pct=args.moisture,
        C_pct=args.C,
        H_pct=args.H,
        O_pct=args.O,
        N_pct=args.N,
        S_pct=args.S,
        Cl_pct=args.Cl,
        ash_pct=args.ash,
        cellulose_pct=args.cellulose,
        hemicellulose_pct=args.hemicellulose,
        lignin_pct=args.lignin,
        extractives_pct=args.extractives,
        plastics_pct=args.plastics,
        pe_pp_pct=args.pe_pp,
        ps_pct=args.ps,
        pet_pct=args.pet,
        pvc_pct=args.pvc,
        other_organics_pct=args.other_organics,
        lhv_mj_kg=args.lhv,
        hhv_mj_kg=args.hhv,
    )
    conditions = GasifierConditions(
        temperature_c=args.temperature,
        pressure_bar=args.pressure,
        residence_time_s=args.residence_time,
        er=args.er,
        o2_flow_kmol_h=args.o2_flow_kmol_h,
        agent=args.agent,
        steam_biomass_ratio=args.steam_biomass_ratio,
        model=args.model,
        thermal_mode=args.thermal_mode,
        external_heat_input_kw=args.external_heat_kw,
        syngas_cooler_outlet_c=args.syngas_cooler_outlet,
        heat_exchanger_effectiveness=args.heat_exchanger_effectiveness,
        catalyst_type=args.catalyst,
        catalyst_to_biomass_ratio=args.catalyst_ratio,
        catalyst_activity=args.catalyst_activity,
        gasifier_type=args.gasifier_type,
        syngas_cooling_time_s=args.syngas_cooling_time,
    )
    result = Gasifier(feedstock, conditions).simulate()
    if args.json_out:
        write_json(result, args.json_out)
    if args.csv_out:
        write_csv(result, args.csv_out)
    return result


def main() -> None:
    """CLI entry point."""
    result = run_from_args(build_parser().parse_args())
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
