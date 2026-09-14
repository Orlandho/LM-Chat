# SPDX-FileCopyrightText: Copyright (c) 2026 Orlando Dorival. All rights reserved.
# SPDX-License-Identifier: MIT

"""
LM-Chat™: Autonomous Spatial AI Assistant & Neural Copilot for NVIDIA Omniverse.
"""

__version__ = "1.1.0"

try:
    from .extension import *
except (ImportError, ModuleNotFoundError):
    try:
        from extension import *
    except (ImportError, ModuleNotFoundError):
        pass
