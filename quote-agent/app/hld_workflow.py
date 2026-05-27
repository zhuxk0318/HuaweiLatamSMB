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
    SUBNET_LABEL_SPACE,
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
# Lighter style inspired by huaweicloud-arch-drawio: boundary partitions,
# left-aligned labels, smaller headers, no heavy fill.
CONTAINER_STYLE_MAP: dict[str, dict[str, str]] = {
    "region":     {"outline": "#3771c8", "fill": "none",      "fontStyle": "0", "dashed": "1",   "dashPattern": "8 4",   "startSize": "18", "strokeWidth": "1"},
    "vpc":        {"outline": "#f85835", "fill": "none",      "fontStyle": "0", "dashed": "0",   "dashPattern": "",      "startSize": "18", "strokeWidth": "1"},
    "subnet":     {"outline": "#999999", "fill": "#f5f5f5",   "fontStyle": "0", "dashed": "1",   "dashPattern": "5 5",   "startSize": "0", "strokeWidth": "1"},
    "az":         {"outline": "#3298ff", "fill": "none",      "fontStyle": "0", "dashed": "1",   "dashPattern": "5 5",   "startSize": "16", "strokeWidth": "1"},
    "as_group":   {"outline": "#3298ff", "fill": "none",      "fontStyle": "0", "dashed": "1",   "dashPattern": "5 5",   "startSize": "16", "strokeWidth": "1"},
    "as_policy":  {"outline": "#3298ff", "fill": "none",      "fontStyle": "0", "dashed": "1",   "dashPattern": "5 5",   "startSize": "16", "strokeWidth": "1"},
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
EXTERNAL_ZONE_TITLE = "External"
EXTERNAL_ZONE_HEADER_H = 28
EXTERNAL_ZONE_ITEM_H = 52
EXTERNAL_ZONE_ITEM_GAP = 14
EXTERNAL_ZONE_PADDING = 18
REGION_DISPLAY_LABEL = "Huawei Cloud Region"


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
- vpc contains one or more az containers (for DR/HA) or subnet containers (for single-AZ)
- az contains one or more subnet containers (when DR/HA is required)
- subnet may optionally contain as_group or as_policy containers
- az must NOT be a child of subnet (az sits between vpc and subnet)
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


# Only explicit multi-AZ topology cues should trigger AZ container rendering.
_DR_KEYWORDS = re.compile(
    r"multi[\s-]?az|dual[\s-]?az|two[\s-]?az|2[\s-]?az|"
    r"active.?active\s+across\s+az|active.?standby\s+across\s+az|"
    r"跨az|双az|多az|双可用区|多可用区",
    re.IGNORECASE,
)


def _detect_dr_semantics(requirements: HldRequirements) -> bool:
    """Return True only for explicit multi-AZ topology requirements."""
    fields = [
        requirements.business_goal,
        requirements.architecture_boundary,
        requirements.core_components,
        requirements.data_stores_flow,
        requirements.network_security_boundary,
    ]
    return any(_DR_KEYWORDS.search(f) for f in fields if f)


# ── Semantic template detection ───────────────────────────────────────────

_SHARED_FILE_KEYWORDS = re.compile(
    r"shared\s+file|file\s+share|shared\s+storage|nas|nfs|sfs",
    re.IGNORECASE,
)

_HYBRID_KEYWORDS = re.compile(
    r"hybrid|on.?prem|on\s+premise|idc|data\s+center|local\s+dc|"
    r"专线|本地机房|private\s+line|dedicated\s+line",
    re.IGNORECASE,
)

_CCE_KEYWORDS = re.compile(
    r"cce|kubernetes|k8s|container|microservice|ingress",
    re.IGNORECASE,
)

# OBS is only appropriate when these semantics are present
_OBS_KEYWORDS = re.compile(
    r"object\s+storage|static\s+assets?|large\s+files?|media\s+archive|"
    r"big\s+data|analytics|log\s+archive|backup\s+archive|"
    r"data\s+lake|blob\s+storage|file\s+archive|"
    r"对象存储|大数据|日志归档|备份归档",
    re.IGNORECASE,
)

_BIG_DATA_KEYWORDS = re.compile(
    r"big\s+data|analytics|data\s+lake|data\s+warehouse|etl|elt|"
    r"dataarts|dws|dli|mrs|obs|cdm|lakehouse|"
    r"大数据|数据湖|数据仓库|数据分析|数据编排",
    re.IGNORECASE,
)


class SemanticFlags:
    """Lightweight flags detected from requirements text fields."""
    __slots__ = ("has_dr", "needs_shared_file", "is_hybrid", "prefers_cce")

    def __init__(self, *, has_dr: bool = False, needs_shared_file: bool = False,
                 is_hybrid: bool = False, prefers_cce: bool = False):
        self.has_dr = has_dr
        self.needs_shared_file = needs_shared_file
        self.is_hybrid = is_hybrid
        self.prefers_cce = prefers_cce

    def any_set(self) -> bool:
        return self.has_dr or self.needs_shared_file or self.is_hybrid or self.prefers_cce


def _detect_semantic_flags(requirements: HldRequirements) -> SemanticFlags:
    """Detect all semantic template flags from requirements text fields."""
    fields = [
        requirements.business_goal,
        requirements.architecture_boundary,
        requirements.core_components,
        requirements.data_stores_flow,
        requirements.network_security_boundary,
        requirements.external_integrations,
    ]
    text = " ".join(f for f in fields if f)
    return SemanticFlags(
        has_dr=_detect_dr_semantics(requirements),
        needs_shared_file=bool(_SHARED_FILE_KEYWORDS.search(text)),
        is_hybrid=bool(_HYBRID_KEYWORDS.search(text)),
        prefers_cce=bool(_CCE_KEYWORDS.search(text)),
    )


# ── Spec normalizer helpers ──────────────────────────────────────────────


def _normalize_obs_sdrs_cleanup(
    spec: dict,
    nodes: list[dict],
    edges: list[dict],
    node_by_id: dict[str, dict],
    requirements: HldRequirements,
) -> None:
    """Remove OBS nodes without object-storage semantics and strip unsupported DR/backup products."""
    # OBS gating: remove OBS nodes unless explicit object-storage semantics
    obs_nodes = [n for n in nodes if n.get("product") and n["product"].lower() == "obs"]
    if obs_nodes:
        req_fields = [
            requirements.business_goal,
            requirements.architecture_boundary,
            requirements.core_components,
            requirements.data_stores_flow,
            requirements.network_security_boundary,
            requirements.external_integrations,
        ]
        req_text = " ".join(f for f in req_fields if f)
        has_obs_semantics = bool(_OBS_KEYWORDS.search(req_text))
        if not has_obs_semantics:
            obs_ids = {n["id"] for n in obs_nodes}
            nodes[:] = [n for n in nodes if n["id"] not in obs_ids]
            edges[:] = [e for e in edges if e["source"] not in obs_ids and e["target"] not in obs_ids]
            for oid in obs_ids:
                node_by_id.pop(oid, None)

    # Unsupported default backup/DR products: strip SDRS and CSBS if they slipped through
    unsupported_nodes = [
        n for n in nodes
        if n.get("product") and n["product"].lower() in {"sdrs", "csbs"}
    ]
    if unsupported_nodes:
        unsupported_ids = {n["id"] for n in unsupported_nodes}
        nodes[:] = [n for n in nodes if n["id"] not in unsupported_ids]
        edges[:] = [e for e in edges if e["source"] not in unsupported_ids and e["target"] not in unsupported_ids]
        for nid in unsupported_ids:
            node_by_id.pop(nid, None)


# ── Spec normalizer ──────────────────────────────────────────────────────


def _normalize_spec(spec: dict, flags: SemanticFlags, requirements: HldRequirements) -> None:
    """Post-parse spec normalizer: inject/fix structure based on semantic flags.

    Mutates spec in-place. Runs after parse_architecture_spec validation.
    """
    containers = spec.get("containers", [])
    nodes = spec.get("nodes", [])
    edges = spec.get("edges", [])
    container_by_id = {c["id"]: c for c in containers}
    node_by_id = {n["id"]: n for n in nodes}
    node_ids = {n["id"] for n in nodes}

    # Helper: find a container by type
    def _find_container(ctype: str) -> dict | None:
        for c in containers:
            if c["container_type"] == ctype:
                return c
        return None

    # Helper: find data subnet id
    def _find_data_subnet() -> str | None:
        for c in containers:
            if c["container_type"] == "subnet":
                label = c.get("label", "").lower()
                if "data" in label or "db" in label:
                    return c["id"]
        return None

    # Helper: find app subnet id
    def _find_app_subnet() -> str | None:
        for c in containers:
            if c["container_type"] == "subnet":
                label = c.get("label", "").lower()
                if "app" in label or "application" in label:
                    return c["id"]
        return None

    def _find_frontend_subnet() -> str | None:
        for c in containers:
            if c["container_type"] == "subnet":
                label = c.get("label", "").lower()
                if any(token in label for token in ("front", "public", "ingress", "dmz", "web")):
                    return c["id"]
        return None

    def _requirements_text() -> str:
        req_fields = [
            requirements.business_goal,
            requirements.architecture_boundary,
            requirements.core_components,
            requirements.data_stores_flow,
            requirements.network_security_boundary,
            requirements.external_integrations,
        ]
        return " ".join(f for f in req_fields if f)

    def _is_big_data_scenario() -> bool:
        if _BIG_DATA_KEYWORDS.search(_requirements_text()):
            return True
        big_data_products = {
            "obs", "cdm", "cloud data migration (cdm)", "dataarts", "dataarts studio",
            "dws", "dli", "mrs",
        }
        return any((n.get("product") or "").lower() in big_data_products for n in nodes)

    # Helper: check if a product already exists among nodes
    def _has_product(product: str) -> bool:
        for n in nodes:
            p = n.get("product")
            if p is not None and p.lower() == product.lower():
                return True
        return False

    # Helper: next available id
    def _next_id(prefix: str) -> str:
        i = 1
        while f"{prefix}-{i}" in node_ids:
            i += 1
        nid = f"{prefix}-{i}"
        node_ids.add(nid)
        return nid

    def _ancestor_vpc_id(container_id: str | None) -> str | None:
        current = container_id
        while current and current in container_by_id:
            container = container_by_id[current]
            if container["container_type"] == "vpc":
                return current
            current = container.get("parent_id")
        return None

    def _normalize_big_data_layout() -> None:
        if not _is_big_data_scenario():
            return

        data_subnet_id = _find_data_subnet()
        if not data_subnet_id:
            return

        product_groups = {
            "storage": {"obs", "cdm", "cloud data migration (cdm)"},
            "analysis": {"dws", "dli", "mrs"},
            "orchestration": {"dataarts", "dataarts studio"},
            "compute": {"ecs", "cce", "cci"},
        }
        app_subnet_id = _find_app_subnet()

        for node in nodes:
            product = (node.get("product") or "").lower()
            label = node.get("label", "").lower()
            is_compute_node = (
                product in product_groups["compute"]
                or (node.get("type") == "service" and any(token in label for token in ("ecs", "cce", "cci")))
            )
            if product in product_groups["storage"] | product_groups["analysis"] | product_groups["orchestration"]:
                node["container_id"] = data_subnet_id
            elif (
                app_subnet_id
                and is_compute_node
                and "data" in container_by_id.get(node.get("container_id", ""), {}).get("label", "").lower()
            ):
                node["container_id"] = app_subnet_id

        def _has_edge(source: str, target: str) -> bool:
            return any(e["source"] == source and e["target"] == target for e in edges)

        storage_nodes = [n for n in nodes if (n.get("product") or "").lower() == "obs"]
        cdm_nodes = [n for n in nodes if (n.get("product") or "").lower() in {"cdm", "cloud data migration (cdm)"}]
        analysis_nodes = [n for n in nodes if (n.get("product") or "").lower() in product_groups["analysis"]]
        orchestration_nodes = [n for n in nodes if (n.get("product") or "").lower() in product_groups["orchestration"]]
        if cdm_nodes and storage_nodes and not _has_edge(cdm_nodes[0]["id"], storage_nodes[0]["id"]):
            edges.append({"source": cdm_nodes[0]["id"], "target": storage_nodes[0]["id"], "label": "", "edge_kind": "traffic"})
        if storage_nodes and analysis_nodes and not _has_edge(storage_nodes[0]["id"], analysis_nodes[0]["id"]):
            edges.append({"source": storage_nodes[0]["id"], "target": analysis_nodes[0]["id"], "label": "", "edge_kind": "traffic"})
        if analysis_nodes and orchestration_nodes and not _has_edge(analysis_nodes[0]["id"], orchestration_nodes[0]["id"]):
            edges.append({"source": analysis_nodes[0]["id"], "target": orchestration_nodes[0]["id"], "label": "", "edge_kind": "traffic"})

    def _normalize_ingress_node_placement() -> None:
        frontend_subnet_id = _find_frontend_subnet()
        if not frontend_subnet_id:
            return
        root_region_id = next(
            (c["id"] for c in containers if c["container_type"] == "region" and c.get("parent_id") is None),
            None,
        )

        ingress_products = {"cdn", "elb", "waf", "nat gateway", "nat", "apig", "vpn", "direct connect", "dc"}
        ingress_labels = ("cdn", "elb", "waf", "nat", "api gateway", "apig", "vpn", "direct connect")

        for node in nodes:
            product = (node.get("product") or "").lower()
            label = node.get("label", "").lower()
            if product not in ingress_products and not any(token in label for token in ingress_labels):
                continue

            cid = node.get("container_id")
            if cid is None or cid == root_region_id:
                node["container_id"] = frontend_subnet_id
                continue

            container = container_by_id.get(cid)
            if container and container["container_type"] in {"region", "vpc"}:
                node["container_id"] = frontend_subnet_id

    def _collapse_az_to_single_az() -> None:
        """Flatten accidental AZ containers back to region -> vpc -> subnet -> node."""
        az_containers = [c for c in containers if c["container_type"] == "az"]
        if not az_containers:
            return

        region = next(
            (c for c in containers if c["container_type"] == "region" and c.get("parent_id") is None),
            None,
        )
        if not region:
            return

        container_by_id_local = {c["id"]: c for c in containers}
        keep_az = az_containers[0]
        keep_vpc = next(
            (c for c in containers if c["container_type"] == "vpc" and c.get("parent_id") == keep_az["id"]),
            None,
        )
        if keep_vpc:
            keep_vpc["parent_id"] = region["id"]

        removed_az_ids = {c["id"] for c in az_containers}
        removed_vpc_ids: set[str] = set()

        for c in containers:
            if c["container_type"] == "vpc" and c.get("parent_id") in removed_az_ids:
                if keep_vpc and c["id"] == keep_vpc["id"]:
                    continue
                removed_vpc_ids.add(c["id"])
                for subnet in containers:
                    if subnet["container_type"] == "subnet" and subnet.get("parent_id") == c["id"] and keep_vpc:
                        # Do not remap duplicate AZ2 subnets back into the kept VPC.
                        removed_vpc_ids.add(subnet["id"])

        removed_container_ids = removed_az_ids | removed_vpc_ids

        for c in containers:
            if c["container_type"] == "subnet" and c.get("parent_id") == keep_az["id"] and keep_vpc:
                c["parent_id"] = keep_vpc["id"]

        nodes[:] = [
            n for n in nodes
            if n.get("container_id") not in removed_container_ids
        ]
        node_by_id.clear()
        node_by_id.update({n["id"]: n for n in nodes})
        node_ids.clear()
        node_ids.update(n["id"] for n in nodes)

        edges[:] = [
            e for e in edges
            if e.get("edge_kind") != "replication"
            and e["source"] in node_ids
            and e["target"] in node_ids
        ]

        containers[:] = [
            c for c in containers
            if c["id"] not in removed_container_ids and c["id"] != keep_az["id"]
        ]
        container_by_id.clear()
        container_by_id.update({c["id"]: c for c in containers})

    if not flags.any_set():
        _collapse_az_to_single_az()
        _normalize_big_data_layout()
        _normalize_ingress_node_placement()
        # Still run OBS/SDRS cleanup even without semantic flags
        _normalize_obs_sdrs_cleanup(spec, nodes, edges, node_by_id, requirements)
        return

    # ── DR: ensure 2AZ structure with correct hierarchy (region → az → vpc → subnet) ──
    if flags.has_dr:
        has_az = any(c["container_type"] == "az" for c in containers)
        if not has_az:
            _inject_dr_az_containers(spec, container_by_id, node_by_id)
            node_ids.update(n["id"] for n in nodes)
    else:
        _collapse_az_to_single_az()

    # ── Shared file: ensure SFS node exists ──
    if flags.needs_shared_file:
        if not _has_product("SFS") and not _has_product("SFS Turbo"):
            data_subnet_id = _find_data_subnet()
            if data_subnet_id:
                sfs_id = _next_id("sfs")
                sfs_node = {
                    "id": sfs_id,
                    "label": "SFS Turbo",
                    "type": "service",
                    "container_id": data_subnet_id,
                    "product": "SFS Turbo",
                }
                nodes.append(sfs_node)
                node_by_id[sfs_id] = sfs_node
                # Connect from app-layer services to SFS
                app_subnet_id = _find_app_subnet()
                if app_subnet_id:
                    app_services = [n for n in nodes if n.get("container_id") == app_subnet_id and n.get("type") == "service"]
                    if app_services:
                        edges.append({
                            "source": app_services[0]["id"],
                            "target": sfs_id,
                            "label": "mount",
                            "edge_kind": "traffic",
                        })

    # ── Hybrid: ensure external side + VPN/DC connection ──
    if flags.is_hybrid:
        # Check for existing external nodes
        external_nodes = [n for n in nodes if n.get("type") == "external"]
        if not external_nodes:
            # Inject an on-prem external node
            onprem_id = _next_id("onprem")
            onprem_node = {
                "id": onprem_id,
                "label": "On-Prem IDC",
                "type": "external",
                "container_id": "outside",
                "product": None,
            }
            nodes.append(onprem_node)
            node_by_id[onprem_id] = onprem_node
            external_nodes = [onprem_node]

        # External data ingestion into CDM should stay direct, without auto-added VPN/DC.
        has_cdm_ingest = bool(external_nodes) and any(
            (n.get("product") or "").lower() in {"cdm", "cloud data migration (cdm)"}
            for n in nodes
        )
        if has_cdm_ingest:
            pass
        # Check for VPN or Direct Connect node
        has_vpn_or_dc = _has_product("VPN") or _has_product("Direct Connect") or _has_product("DC")
        if not has_cdm_ingest and not has_vpn_or_dc:
            # Inject a VPN gateway in the frontend subnet
            fe_subnet = None
            for c in containers:
                if c["container_type"] == "subnet":
                    label = c.get("label", "").lower()
                    if "frontend" in label or "public" in label or "ingress" in label:
                        fe_subnet = c
                        break
            if not fe_subnet:
                fe_subnet = _find_container("subnet")
            if fe_subnet:
                vpn_id = _next_id("vpn")
                vpn_node = {
                    "id": vpn_id,
                    "label": "VPN",
                    "type": "gateway",
                    "container_id": fe_subnet["id"],
                    "product": "VPN",
                }
                nodes.append(vpn_node)
                node_by_id[vpn_id] = vpn_node
                # Add edge from external to VPN
                edges.append({
                    "source": external_nodes[0]["id"],
                    "target": vpn_id,
                    "label": "VPN Tunnel",
                    "edge_kind": "traffic",
                })

    # ── CCE: prefer CCE over ECS for container/microservice scenarios ──
    if flags.prefers_cce:
        if not _has_product("CCE"):
            # Find first ECS-like node in app subnet and replace with CCE
            app_subnet_id = _find_app_subnet()
            if app_subnet_id:
                for n in nodes:
                    is_ecs = (n.get("product") == "ECS" or
                              (n.get("product") is None and "ecs" in n.get("label", "").lower()))
                    if is_ecs and n.get("container_id") == app_subnet_id:
                        n["product"] = "CCE"
                        n["label"] = "CCE"
                        break

    _normalize_big_data_layout()
    _normalize_ingress_node_placement()

    # ── OBS gating + SDRS/CSBS removal (always runs) ──
    _normalize_obs_sdrs_cleanup(spec, nodes, edges, node_by_id, requirements)


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
        "- Unless the requirements explicitly ask for multi-AZ / dual-AZ deployment, do NOT create any az containers; keep single-AZ structure as region -> vpc -> subnet -> node\n"
        f"- Prefer template=\"{template_hint}\" for this deployment mode\n"
    )

    # DR/HA-specific constraints: force 2AZ structure
    flags = _detect_semantic_flags(requirements)
    if flags.has_dr:
        system_msg += (
            "\n\n## CRITICAL: Disaster Recovery / High Availability Requirements Detected\n"
            "You MUST generate a two-AZ (Availability Zone) architecture:\n"
            "- Add two containers with container_type=\"az\" as children of the region: one labeled \"AZ1\" and one labeled \"AZ2\"\n"
            "- AZ containers sit BETWEEN region and VPC: region → az → vpc → subnet → node\n"
            "- Each AZ must contain its own VPC with matching subnets under that VPC\n"
            "- AZ2 should mirror AZ1's nodes and icons as a standby copy\n"
            "- Use edge_kind=\"replication\" edges ONLY between nodes in different AZ containers (e.g. primary in AZ1 → standby in AZ2)\n"
            "- NEVER create a replication edge where source equals target (self-loop)\n"
            "- Keep replication/sync expression minimal; a single clear cross-AZ line is preferred over many parallel lines\n"
            "- Do NOT place AZ containers inside subnets or VPCs — AZ must be a child of the region\n"
            "- Do NOT include SDRS or CSBS — use CBR for backup if backup is needed\n"
        )

    if flags.needs_shared_file:
        system_msg += (
            "\n\n## Shared File Storage Requirement Detected\n"
            "- Include an SFS Turbo node (product=\"SFS Turbo\") in the data subnet\n"
            "- Do NOT substitute OBS for shared file storage — use SFS Turbo instead\n"
            "- Add a traffic edge from application services to the SFS Turbo node\n"
        )

    if flags.is_hybrid:
        system_msg += (
            "\n\n## Hybrid / On-Premise Connectivity Requirement Detected\n"
            "- Include an external node (type=\"external\") for the on-premise / IDC side\n"
            "- Include a VPN or Direct Connect gateway node in the frontend subnet\n"
            "- Add a traffic edge from the external node to the VPN/DC gateway\n"
        )

    if flags.prefers_cce:
        system_msg += (
            "\n\n## Container / Microservice Requirement Detected\n"
            "- Use CCE (Cloud Container Engine) as the primary compute node, NOT plain ECS\n"
            "- Typical pattern: ELB/WAF → CCE → data/cache\n"
            "- Set product=\"CCE\" on the container compute node\n"
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


# ── DR normalization helper ──────────────────────────────────────────────


def _inject_dr_az_containers(
    spec: dict,
    container_by_id: dict[str, dict],
    node_by_id: dict[str, dict],
) -> None:
    """Inject a minimal 2AZ DR structure using region → az → vpc → subnet → node."""
    containers = spec["containers"]
    nodes = spec["nodes"]
    edges = spec["edges"]
    region = next(
        (c for c in containers if c["container_type"] == "region" and c.get("parent_id") is None),
        None,
    )
    if not region:
        return

    source_vpc = next(
        (c for c in containers if c["container_type"] == "vpc" and c.get("parent_id") == region["id"]),
        None,
    )
    if not source_vpc:
        return

    def _unique_container_id(base: str) -> str:
        candidate = base
        index = 2
        while candidate in container_by_id:
            candidate = f"{base}-{index}"
            index += 1
        return candidate

    def _unique_node_id(base: str) -> str:
        candidate = base
        existing = {n["id"] for n in nodes}
        index = 2
        while candidate in existing:
            candidate = f"{base}-{index}"
            index += 1
        return candidate

    def _container_depth(cid: str) -> int:
        depth = 0
        current = container_by_id.get(cid)
        while current and current.get("parent_id"):
            depth += 1
            current = container_by_id.get(current["parent_id"])
        return depth

    def _is_descendant_of(container_id: str, ancestor_id: str) -> bool:
        current = container_by_id.get(container_id)
        while current:
            if current["id"] == ancestor_id:
                return True
            pid = current.get("parent_id")
            current = container_by_id.get(pid) if pid else None
        return False

    def _find_data_like_subnet(vpc_id: str) -> str | None:
        candidates = [
            c for c in containers
            if c["container_type"] == "subnet"
            and c.get("parent_id") == vpc_id
            and ("data" in c.get("label", "").lower() or "db" in c.get("label", "").lower() or "storage" in c.get("label", "").lower())
        ]
        return candidates[0]["id"] if candidates else None

    def _ancestor_of_type(container_id: str, target_type: str) -> str | None:
        current = container_by_id.get(container_id)
        while current:
            if current["container_type"] == target_type:
                return current["id"]
            pid = current.get("parent_id")
            current = container_by_id.get(pid) if pid else None
        return None

    # Remove existing replication edges; the normalized DR view should use a single clear cross-AZ line.
    edges[:] = [e for e in edges if e.get("edge_kind") != "replication"]

    az1_id = _unique_container_id("az-1")
    az2_id = _unique_container_id("az-2")
    az1 = {"id": az1_id, "label": "AZ1", "container_type": "az", "parent_id": region["id"]}
    az2 = {"id": az2_id, "label": "AZ2", "container_type": "az", "parent_id": region["id"]}
    containers.append(az1)
    containers.append(az2)
    container_by_id[az1_id] = az1
    container_by_id[az2_id] = az2

    # Reparent the original VPC under AZ1 and clone its full subtree under AZ2.
    source_vpc["parent_id"] = az1_id
    cloned_vpc_id = _unique_container_id(f"{source_vpc['id']}-az2")
    cloned_vpc = {
        "id": cloned_vpc_id,
        "label": source_vpc["label"],
        "container_type": "vpc",
        "parent_id": az2_id,
    }
    containers.append(cloned_vpc)
    container_by_id[cloned_vpc_id] = cloned_vpc

    container_clone_map: dict[str, str] = {source_vpc["id"]: cloned_vpc_id}
    descendant_containers = [
        c for c in containers
        if c["id"] not in {az1_id, az2_id, cloned_vpc_id}
        and _is_descendant_of(c["id"], source_vpc["id"])
        and c["id"] != source_vpc["id"]
    ]
    descendant_containers.sort(key=lambda c: _container_depth(c["id"]))

    for original in descendant_containers:
        cloned_id = _unique_container_id(f"{original['id']}-az2")
        cloned_parent = container_clone_map.get(original["parent_id"])
        if not cloned_parent:
            continue
        cloned = {
            "id": cloned_id,
            "label": original["label"],
            "container_type": original["container_type"],
            "parent_id": cloned_parent,
        }
        containers.append(cloned)
        container_by_id[cloned_id] = cloned
        container_clone_map[original["id"]] = cloned_id

    source_nodes = [
        n for n in list(nodes)
        if n.get("container_id") in container_clone_map or _is_descendant_of(n.get("container_id", ""), source_vpc["id"])
    ]
    node_clone_map: dict[str, str] = {}
    for node in source_nodes:
        cloned_container_id = container_clone_map.get(node.get("container_id", ""))
        if not cloned_container_id:
            continue
        cloned_node_id = _unique_node_id(f"{node['id']}-az2")
        cloned_label = node["label"]
        cloned_node = {
            "id": cloned_node_id,
            "label": cloned_label[:MAX_LABEL_LEN],
            "type": node.get("type", "service"),
            "container_id": cloned_container_id,
            "product": node.get("product"),
        }
        nodes.append(cloned_node)
        node_by_id[cloned_node_id] = cloned_node
        node_clone_map[node["id"]] = cloned_node_id

    # Keep backup in the data/storage subnet if it exists, and strip unsupported products.
    for node in nodes:
        product = (node.get("product") or "").lower()
        if product == "cbr":
            current_cid = node.get("container_id", "")
            current_container = container_by_id.get(current_cid)
            if current_container and current_container["container_type"] != "subnet":
                target_subnet = _find_data_like_subnet(_ancestor_of_type(current_cid, "vpc") or source_vpc["id"])
                if target_subnet:
                    node["container_id"] = target_subnet

    # Prefer a single database/storage replication line; fall back to the first cloned node.
    primary_id = None
    standby_id = None
    preferred_types = ("database",)
    for preferred_type in preferred_types:
        for node in source_nodes:
            if node.get("type") == preferred_type and node["id"] in node_clone_map:
                primary_id = node["id"]
                standby_id = node_clone_map[node["id"]]
                break
        if primary_id:
            break
    if not primary_id:
        for node in source_nodes:
            if node["id"] in node_clone_map:
                primary_id = node["id"]
                standby_id = node_clone_map[node["id"]]
                break

    if primary_id and standby_id:
        edges.append({
            "source": primary_id,
            "target": standby_id,
            "label": "DR Sync",
            "edge_kind": "replication",
        })


def _repair_generated_template_spec(spec: dict) -> None:
    """Apply small deterministic repairs before strict validation.

    This is intentionally narrow and only handles:
    - legacy DR hierarchy emitted as region -> vpc -> az -> subnet
    - replication edges that point to non-node placeholders like subnet-data-dr
    - replication self-loops such as rds -> rds
    """
    containers = spec.get("containers") or []
    nodes = spec.get("nodes") or []
    edges = spec.get("edges") or []
    if not containers:
        return

    container_by_id = {c["id"]: c for c in containers}
    region = next(
        (c for c in containers if c.get("parent_id") is None and c.get("container_type") == "region"),
        None,
    )
    if region:
        # Repair legacy region -> vpc -> az -> subnet into region -> az -> vpc -> subnet.
        root_vpcs = [
            c for c in containers
            if c.get("container_type") == "vpc" and c.get("parent_id") == region["id"]
        ]
        for vpc in list(root_vpcs):
            az_children = [
                c for c in containers
                if c.get("container_type") == "az" and c.get("parent_id") == vpc["id"]
            ]
            if not az_children:
                continue

            def _unique_container_id(base: str) -> str:
                candidate = base
                index = 2
                while candidate in container_by_id:
                    candidate = f"{base}-{index}"
                    index += 1
                return candidate

            first_az = az_children[0]
            first_az["parent_id"] = region["id"]
            vpc["parent_id"] = first_az["id"]

            for subnet in containers:
                if subnet.get("container_type") == "subnet" and subnet.get("parent_id") == first_az["id"]:
                    subnet["parent_id"] = vpc["id"]

            for az in az_children[1:]:
                az["parent_id"] = region["id"]
                cloned_vpc_id = _unique_container_id(f"{vpc['id']}-{az['id']}")
                cloned_vpc = {
                    "id": cloned_vpc_id,
                    "label": vpc["label"],
                    "container_type": "vpc",
                    "parent_id": az["id"],
                }
                containers.append(cloned_vpc)
                container_by_id[cloned_vpc_id] = cloned_vpc
                for subnet in containers:
                    if subnet.get("container_type") == "subnet" and subnet.get("parent_id") == az["id"]:
                        subnet["parent_id"] = cloned_vpc_id

    node_ids = {n["id"] for n in nodes}
    container_ids = {c["id"] for c in containers}
    repaired_edges: list[dict] = []
    for edge in edges:
        src = edge.get("source")
        tgt = edge.get("target")
        kind = edge.get("edge_kind", "traffic")
        if kind == "replication":
            if src == tgt:
                logger.warning(
                    "Dropping replication self-loop %s -> %s during pre-parse repair",
                    src, tgt,
                )
                continue
            unknown_src = src not in node_ids and src not in container_ids
            unknown_tgt = tgt not in node_ids and tgt not in container_ids
            if unknown_src or unknown_tgt:
                logger.warning(
                    "Dropping invalid replication edge %s -> %s during pre-parse repair",
                    src, tgt,
                )
                continue
        repaired_edges.append(edge)
    spec["edges"] = repaired_edges


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

    if "containers" in spec and "template" in spec:
        _repair_generated_template_spec(spec)

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

        # Build container_by_id early for hierarchy validation
        container_by_id = {c["id"]: c for c in containers}

        # AZ containers must be direct children of region, not VPC/subnet.
        for c in containers:
            if c["container_type"] == "az":
                pid = c.get("parent_id")
                if pid:
                    parent = container_by_id.get(pid)
                    if parent and parent["container_type"] != "region":
                        raise ValueError(
                            f"AZ container '{c['id']}' must not be a child of {parent['container_type']} '{pid}'. "
                            "AZ must be a child of region (region → az → vpc → subnet)."
                        )

        # If AZ containers are present, VPCs must sit under AZs rather than directly under region.
        has_az_container = any(c["container_type"] == "az" for c in containers)
        for c in containers:
            if c["container_type"] == "vpc":
                pid = c.get("parent_id")
                if not pid:
                    continue
                parent = container_by_id.get(pid)
                if parent and parent["container_type"] not in {"region", "az"}:
                    raise ValueError(
                        f"VPC container '{c['id']}' must be under region or az, got {parent['container_type']} '{pid}'."
                    )
                if has_az_container and parent and parent["container_type"] == "region":
                    raise ValueError(
                        f"VPC container '{c['id']}' must be a child of az when AZ containers are present."
                    )

        # Build parent chain for hierarchy checks
        # (container_by_id already built above for AZ validation)

        def _ancestor_types(cid: str) -> list[str]:
            types = []
            cur = container_by_id.get(cid)
            while cur:
                types.append(cur["container_type"])
                pid = cur.get("parent_id")
                cur = container_by_id.get(pid) if pid else None
            return types

        def _ancestor_container_type(cid: str, target_type: str, cbid: dict) -> str | None:
            cur = cbid.get(cid)
            while cur:
                if cur["container_type"] == target_type:
                    return cur["id"]
                pid = cur.get("parent_id")
                cur = cbid.get(pid) if pid else None
            return None

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
            product = (node.get("product") or "").lower()
            label_lower = node.get("label", "").lower()
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

            # database nodes must be in a data/db subnet (directly or via az/as_group/as_policy)
            if node["type"] == "database":
                container = container_by_id.get(cid)
                # Walk up to find the enclosing subnet
                subnet_ancestor = None
                cur = container
                while cur:
                    if cur["container_type"] == "subnet":
                        subnet_ancestor = cur
                        break
                    pid = cur.get("parent_id")
                    cur = container_by_id.get(pid) if pid else None
                if not subnet_ancestor:
                    raise ValueError(f"Database node {node['id']} must be inside a subnet container (directly or via az/as_group)")
                subnet_label = subnet_ancestor.get("label", "").lower()
                if "data" not in subnet_label and "db" not in subnet_label:
                    raise ValueError(f"Database node {node['id']} must be in a data/db subnet, got '{subnet_ancestor.get('label')}'")

            # Warn if non-external node lacks product field (needed for icon rendering)
            if not node.get("product"):
                logger.warning("Node %s (type=%s) missing 'product' field — will use generic shape fallback", node["id"], node["type"])

            ingress_products = {"cdn", "elb", "waf", "nat gateway", "nat", "apig", "vpn", "direct connect", "dc"}
            ingress_labels = ("cdn", "elb", "waf", "nat", "api gateway", "apig", "vpn", "direct connect")
            is_ingress_node = (
                node["type"] == "gateway"
                or product in ingress_products
                or any(token in label_lower for token in ingress_labels)
            )
            if is_ingress_node:
                cur = container_by_id.get(cid)
                subnet_ancestor = None
                while cur:
                    if cur["container_type"] == "subnet":
                        subnet_ancestor = cur
                        break
                    pid = cur.get("parent_id")
                    cur = container_by_id.get(pid) if pid else None
                if not subnet_ancestor:
                    raise ValueError(
                        f"Ingress/gateway node {node['id']} must be inside a frontend/public subnet, not directly under region/vpc."
                    )

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

            # Reject replication self-loops (source == target)
            if kind == "replication" and edge["source"] == edge["target"]:
                raise ValueError(
                    f"Replication self-loop detected: edge '{edge.get('label', '')}' "
                    f"has source == target == '{edge['source']}'. "
                    "Replication edges must connect different nodes (e.g. primary in AZ1 → standby in AZ2)."
                )

            # Replication edges must be cross-AZ (source and target in different AZs)
            if kind == "replication":
                src_node = node_by_id.get(edge["source"])
                tgt_node = node_by_id.get(edge["target"])
                if src_node and tgt_node:
                    src_az = _ancestor_container_type(src_node.get("container_id", ""), "az", container_by_id)
                    tgt_az = _ancestor_container_type(tgt_node.get("container_id", ""), "az", container_by_id)
                    if src_az and tgt_az and src_az == tgt_az:
                        raise ValueError(
                            f"Replication edge '{edge.get('label', '')}' connects nodes in the same AZ "
                            f"('{src_az}'). Replication edges must be cross-AZ."
                        )

        # DR normalization: if any replication edge exists but no az container,
        # inject AZ1/AZ2 containers and redistribute nodes.
        has_replication = any(e.get("edge_kind") == "replication" for e in spec["edges"])
        has_az = any(c["container_type"] == "az" for c in containers)
        if has_replication and not has_az:
            logger.warning(
                "Spec has replication edges but no AZ containers — injecting AZ1/AZ2 for DR structure"
            )
            _inject_dr_az_containers(spec, container_by_id, node_by_id)

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

    def _compute_edge_waypoints(
        src_box: tuple[int, int, int, int],
        tgt_box: tuple[int, int, int, int],
        exit_hint: str,
        entry_hint: str,
        obstacles: list[tuple[int, int, int, int]],
    ) -> list[tuple[int, int]]:
        src_anchor = _anchor_point(src_box, _parse_anchor(exit_hint, "exit"))
        tgt_anchor = _anchor_point(tgt_box, _parse_anchor(entry_hint, "entry"))

        if "exitY=" in exit_hint:
            mid_y = (src_anchor[1] + tgt_anchor[1]) // 2
            points = [
                (src_anchor[0], mid_y),
                (tgt_anchor[0], mid_y),
            ]
        else:
            mid_x = (src_anchor[0] + tgt_anchor[0]) // 2
            points = [
                (mid_x, src_anchor[1]),
                (mid_x, tgt_anchor[1]),
            ]

        deduped: list[tuple[int, int]] = []
        for point in points:
            if not deduped or deduped[-1] != point:
                deduped.append(point)
        return deduped

    def _compute_external_zone_waypoints(
        src_box: tuple[int, int, int, int],
        tgt_box: tuple[int, int, int, int],
    ) -> list[tuple[int, int]]:
        src_anchor = (src_box[0] + src_box[2], src_box[1] + src_box[3] // 2)
        tgt_anchor = (tgt_box[0], tgt_box[1] + tgt_box[3] // 2)
        corridor_x = (src_anchor[0] + tgt_anchor[0]) // 2
        points = [
            (corridor_x, src_anchor[1]),
            (corridor_x, tgt_anchor[1]),
        ]
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
        container_title_size = title_font_size - 2
        if ctype == "subnet":
            parts = [
                "rounded=1",
                "html=1",
                "collapsible=0",
                "absoluteArcSize=1",
                "arcSize=12",
                f"fillColor={cs['fill']}",
                f"strokeColor={cs['outline']}",
                f"strokeWidth={cs.get('strokeWidth', '1')}",
                f"fontStyle={cs['fontStyle']}",
                f"fontFamily={font_family}",
                f"fontSize={container_title_size}",
                "verticalAlign=top",
                "align=left",
                "spacingLeft=10",
                "spacingTop=2",
            ]
            if cs["dashed"] == "1":
                parts.append("dashed=1")
                parts.append(f"dashPattern={cs['dashPattern']}")
            return ";".join(parts)

        # Lighter container: rounded corners, left-aligned label, smaller title
        base = "swimlane;html=1;collapsible=0;swimlaneLine=0;rounded=1;absoluteArcSize=1;arcSize=12;"
        parts = [
            f"startSize={cs['startSize']}",
            f"fillColor={cs['fill']}",
            f"strokeColor={cs['outline']}",
            f"strokeWidth={cs.get('strokeWidth', '1')}",
            f"fontStyle={cs['fontStyle']}",
            f"fontFamily={font_family}",
            f"fontSize={container_title_size}",
            "verticalAlign=top",
            "align=left",
            "spacingLeft=10",
            "spacingTop=4",
        ]
        if cs["dashed"] == "1":
            parts.append("dashed=1")
            parts.append(f"dashPattern={cs['dashPattern']}")
        return base + ";".join([""] + parts)

    def _container_start_size(ctype: str) -> int:
        if ctype == "subnet":
            return max(SUBNET_LABEL_SPACE - CONTAINER_TITLE_GAP, 0)
        return int(CONTAINER_STYLE_MAP[ctype]["startSize"])

    def _container_header_height(ctype: str) -> int:
        if ctype == "subnet":
            return SUBNET_LABEL_SPACE
        return int(CONTAINER_STYLE_MAP[ctype]["startSize"]) + CONTAINER_TITLE_GAP

    def _node_layer_rank(node: dict, container_id: str) -> tuple[int, str]:
        label = container_by_id.get(container_id, {}).get("label", "").lower()
        product = (node.get("product") or "").lower()
        if any(k in label for k in ("data", "db", "storage")):
            if product in {"dataarts", "dataarts studio"}:
                return (0, node["label"].lower())
            if product in {"dws", "dli", "mrs"}:
                return (1, node["label"].lower())
            if product in {"obs", "cdm", "cloud data migration (cdm)"}:
                return (2, node["label"].lower())
        return (1, node["label"].lower())

    def _is_big_data_data_container(cid: str, container_nodes: list[dict]) -> bool:
        label = container_by_id.get(cid, {}).get("label", "").lower()
        if not any(k in label for k in ("data", "db", "storage")):
            return False
        products = {(n.get("product") or "").lower() for n in container_nodes}
        return bool(products & {"obs", "cdm", "cloud data migration (cdm)", "dws", "dli", "mrs", "dataarts", "dataarts studio"})

    def _layout_big_data_nodes(
        cid: str,
        container_nodes: list[dict],
        *,
        start_x: int,
        start_y: int,
    ) -> list[tuple[dict, int, int, int, int]]:
        orchestration = [n for n in container_nodes if (n.get("product") or "").lower() in {"dataarts", "dataarts studio"}]
        analysis = [n for n in container_nodes if (n.get("product") or "").lower() in {"dws", "dli", "mrs"}]
        storage = [n for n in container_nodes if (n.get("product") or "").lower() in {"obs", "cdm", "cloud data migration (cdm)"}]
        others = [
            n for n in container_nodes
            if n not in orchestration and n not in analysis and n not in storage
        ]
        rows = [orchestration, analysis + others, storage]

        placed: list[tuple[dict, int, int, int, int]] = []
        cur_y = start_y
        for row in rows:
            if not row:
                continue
            cur_x = start_x
            row_h = 0
            for node in row:
                nw, nh = measure_node_box(node)
                placed.append((node, cur_x, cur_y, nw, nh))
                cur_x += nw + NODE_GAP_X
                row_h = max(row_h, nh)
            cur_y += row_h + NODE_GAP_Y
        return placed

    # --- Template-driven rendering (containers) ---
    is_template_spec = "containers" in spec and "template" in spec

    if is_template_spec:
        containers = [dict(c) for c in spec["containers"]]
        nodes = [dict(n) for n in nodes]
        edges = [dict(e) for e in edges]

        def _next_local_node_id(base: str) -> str:
            candidate = base
            existing = {n["id"] for n in nodes}
            index = 2
            while candidate in existing:
                candidate = f"{base}-{index}"
                index += 1
            return candidate

        def _flatten_as_group_containers() -> None:
            """Render AS groups as a single AS icon instead of a dashed container."""
            as_groups = [c for c in containers if c["container_type"] == "as_group"]
            if not as_groups:
                return

            group_parent: dict[str, str] = {}
            group_icon_node: dict[str, str] = {}
            member_to_group: dict[str, str] = {}
            original_nodes = list(nodes)

            for group in as_groups:
                parent_id = group.get("parent_id")
                if not parent_id:
                    continue
                group_parent[group["id"]] = parent_id
                icon_id = _next_local_node_id(f"{group['id']}-icon")
                icon_node = {
                    "id": icon_id,
                    "label": "AS",
                    "type": "service",
                    "container_id": parent_id,
                    "product": "AS",
                }
                nodes.append(icon_node)
                group_icon_node[group["id"]] = icon_id

                for node in original_nodes:
                    if node.get("container_id") == group["id"]:
                        node["container_id"] = parent_id
                        member_to_group[node["id"]] = group["id"]

                for child in containers:
                    if child.get("parent_id") == group["id"]:
                        child["parent_id"] = parent_id

            rewritten_edges: list[dict] = []
            for edge in edges:
                src_group = member_to_group.get(edge["source"])
                tgt_group = member_to_group.get(edge["target"])
                if src_group and tgt_group and src_group == tgt_group:
                    continue
                new_edge = dict(edge)
                if src_group:
                    new_edge["source"] = group_icon_node[src_group]
                if tgt_group:
                    new_edge["target"] = group_icon_node[tgt_group]
                if new_edge["source"] == new_edge["target"]:
                    continue
                rewritten_edges.append(new_edge)

            edges[:] = rewritten_edges
            containers[:] = [c for c in containers if c["container_type"] != "as_group"]

        _flatten_as_group_containers()
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
        container_positions: dict[str, tuple[int, int, int, int]] = {}
        # Track node positions for edge routing: node_id -> (x, y, w, h) absolute
        node_positions: dict[str, tuple[int, int, int, int]] = {}

        _size_cache: dict[str, tuple[int, int]] = {}

        def _compute_container_size(cid: str) -> tuple[int, int]:
            if cid in _size_cache:
                return _size_cache[cid]
            child_ids = children_of.get(cid, [])
            child_nodes = sorted(nodes_by_container.get(cid, []), key=lambda n: _node_layer_rank(n, cid))
            ctype = container_by_id[cid]["container_type"]
            start_size = _container_start_size(ctype)

            # Sort subnets by semantic layer so size matches render order
            if ctype == "vpc":
                child_ids = sorted(
                    child_ids,
                    key=lambda ch: subnet_layer_rank(container_by_id[ch].get("label", "")),
                )

            child_sizes = [_compute_container_size(ch) for ch in child_ids]
            # VPC always stacks subnets vertically. Containers whose direct
            # children are AZs should keep AZ1/AZ2 side-by-side even in LR diagrams.
            has_az_children = bool(child_ids) and all(
                container_by_id[ch]["container_type"] == "az" for ch in child_ids
            )
            stack_vertical = ctype == "vpc" or (is_lr and not has_az_children)
            if _is_big_data_data_container(cid, child_nodes):
                is_group = ctype in ("az", "as_group", "as_policy")
                pad_x = CONTAINER_PADDING_X + (GROUP_PADDING_X if is_group else 0)
                pad_y = CONTAINER_PADDING_Y + (GROUP_PADDING_Y if is_group else 0)
                header_h = _container_header_height(ctype)
                grid = _layout_big_data_nodes(cid, child_nodes, start_x=0, start_y=0)
                nodes_w = max((x + w for _, x, y, w, h in grid), default=0) + CONTAINER_PADDING_X
                nodes_h = max((y + h for _, x, y, w, h in grid), default=0) + CONTAINER_PADDING_Y
                if stack_vertical:
                    child_total_h = sum(s[1] for s in child_sizes) + len(child_sizes) * CONTAINER_PADDING_Y
                    child_max_w = max((s[0] for s in child_sizes), default=0)
                    content_w = max(child_max_w if child_sizes else 0, nodes_w)
                    content_h = (child_total_h if child_sizes else 0) + nodes_h
                else:
                    child_total_w = sum(s[0] for s in child_sizes) + max(0, len(child_sizes) - 1) * CONTAINER_PADDING_X
                    child_max_h = max((s[1] for s in child_sizes), default=0)
                    content_w = max(child_total_w if child_sizes else 0, nodes_w)
                    content_h = (child_max_h if child_sizes else 0) + nodes_h
                result = (
                    max(content_w + 2 * pad_x, MIN_CONTAINER_W),
                    max(header_h + content_h + pad_y, MIN_CONTAINER_H),
                )
                _size_cache[cid] = result
                return result
            result = compute_container_size(
                ctype, child_sizes, child_nodes,
                is_lr=is_lr, stack_vertical=stack_vertical, start_size=start_size,
            )
            _size_cache[cid] = result
            return result

        # Find root region
        root_id = next(c["id"] for c in containers if c.get("parent_id") is None and c["container_type"] == "region")

        # Nodes outside the region are rendered as a left-side access/integration zone.
        outside_nodes = [n for n in nodes if n.get("container_id") not in container_by_id]
        user_nodes = [n for n in outside_nodes if n.get("type") == "user"]
        external_nodes = [n for n in outside_nodes if n.get("type") == "external"]
        outside_node_ids = {n["id"] for n in outside_nodes}
        internal_nodes = [n for n in nodes if n["id"] not in outside_node_ids]

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

        def _find_public_subnet_id() -> str | None:
            subnet_ids = [
                c["id"]
                for c in containers
                if c["container_type"] == "subnet"
            ]
            if not subnet_ids:
                return None
            ranked = sorted(
                subnet_ids,
                key=lambda cid: subnet_layer_rank(container_by_id[cid].get("label", "")),
            )
            return ranked[0]

        def _filter_render_edges() -> tuple[list[dict], bool, str | None]:
            kept: list[dict] = []
            has_external_access = False
            external_targets: list[str] = []
            seen_keys: set[tuple[str, str, str]] = set()

            for edge in edges:
                src = edge["source"]
                tgt = edge["target"]
                kind = edge.get("edge_kind", "traffic")

                if src in outside_node_ids or tgt in outside_node_ids:
                    if kind == "traffic":
                        has_external_access = True
                        internal_endpoint = tgt if src in outside_node_ids else src
                        if internal_endpoint in node_by_id or internal_endpoint in container_by_id:
                            external_targets.append(internal_endpoint)
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
            preferred_target = None
            for target in external_targets:
                target_node = node_by_id.get(target)
                if target_node and (target_node.get("product") or "").lower() in {"cdm", "cloud data migration (cdm)"}:
                    preferred_target = target
                    break
            if preferred_target is None and external_targets:
                preferred_target = external_targets[0]
            return (primary_traffic + replication)[:MAX_RENDER_EDGES], has_external_access, preferred_target

        render_edges, has_external_access, external_target_id = _filter_render_edges()
        public_subnet_id = _find_public_subnet_id()

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
            container_positions[cid] = (abs_x, abs_y, cw, ch)

            cs = CONTAINER_STYLE_MAP[ctype]
            style = _container_style(ctype)
            display_label = REGION_DISPLAY_LABEL if ctype == "region" else c["label"]
            cells.append((cell_id, display_label, style, parent_cell or "1", None, None, x, y, cw, ch))
            parent_for_children = str(cell_id)
            cell_id += 1

            is_group = ctype in ("az", "as_group", "as_policy")
            pad_x = CONTAINER_PADDING_X + (GROUP_PADDING_X if is_group else 0)
            pad_y = CONTAINER_PADDING_Y + (GROUP_PADDING_Y if is_group else 0)
            header_h = _container_header_height(ctype)

            # Render child containers — sort subnets by semantic layer
            child_ids = children_of.get(cid, [])
            if ctype == "vpc":
                child_ids = sorted(
                    child_ids,
                    key=lambda ch: subnet_layer_rank(container_by_id[ch].get("label", "")),
                )
            child_x = pad_x
            child_y = header_h
            # VPC always stacks subnets vertically (public > app > data).
            vpc_vertical = ctype == "vpc"
            az_row = bool(child_ids) and all(
                container_by_id[ch]["container_type"] == "az" for ch in child_ids
            )
            stack_vertical = vpc_vertical or (is_lr and not az_row)

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
                if stack_vertical:
                    child_y += ch_h + CONTAINER_PADDING_Y
                else:
                    child_x += ch_w + CONTAINER_PADDING_X

            # Render nodes inside this container using grid layout
            child_nodes = sorted(nodes_by_container.get(cid, []), key=lambda n: _node_layer_rank(n, cid))
            if child_nodes:
                # If we had child containers, place nodes below them
                if child_ids:
                    if stack_vertical:
                        node_y_start = child_y
                    else:
                        max_child_h = max(_compute_container_size(ch)[1] for ch in child_ids)
                        node_y_start = header_h + max_child_h + CONTAINER_PADDING_Y
                else:
                    node_y_start = header_h

                # Use grid layout from hld_layout
                if _is_big_data_data_container(cid, child_nodes):
                    grid = _layout_big_data_nodes(
                        cid,
                        child_nodes,
                        start_x=pad_x,
                        start_y=node_y_start,
                    )
                else:
                    grid = layout_nodes_in_grid(
                        child_nodes,
                        # layout_nodes_in_grid compares absolute x positions against
                        # area_width, so the right boundary must include the start_x offset.
                        area_width=cw - pad_x,
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

        root_x = DIAGRAM_MARGIN + (EXTERNAL_NOTE_WIDTH + EXTERNAL_NOTE_GAP if outside_nodes else 0)

        # Render root region
        _render_container(root_id, None, root_x, DIAGRAM_MARGIN, root_x, DIAGRAM_MARGIN)

        external_zone_cell_id: int | None = None
        external_zone_box: tuple[int, int, int, int] | None = None
        if outside_nodes:
            ext_x = DIAGRAM_MARGIN
            ordered_outside = user_nodes + sorted(external_nodes, key=lambda n: n["label"].lower())
            zone_inner_h = len(ordered_outside) * EXTERNAL_ZONE_ITEM_H + max(0, len(ordered_outside) - 1) * EXTERNAL_ZONE_ITEM_GAP
            zone_h = EXTERNAL_ZONE_HEADER_H + zone_inner_h + 2 * EXTERNAL_ZONE_PADDING
            zone_w = EXTERNAL_NOTE_WIDTH
            public_box = container_positions.get(public_subnet_id) if public_subnet_id else None
            target_box = (
                node_positions.get(external_target_id)
                or container_positions.get(external_target_id)
                or public_box
            )
            if target_box:
                zone_y = max(DIAGRAM_MARGIN, min(DIAGRAM_MARGIN + root_h - zone_h, target_box[1]))
            else:
                zone_y = DIAGRAM_MARGIN + max(0, (root_h - zone_h) // 2)

            zone_style = (
                f"rounded=1;whiteSpace=wrap;html=1;fillColor=#FAFAFA;strokeColor=#999999;"
                f"fontStyle=1;fontSize={title_font_size};fontFamily={font_family};align=center"
            )
            external_zone_cell_id = cell_id
            external_zone_box = (ext_x, zone_y, zone_w, zone_h)
            cells.append((cell_id, EXTERNAL_ZONE_TITLE, zone_style, "1", None, None, ext_x, zone_y, zone_w, zone_h))
            cell_id += 1

            item_y = EXTERNAL_ZONE_HEADER_H + EXTERNAL_ZONE_PADDING
            user_item_style = (
                f"rounded=1;whiteSpace=wrap;html=1;fillColor=#DCEEFF;strokeColor=#2F80ED;"
                f"fontSize={font_size};fontFamily={font_family};align=center;verticalAlign=middle"
            )
            external_item_style = (
                f"rounded=1;whiteSpace=wrap;html=1;fillColor=#F5F5F5;strokeColor=#999999;"
                f"fontSize={font_size};fontFamily={font_family};align=center;verticalAlign=middle"
            )
            for n in ordered_outside:
                item_style = user_item_style if n["type"] == "user" else external_item_style
                item_x = EXTERNAL_ZONE_PADDING
                item_w = zone_w - 2 * EXTERNAL_ZONE_PADDING
                cells.append((cell_id, n["label"], item_style, str(external_zone_cell_id), None, None, item_x, item_y, item_w, EXTERNAL_ZONE_ITEM_H))
                item_y += EXTERNAL_ZONE_ITEM_H + EXTERNAL_ZONE_ITEM_GAP
                cell_id += 1

            aggregate_target = external_target_id or public_subnet_id
            if has_external_access and aggregate_target:
                render_edges.insert(0, {
                    "source": "__external_zone__",
                    "target": aggregate_target,
                    "label": "",
                    "edge_kind": "traffic",
                })

        # Edges with explicit anchors and manual waypoints to avoid icon overlap.
        base_edge_style = f"edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=0;jettySize=auto;html=1;endArrow=classic;endFill=1;strokeColor=#333333;strokeWidth=1;fontFamily={font_family};fontSize={font_size - 1}"
        obstacle_boxes = list(node_positions.values()) + list(container_positions.values())
        for edge in render_edges:
            is_external_zone_edge = edge["source"] == "__external_zone__" or edge["target"] == "__external_zone__"
            if edge["source"] == "__external_zone__":
                source_cell = external_zone_cell_id
                src_box = external_zone_box
            else:
                source_cell = node_cell_map.get(edge["source"]) or container_cell_map.get(edge["source"])
                src_box = node_positions.get(edge["source"]) or container_positions.get(edge["source"])

            if edge["target"] == "__external_zone__":
                target_cell = external_zone_cell_id
                tgt_box = external_zone_box
            else:
                target_cell = node_cell_map.get(edge["target"]) or container_cell_map.get(edge["target"])
                tgt_box = node_positions.get(edge["target"]) or container_positions.get(edge["target"])
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
            exit_hint = ""
            entry_hint = ""
            if is_external_zone_edge and src_box and tgt_box:
                if edge["source"] == "__external_zone__":
                    exit_hint = "exitX=1.0;exitY=0.5;exitDx=0;exitDy=0;"
                    entry_hint = "entryX=0.0;entryY=0.5;entryDx=0;entryDy=0;"
                else:
                    exit_hint = "exitX=0.0;exitY=0.5;exitDx=0;exitDy=0;"
                    entry_hint = "entryX=1.0;entryY=0.5;entryDx=0;entryDy=0;"
            elif src_box and tgt_box:
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
                if is_external_zone_edge:
                    edge_points_by_id[cell_id] = _compute_external_zone_waypoints(src_box, tgt_box)
                else:
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
                f"The total number of nodes must be <= {MAX_NODES}. "
                "Prefer a minimal diagram and drop optional services rather than exceeding the node budget. "
                "If AZ containers are present, they must be direct children of the region, and each AZ must contain its own VPC and subnets. "
                "Never create a replication edge where source equals target (no self-loops). "
                "Do not point edges to container ids or placeholder ids such as subnet-*, vpc-*, az-*, or *-dr; every edge source/target must resolve to a node id. "
                "No markdown fences, no explanation."
            )},
        ]
        try:
            llm_output = client.complete_text(correction_messages)
        except httpx.ReadTimeout as exc:
            raise RuntimeError("HLD LLM correction timed out while repairing the architecture spec.") from exc
        spec = parse_architecture_spec(llm_output)

    # 3b. Normalize spec based on semantic flags (post-parse safety net)
    flags = _detect_semantic_flags(requirements)
    _normalize_spec(spec, flags, requirements)

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
