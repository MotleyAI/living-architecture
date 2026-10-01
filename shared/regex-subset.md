# Portable regex subset

`issue_key_pattern` must use only constructs that Python `re` and JavaScript `RegExp` (no flags) read
identically on ASCII input. Accepted patterns are applied with full-match semantics. The accept/reject
vectors are in `vectors/regex-subset.yaml`.

Allowed:

- literal characters, except the unescaped metacharacters `{` `}` `[` `]` `(` `)` outside their constructs
- `.`
- escapes: `\d \D \w \W \s \S`, the anchor `\b`, and a backslash before any ASCII punctuation character
- character classes `[...]` and `[^...]` holding literals, ranges `a-z`, the class escapes above and escaped
  punctuation; a `[` inside a class must be escaped
- quantifiers `*`, `+`, `?`, `{m}`, `{m,}`, `{m,n}`, each optionally followed by `?` (lazy)
- anchors `^` and `$`
- groups `( … )` and non-capturing groups `(?: … )`
- alternation `|`

Rejected: every other construct, including lookahead and lookbehind, named groups (`(?P<n>…)`, `(?<n>…)`),
backreferences, inline flags (`(?i)`, `(?i:…)`), possessive quantifiers (`*+`, `++`, `?+`, `{m,n}+`),
atomic groups (`(?>…)`), conditionals, comments (`(?#…)`), `\A`, `\Z`, `\z`, and any pattern that does not
compile.
