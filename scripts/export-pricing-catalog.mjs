import fs from "node:fs/promises";
import path from "node:path";
import vm from "node:vm";

const siteRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const sourcePath = path.join(siteRoot, "src/data/pricingCatalog.ts");
const outputPath = path.resolve(siteRoot, "./quote-agent/data/flexible-pricing-catalog.json");

function transpileCatalogSource(source) {
  return source
    .replace(/^export type .*$/gm, "")
    .replace(/^export const HOURS_PER_MONTH =/m, "const HOURS_PER_MONTH =")
    .replace(/^export const pricingCatalog =/m, "const pricingCatalog =")
    .replace(/^export const pricingMetadata =/m, "const pricingMetadata =")
    .replace(/ as const;/g, ";")
    .concat("\nmodule.exports = { pricingCatalog, pricingMetadata };\n");
}

function convertEcsItems(region, ecsList) {
  return ecsList.map((ecs) => ({
    product: "ECS",
    region,
    sku: ecs.spec,
    family: ecs.familyLabel,
    tier: ecs.category,
    billing_mode: "on_demand_monthly",
    unit: "instance-month",
    price: Math.round(ecs.hourlyUsd * 730 * 100) / 100,
    currency: "USD",
    source_url: "https://www.huaweicloud.com/intl/en-us/product/ecs.html",
    captured_at: new Date().toISOString(),
    raw_attributes: {
      vcpu: ecs.vcpu,
      memoryGiB: ecs.memoryGiB,
      hourlyUsd: ecs.hourlyUsd,
      monthlyUsd: ecs.monthlyUsd,
      yearlyUsd: ecs.yearlyUsd,
      ri1YearMonthlyUsd: ecs.ri1YearMonthlyUsd,
      ri1YearEffectiveHourlyUsd: ecs.ri1YearEffectiveHourlyUsd,
      spec: ecs.spec,
      resourceSpecCode: ecs.resourceSpecCode,
      generation: ecs.generation,
      image: ecs.image,
    },
    confirmed: true,
    status: "confirmed",
    capture_error: null,
  }));
}

function convertEvsItems(region, evsList) {
  return evsList.map((evs) => ({
    product: "EVS",
    region,
    sku: evs.key,
    family: evs.volumeType || "SSD",
    tier: evs.key,
    billing_mode: "on_demand_monthly",
    unit: "GB-month",
    price: Math.round(evs.monthlyEquivalentUsdPerGb * 10000) / 10000,
    currency: "USD",
    source_url: "https://www.huaweicloud.com/intl/en-us/product/evs.html",
    captured_at: new Date().toISOString(),
    raw_attributes: {
      key: evs.key,
      label: evs.label,
      resourceSpecCode: evs.resourceSpecCode,
      hourlyUsdPerGb: evs.hourlyUsdPerGb,
      monthlyUsdPerGb: evs.monthlyUsdPerGb,
      yearlyUsdPerGb: evs.yearlyUsdPerGb,
      monthlyEquivalentUsdPerGb: evs.monthlyEquivalentUsdPerGb,
    },
    confirmed: true,
    status: "confirmed",
    capture_error: null,
  }));
}

async function main() {
  const source = await fs.readFile(sourcePath, "utf8");
  const script = new vm.Script(transpileCatalogSource(source), { filename: sourcePath });
  const context = vm.createContext({ module: { exports: {} }, exports: {} });
  script.runInContext(context);
  const { pricingCatalog } = context.module.exports;

  // Read existing flexible catalog to preserve non-ECS/EVS items
  let existingItems = [];
  try {
    const existing = JSON.parse(await fs.readFile(outputPath, "utf8"));
    existingItems = existing.items.filter((item) => item.product !== "ECS" && item.product !== "EVS");
  } catch {
    // File doesn't exist yet, start fresh
  }

  // Convert ECS/EVS from TS catalog
  const ecsItems = [];
  const evsItems = [];
  for (const [region, catalog] of Object.entries(pricingCatalog)) {
    ecsItems.push(...convertEcsItems(region, catalog.ecs));
    evsItems.push(...convertEvsItems(region, catalog.evs));
  }

  const allItems = [...ecsItems, ...evsItems, ...existingItems];
  allItems.sort((a, b) => a.product.localeCompare(b.product) || a.region.localeCompare(b.region) || a.sku.localeCompare(b.sku));

  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  await fs.writeFile(
    outputPath,
    JSON.stringify(
      {
        generated_at: new Date().toISOString(),
        items: allItems,
      },
      null,
      2,
    ),
  );

  console.log(`Wrote ${outputPath} (${allItems.length} items: ${ecsItems.length} ECS, ${evsItems.length} EVS, ${existingItems.length} other)`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
