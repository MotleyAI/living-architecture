// Every kind a dr-compliance finding prints is a check id `--select` accepts (parse-error aside).
import { describe, expect, it } from 'vitest';
import { findings, language, languageIds } from '../src/contract/index.js';

describe('dr-compliance kinds', () => {
  const checks = new Set(languageIds().flatMap((id) => language(id).compliance_checks as string[]));
  const kinds = new Set(
    Object.entries(findings())
      .filter(([id]) => id.startsWith('compliance.'))
      .map(([, text]) => /^\{path\}(?::\{line\})?: ([a-z-]+):/.exec(text)?.[1])
      .filter((kind): kind is string => kind !== undefined),
  );

  it('prints attr-blindspot', () => {
    expect(kinds.has('attr-blindspot')).toBe(true);
  });

  it('selects every printed kind', () => {
    expect([...kinds].filter((kind) => kind !== 'parse-error' && !checks.has(kind))).toEqual([]);
  });

  it('lists attr-blindspot for both languages', () => {
    for (const id of ['python', 'typescript']) expect(language(id).compliance_checks).toContain('attr-blindspot');
  });
});
