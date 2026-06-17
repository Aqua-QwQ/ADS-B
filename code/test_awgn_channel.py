# -*- coding: utf-8 -*-
"""Tests for the one-command ADS-B experiment pipeline helpers."""

import tempfile
import unittest
from pathlib import Path

import numpy as np

import awgn_channel


class AwgnChannelTests(unittest.TestCase):
    def test_batch_channel_writes_one_float32_file_per_snr(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tx_path = root / "tx_samples.dat"
            out_dir = root / "data"
            tx = np.array([1.0, 0.0, 0.0, 1.0], dtype=np.float32)
            tx.tofile(str(tx_path))

            results = awgn_channel.generate_awgn_files(
                tx_path=tx_path,
                output_dir=out_dir,
                snr_values=[20, 5],
                seed=123,
                plot=False,
            )

            self.assertEqual([r["snr_db"] for r in results], [20, 5])
            for snr in (20, 5):
                rx_path = out_dir / f"rx_samples_snr{snr}.dat"
                self.assertTrue(rx_path.exists())
                rx = np.fromfile(str(rx_path), dtype=np.float32)
                self.assertEqual(rx.dtype, np.float32)
                self.assertEqual(rx.shape, tx.shape)
                self.assertFalse(np.array_equal(rx, tx))

    def test_zero_signal_uses_positive_noise_power(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tx_path = root / "tx_samples.dat"
            tx = np.zeros(8, dtype=np.float32)
            tx.tofile(str(tx_path))

            results = awgn_channel.generate_awgn_files(
                tx_path=tx_path,
                output_dir=root,
                snr_values=[10],
                seed=1,
                plot=False,
            )

            self.assertGreater(results[0]["noise_power"], 0.0)
            rx = np.fromfile(str(root / "rx_samples_snr10.dat"), dtype=np.float32)
            self.assertEqual(rx.shape, tx.shape)


if __name__ == "__main__":
    unittest.main(verbosity=2)
