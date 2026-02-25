from __future__ import annotations

import json
from typing import Any, Literal

import yaml
from rich.console import Console
from rich.table import Table

from rsspot.utils.serialization import to_plain_data

OutputFormat = Literal["json", "yaml", "table"]


def emit(value: Any, *, output: OutputFormat = "json") -> None:
    """Render SDK/CLI output as json, yaml, or table."""

    plain = to_plain_data(value)
    if output == "json":
        print(json.dumps(plain, indent=2))
        return
    if output == "yaml":
        print(yaml.safe_dump(plain, sort_keys=False))
        return

    console = Console()
    if isinstance(plain, list) and plain and all(isinstance(item, dict) for item in plain):
        keys: list[str] = []
        for row in plain:
            assert isinstance(row, dict)
            for key in row:
                key_str = str(key)
                if key_str not in keys:
                    keys.append(key_str)
        table = Table(show_header=True, header_style="bold")
        for key in keys:
            table.add_column(key)
        for row in plain:
            assert isinstance(row, dict)
            table.add_row(*[str(row.get(key, "")) for key in keys])
        console.print(table)
        return

    if isinstance(plain, dict):
        table = Table(show_header=True, header_style="bold")
        table.add_column("key")
        table.add_column("value")
        for key, val in plain.items():
            table.add_row(str(key), str(val))
        console.print(table)
        return

    console.print(str(plain))
