import { compileLifecycles, lifecycleFingerprint } from './lifecycle.js';
import { setRuntimeStyles } from './runtime-styles.js';

export function createLifecyclePreview(elements, workflow) {
  let result = null;
  let fingerprint = null;
  let compiledNodes = null;
  let compiledConnections = null;
  const scopeFor = (id) => result?.scopes.find((scope) => scope.id === id);

  function clear() {
    result = null;
    fingerprint = null;
    compiledNodes = null;
    compiledConnections = null;
    if (elements.lifecyclePanel) elements.lifecyclePanel.hidden = true;
    elements.compileLifecyclesButton?.setAttribute('aria-pressed', 'false');
  }

  function invalidate() {
    if (!result) return false;
    if (compiledNodes === workflow.nodes && compiledConnections === workflow.connections
      && fingerprint === lifecycleFingerprint(workflow)) return false;
    clear();
    if (elements.lifecyclePanel) {
      elements.lifecyclePanel.hidden = false;
      elements.lifecycleSummary.textContent = '流程已修改，请重新编译生命周期';
      elements.lifecyclePanel.classList.remove('has-errors');
      elements.lifecycleScopes.replaceChildren();
      elements.lifecycleErrors.replaceChildren();
    }
    return true;
  }

  function compile() {
    result = compileLifecycles(workflow);
    fingerprint = lifecycleFingerprint(workflow);
    compiledNodes = workflow.nodes;
    compiledConnections = workflow.connections;
    elements.compileLifecyclesButton?.setAttribute('aria-pressed', 'true');
    if (!elements.lifecyclePanel) return result;
    elements.lifecyclePanel.hidden = false;
    elements.lifecyclePanel.classList.toggle('has-errors', result.errors.length > 0);
    elements.lifecycleSummary.textContent = result.structureValid
      ? `${result.scopes.length} 个生命周期 · ${workflow.nodes.length} 个节点 · ${result.errors.length ? `${result.errors.length} 条数据越界` : '未发现跨生命周期数据连线'}`
      : `生命周期编译失败 · ${result.errors.length} 个结构问题（未应用着色）`;
    elements.lifecycleScopes.replaceChildren();
    if (result.structureValid) {
      for (const scope of result.scopes) {
        const chip = document.createElement('span');
        chip.className = 'lifecycle-scope';
        chip.title = scope.path.join(' → ');
        chip.dataset.scopeId = scope.id;
        setRuntimeStyles(chip, `lifecycle-legend:${scope.id}`, { '--lifecycle-color': scope.color, '--lifecycle-fill': scope.fill });
        chip.textContent = `${scope.parentId ? `${scope.parentId} → ` : ''}${scope.id} · ${scope.label}`;
        elements.lifecycleScopes.append(chip);
      }
    }
    elements.lifecycleErrors.replaceChildren(...result.errors.map((error) => {
      const item = document.createElement('li');
      item.textContent = error.message;
      return item;
    }));
    return result;
  }

  function decorateNode(element, node) {
    if (!result?.structureValid) return;
    const scope = scopeFor(result.nodeScopes.get(node.id));
    if (!scope) return;
    element.classList.add('lifecycle-colored');
    element.dataset.lifecycleId = scope.id;
    setRuntimeStyles(element, `lifecycle-node:${node.id}`, { '--lifecycle-color': scope.color, '--lifecycle-fill': scope.fill });
    const children = result.scopes.filter((item) => item.ownerId === node.id);
    const badge = document.createElement('span');
    badge.className = 'lifecycle-badge';
    badge.textContent = `${scope.id}${children.length ? ` → ${children.map((child) => child.id).join(' / ')}` : ''}`;
    badge.title = `${scope.path.join(' → ')}${children.length ? '\n生命周期衔接点；控制出口进入相应子空间。' : ''}`;
    element.append(badge);
    for (const port of element.querySelectorAll('.node-port')) {
      let portScope = scope.id;
      if (port.dataset.portDirection === 'output') {
        portScope = result.outputScopes.get(node.id)?.[port.dataset.portId]
          || children.find((child) => child.portId === port.dataset.portId)?.id || scope.id;
      } else if (['foreach', 'while_pop'].includes(node.type) && port.dataset.portId === 'loop-in') {
        portScope = children.find((child) => child.kind === 'loop')?.id || scope.id;
      }
      port.dataset.lifecycleId = portScope;
      port.title = `${port.title || port.dataset.portLabel} · ${portScope} · ${scopeFor(portScope).path.join(' → ')}`;
    }
  }

  function decorateConnection(path, connection) {
    if (!result?.invalidConnections.has(connection)) return;
    path.classList.add('lifecycle-invalid');
    const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
    title.textContent = result.errors.find((error) => error.connection === connection)?.message;
    path.append(title);
  }

  return { compile, clear, invalidate, decorateNode, decorateConnection };
}
