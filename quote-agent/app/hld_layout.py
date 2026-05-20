"""Deterministic layout helpers for HLD architecture diagrams.

Provides layout constants, node box measurement, grid layout, container
size computation, and edge anchor routing — all used by hld_workflow.py
to produce non-overlapping draw.io XML.
"""
from __future__ import annotations

from app.hwc_drawio_library import resolve_hwc_icon
from app.hwc_icon_mapping import resolve_product_icon_title

# ── Layout constants ──────────────────────────────────────────────────────

# Icon node bounding box (icon image + label area below)
ICON_IMAGE_SIZE = 60
ICON_BOX_WIDTH = 120
ICON_BOX_HEIGHT = 110

# Generic (fallback) shape node size
NODE_WIDTH = 160
NODE_HEIGHT = 50

# Spacing between nodes in a row / between rows
NODE_GAP_X = 36
NODE_GAP_Y = 28

# Container internal padding (space from container edge to first child)
CONTAINER_PADDING_X = 24
CONTAINER_PADDING_Y = 24

# Extra gap between container title band and first child
CONTAINER_TITLE_GAP = 12

# Logical group (AZ, AS Group, AS Policy) extra padding
GROUP_PADDING_X = 20
GROUP_PADDING_Y = 18

# Minimum container dimensions
MIN_CONTAINER_W = 300
MIN_CONTAINER_H = 80

# Edge anchor offsets (fraction of node width/height)
# Used to pick connection points that avoid crossing node centers
ANCHOR_TOP = 0.5, 0.0
ANCHOR_BOTTOM = 0.5, 1.0
ANCHOR_LEFT = 0.0, 0.5
ANCHOR_RIGHT = 1.0, 0.5

# Max columns per row in a subnet before wrapping
DEFAULT_MAX_COLS = 5

# Subnet layer ordering: lower rank = rendered higher (top)
# Labels are matched case-insensitively against these keywords
SUBNET_LAYER_RANKS: list[tuple[str, int]] = [
    ("public", 0),
    ("frontend", 0),
    ("web", 0),
    ("dmz", 0),
    ("app", 1),
    ("application", 1),
    ("middle", 1),
    ("data", 2),
    ("db", 2),
    ("database", 2),
    ("storage", 2),
    ("mgmt", 3),
    ("management", 3),
    ("admin", 3),
]


def subnet_layer_rank(label: str) -> int:
    """Return a rank for subnet vertical ordering (lower = higher on page).

    Matches the label (case-insensitive) against known subnet keywords.
    Unmatched labels get rank 4 (rendered last / lowest).
    """
    low = label.lower()
    for keyword, rank in SUBNET_LAYER_RANKS:
        if keyword in low:
            return rank
    return 4


# ── Node box measurement ──────────────────────────────────────────────────

def measure_node_box(node: dict) -> tuple[int, int]:
    """Return (width, height) of the layout box for a node.

    Icon nodes use ICON_BOX_WIDTH x ICON_BOX_HEIGHT (icon + label).
    Fallback shape nodes use NODE_WIDTH x NODE_HEIGHT.
    """
    product = node.get("product")
    icon_title = resolve_product_icon_title(product) if product else None
    has_icon = bool(icon_title and resolve_hwc_icon(icon_title))
    if has_icon:
        return ICON_BOX_WIDTH, ICON_BOX_HEIGHT
    return NODE_WIDTH, NODE_HEIGHT


# ── Grid layout ───────────────────────────────────────────────────────────

def layout_nodes_in_grid(
    nodes: list[dict],
    *,
    area_width: int = 0,
    max_cols: int = DEFAULT_MAX_COLS,
    start_x: int = 0,
    start_y: int = 0,
    gap_x: int = NODE_GAP_X,
    gap_y: int = NODE_GAP_Y,
) -> list[tuple[dict, int, int, int, int]]:
    """Place nodes in a left-to-right, top-to-bottom grid.

    Returns list of (node, x, y, w, h) tuples.  Each (x, y) is the
    top-left of the node's layout box relative to (start_x, start_y).
    """
    if not nodes:
        return []

    placed: list[tuple[dict, int, int, int, int]] = []
    cur_x = start_x
    cur_y = start_y
    col = 0

    for n in nodes:
        nw, nh = measure_node_box(n)
        placed.append((n, cur_x, cur_y, nw, nh))
        col += 1
        cur_x += nw + gap_x

        # Wrap to next row
        if col >= max_cols or (area_width > 0 and cur_x + nw > area_width):
            cur_x = start_x
            cur_y += nh + gap_y
            col = 0

    return placed


# ── Container size computation ────────────────────────────────────────────

def compute_container_size(
    ctype: str,
    child_container_sizes: list[tuple[int, int]],
    child_nodes: list[dict],
    *,
    is_lr: bool = False,
    start_size: int = 26,
    max_cols: int = DEFAULT_MAX_COLS,
) -> tuple[int, int]:
    """Compute (width, height) for a container from its children.

    - child_container_sizes: list of (w, h) for nested containers
    - child_nodes: list of node dicts placed directly in this container
    - is_lr: True for deployment_vertical (LR layout)
    - start_size: header bar height for this container type
    """
    header_h = start_size + CONTAINER_TITLE_GAP  # header + gap below title band

    # --- Child containers contribution ---
    if not child_container_sizes and not child_nodes:
        return MIN_CONTAINER_W, MIN_CONTAINER_H

    if is_lr:
        # LR: stack child containers vertically
        child_total_h = sum(s[1] for s in child_container_sizes) + len(child_container_sizes) * CONTAINER_PADDING_Y
        child_max_w = max((s[0] for s in child_container_sizes), default=0)
    else:
        # TB: stack child containers horizontally
        child_total_w = sum(s[0] for s in child_container_sizes) + max(0, len(child_container_sizes) - 1) * CONTAINER_PADDING_X
        child_max_h = max((s[1] for s in child_container_sizes), default=0)

    # --- Direct child nodes contribution ---
    if child_nodes:
        # Lay out nodes in a grid to measure bounding box
        grid = layout_nodes_in_grid(child_nodes, max_cols=max_cols, start_x=0, start_y=0)
        if grid:
            max_right = max(x + w for _, x, y, w, h in grid)
            max_bottom = max(y + h for _, x, y, w, h in grid)
            nodes_w = max_right + CONTAINER_PADDING_X
            nodes_h = max_bottom + CONTAINER_PADDING_Y
        else:
            nodes_w = 0
            nodes_h = 0
    else:
        nodes_w = 0
        nodes_h = 0

    # --- Merge ---
    is_group = ctype in ("az", "as_group", "as_policy")
    pad_x = CONTAINER_PADDING_X + (GROUP_PADDING_X if is_group else 0)
    pad_y = CONTAINER_PADDING_Y + (GROUP_PADDING_Y if is_group else 0)

    if is_lr:
        # LR: child containers stacked vertically, nodes below them
        content_w = max(child_max_w if child_container_sizes else 0, nodes_w)
        content_h = (child_total_h if child_container_sizes else 0) + nodes_h
        w = max(content_w + 2 * pad_x, MIN_CONTAINER_W)
        h = max(header_h + content_h + pad_y, MIN_CONTAINER_H)
    else:
        # TB: child containers stacked horizontally, nodes placed below them
        child_w = child_total_w if child_container_sizes else 0
        child_h = child_max_h if child_container_sizes else 0
        # Width must fit both child containers row and node grid
        content_w = max(child_w, nodes_w)
        # Height: child containers + nodes below
        content_h = child_h + nodes_h
        w = max(content_w + 2 * pad_x, MIN_CONTAINER_W)
        h = max(header_h + content_h + pad_y, MIN_CONTAINER_H)

    return w, h


# ── Edge anchor routing ───────────────────────────────────────────────────

def route_edge_anchors(
    src_box: tuple[int, int, int, int],
    tgt_box: tuple[int, int, int, int],
) -> tuple[str, str]:
    """Pick exit/entry style hints for an edge between two node boxes.

    Each box is (x, y, w, h).  Returns (exit_hint, entry_hint) where
    each hint is a drawio style fragment like "exitX=0.5;exitY=1.0;"
    or an empty string for default.

    Heuristic:
    - If target is mostly below source → source exits bottom, target enters top
    - If target is mostly right of source → source exits right, target enters left
    - Otherwise fall back to defaults (drawio orthogonal routing)
    """
    sx, sy, sw, sh = src_box
    tx, ty, tw, th = tgt_box

    src_cx = sx + sw / 2
    src_cy = sy + sh / 2
    tgt_cx = tx + tw / 2
    tgt_cy = ty + th / 2

    dx = tgt_cx - src_cx
    dy = tgt_cy - src_cy

    # If vertical distance dominates → top/bottom routing
    if abs(dy) > abs(dx) * 0.6:
        if dy > 0:
            return "exitX=0.5;exitY=1.0;exitDx=0;exitDy=0;", "entryX=0.5;entryY=0.0;entryDx=0;entryDy=0;"
        else:
            return "exitX=0.5;exitY=0.0;exitDx=0;exitDy=0;", "entryX=0.5;entryY=1.0;entryDx=0;entryDy=0;"

    # If horizontal distance dominates → left/right routing
    if abs(dx) > abs(dy) * 0.6:
        if dx > 0:
            return "exitX=1.0;exitY=0.5;exitDx=0;exitDy=0;", "entryX=0.0;entryY=0.5;entryDx=0;entryDy=0;"
        else:
            return "exitX=0.0;exitY=0.5;exitDx=0;exitDy=0;", "entryX=1.0;entryY=0.5;entryDx=0;entryDy=0;"

    # Default: still emit explicit anchors to avoid draw.io auto-routing.
    if abs(dy) >= abs(dx):
        if dy >= 0:
            return "exitX=0.5;exitY=1.0;exitDx=0;exitDy=0;", "entryX=0.5;entryY=0.0;entryDx=0;entryDy=0;"
        return "exitX=0.5;exitY=0.0;exitDx=0;exitDy=0;", "entryX=0.5;entryY=1.0;entryDx=0;entryDy=0;"
    if dx >= 0:
        return "exitX=1.0;exitY=0.5;exitDx=0;exitDy=0;", "entryX=0.0;entryY=0.5;entryDx=0;entryDy=0;"
    return "exitX=0.0;exitY=0.5;exitDx=0;exitDy=0;", "entryX=1.0;entryY=0.5;entryDx=0;entryDy=0;"


# ── Overlap checking (for tests) ──────────────────────────────────────────

def boxes_overlap(
    a: tuple[int, int, int, int],
    b: tuple[int, int, int, int],
    *,
    tolerance: int = 0,
) -> bool:
    """Return True if boxes a and b overlap (with optional tolerance)."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return (
        ax - tolerance < bx + bw
        and bx - tolerance < ax + aw
        and ay - tolerance < by + bh
        and by - tolerance < ay + ah
    )
