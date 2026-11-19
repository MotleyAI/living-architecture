// Schema validation (JSON Schema 2020-12) with jsonschema-style messages, and default materialization.
import { Ajv2020, type ErrorObject, type ValidateFunction } from 'ajv/dist/2020.js';
import { DR, type Snapshot } from './snapshot.js';
import { canonicalRepr, toPlain } from './values.js';

const stores = new Map<string, Ajv2020>();
const compiled = new Map<string, ValidateFunction>();

const storeKey = (snapshots: Snapshot[]): string => snapshots.map((s) => s.root).join('\0');

/** Every schema of `snapshots` under its `$id`, so cross-file `$ref`s resolve. */
function schemaStore(snapshots: Snapshot[]): Ajv2020 {
  const key = storeKey(snapshots);
  let store = stores.get(key);
  if (store === undefined) {
    store = new Ajv2020({ allErrors: true, strict: false, verbose: true });
    for (const snapshot of snapshots) for (const name of snapshot.schemaNames()) store.addSchema(snapshot.schema(name));
    stores.set(key, store);
  }
  return store;
}

/** A shared schema's validator by its `$id`; any other schema compiled without its `$id`, keyed by its text. */
function validator(schema: Record<string, any>, snapshots: Snapshot[]): ValidateFunction {
  const ajv = schemaStore(snapshots);
  const shared = typeof schema.$id === 'string' ? ajv.getSchema(schema.$id) : undefined;
  if (shared?.schema === schema) return shared;
  const key = `${storeKey(snapshots)}\0${JSON.stringify(schema)}`;
  let fn = compiled.get(key);
  if (fn === undefined) {
    const anonymous = { ...schema };
    delete anonymous.$id;
    fn = ajv.compile(anonymous);
    compiled.set(key, fn);
  }
  return fn;
}

function describe(error: ErrorObject): string {
  const params = error.params as Record<string, any>;
  const data = canonicalRepr(error.data);
  switch (error.keyword) {
    case 'required':
      return `'${params.missingProperty}' is a required property`;
    case 'additionalProperties':
      return `Additional properties are not allowed ('${params.additionalProperty}' was unexpected)`;
    case 'type':
      return `${data} is not of type '${params.type}'`;
    case 'enum':
      return `${data} is not one of ${canonicalRepr(params.allowedValues)}`;
    case 'const':
      return `${canonicalRepr(params.allowedValue)} was expected`;
    case 'anyOf':
      return `${data} is not valid under any of the given schemas`;
    case 'oneOf':
      return `${data} is not valid under exactly one of the given schemas`;
    default:
      return `${data} ${error.message ?? 'is invalid'}`;
  }
}

/** Errors a combinator or conditional reports itself, not its branches' internals. */
function reported(error: ErrorObject): boolean {
  return error.keyword !== 'if' && !/\/(?:anyOf|oneOf)\/\d+\//.test(error.schemaPath);
}

/** Sorted `key.path: message` lines, one per violation; empty when valid. `extra`: other contracts' schemas. */
export function validate(schema: Record<string, any>, data: unknown, extra: Snapshot[] = []): string[] {
  const fn = validator(schema, [DR, ...extra]);
  if (fn(toPlain(data))) return [];
  return (fn.errors ?? [])
    .filter(reported)
    .map((error) => {
      const path = error.instancePath.split('/').slice(1).map((p) => p.replaceAll('~1', '/').replaceAll('~0', '~')).join('.');
      return path ? `${path}: ${describe(error)}` : describe(error);
    })
    .sort();
}

type Docs = Map<string, any>;

/** dr's schemas and `extra`'s, by `$id`. */
function documents(extra: Snapshot[]): Docs {
  const docs: Docs = new Map();
  for (const snapshot of [DR, ...extra]) {
    for (const name of snapshot.schemaNames()) {
      const doc = snapshot.schema(name);
      docs.set(String(doc.$id), doc);
    }
  }
  return docs;
}

/** `schema` with its `$ref`s followed (`<$id>#<pointer>`, or `#<pointer>` within `base`), and the `$id` it ends in. */
function deref(schema: any, base: string, docs: Docs): [any, string] {
  while (schema !== null && typeof schema === 'object' && typeof schema.$ref === 'string') {
    const [file, pointer = ''] = schema.$ref.split('#');
    base = file || base;
    let target = docs.get(base);
    for (const part of pointer.split('/').slice(1)) target = target?.[part.replaceAll('~1', '/').replaceAll('~0', '~')];
    schema = target;
  }
  return [schema, base];
}

function hasDefaults(schema: any, base: string, docs: Docs): boolean {
  return Object.values<any>(schema?.properties ?? {}).some((raw) => {
    const [sub, subBase] = deref(raw, base, docs);
    return 'default' in sub || hasDefaults(sub, subBase, docs);
  });
}

function fill(schema: any, value: any, base: string, docs: Docs): any {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return value;
  const out: Record<string, any> = { ...value };
  for (const [key, raw] of Object.entries<any>(schema?.properties ?? {})) {
    const [sub, subBase] = deref(raw, base, docs);
    if (key in out) out[key] = fill(sub, out[key], subBase, docs);
    else if ('default' in sub) out[key] = structuredClone(sub.default);
    else if (hasDefaults(sub, subBase, docs)) out[key] = fill(sub, {}, subBase, docs);
  }
  return out;
}

/**
 * `data` (null = missing document) with schema defaults filled in, following `$ref`s as inline definitions; explicit
 * values are kept. `extra`: other contracts' schemas.
 */
export function materializeDefaults(schema: Record<string, any>, data: unknown, extra: Snapshot[] = []): any {
  const docs = documents(extra);
  const [root, base] = deref(schema, String(schema.$id ?? ''), docs);
  return fill(root, data === null ? {} : toPlain(data), base, docs);
}

/** `value` with its keys in the schema's property order, following `$ref`s, as a typed config dumps it. */
export function schemaOrdered(schema: Record<string, any>, value: unknown, extra: Snapshot[] = []): any {
  const docs = documents(extra);
  const order = (raw: any, base: string, item: any): any => {
    const [sub, subBase] = deref(raw, base, docs);
    if (item === null || typeof item !== 'object' || Array.isArray(item) || sub?.properties === undefined) return item;
    return Object.fromEntries(Object.keys(sub.properties).map((key) => [key, order(sub.properties[key], subBase, item[key])]));
  };
  return order(schema, String(schema.$id ?? ''), value);
}
