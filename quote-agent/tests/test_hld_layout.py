"""Tests for HLD layout helpers: non-overlap, container sizing, grid layout."""
import json
import pytest
from app.hld_layout import (
    ICON_BOX_WIDTH,
    ICON_BOX_HEIGHT,
    NODE_WIDTH,
    NODE_HEIGHT,
    NODE_GAP_X,
    NODE_GAP_Y,
    CONTAINER_PADDING_X,
    CONTAINER_PADDING_Y,
    GROUP_PADDING_X,
    GROUP_PADDING_Y,
    MIN_CONTAINER_W,
    measure_node_box,
    layout_nodes_in_grid,
    compute_container_size,
    route_edge_anchors,
    boxes_overlap,
    subnet_layer_rank,
)
from app.hld_workflow import (
    render_spec_to_drawio_xml,
    _load_style_preset,
    CONTAINER_STYLE_MAP,
)


# ── Fixtures ──────────────────────────────────────────────────────────────

def _make_template_spec(**overrides) -> dict:
    spec = {
        "title": "Layout Test",
        "diagram_type": "architecture",
        "template": "layered_horizontal",
        "layout": "TB",
        "containers": [
            {"id": "region-1", "label": "Region", "container_type": "region", "parent_id": None},
            {"id": "vpc-1", "label": "VPC", "container_type": "vpc", "parent_id": "region-1"},
            {"id": "subnet-fe", "label": "Frontend Subnet", "container_type": "subnet", "parent_id": "vpc-1"},
            {"id": "subnet-app", "label": "Application Subnet", "container_type": "subnet", "parent_id": "vpc-1"},
            {"id": "subnet-data", "label": "Data Subnet", "container_type": "subnet", "parent_id": "vpc-1"},
        ],
        "nodes": [
            {"id": "elb", "label": "ELB", "type": "gateway", "container_id": "subnet-fe", "product": "ELB"},
            {"id": "ecs", "label": "ECS", "type": "service", "container_id": "subnet-app", "product": "ECS"},
            {"id": "rds", "label": "RDS", "type": "database", "container_id": "subnet-data", "product": "RDS"},
        ],
        "edges": [
            {"source": "elb", "target": "ecs", "label": "route", "edge_kind": "traffic"},
            {"source": "ecs", "target": "rds", "label": "query", "edge_kind": "traffic"},
        ],
    }
    spec.update(overrides)
    return spec


def _make_dense_spec() -> dict:
    """Spec with many nodes per subnet to stress layout."""
    spec = {
        "title": "Dense Layout Test",
        "diagram_type": "architecture",
        "template": "layered_horizontal",
        "layout": "TB",
        "containers": [
            {"id": "region-1", "label": "Region", "container_type": "region", "parent_id": None},
            {"id": "vpc-1", "label": "VPC", "container_type": "vpc", "parent_id": "region-1"},
            {"id": "subnet-fe", "label": "Frontend Subnet", "container_type": "subnet", "parent_id": "vpc-1"},
            {"id": "subnet-app", "label": "Application Subnet", "container_type": "subnet", "parent_id": "vpc-1"},
            {"id": "subnet-data", "label": "Data Subnet", "container_type": "subnet", "parent_id": "vpc-1"},
        ],
        "nodes": [
            {"id": "elb", "label": "ELB", "type": "gateway", "container_id": "subnet-fe", "product": "ELB"},
            {"id": "waf", "label": "WAF", "type": "gateway", "container_id": "subnet-fe", "product": "WAF"},
            {"id": "nat", "label": "NAT GW", "type": "gateway", "container_id": "subnet-fe", "product": "NAT Gateway"},
            {"id": "ecs1", "label": "ECS-1", "type": "service", "container_id": "subnet-app", "product": "ECS"},
            {"id": "ecs2", "label": "ECS-2", "type": "service", "container_id": "subnet-app", "product": "ECS"},
            {"id": "cce", "label": "CCE", "type": "service", "container_id": "subnet-app", "product": "CCE"},
            {"id": "dcs", "label": "DCS", "type": "service", "container_id": "subnet-app", "product": "DCS"},
            {"id": "rds", "label": "RDS", "type": "database", "container_id": "subnet-data", "product": "RDS"},
            {"id": "obs", "label": "OBS", "type": "database", "container_id": "subnet-data", "product": "OBS"},
        ],
        "edges": [
            {"source": "elb", "target": "ecs1", "label": "route", "edge_kind": "traffic"},
            {"source": "ecs1", "target": "rds", "label": "query", "edge_kind": "traffic"},
        ],
    }
    return spec


# ── measure_node_box ──────────────────────────────────────────────────────

class TestMeasureNodeBox:
    def test_icon_node_uses_icon_box(self):
        node = {"id": "n1", "product": "ECS"}
        w, h = measure_node_box(node)
        assert w == ICON_BOX_WIDTH
        assert h == ICON_BOX_HEIGHT

    def test_no_product_uses_node_box(self):
        node = {"id": "n1", "product": None}
        w, h = measure_node_box(node)
        assert w == NODE_WIDTH
        assert h == NODE_HEIGHT

    def test_unknown_product_uses_node_box(self):
        node = {"id": "n1", "product": "NonExistent999"}
        w, h = measure_node_box(node)
        assert w == NODE_WIDTH
        assert h == NODE_HEIGHT


# ── layout_nodes_in_grid ─────────────────────────────────────────────────

class TestLayoutNodesInGrid:
    def test_empty_nodes(self):
        assert layout_nodes_in_grid([]) == []

    def test_single_node_position(self):
        nodes = [{"id": "n1", "product": None}]
        result = layout_nodes_in_grid(nodes, start_x=10, start_y=20)
        assert len(result) == 1
        n, x, y, w, h = result[0]
        assert x == 10
        assert y == 20

    def test_no_overlap_in_row(self):
        nodes = [{"id": f"n{i}", "product": None} for i in range(5)]
        result = layout_nodes_in_grid(nodes, start_x=0, start_y=0)
        # Check no two nodes overlap
        for i in range(len(result)):
            for j in range(i + 1, len(result)):
                _, xi, yi, wi, hi = result[i]
                _, xj, yj, wj, hj = result[j]
                assert not boxes_overlap((xi, yi, wi, hi), (xj, yj, wj, hj)), f"nodes {i} and {j} overlap"

    def test_wraps_to_next_row(self):
        nodes = [{"id": f"n{i}", "product": None} for i in range(7)]
        result = layout_nodes_in_grid(nodes, max_cols=3, start_x=0, start_y=0)
        # Should have 3 rows: 3, 3, 1
        rows = {}
        for _, x, y, w, h in result:
            rows.setdefault(y, []).append(x)
        assert len(rows) == 3

    def test_icon_nodes_use_icon_box_size(self):
        nodes = [{"id": "n1", "product": "ECS"}]
        result = layout_nodes_in_grid(nodes, start_x=0, start_y=0)
        _, x, y, w, h = result[0]
        assert w == ICON_BOX_WIDTH
        assert h == ICON_BOX_HEIGHT


# ── compute_container_size ───────────────────────────────────────────────

class TestComputeContainerSize:
    def test_empty_container_returns_minimum(self):
        w, h = compute_container_size("subnet", [], [])
        assert w >= MIN_CONTAINER_W
        assert h >= 80

    def test_container_grows_with_nodes(self):
        nodes_1 = [{"id": "n1", "product": None}]
        nodes_4 = [{"id": f"n{i}", "product": None} for i in range(4)]
        w1, h1 = compute_container_size("subnet", [], nodes_1)
        w4, h4 = compute_container_size("subnet", [], nodes_4)
        assert w4 >= w1
        assert h4 >= h1

    def test_group_container_has_extra_padding(self):
        nodes = [{"id": "n1", "product": None}]
        w_sub, h_sub = compute_container_size("subnet", [], nodes)
        w_az, h_az = compute_container_size("az", [], nodes)
        # AZ should be larger due to group padding
        assert w_az >= w_sub
        assert h_az >= h_sub

    def test_container_grows_with_child_containers(self):
        child_small = [(300, 100)]
        child_big = [(300, 100), (300, 100)]
        w1, h1 = compute_container_size("vpc", child_small, [], is_lr=True)
        w2, h2 = compute_container_size("vpc", child_big, [], is_lr=True)
        assert h2 > h1  # LR: more children → taller


# ── route_edge_anchors ───────────────────────────────────────────────────

class TestRouteEdgeAnchors:
    def test_target_below_exits_bottom(self):
        src = (0, 0, 120, 110)
        tgt = (0, 200, 120, 110)
        exit_h, entry_h = route_edge_anchors(src, tgt)
        assert "exitY=1.0" in exit_h
        assert "entryY=0.0" in entry_h

    def test_target_right_exits_right(self):
        src = (0, 0, 120, 110)
        tgt = (300, 0, 120, 110)
        exit_h, entry_h = route_edge_anchors(src, tgt)
        assert "exitX=1.0" in exit_h
        assert "entryX=0.0" in entry_h

    def test_target_above_exits_top(self):
        src = (0, 200, 120, 110)
        tgt = (0, 0, 120, 110)
        exit_h, entry_h = route_edge_anchors(src, tgt)
        assert "exitY=0.0" in exit_h
        assert "entryY=1.0" in entry_h


# ── boxes_overlap ────────────────────────────────────────────────────────

class TestBoxesOverlap:
    def test_non_overlapping(self):
        a = (0, 0, 100, 100)
        b = (150, 0, 100, 100)
        assert not boxes_overlap(a, b)

    def test_overlapping(self):
        a = (0, 0, 100, 100)
        b = (50, 0, 100, 100)
        assert boxes_overlap(a, b)

    def test_touching_not_overlapping(self):
        a = (0, 0, 100, 100)
        b = (100, 0, 100, 100)
        assert not boxes_overlap(a, b)


# ── Integration: rendered diagram non-overlap ────────────────────────────

class TestRenderedNonOverlap:
    # Container labels that should be excluded from overlap checks
    # (they naturally contain their children)
    CONTAINER_LABELS = {"Region", "VPC", "Frontend Subnet", "Application Subnet",
                        "Data Subnet", "Management Subnet", "AZ1", "AS Group",
                        "AS Policy"}

    def _extract_node_geometries(self, xml: str) -> dict[str, tuple[int, int, int, int]]:
        """Parse drawio XML to extract node label -> (abs_x, abs_y, w, h).

        Computes absolute positions by walking the parent chain.
        """
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml)

        # First pass: build id -> cell dict and id -> parent_id
        cells_by_id: dict[str, dict] = {}
        for cell in root.iter("mxCell"):
            cid = cell.get("id", "")
            if cid in ("0", "1"):
                continue
            cells_by_id[cid] = {
                "value": cell.get("value", ""),
                "parent": cell.get("parent", "1"),
                "vertex": cell.get("vertex") == "1",
                "x": 0, "y": 0, "w": 0, "h": 0, "relative": False,
            }
            geo = cell.find("mxGeometry")
            if geo is not None:
                cells_by_id[cid]["x"] = float(geo.get("x", "0"))
                cells_by_id[cid]["y"] = float(geo.get("y", "0"))
                cells_by_id[cid]["w"] = float(geo.get("width", "0"))
                cells_by_id[cid]["h"] = float(geo.get("height", "0"))
                cells_by_id[cid]["relative"] = geo.get("relative") == "1"

        # Compute absolute position by walking parent chain
        abs_cache: dict[str, tuple[float, float]] = {}

        def _abs_pos(cid: str) -> tuple[float, float]:
            if cid in abs_cache:
                return abs_cache[cid]
            c = cells_by_id.get(cid)
            if not c or c["relative"]:
                abs_cache[cid] = (0.0, 0.0)
                return (0.0, 0.0)
            px, py = _abs_pos(c["parent"])
            ax = px + c["x"]
            ay = py + c["y"]
            abs_cache[cid] = (ax, ay)
            return (ax, ay)

        geoms: dict[str, tuple[int, int, int, int]] = {}
        for cid, c in cells_by_id.items():
            if not c["vertex"] or c["relative"]:
                continue
            value = c["value"]
            w, h = int(c["w"]), int(c["h"])
            if not value or w <= 0 or h <= 0:
                continue
            ax, ay = _abs_pos(cid)
            geoms[value] = (int(ax), int(ay), w, h)
        return geoms

    def _check_leaf_no_overlap(self, geoms: dict[str, tuple[int, int, int, int]]) -> None:
        """Assert no two leaf (non-container) nodes overlap."""
        leaf_items = [(k, v) for k, v in geoms.items() if k not in self.CONTAINER_LABELS]
        for i in range(len(leaf_items)):
            for j in range(i + 1, len(leaf_items)):
                label_i, box_i = leaf_items[i]
                label_j, box_j = leaf_items[j]
                assert not boxes_overlap(box_i, box_j), f"'{label_i}' and '{label_j}' overlap: {box_i} vs {box_j}"

    def test_simple_spec_no_overlap(self):
        spec = _make_template_spec()
        style = _load_style_preset()
        xml = render_spec_to_drawio_xml(spec, style)
        geoms = self._extract_node_geometries(xml)
        self._check_leaf_no_overlap(geoms)

    def test_dense_spec_no_overlap(self):
        spec = _make_dense_spec()
        style = _load_style_preset()
        xml = render_spec_to_drawio_xml(spec, style)
        geoms = self._extract_node_geometries(xml)
        self._check_leaf_no_overlap(geoms)

    def test_deployment_vertical_no_overlap(self):
        spec = _make_dense_spec()
        spec["template"] = "deployment_vertical"
        spec["layout"] = "LR"
        style = _load_style_preset()
        xml = render_spec_to_drawio_xml(spec, style)
        geoms = self._extract_node_geometries(xml)
        self._check_leaf_no_overlap(geoms)

    def test_az_group_nodes_no_overlap(self):
        spec = _make_template_spec()
        spec["containers"].append({"id": "az-1", "label": "AZ1", "container_type": "az", "parent_id": "subnet-app"})
        spec["nodes"].append({"id": "ecs2", "label": "ECS-HA", "type": "service", "container_id": "az-1", "product": "ECS"})
        spec["nodes"].append({"id": "ecs3", "label": "ECS-HA2", "type": "service", "container_id": "az-1", "product": "ECS"})
        style = _load_style_preset()
        xml = render_spec_to_drawio_xml(spec, style)
        geoms = self._extract_node_geometries(xml)
        self._check_leaf_no_overlap(geoms)


# ── Container sizing grows with content ──────────────────────────────────

class TestContainerSizing:
    def test_more_nodes_larger_container(self):
        nodes_1 = [{"id": "n1", "product": None}]
        nodes_5 = [{"id": f"n{i}", "product": None} for i in range(5)]
        w1, h1 = compute_container_size("subnet", [], nodes_1)
        w5, h5 = compute_container_size("subnet", [], nodes_5)
        assert w5 > w1 or h5 > h1

    def test_icon_nodes_larger_than_fallback(self):
        icon_nodes = [{"id": "n1", "product": "ECS"}]
        fallback_nodes = [{"id": "n1", "product": None}]
        w_i, h_i = compute_container_size("subnet", [], icon_nodes)
        w_f, h_f = compute_container_size("subnet", [], fallback_nodes)
        # Icon box is taller (110 vs 50)
        assert h_i > h_f


# ── Subnet layer ordering ─────────────────────────────────────────────────

class TestSubnetLayerRank:
    def test_public_rank_0(self):
        assert subnet_layer_rank("Public Subnet") == 0

    def test_frontend_rank_0(self):
        assert subnet_layer_rank("Frontend Subnet") == 0

    def test_app_rank_1(self):
        assert subnet_layer_rank("Application Subnet") == 1

    def test_data_rank_2(self):
        assert subnet_layer_rank("Data Subnet") == 2

    def test_db_rank_2(self):
        assert subnet_layer_rank("DB Subnet") == 2

    def test_mgmt_rank_3(self):
        assert subnet_layer_rank("Management Subnet") == 3

    def test_unknown_rank_4(self):
        assert subnet_layer_rank("Custom Subnet") == 4

    def test_case_insensitive(self):
        assert subnet_layer_rank("PUBLIC SUBNET") == 0
        assert subnet_layer_rank("application subnet") == 1


# ── Golden-shape: ordered subnet vertical stacking ────────────────────────

class TestSubnetVerticalStacking:
    """Verify that rendered subnets follow public > app > data > mgmt order."""

    def _extract_container_y_positions(self, xml: str) -> dict[str, int]:
        """Parse drawio XML to get container label -> y position."""
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml)
        positions: dict[str, int] = {}
        for cell in root.iter("mxCell"):
            value = cell.get("value", "")
            if not value:
                continue
            geo = cell.find("mxGeometry")
            if geo is None:
                continue
            y = float(geo.get("y", "0"))
            # Only include known container labels
            if any(kw in value.lower() for kw in ("subnet", "vpc", "region", "az", "as ")):
                positions[value] = int(y)
        return positions

    def test_subnets_in_vertical_order(self):
        """Subnets under a VPC should be ordered: public/frontend, app, data, mgmt."""
        spec = {
            "title": "Subnet Order Test",
            "diagram_type": "architecture",
            "template": "layered_horizontal",
            "layout": "TB",
            "containers": [
                {"id": "region-1", "label": "Region", "container_type": "region", "parent_id": None},
                {"id": "vpc-1", "label": "VPC", "container_type": "vpc", "parent_id": "region-1"},
                {"id": "subnet-data", "label": "Data Subnet", "container_type": "subnet", "parent_id": "vpc-1"},
                {"id": "subnet-fe", "label": "Frontend Subnet", "container_type": "subnet", "parent_id": "vpc-1"},
                {"id": "subnet-app", "label": "Application Subnet", "container_type": "subnet", "parent_id": "vpc-1"},
                {"id": "subnet-mgmt", "label": "Management Subnet", "container_type": "subnet", "parent_id": "vpc-1"},
            ],
            "nodes": [
                {"id": "elb", "label": "ELB", "type": "gateway", "container_id": "subnet-fe", "product": "ELB"},
                {"id": "ecs", "label": "ECS", "type": "service", "container_id": "subnet-app", "product": "ECS"},
                {"id": "rds", "label": "RDS", "type": "database", "container_id": "subnet-data", "product": "RDS"},
                {"id": "nat", "label": "NAT", "type": "gateway", "container_id": "subnet-mgmt", "product": "NAT Gateway"},
            ],
            "edges": [],
        }
        style = _load_style_preset()
        xml = render_spec_to_drawio_xml(spec, style)
        positions = self._extract_container_y_positions(xml)

        # Frontend should be above Application, above Data, above Management
        y_fe = positions.get("Frontend Subnet")
        y_app = positions.get("Application Subnet")
        y_data = positions.get("Data Subnet")
        y_mgmt = positions.get("Management Subnet")

        assert y_fe is not None, "Frontend Subnet not found in output"
        assert y_app is not None, "Application Subnet not found in output"
        assert y_data is not None, "Data Subnet not found in output"
        assert y_mgmt is not None, "Management Subnet not found in output"

        assert y_fe < y_app, f"Frontend (y={y_fe}) should be above Application (y={y_app})"
        assert y_app < y_data, f"Application (y={y_app}) should be above Data (y={y_data})"
        assert y_data < y_mgmt, f"Data (y={y_data}) should be above Management (y={y_mgmt})"


# ── Golden-shape: external nodes outside region/vpc ───────────────────────

class TestExternalNodesPlacement:
    """Verify external services are rendered as a right-side note, not nodes."""

    def _extract_vertex_abs_positions(self, xml: str) -> dict[str, tuple[int, int, int, int]]:
        """Parse drawio XML for vertex label -> (abs_x, abs_y, w, h)."""
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml)
        cells_by_id: dict[str, dict] = {}
        for cell in root.iter("mxCell"):
            cid = cell.get("id", "")
            if cid in ("0", "1"):
                continue
            cells_by_id[cid] = {
                "value": cell.get("value", ""),
                "parent": cell.get("parent", "1"),
                "vertex": cell.get("vertex") == "1",
                "x": 0.0, "y": 0.0, "w": 0.0, "h": 0.0, "relative": False,
            }
            geo = cell.find("mxGeometry")
            if geo is not None:
                cells_by_id[cid]["x"] = float(geo.get("x", "0"))
                cells_by_id[cid]["y"] = float(geo.get("y", "0"))
                cells_by_id[cid]["w"] = float(geo.get("width", "0"))
                cells_by_id[cid]["h"] = float(geo.get("height", "0"))
                cells_by_id[cid]["relative"] = geo.get("relative") == "1"

        abs_cache: dict[str, tuple[float, float]] = {}
        def _abs_pos(cid: str) -> tuple[float, float]:
            if cid in abs_cache:
                return abs_cache[cid]
            c = cells_by_id.get(cid)
            if not c or c["relative"]:
                abs_cache[cid] = (0.0, 0.0)
                return (0.0, 0.0)
            px, py = _abs_pos(c["parent"])
            ax, ay = px + c["x"], py + c["y"]
            abs_cache[cid] = (ax, ay)
            return (ax, ay)

        result: dict[str, tuple[int, int, int, int]] = {}
        for cid, c in cells_by_id.items():
            if not c["vertex"] or c["relative"]:
                continue
            value = c["value"]
            w, h = int(c["w"]), int(c["h"])
            if not value or w <= 0 or h <= 0:
                continue
            ax, ay = _abs_pos(cid)
            result[value] = (int(ax), int(ay), w, h)
        return result

    def test_external_services_note_right_of_region(self):
        spec = {
            "title": "External Node Test",
            "diagram_type": "architecture",
            "template": "layered_horizontal",
            "layout": "TB",
            "containers": [
                {"id": "region-1", "label": "Region", "container_type": "region", "parent_id": None},
                {"id": "vpc-1", "label": "VPC", "container_type": "vpc", "parent_id": "region-1"},
                {"id": "subnet-app", "label": "Application Subnet", "container_type": "subnet", "parent_id": "vpc-1"},
            ],
            "nodes": [
                {"id": "ecs", "label": "ECS", "type": "service", "container_id": "subnet-app", "product": "ECS"},
                {"id": "ext-api", "label": "External API", "type": "external", "container_id": "ext-zone"},
                {"id": "crm", "label": "CRM System", "type": "external", "container_id": "ext-zone"},
            ],
            "edges": [
                {"source": "ecs", "target": "ext-api", "label": "call", "edge_kind": "traffic"},
            ],
        }
        style = _load_style_preset()
        xml = render_spec_to_drawio_xml(spec, style)
        positions = self._extract_vertex_abs_positions(xml)

        ecs_pos = positions.get("ECS")
        note_label = next((label for label in positions if "External Services:" in label), None)
        ext_pos = positions.get(note_label) if note_label else None
        assert ecs_pos is not None, "ECS node not found"
        assert ext_pos is not None, "External services note not found"
        assert "External API" in note_label
        assert "CRM System" in note_label

        # Note should be to the right of internal node
        ext_right_edge = ext_pos[0]  # ext x
        ecs_right_edge = ecs_pos[0] + ecs_pos[2]  # ecs x + w
        assert ext_right_edge > ecs_right_edge, (
            f"External note (x={ext_pos[0]}) should be right of ECS right edge ({ecs_right_edge})"
        )
        assert "External API" not in positions, "External services should not render as standalone nodes"


# ── Golden-shape: logical group padding ───────────────────────────────────

class TestLogicalGroupPadding:
    """Verify AZ/AS Group/AS Policy containers have visible inner padding."""

    def test_group_container_larger_than_plain(self):
        """A group container with the same children should be larger than a subnet."""
        nodes = [{"id": "n1", "product": "ECS"}, {"id": "n2", "product": "RDS"}]
        w_sub, h_sub = compute_container_size("subnet", [], nodes)
        w_az, h_az = compute_container_size("az", [], nodes)
        # AZ should be strictly larger due to GROUP_PADDING
        assert w_az > w_sub or h_az > h_sub, (
            f"AZ ({w_az}x{h_az}) should be larger than subnet ({w_sub}x{h_sub})"
        )

    def test_group_nodes_no_overlap(self):
        """Nodes inside an AZ group should not overlap."""
        spec = _make_template_spec()
        spec["containers"].append(
            {"id": "az-1", "label": "AZ1", "container_type": "az", "parent_id": "subnet-app"}
        )
        spec["nodes"].append(
            {"id": "ecs2", "label": "ECS-HA", "type": "service", "container_id": "az-1", "product": "ECS"}
        )
        spec["nodes"].append(
            {"id": "ecs3", "label": "ECS-HA2", "type": "service", "container_id": "az-1", "product": "ECS"}
        )
        style = _load_style_preset()
        xml = render_spec_to_drawio_xml(spec, style)
        geoms = TestRenderedNonOverlap()._extract_node_geometries(xml)
        TestRenderedNonOverlap()._check_leaf_no_overlap(geoms)


# ── Golden-shape: no overlap in dense subnet ──────────────────────────────

class TestDenseSubnetNoOverlap:
    """Verify no node overlap in a subnet with many nodes."""

    def test_dense_subnet_no_overlap(self):
        """A subnet with 6+ icon nodes should have no overlapping nodes."""
        spec = {
            "title": "Dense Subnet Test",
            "diagram_type": "architecture",
            "template": "layered_horizontal",
            "layout": "TB",
            "containers": [
                {"id": "region-1", "label": "Region", "container_type": "region", "parent_id": None},
                {"id": "vpc-1", "label": "VPC", "container_type": "vpc", "parent_id": "region-1"},
                {"id": "subnet-app", "label": "Application Subnet", "container_type": "subnet", "parent_id": "vpc-1"},
            ],
            "nodes": [
                {"id": f"n{i}", "label": f"Node-{i}", "type": "service", "container_id": "subnet-app", "product": "ECS"}
                for i in range(8)
            ],
            "edges": [],
        }
        style = _load_style_preset()
        xml = render_spec_to_drawio_xml(spec, style)
        geoms = TestRenderedNonOverlap()._extract_node_geometries(xml)
        TestRenderedNonOverlap()._check_leaf_no_overlap(geoms)


class TestEdgeRenderingConstraints:
    def _extract_edges(self, xml: str) -> list[dict]:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml)
        edges: list[dict] = []
        for cell in root.iter("mxCell"):
            if cell.get("edge") != "1":
                continue
            geo = cell.find("mxGeometry")
            points: list[tuple[int, int]] = []
            if geo is not None:
                arr = geo.find("./Array[@as='points']")
                if arr is not None:
                    for point in arr.findall("mxPoint"):
                        points.append((int(float(point.get("x", "0"))), int(float(point.get("y", "0")))))
            edges.append({
                "value": cell.get("value", ""),
                "style": cell.get("style", ""),
                "points": points,
            })
        return edges

    def test_edges_are_capped_and_explicitly_routed(self):
        spec = {
            "title": "Edge Constraint Test",
            "diagram_type": "architecture",
            "template": "layered_horizontal",
            "layout": "TB",
            "containers": [
                {"id": "region-1", "label": "Region", "container_type": "region", "parent_id": None},
                {"id": "vpc-1", "label": "VPC", "container_type": "vpc", "parent_id": "region-1"},
                {"id": "subnet-fe", "label": "Frontend Subnet", "container_type": "subnet", "parent_id": "vpc-1"},
                {"id": "subnet-app", "label": "Application Subnet", "container_type": "subnet", "parent_id": "vpc-1"},
                {"id": "subnet-data", "label": "Data Subnet", "container_type": "subnet", "parent_id": "vpc-1"},
                {"id": "asg-1", "label": "AS Group", "container_type": "as_group", "parent_id": "subnet-app"},
            ],
            "nodes": [
                {"id": "user", "label": "User", "type": "user", "container_id": "outside", "product": None},
                {"id": "elb", "label": "ELB", "type": "gateway", "container_id": "subnet-fe", "product": "ELB"},
                {"id": "ecs1", "label": "ECS-1", "type": "service", "container_id": "asg-1", "product": "ECS"},
                {"id": "ecs2", "label": "ECS-2", "type": "service", "container_id": "asg-1", "product": "ECS"},
                {"id": "rds", "label": "RDS", "type": "database", "container_id": "subnet-data", "product": "RDS"},
                {"id": "rds-standby", "label": "RDS-Standby", "type": "database", "container_id": "subnet-data", "product": "RDS"},
                {"id": "crm", "label": "CRM", "type": "external", "container_id": "outside", "product": None},
            ],
            "edges": [
                {"source": "user", "target": "elb", "label": "HTTPS", "edge_kind": "traffic"},
                {"source": "elb", "target": "ecs1", "label": "HTTP", "edge_kind": "traffic"},
                {"source": "elb", "target": "ecs2", "label": "HTTP", "edge_kind": "traffic"},
                {"source": "ecs1", "target": "rds", "label": "SQL", "edge_kind": "traffic"},
                {"source": "ecs2", "target": "rds", "label": "SQL", "edge_kind": "traffic"},
                {"source": "ecs1", "target": "rds-standby", "label": "sync", "edge_kind": "replication"},
                {"source": "ecs1", "target": "crm", "label": "call", "edge_kind": "traffic"},
                {"source": "elb", "target": "rds", "label": "ops", "edge_kind": "management"},
            ],
        }
        style = _load_style_preset()
        xml = render_spec_to_drawio_xml(spec, style)
        edges = self._extract_edges(xml)

        assert len(edges) <= 12
        assert len(edges) == 4
        for edge in edges:
            assert "exitX=" in edge["style"]
            assert "exitY=" in edge["style"]
            assert "entryX=" in edge["style"]
            assert "entryY=" in edge["style"]
            assert edge["points"], f"edge {edge['value']} missing waypoint"

        styles = " ".join(edge["style"] for edge in edges)
        assert "dashed=1" in styles, "replication edge should remain dashed"

    def test_waypoints_keep_clearance_from_icons(self):
        spec = _make_template_spec()
        style = _load_style_preset()
        xml = render_spec_to_drawio_xml(spec, style)
        geoms = TestRenderedNonOverlap()._extract_node_geometries(xml)
        edges = self._extract_edges(xml)

        icon_boxes = [box for label, box in geoms.items() if label in {"ELB", "ECS", "RDS"}]
        for edge in edges:
            for point in edge["points"]:
                px, py = point
                for box in icon_boxes:
                    inflated = (
                        box[0] - 30,
                        box[1] - 30,
                        box[2] + 60,
                        box[3] + 60,
                    )
                    assert not boxes_overlap((px, py, 1, 1), inflated), (
                        f"waypoint {point} should stay outside icon clearance box {inflated}"
                    )
