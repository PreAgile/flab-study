#!/usr/bin/env python3
"""
Generate Excalidraw JSON + SVG for chapter 02 diagrams.

Usage:
    python3 gen_diagrams.py

Outputs all priority diagrams into the current directory.
"""

import json
import os
import random
from pathlib import Path
from textwrap import dedent

# ─────────────────────────────────────────────────────────────
# Color palette (matches existing 02-compile-flow.svg conventions)
# ─────────────────────────────────────────────────────────────
PALETTE = {
    "blue":      {"stroke": "#1565c0", "fill": "#e3f2fd"},  # .java / source
    "purple":    {"stroke": "#6a1b9a", "fill": "#f3e5f5"},  # javac
    "green":     {"stroke": "#2e7d32", "fill": "#e8f5e9"},  # .class / bytecode
    "orange":    {"stroke": "#ef6c00", "fill": "#fff3e0"},  # ClassLoader
    "pink":      {"stroke": "#c2185b", "fill": "#fce4ec"},  # Metaspace / heap
    "amber":     {"stroke": "#f57c00", "fill": "#fff8e1"},  # Interpreter
    "deep_orange":{"stroke": "#d84315", "fill": "#ffe0b2"}, # C1
    "red":       {"stroke": "#c62828", "fill": "#ffcdd2"},  # C2
    "gray":      {"stroke": "#424242", "fill": "#eeeeee"},  # CPU / native
    "teal":      {"stroke": "#00695c", "fill": "#e0f2f1"},  # Code Cache
    "indigo":    {"stroke": "#283593", "fill": "#e8eaf6"},  # Special
    "brown":     {"stroke": "#5d4037", "fill": "#efebe9"},  # Bootstrap
}

FONT_FAMILY = 2  # Excalidraw's "Normal" handwriting → use 2 (Helvetica) for legibility


def rand_seed():
    return random.randint(1, 2_000_000_000)


# ─────────────────────────────────────────────────────────────
# Element factories
# ─────────────────────────────────────────────────────────────

def _base_props(elem_id):
    return {
        "id": elem_id,
        "angle": 0,
        "fillStyle": "solid",
        "strokeWidth": 2,
        "strokeStyle": "solid",
        "roughness": 1,
        "opacity": 100,
        "groupIds": [],
        "frameId": None,
        "seed": rand_seed(),
        "version": 1,
        "versionNonce": rand_seed(),
        "isDeleted": False,
        "boundElements": [],
        "updated": 1778553526610,
        "link": None,
        "locked": False,
    }


def rect(eid, x, y, w, h, color="gray", rounded=True):
    p = _base_props(eid)
    p.update({
        "type": "rectangle",
        "x": x, "y": y, "width": w, "height": h,
        "strokeColor": PALETTE[color]["stroke"],
        "backgroundColor": PALETTE[color]["fill"],
        "roundness": {"type": 3} if rounded else None,
    })
    return p


def text(eid, x, y, content, size=16, color="#1e1e1e", w=None, align="center"):
    # Approx text width
    lines = content.split("\n")
    max_line = max(len(l) for l in lines)
    auto_w = max_line * size * 0.6
    auto_h = len(lines) * size * 1.25
    p = _base_props(eid)
    p.update({
        "type": "text",
        "x": x, "y": y,
        "width": w if w else auto_w,
        "height": auto_h,
        "strokeColor": color,
        "backgroundColor": "transparent",
        "roundness": None,
        "text": content,
        "fontSize": size,
        "fontFamily": FONT_FAMILY,
        "textAlign": align,
        "verticalAlign": "top",
        "baseline": int(size * 0.9),
        "containerId": None,
        "originalText": content,
        "lineHeight": 1.25,
        "autoResize": True,
    })
    return p


def text_in_box(eid, x, y, w, h, content, size=16, color="#1e1e1e"):
    """Text centered inside a box at (x,y,w,h)."""
    lines = content.split("\n")
    text_h = len(lines) * size * 1.25
    text_y = y + (h - text_h) / 2
    return text(eid, x + 4, text_y, content, size=size, color=color, w=w - 8, align="center")


def arrow(eid, x1, y1, x2, y2, color="#1e1e1e", dashed=False):
    p = _base_props(eid)
    p.update({
        "type": "arrow",
        "x": x1, "y": y1,
        "width": x2 - x1, "height": y2 - y1,
        "strokeColor": color,
        "backgroundColor": "transparent",
        "strokeStyle": "dashed" if dashed else "solid",
        "roundness": {"type": 2},
        "points": [[0, 0], [x2 - x1, y2 - y1]],
        "lastCommittedPoint": None,
        "startBinding": None,
        "endBinding": None,
        "startArrowhead": None,
        "endArrowhead": "arrow",
    })
    return p


def line(eid, x1, y1, x2, y2, color="#666", dashed=False):
    p = _base_props(eid)
    p.update({
        "type": "line",
        "x": x1, "y": y1,
        "width": x2 - x1, "height": y2 - y1,
        "strokeColor": color,
        "backgroundColor": "transparent",
        "strokeStyle": "dashed" if dashed else "solid",
        "roundness": {"type": 2},
        "points": [[0, 0], [x2 - x1, y2 - y1]],
        "lastCommittedPoint": None,
    })
    return p


# ─────────────────────────────────────────────────────────────
# Excalidraw wrapper
# ─────────────────────────────────────────────────────────────

def make_excalidraw(elements):
    return {
        "type": "excalidraw",
        "version": 2,
        "source": "https://excalidraw.com",
        "elements": elements,
        "appState": {
            "gridSize": 20,
            "viewBackgroundColor": "#ffffff",
        },
        "files": {},
    }


# ─────────────────────────────────────────────────────────────
# SVG renderer (lightweight, only handles types we use)
# ─────────────────────────────────────────────────────────────

SVG_FONT = "-apple-system,BlinkMacSystemFont,&apos;Apple SD Gothic Neo&apos;,&apos;Pretendard&apos;,&apos;Noto Sans KR&apos;,&apos;Malgun Gothic&apos;,&apos;Helvetica Neue&apos;,Helvetica,Arial,sans-serif"


def _bounds(elements):
    pad = 30
    xs, ys, x2s, y2s = [], [], [], []
    for e in elements:
        x, y = e["x"], e["y"]
        if e["type"] == "arrow" or e["type"] == "line":
            # treat both endpoints
            for px, py in e["points"]:
                xs.append(x + px); ys.append(y + py)
                x2s.append(x + px); y2s.append(y + py)
        else:
            w, h = e.get("width", 0), e.get("height", 0)
            xs.append(x); ys.append(y)
            x2s.append(x + w); y2s.append(y + h)
    minx, miny = min(xs) - pad, min(ys) - pad
    maxx, maxy = max(x2s) + pad, max(y2s) + pad
    return minx, miny, maxx - minx, maxy - miny


def to_svg(elements, title=None):
    minx, miny, w, h = _bounds(elements)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{minx:.0f} {miny:.0f} {w:.0f} {h:.0f}" '
        f'width="{w:.0f}" height="{h:.0f}" '
        f'font-family="{SVG_FONT}">',
        '<defs>',
        '<marker id="arrowhead" viewBox="0 0 10 10" refX="9" refY="5" '
        'markerUnits="strokeWidth" markerWidth="6" markerHeight="6" orient="auto">',
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#1e1e1e"/>',
        '</marker>',
        '</defs>',
        f'<rect x="{minx:.0f}" y="{miny:.0f}" width="{w:.0f}" height="{h:.0f}" fill="#ffffff"/>',
    ]

    # Render in z-order: rectangles first, then arrows/lines, then text on top.
    for e in elements:
        if e["type"] == "rectangle":
            rx = 8 if e.get("roundness") else 0
            parts.append(
                f'<rect x="{e["x"]:.0f}" y="{e["y"]:.0f}" '
                f'width="{e["width"]:.0f}" height="{e["height"]:.0f}" '
                f'rx="{rx}" ry="{rx}" '
                f'stroke="{e["strokeColor"]}" fill="{e["backgroundColor"]}" '
                f'stroke-width="{e["strokeWidth"]}"/>'
            )

    for e in elements:
        if e["type"] in ("arrow", "line"):
            x1 = e["x"] + e["points"][0][0]
            y1 = e["y"] + e["points"][0][1]
            x2 = e["x"] + e["points"][-1][0]
            y2 = e["y"] + e["points"][-1][1]
            dash = ' stroke-dasharray="6 4"' if e.get("strokeStyle") == "dashed" else ""
            marker = ' marker-end="url(#arrowhead)"' if e["type"] == "arrow" else ""
            parts.append(
                f'<path d="M {x1:.0f},{y1:.0f} L {x2:.0f},{y2:.0f}" '
                f'stroke="{e["strokeColor"]}" fill="none" '
                f'stroke-width="{e["strokeWidth"]}" stroke-linecap="round" '
                f'stroke-linejoin="round"{dash}{marker}/>'
            )

    for e in elements:
        if e["type"] == "text":
            lines = e["text"].split("\n")
            line_h = e["fontSize"] * 1.25
            for i, line in enumerate(lines):
                # text-anchor based on textAlign
                ta = e.get("textAlign", "left")
                anchor = {"left": "start", "center": "middle", "right": "end"}[ta]
                if ta == "center":
                    tx = e["x"] + e["width"] / 2
                elif ta == "right":
                    tx = e["x"] + e["width"]
                else:
                    tx = e["x"]
                ty = e["y"] + (i + 1) * line_h - e["fontSize"] * 0.25
                line_esc = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                parts.append(
                    f'<text x="{tx:.0f}" y="{ty:.0f}" '
                    f'text-anchor="{anchor}" '
                    f'font-size="{e["fontSize"]}" '
                    f'fill="{e["strokeColor"]}">{line_esc}</text>'
                )

    parts.append('</svg>')
    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────
# Helper: box+text combo
# ─────────────────────────────────────────────────────────────
_id_counter = [0]
def nid(prefix="el"):
    _id_counter[0] += 1
    return f"{prefix}_{_id_counter[0]}"


def box(x, y, w, h, label, color="gray", text_size=16, rounded=True):
    """Create rect + centered text. Returns list of 2 elements."""
    return [
        rect(nid("box"), x, y, w, h, color=color, rounded=rounded),
        text_in_box(nid("txt"), x, y, w, h, label, size=text_size),
    ]


# ─────────────────────────────────────────────────────────────
# DIAGRAM 1: javac 4 stages (Lexer → Parser → APT → SemAnalysis → Bytecode Gen)
# ─────────────────────────────────────────────────────────────

def diagram_javac_stages():
    els = []
    # Title
    els.append(text(nid(), 50, 30, "javac: .java → .class (5단계)", size=24, color="#1e1e1e", align="left"))
    els.append(text(nid(), 50, 62, "각 단계가 한 가지 일만 한다 — Lombok 같은 도구가 끼어들 수 있는 이유", size=13, color="#666", align="left"))

    # Input
    els += box(50, 110, 160, 70, ".java\n(소스 텍스트)", color="blue")

    # 5 stages
    stages = [
        ("1. Lexer\n(Tokenization)",          260,  110, "purple"),
        ("2. Parser\n(AST 생성)",              460,  110, "purple"),
        ("3. Annotation\nProcessor",           660,  110, "indigo"),
        ("4. Semantic\nAnalysis",              860,  110, "purple"),
        ("5. Bytecode\nGeneration",           1060,  110, "purple"),
    ]
    for label, x, y, color in stages:
        els += box(x, y, 160, 70, label, color=color, text_size=15)

    # Arrows between
    for sx in [210, 420, 620, 820, 1020]:
        els.append(arrow(nid(), sx, 145, sx + 40, 145))

    # Output
    els += box(1260, 110, 160, 70, ".class\n(바이트코드)", color="green")
    els.append(arrow(nid(), 1220, 145, 1260, 145))

    # Detail callouts under each stage
    details = [
        (260, 200, "글자 → 토큰",      ["int, c, =, a, +, b, ;"]),
        (460, 200, "토큰 → AST",       ["VarDecl(int, c,",  "  BinaryOp(+,",  "    a, b))"]),
        (660, 200, "★ Lombok/MapStruct", ["@Getter →",  "메서드 노드 삽입", "라운드 반복"]),
        (860, 200, "타입/스코프 검사",   ["int x = \"a\" →",  "컴파일 에러", "+ Desugar"]),
        (1060, 200, "AST 후위순회",     ["iload_1", "iload_2", "iadd", "istore_3"]),
    ]
    for x, y, head, lines in details:
        els.append(text(nid(), x, y, head, size=12, color="#333", w=170, align="center"))
        els.append(text(nid(), x, y + 22, "\n".join(lines), size=11, color="#666", w=170, align="center"))

    # Note
    note_y = 360
    els.append(text(nid(), 50, note_y, "왜 5단계로 쪼갰나?", size=16, color="#1e1e1e", align="left"))
    els.append(text(nid(), 50, note_y + 30,
                    "• Lexer/Parser 재사용 → IDE, formatter, Lombok이 모두 같은 API 사용\n"
                    "• AST가 만들어진 직후에 Annotation Processor가 끼어들 수 있는 \"틈\"이 생김\n"
                    "• Semantic Analysis가 분리돼야 타입 검사 알고리즘 디버깅 가능\n"
                    "• 각 단계가 한 가지 일만 하면 컴파일러 자체의 테스트·확장이 쉬워짐",
                    size=13, color="#444", align="left"))

    return els


# ─────────────────────────────────────────────────────────────
# DIAGRAM 2: ClassLoader 3 phases + parent delegation tree
# ─────────────────────────────────────────────────────────────

def diagram_classloader():
    els = []
    els.append(text(nid(), 50, 30, "ClassLoader: .class → Metaspace (3단계 + 부모 위임)", size=24, align="left"))
    els.append(text(nid(), 50, 62, "Loading → Linking(Verify/Prepare/Resolve) → Initialization", size=13, color="#666", align="left"))

    # Left side: 3 phases vertically
    els.append(text(nid(), 50, 110, "[3단계 로딩 흐름]", size=15, color="#1e1e1e", align="left"))

    # Phase 1: Loading
    els += box(50, 140, 280, 70, "1. Loading\nbyte[] 읽기 (파일/네트워크/메모리)", color="orange", text_size=14)
    els.append(arrow(nid(), 190, 215, 190, 245))

    # Phase 2: Linking (with 3 sub-phases)
    els += box(50, 250, 280, 200, "", color="amber")
    els.append(text(nid(), 60, 260, "2. Linking", size=15, color="#1e1e1e", align="left"))
    els += box(70, 290, 240, 40, "2a. Verification\nMagic, stack, type 검사", color="amber", text_size=12)
    els.append(arrow(nid(), 190, 335, 190, 345))
    els += box(70, 350, 240, 40, "2b. Preparation\nstatic 필드 = 기본값 (0/null)", color="amber", text_size=12)
    els.append(arrow(nid(), 190, 395, 190, 405))
    els += box(70, 410, 240, 35, "2c. Resolution (lazy)\n심볼 → 실제 참조", color="amber", text_size=12)
    els.append(arrow(nid(), 190, 455, 190, 485))

    # Phase 3: Initialization
    els += box(50, 490, 280, 80, "3. Initialization\n<clinit> 실행\n(static 블록 + 필드 할당)", color="deep_orange", text_size=14)
    els.append(arrow(nid(), 190, 575, 190, 605))

    # Output: Metaspace
    els += box(50, 610, 280, 90, "Metaspace에 저장\n(Class 객체 + CP + 메서드 메타\n+ vtable + 필드 레이아웃)", color="pink", text_size=13)

    # Right side: parent delegation tree
    els.append(text(nid(), 480, 110, "[부모 위임 모델]", size=15, color="#1e1e1e", align="left"))
    els.append(text(nid(), 480, 132, "자식이 부모에게 먼저 물어봄 → 보안·공유·격리", size=12, color="#666", align="left"))

    # Tree boxes (vertical)
    els += box(550, 170, 220, 55, "Bootstrap ClassLoader\n(C++, java.lang.*)", color="brown", text_size=13)
    els.append(arrow(nid(), 660, 250, 660, 230))  # arrows point upward (child→parent)

    els += box(550, 255, 220, 55, "Platform ClassLoader\n(JDK 9+, java.sql/xml/...)", color="indigo", text_size=13)
    els.append(arrow(nid(), 660, 335, 660, 315))

    els += box(550, 340, 220, 55, "Application ClassLoader\n(클래스패스/모듈패스)", color="orange", text_size=13)
    els.append(arrow(nid(), 580, 425, 580, 405))
    els.append(arrow(nid(), 740, 425, 740, 405))

    els += box(480, 430, 200, 55, "Custom ClassLoader 1\n(Tomcat 웹앱 A)", color="amber", text_size=12)
    els += box(700, 430, 200, 55, "Custom ClassLoader 2\n(Tomcat 웹앱 B)", color="amber", text_size=12)

    # Legend
    els.append(text(nid(), 480, 530, "위로 화살표 = \"이거 갖고 있어?\" 위임", size=12, color="#666", align="left"))
    els.append(text(nid(), 480, 552, "→ 같은 java.lang.Object를 모두 공유", size=12, color="#666", align="left"))
    els.append(text(nid(), 480, 574, "→ 웹앱 A/B가 서로 격리됨", size=12, color="#666", align="left"))

    return els


# ─────────────────────────────────────────────────────────────
# DIAGRAM 3: Tiered Compilation 5-tier ladder
# ─────────────────────────────────────────────────────────────

def diagram_tiered():
    els = []
    els.append(text(nid(), 50, 30, "Tiered Compilation (5단)", size=24, align="left"))
    els.append(text(nid(), 50, 62, "L0 → L3 → L4 (대부분 메서드의 승격 경로)", size=13, color="#666", align="left"))

    tiers = [
        ("Level 0",  "Interpreter",           "no profiling",                   "모든 메서드의 출발점", "amber"),
        ("Level 1",  "C1",                    "no profiling",                   "Trivial 메서드 (getter/setter) — 끝", "deep_orange"),
        ("Level 2",  "C1",                    "with counters",                  "C2 큐 막힐 때 우회용", "deep_orange"),
        ("Level 3",  "C1",                    "FULL profiling",                 "★ 메서드 인자 타입·분기 빈도·null 빈도 수집", "deep_orange"),
        ("Level 4",  "C2",                    "with profile data",              "★ Peak: inline + EA + vectorization", "red"),
    ]

    y = 110
    box_h = 75
    gap = 20
    for i, (level, compiler, profile, role, color) in enumerate(tiers):
        ty = y + i * (box_h + gap)
        # Level number
        els += box(50, ty, 100, box_h, level, color=color, text_size=18)
        # Compiler
        els += box(170, ty, 130, box_h, compiler, color="gray", text_size=18)
        # Profile
        els += box(320, ty, 200, box_h, profile, color="indigo", text_size=14)
        # Role
        els += box(540, ty, 540, box_h, role, color="teal", text_size=14)

    # Promotion arrows on the right
    arr_x = 1100
    for i in range(len(tiers) - 1):
        ty1 = y + i * (box_h + gap) + box_h
        ty2 = y + (i + 1) * (box_h + gap)
        els.append(arrow(nid(), arr_x, ty1, arr_x, ty2))

    # Side notes
    note_x = 1130
    els.append(text(nid(), note_x, y + 5, "카운터\n임계치", size=12, color="#666", w=80, align="left"))
    thresholds = [
        ("L0→L3", "~2000회"),
        ("L0→L1", "trivial 한정"),
        ("L0→L2", "C2 큐 막힐 때"),
        ("L3→L4", "~15000회"),
    ]
    for i, (path, val) in enumerate(thresholds):
        ty = y + (i + 1) * (box_h + gap) - 18
        els.append(text(nid(), note_x, ty, f"{path}\n{val}", size=11, color="#444", w=120, align="left"))

    # Bottom note
    bottom_y = y + 5 * (box_h + gap) + 20
    els.append(text(nid(), 50, bottom_y,
                    "왜 C1과 C2를 둘 다? — C1이 빠르게 native 공급(워밍업) + Profile 수집 / C2가 그 Profile로 공격적 최적화(peak)",
                    size=13, color="#444", align="left"))

    return els


# ─────────────────────────────────────────────────────────────
# DIAGRAM 4: Method call entry pointers (i2i, i2c, c2i, compiled)
# ─────────────────────────────────────────────────────────────

def diagram_method_call():
    els = []
    els.append(text(nid(), 50, 30, "메서드 호출: Interpreter ↔ Compiled 사이의 4가지 entry", size=24, align="left"))
    els.append(text(nid(), 50, 62, "컴파일 완료 시 entry pointer만 갈아끼우면 다음 호출부터 자동으로 native로", size=13, color="#666", align="left"))

    # Two big boxes: Interpreter world / Compiled world
    els += box(80, 120, 380, 280, "", color="amber")
    els.append(text(nid(), 100, 135, "Interpreter 세계", size=18, color="#1e1e1e", align="left"))
    els.append(text(nid(), 100, 162, "bytecode 한 줄씩 해석", size=12, color="#666", align="left"))

    els += box(720, 120, 380, 280, "", color="teal")
    els.append(text(nid(), 740, 135, "Compiled 세계 (Code Cache)", size=18, color="#1e1e1e", align="left"))
    els.append(text(nid(), 740, 162, "JIT이 만든 native code", size=12, color="#666", align="left"))

    # Inside interpreter
    els += box(110, 200, 320, 60, "Caller (interpreter)", color="amber", text_size=14)
    els += box(110, 290, 320, 60, "Callee (interpreter)", color="amber", text_size=14)
    els.append(arrow(nid(), 270, 265, 270, 285))

    # Inside compiled
    els += box(750, 200, 320, 60, "Caller (compiled native)", color="teal", text_size=14)
    els += box(750, 290, 320, 60, "Callee (compiled native)", color="teal", text_size=14)
    els.append(arrow(nid(), 910, 265, 910, 285))

    # Cross arrows with labels
    # i2i (interp caller → interp callee): label inside interpreter box
    els.append(text(nid(), 285, 268, "_i2i_entry", size=11, color="#444", align="center", w=80))

    # _from_compiled_entry
    els.append(text(nid(), 925, 268, "_from_compiled_entry", size=11, color="#444", align="center", w=170))

    # i2c: interp caller → compiled callee
    els.append(arrow(nid(), 430, 225, 720, 315))
    els.append(text(nid(), 540, 245, "_i2c_entry (adapter)", size=12, color="#1565c0", align="left"))
    els.append(text(nid(), 540, 263, "interp → compiled", size=11, color="#666", align="left"))

    # c2i: compiled caller → interp callee
    els.append(arrow(nid(), 720, 225, 430, 315))
    els.append(text(nid(), 540, 285, "_c2i_entry (adapter)", size=12, color="#c2185b", align="left"))
    els.append(text(nid(), 540, 303, "compiled → interp", size=11, color="#666", align="left"))

    # Legend below
    legend_y = 440
    els.append(text(nid(), 50, legend_y, "각 메서드 메타데이터 안의 4개 entry pointer:", size=15, color="#1e1e1e", align="left"))
    legend_items = [
        ("_i2i_entry",            "interp → interp 직접 호출"),
        ("_i2c_entry",            "interp → compiled (adapter가 calling convention 변환)"),
        ("_c2i_entry",            "compiled → interp (adapter가 역변환)"),
        ("_from_compiled_entry",  "compiled → compiled 직접 점프"),
    ]
    for i, (name, desc) in enumerate(legend_items):
        ly = legend_y + 30 + i * 25
        els.append(text(nid(), 50, ly, f"• {name}", size=13, color="#1565c0", align="left"))
        els.append(text(nid(), 260, ly, desc, size=13, color="#444", align="left"))

    # Big arrow underneath: compilation completion event
    note_y = legend_y + 160
    els.append(text(nid(), 50, note_y, "★ JIT 컴파일 완료 시: entry pointer를 native code 주소로 갱신",
                    size=14, color="#c62828", align="left"))
    els.append(text(nid(), 50, note_y + 22, "  → 호출자 코드는 안 바꿈. 다음 호출자부터 자동으로 native로 점프",
                    size=12, color="#666", align="left"))

    return els


# ─────────────────────────────────────────────────────────────
# DIAGRAM 5: JVM Memory Layout
# ─────────────────────────────────────────────────────────────

def diagram_memory():
    els = []
    els.append(text(nid(), 50, 30, "JVM 프로세스 메모리 레이아웃", size=24, align="left"))
    els.append(text(nid(), 50, 62, "각 영역이 무엇을 담고 누가 만들고 누가 GC하는가", size=13, color="#666", align="left"))

    # Main column
    sections = [
        ("Heap (객체)",                  "pink",   "new Foo() 결과물\nGC 대상 (G1/ZGC/Shenandoah)", "JIT/Interpreter"),
        ("Metaspace (클래스 메타)",      "orange", "Class 객체, Constant Pool,\n메서드 메타데이터, vtable",        "ClassLoader"),
        ("★ Code Cache (native code)",   "teal",   "JIT 산출물 (C1/C2)\nSegmented (JDK 9+)\n기본 240MB", "JIT"),
        ("JVM Stack (스레드별)",         "amber",  "프레임, 지역 변수,\noperand stack",            "각 스레드"),
        ("Native Stack (C/C++)",         "gray",   "JNI 호출, native 메서드",                       "OS"),
    ]
    y = 110
    box_h = 110
    gap = 18
    for i, (name, color, contents, who) in enumerate(sections):
        ty = y + i * (box_h + gap)
        els += box(80, ty, 400, box_h, "", color=color, rounded=True)
        els.append(text(nid(), 100, ty + 15, name, size=18, color="#1e1e1e", align="left"))
        els.append(text(nid(), 100, ty + 45, contents, size=12, color="#444", align="left"))
        els.append(text(nid(), 100, ty + 82, f"채우는 주체: {who}", size=11, color="#666", align="left"))

    # Right side: Code Cache zoom-in (segmented)
    cc_x = 560
    cc_y = 110
    els.append(text(nid(), cc_x, cc_y, "★ Code Cache 내부 (JDK 9+ Segmented)", size=15, color="#1e1e1e", align="left"))
    cc_segs = [
        ("Non-method",          "Interpreter 어셈블리,\nadapter, stub",        "indigo"),
        ("Profiled methods",    "C1 컴파일 결과\n(deopt 가능)",                "deep_orange"),
        ("Non-profiled methods","C2 컴파일 결과\n(안정, deopt 드뭄)",          "red"),
    ]
    for i, (name, desc, color) in enumerate(cc_segs):
        sy = cc_y + 35 + i * 100
        els += box(cc_x, sy, 380, 85, "", color=color)
        els.append(text(nid(), cc_x + 15, sy + 12, name, size=16, color="#1e1e1e", align="left"))
        els.append(text(nid(), cc_x + 15, sy + 38, desc, size=12, color="#444", align="left"))

    # Arrow from Code Cache main to zoom
    els.append(arrow(nid(), 480, cc_y + 105, cc_x - 5, cc_y + 105))

    # Bottom note
    note_y = y + len(sections) * (box_h + gap) + 30
    els.append(text(nid(), 50, note_y, "Code Cache가 가득 차면? → JIT 중단 → 모든 새 메서드는 인터프리터 → 성능 폭락",
                    size=13, color="#c62828", align="left"))
    els.append(text(nid(), 50, note_y + 25, "튜닝: -XX:ReservedCodeCacheSize=512m (기본 240MB)",
                    size=12, color="#666", align="left"))

    return els


# ─────────────────────────────────────────────────────────────
# DIAGRAM 6: 7-Stage main flow (replacing existing 02-compile-flow but more detailed)
# ─────────────────────────────────────────────────────────────

def diagram_7_stage():
    els = []
    els.append(text(nid(), 50, 30, ".java → CPU: 7-Stage 전체 흐름", size=24, align="left"))
    els.append(text(nid(), 50, 62, "각 박스를 클릭하면 (실제 문서에선 해당 Stage 절로 점프)", size=13, color="#666", align="left"))

    stages = [
        ("1. .java\n(텍스트)",                "blue",         50,  110),
        ("2. javac\n(컴파일러)",              "purple",       250, 110),
        ("3. .class\n(바이트코드)",           "green",        450, 110),
        ("4. ClassLoader\n→ Metaspace",       "orange",       650, 110),
        ("5. Interpreter\n(Template)",        "amber",        850, 110),
        ("6a. C1 JIT",                        "deep_orange",  1050, 30),
        ("6b. C2 JIT",                        "red",          1050, 190),
        ("7. Code Cache\n(native code)",      "teal",         1250, 110),
        ("8. CPU 실행",                       "gray",         1450, 110),
    ]
    for label, color, x, y in stages:
        els += box(x, y, 160, 90, label, color=color, text_size=15)

    # Main flow arrows
    arrows = [
        (210, 155, 250, 155),   # 1→2
        (410, 155, 450, 155),   # 2→3
        (610, 155, 650, 155),   # 3→4
        (810, 155, 850, 155),   # 4→5
        (1010, 130, 1050, 75),  # 5→6a
        (1010, 180, 1050, 235), # 5→6b
        (1210, 75, 1250, 130),  # 6a→7
        (1210, 235, 1250, 180), # 6b→7
        (1410, 155, 1450, 155), # 7→8
    ]
    for x1, y1, x2, y2 in arrows:
        els.append(arrow(nid(), x1, y1, x2, y2))

    # Interpreter direct path (bypass JIT)
    els.append(arrow(nid(), 1010, 200, 1450, 200, color="#999"))
    els.append(text(nid(), 1100, 210, "(interp 직접 실행도 가능)", size=11, color="#999", align="left"))

    # Deopt arrow (dashed, backwards)
    els.append(arrow(nid(), 1250, 230, 1010, 230, color="#c62828", dashed=True))
    els.append(text(nid(), 1080, 240, "★ Deopt (C2 가정 깨질 때)", size=12, color="#c62828", align="left"))

    # Stage labels with sub-details
    details = [
        (50, 220,  "Stage 1", "javac 4단계:\nLex → Parse →\nAPT → BCGen"),
        (450, 220, "Stage 2", "ClassFile 포맷:\nCAFEBABE\nConstant Pool"),
        (650, 220, "Stage 3", "Loading →\nLinking →\nInitialization"),
        (850, 220, "Stage 4", "Template\nInterpreter\n(asm 점프 테이블)"),
        (1050, 320, "Stage 5", "C1: 빠른 컴파일\nC2: 공격적 최적화\nTiered로 협업"),
        (1250, 320, "Stage 6", "Native code\n메서드 단위 캐싱\n4-entry 디스패치"),
        (1450, 320, "결과",    "CPU가 직접\nmachine code 실행"),
    ]
    for x, y, head, desc in details:
        els.append(text(nid(), x, y, head, size=14, color="#1565c0", align="left", w=160))
        els.append(text(nid(), x, y + 20, desc, size=11, color="#444", align="left", w=160))

    # Bottom legend
    legend_y = 470
    els.append(text(nid(), 50, legend_y, "메모리 행선지", size=15, color="#1e1e1e", align="left"))
    legend_items = [
        ("blue",         ".java",            "디스크"),
        ("green",        ".class",           "디스크"),
        ("pink",         "객체 (new ...)",   "Heap"),
        ("orange",       "클래스 메타",      "Metaspace"),
        ("amber",        "프레임/스택",      "JVM Stack (스레드별)"),
        ("teal",         "native code",      "Code Cache"),
    ]
    for i, (color, what, where) in enumerate(legend_items):
        lx = 50 + (i // 2) * 350
        ly = legend_y + 30 + (i % 2) * 25
        els += box(lx, ly, 16, 16, "", color=color)
        els.append(text(nid(), lx + 25, ly + 1, f"{what} → {where}", size=12, color="#444", align="left"))

    return els


# ─────────────────────────────────────────────────────────────
# Main: write all diagrams
# ─────────────────────────────────────────────────────────────

OUT_DIR = Path(__file__).parent

DIAGRAMS = [
    ("02a-javac-stages",        diagram_javac_stages,   "javac 5단계 (Lexer → Parser → APT → SemAnalysis → BCGen)"),
    ("02b-classloader-flow",    diagram_classloader,    "ClassLoader: Loading → Linking → Initialization + 부모 위임"),
    ("02c-tiered-compilation",  diagram_tiered,         "Tiered Compilation 5단 (L0~L4)"),
    ("02d-method-call-entries", diagram_method_call,    "메서드 호출: 4가지 entry pointer (i2i/i2c/c2i/compiled)"),
    ("02e-jvm-memory",          diagram_memory,         "JVM 메모리 레이아웃 + Code Cache 내부"),
    ("02f-7-stage-flow",        diagram_7_stage,        ".java → CPU 7-Stage 전체 흐름"),
]


def main():
    for slug, factory, desc in DIAGRAMS:
        random.seed(hash(slug) & 0xFFFFFFFF)  # stable seeds per diagram
        _id_counter[0] = 0
        elements = factory()
        # Excalidraw JSON
        data = make_excalidraw(elements)
        (OUT_DIR / f"{slug}.excalidraw").write_text(json.dumps(data, indent=2, ensure_ascii=False))
        # SVG
        svg = to_svg(elements, title=desc)
        (OUT_DIR / f"{slug}.svg").write_text(svg)
        print(f"  ✓ {slug}.svg / .excalidraw  — {desc}")


if __name__ == "__main__":
    main()
