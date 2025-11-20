#! /usr/bin/env python3
#
# SPDX-License-Identifier: MIT

import sys
import argparse
import json
import textwrap
import html
import urllib.request

from pathlib import Path

from .version import VERSION


LBRACE = '<span class="token">{</span>'
RBRACE = '<span class="token">}</span>'
LBRACKET = '<span class="token">[</span>'
RBRACKET = '<span class="token">]</span>'
QUOTE = '<span class="token">"</span>'
COLON = '<span class="token">:</span>'
COMMA = '<span class="token">,</span>'

STYLE = textwrap.dedent(
    """
    a {
        text-decoration: none;
    }
    code {
    }
    /*
    pre.code {
        white-space: pre-wrap;
    }
    pre.code::before {
        counter-reset: listing;
    }
    pre.code code {
        counter-increment: listing;
        text-align: left;
        float: left;
        clear: left;
    }
    pre.code code::before {
        content: counter(listing) " ";
        display: inline-block;
        width: 4em;
        padding-left: auto;
        margin-left: auto;
        text-align: right;
    }
    */
    .token {
        color: #0000ff;
    }
    .string {
        color: #ff0000;
    }
    .ident {
        color: #0080ff;
    }
    .number {
        color: #000000;
    }
    .boolean {
        color: #000000;
    }
    .link {
        color: #0000ff;
    }
    .properties {
        color: #008000;
    }
    .classes {
        color: #800000;
    }
    .vocabularies {
        color: #800080;
    }
    :target {
        background-color: yellow;
    }
    """
)


def string(s, cls="string"):
    lst = [QUOTE, f'<span class="{cls}">']
    lst.append(html.escape(json.dumps(s).strip('"')))
    lst.append("</span>")
    lst.append(QUOTE)
    return "".join(lst)


def indent_str(i):
    return "  " * i


def get_obj_id(obj):
    return obj.get("@id", obj.get("spdxId"))


class OutputFile(object):
    def __init__(self, f, data):
        self.f = f
        self.data = data
        self.checked_urls = set()

        with urllib.request.urlopen(data["@context"]) as url:
            self.context = json.loads(url.read())

    def get_anchor(self, name, prefix, context):
        anchor = None

        if name in context:
            anchor = context[name]
            if isinstance(anchor, dict):
                if "@id" in anchor:
                    anchor = anchor["@id"]
                else:
                    anchor = None

        if not anchor:
            anchor = prefix + "-" + name

        if anchor in self.anchors:
            return None
        self.anchors.add(anchor)
        return anchor

    def index_data(self):
        self.anchors = set()
        self.ids = set()
        for obj in self.data.get("@graph", []):
            obj_id = get_obj_id(obj)
            if not obj_id:
                continue
            self.ids.add(obj_id)
            if obj["type"] == "SpdxDocument":
                for i in obj.get("import", []):
                    self.ids.add(i["externalSpdxId"])

    def get_doc_url(self, typ, name, context):
        sub_context = context
        if "@vocab" in context:
            rdf_uri = context["@vocab"]
            typ = "Vocabularies"
        else:
            if typ is None:
                return None, sub_context, None

            if name not in context:
                return None, sub_context, None

            rdf_uri = context[name]
            if isinstance(rdf_uri, dict):
                if "@context" in rdf_uri:
                    sub_context = rdf_uri["@context"]

                if "@id" in rdf_uri:
                    rdf_uri = rdf_uri["@id"]
                else:
                    return None, sub_context, None
        try:
            _, profile, n = rdf_uri.rstrip("/").rsplit("/", 2)
        except ValueError:
            return None, sub_context, None
        url = f"https://spdx.github.io/spdx-spec/v3.0.1/model/{profile}/{typ}/{n}"

        if url not in self.checked_urls:
            try:
                with urllib.request.urlopen(url):
                    pass
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise e
                raise Exception(f"Url '{url} is not valid")

        self.checked_urls.add(url)

        return url, sub_context, typ.lower()

    def write_value(self, v, indent, context, typ=None):
        if isinstance(v, str):
            doc_url, _, css_class = self.get_doc_url(typ, v, context)
            if v in self.ids:
                self.f.write('<a href="#' + html.escape(v) + '">')
                self.f.write(string(v, "ident"))
                self.f.write("</a>")
            elif doc_url:
                self.f.write('<a href="' + html.escape(doc_url) + '">')
                self.f.write(string(v, css_class))
                self.f.write("</a>")
            elif v.startswith("http://") or v.startswith("https://"):
                self.f.write('<a href="' + html.escape(v) + '">')
                self.f.write(string(v, "link"))
                self.f.write("</a>")
            else:
                self.f.write(string(v))
        elif isinstance(v, dict):
            self.write_obj(v, indent, context)
        elif isinstance(v, list):
            self.write_list(v, indent, context)
        elif isinstance(v, bool):
            self.f.write('<span class="boolean">' + json.dumps(v) + "</span>")
        else:
            self.f.write('<span class="number">' + json.dumps(v) + "</span>")

    def write_key_value(self, k, v, indent, context):
        anchor = self.get_anchor(k, "property", context)
        if anchor:
            self.f.write('<span id="' + html.escape(anchor) + '">')

        self.f.write(indent_str(indent))
        doc_url, sub_context, css_class = self.get_doc_url("Properties", k, context)
        if doc_url:
            self.f.write('<a href="' + html.escape(doc_url) + '">')
        self.f.write(string(k, css_class or "string"))
        if doc_url:
            self.f.write("</a>")
        self.f.write(COLON + " ")
        typ = None
        if k == "type":
            typ = "Classes"
        self.write_value(v, indent, sub_context, typ)

        if anchor:
            self.f.write("</span>")

    def newline(self):
        self.f.write("\n")
        # self.f.write("</code>\n<code>")

    def write_list(self, lst, indent, context):
        self.f.write(LBRACKET)
        self.newline()
        if lst:
            for i in lst[:-1]:
                self.f.write(indent_str(indent + 1))
                self.write_value(i, indent + 1, context)
                self.f.write(COMMA)
                self.newline()

            self.f.write(indent_str(indent + 1))
            self.write_value(lst[-1], indent + 1, context)
            self.newline()

        self.f.write(indent_str(indent) + RBRACKET)

    def write_obj(self, obj, indent, context):
        if "type" in obj:
            anchor = self.get_anchor(obj["type"], "class", context)
        else:
            anchor = None

        if anchor:
            self.f.write('<span id="' + html.escape(anchor) + '">')

        obj_id = get_obj_id(obj)
        if obj_id:
            self.f.write('<span id="' + html.escape(obj_id) + '">')

        external_obj_id = obj.get("externalSpdxId")
        if external_obj_id:
            self.f.write('<span id="' + html.escape(external_obj_id) + '">')

        self.f.write(LBRACE)
        self.newline()
        keys = list(obj.keys())

        if keys:
            for k in keys[:-1]:
                self.write_key_value(k, obj[k], indent + 1, context)
                self.f.write(COMMA)
                self.newline()

            self.write_key_value(keys[-1], obj[keys[-1]], indent + 1, context)
            self.newline()

        self.f.write(indent_str(indent) + RBRACE)
        if external_obj_id:
            self.f.write("</span>")

        if obj_id:
            self.f.write("</span>")

        if anchor:
            self.f.write("</span>")

    def write(self):
        self.index_data()
        self.f.write("<table>\n")
        self.f.write("<tr><th>Legend</th></tr>\n")
        self.f.write('<tr><td><span class="string">String</span></td></tr>\n')
        self.f.write(
            '<tr><td><span class="classes">SPDX Class (link)</span></td></tr>\n'
        )
        self.f.write(
            '<tr><td><span class="properties">SPDX Property (link)</span></td></tr>\n'
        )
        self.f.write(
            '<tr><td><span class="vocabularies">SPDX Vocabulary (link)</span></td></tr>\n'
        )
        self.f.write(
            '<tr><td><span class="ident">Identifier IRI (link)</span></td></tr>\n'
        )
        self.f.write("</table>\n")
        self.f.write('<pre class="code"><code>')
        self.write_obj(self.data, 0, self.context["@context"])
        self.f.write("</code></pre>")


def main():
    parser = argparse.ArgumentParser(description="Create HTML Example from JSON file")
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        help="Show version",
        version=VERSION,
    )
    parser.add_argument("infile", type=Path, help="Input JSON file")
    parser.add_argument("outfile", type=Path, help="Output HTML file")

    args = parser.parse_args()

    with args.infile.open("r") as f:
        data = json.load(f)

    with args.outfile.open("w") as f:
        o = OutputFile(f, data)
        f.write(
            textwrap.dedent(
                """\
                <!DOCTYPE html>
                <html>
                <head>
                <style>
                """
            )
        )
        f.write(STYLE)
        f.write(
            textwrap.dedent(
                """
                </style>
                </head>
                <body>"""
            )
        )
        o.write()

        f.write(
            textwrap.dedent(
                """\
                </body>
                </html>
                """
            )
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
