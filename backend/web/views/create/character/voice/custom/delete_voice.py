from web.views.create.character.voice.custom.client import call_voice_api


# 删除指定 voice_id 的自定义音色。
def delete_voice(voice_id):
    data = {
        "model": "voice-enrollment",
        "input": {
            "action": "delete_voice",
            "voice_id": voice_id,
        },
    }
    return call_voice_api(data)
