import { portsForNode } from './node-contract.js';

function endpointPort(node, portId, direction, type) {
  return portsForNode(node).find((port) => (
    port.id === portId
    && port.direction === direction
    && port.type === type
  ));
}

export function isValidConnection(connection, nodes) {
  if (!connection || typeof connection.id !== 'string') return false;
  if (!['control', 'content', 'message', 'list-content', 'list-message'].includes(connection.type)) return false;
  const source = nodes.find((node) => node.id === connection.fromId);
  const target = nodes.find((node) => node.id === connection.toId);
  if (!source || !target) return false;
  return Boolean(
    endpointPort(source, connection.fromPortId, 'output', connection.type)
    && endpointPort(target, connection.toPortId, 'input', connection.type),
  );
}

export function filterValidConnections(connections, nodes) {
  return (Array.isArray(connections) ? connections : []).filter((connection) => isValidConnection(connection, nodes));
}

export function reconcileConnections(state) {
  state.connections = filterValidConnections(state.connections, state.nodes);
}