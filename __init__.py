# SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: LicenseRef-NvidiaProprietary

try:
    from .extension import *
except (ImportError, ModuleNotFoundError):
    try:
        from extension import *
    except (ImportError, ModuleNotFoundError):
        pass
