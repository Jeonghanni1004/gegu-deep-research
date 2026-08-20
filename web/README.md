# Deep Research Demo（单股票）

浏览器产品层：读取已冻结的 Final Analyst grounded artifacts，**默认不调用任何 LLM**。

## 启动

```powershell
cd C:\Users\86137\ashare-deep-research
pip install -r requirements-web.txt
$env:PYTHONPATH = "src"
python web\server.py
```

浏览器打开：http://127.0.0.1:8765

## 行为说明

- `POST /api/research/start` 仅支持 `mode=replay`
- 完整 E2E 产物目前：`600519`（贵州茅台）
- 前端动画是对已有 pipeline 的回放，不重新跑 Agent，不改写判断

## 自检（无 API）

```powershell
$env:PYTHONPATH = "src"
python -m tests.test_demo_web
```
