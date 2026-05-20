"""HLD wizard recommendation engine.

Context-driven recommendations with source tracking.
- Step 1 (project_name): static only, no API call needed.
- Rule-allowed fields (deployment_mode, user_access_entry, preferred_filename):
  rules may produce dynamic answers from prior context, source="rule".
- Context-driven fields (business_goal, architecture_boundary, core_components,
  external_integrations, data_stores_flow, network_security_boundary):
  rules that use prior answers dynamically; LLM fallback when rules are insufficient.
- Every response includes source: "static" | "rule" | "llm" | "fallback_default".
"""
from __future__ import annotations

import json
import logging
import os
import re

from app.models import (
    HldRecommendationRequest,
    HldRecommendationResponse,
    HldRecommendationSource,
    HldWizardStep,
)

logger = logging.getLogger(__name__)

# ── Step routing table ────────────────────────────────────────────────────

ALL_STEPS: list[str] = [
    "project_name",
    "business_goal",
    "architecture_boundary",
    "deployment_mode",
    "user_access_entry",
    "core_components",
    "external_integrations",
    "data_stores_flow",
    "network_security_boundary",
    "preferred_filename",
]

# Steps that are purely static (no recommendation API call needed)
STATIC_STEPS: set[str] = {"project_name"}

# Steps where rule-based answers are acceptable as primary source
RULE_ALLOWED_STEPS: set[str] = {"deployment_mode", "user_access_entry", "preferred_filename"}

# Steps that must be context-driven — rules may produce answers but LLM fallback
# is expected when rules don't cover the specific context
CONTEXT_DRIVEN_STEPS: set[str] = {
    "business_goal",
    "architecture_boundary",
    "core_components",
    "external_integrations",
    "data_stores_flow",
    "network_security_boundary",
}

KNOWN_SERVICE_TOKENS: list[str] = [
    "ecs",
    "cce",
    "cci",
    "modelarts",
    "rds mysql",
    "rds",
    "gaussdb",
    "dds",
    "dcs",
    "redis",
    "obs",
    "evs",
    "sfs",
    "elb",
    "waf",
    "vpc",
    "nat gateway",
    "nat",
    "vpn",
    "dli",
]


def _extract_component_tokens(components: str) -> set[str]:
    text = components.lower()
    found: set[str] = set()
    for token in KNOWN_SERVICE_TOKENS:
        if token in text:
            found.add(token)
    return found


# ── Rule-based recommendations ──────────────────────────────────────────

def _rule_recommend(step: str, answers: dict[str, str], language: str) -> HldRecommendationResponse | None:
    """Return a rule-based recommendation if available, else None.

    Rules use prior answers dynamically — never return hardcoded text that
    ignores the user's accumulated context.
    """
    is_es = language == "es"
    is_zh = language == "zh"

    if step == "business_goal":
        project = answers.get("project_name", "").lower()
        if not project:
            return None
        if any(kw in project for kw in ("migrate", "migration", "migrar", "迁移")):
            val = "Migrate existing on-prem workloads to Huawei Cloud to reduce cost and improve reliability" if not is_zh else "将现有本地工作负载迁移至华为云以降低成本并提升可靠性"
        elif any(kw in project for kw in ("ai", "assistant", "modelo", "模型")):
            val = "Build an AI-powered assistant to improve internal knowledge access and productivity" if not is_zh else "构建AI驱动的助手以改善内部知识访问和生产力"
        elif any(kw in project for kw in ("portal", "crm", "service", "门户", "服务")):
            val = "Modernize customer-facing portal for better UX and lower operational cost" if not is_zh else "现代化面向客户的门户以改善用户体验并降低运营成本"
        else:
            return None
        if is_es and not is_zh:
            # Provide Spanish version for common patterns
            if "migrate" in val.lower() or "migrat" in val.lower():
                val = "Migrar cargas de trabajo on-prem existentes a Huawei Cloud para reducir costos y mejorar confiabilidad"
            elif "ai" in val.lower():
                val = "Construir un asistente impulsado por IA para mejorar acceso a conocimiento interno y productividad"
            elif "portal" in val.lower() or "modernize" in val.lower():
                val = "Modernizar portal orientado al cliente para mejor UX y menor costo operativo"
        return HldRecommendationResponse(recommended_answer=val, source="rule")

    if step == "architecture_boundary":
        goal = (answers.get("business_goal", "") + " " + answers.get("project_name", "")).lower()
        if any(kw in goal for kw in ("website", "portal", "app", "api", "web", "sitio", "网站", "应用")):
            val = "Application" if not is_es else "Aplicación" if not is_zh else "应用层"
        elif any(kw in goal for kw in ("multi-branch", "enterprise", "vpn", "access", "sucursal", "企业", "分支")):
            val = "Application + Network" if not is_es else "Aplicación + Red" if not is_zh else "应用 + 网络"
        elif any(kw in goal for kw in ("migrate", "migration", "migrar", "迁移")):
            val = "Application + Platform + Network" if not is_es else "Aplicación + Plataforma + Red" if not is_zh else "应用 + 平台 + 网络"
        else:
            return None
        return HldRecommendationResponse(recommended_answer=val, source="rule")

    if step == "deployment_mode":
        goal = (answers.get("business_goal", "") + " " + answers.get("architecture_boundary", "")).lower()
        if any(kw in goal for kw in ("migrate", "migration", "migrar", "迁移")):
            val = "cloud" if not is_zh else "云"
        elif any(kw in goal for kw in ("hybrid", "on-prem", "本地")):
            val = "hybrid" if not is_zh else "混合"
        else:
            val = "cloud" if not is_zh else "云"
        if is_es and not is_zh:
            val = {"cloud": "nube", "hybrid": "híbrido"}.get(val, val)
        return HldRecommendationResponse(recommended_answer=val, source="rule")

    if step == "user_access_entry":
        boundary = answers.get("architecture_boundary", "").lower()
        if "network" in boundary:
            val = "Web / Mobile via ELB + WAF; VPN for admin access" if not is_es else "Web / Móvil vía ELB + WAF; VPN para acceso admin" if not is_zh else "Web / 移动端 通过 ELB + WAF；VPN 用于管理访问"
        else:
            val = "Web / Mobile via ELB + WAF" if not is_es else "Web / Móvil vía ELB + WAF" if not is_zh else "Web / 移动端 通过 ELB + WAF"
        return HldRecommendationResponse(recommended_answer=val, source="rule")

    if step == "core_components":
        goal = (answers.get("business_goal", "") + " " + answers.get("project_name", "")).lower()
        boundary = answers.get("architecture_boundary", "").lower()
        if any(kw in goal for kw in ("migrate", "migration", "migrar", "迁移")):
            val = "ECS, ELB, RDS MySQL, OBS, VPC" if not is_zh else "ECS, ELB, RDS MySQL, OBS, VPC"
        elif any(kw in goal for kw in ("ai", "ml", "model", "modelo", "模型")):
            val = "CCE, ModelArts, OBS, RDS, ELB" if not is_zh else "CCE, ModelArts, OBS, RDS, ELB"
        elif any(kw in goal for kw in ("portal", "crm", "service", "门户", "服务")):
            val = "ECS, ELB, RDS MySQL, OBS, VPC, WAF" if not is_zh else "ECS, ELB, RDS MySQL, OBS, VPC, WAF"
        elif "platform" in boundary:
            val = "ECS, CCE, RDS MySQL, OBS, ELB, VPC" if not is_zh else "ECS, CCE, RDS MySQL, OBS, ELB, VPC"
        else:
            return None
        return HldRecommendationResponse(recommended_answer=val, source="rule")

    if step == "external_integrations":
        goal = answers.get("business_goal", "").lower()
        if any(kw in goal for kw in ("erp", "sap")):
            val = "SAP ERP via Direct Connect" if not is_es else "SAP ERP vía Direct Connect" if not is_zh else "通过 Direct Connect 连接 SAP ERP"
        elif any(kw in goal for kw in ("crm", "salesforce")):
            val = "Salesforce API, email notifications" if not is_es else "API Salesforce, notificaciones por email" if not is_zh else "Salesforce API，邮件通知"
        elif any(kw in goal for kw in ("office", "365", "microsoft")):
            val = "Office 365 / Entra ID for SSO" if not is_es else "Office 365 / Entra ID para SSO" if not is_zh else "Office 365 / Entra ID 用于 SSO"
        else:
            return None
        return HldRecommendationResponse(recommended_answer=val, source="rule")

    if step == "data_stores_flow":
        component_tokens = _extract_component_tokens(answers.get("core_components", ""))
        if not component_tokens:
            return None

        fragments_en: list[str] = []
        if "ecs" in component_tokens or "cce" in component_tokens or "cci" in component_tokens:
            fragments_en.append("Application services process requests")

        if "rds mysql" in component_tokens:
            fragments_en.append("transactional data is stored in RDS MySQL")
        elif "rds" in component_tokens:
            fragments_en.append("transactional data is stored in RDS")
        elif "gaussdb" in component_tokens:
            fragments_en.append("transactional data is stored in GaussDB")
        elif "dds" in component_tokens:
            fragments_en.append("document data is stored in DDS")

        if "obs" in component_tokens:
            fragments_en.append("files and backups are stored in OBS")
        elif "evs" in component_tokens:
            fragments_en.append("persistent block storage is provided by EVS")
        elif "sfs" in component_tokens:
            fragments_en.append("shared files are stored in SFS")

        if "dcs" in component_tokens or "redis" in component_tokens:
            fragments_en.append("hot data is cached in DCS Redis")

        if "modelarts" in component_tokens:
            fragments_en.append("model artifacts and AI outputs are managed through ModelArts")

        if "dli" in component_tokens:
            fragments_en.append("analytics queries are processed in DLI")

        if not fragments_en:
            return None

        val = "; ".join(fragments_en)
        if is_es and not is_zh:
            mapping = {
                "Application services process requests": "Los servicios de aplicación procesan las solicitudes",
                "transactional data is stored in RDS MySQL": "los datos transaccionales se almacenan en RDS MySQL",
                "transactional data is stored in RDS": "los datos transaccionales se almacenan en RDS",
                "transactional data is stored in GaussDB": "los datos transaccionales se almacenan en GaussDB",
                "document data is stored in DDS": "los datos documentales se almacenan en DDS",
                "files and backups are stored in OBS": "los archivos y respaldos se almacenan en OBS",
                "persistent block storage is provided by EVS": "el almacenamiento persistente en bloques se proporciona con EVS",
                "shared files are stored in SFS": "los archivos compartidos se almacenan en SFS",
                "hot data is cached in DCS Redis": "los datos de acceso frecuente se almacenan en caché en DCS Redis",
                "model artifacts and AI outputs are managed through ModelArts": "los artefactos del modelo y las salidas de IA se gestionan con ModelArts",
                "analytics queries are processed in DLI": "las consultas analíticas se procesan en DLI",
            }
            val = "; ".join(mapping.get(fragment, fragment) for fragment in fragments_en)
        elif is_zh:
            mapping = {
                "Application services process requests": "应用服务处理请求",
                "transactional data is stored in RDS MySQL": "事务数据存储在 RDS MySQL",
                "transactional data is stored in RDS": "事务数据存储在 RDS",
                "transactional data is stored in GaussDB": "事务数据存储在 GaussDB",
                "document data is stored in DDS": "文档型数据存储在 DDS",
                "files and backups are stored in OBS": "文件和备份存储在 OBS",
                "persistent block storage is provided by EVS": "持久块存储由 EVS 提供",
                "shared files are stored in SFS": "共享文件存储在 SFS",
                "hot data is cached in DCS Redis": "热点数据缓存在 DCS Redis",
                "model artifacts and AI outputs are managed through ModelArts": "模型产物和 AI 输出通过 ModelArts 管理",
                "analytics queries are processed in DLI": "分析查询在 DLI 中处理",
            }
            val = "；".join(mapping.get(fragment, fragment) for fragment in fragments_en)
        return HldRecommendationResponse(recommended_answer=val, source="rule")

    if step == "network_security_boundary":
        boundary = answers.get("architecture_boundary", "").lower()
        components = answers.get("core_components", "").lower()
        has_waf = "waf" in components
        base = "VPC with public subnet (ELB"
        if has_waf:
            base += " + WAF"
        base += ") and private subnets (app + data); NAT Gateway for egress"
        if "network" in boundary:
            base += "; VPN for admin access; Direct Connect for hybrid if needed"
        if is_zh:
            base = "VPC 包含公有子网 (ELB"
            if has_waf:
                base += " + WAF"
            base += ") 和私有子网 (应用 + 数据)；NAT 网关用于出站"
            if "network" in boundary:
                base += "；VPN 用于管理访问；Direct Connect 用于混合场景"
        elif is_es:
            base = "VPC con subred pública (ELB"
            if has_waf:
                base += " + WAF"
            base += ") y subredes privadas (app + datos); NAT Gateway para salida"
            if "network" in boundary:
                base += "; VPN para acceso admin; Direct Connect para híbrido si necesario"
        return HldRecommendationResponse(recommended_answer=base, source="rule")

    if step == "preferred_filename":
        project = answers.get("project_name", "")
        if project:
            safe = re.sub(r"[^\w\-.]", "_", project.strip())
            return HldRecommendationResponse(recommended_answer=safe, source="rule")
        return HldRecommendationResponse(recommended_answer="hld-design", source="rule")

    return None


# ── LLM-based recommendation (fallback for complex fields) ─────────────

def _llm_recommend(
    step: str,
    answers: dict[str, str],
    language: str,
    *,
    baseline: str = "",
) -> HldRecommendationResponse:
    """Use LLM to generate a recommendation.

    For every non-static step, the LLM should get a chance to refine the
    recommendation. A rule-derived baseline is provided when available so the
    model can improve it rather than starting from scratch.
    """
    try:
        from app.chat_service import build_chat_client_from_env
    except Exception:
        return HldRecommendationResponse(recommended_answer="", source="fallback_default")

    api_key = os.getenv("HUAWEI_MAAS_API_KEY")
    base_url = os.getenv("HUAWEI_MAAS_BASE_URL")
    model = os.getenv("HUAWEI_MAAS_MODEL")
    if not all([api_key, base_url, model]):
        return HldRecommendationResponse(recommended_answer="", source="fallback_default")

    lang_name = {"en": "English", "es": "Spanish", "zh": "Chinese"}.get(language, "English")

    system_msg = (
        f"You are a Huawei Cloud solution architect assistant. "
        f"Given the partial answers from a user, recommend a value for the next question. "
        f"Respond in {lang_name}. Be concise and practical. "
        f"Output ONLY the recommended answer text, nothing else."
    )

    answers_summary = "\n".join(f"- {k}: {v}" for k, v in answers.items() if v)
    step_labels = {
        "project_name": "Project or system name",
        "business_goal": "Primary business goal or scenario",
        "architecture_boundary": "Architecture boundary (Application / Platform / Network / Deployment)",
        "deployment_mode": "Deployment mode (on-prem / cloud / hybrid)",
        "user_access_entry": "How users access the system",
        "core_components": "Core components or services (Huawei Cloud service names preferred)",
        "external_integrations": "External systems or third-party integrations",
        "data_stores_flow": "Data stores and data flow description",
        "network_security_boundary": "Network and security boundary description",
        "preferred_filename": "Output filename (without extension)",
    }
    user_msg = (
        f"Question to answer: {step_labels.get(step, step)}\n\n"
        f"Previous answers:\n{answers_summary or '(none yet)'}\n\n"
        + (
            f"Suggested baseline recommendation:\n{baseline}\n\n"
            "Refine or replace the baseline if the prior answers imply a better answer.\n\n"
            if baseline.strip()
            else ""
        )
        + (
            "Important constraint: for the data_stores_flow step, do not introduce Huawei Cloud services or components "
            "that do not already appear in the user's previous core_components answer. Reuse only the services already mentioned.\n\n"
            if step == "data_stores_flow"
            else ""
        )
        + f"Provide a practical recommendation for: {step_labels.get(step, step)}"
    )

    try:
        client = build_chat_client_from_env()
        result = client.complete_text([
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ])
        if result.strip():
            return HldRecommendationResponse(recommended_answer=result.strip(), source="llm")
        return HldRecommendationResponse(recommended_answer="", source="fallback_default")
    except Exception as exc:
        logger.warning("LLM recommendation failed for step=%s: %s", step, exc)
        return HldRecommendationResponse(recommended_answer="", source="fallback_default")


# ── Public API ──────────────────────────────────────────────────────────

def get_recommendation(request: HldRecommendationRequest) -> HldRecommendationResponse:
    """Get a recommendation for the given wizard step.

    Every step except project_name triggers a recommendation calculation.
    - project_name: returns empty with source="static"
    - Rule-allowed steps: rules produce dynamic answers from prior context
    - Context-driven steps: rules first (using prior answers), LLM fallback
    - Unrecognized steps: source="fallback_default" with warning
    """
    step = request.step

    # Step 1: static only
    if step == "project_name":
        return HldRecommendationResponse(recommended_answer="", source="static")

    # Validate step is known
    if step not in ALL_STEPS:
        logger.warning("Unrecognized recommendation step: %s", step)
        return HldRecommendationResponse(recommended_answer="", source="fallback_default")

    # Build a dynamic rule baseline first.
    rule_result = _rule_recommend(step, request.answers, request.language)
    baseline = rule_result.recommended_answer if rule_result and rule_result.recommended_answer else ""

    # From step 2 onward, always let the LLM refine the recommendation.
    llm_result = _llm_recommend(step, request.answers, request.language, baseline=baseline)
    if llm_result.recommended_answer:
        return llm_result

    # If LLM fails or returns empty, fall back to the dynamic rule result.
    if baseline:
        return rule_result  # type: ignore[return-value]

    # Ultimate fallback
    return HldRecommendationResponse(recommended_answer="", source="fallback_default")
