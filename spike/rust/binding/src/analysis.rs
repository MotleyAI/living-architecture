//! The port of dr's per-file analysis: `static_resolver.Binder`/`Module`/`Scope` and `bindings._Parsed`.

use std::collections::BTreeSet;

use ruff_python_ast::name::Name;
use ruff_python_ast::{
    Expr, ExprContext, ModModule, Pattern, PythonVersion, Stmt, StmtClassDef, StmtFunctionDef, TypeParam, TypeParams,
};
use ruff_python_parser::{Mode, ParseOptions, parse_unchecked};
use ruff_text_size::Ranged;
use rustc_hash::FxHashMap;

use crate::text::{Src, py_space};
use crate::walk::{N, children};

pub type Span = (u32, u32);

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Kind {
    Module,
    Class,
    Function,
    Comprehension,
    Annotation,
}

impl Kind {
    pub fn name(self) -> &'static str {
        match self {
            Kind::Module => "module",
            Kind::Class => "class",
            Kind::Function => "function",
            Kind::Comprehension => "comprehension",
            Kind::Annotation => "annotation",
        }
    }
}

/// `static_resolver.Binding`; a declaration keeps CPython's `lineno:col_offset`.
#[derive(Clone, Debug)]
pub enum Binding {
    Other,
    Module(Name),
    Member(Option<Name>, Name),
    Decl(Box<str>),
}

#[derive(Debug)]
pub struct Scope {
    pub kind: Kind,
    pub parent: Option<u32>,
    pub raw: FxHashMap<Name, Vec<Binding>>,
    pub bindings: FxHashMap<Name, Vec<Binding>>,
    pub globals: Vec<Name>,
    pub nonlocals: Vec<Name>,
}

impl Scope {
    fn new(kind: Kind, parent: Option<u32>) -> Self {
        Self { kind, parent, raw: FxHashMap::default(), bindings: FxHashMap::default(), globals: vec![], nonlocals: vec![] }
    }
}

/// `Scope.owner`, `Scope.resolving` and `Scope._enclosing` over a module's scopes.
pub struct Scopes(pub Vec<Scope>);

impl Scopes {
    fn enclosing(&self, s: u32) -> impl Iterator<Item = u32> + '_ {
        let mut scope = self.0[s as usize].parent;
        let mut sees_class = self.0[s as usize].kind == Kind::Annotation;
        std::iter::from_fn(move || {
            while let Some(at) = scope {
                let kind = self.0[at as usize].kind;
                if kind == Kind::Module {
                    return None;
                }
                let yield_it = kind != Kind::Class || sees_class;
                sees_class = sees_class && kind == Kind::Annotation;
                scope = self.0[at as usize].parent;
                if yield_it {
                    return Some(at);
                }
            }
            None
        })
    }

    pub fn owner(&self, s: u32, name: &str) -> u32 {
        let scope = &self.0[s as usize];
        if scope.globals.iter().any(|g| g == name) {
            return 0;
        }
        if scope.nonlocals.iter().any(|g| g == name) {
            for e in self.enclosing(s) {
                let found = &self.0[e as usize];
                if found.raw.contains_key(name) || found.nonlocals.iter().any(|g| g == name) {
                    return self.owner(e, name);
                }
            }
            return 0;
        }
        s
    }

    pub fn resolving(&self, s: u32, name: &str) -> u32 {
        let scope = &self.0[s as usize];
        if scope.globals.iter().any(|g| g == name) || scope.nonlocals.iter().any(|g| g == name) {
            return self.owner(s, name);
        }
        if scope.kind == Kind::Module || scope.bindings.contains_key(name) {
            return s;
        }
        for e in self.enclosing(s) {
            let found = &self.0[e as usize];
            if found.globals.iter().any(|g| g == name) || found.nonlocals.iter().any(|g| g == name) {
                return self.owner(e, name);
            }
            if found.bindings.contains_key(name) {
                return e;
            }
        }
        0
    }
}

/// An identifier of a checked name: its offset, the scope it is resolved in and whether it binds.
#[derive(Clone, Copy, Debug)]
pub struct Occurrence {
    pub offset: u32,
    pub scope: u32,
    pub binds: bool,
}

/// A binding that runs: its name's offset, the offset it runs at and the span its statement evaluates first.
pub type Point = (Option<u32>, u32, Option<Span>);

/// `_Parsed`: a module's scopes, binding sites and points, star imports and identifiers; it keeps no syntax tree.
pub struct Parsed {
    pub scopes: Scopes,
    pub all_names: Option<BTreeSet<String>>,
    pub sites: FxHashMap<(u32, Name), Vec<u32>>,
    pub points: FxHashMap<(u32, Name), Vec<Point>>,
    pub named: FxHashMap<Name, Vec<Occurrence>>,
    pub stars: Vec<(Option<String>, u32)>,
    pub loops: FxHashMap<u32, Vec<[Span; 2]>>,
    pub dotted: String,
}

fn inside(spans: &[Span], at: u32) -> bool {
    spans.iter().any(|(s, e)| *s <= at && at < *e)
}

impl Parsed {
    /// A binding of `name` in class `scope` may run before the read at `at`.
    pub fn may_precede(&self, scope: u32, name: &Name, at: u32) -> bool {
        let key = (scope, name.clone());
        let points = self.points.get(&key).map_or(&[][..], Vec::as_slice);
        let looped = self.loops.get(&scope).is_some_and(|loops| {
            loops.iter().any(|spans| {
                inside(spans, at) && points.iter().any(|(b, _, _)| b.is_some_and(|b| inside(spans, b)))
            })
        });
        looped || points.iter().any(|(_, point, first)| *point <= at && !first.is_some_and(|f| inside(&[f], at)))
    }

    /// The scopes a declaration in `scope` shares its scope with.
    pub fn joined(&self, scope: u32) -> Vec<u32> {
        let s = &self.scopes.0[scope as usize];
        if s.kind == Kind::Annotation {
            return (0..self.scopes.0.len() as u32)
                .filter(|&i| {
                    let c = &self.scopes.0[i as usize];
                    c.parent == Some(scope) && matches!(c.kind, Kind::Function | Kind::Class)
                })
                .collect();
        }
        match s.parent {
            Some(p) if self.scopes.0[p as usize].kind == Kind::Annotation && matches!(s.kind, Kind::Function | Kind::Class) => {
                vec![p]
            }
            _ => vec![],
        }
    }
}

/// Why a file has no analysis.
pub enum Failure {
    Syntax,
}

pub fn version(text: &str) -> Option<PythonVersion> {
    Some(match text {
        "3.11" => PythonVersion::PY311,
        "3.12" => PythonVersion::PY312,
        "3.13" => PythonVersion::PY313,
        "3.14" => PythonVersion::PY314,
        _ => return None,
    })
}

/// `text` parsed as `ast.parse` would for `version`: None when CPython would reject it.
pub fn parse(text: &str, version: PythonVersion) -> Option<ModModule> {
    let parsed = parse_unchecked(text, ParseOptions::from(Mode::Module).with_target_version(version));
    if !parsed.has_no_syntax_errors() {
        return None;
    }
    parsed.try_into_module().map(ruff_python_parser::Parsed::into_syntax)
}

/// `rel`'s module path and whether it is a package (`_module_parts([""], rel)`).
pub fn module_parts(rel: &str) -> (Vec<String>, bool) {
    let stem = rel.rsplit_once('.').map_or(rel, |(s, _)| s);
    let mut parts: Vec<String> = stem.split('/').map(str::to_owned).collect();
    if parts.last().map(String::as_str) == Some("__init__") {
        parts.pop();
        (parts, true)
    } else {
        (parts, false)
    }
}

/// The decoded text analysed as dr's `_Parsed`.
pub fn analyse(text: &str, rel: &str, version: PythonVersion) -> Result<Parsed, Failure> {
    let src = Src::new(text);
    let tree = parse(text, version).ok_or(Failure::Syntax)?;
    Ok(analyse_tree(&src, &tree, rel, version))
}

/// A parsed module analysed as dr's `_Parsed`.
pub fn analyse_tree(src: &Src, tree: &ModModule, rel: &str, version: PythonVersion) -> Parsed {
    let (parts, is_package) = module_parts(rel);
    Binder::run(src, tree, parts, is_package, version)
}

fn at(r: impl Ranged) -> Span {
    (r.start().into(), r.end().into())
}

/// Where the context binding a name sets its run point.
#[derive(Clone, Copy)]
enum Ctx {
    EvalFirst(Span),
    Case(u32),
    Stmt(u32),
}

#[derive(Clone, Copy, PartialEq, Eq, Default)]
enum Parent {
    #[default]
    None,
    Aug,
    AnnNoValue,
}

/// What node binds a name, for its offset and run point.
#[derive(Clone, Copy)]
enum Bound<'a> {
    Name(Span),
    Def(&'a Stmt),
    Param(&'a ruff_python_ast::Parameter),
    Alias(&'a ruff_python_ast::Alias),
    Handler(&'a ruff_python_ast::ExceptHandlerExceptHandler),
    Pattern(&'a Pattern),
    TypeParam(&'a TypeParam),
}

struct BoundEntry {
    scope: u32,
    name: Name,
    offset: Option<u32>,
    point: Option<(u32, Option<Span>)>,
    aug: bool,
}

struct Binder<'s, 'a> {
    src: &'s Src<'s>,
    parts: Vec<String>,
    is_package: bool,
    version: PythonVersion,
    scopes: Vec<Scope>,
    stars: Vec<(Option<String>, u32)>,
    bound: Vec<BoundEntry>,
    loads: Vec<(Name, u32, u32)>,
    annotations: Vec<(&'a Expr, u32)>,
    ctx: Vec<Ctx>,
    parent: Parent,
    loops: FxHashMap<u32, Vec<[Span; 2]>>,
}

impl<'s, 'a> Binder<'s, 'a> {
    fn run(src: &'s Src<'s>, tree: &'a ModModule, parts: Vec<String>, is_package: bool, version: PythonVersion) -> Parsed {
        let mut b = Binder {
            src,
            parts,
            is_package,
            version,
            scopes: vec![Scope::new(Kind::Module, None)],
            stars: vec![],
            bound: vec![],
            loads: vec![],
            annotations: vec![],
            ctx: vec![],
            parent: Parent::None,
            loops: FxHashMap::default(),
        };
        for s in &tree.body {
            b.visit(N::Stmt(s), 0);
        }
        b.finish(tree)
    }

    fn ch(&self, at: u32) -> u32 {
        self.src.ch(at)
    }

    fn chs(&self, (s, e): Span) -> Span {
        (self.src.ch(s), self.src.ch(e))
    }

    fn new_scope(&mut self, kind: Kind, parent: u32) -> u32 {
        self.scopes.push(Scope::new(kind, Some(parent)));
        (self.scopes.len() - 1) as u32
    }

    /// A statement's CPython start: a decorated definition starts at its `def`, `async` or `class` keyword.
    fn stmt_start(&self, s: &Stmt) -> u32 {
        let decorators = match s {
            Stmt::FunctionDef(d) => &d.decorator_list,
            Stmt::ClassDef(c) => &c.decorator_list,
            _ => return s.start().into(),
        };
        let Some(last) = decorators.last() else { return s.start().into() };
        let bytes = self.src.text.as_bytes();
        let mut i = u32::from(last.end()) as usize;
        while let Some(&c) = bytes.get(i) {
            match c {
                b' ' | b'\t' | 0x0c | b'\r' | b'\n' | b'\\' => i += 1,
                b'#' => i += memchr::memchr2(b'\r', b'\n', &bytes[i..]).unwrap_or(bytes.len() - i),
                _ => break,
            }
        }
        i as u32
    }

    fn stmt_span(&self, s: &Stmt) -> Span {
        (self.stmt_start(s), s.end().into())
    }

    fn decl(&self, start: u32) -> Binding {
        Binding::Decl(self.src.key(start).into_boxed_str())
    }

    fn bind(&mut self, scope: u32, name: &Name, binding: Binding, node: Bound<'a>) {
        self.scopes[scope as usize].raw.entry(name.clone()).or_default().push(binding);
        let offset = self.bound_at(node, name);
        let point = (self.parent != Parent::AnnNoValue).then(|| self.point(node));
        self.bound.push(BoundEntry { scope, name: name.clone(), offset, point, aug: self.parent == Parent::Aug });
    }

    /// `bound_at`: the byte offset of the identifier with which `node` binds `name`.
    fn bound_at(&self, node: Bound<'a>, name: &str) -> Option<u32> {
        let src = self.src;
        let first_word = |(s, e): Span| src.word(s, e, name, false);
        match node {
            Bound::Name((s, _)) => Some(s),
            Bound::Def(stmt) => {
                let span = self.stmt_span(stmt);
                self.def_keyword_end(span.0).and_then(|e| src.name_from(e, name)).or_else(|| first_word(span))
            }
            Bound::Param(p) => {
                let start = u32::from(p.name.start());
                src.name_from(start, name).or_else(|| first_word((start, p.end().into())))
            }
            Bound::Alias(a) => src.word(a.start().into(), a.end().into(), name, a.asname.is_some()),
            Bound::Handler(h) => {
                let after = h.type_.as_ref().and_then(|t| self.as_keyword_end(t.end().into()));
                after.and_then(|e| src.name_from(e, name)).or_else(|| first_word(at(h)))
            }
            Bound::Pattern(p) => src.word(p.start().into(), p.end().into(), name, true),
            Bound::TypeParam(t) => first_word(at(t)),
        }
    }

    /// `(?:async\s+)?(?:def|class)\s+` matched at `start`: its end.
    fn def_keyword_end(&self, start: u32) -> Option<u32> {
        let text = &self.src.text[start as usize..];
        let spaces = |t: &str| t.chars().take_while(|c| py_space(*c)).map(char::len_utf8).sum::<usize>();
        let keyword = |t: &str| -> Option<usize> {
            let word = ["def", "class"].into_iter().find(|k| t.starts_with(k))?;
            let n = spaces(&t[word.len()..]);
            (n > 0).then_some(word.len() + n)
        };
        let with_async = text.strip_prefix("async").and_then(|rest| {
            let n = spaces(rest);
            (n > 0).then(|| keyword(&rest[n..]).map(|k| 5 + n + k)).flatten()
        });
        with_async.or_else(|| keyword(text)).map(|n| start + n as u32)
    }

    /// `(?:\s|\)|#[^\r\n]*+|\\\r?\n)*+as\s+` matched at `start`: its end.
    fn as_keyword_end(&self, start: u32) -> Option<u32> {
        let text = self.src.text;
        let bytes = text.as_bytes();
        let mut i = start as usize;
        loop {
            let Some(c) = text[i..].chars().next() else { break };
            if py_space(c) || c == ')' {
                i += c.len_utf8();
            } else if c == '#' {
                i += memchr::memchr2(b'\r', b'\n', &bytes[i..]).unwrap_or(bytes.len() - i);
            } else if c == '\\' && bytes.get(i + 1) == Some(&b'\n') {
                i += 2;
            } else if c == '\\' && bytes.get(i + 1) == Some(&b'\r') && bytes.get(i + 2) == Some(&b'\n') {
                i += 3;
            } else {
                break;
            }
        }
        let rest = text[i..].strip_prefix("as")?;
        let n: usize = rest.chars().take_while(|c| py_space(*c)).map(char::len_utf8).sum();
        (n > 0).then_some((i + 2 + n) as u32)
    }

    /// `_binding_point`, in characters.
    fn point(&self, node: Bound<'a>) -> (u32, Option<Span>) {
        match node {
            Bound::Def(s) => return (self.ch(s.end().into()), None),
            Bound::Handler(h) => return (self.ch(h.body.first().map_or(0, |s| self.stmt_start(s))), None),
            _ => {}
        }
        let own = match node {
            Bound::Name((_, e)) => Some(self.ch(e)),
            _ => None,
        };
        match self.ctx.last() {
            Some(Ctx::EvalFirst(first)) => (own.unwrap_or(first.1), Some(*first)),
            Some(Ctx::Case(end)) => (*end, None),
            Some(Ctx::Stmt(end)) => (own.unwrap_or(*end), None),
            None => (0, None),
        }
    }

    fn eval_first(&self, e: &Expr) -> Ctx {
        Ctx::EvalFirst(self.chs(at(e)))
    }

    fn visit(&mut self, node: N<'a>, scope: u32) {
        let parent = std::mem::take(&mut self.parent);
        match node {
            N::Stmt(s @ Stmt::FunctionDef(f)) => self.function(s, f, scope),
            N::Stmt(s @ Stmt::ClassDef(c)) => self.class(s, c, scope),
            N::Stmt(s @ (Stmt::Import(_) | Stmt::ImportFrom(_))) => self.imports(s, scope),
            N::Stmt(s @ Stmt::TypeAlias(t)) => {
                self.ctx.push(Ctx::Stmt(self.ch(s.end().into())));
                self.visit(N::Expr(&t.name), scope);
                let inner = self.type_params(t.type_params.as_deref(), scope);
                self.annotations.push((&t.value, inner));
                self.ctx.pop();
            }
            N::Stmt(Stmt::AnnAssign(a)) => {
                self.annotations.push((&a.annotation, scope));
                let ctx = match &a.value {
                    Some(v) => self.eval_first(v),
                    None => Ctx::Stmt(self.ch(a.end().into())),
                };
                self.ctx.push(ctx);
                self.parent = if a.value.is_none() { Parent::AnnNoValue } else { Parent::None };
                self.visit(N::Expr(&a.target), scope);
                if let Some(v) = &a.value {
                    self.visit(N::Expr(v), scope);
                }
                self.ctx.pop();
            }
            N::Stmt(Stmt::AugAssign(a)) => {
                self.ctx.push(self.eval_first(&a.value));
                self.parent = Parent::Aug;
                self.visit(N::Expr(&a.target), scope);
                self.visit(N::Expr(&a.value), scope);
                self.ctx.pop();
            }
            N::Expr(Expr::Lambda(l)) => {
                let inner = self.new_scope(Kind::Function, scope);
                if let Some(p) = &l.parameters {
                    self.signature(p, scope, scope, inner);
                }
                self.visit(N::Expr(&l.body), inner);
            }
            N::Expr(Expr::ListComp(c)) => self.comprehension(&c.generators, [None, Some(&*c.elt)], scope),
            N::Expr(Expr::SetComp(c)) => self.comprehension(&c.generators, [None, Some(&*c.elt)], scope),
            N::Expr(Expr::Generator(c)) => self.comprehension(&c.generators, [None, Some(&*c.elt)], scope),
            N::Expr(Expr::DictComp(c)) => self.comprehension(&c.generators, [c.key.as_deref(), Some(&*c.value)], scope),
            N::Expr(Expr::Name(n)) => {
                let span = at(n);
                if n.ctx == ExprContext::Load {
                    self.loads.push((n.id.clone(), self.ch(span.0), scope));
                } else {
                    self.parent = parent;
                    self.bind(scope, &n.id, self.decl(span.0), Bound::Name(span));
                    self.parent = Parent::None;
                }
            }
            N::Expr(Expr::Named(n)) => {
                let mut target = scope;
                while self.scopes[target as usize].kind == Kind::Comprehension {
                    match self.scopes[target as usize].parent {
                        Some(p) => target = p,
                        None => break,
                    }
                }
                self.ctx.push(self.eval_first(&n.value));
                if let Expr::Name(t) = &*n.target {
                    self.bind(target, &t.id, Binding::Other, Bound::Name(at(t)));
                }
                self.visit(N::Expr(&n.value), scope);
                self.ctx.pop();
            }
            _ => {
                self.record(node, scope);
                let ctx = match node {
                    N::Stmt(Stmt::Assign(a)) => Some(self.eval_first(&a.value)),
                    N::Stmt(Stmt::For(f)) => Some(self.eval_first(&f.iter)),
                    N::Stmt(s) => Some(Ctx::Stmt(self.ch(s.end().into()))),
                    N::WithItem(w) => Some(self.eval_first(&w.context_expr)),
                    N::Case(c) => Some(Ctx::Case(self.ch(c.pattern.end().into()))),
                    _ => None,
                };
                if let Some(c) = ctx {
                    self.ctx.push(c);
                }
                children(node, &mut |c| self.visit(c, scope));
                if ctx.is_some() {
                    self.ctx.pop();
                }
            }
        }
    }

    /// `Binder._record`: global and nonlocal declarations, and the names handlers and patterns bind.
    fn record(&mut self, node: N<'a>, scope: u32) {
        match node {
            N::Stmt(Stmt::Global(g)) => {
                let s = &mut self.scopes[scope as usize].globals;
                g.names.iter().for_each(|n| s.push(n.id.clone()));
            }
            N::Stmt(Stmt::Nonlocal(g)) => {
                let s = &mut self.scopes[scope as usize].nonlocals;
                g.names.iter().for_each(|n| s.push(n.id.clone()));
            }
            N::Handler(h) => {
                if let Some(name) = &h.name {
                    self.bind(scope, &name.id, Binding::Other, Bound::Handler(h));
                }
            }
            N::Pattern(p @ Pattern::MatchAs(a)) => {
                if let Some(name) = &a.name {
                    self.bind(scope, &name.id, Binding::Other, Bound::Pattern(p));
                }
            }
            N::Pattern(p @ Pattern::MatchStar(a)) => {
                if let Some(name) = &a.name {
                    self.bind(scope, &name.id, Binding::Other, Bound::Pattern(p));
                }
            }
            N::Pattern(p @ Pattern::MatchMapping(m)) => {
                if let Some(name) = &m.rest {
                    self.bind(scope, &name.id, Binding::Other, Bound::Pattern(p));
                }
            }
            _ => {}
        }
    }

    /// The PEP 695 annotation scope binding `params`, their bounds and defaults read in it; else `scope`.
    fn type_params(&mut self, params: Option<&'a TypeParams>, scope: u32) -> u32 {
        let Some(params) = params.filter(|p| !p.type_params.is_empty()) else { return scope };
        let inner = self.new_scope(Kind::Annotation, scope);
        for param in &params.type_params {
            let (name, exprs): (_, [Option<&'a Expr>; 2]) = match param {
                TypeParam::TypeVar(t) => (&t.name, [t.bound.as_deref(), t.default.as_deref()]),
                TypeParam::TypeVarTuple(t) => (&t.name, [None, t.default.as_deref()]),
                TypeParam::ParamSpec(t) => (&t.name, [None, t.default.as_deref()]),
            };
            self.bind(inner, &name.id, Binding::Other, Bound::TypeParam(param));
            for expr in exprs.into_iter().flatten() {
                match expr {
                    Expr::Tuple(t) => self.annotations.extend(t.elts.iter().map(|e| (e, inner))),
                    e => self.annotations.push((e, inner)),
                }
            }
        }
        inner
    }

    /// `Binder._signature` then the parameters bound in `inner`.
    fn signature(&mut self, p: &'a ruff_python_ast::Parameters, scope: u32, annotated: u32, inner: u32) {
        let positional = p.posonlyargs.iter().chain(&p.args);
        for default in positional.clone().chain(&p.kwonlyargs).filter_map(|a| a.default.as_deref()) {
            self.visit(N::Expr(default), scope);
        }
        let params: Vec<&'a ruff_python_ast::Parameter> = positional
            .map(|a| &a.parameter)
            .chain(p.vararg.as_deref())
            .chain(p.kwonlyargs.iter().map(|a| &a.parameter))
            .chain(p.kwarg.as_deref())
            .collect();
        for param in &params {
            if let Some(a) = &param.annotation {
                self.annotations.push((a, annotated));
            }
        }
        for param in params {
            self.bind(inner, &param.name.id, Binding::Other, Bound::Param(param));
        }
    }

    fn function(&mut self, s: &'a Stmt, f: &'a StmtFunctionDef, scope: u32) {
        self.ctx.push(Ctx::Stmt(self.ch(s.end().into())));
        for d in &f.decorator_list {
            self.visit(N::Expr(&d.expression), scope);
        }
        let annotated = self.type_params(f.type_params.as_deref(), scope);
        if let Some(r) = &f.returns {
            self.annotations.push((r, annotated));
        }
        self.bind(scope, &f.name.id, self.decl(self.stmt_start(s)), Bound::Def(s));
        let inner = self.new_scope(Kind::Function, annotated);
        self.signature(&f.parameters, scope, annotated, inner);
        for child in &f.body {
            self.visit(N::Stmt(child), inner);
        }
        self.ctx.pop();
    }

    fn class(&mut self, s: &'a Stmt, c: &'a StmtClassDef, scope: u32) {
        self.ctx.push(Ctx::Stmt(self.ch(s.end().into())));
        for d in &c.decorator_list {
            self.visit(N::Expr(&d.expression), scope);
        }
        let annotated = self.type_params(c.type_params.as_deref(), scope);
        if let Some(a) = &c.arguments {
            for e in &a.args {
                self.visit(N::Expr(e), annotated);
            }
            for k in &a.keywords {
                self.visit(N::Expr(&k.value), annotated);
            }
        }
        self.bind(scope, &c.name.id, self.decl(self.stmt_start(s)), Bound::Def(s));
        let inner = self.new_scope(Kind::Class, annotated);
        let mut loops = vec![];
        self.class_loops(&c.body, &mut loops);
        self.loops.insert(inner, loops);
        for child in &c.body {
            self.visit(N::Stmt(child), inner);
        }
        self.ctx.pop();
    }

    /// `_loops` with `_repeated`: each loop of a class body outside nested definitions, as its repeated spans.
    fn class_loops(&self, body: &'a [Stmt], out: &mut Vec<[Span; 2]>) {
        for s in body {
            let repeated = |head: &Expr, body: &[Stmt]| {
                let first = body.first().map_or(0, |b| self.stmt_start(b));
                let last = body.last().map_or(0, |b| u32::from(b.end()));
                [self.chs(at(head)), self.chs((first, last))]
            };
            match s {
                Stmt::FunctionDef(_) | Stmt::ClassDef(_) => continue,
                Stmt::For(f) => out.push(repeated(&f.target, &f.body)),
                Stmt::While(w) => out.push(repeated(&w.test, &w.body)),
                _ => {}
            }
            match s {
                Stmt::For(f) => {
                    self.class_loops(&f.body, out);
                    self.class_loops(&f.orelse, out);
                }
                Stmt::While(w) => {
                    self.class_loops(&w.body, out);
                    self.class_loops(&w.orelse, out);
                }
                Stmt::If(i) => {
                    self.class_loops(&i.body, out);
                    i.elif_else_clauses.iter().for_each(|c| self.class_loops(&c.body, out));
                }
                Stmt::With(w) => self.class_loops(&w.body, out),
                Stmt::Match(m) => m.cases.iter().for_each(|c| self.class_loops(&c.body, out)),
                Stmt::Try(t) => {
                    self.class_loops(&t.body, out);
                    for ruff_python_ast::ExceptHandler::ExceptHandler(h) in &t.handlers {
                        self.class_loops(&h.body, out);
                    }
                    self.class_loops(&t.orelse, out);
                    self.class_loops(&t.finalbody, out);
                }
                _ => {}
            }
        }
    }

    fn comprehension(&mut self, generators: &'a [ruff_python_ast::Comprehension], parts: [Option<&'a Expr>; 2], scope: u32) {
        self.visit(N::Expr(&generators[0].iter), scope);
        let inner = self.new_scope(Kind::Comprehension, scope);
        for (i, g) in generators.iter().enumerate() {
            if i > 0 {
                self.visit(N::Expr(&g.iter), inner);
            }
            self.visit(N::Expr(&g.target), inner);
            for cond in &g.ifs {
                self.visit(N::Expr(cond), inner);
            }
        }
        for part in parts.into_iter().flatten() {
            self.visit(N::Expr(part), inner);
        }
    }

    fn from_module(&self, level: u32, module: Option<&str>) -> Option<String> {
        if level == 0 {
            return module.map(str::to_owned);
        }
        let package = if self.is_package { &self.parts[..] } else { &self.parts[..self.parts.len().saturating_sub(1)] };
        let level = level as usize;
        if level - 1 >= package.len() {
            return None;
        }
        let mut parts: Vec<&str> = package[..package.len() - level + 1].iter().map(String::as_str).collect();
        parts.extend(module);
        Some(parts.join("."))
    }

    fn imports(&mut self, s: &'a Stmt, scope: u32) {
        self.ctx.push(Ctx::Stmt(self.ch(s.end().into())));
        match s {
            Stmt::Import(i) => {
                for alias in &i.names {
                    let full = alias.name.id.as_str();
                    let first = Name::from(full.split('.').next().unwrap_or(full));
                    let name = alias.asname.as_ref().map_or(first.clone(), |a| a.id.clone());
                    let module = if alias.asname.is_some() { alias.name.id.clone() } else { name.clone() };
                    self.bind(scope, &name, Binding::Module(module), Bound::Alias(alias));
                }
            }
            Stmt::ImportFrom(i) => {
                let module = self.from_module(i.level, i.module.as_ref().map(|m| m.id.as_str()));
                for alias in &i.names {
                    if alias.name.id.as_str() == "*" {
                        self.stars.push((module.clone(), self.ch(s.start().into())));
                    } else {
                        let name = alias.asname.as_ref().map_or(&alias.name.id, |a| &a.id).clone();
                        let member = Binding::Member(module.as_deref().map(Name::from), alias.name.id.clone());
                        self.bind(scope, &name, member, Bound::Alias(alias));
                    }
                }
            }
            _ => unreachable!(),
        }
        self.ctx.pop();
    }

    fn finish(self, tree: &'a ModModule) -> Parsed {
        let mut scopes = Scopes(self.scopes);
        let mut sites: FxHashMap<(u32, Name), Vec<u32>> = FxHashMap::default();
        let mut points: FxHashMap<(u32, Name), Vec<Point>> = FxHashMap::default();
        let mut named: FxHashMap<Name, Vec<Occurrence>> = FxHashMap::default();
        for b in self.bound {
            let owner = scopes.owner(b.scope, &b.name);
            let offset = b.offset.map(|o| self.src.ch(o));
            if let Some((run, first)) = b.point {
                points.entry((owner, b.name.clone())).or_default().push((offset, run, first));
            }
            if let Some(o) = offset {
                sites.entry((owner, b.name.clone())).or_default().push(o);
                let occs = named.entry(b.name).or_default();
                occs.push(Occurrence { offset: o, scope: b.scope, binds: true });
                if b.aug {
                    occs.push(Occurrence { offset: o, scope: b.scope, binds: false });
                }
            }
        }
        for (name, offset, scope) in self.loads {
            named.entry(name).or_default().push(Occurrence { offset, scope, binds: false });
        }
        for (expr, scope) in self.annotations {
            annotation_names(self.src, N::Expr(expr), 0, self.version, &mut |name, offset| {
                named.entry(name.clone()).or_default().push(Occurrence { offset, scope, binds: false });
            });
        }
        let mut by_scope: Vec<Vec<(Name, Vec<Binding>)>> = (0..scopes.0.len()).map(|_| vec![]).collect();
        for (i, scope) in scopes.0.iter().enumerate() {
            for (name, found) in &scope.raw {
                by_scope[i].push((name.clone(), found.clone()));
            }
        }
        for (i, entries) in by_scope.into_iter().enumerate() {
            for (name, found) in entries {
                let owner = scopes.owner(i as u32, &name);
                scopes.0[owner as usize].bindings.entry(name).or_default().extend(found);
            }
        }
        Parsed {
            scopes,
            all_names: literal_all(tree),
            sites,
            points,
            named,
            stars: self.stars,
            loops: self.loops,
            dotted: self.parts.join("."),
        }
    }
}

/// `literal_all`: the names of the module's last top-level `__all__` assignment when it is a literal of strings.
fn literal_all(tree: &ModModule) -> Option<BTreeSet<String>> {
    let mut names = None;
    for stmt in &tree.body {
        let (targets, value): (Vec<&Expr>, Option<&Expr>) = match stmt {
            Stmt::Assign(a) => (a.targets.iter().collect(), Some(&a.value)),
            Stmt::AnnAssign(a) => (vec![&a.target], a.value.as_deref()),
            _ => continue,
        };
        if !targets.iter().any(|t| matches!(t, Expr::Name(n) if n.id.as_str() == "__all__")) {
            continue;
        }
        let elts = match value {
            Some(Expr::List(l)) => Some(&l.elts),
            Some(Expr::Tuple(t)) => Some(&t.elts),
            _ => None,
        };
        names = elts.and_then(|elts| {
            elts.iter()
                .map(|e| match e {
                    Expr::StringLiteral(s) => Some(s.value.to_str().to_owned()),
                    _ => None,
                })
                .collect()
        });
    }
    names
}

fn is_literal(e: &Expr) -> bool {
    match e {
        Expr::Name(n) => n.id.as_str() == "Literal",
        Expr::Attribute(a) => a.attr.id.as_str() == "Literal",
        _ => false,
    }
}

/// `_annotation_names`: each name an annotation reads, with its character offset; string annotations included,
/// `Literal` values left out.
fn annotation_names(src: &Src, node: N, base: u32, version: PythonVersion, out: &mut dyn FnMut(&Name, u32)) {
    match node {
        N::Expr(Expr::Name(n)) => out(&n.id, base + src.ch(n.start().into())),
        N::Expr(Expr::StringLiteral(s)) => {
            if let Some((inner, offset)) = forward_reference(src, s) {
                if let Some(tree) = parse(&inner, version) {
                    let sub = Src::new(&inner);
                    for stmt in &tree.body {
                        annotation_names(&sub, N::Stmt(stmt), base + offset, version, out);
                    }
                }
            }
        }
        N::Expr(Expr::Subscript(s)) if is_literal(&s.value) => annotation_names(src, N::Expr(&s.value), base, version, out),
        _ => children(node, &mut |c| annotation_names(src, c, base, version, out)),
    }
}

/// `_forward_reference`: a string's stripped text and its character offset, when its text is exactly its value.
fn forward_reference(src: &Src, node: &ruff_python_ast::ExprStringLiteral) -> Option<(String, u32)> {
    let (start, end) = at(node);
    let text = &src.text[start as usize..end as usize];
    let body = text.strip_prefix(['r', 'R', 'u', 'U']).unwrap_or(text);
    let quote = ["'''", "\"\"\"", "'", "\""].into_iter().find(|q| body.starts_with(q))?;
    let open = text.len() - body.len() + quote.len();
    if !text.ends_with(quote) {
        return None;
    }
    let inner = &text[open..text.len().saturating_sub(quote.len()).max(open)];
    if inner != node.value.to_str() {
        return None;
    }
    let lead = inner.len() - inner.trim_start_matches(py_space).len();
    let stripped = inner.trim_matches(py_space).to_owned();
    let offset = src.ch(start + open as u32 + lead as u32) ;
    Some((stripped, offset))
}
