# Copyright 2026, Aurélien ROY, <aurroy@hotmail.com>
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

"""A small LaTeX-ish markup for every plot text (titles, axis labels,
legend entries, annotation text), rendered to Qt rich text + Unicode --
no new dependency, no matplotlib mathtext (round-2 decision 1).

The SOURCE string is what the app stores, edits and serializes; to_html()
is only ever applied at display time. Supported:

  \\textbf{..} \\mathbf{..}           bold
  \\textit{..} \\mathit{..} \\emph{..}  italic
  \\textrm{..} \\mathrm{..}           upright (just the group)
  \\textcolor{red}{..}  \\textcolor{#ff8800}{..}   color
  x^{2}  x_{i}                      super/subscript -- braces REQUIRED:
                                    a bare ^ or _ stays literal, so plain
                                    names like "sensor_1" or "_nolegend_"
                                    never turn into subscripts
  \\alpha .. \\omega, \\Gamma .. \\Omega, \\times \\leq \\geq \\pm \\infty ...
                                    Unicode (see SYMBOLS)
  \\{ \\} \\_ \\^ \\\\ \\$ \\% \\& \\#     the literal character
  \\,  \\;  \\quad                     thin / medium / em space
  a real newline                    a line break (<br>)
  {..}                              a plain group (braces dropped)

Anything else -- an unknown command such as \\notarealcommand, an
unmatched brace, a style command with no {argument} -- renders literally,
exactly as typed; nothing here ever raises. Out of scope by design:
fractions, integrals, matrices, sqrt with a radicand -- real LaTeX math.

The HTML uses only <b> <i> <sup> <sub> <br> <span style="color:.."> and
entities, which is also the subset plotly's own text rendering accepts --
so to_html() doubles as the HTML-export (plotly) converter.
"""
import html
import re

GREEK = {
    'alpha': 'α', 'beta': 'β', 'gamma': 'γ', 'delta': 'δ', 'epsilon': 'ϵ',
    'varepsilon': 'ε', 'zeta': 'ζ', 'eta': 'η', 'theta': 'θ', 'vartheta': 'ϑ',
    'iota': 'ι', 'kappa': 'κ', 'lambda': 'λ', 'mu': 'μ', 'nu': 'ν', 'xi': 'ξ',
    'omicron': 'ο', 'pi': 'π', 'varpi': 'ϖ', 'rho': 'ρ', 'varrho': 'ϱ',
    'sigma': 'σ', 'varsigma': 'ς', 'tau': 'τ', 'upsilon': 'υ', 'phi': 'ϕ',
    'varphi': 'φ', 'chi': 'χ', 'psi': 'ψ', 'omega': 'ω',
    'Gamma': 'Γ', 'Delta': 'Δ', 'Theta': 'Θ', 'Lambda': 'Λ', 'Xi': 'Ξ',
    'Pi': 'Π', 'Sigma': 'Σ', 'Upsilon': 'Υ', 'Phi': 'Φ', 'Psi': 'Ψ',
    'Omega': 'Ω',
}

MATH = {
    'times': '×', 'cdot': '·', 'div': '÷', 'pm': '±', 'mp': '∓',
    'leq': '≤', 'le': '≤', 'geq': '≥', 'ge': '≥', 'neq': '≠', 'ne': '≠',
    'll': '≪', 'gg': '≫', 'approx': '≈', 'simeq': '≃', 'sim': '∼',
    'equiv': '≡', 'propto': '∝', 'infty': '∞', 'partial': '∂', 'nabla': '∇',
    'sum': '∑', 'prod': '∏', 'int': '∫', 'oint': '∮', 'sqrt': '√',
    'degree': '°', 'circ': '∘', 'bullet': '•', 'star': '⋆', 'ast': '∗',
    'to': '→', 'rightarrow': '→', 'leftarrow': '←', 'leftrightarrow': '↔',
    'Rightarrow': '⇒', 'Leftarrow': '⇐', 'Leftrightarrow': '⇔',
    'uparrow': '↑', 'downarrow': '↓', 'mapsto': '↦',
    'in': '∈', 'notin': '∉', 'ni': '∋', 'subset': '⊂', 'supset': '⊃',
    'subseteq': '⊆', 'supseteq': '⊇', 'cup': '∪', 'cap': '∩',
    'emptyset': '∅', 'forall': '∀', 'exists': '∃', 'neg': '¬',
    'wedge': '∧', 'vee': '∨', 'oplus': '⊕', 'otimes': '⊗',
    'perp': '⊥', 'parallel': '∥', 'angle': '∠', 'triangle': '△',
    'ell': 'ℓ', 'hbar': 'ℏ', 'Re': 'ℜ', 'Im': 'ℑ', 'aleph': 'ℵ',
    'prime': '′', 'ldots': '…', 'dots': '…', 'cdots': '⋯', 'vdots': '⋮',
    'langle': '⟨', 'rangle': '⟩', 'lfloor': '⌊', 'rfloor': '⌋',
    'lceil': '⌈', 'rceil': '⌉', 'AA': 'Å', 'permil': '‰',
    'quad': ' ',
}

SYMBOLS = {**GREEK, **MATH}

# \X for a non-letter X: the literal character (or a small space).
ESCAPES = {'{': '{', '}': '}', '_': '_', '^': '^', '\\': '\\', '$': '$',
           '%': '%', '&': '&', '#': '#', ',': ' ', ';': ' ', ' ': ' '}

# One-argument style commands -> the HTML tag wrapping their argument
# (None: just the group, no tag).
STYLE_COMMANDS = {'textbf': 'b', 'mathbf': 'b', 'textit': 'i', 'mathit': 'i',
                  'emph': 'i', 'textrm': None, 'mathrm': None, 'text': None}

_COLOR_ARG = re.compile(r'\{\s*(#[0-9A-Fa-f]{3,8}|[A-Za-z]+)\s*\}')
_NAME = re.compile(r'[A-Za-z]+')


class _Renderer:
    """Recursive-descent translator over one source string. Every
    _parse_* returns (html, next_index); a construct it can't complete
    is emitted as the literal text it came from."""

    def __init__(self, src):
        self.src = src

    def render(self):
        out, _i, _closed = self._parse(0, in_group=False)
        return out

    def _parse(self, i, in_group):
        """Parse from i up to the end, or (in_group) up to the matching
        '}' -- returns (html, index after it, whether it was closed)."""
        src, parts = self.src, []
        while i < len(src):
            c = src[i]
            if c == '}':
                if in_group:
                    return ''.join(parts), i + 1, True
                parts.append('}')  # unmatched: literal
                i += 1
            elif c == '{':
                inner, j, closed = self._parse(i + 1, in_group=True)
                if closed:
                    parts.append(inner)
                    i = j
                else:
                    parts.append('{')
                    i += 1
            elif c == '\\':
                text, i = self._parse_command(i)
                parts.append(text)
            elif c in '^_' and src.startswith('{', i + 1):
                inner, j, closed = self._parse(i + 2, in_group=True)
                if closed:
                    tag = 'sup' if c == '^' else 'sub'
                    parts.append(f'<{tag}>{inner}</{tag}>')
                    i = j
                else:
                    parts.append(html.escape(c))
                    i += 1
            elif c == '\n':
                parts.append('<br>')
                i += 1
            elif c == ' ':
                # HTML collapses runs of spaces; keep them as typed.
                parts.append('&nbsp;' if not parts or parts[-1] in (' ', '&nbsp;', '<br>') else ' ')
                i += 1
            else:
                parts.append(html.escape(c))
                i += 1
        return ''.join(parts), i, False

    def _group_at(self, i):
        """(html, next_index) of a '{..}' group starting exactly at i, or
        None if there is none (or it never closes)."""
        if not self.src.startswith('{', i):
            return None
        inner, j, closed = self._parse(i + 1, in_group=True)
        return (inner, j) if closed else None

    def _parse_command(self, i):
        src = self.src
        m = _NAME.match(src, i + 1)
        if m is None:
            if i + 1 < len(src) and src[i + 1] in ESCAPES:
                return html.escape(ESCAPES[src[i + 1]]), i + 2
            return html.escape('\\'), i + 1  # a lone or unknown \X: literal
        name, j = m.group(0), m.end()
        literal = html.escape(src[i:j])
        if name in SYMBOLS:
            return SYMBOLS[name], j
        if name in STYLE_COMMANDS:
            group = self._group_at(j)
            if group is None:
                return literal, j
            inner, k = group
            tag = STYLE_COMMANDS[name]
            return (f'<{tag}>{inner}</{tag}>' if tag else inner), k
        if name in ('textcolor', 'color'):
            cm = _COLOR_ARG.match(src, j)
            group = self._group_at(cm.end()) if cm else None
            if group is None:
                return literal, j
            inner, k = group
            return f'<span style="color:{cm.group(1)}">{inner}</span>', k
        # Unknown command: exactly as typed, braces of its argument included.
        group = self._group_at(j)
        if group is not None:
            inner, k = group
            return f'{literal}{{{inner}}}', k
        return literal, j


def to_html(source):
    """The rich-text HTML for a source string (see the module docstring).
    Never raises; None renders as ''."""
    if not source:
        return ''
    return _Renderer(str(source)).render()


# plotly accepts the same tag subset (see the module docstring).
to_plotly = to_html


_SUPERSCRIPT = str.maketrans('0123456789+-=()ni', '⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ')
_SUBSCRIPT = str.maketrans('0123456789+-=()', '₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎')
_TAG = re.compile(r'<(/?)(sup|sub|b|i|br|span)\b[^>]*>')


def to_plain(source):
    """A plain-Unicode approximation, for places that can't show HTML (a
    tree row, a window title, a CSV header): markup dropped, symbols kept,
    super/subscripts as Unicode where every character has one, else as
    ^(..)/_(..), line breaks as spaces."""
    rendered = to_html(source)
    out, stack, i = [], [], 0
    for m in _TAG.finditer(rendered):
        out.append(rendered[i:m.start()])
        i = m.end()
        closing, tag = m.group(1), m.group(2)
        if tag == 'br':
            out.append(' ')
        elif tag in ('sup', 'sub'):
            if not closing:
                stack.append((tag, len(out)))
            elif stack:
                kind, start = stack.pop()
                inner = html.unescape(''.join(out[start:]))
                del out[start:]
                table = _SUPERSCRIPT if kind == 'sup' else _SUBSCRIPT
                if all(ord(ch) in table for ch in inner):
                    out.append(html.escape(inner.translate(table)))
                else:
                    out.append(html.escape(('^(%s)' if kind == 'sup' else '_(%s)') % inner))
    out.append(rendered[i:])
    return html.unescape(''.join(out))
