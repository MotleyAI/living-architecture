//! `fidelity-dump --python-version 3.X --root DIR [REL ...]`: ruff's spans of what dr reads, in the schema of
//! `spike/py/fidelity_dump.py`, each span as ruff gives it (only node kinds are mapped to CPython's class names).
//! `fidelity-dump --describe-options --python-version 3.X` prints the parse options used for 3.X.

use std::io::Write;

use binding::text::{Decoded, Src, decode};
use binding::walk::{N, children};
use binding::Cli;
use ruff_python_ast::token::TokenKind;
use ruff_python_ast::{
    Expr, FStringPartRef, InterpolatedStringElement, InterpolatedStringElements, ModModule, Pattern, PythonVersion,
    Stmt, TypeParam,
};
use ruff_python_parser::{Mode, ParseOptions, Parsed, parse_unchecked};
use ruff_text_size::{Ranged, TextRange};
use serde_json::{Value, json};

fn options(version: PythonVersion) -> ParseOptions {
    ParseOptions::from(Mode::Module).with_target_version(version)
}

struct Dump<'s> {
    src: &'s Src<'s>,
    nodes: Vec<(u32, u32, &'static str)>,
    strings: Vec<(u32, u32, &'static str, (u32, u32))>,
}

fn span(r: impl Ranged) -> (u32, u32) {
    (r.start().into(), r.end().into())
}

fn stmt_kind(s: &Stmt) -> &'static str {
    match s {
        Stmt::FunctionDef(f) if f.is_async => "AsyncFunctionDef",
        Stmt::FunctionDef(_) => "FunctionDef",
        Stmt::ClassDef(_) => "ClassDef",
        Stmt::Return(_) => "Return",
        Stmt::Delete(_) => "Delete",
        Stmt::TypeAlias(_) => "TypeAlias",
        Stmt::Assign(_) => "Assign",
        Stmt::AugAssign(_) => "AugAssign",
        Stmt::AnnAssign(_) => "AnnAssign",
        Stmt::For(f) if f.is_async => "AsyncFor",
        Stmt::For(_) => "For",
        Stmt::While(_) => "While",
        Stmt::If(_) => "If",
        Stmt::With(w) if w.is_async => "AsyncWith",
        Stmt::With(_) => "With",
        Stmt::Match(_) => "Match",
        Stmt::Raise(_) => "Raise",
        Stmt::Try(t) if t.is_star => "TryStar",
        Stmt::Try(_) => "Try",
        Stmt::Assert(_) => "Assert",
        Stmt::Import(_) => "Import",
        Stmt::ImportFrom(_) => "ImportFrom",
        Stmt::Global(_) => "Global",
        Stmt::Nonlocal(_) => "Nonlocal",
        Stmt::Expr(_) => "Expr",
        Stmt::Pass(_) => "Pass",
        Stmt::Break(_) => "Break",
        Stmt::Continue(_) => "Continue",
        Stmt::IpyEscapeCommand(_) => "IpyEscapeCommand",
    }
}

/// CPython's class name of a non-string expression; None for a string.
fn expr_kind(e: &Expr) -> Option<&'static str> {
    Some(match e {
        Expr::BoolOp(_) => "BoolOp",
        Expr::Named(_) => "NamedExpr",
        Expr::BinOp(_) => "BinOp",
        Expr::UnaryOp(_) => "UnaryOp",
        Expr::Lambda(_) => "Lambda",
        Expr::If(_) => "IfExp",
        Expr::Dict(_) => "Dict",
        Expr::Set(_) => "Set",
        Expr::ListComp(_) => "ListComp",
        Expr::SetComp(_) => "SetComp",
        Expr::DictComp(_) => "DictComp",
        Expr::Generator(_) => "GeneratorExp",
        Expr::Await(_) => "Await",
        Expr::Yield(_) => "Yield",
        Expr::YieldFrom(_) => "YieldFrom",
        Expr::Compare(_) => "Compare",
        Expr::Call(_) => "Call",
        Expr::NumberLiteral(_) | Expr::BooleanLiteral(_) | Expr::NoneLiteral(_) | Expr::EllipsisLiteral(_) => "Constant",
        Expr::Attribute(_) => "Attribute",
        Expr::Subscript(_) => "Subscript",
        Expr::Starred(_) => "Starred",
        Expr::Name(_) => "Name",
        Expr::List(_) => "List",
        Expr::Tuple(_) => "Tuple",
        Expr::Slice(_) => "Slice",
        Expr::IpyEscapeCommand(_) => "IpyEscapeCommand",
        Expr::StringLiteral(_) | Expr::BytesLiteral(_) | Expr::FString(_) | Expr::TString(_) => return None,
    })
}

fn pattern_kind(p: &Pattern) -> &'static str {
    match p {
        Pattern::MatchValue(_) => "MatchValue",
        Pattern::MatchSingleton(_) => "MatchSingleton",
        Pattern::MatchSequence(_) => "MatchSequence",
        Pattern::MatchMapping(_) => "MatchMapping",
        Pattern::MatchClass(_) => "MatchClass",
        Pattern::MatchStar(_) => "MatchStar",
        Pattern::MatchAs(_) => "MatchAs",
        Pattern::MatchOr(_) => "MatchOr",
    }
}

impl<'s> Dump<'s> {
    fn node(&mut self, kind: &'static str, r: impl Ranged) {
        let (s, e) = span(r);
        self.nodes.push((s, e, kind));
    }

    fn part(&mut self, kind: &'static str, r: impl Ranged, node: TextRange) {
        let (s, e) = span(r);
        self.strings.push((s, e, kind, span(node)));
    }

    fn elements(&mut self, elements: &InterpolatedStringElements, node: TextRange) {
        for element in elements {
            match element {
                InterpolatedStringElement::Literal(l) => self.part("fstr-literal", l, node),
                InterpolatedStringElement::Interpolation(i) => {
                    self.part("fstr-field", i, node);
                    if let Some(spec) = &i.format_spec {
                        self.part("fstr-spec", &**spec, node);
                        self.elements(&spec.elements, node);
                    }
                }
            }
        }
    }

    fn walk(&mut self, n: N) {
        match n {
            N::Stmt(s) => {
                self.node(stmt_kind(s), s);
                if let Stmt::If(i) = s {
                    i.elif_else_clauses.iter().filter(|c| c.test.is_some()).for_each(|c| self.node("If", c));
                }
            }
            N::Expr(e) => match expr_kind(e) {
                Some(kind) => self.node(kind, e),
                None => self.string(e),
            },
            N::Pattern(p) => self.node(pattern_kind(p), p),
            N::Handler(h) => self.node("ExceptHandler", h),
            N::Param(p) => self.node("arg", p),
            N::Keyword(k) => self.node("keyword", k),
            N::Alias(a) => self.node("alias", a),
            N::TypeParam(t) => self.node(
                match t {
                    TypeParam::TypeVar(_) => "TypeVar",
                    TypeParam::TypeVarTuple(_) => "TypeVarTuple",
                    TypeParam::ParamSpec(_) => "ParamSpec",
                },
                t,
            ),
            N::Params(_) | N::WithItem(_) | N::Case(_) | N::Comp(_) | N::Interp(_) => {}
        }
        children(n, &mut |c| self.walk(c));
    }

    fn string(&mut self, e: &Expr) {
        let node = e.range();
        match e {
            Expr::StringLiteral(s) => s.value.iter().for_each(|p| self.part("str", p, node)),
            Expr::BytesLiteral(b) => b.value.iter().for_each(|p| self.part("str", p, node)),
            Expr::FString(f) => {
                for part in f.value.iter() {
                    match part {
                        FStringPartRef::Literal(l) => self.part("str", l, node),
                        FStringPartRef::FString(fs) => {
                            self.part("fstr", fs, node);
                            self.elements(&fs.elements, node);
                        }
                    }
                }
            }
            Expr::TString(t) => {
                for ts in t.value.iter() {
                    self.part("tstr", ts, node);
                    self.elements(&ts.elements, node);
                }
            }
            _ => {}
        }
    }

    fn entry(&self, kind: &str, s: u32, e: u32) -> Value {
        json!({"kind": kind, "chars": [self.src.ch(s), self.src.ch(e)], "bytes": [s, e]})
    }
}

/// Top-level comment and string tokens, an f- or t-string run as one; the lexer's failure when it has one.
fn tokens(src: &Src, parsed: &Parsed<ModModule>) -> Value {
    let mut out = vec![];
    let mut depth = 0;
    let (mut start, mut kind) = (0, "");
    for token in parsed.tokens().iter() {
        let (s, e) = span(token);
        match token.kind() {
            TokenKind::Unknown => return json!("LexicalError"),
            TokenKind::FStringStart | TokenKind::TStringStart => {
                if depth == 0 {
                    start = s;
                    kind = if token.kind() == TokenKind::FStringStart { "fstring" } else { "tstring" };
                }
                depth += 1;
            }
            TokenKind::FStringEnd | TokenKind::TStringEnd => {
                depth -= 1;
                if depth == 0 {
                    out.push((start, e, kind));
                }
            }
            TokenKind::Comment if depth == 0 => out.push((s, e, "comment")),
            TokenKind::String if depth == 0 => out.push((s, e, "string")),
            _ => {}
        }
    }
    sorted(src, out)
}

fn sorted(src: &Src, mut entries: Vec<(u32, u32, &str)>) -> Value {
    entries.sort_by_key(|(s, e, k)| (src.ch(*s), src.ch(*e), *k));
    entries.into_iter().map(|(s, e, k)| json!({"kind": k, "chars": [src.ch(s), src.ch(e)], "bytes": [s, e]})).collect()
}

fn dump_text(text: &str, version: PythonVersion) -> Value {
    let src = Src::new(text);
    let parsed = parse_unchecked(text, options(version)).try_into_module().expect("module");
    let ok = parsed.has_no_syntax_errors();
    let mut out = json!({"status": if ok { "ok" } else { "syntax-error" }, "tokens": tokens(&src, &parsed)});
    if ok {
        let mut d = Dump { src: &src, nodes: vec![], strings: vec![] };
        for s in &parsed.syntax().body {
            d.walk(N::Stmt(s));
        }
        let nodes = sorted(&src, std::mem::take(&mut d.nodes).into_iter().map(|(s, e, k)| (s, e, k)).collect());
        let mut strings = std::mem::take(&mut d.strings);
        strings.sort_by_key(|(s, e, k, _)| (src.ch(*s), src.ch(*e), *k));
        let strings: Vec<Value> = strings
            .into_iter()
            .map(|(s, e, k, (ns, ne))| {
                let mut entry = d.entry(k, s, e);
                entry["node"] = json!([src.ch(ns), src.ch(ne)]);
                entry
            })
            .collect();
        out["nodes"] = nodes;
        out["strings"] = Value::Array(strings);
    }
    out
}

fn main() {
    let cli = Cli::parse(&["--describe-options"], &[], &["--describe-options"]).unwrap_or_else(|e| {
        eprintln!("{e}");
        std::process::exit(2)
    });
    if cli.switches.iter().any(|s| s == "--describe-options") {
        println!(
            "ruff_python_parser 0.0.22, Python {}: parse_unchecked(source, ParseOptions::from(Mode::Module)\
             .with_target_version(PythonVersion {{ major: {}, minor: {} }})) = {:?}; a ParseError or an \
             UnsupportedSyntaxError counts as rejection",
            cli.version_text,
            cli.version.major,
            cli.version.minor,
            options(cli.version)
        );
        return;
    }
    let mut out = std::io::BufWriter::new(std::io::stdout().lock());
    for rel in &cli.rels {
        let doc = match std::fs::read(cli.root.join(rel)).map(|d| decode(&d)) {
            Ok(Decoded::Text(text)) => dump_text(&text, cli.version),
            Ok(Decoded::Undecodable) => json!({"status": "undecodable"}),
            Ok(Decoded::Unsupported(name)) => json!({"status": format!("unsupported-encoding: {name}")}),
            Err(e) => json!({"status": format!("unreadable: {e}")}),
        };
        writeln!(out, "{rel}\t{doc}").expect("stdout");
    }
}
