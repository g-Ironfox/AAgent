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
