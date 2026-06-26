from web.views.create.character.voice.custom.client import call_voice_api


# 用音频 URL 复刻一个新音色，返回 voice_id。
def create_voice(voice_url, prefix):
    data = {
        "model": "voice-enrollment",
        "input": {
            "action": "create_voice",
            "target_model": "cosyvoice-v3-flash",
            "prefix": prefix,
            "url": voice_url,
        },
    }
    return call_voice_api(data)
