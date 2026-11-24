from html.parser import HTMLParser

VOID = {"input", "br", "img", "hr", "meta", "link", "path", "circle", "line", "rect"}


class _Collect(HTMLParser):
    """Collects the full markup (nested elements included) of every element carrying `attr`."""

    def __init__(self, attr):
        super().__init__(convert_charrefs=False)
        self.attr, self.found, self.stack = attr, [], []  # stack: [tag, depth, parts] of open captures
        self.depth = 0

    def _text(self, tag, attrs, closing=""):
        body = "".join(f' {k}="{v}"' if v is not None else f" {k}" for k, v in attrs)
        return f"<{tag}{body}{closing}>"

    def handle_starttag(self, tag, attrs):
        text = self._text(tag, attrs)
        for cap in self.stack:
            cap[2].append(text)
        if tag in VOID:
            return
        self.depth += 1
        if any(k == self.attr for k, _ in attrs):
            self.stack.append([tag, self.depth, [text]])

    def handle_startendtag(self, tag, attrs):
        text = self._text(tag, attrs, " /")
        for cap in self.stack:
            cap[2].append(text)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        for cap in self.stack:
            cap[2].append(f"</{tag}>")
        if self.stack and self.stack[-1][1] == self.depth:
            self.found.append("".join(self.stack.pop()[2]))
        self.depth -= 1

    def handle_data(self, data):
        for cap in self.stack:
            cap[2].append(data)

    def handle_entityref(self, name):
        self.handle_data(f"&{name};")

    def handle_charref(self, name):
        self.handle_data(f"&#{name};")


def elements_with(html: str, attr: str) -> list[str]:
    """The full outer HTML of each element that has attribute `attr`."""
    parser = _Collect(attr)
    parser.feed(html)
    return parser.found
