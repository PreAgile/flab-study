# 경력기술서 — 김면수

> 5년차+ 백엔드 엔지니어 · 분산 시스템 · 비동기 메시징 · 고성능 데이터 파이프라인
> Node.js / NestJS 운영 (5년) → JVM(Kotlin / Spring) 자산 빌드 중
> **E-mail** digle117@gmail.com · **GitHub** github.com/PreAgile · **Blog** medium.com/@digle117

---

## 목차

1. 르몽 (Lemong) — 댓글몽 / 댓글몽 Biz
   1.1 멀티플랫폼 통합 인증 & 세션 유지
   1.2 리뷰 Aggregation 비동기 파이프라인
   1.3 댓글몽 Biz — 멀티테넌트 구조
   1.4 마케팅 댓글 예약 비동기 실행
   1.5 PAMS — Proxy Allocate Management ⭐
   1.6 운영 & 관측 시스템
2. 아이브릭스 (I-BRICKS)
3. JVM / Spring 자산 narrative
4. 참고 자료

---

## 1. 르몽 (Lemong)  ·  2024.11 ~ 현재

### 서비스 개요

자영업자와 프랜차이즈 본사를 위한 **리뷰 통합 관리 SaaS**. 배달의민족 · 요기요 · 쿠팡이츠 · 네이버 · 땡겨요 · 먹깨비 **6개 플랫폼**의 리뷰 데이터를 통합 수집·분석하고, AI 자동 댓글 + 불만족 리뷰 알림을 제공.

**운영 규모 (일일)** : API 호출 20만+ / 페이지 스크래핑 100만+ / 리뷰 수집 12만+ / 플랫폼별 동시 worker 30+

**시스템 구성**

```
[Client] → [ALB] → [cmong-be (NestJS)] ⇌ [RabbitMQ 6 Queue + DLQ]
                          ↓                        ↓
                    [MySQL/Aurora]          [cmong-scraper-js Worker 30+]
                    [Redis · ES]                   ↓
                                            [PAMS Proxy 풀]
                                                   ↓
                                            [6 외부 플랫폼]
```

---

### 1.1 멀티플랫폼 통합 인증 & 세션 유지

**상황** ─ 6개 플랫폼이 모두 다른 anti-bot · 2FA · captcha 정책을 가짐. worker 30+개가 같은 매장에 동시 로그인 시도 시 IP 평판 차단 + 중복 세션 폭증.

**시도** ─ Playwright + Camoufox 스텔스 브라우저 풀 + **`SessionLockRegistry`** FIFO 큐 + lease TTL 도입. 한 매장의 동시 로그인은 1개만 허용하고 나머지 worker는 세션 재사용. 8종 LOGIN 분기 (정상 / captcha / 2FA / IP차단 / device verify / password 변경 / account locked / unknown)를 계층형 예외 `ScrapperException`으로 일원화.

**핵심 trade-off** ─ *세션 재사용 효율 ↔ 보안 만료 정책*. lease TTL 30분으로 시작 → IP 평판이 떨어지는 패턴 발견 → 플랫폼별 5~60분 차등 적용.

**결과**

| 지표 | 값 |
|------|---|
| **세션 유지율** | **99.2%** [실측] |
| 동시 worker 30+ 환경 중복 로그인 | 0건 |
| 장애 복원 | 자동 (captcha 감지 → PAMS IP rotation) |

---

### 1.2 리뷰 Aggregation 비동기 파이프라인

**상황** ─ 6 플랫폼 × 매장 N개. 무거운 스크래핑 작업이 5분 timeout — 사용자 동기화 요청 시 ALB 502 폭증.

**시도** ─ **RabbitMQ reply-request-reply 패턴** 도입. API는 즉시 202 Accepted + taskId 반환, scraper worker가 큐 prefetch=2로 분산 소비, 완료 시 `REPLY_COMPLETE` 큐로 결과 publish. 댓글 자동화 중복 등록 방지는 **4단계 멱등성** — `Idempotency-Key UNIQUE` 제약 + 상태머신 (PENDING → CONFIRMED / CANCELLED) + Redis 응답 캐싱 + 일일 reconciliation.

**핵심 trade-off** ─ *사용자 인지 latency (ACK) ↔ 처리 완료 latency*. ACK는 100ms 이내, 실제 처리는 최대 5분 — 사용자에겐 polling/푸시 알림으로 처리 상태 노출.

**결과**

| 지표 | 값 |
|------|---|
| **일일 처리** | **페이지 100만+ · 리뷰 12만+** [실측] |
| 5분 timeout | 0건 |
| 결제 webhook 중복 처리 | 0건 (멱등성 4단계) |

---

### 1.3 댓글몽 Biz — 프랜차이즈 멀티테넌트

**상황** ─ 프랜차이즈 본사가 1,000개 매장을 한 화면에서 관리. 매장별 인증 세션이 격리되지 않으면 한 매장 차단이 전체 차단으로 전이.

**시도** ─ 매장별 인증 세션 격리 + **Token Bucket Rate Limiter** (매장별 quota) + Worker Queue 폭주 제어. **`StickySessionService`** sticky session 라우팅으로 한 매장은 한 worker에 affinity 고정 → 세션 thrashing 회피 + 인스턴스 캐시 hit률 상승.

**핵심 trade-off** ─ *worker 풀 효율 ↔ 매장별 격리도*. 완전 격리 시 worker 활용률 하락 → sticky session + 시간대별 dynamic re-allocation으로 절충.

**결과**

| 지표 | 값 |
|------|---|
| **동시 처리 매장** | **1,000개** [실측] |
| 플랫폼 API 차단률 | **90% 감소** |
| 리뷰 처리량 | **6배 향상** [실측] |

---

### 1.4 마케팅 댓글 예약 비동기 실행

**상황** ─ 마케팅 캠페인 시 수만 건 예약 댓글이 동시 트리거. 단순 cron polling으로는 TPS 100/s 부근에서 DB 락 컨텐션 폭증 + 처리 지연 5분+.

**시도** ─ AWS Aurora 기반 예약 큐 테이블 + **Aurora Consume 패턴** (Message Queue 수준의 비동기 실행) + Redis Pub/Sub 상태 추적 + 지수 백오프 멱등 재시도. 카운터는 Redis pipeline 배치로 atomic 집계.

**핵심 trade-off** ─ *Aurora 일관성 ↔ Message Queue 지연*. SELECT FOR UPDATE 분산 처리 + Redis pipeline 배치 카운터로 latency 10초 미만 유지.

**결과**

| 지표 | 값 |
|------|---|
| **TPS** | **1,000/s 이상** [실측] |
| 예약 실패율 | **1% 이하** |
| 처리 지연 | **10초 미만** |

---

### 1.5 PAMS — Proxy Allocate Management System ⭐

**상황** ─ 외부 Decodo Residential Proxy 비용 **월 800만 원**. 트래픽 증가에 따라 비용이 선형 증가 + 평판 관리 불가 + 외부 장애 시 전체 서비스 중단.

**시도** ─ 3가지 동시 진행.

1. **Decodo → 자체 Datacenter Proxy 풀** 전환 (계약 비용 90% 절감)
2. **Naver IP Reputation 시스템** — port-IP 매핑 영구화 + S3 부트스트랩 + 세션-IP 평판 추적. 한 매장은 평판 좋은 sticky IP로 라우팅
3. **자동 Cooldown 알고리즘** — 성공률 / 타임아웃 / 응답지연 3 지표 모니터링 + 장애 IP 자동 격리 + 트래픽 재분산

**핵심 trade-off** ─ *Datacenter IP 평판 (낮음) ↔ 비용*. sticky pool로 한 IP의 평판을 장기 관리하고, 평판 떨어진 IP는 cooldown 후 복귀시켜 풀 규모를 유지.

**결과**

| 지표 | Before | After | 변화 |
|------|:---:|:---:|:---:|
| **월 비용** | 800만 원 | **90만 원** | **-88.75%** |
| **성공률** | 70% | **98%** | **+28%p** |
| 외부 의존 | Decodo 단일 | 자체 풀 + Decodo 보조 | HA 확보 |

Prometheus + Grafana Proxy Health Dashboard로 실시간 가용성 추적, 장애 시 자동 자원 재할당으로 사용자 영향 없이 회복.

---

### 1.6 운영 & 관측 시스템

**상황** ─ 다중 인스턴스 운영 시 cron job 중복 실행, 분산 트랜잭션 컨텍스트 끊김, 장애 추적 어려움.

**시도**
- 자체 **`@SafeCron`** 데코레이터 — Redis 락 + Slack 알림 + 자동 cleanup으로 다중 인스턴스 cron 중복 실행 방지
- `@nestjs-cls/transactional` CLS 컨텍스트로 분산 트랜잭션 일관성 보장
- **Datadog APM (dd-trace)** 분산 트레이싱 + structured JSON 로깅 + Prometheus / Grafana + Slack Webhook 자동 알림 + ElasticSearch / Kibana 로그 분석

**결과** ─ 운영 대응 시간 **70% 단축** · 평균 복구 시간 **MTTR 5분 이내** [실측]

---

## 2. 아이브릭스 (I-BRICKS)  ·  2021.05 ~ 2024.11

> 한국어 언어 처리 전문 기업 — 검색 시스템 · 데이터 파이프라인 · 챗봇 개발 담당

### 2.1 식품 E-commerce 서비스 (Java / Spring Boot)

**상황** ─ TossPayments 통합 결제 시스템 + 트래픽 증가에 따른 API 응답 지연.

**시도** ─ Idempotency-Key + 결제 상태머신으로 안정성 확보. Product GET API 병목 분석 → N+1 쿼리 제거 + 인덱스 튜닝 + Redis Cache-Aside. nGrinder 부하 테스트로 검증.

**결과**

| 지표 | Before | After |
|------|:---:|:---:|
| TPS | 330.9 | **370 (+12%)** [실측] |
| Product GET API 응답시간 | 3초 | **0.3초 (-10배)** [실측] |
| CI/CD 배포 효율성 | 기준 | +30% (Jenkins + Docker) |

### 2.2 EBS 학습 시스템 데이터 파이프라인

**상황** ─ EBS 학습 시스템 로깅 데이터 일일 수천만 건 안정 수집 필요.

**시도** ─ **Kafka 기반 비동기 메시징** + Apache Nifi + Elasticsearch 클러스터링. 데이터 처리량 2배 증가 시나리오 안정성 검증.

**결과** ─ 데이터 쿼리 응답 시간 **50% 단축** · 일일 수천만 건 안정 수집

### 2.3 대법원 챗봇 도우미 (웹 프론트엔드)

React + Redux + SCSS 기반 사용자 중심 UI/UX. 머신러닝 자연어 처리 성능 50% 향상, 사용자 만족도 30% 증가, 웹 접근성 KWCAG2.1 준수.

---

## 3. JVM / Spring 자산 narrative (3-Repo 포트폴리오)

> Node.js 운영 자산을 **Kotlin / Spring 추상 패턴**으로 재설계하는 작업. 매주 ADR 1+ / 실험 1+ 누적.

### 3.1 commerce-comment-platform-be · Java / Spring Boot / JPA

운영 자산의 *결제 멱등성 + 분산 락 + 트랜잭션 분리* 패턴을 JPA / Spring 환경에서 재구성.

- **ADR-004** 분산 락 — Redisson watchdog + Pub/Sub vs 비관락 vs 낙관락 vs GET_LOCK 4종 비교 [실측: 비관락 180ms ⭐ / 낙관락 549ms / GET_LOCK 5,015ms / Redisson 53/100 race 통과율]
- **ADR-006** 결제 멱등성 4단계 — 키 + 상태머신 + Redis 응답 캐싱 + reconciliation
- **ADR-007** 트랜잭션 격리수준 — MySQL InnoDB RR ≠ ANSI RR 발견
- **ADR-008** 트랜잭션 분리 패턴 9 시나리오 매트릭스 (단순분리 / Saga / Outbox)
- **ADR-009** No-offset Pagination — OFFSET 1M 마지막 페이지 폭락 → QuerydslZeroOffset
- **Dirty Checking 5 실험** + **JPA Spring Mastery 8편** (학술 출처 도달)

### 3.2 commerce-batch-orchestrator · Spring Batch + RabbitMQ → Kafka

운영의 RabbitMQ 5가지 한계 [실측]를 측정한 후 Kafka 전환을 정당화하는 narrative.

- **ADR-001** Kafka vs RabbitMQ — Day 1 Kafka 거부 → RabbitMQ 1주 운영 측정 → 한계 5가지 (replay 비용 / prefetch HoL / x-overflow / publisher confirm 실패 / DLQ 운영 비용) 정량화 후 Kafka 전환
- **ADR-005** Outbox Relay — polling 5s vs CDC (Debezium) latency 비교
- **Reader 4종 매트릭스** — JpaPagingItemReader / JdbcCursor / JpaCursor / **QuerydslZeroOffset** (카카오페이 235s → 47s 재현)

### 3.3 commerce-external-gateway-kt · Kotlin / Coroutines / Resilience4j

운영의 *외부 게이트웨이 + 세션 + 에러 분류* 자산을 Kotlin Coroutines로 reframe.

- **ADR-002** Coroutines vs Virtual Thread — supervisorScope / Flow backpressure
- **Single-Flight 5 invariants** — Token Refresh 5번 → 1번 [실측]
- **9종 에러 카테고리 분류기** (GraphQL 200 OK + body.errors 1순위 룰)
- **Resilience4j 5종** — CircuitBreaker / Retry / Bulkhead / RateLimiter / TimeLimiter
- **Camoufox PID Registry 5 component lifecycle** — 헤드리스 OOM 회피 ↔ JVM Heap/GC 동형성 narrative

**누적 자산** : ADR **49+** · 실험 **47+** · 블로그 **17편 발행** (ko + en)

---

## 4. 참고 자료

- **GitHub** : github.com/PreAgile
- **Blog** : medium.com/@digle117
- **Portfolio Docs** (3-Repo + ADR + 실험 인덱스) : [공개 URL 채우기]
- **메타 블로그 4편 (예정)** : 헤드리스 OOM ↔ JVM Heap/GC 동형성 / RabbitMQ → Kafka 운영자 회고 / Resilience4j 임계값 결정기 / JPA N+1 정면돌파
