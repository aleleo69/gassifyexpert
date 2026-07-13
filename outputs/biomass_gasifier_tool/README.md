# Biomass Gasifier Tool

Python 3.11+ tool for simplified biomass gasification screening.

The model accepts elemental CHNO(S,Cl) composition, moisture, ash, structural
fractions, gasification conditions, ER or O2 flow, and gasifying agent. It
returns gas/char/tar yields, dry and wet gas composition, syngas LHV, estimated
cold gas efficiency, mass and atomic balance checks, warnings, and uncertainty
placeholders.

## Assumptions and limits

- Steady-state ideal gas calculation at normal gas volume basis.
- Complete feedstock bookkeeping for C/H/O/N/S/Cl plus ash.
- Air uses `N2/O2 = 3.76 mol/mol`.
- Char is represented as carbon plus feed ash.
- Tar is represented as a configurable pseudo-species `C6H6`.
- Semi-empirical coefficients are placeholders exposed in `empirical.py`.
- Pollutant species are qualitative screening estimates.
- Dioxins/furans are reported only as `low`, `medium`, or `high` risk index.
- Hybrid/equilibrium mode uses `scipy.optimize` when installed, but is still a
  surrogate, not a rigorous thermodynamic database calculation.

## Example

```bash
python main.py \
  --mass 100 --mass-basis dry --moisture 10 \
  --C 50 --H 6 --O 42 --N 1 --S 0.1 --Cl 0.05 --ash 0.85 \
  --cellulose 40 --hemicellulose 25 --lignin 25 --extractives 10 \
  --temperature 850 --pressure 1 --residence-time 2 \
  --er 0.30 --agent air --model semi_empirical \
  --json-out example_result.json --csv-out example_result.csv
```

Run tests:

```bash
python -m unittest discover -s tests
```

## Web UI

```bash
python web_server.py --host 127.0.0.1 --port 8765
```

Then open `http://127.0.0.1:8765`.
