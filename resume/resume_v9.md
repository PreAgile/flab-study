# 김면수

백엔드 개발자

Phone: 010-9101-5429 ｜ Email: digle117@gmail.com
GitHub: github.com/PreAgile ｜ Blog: astro-paper-23v.pages.dev

---

분산 환경에서 트랜잭션 일관성, 비동기 메시징 기반 처리량 개선, 외부 API 의존성 격리, 세션 일관성 문제를 주로 다뤄온 백엔드 개발자입니다.

현재 르몽에서 6개 배달 플랫폼을 통합 관리하는 리뷰 SaaS의 백엔드를 담당하고 있습니다. 일평균 API 호출 20만 건, 페이지 수집 100만 건, 리뷰 수집 12만 건 규모를 Node.js/NestJS 기반으로 RabbitMQ, Redis, Aurora, ECS, Datadog 위에서 운영하고 있습니다.

이 운영 경험을 Kotlin/Spring Boot/JPA 환경에서 동일하게 재현하고 비교하는 재설계 프로젝트를 진행하면서, **JVM 오픈 소스 프로젝트**에도 정기적으로 기여하고 있습니다. **Kotlin 테스트 프레임워크 Kotest의 organization 정식 멤버**로 6개 PR을 머지했고, **LINE의 비동기 RPC 프레임워크 Armeria**에는 MDC 확장 PR을 머지했습니다. Public API 호환성, JSON Schema 표준 구현, MDC 로깅 컨텍스트 전파, 정적 분석(NullAway) 정책 같은 제약 안에서 작성한 변경들입니다.

## 오픈소스 기여

**Kotest** ｜ Kotlin 테스트 프레임워크 (GitHub 4.7k stars)
2026년 3월 메인테이너 sksamuel의 직접 초대로 organization 정식 멤버가 되어 약 한 달간 **6개 PR을 머지**했습니다. 가장 임팩트 있는 작업은 JVM/JS/Wasm/Native 멀티플랫폼 환경에서 Spec/Test/TestCase 계층을 통합하는 **타입 안전한 Test Metadata Public API를 신규 설계**한 PR #5905(+355/-16)로, 기존 sealed interface와 호환성을 유지하면서 새 공개 API를 추가하는 작업이었습니다. 그 외 JSON Schema anyOf/oneOf 표준 구현(#5807), Kotlin 내부 어노테이션 `@OnlyInputTypes`를 활용한 타입 안전 어설션(#5789), 컬렉션 data class 필드 단위 diff(#5835), JSON Matchers 커스텀 파서 지원(#5795), 어설션 체이닝(#5756)을 머지했습니다.

**Armeria** ｜ LINE의 Java 기반 비동기 RPC 프레임워크
RequestContextExporter의 BuiltInProperty에 request/response timing, content preview, serialization format, session protocol, host를 추가하고, Logback MDC export 경로의 테스트를 보강한 PR(#6683, +339/-5)을 머지했습니다.

**Spring Batch**
fault-tolerant step의 chunk scanning 메커니즘이 4년 이상 공식 문서에 누락되어 있던 이슈 #3946을 해결하는 PR(#5395)을 제출했습니다. retry 정책과 chunk scanning의 상호작용을 reference docs의 fault tolerance / scalability / chunk-oriented-processing 섹션에 추가했고, 메인테이너 응답을 대기 중입니다.

## 경력

### 르몽 (Lemong)
백엔드 개발자 ｜ 2024.11 ~ 현재

자영업자와 프랜차이즈 본사를 위한 리뷰 통합 관리 SaaS '댓글몽'을 운영합니다. 배달의민족, 요기요, 쿠팡이츠, 네이버, 땡겨요, 먹깨비 6개 플랫폼의 리뷰를 통합 수집·분석하고 자동 댓글과 불만족 리뷰 알림 기능을 제공합니다. 일평균 **API 호출 20만 건, 페이지 스크래핑 100만 건, 리뷰 수집 12만 건** 규모를 처리하며, 플랫폼별로 30개 이상의 worker가 병렬로 동작합니다.

**멀티플랫폼 통합 인증과 세션 관리**
플랫폼마다 다른 로그인 정책(2FA, captcha, device verification, IP 차단)을 Playwright와 Camoufox 스텔스 브라우저 기반 비동기 세션 모듈로 통합 처리했습니다. worker 30개 이상이 같은 매장에 동시 접근할 때 발생하던 중복 로그인 문제는 FIFO 큐와 lease TTL 기반의 SessionLockRegistry를 만들어, 한 매장의 로그인은 한 시점에 하나만 진행되고 나머지 worker는 큐에서 대기하다 이미 만들어진 세션을 이어받도록 했습니다. **세션 유지율 99.2% (최근 6개월 운영 지표)**를 유지하고 있습니다. 8가지 로그인 분기는 ScrapperException 계층 구조로 일원화해, captcha 감지 시 자동으로 PAMS에 IP 교체를 요청하는 재시도 흐름으로 연결했습니다.

**스크래퍼 비동기 파이프라인 진화**
외부 플랫폼 댓글 등록은 건당 3~5분이 걸리는 무거운 IO 작업입니다. 처음에는 사용자 동기화 요청을 RabbitMQ의 reply-request-reply 패턴으로 분리해 API가 즉시 응답하도록 만들어 ALB 타임아웃 문제를 풀었습니다. 이 구조도 일괄 댓글(피크 1,000건)과 마케팅 캠페인(수만 건)이 동시에 트리거되는 시나리오에서는 사용자 시간대 예약과 진행 중 작업 취소를 지원하지 못하는 한계가 드러나, 별도 오케스트레이터 서비스와 RabbitMQ Quorum Queue 기반 파이프라인으로 작업 예약·취소·재시도·결과 회수를 분리하는 작업을 진행 중입니다.

- API는 검증 후 bulk INSERT와 202 응답만 수행
- SELECT FOR UPDATE SKIP LOCKED로 예약 작업 picking
- DLX 기반 단계적 재시도와 플랫폼별 prefetch / concurrency 분리
- 사용자 시간대 예약 등록과 Stage 1 취소 윈도우 확보

댓글 자동화의 중복 등록은 Idempotency-Key UNIQUE 제약, 상태머신(PENDING → CONFIRMED / CANCELLED), Redis 응답 캐싱, 일일 reconciliation의 네 단계로 막아 **댓글 등록 중복 0건 (최근 6개월 기준)**을 유지하고 있습니다.

**프랜차이즈 멀티테넌트 구조 (댓글몽 Biz)**
프랜차이즈 본사가 **1,000개 매장**을 한 화면에서 관리할 때, 매장별 세션이 격리되지 않으면 한 매장의 차단이 같은 worker를 쓰는 다른 매장으로 전이되는 문제가 있었습니다. 매장별 인증 세션을 분리하고, Token Bucket Rate Limiter와 Worker Queue로 폭주를 흡수했습니다. 한 매장은 한 worker에 affinity가 고정되는 sticky session 라우팅을 적용해 세션 thrashing을 줄이되, 시간대별로 worker 활용률을 보면서 dynamic하게 재할당하는 식으로 절충했습니다. 그 결과 **플랫폼 API 차단률이 90% 감소**하고 전체 리뷰 처리량은 **6배**로 늘었습니다.

**마케팅 댓글 예약 비동기 실행**
캠페인마다 수만 건의 예약 댓글이 같은 시각에 깨어나면서, 단순 cron 폴링이 TPS 100 부근에서 DB 락 컨텐션을 유발해 처리 지연이 5분을 넘어가던 문제가 있었습니다. Aurora 기반 예약 큐 테이블과 Aurora Consume 패턴(메시지 큐 수준의 비동기 실행)으로 다시 설계했습니다. SELECT FOR UPDATE를 분산 처리하고 Redis Pub/Sub로 상태를 추적하며, 실패한 작업은 지수 백오프로 멱등 재시도합니다. **TPS 1,000/s 이상 (Aurora 부하 테스트 기준), 예약 실패율 1% 이하, 처리 지연 10초 미만**을 유지하고 있습니다.

**자체 프록시 풀 관리·모니터링 시스템**
외부 Decodo Residential Proxy 의존도가 높아 비용이 매월 **800만 원**에 달했고, Decodo 측 장애가 그대로 우리 서비스 중단으로 이어지는 SPOF 구조였습니다. 자체 Datacenter Proxy 풀로 전환하고, Naver IP Reputation 시스템(port-IP 매핑을 MySQL에 영구화 + S3 부트스트랩)을 구축해 매장과 세션이 평판 좋은 IP에 sticky하게 고정되도록 했습니다. 성공률·타임아웃·응답 지연 세 지표를 임계치로 두는 자동 Cooldown 알고리즘으로 장애 IP를 격리하고 트래픽을 재분산합니다.

전환 이후 **월 비용은 800만 원에서 90만 원으로(88.75% 절감), 요청 성공률은 70%에서 98%(프록시 전환 후 운영 대시보드 기준)**로 개선되었고, Prometheus와 Grafana 기반 Health 대시보드로 가용성을 실시간 추적합니다. Decodo는 보조 풀로 남겨 HA를 확보했습니다.

### 아이브릭스 (I-BRICKS)
백엔드 개발자 ｜ 2021.05 ~ 2024.11

한국어 자연어 처리 전문 기업으로 검색 시스템, 데이터 파이프라인, 챗봇 개발을 담당했습니다.

**한국 금융연수원 강의 검색·추천 시스템**
동영상 강의 플랫폼의 검색과 추천 기능을 Elasticsearch 기반으로 구축했습니다. RDB 덤프를 Logstash로 정기 색인해 Elasticsearch에 적재하는 파이프라인을 만들고, 그 위에 사용자별 강의 시청 로그와 신규 강의 진입 로그를 기반으로 한 추천 시스템을 얹었습니다. 시청 시간, 카테고리 선호도 등 필드별로 가중치를 다르게 설정해 사용자별 맞춤 추천을 제공했고, 강의 메타데이터 검색도 같은 인덱스에서 처리해 검색과 추천 경로를 일원화했습니다.

**EBS 학습 시스템 데이터 파이프라인**
일일 **수천만 건**의 로깅 데이터를 안정적으로 수집하기 위해 Kafka 기반 비동기 메시징을 도입하고, Apache Nifi와 Elasticsearch 클러스터를 함께 구성해 데이터 처리량이 두 배로 늘어도 안정적으로 동작하도록 설계했습니다. 쿼리 응답 시간을 50% 단축했습니다.

**대법원 챗봇 도우미 (웹 프론트엔드)**
React, Redux, SCSS 기반 사용자 중심 UI를 구현했으며 KWCAG 2.1 웹 접근성 기준을 준수했습니다.

## Spring/Kotlin 백엔드 재설계 프로젝트

5년 동안 Node.js로 운영하며 부딪힌 분산 락, 결제 멱등성, 트랜잭션 분리, 외부 의존성 격리 같은 문제를 Java/Kotlin/Spring 환경에서 동일한 시나리오로 다시 풀어보고, 그 결정 과정을 ADR로 남기는 프로젝트입니다. 현재까지 **ADR 49건, 실험 47건, 기술 블로그 17편**을 누적했습니다.

- **commerce-comment-platform-be** (Java / Spring Boot / JPA): 결제 멱등성 4단계, 분산 락 4종 비교(비관락 · 낙관락 · GET_LOCK · Redisson), MySQL InnoDB RR과 ANSI RR 차이 재현, 트랜잭션 분리 패턴 9 시나리오 매트릭스, No-offset Pagination.
- **commerce-batch-orchestrator** (Spring Batch + Kafka): RabbitMQ를 1주간 운영해 5가지 한계(replay 비용, prefetch HoL, x-overflow, publisher confirm 실패, DLQ 운영 비용)를 측정하고 Kafka 전환을 정당화하는 ADR 작성. Outbox Relay의 polling과 CDC 지연 비교, Spring Batch Reader 4종 매트릭스.
- **commerce-external-gateway-kt** (Kotlin / Coroutines / Resilience4j): 운영 자산을 Kotlin으로 재설계. Single-Flight 패턴의 다섯 불변식(promise sharing, sync throw normalization, force release, deadline, capacity), 9종 에러 카테고리 분류기, Resilience4j 다섯 모듈(CircuitBreaker, Retry, Bulkhead, RateLimiter, TimeLimiter) 적용.

## 기술 스택

| 영역 | 사용 기술 |
|------|-----------|
| 언어 | TypeScript, JavaScript, Java, Kotlin |
| 프레임워크 | NestJS, Node.js, Spring Boot, Spring Batch |
| 데이터베이스 | MySQL 8, Aurora, Oracle, PostgreSQL |
| 캐시 / 락 | Redis (ioredis, 분산 락, Token Bucket), Redisson |
| 메시징 | RabbitMQ (Quorum Queue, DLX), Kafka |
| 검색 | Elasticsearch, Logstash |
| 외부 의존성 격리 | Resilience4j, Custom Retry / Timeout |
| 헤드리스 브라우저 | Playwright, Camoufox |
| 부하 / 관측 | Prometheus, Grafana, Datadog APM, nGrinder |
| 테스트 | Jest, Testcontainers, JUnit 5, Kotest |
| 인프라 | Docker, AWS ECS, Naver Cloud, Jenkins, GitHub Actions |

## 교육

**F-Lab Java Backend Mentoring** ｜ 2024.01 ~ 2024.07
Meta 시니어 개발자 멘토링 과정 수료. 객체지향 설계, 트랜잭션 처리, 클린 아키텍처 중심으로 동시성 제어, CQRS, 분산 트랜잭션을 심화 학습했습니다.

**경기대학교 컴퓨터과학과 졸업**
