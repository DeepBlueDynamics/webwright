#!/usr/bin/env python
"""Test the boot splash"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from lib.boot import show_boot_splash

if __name__ == "__main__":
    print("Testing boot splash:\n")
    show_boot_splash()
    print("\n✓ Boot splash complete!")
