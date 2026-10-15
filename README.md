# QwenPaw Ops

QwenPaw 框架补丁存活工具集。

QwenPaw 部署在容器中，`pip upgrade` 或 pod 重建会覆盖 `site-packages`，导致手动补丁丢失。本工具集自动检测补丁是否在位，丢失时自动补回（含 `py_compile` 验证 + 失败回滚）。

## 补丁清单

| 补丁 | 脚本 | 解决问题 |
|---|---|---|
| `gmi` | `gmi_fallback_patch.py` | 阿里网关内容审核误杀（`data_inspection_failed`）时自动跨模型 fallback，而非直接断线 |
| `cron` | `cron_dedup_check.py` | 多 pod 共享存储时防止同一 cron 任务双跑（`O_CREAT\|O_EXCL` 锁文件） |
| `ast` | `ast_search_dedup_check.py` | 防止 `ast_search` 工具重复注册（Coding Mode + builtin_tools 双注册） |
| `compact` | `compact_cn_check.py` | compact 通知汉化插件存活检查（pid + cmdline 验证） |
| `thinking` | `thinking_config_check.py` | 各模型思考档 `generate_kwargs` 配置漂移检测 + API 自动补回 |

## 快速开始

```bash
# 1. 复制配置模板
cp .env.example .env

# 2. 编辑 .env（如果路径非默认）
vim .env

# 3. 检查所有补丁状态
bash run.sh check

# 4. 自动补回缺失补丁
bash run.sh apply

# 5. 只检查某个补丁
bash run.sh check gmi
```

### 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| `QWENPAW_SITE_PACKAGES` | site-packages 路径 | `/app/venv/lib/python3.11/site-packages` |
| `QWENPAW_WORKING` | working 目录 | `/app/working` |
| `QWENPAW_API` | daemon API 地址 | `http://127.0.0.1:8088` |
| `QWENPAW_PROVIDER` | provider ID | `<PLATFORM_NAME>-platform` |

### 自定义 thinking 配置

`thinking_config_check.py` 中的 `EXPECTED` 字典默认为空，需要根据你实际使用的模型填写：

```python
EXPECTED = {
    "your-model": {"extra_body": {"enable_thinking": True, "thinking_budget": 196608}},
    # ...
}
```

## 补丁机制

每个补丁遵循相同模式：

1. **标记检查** — 用唯一 marker 字符串判断补丁是否在位
2. **丢失检测** — marker 不在源码中 = 被覆盖了
3. **自动补回** — 找到原始代码 → 替换为补丁版 → 写回
4. **编译验证** — `py_compile` 检查语法，失败自动回滚
5. **自测** — 部分补丁有行为自测（如 gmi 的错误分类验证）

## 推送安全

`.gitignore` 屏蔽 `.env` 和密钥文件。`pre_push_check.sh` 推送前扫描敏感信息。GitHub Actions CI 自动跑语法检查 + 敏感扫描。

## 许可证

MIT
