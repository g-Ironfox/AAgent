import { portsForNode } from './domain/node-contract.js';
import { state } from './domain/serialization.js';

export function createWorkflowEditor(elements, markChanged) {
  const editorState = { selectedId: 'input', connectionDrag: null };
  let connectionSequence = 0;
  let renderInspector = () => {};

  function setInspectorRenderer(renderer) {
    renderInspector = renderer;
  }

  function createConnectionId() {
    connectionSequence += 1;
    return `connection-${Date.now()}-${connectionSequence}`;
  }

  function portCenter(nodeId, portId, direction = null, type = null) {
    const nodeElement = Array.from(elements.nodeLayer.querySelectorAll('[data-node-id]'))
      .find((element) => element.dataset.nodeId === nodeId);
    const port = Array.from(nodeElement?.querySelectorAll('[data-port-id]') || [])
      .find((element) => (
        element.dataset.portId === portId
        && (!direction || element.dataset.portDirection === direction)
        && (!type || element.dataset.portType === type)
      ));
    if (!port) return null;
    const canvasRect = elements.canvas.getBoundingClientRect();
    const rect = port.getBoundingClientRect();
    return {
      x: rect.left + rect.width / 2 - canvasRect.left + elements.canvas.scrollLeft,
      y: rect.top + rect.height / 2 - canvasRect.top + elements.canvas.scrollTop,
      direction: port.dataset.portDirection,
    };
  }

  function connectionPath(start, end) {
    const curve = Math.max(42, Math.abs(end.x - start.x) * 0.45);
    const startDirection = start.direction === 'input' ? -1 : 1;
    const endDirection = end.direction === 'output' ? 1 : -1;
    return `M ${start.x} ${start.y} C ${start.x + curve * startDirection} ${start.y}, ${end.x + curve * endDirection} ${end.y}, ${end.x} ${end.y}`;
  }

  function compatiblePort(port, drag) {
    const targetDirection = drag.targetDirection || (drag.direction === 'output' ? 'input' : 'output');
    return Boolean(
      port
      && port.dataset.portType === drag.type
      && port.dataset.portDirection === targetDirection
      && port.dataset.nodeId !== drag.anchorNodeId,
    );
  }

  function setCompatiblePorts(drag) {
    for (const port of elements.nodeLayer.querySelectorAll('.node-port')) {
      port.classList.toggle('compatible', compatiblePort(port, drag));
    }
  }

  function finishConnectionDrag(event, cancelled = false) {
    const drag = editorState.connectionDrag;
    if (!drag || event.pointerId !== drag.pointerId) return;
    if (cancelled) {
      if (drag.connection && !state.connections.includes(drag.connection)) state.connections.push(drag.connection);
      finishConnectionInteraction(event);
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
      if (drag.type !== 'control' && drag.direction === 'input' && connection) {
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
    finishConnectionInteraction(event);
  }

  function finishConnectionInteraction(event) {
    for (const port of elements.nodeLayer.querySelectorAll('.node-port')) port.classList.remove('compatible');
    if (event.currentTarget?.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    editorState.connectionDrag = null;
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
        ? state.connections.find((item) => item.toId === node.id && item.toPortId === port.dataset.portId && item.type === type)
        : null;
      const outgoing = direction === 'output'
        ? state.connections.filter((item) => item.fromId === node.id && item.fromPortId === port.dataset.portId && item.type === type)
        : [];
      const connectionId = type === 'control' ? incoming?.id || (outgoing.length === 1 ? outgoing[0].id : null) : incoming?.id || null;
      const connection = connectionId ? incoming || outgoing.find((item) => item.id === connectionId) : null;
      if (connection) state.connections = state.connections.filter((item) => item.id !== connection.id);
      const hasDataInputConnection = type !== 'control' && direction === 'input' && connection;
      const hasControlConnection = type === 'control' && connection;
      const anchorNodeId = hasDataInputConnection || (hasControlConnection && direction === 'input')
        ? connection.fromId
        : hasControlConnection && direction === 'output' ? connection.toId : node.id;
      const anchorPortId = hasDataInputConnection || (hasControlConnection && direction === 'input')
        ? connection.fromPortId
        : hasControlConnection && direction === 'output' ? connection.toPortId : port.dataset.portId;
      const anchorDirection = hasDataInputConnection || (hasControlConnection && direction === 'input')
        ? 'output'
        : hasControlConnection && direction === 'output' ? 'input' : direction;
      editorState.connectionDrag = {
        pointerId: event.pointerId,
        direction,
        targetDirection: connection && type !== 'control' && direction === 'input' ? 'input' : hasControlConnection ? direction : null,
        type,
        anchorNodeId,
        anchorPortId,
        anchorDirection,
        connectionId,
        connection,
        pointer: { x: event.clientX, y: event.clientY },
      };
      port.setPointerCapture(event.pointerId);
      setCompatiblePorts(editorState.connectionDrag);
      renderConnections();
    });
    port.addEventListener('pointermove', (event) => {
      if (!editorState.connectionDrag || event.pointerId !== editorState.connectionDrag.pointerId) return;
      editorState.connectionDrag.pointer = { x: event.clientX, y: event.clientY };
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
    const finishDrag = (event) => {
      if (!drag || event.pointerId !== drag.pointerId) return;
      element.classList.remove('dragging');
      if (element.hasPointerCapture(event.pointerId)) element.releasePointerCapture(event.pointerId);
      drag = null;
    };
    element.addEventListener('pointerup', finishDrag);
    element.addEventListener('pointercancel', finishDrag);
  }

  function createNodeUI(node) {
    const element = document.createElement('button');
    const ports = portsForNode(node);
    const inputs = ports.filter((port) => port.direction === 'input');
    const outputs = ports.filter((port) => port.direction === 'output');
    const symbols = { input: 'IN', output: 'OUT', router: 'R', construct_message: 'M', construct_content: 'C', construct_list: 'L', list_append: 'L+', foreach: 'FE', history: 'H', local_tool: 'LT', remote_sync_tool: 'RS', remote_async_tool: 'RA', context_create: 'C+', context_read: 'CR', context_write: 'CW', workflow: 'WF' };
    element.type = 'button';
    element.className = `flow-node ${node.type}${node.id === editorState.selectedId ? ' selected' : ''}`;
    element.style.left = `${node.x}px`;
    element.style.top = `${node.y}px`;
    element.dataset.nodeId = node.id;
    const head = document.createElement('span');
    head.className = 'flow-node-head';
    head.innerHTML = `<span class="node-symbol ${node.type}-symbol">${symbols[node.type] || 'L'}</span><span><strong></strong><small></small></span>`;
    head.querySelector('strong').textContent = node.name;
    head.querySelector('small').textContent = node.type.toUpperCase();
    const body = document.createElement('span');
    body.className = 'flow-node-body';
    body.style.height = `${Math.max(70, 8 + Math.max(inputs.length, outputs.length) * 28)}px`;
    for (const port of ports) {
      const portElement = document.createElement('span');
      const row = port.direction === 'input' ? inputs.indexOf(port) : outputs.indexOf(port);
      portElement.className = 'node-port';
      portElement.style.top = `${8 + row * 28}px`;
      Object.assign(portElement.dataset, {
        portId: port.id,
        portDirection: port.direction,
        portType: port.type,
        portMultiple: String(port.multiple === true),
        portLabel: port.label,
      });
      portElement.setAttribute('aria-label', `${port.direction === 'input' ? '输入' : '输出'} ${port.label} (${port.type})`);
      portElement.title = port.title;
      body.append(portElement);
    }
    element.append(head, body);
    element.addEventListener('click', () => selectNode(node.id));
    element.querySelectorAll('.node-port').forEach((port) => bindConnectionPort(port, node));
    bindNodeDrag(element, node);
    return element;
  }

  function renderNodes() {
    elements.nodeLayer.replaceChildren(...state.nodes.map(createNodeUI));
    const renderedNodes = Array.from(elements.nodeLayer.querySelectorAll('.flow-node'));
    const maxX = Math.max(1800, ...renderedNodes.map((element) => element.offsetLeft + element.offsetWidth + 20));
    const maxY = Math.max(1200, ...renderedNodes.map((element) => element.offsetTop + element.offsetHeight + 20));
    elements.nodeLayer.style.width = `${maxX}px`;
    elements.nodeLayer.style.height = `${maxY}px`;
    elements.connectionLayer.style.width = `${maxX}px`;
    elements.connectionLayer.style.height = `${maxY}px`;
    elements.nodeCount.textContent = `${state.nodes.length} 个实例`;
    requestAnimationFrame(renderConnections);
  }

  function renderConnections() {
    const canvasRect = elements.canvas.getBoundingClientRect();
    const width = Math.max(elements.nodeLayer.scrollWidth, elements.canvas.clientWidth);
    const height = Math.max(elements.nodeLayer.scrollHeight, elements.canvas.clientHeight);
    elements.connectionLayer.setAttribute('viewBox', `0 0 ${width} ${height}`);
    elements.connectionLayer.setAttribute('width', String(width));
    elements.connectionLayer.setAttribute('height', String(height));
    const paths = [];
    for (const connection of state.connections) {
      const start = portCenter(connection.fromId, connection.fromPortId, 'output', connection.type);
      const end = portCenter(connection.toId, connection.toPortId, 'input', connection.type);
      if (!start || !end) continue;
      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('class', `connection-path ${connection.type}`);
      path.setAttribute('d', connectionPath(start, end));
      paths.push(path);
    }
    if (editorState.connectionDrag) {
      const drag = editorState.connectionDrag;
      const canvasPoint = {
        x: drag.pointer.x - canvasRect.left + elements.canvas.scrollLeft,
        y: drag.pointer.y - canvasRect.top + elements.canvas.scrollTop,
        direction: drag.anchorDirection === 'output' ? 'input' : 'output',
      };
      const anchor = portCenter(drag.anchorNodeId, drag.anchorPortId, drag.anchorDirection, drag.type);
      if (anchor) {
        const preview = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        preview.setAttribute('class', `connection-path preview ${drag.type}`);
        preview.setAttribute('d', drag.anchorDirection === 'output' ? connectionPath(anchor, canvasPoint) : connectionPath(canvasPoint, anchor));
        paths.push(preview);
      }
    }
    elements.connectionLayer.replaceChildren(...paths);
    elements.connectionCount.textContent = `${state.connections.length} 条连接`;
  }

  function selectNode(id) {
    editorState.selectedId = id;
    renderNodes();
    renderInspector();
  }

  function ensureSelection() {
    if (!state.nodes.some((node) => node.id === editorState.selectedId)) editorState.selectedId = state.nodes[0]?.id;
    return editorState.selectedId;
  }

  function bindCanvasPan() {
    let pan = null;
    elements.canvas.addEventListener('pointerdown', (event) => {
      if (event.button !== 0 || event.target.closest('.flow-node')) return;
      pan = { pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, scrollLeft: elements.canvas.scrollLeft, scrollTop: elements.canvas.scrollTop };
      elements.canvas.setPointerCapture(event.pointerId);
      elements.canvas.classList.add('panning');
    });
    elements.canvas.addEventListener('pointermove', (event) => {
      if (!pan || event.pointerId !== pan.pointerId) return;
      elements.canvas.scrollLeft = pan.scrollLeft - (event.clientX - pan.startX);
      elements.canvas.scrollTop = pan.scrollTop - (event.clientY - pan.startY);
    });
    const finishPan = (event) => {
      if (!pan || event.pointerId !== pan.pointerId) return;
      elements.canvas.classList.remove('panning');
      if (elements.canvas.hasPointerCapture(event.pointerId)) elements.canvas.releasePointerCapture(event.pointerId);
      pan = null;
    };
    elements.canvas.addEventListener('pointerup', finishPan);
    elements.canvas.addEventListener('pointercancel', finishPan);
  }

  function renderWorkflow() {
    ensureSelection();
    renderNodes();
    renderInspector();
    renderConnections();
  }

  bindCanvasPan();
  return {
    editorState,
    ensureSelection,
    renderConnections,
    renderNodes,
    renderWorkflow,
    selectNode,
    setInspectorRenderer,
  };
}