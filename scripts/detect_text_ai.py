#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
detect_text_ai.py — 检测文本中的 AI 味模式 (Detect AI-flavored patterns in text)

检测 TEXT-001 ~ TEXT-008 共 8 类 AI 生成文本的典型低质量模式。
Python 3.8+ 标准库零依赖。支持中文与英文文本。

用法:
    python3 detect_text_ai.py --file <文档路径> --json
    python3 detect_text_ai.py --text "综上所述，AI技术在当今社会具有重要意义" --json
    python3 detect_text_ai.py --file report.md --output report_ai.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Set, Tuple

# --------------------------------------------------------------------------- #
# 常量定义
# --------------------------------------------------------------------------- #

SEVERITY_WEIGHT = {
    "Blocker": 25,
    "Critical": 15,
    "Warning": 5,
}

# TEXT-001 套话开头（段落起始匹配）
CLICHE_OPENINGS = [
    "在当今社会", "在当今时代", "当今社会", "随着社会的发展",
    "随着技术的发展", "随着科技的发展", "随着信息技术的发展",
    "随着互联网的发展", "随着人工智能的发展",
    "众所周知", "众所周知地", "毋庸置疑",
    "近年来", "近年来，随着",
    "在信息化时代", "在数字化时代", "在大数据时代", "在人工智能时代",
    "自古以来", "从古至今",
    "In today's society", "In today's world", "With the development of",
    "In the modern era", "As we all know", "It is well known that",
    "In recent years", "Since the dawn of",
]

# TEXT-002 空泛表述
VAGUE_EXPRESSIONS = [
    "具有重要意义", "具有深远意义", "具有重要意义和作用", "具有重要作用",
    "发挥着重要作用", "发挥着关键作用", "起到了重要作用",
    "值得关注", "值得注意", "值得深思", "值得探讨",
    "不可或缺", "必不可少", "至关重要", "举足轻重",
    "日益增长", "日益重要", "日趋重要", "蓬勃发展",
    "提供了有力支持", "奠定了坚实基础", "开辟了新道路", "注入了新活力",
    "of great significance", "plays an important role",
    "is of great importance", "is worth noting", "is worth mentioning",
    "plays a key role", "plays a crucial role",
]

# TEXT-004 虚假自信
FALSE_CONFIDENCE = [
    "显然", "显然地", "显而易见",
    "毫无疑问", "毫无疑义", "毋庸置疑", "无可置疑",
    "必定", "必然", "必将", "必定会",
    "绝对", "绝对地", "绝对的",
    "一定", "一定会", "肯定会", "注定",
    "obviously", "clearly", "undoubtedly", "without a doubt",
    "certainly", "definitely", "absolutely", "it is evident that",
    "it goes without saying",
]

# TEXT-005 AI常用短语
AI_CATCHPHRASES = [
    "让我们深入探讨", "让我们深入", "让我们来", "让我们一起",
    "值得注意的是", "需要注意的是", "需要指出的是", "应当指出",
    "总而言之", "综上所述", "总的来说", "总体而言", "总之",
    "在此过程中", "在这一过程中", "在这个过程中",
    "这不仅...而且", "不仅...还", "一方面...另一方面",
    "众所周知", "如前所述", "正如我们所知",
    "在本文中，我们将", "接下来，我们将", "首先，其次，最后",
    "深入探讨", "深入分析", "深入剖析", "深度解析",
    "let's dive into", "let's explore", "let's delve into",
    "it is worth noting that", "it should be noted that",
    "in conclusion", "to sum up", "in summary", "all in all",
    "first and foremost", "last but not least",
    "in this article, we will", "in this blog post, we",
]

# 中英文停用词/虚词（用于信息密度计算）
CHINESE_STOPCHARS = set("的了是在我有和人这中大为以与及或之其也而则对于上下来去到被把将该些")
ENGLISH_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "of", "to", "in", "on", "at", "for", "with", "by", "as", "from",
    "and", "or", "but", "not", "this", "that", "these", "those", "it",
    "its", "they", "them", "their", "we", "you", "he", "she", "his",
    "her", "our", "your", "which", "who", "whom", "what", "when",
    "where", "why", "how", "can", "could", "will", "would", "should",
    "may", "might", "must", "shall", "do", "does", "did", "have",
    "has", "had", "been", "being",
}

# TEXT-008 虚假引用模式
CITATION_PATTERNS = [
    # (Smith et al., 2023) / (Smith, 2023) / (张三等, 2020)
    re.compile(r"\([A-Z][a-zA-Z]+(?:\s+(?:et al\.|and|&)\s+[A-Z][a-zA-Z]+)?\s*,\s*\d{4}[a-z]?\s*\)"),
    re.compile(r"\([\u4e00-\u9fa5]{2,4}(?:\s*等)?\s*[,，]\s*\d{4}\s*\)"),
    # [1] [Smith 2020]
    re.compile(r"\[[A-Z][a-zA-Z]+\s+\d{4}\]"),
    # Smith et al. (2023)
    re.compile(r"[A-Z][a-zA-Z]+\s+et al\.\s*\(\d{4}\)"),
]


# --------------------------------------------------------------------------- #
# 数据结构
# --------------------------------------------------------------------------- #

@dataclass
class Finding:
    pattern_id: str
    severity: str
    location: str
    symptom: str
    remedy: str


@dataclass
class TextReport:
    source: str  # 文件路径或 "<text>"
    findings: List[Finding] = field(default_factory=list)
    char_count: int = 0
    paragraph_count: int = 0


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #

def add(report: TextReport, pid: str, severity: str, location: str,
        symptom: str, remedy: str) -> None:
    report.findings.append(Finding(
        pattern_id=pid, severity=severity, location=location,
        symptom=symptom, remedy=remedy,
    ))


def split_paragraphs(text: str) -> List[Tuple[int, str]]:
    """按空行分段，返回 (起始行号, 段落文本) 列表。"""
    paragraphs: List[Tuple[int, str]] = []
    current: List[str] = []
    start_line = 1
    line_no = 0
    for raw in text.splitlines():
        line_no += 1
        if raw.strip() == "":
            if current:
                paragraphs.append((start_line, "\n".join(current)))
                current = []
            start_line = line_no + 1
        else:
            if not current:
                start_line = line_no
            current.append(raw)
    if current:
        paragraphs.append((start_line, "\n".join(current)))
    return paragraphs


def is_meaningful_char(ch: str) -> bool:
    """判断一个字符是否为实质内容字符（非标点、非空白、非虚词）。"""
    if ch.isspace():
        return False
    if ch in CHINESE_STOPCHARS:
        return False
    # 标点符号
    if ch in "，。、；：？！""''（）【】《》〈〉「」『』—…·,.:;!?\"'()[]{}<>-_/\\@#$%^&*+=|~`":
        return False
    return True


def lexical_diversity(text: str) -> float:
    """计算词汇多样性：唯一实质字符 / 总实质字符。值越低越空洞。"""
    chars = [c for c in text if is_meaningful_char(c)]
    if not chars:
        return 1.0
    return len(set(chars)) / len(chars)


def content_density(text: str) -> float:
    """计算内容密度：实质字符数 / 总字符数。"""
    if not text:
        return 0.0
    meaningful = sum(1 for c in text if is_meaningful_char(c))
    return meaningful / len(text)


def english_word_density(text: str) -> float:
    """英文文本的实义词密度（排除停用词）。"""
    words = re.findall(r"[A-Za-z]+", text)
    if not words:
        return -1.0  # 无英文词
    content = [w for w in words if w.lower() not in ENGLISH_STOPWORDS]
    return len(content) / len(words)


def line_of_offset(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


# --------------------------------------------------------------------------- #
# 各检测器
# --------------------------------------------------------------------------- #

def detect_text001_cliche_opening(report: TextReport, text: str,
                                   paragraphs: List[Tuple[int, str]]) -> None:
    """TEXT-001 套话开头：段落开头匹配套话模式。"""
    for start_line, para in paragraphs:
        # 取段落前 30 个字符作为开头判断
        head = para.lstrip()[:40]
        for opening in CLICHE_OPENINGS:
            if head.startswith(opening):
                add(report, "TEXT-001", "Critical", f"{report.source}:{start_line}",
                    f"套话开头: 段落以 '{opening}' 开头",
                    "删除套话开头，直接切入主题。第一句就应给出实质信息")
                break


def detect_text002_vague(report: TextReport, text: str) -> None:
    """TEXT-002 空泛表述：匹配无实质内容的空话。"""
    seen_spans: Set[int] = set()
    for expr in VAGUE_EXPRESSIONS:
        for m in re.finditer(re.escape(expr), text):
            if m.start() in seen_spans:
                continue
            seen_spans.add(m.start())
            ln = line_of_offset(text, m.start())
            add(report, "TEXT-002", "Warning", f"{report.source}:{ln}",
                f"空泛表述: '{expr}' 无具体信息",
                "用具体数据、事实或机制替代空泛修饰")


def detect_text003_over_structured(report: TextReport, text: str) -> None:
    """TEXT-003 过度结构化：列表过多/标题层次过深。"""
    lines = text.splitlines()
    # 统计 Markdown 列表项
    list_items = sum(1 for l in lines if re.match(r"^\s*([-*+]|\d+\.)\s+", l))
    # 统计标题层次
    max_heading_level = 0
    heading_count = 0
    for l in lines:
        m = re.match(r"^(#{1,6})\s", l)
        if m:
            heading_count += 1
            max_heading_level = max(max_heading_level, len(m.group(1)))
    total_lines = len([l for l in lines if l.strip()])
    # 列表项占比 > 50%
    if total_lines > 0 and list_items / total_lines > 0.5 and list_items > 10:
        add(report, "TEXT-003", "Warning", report.source,
            f"过度结构化: 列表项 {list_items} 行占总行数 "
            f"{list_items/total_lines*100:.0f}%，文本被列表淹没",
            "减少列表，用自然段落表达连贯论述")
    # 标题层次超过 4 级
    if max_heading_level >= 5:
        add(report, "TEXT-003", "Warning", report.source,
            f"过度结构化: 标题层级深达 H{max_heading_level}，层次过细",
            "标题层级控制在 3 级以内，深层内容用段落组织")
    # 标题数量过多（每 10 行正文超过 3 个标题）
    if total_lines > 0 and heading_count > 0 and total_lines / heading_count < 5:
        add(report, "TEXT-003", "Warning", report.source,
            f"过度结构化: {heading_count} 个标题 / {total_lines} 行正文，"
            "标题密度过高，像提纲不像文章",
            "合并小节，让每个标题下有足够实质内容")


def detect_text004_false_confidence(report: TextReport, text: str) -> None:
    """TEXT-004 虚假自信：显然/毫无疑问/必定/绝对/毋庸置疑。"""
    seen_spans: Set[int] = set()
    for word in FALSE_CONFIDENCE:
        for m in re.finditer(re.escape(word), text):
            if m.start() in seen_spans:
                continue
            seen_spans.add(m.start())
            ln = line_of_offset(text, m.start())
            add(report, "TEXT-004", "Warning", f"{report.source}:{ln}",
                f"虚假自信: '{word}' 表达过度确定性",
                "标注不确定性（如'通常''多数情况下''根据现有证据'），如实反映局限")


def detect_text005_catchphrase(report: TextReport, text: str) -> None:
    """TEXT-005 AI常用短语：让我们深入探讨/值得注意的是/总而言之。"""
    seen_spans: Set[int] = set()
    for phrase in AI_CATCHPHRASES:
        for m in re.finditer(re.escape(phrase), text, re.I):
            if m.start() in seen_spans:
                continue
            seen_spans.add(m.start())
            ln = line_of_offset(text, m.start())
            add(report, "TEXT-005", "Warning", f"{report.source}:{ln}",
                f"AI常用短语: '{m.group(0)}' 是AI生成文本的高频套话",
                "用自然的人类表达替换，删除过渡性废话")


def detect_text006_hollow(report: TextReport, text: str,
                           paragraphs: List[Tuple[int, str]]) -> None:
    """TEXT-006 信息空洞：段落长但信息密度低。"""
    for start_line, para in paragraphs:
        # 去掉段落内的 Markdown 标记后再统计
        clean = re.sub(r"[#*`>\-]", "", para)
        char_len = len([c for c in clean if not c.isspace()])
        if char_len < 100:
            continue
        diversity = lexical_diversity(clean)
        density = content_density(clean)
        # 触发条件：词汇多样性低（<0.5）或内容密度低（<0.6）且段落长
        if diversity < 0.45 or density < 0.55:
            add(report, "TEXT-006", "Warning", f"{report.source}:{start_line}",
                f"信息空洞: 段落 {char_len} 字但词汇多样性 {diversity:.2f}、"
                f"内容密度 {density:.2f} 偏低，实质信息少",
                "每段必须有具体事实/数据/机制，删除凑字数的修饰")


def detect_text007_repetition(report: TextReport, text: str,
                                paragraphs: List[Tuple[int, str]]) -> None:
    """TEXT-007 重复赘述：同一观点换多种方式重复。"""
    # 1) 完全相同的句子出现 2+ 次
    sentences: Dict[str, List[int]] = {}
    for start_line, para in paragraphs:
        for sent in re.split(r"[。.！!？?\n]+", para):
            s = sent.strip()
            if len(s) >= 12:  # 只看较长的句子
                sentences.setdefault(s, []).append(start_line)
    for sent, lines in sentences.items():
        if len(lines) >= 2:
            add(report, "TEXT-007", "Warning", f"{report.source}:{lines[0]}",
                f"重复赘述: 句子在 {len(lines)} 处重复出现 ('{sent[:30]}...')",
                "同一观点只说一次，删除重复表述")
    # 2) 高重叠的近似句（基于字符 bigram Jaccard）
    sent_list = list(sentences.keys())
    flagged: Set[int] = set()
    for i in range(len(sent_list)):
        if i in flagged:
            continue
        bi_i = set(_bigrams(sent_list[i]))
        if not bi_i:
            continue
        for j in range(i + 1, len(sent_list)):
            if j in flagged:
                continue
            bi_j = set(_bigrams(sent_list[j]))
            if not bi_j:
                continue
            overlap = len(bi_i & bi_j) / len(bi_i | bi_j)
            if overlap > 0.7 and len(sent_list[j]) >= 12:
                add(report, "TEXT-007", "Warning", report.source,
                    f"重复赘述: 两句高度相似（重叠 {overlap*100:.0f}%）"
                    f"'{sent_list[i][:25]}...' vs '{sent_list[j][:25]}...'",
                    "合并为一句，删除换汤不换药的重复")
                flagged.add(j)
                break


def _bigrams(s: str) -> List[str]:
    chars = [c for c in s if not c.isspace()]
    return [chars[i] + chars[i + 1] for i in range(len(chars) - 1)]


def detect_text008_fake_citation(report: TextReport, text: str) -> None:
    """TEXT-008 虚假引用：检测学术格式引用但无法验证。"""
    seen_spans: Set[int] = set()
    for pat in CITATION_PATTERNS:
        for m in pat.finditer(text):
            if m.start() in seen_spans:
                continue
            seen_spans.add(m.start())
            ln = line_of_offset(text, m.start())
            add(report, "TEXT-008", "Critical", f"{report.source}:{ln}",
                f"疑似虚假引用: '{m.group(0)}' 格式为学术引用，但无法程序验证其真实性",
                "只引用真实可验证的来源，附上可访问的链接或 DOI；"
                "若为虚构示例必须明确标注")


# --------------------------------------------------------------------------- #
# 主检测流程
# --------------------------------------------------------------------------- #

def analyze_text(text: str, source: str) -> TextReport:
    report = TextReport(source=source)
    report.char_count = len(text)
    paragraphs = split_paragraphs(text)
    report.paragraph_count = len(paragraphs)

    detect_text001_cliche_opening(report, text, paragraphs)
    detect_text002_vague(report, text)
    detect_text003_over_structured(report, text)
    detect_text004_false_confidence(report, text)
    detect_text005_catchphrase(report, text)
    detect_text006_hollow(report, text, paragraphs)
    detect_text007_repetition(report, text, paragraphs)
    detect_text008_fake_citation(report, text)

    return report


def compute_score(reports: List[TextReport]) -> int:
    total = 0
    for r in reports:
        for f in r.findings:
            total += SEVERITY_WEIGHT.get(f.severity, 0)
    return min(total, 100)


def filter_by_severity(reports: List[TextReport], minimum: str) -> List[TextReport]:
    order = {"Warning": 0, "Critical": 1, "Blocker": 2}
    min_idx = order.get(minimum, 0)
    out: List[TextReport] = []
    for r in reports:
        kept = [f for f in r.findings if order.get(f.severity, 0) >= min_idx]
        if kept:
            out.append(TextReport(source=r.source, char_count=r.char_count,
                                  paragraph_count=r.paragraph_count, findings=kept))
    return out


def build_json_report(reports: List[TextReport], score: int) -> Dict[str, Any]:
    severity_count = {"Blocker": 0, "Critical": 0, "Warning": 0}
    pattern_count: Dict[str, int] = {}
    for r in reports:
        for f in r.findings:
            severity_count[f.severity] = severity_count.get(f.severity, 0) + 1
            pattern_count[f.pattern_id] = pattern_count.get(f.pattern_id, 0) + 1
    return {
        "ai_flavor_score": score,
        "summary": {
            "sources_scanned": len(reports),
            "total_findings": sum(len(r.findings) for r in reports),
            "by_severity": severity_count,
            "by_pattern": dict(sorted(pattern_count.items())),
        },
        "gate_passed": severity_count["Blocker"] == 0 and severity_count["Critical"] == 0,
        "sources": [
            {
                "source": r.source,
                "char_count": r.char_count,
                "paragraph_count": r.paragraph_count,
                "findings": [asdict(f) for f in r.findings],
            }
            for r in reports if r.findings
        ],
    }


def print_human_report(reports: List[TextReport], score: int) -> None:
    print("=" * 72)
    print("反AI味检测报告 (Text Anti-AI-Flavor)")
    print("=" * 72)
    print(f"扫描文本源数: {len(reports)}")
    total = sum(len(r.findings) for r in reports)
    print(f"发现总数: {total}")
    print(f"AI味评分: {score}/100 (越低越好，0=无AI味)")
    severity_count = {"Blocker": 0, "Critical": 0, "Warning": 0}
    for r in reports:
        for f in r.findings:
            severity_count[f.severity] += 1
    print(f"  Blocker: {severity_count['Blocker']}  "
          f"Critical: {severity_count['Critical']}  "
          f"Warning: {severity_count['Warning']}")
    gate = severity_count["Blocker"] == 0 and severity_count["Critical"] == 0
    print(f"质量门禁: {'PASS' if gate else 'FAIL (存在 Critical/Blocker，不可交付)'}")
    print("-" * 72)
    for r in reports:
        if not r.findings:
            continue
        print(f"\n来源: {r.source}  ({r.char_count} 字, {r.paragraph_count} 段)")
        for f in r.findings:
            print(f"  [{f.severity}] {f.pattern_id} {f.location}")
            print(f"    症状: {f.symptom}")
            print(f"    修复: {f.remedy}")
    print("\n" + "=" * 72)


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="detect_text_ai.py",
        description="检测文本中的 AI 味模式 (TEXT-001 ~ TEXT-008)",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", help="要检测的文档文件路径")
    group.add_argument("--text", help="直接检测传入的文本字符串")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    parser.add_argument("--output", help="将报告写入指定文件（默认输出到 stdout）")
    parser.add_argument("--min-severity",
                        choices=["Warning", "Critical", "Blocker"],
                        default="Warning",
                        help="只显示该级别及以上的发现")
    args = parser.parse_args(argv)

    reports: List[TextReport] = []

    if args.text is not None:
        reports.append(analyze_text(args.text, "<text>"))
    elif args.file:
        if not os.path.isfile(args.file):
            print(f"错误: 文件不存在: {args.file}", file=sys.stderr)
            return 2
        try:
            with open(args.file, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError as e:
            print(f"错误: 读取文件失败: {e}", file=sys.stderr)
            return 2
        reports.append(analyze_text(content, os.path.abspath(args.file)))

    reports = filter_by_severity(reports, args.min_severity)
    score = compute_score(reports)

    if args.json:
        payload = build_json_report(reports, score)
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"报告已写入: {args.output}", file=sys.stderr)
        else:
            print(text)
    else:
        print_human_report(reports, score)
    return 0


if __name__ == "__main__":
    sys.exit(main())
