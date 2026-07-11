from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

DEFAULT_POOL_NAME = "StandardKernels"


def default_config(kernel_path: str) -> dict[str, Any]:
    return {
        "AllowStealingKernels": False,
        "AllowSilentKernelReplacement": True,
        "EnableAutomaticKernelConnection": False,
        "SendInputNamePacketUponKernelConnection": True,
        "Pools": {
            DEFAULT_POOL_NAME: {
                "Default": True,
                "KernelPath": kernel_path,
                "KeepAlive": True,
                "MinimumKernelNumber": 2,
                "MaximumKernelNumber": 4,
            }
        },
    }


def _strip_hash_comments(text: str) -> str:
    """Remove WSTPServer-style # comments while preserving string contents."""
    result: list[str] = []
    in_string = False
    escaped = False
    index = 0

    while index < len(text):
        character = text[index]

        if in_string:
            result.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue

        if character == '"':
            in_string = True
            result.append(character)
            index += 1
            continue

        if character == "#":
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            continue

        result.append(character)
        index += 1

    return "".join(result)


def _strip_trailing_commas(text: str) -> str:
    """Remove commas before } or ] outside string contents."""
    result: list[str] = []
    in_string = False
    escaped = False
    index = 0

    while index < len(text):
        character = text[index]

        if in_string:
            result.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            index += 1
            continue

        if character == '"':
            in_string = True
            result.append(character)
            index += 1
            continue

        if character == ",":
            next_index = index + 1
            while next_index < len(text) and text[next_index].isspace():
                next_index += 1
            if next_index < len(text) and text[next_index] in "}]":
                index += 1
                continue

        result.append(character)
        index += 1

    return "".join(result)


def load_config(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8-sig")
    try:
        config = json.loads(text)
    except JSONDecodeError:
        config = json.loads(_strip_trailing_commas(_strip_hash_comments(text)))
    if not isinstance(config, dict):
        raise ValueError("WSTPServer config must be a JSON object")
    return config


def save_config(path: Path, config: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.tmp")
    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(config, file, indent=4)
        file.write("\n")
    temporary_path.replace(path)


def ensure_config(path: Path, kernel_path: str) -> bool:
    """Create a default WSTPServer config if missing.

    Returns True when a new file was created, False when an existing file was
    left untouched.
    """
    if path.exists() and path.stat().st_size > 0:
        return False
    save_config(path, default_config(kernel_path))
    return True


def pools(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_pools = config.setdefault("Pools", {})
    if not isinstance(raw_pools, dict):
        raise ValueError("Config key 'Pools' must be an object")
    return raw_pools


def first_pool(config: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    pool_map = pools(config)
    if not pool_map:
        pool_map[DEFAULT_POOL_NAME] = default_config("")["Pools"][DEFAULT_POOL_NAME]
    first_name = next(iter(pool_map))
    pool = pool_map[first_name]
    if not isinstance(pool, dict):
        raise ValueError(f"Pool '{first_name}' must be an object")
    return first_name, pool


def update_first_pool(
    path: Path,
    *,
    kernel_path: str,
    minimum_kernels: int,
    maximum_kernels: int,
    keep_alive: bool,
) -> None:
    if minimum_kernels > maximum_kernels:
        raise ValueError("Minimum kernels cannot be greater than maximum kernels")

    config = load_config(path) if path.exists() and path.stat().st_size > 0 else default_config(kernel_path)
    _, pool = first_pool(config)
    pool["KernelPath"] = kernel_path
    pool["MinimumKernelNumber"] = minimum_kernels
    pool["MaximumKernelNumber"] = maximum_kernels
    pool["KeepAlive"] = keep_alive
    save_config(path, config)
