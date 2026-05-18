# 김면수

백엔드 개발자

010-9101-5429 ｜ digle117@gmail.com
github.com/PreAgile ｜ astro-paper-23v.pages.dev

---

분산 환경에서 트랜잭션 일관성을 지키는 일, 비동기 메시징으로 처리량을 늘리는 일, 그리고 트래픽이 일정 수준을 넘어가면서 단순한 구조가 한계에 부딪히는 지점을 찾아 풀어내는 일에 관심이 많습니다.

현재 르몽에서 6개 배달 플랫폼을 통합 관리하는 리뷰 SaaS의 백엔드를 담당하며, Node.js/NestJS 기반 운영 시스템에서 분산 작업 큐, 세션 일관성, 멱등성, 외부 의존성 격리, 관측 기반 장애 대응을 다뤄왔습니다. 일평균 API 호출 20만 건, 페이지 수집 100만 건, 리뷰 수집 12만 건 규모를 RabbitMQ, Redis, Aurora, ECS, Prometheus/Grafana 위에서 안정적으로 운영하고 있습니다.

이 운영 경험을 Kotlin/Spring Boot/JPA 환경에서 동일하게 재현하고 비교하는 재설계 프로젝트를 진행하고 있으며, 그 과정에서 **Kotest organization 정식 멤버로 6개 PR을 머지**하고 **Armeria에 MDC 확장 PR을 머지**하는 등 JVM 오픈소스 리뷰 사이클을 통해 생태계 적응력을 검증하고 있습니다.

## 오픈소스 기여

JVM 생태계의 주요 프로젝트에 정기적으로 기여하면서, 메인테이너와의 코드 리뷰 사이클을 통해 운영 외부에서의 코드 품질도 검증하고 있습니다.

**Kotest** — Kotlin 테스트 프레임워크 (GitHub 4.7k stars)
2026년 3월 메인테이너 sksamuel의 직접 초대로 organization 정식 멤버가 되어 약 한 달간 **6개 PR을 머지**했습니다. 가장 임팩트 있는 작업은 JVM/JS/Wasm/Native 멀티플랫폼 환경에서 Spec/Test/TestCase 계층을 통합하는 **타입 안전한 Test Metadata Public API를 신규 설계**한 PR #5905(+355/-16)입니다. 그 외 JSON Schema anyOf/oneOf 표준 구현(#5807), Kotlin 내부 어노테이션을 활용한 타입 안전 어설션(#5789), 컬렉션 data class 필드 단위 diff(#5835), JSON Matchers 커스텀 파서 지원(#5795), 어설션 체이닝(#5756)을 머지했습니다.

**Armeria** — LINE의 Java 기반 비동기 RPC 프레임워크
요청/응답 컨텍스트를 Logback MDC로 export하는 **BuiltInProperty 확장 PR을 머지**(#6683, +339/-5)했습니다. HTTP/2 비동기 타이밍, RequestContext 기반 ThreadLocal 추적, NullAway 정책 준수를 함께 다룬 작업입니다.

**Spring Batch**
fault-tolerant step의 chunk scanning 메커니즘이 4년 이상 공식 문서에 누락되어 있던 이슈 #3946을 해결하는 PR(#5395)을 제출하고 메인테이너 응답을 대기 중입니다.

**Spring Cloud Gateway**
WebFlux 기반 필터 구현, Apache HttpClient5 쿠키 매니저 옵션 등 코어 모듈 기여 후보를 분석 중입니다.

## 경력

### 르몽 (Lemong)
백엔드 개발자 ｜ 2024.11 ~ 현재

자영업자와 프랜차이즈 본사를 위한 리뷰 통합 관리 SaaS '댓글몽'을 운영합니다. 배달의민족, 요기요, 쿠팡이츠, 네이버, 땡겨요, 먹깨비 6개 플랫폼의 리뷰를 통합 수집/분석하고 자동 댓글과 불만족 리뷰 알림 기능을 제공하고 있습니다. 일평균 API 호출 20만 건, 페이지 스크래핑 100만 건, 리뷰 수집 12만 건 규모를 처리하며, 플랫폼별로 30개 이상의 worker가 병렬로 동작합니다.

**멀티플랫폼 통합 인증과 세션 관리**
플랫폼마다 다른 로그인 정책(2FA, captcha, device verification, IP 차단)을 Playwright와 Camoufox 스텔스 브라우저를 활용한 비동기 세션 모듈로 통합 처리. worker 30개 이상이 같은 매장에 동시 접근할 때 발생하던 중복 로그인 문제를, FIFO 큐와 lease TTL 기반의 SessionLockRegistry로 풀어내 **세션 유지율 99.2% (최근 6개월 운영 지표)**를 유지하고 있습니다. 8가지 로그인 분기는 ScrapperException 계층 구조로 일원화해 장애 복원이 자동으로 흐르도록 설계했습니다.

**스크래퍼 비동기 파이프라인 진화**
외부 플랫폼 댓글 등록은 건당 3~5분이 걸리는 무거운 IO 작업입니다. 처음에는 사용자 동기화 요청이 들어오면 cmong-be가 즉시 응답하기 위해 RabbitMQ의 reply-request-reply 패턴으로 작업을 분리해 ALB 타임아웃 문제를 풀었습니다. 이 구조가 일괄 댓글이나 마케팅 캠페인처럼 수천~수만 건이 동시에 트리거되는 시나리오에서 한계에 부딪히면서, 별도 오케스트레이터 서비스와 RabbitMQ Quorum Queue 기반 파이프라인으로 한 단계 더 분리하는 작업을 진행 중입니다.

- API는 검증 후 bulk INSERT와 202 응답만 수행
- SELECT FOR UPDATE SKIP LOCKED로 예약 작업 picking
- DLX 기반 단계적 재시도와 플랫폼별 prefetch / concurrency 분리
- 사용자 시간대 예약 등록과 Stage 1 취소 윈도우 확보

댓글 자동화의 중복 등록은 Idempotency-Key UNIQUE 제약, 상태머신, Redis 응답 캐싱, 일일 reconciliation의 네 단계로 막아 **댓글 등록 중복 0건 (최근 6개월 기준)**을 유지하고 있습니다.

**프랜차이즈 멀티테넌트 구조 (댓글몽 Biz)**
프랜차이즈 본사가 **1,000개 매장**을 한 화면에서 관리할 수 있도록 매장별 세션을 격리. Token Bucket Rate Limiter와 Worker Queue를 조합하고, 한 매장은 한 worker에 고정되는 sticky session 라우팅을 적용해 세션 thrashing을 줄였습니다. 그 결과 **플랫폼 API 차단률이 90% 감소**하고 전체 리뷰 처리량은 **6배**로 늘었습니다.

**마케팅 댓글 예약 비동기 실행**
캠페인마다 수만 건의 예약 댓글이 동시에 트리거되면서 단순 cron 폴링이 DB 락 컨텐션을 유발하던 문제를, Aurora 기반 예약 큐 테이블과 Aurora Consume 패턴(메시지 큐 수준의 비동기 실행)으로 재설계. Redis Pub/Sub로 상태를 추적하고 지수 백오프로 멱등 재시도를 구현해 **TPS 1,000/s 이상 (Aurora 부하 테스트 기준), 예약 실패율 1% 이하, 처리 지연 10초 미만**을 안정적으로 유지하고 있습니다.

**PAMS — 자체 프록시 풀 관리·모니터링 시스템**
외부 Decodo Residential Proxy 의존도가 높아 비용이 매월 **800만 원**에 달하고 외부 장애가 곧 서비스 중단으로 이어지던 구조를, 자체 Datacenter 프록시 풀과 IP 평판 관리 시스템(PAMS, Proxy Allocation Management System)으로 전환. port-IP 매핑을 영구화하고 매장별 sticky pool을 적용했으며, 성공률/타임아웃/응답 지연 세 지표를 기준으로 한 자동 Cooldown 알고리즘으로 장애 IP를 격리하고 트래픽을 재분산합니다.

전환 이후 **월 비용은 800만 원에서 90만 원으로(88.75% 절감), 요청 성공률은 70%에서 98%(프록시 전환 후 운영 대시보드 기준)**로 개선되었고, Prometheus와 Grafana 기반 Health 대시보드로 가용성을 실시간 추적할 수 있게 되었습니다.

### 아이브릭스 (I-BRICKS)
백엔드 개발자 ｜ 2021.05 ~ 2024.11

한국어 자연어 처리 전문 기업으로 검색 시스템, 데이터 파이프라인, 챗봇 개발을 담당했습니다.

**한국 금융연수원 강의 검색·추천 시스템**
동영상 강의 플랫폼의 검색과 추천 기능을 Elasticsearch 기반으로 구축. RDB 덤프를 Logstash로 정기 색인해 Elasticsearch에 적재하는 파이프라인을 만들고, 그 위에 사용자별 강의 시청 로그와 신규 강의 진입 로그를 기반으로 한 추천 시스템을 얹었습니다. 시청 시간, 카테고리 선호도 등 필드별로 가중치를 다르게 설정해 사용자별 맞춤 추천을 제공했고, 강의 메타데이터 검색도 같은 인덱스에서 처리해 검색과 추천 경로를 일원화했습니다.

**EBS 학습 시스템 데이터 파이프라인**
일일 **수천만 건**의 로깅 데이터를 안정적으로 수집하기 위해 Kafka 기반 비동기 메시징을 도입하고, Apache Nifi와 Elasticsearch 클러스터로 데이터 처리량이 두 배 늘어도 안정적으로 동작하도록 설계. 쿼리 응답 시간을 50% 단축했습니다.

**대법원 챗봇 도우미 (웹 프론트엔드)**
React, Redux, SCSS 기반 사용자 중심 UI를 구현했으며 KWCAG 2.1 웹 접근성 기준을 준수했습니다.

## Spring/Kotlin 백엔드 재설계 프로젝트

5년 동안 Node.js로 운영하며 부딪힌 분산 락, 결제 멱등성, 트랜잭션 분리, 외부 의존성 격리 같은 문제를 Java/Kotlin/Spring 환경에서 동일하게 재현하고, 같은 문제를 다른 도구로 풀 때의 trade-off를 측정해 ADR로 정리하는 작업입니다. 현재까지 **ADR 49건, 실험 47건, 기술 블로그 17편**을 누적했습니다.

- **commerce-comment-platform-be** (Java / Spring Boot / JPA): 결제 멱등성 4단계, Redisson watchdog 등 분산 락 4종 비교, MySQL InnoDB RR과 ANSI RR의 차이, 트랜잭션 분리 패턴(Saga, Outbox) 9개 시나리오, No-offset Pagination 적용.
- **commerce-batch-orchestrator** (Spring Batch + Kafka): RabbitMQ를 1주간 운영해 5가지 한계를 측정하고 Kafka 전환을 정당화하는 ADR 작성. Outbox Relay의 polling과 CDC 지연 비교, Spring Batch Reader 4종 매트릭스.
- **commerce-external-gateway-kt** (Kotlin / Coroutines / Resilience4j): 운영 자산을 Kotlin으로 재설계. Single-Flight 패턴의 다섯 가지 불변식, 9종 에러 카테고리 분류기, Resilience4j 다섯 가지 모듈 적용.

## 기술 스택

| 영역 | 사용 기술 |
|------|-----------|
| 언어 | TypeScript, JavaScript, Java, Kotlin |
| 프레임워크 | NestJS, Node.js, Spring Boot, Spring Batch |
| 데이터베이스 | MySQL 8, Aurora, Oracle, PostgreSQL |
| 캐시 / 락 | Redis (ioredis, 분산 락, Token Bucket), Redisson |
| 메시징 | RabbitMQ (Quorum Queue, DLX), Kafka |
| 검색 | Elasticsearch, Logstash |
| 외부 의존성 격리 | Resilience4j, Custom Retry/Timeout |
| 헤드리스 브라우저 | Playwright, Camoufox |
| 부하 / 관측 | Prometheus, Grafana, Datadog APM, nGrinder |
| 테스트 | Jest, Testcontainers, JUnit 5, Kotest |
| 인프라 | Docker, AWS ECS, Naver Cloud, Jenkins, GitHub Actions |

## 교육

**F-Lab Java Backend Mentoring** ｜ 2024.01 ~ 2024.07
Meta 시니어 개발자 멘토링 과정 수료. 객체지향 설계, 트랜잭션 처리, 클린 아키텍처 중심으로 동시성 제어, CQRS, 분산 트랜잭션을 심화 학습했습니다.

**경기대학교 컴퓨터과학과 졸업**
