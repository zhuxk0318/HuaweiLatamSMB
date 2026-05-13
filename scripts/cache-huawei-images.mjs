import { createHash } from "node:crypto";
import { createWriteStream } from "node:fs";
import { mkdir, rm, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { Readable, Transform } from "node:stream";
import { pipeline } from "node:stream/promises";

const seeds = [
  "https://www.huaweicloud.com/intl/en-us/",
  "https://e.huawei.com/en/",
];

const cliOptions = Object.fromEntries(
  process.argv
    .slice(2)
    .filter((arg) => arg.startsWith("--") && arg.includes("="))
    .map((arg) => {
      const [key, value] = arg.slice(2).split("=", 2);
      return [key, value];
    }),
);

const pageLimitPerSite = Number(cliOptions["page-limit"] ?? process.env.HUAWEI_CACHE_PAGE_LIMIT ?? 80);
const imageLimit = Number(cliOptions["image-limit"] ?? process.env.HUAWEI_CACHE_IMAGE_LIMIT ?? 800);
const maxBytes = Number(cliOptions["max-bytes"] ?? process.env.HUAWEI_CACHE_MAX_BYTES ?? 8 * 1024 * 1024);
const timeoutMs = Number(cliOptions.timeout ?? process.env.HUAWEI_CACHE_TIMEOUT_MS ?? 8000);
const outputDir = path.resolve("public/assets/huawei/official-cache");
const manifestPath = path.join(outputDir, "manifest.json");

const headers = {
  "user-agent":
    "Mozilla/5.0 (compatible; HuaweiAssetCache/1.0; +https://www.huaweicloud.com/intl/en-us/)",
  accept: "text/html,application/xhtml+xml,image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
};

function siteId(url) {
  return new URL(url).hostname.replace(/^www\./, "");
}

function normalizeUrl(rawUrl, baseUrl) {
  const trimmed = rawUrl?.trim();
  if (!trimmed || trimmed.startsWith("data:") || trimmed.startsWith("javascript:")) {
    return null;
  }
  try {
    return new URL(trimmed.replace(/&amp;/g, "&"), baseUrl).toString();
  } catch {
    return null;
  }
}

function isHuaweiUrl(url) {
  const hostname = new URL(url).hostname.toLowerCase();
  return (
    hostname.endsWith("huaweicloud.com") ||
    hostname.endsWith("huawei.com") ||
    hostname.endsWith("hc-cdn.com") ||
    hostname.endsWith("huaweicloudimg.com")
  );
}

function shouldSkipImageUrl(url) {
  const lower = url.toLowerCase();
  return (
    lower.includes("favicon") ||
    lower.includes("logo") ||
    lower.includes("sprite") ||
    lower.includes("spacer") ||
    lower.includes("pixel") ||
    lower.includes("tracking") ||
    lower.includes("analytics") ||
    lower.includes("beacon") ||
    lower.endsWith(".ico")
  );
}

function extensionFor(url, contentType = "") {
  const pathname = new URL(url).pathname;
  const ext = path.extname(pathname).toLowerCase();
  if (/^\.(avif|webp|png|jpe?g|gif|svg)$/.test(ext)) {
    return ext;
  }
  if (contentType.includes("svg")) return ".svg";
  if (contentType.includes("png")) return ".png";
  if (contentType.includes("webp")) return ".webp";
  if (contentType.includes("avif")) return ".avif";
  if (contentType.includes("gif")) return ".gif";
  return ".jpg";
}

function imageName(url, contentType) {
  const hash = createHash("sha256").update(url).digest("hex").slice(0, 16);
  const rawBase = path.basename(new URL(url).pathname).replace(/\.[^.]+$/, "");
  const safeBase = rawBase.toLowerCase().replace(/[^a-z0-9-]+/g, "-").replace(/^-|-$/g, "").slice(0, 54);
  return `${safeBase || "huawei-image"}-${hash}${extensionFor(url, contentType)}`;
}

function decodeHtml(value = "") {
  return value
    .replace(/&quot;/g, "\"")
    .replace(/&#34;/g, "\"")
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}

function extractAttribute(tag, name) {
  const match = tag.match(new RegExp(`${name}\\s*=\\s*("([^"]*)"|'([^']*)'|([^\\s>]+))`, "i"));
  return decodeHtml(match?.[2] ?? match?.[3] ?? match?.[4] ?? "");
}

function addImage(candidateMap, rawUrl, baseUrl, alt = "") {
  const absoluteUrl = normalizeUrl(rawUrl, baseUrl);
  if (!absoluteUrl || !isHuaweiUrl(absoluteUrl) || shouldSkipImageUrl(absoluteUrl)) {
    return;
  }
  if (!candidateMap.has(absoluteUrl)) {
    candidateMap.set(absoluteUrl, { originalUrl: absoluteUrl, alt });
  } else if (alt && !candidateMap.get(absoluteUrl).alt) {
    candidateMap.get(absoluteUrl).alt = alt;
  }
}

function extractImages(html, pageUrl) {
  const images = new Map();
  const imgTags = html.match(/<(img|source)\b[^>]*>/gi) ?? [];
  for (const tag of imgTags) {
    const alt = extractAttribute(tag, "alt");
    for (const attr of ["src", "data-src", "data-original", "data-lazy", "content"]) {
      addImage(images, extractAttribute(tag, attr), pageUrl, alt);
    }
    const srcset = extractAttribute(tag, "srcset") || extractAttribute(tag, "data-srcset");
    for (const part of srcset.split(",")) {
      addImage(images, part.trim().split(/\s+/)[0], pageUrl, alt);
    }
  }

  const metaTags = html.match(/<meta\b[^>]*>/gi) ?? [];
  for (const tag of metaTags) {
    const property = `${extractAttribute(tag, "property")} ${extractAttribute(tag, "name")}`.toLowerCase();
    if (property.includes("image")) {
      addImage(images, extractAttribute(tag, "content"), pageUrl, property);
    }
  }

  const cssUrls = html.matchAll(/url\((['"]?)([^'")]+)\1\)/gi);
  for (const match of cssUrls) {
    addImage(images, match[2], pageUrl);
  }

  const directUrls = html.matchAll(/https?:\/\/[^"'<>\\\s]+\.(?:avif|webp|png|jpe?g|gif|svg)(?:\?[^"'<>\\\s]*)?/gi);
  for (const match of directUrls) {
    addImage(images, match[0], pageUrl);
  }

  return [...images.values()];
}

function extractLinks(html, pageUrl, rootHost) {
  const links = [];
  const anchors = html.match(/<a\b[^>]*>/gi) ?? [];
  for (const tag of anchors) {
    const absoluteUrl = normalizeUrl(extractAttribute(tag, "href"), pageUrl);
    if (!absoluteUrl) continue;
    const parsed = new URL(absoluteUrl);
    parsed.hash = "";
    if (parsed.hostname === rootHost && !/\.(pdf|zip|rar|7z|png|jpe?g|gif|svg|webp|mp4)$/i.test(parsed.pathname)) {
      links.push(parsed.toString());
    }
  }
  return links;
}

async function fetchWithTimeout(url, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, headers: { ...headers, ...options.headers }, signal: controller.signal });
  } finally {
    clearTimeout(timeout);
  }
}

async function fetchHtml(url) {
  const response = await fetchWithTimeout(url);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("text/html")) {
    throw new Error(`Unexpected content-type ${contentType}`);
  }
  return response.text();
}

async function downloadImage(candidate, pageUrl, rootSite) {
  const cachedFilename = imageName(candidate.originalUrl, "");
  const cachedDiskPath = path.join(outputDir, cachedFilename);
  try {
    const cachedFile = await stat(cachedDiskPath);
    if (cachedFile.size >= 1024) {
      return {
        sourceSite: rootSite,
        sourceUrl: pageUrl,
        originalUrl: candidate.originalUrl,
        localPath: `/assets/huawei/official-cache/${cachedFilename}`,
        fileSize: cachedFile.size,
        alt: candidate.alt ?? "",
      };
    }
  } catch {
    // Continue with a network download when the expected cached file is absent.
  }

  const response = await fetchWithTimeout(candidate.originalUrl);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.startsWith("image/")) {
    throw new Error(`Unexpected content-type ${contentType || "unknown"}`);
  }
  const declaredLength = Number(response.headers.get("content-length") ?? 0);
  if (declaredLength > maxBytes) {
    throw new Error(`File exceeds ${maxBytes} bytes`);
  }

  const filename = imageName(candidate.originalUrl, contentType);
  const diskPath = path.join(outputDir, filename);
  const sizeCounter = new TransformByteLimit(maxBytes);
  await pipeline(Readable.fromWeb(response.body), sizeCounter, createWriteStream(diskPath));
  const file = await stat(diskPath);

  if (file.size < 1024) {
    await rm(diskPath, { force: true });
    throw new Error("Image is too small");
  }

  return {
    sourceSite: rootSite,
    sourceUrl: pageUrl,
    originalUrl: candidate.originalUrl,
    localPath: `/assets/huawei/official-cache/${filename}`,
    fileSize: file.size,
    alt: candidate.alt ?? "",
  };
}

class TransformByteLimit extends Transform {
  constructor(limit) {
    super();
    this.limit = limit;
    this.total = 0;
  }

  _transform(chunk, _encoding, callback) {
    this.total += chunk.length;
    if (this.total > this.limit) {
      callback(new Error(`File exceeds ${this.limit} bytes`));
      return;
    }
    callback(null, chunk);
  }
}

async function crawlSite(seedUrl, manifest) {
  const root = new URL(seedUrl);
  const rootSite = siteId(seedUrl);
  const queue = [seedUrl];
  const visited = new Set();
  const queued = new Set(queue);

  while (queue.length && visited.size < pageLimitPerSite && manifest.images.length < imageLimit) {
    const pageUrl = queue.shift();
    visited.add(pageUrl);

    let html;
    try {
      html = await fetchHtml(pageUrl);
      manifest.pages.push({ sourceSite: rootSite, sourceUrl: pageUrl, status: "ok" });
    } catch (error) {
      manifest.failures.push({ sourceSite: rootSite, sourceUrl: pageUrl, stage: "page", error: String(error.message ?? error) });
      continue;
    }

    for (const link of extractLinks(html, pageUrl, root.hostname)) {
      if (!queued.has(link) && visited.size + queue.length < pageLimitPerSite) {
        queued.add(link);
        queue.push(link);
      }
    }

    for (const candidate of extractImages(html, pageUrl).slice(0, Number(cliOptions["candidates-per-page"] ?? 80))) {
      if (manifest.images.length >= imageLimit) break;
      if (manifest.seenImages.has(candidate.originalUrl)) continue;
      manifest.seenImages.add(candidate.originalUrl);
      try {
        const record = await downloadImage(candidate, pageUrl, rootSite);
        manifest.images.push(record);
        console.log(`saved ${record.localPath}`);
      } catch (error) {
        manifest.failures.push({
          sourceSite: rootSite,
          sourceUrl: pageUrl,
          originalUrl: candidate.originalUrl,
          stage: "image",
          error: String(error.message ?? error),
        });
      }
    }
  }
}

async function main() {
  await mkdir(outputDir, { recursive: true });
  const manifest = {
    generatedAt: new Date().toISOString(),
    seeds,
    limits: { pageLimitPerSite, imageLimit, maxBytes },
    images: [],
    pages: [],
    failures: [],
    seenImages: new Set(),
  };

  for (const seed of seeds) {
    await crawlSite(seed, manifest);
  }

  const serializableManifest = {
    generatedAt: manifest.generatedAt,
    seeds: manifest.seeds,
    limits: manifest.limits,
    images: manifest.images,
    pages: manifest.pages,
    failures: manifest.failures,
  };
  await writeFile(manifestPath, `${JSON.stringify(serializableManifest, null, 2)}\n`, "utf8");
  console.log(
    `cached ${manifest.images.length} images from ${manifest.pages.length} pages; ${manifest.failures.length} failures recorded`,
  );
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
