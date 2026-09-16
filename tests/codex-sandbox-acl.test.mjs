import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const taskScript = join(repoRoot, "tools", "codex-sandbox-maintenance-task.ps1");
const taskWrapper = join(repoRoot, "tools", "codex-sandbox-maintenance-task.cmd");
const cleaner = join(repoRoot, "tools", "codex-sandbox-acl.ps1");
const gitIgnoreSync = join(repoRoot, "tools", "sync-codex-git-ignore.ps1");
const updateGuard = join(repoRoot, "tools", "maintain-codex-sandbox-after-updates.ps1");

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

test("update guard validates once and repeats after an environment update", () => {
  const fixture = mkdtempSync(join(tmpdir(), "codex-update-guard-"));
  const state = join(fixture, "state.json");
  const config = join(fixture, "config.toml");
  const ruleSource = join(fixture, "managed.rules");
  const ruleDestination = join(fixture, "home", "managed.rules");
  const regressionCount = join(fixture, "regression-count.txt");
  const regression = join(fixture, "regression.ps1");
  try {
    writeFileSync(config, [
      'approval_policy = "on-request"',
      'default_permissions = ":workspace"',
      'approvals_reviewer = "auto_review"',
      "",
    ].join("\n"), "utf8");
    writeFileSync(ruleSource, 'prefix_rule(pattern = ["git", "push"], decision = "prompt")\n', "utf8");
    writeFileSync(regression, [
      "param([string]$CountPath)",
      "$count = if (Test-Path -LiteralPath $CountPath) { [int](Get-Content -LiteralPath $CountPath -Raw) } else { 0 }",
      "Set-Content -LiteralPath $CountPath -Value ($count + 1)",
      "exit 0",
      "",
    ].join("\n"), "utf8");

    const run = (codexVersion) => spawnSync("pwsh", [
      "-NoProfile", "-File", updateGuard,
      "-StatePath", state,
      "-ConfigPath", config,
      "-RuleSourcePath", ruleSource,
      "-RuleDestinationPath", ruleDestination,
      "-RegressionScriptPath", regression,
      "-RegressionArgument", regressionCount,
      "-CodexVersionOverride", codexVersion,
      "-WindowsVersionOverride", "26100.8875",
    ], { encoding: "utf8" });

    const first = run("codex-cli 1.0.0");
    assert.equal(first.status, 0, first.stdout + first.stderr);
    assert.equal(readFileSync(regressionCount, "utf8").trim(), "1");
    assert.equal(readFileSync(ruleDestination, "utf8"), readFileSync(ruleSource, "utf8"));

    const unchanged = run("codex-cli 1.0.0");
    assert.equal(unchanged.status, 0, unchanged.stdout + unchanged.stderr);
    assert.equal(readFileSync(regressionCount, "utf8").trim(), "1");

    const expiredState = JSON.parse(readFileSync(state, "utf8"));
    expiredState.lastValidated.validatedAtUtc = "2000-01-01T00:00:00.000Z";
    writeFileSync(state, JSON.stringify(expiredState), "utf8");
    const expired = run("codex-cli 1.0.0");
    assert.equal(expired.status, 0, expired.stdout + expired.stderr);
    assert.equal(readFileSync(regressionCount, "utf8").trim(), "2");

    const updated = run("codex-cli 1.1.0");
    assert.equal(updated.status, 0, updated.stdout + updated.stderr);
    assert.equal(readFileSync(regressionCount, "utf8").trim(), "3");
    const saved = JSON.parse(readFileSync(state, "utf8"));
    assert.equal(saved.lastValidated.codexVersion, "codex-cli 1.1.0");
    assert.equal(saved.lastValidated.windowsVersion, "26100.8875");
    assert.equal(saved.healthy, true);
  } finally {
    rmSync(fixture, { recursive: true, force: true });
  }
});

test("update guard keeps the previous validated version when regression fails", () => {
  const fixture = mkdtempSync(join(tmpdir(), "codex-update-failure-"));
  const state = join(fixture, "state.json");
  const config = join(fixture, "config.toml");
  const ruleSource = join(fixture, "managed.rules");
  const ruleDestination = join(fixture, "home", "managed.rules");
  const regression = join(fixture, "regression.ps1");
  try {
    writeFileSync(config, 'approval_policy = "on-request"\ndefault_permissions = ":workspace"\napprovals_reviewer = "auto_review"\n', "utf8");
    writeFileSync(ruleSource, 'prefix_rule(pattern = ["git", "push"], decision = "prompt")\n', "utf8");
    writeFileSync(regression, "exit 1\n", "utf8");
    writeFileSync(state, JSON.stringify({ healthy: true, lastValidated: { codexVersion: "codex-cli 1.0.0", windowsVersion: "26100.8000" } }), "utf8");

    const result = spawnSync("pwsh", [
      "-NoProfile", "-File", updateGuard,
      "-StatePath", state,
      "-ConfigPath", config,
      "-RuleSourcePath", ruleSource,
      "-RuleDestinationPath", ruleDestination,
      "-RegressionScriptPath", regression,
      "-CodexVersionOverride", "codex-cli 1.1.0",
      "-WindowsVersionOverride", "26100.8875",
    ], { encoding: "utf8" });

    assert.notEqual(result.status, 0, result.stdout + result.stderr);
    const saved = JSON.parse(readFileSync(state, "utf8"));
    assert.equal(saved.lastValidated.codexVersion, "codex-cli 1.0.0");
    assert.equal(saved.healthy, false);
  } finally {
    rmSync(fixture, { recursive: true, force: true });
  }
});

test("update guard reports config drift without overwriting user config", () => {
  const fixture = mkdtempSync(join(tmpdir(), "codex-config-drift-"));
  const state = join(fixture, "state.json");
  const config = join(fixture, "config.toml");
  const ruleSource = join(fixture, "managed.rules");
  const ruleDestination = join(fixture, "home", "managed.rules");
  const regression = join(fixture, "regression.ps1");
  const originalConfig = 'approval_policy = "never"\ndefault_permissions = ":workspace"\napprovals_reviewer = "auto_review"\n';
  try {
    writeFileSync(config, originalConfig, "utf8");
    writeFileSync(ruleSource, 'prefix_rule(pattern = ["git", "push"], decision = "prompt")\n', "utf8");
    writeFileSync(regression, "exit 0\n", "utf8");

    const result = spawnSync("pwsh", [
      "-NoProfile", "-File", updateGuard,
      "-StatePath", state,
      "-ConfigPath", config,
      "-RuleSourcePath", ruleSource,
      "-RuleDestinationPath", ruleDestination,
      "-RegressionScriptPath", regression,
      "-CodexVersionOverride", "codex-cli 1.0.0",
      "-WindowsVersionOverride", "26100.8875",
    ], { encoding: "utf8" });

    assert.equal(result.status, 10, result.stdout + result.stderr);
    assert.equal(readFileSync(config, "utf8"), originalConfig);
    assert.equal(JSON.parse(readFileSync(state, "utf8")).healthy, false);
  } finally {
    rmSync(fixture, { recursive: true, force: true });
  }
});

test("update guard records operational failures as unhealthy", () => {
  const fixture = mkdtempSync(join(tmpdir(), "codex-operational-failure-"));
  const state = join(fixture, "state.json");
  const config = join(fixture, "config.toml");
  const missingRule = join(fixture, "missing.rules");
  try {
    writeFileSync(config, 'approval_policy = "on-request"\ndefault_permissions = ":workspace"\napprovals_reviewer = "auto_review"\n', "utf8");
    const result = spawnSync("pwsh", [
      "-NoProfile", "-File", updateGuard,
      "-StatePath", state,
      "-ConfigPath", config,
      "-RuleSourcePath", missingRule,
      "-RuleDestinationPath", join(fixture, "home", "managed.rules"),
      "-CodexVersionOverride", "codex-cli 1.0.0",
      "-WindowsVersionOverride", "26100.8875",
    ], { encoding: "utf8" });

    assert.equal(result.status, 20, result.stdout + result.stderr);
    const saved = JSON.parse(readFileSync(state, "utf8"));
    assert.equal(saved.healthy, false);
    assert.equal(saved.checks.operational, false);
  } finally {
    rmSync(fixture, { recursive: true, force: true });
  }
});
