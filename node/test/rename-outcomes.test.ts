// Every branch of every TypeScript rename rule ends in an outcome: rewrite, blind spot, leftover or unrelated.
import type * as TS from 'typescript';
import { describe, expect, it } from 'vitest';
import { ts } from '../src/lang/index.js';
import { type FormCall, walk } from '../src/refactor/members.js';
import { blindspotOutcome, formCallOutcome, literalOutcomes, mentionOutcome } from '../src/refactor/outcomes.js';

const OLD = 'saveModel';
const source = (text: string) => ts().createSourceFile('a.ts', text, ts().ScriptTarget.Latest, true);

function formCall(text: string): FormCall {
  const file = source(text);
  const call = [...walk(file)].find((n) => ts().isCallExpression(n)) as TS.CallExpression;
  const literal = call.arguments[1] as TS.StringLiteral;
  const start = literal.getStart(file) + 1;
  return { call, start, end: start + OLD.length, object: call.arguments[0] as TS.Expression };
}

describe('formCallOutcome', () => {
  const found = formCall("vi.spyOn(engine, 'saveModel');\n");
  for (const [renamed, kind] of [
    [[], 'unrelated'],
    [[false], 'unrelated'],
    [[true, true], 'rewrite'],
    [[true, false], 'blindspot'],
  ] as [boolean[], string][]) {
    it(`${JSON.stringify(renamed)} → ${kind}`, () => {
      const outcome = formCallOutcome('a.ts', found, renamed, 'engine', OLD, 'storeModel');
      expect([outcome.kind, outcome.start, outcome.end]).toEqual([kind, found.start, found.end]);
      expect(outcome.edits.map((e) => e.newText)).toEqual(kind === 'rewrite' ? ['storeModel'] : []);
      expect(outcome.finding?.template).toBe(kind === 'blindspot' ? 'refactor.mixed-target' : undefined);
    });
  }
});

describe('blindspotOutcome', () => {
  it('spans a string form literal, or the access position', () => {
    expect(blindspotOutcome('a.ts', 7, [10, 19], 'o', OLD)).toMatchObject({ kind: 'blindspot', start: 10, end: 19 });
    expect(blindspotOutcome('a.ts', 7, null, 'o', OLD)).toMatchObject({ kind: 'blindspot', start: 7, end: 7 });
  });
});

describe('mentionOutcome', () => {
  const mention = { start: 3, end: 12, where: 'comment' as const, opens: false };
  it('rewrites or lists', () => {
    expect(mentionOutcome('a.ts', mention, true, OLD, 'storeModel')).toMatchObject({ kind: 'rewrite', edits: [{ start: 3, length: 9 }] });
    expect(mentionOutcome('a.ts', mention, false, OLD, 'storeModel')).toMatchObject({ kind: 'leftover', finding: { template: 'refactor.leftover' } });
  });
});

describe('literalOutcomes', () => {
  it('lists whole-value string and plain template literals no rule examined', () => {
    const text = [
      "const a = get('saveModel');",
      "const b = 'saveModel is slow';",
      'const c = `saveModel`;',
      'const d = `${x}saveModel`;',
      "const e = spy(o, 'saveModel');",
      'const f = "saveModel";',
      '',
    ].join('\n');
    const handled = text.indexOf("'saveModel');\n", text.indexOf('spy'));
    const outcomes = literalOutcomes('a.ts', source(text), OLD, (start, end) => start <= handled && handled < end);
    expect(outcomes.map((o) => [o.kind, text.slice(o.start, o.end)])).toEqual([
      ['leftover', "'saveModel'"],
      ['leftover', '`saveModel`'],
      ['leftover', '"saveModel"'],
    ]);
    expect(outcomes.every((o) => o.finding?.values.where === 'string')).toBe(true);
  });
});
