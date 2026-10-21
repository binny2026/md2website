# SETUP · 三步上手

把 Markdown 文档变成可浏览的静态网站，并能一键部署到服务器。

---

## 前置要求

| 依赖 | 版本 | 用途 | 检查命令 |
| --- | --- | --- | --- |
| Python | 3.8+ | 运行辅助脚本 | `python3 --version` |
| Node.js | **18+** | 构建站点（必需） | `node --version` |
| tar / ssh / scp | 系统自带 | 仅部署时需要 | `tar --version` |

没装 Node.js？

- macOS：`brew install node` 或到 [nodejs.org](https://nodejs.org) 下载
- Ubuntu/Debian：`curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash - && sudo apt install -y nodejs`
- Windows：装好 Node.js 后，用 **WSL** 或 **Git Bash** 运行

自检：

```bash
python3 scripts/_env.py
```

---

## 最简用法：双击即用

装好之后，把一键入口复制到你的 Markdown 目录：

```bash
cp ~/.workbuddy/skills/md2website/assets/build.sh ~/你的md目录/
```

然后在 **Finder 里双击** `build.sh`（或在终端里 `./build.sh`），它会自动完成：

```
检查环境 → 扫描章节 → 生成站点 → 安装依赖 → 构建 → 打开浏览器
```

零参数、零配置。站点默认生成在同级的 `<目录名>-site/`。

想自己定标题和输出位置：

```bash
./build.sh --wizard
```

会逐项问你：站点标题、副标题、输出目录；生成后还会询问是否现在配置服务器（可选，可稍后部署时再配）。

其他参数：

| 参数 | 作用 |
| --- | --- |
| `--dir <路径>` | 指定 Markdown 源目录 |
| `--out <路径>` | 指定输出目录 |
| `--title "标题"` | 指定站点标题 |
| `--no-open` | 构建完不自动打开浏览器 |
| `--no-build` | 只生成，不装依赖、不构建 |

> macOS 首次双击若提示“无法打开”，在终端执行一次 `chmod +x build.sh`，或在
> 「系统设置 → 隐私与安全性」里点“仍要打开”。

---

## 分步命令（需要精细控制时用）

下面是可以手动逐步执行的版本，适合排查问题或集成到自己的流程。

### 第一步：安装

也可以在 Trae CN / Codex / Claude Code 等桌面 Agent 对话框里直接发仓库地址：

```
安装这个技能：https://github.com/binny2026/md2website
```

Agent 会克隆并执行安装脚本（非交互环境自动装到所有已检测到的 Agent 目录），装完新开会话即可。

手动安装：

```bash
git clone <仓库地址> md2website
cd md2website
./install.sh
```

安装脚本会探测本机已安装的桌面 Agent，让你多选安装目标：

```
  1  Trae CN      ~/.trae-cn/skills
  2  Trae         ~/.trae/skills
  3  Codex        ~/.codex/skills
  4  Claude Code  ~/.claude/skills
  5  WorkBuddy    ~/.workbuddy/skills
  6  Custom Path
```

输入 `1 3 5`、`1,3,5` 或 `1-3` 选择多个；`a` 全选，`q` 取消。
回车 = 更新已安装过的目录；首次安装则默认全部可安装目录。
未检测到 `skills` 目录的 Agent 会自动跳过，不会创建目录。

其他用法：

```bash
./install.sh --all                  # 装到所有检测到的 Agent
./install.sh --list                 # 只看检测结果
./install.sh --dir ~/my-skills/md2website   # 指定目录（可重复传）
./install.sh --check                # 只检查环境
```

非交互环境（Agent 执行 / CI / 管道）不传参数时，会装到所有已检测到的 Agent 目录（等价自动 `--all`）；
只想装一个目录就用 `--dir` 指定。
下文命令里的 `~/.workbuddy/skills/md2website` 请替换成你的实际安装路径（安装结束会打印）。

---

### 第二步：生成站点

```bash
SKILL=~/.workbuddy/skills/md2website

# 先看看源文档有什么坑（只读，不改文件）
python3 $SKILL/scripts/scan.py ~/你的md目录

# 生成站点
python3 $SKILL/scripts/init.py ~/你的md目录 \
    --out ./my-doc-site \
    --title "我的文档"
```

`init.py` 会：

- 按子目录识别章节，取每章首个 H1 当标题
- 复制 Markdown 与图片到 `./my-doc-site/docs/`（**源目录只读，不会被改**）
- 生成导航、首页、搜索配置、深浅色主题、图片放大

然后：

```bash
cd my-doc-site
npm install      # 首次约 1-3 分钟
npm run dev      # 打开 http://127.0.0.1:5174
```

如果源文档有 `<img>` 标签之类的问题导致构建失败：

```bash
python3 $SKILL/scripts/fix.py ./docs
npm run build
```

---

### 第三步：部署（可选）

服务器信息默认只保存在当前站点目录的 `.deploy-local.yml`（权限 600，已被 `.gitignore` 忽略），每个站点一份、互不影响。所有字段都没有预置默认值。

```bash
# 1. 交互式配置（也可直接执行 ./deploy.sh，缺配置会自动进入向导）
python3 $SKILL/scripts/profile.py wizard --project .

# 2. 先测连通性
./deploy.sh --dry-run

# 3. 正式部署
./deploy.sh
```

**首次部署前**，把公钥装到服务器（只需一次；下面以 ed25519 为例）：

```bash
ssh-copy-id -i ~/.ssh/id_ed25519.pub <账号>@doc.example.com
```

多站点需要共用配置时，才显式创建并绑定配置档：

```bash
python3 $SKILL/scripts/profile.py set --name my-doc \
    HOST="doc.example.com" PORT="22" USER="deploy" \
    REMOTE_DIR="/www/wwwroot/doc.example.com" SITE_BASE="/"
python3 $SKILL/scripts/profile.py bind --project . --name my-doc

python3 $SKILL/scripts/profile.py list     # 所有配置档
python3 $SKILL/scripts/profile.py show     # 本项目的配置
./deploy.sh --profile other-doc            # 临时换一台部署
```

---

## 关键概念：SITE_BASE

产物里的资源用绝对路径 `/assets/...`，所以：

| 部署位置 | SITE_BASE | 说明 |
| --- | --- | --- |
| `https://doc.example.com/` | `/` | 域名根目录，必填，无默认值 |
| `https://example.com/docs/` | `/docs/` | 子目录，**需在生成时用 `init.py --base /docs/`，改配置项本身不改变资源路径** |

填错的表现：页面能打开但样式全丢、图片全裂。

---

## 日常维护

| 场景 | 操作 |
| --- | --- |
| 改已有章节内容 | 覆盖 `docs/<章节>/index.md`，`npm run build` |
| 加图片 | 放进该章 `assets/`，正文写 `![](assets/xx.png)` |
| 新增章节 | 在 `docs/.vitepress/config.mjs` 的 `chapters` 数组加一行，再 build |

**新增章节必须改 config，否则侧边栏点不到。**

---

## 遇到问题

| 现象 | 原因 | 解决 |
| --- | --- | --- |
| `npm: command not found` | 没装 Node.js | 见开头安装指引 |
| 构建报 `Element is missing end tag` | 正文有裸尖括号 | 检查 config 的 `markdown.config` 是否被改动 |
| 构建报 `Rollup failed to resolve import` | 原始 `<img>` 标签 | `python3 $SKILL/scripts/fix.py ./docs` |
| 线上样式全丢 | SITE_BASE 与实际路径不符 | 改 `SITE_BASE` 后重新 build |
| `SSH 连接失败（已禁止交互输入密码）` | 公钥没装到服务器 | 执行报错提示里的 `ssh-copy-id` 命令 |
| 双击 index.html 打不开内链 | 需要 HTTP 服务 | 用 `npm run preview` 或部署后访问 |

更多排错见 `SKILL.md`。
