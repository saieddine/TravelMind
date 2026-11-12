"""Run all current team functions and Sasha regressions with outbound sockets blocked."""
import importlib
import inspect
import socket
import unittest
from unittest.mock import patch


def suite():
    result = unittest.TestSuite()
    for name in ("test_destination_agent", "test_itinerary"):
        module = importlib.import_module(name)
        for function_name, function in inspect.getmembers(module, inspect.isfunction):
            if function_name.startswith("test_"):
                result.addTest(unittest.FunctionTestCase(function, description=name + "." + function_name))
    result.addTests(unittest.defaultTestLoader.discover("tests_sasha", top_level_dir="."))
    return result


def blocked(*args, **kwargs):
    raise AssertionError("External network forbidden in offline tests")

if __name__ == "__main__":
    with patch("socket.socket.connect", blocked), patch("socket.socket.connect_ex", blocked), patch("socket.create_connection", blocked):
        result = unittest.TextTestRunner(verbosity=2).run(suite())
    raise SystemExit(not result.wasSuccessful())
