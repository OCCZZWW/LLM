import os
import shutil
import stat
import json
import subprocess
import requests

# ---------------------------------------------------------------------------
# 配置加载 —— 直接对接 Ollama 的 OpenAI 兼容 API
# ---------------------------------------------------------------------------
OLLAMA_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen3-vl:4b-instruct"

url = f"{OLLAMA_URL.rstrip('/')}/v1/chat/completions"
headers = {"Content-Type": "application/json"}

# ---------------------------------------------------------------------------
# 工具定义 (OpenAI function calling 格式)
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "getDate",
            "description": "获取当前电脑的日期和时间。当用户询问今天几号、现在几点、当前日期时间等问题时调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "isLeapYear",
            "description": "判断某一年是否是闰年。当用户询问某一年是不是闰年、当年是否是闰年等问题时调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {
                        "type": "integer",
                        "description": "要判断的年份，例如 2024",
                    }
                },
                "required": ["year"],
            },
        },
    },
    # ---- 文件操作工具 ----
    {
        "type": "function",
        "function": {
            "name": "getCwd",
            "description": "获取当前工作目录的绝对路径。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listDir",
            "description": "列出指定目录下的所有文件和子目录。默认列出当前工作目录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "目录路径，留空则使用当前工作目录",
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "是否递归列出所有子目录，默认 false",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "getFileType",
            "description": "获取指定文件的类型信息（扩展名、MIME 类型、是否为目录等）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件或目录的路径"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "readFile",
            "description": "读取指定纯文本文件的内容。仅支持 UTF-8 / GBK 等文本编码的文件，二进制文件无法读取。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "encoding": {
                        "type": "string",
                        "description": "文件编码，默认 utf-8。中文 Windows 文件可尝试 gbk",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "createFile",
            "description": "根据指定路径创建新文件，可选择同时写入初始内容。如果文件已存在将被覆盖。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "要创建的文件路径"},
                    "content": {
                        "type": "string",
                        "description": "文件初始内容，留空则创建空文件",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "writeFile",
            "description": "编辑指定文件的内容。仅支持纯文本文件。可选择覆盖原内容或追加到末尾。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "要编辑的文件路径"},
                    "content": {"type": "string", "description": "要写入的内容"},
                    "append": {
                        "type": "boolean",
                        "description": "true=追加到末尾，false=覆盖原内容。默认 false",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "createDir",
            "description": "创建新目录。如果父目录不存在会一并创建（类似 mkdir -p）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "要创建的目录路径"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deleteDir",
            "description": "删除指定目录。若目录非空需确认后调用，非空目录会被连同内部文件一起删除。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "要删除的目录路径"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deleteFile",
            "description": "删除指定的文件。只能删除文件，不能删除目录。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "要删除的文件路径"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "renamePath",
            "description": "重命名文件或目录。目标路径必须位于同一父目录下，不能跨磁盘移动。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "原路径"},
                    "new_name": {"type": "string", "description": "新文件名或新目录名（不含父目录路径）"},
                },
                "required": ["path", "new_name"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# 工具实现
# ---------------------------------------------------------------------------
def get_date() -> str:
    """
    调用 Windows 本地 `date /t` 和 `time /t` 命令获取日期和时间。
    在非 Windows 环境下自动 fallback 到 Python datetime。
    """
    try:
        date_res = subprocess.run(
            ["cmd", "/c", "date", "/t"],
            capture_output=True, text=True, timeout=5,
        )
        time_res = subprocess.run(
            ["cmd", "/c", "time", "/t"],
            capture_output=True, text=True, timeout=5,
        )
        date_str = date_res.stdout.strip()
        time_str = time_res.stdout.strip()
        return f"当前日期: {date_str}\n当前时间: {time_str}"
    except FileNotFoundError:
        # 非 Windows 环境 fallback
        import datetime
        now = datetime.datetime.now()
        return now.strftime("当前日期: %Y/%m/%d\n当前时间: %H:%M:%S")
    except subprocess.TimeoutExpired:
        return "[错误] 调用本地 date 命令超时"


def is_leap_year(year: int) -> str:
    """
    判断给定年份是否是闰年。
    规则：能被 4 整除但不能被 100 整除，或者能被 400 整除。
    """
    try:
        y = int(year)
    except (TypeError, ValueError):
        return f"[错误] 无法解析年份: {year}"

    if y < 1:
        return f"[错误] 年份无效: {y}"

    leap = (y % 4 == 0 and y % 100 != 0) or (y % 400 == 0)
    if leap:
        return f"{y} 年是闰年（2 月有 29 天）"
    else:
        return f"{y} 年不是闰年（2 月有 28 天）"


# ---------------------------------------------------------------------------
# 文件操作工具实现
# ---------------------------------------------------------------------------

def _resolve(path: str | None) -> str:
    """把相对路径解析为绝对路径，None 或空串返回 cwd。"""
    if not path:
        return os.getcwd()
    return os.path.abspath(os.path.expanduser(path))


def _is_text_file(path: str) -> bool:
    """简单判断是否为文本文件（尝试 utf-8 / gbk 解码）。"""
    try:
        with open(path, "rb") as f:
            raw = f.read(4096)
        # 空文件视为文本
        if not raw:
            return True
        raw.decode("utf-8")
        return True
    except (UnicodeDecodeError, OSError):
        pass
    try:
        raw.decode("gbk")
        return True
    except (UnicodeDecodeError, OSError):
        return False


def get_cwd() -> str:
    path = os.getcwd()
    return f"当前工作目录: {path}"


def list_dir(path: str | None = None, recursive: bool = False) -> str:
    target = _resolve(path)
    if not os.path.exists(target):
        return f"[错误] 路径不存在: {target}"
    if not os.path.isdir(target):
        return f"[错误] 不是目录: {target}"

    lines = [f"目录: {target}"]
    if recursive:
        for root, dirs, files in os.walk(target):
            rel = os.path.relpath(root, target)
            prefix = "" if rel == "." else f"[{rel}] "
            for d in sorted(dirs):
                lines.append(f"{prefix}{d}/")
            for f in sorted(files):
                full = os.path.join(root, f)
                size = os.path.getsize(full)
                lines.append(f"{prefix}{f}  ({size} bytes)")
    else:
        entries = sorted(os.listdir(target))
        for name in entries:
            full = os.path.join(target, name)
            if os.path.isdir(full):
                lines.append(f"{name}/  <DIR>")
            else:
                size = os.path.getsize(full)
                lines.append(f"{name}  ({size} bytes)")
    return "\n".join(lines)


def get_file_type(path: str) -> str:
    target = _resolve(path)
    if not os.path.exists(target):
        return f"[错误] 路径不存在: {target}"

    import mimetypes

    lines = [f"路径: {target}"]
    if os.path.isdir(target):
        lines.append("类型: 目录 (directory)")
    elif os.path.isfile(target):
        ext = os.path.splitext(target)[1].lower()
        mime, _ = mimetypes.guess_type(target)
        size = os.path.getsize(target)
        lines.append(f"类型: 普通文件 (file)")
        lines.append(f"扩展名: {ext or '(无)'}")
        lines.append(f"MIME: {mime or '未知'}")
        lines.append(f"大小: {size} bytes")
        lines.append(f"是否文本: {'是' if _is_text_file(target) else '否（二进制）'}")
    else:
        lines.append("类型: 其他（符号链接/特殊文件）")
    return "\n".join(lines)


def read_file(path: str, encoding: str | None = None) -> str:
    target = _resolve(path)
    if not os.path.exists(target):
        return f"[错误] 文件不存在: {target}"
    if not os.path.isfile(target):
        return f"[错误] 不是文件: {target}"

    encodings = [encoding] if encoding else ["utf-8", "gbk", "utf-16"]
    last_err = None
    for enc in encodings:
        try:
            with open(target, "r", encoding=enc) as f:
                content = f.read()
            # 如果内容过长，截取前 8KB 并提示
            if len(content) > 8192:
                return (
                    f"[文件过大，仅显示前 8192 字符]\n"
                    f"--- {target} (encoding={enc}) ---\n"
                    f"{content[:8192]}\n... [已截断]"
                )
            return f"--- {target} (encoding={enc}) ---\n{content}"
        except UnicodeDecodeError as e:
            last_err = e
            continue
        except OSError as e:
            return f"[错误] 读取失败: {e}"
    return f"[错误] 无法解码文件（尝试了 {encodings}）: {last_err}"


def create_file(path: str, content: str = "") -> str:
    target = _resolve(path)
    parent = os.path.dirname(target)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)
    try:
        with open(target, "w", encoding="utf-8") as f:
            f.write(content or "")
        size = os.path.getsize(target)
        return f"文件已创建: {target}  ({size} bytes)"
    except OSError as e:
        return f"[错误] 创建失败: {e}"


def write_file(path: str, content: str, append: bool = False) -> str:
    target = _resolve(path)
    if not os.path.exists(target):
        return f"[错误] 文件不存在，请先用 createFile 创建: {target}"
    if not os.path.isfile(target):
        return f"[错误] 不是文件: {target}"
    if not _is_text_file(target):
        return f"[错误] 该文件为二进制文件，不支持文本写入: {target}"

    mode = "a" if append else "w"
    try:
        with open(target, mode, encoding="utf-8") as f:
            f.write(content)
        size = os.path.getsize(target)
        action = "追加" if append else "覆盖"
        return f"已{action}写入: {target}  ({size} bytes)"
    except OSError as e:
        return f"[错误] 写入失败: {e}"


def create_dir(path: str) -> str:
    target = _resolve(path)
    try:
        os.makedirs(target, exist_ok=True)
        return f"目录已创建: {target}"
    except OSError as e:
        return f"[错误] 创建目录失败: {e}"


def delete_dir(path: str) -> str:
    target = _resolve(path)
    if not os.path.exists(target):
        return f"[错误] 路径不存在: {target}"
    if not os.path.isdir(target):
        return f"[错误] 不是目录: {target}"

    # 防止删除根目录或重要系统目录（简单保护）
    dangerous = {"C:\\", "C:/", "/"}
    if target.rstrip("\\/") in dangerous:
        return f"[错误] 拒绝删除危险路径: {target}"

    try:
        # 统计将被删除的内容
        file_count = 0
        dir_count = 0
        for root, dirs, files in os.walk(target):
            file_count += len(files)
            dir_count += len(dirs)
        shutil.rmtree(target)
        return f"目录已删除: {target}  (含 {dir_count} 个子目录, {file_count} 个文件)"
    except OSError as e:
        return f"[错误] 删除失败: {e}"


def delete_file(path: str) -> str:
    target = _resolve(path)
    if not os.path.exists(target):
        return f"[错误] 文件不存在: {target}"
    if not os.path.isfile(target):
        return f"[错误] 不是文件，无法用 deleteFile 删除目录: {target}"
    try:
        os.remove(target)
        return f"文件已删除: {target}"
    except OSError as e:
        return f"[错误] 删除失败: {e}"


def rename_path(path: str, new_name: str) -> str:
    target = _resolve(path)
    if not os.path.exists(target):
        return f"[错误] 路径不存在: {target}"
    if not new_name or os.sep in new_name or (os.altsep and os.altsep in new_name):
        return f"[错误] new_name 只能是名称，不能包含路径分隔符: {new_name}"

    parent = os.path.dirname(target)
    new_path = os.path.join(parent, new_name)
    if os.path.exists(new_path):
        return f"[错误] 目标已存在: {new_path}"
    try:
        os.rename(target, new_path)
        kind = "目录" if os.path.isdir(new_path) else "文件"
        return f"{kind}已重命名: {target} -> {new_path}"
    except OSError as e:
        return f"[错误] 重命名失败: {e}"


# 工具名 -> 函数 的映射
TOOL_MAP = {
    "getDate": get_date,
    "isLeapYear": is_leap_year,
    # 文件操作
    "getCwd": get_cwd,
    "listDir": list_dir,
    "getFileType": get_file_type,
    "readFile": read_file,
    "createFile": create_file,
    "writeFile": write_file,
    "createDir": create_dir,
    "deleteDir": delete_dir,
    "deleteFile": delete_file,
    "renamePath": rename_path,
}


# ---------------------------------------------------------------------------
# 核心：发送一次请求到 Ollama OpenAI 兼容端点，流式解析文本和 tool_calls
# ---------------------------------------------------------------------------
def stream_chat(messages: list, tools: list | None = None):
    """
    发送一轮 messages 给 Ollama 并流式打印回复。
    返回: (full_reply_text, tool_calls_list)
    """
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": True,
    }
    if tools:
        payload["tools"] = tools

    try:
        resp = requests.post(url, headers=headers, json=payload, stream=True, timeout=120)
        resp.raise_for_status()
    except requests.ConnectionError:
        print("[错误] 无法连接 Ollama，请确认 Ollama 已启动 (http://localhost:11434)")
        return "", []
    except requests.RequestException as e:
        print(f"[错误] 请求失败: {e}")
        return "", []

    full_reply = ""
    tc_buffer: dict[int, dict] = {}

    for line_bytes in resp.iter_lines():
        if not line_bytes:
            continue
        line_str = line_bytes.decode("utf-8").strip()
        if not line_str.startswith("data: "):
            continue
        json_str = line_str[6:]
        if json_str == "[DONE]":
            print()
            break

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            continue

        choices = data.get("choices", [])
        if not choices:
            continue
        delta = choices[0].get("delta", {})

        # 1) 文本增量
        content = delta.get("content")
        if content:
            full_reply += content
            print(content, end="", flush=True)

        # 2) tool_calls 增量 (OpenAI 流式格式)
        for tc in delta.get("tool_calls", []):
            idx = tc.get("index", 0)
            buf = tc_buffer.setdefault(idx, {"id": "", "name": "", "arguments": ""})
            if tc.get("id"):
                buf["id"] += tc["id"]
            fn = tc.get("function", {})
            if fn.get("name"):
                buf["name"] += fn["name"]
            if fn.get("arguments"):
                buf["arguments"] += fn["arguments"]

    tool_calls = []
    for idx in sorted(tc_buffer.keys()):
        buf = tc_buffer[idx]
        if buf["name"]:
            tool_calls.append({
                "id": buf["id"] or f"call_{idx}",
                "type": "function",
                "function": {
                    "name": buf["name"],
                    "arguments": buf["arguments"] or "{}",
                },
            })

    return full_reply, tool_calls


# ---------------------------------------------------------------------------
# 主循环
# ---------------------------------------------------------------------------
messages = []  # OpenAI 格式的消息历史
try:
    while True:
        q = input("请输入问题: ").strip()
        if not q:
            continue

        messages.append({"role": "user", "content": q})
        assistant_text, tool_calls = stream_chat(messages, tools=TOOLS)

        if tool_calls:
            messages.append({
                "role": "assistant",
                "content": assistant_text or None,
                "tool_calls": tool_calls,
            })

            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                try:
                    fn_args = json.loads(tc["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    fn_args = {}

                print(f"\n[系统] 正在调用工具: {fn_name}({fn_args})")
                tool_result = TOOL_MAP.get(fn_name, lambda: f"未知工具: {fn_name}")(**fn_args)
                print(f"[系统] 工具返回:\n{tool_result}\n")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": fn_name,
                    "content": tool_result,
                })

            print("Assistant: ", end="", flush=True)
            final_text, _ = stream_chat(messages, tools=None)
            messages.append({"role": "assistant", "content": final_text})
        else:
            messages.append({"role": "assistant", "content": assistant_text})

except KeyboardInterrupt:
    print("\n对话已结束")
