"""Render a real .pptx proposal from template + content data."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.enum.text import PP_ALIGN

logger = logging.getLogger(__name__)

# Default template path relative to repo root
DEFAULT_TEMPLATE_PATH = Path(
    "/root/huawei-latam-smb-site/public/assets/huawei/proposal/Proposal Template.pptx"
)


def _slide(prs: Presentation, slide_number: int):
    """Return a 1-based slide from the template, or None if absent."""
    index = slide_number - 1
    if 0 <= index < len(prs.slides):
        return prs.slides[index]
    return None


def _shape_text(shape: Any) -> str:
    if not getattr(shape, "has_text_frame", False):
        return ""
    return shape.text_frame.text or ""


def _set_text(shape: Any, text: str, *, font_size: int | None = None, bold: bool | None = None) -> None:
    """Replace text in a shape while preserving the shape box and basic styling."""
    if not getattr(shape, "has_text_frame", False):
        return
    tf = shape.text_frame
    tf.clear()
    tf.word_wrap = True
    lines = str(text or "").splitlines() or [""]
    for index, line in enumerate(lines):
        paragraph = tf.paragraphs[0] if index == 0 else tf.add_paragraph()
        paragraph.text = line
        paragraph.alignment = PP_ALIGN.LEFT
        if font_size is not None:
            for run in paragraph.runs:
                run.font.size = Pt(font_size)
        if bold is not None:
            for run in paragraph.runs:
                run.font.bold = bold


def _clear_update_markers(slide: Any) -> int:
    cleared = 0
    for shape in slide.shapes:
        if _shape_text(shape).strip().lower() == "update":
            _set_text(shape, "")
            cleared += 1
    return cleared


def _first_text_shape_containing(slide: Any, needle: str):
    needle_low = needle.lower()
    for shape in slide.shapes:
        if needle_low in _shape_text(shape).lower():
            return shape
    return None


def _append_bullets(title: str, values: list[str]) -> str:
    clean = [v.strip() for v in values if isinstance(v, str) and v.strip()]
    if not clean:
        return ""
    return f"{title}\n" + "\n".join(f"- {value}" for value in clean)


def _apply_template_content(
    prs: Presentation,
    proposal_data: dict[str, Any],
    hld_png_path: Path | None,
) -> dict[str, Any]:
    """Fill known update-marked template pages with proposal content."""
    sections = proposal_data.get("sections", {})
    content_selection = proposal_data.get("content_selection", {})
    migration_context = proposal_data.get("migration_context", {})
    project_name = proposal_data.get("project_name") or "Proposal"
    customer_name = proposal_data.get("customer_name") or ""
    country = proposal_data.get("country") or ""
    proposal_title = proposal_data.get("proposal_title") or f"Propuesta Tecnica {customer_name or project_name}"
    proposal_subtitle = proposal_data.get("proposal_subtitle") or project_name
    assumptions = proposal_data.get("assumptions") or []
    risks = proposal_data.get("risks") or []

    updated_pages: list[int] = []
    hld_image_embedded = False

    # Slide 1: cover.
    slide = _slide(prs, 1)
    if slide:
        region_shape = _first_text_shape_containing(slide, "HUAWEI CLOUD")
        if region_shape:
            _set_text(region_shape, f"HUAWEI CLOUD {country}".strip(), font_size=16, bold=True)
        cover_shape = _first_text_shape_containing(slide, "[Customer Name]") or _first_text_shape_containing(slide, "Propuesta")
        if cover_shape:
            lines = [proposal_title]
            if proposal_subtitle:
                lines.append(proposal_subtitle)
            if customer_name:
                lines.append(customer_name)
            _set_text(cover_shape, "\n".join(lines), font_size=24, bold=True)
        updated_pages.append(1)

    # Slide 3: overview and project background.
    slide = _slide(prs, 3)
    if slide:
        overview = (
            "Vision general\n"
            f"{sections.get('executive_summary') or proposal_data.get('business_background') or ''}\n\n"
            "Antecedentes del proyecto\n"
            f"{proposal_data.get('business_background') or ''}\n\n"
            "Desafios actuales\n"
            f"{sections.get('current_challenges') or proposal_data.get('current_pain_points') or ''}\n\n"
            "Resultados esperados\n"
            f"{sections.get('target_solution') or proposal_data.get('target_outcomes') or ''}"
        )
        body_shape = _first_text_shape_containing(slide, "Visión general")
        if body_shape:
            _set_text(body_shape, overview, font_size=11)
        _clear_update_markers(slide)
        updated_pages.append(3)

    # Slide 5: project objectives.
    slide = _slide(prs, 5)
    if slide:
        objective_shape = slide.shapes[0] if slide.shapes else None
        if objective_shape and getattr(objective_shape, "has_text_frame", False):
            objective_text = (
                "El objetivo de este proyecto es entregar una propuesta tecnica para "
                f"{project_name}, alineada con los objetivos de negocio del cliente.\n\n"
                f"{sections.get('target_solution') or proposal_data.get('target_outcomes') or ''}\n\n"
                "La solucion propuesta considera seguridad, escalabilidad, continuidad operacional "
                "y una ruta de adopcion por fases segun el alcance seleccionado."
            )
            _set_text(objective_shape, objective_text, font_size=12)
        _clear_update_markers(slide)
        updated_pages.append(5)

    # Slide 13: architecture diagram.
    slide = _slide(prs, 13)
    if slide:
        _clear_update_markers(slide)
        if hld_png_path and hld_png_path.exists():
            try:
                slide.shapes.add_picture(str(hld_png_path), Inches(0.85), Inches(1.0), width=Inches(11.6), height=Inches(5.7))
                hld_image_embedded = True
            except Exception as exc:
                logger.warning("Failed to embed HLD image on template slide 13: %s", exc)
        else:
            placeholder = _first_text_shape_containing(slide, "Vista General")
            if placeholder:
                note = slide.shapes.add_textbox(Inches(0.9), Inches(1.6), Inches(11.0), Inches(1.0))
                _set_text(note, "Architecture diagram is pending from the HLD workflow.", font_size=18)
        updated_pages.append(13)

    # Slide 14: service configuration / pricing summary.
    slide = _slide(prs, 14)
    if slide:
        pricing = sections.get("pricing_summary") or ""
        if proposal_data.get("quote_status") == "pending_external_workflow":
            pricing = "Pricing is pending from the Pricing workflow."
        elif not content_selection.get("include_price", True):
            pricing = "Pricing was not included in this proposal scope."
        if pricing:
            box = slide.shapes.add_textbox(Inches(0.8), Inches(6.25), Inches(11.2), Inches(0.55))
            _set_text(box, pricing, font_size=11)
        _clear_update_markers(slide)
        updated_pages.append(14)

    # Slide 15: architecture description and assumptions.
    slide = _slide(prs, 15)
    if slide:
        description_shape = _first_text_shape_containing(slide, "Conectividad")
        if description_shape:
            architecture_text = (
                "1. Descripcion de la solucion\n"
                f"{sections.get('target_solution') or proposal_data.get('target_outcomes') or ''}\n\n"
                "2. Consideraciones de diseno\n"
                f"HLD status: {proposal_data.get('hld_status', 'skipped')}. "
                "La arquitectura debe validarse con los equipos tecnicos del cliente antes de la implementacion.\n\n"
                "3. Seguridad y operacion\n"
                "La propuesta considera buenas practicas de segmentacion, control de acceso, monitoreo y continuidad operacional."
            )
            _set_text(description_shape, architecture_text, font_size=10)
        assumptions_shape = _first_text_shape_containing(slide, "La conectividad")
        if assumptions_shape:
            assumption_text = _append_bullets("Supuestos del Diseno", assumptions) or "Supuestos del Diseno\n- Pendiente de validacion con el cliente."
            risk_text = _append_bullets("Riesgos", risks)
            _set_text(assumptions_shape, f"{assumption_text}\n\n{risk_text}".strip(), font_size=10)
        updated_pages.append(15)

    # Slide 20: migration plan.
    if content_selection.get("include_migration", False):
        slide = _slide(prs, 20)
        if slide:
            migration_text = (
                "Supuestos:\n"
                f"- Alcance: {migration_context.get('scope') or 'Pendiente de definicion.'}\n"
                f"- Restricciones: {migration_context.get('constraints') or 'Pendiente de validacion.'}\n"
                f"- Notas: {migration_context.get('notes') or 'Se recomienda una migracion por fases con validacion antes del cutover.'}"
            )
            body_shape = _first_text_shape_containing(slide, "Supuestos:")
            if body_shape:
                _set_text(body_shape, migration_text, font_size=13)
            _clear_update_markers(slide)
            updated_pages.append(20)

    # Slide 23 and 25: customer-specific support/training markers.
    if content_selection.get("include_support_training", False):
        slide = _slide(prs, 23)
        if slide:
            logo_shape = _first_text_shape_containing(slide, "Customer logo")
            if logo_shape:
                _set_text(logo_shape, customer_name or "Customer", font_size=12, bold=True)
            updated_pages.append(23)
        slide = _slide(prs, 25)
        if slide:
            title_shape = _first_text_shape_containing(slide, "Capacitación profesional")
            if title_shape:
                _set_text(
                    title_shape,
                    f"Capacitacion profesional para servicios en la nube\nPlan de formacion para {customer_name or project_name}",
                    font_size=16,
                    bold=True,
                )
            updated_pages.append(25)

    return {
        "template_pages_updated": sorted(set(updated_pages)),
        "hld_image_embedded": hld_image_embedded,
    }


def _add_title_slide(prs: Presentation, title: str, subtitle: str = "") -> None:
    """Add a title + subtitle slide using a blank layout."""
    layout = prs.slide_layouts[6] if len(prs.slide_layouts) > 6 else prs.slide_layouts[0]
    slide = prs.slides.add_slide(layout)
    left = Inches(0.5)
    top = Inches(0.5)
    width = Inches(9)
    height = Inches(1.2)
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = title
    p.font.size = Pt(28)
    p.font.bold = True
    if subtitle:
        p2 = tf.add_paragraph()
        p2.text = subtitle
        p2.font.size = Pt(14)


def _add_content_slide(prs: Presentation, title: str, body: str) -> None:
    """Add a slide with a title and body text."""
    layout = prs.slide_layouts[6] if len(prs.slide_layouts) > 6 else prs.slide_layouts[0]
    slide = prs.slides.add_slide(layout)
    # Title
    txBox = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(9), Inches(0.8))
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = title
    p.font.size = Pt(24)
    p.font.bold = True
    # Body
    txBox2 = slide.shapes.add_textbox(Inches(0.5), Inches(1.3), Inches(9), Inches(5.5))
    tf2 = txBox2.text_frame
    tf2.word_wrap = True
    # Split body into paragraphs
    for i, line in enumerate(body.split("\n")):
        if i == 0:
            p2 = tf2.paragraphs[0]
        else:
            p2 = tf2.add_paragraph()
        p2.text = line
        p2.font.size = Pt(12)
        p2.space_after = Pt(4)


def _add_image_slide(prs: Presentation, title: str, image_path: Path) -> bool:
    """Add a slide with a title and an image. Returns True if image was embedded."""
    layout = prs.slide_layouts[6] if len(prs.slide_layouts) > 6 else prs.slide_layouts[0]
    slide = prs.slides.add_slide(layout)
    # Title
    txBox = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(9), Inches(0.8))
    tf = txBox.text_frame
    p = tf.paragraphs[0]
    p.text = title
    p.font.size = Pt(24)
    p.font.bold = True
    # Image — centered, max 8x5 inches
    if image_path.exists():
        try:
            slide.shapes.add_picture(
                str(image_path),
                Inches(0.5), Inches(1.3),
                Inches(8), Inches(5),
            )
            return True
        except Exception as exc:
            logger.warning("Failed to embed image %s: %s", image_path, exc)
    return False


def render_proposal_pptx(
    template_path: Path,
    output_path: Path,
    proposal_data: dict[str, Any],
    hld_png_path: Path | None = None,
) -> dict[str, Any]:
    """Render a real .pptx from template + proposal content.

    Args:
        template_path: Path to the .pptx template.
        output_path: Where to write the output .pptx.
        proposal_data: The proposal.json content dict.
        hld_png_path: Optional path to HLD PNG to embed.

    Returns:
        dict with keys: slides_generated, hld_image_embedded

    Raises:
        FileNotFoundError: if template_path does not exist.
        Exception: any PPTX rendering error.
    """
    if not template_path.exists():
        raise FileNotFoundError(f"Proposal template not found: {template_path}")

    prs = Presentation(str(template_path))
    sections = proposal_data.get("sections", {})
    sections_generated: list[str] = []
    template_meta = _apply_template_content(prs, proposal_data, hld_png_path)
    template_pages_updated = template_meta["template_pages_updated"]

    # The Huawei template is the primary output surface. If a non-standard
    # template has no known update pages, append a compact fallback appendix.
    append_fallback_pages = not template_pages_updated

    # Executive Summary
    executive_summary = sections.get("executive_summary", "")
    if append_fallback_pages and executive_summary:
        _add_content_slide(prs, "Executive Summary", executive_summary)
        sections_generated.append("Executive Summary")

    # Solution Overview (current_challenges + target_solution)
    challenges = sections.get("current_challenges", "")
    solution = sections.get("target_solution", "")
    if append_fallback_pages and (challenges or solution):
        body = ""
        if challenges:
            body += f"Current Challenges:\n{challenges}\n\n"
        if solution:
            body += f"Proposed Solution:\n{solution}"
        _add_content_slide(prs, "Solution Overview", body)
        sections_generated.append("Solution Overview")

    # Pricing Summary — only if include_price
    content_selection = proposal_data.get("content_selection", {})
    if append_fallback_pages and content_selection.get("include_price", True):
        pricing = sections.get("pricing_summary", "")
        if pricing:
            _add_content_slide(prs, "Pricing Summary", pricing)
            sections_generated.append("Pricing Summary")

    # Assumptions & Risks
    assumptions = proposal_data.get("assumptions", [])
    risks = proposal_data.get("risks", [])
    if append_fallback_pages and (assumptions or risks):
        body = ""
        if assumptions:
            body += "Assumptions:\n" + "\n".join(f"- {a}" for a in assumptions) + "\n\n"
        if risks:
            body += "Risks:\n" + "\n".join(f"- {r}" for r in risks)
        _add_content_slide(prs, "Assumptions & Risks", body)
        sections_generated.append("Assumptions & Risks")

    # Next Steps
    next_steps = sections.get("next_steps", "")
    if append_fallback_pages and next_steps:
        _add_content_slide(prs, "Next Steps", next_steps)
        sections_generated.append("Next Steps")

    # HLD Architecture Diagram
    hld_image_embedded = bool(template_meta.get("hld_image_embedded"))
    if append_fallback_pages and hld_png_path and hld_png_path.exists():
        hld_image_embedded = _add_image_slide(prs, "Architecture Diagram", hld_png_path)
        if hld_image_embedded:
            sections_generated.append("Architecture Diagram")

    # Migration Plan — only if include_migration
    if append_fallback_pages and content_selection.get("include_migration", False):
        migration_context = proposal_data.get("migration_context", {})
        migration_body = ""
        if migration_context.get("scope"):
            migration_body += f"Scope: {migration_context['scope']}\n\n"
        if migration_context.get("constraints"):
            migration_body += f"Constraints: {migration_context['constraints']}\n\n"
        if migration_context.get("notes"):
            migration_body += f"Notes: {migration_context['notes']}\n\n"
        if not migration_body:
            migration_body = "Migration plan details to be determined."
        _add_content_slide(prs, "Migration Plan", migration_body)
        sections_generated.append("Migration Plan")

    # Support & Training — only if include_support_training
    if append_fallback_pages and content_selection.get("include_support_training", False):
        _add_content_slide(prs, "Support & Training", "Support and training details to be determined.")
        sections_generated.append("Support & Training")

    slides_generated = len(prs.slides)
    prs.save(str(output_path))
    logger.info("Rendered PPTX: %s (%d slides, hld_image=%s)", output_path, slides_generated, hld_image_embedded)

    return {
        "slides_generated": slides_generated,
        "sections_generated": sections_generated,
        "template_pages_updated": template_pages_updated,
        "hld_image_embedded": hld_image_embedded,
    }
