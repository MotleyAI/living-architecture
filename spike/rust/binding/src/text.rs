//! dr's decoding rule (`Snapshot.text`) and a decoded text's offsets: bytes to characters, CPython line and column.

use unicode_normalization::UnicodeNormalization;

const BOM: &[u8] = b"\xef\xbb\xbf";

/// A decoding outcome: the text, or why there is none.
pub enum Decoded {
    Text(String),
    Undecodable,
    /// A codec Python has that this port does not implement.
    Unsupported(String),
}

/// `chr(c).isspace()` for a byte.
fn byte_space(c: u8) -> bool {
    matches!(c, 9..=13 | 0x1c..=0x20 | 0x85 | 0xa0)
}

/// `str.isspace()` for one character.
pub fn py_space(c: char) -> bool {
    if c.is_ascii() {
        byte_space(c as u8)
    } else {
        c.is_whitespace() || c == '\u{85}'
    }
}

/// `re.match(b"^[ \t\f]*#.*?coding[:=][ \t]*([-_.a-zA-Z0-9]+)", line)`.
fn cookie_line(line: &[u8]) -> bool {
    let mut i = line.iter().take_while(|c| matches!(c, b' ' | b'\t' | 0x0c)).count();
    if line.get(i) != Some(&b'#') {
        return false;
    }
    i += 1;
    (i..line.len()).any(|at| {
        if !line[at..].starts_with(b"coding") {
            return false;
        }
        let mut j = at + 6;
        if !matches!(line.get(j), Some(b':' | b'=')) {
            return false;
        }
        j += 1;
        while matches!(line.get(j), Some(b' ' | b'\t')) {
            j += 1;
        }
        matches!(line.get(j), Some(c) if c.is_ascii_alphanumeric() || matches!(c, b'-' | b'_' | b'.'))
    })
}

/// rope's `_find_coding`.
fn find_coding(line: &[u8]) -> Option<String> {
    let mut start = line.windows(6).position(|w| w == b"coding")? + 6;
    if !matches!(line.get(start), Some(b'=' | b':')) {
        return None;
    }
    start += 1;
    while start < line.len() && byte_space(line[start]) {
        start += 1;
    }
    let mut end = start;
    while end < line.len() && (char::from(line[end]).is_alphanumeric() || matches!(line[end], b'-' | b'_')) {
        end += 1;
    }
    String::from_utf8(line[start..end].to_vec()).ok()
}

/// dr's `read_str_coding` on bytes.
pub fn read_str_coding(body: &[u8]) -> Option<String> {
    for line in body.splitn(3, |c| *c == b'\n').take(2) {
        if cookie_line(line) {
            return find_coding(line);
        }
    }
    None
}

/// `encodings.normalize_encoding` after lowercasing.
fn normalize(name: &str) -> String {
    let mut out = String::new();
    let mut punct = false;
    for c in name.to_lowercase().chars() {
        if c.is_alphanumeric() || c == '.' {
            if punct && !out.is_empty() {
                out.push('_');
            }
            if c.is_ascii() {
                out.push(c);
            }
            punct = false;
        } else {
            punct = true;
        }
    }
    out
}

enum Codec {
    Utf8,
    Utf8Sig,
    Latin1,
    Ascii,
}

fn codec(name: &str) -> Option<Codec> {
    let n = normalize(name);
    Some(match n.as_str() {
        "utf_8" | "utf8" | "u8" | "utf" | "cp65001" | "utf8_ucs2" | "utf8_ucs4" => Codec::Utf8,
        "utf_8_sig" => Codec::Utf8Sig,
        "latin_1" | "latin1" | "latin" | "l1" | "iso8859_1" | "iso_8859_1" | "iso_ir_100" | "8859" | "cp819"
        | "ibm819" | "iso_8859_1_1987" | "csisolatin1" | "iso8859" => Codec::Latin1,
        "ascii" | "646" | "us_ascii" | "us" | "ansi_x3.4_1968" | "ansi_x3_4_1968" | "ansi_x3.4_1986" | "cp367"
        | "csascii" | "ibm367" | "iso646_us" | "iso_646.irv_1991" | "iso_ir_6" => Codec::Ascii,
        _ => return None,
    })
}

/// `Snapshot.text`: the UTF-8 BOM stripped, then the cookie's codec, else UTF-8.
pub fn decode(data: &[u8]) -> Decoded {
    let body = data.strip_prefix(BOM).unwrap_or(data);
    let name = read_str_coding(body).unwrap_or_else(|| "utf-8".to_owned());
    let Some(found) = codec(&name) else {
        let known = include_str!("codecs.txt").lines().any(|n| n == normalize(&name));
        return if known { Decoded::Unsupported(name) } else { Decoded::Undecodable };
    };
    let text = match found {
        Codec::Utf8 => String::from_utf8(body.to_vec()).ok(),
        Codec::Utf8Sig => String::from_utf8(body.strip_prefix(BOM).unwrap_or(body).to_vec()).ok(),
        Codec::Latin1 => Some(body.iter().map(|&c| char::from(c)).collect()),
        Codec::Ascii => body.is_ascii().then(|| String::from_utf8(body.to_vec()).unwrap_or_default()),
    };
    text.map_or(Decoded::Undecodable, Decoded::Text)
}

/// A decoded text: its byte offsets as characters, and as CPython's line and byte column.
pub struct Src<'t> {
    pub text: &'t str,
    lines: Vec<u32>,
    chars: Option<Vec<u32>>,
}

impl<'t> Src<'t> {
    pub fn new(text: &'t str) -> Self {
        let bytes = text.as_bytes();
        let mut lines = vec![0];
        let mut i = 0;
        while let Some(at) = memchr::memchr2(b'\r', b'\n', &bytes[i..]) {
            i += at + 1;
            if bytes[i - 1] == b'\r' && bytes.get(i) == Some(&b'\n') {
                i += 1;
            }
            lines.push(i as u32);
        }
        let chars = (!text.is_ascii()).then(|| {
            let mut out = vec![0; bytes.len() + 1];
            let mut n = 0;
            for (at, ch) in text.char_indices() {
                for k in 0..ch.len_utf8() {
                    out[at + k] = n;
                }
                n += 1;
            }
            out[bytes.len()] = n;
            out
        });
        Self { text, lines, chars }
    }

    /// The character offset of byte offset `at`.
    pub fn ch(&self, at: u32) -> u32 {
        self.chars.as_ref().map_or(at, |c| c[at as usize])
    }

    /// CPython's `lineno:col_offset` of byte offset `at`.
    pub fn key(&self, at: u32) -> String {
        let line = self.lines.partition_point(|s| *s <= at);
        format!("{}:{}", line, at - self.lines[line - 1])
    }

    /// The end of the run of identifier characters starting at byte `at`.
    pub fn name_end(&self, at: u32) -> u32 {
        let rest = &self.text[at as usize..];
        let len: usize = rest.chars().take_while(|c| unicode_ident::is_xid_continue(*c)).map(char::len_utf8).sum();
        at + len as u32
    }

    /// The identifier starting at byte `at`, if it spells `name`.
    pub fn name_from(&self, at: u32, name: &str) -> Option<u32> {
        let end = self.name_end(at);
        (end > at && same_name(&self.text[at as usize..end as usize], name)).then_some(at)
    }

    /// The first or last whole identifier between bytes `start` and `end` that spells `word`.
    pub fn word(&self, start: u32, end: u32, word: &str, last: bool) -> Option<u32> {
        let mut found = None;
        let mut at = start;
        while at < end {
            let stop = self.name_end(at).min(end);
            if stop > at && same_name(&self.text[at as usize..stop as usize], word) {
                if !last {
                    return Some(at);
                }
                found = Some(at);
            }
            let step = self.text[at as usize..].chars().next().map_or(1, char::len_utf8) as u32;
            at = stop.max(at + step);
        }
        found
    }
}

/// `raw` spells `name` as Python reads identifiers.
pub fn same_name(raw: &str, name: &str) -> bool {
    if raw.is_ascii() { raw == name } else { raw.nfkc().eq(name.chars()) }
}
