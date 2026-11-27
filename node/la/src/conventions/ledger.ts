// The stealth waiver ledger: waivers kept outside the repo, matched by path, rule and trimmed line text.
import { ConfigError, parseConfig } from 'type-rename-move/config';
import { conventions, decodeUtf8OrNull, isOsError, message, osErrorText, readFile, schema, toPlain, validate } from '../contract/index.js';

export interface LedgerEntry {
  path: string;
  rule: string;
  line: string;
  reason: string;
}

const invalid = (path: string, error: string): ConfigError => new ConfigError(message('conventions.ledger-invalid', { path, error }));

/** The ledger's entries; none when it is missing. ConfigError naming the file when it is not a valid ledger. */
export function loadLedger(path: string): LedgerEntry[] {
  let bytes: Buffer;
  try {
    bytes = readFile(path);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return [];
    if (isOsError(error)) throw invalid(path, osErrorText(error, path, path));
    throw error;
  }
  const text = decodeUtf8OrNull(bytes);
  if (text === null) throw new ConfigError(message('yaml.invalid', { path }));
  const data = parseConfig(text, path) ?? [];
  const errors = validate(schema('waiver-ledger'), data);
  if (errors.length > 0) throw invalid(path, errors.join('; '));
  const entries = toPlain(data) as LedgerEntry[];
  const rules = conventions().rules;
  for (const [index, entry] of entries.entries()) {
    if (!rules[entry.rule]?.waivable) throw invalid(path, message('conventions.ledger-rule', { index, rule: entry.rule }));
  }
  return entries.map(({ path: p, rule, line, reason }) => ({ path: p, rule, line, reason }));
}

/** Whether an entry waives the violation of `rule` on `line` of `path`. */
export function waived(entries: LedgerEntry[], { path, rule, line }: { path: string; rule: string; line: string }): boolean {
  const text = line.replace(/\r$/, '').trim();
  return entries.some((e) => e.path === path && e.rule === rule && e.line === text);
}
