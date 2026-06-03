---
name: tapd-bug-autofix
description: Use when Codex needs to read bugs or defects from TAPD, fetch TAPD screenshots or attachments, analyze bug details, locate related code, implement fixes, run validation, and report results. Trigger on TAPD, bug, defect, workspace_id, TAPD_WORKSPACE_ID, screenshot, attachment, image, read TAPD bugs, autonomous bug fix, and Chinese requests about TAPD defect repair.
---

# TAPD Bug Autofix

Use this skill to read TAPD bugs from the current project, inspect descriptions, screenshots, and attachments, then fix matching issues in the repository.

The helper is read-only by default. Do not update TAPD bug status, assignees, or comments unless the user explicitly asks for write-back behavior.

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
npx @piggyjoe/agent-skills tapd-bug-autofix image --image-path "<IMAGE_PATH_OR_IMAGE_URL>"
npx @piggyjoe/agent-skills tapd-bug-autofix attachment --attachment-id "<ATTACHMENT_ID>"
```

If the skill has already been installed into the project, the Python helper can also be run directly:

```bash
python .agents/skills/tapd-bug-autofix/scripts/tapd_bugs.py list --limit 20
python .agents/skills/tapd-bug-autofix/scripts/tapd_bugs.py get --bug-id "<TAPD_BUG_ID>" --with-comments
python .agents/skills/tapd-bug-autofix/scripts/tapd_bugs.py comments --bug-id "<TAPD_BUG_ID>"
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
- Inline image download link: `GET https://api.tapd.cn/files/get_image`
- Attachment download link: `GET https://api.tapd.cn/attachments/down`

For inline TAPD images, pass the image path or full image URL to `image`. For attachment IDs, pass the ID to `attachment`. The returned `data.Attachment.download_url` is temporary; use it immediately and do not commit it.

## Repair Workflow

For each selected bug:

1. Read the bug fields and comments. Prefer `get --bug-id "<id>" --with-comments` for a selected bug, because important reproduction details may live in comments.
2. Extract inline image paths, image URLs, and attachment IDs from the bug description and comments.
3. Fetch temporary download URLs with `image` or `attachment`, then inspect screenshots or files before making assumptions.
4. Convert the bug into a repair hypothesis: wrong behavior, expected behavior, likely files, reproduction signal, and missing evidence.
5. Search the repository for related code using title keywords, module names, routes, API names, error messages, stack traces, UI labels, field names, and screenshot text.
6. Inspect surrounding code before editing. Prefer the smallest safe fix and preserve project style.
7. Add or update targeted tests when practical.
8. Validate with targeted tests first, then lint/typecheck/build when available and reasonable.

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
