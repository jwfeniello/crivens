// Validate every .glb under a directory; print totals and any files with errors/warnings.
const v = require('gltf-validator'); const fs = require('fs'); const path = require('path');
function walk(d) { return fs.readdirSync(d, {withFileTypes: true}).flatMap(e => e.isDirectory() ? walk(path.join(d, e.name)) : e.name.endsWith('.glb') ? [path.join(d, e.name)] : []); }
(async () => {
  const files = walk(process.argv[2]); let bad = 0; const codes = {};
  for (const f of files) {
    const r = await v.validateBytes(new Uint8Array(fs.readFileSync(f)), {maxIssues: 10});
    if (r.issues.numErrors || r.issues.numWarnings) {
      bad++; for (const m of r.issues.messages.filter(m => m.severity <= 1)) codes[m.code] = (codes[m.code] || 0) + 1;
      if (bad <= 5) console.log(path.basename(f), r.issues.numErrors, 'err', r.issues.numWarnings, 'warn', r.issues.messages[0].code, r.issues.messages[0].message);
    }
  }
  console.log('validated', files.length, 'files;', bad, 'with errors/warnings', JSON.stringify(codes));
})();
