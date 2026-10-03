// Schema validation (JSON Schema 2020-12) with jsonschema-style messages, and default materialization.
import { Ajv2020, type ErrorObject, type ValidateFunction } from 'ajv/dist/2020.js';
import { canonicalRepr, toPlain } from './values.js';

const compiled = new Map<string, ValidateFunction>();

function validator(schema: object): ValidateFunction {
  const key = JSON.stringify(schema);
  let fn = compiled.get(key);
  if (fn === undefined) {
    fn = new Ajv2020({ allErrors: true, strict: false }).compile(schema);
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

/** Sorted `key.path: message` lines, one per violation; empty when valid. */
export function validate(schema: object, data: unknown): string[] {
  const fn = validator(schema);
  if (fn(toPlain(data))) return [];
  return (fn.errors ?? [])
    .filter(reported)
    .map((error) => {
      const path = error.instancePath.split('/').slice(1).map((p) => p.replaceAll('~1', '/').replaceAll('~0', '~')).join('.');
      return path ? `${path}: ${describe(error)}` : describe(error);
    })
    .sort();
}

function hasDefaults(schema: any): boolean {
  return Object.values(schema?.properties ?? {}).some((sub: any) => 'default' in sub || hasDefaults(sub));
}

function fill(schema: any, value: any): any {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return value;
  const out: Record<string, any> = { ...value };
  for (const [key, sub] of Object.entries<any>(schema?.properties ?? {})) {
    if (key in out) out[key] = fill(sub, out[key]);
    else if ('default' in sub) out[key] = structuredClone(sub.default);
    else if (hasDefaults(sub)) out[key] = fill(sub, {});
  }
  return out;
}

/** `data` (null = missing document) with schema defaults filled in; explicit values are kept. */
export function materializeDefaults(schema: object, data: unknown): any {
  return fill(schema, data === null ? {} : toPlain(data));
}
