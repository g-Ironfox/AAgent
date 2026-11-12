import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { workflowCanvasSvg as workspaceCanvasSvg } from '../webui_py/static/workflow_canvas.mjs';
import { NODE_TYPES } from '../workflow_editor/static/workflow/domain/node-contract.js';
import { workflowCanvasSvg } from './static/workflow_canvas.mjs';

test('Map input ports render in mapping order rather than connection order', () => {
  const svg = workflowCanvasSvg({
    name: 'map_port_order',
    input_ports: [],
    output_ports: [],
    nodes: [
      { id: 'input', type: 'input', x: 0, y: 0 },
      {
        id: 'map', type: 'construct_map_content', name: 'Map', x: 400, y: 0,
        arguments: { mappings: [
          { key: 'first', value_source: 'port', port_id: 'map-value-in-0' },
          { key: 'second', value_source: 'port', port_id: 'map-value-in-1' },
        ] },
      },
    ],
    connections: [
      { fromId: 'input', fromPortId: 'control-out', toId: 'map', toPortId: 'control-in', type: 'control' },
      { fromId: 'input', fromPortId: 'value-second', toId: 'map', toPortId: 'map-value-in-1', type: 'content' },
      { fromId: 'input', fromPortId: 'value-first', toId: 'map', toPortId: 'map-value-in-0', type: 'content' },
    ],
  });
  const mapInputLabels = [...svg.matchAll(/<text x="10" y="\d+"[^>]*>([^<]+)<\/text>/g)]
    .map((match) => match[1]);
  assert.deepEqual(mapInputLabels, ['control-in', 'map-value-in-0', 'map-value-in-1']);
});

test('Workflow-local Struct connections use declared colors and node accents stay fixed', () => {
  const svg = workflowCanvasSvg({
    name: 'struct_colors',
    metadata: { structs: [{ id: 'profile', name: 'Profile', color: '#3A7D68', fields: [] }] },
    input_ports: [],
    output_ports: [],
    nodes: [
      { id: 'make', type: 'construct_struct', name: 'Profile', x: 0, y: 0, arguments: { struct_id: 'profile' } },
      { id: 'serialize', type: 'struct_to_json', name: 'Serialize', x: 300, y: 0, arguments: { value_type: 'struct:profile' } },
    ],
    connections: [
      { fromId: 'make', fromPortId: 'struct-out', toId: 'serialize', toPortId: 'value-in', type: 'struct:profile' },
    ],
  });
  assert.match(svg, /stroke="#3A7D68"/);
  assert.match(svg, /fill="#326b4b"/);
  assert.doesNotMatch(svg, /<rect width="190" height="4" fill="#3A7D68"/);
});

test('Struct and Struct-list connections use independent colors with legacy fallback', () => {
  const workflow = {
    name: 'typed_colors', metadata: { structs: [{ id: 'profile', name: 'Profile', color: '#3A7D68', list_color: '#3976A8', fields: [] }] },
    nodes: [
      { id: 'struct', type: 'construct_struct', name: 'Profile' },
      { id: 'list', type: 'construct_list', name: 'Profiles' },
    ],
    connections: [
      { id: 'one', fromId: 'struct', fromPortId: 'struct-out', toId: 'list', toPortId: 'struct:profile-in-0', type: 'struct:profile' },
      { id: 'two', fromId: 'list', fromPortId: 'list-out', toId: 'struct', toPortId: 'struct-in', type: 'list-struct:profile' },
    ],
  };
  const svg = workflowCanvasSvg(workflow);
  assert.match(svg, /stroke="#3A7D68"/);
  assert.match(svg, /stroke="#3976A8"/);

  delete workflow.metadata.structs[0].list_color;
  assert.equal((workflowCanvasSvg(workflow).match(/stroke="#3A7D68"/g) || []).length, 2);
});

test('All supported node types have a specific thumbnail accent', () => {
  const expectedColors = {
    construct_event: '#147d78',
    deserialize_json: '#61568a',
    map_content_get: '#326b4b',
    publish_event: '#b8483d',
    session_create: '#187b70',
    session_read: '#28749c',
    session_write: '#ab6740',
  };
  for (const [type, color] of Object.entries(expectedColors)) {
    const svg = workflowCanvasSvg({ nodes: [{ id: type, type, x: 0, y: 0 }], connections: [] });
    assert.match(svg, new RegExp(`<rect width="190" height="4" fill="${color}"/>`), type);
  }
});

test('Built-in control and data connection colors match the workflow editor', () => {
  const types = ['control', 'content', 'message', 'event', 'map-content', 'list-content', 'list-message', 'list-event'];
  const svg = workflowCanvasSvg({
    nodes: [{ id: 'source', type: 'input', x: 0, y: 0 }, { id: 'target', type: 'output', x: 300, y: 0 }],
    connections: types.map((type, index) => ({
      id: String(index), fromId: 'source', fromPortId: `out-${index}`,
      toId: 'target', toPortId: `in-${index}`, type,
    })),
  });
  const colors = [...svg.matchAll(/<path d="[^"]+" fill="none" stroke="([^"]+)"/g)]
    .map((match) => match[1])
    .filter((color) => color !== '#dfe4df');
  assert.deepEqual(colors, ['#13775a', '#356e9b', '#b75b18', '#147d78', '#46713f', '#d12f72', '#7a3e88', '#147d78']);
});

// Compare both SVG renderers with the editor's actual CSS to catch style drift.
const editorCss = readFileSync(new URL('../workflow_editor/static/css/workflow/canvas.css', import.meta.url), 'utf8');
const editorVariables = Object.fromEntries([...readFileSync(new URL('../workflow_editor/static/css/base.css', import.meta.url), 'utf8')
  .matchAll(/(--[\w-]+):([^;{}]+)/g)].map((match) => [match[1], match[2].trim()]));

function editorDeclarations(selector) {
  const rule = [...editorCss.matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .find((match) => match[1].split(',').some((item) => item.trim() === selector));
  return Object.fromEntries((rule?.[2] || '').split(';').filter((item) => item.includes(':')).map((item) => {
    const colon = item.indexOf(':');
    return [item.slice(0, colon).trim(), item.slice(colon + 1).trim()];
  }));
}

function editorColor(value) {
  return value.replace(/var\((--[\w-]+)(?:,([^()]+))?\)/g, (_, name, fallback) => editorVariables[name] || fallback);
}

for (const [surface, render] of [['manager', workflowCanvasSvg], ['workspace', workspaceCanvasSvg]]) {
  test(`${surface}: all node accents match the editor CSS`, () => {
    const defaultAccent = editorDeclarations('.flow-node')['border-top'].split(' ').at(-1);
    for (const type of NODE_TYPES) {
      const expected = editorColor(editorDeclarations(`.flow-node.${type}`)['border-top-color'] || defaultAccent);
      const svg = render({ nodes: [{ id: type, type }], connections: [] });
      const accent = svg.match(/<rect width="190" height="4" fill="([^"]+)"/)[1];
      assert.equal(accent, expected, type);
    }
  });

  test(`${surface}: connection colors, port colors and dash patterns match the editor CSS`, () => {
    const types = ['control', 'content', 'message', 'event', 'map-content', 'list-content', 'list-message', 'list-event', 'struct:missing', 'list-struct:missing'];
    for (const type of types) {
      const declarations = {
        ...editorDeclarations('.connection-path'),
        ...editorDeclarations(type.includes('struct:') ? '.connection-path[class*="struct:"]' : `.connection-path.${type}`),
      };
      const svg = render({
        nodes: [{ id: 'source', type: 'input' }, { id: 'target', type: 'output', x: 300 }],
        connections: [{ fromId: 'source', fromPortId: 'out', toId: 'target', toPortId: 'in', type }],
      });
      const edge = [...svg.matchAll(/<path d="[^"]+" fill="none" stroke="([^"]+)" stroke-width="2"([^>]*)\/>/g)];
      assert.equal(edge.length, 1, type);
      const expectedColor = editorColor(declarations.stroke);
      assert.equal(edge[0][1], expectedColor, type);
      const dash = edge[0][2].match(/stroke-dasharray="([^"]+)"/)?.[1] || null;
      assert.equal(dash, declarations['stroke-dasharray'] || null, type);
      const ports = [...svg.matchAll(/<circle[^>]+fill="([^"]+)"/g)].map((match) => match[1]);
      assert.deepEqual(ports, [expectedColor, expectedColor], type);
    }
  });
}
