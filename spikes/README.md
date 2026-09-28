# Spike WP-G: 3D offscreen render + readback ("Option A")

CLAUDE.md, Roadmap Phase 6, **Option A**: *a 3D cell is a normal grid item
that renders an offscreen GL view to an image each frame and forwards mouse
input to its camera; this keeps move/resize/select/copy/annotations
working. Prototype the readback speed live before committing.*

This spike measures that. It is standalone: nothing under `lafigure/` is
imported or changed. `gl_offscreen_readback.py` is the only code.

**Verdict: GO on a hardware GPU** (about 1 to 3 ms per 3D cell per
frame, readback included, up to 1.5 M vertices). **NO-GO for large data on
software GL** (llvmpipe), but only because llvmpipe *draws* slowly. The
readback itself costs the same there. See the recommendation at the end.

## What was measured, and how

All numbers below are wall-clock times measured in this session
(2026-09-28) by running the script. None are estimated.

Environment: Windows 11, Python 3.10.0, PyQt5 / Qt 5.15.2, pyqtgraph 0.14.0,
NVIDIA GeForce RTX 4070 SUPER (driver 591.86, GL 4.6 compatibility
context), and Qt's bundled Mesa 12.0 llvmpipe (`opengl32sw.dll`, GL 3.0) for
the software rows.

### Why raw Qt GL instead of `GLViewWidget`

`pyqtgraph.opengl` needs **PyOpenGL**, which is not installed here and could
not be installed: pip fails TLS verification (`CERTIFICATE_VERIFY_FAILED`
on pypi.org, intercepted TLS). I did not disable certificate checks to get
around that. PyQt5 ships its own GL bindings, so the script reproduces the
same GPU path with them:

| `GLViewWidget` / `GLScatterPlotItem` does | the spike does |
|---|---|
| `GLScatterPlotItem.upload_vbo`: `QOpenGLBuffer` VBOs, uploaded once | same (`QOpenGLBuffer`, `StaticDraw`), position + RGBA color |
| `paint()`: shader + one `glDrawArrays(GL_POINTS)` | same (GLSL 120 shader, `glDrawArrays`) |
| `grabFramebuffer()`: render into the widget's FBO, then `glReadPixels` to `QImage` | `QOpenGLFramebufferObject` (depth attached) → `fbo.toImage()` (Qt's same `glReadPixels` + flip) |
| `viewMatrix()`, `projectionMatrix()`, `orbit()`, `pan('view-upright')`, `wheelEvent`, `mouseMoveEvent` button mapping | `Camera` class, same formulas in numpy |

The context is a `QOpenGLContext` made current on a `QOffscreenSurface`.
No window is shown for the main benchmark.

The numpy `Camera` is checked at startup against `GLViewWidget`'s literal
`QMatrix4x4.translate/rotate/frustum` recipe after a sequence of
orbit, pan and wheel moves. The largest difference is **2.6e-6**, which is
float32 rounding.

### Per frame, timed

Setup is excluded: data generation and VBO upload happen once and are
reported separately (≈50 ms for 1 M points). There are 3 warm-up frames,
then 60 timed frames. Before each frame, the camera is fed a synthetic
left-button drag (`Camera.drag(dx, dy, 'left')`, i.e. `orbit(-dx, dy)`):
one full turn over the 60 frames, plus a small elevation wobble. So every
frame is a new view. Each frame has three steps:

1. **render**: clear, draw, `glFinish()` (forces the GPU work into this
   bucket),
2. **readback**: `fbo.toImage()` → `QImage`,
3. **toPixmap**: `QPixmap.fromImage()`. This is what a grid item would
   paint. The pixmap is then discarded.

Point size is 4 px. The scatter is a Gaussian cloud: dense in the center,
so a lot of overdraw. The surface is a 500×500 height field drawn as
non-indexed triangles (1,494,006 vertices).

## Results

### Hardware GPU (NVIDIA RTX 4070 SUPER), median of 60 frames, ms

| scene | size | render+glFinish | readback (toImage) | QPixmap.fromImage | **total** | total p95 | max fps |
|---|---|---:|---:|---:|---:|---:|---:|
| scatter 10,000 pts | 800x600 | 0.12 | 0.54 | 0.24 | **0.90** | 1.25 | 1106 |
| scatter 10,000 pts | 1600x1000 | 0.15 | 1.40 | 0.71 | **2.27** | 2.71 | 440 |
| scatter 100,000 pts | 800x600 | 0.15 | 0.54 | 0.23 | **0.96** | 1.33 | 1045 |
| scatter 100,000 pts | 1600x1000 | 0.23 | 1.45 | 0.73 | **2.44** | 2.80 | 410 |
| scatter 1,000,000 pts | 800x600 | 0.26 | 0.52 | 0.22 | **1.01** | 1.49 | 994 |
| scatter 1,000,000 pts | 1600x1000 | 0.32 | 1.31 | 0.68 | **2.35** | 2.67 | 426 |
| surface 500x500 (1,494,006 tri verts) | 800x600 | 0.21 | 0.53 | 0.23 | **0.97** | 1.44 | 1027 |
| surface 500x500 (1,494,006 tri verts) | 1600x1000 | 0.29 | 1.36 | 0.70 | **2.40** | 2.91 | 416 |

On a real GPU the cost depends on **pixel count, not data size**.
Readback plus pixmap conversion is 70–95% of each frame and grows with the
framebuffer (about 0.8 ms at 0.48 MPx, about 2.1 ms at 1.6 MPx). Going from
10 k to 1 M points adds about 0.15 ms.

### Inside a real LaFigure-like window (hardware GPU)

This is Option A as it would actually run. The window is a 1600×1000
`pg.GraphicsLayoutWidget` created with `useOpenGL=True`, as `lafigure`
sets it, so its viewport is a `QOpenGLWidget` with its **own** GL context.
It is shown off-screen with `WA_DontShowOnScreen`. It holds 2 ordinary
PlotItems (100 k-point curves) and K 3D cells. Each 3D cell is a plain
`pg.GraphicsWidget` in the grid whose `paint()` draws the read-back pixmap.

One frame does the following for every 3D cell: switch to the offscreen
context, orbit that cell's camera, render at the cell's current size, read
back, and convert to a pixmap. Then it runs a **synchronous
`viewport().repaint()`** of the whole window. Each cell holds 1,000,000
points.

| 3D cells | cell size | **ms/frame** | p95 | max fps | 3D pixels composited |
|---:|---|---:|---:|---:|---|
| 1 | 705x471 | **2.79** | 3.18 | 359 | 15324/20592 sampled px lit |
| 4 | 788x365 | **6.81** | 7.81 | 147 | 13901/17836 sampled px lit |

Last column: `win.grab()` was sampled inside the first 3D cell after the
run, and most samples are lit (the background is black). So the pixmaps
really are composited alongside the 2D plots, even though the GL context
switches every frame. I also checked the saved grab (`--save-png`) by eye:
two sine plots on top and four orbiting point clouds below, all rendered
correctly.

### Software GL (Qt's bundled Mesa llvmpipe, `--software`), ms

| scene | size | render+glFinish | readback (toImage) | QPixmap.fromImage | **total** | total p95 | max fps |
|---|---|---:|---:|---:|---:|---:|---:|
| scatter 10,000 pts | 800x600 | 2.12 | 0.48 | 0.25 | **2.87** | 3.31 | 348 |
| scatter 10,000 pts | 1600x1000 | 2.47 | 1.49 | 0.85 | **4.82** | 5.74 | 207 |
| scatter 100,000 pts | 800x600 | 17.36 | 0.48 | 0.27 | **18.11** | 19.58 | 55 |
| scatter 100,000 pts | 1600x1000 | 20.56 | 1.66 | 0.95 | **23.29** | 24.80 | 43 |
| scatter 1,000,000 pts | 800x600 | 196.36 | 0.55 | 0.30 | **197.21** | 205.77 | 5 |
| scatter 1,000,000 pts | 1600x1000 | 154.98 | 1.46 | 0.88 | **157.39** | 163.81 | 6 |
| surface 500x500 (1,494,006 tri verts) | 800x600 | 74.16 | 0.47 | 0.26 | **74.96** | 90.84 | 13 |
| surface 500x500 (1,494,006 tri verts) | 1600x1000 | 87.23 | 1.49 | 0.90 | **89.61** | 117.12 | 11 |
| in-scene, 1 cell × 1 M pts | 705x471 | | | | **199.14** | 251.42 | 5 |
| in-scene, 4 cells × 1 M pts | 788x365 | | | | **744.46** | 794.77 | 1 |

On llvmpipe, **drawing** dominates: it scales with vertex count, about
0.2 ms per 1 k points. Readback and pixmap conversion cost the same as on
the GPU. `QT_OPENGL=software` also moves the `useOpenGL=True` viewport onto
llvmpipe, so the in-scene rows are "the whole app in software GL".

### Brushing primitive: numpy projection, 1,000,000 points

This is for the roadmap bullet "brushing via camera-matrix projection in
numpy → rows". The same MVP matrix the renderer uploads is applied to
DataSource-like float64 columns `x, y, z`. Only the x, y, w rows of the
MVP are used, because depth is not needed for a rectangle brush. It runs
on the CPU, so the GPU does not matter. Numbers are medians of 20; they
varied between 29 and 44 ms across runs of the script.

| step | median ms (HW run) | median ms (SW run) |
|---|---:|---:|
| project to screen | 29.49 | 31.59 |
| project + rect test → row indices (≈376 k rows hit) | 32.96 | 33.32 |
| **rect test only, on screen coords cached at drag start** | **1.89** | **1.34** |
| project only, float32 packed `(N,3) @ 3×4` | 11.87 | 11.30 |

The camera does not move while the user drags a brush rectangle. So a
brush should project **once at mouse press** (about 30 ms, or 12 ms from
float32 columns) and then run only the rect test on each move (about 2 ms).
Re-projecting on every move event (about 33 ms) would feel laggy at 1 M
points.

### Render / projection consistency after mouse-style camera moves

This validates both "forwards mouse input to its camera" and the brush
math against real pixels. The test scene is a 4×4×4 lattice of 5-px
points at 800×600. The camera goes through the same calls
`GLViewWidget.mouseMoveEvent`/`wheelEvent` would make: a left drag (orbit)
of (120, −40) px in 10 steps, a wheel of +240 (dolly), and a middle drag
(pan) of (60, 25) px. After each move the scene is rendered and read back,
and every point's numpy projection is checked for a lit pixel:

```
initial                          64/64 projected points land on lit pixels
left-drag orbit (120, -40) px    64/64 ..., max on-screen move 282.8 px
wheel +240 (dolly in)            64/64 ..., max on-screen move 67.4 px
middle-drag pan (60, 25) px      64/64 ..., max on-screen move 97.1 px
-> CONSISTENT
```

This holds identically on the GPU and on llvmpipe. The camera API is
driven by direct calls, not real `QMouseEvent`s, as the package allowed.
Mapping a grid item's `mouseDragEvent` delta onto `Camera.drag()` is a
one-liner, but it is not exercised here.

## Headless / offscreen findings

- **`QT_QPA_PLATFORM=offscreen` gives no OpenGL at all on Windows / Qt
  5.15**: `QOpenGLContext.create()` returns False, with or without
  `QT_OPENGL=software`. The same goes for `minimal`. The script detects
  this and exits with code 2 and an explanation; it does not crash. The
  LaFigure test suite runs under `offscreen` with `useOpenGL=False`, so
  **a future 3D cell cannot be rendered in the existing headless test
  setup on Windows**. Its tests would need either a fallback (e.g. paint a
  placeholder when no context can be created, and test the camera math and
  brushing in numpy, which needs no GL) or the native platform.
- **The native `windows` platform works without ever showing a window.**
  `QOffscreenSurface` + FBO renders fine, and the in-scene test uses
  `WA_DontShowOnScreen`. It still needs a desktop session. A CI service
  without an interactive desktop is untested.
- **Software fallback exists.** `QT_OPENGL=software` selects Qt's bundled
  Mesa llvmpipe (`opengl32sw.dll`, shipped with the PyQt5 wheel). It renders
  correctly, with the same consistency check passing, but slowly (table
  above).
- **Context profile matters for PyQt5.** The default hardware context
  requested as 3.3 *core* has no PyQt5 function table
  (`PyQt5._QOpenGLFunctions_3_3_Core` does not exist). The script therefore
  uses the default compatibility context and `QOpenGLFunctions_2_1` with
  GLSL 120. With PyOpenGL (and so `GLViewWidget`), this doesn't apply.
- Two PyQt5 pitfalls hit along the way:
  - `QOpenGLFramebufferObject(w, h, CombinedDepthStencil)` is invalid unless
    the target and internal format are passed explicitly
    (`GL_TEXTURE_2D, GL_RGBA8`).
  - PyQt5's `glReadPixels` wrapper rejects `GL_RGBA/GL_UNSIGNED_BYTE`
    ("pixel data format not supported"). `fbo.toImage()` is the working
    readback path.
- Linux (Xvfb + `LIBGL_ALWAYS_SOFTWARE=1`, or EGL) is **untested**.

## How to reproduce

```
# Windows PowerShell: make sure the offscreen platform is NOT set
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
python spikes/gl_offscreen_readback.py                      # hardware GL
python spikes/gl_offscreen_readback.py --software           # Mesa llvmpipe
python spikes/gl_offscreen_readback.py --save-png out_dir   # also dump frames
# bash: unset QT_QPA_PLATFORM; python spikes/gl_offscreen_readback.py
```

Requirements: PyQt5, numpy, pyqtgraph (only for the in-scene test).
PyOpenGL is **not** needed. Useful options:

- `--points 10000 100000 1000000`
- `--surface 500` (0 skips it)
- `--sizes 800x600 1600x1000`
- `--frames 60`
- `--point-size 4`
- `--in-scene 1 4` (pass the flag with no value to skip)
- `--in-scene-points`
- `--brush-points`
- `--platform NAME` (sets `QT_QPA_PLATFORM`)

The exit code is 0 when the consistency check passes, 1 on a render/projection
mismatch, and 2 when no GL context can be created.

### Not done here, for a session with PyOpenGL

The spike never ran `pyqtgraph.opengl` itself. To close that gap:

1. `pip install PyOpenGL`.
2. Build a `GLViewWidget` with one `GLScatterPlotItem(pos=..., size=4,
   pxMode=True)`, `resize(w, h)`, and set `WA_DontShowOnScreen` + `show()`.
3. Time `orbit(dx, 0)` + `grabFramebuffer()` + `QPixmap.fromImage()` over
   60 frames.

Expectation: the same order as the hardware table above, since it is the
same VBO/draw/FBO/`glReadPixels` path plus pyqtgraph's per-item Python
overhead (a handful of calls per item per frame). This is **unverified**.
Also check whether `GLViewWidget` can be driven with no visible window at
all. If it can't, keep this spike's approach: a `QOffscreenSurface`
renderer plus pyqtgraph's GL *items* or their shaders, not the widget.

## Go / no-go for Option A

**Threshold.** The whole window, 2D subplots included, should repaint
within one 60 Hz frame, 16.7 ms, during a camera drag. A 3D cell should
therefore use at most half of that, **≤ 8 ms**, leaving the rest for the
2D cells and Qt. With several 3D cells, the sum should stay ≤ 16.7 ms.

**Hardware GPU: GO.**

- Across every scene at 1600×1000 (up to a 1 M-point scatter or a
  1.5 M-vertex surface), a single cell costs **at most 2.44 ms median and
  2.91 ms p95**. That is about a third of the budget, and data size barely
  matters.
- Four 1 M-point 3D cells plus two 2D plots in a real `useOpenGL=True`
  GraphicsLayoutWidget take **6.8 ms per full-window frame (p95 7.8)**.
- Readback is the dominant cost, and it is bounded by pixel count, which
  the cell size already bounds.
- Camera forwarding and numpy projection brushing are both validated
  against real rendered pixels.

**Software GL (llvmpipe, e.g. a VM or remote desktop without a GPU):
NO-GO for large data, OK for small.**

- ≤ 10 k points fits the budget (2.9–4.8 ms).
- 100 k points is borderline (18–23 ms, about 50 fps for one cell).
- 1 M points is 5 fps.
- The readback is not the problem: readback plus pixmap is ≤ 2.6 ms. The drawing is, and a
  native `GLViewWidget` embedded any other way would draw just as slowly
  on the same rasterizer. So this is not an argument against Option A
  versus alternatives. It is an argument for **decimating while the camera
  moves** (draw every Nth point during a drag, the full set on release),
  much like the 2D side's `setDownsampling`.

**Conditions to carry into WP-O (Phase 6 integration):**

1. **Render on demand, not every frame.** Re-render only on a camera
   change, a data change, a resize or a brush. A static 3D cell just keeps
   painting its cached pixmap, which costs nothing extra. Mouse-drag frames
   are the only hot path, and they are what was measured.
2. **One offscreen context per figure**, shared by all its 3D cells: FBO
   per cell, or one FBO resized per cell as in the in-scene test. Call
   `makeCurrent(offscreen_surface)` before every render, because the
   `useOpenGL=True` viewport's context becomes current during every
   repaint. The in-scene test does exactly this and composites correctly.
3. **Brushing**: project once at brush press (numpy, about 30 ms for 1 M
   points), then run only the rect test per move (about 2 ms). A rect brush
   also selects occluded points behind the visible ones. Decide whether
   that is wanted. Depth-aware selection would need the depth buffer (not
   measured).
4. **HiDPI**: size the FBO as `cell size × devicePixelRatio`, or the cell
   will look blurry. Readback cost scales with that pixel count (not
   measured).
5. **Tests**: under the suite's `QT_QPA_PLATFORM=offscreen` there is no GL
   on Windows. Keep camera and brush math GL-free and unit-testable in
   numpy, and make the cell degrade to a placeholder when no context can be
   created.
