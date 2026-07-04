#!/usr/bin/env python3
"""
Mochi Agent 构建脚本
用于打包项目为 PyPI 分发包

用法:
    python scripts/build.py          # 构建 wheel + sdist
    python scripts/build.py --clean  # 清理旧构建后重新构建
    python scripts/build.py --check  # 构建并检查产物
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = PROJECT_ROOT / "dist"
BUILD_DIR = PROJECT_ROOT / "build"


def clean():
    """清理旧的构建产物"""
    for d in [DIST_DIR, BUILD_DIR]:
        if d.exists():
            shutil.rmtree(d)
            print(f"  ✓ 已清理: {d.name}/")
    # 清理 egg-info
    for egg in PROJECT_ROOT.glob("*.egg-info"):
        shutil.rmtree(egg)
        print(f"  ✓ 已清理: {egg.name}/")


def build():
    """执行 poetry build"""
    print("\n  🔨 正在构建...")
    result = subprocess.run(
        ["poetry", "build"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"  ✗ 构建失败:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)
    print(result.stdout)
    print("  ✓ 构建完成!")


def check_dist():
    """检查构建产物"""
    if not DIST_DIR.exists():
        print("  ✗ dist/ 目录不存在，请先构建", file=sys.stderr)
        sys.exit(1)

    files = list(DIST_DIR.iterdir())
    if not files:
        print("  ✗ dist/ 目录为空", file=sys.stderr)
        sys.exit(1)

    print("\n  📦 构建产物:")
    for f in sorted(files):
        size_kb = f.stat().st_size / 1024
        print(f"    {f.name}  ({size_kb:.1f} KB)")

    # 检查是否有 wheel 和 sdist
    has_wheel = any(f.suffix == ".whl" for f in files)
    has_sdist = any(f.suffix == ".gz" for f in files)
    print(f"\n  wheel: {'✓' if has_wheel else '✗'}  |  sdist: {'✓' if has_sdist else '✗'}")


def print_upload_instructions():
    """打印上传说明"""
    print("""
  ─────────────────────────────────────────────
  📤 上传到 PyPI:

    # 测试上传 (推荐先测试)
    twine upload --repository testpypi dist/*

    # 正式上传
    twine upload dist/*

  💡 如果尚未安装 twine:
    pip install twine
  ─────────────────────────────────────────────
""")


def main():
    parser = argparse.ArgumentParser(description="Mochi Agent 构建脚本")
    parser.add_argument("--clean", action="store_true", help="清理旧构建产物后重新构建")
    parser.add_argument("--check", action="store_true", help="构建并检查产物")
    args = parser.parse_args()

    print("\n  🐾 Mochi Agent Build")
    print("  ─────────────────────")

    if args.clean:
        clean()

    build()
    check_dist()
    print_upload_instructions()


if __name__ == "__main__":
    main()
