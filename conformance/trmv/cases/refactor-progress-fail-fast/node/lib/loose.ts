export function loose(s: any): number {
  return s.drop() + s.size();
}
