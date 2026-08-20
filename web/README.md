# 个股 Deep Research · Demo（前端工作台）

浏览器产品层：针对**单只个股**回放已冻结的 grounded artifacts，**默认不调用任何 LLM**。

前端静态资源：`web/static/`（`index.html` / `app.js` / `styles.css`）。

## 启动

```powershell
cd ashare-deep-research
pip install -r requirements-web.txt
$env:PYTHONPATH = "src;web"
python web\server.py
```

浏览器打开：http://127.0.0.1:8765

## 当前可回放标的

- `600519` 贵州茅台
- `601127` 赛力斯

## Brief 页会看到什么

- **当前最值得研究的变化**（Insight，非模板投资结论）
- **Research Signals** Top 3–5
- **Fundamental Picture** / **External Signals**
- **Where They Might Connect**
- 可跳转到 Evidence / Debate / Final Judgment

> 改了 Python 展示层后需重启 `server.py`；前端静态文件建议硬刷新。

## 行为说明

- `POST /api/research/start` 仅支持 `mode=replay`
- 前端动画是对已有 pipeline 的回放，不重新跑 Agent，不改写 Final Analyst 判断
- Insight Layer（`insight_layer.py`）只做呈现层排序与组织

## 自检（无 API）

```powershell
$env:PYTHONPATH = "src;web"
python -m tests.test_demo_web
```
