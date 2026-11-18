export class Query {
  rootModel(): string {
    return "q";
  }
}

export class Plan {
  rootModel(): string {
    return "p";
  }
}

export class Fake {
  rootModel(): string {
    return "f";
  }
}

export function read(f: Fake): string {
  return f.rootModel();
}
