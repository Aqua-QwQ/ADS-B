# -*- coding: utf-8 -*-
"""One-command runner for the ADS-B baseband experiment."""

import argparse
import os
import subprocess
import sys
from pathlib import Path


CODE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CODE_DIR.parent
RUNTIME_CACHE_DIR = Path("/tmp") / "adsb_pipeline_cache"
DEFAULT_SNR_VALUES = [20, 10, 5, 0]


def run_step(name, command):
    print(f"\n=== {name} ===", flush=True)
    print(" ".join(str(part) for part in command), flush=True)
    env = os.environ.copy()
    env.setdefault("MPLCONFIGDIR", str(RUNTIME_CACHE_DIR / "matplotlib"))
    env.setdefault("XDG_CACHE_HOME", str(RUNTIME_CACHE_DIR / "xdg"))
    completed = subprocess.run(
        command, cwd=str(PROJECT_ROOT), env=env, check=False
    )
    if completed.returncode != 0:
        raise RuntimeError(f"{name} failed with exit code {completed.returncode}")


def verify_outputs(snr_values):
    required = [
        PROJECT_ROOT / "data" / "tx_bits.txt",
        PROJECT_ROOT / "data" / "adsb_frame_bits.txt",
        PROJECT_ROOT / "data" / "tx_samples.dat",
        PROJECT_ROOT / "results" / "ber_stat.csv",
        PROJECT_ROOT / "figures" / "ber_curve.png",
    ]
    required.extend(
        PROJECT_ROOT / "data" / f"rx_samples_snr{snr}.dat"
        for snr in snr_values
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("missing expected output files:\n" + "\n".join(missing))
    return required


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run transmitter, AWGN channel, and receiver in one command."
    )
    parser.add_argument(
        "--mode",
        choices=["single", "multi"],
        default="multi",
        help="transmitter mode; multi also refreshes the single-frame interface",
    )
    parser.add_argument(
        "--config",
        default="config/aircraft_scenario.json",
        help="scenario JSON used by --mode multi",
    )
    parser.add_argument(
        "--snr",
        nargs="+",
        type=int,
        default=DEFAULT_SNR_VALUES,
        help="SNR values in dB",
    )
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args(argv)

    py = sys.executable
    transmitter_cmd = [
        py,
        str(CODE_DIR / "transmitter.py"),
        "--mode",
        args.mode,
    ]
    if args.mode == "multi":
        transmitter_cmd.extend(["--config", args.config])

    awgn_cmd = [
        py,
        str(CODE_DIR / "awgn_channel.py"),
        "--snr",
        *[str(snr) for snr in args.snr],
        "--seed",
        str(args.seed),
    ]
    if args.no_plots:
        awgn_cmd.append("--no-plots")

    run_step("1. Transmitter", transmitter_cmd)
    run_step("2. AWGN channel", awgn_cmd)
    run_step("3. Receiver", [py, str(CODE_DIR / "receiver.py")])
    outputs = verify_outputs(args.snr)

    print("\n=== Pipeline summary ===", flush=True)
    print(f"Project root: {PROJECT_ROOT}", flush=True)
    print(f"SNR values  : {args.snr}", flush=True)
    print("Key outputs :", flush=True)
    for path in outputs:
        print(f"  - {path.relative_to(PROJECT_ROOT)}", flush=True)
    print("\nRun complete.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
