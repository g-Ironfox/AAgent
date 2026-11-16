// Mirror the Manager renderer locally: both services deploy independently.
// test_workspace_workflow.mjs checks that their renderers stay identical.
import { workflowCanvasFilename, workflowCanvasSvg } from './workflow_canvas.mjs';
import { editWorkflowMetadata, parseWorkflowFile, validateWorkflowMetadata } from './workflow-file.mjs';

export function createWorkflowPanel({ onChange, onError }) {
  const el = Object.fromEntries([
    'workflowPanel', 'workflowVersion', 'workflowName', 'workflowDescription', 'workflowCanvasPreview',
    'workflowCanvasMeta', 'canvasExportButton', 'inputPorts', 'outputPorts', 'workflowDependencies',
    'dependencyCount', 'remoteTools', 'remoteToolCount',
  ].map((id) => [id, document.getElementById(id)]));
  let original = null;
  let originalContent = '';
  let dependencyInputs = [];
  let disabled = true;

  function element(tag, className, text) {
    const result = document.createElement(tag);
    if (className) result.className = className;
    if (text !== undefined) result.textContent = text;
    return result;
  }

  function renderPorts(container, ports = []) {
    container.replaceChildren();
    for (const port of ports) {
      const row = element('div', 'metadata-port-row');
      row.append(element('strong', '', port.name), element('code', '', port.type));
      container.append(row);
    }
    if (!ports.length) container.append(element('p', 'metadata-port-empty', '暂无字段'));
  }

  function contract(title, direction, ports) {
    const section = element('section', 'dependency-contract');
    const heading = element('h5');
    heading.append(element('span', 'metadata-port-mark ' + direction, direction === 'input' ? 'IN' : 'OUT'), title);
    const list = element('div', 'dependency-contract-ports');
    renderPorts(list, ports);
    section.append(heading, list);
    return section;
  }

  function renderReferences(container, references, editable) {
    container.replaceChildren();
    if (!references.length) container.append(element('p', 'metadata-port-empty', editable ? '无 Workflows 依赖' : '无 Tool 依赖'));
    references.forEach((reference, index) => {
      const item = element('article', 'workflow-dependency-item');
      const heading = element('header');
      const identity = element('div', 'workflow-dependency-identity');
      identity.append(element('span', 'metadata-port-mark ' + (editable ? 'workflow' : 'remote-tool'), editable ? 'WF' : reference.kind === 'local' ? 'LT' : 'RT'));
      const name = reference.name ?? reference.workflow_name;
      if (editable) {
        const input = element('input', 'dependency-name-input');
        input.type = 'text';
        input.value = name;
        input.disabled = disabled;
        input.setAttribute('aria-label', '依赖 Workflow ' + (index + 1) + ' 名称');
        input.addEventListener('input', sync);
        dependencyInputs.push(input);
        identity.append(input);
      } else identity.append(element('strong', '', name));
      heading.append(identity);
      const contracts = element('div', 'dependency-contracts');
      contracts.append(contract('Input', 'input', reference.input_ports), contract('Output', 'output', reference.output_ports));
      item.append(heading, contracts);
      container.append(item);
    });
  }

  function currentWorkflow() {
    return editWorkflowMetadata(original, {
      name: el.workflowName.value,
      description: el.workflowDescription.value,
      dependencies: dependencyInputs.map((input) => input.value),
    });
  }

  function renderCanvas(workflow) {
    try {
      const parsed = new DOMParser().parseFromString(workflowCanvasSvg(workflow), 'image/svg+xml');
      const svg = parsed.documentElement;
      if (svg.nodeName === 'parsererror') throw new Error('画布 SVG 生成失败');
      // The WebUI CSP disallows inline styles; the matching rules live in the stylesheet.
      svg.querySelectorAll('style').forEach((style) => style.remove());
      svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
      const box = svg.getAttribute('viewBox').split(/\s+/).map(Number);
      svg.setAttribute('viewBox', `${box[0]} ${box[1] + 54} ${box[2]} ${Math.max(1, box[3] - 54)}`);
      el.workflowCanvasPreview.replaceChildren(document.importNode(svg, true));
      el.workflowCanvasMeta.textContent = `${workflow.nodes.length} 节点 / ${workflow.connections.length} 连接`;
    } catch (error) {
      el.workflowCanvasPreview.replaceChildren(element('p', 'workflow-canvas-preview-empty', error.message || '画布生成失败'));
      el.workflowCanvasMeta.textContent = '不可用';
    }
  }

  function sync() {
    if (disabled || !original) return;
    const workflow = currentWorkflow();
    // Entering/leaving the view or undoing every edit preserves the exact source text.
    onChange(JSON.stringify(workflow) === JSON.stringify(original) ? originalContent : JSON.stringify(workflow, null, 2));
    renderCanvas(workflow);
  }

  el.workflowName.addEventListener('input', sync);
  el.workflowDescription.addEventListener('input', sync);
  el.canvasExportButton.addEventListener('click', () => {
    if (!original || el.canvasExportButton.disabled) return;
    try {
      const workflow = currentWorkflow();
      const url = URL.createObjectURL(new Blob([workflowCanvasSvg(workflow)], { type: 'image/svg+xml;charset=utf-8' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = workflowCanvasFilename(workflow.name);
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) { onError(error.message || '导出画布失败'); }
  });

  return {
    setContent(content) {
      original = parseWorkflowFile(content);
      originalContent = content;
      dependencyInputs = [];
      if (!original) return false;
      el.workflowVersion.textContent = 'SCHEMA ' + original.schema_version + ' / VERSION ' + (original.version ?? 1);
      el.workflowName.value = original.name;
      el.workflowDescription.value = original.description || '';
      renderPorts(el.inputPorts, original.input_ports);
      renderPorts(el.outputPorts, original.output_ports);
      renderReferences(el.workflowDependencies, original.workflow_nodes || [], true);
      const tools = [...(original.metadata?.tools || []), ...(original.remote_tools || []).map((tool) => ({ ...tool, kind: 'remote' }))];
      renderReferences(el.remoteTools, tools, false);
      el.dependencyCount.textContent = (original.workflow_nodes?.length || 0) + ' 项';
      el.remoteToolCount.textContent = tools.length + ' 项';
      renderCanvas(original);
      return true;
    },
    setEditing(editing, busy) {
      disabled = !editing || busy;
      for (const input of [el.workflowName, el.workflowDescription, ...dependencyInputs]) input.disabled = disabled;
      el.canvasExportButton.disabled = busy;
    },
    validate() { if (original) validateWorkflowMetadata(currentWorkflow()); },
  };
}
