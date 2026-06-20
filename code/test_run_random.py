# -*- coding: utf-8 -*-
"""Tests for the random-state one-command runner."""

import unittest

import run_random


class RunRandomTests(unittest.TestCase):
    def test_random_state_is_reproducible_with_seed(self):
        first = run_random.generate_random_aircraft_state(seed=1234)
        second = run_random.generate_random_aircraft_state(seed=1234)
        other = run_random.generate_random_aircraft_state(seed=4321)

        self.assertEqual(first, second)
        self.assertNotEqual(first["icao"], other["icao"])
        self.assertEqual(first["df"], 17)
        self.assertEqual(first["ca"], 5)
        self.assertEqual(first["type_code"], 19)
        self.assertGreaterEqual(first["altitude"], 0.0)
        self.assertLessEqual(first["altitude"], 102375.0)
        self.assertGreaterEqual(first["speed"], 0.0)
        self.assertLessEqual(first["speed"], 1023.0)
        self.assertGreaterEqual(first["heading"], 0.0)
        self.assertLess(first["heading"], 360.0)
        self.assertGreaterEqual(first["latitude"], -90.0)
        self.assertLessEqual(first["latitude"], 90.0)
        self.assertGreaterEqual(first["longitude"], -180.0)
        self.assertLessEqual(first["longitude"], 180.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
