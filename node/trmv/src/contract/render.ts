// Template rendering with the canonical repr.
import { findings } from './snapshot.js';
import { canonicalRepr, normalize } from './values.js';

const PLACEHOLDER_RE = /\{\{|\}\}|\{([a-z_]+)(!r)?\}/g;

export function renderTemplate(template: string, values: Record<string, unknown>): string {
  return template.replace(PLACEHOLDER_RE, (match: string, name?: string, bang?: string) => {
    if (name === undefined) return match[0] ?? '';
    const value = normalize(values[name]);
    return typeof value === 'string' && !bang ? value : canonicalRepr(value);
  });
}

/** The registry template `id` rendered with `values`. */
export function message(id: string, values: Record<string, unknown> = {}): string {
  const template = findings()[id];
  if (template === undefined) throw new Error(`unknown template ${id}`);
  return renderTemplate(template, values);
}
