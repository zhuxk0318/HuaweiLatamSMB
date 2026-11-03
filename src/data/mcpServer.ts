// hcloud-mcp-server v0.4.0 — tool catalog and metadata for the public MCP page.
// Source of truth: /home/ubuntu-user/.mcp-servers/hcloud-mcp-server (Python, 150 tools).

export const mcpServerVersion = "0.4.0";
export const mcpProtocolVersion = "2025-03-26";
export const mcpTotalTools = 150; // 149 structured read-only + 1 hcloud_cli catch-all
export const mcpStructuredTools = 149;
export const mcpServicesCovered = 34;
export const mcpGitHubRepo = "https://github.com/binrogithub/hcloud-mcp-server";
export const mcpDownloadUrl = "/downloads/hcloud-mcp-server.tar.gz";
export const mcpDownloadSize = "22 KB";

export type McpServiceCategory =
  | "Compute"
  | "Network"
  | "Storage"
  | "Database"
  | "Security & Identity"
  | "Monitoring & Logs"
  | "Migration & Backup"
  | "Big Data & Analytics"
  | "DevOps"
  | "Messaging"
  | "Governance & Billing";

export type McpService = {
  id: string;
  name: string; // short display name
  fullName: string; // official Huawei Cloud name
  cliService: string; // hcloud CLI service name
  category: McpServiceCategory;
  toolCount: number;
  description: string;
};

export type McpTool = {
  name: string;
  service: string; // service id
  description: string;
  readOnly: boolean;
};

// 34 services grouped by category.
export const mcpServices: McpService[] = [
  // Compute
  { id: "ecs", name: "ECS", fullName: "Elastic Cloud Server", cliService: "ECS", category: "Compute", toolCount: 8, description: "Virtual servers, flavors, keypairs, AZs, interfaces, volumes, quotas." },
  { id: "cce", name: "CCE", fullName: "Cloud Container Engine", cliService: "CCE", category: "Compute", toolCount: 6, description: "Kubernetes clusters, nodes, node pools, add-ons." },
  { id: "cci", name: "CCI", fullName: "Cloud Container Instance", cliService: "CCI", category: "Compute", toolCount: 3, description: "Serverless containers — namespaces, deployments, pods." },
  { id: "as", name: "AS", fullName: "Auto Scaling", cliService: "AS", category: "Compute", toolCount: 7, description: "Scaling groups, configurations, policies, instances." },
  { id: "ims", name: "IMS", fullName: "Image Management Service", cliService: "IMS", category: "Compute", toolCount: 4, description: "Public/private images, OS versions, quotas." },
  // Network
  { id: "vpc", name: "VPC", fullName: "Virtual Private Cloud", cliService: "VPC", category: "Network", toolCount: 9, description: "VPCs, subnets, security groups, route tables, quotas." },
  { id: "eip", name: "EIP", fullName: "Elastic IP", cliService: "EIP", category: "Network", toolCount: 4, description: "Elastic public IPs, bandwidths, quotas." },
  { id: "elb", name: "ELB", fullName: "Elastic Load Balance", cliService: "ELB", category: "Network", toolCount: 9, description: "Load balancers, listeners, pools, members, health monitors, L7 policies, flavors." },
  { id: "nat", name: "NAT", fullName: "NAT Gateway", cliService: "NAT", category: "Network", toolCount: 4, description: "NAT gateways, SNAT/DNAT rules." },
  { id: "dns", name: "DNS", fullName: "Domain Name Service", cliService: "DNS", category: "Network", toolCount: 3, description: "DNS zones and record sets." },
  { id: "vpn", name: "VPN", fullName: "Virtual Private Network", cliService: "VPN", category: "Network", toolCount: 7, description: "VPN gateways, connections, IKE/IPsec policies, customer gateways (API v5)." },
  { id: "er", name: "ER", fullName: "Enterprise Router", cliService: "ER", category: "Network", toolCount: 4, description: "Enterprise routers, route tables, attachments." },
  { id: "cfw", name: "CFW", fullName: "Cloud Firewall", cliService: "CFW", category: "Network", toolCount: 3, description: "Firewalls, ACL rules, service rules." },
  // Storage
  { id: "obs", name: "OBS", fullName: "Object Storage Service", cliService: "OBS", category: "Storage", toolCount: 3, description: "Buckets and objects — list, stat, cat (via obsutil)." },
  { id: "evs", name: "EVS", fullName: "Elastic Volume Service", cliService: "EVS", category: "Storage", toolCount: 5, description: "Disk volumes, snapshots, volume types." },
  { id: "swr", name: "SWR", fullName: "Software Repository for Containers", cliService: "SWR", category: "Storage", toolCount: 4, description: "Namespaces, repositories, tags, login domain." },
  // Database
  { id: "rds", name: "RDS", fullName: "Relational Database Service", cliService: "RDS", category: "Database", toolCount: 5, description: "Instances, flavors, storage types, engine versions, backups." },
  { id: "gaussdb", name: "GaussDB", fullName: "GaussDB (openGauss)", cliService: "GaussDB", category: "Database", toolCount: 4, description: "openGauss instances, flavors, datastores." },
  { id: "dcs", name: "DCS", fullName: "Distributed Cache Service", cliService: "DCS", category: "Database", toolCount: 4, description: "Redis instances, flavors, availability zones." },
  { id: "dds", name: "DDS", fullName: "Document Database Service", cliService: "DDS", category: "Database", toolCount: 3, description: "MongoDB instances, flavors, storage types." },
  { id: "dws", name: "DWS", fullName: "GaussDB(DWS)", cliService: "DWS", category: "Database", toolCount: 3, description: "Data warehouse clusters, flavors." },
  // Security & Identity
  { id: "iam", name: "IAM", fullName: "Identity and Access Management", cliService: "IAM", category: "Security & Identity", toolCount: 8, description: "Users, groups, policies, agencies, projects, domains." },
  { id: "kms", name: "KMS", fullName: "Key Management Service", cliService: "KMS", category: "Security & Identity", toolCount: 2, description: "Encryption keys and key details." },
  // Monitoring & Logs
  { id: "ces", name: "CES", fullName: "Cloud Eye", cliService: "CES", category: "Monitoring & Logs", toolCount: 4, description: "Alarms, alarm rules, metrics, metric data points." },
  { id: "lts", name: "LTS", fullName: "Log Tank Service", cliService: "LTS", category: "Monitoring & Logs", toolCount: 2, description: "Log groups and log streams." },
  // Migration & Backup
  { id: "drs", name: "DRS", fullName: "Data Replication Service", cliService: "DRS", category: "Migration & Backup", toolCount: 3, description: "Replication jobs and quotas." },
  { id: "sms", name: "SMS", fullName: "Server Migration Service", cliService: "SMS", category: "Migration & Backup", toolCount: 5, description: "Source servers, migration tasks, migration projects." },
  { id: "oms", name: "OMS", fullName: "Object Storage Migration Service", cliService: "OMS", category: "Migration & Backup", toolCount: 3, description: "Migration tasks and sync tasks." },
  { id: "cbr", name: "CBR", fullName: "Cloud Backup and Recovery", cliService: "CBR", category: "Migration & Backup", toolCount: 4, description: "Vaults, backups, backup policies." },
  // Big Data & Analytics
  { id: "mrs", name: "MRS", fullName: "MapReduce Service", cliService: "MRS", category: "Big Data & Analytics", toolCount: 3, description: "Clusters and flavors." },
  { id: "dataarts", name: "DataArts", fullName: "DataArts Studio", cliService: "DataArtsStudio", category: "Big Data & Analytics", toolCount: 2, description: "Workspaces and catalogs." },
  // DevOps
  { id: "codearts", name: "CodeArts", fullName: "CodeArts", cliService: "ProjectMan/Repo/Pipeline", category: "DevOps", toolCount: 3, description: "Projects, repositories, pipelines." },
  // Messaging
  { id: "smn", name: "SMN", fullName: "Simple Message Notification", cliService: "SMN", category: "Messaging", toolCount: 2, description: "Topics and subscriptions." },
  // Governance & Billing
  { id: "organizations", name: "Organizations", fullName: "Organizations + RGC", cliService: "Organizations/RGC", category: "Governance & Billing", toolCount: 3, description: "Organizational units, accounts, RGC control policies." },
  { id: "bss", name: "BSS", fullName: "Billing and Subscription", cliService: "BSSINTL", category: "Governance & Billing", toolCount: 3, description: "Customer orders, account balance, measurements." },
];

export const mcpCategoryOrder: McpServiceCategory[] = [
  "Compute",
  "Network",
  "Storage",
  "Database",
  "Security & Identity",
  "Monitoring & Logs",
  "Migration & Backup",
  "Big Data & Analytics",
  "DevOps",
  "Messaging",
  "Governance & Billing",
];

// Full tool reference table (149 structured tools). The generic hcloud_cli is
// described separately in the page copy.
export const mcpTools: McpTool[] = [
  // ECS
  { name: "hcloud_list_servers", service: "ecs", description: "List ECS cloud servers with optional filters", readOnly: true },
  { name: "hcloud_show_server", service: "ecs", description: "Get details of a specific ECS server", readOnly: true },
  { name: "hcloud_list_flavors", service: "ecs", description: "List available ECS instance flavors/specs", readOnly: true },
  { name: "hcloud_list_availability_zones", service: "ecs", description: "List availability zones for ECS", readOnly: true },
  { name: "hcloud_list_server_interfaces", service: "ecs", description: "List network interfaces attached to an ECS server", readOnly: true },
  { name: "hcloud_list_server_block_devices", service: "ecs", description: "List block devices (volumes) attached to an ECS server", readOnly: true },
  { name: "hcloud_list_keypairs", service: "ecs", description: "List SSH key pairs", readOnly: true },
  { name: "hcloud_show_server_limits", service: "ecs", description: "Show ECS quota/limits for the tenant", readOnly: true },
  // VPC
  { name: "hcloud_list_vpcs", service: "vpc", description: "List VPCs in the region", readOnly: true },
  { name: "hcloud_show_vpc", service: "vpc", description: "Get details of a specific VPC", readOnly: true },
  { name: "hcloud_list_subnets", service: "vpc", description: "List subnets", readOnly: true },
  { name: "hcloud_show_subnet", service: "vpc", description: "Get details of a specific subnet", readOnly: true },
  { name: "hcloud_list_security_groups", service: "vpc", description: "List security groups", readOnly: true },
  { name: "hcloud_show_security_group", service: "vpc", description: "Get details of a specific security group", readOnly: true },
  { name: "hcloud_list_security_group_rules", service: "vpc", description: "List security group rules", readOnly: true },
  { name: "hcloud_list_route_tables", service: "vpc", description: "List route tables", readOnly: true },
  { name: "hcloud_show_quota", service: "vpc", description: "Show VPC resource quotas", readOnly: true },
  // EIP
  { name: "hcloud_list_public_ips", service: "eip", description: "List elastic public IPs", readOnly: true },
  { name: "hcloud_show_public_ip", service: "eip", description: "Get details of a specific elastic public IP", readOnly: true },
  { name: "hcloud_list_bandwidths", service: "eip", description: "List bandwidths", readOnly: true },
  { name: "hcloud_list_eip_quotas", service: "eip", description: "List EIP resource quotas", readOnly: true },
  // EVS
  { name: "hcloud_list_volumes", service: "evs", description: "List EVS disk volumes", readOnly: true },
  { name: "hcloud_show_volume", service: "evs", description: "Get details of a specific EVS volume", readOnly: true },
  { name: "hcloud_list_snapshots", service: "evs", description: "List EVS volume snapshots", readOnly: true },
  { name: "hcloud_show_snapshot", service: "evs", description: "Get details of a specific EVS snapshot", readOnly: true },
  { name: "hcloud_list_volume_types", service: "evs", description: "List available EVS volume types", readOnly: true },
  // IAM
  { name: "hcloud_list_users", service: "iam", description: "List IAM users", readOnly: true },
  { name: "hcloud_show_user", service: "iam", description: "Get details of a specific IAM user", readOnly: true },
  { name: "hcloud_list_groups", service: "iam", description: "List IAM user groups", readOnly: true },
  { name: "hcloud_list_policies", service: "iam", description: "List IAM policies (system and custom)", readOnly: true },
  { name: "hcloud_list_user_policies", service: "iam", description: "List policies attached to an IAM user", readOnly: true },
  { name: "hcloud_list_agencies", service: "iam", description: "List IAM agencies (trust relationships)", readOnly: true },
  { name: "hcloud_list_projects", service: "iam", description: "List IAM projects", readOnly: true },
  { name: "hcloud_list_domains", service: "iam", description: "List authenticated IAM domains", readOnly: true },
  // ELB
  { name: "hcloud_list_load_balancers", service: "elb", description: "List ELB load balancers", readOnly: true },
  { name: "hcloud_show_load_balancer", service: "elb", description: "Get details of a specific load balancer", readOnly: true },
  { name: "hcloud_show_load_balancer_topology", service: "elb", description: "Show load balancer topology tree (listeners, pools, members)", readOnly: true },
  { name: "hcloud_list_listeners", service: "elb", description: "List ELB listeners", readOnly: true },
  { name: "hcloud_list_pools", service: "elb", description: "List ELB backend server groups (pools)", readOnly: true },
  { name: "hcloud_list_members", service: "elb", description: "List backend members in an ELB pool", readOnly: true },
  { name: "hcloud_list_health_monitors", service: "elb", description: "List ELB health monitors", readOnly: true },
  { name: "hcloud_list_l7_policies", service: "elb", description: "List ELB URL-based routing policies", readOnly: true },
  { name: "hcloud_list_elb_flavors", service: "elb", description: "List available ELB flavor specifications", readOnly: true },
  // RDS
  { name: "hcloud_list_rds_instances", service: "rds", description: "List RDS database instances", readOnly: true },
  { name: "hcloud_list_rds_flavors", service: "rds", description: "List RDS instance flavor/spec options", readOnly: true },
  { name: "hcloud_list_rds_storage_types", service: "rds", description: "List supported RDS storage types per engine/version", readOnly: true },
  { name: "hcloud_list_rds_datastores", service: "rds", description: "List available RDS DB engine versions", readOnly: true },
  { name: "hcloud_list_rds_backups", service: "rds", description: "List RDS backups", readOnly: true },
  // CCE
  { name: "hcloud_list_cce_clusters", service: "cce", description: "List CCE (Kubernetes) clusters", readOnly: true },
  { name: "hcloud_show_cce_cluster", service: "cce", description: "Get details of a specific CCE cluster", readOnly: true },
  { name: "hcloud_list_cce_nodes", service: "cce", description: "List nodes in a CCE cluster", readOnly: true },
  { name: "hcloud_list_node_pools", service: "cce", description: "List node pools in a CCE cluster", readOnly: true },
  { name: "hcloud_show_node_pool", service: "cce", description: "Get details of a specific CCE node pool", readOnly: true },
  { name: "hcloud_list_addon_instances", service: "cce", description: "List installed add-ons in a CCE cluster", readOnly: true },
  // AS
  { name: "hcloud_list_scaling_groups", service: "as", description: "List AS (Auto Scaling) groups", readOnly: true },
  { name: "hcloud_show_scaling_group", service: "as", description: "Get details of a specific AS group", readOnly: true },
  { name: "hcloud_list_scaling_configs", service: "as", description: "List AS (Auto Scaling) configurations", readOnly: true },
  { name: "hcloud_show_scaling_config", service: "as", description: "Get details of a specific AS configuration", readOnly: true },
  { name: "hcloud_list_scaling_policies", service: "as", description: "List AS (Auto Scaling) policies", readOnly: true },
  { name: "hcloud_show_scaling_policy", service: "as", description: "Get details of a specific AS policy", readOnly: true },
  { name: "hcloud_list_scaling_instances", service: "as", description: "List instances currently in AS groups", readOnly: true },
  // OBS
  { name: "hcloud_obs_ls", service: "obs", description: "List OBS buckets or objects in a bucket", readOnly: true },
  { name: "hcloud_obs_stat", service: "obs", description: "Show properties of an OBS bucket or object", readOnly: true },
  { name: "hcloud_obs_cat", service: "obs", description: "View content of a text object in OBS", readOnly: true },
  // DNS
  { name: "hcloud_list_dns_zones", service: "dns", description: "List DNS zones", readOnly: true },
  { name: "hcloud_show_dns_zone", service: "dns", description: "Get details of a specific DNS zone", readOnly: true },
  { name: "hcloud_list_dns_recordsets", service: "dns", description: "List DNS record sets in a zone", readOnly: true },
  // KMS
  { name: "hcloud_list_kms_keys", service: "kms", description: "List KMS encryption keys", readOnly: true },
  { name: "hcloud_list_kms_key_detail", service: "kms", description: "Get details of a specific KMS key (state, creation date, etc.)", readOnly: true },
  // CES
  { name: "hcloud_list_alarms", service: "ces", description: "List CES (Cloud Eye) alarms", readOnly: true },
  { name: "hcloud_list_alarm_rules", service: "ces", description: "List CES alarm rules (v2 API, more complete)", readOnly: true },
  { name: "hcloud_list_metrics", service: "ces", description: "List CES (Cloud Eye) metrics", readOnly: true },
  { name: "hcloud_show_metric_data", service: "ces", description: "Show CES (Cloud Eye) metric data points", readOnly: true },
  // IMS
  { name: "hcloud_list_images", service: "ims", description: "List available IMS images (essential for finding image_ref for ECS/CCE/AS)", readOnly: true },
  { name: "hcloud_show_image", service: "ims", description: "Get details of a specific IMS image (min_ram, min_disk, status)", readOnly: true },
  { name: "hcloud_list_os_versions", service: "ims", description: "List available IMS OS versions (key for image selection)", readOnly: true },
  { name: "hcloud_show_image_quotas", service: "ims", description: "Show IMS image resource quotas", readOnly: true },
  // NAT
  { name: "hcloud_list_nat_gateways", service: "nat", description: "List NAT gateways", readOnly: true },
  { name: "hcloud_show_nat_gateway", service: "nat", description: "Get details of a specific NAT gateway", readOnly: true },
  { name: "hcloud_list_nat_gateway_snat_rules", service: "nat", description: "List SNAT rules on a NAT gateway", readOnly: true },
  { name: "hcloud_list_nat_gateway_dnat_rules", service: "nat", description: "List DNAT rules on a NAT gateway", readOnly: true },
  // DCS
  { name: "hcloud_list_dcs_instances", service: "dcs", description: "List DCS (Redis) instances", readOnly: true },
  { name: "hcloud_show_dcs_instance", service: "dcs", description: "Get details of a specific DCS (Redis) instance", readOnly: true },
  { name: "hcloud_list_dcs_flavors", service: "dcs", description: "List available DCS (Redis) instance flavors/specs", readOnly: true },
  { name: "hcloud_list_dcs_available_zones", service: "dcs", description: "List available availability zones for DCS (Redis)", readOnly: true },
  // DDS
  { name: "hcloud_list_dds_instances", service: "dds", description: "List DDS (MongoDB) instances", readOnly: true },
  { name: "hcloud_list_dds_flavors", service: "dds", description: "List available DDS (MongoDB) instance flavors/specs", readOnly: true },
  { name: "hcloud_list_dds_storage_types", service: "dds", description: "List available DDS (MongoDB) storage types", readOnly: true },
  // SMN
  { name: "hcloud_list_smn_topics", service: "smn", description: "List SMN (Simple Message Notification) topics", readOnly: true },
  { name: "hcloud_list_smn_subscriptions", service: "smn", description: "List SMN subscriptions", readOnly: true },
  // VPN
  { name: "hcloud_list_vpn_gateways", service: "vpn", description: "List VPN gateways (VGWs) with optional filters", readOnly: true },
  { name: "hcloud_show_vpn_gateway", service: "vpn", description: "Get details of a specific VPN gateway (VGW)", readOnly: true },
  { name: "hcloud_list_vpn_connections", service: "vpn", description: "List VPN connections with optional filters", readOnly: true },
  { name: "hcloud_show_vpn_connection", service: "vpn", description: "Get details of a specific VPN connection", readOnly: true },
  { name: "hcloud_list_vpn_ike_policies", service: "vpn", description: "List VPN IKE policies", readOnly: true },
  { name: "hcloud_list_vpn_ipsec_policies", service: "vpn", description: "List VPN IPsec policies", readOnly: true },
  { name: "hcloud_list_vpn_customer_gateways", service: "vpn", description: "List VPN customer gateways (CGWs) with optional filters", readOnly: true },
  // DRS
  { name: "hcloud_list_drs_jobs", service: "drs", description: "List DRS (Data Replication Service) jobs with optional filters", readOnly: true },
  { name: "hcloud_show_drs_job", service: "drs", description: "Get details of a specific DRS job", readOnly: true },
  { name: "hcloud_list_drs_quotas", service: "drs", description: "List DRS quotas for the tenant", readOnly: true },
  // SWR
  { name: "hcloud_list_swr_namespaces", service: "swr", description: "List SWR (Software Repository for Containers) namespaces with optional filters", readOnly: true },
  { name: "hcloud_list_swr_repositories", service: "swr", description: "List SWR repositories with optional filters", readOnly: true },
  { name: "hcloud_list_swr_tags", service: "swr", description: "List tags for a specific SWR repository", readOnly: true },
  { name: "hcloud_show_swr_domain", service: "swr", description: "Show the SWR login domain for the tenant", readOnly: true },
  // OMS
  { name: "hcloud_list_oms_tasks", service: "oms", description: "List OMS (Object Storage Migration Service) tasks", readOnly: true },
  { name: "hcloud_show_oms_task", service: "oms", description: "Get details of a specific OMS (Object Storage Migration Service) task", readOnly: true },
  { name: "hcloud_list_oms_sync_tasks", service: "oms", description: "List OMS (Object Storage Migration Service) sync tasks", readOnly: true },
  // SMS
  { name: "hcloud_list_sms_servers", service: "sms", description: "List SMS (Server Migration Service) source servers", readOnly: true },
  { name: "hcloud_show_sms_server", service: "sms", description: "Get details of a specific SMS (Server Migration Service) source server", readOnly: true },
  { name: "hcloud_list_sms_tasks", service: "sms", description: "List SMS (Server Migration Service) migration tasks", readOnly: true },
  { name: "hcloud_show_sms_task", service: "sms", description: "Get details of a specific SMS (Server Migration Service) migration task", readOnly: true },
  { name: "hcloud_list_sms_migration_projects", service: "sms", description: "List SMS (Server Migration Service) migration projects", readOnly: true },
  // CBR
  { name: "hcloud_list_cbr_vaults", service: "cbr", description: "List CBR (Cloud Backup and Recovery) vaults", readOnly: true },
  { name: "hcloud_show_cbr_vault", service: "cbr", description: "Get details of a specific CBR (Cloud Backup and Recovery) vault", readOnly: true },
  { name: "hcloud_list_cbr_backups", service: "cbr", description: "List CBR (Cloud Backup and Recovery) backups", readOnly: true },
  { name: "hcloud_list_cbr_policies", service: "cbr", description: "List CBR (Cloud Backup and Recovery) backup policies", readOnly: true },
  // CCI
  { name: "hcloud_list_cci_namespaces", service: "cci", description: "List CCI (Cloud Container Instance) namespaces", readOnly: true },
  { name: "hcloud_list_cci_deployments", service: "cci", description: "List CCI (Cloud Container Instance) deployments", readOnly: true },
  { name: "hcloud_list_cci_pods", service: "cci", description: "List CCI (Cloud Container Instance) pods", readOnly: true },
  // MRS
  { name: "hcloud_list_mrs_clusters", service: "mrs", description: "List MRS (MapReduce Service) clusters", readOnly: true },
  { name: "hcloud_show_mrs_cluster", service: "mrs", description: "Get details of a specific MRS (MapReduce Service) cluster", readOnly: true },
  { name: "hcloud_list_mrs_flavors", service: "mrs", description: "List available MRS (MapReduce Service) cluster flavors/specs", readOnly: true },
  // DWS
  { name: "hcloud_list_dws_clusters", service: "dws", description: "List DWS (GaussDB Data Warehouse) clusters", readOnly: true },
  { name: "hcloud_show_dws_cluster", service: "dws", description: "Get details of a specific DWS (GaussDB Data Warehouse) cluster", readOnly: true },
  { name: "hcloud_list_dws_flavors", service: "dws", description: "List available DWS (GaussDB Data Warehouse) cluster flavors/specs", readOnly: true },
  // GaussDB
  { name: "hcloud_list_gaussdb_instances", service: "gaussdb", description: "List GaussDB (openGauss) instances", readOnly: true },
  { name: "hcloud_show_gaussdb_instance", service: "gaussdb", description: "Get details of a specific GaussDB (openGauss) instance", readOnly: true },
  { name: "hcloud_list_gaussdb_flavors", service: "gaussdb", description: "List available GaussDB (openGauss) instance flavors/specs", readOnly: true },
  { name: "hcloud_list_gaussdb_datastores", service: "gaussdb", description: "List available GaussDB (openGauss) DB engine versions", readOnly: true },
  // ER
  { name: "hcloud_list_er_routers", service: "er", description: "List ER (Enterprise Router) routers", readOnly: true },
  { name: "hcloud_show_er_router", service: "er", description: "Get details of a specific ER (Enterprise Router) router", readOnly: true },
  { name: "hcloud_list_er_route_tables", service: "er", description: "List route tables for a specific ER (Enterprise Router) router", readOnly: true },
  { name: "hcloud_list_er_attachments", service: "er", description: "List attachments for a specific ER (Enterprise Router) router", readOnly: true },
  // CFW
  { name: "hcloud_list_cfw_firewalls", service: "cfw", description: "List CFW (Cloud Firewall) firewalls", readOnly: true },
  { name: "hcloud_list_cfw_acl_rules", service: "cfw", description: "List CFW (Cloud Firewall) ACL rules", readOnly: true },
  { name: "hcloud_list_cfw_service_rules", service: "cfw", description: "List CFW (Cloud Firewall) service rules", readOnly: true },
  // CodeArts
  { name: "hcloud_list_codearts_projects", service: "codearts", description: "List CodeArts projects", readOnly: true },
  { name: "hcloud_list_codearts_repositories", service: "codearts", description: "List CodeArts repositories in a project", readOnly: true },
  { name: "hcloud_list_codearts_pipelines", service: "codearts", description: "List CodeArts pipelines in a project", readOnly: true },
  // DataArts
  { name: "hcloud_list_dataarts_workspaces", service: "dataarts", description: "List DataArts workspaces", readOnly: true },
  { name: "hcloud_list_dataarts_catalogs", service: "dataarts", description: "List DataArts catalogs in a workspace", readOnly: true },
  // Organizations
  { name: "hcloud_list_organizations_ous", service: "organizations", description: "List Organizations organizational units (OUs)", readOnly: true },
  { name: "hcloud_list_organizations_accounts", service: "organizations", description: "List Organizations accounts", readOnly: true },
  { name: "hcloud_list_rgc_control_policies", service: "organizations", description: "List RGC control policies", readOnly: true },
  // LTS
  { name: "hcloud_list_lts_groups", service: "lts", description: "List LTS (Log Tank Service) log groups", readOnly: true },
  { name: "hcloud_list_lts_streams", service: "lts", description: "List LTS (Log Tank Service) log streams in a log group", readOnly: true },
  // BSS
  { name: "hcloud_list_bss_customer_orders", service: "bss", description: "List BSS (Billing and Subscription) customer orders", readOnly: true },
  { name: "hcloud_show_bss_account_balance", service: "bss", description: "Show BSS (Billing and Subscription) account balance", readOnly: true },
  { name: "hcloud_list_bss_measurements", service: "bss", description: "List BSS (Billing and Subscription) measurements", readOnly: true },
];

// Installation snippets for different AI clients.
// Each includes the config file path so agents know WHERE to write the snippet.
export const mcpInstallSnippets: Record<string, { label: string; configPath: string; language: string; code: string }> = {
  opencode: {
    label: "opencode",
    configPath: "~/.config/opencode/opencode.json",
    language: "json",
    code: `{
  "mcp": {
    "hcloud": {
      "type": "local",
      "command": ["hcloud-mcp"],
      "enabled": true
    }
  }
}`,
  },
  claude: {
    label: "Claude Desktop",
    configPath: "~/.claude/claude_desktop_config.json",
    language: "json",
    code: `{
  "mcpServers": {
    "hcloud": {
      "command": "hcloud-mcp"
    }
  }
}`,
  },
  cursor: {
    label: "Cursor",
    configPath: ".cursor/mcp.json",
    language: "json",
    code: `{
  "mcpServers": {
    "hcloud": {
      "command": "hcloud-mcp"
    }
  }
}`,
  },
  vscode: {
    label: "VS Code",
    configPath: ".vscode/settings.json",
    language: "json",
    code: `{
  "mcp.servers": {
    "hcloud": {
      "type": "stdio",
      "command": "hcloud-mcp"
    }
  }
}`,
  },
};

// Step-by-step installation guide (for the page and the plain-text endpoint).
export const mcpInstallSteps: Array<{ step: number; title: string; commands: string[]; note?: string }> = [
  {
    step: 1,
    title: "Install KooCLI (hcloud)",
    commands: [
      "curl -LO https://ap-southeast-3-hwcloudcli.obs.ap-southeast-3.myhuaweicloud.com/cli/latest/huaweicloud-cli-linux-amd64.tar.gz",
      "tar xzf huaweicloud-cli-linux-amd64.tar.gz",
      "sudo mv hcloud /usr/local/bin/",
      "hcloud --version",
    ],
    note: "KooCLI is a single binary — no installation needed, just download and extract. Docs: https://support.huaweicloud.com/intl/en-us/qs-hcli/hcli_02_003.html",
  },
  {
    step: 2,
    title: "Configure Huawei Cloud credentials",
    commands: [
      "hcloud configure set --cli-mode=AKSK --cli-region=la-north-2 --cli-agree-privacy-statement=true",
      "hcloud configure set --cli-access-key=YOUR_ACCESS_KEY --cli-secret-key=YOUR_SECRET_KEY",
      "hcloud IAM ListCustomPolicies  # verify credentials work",
    ],
    note: "Get your AK/SK from the Huawei Cloud console: My Credentials → Access Keys. The region can be any Huawei Cloud region (la-north-2, sa-brazil-1, ap-southeast-1, etc.).",
  },
  {
    step: 3,
    title: "Install the MCP server",
    commands: [
      "git clone https://github.com/binrogithub/hcloud-mcp-server.git",
      "cd hcloud-mcp-server",
      "pip install --upgrade pip setuptools  # needed on older systems (Ubuntu 22.04)",
      "pip install .",
      "hcloud-mcp --help  # verify installation",
    ],
    note: "Requires Python 3.10+ and git. Alternative: download tarball from http://huaweilatam.com/downloads/hcloud-mcp-server.tar.gz. Dependencies: mcp>=2.0, pyyaml>=6.0 (installed automatically by pip).",
  },
  {
    step: 4,
    title: "Add the MCP server to your AI client",
    commands: [
      "# See the installation tabs below for your specific client",
      "# Copy the JSON config to the config file path shown for your client",
    ],
    note: "The config tells your AI client how to start the hcloud-mcp server. After adding it, restart your AI client.",
  },
  {
    step: 5,
    title: "Verify the integration",
    commands: [
      "hcloud-mcp --help  # MCP server starts and shows help",
      "hcloud IAM ListCustomPolicies  # credentials work",
      "# In your AI client, ask: 'List my ECS servers in la-north-2'",
    ],
    note: "If the AI client can call hcloud_list_servers and get results, the installation is complete.",
  },
];

// Example usage blocks shown on the page.
export const mcpExamples: Array<{ title: string; description: string; language: string; code: string }> = [
  {
    title: "List ECS servers",
    description: "Structured tool with type-safe parameters. Returns JSON.",
    language: "python",
    code: `hcloud_list_servers(region="la-north-2")`,
  },
  {
    title: "List VPN gateways (API v5)",
    description: "New VPN v5 tools added in v0.4.0.",
    language: "python",
    code: `hcloud_list_vpn_gateways(region="la-north-2")`,
  },
  {
    title: "Show CCE cluster details",
    description: "Get details of a specific Kubernetes cluster.",
    language: "python",
    code: `hcloud_show_cce_cluster(region="la-north-2", cluster_id="cluster-id")`,
  },
  {
    title: "Generic CLI (write operations)",
    description: "The hcloud_cli catch-all handles writes with a safety gate. Destructive operations require confirm=true; default is dry-run.",
    language: "python",
    code: `hcloud_cli(command="ECS CreateServers --cli-region=la-north-2 --name=my-server --flavorRef=s6.small.1 --imageRef=...")`,
  },
];
