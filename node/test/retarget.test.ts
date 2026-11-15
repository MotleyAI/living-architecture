// dr-refactor retarget: references to an alias rewritten to name its target, the alias left in place.
import { writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { message } from '../src/contract/index.js';
import { ts } from '../src/lang/index.js';
import { copyProject, expectedOut, files, mapYaml, read, refactor, renameHeader, tsProject } from './refactor-project.js';

const ENGINE = `export class Engine {
  saveModel(m: string): void {
    console.log(m);
  }

  /** @deprecated use saveModel */
  save(m: string): void {
    return this.saveModel(m);
  }
}
`;
const ENGINE_USE = `import { Engine } from './engine';

export function use(engine: Engine): void {
  engine.save('m');
}
`;
const MODELS = 'export class Model {}\n\n/** @deprecated use Model */\nexport const AcmeModel = Model;\n';

const API = 'export function modern(): number {\n  return 1;\n}\n\n/** @deprecated use modern */\nexport const legacy = modern;\n';

const header = (old: string, next: string): string => message('refactor.retarget-header', { old, new: next });

/** The codes of the type checker's diagnostics over `root`'s tsconfig. */
function diagnosticCodes(root: string): number[] {
  const config = ts().getParsedCommandLineOfConfigFile(join(root, 'tsconfig.json'), {}, { ...ts().sys, onUnRecoverableConfigFileDiagnostic: () => undefined });
  if (config === undefined) throw new Error('no tsconfig');
  return ts().getPreEmitDiagnostics(ts().createProgram(config.fileNames, config.options)).map((d) => d.code);
}

describe('retarget', () => {
  it('moves a call of a deprecated method to its target and leaves the method', () => {
    const root = tsProject({ 'src/engine.ts': ENGINE, 'src/use.ts': ENGINE_USE });
    const result = refactor(root, '--apply', 'retarget', '--file', 'src/engine.ts', '--symbol', 'Engine.save', '--target', 'Engine.saveModel');
    const use = ENGINE_USE.replace("engine.save('m')", "engine.saveModel('m')");
    expect(result).toEqual({ code: 0, out: expectedOut([header('save', 'saveModel')], [{ path: 'src/use.ts', old: ENGINE_USE, new: use }], true), err: '' });
    expect(read(root, 'src/engine.ts')).toBe(ENGINE);
  });

  it.each([
    ['an import re-exported', "import { modern, legacy } from './api';\n\nexport { modern, legacy };\n"],
    ['an export from', "export { modern, legacy } from './api';\n"],
  ])('keeps a re-export shim (%s)', (_kind, shim) => {
    const use = "import { legacy } from './shim';\n\nexport const n = legacy();\n";
    const root = tsProject({ 'src/api.ts': API, 'src/shim.ts': shim, 'src/use.ts': use });
    const result = refactor(root, '--apply', 'retarget', '--file', 'src/api.ts', '--symbol', 'legacy', '--target', 'modern');
    expect([result.code, result.err]).toEqual([0, '']);
    expect([read(root, 'src/api.ts'), read(root, 'src/shim.ts')]).toEqual([API, shim]);
    expect(read(root, 'src/use.ts')).toBe("import { modern } from './shim';\n\nexport const n = modern();\n");
    expect(diagnosticCodes(root)).toEqual([]);
  });

  it('removes the import the rewrite would duplicate', () => {
    const use = "import { Model, AcmeModel } from './models';\n\nexport const m = new AcmeModel();\nexport const n: Model = m;\n";
    const root = tsProject({ 'src/models.ts': MODELS, 'src/use.ts': use });
    expect(refactor(root, '--apply', 'retarget', '--file', 'src/models.ts', '--symbol', 'AcmeModel', '--target', 'Model').code).toBe(0);
    expect(read(root, 'src/use.ts')).toBe("import { Model } from './models';\n\nexport const m = new Model();\nexport const n: Model = m;\n");
    expect(read(root, 'src/models.ts')).toBe(MODELS);
  });

  it.each([
    ['in the same list', "import { legacy, type modern } from './api';\n\nexport const r: ReturnType<typeof modern> = legacy();\n", "import { modern } from './api';\n\nexport const r: ReturnType<typeof modern> = modern();\n"],
    ['as its own declaration', "import type { modern } from './api';\nimport { legacy } from './api';\n\nexport const r: ReturnType<typeof modern> = legacy();\n", "import { modern } from './api';\n\nexport const r: ReturnType<typeof modern> = modern();\n"],
  ])('keeps the value import over a type-only import of the target %s', (_where, use, expected) => {
    const root = tsProject({ 'src/api.ts': API, 'src/use.ts': use });
    expect(refactor(root, '--apply', 'retarget', '--file', 'src/api.ts', '--symbol', 'legacy', '--target', 'modern').code).toBe(0);
    expect(read(root, 'src/use.ts')).toBe(expected);
    expect(diagnosticCodes(root)).toEqual([]);
  });

  it('removes an alias import the rewrite would duplicate in another declaration', () => {
    const use = "import { modern } from './api';\nimport { legacy } from './api';\n\nexport const r = legacy() + modern();\n";
    const root = tsProject({ 'src/api.ts': API, 'src/use.ts': use });
    expect(refactor(root, '--apply', 'retarget', '--file', 'src/api.ts', '--symbol', 'legacy', '--target', 'modern').code).toBe(0);
    expect(read(root, 'src/use.ts')).toBe("import { modern } from './api';\n\nexport const r = modern() + modern();\n");
    expect(diagnosticCodes(root)).toEqual([]);
  });

  it('refuses a shorthand property where the target name is bound to something else', () => {
    const use = "import { legacy } from './api';\n\nexport function f(): object {\n  const modern = 2;\n  return { legacy, modern };\n}\n";
    const root = tsProject({ 'src/api.ts': API, 'src/use.ts': use });
    const result = refactor(root, '--apply', 'retarget', '--file', 'src/api.ts', '--symbol', 'legacy', '--target', 'modern');
    const shadowed = message('refactor.retarget-shadowed', { path: 'src/use.ts', line: 5, name: 'modern' });
    expect(result).toEqual({ code: 1, out: '', err: `${shadowed}\n` });
    expect(read(root, 'src/use.ts')).toBe(use);
  });

  it.each([
    [
      'an import re-exported and used',
      "import { legacy } from './api';\n\nexport { legacy };\n\nexport function make(): number {\n  return legacy();\n}\n",
      "import { legacy } from './api';\nimport { modern } from './api';\n\nexport { legacy };\n\nexport function make(): number {\n  return modern();\n}\n",
    ],
    ['an export from', "export { legacy } from './api';\n", "export { legacy } from './api';\n"],
  ])("rewrites a single-name shim's importers (%s)", (_kind, shim, shimAfter) => {
    const use = "import { legacy } from './shim';\n\nexport const a = legacy();\n";
    const direct = "import { legacy } from './api';\n\nexport const b = legacy();\n";
    const root = tsProject({ 'src/api.ts': API, 'src/shim.ts': shim, 'src/use.ts': use, 'src/direct.ts': direct });
    const result = refactor(root, '--apply', 'retarget', '--file', 'src/api.ts', '--symbol', 'legacy', '--target', 'modern');
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, 'src/shim.ts')).toBe(shimAfter);
    expect(read(root, 'src/use.ts')).toBe("import { modern } from './api';\n\nexport const a = modern();\n");
    expect(read(root, 'src/direct.ts')).toBe("import { modern } from './api';\n\nexport const b = modern();\n");
    expect(diagnosticCodes(root)).toEqual([]);
  });

  it('imports the target from its home for an importer of a single-name shim under a local alias', () => {
    const shim = "import { legacy } from './api';\n\nexport { legacy };\n";
    const use = "import { legacy as old } from './shim';\n\nexport const a = { old };\n";
    const root = tsProject({ 'src/api.ts': API, 'src/shim.ts': shim, 'src/use.ts': use });
    const result = refactor(root, '--apply', 'retarget', '--file', 'src/api.ts', '--symbol', 'legacy', '--target', 'modern');
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, 'src/shim.ts')).toBe(shim);
    expect(read(root, 'src/use.ts')).toBe("import { modern as old } from './api';\n\nexport const a = { old };\n");
    expect(diagnosticCodes(root)).toEqual([]);
  });

  it('keeps an aliased re-export shim, whose importers the rename does not reach', () => {
    const shim = "import { modern, legacy as old } from './api';\n\nexport { modern, old as legacy };\n";
    const use = "import { legacy } from './shim';\n\nexport const n = legacy();\n";
    const root = tsProject({ 'src/api.ts': API, 'src/shim.ts': shim, 'src/use.ts': use });
    const result = refactor(root, '--apply', 'retarget', '--file', 'src/api.ts', '--symbol', 'legacy', '--target', 'modern');
    expect([result.code, result.err]).toEqual([0, '']);
    expect([read(root, 'src/shim.ts'), read(root, 'src/use.ts')]).toEqual([shim, use]);
    expect(diagnosticCodes(root)).toEqual([]);
  });

  it('rewrites an import beside an export from, which binds nothing locally', () => {
    const shim = "import { legacy } from './api';\n\nexport { legacy } from './api';\nexport const n = legacy();\n";
    const root = tsProject({ 'src/api.ts': API, 'src/shim.ts': shim });
    const result = refactor(root, '--apply', 'retarget', '--file', 'src/api.ts', '--symbol', 'legacy', '--target', 'modern');
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, 'src/shim.ts')).toBe("import { modern } from './api';\n\nexport { legacy } from './api';\nexport const n = modern();\n");
    expect(diagnosticCodes(root)).toEqual([]);
  });

  it.each([
    [
      'the alias imported first keeps its place, the later import of the target goes',
      "import { legacy } from './api';\nimport './other';\nimport { modern } from './api';\nexport const a = legacy();\nexport const b = modern();\n",
      "import { modern } from './api';\nimport './other';\nexport const a = modern();\nexport const b = modern();\n",
    ],
    [
      'the target imported first stays, the later import of the alias goes',
      "import { modern } from './api';\nimport './other';\nimport { legacy } from './api';\nexport const a = legacy();\nexport const b = modern();\n",
      "import { modern } from './api';\nimport './other';\nexport const a = modern();\nexport const b = modern();\n",
    ],
  ])('keeps the module\'s first import: %s', (_kind, use, after) => {
    const root = tsProject({ 'src/api.ts': API, 'src/other.ts': 'export {};\n', 'src/use.ts': use });
    const result = refactor(root, '--apply', 'retarget', '--file', 'src/api.ts', '--symbol', 'legacy', '--target', 'modern');
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, 'src/use.ts')).toBe(after);
    expect(diagnosticCodes(root)).toEqual([]);
  });

  it('keeps the key of a shorthand property', () => {
    const use = "import { legacy } from './api';\n\nexport const o = { legacy };\n";
    const root = tsProject({ 'src/api.ts': API, 'src/use.ts': use });
    const result = refactor(root, '--apply', 'retarget', '--file', 'src/api.ts', '--symbol', 'legacy', '--target', 'modern');
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, 'src/use.ts')).toBe("import { modern } from './api';\n\nexport const o = { legacy: modern };\n");
  });

  it('keeps an import alias, naming the target under it', () => {
    const use = "import { AcmeModel as SM } from './models';\n\nexport const k = new SM();\n";
    const root = tsProject({ 'src/models.ts': MODELS, 'src/use.ts': use });
    expect(refactor(root, '--apply', 'retarget', '--file', 'src/models.ts', '--symbol', 'AcmeModel', '--target', 'Model').code).toBe(0);
    expect(read(root, 'src/use.ts')).toBe("import { Model as SM } from './models';\n\nexport const k = new SM();\n");
  });

  it('moves reads of a deprecated accessor to its target and leaves the accessor', () => {
    const c = 'export class C {\n  value = 1;\n\n  /** @deprecated */\n  get old(): number {\n    return this.value;\n  }\n}\n';
    const use = "import { C } from './c';\n\nexport function f(c: C): number {\n  return c.old + c.old;\n}\n";
    const root = tsProject({ 'src/c.ts': c, 'src/use.ts': use });
    expect(refactor(root, '--apply', 'retarget', '--file', 'src/c.ts', '--symbol', 'C.old', '--target', 'C.value').code).toBe(0);
    expect(read(root, 'src/use.ts')).toBe("import { C } from './c';\n\nexport function f(c: C): number {\n  return c.value + c.value;\n}\n");
    expect(read(root, 'src/c.ts')).toBe(c);
  });

  it('moves value and type uses of a merged const-and-type alias and leaves both declarations', () => {
    const models = 'export class Model {}\n\n/** @deprecated */\nexport const AcmeModel = Model;\n/** @deprecated */\nexport type AcmeModel = Model;\n';
    const use = "import { AcmeModel } from './models';\n\nexport const m: AcmeModel = new AcmeModel();\n";
    const root = tsProject({ 'src/models.ts': models, 'src/use.ts': use });
    expect(refactor(root, '--apply', 'retarget', '--file', 'src/models.ts', '--symbol', 'AcmeModel', '--target', 'Model').code).toBe(0);
    expect(read(root, 'src/use.ts')).toBe("import { Model } from './models';\n\nexport const m: Model = new Model();\n");
    expect(read(root, 'src/models.ts')).toBe(models);
  });

  it('accepts a target imported from another module', () => {
    const compat = "import { Model } from './core';\n\n/** @deprecated */\nexport const AcmeModel = Model;\n";
    const use = "import { AcmeModel } from './compat';\n\nexport const a = new AcmeModel();\n";
    const root = tsProject({ 'src/core.ts': 'export class Model {}\n', 'src/compat.ts': compat, 'src/use.ts': use });
    const result = refactor(root, '--apply', 'retarget', '--file', 'src/compat.ts', '--symbol', 'AcmeModel', '--target', 'Model');
    expect([result.code, result.err]).toEqual([0, '']);
    expect(read(root, 'src/compat.ts')).toBe(compat);
    expect(read(root, 'src/use.ts')).toBe("import { Model } from './core';\n\nexport const a = new Model();\n");
  });

  it('refuses a member alias whose target is in another class', () => {
    const store = 'export class Store {\n  saveModel(m: string): void {\n    console.log(m);\n  }\n}\n\n';
    const root = tsProject({ 'src/engine.ts': store + ENGINE, 'src/use.ts': ENGINE_USE });
    const before = files(root);
    const result = refactor(root, '--apply', 'retarget', '--file', 'src/engine.ts', '--symbol', 'Engine.save', '--target', 'Store.saveModel');
    expect(result).toEqual({ code: 2, out: '', err: `${message('refactor.retarget-scope', { target: 'Store.saveModel', alias: 'Engine.save' })}\n` });
    expect(files(root)).toEqual(before);
  });

  it('refuses an alias a subclass overrides, naming each override', () => {
    const engine = `${ENGINE}\nexport class Fast extends Engine {\n  override save(m: string): void {\n    console.log(m);\n  }\n}\n`;
    const root = tsProject({ 'src/engine.ts': engine, 'src/use.ts': ENGINE_USE });
    const before = files(root);
    const result = refactor(root, '--apply', 'retarget', '--file', 'src/engine.ts', '--symbol', 'Engine.save', '--target', 'Engine.saveModel');
    const override = message('refactor.retarget-override', { path: 'src/engine.ts', line: 13, cls: 'Fast', name: 'save' });
    expect(result).toEqual({ code: 1, out: '', err: `${override}\n` });
    expect(files(root)).toEqual(before);
  });

  it('refuses a use where the target name is bound to something else', () => {
    const use = "import { AcmeModel } from './models';\n\nexport function f(): object {\n  const Model = 1;\n  return [Model, new AcmeModel()];\n}\n";
    const root = tsProject({ 'src/models.ts': MODELS, 'src/use.ts': use });
    const result = refactor(root, '--apply', 'retarget', '--file', 'src/models.ts', '--symbol', 'AcmeModel', '--target', 'Model');
    const shadowed = message('refactor.retarget-shadowed', { path: 'src/use.ts', line: 5, name: 'Model' });
    expect(result).toEqual({ code: 1, out: '', err: `${shadowed}\n` });
    expect(read(root, 'src/use.ts')).toBe(use);
  });

  it('a retarget entry writes the new name another entry gives its target', () => {
    const root = tsProject({
      'src/engine.ts': ENGINE,
      'src/use.ts': ENGINE_USE,
      'map.yaml': mapYaml([
        { file: 'src/engine.ts', symbol: 'Engine.saveModel', new_name: 'persistModel' },
        { file: 'src/engine.ts', symbol: 'Engine.save', retarget: 'Engine.saveModel' },
      ]),
    });
    const result = refactor(root, '--apply', 'rename-map', 'map.yaml');
    expect(result.code).toBe(0);
    expect(result.out.split('\n').slice(0, 2)).toEqual([renameHeader('saveModel', 'persistModel'), header('save', 'persistModel')]);
    expect(read(root, 'src/use.ts')).toContain("engine.persistModel('m')");
    expect(read(root, 'src/engine.ts')).toBe(ENGINE.replace('saveModel(m: string)', 'persistModel(m: string)').replace('this.saveModel(m)', 'this.persistModel(m)'));
  });

  it.each([false, true])('retarget equals its one-entry map (apply %s)', (apply) => {
    const viaCommand = tsProject({ 'src/engine.ts': ENGINE, 'src/use.ts': ENGINE_USE });
    const viaMap = copyProject(viaCommand);
    writeFileSync(join(viaMap, 'map.yaml'), mapYaml([{ file: 'src/engine.ts', symbol: 'Engine.save', retarget: 'Engine.saveModel' }]));
    const flag = apply ? ['--apply'] : [];
    const direct = refactor(viaCommand, ...flag, 'retarget', '--file', 'src/engine.ts', '--symbol', 'Engine.save', '--target', 'Engine.saveModel');
    expect(direct.code).toBe(0);
    expect(refactor(viaMap, ...flag, 'rename-map', 'map.yaml')).toEqual(direct);
  });
});

const CORE = 'export class Facade {}\n\nexport class Part {}\n\nexport function helper(): number {\n  return 1;\n}\n';
const COMPAT = "import { Facade, Part } from './core';\n\nexport const CONST = 1;\n/** @deprecated */\nexport const Flight = Facade;\n/** @deprecated */\nexport type Flight = Facade;\n/** @deprecated */\nexport const OldPart = Part;\n";
const retargetFlight = (root: string): ReturnType<typeof refactor> =>
  refactor(root, '--apply', 'retarget', '--file', 'src/compat.ts', '--symbol', 'Flight', '--target', 'Facade');

describe('retarget import planner', () => {
  it.each([
    [
      'joins an earlier home import',
      "import { helper } from './core';\nimport { CONST, Flight } from './compat';\n\nexport const x = [CONST, new Flight(), helper()];\n",
      "import { helper, Facade } from './core';\nimport { CONST } from './compat';\n\nexport const x = [CONST, new Facade(), helper()];\n",
    ],
    ['replaces a sole-name import', "import { Flight } from './compat';\n\nexport const x = new Flight();\n", "import { Facade } from './core';\n\nexport const x = new Facade();\n"],
    [
      'adds a statement after a multi-name import',
      "import { CONST, Flight } from './compat';\n\nexport const x = [CONST, new Flight()];\n",
      "import { CONST } from './compat';\nimport { Facade } from './core';\n\nexport const x = [CONST, new Facade()];\n",
    ],
    ['keeps as Z', "import { Flight as Z } from './compat';\n\nexport const x = new Z();\n", "import { Facade as Z } from './core';\n\nexport const x = new Z();\n"],
    [
      'edits name spans only',
      "import {\n  Flight, // the alias\n} from './compat';\n\nexport const x = new Flight();\n",
      "import {\n  Facade, // the alias\n} from './core';\n\nexport const x = new Facade();\n",
    ],
    [
      'keeps the import attributes of the statement it edits',
      "import { Flight } from './compat' with { kind: 'legacy' };\n\nexport const x = new Flight();\n",
      "import { Facade } from './core' with { kind: 'legacy' };\n\nexport const x = new Facade();\n",
    ],
    [
      'gives a new statement no comment or attribute',
      "import { CONST, Flight } from './compat' with { kind: 'legacy' }; // keep\n\nexport const x = [CONST, new Flight()];\n",
      "import { CONST } from './compat' with { kind: 'legacy' }; // keep\nimport { Facade } from './core';\n\nexport const x = [CONST, new Facade()];\n",
    ],
    [
      'imports type-only for type uses only',
      "import { Flight } from './compat';\n\nexport function f(x: Flight): void {\n  console.log(x);\n}\n",
      "import type { Facade } from './core';\n\nexport function f(x: Facade): void {\n  console.log(x);\n}\n",
    ],
    [
      'adds a type-only statement for type uses only',
      "import { CONST, Flight } from './compat';\n\nexport const c = CONST;\nexport let f: Flight | undefined;\n",
      "import { CONST } from './compat';\nimport type { Facade } from './core';\n\nexport const c = CONST;\nexport let f: Facade | undefined;\n",
    ],
  ])('places the target import: %s', (_kind, use, expected) => {
    const root = tsProject({ 'src/core.ts': CORE, 'src/compat.ts': COMPAT, 'src/use.ts': use });
    expect([retargetFlight(root).code, read(root, 'src/use.ts')]).toEqual([0, expected]);
    expect(read(root, 'src/compat.ts')).toBe(COMPAT);
    expect(diagnosticCodes(root)).toEqual([]);
  });

  it('spells a relative specifier from the importing file, in its extension style', () => {
    const importers: Record<string, [string, string]> = {
      'src/a.ts': ['./compat', './lib/core'],
      'src/lib/b.ts': ['../compat', './core'],
      'src/lib/deep/c.ts': ['../../compat.js', '../core.js'],
      'src/other/d.ts': ['../compat', '../lib/core'],
    };
    const body = (specifier: string): string => `import { CONST, Flight } from '${specifier}';\n\nexport const x = [CONST, new Flight()];\n`;
    const root = tsProject({
      'src/lib/core.ts': CORE,
      'src/compat.ts': COMPAT.replace("'./core'", "'./lib/core'"),
      ...Object.fromEntries(Object.entries(importers).map(([rel, [specifier]]) => [rel, body(specifier)])),
    });
    expect(retargetFlight(root).code).toBe(0);
    for (const [rel, [specifier, home]] of Object.entries(importers)) {
      expect(read(root, rel)).toBe(`import { CONST } from '${specifier}';\nimport { Facade } from '${home}';\n\nexport const x = [CONST, new Facade()];\n`);
    }
    expect(diagnosticCodes(root)).toEqual([]);
  });

  it('names a bare package home as the alias module spells it', () => {
    const root = tsProject({
      'node_modules/facade-lib/package.json': '{"name": "facade-lib", "types": "index.d.ts"}\n',
      'node_modules/facade-lib/index.d.ts': 'export declare class Facade {}\n',
      'src/compat.ts': "import { Facade } from 'facade-lib';\n\nexport const CONST = 1;\n/** @deprecated */\nexport const Flight = Facade;\n",
      'src/use.ts': "import { CONST, Flight } from './compat';\n\nexport const x = [CONST, new Flight()];\n",
    });
    expect(retargetFlight(root).code).toBe(0);
    expect(read(root, 'src/use.ts')).toBe("import { CONST } from './compat';\nimport { Facade } from 'facade-lib';\n\nexport const x = [CONST, new Facade()];\n");
    expect(diagnosticCodes(root)).toEqual([]);
  });

  it.each([
    [
      'under its exported name',
      { 'src/core.ts': 'export class CoreModel {}\n', 'src/compat.ts': "import { CoreModel as Model } from './core';\n\nexport const AcmeModel = Model;\n" },
      "import { CoreModel as Model } from './core';\n\nexport const x = new Model();\n",
    ],
    [
      'not chased along a re-export chain',
      {
        'src/private.ts': 'export class Model {}\n',
        'src/public.ts': "export { Model } from './private';\n",
        'src/compat.ts': "import { Model } from './public';\n\nexport const AcmeModel = Model;\n",
      },
      "import { Model } from './public';\n\nexport const x = new Model();\n",
    ],
  ])('imports the target from the home the alias module imports it from (%s)', (_kind, home, expected) => {
    const root = tsProject({ ...home, 'src/use.ts': "import { AcmeModel } from './compat';\n\nexport const x = new AcmeModel();\n" });
    const result = refactor(root, '--apply', 'retarget', '--file', 'src/compat.ts', '--symbol', 'AcmeModel', '--target', 'Model');
    expect([result.code, read(root, 'src/use.ts')]).toEqual([0, expected]);
    expect(diagnosticCodes(root)).toEqual([]);
  });

  it('gives a block one import per home across map entries', () => {
    const root = tsProject({
      'src/core.ts': CORE,
      'src/compat.ts': COMPAT,
      'src/use.ts': "import { CONST, Flight, OldPart } from './compat';\n\nexport const x = [CONST, new Flight(), new OldPart()];\n",
      'map.yaml': mapYaml([
        { file: 'src/compat.ts', symbol: 'Flight', retarget: 'Facade' },
        { file: 'src/compat.ts', symbol: 'OldPart', retarget: 'Part' },
      ]),
    });
    expect(refactor(root, '--apply', 'rename-map', 'map.yaml').code).toBe(0);
    expect(read(root, 'src/use.ts')).toBe("import { CONST } from './compat';\nimport { Facade, Part } from './core';\n\nexport const x = [CONST, new Facade(), new Part()];\n");
    expect(diagnosticCodes(root)).toEqual([]);
  });

  it('adds no import for a use in a re-export shim whose import binds the target', () => {
    const shim = "import { modern, legacy } from './api';\n\nexport { modern, legacy };\n\nexport function make(): number {\n  return legacy();\n}\n";
    const root = tsProject({ 'src/api.ts': API, 'src/shim.ts': shim });
    expect(refactor(root, '--apply', 'retarget', '--file', 'src/api.ts', '--symbol', 'legacy', '--target', 'modern').code).toBe(0);
    expect(read(root, 'src/shim.ts')).toBe(shim.replace('return legacy()', 'return modern()'));
    expect(diagnosticCodes(root)).toEqual([]);
  });

  it('removes a later import of the target in the block', () => {
    const use = "import { CONST, Flight } from './compat';\nimport { Facade } from './core';\n\nexport const x = [CONST, new Flight(), new Facade()];\n";
    const root = tsProject({ 'src/core.ts': CORE, 'src/compat.ts': COMPAT, 'src/use.ts': use });
    expect(retargetFlight(root).code).toBe(0);
    expect(read(root, 'src/use.ts')).toBe("import { CONST } from './compat';\nimport { Facade } from './core';\n\nexport const x = [CONST, new Facade(), new Facade()];\n");
    expect(diagnosticCodes(root)).toEqual([]);
  });

  it('refuses a namespace member through a module that does not export the target', () => {
    const use = "import * as c from './shim';\n\nexport const x = new c.AcmeModel();\n";
    const root = tsProject({ 'src/models.ts': MODELS, 'src/shim.ts': "export { AcmeModel } from './models';\n", 'src/use.ts': use });
    const result = refactor(root, '--apply', 'retarget', '--file', 'src/models.ts', '--symbol', 'AcmeModel', '--target', 'Model');
    const unbound = message('refactor.retarget-unbound', { path: 'src/use.ts', line: 3, module: 'src/shim.ts', name: 'Model' });
    expect(result).toEqual({ code: 1, out: '', err: `${unbound}\n` });
    expect(read(root, 'src/use.ts')).toBe(use);
  });
});
