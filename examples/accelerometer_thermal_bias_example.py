# Copyright 2026, Aurélien ROY, <lafigure@proton.me>
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

"""A synthetic IMU-style dataset: Z-axis accelerometer reading corrupted by
a temperature-dependent bias, driven by a heater's PWM duty cycle -- the
kind of thing you'd see characterizing a real accelerometer's thermal
sensitivity on a hot plate.

Model
-----
``heating_pwm(t)`` drives a first-order thermal lag (time constant 10s)
toward a duty-cycle-proportional steady-state temperature, so
``temperature(t)`` ramps/settles rather than jumping. Five phases:
0% baseline, four 10s echelons (25/50/75/100%) each separated by 20s back
at 0%, then a 100s feed-forward phase (a fast ramp up, then an inverse
exponential decay down to the duty cycle that HOLDS the final temperature)
that gets the sensor to its hottest point of the run quickly and keeps it
there, and finally 60s back at 0% to cool down.

``real_accZ(t) = -9.81 * cos(tilt(t))`` -- tilt is 0 deg for almost the
whole run except one brief twitch during the 100s hold phase, so the
"real" signal is flat but for that one blip.

The modeled bias is a linear combination of the temperature rise above
ambient, its own rate of change, and the raw PWM duty cycle -- three
independent ways a real accelerometer's bias can couple to self-heating
(thermal gradient across the die, its transient, and electrical coupling
from the heater drive itself). The three terms are scaled to contribute
about equally, for a combined bias swing of roughly +-1 m/s^2.
``AccZ(t) = real_accZ(t) + bias(t)`` plus a touch of sensor noise.

All five series share one `lafigure.DataSource` (lafigure/datasource.py),
row-aligned by sample index, so brushing a rectangle on ANY of them
selects the same instants everywhere else built from it. Try it live:
toolbar -> Brush mode, then drag a rectangle over one of the PWM echelons
on the "time vs heating_pwm" plot, or over the twitch on the "time vs
tilt" plot -- the matching instants light up on "temperature vs AccZ"
too, which is exactly where the thermal-bias coupling is otherwise hard
to see on a plain time-series view.

Run (from anywhere -- this file adds the repo root to sys.path itself,
since lafigure isn't pip-installed):
    python examples/accelerometer_thermal_bias_example.py
"""
import os
import sys

import numpy as np
import pyqtgraph as pg
from pyqtgraph.Qt import QtWidgets

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lafigure
_debug_log = lafigure.enable_debug_mode()
print(f"Debug log: {_debug_log}")

AMBIENT_C = 25.0
TAU_THERMAL_S = 10.0          # first-order thermal time constant
GAIN_C_PER_PCT = 0.6          # steady-state temperature rise per % PWM
DT = 0.05                     # 20 Hz sampling


def _pwm_schedule():
    """Returns (durations, levels) for every phase, in order."""
    durations = [40, 10, 20, 10, 20, 10, 20, 10, 20, 100, 60]
    levels_direct = [0, 25, 0, 50, 0, 75, 0, 100, 0]
    # The 100s phase (index 9) gets its own waveform below, not a flat
    # level; placeholder 0 here, overwritten per-sample afterwards.
    levels = levels_direct + [0, 0]
    return durations, levels


def _build_pwm_and_tilt():
    durations, levels = _pwm_schedule()
    total = sum(durations)
    n = int(round(total / DT))
    t = np.arange(n) * DT
    pwm = np.zeros(n)
    tilt_deg = np.zeros(n)

    boundaries = np.concatenate(([0.0], np.cumsum(durations)))
    ramp_phase_idx = 9  # the "fast temperature stabilization" phase

    # Target hold temperature for the ramp phase: the hottest point of the
    # whole run (per the brief, up to 75 C), reached quickly and held.
    target_hold_c = 75.0
    pwm_hold = (target_hold_c - AMBIENT_C) / GAIN_C_PER_PCT   # steady PWM to hold it
    pwm_peak = 100.0                                          # initial feed-forward spike
    ramp_up_s = 4.0                                           # quick linear ramp to the spike
    decay_tau_s = 8.0                                         # inverse-exponential settle

    for i, lvl in enumerate(levels):
        start, end = boundaries[i], boundaries[i + 1]
        mask = (t >= start) & (t < end)
        if i == ramp_phase_idx:
            local_t = t[mask] - start
            pwm[mask] = np.where(
                local_t < ramp_up_s,
                pwm_peak * (local_t / ramp_up_s),
                pwm_hold + (pwm_peak - pwm_hold) * np.exp(-(local_t - ramp_up_s) / decay_tau_s),
            )
        else:
            pwm[mask] = lvl

    # A small tilt twitch partway through the 100s hold phase -- a brief
    # bump and release, not a step, so it reads as a real jolt.
    twitch_center = boundaries[ramp_phase_idx] + 55.0
    twitch_half_width_s = 1.5
    twitch_peak_deg = 12.0
    twitch_mask = np.abs(t - twitch_center) < (4 * twitch_half_width_s)
    tilt_deg[twitch_mask] += twitch_peak_deg * np.exp(
        -0.5 * ((t[twitch_mask] - twitch_center) / twitch_half_width_s) ** 2)

    return t, pwm, tilt_deg


def _simulate_temperature(t, pwm):
    """Euler-integrates the first-order thermal lag toward a PWM-driven
    steady-state temperature; returns (temperature, dT/dt)."""
    n = len(t)
    temp = np.empty(n)
    temp[0] = AMBIENT_C
    temp_ss = AMBIENT_C + GAIN_C_PER_PCT * pwm
    for i in range(1, n):
        temp[i] = temp[i - 1] + (temp_ss[i - 1] - temp[i - 1]) / TAU_THERMAL_S * DT
    dtemp_dt = np.gradient(temp, t)
    return temp, dtemp_dt


def _calibrate_bias_coeffs(rng, delta_temp, dtemp_dt, pwm, target_amplitude=0.33):
    """Scales each regressor so its own contribution peaks at about
    `target_amplitude`, with a touch of randomness so the three terms are
    'about the same' rather than identical."""
    scales = rng.uniform(0.8, 1.2, size=3)
    coeff_a = target_amplitude * scales[0] / np.max(np.abs(delta_temp))
    coeff_b = target_amplitude * scales[1] / np.max(np.abs(dtemp_dt))
    coeff_c = target_amplitude * scales[2] / np.max(np.abs(pwm))
    return coeff_a, coeff_b, coeff_c


def build_dataset(seed=42):
    rng = np.random.default_rng(seed)

    t, pwm, tilt_deg = _build_pwm_and_tilt()
    temp, dtemp_dt = _simulate_temperature(t, pwm)

    tilt_rad = np.deg2rad(tilt_deg)
    real_accz = -9.81 * np.cos(tilt_rad)

    delta_temp = temp - AMBIENT_C
    cst_randA, cst_randB, cst_randC = _calibrate_bias_coeffs(rng, delta_temp, dtemp_dt, pwm)
    bias = cst_randA * delta_temp + cst_randB * dtemp_dt + cst_randC * pwm

    accz = real_accz + bias + rng.normal(scale=0.01, size=t.size)

    return lafigure.DataSource({
        'time': t, 'accz': accz, 'temp': temp, 'pwm': pwm, 'tilt_deg': tilt_deg,
    })


def main():
    app = QtWidgets.QApplication(sys.argv)
    source = build_dataset()

    fig = lafigure.LaFigure(empty=True)
    fig.setWindowTitle("LaFigure example -- accelerometer thermal bias")

    ax_accz = fig.subplot(0, 0, title="Time vs AccZ")
    ax_accz.plot(source, x='time', y='accz', name="AccZ", pen=pg.mkPen((214, 39, 40), width=1))
    ax_accz.plot_item.setLabel('bottom', 'time', units='s')
    ax_accz.plot_item.setLabel('left', 'AccZ', units='m/s^2')

    ax_temp = fig.subplot(0, 1, title="Time vs Temperature")
    ax_temp.plot(source, x='time', y='temp', name="T", pen=pg.mkPen((255, 127, 14), width=1))
    ax_temp.plot_item.setLabel('bottom', 'time', units='s')
    ax_temp.plot_item.setLabel('left', 'temperature', units='degC')

    ax_pwm = fig.subplot(1, 0, title="Time vs heating_pwm (brush me)")
    ax_pwm.plot(source, x='time', y='pwm', name="PWM", pen=pg.mkPen((31, 119, 180), width=1))
    ax_pwm.plot_item.setLabel('bottom', 'time', units='s')
    ax_pwm.plot_item.setLabel('left', 'heating PWM', units='%')

    ax_tilt = fig.subplot(1, 1, title="Time vs tilt (brush me)")
    ax_tilt.plot(source, x='time', y='tilt_deg', name="tilt", pen=pg.mkPen((44, 160, 44), width=1))
    ax_tilt.plot_item.setLabel('bottom', 'time', units='s')
    ax_tilt.plot_item.setLabel('left', 'tilt', units='deg')

    ax_coupling = fig.subplot(2, 0, colspan=2, title="Temperature vs AccZ -- thermal bias coupling")
    ax_coupling.scatter(source, x='temp', y='accz', name="samples", size=3,
                         symbolBrush=pg.mkBrush(120, 120, 120, 120), symbolPen=None)
    ax_coupling.plot_item.setLabel('bottom', 'temperature', units='degC')
    ax_coupling.plot_item.setLabel('left', 'AccZ', units='m/s^2')

    fig.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
