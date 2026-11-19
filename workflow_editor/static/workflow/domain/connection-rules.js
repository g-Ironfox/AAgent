import { createWorkflowId, portsForNode } from './node-contract.js';

function endpointPort(node, portId, direction, type) {
  return portsForNode(node).find((port) => (
    port.id === portId
    && port.direction === direction
    && port.type === type
  ));
}

export function isValidConnection(connection, nodes) {
  if (!connection || typeof connection.id !== 'string' || !connection.id.trim()) return false;
  if (!['control', 'content', 'number', 'map-content', 'list-content'].includes(connection.type)
    && !/^(struct|list-struct):[A-Za-z_][A-Za-z0-9_]*$/.test(connection.type || '')) return false;
  const source = nodes.find((node) => node.id === connection.fromId);
  const target = nodes.find((node) => node.id === connection.toId);
  if (!source || !target) return false;
  return Boolean(
    endpointPort(source, connection.fromPortId, 'output', connection.type)
    && endpointPort(target, connection.toPortId, 'input', connection.type),
  );
}

export function filterValidConnections(connections, nodes) {
  const candidates = Array.isArray(connections) ? connections : [];
  const reservedIds = new Set(candidates
    .map((connection) => connection?.id)
    .filter((id) => typeof id === 'string' && id.trim()));
  const usedIds = new Set();
  const valid = [];

  for (const connection of candidates) {
    if (!connection || typeof connection !== 'object' || Array.isArray(connection)) continue;
    let normalized = connection;
    if (typeof connection.id !== 'string' || !connection.id.trim() || usedIds.has(connection.id)) {
      let id;
      do {
        id = createWorkflowId('connection');
      } while (reservedIds.has(id) || usedIds.has(id));
      normalized = { ...connection, id };
    }
    if (!isValidConnection(normalized, nodes)) continue;
    usedIds.add(normalized.id);
    reservedIds.add(normalized.id);
    valid.push(normalized);
  }

  return valid;
}

export function reconcileConnections(state) {
  state.connections = filterValidConnections(state.connections, state.nodes);
}
