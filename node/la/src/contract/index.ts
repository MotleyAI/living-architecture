// la's shared contract, loaded from its vendored snapshot, over dr's contract library; an id la's registry lacks
// renders from dr's.
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  Snapshot,
  contractHash as drContractHash,
  materializeDefaults as drMaterializeDefaults,
  message as drMessage,
  renderTemplate,
  schemaOrdered as drSchemaOrdered,
  validate as drValidate,
} from 'deterministic-refactor/contract';
import type { Identity } from 'deterministic-refactor/twin';
import { VERSION } from '../index.js';

export * from 'deterministic-refactor/contract';

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

export function scriptPath(name: string): string {
  return LA.scriptPath(name);
}

/** The finding `id` rendered from la's registry, else from dr's. */
export function message(id: string, values: Record<string, unknown> = {}): string {
  const template = findings()[id];
  return template === undefined ? drMessage(id, values) : renderTemplate(template, values);
}

/** `data` against an la schema, whose `$ref`s into dr's schemas resolve. */
export function validate(schema: Record<string, any>, data: unknown): string[] {
  return drValidate(schema, data, [LA]);
}

/** `data` with an la schema's defaults filled in, following its `$ref`s into dr's schemas. */
export function materializeDefaults(schema: Record<string, any>, data: unknown): any {
  return drMaterializeDefaults(schema, data, [LA]);
}

/** `value` in an la schema's property order, following its `$ref`s into dr's schemas. */
export function schemaOrdered(schema: Record<string, any>, value: unknown): any {
  return drSchemaOrdered(schema, value, [LA]);
}

/** la's twin identity: its doctor, version, la's contract hash and the dr hash of the dr library it runs with. */
export function identity(): Identity {
  const cli = LA.yaml('cli.yaml');
  return { package: cli.package, doctor: cli.doctor, version: VERSION, hashes: [contractHash(), drContractHash()], contract: LA };
}
