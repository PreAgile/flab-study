"""
외부 플랫폼 자동화 워크플로 — HTTP → RabbitMQ 마이그레이션 발표 자료 생성기.

서비스 명칭은 의도적으로 일반화한다:
  API 서버  (사용자 향 API · 도메인 소유)
  중계 서버 (오케스트레이터 · 워크플로)
  스크래퍼 서버 (외부 플랫폼 자동화 워커)
  배치 서버 (정기 잡 · 중계 서버로 흡수 예정)

산출물:
- ../architecture-as-is.excalidraw    + .svg
- ../architecture-to-be.excalidraw    + .svg
- ../problems.png                     (Pillow 직접 렌더)

실행:
    python3 scripts/gen_diagrams.py
"""

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER_DIR = ROOT.parent.parent / "flab-study" / "jvm" / "_tools"
sys.path.insert(0, str(HELPER_DIR))

from gen_excalidraw import rect, text, arrow, write_file  # noqa: E402


# ============================================================================
# 팔레트
# ============================================================================
CLR_TEXT = "#1e1e1e"
CLR_MUTED = "#666666"

CLR_API = "#1565c0"          # API 서버
CLR_API_BG = "#e3f2fd"

CLR_MED = "#6a1b9a"           # 중계 서버
CLR_MED_BG = "#f3e5f5"

CLR_SCR = "#ef6c00"           # 스크래퍼 서버
CLR_SCR_BG = "#fff3e0"

CLR_BATCH = "#455a64"         # 배치 서버
CLR_BATCH_BG = "#eceff1"

CLR_MQ = "#2e7d32"            # RabbitMQ
CLR_MQ_BG = "#e8f5e9"

CLR_DB = "#0277bd"            # Aurora
CLR_DB_BG = "#e1f5fe"

CLR_EXT = "#5d4037"           # 외부 플랫폼
CLR_EXT_BG = "#efebe9"

CLR_PAIN = "#c62828"
CLR_PAIN_BG = "#ffebee"

CLR_GOOD = "#2e7d32"
CLR_GOOD_BG = "#e8f5e9"


# ============================================================================
# As-Is
# ============================================================================
def gen_as_is():
    e = []

    # 타이틀
    e.append(text(60, 30,
                  "As-Is  ·  현재 구조 (HTTP 동기 호출 체인)",
                  font_size=30, color=CLR_TEXT))
    e.append(text(60, 75,
                  "사용자가 댓글 등록을 누르면 → API 서버가 중계 서버에 HTTP → 중계 서버가 스크래퍼에 HTTP → 스크래퍼가 외부 플랫폼 자동화 (5분+)",
                  font_size=15, color=CLR_MUTED))

    # 외부 플랫폼 (맨 우측)
    e.append(rect(1300, 130, 240, 200, stroke=CLR_EXT, stroke_width=3,
                  bg=CLR_EXT_BG, fill_style="solid", element_id="ext"))
    e.append(text(1315, 142, "외부 플랫폼", font_size=20, color=CLR_EXT))
    e.append(text(1315, 175,
                  "배달의민족\n쿠팡이츠\n요기요\n땡겨요\n네이버 플레이스\n카카오맵 등",
                  font_size=13, color=CLR_EXT))
    e.append(text(1315, 295,
                  "사장이 손으로 로그인·\n댓글 작성하는 화면을\n스크래퍼가 자동화",
                  font_size=11, color=CLR_MUTED))

    # ── 서비스 박스 3개 ──
    e.append(rect(60, 130, 320, 200, stroke=CLR_API, stroke_width=3,
                  bg=CLR_API_BG, fill_style="solid", element_id="api"))
    e.append(text(80, 142, "① API 서버", font_size=22, color=CLR_API))
    e.append(text(80, 175,
                  "역할: 사용자 향 API · 도메인 소유\n"
                  "스택: NestJS + TypeORM\n"
                  "보유 테이블:\n"
                  " · review  (외부 플랫폼에서 가져온 리뷰)\n"
                  " · reply   (사장이 단 답글)\n"
                  " · job, campaign\n"
                  " · rds_queue (현재의 DB 기반 큐)",
                  font_size=12, color=CLR_API))

    e.append(rect(440, 130, 320, 200, stroke=CLR_MED, stroke_width=3,
                  bg=CLR_MED_BG, fill_style="solid", element_id="med"))
    e.append(text(460, 142, "② 중계 서버", font_size=22, color=CLR_MED))
    e.append(text(460, 175,
                  "역할: 현재는 HTTP 중계만 함\n"
                  "스택: FastAPI\n"
                  "엔드포인트:\n"
                  " · /populate  (리뷰 수집)\n"
                  " · /reply     (댓글 작성 트리거)\n"
                  " · /score, /dashboard\n"
                  "→ API 서버 ↔ 스크래퍼 사이 동기 패스스루",
                  font_size=12, color=CLR_MED))

    e.append(rect(820, 130, 320, 200, stroke=CLR_SCR, stroke_width=3,
                  bg=CLR_SCR_BG, fill_style="solid", element_id="scr"))
    e.append(text(840, 142, "③ 스크래퍼 서버", font_size=22, color=CLR_SCR))
    e.append(text(840, 175,
                  "역할: 외부 플랫폼 자동화 워커\n"
                  "스택: NestJS + Playwright\n"
                  "동작:\n"
                  " · 헤드리스 브라우저로 로그인\n"
                  " · 댓글 1건당 30s ~ 5분+\n"
                  " · 봇 차단 / 캡차로 변동 큼\n"
                  " · OOM·세션 만료로 자주 죽음",
                  font_size=12, color=CLR_SCR))

    # 배치 서버 (별도, 좌측 상단)
    e.append(rect(60, 30, 320, 80, stroke=CLR_BATCH, stroke_width=2,
                  bg=CLR_BATCH_BG, fill_style="solid", element_id="batch"))
    e.append(text(80, 40, "④ 배치 서버", font_size=18, color=CLR_BATCH))
    e.append(text(80, 65,
                  "FastAPI 기반 정기 잡 (백필·집계·블라인드 처리)\n"
                  "별도 운영 중 → 중계 서버로 통합 예정",
                  font_size=12, color=CLR_BATCH))

    # 단계 화살표 (단계 번호 ①→②→③→외부)
    e.append(arrow(380, 230, [[0, 0], [60, 0]],
                   stroke=CLR_TEXT, stroke_width=3))
    e.append(text(385, 195,
                  "ⓐ HTTP POST\n5분+ 점유",
                  font_size=12, color=CLR_TEXT))

    e.append(arrow(760, 230, [[0, 0], [60, 0]],
                   stroke=CLR_TEXT, stroke_width=3))
    e.append(text(765, 195,
                  "ⓑ HTTP POST\n5분+ 점유",
                  font_size=12, color=CLR_TEXT))

    e.append(arrow(1140, 230, [[0, 0], [160, 0]],
                   stroke=CLR_SCR, stroke_width=3))
    e.append(text(1150, 195,
                  "ⓒ Playwright 자동화\n외부 플랫폼 호출",
                  font_size=12, color=CLR_SCR))

    # 응답 점선 (전부 동기 대기)
    e.append(arrow(820, 285, [[0, 0], [-60, 0]],
                   stroke=CLR_MUTED, stroke_width=2, dashed=True))
    e.append(arrow(440, 285, [[0, 0], [-60, 0]],
                   stroke=CLR_MUTED, stroke_width=2, dashed=True))
    e.append(text(450, 295,
                  "전 구간 응답 대기 (블로킹) — 5분+ 동안 HTTP 소켓 점유",
                  font_size=11, color=CLR_MUTED))

    # 빨강 ❶
    e.append(rect(60, 360, 540, 80, stroke=CLR_PAIN, stroke_width=2,
                  bg=CLR_PAIN_BG, fill_style="solid"))
    e.append(text(75, 370,
                  "❶ HTTP 커넥션 5분+ 점유 → 풀 고갈 / 게이트웨이 타임아웃",
                  font_size=14, color=CLR_PAIN))
    e.append(text(75, 400,
                  "동시 1,000건 처리 시 1,000개 소켓이 5분간 잠긴다.\n"
                  "ALB idle timeout(60s) 도달 → 응답은 버려지지만 스크래퍼는 계속 일함 (멱등성 깨짐)",
                  font_size=12, color=CLR_PAIN))

    e.append(rect(620, 360, 540, 80, stroke=CLR_PAIN, stroke_width=2,
                  bg=CLR_PAIN_BG, fill_style="solid"))
    e.append(text(635, 370,
                  "❷ 스크래퍼 다운 = 전체 5xx cascade (회로차단기 부재)",
                  font_size=14, color=CLR_PAIN))
    e.append(text(635, 400,
                  "스크래퍼 한 대 OOM → 중계 500 → API 500 → 사용자 에러.\n"
                  "재시도 폭주로 정상 인스턴스까지 같이 무너진다 (thundering herd).",
                  font_size=12, color=CLR_PAIN))

    # Aurora MySQL
    e.append(rect(60, 470, 1480, 250, stroke=CLR_DB, stroke_width=3,
                  bg=CLR_DB_BG, fill_style="solid", element_id="aurora"))
    e.append(text(80, 482,
                  "Aurora MySQL  ·  API 서버 / 중계 서버 / 배치 서버가 모두 같은 클러스터·같은 스키마를 공유한다",
                  font_size=18, color=CLR_DB))

    e.append(rect(90, 530, 650, 180, stroke=CLR_DB, stroke_width=2,
                  bg="#ffffff", fill_style="solid"))
    e.append(text(105, 540, "Writer  ·  db.r7g.xlarge (4 vCPU)",
                  font_size=15, color=CLR_DB))
    e.append(text(105, 570,
                  "테이블: review, reply, rds_queue, shop, campaign, job, ...\n\n"
                  "한 reply 라이프사이클당 발생 SQL:\n"
                  "  INSERT reply        (status = BATCH_PENDING)\n"
                  "  INSERT rds_queue    (payload)\n"
                  "  UPDATE reply        → PENDING\n"
                  "  UPDATE reply        → IN_PROGRESS\n"
                  "  UPDATE reply        → COMPLETED  ← 동일 행 4번 두드림",
                  font_size=12, color=CLR_TEXT))

    e.append(rect(770, 530, 750, 180, stroke=CLR_DB, stroke_width=2,
                  bg="#ffffff", fill_style="solid"))
    e.append(text(785, 540,
                  "Reader  ·  db.t4g.medium",
                  font_size=15, color=CLR_DB))
    e.append(text(785, 570,
                  "현재 활용도 낮음 — 대부분의 SELECT 도 Writer 로 간다.\n"
                  "인스턴스 사이즈도 작아 본격 활용이 어려움.\n\n"
                  "→ Writer 가 단일 병목. AAS(Active Sessions) 가 max vCPU 를\n"
                  "   넘으면 모든 트랜잭션의 commit latency 가 같이 솟는다.",
                  font_size=12, color=CLR_TEXT))

    # 화살표: 세 서비스 → Aurora
    e.append(arrow(220, 330, [[0, 0], [0, 200]],
                   stroke=CLR_DB, stroke_width=2, dashed=True))
    e.append(text(100, 440,
                  "INSERT·UPDATE 폭주\n(reply, rds_queue, ...)",
                  font_size=11, color=CLR_DB))

    e.append(arrow(600, 330, [[0, 0], [0, 200]],
                   stroke=CLR_DB, stroke_width=2, dashed=True))
    e.append(text(480, 440,
                  "UPDATE review (동기화)\nINSERT review (백필)",
                  font_size=11, color=CLR_DB))

    e.append(arrow(220, 110, [[0, 0], [0, 20]],
                   stroke=CLR_DB, stroke_width=2, dashed=True))

    # 빨강 ❸
    e.append(rect(60, 750, 1480, 90, stroke=CLR_PAIN, stroke_width=2,
                  bg=CLR_PAIN_BG, fill_style="solid"))
    e.append(text(75, 760,
                  "❸ 동일 reply 행에 INSERT 1 + UPDATE 3 → 행 락·인덱스 페이지 latch 경합, AAS 폭증",
                  font_size=15, color=CLR_PAIN))
    e.append(text(75, 790,
                  "동시 수천 건이 같은 보조 인덱스(예: review_id, status, created_at)의 같은 페이지를 갱신.\n"
                  "InnoDB row-lock + secondary index latch · undo log 폭증 · binlog flush 지연.\n"
                  "Writer 1대(db.r7g.xlarge)에 세션이 누적 → commit latency·세션 수 같이 솟는다.",
                  font_size=12, color=CLR_PAIN))

    # 범례
    e.append(text(60, 870,
                  "범례   ━━ HTTP 동기 호출   ⋯⋯ DB DML / 응답 대기   ①②③④ 서비스   ⓐⓑⓒ 호출 단계   ❶❷❸ 통증",
                  font_size=12, color=CLR_MUTED))

    out = ROOT / "architecture-as-is.excalidraw"
    write_file(e, str(out))


# ============================================================================
# To-Be
# ============================================================================
def gen_to_be():
    e = []

    e.append(text(60, 30,
                  "To-Be  ·  RabbitMQ 비동기 + Job 테이블 SoT",
                  font_size=30, color=CLR_TEXT))
    e.append(text(60, 75,
                  "강결합 분리 (fire-and-forget) · 배치 서버 흡수 · "
                  "메시지 상태는 Job 테이블이 단일 진실원 (SoT) · Outbox 로 RDB 부담 최소화",
                  font_size=15, color=CLR_MUTED))

    # 외부 플랫폼 (우측 하단, 강조 약하게)
    e.append(rect(1320, 130, 220, 130, stroke=CLR_EXT, stroke_width=3,
                  bg=CLR_EXT_BG, fill_style="solid", element_id="ext"))
    e.append(text(1335, 142, "외부 플랫폼", font_size=18, color=CLR_EXT))
    e.append(text(1335, 170,
                  "배달의민족·쿠팡이츠\n요기요·땡겨요·네이버·\n카카오맵 등",
                  font_size=12, color=CLR_EXT))
    e.append(text(1335, 230,
                  "Playwright 로\n자동화 호출",
                  font_size=11, color=CLR_MUTED))

    # 서비스 박스 3개
    e.append(rect(60, 130, 320, 190, stroke=CLR_API, stroke_width=3,
                  bg=CLR_API_BG, fill_style="solid", element_id="api"))
    e.append(text(80, 142, "① API 서버", font_size=22, color=CLR_API))
    e.append(text(80, 175,
                  "역할: 사용자 향 API · 도메인 소유\n"
                  "변경:\n"
                  " · reply.request 발행 (publish)\n"
                  " · reply.complete 소비 (consume)\n"
                  " · job, outbox 테이블 추가\n"
                  " · rds_queue 제거 (Phase 3)\n"
                  " · reply UPDATE 3회 → 1회",
                  font_size=12, color=CLR_API))

    e.append(rect(460, 130, 320, 190, stroke=CLR_MED, stroke_width=3,
                  bg=CLR_MED_BG, fill_style="solid", element_id="med"))
    e.append(text(480, 142, "② 중계 서버 (오케스트레이터)",
                  font_size=18, color=CLR_MED))
    e.append(text(480, 178,
                  "역할: 워크플로 오케스트레이션\n"
                  "변경:\n"
                  " · reply.request 소비\n"
                  " · scrape.request 발행\n"
                  " · scrape.complete 소비\n"
                  " · reply.complete 발행\n"
                  " · 배치 서버 잡 흡수",
                  font_size=12, color=CLR_MED))

    e.append(rect(860, 130, 320, 190, stroke=CLR_SCR, stroke_width=3,
                  bg=CLR_SCR_BG, fill_style="solid", element_id="scr"))
    e.append(text(880, 142, "③ 스크래퍼 서버", font_size=22, color=CLR_SCR))
    e.append(text(880, 175,
                  "역할: 외부 플랫폼 자동화 워커\n"
                  "변경:\n"
                  " · scrape.request 소비\n"
                  " · scrape.complete 발행\n"
                  " · 죽어도 메시지는 RMQ 가 보존\n"
                  " · prefetch=N 으로 동시성 제어\n"
                  " · 5분+ 작업이어도 OK",
                  font_size=12, color=CLR_SCR))

    # RabbitMQ broker
    e.append(rect(60, 370, 1480, 140, stroke=CLR_MQ, stroke_width=3,
                  bg=CLR_MQ_BG, fill_style="solid", element_id="rmq"))
    e.append(text(80, 382,
                  "RabbitMQ Broker  ·  durable queue · publisher confirm · ack on success · DLQ 라우팅",
                  font_size=17, color=CLR_MQ))

    # 4 큐
    queues = [
        ("queue: reply.request",  "API 서버 → 중계 서버",     90),
        ("queue: scrape.request", "중계 서버 → 스크래퍼",     390),
        ("queue: scrape.complete", "스크래퍼 → 중계 서버",    690),
        ("queue: reply.complete",  "중계 서버 → API 서버",    990),
    ]
    for q_name, q_dir, qx in queues:
        e.append(rect(qx, 420, 280, 70, stroke=CLR_MQ, stroke_width=1,
                      bg="#ffffff", fill_style="solid"))
        e.append(text(qx + 15, 428, q_name, font_size=13, color=CLR_MQ))
        e.append(text(qx + 15, 452,
                      f"방향: {q_dir}\nat-least-once · idempotency key",
                      font_size=11, color=CLR_TEXT))

    # DLQ
    e.append(rect(1310, 420, 220, 70, stroke=CLR_PAIN, stroke_width=2,
                  bg="#ffffff", fill_style="solid"))
    e.append(text(1325, 428, "DLQ (Dead Letter Queue)",
                  font_size=12, color=CLR_PAIN))
    e.append(text(1325, 452,
                  "retry 초과 메시지 격리\n→ 관측·수동 재처리",
                  font_size=11, color=CLR_PAIN))

    # 화살표 — 단계 ⓐ~ⓕ
    # ⓐ API → RMQ (publish reply.request)
    e.append(arrow(220, 320, [[0, 0], [0, 50]],
                   stroke=CLR_API, stroke_width=2))
    e.append(text(70, 335, "ⓐ publish\nreply.request",
                  font_size=11, color=CLR_API))

    # ⓑ RMQ → 중계 (consume reply.request)
    e.append(arrow(230, 370, [[0, 0], [380, -50]],
                   stroke=CLR_MED, stroke_width=2))
    e.append(text(300, 348, "ⓑ consume reply.request",
                  font_size=11, color=CLR_MED))

    # ⓒ 중계 → RMQ (publish scrape.request)
    e.append(arrow(600, 320, [[0, 0], [-70, 50]],
                   stroke=CLR_MED, stroke_width=2))
    e.append(text(500, 340, "ⓒ publish\nscrape.request",
                  font_size=11, color=CLR_MED))

    # ⓓ RMQ → 스크래퍼 (consume scrape.request)
    e.append(arrow(550, 370, [[0, 0], [450, -50]],
                   stroke=CLR_SCR, stroke_width=2))
    e.append(text(700, 348, "ⓓ consume scrape.request",
                  font_size=11, color=CLR_SCR))

    # ⓔ 스크래퍼 → RMQ (publish scrape.complete)
    e.append(arrow(1020, 320, [[0, 0], [-180, 50]],
                   stroke=CLR_SCR, stroke_width=2))
    e.append(text(880, 340, "ⓔ publish\nscrape.complete",
                  font_size=11, color=CLR_SCR))

    # ⓕ RMQ → 중계 (consume scrape.complete)
    e.append(arrow(830, 370, [[0, 0], [-220, -50]],
                   stroke=CLR_MED, stroke_width=2))
    e.append(text(640, 360, "ⓕ consume scrape.complete",
                  font_size=11, color=CLR_MED))

    # ⓖ 중계 → RMQ (publish reply.complete)
    e.append(arrow(620, 320, [[0, 0], [500, 50]],
                   stroke=CLR_MED, stroke_width=2))
    e.append(text(900, 305, "ⓖ publish reply.complete",
                  font_size=11, color=CLR_MED))

    # ⓗ RMQ → API (consume reply.complete)
    e.append(arrow(1130, 370, [[0, 0], [-900, -50]],
                   stroke=CLR_API, stroke_width=2))
    e.append(text(620, 376, "ⓗ consume reply.complete",
                  font_size=11, color=CLR_API))

    # 스크래퍼 → 외부 플랫폼
    e.append(arrow(1180, 200, [[0, 0], [140, 0]],
                   stroke=CLR_SCR, stroke_width=2))
    e.append(text(1190, 175,
                  "Playwright\n자동화 호출",
                  font_size=11, color=CLR_SCR))

    # Aurora
    e.append(rect(60, 540, 1480, 200, stroke=CLR_DB, stroke_width=3,
                  bg=CLR_DB_BG, fill_style="solid", element_id="aurora"))
    e.append(text(80, 552,
                  "Aurora MySQL (공유, 그대로) — Job 테이블 = Source of Truth · "
                  "Reply 행 UPDATE 1회로 압축",
                  font_size=18, color=CLR_DB))

    # 좌측: Reply/Review 도메인 (변경 최소)
    e.append(rect(90, 590, 380, 140, stroke=CLR_DB, stroke_width=2,
                  bg="#ffffff", fill_style="solid"))
    e.append(text(105, 600, "도메인 테이블 (review, reply, ...)",
                  font_size=14, color=CLR_DB))
    e.append(text(105, 628,
                  "· reply 의 중간 상태 컬럼은 Job 으로 이관\n"
                  "· INSERT 1 + 최종 UPDATE 1 (총 2회 DML)\n"
                  "· 보조 인덱스(status 등) 갱신 1/3 로 감소\n"
                  "· 락 점유 시간·undo·binlog 부담 ↓",
                  font_size=12, color=CLR_TEXT))

    # 가운데: job 테이블 (SoT)
    e.append(rect(490, 590, 480, 140, stroke=CLR_GOOD, stroke_width=3,
                  bg=CLR_GOOD_BG, fill_style="solid"))
    e.append(text(505, 600, "job  ·  Source of Truth (메시지 상태)",
                  font_size=14, color=CLR_GOOD))
    e.append(text(505, 628,
                  "PK  job_id   (= correlation_id, idempotency key)\n"
                  "FK  reply_id, review_id\n"
                  "status: CREATED · QUEUED · IN_PROGRESS\n"
                  "        · COMPLETED · FAILED · CANCELED\n"
                  "payload JSON · retries · last_error · updated_at",
                  font_size=12, color=CLR_TEXT))

    # 우측: outbox
    e.append(rect(990, 590, 540, 140, stroke=CLR_GOOD, stroke_width=2,
                  bg="#ffffff", fill_style="solid"))
    e.append(text(1005, 600, "outbox  ·  트랜잭션 발행 보장",
                  font_size=14, color=CLR_GOOD))
    e.append(text(1005, 628,
                  "Reply INSERT + Job INSERT + Outbox INSERT 를\n"
                  "동일 트랜잭션·동일 commit 으로 묶는다 (bulk).\n"
                  "별도 relay 가 outbox → RMQ 로 발행.\n"
                  "→ 'DB 는 롤백됐는데 메시지는 나갔다' 사라짐.",
                  font_size=12, color=CLR_TEXT))

    # 상태 머신
    e.append(rect(60, 770, 940, 110, stroke=CLR_GOOD, stroke_width=2,
                  bg="#ffffff", fill_style="solid"))
    e.append(text(75, 782, "Job 상태 전이",
                  font_size=16, color=CLR_GOOD))
    e.append(rect(80, 815, 130, 50, stroke=CLR_GOOD))
    e.append(text(105, 830, "CREATED", font_size=13, color=CLR_GOOD))
    e.append(arrow(210, 840, [[0, 0], [30, 0]], stroke=CLR_GOOD))
    e.append(rect(240, 815, 130, 50, stroke=CLR_GOOD))
    e.append(text(275, 830, "QUEUED", font_size=13, color=CLR_GOOD))
    e.append(arrow(370, 840, [[0, 0], [30, 0]], stroke=CLR_GOOD))
    e.append(rect(400, 815, 170, 50, stroke=CLR_GOOD))
    e.append(text(425, 830, "IN_PROGRESS", font_size=13, color=CLR_GOOD))
    e.append(arrow(570, 840, [[0, 0], [30, 0]], stroke=CLR_GOOD))
    e.append(rect(600, 815, 160, 50, stroke=CLR_GOOD))
    e.append(text(625, 830, "COMPLETED", font_size=13, color=CLR_GOOD))
    e.append(arrow(685, 815, [[0, 0], [40, -10]],
                   stroke=CLR_PAIN, stroke_width=2))
    e.append(rect(725, 780, 100, 35, stroke=CLR_PAIN))
    e.append(text(745, 790, "FAILED", font_size=12, color=CLR_PAIN))
    e.append(arrow(685, 865, [[0, 0], [40, 12]],
                   stroke=CLR_MUTED, stroke_width=2, dashed=True))
    e.append(rect(725, 870, 110, 30, stroke=CLR_MUTED))
    e.append(text(745, 877, "CANCELED", font_size=12, color=CLR_MUTED))

    # 우측: 핵심 효과
    e.append(rect(1020, 770, 520, 110, stroke=CLR_GOOD, stroke_width=2,
                  bg=CLR_GOOD_BG, fill_style="solid"))
    e.append(text(1035, 780, "핵심 효과",
                  font_size=15, color=CLR_GOOD))
    e.append(text(1035, 805,
                  "· HTTP 5분+ 점유 → 0초 (publish only)\n"
                  "· 스크래퍼 다운 = 큐 backlog 만 쌓일 뿐, 5xx 없음\n"
                  "· Reply 행 UPDATE 3회 → 1회\n"
                  "· 메시지 상태: Job 테이블 단일 SoT (Redis 통계는 캐시)",
                  font_size=12, color=CLR_GOOD))

    e.append(text(60, 910,
                  "범례   ━━ MQ publish/consume   ⓐ~ⓗ 메시지 흐름 단계   ①②③ 서비스",
                  font_size=12, color=CLR_MUTED))

    out = ROOT / "architecture-to-be.excalidraw"
    write_file(e, str(out))


# ============================================================================
# problems.png  (Pillow)
# ============================================================================
def gen_problems_png():
    from PIL import Image, ImageDraw, ImageFont

    W, H = 1600, 1000
    img = Image.new("RGB", (W, H), "#ffffff")
    d = ImageDraw.Draw(img)

    def font(size):
        candidates = [
            "/System/Library/Fonts/AppleSDGothicNeo.ttc",
            "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
            "/Library/Fonts/Arial Unicode.ttf",
        ]
        for p in candidates:
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
        return ImageFont.load_default()

    f_title = font(34)
    f_h2 = font(22)
    f_body = font(16)
    f_small = font(13)
    f_caption = font(12)

    C_TEXT = "#1e1e1e"
    C_MUTED = "#666666"
    C_PAIN = "#c62828"
    C_PAIN_BG = "#ffebee"
    C_OK = "#2e7d32"
    C_API = "#1565c0"
    C_SCR = "#ef6c00"

    # 타이틀
    d.text((40, 30),
           "현재 구조의 통증 3가지 — 메커니즘까지",
           fill=C_TEXT, font=f_title)
    d.text((40, 80),
           "왜 HTTP → RabbitMQ 로 가야 하는가. "
           "한 컷에 담는다.",
           fill=C_MUTED, font=f_body)

    def panel(x, y, w, h, idx, title, subtitle):
        d.rectangle([x, y, x + w, y + h], outline=C_PAIN, width=2,
                    fill=C_PAIN_BG)
        d.text((x + 16, y + 12),
               f"❶❷❸"[idx - 1] + "  " + title,
               fill=C_PAIN, font=f_h2)
        d.text((x + 16, y + 48), subtitle, fill=C_MUTED, font=f_small)

    PY = 140
    PH = 720

    # ── Panel 1: HTTP 점유 ──
    panel(40, PY, 500, PH, 1,
          "HTTP 커넥션 5분+ 점유",
          "1 요청 = 1 소켓이 5분 동안 잠긴다")

    bx, by = 70, PY + 90
    d.rectangle([bx, by, bx + 220, by + 70], outline=C_API, width=2,
                fill="#e3f2fd")
    d.text((bx + 16, by + 12), "API 서버", fill=C_API, font=f_h2)
    d.text((bx + 16, by + 44), "HTTP pool: 100", fill=C_API,
           font=f_small)

    # 풀 그리드 (10x10) — 전부 점유
    gx, gy = 70, by + 100
    cell = 20
    for i in range(10):
        for j in range(10):
            d.rectangle([gx + j * cell, gy + i * cell,
                         gx + (j + 1) * cell - 2,
                         gy + (i + 1) * cell - 2],
                        outline=C_PAIN, fill=C_PAIN, width=1)
    d.text((gx + 220, gy + 10),
           "100/100 in-flight\n(전부 5분+ 점유)",
           fill=C_PAIN, font=f_body)

    # 화살표 → 스크래퍼
    scrx, scry = 360, by + 220
    d.rectangle([scrx, scry, scrx + 150, scry + 50],
                outline=C_SCR, width=2, fill="#fff3e0")
    d.text((scrx + 6, scry + 10), "스크래퍼", fill=C_SCR, font=f_body)
    d.text((scrx + 6, scry + 30), "5분+ 작업", fill=C_SCR, font=f_caption)
    d.line([gx + 180, gy + 100, scrx, scry + 25], fill=C_PAIN, width=3)

    # 결과
    d.text((70, PY + 470),
           "❌ 101번째 요청 → 풀 빈자리 없음 → 429 / 503",
           fill=C_PAIN, font=f_body)
    d.text((70, PY + 500),
           "❌ ALB idle timeout(60s) 도달 → 클라이언트 끊김",
           fill=C_PAIN, font=f_body)
    d.text((70, PY + 525),
           "   그래도 스크래퍼는 계속 일함 → 응답 버려짐",
           fill=C_PAIN, font=f_body)
    d.text((70, PY + 565),
           "→ MQ 면: publish 즉시 소켓 반납, 0초 점유",
           fill=C_OK, font=f_body)

    # ── Panel 2: Aurora 락 경합 ──
    panel(560, PY, 500, PH, 2,
          "Aurora 락 경합 — 한 reply 행을 4번 두드린다",
          "INSERT 1 + UPDATE 3 + rds_queue INSERT 1")

    tlx, tly = 600, PY + 110
    d.line([tlx, tly + 110, tlx + 400, tly + 110], fill=C_TEXT, width=2)
    steps = [
        ("t1", "INSERT reply\n(BATCH_PENDING)", "행 락 획득"),
        ("t2", "INSERT rds_queue\n(payload)", "별 테이블 INSERT"),
        ("t3", "UPDATE reply\n→ PENDING", "행 락 재획득"),
        ("t4", "UPDATE reply\n→ IN_PROGRESS", "다시 또"),
        ("t5", "UPDATE reply\n→ COMPLETED", "또 다시"),
    ]
    for i, (t, what, why) in enumerate(steps):
        x = tlx + i * 80 + 20
        d.line([x, tly + 110, x, tly + 100], fill=C_TEXT, width=2)
        d.ellipse([x - 5, tly + 105, x + 5, tly + 115],
                  outline=C_TEXT, fill=C_PAIN, width=1)
        d.text((x - 8, tly + 75), t, fill=C_TEXT, font=f_small)
        d.text((x - 30, tly + 125), what, fill=C_TEXT, font=f_caption)
        d.text((x - 30, tly + 165), why, fill=C_PAIN, font=f_caption)

    d.text((tlx - 20, tly + 220),
           "× 동시 1,000건이 같은 보조 인덱스",
           fill=C_PAIN, font=f_body)
    d.text((tlx - 20, tly + 245),
           "  (review_id / status / created_at) 같은",
           fill=C_PAIN, font=f_body)
    d.text((tlx - 20, tly + 270),
           "  page 를 동시에 갱신",
           fill=C_PAIN, font=f_body)
    d.text((tlx - 20, tly + 310),
           "→ InnoDB row lock + index page latch 경합",
           fill=C_PAIN, font=f_body)
    d.text((tlx - 20, tly + 335),
           "→ undo / binlog flush 동반 지연",
           fill=C_PAIN, font=f_body)
    d.text((tlx - 20, tly + 380),
           "→ MQ + Job SoT 면: 중간 상태는 Job 에만,",
           fill=C_OK, font=f_body)
    d.text((tlx - 20, tly + 405),
           "    Reply 최종 1회 UPDATE → 인덱스 갱신 1/3",
           fill=C_OK, font=f_body)

    # ── Panel 3: AAS spike ──
    panel(1080, PY, 480, PH, 3,
          "AAS(Active Sessions) 폭증",
          "Writer 1대(db.r7g.xlarge, 4 vCPU)의 한계 도달")

    cx0, cy0 = 1110, PY + 130
    cw, ch = 420, 350
    d.rectangle([cx0, cy0, cx0 + cw, cy0 + ch], outline=C_TEXT, width=1)

    vcpu_y = cy0 + int(ch * 0.55)
    d.line([cx0, vcpu_y, cx0 + cw, vcpu_y], fill=C_OK, width=2)
    d.text((cx0 + cw + 6, vcpu_y - 8),
           "max\nvCPU=4", fill=C_OK, font=f_caption)

    pts = []
    for i in range(cw + 1):
        x = cx0 + i
        t = i / cw
        baseline = 0.5
        spike1 = 6.0 * math.exp(-((t - 0.35) ** 2) / 0.003)
        spike2 = 7.5 * math.exp(-((t - 0.62) ** 2) / 0.004)
        v = baseline + spike1 + spike2
        y = cy0 + ch - int(min(v, 10) / 10 * ch)
        pts.append((x, y))
    poly = pts + [(cx0 + cw, cy0 + ch), (cx0, cy0 + ch)]
    d.polygon(poly, fill="#ffcdd2")
    for i in range(len(pts) - 1):
        d.line([pts[i], pts[i + 1]], fill=C_PAIN, width=2)

    d.text((cx0 - 20, cy0), "AAS", fill=C_TEXT, font=f_small)
    d.text((cx0, cy0 + ch + 6), "time →", fill=C_MUTED, font=f_small)
    d.text((cx0 + 100, cy0 + 10),
           "댓글 캠페인\n일괄 발사",
           fill=C_PAIN, font=f_caption)
    d.text((cx0 + 240, cy0 - 5),
           "스크래퍼 재시도\n폭주 구간",
           fill=C_PAIN, font=f_caption)

    d.text((cx0, cy0 + ch + 40),
           "AAS > max vCPU = 세션 대기열 형성",
           fill=C_PAIN, font=f_body)
    d.text((cx0, cy0 + ch + 65),
           "→ 모든 트랜잭션 commit latency ↑",
           fill=C_PAIN, font=f_body)
    d.text((cx0, cy0 + ch + 100),
           "→ MQ + Outbox 면: DML 빈도 ↓ → 곡선 평탄화",
           fill=C_OK, font=f_body)

    # 푸터 — 핵심 우려와 답
    d.rectangle([40, 890, W - 40, 970], outline=C_OK, width=2,
                fill="#e8f5e9")
    d.text((60, 902),
           "Q. Job 테이블을 또 만들면 INSERT/UPDATE 가 늘어서 락이 더 심해지지 않나?",
           fill=C_OK, font=f_h2)
    d.text((60, 935),
           "A. Reply+Job+Outbox 를 한 트랜잭션·한 commit·bulk insert 로 묶고, "
           "이후 상태 전이는 Job 에만. Reply 인덱스 갱신은 최종 1회. 총 DML 은 오히려 줄어든다.",
           fill=C_OK, font=f_body)

    out = ROOT / "problems.png"
    img.save(str(out), "PNG", optimize=True)
    print(f"  -> {out}")


# ============================================================================
if __name__ == "__main__":
    gen_as_is()
    gen_to_be()
    gen_problems_png()
    print("\nDone.")
