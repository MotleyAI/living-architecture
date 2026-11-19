export interface IntrospectedColumn {
  name: string;
}

export class Ds {
  columns: string[] = [];
}

export class Probe {
  columns: IntrospectedColumn[] = [];
}
