"""Procedural water-ripple primitives.

Coordinate and data contract
----------------------------
* UV coordinates are floats in ``[0, 1]``.  Operations that would leave that
  range wrap modulo 1.0.
* A wave is a mapping ``{"dir": (x, y), "freq": float, "amp": float,
  "speed": float}``.  ``dir`` is normalized before use, ``freq`` is the wave
  number in cycles per UV unit, ``amp`` is the peak amplitude, and ``speed``
  is the phase advance per unit time.
* ``MAX_FREQ`` is the largest supported wave number.
* Numeric comparisons in this project use an absolute tolerance of ``1e-6``.

All functions below are intentional stubs for the bug-fixing exercise.
"""

import math

TWO_PI = math.tau
MAX_FREQ = 64.0
TOLERANCE = 1e-6


class WaterError(ValueError):
    """Raised when wave, UV, or batch data violates the water contract."""


def wave_height(waves, uv, time) -> float:
    """Return the height of stacked sine waves at ``uv`` and ``time``.

    The required surface is::

        h(uv, t) = sum_i amp_i * sin(2*pi * freq_i *
                                      (dot(normalize(dir_i), uv) - speed_i*t))

    ``uv`` is a pair in ``[0, 1]``.  Each direction must be a non-zero finite
    2D vector and is normalized so that equal phase distances give equal wave
    travel regardless of the magnitude of ``dir``.  Return ``0.0`` for an
    empty wave list.

    Raises:
        WaterError: if a wave has a zero/non-finite direction, a negative
            amplitude, a negative frequency, or a frequency above MAX_FREQ.
    """
    raise NotImplementedError("wave_height is not implemented")


def wave_normal(waves, uv, time, scale) -> tuple:
    """Return the normalized analytic normal of the water surface.

    With ``h`` from :func:`wave_height`, the analytic partial derivatives are
    used to form::

        n = normalize((-scale * dh/du, -scale * dh/dv, 1.0))

    ``scale`` controls the visual bump strength and must be finite.  The
    returned tuple has three components and unit length.  Do not estimate the
    derivatives with finite differences: a coarse sample step loses high
    frequency detail.  Results are accurate to an absolute tolerance of 1e-6.
    """
    raise NotImplementedError("wave_normal is not implemented")


def refract_uv(uv, normal, strength) -> tuple:
    """Refract a UV sample by a surface normal and wrap it back into range.

    The horizontal offset is ``(normal[0] * strength, normal[1] * strength)``;
    ``normal`` is a 3-tuple whose first two components are used.  Add that
    offset to ``uv`` and wrap each component modulo 1.0, returning a pair in
    ``[0, 1)``.  Wrapping (rather than clamping) keeps the result continuous
    across both edges and avoids stretched edge samples.
    """
    raise NotImplementedError("refract_uv is not implemented")


def fresnel(cos_theta, f0) -> float:
    """Return the Schlick Fresnel reflectance in the range ``[0, 1]``.

    ``cos_theta`` is the clamped cosine of the view angle (``0..1``) and
    ``f0`` is the normal-incidence reflectance (also in ``0..1``)::

        f = f0 + (1 - f0) * (1 - cos_theta) ** 5

    The result must depend on the view angle, equal ``f0`` at normal incidence
    (``cos_theta == 1``), and approach ``1.0`` at grazing incidence
    (``cos_theta == 0``).
    """
    raise NotImplementedError("fresnel is not implemented")


def blend_waves(waves, weights) -> list:
    """Blend waves with normalized weights and return new wave mappings.

    ``weights`` has one finite, non-negative entry per wave.  Normalize the
    weights to sum to 1.0 (raising WaterError when the sum is zero, the
    lengths differ, or a weight is invalid), then return a new list in input
    order in which each wave's amplitude is multiplied by its normalized
    weight.  All other fields are copied unchanged.  Inputs must not be
    mutated, and the blended amplitudes must not overflow the original scale.
    """
    raise NotImplementedError("blend_waves is not implemented")


def tile_wrap(uv) -> tuple:
    """Wrap a UV pair modulo 1.0 and return a pair in ``[0, 1)``.

    Use modular wrapping, not clamping, so that values just below and just
    above the seam remain adjacent.  For example ``(1.2, -0.2)`` becomes
    ``(0.2, 0.8)`` and an exact boundary value of 1.0 becomes 0.0.
    """
    raise NotImplementedError("tile_wrap is not implemented")


def validate_waves(waves) -> list[str]:
    """Return a list of human-readable problems; an empty list means valid.

    Each wave is checked independently.  Report a non-zero direction
    requirement, a non-negative amplitude requirement, and a frequency in
    ``[0, MAX_FREQ]``.  Collect every problem instead of stopping at the first
    one.  The issue strings should identify the offending field (for example,
    contain ``"dir"``, ``"amp"``, or ``"freq"``).  This function does not
    raise WaterError for ordinary invalid wave data; callers that need strict
    behavior use wave_height or ripple_batch.
    """
    raise NotImplementedError("validate_waves is not implemented")


def ripple_batch(frames, config) -> dict:
    """Generate independent ripple records for a batch of frames atomically.

    ``frames`` is a sequence of mappings.  Each frame supplies ``"uv"`` (a
    pair in ``[0, 1]``) and ``"time"`` (a float), and may override the default
    wave list with ``"waves"``.  ``config`` supplies the defaults::

        {
            "waves": [...],
            "scale": 1.0,
            "refract_strength": 0.0,
            "cos_theta": 1.0,
            "f0": 0.04,
        }

    Return::

        {
            "count": len(frames),
            "frames": [
                {
                    "uv": (u, v),
                    "time": t,
                    "height": h,
                    "normal": (nx, ny, nz),
                    "refracted_uv": (ru, rv),
                    "fresnel": f,
                },
                ...
            ],
        }

    Records preserve input order.  Every frame is an independent computation:
    batches must not share mutable wave phase or surface state between frames,
    and frames/config must not be mutated.  Validate every effective wave list
    and frame before returning.  If any frame is invalid, raise WaterError and
    roll back the whole batch (return no partial records).
    """
    raise NotImplementedError("ripple_batch is not implemented")
