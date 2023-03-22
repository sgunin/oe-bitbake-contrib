# Copyright (C) 2023 Alberto Pianon <pianon@array.eu>
#
# SPDX-License-Identifier: GPL-2.0-only
#

class TraceException(Exception):
    pass

try:
    from .unpack import TraceUnpack
except (ModuleNotFoundError, ImportError):
    # fallback to base class (which implements the process necessary to trace
    # upstream data but does not actually collect any data)
    from .unpack_base import TraceUnpackBase as TraceUnpack

