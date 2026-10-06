"""Core calculations used by the Discipline Score research notebooks."""

from __future__ import annotations

from typing import Any

import pandas as pd


PITCH_CATEGORIES = {
    "fastball": {"FF", "SI", "FC", "FA"},
    "breaking": {"SL", "CU", "ST", "SV", "KC", "SC", "KN"},
    "offspeed": {"CH", "FS", "FO", "CS", "EP"},
    "pitchout": {"PO"},
}

SWING_DESCRIPTIONS = {
    "swinging_strike",
    "swinging_strike_blocked",
    "foul",
    "foul_tip",
    "foul_bunt",
    "hit_into_play",
    "hit_into_play_no_out",
    "hit_into_play_score",
    "bunt_foul_tip",
    "missed_bunt",
}

NO_CONTACT_DESCRIPTIONS = {
    "swinging_strike",
    "swinging_strike_blocked",
    "foul",
    "foul_tip",
    "foul_bunt",
    "missed_bunt",
    "bunt_foul_pitch",
}


def categorize_pitch(pitch_type: str) -> str:
    """Map a Statcast pitch code to a broad pitch family."""
    for category, pitch_types in PITCH_CATEGORIES.items():
        if pitch_type in pitch_types:
            return category
    return "unknown"


def is_swing(description: str) -> int:
    """Return 1 for a swing description and 0 otherwise."""
    return int(description in SWING_DESCRIPTIONS)


def is_outside_zone(
    plate_x: float,
    plate_z: float,
    sz_top: float,
    sz_bottom: float,
    ball_radius: float = 0.02,
) -> bool:
    """Approximate whether the center of a pitch is outside the strike zone."""
    inside_horizontal = abs(plate_x) <= 0.83 + ball_radius
    inside_vertical = sz_bottom - ball_radius <= plate_z <= sz_top + ball_radius
    return not (inside_horizontal and inside_vertical)


def normalize_plate_z(plate_z: float, sz_top: float, sz_bottom: float) -> float:
    """Express vertical pitch location relative to the hitter's strike zone."""
    zone_height = sz_top - sz_bottom
    if zone_height == 0:
        raise ValueError("sz_top and sz_bottom must define a non-zero strike zone")
    return (plate_z - sz_bottom) / zone_height


def discipline_score(swing: int, swing_probability: float) -> float:
    """Calculate pitch-level Discipline Score.

    Takes receive ``+p`` and swings receive ``-(1-p)``, where ``p`` is the
    estimated probability that a comparable pitch induces a swing.
    """
    if swing not in (0, 1):
        raise ValueError("swing must be 0 (take) or 1 (swing)")
    if not 0 <= swing_probability <= 1:
        raise ValueError("swing_probability must be between 0 and 1")
    return swing_probability if swing == 0 else -(1 - swing_probability)


def contact_quality(
    swing: int,
    description: str,
    launch_speed: float | None,
    launch_angle: float | None,
) -> float:
    """Calculate the project's simple contact-quality adjustment."""
    if swing == 0 or description in NO_CONTACT_DESCRIPTIONS:
        return 0.0
    if _is_missing(launch_speed) or _is_missing(launch_angle):
        return float("nan")

    exit_velocity_score = min(1.0, max(0.0, (float(launch_speed) - 70.0) / 28.0))
    launch_angle_score = max(0.0, 1.0 - abs(float(launch_angle) - 20.0) / 20.0)
    return exit_velocity_score * launch_angle_score


def adjusted_discipline_score(ds: float, cq: float) -> float:
    """Combine decision quality and contact quality."""
    return ds + cq


def add_scores(
    pitches: pd.DataFrame,
    *,
    swing_column: str = "swing",
    probability_column: str = "swing_probability",
) -> pd.DataFrame:
    """Return a copy of a pitch table with DS, CQ, and ADS columns added."""
    required = {
        swing_column,
        probability_column,
        "description",
        "launch_speed",
        "launch_angle",
    }
    missing = required.difference(pitches.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    result = pitches.copy()
    result["discipline_score"] = result.apply(
        lambda row: discipline_score(row[swing_column], row[probability_column]), axis=1
    )
    result["contact_quality"] = result.apply(
        lambda row: contact_quality(
            row[swing_column],
            row["description"],
            row["launch_speed"],
            row["launch_angle"],
        ),
        axis=1,
    )
    result["adjusted_discipline_score"] = (
        result["discipline_score"] + result["contact_quality"]
    )
    return result


def _is_missing(value: Any) -> bool:
    """Handle Python, NumPy, and pandas scalar missing values."""
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False
