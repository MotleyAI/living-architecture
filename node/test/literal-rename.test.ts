// A string-literal type member renamed where the language service types a string by that union.
import { describe, expect, it } from 'vitest';
import { message } from '../src/contract/index.js';
import { copyProject, files, lineCol, read, refactor, tsProject } from './refactor-project.js';

const KINDS = "export type Kind = 'edit_model' | 'drop';\nexport type Other = 'edit_model' | 'zzz';\nexport type Alias = Kind;\n";
const USE = `import type { Alias, Kind, Other } from './kinds';

export function f(kind: Kind): Kind {
  return kind;
}

export function g(o: Other): Other {
  return o;
}

export const typed: Kind = 'edit_model';
export const quoted: Kind = "edit_model";
export const aliased: Alias = 'edit_model';
export const argument = f('edit_model');
export const listed: Kind[] = ['edit_model', 'drop'];
export const other = g('edit_model');
export const plain: string = 'edit_model';
export const frozen = 'edit_model' as const;

export function compare(k: Kind): number {
  return k === 'edit_model' ? 1 : 0;
}

export function branch(k: Kind): number {
  switch (k) {
    case 'edit_model':
      return 2;
    default:
      return 0;
  }
}
`;
const USE_AFTER = USE.replace("typed: Kind = 'edit_model'", "typed: Kind = 'edit_master'")
  .replace('quoted: Kind = "edit_model"', 'quoted: Kind = "edit_master"')
  .replace("aliased: Alias = 'edit_model'", "aliased: Alias = 'edit_master'")
  .replace("f('edit_model')", "f('edit_master')")
  .replace("['edit_model', 'drop']", "['edit_master', 'drop']")
  .replace("k === 'edit_model'", "k === 'edit_master'")
  .replace("case 'edit_model':", "case 'edit_master':");

const project = { 'src/kinds.ts': KINDS, 'src/use.ts': USE };
const renameKind = (root: string, newName: string, ...flags: string[]) =>
  refactor(root, '--apply', 'rename', '--file', 'src/kinds.ts', '--symbol', "Kind['edit_model']", '--new-name', newName, ...flags);

describe('Literal member rename', () => {
  it('rewrites every string typed by the union, keeping its quotes, and nothing else', () => {
    const root = tsProject(project);
    expect(renameKind(root, 'edit_master').code).toBe(0);
    expect(read(root, 'src/kinds.ts')).toBe(KINDS.replace("Kind = 'edit_model'", "Kind = 'edit_master'"));
    expect(read(root, 'src/use.ts')).toBe(USE_AFTER);
  });

  it('a locator on the string inside the type equals the path', () => {
    const bySymbol = tsProject(project);
    const byPosition = copyProject(bySymbol);
    const position = lineCol(byPosition, 'src/kinds.ts', "'edit_model'", 0, 1);
    const expected = refactor(byPosition, '--apply', 'rename', '--file', 'src/kinds.ts', ...position, '--new-name', 'edit_master');
    expect(renameKind(bySymbol, 'edit_master')).toEqual(expected);
    expect(files(bySymbol)).toEqual(files(byPosition));
  });

  it('is located through a parameter annotation', () => {
    const inline = "export function g(mode: 'fast' | 'slow'): string {\n  return mode;\n}\n\nexport const call = g('fast');\n";
    const root = tsProject({ 'src/g.ts': inline });
    const result = refactor(root, '--apply', 'rename', '--file', 'src/g.ts', '--symbol', "g(mode)['fast']", '--new-name', 'quick');
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, 'src/g.ts')).toBe(inline.replaceAll("'fast'", "'quick'"));
  });

  it('takes a value that is no identifier', () => {
    const root = tsProject(project);
    expect(renameKind(root, 'edit master').code).toBe(0);
    expect(read(root, 'src/use.ts')).toContain("typed: Kind = 'edit master'");
  });

  it.each(["it's", 'say "hi"', 'back\\slash', 'two\nlines'])('refuses the value %j', (value) => {
    const root = tsProject(project);
    const before = files(root);
    expect(renameKind(root, value)).toEqual({ code: 2, out: '', err: `${message('refactor.literal-value', { value })}\n` });
    expect(files(root)).toEqual(before);
  });

  it.each([[[]], [['--docs']]])('lists the other equal strings as leftovers, not one typed by another union (flags %j)', (flags) => {
    const root = tsProject(project);
    const result = renameKind(root, 'edit_master', ...flags);
    expect(result.code).toBe(0);
    const leftover = (path: string, line: number): string => message('refactor.leftover', { path, line, where: 'string', old: 'edit_model' });
    expect(result.err).toBe([leftover('src/kinds.ts', 2), leftover('src/use.ts', 17), leftover('src/use.ts', 18), ''].join('\n'));
  });

  it('lists a string where any string is accepted, or that already has an error', () => {
    const loose = `import type { Other } from './kinds';

export function h(o: Other | string): string {
  return o;
}

export function n(o: number): number {
  return o;
}

export const wide = h('edit_model');
export const wrong = n('edit_model');
`;
    const root = tsProject({ ...project, 'src/loose.ts': loose });
    const result = renameKind(root, 'edit_master');
    const leftover = (line: number): string => message('refactor.leftover', { path: 'src/loose.ts', line, where: 'string', old: 'edit_model' });
    expect(result.code).toBe(0);
    expect(result.err.split('\n')).toEqual(expect.arrayContaining([leftover(11), leftover(12)]));
    expect(read(root, 'src/loose.ts')).toBe(loose);
  });
});
