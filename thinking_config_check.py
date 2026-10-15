#!/usr/bin/env python3
"""思考档配置校验+自动补回。

背景：全局 thinking_level 设置可能冲掉各模型的 generate_kwargs 锁。
平台卡片重同步可能再抹 gk，本脚本核对各模型终态，丢了走 API PUT 补回。

输出标记：
- 校验通过            → 静默
- REPAIRED:<明细>     → 有 gk 被抹/改，已自动补回
- NOTES:<明细>        → 含 THINKING_LEVEL_DRIFT 等告警
- ERROR:<明细>        → 校验本身失败（退出码 1）

环境变量：
  QWENPAW_API        daemon API 地址（默认 http://127.0.0.1:8088）
  QWENPAW_PROVIDER   provider ID（默认 <PLATFORM_NAME>-platform）
  QWENPAW_WORKSPACE  workspace 目录（默认 /app/working）
"""
import json
import os
import sys
import urllib.request

API = os.environ.get("QWENPAW_API", "http://127.0.0.1:8088")
PROVIDER = os.environ.get("QWENPAW_PROVIDER", "<PLATFORM_NAME>-platform")
WORKSPACE = os.environ.get("QWENPAW_WORKSPACE", "/app/working")
AGENT_JSON = os.path.join(WORKSPACE, "agent.json")

# 各模型期望的 generate_kwargs（根据实际使用的模型自定义）
EXPECTED = {
    # "model-name": {"generate_kwargs key": "value", ...},
    # 示例：
    # "qwen3-max": {"extra_body": {"enable_thinking": True, "thinking_budget": 196608}},
    # "glm-4-plus": {"reasoning_effort": "xhigh"},
    # "deepseek-v3": {"reasoning_effort": "low", "max_tokens": 1024},
    # "qwen3-flash": {"extra_body": {"enable_thinking": False}},
}


def get_live_gk():
    with urllib.request.urlopen(f"{API}/api/models", timeout=15) as r:
        providers = json.load(r)
    live = {}
    for p in providers:
        if p.get("id") == PROVIDER:
            for key in ("models", "extra_models"):
                for m in p.get(key) or []:
                    mid = m.get("id") or m.get("name")
                    if mid in EXPECTED:
                        live[mid] = m.get("generate_kwargs") or {}
    return live


def put_config(model, gk):
    body = json.dumps({"generate_kwargs": gk}).encode()
    req = urllib.request.Request(
        f"{API}/api/models/{PROVIDER}/models/{model}/config",
        data=body,
        method="PUT",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        r.read()


def main():
    if not EXPECTED:
        print("NOTES: EXPECTED 为空，请先在脚本中配置你的模型期望值")
        return 0

    repaired, notes = [], []
    try:
        live = get_live_gk()
    except Exception as e:
        print(f"ERROR:读 /api/models 失败: {e}")
        return 1

    for mid, want in EXPECTED.items():
        if mid not in live:
            notes.append(f"{mid}:模型卡不在 daemon 活列表,无法核对")
            continue
        got = live[mid]
        if got != want:
            try:
                put_config(mid, want)
                repaired.append(
                    f"{mid}:gk 原为 {json.dumps(got, ensure_ascii=False)}"
                    f" → 已补回 {json.dumps(want, ensure_ascii=False)}"
                )
            except Exception as e:
                notes.append(f"{mid}:补回失败 {e}")

    try:
        cfg = json.load(open(AGENT_JSON))
        tl, tb = cfg.get("thinking_level"), cfg.get("thinking_budget")
        if tl != "inherit" or tb is not None:
            notes.append(
                f"THINKING_LEVEL_DRIFT:thinking_level={tl} thinking_budget={tb}"
                f"(期望 inherit/null),脚本不自动改 agent.json,需人工处理"
            )
    except Exception as e:
        notes.append(f"ERROR:读 agent.json 失败: {e}")

    if repaired:
        print("REPAIRED:" + "；".join(repaired))
    if notes:
        print("NOTES:" + "；".join(notes))
    if not repaired and not notes:
        print("校验通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
