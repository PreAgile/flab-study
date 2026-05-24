# 김면수 ｜ Backend Engineer

**📞 연락처** 010-9101-5429  **｜ ✉ 이메일** [digle117@gmail.com](mailto:digle117@gmail.com)  **｜ 💻 GitHub** [github.com/PreAgile](https://github.com/PreAgile)  **｜ 📝 기술 블로그** [astro-paper-23v.pages.dev](https://astro-paper-23v.pages.dev)

---

## 자기소개

**결제 정합성 · 대량 작업 처리 · 외부 의존성 격리** 를 중심으로 운영 시스템을 설계해 온 5년차 백엔드 엔지니어입니다. NestJS 기반 SaaS 운영에서 직접 부딪힌 멱등성 · 트랜잭션 · 분산 락 · 작업 큐 · 회로 차단 패턴을 **Java/Kotlin/Spring** 환경으로 재설계하며 JVM 백엔드 역량을 확장하고 있습니다. 각 설계 결정의 근거를 ADR(Architecture Decision Record)과 PR 본문에 남기는 습관을 유지합니다.

현재 르몽에서 6개 외부 플랫폼을 통합하는 리뷰 SaaS 의 백엔드를 담당하고 있으며, **일평균 API 호출 20만 · 페이지 스크래핑 100만 · 리뷰 수집 12만** 규모의 운영 트래픽 위에서 결정·측정·검증을 반복합니다. **Kotest organization 정식 멤버**(6 PR 머지), **LINE Armeria** (1 PR 머지), **Spring Batch · Spring Cloud Gateway** 이슈 분석 진행 중.

---

## 핵심 운영 지표

| 영역 | Before → After | 근거 |
|---|---|---|
| 프록시 풀 비용 | **월 800만 → 90만 원 (88.75% ↓)** | 자체 IP 평판 시스템, 운영 청구서 기준 |
| 외부 플랫폼 요청 성공률 | **70% → 98%** | 운영 대시보드 기준 |
| 세션 유지율 (최근 6개월) | **99.2%** | 세션 락 레지스트리 FIFO + lease TTL |
| 댓글 등록 중복 사고 | **0건 / 6개월** | Idempotency-Key + 세션 락 조합 |
| 멀티 인스턴스 webhook race | **검출 + 차단** | 운영 로그 「중복 웹훅 락 차단」 정기 검출 |

> 「운영 실측」 = 운영 로그 / 대시보드 기준 · 「재설계 실험」 = JVM/Spring 재설계 프로젝트의 실험실 측정. 본문에 두 범주를 구분해서 표기합니다.

---

## 기술 스택

**Production** — 운영 시스템에서 직접 다룬 스택

- TypeScript · NestJS · Node.js · TypeORM
- MySQL / Aurora · PostgreSQL · Redis (Cluster · Lua · 분산 락 · Token Bucket)
- RabbitMQ (Quorum Queue · DLX) · 메시지 큐 application-level retry
- Docker · Docker Compose · Traefik 동적 라우팅 · AWS ECS · 물리서버 도커 분할
- Prometheus · Grafana · APM (span tagging) · Slack Webhook · JFR

**JVM / Spring Re-design** — 재설계 프로젝트에서 재현·검증한 스택

- Java · Kotlin · Spring Boot · Spring Batch · JPA · QueryDSL
- Redisson · Resilience4j (Circuit Breaker · Retry · Bulkhead · RateLimiter · TimeLimiter)
- Kafka (Outbox · CDC · Consumer Group) · ShedLock · OAuth2

**Evidence** — 측정·테스트·검증 도구

- Testcontainers · JUnit 5 · Kotest · Pytest · Jest · nGrinder
- Kotest organization 멤버 · Armeria 머지 · Spring Batch 이슈 분석

---

## 오픈소스 기여

JVM 생태계 오픈소스에 정기 기여 — **머지 7 · 이슈 분석 + PR 준비 다수**.

### [Kotest](https://github.com/kotest/kotest) — Kotlin 멀티플랫폼 테스트 프레임워크 (4.7k stars)

2026.03 메인테이너 sksamuel 의 직접 초대로 **organization 정식 멤버**, 한 달간 6 PR 머지.

- 타입 안전 Test Metadata Public API 신규 설계 (+355/-16, 5 리뷰 16h 내 머지) — [issue #5103](https://github.com/kotest/kotest/issues/5103), [PR #5905](https://github.com/kotest/kotest/pull/5905)
- 컬렉션 data class 필드 단위 diff — [issue #2545](https://github.com/kotest/kotest/issues/2545), [PR #5835](https://github.com/kotest/kotest/pull/5835)
- JSON Schema anyOf / oneOf 표준 구현 — [issue #4463](https://github.com/kotest/kotest/issues/4463), [PR #5807](https://github.com/kotest/kotest/pull/5807)
- JSON Matchers 커스텀 Json 인스턴스 지원 — [issue #4601](https://github.com/kotest/kotest/issues/4601), [PR #5795](https://github.com/kotest/kotest/pull/5795)
- `@OnlyInputTypes` 활용 타입 안전 어설션 — [issue #5589](https://github.com/kotest/kotest/issues/5589), [PR #5789](https://github.com/kotest/kotest/pull/5789)
- `shouldHaveSingleElement` 어설션 체이닝 — [issue #5755](https://github.com/kotest/kotest/issues/5755), [PR #5756](https://github.com/kotest/kotest/pull/5756)

### [Armeria](https://github.com/line/armeria) — LINE 의 Java 기반 비동기 RPC 프레임워크 (5.1k stars)

- `RequestContextExporter` BuiltInProperty 확장 + Logback MDC export 테스트 보강 (+339/-5, **MERGED** 2026.04) — [issue #4403](https://github.com/line/armeria/issues/4403), [PR #6683](https://github.com/line/armeria/pull/6683)

### [Spring Batch](https://github.com/spring-projects/spring-batch) — Spring 의 대량 배치 처리 프레임워크 (2.9k stars)

이슈 분석 완료, PR 작성 중.

- fault-tolerant step chunk scanning 공식 문서 4년 누락 보완 — [issue #3946](https://github.com/spring-projects/spring-batch/issues/3946) (메인테이너 "documentation issue" 라벨 부여)
- conditional flow decider order 버그 — [issue #4478](https://github.com/spring-projects/spring-batch/issues/4478) (메인테이너 "this is a bug" 인정)

### [Spring Cloud Gateway](https://github.com/spring-cloud/spring-cloud-gateway) — Spring 의 reactive API gateway

이슈 분석 완료, 5.1.x 릴리즈 사이클 대기.

- Apache HttpClient5 쿠키 매니저 기본 비활성화 — [issue #3311](https://github.com/spring-cloud/spring-cloud-gateway/issues/3311) (메인테이너 코멘트 + 구현 준비)
- API Versioning Predicates 공식 문서 보완 — [issue #4024](https://github.com/spring-cloud/spring-cloud-gateway/issues/4024) (머지 가능성 메인테이너 확인)

---

## 경력 — 르몽(Lemong) ｜ 백엔드 엔지니어 ｜ 2024.11 ~ 현재

### 시스템 개요

자영업자와 프랜차이즈 본사를 위한 리뷰 통합 관리 SaaS 「댓글몽 / 댓글몽 Biz」 의 백엔드를 담당합니다. 4 책임 도메인 (메인 API · 배치 워커 · 운영 콘솔 · 스크래퍼 워커) 으로 분리되어 있으며, 메시지 큐 · 분산 캐시 (Cluster) · 관계형 DB · 컨테이너 오케스트레이션 위에 올라가 있습니다.

![전체 시스템 아키텍처](diagrams/A1_system_overview.svg)

본문은 5 개 핵심 사례 + 보조 운영 사례 한 줄 요약 + 별도 JVM/Spring 재설계 프로젝트 섹션으로 구성합니다.

---

### 결제 멱등성 + 정합성 reconciliation — 멀티 인스턴스 환경에서 「한 번만 처리」 보장

![결제 webhook 4중 멱등성 + 정합성 reconciliation](diagrams/A2_payment_webhook_4layer.svg)

**문제** — 결제 PG webhook 이 같은 결제 식별자로 **중복 호출되는 경로 5종**.

- PG 자체 retry (5xx / timeout)
- 정기결제 schedule 1차 실패 후 fallback retry → PAID / FAILED 거의 동시 도착
- 결제 취소 후 재결제 · 부분 환불 상태 전이
- Load Balancer keep-alive 재시도

단순 INSERT 시 결제 row 이중 집계 → 매출 중복 → 알림톡 2회 발송 → 정기결제 중복 생성 → 다음 달 이중 과금 도미노. 멀티 인스턴스 배포라 in-memory dedupe 불가, ORM 의 `findOne → save` 패턴은 read-modify-write 사이에 race window, 분산 캐시 락 단독으로는 TTL 만료 후 ABA 문제 (Martin Kleppmann Redlock 분석에서 지적), DB UNIQUE 단독으로는 PG retry 폭주를 1차 차단 불가.

추가로 webhook 4중 멱등성으로도 못 막는 사후 정합성 결함이 누적됩니다 — 외부 PG 와 DB 의 source of truth 가 분리되어 있어 좀비 schedule (PG 살아있음 + DB cancel), 중복 빌링키, admin override orphan 케이스가 사용자 클레임 / 환불 분쟁 발생 후에야 노출됩니다.

**해결** — 「락 / DB / 상태머신 / 원자 해제」 4중 방어 + 일일 reconciliation cron 의 사후 탐지.

4중 멱등성 (운영 실측):

1. **분산 락 (ABA-safe)** — 분산 캐시 `SETNX EX 30s` + 토큰 lock value. Stripe Idempotency Key 디자인과 동일하게 lock value 로 ownership 검증
2. **DB UNIQUE** — 복합 키 `imp_uid + merchant_uid + status` · 1시간 dedupe window · 캐시 fail-open 되어도 최종 차단
3. **상태머신** — `READY → PAID / FAILED / CANCELLED × action_type` 분기 · 상태 역전 (PAID 뒤 FAILED 도착) 시 다른 row 로 격리
4. **Lua 원자 해제** — `GET → 비교 → DEL` 한 트랜잭션 · 자기 토큰일 때만 해제, TTL 만료 후 ABA 차단

일일 reconciliation cron — 3종 inconsistency 자동 탐지:

- **좀비 schedule** — DB 차집합으로 의심 K << N 압축 후 외부 PG `getSchedulesByBillingKey` 호출 → 응답 4-way 분기 자동 정정
- **중복 빌링키** — `GROUP BY user_id HAVING COUNT > 1` 단일 SQL
- **admin override orphan** — `active.end_date > scheduled.schedule_at + 1month` 조건 4단 JOIN SQL

쿠폰 멱등성도 같은 패턴 — 사전 검증 (`findOne((user, coupon))` idempotent return) · 트랜잭션 (`QueryRunner` 명시적) · schedule 등록 직전 `amountWithUserCoupons` fallback 보정.

**성과 (운영 실측)**

- 운영 로그 「중복 웹훅 락 차단: merchant_uid=...」 메시지 정기 검출 — race 발생 + 차단됨이 데이터로 입증
- 같은 SETNX + Lua DEL helper 가 결제 외 8 곳 이상 흐름 (promotional upgrade · change plan · verify code · 알림 배치) 에서 공통 helper 로 재사용
- 매일 09:10 KST 정합성 상태가 Slack 한 메시지로 운영자에게 전달 — 사후 환불 / CS 부담을 사전 탐지로 전환
- 쿠폰 중복 발급 0건 (UNIQUE + findOne 곱셈 결합), 쿠폰 수정 중 부분 update 사고 0건

**역할 범위** — 4중 멱등성 + reconciliation cron 설계 · 구현 · 운영 모니터링 (Slack 자동 경고 채널 구축) 전 단계 단독 담당.

**Spring 매핑** — `@Transactional` propagation · Redisson watchdog · JPA `@Version` `OptimisticLockException` · `ER_DUP_ENTRY` → `@RestControllerAdvice` · ShedLock cron · QueryDSL 차집합 (재설계 프로젝트 [commerce-comment-platform-be](https://github.com/PreAgile/commerce-comment-platform-be) 에서 동일 시나리오 재현)

---

### 대량 작업 처리 — DB 를 큐로 쓰는 CAS + RabbitMQ 분리 진화

![관계형 DB 작업 큐 + Hierarchical 동시성](diagrams/B1_rds_queue_cas.svg)

**문제** — 대량 비동기 작업을 두 가지 형태로 운영합니다.

- **외부 플랫폼 댓글 등록 (한 건 ≈ 3~5분 IO)** — 사용자가 「100~1,000건 일괄 댓글」 트리거. HTTP 동기 처리 시 Load Balancer 5분 타임아웃 초과, 단일 인스턴스 in-memory queue 는 재배포 시 작업 유실, 같은 사용자 같은 플랫폼 계정으로 worker 2개가 동시 로그인 시 외부 플랫폼 봇 탐지 → 그 계정 전체 차단
- **2시간 cron 리뷰 수집** — 단일 플랫폼 1회 실행 기준 **13,127 매장 / 5,719 계정 그룹 / 13,699 task** 처리. 외부 플랫폼은 같은 계정 동시 다중 호출 시 captcha / 지역차단 / 세션 무효화. 매장 단위 ThreadPool 로 전부 동시 처리는 동일 계정 병렬 로그인 = 세션 충돌, 전부 순차는 11시간 → 2시간 cron 안에 못 끝남

외부 메시지 큐는 fire-and-forget 에 최적이라 stateful 관리·취소·예약·진행률 폴링에 부적합. BullMQ 같은 외부 큐 미들웨어는 트랜잭션과 묶기 어려움.

**해결** — 두 축으로 풀었습니다.

(a) **관계형 DB 를 큐로 사용 (CAS 픽업)** — 트랜잭션과 큐 책임을 한 곳에 묶음. 다중 워커 안전 픽업은 `updated_at` 을 version 필드로 쓰는 ORM 낙관락 = CAS (Compare-And-Set) SQL 버전. `affected = 0` 이면 다른 인스턴스가 먼저 가져갔음을 인식. 같은 플랫폼 계정 동시 사용은 픽업 SQL 에 `platform_id NOT IN (실행 중 집합)` 조건으로 차단.

(b) **계정 단위 순차 / 계정 사이 병렬 의 hierarchical 동시성** — `(platform_id, password)` 키로 매장 그룹화 → ThreadPool 에 그룹 단위 제출. 한 그룹은 한 worker thread 가 처음부터 끝까지 순차 처리. 첫 매장 인증 에러 시 `_deactivate_shops` 로 그룹 전체 즉시 차단 (회로 차단 패턴) — 봇 탐지 가속 회피.

**진화 (현재 계획 중)** — 운영 트래픽이 커지면서 정합성 사례 누적과 AAS 세션 부담을 발견 → **RabbitMQ 로 분리하는 마이그레이션** 진행 중. 댓글 예약 / 댓글 등록 같은 stateful 작업과 fire-and-forget 작업을 책임 단위로 나누어, DB 는 작업 상태의 source of truth 로 두고 큐는 fan-out 만 담당하도록 책임 재분할.

**성과 (운영 실측)**

- 동시 처리 워커 최대 30, 같은 그룹 내 순차 + 다른 그룹 병렬로 처리량 극대화
- 운영 로그 `Job N modified by another instance (optimistic lock failed)` 정기 검출 — race 발생하나 차단됨이 데이터로 입증
- 외부 플랫폼 중복 댓글 0건, 인스턴스 재배포 무중단
- 단일 플랫폼 13,127 매장 2시간 cron 안에 완료, 동일 platform_id 동시 호출 0건
- 인증 에러 발생 그룹만 비활성 · 다른 그룹 정상 진행 (장애 격리)

**역할 범위** — RDS Queue 설계 / 픽업 SQL CAS 구현 / 좀비 작업 자동 복구 (부팅 시 재스케줄 + health check) 단독 설계. hierarchical 동시성 모델 + 회로 차단 임계치 dict 도입. 현재 RabbitMQ 분리 마이그레이션 ADR 작성 중.

**Spring 매핑** — JPA `@Version` 낙관락 + `OptimisticLockException` (CAS) · Spring Batch + ShedLock + QuerydslZeroOffset Reader · Resilience4j Bulkhead.semaphore (계정 단위 동시성) + CircuitBreaker (도미노 차단) · Kafka Outbox / Consumer 멱등 + DLQ (재설계 프로젝트 [commerce-batch-orchestrator](https://github.com/PreAgile/commerce-batch-orchestrator) 에서 RabbitMQ↔Kafka 정량 비교)

---

### 외부 의존성 격리 + 세션 안정성 — 30+ 워커 동시 로그인 race · 외부 플랫폼 가용성 복원

![세션 락 레지스트리 + Cold-Start Guard](diagrams/C1_session_lock_registry.svg)

**문제** — 30+ worker 가 같은 외부 플랫폼 세션을 동시에 잡으려 하는 race + 외부 플랫폼의 봇 보호 시스템이 헤드리스 브라우저를 차단하는 두 가지 외부 의존성 문제가 결합되어 있습니다.

세션 race:

- 같은 세션 두 page 동시 navigation = 헤드리스 브라우저 `execution context destroyed`
- 같은 매장 동시 로그인 두 번 = 외부 플랫폼 IP 평판 영구 차단 (1~24시간 그 매장 작업 전체 실패)
- 헤드리스 브라우저 1 인스턴스 ≈ 1GB+, launch 5~10초 — race 시 메모리·런타임 N배 폭증
- 분산 캐시 Cluster 모드는 같은 트랜잭션 여러 키 사용 시 CROSSSLOT
- 가장 까다로운 hazard: **cold-start deadlock** — 인스턴스가 죽었다 살아나면 in-memory Map 은 비어있는데 분산 캐시 큐 head 는 옛 인스턴스 requestId. 살아난 worker 는 그 head 차례를 기다리지만 옛 worker 는 죽어서 영원히 release 안 됨

외부 플랫폼 가용성:

- 일부 외부 플랫폼은 봇 보호 시스템이 평범한 헤드리스 브라우저를 99% 차단
- 보호 시스템의 인증 쿠키가 pending → verified → blocked 의 상태 머신을 가지며, 옛 구현은 4 가지 silent 결함으로 검증 실패를 password retry 로 잘못 흘려보냄

**해결** — 두 축의 해결책을 합성한 「외부 의존성 격리 + 외부 플랫폼 가용성 복원」 패턴.

(a) **세션 락 레지스트리 — 4 layer 직렬화**:

- FIFO 큐 (분산 캐시 LIST) · per-request lease (90s TTL · 5s 갱신)
- **Instance-aware lease value** = `{instanceId-UUID} : {timestamp}` (Martin Kleppmann fencing token 패턴 단순화 — cross-instance ownership 검증을 lease-level 에서)
- Handoff pattern (release 시 다음 큐 entry 가 같은 세션 재사용)
- 안전망 3종 — `forceRelease` (운영 kill switch) · `forceTerminate` (activeCount 강제 0) · `evictStaleHead` (2s 주기 stale head LREM)
- 분산 캐시 Cluster CROSSSLOT — queue 는 단일 키 분리 (부하 분산 우선), 평판 모듈은 hash tag `{pool}` (트랜잭션 묶음 우선) 으로 모듈별 의도된 정책 분기

(b) **외부 플랫폼 가용성 복원 — 인증 흐름 안정화**:

- 인증 쿠키 4-state 상태머신 (`초기 / 검증 / challenge / 차단`) — 우선순위 「차단 > challenge > 검증 > 초기」 명문화로 옛 구현의 4 가지 silent 결함을 모두 차단
- 정책 분기를 service 와 spec 의 SSOT 순수 함수로 추출 (discriminated union 반환)
- Referrer Warming — 메인 URL 거쳐 referrer chain 형성, 15초 human-like mouse jitter 유지 → sensor telemetry 누적 → 쿠키 검증 진입
- 차단 검출 helper 를 main loginResult / Quick Retry / Prewarm Swap 3 경로에서 일관 호출 (silent 회귀 방지)

**성과 (운영 실측 · 최근 6개월)**

- 세션 유지율 **99.2%**, 동일 매장 동시 로그인 **0건**
- 댓글 등록 중복 **0건**, `execution context destroyed` 사고 **0건**
- 인스턴스 재시작 후 dead-letter 누수 **0건** (cold-start guard 효과)
- CROSSSLOT 에러 **0건** (hash tag / 단일 키 분리 정책 일관 적용)
- 외부 플랫폼 로그인 성공률 **77.8% → 100%** (Referrer Warming 패치 · 18/18 iter 측정 입증 · PR 본문에 iter × worker 측정값 박는 검증 형식이 팀 관행으로 자리잡음)

**역할 범위** — 세션 락 레지스트리 (4 layer + 안전망 3종) 설계 · 구현 · 운영. 인증 쿠키 상태머신 정책 분기 spec / service SSOT 분리 리팩토링.

**Spring 매핑** — Redisson `RFairLock` (FIFO + lease auto-extend) · Kotlin Coroutines `Mutex.withLock` per-key in-process layer · sealed class 로 인증 쿠키 상태 discriminated union · Resilience4j Bulkhead 외부 의존성별 풀 분리 (재설계 프로젝트 [commerce-external-gateway-kt](https://github.com/PreAgile/commerce-external-gateway-kt) 에서 7 가지 행동 계약 spec 으로 명문화)

---

### 자체 IP 평판 시스템 — 외부 의존 제거 + 비용 88.75% 절감

![자체 IP 평판 시스템 Before / After](diagrams/C2_proxy_pool_before_after.svg)

**문제** — 외부 Residential 프록시 단일 의존으로 비용 · SPOF · 평판 측정의 세 축이 누적되어 있었습니다.

- **비용 / SPOF** — 매월 800 만 원 · 외부 벤더 장애 = 서비스 중단
- **Identifier 불일치** — Datacenter 프록시는 port 별로 IP 가 시간에 따라 바뀜 → 평판 측정 단위 (IP) 와 stable identifier (port) 가 어긋남
- **Cluster CROSSSLOT** — 평판 카운터 · STREAM · blocklist 를 한 MULTI/EXEC 에 묶을 때 슬롯 분산
- **port rotation 회피** — 차단 IP 가 다음에 다른 port 에 mapping 되면 그 port 가 영구 blocklist 를 우회

**해결** — 6개월 14 phase phased rollout. 한 번의 큰 배포가 아니라 각 phase 머지 → 측정 → 안전 확인 → 다음 phase 의 점진적 cutover.

핵심 결정 4가지:

- **port↔IP 매핑 3중 저장** (In-memory Map + 분산 캐시 HASH + 관계형 DB + 외부 스토리지 부트스트랩 manifest) — 클러스터 cold start 시 외부 의존 없이 복구
- **이중 blocklist** — `port_set` + `ip_set`. allocator 가 port 선정 후 IP lookup → `ip_set` hit 시 그 port 도 자동 `port_set` 추가. port rotation 회피 hazard 차단
- **Adaptive Cooldown** — 5종 outcome (success / block / timeout / networkError / authError / siteChange / unknownError) × consecutiveFailures × latency 가중치로 health 점수, Shadow mode 로 실 운영 영향 없이 결정 측정
- **Pool exhausted → legacy fallback** — `NaverIspPoolExhaustedError` throw → legacy path 위임, legacy 도 `selectPortRespectingBlocklist` 로 차단 IP skip

운영 절차도 AGENTS.md 에 명문화 — env value 빈 값 · 미설정 · deprecated alias 까지 모든 경로 default 정책 명시. fallback 선정 로직은 **외부 AI 코드 리뷰 3회 follow-up** 으로 정밀화한 흔적이 PR 본문에 남아있습니다.

**성과 (운영 실측)**

- 월 비용 **800만 → 90만 원 (88.75% 절감)** — 운영 청구서 기준
- 요청 성공률 **70% → 98%** — 프록시 전환 후 운영 대시보드
- 외부 벤더 SPOF 제거 (HA 보조 풀로 잔존), 메트릭 대시보드 구축
- 차단 IP 가 legacy 경로로 재할당되는 사고 **0건**
- CROSSSLOT 에러 **0건** — hash tag `{pool}` 도입 후

**역할 범위** — 14 phase phased rollout 의 phase 별 ADR 작성 · 구현 · 측정 · 운영 절차 문서화 단독 담당. 외부 AI 코드 리뷰 follow-up 통합.

**Spring 매핑** — Spring Cloud Gateway + Resilience4j `Retry` / `CircuitBreaker` / `Bulkhead` 합성 · WebClient ExchangeFilterFunction 으로 proxy resolver 추상화 · `@ConfigurationProperties` + `@Validated` 로 env 정책 (재설계 프로젝트 [commerce-external-gateway-kt](https://github.com/PreAgile/commerce-external-gateway-kt))

---

### BIZ 대시보드 — 2단계 쿼리 + SQL VIEW + 외부 IO 응답 경로 제외

![BIZ 대시보드 2단계 쿼리 + SQL VIEW SSOT](diagrams/B3_dashboard_2step_query.svg)

**문제** — 프랜차이즈 본사 1명이 산하 1,000매장을 한 화면에서 봅니다.

한 응답에 담아야 하는 것: 매장별 최근 7일 일별 주문, 광고 ROAS / 클릭 / 전환, 일 매출 7일, 크롤링 지연 (stale) 표시, 브랜드 메타.

- 단순 JOIN 한 방 — brand → ... → orders 까지 끌면 카디널리티 폭발 (1,000 × 7 × 매장당 N)
- 외부 광고 / 매출 IO 가 응답 경로에 끼면 응답 지연 누적
- ORM 표현력으로 4단 조인 + dynamic where + order by + LIMIT 조합 유지보수 어려움

**해결** — 「N+1 과 단일 거대 JOIN 사이의 sweet spot 인 2 단계 batch select」 + 「SQL VIEW 를 정의 SSOT 로」 + 「외부 IO 는 응답 경로 밖으로」 의 3 축.

- **Step 1** — shop 목록만 추리기 (`brand × brand_user × shop × brand_shop` 4단 조인 · `LIMIT %s+1 OFFSET %s` has_more 트릭으로 DB-level pagination)
- **Step 2** — 추린 20 shop_ids 에 대해서만 orders GROUP BY → 140 행 (20 × 7) 카디널리티 통제
- 매장 4상태 분류 (`active / inactive / shop_deleted / brand_removed`) — 본사 운영자가 「주문 0인 이유」 즉시 식별
- stale 매장 판정은 SQL VIEW (`v_shop_crawling_status`) 로 두어 메인 API · 어드민 ad-hoc · BI 도구가 같은 정의 공유 (single source of truth)
- 광고 / 매출은 별도 daily upsert + 4상태 머신 (`SUCCESS / PLATFORM_FAILED / SCRAPER_FAILED / FAILED`) — 본사 화면은 적재된 테이블만 read

**성과 (운영 실측)**

- 1,000 × 7 = 7,000 행 폭발 → **140 행 (98% 감소)** 으로 카디널리티 통제
- 응답 경로 외부 IO **0건** · p99 latency 안정
- VIEW 기반 정의 공유 — stale 정책 변경 시 SQL 한 곳만 수정
- 광고 15시간 컷 + 매출 idempotent re-fetch 로 외부 호출량 절감

**역할 범위** — 2단계 batch select 설계 · VIEW SSOT 도입 · 4상태 머신 ADR 작성 단독 담당.

**Spring 매핑** — Spring Data JPA + QueryDSL 동적 조건 · `@Subselect` SQL VIEW 매핑 · `@EntityGraph` N+1 회피 · `Cursor` 복합키 페이지네이션 (재설계 프로젝트 [commerce-comment-platform-be](https://github.com/PreAgile/commerce-comment-platform-be))

---

### 보조 운영 사례 — 한 줄 요약

위 5개 핵심 사례 외에 직접 설계·구현한 운영 패턴 (각각의 상세는 면접 / 포트폴리오에서):

- **Single-Flight Coordinator** — Hexagonal Architecture (Port-Adapter) + Decorator 5종 합성. 한 사용자 동시 N 요청 → 첫 번째만 실제 로그인, 나머지는 결과 공유. 행동 계약 7가지를 spec 헤더에 명문화. 인라인 80+ 줄 제거 · 22 new unit spec.
- **SafeCron 데코레이터** — 멀티 인스턴스 cron 중복 실행 차단. NestJS DI 우회 (`setModuleRef`) 트릭으로 한 줄 데코레이터에 분산 락 + Slack 표준화 + 환경변수 토글 통합. 14곳 적용.
- **매장 일괄 등록** — 본사 1,000+ 매장 엑셀 등록. `SELECT FOR UPDATE` 비관락 + 그룹 단위 트랜잭션 경계 (`@Transactional`). 부분 성공 / 실패 row 단위 추적.
- **고사양 헤드리스 브라우저 워크로드** — 200+ 워커가 자원 부담이 차원이 다름 (1 워커 ≈ 1GB+ RAM). 클라우드 비용 폭증 + 데이터센터 ASN 봇 탐지를 피하기 위해 **물리서버 32 코어 / 512 GB RAM 에 도커 8 분할 운영**. Traefik 동적 라우팅 + 5-step 무중단 재시작 파이프라인.
- **자동 답글 종단 파이프라인** — 수집 → AI → TOCTOU 4 게이트 → API Key/JWT 이중 인증 게시. 트랜잭션 경계 분리 + Layered Idempotency 책임 분담.
- **부정 리뷰 탐지** — 6 신호 노이즈 필터 (Shannon 엔트로피 · zlib 압축률 · n-gram · 이모지 run) + 길이 가중치 (Bell + Polarity Amplification + tanh box) + 별점·스코어 OR 분류.

---

## JVM/Spring 재설계 프로젝트 — Node.js 운영 자산을 Java/Kotlin/Spring 으로 재현

5년 동안 Node.js / NestJS 로 운영하며 직접 부딪힌 **분산 락 · 결제 멱등성 · 트랜잭션 분리 · 외부 의존성 격리** 문제를 Java/Kotlin/Spring 환경에서 동일한 시나리오로 다시 풀어보고, 결정 과정을 **ADR (Architecture Decision Record — 설계 결정과 그 근거 · 대안 · 결과를 코드 저장소에 함께 박는 문서)** 로 남기는 프로젝트입니다.

> 운영 문제는 NestJS 환경에서 직접 겪었고, 동일 문제를 Java/Kotlin/Spring/JPA 환경에서 재현하며 ADR 과 실험으로 검증했습니다.

현재까지 **ADR 49건 · 실험 47건 · 기술 블로그 17편** 누적 (재설계 실험 — 운영 실측과 구분).

### [commerce-comment-platform-be](https://github.com/PreAgile/commerce-comment-platform-be) — 결제 도메인 (Java / Spring Boot / JPA)

- Stage 0 (raw JDBC) → Stage 5 (DDD / MSA) 진화 · Lombok 금지 · record / sealed 적극 · OSIV=false
- **ADR-006 결제 멱등성 4단계** — `idempotency_key` 테이블 + 4 상태머신 + Redis SETNX 1차 + DB UNIQUE 진실의 원천 + 일 1회 reconciliation 4중 안전망 (Stripe / 토스 패턴)
- **ADR-004 분산 락** — Redisson watchdog vs SET NX+Lua 비교 후 Redisson 채택
- **ADR-BE-007 격리수준** — REPEATABLE READ 기본 + RC 명시 (EXP-06 4 격리수준 phantom 실측)
- **ADR-BE-008 트랜잭션 경계** — 외부 호출이 저장 결정에 관여할 때 분리 (EXP-09b 9 시나리오 풀 고갈 실측)
- **ADR-BE-009 No-Offset Pagination** — Cursor 복합키 · row constructor 함정 회피 (EXP-07 1M OFFSET 171ms → Cursor)
- **핵심 실험** — EXP-02 락 4종 GET_LOCK 트랩 검출, EXP-03 `@Version` 만으론 silent Lost Update 74건 / OptLockEx 86건 실측, EXP-04 N+1 4-depth 121 prepStmt → JOIN FETCH 1, EXP-13 dirty checking 132x readOnly 격차, EXP-14 IDENTITY=saveAll batch 비활성 트랩

### [commerce-batch-orchestrator](https://github.com/PreAgile/commerce-batch-orchestrator) — 배치 / Kafka / Outbox

- **ADR-005 Outbox 폴링 → Debezium CDC 진화** — Dual-Write 함정 해결
- **ADR-MQ-006 RabbitMQ vs Kafka 정면 비교** — RabbitMQ classic queue replay 불가 · HOL blocking · Consumer Group 부재 한계 정량화 후 Kafka 메인 + RabbitMQ 잔존
- **ADR-MQ-007 Spring Batch Reader 4종 비교** — `QuerydslZeroOffsetItemReader` 채택
- **ADR-MQ-008 Consumer 멱등 + DLQ + retry topic** — At-least-once + 멱등 = Effectively-Once
- **ADR-MQ-009 CooperativeStickyAssignor (KIP-429)** — Rebalance stop-the-world 회피
- **핵심 실험** — E-MQ-01 Direct publish 유실 → E-MQ-02 Outbox 폴링 → E-MQ-03 Debezium CDC, E-MQ-04~07 Reader 4종 100만 row 비교, E-MQ-08/09 RabbitMQ ↔ Kafka throughput, E-MQ-10 Eager vs Cooperative Sticky rebalance 폭풍

> 르몽의 RabbitMQ 분리 마이그레이션 계획이 이 프로젝트의 ADR-MQ-006 정량 비교와 직접 연결됩니다.

### [commerce-external-gateway-kt](https://github.com/PreAgile/commerce-external-gateway-kt) — 외부 게이트웨이 (Kotlin / Coroutines / Resilience4j)

- **ADR-002 Coroutines vs Virtual Threads** — Coroutines 채택 (구조적 동시성)
- **ADR-007 Circuit Breaker 임계값** — 50% / 70% / 90% 측정 후 70% 채택 (CB-1/2/3 실험)
- **ADR-SCR-008 Single-Flight Coordinator** — TS 운영자산 7 가지 행동 보장을 Kotlin Coroutines `Mutex` / `Deferred` 로 이식. SF-2 99.9% coalescing 측정
- **ADR-SCR-009 3-Layer 세션 캐시** — Memory L1 → Redis L2 → 외부 인증 L3 (NAVER 인증 운영 경험 일반화)
- **ADR-SCR-010 Bulkhead 격리** — Semaphore vs FixedThreadPool 외부 의존성별 풀 분리
- **ADR-SCR-011 Resilience4j 데코레이터 체인 순서** — `Bulkhead → CB → Retry → TimeLimiter → RateLimiter` (Retry 안에 CB 두면 CB 통계 N배 카운트 함정)
- **핵심 실험** — EXP-WC-01 WebClient `.block()` EventLoop pinning 처리량 1/10 폭락 실측 → 완전 비동기 강제

---

## 경력 — 아이브릭스(I-BRICKS) ｜ 백엔드 개발자 ｜ 2021.05 ~ 2024.11

한국어 자연어 처리 전문 기업에서 검색·추천 시스템, 데이터 파이프라인, 챗봇 개발 담당.

- **EBS 학습 시스템 데이터 파이프라인 (Kafka · Apache Nifi · Elasticsearch)** — 일일 **수천만 건** 로깅을 Kafka producer / consumer + Nifi flow + Elasticsearch 클러스터로 처리. 단일 인스턴스 INSERT 의 처리량 한계 → Kafka 비동기 메시징 + Nifi 흐름 분기로 처리량 2배 증가에도 안정 동작, **쿼리 응답 시간 50% 단축**. (Kafka 운영 경험의 시초 — JVM 재설계 프로젝트의 commerce-batch-orchestrator 가 이 경험의 확장)
- **한국 금융연수원 강의 검색·추천 (Elasticsearch + Logstash)** — RDB → ES 파이프라인 구축, 사용자별 시청 시간·카테고리 선호도 가중치 부여로 검색·추천 경로를 한 인덱스에서 일관 처리.
- **대법원 챗봇 도우미** — React / Redux / SCSS 기반 사용자 UI, KWCAG 2.1 웹 접근성 준수.

---

## 교육

**F-Lab Java Backend Mentoring** ｜ 2024.01 ~ 2024.07
Meta 시니어 개발자 멘토링 과정 수료. 객체지향 설계, 트랜잭션 처리, 클린 아키텍처 중심으로 동시성 제어, CQRS, 분산 트랜잭션 심화 학습.

**경기대학교 컴퓨터과학과 졸업**
