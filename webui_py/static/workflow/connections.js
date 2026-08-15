import { state } from './model.js';

export function createConnectionController(elements, markChanged) {
  let connectionSequence = 0;

  function createConnectionId() {
    connectionSequence += 1;
    return `connection-${Date.now()}-${connectionSequence}`;
  }

  function portCenter(nodeId, portId) {
    const nodeElement = Array.from(elements.nodeLayer.querySelectorAll('[data-node-id]'))
      .find((element) => element.dataset.nodeId === nodeId);
    const port = Array.from(nodeElement?.querySelectorAll('[data-port-id]') || [])
      .find((element) => element.dataset.portId === portId);
    if (!port) return null;
    const canvasRect = elements.canvas.getBoundingClientRect();
    const rect = port.getBoundingClientRect();
    return {
      x: rect.left + rect.width / 2 - canvasRect.left + elements.canvas.scrollLeft,
      y: rect.top + rect.height / 2 - canvasRect.top + elements.canvas.scrollTop,
    };
  }

  function connectionPath(start, end) {
    const direction = end.x >= start.x ? 1 : -1;
    const curve = Math.max(42, Math.abs(end.x - start.x) * 0.45);
    return `M ${start.x} ${start.y} C ${start.x + curve * direction} ${start.y}, ${end.x - curve * direction} ${end.y}, ${end.x} ${end.y}`;
  }

  function compatiblePort(port, drag) {
    const targetDirection = drag.targetDirection || (drag.direction === 'output' ? 'input' : 'output');
    if (!port || port.dataset.portType !== drag.type || port.dataset.portDirection !== targetDirection) return false;
    if (port.dataset.nodeId === drag.anchorNodeId) return false;
    return true;
  }

  function setCompatiblePorts(drag) {
    for (const port of elements.nodeLayer.querySelectorAll('.node-port')) {
      port.classList.toggle('compatible', compatiblePort(port, drag));
    }
  }

  function finishConnectionDrag(event, cancelled = false) {
    const drag = state.connectionDrag;
    if (!drag || event.pointerId !== drag.pointerId) return;
    if (cancelled) {
      if (drag.connection && !state.connections.includes(drag.connection)) state.connections.push(drag.connection);
      for (const port of elements.nodeLayer.querySelectorAll('.node-port')) port.classList.remove('compatible');
      if (event.currentTarget?.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
      state.connectionDrag = null;
      renderConnections();
      return;
    }
    const target = document.elementFromPoint(event.clientX, event.clientY)?.closest('.node-port');
    const connection = drag.connection || state.connections.find((item) => item.id === drag.connectionId);
    if (compatiblePort(target, drag)) {
      const targetIsInput = target.dataset.portDirection === 'input';
      const targetIsSingleOutput = target.dataset.portDirection === 'output' && target.dataset.portMultiple !== 'true';
      state.connections = state.connections.filter((item) => {
        const occupiesTargetInput = targetIsInput && item.toId === target.dataset.nodeId && item.toPortId === target.dataset.portId;
        const occupiesTargetOutput = targetIsSingleOutput && item.fromId === target.dataset.nodeId && item.fromPortId === target.dataset.portId;
        return !(item.type === drag.type && (occupiesTargetInput || occupiesTargetOutput));
      });
      if (drag.type === 'content' && drag.direction === 'input' && connection) {
        connection.toId = target.dataset.nodeId;
        connection.toPortId = target.dataset.portId;
        state.connections.push(connection);
      } else if (drag.type === 'control' && connection) {
        if (drag.direction === 'output') {
          connection.fromId = target.dataset.nodeId;
          connection.fromPortId = target.dataset.portId;
        } else {
          connection.toId = target.dataset.nodeId;
          connection.toPortId = target.dataset.portId;
        }
        state.connections.push(connection);
      } else {
        const from = drag.anchorDirection === 'output'
          ? { id: drag.anchorNodeId, portId: drag.anchorPortId }
          : { id: target.dataset.nodeId, portId: target.dataset.portId };
        const to = drag.anchorDirection === 'output'
          ? { id: target.dataset.nodeId, portId: target.dataset.portId }
          : { id: drag.anchorNodeId, portId: drag.anchorPortId };
        state.connections.push({ id: createConnectionId(), fromId: from.id, fromPortId: from.portId, toId: to.id, toPortId: to.portId, type: drag.type });
      }
      markChanged();
    } else if (target) {
      if (drag.connection) state.connections.push(drag.connection);
    } else if (drag.connectionId) {
      state.connections = state.connections.filter((item) => item.id !== drag.connectionId);
      markChanged();
    }
    for (const port of elements.nodeLayer.querySelectorAll('.node-port')) port.classList.remove('compatible');
    if (event.currentTarget?.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    state.connectionDrag = null;
    renderConnections();
  }

  function bindConnectionPort(port, node) {
    port.dataset.nodeId = node.id;
    port.addEventListener('click', (event) => event.stopPropagation());
    port.addEventListener('pointerdown', (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      event.stopPropagation();
      const direction = port.dataset.portDirection;
      const type = port.dataset.portType;
      const incoming = direction === 'input'
        ? state.connections.find((connection) => connection.toId === node.id && connection.toPortId === port.dataset.portId && connection.type === type)
        : null;
      const outgoing = direction === 'output'
        ? state.connections.filter((connection) => connection.fromId === node.id && connection.fromPortId === port.dataset.portId && connection.type === type)
        : [];
      const connectionId = type === 'control'
        ? incoming?.id || (outgoing.length === 1 ? outgoing[0].id : null)
        : incoming?.id || null;
      const connection = connectionId
        ? incoming || outgoing.find((item) => item.id === connectionId)
        : null;
      if (connection) {
        state.connections = state.connections.filter((item) => item.id !== connection.id);
      }
      const hasContentInputConnection = type === 'content' && direction === 'input' && connection;
      const hasControlConnection = type === 'control' && connection;
      const anchorNodeId = hasContentInputConnection || (hasControlConnection && direction === 'input')
        ? connection.fromId
        : hasControlConnection && direction === 'output'
          ? connection.toId
          : node.id;
      const anchorPortId = hasContentInputConnection || (hasControlConnection && direction === 'input')
        ? connection.fromPortId
        : hasControlConnection && direction === 'output'
          ? connection.toPortId
          : (port.dataset.portId || null);
      const anchorDirection = hasContentInputConnection || (hasControlConnection && direction === 'input') ? 'output' : direction === 'output' ? 'input' : direction;
      state.connectionDrag = {
        pointerId: event.pointerId,
        direction,
        targetDirection: connection && type === 'content' && direction === 'input'
          ? 'input'
          : hasControlConnection
            ? direction
            : null,
        type,
        anchorNodeId,
        anchorPortId,
        anchorDirection,
        connectionId,
        connection,
        pointer: { x: event.clientX, y: event.clientY },
      };
      port.setPointerCapture(event.pointerId);
      setCompatiblePorts(state.connectionDrag);
      renderConnections();
    });
    port.addEventListener('pointermove', (event) => {
      if (!state.connectionDrag || event.pointerId !== state.connectionDrag.pointerId) return;
      state.connectionDrag.pointer = { x: event.clientX, y: event.clientY };
      renderConnections();
    });
    port.addEventListener('pointerup', finishConnectionDrag);
    port.addEventListener('pointercancel', (event) => finishConnectionDrag(event, true));
  }

  function bindNodeDrag(element, node) {
    let drag = null;

    element.addEventListener('pointerdown', (event) => {
      if (event.button !== 0) return;
      drag = { pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, nodeX: node.x, nodeY: node.y, moved: false };
      element.setPointerCapture(event.pointerId);
      element.classList.add('dragging');
    });

    element.addEventListener('pointermove', (event) => {
      if (!drag || event.pointerId !== drag.pointerId) return;
      const deltaX = event.clientX - drag.startX;
      const deltaY = event.clientY - drag.startY;
      if (!drag.moved && Math.hypot(deltaX, deltaY) < 3) return;
      drag.moved = true;
      const maxX = Math.max(12, elements.nodeLayer.scrollWidth - element.offsetWidth - 12);
      const maxY = Math.max(12, elements.nodeLayer.scrollHeight - element.offsetHeight - 12);
      node.x = Math.min(maxX, Math.max(12, drag.nodeX + deltaX));
      node.y = Math.min(maxY, Math.max(12, drag.nodeY + deltaY));
      element.style.left = `${node.x}px`;
      element.style.top = `${node.y}px`;
      renderConnections();
    });

    function finishDrag(event) {
      if (!drag || event.pointerId !== drag.pointerId) return;
      if (drag.moved) markChanged();
      element.classList.remove('dragging');
      if (element.hasPointerCapture(event.pointerId)) element.releasePointerCapture(event.pointerId);
      drag = null;
    }

    element.addEventListener('pointerup', finishDrag);
    element.addEventListener('pointercancel', finishDrag);
  }

  function renderConnections() {
    const canvasRect = elements.canvas.getBoundingClientRect();
    const width = Math.max(elements.nodeLayer.scrollWidth, elements.canvas.clientWidth);
    const height = Math.max(elements.nodeLayer.scrollHeight, elements.canvas.clientHeight);
    elements.connectionLayer.setAttribute('viewBox', `0 0 ${width} ${height}`);
    elements.connectionLayer.setAttribute('width', String(width));
    elements.connectionLayer.setAttribute('height', String(height));
    const fragment = document.createDocumentFragment();
    for (const connection of state.connections) {
      const start = portCenter(connection.fromId, connection.fromPortId);
      const end = portCenter(connection.toId, connection.toPortId);
      if (!start || !end) continue;
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('class', `connection-path${connection.type === 'content' ? ' content' : ''}`);
      path.setAttribute('d', connectionPath(start, end));
      fragment.append(path);
    }
    if (state.connectionDrag) {
      const drag = state.connectionDrag;
      const canvasPoint = {
        x: drag.pointer.x - canvasRect.left + elements.canvas.scrollLeft,
        y: drag.pointer.y - canvasRect.top + elements.canvas.scrollTop,
      };
      const anchor = portCenter(drag.anchorNodeId, drag.anchorPortId);
      if (anchor) {
        const preview = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        preview.setAttribute('class', `connection-path preview${drag.type === 'content' ? ' content' : ''}`);
        preview.setAttribute('d', drag.anchorDirection === 'output' ? connectionPath(anchor, canvasPoint) : connectionPath(canvasPoint, anchor));
        fragment.append(preview);
      }
    }
    elements.connectionLayer.replaceChildren(fragment);
    elements.connectionCount.textContent = `${state.connections.length} 条连接`;
  }

  return { bindConnectionPort, bindNodeDrag, renderConnections };
}