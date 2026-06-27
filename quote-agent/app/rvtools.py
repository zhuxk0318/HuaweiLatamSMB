from __future__ import annotations

from io import BytesIO
from typing import Any

import pandas as pd

from app.models import ParsedVM, SheetSelection, SheetSelectionError, resolve_sheet_selection


class RvToolsParseError(ValueError):
    pass


# ── Column alias constants ──────────────────────────────────────────────────────

VM_NAME_COLUMNS = [
    "VM",
    "VM Name",
    "Name",
    "Equipo",
    "Server",
    "Servidor",
    "Hostname",
    "Host Name",
    "Nombre",
    "Servicio",
    "Service",
]

CUSTOMER_COLUMNS = ["Cliente", "Customer", "Client"]

WORKLOAD_COLUMNS = ["Tipo SAP", "Workload Type", "Application Type"]

CPU_COLUMNS = ["CPUs", "CPU", "vCPU", "vCPUs", "NumCpu", "Num CPU", "Num CPUs", "Cores", "Core", "Processor"]

MEMORY_GIB_COLUMNS = ["Memory in GiB", "Memory GB", "Memory GiB", "MemoryGB", "Mem", "RAM", "RAM GB", "Memoria", "Memoria GB"]

MEMORY_MIB_COLUMNS = ["Memory", "Memory MB", "Memory MiB", "Memory Mib", "Memory Size"]

STORAGE_GIB_COLUMNS = [
    "Total disk capacity GiB",
    "Total disk capacity GB",
    "Storage GB",
    "Storage(GB)",
    "HD",
    "Disk",
    "Disk GB",
    "Disco",
    "Storage",
    "Total Disk",
]

STORAGE_MIB_COLUMNS = [
    "Total disk capacity MiB",
    "Total disk capacity MB",
    "Capacity MiB",
    "Capacity MB",
]

OS_COLUMNS = ["OS according to the configuration file", "OS", "Guest OS", "S.O", "Sistema Operativo"]

POWER_STATE_COLUMNS = ["Powerstate", "Power State", "State"]

# Sheet names that suggest an inventory-like sheet (used as soft bonus)
_INVENTORY_SHEET_HINTS = {"filtrado", "filtered", "inventory"}


# ── Helpers ─────────────────────────────────────────────────────────────────────


def _normalize_key(value: Any) -> str:
    return "".join(ch for ch in str(value).strip().lower() if ch.isalnum())


def _normalized_column_candidates(value: Any) -> set[str]:
    raw = str(value).strip().lower()
    parts = [raw]
    if "." in raw:
        parts.extend(part.strip() for part in raw.split(".") if part.strip())
        parts.append(raw.split(".")[-1].strip())
    return {_normalize_key(part) for part in parts if part}


def _first_value(row: dict[str, Any], names: list[str]) -> Any:
    normalized: dict[str, Any] = {}
    for key, value in row.items():
        for candidate in _normalized_column_candidates(key):
            normalized.setdefault(candidate, value)
    for name in names:
        for candidate in _normalized_column_candidates(name):
            value = normalized.get(candidate)
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


# ── Inventory-like sheet detection ─────────────────────────────────────────────


def _has_any_column(frame: pd.DataFrame, aliases: list[str]) -> bool:
    """Return True if the DataFrame has any column matching one of the aliases."""
    available: set[str] = set()
    for col in frame.columns:
        available.update(_normalized_column_candidates(col))
    for alias in aliases:
        if any(candidate in available for candidate in _normalized_column_candidates(alias)):
            return True
    return False


def _inventory_frame_score(frame: pd.DataFrame) -> tuple[int, list[str]]:
    matched: list[str] = []
    if _has_any_column(frame, VM_NAME_COLUMNS):
        matched.append("vm")
    if _has_any_column(frame, CPU_COLUMNS):
        matched.append("cpu")
    if _has_any_column(frame, MEMORY_GIB_COLUMNS) or _has_any_column(frame, MEMORY_MIB_COLUMNS):
        matched.append("memory")
    if _has_any_column(frame, STORAGE_GIB_COLUMNS) or _has_any_column(frame, STORAGE_MIB_COLUMNS):
        matched.append("storage")
    return len(matched), matched


def _preview_columns(frame: pd.DataFrame, limit: int = 12) -> str:
    columns = [str(column) for column in frame.columns[:limit]]
    suffix = "" if len(frame.columns) <= limit else f", ... +{len(frame.columns) - limit} more"
    return ", ".join(columns) + suffix


def _make_unique_headers(values: list[Any]) -> list[str]:
    seen: dict[str, int] = {}
    headers: list[str] = []
    for index, value in enumerate(values):
        base = str(value).strip() if value not in (None, "") else f"Unnamed: {index}"
        count = seen.get(base, 0)
        seen[base] = count + 1
        headers.append(base if count == 0 else f"{base}_{count}")
    return headers


def _promote_header_row(frame: pd.DataFrame, row_index: int) -> pd.DataFrame | None:
    """Treat one of the first data rows as the real header for template-style sheets."""
    if row_index < 0 or row_index >= len(frame.index):
        return None
    header_values = frame.iloc[row_index].tolist()
    if all(value in (None, "") for value in header_values):
        return None
    promoted = frame.iloc[row_index + 1 :].copy()
    if promoted.empty:
        return None
    promoted.columns = _make_unique_headers(header_values)
    return promoted.reset_index(drop=True).fillna("")


def _inventory_candidate_frames(frame: pd.DataFrame) -> list[pd.DataFrame]:
    """Return candidate frames, including variants where an early row is promoted to header."""
    candidates: list[pd.DataFrame] = [frame.fillna("")]
    for row_index in range(min(3, len(frame.index))):
        promoted = _promote_header_row(frame, row_index)
        if promoted is not None:
            candidates.append(promoted)
    return candidates


def _is_inventory_like_frame(frame: pd.DataFrame) -> bool:
    """Score-based check: VM inventories need VM + CPU + memory; storage may be absent."""
    _score, matched = _inventory_frame_score(frame)
    required = {"vm", "cpu", "memory"}
    return required.issubset(set(matched))


def _workbook_inventory_diagnostics(
    workbook: dict[str, pd.DataFrame],
    selected_names: list[str],
) -> str:
    snippets: list[str] = []
    ordered_names = list(dict.fromkeys(selected_names + list(workbook.keys())))
    for sheet_name in ordered_names[:6]:
        frame = workbook.get(sheet_name)
        if frame is None or frame.empty:
            snippets.append(f"{sheet_name}: empty")
            continue
        best_score = -1
        best_matched: list[str] = []
        best_columns = ""
        for candidate in _inventory_candidate_frames(frame):
            score, matched = _inventory_frame_score(candidate)
            if score > best_score:
                best_score = score
                best_matched = matched
                best_columns = _preview_columns(candidate)
        snippets.append(f"{sheet_name}: matched={best_matched or []}; columns=[{best_columns}]")
    return " Sheets scanned: " + " | ".join(snippets) if snippets else ""


def _find_inventory_sheet(
    workbook: dict[str, pd.DataFrame],
    selected_names: list[str],
) -> tuple[str, pd.DataFrame] | None:
    """Find the best inventory-like sheet. Prefer selected sheets, then all sheets.
    Within each group, prefer sheets whose name hints inventory (filtrado/filtered/inventory).
    Returns (sheet name, normalized frame) or None.
    """
    # Search selected sheets first, then all sheets
    for candidates in [selected_names, list(workbook.keys())]:
        hint_matches: list[tuple[str, pd.DataFrame]] = []
        other_matches: list[tuple[str, pd.DataFrame]] = []
        for name in candidates:
            frame = workbook.get(name)
            if frame is None or frame.empty:
                continue
            for candidate in _inventory_candidate_frames(frame):
                if not _is_inventory_like_frame(candidate):
                    continue
                if name.strip().lower() in _INVENTORY_SHEET_HINTS:
                    hint_matches.append((name, candidate))
                else:
                    other_matches.append((name, candidate))
                break
        if hint_matches:
            return hint_matches[0]
        if other_matches:
            return other_matches[0]
    return None


# ── Non-standard inventory parser ──────────────────────────────────────────────


def _parse_inventory_sheet(
    info_frame: pd.DataFrame,
    sheet_name: str,
) -> list[ParsedVM]:
    """Parse an inventory-like sheet (no vInfo/vDisk structure) into ParsedVM list."""
    rows = info_frame.fillna("").to_dict(orient="records")
    parsed: list[ParsedVM] = []
    for index, row in enumerate(rows, start=1):
        vm_name = str(_first_value(row, VM_NAME_COLUMNS) or f"VM-{index}").strip()
        if not vm_name:
            vm_name = f"VM-{index}"

        # CPU
        vcpu = int(_to_number(_first_value(row, CPU_COLUMNS)))

        # Memory: prefer GiB column, fall back to MiB/MB → GiB
        memory_gib_val = _first_value(row, MEMORY_GIB_COLUMNS)
        raw_memory_mb_val = _first_value(row, MEMORY_MIB_COLUMNS)
        if memory_gib_val is not None:
            memory_gib = round(_to_number(memory_gib_val), 2)
        elif raw_memory_mb_val is not None:
            memory_gib = round(_to_number(raw_memory_mb_val) / 1024, 2)
        else:
            memory_gib = 0.0

        # Storage: prefer GiB column, fall back to MiB → GiB
        storage_gib_val = _first_value(row, STORAGE_GIB_COLUMNS)
        raw_storage_mib_val = _first_value(row, STORAGE_MIB_COLUMNS)
        if storage_gib_val is not None:
            disk_gib = round(_to_number(storage_gib_val), 2)
        elif raw_storage_mib_val is not None:
            disk_gib = round(_to_number(raw_storage_mib_val) / 1024, 2)
        else:
            disk_gib = 0.0

        # OS
        os_val = str(_first_value(row, OS_COLUMNS) or "").strip()

        # Power state: if absent, leave empty (don't default to poweredOff)
        power_val = str(_first_value(row, POWER_STATE_COLUMNS) or "").strip()

        # Customer / workload
        customer = str(_first_value(row, CUSTOMER_COLUMNS) or "").strip() or None
        workload_type = str(_first_value(row, WORKLOAD_COLUMNS) or "").strip() or None

        # raw_memory_mb: preserve original MiB/MB value if available
        raw_memory_mb = _to_number(raw_memory_mb_val) if raw_memory_mb_val is not None else None
        # raw_storage_mib: preserve original MiB value if available
        raw_storage_mib = _to_number(raw_storage_mib_val) if raw_storage_mib_val is not None else None

        parsed.append(
            ParsedVM(
                vm_name=vm_name,
                power_state=power_val,
                os=os_val,
                vcpu=vcpu,
                memory_gib=memory_gib,
                disk_gib=disk_gib,
                customer=customer,
                workload_type=workload_type,
                source_sheet=sheet_name,
                raw_memory_mb=raw_memory_mb,
                raw_storage_mib=raw_storage_mib,
            )
        )
    return parsed


# ── Main parser ────────────────────────────────────────────────────────────────


def parse_rvtools_workbook(
    file_bytes: bytes,
    sheet_selection: SheetSelection | None = None,
) -> tuple[list[ParsedVM], list[dict[str, Any]], list[dict[str, Any]]]:
    workbook = pd.read_excel(BytesIO(file_bytes), sheet_name=None)
    all_sheet_names = list(workbook.keys())

    if sheet_selection is None:
        sheet_selection = SheetSelection()

    try:
        selected_names = resolve_sheet_selection(all_sheet_names, sheet_selection)
    except SheetSelectionError as exc:
        raise RvToolsParseError(str(exc)) from exc

    # Find vInfo-like and vDisk-like sheets among the selected sheets
    info_sheet_name = next((name for name in selected_names if name.lower() == "vinfo" or "vinfo" in name.lower()), None)
    disk_sheet_name = next((name for name in selected_names if name.lower() == "vdisk" or "vdisk" in name.lower()), None)

    # If no vInfo found in selected sheets, fall back to searching all sheets
    # (RVTools exports always have vInfo; user may not have selected it explicitly)
    if not info_sheet_name:
        info_sheet_name = next((name for name in all_sheet_names if name.lower() == "vinfo" or "vinfo" in name.lower()), None)
    if not disk_sheet_name:
        disk_sheet_name = next((name for name in all_sheet_names if name.lower() == "vdisk" or "vdisk" in name.lower()), None)

    # ── Standard RVTools path (vInfo found) ─────────────────────────────────
    if info_sheet_name:
        info_frame = workbook[info_sheet_name].fillna("")
        disk_frame = workbook[disk_sheet_name].fillna("") if disk_sheet_name else pd.DataFrame()

        info_rows = info_frame.to_dict(orient="records")
        disk_rows = disk_frame.to_dict(orient="records") if not disk_frame.empty else []

        disk_by_vm: dict[str, float] = {}
        for row in disk_rows:
            vm_name = str(_first_value(row, VM_NAME_COLUMNS) or "").strip()
            if not vm_name:
                continue
            disk_by_vm[vm_name] = disk_by_vm.get(vm_name, 0.0) + _disk_to_gib(row)

        parsed: list[ParsedVM] = []
        for index, row in enumerate(info_rows, start=1):
            vm_name = str(_first_value(row, VM_NAME_COLUMNS) or f"VM-{index}").strip()
            parsed.append(
                ParsedVM(
                    vm_name=vm_name,
                    power_state=str(_first_value(row, POWER_STATE_COLUMNS) or "").strip(),
                    os=str(_first_value(row, OS_COLUMNS) or "").strip(),
                    vcpu=int(_to_number(_first_value(row, CPU_COLUMNS))),
                    memory_gib=round(
                        _memory_to_gib(
                            _first_value(row, MEMORY_MIB_COLUMNS)
                        ),
                        2,
                    ),
                    disk_gib=round(disk_by_vm.get(vm_name, 0.0), 2),
                    source_sheet=info_sheet_name,
                )
            )

        return parsed, info_rows, disk_rows

    # ── Non-standard inventory path (no vInfo, try inventory-like sheet) ────
    inventory_match = _find_inventory_sheet(workbook, selected_names)
    if inventory_match:
        inventory_sheet, info_frame = inventory_match
        parsed = _parse_inventory_sheet(info_frame, inventory_sheet)
        info_rows = info_frame.fillna("").to_dict(orient="records")
        return parsed, info_rows, []

    # ── Nothing usable found ────────────────────────────────────────────────
    diagnostics = _workbook_inventory_diagnostics(workbook, selected_names)
    raise RvToolsParseError(
        "No vInfo sheet or inventory-like sheet with VM/CPU/Memory columns was found."
        f"{diagnostics}"
    )
