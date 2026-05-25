import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { ArrowRight, ArrowLeft, Check, X, RefreshCw, LoaderCircle } from "lucide-react";

type Lang = "es" | "en" | "zh" | "pg";
type RecSource = "static" | "rule" | "llm" | "fallback_default";

export type HldRequirements = {
  project_name: string;
  business_goal: string;
  architecture_boundary: string;
  deployment_mode: "on-prem" | "cloud" | "hybrid";
  user_access_entry: string;
  core_components: string;
  external_integrations: string;
  data_stores_flow: string;
  network_security_boundary: string;
  preferred_filename: string;
  language: string;
};

type WizardField = keyof Omit<HldRequirements, "language">;
type WizardStep = WizardField | "summary";

const STEP_ORDER: WizardStep[] = [
  "project_name",
  "business_goal",
  "architecture_boundary",
  "user_access_entry",
  "core_components",
  "external_integrations",
  "data_stores_flow",
  "network_security_boundary",
  "preferred_filename",
  "summary",
];

const API_BASE_URL = (import.meta.env.VITE_QUOTE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "/quote-api";

interface StepMeta {
  question: Record<Lang, string>;
  helper: Record<Lang, string>;
  placeholder: Record<Lang, string>;
}

const stepMeta: Record<WizardStep, StepMeta> = {
  project_name: {
    question: { en: "What is the project or system name?", es: "¿Cuál es el nombre del proyecto?", zh: "项目或系统名称是什么？" , pg: "What is the project or system name?" },
    helper: { en: "A short name to identify this architecture, e.g. 'Customer Portal Migration'", es: "Un nombre corto para identificar esta arquitectura", zh: "用于识别此架构的简短名称" , pg: "A short name to identify this architecture, e.g. 'Customer Portal Migration'" },
    placeholder: { en: "e.g. Cloud Migration Phase 1", es: "ej. Migración Cloud Fase 1", zh: "例如 云迁移第一阶段" , pg: "e.g. Cloud Migration Phase 1" },
  },
  business_goal: {
    question: { en: "What business problem are you solving?", es: "¿Qué problema del negocio busca resolver?", zh: "您要解决什么业务问题？" , pg: "What business problem are you solving?" },
    helper: { en: "Describe the goal in plain language — cost reduction, compliance, performance, new service launch, etc.", es: "Describa el objetivo en lenguaje simple — reducir costos, cumplimiento, rendimiento, etc.", zh: "用通俗语言描述目标 — 降低成本、合规、性能、新服务上线等" , pg: "Describe the goal in plain language — cost reduction, compliance, performance, new service launch, etc." },
    placeholder: { en: "e.g. Reduce infrastructure cost by 30%", es: "ej. Reducir costos de infraestructura en 30%", zh: "例如 降低基础设施成本30%" , pg: "e.g. Reduce infrastructure cost by 30%" },
  },
  architecture_boundary: {
    question: { en: "What parts of the system are in scope?", es: "¿Qué partes del sistema están en alcance?", zh: "系统的哪些部分在范围内？" , pg: "What parts of the system are in scope?" },
    helper: { en: "Which layers are you designing — just the app, or also network and deployment?", es: "¿Qué capas está diseñando — solo la aplicación, o también red y despliegue?", zh: "您在设计哪些层 — 仅应用，还是网络和部署？" , pg: "Which layers are you designing — just the app, or also network and deployment?" },
    placeholder: { en: "e.g. Application / Platform / Network", es: "ej. Aplicación / Plataforma / Red", zh: "例如 应用 / 平台 / 网络" , pg: "e.g. Application / Platform / Network" },
  },
  deployment_mode: {
    question: { en: "", es: "", zh: "" , pg: "" },
    helper: { en: "", es: "", zh: "" , pg: "" },
    placeholder: { en: "", es: "", zh: "" , pg: "" },
  },
  user_access_entry: {
    question: { en: "How do users reach the system?", es: "¿Cómo acceden los usuarios al sistema?", zh: "用户如何访问系统？" , pg: "How do users reach the system?" },
    helper: { en: "Through a web browser? Mobile app? VPN? API calls from partners?", es: "¿Por navegador web? App móvil? VPN? Llamadas API de socios?", zh: "通过浏览器？移动应用？VPN？合作伙伴API调用？" , pg: "Through a web browser? Mobile app? VPN? API calls from partners?" },
    placeholder: { en: "e.g. Web and Mobile via ELB + WAF", es: "ej. Web y Móvil vía ELB + WAF", zh: "例如 通过 ELB + WAF 访问" , pg: "e.g. Web and Mobile via ELB + WAF" },
  },
  core_components: {
    question: { en: "What main services does the system need?", es: "¿Qué servicios principales necesita el sistema?", zh: "系统需要哪些主要服务？" , pg: "What main services does the system need?" },
    helper: { en: "Think about compute, database, storage, load balancing — we'll map them to Huawei Cloud services", es: "Piense en compute, base de datos, almacenamiento, balanceo — los mapearemos a servicios Huawei Cloud", zh: "考虑计算、数据库、存储、负载均衡 — 我们会映射到华为云服务" , pg: "Think about compute, database, storage, load balancing — we'll map them to Huawei Cloud services" },
    placeholder: { en: "e.g. ECS, RDS MySQL, OBS, ELB", es: "ej. ECS, RDS MySQL, OBS, ELB", zh: "例如 ECS, RDS MySQL, OBS, ELB" , pg: "e.g. ECS, RDS MySQL, OBS, ELB" },
  },
  external_integrations: {
    question: { en: "Does the system connect to anything outside?", es: "¿El sistema se conecta con algo externo?", zh: "系统是否连接外部？" , pg: "Does the system connect to anything outside?" },
    helper: { en: "Third-party APIs, on-prem systems, SaaS tools — or 'none' if standalone", es: "APIs de terceros, sistemas on-prem, herramientas SaaS — o 'ninguno' si es independiente", zh: "第三方API、本地系统、SaaS工具 — 独立则填「无」" , pg: "Third-party APIs, on-prem systems, SaaS tools — or 'none' if standalone" },
    placeholder: { en: "e.g. SAP ERP, Office 365", es: "ej. SAP ERP, Office 365", zh: "例如 SAP ERP, Office 365" , pg: "e.g. SAP ERP, Office 365" },
  },
  data_stores_flow: {
    question: { en: "How does data flow through the system?", es: "¿Cómo fluyen los datos en el sistema?", zh: "数据如何在系统中流动？" , pg: "How does data flow through the system?" },
    helper: { en: "Where is data stored? Does it move between services? Any analytics or backup?", es: "¿Dónde se almacenan los datos? ¿Se mueve entre servicios? ¿Hay análisis o respaldo?", zh: "数据存储在哪里？是否在服务间流动？有分析或备份？" , pg: "Where is data stored? Does it move between services? Any analytics or backup?" },
    placeholder: { en: "e.g. App → RDS MySQL; files → OBS; analytics → DLI", es: "ej. App → RDS MySQL; archivos → OBS; análisis → DLI", zh: "例如 应用 → RDS MySQL；文件 → OBS；分析 → DLI" , pg: "e.g. App → RDS MySQL; files → OBS; analytics → DLI" },
  },
  network_security_boundary: {
    question: { en: "How is the network and security set up?", es: "¿Cómo se configura la red y seguridad?", zh: "网络和安全如何配置？" , pg: "How is the network and security set up?" },
    helper: { en: "VPC, subnets, firewalls, VPN — or just accept the recommendation for a standard setup", es: "VPC, subredes, firewalls, VPN — o acepte la recomendación para una configuración estándar", zh: "VPC、子网、防火墙、VPN — 或接受标准配置推荐" , pg: "VPC, subnets, firewalls, VPN — or just accept the recommendation for a standard setup" },
    placeholder: { en: "e.g. VPC + WAF + NAT + VPN", es: "ej. VPC + WAF + NAT + VPN", zh: "例如 VPC + WAF + NAT + VPN" , pg: "e.g. VPC + WAF + NAT + VPN" },
  },
  preferred_filename: {
    question: { en: "What should the output file be named?", es: "¿Cómo nombrar el archivo de salida?", zh: "输出文件名是什么？" , pg: "What should the output file be named?" },
    helper: { en: "Optional — we'll use the project name if you leave this blank", es: "Opcional — usaremos el nombre del proyecto si lo deja en blanco", zh: "可选 — 留空则使用项目名称" , pg: "Optional — we'll use the project name if you leave this blank" },
    placeholder: { en: "e.g. my-project-hld", es: "ej. mi-proyecto-hld", zh: "例如 my-project-hld" , pg: "e.g. my-project-hld" },
  },
  summary: {
    question: { en: "", es: "", zh: "" , pg: "" },
    helper: { en: "", es: "", zh: "" , pg: "" },
    placeholder: { en: "", es: "", zh: "" , pg: "" },
  },
};

const summaryCopy: Record<Lang, { title: string; confirm: string; back: string; optional: string; fromRec: string }> = {
  en: { title: "Review your requirements", confirm: "Generate HLD", back: "Back", optional: "(optional)", fromRec: "recommended" },
  es: { title: "Revise sus requerimientos", confirm: "Generar HLD", back: "Volver", optional: "(opcional)", fromRec: "recomendado" },
  zh: { title: "确认需求", confirm: "生成 HLD", back: "返回", optional: "（可选）", fromRec: "推荐" },
  pg: { title: "Review your requirements", confirm: "Generate HLD", back: "Back", optional: "(optional)", fromRec: "recommended" },
};

const fieldLabels: Record<Lang, Record<WizardField, string>> = {
  en: {
    project_name: "Project Name", business_goal: "Business Goal", architecture_boundary: "Scope",
    deployment_mode: "", user_access_entry: "User Access", core_components: "Core Services",
    external_integrations: "External Connections", data_stores_flow: "Data Flow",
    network_security_boundary: "Network & Security", preferred_filename: "Filename",
  },
  es: {
    project_name: "Nombre del Proyecto", business_goal: "Objetivo", architecture_boundary: "Alcance",
    deployment_mode: "", user_access_entry: "Acceso", core_components: "Servicios Principales",
    external_integrations: "Conexiones Externas", data_stores_flow: "Flujo de Datos",
    network_security_boundary: "Red y Seguridad", preferred_filename: "Archivo",
  },
  zh: {
    project_name: "项目名称", business_goal: "业务目标", architecture_boundary: "范围",
    deployment_mode: "", user_access_entry: "用户访问", core_components: "核心服务",
    external_integrations: "外部连接", data_stores_flow: "数据流",
    network_security_boundary: "网络与安全", preferred_filename: "文件名",
  },
  pg: {
    project_name: "Project Name", business_goal: "Business Goal", architecture_boundary: "Scope",
    deployment_mode: "", user_access_entry: "User Access", core_components: "Core Services",
    external_integrations: "External Connections", data_stores_flow: "Data Flow",
    network_security_boundary: "Network & Security", preferred_filename: "Filename",
  },
};

interface StepState {
  recommended_answer: string;
  source: RecSource;
  user_answer: string;
  accepted_from_recommendation: boolean;
}

interface HldDesignWizardProps {
  lang: Lang;
  onSubmit: (requirements: HldRequirements) => void;
  onCancel: () => void;
  initialRequirements?: HldRequirements | null;
  initialStep?: WizardStep;
}

function isLongTextField(field: WizardField): boolean {
  return !["project_name", "preferred_filename"].includes(field);
}

export function HldDesignWizard({ lang, onSubmit, onCancel, initialRequirements, initialStep }: HldDesignWizardProps) {
  // Compute initial step index — if initialStep is specified, jump there
  const initialStepIndex = initialStep ? STEP_ORDER.indexOf(initialStep) : 0;
  const [stepIndex, setStepIndex] = useState(Math.max(0, initialStepIndex));
  // If initialRequirements provided, pre-populate answers (skip language field)
  const initialAnswers: Record<string, string> = {};
  if (initialRequirements) {
    for (const key of Object.keys(initialRequirements)) {
      if (key !== "language") {
        initialAnswers[key] = (initialRequirements as Record<string, string>)[key];
      }
    }
  }
  const [answers, setAnswers] = useState<Record<string, string>>(initialAnswers);
  const [stepStates, setStepStates] = useState<Record<string, StepState>>({});
  const [currentInput, setCurrentInput] = useState("");
  const [loadingRec, setLoadingRec] = useState(false);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const step = STEP_ORDER[stepIndex];
  const isSummary = step === "summary";
  const isOptional = step === "preferred_filename";
  const isFirst = stepIndex === 0;

  const currentRec = stepStates[step]?.recommended_answer || "";
  const currentSource = stepStates[step]?.source || "fallback_default";

  // Stable snapshot of answers for useEffect dependency — only the values
  // that have been submitted so far, serialized to avoid object identity issues.
  const answersSnapshot = useMemo(() => {
    return JSON.stringify(answers);
  }, [answers]);

  // Static defaults for step 1 (no LLM call)
  const step1Defaults: Record<Lang, string[]> = {
    en: ["SMB Customer Service Portal", "AI Knowledge Assistant for Internal Teams", "Cloud Migration for ERP Workloads"],
    es: ["Portal de Atención al Cliente SMB", "Asistente de Conocimiento AI para Equipos", "Migración Cloud para Cargas ERP"],
    zh: ["SMB 客户服务门户", "AI 知识助手", "ERP 工作负载云迁移"],
    pg: ["SMB Customer Service Portal", "AI Knowledge Assistant for Internal Teams", "Cloud Migration for ERP Workloads"],
  };

  // Fetch recommendation when step changes or when accumulated answers change.
  // This ensures every step (except project_name) re-requests recommendations
  // with the latest context, so recommendations converge as the user progresses.
  useEffect(() => {
    if (isSummary) return;
    if (step === "project_name") {
      // Step 1: use static defaults, no API call
      setStepStates((prev) => ({
        ...prev,
        [step]: {
          ...(prev[step] || { user_answer: "", accepted_from_recommendation: false, source: "static" as RecSource }),
          recommended_answer: "",
          source: "static",
        },
      }));
      // Restore user's previous answer if going back
      const prevAnswer = answers[step];
      if (prevAnswer) {
        setCurrentInput(prevAnswer);
      } else {
        setCurrentInput("");
      }
      return;
    }

    // For steps 2+, check if user already submitted an answer — if going back,
    // restore their answer rather than re-fetching recommendation.
    const prevUserAnswer = answers[step];
    if (prevUserAnswer !== undefined && prevUserAnswer !== "") {
      // User already answered this step — restore their value
      setCurrentInput(prevUserAnswer);
      // Still fetch recommendation in background for the regenerate button
    }

    let cancelled = false;
    setLoadingRec(true);
    const langKey = lang === "zh" ? "en" : lang;
    const currentAnswers = JSON.parse(answersSnapshot);
    fetch(`${API_BASE_URL}/api/hld/designs/recommendations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ step, answers: currentAnswers, language: langKey }),
    })
      .then((r) => r.ok ? r.json() : null)
      .then((data) => {
        if (cancelled) return;
        const rec = data?.recommended_answer || "";
        const source: RecSource = data?.source || "fallback_default";
        console.debug("[HLD Rec]", { step, source, recommended: rec });
        setStepStates((prev) => ({
          ...prev,
          [step]: {
            ...(prev[step] || { user_answer: "", accepted_from_recommendation: false, source: "fallback_default" as RecSource }),
            recommended_answer: rec,
            source,
          },
        }));
        // Only pre-fill input if user hasn't already answered this step
        if (!prevUserAnswer) {
          setCurrentInput(rec);
        }
        setLoadingRec(false);
      })
      .catch(() => {
        if (cancelled) return;
        setLoadingRec(false);
      });
    return () => { cancelled = true; };
  }, [step, lang, answersSnapshot]);

  // Auto-focus input
  useEffect(() => {
    if (!isSummary) {
      inputRef.current?.focus();
    }
  }, [stepIndex, isSummary]);

  // Auto-scroll transcript
  useEffect(() => {
    if (transcriptRef.current) {
      transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
    }
  }, [stepIndex, stepStates]);

  function handleNext() {
    if (isSummary) {
      const req: HldRequirements = {
        project_name: answers.project_name || "",
        business_goal: answers.business_goal || "",
        architecture_boundary: answers.architecture_boundary || "",
        deployment_mode: "cloud",
        user_access_entry: answers.user_access_entry || "",
        core_components: answers.core_components || "",
        external_integrations: answers.external_integrations || "",
        data_stores_flow: answers.data_stores_flow || "",
        network_security_boundary: answers.network_security_boundary || "",
        preferred_filename: answers.preferred_filename || "",
        language: lang === "zh" ? "en" : lang,
      };
      onSubmit(req);
      return;
    }

    let finalValue: string;
    if (!currentInput.trim() && currentRec) {
      // Accept recommendation on empty input
      finalValue = currentRec;
      setStepStates((prev) => ({
        ...prev,
        [step]: { ...(prev[step] || {}), user_answer: finalValue, accepted_from_recommendation: true },
      }));
    } else {
      finalValue = currentInput;
      setStepStates((prev) => ({
        ...prev,
        [step]: { ...(prev[step] || {}), user_answer: finalValue, accepted_from_recommendation: finalValue === currentRec },
      }));
    }

    setAnswers((prev) => ({ ...prev, [step]: finalValue }));
    setCurrentInput("");
    setStepIndex((i) => i + 1);
  }

  function handleBack() {
    if (isFirst) {
      onCancel();
      return;
    }
    setStepIndex((i) => i - 1);
    // Don't clear currentInput — the useEffect will restore the user's answer
  }

  function handleRegenerate() {
    setLoadingRec(true);
    const langKey = lang === "zh" ? "en" : lang;
    fetch(`${API_BASE_URL}/api/hld/designs/recommendations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ step, answers, language: langKey }),
    })
      .then((r) => r.ok ? r.json() : null)
      .then((data) => {
        const rec = data?.recommended_answer || "";
        const source: RecSource = data?.source || "fallback_default";
        console.debug("[HLD Rec] regenerate", { step, source, recommended: rec });
        setStepStates((prev) => ({
          ...prev,
          [step]: {
            ...(prev[step] || { user_answer: "", accepted_from_recommendation: false, source: "fallback_default" as RecSource }),
            recommended_answer: rec,
            source,
          },
        }));
        setCurrentInput(rec);
        setLoadingRec(false);
      })
      .catch(() => setLoadingRec(false));
  }

  function canAdvance(): boolean {
    if (isSummary) return true;
    if (isOptional) return true;
    if (!currentInput.trim() && currentRec) return true;
    return currentInput.trim().length > 0;
  }

  const answeredSteps = STEP_ORDER.slice(0, stepIndex).filter((s) => s !== "summary");

  // Source label for debug display
  const sourceLabel: Record<RecSource, Record<Lang, string>> = {
    static: { en: "static", es: "estático", zh: "静态" , pg: "static" },
    rule: { en: "rule", es: "regla", zh: "规则" , pg: "rule" },
    llm: { en: "AI", es: "IA", zh: "AI" , pg: "AI" },
    fallback_default: { en: "default", es: "predeterminado", zh: "默认" , pg: "default" },
  };

  return (
    <div className="hld-wizard">
      <div className="hld-wizard-transcript" ref={transcriptRef}>
        {answeredSteps.map((s) => {
          const meta = stepMeta[s as WizardStep];
          const q = meta.question[lang];
          const a = answers[s] || "";
          const fromRec = stepStates[s]?.accepted_from_recommendation;
          return (
            <div className="hld-wizard-step" key={s}>
              <div className="hld-wizard-question">{q}</div>
              <div className="hld-wizard-answer">
                {a}
                {fromRec ? <span className="hld-wizard-rec-badge">{summaryCopy[lang].fromRec}</span> : null}
              </div>
            </div>
          );
        })}

        {!isSummary && (
          <div className="hld-wizard-step hld-wizard-step-active">
            <div className="hld-wizard-question">{stepMeta[step].question[lang]}</div>
            <div className="hld-wizard-helper">{stepMeta[step].helper[lang]}</div>

            {step === "project_name" ? (
              <div className="hld-wizard-input-area">
                <div className="hld-wizard-examples">
                  {step1Defaults[lang].map((ex) => (
                    <button key={ex} type="button" className="hld-wizard-example-chip" onClick={() => setCurrentInput(ex)}>
                      {ex}
                    </button>
                  ))}
                </div>
                <div className="hld-wizard-input-bar">
                  <input
                    ref={inputRef}
                    type="text"
                    value={currentInput}
                    onChange={(e) => setCurrentInput(e.target.value)}
                    placeholder={stepMeta[step].placeholder[lang]}
                    onKeyDown={(e) => { if (e.key === "Enter" && canAdvance()) handleNext(); }}
                  />
                </div>
              </div>
            ) : (
              <div className="hld-wizard-input-area">
                {loadingRec ? (
                  <div className="hld-wizard-rec-loading">
                    <LoaderCircle size={14} className="spin-icon" />
                  </div>
                ) : currentRec ? (
                  <div className="hld-wizard-rec-hint">
                    <span className="hld-wizard-rec-label">
                      {sourceLabel[currentSource][lang]}:
                    </span> {currentRec}
                    <button type="button" className="hld-wizard-regen" onClick={handleRegenerate} title="Regenerate suggestion">
                      <RefreshCw size={13} />
                    </button>
                  </div>
                ) : null}
                <div className="hld-wizard-input-bar">
                  <input
                    ref={inputRef}
                    type="text"
                    value={currentInput}
                    onChange={(e) => setCurrentInput(e.target.value)}
                    placeholder={currentRec || stepMeta[step].placeholder[lang]}
                    onKeyDown={(e) => { if (e.key === "Enter" && canAdvance()) handleNext(); }}
                  />
                </div>
              </div>
            )}
          </div>
        )}

        {isSummary && (
          <div className="hld-wizard-summary">
            <h3>{summaryCopy[lang].title}</h3>
            {STEP_ORDER.filter((s) => s !== "summary").map((s) => {
              const field = s as WizardField;
              const label = fieldLabels[lang][field];
              const value = answers[s] || "";
              const optional = s === "preferred_filename" ? ` ${summaryCopy[lang].optional}` : "";
              const fromRec = stepStates[s]?.accepted_from_recommendation;
              const fieldId = `hld-summary-${field}`;
              return (
                <div className="hld-wizard-summary-row" key={s}>
                  <label className="hld-wizard-summary-label" htmlFor={fieldId}>
                    {label}{optional}
                    {fromRec ? <span className="hld-wizard-rec-badge">{summaryCopy[lang].fromRec}</span> : null}
                  </label>
                  <div className="hld-wizard-summary-control">
                    {isLongTextField(field) ? (
                      <textarea
                        id={fieldId}
                        className="hld-wizard-summary-input hld-wizard-summary-textarea"
                        value={value}
                        placeholder={stepMeta[field].placeholder[lang]}
                        rows={field === "core_components" || field === "data_stores_flow" ? 3 : 2}
                        onChange={(e) => setAnswers((prev) => ({ ...prev, [field]: e.target.value }))}
                      />
                    ) : (
                      <input
                        id={fieldId}
                        type="text"
                        className="hld-wizard-summary-input"
                        value={value}
                        placeholder={stepMeta[field].placeholder[lang]}
                        onChange={(e) => setAnswers((prev) => ({ ...prev, [field]: e.target.value }))}
                      />
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="hld-wizard-nav">
        <button type="button" className="hld-wizard-back" onClick={handleBack}>
          <ArrowLeft size={16} />
          {isFirst ? <X size={16} /> : null}
          {isFirst ? "" : summaryCopy[lang].back}
        </button>
        <button
          type="button"
          className="hld-wizard-next"
          onClick={handleNext}
          disabled={!canAdvance()}
        >
          {isSummary ? summaryCopy[lang].confirm : <ArrowRight size={16} />}
        </button>
      </div>
    </div>
  );
}
