"""Tests for HWC icon library, icon mapping, and iconic rendering."""
import pytest
from app.hwc_drawio_library import (
    load_hwc_libraries,
    resolve_hwc_icon,
    list_supported_products,
)
from app.hwc_icon_mapping import resolve_product_icon_title, PRODUCT_TO_ICON_TITLE
from app.hld_workflow import (
    parse_architecture_spec,
    render_spec_to_drawio_xml,
    _load_style_preset,
    CONTAINER_STYLE_MAP,
    EDGE_KIND_STYLE_MAP,
    VALID_EDGE_KINDS,
)


# ── Icon library tests ──────────────────────────────────────────────────

class TestHwcDrawioLibrary:
    def test_load_libraries_returns_entries(self):
        entries = load_hwc_libraries()
        assert len(entries) > 100, "Should load many icon entries"

    def test_entry_has_required_keys(self):
        entries = load_hwc_libraries()
        for e in entries[:10]:
            assert "title" in e
            assert "data" in e
            assert "w" in e
            assert "h" in e

    def test_resolve_known_icon(self):
        entry = resolve_hwc_icon("Elastic Cloud Server (ECS)")
        assert entry is not None
        assert entry["title"] == "Elastic Cloud Server (ECS)"
        assert entry["data"].startswith("data:image/svg+xml;base64,")

    def test_resolve_unknown_returns_none(self):
        assert resolve_hwc_icon("NonExistent Service") is None

    def test_list_supported_products(self):
        products = list_supported_products()
        assert "Elastic Cloud Server (ECS)" in products
        assert "Relational Database Service (RDS)" in products
        assert "Elastic Load Balance (ELB)" in products
        assert "Object Storage Service (OBS)" in products


# ── Icon mapping tests ──────────────────────────────────────────────────

class TestHwcIconMapping:
    @pytest.mark.parametrize("product,expected_title", [
        ("ECS", "Elastic Cloud Server (ECS)"),
        ("RDS", "Relational Database Service (RDS)"),
        ("ELB", "Elastic Load Balance (ELB)"),
        ("OBS", "Object Storage Service (OBS)"),
        ("WAF", "Web Application Firewall (WAF)"),
        ("NAT Gateway", "NAT Gateway"),
        ("EIP", "Elastic IP (EIP)"),
        ("CCE", "Cloud Container Engine (CCE)"),
        ("DDS", "Document Database Service (DDS)"),
        ("DCS", "Distributed Cache Service (DCS) for Redis"),
        ("DMS", "Distributed Message Service (DMS)"),
        ("SMN", "Simple Message Notification (SMN)"),
        ("CBR", "Cloud Backup and Recovery (CBR)"),
        ("VPN", "Virtual Private Network (VPN)"),
        ("CES", "Cloud Eye Service (CES)"),
        ("CTS", "Cloud Trace Service (CTS)"),
        ("KMS", "Key Management Service (KMS)"),
        ("APIG", "API Gateway (APIG)"),
    ])
    def test_resolve_product(self, product, expected_title):
        assert resolve_product_icon_title(product) == expected_title

    def test_synonym_elastic_cloud_server(self):
        assert resolve_product_icon_title("Elastic Cloud Server") == "Elastic Cloud Server (ECS)"

    def test_synonym_load_balancer(self):
        assert resolve_product_icon_title("Load Balancer") == "Elastic Load Balance (ELB)"

    def test_synonym_object_storage_service(self):
        assert resolve_product_icon_title("Object Storage Service") == "Object Storage Service (OBS)"

    def test_unknown_product_returns_none(self):
        assert resolve_product_icon_title("Foobar Service") is None

    def test_none_product_returns_none(self):
        assert resolve_product_icon_title(None) is None

    def test_empty_product_returns_none(self):
        assert resolve_product_icon_title("") is None

    # ── New synonym / normalization coverage ────────────────────────────

    @pytest.mark.parametrize("product,expected_title", [
        # SFS / shared storage
        ("shared file", "Scalable File Service (SFS)"),
        ("shared files", "Scalable File Service (SFS)"),
        ("file share", "Scalable File Service (SFS)"),
        ("nas", "Scalable File Service (SFS)"),
        ("nfs", "Scalable File Service (SFS)"),
        ("SFS Turbo", "Scalable File Service (SFS) Turbo"),
        # RDS / MySQL
        ("mysql", "RDS for MySQL"),
        ("RDS MySQL primary", "RDS for MySQL"),
        ("RDS for MySQL", "RDS for MySQL"),
        # DCS / Redis
        ("Redis cache", "Distributed Cache Service (DCS) for Redis"),
        ("redis", "Distributed Cache Service (DCS) for Redis"),
        # Direct Connect
        ("Direct Connect", "Direct Connect"),
        ("dedicated line", "Direct Connect"),
        ("private line", "Direct Connect"),
        # DRS
        ("database replication service", "Data Replication Service (DRS)"),
        ("drs", "Data Replication Service (DRS)"),
        # CBR / Backup
        ("backup", "Cloud Backup and Recovery (CBR)"),
        ("backup copy", "Cloud Backup and Recovery (CBR)"),
        # SDRS
        ("disaster recovery", "Storage Disaster Recovery Service (SDRS)"),
    ])
    def test_new_synonyms(self, product, expected_title):
        assert resolve_product_icon_title(product) == expected_title

    @pytest.mark.parametrize("product,expected_title", [
        # Role suffix stripping
        ("ECS primary", "Elastic Cloud Server (ECS)"),
        ("RDS standby", "Relational Database Service (RDS)"),
        ("RDS MySQL replica", "RDS for MySQL"),
        ("DCS (primary)", "Distributed Cache Service (DCS) for Redis"),
        # Separator normalization
        ("rds-mysql", "RDS for MySQL"),
        ("sfs_turbo", "Scalable File Service (SFS) Turbo"),
        ("auto_scaling", "Auto Scaling (AS)"),
        # Case insensitivity on synonyms
        ("Shared File", "Scalable File Service (SFS)"),
        ("NAS", "Scalable File Service (SFS)"),
    ])
    def test_normalization(self, product, expected_title):
        assert resolve_product_icon_title(product) == expected_title


# ── Container style tests ───────────────────────────────────────────────

class TestContainerStyles:
    def test_vpc_colors(self):
        cs = CONTAINER_STYLE_MAP["vpc"]
        assert cs["fill"] == "none"
        assert cs["outline"] == "#f85835"

    def test_subnet_colors(self):
        cs = CONTAINER_STYLE_MAP["subnet"]
        assert cs["fill"] == "#f5f5f5"
        assert cs["outline"] == "#999999"

    def test_az_blue_dashed(self):
        cs = CONTAINER_STYLE_MAP["az"]
        assert cs["outline"] == "#3298ff"
        assert cs["dashed"] == "1"
        assert cs["dashPattern"] == "5 5"

    def test_as_group_blue_dashed(self):
        cs = CONTAINER_STYLE_MAP["as_group"]
        assert cs["outline"] == "#3298ff"
        assert cs["dashed"] == "1"
        assert cs["dashPattern"] == "5 5"

    def test_as_policy_blue_dashed(self):
        cs = CONTAINER_STYLE_MAP["as_policy"]
        assert cs["outline"] == "#3298ff"
        assert cs["dashed"] == "1"
        assert cs["dashPattern"] == "5 5"


# ── Edge style tests ────────────────────────────────────────────────────

class TestEdgeStyles:
    def test_management_edge_kind_exists(self):
        assert "management" in VALID_EDGE_KINDS

    def test_traffic_solid_black(self):
        es = EDGE_KIND_STYLE_MAP["traffic"]
        assert es["dashed"] == "0"
        assert es["strokeColor"] == "#333333"

    def test_management_dashed(self):
        es = EDGE_KIND_STYLE_MAP["management"]
        assert es["dashed"] == "1"
        assert es["strokeColor"] == "#333333"

    def test_replication_dashed(self):
        es = EDGE_KIND_STYLE_MAP["replication"]
        assert es["dashed"] == "1"
        assert es["strokeColor"] == "#333333"

    def test_notification_purple_dashed(self):
        es = EDGE_KIND_STYLE_MAP["notification"]
        assert es["dashed"] == "1"
        assert es["strokeColor"] == "#8e44ad"


# ── Iconic rendering tests ──────────────────────────────────────────────

def _make_iconic_spec() -> dict:
    """Return a template-driven spec with product fields for icon rendering."""
    return {
        "title": "Iconic HLD",
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


class TestIconicRendering:
    def test_iconic_spec_parses(self):
        spec = _make_iconic_spec()
        parsed = parse_architecture_spec(json.dumps(spec))
        assert parsed["nodes"][0]["product"] == "ELB"

    def test_iconic_render_produces_xml(self):
        spec = parse_architecture_spec(json.dumps(_make_iconic_spec()))
        style = _load_style_preset()
        xml = render_spec_to_drawio_xml(spec, style)
        assert "<mxfile>" in xml
        assert "diagram" in xml

    def test_icon_nodes_use_image_style(self):
        spec = parse_architecture_spec(json.dumps(_make_iconic_spec()))
        style = _load_style_preset()
        xml = render_spec_to_drawio_xml(spec, style)
        # Icon nodes should use shape=image style
        assert "shape=image" in xml
        # Should have verticalLabelPosition=bottom for icon+label layout
        assert "verticalLabelPosition=bottom" in xml

    def test_management_edge_kind_accepted(self):
        spec = _make_iconic_spec()
        spec["edges"].append(
            {"source": "ecs", "target": "rds", "label": "admin", "edge_kind": "management"}
        )
        parsed = parse_architecture_spec(json.dumps(spec))
        assert parsed["edges"][-1]["edge_kind"] == "management"

    def test_fallback_when_no_product(self):
        """Nodes without product should still render (generic shape fallback)."""
        spec = _make_iconic_spec()
        spec["nodes"][0]["product"] = None
        parsed = parse_architecture_spec(json.dumps(spec))
        style = _load_style_preset()
        xml = render_spec_to_drawio_xml(parsed, style)
        assert "<mxfile>" in xml

    def test_fallback_when_unknown_product(self):
        """Nodes with unknown product should fall back to generic shape."""
        spec = _make_iconic_spec()
        spec["nodes"][0]["product"] = "UnknownService"
        parsed = parse_architecture_spec(json.dumps(spec))
        style = _load_style_preset()
        xml = render_spec_to_drawio_xml(parsed, style)
        assert "<mxfile>" in xml

    def test_orthogonal_edge_style(self):
        spec = parse_architecture_spec(json.dumps(_make_iconic_spec()))
        style = _load_style_preset()
        xml = render_spec_to_drawio_xml(spec, style)
        assert "orthogonalEdgeStyle" in xml

    def test_edge_stroke_width(self):
        spec = parse_architecture_spec(json.dumps(_make_iconic_spec()))
        style = _load_style_preset()
        xml = render_spec_to_drawio_xml(spec, style)
        assert "strokeWidth=1" in xml


import json
