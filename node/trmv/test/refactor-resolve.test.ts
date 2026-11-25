// trmv-refactor's resolve and checks phases search no references: a run refused in checks made no rename search.
import type * as TS from 'typescript';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { refactorRaw, tsProject } from './refactor-project.js';

const searches = vi.hoisted(() => ({ count: 0 }));

vi.mock('../src/lang/ts.js', async (importOriginal) => {
  const original = await importOriginal<typeof import('../src/lang/ts.js')>();
  let counting: typeof TS | undefined;
  return {
    ts(): typeof TS {
      const real = original.ts();
      counting ??= Object.create(real, {
        createLanguageService: {
          value: (...args: Parameters<typeof real.createLanguageService>): TS.LanguageService => {
            const service = real.createLanguageService(...args);
            const find = service.findRenameLocations;
            service.findRenameLocations = ((...call: unknown[]): readonly TS.RenameLocation[] | undefined => {
              searches.count += 1;
              return Reflect.apply(find, service, call) as readonly TS.RenameLocation[] | undefined;
            }) as typeof find;
            return service;
          },
        },
      }) as typeof TS;
      return counting;
    },
  };
});

afterEach(() => {
  searches.count = 0;
});

describe('trmv-refactor resolve', () => {
  it('resolves a re-export retarget without a reference search', () => {
    const root = tsProject({
      'src/core.ts': 'export class Model {}\n',
      'src/compat.ts': "export { Model as AcmeModel } from './core';\n",
      'src/use.ts': "import { AcmeModel } from './compat';\n\nexport const x = new AcmeModel();\n",
    });
    const result = refactorRaw(root, 'retarget', '--file', 'src/compat.ts', '--symbol', 'AcmeModel', '--target', 'Model', '--keep', 'src/gone.ts');
    expect(result.code).toBe(2);
    expect(searches.count).toBe(0);
  });

  it('resolves a string literal member rename without a reference search', () => {
    const root = tsProject({ 'src/kind.ts': "export type Kind = 'load' | 'save';\n\nexport const k: Kind = 'load';\n" });
    const result = refactorRaw(root, 'rename', '--file', 'src/kind.ts', '--line', '1', '--col', '21', '--new-name', 'fetch', '--keep', 'src/gone.ts');
    expect(result.code).toBe(2);
    expect(searches.count).toBe(0);
  });
});
