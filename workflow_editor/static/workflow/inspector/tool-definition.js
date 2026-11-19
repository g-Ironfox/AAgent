import { reconcileConnections } from '../domain/connection-rules.js';

const fields = ['tool_name', 'description', 'schema', 'required'];

export function toolPreview(node) {
  if (fields.some((field) => node[`${field}_source`] === 'port')) return '运行时根据输入端口生成 Tool JSON。';
  if (typeof node.tool_name !== 'string' || !node.tool_name.trim()) throw new Error('工具名称不能为空');
  const parameters = typeof node.schema === 'string' ? JSON.parse(node.schema) : structuredClone(node.schema ?? { type: 'object', properties: {} });
  if (!parameters || Array.isArray(parameters) || parameters.type !== 'object') throw new Error('Schema 必须为 type: object 的 JSON Schema');
  if (node.required !== undefined) parameters.required = [...node.required];
  if (parameters.required !== undefined && (!Array.isArray(parameters.required) || parameters.required.some((name) => typeof name !== 'string' || !Object.hasOwn(parameters.properties || {}, name)) || new Set(parameters.required).size !== parameters.required.length)) throw new Error('必填参数必须是 Schema.properties 中不重复的参数名');
  return JSON.stringify({ type: 'function', function: { name: node.tool_name, description: node.description ?? '', parameters } }, null, 2);
}

export function bindConstructTool(node, context) {
  const mount = context.elements.inspectorContent;
  const preview = mount.querySelector('[data-tool-preview]');
  const error = mount.querySelector('[data-tool-error]');
  const empty = mount.querySelector('[data-tool-required-empty]');
  const requiredField = mount.querySelector('[data-tool-value="required"]');
  const refresh = () => {
    try { preview.value = toolPreview(node); error.textContent = ''; }
    catch (reason) { preview.value = ''; error.textContent = reason.message; }
  };
  const changed = () => { context.markChanged(); refresh(); };
  for (const field of fields) {
    const source = mount.querySelector(`[data-tool-source="${field}"]`);
    const value = mount.querySelector(`[data-tool-value="${field}"]`);
    source.value = node[`${field}_source`] || 'fixed';
    mount.querySelector(`[data-tool-fixed="${field}"]`).hidden = source.value === 'port';
    if (field === 'schema') value.value = typeof node.schema === 'string' ? node.schema : JSON.stringify(node.schema ?? { type: 'object', properties: {} }, null, 2);
    else if (field === 'required') value.value = (node.required || []).join(', ');
    else value.value = node[field] || '';
    source.addEventListener('change', () => {
      node[`${field}_source`] = source.value;
      reconcileConnections(state);
      context.markChanged();
      context.editor.renderNodes();
      context.renderInspector();
    });
    value.addEventListener('input', () => {
      if (field === 'schema') {
        // Preserve incomplete JSON while typing so save/undo cannot silently restore stale values.
        node.schema = value.value;
      } else if (field === 'required') {
        const names = value.value.split(/[,，\n]/).map((name) => name.trim()).filter(Boolean);
        if (names.length) node.required = names;
        else if (empty.checked) node.required = [];
        else delete node.required;
      } else node[field] = value.value;
      changed();
    });
  }
  empty.checked = Array.isArray(node.required) && node.required.length === 0;
  empty.closest('label').hidden = node.required_source === 'port';
  empty.addEventListener('change', () => {
    if (!requiredField.value.trim()) {
      if (empty.checked) node.required = [];
      else delete node.required;
    }
    changed();
  });
  refresh();
}
