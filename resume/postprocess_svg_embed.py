#!/usr/bin/env python3
"""
docx 의 PNG 이미지 6개에 대응되는 SVG 를 같이 임베드.
Word 2016+ 는 <asvg:svgBlip>을 보고 SVG 를 native 로 렌더링 (사용자 PC 폰트 사용).
PNG 는 호환성 fallback 으로만 잔존.
"""

import os
import shutil
import tempfile
import zipfile
import re
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
SRC_DOCX = ROOT / "resume_v12.docx"
OUT_DOCX = ROOT / "resume_v12.docx"  # overwrite
DIAGRAMS = ROOT / "diagrams"

# PNG → SVG 매핑 (이미지 임베드 순서대로)
PNG_TO_SVG = {
    "image1.png": "A1_system_overview.svg",
    "image2.png": "A2_payment_webhook_4layer.svg",
    "image3.png": "B1_rds_queue_cas.svg",
    "image4.png": "C1_session_lock_registry.svg",
    "image5.png": "C2_proxy_pool_before_after.svg",
    "image6.png": "C3_akamai_bypass_state_machine.svg",
}

# 작업 디렉토리 — sandbox-safe (매번 새 mkdtemp)
WORK = Path(tempfile.mkdtemp(prefix="docx_work_", dir="/tmp"))

# docx 압축 풀기
with zipfile.ZipFile(SRC_DOCX, "r") as z:
    z.extractall(WORK)

# 1) media 에 SVG 6개 복사
media_dir = WORK / "word" / "media"
for png_name, svg_name in PNG_TO_SVG.items():
    src = DIAGRAMS / svg_name
    dst = media_dir / png_name.replace(".png", ".svg")
    shutil.copy(src, dst)

# 2) word/_rels/document.xml.rels — SVG 에 대응되는 rId 추가
rels_path = WORK / "word" / "_rels" / "document.xml.rels"
rels_text = rels_path.read_text(encoding="utf-8")

# 기존 rId 의 max 찾기
existing_ids = [int(m.group(1)) for m in re.finditer(r'Id="rId(\d+)"', rels_text)]
next_id = max(existing_ids) + 1 if existing_ids else 1

# PNG 의 rId 를 image 파일명별로 매핑
png_rid = {}  # filename → rId
for m in re.finditer(r'Id="(rId\d+)"\s+Type="[^"]*image"\s+Target="media/([^"]+)"', rels_text):
    png_rid[m.group(2)] = m.group(1)

# SVG 들의 rId 도 새로 할당
svg_rid = {}  # svg filename → rId
new_relationships = []
for png_name in PNG_TO_SVG.keys():
    if png_name not in png_rid:
        print(f"!! PNG {png_name} 의 rId 없음 — 건너뜀")
        continue
    svg_name_in_docx = png_name.replace(".png", ".svg")
    rid = f"rId{next_id}"
    svg_rid[svg_name_in_docx] = rid
    new_relationships.append(
        f'<Relationship Id="{rid}" '
        f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
        f'Target="media/{svg_name_in_docx}"/>'
    )
    next_id += 1

# Relationships 클로징 직전에 삽입
rels_text = rels_text.replace(
    "</Relationships>",
    "".join(new_relationships) + "</Relationships>",
)
rels_path.write_text(rels_text, encoding="utf-8")

# 3) [Content_Types].xml 에 svg+xml 추가
ct_path = WORK / "[Content_Types].xml"
ct_text = ct_path.read_text(encoding="utf-8")
if 'image/svg+xml' not in ct_text:
    # <Default Extension="svg" ContentType="image/svg+xml"/> 삽입
    ct_text = ct_text.replace(
        "</Types>",
        '<Default Extension="svg" ContentType="image/svg+xml"/></Types>',
    )
    ct_path.write_text(ct_text, encoding="utf-8")

# 4) document.xml — 각 <a:blip r:embed="rIdN"/> 안에 SVG extension 추가
doc_path = WORK / "word" / "document.xml"
doc_text = doc_path.read_text(encoding="utf-8")

# Namespace 선언이 이미 있는지 확인 후 없으면 root 에 추가
NS_ASVG = ' xmlns:asvg="http://schemas.microsoft.com/office/drawing/2016/SVG/main"'
NS_A14 = ' xmlns:a14="http://schemas.microsoft.com/office/drawing/2010/main"'
if "xmlns:asvg" not in doc_text:
    doc_text = doc_text.replace("<w:document ", "<w:document" + NS_ASVG + " ", 1)
if "xmlns:a14" not in doc_text:
    doc_text = doc_text.replace("<w:document ", "<w:document" + NS_A14 + " ", 1)

# PNG rId 별로 svg blip extension 삽입
# <a:blip r:embed="rIdN"/> → <a:blip r:embed="rIdN"><a:extLst>...<asvg:svgBlip r:embed="rIdM"/>...</a:extLst></a:blip>
# rId(PNG) ↔ rId(SVG) 매핑은 위에서 만들어둠

# PNG rId 별 SVG rId 매핑
png_to_svg_rid = {}
for png_name, svg_name in PNG_TO_SVG.items():
    if png_name in png_rid and png_name.replace(".png", ".svg") in svg_rid:
        png_to_svg_rid[png_rid[png_name]] = svg_rid[png_name.replace(".png", ".svg")]

print(f"PNG → SVG rId 매핑: {png_to_svg_rid}")


def make_svg_ext(svg_rid_value):
    return (
        '<a:extLst>'
        '<a:ext uri="{96DAC541-7B7A-43D3-8B79-37D633B846F1}">'
        f'<asvg:svgBlip xmlns:asvg="http://schemas.microsoft.com/office/drawing/2016/SVG/main" r:embed="{svg_rid_value}"/>'
        '</a:ext>'
        '</a:extLst>'
    )


def replace_blip(m):
    blip_open = m.group(0)
    rid = m.group(1)
    if rid not in png_to_svg_rid:
        return blip_open
    svg_r = png_to_svg_rid[rid]
    return f'<a:blip r:embed="{rid}">{make_svg_ext(svg_r)}</a:blip>'


# self-closing <a:blip ... /> 도 처리
self_close_pat = re.compile(r'<a:blip\s+r:embed="(rId\d+)"\s*/>')
doc_text, n1 = self_close_pat.subn(replace_blip, doc_text)
# open tag <a:blip r:embed="..."> ... </a:blip>
open_pat = re.compile(r'<a:blip\s+r:embed="(rId\d+)"\s*>')


def replace_open(m):
    rid = m.group(1)
    if rid not in png_to_svg_rid:
        return m.group(0)
    svg_r = png_to_svg_rid[rid]
    # 이 경우 close tag 가 있고 그 사이에 다른 ext 가 있을 수 있으므로
    # 일단 open 만 처리 → close 직전에 ext 추가가 필요
    return f'<a:blip r:embed="{rid}">{make_svg_ext(svg_r)}'


# 단순한 self-close 위주로 처리되었을 것이라 가정 (python-docx 가 보통 self-close 로 생성)
print(f"self-close blip 치환 수: {n1}")

doc_path.write_text(doc_text, encoding="utf-8")

# 5) zip 다시 압축
TMP_OUT = ROOT / "_resume_v12.tmp.docx"
with zipfile.ZipFile(TMP_OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for root, dirs, files in os.walk(WORK):
        for f in files:
            full = Path(root) / f
            arcname = full.relative_to(WORK)
            z.write(full, arcname)

shutil.move(TMP_OUT, OUT_DOCX)
try:
    shutil.rmtree(WORK)
except Exception:
    pass  # /tmp 정리 실패해도 결과물에 영향 없음
print(f"✓ saved: {OUT_DOCX}  ({OUT_DOCX.stat().st_size//1024} KB)")
