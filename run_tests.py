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

"""Headless test runner, no pytest needed. From the repo root:

    QT_QPA_PLATFORM=offscreen python run_tests.py              (bash)
    $env:QT_QPA_PLATFORM='offscreen'; python run_tests.py      (PowerShell)

Imports every tests/test_*.py and runs each top-level test_* function in
it, in file order then definition order. Optional arguments keep only the
tests whose "module.function" name contains one of them, e.g.
`python run_tests.py layout test_fit_`. Prints "ALL OK" only if every
test that ran passed; exits non-zero otherwise.
"""
import glob
import importlib
import inspect
import os
import sys
import time
import traceback

from pyqtgraph.Qt import QtWidgets

ROOT = os.path.dirname(os.path.abspath(__file__))


def collect():
    sys.path.insert(0, ROOT)
    tests = []
    for path in sorted(glob.glob(os.path.join(ROOT, 'tests', 'test_*.py'))):
        mod_name = os.path.splitext(os.path.basename(path))[0]
        module = importlib.import_module(f'tests.{mod_name}')
        for name, obj in vars(module).items():  # definition order
            if (name.startswith('test_') and inspect.isfunction(obj)
                    and obj.__module__ == module.__name__):
                tests.append((f'{mod_name}.{name}', obj))
    return tests


def main(filters):
    tests = collect()
    if filters:
        tests = [(n, fn) for n, fn in tests if any(f in n for f in filters)]
    from tests.helpers import app  # the one QApplication, created on import
    failures = []
    for name, fn in tests:
        start = time.perf_counter()
        try:
            fn()
        except Exception:
            failures.append(name)
            print(f'FAIL {name}')
            traceback.print_exc()
        else:
            print(f'ok   {name} ({time.perf_counter() - start:.2f}s)')
        app.processEvents()
        # Most tests build a LaFigure (or a FigureManager/dialog) and never
        # close it -- each one stays referenced forever by the process-wide
        # FigureRegistry (registry.py's `self.figures.append`, only removed
        # by LaFigure.closeEvent -> registry.unregister). Left unclosed
        # across the whole suite, this accumulated enough live QMainWindows/
        # native Qt resources to crash the process outright (no Python
        # traceback -- a native STATUS_STACK_BUFFER_OVERRUN on Windows,
        # reproducing deterministically ~500 tests in) once round 4 added
        # ~70 more tests on top of round 3's total. closeAllWindows() sends
        # a real close event to every top-level widget, which for a
        # LaFigure runs its closeEvent -> registry.unregister, so this is
        # cheap, safe cleanup rather than a workaround for any one test.
        QtWidgets.QApplication.closeAllWindows()
        app.processEvents()
    print(f'\n{len(tests) - len(failures)}/{len(tests)} passed')
    if failures:
        print('FAILED: ' + ', '.join(failures))
        return 1
    if not tests:
        print('no tests matched')
        return 1
    print('ALL OK')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
