#!/usr/bin/env python3
"""
RetroBat ROM Browser
A Calibre-inspired ROM library manager for RetroBat/EmulationStation collections.
"""

import sys
import os

# Ensure the package is on the path when run directly
sys.path.insert(0, os.path.dirname(__file__))

from retrobat_browser.app import main

if __name__ == "__main__":
    main()
