"""
Excalidraw JSON generator helper.
Produces valid .excalidraw files that open in Excalidraw web/VSCode/Obsidian.
"""
import json
import random
import time
from pathlib import Path


def _seed():
    return random.randint(1, 2**31 - 1)


def _nonce():
    return random.randint(1, 2**31 - 1)


def _ts():
    return int(time.time() * 1000)


def _base(element_type, x, y, width, height, stroke="#1e1e1e", bg="transparent",
          fill_style="solid", stroke_width=2, roundness=None, group_ids=None,
          element_id=None):
    return {
        "id": element_id or f"el_{_seed()}",
        "type": element_type,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "angle": 0,
        "strokeColor": stroke,
        "backgroundColor": bg,
        "fillStyle": fill_style,
        "strokeWidth": stroke_width,
        "strokeStyle": "solid",
        "roughness": 1,
        "opacity": 100,
        "groupIds": group_ids or [],
        "frameId": None,
        "roundness": ({"type": roundness} if roundness else None),
        "seed": _seed(),
        "version": 1,
        "versionNonce": _nonce(),
        "isDeleted": False,
        "boundElements": [],
        "updated": _ts(),
        "link": None,
        "locked": False,
    }


def rect(x, y, w, h, stroke="#1e1e1e", bg="transparent", fill_style="solid",
         stroke_width=2, roundness=3, group_ids=None, element_id=None):
    return _base("rectangle", x, y, w, h, stroke, bg, fill_style, stroke_width,
                 roundness, group_ids, element_id)


def ellipse(x, y, w, h, **kw):
    return _base("ellipse", x, y, w, h, **kw)


def diamond(x, y, w, h, **kw):
    return _base("diamond", x, y, w, h, **kw)


def text(x, y, content, font_size=20, font_family=2, text_align="left",
         vertical_align="top", color="#1e1e1e", group_ids=None,
         container_id=None, width=None, height=None, element_id=None):
    """font_family: 1=Virgil(hand-drawn), 2=Helvetica(default, clean), 3=Cascadia(code).
    한글이 깨끗하게 보이도록 기본값을 2(Helvetica)로 설정."""
    if width is None:
        width = max(len(line) for line in content.split("\n")) * (font_size * 0.6)
    if height is None:
        height = len(content.split("\n")) * font_size * 1.25
    el = _base("text", x, y, width, height, stroke=color, group_ids=group_ids,
               element_id=element_id)
    el.update({
        "text": content,
        "fontSize": font_size,
        "fontFamily": font_family,
        "textAlign": text_align,
        "verticalAlign": vertical_align,
        "baseline": font_size,
        "containerId": container_id,
        "originalText": content,
        "lineHeight": 1.25,
        "autoResize": True,
    })
    return el


def arrow(x, y, points, start_id=None, end_id=None, stroke="#1e1e1e",
          stroke_width=2, group_ids=None, dashed=False):
    """points: list of [dx, dy] relative to (x, y). First point is [0,0]."""
    el = _base("arrow", x, y,
               max(p[0] for p in points) - min(p[0] for p in points),
               max(p[1] for p in points) - min(p[1] for p in points),
               stroke=stroke, stroke_width=stroke_width, group_ids=group_ids)
    if dashed:
        el["strokeStyle"] = "dashed"
    el.update({
        "points": [list(p) for p in points],
        "lastCommittedPoint": None,
        "startBinding": ({"elementId": start_id, "focus": 0, "gap": 5}
                         if start_id else None),
        "endBinding": ({"elementId": end_id, "focus": 0, "gap": 5}
                       if end_id else None),
        "startArrowhead": None,
        "endArrowhead": "arrow",
        "elbowed": False,
    })
    return el


def line(x, y, points, **kw):
    el = arrow(x, y, points, **kw)
    el["type"] = "line"
    el["endArrowhead"] = None
    return el


def write_file(elements, path, view_bg="#ffffff"):
    doc = {
        "type": "excalidraw",
        "version": 2,
        "source": "https://excalidraw.com",
        "elements": elements,
        "appState": {
            "gridSize": None,
            "viewBackgroundColor": view_bg,
        },
        "files": {},
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
    print(f"  -> {path}")
    # SVG companion alongside the .excalidraw file
    svg_path = str(Path(path).with_suffix(".svg"))
    write_svg(elements, svg_path, view_bg=view_bg)


def _svg_escape(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _element_to_svg(el):
    """Render one Excalidraw element to SVG fragment string."""
    t = el["type"]
    x, y, w, h = el["x"], el["y"], el["width"], el["height"]
    stroke = el.get("strokeColor", "#1e1e1e")
    bg = el.get("backgroundColor", "transparent")
    sw = el.get("strokeWidth", 2)
    dasharray = ""
    if el.get("strokeStyle") == "dashed":
        dasharray = ' stroke-dasharray="8 4"'
    elif el.get("strokeStyle") == "dotted":
        dasharray = ' stroke-dasharray="2 4"'

    if t == "rectangle":
        rx = 8 if el.get("roundness") else 0
        fill = bg if bg != "transparent" else "none"
        return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" '
                f'rx="{rx}" ry="{rx}" stroke="{stroke}" fill="{fill}" '
                f'stroke-width="{sw}"{dasharray}/>')

    if t == "ellipse":
        cx, cy = x + w / 2, y + h / 2
        rx, ry = w / 2, h / 2
        fill = bg if bg != "transparent" else "none"
        return (f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" '
                f'stroke="{stroke}" fill="{fill}" stroke-width="{sw}"{dasharray}/>')

    if t == "diamond":
        cx, cy = x + w / 2, y + h / 2
        pts = f"{cx},{y} {x+w},{cy} {cx},{y+h} {x},{cy}"
        fill = bg if bg != "transparent" else "none"
        return (f'<polygon points="{pts}" stroke="{stroke}" fill="{fill}" '
                f'stroke-width="{sw}"{dasharray}/>')

    if t == "text":
        content = el.get("text", "")
        fs = el.get("fontSize", 16)
        # SVG에서는 한글이 깨끗하게 보이는 system sans-serif로 통일.
        # Excalidraw 앱에서는 fontFamily=1(Virgil) 하나만 hand-drawn으로 유지.
        ff_id = el.get("fontFamily", 1)
        if ff_id == 3:
            font_family = ("'SF Mono','Menlo','D2Coding','Consolas',"
                           "'Cascadia Code',monospace")
        else:
            font_family = (
                "-apple-system,BlinkMacSystemFont,"
                "'Apple SD Gothic Neo','Pretendard','Noto Sans KR',"
                "'Malgun Gothic','Helvetica Neue',Helvetica,Arial,sans-serif"
            )
        text_align = el.get("textAlign", "left")
        anchor = {"left": "start", "center": "middle", "right": "end"}[text_align]
        lines = content.split("\n")
        # First line baseline: y + fontSize * 0.85 (rough); subsequent lines via dy
        first_y = y + fs * 0.85
        if anchor == "middle":
            tx = x + w / 2
        elif anchor == "end":
            tx = x + w
        else:
            tx = x
        tspans = []
        for i, line in enumerate(lines):
            dy = "0" if i == 0 else f"{int(fs * 1.25)}"
            tspans.append(
                f'<tspan x="{tx}" dy="{dy}">{_svg_escape(line)}</tspan>'
            )
        return (f'<text x="{tx}" y="{first_y}" font-family="{font_family}" '
                f'font-size="{fs}" fill="{stroke}" text-anchor="{anchor}">'
                f'{"".join(tspans)}</text>')

    if t in ("arrow", "line"):
        pts = el.get("points", [])
        if not pts:
            return ""
        abs_pts = [(x + p[0], y + p[1]) for p in pts]
        d = "M " + " L ".join(f"{px},{py}" for px, py in abs_pts)
        marker = ""
        if t == "arrow" and el.get("endArrowhead") == "arrow":
            marker = ' marker-end="url(#arrowhead)"'
        return (f'<path d="{d}" stroke="{stroke}" fill="none" '
                f'stroke-width="{sw}" stroke-linecap="round" '
                f'stroke-linejoin="round"{dasharray}{marker}/>')

    return ""


def write_svg(elements, path, view_bg="#ffffff", padding=20):
    """Render the same Excalidraw elements as a clean SVG file."""
    # Bounding box
    xs, ys, xe, ye = [], [], [], []
    for el in elements:
        x, y, w, h = el["x"], el["y"], el["width"], el["height"]
        xs.append(x); ys.append(y)
        if el["type"] in ("arrow", "line"):
            for p in el.get("points", []):
                xs.append(x + p[0]); ys.append(y + p[1])
                xe.append(x + p[0]); ye.append(y + p[1])
        else:
            xe.append(x + w); ye.append(y + h)
    min_x = min(xs) - padding
    min_y = min(ys) - padding
    max_x = max(xe) + padding
    max_y = max(ye) + padding
    width = max_x - min_x
    height = max_y - min_y

    body = "\n  ".join(_element_to_svg(el) for el in elements if el["type"] != "text")
    text_body = "\n  ".join(_element_to_svg(el) for el in elements if el["type"] == "text")

    default_font = (
        "-apple-system,BlinkMacSystemFont,"
        "&apos;Apple SD Gothic Neo&apos;,&apos;Pretendard&apos;,"
        "&apos;Noto Sans KR&apos;,&apos;Malgun Gothic&apos;,"
        "&apos;Helvetica Neue&apos;,Helvetica,Arial,sans-serif"
    )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="{min_x} {min_y} {width} {height}" width="{int(width)}" height="{int(height)}" font-family="{default_font}">
  <defs>
    <marker id="arrowhead" viewBox="0 0 10 10" refX="9" refY="5"
            markerUnits="strokeWidth" markerWidth="6" markerHeight="6" orient="auto">
      <path d="M 0 0 L 10 5 L 0 10 z" fill="#1e1e1e"/>
    </marker>
  </defs>
  <rect x="{min_x}" y="{min_y}" width="{width}" height="{height}" fill="{view_bg}"/>
  {body}
  {text_body}
</svg>
'''
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"  -> {path}")


# =========================================================================
# Diagram 1: JVM, JRE, JDK Russian doll
# =========================================================================
def gen_01_jvm_jre_jdk():
    els = []

    # JDK outer box
    els.append(rect(50, 50, 1100, 700, stroke="#0277bd", stroke_width=3,
                    element_id="jdk_box"))
    els.append(text(70, 60, "JDK (Java Development Kit)", font_size=28,
                    color="#0277bd"))
    els.append(text(70, 95, "개발자가 다운로드받는 것. 전체 패키지.",
                    font_size=14, color="#0277bd"))

    # JRE box (inside JDK, left 60%)
    els.append(rect(80, 140, 700, 580, stroke="#f57f17", stroke_width=3,
                    element_id="jre_box"))
    els.append(text(100, 150, "JRE (Java Runtime Environment)",
                    font_size=22, color="#f57f17"))
    els.append(text(100, 180, "JDK 8까지만 유효 — JDK 9+ 폐기, jlink로 대체",
                    font_size=13, color="#d84315"))

    # JVM box (inside JRE, left part)
    els.append(rect(110, 220, 420, 470, stroke="#d84315", stroke_width=3,
                    element_id="jvm_box"))
    els.append(text(130, 230, "JVM (Java Virtual Machine)",
                    font_size=20, color="#d84315"))

    # JVM internal 4 quadrants
    els.append(rect(125, 275, 185, 100, stroke="#1e1e1e", stroke_width=1))
    els.append(text(135, 285, "Class Loader\nSubsystem",
                    font_size=14, color="#1e1e1e"))
    els.append(text(135, 325, "Bootstrap\nPlatform\nApplication",
                    font_size=11, color="#666"))

    els.append(rect(325, 275, 195, 100, stroke="#1e1e1e", stroke_width=1))
    els.append(text(335, 285, "Runtime Data Areas",
                    font_size=14, color="#1e1e1e"))
    els.append(text(335, 310, "Heap | Method Area\nStack | PC | Native",
                    font_size=11, color="#666"))

    els.append(rect(125, 395, 185, 130, stroke="#1e1e1e", stroke_width=1))
    els.append(text(135, 405, "Execution Engine",
                    font_size=14, color="#1e1e1e"))
    els.append(text(135, 430, "Interpreter\nJIT (C1/C2)\nGC",
                    font_size=11, color="#666"))

    els.append(rect(325, 395, 195, 130, stroke="#1e1e1e", stroke_width=1))
    els.append(text(335, 405, "Native Interface",
                    font_size=14, color="#1e1e1e"))
    els.append(text(335, 430, "JNI\nNative Method\nLibrary",
                    font_size=11, color="#666"))

    # Class Libraries (inside JRE, right of JVM)
    els.append(rect(560, 220, 200, 470, stroke="#388e3c", stroke_width=2))
    els.append(text(580, 230, "Class Libraries",
                    font_size=18, color="#388e3c"))
    els.append(text(580, 265, "(= 옛 rt.jar)\n\njava.base\njava.sql\njava.xml\njava.net.http\njava.desktop\njava.management\njdk.compiler\n...",
                    font_size=13, color="#388e3c"))

    # Development Tools (outside JRE but inside JDK, right 40%)
    els.append(rect(800, 140, 320, 580, stroke="#7b1fa2", stroke_width=2))
    els.append(text(820, 150, "Development Tools",
                    font_size=20, color="#7b1fa2"))
    els.append(text(820, 185,
                    "javac — 컴파일러\njavadoc — 문서 생성\njdb — 디버거\n\n"
                    "jar / jlink / jpackage\njdeps / jdeprscan\n\n"
                    "jstack — 스택 덤프\njmap — 힙 덤프\njstat — GC 통계\n"
                    "jcmd — 통합 진단\njfr — Flight Recorder\n\n"
                    "javap — 역어셈블러\nserialver / keytool",
                    font_size=13, color="#7b1fa2"))

    # OS / Hardware arrows below JVM
    els.append(rect(150, 770, 380, 50, stroke="#1e1e1e", stroke_width=2,
                    bg="#f0f0f0", fill_style="solid", element_id="os_box"))
    els.append(text(280, 783, "OS (Linux / Windows / macOS)",
                    font_size=18, color="#1e1e1e"))

    els.append(rect(150, 840, 380, 50, stroke="#1e1e1e", stroke_width=2,
                    bg="#e0e0e0", fill_style="solid", element_id="hw_box"))
    els.append(text(280, 853, "Hardware (x86_64 / ARM64)",
                    font_size=18, color="#1e1e1e"))

    # Arrows
    els.append(arrow(335, 525, [[0, 0], [0, 245]],
                     start_id="jvm_box", end_id="os_box"))
    els.append(arrow(335, 820, [[0, 0], [0, 20]],
                     start_id="os_box", end_id="hw_box"))

    write_file(els,
               "/Users/mac/Desktop/lemong/code/cj/flab/jvm/00-overview/_excalidraw/01-jvm-jre-jdk.excalidraw")


# =========================================================================
# Diagram 2: Compilation Flow (.java → .class → JVM → native)
# =========================================================================
def gen_02_compile_flow():
    els = []

    els.append(text(50, 40, "Java 컴파일 & 실행 흐름", font_size=28,
                    color="#1e1e1e"))
    els.append(text(50, 80, "소스 코드 한 줄이 CPU 명령어로 변환되기까지",
                    font_size=14, color="#666"))

    # Stage 1: .java source
    els.append(rect(50, 130, 180, 100, stroke="#1565c0", stroke_width=2,
                    bg="#e3f2fd", fill_style="solid", element_id="src"))
    els.append(text(70, 145, "1) .java", font_size=18, color="#1565c0"))
    els.append(text(70, 175, "사람이 읽는\n소스 코드\nUTF-8 텍스트", font_size=12,
                    color="#1565c0"))

    # Stage 2: javac
    els.append(rect(280, 130, 180, 100, stroke="#6a1b9a", stroke_width=2,
                    bg="#f3e5f5", fill_style="solid", element_id="javac"))
    els.append(text(300, 145, "2) javac", font_size=18, color="#6a1b9a"))
    els.append(text(300, 175, "Lexer → Parser\n→ AST → Annotation\n→ Bytecode 생성",
                    font_size=12, color="#6a1b9a"))

    # Stage 3: .class
    els.append(rect(510, 130, 180, 100, stroke="#2e7d32", stroke_width=2,
                    bg="#e8f5e9", fill_style="solid", element_id="cls"))
    els.append(text(530, 145, "3) .class", font_size=18, color="#2e7d32"))
    els.append(text(530, 175, "ClassFile 포맷\nCAFEBABE magic\n+ bytecode",
                    font_size=12, color="#2e7d32"))

    # Stage 4: ClassLoader
    els.append(rect(740, 130, 180, 100, stroke="#ef6c00", stroke_width=2,
                    bg="#fff3e0", fill_style="solid", element_id="cl"))
    els.append(text(760, 145, "4) ClassLoader", font_size=18, color="#ef6c00"))
    els.append(text(760, 175, "Loading\nLinking (verify)\nInitializing",
                    font_size=12, color="#ef6c00"))

    # Stage 5: Interpreter
    els.append(rect(970, 130, 180, 100, stroke="#c2185b", stroke_width=2,
                    bg="#fce4ec", fill_style="solid", element_id="interp"))
    els.append(text(990, 145, "5) Interpreter", font_size=18, color="#c2185b"))
    els.append(text(990, 175, "Template-based\nbytecode 한 줄씩\n실행",
                    font_size=12, color="#c2185b"))

    # Arrows between stages 1-5
    els.append(arrow(230, 180, [[0, 0], [50, 0]], start_id="src", end_id="javac"))
    els.append(arrow(460, 180, [[0, 0], [50, 0]], start_id="javac", end_id="cls"))
    els.append(arrow(690, 180, [[0, 0], [50, 0]], start_id="cls", end_id="cl"))
    els.append(arrow(920, 180, [[0, 0], [50, 0]], start_id="cl", end_id="interp"))

    # Bottom row: JIT path
    els.append(text(50, 290, "↓ 호출 빈도가 임계치를 넘으면 (-XX:CompileThreshold, 기본 10,000)",
                    font_size=14, color="#666"))

    els.append(rect(290, 330, 200, 100, stroke="#f57c00", stroke_width=2,
                    bg="#fff8e1", fill_style="solid", element_id="c1"))
    els.append(text(310, 345, "6a) C1 JIT", font_size=18, color="#f57c00"))
    els.append(text(310, 375, "Client compiler\n빠른 컴파일\n간단한 최적화",
                    font_size=12, color="#f57c00"))

    els.append(rect(560, 330, 200, 100, stroke="#d84315", stroke_width=2,
                    bg="#ffe0b2", fill_style="solid", element_id="c2"))
    els.append(text(580, 345, "6b) C2 JIT", font_size=18, color="#d84315"))
    els.append(text(580, 375, "Server compiler\n공격적 최적화\n(EA, Inline, Vec)",
                    font_size=12, color="#d84315"))

    els.append(rect(830, 330, 220, 100, stroke="#1e1e1e", stroke_width=2,
                    bg="#eeeeee", fill_style="solid", element_id="native"))
    els.append(text(850, 345, "7) Native Code", font_size=18, color="#1e1e1e"))
    els.append(text(850, 375, "x86_64 / ARM64\nmachine code\nCode Cache에 저장",
                    font_size=12, color="#1e1e1e"))

    # Vertical arrow from interpreter down to JIT
    els.append(arrow(1060, 230, [[0, 0], [-660, 100]],
                     start_id="interp", end_id="c1", dashed=True))
    els.append(arrow(490, 380, [[0, 0], [70, 0]], start_id="c1", end_id="c2"))
    els.append(arrow(760, 380, [[0, 0], [70, 0]], start_id="c2", end_id="native"))

    # Tiered Compilation note
    els.append(text(50, 480, "Tiered Compilation (JDK 8+ 기본):",
                    font_size=16, color="#1e1e1e"))
    els.append(text(50, 510,
                    "Level 0 → Interpreter\n"
                    "Level 1 → C1, no profiling (간단한 메서드)\n"
                    "Level 2 → C1, with invocation/back-edge counter\n"
                    "Level 3 → C1, full profiling (메서드 인자, 분기 등)\n"
                    "Level 4 → C2, profiling 정보 활용한 공격적 최적화\n\n"
                    "역최적화 (Deoptimization): C2가 한 가정이 깨지면 Level 0로 복귀.\n"
                    "  예: type speculation 실패, class redefinition, uncommon trap.",
                    font_size=14, color="#1e1e1e"))

    # GC and Code Cache annotations
    els.append(rect(50, 700, 480, 130, stroke="#558b2f", stroke_width=2,
                    bg="#f1f8e9", fill_style="solid"))
    els.append(text(70, 715, "💾 메모리 행선지", font_size=18, color="#558b2f"))
    els.append(text(70, 745,
                    "• Class 메타데이터 → Metaspace (네이티브 메모리)\n"
                    "• 객체 인스턴스 → Heap (Young/Old, GC 대상)\n"
                    "• JIT 컴파일된 native code → Code Cache (네이티브 메모리)\n"
                    "• 스레드별 호출 스택 → JVM Stack",
                    font_size=12, color="#558b2f"))

    els.append(rect(560, 700, 490, 130, stroke="#5d4037", stroke_width=2,
                    bg="#efebe9", fill_style="solid"))
    els.append(text(580, 715, "⚙️ 실행 모드 변경 트리거", font_size=18,
                    color="#5d4037"))
    els.append(text(580, 745,
                    "• 메서드 호출 횟수 > CompileThreshold (10,000)\n"
                    "• 루프 백엣지 카운터 > OnStackReplacePercentage 비율\n"
                    "• 클래스 로드 시 method 크기 / 분기 패턴 분석\n"
                    "• Profiling 정보 누적 후 자동 승격 (C1 → C2)",
                    font_size=12, color="#5d4037"))

    write_file(els,
               "/Users/mac/Desktop/lemong/code/cj/flab/jvm/00-overview/_excalidraw/02-compile-flow.excalidraw")


# =========================================================================
# Diagram 3: JVM Architecture Big Picture
# =========================================================================
def gen_03_jvm_architecture():
    els = []

    els.append(text(50, 30, "JVM 아키텍처 — 전체 큰 그림", font_size=28,
                    color="#1e1e1e"))
    els.append(text(50, 70, "이 그림 하나가 머리에 박히면 나머지 챕터가 다 매핑된다",
                    font_size=14, color="#666"))

    # Outer JVM frame
    els.append(rect(50, 110, 1200, 800, stroke="#d84315", stroke_width=3,
                    element_id="jvm_outer"))
    els.append(text(70, 120, "JVM Process (libjvm.so)", font_size=22,
                    color="#d84315"))

    # === ClassLoader Subsystem (top) ===
    els.append(rect(80, 170, 1140, 130, stroke="#1565c0", stroke_width=2,
                    bg="#e3f2fd", fill_style="solid"))
    els.append(text(100, 180, "① ClassLoader Subsystem", font_size=18,
                    color="#1565c0"))

    # Three classloaders
    els.append(rect(120, 215, 200, 70, stroke="#1e1e1e", stroke_width=1,
                    bg="#ffffff", fill_style="solid"))
    els.append(text(140, 225, "Bootstrap ClassLoader", font_size=12,
                    color="#1e1e1e"))
    els.append(text(140, 245, "(C++, native)\n$JAVA_HOME/lib/modules\njava.base, java.sql, ...",
                    font_size=10, color="#666"))

    els.append(rect(340, 215, 200, 70, stroke="#1e1e1e", stroke_width=1,
                    bg="#ffffff", fill_style="solid"))
    els.append(text(360, 225, "Platform ClassLoader", font_size=12,
                    color="#1e1e1e"))
    els.append(text(360, 245, "(Java)\n표준 모듈 외 플랫폼 모듈\nJDK 9+ (구 Extension CL)",
                    font_size=10, color="#666"))

    els.append(rect(560, 215, 200, 70, stroke="#1e1e1e", stroke_width=1,
                    bg="#ffffff", fill_style="solid"))
    els.append(text(580, 225, "Application ClassLoader", font_size=12,
                    color="#1e1e1e"))
    els.append(text(580, 245, "(Java)\n-classpath\n사용자 코드",
                    font_size=10, color="#666"))

    els.append(rect(780, 215, 200, 70, stroke="#1e1e1e", stroke_width=1,
                    bg="#fff3e0", fill_style="solid"))
    els.append(text(800, 225, "User-defined CL", font_size=12, color="#1e1e1e"))
    els.append(text(800, 245, "Tomcat WebappCL\nOSGi BundleCL\n동적 로딩",
                    font_size=10, color="#666"))

    els.append(text(1000, 240, "Loading\nLinking\n(Verify/Prepare/Resolve)\nInitializing",
                    font_size=11, color="#1565c0"))

    # === Runtime Data Areas (middle) ===
    els.append(rect(80, 320, 1140, 280, stroke="#2e7d32", stroke_width=2,
                    bg="#e8f5e9", fill_style="solid"))
    els.append(text(100, 330, "② Runtime Data Areas", font_size=18,
                    color="#2e7d32"))

    # Heap (per-process, shared)
    els.append(rect(120, 370, 480, 220, stroke="#388e3c", stroke_width=2,
                    bg="#c8e6c9", fill_style="solid"))
    els.append(text(140, 380, "Heap (모든 스레드 공유)", font_size=16,
                    color="#1b5e20"))

    els.append(rect(135, 410, 220, 80, stroke="#1e1e1e", stroke_width=1,
                    bg="#ffffff", fill_style="solid"))
    els.append(text(155, 420, "Young Generation", font_size=13, color="#1e1e1e"))
    els.append(text(155, 445, "Eden | S0 | S1\n새 객체 할당\nMinor GC 빈번",
                    font_size=10, color="#666"))

    els.append(rect(370, 410, 220, 80, stroke="#1e1e1e", stroke_width=1,
                    bg="#ffffff", fill_style="solid"))
    els.append(text(390, 420, "Old Generation", font_size=13, color="#1e1e1e"))
    els.append(text(390, 445, "Tenured\n오래된 객체\nMajor/Full GC",
                    font_size=10, color="#666"))

    els.append(rect(135, 510, 455, 70, stroke="#5e35b2", stroke_width=1,
                    bg="#ede7f6", fill_style="solid"))
    els.append(text(155, 520, "Metaspace (네이티브 메모리)", font_size=13,
                    color="#4527a0"))
    els.append(text(155, 545, "Class 메타데이터, Method 메타데이터, 상수 풀, 클래스 로더 데이터\nJDK 8+ (PermGen 대체)",
                    font_size=10, color="#4527a0"))

    # Per-thread
    els.append(rect(620, 370, 580, 220, stroke="#f57c00", stroke_width=2,
                    bg="#ffe0b2", fill_style="solid"))
    els.append(text(640, 380, "Per-Thread (각 스레드마다)", font_size=16,
                    color="#e65100"))

    els.append(rect(635, 410, 270, 80, stroke="#1e1e1e", stroke_width=1,
                    bg="#ffffff", fill_style="solid"))
    els.append(text(655, 420, "JVM Stack", font_size=13, color="#1e1e1e"))
    els.append(text(655, 445, "Stack Frame per 메서드 호출\n- Local Variables\n- Operand Stack\n- Frame Data",
                    font_size=10, color="#666"))

    els.append(rect(920, 410, 270, 80, stroke="#1e1e1e", stroke_width=1,
                    bg="#ffffff", fill_style="solid"))
    els.append(text(940, 420, "PC Register", font_size=13, color="#1e1e1e"))
    els.append(text(940, 445, "현재 실행 중인\nbytecode instruction 주소\n(스레드별 1개)",
                    font_size=10, color="#666"))

    els.append(rect(635, 510, 555, 70, stroke="#1e1e1e", stroke_width=1,
                    bg="#ffffff", fill_style="solid"))
    els.append(text(655, 520, "Native Method Stack", font_size=13, color="#1e1e1e"))
    els.append(text(655, 545, "JNI를 통해 호출되는 C/C++ 함수의 스택. OS 스레드 스택과 사실상 동일.",
                    font_size=10, color="#666"))

    # === Execution Engine (bottom-left) ===
    els.append(rect(80, 620, 700, 270, stroke="#c2185b", stroke_width=2,
                    bg="#fce4ec", fill_style="solid"))
    els.append(text(100, 630, "③ Execution Engine", font_size=18,
                    color="#c2185b"))

    els.append(rect(120, 670, 200, 100, stroke="#1e1e1e", stroke_width=1,
                    bg="#ffffff", fill_style="solid"))
    els.append(text(140, 680, "Interpreter", font_size=14, color="#1e1e1e"))
    els.append(text(140, 705, "Template-based\nbytecode → asm\n루틴 호출 방식",
                    font_size=11, color="#666"))

    els.append(rect(340, 670, 200, 100, stroke="#1e1e1e", stroke_width=1,
                    bg="#ffffff", fill_style="solid"))
    els.append(text(360, 680, "JIT Compiler", font_size=14, color="#1e1e1e"))
    els.append(text(360, 705, "C1 (Client)\nC2 (Server, Sea of Nodes)\n→ Code Cache",
                    font_size=11, color="#666"))

    els.append(rect(560, 670, 200, 100, stroke="#1e1e1e", stroke_width=1,
                    bg="#ffffff", fill_style="solid"))
    els.append(text(580, 680, "Garbage Collector", font_size=14, color="#1e1e1e"))
    els.append(text(580, 705, "Serial / Parallel\nG1 / ZGC / Shenandoah\n+ Epsilon (no-op)",
                    font_size=11, color="#666"))

    els.append(text(120, 790, "TLAB (Thread-Local Allocation Buffer): 각 스레드가 Eden에 가진 작은 영역.",
                    font_size=12, color="#c2185b"))
    els.append(text(120, 815, "  → 동시 할당 시 contention 회피, bump-the-pointer 알고리즘.",
                    font_size=11, color="#666"))
    els.append(text(120, 845, "Safepoint: 모든 스레드를 일시 정지시키는 polling 메커니즘.",
                    font_size=12, color="#c2185b"))
    els.append(text(120, 870, "  → GC, deoptimization, stack walking, biased lock revoke 등의 전제.",
                    font_size=11, color="#666"))

    # === Native Interface (bottom-right) ===
    els.append(rect(800, 620, 420, 270, stroke="#5d4037", stroke_width=2,
                    bg="#efebe9", fill_style="solid"))
    els.append(text(820, 630, "④ Native Interface", font_size=18,
                    color="#5d4037"))

    els.append(rect(820, 670, 380, 100, stroke="#1e1e1e", stroke_width=1,
                    bg="#ffffff", fill_style="solid"))
    els.append(text(840, 680, "JNI (Java Native Interface)", font_size=14,
                    color="#1e1e1e"))
    els.append(text(840, 705, "Java ↔ C/C++ 함수 호출 브릿지\nObject 핸들 관리 (Local/Global ref)\nException 전파",
                    font_size=11, color="#666"))

    els.append(rect(820, 790, 380, 80, stroke="#1e1e1e", stroke_width=1,
                    bg="#ffffff", fill_style="solid"))
    els.append(text(840, 800, "Native Method Library", font_size=14,
                    color="#1e1e1e"))
    els.append(text(840, 825, "libnio.so, libnet.so, libzip.so, ...\nSystem.loadLibrary로 동적 로드",
                    font_size=11, color="#666"))

    write_file(els,
               "/Users/mac/Desktop/lemong/code/cj/flab/jvm/00-overview/_excalidraw/03-jvm-architecture.excalidraw")


# =========================================================================
# Diagram 4: JVM Timeline 1995-2026
# =========================================================================
def gen_04_jvm_timeline():
    els = []

    els.append(text(50, 30, "JVM / Java 진화 타임라인 (1991 → 2026)",
                    font_size=28, color="#1e1e1e"))
    els.append(text(50, 70, "각 점은 \"왜 만들어졌나\"를 동시에 기억하라",
                    font_size=14, color="#666"))

    # Horizontal axis
    els.append(line(80, 600, [[0, 0], [1180, 0]], stroke="#1e1e1e",
                    stroke_width=2))

    milestones = [
        (100, 600, 1991, "Green Project", "Oak 언어\n임베디드용\nGosling"),
        (200, 600, 1995, "Java 1.0", "JVM = pure interpreter\nC++ 대비 50배 느림"),
        (300, 600, 1999, "HotSpot (1.3)", "JIT 등장!\nAnimorphic 인수\n\"hot spot만 컴파일\""),
        (420, 600, 2004, "Java 5", "Generics\nAnnotation\nautoboxing\nJMM 명세화 (JSR-133)"),
        (540, 600, 2006, "OpenJDK", "Sun이 GPLv2로\n오픈소스화"),
        (660, 600, 2010, "Oracle 인수", "Java 소유권 이전\nApache Harmony 결별"),
        (780, 600, 2014, "Java 8", "Lambda + Stream\nMetaspace ← PermGen\nNashorn JS"),
        (880, 600, 2017, "Java 9", "Module System\n(Jigsaw)\nJRE 폐기 시작\n6개월 주기"),
        (980, 600, 2018, "Java 10/11", "var\nZGC preview\nLTS 시작"),
        (1080, 600, 2021, "Java 17 LTS", "Sealed class\nPattern matching\nMacOS AArch64"),
        (1200, 600, 2023, "Java 21 LTS", "Virtual Thread\nPattern records\nGenerational ZGC"),
    ]

    for x, y_axis, year, title, desc in milestones:
        # Vertical line on axis
        els.append(line(x, y_axis - 10, [[0, 0], [0, 20]], stroke="#1e1e1e",
                        stroke_width=2))
        # Year label below
        els.append(text(x - 20, y_axis + 20, str(year), font_size=14,
                        color="#1e1e1e"))
        # Title and desc — alternate above/below
        idx = milestones.index((x, y_axis, year, title, desc))
        if idx % 2 == 0:
            # Above the line
            els.append(text(x - 50, y_axis - 130, title, font_size=14,
                            color="#d84315"))
            els.append(text(x - 50, y_axis - 105, desc, font_size=10,
                            color="#666"))
            els.append(line(x, y_axis - 10, [[0, 0], [0, -25]], stroke="#999",
                            stroke_width=1))
        else:
            # Below
            els.append(text(x - 50, y_axis + 60, title, font_size=14,
                            color="#1565c0"))
            els.append(text(x - 50, y_axis + 85, desc, font_size=10,
                            color="#666"))
            els.append(line(x, y_axis + 10, [[0, 0], [0, 30]], stroke="#999",
                            stroke_width=1))

    # Bottom annotations: GC evolution
    els.append(text(50, 800, "GC 알고리즘 진화 (별도 축)", font_size=20,
                    color="#1e1e1e"))
    els.append(text(50, 830,
                    "Serial GC (1.0) → Parallel GC (1.4, 멀티코어 대응) → CMS (1.4, 동시 마킹)",
                    font_size=14, color="#388e3c"))
    els.append(text(50, 855,
                    "→ G1 (1.7u4 experimental, 1.9 default) — Region 기반, 예측 가능한 STW",
                    font_size=14, color="#388e3c"))
    els.append(text(50, 880,
                    "→ ZGC (11 experimental, 15 prod, 21 generational) — Colored Pointer, sub-ms pause",
                    font_size=14, color="#388e3c"))
    els.append(text(50, 905,
                    "→ Shenandoah (12+, RedHat) — Brooks/Load Reference Barrier, 동시 압축",
                    font_size=14, color="#388e3c"))
    els.append(text(50, 935,
                    "CMS는 9에서 deprecated, 14에서 제거. \"Concurrent Mode Failure\" 안정성 이슈 + G1과 기능 중복.",
                    font_size=12, color="#d84315"))

    write_file(els,
               "/Users/mac/Desktop/lemong/code/cj/flab/jvm/00-overview/_excalidraw/04-jvm-timeline.excalidraw")


# =========================================================================
# Chapter 00 / 01 (overview/what-is-jvm-jre-jdk):
# JDK 패키징 구조의 진화 (JDK 8 / 9~10 / 11+)
# =========================================================================

OV_DIR = "/Users/mac/Desktop/lemong/code/cj/flab/jvm/00-overview/_excalidraw"


def _dir_tree_box(els, x, y, w, h, title, title_color, bg, items):
    """디렉토리 트리 박스 헬퍼.
    items: list of (indent_level, text, optional_note)
    """
    els.append(rect(x, y, w, h, stroke=title_color, bg=bg,
                    fill_style="solid", stroke_width=3, roundness=3))
    els.append(text(x + 15, y + 10, title, font_size=18, color=title_color))
    line_y = y + 50
    for level, item, note in items:
        indent = level * 22
        els.append(text(x + 20 + indent, line_y, item,
                        font_size=13, color="#1e1e1e"))
        if note:
            els.append(text(x + w - 250, line_y, note,
                            font_size=11, color="#888"))
        line_y += 24


def gen_ov_01a_jdk8_structure():
    """JDK 8까지 — 전통적 3중 박스 + jre/ 폴더 명시"""
    els = []

    els.append(text(50, 30, "JDK 8까지 — 전통적 3중 박스 (jre/ 폴더 실재)",
                    font_size=24, color="#0277bd"))
    els.append(text(50, 65,
                    "사용자는 JRE만 받을 수도 있고, 개발자는 JDK를 받음. 명확한 사용자/개발자 분리 모델.",
                    font_size=13, color="#666"))

    # JDK 큰 박스
    els.append(rect(50, 100, 1100, 580, stroke="#0277bd",
                    bg="#e3f2fd", fill_style="solid", stroke_width=4))
    els.append(text(70, 110, "$JAVA_HOME/   (JDK 8)",
                    font_size=20, color="#0277bd"))

    # 개발 도구 영역 (좌측)
    _dir_tree_box(els, 80, 160, 450, 480,
                  "개발 도구 영역", "#7b1fa2", "#f3e5f5",
                  [
                      (0, "bin/", ""),
                      (1, "javac", "(컴파일러)"),
                      (1, "javadoc", "(문서)"),
                      (1, "jdb", "(디버거)"),
                      (1, "jstack", "(스택 덤프)"),
                      (1, "jmap", "(힙 덤프)"),
                      (1, "jstat", "(GC 통계)"),
                      (1, "jar", ""),
                      (1, "...", ""),
                      (0, "lib/", ""),
                      (1, "tools.jar", "(JDK 도구)"),
                      (1, "dt.jar", "(데스크톱 도구)"),
                      (0, "include/", "(JNI 헤더)"),
                  ])

    # JRE 영역 (우측) — 별도 폴더로 강조
    _dir_tree_box(els, 560, 160, 570, 480,
                  "jre/  ← 별도 폴더로 실제 존재 ★", "#d84315", "#ffe0b2",
                  [
                      (0, "bin/", ""),
                      (1, "java", "(실행기)"),
                      (1, "javaw", ""),
                      (1, "keytool", ""),
                      (0, "lib/", ""),
                      (1, "rt.jar", "★ 60MB 단일 jar ★"),
                      (1, "charsets.jar", ""),
                      (1, "jsse.jar", "(보안)"),
                      (1, "ext/", "(Extension)"),
                      (0, "", ""),
                      (0, "→ 사용자는 이 폴더만 별도로 다운받을 수 있었음", ""),
                      (0, "  (JRE 단독 배포)", ""),
                  ])

    # 핵심 개념 박스
    els.append(rect(50, 710, 1100, 200, stroke="#1e1e1e", stroke_width=2,
                    bg="#fafafa", fill_style="solid"))
    els.append(text(70, 720, "🎯 핵심 개념 & 왜 이렇게 됐나",
                    font_size=18, color="#1e1e1e"))
    els.append(text(70, 755,
                    "• 1996년 JDK 1.0부터의 전통적 디자인. \"사용자 vs 개발자\"를 명확히 분리.\n"
                    "• JDK 안에 진짜로 jre/ 폴더가 존재 → 디렉토리 레벨에서 '실행 환경'과 '개발 도구'를 분리.\n"
                    "• rt.jar(60MB) — 모든 표준 클래스가 한 jar에 묶임. 간단하지만 비대화 문제.\n"
                    "• Extension Mechanism (jre/lib/ext): 표준 외 라이브러리를 시스템 전역에 끼워 넣음 → 보안/충돌 위험.\n"
                    "• 한계: 임베디드/IoT에서 rt.jar 60MB가 부담. 내부 API(sun.misc.*)가 무분별하게 노출됨.",
                    font_size=12, color="#333"))

    write_file(els, f"{OV_DIR}/01a-jdk8-structure.excalidraw")


def gen_ov_01b_jdk9_structure():
    """JDK 9~10 — 평탄화 + Module System (jre/ 폴더 사라짐)"""
    els = []

    els.append(text(50, 30, "JDK 9~10 — Module System + 평탄화 (jre/ 폴더 사라짐)",
                    font_size=24, color="#7b1fa2"))
    els.append(text(50, 65,
                    "JEP 261 (Module System) + JEP 282 (jlink). 디렉토리 구조 자체가 바뀜.",
                    font_size=13, color="#666"))

    # JDK 큰 박스 (평탄화)
    els.append(rect(50, 100, 1100, 580, stroke="#7b1fa2",
                    bg="#f3e5f5", fill_style="solid", stroke_width=4))
    els.append(text(70, 110, "$JAVA_HOME/   (JDK 9~10)  — 평탄화됨",
                    font_size=20, color="#7b1fa2"))

    # 통합된 bin/ 영역
    _dir_tree_box(els, 80, 160, 520, 480,
                  "bin/  — 모든 도구가 한곳에", "#7b1fa2", "#ffffff",
                  [
                      (0, "java", "(실행기 — JRE에 있던 것)"),
                      (0, "javac", "(컴파일러)"),
                      (0, "javadoc, jdb, jar", ""),
                      (0, "jstack, jmap, jstat", "(진단)"),
                      (0, "jlink ★", "(JDK 9 신규 — 커스텀 런타임 빌더)"),
                      (0, "jdeps", "(모듈 의존성 분석)"),
                      (0, "jdeprscan", "(deprecated API 스캔)"),
                      (0, "jshell ★", "(JDK 9 신규 — REPL)"),
                      (0, "keytool", ""),
                      (0, "...", ""),
                      (0, "", ""),
                      (0, "→ 옛 jre/bin/* 와 JDK bin/* 가 통합됨", ""),
                  ])

    # 새로운 lib/modules + conf/
    _dir_tree_box(els, 630, 160, 500, 480,
                  "새 디렉토리 구조", "#d84315", "#fff3e0",
                  [
                      (0, "lib/", ""),
                      (1, "modules ★", "★ jimage 포맷 ★"),
                      (1, "", "(옛 rt.jar 대체)"),
                      (1, "src.zip", "(소스)"),
                      (0, "", ""),
                      (0, "conf/ ★", "(JDK 9 신규)"),
                      (1, "security/", ""),
                      (1, "logging.properties", ""),
                      (0, "", ""),
                      (0, "include/", "(JNI 헤더)"),
                      (0, "legal/", "(라이선스)"),
                      (0, "", ""),
                      (0, "✗ jre/ 폴더 없음 ✗", ""),
                      (0, "  rt.jar 사라짐", ""),
                      (0, "  ext/ 폴더 사라짐", ""),
                  ])

    # 핵심 개념 박스
    els.append(rect(50, 710, 1100, 240, stroke="#1e1e1e", stroke_width=2,
                    bg="#fafafa", fill_style="solid"))
    els.append(text(70, 720, "🎯 핵심 개념 & 왜 바뀌었나",
                    font_size=18, color="#1e1e1e"))
    els.append(text(70, 755,
                    "• JEP 261 (Module System): \"Project Jigsaw\". 패키지보다 상위 단위인 module 도입. "
                    "module-info.java로 의존성과 export를 명시.\n"
                    "• JEP 282 (jlink): \"내 앱이 필요한 모듈만\" 골라 커스텀 런타임 이미지 생성. "
                    "임베디드/Docker에서 이미지 크기 절감.\n"
                    "• jimage 포맷: rt.jar 단일 jar → modules 파일로 압축. 시작 속도 + 메모리 절감.\n"
                    "• jre/ 폴더 사라짐: 더 이상 \"JRE = 별도 폴더\" 모델이 아님. 모든 게 평탄.\n"
                    "• Bootstrap → Platform → Application CL: 옛 Extension CL(jre/lib/ext) 폐기. PlatformCL이 대체.\n"
                    "• 6개월 릴리스 주기 시작: 그 전 3~5년 → 매년 3월/9월.\n"
                    "• 한계: 이때까지는 별도 JRE 배포가 여전히 존재 (Oracle 등). 사용자는 \"JRE 단독\"을 받을 수 있었음.",
                    font_size=12, color="#333"))

    write_file(els, f"{OV_DIR}/01b-jdk9-structure.excalidraw")


def gen_ov_01c_jdk11plus_structure():
    """JDK 11+ — 별도 JRE 배포 종료, jlink 커스텀 이미지가 표준"""
    els = []

    els.append(text(50, 30, "JDK 11+ LTS — 별도 JRE 배포 종료, jlink 이미지 시대",
                    font_size=24, color="#d84315"))
    els.append(text(50, 65,
                    "Oracle JDK 11부터 standalone JRE 별도 배포 중단. \"앱별 jlink 이미지\"가 사실상 표준.",
                    font_size=13, color="#666"))

    # 좌측: JDK 전체 박스
    els.append(rect(50, 110, 540, 580, stroke="#0277bd",
                    bg="#e3f2fd", fill_style="solid", stroke_width=3,
                    element_id="jdk_box"))
    els.append(text(70, 120, "$JAVA_HOME/   (JDK 21 LTS)",
                    font_size=18, color="#0277bd"))
    _dir_tree_box(els, 70, 165, 500, 510,
                  "JDK 전체 (개발자용)", "#0277bd", "#ffffff",
                  [
                      (0, "bin/", ""),
                      (1, "java, javac, jlink, jpackage", ""),
                      (1, "jstack, jmap, jcmd, jfr", ""),
                      (1, "javap, jshell, jdeps", ""),
                      (0, "lib/", ""),
                      (1, "modules", "(jimage)"),
                      (0, "conf/", ""),
                      (0, "include/", ""),
                      (0, "", ""),
                      (0, "→ 별도 JRE 배포는 없음 (Oracle 기준)", ""),
                      (0, "→ 사용자는 그냥 JDK 받거나", ""),
                      (0, "   jlink 이미지를 받음", ""),
                      (0, "", ""),
                      (0, "추가:", ""),
                      (1, "JDK 11: HTTP Client (java.net.http)", ""),
                      (1, "JDK 14: jpackage (설치파일)", ""),
                      (1, "JDK 15: Hidden Class", ""),
                      (1, "JDK 17: Sealed, Pattern Matching", ""),
                      (1, "JDK 21: Virtual Thread", ""),
                  ])

    # 우측: jlink 커스텀 이미지
    els.append(rect(620, 110, 540, 580, stroke="#388e3c",
                    bg="#e8f5e9", fill_style="solid", stroke_width=3,
                    element_id="jlink_box"))
    els.append(text(640, 120,
                    "./my-app-runtime/   (jlink로 만든 이미지)",
                    font_size=18, color="#388e3c"))
    _dir_tree_box(els, 640, 165, 500, 510,
                  "내 앱 전용 런타임 이미지 (배포용)", "#388e3c", "#ffffff",
                  [
                      (0, "bin/", ""),
                      (1, "java", "(실행기 only)"),
                      (0, "lib/", ""),
                      (1, "modules", "(필요한 모듈만)"),
                      (0, "conf/", ""),
                      (0, "", ""),
                      (0, "특징:", ""),
                      (0, "✓ 30~80MB로 작음", ""),
                      (0, "  (JDK 전체 ~300MB 대비)", ""),
                      (0, "✓ Docker 이미지 가벼움", ""),
                      (0, "✓ 보안 표면 작음", ""),
                      (0, "✓ AppCDS 미리 포함 가능", ""),
                      (0, "", ""),
                      (0, "생성 명령:", ""),
                      (0, "  $ jdeps --list-deps app.jar", ""),
                      (0, "  $ jlink \\", ""),
                      (0, "      --module-path $JAVA_HOME/jmods \\", ""),
                      (0, "      --add-modules java.base,java.sql \\", ""),
                      (0, "      --output my-app-runtime", ""),
                  ])

    # 화살표 — JDK에서 jlink 이미지 생성
    els.append(arrow(590, 400, [[0, 0], [30, 0]],
                     start_id="jdk_box", end_id="jlink_box",
                     stroke="#1e1e1e", stroke_width=3))
    els.append(text(595, 370, "jlink", font_size=14, color="#1e1e1e"))

    # 핵심 개념 박스
    els.append(rect(50, 720, 1110, 250, stroke="#1e1e1e", stroke_width=2,
                    bg="#fafafa", fill_style="solid"))
    els.append(text(70, 730, "🎯 핵심 개념 & 왜 이렇게 됐나",
                    font_size=18, color="#1e1e1e"))
    els.append(text(70, 765,
                    "• Oracle JDK 11부터 별도 JRE 배포 중단: jlink가 \"내 앱에 맞춤형 JRE\"를 만들 수 있게 되면서 "
                    "\"범용 JRE\"의 가치 약화.\n"
                    "• JDK 11 = 첫 LTS: prod에서 가장 많이 쓰이는 LTS 베이스. Oracle, Temurin, Corretto, Liberica 등 다양한 벤더.\n"
                    "• 2018.09 Oracle 라이선스 변경: Oracle JDK 상업 사용 유료화 → 대안 빌드(Temurin, Corretto) 폭발.\n"
                    "• 2021 Oracle No-Fee Terms (JDK 17~): 다시 무료화. 하지만 시장은 이미 다극화.\n"
                    "• Eclipse Temurin 등 일부 벤더는 한동안 JRE 빌드를 별도 제공 (호환성). 추세는 jlink 이미지로 이동.\n"
                    "• 컨테이너 시대의 패키징 표준: Spring Boot 앱 → jlink로 작은 런타임 + fat jar → Distroless 이미지로 100MB대 컨테이너.\n"
                    "• JRE 개념은 살아있다: \"실행에 필요한 최소 구성\"이라는 개념은 jlink 이미지가 계승. \"별도 표준 배포\"라는 형식만 사라짐.",
                    font_size=12, color="#333"))

    write_file(els, f"{OV_DIR}/01c-jdk11plus-structure.excalidraw")


# =========================================================================
# Chapter 01: Class Lifecycle
# =========================================================================

CL_DIR = "/Users/mac/Desktop/lemong/code/cj/flab/jvm/01-class-lifecycle/_excalidraw"


def gen_cl_01_classfile_format():
    """ClassFile 바이트 구조 — 세로 흐름"""
    els = []

    els.append(text(50, 30, "ClassFile 바이트 구조 (.class)", font_size=28,
                    color="#1e1e1e"))
    els.append(text(50, 70, "위에서 아래로 — 파일에 저장되는 순서 그대로",
                    font_size=14, color="#666"))

    # 좌측 메인 흐름 (세로)
    y = 120
    sections = [
        ("Magic", "0xCAFEBABE", "4B", "#d32f2f", "#ffebee"),
        ("minor / major", "버전 식별\nmajor=65 → JDK 21", "2B+2B", "#d32f2f", "#ffebee"),
        ("CP count", "Constant Pool 개수\n(1-indexed!)", "2B", "#0277bd", "#e3f2fd"),
        ("Constant Pool", "★ 가장 큰 영역\n18개 tag\nUtf8, Class, Methodref...\nLong/Double은 2슬롯", "가변", "#0277bd", "#e3f2fd"),
        ("access_flags", "0x0001 PUBLIC\n0x0010 FINAL\n0x0200 INTERFACE...", "2B", "#f57f17", "#fff8e1"),
        ("this/super_class", "CP CONSTANT_Class 인덱스\nsuper=0이면 Object 자신", "2B+2B", "#f57f17", "#fff8e1"),
        ("interfaces[]", "implements한 인터페이스들", "가변", "#f57f17", "#fff8e1"),
        ("fields[]", "field_info { flags, name, desc, attrs }", "가변", "#388e3c", "#e8f5e9"),
        ("methods[]", "★ method_info { flags, name, desc, attrs }\n  attrs 중 Code attribute가 본문", "가변", "#7b1fa2", "#f3e5f5"),
        ("attributes[]", "SourceFile, BootstrapMethods,\nNestHost, Record, ...", "가변", "#5d4037", "#efebe9"),
    ]

    for label, desc, sz, stroke, bg in sections:
        els.append(rect(80, y, 500, 70, stroke=stroke, bg=bg, fill_style="solid",
                        stroke_width=2))
        els.append(text(100, y + 8, label, font_size=18, color=stroke))
        els.append(text(100, y + 35, desc, font_size=11, color="#444"))
        els.append(text(530, y + 25, sz, font_size=14, color=stroke))
        y += 85

    # 우측 — Code attribute 상세 (zoom-in)
    els.append(rect(640, 120, 530, 720, stroke="#7b1fa2", stroke_width=2))
    els.append(text(660, 130, "Code attribute 상세 (모든 메서드)",
                    font_size=20, color="#7b1fa2"))

    code_y = 170
    code_sections = [
        ("max_stack", "javac가 미리 계산\noperand stack 최대 깊이"),
        ("max_locals", "local variable slot 수"),
        ("code_length", ""),
        ("code[]", "★ 실제 bytecode (200+ opcodes)\n  iload, istore, invokevirtual,\n  invokedynamic, ..."),
        ("exception_table[]", "{ start_pc, end_pc, handler_pc, catch_type }\n  catch_type=0 → finally"),
        ("attributes[]", "LineNumberTable\nLocalVariableTable\n★ StackMapTable (JDK 6+ 필수)"),
    ]
    for label, desc in code_sections:
        els.append(rect(660, code_y, 490, 80, stroke="#1e1e1e",
                        bg="#ffffff", stroke_width=1))
        els.append(text(680, code_y + 8, label, font_size=15, color="#7b1fa2"))
        els.append(text(680, code_y + 35, desc, font_size=12, color="#444"))
        code_y += 95

    # 진화 타임라인 (하단)
    els.append(rect(50, 1010, 1120, 230, stroke="#1e1e1e", stroke_width=2,
                    bg="#fafafa", fill_style="solid"))
    els.append(text(70, 1020, "ClassFile 포맷의 진화", font_size=22,
                    color="#1e1e1e"))
    els.append(text(70, 1055,
                    "JDK 5  (major=49) — Generics → Signature attribute, Annotation attributes\n"
                    "JDK 6  (major=50) — StackMapTable (optional)\n"
                    "JDK 7  (major=51) — invokedynamic + BootstrapMethods + CONSTANT_MethodHandle/Type/InvokeDynamic\n"
                    "JDK 8  (major=52) — Lambda, MethodParameters, RuntimeVisibleTypeAnnotations\n"
                    "JDK 9  (major=53) — Module attribute, CONSTANT_Module/Package\n"
                    "JDK 11 (major=55) — NestHost / NestMembers (synthetic accessor 제거)\n"
                    "JDK 16 (major=60) — Record attribute\n"
                    "JDK 17 (major=61) — PermittedSubclasses (sealed)\n"
                    "JDK 22+ (major=66+) — Class-File API (java.lang.classfile)",
                    font_size=13, color="#333"))

    write_file(els, f"{CL_DIR}/01-classfile-format.excalidraw")


def gen_cl_02_classloader_hierarchy():
    """ClassLoader 위임 + Tomcat/OSGi 변형"""
    els = []

    els.append(text(50, 30, "ClassLoader 위임 모델과 그 위반자들",
                    font_size=28, color="#1e1e1e"))
    els.append(text(50, 70,
                    "표준 위임 (좌) | Tomcat 반전 위임 (중) | OSGi 그래프 (우)",
                    font_size=14, color="#666"))

    # === 좌측: 표준 JDK 9+ 위임 ===
    els.append(rect(40, 110, 360, 580, stroke="#0277bd", stroke_width=2,
                    bg="#e3f2fd", fill_style="solid"))
    els.append(text(60, 120, "① JDK 9+ 표준 (3계층)", font_size=18,
                    color="#0277bd"))

    levels = [
        (60, 170, "Bootstrap CL", "(C++)\n$JAVA_HOME/lib/modules\njava.base, java.sql ...",
         "#d32f2f", "bs1"),
        (60, 290, "Platform CL", "(Java)\n표준이지만 비핵심 모듈\nJDK 9+ (구 Ext CL 대체)",
         "#f57f17", "p1"),
        (60, 410, "Application CL", "(Java)\n-classpath\n사용자 코드",
         "#388e3c", "a1"),
        (60, 530, "User CL", "URLClassLoader\n등 직접 만든 것",
         "#7b1fa2", "u1"),
    ]
    for x, y, name, desc, color, id_ in levels:
        els.append(rect(x, y, 320, 110, stroke=color, bg="#ffffff",
                        stroke_width=2, element_id=id_))
        els.append(text(x + 20, y + 10, name, font_size=16, color=color))
        els.append(text(x + 20, y + 35, desc, font_size=11, color="#333"))

    # 위로 향하는 위임 화살표
    els.append(arrow(220, 530, [[0, 0], [0, -110]],
                     start_id="u1", end_id="a1"))
    els.append(arrow(220, 410, [[0, 0], [0, -110]],
                     start_id="a1", end_id="p1"))
    els.append(arrow(220, 290, [[0, 0], [0, -110]],
                     start_id="p1", end_id="bs1"))

    els.append(text(60, 660, "★ 부모에게 먼저 묻고, 없으면 자기가 찾음",
                    font_size=12, color="#0277bd"))

    # === 중앙: Tomcat 반전 위임 ===
    els.append(rect(440, 110, 360, 580, stroke="#d84315", stroke_width=2,
                    bg="#ffe0b2", fill_style="solid"))
    els.append(text(460, 120, "② Tomcat WebappCL (반전)", font_size=18,
                    color="#d84315"))

    els.append(rect(460, 170, 320, 60, stroke="#d32f2f", bg="#ffffff",
                    stroke_width=2, element_id="bs2"))
    els.append(text(480, 180, "Bootstrap → Platform → App", font_size=13,
                    color="#d32f2f"))
    els.append(text(480, 205, "Tomcat Common / Catalina / Shared", font_size=11,
                    color="#666"))

    els.append(rect(460, 260, 320, 90, stroke="#d84315", bg="#fff3e0",
                    stroke_width=2, element_id="w1"))
    els.append(text(480, 270, "WebApp #1 CL", font_size=15, color="#d84315"))
    els.append(text(480, 295, "WEB-INF/classes + WEB-INF/lib\n자기 먼저 검색, 없으면 부모로",
                    font_size=11, color="#444"))

    els.append(rect(460, 380, 320, 90, stroke="#d84315", bg="#fff3e0",
                    stroke_width=2, element_id="w2"))
    els.append(text(480, 390, "WebApp #2 CL", font_size=15, color="#d84315"))
    els.append(text(480, 415, "독립된 라이브러리 버전\n격리 보장", font_size=11,
                    color="#444"))

    els.append(rect(460, 500, 320, 90, stroke="#d84315", bg="#fff3e0",
                    stroke_width=2, element_id="w3"))
    els.append(text(480, 510, "WebApp #3 CL", font_size=15, color="#d84315"))
    els.append(text(480, 535, "위와 동일 패턴", font_size=11, color="#444"))

    # 자기 먼저 (빨간) + 부모 (점선)
    els.append(arrow(620, 260, [[0, 0], [0, -30]],
                     start_id="w1", end_id="bs2", dashed=True))
    els.append(text(630, 230, "부모 (점선=2nd)", font_size=10, color="#999"))

    els.append(text(460, 615,
                    "★ 핵심: java.*/javax.* 외에는 자기 WEB-INF가 먼저\n"
                    "★ 이유: 각 webapp이 자기만의 라이브러리 버전 유지",
                    font_size=12, color="#d84315"))

    # === 우측: OSGi 그래프 ===
    els.append(rect(840, 110, 380, 580, stroke="#388e3c", stroke_width=2,
                    bg="#e8f5e9", fill_style="solid"))
    els.append(text(860, 120, "③ OSGi (DAG, 그래프 위임)",
                    font_size=18, color="#388e3c"))

    bundles = [
        (880, 180, "Bundle A", "exports: org.acme.api", "bA"),
        (1080, 180, "Bundle B", "imports A\nexports util", "bB"),
        (880, 340, "Bundle C", "imports A, B", "bC"),
        (1080, 340, "Bundle D", "exports lib", "bD"),
        (980, 500, "Bundle E", "imports C, D", "bE"),
    ]
    for x, y, name, desc, id_ in bundles:
        els.append(rect(x, y, 140, 80, stroke="#388e3c", bg="#ffffff",
                        stroke_width=2, element_id=id_))
        els.append(text(x + 15, y + 8, name, font_size=13, color="#388e3c"))
        els.append(text(x + 15, y + 32, desc, font_size=10, color="#444"))

    # 그래프 edges
    els.append(arrow(1020, 220, [[0, 0], [60, 0]],
                     start_id="bA", end_id="bB"))
    els.append(arrow(950, 260, [[0, 0], [0, 80]],
                     start_id="bA", end_id="bC"))
    els.append(arrow(1150, 260, [[0, 0], [-200, 80]],
                     start_id="bB", end_id="bC"))
    els.append(arrow(1020, 380, [[0, 0], [30, 120]],
                     start_id="bC", end_id="bE"))
    els.append(arrow(1150, 420, [[0, 0], [-100, 80]],
                     start_id="bD", end_id="bE"))

    els.append(text(860, 615,
                    "★ 각 Bundle이 자체 CL\n"
                    "★ import한 패키지의 클래스는 그 Bundle CL에 위임\n"
                    "★ 트리 아닌 DAG → 정밀한 모듈 격리",
                    font_size=12, color="#388e3c"))

    # === 하단: SPI + TCCL ===
    els.append(rect(40, 720, 1180, 200, stroke="#5d4037", stroke_width=2,
                    bg="#efebe9", fill_style="solid"))
    els.append(text(60, 730, "④ SPI 패턴과 Thread Context ClassLoader",
                    font_size=20, color="#5d4037"))

    els.append(text(60, 770,
                    "문제: DriverManager(Bootstrap)이 MySQL Driver(AppCL)를 찾아야 한다 — 일반 위임으로는 불가능 (부모가 자식 코드를 모름)\n"
                    "해결: Thread.currentThread().getContextClassLoader()를 통해 자식 CL에 접근\n\n"
                    "Bootstrap → DriverManager.loadInitialDrivers()\n"
                    "    ↓\n"
                    "ServiceLoader.load(Driver.class)  ←  내부적으로 TCCL 사용\n"
                    "    ↓\n"
                    "AppCL  →  META-INF/services/java.sql.Driver  →  MySQL Driver 발견\n\n"
                    "그 외: JAXP, JNDI, JCE, SLF4J, JAXB 등 모든 SPI",
                    font_size=12, color="#444"))

    write_file(els, f"{CL_DIR}/02-classloader-hierarchy.excalidraw")


def gen_cl_03_linking_stages():
    """Linking 5단계 + Verification 4 Pass + 에러 매핑"""
    els = []

    els.append(text(50, 30, "Loading → Linking → Initialization 5단계",
                    font_size=28, color="#1e1e1e"))
    els.append(text(50, 70,
                    "각 단계가 무엇을 하는지 + 어떤 에러를 던지는지",
                    font_size=14, color="#666"))

    # 가로 5단계
    stages = [
        (60, 120, "1) Loading", ".class → InstanceKlass\nClassLoader가 메모리 적재",
         "#0277bd", "#e3f2fd"),
        (300, 120, "2) Verification", "타입 안전성 증명\n★ 4 Pass ★", "#d32f2f", "#ffebee"),
        (540, 120, "3) Preparation", "static 필드 default (0/null)\nConstantValue는 즉시",
         "#f57f17", "#fff8e1"),
        (780, 120, "4) Resolution", "심볼릭 → 직접 참조\nLazy + Caching",
         "#388e3c", "#e8f5e9"),
        (1020, 120, "5) Initialization", "<clinit> 실행\nJLS 12.4.2 락 절차",
         "#7b1fa2", "#f3e5f5"),
    ]
    for x, y, label, desc, color, bg in stages:
        els.append(rect(x, y, 200, 130, stroke=color, bg=bg, fill_style="solid",
                        stroke_width=3))
        els.append(text(x + 15, y + 10, label, font_size=17, color=color))
        els.append(text(x + 15, y + 50, desc, font_size=12, color="#444"))

    # 화살표 연결
    for i in range(4):
        sx = 260 + i * 240
        els.append(arrow(sx, 185, [[0, 0], [40, 0]]))

    # Linking 묶음 표시
    els.append(rect(290, 95, 700, 170, stroke="#999", stroke_width=1,
                    bg="transparent", fill_style="solid"))
    els.append(text(560, 280, "← Linking (3단계) →", font_size=14,
                    color="#999"))

    # Verification 4 Pass 상세 (중앙 하단)
    els.append(rect(290, 320, 700, 280, stroke="#d32f2f", stroke_width=2,
                    bg="#fff5f5", fill_style="solid"))
    els.append(text(310, 330, "Verification 4 Pass 상세", font_size=20,
                    color="#d32f2f"))

    passes = [
        (310, 370, "Pass 1: ClassFile 포맷",
         "magic == 0xCAFEBABE, version 지원 범위, CP 형식 → ClassFormatError"),
        (310, 430, "Pass 2: 의미적 일관성",
         "final 클래스 상속 금지, interface 제약, ... → VerifyError"),
        (310, 490, "Pass 3: ★ Bytecode 검증 ★",
         "각 instruction의 stack/locals 타입 일관성\nStackMapTable과 비교 (JDK 6+) → VerifyError"),
        (310, 550, "Pass 4: 심볼릭 참조 검증",
         "Resolution 단계와 통합 → NoSuchFieldError/NoSuchMethodError/IllegalAccessError"),
    ]
    for x, y, label, desc in passes:
        els.append(text(x, y, label, font_size=14, color="#d32f2f"))
        els.append(text(x + 20, y + 22, desc, font_size=11, color="#666"))

    # Resolution 흐름 (좌하단)
    els.append(rect(60, 640, 580, 220, stroke="#388e3c", stroke_width=2,
                    bg="#e8f5e9", fill_style="solid"))
    els.append(text(80, 650, "Resolution: Symbolic → Direct (Lazy + Cached)",
                    font_size=18, color="#388e3c"))
    els.append(text(80, 690,
                    "ClassFile 안:                                    메모리 안:\n"
                    "\"java/lang/System\" + \"out\"   →→→→→→→→→→→→  System.class 의 out 필드 메모리 offset\n"
                    "CONSTANT_Fieldref CP 엔트리                    (Field* 포인터)\n\n"
                    "처음 접근 시점에 resolve → CP에 cache → 두 번째부터 즉시\n\n"
                    "Trigger instructions:\n"
                    "  getstatic, putstatic, getfield, putfield\n"
                    "  invokevirtual/special/static/interface/dynamic\n"
                    "  new, checkcast, instanceof, anewarray, ldc",
                    font_size=12, color="#444"))

    # Initialization 12-step (우하단)
    els.append(rect(680, 640, 540, 220, stroke="#7b1fa2", stroke_width=2,
                    bg="#f3e5f5", fill_style="solid"))
    els.append(text(700, 650, "Initialization JLS 12.4.2 (요약 핵심)",
                    font_size=18, color="#7b1fa2"))
    els.append(text(700, 685,
                    "Step 1.  Class init lock 획득\n"
                    "Step 2.  다른 스레드 init 중 → wait\n"
                    "Step 3.  이 스레드 재귀 호출 → return (★ 순환 회피)\n"
                    "Step 4.  이미 INITIALIZED → return\n"
                    "Step 5.  ERRONEOUS → NoClassDefFoundError\n"
                    "Step 6.  INITIALIZING 마킹\n"
                    "Step 7.  Lock 해제\n"
                    "Step 9.  Super class init (재귀)\n"
                    "         Super interface init (default method 있는 것)\n"
                    "Step 10. <clinit> 실행\n"
                    "         실패 → ERRONEOUS + ExceptionInInitializerError",
                    font_size=11, color="#444"))

    # 하단 에러 매핑
    els.append(rect(60, 890, 1160, 100, stroke="#1e1e1e", stroke_width=2,
                    bg="#fafafa", fill_style="solid"))
    els.append(text(80, 900, "에러 → 단계 매핑", font_size=18, color="#1e1e1e"))
    els.append(text(80, 935,
                    "ClassFormatError → Pass 1   |   VerifyError → Pass 2/3   |   NoSuchFieldError/NoSuchMethodError → Pass 4\n"
                    "IllegalAccessError → Pass 4 (가시성)   |   IncompatibleClassChangeError → Pass 4 (시그니처 변경)\n"
                    "ExceptionInInitializerError → Initialization   |   NoClassDefFoundError → 이후 모든 접근 (영구 erroneous)",
                    font_size=12, color="#333"))

    write_file(els, f"{CL_DIR}/03-linking-stages.excalidraw")


def gen_cl_04_class_lifecycle():
    """Class lifecycle 전체 — 탄생부터 unload까지"""
    els = []

    els.append(text(50, 30, "Class Lifecycle — 탄생부터 죽음까지",
                    font_size=28, color="#1e1e1e"))
    els.append(text(50, 70, "Loading → Linking → Initialization → 사용 → Unload",
                    font_size=14, color="#666"))

    # 상단: 트리거 6가지
    els.append(rect(40, 110, 1180, 130, stroke="#0277bd", stroke_width=2,
                    bg="#e3f2fd", fill_style="solid"))
    els.append(text(60, 120, "Initialization 트리거 (JVMS 5.5) — 정확히 6가지",
                    font_size=18, color="#0277bd"))

    triggers = [
        (60, 160, "1) new MyClass()"),
        (260, 160, "2) MyClass.staticMethod()"),
        (520, 160, "3) MyClass.staticField (★ ConstantValue 제외)"),
        (60, 200, "4) Class.forName(\"X\", true, ...)"),
        (340, 200, "5) JVM 시작 시 main 클래스"),
        (640, 200, "6) Subclass init → 부모 (인터페이스는 default method 있을 때만)"),
    ]
    for x, y, t in triggers:
        els.append(text(x, y, t, font_size=13, color="#0277bd"))

    # 중앙: State 전이
    els.append(rect(40, 270, 1180, 330, stroke="#388e3c", stroke_width=2,
                    bg="#e8f5e9", fill_style="solid"))
    els.append(text(60, 280, "InstanceKlass State Machine (HotSpot)",
                    font_size=20, color="#388e3c"))

    states = [
        (80, 330, "allocated", "메모리만 할당", "#999", "s_a"),
        (280, 330, "loaded", "ClassFile 파싱 완료", "#0277bd", "s_l"),
        (480, 330, "linked", "verify + prepare 완료", "#f57f17", "s_li"),
        (680, 330, "being_initialized", "<clinit> 실행 중", "#7b1fa2", "s_bi"),
        (920, 330, "fully_initialized", "★ 완료 ★", "#388e3c", "s_fi"),
        (480, 480, "initialization_error", "★ 영구 erroneous ★\n이후 모든 접근 NCDFE",
         "#d32f2f", "s_e"),
    ]
    for x, y, label, desc, color, id_ in states:
        els.append(rect(x, y, 180, 100, stroke=color, bg="#ffffff",
                        stroke_width=2, element_id=id_))
        els.append(text(x + 15, y + 10, label, font_size=14, color=color))
        els.append(text(x + 15, y + 40, desc, font_size=11, color="#444"))

    # 전이 화살표
    els.append(arrow(260, 380, [[0, 0], [20, 0]],
                     start_id="s_a", end_id="s_l"))
    els.append(arrow(460, 380, [[0, 0], [20, 0]],
                     start_id="s_l", end_id="s_li"))
    els.append(arrow(660, 380, [[0, 0], [20, 0]],
                     start_id="s_li", end_id="s_bi"))
    els.append(arrow(860, 380, [[0, 0], [60, 0]],
                     start_id="s_bi", end_id="s_fi"))

    # 에러 전이
    els.append(arrow(780, 430, [[0, 0], [-200, 50]],
                     start_id="s_bi", end_id="s_e", dashed=True))
    els.append(text(550, 460, "예외 발생", font_size=11, color="#d32f2f"))

    # 하단: Unload 조건 + 흐름
    els.append(rect(40, 630, 580, 360, stroke="#d84315", stroke_width=2,
                    bg="#fff3e0", fill_style="solid"))
    els.append(text(60, 640, "ClassLoader Unload 조건",
                    font_size=20, color="#d84315"))

    conditions = [
        (60, 685, "1) CL 객체 GC root에서 unreachable"),
        (60, 720, "2) CL이 로드한 모든 Class 객체 unreachable"),
        (60, 755, "3) 그 Class들의 모든 인스턴스 unreachable"),
        (60, 790, "4) 다른 CL의 코드가 이 CL의 클래스 참조 없음"),
    ]
    for x, y, t in conditions:
        els.append(text(x, y, t, font_size=14, color="#d84315"))

    els.append(text(60, 850, "★ Bootstrap/Platform/App CL은 사실상 영구 → unload 불가",
                    font_size=12, color="#d32f2f"))
    els.append(text(60, 880, "★ 사용자 정의 CL (URLClassLoader, WebappCL) 만 unload 가능",
                    font_size=12, color="#d32f2f"))
    els.append(text(60, 920,
                    "흔한 누수: ThreadLocal, JDBC Driver, static collection,\n"
                    "JMX, Logging cache, Reflection cache",
                    font_size=12, color="#666"))

    # 우하단: Initialization 함정
    els.append(rect(660, 630, 560, 360, stroke="#7b1fa2", stroke_width=2,
                    bg="#f3e5f5", fill_style="solid"))
    els.append(text(680, 640, "Initialization 4대 함정",
                    font_size=20, color="#7b1fa2"))

    pitfalls = [
        ("ConstantValue 인라이닝",
         "static final 상수가 사용 클래스의 .class에 박힘\n"
         "→ 값 바꿔도 재컴파일 안 하면 옛값 그대로"),
        ("부모 ↔ 인터페이스 초기화 차이",
         "부모: 항상 먼저\n"
         "인터페이스: default method 있는 경우만"),
        ("순환 의존",
         "한 스레드의 재귀: Step 3로 회피 (값은 0)\n"
         "두 스레드 교차: 데드락 가능"),
        ("ExceptionInInitializerError 영구",
         "한 번 실패 → 영구 erroneous\n"
         "이후 접근은 모두 NoClassDefFoundError"),
    ]
    py = 685
    for title, desc in pitfalls:
        els.append(text(680, py, "▸ " + title, font_size=14, color="#7b1fa2"))
        els.append(text(700, py + 20, desc, font_size=11, color="#444"))
        py += 70

    write_file(els, f"{CL_DIR}/04-class-lifecycle.excalidraw")


# =========================================================================
# Top-level: 전체 챕터 의존 그래프
# =========================================================================

TOP_DIR = "/Users/mac/Desktop/lemong/code/cj/flab/jvm/_diagrams"


def gen_dependency_graph():
    """전체 챕터 의존 그래프 — 본 챕터 + 보강 챕터 + 종합"""
    els = []

    els.append(text(50, 30, "JVM 학습 의존 그래프 — 본 + 보강 + 종합",
                    font_size=26, color="#1e1e1e"))
    els.append(text(50, 70,
                    "위에서 아래로 학습. 보강 챕터 (10/11/12)는 '시니어/창시자 수준' 도달용.",
                    font_size=13, color="#666"))

    BOX_W, BOX_H = 230, 80

    # === 본 챕터 (좌측 메인 흐름) ===
    nodes = {
        "n00": (510, 120,  "00 Overview",          "JVM/JRE/JDK, 컴파일 흐름,\n아키텍처, 역사",
                "#0277bd", "#e3f2fd"),
        "n01": (240, 260,  "01 Class Lifecycle",   "ClassFile, ClassLoader,\nLinking, Initialization",
                "#388e3c", "#e8f5e9"),
        "n06": (780, 260,  "06 Version History",   "JDK 8 → 9 → 17 → 21\n변천사 풀버전",
                "#f57f17", "#fff8e1"),
        "n02": (240, 400,  "02 Runtime Data Areas","Heap, Metaspace,\nStack/PC, Code Cache",
                "#388e3c", "#e8f5e9"),
        "n03": ( 60, 540,  "03 Execution Engine",  "Interp, C1/C2,\n★ EA, Inline Cache,\nSpeculative Opt",
                "#7b1fa2", "#f3e5f5"),
        "n05": (420, 540,  "05 Threading",         "★ JMM happens-before,\nMem Barrier, Loom,\nMark Word",
                "#7b1fa2", "#f3e5f5"),
        "n04": ( 60, 700,  "04 GC",                "Serial → ... → ZGC\n★ SATB/IU, Brooks/LRB,\nColored Pointer",
                "#d32f2f", "#ffebee"),
        "n07": (290, 860,  "07 HotSpot Internals", "OpenJDK C++ 소스\n★ C2 phase 풀버전\nSea-of-Nodes 노드",
                "#5d4037", "#efebe9"),
        "n08": (290, 1020, "08 GraalVM",           "Graal vs C2,\nNative Image (SVM),\nTruffle",
                "#5d4037", "#efebe9"),

        # === 보강 챕터 (우측) ⭐ ===
        "n10": (820, 540,  "⭐ 10 Ops Scenarios",   "P99 spike, Full GC,\nMetaspace OOM, VT pinning,\nContainer OOM",
                "#f9a825", "#fff9c4"),
        "n11": (820, 700,  "⭐ 11 Hands-on Workbook","JMH 벤치마크, JFR 분석,\nasync-profiler, MAT,\nGC log 해석",
                "#f9a825", "#fff9c4"),
        "n12": (820, 860,  "⭐ 12 Tradeoff Master",  "GC 7종, JVM 5종,\nAOT vs JIT, Threading\n종합 비교표",
                "#f9a825", "#fff9c4"),

        # === 종합 ===
        "n09": (550, 1180, "🏁 09 Mock Interviews", "Junior / Senior /\nPrincipal 시나리오\n+ 운영 사고 시뮬",
                "#d84315", "#fff3e0"),
    }

    for nid, (x, y, label, sub, color, bg) in nodes.items():
        # 보강 챕터는 박스 더 큼 (3줄 텍스트)
        h = BOX_H + (20 if nid in ("n03", "n04", "n05", "n07", "n10", "n11", "n12") else 0)
        els.append(rect(x, y, BOX_W, h, stroke=color, bg=bg,
                        fill_style="solid", stroke_width=2,
                        element_id=nid))
        els.append(text(x + 15, y + 8, label, font_size=15, color=color))
        els.append(text(x + 15, y + 32, sub, font_size=11, color="#444"))

    # === 엣지 ===
    edges = [
        # 본 챕터 흐름
        ("n00", "n01", False, "#1e1e1e"),
        ("n00", "n06", False, "#1e1e1e"),
        ("n01", "n02", False, "#1e1e1e"),
        ("n02", "n03", False, "#1e1e1e"),
        ("n02", "n05", False, "#1e1e1e"),
        ("n03", "n04", False, "#1e1e1e"),
        ("n03", "n07", False, "#1e1e1e"),
        ("n04", "n07", False, "#1e1e1e"),
        ("n05", "n07", False, "#1e1e1e"),
        ("n07", "n08", False, "#1e1e1e"),

        # 보강 챕터 의존
        ("n03", "n10", True, "#f9a825"),   # JIT 운영 시나리오
        ("n04", "n10", True, "#f9a825"),   # GC 운영 시나리오
        ("n05", "n10", True, "#f9a825"),   # Threading 운영 시나리오
        ("n03", "n11", True, "#f9a825"),   # JIT 실습
        ("n04", "n11", True, "#f9a825"),   # GC 실습
        ("n10", "n11", False, "#f9a825"),  # 시나리오 → 실습 자연 흐름
        ("n04", "n12", True, "#f9a825"),   # GC 비교
        ("n05", "n12", True, "#f9a825"),   # Threading 비교
        ("n08", "n12", True, "#f9a825"),   # JVM 구현 비교

        # 모두 09로 (dashed light gray)
        ("n08", "n09", True, "#999"),
        ("n10", "n09", True, "#999"),
        ("n11", "n09", True, "#999"),
        ("n12", "n09", True, "#999"),
    ]

    def cb(nid):
        x, y, *_ = nodes[nid]
        h = BOX_H + (20 if nid in ("n03", "n04", "n05", "n07", "n10", "n11", "n12") else 0)
        return (x + BOX_W / 2, y + h)

    def ct(nid):
        x, y, *_ = nodes[nid]
        return (x + BOX_W / 2, y)

    def cr(nid):
        x, y, *_ = nodes[nid]
        h = BOX_H + (20 if nid in ("n03", "n04", "n05", "n07", "n10", "n11", "n12") else 0)
        return (x + BOX_W, y + h / 2)

    def cl(nid):
        x, y, *_ = nodes[nid]
        h = BOX_H + (20 if nid in ("n03", "n04", "n05", "n07", "n10", "n11", "n12") else 0)
        return (x, y + h / 2)

    for fid, tid, dashed, color in edges:
        fx, fy, *_ = nodes[fid]
        tx, ty, *_ = nodes[tid]

        # 좌→우 이동인 경우 (보강 챕터로 가는 의존)
        if fx + BOX_W < tx:
            sx, sy = cr(fid)
            ex, ey = cl(tid)
        # 우→좌 (드물게)
        elif tx + BOX_W < fx:
            sx, sy = cl(fid)
            ex, ey = cr(tid)
        # 같은 컬럼이면 위/아래
        elif abs((fx + BOX_W / 2) - (tx + BOX_W / 2)) < 50:
            sx, sy = cb(fid)
            ex, ey = ct(tid)
        # 그 외 (대각선, 위→아래)
        else:
            sx, sy = cb(fid)
            ex, ey = ct(tid)

        els.append(arrow(sx, sy, [[0, 0], [ex - sx, ey - sy]],
                          start_id=fid, end_id=tid,
                          dashed=dashed,
                          stroke=color))

    # 범례
    els.append(rect(60, 120, 170, 130, stroke="#1e1e1e", stroke_width=1,
                    bg="#fafafa", fill_style="solid"))
    els.append(text(75, 130, "범례", font_size=15, color="#1e1e1e"))
    els.append(line(80, 165, [[0, 0], [40, 0]], stroke="#1e1e1e",
                     stroke_width=2))
    els.append(text(130, 158, "본 챕터 흐름", font_size=11, color="#1e1e1e"))
    els.append(line(80, 195, [[0, 0], [40, 0]], stroke="#f9a825",
                     stroke_width=2, dashed=True))
    els.append(text(130, 188, "보강 의존", font_size=11, color="#f9a825"))
    els.append(line(80, 225, [[0, 0], [40, 0]], stroke="#999",
                     stroke_width=2, dashed=True))
    els.append(text(130, 218, "09 통합", font_size=11, color="#666"))

    # 우측 영역 라벨
    els.append(text(820, 480,
                    "⭐ 보강 챕터 (시니어/창시자 수준)",
                    font_size=14, color="#f9a825"))

    # 학습 시간 표시
    els.append(rect(60, 1320, 1100, 110, stroke="#1e1e1e", stroke_width=2,
                    bg="#f5f5f5", fill_style="solid"))
    els.append(text(80, 1330, "16주 완전 학습 가이드",
                    font_size=18, color="#1e1e1e"))
    els.append(text(80, 1360,
                    "1주: 00   |   2주: 01   |   3주: 02   |   4-5주: 03 (JIT 깊이)   |   "
                    "6-7주: 04 (GC + ZGC/Shenandoah)\n"
                    "8주: 05 Threading   |   9주: 06   |   10-11주: 07 HotSpot 소스   |   "
                    "12주: 08 + 12 Tradeoff\n"
                    "⭐ 13주: 10 Ops Scenarios   |   ⭐ 14주: 11 Hands-on Workbook   |   "
                    "15-16주: 09 Mock Interview",
                    font_size=12, color="#333"))

    write_file(els, f"{TOP_DIR}/dependency-graph.excalidraw")


if __name__ == "__main__":
    print("Generating Excalidraw diagrams...")
    print("[Top-level]")
    gen_dependency_graph()
    print("[Chapter 00 - Overview]")
    gen_01_jvm_jre_jdk()
    gen_02_compile_flow()
    gen_03_jvm_architecture()
    gen_04_jvm_timeline()
    print("[Chapter 00 - Overview: 패키징 구조 진화]")
    gen_ov_01a_jdk8_structure()
    gen_ov_01b_jdk9_structure()
    gen_ov_01c_jdk11plus_structure()
    print("[Chapter 01 - Class Lifecycle]")
    gen_cl_01_classfile_format()
    gen_cl_02_classloader_hierarchy()
    gen_cl_03_linking_stages()
    gen_cl_04_class_lifecycle()
    print("Done.")
