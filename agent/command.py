from tools.qqapi import send_group_msg, send_private_msg
from tools.tool import execute_tool, deepseekBalance, kimiBalance, tavily_search
def commad(group_id,user_id,raw_message):   
    if raw_message.startswith('/'):
        command_text = raw_message[1:].strip()
        if not command_text:
            return
        command_parts = command_text.split(maxsplit=1)
        cmd = command_parts[0]
        if cmd == 'dsB':
            balance = deepseekBalance()
            res = f"{balance}rmb" if balance is not None else "DeepSeek 余额查询失败"
        elif cmd == 'kmB':
            balance = kimiBalance()
            res = f"{balance}rmb" if balance is not None else "Kimi 余额查询失败"
        elif cmd == 'B':
            kimi_balance = kimiBalance()
            deepseek_balance = deepseekBalance()
            res = f'''余额
    kimi{kimi_balance if kimi_balance is not None else "查询失败"}rmb
    deepseek{deepseek_balance if deepseek_balance is not None else "查询失败"}rmb
    '''
        elif cmd == "search":
            query = command_parts[1].strip() if len(command_parts) > 1 else ""
            if not query:
                return
            print(query)
            search_results = tavily_search(query)
            if search_results:
                res = search_results[0].get('title', '')
            else:
                res = "搜索无结果"
        # 将命令结果回复给用户（群消息回群，私聊回私聊）
        if res:
            if group_id:
                send_group_msg(group_id, res)
            else:
                send_private_msg(user_id, res)
        else:
            print("命令无结果:", raw_message)