"""Build the editable ReAct example from the existing Workflow 2.0 primitives.

Run from any directory: python scripts/build_react_workflow.py
No runtime code, protocol changes, or external services are required.
"""
from pathlib import Path
import json


class Graph:
    def __init__(self):
        self.doc = {"schema_version": "2.0", "description": "ReAct with native tool calls, per-call human approval, durable history and function-scoped branches.",
                    "input_ports": [{"name": "task", "type": "content"}], "output_ports": [],
                    "metadata": {"structs": [], "functions": [], "tools": [
                        {"name": "workspace.list_files", "kind": "local", "input_ports": [],
                         "output_ports": [{"name": "items", "type": "list-content"}, {"name": "revision", "type": "number"}]},
                        {"name": "workspace.get_file", "kind": "local", "input_ports": [{"name": "file_id", "type": "content"}],
                         "output_ports": [{"name": "output", "type": "content"}]},
                    ]}, "nodes": [], "connections": []}
        self.lane = 0
        self.column = 0

    def node(self, id, type, **kw):
        self.doc["nodes"].append(dict(id=id, type=type, name=kw.pop('name', id.replace('_', ' ')), x=80+260*self.column, y=100+600*self.lane, **kw))
        self.column += 1
        return id

    def function(self, name, inputs, outputs=()):
        self.doc['metadata']['functions'].append(dict(id=name, name=name, input_ports=ports(inputs), output_ports=ports(outputs)))
        self.lane += 1
        self.column = 0
        return self.node(name+'_in', 'function_input', function_id=name)

    def ret(self, id, function):
        return self.node(id, 'function_output', function_id=function)

    def data(self, source, out, target, inp, type='content'):
        self.doc['connections'].append(dict(fromId=source, fromPortId=out, toId=target, toPortId=inp, type=type))

    def control(self, source, target, out='control-out', inp='control-in'):
        self.data(source, out, target, inp, 'control')

    def chain(self, *nodes):
        for a, b in zip(nodes, nodes[1:]): self.control(a, b)

    def const(self, id, value):
        return self.node(id, 'construct_content', arguments={'append_items': [{'type': 'fixed', 'value': value}]}, dataInputPorts=[])

    def text(self, id, prefix='', suffix=''):
        return self.node(id, 'construct_content', arguments={'append_items': [
            {'type': 'fixed', 'value': prefix}, {'type': 'port', 'port_id': 'value'}, {'type': 'fixed', 'value': suffix}
        ]}, dataInputPorts=['value'])

    def ctx(self, id, kind, type='list-content'):
        return self.node(id, 'context_'+kind, arguments={'value_type': type})

    def call(self, id, function, bindings):
        self.node(id, 'function_call', arguments={'function_id': function})
        for name, source in bindings.items():
            self.data(*source[:2], id, 'function:'+name, source[2] if len(source) == 3 else 'content')
        return id

    def count_text(self, prefix):
        # construct_content accepts content only in the editor. Convert the
        # number through a typed Struct and JSON using existing node contracts.
        self.make_struct(prefix + '_value', 'ToolCallCount', {
            'count': (prefix, 'length-out', 'number'),
        })
        self.node(prefix + '_json', 'struct_to_json', arguments={'value_type': 'struct:ToolCallCount'})
        self.data(prefix + '_value', 'struct-out', prefix + '_json', 'value-in', 'struct:ToolCallCount')
        self.node(prefix + '_text', 'deserialize_json', arguments={'outputs': [{'key': 'count', 'type': 'content'}]})
        self.data(prefix + '_json', 'content-out', prefix + '_text', 'content-in')
        self.chain(prefix, prefix + '_value', prefix + '_json', prefix + '_text')

    def struct(self, name, fields):
        self.doc['metadata']['structs'].append(dict(id=name, name=name, color='#3976A8', fields=[dict(name=n, type=t, required=True) for n,t in fields]))

    def make_struct(self, id, type, bindings):
        self.node(id, 'construct_struct', arguments={'struct_id': type}, dataInputPorts=list(bindings))
        for name, (source, out, kind) in bindings.items(): self.data(source, out, id, name, kind)
        return id

    def get(self, id, type, field, source, out='struct-out'):
        self.node(id, 'struct_get', arguments={'struct_id': type, 'field': field}, dataInputPorts=['struct-in'])
        self.data(source, out, id, 'struct-in', 'struct:'+type)
        return id


def ports(items):
    return [dict(name=name, type=type) for name,type in items]


def build_workflow():
    g = Graph()
    g.struct('ToolCallCount', [('count', 'number')])
    g.struct('CallFunction', [('name', 'content'), ('arguments', 'content')])
    g.struct('ToolCall', [('id', 'content'), ('type', 'content'), ('function', 'struct:CallFunction')])
    g.struct('Assistant', [('role', 'content'), ('content', 'content'), ('reasoning_content', 'content'), ('tool_calls', 'list-struct:ToolCall')])
    g.struct('ToolMessage', [('role', 'content'), ('content', 'content'), ('tool_call_id', 'content')])
    n = g.node
    d = g.data
    p = lambda node, name: (node, 'function:'+name)
    n('in', 'input', workflowPorts=[{'id': 'workflow:task', 'name': 'task', 'type': 'content'}])
    prompt = g.const('system_prompt', 'You are a ReAct assistant. Respond in the user\'s language. Briefly explain your next step and use the provided tools when useful. Every tool call requires the human to reply APPROVE before execution. A rejection is returned as a tool observation. Never claim a proposed call has already run. Ask the user for feedback when no tool is needed. The user can end the run with DONE. Use only the provided tool names and their exact argument schemas.')
    n('system', 'construct_message', arguments={'role': 'system'})
    d(prompt, 'content-out', 'system', 'content-in')
    n('task_message', 'construct_message', arguments={'role': 'user'})
    d('in', 'workflow:task', 'task_message', 'content-in')
    n('initial_history', 'construct_list', arguments={'item_type': 'content', 'initial_value_count': 2}, dataInputPorts=['content-in-0','content-in-1'])
    d('system', 'content-out', 'initial_history', 'content-in-0')
    d('task_message', 'content-out', 'initial_history', 'content-in-1')
    g.ctx('create_history', 'create')
    d('initial_history', 'list-out', 'create_history', 'initial-value', 'list-content')
    g.const('start_token', 'next')
    n('initial_tokens', 'construct_list', arguments={'item_type': 'content', 'initial_value_count': 1}, dataInputPorts=['content-in-0'])
    d('start_token', 'content-out', 'initial_tokens', 'content-in-0')
    g.ctx('create_tokens', 'create')
    d('initial_tokens', 'list-out', 'create_tokens', 'initial-value', 'list-content')
    n('turn_gate', 'while_pop', arguments={'value_type': 'list-content'})
    d('create_tokens', 'context-id', 'turn_gate', 'context-id')
    g.call('call_turn', 'react_turn', {'history_id': ('create_history','context-id'), 'tokens_id': ('create_tokens','context-id')})
    n('out', 'output', workflowPorts=[])
    g.chain('in', prompt, 'system', 'task_message', 'initial_history', 'create_history', 'start_token', 'initial_tokens', 'create_tokens', 'turn_gate')
    g.control('turn_gate', 'call_turn', 'loop-out')
    g.control('call_turn', 'turn_gate', inp='loop-in')
    g.control('turn_gate', 'out')

    # Small reusable functions prevent branch merges in callers.
    fi = g.function('append_history', [('history_id','content'), ('message','content')])
    g.ctx('history_read', 'read'); d(*p(fi,'history_id'), 'history_read','context-id')
    n('history_append','list_append',arguments={'item_type':'content','position':'end'})
    d('history_read','value-out','history_append','list-in','list-content'); d(*p(fi,'message'),'history_append','item-in')
    g.ctx('history_write','write'); d(*p(fi,'history_id'),'history_write','context-id'); d('history_append','list-out','history_write','value-in','list-content')
    g.ret('history_return','append_history'); g.chain(fi,'history_read','history_append','history_write','history_return')

    fi = g.function('queue_turn', [('tokens_id','content')])
    g.ctx('tokens_read','read'); d(*p(fi,'tokens_id'),'tokens_read','context-id')
    g.const('next_token','next')
    n('tokens_append','list_append',arguments={'item_type':'content','position':'end'})
    d('tokens_read','value-out','tokens_append','list-in','list-content'); d('next_token','content-out','tokens_append','item-in')
    g.ctx('tokens_write','write'); d(*p(fi,'tokens_id'),'tokens_write','context-id'); d('tokens_append','list-out','tokens_write','value-in','list-content')
    g.ret('tokens_return','queue_turn'); g.chain(fi,'tokens_read','next_token','tokens_append','tokens_write','tokens_return')

    # Serialize a genuine assistant tool-call message; array elements stay objects.
    fi = g.function('build_assistant', [('content','content'),('reasoning','content'),('calls','list-content')], [('message','content')])
    n('build_count','list_length',arguments={'value_type':'list-content'}); d(*p(fi,'calls'),'build_count','list-in','list-content')
    g.count_text('build_count')
    n('build_route','router',arguments={'branches':[{'id':'none','name':'0'}]}); d('build_count_text','count','build_route','content-in')
    n('build_plain','construct_message',arguments={'role':'assistant'}); d(*p(fi,'content'),'build_plain','content-in')
    g.ret('build_plain_return','build_assistant'); d('build_plain','content-out','build_plain_return','function:message')
    g.control(fi,'build_count'); g.control('build_count_text','build_route'); g.control('build_route','build_plain','none'); g.chain('build_plain','build_plain_return')
    n('build_empty','construct_list',arguments={'item_type':'struct:ToolCall','initial_value_count':0},dataInputPorts=[])
    g.ctx('build_context','create','list-struct:ToolCall'); d('build_empty','list-out','build_context','initial-value','list-struct:ToolCall')
    n('build_each','foreach',arguments={'item_type':'content'}); d(*p(fi,'calls'),'build_each','list-in','list-content')
    n('build_call','json_to_struct',arguments={'value_type':'struct:ToolCall'}); d('build_each','item-out','build_call','content-in')
    g.ctx('build_read','read','list-struct:ToolCall'); d('build_context','context-id','build_read','context-id')
    n('build_append','list_append',arguments={'item_type':'struct:ToolCall','position':'end'})
    d('build_read','value-out','build_append','list-in','list-struct:ToolCall'); d('build_call','value-out','build_append','item-in','struct:ToolCall')
    g.ctx('build_write','write','list-struct:ToolCall'); d('build_context','context-id','build_write','context-id'); d('build_append','list-out','build_write','value-in','list-struct:ToolCall')
    g.ctx('build_final_read','read','list-struct:ToolCall'); d('build_context','context-id','build_final_read','context-id')
    g.const('build_role','assistant')
    g.make_struct('build_message','Assistant',{'role':('build_role','content-out','content'), 'content':(*p(fi,'content'),'content'),
        'reasoning_content':(*p(fi,'reasoning'),'content'), 'tool_calls':('build_final_read','value-out','list-struct:ToolCall')})
    n('build_json','struct_to_json',arguments={'value_type':'struct:Assistant'}); d('build_message','struct-out','build_json','value-in','struct:Assistant')
    g.ret('build_calls_return','build_assistant'); d('build_json','content-out','build_calls_return','function:message')
    g.control('build_route','build_empty','branch$others'); g.chain('build_empty','build_context','build_each')
    g.control('build_each','build_call','loop-out'); g.chain('build_call','build_read','build_append','build_write'); g.control('build_write','build_each',inp='loop-in')
    g.chain('build_each','build_final_read','build_role','build_message','build_json','build_calls_return')

    fi = g.function('record_tool_result', [('history_id','content'),('call_id','content'),('content','content')])
    g.const('result_role','tool')
    g.make_struct('result_message','ToolMessage', {'role':('result_role','content-out','content'), 'content':(*p(fi,'content'),'content'), 'tool_call_id':(*p(fi,'call_id'),'content')})
    n('result_json','struct_to_json',arguments={'value_type':'struct:ToolMessage'}); d('result_message','struct-out','result_json','value-in','struct:ToolMessage')
    g.call('result_save','append_history', {'history_id':p(fi,'history_id'), 'message':('result_json','content-out')})
    g.ret('result_return','record_tool_result'); g.chain(fi,'result_role','result_message','result_json','result_save','result_return')

    fi = g.function('execute_reviewed_tool', [('name','content'),('arguments','content')], [('observation','content')])
    n('execute_tool','json_tool'); d(*p(fi,'name'),'execute_tool','tool-name'); d(*p(fi,'arguments'),'execute_tool','arguments-json')
    g.ret('execute_success','execute_reviewed_tool'); d('execute_tool','result-json','execute_success','function:observation')
    g.ret('execute_error','execute_reviewed_tool'); d('execute_tool','error-json','execute_error','function:observation')
    g.chain(fi,'execute_tool','execute_success'); g.control('execute_tool','execute_error','error-out')

    fi = g.function('review_tool', [('history_id','content'),('stop_id','content'),('call','content')])
    n('review_parse','json_to_struct',arguments={'value_type':'struct:ToolCall'}); d(*p(fi,'call'),'review_parse','content-in')
    g.get('review_id','ToolCall','id','review_parse','value-out')
    g.get('review_function','ToolCall','function','review_parse','value-out')
    g.get('review_name','CallFunction','name','review_function','value-out')
    g.get('review_args','CallFunction','arguments','review_function','value-out')
    g.ctx('review_stop','read','content'); d(*p(fi,'stop_id'),'review_stop','context-id')
    n('review_stop_route','router',arguments={'branches':[{'id':'stopped','name':'DONE'}]}); d('review_stop','value-out','review_stop_route','content-in')
    g.chain(fi,'review_parse','review_id','review_function','review_name','review_args','review_stop','review_stop_route')
    result_bindings = {'history_id':p(fi,'history_id'), 'call_id':('review_id','value-out')}
    g.const('review_skipped','Cancelled: user ended this run; this tool was not executed.')
    g.call('review_skip_save','record_tool_result',dict(result_bindings,content=('review_skipped','content-out')))
    g.ret('review_skip_return','review_tool'); g.control('review_stop_route','review_skipped','stopped'); g.chain('review_skipped','review_skip_save','review_skip_return')
    g.text('review_prompt','Tool request (full call):\n','\nReply APPROVE to execute this exact call; DONE to end; any other reply rejects it and is sent back as feedback.')
    d(*p(fi,'call'),'review_prompt','value')
    n('review_show','output_to_terminal'); d('review_prompt','content-out','review_show','content-in')
    n('review_wait','wait_terminal_event'); n('review_inputs','read_terminal_input')
    n('review_latest','list_get',arguments={'value_type':'list-content','index_source':'fixed','index':-1}); d('review_inputs','list-out','review_latest','list-in','list-content')
    n('review_decision','router',arguments={'branches':[{'id':'approve','name':'APPROVE'},{'id':'done','name':'DONE'}]}); d('review_latest','item-out','review_decision','content-in')
    g.control('review_stop_route','review_prompt','branch$others'); g.chain('review_prompt','review_show','review_wait','review_inputs','review_latest','review_decision')
    g.call('review_execute','execute_reviewed_tool',{'name':('review_name','value-out'),'arguments':('review_args','value-out')})
    n('review_show_result','output_to_terminal'); d('review_execute','function:observation','review_show_result','content-in')
    g.call('review_approved_save','record_tool_result',dict(result_bindings,content=('review_execute','function:observation')))
    g.ret('review_approved_return','review_tool'); g.control('review_decision','review_execute','approve'); g.chain('review_execute','review_show_result','review_approved_save','review_approved_return')
    g.const('review_done','DONE'); g.ctx('review_set_stop','write','content'); d(*p(fi,'stop_id'),'review_set_stop','context-id'); d('review_done','content-out','review_set_stop','value-in')
    g.const('review_cancelled','Cancelled: user ended this run; this tool was not executed.')
    g.call('review_cancel_save','record_tool_result',dict(result_bindings,content=('review_cancelled','content-out')))
    g.ret('review_cancel_return','review_tool'); g.control('review_decision','review_done','done'); g.chain('review_done','review_set_stop','review_cancelled','review_cancel_save','review_cancel_return')
    g.text('review_rejected','Rejected by human; tool was not executed. Feedback: '); d('review_latest','item-out','review_rejected','value')
    g.call('review_reject_save','record_tool_result',dict(result_bindings,content=('review_rejected','content-out')))
    g.ret('review_reject_return','review_tool'); g.control('review_decision','review_rejected','branch$others'); g.chain('review_rejected','review_reject_save','review_reject_return')

    fi = g.function('react_turn', [('history_id','content'),('tokens_id','content')])
    g.ctx('read_for_llm','read'); d(*p(fi,'history_id'),'read_for_llm','context-id')
    n('llm','llm',arguments={'model':'REPLACE_WITH_MODEL_ID','think':True,'tool_calls':True,'tools':['workspace.list_files','workspace.get_file']})
    d('read_for_llm','value-out','llm','messages-in','list-content')
    # Null assistant content is normal for a native tool-call completion.
    g.text('normalize_content'); d('llm','output','normalize_content','value')
    g.call('assistant_message','build_assistant',{'content':('normalize_content','content-out'),'reasoning':('llm','reasoning'),'calls':('llm','tool_calls','list-content')})
    g.call('save_assistant','append_history', {'history_id':p(fi,'history_id'),'message':('assistant_message','function:message')})
    n('turn_count','list_length',name='tool call count',arguments={'value_type':'list-content'}); d('llm','tool_calls','turn_count','list-in','list-content')
    g.count_text('turn_count')
    n('turn_kind','router',arguments={'branches':[{'id':'text','name':'0'}]}); d('turn_count_text','count','turn_kind','content-in')
    g.chain(fi,'read_for_llm','llm','normalize_content','assistant_message','save_assistant','turn_count'); g.control('turn_count_text','turn_kind')
    n('show_proposal','output_to_terminal'); d('normalize_content','content-out','show_proposal','content-in')
    n('wait_for_human','wait_terminal_event'); n('read_human','read_terminal_input')
    n('latest_human','list_get',arguments={'value_type':'list-content','index_source':'fixed','index':-1}); d('read_human','list-out','latest_human','list-in','list-content')
    n('done_gate','router',arguments={'branches':[{'id':'done','name':'DONE'}]}); d('latest_human','item-out','done_gate','content-in')
    g.ret('turn_done','react_turn'); g.control('done_gate','turn_done','done')
    n('observation_message','construct_message',arguments={'role':'user'}); d('latest_human','item-out','observation_message','content-in')
    g.call('save_observation','append_history',{'history_id':p(fi,'history_id'),'message':('observation_message','content-out')})
    g.call('queue_after_text','queue_turn',{'tokens_id':p(fi,'tokens_id')}); g.ret('turn_continue','react_turn')
    g.control('turn_kind','show_proposal','text'); g.chain('show_proposal','wait_for_human','read_human','latest_human','done_gate')
    g.control('done_gate','observation_message','branch$others'); g.chain('observation_message','save_observation','queue_after_text','turn_continue')
    g.const('turn_stop_initial','continue'); g.ctx('turn_stop_context','create','content'); d('turn_stop_initial','content-out','turn_stop_context','initial-value')
    n('turn_calls','foreach',arguments={'item_type':'content'}); d('llm','tool_calls','turn_calls','list-in','list-content')
    g.call('review_each_tool','review_tool',{'history_id':p(fi,'history_id'),'stop_id':('turn_stop_context','context-id'),'call':('turn_calls','item-out')})
    g.ctx('turn_stop_read','read','content'); d('turn_stop_context','context-id','turn_stop_read','context-id')
    n('turn_stop_route','router',arguments={'branches':[{'id':'done','name':'DONE'}]}); d('turn_stop_read','value-out','turn_stop_route','content-in')
    g.ret('turn_tools_done','react_turn'); g.call('queue_after_tools','queue_turn',{'tokens_id':p(fi,'tokens_id')}); g.ret('turn_tools_continue','react_turn')
    g.control('turn_kind','turn_stop_initial','branch$others'); g.chain('turn_stop_initial','turn_stop_context','turn_calls')
    g.control('turn_calls','review_each_tool','loop-out'); g.control('review_each_tool','turn_calls',inp='loop-in')
    g.chain('turn_calls','turn_stop_read','turn_stop_route'); g.control('turn_stop_route','turn_tools_done','done')
    g.control('turn_stop_route','queue_after_tools','branch$others'); g.chain('queue_after_tools','turn_tools_continue')
    return g.doc


if __name__ == '__main__':
    destination = Path(__file__).resolve().parents[1] / 'docs/examples/react-human-in-loop.flow'
    destination.write_text(json.dumps(build_workflow(), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(destination)
