"""Shared Trading 212 options helpers."""

from __future__ import annotations

from typing import Any, Mapping

from .const import (
    CONF_MAX_POSITION_ENTITIES,
    CONF_POSITION_DISPLAY_FORMAT,
    DEFAULT_MAX_POSITION_ENTITIES,
    FEATURE_ACCOUNT_SUMMARY,
    FEATURE_OPTION_DEFAULTS,
    FEATURE_OPTIONS,
    MAX_POSITION_ENTITIES,
    MIN_POSITION_ENTITIES,
    POSITION_DISPLAY_FORMATS,
)


def get_entry_options(options: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return merged entry options with saved values preserved over defaults."""
    merged: dict[str, Any] = dict(FEATURE_OPTION_DEFAULTS)
    if isinstance(options, Mapping):
        for key, value in options.items():
            merged[key] = value
    return _normalise_merged_options(merged)


def merge_entry_options(
    base_options: Mapping[str, Any] | None = None,
    updates: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return merged options with updates applied over existing saved values."""
    merged: dict[str, Any] = dict(FEATURE_OPTION_DEFAULTS)
    if isinstance(base_options, Mapping):
        for key, value in base_options.items():
            merged[key] = value
    if isinstance(updates, Mapping):
        for key, value in updates.items():
            merged[key] = value
    return _normalise_merged_options(merged)


def _normalise_merged_options(options: Mapping[str, Any]) -> dict[str, Any]:
    """Return a validated merged options mapping."""
    normalised: dict[str, Any] = dict(options)
    for key in FEATURE_OPTIONS:
        normalised[key] = bool(
            options.get(key, FEATURE_OPTION_DEFAULTS.get(key, False))
        )

    try:
        max_positions = int(
            options.get(CONF_MAX_POSITION_ENTITIES, DEFAULT_MAX_POSITION_ENTITIES)
        )
    except (TypeError, ValueError):
        max_positions = DEFAULT_MAX_POSITION_ENTITIES
    normalised[CONF_MAX_POSITION_ENTITIES] = min(
        max(max_positions, MIN_POSITION_ENTITIES),
        MAX_POSITION_ENTITIES,
    )

    position_display_format = options.get(CONF_POSITION_DISPLAY_FORMAT)
    if (
        isinstance(position_display_format, str)
        and position_display_format in POSITION_DISPLAY_FORMATS
    ):
        normalised[CONF_POSITION_DISPLAY_FORMAT] = position_display_format
    else:
        normalised[CONF_POSITION_DISPLAY_FORMAT] = FEATURE_OPTION_DEFAULTS[
            CONF_POSITION_DISPLAY_FORMAT
        ]

    normalised[FEATURE_ACCOUNT_SUMMARY] = True
    return normalised
