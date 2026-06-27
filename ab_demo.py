"""Read-me demo: run the A/B convincer and print the kill-question verdict.
`python ab_demo.py`."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from cua.ab import compare
from cua.fixtures.form_fill import DEFAULT_ORACLE, build_capture

print(compare(build_capture(), DEFAULT_ORACLE).render())
