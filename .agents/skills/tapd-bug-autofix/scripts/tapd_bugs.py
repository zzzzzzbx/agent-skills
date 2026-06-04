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
WORKFLOW_CONFIG_RELATIVE_PATH = Path(".agents") / "tapd-bug-autofix.workflow.json"
DEFAULT_WORKFLOW_CONFIG = {
    "name": "tapd-bug-autofix-default",
    "read": {
        "v_status": "新|重新打开",
        "with_comments": True,
        "comments_limit": 30,
    },
    "write": {
        "enabled": True,
        "status_field": "v_status",
        "current_user_env": "TAPD_CURRENT_USER",
    },
    "transitions": {
        "accept": {
            "v_status": "接收/处理",
        },
        "ready_for_release": {
            "v_status": "待发布",
        },
        "resolved": {
            "v_status": "已解决",
        },
    },
}


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


def _request_json(
    path: str,
    params: dict[str, Any],
    *,
    method: str = "GET",
) -> dict[str, Any]:
    clean_params = {
        key: value
        for key, value in params.items()
        if value is not None and value != ""
    }

    method = method.upper()
    headers = _auth_headers()

    if method == "GET":
        query = urllib.parse.urlencode(clean_params)
        url = f"{TAPD_API_BASE}{path}?{query}"
        data = None
    else:
        url = f"{TAPD_API_BASE}{path}"
        data = urllib.parse.urlencode(clean_params).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    req = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method,
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


def _find_workflow_config(explicit_path: str | None = None) -> Path | None:
    if explicit_path:
        return Path(explicit_path).expanduser().resolve()

    env_path = os.getenv("TAPD_WORKFLOW_CONFIG")
    if env_path:
        return Path(env_path).expanduser().resolve()

    for parent in [Path.cwd(), *Path.cwd().parents]:
        candidate = parent / WORKFLOW_CONFIG_RELATIVE_PATH

        if candidate.exists():
            return candidate.resolve()

    return None


def _default_workflow_config_path() -> Path:
    return (Path.cwd() / WORKFLOW_CONFIG_RELATIVE_PATH).resolve()


def _load_workflow_config(
    explicit_path: str | None = None,
    *,
    required: bool = True,
) -> tuple[Path | None, dict[str, Any] | None]:
    path = _find_workflow_config(explicit_path)

    if path is None:
        if required:
            raise TapdError(
                "Missing TAPD workflow config. Run "
                "`tapd_bugs.py workflow init` from the project root, or pass "
                "--workflow-config."
            )
        return None, None

    if not path.exists():
        raise TapdError(f"TAPD workflow config does not exist: {path}")

    try:
        with path.open("r", encoding="utf-8") as file:
            config = json.load(file)
    except json.JSONDecodeError as exc:
        raise TapdError(f"Invalid TAPD workflow config JSON: {path}") from exc

    if not isinstance(config, dict):
        raise TapdError(f"TAPD workflow config must be a JSON object: {path}")

    return path, config


def _workflow_read_config(config: dict[str, Any]) -> dict[str, Any]:
    read_config = config.get("read", {})

    if not isinstance(read_config, dict):
        raise TapdError("TAPD workflow config field `read` must be an object.")

    return read_config


def _workflow_write_config(config: dict[str, Any]) -> dict[str, Any]:
    write_config = config.get("write", {})

    if not isinstance(write_config, dict):
        raise TapdError("TAPD workflow config field `write` must be an object.")

    return write_config


def _apply_workflow_read_defaults(args: argparse.Namespace) -> dict[str, Any] | None:
    if not getattr(args, "workflow", False):
        return None

    _, config = _load_workflow_config(args.workflow_config, required=True)
    assert config is not None

    read_config = _workflow_read_config(config)

    if not args.status and read_config.get("status"):
        args.status = str(read_config["status"])

    if not args.v_status and read_config.get("v_status"):
        args.v_status = str(read_config["v_status"])

    if read_config.get("with_comments"):
        args.with_comments = True

    if args.comments_limit == 30 and read_config.get("comments_limit"):
        args.comments_limit = int(read_config["comments_limit"])

    if args.comments_page == 1 and read_config.get("comments_page"):
        args.comments_page = int(read_config["comments_page"])

    if (
        args.comment_entry_type == DEFAULT_COMMENT_ENTRY_TYPE
        and read_config.get("comment_entry_type")
    ):
        args.comment_entry_type = str(read_config["comment_entry_type"])

    return config


def _workflow_transition_fields(
    config: dict[str, Any],
    transition_name: str,
) -> dict[str, Any]:
    transitions = config.get("transitions", {})

    if not isinstance(transitions, dict):
        raise TapdError("TAPD workflow config field `transitions` must be an object.")

    if transition_name not in transitions:
        available = ", ".join(sorted(transitions))
        raise TapdError(
            f"Unknown TAPD workflow transition: {transition_name}. "
            f"Available transitions: {available or '(none)'}."
        )

    transition = transitions[transition_name]

    if isinstance(transition, str):
        status_field = str(_workflow_write_config(config).get("status_field", "v_status"))
        return {status_field: transition}

    if not isinstance(transition, dict):
        raise TapdError(
            f"TAPD workflow transition `{transition_name}` must be an object or string."
        )

    fields = {
        key: value
        for key, value in transition.items()
        if value is not None and value != ""
    }

    if not fields:
        raise TapdError(f"TAPD workflow transition `{transition_name}` is empty.")

    return fields


def _add_current_user_field(
    fields: dict[str, Any],
    *,
    current_user: str | None,
    write_config: dict[str, Any] | None = None,
) -> None:
    if "current_user" in fields:
        return

    if current_user:
        fields["current_user"] = current_user
        return

    env_name = "TAPD_CURRENT_USER"

    if write_config and write_config.get("current_user_env"):
        env_name = str(write_config["current_user_env"])

    env_value = os.getenv(env_name)

    if env_value:
        fields["current_user"] = env_value


def _update_bug_fields(
    *,
    workspace_id: str,
    bug_id: str,
    fields: dict[str, Any],
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "workspace_id": workspace_id,
        "id": bug_id,
    }
    params.update(fields)

    return _request_json("/bugs", params, method="POST")


def list_bugs(args: argparse.Namespace) -> int:
    workspace_id = args.workspace_id or os.getenv("TAPD_WORKSPACE_ID")

    if not workspace_id:
        raise TapdError(
            "Missing workspace id. Pass --workspace-id or set TAPD_WORKSPACE_ID "
            "in the project .env file."
        )

    _apply_workflow_read_defaults(args)

    params: dict[str, Any] = {
        "workspace_id": workspace_id,
        "limit": min(args.limit, 200),
        "page": args.page,
        "order": args.order,
        "fields": args.fields,
        "status": args.status,
        "v_status": args.v_status,
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

    if getattr(args, "workflow", False):
        _, config = _load_workflow_config(args.workflow_config, required=True)
        assert config is not None
        read_config = _workflow_read_config(config)

        if read_config.get("with_comments"):
            args.with_comments = True

        if args.comments_limit == 200 and read_config.get("comments_limit"):
            args.comments_limit = int(read_config["comments_limit"])

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


def update_bug_status(args: argparse.Namespace) -> int:
    workspace_id = args.workspace_id or os.getenv("TAPD_WORKSPACE_ID")

    if not workspace_id:
        raise TapdError(
            "Missing workspace id. Pass --workspace-id or set TAPD_WORKSPACE_ID "
            "in the project .env file."
        )

    fields: dict[str, Any] = {
        "status": args.status,
        "v_status": args.v_status,
    }

    if args.keep_owner:
        fields["keep_owner"] = "1"

    fields = {
        key: value
        for key, value in fields.items()
        if value is not None and value != ""
    }

    if not fields.get("status") and not fields.get("v_status"):
        raise TapdError("Pass --status or --v-status to update a TAPD bug status.")

    _add_current_user_field(fields, current_user=args.current_user)

    data = _update_bug_fields(
        workspace_id=workspace_id,
        bug_id=args.bug_id,
        fields=fields,
    )

    print(
        json.dumps(
            {
                "workspace_id": workspace_id,
                "bug_id": args.bug_id,
                "updated_fields": fields,
                "response": data.get("data", data),
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0


def transition_bug(args: argparse.Namespace) -> int:
    workspace_id = args.workspace_id or os.getenv("TAPD_WORKSPACE_ID")

    if not workspace_id:
        raise TapdError(
            "Missing workspace id. Pass --workspace-id or set TAPD_WORKSPACE_ID "
            "in the project .env file."
        )

    path, config = _load_workflow_config(args.workflow_config, required=True)
    assert config is not None

    write_config = _workflow_write_config(config)

    if not write_config.get("enabled", False) and not args.force:
        raise TapdError(
            "TAPD workflow write-back is disabled. Set write.enabled=true in "
            f"{path}, or pass --force for this transition."
        )

    fields = _workflow_transition_fields(config, args.to)
    _add_current_user_field(
        fields,
        current_user=args.current_user,
        write_config=write_config,
    )

    data = _update_bug_fields(
        workspace_id=workspace_id,
        bug_id=args.bug_id,
        fields=fields,
    )

    print(
        json.dumps(
            {
                "workspace_id": workspace_id,
                "bug_id": args.bug_id,
                "workflow_config": str(path),
                "transition": args.to,
                "updated_fields": fields,
                "response": data.get("data", data),
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0


def workflow_command(args: argparse.Namespace) -> int:
    if args.workflow_command == "init":
        target = (
            Path(args.path).expanduser().resolve()
            if args.path
            else _default_workflow_config_path()
        )

        if target.exists() and not args.force:
            raise TapdError(
                f"TAPD workflow config already exists: {target}. "
                "Pass --force to overwrite it."
            )

        target.parent.mkdir(parents=True, exist_ok=True)

        with target.open("w", encoding="utf-8", newline="\n") as file:
            json.dump(DEFAULT_WORKFLOW_CONFIG, file, ensure_ascii=False, indent=2)
            file.write("\n")

        print(
            json.dumps(
                {
                    "created": str(target),
                    "workflow": DEFAULT_WORKFLOW_CONFIG,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

        return 0

    if args.workflow_command == "show":
        path, config = _load_workflow_config(args.path, required=True)
        print(
            json.dumps(
                {
                    "path": str(path),
                    "workflow": config,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.workflow_command == "path":
        path = _find_workflow_config(args.path)
        default_path = _default_workflow_config_path()

        print(
            json.dumps(
                {
                    "path": str(path) if path else None,
                    "exists": bool(path and path.exists()),
                    "default_path": str(default_path),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    raise TapdError("Missing workflow command.")


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
    list_parser.add_argument(
        "--v-status",
        default=None,
        help='Display status name, for example "新|重新打开".',
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
        "--workflow",
        action="store_true",
        help="Apply read defaults from the project TAPD workflow config.",
    )
    list_parser.add_argument("--workflow-config", default=None)
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
        "--workflow",
        action="store_true",
        help="Apply read defaults from the project TAPD workflow config.",
    )
    get_parser.add_argument("--workflow-config", default=None)
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

    status_parser = subparsers.add_parser(
        "status",
        help="Update one TAPD bug status directly.",
    )
    status_parser.add_argument("--workspace-id", default=None)
    status_parser.add_argument("--bug-id", required=True)
    status_parser.add_argument("--status", default=None)
    status_parser.add_argument(
        "--v-status",
        default=None,
        help="Display status name, useful for customized TAPD workflows.",
    )
    status_parser.add_argument("--current-user", default=None)
    status_parser.add_argument("--keep-owner", action="store_true")
    status_parser.set_defaults(func=update_bug_status)

    transition_parser = subparsers.add_parser(
        "transition",
        help="Update one TAPD bug using a configured workflow transition.",
    )
    transition_parser.add_argument("--workspace-id", default=None)
    transition_parser.add_argument("--bug-id", required=True)
    transition_parser.add_argument("--to", required=True)
    transition_parser.add_argument("--workflow-config", default=None)
    transition_parser.add_argument("--current-user", default=None)
    transition_parser.add_argument(
        "--force",
        action="store_true",
        help="Allow transition even when write.enabled is false.",
    )
    transition_parser.set_defaults(func=transition_bug)

    workflow_parser = subparsers.add_parser(
        "workflow",
        help="Create or inspect the project TAPD workflow config.",
    )
    workflow_subparsers = workflow_parser.add_subparsers(
        dest="workflow_command",
        required=True,
    )

    workflow_init_parser = workflow_subparsers.add_parser(
        "init",
        help="Create .agents/tapd-bug-autofix.workflow.json.",
    )
    workflow_init_parser.add_argument("--path", default=None)
    workflow_init_parser.add_argument("--force", action="store_true")
    workflow_init_parser.set_defaults(func=workflow_command)

    workflow_show_parser = workflow_subparsers.add_parser(
        "show",
        help="Print the active TAPD workflow config.",
    )
    workflow_show_parser.add_argument("--path", default=None)
    workflow_show_parser.set_defaults(func=workflow_command)

    workflow_path_parser = workflow_subparsers.add_parser(
        "path",
        help="Print the resolved TAPD workflow config path.",
    )
    workflow_path_parser.add_argument("--path", default=None)
    workflow_path_parser.set_defaults(func=workflow_command)

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
