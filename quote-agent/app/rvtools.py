from __future__ import annotations

from io import BytesIO
from typing import Any

import pandas as pd

from app.models import ParsedVM


class RvToolsParseError(ValueError):
    pass


def _normalize_key(value: Any) -> str:
    return "".join(ch for ch in str(value).strip().lower() if ch.isalnum())


def _first_value(row: dict[str, Any], names: list[str]) -> Any:
    normalized = {_normalize_key(key): value for key, value in row.items()}
    for name in names:
        value = normalized.get(_normalize_key(name))
        if value not in (None, ""):
            return value
    return None


def _to_number(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "")
    current = []
    for char in text:
        if char.isdigit() or char in ".-":
            current.append(char)
        elif current:
            break
    try:
        return float("".join(current))
    except ValueError:
        return 0.0


def _memory_to_gib(value: Any) -> float:
    numeric = _to_number(value)
    return numeric / 1024 if numeric > 512 else numeric


def _disk_to_gib(row: dict[str, Any]) -> float:
    for field in ["Capacity GiB", "Capacity GB", "Provisioned GB", "Capacity MiB", "Capacity MB", "Capacity"]:
        value = _first_value(row, [field])
        if value is None:
            continue
        numeric = _to_number(value)
        if "mib" in field.lower() or field.lower().endswith("mb"):
            return numeric / 1024
        return numeric / 1024 if numeric > 4096 else numeric
    return 0.0


def parse_rvtools_workbook(file_bytes: bytes) -> tuple[list[ParsedVM], list[dict[str, Any]], list[dict[str, Any]]]:
    workbook = pd.read_excel(BytesIO(file_bytes), sheet_name=None)
    info_sheet_name = next((name for name in workbook if name.lower() == "vinfo" or "vinfo" in name.lower()), None)
    disk_sheet_name = next((name for name in workbook if name.lower() == "vdisk" or "vdisk" in name.lower()), None)

    if not info_sheet_name:
        raise RvToolsParseError("RVTools vInfo sheet was not found.")

    info_frame = workbook[info_sheet_name].fillna("")
    disk_frame = workbook[disk_sheet_name].fillna("") if disk_sheet_name else pd.DataFrame()

    info_rows = info_frame.to_dict(orient="records")
    disk_rows = disk_frame.to_dict(orient="records") if not disk_frame.empty else []

    disk_by_vm: dict[str, float] = {}
    for row in disk_rows:
        vm_name = str(_first_value(row, ["VM", "VM Name", "Name"]) or "").strip()
        if not vm_name:
            continue
        disk_by_vm[vm_name] = disk_by_vm.get(vm_name, 0.0) + _disk_to_gib(row)

    parsed: list[ParsedVM] = []
    for index, row in enumerate(info_rows, start=1):
        vm_name = str(_first_value(row, ["VM", "VM Name", "Name"]) or f"VM-{index}").strip()
        parsed.append(
            ParsedVM(
                vm_name=vm_name,
                power_state=str(_first_value(row, ["Powerstate", "Power State", "State"]) or "").strip(),
                os=str(_first_value(row, ["OS according to the configuration file", "OS", "Guest OS"]) or "").strip(),
                vcpu=int(_to_number(_first_value(row, ["CPUs", "NumCpu", "Num CPU", "Num CPUs", "vCPU", "vCPUs"]))),
                memory_gib=round(
                    _memory_to_gib(
                        _first_value(row, ["Memory", "Memory MB", "Memory MiB", "Memory Mib", "Memory Size"])
                    ),
                    2,
                ),
                disk_gib=round(disk_by_vm.get(vm_name, 0.0), 2),
            )
        )

    return parsed, info_rows, disk_rows
