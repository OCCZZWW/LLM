# AnythingLLM 文档上传页

一个单文件网页，向 AnythingLLM 上传文档并自动向量化。

## 使用

直接双击 `upload.html` 或在浏览器打开即可。

- **AnythingLLM**: `http://localhost:3001`
- **API**: `POST /api/v1/document/upload`
- **工作区**: 第一个工作区（我的工作区）
- **Key**: 已硬编码在 HTML 里

## 注意

AnythingLLM 默认开启 CORS（允许所有来源），所以 `file://` 协议下的浏览器也能直连。如果被挡，把 HTML 放到任意 HTTP 服务（如 `python -m http.server`）再打开。
