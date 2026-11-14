// The template renderer, through src/contract/index.ts: renderTemplate(template, values): string and
// message(id, values?): string (the findings.yaml template `id` rendered with `values`).
import { describe, expect, it } from 'vitest';
import { message, renderTemplate } from '../src/contract/index.js';

describe('renderTemplate', () => {
  it('inserts a string as is', () => {
    expect(renderTemplate('{node} claims {unit}', { node: 'python.api', unit: 'pkg.api' })).toBe('python.api claims pkg.api');
  });

  it('inserts the canonical repr for !r', () => {
    expect(renderTemplate('got {value!r}', { value: "it's" })).toBe('got "it\'s"');
    expect(renderTemplate('got {value!r}', { value: 'plain' })).toBe("got 'plain'");
  });

  it('renders a non-string plain placeholder as its canonical repr', () => {
    expect(renderTemplate('{a} {b} {c} {d}', { a: true, b: null, c: ['x', null], d: { k: 'v' } })).toBe(
      "True None ['x', None] {'k': 'v'}",
    );
  });

  it('treats doubled braces as literal', () => {
    expect(renderTemplate('{{x}} {y}', { y: 'v' })).toBe('{x} v');
    expect(renderTemplate('{{{y}}}', { y: 'v' })).toBe('{v}');
  });

  it('renders a multi-line template to several lines', () => {
    expect(renderTemplate('a {x}\nb {x!r}', { x: 'v' })).toBe("a v\nb 'v'");
  });
});

describe('message', () => {
  it('renders a registry template by id', () => {
    expect(message('arch-check.layout-not-relative', { key: 'source_root', value: "it's" })).toBe(
      'architecture/index.yaml: source_root "it\'s" must be a relative path',
    );
  });

  it('renders a template without placeholders', () => {
    expect(message('arch-check.ok')).toBe('arch_check: OK');
  });

  it('renders explicit-any with the language spellings of the any and top types', () => {
    expect(message('compliance.explicit-any', { path: 'a.ts', line: 3, any: 'any', top: 'unknown' })).toBe(
      'a.ts:3: explicit-any: an `any` type — use a real type or `unknown`',
    );
    expect(message('compliance.explicit-any', { path: 'm.py', line: 2, any: 'Any', top: 'object' })).toBe(
      'm.py:2: explicit-any: an `Any` type — use a real type or `object`',
    );
  });
});
