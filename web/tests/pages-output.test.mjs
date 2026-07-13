import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import test from "node:test";

test("GitHub Pages output uses the repository base path and ships data", async () => {
  const output = new URL("../out/", import.meta.url);
  const index = await readFile(new URL("index.html", output), "utf8");
  const chunks = await readdir(new URL("_next/static/chunks/app/", output));
  const pageChunk = chunks.find((name) => name.startsWith("page-"));
  assert.ok(pageChunk);
  const script = await readFile(new URL(`_next/static/chunks/app/${pageChunk}`, output), "utf8");

  assert.match(index, /\/nasdaq-monitor\/favicon\.svg/);
  assert.match(script, /\/nasdaq-monitor/);
  await assert.doesNotReject(() => readFile(new URL("data/nasdaq100.json", output)));
});
