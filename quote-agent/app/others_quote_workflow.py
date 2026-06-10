"""Others Quote workflow.

Orchestrates the non-billing quote pipeline: ingest custom requirement sheets,
product comparison tables, or other non-billing Excel files, match rows
one-by-one against Huawei Cloud products, price, and summarize.

This is a pure row-by-row workflow — no billing aggregation, no billing
reclassification, no billing gap/reconciliation analysis.

Phase 6A: Uses Others-specific node implementations that guard against
billing path entry and skip billing-specific logic.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.flexible_workflow import (
    FlexibleQuoteState,
    ingest_files,
    load_pricebook,
    parse_documents,
    understand_input,
    extract_others_requirement_items,
    normalize_others_requirements,
    deduplicate_items,
    map_to_huawei_product,
    validate_quote_readiness,
    return_blockers,
    resolve_price_components,
    quote_items,
    summarize_others_quote,
    incorporate_feedback,
    export_flexible_workbook,
    _route_after_validation,
    build_flexible_preview_response,
    build_flexible_review_state,
)


# ── Others preview graph ────────────────────────────────────────────────────────


def build_others_preview_graph():
    """Build the Others Quote preview pipeline.

    Pipeline: ingest → load_pricebook → parse → understand →
              extract_others → normalize_others → deduplicate → map →
              validate → price → quote → summarize_others

    This is a pure row-by-row pipeline:
    - extract_others_requirement_items: rejects billing documents, extracts rows
    - normalize_others_requirements: standard product normalization only
    - summarize_others_quote: no billing gap/reconciliation analysis
    """
    graph = StateGraph(FlexibleQuoteState)
    graph.add_node("ingest_files", ingest_files)
    graph.add_node("load_pricebook", load_pricebook)
    graph.add_node("parse_documents", parse_documents)
    graph.add_node("understand_input", understand_input)
    graph.add_node("extract_requirement_items", extract_others_requirement_items)
    graph.add_node("normalize_requirements", normalize_others_requirements)
    graph.add_node("deduplicate_items", deduplicate_items)
    graph.add_node("map_to_huawei_product", map_to_huawei_product)
    graph.add_node("validate_quote_readiness", validate_quote_readiness)
    graph.add_node("return_blockers", return_blockers)
    graph.add_node("resolve_price_components", resolve_price_components)
    graph.add_node("quote_items", quote_items)
    graph.add_node("summarize_quote", summarize_others_quote)

    graph.add_edge(START, "ingest_files")
    graph.add_edge("ingest_files", "load_pricebook")
    graph.add_edge("load_pricebook", "parse_documents")
    graph.add_edge("parse_documents", "understand_input")
    graph.add_edge("understand_input", "extract_requirement_items")
    graph.add_edge("extract_requirement_items", "normalize_requirements")
    graph.add_edge("normalize_requirements", "deduplicate_items")
    graph.add_edge("deduplicate_items", "map_to_huawei_product")
    graph.add_edge("map_to_huawei_product", "validate_quote_readiness")
    graph.add_conditional_edges("validate_quote_readiness", _route_after_validation, {"needs_input": "return_blockers", "ready": "resolve_price_components"})
    graph.add_edge("return_blockers", "summarize_quote")
    graph.add_edge("resolve_price_components", "quote_items")
    graph.add_edge("quote_items", "summarize_quote")
    graph.add_edge("summarize_quote", END)
    return graph.compile()


# ── Others review graph ─────────────────────────────────────────────────────────


def build_others_review_graph():
    """Build the Others Quote review pipeline (after manual feedback)."""
    graph = StateGraph(FlexibleQuoteState)
    graph.add_node("incorporate_feedback", incorporate_feedback)
    graph.add_node("validate_quote_readiness", validate_quote_readiness)
    graph.add_node("return_blockers", return_blockers)
    graph.add_node("resolve_price_components", resolve_price_components)
    graph.add_node("quote_items", quote_items)
    graph.add_node("summarize_quote", summarize_others_quote)

    graph.add_edge(START, "incorporate_feedback")
    graph.add_edge("incorporate_feedback", "validate_quote_readiness")
    graph.add_conditional_edges("validate_quote_readiness", _route_after_validation, {"needs_input": "return_blockers", "ready": "resolve_price_components"})
    graph.add_edge("return_blockers", "summarize_quote")
    graph.add_edge("resolve_price_components", "quote_items")
    graph.add_edge("quote_items", "summarize_quote")
    graph.add_edge("summarize_quote", END)
    return graph.compile()


# ── Others export graph ─────────────────────────────────────────────────────────


def build_others_export_graph():
    """Build the Others Quote export pipeline (review → export workbook)."""
    graph = StateGraph(FlexibleQuoteState)
    graph.add_node("incorporate_feedback", incorporate_feedback)
    graph.add_node("validate_quote_readiness", validate_quote_readiness)
    graph.add_node("return_blockers", return_blockers)
    graph.add_node("resolve_price_components", resolve_price_components)
    graph.add_node("quote_items", quote_items)
    graph.add_node("summarize_quote", summarize_others_quote)
    graph.add_node("export_workbook", export_flexible_workbook)

    graph.add_edge(START, "incorporate_feedback")
    graph.add_edge("incorporate_feedback", "validate_quote_readiness")
    graph.add_conditional_edges("validate_quote_readiness", _route_after_validation, {"needs_input": "return_blockers", "ready": "resolve_price_components"})
    graph.add_edge("return_blockers", "summarize_quote")
    graph.add_edge("resolve_price_components", "quote_items")
    graph.add_edge("quote_items", "summarize_quote")
    graph.add_edge("summarize_quote", "export_workbook")
    graph.add_edge("export_workbook", END)
    return graph.compile()


# ── Compiled graph instances ────────────────────────────────────────────────────

others_preview_graph = build_others_preview_graph()
others_review_graph = build_others_review_graph()
others_export_graph = build_others_export_graph()
