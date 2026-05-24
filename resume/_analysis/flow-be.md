# flow-be 코드/커밋 기반 시니어 레벨 사례 추출

> 회사: 르몽(Lemong), 서비스: 댓글몽
> 분석 대상: `~/Desktop/lemong/project/flow-be` (FastAPI 기반 배치 + AI 파이프라인 BE)
> 커밋 범위: PR #1 (2026-01-13) ~ PR #39 (2026-03-13), `main` 브랜치 기준
> 작성 시점: 2026-05-23
> 참고 자료: `resume/resume_v9.md`, `resume/architecture.md`, `resume/기술이력서_개인정보삭제.pdf`

---

## 0. flow-be 한 줄 정의 (조사 결과)

`flow-be`는 댓글몽의 **운영(Operations) 콘솔용 백엔드**다. 사용자용 SaaS BE(`cmong-be`, NestJS)와 작업 큐 워커(`cmong-mq`)는 별도 시스템이고, `flow-be`는 다음을 담당한다.

1. **운영 어드민의 리뷰·주문·매장 수집 잡 트리거 (배치)**
   - "이 매장 리뷰 30일치 다시 긁어와 / AI 답글 다시 생성해" 같은 운영 액션을 백오피스에서 수행할 수 있도록 노출.
   - `api/services/populate.py` → `task/services/populate_task.py` 라인.
2. **정기 크롤 스케줄러 (Cron)**
   - APScheduler 기반으로 활성 매장의 리뷰/주문 수집을 시간 단위로 자동 실행.
   - `task/services/scheduler/` 4개 서비스 + `task/models/cron_job.py`.
3. **AI 파이프라인 통합**
   - MLOps 서비스(`ml.lemong.ai`)에 답글 생성, 리뷰 스코어링(불만족 탐지)을 요청하고 결과를 영속화.
   - `task/clients/ai_client.py`, `task/services/score_processor.py`, `task/services/template_replies_cache.py`.
4. **댓글몽 Biz(프랜차이즈) 대시보드 데이터 공급**
   - 1000+ 매장의 크롤링 지연/주문 누락/광고 ROAS/매출 7일 트렌드를 SQL VIEW + raw SQL로 집계.
   - `api/services/dashboard.py`, `task/services/shop_dashboard_task.py`, `task/services/advertisement_task.py`.
5. **자동 답글 게시 (PR #39)**
   - AI가 생성한 reply2를 BE API로 다시 호출해 실제 플랫폼에 게시.
   - `task/services/populate_task.py:_execute_auto_replies`, `task/clients/be_client.py:post_reply`.

### `cmong-mq`와의 역할 분담 (코드 근거)

- 템플릿 답글의 **버전 식별자가 cmong-mq에서 정의된 값을 그대로 차용** ─ `task/services/template_replies_cache.py:14` 주석 `# Template version names (from cmong-mq)`, `TEMPLATE_VERSIONS = {"template", "template-short"}`. 즉 정기 트래픽의 AI 생성과 템플릿 운영은 cmong-mq가 책임지고, flow-be는 그 산출물(`ai_replies` 테이블)을 **읽어 캐싱·재사용**한다.
- 자동 답글 게시(`is_auto_reply=True`)는 flow-be가 BE API의 `POST /users/{user_id}/shops/{shop_id}/reviews/{review_id}/replies`를 호출하는 형태(`task/clients/be_client.py:115-142`). 즉 flow-be는 **AI 생성 + 정책 결정(매장별 별점 컷오프, 기간, 홍보문구 합성)** 까지 하고, **실제 플랫폼 송신은 cmong-be에 위임**한다.

이 구조 위에서 김면수 본인이 짚어준 5개 영역(자동댓글, 크롤 잡 관리, 불만족 리뷰, 수천만 건 집계, mq 협업)을 시니어 5년차 톤으로 5단(배경/구현/아키텍처/도전과 해결/결과) + 사용 기술로 정리한다.

---

## 사례 1 ─ 운영용 비동기 잡 오케스트레이션과 서버 재시작 시 자동 복구

**구분**: 백오피스 / 배치 / 분산 상태 관리
**핵심 커밋**: PR #26 `d106278` (Job 스키마 정리 + orphaned job 자동 재시도, 2026-02-06), 베이스 PR #11 `721056b`, 콜드패스 부트스트랩 `app/main.py:30-78`.

### 배경

운영팀이 백오피스에서 "특정 매장의 최근 30일 리뷰를 다시 긁어와 AI 답글까지 새로 생성해" 같은 요청을 누르면, 한 잡당 평균 분 단위 작업(스크래퍼 호출 + AI 호출 + DB 저장)이 시작된다. 운영자가 한 번에 수십~수백 매장을 트리거하기 때문에 작업은 **FastAPI BackgroundTasks 기반 비동기 실행**이 기본이다.

이 구조의 가장 큰 운영 리스크는 두 가지였다.

1. 잡 상태를 어디에 두느냐. RDBMS(`cron_jobs` 테이블)에 두면 정기 cron 잡은 영속화되지만, 짧고 일회성인 백오피스 잡까지 RDB에 쌓으면 운영 콘솔에서 "지난 1시간 내 잡" 같은 시계열 조회 시 인덱스 부담이 커진다.
2. ECS 재배포·OOM·인스턴스 교체로 프로세스가 죽으면, `BackgroundTasks`로 띄워둔 in-flight 잡은 흔적도 없이 사라진다. 운영자 입장에서는 "어드민에서 트리거했는데 RUNNING에서 멈춰 있다"는 좀비 잡만 남는다.

### 구현

#### 1) 잡 상태 저장소를 Redis로, 타입별 매니저는 제네릭 베이스로 통일

`task/services/job_manager.py`에 PEP 695 제네릭 문법을 활용한 `BaseJobManagerService[TJobInfo, TMetrics]`를 정의하고, `ReviewJobManagerService` / `OrderJobManagerService` / `GetShopJobManagerService` 3종이 상속하는 구조로 만들었다.

```
flow:{task_type}:job:{job_id}              # Hash: job 본문
flow:{task_type}:jobs:by_created            # ZSet: 생성순 인덱스
flow:{task_type}:jobs:by_status:{status}    # ZSet: 상태별 인덱스
```

(`task/services/job_manager.py:48-75`)

상태별로 TTL을 다르게 줘서, RUNNING=6h, COMPLETED=1h, FAILED=2h, CANCELLED=30m으로 분기했다(`TTL_BY_STATUS`, L61-75). 운영 콘솔이 노출하는 시계열 윈도우와 일치시켜서, "최근 6시간 진행 중 잡" 조회는 RUNNING ZSet 하나만 보면 끝난다.

#### 2) Pub/Sub로 실시간 진행률 브로드캐스트

잡이 phase(`INITIALIZING → FETCHING_REVIEWS → PROCESSING_REVIEWS → SAVING_REVIEWS → POST_PROCESSING → COMPLETED`)를 넘을 때마다, `BaseJobManagerService.publish_status`가 `flow:{task_type}:status` 채널로 Pub/Sub 메시지를 쏜다(`task/services/job_manager.py:337-355`). 어드민 WebSocket(`app/core/websocket.py`, `api/routers/ws.py`)이 이 채널을 구독해 운영자 화면에 1/n 진행도가 실시간으로 그려진다.

#### 3) 서버 재시작 시 orphaned 잡 자동 재시도

`app/main.py:30-67`의 lifespan에서 `JobRecoveryService.recover_all_jobs()`를 호출한다.

```python
# task/services/job_recovery.py:51-141
async def recover_all_jobs(self) -> dict[str, int]:
    # RUNNING/QUEUED ZSet에서 orphaned job_id 수집
    review_jobs = self.review_job_manager.get_orphaned_jobs()
    # 모든 Job을 QUEUED로 리셋
    for job in review_jobs:
        self.review_job_manager.reset_job_for_retry(job.job_id)
    # worker_count 제한 (기본 10)으로 병렬 재실행
    semaphore = asyncio.Semaphore(self.worker_count)
    ...
```

핵심 결정 3가지:

1. **재시도 가능/불가 분리**: GetShop 잡은 `platform_account_id`를 트리거 시점의 메모리에서만 들고 있어 재구성이 안전하지 않아, recovery 시 platform 정보가 있는 잡만 재시도하고 나머지는 명시적 `FAILED`로 떨어뜨려 운영자가 인지하게 했다(`job_recovery.py:106-133`, `_mark_getshop_failed`).
2. **CronJob 복구는 별도 경로**: RDB에 있는 `CronJob` 중 RUNNING 상태 잡은 Redis의 progress_tracker 키 유무로 판정 ─ Redis에 진행률이 남아 있으면 COMPLETED로 마킹하고 그 시점 카운터로 보정, 없으면 FAILED. 즉 **"진행률 데이터가 남아 있는 동안은 완료로 본다"** 는 가용 데이터 기반 결정(`task/services/scheduler/job_service.py:276-314`).
3. **Semaphore 워커 제한**: 평소 cron 1회에 매장 수백 개가 동시 실행되는 상황에서 재시작 직후 폭주를 막기 위해 `DEFAULT_WORKER_COUNT = 10`(`job_recovery.py:32`). cron의 전역 동시성 한도는 별도로 `MAX_GLOBAL_CONCURRENT_WORKERS = 200` Semaphore로 한 번 더 막는다(`task/services/scheduler/execution_service.py:23-32`).

### 아키텍처

```
[운영 어드민]
   │ POST /populate
   ▼
[PopulateService.execute_populate]  ──┐  shop_settings 일괄 조회 (N+1 방지)
   │ BackgroundTasks                  │  auto_reply_shop_ids 사전 계산
   ▼                                  │
[ReviewJobManager.create_job] ─────► Redis
   │                                  │   - Hash flow:review:job:{id}
   │                                  │   - ZSet by_created / by_status:QUEUED
   ▼
[_execute_populate_task] (async)
   │ status: QUEUED → RUNNING (ZSet 이동, expire 갱신)
   │ on_progress(phase, current, total) ──► Pub/Sub flow:review:status
   ▼
[PopulateTaskService.execute] (Phase 진행)
   │ INITIALIZING → FETCHING_REVIEWS → PROCESSING_REVIEWS
   │              → SAVING_REVIEWS → POST_PROCESSING → COMPLETED
   ▼
status: COMPLETED / FAILED / SCRAPER_TIMEOUT / AUTH_ERROR …
   └──► TTL 상태별 차등 (1h/2h/6h …)

[서버 재시작 (ECS deploy / OOM kill)]
   │
   ▼
[lifespan ↑]
   ├─ CronJob.recover_running_jobs()   ── RDB cron_jobs 중 RUNNING 정리
   ├─ JobRecoveryService.recover_all() ── Redis ZSet의 orphaned 자동 재실행
   └─ SchedulerService.start()          ── APScheduler 재시작
```

### 도전과 해결

- **도전 A. RDB가 정답인 잡(cron)과 Redis가 정답인 잡(ad-hoc 백오피스)을 한 시스템에서 다루기.**
  cron은 "지난주 새벽 3시 잡 결과"를 추적해야 하므로 영속화가 필요해 `task/models/cron_job.py`로 RDB에 두고, 운영 임시 잡은 짧은 수명·고RPS이므로 Redis Hash + ZSet으로 분리. 두 잡 모두 ‘진행률’이라는 공통 관심사가 있어 `CronJobProgressTracker`(`task/services/scheduler/progress_tracker.py`)도 Redis로 통일하고, RDB cron 잡의 RUNNING 중 진행률만 Redis에서 실시간 조회해 채워주는 read-through 패턴을 적용(`task/services/scheduler/job_service.py:340-388`). 그 결과 한 응답 모델(`CronJobResponse`)에 RDB 정합성과 실시간성을 모두 담아낼 수 있었다.

- **도전 B. orphan recovery 폭주 방지.**
  재배포 직후 RUNNING이 200개 남아 있던 상황이라고 가정하면, 한꺼번에 다 띄우면 외부 스크래퍼 API + AI MLOps에 burst가 그대로 전이된다. `asyncio.Semaphore(10)`으로 회복 동시성을 좁히고, 실제 cron 본실행은 별도 전역 Semaphore(`MAX_GLOBAL_CONCURRENT_WORKERS = 200`)로 한 번 더 차단. recovery는 의도적으로 정상 트래픽보다 보수적인 워커 수를 쓰는 격리 정책.

- **도전 C. 상태 인덱스 일관성.**
  상태 전이마다 ZSet 두 곳(`by_created`, `by_status:{old}`, `by_status:{new}`)을 갱신해야 하는데, 만료된 키가 인덱스에는 남아 좀비가 되는 케이스가 있었다. `list_jobs`에서 ZSet 조회 후 실제 Hash가 만료된 ID는 즉시 `_cleanup_expired_jobs`로 인덱스에서 빼는 self-healing 패턴을 넣어(`job_manager.py:225-292`), 인덱스가 점진적으로 정합화되도록 했다.

### 결과

- 서버 재배포·OOM kill로 사라지던 백오피스 잡이 **자동 재시도 경로**를 가지게 됨 (PR #26 `2207982`, "서버 재시작 시 orphaned job 자동 재시도").
- 운영자가 잡 상태를 실시간으로 받아볼 수 있는 WebSocket 채널 확립 (PR #6 `511d566` redis pub/sub 클래스 + `app/core/websocket.py`).
- TaskType 3종(REVIEW/ORDER/GET_SHOP) 공통 베이스를 PEP 695 제네릭으로 묶어, 신규 잡 타입 추가 시 4개 메서드(`create_job`, `_create_job_info`, `_hash_to_job`, `_job_to_hash`)만 구현하면 되는 확장 포인트 확립 (`job_manager.py:78-156`).
- 잡 metrics 모델(`ReviewJobMetrics` / `OrderJobMetrics` / `GetShopJobMetrics`)이 type-bound generic 파라미터로 묶여, 상태 업데이트(`update_job(status, progress, metrics)`) API가 타입 안전성을 잃지 않은 채 3종 잡을 다룬다. 즉 운영 콘솔 API는 단일 진입점이지만 내부적으로는 타입 시스템 수준에서 분리.

**사용 기술**: Python 3.12, FastAPI BackgroundTasks, Redis(Hash/ZSet/Pub-Sub, TTL 상태별 차등), asyncio.Semaphore, Pony ORM, APScheduler(AsyncIOScheduler), PEP 695 Generics, WebSocket.

#### 추가 인사이트 — 왜 RDB가 아니라 Redis인가

운영용 잡은 단명(수십초~수분)이고 시계열 조회(생성순/상태별)가 잦다. RDB로 가면:

- INSERT/UPDATE 빈도가 높은데 잡 메트릭(`items_processed`, `ai_requests` 등)이 진행 중 매 phase마다 UPDATE → 잠재적 락 경합.
- 시계열 조회(최근 N분 RUNNING) 인덱스가 잡 라이프사이클 종료 후에도 그대로 남아 누적.
- 백오피스 잡과 사용자 요청을 모두 받는 cmong-be의 DB와 분리하지 않으면 운영 트리거가 사용자 트래픽에 영향.

Redis Hash(잡 본문) + ZSet(상태별 인덱스)는 정확히 이 모양에 맞는다. 잡이 종료되면 TTL이 알아서 정리하고, 생성순/상태별 시계열은 ZRANGEBYSCORE로 O(log N) 조회. RDB는 cron 정기 잡처럼 영속화가 필요한 케이스에만 한정.

---

## 사례 2 ─ 리뷰 수집 파이프라인의 메모리 스파이크 잡기: 30개 배치 + AI 동시성 제어 + 명시적 GC

**구분**: 배치 / 메모리 / 비동기 동시성
**핵심 커밋**: `c58fa32` (2026-02-27 ai 생성 로직 변경), PR #27 `25c46d4` (2026-02-27 메모리 스파이크 로깅), PR #28 `f9252b3` (2026-03-03 AI 생성 로직 수정), `7b76710` (2026-03-03 메모리 스파이크 수정 1차).

### 배경

`PopulateTaskService.execute`는 한 매장당 수십~수백 건의 리뷰를 스크래퍼에서 받아 AI 답글을 생성하고, DB에 저장한 뒤 후처리(스코어링·자동답글)까지 한 번에 도는 긴 코루틴이다. 운영 중 메모리가 일정 매장에서 튀는 현상이 잡혔고, 동시에 도는 매장 수가 늘면 ECS 태스크가 OOM으로 죽는 사고가 누적되었다(`c58fa32` 직전 시점의 PR 메시지 "ai 생성 로직 변경" 그리고 `25c46d4` PR 제목 "메모리 스파이크 확인을 위한 로깅 추가").

### 구현

#### 1) 우선 관측부터 — 메모리 사용량 inline 로깅

PR #27에서 매 phase 전이·배치 commit·후처리 시작·완료 시점에 `_get_memory_mb()`를 찍어, 어느 구간에서 스파이크가 나는지 식별 가능하게 했다(`task/services/populate_task.py:39-44`):

```python
def _get_memory_mb() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    if platform.system() == "Darwin":
        return usage.ru_maxrss / (1024 * 1024)
    return usage.ru_maxrss / 1024
```

핵심 결정은 **외부 APM에 의존하지 않고 잡 내부 로그에 매장ID + job_id + 단계명 + 메모리를 함께 남긴 것**. CloudWatch / Datadog에서 잡별 단계별 메모리 곡선을 즉시 sort + group by 가능해진다.

#### 2) 전체 review를 메모리에 들고 있던 흐름을 30개 단위 배치로 분할

기존: 스크래퍼에서 받은 `reviews: list[dict]`(수백 건, 각 dict가 본문/메뉴/이미지 포함)을 한 번에 돌면서 AI 호출까지 마치고 commit. 즉 (리뷰 본문 N개) × (AI 응답 N개) × (Pony ORM 엔티티 캐시) 가 동시에 메모리에 떠 있었다.

수정 후(`populate_task.py:319-413`):

```python
REVIEW_BATCH_SIZE = 30
AI_CONCURRENT_PER_SHOP = REVIEW_BATCH_SIZE

for batch_start in range(0, total_reviews, REVIEW_BATCH_SIZE):
    batch_reviews = reviews[batch_start:batch_end]
    batch_context = ProcessingContext()

    # 배치 내 review_id의 기존 여부를 단일 db_session으로 일괄 체크
    existing_review_ids = self._check_existing_reviews_batch(review_ids)

    # 새 리뷰만 AI 생성 (병렬), 동시 호출은 Semaphore로 제한
    ai_semaphore = asyncio.Semaphore(AI_CONCURRENT_PER_SHOP)
    async def _process_with_limit(rd: dict):
        async with ai_semaphore:
            return await self._prepare_new_review_data(...)

    results = await asyncio.gather(*[_process_with_limit(rd) for rd in new_review_datas])

    # 배치 단위 단일 db_session으로 일괄 commit
    self._save_batch_reviews(new_reviews=..., existing_replies=..., shop_context=shop_info)

    # 배치 종료 후 명시적 해제 + GC
    del batch_reviews
    del batch_context
    del new_reviews_to_save
    del existing_replies_to_save
    gc.collect()
```

배치당 동시 AI 호출 한도를 `REVIEW_BATCH_SIZE` (30)와 같게 묶어, **AI 응답 풀의 동시 in-flight 개수가 절대 30을 넘지 않게** 했다. AI 호출은 httpx 비동기로 60s 타임아웃 ─ 이게 같은 매장에서 200개 동시에 떠 있으면 응답 dict 200개가 동시에 힙에 상주한다. Semaphore로 슬롯 30개로 묶고, 매 배치가 끝나면 `del` + `gc.collect()`로 generation 0/1을 강제로 비웠다.

#### 3) post-processing 페이즈는 review_id만 들고 가도록 분리

PR #27에서 도입된 패턴(`_run_post_processing_by_ids`): 배치 처리 중에는 `ProcessingContext.new_reviews`(`NewReviewInfo`만 담는 가벼운 dataclass: `review_id`, `content`, `rating`, `is_auto_reply_target`)에만 정보를 모으고, 후처리에 들어가서는 `_get_review_content(review_id)`로 그때그때 DB에서 다시 읽어 스코어링한다(`populate_task.py:433-472`).

즉 **스크래퍼 응답 dict 그래프(이미지 base64, 메뉴 옵션, raw response)는 배치 commit이 끝나는 즉시 메모리에서 사라지게** 만들었고, 후처리는 가벼운 PK + 필요한 컬럼만으로 진행한다.

#### 4) AI 답글 생성 로직 ─ 3슬롯 고정으로 메모리 모양 단순화

PR #28 `f9252b3`의 변경(`task/services/populate_task.py:622-664`):

- 이전: 플랫폼별로 `template_count` 1/2 → AI 생성 개수 1/2 → reply1/2/3 슬롯에 동적으로 끼워 넣기.
- 이후: **항상 3개의 템플릿 슬롯(`TOTAL_REPLY_SLOTS=3`)을 가져온 뒤, AI 생성 결과가 있는 인덱스(1, 2)만 in-place 교체.**

```python
potential_replies = list(template_replies)  # 항상 3개

if ai_reply_contents:
    if len(ai_reply_contents) >= 1:
        potential_replies[1] = AiReplyData(...)  # reply2 위치
    if len(ai_reply_contents) >= 2:
        potential_replies[2] = AiReplyData(...)  # reply3 위치 (NAVER 등)
```

이 변경의 본질은 **"AI 응답 개수에 따라 자료구조 모양이 달라지는 분기"** 를 없애, 메모리 점유 패턴(슬롯 3개 고정)을 평탄화한 것. 운영 시점에 "왜 어떤 매장은 reply3가 None이지" 같은 데이터 일관성 이슈도 동시에 잡았다 — 템플릿이 항상 폴백으로 깔리니까.

### 아키텍처

```
[리뷰 수집 한 매장 코루틴]
  │
  ├─ FETCHING_REVIEWS  ─► 스크래퍼 1회 호출, list[dict] (수십~수백건)
  │
  ▼ batch loop (30씩)
  ┌──────────────────────────────────────────────────────────┐
  │ batch_reviews[0..30]                                      │
  │   ├─ _check_existing_reviews_batch  (단일 db_session)     │
  │   ├─ asyncio.Semaphore(30)                                 │
  │   │    └─ _prepare_new_review_data × N (AI 호출, httpx)    │
  │   ├─ _save_batch_reviews  (단일 db_session, bulk insert)  │
  │   └─ del batch_*; gc.collect()                            │
  └──────────────────────────────────────────────────────────┘
  │
  ├─ POST_PROCESSING  ─► review_id 기반으로 content 재조회 → 스코어링
  │
  └─ AUTO_REPLY       ─► is_auto_reply_target만 추려 BE API 호출
```

### 도전과 해결

- **도전 A. Pony ORM의 `@db_session` 경계가 과도하게 잘리는 문제.**
  초기 구현은 매 리뷰마다 `@db_session`이 붙은 헬퍼(`_check_existing_review`, `_save_new_review`)를 호출했다. session 컨텍스트가 N번 열리고 닫히면서 작업 시간이 길어지고, identity map이 매번 재구축되어 메모리 패턴이 톱니파 모양으로 튀었다. 해결: **배치 단위 단일 `@db_session`** (`_save_batch_reviews`, `_check_existing_reviews_batch`)으로 묶어 한 번에 commit. 동시에 `disable_optimistic_lock` 데코레이터를 `Review`/`Reply` 엔티티에 적용해 UPDATE 시 PK 외 WHERE 절을 빼서 락 경합을 줄였다(`task/models/database.py:9-15`, `task/models/review.py:8`).

- **도전 B. AI 답글 생성이 매장 전체 작업 시간의 80%를 차지.**
  AI MLOps API는 httpx 동기 시간 60s. 직렬로 돌면 100건 매장이 1시간 넘는다. `asyncio.gather`로 병렬화하되, **매장당 동시성**(Semaphore 30) + **전역 cron 동시성**(MAX_GLOBAL=200) 두 단계로 격리. 또한 답글 생성 기간 컷오프(`get_ai_reply_period`: CPEATS 14일/기타 30일)와 작성 가능 여부(`writable`) 필터로 **불필요한 AI 호출을 호출 전에 컷**(`populate_task.py:577-585`).

- **도전 C. AI 실패 메시지가 정상 답글로 오인되는 정합성 문제.**
  `AIClient.create_completion`은 실패 시 `"[MLOPS] Generate Error: ..."` 문자열을 그대로 반환한다(`task/clients/ai_client.py:147-156`). PopulateTaskService 쪽에서 `generated_content.startswith("[MLOPS]")` 가드로 카운트만 실패로 올리고 본문은 None 처리해 폴백 템플릿으로 자연 전환(`populate_task.py:911-919`).

### 결과

- 메모리 스파이크 관측 → 원인 식별(스크래퍼 응답 dict 통째 보유 + AI 응답 동시 다발) → 30개 배치 + Semaphore 30 + 명시적 GC + 단일 db_session 패턴으로 메모리 곡선을 **톱니가 아닌 계단형**으로 정리.
- AI 호출 실패율을 metrics에 명시적으로 분리해 잡아냄: `num_total_ai_requests` / `num_successful_ai_requests` / `num_failed_ai_requests` (`api/schemas/populate.py`의 `ReviewJobMetrics`).
- 답글 슬롯 자료구조를 3슬롯 고정으로 평탄화해, 운영 시점의 데이터 일관성 + 메모리 모양 두 마리를 같이 잡음 (PR #28).

**사용 기술**: Python `resource.getrusage`, asyncio.Semaphore(매장 내부 + 전역 cron 2단), Pony ORM `@db_session` 배치 묶기 + optimistic lock disable, `gc.collect()`, httpx AsyncClient, MLOps REST 클라이언트, dataclass 기반 가벼운 후처리 컨텍스트.

#### 추가 인사이트 — 명시적 `gc.collect()` 호출이 왜 정당화되는가

Python에서 `gc.collect()`를 명시적으로 부르는 건 코드 스멜로 취급되는 경우가 많다. 이 코드베이스에서 정당화되는 이유:

1. 배치 한 번이 끝나는 시점은 **명시적으로 큰 메모리 그래프(스크래퍼 응답 dict 30개 + AI 응답 30개 + Pony identity map)가 통째로 폐기되는 지점** 이다. 이 시점에 gen0/gen1 회수를 강제하지 않으면, 다음 배치의 AI 응답이 도착할 때까지 generation 승격이 늦어져 RSS 피크가 누적된다.
2. Pony ORM은 `@db_session` 종료 시 identity map을 비우지만, 거기 박혀 있던 엔티티가 `batch_context.new_reviews`(`NewReviewInfo` dataclass) 같은 다른 자료구조에 약하게 참조되면 그대로 살아남는다. `del`로 명시적 unbind + `gc.collect()` 조합이 안전.
3. 매장 1개 처리 시간(분 단위)에 비해 `gc.collect()` 자체의 비용(수~수십 ms)은 무시 가능한 수준 — 한 매장 안에서만 부르고, 매 리뷰마다 부르지 않음.

이 결정은 측정(`_get_memory_mb()` 로깅)을 먼저 했기 때문에 정당화될 수 있다. 측정 없이 GC를 부르는 건 미신이지만, 메모리 곡선이 톱니파에서 평탄해지는 걸 본 뒤에 부르는 건 데이터 기반 결정.

---

## 사례 3 ─ 자동 답글(AI generated reply 게시) 기능: 멀티소스 정책 결정 + DB 트랜잭션 외 IO 분리

**구분**: AI 파이프라인 / 외부 API 통합 / 트랜잭션 경계 설계
**핵심 커밋**: PR #39 `b03352b` (2026-03-13 자동댓글 기능 추가), 그 중 코어 `67d9f1a` (2026-03-13 feat: 자동댓글 기능 추가).

### 배경

댓글몽의 메인 가치 제안 중 하나가 "사장님이 안 달아도 AI가 자동으로 답글 단다". 이전까지 flow-be는 AI 답글을 **생성·저장만** 했고, 실제 매장 플랫폼에 게시하는 건 사장님이 댓글몽 앱에서 누르거나, cmong-mq가 또 다른 경로로 했다.

PR #39는 flow-be의 운영성 트리거(어드민에서 "이 매장 자동답글 켠 채로 다시 돌려"를 누르는 경우)에서도 **수집 → AI 생성 → 게시까지 한 잡 안에서 끝내는** 종단 흐름을 만들었다.

자동 답글이 위험한 이유:

- **잘못 달면 매장 평판 직격**. 별점 1점 리뷰에 "맛있게 드셔서 감사해요" 같은 답글이 자동으로 달리면 사고.
- **중복 게시 방지**. 한 리뷰에 두 번 게시되면 플랫폼 API 호출량 낭비 + 사장님 신뢰도 하락.
- **홍보문구 합성**. 사장님이 등록한 매장별 "쿠폰 받으세요" 같은 홍보 텍스트를 AI 답글의 위/아래에 붙여야 한다.
- **별점 컷오프**. 매장마다 "별점 5점만 자동 답글", "4점 이상만" 식의 정책 다름.

### 구현

#### 1) 자동 답글 정책 결정 트리

`api/services/populate.py:50-99`, `task/services/populate_task.py:_get_shop_info`, `task/services/shop_filter_service.py:get_auto_reply_shops`:

```
auto_reply 파라미터 (요청 시점)
  ├─ True  → 전체 매장 강제 자동 답글
  ├─ False → 전체 매장 자동 답글 비활성화
  └─ None  → 요금제 기반: SPECIAL 플랜 + is_auto_reply != DISABLED 매장만
```

매장 단위 별점 컷오프는 `shop.auto_reply_rating`(매장 테이블)에서 가져와 (`populate_task.py:198`) 리뷰별로 `rating >= auto_reply_rating` 일 때만 타겟에 포함시킨다(`populate_task.py:379-388`).

#### 2) "이미 답글이 있는지"는 한 번 더 게시 직전에 검증 (TOCTOU 방지)

`_collect_auto_reply_payload`(`populate_task.py:1099-1151`):

```python
@db_session
def _collect_auto_reply_payload(self, review_id, shop_context):
    review = Review.get(review_id=review_id)
    if review.is_replied:
        return None
    existing_replies = Reply.select(lambda r: r.review.review_id == review_id).count()
    if existing_replies > 0:
        return None
    if not self._is_within_ai_reply_period(review.created_at, shop_context.platform_enum):
        return None
    if not review.reply2_id:
        return None
    ai_reply = AiReply.get(ai_reply_id=review.reply2_id)
    if not ai_reply or not ai_reply.content:
        return None
    ...
```

즉 **타겟에 포함되어도 게시 직전 게이트 4단**: ① review.is_replied 플래그, ② replies 카운트, ③ AI 답글 기간 컷오프(CPEATS 14일/기타 30일), ④ AI 생성 본문 존재 여부. 이 중 하나라도 실패하면 조용히 skip.

#### 3) AI 답글 + 홍보문구 합성: 순수 함수로 분리해서 테스트 가능하게

`_assemble_reply_comment` (`populate_task.py:1153-1170`):

```python
@staticmethod
def _assemble_reply_comment(payload: AutoReplyPayload) -> str:
    comment = payload.ai_reply_content
    if payload.custom_reply_text:
        if payload.custom_reply_position == "bottom":
            comment = comment + "\n" + payload.custom_reply_text
        else:
            comment = payload.custom_reply_text + "\n" + comment
    # 템플릿 변수 치환
    comment = comment.replace("(매장명)", payload.shop_name)
    comment = comment.replace("(닉네임)", payload.reviewer)
    return comment
```

이 함수가 staticmethod인 게 중요하다. `_collect_auto_reply_payload`는 `@db_session`이 붙어 트랜잭션 안에서 DB 데이터를 dataclass(`AutoReplyPayload`)로 추출하고, 합성과 외부 호출은 **DB 세션 밖**에서 수행한다. 즉 외부 API 호출이 길어져도 DB 커넥션이 그만큼 점유되지 않는다. PR #39의 테스트(`tests/task/services/test_populate_task.py:580-652`)도 이 함수만 단독으로 6가지 케이스(AI만/top/bottom/매장명 치환/닉네임 치환/홍보문구에도 치환) 검증.

#### 4) 게시 호출: BE API 우회

```python
result = await be_client.post_reply(
    user_id=shop_context.user_id,
    shop_id=shop_context.shop_id,
    review_id=review_info.review_id,
    comment=comment,
    platform=shop_context.platform_enum.value,
    is_auto_reply=True,
)
```

`task/clients/be_client.py:115-142`. `is_auto_reply=True` 플래그가 BE에 명시 ─ BE 쪽 알림톡·통계가 자동/수동을 구분해 다른 흐름을 탈 수 있게.

`BeClient`는 **API Key 우선 → 401/403이면 JWT fallback** 의 이중 인증(`_request_with_fallback`, `task/clients/be_client.py:69-110`). 운영 환경에서 API Key가 회전되거나 누락되었을 때 JWT 로그인(`be_auth_email`/`be_auth_password`)으로 폴백해 자동 답글 잡 전체가 죽지 않도록 안전장치.

#### 5) 후처리 실행 순서를 명시적으로 고정

`_run_post_processing_by_ids`(`populate_task.py:433-466`):

```
1. 리뷰 스코어링 (AI Score API 호출)
2. 알림톡 전송 (TODO)  ← cmong-be 측 책임 영역
3. 자동 답글 실행      ← 알림톡 이후에 게시되도록 순서 고정
```

순서 결정의 본질: 불만족 리뷰(낮은 스코어/낮은 별점)는 자동 답글 대상이 아니어야 하고, 사장님이 알림을 받아 직접 대응할 수 있도록 알림톡이 먼저 가야 한다. 자동 답글은 가장 마지막 단계.

추가로 `is_replied=False` 인 기존 리뷰 중 별점 컷오프 통과 건도 별도 리스트(`all_existing_auto_reply_targets`, `populate_task.py:317-355, 423-427`)로 모아 한 번 더 자동 답글 시도 → 누락 보상.

### 아키텍처

```
[운영자: auto_reply=true로 populate 트리거]
        │
        ▼
[execute_populate] ── shop_settings batch + auto_reply 매장 사전 계산
        │
        ▼
[_execute_populate_task] (한 매장 1 코루틴)
        │
        ▼
[PopulateTaskService.execute]
   FETCHING_REVIEWS → 30개 배치로 PROCESSING → SAVING (Review, AiReply, Reply commit)
                                                  │
                                  reply2_id 에 AI 답글이 박힘
                                                  │
                                                  ▼
                               POST_PROCESSING
                                  1) review score (AI Score API)
                                  2) 알림톡 (TODO; cmong-be 영역)
                                  3) _execute_auto_replies
                                        │
                                        ▼
                                 for each target:
                                   ├─ _collect_auto_reply_payload (@db_session)
                                   │     · is_replied? · 기존 replies?
                                   │     · 기간 컷오프? · reply2 content?
                                   │     · shop_name · reviewer · custom_reply
                                   ├─ _assemble_reply_comment (pure)
                                   │     · 홍보문구 top/bottom · (매장명)(닉네임) 치환
                                   └─ BeClient.post_reply (API key → JWT fallback)
                                        │
                                        └─► cmong-be → 플랫폼 API
```

### 도전과 해결

- **도전 A. DB 세션 안에서 외부 API를 호출하면 안 됨.**
  Pony의 `@db_session`은 with 진입 시 커넥션을 잡고 나갈 때 commit/rollback한다. 이 안에서 60초 타임아웃 가능한 BE API를 그대로 호출하면 커넥션 풀이 빠르게 고갈된다. 해결: **payload 수집은 `@db_session`, 합성은 staticmethod, 게시는 async** 의 3단 분리. `_execute_auto_replies` 자체는 `@db_session`이 없고, 안에서 `_collect_auto_reply_payload`(짧은 트랜잭션)와 `be_client.post_reply`(긴 IO)를 명확히 갈라 호출.

- **도전 B. AI 생성 실패와 게시 실패의 metrics 분리.**
  `num_total_ai_requests` / `num_successful_ai_requests` / `num_failed_ai_requests` 는 AI MLOps 호출 성공률만 본다. 별도로 `num_total_auto_replies` 카운터(`populate_task.py:141, 1211`)는 **실제 BE API 게시 성공 건수**만 집계해, 운영자가 "AI는 잘 만들었는데 게시가 안 됐다" / "AI 자체가 실패했다"를 구분할 수 있게 함.

- **도전 C. 자동답글 OFF인데 잡이 도는 경우의 가드.**
  PR #39 초기 버전(`67d9f1a`)은 인스턴스 변수 `disable_auto_reply` 로 명시 차단했지만, 최종 머지에는 단순화되어 `self.auto_reply` 플래그가 False면 즉시 return(`populate_task.py:1178-1179`). 외부 호출자가 잘못 깨워도 안전.

### 결과

- 어드민에서 한 번의 트리거로 **수집 → AI 생성 → 게시까지 종단 자동화**가 가능해짐.
- 게시 직전 4단 가드(TOCTOU 방어)로 중복/오답글 위험 차단.
- 합성 로직을 staticmethod로 빼내 6가지 케이스(`test_populate_task.py:580-652`)를 단위 테스트로 잠금.
- BE API 호출 시 API Key → JWT fallback의 이중 인증으로 키 회전·만료 시에도 잡 전체가 죽지 않는 가용성 확보.

**사용 기술**: httpx AsyncClient, Pony ORM `@db_session` 트랜잭션 경계 분리, dataclass(`AutoReplyPayload`)로 DB-외부IO 경계 횡단, BE API 이중 인증(API Key + JWT), 별점 컷오프 정책, 플랫폼별 답글 기간 컷오프(`PLATFORM_AI_REPLY_PERIODS`).

#### 추가 인사이트 — 자동 답글의 idempotency 책임 분담

자동 답글이 두 번 게시되면 안 된다. 이 멱등성을 어디서 보장할 것인가는 분산 시스템에서 자주 나오는 결정 포인트.

flow-be의 답:

- **flow-be 측 책임**: 게시 전 4단 게이트(`is_replied` / `Reply.count() > 0` / 기간 컷 / `reply2_id` 존재)로 **flow-be가 트리거한 동일 잡 안에서 두 번 호출되는 케이스**를 차단. 이건 잡 자체의 결함 방어.
- **BE 측 책임**: BE API의 `is_auto_reply=True` 플래그를 받아, BE 측에서 외부 플랫폼에 실제 전송하는 단계의 멱등성(같은 review_id로 두 번 reply 등록되지 않게)을 보장해야 한다. 즉 **flow-be는 BE를 신뢰하고 BE는 플랫폼 응답으로 자기 멱등을 보장** 하는 layered idempotency.

이런 분담을 한 시스템(예: flow-be)이 다 떠안으면, flow-be가 BE API 응답 본문까지 파싱해 reply_id 중복 여부를 다시 검사하는 식의 leakage가 생긴다. 경계 명확화의 가치는 운영 관점에서 "어디서 책임이 깨지면 어디서 알 수 있는가"가 분명한 것.

#### 코드 패턴 — payload 수집과 게시의 명확한 경계

```python
# 트랜잭션 안에서 dataclass로 데이터 뽑기 (짧음)
@db_session
def _collect_auto_reply_payload(self, review_id, shop_context) -> AutoReplyPayload | None:
    ...

# 트랜잭션 밖에서 합성 (순수 함수, 테스트 용이)
@staticmethod
def _assemble_reply_comment(payload: AutoReplyPayload) -> str:
    ...

# 트랜잭션 밖에서 외부 IO (길음, 60s 타임아웃 가능)
async def _execute_auto_replies(self, ...):
    for review_info in auto_reply_reviews:
        payload = self._collect_auto_reply_payload(review_info.review_id, shop_context)
        if payload is None: continue
        comment = self._assemble_reply_comment(payload)
        result = await be_client.post_reply(...)
```

이 패턴은 Java/Spring 환경의 `@Transactional` 분리 패턴과 본질적으로 같다 — read-only `@Transactional`로 DTO 추출 → 외부 호출은 트랜잭션 밖 → 결과 반영은 짧은 write `@Transactional`. Pony ORM의 db_session도 같은 의도로 다뤘다.

---

## 사례 4 ─ 정기 크롤 스케줄러: 24시간 선생성 + Config당 1잡 동시성 + Redis 실시간 진행률

**구분**: 스케줄러 / 분산 잡 큐 / Redis 캐시
**핵심 커밋**: `9b0d85c` (2026-02-12 cron job 1차 작성), `8be9693` (Implement Cron Job scheduling), 후속 fix들 ─ `45f1381` (2026-03-12 "job 리스트에 get shop job도 추가"), `f64c360` (2026-03-12 "last_crawled_at이 null인 경우는 제외"), `486b384` (2026-03-10 Merge branch 'add-cron').

### 배경

`flow-be`는 사용자에게 노출되는 API 외에 **활성 매장 전체를 주기적으로 긁어오는 cron** 역할도 한다. 평균 매장 수천 개, 플랫폼 5종(BAEMIN/YOGIYO/CPEATS/DDANGYO/NAVER), 매장마다 1~24시간 간격으로 다른 주기.

요구 사항:

1. 운영자가 어드민에서 cron 설정(`CronJobConfig`: name, task_type, platform, interval_hours, is_active)을 켜고 끄면 즉시 반영.
2. 한 cron이 매장 1000개를 도는 동안 같은 cron의 다음 트리거가 와도 절대 동시에 돌면 안 됨(중복 처리 방지).
3. 매장 단위로 마지막 크롤 시각(`last_crawled_at`)을 추적해, 직전에 이미 긁힌 매장은 skip.
4. 어드민에서 cron 진행률을 실시간으로 본다(잡 시작/중간/완료).

### 구현

#### 1) "24시간 내 예정 잡을 미리 생성" 패턴

APScheduler가 `_generate_scheduled_jobs`(`task/services/scheduler/scheduler_service.py:80-87`, `task/services/scheduler/job_service.py:198-260`)를 매 시간 정각에 호출한다.

```python
@staticmethod
@db_session
def generate_scheduled_jobs(hours_ahead: int = 24) -> int:
    active_configs = CronJobConfig.select_by_sql(
        "SELECT * FROM cron_job_configs WHERE is_active = 1"
    )
    for config in active_configs:
        # 마지막 Job의 scheduled_at 기준으로 다음 시간 계산
        latest_job = ...
        next_time = (latest_job.scheduled_at if latest_job else now.replace(minute=0)) \
                    + timedelta(hours=config.interval_hours)
        while next_time <= now + 24h:
            # ±5분 윈도우 안에 이미 같은 config의 잡이 있으면 skip (멱등)
            if not exists(... time_min <= scheduled_at <= time_max):
                CronJob(... status=SCHEDULED, scheduled_at=next_time)
            next_time += timedelta(hours=config.interval_hours)
```

이 패턴의 본질은 **"실행 시점 1초 전에 잡을 만들지 않고, 24시간 치를 미리 RDB에 박아둔다"**. 그래서:

- 운영자가 어드민에서 향후 잡 목록을 한 번에 본다.
- APScheduler가 죽어도 다음 부팅 시 RDB의 SCHEDULED 잡을 그대로 이어받는다(상태가 인메모리에 없음).
- 같은 config의 잡이 중복 생성되는 걸 ±5분 윈도우 exists 체크로 막는다.

#### 2) "Config당 RUNNING 1개" 동시성 제어

매 1분마다 `_execute_due_jobs`(`task/services/scheduler/execution_service.py:50-105`):

```python
with db_session:
    due_jobs = CronJob.select(j.status == SCHEDULED and j.scheduled_at <= now)[:]
    for job in due_jobs:
        config_id = job.config.config_id if job.config else None
        if config_id:
            running_exists = CronJob.exists(lambda j:
                j.config.config_id == config_id
                and j.status == RUNNING
                and j.deleted_at is None
            )
            if running_exists:
                # 이전 잡이 아직 도는 중이면 이 잡은 CANCELLED
                job.status = CANCELLED
                job.error_message = "이전 Job이 아직 실행 중이어서 취소됨"
                continue
        jobs_to_execute.append(job.job_id)

# db_session 닫고 나서 비동기 작업 생성
for job_id in jobs_to_execute:
    asyncio.create_task(self._execute_job(job_id))
```

핵심 결정 3가지:

1. **DB 세션 안에서 due 잡을 SCHEDULED로 잠그고 RUNNING 중복을 검사하고, 세션을 닫은 다음에 `asyncio.create_task`** ─ Pony의 db_session 안에서 await를 하면 트랜잭션이 너무 길게 잡혀 같은 테이블 다른 트랜잭션을 막는다.
2. **CANCELLED는 사일런트 스킵이 아니라 error_message에 사유 명시** ─ 운영자가 어드민에서 "이 잡 왜 안 돌았어요?"를 사유로 답한다.
3. **전역 동시성 한도**: 모든 플랫폼 cron이 합쳐서 200개를 넘으면 추가 매장은 Semaphore에서 대기(`MAX_GLOBAL_CONCURRENT_WORKERS = 200`, `execution_service.py:23-32`). MLOps + 스크래퍼 API 백엔드 보호.

#### 3) Redis 실시간 진행률 + DB read-through

`CronJobProgressTracker`(`task/services/scheduler/progress_tracker.py`):

```python
REDIS_KEY_PREFIX = "cronjob:progress"
REDIS_CHANNEL_PREFIX = "cronjob:progress:stream"
REDIS_TTL = 60 * 60 * 24  # 24시간

def init_progress(self, job_id, target_shops_count):
    self.redis.set(key, json.dumps(data), ex=REDIS_TTL)
    self._publish_progress(job_id, data, event_type="started")

def increment_progress(self, job_id, success=True):
    # GET → JSON 디코드 → 카운트 ++ → SET
    # 매 매장 완료마다 Pub/Sub stream 발행
    self._publish_progress(job_id, data, event_type="progress")
```

`JobService._to_response_with_redis`(`task/services/scheduler/job_service.py:340-388`)는 RDB의 cron_job 응답을 만들 때 **status=RUNNING이면 Redis에서 실시간 카운터를 덮어쓴다**:

```python
if job.status == RUNNING and self.progress_tracker:
    redis_progress = self.progress_tracker.get_progress(job.job_id)
    if redis_progress:
        target_shops_count = redis_progress.get("target_shops_count", ...)
        executed_shops_count = redis_progress.get("executed_shops_count", ...)
        ...
```

잡이 끝나면 `finalize(job_id)`가 Redis 진행률을 RDB에 sync하고 Redis 키를 삭제(`progress_tracker.py:113-121`). **읽기 부하는 RDB로 흡수하되, RUNNING 상태의 톡톡 튀는 카운트만 Redis에서 가져오는 read-through 패턴.**

#### 4) `last_crawled_at` 기반 매장 스킵 + null 버그 픽스

`ShopFilterService._exclude_cron_shop_ids`(`task/services/shop_filter_service.py:377-402`):

```python
records = select((s.platform_shop_id, s.crawling_time, s.last_crawled_at)
                 for s in Shop if s.platform_shop_id in platform_shop_ids)[:]

skip_map = {sid: (ct if ct is not None else DEFAULT_SKIP_HOUR=3)
            for sid, ct, _ in records}
last_crawled_map = {sid: lc for sid, _, lc in records}

result = [sid for sid in platform_shop_ids
          if last_crawled_map.get(sid) is None
          or last_crawled_map[sid] < now - timedelta(hours=skip_map[sid])]
```

매장별로 `crawling_time` 컬럼(시간 간격)을 두고, 마지막 크롤 후 그 시간이 안 지났으면 이번 cron 사이클에서 skip. 매장이 신규 추가되어 `last_crawled_at`이 NULL이면 처음 한 번은 무조건 포함시키는 게 의도였다 ─ 정작 운영 대시보드(`api/services/dashboard.py:101-103`)에서는 **`last_crawled_at IS NOT NULL`** 로 명시 필터링하는 게 정답이라, PR #36 `f64c360`에서 stale shops 조회의 null 버그를 잡았다("fix: last_crawled_at이 null인 경우는 제외함").

#### 5) GetShop 잡도 cron 흐름에 추가 (PR #37)

`45f1381` "fix: job 리스트에 get shop job도 추가되게 수정" — 매장 자체를 BE에서 다시 끌어오는 GetShop 잡이 list_jobs 응답에 빠져 있던 버그를 운영 시점에 발견하고 보강(`api/services/populate.py:220-256`).

### 아키텍처

```
APScheduler (KST, AsyncIOScheduler)
   │
   ├─ every hour at :00  ─► generate_scheduled_jobs(24h ahead)
   │                          ├─ active CronJobConfig 조회
   │                          ├─ next_time 계산 (latest + interval_hours)
   │                          └─ ±5분 윈도우 dedupe 후 SCHEDULED 잡 RDB insert
   │
   ├─ every minute       ─► execute_due_jobs
   │                          ├─ SCHEDULED && scheduled_at <= now
   │                          ├─ Config당 RUNNING 1개 보장 (없으면 RUNNING으로 전환)
   │                          └─ asyncio.create_task(_execute_job)
   │
   └─ every day 00:00    ─► cleanup_old_jobs(30d)

_execute_job(job_id)
   ├─ _prepare_job_execution     (@db_session, primitive만 추출 후 세션 닫음)
   ├─ ShopFilterService.filter_platform_shops  (plans / platform / use_cron / last_crawled)
   ├─ progress_tracker.init_progress (Redis SET + Pub/Sub started)
   ├─ for each shop:
   │     async with global_semaphore(200):
   │         _execute_populate_task(populate_job_id, shop_id, request, auto_reply)
   │         progress_tracker.increment_progress (Redis SET + Pub/Sub progress)
   ├─ _aggregate_metrics  (개별 populate job metrics 합산)
   └─ progress_tracker.finalize → DB sync → DELETE Redis key
```

### 도전과 해결

- **도전 A. APScheduler 1회 실행이 OOM으로 죽는 경우.**
  매 1분 `execute_due_jobs`가 due 잡을 한 번에 200개 트리거하고, 각 잡이 다시 매장 100개를 도는 중첩 구조. 한 잡당 5MB만 잡아도 200 × 100 × 5MB = 100GB 단순 곱셈. 해결: `_execute_due_jobs`는 잡 생성만 하고 **즉시 db_session을 닫고 `asyncio.create_task`로 비동기 실행 분리**(`execution_service.py:55-100`). + `MAX_GLOBAL_CONCURRENT_WORKERS=200`으로 같은 시점 in-flight 매장 코루틴을 차단.

- **도전 B. RUNNING 상태로 서버가 죽으면 RDB만 보면 영원히 RUNNING.**
  사례 1과 동일 문제의 cron 버전. `JobService.recover_running_jobs`(`task/services/scheduler/job_service.py:276-314`)가 lifespan 부팅 시 호출되어, Redis에 진행률 데이터가 남아 있는 cron은 그 카운터로 보정 + COMPLETED 마킹("서버 재시작으로 인해 완료 처리됨"), Redis에도 데이터가 없으면 FAILED 처리. **Redis 잔존 데이터를 신뢰 근거로 사용하는 운영 가능성 우선 정책.**

- **도전 C. 운영 환경 timezone 일관성.**
  AsyncIOScheduler는 KST로 띄우되(`scheduler_service.py:13`), `datetime.now()`는 server timezone(UTC) 기준 ─ 두 시간대가 한 코드베이스에서 섞이지 않게 cron 모델은 모두 timezone-naive(`job_service.py:127`)로 두고, "서버가 UTC 기준" 이라는 인바리언트를 주석으로 명시. 잡 모델에는 KST를 저장하지 않음.

### 결과

- 24시간 선생성 + ±5분 dedupe → cron 잡 중복 0건, 운영 가시성(어드민에서 다음 24시간 잡 미리 볼 수 있음) 확보.
- Config당 RUNNING 1개 보장 → 같은 cron 두 번 동시 도는 사고 차단, CANCELLED는 사유 남겨 운영 관찰성.
- Redis read-through 진행률 → 매장 1000개 도는 cron이 도는 중에도 어드민 화면이 1초 단위로 톡톡 올라감.
- `last_crawled_at` 기반 매장 스킵으로 외부 스크래퍼/MLOps 호출량 자체를 사이클당 수십%대 절감(매장별 `crawling_time` 컬럼이 정책 노브).

**사용 기술**: APScheduler(AsyncIOScheduler, KST timezone), Pony ORM(`select_by_sql` raw query for cron config polling), Redis(SET + EX TTL 24h, Pub/Sub channel per job_id), `asyncio.Semaphore` 전역 200, db_session 짧게 끊기 + asyncio.create_task로 트랜잭션 외부 IO 분리.

#### 추가 인사이트 — 24시간 선생성의 본질

흔히 cron은 "지금 시각 == 트리거 시각이면 실행"으로 짠다. 이 코드베이스는 한 단계 떨어트려 **"향후 24시간 치 잡을 RDB에 미리 박아두는 책임"** 과 **"매 분 due 잡을 picking 해서 실행하는 책임"** 을 분리한다. 효용:

1. **운영 가시성**: 어드민에서 "다음 12시간 동안 어떤 잡이 어떤 시각에 도는가"를 SELECT 한 방으로 보여줄 수 있다.
2. **APScheduler 죽음에 대한 내성**: 인메모리 스케줄러가 죽거나 재시작되어도, RDB에 SCHEDULED로 박힌 잡은 그대로 다음 부팅 시 이어받는다. 즉 **스케줄러 상태가 외부화** 되어 있다.
3. **운영자 개입의 진입점**: 어드민에서 특정 시각 잡을 미리 cancel/run-now로 만질 수 있다(`JobService.run_now`, `JobService.cancel`). 인메모리 cron은 이런 개입 진입점을 만들기 어렵다.
4. **dedupe의 정확성**: ±5분 윈도우 exists 체크로 중복 생성을 막아, 같은 config의 같은 시각 잡이 두 번 박히는 사고를 사전 차단.

이 패턴은 Spring Batch의 `JobRepository` + `JobLauncher`/`JobExecution` 구조의 본질과 같다. 즉 **스케줄러 자체가 어떤 잡을 언제 실행할지의 결정을 영속화** 하고, 실행 엔진은 그걸 picking 해서 도는 역할만 한다.

#### 코드 패턴 — db_session 안에서 await 금지

```python
# BAD (실제 코드 X, 안티 패턴 예시)
@db_session
async def execute_due_jobs(self):
    due_jobs = CronJob.select(...).[:]
    for job in due_jobs:
        await self._execute_job(job)   # ← db_session 안에서 await
```

위 코드는 트랜잭션이 await 동안 열려 있어, 같은 테이블의 다른 트랜잭션을 막는다. flow-be는 **db_session을 명시적으로 닫고 나서 asyncio.create_task** 를 부른다 (`execution_service.py:55-100`):

```python
# GOOD
jobs_to_execute: list[str] = []
with db_session:
    due_jobs = CronJob.select(...)[:]
    for job in due_jobs:
        # 동기 작업만, await 없음
        if running_exists: ...
        jobs_to_execute.append(job.job_id)
# db_session 종료
for job_id in jobs_to_execute:
    asyncio.create_task(self._execute_job(job_id))
```

이 패턴은 비동기 + 트랜잭션 경계를 다룰 때 항상 의식해야 하는 부분. flow-be에는 같은 패턴이 `_prepare_job_execution`(`execution_service.py:162-188`), `_update_target_shops_count`(L190-197), `_complete_job`(L354-365) 등 곳곳에 일관되게 적용되어 있다.

---

## 사례 5 ─ 매장 1000개 × 7일 매출/주문/광고 집계: 2단계 쿼리 + DB-level pagination + SQL VIEW

**구분**: 대시보드 / 대량 데이터 집계 / 쿼리 최적화
**핵심 커밋**: PR #20 `7c9d4eb`(2026-01-30 Cmong 2056 + 페이지네이션 추가, prod RDS 옵션, 대시보드 조회 쿼리 개선 - **view 삭제**), PR #19 `44e40c1` (주문 불러오기 API + 대시보드), PR #30 `c80c00b` (주문데이터·우가클 데이터 불러오기), `8439e34` (주문 대시보드 추가).

### 배경

댓글몽 Biz(프랜차이즈) 화면이 본사 1명이 산하 매장 1000개를 한 화면에서 본다. 한 화면에 보여야 할 것:

- 매장별 최근 7일 일별 주문 건수 (orders.sales_date 그룹화)
- 매장별 광고 ROAS, 클릭, 주문전환 (ShopDashboardAd)
- 매장별 일 매출(ShopDashboardDaily, BAEMIN/YOGIYO/CPEATS)
- 매장의 크롤링 지연(stale) 표시
- 브랜드 메타(brand_name, brand_user)

매출/주문 테이블은 매장 1000개 × 일 30건 × 12개월 = 누적 수백만 ~ 수천만 건 규모. 한 페이지 응답에 모든 매장의 모든 주문을 JOIN으로 끌고 오면 죽는다.

### 구현

#### 1) 2단계 쿼리 + DB-level LIMIT/OFFSET (Shop 먼저 추리고 → 그 Shop의 주문만 group by)

`api/services/dashboard.py:370-579` `get_orders_dashboard`:

```sql
-- Step 1: Shop 목록만 (LIMIT/OFFSET 적용, brand + brand_user + brand_shop 조인)
SELECT s.shop_id, s.platform_shop_id, s.name AS shop_name, s.platform, ...
       b.brand_id, b.display_name AS brand_name, bu.brand_user_id,
       bs.created_at AS joined_at, bs.is_active AS brand_shop_is_active, bs.deleted_at
FROM brands b
INNER JOIN brand_users bu ON bu.brand_id = b.brand_id
INNER JOIN shops s ON s.user_id = bu.user_id
INNER JOIN brand_shops bs ON bs.shop_id = s.shop_id AND bs.brand_id = b.brand_id
WHERE b.is_active = 1 AND b.deleted_at IS NULL
  AND s.platform IN (...)
  [AND b.brand_id = %s]    -- 필터
  [AND bs.is_active = 1 AND bs.deleted_at IS NULL]  -- include_removed=False일 때만
ORDER BY b.display_name, s.platform_shop_id
LIMIT %s OFFSET %s

-- Step 2: 위에서 추린 shop_ids에 대해서만 주문 group by
SELECT shop_id, sales_date, COUNT(order_id) AS order_count
FROM orders
WHERE shop_id IN (...추린 shop_ids)
  AND sales_date BETWEEN %s AND %s
GROUP BY shop_id, sales_date
```

핵심 결정 3가지:

1. **brand → brand_user → shop → brand_shop 의 4단 조인을 첫 단계에서 끝내고**, 두 번째 단계에서는 IN 절로만 orders를 친다. 즉 orders 테이블에 풀스캔이 아니라 IN 인덱스 lookup. shop이 페이지당 20개로 좁혀지면 두 번째 쿼리는 20개 shop의 7일치 주문만 GROUP BY.
2. **LIMIT/OFFSET을 DB 레벨에서**. Python 메모리에 다 끌어놓고 슬라이싱하지 않음. `has_more` 판단은 `LIMIT %s+1`로 한 건 더 가져와 비교(`dashboard.py:446, 450-451`).
3. **모든 raw SQL은 cls._execute_raw_sql + cursor 패턴**. Pony ORM의 lambda 쿼리 표현력이 7일치 일자별 expansion + brand 4단 조인을 자연스럽게 표현하기 어려워, dashboard만 raw SQL로 빠져나갔다. db.get_connection() 후 cursor.execute → fetchall → finally cursor.close()의 정석.

#### 2) shop 4가지 상태(active/inactive/deleted/removed)를 응답 시 분기

`dashboard.py:485-503`:

```python
if bs_deleted_at:
    is_removed, removed_at, removal_type = True, bs_deleted_at, "soft_delete"
elif bs_is_active == 0:
    is_removed, removal_type = True, "inactive"
elif shop_deleted_at:
    is_removed, removed_at, removal_type = True, shop_deleted_at, "shop_deleted"
elif shop_is_active == 0:
    is_removed, removal_type = True, "shop_inactive"
```

본사 관점에서 "왜 이 매장이 주문이 0이지" 를 단번에 분류해 보여주기 위한 4단 분기(브랜드에서 삭제 / 브랜드에서 비활성 / shop 자체 삭제 / shop 자체 비활성).

#### 3) v_shop_crawling_status VIEW로 stale 매장 조회 일원화

`api/services/dashboard.py:72-287`의 `get_crawling_status` / `get_stale_shops` / `get_crawling_summary`는 모두 RDB의 SQL VIEW(`v_shop_crawling_status`, `v_shop_crawling_summary`)에 의존한다.

- `last_crawled_at IS NOT NULL` + `hours_since_crawled >= %s` 로 stale 매장 추출
- `account_status != 'failed'` 로 실패 계정 자동 제외(`include_failed_accounts=False` 기본값)
- `plan_id`, `is_active`, `platform` 필터를 dynamic where 절로 조합
- 정렬은 `StaleShopSortField` enum (`hours_since_crawled` / `last_crawled_at` / 그 외)을 `sort_order`(asc/desc)와 조합해 ORDER BY 동적 생성

VIEW를 쓰는 이유는 **stale 판정 로직(account_status, plan_id, hours_since_crawled, is_active 4축 조합)을 백엔드 코드가 아닌 DB에 둬서, 다른 시스템(cmong-be, 어드민 ad-hoc 쿼리)도 같은 정의를 공유**하기 위함.

흥미로운 흔적: PR #20 메시지에 "**대시보드 조회 쿼리 개선 (view 삭제)**" — 처음에는 더 무거운 VIEW 한 개에 다 몰아넣었다가, 페이지네이션과 동적 필터 적용을 위해 그 VIEW를 제거하고 raw SQL + (별도의 작은 VIEW)로 옮겼다는 운영 학습.

#### 4) 광고/매출 데이터는 매장 단위로 increment-fetch

`task/services/advertisement_task.py`와 `task/services/shop_dashboard_task.py`는 각각:

- **광고는 15시간마다 갱신**: `should_fetch_advertisement` (`advertisement_task.py:70-97`) 가 직전 `updated_at`이 15시간 미만이면 skip → cron 매 시간 돌아도 실제 외부 API 호출은 사이클당 1/15.
- **매출 7일치를 한 번에 받아 일별 upsert**: `ShopDashboardTask`(`shop_dashboard_task.py`)는 BAEMIN/YOGIYO/CPEATS의 sales_summary API를 7일 범위로 호출해 daily_stats를 받고, 각 date에 대해 SUCCESS / PLATFORM_FAILED / SCRAPER_FAILED / FAILED 4상태로 upsert. 이미 SUCCESS / PLATFORM_FAILED인 날짜는 재시도하지 않음(`_get_dates_to_fetch`, L153-182). **상태 머신 기반 idempotent re-fetch**.

대시보드 응답은 위에서 채워진 `shop_dashboard_daily`/`shop_dashboard_ad` 테이블을 그대로 읽기 때문에, 무거운 외부 호출이 응답 경로에 끼지 않는다.

### 아키텍처

```
[댓글몽 Biz 본사 화면]
   │ GET /dashboard/orders?days=7&brand_id=X&limit=20&offset=0
   ▼
[DashboardService.get_orders_dashboard]
   ├─ Step 1: brand × brand_user × shop × brand_shop 조인 (LIMIT 20+1 / OFFSET)
   │           └─ shop 단위 4상태 분기 (active / inactive / shop_deleted / brand removed)
   └─ Step 2: orders IN (...shop_ids) AND sales_date BETWEEN start AND end
              GROUP BY shop_id, sales_date

[Crawling 대시보드]
   │ GET /dashboard/crawling-status?stale_hours=24&platform=...
   ▼
[v_shop_crawling_status VIEW]  ←──── (DB에서 정의 공유)
   └─ stale 4축 조합 + ORDER BY (정렬 enum)

[광고/매출 데이터 적재 흐름 (cron 측면)]
PopulateTaskService.execute
   └─ _fetch_advertisement_and_dashboard (한 매장 commit 후)
        ├─ AdvertisementTask.should_fetch (15h 컷)
        │   └─ httpx → owner/ad/shop → ShopDashboardAd upsert
        └─ ShopDashboardTask.should_fetch (날짜별 상태 점검)
            ├─ 재시도 필요한 날짜만 _get_dates_to_fetch
            ├─ httpx → owner/sales/summary (7일 한 번에)
            └─ daily_stats → ShopDashboardDaily upsert (date별 4상태)
```

### 도전과 해결

- **도전 A. 본사 1명이 1000개 매장을 한 화면에서 돌리는 상황의 응답 속도.**
  단순 JOIN 한 방으로 brand → ... → orders 까지 끌면 cardinality 폭발(1000 매장 × 7일 × 매장당 평균 주문 N건). 2단계 쿼리로 분리해 첫 단계가 1000행 → 20행으로 좁히고, 두 번째 단계는 20개 shop의 7일치 group by만. 같은 데이터 모델이라도 쿼리 모양으로 카디널리티를 통제.

- **도전 B. Pony ORM의 표현력 한계.**
  4단 조인 + dynamic where + dynamic order by + dynamic LIMIT 조합을 Pony lambda로 짜면 가독성과 일관성이 무너진다. dashboard는 raw SQL + parameterized query로 빠져나오는 결정. 다른 도메인(brand, shop_filter)에서는 Pony를 그대로 쓰되, **대시보드만큼은 raw SQL이 정답** 이라는 경계 설정.

- **도전 C. 정의 동기화 비용 (VIEW를 두는 이유).**
  stale 매장 판정 기준이 운영 중 자주 바뀐다(stale_hours 임계, account_status 정의). 백엔드 코드에 박아두면 변경 시마다 배포, 다른 시스템과의 불일치. RDB VIEW에 두면 정의를 SQL 한 곳에서 관리하고, 어드민 ad-hoc 쿼리, BI 도구, flow-be 모두 같은 정의를 본다.

- **도전 D. 외부 API 호출이 대시보드 응답 경로에 끼지 않도록 분리.**
  광고/매출은 cron이 매장 처리 끝나는 시점에 미리 적재(`_fetch_advertisement_and_dashboard`, `populate_task.py:1238-1289`), 본사 화면은 적재된 테이블만 read. 동기 응답 경로에서 외부 IO 0.

### 결과

- 매장 1000개 × 7일 일별 주문 트렌드 페이지 응답을 **2단계 쿼리 + DB-level LIMIT/OFFSET**으로 가볍게 유지.
- VIEW 기반 stale 판정으로 정책 변경 시 백엔드 배포 없이 SQL만 수정.
- 광고는 15시간 컷 / 매출은 상태 머신 기반 idempotent re-fetch로 외부 API 호출량 절감.
- 4상태(active/inactive/shop_deleted/brand_removed)를 응답에 직접 분류해 본사 운영자가 "주문 0인 이유"를 즉시 식별.

**사용 기술**: MySQL 8 raw SQL(parameterized, parameterized IN 리스트), SQL VIEW(`v_shop_crawling_status`, `v_shop_crawling_summary`), Pony ORM `db.get_connection()` cursor, dataclass 응답 + Pydantic `ShopOrderStatus` / `CrawlingSummaryItem`, dynamic ORDER BY/WHERE 빌더.

#### 추가 인사이트 — N+1 회피와 카디널리티 통제의 두 축

대량 데이터 대시보드의 가장 흔한 안티 패턴 두 가지:

1. **N+1**: shop 20개 조회 후 각 shop마다 orders 쿼리. 21개 쿼리.
2. **카디널리티 폭발**: shop × orders × brand 의 단일 거대 JOIN. 행이 수십만으로 부풀어 메모리/네트워크 압박.

flow-be `get_orders_dashboard`는 양쪽 다 피한다:

- 첫 단계는 brand × brand_user × shop × brand_shop만 → 행 수가 LIMIT으로 통제됨. 행마다 추가 쿼리 없음.
- 두 번째 단계는 IN (...20 shop_ids) + sales_date 범위 + GROUP BY → 20개 shop 각각의 7행 = 140행. 카디널리티 통제됨.

이 패턴은 일반화하면 "**select shape를 N+1과 단일 거대 JOIN 사이의 sweet spot인 2-스텝 batch select로 옮긴다**" 이다. ORM이 안 도와주거나 도와주는 방식이 비효율적일 때 raw SQL로 명시적으로 빠져나오는 결정.

#### 추가 인사이트 — VIEW를 코드로 옮기지 않은 결정

`v_shop_crawling_status` VIEW는 SQL로 정의되어 있다. 같은 정의를 Python 함수로 옮길 수도 있었다. VIEW를 유지한 이유:

1. **다른 소비자**: cmong-be (NestJS), 어드민 ad-hoc 쿼리, BI 도구 등 다른 시스템도 같은 정의를 본다. VIEW에 두면 정의가 단일 출처(single source of truth).
2. **운영자 직접 조작 가능**: stale 임계 정의(예: `account_status IS NULL OR account_status != 'failed'`)를 운영 중 바꿀 때 SQL DDL 한 줄 수정. 백엔드 코드 + 배포가 필요 없음.
3. **인덱스 + 쿼리 최적화의 위치**: VIEW 내부의 JOIN과 WHERE를 RDB 옵티마이저가 보고 인덱스를 활용. Python 함수로 빼면 옵티마이저 단위가 더 작아져 plan이 비효율적일 수 있다.

PR #20 메시지의 "**view 삭제**"는 이 결정의 반대 케이스 — 무거운 단일 VIEW에 모든 대시보드 쿼리를 다 몰아넣었더니 동적 필터 적용이 어려워서, 그 VIEW를 제거하고 stale 매장 판정용 작은 VIEW만 남기고 나머지는 raw SQL로 뺀 사례. 즉 **VIEW는 정의 공유가 가치 있는 경우에만 유지** 라는 운영 학습.

---

## 사례 6 ─ 불만족 리뷰 탐지 파이프라인: 노이즈 필터 + 길이 가중치 + AI Score 조합 스코어러

**구분**: AI 파이프라인 / 신호 처리 / 운영 데이터 모델링
**핵심 커밋**: `2c9bd06` (2026-01-16 feat: Implement AI scoring system and integrate with Redis), `f87ec5b` (구조 개선), `_save_review_score`/`ScoreProcessor` 도입은 PR #11/#7 라인.

### 배경

자동 답글이 위험한 가장 큰 케이스는 "별점은 5점인데 사실 본문은 컴플레인" 처럼 별점과 본문의 sentiment가 불일치할 때, 그리고 "ㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋ" 같은 노이즈 리뷰에 진지한 답글을 다는 케이스다. 댓글몽은:

1. AI MLOps 측에서 본문 자체의 sentiment score(0~100, 100이 매우 긍정)를 받아온다.
2. flow-be가 받아온 raw_score를 **본문 길이·반복·다양성** 같은 신호로 가중해 최종 score를 산출한다.
3. 임계치를 넘는 부정 리뷰는 별도 알림(BE 측 `send_negative_review_alarm` 흐름)으로 흐른다.

핵심은 **AI 모델이 못 거르는 노이즈 패턴(짧고 반복적, 이모지 도배, 자모 반복)을 사전 필터링** 해서 점수 자체를 None(skip)으로 만드는 것.

### 구현

#### 1) 두 단계 점수: noise pre-filter → AI raw_score → length-weighted final

`task/services/score_processor.py`:

```python
async def process_review(self, review_text, ai_client):
    pre_result = self.preprocess_review(review_text)
    if pre_result.should_skip:    # noise or empty
        return ScoreResult(score=None, ...)
    raw_score, reasons = await ai_client.request_score(pre_result.text_cleaned)
    if raw_score is None:
        return ScoreResult(score=None, ...)
    final_score = self.apply_score_weight(raw_score, pre_result.text_cleaned)
    return ScoreResult(score=final_score, reasons=reasons, ...)
```

#### 2) 노이즈 필터 ─ 6개 신호 가중 합산

`ScoreProcessor._noise_filter`(`score_processor.py:128-184`)가 6개 신호를 본다(임계치는 `ScoreTuning` Enum, 운영 노브):

| 신호 | 계산 |
|------|------|
| 토큰 반복도 (top word share) | `top_word_count / total_tokens` |
| Bigram / Trigram 반복도 | `most_common_ngram / total_ngrams` |
| 샤논 엔트로피 | `-Σ p log2 p` (문자 단위) |
| 문자 다양성 | `unique_chars / length` (40자 이상에서만) |
| 압축률 | `zlib.compress(text) / len(text)` |
| 같은 문자 / 이모지 4회 이상 연속 | regex `(.)\1{4,}`, `(emoji)\1{4,}` |

각 신호에 가중치(`TOKEN_REPEAT_WEIGHT=1.5`, `BIGRAM_REP_WEIGHT=1.2`, ...)를 곱해 가중 합산이 `NOISE_WEIGHTED_THRESHOLD=2.0`을 넘으면 noise로 판정. 단일 신호 임계 통과로 결정하지 않고 가중 합산을 쓴 이유는, **"엔트로피만 낮으면 외래어/한자 리뷰가 잘못 걸리고, 반복만 보면 의도적 강조가 노이즈로 잡힌다"** 는 운영 시그널 누적의 결과.

#### 3) 길이 가중치 ─ Bell + Polarity Amplification + Positive Bonus

`_length_weight_bell` (`score_processor.py:186-201`):

리뷰 길이 n에 따라 sweet-spot(60~600자)에서 가중치 1, 너무 짧으면 (60자 미만) 0.7 + (n/60)^1.5 식의 신뢰도 shrink, 너무 길면(>600자) 점진적 감쇠. 즉 **너무 짧은 리뷰는 raw score를 50(중립) 쪽으로 끌어내리고, 너무 긴 리뷰는 신뢰도를 다시 감쇠**.

`_polarity_amplify_weight` (`score_processor.py:203-222`): sweet-spot에서는 deviation을 1.2배 증폭(긍정/부정을 더 또렷하게), 양극단에서는 1배로 감쇠.

`_apply_length_weight` (`score_processor.py:240-253`):

```python
deviation = base_score - 50.0
raw_push = deviation * w_conf * w_pol
cap = 35.0
final_score = 50.0 + math.tanh(raw_push / cap) * cap
bonus = self._positive_length_bonus(base_score, n)
final_score += bonus
final_score = max(0.0, min(100.0, final_score))
```

tanh로 양 끝에서 sigmoidal하게 누르고, 50을 중심으로 ±35 범위로 박스. 추가로 score >= 75 이고 40~250자 길이일 때 최대 +5 보너스 — **"긍정이고 적절히 긴" 리뷰는 더 또렷하게 긍정으로**.

#### 4) 스코어 저장 idempotent 보장

`PopulateTaskService._save_review_score`/`_check_existing_score` (`populate_task.py:1052-1097`):

```python
@db_session
def _check_existing_score(self, review_id):
    existing = ReviewScore.select(lambda rs:
        rs.review.review_id == review_id and rs.version == SCORE_VERSION
    ).first()
    return existing is not None
```

`SCORE_VERSION = "v1"` 별로 idempotent. 스코어링 알고리즘이 v2로 가더라도 v1 점수는 그대로 남고 v2 점수가 별도 row로 추가. 운영 시점에 v1 → v2 마이그레이션 시 backfill 가능한 구조.

#### 5) ReviewScoreThreshold 테이블로 임계치도 데이터화

`task/models/review.py:91-100`의 `ReviewScoreThreshold`:

```python
threshold_id = PrimaryKey(int, auto=True)
label = Required(str, 20)              # e.g. "NEGATIVE", "NEUTRAL", "POSITIVE"
display_name = Optional(str, 50)
min_score = Required(float)
max_score = Required(float)
```

레이블·구간을 코드가 아닌 DB에 둬서, "불만족 기준을 점수 30 → 40으로 올리자"가 배포 없이 됨.

### 아키텍처

```
[리뷰 수집 후 POST_PROCESSING 단계]
        │ review_id
        ▼
[_save_review_score(review_id, content)]
        │
        ├─ _check_existing_score(review_id, version=v1)   ── idempotent
        │      └─ 이미 있으면 skip
        │
        ├─ ai_client.request_score(content)
        │      └─ POST https://ml.lemong.ai/score/  (httpx, 60s, basic auth)
        │      └─ raw_score: float (0~100), reasons: list[str]
        │
        ▼
[ScoreProcessor (in test/utility, future production wiring)]
   preprocess_review
        ├─ NaN/empty → skip
        ├─ 정규화 (다중공백/이모지 run/구두점)
        └─ _noise_filter
              · 6신호 가중합 ≥ 2.0 → skip("noise")
   apply_score_weight
        ├─ _length_weight_bell(n)        ── sweet spot 60-600
        ├─ _polarity_amplify_weight(n)   ── sweet spot에서 1.2x
        ├─ tanh로 ±35 박스
        └─ score>=75 & 40-250자 → +5 bonus
        │
        ▼
[ReviewScore insert(score, reasons, version=v1)]

[ReviewScoreThreshold 테이블 (DB)]
   ├─ NEGATIVE: 0 ~ X
   ├─ NEUTRAL:  X ~ Y
   └─ POSITIVE: Y ~ 100
        (운영자가 DB에서 직접 조정 가능)
```

### 도전과 해결

- **도전 A. AI 모델이 못 거르는 노이즈를 model 호출 비용 없이 사전 필터링.**
  "ㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋ"에 50점 raw 호출을 던지면 AI 인프라 비용 + 응답 시간 낭비. preprocess 단계의 6신호 노이즈 필터로 AI 호출 자체를 막아 비용/지연 동시 절감.

- **도전 B. 짧은 리뷰의 점수 신뢰도 vs 긴 리뷰의 신호 희석을 한 함수에서 해결.**
  Bell + Polarity 두 가중치를 별도 함수로 분리해 가독성 유지 (`_length_weight_bell`은 신뢰도 shrink, `_polarity_amplify_weight`는 sweet spot 증폭). 합산 시 tanh로 양극단을 누르고, positive 보너스만 별도로 더해 명시적.

- **도전 C. 알고리즘 변경 시 과거 데이터 정합성.**
  `SCORE_VERSION = "v1"` 컬럼을 PK 일부처럼 다뤄, 같은 review_id에 여러 버전이 공존하도록 모델 설계. 운영 시점에 v2 알고리즘으로 백필하더라도 v1 점수에 의존한 다운스트림(알림톡 로직)은 깨지지 않음.

- **도전 D. 임계치를 코드에서 빼서 운영자가 만지게.**
  `ReviewScoreThreshold` 테이블 + `ScoreTuning` Enum의 이중 노브. 알고리즘 자체의 튜닝 파라미터는 Enum(코드 변경 + PR로 관리), 분류 임계치(NEGATIVE/POSITIVE 컷)는 DB 테이블(운영자가 직접 조정).

### 결과

- AI Score API 호출 전에 노이즈 6신호 가중 필터로 잡 비용 절감 + 노이즈 리뷰에 대한 잘못된 자동 답글/알림 방지.
- 길이 가중치(bell + polarity + bonus + tanh box)로 raw score를 신뢰도 보정.
- 알고리즘 버전·임계치 양쪽을 분리한 운영 가능 구조(version 컬럼 + threshold 테이블).
- 1차 운영용 골격을 `c58fa32` ~ PR #11 라인에서 `task/services/score_processor.py` + `_save_review_score` 결합으로 확립.

**사용 기술**: Python `math.tanh`, `zlib.compress`(엔트로피 보조), `collections.Counter`(n-gram), `re`(emoji/repeat run), Shannon entropy, MLOps Score API(httpx), `ReviewScore`/`ReviewScoreThreshold` Pony 모델, `SCORE_VERSION` 기반 idempotency.

#### 추가 인사이트 — 신호 처리 관점에서의 노이즈 필터

이 필터는 단순한 if-else 룰 묶음이 아니라 **신호 처리 + 정보 이론 관점의 가중 합산** 이다.

- **샤논 엔트로피(`-Σ p log2 p`)**: 한 글자가 얼마나 균등하게 분포하는지. "ㅋㅋㅋㅋㅋ"는 엔트로피 0에 가까움.
- **zlib 압축률**: 정보량이 적은 텍스트는 압축이 잘 됨. 압축률 < 0.45면 단일 노이즈 신호.
- **n-gram 반복도**: bigram/trigram이 한 종류로 쏠리면 의미 없는 반복(`"맛있어요 맛있어요 맛있어요"`).
- **이모지/문자 run**: 같은 이모지/자모 4회 이상 연속.

이 5종 신호를 단일 임계로 잡으면 false positive가 나기 쉽다(예: 정상 외국어 리뷰가 엔트로피 임계에 걸림). 그래서 **각 신호에 가중치를 두고 합산이 임계를 넘으면 노이즈** 라는 다중 신호 fusion 패턴. AI 모델이 직접 노이즈를 판정하기 전에 cheap한 신호로 사전 컷.

#### 추가 인사이트 — 길이 가중치의 두 축 분리 이유

`_length_weight_bell(n)`은 **신뢰도(confidence shrink)** — 너무 짧으면 raw_score를 50 쪽으로 끌어내려 영향력을 줄임.
`_polarity_amplify_weight(n)`은 **극성 증폭(polarity amplification)** — sweet spot에서는 deviation을 1.2배 증폭.

두 가중치가 합쳐지면:

```
deviation = base_score - 50
raw_push = deviation × w_confidence × w_polarity
final = 50 + tanh(raw_push / 35) × 35
```

`tanh`로 양극단을 부드럽게 누른다 — raw_push가 아무리 커도 final은 50±35 박스 안. 이건 sigmoidal squashing의 고전 패턴.

분리한 이유는 운영 튜닝 시 두 축을 독립적으로 조정할 수 있게 하기 위함. "짧은 리뷰는 더 보수적으로(W_MIN ↑)" vs "긍정/부정을 더 또렷하게(PEAK ↑)"가 한 함수에 묶이면 한 노브를 만질 때 다른 효과까지 같이 흔들린다.

#### 코드 패턴 — 알고리즘 튜닝 노브를 Enum으로

```python
class ScoreTuning(Enum):
    SWEET_MIN = 60
    SWEET_MAX = 600
    W_MIN = 0.7
    PEAK = 1.20
    NOISE_WEIGHTED_THRESHOLD = 2.0
    BAND_HIGH = 0.75
    POSITIVE_THRESHOLD = 75.0
    POSITIVE_BONUS_MAX = 5.0
    ...
```

이런 튜닝 상수를 Enum으로 묶은 이유:

1. 한 곳에서 모든 노브를 본다 — 코드 리뷰 시 "어디서 이 값을 바꿔야 하지" 가 명확.
2. `.value` 접근만 허용 → 우발적 수정 방지.
3. 신규 노브 추가 시 명시적 enum entry 추가가 필요 → 운영 메모 남기기 좋음.

---

## 사례 7 ─ 외부 스크래퍼 의존성 격리: 401/타임아웃/플랫폼 에러 분류 + 3회 재시도 + 자동 비활성화 + 프록시 라우팅

**구분**: 외부 의존성 격리 / 에러 분류 / 운영 정책
**핵심 커밋**: `f192aa4` (스크래퍼 연결 에러 수정), PR #13 `23a41d5`(리뷰 불러오기 오류 수정 및 상태값 변경되게 수정), PR #15 `880104d`(리뷰 불러오기 수정 및 응답형식 수정), `bb444bb` (platform enum str 제거), `task/clients/scraper_client.py:handle_scraper_error`.

### 배경

flow-be는 직접 배달 플랫폼(BAEMIN/YOGIYO/CPEATS/DDANGYO/NAVER)을 긁지 않는다. **별도의 스크래퍼 서비스**(URL은 `PlatformScraperConfig` 테이블에서 환경별로 매핑, `common/utils/url_mapper.py:24-40`)에 HTTP 요청을 던지고, 거기서 응답을 받아 RDB에 적재한다.

이 구조는 외부 의존성이 한 층 추가된 것이고, 운영 중 가장 흔한 사고는:

- **세션 만료/로그인 실패**: 매장 계정 비밀번호가 플랫폼에서 변경되었거나, captcha가 떴거나.
- **타임아웃**: 스크래퍼가 헤드리스 브라우저로 플랫폼을 긁는 중 5분을 넘김.
- **플랫폼 차단**: IP가 plat에서 차단되어 401/403.
- **스크래퍼 자체 다운**: 5xx 또는 connection refused.

이 4가지를 같은 `try except` 안에서 같은 에러로 처리하면, 매장 비활성화 / 운영자 알림 / 재시도 정책이 모두 한 묶음이 되어 운영이 망가진다.

### 구현

#### 1) ScraperAPIError vs PlatformAuthError 두 예외 계층

`common/exceptions/task_exceptions.py` (참조: `scraper_client.py:11`):

- `PlatformAuthError`: 401 또는 로그인/credential 키워드가 메시지에 포함. **재시도 불가, 즉시 매장 비활성화 카운트 증가.**
- `ScraperAPIError`: 그 외 HTTP 에러. `scraper_code` / `scraper_message`까지 응답 본문에서 파싱해 보존(`scraper_client.py:117-135`).

#### 2) 3회 재시도 (timeout만)

`scraper_client.py:101-154`:

```python
for attempt in range(self.RETRY_COUNT):  # 3회
    try:
        response = await client.get(endpoint, params=params, headers=headers)
        if response.status_code == 401:
            raise PlatformAuthError(platform, shop_id)  # 재시도 X
        if response.status_code >= 400:
            raise ScraperAPIError(...)  # 재시도 X
        return inner_data.get("reviews", [])
    except httpx.TimeoutException:
        logger.warning(f"Timeout (attempt {attempt+1}/3)")
        if attempt == self.RETRY_COUNT - 1:
            raise ScraperAPIError(platform, 408, "Request timeout")
    except (PlatformAuthError, ScraperAPIError):
        raise  # 상위 분류된 에러는 그대로 위로
    except Exception as e:
        if attempt == self.RETRY_COUNT - 1:
            raise ScraperAPIError(platform, 500, str(e))
```

**timeout만 3회 재시도** 인 게 핵심: 401은 한 번 더 한다고 통과할 게 아니고, 5xx도 즉시 운영자가 인지해야 한다. 일시적 네트워크 흔들림 = timeout만 재시도.

#### 3) PopulateTaskService 측의 에러 메시지 분류 → TaskStatus 분기

`task/services/populate_task.py:290-306`:

```python
except Exception as e:
    error_str = str(e).lower()
    if "timeout" in error_str:
        self._error_status = TaskStatus.SCRAPER_TIMEOUT
    elif "auth" in error_str or "login" in error_str or "credential" in error_str:
        self._error_status = TaskStatus.AUTH_ERROR
    else:
        self._error_status = TaskStatus.SCRAPER_ERROR
    ScraperClient.handle_scraper_error(shop_info.platform_shop_id, shop_info.platform_enum)
    return False
```

3개의 별도 TaskStatus enum을 사용 → 운영 대시보드와 잡 상세 화면에서 운영자가 "왜 실패했는지"를 즉시 분류.

#### 4) 매장 비활성화 카운터: ShopDeactivationCount

`scraper_client.py:329-376`:

```python
@staticmethod
@db_session
def handle_scraper_error(platform_shop_id, platform=None):
    shop = Shop.get(platform_shop_id=platform_shop_id)
    count_record = ShopDeactivationCount.select(
        lambda c: c.shop.platform_shop_id == platform_shop_id
    ).first()
    if not count_record:
        count_record = ShopDeactivationCount(shop=shop, error_count=1)
    else:
        count_record.error_count += 1

    if count_record.error_count > LOGIN_ERROR_THRESHOLD:  # 3
        if shop.is_active != 4:
            shop.is_active = 4   # 4 = 비활성
            ShopDeactivationLog(shop=shop, deactivated_at=...)
        count_record.delete()
    commit()

@staticmethod
@db_session
def reset_error_count(platform_shop_id):
    """성공 시 호출"""
```

**3회 누적되면 매장 자동 비활성화 + Log 적재**. 성공하면 카운트 리셋. 운영자가 매장 상태를 보고 사장님에게 "비밀번호 다시 입력해주세요" 안내 가능.

추가로 OrderTaskService는 잡 시작 전에 `ScraperClient.check_login_error_shop`로 비활성화 매장 사전 컷:

```python
# task/services/order_task.py:226-230
if ScraperClient.check_login_error_shop(self.platform_shop_id):
    self._error_status = TaskStatus.AUTH_ERROR
    return False
```

#### 5) 프록시 라우팅: NAVER 등 차단 위험 플랫폼만 proxy 사용

`scraper_client.py:79-92, 200-213`:

```python
platform_upper = platform.value.upper()
if should_use_proxy(platform_upper):
    proxy_details = get_proxy_info(user_id, platform_upper)
    if proxy_details:
        params["proxyInfo"] = json.dumps({
            "userId": user_id, "planId": 0,
            "platform": platform_upper, "proxy": proxy_details,
        })
```

`task/services/proxy_service.py`가 매장(`user_id`)별·플랫폼별로 어느 proxy를 쓸지 결정 — 댓글몽의 PAMS(Proxy Allocate Management System)와 연동되는 인터페이스. flow-be는 proxy 결정 자체에 관여하지 않고 **proxy 정보 dict를 스크래퍼에게 전달만**.

#### 6) Session 사전 검증 (validate_session)

`scraper_client.py:267-327`: scraper의 `owner/validate_session` 엔드포인트에 platform_id/password로 세션이 살아있는지 사전 확인. `loggedIn=true`면 정상, 아니면 platform_code/platform_message를 반환해 운영자에게 정확한 사유 전달.

### 아키텍처

```
[PopulateTaskService.execute]
        │
        ▼
[ScraperClient.fetch_reviews]
        ├─ params 빌드 (platform_id, password, channel, shop_id, range, count)
        ├─ should_use_proxy(platform) ? params["proxyInfo"] = {...}
        ├─ httpx.AsyncClient(timeout=300)
        │
        ├─ retry x 3 (timeout만)
        │     ├─ 200 → return reviews
        │     ├─ 401 → raise PlatformAuthError
        │     ├─ ≥400 → raise ScraperAPIError(scraper_code, scraper_message)
        │     └─ TimeoutException → 다음 attempt
        │
        ▼
[PopulateTaskService except]
        ├─ "timeout"     → TaskStatus.SCRAPER_TIMEOUT
        ├─ "auth/login"  → TaskStatus.AUTH_ERROR
        └─ 그 외         → TaskStatus.SCRAPER_ERROR
        │
        └─► ScraperClient.handle_scraper_error
                ├─ ShopDeactivationCount ++
                └─ count > 3 → Shop.is_active = 4 (비활성) + ShopDeactivationLog

[OrderTaskService]
        └─ 시작 전에 check_login_error_shop(platform_shop_id)로 사전 컷
```

### 도전과 해결

- **도전 A. "스크래퍼 자체가 다운" vs "플랫폼이 우리를 차단"을 구분.**
  같은 5xx여도 의미가 완전히 다르다. ScraperAPIError 생성 시 `scraper_code`/`scraper_message`를 응답 본문에서 추출해 보존(`scraper_client.py:120-135`). 운영자가 잡 상세에서 사유를 본 후 스크래퍼팀에 컨택할지 사장님에게 컨택할지 분기.

- **도전 B. 매장 자동 비활성화의 임계치 + 회복 경로.**
  3회 누적 비활성 + 성공 시 리셋. 너무 빨리 비활성화하면 일시 장애에서 매장이 줄줄이 꺼지고, 너무 느리면 무한 재시도. PR #29의 `populate_constants.py:36-43`에 플랫폼별로 임계치 차등(BAEMIN=3, YOGIYO=2, NAVER=1)을 두는 정책 확장 포인트도 마련.

- **도전 C. 잡 자체는 실패해도 운영 가시성을 잃지 않게.**
  스크래퍼 에러로 잡이 죽어도 TaskStatus enum과 error_message가 Redis Job Hash에 남고, Pub/Sub로 어드민에 즉시 전파(`api/services/populate.py:373` warning 로그 + `publish_status` 호출). 운영자는 어드민 화면에서 어떤 매장이 어떤 사유로 실패했는지 실시간 추적.

- **도전 D. retry가 외부 부하를 증폭시키는 anti-pattern 회피.**
  401/4xx는 재시도 안 함. 5xx도 즉시 fail. **Timeout만 재시도** 정책으로 plat·scraper에 무의미한 부하를 다시 던지지 않음. 동시에 매장 단위 비활성화 카운트로, 같은 매장이 계속 실패하는 경우 잡 자체를 사전에 컷.

### 결과

- 외부 의존성(스크래퍼) 에러를 3종(AUTH_ERROR / SCRAPER_TIMEOUT / SCRAPER_ERROR)으로 분류해 운영 가시성 확보.
- 매장 자동 비활성화(임계 3) + 성공 시 카운트 리셋의 자가 치유 정책.
- proxy 정보 전달은 PAMS와의 책임 분리 — flow-be는 routing 결정에 관여하지 않음.
- Session 사전 검증(`validate_session`)으로 잘못된 credential로 잡을 띄우는 사고 사전 차단.

**사용 기술**: httpx AsyncClient(timeout=300, retry 3회 selective), 예외 계층(PlatformAuthError / ScraperAPIError + scraper_code/scraper_message 보존), Pony ORM의 `ShopDeactivationCount` + `ShopDeactivationLog` 자가 치유 모델, PAMS proxy info passthrough, MySQL `is_active=4` 비활성 상태 머신.

#### 추가 인사이트 — 재시도가 부하 증폭으로 가는 함정

Resilience 패턴을 잘못 쓰면 retry가 외부 시스템에 폭주를 가한다. 흔한 안티 패턴:

1. **모든 에러에 retry**: 401인데 한 번 더 시도 → credential이 잘못된 게 분명하면 그대로 fail이 맞다.
2. **고정 backoff 없이 retry**: 즉시 3회 retry 시 외부 시스템에 3배 부하.
3. **circuit breaker 없는 retry**: 외부 시스템이 다운된 상태에서 모든 클라이언트가 retry를 누적 → cascading failure.

flow-be의 답:

- **선별 retry**: Timeout만 retry. 401/4xx/5xx는 즉시 fail.
- **매장 단위 circuit breaker**: `ShopDeactivationCount`가 3회 누적되면 매장 비활성. 이게 사실상 매장 단위 circuit breaker 역할. 같은 매장에 같은 사고가 누적되면 잡 자체를 띄우지 않음.
- **사전 컷**: `check_login_error_shop`로 잡 시작 전에 비활성 매장을 거른다.

이 구조는 외부 시스템(scraper)의 안전을 우리가 직접 책임지는 정책이다. 우리가 retry burst를 보내지 않는 게 곧 시스템 전체의 안정.

#### 추가 인사이트 — 자가 치유의 핵심: 성공 시 카운트 리셋

매장 비활성화 카운터가 한 번 증가하면 영원히 누적되면, 일시 장애로 카운트가 쌓인 매장이 그 후 정상이어도 점점 비활성 임계에 가까워진다. `reset_error_count`(`scraper_client.py:367-376`)가 **성공 시 카운트를 0으로** 되돌리는 게 핵심.

```
fail (count = 1) → fail (count = 2) → SUCCESS (count = 0) ← 리셋
fail → fail → fail → fail (count = 4 > 3) → 매장 비활성화
```

이 패턴은 "**연속 실패 N회 이상이면 차단**" 의 의미로 단일 카운터에 명시. 성공이 일종의 heartbeat 역할을 한다.

#### 추가 인사이트 — 에러 사유 보존의 가치

`ScraperAPIError`가 `scraper_code` / `scraper_message`를 받는 게 중요한 운영적 결정.

```python
raise ScraperAPIError(
    platform,
    response.status_code,
    response.text,
    scraper_code=str(scraper_code) if scraper_code else None,
    scraper_message=scraper_message,
)
```

스크래퍼 응답 본문에서 plat 측 에러 코드를 파싱해 전달 — 운영자가 잡 상세에서 "scraper_code=PLATFORM_BLOCKED" 같은 사유를 보면 어디에 컨택할지 즉시 판단. 단순 HTTP 500 메시지만 남기면 운영자는 매번 로그를 거꾸로 뒤져야 한다. **에러 객체가 캡처해야 할 것은 stack trace가 아니라 운영자가 다음 액션을 결정할 데이터** 라는 시니어 관점의 에러 설계.

---

## 부록 A. 이력서에 옮길 때의 톤·문구 추천

`resume_v9.md`의 톤(분산 환경의 트랜잭션 일관성·외부 의존성 격리)에 맞춰, flow-be 사례를 이력서에 한 단락으로 압축할 때 추천 문구.

```
flow-be (FastAPI 기반 운영 콘솔/스케줄러/AI 파이프라인 BE)

- 운영 어드민·정기 cron의 잡 상태를 Redis Hash + ZSet(생성순/상태별)로 저장하고
  TTL을 상태별 차등(RUNNING 6h / COMPLETED 1h / FAILED 2h)으로 두어 운영 가시성과
  스토리지 비용을 동시에 잡았습니다. ECS 재배포로 사라지던 백오피스 잡은 lifespan에서
  RUNNING/QUEUED 인덱스를 스캔해 QUEUED로 리셋하고 Semaphore(10)로 회복 동시성을 묶어
  자동 재시도되도록 했습니다 (PR #26).

- 한 매장의 리뷰 수집·AI 답글 생성·자동 게시까지 한 코루틴에서 처리하던 흐름의
  메모리 스파이크를 30개 단위 배치 + 매장 내 AI Semaphore(30) + 단일 db_session + 명시적
  gc.collect() 패턴으로 평탄화했고, 후처리 단계는 review_id만 들고 가도록 분리해 스크래퍼
  응답 dict 그래프가 commit과 동시에 해제되도록 했습니다 (PR #27/#28).

- 자동 답글(reply 게시) 기능을 BE API 우회 호출로 구현하면서, DB 트랜잭션 안에서는 게시에
  필요한 데이터만 dataclass로 추출하고 실제 외부 API 호출은 트랜잭션 밖에서 수행했습니다.
  게시 직전 4단 가드(is_replied / 기존 replies / AI 답글 기간 / reply2 content)로 중복·오답글을
  차단하고, BE API 호출은 API Key → JWT의 이중 인증으로 키 회전 시에도 잡이 죽지 않게
  했습니다 (PR #39).

- APScheduler 기반 정기 cron을 24시간 치 잡 선생성 + ±5분 윈도우 dedupe로 운영 가시성을
  확보하고, Config당 RUNNING 1개 보장 + 전역 워커 Semaphore(200)으로 동시성을 두 단계로
  제한했습니다. RUNNING 잡의 실시간 진행률은 Redis에서 read-through로 가져와 어드민 화면이
  매장 1000개 도는 cron 도중에도 매장 단위로 톡톡 올라가도록 했습니다.

- 프랜차이즈 본사가 1000개 매장을 한 화면에서 보는 댓글몽 Biz 대시보드는, brand × brand_user
  × shop × brand_shop의 4단 조인을 첫 단계에서 끝내고(LIMIT/OFFSET 적용) 두 번째 단계는
  추려진 shop_ids에 대해 orders를 group by 하는 2단계 raw SQL로 카디널리티를 통제했습니다.
  stale 매장 판정은 SQL VIEW(`v_shop_crawling_status`)에 두어 백엔드 코드 외 시스템도 같은
  정의를 공유하게 했습니다.

- 리뷰 sentiment 점수는 AI Score API 호출 전에 6신호 가중 노이즈 필터(엔트로피·압축률·
  n-gram 반복·token repeat·이모지 run)로 사전 컷하고, 받은 raw_score는 bell-shape 신뢰도
  shrink + sweet-spot polarity amplification + tanh ±35 박스 + 긍정 길이 보너스로 가중해
  최종 점수를 산출합니다. SCORE_VERSION 컬럼으로 알고리즘 버전을 분리해 v2 백필 시에도
  v1 점수가 보존되도록 했습니다.

- 외부 스크래퍼 의존성은 PlatformAuthError(즉시 비활성화 카운트++) / ScraperAPIError(에러
  본문의 scraper_code/message 보존) 2계층 예외로 분류했고, retry는 timeout에만 3회 적용해
  외부 부하 증폭을 막았습니다. 매장 단위 ShopDeactivationCount가 3회 누적되면 자동 비활성
  + DeactivationLog 적재로 운영자에게 가시화하고, 성공 시 즉시 카운트 리셋의 자가 치유
  구조를 적용했습니다.
```

---

## 부록 B. 핵심 파일 인덱스 (다음 작업용)

| 영역 | 파일 |
|------|------|
| 잡 매니저 (Redis Hash/ZSet 베이스) | `task/services/job_manager.py` |
| 잡 복구 (lifespan 호출) | `task/services/job_recovery.py` |
| 자동답글 + 메모리 배치 + AI 생성 | `task/services/populate_task.py` |
| 주문 수집 | `task/services/order_task.py` |
| 광고 데이터 (BAEMIN, 15h 컷) | `task/services/advertisement_task.py` |
| 매출/주문/대시보드 일별 (BAEMIN/YOGIYO/CPEATS) | `task/services/shop_dashboard_task.py` |
| 매장 필터 (plans/brand/use_cron/last_crawled) | `task/services/shop_filter_service.py` |
| 템플릿 답글 Redis 캐시 (cmong-mq와 공유) | `task/services/template_replies_cache.py` |
| 노이즈 필터 + 길이 가중 스코어러 | `task/services/score_processor.py` |
| Cron 스케줄러 (APScheduler) | `task/services/scheduler/scheduler_service.py` |
| Cron 실행 (Config당 RUNNING 1, global semaphore 200) | `task/services/scheduler/execution_service.py` |
| Cron 잡 생성/조회/recovery (RDB) | `task/services/scheduler/job_service.py` |
| Cron 실시간 진행률 (Redis + Pub/Sub) | `task/services/scheduler/progress_tracker.py` |
| 스크래퍼 클라이언트 (retry/proxy/error 분류) | `task/clients/scraper_client.py` |
| AI MLOps 클라이언트 (chat + score) | `task/clients/ai_client.py` |
| BE API 클라이언트 (API Key → JWT fallback) | `task/clients/be_client.py` |
| Pub/Sub 매니저 | `app/core/redis_pubsub.py` |
| WebSocket | `app/core/websocket.py`, `api/routers/ws.py` |
| 대시보드 raw SQL (4단 조인 + 2단계 쿼리) | `api/services/dashboard.py` |
| populate 트리거 (BackgroundTasks) | `api/services/populate.py` |
| lifespan (startup recovery + scheduler) | `app/main.py` |
| Pony ORM 모델 (optimistic lock disable 데코) | `task/models/database.py`, `task/models/review.py`, `task/models/cron_job.py` |

| PR / commit | 의미 |
|-------------|------|
| PR #1 `727cfea` (2026-01-13) | FastAPI + Docker + Redis + uv 부트스트랩 |
| PR #7 `b37434d` (2026-01-22) | 리뷰 불러오기 1차, JWT, CORS, 시크릿매니저 |
| PR #11 `721056b` (2026-01-23) | TemplateRepliesCache 도입 + ShopFilterService 리팩토링 |
| `2c9bd06` (2026-01-16) | AI scoring + Redis 통합 |
| PR #20 `7c9d4eb` (2026-01-30) | 페이지네이션 + prod RDS + 대시보드 view 삭제 |
| PR #26 `d106278` + `2207982` (2026-02-06) | Job 스키마 정리 + orphaned job 자동 재시도 (lifespan) |
| `8be9693`, `9b0d85c` (2026-02-11~12) | Cron Job 1차 작성 |
| PR #27 `25c46d4` (2026-02-27) | 메모리 스파이크 진단 로깅 |
| PR #28 `f9252b3` (2026-03-03) | AI 생성 로직 3슬롯 고정 |
| `7b76710` (2026-03-03) | 메모리 스파이크 수정 1차 (배치/db_session) |
| PR #36 `f64c360` (2026-03-12) | stale shops `last_crawled_at IS NOT NULL` 보정 |
| PR #37 `45f1381` (2026-03-12) | list_jobs에 GetShop 추가 |
| PR #39 `b03352b` (2026-03-13) | 자동댓글 기능 (수집 → AI → 게시 종단) |

---

## 부록 C. 시니어 5년차 톤·어휘 사전 (이 코드베이스 기준)

이력서에 옮길 때 사용할 표준 어휘. resume_v9.md의 톤에 맞춰 정리.

### 분산/비동기 어휘

| 한국어 | 영문/원어 | flow-be 적용 예 |
|--------|----------|----------------|
| 잡 라이프사이클 | job lifecycle | Redis Hash + ZSet(생성순/상태별) + TTL 상태별 차등 |
| 좀비 잡 / orphaned job | orphaned job | lifespan에서 RUNNING/QUEUED 인덱스 스캔 후 QUEUED 리셋 |
| 멱등성 | idempotency | `_check_existing_score(version)`, ±5분 윈도우 dedupe, `is_replied` 4단 가드 |
| 자가 치유 | self-healing | `list_jobs`에서 만료 키 자동 정리, 성공 시 deactivation count 리셋 |
| 동시성 제어 (2단) | concurrency control | 매장 내부 Semaphore(30) + 전역 Semaphore(200) |
| 백 프레셔 | back pressure | 전역 Semaphore + AI 호출 60s timeout |
| 사전 컷 / 사전 게이트 | pre-cut / pre-gate | `check_login_error_shop`, AI 답글 기간 컷, 매장 별점 컷오프 |
| 트랜잭션 경계 분리 | transactional boundary | `_collect_..._payload` (`@db_session`) → `_assemble_...` (pure) → `be_client.post_*` (outside) |
| 읽기 통과 / read-through | read-through | RUNNING cron 잡의 응답 시 Redis 실시간 진행률을 RDB 값에 덮어쓰기 |
| 단일 출처 | single source of truth | `v_shop_crawling_status` VIEW로 stale 판정 일원화 |
| 카디널리티 통제 | cardinality control | 2단계 쿼리 (shop LIMIT/OFFSET → orders IN GROUP BY) |
| 책임 분담 / 경계 명확화 | responsibility boundary | flow-be는 AI 생성 + 정책, cmong-be는 게시 멱등성 + 알림톡 |
| 보수적 회복 | conservative recovery | recovery 시 worker_count=10 (정상 cron은 200) |

### 운영/가시성 어휘

| 한국어 | 영문 | flow-be 적용 예 |
|--------|------|----------------|
| 운영 가시성 | operational visibility | TaskStatus 분류, scraper_code/message 보존, 잡 metrics 카운터 분리 |
| 운영 노브 | operational knob | `ScoreTuning` Enum (튜닝), `ReviewScoreThreshold` 테이블 (분류 컷) |
| 차등 정책 | tiered policy | TTL 상태별 (RUNNING 6h / COMPLETED 1h / FAILED 2h), 플랫폼별 로그인 에러 임계 |
| 명시적 사유 | explicit reason | CANCELLED 시 error_message에 "이전 Job이 아직 실행 중이어서 취소됨" |
| 측정 우선 / 측정 기반 | measure-first | `_get_memory_mb()` 로깅 → 30개 배치 결정 → gc.collect() 추가 |

### 안티 패턴 회피

| 흔한 안티 패턴 | flow-be의 회피 방식 |
|---------------|--------------------|
| db_session 안에서 await | 데이터만 dataclass로 추출 → 세션 닫고 → asyncio.create_task / await |
| 모든 에러에 retry | Timeout만 retry, 401/4xx는 즉시 fail |
| 단일 거대 JOIN | 2단계 쿼리 (shop 추리고 → orders IN으로 좁힘) |
| Python 메모리에 전체 결과 + 슬라이싱 | DB-level LIMIT/OFFSET (LIMIT +1 트릭으로 has_more 판정) |
| 정의를 코드에 박기 | stale 판정은 SQL VIEW, 분류 임계는 DB 테이블 |
| 우발적 gc.collect() | 배치 끝 시점에만 + 측정으로 정당화 |

---

## 부록 D. 다섯 가지 시니어 관점 정리 (한 줄씩)

면접에서 한 줄로 답해야 할 때:

1. **트랜잭션 경계** — Pony ORM `@db_session`을 짧게 끊고, 외부 IO는 트랜잭션 밖. 이 원칙이 자동답글·cron 잡·매장 비활성화 모든 흐름에 일관 적용.
2. **동시성을 2단으로 제한** — 매장 내 AI Semaphore(30) × 전역 cron Semaphore(200) 의 곱셈으로 외부(스크래퍼 + MLOps) 부하를 결정적으로 제어.
3. **상태 저장소를 워크로드 모양에 맞춤** — 단명 잡은 Redis Hash + ZSet + TTL, 영속 잡은 RDB cron_jobs. RUNNING 잡의 진행률만 Redis read-through로 RDB에 맞춤.
4. **재시도는 timeout에만, 매장 단위 circuit breaker로 보강** — `ShopDeactivationCount` 누적 + 성공 시 리셋의 자가 치유 + 사전 컷.
5. **운영자에게 의사결정 데이터 노출** — scraper_code, error_message, CANCELLED 사유, TaskStatus enum 분류, Redis 실시간 progress 모두 어드민 화면에서 즉시 본다.

---

## 부록 E. 도메인 어휘 (댓글몽 기준)

- **댓글몽**: 자영업자용 리뷰 통합 SaaS (사장님 화면)
- **댓글몽 Biz**: 프랜차이즈 본사용 멀티매장 대시보드 (본사 화면)
- **flow-be**: 운영 어드민 + 정기 cron + AI 파이프라인 통합 BE (이 저장소)
- **cmong-be**: 사용자용 메인 BE (NestJS)
- **cmong-mq**: 사용자 트래픽의 백그라운드 작업 큐 워커
- **PAMS**: Proxy Allocate Management System (자체 프록시 풀)
- **MLOps**: ml.lemong.ai 도메인의 AI 생성/스코어링 서비스
- **Scraper**: 6개 플랫폼을 직접 헤드리스 브라우저로 긁는 별도 서비스
- **Platform Account**: 매장(Shop)이 외부 배달 플랫폼에 가지고 있는 로그인 계정. id/password 저장.
- **Platform Shop ID**: 외부 플랫폼의 매장 식별자 (배민 shop_id, 요기요 shop_id 등). flow-be의 PK 중 하나.
- **Cron Job (flow-be 정의)**: 운영자가 어드민에서 켜고 끄는 정기 작업의 단위 실행. `CronJobConfig`(설정) → `CronJob`(인스턴스) 관계.
- **Populate**: 한 매장의 리뷰를 수집 + AI 답글 생성 + (옵션) 자동 답글 게시까지 도는 한 잡.
- **Get Shop**: 한 user_id의 매장 목록을 BE API로부터 다시 가져오는 잡.


