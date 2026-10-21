---
name: md-to-vitepress
description: "把一个 Markdown 文档项目（多章节教程、笔记、课件、手册）改造为 VitePress 静态文档站，并支持一键部署到远程服务器。自动识别章节目录、生成侧边栏导航/首页/全文搜索/代码高亮/图片放大，自动检测并修复会导致 Vue 编译器报错的语法冲突。当用户说「把 md 转成 html」「md 项目改造成 vitepress」「课件/笔记/文档做成网站」「生成文档站」「部署文档站到服务器」时使用。"
---

# Markdown → VitePress 文档站

把一堆 Markdown 变成一个可浏览的静态文档网站：左侧章节导航、页面内目录、全文搜索、代码复制、深浅色主题、图片放大，且能一键部署到服务器。

**核心约束：源 Markdown 目录只读。** 所有产物写到独立输出目录，绝不修改用户的原始文档。

## 为什么需要专门的 skill

Markdown 课件/笔记直接用 VitePress 构建几乎必然失败，原因是 **VitePress 把每个 `.md` 当作 Vue 单文件组件编译**，正文里这些写法会被 Vue 误判：

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
SKILL_DIR = $HOME/.workbuddy/skills/md-to-vitepress   （install.sh 可改位置）
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
- `scripts/init.py` — 扫描源目录，生成完整 VitePress 项目，并自动修复语法冲突、改写跨章节死链、为合集目录生成分组侧边栏
- `scripts/scan.py` — 扫描语法冲突与缺失图片
- `scripts/fix.py` — 修复 `<img>` 标签与错误图片路径
- `scripts/profile.py` — 部署配置档管理
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

其中 `SKILL_DIR=$HOME/.workbuddy/skills/md-to-vitepress`（若用 `install.sh --dir` 装到别处，以实际位置为准）。
输出会列出阻断项（blocker）与警告（warn）。**先看清楚再动手**，把数量报给用户。

#### 2. 初始化项目

```bash
python3 "$SKILL_DIR"/scripts/init.py "<md源目录>" \
    --out "<输出目录>" \
    --title "站点标题" \
    --subtitle "副标题"
```

- `--out` 必须是不存在的路径（脚本拒绝覆盖已有目录）
- 未指定 `--out` 时默认 `./outputs/vitepress-site`
- 脚本自动：按子目录识别章节、取每个目录首个 H1 作标题、把主文档改名为 `index.md`、复制所有图片、生成导航/首页/主题/部署配置；无「同名/index/README 主文档」的多文件目录会识别为**合集目录**（侧边栏展开逐篇导航），正文指向源 `.md` 的链接自动改写为站点 URL

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

#### 7. 配置部署信息（交互式，一次一问）

**服务器信息不存在项目里**，统一存到 `~/.workbuddy/deploy-profiles/<配置档名>.conf`（权限 600），
项目内只留一个 `.deploy-profile` 文件记录用哪个配置档（可安全提交）。多个项目各自一份，互不干扰。

先检查当前项目有没有配好：

```bash
python3 "$SKILL_DIR"/scripts/profile.py check
```

返回 `OK` 就直接进入第 8 步。返回 `UNBOUND` / `MISSING` / `INCOMPLETE` 时，**必须交互补齐，禁止自己编造主机名或目录**：

1. **一次只问一个问题**，并附上建议答案（推荐值放前面），用选择题/快捷回复形式，不要让用户手敲整段配置。
2. 必问三项（其余有默认值，用户不提就不问）：

   | 项目 | 问法示例 | 建议答案 |
   | --- | --- | --- |
   | 主机 | 部署到哪台服务器？ | 上次用过的 HOST；或「域名根目录 / 子目录」二选一 |
   | 账号 | 用哪个账号登录？ | `root` |
   | 目录 | 站点放在服务器哪个绝对路径？ | 借鉴 `/www/wwwroot/<域名>` |

3. **只问一个歧义点**：站点是域名根目录还是子目录（决定 `SITE_BASE`）。这直接影响资源能否加载，必须确认。
4. 拿到答案后一次写入并绑定：

```bash
python3 "$SKILL_DIR"/scripts/profile.py set --name <配置档名> \
    HOST="<主机>" USER="<账号>" REMOTE_DIR="<目录>" SITE_BASE="/<子目录>/或/"
python3 "$SKILL_DIR"/scripts/profile.py bind --project "<输出目录>" --name <配置档名>
```

5. 配置档名默认取项目目录名（`init.py` 已在 `DEPLOY.md` 里写好建议名），用户没指定就用它。

**绝不把密码写进配置文件**，只记 SSH 密钥路径。需要密码时提示用户执行 `ssh-copy-id`。

#### 8. 一键部署

```bash
./deploy.sh                # 用项目绑定的配置档，构建 + 上传
./deploy.sh --profile X    # 临时换配置档（测另一台服务器时）
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
- 章节标题取主文档**第一个 H1**，没有则用目录名
- 根目录散装的 md → 平铺成单页（`readme/index` 跳过）
- URL slug 保留中文，只清洗空格和特殊字符

## 增量更新已有站点

| 场景 | 操作 |
| --- | --- |
| 改已有章节内容 | 覆盖 `docs/<slug>/index.md`，重新 build |
| 加图片 | 放进该章 `assets/`，正文用相对路径 |
| 新增章节 | 在 `docs/.vitepress/config.mjs` 的 `chapters` 数组加一条，再 build |

**新增章节必须改 config，否则侧边栏点不到**——这点要向用户讲清楚。

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
| `未找到部署配置` | 项目没绑定配置档 | `profile.py bind --project . --name X` |
| `项目绑定了配置档 X，但文件不存在` | 配置档被删了 | `profile.py set --name X HOST=...` 重建 |
| `SSH 连接失败（已禁止交互输入密码）` | 公钥未装到服务器 | 照报错里的 `ssh-copy-id` 命令执行一次 |

## 交付话术

完成后告诉用户：项目路径、页面/图片数量、预览地址、功能清单，以及三个关键区别：

1. **改内容只需 build，加章节要改 config**（否则侧边栏点不到）
2. **服务器配置在 `~/.workbuddy/deploy-profiles/`，不在项目里**（多项目各一份，不进 git）
3. **换部署目标用 `bind` 或 `--profile`**，不用手改文件

不要只说"完成了"。
