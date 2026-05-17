# 댓글몽 시스템 아키텍처 (이력서 보조 자료)

> 르몽(Lemong) 「댓글몽 / 댓글몽 Biz」 — 6개 배달 플랫폼 통합 리뷰 관리 SaaS
> 일일 API 호출 20만+ / 페이지 스크래핑 100만+ / 리뷰 수집 12만+ / 플랫폼별 동시 worker 30+

---

## 1. 전체 시스템 아키텍처 (High-Level)

```mermaid
flowchart TB
    subgraph CLIENT["🧑 Client Layer"]
        WEB[댓글몽 Web App]
        BIZ[댓글몽 Biz<br/>프랜차이즈 대시보드]
    end

    subgraph EDGE["🌐 Edge / API Gateway"]
        ALB[AWS ALB<br/>keep-alive 301s]
        AUTH[JWT RS256 +<br/>Kakao OAuth SSO]
    end

    subgraph BE["⚙️ cmong-be (NestJS)"]
        direction TB
        API[REST API Layer<br/>137 controllers]
        BL[Business Logic<br/>100+ services]
        TX["@Transactional CLS<br/>+ Unified Error Handler"]
        EVT[EventEmitter2<br/>Domain Events]
    end

    subgraph MQ["📨 RabbitMQ (6 Queue)"]
        Q1[POPULATE_BATCH<br/>prefetch=1]
        Q2[SCRAPING<br/>prefetch=2]
        Q3[CPEATS_SCRAPING]
        Q4[MARKETING_SCRAPING]
        Q5[REPLY_REQUEST]
        Q6[REPLY_COMPLETE]
        DLQ[Dead Letter Queue]
    end

    subgraph SCRAPER["🤖 cmong-scraper-js (NestJS Worker)"]
        direction TB
        WP[Worker Pool<br/>30+ per platform]
        SLR[SessionLockRegistry<br/>FIFO + lease TTL]
        BP1[Camoufox Pool<br/>Firefox Stealth]
        BP2[Chromium Pool<br/>Playwright Stealth]
        SF[SingleFlightCoordinator<br/>5 invariants]
    end

    subgraph PAMS["🛡️ PAMS — Proxy Allocate Management"]
        direction TB
        NIR[Naver IP Reputation<br/>sticky pool allocator]
        DCP[Datacenter Proxy Pool<br/>월 800만 → 90만 절감]
        ADP[Adaptive Routing<br/>auto Cooldown]
    end

    subgraph PLATFORM["📱 6 외부 플랫폼"]
        P1[배달의민족]
        P2[요기요]
        P3[쿠팡이츠 + Akamai]
        P4[네이버 GraphQL]
        P5[땡겨요]
        P6[먹깨비]
    end

    subgraph DATA["💾 Data Layer"]
        MYSQL[(MySQL 8 / Aurora<br/>152 entities)]
        REDIS[(Redis<br/>분산 락 · Cache · Token Bucket)]
        ES[(ElasticSearch<br/>로그 분석)]
        S3[(AWS S3<br/>파일 스토리지)]
    end

    subgraph OBS["📊 Observability"]
        DD[Datadog APM<br/>dd-trace]
        PROM[Prometheus<br/>+ Grafana]
        SLACK[Slack Webhook<br/>운영 알림]
        KIB[Kibana<br/>로그 분석]
    end

    WEB --> ALB
    BIZ --> ALB
    ALB --> AUTH
    AUTH --> API
    API --> BL
    BL --> TX
    TX --> EVT
    BL <--> MYSQL
    BL <--> REDIS

    BL -->|publish| Q1
    BL -->|publish| Q2
    BL -->|publish| Q5
    Q1 --> WP
    Q2 --> WP
    Q3 --> WP
    Q4 --> WP
    Q5 --> WP
    WP -->|ack/result| Q6
    Q6 --> BL

    Q1 -.->|on fail| DLQ
    Q2 -.->|on fail| DLQ

    WP --> SLR
    SLR --> BP1
    SLR --> BP2
    BP1 -->|HTTP via| PAMS
    BP2 -->|HTTP via| PAMS
    WP --> SF

    NIR --> DCP
    DCP --> ADP
    ADP --> P1
    ADP --> P2
    ADP --> P3
    ADP --> P4
    ADP --> P5
    ADP --> P6

    BE -.->|trace| DD
    SCRAPER -.->|trace| DD
    PAMS -.->|metrics| PROM
    PROM --> SLACK
    BE -.->|logs| ES
    ES --> KIB

    classDef beStyle fill:#1F3A5F,stroke:#1F3A5F,color:#fff
    classDef scraperStyle fill:#C75B3F,stroke:#C75B3F,color:#fff
    classDef mqStyle fill:#F4F4F0,stroke:#666
    classDef dataStyle fill:#EAF1F8,stroke:#1F3A5F
    classDef obsStyle fill:#FBEEE9,stroke:#C75B3F
    classDef pamsStyle fill:#F4F4F0,stroke:#1F3A5F,color:#1F3A5F

    class API,BL,TX,EVT beStyle
    class WP,SLR,BP1,BP2,SF scraperStyle
    class Q1,Q2,Q3,Q4,Q5,Q6,DLQ mqStyle
    class MYSQL,REDIS,ES,S3 dataStyle
    class DD,PROM,SLACK,KIB obsStyle
    class NIR,DCP,ADP pamsStyle
```

---

## 2. 비동기 메시징 + 멱등성 4단계 (결제 webhook 흐름)

```mermaid
sequenceDiagram
    autonumber
    participant PG as Portone (PG사)
    participant API as cmong-be API
    participant Redis as Redis
    participant DB as MySQL
    participant Recon as Reconciliation<br/>(일일 배치)

    PG->>API: POST /payments/webhook<br/>{merchant_uid, imp_uid, status}

    Note over API,Redis: ① 분산 락 획득 (Redis SET NX + LUA)
    API->>Redis: SET NX lock:webhook:{merchant_uid}<br/>VALUE = Date.now() (ABA 방지 token)
    Redis-->>API: OK (TTL 30s)

    Note over API,DB: ② Idempotency-Key UNIQUE 제약
    API->>DB: INSERT idempotency_keys (merchant_uid)
    alt 이미 처리됨
        DB-->>API: UNIQUE violation
        API->>Redis: GET cached_response:{merchant_uid}
        Redis-->>API: 캐싱된 응답
        API-->>PG: 200 OK (idempotent)
    end

    Note over API,DB: ③ 결제 상태머신 전이
    API->>DB: UPDATE payments<br/>PENDING → CONFIRMED|CANCELLED
    DB-->>API: row updated

    Note over API,Redis: ④ Redis 응답 캐싱 (다음 webhook 대비)
    API->>Redis: SET cached_response:{merchant_uid}<br/>TTL 24h

    Note over API,Redis: 락 해제 (LUA DEL_IF_VALUE_MATCHES)
    API->>Redis: EVAL "DEL key IF value == token"
    Redis-->>API: 1 (released)

    API-->>PG: 200 OK

    Note over Recon,DB: 일일 reconciliation 배치
    Recon->>DB: SELECT * FROM payments<br/>WHERE updated_at > yesterday
    Recon->>PG: GET /payments/{imp_uid} (실 상태 확인)
    Recon->>DB: UPDATE if mismatch
```

---

## 3. Multi-Worker 동시 로그인 Race 방지 (SessionLockRegistry FIFO)

```mermaid
sequenceDiagram
    autonumber
    participant W1 as Worker 1
    participant W2 as Worker 2
    participant W3 as Worker 3
    participant SLR as SessionLockRegistry
    participant BP as Browser Pool
    participant Plt as 외부 플랫폼

    par 동시 로그인 요청 (worker 30+개)
        W1->>SLR: acquire(shop_A, "login")
    and
        W2->>SLR: acquire(shop_A, "login")
    and
        W3->>SLR: acquire(shop_A, "login")
    end

    Note over SLR: FIFO 큐 + lease TTL + watchdog
    SLR-->>W1: granted (lease 60s)
    SLR-->>W2: queued (position 1)
    SLR-->>W3: queued (position 2)

    Note over W1,Plt: W1만 실제 로그인 진행
    W1->>BP: allocate Camoufox session
    BP->>Plt: 로그인 (8종 분기 처리)
    alt 정상
        Plt-->>BP: cookies + session
    else captcha / 2FA
        Plt-->>BP: challenge → ScrapperException
        Note right of W1: 계층형 예외 처리<br/>→ 재시도 정책 적용
    else IP 차단
        Plt-->>BP: blocked → BeaconConfirmation 실패
        Note right of W1: PAMS에 IP rotation 요청
    end
    BP-->>W1: 세션 확보
    W1->>SLR: release(shop_A)

    Note over SLR,W2: 다음 worker에 lease 전달 (handoff)
    SLR-->>W2: granted — 이미 W1이 세션 만듦
    W2->>BP: reuse W1's session ✅
    Note right of W2: 동일 세션 재사용으로<br/>중복 로그인 방지

    SLR-->>W3: granted
    W3->>BP: reuse session ✅
```

---

## 4. 5분 단위 무거운 작업의 RabbitMQ 분리 (Reply-Request-Reply)

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant API as cmong-be
    participant MQ as RabbitMQ
    participant SC as cmong-scraper-js<br/>(Worker)
    participant DB as MySQL

    U->>API: POST /shops/{id}/reviews/sync
    Note over API: 동기 처리 시 5분 timeout 위험

    API->>MQ: publish (SCRAPING queue)<br/>+ replyTo + correlationId
    API->>U: 202 Accepted<br/>{ taskId, status: "QUEUED" }
    Note right of U: 사용자는 즉시 응답 받음

    par 백그라운드 처리
        MQ->>SC: consume (prefetch=2)
        Note over SC: 30+ worker 중 1개 할당
        SC->>SC: 5분짜리 스크래핑 + 파싱
        SC->>DB: bulk insert reviews
        SC->>MQ: publish REPLY_COMPLETE<br/>(correlationId)
        MQ->>API: consume REPLY_COMPLETE
        API->>DB: UPDATE task SET status="DONE"
    and 사용자 polling 또는 WebSocket
        U->>API: GET /tasks/{taskId}
        API->>DB: SELECT status
        API-->>U: { status: "PROCESSING" } 또는 "DONE" + data
    end

    Note over MQ: 실패 시 DLQ로<br/>+ Task Completion Cache로<br/>중복 처리 방지
```

---

## 5. PAMS — Proxy 비용 88.75% 절감 아키텍처

```mermaid
flowchart LR
    subgraph BEFORE["BEFORE — 월 800만 원"]
        WK1[Worker] -->|모든 요청| DECODO[Decodo Residential<br/>Pay-per-GB]
        DECODO --> EXT1[외부 플랫폼]
        style DECODO fill:#FBEEE9,stroke:#C75B3F
    end

    subgraph AFTER["AFTER — 월 90만 원 (88.75% ↓)"]
        WK2[Worker] --> RESOLVER{Platform Resolver}
        RESOLVER -->|Naver| NREP[Naver IP Reputation<br/>sticky pool]
        RESOLVER -->|Others| DCPOOL[Datacenter Proxy Pool<br/>+ Cooldown 알고리즘]
        NREP --> PORTIP[(port-IP mapping<br/>MySQL + S3 boot)]
        DCPOOL --> HEALTH[Health Monitor<br/>성공률·타임아웃·지연]
        HEALTH -.->|장애 IP| COOLDOWN[Auto Cooldown<br/>+ 트래픽 재분산]
        COOLDOWN -.-> DCPOOL
        NREP --> EXT2[외부 플랫폼]
        DCPOOL --> EXT2
        style NREP fill:#EAF1F8,stroke:#1F3A5F
        style DCPOOL fill:#EAF1F8,stroke:#1F3A5F
        style HEALTH fill:#F4F4F0,stroke:#666
    end

    METRICS["성공률 70% → 98%<br/>비용 800만 → 90만<br/>Prometheus + Grafana<br/>Health Dashboard"]
    AFTER --> METRICS
    style METRICS fill:#1F3A5F,color:#fff,stroke:#1F3A5F
```

---

## 6. JVM 자산 빌드 narrative — Node 추상 패턴 ↔ Kotlin/Spring 매핑

```mermaid
flowchart LR
    subgraph NODE["운영 자산 (Node.js / NestJS)"]
        N1[Redis SET NX + LUA<br/>분산 락]
        N2[Idempotency Key + 상태머신<br/>+ Redis 캐싱 + reconciliation]
        N3[SessionLockRegistry<br/>FIFO + lease TTL]
        N4[Custom Error Strategy<br/>5종 + 9종 카테고리]
        N5[Camoufox PID Registry<br/>OOM 회피]
        N6[RabbitMQ classic queue<br/>운영 5가지 한계 측정]
    end

    subgraph KOTLIN["자산 빌드 (Kotlin / Spring 3-Repo)"]
        K1[Redisson watchdog<br/>+ Pub/Sub 4종 비교]
        K2[ADR-006 결제 멱등성 4단계<br/>+ EXP-09b 9 시나리오]
        K3[Coroutines + supervisorScope<br/>+ Single-Flight 5 invariants]
        K4[Resilience4j 5종<br/>+ 9종 에러 분류기]
        K5[JVM Heap/GC 튜닝<br/>G1GC Region + Humongous]
        K6[Kafka 마이그레이션<br/>+ Outbox Relay]
    end

    META["메타 블로그 4편 (ko + en)<br/>『두 언어가 같은 추상 패턴을<br/>다른 도구로 푼다』"]

    N1 -.same pattern.-> K1
    N2 -.same pattern.-> K2
    N3 -.same pattern.-> K3
    N4 -.same pattern.-> K4
    N5 -.same pattern.-> K5
    N6 -.same pattern.-> K6

    NODE --> META
    KOTLIN --> META

    style NODE fill:#F4F4F0,stroke:#666
    style KOTLIN fill:#EAF1F8,stroke:#1F3A5F
    style META fill:#1F3A5F,color:#fff,stroke:#1F3A5F
```

---

## 사용 안내

- 각 다이어그램은 mermaid 문법으로, GitHub README나 Notion에서 그대로 렌더링됩니다.
- 면접 시 `핵심 시그널 → 1번 다이어그램 → 깊이 질문 → 2~6번 중 해당 다이어그램`으로 답변 가능합니다.
- 라이브 미리보기: https://mermaid.live 에서 각 코드 블록을 붙여넣어 확인하세요.
