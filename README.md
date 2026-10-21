# md-to-vitepress

把一个 Markdown 文档项目（多章节教程、笔记、课件、手册）改造成 VitePress 静态文档站，并支持一键部署到远程服务器。

**源目录只读**：所有产物写到独立目录，不会改动你的原始 Markdown。

## 功能特性

| 能力 | 说明 |
| --- | --- |
| 自动识别章节 | 按子目录递归扫描，取每篇首个 `H1` 作标题，主文档自动改名为 `index.md` |
| 多级目录 / 合集目录 | 子目录递归成分组侧边栏；多文件目录整组展开逐篇导航 |
| 侧边栏 / 全文搜索 / 代码复制 / 图片放大 | VitePress 原生能力全部开启 |
| 科技感双主题 | 深色 / 浅色，背景网格 + 光晕，渐变标题与按钮 |
| 语法冲突自动修复 | `<https://...>`、`{{ }}`、`<email_hash:...>`、`<img>` 标签等会被 Vue 误判的写法自动转义 |
| 死链自动改写 | 正文里指向源 `.md` 的相对链接自动改写为站点 URL |
| 一键部署 | 打包 → 上传 → 远程解压 → 校验，支持 SSH 密钥或账号密码 |
| 配置隔离 | 服务器信息存在用户目录，项目内不含敏感信息 |

---

## 环境要求

| 依赖 | 版本 | 用途 | 检查 |
| --- | --- | --- | --- |
| Python | 3.8+ | 运行生成脚本（仅标准库） | `python3 --version` |
| Node.js | **18+** | 构建站点（必需） | `node --version` |
| tar / ssh / scp | 系统自带 | 仅部署需要 | `tar --version` |
| sshpass | 可选 | 用账号密码登录服务器时必需 | `sshpass -V` |

没装 Node.js：

- macOS：`brew install node`，或到 [nodejs.org](https://nodejs.org) 下载
- Ubuntu / Debian：
  ```bash
  curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash - && sudo apt install -y nodejs
  ```
- Windows：装好 Node.js 后用 **WSL** 或 **Git Bash** 运行

---

## 安装

### 方式一：从仓库安装（推荐）

```bash
git clone git@github.com:binny2026/md2website.git md-to-vitepress
cd md-to-vitepress
./install.sh
```

默认安装到 `~/.workbuddy/skills/md-to-vitepress`。

### 方式二：安装到自定义目录

```bash
./install.sh --dir ~/my-skills/md-to-vitepress
```

安装到别处时，把下文命令里的 `SKILL` 换成实际路径。

### 安装前后的检查

```bash
./install.sh --check     # 只检查环境（Python / Node 版本），不安装
python3 ~/.workbuddy/skills/md-to-vitepress/scripts/_env.py   # 安装后再自检一次
```

### 卸载

```bash
./install.sh --uninstall                        # 当前目录是安装副本时
./install.sh --uninstall --dir ~/.workbuddy/skills/md-to-vitepress   # 显式指定
```

卸载不会删除部署配置档（`~/.workbuddy/deploy-profiles/`），需要时手动清理。

> 仓库里的 `install.sh` 只复制 `SKILL.md`、`scripts/`、`assets/`、文档等必要文件，不会带上 `.git` 与临时产物。

---

## 使用

### 方式一：一键建站（最省事，推荐）

把入口脚本复制到你的 Markdown 目录，双击或执行即可：

```bash
cp ~/.workbuddy/skills/md-to-vitepress/assets/build.sh ~/你的md目录/
cd ~/你的md目录 && ./build.sh
```

它会自动完成：

```
检查环境 → 扫描章节 → 生成站点 → 安装依赖 → 构建 → 启动预览
```

站点默认生成在同级目录的 `<目录名>-site/`。

常用参数：

| 参数 | 作用 |
| --- | --- |
| `--wizard` | 交互式询问标题、副标题、输出目录 |
| `--dir <路径>` | 指定 Markdown 源目录 |
| `--out <路径>` | 指定输出目录 |
| `--title "标题"` | 站点标题 |
| `--subtitle "副标题"` | 站点副标题 |
| `--name "站点名"` | 站点标识名（`package.json` name、部署包名），默认由标题转换 |
| `--skill <路径>` | 手动指定 skill 本体位置 |
| `--no-build` | 只生成项目，不装依赖、不构建 |
| `--no-open` | 构建完不自动打开浏览器 |

示例：

```bash
./build.sh --dir ~/笔记/课程 --out ~/笔记/课程-site --title "我的课程" --name my-course --no-open
```

### 方式二：在 AI Agent 里使用

装好后对 agent 说「把这个目录做成文档站 / 生成文档站 / 部署文档站到服务器」即可，agent 会读 `SKILL.md` 执行完整流程。也可显式指定源目录：

```
Use Skill: md-to-vitepress /path/to/md目录 生成站点
```

### 方式三：分步命令行（排错或精细控制）

```bash
SKILL=~/.workbuddy/skills/md-to-vitepress

# 1) 扫描源目录（只读，不改文件），先看有没有阻断项
python3 $SKILL/scripts/scan.py ~/你的md目录

# 2) 生成站点项目
python3 $SKILL/scripts/init.py ~/你的md目录 \
    --out ~/你的md目录-site \
    --title "站点标题" \
    --subtitle "副标题" \
    --name "site-name"

# 3) 安装依赖并构建
cd ~/你的md目录-site
npm install          # 首次约 1-3 分钟
npm run build

# 4) 本地预览
npm run preview      # http://127.0.0.1:4173
```

`init.py` 参数：

| 参数 | 说明 |
| --- | --- |
| `source` | Markdown 源目录（位置参数） |
| `--out` | 输出目录，必须不存在；默认 `./outputs/vitepress-site` |
| `--title` | 站点标题 |
| `--subtitle` | 站点副标题 |
| `--name` | 站点标识名，默认由标题转换 |
| `--base` | 站点根路径，子目录部署填 `/docs/`，默认 `/` |

如果改动了生成后的 Markdown，或手工加了内容导致构建失败：

```bash
python3 $SKILL/scripts/fix.py ~/你的md目录-site/docs            # 修复
python3 $SKILL/scripts/fix.py ~/你的md目录-site/docs --dry-run   # 只看不改
npm run build
```

---

## 部署到服务器

站点目录里已自带 `deploy.sh` 和 `DEPLOY.md`。服务器信息**不存在于项目内**，统一存放在 `~/.workbuddy/deploy-profiles/<配置档名>.conf`（权限 600），项目里只留 `.deploy-profile` 记录用哪个配置档（可安全提交）。

### 首次配置（交互式，支持账号密码）

```bash
cd ~/你的md目录-site
python3 ~/.workbuddy/skills/md-to-vitepress/scripts/profile.py wizard --project "$(pwd)"
```

会依次询问主机、账号、密码（留空则用 SSH 密钥）、私钥路径、远程目录、端口、站点根路径，结果写入站点本地 `.deploy-local.yml`（权限 600，已被 `.gitignore` 忽略，不会上传服务器）。

### 首次配置（配置档方式，多项目共用）

```bash
PY=python3
SKILL=~/.workbuddy/skills/md-to-vitepress

# 1) 创建配置档
$PY $SKILL/scripts/profile.py set --name my-doc \
    HOST="doc.example.com" USER="root" \
    REMOTE_DIR="/www/wwwroot/doc.example.com" SITE_BASE="/"

# 2) 项目绑定
$PY $SKILL/scripts/profile.py bind --project "$(pwd)" --name my-doc

# 3) 验证
$PY $SKILL/scripts/profile.py check
./deploy.sh --dry-run
```

### 正式部署

```bash
./deploy.sh                 # 构建 + 上传 + 远程解压 + 校验
./deploy.sh --dry-run       # 只检查配置与连通性，不上传
./deploy.sh --no-build      # 跳过构建，直接上传现有 dist
./deploy.sh --profile other-doc   # 临时换一台服务器
```

配置优先级：

```
--profile 指定 > 站点本地 .deploy-local.yml > 项目绑定 .deploy-profile > 项目内 deploy.conf（旧版）
```

### 登录方式

- **SSH 密钥**：`SSH_KEY` 指向私钥，首次需把公钥装到服务器
  ```bash
  ssh-copy-id -i ~/.ssh/id_ed25519.pub root@doc.example.com
  ```
- **账号密码**：配置 `PASSWORD`，本机需安装 `sshpass`
  ```bash
  brew install sshpass        # macOS
  sudo apt install sshpass    # Debian / Ubuntu
  ```

### 上传形态

| 字段 | 默认 | 说明 |
| --- | --- | --- |
| `DIST_NAME` | `dist` | 产物文件夹名 |
| `UPLOAD_WITH_DIR` | `false` | `true` 时远程生成 `<REMOTE_DIR>/<DIST_NAME>/`；`false` 平铺到 `<REMOTE_DIR>/index.html` |

### 部署后检查 nginx（重要）

站点默认 `cleanUrls: true`，子页面 URL 不带 `.html`。宝塔 / nginx 默认没有回退规则，会出现侧边栏子页面 404。在站点 `server` 块加：

```nginx
location / {
    try_files $uri $uri/ $uri.html /index.html;
}
```

然后 `nginx -s reload`。

### 配置字段

| 字段 | yml 键 | 默认 | 说明 |
| --- | --- | --- | --- |
| `HOST` | `host` | 必填 | 服务器域名或 IP |
| `USER` | `user` | 必填 | 登录账号 |
| `REMOTE_DIR` | `remote_dir` | 必填 | 远程部署目录（绝对路径） |
| `PORT` | `port` | 22 | SSH 端口 |
| `SSH_KEY` | `ssh_key` | `$HOME/.ssh/id_rsa` | 私钥路径 |
| `PASSWORD` | `password` | 空 | 登录密码，配置后走 sshpass |
| `SITE_BASE` | `site_base` | `/` | 站点根路径，子目录填 `/docs/`，改后需重新构建 |
| `CLEAN_MODE` | `clean_mode` | `manifest` | 清理方式 `manifest` / `none` / `all` |
| `BUILD_BEFORE_DEPLOY` | `build_before_deploy` | `true` | 部署前是否构建 |
| `REMOTE_TMP` | `remote_tmp` | `/tmp` | 远程临时目录 |
| `DIST_NAME` | `dist_name` | `dist` | 产物文件夹名 |
| `UPLOAD_WITH_DIR` | `upload_with_dir` | `false` | 是否带文件夹一起上传 |

---

## 脚本职责

| 脚本 | 作用 | 是否改文件 |
| --- | --- | --- |
| `install.sh` | 安装 / 检查 / 卸载 | 写安装目录 |
| `scripts/_env.py` | 探测 Python / Node，给出安装指引 | 只读 |
| `scripts/scan.py` | 检测 Vue 语法冲突、缺失图片 | 只读 |
| `scripts/fix.py` | 修复 `<img>` 标签、错误图片扩展名 | 改写（默认，可 `--dry-run`） |
| `scripts/init.py` | 生成完整 VitePress 项目（含死链改写、多级目录、主题） | 只写新目录 |
| `scripts/profile.py` | 部署配置档管理（`path/show/check/set/list/bind/cache/wizard`） | 写 `~/.workbuddy/deploy-profiles/` 或站点 `.deploy-local.yml` |
| `assets/build.sh` | 一键入口：扫描 → 生成 → 装依赖 → 构建 → 预览 | 写输出目录 |
| `assets/deploy.sh` | 构建 + 打包上传 + 远程解压 + 校验 | 写本地临时包 |

---

## 生成的站点结构

```
<输出目录>/
├── docs/
│   ├── index.md                 # 首页
│   ├── .vitepress/
│   │   ├── config.mjs           # 导航 / 侧边栏 / 主题 / 语法转义规则
│   │   ├── theme/
│   │   │   ├── index.mjs
│   │   │   └── custom.css       # 科技感双主题
│   │   └── dist/                # 构建产物
│   ├── <章节>/
│   │   └── index.md
│   └── assets/                  # 图片
├── package.json
├── deploy.sh
├── DEPLOY.md
└── .gitignore                   # 已忽略部署配置与构建产物
```

---

## 常见问题

| 现象 | 原因 | 解决 |
| --- | --- | --- |
| `npm: command not found` | 没装 Node.js | 见「环境要求」 |
| 构建报 `Element is missing end tag` | 正文有裸尖括号 | 勿改 `config.mjs` 的 `markdown.config`；或跑 `fix.py` |
| 构建报 `Rollup failed to resolve import` | 原始 `<img>` 标签 | `python3 scripts/fix.py ./docs` |
| 线上样式全丢、图片全裂 | `SITE_BASE` 与实际路径不符 | 改 `--base` / `SITE_BASE` 后重新构建 |
| 线上子页面 404 | nginx 缺 `try_files` | 见「部署后检查 nginx」 |
| `SSH 连接失败（已禁止交互输入密码）` | 公钥没装到服务器 | 执行 `ssh-copy-id`，或改用 `PASSWORD` 登录 |
| `本机未安装 sshpass` | 配置了密码登录 | `brew install sshpass` / `apt install sshpass` |
| 双击 `index.html` 内链打不开 | 静态文件需 HTTP 服务 | 用 `npm run preview` 或部署后访问 |

更多排错与执行规范见 `SKILL.md`；三步上手版见 `SETUP.md`；English: `README.en.md`。

---

## 许可证

MIT
