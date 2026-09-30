# Copyright 2026, Aurélien ROY, <aurroy@hotmail.com>
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

"""Built-in SeriesKinds beyond 'line' (which lives in series.py itself).

Each submodule here owns one SeriesKind and calls register_series_kind()
at import time -- importing this subpackage is enough to make
ax.scatter(...)/ax.stairs(...)/ax.area(...)/ax.hist(...)/ax.bar(...)/
ax.errorbar(...)/ax.imshow(...) all reachable (see axes.py's
__getattr__/_plot_kind, which routes any name found in SERIES_KINDS with
no per-kind code there). lafigure's top-level __init__.py imports this
package (`from . import kinds`) so a plain `import lafigure` registers
all of them; a future kind package adds its module to the import list
below, not to lafigure/__init__.py."""
from . import scatter, stairs, area, hist, bar, errorbar, imshow
from . import scatter3d, line3d, surface  # 3D kinds, for axes_type='3d' subplots (view3d.py)
from . import polar, polarhistogram, piechart  # polar family (kinds/_polar_base.py)

__all__ = ["scatter", "stairs", "area", "hist", "bar", "errorbar", "imshow",
           "scatter3d", "line3d", "surface",
           "polar", "polarhistogram", "piechart"]
