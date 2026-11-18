import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import vm from 'node:vm';
import { editWorkflowMetadata, parseWorkflowFile, validateWorkflowMetadata } from './static/workflow-file.mjs';
import { workflowCanvasFilename, workflowCanvasSvg } from './static/workflow_canvas.mjs';

const clone = (value) => JSON.parse(JSON.stringify(value));
const workflow = () => ({
  schema_version: '2.0', name: 'parent', description: 'description', version: 3,
  input_ports: [{ name: 'question', type: 'content' }], output_ports: [],
  subprocess_workflow_files: [
    { name: 'child-a', input_ports: [{ name: 'question', type: 'content' }], output_ports: [], extra: 'keep' },
    { name: 'child-b', input_ports: [], output_ports: [] },
  ],
  remote_tools: [{ name: 'remote', input_ports: [], output_ports: [{ name: 'answer', type: 'content' }] }],
  metadata: { structs: [{ id: 'profile', name: 'Profile', color: '#3A7D68', fields: [] }] },
  nodes: [
    { id: 'in', name: 'Input', type: 'input', x: 0, y: 0 },
    { id: 'a', name: 'A', type: "spawn_and_wait_subprocess", x: 250, y: 0, arguments: { workflow_file: 'child-a', keep: 1 } },
    { id: 'b', type: "spawn_and_wait_subprocess", arguments: { workflow_file: 'child-b' } },
    { id: 'other', type: 'local_tool', arguments: { workflow_file: 'child-a' } },
  ],
  connections: [{ fromId: 'in', fromPortId: 'control-out', toId: 'a', toPortId: 'control-in', type: 'control' }],
  custom: { preserved: true },
});
const file = (id, content = JSON.stringify(workflow())) => ({
  file_id: id, name: id + '.json', content, revision: 4, updated_at: '2026-11-10T10:00:00Z',
});

test('detect workflow content independently of filename and reject unrelated/malformed JSON', () => {
  for (const schema_version of ['1.1', '1.2', '1.3', '1.4', '1.5', '1.6', '1.7', '2.0']) {
    assert.equal(parseWorkflowFile(JSON.stringify({ ...workflow(), schema_version })).schema_version, schema_version);
  }
  for (const content of ['notes', '{}', '[]', 'null', '{broken', JSON.stringify({ name: 'workflow.json' }),
    JSON.stringify({ ...workflow(), nodes: [null] }),
    JSON.stringify({ ...workflow(), description: { invalid: true } }),
    JSON.stringify({ ...workflow(), input_ports: [null] }),
    JSON.stringify({ ...workflow(), subprocess_workflow_files: [null] }),
  ]) assert.equal(parseWorkflowFile(content), null);
});

test('dependency swaps update only Workflow references and preserve contracts, metadata and node settings', () => {
  const source = workflow();
  const before = clone(source);
  const updated = editWorkflowMetadata(source, { name: 'renamed', description: 'new', subprocessFiles: ['child-b', 'child-a'] });
  assert.equal(updated.nodes[1].arguments.workflow_file, 'child-b');
  assert.equal(updated.nodes[2].arguments.workflow_file, 'child-a');
  assert.equal(updated.nodes[3].arguments.workflow_file, 'child-a');
  assert.equal(updated.nodes[1].arguments.keep, 1);
  for (const key of ['input_ports', 'output_ports', 'connections', 'metadata', 'remote_tools', 'custom']) {
    assert.deepEqual(updated[key], source[key]);
  }
  assert.deepEqual(updated.subprocess_workflow_files[0].input_ports, source.subprocess_workflow_files[0].input_ports);
  assert.equal(updated.subprocess_workflow_files[0].extra, 'keep');
  assert.deepEqual(source, before);
});

test('legacy dependency keys and absent optional fields survive edits', () => {
  const source = { ...workflow(), subprocess_workflow_files: [{ workflow_name: 'child-a' }] };
  delete source.description;
  const updated = editWorkflowMetadata(source, { name: source.name, description: '', subprocessFiles: ['new-child'] });
  assert.deepEqual(updated.subprocess_workflow_files, [{ name: 'new-child' }]);
  assert.equal('description' in updated, false);
  assert.equal(updated.nodes[1].arguments.workflow_file, 'new-child');
});

test('metadata rejects empty names and duplicate dependency names', () => {
  assert.throws(() => validateWorkflowMetadata({ ...workflow(), name: '  ' }), /名称不能为空/);
  assert.throws(() => validateWorkflowMetadata({ ...workflow(), subprocess_workflow_files: [{ name: ' ' }] }), /文件名不能为空/);
  assert.throws(() => validateWorkflowMetadata({ ...workflow(), subprocess_workflow_files: [{ name: 'same' }, { name: 'same' }] }), /不能重复/);
});

test('standalone WebUI canvas stays identical to the Manager renderer', async () => {
  assert.equal(await readFile(new URL('./static/workflow_canvas.mjs', import.meta.url), 'utf8'),
    await readFile(new URL('../manager_webui/static/workflow_canvas.mjs', import.meta.url), 'utf8'));
  const svg = workflowCanvasSvg({ ...workflow(), name: '<script>alert(1)</script>' });
  assert.ok(!svg.includes('<script>'));
  assert.ok(svg.includes('&lt;script&gt;'));
  assert.match(svg, /stroke="#13775a"/);
});

class Element {
  constructor(tag = '') {
    this.tag = tag; this.children = []; this.listeners = {}; this.attributes = {};
    this.value = ''; this.textContent = ''; this.disabled = false; this.hidden = false;
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = []; this.append(...children); }
  addEventListener(type, handler) { (this.listeners[type] ||= []).push(handler); }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  getAttribute(key) { return this.attributes[key]; }
  querySelectorAll(selector) { return selector === 'style' ? (this.styles || []) : []; }
  remove() { this.removed = true; }
  focus() {}
  select() {}
  click() { this.clicked = true; }
}
const source = (await Promise.all(['workspace-workflow.js', 'workspace.js'].map((name) =>
  readFile(new URL('./static/' + name, import.meta.url), 'utf8'))))
  .map((text) => text.replace(/^import[\s\S]+?;\r?\n/gm, '').replace('export function createWorkflowPanel', 'function createWorkflowPanel'))
  .join('\n');
const markup = await readFile(new URL('./static/workspace.html', import.meta.url), 'utf8');
const htmlIds = new Set([...markup.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1]));

async function harness(items = [file('flow')]) {
  const elements = new Map([...htmlIds].map((id) => [id, new Element()]));
  const documentListeners = {};
  const downloads = [];
  const blobs = [];
  const calls = [];
  const stored = new Map(items.map((item) => [item.file_id, clone(item)]));
  const settings = { confirm: true, saveError: null, restoreItems: null };
  const document = {
    getElementById: (id) => elements.get(id) || null,
    createElement(tag) { const item = new Element(tag); if (tag === 'a') downloads.push(item); return item; },
    importNode: (node) => node,
    addEventListener(type, handler) { documentListeners[type] = handler; },
  };
  const context = vm.createContext({
    document, window: { confirm: () => settings.confirm, prompt: () => '1' },
    DOMParser: class {
      parseFromString(svgMarkup) {
        const svg = new Element('svg'); svg.nodeName = 'svg'; svg.markup = svgMarkup;
        svg.setAttribute('viewBox', /viewBox="([^"]+)"/.exec(svgMarkup)[1]);
        svg.styles = [new Element('style')]; return { documentElement: svg };
      }
    },
    URL: { createObjectURL: (blob) => { blobs.push(blob); return 'blob:test'; }, revokeObjectURL() {} }, Blob,
    parseWorkflowFile, editWorkflowMetadata, validateWorkflowMetadata, workflowCanvasFilename, workflowCanvasSvg,
    fetchFiles: async () => ({ items: [...stored.values()].map(clone) }),
    fetchFile: async (id) => clone(stored.get(id)),
    updateFile: async (id, name, content, revision) => {
      calls.push({ id, name, content, revision });
      if (settings.saveError) throw new Error(settings.saveError);
      const saved = { ...stored.get(id), name, content, revision: revision + 1 };
      stored.set(id, saved); return clone(saved);
    },
    createFile: async (name) => { const created = { ...file('new', ''), name }; stored.set('new', created); return created; },
    createCheckpoint: async () => ({}), fetchCheckpoints: async () => ({ items: [{ seq: 1, data: { name: 'checkpoint' } }] }),
    restoreCheckpoint: async () => {
      stored.clear(); settings.restoreItems.forEach((item) => stored.set(item.file_id, clone(item)));
      return { data: { checkpoint_seq: 1 } };
    },
    updateFilePin: async (id, pinned) => ({ ...stored.get(id), pinned }),
    deleteFile: async (id) => { stored.delete(id); },
  });
  vm.runInContext(source, context);
  await new Promise(setImmediate);
  const get = (id) => elements.get(id);
  const fire = async (target, type = 'click', payload = {}) => {
    const element = typeof target === 'string' ? get(target) : target;
    for (const handler of element.listeners[type] || []) await handler(payload);
    await new Promise(setImmediate);
  };
  const input = async (target, value) => {
    const element = typeof target === 'string' ? get(target) : target;
    element.value = value; await fire(element, 'input');
  };
  const dependency = (index) => get('subprocessWorkflowFiles').children[index].children[0].children[0].children[1];
  return { get, fire, input, dependency, settings, calls, stored, downloads, blobs, documentListeners };
}

test('view switching preserves exact text, renders ports and strips inline SVG styles for CSP', async () => {
  const content = JSON.stringify(workflow(), null, 4) + '\n';
  const h = await harness([file('flow', content)]);
  assert.equal(h.get('workflowButton').hidden, false);
  assert.equal(h.get('workflowPanel').hidden, true);
  await h.fire('workflowButton');
  assert.equal(h.get('workflowPanel').hidden, false);
  assert.equal(h.get('filePreview').hidden, true);
  assert.equal(h.get('workflowName').disabled, true);
  assert.equal(h.get('workflowCanvasMeta').textContent, '4 节点 / 1 连接');
  assert.equal(h.get('inputPorts').children[0].children[0].textContent, 'question');
  assert.equal(h.get('remoteToolCount').textContent, '1 项');
  const svg = h.get('workflowCanvasPreview').children[0];
  assert.equal(svg.nodeName, 'svg');
  assert.ok(svg.styles.every((style) => style.removed));
  await h.fire('workflowButton');
  assert.equal(h.get('fileContent').value, content);
  assert.equal(h.calls.length, 0);
});

test('metadata edits round-trip through raw JSON and save using the file revision', async () => {
  const h = await harness();
  await h.fire('workflowButton'); await h.fire('editButton');
  await h.input('workflowName', 'new-parent');
  await h.input('workflowDescription', 'new description');
  await h.input(h.dependency(0), 'new-child');
  await h.fire('workflowButton');
  const draft = JSON.parse(h.get('fileContent').value);
  assert.equal(draft.nodes[1].arguments.workflow_file, 'new-child');
  await h.input('fileContent', JSON.stringify({ ...draft, description: 'raw edit' }));
  await h.fire('workflowButton');
  assert.equal(h.get('workflowDescription').value, 'raw edit');
  await h.fire('editButton');
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0].revision, 4);
  assert.equal(h.calls[0].name, 'flow.json');
  const saved = JSON.parse(h.stored.get('flow').content);
  assert.equal(saved.name, 'new-parent'); assert.equal(saved.description, 'raw edit');
  assert.deepEqual(saved.metadata, workflow().metadata);
  assert.equal(h.get('workflowName').disabled, true);
  assert.equal(h.get('cancelButton').hidden, true);
});

test('cancel restores metadata and the exact original JSON; reverting all fields stays clean', async () => {
  const content = JSON.stringify(workflow(), null, 4) + '\n';
  const h = await harness([file('flow', content)]);
  await h.fire('workflowButton'); await h.fire('editButton');
  await h.input('workflowName', 'changed'); await h.input('workflowName', 'parent');
  assert.equal(h.get('fileContent').value, content);
  assert.equal(h.get('editButton').disabled, true);
  await h.input(h.dependency(0), 'new-child'); await h.fire('cancelButton');
  assert.equal(h.get('fileContent').value, content);
  assert.equal(h.get('workflowName').value, 'parent');
  assert.equal(h.dependency(0).value, 'child-a');
  assert.equal(h.calls.length, 0);
});

test('validation and revision conflict keep the draft and editor available', async () => {
  const h = await harness();
  await h.fire('workflowButton'); await h.fire('editButton');
  await h.input('workflowName', ' '); await h.fire('editButton');
  assert.equal(h.calls.length, 0); assert.match(h.get('saveStatus').textContent, /名称不能为空/);
  await h.input('workflowName', 'renamed'); await h.input(h.dependency(0), 'child-b'); await h.fire('editButton');
  assert.equal(h.calls.length, 0); assert.match(h.get('saveStatus').textContent, /不能重复/);
  await h.input(h.dependency(0), 'new-child');
  h.settings.saveError = 'revision conflict'; await h.fire('editButton');
  assert.equal(h.get('workflowName').value, 'renamed');
  assert.equal(h.dependency(0).value, 'new-child');
  assert.equal(h.get('workflowName').disabled, false);
  assert.match(h.get('saveStatus').textContent, /revision conflict/);
  h.settings.saveError = null; await h.fire('editButton');
  assert.equal(h.stored.get('flow').revision, 5);
});

test('invalid JSON and ordinary files hide the toggle, and dirty-file selection can be declined', async () => {
  const h = await harness([file('flow'), file('notes', 'plain text')]);
  await h.fire('workflowButton'); await h.fire('editButton'); await h.input('workflowName', 'draft');
  h.settings.confirm = false; await h.fire(h.get('fileList').children[1]);
  assert.equal(h.get('workflowName').value, 'draft');
  h.settings.confirm = true; await h.fire(h.get('fileList').children[1]);
  assert.equal(h.get('workflowPanel').hidden, true); assert.equal(h.get('workflowButton').hidden, true);
  await h.fire('editButton'); await h.input('fileContent', JSON.stringify(workflow()));
  assert.equal(h.get('workflowButton').hidden, false);
  await h.input('fileContent', '{broken'); assert.equal(h.get('workflowButton').hidden, true);
});

test('checkpoint restoration and deletion do not leave stale workflow metadata visible', async () => {
  const h = await harness(); await h.fire('workflowButton');
  h.settings.restoreItems = [file('flow', 'restored notes')];
  await h.fire('restoreButton');
  assert.equal(h.get('workflowPanel').hidden, true);
  assert.equal(h.get('workflowButton').hidden, true);
  assert.equal(h.get('filePreview').textContent, 'restored notes');
  await h.fire('deleteButton'); assert.equal(h.get('fileEmpty').hidden, false);
});

test('downloads workflow JSON and canvas SVG without changing the saved document', async () => {
  const h = await harness(); await h.fire('workflowButton');
  await h.fire('canvasExportButton'); await h.fire('downloadButton');
  assert.match(h.downloads[0].download, /-canvas\.svg$/);
  assert.equal(h.blobs[0].type, 'image/svg+xml;charset=utf-8');
  assert.equal(h.downloads[1].download, 'flow.json');
  assert.equal(h.blobs[1].type, 'application/json;charset=utf-8');
  assert.equal(h.calls.length, 0);
});


test('Ctrl+S saves metadata and filename together without changing the Workflow name implicitly', async () => {
  const h = await harness(); await h.fire('workflowButton'); await h.fire('editButton');
  await h.input('workflowDescription', 'keyboard save'); await h.input('fileName', 'renamed-file.json');
  let prevented = false;
  h.documentListeners.keydown({ ctrlKey: true, key: 's', preventDefault() { prevented = true; } });
  await new Promise(setImmediate);
  assert.equal(prevented, true);
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0].name, 'renamed-file.json');
  assert.equal(JSON.parse(h.calls[0].content).name, 'parent');
  assert.equal(JSON.parse(h.calls[0].content).description, 'keyboard save');
});

test('removing the last workflow and creating an empty file clear the visual editor', async () => {
  const h = await harness(); await h.fire('workflowButton'); await h.fire('deleteButton');
  assert.equal(h.get('workflowPanel').hidden, true);
  assert.equal(h.get('workflowButton').hidden, true);
  assert.equal(h.get('fileEmpty').hidden, false);
  await h.fire('createButton');
  assert.equal(h.get('workflowButton').hidden, true);
  assert.equal(h.get('fileContent').hidden, false);
  assert.equal(h.get('fileContent').value, '');
});
