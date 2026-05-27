import { useState, type FormEvent } from "react";
import { ArrowRight, ArrowLeft, LayoutDashboard, Calculator, ArrowUp, GraduationCap, Shield } from "lucide-react";

type Lang = "es" | "en" | "zh" | "pg";

export type ProposalRequest = {
  project_name: string;
  customer_name?: string | null;
  country?: string | null;
  language: string;
  business_background: string;
  current_pain_points: string;
  target_outcomes: string;
  quote_mode: "skip" | "rvtools" | "flexible";
  // Extended fields — frontend-only for now, mapped on submit
  proposal_title?: string | null;
  proposal_subtitle?: string | null;
  include_hld?: boolean;
  include_price?: boolean;
  include_migration?: boolean;
  include_support_training?: boolean;
  include_huawei_capability?: boolean;
  hld_mode?: "skip" | "create_new";
  price_mode?: "skip" | "create_new";
  migration_scope?: string | null;
  migration_constraints?: string | null;
  migration_notes?: string | null;
};

type WizardStep = "basic" | "context" | "content" | "assets" | "review";

const STEP_ORDER: WizardStep[] = ["basic", "context", "content", "assets", "review"];

const stepCopy: Record<Lang, Record<WizardStep, string>> = {
  en: { basic: "Basic Info", context: "Business Context", content: "Content Selection", assets: "Asset Linking", review: "Review" },
  es: { basic: "Info Básica", context: "Contexto", content: "Contenido", assets: "Activos", review: "Revisión" },
  zh: { basic: "基本信息", context: "业务背景", content: "内容选择", assets: "资产关联", review: "确认" },
  pg: { basic: "Info Básica", context: "Contexto", content: "Conteúdo", assets: "Ativos", review: "Revisão" },
};

const fieldCopy: Record<Lang, Record<string, string>> = {
  en: {
    project_name: "Project Name", customer_name: "Customer Name", country: "Country",
    proposal_title: "Proposal Title", proposal_subtitle: "Proposal Subtitle",
    business_background: "Business Background", current_pain_points: "Current Pain Points",
    target_outcomes: "Target Outcomes",
    include_hld: "Architecture Design (HLD)", include_price: "Pricing & Quote",
    include_migration: "Migration Plan", include_support: "Support & Training",
    include_capability: "Huawei Capabilities",
    hld_desc: "High-level architecture diagram from HLD workflow",
    price_desc: "Cloud pricing estimate from Quote workflow",
    migration_desc: "Migration strategy and wave plan",
    support_desc: "Support tiers and training plan",
    capability_desc: "Huawei Cloud regional capabilities and SLA",
    create_new_hld: "Create new HLD (opens HLD workflow)", skip_hld: "Skip for now",
    create_new_price: "Create new quote (opens Pricing)", skip_price: "Skip for now",
    migration_scope: "Migration Scope", migration_constraints: "Constraints",
    migration_notes: "Additional Notes",
    hld_reuse_hint: "HLD is generated separately via the HLD Design workflow. Select 'Create new' to go there after this proposal.",
    price_reuse_hint: "Pricing is generated separately via the Pricing workflow. Select 'Create new' to go there after this proposal.",
    yes: "Yes", no: "No",
    generate: "Generate Proposal", back: "Back", next: "Next", cancel: "Cancel",
    optional: "(optional)",
  },
  es: {
    project_name: "Nombre del Proyecto", customer_name: "Nombre del Cliente", country: "País",
    proposal_title: "Título de la Propuesta", proposal_subtitle: "Subtítulo",
    business_background: "Contexto del Negocio", current_pain_points: "Pain Points Actuales",
    target_outcomes: "Resultados Esperados",
    include_hld: "Diseño de Arquitectura (HLD)", include_price: "Precios y Cotización",
    include_migration: "Plan de Migración", include_support: "Soporte y Capacitación",
    include_capability: "Capacidades Huawei",
    hld_desc: "Diagrama de arquitectura desde el flujo HLD",
    price_desc: "Estimación de precios desde el flujo de Cotización",
    migration_desc: "Estrategia de migración y plan de oleadas",
    support_desc: "Niveles de soporte y plan de capacitación",
    capability_desc: "Capacidades regionales y SLA de Huawei Cloud",
    create_new_hld: "Crear nuevo HLD (abre flujo HLD)", skip_hld: "Omitir por ahora",
    create_new_price: "Crear nueva cotización (abre Pricing)", skip_price: "Omitir por ahora",
    migration_scope: "Alcance de Migración", migration_constraints: "Restricciones",
    migration_notes: "Notas Adicionales",
    hld_reuse_hint: "El HLD se genera por separado en el flujo HLD Design. Seleccione 'Crear nuevo' para ir allí después de esta propuesta.",
    price_reuse_hint: "Los precios se generan por separado en el flujo de Pricing. Seleccione 'Crear nuevo' para ir allí después de esta propuesta.",
    yes: "Sí", no: "No",
    generate: "Generar Propuesta", back: "Volver", next: "Siguiente", cancel: "Cancelar",
    optional: "(opcional)",
  },
  zh: {
    project_name: "项目名称", customer_name: "客户名称", country: "国家",
    proposal_title: "提案标题", proposal_subtitle: "提案副标题",
    business_background: "业务背景", current_pain_points: "当前痛点",
    target_outcomes: "目标成果",
    include_hld: "架构设计（HLD）", include_price: "报价与定价",
    include_migration: "迁移计划", include_support: "支持与培训",
    include_capability: "华为云能力",
    hld_desc: "来自 HLD 工作流的高层架构图",
    price_desc: "来自报价工作流的云定价估算",
    migration_desc: "迁移策略与波次计划",
    support_desc: "支持等级与培训计划",
    capability_desc: "华为云区域能力与 SLA",
    create_new_hld: "创建新 HLD（打开 HLD 工作流）", skip_hld: "暂时跳过",
    create_new_price: "创建新报价（打开定价）", skip_price: "暂时跳过",
    migration_scope: "迁移范围", migration_constraints: "约束条件",
    migration_notes: "补充说明",
    hld_reuse_hint: "HLD 通过 HLD Design 工作流单独生成。选择'创建新'可在本提案完成后跳转。",
    price_reuse_hint: "定价通过 Pricing 工作流单独生成。选择'创建新'可在本提案完成后跳转。",
    yes: "是", no: "否",
    generate: "生成提案", back: "返回", next: "下一步", cancel: "取消",
    optional: "（可选）",
  },
  pg: {
    project_name: "Nome do Projeto", customer_name: "Nome do Cliente", country: "País",
    proposal_title: "Título da Proposta", proposal_subtitle: "Subtítulo",
    business_background: "Contexto do Negócio", current_pain_points: "Dores Atuais",
    target_outcomes: "Resultados Esperados",
    include_hld: "Design de Arquitetura (HLD)", include_price: "Preços e Cotação",
    include_migration: "Plano de Migração", include_support: "Suporte e Treinamento",
    include_capability: "Capacidades Huawei",
    hld_desc: "Diagrama de arquitetura do fluxo HLD",
    price_desc: "Estimativa de preços do fluxo de Cotação",
    migration_desc: "Estratégia de migração e plano de ondas",
    support_desc: "Níveis de suporte e plano de treinamento",
    capability_desc: "Capacidades regionais e SLA do Huawei Cloud",
    create_new_hld: "Criar novo HLD (abre fluxo HLD)", skip_hld: "Pular por agora",
    create_new_price: "Criar nova cotação (abre Pricing)", skip_price: "Pular por agora",
    migration_scope: "Escopo da Migração", migration_constraints: "Restrições",
    migration_notes: "Notas Adicionais",
    hld_reuse_hint: "O HLD é gerado separadamente pelo fluxo HLD Design. Selecione 'Criar novo' para ir lá após esta proposta.",
    price_reuse_hint: "Os preços são gerados separadamente pelo fluxo de Pricing. Selecione 'Criar novo' para ir lá após esta proposta.",
    yes: "Sim", no: "Não",
    generate: "Gerar Proposta", back: "Voltar", next: "Próximo", cancel: "Cancelar",
    optional: "(opcional)",
  },
};

interface ProposalWizardProps {
  lang: Lang;
  onSubmit: (request: ProposalRequest) => void;
  onCancel: () => void;
}

export function ProposalWizard({ lang, onSubmit, onCancel }: ProposalWizardProps) {
  const [stepIndex, setStepIndex] = useState(0);

  // Basic Info
  const [projectName, setProjectName] = useState("");
  const [customerName, setCustomerName] = useState("");
  const [country, setCountry] = useState("");
  const [proposalTitle, setProposalTitle] = useState("");
  const [proposalSubtitle, setProposalSubtitle] = useState("");

  // Business Context
  const [businessBackground, setBusinessBackground] = useState("");
  const [currentPainPoints, setCurrentPainPoints] = useState("");
  const [targetOutcomes, setTargetOutcomes] = useState("");

  // Content Selection
  const [includeHld, setIncludeHld] = useState(false);
  const [includePrice, setIncludePrice] = useState(false);
  const [includeMigration, setIncludeMigration] = useState(false);
  const [includeSupport, setIncludeSupport] = useState(false);
  const [includeCapability, setIncludeCapability] = useState(true);

  // Asset Linking
  const [hldMode, setHldMode] = useState<"skip" | "create_new">("skip");
  const [priceMode, setPriceMode] = useState<"skip" | "create_new">("skip");
  const [migrationScope, setMigrationScope] = useState("");
  const [migrationConstraints, setMigrationConstraints] = useState("");
  const [migrationNotes, setMigrationNotes] = useState("");

  const step = STEP_ORDER[stepIndex];
  const isFirst = stepIndex === 0;
  const isLast = stepIndex === STEP_ORDER.length - 1;
  const t = fieldCopy[lang];

  function canAdvance(): boolean {
    if (step === "basic") return projectName.trim().length > 0;
    if (step === "context") return businessBackground.trim().length > 0 && currentPainPoints.trim().length > 0 && targetOutcomes.trim().length > 0;
    return true;
  }

  function handleNext() {
    if (!canAdvance()) return;
    if (isLast) {
      const langKey = lang === "zh" ? "en" : lang;
      const req: ProposalRequest = {
        project_name: projectName,
        customer_name: customerName || null,
        country: country || null,
        language: langKey,
        business_background: businessBackground,
        current_pain_points: currentPainPoints,
        target_outcomes: targetOutcomes,
        quote_mode: includePrice ? "flexible" : "skip",
        proposal_title: proposalTitle || null,
        proposal_subtitle: proposalSubtitle || null,
        include_hld: includeHld,
        include_price: includePrice,
        include_migration: includeMigration,
        include_support_training: includeSupport,
        include_huawei_capability: includeCapability,
        hld_mode: includeHld ? hldMode : "skip",
        price_mode: includePrice ? priceMode : "skip",
        migration_scope: migrationScope || null,
        migration_constraints: migrationConstraints || null,
        migration_notes: migrationNotes || null,
      };
      onSubmit(req);
      return;
    }
    setStepIndex((i) => i + 1);
  }

  function handleBack() {
    if (isFirst) { onCancel(); return; }
    setStepIndex((i) => i - 1);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    handleNext();
  }

  const contentModules = [
    { key: "hld", label: t.include_hld, desc: t.hld_desc, icon: LayoutDashboard, checked: includeHld, toggle: () => setIncludeHld(!includeHld) },
    { key: "price", label: t.include_price, desc: t.price_desc, icon: Calculator, checked: includePrice, toggle: () => setIncludePrice(!includePrice) },
    { key: "migration", label: t.include_migration, desc: t.migration_desc, icon: ArrowUp, checked: includeMigration, toggle: () => setIncludeMigration(!includeMigration) },
    { key: "support", label: t.include_support, desc: t.support_desc, icon: GraduationCap, checked: includeSupport, toggle: () => setIncludeSupport(!includeSupport) },
    { key: "capability", label: t.include_capability, desc: t.capability_desc, icon: Shield, checked: includeCapability, toggle: () => setIncludeCapability(!includeCapability) },
  ];

  return (
    <form className="proposal-wizard" onSubmit={handleSubmit}>
      <div className="proposal-wizard-steps">
        {STEP_ORDER.map((s, i) => (
          <span key={s} className={`proposal-step-indicator${i === stepIndex ? " active" : ""}${i < stepIndex ? " done" : ""}`}>
            {i + 1}. {stepCopy[lang][s]}
          </span>
        ))}
      </div>

      <div className="proposal-wizard-body">
        {/* Step 1: Basic Info */}
        {step === "basic" && (
          <div className="proposal-wizard-grid">
            <div className="proposal-field">
              <label>{t.project_name} *</label>
              <input type="text" value={projectName} onChange={(e) => setProjectName(e.target.value)} placeholder="e.g. Cloud Migration Phase 1" />
            </div>
            <div className="proposal-field">
              <label>{t.customer_name}</label>
              <input type="text" value={customerName} onChange={(e) => setCustomerName(e.target.value)} />
            </div>
            <div className="proposal-field">
              <label>{t.country}</label>
              <input type="text" value={country} onChange={(e) => setCountry(e.target.value)} placeholder="e.g. Chile" />
            </div>
            <div className="proposal-field">
              <label>{t.proposal_title} {t.optional}</label>
              <input type="text" value={proposalTitle} onChange={(e) => setProposalTitle(e.target.value)} />
            </div>
            <div className="proposal-field">
              <label>{t.proposal_subtitle} {t.optional}</label>
              <input type="text" value={proposalSubtitle} onChange={(e) => setProposalSubtitle(e.target.value)} />
            </div>
          </div>
        )}

        {/* Step 2: Business Context */}
        {step === "context" && (
          <div className="proposal-wizard-grid">
            <div className="proposal-field full">
              <label>{t.business_background} *</label>
              <textarea value={businessBackground} onChange={(e) => setBusinessBackground(e.target.value)} rows={3} placeholder="e.g. Moving on-prem workloads to Huawei Cloud" />
            </div>
            <div className="proposal-field full">
              <label>{t.current_pain_points} *</label>
              <textarea value={currentPainPoints} onChange={(e) => setCurrentPainPoints(e.target.value)} rows={3} placeholder="e.g. High infrastructure costs, limited scalability" />
            </div>
            <div className="proposal-field full">
              <label>{t.target_outcomes} *</label>
              <textarea value={targetOutcomes} onChange={(e) => setTargetOutcomes(e.target.value)} rows={3} placeholder="e.g. Reduce TCO by 30%, improve availability" />
            </div>
          </div>
        )}

        {/* Step 3: Content Selection */}
        {step === "content" && (
          <div className="proposal-content-selection">
            {contentModules.map((mod) => {
              const Icon = mod.icon;
              return (
                <div
                  key={mod.key}
                  className={`proposal-content-card${mod.checked ? " selected" : ""}`}
                  onClick={mod.toggle}
                >
                  <div className="proposal-content-card-header">
                    <Icon size={20} />
                    <strong>{mod.label}</strong>
                  </div>
                  <p>{mod.desc}</p>
                  <span className="proposal-content-toggle">{mod.checked ? t.yes : t.no}</span>
                </div>
              );
            })}
          </div>
        )}

        {/* Step 4: Asset Linking */}
        {step === "assets" && (
          <div className="proposal-wizard-grid">
            {includeHld && (
              <div className="proposal-field full">
                <label>{t.include_hld}</label>
                <p className="proposal-hint">{t.hld_reuse_hint}</p>
                <div className="proposal-radio-group">
                  <label className="proposal-radio">
                    <input type="radio" name="hld_mode" value="create_new" checked={hldMode === "create_new"} onChange={() => setHldMode("create_new")} />
                    {t.create_new_hld}
                  </label>
                  <label className="proposal-radio">
                    <input type="radio" name="hld_mode" value="skip" checked={hldMode === "skip"} onChange={() => setHldMode("skip")} />
                    {t.skip_hld}
                  </label>
                </div>
              </div>
            )}
            {includePrice && (
              <div className="proposal-field full">
                <label>{t.include_price}</label>
                <p className="proposal-hint">{t.price_reuse_hint}</p>
                <div className="proposal-radio-group">
                  <label className="proposal-radio">
                    <input type="radio" name="price_mode" value="create_new" checked={priceMode === "create_new"} onChange={() => setPriceMode("create_new")} />
                    {t.create_new_price}
                  </label>
                  <label className="proposal-radio">
                    <input type="radio" name="price_mode" value="skip" checked={priceMode === "skip"} onChange={() => setPriceMode("skip")} />
                    {t.skip_price}
                  </label>
                </div>
              </div>
            )}
            {includeMigration && (
              <>
                <div className="proposal-field full"><label>{t.migration_scope}</label><textarea value={migrationScope} onChange={(e) => setMigrationScope(e.target.value)} rows={2} /></div>
                <div className="proposal-field full"><label>{t.migration_constraints}</label><textarea value={migrationConstraints} onChange={(e) => setMigrationConstraints(e.target.value)} rows={2} /></div>
                <div className="proposal-field full"><label>{t.migration_notes}</label><textarea value={migrationNotes} onChange={(e) => setMigrationNotes(e.target.value)} rows={2} /></div>
              </>
            )}
            {!includeHld && !includePrice && !includeMigration && (
              <div className="proposal-empty-note">
                <p>{lang === "zh" ? "未选择任何内容模块，可在上一步勾选。" : lang === "es" ? "No se seleccionaron módulos de contenido. Puede seleccionarlos en el paso anterior." : "No content modules selected. You can select them in the previous step."}</p>
              </div>
            )}
          </div>
        )}

        {/* Step 5: Review */}
        {step === "review" && (
          <div className="proposal-review">
            <div className="proposal-review-row"><strong>{t.project_name}:</strong> {projectName}</div>
            {customerName && <div className="proposal-review-row"><strong>{t.customer_name}:</strong> {customerName}</div>}
            {country && <div className="proposal-review-row"><strong>{t.country}:</strong> {country}</div>}
            {proposalTitle && <div className="proposal-review-row"><strong>{t.proposal_title}:</strong> {proposalTitle}</div>}
            <div className="proposal-review-row"><strong>{t.business_background}:</strong> {businessBackground}</div>
            <div className="proposal-review-row"><strong>{t.current_pain_points}:</strong> {currentPainPoints}</div>
            <div className="proposal-review-row"><strong>{t.target_outcomes}:</strong> {targetOutcomes}</div>
            <div className="proposal-review-chips">
              {includeHld && <span className="proposal-review-chip">{t.include_hld}</span>}
              {includePrice && <span className="proposal-review-chip">{t.include_price}</span>}
              {includeMigration && <span className="proposal-review-chip">{t.include_migration}</span>}
              {includeSupport && <span className="proposal-review-chip">{t.include_support}</span>}
              {includeCapability && <span className="proposal-review-chip">{t.include_capability}</span>}
            </div>
            {includeHld && <div className="proposal-review-row"><strong>HLD:</strong> {hldMode === "create_new" ? t.create_new_hld : t.skip_hld}</div>}
            {includePrice && <div className="proposal-review-row"><strong>Price:</strong> {priceMode === "create_new" ? t.create_new_price : t.skip_price}</div>}
            {includeMigration && migrationScope && <div className="proposal-review-row"><strong>{t.migration_scope}:</strong> {migrationScope}</div>}
          </div>
        )}
      </div>

      <div className="proposal-wizard-nav">
        <button type="button" className="proposal-wizard-back" onClick={handleBack}>
          <ArrowLeft size={16} />
          {isFirst ? t.cancel : t.back}
        </button>
        <button type="submit" className="proposal-wizard-next" disabled={!canAdvance()}>
          {isLast ? t.generate : t.next}
          {!isLast ? <ArrowRight size={16} /> : null}
        </button>
      </div>
    </form>
  );
}
