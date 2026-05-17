# 백엔드 개발자 김면수

> **5년차+ 백엔드 엔지니어** · 분산 시스템 · 비동기 메시징 · 고성능 데이터 파이프라인
> Node.js / NestJS 운영 (5년) → JVM(Kotlin / Spring) 자산 빌드 중

**Mobile** 010-9101-5429 · **E-mail** digle117@gmail.com
**GitHub** github.com/PreAgile · **Blog** medium.com/@digle117 · **Portfolio Docs** [링크 채우기]

---

## Introduction

분산 환경에서의 **트랜잭션 일관성**, **비동기 메시징**, **고성능 데이터 파이프라인** 설계에 강점을 가지고 있습니다. "왜 이 구조를 선택했는가"에 대해 측정값 · 트레이드오프 · 외부 사례를 동시에 인용하는 의사결정 패턴을 가집니다.

현재 르몽(Lemong)에서 **6개 배달 플랫폼 통합 리뷰 관리 SaaS**의 백엔드 아키텍처를 설계하며, 세션 유지율 **99.2%**, Proxy 비용 **월 800만 → 90만 원 (88.75% 절감)**, 일일 **100만+ 페이지 스크래핑 / 12만+ 리뷰 수집 / API 20만+ 호출** 파이프라인을 운영합니다.

Node.js 5년 운영 자산을 **Kotlin / Spring 추상 패턴**으로 재설계하는 3-Repo 포트폴리오 (ADR 49+ · 실험 47+ · 블로그 17편 발행)를 빌드 중이며, 헤드리스 브라우저 OOM 회피 ↔ JVM Heap/GC 동형성, RabbitMQ → Kafka 운영자 회고 등 양 언어 추상 패턴 매핑을 자산화하고 있습니다.

---

## 핵심 시그널

**① 6 플랫폼 외부 게이트웨이 운영** — 배민 · 요기요 · 쿠팡이츠 · 네이버 · 땡겨요 · 먹깨비 통합. REST + GraphQL + Headless Browser 매트릭스 + 9종 에러 카테고리 분류기 + 8종 LOGIN 분기 (정상 / captcha / 2FA / IP차단 / device verify / password 변경 / account locked / unknown).

**② 분산 락 + 멱등성 4단계 전략** — Redis SET NX + LUA `DEL_IF_VALUE_MATCHES` (ABA 방지 timestamp 토큰) → 결제 webhook 중복 처리 0건. Idempotency 키 + 상태머신 + Redis 응답 캐싱 + reconciliation 4단계.

**③ 비동기 메시징 파이프라인** — RabbitMQ 6 큐 (POPULATE_BATCH / SCRAPING / MARKETING_*) prefetch 튜닝 + DLQ. 5분 단위 무거운 작업의 reply-request-reply 분리. **TPS 1,000/s · 예약 실패율 1% 이하 · 처리 지연 10초 미만**.

**④ Proxy Allocate Management System (PAMS)** — 외부 Decodo 의존을 Datacenter Proxy 풀 + 자체 IP 평판 관리로 전환. 자동 Cooldown 자원 관리 알고리즘 + Prometheus / Grafana Health Dashboard. **월 800만 → 90만 원 (88.75% 절감) · 성공률 70% → 98%**.

**⑤ JVM / Spring 자산 빌드 중** — Kotlin / Spring 3-Repo 포트폴리오. ADR 49+ · 실험 47+ · 블로그 17편 발행 (ko + en). 트랜잭션 격리수준 · 분산 락 4종 비교 · 결제 멱등성 4단계 · Single-Flight 5 invariants · Coroutines vs Virtual Thread 모두 [실측]으로 검증.

---

## 경력

### 르몽 (Lemong) — 백엔드 개발자 | 2024.11 ~ 현재

> 6개 배달 플랫폼 통합 리뷰 관리 SaaS **댓글몽 / 댓글몽 Biz** 운영
> 일일 API 호출 **20만+** / 일일 페이지 스크래핑 **100만+** / 일일 리뷰 수집 **12만+** / 플랫폼별 동시 worker **30+**

#### ① 멀티플랫폼 통합 인증 & 세션 유지 시스템

- 배달 플랫폼별 로그인 정책 분석 + **Playwright + Camoufox 스텔스 브라우저** 기반 비동기 로그인 세션 유지 구조 설계
- 8종 LOGIN 분기 (captcha / 2FA / IP 차단 / device verify / password 변경 / account locked / unknown / 정상) **계층형 예외(`ScrapperException`)** 로 관리하여 장애 복원 자동화
- **`SessionLockRegistry` FIFO + lease TTL + watchdog timeout** — 30+ worker 동시 로그인 race 방지 + 공정성 확보
- 세션 만료 자동 감지 → 재로그인 프로세스 + `BeaconConfirmationRepository` 검증
- **세션 유지율 99.2% [실측]**

#### ② 리뷰 Aggregation 비동기 파이프라인

- NestJS + Python + Playwright 기반 비동기 리뷰 파이프라인 — 6 플랫폼 매트릭스 통합 수집
- **일일 100만+ 페이지 스크래핑 · 12만+ 리뷰 데이터 실시간 수집 [실측]** + 정합성 검증
- 5분 단위 무거운 스크래핑 작업을 **RabbitMQ reply-request-reply 패턴**으로 분리 → 사용자 인지 latency 단축
- 댓글 자동화 중복 등록 방지 **4단계 멱등성** — `Idempotency-Key UNIQUE 제약` + 상태머신 (PENDING → CONFIRMED / CANCELLED) + Redis 응답 캐싱 + 일일 reconciliation

#### ③ 댓글몽 Biz — 프랜차이즈 멀티테넌트 구조

- 최대 **1,000개 매장 동시 처리** 멀티테넌트 구조 설계
- 매장별 인증 세션 격리 + **Token Bucket Rate Limiter + Worker Queue** 조합
- 플랫폼별 **sticky session 라우팅** (`StickySessionService`) — 세션 thrashing 회피, 인스턴스 affinity 보장
- **플랫폼 API 차단률 90% 감소 · 리뷰 처리량 6배 향상 [실측]**

#### ④ 마케팅 댓글 예약 비동기 실행 시스템

- AWS Aurora(MySQL 호환) 기반 예약 큐 테이블 설계 — Aurora Consume 구조로 **Message Queue 수준의 비동기 실행** 구현
- Redis Pub/Sub 기반 상태 추적 + 멱등 재시도 (지수 백오프) + Redis pipeline 배치 카운터
- **TPS 1,000/s 이상 · 예약 실패율 1% 이하 · 처리 지연 10초 미만 [실측]**

#### ⑤ PAMS — Proxy Allocate Management System

- 외부 Decodo Residential Proxy 의존을 **Datacenter Proxy 풀 + 자체 IP 평판 관리(Naver IP Reputation)** 시스템으로 전환
- **자동 Cooldown 기반 자원 관리 알고리즘** — 성공률 / 타임아웃 / 응답지연 3 지표 Health 모니터링 + 장애 시 자동 자원 재할당 / 트래픽 재분산
- Naver IP Reputation **sticky pool allocator** — port-IP 매핑 영구화 + S3 부트스트랩 + 세션-IP 평판 추적
- **Proxy 비용 월 800만 → 90만 원 (88.75% 절감) · 성공률 70% → 98% [실측]**
- Prometheus + Grafana Proxy Health Dashboard 구축 (가용성 HA 확보)

#### ⑥ 운영 & 관측 시스템

- **Datadog APM** (dd-trace) 분산 트레이싱 + structured JSON 로깅 (`@nestjs-cls` request context propagation)
- Prometheus + Grafana + Slack Webhook 운영 모니터링 자동화
- ElasticSearch + Kibana 로그 분석 / 장애 트렌드 시각화
- **`@SafeCron` 데코레이터** 자체 구현 — 다중 인스턴스 환경 cron 중복 실행 방지 (Redis 락 + Slack 알림 + 자동 cleanup)
- **운영 대응 시간 70% 단축 · 평균 복구 시간 (MTTR) 5분 이내 [실측]**

---

### 아이브릭스 (I-BRICKS) — 백엔드 개발자 | 2021.05 ~ 2024.11

> 한국어 언어 처리 전문 기업 — 검색 시스템 · 데이터 파이프라인 · 챗봇 개발 담당

#### 식품 E-commerce 서비스 개발 *(Java / Spring Boot)*

- **TossPayments API 통합 결제 시스템** 구축 — Idempotency-Key + 결제 상태머신 적용으로 안정성 향상
- Redis 캐싱 최적화 + **nGrinder 부하 테스트**로 **TPS 330.9 → 370 (12% 개선) [실측]**
- Product GET API 응답시간 **3초 → 0.3초 (10배) [실측]** — N+1 쿼리 제거 + 인덱스 튜닝 + Redis Cache-Aside
- Jenkins + Docker CI/CD 자동화 → 배포 효율성 30% 향상

#### EBS 학습 시스템 데이터 파이프라인 구축

- **Kafka 기반 비동기 메시징**으로 일일 **수천만 건 로깅 데이터** 안정적 수집
- Apache Nifi + Elasticsearch 클러스터링으로 데이터 처리량 **2배 증가 시 안정적 운영**
- 데이터 쿼리 응답 시간 **50% 단축 [실측]**

#### 대법원 챗봇 도우미 *(웹 프론트엔드)*

- React + Redux + SCSS 사용자 중심 UI/UX 구현
- 머신러닝 자연어 처리 성능 50% 향상, 사용자 만족도 30% 증가
- 웹 접근성 기준 (KWCAG2.1) 준수

---

## JVM / Spring 자산 (3-Repo 포트폴리오, 빌드 중)

> Node.js 5년 운영 자산을 Kotlin / Spring 추상 패턴으로 재설계하는 narrative. 매주 ADR 1+ / 실험 1+ 누적.

### ① commerce-comment-platform-be *(Java / Spring Boot / JPA)*

- Stage 0 (트랜잭션 안 외부 호출 풀 고갈 EXP-09 [실측 16.7% 성공]) → Stage 4 (**Outbox + Saga**)
- **ADR-004 분산 락** — Redisson watchdog + Pub/Sub 4종 비교 [실측] (비관락 180ms ⭐ / 낙관락 549ms / GET_LOCK 5,015ms / Redisson 53/100)
- **ADR-006 결제 멱등성 4단계** — 키 + 상태머신 + Redis 응답 캐싱 + reconciliation
- **ADR-007 트랜잭션 격리수준** — MySQL InnoDB RR ≠ ANSI RR 발견
- **ADR-008 트랜잭션 분리 패턴** — 단순분리 / Saga / Outbox 9 시나리오 매트릭스
- **ADR-009 No-offset Pagination** — OFFSET 1M = 171ms 마지막 페이지 폭락 → QuerydslZeroOffset
- **Dirty Checking 5 실험** — Read-Only Transaction / Dynamic Update / Bytecode Enhancement / Identity Lost Update / Service Layer Cache
- **JPA Spring Mastery 8편** (Garcia-Molina 1987 / Helland CIDR 2005·2007 / Vogels 2008 학술 도달)

### ② commerce-batch-orchestrator *(Spring Batch + RabbitMQ → Kafka)*

- **통신 진화 4단계 narrative** [실측] — 단독 → HTTP → RabbitMQ → Kafka
- **ADR-001 Kafka vs RabbitMQ** — Day 1 Kafka 거부 후 RabbitMQ 5가지 한계 [실측]로 전환 정당화 (replay 비용 · prefetch HoL · x-overflow · publisher confirm 실패 · DLQ 운영 비용)
- **ADR-005 Outbox Relay** — polling 5s vs CDC (Debezium) latency 비교
- **Reader 4종 매트릭스** [실측] — JpaPagingItemReader / JdbcCursor / JpaCursor / **QuerydslZeroOffset** (카카오페이 50만건 235s → 47s 재현)

### ③ commerce-external-gateway-kt *(Kotlin / Coroutines / Resilience4j)*

- 운영 자산을 Kotlin 재설계로 reframe — **9종 operation × 3 플랫폼 (REST / GraphQL / Playwright) 매트릭스 27 결합**
- **ADR-002 Coroutines vs Virtual Thread** — supervisorScope 자식 실패 격리 / Flow backpressure (buffer / conflate / sample)
- **Single-Flight 5 invariants** — promise sharing / sync throw normalization / forceRelease / deadline / capacity → **Token Refresh 5번 → 1번 [실측]**
- **9종 에러 카테고리 분류기** — NETWORK_TIMEOUT / EXTERNAL_5XX / EXTERNAL_4XX / AUTH_EXPIRED / RATE_LIMITED / IP_BLOCKED / CAPTCHA_REQUIRED / DATA_INCONSISTENT / UNKNOWN (**GraphQL 200 OK + body.errors 1순위 룰**)
- **Camoufox PID Registry 5 component lifecycle** — 메모리 누수 회피 + Quarantine + Reuse
- **Resilience4j 5종** — CircuitBreaker / Retry / Bulkhead / RateLimiter / TimeLimiter

**누적 자산** : ADR **49+개** · 실험 **47+건** · 블로그 **17편 발행** (ko + en) · OSS PR 진행 중

---

## 기술 스택

| 영역 | 운영 (5년차+) | 자산 빌드 (전환 narrative) |
|------|-------------|---------------------|
| **언어** | TypeScript / JavaScript | **Java / Kotlin** |
| **프레임워크** | NestJS / Node.js / Express | **Spring Boot · Spring Batch · Ktor 평가** |
| **DB** | MySQL 8 / Aurora / Oracle (테스트) | PostgreSQL |
| **Cache / Lock** | Redis (ioredis · 분산 락 · Token Bucket · SessionLock) | **Redisson watchdog · Pub/Sub** |
| **메시징** | RabbitMQ (6 queue · prefetch 튜닝 · DLQ) | **Kafka (마이그레이션 narrative)** |
| **검색 / 로깅** | ElasticSearch · Kibana · Apache Nifi | |
| **외부 의존성 격리** | TimeoutInterceptor · Custom Retry · Strategy Error Handler | **Resilience4j 5종 (CB · Retry · Bulkhead · RL · TL)** |
| **헤드리스 브라우저** | Playwright · Camoufox · playwright-extra · stealth plugin | |
| **부하 / 관측** | Prometheus · Grafana · Datadog APM · nGrinder | k6 · Gatling · OpenTelemetry · Tempo |
| **테스트** | Jest · Testcontainers · E2E · Chaos | **JUnit5 + Kotest · WireMock + Toxiproxy** |
| **인프라** | Docker · AWS ECS · Naver Cloud · Jenkins · GitHub Actions | K8s 평가 · Helm |
| **설계** | RESTful API · 트랜잭션 관리 · Rate Limiting · CI/CD · HA | **DDD · Hexagonal · Port-Adapter · Saga · Outbox · CQRS** |

---

## 교육

**F-lab Java Backend Mentoring** | 2024.01 ~ 2024.07
- Meta 시니어 개발자 멘토링 수료
- 객체지향 설계 · 트랜잭션 처리 · 클린 아키텍처 중심 프로젝트 리뷰
- 동시성 제어 · CQRS · 분산 트랜잭션 심화 학습

**경기대학교 컴퓨터과학과** | 졸업
