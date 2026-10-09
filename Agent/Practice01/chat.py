import configparser
import json
import requests

config = configparser.ConfigParser()
config.read("config.ini")
cfg = config["llm"]

api_key = cfg["api_key"].strip().strip('"').strip("'")
base_url = cfg["base_url"].strip().strip('"').strip("'")
slug = cfg["workspace_slug"].strip()

url = f"{base_url.rstrip('/')}/v1/workspace/{slug}/stream-chat"
headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

history = []
try:
    while True:
        q = input("请输入问题: ")
        # AnythingLLM原生接口不需要手动传OpenAI格式的history，它会自动维护会话上下文
        # 如果要手动维护历史，用它要求的正确格式
        payload = {
            "message": q,
            "mode": "chat",
            "history": history
        }
        resp = requests.post(url, headers=headers, json=payload, stream=True)
        full_reply = ""
        # 去掉decode_unicode参数，手动控制解码避免乱码
        for line_bytes in resp.iter_lines():
            if not line_bytes:
                continue
            # 手动用utf-8解码，彻底解决中文乱码
            line_str = line_bytes.decode("utf-8").strip()
            if not line_str.startswith("data: "):
                continue
            json_str = line_str[6:]
            if json_str == "[DONE]":
                print()
                break
            # 加异常捕获，非法行直接跳过不崩溃
            try:
                data = json.loads(json_str)
                # 兼容AnythingLLM不同版本的返回字段
                if "textResponse" in data:
                    chunk = data["textResponse"]
                    full_reply += chunk
                    print(chunk, end="", flush=True)
                # 部分版本返回的是text字段，做兼容兜底
                elif "text" in data:
                    chunk = data["text"]
                    full_reply += chunk
                    print(chunk, end="", flush=True)
            except json.JSONDecodeError:
                continue

        # 正确追加对话历史
        history.append({"role": "user", "content": q})
        history.append({"role": "assistant", "content": full_reply})

except KeyboardInterrupt:
    print("\n对话已结束")
