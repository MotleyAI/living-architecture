// The diagrams-fresh check's read of index.yaml: a duplicate key is a reason, never a raise.
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, describe, expect, it } from 'vitest';
import { diagramsMap } from '../src/c4/diagrams.js';

describe('diagramsMap', () => {
  const root = mkdtempSync(join(tmpdir(), 'la-diagrams-map-'));
  afterAll(() => rmSync(root, { recursive: true, force: true }));

  it('reports a duplicate key with the c4 wording', () => {
    mkdirSync(join(root, 'architecture'));
    writeFileSync(join(root, 'architecture', 'index.yaml'), 'diagrams: {}\ndiagrams: {}\n');
    expect(diagramsMap(root)).toBe("index.yaml is not valid YAML: duplicate key 'diagrams' at lines 1 and 2");
  });
});
