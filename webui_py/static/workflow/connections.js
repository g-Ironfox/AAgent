import { state } from './model.js';

export function createConnectionController(elements, markChanged) {
  function portSelector(direction, type) {
    if (direction === 'output') return type === 'content' ? '.content-output' : '.node-port.output';
    return type === 'content' ? '.text-input' : '.node-port.input';
  }

  function portCenter(nodeId, direction, type) {
    const nodeElement = elements.nodeLayer.querySelector(`[data-node-id="${nodeId}"]`);
    const port = nodeElement?.querySelector(portSelector(direction, type));
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
    if (!port || port.dataset.portType !== drag.type || port.dataset.portDirection === drag.direction) return false;
    if (port.dataset.nodeId === drag.fixedNodeId) return false;
    return drag.direction === 'output' ? port.dataset.portDirection === 'input' : port.dataset.portDirection === 'output';
  }

  function setCompatiblePorts(drag) {
    for (const port of elements.nodeLayer.querySelectorAll('.node-port')) {
      port.classList.toggle('compatible', compatiblePort(port, drag));
    }
  }

  function finishConnectionDrag(event) {
    const drag = state.connectionDrag;
    if (!drag || event.pointerId !== drag.pointerId) return;
    const target = document.elementFromPoint(event.clientX, event.clientY)?.closest('.node-port');
    if (compatiblePort(target, drag)) {
      if (drag.direction === 'output') {
        state.connections = state.connections.filter((connection) => !(connection.toId === target.dataset.nodeId && connection.type === drag.type));
        const connection = state.connections.find((item) => item.id === drag.connectionId);
        if (connection) connection.toId = target.dataset.nodeId;
        else state.connections.push({ id: `connection-${Date.now()}`, fromId: drag.fixedNodeId, toId: target.dataset.nodeId, type: drag.type });
      } else {
        const connection = state.connections.find((item) => item.id === drag.connectionId);
        if (connection) connection.fromId = target.dataset.nodeId;
      }
      markChanged();
    }
    for (const port of elements.nodeLayer.querySelectorAll('.node-port')) port.classList.remove('compatible');
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
        ? state.connections.find((connection) => connection.toId === node.id && connection.type === type)
        : null;
      const outgoing = direction === 'output'
        ? state.connections.filter((connection) => connection.fromId === node.id && connection.type === type)
        : [];
      if (direction === 'input' && !incoming) return;
      state.connectionDrag = {
        pointerId: event.pointerId,
        direction,
        type,
        fixedNodeId: node.id,
        connectionId: incoming?.id || (outgoing.length === 1 ? outgoing[0].id : null),
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
    port.addEventListener('pointercancel', finishConnectionDrag);
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
      const start = portCenter(connection.fromId, 'output', connection.type);
      const end = portCenter(connection.toId, 'input', connection.type);
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
      const fixedDirection = drag.direction === 'output' ? 'output' : 'input';
      const fixed = portCenter(drag.fixedNodeId, fixedDirection, drag.type);
      if (fixed) {
        const preview = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        preview.setAttribute('class', `connection-path preview${drag.type === 'content' ? ' content' : ''}`);
        preview.setAttribute('d', drag.direction === 'output' ? connectionPath(fixed, canvasPoint) : connectionPath(canvasPoint, fixed));
        fragment.append(preview);
      }
    }
    elements.connectionLayer.replaceChildren(fragment);
    elements.connectionCount.textContent = `${state.connections.length} 条连接`;
  }

  return { bindConnectionPort, bindNodeDrag, renderConnections };
}