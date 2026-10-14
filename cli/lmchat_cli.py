# -*- coding: utf-8 -*-
"""
LM-Chat™ Official CLI Harness Entrypoint.

Commercial trademark: LM-Chat™
NVIDIA Omniverse Autonomous Spatial AI Suite.
"""

import sys
import os
import asyncio

# Ensure project root and extension package are in sys.path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ext_pkg_root = os.path.join(repo_root, "exts", "orlandodorival.lm_chat")
for p in [ext_pkg_root, repo_root]:
    if p not in sys.path:
        sys.path.insert(0, p)

from cli.omni_harness import main, LMChatCLI, parse_arguments, BANNER

if __name__ == "__main__":
    asyncio.run(main())
