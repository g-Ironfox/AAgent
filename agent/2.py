def review(e):
        application = e['payload']['application']
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "review",
                    "description": "请给出审查结果",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "permit": {"type": "boolean", "description": "是否放行"},
                            "detail": {"type": "string", "description": "理由"}
                        },
                        "required": ["permit"]
                    }
                }
            },
        ]

        system_prompt = settings['system_prompt'].replace("{{TARGET_USER_ID}}", TARGET_USER_ID).replace("{{BOT_ID}}", BOT_ID)
        system_prompt = system_prompt.replace("{{SYSTEM_DOCUMENTS_PROMPT}}",system_documents_prompt())

        h=get_recent_history(limit=int(settings.get('max_context_count')))[::-1]
        messages = [
            {"role": "system", "content": system_prompt},
        ]

        context=[]

        for i in h:
            payload=i.get('payload')
            if i['event_type']=='qq':
                if i['payload']["post_type"]=="message":
                    if (not payload['group_id']) and str(payload['user_id']) == str(TARGET_USER_ID):
                        
                        context.append(f"<Command source='qq'>{payload['raw_message']}</Command>")
                    else:
                        #context.append(f"<QQ event='msg' type='group' group_id={payload['group_id']}  sender_id={payload['user_id']}>{payload['raw_message']}</QQ>")
                        pass
                #if i['payload']["post_type"]=="send" and str(i['payload']["target_id"]) == str(TARGET_USER_ID):
                #    context.append(f"<QQ event='msg' sender_id=self>{payload['raw_message']}</QQ>")

            if i['event_type']=='tool_return':
                context.append(f"""<tool>
<tool_name>{payload['tool']}</tool_name>
<tool_args>{json.dumps(payload['args'],ensure_ascii=False)}</tool_args>
<tool_result>{payload['result']}</tool_result>
</tool>""")
            if i['event_type']=='terminal':
                context.append(f"<Command source='terminal'>{payload['message']}</Command>")

            if i['event_type']=='response':
                if payload.get("content"):
                    context.append(f"<response target='terminal'>{payload['content']}</response>")

            if i['event_type']=='application':
                task_content=f"""<application>
                <sub_agent_name>{payload.get("sub_agent_name")}</sub_agent_name>
                <apply_tool_name>{payload.get("tool_name")}</apply_tool_name>
                <apply_tool_arguments>{payload.get("arguments")}</apply_tool_arguments>
                """
                context.append(task_content)
        messages.append({"role":"user","content":"\n".join(context)})

        if task_content:
            messages.append({"role":"user","content":task_content})
        content,reasoning,tool_calls=chat_with_deepseek(messages,tools=tools)
        if tool_calls and tool_calls[0]['function'] == "review":
            if json.loads(tool_calls[0]['arguments']).get('permit'):
                e = {
                    'event_type': ,
                    'payload':{
                        "application":
                    }
                }
        print(tool_calls)


    def application(e):
        p = e.get("payload")
        task_content=f"""<application>
<sub_agent_name>{p.get("sub_agent_name")}</sub_agent_name>
<apply_tool_name>{p.get("tool_name")}</apply_tool_name>
<apply_tool_arguments>{p.get("arguments")}</apply_tool_arguments>
批准or驳回? 若批准请直接执行,若不批准请直接给出驳回理由。请调用工具。
"""
        e={
            "event_type":"task",
            "payload":{
                "task_content":task_content,
                "return_queue":p.get("queue_name")
            }
        }
        publish_to_queue(MAIN_AGENT_QUEUE_NAME,e)