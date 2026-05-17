# 경력기술서

김면수 / 백엔드 개발자
digle117@gmail.com ｜ github.com/PreAgile ｜ medium.com/@digle117

---

## 르몽 (Lemong)

2024년 11월부터 르몽에서 리뷰 통합 관리 SaaS의 백엔드를 담당하고 있습니다. 댓글몽은 자영업자가, 댓글몽 Biz는 프랜차이즈 본사가 사용하는 서비스로, 배달의민족, 요기요, 쿠팡이츠, 네이버, 땡겨요, 먹깨비 6개 플랫폼의 리뷰를 통합 수집/분석하고 자동 댓글과 불만족 리뷰 알림을 제공합니다.

운영 규모는 일평균 API 호출 20만 건, 페이지 스크래핑 100만 건, 리뷰 수집 12만 건이며, 플랫폼별로 30개 이상의 worker가 병렬로 동작합니다. cmong-be(API/도메인 서버)와 cmong-scraper-js(스크래퍼 워커) 두 저장소를 중심으로 일하고 있습니다.

### 멀티플랫폼 통합 인증과 세션 관리

플랫폼마다 로그인 정책이 달라 한 곳에서 통과한 코드가 다른 곳에서는 그대로 막히는 일이 잦았습니다. 2FA를 요구하는 곳, captcha를 띄우는 곳, IP를 기준으로 차단하는 곳, device verification을 요구하는 곳이 섞여 있고, 같은 플랫폼이라도 시간대별로 정책이 변하기도 했습니다.

Playwright 위에서 Camoufox 스텔스 브라우저 풀을 운영하면서, worker 30개 이상이 같은 매장에 접근할 때 발생하는 중복 로그인 문제가 가장 어려웠습니다. 세션을 매번 새로 만들면 평판 좋은 IP가 빠르게 소진되고, 그렇다고 무작정 재사용하면 인증 만료 시점을 놓치기 쉬웠습니다.

이 문제는 FIFO 큐와 lease TTL을 가진 SessionLockRegistry를 만들어 풀었습니다. 한 매장에 대한 로그인은 한 시점에 하나만 진행되고, 다른 worker는 큐에서 대기하다가 먼저 만든 세션을 그대로 이어받습니다. lease TTL은 30분에서 시작했지만 운영하다 보니 플랫폼별로 IP 평판이 떨어지는 패턴이 달라, 5분에서 60분까지 차등 적용하는 쪽으로 조정했습니다.

8가지 로그인 분기(정상, captcha, 2FA, IP 차단, device verification, password 변경, account locked, unknown)는 ScrapperException을 상위에 두고 계층 구조로 일원화했습니다. 어떤 분기든 발생하면 동일한 흐름을 타고 복원 로직으로 들어가기 때문에 새로운 플랫폼을 붙일 때 분기 처리를 다시 짤 필요가 없습니다.

운영 결과 세션 유지율 99.2%를 유지하고 있고, 중복 로그인으로 인한 IP 차단 사례는 발생하지 않았습니다.

### 리뷰 수집 비동기 파이프라인

리뷰 수집은 무거운 작업입니다. 매장 하나의 데이터를 모두 긁어오는 데 5분 이상 걸리는 경우가 흔하고, 이걸 동기 호출로 받으면 ALB 타임아웃에 걸려 502가 떴습니다. 사용자에게 즉시 응답을 줄 수 있어야 하면서도, 백그라운드에서 작업이 안정적으로 끝나야 했습니다.

RabbitMQ의 reply-request-reply 패턴으로 분리했습니다. API는 메시지를 publish하고 202와 taskId만 반환합니다. scraper worker는 prefetch 2로 큐에서 분산 소비하고, 작업이 끝나면 REPLY_COMPLETE 큐에 결과를 publish합니다. 사용자는 polling이나 푸시 알림으로 진행 상태를 확인합니다.

큐는 종류별로 분리해 운영합니다. POPULATE_BATCH는 prefetch 1로 묶고, SCRAPING이나 MARKETING은 prefetch 2를 두는 식으로 작업 특성에 맞춰 설정을 다르게 했습니다. DLQ는 모든 큐가 공유하되 원인별로 라벨을 붙여 운영팀이 빠르게 식별할 수 있게 했습니다.

댓글 자동화의 중복 등록은 멱등성 네 단계로 막았습니다. Idempotency-Key에 UNIQUE 제약을 걸어 중복 진입을 차단하고, 결제 상태머신을 PENDING / CONFIRMED / CANCELLED로 명확히 분리했습니다. 같은 키에 대한 요청은 Redis에 캐싱된 응답을 그대로 돌려주고, 마지막으로 일일 reconciliation 배치가 외부 PG와 우리 DB를 대조해 누락을 잡습니다. 운영 시작 이후 결제 webhook 중복 처리는 0건입니다.

### 프랜차이즈 멀티테넌트 구조 (댓글몽 Biz)

프랜차이즈 본사는 한 화면에서 1,000개 매장의 리뷰를 동시에 관리해야 합니다. 처음 설계할 때는 매장별 세션을 격리하지 않았는데, 한 매장이 차단당하면 같은 worker를 쓰던 다른 매장까지 영향을 받는 문제가 발생했습니다.

매장별로 인증 세션을 완전히 분리하고, Token Bucket Rate Limiter를 매장 단위로 적용했습니다. 그 위에 Worker Queue를 두어 폭주하는 요청은 큐에서 흡수하도록 만들었습니다. 다만 완전 격리만 하면 worker 풀의 활용률이 떨어지는 문제가 생겨, sticky session 라우팅(StickySessionService)으로 한 매장은 한 worker에 affinity를 두되 시간대별로 dynamic하게 재할당하는 식으로 절충했습니다.

도입 이후 플랫폼 API 차단률이 90% 감소했고, 같은 시간 안에 처리할 수 있는 리뷰량이 6배로 늘었습니다.

### 마케팅 댓글 예약 비동기 실행

마케팅 캠페인이 한 번 트리거되면 수만 건의 예약 댓글이 같은 시각에 깨어납니다. 처음에는 단순 cron 폴링으로 구현했는데, TPS가 100 부근까지 올라가자 DB 락 컨텐션이 폭증하고 처리 지연이 5분을 넘어가는 일이 잦아졌습니다.

Aurora 기반 예약 큐 테이블과 Aurora Consume 패턴으로 다시 설계했습니다. 메시지 큐 수준의 비동기 실행이 가능하도록 SELECT FOR UPDATE를 분산 처리하고, 카운터는 Redis pipeline 배치로 atomic하게 집계합니다. 상태 추적은 Redis Pub/Sub로 흘려보내고, 실패한 작업은 지수 백오프로 멱등 재시도합니다.

운영 데이터 기준 TPS 1,000 이상, 예약 실패율 1% 이하, 처리 지연 10초 미만을 안정적으로 유지하고 있습니다.

### PAMS — 프록시 비용과 가용성 개선

이 시스템은 회사에 합류한 뒤 가장 큰 비용 절감과 가용성 개선을 만든 작업입니다.

외부 Decodo Residential Proxy에 의존하던 구조는 두 가지 문제가 있었습니다. 첫째, 트래픽이 늘 때마다 비용이 선형으로 증가해 매월 800만 원에 도달했습니다. 둘째, Decodo 측 장애가 곧 우리 서비스 중단으로 이어지는 SPOF 구조였습니다.

세 가지를 동시에 진행했습니다.

첫째, 자체 Datacenter Proxy 풀로 전환했습니다. Datacenter IP는 평판이 낮은 게 일반적이지만, 비용은 Residential의 10분의 1 수준이라 풀 규모를 크게 가져갈 수 있었습니다.

둘째, Naver IP Reputation 시스템을 구축했습니다. port-IP 매핑을 MySQL에 영구화하고 부팅 시 S3에서 부트스트랩하는 구조로 만들어, 매장과 세션이 평판 좋은 IP에 고정되도록 sticky pool을 운영합니다. 이렇게 한 IP의 평판을 장기간 관리하면 Datacenter라도 사용할 만한 수준이 됩니다.

셋째, 자동 Cooldown 알고리즘을 추가했습니다. 성공률, 타임아웃, 응답 지연 세 지표를 모니터링하다가 임계치를 넘으면 해당 IP를 자동으로 cooldown 풀로 격리하고 트래픽을 재분산합니다. 일정 시간이 지나면 다시 검증해 복귀시키는 식으로 풀 규모를 유지합니다.

전환 이후 월 비용은 800만 원에서 90만 원으로 88.75% 줄었고, 요청 성공률은 70%에서 98%로 올랐습니다. Prometheus와 Grafana 기반 Health 대시보드를 만들어 가용성을 실시간으로 추적하고, Decodo는 보조 풀로 남겨 HA를 확보했습니다.

### 운영과 관측

다중 인스턴스 환경에서 가장 자주 마주친 문제는 cron job의 중복 실행과 분산 트랜잭션 컨텍스트의 끊김이었습니다.

cron 중복 실행은 @SafeCron 데코레이터를 직접 만들어 해결했습니다. 실행 시점에 Redis 락을 잡고, 다른 인스턴스는 동일 작업을 건너뜁니다. 시작/완료/실패는 Slack으로 자동 알림이 가고, 어떤 이유로든 종료되면 finally 블록에서 락을 안전하게 정리합니다.

트랜잭션 컨텍스트는 @nestjs-cls/transactional을 통해 비동기 호출 사이에서 끊기지 않도록 묶었고, 분산 트레이싱은 Datadog APM으로 통합했습니다. 로그는 structured JSON으로 보내 Datadog과 ElasticSearch에서 같은 키로 검색 가능하게 했습니다. Prometheus + Grafana + Slack Webhook 조합으로 알림이 자동으로 가도록 정비해 운영 대응 시간을 70% 줄였고, 평균 복구 시간은 5분 이내로 유지하고 있습니다.

---

## 아이브릭스 (I-BRICKS)

2021년 5월부터 2024년 11월까지 약 3년 6개월 동안 한국어 자연어 처리 전문 기업에서 근무했습니다. 검색 시스템, 데이터 파이프라인, 챗봇 개발을 담당했고 백엔드는 Java/Spring Boot, 일부는 Node.js로 작성했습니다.

### 식품 E-commerce 서비스 (Java / Spring Boot)

TossPayments API를 통합한 결제 시스템을 처음부터 구축했습니다. Idempotency-Key를 적용하고 결제 상태를 명시적인 상태머신으로 분리해 중복 결제와 상태 꼬임을 방지했습니다. 사용자 입장에서 가장 자주 호출되는 Product GET API가 3초 이상 걸리는 게 문제였는데, 분석해 보니 N+1 쿼리와 미스된 인덱스가 원인이었습니다. 쿼리를 정리하고 인덱스를 다시 잡은 뒤 Redis Cache-Aside를 얹어 응답 시간을 0.3초까지 줄였습니다.

nGrinder로 부하 테스트를 정기적으로 돌리며 TPS를 330에서 370까지 끌어올렸고, Jenkins와 Docker 기반 CI/CD를 정비해 배포 효율을 30% 개선했습니다.

### EBS 학습 시스템 데이터 파이프라인

일일 수천만 건의 학습 로그를 안정적으로 수집하기 위해 Kafka 기반 비동기 메시징을 도입했습니다. Apache Nifi와 Elasticsearch 클러스터를 함께 구성해 데이터 처리량이 두 배로 늘어나도 안정적으로 동작하도록 설계했고, 쿼리 응답 시간을 50% 단축했습니다.

### 대법원 챗봇 도우미 (웹 프론트엔드)

React, Redux, SCSS 기반의 사용자 화면을 구현했습니다. 머신러닝 자연어 처리 결과를 사용자에게 어떻게 노출할지 UI 측면에서 고민했고, KWCAG 2.1 웹 접근성 기준을 준수했습니다.

---

## JVM 학습 프로젝트

5년 동안 Node.js로 운영하며 만난 문제들을 Java/Kotlin/Spring 환경에서 다시 풀어보고, 그 결정 과정을 ADR과 실험 노트로 기록하고 있습니다. 운영 코드와 별개로 진행하는 학습용 저장소 세 개를 운영합니다.

**commerce-comment-platform-be** (Java / Spring Boot / JPA)
운영 시스템에서 다뤘던 결제 멱등성, 분산 락, 트랜잭션 분리 같은 주제를 JPA 환경에서 다시 검증합니다. Redisson watchdog과 비관락, 낙관락, GET_LOCK 네 가지를 같은 시나리오에서 비교 측정했고, MySQL InnoDB의 RR 격리수준이 ANSI 표준 RR과 어떻게 다른지 직접 재현해 ADR로 정리했습니다. 트랜잭션 분리 패턴(Saga, Outbox, 단순 분리)도 9개 시나리오 매트릭스로 비교했고, No-offset Pagination을 도입해 OFFSET 1M 지점에서 발생하는 응답 지연 문제를 풀었습니다. Dirty Checking 관련 실험 다섯 건과 JPA Spring Mastery 시리즈 글 여덟 편을 작성했습니다.

**commerce-batch-orchestrator** (Spring Batch + Kafka)
처음부터 Kafka를 채택하지 않고, RabbitMQ를 1주간 운영하면서 다섯 가지 한계(replay 비용, prefetch head-of-line blocking, x-overflow 드롭, publisher confirm 실패 시나리오, DLQ 재처리 운영 비용)를 직접 측정한 뒤 Kafka로 전환을 정당화하는 ADR을 썼습니다. Outbox Relay의 polling 5초와 CDC(Debezium) 지연을 비교했고, Spring Batch Reader 네 가지(JpaPagingItemReader, JdbcCursor, JpaCursor, QuerydslZeroOffset)의 성능을 매트릭스로 측정했습니다.

**commerce-external-gateway-kt** (Kotlin / Coroutines / Resilience4j)
운영의 외부 게이트웨이 자산을 Kotlin Coroutines로 재설계하는 프로젝트입니다. Single-Flight 패턴을 다섯 가지 불변식(promise sharing, sync throw normalization, force release, deadline, capacity)으로 형식화했고, 9종 에러 카테고리 분류기를 정의해 GraphQL의 200 OK + body.errors 케이스를 1순위 룰로 잡았습니다. Resilience4j의 다섯 모듈(CircuitBreaker, Retry, Bulkhead, RateLimiter, TimeLimiter)을 적용하고 임계값을 측정으로 정했습니다.

지금까지 ADR 49건, 실험 노트 47건, 기술 블로그 17편을 누적했습니다.

---

## 기술 스택

**운영 경험**
TypeScript, JavaScript / NestJS, Node.js, Express / MySQL 8, Aurora, Oracle / Redis (ioredis, 분산 락, Token Bucket) / RabbitMQ (6 queue, prefetch 튜닝, DLQ) / Elasticsearch, Kibana, Apache Nifi / Playwright, Camoufox / Prometheus, Grafana, Datadog APM, nGrinder / Jest, Testcontainers / Docker, AWS ECS, Naver Cloud, Jenkins, GitHub Actions

**학습 중**
Java, Kotlin / Spring Boot, Spring Batch / PostgreSQL / Redisson / Kafka / Resilience4j / k6, Gatling, OpenTelemetry / JUnit 5, Kotest, WireMock / Kubernetes

**관심 영역**
RESTful API 설계, 트랜잭션 관리, Rate Limiting, CI/CD, HA 구조, DDD, Hexagonal Architecture, Saga, Outbox, CQRS

---

## 교육

**F-Lab Java Backend Mentoring** ｜ 2024.01 ~ 2024.07
Meta 시니어 개발자 멘토링 과정 수료. 객체지향 설계, 트랜잭션 처리, 클린 아키텍처를 중심으로 동시성 제어, CQRS, 분산 트랜잭션을 심화 학습했습니다.

**경기대학교 컴퓨터과학과** ｜ 졸업

---

## 외부 자료

- GitHub: github.com/PreAgile
- 기술 블로그: medium.com/@digle117
- ADR/실험 노트 저장소: (공개 URL 예정)
