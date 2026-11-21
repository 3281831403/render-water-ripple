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

The functions below implement the analytic surface, its normal, UV
refraction/tiling, Fresnel reflectance, wave blending, validation, and an
independent per-frame batch generator.
"""

import math

TWO_PI = math.tau
MAX_FREQ = 64.0
TOLERANCE = 1e-6


class WaterError(ValueError):
    """Raised when wave, UV, or batch data violates the water contract."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _as_float(value, name):
    """Convert ``value`` to a finite float or raise :class:`WaterError`."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise WaterError(f"{name} must be a finite number") from None
    if not math.isfinite(number):
        raise WaterError(f"{name} must be a finite number")
    return number


def _check_uv(uv, name="uv"):
    """Validate and return a UV pair as a tuple of floats."""
    try:
        raw_u, raw_v = uv
    except (TypeError, ValueError):
        raise WaterError(f"{name} must be a pair of numbers") from None
    return _as_float(raw_u, f"{name}[0]"), _as_float(raw_v, f"{name}[1]")


def _wrap_unit(value):
    """Wrap ``value`` modulo 1.0 into ``[0, 1)``.

    ``math.fmod`` is used rather than ``%`` because the ``%`` operator can
    round a tiny negative remainder up to exactly ``1.0``; folding that back
    to ``0.0`` keeps the half-open range exact at the seam.
    """
    wrapped = math.fmod(value, 1.0)
    if wrapped < 0.0:
        wrapped += 1.0
    if wrapped >= 1.0:
        wrapped = 0.0
    return wrapped


def _wave_problems(index, wave):
    """Return the list of contract violations for one wave mapping."""
    problems = []
    prefix = f"wave[{index}]"
    if not isinstance(wave, dict):
        return [f"{prefix}: wave must be a mapping with dir/amp/freq"]

    # Direction: present, 2D, finite, non-zero.
    direction = wave.get("dir")
    if direction is None:
        problems.append(f"{prefix}: dir is required")
    else:
        try:
            dx, dy = direction
            dx = float(dx)
            dy = float(dy)
        except (TypeError, ValueError):
            problems.append(f"{prefix}: dir must be a finite non-zero 2D vector")
        else:
            if not (math.isfinite(dx) and math.isfinite(dy)):
                problems.append(
                    f"{prefix}: dir must be a finite non-zero 2D vector"
                )
            elif dx == 0.0 and dy == 0.0:
                problems.append(f"{prefix}: dir must be a non-zero vector")

    # Amplitude: present, finite, non-negative.
    if "amp" not in wave:
        problems.append(f"{prefix}: amp is required")
    else:
        try:
            amp = float(wave["amp"])
        except (TypeError, ValueError):
            problems.append(f"{prefix}: amp must be a finite number >= 0")
        else:
            if not math.isfinite(amp):
                problems.append(f"{prefix}: amp must be a finite number")
            elif amp < 0.0:
                problems.append(f"{prefix}: amp must be non-negative, got {amp}")

    # Frequency: present, finite, within [0, MAX_FREQ].
    if "freq" not in wave:
        problems.append(f"{prefix}: freq is required")
    else:
        try:
            freq = float(wave["freq"])
        except (TypeError, ValueError):
            problems.append(
                f"{prefix}: freq must be a finite number in [0, {MAX_FREQ}]"
            )
        else:
            if not math.isfinite(freq):
                problems.append(f"{prefix}: freq must be finite")
            elif freq < 0.0:
                problems.append(f"{prefix}: freq must be non-negative, got {freq}")
            elif freq > MAX_FREQ:
                problems.append(
                    f"{prefix}: freq must not exceed {MAX_FREQ}, got {freq}"
                )

    # Speed is optional but must be finite when supplied.
    if "speed" in wave:
        try:
            speed = float(wave["speed"])
        except (TypeError, ValueError):
            problems.append(f"{prefix}: speed must be a finite number")
        else:
            if not math.isfinite(speed):
                problems.append(f"{prefix}: speed must be a finite number")

    return problems


def _require_valid_waves(waves):
    """Validate ``waves``; raise on any problem, else return a list snapshot.

    Returning a materialized list means generators are validated once and
    then iterated from the snapshot rather than from a consumed iterator.
    """
    if waves is None:
        raise WaterError("waves must be a sequence of wave mappings")
    try:
        wave_list = list(waves)
    except TypeError:
        raise WaterError("waves must be a sequence of wave mappings") from None
    problems = validate_waves(wave_list)
    if problems:
        raise WaterError("; ".join(problems))
    return wave_list


def _phase_terms(wave, u, v, time):
    """Return ``(amp, k, dx, dy, phase)`` for one wave at ``(u, v, time)``.

    ``k`` is ``2*pi*freq`` and ``(dx, dy)`` is the normalized direction.
    """
    dx, dy = wave["dir"]
    dx = float(dx)
    dy = float(dy)
    length = math.hypot(dx, dy)
    if length == 0.0 or not math.isfinite(length):
        raise WaterError("dir must be a finite non-zero 2D vector")
    dx /= length
    dy /= length

    amp = float(wave["amp"])
    freq = float(wave["freq"])
    speed = float(wave.get("speed", 0.0))
    k = TWO_PI * freq
    phase = k * ((dx * u + dy * v) - speed * float(time))
    return amp, k, dx, dy, phase


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
    wave_list = _require_valid_waves(waves)
    if not wave_list:
        return 0.0
    u, v = _check_uv(uv)
    t = _as_float(time, "time")

    total = 0.0
    for wave in wave_list:
        amp, _k, _dx, _dy, phase = _phase_terms(wave, u, v, t)
        total += amp * math.sin(phase)
    return total


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
    wave_list = _require_valid_waves(waves)
    u, v = _check_uv(uv)
    t = _as_float(time, "time")
    scale = _as_float(scale, "scale")

    dh_du = 0.0
    dh_dv = 0.0
    for wave in wave_list:
        amp, k, dx, dy, phase = _phase_terms(wave, u, v, t)
        derivative = amp * k * math.cos(phase)
        dh_du += derivative * dx
        dh_dv += derivative * dy

    nx = -scale * dh_du
    ny = -scale * dh_dv
    nz = 1.0
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    return (nx / length, ny / length, nz / length)


def refract_uv(uv, normal, strength) -> tuple:
    """Refract a UV sample by a surface normal and wrap it back into range.

    The horizontal offset is ``(normal[0] * strength, normal[1] * strength)``;
    ``normal`` is a 3-tuple whose first two components are used.  Add that
    offset to ``uv`` and wrap each component modulo 1.0, returning a pair in
    ``[0, 1)``.  Wrapping (rather than clamping) keeps the result continuous
    across both edges and avoids stretched edge samples.
    """
    u, v = _check_uv(uv)
    try:
        nx, ny = normal[0], normal[1]
    except (TypeError, IndexError):
        raise WaterError("normal must have at least two components") from None
    strength = _as_float(strength, "strength")
    return (
        _wrap_unit(u + _as_float(nx, "normal[0]") * strength),
        _wrap_unit(v + _as_float(ny, "normal[1]") * strength),
    )


def fresnel(cos_theta, f0) -> float:
    """Return the Schlick Fresnel reflectance in the range ``[0, 1]``.

    ``cos_theta`` is the clamped cosine of the view angle (``0..1``) and
    ``f0`` is the normal-incidence reflectance (also in ``0..1``)::

        f = f0 + (1 - f0) * (1 - cos_theta) ** 5

    The result must depend on the view angle, equal ``f0`` at normal incidence
    (``cos_theta == 1``), and approach ``1.0`` at grazing incidence
    (``cos_theta == 0``).
    """
    cos_theta = _as_float(cos_theta, "cos_theta")
    f0 = _as_float(f0, "f0")
    if not 0.0 <= cos_theta <= 1.0:
        raise WaterError("cos_theta must be in [0, 1]")
    if not 0.0 <= f0 <= 1.0:
        raise WaterError("f0 must be in [0, 1]")
    return f0 + (1.0 - f0) * (1.0 - cos_theta) ** 5


def blend_waves(waves, weights) -> list:
    """Blend waves with normalized weights and return new wave mappings.

    ``weights`` has one finite, non-negative entry per wave.  Normalize the
    weights to sum to 1.0 (raising WaterError when the sum is zero, the
    lengths differ, or a weight is invalid), then return a new list in input
    order in which each wave's amplitude is multiplied by its normalized
    weight.  All other fields are copied unchanged.  Inputs must not be
    mutated, and the blended amplitudes must not overflow the original scale.
    """
    try:
        wave_list = list(waves)
    except TypeError:
        raise WaterError("waves must be a sequence of wave mappings") from None
    try:
        weight_list = list(weights)
    except TypeError:
        raise WaterError("weights must be a sequence of numbers") from None
    if len(wave_list) != len(weight_list):
        raise WaterError("waves and weights must have the same length")

    wave_list = _require_valid_waves(wave_list)

    normalized = []
    total = 0.0
    for index, weight in enumerate(weight_list):
        number = _as_float(weight, f"weights[{index}]")
        if number < 0.0:
            raise WaterError(f"weights[{index}] must be non-negative")
        normalized.append(number)
        total += number
    if total <= 0.0 or not math.isfinite(total):
        raise WaterError("weights must sum to a positive finite value")
    normalized = [number / total for number in normalized]

    blended = []
    for wave, weight in zip(wave_list, normalized):
        clone = dict(wave)
        clone["dir"] = (float(wave["dir"][0]), float(wave["dir"][1]))
        clone["amp"] = float(wave["amp"]) * weight
        clone["freq"] = float(wave["freq"])
        clone["speed"] = float(wave.get("speed", 0.0))
        blended.append(clone)
    return blended


def tile_wrap(uv) -> tuple:
    """Wrap a UV pair modulo 1.0 and return a pair in ``[0, 1)``.

    Use modular wrapping, not clamping, so that values just below and just
    above the seam remain adjacent.  For example ``(1.2, -0.2)`` becomes
    ``(0.2, 0.8)`` and an exact boundary value of 1.0 becomes 0.0.
    """
    u, v = _check_uv(uv)
    return (_wrap_unit(u), _wrap_unit(v))


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
    if waves is None:
        return ["waves must be a sequence of wave mappings"]
    try:
        wave_list = list(waves)
    except TypeError:
        return ["waves must be a sequence of wave mappings"]

    problems = []
    for index, wave in enumerate(wave_list):
        problems.extend(_wave_problems(index, wave))
    return problems


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
    if not isinstance(config, dict):
        raise WaterError("config must be a mapping")
    try:
        frame_list = list(frames)
    except TypeError:
        raise WaterError("frames must be a sequence of mappings") from None

    scale = _as_float(config.get("scale", 1.0), "config.scale")
    refract_strength = _as_float(
        config.get("refract_strength", 0.0), "config.refract_strength"
    )
    cos_theta = _as_float(config.get("cos_theta", 1.0), "config.cos_theta")
    f0 = _as_float(config.get("f0", 0.04), "config.f0")

    default_waves = config.get("waves", [])
    if default_waves is None:
        default_waves = []
    # Take an independent snapshot so later mutation by a caller cannot leak
    # between frames and so we never mutate the caller's config.
    try:
        default_waves = [dict(wave) for wave in default_waves]
    except TypeError:
        raise WaterError("config.waves must be a sequence of mappings") from None
    _require_valid_waves(default_waves)

    # Validate every frame up front so an invalid frame anywhere in the batch
    # raises before any record is produced (atomic rollback).
    prepared = []
    for index, frame in enumerate(frame_list):
        if not isinstance(frame, dict):
            raise WaterError(f"frames[{index}] must be a mapping")
        u, v = _check_uv(frame.get("uv"), f"frames[{index}].uv")
        time = _as_float(frame.get("time"), f"frames[{index}].time")
        if "waves" in frame and frame["waves"] is not None:
            try:
                waves = [dict(wave) for wave in frame["waves"]]
            except TypeError:
                raise WaterError(
                    f"frames[{index}].waves must be a sequence of mappings"
                ) from None
        else:
            waves = [dict(wave) for wave in default_waves]
        _require_valid_waves(waves)
        prepared.append((index, (u, v), time, waves))

    records = []
    for index, (u, v), time, waves in prepared:
        # Compute each record from fresh, frame-local wave data.  No wave
        # phase or surface state is shared across frames.
        height = wave_height(waves, (u, v), time)
        normal = wave_normal(waves, (u, v), time, scale)
        refracted_uv = refract_uv((u, v), normal, refract_strength)
        reflectance = fresnel(cos_theta, f0)
        records.append(
            {
                "uv": (u, v),
                "time": time,
                "height": height,
                "normal": normal,
                "refracted_uv": refracted_uv,
                "fresnel": reflectance,
            }
        )

    return {"count": len(records), "frames": records}
