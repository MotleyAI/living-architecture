//! The spike's port of dr's per-file binding analysis onto ruff's parser.

pub mod analysis;
pub mod dump;
pub mod text;
pub mod walk;

use std::path::Path;

use ruff_python_ast::PythonVersion;
use serde_json::{Value, json};

use crate::analysis::{Failure, Parsed, analyse};
use crate::text::{Decoded, decode};

/// One file read, decoded and analysed as dr does; the status dump when it does not decode or parse.
pub fn analyse_file(root: &Path, rel: &str, version: PythonVersion) -> Result<Parsed, Value> {
    let data = std::fs::read(root.join(rel)).map_err(|e| json!({"status": format!("unreadable: {e}")}))?;
    match decode(&data) {
        Decoded::Text(text) => analyse(&text, rel, version).map_err(|Failure::Syntax| json!({"status": "syntax-error"})),
        Decoded::Undecodable => Err(json!({"status": "undecodable"})),
        Decoded::Unsupported(name) => Err(json!({"status": format!("unsupported-encoding: {name}")})),
    }
}

/// The REL arguments, else one per stdin line.
pub fn rels(args: Vec<String>) -> Vec<String> {
    if !args.is_empty() {
        return args;
    }
    std::io::stdin().lines().map_while(Result::ok).filter(|l| !l.trim().is_empty()).collect()
}

/// `--python-version 3.X --root DIR [REL ...]`, with the given switches and valued options.
pub struct Cli {
    pub version: PythonVersion,
    pub version_text: String,
    pub root: std::path::PathBuf,
    pub switches: Vec<String>,
    pub options: std::collections::HashMap<String, String>,
    pub rels: Vec<String>,
}

impl Cli {
    /// The command line; RELs are read from stdin when none is given, unless a switch makes `--root` optional.
    pub fn parse(switches: &[&str], valued: &[&str], rootless: &[&str]) -> Result<Self, String> {
        let mut args = std::env::args().skip(1);
        let (mut version_text, mut root, mut found, mut options, mut rest) =
            (None, None, vec![], std::collections::HashMap::new(), vec![]);
        while let Some(arg) = args.next() {
            match arg.as_str() {
                "--python-version" => version_text = args.next(),
                "--root" => root = args.next(),
                f if switches.contains(&f) => found.push(arg),
                f if valued.contains(&f) => {
                    options.insert(arg.clone(), args.next().ok_or_else(|| format!("{arg} needs a value"))?);
                }
                _ => rest.push(arg),
            }
        }
        let version_text = version_text.ok_or("--python-version is required")?;
        let version = analysis::version(&version_text).ok_or_else(|| format!("unknown version {version_text}"))?;
        let needs_root = !found.iter().any(|f| rootless.contains(&f.as_str()));
        let root = match root {
            Some(r) => r.into(),
            None if needs_root => return Err("--root is required".into()),
            None => std::path::PathBuf::new(),
        };
        let rels = if needs_root { rels(rest) } else { rest };
        Ok(Self { version, version_text, root, switches: found, options, rels })
    }
}
