"""HTTP session and output helpers for the CIDS CLI."""

from __future__ import annotations

import html
import http.cookiejar
import json
import os
import re
import stat
import sys
import warnings
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple
from urllib.parse import urljoin

# Some macOS system Pythons are linked against LibreSSL.  urllib3 emits a
# noisy advisory on import; it does not affect the CLI's normal HTTP usage.
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL")
import requests

from .auth import resolve_credentials


BASE_URL = "https://asiemodel.net/model/"
DEFAULT_TIMEOUT = 30.0


class CidsError(RuntimeError):
    """A user-facing, sanitized CLI error."""

    code = "CIDS_ERROR"
    exit_status = 1

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        exit_status: Optional[int] = None,
        details: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code or self.code
        self.exit_status = exit_status if exit_status is not None else self.exit_status
        self.details = dict(details or {})


class AuthError(CidsError):
    code = "AUTH_REQUIRED"
    exit_status = 3


class RequestError(CidsError):
    code = "REMOTE_UNAVAILABLE"
    exit_status = 4


def config_dir() -> Path:
    root = os.environ.get("XDG_CONFIG_HOME")
    if root:
        return Path(root).expanduser() / "cids-cli"
    return Path.home() / ".config" / "cids-cli"


def cookie_path() -> Path:
    return config_dir() / "cookies.lwp"


def _secure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, stat.S_IRWXU)
    except OSError:
        pass


def _secure_file(path: Path) -> None:
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def _redact(value: Any, secrets: Iterable[str] = ()) -> str:
    text = str(value)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"(?i)(password|passwd|token|secret|authorization)([=:\s]+)[^&\s,]+", r"\1\2[REDACTED]", text)
    text = re.sub(r"(?i)(cookie:)[^\r\n]+", r"\1 [REDACTED]", text)
    return text


def _read_credentials(username: Optional[str], password: Optional[str]) -> Tuple[str, str]:
    try:
        credentials = resolve_credentials(username, password)
    except ValueError as exc:
        raise AuthError(str(exc)) from None
    return credentials.username, credentials.password


class _VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data: str) -> None:
        if not self.hidden and data.strip():
            self.parts.append(data.strip())


def html_to_text(value: str) -> str:
    parser = _VisibleText()
    try:
        parser.feed(value)
        return "\n".join(parser.parts)
    except Exception:
        return re.sub(r"<[^>]+>", " ", html.unescape(value)).strip()


@dataclass
class ResponseData:
    status: int
    url: str
    content_type: str
    text: str
    headers: Mapping[str, str]

    def parsed_json(self) -> Any:
        try:
            return json.loads(self.text)
        except (TypeError, ValueError):
            return None


class CidsClient:
    def __init__(self, base_url: str = BASE_URL, timeout: float = DEFAULT_TIMEOUT, trace: bool = False) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self.trace = trace
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "cids-cli/0.1.0", "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"})
        self.secrets = []
        self._load_cookies()

    def _load_cookies(self) -> None:
        path = cookie_path()
        if not path.exists():
            return
        jar = http.cookiejar.LWPCookieJar(str(path))
        try:
            jar.load(ignore_discard=True, ignore_expires=True)
            self.session.cookies.update(jar)
        except (OSError, http.cookiejar.LoadError):
            # A corrupt cache should not prevent a fresh login.
            return

    def _save_cookies(self) -> None:
        _secure_dir(config_dir())
        path = cookie_path()
        jar = http.cookiejar.LWPCookieJar(str(path))
        for cookie in self.session.cookies:
            jar.set_cookie(cookie)
        try:
            jar.save(ignore_discard=True, ignore_expires=True)
            _secure_file(path)
        except OSError as exc:
            raise CidsError("Could not save the session cookie jar: " + _redact(exc, self.secrets))

    def _trace(self, message: str) -> None:
        if self.trace:
            print("[trace] " + _redact(message, self.secrets), file=sys.stderr)

    def request(self, method: str, path: str, *, params: Optional[Mapping[str, Any]] = None,
                data: Optional[Mapping[str, Any]] = None,
                files: Optional[Mapping[str, Tuple[str, Any]]] = None,
                json_data: Optional[Any] = None) -> ResponseData:
        url = urljoin(self.base_url, path.lstrip("/"))
        self._trace(f"{method.upper()} {url} params={params or {}} fields={list((data or {}).keys())} json_fields={list((json_data or {}).keys()) if isinstance(json_data, dict) else []} files={list((files or {}).keys())}")
        try:
            response = self.session.request(method.upper(), url, params=params, data=data, files=files, json=json_data, timeout=self.timeout, allow_redirects=True)
        except requests.RequestException as exc:
            raise RequestError("Request failed: " + _redact(exc, self.secrets)) from None
        self._save_cookies()
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        text = response.text
        if response.status_code >= 400:
            detail = html_to_text(text)[:500] if "html" in content_type else text[:500]
            raise RequestError(
                f"HTTP {response.status_code} from {response.url}: {_redact(detail, self.secrets)}",
                code="REMOTE_HTTP_ERROR",
            )
        return ResponseData(response.status_code, response.url, content_type, text, {"Content-Type": content_type})

    def login(self, username: Optional[str] = None, password: Optional[str] = None) -> ResponseData:
        username, password = _read_credentials(username, password)
        self.secrets.extend([username, password])
        result = self.request("POST", "index.php", data={
            "username": username,
            "password": password,
            "submit": "Login",
        })
        if not self.is_authenticated(result.text):
            raise AuthError(
                "Login was not accepted; check the username and password.",
                code="AUTH_REJECTED",
            )
        return result

    @staticmethod
    def is_authenticated(page: str) -> bool:
        # Both successful and failed requests return HTTP 200. Detect the
        # public login form by its controls; its action may be relative or
        # absolute depending on which wrapper served it.
        has_user = bool(re.search(r"name\s*=\s*['\"]username['\"]", page, re.I))
        has_password = bool(re.search(r"name\s*=\s*['\"]password['\"]", page, re.I))
        return not (has_user and has_password)

    def status(self) -> Tuple[bool, ResponseData]:
        result = self.request("GET", "main.php")
        return self.is_authenticated(result.text), result

    def logout(self) -> ResponseData:
        result = self.request("GET", "logout.php?redirect=")
        self.session.cookies.clear()
        self._save_cookies()
        return result


def render_response(response: ResponseData, output_format: str) -> str:
    if output_format == "html":
        return response.text
    if output_format == "text":
        return html_to_text(response.text) if "html" in response.content_type else response.text
    parsed = response.parsed_json()
    body: Any = parsed if parsed is not None else response.text
    return json.dumps({"status": response.status, "url": response.url, "content_type": response.content_type, "body": body}, ensure_ascii=False, indent=2)


def render_plan(method: str, url: str, params: Mapping[str, Any], files: Mapping[str, str]) -> str:
    return json.dumps({"dry_run": True, "method": method.upper(), "url": url, "params": dict(params), "files": dict(files)}, ensure_ascii=False, indent=2)
