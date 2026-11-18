// The errors an edited program has that the program before the edits lacks, checked in memory.
import type * as TS from 'typescript';
import { byCodePoint } from '../contract/index.js';
import { ts } from '../lang/index.js';
import { applyEdits, type Edit } from './edits.js';
import { mapRange, replaced, unmapPosition } from './position.js';
import type { Refactor } from './session.js';
import { Workspace } from './workspace.js';

/** A checker error: its file, span and code. */
interface CheckerError {
  path: string;
  start: number;
  end: number;
  code: number;
}

/** An error the edits bring: its file and its span in the text before them. */
export interface AddedError {
  path: string;
  start: number;
  end: number;
}

/** The semantic errors of every source of `services`' programs, declaration files and dependencies aside. */
function errors(services: Iterable<TS.LanguageService>): CheckerError[] {
  const out: CheckerError[] = [];
  for (const service of services) {
    const program = service.getProgram();
    for (const file of program?.getSourceFiles() ?? []) {
      if (program === undefined || file.isDeclarationFile || program.isSourceFileFromExternalLibrary(file)) continue;
      for (const d of program.getSemanticDiagnostics(file)) {
        if (d.category !== ts().DiagnosticCategory.Error || d.start === undefined) continue;
        out.push({ path: file.fileName, start: d.start, end: d.start + (d.length ?? 0), code: d.code });
      }
    }
  }
  return out;
}

/** The errors of every project holding a file of `edits` (per file, sorted and disjoint) once they are applied, that
 * it lacks before them at the same code and mapped position; in path and position order. */
export function addedErrors(r: Refactor, edits: Map<string, Edit[]>): AddedError[] {
  const paths = [...edits.keys()];
  const spans = new Map(paths.map((path) => [path, replaced(edits.get(path) ?? [])]));
  const texts = new Map<string, string>();
  for (const path of paths) {
    const text = r.services(path)[0]?.getProgram()?.getSourceFile(path)?.text;
    if (text !== undefined) texts.set(path, applyEdits(text, edits.get(path) ?? []));
  }
  const key = (path: string, start: number, code: number): string => `${path}\0${start}\0${code}`;
  const before = new Set<string>();
  for (const e of errors(new Set(paths.flatMap((path) => r.services(path))))) {
    before.add(key(e.path, mapRange(spans.get(e.path) ?? [], e.start, e.start)[0], e.code));
  }
  const edited = new Workspace(r.root, (path) => texts.get(path), new Map(), null, r.workspace.registry);
  const out = new Map<string, AddedError>();
  for (const e of errors(new Set(paths.flatMap((path) => edited.holding(path))))) {
    if (before.has(key(e.path, e.start, e.code))) continue;
    const fileSpans = spans.get(e.path) ?? [];
    const [start, end] = [unmapPosition(fileSpans, e.start), unmapPosition(fileSpans, e.end)];
    out.set(`${e.path}\0${start}\0${end}`, { path: e.path, start, end });
  }
  return [...out.values()].sort((a, b) => byCodePoint(a.path, b.path) || a.start - b.start || a.end - b.end);
}
