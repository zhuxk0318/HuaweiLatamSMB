import fs from "node:fs/promises";
import path from "node:path";
import vm from "node:vm";

const siteRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const sourcePath = path.join(siteRoot, "src/data/pricingCatalog.ts");
const outputPath = path.resolve(siteRoot, "./quote-agent/data/pricing-pricebook.json");

function transpileCatalogSource(source) {
  return source
    .replace(/^export type .*$/gm, "")
    .replace(/^export const HOURS_PER_MONTH =/m, "const HOURS_PER_MONTH =")
    .replace(/^export const pricingCatalog =/m, "const pricingCatalog =")
    .replace(/^export const pricingMetadata =/m, "const pricingMetadata =")
    .replace(/ as const;/g, ";")
    .concat("\nmodule.exports = { pricingCatalog, pricingMetadata };\n");
}

async function main() {
  const source = await fs.readFile(sourcePath, "utf8");
  const script = new vm.Script(transpileCatalogSource(source), { filename: sourcePath });
  const context = vm.createContext({ module: { exports: {} }, exports: {} });
  script.runInContext(context);
  const { pricingCatalog, pricingMetadata } = context.module.exports;

  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  await fs.writeFile(
    outputPath,
    JSON.stringify(
      {
        pricingCatalog,
        pricingMetadata,
        exportedAt: new Date().toISOString(),
        sourceFile: sourcePath,
      },
      null,
      2,
    ),
  );

  console.log(`Wrote ${outputPath}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
