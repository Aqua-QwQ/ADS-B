# -*- coding: utf-8 -*-
"""Pure Python AWGN channel for the ADS-B baseband experiment."""

import argparse
import os
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/adsb_pipeline_cache/matplotlib")
os.environ.setdefault("XDG_CACHE_HOME", "/tmp/adsb_pipeline_cache/xdg")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np


CODE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CODE_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
FIG_DIR = PROJECT_ROOT / "figures"
DEFAULT_SNR_VALUES = [20, 10, 5, 0]
SAMPLE_RATE = 2e6


def read_float32_samples(path):
    samples = np.fromfile(str(path), dtype=np.float32)
    if samples.size == 0:
        raise ValueError(f"sample file is empty: {path}")
    return samples


def add_awgn(samples, snr_db, rng):
    samples = np.asarray(samples, dtype=np.float32)
    signal_power = float(np.mean(samples.astype(np.float64) ** 2))
    if signal_power <= 0.0:
        signal_power = 1.0
    snr_linear = 10.0 ** (float(snr_db) / 10.0)
    noise_power = signal_power / snr_linear
    noise = rng.normal(0.0, np.sqrt(noise_power), size=samples.shape)
    rx_samples = samples.astype(np.float64) + noise
    return rx_samples.astype(np.float32), signal_power, noise_power


def plot_rx_waveform(samples, snr_db, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    t_us = np.arange(samples.size) / SAMPLE_RATE * 1e6
    fig, ax = plt.subplots(figsize=(12, 3))
    ax.plot(t_us, samples, linewidth=1.0)
    ax.set_xlabel("Time (us)")
    ax.set_ylabel("Amplitude")
    ax.set_title(f"Received waveform after AWGN channel (SNR={snr_db} dB)")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(str(output_path), dpi=150)
    plt.close(fig)


def plot_rx_spectrum(samples, snr_db, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    x = samples.astype(np.float64) - np.mean(samples)
    spectrum = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(x.size, d=1.0 / SAMPLE_RATE)
    mag = np.abs(spectrum) / x.size * 2.0

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(freqs / 1e6, mag, linewidth=1.0)
    ax.set_xlabel("Frequency (MHz)")
    ax.set_ylabel("Magnitude")
    ax.set_title(f"Received spectrum after AWGN channel (SNR={snr_db} dB)")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(str(output_path), dpi=150)
    plt.close(fig)


def generate_awgn_files(
    tx_path=None,
    output_dir=None,
    snr_values=None,
    seed=2026,
    plot=True,
    figure_dir=None,
):
    tx_path = Path(tx_path) if tx_path is not None else DATA_DIR / "tx_samples.dat"
    output_dir = Path(output_dir) if output_dir is not None else DATA_DIR
    figure_dir = Path(figure_dir) if figure_dir is not None else FIG_DIR
    snr_values = DEFAULT_SNR_VALUES if snr_values is None else list(snr_values)

    tx_samples = read_float32_samples(tx_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    results = []
    for snr_db in snr_values:
        rx_samples, signal_power, noise_power = add_awgn(tx_samples, snr_db, rng)
        rx_path = output_dir / f"rx_samples_snr{snr_db}.dat"
        rx_samples.tofile(str(rx_path))

        if plot:
            plot_rx_waveform(
                rx_samples,
                snr_db,
                figure_dir / f"rx_waveform_snr{snr_db}.png",
            )
            plot_rx_spectrum(
                rx_samples,
                snr_db,
                figure_dir / f"rx_spectrum_snr{snr_db}.png",
            )

        results.append(
            {
                "snr_db": snr_db,
                "rx_path": str(rx_path),
                "num_samples": int(rx_samples.size),
                "signal_power": signal_power,
                "noise_power": noise_power,
            }
        )
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate AWGN channel outputs for ADS-B baseband samples."
    )
    parser.add_argument(
        "--tx",
        default=str(DATA_DIR / "tx_samples.dat"),
        help="input float32 tx sample file",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DATA_DIR),
        help="directory for rx_samples_snr*.dat",
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

    results = generate_awgn_files(
        tx_path=args.tx,
        output_dir=args.output_dir,
        snr_values=args.snr,
        seed=args.seed,
        plot=not args.no_plots,
    )
    print("=== ADS-B AWGN channel ===")
    for r in results:
        print(
            "SNR={snr_db:>2} dB -> {rx_path} "
            "(samples={num_samples}, signal_power={signal_power:.6f}, "
            "noise_power={noise_power:.6f})".format(**r)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
