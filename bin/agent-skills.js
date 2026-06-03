#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const packageRoot = path.resolve(__dirname, "..");
const packageJson = require(path.join(packageRoot, "package.json"));
const skillsRoot = path.join(packageRoot, ".agents", "skills");
const tapdCommands = new Set(["list", "get", "image", "attachment"]);

main(process.argv.slice(2));

function main(argv) {
  const invokedAs = path.basename(process.argv[1] || "", ".js");

  if (invokedAs === "tapd-bug-autofix" || invokedAs === "tapd-bugs") {
    runTapdLegacy(argv);
    return;
  }

  const command = argv[0];

  if (!command || command === "help" || command === "-h" || command === "--help") {
    printHelp();
    return;
  }

  if (command === "version" || command === "-v" || command === "--version") {
    console.log(packageJson.version);
    return;
  }

  if (command === "list") {
    listSkills();
    return;
  }

  if (command === "install" || command === "update") {
    installSkills(command, argv.slice(1));
    return;
  }

  if (command === "where") {
    printLocations(argv.slice(1));
    return;
  }

  if (command === "run") {
    runSkill(argv.slice(1));
    return;
  }

  if (isSkillName(command)) {
    runSkill(argv);
    return;
  }

  fail(`Unknown command: ${command}`);
}

function runTapdLegacy(argv) {
  const command = argv[0];

  if (!command || command === "help" || command === "-h" || command === "--help") {
    printTapdHelp("tapd-bug-autofix");
    return;
  }

  if (command === "version" || command === "-v" || command === "--version") {
    console.log(packageJson.version);
    return;
  }

  if (command === "install" || command === "update") {
    installSkills(command, ["tapd-bug-autofix", ...argv.slice(1)]);
    return;
  }

  if (command === "where") {
    printLocations(["tapd-bug-autofix", ...argv.slice(1)]);
    return;
  }

  if (command === "bugs") {
    runTapdScript(argv.slice(1));
    return;
  }

  if (tapdCommands.has(command)) {
    runTapdScript(argv);
    return;
  }

  fail(`Unknown tapd-bug-autofix command: ${command}`);
}

function listSkills() {
  const skills = getAvailableSkills();

  if (skills.length === 0) {
    console.log("No packaged skills found.");
    return;
  }

  for (const skill of skills) {
    const metadata = readSkillMetadata(skill);
    const suffix = metadata.description ? ` - ${metadata.description}` : "";
    console.log(`${skill}${suffix}`);
  }
}

function installSkills(mode, args) {
  const options = parseInstallOptions(args);

  if (options.help) {
    printInstallHelp(mode);
    return;
  }

  const skills = resolveSkillSelection(options.skill);
  const targetRoot = path.resolve(options.target);

  if (!fs.existsSync(targetRoot) || !fs.statSync(targetRoot).isDirectory()) {
    fail(`Target directory does not exist: ${targetRoot}`);
  }

  for (const skillName of skills) {
    installOneSkill(mode, skillName, targetRoot, options);
  }
}

function installOneSkill(mode, skillName, targetRoot, options) {
  const source = getSkillSource(skillName);
  const destination = path.join(targetRoot, ".agents", "skills", skillName);
  const exists = fs.existsSync(destination);

  if (mode === "install" && exists && !options.force) {
    fail(
      `Skill already exists at ${destination}\n` +
        `Run "agent-skills update ${skillName}" to refresh it, or "agent-skills install ${skillName} --force" to overwrite package-managed files.`
    );
  }

  if (!options.dryRun) {
    fs.mkdirSync(path.dirname(destination), { recursive: true });
    fs.cpSync(source, destination, {
      recursive: true,
      force: true,
      errorOnExist: false,
    });
  }

  const dryRunAction = mode === "update" || exists ? "Would update" : "Would install";
  const action = exists ? "Updated" : "Installed";
  console.log(`${options.dryRun ? dryRunAction : action} ${skillName} at ${destination}`);
}

function parseInstallOptions(args) {
  const options = {
    skill: null,
    target: process.cwd(),
    force: false,
    dryRun: false,
    help: false,
  };

  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];

    if (arg === "--help" || arg === "-h") {
      options.help = true;
      continue;
    }

    if (arg === "--force" || arg === "-f") {
      options.force = true;
      continue;
    }

    if (arg === "--dry-run") {
      options.dryRun = true;
      continue;
    }

    if (arg === "--target" || arg === "-t") {
      const value = args[index + 1];
      if (!value) {
        fail(`Missing value for ${arg}`);
      }
      options.target = value;
      index += 1;
      continue;
    }

    if (arg.startsWith("--target=")) {
      options.target = arg.slice("--target=".length);
      continue;
    }

    if (arg.startsWith("-")) {
      fail(`Unknown option for install/update: ${arg}`);
    }

    if (options.skill) {
      fail(`Unexpected argument: ${arg}`);
    }

    options.skill = arg;
  }

  return options;
}

function printLocations(args) {
  const options = parseWhereOptions(args);
  const targetRoot = path.resolve(options.target);
  const skills = options.skill ? [options.skill] : getAvailableSkills();

  for (const skillName of skills) {
    const source = getSkillSource(skillName);
    console.log(`${skillName}`);
    console.log(`  Package skill: ${source}`);
    console.log(`  Target skill:  ${path.join(targetRoot, ".agents", "skills", skillName)}`);

    if (skillName === "tapd-bug-autofix") {
      console.log(`  Python helper: ${getTapdScript()}`);
    }
  }
}

function parseWhereOptions(args) {
  const options = {
    skill: null,
    target: process.cwd(),
  };

  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];

    if (arg === "--target" || arg === "-t") {
      const value = args[index + 1];
      if (!value) {
        fail(`Missing value for ${arg}`);
      }
      options.target = value;
      index += 1;
      continue;
    }

    if (arg.startsWith("--target=")) {
      options.target = arg.slice("--target=".length);
      continue;
    }

    if (arg.startsWith("-")) {
      fail(`Unknown option for where: ${arg}`);
    }

    if (options.skill) {
      fail(`Unexpected argument: ${arg}`);
    }

    options.skill = arg;
  }

  return options;
}

function runSkill(args) {
  const skillName = args[0];
  const skillArgs = args.slice(1);

  if (!skillName) {
    fail("Missing skill name. Usage: agent-skills run <skill> <command> [args...]");
  }

  getSkillSource(skillName);

  if (skillName === "tapd-bug-autofix") {
    const command = skillArgs[0];

    if (!command || command === "help" || command === "-h" || command === "--help") {
      printTapdHelp(`agent-skills ${skillName}`);
      return;
    }

    if (command === "bugs") {
      runTapdScript(skillArgs.slice(1));
      return;
    }

    if (tapdCommands.has(command)) {
      runTapdScript(skillArgs);
      return;
    }
  }

  fail(`Skill ${skillName} does not expose a runnable command for: ${skillArgs.join(" ")}`);
}

function runTapdScript(args) {
  const tapdScript = getTapdScript();

  if (!fs.existsSync(tapdScript)) {
    fail(`TAPD helper script is missing: ${tapdScript}`);
  }

  const python = findPython();
  if (!python) {
    fail("Python was not found. Install Python 3 or set the PYTHON environment variable.");
  }

  const result = spawnSync(python.command, [...python.prefixArgs, tapdScript, ...args], {
    cwd: process.cwd(),
    env: process.env,
    stdio: "inherit",
  });

  if (result.error) {
    fail(`Failed to run Python: ${result.error.message}`);
  }

  process.exit(result.status == null ? 1 : result.status);
}

function getTapdScript() {
  return path.join(getSkillSource("tapd-bug-autofix"), "scripts", "tapd_bugs.py");
}

function findPython() {
  const candidates = [];

  if (process.env.PYTHON) {
    candidates.push({ command: process.env.PYTHON, prefixArgs: [] });
  }

  if (process.platform === "win32") {
    candidates.push({ command: "py", prefixArgs: ["-3"] });
  }

  candidates.push({ command: "python3", prefixArgs: [] });
  candidates.push({ command: "python", prefixArgs: [] });

  for (const candidate of candidates) {
    const check = spawnSync(candidate.command, [...candidate.prefixArgs, "--version"], {
      stdio: "ignore",
    });

    if (!check.error && check.status === 0) {
      return candidate;
    }
  }

  return null;
}

function resolveSkillSelection(skillName) {
  if (!skillName || skillName === "all") {
    const skills = getAvailableSkills();

    if (skills.length === 0) {
      fail("No packaged skills found.");
    }

    return skills;
  }

  getSkillSource(skillName);
  return [skillName];
}

function getAvailableSkills() {
  if (!fs.existsSync(skillsRoot)) {
    return [];
  }

  return fs
    .readdirSync(skillsRoot, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();
}

function isSkillName(name) {
  return getAvailableSkills().includes(name);
}

function getSkillSource(skillName) {
  const source = path.join(skillsRoot, skillName);

  if (!fs.existsSync(source) || !fs.statSync(source).isDirectory()) {
    fail(`Unknown packaged skill: ${skillName}`);
  }

  return source;
}

function readSkillMetadata(skillName) {
  const skillPath = path.join(getSkillSource(skillName), "SKILL.md");

  if (!fs.existsSync(skillPath)) {
    return {};
  }

  const content = fs.readFileSync(skillPath, "utf8");
  const match = content.match(/^---\r?\n([\s\S]*?)\r?\n---/);

  if (!match) {
    return {};
  }

  const metadata = {};

  for (const line of match[1].split(/\r?\n/)) {
    const separator = line.indexOf(":");

    if (separator === -1) {
      continue;
    }

    const key = line.slice(0, separator).trim();
    const value = line.slice(separator + 1).trim();

    if (key) {
      metadata[key] = value;
    }
  }

  return metadata;
}

function printHelp() {
  console.log(`agent-skills ${packageJson.version}

Usage:
  agent-skills list
  agent-skills install [skill|all] [--target <dir>] [--force]
  agent-skills update [skill|all] [--target <dir>]
  agent-skills where [skill] [--target <dir>]
  agent-skills run <skill> <command> [args...]

TAPD shortcuts:
  agent-skills tapd-bug-autofix list [TAPD options]
  agent-skills tapd-bug-autofix get --bug-id <id>
  agent-skills tapd-bug-autofix image --image-path <path-or-url>
  agent-skills tapd-bug-autofix attachment --attachment-id <id>

Examples:
  npx @piggyjoe/agent-skills list
  npx @piggyjoe/agent-skills install tapd-bug-autofix
  npx @piggyjoe/agent-skills update all
  npx @piggyjoe/agent-skills tapd-bug-autofix list --limit 20
`);
}

function printTapdHelp(commandPrefix) {
  console.log(`${commandPrefix} ${packageJson.version}

Usage:
  ${commandPrefix} list [TAPD options]
  ${commandPrefix} get --bug-id <id> [--workspace-id <id>]
  ${commandPrefix} image --image-path <path-or-url> [--workspace-id <id>]
  ${commandPrefix} attachment --attachment-id <id> [--workspace-id <id>]

Examples:
  ${commandPrefix} list --status "new|in_progress|reopened" --limit 20
  ${commandPrefix} get --bug-id 1010158231500628817
`);
}

function printInstallHelp(mode) {
  console.log(`agent-skills ${mode}

Usage:
  agent-skills ${mode} [skill|all] [--target <dir>] [--force] [--dry-run]

Options:
  --target, -t   Project directory that should receive .agents/skills/<skill>
  --force, -f    Overwrite package-managed files during install
  --dry-run      Print destinations without copying files
`);
}

function fail(message) {
  console.error(`ERROR: ${message}`);
  process.exit(1);
}
