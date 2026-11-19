export type Kind2 = 'formula' | 'sql';
export const DISPATCH_FORMULA = 'formula';

export function viaConstant(): Kind2 {
  return DISPATCH_FORMULA;
}

export function matches(doc: Record<string, string>): boolean {
  return doc['kind'] === DISPATCH_FORMULA;
}
