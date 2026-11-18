import { jest as j } from '@jest/globals';

const factory = (): { get: () => number } => ({ get: () => 2 });

j.mock<typeof import('../src/api')>('../src/api', factory);
j.doMock('../src/api.js', factory);
j.unstable_mockModule('../src/api.js', factory);
j.unmock('../src/api');
j.doUnmock('../src/api');
j.dontMock('../src/api');
j.setMock('../src/api', {});
j.requireActual('../src/api');
j.requireMock('../src/api');
j.createMockFromModule('../src/api');
