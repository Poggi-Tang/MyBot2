from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Iterable


REDACTED = "[仅管理员可见]"

_REQUEST_ACTION = r"(?:给我|发我|发给我|查看|看看|看下|获取|读取|显示|告诉我|导出|打开|复制|提供|找出|查出)"
_DESKTOP_CAPTURE = re.compile(
    r"(?:截(?:取|一张|个)?(?:电脑|本机|当前)?(?:桌面|屏幕)|"
    r"(?:桌面|电脑屏幕|本机屏幕|当前屏幕).{0,8}(?:截图|截屏|画面))",
    re.IGNORECASE,
)
_CREDENTIAL_REQUEST = re.compile(
    rf"(?:{_REQUEST_ACTION}.{{0,18}}(?:api\s*key|apikey|密钥|token|令牌|密码|口令|secret|authorization)|"
    rf"(?:api\s*key|apikey|密钥|token|令牌|密码|口令|secret|authorization).{{0,18}}{_REQUEST_ACTION})",
    re.IGNORECASE,
)
_PATH_REQUEST = re.compile(
    rf"(?:{_REQUEST_ACTION}.{{0,18}}(?:真实|完整|绝对|本机|磁盘)?(?:文件|目录|项目)?路径|"
    rf"(?:真实|完整|绝对|本机|磁盘)(?:文件|目录|项目)?路径.{{0,18}}{_REQUEST_ACTION}|"
    r"文件(?:到底)?(?:在|位于)哪(?:里|个目录))",
    re.IGNORECASE,
)
_PRIVATE_REQUEST = re.compile(
    rf"(?:{_REQUEST_ACTION}.{{0,18}}(?:隐私|私密信息|个人信息|身份证|手机号|通讯录|聊天记录|历史对话|住址)|"
    rf"(?:隐私|私密信息|个人信息|身份证|手机号|通讯录|聊天记录|历史对话|住址).{{0,18}}{_REQUEST_ACTION})",
    re.IGNORECASE,
)

_TOKEN_VALUE = re.compile(
    r"(?i)(?:\b(?:sk|bai)-[A-Za-z0-9_-]{12,}\b|"
    r"\bgh[opsu]_[A-Za-z0-9_]{12,}\b|"
    r"\bBearer\s+[A-Za-z0-9._~-]{12,}\b)"
)
_ASSIGNED_SECRET = re.compile(
    r"(?i)\b(api[_ -]?key|access[_ -]?token|token|authorization|secret|password)"
    r"\s*[:=]\s*['\"]?([^\s'\",;]{8,})['\"]?"
)
_WINDOWS_PATH = re.compile(
    r"(?i)(?<![A-Za-z0-9_])(?:[A-Za-z]:[\\/](?:[^\\/\r\n:*?\"<>|]+[\\/])*"
    r"[^\\/\r\n:*?\"<>|]+)"
)
_UNC_PATH = re.compile(
    r"(?i)(?<![A-Za-z0-9_])(?:\\\\[^\\\s]+\\[^\r\n:*?\"<>|]+)"
)
_UNIX_PRIVATE_PATH = re.compile(r"(?<![A-Za-z0-9_])/(?:home|Users)/[^\s`'\"<>]+")
_CHINA_MOBILE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_CHINA_ID = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")

_SENSITIVE_FILE_NAME = re.compile(
    r"(?i)(?:desktop|screenshot|screen[-_ ]?capture|截屏|截图|屏幕|"
    r"\.env(?:\.|$)|credentials?|secrets?|tokens?|api[-_ ]?keys?|config\.json$)"
)
_TEXT_EXTENSIONS = {
    ".txt", ".md", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".ini",
    ".cfg", ".conf", ".env", ".log", ".csv", ".py", ".ps1", ".sh",
}


def _identity(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).strip()
    return normalized.removeprefix("@").strip().casefold()


class SecurityPolicy:
    def __init__(self, administrators: Iterable[str] = (), *, enabled: bool = True) -> None:
        self.enabled = bool(enabled)
        self.administrators: set[str] = set()
        self.configure(administrators, enabled=enabled)

    def configure(self, administrators: Iterable[str], *, enabled: bool | None = None) -> None:
        if enabled is not None:
            self.enabled = bool(enabled)
        self.administrators = {
            normalized
            for value in administrators
            if (normalized := _identity(value))
        }

    def is_admin(self, *identities: str) -> bool:
        if not self.enabled:
            return True
        return any(_identity(value) in self.administrators for value in identities if str(value).strip())

    def restricted_request(self, text: str) -> tuple[str, ...]:
        if not self.enabled:
            return ()
        value = str(text or "")
        matches: list[str] = []
        for name, pattern in (
            ("desktop_capture", _DESKTOP_CAPTURE),
            ("credentials", _CREDENTIAL_REQUEST),
            ("absolute_paths", _PATH_REQUEST),
            ("private_information", _PRIVATE_REQUEST),
        ):
            if pattern.search(value):
                matches.append(name)
        return tuple(matches)

    def protect_text(self, text: str, *, privileged: bool) -> str:
        value = str(text or "")
        if not self.enabled or privileged:
            return value
        value = _ASSIGNED_SECRET.sub(lambda match: f"{match.group(1)}={REDACTED}", value)
        for pattern in (
            _TOKEN_VALUE,
            _WINDOWS_PATH,
            _UNC_PATH,
            _UNIX_PRIVATE_PATH,
            _CHINA_ID,
            _CHINA_MOBILE,
            _EMAIL,
        ):
            value = pattern.sub(REDACTED, value)
        return value

    def sensitive_output_file(self, path: str | Path) -> bool:
        candidate = Path(path)
        if _SENSITIVE_FILE_NAME.search(candidate.name):
            return True
        try:
            if (
                candidate.suffix.casefold() not in _TEXT_EXTENSIONS
                or not candidate.is_file()
                or candidate.stat().st_size > 2 * 1024 * 1024
            ):
                return False
            content = candidate.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return False
        protected = self.protect_text(content, privileged=False)
        return protected != content
