import { DATA_TYPES } from './node-contract.js';

export function validateFunctions(value = [], structs = []) {
  if (!Array.isArray(value)) throw new Error('metadata.functions 必须是数组');
  const ids = new Set();
  const names = new Set();
  for (const fn of value) {
    if (!fn || Object.keys(fn).sort().join(',') !== 'id,input_ports,name,output_ports'
      || typeof fn.id !== 'string' || !/^[A-Za-z_][A-Za-z0-9_]*$/.test(fn.id) || ids.has(fn.id)
      || typeof fn.name !== 'string' || !fn.name.trim() || names.has(fn.name.trim().toLowerCase())) {
      throw new Error('函数 ID 或名称无效、重复');
    }
    ids.add(fn.id);
    names.add(fn.name.trim().toLowerCase());
    for (const side of ['input_ports', 'output_ports']) {
      if (!Array.isArray(fn[side])) throw new Error(`函数 ${fn.id} 的接口必须是数组`);
      const portNames = new Set();
      for (const port of fn[side]) {
        const ref = /^(?:list-)?struct:(.+)$/.exec(port?.type || '')?.[1];
        if (!port || Object.keys(port).sort().join(',') !== 'name,type'
          || typeof port.name !== 'string' || !port.name.trim() || portNames.has(port.name)
          || (!DATA_TYPES.has(port.type) && !structs.some((s) => s.id === ref))) {
          throw new Error(`函数 ${fn.id} 的 ${side} 无效`);
        }
        portNames.add(port.name);
      }
    }
  }
  return structuredClone(value);
}

export function bindNodeFunctions(nodes, functions = []) {
  const byId = new Map(functions.map((fn) => [fn.id, fn]));
  for (const node of nodes) {
    const owner = node.function_id;
    if (!['function_input', 'function_output'].includes(node.type)) delete node.function_id;
    let fn;
    let inputs = [];
    let outputs = [];
    if (node.type === 'function_call') {
      fn = byId.get(node.callee_id);
      if (!fn) throw new Error(`调用的函数不存在：${node.callee_id}`);
      inputs = fn.input_ports;
      outputs = fn.output_ports;
    } else if (['function_input', 'function_output'].includes(node.type)) {
      fn = byId.get(owner);
      if (!fn) throw new Error('函数输入和输出必须属于一个函数');
      if (node.type === 'function_input') outputs = fn.input_ports;
      else inputs = fn.output_ports;
    }
    node._function_inputs = inputs;
    node._function_outputs = outputs;
  }
}
