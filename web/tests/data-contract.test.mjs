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

test("sector monitor exports eight usable core benchmarks", async () => {
  const [sectors, analysis] = await Promise.all([readJson("sectors.json"), readJson("sector_analysis.json")]);
  assert.equal(sectors.indices.length, 8);
  assert.equal(new Set(sectors.indices.map((item) => item.code)).size, 8);
  assert.ok(sectors.indices.every((item) => item.series.length > 200 && item.series.length <= 252));
  assert.ok(sectors.indices.every((item) => item.series.at(-1).date === item.latest_date));
  assert.ok(sectors.indices.every((item) => item.history_path && item.quality?.calendar));
  assert.ok(sectors.indices.filter((item) => /^9/.test(item.code)).every((item) => item.series.at(-1).money_flow_ratio_pct != null));
  const histories = await Promise.all(sectors.indices.map((item) => readJson(`sectors/${item.code}.json`)));
  assert.ok(histories.every((item) => item.series.length >= 500));
  assert.ok(histories.every((item, index) => item.series.at(-1).date === sectors.indices[index].latest_date));
  assert.equal(analysis.market_date, sectors.latest_a_share_date);
  assert.deepEqual(Object.keys(analysis.sections).sort(), ["confirmation", "next", "risks", "rotation", "today"]);
  assert.ok(Array.isArray(analysis.evidence));
});
