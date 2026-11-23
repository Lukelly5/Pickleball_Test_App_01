"""Frame-level template tags for Stryde."""
import re
from functools import lru_cache
from pathlib import Path

from django import template
from django.utils.html import escape
from django.utils.safestring import SafeString, mark_safe

register = template.Library()

ICON_DIR = Path(__file__).resolve().parent.parent / "icons"
_NAME = re.compile(r"[a-z0-9-]+")
_LICENSE = re.compile(r"<!--.*?-->\s*", re.S)


@lru_cache(maxsize=None)
def _svg(name: str) -> str:
    if not _NAME.fullmatch(name):
        raise ValueError(f"Unknown icon: {name}")
    path = ICON_DIR / f"{name}.svg"
    if not path.is_file():
        raise ValueError(f"Unknown icon: {name}")
    return _LICENSE.sub("", path.read_text(encoding="utf-8")).strip()


@register.simple_tag
def icon(name: str, **kwargs) -> SafeString:
    """Inline a Lucide icon: {% icon "plus" class="size-4" %}."""
    svg = _svg(name)
    base = f'class="lucide lucide-{name}"'
    extra = kwargs.get("class", "")
    classes = f'class="lucide lucide-{name} {escape(extra)}"' if extra else base
    svg = svg.replace(base, f'{classes} aria-hidden="true"', 1)
    return mark_safe(svg)
