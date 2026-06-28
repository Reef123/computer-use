"""Windows executor: real screenshot, UIA probe, and native input.

This module is safe to import on non-Windows hosts. Windows-only dependencies
are imported lazily by ``WinExecutor.__init__`` so the macOS test suite remains
stdlib-only.
"""
from __future__ import annotations

import base64
import io
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .types import EMPTY, Element, Observation, Vision, _Empty

LOGICAL_SIZE = (1024, 768)


class WinExecutor:
    """Executor implementation for one primary Windows display.

    The live computer-use tool is fixed at 1024x768. The VM may run at a larger
    native resolution, so screenshots are scaled down and action/probe points
    are scaled back up using one per-axis scale captured at construction.
    """

    def __init__(
        self,
        *,
        capture_dir: str | os.PathLike[str] = "captures",
        coord_space: tuple[int, int] = LOGICAL_SIZE,
        monitor_index: int = 1,
    ) -> None:
        if os.name != "nt":
            raise RuntimeError("WinExecutor requires Windows with a visible desktop")

        _enable_dpi_awareness()

        import mss  # type: ignore[import-not-found]
        from PIL import Image  # type: ignore[import-not-found]
        import uiautomation as auto  # type: ignore[import-not-found]

        self._mss_mod = mss
        self._image_mod = Image
        self._auto = auto
        self._sct = mss.mss()

        if monitor_index <= 0 or monitor_index >= len(self._sct.monitors):
            raise ValueError(
                f"monitor_index={monitor_index} is not available; "
                f"mss reported {len(self._sct.monitors) - 1} display(s)"
            )

        monitor = dict(self._sct.monitors[monitor_index])
        self._monitor = monitor
        self._left = int(monitor["left"])
        self._top = int(monitor["top"])
        self._real_w = int(monitor["width"])
        self._real_h = int(monitor["height"])
        self.coord_space = coord_space
        self._logical_w, self._logical_h = coord_space
        self._sx = self._real_w / self._logical_w
        self._sy = self._real_h / self._logical_h

        self.capture_dir = Path(capture_dir)
        self.capture_dir.mkdir(parents=True, exist_ok=True)
        self._capture_n = 0
        self._last_png: bytes | None = None
        self._last_path: Path | None = None

    @property
    def real_size(self) -> tuple[int, int]:
        return self._real_w, self._real_h

    @property
    def scale(self) -> tuple[float, float]:
        return self._sx, self._sy

    def screenshot(self) -> Observation:
        raw = self._sct.grab(self._monitor)
        image = self._image_mod.frombytes("RGB", raw.size, raw.rgb)
        resample = getattr(getattr(self._image_mod, "Resampling", self._image_mod), "LANCZOS")
        image = image.resize(self.coord_space, resample)

        buf = io.BytesIO()
        image.save(buf, format="PNG")
        self._last_png = buf.getvalue()

        self._capture_n += 1
        stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        path = self.capture_dir / f"win-frame-{stamp}-{self._capture_n:04d}.png"
        path.write_bytes(self._last_png)
        self._last_path = path

        return Observation(
            vision=Vision(str(path), self.coord_space),
            structure=None,
        )

    def screenshot_b64(self) -> str:
        if self._last_png is None:
            raise RuntimeError("screenshot_b64() called before screenshot(); no cached frame")
        return base64.b64encode(self._last_png).decode("ascii")

    def actuate(self, action: dict) -> str:
        kind = str(action.get("action", "") or "")
        try:
            if kind == "mouse_move":
                point = self._validated_real_point(action.get("coordinate"))
                if point is None:
                    return self._withheld(kind, action.get("coordinate"))
                self._auto.MoveTo(*point, moveSpeed=0, waitTime=0.05)
                return f"moved mouse to {action.get('coordinate')}"

            if kind == "cursor_position":
                x, y = self._auto.GetCursorPos()
                lx, ly = self._real_to_logical_point(x, y)
                return f"cursor at [{lx}, {ly}]"

            if kind == "wait":
                duration = float(action.get("duration", 1))
                if duration < 0:
                    return "withheld wait: negative duration"
                time.sleep(duration)
                return f"waited {duration:g}s"

            if kind in {"left_click", "right_click", "middle_click", "double_click", "triple_click"}:
                point = self._validated_real_point(action.get("coordinate"))
                if point is None:
                    return self._withheld(kind, action.get("coordinate"))
                self._click(kind, point)
                return f"executed {kind} at {action.get('coordinate')}"

            if kind == "left_click_drag":
                end = self._validated_real_point(action.get("coordinate"))
                if end is None:
                    return self._withheld(kind, action.get("coordinate"))
                start_coord = action.get("start_coordinate", action.get("from_coordinate"))
                if start_coord is None:
                    start = self._auto.GetCursorPos()
                else:
                    start = self._validated_real_point(start_coord)
                    if start is None:
                        return self._withheld(kind, start_coord)
                self._auto.DragDrop(start[0], start[1], end[0], end[1], moveSpeed=1, waitTime=0.05)
                return f"dragged left mouse to {action.get('coordinate')}"

            if kind == "left_mouse_down":
                point = self._validated_real_point(action.get("coordinate"))
                if point is None:
                    if action.get("coordinate") is not None:
                        return self._withheld(kind, action.get("coordinate"))
                    point = self._auto.GetCursorPos()
                self._auto.PressMouse(point[0], point[1], waitTime=0.05)
                return "left mouse down"

            if kind == "left_mouse_up":
                self._auto.ReleaseMouse(waitTime=0.05)
                return "left mouse up"

            if kind == "type":
                text = action.get("text")
                if not isinstance(text, str):
                    return "withheld type: missing text"
                self._auto.SendKeys(_literal_sendkeys(text), interval=0.01, waitTime=0.05)
                return f"typed {len(text)} character(s)"

            if kind == "key":
                text = action.get("text")
                if not isinstance(text, str) or not text.strip():
                    return "withheld key: missing text"
                keys = _key_to_sendkeys(text)
                self._auto.SendKeys(keys, interval=0.01, waitTime=0.05)
                return f"pressed key {text}"

            if kind == "scroll":
                point = self._validated_real_point(action.get("coordinate"))
                if point is None:
                    return self._withheld(kind, action.get("coordinate"))
                direction = str(action.get("scroll_direction", "") or "").strip().lower()
                amount = action.get("scroll_amount", 0)
                if not _is_plain_int(amount) or int(amount) < 0:
                    return f"withheld scroll: invalid scroll_amount {amount!r}"
                self._scroll(point, direction, int(amount))
                return f"scrolled {direction} by {int(amount)} at {action.get('coordinate')}"

            return f"Unknown action '{kind}' not executed."
        except Exception as exc:  # pragma: no cover - Windows-only defensive path
            return f"failed {kind}: {exc}"

    def probe(self, action: dict) -> tuple[Element, ...] | _Empty:
        point = self._validated_real_point(action.get("coordinate"))
        if point is None:
            return EMPTY

        try:
            control = self._auto.ControlFromPoint(*point)
        except Exception:
            return EMPTY
        if control is None:
            return EMPTY

        elements: list[Element] = []
        seen: set[tuple[str, str, tuple[int, int, int, int]]] = set()
        current = control
        for _ in range(4):
            element = self._element_from_control(current)
            if element is not None:
                key = (element.id, element.role, element.bounds)
                if key not in seen and self._is_usable(element):
                    elements.append(element)
                    seen.add(key)
            try:
                current = current.GetParentControl()
            except Exception:
                current = None
            if current is None:
                break

        return tuple(elements[:3]) if elements else EMPTY

    def _click(self, kind: str, point: tuple[int, int]) -> None:
        x, y = point
        if kind == "left_click":
            self._auto.Click(x, y, waitTime=0.05)
        elif kind == "right_click":
            self._auto.RightClick(x, y, waitTime=0.05)
        elif kind == "middle_click":
            self._auto.MiddleClick(x, y, waitTime=0.05)
        elif kind == "double_click":
            self._auto.Click(x, y, waitTime=0.03)
            self._auto.Click(x, y, waitTime=0.05)
        elif kind == "triple_click":
            self._auto.Click(x, y, waitTime=0.03)
            self._auto.Click(x, y, waitTime=0.03)
            self._auto.Click(x, y, waitTime=0.05)

    def _scroll(self, point: tuple[int, int], direction: str, amount: int) -> None:
        self._auto.MoveTo(*point, moveSpeed=0, waitTime=0.02)
        if amount == 0:
            return
        if direction == "up":
            self._auto.WheelUp(amount, interval=0.02, waitTime=0.05)
        elif direction == "down":
            self._auto.WheelDown(amount, interval=0.02, waitTime=0.05)
        elif direction in {"left", "right"}:
            delta = -120 if direction == "left" else 120
            for _ in range(amount):
                self._auto.mouse_event(self._auto.MouseEventFlag.HWheel, 0, 0, delta, 0)
                time.sleep(0.02)
            time.sleep(0.05)
        else:
            raise ValueError(f"unknown scroll_direction {direction!r}")

    def _validated_real_point(self, coord: Any) -> tuple[int, int] | None:
        if (
            not isinstance(coord, list)
            or len(coord) != 2
            or not _is_plain_int(coord[0])
            or not _is_plain_int(coord[1])
        ):
            return None

        x, y = int(coord[0]), int(coord[1])
        if not (0 <= x < self._logical_w and 0 <= y < self._logical_h):
            return None
        return self._logical_to_real_point(x, y)

    def _logical_to_real_point(self, x: int, y: int) -> tuple[int, int]:
        rx = self._left + round(x * self._sx)
        ry = self._top + round(y * self._sy)
        rx = min(max(rx, self._left), self._left + self._real_w - 1)
        ry = min(max(ry, self._top), self._top + self._real_h - 1)
        return rx, ry

    def _real_to_logical_point(self, x: int, y: int) -> tuple[int, int]:
        lx = round((x - self._left) / self._sx)
        ly = round((y - self._top) / self._sy)
        lx = min(max(lx, 0), self._logical_w - 1)
        ly = min(max(ly, 0), self._logical_h - 1)
        return lx, ly

    def _real_rect_to_logical_bounds(self, rect: Any) -> tuple[int, int, int, int]:
        left = min(max(round((int(rect.left) - self._left) / self._sx), 0), self._logical_w)
        top = min(max(round((int(rect.top) - self._top) / self._sy), 0), self._logical_h)
        right = min(max(round((int(rect.right) - self._left) / self._sx), 0), self._logical_w)
        bottom = min(max(round((int(rect.bottom) - self._top) / self._sy), 0), self._logical_h)
        return left, top, max(0, right - left), max(0, bottom - top)

    def _element_from_control(self, control: Any) -> Element | None:
        role = str(_safe_attr(control, "ControlTypeName", "") or "")
        name = str(_safe_attr(control, "Name", "") or "")
        automation_id = str(_safe_attr(control, "AutomationId", "") or "")
        class_name = str(_safe_attr(control, "ClassName", "") or "")
        rect = _safe_attr(control, "BoundingRectangle", None)
        if rect is None:
            return None
        bounds = self._real_rect_to_logical_bounds(rect)
        if bounds[2] <= 0 or bounds[3] <= 0:
            return None
        patterns = self._supported_patterns(control)
        marker = automation_id or f"{role}:{class_name}:{name}:{bounds}"
        return Element(
            id=marker,
            role=role,
            name=name,
            bounds=bounds,
            enabled=bool(_safe_attr(control, "IsEnabled", True)),
            offscreen=bool(_safe_attr(control, "IsOffscreen", False)),
            patterns=patterns,
        )

    def _supported_patterns(self, control: Any) -> tuple[str, ...]:
        names = (
            ("InvokePattern", "invoke"),
            ("ValuePattern", "value"),
            ("TogglePattern", "toggle"),
            ("SelectionItemPattern", "selectionitem"),
            ("SelectionPattern", "selection"),
            ("ExpandCollapsePattern", "expandcollapse"),
            ("RangeValuePattern", "rangevalue"),
            ("ScrollItemPattern", "scrollitem"),
            ("ScrollPattern", "scroll"),
            ("TextPattern", "text"),
            ("TextPattern2", "text2"),
            ("TextEditPattern", "textedit"),
        )
        found: list[str] = []
        for attr, label in names:
            pattern_id = getattr(self._auto.PatternId, attr, None)
            if pattern_id is None:
                continue
            try:
                if control.GetPattern(pattern_id) is not None:
                    found.append(label)
            except Exception:
                continue
        return tuple(found)

    def _is_usable(self, element: Element) -> bool:
        if element.offscreen:
            return False
        if element.role == "WindowControl":
            return False
        has_automation_id = not element.id.startswith(f"{element.role}:")
        if not element.name and not has_automation_id and not element.patterns:
            return False
        generic_roles = {"PaneControl", "GroupControl", "CustomControl"}
        if element.role in generic_roles and not element.patterns and not element.name and not has_automation_id:
            return False
        return True

    def _withheld(self, kind: str, coord: Any) -> str:
        return (
            f"withheld {kind}: invalid coordinate {coord!r}; "
            f"expected [x, y] within {self._logical_w}x{self._logical_h}"
        )


def _enable_dpi_awareness() -> None:
    try:
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _is_plain_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _safe_attr(obj: Any, attr: str, default: Any) -> Any:
    try:
        return getattr(obj, attr)
    except Exception:
        return default


def _literal_sendkeys(text: str) -> str:
    pieces: list[str] = []
    for char in text:
        if char == "\n":
            pieces.append("{Enter}")
        elif char == "\t":
            pieces.append("{Tab}")
        elif char == "{":
            pieces.append("{{}")
        elif char == "}":
            pieces.append("{}}")
        else:
            pieces.append(char)
    return "".join(pieces)


def _key_to_sendkeys(text: str) -> str:
    stripped = text.strip()
    if "+" in stripped:
        raw_parts = [part.strip() for part in stripped.split("+") if part.strip()]
    elif any(stripped.lower().startswith(prefix) for prefix in ("ctrl-", "control-", "alt-", "shift-", "win-", "super-")):
        raw_parts = [part.strip() for part in stripped.split("-") if part.strip()]
    else:
        raw_parts = [stripped]
    if not raw_parts:
        return ""

    modifiers: list[str] = []
    final: str | None = None
    for part in raw_parts:
        key = part.lower()
        if key in {"ctrl", "control"}:
            modifiers.append("{Ctrl}")
        elif key in {"alt", "option"}:
            modifiers.append("{Alt}")
        elif key == "shift":
            modifiers.append("{Shift}")
        elif key in {"cmd", "command", "meta", "super", "win", "windows"}:
            modifiers.append("{Win}")
        else:
            final = part

    if final is None:
        final = raw_parts[-1]
    return "".join(modifiers) + _single_key_to_sendkeys(final)


def _single_key_to_sendkeys(key: str) -> str:
    normalized = key.strip()
    lower = normalized.lower()
    aliases = {
        "return": "Enter",
        "enter": "Enter",
        "kp_enter": "Enter",
        "escape": "Esc",
        "esc": "Esc",
        "backspace": "Back",
        "delete": "Delete",
        "del": "Delete",
        "tab": "Tab",
        "space": "Space",
        "page_up": "PageUp",
        "pageup": "PageUp",
        "page_down": "PageDown",
        "pagedown": "PageDown",
        "left": "Left",
        "right": "Right",
        "up": "Up",
        "down": "Down",
        "home": "Home",
        "end": "End",
        "insert": "Insert",
        "ins": "Insert",
    }
    if lower in aliases:
        return "{" + aliases[lower] + "}"
    if len(normalized) == 1:
        return _literal_sendkeys(normalized)
    upper = normalized.upper()
    if upper.startswith("F") and upper[1:].isdigit():
        return "{" + upper + "}"
    return "{" + upper + "}"
