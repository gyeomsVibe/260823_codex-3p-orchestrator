import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const taskScript = join(repoRoot, "tools", "codex-sandbox-acl-task.ps1");
const cleaner = join(repoRoot, "tools", "codex-sandbox-acl.ps1");

test("scheduled task audits ACLs without deleting entries", () => {
  const source = readFileSync(taskScript, "utf8");
  assert.match(source, /&\s+\$cleaner\s+-Mode\s+Check\b/);
  assert.doesNotMatch(source, /&\s+\$cleaner\s+-Mode\s+Clean\b/);
});

test("ACL auditor contains no mutation primitive", () => {
  const source = readFileSync(cleaner, "utf8");
  assert.doesNotMatch(source, /\bSet-Acl\b/i);
  assert.doesNotMatch(source, /\bRemoveAccessRule/i);
  assert.doesNotMatch(source, /\bicacls(?:\.exe)?\b/i);
});

test("legacy Clean mode refuses to mutate ACLs", () => {
  const fixture = mkdtempSync(join(tmpdir(), "codex-acl-safety-"));
  try {
    const before = execFileSync("pwsh", [
      "-NoProfile",
      "-Command",
      `(Get-Acl -LiteralPath '${fixture.replaceAll("'", "''")}').Sddl`,
    ], { encoding: "utf8" }).trim();

    const result = spawnSync("pwsh", [
      "-NoProfile",
      "-File",
      cleaner,
      "-Mode",
      "Clean",
      "-Paths",
      fixture,
    ], { encoding: "utf8" });

    const after = execFileSync("pwsh", [
      "-NoProfile",
      "-Command",
      `(Get-Acl -LiteralPath '${fixture.replaceAll("'", "''")}').Sddl`,
    ], { encoding: "utf8" }).trim();

    assert.equal(result.status, 3, result.stdout + result.stderr);
    assert.match(result.stdout + result.stderr, /automatic ACL cleanup is retired/i);
    assert.equal(after, before);
  } finally {
    rmSync(fixture, { recursive: true, force: true });
  }
});
