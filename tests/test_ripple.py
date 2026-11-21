"""Fifteen red tests for the procedural water-ripple exercise."""

import math

import pytest

from water.ripple import (
    WaterError,
    blend_waves,
    fresnel,
    refract_uv,
    ripple_batch,
    tile_wrap,
    validate_waves,
    wave_height,
    wave_normal,
)


def _wave(dir=(1.0, 0.0), freq=1.0, amp=1.0, speed=0.0):
    """Build one wave mapping using the project's canonical fields."""
    return {
        "dir": (float(dir[0]), float(dir[1])),
        "freq": float(freq),
        "amp": float(amp),
        "speed": float(speed),
    }


def test_direction_is_normalized_for_phase():
    """Defect 1: phase must not depend on the magnitude of ``dir``."""
    raw = _wave(dir=(3.0, 4.0), freq=1.0, amp=0.8, speed=0.0)
    unit = _wave(dir=(0.6, 0.8), freq=1.0, amp=0.8, speed=0.0)
    uv = (0.2, 0.1)
    expected = 0.8 * math.sin(math.tau * 0.2)

    assert wave_height([raw], uv, 0.0) == pytest.approx(expected, abs=1e-6)
    assert wave_height([unit], uv, 0.0) == pytest.approx(expected, abs=1e-6)


def test_wave_height_scales_with_amplitude():
    """Defect 2: amplitude must multiply the sine wave."""
    wave = _wave(dir=(1.0, 0.0), freq=1.0, amp=0.2, speed=0.0)
    expected = 0.2 * math.sin(math.pi / 4.0)

    assert wave_height([wave], (0.125, 0.0), 0.0) == pytest.approx(
        expected, abs=1e-6
    )


def test_wave_normal_uses_analytic_partials():
    """Defect 3: coarse finite differences lose high-frequency detail."""
    wave = _wave(dir=(1.0, 0.0), freq=2.0, amp=0.5, speed=0.0)
    gradient = 0.5 * math.tau * 2.0
    inv_length = 1.0 / math.sqrt(gradient * gradient + 1.0)
    expected = (-gradient * inv_length, 0.0, inv_length)

    assert wave_normal([wave], (0.0, 0.0), 0.0, 1.0) == pytest.approx(
        expected, abs=1e-6
    )


def test_wave_normal_is_unit_length():
    """Defect 4: an unnormalized normal makes reflections too bright."""
    waves = [
        _wave(dir=(1.0, 0.0), freq=1.5, amp=0.8, speed=0.6),
        _wave(dir=(0.0, 1.0), freq=3.0, amp=0.25, speed=0.1),
    ]
    normal = wave_normal(waves, (0.3, 0.7), 0.2, 2.0)
    length = math.sqrt(sum(component * component for component in normal))

    assert length == pytest.approx(1.0, abs=1e-6)
    assert normal[2] > 0.0


def test_refract_uv_wraps_at_edges():
    """Defect 5: refraction must wrap, not stretch, beyond either edge."""
    normal = (0.5, -0.75, 0.433)

    assert refract_uv((0.98, 0.02), normal, 0.2) == pytest.approx(
        (0.08, 0.87), abs=1e-6
    )


def test_fresnel_depends_on_view_angle():
    """Defect 6: Fresnel response must vary with the view angle."""
    f0 = 0.04

    assert fresnel(0.5, f0) == pytest.approx(0.07, abs=1e-6)
    assert fresnel(1.0, f0) == pytest.approx(f0, abs=1e-6)
    assert fresnel(0.0, f0) == pytest.approx(1.0, abs=1e-6)


def test_blend_waves_normalizes_weights():
    """Defect 7: blending must normalize weights so amplitude cannot overflow."""
    waves = [
        _wave(dir=(1.0, 0.0), freq=1.0, amp=0.5, speed=0.3),
        _wave(dir=(0.0, 1.0), freq=2.0, amp=0.5, speed=-0.2),
    ]
    blended = blend_waves(waves, [3.0, 1.0])

    assert len(blended) == 2
    assert [wave["amp"] for wave in blended] == pytest.approx(
        [0.375, 0.125], abs=1e-6
    )
    assert sum(wave["amp"] for wave in blended) == pytest.approx(0.5, abs=1e-6)
    assert [wave["dir"] for wave in blended] == [(1.0, 0.0), (0.0, 1.0)]
    assert [wave["freq"] for wave in blended] == [1.0, 2.0]
    assert [wave["amp"] for wave in waves] == [0.5, 0.5]


def test_tile_wrap_is_continuous_at_seam():
    """Defect 8: UV tiling must wrap instead of clamping at the seam."""
    assert tile_wrap((1.0, 0.25)) == pytest.approx((0.0, 0.25), abs=1e-6)
    assert tile_wrap((1.2, -0.2)) == pytest.approx((0.2, 0.8), abs=1e-6)
    assert tile_wrap((2.25, 1.75)) == pytest.approx((0.25, 0.75), abs=1e-6)


def test_ripple_batch_frames_do_not_share_state():
    """Defect 9: each batch frame must be computed independently."""
    first_wave = _wave(dir=(1.0, 0.0), freq=1.2, amp=0.6, speed=0.3)
    second_wave = _wave(dir=(0.0, 1.0), freq=0.8, amp=0.4, speed=0.5)
    config = {
        "waves": [first_wave],
        "scale": 1.0,
        "refract_strength": 0.05,
        "f0": 0.04,
    }
    frames = [
        {"uv": (0.10, 0.20), "time": 0.0, "waves": [first_wave]},
        {"uv": (0.35, 0.15), "time": 0.25, "waves": [second_wave]},
        {"uv": (0.10, 0.20), "time": 0.0, "waves": [first_wave]},
    ]
    expected = [
        wave_height([first_wave], (0.10, 0.20), 0.0),
        wave_height([second_wave], (0.35, 0.15), 0.25),
        wave_height([first_wave], (0.10, 0.20), 0.0),
    ]
    result = ripple_batch(frames, config)
    heights = [record["height"] for record in result["frames"]]

    assert heights == pytest.approx(expected, abs=1e-6)
    assert heights[0] == pytest.approx(heights[2], abs=1e-6)


def test_negative_amplitude_is_rejected_and_rolls_back():
    """Defect 10: negative amplitude must be reported, rejected, and atomic."""
    good = _wave(dir=(1.0, 0.0), freq=1.0, amp=0.25, speed=0.0)
    bad = _wave(dir=(1.0, 0.0), freq=1.0, amp=-0.25, speed=0.0)
    config = {
        "waves": [good],
        "scale": 1.0,
        "refract_strength": 0.05,
        "f0": 0.04,
    }
    frames = [
        {"uv": (0.10, 0.10), "time": 0.0, "waves": [good]},
        {"uv": (0.20, 0.20), "time": 0.1, "waves": [bad]},
    ]

    issues = validate_waves([bad])
    assert any("amp" in issue.lower() for issue in issues)
    assert validate_waves([good]) == []

    with pytest.raises(WaterError):
        wave_height([bad], (0.2, 0.3), 0.1)

    with pytest.raises(WaterError):
        ripple_batch(frames, config)


def test_single_wave_height_is_zero_at_time_zero():
    """Additional check: a single wave begins at amp * sin(0) == 0."""
    wave = _wave(dir=(3.0, 4.0), freq=2.0, amp=0.7, speed=1.3)

    assert wave_height([wave], (0.0, 0.0), 0.0) == pytest.approx(0.0, abs=1e-6)


def test_zero_amplitude_always_flat():
    """Additional check: zero-amplitude waves stay flat at every sample."""
    waves = [
        _wave(dir=(1.0, 0.0), freq=3.0, amp=0.0, speed=1.0),
        _wave(dir=(0.0, 1.0), freq=2.0, amp=0.0, speed=0.5),
    ]
    samples = [((0.1, 0.2), 0.0), ((0.4, 0.6), 0.75), ((0.9, 0.9), 2.0)]

    for uv, time in samples:
        assert wave_height(waves, uv, time) == pytest.approx(0.0, abs=1e-6)


def test_empty_wave_list_returns_zero():
    """Additional check: no waves means a flat surface."""
    assert wave_height([], (0.4, 0.6), 1.3) == pytest.approx(0.0, abs=1e-6)


def test_negative_frequency_raises_water_error():
    """Additional check: negative frequency is outside the contract."""
    bad = _wave(dir=(1.0, 0.0), freq=-0.01, amp=0.2, speed=0.0)

    with pytest.raises(WaterError):
        wave_height([bad], (0.2, 0.3), 0.4)


def test_ripple_batch_preserves_frame_order():
    """Additional check: successful batches keep the exact input frame order."""
    waves = [
        _wave(dir=(1.0, 0.0), freq=1.5, amp=0.5, speed=0.4),
        _wave(dir=(0.0, 1.0), freq=0.75, amp=0.2, speed=0.1),
    ]
    config = {
        "waves": waves,
        "scale": 1.0,
        "refract_strength": 0.03,
        "f0": 0.04,
    }
    frames = [
        {"uv": (0.0, 0.0), "time": 0.0},
        {"uv": (0.12, 0.0), "time": 0.25},
        {"uv": (0.31, 0.47), "time": 0.5},
    ]
    expected = [
        wave_height(waves, frame["uv"], frame["time"]) for frame in frames
    ]
    result = ripple_batch(frames, config)

    assert result["count"] == 3
    assert [record["uv"] for record in result["frames"]] == [
        (0.0, 0.0),
        (0.12, 0.0),
        (0.31, 0.47),
    ]
    assert [record["time"] for record in result["frames"]] == [0.0, 0.25, 0.5]
    assert [record["height"] for record in result["frames"]] == pytest.approx(
        expected, abs=1e-6
    )
