# 深研 · AI 智能投研助手（前端）

浏览器产品层：对话形态的投研 Agent 工作台。

前端静态资源：`web/static/`（`index.html` / `app.js` / `styles.css`）。

## 启动

```powershell
cd ashare-deep-research
pip install -r requirements-web.txt
$env:PYTHONPATH = "src;web"
python web\server.py
```

浏览器打开：http://127.0.0.1:8765

## 产品动线

1. **首页**：左侧历史对话（可收起/展开）；中间问候语 + 示例提问；底部对话框（文本 / 语音 / 附件 / 图片）
2. **对话中**：助手回复可内嵌链接与证据锚点；消息下方提供「追问建议」与「建议回答」
3. **分析文档**：右侧打开后中间对话框仍保留；文档内划词会自动写入底部引用条，右键可复制

## 与后端的关系

- 普通问题：前端模拟助手回复，并生成可编辑分析文档（本地演示）
- 提到已有 artifacts 标的（如 `600519` / `601127`）：会请求 `GET /api/research/{symbol}`，把 grounded 研究写入右侧文档
- 历史对话保存在浏览器 `localStorage`

## 自检（无 API）

```powershell
$env:PYTHONPATH = "src;web"
python -m tests.test_demo_web
```
