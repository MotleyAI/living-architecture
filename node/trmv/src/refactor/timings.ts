// `trmv-refactor --timings`: each phase's exclusive wall time, printed in the shared phase order.
import { message, timingPhases } from '../contract/index.js';

const CENTISECOND_NS = 10_000_000n;

/** `ns` floored to whole centiseconds, never negative, as `S.CC`. */
export function seconds(ns: bigint): string {
  const cs = (ns > 0n ? ns : 0n) / CENTISECOND_NS;
  return `${cs / 100n}.${String(cs % 100n).padStart(2, '0')}`;
}

/** A stack of phases: entering one pauses the one below it, leaving it resumes that one. */
export class Timer {
  private readonly start: bigint;
  private readonly spent = new Map<string, bigint>();
  private readonly stack: string[] = [];
  private since: bigint;

  constructor(private readonly clock: () => bigint = process.hrtime.bigint) {
    this.start = clock();
    this.since = this.start;
  }

  private charge(): void {
    const now = this.clock();
    const top = this.stack.at(-1);
    if (top !== undefined) this.spent.set(top, (this.spent.get(top) ?? 0n) + now - this.since);
    this.since = now;
  }

  phase<T>(name: string, body: () => T): T {
    this.charge();
    this.stack.push(name);
    if (!this.spent.has(name)) this.spent.set(name, 0n);
    try {
      return body();
    } finally {
      this.charge();
      this.stack.pop();
    }
  }

  /** One `refactor.timing` line per phase that ran, in list order, then `total`. */
  lines(): string[] {
    const ran: [string, bigint][] = timingPhases().flatMap((p): [string, bigint][] => {
      const ns = this.spent.get(p);
      return ns === undefined ? [] : [[p, ns]];
    });
    ran.push(['total', this.clock() - this.start]);
    return ran.map(([phase, ns]) => message('refactor.timing', { phase, seconds: seconds(ns) }));
  }
}

const active: Timer[] = [];

/** `body`, timed as `name` on the active timer; untimed without one. */
export function timed<T>(name: string, body: () => T): T {
  const timer = active.at(-1);
  return timer === undefined ? body() : timer.phase(name, body);
}

/** The scope of a `--timings` run; `cancel` when another twin's run prints its own lines. */
export class Report {
  cancelled = false;

  cancel(): void {
    this.cancelled = true;
  }
}

/** `body`; with `enabled`, timed, its lines printed on stderr after all other output, however it exits. */
export function report<T>(enabled: boolean, body: (scope: Report) => T): T {
  const scope = new Report();
  if (!enabled) return body(scope);
  const timer = new Timer();
  active.push(timer);
  try {
    return body(scope);
  } finally {
    active.splice(active.indexOf(timer), 1);
    if (!scope.cancelled) process.stderr.write(`${timer.lines().join('\n')}\n`);
  }
}
