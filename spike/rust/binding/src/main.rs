//! `binding-dump --python-version 3.X --root DIR [REL ...]`: one `REL<TAB>JSON` line per file.

use std::io::Write;

use binding::{Cli, analyse_file, dump::dump};

fn main() {
    let cli = Cli::parse(&[], &[], &[]).unwrap_or_else(|e| {
        eprintln!("{e}");
        std::process::exit(2)
    });
    let mut out = std::io::BufWriter::new(std::io::stdout().lock());
    for rel in &cli.rels {
        let doc = analyse_file(&cli.root, rel, cli.version).map_or_else(|status| status, |p| dump(&p));
        writeln!(out, "{rel}\t{doc}").expect("stdout");
    }
}
