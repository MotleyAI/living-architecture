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

  it('refuses a target declared in another module', () => {
    const compat = "import { Model } from './core';\n\n/** @deprecated */\nexport const AcmeModel = Model;\n";
    const root = tsProject({ 'src/core.ts': 'export class Model {}\n', 'src/compat.ts': compat });
    const result = refactor(root, 'retarget', '--file', 'src/compat.ts', '--symbol', 'AcmeModel', '--target', 'Model');
    expect(result).toEqual({ code: 2, out: '', err: `${message('refactor.retarget-scope', { target: 'Model', alias: 'AcmeModel' })}\n` });
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
