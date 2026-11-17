//! `binding-bench --python-version 3.X --root DIR --regime keep|drop [--threads N] < files`: the per-file analysis
//! timed end to end with phase timers, no dump; one JSON object of seconds. `--threads` above 1 times rayon's
//! parallel run, total only.

use std::path::Path;
use std::time::Instant;

use binding::analysis::{Parsed, analyse_tree, parse};
use binding::text::{Decoded, Src, decode};
use rayon::prelude::*;
use ruff_python_ast::PythonVersion;
use serde_json::json;

#[derive(Default)]
struct Phases {
    decode: f64,
    parse: f64,
    analyse: f64,
    analysed: usize,
}

/// One file decoded, parsed and analysed, its phases added to `phases`.
fn one(root: &Path, rel: &str, version: PythonVersion, phases: &mut Phases) -> Option<Parsed> {
    let t0 = Instant::now();
    let data = std::fs::read(root.join(rel)).ok()?;
    let Decoded::Text(text) = decode(&data) else {
        phases.decode += t0.elapsed().as_secs_f64();
        return None;
    };
    let t1 = Instant::now();
    let src = Src::new(&text);
    let tree = parse(&text, version);
    let t2 = Instant::now();
    let parsed = tree.map(|tree| analyse_tree(&src, &tree, rel, version));
    let t3 = Instant::now();
    phases.decode += (t1 - t0).as_secs_f64();
    phases.parse += (t2 - t1).as_secs_f64();
    phases.analyse += (t3 - t2).as_secs_f64();
    phases.analysed += usize::from(parsed.is_some());
    parsed
}

fn main() {
    let cli = binding::Cli::parse(&[], &["--regime", "--threads"], &[]).unwrap_or_else(|e| {
        eprintln!("{e}");
        std::process::exit(2)
    });
    let keep = match cli.options.get("--regime").map(String::as_str) {
        Some("keep") => true,
        Some("drop") => false,
        _ => {
            eprintln!("--regime keep|drop is required");
            std::process::exit(2)
        }
    };
    let threads: usize = cli.options.get("--threads").and_then(|n| n.parse().ok()).unwrap_or(1);
    let rels = &cli.rels;
    let start = Instant::now();
    let doc = if threads > 1 {
        let pool = rayon::ThreadPoolBuilder::new().num_threads(threads).build().expect("pool");
        let (kept, analysed) = pool.install(|| {
            let run = |rel: &String| one(&cli.root, rel, cli.version, &mut Phases::default());
            if keep {
                let kept: Vec<Parsed> = rels.par_iter().filter_map(run).collect();
                (kept.len(), kept.len())
            } else {
                (0, rels.par_iter().filter(|rel| run(rel).is_some()).count())
            }
        });
        json!({"files": rels.len(), "analysed": analysed, "kept": kept, "total": start.elapsed().as_secs_f64(),
               "threads": threads})
    } else {
        let mut phases = Phases::default();
        let mut kept: Vec<Parsed> = vec![];
        for rel in rels {
            if let Some(parsed) = one(&cli.root, rel, cli.version, &mut phases) {
                if keep {
                    kept.push(parsed);
                }
            }
        }
        json!({"files": rels.len(), "analysed": phases.analysed, "kept": kept.len(),
               "total": start.elapsed().as_secs_f64(), "decode": phases.decode, "parse": phases.parse,
               "analyse": phases.analyse})
    };
    println!("{doc}");
}
