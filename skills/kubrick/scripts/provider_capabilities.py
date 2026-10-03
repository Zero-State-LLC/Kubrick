#!/usr/bin/env python3
"""Provider capability declarations for Kubrick image/video surfaces.

Adapters may change syntax only. When a request exceeds a provider's declared
capability, compilers fail closed with NOT_COMPUTABLE rather than inventing
unsupported temporal or dialogue behavior.
"""
from __future__ import annotations

from typing import Any

# Declared capabilities — keep conservative; unknown providers inherit generic.
PROVIDER_CAPABILITIES: dict[str, dict[str, Any]] = {
    "generic": {
        "image": True,
        "video": True,
        "max_duration_seconds": 16.0,
        "camera_motion": True,
        "dialogue_audio": False,
        "multi_shot": True,
        "physics_hints": True,
        "identity_lock": True,
    },
    "flux": {
        "image": True,
        "video": False,
        "max_duration_seconds": 0.0,
        "camera_motion": False,
        "dialogue_audio": False,
        "multi_shot": False,
        "physics_hints": False,
        "identity_lock": True,
    },
    "sd3": {
        "image": True,
        "video": False,
        "max_duration_seconds": 0.0,
        "camera_motion": False,
        "dialogue_audio": False,
        "multi_shot": False,
        "physics_hints": False,
        "identity_lock": True,
    },
    "midjourney": {
        "image": True,
        "video": False,
        "max_duration_seconds": 0.0,
        "camera_motion": False,
        "dialogue_audio": False,
        "multi_shot": False,
        "physics_hints": False,
        "identity_lock": True,
    },
    "grok-imagine": {
        "image": True,
        "video": True,
        "max_duration_seconds": 8.0,
        "camera_motion": True,
        "dialogue_audio": False,
        "multi_shot": False,
        "physics_hints": True,
        "identity_lock": True,
    },
    "keyframe": {
        "image": True,
        "video": True,
        "min_duration_seconds": 3.0,
        "max_duration_seconds": 60.0,
        "camera_motion": True,
        "dialogue_audio": True,
        "multi_shot": True,
        "physics_hints": True,
        "identity_lock": True,
        "is_multi_shot_single_clip": True,
        "short_beat_threshold_seconds": 2.0,
        "start_frame_hold_seconds": 1.6,
        "exclusive_inputs": [["startImage", "referenceImages"]],
        "exclusivity_notes": {
            "startImage|referenceImages": (
                "Seedance 2.5: startImage and referenceImages are mutually exclusive; "
                "references dropped on shot {shot}"
            ),
        },
        "known_drift": [
            {
                "id": "plain-top-motion-logo",
                "pattern": "plain top + motion",
                "effect": "invented chest logo/graphic",
                "providers": ["keyframe"],
            }
        ],
    },
}


def normalize_provider(provider: str | None) -> str:
    name = (provider or "generic").strip().lower() or "generic"
    return name


def capabilities_for(provider: str | None) -> dict[str, Any]:
    name = normalize_provider(provider)
    if name in PROVIDER_CAPABILITIES:
        return dict(PROVIDER_CAPABILITIES[name])
    # Unknown providers: image-only, no invented video support.
    return {
        "image": True,
        "video": False,
        "max_duration_seconds": 0.0,
        "camera_motion": False,
        "dialogue_audio": False,
        "multi_shot": False,
        "physics_hints": False,
        "identity_lock": True,
        "unknown_provider": True,
    }


def check_image_adapt(provider: str | None) -> dict[str, Any] | None:
    caps = capabilities_for(provider)
    if not caps.get("image"):
        return {
            "code": "PROVIDER_CAPABILITY",
            "message": f"provider `{normalize_provider(provider)}` does not support image adaptation",
            "capabilities": caps,
        }
    return None


def check_video_adapt(provider: str | None, *, duration: float | None = None) -> dict[str, Any] | None:
    caps = capabilities_for(provider)
    name = normalize_provider(provider)
    if not caps.get("video"):
        return {
            "code": "PROVIDER_CAPABILITY",
            "message": f"provider `{name}` does not support video adaptation",
            "capabilities": caps,
        }
    if duration is not None and "min_duration_seconds" in caps:
        min_dur = float(caps["min_duration_seconds"])
        if float(duration) < min_dur:
            return {
                "code": "PROVIDER_CAPABILITY",
                "message": f"requested duration {duration}s is below `{name}` minimum {min_dur}s",
                "capabilities": caps,
            }
    if duration is not None:
        max_dur = float(caps.get("max_duration_seconds") or 0.0)
        if max_dur > 0 and float(duration) > max_dur:
            return {
                "code": "PROVIDER_CAPABILITY",
                "message": (
                    f"requested duration {duration}s exceeds `{name}` max "
                    f"{max_dur}s"
                ),
                "capabilities": caps,
            }
    return None


def check_video_shot(provider: str | None, *, duration: float, wants_camera_motion: bool = False) -> dict[str, Any] | None:
    """Optional advisory when compiling shots toward a known provider."""
    if not provider or normalize_provider(provider) == "generic":
        return None
    caps = capabilities_for(provider)
    name = normalize_provider(provider)
    if not caps.get("video"):
        return {
            "code": "PROVIDER_CAPABILITY",
            "message": f"provider `{name}` cannot execute video shots; keep packet provider-neutral",
            "capabilities": caps,
        }
    if "min_duration_seconds" in caps and float(duration) < float(caps["min_duration_seconds"]):
        return {
            "code": "PROVIDER_CAPABILITY",
            "message": (
                f"shot duration {duration}s is below `{name}` minimum "
                f"{float(caps['min_duration_seconds'])}s"
            ),
            "capabilities": caps,
        }
    max_dur = float(caps.get("max_duration_seconds") or 0.0)
    if max_dur > 0 and float(duration) > max_dur:
        return {
            "code": "PROVIDER_CAPABILITY",
            "message": f"shot duration {duration}s exceeds `{name}` max {max_dur}s",
            "capabilities": caps,
        }
    if wants_camera_motion and not caps.get("camera_motion"):
        return {
            "code": "PROVIDER_CAPABILITY",
            "message": f"provider `{name}` does not declare camera motion support",
            "capabilities": caps,
        }
    return None
