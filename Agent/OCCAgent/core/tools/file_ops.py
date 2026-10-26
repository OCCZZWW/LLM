"""本地文件系统工具（10 个）。

设计要点：
- 所有相对路径统一由 _resolve 解析为绝对路径；
- 文本读写前用 _is_text_file 拦截二进制文件；
- 删除目录时保护根目录等危险路径。
"""

from __future__ import annotations

import mimetypes
import os
import shutil

from .base import ToolRegistry

MAX_READ_CHARS = 8192
DANGEROUS_DIRS = {"C:\\", "C:/", "/"}


def _resolve(path: str | None) -> str:
    """把相对路径解析为绝对路径；None 或空串返回当前工作目录。"""
    if not path:
        return os.getcwd()
    return os.path.abspath(os.path.expanduser(path))


def _is_text_file(path: str) -> bool:
    """读取文件头部，尝试 utf-8 / gbk 解码判断是否为文本。"""
    try:
        with open(path, "rb") as f:
            raw = f.read(4096)
    except OSError:
        return False
    if not raw:
        return True
    try:
        raw.decode("utf-8")
        return True
    except UnicodeDecodeError:
        pass
    try:
        raw.decode("gbk")
        return True
    except UnicodeDecodeError:
        return False


def register_file_tools(registry: ToolRegistry) -> None:
    """注册全部文件操作工具。"""

    # ------------------------------------------------------------------
    # 查看类
    # ------------------------------------------------------------------
    @registry.tool(
        name="getCwd",
        description="获取当前工作目录的绝对路径。",
    )
    def get_cwd() -> str:
        return f"当前工作目录: {os.getcwd()}"

    @registry.tool(
        name="listDir",
        description="列出指定目录下的所有文件和子目录。默认列出当前工作目录。",
        parameters={
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
    )
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
                for name in sorted(dirs):
                    lines.append(f"{prefix}{name}/")
                for name in sorted(files):
                    size = os.path.getsize(os.path.join(root, name))
                    lines.append(f"{prefix}{name}  ({size} bytes)")
        else:
            for name in sorted(os.listdir(target)):
                full = os.path.join(target, name)
                if os.path.isdir(full):
                    lines.append(f"{name}/  <DIR>")
                else:
                    lines.append(f"{name}  ({os.path.getsize(full)} bytes)")
        return "\n".join(lines)

    @registry.tool(
        name="getFileType",
        description="获取指定文件的类型信息（扩展名、MIME 类型、是否为目录等）。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件或目录的路径"},
            },
            "required": ["path"],
        },
    )
    def get_file_type(path: str) -> str:
        target = _resolve(path)
        if not os.path.exists(target):
            return f"[错误] 路径不存在: {target}"

        lines = [f"路径: {target}"]
        if os.path.isdir(target):
            lines.append("类型: 目录 (directory)")
        elif os.path.isfile(target):
            ext = os.path.splitext(target)[1].lower()
            mime, _ = mimetypes.guess_type(target)
            lines.extend(
                [
                    "类型: 普通文件 (file)",
                    f"扩展名: {ext or '(无)'}",
                    f"MIME: {mime or '未知'}",
                    f"大小: {os.path.getsize(target)} bytes",
                    f"是否文本: {'是' if _is_text_file(target) else '否（二进制）'}",
                ]
            )
        else:
            lines.append("类型: 其他（符号链接/特殊文件）")
        return "\n".join(lines)

    @registry.tool(
        name="readFile",
        description="读取指定纯文本文件的内容。仅支持 UTF-8 / GBK 等文本编码的文件，二进制文件无法读取。",
        parameters={
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
    )
    def read_file(path: str, encoding: str | None = None) -> str:
        target = _resolve(path)
        if not os.path.exists(target):
            return f"[错误] 文件不存在: {target}"
        if not os.path.isfile(target):
            return f"[错误] 不是文件: {target}"

        encodings = [encoding] if encoding else ["utf-8", "gbk", "utf-16"]
        last_error: Exception | None = None
        for enc in encodings:
            try:
                with open(target, "r", encoding=enc) as f:
                    content = f.read()
            except UnicodeDecodeError as exc:
                last_error = exc
                continue
            except OSError as exc:
                return f"[错误] 读取失败: {exc}"

            if len(content) > MAX_READ_CHARS:
                return (
                    f"[文件过大，仅显示前 {MAX_READ_CHARS} 字符]\n"
                    f"--- {target} (encoding={enc}) ---\n"
                    f"{content[:MAX_READ_CHARS]}\n... [已截断]"
                )
            return f"--- {target} (encoding={enc}) ---\n{content}"
        return f"[错误] 无法解码文件（尝试了 {encodings}）: {last_error}"

    # ------------------------------------------------------------------
    # 创建类
    # ------------------------------------------------------------------
    @registry.tool(
        name="createFile",
        description="根据指定路径创建新文件，可选择同时写入初始内容。如果文件已存在将被覆盖。",
        parameters={
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
    )
    def create_file(path: str, content: str = "") -> str:
        target = _resolve(path)
        parent = os.path.dirname(target)
        if parent and not os.path.exists(parent):
            os.makedirs(parent, exist_ok=True)
        try:
            with open(target, "w", encoding="utf-8") as f:
                f.write(content or "")
            return f"文件已创建: {target}  ({os.path.getsize(target)} bytes)"
        except OSError as exc:
            return f"[错误] 创建失败: {exc}"

    @registry.tool(
        name="createDir",
        description="创建新目录。如果父目录不存在会一并创建（类似 mkdir -p）。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要创建的目录路径"},
            },
            "required": ["path"],
        },
    )
    def create_dir(path: str) -> str:
        target = _resolve(path)
        try:
            os.makedirs(target, exist_ok=True)
            return f"目录已创建: {target}"
        except OSError as exc:
            return f"[错误] 创建目录失败: {exc}"

    # ------------------------------------------------------------------
    # 修改类
    # ------------------------------------------------------------------
    @registry.tool(
        name="writeFile",
        description="编辑指定文件的内容。仅支持纯文本文件。可选择覆盖原内容或追加到末尾。",
        parameters={
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
    )
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
            action = "追加" if append else "覆盖"
            return f"已{action}写入: {target}  ({os.path.getsize(target)} bytes)"
        except OSError as exc:
            return f"[错误] 写入失败: {exc}"

    @registry.tool(
        name="renamePath",
        description="重命名文件或目录。目标路径必须位于同一父目录下，不能跨磁盘移动。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "原路径"},
                "new_name": {
                    "type": "string",
                    "description": "新文件名或新目录名（不含父目录路径）",
                },
            },
            "required": ["path", "new_name"],
        },
    )
    def rename_path(path: str, new_name: str) -> str:
        target = _resolve(path)
        if not os.path.exists(target):
            return f"[错误] 路径不存在: {target}"
        if not new_name or os.sep in new_name or (os.altsep and os.altsep in new_name):
            return f"[错误] new_name 只能是名称，不能包含路径分隔符: {new_name}"

        new_path = os.path.join(os.path.dirname(target), new_name)
        if os.path.exists(new_path):
            return f"[错误] 目标已存在: {new_path}"
        try:
            os.rename(target, new_path)
            kind = "目录" if os.path.isdir(new_path) else "文件"
            return f"{kind}已重命名: {target} -> {new_path}"
        except OSError as exc:
            return f"[错误] 重命名失败: {exc}"

    # ------------------------------------------------------------------
    # 删除类
    # ------------------------------------------------------------------
    @registry.tool(
        name="deleteDir",
        description="删除指定目录。若目录非空需确认后调用，非空目录会被连同内部文件一起删除。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要删除的目录路径"},
            },
            "required": ["path"],
        },
    )
    def delete_dir(path: str) -> str:
        target = _resolve(path)
        if not os.path.exists(target):
            return f"[错误] 路径不存在: {target}"
        if not os.path.isdir(target):
            return f"[错误] 不是目录: {target}"
        if target.rstrip("\\/") in DANGEROUS_DIRS:
            return f"[错误] 拒绝删除危险路径: {target}"

        file_count = 0
        dir_count = 0
        for _, dirs, files in os.walk(target):
            file_count += len(files)
            dir_count += len(dirs)
        try:
            shutil.rmtree(target)
            return f"目录已删除: {target}  (含 {dir_count} 个子目录, {file_count} 个文件)"
        except OSError as exc:
            return f"[错误] 删除失败: {exc}"

    @registry.tool(
        name="deleteFile",
        description="删除指定的文件。只能删除文件，不能删除目录。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "要删除的文件路径"},
            },
            "required": ["path"],
        },
    )
    def delete_file(path: str) -> str:
        target = _resolve(path)
        if not os.path.exists(target):
            return f"[错误] 文件不存在: {target}"
        if not os.path.isfile(target):
            return f"[错误] 不是文件，无法用 deleteFile 删除目录: {target}"
        try:
            os.remove(target)
            return f"文件已删除: {target}"
        except OSError as exc:
            return f"[错误] 删除失败: {exc}"
