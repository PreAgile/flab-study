# 아키텍처 다이어그램 6장 (Mermaid)

`resume_v12.md` 의 `diagrams/*.svg` 6장을 mermaid 다이어그램으로 옮긴 버전입니다.
GitHub · GitLab · Notion · VSCode · Obsidian 에서 native 로 렌더링됩니다.

---

## A1. 리뷰 통합 관리 SaaS — 전체 시스템 아키텍처

> 4 책임 도메인 · 6 외부 플랫폼 통합 · 멀티 인스턴스 · 멀티 워커 풀

```mermaid
flowchart TB
    User(["👤 사용자<br/>웹앱 · BIZ 대시보드"])
    Edge["🛡️ L7 Load Balancer<br/>JWT(RS256) · OAuth · WAF"]

    subgraph Domain["4 책임 도메인 (멀티 인스턴스)"]
        API["메인 API<br/>결제 · 쿠폰 · 알림톡<br/>멀티테넌트"]
        Batch["배치 워커<br/>2h cron · AI 스코어링<br/>Active-Active 8색"]
        Console["운영 콘솔 API<br/>워크플로 오케스트레이션<br/>BIZ 대시보드"]
        Scraper["스크래퍼 워커<br/>플랫폼당 30+ · 봇 탐지 우회"]
    end

    subgraph Data["데이터 / 메시징"]
        DB[("관계형 DB<br/>Cluster · Replica<br/>큐 테이블 · VIEW SSOT")]
        Cache[("분산 캐시<br/>Cluster 모드<br/>분산 락 · Token Bucket")]
        MQ[/"메시지 큐<br/>Quorum + DLQ"/]
    end

    subgraph Patterns["스크래퍼 도메인 패턴"]
        SLR["세션 락 레지스트리<br/>FIFO + Lease TTL"]
        SF["Single-Flight Coordinator<br/>Hexagonal + Decorator 5종"]
        Akamai["Akamai 우회 엔진<br/>인증 쿠키 4-state · Warming"]
        IPRep["자체 IP 평판<br/>매핑 3중 · Adaptive Cooldown"]
    end

    Ext{{"6 외부 플랫폼<br/>검색 포털 · 배달앱 · PG · 알림톡"}}

    Obs(["관측성 · 알림<br/>APM span tagging<br/>메트릭 · Slack"])

    User --> Edge --> API & Batch & Console & Scraper
    API --> DB & Cache
    Batch --> DB
    Console --> DB & Cache
    Scraper --> MQ
    MQ --> Scraper
    Scraper --> SLR & SF & Akamai & IPRep
    Scraper --> Ext
    Domain -.-> Obs
```

**운영 규모·핵심 성과 지표**

| 영역 | Before → After / 수치 |
|---|---|
| 일평균 처리량 | API **20만** · 페이지 스크래핑 **100만** · 리뷰 수집 **12만** |
| 프록시 풀 비용 | 월 800만 → **90만 (−88.75%)** |
| 요청 성공률 | 70% → **98%** |
| 세션 유지율 (6개월) | **99.2%** · 댓글 등록 중복 **0건** |
| Akamai 로그인 성공률 | 77.8% → **100%** (18/18 iter 측정 입증) |
| CROSSSLOT 사고 | **0건** |
| 오픈소스 | Kotest **6 PR** · Armeria **1 PR** · Spring Batch **1 PR** |

---

## A2. 결제 webhook 4중 멱등성 — 분산 락 · DB · 상태머신 · 원자 해제

> race / ABA / 상태 역전 / out-of-order 의 4 hazard 를 단계별로 곱셈 결합한 방어선

```mermaid
sequenceDiagram
    autonumber
    participant PG as 결제 PG (외부)
    participant LB as L7 Load Balancer
    participant API as 결제 API (N 인스턴스)
    participant Cache as 분산 캐시
    participant DB as 관계형 DB

    Note over PG: retry · 정기결제 fallback · keep-alive
    PG->>LB: webhook (동일 식별자 중복 가능)
    LB->>API: 라운드 로빈 분배

    rect rgb(239, 246, 255)
        Note over API,Cache: ① 분산 락 (ABA-safe)
        API->>Cache: SETNX EX 30s, lock value = 요청 토큰
        alt 락 획득 실패
            API-->>PG: 200 OK 즉시 (retry 폭주 차단)
        end
    end

    rect rgb(236, 253, 245)
        Note over API,DB: ② DB UNIQUE — 최종 정합성 보루
        API->>DB: INSERT (imp_uid+merchant_uid+status)
        Note right of DB: 1시간 dedupe 윈도우
        alt 중복 키 위반
            API-->>PG: 200 OK (이미 처리됨)
        end
    end

    rect rgb(238, 242, 255)
        Note over API: ③ 상태머신 — 의미 충돌 분기
        API->>API: READY → PAID / FAILED / CANCELLED × action_type
        Note right of API: 상태 역전 시 status 포함 키로 별 row 격리
    end

    rect rgb(253, 244, 255)
        Note over API,Cache: ④ Lua 원자 해제
        API->>Cache: GET → 비교 → DEL (한 트랜잭션)
        Note right of Cache: 자기 토큰일 때만 해제 (TTL 만료 후 ABA 차단)
    end

    API-->>PG: 200 OK (멱등 응답)
```

**4 hazard 매핑**

| Hazard | 어느 단계가 차단 |
|---|---|
| PG retry 폭주 | ① 분산 락 → 즉시 200 OK |
| 멀티 인스턴스 race · in-memory dedupe 한계 | ② DB UNIQUE |
| PAID 뒤 FAILED 도착 (상태 역전) | ③ 상태머신 (복합 키에 status) |
| TTL 만료 후 ABA (남의 락 삭제) | ④ Lua 원자 해제 |

**보완 라인 — 일일 정합성 reconciliation cron (사례 2)**

```mermaid
flowchart LR
    Cron[일일 cron<br/>SafeCron 데코레이터<br/>09:10 KST] --> Detect

    subgraph Detect[3종 inconsistency 자동 탐지]
        I1["좀비 schedule<br/>DB 차집합 K << N 압축"]
        I2["중복 빌링키<br/>GROUP BY HAVING COUNT > 1"]
        I3["admin override orphan<br/>활성 종료일 > 다음 결제 + 1m"]
    end

    I1 --> Fix1[자동 SCHEDULED_CANCELLED]
    I2 --> Fix2[자동 scheduleCancel]
    I3 --> Fix3[운영자 Slack 알림]
```

---

## B1. 관계형 DB 를 큐로 — CAS 기반 분산 작업 큐

> 「MySQL is the queue」 · 낙관락 CAS · 같은 플랫폼 계정 직렬화 · 좀비 작업 자동 복구

```mermaid
flowchart LR
    User(["👤 사용자<br/>일괄 100~1,000건"]) --> API
    API["일괄 API<br/>중복 트리거 가드<br/>N 작업 INSERT (트랜잭션)"] --> DB

    DB[("queue_jobs 테이블<br/>관계형 DB")]

    DB --> W1["⚙️ Worker 1<br/>id=103 picked ✓"]
    DB --> W2["⚙️ Worker 2<br/>CAS 실패 (race)"]
    DB --> Wn["⚙️ Worker N<br/>id=102 picked ✓"]

    W1 --> Ext{{외부 플랫폼<br/>댓글 등록 1건 ≈ 3~5분 IO}}
    Wn --> Ext
    W1 --> Cache[("분산 캐시<br/>진행률 폴링 분산")]
    User -.폴링 (read-through).-> Cache
```

**CAS 픽업 SQL**

```sql
UPDATE queue_jobs
   SET status = 'IN_PROGRESS', updated_at = NOW(),
       status_message = '[[' || :instance_id || ']] processing'
 WHERE id = :picked_id
   AND status = 'WAITING'
   AND updated_at = :original_updated_at        -- ★ version 비교 (CAS)
   AND group_id NOT IN (:running_groups)
   AND platform_id NOT IN (:running_platforms); -- 같은 계정 직렬화
-- affected = 0 → 다른 인스턴스가 먼저 가져감 (Optimistic lock failed)
-- affected = 1 → 픽업 성공
```

**핵심 결정 — 왜 외부 큐가 아닌 RDB 인가**

| 옵션 | 한계 |
|---|---|
| 외부 메시지 큐 | fire-and-forget 최적, stateful 관리·취소·예약·진행률 폴링에 부적합 |
| 외부 큐 미들웨어 | 별도 인프라 비용 + 트랜잭션과 큐 묶기 어려움 |
| **관계형 DB 큐** | **트랜잭션 + 큐 책임 = 한 곳, CAS 가 분산 픽업 안전성 보장, SQL 운영 가시성** |

⇒ 분산 시스템의 검증된 패턴 — CAS(Compare-And-Set) SQL 버전 (`updated_at as version`)

---

## C1. 세션 락 레지스트리 — FIFO + Lease TTL + Cold-Start Guard

> 30+ 워커 동시 로그인 race 를 4 layer 직렬화 + Handoff + 안전망 3종

```mermaid
flowchart LR
    W1["⚙️ Worker 1<br/>acquire(shop_A)"] --> Q
    W2["⚙️ Worker 2<br/>acquire(shop_A)"] --> Q
    W3["⚙️ Worker 3<br/>acquire(shop_A)"] --> Q
    Wn["⚙️ Worker N<br/>acquire(shop_A)"] --> Q

    subgraph Registry["세션 락 레지스트리 (shop_id 단위 직렬화)"]
        Q["FIFO 큐<br/>(분산 캐시 LIST)"]
        HEAD["HEAD · GRANTED<br/>Worker 1<br/>Lease 90s · 5s 갱신"]
        Q1["QUEUED · pos 1<br/>Worker 2"]
        Q2["QUEUED · pos 2<br/>Worker 3"]
        Q3["QUEUED · pos N<br/>Worker N"]

        Q --> HEAD --> Q1 --> Q2 --> Q3

        Lease["lease value =<br/>{instanceId-UUID}:{timestamp}<br/>(fencing token 단순화)"]
        Watchdog["Watchdog (2s)<br/>stale head 자동 eviction"]
        Handle["Handle (RAII)<br/>activeCount invariant"]
    end

    HEAD --> Browser[("헤드리스 브라우저 풀<br/>stealth fork · 1 인스턴스 ≈ 1GB")]
```

**Cold-Start Guard — 가장 미묘한 hazard**

```mermaid
sequenceDiagram
    participant Old as 인스턴스 (다운)
    participant Queue as 분산 캐시 큐
    participant New as 새 인스턴스

    Old->>Queue: HEAD = {old-id}:t1 (lease 잡고 사망)
    Note over Old: ⛔ 영원히 release 안 됨
    New->>Queue: 부팅 후 enqueue 시도
    New->>Queue: HEAD lease prefix 검사
    Note over New,Queue: instanceId 다름 → 옛 인스턴스 잔재
    New->>Queue: DEL queue (통째 비움)
    New->>Queue: 새 HEAD 등록 (정상 진행)
```

**Cluster CROSSSLOT 정책 — 모듈별 의도된 분기**

| 모듈 | 정책 | 우선 가치 |
|---|---|---|
| Queue | 단일 키 분리 (slot spread) | 부하 분산 > 트랜잭션 묶음 |
| 평판 (사례 10) | hash tag `{pool}` 슬롯 강제 | 트랜잭션 묶음 > 부하 분산 |

**안전망 3종**

- **forceRelease** — 운영자 kill switch, 대기자 즉시 reject
- **forceTerminate** — activeCount 강제 0, 락 누수 차단
- **evictStaleHead** — 2s 주기, head 의 lease 키 부재 시 LREM

**운영 검증 결과 (최근 6개월)**

| 지표 | 값 |
|---|---|
| 세션 유지율 | **99.2%** |
| 동일 매장 동시 로그인 | **0건** |
| 댓글 등록 중복 | **0건 / 6개월** |
| execution context destroyed | **0건** |
| dead-letter 누수 | **0건** |
| CROSSSLOT 에러 | **0건** |

---

## C2. 자체 IP 평판 시스템 — Before / After

> 외부 의존 제거 · 비용 88.75% 절감 · 성공률 70% → 98% · 14 phase phased rollout

```mermaid
flowchart LR
    subgraph Before["BEFORE — 월 800만 · SPOF"]
        W1["⚙️ 스크래퍼 워커"] --> R[("외부 Residential 프록시<br/>Pay-per-GB · 단일 벤더")]
        R --> E1{{6 외부 플랫폼<br/>성공률 70%}}
    end

    Before -. 14 phase phased rollout .-> After

    subgraph After["AFTER — 월 90만 · 성공률 98%"]
        W2["⚙️ 스크래퍼 워커"] --> Resolver{Platform Resolver}
        Resolver -->|검색 포털| RepIP["자체 IP 평판<br/>sticky pool · 매핑 3중"]
        Resolver -->|배달앱| DC["Datacenter 풀<br/>Adaptive Cooldown"]
        RepIP --> Blocklist["이중 Blocklist<br/>port_set + ip_set"]
        DC --> Blocklist
        Blocklist --> E2{{6 외부 플랫폼<br/>성공률 98%}}
        Resolver -. pool exhausted .-> HA[(HA 보조 풀<br/>blocklist 필터)]
    end
```

**port ↔ IP 매핑 3중 저장 — cold start 외부 의존 X**

| 계층 | 저장소 | 역할 |
|---|---|---|
| ① | In-memory Map | 가장 빠른 hot lookup · latency 최소화 |
| ② | 분산 캐시 HASH | 인스턴스 간 공유 · hash tag `{pool}` · CROSSSLOT 회피 |
| ③ | 관계형 DB + 외부 스토리지 manifest | 영구 매핑 · 클러스터 cold start 부트스트랩 |

**6개월간 풀어낸 4 hazard**

| # | Hazard | 해결 |
|---|---|---|
| 1 | Identifier IP → port 전환 | port↔IP 영구 매핑 3중 · ASN 분류 + KR 가드 |
| 2 | Cluster CROSSSLOT | hash tag `{pool}` 슬롯 강제 (queue 와 반대 정책) |
| 3 | Pool exhausted fallback | legacy 도 blocklist 필터 · AI 코드 리뷰 3회 정밀화 |
| 4 | port rotation 회피 | 차단 IP → 그 port 자동 SADD · 이중 blocklist |

---

## C3. Akamai Bot Manager 우회 — 인증 쿠키 4-state + Referrer Warming + Click Loop

> 로그인 성공률 77.8% → 100% (18/18 iter 측정) · 옛 구현 4 silent 결함 모두 차단

```mermaid
flowchart TB
    Start([외부 플랫폼 로그인 진입]) --> S1
    S1["① 메인 페이지 진입 (mainUrl)<br/>referrer chain 형성"]
    S2["② Referrer Warming · 15s human-like telemetry<br/>mouse jitter 200~600px · 800~1,200ms 대기<br/>추적 쿠키 polling"]
    S3["③ 로그인 제출 + 인증 쿠키 변화 추적<br/>쿠키 상태 분류기"]
    S4["④ 정책 분기 · service/spec SSOT 순수 함수<br/>polling 정책 결정 함수"]
    S5["⑤ Click Loop · Enter 1회 + click 25회 (1~2s jitter)<br/>제출 timing 차단 패턴 회피"]

    S1 --> S2 --> S3 --> S4 --> S5
    S5 -->|성공| Ok([로그인 성공<br/>세션 락 handoff 시작])
    S5 -->|실패| Block[AkamaiBlockDetector<br/>3 경로 일관 호출<br/>silent 회귀 차단]
```

**`인증 쿠키` 상태머신 (우선순위: 차단 > challenge > 검증 > 초기)**

```mermaid
stateDiagram-v2
    [*] --> 초기: cookie 없음

    초기 --> 검증: 검증 토큰만 (verified)
    초기 --> challenge: challenge 토큰 (검증 대기)
    초기 --> 차단: 차단 토큰 (강한 시그널)

    검증 --> challenge: challenge 토큰 추가
    검증 --> 차단: 차단 토큰 추가
    challenge --> 차단: 차단 토큰 추가
    challenge --> 검증: challenge 토큰 사라짐 (race window)

    차단 --> [*]: Full Retry 또는 차단 응답
    검증 --> [*]: 로그인 성공
```

**측정 결과 (PR 본문에 박은 정량)**

| 단계 | 결과 |
|---|---|
| baseline (옛 구현) | 7 / 9 (**77.8%**) |
| **patch (Warming + Click Loop)** | **18 / 18 (100%)** |
| 6 iter × 3 worker | 모두 성공 → default ON 채택 |

**옛 구현의 4 silent 결함 → 모두 차단**

| 결함 | 옛 구현 | 신 구현 |
|---|---|---|
| ① 검증 토큰 첫 등장 즉시 break | race window 안 뒤늦은 challenge 토큰 놓침 | ENTER_RACE_WINDOW 안정 확인 후 break |
| ② 검증·차단 토큰 혼재 | 「검증 성공」 오분류 | 차단 토큰 포함 시 무조건 차단 |
| ③ Akamai → PASSWORD_ERROR | application 401/403 오분류로 retry | helper 3 경로 일관 호출 |
| ④ sensor 준비 전 제출 | 즉시 break · sensor 1~2초 추가 검증 못 받음 | Referrer Warming + Click Loop |

---



---

## B2. Hierarchical 동시성 (계정 단위 순차 · 계정 사이 병렬)

> 5,700+ 계정 · 13,000+ 매장 · 외부 락 서비스 없이 process-local 격리

```mermaid
flowchart LR
    Input["입력<br/>13,127 매장 · 5,719 그룹"] --> Group["그룹 격리<br/>(platform_id, password)"] --> Pool["ThreadPool max_workers=W"]
    Pool --> T1["⚙️ Thread 1 → 그룹 A"]
    Pool --> T2["⚙️ Thread 2 → 그룹 B"]
    Pool --> TN["⚙️ Thread W → 그룹 Z"]
    T1 --> SA1["🏪 매장 1"] --> SA2["🏪 매장 2"] --> SA3["🏪 매장 3"]
```

**임계치 dict — 플랫폼별 인증 에러 그룹 일괄 차단**

| 플랫폼 | 임계치 |
|---|---|
| 봇 탐지 심한 플랫폼 (검색 포털) | 0 |
| 배달앱 A | 3 |
| 배달앱 B | 2 |
| 배달앱 C | 3 |

---

## B3. BIZ 대시보드 — 2 단계 쿼리 + SQL VIEW SSOT

```mermaid
sequenceDiagram
    autonumber
    participant U as 본사 운영자
    participant API as 대시보드 API
    participant DB as 관계형 DB

    U->>API: GET /dashboard/orders?days=7&limit=20
    rect rgb(248, 250, 252)
        Note over API,DB: Step 1 — 4단 JOIN
        API->>DB: shop 목록만 ORDER BY ... LIMIT 21
        DB-->>API: shop_ids
    end
    rect rgb(236, 253, 245)
        Note over API,DB: Step 2 — IN lookup
        API->>DB: orders WHERE shop_id IN (...) GROUP BY
        DB-->>API: 140 행
    end
    API-->>U: 응답 (외부 IO 0건)
```

---

## C4. Single-Flight Coordinator — Hexagonal + Decorator 5종

```mermaid
flowchart LR
    subgraph Callers["호출 서비스 (Port 만 의존)"]
        S1["검색 포털 인증"]
        S2["배달앱 A·B·C 인증"]
    end
    Port["SingleFlightCoordinator (Port)"]
    S1 & S2 --> Port
    Port --> D5["⑤ Telemetry"] --> D4["④ Heartbeat"] --> D3["③ Capacity"] --> D2["② Deadline"] --> D1["① InProcess"]
    D1 --> Adapter[("Backend Adapter")]
```

**행동 계약 7가지** — 코알레싱 · 결과 일관성 · 자원 정리 · kill switch · 호출자 격리 · 입력 계약 · 관측성

---

## D1. 자동 답글 종단 파이프라인 — TOCTOU 4 게이트

```mermaid
flowchart TB
    Admin[어드민 트리거] --> Fetch[수집] --> AI[AI 답글 생성]
    AI --> Post
    subgraph Post[후처리 순서 고정]
        P1[리뷰 스코어링] --> P2[알림톡] --> P3[자동 답글]
    end
    P3 --> Gate
    subgraph Gate[4단 TOCTOU 게이트]
        G1[① is_replied] --> G2[② Reply.count] --> G3[③ 기간 컷오프] --> G4[④ 본문 존재]
    end
    Gate -->|통과| Assemble[합성 staticmethod] --> Auth{API Key} -->|401/403| JWT[JWT fallback] --> BE[메인 API 게시]
    Auth -->|성공| BE
```


## 다이어그램 ID 매핑

| ID | 본 md 섹션 | resume_v13.md 참조 |
|---|---|---|
| A1 | 전체 시스템 아키텍처 | `diagrams/A1_system_overview.svg` |
| A2 | webhook 4중 멱등성 시퀀스 | `diagrams/A2_payment_webhook_4layer.svg` |
| B1 | 관계형 DB 작업 큐 + CAS | `diagrams/B1_rds_queue_cas.svg` |
| B2 | Hierarchical 동시성 | `diagrams/B2_hierarchical_concurrency.svg` |
| B3 | BIZ 대시보드 2 단계 쿼리 | `diagrams/B3_dashboard_2step_query.svg` |
| C1 | 세션 락 레지스트리 + Cold-Start Guard | `diagrams/C1_session_lock_registry.svg` |
| C2 | 자체 IP 평판 Before / After | `diagrams/C2_proxy_pool_before_after.svg` |
| C3 | Akamai 우회 + 인증 쿠키 상태머신 | `diagrams/C3_akamai_bypass_state_machine.svg` |
| C4 | Single-Flight Coordinator | `diagrams/C4_single_flight_hexagonal.svg` |
| D1 | 자동 답글 종단 파이프라인 | `diagrams/D1_auto_reply_pipeline.svg` |
