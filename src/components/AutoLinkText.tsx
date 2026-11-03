import { trackClick } from "../analytics";

type LinkTerm = {
  term: string;
  url: string;
  caseSensitive: boolean;
};

const linkTerms: LinkTerm[] = [
  { term: "ModelArts MaaS", url: "https://support.huaweicloud.com/intl/en-us/modelarts/", caseSensitive: false },
  { term: "DataArts Studio", url: "https://support.huaweicloud.com/intl/en-us/dataarts/", caseSensitive: false },
  { term: "Direct Connect", url: "https://support.huaweicloud.com/intl/en-us/dc/", caseSensitive: false },
  { term: "Cloud End Site", url: "https://support.huaweicloud.com/intl/en-us/cloudend/", caseSensitive: false },
  { term: "NAT Gateway", url: "https://support.huaweicloud.com/intl/en-us/natgateway/", caseSensitive: false },
  { term: "SFS Turbo", url: "https://support.huaweicloud.com/intl/en-us/sfsturbo/", caseSensitive: false },
  { term: "Identity Center", url: "https://support.huaweicloud.com/intl/en-us/identitycenter/", caseSensitive: false },
  { term: "DataArts", url: "https://support.huaweicloud.com/intl/en-us/dataarts/", caseSensitive: false },
  { term: "GaussDB", url: "https://support.huaweicloud.com/intl/en-us/gaussdb/", caseSensitive: false },
  { term: "GeminiDB", url: "https://support.huaweicloud.com/intl/en-us/geminidb/", caseSensitive: false },
  { term: "FunctionGraph", url: "https://support.huaweicloud.com/intl/en-us/functiongraph/", caseSensitive: false },
  { term: "Workspace", url: "https://support.huaweicloud.com/intl/en-us/workspace/", caseSensitive: false },
  { term: "KooCLI", url: "https://support.huaweicloud.com/intl/en-us/cli/", caseSensitive: true },
  { term: "Terraform", url: "https://developer.hashicorp.com/terraform/docs", caseSensitive: true },
  { term: "Velero", url: "https://velero.io/docs/", caseSensitive: true },
  { term: "obsutil", url: "https://support.huaweicloud.com/intl/en-us/obsutil/", caseSensitive: true },
  { term: "Docker", url: "https://docs.docker.com/", caseSensitive: true },
  { term: "Kubernetes", url: "https://kubernetes.io/docs/", caseSensitive: true },
  { term: "kubectl", url: "https://kubernetes.io/docs/reference/kubectl/", caseSensitive: true },
  { term: "Helm", url: "https://helm.sh/docs/", caseSensitive: true },
  { term: "Babelfish", url: "https://support.huaweicloud.com/intl/en-us/gaussdb/", caseSensitive: true },
  { term: "Kind", url: "https://kind.sigs.k8s.io/", caseSensitive: true },
  { term: "DRS", url: "https://support.huaweicloud.com/intl/en-us/drs/", caseSensitive: true },
  { term: "OMS", url: "https://support.huaweicloud.com/intl/en-us/oms/", caseSensitive: true },
  { term: "SMS", url: "https://support.huaweicloud.com/intl/en-us/sms/", caseSensitive: true },
  { term: "MgC", url: "https://support.huaweicloud.com/intl/en-us/mgc/", caseSensitive: true },
  { term: "UGO", url: "https://support.huaweicloud.com/intl/en-us/ugo/", caseSensitive: true },
  { term: "DWS", url: "https://support.huaweicloud.com/intl/en-us/dws/", caseSensitive: true },
  { term: "MRS", url: "https://support.huaweicloud.com/intl/en-us/mrs/", caseSensitive: true },
  { term: "CCE", url: "https://support.huaweicloud.com/intl/en-us/cce/", caseSensitive: true },
  { term: "ECS", url: "https://support.huaweicloud.com/intl/en-us/ecs/", caseSensitive: true },
  { term: "OBS", url: "https://support.huaweicloud.com/intl/en-us/obs/", caseSensitive: true },
  { term: "RDS", url: "https://support.huaweicloud.com/intl/en-us/rds/", caseSensitive: true },
  { term: "VPC", url: "https://support.huaweicloud.com/intl/en-us/vpc/", caseSensitive: true },
  { term: "ELB", url: "https://support.huaweicloud.com/intl/en-us/elb/", caseSensitive: true },
  { term: "SWR", url: "https://support.huaweicloud.com/intl/en-us/swr/", caseSensitive: true },
  { term: "EIP", url: "https://support.huaweicloud.com/intl/en-us/eip/", caseSensitive: true },
  { term: "CBR", url: "https://support.huaweicloud.com/intl/en-us/cbr/", caseSensitive: true },
  { term: "HSS", url: "https://support.huaweicloud.com/intl/en-us/hss/", caseSensitive: true },
  { term: "DEW", url: "https://support.huaweicloud.com/intl/en-us/dew/", caseSensitive: true },
  { term: "DMS", url: "https://support.huaweicloud.com/intl/en-us/dms/", caseSensitive: true },
  { term: "SMN", url: "https://support.huaweicloud.com/intl/en-us/smn/", caseSensitive: true },
  { term: "SDR", url: "https://support.huaweicloud.com/intl/en-us/sdr/", caseSensitive: true },
  { term: "CES", url: "https://support.huaweicloud.com/intl/en-us/ces/", caseSensitive: true },
  { term: "VPN", url: "https://support.huaweicloud.com/intl/en-us/vpn/", caseSensitive: true },
  { term: "EVS", url: "https://support.huaweicloud.com/intl/en-us/evs/", caseSensitive: true },
];

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

type Match = { start: number; end: number; term: string; url: string };

function findAllMatches(text: string): Match[] {
  const matches: Match[] = [];
  for (const lt of linkTerms) {
    const flags = lt.caseSensitive ? "g" : "gi";
    const regex = new RegExp(`(?<![a-zA-Z])${escapeRegex(lt.term)}(?![a-zA-Z])`, flags);
    let m: RegExpExecArray | null;
    while ((m = regex.exec(text)) !== null) {
      matches.push({ start: m.index, end: m.index + m[0].length, term: m[0], url: lt.url });
    }
  }
  matches.sort((a, b) => a.start - b.start || b.end - b.start - (a.end - a.start));
  const filtered: Match[] = [];
  let lastEnd = -1;
  for (const m of matches) {
    if (m.start >= lastEnd) {
      filtered.push(m);
      lastEnd = m.end;
    }
  }
  return filtered;
}

export function AutoLinkText({ text, className }: { text: string; className?: string }) {
  const matches = findAllMatches(text);
  if (matches.length === 0) {
    return <span className={className}>{text}</span>;
  }
  const parts: React.ReactNode[] = [];
  let pos = 0;
  for (let i = 0; i < matches.length; i++) {
    const m = matches[i];
    if (m.start > pos) {
      parts.push(text.slice(pos, m.start));
    }
    parts.push(
      <a
        key={i}
        href={m.url}
        target="_blank"
        rel="noreferrer"
        className="auto-link-term"
        onClick={() =>
          trackClick({
            click_target: "auto_link_term",
            click_section: "auto_link",
            destination: m.url,
          })
        }
      >
        {m.term}
      </a>
    );
    pos = m.end;
  }
  if (pos < text.length) {
    parts.push(text.slice(pos));
  }
  return <span className={className}>{parts}</span>;
}
