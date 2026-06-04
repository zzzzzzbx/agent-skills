# agent-skills

Packaged Codex agent skills with one npm CLI for installation, updates, and helper commands.

## Use with npx

List packaged skills:

```bash
npx @piggyjoe/agent-skills list
```

Install or update one skill in the current project:

```bash
npx @piggyjoe/agent-skills install tapd-bug-autofix
npx @piggyjoe/agent-skills update tapd-bug-autofix
```

Install or update every packaged skill:

```bash
npx @piggyjoe/agent-skills install all
npx @piggyjoe/agent-skills update all
```

Run the TAPD helper directly:

```bash
npx @piggyjoe/agent-skills tapd-bug-autofix list --limit 20
npx @piggyjoe/agent-skills tapd-bug-autofix get --bug-id "<TAPD_BUG_ID>" --with-comments
npx @piggyjoe/agent-skills tapd-bug-autofix comments --bug-id "<TAPD_BUG_ID>"
npx @piggyjoe/agent-skills tapd-bug-autofix workflow init
npx @piggyjoe/agent-skills tapd-bug-autofix transition --bug-id "<TAPD_BUG_ID>" --to accept
npx @piggyjoe/agent-skills tapd-bug-autofix image --image-path "<IMAGE_PATH_OR_IMAGE_URL>"
npx @piggyjoe/agent-skills tapd-bug-autofix attachment --attachment-id "<ATTACHMENT_ID>"
```

The old single-skill binaries are kept as compatibility aliases after installing the package. With `npx`, use `-p @piggyjoe/agent-skills` when calling an alias:

```bash
npx -p @piggyjoe/agent-skills tapd-bug-autofix list --limit 20
npx -p @piggyjoe/agent-skills tapd-bug-autofix install
```

## Skills

Packaged skills live under:

```text
.agents/
  skills/
    tapd-bug-autofix/
      SKILL.md
      scripts/
```

Adding another skill means adding another folder under `.agents/skills/`. The CLI discovers packaged skills from that directory.

## TAPD Credentials

Create a `.env` file in the target project:

```env
TAPD_WORKSPACE_ID=your_workspace_id
TAPD_ACCESS_TOKEN=your_access_token
```

or:

```env
TAPD_WORKSPACE_ID=your_workspace_id
TAPD_API_USER=your_api_user
TAPD_API_PASSWORD=your_api_password
```

Do not commit `.env`.

## TAPD Workflow

Create a project-level workflow config:

```bash
npx @piggyjoe/agent-skills tapd-bug-autofix workflow init
```

This creates:

```text
.agents/tapd-bug-autofix.workflow.json
```

Commit this file in the target project when every agent should follow the same TAPD flow. The default template reads bugs in `新|重新打开`, includes comments, and defines these transitions:

```bash
npx @piggyjoe/agent-skills tapd-bug-autofix list --workflow --limit 20
npx @piggyjoe/agent-skills tapd-bug-autofix transition --bug-id "<TAPD_BUG_ID>" --to accept
npx @piggyjoe/agent-skills tapd-bug-autofix transition --bug-id "<TAPD_BUG_ID>" --to ready_for_release
npx @piggyjoe/agent-skills tapd-bug-autofix transition --bug-id "<TAPD_BUG_ID>" --to resolved
```

For a direct status update:

```bash
npx @piggyjoe/agent-skills tapd-bug-autofix status --bug-id "<TAPD_BUG_ID>" --v-status "待发布"
```

## Local Development

Run the local CLI:

```bash
node bin/agent-skills.js --help
node bin/agent-skills.js list
node bin/agent-skills.js install tapd-bug-autofix --target .
node bin/agent-skills.js tapd-bug-autofix list --limit 5
```

Check package contents:

```bash
npm pack --dry-run
```

## Release Flow

1. Update `package.json` version.
2. Run `npm pack --dry-run`.
3. Commit and tag the release.
4. Publish with `npm publish`.

For GitHub:

```bash
git add .
git commit -m "Initial agent-skills package"
gh repo create agent-skills --source . --private --push
```
