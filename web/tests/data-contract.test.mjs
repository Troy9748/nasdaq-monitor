import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const readJson = async (name) => JSON.parse(await readFile(new URL(`../public/data/${name}`, import.meta.url), "utf8"));

test("generated data satisfies the dashboard contract", async () => {
  const [market, context, analysis] = await Promise.all([
    readJson("nasdaq100.json"),
    readJson("context.json"),
    readJson("analysis.json"),
  ]);

  assert.equal(market.latest_date, market.summary.market_date);
  assert.ok(["normal", "watch", "important", "critical"].includes(market.summary.alert.code));
  assert.ok(market.regime_analysis.stats["多头"].forward["60日"].samples > 0);
  assert.equal(context.series.at(-1).date, market.latest_date);
  assert.equal(analysis.market_date, market.latest_date);
});
