//! The canonical binding dump, byte-equal to `spike/py/binding_dump.py`'s.

use std::collections::BTreeSet;

use ruff_python_ast::name::Name;
use rustc_hash::FxHashMap;
use serde_json::{Value, json};

use crate::analysis::{Binding, Parsed, Span};

fn span(s: Option<Span>) -> Value {
    s.map_or(Value::Null, |(a, b)| json!([a, b]))
}

fn binding(b: &Binding, dotted: &str) -> Value {
    match b {
        Binding::Other => Value::Null,
        Binding::Module(m) => json!(["module", m.as_str(), ""]),
        Binding::Member(m, n) => json!(["member", m.as_ref().map(Name::as_str), n.as_str()]),
        Binding::Decl(key) => json!(["decl", dotted, &**key]),
    }
}

fn table(t: &FxHashMap<Name, Vec<Binding>>, dotted: &str) -> Value {
    let mut names: Vec<&Name> = t.keys().collect();
    names.sort();
    names.into_iter().map(|n| json!([n.as_str(), t[n].iter().map(|b| binding(b, dotted)).collect::<Vec<_>>()])).collect()
}

fn sorted_names(names: &[Name]) -> Value {
    names.iter().map(Name::as_str).collect::<BTreeSet<_>>().into_iter().collect()
}

fn keyed<T>(map: &FxHashMap<(u32, Name), T>) -> Vec<(&(u32, Name), &T)> {
    let mut out: Vec<_> = map.iter().collect();
    out.sort_by(|a, b| a.0.cmp(b.0));
    out
}

pub fn dump(p: &Parsed) -> Value {
    let s = &p.scopes;
    let dotted = p.dotted.as_str();
    let scopes: Vec<Value> = s
        .0
        .iter()
        .enumerate()
        .map(|(i, sc)| {
            json!({"id": i, "kind": sc.kind.name(), "parent": sc.parent, "raw": table(&sc.raw, dotted),
                   "bindings": table(&sc.bindings, dotted), "globals": sorted_names(&sc.globals),
                   "nonlocals": sorted_names(&sc.nonlocals)})
        })
        .collect();
    let sites: Vec<Value> = keyed(&p.sites).into_iter().map(|((sc, n), o)| json!([sc, n.as_str(), o])).collect();
    let points: Vec<Value> = keyed(&p.points)
        .into_iter()
        .map(|((sc, n), found)| {
            let found: Vec<Value> = found.iter().map(|(b, run, first)| json!([b, run, span(*first)])).collect();
            json!([sc, n.as_str(), found])
        })
        .collect();
    let mut names: Vec<&Name> = p.named.keys().collect();
    names.sort();
    let occurrences: Vec<Value> = names
        .iter()
        .map(|n| {
            let occs: Vec<Value> = p.named[*n].iter().map(|o| json!([o.offset, o.scope, o.binds])).collect();
            json!([n.as_str(), occs])
        })
        .collect();
    let mut loops: Vec<(&u32, &Vec<[Span; 2]>)> = p.loops.iter().collect();
    loops.sort();
    let loops: Vec<Value> = loops
        .into_iter()
        .map(|(sc, l)| json!([sc, l.iter().map(|[a, b]| json!([[a.0, a.1], [b.0, b.1]])).collect::<Vec<_>>()]))
        .collect();
    let used: BTreeSet<(u32, &Name)> = p.named.iter().flat_map(|(n, os)| os.iter().map(move |o| (o.scope, n))).collect();
    let resolution: Vec<Value> =
        used.iter().map(|(i, n)| json!([i, n.as_str(), s.owner(*i, n), s.resolving(*i, n)])).collect();
    let offsets: BTreeSet<(&Name, u32)> = p.named.iter().flat_map(|(n, os)| os.iter().map(move |o| (n, o.offset))).collect();
    let classes: BTreeSet<(u32, &Name)> =
        p.points.keys().filter(|(sc, _)| s.0[*sc as usize].kind.name() == "class").map(|(sc, n)| (*sc, n)).collect();
    let may_precede: Vec<Value> = classes
        .iter()
        .flat_map(|(c, n)| {
            offsets.range((*n, 0)..=(*n, u32::MAX)).map(move |(_, at)| json!([c, n.as_str(), at, p.may_precede(*c, n, *at)]))
        })
        .collect();
    let joined: Vec<Value> = (0..s.0.len() as u32).map(|i| json!([i, p.joined(i)])).collect();
    json!({
        "status": "ok",
        "scopes": scopes,
        "sites": sites,
        "points": points,
        "occurrences": occurrences,
        "stars": p.stars.iter().map(|(d, o)| json!([d, o])).collect::<Vec<_>>(),
        "all_names": p.all_names,
        "loops": loops,
        "resolution": resolution,
        "may_precede": may_precede,
        "joined": joined,
    })
}
