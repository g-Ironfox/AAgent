const STORAGE_KEY = 'aagent.workflow.draft.v1';
const NODE_TYPES = new Set(['input', 'router', 'llm']);
const TOOL_IDS = new Set(['web_search', 'documents', 'terminal']);
let idSequence = 0;

const initialNodes = [
  { id: 'input', type: 'input', name: 'Input', x: 52, y: 238 },
  { id: 'router-1', type: 'router', name: '任务路由', branches: [{ id: 'branch-1', name: '分支 1' }, { id: 'branch-2', name: '分支 2' }], x: 310, y: 238 },
  { id: 'llm-1', type: 'llm', name: '主 LLM', model: '', prompt: '完成用户请求，并返回清晰的结果。', tools: ['documents'], think: false, x: 568, y: 238 },
];

const initialConnections = [
  { id: 'control-input-router-1', fromId: 'input', fromPortId: 'control-out', toId: 'router-1', toPortId: 'control-in', type: 'control' },
  { id: 'content-input-router-1', fromId: 'input', fromPortId: 'content-out', toId: 'router-1', toPortId: 'content-in', type: 'content' },
  { id: 'control-router-1-llm-1', fromId: 'router-1', fromPortId: 'branch-1', toId: 'llm-1', toPortId: 'control-in', type: 'control' },
  { id: 'content-input-llm-1', fromId: 'input', fromPortId: 'content-out', toId: 'llm-1', toPortId: 'content-in', type: 'content' },
];

export const state = {
  nodes: structuredClone(initialNodes),
  connections: structuredClone(initialConnections),
  selectedId: 'input',
  connectionDrag: null,
};

export function nodeById(id) {
  return state.nodes.find((node) => node.id === id);
}

export function createWorkflowId(prefix) {
  idSequence += 1;
  return `${prefix}-${Date.now()}-${idSequence}`;
}

function nextNodePosition() {
  const positions = [];
  for (let row = 0; row < 4; row += 1) {
    for (let column = 0; column < 3; column += 1) {
      positions.push({ x: 52 + column * 258, y: 72 + row * 150 });
    }
  }
  return positions.find((position) => state.nodes.every((node) => Math.abs(node.x - position.x) >= 210 || Math.abs(node.y - position.y) >= 125))
    || { x: 52 + state.nodes.length * 210, y: 72 };
}

export function addNode(type) {
  if (type !== 'router' && type !== 'llm') return;
  const number = state.nodes.filter((node) => node.type === type).length + 1;
  const position = nextNodePosition();
  const node = type === 'router'
    ? { id: createWorkflowId('router'), type, name: `Router ${number}`, branches: [{ id: createWorkflowId('branch'), name: '分支 1' }, { id: createWorkflowId('branch'), name: '分支 2' }], ...position }
    : { id: createWorkflowId('llm'), type, name: `LLM ${number}`, model: '', prompt: '处理输入并返回结果。', tools: [], think: false, ...position };
  state.nodes.push(node);
  state.selectedId = node.id;
}

export function deleteNode(id) {
  if (id === 'input') return;
  state.nodes = state.nodes.filter((node) => node.id !== id);
  state.connections = state.connections.filter((connection) => connection.fromId !== id && connection.toId !== id);
  state.selectedId = state.nodes[0].id;
}

export function saveDraft() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(workflowSnapshot()));
}

export function workflowSnapshot() {
  return structuredClone({ version: 1, nodes: state.nodes, connections: state.connections });
}

export function resetDraft() {
  localStorage.removeItem(STORAGE_KEY);
  state.nodes = structuredClone(initialNodes);
  state.connections = structuredClone(initialConnections);
  state.selectedId = 'input';
  state.connectionDrag = null;
}

export function loadDraft() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    const savedNodes = Array.isArray(saved) ? saved : saved?.nodes;
    if (!Array.isArray(savedNodes)) return false;
    const ids = new Set();
    const normalizedNodes = savedNodes.flatMap((node) => {
      if (!node || typeof node.id !== 'string' || ids.has(node.id) || !NODE_TYPES.has(node.type)) return [];
      ids.add(node.id);
      const normalized = {
        id: node.id,
        type: node.type,
        name: typeof node.name === 'string' ? node.name.slice(0, 30) : node.type.toUpperCase(),
        x: Number.isFinite(node.x) ? Math.max(12, node.x) : 52,
        y: Number.isFinite(node.y) ? Math.max(12, node.y) : 72,
      };
      if (node.type === 'router') {
        const branchIds = new Set();
        normalized.branches = (Array.isArray(node.branches) ? node.branches : []).flatMap((branch) => {
          if (!branch || typeof branch.id !== 'string' || branchIds.has(branch.id)) return [];
          branchIds.add(branch.id);
          return [{ id: branch.id, name: typeof branch.name === 'string' ? branch.name.slice(0, 30) : '分支' }];
        });
        if (!normalized.branches.length) normalized.branches.push({ id: createWorkflowId('branch'), name: '分支 1' });
      }
      if (node.type === 'llm') {
        normalized.model = typeof node.model === 'string' ? node.model : 'gpt-5';
        normalized.prompt = typeof node.prompt === 'string' ? node.prompt.slice(0, 500) : '';
        normalized.tools = Array.isArray(node.tools) ? [...new Set(node.tools.filter((tool) => TOOL_IDS.has(tool)))] : [];
        normalized.think = node.think === true;
      }
      return [normalized];
    });
    if (!normalizedNodes.some((node) => node.id === 'input' && node.type === 'input')) return false;
    state.nodes = normalizedNodes;
    state.connections = (Array.isArray(saved?.connections) ? saved.connections : initialConnections).filter((connection) => {
      if (!connection || typeof connection.id !== 'string' || !['control', 'content'].includes(connection.type)) return false;
      const from = state.nodes.find((node) => node.id === connection.fromId);
      const to = state.nodes.find((node) => node.id === connection.toId);
      if (!from || !to || typeof connection.fromPortId !== 'string' || typeof connection.toPortId !== 'string') return false;
      const validFromPort = connection.type === 'control'
        ? (from.type !== 'input' && from.type !== 'llm'
          ? from.branches.some((branch) => branch.id === connection.fromPortId)
          : connection.fromPortId === 'control-out')
        : (from.type === 'input' && connection.fromPortId === 'content-out')
          || (from.type === 'llm' && ['output', ...(from.think === true ? ['reasoning'] : [])].includes(connection.fromPortId));
      const validToPort = connection.type === 'control'
        ? to.type !== 'input' && connection.toPortId === 'control-in'
        : (to.type === 'llm' || to.type === 'router') && connection.toPortId === 'content-in';
      return validFromPort && validToPort;
    });
    state.selectedId = 'input';
    state.connectionDrag = null;
    return true;
  } catch (error) {
    console.warn('Workflow 草稿读取失败', error);
    return false;
  }
}