"""Phase A tests: Azure billing CSV parsing (SEP=, header, BOM, empty trailing columns)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.flexible_workflow import _parse_csv_document, _strip_sep_header, _drop_empty_columns
import pandas as pd


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

AZURE_CSV_PATH = Path("/root/SMBReference/CGE/azure Billing_invoice_transactions.csv")


@pytest.fixture
def azure_csv_bytes() -> bytes:
    """Read the real Azure billing CSV (includes SEP=, line)."""
    assert AZURE_CSV_PATH.exists(), f"Azure CSV not found at {AZURE_CSV_PATH}"
    return AZURE_CSV_PATH.read_bytes()


def _minimal_azure_csv() -> bytes:
    """Tiny Azure-like CSV with SEP=, header for fast unit tests."""
    return (
        "SEP=,\r\n"
        "DATE (UTC),PRODUCT FAMILY,PRODUCT TYPE,PRODUCT SKU,UNIT TYPE,QUANTITY,\r\n"
        '"4/3/2026","Developer Tools","API Management","API Management - Desarrollador","1 unidad/hora","2,232",\r\n'
        '"4/3/2026","Storage","Backup","Backup - Estándar","Datos almacenados GRS (GB/mes)","244.65",\r\n'
    ).encode("utf-8-sig")  # include BOM


# ---------------------------------------------------------------------------
# _strip_sep_header
# ---------------------------------------------------------------------------

class TestStripSepHeader:
    def test_strips_sep_line(self):
        text = "SEP=,\nA,B\n1,2"
        cleaned, had_sep = _strip_sep_header(text)
        assert had_sep is True
        assert cleaned == "A,B\n1,2"

    def test_no_sep_line(self):
        text = "A,B\n1,2"
        cleaned, had_sep = _strip_sep_header(text)
        assert had_sep is False
        assert cleaned == text

    def test_sep_with_spaces(self):
        text = "SEP = ,\nA,B\n1,2"
        cleaned, had_sep = _strip_sep_header(text)
        assert had_sep is True
        assert cleaned == "A,B\n1,2"


# ---------------------------------------------------------------------------
# _drop_empty_columns
# ---------------------------------------------------------------------------

class TestDropEmptyColumns:
    def test_drops_unnamed_and_blank_columns(self):
        frame = pd.DataFrame({"A": [1], "": [""], "Unnamed: 5": [""]})
        result = _drop_empty_columns(frame)
        assert list(result.columns) == ["A"]

    def test_keeps_non_empty_columns(self):
        frame = pd.DataFrame({"A": [1], "B": ["x"]})
        result = _drop_empty_columns(frame)
        assert list(result.columns) == ["A", "B"]


# ---------------------------------------------------------------------------
# Core Azure CSV parse tests (required 3)
# ---------------------------------------------------------------------------

class TestParseAzureBillingCsv:
    def test_parse_azure_billing_csv_skips_sep_header(self):
        """Columns must be real Azure headers, not the broken SEP=/Unnamed:1 two-column result."""
        doc = _parse_csv_document(_minimal_azure_csv(), "azure_billing.csv")
        cols = doc["columns"]
        # Must contain key Azure columns
        for expected in ["DATE (UTC)", "PRODUCT FAMILY", "PRODUCT TYPE", "PRODUCT SKU", "UNIT TYPE"]:
            assert expected in cols, f"Missing expected column: {expected}"
        # Must NOT be the broken two-column result
        assert len(cols) > 2, f"Only {len(cols)} columns parsed — SEP=, was not skipped"
        # Metadata
        assert doc["document_type"] == "azure_billing_csv"
        assert doc["dialect"] == "excel_sep_header"

    def test_parse_azure_billing_csv_preserves_row_count(self, azure_csv_bytes: bytes):
        """Real file has 82 data rows after the SEP=, line and header."""
        doc = _parse_csv_document(azure_csv_bytes, "azure Billing_invoice_transactions.csv")
        assert len(doc["rows"]) == 82, f"Expected 82 data rows, got {len(doc['rows'])}"

    def test_parse_azure_billing_csv_adds_line_numbers(self):
        """_line_number starts at 2 (row 1 = header in the cleaned CSV)."""
        doc = _parse_csv_document(_minimal_azure_csv(), "azure_billing.csv")
        rows = doc["rows"]
        assert rows[0]["_line_number"] == 2, "First data row should have _line_number == 2"
        assert rows[1]["_line_number"] == 3, "Second data row should have _line_number == 3"


# ---------------------------------------------------------------------------
# Compatibility: plain CSV without SEP=, still works
# ---------------------------------------------------------------------------

class TestPlainCsvCompat:
    def test_plain_csv_without_sep(self):
        """A normal CSV (no SEP=, no BOM) must still parse correctly."""
        csv = b"A,B,C\n1,2,3\n4,5,6\n"
        doc = _parse_csv_document(csv, "plain.csv")
        assert doc["columns"] == ["A", "B", "C"]
        assert len(doc["rows"]) == 2
        assert doc["rows"][0]["_line_number"] == 2
        # No SEP=, metadata should be absent
        assert "document_type" not in doc
        assert "dialect" not in doc
