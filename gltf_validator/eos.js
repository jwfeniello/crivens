// Print which image index triggers IMAGE_UNEXPECTED_EOS in each given glb.
const v = require('gltf-validator'); const fs = require('fs');
(async () => { for (const f of process.argv.slice(2)) {
  const r = await v.validateBytes(new Uint8Array(fs.readFileSync(f)), {maxIssues: 50});
  console.log(f.split(/[\/]/).pop(), r.issues.messages.filter(m => m.code === 'IMAGE_UNEXPECTED_EOS').map(m => m.pointer).join(' '));
}})();
