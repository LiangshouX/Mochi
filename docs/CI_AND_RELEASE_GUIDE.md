# GitHub CI / Release / PyPI 发布 — 完整操作手册

> 本手册面向 Mochi 项目，涵盖 GitHub Actions CI、Release 管理、PyPI 发布的全部流程。

---

## 目录

1. [核心概念速览](#1-核心概念速览)
2. [前置准备](#2-前置准备)
3. [GitHub Actions CI — 自动测试](#3-github-actions-ci--自动测试)
4. [GitHub Release — 版本发布](#4-github-release--版本发布)
5. [PyPI 发布 — 让用户 pip install](#5-pypi-发布--让用户-pip-install)
6. [完整工作流：从代码到用户](#6-完整工作流从代码到用户)
7. [附录：常见问题](#7-附录常见问题)

---

## 1. 核心概念速览

### 什么是 CI（持续集成）？

**CI = Continuous Integration**，每次你 push 代码或提 PR，GitHub 自动帮你跑测试、lint、构建，确保代码不会悄悄坏掉。

```
你 push 代码 → GitHub 自动触发 → 跑测试 → 绿了 ✅ / 红了 ❌
```

**核心价值**：不在本地跑测试也行，CI 帮你兜底。

### 什么是 GitHub Actions？

GitHub Actions 是 GitHub 内置的 CI/CD 引擎。你在 `.github/workflows/` 下写一个 YAML 文件，GitHub 就会在云端给你开一台机器（runner），按你的指令执行。

```yaml
# 最简单的例子：每次 push 就打印 hello
on: push
jobs:
  say-hello:
    runs-on: ubuntu-latest
    steps:
      - run: echo "hello"
```

### 什么是 Release？

Release 是 GitHub 上的**版本快照**。当你觉得代码到了一个稳定的里程碑，就打一个 Release：

- 绑定一个 **Git tag**（如 `v0.1.0`）
- 附带 **release notes**（变更说明）
- 可以上传 **附件**（如 `.whl`、`.tar.gz`）

Release 不是必须的，但它是 PyPI 自动发布的关键触发点。

### CI / Release / PyPI 的关系

```
代码变更
   │
   ▼
push / PR ──→ GitHub Actions CI ──→ 跑测试、lint
   │                                    │
   │                               通过 ✅
   │                                    │
   ▼                                    ▼
打 Release (v0.2.0) ──→ Actions 检测到 tag ──→ 构建包 ──→ 上传 PyPI
                                                           │
                                                           ▼
                                                    用户 pip install mochi-assistant
```

---

## 2. 前置准备

### 2.1 GitHub 仓库

项目已在 GitHub 上：`https://github.com/LiangshouX/Mochi`

### 2.2 本地工具

```bash
# 确保有 poetry（构建用）
pip install poetry

# 确保有 twine（手动上传 PyPI 用，CI 里不需要）
pip install twine
```

### 2.3 PyPI 账户与 Trusted Publisher（推荐）

PyPI 现在推荐 **Trusted Publisher**（受信任发布者），不需要手动生成 API Token，直接让 GitHub Actions 用 OIDC 认证上传。

**设置步骤**：

1. 去 [https://pypi.org/manage/account/publishing/](https://pypi.org/manage/account/publishing/)（需要先注册 PyPI 账户）
2. 点 **Add a new pending publisher**，填写：

   | 字段 | 值 |
   |------|-----|
   | PyPI project name | `mochi-assistant` |
   | Owner | `LiangshouX` |
   | Repository | `Mochi` |
   | Workflow name | `release.yml` |
   | Environment name | `pypi` |

3. 保存即可。之后 GitHub Actions 里配置了对应的 environment，就能自动上传。

> **如果项目还没在 PyPI 上存在**：第一次发布时，Trusted Publisher 会自动创建项目。也可以先手动 `twine upload` 一次，之后再切到 Trusted Publisher。

### 2.4 TestPyPI（可选，先测试再正式）

TestPyPI 是 PyPI 的测试环境，地址：[https://test.pypi.org/](https://test.pypi.org/)

同样可以配置 Trusted Publisher，流程和 PyPI 完全一样，只是 environment name 改成 `testpypi`。

---

## 3. GitHub Actions CI — 自动测试

### 3.1 创建 CI 工作流

创建文件 `.github/workflows/ci.yml`：

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.12", "3.13"]

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install Poetry
        run: |
          pip install poetry
          poetry config virtualenvs.create false

      - name: Install dependencies
        run: poetry install --with dev

      - name: Run tests
        run: pytest -v

      # 可选：lint
      # - name: Lint with ruff
      #   run: |
      #     pip install ruff
      #     ruff check .
```

### 3.2 这个 CI 做了什么？

```
push 到 main / 提 PR
       │
       ▼
  开两台机器（Python 3.12 和 3.13）
       │
       ▼
  每台机器：checkout → 装 poetry → 装依赖 → 跑 pytest
       │
       ▼
  全部通过 → PR 上显示绿色 ✅
  任一失败 → PR 上显示红色 ❌
```

### 3.3 查看 CI 结果

- push 后去仓库的 **Actions** tab 查看
- PR 页面会自动显示 CI 状态
- 如果红了，点进去看哪一步失败的

---

## 4. GitHub Release — 版本发布

### 4.1 打 Release 的两种方式

**方式一：网页操作**

1. 去仓库 → **Releases** → **Create a new release**
2. 填写 tag（如 `v0.2.0`）、标题、release notes
3. 点 **Publish release**

**方式二：命令行**

```bash
# 1. 改版本号（在 pyproject.toml 里）
# version = "0.2.0"

# 2. 提交
git add pyproject.toml
git commit -m "chore: bump version to 0.2.0"

# 3. 打 tag
git tag v0.2.0

# 4. 推送 tag
git push origin v0.2.0
```

tag 推上去后，GitHub 会自动识别，你可以在 Releases 页面补充 release notes。

### 4.2 语义化版本（SemVer）

```
v 主版本 . 次版本 . 补丁版本
  │         │         │
  │         │         └─ bug 修复，向后兼容
  │         └─────────── 新功能，向后兼容
  └───────────────────── 破坏性变更，不兼容
```

示例：
- `v0.1.0` → 初始版本
- `v0.1.1` → 修了个 bug
- `v0.2.0` → 加了新功能
- `v1.0.0` → 第一个正式稳定版

---

## 5. PyPI 发布 — 让用户 pip install

### 5.1 手动发布（本地操作）

适合偶尔发一次、或者调试构建产物。

```bash
# 1. 构建
python scripts/build.py --clean

# 2. 检查产物（应该有 .whl 和 .tar.gz）
ls dist/

# 3. 先传 TestPyPI 测试
twine upload --repository testpypi dist/*

# 4. 从 TestPyPI 安装验证
pip install --index-url https://test.pypi.org/simple/ mochi-assistant

# 5. 确认没问题后，传正式 PyPI
twine upload dist/*
```

### 5.2 自动发布（GitHub Actions，推荐）

创建文件 `.github/workflows/release.yml`：

```yaml
name: Release to PyPI

on:
  release:
    types: [published]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install Poetry
        run: pip install poetry

      - name: Build package
        run: poetry build

      - name: Upload build artifacts
        uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/

  publish-pypi:
    needs: build
    runs-on: ubuntu-latest
    environment: pypi          # ← 对应 Trusted Publisher 里配置的 environment
    permissions:
      id-token: write          # ← OIDC 认证必须
    steps:
      - name: Download build artifacts
        uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist/

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
```

### 5.3 自动发布的工作流

```
你在 GitHub 上 Create Release (tag: v0.2.0)
       │
       ▼
GitHub Actions 检测到 release 事件
       │
       ▼
build job: checkout → poetry build → 生成 .whl + .tar.gz
       │
       ▼
publish-pypi job: 用 OIDC 认证 → 上传到 PyPI
       │
       ▼
用户可以 pip install mochi-assistant==0.2.0 了 🎉
```

### 5.4 如果不用 Trusted Publisher（用 API Token）

有些人更习惯用 API Token，步骤：

1. 去 [https://pypi.org/manage/account/token/](https://pypi.org/manage/account/token/) 创建 token
2. 去 GitHub 仓库 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**
   - Name: `PYPI_API_TOKEN`
   - Value: 你刚创建的 token（以 `pypi-` 开头）
3. `release.yml` 的 publish 步骤改成：

```yaml
      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          password: ${{ secrets.PYPI_API_TOKEN }}
```

> **推荐 Trusted Publisher**：不需要管理 token，更安全，token 不会过期。

---

## 6. 完整工作流：从代码到用户

日常开发和发布的标准流程：

```
日常开发
─────────────────────────────────────────────────
  1. 在 main 分支（或 feature 分支）开发
  2. push → CI 自动跑测试
  3. 测试通过 → merge 到 main


准备发布
─────────────────────────────────────────────────
  1. 更新 pyproject.toml 里的 version
  2. 写 CHANGELOG（可选但推荐）
  3. commit & push


发布
─────────────────────────────────────────────────
  1. 去 GitHub 创建 Release，tag 填 v0.2.0
  2. Actions 自动构建 + 上传 PyPI
  3. 去 PyPI 确认版本已更新


用户安装
─────────────────────────────────────────────────
  pip install mochi-assistant        # 最新版本
  pip install mochi-assistant==0.2.0 # 指定版本
```

### 版本号在哪里改？

`pyproject.toml` 第 3 行：

```toml
version = "0.2.0"   # ← 改这里
```

> **注意**：PyPI 不允许重复上传同版本号。每次发布必须改版本号，否则会报错 `400 Bad Request`。

---

## 7. 附录：常见问题

### Q: CI 红了怎么办？

去 Actions tab 点进去看日志。常见原因：
- 测试代码本身有 bug
- 依赖装不上（检查 pyproject.toml 的 dependencies）
- Python 版本不兼容

### Q: 上传 PyPI 报 403？

- 如果用 Token：检查 token 是否正确、是否有 `mochi-assistant` 项目的权限
- 如果用 Trusted Publisher：检查 environment name 是否和 YAML 里一致

### Q: 上传 PyPI 报 400 "File already exists"？

版本号重复了。PyPI 不允许覆盖已发布的版本，必须改 `pyproject.toml` 里的 `version`。

### Q: 我想先在 TestPyPI 测试？

创建另一个 workflow job 或单独的 workflow 文件，environment 改成 `testpypi`，target repository 改成 testpypi：

```yaml
      - name: Publish to TestPyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          repository-url: https://test.pypi.org/legacy/
          # 如果用 token 而非 Trusted Publisher：
          # password: ${{ secrets.TESTPYPI_API_TOKEN }}
```

### Q: `.github/workflows/` 目录放哪里？

```
Mochi/
├── .github/
│   └── workflows/
│       ├── ci.yml         # CI（测试）
│       └── release.yml    # 发布到 PyPI
├── mochi_assistant/
├── scripts/
├── pyproject.toml
└── ...
```

### Q: 两个 YAML 文件可以合并成一个吗？

可以。用 `on` 触发不同事件，用 `if` 条件控制 job 是否执行。但分开写更清晰，推荐分开。

### Q: 发布前需要手动跑测试吗？

不需要，CI 已经帮你跑了。但如果你想本地先跑一遍：
```bash
pytest -v
python scripts/build.py --check
```

### Q: Poetry 构建和 `python -m build` 有什么区别？

都是生成 `.whl` + `.tar.gz`。Mochi 用 Poetry 做 build backend，所以 `poetry build` 是最直接的方式。效果一样，只是入口不同。
