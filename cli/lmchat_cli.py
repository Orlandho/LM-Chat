# -*- coding: utf-8 -*-
"""
LM-Chat™ Official CLI Harness Entrypoint.

Commercial trademark: LM-Chat™
NVIDIA Omniverse Autonomous Spatial AI Suite.
"""

import sys
import os
import asyncio

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cli.omni_harness import main, LMChatCLI, parse_arguments, BANNER

if __name__ == "__main__":
    asyncio.run(main())
