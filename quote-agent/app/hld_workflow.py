"""HLD architecture diagram generation workflow.

Pipeline: structured requirements -> LLM generates architecture spec JSON
-> deterministic render to .drawio XML -> draw.io CLI exports PNG -> repair PNG.
"""
from __future__ import annotations

import grp
import httpx
import json
import logging
import os
import pwd
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path
from typing import Callable

from app.chat_service import ChatCompletionsClient, build_chat_client_from_env
from app.hwc_drawio_library import build_icon_svg_data_uri, resolve_hwc_icon
from app.hwc_icon_mapping import resolve_product_icon_title
from app.hld_layout import (
    ICON_IMAGE_SIZE,
    ICON_BOX_WIDTH,
    ICON_BOX_HEIGHT,
    NODE_WIDTH as LAYOUT_NODE_WIDTH,
    NODE_HEIGHT as LAYOUT_NODE_HEIGHT,
    NODE_GAP_X,
    NODE_GAP_Y,
    CONTAINER_PADDING_X,
    CONTAINER_PADDING_Y,
    CONTAINER_TITLE_GAP,
    GROUP_PADDING_X,
    GROUP_PADDING_Y,
    MIN_CONTAINER_W,
    MIN_CONTAINER_H,
    DEFAULT_MAX_COLS,
    measure_node_box,
    layout_nodes_in_grid,
    compute_container_size,
    route_edge_anchors,
    subnet_layer_rank,
)
from app.models import HldRequirements

logger = logging.getLogger(__name__)

VENDOR_DIR = Path(__file__).resolve().parent.parent / "vendor" / "drawio-skill"
ARTIFACTS_ROOT = Path(tempfile.gettempdir()) / "hld-designs"

# --- Export concurrency ---
EXPORT_SEMAPHORE = threading.Semaphore(2)

# --- Non-root user for drawio export ---
HLD_RENDER_USER = "hld-render"

def _get_render_user_ids() -> tuple[int, int] | None:
    """Return (uid, gid) for the hld-render user, or None if not available."""
    try:
        pw = pwd.getpwnam(HLD_RENDER_USER)
        gr = grp.getgrgid(pw.pw_gid)
        return pw.pw_uid, gr.gr_gid
    except KeyError:
        return None


def ensure_render_user_home() -> None:
    """Ensure the render user's HOME and XDG dirs exist and are owned correctly."""
    ids = _get_render_user_ids()
    if ids is None:
        return
    uid, gid = ids
    try:
        pw = pwd.getpwnam(HLD_RENDER_USER)
    except KeyError:
        return

    home = Path(pw.pw_dir)
    dirs = [
        home,
        home / ".config",
        home / ".cache",
        home / ".local",
        home / ".local" / "share",
    ]
    for path in dirs:
        path.mkdir(parents=True, exist_ok=True)
        try:
            os.chown(path, uid, gid)
            os.chmod(path, 0o700)
        except OSError as exc:
            logger.warning("Failed to set ownership on render home path %s: %s", path, exc)

# --- Node type -> (shape style prefix, role for color lookup) ---
NODE_TYPE_MAP: dict[str, tuple[str, str]] = {
    "user": ("rounded=1;whiteSpace=wrap;html=1;", "neutral"),
    "service": ("rounded=1;whiteSpace=wrap;html=1;", "primary"),
    "database": ("shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;backgroundOutline=1;", "success"),
    "queue": ("rounded=1;whiteSpace=wrap;html=1;", "warning"),
    "gateway": ("rhombus;whiteSpace=wrap;html=1;", "accent"),
    "external": ("rounded=1;whiteSpace=wrap;html=1;dashed=1;", "neutral"),
    "network_zone": ("rounded=1;whiteSpace=wrap;html=1;dashed=1;dashPattern=8 8;", "secondary"),
}

VALID_NODE_TYPES = set(NODE_TYPE_MAP.keys())

# --- Template-driven HLD ---
VALID_TEMPLATES = ("layered_horizontal", "deployment_vertical")
VALID_CONTAINER_TYPES = ("region", "vpc", "subnet", "az", "as_group", "as_policy")
VALID_EDGE_KINDS = ("traffic", "management", "replication", "notification")

# Container type -> visual semantics for drawio rendering
CONTAINER_STYLE_MAP: dict[str, dict[str, str]] = {
    "region":     {"outline": "#c0392b", "fill": "#fdf2f2", "fontStyle": "1", "dashed": "0",   "dashPattern": "",      "startSize": "30", "strokeWidth": "2"},
    "vpc":        {"outline": "#E85D4D", "fill": "#FFE6E6", "fontStyle": "1", "dashed": "0",   "dashPattern": "",      "startSize": "28", "strokeWidth": "2"},
    "subnet":     {"outline": "#7ED321", "fill": "#E6F7E6", "fontStyle": "1", "dashed": "0",   "dashPattern": "",      "startSize": "26", "strokeWidth": "2"},
    "az":         {"outline": "#4A90E2", "fill": "#eaf2f8", "fontStyle": "0", "dashed": "1",   "dashPattern": "5 5",   "startSize": "24", "strokeWidth": "1"},
    "as_group":   {"outline": "#4A90E2", "fill": "#eaf2f8", "fontStyle": "0", "dashed": "1",   "dashPattern": "5 5",   "startSize": "24", "strokeWidth": "1"},
    "as_policy":  {"outline": "#4A90E2", "fill": "#eaf2f8", "fontStyle": "0", "dashed": "1",   "dashPattern": "5 5",   "startSize": "24", "strokeWidth": "1"},
}

# edge_kind -> drawio style overrides
EDGE_KIND_STYLE_MAP: dict[str, dict[str, str]] = {
    "traffic":       {"dashed": "0", "dashPattern": "",      "strokeColor": "#333333"},
    "management":    {"dashed": "1", "dashPattern": "5 5",   "strokeColor": "#333333"},
    "replication":   {"dashed": "1", "dashPattern": "5 5",   "strokeColor": "#333333"},
    "notification":  {"dashed": "1", "dashPattern": "5 5",   "strokeColor": "#8e44ad"},
}

MAX_NODES = 15
MAX_EDGES = 20
MAX_LABEL_LEN = 30

# --- Layout constants (re-exported from hld_layout for backward compat) ---
LAYER_WIDTH = 900
LAYER_HEIGHT = 60
NODE_WIDTH = LAYOUT_NODE_WIDTH
NODE_HEIGHT = LAYOUT_NODE_HEIGHT
ICON_SIZE = ICON_IMAGE_SIZE
ICON_LABEL_FONT_SIZE = 14
LAYER_PADDING_X = CONTAINER_PADDING_X
LAYER_PADDING_Y = CONTAINER_PADDING_Y
DIAGRAM_MARGIN = 40
MAX_RENDER_EDGES = 12
EDGE_WAYPOINT_CLEARANCE = 30
EXTERNAL_NOTE_GAP = 40
EXTERNAL_NOTE_WIDTH = 220


# ── Vendor resource loading ──────────────────────────────────────────────

@lru_cache(maxsize=8)
def _load_vendor_text(relative_path: str) -> str:
    path = VENDOR_DIR / relative_path
    return path.read_text(encoding="utf-8")


@lru_cache(maxsize=4)
def _load_vendor_json(relative_path: str) -> dict:
    return json.loads(_load_vendor_text(relative_path))


def _load_style_preset() -> dict:
    return _load_vendor_json("styles/built-in/corporate.json")


def _load_diagram_types_ref() -> str:
    return _load_vendor_text("references/diagram-types.md")


# ── CLI validation ───────────────────────────────────────────────────────

def validate_drawio_cli() -> str:
    """Return the draw.io CLI command name, or raise RuntimeError."""
    for cmd in ("drawio", "draw.io"):
        if shutil.which(cmd):
            logger.info("draw.io CLI found: %s", cmd)
            return cmd
    raise RuntimeError(
        "draw.io CLI not found on PATH. Install draw.io desktop and ensure "
        "'drawio' or 'draw.io' is on PATH."
    )


def validate_xvfb() -> None:
    """Raise RuntimeError if xvfb-run is not available on Linux."""
    if os.name != "posix":
        return
    if not shutil.which("xvfb-run"):
        raise RuntimeError(
            "xvfb-run not found on PATH. Install xvfb package for headless "
            "draw.io export on Linux."
        )


# ── Orphan artifact cleanup ─────────────────────────────────────────────

def cleanup_orphan_artifacts() -> None:
    """Remove artifact directories older than TTL that aren't in the current task table.

    Should be called once at service startup.
    """
    if not ARTIFACTS_ROOT.exists():
        return
    cutoff = os.path.getmtime  # not used directly; we check dir age
    import time as _time
    now = _time.time()
    for entry in ARTIFACTS_ROOT.iterdir():
        if not entry.is_dir():
            continue
        try:
            age = now - entry.stat().st_mtime
            if age > TASK_TTL_SECONDS:
                shutil.rmtree(entry, ignore_errors=True)
                logger.info("Cleaned orphan artifact dir: %s", entry)
        except OSError:
            pass


# Need TASK_TTL_SECONDS for orphan cleanup — import from hld_tasks lazily to
# avoid circular import. We define a default here and override at startup.
TASK_TTL_SECONDS = 1800


# ── LLM prompt construction ─────────────────────────────────────────────

ARCHITECTURE_SPEC_SCHEMA = """\
{
  "title": "string",
  "diagram_type": "architecture",
  "template": "layered_horizontal | deployment_vertical",
  "layout": "TB | LR",
  "containers": [
    {"id": "string", "label": "string", "container_type": "region|vpc|subnet|az|as_group|as_policy", "parent_id": "string|null"}
  ],
  "nodes": [
    {"id": "string", "label": "string", "type": "user|service|database|queue|gateway|external|network_zone", "container_id": "string", "product": "string"}
  ],
  "edges": [
    {"source": "string", "target": "string", "label": "string|null", "edge_kind": "traffic|management|replication|notification"}
  ]
}
Hierarchy rules:
- containers must form a valid tree: exactly one root container with container_type="region"
- region contains one or more vpc containers
- vpc contains one or more subnet containers
- az, as_group, as_policy are optional and nest inside a subnet
- external/user nodes must NOT be inside a region (container_id must be null or reference a container outside region)
- database nodes must be inside a subnet whose label contains "data" or "db"
- template="layered_horizontal": conceptual multi-tier (Internet/Ingress → Frontend → Application → Data), use subnet names like "External Subnet", "Frontend Subnet", "Application Subnet", "Data Subnet"
- template="deployment_vertical": concrete deployment (Region → VPC → web/app tier → db tier), use resource-role names like "elb-web", "ecs-web", "rds-web Primary"
Layout rules:
- layout: use "TB" for layered_horizontal, "LR" for deployment_vertical
- Keep labels concise (max 30 chars)
- Maximum 15 nodes and 20 edges for readability
- edge_kind: "traffic" for request/data flow, "management" for admin/ops access, "replication" for HA/DR sync, "notification" for event/integration paths
Icon rules:
- Every non-external node MUST have a "product" field with a standard Huawei Cloud service name (e.g. "ECS", "RDS", "ELB", "OBS", "CCE", "WAF", "NAT Gateway", "EIP", "SMN", "VPC", "DCS", "DMS", "CBR", "CES", "CTS", "KMS")
- Use the short product name as the product value (e.g. "ECS" not "Elastic Cloud Server")
- The product field drives icon rendering — nodes without a valid product will use a generic fallback shape
"""


def _normalize_text_field(value: str) -> list[str]:
    """Split a comma-or-slash-separated text field into a list of trimmed items."""
    parts = re.split(r"[,;/]\s*", value)
    return [p.strip() for p in parts if p.strip()]


def build_hld_prompt(requirements: HldRequirements, style_preset: dict) -> list[dict[str, str]]:
    """Build LLM messages for generating a constrained architecture spec JSON."""
    diagram_ref = _load_diagram_types_ref()
    arch_section = diagram_ref
    arch_marker = "### Architecture"
    if arch_marker in diagram_ref:
        arch_section = diagram_ref[diagram_ref.index(arch_marker):]
        next_h3 = arch_section.find("\n### ", 4)
        if next_h3 > 0:
            arch_section = arch_section[:next_h3]

    core_list = _normalize_text_field(requirements.core_components)
    ext_list = _normalize_text_field(requirements.external_integrations)
    data_list = _normalize_text_field(requirements.data_stores_flow)

    # Auto-select template based on deployment mode
    template_hint = "deployment_vertical" if requirements.deployment_mode == "cloud" else "layered_horizontal"

    system_msg = (
        "You are an architecture diagram generator for Huawei Cloud solutions.\n"
        "You must output a JSON object conforming to the Architecture Spec Schema below.\n"
        "Do NOT output draw.io XML. Output ONLY the JSON spec.\n\n"
        "## Architecture Diagram Type Reference\n"
        f"{arch_section}\n\n"
        "## Style Preset (corporate)\n"
        f"Palette: {json.dumps(style_preset.get('palette', {}), indent=2)}\n"
        f"Roles: {json.dumps(style_preset.get('roles', {}), indent=2)}\n\n"
        "## Architecture Spec JSON Schema\n"
        f"{ARCHITECTURE_SPEC_SCHEMA}\n\n"
        "## Huawei Cloud Design Conventions\n"
        "- Use Huawei Cloud service names (ECS, CCE, RDS, OBS, ELB, WAF, NAT, VPN, VPC, etc.)\n"
        "- The spec MUST use containers (region → vpc → subnet) instead of flat layers\n"
        "- Place WAF/ELB at the gateway layer between users and application services\n"
        "- Use gateway type for load balancers, API gateways, WAF\n"
        "- Use service type for compute (ECS, CCE), middleware, app servers\n"
        "- Use database type for RDS, DDS, DWS, GaussDB\n"
        "- Use queue type for DMS, Kafka, message buses\n"
        "- Use external type for third-party systems, on-prem systems — these must NOT be inside the region container\n"
        "- Non-external nodes must have a container_id referencing a valid container\n"
        "- External and user nodes may omit container_id and will be rendered outside the region\n"
        "- Database nodes must be in a data/db subnet\n"
        "- Use edge_kind on every edge: traffic, management, replication, or notification\n"
        "- Every non-external node MUST have a product field with a standard Huawei Cloud service name\n"
        "- Product examples: ECS, CCE, RDS, DDS, ELB, WAF, OBS, EVS, NAT Gateway, EIP, SMN, DCS, DMS, CBR, VPN, Direct Connect, CES, CTS, KMS, APIG\n"
        f"- Prefer template=\"{template_hint}\" for this deployment mode\n"
    )

    user_msg = (
        f"Generate an HLD architecture diagram with these requirements:\n\n"
        f"Project: {requirements.project_name}\n"
        f"Business Goal: {requirements.business_goal}\n"
        f"Architecture Boundary: {requirements.architecture_boundary}\n"
        f"Deployment Mode: {requirements.deployment_mode}\n"
        f"User/Access Entry: {requirements.user_access_entry}\n"
        f"Core Components: {', '.join(core_list)}\n"
        f"External Integrations: {', '.join(ext_list)}\n"
        f"Data Stores/Flow: {', '.join(data_list)}\n"
        f"Network/Security Boundary: {requirements.network_security_boundary}\n\n"
        "Output the Architecture Spec JSON only. No markdown fences, no explanation."
    )

    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


# ── Spec parsing ─────────────────────────────────────────────────────────

def parse_architecture_spec(llm_output: str) -> dict:
    """Parse and validate the LLM output as an architecture spec JSON.

    Strips markdown fences if present. Validates required keys and constraints.
    Supports both legacy (layers) and template-driven (containers) specs.
    Raises ValueError on invalid output.
    """
    text = llm_output.strip()
    # Strip markdown code fences
    fence_match = re.match(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    spec = json.loads(text)

    # Validate required keys
    for key in ("title", "diagram_type", "layout", "nodes", "edges"):
        if key not in spec:
            raise ValueError(f"Missing required key: {key}")

    if spec["diagram_type"] != "architecture":
        raise ValueError(f"Expected diagram_type='architecture', got '{spec['diagram_type']}'")

    if spec["layout"] not in ("TB", "LR"):
        raise ValueError(f"Invalid layout: {spec['layout']}")

    def _normalize_container_type(value: str | None) -> str | None:
        if value is None:
            return None
        aliases = {
            "as group": "as_group",
            "as-group": "as_group",
            "as policy": "as_policy",
            "as-policy": "as_policy",
            "availability_zone": "az",
            "availability zone": "az",
            "network_zone": "subnet",
            "network zone": "subnet",
        }
        key = value.strip().lower()
        return aliases.get(key, key)

    # --- Template-driven spec (containers) ---
    is_template_spec = "containers" in spec and "template" in spec

    if is_template_spec:
        template = spec["template"]
        if template not in VALID_TEMPLATES:
            raise ValueError(f"Unsupported template: {template}. Must be one of {VALID_TEMPLATES}")

        containers = spec["containers"]
        if not containers:
            raise ValueError("containers must be non-empty")

        container_ids = [c["id"] for c in containers]
        if len(container_ids) != len(set(container_ids)):
            raise ValueError("Duplicate container id found")

        # Validate container_type and parent_id
        for c in containers:
            c["container_type"] = _normalize_container_type(c.get("container_type"))
            if c.get("container_type") not in VALID_CONTAINER_TYPES:
                raise ValueError(f"Invalid container_type: {c.get('container_type')}")
            pid = c.get("parent_id")
            if pid is not None and pid not in container_ids:
                raise ValueError(f"Container {c['id']} references unknown parent_id: {pid}")

        # Must have exactly one root region
        root_containers = [c for c in containers if c.get("parent_id") is None]
        region_roots = [c for c in root_containers if c["container_type"] == "region"]
        if len(region_roots) != 1:
            raise ValueError(f"Must have exactly one root region container, found {len(region_roots)}")

        # Build parent chain for hierarchy checks
        container_by_id = {c["id"]: c for c in containers}

        def _ancestor_types(cid: str) -> list[str]:
            types = []
            cur = container_by_id.get(cid)
            while cur:
                types.append(cur["container_type"])
                pid = cur.get("parent_id")
                cur = container_by_id.get(pid) if pid else None
            return types

        region_id = region_roots[0]["id"]
        data_subnet_ids = [
            c["id"]
            for c in containers
            if c["container_type"] == "subnet"
            and ("data" in c.get("label", "").lower() or "db" in c.get("label", "").lower())
        ]

        # nodes: validate container_id, type, label
        if not spec["nodes"]:
            raise ValueError("nodes must be non-empty")
        node_ids = [n["id"] for n in spec["nodes"]]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Duplicate node id found")
        if len(spec["nodes"]) > MAX_NODES:
            raise ValueError(f"Too many nodes: {len(spec['nodes'])} > {MAX_NODES}")

        for node in spec["nodes"]:
            if node.get("type") not in VALID_NODE_TYPES:
                raise ValueError(f"Invalid node type: {node.get('type')}")
            cid = node.get("container_id")
            if len(node.get("label", "")) > MAX_LABEL_LEN:
                raise ValueError(f"Node {node['id']} label too long ({len(node.get('label', ''))} > {MAX_LABEL_LEN})")

            if node["type"] in ("external", "user"):
                if cid is not None and cid not in container_ids:
                    raise ValueError(f"Node {node['id']} references unknown container_id: {cid}")
                # external/user nodes must NOT be inside the region
                if cid in container_by_id and "region" in _ancestor_types(cid):
                    raise ValueError(f"Node {node['id']} of type '{node['type']}' must not be inside the region container")
                continue

            if cid is None:
                if node["type"] == "database":
                    if len(data_subnet_ids) == 1:
                        node["container_id"] = data_subnet_ids[0]
                        cid = node["container_id"]
                        logger.warning(
                            "Node %s missing container_id — assigned to data subnet %s",
                            node["id"], cid,
                        )
                    else:
                        raise ValueError(f"Node {node['id']} missing container_id")
                else:
                    node["container_id"] = region_id
                    cid = region_id
                    logger.warning(
                        "Node %s missing container_id — assigned to region container %s",
                        node["id"], cid,
                    )
            if cid not in container_ids:
                raise ValueError(f"Node {node['id']} references unknown container_id: {cid}")

            # database nodes must be in a data/db subnet
            if node["type"] == "database":
                container = container_by_id.get(cid)
                if not container or container["container_type"] != "subnet":
                    raise ValueError(f"Database node {node['id']} must be inside a subnet container")
                subnet_label = container.get("label", "").lower()
                if "data" not in subnet_label and "db" not in subnet_label:
                    raise ValueError(f"Database node {node['id']} must be in a data/db subnet, got '{container.get('label')}'")

            # Warn if non-external node lacks product field (needed for icon rendering)
            if not node.get("product"):
                logger.warning("Node %s (type=%s) missing 'product' field — will use generic shape fallback", node["id"], node["type"])

        # edges: validate source/target, edge_kind, count
        node_id_set = set(node_ids)
        node_by_id = {n["id"]: n for n in spec["nodes"]}

        def _container_contains_node(container_id: str, node: dict) -> bool:
            current = node.get("container_id")
            while current:
                if current == container_id:
                    return True
                parent = container_by_id.get(current, {}).get("parent_id")
                current = parent
            return False

        def _resolve_container_endpoint(container_id: str) -> str | None:
            # Prefer a directly contained node, else any descendant-contained node.
            for n in spec["nodes"]:
                if n.get("container_id") == container_id:
                    return n["id"]
            for n in spec["nodes"]:
                if _container_contains_node(container_id, n):
                    return n["id"]
            return None

        if len(spec["edges"]) > MAX_EDGES:
            raise ValueError(f"Too many edges: {len(spec['edges'])} > {MAX_EDGES}")
        for edge in spec["edges"]:
            if edge["source"] not in node_id_set and edge["source"] in container_ids:
                resolved = _resolve_container_endpoint(edge["source"])
                if resolved:
                    logger.warning(
                        "Edge source %s references container — remapped to node %s",
                        edge["source"], resolved,
                    )
                    edge["source"] = resolved
            if edge["target"] not in node_id_set and edge["target"] in container_ids:
                resolved = _resolve_container_endpoint(edge["target"])
                if resolved:
                    logger.warning(
                        "Edge target %s references container — remapped to node %s",
                        edge["target"], resolved,
                    )
                    edge["target"] = resolved
            if edge["source"] not in node_id_set:
                raise ValueError(f"Edge references unknown source: {edge['source']}")
            if edge["target"] not in node_id_set:
                raise ValueError(f"Edge references unknown target: {edge['target']}")
            label = edge.get("label") or ""
            if len(label) > MAX_LABEL_LEN:
                raise ValueError(f"Edge label too long ({len(label)} > {MAX_LABEL_LEN})")
            kind = edge.get("edge_kind", "traffic")
            if kind not in VALID_EDGE_KINDS:
                raise ValueError(f"Invalid edge_kind: {kind}. Must be one of {VALID_EDGE_KINDS}")

    else:
        # Legacy spec (layers) — backward compat
        if "layers" not in spec:
            raise ValueError("Missing required key: layers (or containers+template)")
        if not spec["layers"]:
            raise ValueError("layers must be non-empty")
        layer_ids = [l["id"] for l in spec["layers"]]
        if len(layer_ids) != len(set(layer_ids)):
            raise ValueError("Duplicate layer id found")

        if not spec["nodes"]:
            raise ValueError("nodes must be non-empty")
        node_ids = [n["id"] for n in spec["nodes"]]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("Duplicate node id found")
        if len(spec["nodes"]) > MAX_NODES:
            raise ValueError(f"Too many nodes: {len(spec['nodes'])} > {MAX_NODES}")

        for node in spec["nodes"]:
            if node.get("type") not in VALID_NODE_TYPES:
                raise ValueError(f"Invalid node type: {node.get('type')}")
            if node.get("layer_id") not in set(layer_ids):
                raise ValueError(f"Node {node['id']} references unknown layer_id: {node.get('layer_id')}")
            if len(node.get("label", "")) > MAX_LABEL_LEN:
                raise ValueError(f"Node {node['id']} label too long ({len(node.get('label', ''))} > {MAX_LABEL_LEN})")

        node_id_set = set(node_ids)
        if len(spec["edges"]) > MAX_EDGES:
            raise ValueError(f"Too many edges: {len(spec['edges'])} > {MAX_EDGES}")
        for edge in spec["edges"]:
            if edge["source"] not in node_id_set:
                raise ValueError(f"Edge references unknown source: {edge['source']}")
            if edge["target"] not in node_id_set:
                raise ValueError(f"Edge references unknown target: {edge['target']}")
            label = edge.get("label") or ""
            if len(label) > MAX_LABEL_LEN:
                raise ValueError(f"Edge label too long ({len(label)} > {MAX_LABEL_LEN})")

    return spec


# ── Draw.io XML rendering ───────────────────────────────────────────────

def _safe_filename(name: str) -> str:
    """Convert a project name to a safe filename."""
    safe = re.sub(r"[^\w\-.]", "_", name.strip())
    return safe or "hld-design"


def render_spec_to_drawio_xml(spec: dict, style_preset: dict) -> str:
    """Render the architecture spec to .drawio XML deterministically.

    Supports both legacy (layers) and template-driven (containers) specs.
    Does NOT mutate the spec dict. Uses a local node_id -> cell_id map.
    """
    palette = style_preset.get("palette", {})
    roles = style_preset.get("roles", {})
    font_cfg = style_preset.get("font", {})
    edge_cfg = style_preset.get("edges", {})
    shapes_cfg = style_preset.get("shapes", {})

    font_family = font_cfg.get("fontFamily", "Arial")
    font_size = font_cfg.get("fontSize", 11)
    title_font_size = font_cfg.get("titleFontSize", 13)

    nodes = spec["nodes"]
    edges = spec["edges"]
    layout = spec["layout"]

    # Local map: node_id -> cell_id (no mutation of spec)
    node_cell_map: dict[str, int] = {}
    edge_points_by_id: dict[int, list[tuple[int, int]]] = {}

    is_lr = layout == "LR"
    cell_id = 2  # id=0 and id=1 are root cells
    cells: list[tuple[int, str, str, str | None, str | None, int, int, int, int]] = []

    def _parse_anchor(style_fragment: str, prefix: str) -> tuple[float, float]:
        x_match = re.search(rf"{prefix}X=([0-9.]+)", style_fragment)
        y_match = re.search(rf"{prefix}Y=([0-9.]+)", style_fragment)
        x_val = float(x_match.group(1)) if x_match else 0.5
        y_val = float(y_match.group(1)) if y_match else 0.5
        return x_val, y_val

    def _anchor_point(box: tuple[int, int, int, int], anchor: tuple[float, float]) -> tuple[int, int]:
        x, y, w, h = box
        return int(x + w * anchor[0]), int(y + h * anchor[1])

    def _inflate_box(box: tuple[int, int, int, int], padding: int) -> tuple[int, int, int, int]:
        x, y, w, h = box
        return (x - padding, y - padding, w + 2 * padding, h + 2 * padding)

    def _segment_hits_box(
        p1: tuple[int, int],
        p2: tuple[int, int],
        box: tuple[int, int, int, int],
    ) -> bool:
        x1, y1 = p1
        x2, y2 = p2
        bx, by, bw, bh = box
        if x1 == x2:
            if bx <= x1 <= bx + bw:
                low, high = sorted((y1, y2))
                return low < by + bh and high > by
            return False
        if y1 == y2:
            if by <= y1 <= by + bh:
                low, high = sorted((x1, x2))
                return low < bx + bw and high > bx
            return False
        return False

    def _path_is_clear(
        points: list[tuple[int, int]],
        obstacles: list[tuple[int, int, int, int]],
    ) -> bool:
        for i in range(len(points) - 1):
            if points[i] == points[i + 1]:
                continue
            for obstacle in obstacles:
                if _segment_hits_box(points[i], points[i + 1], obstacle):
                    return False
        return True

    def _pick_corridor(
        preferred: int,
        candidates: list[int],
        build_points: Callable[[int], list[tuple[int, int]]],
        obstacles: list[tuple[int, int, int, int]],
    ) -> int:
        seen: set[int] = set()
        ordered = [preferred] + candidates
        for candidate in ordered:
            if candidate in seen:
                continue
            seen.add(candidate)
            if _path_is_clear(build_points(candidate), obstacles):
                return candidate
        return preferred

    def _compute_edge_waypoints(
        src_box: tuple[int, int, int, int],
        tgt_box: tuple[int, int, int, int],
        exit_hint: str,
        entry_hint: str,
        obstacles: list[tuple[int, int, int, int]],
    ) -> list[tuple[int, int]]:
        clearance = EDGE_WAYPOINT_CLEARANCE + 4
        src_anchor = _anchor_point(src_box, _parse_anchor(exit_hint, "exit"))
        tgt_anchor = _anchor_point(tgt_box, _parse_anchor(entry_hint, "entry"))
        blocked = [
            _inflate_box(box, clearance)
            for box in obstacles
            if box not in (src_box, tgt_box)
        ]

        if "exitY=" in exit_hint:
            src_escape_y = (
                src_box[1] + src_box[3] + clearance
                if "exitY=1.0" in exit_hint
                else src_box[1] - clearance
            )
            tgt_escape_y = (
                tgt_box[1] - clearance
                if "entryY=0.0" in entry_hint
                else tgt_box[1] + tgt_box[3] + clearance
            )
            left_corridor = min(src_box[0], tgt_box[0]) - clearance
            right_corridor = max(src_box[0] + src_box[2], tgt_box[0] + tgt_box[2]) + clearance
            preferred_corridor = left_corridor if src_anchor[0] >= tgt_anchor[0] else right_corridor

            def _vertical_path(corridor_x: int) -> list[tuple[int, int]]:
                return [
                    src_anchor,
                    (src_anchor[0], src_escape_y),
                    (corridor_x, src_escape_y),
                    (corridor_x, tgt_escape_y),
                    (tgt_anchor[0], tgt_escape_y),
                    tgt_anchor,
                ]

            corridor_x = _pick_corridor(
                preferred_corridor,
                [left_corridor, right_corridor],
                _vertical_path,
                blocked,
            )
            points = _vertical_path(corridor_x)[1:-1]
        else:
            src_escape_x = (
                src_box[0] + src_box[2] + clearance
                if "exitX=1.0" in exit_hint
                else src_box[0] - clearance
            )
            tgt_escape_x = (
                tgt_box[0] - clearance
                if "entryX=0.0" in entry_hint
                else tgt_box[0] + tgt_box[2] + clearance
            )
            top_corridor = min(src_box[1], tgt_box[1]) - clearance
            bottom_corridor = max(src_box[1] + src_box[3], tgt_box[1] + tgt_box[3]) + clearance
            preferred_corridor = top_corridor if src_anchor[1] >= tgt_anchor[1] else bottom_corridor

            def _horizontal_path(corridor_y: int) -> list[tuple[int, int]]:
                return [
                    src_anchor,
                    (src_escape_x, src_anchor[1]),
                    (src_escape_x, corridor_y),
                    (tgt_escape_x, corridor_y),
                    (tgt_escape_x, tgt_anchor[1]),
                    tgt_anchor,
                ]

            corridor_y = _pick_corridor(
                preferred_corridor,
                [top_corridor, bottom_corridor],
                _horizontal_path,
                blocked,
            )
            points = _horizontal_path(corridor_y)[1:-1]

        deduped: list[tuple[int, int]] = []
        for point in points:
            if not deduped or deduped[-1] != point:
                deduped.append(point)
        return deduped

    def _node_style(ntype: str) -> str:
        shape_prefix, role_key = NODE_TYPE_MAP.get(ntype, NODE_TYPE_MAP["service"])
        color_slot = roles.get(role_key, "primary")
        colors = palette.get(color_slot, palette.get("primary", {}))
        fill = colors.get("fillColor", "#e3f2fd")
        stroke = colors.get("strokeColor", "#1565c0")
        return f"{shape_prefix}fillColor={fill};strokeColor={stroke};fontFamily={font_family};fontSize={font_size}"

    def _render_icon_node(n: dict, parent: str, x: int, y: int) -> tuple[int, tuple[int, int, int, int]]:
        """Render a node as icon+label or fallback to generic shape.

        The (x, y) is the top-left of the layout box (ICON_BOX or NODE_BOX).
        For icon nodes, the 60x60 image is centered within the wider box and
        the label sits below.  For fallback shapes, the shape fills the box.

        Returns the primary cell_id for edge connections.
        """
        nonlocal cell_id
        product = n.get("product")
        icon_title = resolve_product_icon_title(product) if product else None
        icon_entry = resolve_hwc_icon(icon_title) if icon_title else None

        if icon_entry and icon_entry.get("data"):
            image_data_uri = build_icon_svg_data_uri(icon_title) if icon_title else None
            if not image_data_uri:
                ntype = n.get("type", "service")
                primary = cell_id
                cells.append((cell_id, n["label"], _node_style(ntype), parent,
                              None, None, x, y, ICON_BOX_WIDTH, ICON_BOX_HEIGHT))
                cell_id += 1
                return primary, (x, y, ICON_BOX_WIDTH, ICON_BOX_HEIGHT)

            # Center the 60x60 icon image within the ICON_BOX_WIDTH cell
            img_offset_x = (ICON_BOX_WIDTH - ICON_IMAGE_SIZE) // 2
            icon_style = (
                f"shape=image;verticalLabelPosition=bottom;labelPosition=center;"
                f"verticalAlign=top;image={image_data_uri};aspect=fixed;imageAspect=0;"
                f"fontFamily={font_family};fontSize={ICON_LABEL_FONT_SIZE}"
            )
            primary = cell_id
            cells.append((cell_id, n["label"], icon_style, parent,
                          None, None, x + img_offset_x, y, ICON_IMAGE_SIZE, ICON_IMAGE_SIZE))
            cell_id += 1
            return primary, (x + img_offset_x, y, ICON_IMAGE_SIZE, ICON_IMAGE_SIZE)
        else:
            # Fallback: generic shape
            ntype = n.get("type", "service")
            primary = cell_id
            cells.append((cell_id, n["label"], _node_style(ntype), parent,
                          None, None, x, y, NODE_WIDTH, NODE_HEIGHT))
            cell_id += 1
            return primary, (x, y, NODE_WIDTH, NODE_HEIGHT)

    def _container_style(ctype: str) -> str:
        cs = CONTAINER_STYLE_MAP.get(ctype, CONTAINER_STYLE_MAP["subnet"])
        base = "swimlane;html=1;collapsible=0;"
        parts = [
            f"startSize={cs['startSize']}",
            f"fillColor={cs['fill']}",
            f"strokeColor={cs['outline']}",
            f"strokeWidth={cs.get('strokeWidth', '1')}",
            f"fontStyle={cs['fontStyle']}",
            f"fontFamily={font_family}",
            f"fontSize={title_font_size}",
        ]
        if cs["dashed"] == "1":
            parts.append("dashed=1")
            parts.append(f"dashPattern={cs['dashPattern']}")
        return base + ";".join([""] + parts)

    # --- Template-driven rendering (containers) ---
    is_template_spec = "containers" in spec and "template" in spec

    if is_template_spec:
        containers = spec["containers"]
        container_by_id = {c["id"]: c for c in containers}
        node_by_id = {n["id"]: n for n in nodes}
        container_cell_map: dict[str, int] = {}

        # Build children map for layout computation
        children_of: dict[str | None, list[str]] = {}
        for c in containers:
            pid = c.get("parent_id")
            children_of.setdefault(pid, []).append(c["id"])

        # Nodes grouped by container
        nodes_by_container: dict[str, list[dict]] = {}
        for n in nodes:
            cid = n.get("container_id", "")
            nodes_by_container.setdefault(cid, []).append(n)

        container_sizes: dict[str, tuple[int, int]] = {}  # id -> (w, h)
        # Track node positions for edge routing: node_id -> (x, y, w, h) absolute
        node_positions: dict[str, tuple[int, int, int, int]] = {}

        def _compute_container_size(cid: str) -> tuple[int, int]:
            child_ids = children_of.get(cid, [])
            child_nodes = nodes_by_container.get(cid, [])
            ctype = container_by_id[cid]["container_type"]
            start_size = int(CONTAINER_STYLE_MAP[ctype]["startSize"])

            # Sort subnets by semantic layer so size matches render order
            if ctype == "vpc":
                child_ids = sorted(
                    child_ids,
                    key=lambda ch: subnet_layer_rank(container_by_id[ch].get("label", "")),
                )

            child_sizes = [_compute_container_size(ch) for ch in child_ids]
            # VPC always stacks subnets vertically regardless of overall layout
            effective_lr = is_lr or ctype == "vpc"
            return compute_container_size(
                ctype, child_sizes, child_nodes,
                is_lr=effective_lr, start_size=start_size,
            )

        # Find root region
        root_id = next(c["id"] for c in containers if c.get("parent_id") is None and c["container_type"] == "region")

        # Nodes outside the region are rendered as either left-side users or right-side notes.
        outside_nodes = [n for n in nodes if n.get("container_id") not in container_by_id]
        user_nodes = [n for n in outside_nodes if n.get("type") == "user"]
        external_nodes = [n for n in outside_nodes if n.get("type") == "external"]
        external_node_ids = {n["id"] for n in external_nodes}
        internal_nodes = [n for n in nodes if n["id"] not in external_node_ids and n["id"] not in {u["id"] for u in user_nodes}]

        def _ancestor_container(node_id: str, target_type: str) -> str | None:
            current = node_by_id.get(node_id, {}).get("container_id")
            while current in container_by_id:
                container = container_by_id[current]
                if container["container_type"] == target_type:
                    return current
                current = container.get("parent_id")
            return None

        def _group_representative(container_id: str) -> str | None:
            direct = [n["id"] for n in internal_nodes if n.get("container_id") == container_id]
            if direct:
                return sorted(direct)[0]
            descendants = []
            for n in internal_nodes:
                current = n.get("container_id")
                while current in container_by_id:
                    if current == container_id:
                        descendants.append(n["id"])
                        break
                    current = container_by_id[current].get("parent_id")
            return sorted(descendants)[0] if descendants else None

        def _filter_render_edges() -> tuple[list[dict], list[dict]]:
            kept: list[dict] = []
            removed_external: list[dict] = []
            seen_keys: set[tuple[str, str, str]] = set()

            for edge in edges:
                src = edge["source"]
                tgt = edge["target"]
                kind = edge.get("edge_kind", "traffic")

                if src in external_node_ids or tgt in external_node_ids:
                    removed_external.append(edge)
                    continue
                if kind in ("management", "notification"):
                    continue

                render_edge = dict(edge)
                src_group = _ancestor_container(src, "as_group")
                tgt_group = _ancestor_container(tgt, "as_group")

                if src_group and src_group == tgt_group:
                    continue
                if src_group and tgt_group and src_group == tgt_group:
                    continue

                if src_group and not tgt_group:
                    rep = _group_representative(src_group)
                    if rep:
                        render_edge["source"] = rep
                if tgt_group and not src_group:
                    rep = _group_representative(tgt_group)
                    if rep:
                        render_edge["target"] = rep

                canonical_src = src_group or render_edge["source"]
                canonical_tgt = tgt_group or render_edge["target"]
                dedupe_key = (canonical_src, canonical_tgt, kind)
                if dedupe_key in seen_keys:
                    continue
                seen_keys.add(dedupe_key)
                kept.append(render_edge)

            primary_traffic = [e for e in kept if e.get("edge_kind", "traffic") == "traffic"]
            replication = [e for e in kept if e.get("edge_kind") == "replication"]
            return (primary_traffic + replication)[:MAX_RENDER_EDGES], removed_external

        render_edges, external_edges = _filter_render_edges()

        # Compute full diagram size
        root_w, root_h = _compute_container_size(root_id)

        # --- Render containers recursively ---
        def _render_container(
            cid: str,
            parent_cell: str | None,
            x: int,
            y: int,
            abs_x: int,
            abs_y: int,
        ) -> None:
            nonlocal cell_id
            c = container_by_id[cid]
            ctype = c["container_type"]
            cw, ch = _compute_container_size(cid)
            container_cell_map[cid] = cell_id
            container_sizes[cid] = (cw, ch)

            cs = CONTAINER_STYLE_MAP[ctype]
            style = _container_style(ctype)
            cells.append((cell_id, c["label"], style, parent_cell or "1", None, None, x, y, cw, ch))
            parent_for_children = str(cell_id)
            cell_id += 1

            is_group = ctype in ("az", "as_group", "as_policy")
            pad_x = CONTAINER_PADDING_X + (GROUP_PADDING_X if is_group else 0)
            pad_y = CONTAINER_PADDING_Y + (GROUP_PADDING_Y if is_group else 0)
            header_h = int(cs["startSize"]) + CONTAINER_TITLE_GAP

            # Render child containers — sort subnets by semantic layer
            child_ids = children_of.get(cid, [])
            if ctype == "vpc":
                child_ids = sorted(
                    child_ids,
                    key=lambda ch: subnet_layer_rank(container_by_id[ch].get("label", "")),
                )
            child_x = pad_x
            child_y = header_h
            # VPC always stacks subnets vertically (public > app > data > mgmt)
            vpc_vertical = ctype == "vpc"

            for ch_id in child_ids:
                ch_w, ch_h = _compute_container_size(ch_id)
                _render_container(
                    ch_id,
                    parent_for_children,
                    child_x,
                    child_y,
                    abs_x + child_x,
                    abs_y + child_y,
                )
                if is_lr or vpc_vertical:
                    child_y += ch_h + CONTAINER_PADDING_Y
                else:
                    child_x += ch_w + CONTAINER_PADDING_X

            # Render nodes inside this container using grid layout
            child_nodes = nodes_by_container.get(cid, [])
            if child_nodes:
                # If we had child containers, place nodes below them
                if child_ids:
                    if is_lr or vpc_vertical:
                        node_y_start = child_y
                    else:
                        max_child_h = max(_compute_container_size(ch)[1] for ch in child_ids)
                        node_y_start = header_h + max_child_h + CONTAINER_PADDING_Y
                else:
                    node_y_start = header_h

                # Use grid layout from hld_layout
                grid = layout_nodes_in_grid(
                    child_nodes,
                    area_width=cw - 2 * pad_x,
                    max_cols=DEFAULT_MAX_COLS,
                    start_x=pad_x,
                    start_y=node_y_start,
                )
                for n, nx, ny, nw, nh in grid:
                    primary, rendered_box = _render_icon_node(n, parent_for_children, nx, ny)
                    node_cell_map[n["id"]] = primary
                    # Store actual rendered cell geometry for edge routing.
                    node_positions[n["id"]] = (
                        abs_x + rendered_box[0],
                        abs_y + rendered_box[1],
                        rendered_box[2],
                        rendered_box[3],
                    )

        user_col_w = max((measure_node_box(n)[0] for n in user_nodes), default=0)
        root_x = DIAGRAM_MARGIN + (user_col_w + EXTERNAL_NOTE_GAP if user_nodes else 0)

        # Render root region
        _render_container(root_id, None, root_x, DIAGRAM_MARGIN, root_x, DIAGRAM_MARGIN)

        if user_nodes:
            user_x = max(DIAGRAM_MARGIN, root_x - user_col_w - EXTERNAL_NOTE_GAP)
            user_heights = [measure_node_box(n)[1] for n in user_nodes]
            user_total_h = sum(user_heights) + max(0, len(user_nodes) - 1) * NODE_GAP_Y
            user_y = DIAGRAM_MARGIN + max(0, (root_h - user_total_h) // 2)
            for n in user_nodes:
                primary, rendered_box = _render_icon_node(n, "1", user_x, user_y)
                node_cell_map[n["id"]] = primary
                node_positions[n["id"]] = rendered_box
                user_y += measure_node_box(n)[1] + NODE_GAP_Y

        # Render external services as a right-side note box instead of individual nodes/edges.
        if external_nodes:
            ext_x = root_x + root_w + EXTERNAL_NOTE_GAP
            ext_items = [f"- {n['label']}" for n in external_nodes]
            integration_labels = sorted({(e.get("label") or "").strip() for e in external_edges if (e.get("label") or "").strip()})
            note_lines = ["External Services:"] + ext_items
            if integration_labels:
                note_lines.extend(["", f"Integration: {', '.join(integration_labels[:3])}"])
            note_value = "<div>" + "<br/>".join(note_lines) + "</div>"
            note_h = max(120, 34 + len(note_lines) * 16)
            note_y = DIAGRAM_MARGIN + max(0, (root_h - note_h) // 2)
            note_style = (
                f"rounded=1;whiteSpace=wrap;html=1;fillColor=#F5F5F5;strokeColor=#999999;"
                f"align=left;verticalAlign=top;fontSize={font_size};fontFamily={font_family};spacing=8"
            )
            cells.append((cell_id, note_value, note_style, "1", None, None, ext_x, note_y, EXTERNAL_NOTE_WIDTH, note_h))
            cell_id += 1

        # Edges with explicit anchors and manual waypoints to avoid icon overlap.
        base_edge_style = f"edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=0;jettySize=auto;html=1;endArrow=classic;endFill=1;strokeColor=#333333;strokeWidth=1;fontFamily={font_family};fontSize={font_size - 1}"
        obstacle_boxes = list(node_positions.values())
        for edge in render_edges:
            source_cell = node_cell_map.get(edge["source"])
            target_cell = node_cell_map.get(edge["target"])
            if not source_cell or not target_cell:
                continue
            kind = edge.get("edge_kind", "traffic")
            label = "" if kind == "traffic" else (edge.get("label") or "")
            kind_overrides = EDGE_KIND_STYLE_MAP.get(kind, {})
            kind_parts = []
            if kind_overrides.get("dashed") == "1":
                kind_parts.append("dashed=1")
                kind_parts.append(f"dashPattern={kind_overrides['dashPattern']}")
            if "strokeColor" in kind_overrides:
                kind_parts.append(f"strokeColor={kind_overrides['strokeColor']}")

            # Route edge anchors to reduce node crossings
            src_box = node_positions.get(edge["source"])
            tgt_box = node_positions.get(edge["target"])
            exit_hint = ""
            entry_hint = ""
            if src_box and tgt_box:
                exit_hint, entry_hint = route_edge_anchors(src_box, tgt_box)
            if not exit_hint:
                exit_hint = "exitX=1.0;exitY=0.5;exitDx=0;exitDy=0;"
            if not entry_hint:
                entry_hint = "entryX=0.0;entryY=0.5;entryDx=0;entryDy=0;"

            edge_style = base_edge_style
            edge_style += ";" + exit_hint + entry_hint
            if kind_parts:
                edge_style += ";" + ";".join(kind_parts)
            cells.append((cell_id, label, edge_style, "1", str(source_cell), str(target_cell), 0, 0, 0, 0))
            if src_box and tgt_box:
                edge_points_by_id[cell_id] = _compute_edge_waypoints(
                    src_box,
                    tgt_box,
                    exit_hint,
                    entry_hint,
                    obstacle_boxes,
                )
            cell_id += 1

    else:
        # --- Legacy layer-based rendering ---
        layers = spec["layers"]

        # Build lookup maps
        nodes_by_layer: dict[str, list[dict]] = {}
        for n in nodes:
            lid = n.get("layer_id", "")
            nodes_by_layer.setdefault(lid, []).append(n)

        # Layer containers
        layer_cells: dict[str, int] = {}
        layer_positions: dict[str, tuple[int, int]] = {}

        if is_lr:
            container_w = 200
        else:
            container_w = LAYER_WIDTH

        for i, layer in enumerate(layers):
            lid = layer["id"]
            layer_cells[lid] = cell_id
            layer_positions[lid] = (DIAGRAM_MARGIN, DIAGRAM_MARGIN)
            container_style = f"{shapes_cfg.get('container', 'swimlane;startSize=30')};html=1;fontFamily={font_family};fontSize={title_font_size};fontStyle=1"
            cells.append((cell_id, layer["label"], container_style, "1", None, None, DIAGRAM_MARGIN, DIAGRAM_MARGIN, container_w, LAYER_HEIGHT))
            cell_id += 1

        # TB layout: compute y positions accounting for actual node counts per layer
        if not is_lr:
            y_cursor = DIAGRAM_MARGIN
            for layer in layers:
                lid = layer["id"]
                layer_nodes = nodes_by_layer.get(lid, [])
                num_rows = max(len(layer_nodes), 1)
                layer_h = LAYER_HEIGHT + num_rows * (NODE_HEIGHT + NODE_GAP_Y) + LAYER_PADDING_Y
                idx = next(i for i, c in enumerate(cells) if c[0] == layer_cells[lid])
                cells[idx] = (cells[idx][0], cells[idx][1], cells[idx][2], cells[idx][3],
                              cells[idx][4], cells[idx][5], DIAGRAM_MARGIN, y_cursor, LAYER_WIDTH, layer_h)
                layer_positions[lid] = (DIAGRAM_MARGIN, y_cursor)

                node_x_cursor = LAYER_PADDING_X
                node_y = LAYER_HEIGHT + 10
                for n in layer_nodes:
                    ntype = n.get("type", "service")
                    cells.append((cell_id, n["label"], _node_style(ntype), str(layer_cells[lid]),
                                  None, None, node_x_cursor, node_y, NODE_WIDTH, NODE_HEIGHT))
                    node_cell_map[n["id"]] = cell_id
                    cell_id += 1
                    node_x_cursor += NODE_WIDTH + NODE_GAP_X

                y_cursor += layer_h + LAYER_PADDING_Y

        else:
            # LR layout
            x_cursor = DIAGRAM_MARGIN
            for layer in layers:
                lid = layer["id"]
                layer_nodes = nodes_by_layer.get(lid, [])
                layer_h = LAYER_HEIGHT + max(len(layer_nodes), 1) * (NODE_HEIGHT + NODE_GAP_Y) + LAYER_PADDING_Y
                idx = next(i for i, c in enumerate(cells) if c[0] == layer_cells[lid])
                cells[idx] = (cells[idx][0], cells[idx][1], cells[idx][2], cells[idx][3],
                              cells[idx][4], cells[idx][5], x_cursor, DIAGRAM_MARGIN, container_w, layer_h)

                node_y = LAYER_HEIGHT + 10
                for n in layer_nodes:
                    ntype = n.get("type", "service")
                    cells.append((cell_id, n["label"], _node_style(ntype), str(layer_cells[lid]),
                                  None, None, LAYER_PADDING_X, node_y, NODE_WIDTH, NODE_HEIGHT))
                    node_cell_map[n["id"]] = cell_id
                    cell_id += 1
                    node_y += NODE_HEIGHT + NODE_GAP_Y

                x_cursor += container_w + LAYER_PADDING_X

        # Edges (legacy — no edge_kind)
        edge_style = f"{edge_cfg.get('style', 'edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;jettySize=auto;html=1;strokeWidth=1')};{edge_cfg.get('arrow', 'endArrow=classic;endFill=1')};fontFamily={font_family};fontSize={font_size - 1}"
        for edge in edges:
            source_cell = node_cell_map.get(edge["source"])
            target_cell = node_cell_map.get(edge["target"])
            if not source_cell or not target_cell:
                continue
            label = edge.get("label") or ""
            cells.append((cell_id, label, edge_style, "1",
                          str(source_cell), str(target_cell), 0, 0, 0, 0))
            cell_id += 1

    # Build XML
    root = ET.Element("mxfile")
    diagram = ET.SubElement(root, "diagram", name=spec.get("title", "HLD"), id="hld-diagram")
    mxGraphModel = ET.SubElement(diagram, "mxGraphModel", dx="1422", dy="762", grid="1", gridSize="10", guides="1", tooltips="1", connect="1", arrows="1", fold="1", page="1", pageScale="1", pageWidth="1100", pageHeight="850", math="0", shadow="0")
    root_cell = ET.SubElement(mxGraphModel, "root")
    ET.SubElement(root_cell, "mxCell", id="0")
    ET.SubElement(root_cell, "mxCell", id="1", parent="0")

    for cid, value, style, parent, source, target, x, y, w, h in cells:
        attrs = {"id": str(cid), "value": value, "style": style, "parent": parent}
        if source is not None:
            attrs["source"] = source
        if target is not None:
            attrs["target"] = target
        if source is not None and target is not None:
            attrs["edge"] = "1"
        else:
            attrs["vertex"] = "1"
        mxCell = ET.SubElement(root_cell, "mxCell", **attrs)
        geo_attrs: dict[str, str] = {}
        if source is not None and target is not None:
            geo_attrs["relative"] = "1"
        else:
            geo_attrs["x"] = str(x)
            geo_attrs["y"] = str(y)
            geo_attrs["width"] = str(w)
            geo_attrs["height"] = str(h)
        geo_attrs["as"] = "geometry"
        mxGeometry = ET.SubElement(mxCell, "mxGeometry", **geo_attrs)
        if cid in edge_points_by_id:
            points_el = ET.SubElement(mxGeometry, "Array", {"as": "points"})
            for px, py in edge_points_by_id[cid]:
                ET.SubElement(points_el, "mxPoint", x=str(px), y=str(py))

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode", xml_declaration=True)


# ── PNG export ───────────────────────────────────────────────────────────

def _set_render_dir_permissions(artifacts_dir: Path) -> None:
    """Set artifact dir ownership so hld-render user can write to it."""
    ids = _get_render_user_ids()
    if ids is None:
        return
    uid, gid = ids
    try:
        os.chown(str(artifacts_dir), uid, gid)
        for child in artifacts_dir.iterdir():
            os.chown(str(child), uid, gid)
    except OSError as exc:
        logger.warning("Failed to chown artifacts dir %s: %s", artifacts_dir, exc)


def export_png(drawio_path: Path, png_path: Path, cli_cmd: str) -> None:
    """Run draw.io CLI to export PNG as non-root user. Uses xvfb-run on Linux.

    Acquires EXPORT_SEMAPHORE to limit concurrent drawio processes.
    Drops to hld-render user via preexec_fn if available.
    """
    cmd_parts: list[str] = []
    if os.name == "posix" and shutil.which("xvfb-run"):
        cmd_parts.extend(["xvfb-run", "--auto-servernum", "--server-args=-screen 0 1280x1024x24"])
    cmd_parts.extend([
        cli_cmd,
        "--no-sandbox",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--export", "--format", "png",
        "--output", str(png_path),
        str(drawio_path),
    ])

    render_ids = _get_render_user_ids()
    preexec_fn = None
    env = os.environ.copy()
    # Electron/draw.io headless compat: disable GPU/SHM, suppress D-Bus
    env.pop("DBUS_SESSION_BUS_ADDRESS", None)
    if render_ids is not None:
        ensure_render_user_home()
        uid, gid = render_ids
        try:
            pw = pwd.getpwnam(HLD_RENDER_USER)
            home_dir = pw.pw_dir
        except KeyError:
            home_dir = f"/home/{HLD_RENDER_USER}"
        env["HOME"] = home_dir
        env.setdefault("XDG_CONFIG_HOME", f"{home_dir}/.config")
        env.setdefault("XDG_CACHE_HOME", f"{home_dir}/.cache")
        env.setdefault("XDG_DATA_HOME", f"{home_dir}/.local/share")
        def _drop_privs() -> None:
            os.setgid(gid)
            os.setuid(uid)
        preexec_fn = _drop_privs

    if not EXPORT_SEMAPHORE.acquire(timeout=30):
        raise RuntimeError("Too many concurrent draw.io export processes. Please retry later.")
    try:
        logger.info("Exporting PNG: %s (as user=%s)", " ".join(cmd_parts), HLD_RENDER_USER if render_ids else "current")
        result = subprocess.run(
            cmd_parts, capture_output=True, text=True, timeout=120,
            preexec_fn=preexec_fn, env=env,
        )
        stderr_snippet = (result.stderr or "")[:500]
        stdout_snippet = (result.stdout or "")[:200]

        # Check return code
        if result.returncode != 0:
            logger.error("draw.io export failed: rc=%d stderr=%s stdout=%s", result.returncode, stderr_snippet, stdout_snippet)
            if "Permission denied" in stderr_snippet or "permission" in stderr_snippet.lower():
                raise RuntimeError(f"draw.io export failed (permission denied): {stderr_snippet}")
            if "not found" in stderr_snippet.lower() or "No such file" in stderr_snippet:
                raise RuntimeError(f"draw.io CLI not found or path error: {stderr_snippet}")
            raise RuntimeError(f"draw.io export failed (rc={result.returncode}): {stderr_snippet}")

        # Verify artifact actually exists and is non-empty (draw.io can return rc=0 without writing a file)
        if not png_path.exists():
            logger.error("draw.io export reported success but PNG not created: path=%s rc=%d stderr=%s stdout=%s",
                         png_path, result.returncode, stderr_snippet, stdout_snippet)
            raise RuntimeError("draw.io export reported success but PNG artifact was not created")
        png_size = png_path.stat().st_size
        if png_size == 0:
            logger.error("draw.io export created empty PNG: path=%s rc=%d stderr=%s stdout=%s",
                         png_path, result.returncode, stderr_snippet, stdout_snippet)
            raise RuntimeError("draw.io export created an empty PNG artifact")

        logger.info("draw.io export succeeded: path=%s size=%d", png_path, png_size)
    finally:
        EXPORT_SEMAPHORE.release()


def repair_png(png_path: Path) -> bool:
    """Run repair_png.py on the exported PNG. Returns True if repaired.

    Best-effort: logs warning on failure, does not raise.
    """
    try:
        repair_script = VENDOR_DIR / "scripts" / "repair_png.py"
        result = subprocess.run(
            [sys.executable, str(repair_script), str(png_path)],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and "repaired" in result.stdout:
            logger.info("PNG repaired: %s", png_path)
            return True
        return False
    except Exception as exc:
        logger.warning("repair_png failed (best-effort, non-blocking): %s", exc)
        return False


# ── Full generation pipeline ─────────────────────────────────────────────

def generate_hld_design(
    requirements: HldRequirements,
    artifacts_dir: Path,
    *,
    cli_cmd: str,
    stage_callback: Callable[[str], None] | None = None,
) -> dict[str, str]:
    """Full generation pipeline. Returns dict with artifact paths.

    Args:
        requirements: Structured HLD requirements.
        artifacts_dir: Directory to write artifacts into.
        cli_cmd: Pre-validated draw.io CLI command.
        stage_callback: Optional callback invoked at each stage with stage name.

    Raises on failure.
    """
    def _stage(name: str) -> None:
        logger.info("HLD stage: %s", name)
        if stage_callback:
            stage_callback(name)

    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load style preset
    style_preset = _load_style_preset()

    # 2. Build LLM prompt and call LLM
    _stage("generate_spec")
    messages = build_hld_prompt(requirements, style_preset)
    client = build_chat_client_from_env(timeout=180.0)
    try:
        llm_output = client.complete_text(messages)
    except httpx.ReadTimeout as exc:
        raise RuntimeError("HLD LLM generation timed out while creating the architecture spec.") from exc
    logger.info("LLM output received (%d chars)", len(llm_output))

    # 3. Parse architecture spec JSON (with one retry on failure)
    _stage("parse_spec")
    try:
        spec = parse_architecture_spec(llm_output)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("First spec parse failed: %s. Retrying with correction prompt.", exc)
        correction_messages = messages + [
            {"role": "assistant", "content": llm_output},
            {"role": "user", "content": (
                f"The JSON you output was invalid: {exc}\n"
                "Please output a corrected Architecture Spec JSON that strictly follows the schema. "
                "No markdown fences, no explanation."
            )},
        ]
        try:
            llm_output = client.complete_text(correction_messages)
        except httpx.ReadTimeout as exc:
            raise RuntimeError("HLD LLM correction timed out while repairing the architecture spec.") from exc
        spec = parse_architecture_spec(llm_output)

    # 4. Render spec to .drawio XML
    _stage("render_drawio")
    xml_content = render_spec_to_drawio_xml(spec, style_preset)
    basename = _safe_filename(requirements.preferred_filename or requirements.project_name)
    drawio_path = artifacts_dir / f"{basename}.drawio"
    drawio_path.write_text(xml_content, encoding="utf-8")
    logger.info("Wrote .drawio: %s", drawio_path)

    # 4b. Set permissions so hld-render user can write PNG
    _set_render_dir_permissions(artifacts_dir)

    # 5. Export PNG
    _stage("export_png")
    png_path = artifacts_dir / f"{basename}.png"
    export_png(drawio_path, png_path, cli_cmd)
    logger.info("Wrote PNG: %s", png_path)

    # 5b. Verify both artifacts exist and are non-empty before proceeding
    for label, p in [(".drawio", drawio_path), ("PNG", png_path)]:
        if not p.exists() or p.stat().st_size == 0:
            raise RuntimeError(f"{label} artifact missing or empty after generation: {p}")

    # 6. Repair PNG (best-effort, never fails the task)
    _stage("repair_png")
    repair_png(png_path)

    _stage("completed")
    return {
        "drawio": str(drawio_path),
        "png": str(png_path),
        "basename": basename,
    }


def cleanup_artifacts(design_id: str) -> None:
    """Remove the artifacts directory for a design task."""
    artifacts_dir = ARTIFACTS_ROOT / design_id
    if artifacts_dir.exists():
        shutil.rmtree(artifacts_dir, ignore_errors=True)
