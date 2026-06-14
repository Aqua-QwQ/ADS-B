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

Two operating modes (see --mode):
    single : one virtual aircraft state -> one 128-bit frame -> 256 samples.
              Produces the member-4 compatible single-frame interface.
    multi  : physics-based dynamic aircraft scenario (config/aircraft_scenario.json)
              -> N trajectory states -> N frames -> N*256 samples, plus trajectory
              and state-vs-time plots. Also refreshes the single-frame interface
              with frame 0 so member 4 keeps working.

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
    python code/transmitter.py --mode single
    python code/transmitter.py --mode multi --config config/aircraft_scenario.json
"""

import argparse
import json
import math
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
CONFIG_DIR = PROJECT_ROOT / "config"
DOCS_DIR = PROJECT_ROOT / "docs"

# --- physics model constants (dynamic trajectory) --------------------------
EARTH_RADIUS_M = 6371000.0
KNOT_TO_MPS = 0.514444

# --- default scenario (used when keys are missing from the config file) ----
DEFAULT_SCENARIO = {
    "icao": 11259375,
    "df": 17,
    "ca": 5,
    "type_code": 19,
    "num_frames": 20,
    "frame_interval_s": 1.0,
    "initial_altitude_ft": 3000.0,
    "vertical_rate_fpm": 600.0,
    "initial_speed_kt": 220.0,
    "acceleration_ktps": 0.2,
    "initial_heading_deg": 80.0,
    "turn_rate_dps": 1.5,
    "initial_latitude_deg": 39.9000,
    "initial_longitude_deg": 116.4000,
}


# ---------------------------------------------------------------------------
# 1. directories
# ---------------------------------------------------------------------------
def ensure_dirs():
    """Create the data/, figures/, config/, docs/ directories if missing."""
    for d in (DATA_DIR, FIG_DIR, CONFIG_DIR, DOCS_DIR):
        d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 2. scenario config
# ---------------------------------------------------------------------------
def load_scenario_config(config_path):
    """Read a JSON scenario config and fill missing fields with defaults.

    Raises FileNotFoundError with a clear message if the file is missing.
    """
    p = Path(config_path)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    if not p.exists():
        raise FileNotFoundError(
            f"scenario config not found: {p}\n"
            f"expected a JSON file like config/aircraft_scenario.json"
        )
    with open(str(p), "r", encoding="utf-8") as f:
        cfg = json.load(f)
    merged = dict(DEFAULT_SCENARIO)
    merged.update(cfg)
    return merged


# ---------------------------------------------------------------------------
# 3. virtual aircraft state (single-frame mode)
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
# 4. physics-based dynamic trajectory (multi-frame mode)
# ---------------------------------------------------------------------------
def generate_aircraft_trajectory(config):
    """Generate a list of aircraft state dicts from a physics motion model.

    The model advances latitude/longitude from ground speed, heading and the
    frame interval (flat-earth equirectangular approximation), and integrates
    altitude / speed / heading from their respective rates. Every returned
    state can be passed directly to member 2's generate_adsb_frame(state).

    An extra non-protocol metadata key "time_s" is attached for plotting / CSV
    convenience; member 2 ignores unknown keys.
    """
    num_frames = int(config["num_frames"])
    dt = float(config["frame_interval_s"])
    icao = int(config["icao"])
    df = int(config["df"])
    ca = int(config["ca"])
    type_code = int(config["type_code"])

    alt0 = float(config["initial_altitude_ft"])
    vs = float(config["vertical_rate_fpm"])
    spd0 = float(config["initial_speed_kt"])
    acc = float(config["acceleration_ktps"])
    hdg0 = float(config["initial_heading_deg"])
    turn = float(config["turn_rate_dps"])
    lat0 = float(config["initial_latitude_deg"])
    lon0 = float(config["initial_longitude_deg"])

    states = []
    cur_lat = lat0
    cur_lon = lon0
    for i in range(num_frames):
        t = i * dt
        altitude_ft = alt0 + vs / 60.0 * t
        speed_kt = spd0 + acc * t
        heading_deg = (hdg0 + turn * t) % 360.0

        # position advance over this frame
        speed_mps = speed_kt * KNOT_TO_MPS
        distance_m = speed_mps * dt
        heading_rad = math.radians(heading_deg)
        north_m = distance_m * math.cos(heading_rad)
        east_m = distance_m * math.sin(heading_rad)
        lat_rad = math.radians(cur_lat)
        delta_lat_deg = math.degrees(north_m / EARTH_RADIUS_M)
        delta_lon_deg = math.degrees(
            east_m / (EARTH_RADIUS_M * math.cos(lat_rad))
        )
        cur_lat += delta_lat_deg
        cur_lon += delta_lon_deg

        # clamp / wrap to protocol-legal ranges
        altitude_ft = min(max(altitude_ft, 0.0), 102375.0)
        speed_kt = min(max(speed_kt, 0.0), 1023.0)
        heading_deg = heading_deg % 360.0
        cur_lat = min(max(cur_lat, -90.0), 90.0)
        cur_lon = ((cur_lon + 180.0) % 360.0) - 180.0

        state = {
            "df": df,
            "ca": ca,
            "icao": icao,
            "type_code": type_code,
            "altitude": altitude_ft,
            "speed": speed_kt,
            "heading": heading_deg,
            "latitude": cur_lat,
            "longitude": cur_lon,
            "time_s": t,
        }
        states.append(state)
    return states


# ---------------------------------------------------------------------------
# 5. ADS-B frame (member 2)
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
    the pipeline (text outputs) stays text-based. Also tolerates a str return
    for forward compatibility. The frame content is produced entirely by
    member 2 and is not altered here.
    """
    frame = generate_adsb_frame(state)            # list[int] (or str), len 112
    if isinstance(frame, str):
        frame_str = frame
    else:
        frame_str = bits_to_string(frame)         # '0'/'1' string
    if len(frame_str) != ADSB_FRAME_BITS:
        raise RuntimeError(
            f"ADS-B frame must be {ADSB_FRAME_BITS} bits, got {len(frame_str)}"
        )
    if any(c not in "01" for c in frame_str):
        raise ValueError("ADS-B frame must contain only '0' and '1'")
    return frame_str


# ---------------------------------------------------------------------------
# 6. preamble
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
# 7. PPM modulation
# ---------------------------------------------------------------------------
def ppm_modulate(tx_bits):
    """PPM map: 1 -> [1, 0], 0 -> [0, 1]. Returns float32 array (256 pts)."""
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
# 8. single-frame transmission
# ---------------------------------------------------------------------------
def generate_single_frame_transmission(state):
    """Run state -> ADS-B frame -> +preamble -> PPM for one frame.

    Returns (adsb_bits, tx_bits, tx_samples) where adsb_bits/tx_bits are
    '0'/'1' strings (112 / 128 chars) and tx_samples is float32 len 256.
    """
    adsb_bits = get_adsb_frame(state)
    tx_bits = add_preamble(adsb_bits)
    tx_samples = ppm_modulate(tx_bits)
    return adsb_bits, tx_bits, tx_samples


# ---------------------------------------------------------------------------
# 9. multi-frame transmission
# ---------------------------------------------------------------------------
def generate_multi_frame_transmission(states):
    """Run the full transmit chain for every state in the trajectory.

    Returns (adsb_bits_list, tx_bits_list, tx_samples_multi) where the two
    lists have len(states) string entries and tx_samples_multi is a single
    float32 array of length len(states) * 256.
    """
    adsb_bits_list = []
    tx_bits_list = []
    chunks = []
    for state in states:
        adsb_bits = get_adsb_frame(state)
        tx_bits = add_preamble(adsb_bits)
        tx_samples = ppm_modulate(tx_bits)
        adsb_bits_list.append(adsb_bits)
        tx_bits_list.append(tx_bits)
        chunks.append(tx_samples)
    tx_samples_multi = np.concatenate(chunks).astype(np.float32)
    return adsb_bits_list, tx_bits_list, tx_samples_multi


# ---------------------------------------------------------------------------
# 10. single-frame outputs (member-4 interface)
# ---------------------------------------------------------------------------
def save_single_outputs(state, adsb_bits, tx_bits, tx_samples):
    """Write the single-frame member-4 interface files.

    - data/adsb_frame_bits.txt : 112-bit ADS-B message
    - data/tx_bits.txt         : 128-bit transmit stream (BER reference)
    - data/tx_samples.dat      : float32, exactly 256 samples (one frame)
    - data/tx_state.txt        : human-readable state used for this frame
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    (DATA_DIR / "tx_bits.txt").write_text(tx_bits + "\n", encoding="ascii")
    (DATA_DIR / "adsb_frame_bits.txt").write_text(
        adsb_bits + "\n", encoding="ascii"
    )

    # raw float32 binary, single frame only
    tx_samples.astype(np.float32).tofile(str(DATA_DIR / "tx_samples.dat"))

    lines = ["# virtual aircraft state (member-2 compatible)"]
    for key, value in state.items():
        if key == "icao":
            lines.append(f"{key}={value} ({hex(value)})")
        else:
            lines.append(f"{key}={value}")
    (DATA_DIR / "tx_state.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


# keep backward-compatible name used by earlier docs
save_outputs = save_single_outputs


# ---------------------------------------------------------------------------
# 11. multi-frame outputs (enhanced experiment)
# ---------------------------------------------------------------------------
def save_multi_outputs(states, adsb_bits_list, tx_bits_list, tx_samples_multi):
    """Write the enhanced multi-frame experiment outputs.

    - data/tx_states.csv            : per-frame state table
    - data/adsb_frame_bits_multi.txt: one 112-bit message per line
    - data/tx_bits_multi.txt        : one 128-bit transmit stream per line
    - data/tx_samples_multi.dat     : float32, len = num_frames * 256
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    header = [
        "frame_index", "time_s", "icao", "type_code",
        "altitude", "speed", "heading", "latitude", "longitude",
    ]
    csv_lines = [",".join(header)]
    for i, s in enumerate(states):
        row = [
            str(i),
            str(s.get("time_s", float(i))),
            str(s["icao"]),
            str(s["type_code"]),
            str(s["altitude"]),
            str(s["speed"]),
            str(s["heading"]),
            str(s["latitude"]),
            str(s["longitude"]),
        ]
        csv_lines.append(",".join(row))
    (DATA_DIR / "tx_states.csv").write_text(
        "\n".join(csv_lines) + "\n", encoding="utf-8"
    )

    (DATA_DIR / "adsb_frame_bits_multi.txt").write_text(
        "\n".join(adsb_bits_list) + "\n", encoding="ascii"
    )
    (DATA_DIR / "tx_bits_multi.txt").write_text(
        "\n".join(tx_bits_list) + "\n", encoding="ascii"
    )

    tx_samples_multi.astype(np.float32).tofile(
        str(DATA_DIR / "tx_samples_multi.dat")
    )


# ---------------------------------------------------------------------------
# 12. single-frame waveform plot
# ---------------------------------------------------------------------------
def plot_waveform(tx_samples, path=None):
    """Time-domain PPM waveform -> figures/tx_waveform.png."""
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


# ---------------------------------------------------------------------------
# 13. single-frame spectrum plot
# ---------------------------------------------------------------------------
def plot_spectrum(tx_samples, sample_rate=SAMPLE_RATE, path=None):
    """Single-sided magnitude spectrum of the baseband signal."""
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    if path is None:
        path = FIG_DIR / "tx_spectrum.png"
    fs = sample_rate

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
# 14. 2D aircraft trajectory plot
# ---------------------------------------------------------------------------
def plot_aircraft_trajectory(states, path=None):
    """Plot longitude vs latitude with per-frame index labels."""
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    if path is None:
        path = FIG_DIR / "aircraft_trajectory.png"

    lons = [s["longitude"] for s in states]
    lats = [s["latitude"] for s in states]

    fig, ax = plt.subplots(figsize=(10, 8))
    ax.plot(lons, lats, "-o", markersize=5, linewidth=1.5)
    for i, s in enumerate(states):
        ax.annotate(
            str(i),
            (s["longitude"], s["latitude"]),
            textcoords="offset points",
            xytext=(5, 5),
            fontsize=8,
        )
    # mark start / end
    ax.plot(lons[0], lats[0], "s", color="green", markersize=10, label="start")
    ax.plot(lons[-1], lats[-1], "s", color="red", markersize=10, label="end")
    ax.set_xlabel("Longitude (deg)")
    ax.set_ylabel("Latitude (deg)")
    ax.set_title("Dynamic aircraft trajectory (ADS-B virtual aircraft)")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(str(path), dpi=150)
    plt.close(fig)
    return str(path)


# ---------------------------------------------------------------------------
# 15. altitude / speed / heading vs frame plot
# ---------------------------------------------------------------------------
def plot_altitude_speed_heading(states, path=None):
    """Three-panel plot of altitude, speed and heading vs frame index."""
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    if path is None:
        path = FIG_DIR / "altitude_speed_heading.png"

    frames = list(range(len(states)))
    alt = [s["altitude"] for s in states]
    spd = [s["speed"] for s in states]
    hdg = [s["heading"] for s in states]

    fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
    axes[0].plot(frames, alt, "-o", color="tab:blue")
    axes[0].set_ylabel("Altitude (ft)")
    axes[0].set_title("Aircraft state vs frame index")
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(frames, spd, "-s", color="tab:orange")
    axes[1].set_ylabel("Speed (kt)")
    axes[1].grid(True, alpha=0.3)

    axes[2].plot(frames, hdg, "-^", color="tab:green")
    axes[2].set_ylabel("Heading (deg)")
    axes[2].set_xlabel("Frame index")
    axes[2].grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(str(path), dpi=150)
    plt.close(fig)
    return str(path)


# ---------------------------------------------------------------------------
# 16. multi-frame waveform plot
# ---------------------------------------------------------------------------
def plot_multi_waveform(tx_samples_multi, num_frames, path=None):
    """Plot the first few frames of the multi-frame PPM waveform."""
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    if path is None:
        path = FIG_DIR / "tx_waveform_multi.png"

    show = min(num_frames, 3)
    seg_len = show * TX_SAMPLES_TOTAL
    seg = tx_samples_multi[:seg_len]
    t_us = np.arange(seg.size) / SAMPLE_RATE * 1e6

    fig, ax = plt.subplots(figsize=(12, 4))
    ax.step(t_us, seg, where="post", linewidth=1.0)
    for k in range(show + 1):
        x = k * TX_SAMPLES_TOTAL / SAMPLE_RATE * 1e6
        ax.axvline(x, color="red", linestyle="--", alpha=0.4)
    ax.set_xlabel("Time (us)")
    ax.set_ylabel("Amplitude")
    ax.set_title(
        f"Multi-frame PPM baseband waveform "
        f"(first {show} of {num_frames} frames, 256 samples/frame)"
    )
    ax.set_ylim(-0.2, 1.2)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(str(path), dpi=150)
    plt.close(fig)
    return str(path)


# ---------------------------------------------------------------------------
# 17. CLI entry points
# ---------------------------------------------------------------------------
def _run_single():
    print("=== ADS-B transmitter (member 3) : SINGLE mode ===")
    state = generate_virtual_aircraft_state()
    print("virtual state:", state)

    adsb_bits, tx_bits, tx_samples = generate_single_frame_transmission(state)
    print(f"ADS-B frame  : len={len(adsb_bits)} -> {adsb_bits}")
    print(f"tx bit stream: len={len(tx_bits)} -> {tx_bits}")
    print(
        f"PPM samples  : len={tx_samples.size}, "
        f"dtype={tx_samples.dtype}, range=[{tx_samples.min()}, {tx_samples.max()}]"
    )

    save_single_outputs(state, adsb_bits, tx_bits, tx_samples)
    wf = plot_waveform(tx_samples)
    sp = plot_spectrum(tx_samples)
    print("saved waveform:", wf)
    print("saved spectrum:", sp)

    # hard-rule self-checks
    assert len(adsb_bits) == ADSB_FRAME_BITS
    assert len(tx_bits) == TX_BITS_TOTAL
    assert tx_samples.size == TX_SAMPLES_TOTAL
    assert tx_samples.dtype == np.float32
    assert tx_bits[: len(PREAMBLE)] == PREAMBLE
    print("self-check: all hard rules satisfied.")
    return 0


def _run_multi(config_path):
    print("=== ADS-B transmitter (member 3) : MULTI mode ===")
    config = load_scenario_config(config_path)
    print(
        "scenario    : num_frames={num_frames}, dt={frame_interval_s}s, "
        "icao={icao} ({hex_icao})".format(
            hex_icao=hex(config["icao"]), **config
        )
    )

    states = generate_aircraft_trajectory(config)
    print(f"trajectory   : generated {len(states)} states")
    print(
        f"  first state lat={states[0]['latitude']:.6f} "
        f"lon={states[0]['longitude']:.6f} alt={states[0]['altitude']:.1f}ft"
    )
    print(
        f"  last  state lat={states[-1]['latitude']:.6f} "
        f"lon={states[-1]['longitude']:.6f} alt={states[-1]['altitude']:.1f}ft"
    )

    adsb_bits_list, tx_bits_list, tx_samples_multi = (
        generate_multi_frame_transmission(states)
    )
    print(
        f"frames       : {len(tx_bits_list)} x {TX_BITS_TOTAL} bits, "
        f"samples={tx_samples_multi.size} ({tx_samples_multi.dtype})"
    )

    save_multi_outputs(
        states, adsb_bits_list, tx_bits_list, tx_samples_multi
    )
    # also refresh the single-frame member-4 interface with frame 0
    save_single_outputs(
        states[0],
        adsb_bits_list[0],
        tx_bits_list[0],
        tx_samples_multi[:TX_SAMPLES_TOTAL],
    )
    print("saved multi outputs + single-frame (frame 0) interface.")

    traj = plot_aircraft_trajectory(states)
    ash = plot_altitude_speed_heading(states)
    mwf = plot_multi_waveform(tx_samples_multi, len(states))
    print("saved trajectory plot :", traj)
    print("saved state plots     :", ash)
    print("saved multi waveform  :", mwf)

    # hard-rule self-checks
    assert len(tx_bits_list) == len(states)
    assert all(len(b) == TX_BITS_TOTAL for b in tx_bits_list)
    assert all(len(a) == ADSB_FRAME_BITS for a in adsb_bits_list)
    assert all(b[: len(PREAMBLE)] == PREAMBLE for b in tx_bits_list)
    assert tx_samples_multi.dtype == np.float32
    assert tx_samples_multi.size == len(states) * TX_SAMPLES_TOTAL
    print(
        f"self-check: {len(states)} frames, "
        f"{tx_samples_multi.size} samples total. all hard rules satisfied."
    )
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="ADS-B 1090ES baseband transmitter (member 3)"
    )
    parser.add_argument(
        "--mode",
        choices=["single", "multi"],
        default="single",
        help="single = one virtual frame; multi = physics-based trajectory",
    )
    parser.add_argument(
        "--config",
        default="config/aircraft_scenario.json",
        help="path to scenario JSON (used by --mode multi)",
    )
    args = parser.parse_args(argv)

    ensure_dirs()

    if args.mode == "single":
        return _run_single()
    return _run_multi(args.config)


if __name__ == "__main__":
    sys.exit(main())
