#!/usr/bin/env python3
"""核验 .github/workflows 里每个 action 钉法：sha 必须真的是注释里那个版本标签指向的提交。

现有断言只能证明"钉了 40 位 sha 且写了版本号"，证明不了 sha 与版本号相配 ——
把一个 sha 换成任意别的提交，形状检查照样通过。这一步补的就是这个洞。

退出码：0 = 全部一致；1 = 有 sha 与标签不符、标签在上游取不到、或钉法形状不合规。
不联网/取不到标签一律按失败处理（宁可红一次也不要"没判定当成通过"）。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

# 与 scripts/*.py 同一口径：Windows GBK 控制台下中文读数不能变成乱码
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if callable(_reconfigure):
        _reconfigure(encoding="utf-8", errors="replace")

PIN_RE = re.compile(r"^([\w./-]+)@([0-9a-f]{40})\s*#\s*(\S+)$")


def collect_pins(workflows_dir: str) -> list[tuple[str, str, str, str]]:
    """返回 (文件, 仓库, sha, 标签版本)；形状不合规的直接 sys.exit(1)。"""
    out = []
    for name in sorted(os.listdir(workflows_dir)):
        if not name.endswith((".yml", ".yaml")):
            continue
        with open(os.path.join(workflows_dir, name), encoding="utf-8") as fh:
            for lineno, ln in enumerate(fh.read().split("\n"), 1):
                s = ln.strip()
                if not s.startswith(("- uses:", "uses:")):
                    continue
                ref = s.split("uses:", 1)[1].strip()
                if ref.startswith("docker://") or "./" in ref.split("@")[0]:
                    continue  # 容器/本地 action 没有上游标签可对
                m = PIN_RE.match(ref)
                if not m:
                    print(
                        f"形状不合规 {name}:{lineno}：{ref}\n"
                        "  要求写成 `owner/repo@<40位sha>  # v1.2.3`（版本号缺失时"
                        "这道门无法核验 sha 是不是那个版本）"
                    )
                    sys.exit(1)
                sha, tag = m.group(2), m.group(3)
                out.append((name, m.group(1), sha, tag))
    return out


def resolve_tag(repo: str, version: str) -> str | None:
    """把上游标签解析成提交 sha（跟着附注标签的 ^{} 走）。"""
    ref = version if version.startswith("v") else "v" + version
    proc = subprocess.run(
        [
            "git",
            "ls-remote",
            f"https://github.com/{repo}",
            f"refs/tags/{ref}^{{}}",
            f"refs/tags/{ref}",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    peeled = None
    direct = None
    for line in proc.stdout.strip().split("\n"):
        if not line.strip():
            continue
        sha, _, name = line.partition("\t")
        if name.endswith("^{}"):
            peeled = sha
        elif name == f"refs/tags/{ref}":
            direct = sha
    return peeled or direct


def main(workflows_dir: str | None = None) -> int:
    if workflows_dir is None:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        workflows_dir = os.path.join(root, ".github", "workflows")
    pins = collect_pins(workflows_dir)
    if not pins:
        print("一个 action 引用都没看到 —— 工作流目录可能被挪走了")
        return 1
    bad = 0
    seen: dict[tuple[str, str, str], list[str]] = {}
    for name, repo, sha, version in pins:
        seen.setdefault((repo, sha, version), []).append(name)
    for (repo, sha, version), where in sorted(seen.items()):
        try:
            resolved = resolve_tag(repo, version)
        except Exception as exc:  # noqa: BLE001 - 网络/子进程失败都要变成读数
            print(f"FAIL {repo} #{version}: 上游解析失败 {exc!r}")
            resolved = None
        if resolved is None:
            print(
                f"FAIL {repo} #{version}: 取不到该标签（用于 {sorted(set(where))}）"
                "—— 标签被删/改名或未发布，同样按不通过处理"
            )
            bad += 1
        elif resolved != sha:
            print(
                f"FAIL {repo}: 钉的 sha {sha[:12]} 不是 #{version} 指向的提交"
                f"（上游是 {resolved[:12]}）；用在 {sorted(set(where))}"
            )
            bad += 1
        else:
            print(f"OK   {repo}@{sha[:12]} == #{version}")
    print(f"\n核验 {len(seen)} 组唯一钉法（共 {len(pins)} 处引用），不符 {bad} 组")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
