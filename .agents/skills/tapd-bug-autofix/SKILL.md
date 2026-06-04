---
name: tapd-bug-autofix
description: Use when Codex needs to read bugs or defects from TAPD, fetch TAPD comments, screenshots, or attachments, update TAPD defect status, follow a project TAPD bug workflow, analyze bug details, locate related code, implement fixes, run validation, and report results. Trigger on TAPD, bug, defect, workspace_id, TAPD_WORKSPACE_ID, screenshot, attachment, image, comments, status update, workflow, read TAPD bugs, autonomous bug fix, and Chinese requests about TAPD defect repair or status transitions.
---

# TAPD Bug Autofix

Use this skill to read TAPD bugs from the current project, inspect descriptions, comments, screenshots, and attachments, then fix matching issues in the repository.

The helper can update TAPD bug status. Only write status changes when the user explicitly asks, or when the project workflow config says to do so.

## Credentials

Load credentials from process environment variables or the project root `.env`.

Required workspace:

```env
TAPD_WORKSPACE_ID=your_workspace_id
```

Use one credential set:

```env
TAPD_ACCESS_TOKEN=your_access_token
```

or:

```env
TAPD_API_USER=your_api_user
TAPD_API_PASSWORD=your_api_password
```

Existing process environment variables take priority over `.env`.

Never hard-code TAPD credentials into source files, commits, logs, tests, or documentation. Ensure `.gitignore` contains `.env`.

## Commands

Prefer the npm CLI when available:

```bash
npx @piggyjoe/agent-skills tapd-bug-autofix list --limit 20
npx @piggyjoe/agent-skills tapd-bug-autofix get --bug-id "<TAPD_BUG_ID>" --with-comments
npx @piggyjoe/agent-skills tapd-bug-autofix comments --bug-id "<TAPD_BUG_ID>"
npx @piggyjoe/agent-skills tapd-bug-autofix workflow init
npx @piggyjoe/agent-skills tapd-bug-autofix list --workflow --limit 20
npx @piggyjoe/agent-skills tapd-bug-autofix transition --bug-id "<TAPD_BUG_ID>" --to accept
npx @piggyjoe/agent-skills tapd-bug-autofix status --bug-id "<TAPD_BUG_ID>" --v-status "待发布"
npx @piggyjoe/agent-skills tapd-bug-autofix image --image-path "<IMAGE_PATH_OR_IMAGE_URL>"
npx @piggyjoe/agent-skills tapd-bug-autofix attachment --attachment-id "<ATTACHMENT_ID>"
```

If the skill has already been installed into the project, the Python helper can also be run directly:

```bash
python .agents/skills/tapd-bug-autofix/scripts/tapd_bugs.py list --limit 20
python .agents/skills/tapd-bug-autofix/scripts/tapd_bugs.py get --bug-id "<TAPD_BUG_ID>" --with-comments
python .agents/skills/tapd-bug-autofix/scripts/tapd_bugs.py comments --bug-id "<TAPD_BUG_ID>"
python .agents/skills/tapd-bug-autofix/scripts/tapd_bugs.py workflow init
python .agents/skills/tapd-bug-autofix/scripts/tapd_bugs.py list --workflow --limit 20
python .agents/skills/tapd-bug-autofix/scripts/tapd_bugs.py transition --bug-id "<TAPD_BUG_ID>" --to accept
python .agents/skills/tapd-bug-autofix/scripts/tapd_bugs.py status --bug-id "<TAPD_BUG_ID>" --v-status "待发布"
python .agents/skills/tapd-bug-autofix/scripts/tapd_bugs.py image --image-path "<IMAGE_PATH_OR_IMAGE_URL>"
python .agents/skills/tapd-bug-autofix/scripts/tapd_bugs.py attachment --attachment-id "<ATTACHMENT_ID>"
```

Useful filters for `list`:

```bash
npx @piggyjoe/agent-skills tapd-bug-autofix list --status "new|in_progress|reopened" --limit 20
npx @piggyjoe/agent-skills tapd-bug-autofix list --status "new|in_progress|reopened" --with-comments --comments-limit 20 --limit 10
npx @piggyjoe/agent-skills tapd-bug-autofix list --owner "zhangsan" --limit 10
npx @piggyjoe/agent-skills tapd-bug-autofix list --title "login failed" --limit 10
npx @piggyjoe/agent-skills tapd-bug-autofix list --severity "fatal" --limit 10
npx @piggyjoe/agent-skills tapd-bug-autofix list --priority "high" --limit 10
npx @piggyjoe/agent-skills tapd-bug-autofix list --module "checkout" --limit 10
```

The helper calls these TAPD APIs:

- Bugs: `GET https://api.tapd.cn/bugs`
- Comments: `GET https://api.tapd.cn/comments` with `entry_type=bug|bug_remark` and `entry_id=<bug_id>`
- Status update: `POST https://api.tapd.cn/bugs` with `id`, `workspace_id`, and `status` or `v_status`
- Inline image download link: `GET https://api.tapd.cn/files/get_image`
- Attachment download link: `GET https://api.tapd.cn/attachments/down`

For inline TAPD images, pass the image path or full image URL to `image`. For attachment IDs, pass the ID to `attachment`. The returned `data.Attachment.download_url` is temporary; use it immediately and do not commit it.

## Project workflow

If the project has `.agents/tapd-bug-autofix.workflow.json`, all agents should follow it unless the user overrides the workflow in the current task.

Create the config from the project root:

```bash
npx @piggyjoe/agent-skills tapd-bug-autofix workflow init
```

Default flow:

- Read bugs with status `新|重新打开`.
- Include bug comments.
- After taking a bug, transition it with `transition --bug-id "<id>" --to accept`, which sets `v_status` to `接收/处理`.
- After the user accepts the fix, transition it with `--to ready_for_release`, which sets `v_status` to `待发布`.
- After release, the user may transition it with `--to resolved`, which sets `v_status` to `已解决`.

Read bugs using configured workflow defaults:

```bash
npx @piggyjoe/agent-skills tapd-bug-autofix list --workflow --limit 20
```

Before changing status, make sure the workflow matches the user's current request. Do not transition to `ready_for_release` or `resolved` unless the user explicitly says the fix has been accepted or released.

## Repair Workflow

For each selected bug:

1. Read the bug fields and comments. Prefer `list --workflow` for queue intake and `get --bug-id "<id>" --with-comments` for a selected bug, because important reproduction details may live in comments.
2. Extract inline image paths, image URLs, and attachment IDs from the bug description and comments.
3. If the project workflow instructs the agent to take ownership, transition the bug to the configured accept state before editing.
4. Fetch temporary download URLs with `image` or `attachment`, then inspect screenshots or files before making assumptions.
5. Convert the bug into a repair hypothesis: wrong behavior, expected behavior, likely files, reproduction signal, and missing evidence.
6. Search the repository for related code using title keywords, module names, routes, API names, error messages, stack traces, UI labels, field names, and screenshot text.
7. Inspect surrounding code before editing. Prefer the smallest safe fix and preserve project style.
8. Add or update targeted tests when practical.
9. Validate with targeted tests first, then lint/typecheck/build when available and reasonable.

When multiple bugs are returned, sort by priority/severity first, then modified time. Fix one bug at a time unless several bugs clearly share the same root cause.

Skip a bug when credentials are missing, screenshots are inaccessible, reproduction is unclear, or the related code cannot be found. Explain the blocker clearly.

## Output

After finishing, respond with:

```text
TAPD Bug Fix Report

Bug:
- ID:
- Title:
- Status:
- Priority/Severity:

Evidence:
- Description:
- Images/Attachments:
- Reproduction signal:

Root Cause:
-

Changes:
-

Validation:
-

Result:
-

Notes:
-
```
