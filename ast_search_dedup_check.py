#!/usr/bin/env python3
"""ast_search dedup 校验——防平台热更覆盖 mixin.py 去重补丁。

mixin.py 在 site-packages，平台热更(pip upgrade)会覆盖。
本脚本检查去重代码是否在位，不在则自动补回 + 清 __pycache__。

用法：
  python3 ast_search_dedup_check.py          # 检查+自动补回
  python3 ast_search_dedup_check.py --check  # 只检查不补

环境变量：
  QWENPAW_SITE_PACKAGES  site-packages 路径（默认 /app/venv/lib/python3.11/site-packages）
"""
import os
import sys

SITE_PACKAGES = os.environ.get(
    "QWENPAW_SITE_PACKAGES",
    "/app/venv/lib/python3.11/site-packages",
)
MIXIN = os.path.join(SITE_PACKAGES, "qwenpaw/modes/coding/mixin.py")
MARKER = "_has_builtin_ast"

ORIGINAL = '''    try:
        if ast_tool.is_ast_grep_available():
            result.append(
                PolicyGuardedTool(
                    ast_tool.ast_search,
                    governor=governor,
                    request_context=request_context,
                ),
            )
            logger.info("Registered Coding Mode ast_search tool")'''

DEDUP = '''    try:
        if ast_tool.is_ast_grep_available():
            # Dedup: builtin_tools already registers ast_search via
            # tools/__init__.py import. Skip coding-mode copy to avoid
            # <PLATFORM_NAME> "Duplicate tool name" WARNING every turn.
            _bt = getattr(getattr(agent_config, "tools", None), "builtin_tools", None)
            _has_builtin_ast = _bt is not None and "ast_search" in _bt
            if not _has_builtin_ast:
                result.append(
                    PolicyGuardedTool(
                        ast_tool.ast_search,
                        governor=governor,
                        request_context=request_context,
                    ),
                )
                logger.info("Registered Coding Mode ast_search tool")
            else:
                logger.debug("Coding Mode ast_search skipped (already in builtin_tools)")'''


def check() -> bool:
    try:
        with open(MIXIN, "r") as f:
            return MARKER in f.read()
    except Exception:
        return False


def apply() -> bool:
    if check():
        return True
    try:
        with open(MIXIN, "r") as f:
            content = f.read()
        if ORIGINAL not in content:
            return False
        content = content.replace(ORIGINAL, DEDUP, 1)
        pycache = os.path.join(os.path.dirname(MIXIN), "__pycache__")
        if os.path.isdir(pycache):
            for fn in os.listdir(pycache):
                if fn.startswith("mixin."):
                    os.remove(os.path.join(pycache, fn))
        with open(MIXIN, "w") as f:
            f.write(content)
        return check()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return False


if __name__ == "__main__":
    check_only = "--check" in sys.argv
    if check():
        print("校验通过")
    elif check_only:
        print("AST_DEDUP_LOST")
    else:
        if apply():
            print("AST_DEDUP_REPAIRED")
        else:
            print("AST_DEDUP_LOST")
            sys.exit(1)
