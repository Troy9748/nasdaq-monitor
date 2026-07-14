import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import test from "node:test";

test("GitHub Pages output uses the repository base path and ships data", async () => {
  const output = new URL("../out/", import.meta.url);
  const index = await readFile(new URL("index.html", output), "utf8");
  const appChunksUrl = new URL("_next/static/chunks/app/", output);
  const chunks = await readdir(appChunksUrl, { recursive: true });
  const pageChunk = chunks.find((name) => name.startsWith("page-"));
  assert.ok(pageChunk);
  const script = await readFile(new URL(pageChunk, appChunksUrl), "utf8");
  const appScripts = (await Promise.all(chunks.filter((name) => name.endsWith(".js")).map((name) => readFile(new URL(name, appChunksUrl), "utf8")))).join("\n");

  assert.match(index, /\/nasdaq-monitor\/favicon\.svg/);
  assert.match(script, /\/nasdaq-monitor/);
  assert.match(appScripts, /funds\.html\?sector=/);
  assert.match(appScripts, /fund\.html\?code=/);
  await assert.doesNotReject(() => readFile(new URL("data/nasdaq100.json", output)));
  await assert.doesNotReject(() => readFile(new URL("sectors.html", output)));
  await assert.doesNotReject(() => readFile(new URL("funds.html", output)));
  await assert.doesNotReject(() => readFile(new URL("fund.html", output)));
  await assert.doesNotReject(() => readFile(new URL("data/sectors.json", output)));
  await assert.doesNotReject(() => readFile(new URL("data/funds.json", output)));
});
