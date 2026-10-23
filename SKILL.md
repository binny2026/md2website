---
name: md2website
display_name: Markdown 文档站生成器
display_name_en: Markdown Documentation Website Builder
description_zh: "将 Markdown 教程、笔记、课件和手册转换为支持导航、全文搜索、代码高亮和图片放大的文档站，支持站点更新、门户聚合及远程部署。"
description_en: "Convert Markdown tutorials, notes, and manuals into documentation websites with navigation, full-text search, syntax highlighting, and image zoom. Supports site updates, portal aggregation, and remote deployment."
version: 1.0.0
author: binny
description: "把一个 Markdown 文档项目（多章节教程、笔记、课件、手册）改造为静态文档站，并支持一键部署到远程服务器。自动识别章节目录、生成侧边栏导航/首页/全文搜索/代码高亮/图片放大，自动检测并修复会导致 Vue 编译器报错的语法冲突。当用户说「把 md 转成 html」「md 项目做成文档站」「课件/笔记/文档做成网站」「生成文档站」「部署文档站到服务器」「更新站点」「更新文档站」「重建站点」「同步站点」「重新发布」「部署更新」时使用。更新站点时会自动查找已生成的站点，多个时让用户选择。当用户说「门户」「子模块」「多站点聚合」「挂到门户」「返回门户」时，使用门户功能把多个站点聚合成一个入口。"
---

# Markdown → 文档站

把一堆 Markdown 变成一个可浏览的静态文档网站：左侧章节导航、页面内目录、全文搜索、代码复制、深浅色主题、图片放大，且能一键部署到服务器。

**核心约束：源 Markdown 目录只读。** 所有产物写到独立输出目录，绝不修改用户的原始文档。

## 为什么需要专门的 skill

Markdown 课件/笔记直接构建几乎必然失败，原因是 **站点引擎把每个 `.md` 当作 Vue 单文件组件编译**，正文里这些写法会被 Vue 误判：

| 写法 | Vue 的反应 | 后果 |
| --- | --- | --- |
| `<https://example.com>` | 当成组件标签 | `Element is missing end tag` |
| `{{ xxx }}` | 当成插值表达式 | 编译报错或内容丢失 |
| `<email_hash:a1b2>` | 当成未知标签 | 标签未闭合报错 |
| `<img src="assets/x.png">` | **Vite 当模块 import** | `Rollup failed to resolve import` |
| 图片扩展名写错（`.jpeg`→缺 `.png`） | 路径解析失败 | 构建失败或图片静默丢失 |
| 跨章节相对链接（`../章节/章节.md`） | 主文档改名 index.md 后失效 | 构建报 `dead link` |

这些坑已经内置到生成的 `config.mjs`（前 3 类自动转义）和 `fix.py`（后 2 类自动修复）；跨章节相对链接由 `init.py` 生成时自动改写为站点 URL。

## 路径与环境

脚本**不依赖任何写死的解释器路径**，全部运行时探测：

```
SKILL_DIR = 按序探测 ~/.workbuddy、~/.trae-cn、~/.trae、~/.codex、~/.claude 下的 skills/md2website
            （install.sh 支持交互多选，可同时装到多个 Agent 目录）
PY        = python3                              （当前解释器即可，需 3.8+）
NODE      = 自动探测 PATH → nvm → homebrew → /usr/bin（需 18+）
依赖      = 项目内 npm install，首次约 1-3 分钟
```

开工前先确认环境，缺 Node 直接按提示给用户安装指引，不要继续跑：

```bash
python3 $SKILL_DIR/scripts/_env.py
```

脚本清单：

- `scripts/_env.py` — 环境探测（Python / Node 版本、安装指引）
- `scripts/init.py` — 扫描源目录，生成完整文档站项目，并自动修复语法冲突、改写跨章节死链、为合集/多级目录生成分组侧边栏；`--portal` 生成门户站点（聚合子模块）
- `scripts/scan.py` — 扫描语法冲突与缺失图片
- `scripts/fix.py` — 修复 `<img>` 标签与错误图片路径
- `scripts/profile.py` — 部署配置档管理（set/bind/cache/list/show/check/wizard/submodule）
- `scripts/sites.py` — 查找已生成的站点（list/select，支持 JSON 输出）
- `scripts/update.py` — 更新已有站点（重建 + 构建，可选部署）
- `assets/deploy.sh` — 一键部署脚本（init 时复制到项目里）


## 标准流程

> **重要**：用户说“做成网站 / 生成站点”时，**不要让他手动执行一堆命令**。
> 全程由你执行，用户只需提供 Markdown 目录（以及部署时的服务器信息）。

### 方式 A：一键入口（最省事，优先用）

```bash
bash "$SKILL_DIR/assets/build.sh" --dir "<md源目录>" --out "<输出目录>" --title "站点标题" --no-open
```

一次完成：环境检查 → 生成 → `npm install` → 构建 → 报告页面/图片数量。
适合「用户只想要结果」的场景；出问题再用方式 B 逐步排查。

`--no-open` 让脚本不自动弹浏览器（在 agent 环境里图标打不开）。需要预览时另外起后台服务：

```bash
cd "<输出目录>" && nohup npm run preview >/tmp/preview.log 2>&1 &
```

### 方式 B：分步执行（排错或需要精细控制时）

#### 1. 先检查环境与扫描源目录

```bash
python3 "$SKILL_DIR/scripts/_env.py"        # 确认 Node 18+ 可用
python3 "$SKILL_DIR/scripts/scan.py" "<md源目录>"
```

其中 `SKILL_DIR` 由 5 个 Agent 目录按序探测：`~/.workbuddy`、`~/.trae-cn`、`~/.trae`、`~/.codex`、`~/.claude` 下的 `skills/md2website`；`build.sh` 与 `deploy.sh` 使用同一顺序。
输出会列出阻断项（blocker）与警告（warn）。**先看清楚再动手**，把数量报给用户。

#### 2. 初始化项目

```bash
python3 "$SKILL_DIR"/scripts/init.py "<md源目录>" \
    --out "<输出目录>" \
    --title "站点标题" \
    --subtitle "副标题" \
    --name "站点名"
```

- `--out` 必须是不存在的路径（脚本拒绝覆盖已有目录）
- 未指定 `--out` 时默认 `./outputs/md2website-site`
- `--name` 可选：站点标识名（用于 `package.json` name、部署包名），默认从标题转换
- 脚本自动：按子目录递归识别章节、取每个目录首个 H1 作标题、把主文档改名为 `index.md`、复制所有图片、生成导航/首页/主题/部署配置/`.gitignore`；无「同名/index/README 主文档」的多文件目录识别为**合集目录**（侧边栏展开逐篇导航），子目录递归成**多级目录**；正文指向源 `.md` 的链接自动改写为站点 URL；默认生成**科技感双主题**样式

输出会逐章打印 `✓ 01 标题 → /slug/ (md N, img M)`，**核对数量和图片数对不对**。

#### 3. 修复语法冲突（通常已自动完成）

`init.py` 收尾会打印「自动修复 N 处语法冲突」，这部分不用再做。

只有在**改动了生成后的 md 文件**、或用户手动放了新内容时才需要重跑：

```bash
python3 "$SKILL_DIR"/scripts/fix.py "<输出目录>/docs"
```

`<https://...>`、`{{ }}`、占位符已由 config 内置规则处理；`fix.py` 只处理 `<img>` 标签和错误的图片路径。

#### 4. 安装依赖并构建

```bash
cd "<输出目录>"
npm install                                    # 首次约 1-3 分钟（125 个包，实测 39 秒）
npm run build
```

- 一律使用标准 `npm install`，**不要用软链指向别处的 node_modules**（换机器即失效）
- `deploy.sh` 已内置：发现 `node_modules/vitepress` 不存在时自动安装
- 构建成功标志：`✓ rendering pages... build complete in Ns`


#### 5. 核对产物

```bash
cd docs/.vitepress/dist
find . -name index.html | wc -l          # 页面数应为 章节数+1
find assets -type f -name '*.png' -o -name '*.jpeg' | wc -l   # 图片数对齐源目录
```

再用 `scan.py` 扫一遍 `docs/`，确认没有残留 blocker。

#### 6. 本地预览

```bash
PATH=$NODE_BIN:$PATH npm run preview    # http://127.0.0.1:4173
```

用 curl 验证返回 200 后再用 `present_files` 展示 URL。

#### 7. 配置部署信息（可选，交互式）

**默认每个站点独立配置**：服务器信息只保存在站点目录的 `.deploy-local.yml`（权限 600，已加入 `.gitignore`），
不会提交，也不会随站点上传。生成站点时 `build.sh` 会在交互终端询问「是否现在配置服务器」；
非交互环境自动跳过，首次执行 `deploy.sh` 时若仍无配置，会自动进入同一个向导。

**配置项没有预置默认值**：主机、登录账号、SSH 端口、远程目录、站点根路径都需要用户显式填写；
密码与 SSH 私钥至少填写一项。

Agent 不应编造主机名、账号或目录，也不要让用户在对话里粘贴密码。推荐让用户在自己的终端执行：

```bash
cd "<输出目录>"
python3 "$SKILL_DIR"/scripts/profile.py wizard --project "$(pwd)"
```

只有多个站点确实要共用同一台服务器时，才显式使用配置档（可选）：

```bash
python3 "$SKILL_DIR"/scripts/profile.py set --name <配置档名> \
    HOST="<主机>" PORT="<端口>" USER="<账号>" \
    REMOTE_DIR="<目录>" SITE_BASE="/<子目录>/或/"
python3 "$SKILL_DIR"/scripts/profile.py bind --project "<输出目录>" --name <配置档名>
```

配置档同样不自动补默认值，必填项缺失时 `check` 会返回 `INCOMPLETE`。站点本地配置优先于配置档绑定。

#### 8. 一键部署

```bash
./deploy.sh                # 无配置时自动进入向导，然后构建 + 上传
./deploy.sh --profile X    # 临时改用指定配置档（多站点共用时）
./deploy.sh --no-build     # 跳过构建
./deploy.sh --dry-run      # 只测配置与连通性
```

部署流程：解析配置档 → 构建 → 本地 tar 打包 → scp 上传 → 远程解压 → 按 `.deploy-manifest` 清理旧文件 → 校验 `index.html`。

脚本启动会打印「配置来源」，可据此确认用的是哪个配置档。`--dry-run` 连通失败会直接报错退出（已加 `BatchMode=yes`，不会卡在密码提示）。

## 部署前必须确认的两件事

1. **SSH 密钥是否已配到服务器**。`--dry-run` 连通失败时会给出可直接复制的 `ssh-copy-id` 命令，
   照抄给用户执行即可。不要尝试用密码硬闯，也不要擅自把密码写进配置文件。

2. **`SITE_BASE` 与部署位置是否匹配**。产物资源默认走绝对路径 `/assets/...`：
   - 域名根目录 → `SITE_BASE="/"`（默认）
   - 子目录（如 `example.com/docs/`）→ 必须改成 `"/docs/"` 并**重新构建**，否则样式和图片全部 404
   - 改完用 `profile.py set --name <配置档> SITE_BASE=/docs/`，然后重新 `npm run build`

3. **nginx 是否支持 `cleanUrls`（无扩展名 URL）**。站点默认 `cleanUrls: true`，子页面 URL 不带 `.html`，
   需要 nginx 配 `try_files $uri $uri/ $uri.html /index.html;`。宝塔默认无此规则，部署后务必验证侧边栏
   子页面是否 404；若 404，在站点 nginx 配置加 `location / { try_files $uri $uri/ $uri.html /index.html; }` 后 `nginx -s reload`。

## 多项目配置管理

| 需求 | 命令 |
| --- | --- |
| 列出所有配置档 | `profile.py list` |
| 查看本项目配置 | `profile.py show` |
| 改某一项 | `profile.py set --name X KEY=VALUE` |
| 本项目换服务器 | `profile.py bind --project . --name Y` |
| 临时换一台部署 | `./deploy.sh --profile Y` |

配置档是纯 `KEY=VALUE` 文本，**deploy.sh 只解析白名单字段，不 source 执行**，避免配置文件被写入任意命令。

## 章节识别规则

`init.py` 按以下规则判断章节，不合预期时用 `--chapters` 思路手工调整 config：

- 源目录下**含 `.md` 的子目录** → 各算一个章节
- 目录内**主文档**优先级：`与目录同名.md` > `index.md` > `README.md` > 第一个 md
- 目录内**无**同名/index/README 主文档且有多篇 md → 识别为**合集目录**：侧边栏生成可折叠分组、逐篇列出（分组标题用目录名，每篇标题取各自首个 H1）
- 目录内的**子目录**（含 md）→ 递归识别为**多级目录**：侧边栏生成嵌套分组（子目录标题用目录名，子目录主文档作为目录入口）
- 章节标题取主文档**第一个 H1**，没有则用目录名
- 根目录散装的 md → 平铺成单页（`readme/index` 跳过）
- URL slug 保留中文，只清洗空格和特殊字符

## 更新已有站点（触发词：更新站点 / 重建站点 / 同步站点 / 重新发布）

用户只说「更新站点」时，**不要让他翻目录找路径**，直接跑查找脚本：

```bash
python3 "$SKILL_DIR"/scripts/sites.py list          # 列出所有已生成的站点
python3 "$SKILL_DIR"/scripts/sites.py list --json   # Agent 消费
```

站点靠站点目录里的 `.md2website.json`（源目录、标题、name、base）识别，
全局登记表在 `~/.md2website/sites.json`，`init.py` 生成时会自动写入。

**站点数量处理规则：**

| 找到数量 | 处理方式 |
| --- | --- |
| 1 个 | 直接更新，把站点路径和标题告诉用户 |
| 多个 | 用 AskUserQuestion 让用户选（编号 + 标题 + 源目录 + 最后更新时间） |
| 0 个 | 告诉用户没有已生成站点，询问是否新建 |

更新命令：

```bash
python3 "$SKILL_DIR"/scripts/update.py "<站点目录>"            # 重建 + 构建
python3 "$SKILL_DIR"/scripts/update.py "<站点目录>" --deploy   # 重建 + 构建 + 部署
python3 "$SKILL_DIR"/scripts/update.py "<站点目录>" --dry-run  # 只看计划
```

`update.py` 的行为：

1. 读站点元数据里的源目录；源目录不可用时返回 `need_source`，此时让用户提供
2. 把 `docs/.vitepress` 备份到站点内 `.backup/vitepress-<时间戳>`
3. 用 `init.py --force` 原地重建（**新增章节自动进侧边栏**）
4. 保留 `.deploy-local.yml` 与 `node_modules`，不会重配服务器
5. 构建；加 `--deploy` 才执行 `./deploy.sh`

无交互终端下，脚本会输出 `{"action": "choose"}` 或 `{"action": "need_source"}` JSON，
按里面的信息向用户确认后再带参数重跑。**更新完成后必须核对页面数与图片数。**

手工微调（只改个别文件时用，不必全量重建）：

| 场景 | 操作 |
| --- | --- |
| 改已有章节内容 | 覆盖 `docs/<slug>/index.md`，重新 build |
| 加图片 | 放进该章 `assets/`，正文用相对路径 |
| 新增章节 | 优先跑 `update.py`；手改则必须在 `config.mjs` 的 chapters 数组加一条 |

## 门户与子模块（多站点聚合）

把多个站点聚合成一个「门户」入口：门户首页列出所有子模块，点击进入各子站点；子模块顶部导航带「返回门户」入口。

### 生成门户

```bash
python3 "$SKILL_DIR"/scripts/init.py --portal \
    --out "<门户输出目录>" --title "文档门户" --name portal
```

门户项目标记 `role=portal`，首页通过 `modules.json.php`（PHP）实时扫描直接子目录里的 `site.json`，**刷新页面即更新**，无需重新部署门户。

### 把站点挂为子模块

在站点目录执行交互向导：

```bash
python3 "$SKILL_DIR"/scripts/profile.py submodule --project "<站点目录>"
```

向导询问门户项目路径 + 子目录名，自动推导并写入 `.deploy-local.yml`：`REMOTE_DIR = 门户路径/<子目录名>/`、`SITE_BASE = 门户 SITE_BASE + <子目录名>/`、`PORTAL_PROJECT = 门户项目路径`。

### 部署顺序

1. 先部署门户（`./deploy.sh`），确认服务器门户目录已存在。
2. 再部署子模块（`./deploy.sh`）：自动写 `site.json` 并触发门户重建。

### 命名规则

站点标识名（`package.json` name、子目录默认名）自动生成：英文/数字保留，中文标题转拼音全拼（依赖 `pypinyin`，缺失则回退英文）。如「我的笔记」→ `wodebiji`。

### 子模块返回门户

子模块挂门户后，顶部导航自动出现「返回门户」入口（部署时由 `deploy.sh` 从门户 `REMOTE_DIR` 推断门户 URL 注入）。

## 常见故障

| 报错 | 原因 | 处理 |
| --- | --- | --- |
| `Element is missing end tag` | 正文裸尖括号 | config 转义规则未生效，检查 `markdown.config` |
| `Rollup failed to resolve import "assets/..."` | 原始 `<img>` 标签 | 跑 `fix.py` |
| 构建成功但图片是破图 | 扩展名不符 | `scan.py` 查 `missing_image` |
| `SAFE_DELETE_BULK_CONFIRM_REQUIRED` | Vite 清旧 dist 触发批量删除保护 | 先手动 `rm -rf docs/.vitepress/dist` 再 build |
| 样式全丢、页面裸奔 | `SITE_BASE` 与实际部署路径不符 | 改 `base` 后重新构建 |
| 双击 `index.html` 打不开内链 | `cleanUrls` 需要 HTTP 服务 | 用 `npm run preview` 或部署到服务器 |
| 部署后子页面 404、首页/章节首页正常 | nginx 未配 `try_files` 支持 `cleanUrls` | 站点 nginx 加 `location / { try_files $uri $uri/ $uri.html /index.html; }` 后 `nginx -s reload` |
| `未找到部署配置` | 站点没有 `.deploy-local.yml`，且当前不是交互终端 | 在终端执行 `./deploy.sh` 自动向导，或 `profile.py wizard --project .` |
| `配置档 X 不存在` | 显式用了 `--profile` 但配置档未创建 | `profile.py set --name X HOST=... PORT=... USER=... REMOTE_DIR=... SITE_BASE=...` |
| `SSH 连接失败（已禁止交互输入密码）` | 公钥未装到服务器 | 照报错里的 `ssh-copy-id` 命令执行一次 |

## 交付话术

完成后告诉用户：项目路径、页面/图片数量、预览地址、功能清单，以及三个关键区别：

1. **改内容只需 build，加章节要改 config**（否则侧边栏点不到）
2. **服务器配置默认在站点目录的 `.deploy-local.yml`，每个站点一份**（不进 git、不上传）
3. **需要多站点共用时才用配置档**，换部署目标用 `bind` 或 `--profile`，不用手改文件

不要只说"完成了"。
