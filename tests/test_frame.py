import re
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib import admin
from django.contrib.staticfiles import finders
from django.template import Context, Template
from django.template.loader import render_to_string

VENDORED = [
    "vendor/htmx-2.0.11.min.js",
    "vendor/basecoat-1.1.0/basecoat.min.js",
    "vendor/basecoat-1.1.0/dropdown-menu.min.js",
    "vendor/basecoat-1.1.0/toast.min.js",
    "fonts/inter-latin-wght-normal.woff2",
    "fonts/montserrat-latin-700-normal.woff2",
    "fonts/montserrat-latin-800-normal.woff2",
    "brand/stryde-logo.svg",
    "brand/stryde-logo-one-color.svg",
    "brand/stryde-monogram.svg",
]


def test_vendored_files_exist():
    for path in VENDORED:
        assert finders.find(path), path


def test_base_loads_local_assets_only():
    html = render_to_string("base.html")
    for path in ["css/stryde.css", *VENDORED[:5], "brand/stryde-monogram.svg"]:
        assert path in html, path
    assert "jsdelivr" not in html and "googleapis" not in html and "unpkg" not in html


def test_base_title_suffix():
    html = Template(
        '{% extends "base.html" %}{% block title %}My Events{% endblock %}'
    ).render(Context())
    assert "<title>My Events · Stryde</title>" in html


def test_icon_tag_inlines_svg():
    out = Template('{% load ui %}{% icon "plus" class="size-4" %}').render(Context())
    assert out.lstrip().startswith("<svg")
    assert 'class="lucide lucide-plus size-4"' in out
    assert 'aria-hidden="true"' in out
    assert "@license" not in out


def test_icon_tag_unknown_name_raises():
    with pytest.raises(ValueError, match="Unknown icon: nope"):
        Template('{% load ui %}{% icon "nope" %}').render(Context())


def test_theme_tokens_match_spec():
    css = Path(settings.BASE_DIR, "frontend", "stryde.css").read_text().lower()
    for token, value in [
        ("--color-ink", "#0b1a4a"),
        ("--color-brand", "#0b3dcc"),
        ("--color-progress", "#14e2b8"),
        ("--color-action", "#ff7a3d"),
        ("--color-surface", "#f6f8fc"),
        ("--color-warn", "#8a5a00"),
        ("--color-warn-bg", "#fff4e0"),
        ("--color-danger", "#e5484d"),
        ("--card", "#ffffff"),
        ("--border", "#e3e8f2"),
    ]:
        assert f"{token}: {value};" in css, token


def test_templates_use_no_raw_hex():
    hexcolor = re.compile(r"#[0-9A-Fa-f]{6}\b")
    for path in Path(settings.BASE_DIR, "templates").rglob("*.html"):
        assert not hexcolor.search(path.read_text(encoding="utf-8")), path


def test_admin_header_is_stryde():
    assert admin.site.site_header == "Stryde"
