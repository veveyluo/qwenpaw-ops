#!/usr/bin/env python3
"""gmi-fallback-patch — 内容审核误杀时自动跨模型 fallback。

背景：
  阿里网关内容审核误杀（data_inspection_failed，HTTP 400）在 QwenPaw 的
  model_error_policy.py 里被归为 bad_request → 不重试、不 fallback →
  整个回合被杀。

补丁内容（两处，均带 qwenpaw-gmi-fallback-patch-v1 标记）：
  1. content_safety 匹配标记增加 "data_inspection" / "inappropriate content"
  2. fallback_eligible 扩为 retryable or kind in {"model_not_found", "content_safety"}

生效条件：
  daemon 重启后才生效（Python import 缓存）。若平台热更覆盖了 site-packages，
  补丁会丢失 → 重跑本脚本即可（幂等：已有标记则跳过）。

用法：
  python3 gmi_fallback_patch.py          # 检查并补
  python3 gmi_fallback_patch.py --check  # 只检查不动文件

环境变量：
  QWENPAW_SITE_PACKAGES  site-packages 路径（默认 /app/venv/lib/python3.11/site-packages）
"""
import os
import py_compile
import sys

SITE_PACKAGES = os.environ.get(
    "QWENPAW_SITE_PACKAGES",
    "/app/venv/lib/python3.11/site-packages",
)
TARGET = os.path.join(SITE_PACKAGES, "qwenpaw/providers/model_error_policy.py")
MARKER = "qwenpaw-gmi-fallback-patch-v1"

OLD_MARKERS = '''    elif any(
        marker in message
        for marker in (
            "content policy",
            "content_policy",
            "content safety",
            "safety_filter",
            "moderation",
        )
    ):
        kind = "content_safety"'''

NEW_MARKERS = '''    elif any(
        marker in message
        for marker in (
            "content policy",
            "content_policy",
            "content safety",
            "safety_filter",
            "moderation",
            # qwenpaw-gmi-fallback-patch-v1: Ali/DashScope-style gateway
            # content inspection errors (data_inspection_failed, "Input text
            # data may contain inappropriate content") are moderation
            # verdicts, not malformed requests.
            "data_inspection",
            "inappropriate content",
        )
    ):
        kind = "content_safety"'''

OLD_ELIGIBLE = '''    retryable = kind in {"rate_limited", "transient"}
    fallback_eligible = retryable or kind == "model_not_found"'''

NEW_ELIGIBLE = '''    retryable = kind in {"rate_limited", "transient"}
    # qwenpaw-gmi-fallback-patch-v1: content_safety verdicts are
    # provider-specific (often false positives on benign text). Retrying the
    # same model with identical input is futile, but the next provider in the
    # fallback chain applies its own independent moderation — so cross-model
    # fallback is the correct recovery. Same-model retry stays disabled.
    fallback_eligible = retryable or kind in {"model_not_found", "content_safety"}'''


def classify_selftest() -> bool:
    """补丁后行为自测：阿里审核错误必须 content_safety + fallback。"""
    sys.path.insert(0, SITE_PACKAGES)
    for m in list(sys.modules):
        if m.startswith("qwenpaw.providers"):
            del sys.modules[m]
    from qwenpaw.providers.model_error_policy import classify_model_error

    class FakeExc(Exception):
        def __init__(self, msg, status):
            super().__init__(msg)
            self.status_code = status

    ali = FakeExc(
        'data: {"error":{"code":"data_inspection_failed",'
        '"message":"Input text data may contain inappropriate content.",'
        '"type":"data_inspection_failed"}}',
        400,
    )
    d = classify_model_error(ali)
    ok = d.kind == "content_safety" and d.fallback_eligible and not d.retryable
    d2 = classify_model_error(FakeExc("invalid json body", 400))
    ok2 = d2.kind == "bad_request" and not d2.fallback_eligible
    return ok and ok2


def main() -> int:
    check_only = "--check" in sys.argv
    try:
        src = open(TARGET, encoding="utf-8").read()
    except FileNotFoundError:
        print(f"❌ 目标文件不存在: {TARGET}（包路径变了？需人工看）")
        return 2

    if MARKER in src:
        print(f"✅ 补丁已在位（{MARKER}），无需操作")
        if not classify_selftest():
            print("⚠️ 但自测未通过，请人工检查")
            return 1
        print("✅ 分类自测通过：data_inspection → content_safety + fallback_eligible")
        return 0

    if check_only:
        print("⚠️ 补丁缺失（文件可能被平台热更覆盖），需重跑本脚本补上")
        return 1

    if OLD_MARKERS not in src or OLD_ELIGIBLE not in src:
        print("❌ 源文件结构与补丁预期不符（官方可能已改此处代码），拒绝盲改，请人工比对")
        return 2

    import shutil
    bak = TARGET + ".bak-gmi-auto"
    shutil.copy2(TARGET, bak)
    patched = src.replace(OLD_MARKERS, NEW_MARKERS, 1).replace(OLD_ELIGIBLE, NEW_ELIGIBLE, 1)
    open(TARGET, "w", encoding="utf-8").write(patched)
    try:
        py_compile.compile(TARGET, doraise=True)
    except py_compile.PyCompileError as e:
        shutil.copy2(bak, TARGET)
        print(f"❌ 编译失败已回滚: {e}")
        return 1
    if not classify_selftest():
        shutil.copy2(bak, TARGET)
        print("❌ 自测失败已回滚")
        return 1
    print(f"✅ 补丁已应用并通过自测（备份: {bak}）；生效需 daemon 重启")
    return 0


if __name__ == "__main__":
    sys.exit(main())
