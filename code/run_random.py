# -*- coding: utf-8 -*-
"""One-command runner using a randomly generated single aircraft state."""

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/adsb_pipeline_cache/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/adsb_pipeline_cache/xdg")

import numpy as np

from run_all import CODE_DIR, PROJECT_ROOT, DEFAULT_SNR_VALUES, run_step, verify_outputs
from transmitter import (
    generate_single_frame_transmission,
    plot_spectrum,
    plot_waveform,
    save_single_outputs,
)


def _resolve_seed(seed):
    if seed is not None:
        return int(seed)
    return int(np.random.SeedSequence().entropy)


def generate_random_aircraft_state(seed=None):
    """Generate one valid random aircraft state for the protocol layer."""
    resolved_seed = _resolve_seed(seed)
    rng = np.random.default_rng(resolved_seed)

    altitude = float(int(rng.integers(0, 4096)) * 25)
    state = {
        "df": 17,
        "ca": 5,
        "icao": int(rng.integers(0, 0xFFFFFF + 1)),
        "type_code": 19,
        "altitude": altitude,
        "speed": float(rng.integers(0, 1024)),
        "heading": float(np.round(rng.uniform(0.0, 360.0), 2)),
        "latitude": float(np.round(rng.uniform(-90.0, 90.0), 4)),
        "longitude": float(np.round(rng.uniform(-180.0, 180.0), 4)),
        "random_seed": resolved_seed,
    }
    return state


def generate_random_transmitter_outputs(seed=None):
    state = generate_random_aircraft_state(seed)
    adsb_bits, tx_bits, tx_samples = generate_single_frame_transmission(state)
    save_single_outputs(state, adsb_bits, tx_bits, tx_samples)
    waveform = plot_waveform(tx_samples)
    spectrum = plot_spectrum(tx_samples)
    return {
        "state": state,
        "adsb_bits": adsb_bits,
        "tx_bits": tx_bits,
        "num_samples": int(tx_samples.size),
        "waveform": waveform,
        "spectrum": spectrum,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run the full ADS-B pipeline with a random single-frame state."
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="random aircraft-state seed; omit for a fresh random seed",
    )
    parser.add_argument(
        "--channel-seed",
        type=int,
        default=2026,
        help="AWGN noise seed",
    )
    parser.add_argument(
        "--snr",
        nargs="+",
        type=int,
        default=DEFAULT_SNR_VALUES,
        help="SNR values in dB",
    )
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args(argv)

    print("\n=== 1. Random transmitter data ===", flush=True)
    tx_info = generate_random_transmitter_outputs(seed=args.seed)
    state = tx_info["state"]
    print(f"seed     : {state['random_seed']}", flush=True)
    print(
        "state    : icao={icao} ({hex_icao}), alt={altitude:.0f} ft, "
        "speed={speed:.0f} kt, heading={heading:.2f} deg, "
        "lat={latitude:.4f}, lon={longitude:.4f}".format(
            hex_icao=hex(state["icao"]), **state
        ),
        flush=True,
    )
    print(
        f"outputs  : {len(tx_info['adsb_bits'])} ADS-B bits, "
        f"{len(tx_info['tx_bits'])} tx bits, {tx_info['num_samples']} samples",
        flush=True,
    )

    py = sys.executable
    awgn_cmd = [
        py,
        str(CODE_DIR / "awgn_channel.py"),
        "--snr",
        *[str(snr) for snr in args.snr],
        "--seed",
        str(args.channel_seed),
    ]
    if args.no_plots:
        awgn_cmd.append("--no-plots")

    run_step("2. AWGN channel", awgn_cmd)
    run_step("3. Receiver", [py, str(CODE_DIR / "receiver.py")])
    outputs = verify_outputs(args.snr)

    print("\n=== Random pipeline summary ===", flush=True)
    print(f"Project root : {PROJECT_ROOT}", flush=True)
    print(f"State seed   : {state['random_seed']}", flush=True)
    print(f"Channel seed : {args.channel_seed}", flush=True)
    print(f"SNR values   : {args.snr}", flush=True)
    print("Key outputs  :", flush=True)
    for path in outputs:
        print(f"  - {Path(path).relative_to(PROJECT_ROOT)}", flush=True)
    print("\nRandom run complete.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
