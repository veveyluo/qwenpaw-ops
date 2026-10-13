#!/usr/bin/env python3
"""compact 汉化插件存活校验（watchdog 模式：正常静默，异常才输出）。

校验链：
1. 插件目录存在
2. _status.json 存在（插件加载时会写）
3. 标记里的 pid 仍存活且是 qwenpaw daemon 进程
   → 说明当前 daemon 进程加载过插件、钩子在位
任一环节断 = 框架改版/插件加载失败/daemon 重启后插件没跟上 → 输出告警行。

环境变量：
  QWENPAW_WORKING  working 目录（默认 /app/working）
"""
import json
import os
import sys

WORKING = os.environ.get("QWENPAW_WORKING", "/app/working")
PLUGIN_DIR = os.path.join(WORKING, "plugins/compact-cn-notice")
STATUS = os.path.join(PLUGIN_DIR, "_status.json")


def main():
    if not os.path.isdir(PLUGIN_DIR):
        print("⚠️ compact 汉化插件目录缺失：" + PLUGIN_DIR)
        return 1
    if not os.path.exists(STATUS):
        print("⚠️ compact 汉化插件未加载（_status.json 缺失）——daemon 可能重启后插件加载失败")
        return 1
    try:
        st = json.load(open(STATUS, encoding="utf-8"))
        pid = int(st.get("pid", 0))
    except Exception as e:
        print(f"⚠️ compact 汉化插件标记损坏：{e}")
        return 1
    cmdline = ""
    try:
        cmdline = open(f"/proc/{pid}/cmdline", "rb").read().decode(errors="replace")
    except Exception:
        pass
    if "qwenpaw" not in cmdline:
        print(f"⚠️ compact 汉化钩子失效：标记 pid {pid} 已不是活着的 qwenpaw daemon")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
