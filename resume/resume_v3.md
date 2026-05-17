# 김면수

백엔드 개발자

010-9101-5429 ｜ digle117@gmail.com
github.com/PreAgile ｜ medium.com/@digle117

---

분산 환경에서 트랜잭션 일관성을 지키는 일, 비동기 메시징으로 처리량을 늘리는 일, 그리고 트래픽이 일정 수준을 넘어가면서 단순한 구조가 한계에 부딪히는 지점을 찾아 풀어내는 일에 관심이 많습니다. 현재 르몽에서 6개 배달 플랫폼을 통합 관리하는 리뷰 SaaS의 백엔드를 담당하고 있고, Node.js/NestJS 기반의 운영 시스템과 Python 기반 스크래퍼를 함께 다루고 있습니다.

5년 동안 쌓아온 운영 경험을 Kotlin과 Spring 생태계에서 다시 검증해 보고 싶어, 별도의 학습 프로젝트(JPA, Spring Batch, Coroutines)와 ADR 기록을 꾸준히 남기고 있습니다.

## 경력

### 르몽 (Lemong)
백엔드 개발자 ｜ 2024.11 ~ 현재

자영업자와 프랜차이즈 본사를 위한 리뷰 통합 관리 SaaS '댓글몽'을 운영합니다. 배달의민족, 요기요, 쿠팡이츠, 네이버, 땡겨요, 먹깨비 6개 플랫폼의 리뷰를 통합 수집/분석하고 자동 댓글과 불만족 리뷰 알림 기능을 제공하고 있습니다. 일평균 API 호출 20만 건, 페이지 스크래핑 100만 건, 리뷰 수집 12만 건 규모를 처리하며, 플랫폼별로 30개 이상의 worker가 병렬로 동작합니다.

**멀티플랫폼 통합 인증과 세션 관리**
플랫폼마다 다른 로그인 정책(2FA, captcha, device verification, IP 차단)을 Playwright와 Camoufox 스텔스 브라우저를 활용한 비동기 세션 모듈로 통합 처리. worker 30개 이상이 같은 매장에 동시 접근할 때 발생하던 중복 로그인 문제를, FIFO 큐와 lease TTL 기반의 SessionLockRegistry로 풀어내 **세션 유지율 99.2%**를 유지하고 있습니다. 8가지 로그인 분기는 ScrapperException 계층 구조로 일원화해 장애 복원이 자동으로 흐르도록 설계했습니다.

**리뷰 수집 비동기 파이프라인**
5분 이상 걸리는 무거운 스크래핑 작업이 동기 호출에서 ALB 타임아웃을 유발하던 문제를, RabbitMQ의 reply-request-reply 패턴으로 분리해 해결. API는 즉시 응답하고 scraper worker가 큐에서 분산 소비하며, 완료는 별도 큐로 통지합니다. 댓글 자동화의 중복 등록은 Idempotency-Key UNIQUE 제약, 상태머신, Redis 응답 캐싱, 일일 reconciliation의 네 단계로 막아 결제 webhook 중복 처리 0건을 유지하고 있습니다.

**프랜차이즈 멀티테넌트 구조 (댓글몽 Biz)**
프랜차이즈 본사가 1,000개 매장을 한 화면에서 관리할 수 있도록 매장별 세션을 격리. Token Bucket Rate Limiter와 Worker Queue를 조합하고, 한 매장은 한 worker에 고정되는 sticky session 라우팅을 적용해 세션 thrashing을 줄였습니다. 그 결과 플랫폼 API 차단률이 90% 감소하고 전체 리뷰 처리량은 6배 늘었습니다.

**마케팅 댓글 예약 비동기 실행**
캠페인마다 수만 건의 예약 댓글이 동시에 트리거되면서 단순 cron 폴링이 DB 락 컨텐션을 유발하던 문제를, Aurora 기반 예약 큐 테이블과 Aurora Consume 패턴(메시지 큐 수준의 비동기 실행)으로 재설계. Redis Pub/Sub로 상태를 추적하고 지수 백오프로 멱등 재시도를 구현해 **TPS 1,000 이상, 예약 실패율 1% 이하, 처리 지연 10초 미만**을 안정적으로 유지하고 있습니다.

**PAMS — 프록시 비용과 가용성 개선**
외부 Decodo Residential Proxy 의존도가 높아 비용이 매월 800만 원에 달하고 외부 장애가 곧 서비스 중단으로 이어지던 구조를, 자체 Datacenter 프록시 풀과 IP 평판 관리 시스템으로 전환. port-IP 매핑을 영구화하고 매장별 sticky pool을 적용했으며, 성공률/타임아웃/응답 지연 세 지표를 기준으로 한 자동 Cooldown 알고리즘으로 장애 IP를 격리하고 트래픽을 재분산합니다.

전환 이후 **월 비용은 800만 원에서 90만 원으로(88.75% 절감), 요청 성공률은 70%에서 98%로** 개선되었고, Prometheus와 Grafana 기반 Health 대시보드로 가용성을 실시간 추적할 수 있게 되었습니다.

**운영과 관측**
다중 인스턴스 환경에서 cron job 중복 실행을 막기 위해 Redis 락과 Slack 알림이 묶인 @SafeCron 데코레이터를 직접 만들어 적용했고, @nestjs-cls/transactional로 분산 트랜잭션 컨텍스트를 끊김 없이 전달합니다. Datadog APM, Prometheus + Grafana, ElasticSearch + Kibana를 연결해 운영 대응 시간을 70% 단축하고 평균 복구 시간을 5분 이내로 유지하고 있습니다.

### 아이브릭스 (I-BRICKS)
백엔드 개발자 ｜ 2021.05 ~ 2024.11

한국어 자연어 처리 전문 기업으로 검색 시스템, 데이터 파이프라인, 챗봇 개발을 담당했습니다.

**식품 E-commerce 서비스 개발 (Java / Spring Boot)**
TossPayments API를 통합한 결제 시스템을 Idempotency-Key와 결제 상태머신 기반으로 구축. Product GET API의 N+1 쿼리를 제거하고 인덱스를 재설계한 뒤 Redis Cache-Aside를 적용해 응답 시간을 3초에서 0.3초로, nGrinder 부하 테스트 기준 TPS를 330에서 370으로 끌어올렸습니다. Jenkins와 Docker 기반 CI/CD를 정비해 배포 효율을 30% 개선했습니다.

**EBS 학습 시스템 데이터 파이프라인**
일일 수천만 건의 로깅 데이터를 안정적으로 수집하기 위해 Kafka 기반 비동기 메시징을 도입하고, Apache Nifi와 Elasticsearch 클러스터로 데이터 처리량이 두 배 늘어도 안정적으로 동작하도록 설계. 쿼리 응답 시간을 50% 단축했습니다.

**대법원 챗봇 도우미 (웹 프론트엔드)**
React, Redux, SCSS 기반 사용자 중심 UI를 구현했으며 KWCAG 2.1 웹 접근성 기준을 준수했습니다.

## JVM 학습 프로젝트

5년의 Node.js 운영 경험에서 부딪혔던 분산 락, 결제 멱등성, 트랜잭션 분리, 외부 의존성 격리 같은 문제를 Java/Kotlin/Spring 환경에서 다시 풀어보고 그 결정 과정을 ADR로 기록하고 있습니다. 현재까지 ADR 49건, 실험 47건, 기술 블로그 17편을 누적했습니다.

- **commerce-comment-platform-be** (Java/Spring Boot/JPA): 결제 멱등성 4단계, Redisson watchdog 등 분산 락 4종 비교, MySQL InnoDB RR과 ANSI RR의 차이, 트랜잭션 분리 패턴(Saga, Outbox) 9개 시나리오 매트릭스, No-offset Pagination 적용.
- **commerce-batch-orchestrator** (Spring Batch + Kafka): RabbitMQ를 1주간 운영해 5가지 한계(replay 비용, prefetch HoL, x-overflow 드롭, publisher confirm 실패, DLQ 운영 비용)를 측정하고 Kafka 전환을 정당화하는 ADR 작성. Outbox Relay의 polling과 CDC 지연 비교, Reader 4종 매트릭스.
- **commerce-external-gateway-kt** (Kotlin/Coroutines/Resilience4j): 운영 자산을 Kotlin으로 재설계. Single-Flight 패턴의 다섯 가지 불변식, 9종 에러 카테고리 분류기, Resilience4j 다섯 가지 모듈(CircuitBreaker, Retry, Bulkhead, RateLimiter, TimeLimiter) 적용.

## 기술 스택

| 영역 | 사용 기술 |
|------|-----------|
| 언어 | TypeScript, JavaScript, Java, Kotlin |
| 프레임워크 | NestJS, Node.js, Spring Boot, Spring Batch |
| 데이터베이스 | MySQL 8, Aurora, Oracle, PostgreSQL |
| 캐시 / 락 | Redis (ioredis, 분산 락, Token Bucket), Redisson |
| 메시징 | RabbitMQ, Kafka |
| 검색 / 로깅 | Elasticsearch, Kibana, Apache Nifi |
| 외부 의존성 격리 | Resilience4j, Custom Retry/Timeout |
| 헤드리스 브라우저 | Playwright, Camoufox |
| 부하 / 관측 | Prometheus, Grafana, Datadog APM, nGrinder |
| 테스트 | Jest, Testcontainers, JUnit 5, Kotest |
| 인프라 | Docker, AWS ECS, Naver Cloud, Jenkins, GitHub Actions |

## 교육

**F-Lab Java Backend Mentoring** ｜ 2024.01 ~ 2024.07
Meta 시니어 개발자 멘토링 과정 수료. 객체지향 설계, 트랜잭션 처리, 클린 아키텍처 중심으로 동시성 제어, CQRS, 분산 트랜잭션을 심화 학습했습니다.

**경기대학교 컴퓨터과학과 졸업**
