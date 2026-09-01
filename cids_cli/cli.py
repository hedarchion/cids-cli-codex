"""Command-line entry point for the CIDS application client."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import quote, urljoin

from .client import AuthError, CidsClient, CidsError, RequestError, BASE_URL, cookie_path, render_plan, render_response
from .registry import FunctionSpec, as_dict, get_function, iter_functions
from .import_week import check_week, import_week, validate_week


def _key_values(values: Optional[Sequence[str]], label: str) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for item in values or ():
        if "=" not in item:
            raise CidsError(f"{label} must use key=value syntax: {item!r}")
        key, value = item.split("=", 1)
        if not key:
            raise CidsError(f"{label} key cannot be empty.")
        result[key] = value
    return result


def _request_params(values: Optional[Sequence[str]]) -> Dict[str, Any]:
    """Parse repeated key=value flags without collapsing PHP array fields."""
    result: Dict[str, Any] = {}
    for item in values or ():
        if "=" not in item:
            raise CidsError(f"--param must use key=value syntax: {item!r}")
        key, value = item.split("=", 1)
        if not key:
            raise CidsError("--param key cannot be empty.")
        if key not in result:
            result[key] = value
        elif isinstance(result[key], list):
            result[key].append(value)
        else:
            result[key] = [result[key], value]
    return result


def _substitute_path(spec: FunctionSpec, params: Mapping[str, Any]) -> str:
    path = spec.path
    for key in spec.placeholders:
        if key not in params or params[key] == "":
            raise CidsError(f"Function {spec.name} requires --param {key}=value")
        path = path.replace("{" + key + "}", quote(str(params[key]), safe=""))
    return path


def _write_output(value: str, output_file: Optional[str]) -> None:
    if output_file:
        path = Path(output_file).expanduser()
        try:
            path.write_text(value, encoding="utf-8")
        except OSError as exc:
            raise CidsError(f"Could not write output file: {exc}") from None
        return
    print(value)


def _client(args: argparse.Namespace) -> CidsClient:
    return CidsClient(base_url=args.base_url, timeout=args.timeout, trace=args.trace)


def cmd_functions(args: argparse.Namespace) -> int:
    specs = [
        spec for spec in iter_functions()
        if not args.domain or spec.name == args.domain or spec.name.startswith(args.domain + ".")
    ]
    if args.json:
        print(json.dumps([as_dict(spec) for spec in specs], ensure_ascii=False, indent=2))
        return 0
    for spec in specs:
        marker = "MUTATING" if spec.mutating else "read-only"
        aliases = f" [{', '.join(spec.aliases)}]" if spec.aliases else ""
        print(f"{spec.name:30} {spec.method:4} {marker:8} {spec.description}{aliases}")
    return 0


def cmd_describe(args: argparse.Namespace) -> int:
    spec = get_function(args.name)
    if not spec:
        raise CidsError(f"Unknown function {args.name!r}; run 'cids functions' to list available functions.")
    if args.json:
        print(json.dumps(as_dict(spec), ensure_ascii=False, indent=2))
        return 0
    print(f"{spec.name}: {spec.description}")
    print(f"Method: {spec.method}")
    print(f"Path:   {spec.path}")
    print(f"Safety: {'mutating (requires --yes)' if spec.mutating else 'read-only'}")
    print("Parameters: " + (", ".join(spec.params) if spec.params else "none"))
    if spec.aliases:
        print("Aliases: " + ", ".join(spec.aliases))
    if spec.notes:
        print("Notes: " + spec.notes)
    return 0


def cmd_login(args: argparse.Namespace) -> int:
    client = _client(args)
    client.login(username=args.username)
    print(f"Logged in. Session cookies saved to {cookie_path()}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    client = _client(args)
    authenticated, response = client.status()
    if args.json:
        print(json.dumps({"authenticated": authenticated, "url": response.url}, indent=2))
    else:
        print("authenticated" if authenticated else "not authenticated")
    return 0 if authenticated else 1


def cmd_logout(args: argparse.Namespace) -> int:
    client = _client(args)
    client.logout()
    print("Logged out; local session cookies cleared.")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    spec = get_function(args.name)
    if not spec:
        raise CidsError(f"Unknown function {args.name!r}; run 'cids functions' to list available functions.")
    params = _request_params(args.param)
    file_paths = _key_values(args.file, "--file")
    route = _substitute_path(spec, params)
    url = urljoin(args.base_url.rstrip("/") + "/", route.lstrip("/"))
    if spec.mutating and not args.yes and not args.dry_run:
        raise CidsError(f"{spec.name} can change data; re-run with --yes (or use --dry-run).")
    if args.dry_run:
        _write_output(render_plan(spec.method, url, params, file_paths), args.output_file)
        return 0

    client = _client(args)
    authenticated, _ = client.status()
    if not authenticated:
        raise AuthError("No authenticated session. Run 'cids auth login' first.")

    files_payload: Dict[str, Tuple[str, bytes]] = {}
    for key, path_text in file_paths.items():
        path = Path(path_text).expanduser()
        if not path.is_file():
            raise CidsError(f"File for --file {key} does not exist: {path}")
        try:
            files_payload[key] = (path.name, path.read_bytes())
        except OSError as exc:
            raise CidsError(f"Could not read upload {path}: {exc}") from None

    placeholders = set(spec.placeholders)
    if spec.method.upper() == "GET":
        query = {key: value for key, value in params.items() if key not in placeholders}
        response = client.request("GET", route, params=query or None)
    else:
        if spec.json_body:
            response = client.request(spec.method, route, json_data=params or None)
        else:
            response = client.request(spec.method, route, data=params or None, files=files_payload or None)
    _write_output(render_response(response, args.output_format), args.output_file)
    return 0


def cmd_import_week(args: argparse.Namespace) -> int:
    source = Path(args.source).expanduser()
    if not source.is_file():
        raise CidsError(
            "Weekly lesson JSON does not exist.",
            code="IMPORT_SOURCE_NOT_FOUND",
            exit_status=2,
        )

    if args.yes and (args.dry_run or args.check):
        raise CidsError(
            "--yes cannot be combined with --dry-run or --check.",
            code="IMPORT_MODE_CONFLICT",
            exit_status=2,
        )

    if args.dry_run:
        result = validate_week(source)
        print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None,
                         separators=None if args.pretty else (",", ":")))
        return 0

    required = ("miw_id", "class_id", "setjadual", "owner_id", "grouplevelsubject")
    missing = [name for name in required if not getattr(args, name)]
    if missing:
        raise CidsError(
            "Remote check/import requires: " + ", ".join("--" + name.replace("_", "-") for name in missing),
            code="IMPORT_IDENTIFIER_MISSING",
            exit_status=2,
            details={"fields": missing},
        )
    if not args.check and not args.yes:
        raise CidsError(
            "import-week creates or updates DLPs; re-run with --yes, --check, or --dry-run.",
            code="CONFIRMATION_REQUIRED",
            exit_status=6,
        )
    client = _client(args)
    authenticated, _ = client.status()
    if not authenticated:
        raise AuthError("No authenticated session. Run 'cids auth login' first.")
    options = {
        "miw_id": args.miw_id,
        "class_id": args.class_id,
        "setjadual": args.setjadual,
        "owner_id": args.owner_id,
        "grouplevelsubject": args.grouplevelsubject,
        "subject": args.subject,
        "session": args.session,
    }
    result = check_week(client, source, **options) if args.check else import_week(client, source, **options)
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None,
                     separators=None if args.pretty else (",", ":")))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cids", description="Operate the ASIE/CIDS model application from a terminal.")
    parser.add_argument("--base-url", default=os.environ.get("CIDS_BASE_URL", BASE_URL), help=argparse.SUPPRESS)
    parser.add_argument("--timeout", type=float, default=30.0, help=argparse.SUPPRESS)
    parser.add_argument("--trace", action="store_true", help="Print sanitized request traces to stderr.")
    sub = parser.add_subparsers(dest="command", required=True)

    functions = sub.add_parser("functions", help="List registry functions.")
    functions.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    functions.add_argument("--domain", help="Only show one function-name prefix, for example yip or dashboard.")
    functions.set_defaults(handler=cmd_functions)

    describe = sub.add_parser("describe", help="Describe one registry function.")
    describe.add_argument("name")
    describe.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    describe.set_defaults(handler=cmd_describe)

    auth = sub.add_parser("auth", help="Manage the authenticated session.")
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)
    login = auth_sub.add_parser("login", help="Log in using env vars or secure prompts.")
    login.add_argument("--username", help="Username (otherwise CIDS_USERNAME or a prompt).")
    login.set_defaults(handler=cmd_login)
    status = auth_sub.add_parser("status", help="Check the current session.")
    status.add_argument("--json", action="store_true")
    status.set_defaults(handler=cmd_status)
    logout = auth_sub.add_parser("logout", help="Log out and clear the local cookie jar.")
    logout.set_defaults(handler=cmd_logout)

    run = sub.add_parser("run", help="Run a registry function.")
    run.add_argument("name", help="Function name or alias.")
    run.add_argument("--param", action="append", default=[], metavar="KEY=VALUE", help="Request parameter; repeatable.")
    run.add_argument("--file", action="append", default=[], metavar="KEY=PATH", help="Multipart upload; repeatable.")
    run.add_argument("--dry-run", action="store_true", help="Show the planned request without network access.")
    run.add_argument("--yes", action="store_true", help="Confirm a mutating function.")
    run.add_argument("--format", "--output-format", dest="output_format", choices=("html", "text", "json"), default="text", help="Output format (default: text).")
    run.add_argument("--output-file", help="Write output to this file instead of stdout.")
    run.set_defaults(handler=cmd_run)

    importer = sub.add_parser("import-week", help="Import a generated weekly lesson JSON into an existing MIW.")
    importer.add_argument("source", help="Path to the weekly lesson JSON file.")
    importer.add_argument("--miw-id")
    importer.add_argument("--class-id")
    importer.add_argument("--setjadual", help="Activated timetable identifier.")
    importer.add_argument("--owner-id")
    importer.add_argument("--grouplevelsubject")
    importer.add_argument("--subject", default="english")
    importer.add_argument("--session", default="2026")
    mode = importer.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Validate locally; perform no network requests or writes.")
    mode.add_argument("--check", action="store_true", help="Run authenticated remote preflight checks without CIDS writes.")
    importer.add_argument("--yes", action="store_true", help="Confirm creating/updating all DLPs in the file.")
    importer.add_argument("--pretty", action="store_true", help="Pretty-print JSON instead of compact agent output.")
    importer.set_defaults(handler=cmd_import_week)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except CidsError as exc:
        if getattr(args, "command", None) == "import-week":
            payload = {
                "ok": False,
                "error": {
                    "code": exc.code,
                    "message": str(exc),
                    "details": exc.details,
                },
            }
            print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), file=sys.stderr)
        else:
            print(f"cids: [{exc.code}] {exc}", file=sys.stderr)
        return exc.exit_status


if __name__ == "__main__":
    raise SystemExit(main())
