import assert from 'node:assert/strict';
import { test } from 'node:test';
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
