import { useState, type FormEvent } from "react";
import { Calculator, GraduationCap, LayoutDashboard, Shield, Sparkles, ArrowUp } from "lucide-react";

type Lang = "es" | "en" | "zh" | "pg";

export type ProposalRequest = {
  project_name: string;
  customer_name?: string | null;
  country?: string | null;
  language: string;
  customer_brief: string;
  business_background?: string;
  current_pain_points?: string;
  target_outcomes?: string;
  quote_mode: "skip" | "rvtools" | "flexible";
  include_hld?: boolean;
  include_price?: boolean;
  include_migration?: boolean;
  include_support_training?: boolean;
  include_huawei_capability?: boolean;
  hld_mode?: "skip" | "create_new";
  price_mode?: "skip" | "create_new";
};

const copy = {
  en: {
    heading: "Create a proposal draft",
    intro: "Provide a short customer brief. AI will structure the business context, challenges, outcomes, and recommended solution.",
    projectName: "Project Name",
    customerName: "Customer Name",
    country: "Country",
    customerBrief: "Customer Brief",
    briefHint: "Describe the current environment, key challenges, business goals, and expected solution. Missing details will be listed as assumptions.",
    briefPlaceholder: "Example: The customer operates an on-premises ERP platform and wants to improve availability, reduce infrastructure operations, and migrate to Huawei Cloud in phases.",
    advanced: "Advanced Options",
    advancedHint: "Optional sections to include in the proposal. These options do not start separate HLD or pricing workflows.",
    includeHld: "Architecture Recommendations",
    includePrice: "Pricing Summary",
    includeMigration: "Migration Plan",
    includeSupport: "Support & Training",
    includeCapability: "Huawei Cloud Capabilities",
    hldDesc: "Include high-level architecture recommendations without creating a separate HLD.",
    priceDesc: "Include pricing context only when verified pricing information is available.",
    migrationDesc: "Include a concise migration approach.",
    supportDesc: "Include recommended support and enablement.",
    capabilityDesc: "Include relevant Huawei Cloud regional capabilities.",
    generate: "Generate Proposal",
    cancel: "Cancel",
    required: "Required",
    optional: "Optional",
  },
  es: {
    heading: "Crear borrador de propuesta",
    intro: "Proporcione un breve contexto del cliente. La IA estructurará el contexto, los desafíos, los objetivos y la solución recomendada.",
    projectName: "Nombre del Proyecto",
    customerName: "Nombre del Cliente",
    country: "País",
    customerBrief: "Resumen del Cliente",
    briefHint: "Describa el entorno actual, los principales desafíos, los objetivos de negocio y la solución esperada. Los datos faltantes se indicarán como supuestos.",
    briefPlaceholder: "Ejemplo: El cliente opera un ERP on-premises y busca mejorar la disponibilidad, reducir la operación de infraestructura y migrar a Huawei Cloud por fases.",
    advanced: "Opciones Avanzadas",
    advancedHint: "Secciones opcionales de la propuesta. Estas opciones no inician flujos separados de HLD o cotización.",
    includeHld: "Recomendaciones de Arquitectura",
    includePrice: "Resumen de Precios",
    includeMigration: "Plan de Migración",
    includeSupport: "Soporte y Capacitación",
    includeCapability: "Capacidades de Huawei Cloud",
    hldDesc: "Incluye recomendaciones de alto nivel sin crear un HLD separado.",
    priceDesc: "Incluye contexto de precios solo cuando exista información verificada.",
    migrationDesc: "Incluye un enfoque de migración conciso.",
    supportDesc: "Incluye recomendaciones de soporte y habilitación.",
    capabilityDesc: "Incluye capacidades regionales relevantes de Huawei Cloud.",
    generate: "Generar Propuesta",
    cancel: "Cancelar",
    required: "Obligatorio",
    optional: "Opcional",
  },
  zh: {
    heading: "生成方案建议书初稿",
    intro: "提供一段客户基本情况，AI 将自动整理业务背景、当前挑战、目标和推荐方案。",
    projectName: "项目名称",
    customerName: "客户名称",
    country: "国家",
    customerBrief: "客户需求描述",
    briefHint: "描述客户现有环境、主要挑战、业务目标和期望方案。缺失信息将标记为假设，不会阻止生成。",
    briefPlaceholder: "示例：客户当前在本地运行 ERP，希望提升可用性、降低基础设施运维工作量，并分阶段迁移到华为云。",
    advanced: "高级选项",
    advancedHint: "选择需要包含的可选章节。这些选项不会启动独立的 HLD 或报价流程。",
    includeHld: "架构建议",
    includePrice: "价格摘要",
    includeMigration: "迁移计划",
    includeSupport: "支持与培训",
    includeCapability: "华为云能力",
    hldDesc: "提供高层架构建议，但不创建独立 HLD。",
    priceDesc: "仅在存在已验证价格信息时包含价格说明。",
    migrationDesc: "包含简洁的迁移实施建议。",
    supportDesc: "包含支持和能力提升建议。",
    capabilityDesc: "包含相关的华为云区域能力。",
    generate: "生成建议书",
    cancel: "取消",
    required: "必填",
    optional: "可选",
  },
  pg: {
    heading: "Criar rascunho da proposta",
    intro: "Forneça um breve contexto do cliente. A IA organizará o contexto, desafios, objetivos e solução recomendada.",
    projectName: "Nome do Projeto",
    customerName: "Nome do Cliente",
    country: "País",
    customerBrief: "Resumo do Cliente",
    briefHint: "Descreva o ambiente atual, desafios, objetivos e solução esperada. Informações ausentes serão registradas como premissas.",
    briefPlaceholder: "Exemplo: O cliente opera um ERP on-premises e deseja melhorar a disponibilidade e migrar para a Huawei Cloud em fases.",
    advanced: "Opções Avançadas",
    advancedHint: "Seções opcionais da proposta. Estas opções não iniciam fluxos separados de HLD ou cotação.",
    includeHld: "Recomendações de Arquitetura",
    includePrice: "Resumo de Preços",
    includeMigration: "Plano de Migração",
    includeSupport: "Suporte e Treinamento",
    includeCapability: "Capacidades da Huawei Cloud",
    hldDesc: "Inclui recomendações de alto nível sem criar um HLD separado.",
    priceDesc: "Inclui preços somente quando houver informações verificadas.",
    migrationDesc: "Inclui uma abordagem concisa de migração.",
    supportDesc: "Inclui recomendações de suporte e capacitação.",
    capabilityDesc: "Inclui capacidades regionais relevantes da Huawei Cloud.",
    generate: "Gerar Proposta",
    cancel: "Cancelar",
    required: "Obrigatório",
    optional: "Opcional",
  },
} satisfies Record<Lang, Record<string, string>>;

interface ProposalWizardProps {
  lang: Lang;
  onSubmit: (request: ProposalRequest) => void;
  onCancel: () => void;
}

export function ProposalWizard({ lang, onSubmit, onCancel }: ProposalWizardProps) {
  const [projectName, setProjectName] = useState("");
  const [customerName, setCustomerName] = useState("");
  const [country, setCountry] = useState("");
  const [customerBrief, setCustomerBrief] = useState("");
  const [includeHld, setIncludeHld] = useState(false);
  const [includePrice, setIncludePrice] = useState(false);
  const [includeMigration, setIncludeMigration] = useState(false);
  const [includeSupport, setIncludeSupport] = useState(false);
  const [includeCapability, setIncludeCapability] = useState(true);
  const t = copy[lang];
  const canSubmit = projectName.trim().length > 0 && customerBrief.trim().length > 0;

  const contentModules = [
    { key: "hld", label: t.includeHld, desc: t.hldDesc, icon: LayoutDashboard, checked: includeHld, toggle: () => setIncludeHld((value) => !value) },
    { key: "price", label: t.includePrice, desc: t.priceDesc, icon: Calculator, checked: includePrice, toggle: () => setIncludePrice((value) => !value) },
    { key: "migration", label: t.includeMigration, desc: t.migrationDesc, icon: ArrowUp, checked: includeMigration, toggle: () => setIncludeMigration((value) => !value) },
    { key: "support", label: t.includeSupport, desc: t.supportDesc, icon: GraduationCap, checked: includeSupport, toggle: () => setIncludeSupport((value) => !value) },
    { key: "capability", label: t.includeCapability, desc: t.capabilityDesc, icon: Shield, checked: includeCapability, toggle: () => setIncludeCapability((value) => !value) },
  ];

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    onSubmit({
      project_name: projectName.trim(),
      customer_name: customerName.trim() || null,
      country: country.trim() || null,
      language: lang === "pg" ? "es" : lang,
      customer_brief: customerBrief.trim(),
      business_background: "",
      current_pain_points: "",
      target_outcomes: "",
      quote_mode: "skip",
      include_hld: includeHld,
      include_price: includePrice,
      include_migration: includeMigration,
      include_support_training: includeSupport,
      include_huawei_capability: includeCapability,
      hld_mode: "skip",
      price_mode: "skip",
    });
  }

  return (
    <form className="proposal-wizard proposal-wizard-simple" onSubmit={handleSubmit}>
      <div className="proposal-wizard-heading">
        <span className="proposal-wizard-icon"><Sparkles size={18} /></span>
        <div>
          <h3>{t.heading}</h3>
          <p>{t.intro}</p>
        </div>
      </div>

      <div className="proposal-wizard-grid">
        <div className="proposal-field">
          <label>{t.projectName} <span>{t.required}</span></label>
          <input type="text" value={projectName} onChange={(event) => setProjectName(event.target.value)} />
        </div>
        <div className="proposal-field">
          <label>{t.customerName} <span>{t.optional}</span></label>
          <input type="text" value={customerName} onChange={(event) => setCustomerName(event.target.value)} />
        </div>
        <div className="proposal-field">
          <label>{t.country} <span>{t.optional}</span></label>
          <input type="text" value={country} onChange={(event) => setCountry(event.target.value)} />
        </div>
        <div className="proposal-field full">
          <label>{t.customerBrief} <span>{t.required}</span></label>
          <p className="proposal-hint">{t.briefHint}</p>
          <textarea
            value={customerBrief}
            onChange={(event) => setCustomerBrief(event.target.value)}
            rows={7}
            placeholder={t.briefPlaceholder}
          />
        </div>
      </div>

      <details className="proposal-advanced">
        <summary>{t.advanced}</summary>
        <p>{t.advancedHint}</p>
        <div className="proposal-content-selection">
          {contentModules.map((module) => {
            const Icon = module.icon;
            return (
              <button
                type="button"
                key={module.key}
                className={`proposal-content-card${module.checked ? " selected" : ""}`}
                onClick={module.toggle}
                aria-pressed={module.checked}
              >
                <span className="proposal-content-card-header">
                  <Icon size={20} />
                  <strong>{module.label}</strong>
                </span>
                <span className="proposal-content-card-description">{module.desc}</span>
                <span className="proposal-content-toggle">{module.checked ? "ON" : "OFF"}</span>
              </button>
            );
          })}
        </div>
      </details>

      <div className="proposal-wizard-nav">
        <button type="button" className="proposal-wizard-back" onClick={onCancel}>{t.cancel}</button>
        <button type="submit" className="proposal-wizard-next" disabled={!canSubmit}>
          <Sparkles size={16} />
          {t.generate}
        </button>
      </div>
    </form>
  );
}
