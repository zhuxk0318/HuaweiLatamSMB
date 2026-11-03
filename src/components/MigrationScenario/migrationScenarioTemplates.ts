import {
  solutionScenarioMap,
  textFor,
  type LocalizedPair,
  type QuickIntegration,
  type SolutionScenario,
} from "../../data/solutions";

export type MigrationResourceStatus = "available" | "coming-soon";

export type MigrationResourceType =
  | "ppt"
  | "demo"
  | "skill"
  | "lab-guide"
  | "faq"
  | "architecture"
  | "checklist"
  | "video";

export type MigrationResource = {
  resourceType: MigrationResourceType;
  title: LocalizedPair;
  description: LocalizedPair;
  buttonText: LocalizedPair;
  status: MigrationResourceStatus;
  link?: string;
};

export type RelatedMigrationScenario = {
  scenarioId: string;
  title: LocalizedPair;
  href: string;
};

export type MigrationScenarioFaqItem = {
  question: LocalizedPair;
  result?: LocalizedPair;
};

export type SkillCloneCommand = {
  comment: string;
  command: string;
};

export type SkillToolSection = {
  toolName: string;
  installPath: string;
  commands: SkillCloneCommand[];
};

export type SkillCloneInfo = {
  folderName: string;
  generalCommands: SkillCloneCommand[];
  toolSections: SkillToolSection[];
};

export type MigrationScenarioTemplateConfig = {
  scenarioId: string;
  hero: {
    title: LocalizedPair;
    description: LocalizedPair;
    image: string;
    cta: MigrationResource;
  };
  solutionResources: MigrationResource[];
  skillResources: MigrationResource[];
  howToStart: QuickIntegration;
  faq?: {
    title: LocalizedPair;
    subtitle: LocalizedPair;
    contactLink: string;
    items: MigrationScenarioFaqItem[];
  };
  relatedScenarios: RelatedMigrationScenario[];
  contactInfo: {
    title: LocalizedPair;
    description: LocalizedPair;
    buttonText: LocalizedPair;
    link: string;
  };
  demoVideoEmbedUrl?: string;
  skillZipUrl?: string;
  skillZipLabel?: string;
  skillRepoUrl?: string;
  skillCloneInfo?: SkillCloneInfo;
  skillCloneInfoLabelType?: "skill" | "wsl-install";
  skillGuideUrl?: string;
  skillGuideLabel?: string;
  recommendedServices?: string[];
  detailedLayout?: boolean;
};

const copy = {
  viewPpt: {
    en: "View PPT",
    es: "Ver PPT",
    zh: "查看 PPT",
  },
  comingSoon: {
    en: "Coming Soon",
    es: "Próximamente",
    zh: "即将上线",
  },
  tryAiSkill: {
    en: "Try AI Skill",
    es: "Probar AI Skill",
    zh: "试用 AI Skill",
  },
  watchDemo: {
    en: "Watch Demo",
    es: "Ver demo",
    zh: "观看 Demo",
  },
};

const VIRTUAL_MACHINE_DEMO_VIDEO_URL = "https://www.youtube.com/watch?v=XYDBv9RNXHI";

const supportedScenarioIds = new Set([
  "cloud-to-cloud-migration",
  "database-migration",
  "container-migration",
  "workspace-migration",
  "postgresql-ecs-to-rds-drs",
  "ai-coding-opencode",
  "ai-coding-hermes",
  "ai-coding-claude-code",
  "cloud-foundation",
  "landing-zone",
  "image-discovery",
  "object-migration",
  "vmware-migration",
  "vm-migration",
  "codearts-deployment",
  "mrs-deployment",
  "mrs-migration",
  "other-scenarios",
  "cbr-backup-restore",
  "sdrs-cross-region-dr",
  "dws-cluster-deployment",
  "snowflake-to-dataarts",
  "database-usage-operations",
  "docker-compose-to-cci",
  "vpn-connectivity",
]);

const defaultRelatedScenarioIds = [
  "cloud-to-cloud-migration",
  "database-migration",
  "container-migration",
  "workspace-migration",
  "object-migration",
  "vmware-migration",
  "vm-migration",
  "codearts-deployment",
  "mrs-deployment",
  "cloud-foundation",
  "ai-coding-opencode",
  "ai-coding-hermes",
  "ai-coding-claude-code",
  "other-scenarios",
  "vpn-connectivity",
];

const faqScenarioIds = new Set([
  "database-migration",
  "container-migration",
  "workspace-migration",
  "ai-coding-opencode",
  "ai-coding-hermes",
  "ai-coding-claude-code",
  "cloud-foundation",
  "object-migration",
  "vmware-migration",
  "cloud-to-cloud-migration",
  "vm-migration",
  "codearts-deployment",
  "mrs-deployment",
  "other-scenarios",
  "vpn-connectivity",
]);

function getPresentationUrl(scenario: SolutionScenario) {
  const noPdfYet = new Set([
    "database-usage-operations",
  ]);

  if (noPdfYet.has(scenario.id)) {
    return undefined;
  }

  if (scenario.presentationUrl) {
    return scenario.presentationUrl;
  }

  if (scenario.id === "cloud-to-cloud-migration") {
    return "/presentations/demo-migration.pdf";
  }

  return undefined;
}

function getSolutionResource(scenario: SolutionScenario): MigrationResource {
  const presentationUrl = getPresentationUrl(scenario);

  return {
    resourceType: "ppt",
    title: {
      en: scenario.id === "cloud-to-cloud-migration"
        ? "Huawei Cloud Migration Solution PPT"
        : `${scenario.title.en} Solution PPT`,
      es: scenario.id === "cloud-to-cloud-migration"
        ? "PPT de solución de migración de Huawei Cloud"
        : `PPT de solución - ${scenario.title.es}`,
      zh: scenario.id === "cloud-to-cloud-migration"
        ? "华为云迁移解决方案 PPT"
        : `${scenario.title.zh ?? scenario.title.en} 解决方案 PPT`,
    },
    description: {
      en: scenario.id === "cloud-to-cloud-migration"
        ? "AWS → Huawei Cloud"
        : `Migration solution for ${scenario.title.en}`,
      es: scenario.id === "cloud-to-cloud-migration"
        ? "AWS → Huawei Cloud"
        : `Solución de migración para ${scenario.title.es}`,
      zh: scenario.id === "cloud-to-cloud-migration"
        ? "AWS → 华为云"
        : `${scenario.title.zh ?? scenario.title.en} 迁移解决方案`,
    },
    buttonText: copy.viewPpt,
    status: presentationUrl ? "available" : "coming-soon",
    link: presentationUrl,
  };
}

function getRelatedScenarios(scenario: SolutionScenario): RelatedMigrationScenario[] {
  return defaultRelatedScenarioIds
    .filter((scenarioId) => scenarioId !== scenario.id)
    .map((scenarioId) => solutionScenarioMap[scenarioId])
    .filter((item): item is SolutionScenario => Boolean(item))
    .slice(0, 3)
    .map((item) => ({
      scenarioId: item.id,
      title: item.title,
      href: `#/solutions/${item.id}?from=migration`,
    }));
}

function getFaq(scenario: SolutionScenario): MigrationScenarioTemplateConfig["faq"] {
  if (!faqScenarioIds.has(scenario.id)) {
    return undefined;
  }

  const items = scenario.salesTalkTrack
    .map((question, index) => ({
      question,
      result: scenario.expectedOutcomes[index],
    }))
    .filter((item) => Boolean(item.question && item.result));

  if (!items.length) {
    return undefined;
  }

  return {
    title: {
      en: "Frequently Asked Questions",
      es: "Preguntas frecuentes",
      zh: "FAQ",
    },
    subtitle: {
      en: "Find answers to the most common questions about this migration scenario.",
      es: "Encuentre respuestas a las preguntas más comunes sobre este escenario de migración.",
      zh: "快速查看当前迁移场景中最常见的问题与答案。",
    },
    contactLink: "https://www.huaweicloud.com/intl/en-us/contact-sales.html",
    items,
  };
}

function getDemoResource(scenario: SolutionScenario): MigrationResource {
  const hasDemoVideo = scenario.id === "vmware-migration";

  return {
    resourceType: "demo",
    title: {
      en: "Demo Video",
      es: "Video demo",
      zh: "Demo 视频",
    },
    description: hasDemoVideo
      ? {
          en: "Watch the virtual machine migration demo walkthrough.",
          es: "Vea la demostración de migración de máquinas virtuales.",
          zh: "观看虚拟机迁移 Demo 演示。",
        }
      : {
          en: "A short walkthrough will be added after the recording is ready.",
          es: "Se agregará una guía breve cuando la grabación esté lista.",
          zh: "录制完成后会补充简短演示视频。",
        },
    buttonText: hasDemoVideo ? copy.watchDemo : copy.comingSoon,
    status: hasDemoVideo ? "available" : "coming-soon",
    link: hasDemoVideo ? VIRTUAL_MACHINE_DEMO_VIDEO_URL : undefined,
  };
}

const scenarioSkillInfo: Record<string, {
  zipUrl: string;
  zipLabel: string;
  repoUrl: string;
  cloneInfo: SkillCloneInfo;
  guideUrl?: string;
  guideLabel?: string;
  cloneInfoLabelType?: "skill" | "wsl-install";
}> = {
  "vmware-migration": {
    zipUrl: "/skills/vmware-migration.zip",
    zipLabel: "VMware Migration Skill",
    repoUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Datacenter-on-premise-migration/Vmware-Migration",
    guideUrl: "/guides/vmware-migration-guide.docx",
    guideLabel: "VMware Migration Guide",
    cloneInfo: {
      folderName: "Vmware-Migration",
      generalCommands: [
        { comment: "Clone the repository", command: "git clone https://github.com/binrogithub/1-3-Cloud-Adoption-Skills.git" },
      ],
      toolSections: [
        { toolName: "OpenCode", installPath: "~/.opencode/skills/", commands: [
          { comment: "Copy the skill to OpenCode", command: "find 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Datacenter-on-premise-migration/Vmware-Migration -name SKILL.md -exec dirname {} \\; | while read d; do cp -r \"$d\" ~/.opencode/skills/; done" },
        ] },
        { toolName: "Hermes", installPath: "~/.hermes/skills/", commands: [
          { comment: "Copy the skill to Hermes", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Datacenter-on-premise-migration/Vmware-Migration ~/.hermes/skills/" },
        ] },
        { toolName: "Claude Code", installPath: "~/.claude/skills/", commands: [
          { comment: "Copy the skill to Claude Code", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Datacenter-on-premise-migration/Vmware-Migration ~/.claude/skills/" },
        ] },
      ],
    } as SkillCloneInfo,
  },
  "cloud-to-cloud-migration": {
    zipUrl: "/skills/cloud-to-cloud-migration.zip",
    zipLabel: "Cloud to Cloud Migration Skill",
    guideUrl: "/guides/cloud-to-cloud-migration-guide.pdf",
    guideLabel: "AWS to Huawei Cloud Migration Guide",
    repoUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-to-Cloud-Migration-Examples",
    cloneInfo: {
      folderName: "Cloud-to-Cloud-Migration-Examples",
      generalCommands: [
        { comment: "Clone the repository", command: "git clone https://github.com/binrogithub/1-3-Cloud-Adoption-Skills.git" },
      ],
      toolSections: [
        { toolName: "OpenCode", installPath: "~/.opencode/skills/", commands: [
          { comment: "Copy the skill to OpenCode", command: "find 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Cloud-to-Cloud-Migration-Examples -name SKILL.md -exec dirname {} \\; | while read d; do cp -r \"$d\" ~/.opencode/skills/; done" },
        ] },
        { toolName: "Hermes", installPath: "~/.hermes/skills/", commands: [
          { comment: "Copy the skill to Hermes", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Cloud-to-Cloud-Migration-Examples ~/.hermes/skills/" },
        ] },
        { toolName: "Claude Code", installPath: "~/.claude/skills/", commands: [
          { comment: "Copy the skill to Claude Code", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Cloud-to-Cloud-Migration-Examples ~/.claude/skills/" },
        ] },
      ],
    } as SkillCloneInfo,
  },
  "database-migration": {
    zipUrl: "/skills/database-migration.zip",
    zipLabel: "Database Migration Skill",
    guideUrl: "/guides/database-migration-guide.docx",
    guideLabel: "Database Migration (DRS) Guide",
    repoUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration",
    cloneInfo: {
      folderName: "Database-Migration",
      generalCommands: [
        { comment: "Clone the repository", command: "git clone https://github.com/binrogithub/1-3-Cloud-Adoption-Skills.git" },
      ],
      toolSections: [
        { toolName: "OpenCode", installPath: "~/.opencode/skills/", commands: [
          { comment: "Copy the skill to OpenCode", command: "find 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Database-Migration -name SKILL.md -exec dirname {} \\; | while read d; do cp -r \"$d\" ~/.opencode/skills/; done" },
        ] },
        { toolName: "Hermes", installPath: "~/.hermes/skills/", commands: [
          { comment: "Copy the skill to Hermes", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Database-Migration ~/.hermes/skills/" },
        ] },
        { toolName: "Claude Code", installPath: "~/.claude/skills/", commands: [
          { comment: "Copy the skill to Claude Code", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Database-Migration ~/.claude/skills/" },
        ] },
      ],
    } as SkillCloneInfo,
  },
  "container-migration": {
    zipUrl: "/skills/container-migration.zip",
    zipLabel: "Container Migration Skill",
    guideUrl: "/guides/container-migration-kind-to-cce.docx",
    guideLabel: "Kind to CCE Migration Guide",
    repoUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Container-Migration",
    cloneInfo: {
      folderName: "Container-Migration",
      generalCommands: [
        { comment: "Clone the repository", command: "git clone https://github.com/binrogithub/1-3-Cloud-Adoption-Skills.git" },
      ],
      toolSections: [
        { toolName: "OpenCode", installPath: "~/.opencode/skills/", commands: [
          { comment: "Copy the skill to OpenCode", command: "find 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Container-Migration -name SKILL.md -exec dirname {} \\; | while read d; do cp -r \"$d\" ~/.opencode/skills/; done" },
        ] },
        { toolName: "Hermes", installPath: "~/.hermes/skills/", commands: [
          { comment: "Copy the skill to Hermes", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Container-Migration ~/.hermes/skills/" },
        ] },
        { toolName: "Claude Code", installPath: "~/.claude/skills/", commands: [
          { comment: "Copy the skill to Claude Code", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Container-Migration ~/.claude/skills/" },
        ] },
      ],
    } as SkillCloneInfo,
  },
  "workspace-migration": {
    zipUrl: "/skills/workspace-migration.zip",
    zipLabel: "Workspace Migration Skill",
    guideUrl: "/guides/workspace-migration-guide.docx",
    guideLabel: "VDI to Workspace Migration Guide",
    repoUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Workspace-Migration",
    cloneInfo: {
      folderName: "Workspace-Migration",
      generalCommands: [
        { comment: "Clone the repository", command: "git clone https://github.com/binrogithub/1-3-Cloud-Adoption-Skills.git" },
      ],
      toolSections: [
        { toolName: "OpenCode", installPath: "~/.opencode/skills/", commands: [
          { comment: "Copy the skill to OpenCode", command: "find 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Workspace-Migration -name SKILL.md -exec dirname {} \\; | while read d; do cp -r \"$d\" ~/.opencode/skills/; done" },
        ] },
        { toolName: "Hermes", installPath: "~/.hermes/skills/", commands: [
          { comment: "Copy the skill to Hermes", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Workspace-Migration ~/.hermes/skills/" },
        ] },
        { toolName: "Claude Code", installPath: "~/.claude/skills/", commands: [
          { comment: "Copy the skill to Claude Code", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Workspace-Migration ~/.claude/skills/" },
        ] },
      ],
    } as SkillCloneInfo,
  },
  "ai-coding-opencode": {
    zipUrl: "/skills/ai-coding.zip",
    zipLabel: "OpenCode Setup Skill",
    guideUrl: "/guides/opencode-setup-guide.docx",
    guideLabel: "OpenCode Setup Guide",
    repoUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/AI-Coding/OpenCode-Setup",
    cloneInfo: {
      folderName: "OpenCode-Setup",
      generalCommands: [
        { comment: "Install WSL and Ubuntu (Windows CMD/PowerShell)", command: "wsl --install -d Ubuntu" },
        { comment: "Update packages (WSL Ubuntu terminal)", command: "sudo apt update && sudo apt upgrade -y" },
      ],
      toolSections: [
        { toolName: "OpenCode", installPath: "~/.config/opencode/", commands: [
          { comment: "Install OpenCode", command: "curl -fsSL https://opencode.ai/install | bash" },
          { comment: "Install KooCLI", command: "curl -LO https://ap-southeast-3-hwcloudcli.obs.ap-southeast-3.myhuaweicloud.com/cli/latest/huaweicloud-cli-linux-amd64.tar.gz && tar -zxvf huaweicloud-cli-linux-amd64.tar.gz && sudo mv hcloud /usr/local/bin/" },
          { comment: "Configure KooCLI with AK/SK", command: "hcloud configure init" },
        ] },
      ],
    } as SkillCloneInfo,
    cloneInfoLabelType: "wsl-install",
  },
  "ai-coding-hermes": {
    zipUrl: "/skills/ai-coding.zip",
    zipLabel: "Hermes Setup Skill",
    guideUrl: "/guides/ai-coding-hermes-guide.docx",
    guideLabel: "OpenCode + LiteLLM + MaaS Guide",
    repoUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/AI-Coding/Hermes-Setup",
    cloneInfo: {
      folderName: "Hermes-Setup",
      generalCommands: [
        { comment: "Install WSL and Ubuntu (Windows CMD/PowerShell)", command: "wsl --install -d Ubuntu" },
        { comment: "Update packages (WSL Ubuntu terminal)", command: "sudo apt update && sudo apt upgrade -y" },
      ],
      toolSections: [
        { toolName: "Hermes", installPath: "~/hermes-repro/", commands: [
          { comment: "Install hcloud CLI", command: "curl -LO https://ap-southeast-3-hwcloudcli.obs.ap-southeast-3.myhuaweicloud.com/cli/latest/huaweicloud-cli-linux-amd64.tar.gz && tar -zxvf huaweicloud-cli-linux-amd64.tar.gz && sudo mv hcloud /usr/local/bin/" },
          { comment: "Configure hcloud CLI", command: "hcloud configure init" },
          { comment: "Copy hermes-repro and install", command: "cp -r hermes-repro ~/ && cd ~/hermes-repro && bash install.sh" },
        ] },
      ],
    } as SkillCloneInfo,
    cloneInfoLabelType: "wsl-install",
  },
  "ai-coding-claude-code": {
    zipUrl: "/skills/ai-coding.zip",
    zipLabel: "Claude Code + LiteLLM Skill",
    guideUrl: "/guides/ai-coding-litellm-claude.docx",
    guideLabel: "LiteLLM + Claude + MaaS Guide",
    repoUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/AI-Coding/ClaudeCode-LiteLLM-MaaS",
    cloneInfo: {
      folderName: "ClaudeCode-LiteLLM-MaaS",
      generalCommands: [
        { comment: "Install WSL and Ubuntu (Windows CMD/PowerShell)", command: "wsl --install -d Ubuntu" },
        { comment: "Install Node.js v20 (WSL Ubuntu terminal)", command: "curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs" },
      ],
      toolSections: [
        { toolName: "Claude Code", installPath: "localhost:4000", commands: [
          { comment: "Install Claude Code", command: "npm install -g @anthropic-ai/claude-code" },
          { comment: "Create venv and install LiteLLM", command: "python3 -m venv litellm-venv && source litellm-venv/bin/activate && pip install litellm" },
          { comment: "Start LiteLLM proxy (with MaaS model aliases for Claude Code)", command: "litellm --model custom_openai/maas --api_base https://maas.huaweicloud.com/v1" },
        ] },
      ],
    } as SkillCloneInfo,
    cloneInfoLabelType: "wsl-install",
  },
  "cloud-foundation": {
    zipUrl: "/skills/cloud-foundation.zip",
    zipLabel: "Cloud Foundation Skill",
    repoUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation",
    cloneInfo: {
      folderName: "Cloud-Foundation",
      generalCommands: [
        { comment: "Clone the repository", command: "git clone https://github.com/binrogithub/1-3-Cloud-Adoption-Skills.git" },
      ],
      toolSections: [
        { toolName: "OpenCode", installPath: "~/.opencode/skills/", commands: [
          { comment: "Copy the skill to OpenCode", command: "find 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Cloud-Foundation -name SKILL.md -exec dirname {} \\; | while read d; do cp -r \"$d\" ~/.opencode/skills/; done" },
        ] },
        { toolName: "Hermes", installPath: "~/.hermes/skills/", commands: [
          { comment: "Copy the skill to Hermes", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Cloud-Foundation ~/.hermes/skills/" },
        ] },
        { toolName: "Claude Code", installPath: "~/.claude/skills/", commands: [
          { comment: "Copy the skill to Claude Code", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Cloud-Foundation ~/.claude/skills/" },
        ] },
      ],
    } as SkillCloneInfo,
  },
  "landing-zone": {
    zipUrl: "/skills/landing-zone.zip",
    zipLabel: "Landing Zone Skill",
    repoUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/Landing-Zone-and-Organization-Management",
    cloneInfo: {
      folderName: "Landing-Zone-and-Organization-Management",
      generalCommands: [
        { comment: "Clone the repository", command: "git clone https://github.com/binrogithub/1-3-Cloud-Adoption-Skills.git" },
      ],
      toolSections: [
        { toolName: "OpenCode", installPath: "~/.opencode/skills/", commands: [
          { comment: "Copy the skill to OpenCode", command: "find 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Cloud-Foundation/Landing-Zone-and-Organization-Management/multi-account-landing-zone -name SKILL.md -exec dirname {} \\; | while read d; do cp -r \"$d\" ~/.opencode/skills/; done" },
        ] },
        { toolName: "Hermes", installPath: "~/.hermes/skills/", commands: [
          { comment: "Copy the skill to Hermes", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Cloud-Foundation/Landing-Zone-and-Organization-Management/multi-account-landing-zone ~/.hermes/skills/" },
        ] },
        { toolName: "Claude Code", installPath: "~/.claude/skills/", commands: [
          { comment: "Copy the skill to Claude Code", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Cloud-Foundation/Landing-Zone-and-Organization-Management/multi-account-landing-zone ~/.claude/skills/" },
        ] },
      ],
    } as SkillCloneInfo,
  },
  "image-discovery": {
    zipUrl: "/skills/image-discovery.zip",
    zipLabel: "Image Discovery Skill",
    repoUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/AI-Coding/Image-Import-Demo",
    guideUrl: "/guides/image-discovery-ecs-deployment.docx",
    guideLabel: "Image Discovery & ECS Deployment Guide",
    cloneInfo: {
      folderName: "Image-Import-Demo",
      generalCommands: [
        { comment: "Clone the repository", command: "git clone https://github.com/binrogithub/1-3-Cloud-Adoption-Skills.git" },
      ],
      toolSections: [
        { toolName: "OpenCode", installPath: "~/.opencode/skills/", commands: [
          { comment: "Copy the skill to OpenCode", command: "find 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/AI-Coding/Image-Import-Demo/skills/huaweicloud-terraform-planner -name SKILL.md -exec dirname {} \\; | while read d; do cp -r \"$d\" ~/.opencode/skills/; done" },
        ] },
        { toolName: "Hermes", installPath: "~/.hermes/skills/", commands: [
          { comment: "Copy the skill to Hermes", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/AI-Coding/Image-Import-Demo/skills/huaweicloud-terraform-planner ~/.hermes/skills/" },
        ] },
        { toolName: "Claude Code", installPath: "~/.claude/skills/", commands: [
          { comment: "Copy the skill to Claude Code", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/AI-Coding/Image-Import-Demo/skills/huaweicloud-terraform-planner ~/.claude/skills/" },
        ] },
      ],
    } as SkillCloneInfo,
  },
  "object-migration": {
    zipUrl: "/skills/object-migration.zip",
    zipLabel: "Object Migration Skill",
    guideUrl: "/guides/object-migration-obs-static-site.docx",
    guideLabel: "OBS Static Site Guide",
    repoUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Object-Migration",
    cloneInfo: {
      folderName: "Object-Migration",
      generalCommands: [
        { comment: "Clone the repository", command: "git clone https://github.com/binrogithub/1-3-Cloud-Adoption-Skills.git" },
      ],
      toolSections: [
        { toolName: "OpenCode", installPath: "~/.opencode/skills/", commands: [
          { comment: "Copy the skill to OpenCode", command: "find 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Object-Migration -name SKILL.md -exec dirname {} \\; | while read d; do cp -r \"$d\" ~/.opencode/skills/; done" },
        ] },
        { toolName: "Hermes", installPath: "~/.hermes/skills/", commands: [
          { comment: "Copy the skill to Hermes", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Object-Migration ~/.hermes/skills/" },
        ] },
        { toolName: "Claude Code", installPath: "~/.claude/skills/", commands: [
          { comment: "Copy the skill to Claude Code", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Object-Migration ~/.claude/skills/" },
        ] },
      ],
    } as SkillCloneInfo,
  },
  "vm-migration": {
    zipUrl: "/skills/vm-migration.zip",
    zipLabel: "VM Migration Skill",
    guideUrl: "/guides/vm-migration-guide.docx",
    guideLabel: "VM Migration (SMS) Guide",
    repoUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/VM-Migration",
    cloneInfo: {
      folderName: "VM-Migration",
      generalCommands: [
        { comment: "Clone the repository", command: "git clone https://github.com/binrogithub/1-3-Cloud-Adoption-Skills.git" },
      ],
      toolSections: [
        { toolName: "OpenCode", installPath: "~/.opencode/skills/", commands: [
          { comment: "Copy the skill to OpenCode", command: "find 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/VM-Migration -name SKILL.md -exec dirname {} \\; | while read d; do cp -r \"$d\" ~/.opencode/skills/; done" },
        ] },
        { toolName: "Hermes", installPath: "~/.hermes/skills/", commands: [
          { comment: "Copy the skill to Hermes", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/VM-Migration ~/.hermes/skills/" },
        ] },
        { toolName: "Claude Code", installPath: "~/.claude/skills/", commands: [
          { comment: "Copy the skill to Claude Code", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/VM-Migration ~/.claude/skills/" },
        ] },
      ],
    } as SkillCloneInfo,
  },
  "other-scenarios": {
    zipUrl: "/skills/other-scenarios.zip",
    zipLabel: "Other Scenarios Skill",
    repoUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Other-Scenarios-Examples",
    cloneInfo: {
      folderName: "Other-Scenarios-Examples",
      generalCommands: [
        { comment: "Clone the repository", command: "git clone https://github.com/binrogithub/1-3-Cloud-Adoption-Skills.git" },
      ],
      toolSections: [
        { toolName: "OpenCode", installPath: "~/.opencode/skills/", commands: [
          { comment: "Copy the skill to OpenCode", command: "find 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Other-Scenarios-Examples -name SKILL.md -exec dirname {} \\; | while read d; do cp -r \"$d\" ~/.opencode/skills/; done" },
        ] },
        { toolName: "Hermes", installPath: "~/.hermes/skills/", commands: [
          { comment: "Copy the skill to Hermes", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Other-Scenarios-Examples ~/.hermes/skills/" },
        ] },
        { toolName: "Claude Code", installPath: "~/.claude/skills/", commands: [
          { comment: "Copy the skill to Claude Code", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Other-Scenarios-Examples ~/.claude/skills/" },
        ] },
      ],
    } as SkillCloneInfo,
  },
  "cbr-backup-restore": {
    zipUrl: "/skills/cbr-backup-restore.zip",
    zipLabel: "CBR Backup Restore Skill",
    repoUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/DR-and-Backup/cbr-backup-restore",
    cloneInfo: {
      folderName: "cbr-backup-restore",
      generalCommands: [
        { comment: "Clone the repository", command: "git clone https://github.com/binrogithub/1-3-Cloud-Adoption-Skills.git" },
      ],
      toolSections: [
        { toolName: "OpenCode", installPath: "~/.opencode/skills/", commands: [
          { comment: "Copy the skill to OpenCode", command: "find 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Cloud-Foundation/DR-and-Backup/cbr-backup-restore -name SKILL.md -exec dirname {} \\; | while read d; do cp -r \"$d\" ~/.opencode/skills/; done" },
        ] },
        { toolName: "Hermes", installPath: "~/.hermes/skills/", commands: [
          { comment: "Copy the skill to Hermes", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Cloud-Foundation/DR-and-Backup/cbr-backup-restore ~/.hermes/skills/" },
        ] },
        { toolName: "Claude Code", installPath: "~/.claude/skills/", commands: [
          { comment: "Copy the skill to Claude Code", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Cloud-Foundation/DR-and-Backup/cbr-backup-restore ~/.claude/skills/" },
        ] },
      ],
    } as SkillCloneInfo,
  },
  "sdrs-cross-region-dr": {
    zipUrl: "/skills/sdrs-cross-region-dr.zip",
    zipLabel: "SDRS Cross-Region DR Skill",
    guideUrl: "/guides/sdrs-cross-region-dr-guide.docx",
    guideLabel: "SDRS Cross-Region DR Guide",
    repoUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/DR-and-Backup/sdrs-cross-region-dr",
    cloneInfo: {
      folderName: "sdrs-cross-region-dr",
      generalCommands: [
        { comment: "Clone the repository", command: "git clone https://github.com/binrogithub/1-3-Cloud-Adoption-Skills.git" },
      ],
      toolSections: [
        { toolName: "OpenCode", installPath: "~/.opencode/skills/", commands: [
          { comment: "Copy the skill to OpenCode", command: "find 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Cloud-Foundation/DR-and-Backup/sdrs-cross-region-dr -name SKILL.md -exec dirname {} \\; | while read d; do cp -r \"$d\" ~/.opencode/skills/; done" },
        ] },
        { toolName: "Hermes", installPath: "~/.hermes/skills/", commands: [
          { comment: "Copy the skill to Hermes", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Cloud-Foundation/DR-and-Backup/sdrs-cross-region-dr ~/.hermes/skills/" },
        ] },
        { toolName: "Claude Code", installPath: "~/.claude/skills/", commands: [
          { comment: "Copy the skill to Claude Code", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Cloud-Foundation/DR-and-Backup/sdrs-cross-region-dr ~/.claude/skills/" },
        ] },
      ],
    } as SkillCloneInfo,
  },
  "dws-cluster-deployment": {
    zipUrl: "/skills/dws-cluster-deployment.zip",
    zipLabel: "DWS Cluster Deployment Skill",
    guideUrl: "/guides/dws-cluster-deployment-guide.docx",
    guideLabel: "DWS Cluster Deployment Guide",
    repoUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/dws-cluster-deployment",
    cloneInfo: {
      folderName: "dws-cluster-deployment",
      generalCommands: [
        { comment: "Clone the repository", command: "git clone https://github.com/binrogithub/1-3-Cloud-Adoption-Skills.git" },
      ],
      toolSections: [
        { toolName: "OpenCode", installPath: "~/.opencode/skills/", commands: [
          { comment: "Copy the skill to OpenCode", command: "find 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/dws-cluster-deployment -name SKILL.md -exec dirname {} \\; | while read d; do cp -r \"$d\" ~/.opencode/skills/; done" },
        ] },
        { toolName: "Hermes", installPath: "~/.hermes/skills/", commands: [
          { comment: "Copy the skill to Hermes", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/dws-cluster-deployment ~/.hermes/skills/" },
        ] },
        { toolName: "Claude Code", installPath: "~/.claude/skills/", commands: [
          { comment: "Copy the skill to Claude Code", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/dws-cluster-deployment ~/.claude/skills/" },
        ] },
      ],
    } as SkillCloneInfo,
  },
  "postgresql-ecs-to-rds-drs": {
    zipUrl: "/skills/postgresql-ecs-to-rds-drs.zip",
    zipLabel: "PostgreSQL ECS to RDS DRS Skill",
    guideUrl: "/guides/postgresql-ecs-to-rds-drs-guide.docx",
    guideLabel: "PostgreSQL ECS to RDS Migration Guide",
    repoUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/Relational-Database-Migration/postgresql-ecs-to-rds-drs",
    cloneInfo: {
      folderName: "postgresql-ecs-to-rds-drs",
      generalCommands: [
        { comment: "Clone the repository", command: "git clone https://github.com/binrogithub/1-3-Cloud-Adoption-Skills.git" },
      ],
      toolSections: [
        { toolName: "OpenCode", installPath: "~/.opencode/skills/", commands: [
          { comment: "Copy the skill to OpenCode", command: "find 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Database-Migration/Relational-Database-Migration/postgresql-ecs-to-rds-drs -name SKILL.md -exec dirname {} \\; | while read d; do cp -r \"$d\" ~/.opencode/skills/; done" },
        ] },
        { toolName: "Hermes", installPath: "~/.hermes/skills/", commands: [
          { comment: "Copy the skill to Hermes", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Database-Migration/Relational-Database-Migration/postgresql-ecs-to-rds-drs ~/.hermes/skills/" },
        ] },
        { toolName: "Claude Code", installPath: "~/.claude/skills/", commands: [
          { comment: "Copy the skill to Claude Code", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Database-Migration/Relational-Database-Migration/postgresql-ecs-to-rds-drs ~/.claude/skills/" },
        ] },
      ],
    } as SkillCloneInfo,
  },
  "snowflake-to-dataarts": {
    zipUrl: "/skills/snowflake-to-dataarts.zip",
    zipLabel: "Snowflake to DataArts Migration Skill",
    guideUrl: "/guides/snowflake-to-dataarts-guide.docx",
    guideLabel: "Snowflake to DataArts Migration Guide",
    repoUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/snowflake-to-dataarts",
    cloneInfo: {
      folderName: "snowflake-to-dataarts",
      generalCommands: [
        { comment: "Clone the repository", command: "git clone https://github.com/binrogithub/1-3-Cloud-Adoption-Skills.git" },
      ],
      toolSections: [
        { toolName: "OpenCode", installPath: "~/.opencode/skills/", commands: [
          { comment: "Copy the skill to OpenCode", command: "find 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/snowflake-to-dataarts -name SKILL.md -exec dirname {} \\; | while read d; do cp -r \"$d\" ~/.opencode/skills/; done" },
        ] },
        { toolName: "Hermes", installPath: "~/.hermes/skills/", commands: [
          { comment: "Copy the skill to Hermes", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/snowflake-to-dataarts ~/.hermes/skills/" },
        ] },
        { toolName: "Claude Code", installPath: "~/.claude/skills/", commands: [
          { comment: "Copy the skill to Claude Code", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/snowflake-to-dataarts ~/.claude/skills/" },
        ] },
      ],
    } as SkillCloneInfo,
  },
  "database-usage-operations": {
    zipUrl: "/skills/database-usage-operations.zip",
    zipLabel: "Database Usage Operations Skill",
    guideUrl: "/guides/database-usage-operations.docx",
    guideLabel: "Database Operations with KooCLI Guide",
    repoUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/database-usage-operations",
    cloneInfo: {
      folderName: "database-usage-operations",
      generalCommands: [
        { comment: "Clone the repository", command: "git clone https://github.com/binrogithub/1-3-Cloud-Adoption-Skills.git" },
      ],
      toolSections: [
        { toolName: "OpenCode", installPath: "~/.opencode/skills/", commands: [
          { comment: "Copy the skill to OpenCode", command: "find 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Database-Migration/database-usage-operations -name SKILL.md -exec dirname {} \\; | while read d; do cp -r \"$d\" ~/.opencode/skills/; done" },
        ] },
        { toolName: "Hermes", installPath: "~/.hermes/skills/", commands: [
          { comment: "Copy the skill to Hermes", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Database-Migration/database-usage-operations ~/.hermes/skills/" },
        ] },
        { toolName: "Claude Code", installPath: "~/.claude/skills/", commands: [
          { comment: "Copy the skill to Claude Code", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Database-Migration/database-usage-operations ~/.claude/skills/" },
        ] },
      ],
    } as SkillCloneInfo,
  },
  "codearts-deployment": {
    zipUrl: "/skills/codearts-kocli-deployment.zip",
    zipLabel: "CodeArts Deployment Skill",
    guideUrl: "/guides/codearts-devops-operations.docx",
    guideLabel: "CodeArts DevOps with KooCLI Guide",
    repoUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/CodeArts-Overview",
    cloneInfo: {
      folderName: "CodeArts-Overview",
      generalCommands: [
        { comment: "Clone the repository", command: "git clone https://github.com/binrogithub/1-3-Cloud-Adoption-Skills.git" },
      ],
      toolSections: [
        { toolName: "OpenCode", installPath: "~/.opencode/skills/", commands: [
          { comment: "Copy the skill to OpenCode", command: "find 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Cloud-Foundation/CodeArts-Overview -name SKILL.md -exec dirname {} \\; | while read d; do cp -r \"$d\" ~/.opencode/skills/; done" },
        ] },
        { toolName: "Hermes", installPath: "~/.hermes/skills/", commands: [
          { comment: "Copy the skill to Hermes", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Cloud-Foundation/CodeArts-Overview ~/.hermes/skills/" },
        ] },
        { toolName: "Claude Code", installPath: "~/.claude/skills/", commands: [
          { comment: "Copy the skill to Claude Code", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Cloud-Foundation/CodeArts-Overview ~/.claude/skills/" },
        ] },
      ],
    } as SkillCloneInfo,
  },
  "mrs-deployment": {
    zipUrl: "/skills/mrs-kocli-deployment.zip",
    zipLabel: "MRS Deployment Skill",
    guideUrl: "/guides/mrs-deploy-operations.docx",
    guideLabel: "MRS Deployment with KooCLI Guide",
    repoUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/MRS-Deployment",
    cloneInfo: {
      folderName: "MRS-Deployment",
      generalCommands: [
        { comment: "Clone the repository", command: "git clone https://github.com/binrogithub/1-3-Cloud-Adoption-Skills.git" },
      ],
      toolSections: [
        { toolName: "OpenCode", installPath: "~/.opencode/skills/", commands: [
          { comment: "Copy the skill to OpenCode", command: "find 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/MRS-Deployment -name SKILL.md -exec dirname {} \\; | while read d; do cp -r \"$d\" ~/.opencode/skills/; done" },
        ] },
        { toolName: "Hermes", installPath: "~/.hermes/skills/", commands: [
          { comment: "Copy the skill to Hermes", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/MRS-Deployment ~/.hermes/skills/" },
        ] },
        { toolName: "Claude Code", installPath: "~/.claude/skills/", commands: [
          { comment: "Copy the skill to Claude Code", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/MRS-Deployment ~/.claude/skills/" },
        ] },
      ],
    } as SkillCloneInfo,
  },
  "mrs-migration": {
    zipUrl: "/skills/huawei-mrs-migration-operations.zip",
    zipLabel: "MRS Migration Skill",
    guideUrl: "/guides/mrs-migration-guide.docx",
    guideLabel: "Migrating Hadoop Clusters to MRS Guide",
    repoUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/MRS-Migration",
    cloneInfo: {
      folderName: "MRS-Migration",
      generalCommands: [
        { comment: "Clone the repository", command: "git clone https://github.com/binrogithub/1-3-Cloud-Adoption-Skills.git" },
      ],
      toolSections: [
        { toolName: "OpenCode", installPath: "~/.opencode/skills/", commands: [
          { comment: "Copy the skill to OpenCode", command: "find 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/MRS-Migration -name SKILL.md -exec dirname {} \\; | while read d; do cp -r \"$d\" ~/.opencode/skills/; done" },
        ] },
        { toolName: "Hermes", installPath: "~/.hermes/skills/", commands: [
          { comment: "Copy the skill to Hermes", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/MRS-Migration ~/.hermes/skills/" },
        ] },
        { toolName: "Claude Code", installPath: "~/.claude/skills/", commands: [
          { comment: "Copy the skill to Claude Code", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Database-Migration/Big-Data-Platform-Migration/MRS-Migration ~/.claude/skills/" },
        ] },
      ],
    } as SkillCloneInfo,
  },
  "docker-compose-to-cci": {
    zipUrl: "",
    zipLabel: "Docker Compose to CCI Migration Skill",
    repoUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Container-Migration/cci",
    cloneInfo: {
      folderName: "cci",
      generalCommands: [
        { comment: "Clone the repository", command: "git clone https://github.com/binrogithub/1-3-Cloud-Adoption-Skills.git" },
      ],
      toolSections: [
        { toolName: "OpenCode", installPath: "~/.opencode/skills/", commands: [
          { comment: "Copy the CCI CLI deploy skill", command: "find 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Container-Migration/cci/cci-cli-deploy -name SKILL.md -exec dirname {} \\; | while read d; do cp -r \"$d\" ~/.opencode/skills/; donehuaweicloud-cci-cli-deploy" },
          { comment: "Copy the Docker Compose to CCI migration skill", command: "find 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Container-Migration/cci/docker-compose-to-cci -name SKILL.md -exec dirname {} \\; | while read d; do cp -r \"$d\" ~/.opencode/skills/; donehuaweicloud-docker-compose-to-cci" },
        ] },
        { toolName: "Hermes", installPath: "~/.hermes/skills/", commands: [
          { comment: "Copy the CCI CLI deploy skill", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Container-Migration/cci/cci-cli-deploy ~/.hermes/skills/huaweicloud-cci-cli-deploy" },
          { comment: "Copy the Docker Compose to CCI migration skill", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Container-Migration/cci/docker-compose-to-cci ~/.hermes/skills/huaweicloud-docker-compose-to-cci" },
        ] },
        { toolName: "Claude Code", installPath: "~/.claude/skills/", commands: [
          { comment: "Copy the CCI CLI deploy skill", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Container-Migration/cci/cci-cli-deploy ~/.claude/skills/huaweicloud-cci-cli-deploy" },
          { comment: "Copy the Docker Compose to CCI migration skill", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Container-Migration/cci/docker-compose-to-cci ~/.claude/skills/huaweicloud-docker-compose-to-cci" },
        ] },
      ],
    } as SkillCloneInfo,
  },
  "vpn-connectivity": {
    zipUrl: "/skills/vpn-connectivity.zip",
    zipLabel: "VPN Site-to-Cloud Creation Skill",
    repoUrl: "https://github.com/binrogithub/1-3-Cloud-Adoption-Skills/tree/main/AI-Assist-Migration/Cloud-Foundation/VPN-Connectivity/huaweicloud-vpn-s2c-create",
    cloneInfo: {
      folderName: "huaweicloud-vpn-s2c-create",
      generalCommands: [
        { comment: "Clone the repository", command: "git clone https://github.com/binrogithub/1-3-Cloud-Adoption-Skills.git" },
      ],
      toolSections: [
        { toolName: "OpenCode", installPath: "~/.opencode/skills/", commands: [
          { comment: "Copy the VPN skill to OpenCode", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Cloud-Foundation/VPN-Connectivity/huaweicloud-vpn-s2c-create ~/.opencode/skills/huaweicloud-vpn-s2c-create" },
        ] },
        { toolName: "Hermes", installPath: "~/.hermes/skills/", commands: [
          { comment: "Copy the VPN skill to Hermes", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Cloud-Foundation/VPN-Connectivity/huaweicloud-vpn-s2c-create ~/.hermes/skills/huaweicloud-vpn-s2c-create" },
        ] },
        { toolName: "Claude Code", installPath: "~/.claude/skills/", commands: [
          { comment: "Copy the VPN skill to Claude Code", command: "cp -r 1-3-Cloud-Adoption-Skills/AI-Assist-Migration/Cloud-Foundation/VPN-Connectivity/huaweicloud-vpn-s2c-create ~/.claude/skills/huaweicloud-vpn-s2c-create" },
        ] },
      ],
    } as SkillCloneInfo,
  },
};export function getMigrationScenarioTemplateConfig(
  scenario: SolutionScenario,
): MigrationScenarioTemplateConfig | undefined {
  if (!supportedScenarioIds.has(scenario.id)) {
    return undefined;
  }

  const skillLink = scenario.demoSkillLinks[0]?.url;

  return {
    scenarioId: scenario.id,
    hero: {
      title: scenario.title,
      description: scenario.oneLiner,
      image: scenario.heroImage,
      cta: {
        resourceType: "skill",
        title: {
          en: "AI Skill",
          es: "AI Skill",
          zh: "AI Skill",
        },
        description: {
          en: "Open the AI-assisted migration skill.",
          es: "Abra el skill de migración asistida por IA.",
          zh: "打开 AI 辅助迁移 Skill。",
        },
        buttonText: copy.tryAiSkill,
        status: skillLink ? "available" : "coming-soon",
        link: skillLink,
      },
    },
    solutionResources: [getSolutionResource(scenario)],
    skillResources: [
      getDemoResource(scenario),
      {
        resourceType: "skill",
        title: {
          en: "AI Skill",
          es: "AI Skill",
          zh: "AI Skill",
        },
        description: {
          en: "Use the GitHub Skill to start the AI-assisted migration workflow.",
          es: "Use el Skill de GitHub para iniciar el flujo de migración asistida por IA.",
          zh: "使用 GitHub Skill 开始 AI 辅助迁移流程。",
        },
        buttonText: copy.tryAiSkill,
        status: skillLink ? "available" : "coming-soon",
        link: skillLink,
      },
    ],
    howToStart: scenario.quickIntegration,
    recommendedServices: scenario.recommendedServices,
    faq: getFaq(scenario),
    relatedScenarios: getRelatedScenarios(scenario),
    ...(scenario.id === "vmware-migration"
      ? { demoVideoEmbedUrl: "https://www.youtube.com/embed/XYDBv9RNXHI" }
      : scenario.id === "workspace-migration"
      ? { demoVideoEmbedUrl: "https://www.youtube.com/embed/CQ5zz5QgSxc" }
      : scenario.id === "ai-coding-opencode"
      ? { demoVideoEmbedUrl: "https://www.youtube.com/embed/BbP_FRiql20" }
      : scenario.id === "cloud-to-cloud-migration"
      ? { demoVideoEmbedUrl: "https://www.youtube.com/embed/GwfaSq7dXQk" }
      : scenario.id === "ai-coding-claude-code"
      ? { demoVideoEmbedUrl: "https://www.youtube.com/embed/2f2jUrvaAJA" }
      : scenario.id === "container-migration"
      ? { demoVideoEmbedUrl: "https://www.youtube.com/embed/x_FTvN6qiSQ" }
      : scenario.id === "landing-zone"
      ? { demoVideoEmbedUrl: "https://www.youtube.com/embed/Pdz4J6Ox-r4" }
      : scenario.id === "image-discovery"
      ? { demoVideoEmbedUrl: "https://www.youtube.com/embed/ejtVLxu5ckM" }
      : {}),
    ...(scenarioSkillInfo[scenario.id]
      ? {
          skillZipUrl: scenarioSkillInfo[scenario.id].zipUrl,
          skillZipLabel: scenarioSkillInfo[scenario.id].zipLabel,
          skillRepoUrl: scenarioSkillInfo[scenario.id].repoUrl,
          skillCloneInfo: scenarioSkillInfo[scenario.id].cloneInfo,
          skillCloneInfoLabelType: scenarioSkillInfo[scenario.id].cloneInfoLabelType,
          ...(scenarioSkillInfo[scenario.id].guideUrl
            ? {
                skillGuideUrl: scenarioSkillInfo[scenario.id].guideUrl,
                skillGuideLabel: scenarioSkillInfo[scenario.id].guideLabel,
              }
            : {}),
        }
      : {}),
    detailedLayout: scenario.id !== "vmware-migration",
    contactInfo: {
      title: {
        en: "Need a migration plan?",
        es: "¿Necesita un plan de migración?",
        zh: "需要迁移方案支持？",
      },
      description: {
        en: "Connect with a migration expert or return to the scenario catalog.",
        es: "Conecte con un experto de migración o vuelva al catálogo de escenarios.",
        zh: "联系迁移专家，或返回迁移场景列表继续查看。",
      },
      buttonText: {
        en: "Contact Expert",
        es: "Contactar experto",
        zh: "联系专家",
      },
      link: "https://www.huaweicloud.com/intl/en-us/contact-sales.html",
    },
  };
}

export function migrationText(lang: Parameters<typeof textFor>[0], value: LocalizedPair) {
  return textFor(lang, value);
}
