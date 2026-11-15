const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../dashboard.js'), 'utf8');
const context = vm.createContext({escapeHTML: String, time: String, day: String});
vm.runInContext(source.slice(source.indexOf('const metricNumber'), source.indexOf('function renderDetail()')), context);
function chart(axis, points) {
  return context.storedMetricChart({label:'Test metric', unit:'bpm', axis, points});
}
test('phase lines connect consecutive points and break across missing phases', () => {
  const html = chart('mission_phase', [1, 2, 4].map(n => ({phase_index:n, mission_phase:`TP${n}`, value:70+n})));
  assert.equal((html.match(/<polyline /g) || []).length, 2);
  assert.equal((html.match(/<circle /g) || []).length, 3);
  assert.ok(!html.includes('NaN'));
});
test('timestamp points have equal observation spacing and flat values stay finite', () => {
  const html = chart('timestamp', [0, 1, 10].map(n => ({measured_at:new Date(n*1000).toISOString(), value:70})));
  assert.match(html, /cx="260"/);
  assert.equal((html.match(/<polyline /g) || []).length, 1);
  assert.ok(!html.includes('NaN'));
});
test('timestamps use YYYYMMDD HH:mm:ss in UTC', () => {
  vm.runInContext(source.slice(source.indexOf('const never ='), source.indexOf('const statusLabel')), context);
  assert.equal(vm.runInContext("time('2026-11-15T14:03:09+02:00')", context), '20261115 12:03:09');
});
test('one metric panel combines sources without displaying source or dataset headers', () => {
  vm.runInContext('const storedTrendAxis = new Map(); const storedTrendCache = new Map();', context);
  context.sample = {series:[
    {metric:'hr_bpm', label:'Heart Rate', unit:'bpm', source:'cardioresp', axis:'timestamp', points:[{id:1,value:70,measured_at:'2026-11-15T10:00:00Z'}]},
    {metric:'hr_bpm', label:'Heart Rate', unit:'bpm', source:'shared_demo', axis:'timestamp', points:[{id:2,value:72,measured_at:'2026-11-15T11:00:00Z'}]},
    {metric:'hr_bpm', label:'Heart Rate', unit:'bpm', source:'biologist_csv', axis:'mission_phase', dataset_id:'secret-dataset', points:[{id:3,value:94,phase_index:1,mission_phase:'Baseline'}]}
  ]};
  vm.runInContext("storedTrendCache.set('A-01',{data:sample})", context);
  const html = context.storedTrends('A-01');
  assert.equal((html.match(/class="vital-trend stored-metric"/g) || []).length, 1);
  assert.ok(html.includes('Recorded time') && html.includes('Mission phases'));
  assert.ok(!html.includes('biologist_csv') && !html.includes('secret-dataset') && !html.includes('shared_demo'));
  assert.ok(html.includes('20261115 10:00:00'));
});
test('an explicit metric warning produces the yellow Check required state', () => {
  const ui = vm.createContext({});
  vm.runInContext(source.slice(source.indexOf('function alertSeverity'), source.indexOf('// Line icons')), ui);
  const data = {crew:[{id:'A-02', status:'alert', metrics:[]}], alerts:[{crew_id:'A-02', metric:'heart_rate', severity:'warning'}]};
  ui.classify(data);
  assert.equal(data.crew[0].display, 'warning');
  assert.equal(data.alerts[0].severity, 'warning');
});
