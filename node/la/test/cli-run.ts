// Run an la or dr command through its package's dispatcher in a temp repo, capturing its exit code and streams.
import { run as runWith, type Run } from '../../dr/test/cli-run.js';
import { dispatch as drDispatch } from '../../dr/src/cli/index.js';
import { dispatch } from '../src/cli/index.js';

export { type Run, tempRepo } from '../../dr/test/cli-run.js';

export function run(root: string, command: string, argv: string[]): Run {
  return runWith(root, command, argv, command.startsWith('dr-') ? drDispatch : dispatch);
}
