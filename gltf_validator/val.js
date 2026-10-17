const v = require('gltf-validator'); const fs = require('fs');
const data = new Uint8Array(fs.readFileSync(process.argv[2]));
v.validateBytes(data, {maxIssues: 30}).then(r => {
  console.log('errors', r.issues.numErrors, 'warnings', r.issues.numWarnings, 'infos', r.issues.numInfos);
  for (const m of r.issues.messages.filter(m => m.severity <= 1).slice(0, 15)) console.log(m.severity, m.code, m.pointer, m.message);
}).catch(e => console.error('ERR', e));
