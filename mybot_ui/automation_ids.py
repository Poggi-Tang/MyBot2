from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Iterable
from typing import Any

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtGui import QAction, QShortcut
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSlider,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QSplitterHandle,
    QTabBar,
    QTextEdit,
    QWidget,
)


MYBOT_AUTOMATION_PREFIX = "MyBot"
AUTOMATION_HINT_PROPERTY = "mybot_automation_hint"
AUTOMATION_ID_PROPERTY = "mybot_automation_id"

_OPERABLE_WIDGET_TYPES = (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSlider,
    QAbstractSpinBox,
    QComboBox,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QSplitterHandle,
    QTabBar,
    QTextEdit,
)
_ASCII_TOKEN = re.compile(r"[^a-zA-Z0-9]+")


def semantic_token(value: Any, fallback: str = "control") -> str:
    """Return an ASCII token suitable for a stable UI AutomationId."""
    raw = str(value or "").strip()
    token = _ASCII_TOKEN.sub("_", raw).strip("_").lower()
    if token:
        return token
    if raw:
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]
        return f"{fallback}_{digest}"
    return fallback


def mybot_automation_id(context: str, semantic: str) -> str:
    return (
        f"{MYBOT_AUTOMATION_PREFIX}."
        f"{context_token(context)}."
        f"{semantic_token(semantic)}"
    )


def context_token(value: Any, fallback: str = "Window") -> str:
    parts = []
    for raw_part in str(value or "").split("."):
        part = _ASCII_TOKEN.sub("_", raw_part).strip("_")
        if part:
            parts.append(part)
    return ".".join(parts) or fallback


def set_automation_id(target: QObject, automation_id: str) -> str:
    """Assign the ID through Qt's UIA-backed API and retain it for audits."""
    value = str(automation_id).strip()
    if not value.startswith(f"{MYBOT_AUTOMATION_PREFIX}."):
        raise ValueError("MyBot AutomationId must start with 'MyBot.'.")
    setter = getattr(target, "setAccessibleIdentifier", None)
    if callable(setter):
        setter(value)
    target.setProperty(AUTOMATION_ID_PROPERTY, value)
    return value


def automation_id(target: QObject) -> str:
    getter = getattr(target, "accessibleIdentifier", None)
    if callable(getter):
        value = str(getter() or "").strip()
        if value:
            return value
    return str(target.property(AUTOMATION_ID_PROPERTY) or "").strip()


def set_automation_hint(target: QObject, semantic: str) -> None:
    target.setProperty(AUTOMATION_HINT_PROPERTY, semantic_token(semantic))


def is_operable(target: QObject) -> bool:
    return isinstance(target, _OPERABLE_WIDGET_TYPES) or isinstance(
        target, (QAction, QShortcut)
    )


class AutomationIdManager(QObject):
    """Assign stable, unique MyBot AutomationIds, including dynamic controls."""

    def __init__(
        self,
        app: QApplication | None = None,
        parent: QObject | None = None,
    ) -> None:
        application = app or QApplication.instance()
        super().__init__(parent or application)
        self._roots: dict[QObject, str] = {}
        self._owners: list[tuple[object, str]] = []
        self._scan_pending = False
        if application is not None:
            application.installEventFilter(self)

    def register_owner(self, owner: object, context: str) -> None:
        pair = (owner, context_token(context))
        if pair not in self._owners:
            self._owners.append(pair)
        if isinstance(owner, QObject):
            self.register_root(owner, context)
        self.refresh()

    def register_root(self, root: QObject, context: str) -> None:
        normalized_context = context_token(context)
        self._roots[root] = normalized_context
        set_automation_id(root, f"{MYBOT_AUTOMATION_PREFIX}.{normalized_context}")
        self.refresh()

    def refresh(self) -> None:
        # Named member controls are the public contract and take precedence.
        for owner, context in self._owners:
            for name, target in vars(owner).items():
                if is_operable(target):
                    set_automation_id(
                        target,
                        mybot_automation_id(context, name),
                    )

        used = Counter(
            value
            for root in self._roots
            for target in self._objects_under(root)
            if (value := automation_id(target))
        )
        for root, context in tuple(self._roots.items()):
            for target in self._objects_under(root):
                if not is_operable(target) or automation_id(target):
                    continue
                base = mybot_automation_id(context, self._semantic_for(target))
                candidate = base
                suffix = 2
                while used[candidate]:
                    candidate = f"{base}.{suffix}"
                    suffix += 1
                set_automation_id(target, candidate)
                used[candidate] += 1

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() in {QEvent.Type.ChildAdded, QEvent.Type.Show}:
            child = getattr(event, "child", lambda: None)()
            candidate = child if isinstance(child, QObject) else watched
            if self._belongs_to_registered_root(candidate):
                self._schedule_refresh()
        return super().eventFilter(watched, event)

    def audit(self) -> dict[str, list[str]]:
        missing: list[str] = []
        invalid: list[str] = []
        ids: list[str] = []
        seen: set[int] = set()
        for root in self._roots:
            for target in self._objects_under(root):
                address = id(target)
                if address in seen or not is_operable(target):
                    continue
                seen.add(address)
                value = automation_id(target)
                description = self._describe(target)
                if not value:
                    missing.append(description)
                elif not value.startswith(f"{MYBOT_AUTOMATION_PREFIX}."):
                    invalid.append(f"{description}: {value}")
                ids.append(value)
        duplicates = sorted(
            value for value, count in Counter(ids).items() if value and count > 1
        )
        return {
            "missing": sorted(missing),
            "invalid": sorted(invalid),
            "duplicates": duplicates,
            "ids": sorted(value for value in ids if value),
        }

    def inventory(self) -> list[dict[str, str]]:
        records: list[dict[str, str]] = []
        seen: set[int] = set()
        for root in self._roots:
            for target in self._objects_under(root):
                if id(target) in seen or not is_operable(target):
                    continue
                seen.add(id(target))
                records.append(
                    {
                        "automation_id": automation_id(target),
                        "class": type(target).__name__,
                        # Inventory is documentation, so never serialize live
                        # input values, selections, paths, or credentials.
                        "name": self._stable_name(target),
                    }
                )
        return sorted(records, key=lambda item: item["automation_id"])

    def _schedule_refresh(self) -> None:
        if self._scan_pending:
            return
        self._scan_pending = True

        def run() -> None:
            self._scan_pending = False
            self.refresh()

        QTimer.singleShot(0, run)

    def _belongs_to_registered_root(self, target: QObject) -> bool:
        current: QObject | None = target
        while current is not None:
            if current in self._roots:
                return True
            current = current.parent()
        return False

    @staticmethod
    def _objects_under(root: QObject) -> Iterable[QObject]:
        yield root
        yield from root.findChildren(QObject)

    def _semantic_for(self, target: QObject) -> str:
        hint = str(target.property(AUTOMATION_HINT_PROPERTY) or "").strip()
        if hint:
            return hint
        class_name = semantic_token(type(target).__name__, "control")
        stable_name = self._stable_name(target)
        return semantic_token(stable_name, class_name) if stable_name else class_name

    @staticmethod
    def _stable_name(target: QObject) -> str:
        if isinstance(target, QLineEdit) and target.echoMode() != QLineEdit.EchoMode.Normal:
            return "protected_input"
        for accessor in ("accessibleName", "objectName"):
            getter = getattr(target, accessor, None)
            if callable(getter):
                value = str(getter() or "").strip()
                if value:
                    return value
        if isinstance(target, QAbstractButton):
            return str(target.text() or target.toolTip() or "").strip()
        if isinstance(target, QAction):
            return str(target.text() or target.toolTip() or "").strip()
        if isinstance(target, QTabBar):
            return "_".join(target.tabText(index) for index in range(target.count()))
        if isinstance(target, (QLineEdit, QPlainTextEdit, QTextEdit)):
            return str(target.placeholderText() or "").strip()
        return ""

    @staticmethod
    def _visible_name(target: QObject) -> str:
        for accessor in (
            "accessibleName",
            "text",
            "currentText",
            "placeholderText",
            "title",
            "toolTip",
            "objectName",
        ):
            getter = getattr(target, accessor, None)
            if callable(getter):
                try:
                    value = str(getter() or "").strip()
                except (RuntimeError, TypeError):
                    continue
                if value:
                    return value
        if isinstance(target, QTabBar):
            return "_".join(target.tabText(index) for index in range(target.count()))
        return ""

    @staticmethod
    def _describe(target: QObject) -> str:
        return f"{type(target).__name__}({AutomationIdManager._visible_name(target)!r})"


def install_automation_ids(
    owner: object,
    context: str,
    *,
    roots: Iterable[tuple[QObject, str]] = (),
) -> AutomationIdManager:
    manager = AutomationIdManager(parent=owner if isinstance(owner, QObject) else None)
    manager.register_owner(owner, context)
    for root, root_context in roots:
        manager.register_root(root, root_context)
    manager.refresh()
    return manager
