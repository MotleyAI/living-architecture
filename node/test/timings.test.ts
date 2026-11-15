// `dr-refactor --timings`: exclusive phase times from an injected nanosecond clock, printed in the shared order.
import { describe, expect, it } from 'vitest';
import { message, timingPhases } from '../src/contract/index.js';
import { seconds, Timer } from '../src/refactor/timings.js';

const SECOND = 1_000_000_000n;

class Clock {
  now = 0n;
  readonly read = (): bigint => this.now;
}

const line = (phase: string, value: string): string => message('refactor.timing', { phase, seconds: value });

describe('timings', () => {
  it('lists the shared phases', () => {
    expect(timingPhases()).toEqual(['load', 'resolve', 'references', 'rules', 'blindspot-scan', 'literal-scan', 'literal-probe', 'baseline', 'write']);
  });

  it.each([
    [1_239_000_000n, '1.23'],
    [4_000_000n, '0.00'],
    [-5n, '0.00'],
    [0n, '0.00'],
    [9_999_999n, '0.00'],
    [10_000_000n, '0.01'],
    [123_450_000_001n, '123.45'],
  ])('floors %s ns to %s', (ns, shown) => {
    expect(seconds(ns)).toBe(shown);
  });

  it('subtracts a nested phase from its parent', () => {
    const clock = new Clock();
    const timer = new Timer(clock.read);
    timer.phase('rules', () => {
      clock.now += SECOND;
      timer.phase('blindspot-scan', () => {
        clock.now += 2n * SECOND;
      });
      clock.now += 3n * SECOND;
    });
    expect(timer.lines()).toEqual([line('rules', '4.00'), line('blindspot-scan', '2.00'), line('total', '6.00')]);
  });

  it('adds up repeated runs', () => {
    const clock = new Clock();
    const timer = new Timer(clock.read);
    for (const step of [1_000_000_000n, 239_000_000n]) {
      timer.phase('references', () => {
        clock.now += step;
      });
      clock.now += SECOND;
    }
    expect(timer.lines()).toEqual([line('references', '1.23'), line('total', '3.23')]);
  });

  it('prints in list order, omits unrun phases, total last', () => {
    const clock = new Clock();
    const timer = new Timer(clock.read);
    for (const phase of ['write', 'literal-probe', 'load']) {
      timer.phase(phase, () => {
        clock.now += 4_000_000n;
      });
    }
    expect(timer.lines()).toEqual([line('load', '0.00'), line('literal-probe', '0.00'), line('write', '0.00'), line('total', '0.01')]);
  });

  it('prints only total when no phase ran', () => {
    const clock = new Clock();
    const timer = new Timer(clock.read);
    clock.now += 1_239_000_000n;
    expect(timer.lines()).toEqual([line('total', '1.23')]);
  });

  it('times a phase left by an exception', () => {
    const clock = new Clock();
    const timer = new Timer(clock.read);
    const boom = new Error('boom');
    const body = (): never => {
      clock.now += SECOND;
      throw boom;
    };
    expect(() => timer.phase('baseline', body)).toThrow('boom');
    expect(timer.lines()).toEqual([line('baseline', '1.00'), line('total', '1.00')]);
  });

  it('returns the phase body result', () => {
    const timer = new Timer(new Clock().read);
    expect(timer.phase('load', () => 42)).toBe(42);
  });
});
