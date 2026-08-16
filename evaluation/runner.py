"""Alias entry point: ``python -m evaluation.runner`` == ``python -m evaluation.cli``."""

import sys

from evaluation.cli import main

if __name__ == "__main__":
    sys.exit(main())
