function load() {
  return require('fs'); // ALLOW(import-not-top): lazy load breaks a cycle
}
