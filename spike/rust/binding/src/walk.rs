//! ruff's syntax tree walked as `ast.iter_child_nodes` walks CPython's: the same children, in field order.

use ruff_python_ast::{
    Alias, Comprehension, ExceptHandler, ExceptHandlerExceptHandler, Expr, InterpolatedElement,
    InterpolatedStringElement, InterpolatedStringElements, Keyword, MatchCase, Parameter, Parameters, Pattern, Stmt,
    TypeParam, TypeParams, WithItem,
};

/// A node of ruff's tree standing for one of CPython's.
#[derive(Clone, Copy)]
pub enum N<'a> {
    Stmt(&'a Stmt),
    Expr(&'a Expr),
    Pattern(&'a Pattern),
    Handler(&'a ExceptHandlerExceptHandler),
    Params(&'a Parameters),
    Param(&'a Parameter),
    Keyword(&'a Keyword),
    Alias(&'a Alias),
    WithItem(&'a WithItem),
    Case(&'a MatchCase),
    Comp(&'a Comprehension),
    TypeParam(&'a TypeParam),
    Interp(&'a InterpolatedElement),
}

pub type Visit<'v, 'a> = &'v mut dyn FnMut(N<'a>);

fn stmts<'a>(body: &'a [Stmt], f: Visit<'_, 'a>) {
    body.iter().for_each(|s| f(N::Stmt(s)));
}

fn exprs<'a>(items: impl IntoIterator<Item = &'a Expr>, f: Visit<'_, 'a>) {
    items.into_iter().for_each(|e| f(N::Expr(e)));
}

fn type_params<'a>(params: Option<&'a TypeParams>, f: Visit<'_, 'a>) {
    params.into_iter().flat_map(|p| &p.type_params).for_each(|p| f(N::TypeParam(p)));
}

fn elements<'a>(elements: &'a InterpolatedStringElements, f: Visit<'_, 'a>) {
    for element in elements {
        if let InterpolatedStringElement::Interpolation(i) = element {
            f(N::Interp(i));
        }
    }
}

/// `node`'s children in CPython's field order; an `elif` chain is flattened into its `if`.
pub fn children<'a>(node: N<'a>, f: Visit<'_, 'a>) {
    match node {
        N::Stmt(s) => stmt(s, f),
        N::Expr(e) => expr(e, f),
        N::Pattern(p) => pattern(p, f),
        N::Handler(h) => {
            exprs(h.type_.as_deref(), f);
            stmts(&h.body, f);
        }
        N::Params(p) => {
            p.posonlyargs.iter().chain(&p.args).for_each(|a| f(N::Param(&a.parameter)));
            p.vararg.iter().for_each(|a| f(N::Param(a)));
            p.kwonlyargs.iter().for_each(|a| f(N::Param(&a.parameter)));
            exprs(p.kwonlyargs.iter().filter_map(|a| a.default.as_deref()), f);
            p.kwarg.iter().for_each(|a| f(N::Param(a)));
            exprs(p.posonlyargs.iter().chain(&p.args).filter_map(|a| a.default.as_deref()), f);
        }
        N::Param(p) => exprs(p.annotation.as_deref(), f),
        N::Keyword(k) => f(N::Expr(&k.value)),
        N::Alias(_) => {}
        N::WithItem(w) => {
            f(N::Expr(&w.context_expr));
            exprs(w.optional_vars.as_deref(), f);
        }
        N::Case(c) => {
            f(N::Pattern(&c.pattern));
            exprs(c.guard.as_deref(), f);
            stmts(&c.body, f);
        }
        N::Comp(c) => {
            f(N::Expr(&c.target));
            f(N::Expr(&c.iter));
            exprs(&c.ifs, f);
        }
        N::TypeParam(TypeParam::TypeVar(t)) => exprs(t.bound.as_deref().into_iter().chain(t.default.as_deref()), f),
        N::TypeParam(TypeParam::TypeVarTuple(t)) => exprs(t.default.as_deref(), f),
        N::TypeParam(TypeParam::ParamSpec(t)) => exprs(t.default.as_deref(), f),
        N::Interp(i) => {
            f(N::Expr(&i.expression));
            if let Some(spec) = &i.format_spec {
                elements(&spec.elements, f);
            }
        }
    }
}

fn stmt<'a>(s: &'a Stmt, f: Visit<'_, 'a>) {
    match s {
        Stmt::FunctionDef(d) => {
            f(N::Params(&d.parameters));
            stmts(&d.body, f);
            exprs(d.decorator_list.iter().map(|d| &d.expression), f);
            exprs(d.returns.as_deref(), f);
            type_params(d.type_params.as_deref(), f);
        }
        Stmt::ClassDef(c) => {
            if let Some(a) = &c.arguments {
                exprs(&a.args, f);
                a.keywords.iter().for_each(|k| f(N::Keyword(k)));
            }
            stmts(&c.body, f);
            exprs(c.decorator_list.iter().map(|d| &d.expression), f);
            type_params(c.type_params.as_deref(), f);
        }
        Stmt::Return(r) => exprs(r.value.as_deref(), f),
        Stmt::Delete(d) => exprs(&d.targets, f),
        Stmt::TypeAlias(t) => {
            f(N::Expr(&t.name));
            type_params(t.type_params.as_deref(), f);
            f(N::Expr(&t.value));
        }
        Stmt::Assign(a) => {
            exprs(&a.targets, f);
            f(N::Expr(&a.value));
        }
        Stmt::AugAssign(a) => {
            f(N::Expr(&a.target));
            f(N::Expr(&a.value));
        }
        Stmt::AnnAssign(a) => {
            f(N::Expr(&a.target));
            f(N::Expr(&a.annotation));
            exprs(a.value.as_deref(), f);
        }
        Stmt::For(l) => {
            f(N::Expr(&l.target));
            f(N::Expr(&l.iter));
            stmts(&l.body, f);
            stmts(&l.orelse, f);
        }
        Stmt::While(w) => {
            f(N::Expr(&w.test));
            stmts(&w.body, f);
            stmts(&w.orelse, f);
        }
        Stmt::If(i) => {
            f(N::Expr(&i.test));
            stmts(&i.body, f);
            for clause in &i.elif_else_clauses {
                exprs(clause.test.as_ref(), f);
                stmts(&clause.body, f);
            }
        }
        Stmt::With(w) => {
            w.items.iter().for_each(|i| f(N::WithItem(i)));
            stmts(&w.body, f);
        }
        Stmt::Match(m) => {
            f(N::Expr(&m.subject));
            m.cases.iter().for_each(|c| f(N::Case(c)));
        }
        Stmt::Raise(r) => exprs(r.exc.as_deref().into_iter().chain(r.cause.as_deref()), f),
        Stmt::Try(t) => {
            stmts(&t.body, f);
            t.handlers.iter().for_each(|ExceptHandler::ExceptHandler(h)| f(N::Handler(h)));
            stmts(&t.orelse, f);
            stmts(&t.finalbody, f);
        }
        Stmt::Assert(a) => exprs(std::iter::once(&*a.test).chain(a.msg.as_deref()), f),
        Stmt::Import(i) => i.names.iter().for_each(|a| f(N::Alias(a))),
        Stmt::ImportFrom(i) => i.names.iter().for_each(|a| f(N::Alias(a))),
        Stmt::Expr(e) => f(N::Expr(&e.value)),
        Stmt::Global(_)
        | Stmt::Nonlocal(_)
        | Stmt::Pass(_)
        | Stmt::Break(_)
        | Stmt::Continue(_)
        | Stmt::IpyEscapeCommand(_) => {}
    }
}

fn expr<'a>(e: &'a Expr, f: Visit<'_, 'a>) {
    match e {
        Expr::BoolOp(b) => exprs(&b.values, f),
        Expr::Named(n) => {
            f(N::Expr(&n.target));
            f(N::Expr(&n.value));
        }
        Expr::BinOp(b) => {
            f(N::Expr(&b.left));
            f(N::Expr(&b.right));
        }
        Expr::UnaryOp(u) => f(N::Expr(&u.operand)),
        Expr::Lambda(l) => {
            if let Some(p) = &l.parameters {
                f(N::Params(p));
            }
            f(N::Expr(&l.body));
        }
        Expr::If(i) => {
            f(N::Expr(&i.test));
            f(N::Expr(&i.body));
            f(N::Expr(&i.orelse));
        }
        Expr::Dict(d) => {
            exprs(d.items.iter().filter_map(|i| i.key.as_ref()), f);
            exprs(d.items.iter().map(|i| &i.value), f);
        }
        Expr::Set(s) => exprs(&s.elts, f),
        Expr::ListComp(c) => {
            f(N::Expr(&c.elt));
            c.generators.iter().for_each(|g| f(N::Comp(g)));
        }
        Expr::SetComp(c) => {
            f(N::Expr(&c.elt));
            c.generators.iter().for_each(|g| f(N::Comp(g)));
        }
        Expr::Generator(c) => {
            f(N::Expr(&c.elt));
            c.generators.iter().for_each(|g| f(N::Comp(g)));
        }
        Expr::DictComp(c) => {
            exprs(c.key.as_deref(), f);
            f(N::Expr(&c.value));
            c.generators.iter().for_each(|g| f(N::Comp(g)));
        }
        Expr::Await(a) => f(N::Expr(&a.value)),
        Expr::Yield(y) => exprs(y.value.as_deref(), f),
        Expr::YieldFrom(y) => f(N::Expr(&y.value)),
        Expr::Compare(c) => exprs(&c.operands, f),
        Expr::Call(c) => {
            f(N::Expr(&c.func));
            exprs(&c.arguments.args, f);
            c.arguments.keywords.iter().for_each(|k| f(N::Keyword(k)));
        }
        Expr::FString(s) => {
            for part in s.value.iter() {
                if let ruff_python_ast::FStringPartRef::FString(fs) = part {
                    elements(&fs.elements, f);
                }
            }
        }
        Expr::TString(s) => s.value.iter().for_each(|ts| elements(&ts.elements, f)),
        Expr::Attribute(a) => f(N::Expr(&a.value)),
        Expr::Subscript(s) => {
            f(N::Expr(&s.value));
            f(N::Expr(&s.slice));
        }
        Expr::Starred(s) => f(N::Expr(&s.value)),
        Expr::List(l) => exprs(&l.elts, f),
        Expr::Tuple(t) => exprs(&t.elts, f),
        Expr::Slice(s) => exprs(
            s.lower.as_deref().into_iter().chain(s.upper.as_deref()).chain(s.step.as_deref()),
            f,
        ),
        Expr::StringLiteral(_)
        | Expr::BytesLiteral(_)
        | Expr::NumberLiteral(_)
        | Expr::BooleanLiteral(_)
        | Expr::NoneLiteral(_)
        | Expr::EllipsisLiteral(_)
        | Expr::Name(_)
        | Expr::IpyEscapeCommand(_) => {}
    }
}

fn pattern<'a>(p: &'a Pattern, f: Visit<'_, 'a>) {
    match p {
        Pattern::MatchValue(v) => f(N::Expr(&v.value)),
        Pattern::MatchSingleton(_) | Pattern::MatchStar(_) => {}
        Pattern::MatchSequence(s) => s.patterns.iter().for_each(|p| f(N::Pattern(p))),
        Pattern::MatchMapping(m) => {
            exprs(&m.keys, f);
            m.patterns.iter().for_each(|p| f(N::Pattern(p)));
        }
        Pattern::MatchClass(c) => {
            f(N::Expr(&c.cls));
            c.arguments.patterns.iter().for_each(|p| f(N::Pattern(p)));
            c.arguments.keywords.iter().for_each(|k| f(N::Pattern(&k.pattern)));
        }
        Pattern::MatchAs(a) => {
            if let Some(p) = &a.pattern {
                f(N::Pattern(p));
            }
        }
        Pattern::MatchOr(o) => o.patterns.iter().for_each(|p| f(N::Pattern(p))),
    }
}
