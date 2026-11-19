# Portable regex subset

`issue_key_pattern` and each pattern of `refactor.string_forms` must use only constructs that Python `re` and
JavaScript `RegExp` (no flags) read identically on ASCII input. The accept/reject vectors are in
`vectors/regex-subset.yaml`.

- `issue_key_pattern` is applied with full-match semantics. A tag id containing any non-ASCII character never
  matches, in every twin, whatever the pattern.
- A `refactor.string_forms` pattern is searched anywhere in a string literal's source text and must hold exactly
  one capturing group. A literal part containing any non-ASCII character never matches, in every twin, whatever
  the pattern.

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
