#!/usr/bin/env python3
"""
Read TAPD bugs for Codex.

Auth priority:
1. TAPD_ACCESS_TOKEN as Bearer token
2. TAPD_API_USER + TAPD_API_PASSWORD as Basic Auth

This script automatically loads environment variables from a .env file.

Recommended project structure:

your-project/
  .env
  .gitignore
  .agents/
    skills/
      tapd-bug-autofix/
        SKILL.md
        scripts/
          tapd_bugs.py

.env example:

TAPD_WORKSPACE_ID=你的空间ID
TAPD_ACCESS_TOKEN=你的access_token

Or:

TAPD_WORKSPACE_ID=你的空间ID
TAPD_API_USER=你的api_user
TAPD_API_PASSWORD=你的api_password

Examples:

python .agents/skills/tapd-bug-autofix/scripts/tapd_bugs.py list \
  --status "new|in_progress|reopened" \
  --limit 20

python .agents/skills/tapd-bug-autofix/scripts/tapd_bugs.py get \
  --bug-id 1010158231500628817
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


TAPD_API_BASE = "https://api.tapd.cn"
DEFAULT_COMMENT_ENTRY_TYPE = "bug|bug_remark"


class TapdError(RuntimeError):
    pass


def load_dotenv() -> None:
    """
    Load environment variables from .env.

    Priority:
    - Existing environment variables are not overwritten.
    - First try current working directory: ./.env
    - Then search upward from this script's directory.

    This avoids needing python-dotenv as a dependency.
    """
    candidates: list[Path] = []

    cwd_env = Path.cwd() / ".env"
    candidates.append(cwd_env)

    script_dir = Path(__file__).resolve().parent
    for parent in [script_dir, *script_dir.parents]:
        candidates.append(parent / ".env")

    seen: set[Path] = set()

    for env_path in candidates:
        env_path = env_path.resolve()

        if env_path in seen:
            continue

        seen.add(env_path)

        if env_path.exists() and env_path.is_file():
            _load_dotenv_file(env_path)
            return


def _load_dotenv_file(env_path: Path) -> None:
    with env_path.open("r", encoding="utf-8") as file:
        for line_number, raw_line in enumerate(file, start=1):
            line = raw_line.strip()

            if not line:
                continue

            if line.startswith("#"):
                continue

            if line.startswith("export "):
                line = line[len("export "):].strip()

            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()

            if not key:
                continue

            value = _strip_inline_comment(value)
            value = _strip_quotes(value)

            # Do not overwrite real environment variables.
            os.environ.setdefault(key, value)


def _strip_inline_comment(value: str) -> str:
    """
    Strip inline comments for simple .env values.

    Supported:
    TAPD_WORKSPACE_ID=xxx # comment

    Not stripped inside quotes:
    TAPD_ACCESS_TOKEN="abc#def"
    """
    if not value:
        return value

    quote: str | None = None

    for index, char in enumerate(value):
        if char in {"'", '"'}:
            if quote is None:
                quote = char
            elif quote == char:
                quote = None
            continue

        if char == "#" and quote is None:
            before = value[:index]
            if before.endswith(" ") or before.endswith("\t"):
                return before.strip()

    return value.strip()


def _strip_quotes(value: str) -> str:
    if len(value) >= 2:
        if value[0] == value[-1] and value[0] in {"'", '"'}:
            return value[1:-1]
    return value


def _auth_headers() -> dict[str, str]:
    access_token = os.getenv("TAPD_ACCESS_TOKEN")
    api_user = os.getenv("TAPD_API_USER")
    api_password = os.getenv("TAPD_API_PASSWORD")

    headers = {
        "Accept": "application/json",
        "User-Agent": "codex-tapd-bug-autofix/1.0",
    }

    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
        return headers

    if api_user and api_password:
        raw = f"{api_user}:{api_password}".encode("utf-8")
        encoded = base64.b64encode(raw).decode("ascii")
        headers["Authorization"] = f"Basic {encoded}"
        return headers

    raise TapdError(
        "Missing TAPD credentials. Set TAPD_ACCESS_TOKEN, or set both "
        "TAPD_API_USER and TAPD_API_PASSWORD. You can put them in the project .env file."
    )


def _request_json(path: str, params: dict[str, Any]) -> dict[str, Any]:
    clean_params = {
        key: value
        for key, value in params.items()
        if value is not None and value != ""
    }

    query = urllib.parse.urlencode(clean_params)
    url = f"{TAPD_API_BASE}{path}?{query}"

    req = urllib.request.Request(
        url,
        headers=_auth_headers(),
        method="GET",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise TapdError(f"TAPD HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise TapdError(f"TAPD request failed: {exc}") from exc

    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise TapdError(f"TAPD returned non-JSON response: {body[:500]}") from exc

    # TAPD often returns:
    # {"status":1,"data":[...],"info":"success"}
    status = data.get("status")
    if status not in {1, "1", True, "true", "True"}:
        raise TapdError(
            "TAPD API error: "
            + json.dumps(data, ensure_ascii=False)[:1000]
        )

    return data


def _normalize_bug(item: dict[str, Any]) -> dict[str, Any]:
    bug = item.get("Bug", item)

    wanted_fields = [
        "id",
        "workspace_id",
        "title",
        "description",
        "status",
        "priority",
        "priority_label",
        "severity",
        "module",
        "current_owner",
        "reporter",
        "de",
        "te",
        "fixer",
        "version_report",
        "version_test",
        "version_fix",
        "created",
        "modified",
        "resolved",
        "closed",
        "deadline",
        "source",
        "bugtype",
        "frequency",
        "resolution",
    ]

    normalized = {
        field: bug.get(field)
        for field in wanted_fields
        if field in bug
    }

    return normalized


def _normalize_comment(item: dict[str, Any]) -> dict[str, Any]:
    comment = item.get("Comment", item)

    wanted_fields = [
        "id",
        "title",
        "description",
        "author",
        "entry_type",
        "entry_id",
        "created",
        "modified",
        "workspace_id",
        "root_id",
        "reply_id",
    ]

    return {
        field: comment.get(field)
        for field in wanted_fields
        if field in comment
    }


def _fetch_comments(
    *,
    workspace_id: str,
    bug_id: str,
    entry_type: str,
    limit: int,
    page: int,
) -> list[dict[str, Any]]:
    data = _request_json(
        "/comments",
        {
            "workspace_id": workspace_id,
            "entry_type": entry_type,
            "entry_id": bug_id,
            "limit": min(limit, 200),
            "page": page,
        },
    )

    return [_normalize_comment(item) for item in data.get("data", [])]


def list_bugs(args: argparse.Namespace) -> int:
    workspace_id = args.workspace_id or os.getenv("TAPD_WORKSPACE_ID")

    if not workspace_id:
        raise TapdError(
            "Missing workspace id. Pass --workspace-id or set TAPD_WORKSPACE_ID "
            "in the project .env file."
        )

    params: dict[str, Any] = {
        "workspace_id": workspace_id,
        "limit": min(args.limit, 200),
        "page": args.page,
        "order": args.order,
        "fields": args.fields,
        "status": args.status,
        "title": args.title,
        "current_owner": args.owner,
        "severity": args.severity,
        "priority_label": args.priority,
        "module": args.module,
    }

    data = _request_json("/bugs", params)
    bugs = [_normalize_bug(item) for item in data.get("data", [])]

    if args.with_comments:
        for bug in bugs:
            bug_id = bug.get("id")

            if not bug_id:
                bug["comments_count"] = 0
                bug["comments"] = []
                continue

            comments = _fetch_comments(
                workspace_id=workspace_id,
                bug_id=str(bug_id),
                entry_type=args.comment_entry_type,
                limit=args.comments_limit,
                page=args.comments_page,
            )
            bug["comments_count"] = len(comments)
            bug["comments"] = comments

    print(
        json.dumps(
            {
                "workspace_id": workspace_id,
                "count": len(bugs),
                "bugs": bugs,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0


def get_bug(args: argparse.Namespace) -> int:
    workspace_id = args.workspace_id or os.getenv("TAPD_WORKSPACE_ID")

    if not workspace_id:
        raise TapdError(
            "Missing workspace id. Pass --workspace-id or set TAPD_WORKSPACE_ID "
            "in the project .env file."
        )

    if not args.bug_id:
        raise TapdError("Missing --bug-id.")

    params = {
        "workspace_id": workspace_id,
        "id": args.bug_id,
        "limit": 1,
        "page": 1,
    }

    data = _request_json("/bugs", params)
    bugs = [_normalize_bug(item) for item in data.get("data", [])]

    if not bugs:
        raise TapdError(
            f"No TAPD bug found for id={args.bug_id} "
            f"in workspace_id={workspace_id}."
        )

    bug = bugs[0]

    if args.with_comments:
        comments = _fetch_comments(
            workspace_id=workspace_id,
            bug_id=args.bug_id,
            entry_type=args.comment_entry_type,
            limit=args.comments_limit,
            page=args.comments_page,
        )
        bug["comments_count"] = len(comments)
        bug["comments"] = comments

    print(json.dumps(bug, ensure_ascii=False, indent=2))

    return 0


def get_comments(args: argparse.Namespace) -> int:
    workspace_id = args.workspace_id or os.getenv("TAPD_WORKSPACE_ID")

    if not workspace_id:
        raise TapdError(
            "Missing workspace id. Pass --workspace-id or set TAPD_WORKSPACE_ID "
            "in the project .env file."
        )

    if not args.bug_id:
        raise TapdError("Missing --bug-id.")

    comments = _fetch_comments(
        workspace_id=workspace_id,
        bug_id=args.bug_id,
        entry_type=args.comment_entry_type,
        limit=args.limit,
        page=args.page,
    )

    print(
        json.dumps(
            {
                "workspace_id": workspace_id,
                "bug_id": args.bug_id,
                "entry_type": args.comment_entry_type,
                "count": len(comments),
                "comments": comments,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0


def get_image(args: argparse.Namespace) -> int:
    workspace_id = args.workspace_id or os.getenv("TAPD_WORKSPACE_ID")

    if not workspace_id:
        raise TapdError(
            "Missing workspace id. Pass --workspace-id or set TAPD_WORKSPACE_ID "
            "in the project .env file."
        )

    if not args.image_path:
        raise TapdError("Missing --image-path.")

    data = _request_json(
        "/files/get_image",
        {
            "workspace_id": workspace_id,
            "image_path": args.image_path,
        },
    )

    print(json.dumps(data, ensure_ascii=False, indent=2))

    return 0


def get_attachment(args: argparse.Namespace) -> int:
    workspace_id = args.workspace_id or os.getenv("TAPD_WORKSPACE_ID")

    if not workspace_id:
        raise TapdError(
            "Missing workspace id. Pass --workspace-id or set TAPD_WORKSPACE_ID "
            "in the project .env file."
        )

    if not args.attachment_id:
        raise TapdError("Missing --attachment-id.")

    data = _request_json(
        "/attachments/down",
        {
            "workspace_id": workspace_id,
            "id": args.attachment_id,
        },
    )

    print(json.dumps(data, ensure_ascii=False, indent=2))

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read TAPD bugs for Codex.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List TAPD bugs.")
    list_parser.add_argument("--workspace-id", default=None)
    list_parser.add_argument(
        "--status",
        default=None,
        help='Example: "new|in_progress|reopened"',
    )
    list_parser.add_argument("--title", default=None)
    list_parser.add_argument("--owner", default=None)
    list_parser.add_argument("--severity", default=None)
    list_parser.add_argument("--priority", default=None)
    list_parser.add_argument("--module", default=None)
    list_parser.add_argument("--limit", type=int, default=30)
    list_parser.add_argument("--page", type=int, default=1)
    list_parser.add_argument("--order", default="modified desc")
    list_parser.add_argument(
        "--with-comments",
        action="store_true",
        help="Also fetch comments for each returned bug.",
    )
    list_parser.add_argument("--comments-limit", type=int, default=30)
    list_parser.add_argument("--comments-page", type=int, default=1)
    list_parser.add_argument("--comment-entry-type", default=DEFAULT_COMMENT_ENTRY_TYPE)
    list_parser.add_argument(
        "--fields",
        default=(
            "id,workspace_id,title,description,status,priority,priority_label,"
            "severity,module,current_owner,reporter,de,te,fixer,"
            "version_report,version_test,version_fix,created,modified,"
            "resolved,closed,deadline,source,bugtype,frequency,resolution"
        ),
    )
    list_parser.set_defaults(func=list_bugs)

    get_parser = subparsers.add_parser("get", help="Get one TAPD bug by id.")
    get_parser.add_argument("--workspace-id", default=None)
    get_parser.add_argument("--bug-id", required=True)
    get_parser.add_argument(
        "--with-comments",
        action="store_true",
        help="Also fetch comments for this bug.",
    )
    get_parser.add_argument("--comments-limit", type=int, default=200)
    get_parser.add_argument("--comments-page", type=int, default=1)
    get_parser.add_argument("--comment-entry-type", default=DEFAULT_COMMENT_ENTRY_TYPE)
    get_parser.set_defaults(func=get_bug)

    comments_parser = subparsers.add_parser(
        "comments",
        help="List comments for one TAPD bug.",
    )
    comments_parser.add_argument("--workspace-id", default=None)
    comments_parser.add_argument("--bug-id", required=True)
    comments_parser.add_argument("--limit", type=int, default=200)
    comments_parser.add_argument("--page", type=int, default=1)
    comments_parser.add_argument("--comment-entry-type", default=DEFAULT_COMMENT_ENTRY_TYPE)
    comments_parser.set_defaults(func=get_comments)

    image_parser = subparsers.add_parser(
        "image",
        help="Get a temporary TAPD inline image download URL.",
    )
    image_parser.add_argument("--workspace-id", default=None)
    image_parser.add_argument("--image-path", required=True)
    image_parser.set_defaults(func=get_image)

    attachment_parser = subparsers.add_parser(
        "attachment",
        help="Get a temporary TAPD attachment download URL.",
    )
    attachment_parser.add_argument("--workspace-id", default=None)
    attachment_parser.add_argument("--attachment-id", required=True)
    attachment_parser.set_defaults(func=get_attachment)

    return parser


def main() -> int:
    load_dotenv()

    parser = build_parser()
    args = parser.parse_args()

    try:
        return args.func(args)
    except TapdError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
