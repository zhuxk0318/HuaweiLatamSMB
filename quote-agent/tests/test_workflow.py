from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pandas as pd
from starlette.datastructures import UploadFile

from app.main import export_quote
from app.pricebook import load_pricebook, pick_ecs_match
from app.rvtools import RvToolsParseError, parse_rvtools_workbook
from app.workflow import export_graph


def make_rvtools_file(
    *,
    info_rows: list[dict[str, object]] | None = None,
    disk_rows: list[dict[str, object]] | None = None,
    include_vinfo: bool = True,
) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        if include_vinfo:
            pd.DataFrame(info_rows or []).to_excel(writer, sheet_name="vInfo", index=False)
        pd.DataFrame(disk_rows or []).to_excel(writer, sheet_name="vDisk", index=False)
    return buffer.getvalue()


def test_parse_rvtools_supports_variants_and_aggregates_disk():
    content = make_rvtools_file(
        info_rows=[
            {"VM Name": "app-01", "Power State": "PoweredOn", "NumCpu": 2, "Memory MB": 8192, "OS": "Windows"},
        ],
        disk_rows=[
            {"VM": "app-01", "Capacity GB": 100},
            {"VM": "app-01", "Provisioned GB": 50},
        ],
    )

    parsed, _, _ = parse_rvtools_workbook(content)

    assert len(parsed) == 1
    assert parsed[0].vm_name == "app-01"
    assert parsed[0].vcpu == 2
    assert parsed[0].memory_gib == 8
    assert parsed[0].disk_gib == 150


def test_parse_rvtools_requires_vinfo():
    content = make_rvtools_file(include_vinfo=False, disk_rows=[{"VM": "x", "Capacity GB": 10}])
    try:
        parse_rvtools_workbook(content)
    except RvToolsParseError as exc:
        assert "vInfo" in str(exc)
    else:
        raise AssertionError("Expected missing vInfo error")


def test_price_engine_respects_region_evs_and_category_priority():
    pricebook = load_pricebook()
    mexico = pricebook["pricingCatalog"]["mexico"]
    chile = pricebook["pricingCatalog"]["chile"]

    mexico_match = pick_ecs_match(mexico, 2, 8)
    chile_match = pick_ecs_match(chile, 2, 8)

    assert mexico_match is not None
    assert chile_match is not None
    assert mexico_match["category"] == "General Computing"
    assert chile_match["category"] == "General Computing"
    assert mexico["regionCode"] != chile["regionCode"]
    assert mexico_match["spec"]
    assert chile_match["spec"]

    evs_by_key = {item["key"]: item for item in mexico["evs"]}
    assert evs_by_key["gpssd"]["monthlyEquivalentUsdPerGb"] != evs_by_key["sas"]["monthlyEquivalentUsdPerGb"]


def test_graph_quotes_and_exports_without_maas():
    load_pricebook.cache_clear()
    content = make_rvtools_file(
        info_rows=[
            {"VM": "linux-on", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4},
            {"VM": "linux-off", "Powerstate": "PoweredOff", "CPUs": 2, "Memory": 4},
            {"VM": "oversized", "Powerstate": "PoweredOn", "CPUs": 999, "Memory": 999},
        ],
        disk_rows=[
            {"VM": "linux-on", "Capacity GiB": 120},
            {"VM": "linux-off", "Capacity GiB": 80},
            {"VM": "oversized", "Capacity GiB": 200},
        ],
    )

    result = export_graph.invoke(
        {
            "request": {"region": "mexico", "evs_type": "gpssd", "lang": "en", "source_filename": "sample.xlsx"},
            "file_bytes": content,
        }
    )

    workbook = result["workbook"]
    with ZipFile(BytesIO(workbook.content)) as archive:
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
    assert "Summary" in workbook_xml
    assert "Quote Lines" in workbook_xml
    assert "Manual Review" in workbook_xml
    assert "Raw RVTools" in workbook_xml
    assert "Pricebook Used" in workbook_xml
    summary = result["summary"]
    assert summary["quoted_vms"] == 1
    assert summary["excluded_vms"] == 1
    assert summary["manual_review_vms"] == 1
    quoted_line = next(line for line in result["quote_lines"] if line["vm_name"] == "linux-on")
    assert quoted_line["ecs_ondemand_monthly_usd"] == 33.58


def test_export_api_returns_excel():
    content = make_rvtools_file(
        info_rows=[{"VM": "api-01", "Powerstate": "PoweredOn", "CPUs": 2, "Memory": 4}],
        disk_rows=[{"VM": "api-01", "Capacity GiB": 100}],
    )

    response = export_quote(
        UploadFile(filename="sample.xlsx", file=BytesIO(content)),
        "mexico",
        "gpssd",
        "en",
    )

    assert response.status_code == 200
    assert response.media_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert 'quote-mexico-' in response.headers["content-disposition"]
