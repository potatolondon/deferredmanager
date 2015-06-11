#!/usr/bin/env python
import unittest

from deferred_manager import tests

suite = unittest.TestLoader().loadTestsFromModule(tests)
unittest.TextTestRunner(verbosity=2).run(suite)
