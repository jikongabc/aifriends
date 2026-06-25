from django.utils.timezone import now
from langchain_core.messages import SystemMessage, HumanMessage

from web.models.friend import SystemPrompt, Message
from web.views.friend.message.memory.graph import MemoryGraph


# 拼接「记忆」类系统提示，作为记忆蒸馏的 SystemMessage。
def create_system_message():
    system_prompts = SystemPrompt.objects.filter(title='记忆').order_by('order_number')
    prompt = ''
    for sp in system_prompts:
        prompt += sp.prompt
    return SystemMessage(prompt)


# 把原始记忆 + 最近 10 轮对话拼成 HumanMessage，供 LLM 蒸馏新记忆。
def create_human_message(friend):
    prompt = f'【原始记忆】\n{friend.memory}\n'
    prompt += f'【最近对话】\n'
    messages = list(Message.objects.filter(friend=friend).order_by('-id')[:10])
    messages.reverse()
    for m in messages:
        prompt += f'user: {m.user_message}\n'
        prompt += f'ai: {m.output}\n'
    return HumanMessage(prompt)


# 调用记忆 graph 蒸馏出新的长期记忆并落库。
def update_memory(friend):
    app = MemoryGraph.create_app()

    inputs = {
        'messages': [
            create_system_message(),
            create_human_message(friend),
        ]
    }

    res = app.invoke(inputs)
    friend.memory = res['messages'][-1].content

    friend.update_time = now()
    friend.save()
