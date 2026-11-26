export type Kind2 = 'formula' | 'sql';
export const DISPATCH_FORMULA = 'formula';

export function viaConstant(): Kind2 {
  return DISPATCH_FORMULA;
}
