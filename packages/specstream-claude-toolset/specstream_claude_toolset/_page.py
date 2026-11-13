"""What the driver runs inside a page: the tagged element tree behind `read_page` and `find`, and the
key names Claude writes turned into the names Playwright presses."""

from __future__ import annotations

from anthropic.tools import ToolError

READ_LIMIT = 50_000
TEXT_LIMIT = 100_000
FIND_LIMIT = 20

# Walks the DOM and returns {lines: [{depth, role, name, ref}]}. An element keeps its reference for
# the life of the document (window.__ssRefs), so a second read never renumbers one Claude holds; a
# navigation makes a new document, and the old references answer "stale".
TREE_SCRIPT = r"""
(opts) => {
  const w = window;
  if (!w.__ssRefs) { w.__ssRefs = new Map(); w.__ssRefOf = new WeakMap(); w.__ssNext = 1; }
  const refOf = (el) => {
    let ref = w.__ssRefOf.get(el);
    if (!ref) { ref = 'ref_' + (w.__ssNext++); w.__ssRefOf.set(el, ref); w.__ssRefs.set(ref, el); }
    return ref;
  };
  const INTERACTIVE = new Set(['a', 'button', 'input', 'select', 'textarea', 'summary', 'option']);
  const ROLES = {a: 'link', button: 'button', select: 'combobox', textarea: 'textbox', img: 'image',
    h1: 'heading', h2: 'heading', h3: 'heading', h4: 'heading', h5: 'heading', h6: 'heading',
    nav: 'navigation', main: 'main', form: 'form', table: 'table', li: 'listitem', ul: 'list',
    ol: 'list', summary: 'button', option: 'option', label: 'label', p: 'paragraph', td: 'cell',
    th: 'columnheader', tr: 'row', iframe: 'iframe', dialog: 'dialog'};
  const INPUTS = {checkbox: 'checkbox', radio: 'radio', button: 'button', submit: 'button',
    reset: 'button', range: 'slider', search: 'searchbox', file: 'file input'};
  const roleOf = (el) => {
    const given = el.getAttribute('role');
    if (given) return given;
    const tag = el.tagName.toLowerCase();
    if (tag === 'input') return INPUTS[(el.getAttribute('type') || 'text').toLowerCase()] || 'textbox';
    return ROLES[tag] || null;
  };
  const interactive = (el) => {
    const tag = el.tagName.toLowerCase();
    if (tag === 'a') return el.hasAttribute('href');
    if (INTERACTIVE.has(tag)) return true;
    if (el.hasAttribute('onclick') || el.isContentEditable) return true;
    const tab = el.getAttribute('tabindex');
    if (tab !== null && tab !== '-1') return true;
    const role = el.getAttribute('role');
    return !!role && ['button', 'link', 'tab', 'menuitem', 'checkbox', 'radio', 'switch', 'option',
      'combobox', 'textbox', 'searchbox', 'slider'].includes(role);
  };
  const clean = (text) => (text || '').replace(/\s+/g, ' ').trim().slice(0, 120);
  const ownText = (el) => {
    let text = '';
    for (const node of el.childNodes) if (node.nodeType === 3) text += node.nodeValue;
    return clean(text);
  };
  const nameOf = (el, role) => {
    const label = el.getAttribute('aria-label') || el.getAttribute('alt') || el.getAttribute('title');
    if (label) return clean(label);
    const tag = el.tagName.toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') {
      if (el.labels && el.labels.length) return clean(el.labels[0].innerText);
      return clean(el.getAttribute('placeholder') || el.getAttribute('name') || el.value);
    }
    if (role === 'link' || role === 'button' || role === 'heading' || role === 'option' ||
        role === 'tab' || role === 'menuitem' || role === 'label') return clean(el.innerText);
    return ownText(el);
  };
  const shown = (el) => {
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') return 'hidden';
    const box = el.getBoundingClientRect();
    if (box.width === 0 && box.height === 0) return 'empty';
    const inView = box.bottom > 0 && box.right > 0 && box.top < innerHeight && box.left < innerWidth;
    return inView ? 'view' : 'away';
  };
  const SKIP = new Set(['script', 'style', 'noscript', 'template', 'head', 'meta', 'link', 'svg', 'path']);
  const lines = [];
  const walk = (el, depth) => {
    if (lines.length >= opts.maxLines) return;
    const tag = el.tagName.toLowerCase();
    if (SKIP.has(tag)) return;
    const state = shown(el);
    if (state === 'hidden') return;
    let next = depth;
    const role = roleOf(el);
    const active = interactive(el);
    const visible = state === 'view' || (opts.filter === 'all' && state !== 'empty');
    if (visible && (opts.filter === 'interactive' ? active : (role || active))) {
      const name = nameOf(el, role);
      if (active || name || role === 'image' || role === 'iframe') {
        if (depth <= opts.depth) {
          const line = {depth, role: role || 'generic', name, ref: refOf(el)};
          if (tag === 'input' || tag === 'textarea' || tag === 'select') {
            const type = (el.getAttribute('type') || '').toLowerCase();
            if (type === 'checkbox' || type === 'radio') line.value = el.checked ? 'checked' : 'unchecked';
            else if (type !== 'password') line.value = clean(el.value);
          }
          if (tag === 'a') line.href = (el.getAttribute('href') || '').slice(0, 200);
          lines.push(line);
        }
        next = depth + 1;
      }
    }
    if (next > opts.depth) return;
    for (const child of el.children) walk(child, next);
    if (el.shadowRoot) for (const child of el.shadowRoot.children) walk(child, next);
  };
  let root = document.body || document.documentElement;
  if (opts.ref) {
    root = w.__ssRefs.get(opts.ref);
    if (!root || !root.isConnected) return {stale: true, lines: []};
  }
  if (root) walk(root, 1);
  return {stale: false, lines};
}
"""

ELEMENT_SCRIPT = (
    "(ref) => { const el = window.__ssRefs && window.__ssRefs.get(ref); return el && el.isConnected ? el : null; }"
)

TEXT_SCRIPT = r"""
() => {
  const main = document.querySelector('article, main, [role="main"]');
  const pick = main && main.innerText && main.innerText.trim().length > 200 ? main : document.body;
  return pick ? pick.innerText : '';
}
"""

KIND_SCRIPT = "(el) => ({tag: el.tagName.toLowerCase(), type: (el.getAttribute('type') || '').toLowerCase()})"


def render(lines: list[dict]) -> str:
    """The tagged format of `read_page` and `find`: `button "Search" [ref_4]`, indented by depth."""
    out: list[str] = []
    size = 0
    for index, line in enumerate(lines):
        text = "  " * (max(int(line.get("depth", 1)), 1) - 1) + str(line.get("role") or "generic")
        if line.get("name"):
            text += ' "' + str(line["name"]).replace('"', "'") + '"'
        if line.get("value"):
            text += f" value={line['value']!r}"
        if line.get("href"):
            text += f" href={line['href']}"
        text += f" [{line['ref']}]"
        if size + len(text) + 1 > READ_LIMIT:
            left = len(lines) - index
            out.append(
                f"(Cut at 50,000 characters: {left} more elements. Read again with a smaller depth, "
                "or with the ref of the part you need.)"
            )
            break
        out.append(text)
        size += len(text) + 1
    return "\n".join(out)


def _words(text: str) -> list[str]:
    return [word for word in "".join(c.lower() if c.isalnum() else " " for c in text).split() if len(word) > 1]


def match(lines: list[dict], query: str) -> list[dict]:
    """Up to 20 elements whose role, name, value or address shares the most words with the query."""
    wanted = _words(query)
    scored: list[tuple[int, int, dict]] = []
    for index, line in enumerate(lines):
        role = _words(str(line.get("role", "")))
        name = _words(str(line.get("name", "")) + " " + str(line.get("value", "")) + " " + str(line.get("href", "")))
        score = 0
        for word in wanted:
            if word in name:
                score += 3
            elif any(word in part or part in word for part in name if len(part) > 2):
                score += 2
            if word in role or any(word in part for part in role):
                score += 1
        if score:
            scored.append((-score, index, line))
    scored.sort(key=lambda item: (item[0], item[1]))
    return [dict(line, depth=1) for _, _, line in scored[:FIND_LIMIT]]


_KEYS = {
    "ctrl": "Control", "control": "Control", "cmd": "Meta", "command": "Meta", "meta": "Meta",
    "super": "Meta", "win": "Meta", "windows": "Meta", "alt": "Alt", "option": "Alt", "opt": "Alt",
    "shift": "Shift", "enter": "Enter", "return": "Enter", "esc": "Escape", "escape": "Escape",
    "space": "Space", "spacebar": "Space", "tab": "Tab", "backspace": "Backspace", "delete": "Delete",
    "del": "Delete", "insert": "Insert", "home": "Home", "end": "End", "pageup": "PageUp",
    "page_up": "PageUp", "pagedown": "PageDown", "page_down": "PageDown", "up": "ArrowUp",
    "down": "ArrowDown", "left": "ArrowLeft", "right": "ArrowRight", "arrowup": "ArrowUp",
    "arrowdown": "ArrowDown", "arrowleft": "ArrowLeft", "arrowright": "ArrowRight",
    "capslock": "CapsLock", "plus": "+", "minus": "-",
}  # fmt: skip
MODIFIERS = ("Control", "Meta", "Alt", "Shift")


def key_name(token: str) -> str:
    low = token.strip().lower()
    if not low:
        raise ToolError("An empty key name. Send a key such as Enter, or a chord such as ctrl+a.")
    if low in _KEYS:
        return _KEYS[low]
    if len(low) > 1 and low[0] == "f" and low[1:].isdigit():
        return low.upper()
    return token.strip()


def chord(text: str) -> str:
    """`ctrl+shift+a` as Playwright presses it: `Control+Shift+a`."""
    text = text.strip()
    if text == "+":
        return "+"
    parts = [part for part in text.split("+") if part != ""]
    if text.endswith("++"):
        parts.append("+")
    return "+".join(key_name(part) for part in parts)


def chords(text: str) -> list[str]:
    """A space-separated sequence of keys or chords, in order."""
    found = [chord(part) for part in text.split()]
    if not found:
        raise ToolError("An empty key. Send a key such as Enter, or a chord such as ctrl+a.")
    return found


def modifiers(text: str | None) -> list[str]:
    if not text:
        return []
    names = [key_name(part) for part in text.split("+") if part.strip()]
    for name in names:
        if name not in MODIFIERS:
            raise ToolError(f"{name} is not a modifier key. Use ctrl, shift, alt or cmd, joined with +.")
    return names
