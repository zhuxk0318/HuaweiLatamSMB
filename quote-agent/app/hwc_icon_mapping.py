"""Mapping from standard Huawei Cloud product names to draw.io library icon titles.

Supports synonym normalization so that both "Elastic Cloud Server" and "ECS"
resolve to the same library icon title.
"""
from __future__ import annotations

# Canonical product key -> library icon title
# The keys are the standard short names used in specs (lowercase).
# The values are exact titles in the HWC draw.io libraries.
PRODUCT_TO_ICON_TITLE: dict[str, str] = {
    # Compute
    "ecs": "Elastic Cloud Server (ECS)",
    "bms": "Bare Metal Server (BMS)",
    "cce": "Cloud Container Engine (CCE)",
    "cci": "Cloud Container Instance (CCI)",
    "as": "Auto Scaling (AS)",
    "as_group": "Auto Scaling Group (AS Group)",
    "fgacs": "FGPA Accelerated Cloud Server (FACS)",
    "gacs": "GPU Accelerated Cloud Server (GACS)",
    "deh": "Dedicated Host (DeH)",
    "functiongraph": "FunctionGraph",
    "cae": "Cloud Application Egine (CAE)",
    # Networking
    "vpc": "Virtual Private Cloud (VPC)",
    "subnet": "Subnet",
    "eip": "Elastic IP (EIP)",
    "elb": "Elastic Load Balance (ELB)",
    "nat": "NAT Gateway",
    "nat_gateway": "NAT Gateway",
    "vpn": "Virtual Private Network (VPN)",
    "dc": "Direct Connect",
    "dns": "Domain Name Service (DNS)",
    "sg": "Security Group",
    "er": "Enterprise Router (ER)",
    "cfw": "Cloud Firewall (CFW)",
    "vpcep": "VPC Endpoint (VPCEP)",
    "ga": "Global Accelerator (GA)",
    "cc": "Cloud Connect (CC)",
    "cdn": "Content Delivery Network (CDN)",
    "apig": "API Gateway (APIG)",
    # Storage
    "evs": "Elastic Volume Service (EVS)",
    "obs": "Object Storage Service (OBS)",
    "sfs": "Scalable File Service (SFS)",
    "sfs_turbo": "Scalable File Service (SFS) Turbo",
    "cbr": "Cloud Backup and Recovery (CBR)",
    "csg": "Cloud Storage Gateway (CSG)",
    "dss": "Dedicated Distributed Storage Service (DSS)",
    # Database
    "rds": "Relational Database Service (RDS)",
    "rds_mysql": "RDS for MySQL",
    "rds_pg": "RDS for PostgreSQL",
    "rds_sqlserver": "RDS for SQL Server",
    "rds_mariadb": "RDS for MariaDB",
    "dds": "Document Database Service (DDS)",
    "dcs": "Distributed Cache Service (DCS) for Redis",
    "dms": "Distributed Message Service (DMS)",
    "dms_rocketmq": "Distributed Message Service (DMS) for RocketMQ",
    "kafka": "Kafka",
    "rabbitmq": "RabbitMQ",
    "gaussdb": "GaussDB",
    "dws": "GaussDB(DWS)",
    "gemindb": "GeminiDB",
    "ddm": "Distributed Database Middleware (DDM)",
    "drs": "Data Replication Service (DRS)",
    # Security
    "waf": "Web Application Firewall (WAF)",
    "hss": "Host Security Service (HSS)",
    "kms": "Key Management Service (KMS)",
    "iam": "Identity and Access Management (IAM)",
    "cbh": "Cloud Bastion Host (CBH)",
    "anti_ddos": "Anti-DDoS",
    "dbss": "Database Security Service (DBSS)",
    "dsc": "Data Security Center (DSC)",
    # Management & Governance
    "ces": "Cloud Eye Service (CES)",
    "cts": "Cloud Trace Service (CTS)",
    "smn": "Simple Message Notification (SMN)",
    "lts": "Log Tank Servce (LTS)",
    "aom": "Application Operation Management (AOM)",
    "rms": "Config (RMS)",
    # Migration
    "sms": "Server Migration Service (SMS)",
    "mgc": "Migration Center (MgC)",
    "ugo": "Database and Application Migration (UGO)",
    "oms": "Object Migration Service (OMS)",
    # Big Data / AI
    "mrs": "MapReduce Service (MRS)",
    "dli": "Data Lake Insight (DLI)",
    "modelarts": "ModelArts",
    "dis": "Data Ingestion Service (DIS)",
    "css": "Cloud Search Service (CSS)",
    # Other
    "region": "Region",
    "az": "Availability Zone (AZ)",
    "workspace": "Workspace",
    "romac": "ROMA Connect",
    "sdwan": "Software-Defined WAN (SDWAN)",
    "sdrs": "Storage Disaster Recovery Service (SDRS)",
    "sdrs": "Storage Disaster Recovery Service (SDRS)",
}

# Synonym map: alternative names -> canonical product key
_SYNONYMS: dict[str, str] = {
    # ECS
    "elastic cloud server": "ecs",
    "elastic cloud server (ecs)": "ecs",
    # RDS
    "relational database service": "rds",
    "relational database service (rds)": "rds",
    # ELB
    "elastic load balance": "elb",
    "elastic load balance (elb)": "elb",
    "elastic load balancer": "elb",
    "load balancer": "elb",
    # OBS
    "object storage service": "obs",
    "object storage service (obs)": "obs",
    # EVS
    "elastic volume service": "evs",
    "elastic volume service (evs)": "evs",
    # VPC
    "virtual private cloud": "vpc",
    "virtual private cloud (vpc)": "vpc",
    # EIP
    "elastic ip": "eip",
    "elastic ip (eip)": "eip",
    # NAT
    "nat gateway": "nat",
    # VPN
    "virtual private network": "vpn",
    "virtual private network (vpn)": "vpn",
    # WAF
    "web application firewall": "waf",
    "web application firewall (waf)": "waf",
    # CCE
    "cloud container engine": "cce",
    "cloud container engine (cce)": "cce",
    # DDS
    "document database service": "dds",
    "document database service (dds)": "dds",
    # DCS
    "distributed cache service": "dcs",
    "distributed cache service (dcs) for redis": "dcs",
    # DMS
    "distributed message service": "dms",
    "distributed message service (dms)": "dms",
    # CBR
    "cloud backup and recovery": "cbr",
    "cloud backup and recovery (cbr)": "cbr",
    # SMN
    "simple message notification": "smn",
    "simple message notification (smn)": "smn",
    # APIG
    "api gateway": "apig",
    "api gateway (apig)": "apig",
    # SFS
    "scalable file service": "sfs",
    "scalable file service (sfs)": "sfs",
    # GaussDB
    "gaussdb(dws)": "dws",
    # DNS
    "domain name service": "dns",
    "domain name service (dns)": "dns",
    # Direct Connect
    "direct connect": "dc",
    # IAM
    "identity and access management": "iam",
    "identity and access management (iam)": "iam",
    # KMS
    "key management service": "kms",
    "key management service (kms)": "kms",
    # HSS
    "host security service": "hss",
    "host security service (hss)": "hss",
    # CES
    "cloud eye service": "ces",
    "cloud eye service (ces)": "ces",
    # CTS
    "cloud trace service": "cts",
    "cloud trace service (cts)": "cts",
    # MRS
    "mapreduce service": "mrs",
    "mapreduce service (mrs)": "mrs",
    # DLI
    "data lake insight": "dli",
    "data lake insight (dli)": "dli",
    # CFW
    "cloud firewall": "cfw",
    "cloud firewall (cfw)": "cfw",
    # ER
    "enterprise router": "er",
    "enterprise router (er)": "er",
    # Auto Scaling
    "auto scaling": "as",
    "auto scaling (as)": "as",
    "auto scaling group": "as_group",
    "auto scaling group (as group)": "as_group",
    # Region / AZ
    "availability zone": "az",
    "availability zone (az)": "az",
}


def resolve_product_icon_title(product: str | None) -> str | None:
    """Resolve a product name to its library icon title.

    Tries direct lookup, then synonym normalization, then case-insensitive
    search. Returns None if no mapping found (caller should use fallback).
    """
    if not product:
        return None

    # Direct lookup by canonical key
    key = product.strip().lower()
    title = PRODUCT_TO_ICON_TITLE.get(key)
    if title:
        return title

    # Synonym lookup
    title_via_syn = PRODUCT_TO_ICON_TITLE.get(_SYNONYMS.get(key))
    if title_via_syn:
        return title_via_syn

    # Try matching the product directly as an icon title (case-insensitive)
    from app.hwc_drawio_library import _title_index

    index = _title_index()
    # Exact match
    if product in index:
        return product
    # Case-insensitive match
    lower = product.lower()
    for t in index:
        if t.lower() == lower:
            return t

    return None
