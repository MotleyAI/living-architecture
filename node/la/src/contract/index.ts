// la's shared contract, loaded from its vendored snapshot, over trmv's contract library; an id la's registry lacks
// renders from trmv's.
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  Snapshot,
  contractHash as trmvContractHash,
  materializeDefaults as trmvMaterializeDefaults,
  message as trmvMessage,
  renderTemplate,
  schemaOrdered as trmvSchemaOrdered,
  validate as trmvValidate,
} from 'type-rename-move/contract';
import type { Identity } from 'type-rename-move/twin';
import { VERSION } from '../index.js';

export * from 'type-rename-move/contract';

export const LA = new Snapshot(join(dirname(fileURLToPath(import.meta.url)), 'data'));

export function snapshotDir(): string {
  return LA.root;
}

/** The hash recorded when la's snapshot was vendored. */
export function contractHash(): string {
  return LA.contractHash();
}

export function schema(name: string): Record<string, any> {
  return LA.schema(name);
}

/** Every la schema's name, as `schema` takes it. */
export function schemaNames(): string[] {
  return LA.schemaNames();
}

export function findings(): Record<string, string> {
  return LA.findings();
}

export function checkIds(): string[] {
  return LA.yaml('findings.yaml').check_ids;
}

export function manifest(): Record<string, any> {
  return LA.manifest();
}

export function conventions(): Record<string, any> {
  return LA.yaml('conventions.yaml');
}

export function architecture(): Record<string, any> {
  return LA.yaml('architecture.yaml');
}

/** la's committed config file, relative to the repo root. */
export function configFile(): string {
  return LA.yaml('config.yaml').file;
}

/** One contributor's git-ignored overrides of it. */
export function localConfigFile(): string {
  return LA.yaml('config.yaml').local_file;
}

/** A stealth-mode path in la's stealth directory: `plans_dir`, `waiver_ledger` or `openspec_store`. */
export function stealthPath(key: string): string {
  return LA.yaml('config.yaml')[key];
}

/** la's stealth path registry, and the prefix whose paths count when the repo tracks none under it. */
export function stealthRegistry(): [string[], string] {
  const config = LA.yaml('config.yaml');
  return [[...config.stealth_registry], config.stealth_registry_prefix];
}

/** The core and the waivable leak tokens of the list. */
export function leakTokenGroups(): [string[], string[]] {
  const tokens = LA.yaml('vectors/stealth-leaks.yaml');
  return [[...tokens.core], [...tokens.waivable]];
}

export function scriptPath(name: string): string {
  return LA.scriptPath(name);
}

/** The finding `id` rendered from la's registry, else from trmv's. */
export function message(id: string, values: Record<string, unknown> = {}): string {
  const template = findings()[id];
  return template === undefined ? trmvMessage(id, values) : renderTemplate(template, values);
}

/** `data` against an la schema, whose `$ref`s into trmv's schemas resolve. */
export function validate(schema: Record<string, any>, data: unknown): string[] {
  return trmvValidate(schema, data, [LA]);
}

/** `data` with an la schema's defaults filled in, following its `$ref`s into trmv's schemas. */
export function materializeDefaults(schema: Record<string, any>, data: unknown): any {
  return trmvMaterializeDefaults(schema, data, [LA]);
}

/** `value` in an la schema's property order, following its `$ref`s into trmv's schemas. */
export function schemaOrdered(schema: Record<string, any>, value: unknown): any {
  return trmvSchemaOrdered(schema, value, [LA]);
}

/** la's twin identity: its doctor, version, la's contract hash and the trmv hash of the trmv library it runs with. */
export function identity(): Identity {
  const cli = LA.yaml('cli.yaml');
  return { package: cli.package, doctor: cli.doctor, version: VERSION, hashes: [contractHash(), trmvContractHash()], contract: LA };
}
