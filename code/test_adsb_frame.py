# -*- coding: utf-8 -*-
"""Automated tests for the member 2 ADS-B frame protocol layer."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from adsb_frame import (  # noqa: E402
    bits_to_string,
    generate_adsb_frame,
    generate_crc24,
    parse_frame_fields,
    string_to_bits,
)


TEST_STATE = {
    "df": 17,
    "ca": 5,
    "icao": 0xABCDEF,
    "type_code": 19,
    "altitude": 30000,
    "speed": 450,
    "heading": 90.0,
    "latitude": 39.9042,
    "longitude": 116.4074,
}


def circular_error_degrees(actual, expected):
    """Return the shortest angular distance between two headings."""
    return abs((actual - expected + 180.0) % 360.0 - 180.0)


class AdsbFrameTests(unittest.TestCase):
    def test_standard_frame_is_112_bits(self):
        frame = generate_adsb_frame(TEST_STATE)
        self.assertEqual(len(frame), 112)
        self.assertTrue(all(bit in (0, 1) for bit in frame))

    def test_round_trip_fields(self):
        parsed = parse_frame_fields(generate_adsb_frame(TEST_STATE))
        for field in ("df", "ca", "icao", "type_code", "altitude", "speed"):
            self.assertEqual(parsed[field], TEST_STATE[field])

    def test_quantization_errors(self):
        parsed = parse_frame_fields(generate_adsb_frame(TEST_STATE))
        self.assertLessEqual(circular_error_degrees(parsed["heading"], TEST_STATE["heading"]), 360.0 / 512.0 / 2.0 + 0.01)
        self.assertLessEqual(abs(parsed["latitude"] - TEST_STATE["latitude"]), 180.0 / 1023.0 / 2.0 + 0.01)
        self.assertLessEqual(abs(parsed["longitude"] - TEST_STATE["longitude"]), 360.0 / 1023.0 / 2.0 + 0.01)

    def test_heading_wraps_without_returning_360(self):
        state = dict(TEST_STATE, heading=359.9)
        parsed = parse_frame_fields(generate_adsb_frame(state))
        self.assertGreaterEqual(parsed["heading"], 0.0)
        self.assertLess(parsed["heading"], 360.0)
        self.assertLessEqual(circular_error_degrees(parsed["heading"], state["heading"]), 360.0 / 512.0 / 2.0 + 0.01)

    def test_crc_accepts_valid_frame(self):
        self.assertTrue(parse_frame_fields(generate_adsb_frame(TEST_STATE))["crc_ok"])

    def test_crc_rejects_every_single_bit_error(self):
        frame = generate_adsb_frame(TEST_STATE)
        for index in range(112):
            corrupted = list(frame)
            corrupted[index] ^= 1
            with self.subTest(index=index):
                self.assertFalse(parse_frame_fields(corrupted)["crc_ok"])

    def test_crc_matches_known_valid_adsb_frame(self):
        known = string_to_bits(bin(int("8D40621D58C382D690C8AC2863A7", 16))[2:].zfill(112))
        self.assertEqual(generate_crc24(known[:88]), known[88:])
        self.assertTrue(parse_frame_fields(known)["crc_ok"])

    def test_out_of_range_inputs_raise_value_error(self):
        invalid_values = {
            "altitude": 200000,
            "speed": 1024,
            "heading": 360.0,
            "latitude": 95.0,
            "longitude": 181.0,
        }
        for field, value in invalid_values.items():
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    generate_adsb_frame(dict(TEST_STATE, **{field: value}))

    def test_invalid_frame_length_raises_value_error(self):
        with self.assertRaises(ValueError):
            parse_frame_fields([1, 0, 1])

    def test_file_round_trip(self):
        frame = generate_adsb_frame(TEST_STATE)
        path = Path(__file__).with_name(".adsb_frame_roundtrip_test.txt")
        try:
            path.write_text(bits_to_string(frame) + "\n", encoding="ascii")
            self.assertEqual(string_to_bits(path.read_text(encoding="ascii").strip()), frame)
        finally:
            path.unlink(missing_ok=True)

    def test_member_3_to_member_5_noiseless_interface(self):
        preamble = string_to_bits("1010000101000000")
        frame = generate_adsb_frame(TEST_STATE)
        tx_bits = preamble + frame
        samples = [sample for bit in tx_bits for sample in ([1, 0] if bit else [0, 1])]
        recovered = [1 if samples[i] > samples[i + 1] else 0 for i in range(0, len(samples), 2)]
        self.assertEqual(len(tx_bits), 128)
        self.assertEqual(len(samples), 256)
        self.assertEqual(recovered, tx_bits)
        self.assertTrue(parse_frame_fields(recovered[16:])["crc_ok"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
