const STORAGE_KEY = 'aagent.workflow.draft.v1';

const initialNodes = [
  { id: 'input', type: 'input', name: 'Input', x: 52, y: 238 },
  { id: 'router-1', type: 'router', name: '任务路由', prompt: '根据用户输入选择最合适的处理节点。', x: 310, y: 238 },
  { id: 'llm-1', type: 'llm', name: '主 LLM', model: 'gpt-5', prompt: '完成用户请求，并返回清晰的结果。', tools: ['documents'], x: 568, y: 238 },
];

const initialConnections = [
  { id: 'control-input-router-1', fromId: 'input', toId: 'router-1', type: 'control' },
  { id: 'control-router-1-llm-1', fromId: 'router-1', toId: 'llm-1', type: 'control' },
  { id: 'content-input-llm-1', fromId: 'input', toId: 'llm-1', type: 'content' },
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

export function llmNodes() {
  return state.nodes.filter((node) => node.type === 'llm');
}

export function addNode(type) {
  const number = state.nodes.filter((node) => node.type === type).length + 1;
  const index = state.nodes.length - 1;
  const position = { x: 310 + (index % 2) * 258, y: 80 + Math.floor(index / 2) * 160 };
  const node = type === 'router'
    ? { id: `router-${Date.now()}`, type, name: `Router ${number}`, prompt: '根据输入选择一个候选分支。', ...position }
    : { id: `llm-${Date.now()}`, type, name: `LLM ${number}`, model: 'gpt-5', prompt: '处理输入并返回结果。', tools: [], ...position };
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
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ nodes: state.nodes, connections: state.connections }));
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
    if (!Array.isArray(savedNodes) || !savedNodes.some((node) => node.id === 'input')) return false;
    state.nodes = savedNodes;
    state.connections = Array.isArray(saved?.connections)
      ? saved.connections
      : initialConnections.filter((connection) => state.nodes.some((node) => node.id === connection.fromId) && state.nodes.some((node) => node.id === connection.toId));
    return true;
  } catch (error) {
    console.warn('Workflow 草稿读取失败', error);
    return false;
  }
}