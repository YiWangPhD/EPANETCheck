"""Load an EPANET network and its existing binary results."""

from __future__ import annotations

import tempfile
from pathlib import Path

import wntr


def _without_rules(source: Path) -> str:
    lines = source.read_text(encoding="utf-8", errors="ignore").splitlines(keepends=True)
    output: list[str] = []
    in_rules = False
    for line in lines:
        stripped = line.strip()
        if stripped.upper() == "[RULES]":
            in_rules = True
            continue
        if in_rules and stripped.startswith("[") and stripped.endswith("]"):
            in_rules = False
        if not in_rules:
            output.append(line)
    return "".join(output)


def load_network(inp_file: Path):
    """Load a network through a temporary RULES-free copy."""
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".inp", encoding="utf-8", delete=False
        ) as stream:
            stream.write(_without_rules(inp_file))
            temp_path = Path(stream.name)
        return wntr.network.WaterNetworkModel(str(temp_path))
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def load_model_and_results(inp_file: Path, result_file: Path):
    network = load_network(inp_file)
    results = wntr.epanet.io.BinFile().read(str(result_file), network)
    return network, results
