import os,requests,base64,json
def qwen3asr(filename):
    API_KEY = os.getenv("DASHSCOPE_API_KEY", "your-api-key-here")

    url = "https://llm-ixv881gb6xp6wlu9.cn-beijing.maas.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"

    with open(filename, "rb") as audio_file:
        audio_bytes = audio_file.read()
        base64_audio = base64.b64encode(audio_bytes).decode("utf-8")

    # 构造 Data URL（根据实际音频格式调整 MIME 类型）
    # WAV 格式: data:audio/wav;base64,{base64_audio}
    # MP3 格式: data:audio/mpeg;base64,{base64_audio}
    data_url = f"data:audio/wav;base64,{base64_audio}"

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "X-DashScope-SSE": "disable"
    }

    payload = {
        "model": "qwen-audio-3.0-asr-flash",
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": data_url
                            }
                        }
                    ]
                }
            ]
        },
        "parameters": {
            "format": "wav",
            "sample_rate": "16000"
        }
    }

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()
res=qwen3asr("/app/downloaded/0a37a68ddc7d56f5313fc0ed25c09e05a70b50595c9ed5811f85e678096694d3.mp3")
print(res)
json.dump(res,open("1.json","w"),ensure_ascii=False)