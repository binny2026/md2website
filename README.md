# md-to-vitepress

把 Markdown 文档项目改造为 VitePress 站点，并支持一键部署。

**外部用户请看 [`SETUP.md`](SETUP.md)（三步上手）**；English: [`README.en.md`](README.en.md)。
`SKILL.md` 是给 AI Agent 读的执行规范，包含各类坑位与排错规则。

## 一键建站（推荐）

```bash
# 装好后，把入口复制到你的 md 目录
cp assets/build.sh ~/你的md目录/
cd ~/你的md目录 && ./build.sh        # 或 Finder 里双击
```

自动完成：检查环境 → 扫描章节 → 生成站点 → 安装依赖 → 构建 → 打开浏览器。
零参数、零配置；要自己定标题和输出位置用 `./build.sh --wizard`。

## 快速自检

```bash
python3 scripts/_env.py                    # 检查 Python / Node 环境
python3 scripts/scan.py "<md目录>"          # 扫描语法冲突（只读）
python3 scripts/fix.py  "<产物docs目录>" --dry-run   # 预览修复
```

## 脚本职责

| 脚本 | 作用 | 是否改文件 |
| --- | --- | --- |
| `_env.py` | 探测 Python / Node，给出安装指引 | 只读 |
| `scan.py` | 检测 Vue 语法冲突、缺失图片 | 只读 |
| `fix.py` | 修复 `<img>` 标签、错误图片扩展名 | 改写（默认，可 `--dry-run`） |
| `init.py` | 从 md 目录生成完整 VitePress 项目（含语法修复、死链改写、合集/多级目录分组导航、科技感主题） | 只写新目录 |
| `profile.py` | 管理部署配置档（多项目隔离，可 cache 到站点本地） | 写 `~/.workbuddy/deploy-profiles/` |
| `assets/build.sh` | 一键入口：扫描→生成→装依赖→构建→预览 | 写输出目录 |
| `assets/deploy.sh` | 构建 + 打包上传 + 远程解压 | 写本地临时包 |

## 部署配置档

服务器信息**不放在项目里**，统一存到 `~/.workbuddy/deploy-profiles/<名字>.conf`（权限 600）。
项目只留 `.deploy-profile` 记录用哪个配置档，可安全提交。

```bash
python3 scripts/profile.py list                        # 列出所有配置档
python3 scripts/profile.py set --name doc HOST=... USER=root REMOTE_DIR=...
python3 scripts/profile.py bind --project . --name doc  # 项目绑定
python3 scripts/profile.py check                        # 检查缺项
python3 scripts/profile.py cache --project .            # 缓存配置到站点本地 .deploy-local.conf（不上传）
```

`deploy.sh` 用配置档（`--profile` > 站点本地 `.deploy-local.conf` > 项目绑定 > 项目内 `deploy.conf` 旧版兼容）。

## 依赖

- Python 3.8+（仅标准库，无第三方依赖）
- Node.js 18+（构建必需，项目内 `npm install`）
- tar / ssh / scp（仅部署需要）

## 安装

```bash
./install.sh              # 装到 $HOME/.workbuddy/skills/md-to-vitepress
./install.sh --check      # 只检查环境
./install.sh --uninstall  # 卸载
```

## 许可证

MIT
