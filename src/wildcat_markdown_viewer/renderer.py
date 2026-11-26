"""Markdown -> HTML with GitHub-flavoured features plus D2 diagrams.

Supported:
  * CommonMark + GFM: tables, strikethrough, autolinks (linkify), task lists, raw HTML
  * footnotes, YAML front matter, heading anchors (GitHub slugs)
  * GitHub alerts: > [!NOTE] / [!TIP] / [!IMPORTANT] / [!WARNING] / [!CAUTION]
  * emoji shortcodes (:tada:)
  * math: $inline$, $$block$$ and ```math fences (rendered client-side by KaTeX)
  * ```mermaid fences (rendered client-side by Mermaid)
  * ```d2 fences (rendered to SVG by the d2 CLI)
  * syntax highlighting via Pygments
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from urllib.parse import quote, unquote

import emoji
from markdown_it import MarkdownIt
from markdown_it.rules_core import StateCore
from markdown_it.token import Token
from mdit_py_plugins.anchors import anchors_plugin
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.front_matter import front_matter_plugin
from mdit_py_plugins.tasklists import tasklists_plugin
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

from .d2render import render_d2


@dataclass
class RenderEnv:
    theme: str = "auto"            # auto | light | dark  (used for D2)
    base_dir: Path | None = None   # directory of the document (D2 imports, abs paths)
    doc_prefix: str = "/doc/"      # URL prefix that maps to local files
    stats: dict[str, int] = field(default_factory=lambda: {"d2": 0, "mermaid": 0})


# --------------------------------------------------------------------------- slugs

def github_slug(title: str) -> str:
    slug = title.strip().lower()
    slug = re.sub(r"[^\w\- ]", "", slug, flags=re.UNICODE)
    return slug.replace(" ", "-")


# --------------------------------------------------------------------------- alerts

ALERT_RE = re.compile(r"^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\][ \t]*(?:\n|$)", re.IGNORECASE)

ALERT_ICONS = {
    "note": "M0 8a8 8 0 1 1 16 0A8 8 0 0 1 0 8Zm8-6.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13ZM6.5 7.75A.75.75 0 0 1 7.25 7h1a.75.75 0 0 1 .75.75v2.75h.25a.75.75 0 0 1 0 1.5h-2a.75.75 0 0 1 0-1.5h.25v-2h-.25a.75.75 0 0 1-.75-.75ZM8 6a1 1 0 1 1 0-2 1 1 0 0 1 0 2Z",
    "tip": "M8 1.5c-2.363 0-4 1.69-4 3.75 0 .984.424 1.625.984 2.304l.214.253c.223.264.47.556.673.848.284.411.537.896.621 1.49a.75.75 0 0 1-1.484.211c-.04-.282-.163-.547-.37-.847a8.456 8.456 0 0 0-.542-.68c-.084-.1-.173-.205-.268-.32C3.201 7.75 2.5 6.766 2.5 5.25 2.5 2.31 4.863 0 8 0s5.5 2.31 5.5 5.25c0 1.516-.701 2.5-1.328 3.259-.095.115-.184.22-.268.319-.207.245-.383.453-.541.681-.208.3-.33.565-.37.847a.751.751 0 0 1-1.485-.212c.084-.593.337-1.078.621-1.489.203-.292.45-.584.673-.848.075-.088.147-.173.213-.253.561-.679.985-1.32.985-2.304 0-2.06-1.637-3.75-4-3.75ZM5.75 12h4.5a.75.75 0 0 1 0 1.5h-4.5a.75.75 0 0 1 0-1.5ZM6 15.25a.75.75 0 0 1 .75-.75h2.5a.75.75 0 0 1 0 1.5h-2.5a.75.75 0 0 1-.75-.75Z",
    "important": "M0 1.75C0 .784.784 0 1.75 0h12.5C15.216 0 16 .784 16 1.75v9.5A1.75 1.75 0 0 1 14.25 13H8.06l-2.573 2.573A1.458 1.458 0 0 1 3 14.543V13H1.75A1.75 1.75 0 0 1 0 11.25Zm1.75-.25a.25.25 0 0 0-.25.25v9.5c0 .138.112.25.25.25h2a.75.75 0 0 1 .75.75v2.19l2.72-2.72a.749.749 0 0 1 .53-.22h6.5a.25.25 0 0 0 .25-.25v-9.5a.25.25 0 0 0-.25-.25Zm7 2.25v2.5a.75.75 0 0 1-1.5 0v-2.5a.75.75 0 0 1 1.5 0ZM9 9a1 1 0 1 1-2 0 1 1 0 0 1 2 0Z",
    "warning": "M6.457 1.047c.659-1.234 2.427-1.234 3.086 0l6.082 11.378A1.75 1.75 0 0 1 14.082 15H1.918a1.75 1.75 0 0 1-1.543-2.575Zm1.763.707a.25.25 0 0 0-.44 0L1.698 13.132a.25.25 0 0 0 .22.368h12.164a.25.25 0 0 0 .22-.368Zm.53 3.996v2.5a.75.75 0 0 1-1.5 0v-2.5a.75.75 0 0 1 1.5 0ZM9 11a1 1 0 1 1-2 0 1 1 0 0 1 2 0Z",
    "caution": "M4.47.22A.749.749 0 0 1 5 0h6c.199 0 .389.079.53.22l4.25 4.25c.141.14.22.331.22.53v6a.749.749 0 0 1-.22.53l-4.25 4.25A.749.749 0 0 1 11 16H5a.749.749 0 0 1-.53-.22L.22 11.53A.749.749 0 0 1 0 11V5c0-.199.079-.389.22-.53Zm.84 1.28L1.5 5.31v5.38l3.81 3.81h5.38l3.81-3.81V5.31L10.69 1.5ZM8 4a.75.75 0 0 1 .75.75v3.5a.75.75 0 0 1-1.5 0v-3.5A.75.75 0 0 1 8 4Zm0 8a1 1 0 1 1 0-2 1 1 0 0 1 0 2Z",
}


def _alerts_rule(state: StateCore) -> None:
    """Turn blockquotes starting with [!KIND] into GitHub alert containers."""
    tokens = state.tokens
    out: list[Token] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if (
            tok.type == "blockquote_open"
            and i + 2 < len(tokens)
            and tokens[i + 1].type == "paragraph_open"
            and tokens[i + 2].type == "inline"
            and (m := ALERT_RE.match(tokens[i + 2].content))
        ):
            kind = m.group(1).lower()
            tok.meta["alert"] = kind
            # Tag the matching close token.
            depth = 0
            for j in range(i + 1, len(tokens)):
                if tokens[j].type == "blockquote_open":
                    depth += 1
                elif tokens[j].type == "blockquote_close":
                    if depth == 0:
                        tokens[j].meta["alert"] = kind
                        break
                    depth -= 1
            inline = tokens[i + 2]
            inline.content = inline.content[m.end():]
            out.append(tok)
            if inline.content.strip():
                out.extend(tokens[i + 1:i + 3])
                i += 3
            else:  # marker was alone in its paragraph: drop the empty <p>
                i += 4  # blockquote_open, paragraph_open, inline, paragraph_close
            continue
        out.append(tok)
        i += 1
    state.tokens = out


# --------------------------------------------------------------------------- inline post-processing

WIN_ABS_RE = re.compile(r"^/?[A-Za-z]:[\\/]")


def _local_url(href: str, prefix: str) -> str | None:
    """Rewrite absolute Windows paths so the embedded server can serve them."""
    raw = unquote(href)
    if WIN_ABS_RE.match(raw):
        return prefix + quote(raw.lstrip("/").replace("\\", "/"), safe="/:#?&=")
    return None


def _inline_rule(state: StateCore) -> None:
    env: RenderEnv | None = state.env.get("render_env") if isinstance(state.env, dict) else None
    prefix = env.doc_prefix if env else "/doc/"
    for block in state.tokens:
        if block.type != "inline" or not block.children:
            continue
        in_link = 0
        for child in block.children:
            if child.type == "link_open":
                in_link += 1
                href = child.attrGet("href")
                if isinstance(href, str) and (new := _local_url(href, prefix)):
                    child.attrSet("href", new)
            elif child.type == "link_close":
                in_link -= 1
            elif child.type == "image":
                src = child.attrGet("src")
                if isinstance(src, str) and (new := _local_url(src, prefix)):
                    child.attrSet("src", new)
            elif child.type == "text" and ":" in child.content:
                child.content = emoji.emojize(child.content, language="alias")


# --------------------------------------------------------------------------- render rules

_FORMATTER = HtmlFormatter(nowrap=True)


def _highlight(code: str, lang: str) -> str:
    if lang:
        try:
            lexer = get_lexer_by_name(lang, stripnl=False, ensurenl=False)
            return highlight(code, lexer, _FORMATTER)
        except ClassNotFound:
            pass
    return escape(code)


def _get_env(env) -> RenderEnv:
    if isinstance(env, dict) and isinstance(env.get("render_env"), RenderEnv):
        return env["render_env"]
    return RenderEnv()


def _render_fence(self, tokens, idx, options, env) -> str:
    token = tokens[idx]
    info = token.info.strip()
    words = info.split()
    lang = words[0].lower() if words else ""
    code = token.content
    renv = _get_env(env)

    if lang == "mermaid":
        renv.stats["mermaid"] += 1
        return f'<div class="mermaid-diagram"><pre class="mermaid">{escape(code)}</pre></div>\n'

    if lang == "math":
        return f'<div class="math block">{escape(code)}</div>\n'

    if lang == "d2":
        renv.stats["d2"] += 1
        result = render_d2(code, words[1:], renv.theme, renv.base_dir)
        if result.svg is not None:
            return f'<div class="d2-diagram">{result.svg}</div>\n'
        return (
            '<div class="render-error"><div class="render-error-title">D2 diagram error</div>'
            f"<pre>{escape(result.error or '')}</pre>"
            f'<details><summary>Source</summary><pre><code>{escape(code)}</code></pre></details></div>\n'
        )

    css_lang = re.sub(r"[^\w+-]", "", lang)
    body = _highlight(code, lang)
    return (
        f'<div class="highlight highlight-source-{css_lang}" data-lang="{escape(lang)}">'
        f"<pre><code>{body}</code></pre></div>\n"
    )


def _render_code_block(self, tokens, idx, options, env) -> str:
    return f'<div class="highlight"><pre><code>{escape(tokens[idx].content)}</code></pre></div>\n'


def _render_blockquote_open(self, tokens, idx, options, env) -> str:
    kind = tokens[idx].meta.get("alert")
    if not kind:
        return self.renderToken(tokens, idx, options, env)
    icon = ALERT_ICONS[kind]
    return (
        f'<div class="markdown-alert markdown-alert-{kind}" dir="auto">'
        f'<p class="markdown-alert-title" dir="auto">'
        f'<svg class="octicon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="{icon}"></path></svg>'
        f"{kind.capitalize()}</p>\n"
    )


def _render_blockquote_close(self, tokens, idx, options, env) -> str:
    if tokens[idx].meta.get("alert"):
        return "</div>\n"
    return self.renderToken(tokens, idx, options, env)


def _render_heading_open(self, tokens, idx, options, env) -> str:
    html = self.renderToken(tokens, idx, options, env)
    hid = tokens[idx].attrGet("id")
    if hid:
        html += (
            f'<a class="anchor" aria-hidden="true" tabindex="-1" href="#{escape(str(hid))}">'
            '<span class="octicon octicon-link"></span></a>'
        )
    return html


def _render_front_matter(self, tokens, idx, options, env) -> str:
    content = tokens[idx].content
    return (
        '<details class="front-matter" open><summary>Front matter</summary>'
        f'<div class="highlight highlight-source-yaml"><pre><code>{_highlight(content, "yaml")}</code></pre></div>'
        "</details>\n"
    )


# --------------------------------------------------------------------------- public API

def build_markdown() -> MarkdownIt:
    md = MarkdownIt("gfm-like", {"html": True, "linkify": True, "typographer": False})
    md.use(front_matter_plugin)
    md.use(footnote_plugin)
    md.use(tasklists_plugin, enabled=False)
    md.use(dollarmath_plugin, allow_space=True, allow_digits=False, double_inline=True,
           allow_labels=False)
    md.use(anchors_plugin, min_level=1, max_level=6, slug_func=github_slug, permalink=False)

    md.core.ruler.after("block", "gh_alerts", _alerts_rule)
    md.core.ruler.push("wildcat_inline", _inline_rule)

    md.add_render_rule("fence", _render_fence)
    md.add_render_rule("code_block", _render_code_block)
    md.add_render_rule("blockquote_open", _render_blockquote_open)
    md.add_render_rule("blockquote_close", _render_blockquote_close)
    md.add_render_rule("heading_open", _render_heading_open)
    md.add_render_rule("front_matter", _render_front_matter)
    return md


_MD = build_markdown()


def render_markdown(text: str, env: RenderEnv) -> str:
    if text.startswith("﻿"):
        text = text[1:]
    return _MD.render(text, {"render_env": env})


def first_heading(text: str) -> str | None:
    m = re.search(r"^#{1,2}\s+(.+?)\s*#*\s*$", text, flags=re.MULTILINE)
    if not m:
        return None
    title = re.sub(r"[*_`~]|<[^>]+>", "", m.group(1)).strip()
    return emoji.emojize(title, language="alias") or None


# --------------------------------------------------------------------------- pygments CSS

def pygments_css() -> str:
    """Syntax colours for light and dark themes, scoped by <html data-theme>."""

    def defs(style: str, scope: str) -> str:
        css = HtmlFormatter(style=style).get_style_defs(scope)
        keep = []
        for ln in css.splitlines():
            if ln.startswith(("pre ", "td.linenos", "span.linenos")):
                continue
            if ln.startswith(scope + " {"):  # block background: keep GitHub's own
                continue
            keep.append(ln)
        return "\n".join(keep)

    light = defs("default", ".markdown-body .highlight")
    dark = defs("github-dark", ".markdown-body .highlight")
    return (
        _scope(light, "html[data-theme=light] ")
        + _scope(dark, "html[data-theme=dark] ")
        + "@media (prefers-color-scheme: light) {\n" + _scope(light, "html[data-theme=auto] ") + "}\n"
        + "@media (prefers-color-scheme: dark) {\n" + _scope(dark, "html[data-theme=auto] ") + "}\n"
    )


def _scope(css: str, prefix: str) -> str:
    out = []
    for line in css.splitlines():
        if "{" in line:
            sel, rest = line.split("{", 1)
            sel = ", ".join(prefix + s.strip() for s in sel.split(",") if s.strip())
            out.append(f"{sel} {{{rest}")
        else:
            out.append(line)
    return "\n".join(out) + "\n"
