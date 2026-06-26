from web.views.create.character.voice.custom.client import call_voice_api


# 列出已复刻的自定义音色。
def list_voice():
    data = {
        "model": "voice-enrollment",
        "input": {"action": "list_voice", "page_size": 100, "page_index": 0},
    }
    return call_voice_api(data)
