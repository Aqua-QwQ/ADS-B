# -*- coding: utf-8 -*-
"""
ADS-B 1090ES Baseband Communication Prototype System - Transmitter (Member 3)
Author: Part_3
Date: 2026-06-14

Pipeline:
    virtual aircraft state
        -> member 2 generate_adsb_frame(state)   [112-bit list]
        -> add 16-bit preamble                   [128-bit stream]
        -> PPM modulation (1->[1,0], 0->[0,1])   [256 samples]
        -> save files + plots

Member 2 interface adaptation notes (see code/test_interface.py):
  * generate_adsb_frame(state) RETURNS A LIST OF INTS (not a string).
    We convert it to a '0'/'1' string via member 2's bits_to_string().
  * state field mapping (recommended -> member 2 actual):
        icao        "ABCDEF"  (str)   ->  0xABCDEF   (24-bit int)
        callsign    "TEST123"         ->  (not encoded by member 2)
        latitude_q  quantized int     ->  latitude   (physical deg, float)
        longitude_q quantized int     ->  longitude  (physical deg, float)
        heading     int degrees       ->  heading    (float degrees)
        (none)                        ->  type_code  (required int 0-31)
        (none)                        ->  df (default 17), ca (default 5)
  Member 2's message structure / CRC rules are NOT modified here.

Run:
    python code/transmitter.py
"""

import sys
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")  # headless rendering
import matplotlib.pyplot as plt  # noqa: E402

# --- locate member 2 module -------------------------------------------------
CODE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CODE_DIR.parent
sys.path.insert(0, str(CODE_DIR))

from adsb_frame import generate_adsb_frame, bits_to_string  # noqa: E402

# --- hard-wired protocol constants -----------------------------------------
PREAMBLE = "1010000101000000"          # 16-bit Mode-S / ADS-B preamble
ADSB_FRAME_BITS = 112                  # DF+CA+ICAO+ME+CRC
TX_BITS_TOTAL = 128                    # 16 preamble + 112 frame
PPM_SAMPLES_PER_BIT = 2                # 1->[1,0], 0->[0,1]
TX_SAMPLES_TOTAL = TX_BITS_TOTAL * PPM_SAMPLES_PER_BIT  # 256

# Baseband-only simulation. ADS-B bit rate = 1 Mbit/s => 1 bit = 1 us.
# With 2 samples/bit the sample rate is 2 Msps.
SAMPLE_RATE = 2e6

DATA_DIR = PROJECT_ROOT / "data"
FIG_DIR = PROJECT_ROOT / "figures"


# ---------------------------------------------------------------------------
# 1. virtual aircraft state (adapted to member 2's real fields)
# ---------------------------------------------------------------------------
def generate_virtual_aircraft_state():
    """Return a virtual aircraft state dict matching member 2's contract.

    Member 2 requires: df, ca, icao(24-bit int), type_code, altitude(ft),
    speed(knots), heading(deg float), latitude(deg float), longitude(deg float).
    We use a fixed seed so the run is reproducible but still looks generated.
    """
    rng = np.random.default_rng(42)

    def gen_icao():
        # random 24-bit ICAO
        return int(rng.integers(0, 0xFFFFFF + 1))

    # airborne commercial aircraft near Beijing
    state = {
        "df": 17,                                   # ADS-B extended squitter
        "ca": 5,                                    # capability
        "icao": gen_icao(),                         # 24-bit int
        "type_code": 19,                            # valid ME type code
        "altitude": float(np.round(rng.integers(8000, 12001) / 25) * 25),  # ft
        "speed": float(rng.integers(200, 300)),     # knots
        "heading": float(np.round(rng.uniform(0, 360), 2)),  # deg
        "latitude": float(np.round(rng.uniform(39.0, 41.0), 4)),   # deg
        "longitude": float(np.round(rng.uniform(115.0, 117.5), 4)),  # deg
    }
    return state


# ---------------------------------------------------------------------------
# 2. ADS-B frame
# ---------------------------------------------------------------------------
def _normalize_bits(value):
    """Accept a '0'/'1' string or an iterable of ints; return a list of ints."""
    if isinstance(value, str):
        if any(c not in "01" for c in value):
            raise ValueError("bit string must contain only '0' and '1'")
        return [int(c) for c in value]
    bits = list(value)
    if any(b not in (0, 1) for b in bits):
        raise ValueError("bits must contain only 0 and 1")
    return bits


def get_adsb_frame(state):
    """Generate the 112-bit ADS-B frame as a '0'/'1' string.

    Member 2 returns a list of ints; we convert it to a string so the rest of
    the pipeline (text outputs) stays text-based. The frame content is produced
    entirely by member 2 and is not altered here.
    """
    frame_bits = generate_adsb_frame(state)            # list[int], len 112
    frame_str = bits_to_string(frame_bits)             # '0'/'1' string
    if len(frame_str) != ADSB_FRAME_BITS:
        raise RuntimeError(
            f"ADS-B frame must be {ADSB_FRAME_BITS} bits, got {len(frame_str)}"
        )
    return frame_str


# ---------------------------------------------------------------------------
# 3. preamble
# ---------------------------------------------------------------------------
def add_preamble(adsb_bits):
    """Prepend the fixed 16-bit preamble -> 128-bit transmit stream (string)."""
    bits = _normalize_bits(adsb_bits)
    if len(bits) != ADSB_FRAME_BITS:
        raise ValueError(
            f"adsb_bits must be {ADSB_FRAME_BITS} bits, got {len(bits)}"
        )
    if len(PREAMBLE) != 16:
        raise RuntimeError("preamble must be 16 bits")
    full = PREAMBLE + "".join(str(b) for b in bits)
    if len(full) != TX_BITS_TOTAL:
        raise RuntimeError(
            f"tx bit stream must be {TX_BITS_TOTAL} bits, got {len(full)}"
        )
    return full


# ---------------------------------------------------------------------------
# 4. PPM modulation
# ---------------------------------------------------------------------------
def ppm_modulate(tx_bits):
    """PPM map: 1 -> [1, 0], 0 -> [0, 1]. Returns float32 numpy array (256 pts)."""
    bits = _normalize_bits(tx_bits)
    if len(bits) != TX_BITS_TOTAL:
        raise ValueError(
            f"tx_bits must be {TX_BITS_TOTAL} bits, got {len(bits)}"
        )
    samples = np.empty(TX_SAMPLES_TOTAL, dtype=np.float32)
    for i, bit in enumerate(bits):
        if bit == 1:
            samples[2 * i] = 1.0
            samples[2 * i + 1] = 0.0
        else:
            samples[2 * i] = 0.0
            samples[2 * i + 1] = 1.0
    if samples.size != TX_SAMPLES_TOTAL:
        raise RuntimeError(
            f"PPM samples must be {TX_SAMPLES_TOTAL}, got {samples.size}"
        )
    return samples


# ---------------------------------------------------------------------------
# 5. save outputs
# ---------------------------------------------------------------------------
def save_outputs(state, adsb_bits, tx_bits, tx_samples):
    """Write data/tx_bits.txt, adsb_frame_bits.txt, tx_samples.dat, tx_state.txt."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    (DATA_DIR / "tx_bits.txt").write_text(tx_bits + "\n", encoding="ascii")
    (DATA_DIR / "adsb_frame_bits.txt").write_text(adsb_bits + "\n", encoding="ascii")

    # raw float32 binary
    tx_samples.astype(np.float32).tofile(str(DATA_DIR / "tx_samples.dat"))

    lines = ["# virtual aircraft state (member-2 compatible)"]
    for key, value in state.items():
        if key == "icao":
            lines.append(f"{key}={value} ({hex(value)})")
        else:
            lines.append(f"{key}={value}")
    (DATA_DIR / "tx_state.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# 6. plots
# ---------------------------------------------------------------------------
def plot_waveform(tx_samples, path=None):
    """Time-domain PPM waveform."""
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    if path is None:
        path = FIG_DIR / "tx_waveform.png"

    t_us = np.arange(tx_samples.size) / SAMPLE_RATE * 1e6  # microseconds
    fig, ax = plt.subplots(figsize=(12, 3))
    ax.step(t_us, tx_samples, where="post", linewidth=1.2)
    ax.set_xlim(0, TX_BITS_TOTAL * PPM_SAMPLES_PER_BIT / SAMPLE_RATE * 1e6)
    ax.set_ylim(-0.2, 1.2)
    ax.set_xlabel("Time (us)")
    ax.set_ylabel("Amplitude")
    ax.set_title(
        f"ADS-B PPM baseband waveform ({tx_samples.size} samples, "
        f"{TX_BITS_TOTAL} bits)"
    )
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(str(path), dpi=150)
    plt.close(fig)
    return str(path)


def plot_spectrum(tx_samples, path=None, fs=SAMPLE_RATE):
    """Single-sided magnitude spectrum of the baseband signal."""
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    if path is None:
        path = FIG_DIR / "tx_spectrum.png"

    x = tx_samples.astype(np.float64) - np.mean(tx_samples)
    n = x.size
    spectrum = np.fft.rfft(x, n)
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    mag = np.abs(spectrum) / n * 2.0

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(freqs / 1e6, mag, linewidth=1.2)
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("Magnitude")
    ax.set_title(
        f"ADS-B PPM baseband spectrum (N={n}, fs={fs / 1e6:.0f} Msps)"
    )
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(str(path), dpi=150)
    plt.close(fig)
    return str(path)


# ---------------------------------------------------------------------------
# 7. main
# ---------------------------------------------------------------------------
def main():
    print("=== ADS-B transmitter (member 3) ===")

    state = generate_virtual_aircraft_state()
    print("virtual state:", state)

    adsb_bits = get_adsb_frame(state)
    print(f"ADS-B frame : len={len(adsb_bits)} -> {adsb_bits}")

    tx_bits = add_preamble(adsb_bits)
    print(f"tx bit stream: len={len(tx_bits)} -> {tx_bits}")

    tx_samples = ppm_modulate(tx_bits)
    print(
        f"PPM samples : len={tx_samples.size}, "
        f"dtype={tx_samples.dtype}, range=[{tx_samples.min()}, {tx_samples.max()}]"
    )

    save_outputs(state, adsb_bits, tx_bits, tx_samples)
    wf = plot_waveform(tx_samples)
    sp = plot_spectrum(tx_samples)
    print("saved waveform:", wf)
    print("saved spectrum:", sp)

    # hard-rule self-checks
    assert len(adsb_bits) == ADSB_FRAME_BITS
    assert len(tx_bits) == TX_BITS_TOTAL
    assert tx_samples.size == TX_SAMPLES_TOTAL
    assert tx_samples.dtype == np.float32
    print("self-check: all hard rules satisfied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
