import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const taskScript = join(repoRoot, "tools", "codex-sandbox-acl-task.ps1");
const taskWrapper = join(repoRoot, "tools", "codex-sandbox-acl-task.cmd");
const cleaner = join(repoRoot, "tools", "codex-sandbox-acl.ps1");
const gitIgnoreSync = join(repoRoot, "tools", "sync-codex-git-ignore.ps1");

test("scheduled task audits ACLs without deleting entries", () => {
  const source = readFileSync(taskScript, "utf8");
  assert.match(source, /&\s+\$cleaner\s+-Mode\s+Check\b/);
  assert.doesNotMatch(source, /&\s+\$cleaner\s+-Mode\s+Clean\b/);
});

test("scheduled task wrapper preserves the PowerShell exit code", () => {
  const source = readFileSync(taskWrapper, "utf8");
  assert.match(source, /set\s+"TASK_EXIT=%ERRORLEVEL%"/i);
  assert.match(source, /exit\s+\/b\s+%TASK_EXIT%/i);
});

test("ACL auditor contains no mutation primitive", () => {
  const source = readFileSync(cleaner, "utf8");
  assert.doesNotMatch(source, /\bSet-Acl\b/i);
  assert.doesNotMatch(source, /\bRemoveAccessRule/i);
  assert.doesNotMatch(source, /\bicacls(?:\.exe)?\b/i);
});

test("ACL findings are audit data rather than a task failure", () => {
  const fixture = mkdtempSync(join(tmpdir(), "codex-acl-audit-"));
  try {
    const result = spawnSync("pwsh", [
      "-NoProfile",
      "-File",
      cleaner,
      "-Mode",
      "Check",
      "-Paths",
      fixture,
    ], { encoding: "utf8" });

    assert.equal(result.status, 0, result.stdout + result.stderr);
  } finally {
    rmSync(fixture, { recursive: true, force: true });
  }
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

test("Git ignore support file self-heals without copying Git credentials", () => {
  const fixture = mkdtempSync(join(tmpdir(), "codex-git-ignore-"));
  const source = join(fixture, "source-ignore");
  const destination = join(fixture, "support", "ignore");
  try {
    writeFileSync(source, "*.local\n", "utf8");
    execFileSync("pwsh", [
      "-NoProfile",
      "-File",
      gitIgnoreSync,
      "-SourcePath",
      source,
      "-DestinationPath",
      destination,
    ]);
    assert.equal(readFileSync(destination, "utf8"), "*.local\n");

    writeFileSync(source, "*.cache\n", "utf8");
    execFileSync("pwsh", [
      "-NoProfile",
      "-File",
      gitIgnoreSync,
      "-SourcePath",
      source,
      "-DestinationPath",
      destination,
    ]);
    assert.equal(readFileSync(destination, "utf8"), "*.cache\n");
  } finally {
    rmSync(fixture, { recursive: true, force: true });
  }
});
