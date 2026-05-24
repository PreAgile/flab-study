# resume_v16.docx JD 대조 피드백

대상:

- 이력서: `resume/resume_v16.docx` / 분석 기준 `resume/resume_v16.md`
- JD 기준 문서:
  - `/Users/meyonsoo/Desktop/lemong/project/cj/portfolio-docs/docs/jd-mapping/README.md`
  - `/Users/meyonsoo/Desktop/lemong/project/cj/portfolio-docs/docs/career/COMPANY-PRIORITY.md`
  - `/Users/meyonsoo/Desktop/lemong/project/cj/portfolio-docs/docs/career/SIGNAL-CHECKLIST.md`

전제: 사용자가 의도한 것처럼 이 문서는 “최종 제출본”이라기보다, 제출본을 만들기 위한 **마스터 원고**에 가깝다. 실제 문제를 많이 담아 “깊게 파는 개발자”를 보여주려는 방향은 맞다. 다만 국내 빅테크/대기업 백엔드 담당자가 5년차+ 백엔드 후보를 빠르게 스크리닝한다고 보면, 지금 상태 그대로 제출하기에는 과밀하고 검증 리스크가 있다.

## 한 줄 결론

내용의 깊이는 강하다. 하지만 제출본으로는 너무 많은 사례와 너무 많은 링크가 한 번에 들어가 있어, “깊게 파는 사람”보다 “모든 걸 다 말하려는 사람”으로 읽힐 위험이 있다. 최종본은 이 원고에서 4~6개 핵심 사례만 남기고, 나머지는 부록/포트폴리오 링크로 보내는 편이 낫다.

## JD 관점에서 좋은 점

### 1. A군 회사 JD 키워드와 정면으로 맞는 자산이 많다

`portfolio-docs`의 A군은 토스 / 네이버페이 / 당근페이로 잡혀 있고, 반복 키워드는 결제 정합성, 멱등성, 분산락, Kafka/Outbox, Kotlin/Spring, Resilience4j, Single-Flight, 외부 의존성 격리다.

이력서에는 이 키워드가 모두 들어 있다.

- 결제 멱등성 / 정합성: webhook 4중 멱등성, reconciliation
- 분산락: SETNX + Lua, Redisson 재설계, ShedLock
- 메시징/Outbox: RDS queue → Kafka Outbox 재설계
- Kotlin/Spring: Java/Spring/JPA, Kotlin/Coroutines, Resilience4j로 재설계
- 외부 의존성 격리: IP 평판, Bulkhead, Circuit Breaker, Single-Flight

이 조합은 5년차 백엔드 후보로는 강한 편이다. 특히 결제/외부 의존성/동시성 쪽은 JD와 잘 맞는다.

### 2. “운영에서 실제로 맞은 문제”라는 느낌이 있다

단순 CRUD 경험이 아니라 결제 중복, 정합성 불일치, 세션 race, 봇 탐지, worker OOM, cron 중복 실행처럼 실제 운영에서 발생하는 문제를 다룬다. 이건 좋다.

국내 빅테크 백엔드 면접관이 좋아하는 신호는 보통 다음이다.

- 장애가 어떻게 발생했는지 설명할 수 있는가
- 왜 단순한 해결책으로 부족했는지 말할 수 있는가
- 락/트랜잭션/큐/외부 API/관측을 같이 볼 수 있는가
- 수치와 로그로 검증했는가

이력서는 이 네 가지를 상당히 많이 충족한다.

### 3. OSS 시그널이 좋다

Kotest PR 6개 merge, Armeria PR merge, Spring Batch / Spring Cloud Gateway 이슈 분석은 JVM 전환을 말로만 하지 않는다는 증거다.

특히 확인 결과:

- Kotest #5905는 `MERGED`, +355/-16, 2026-04-14 merge
- Armeria #6683은 `MERGED`, reviewDecision `APPROVED`, 2026-04-07 merge
- Spring Batch #3946은 아직 `OPEN`이지만, 본인 댓글로 #5395 draft PR을 언급함
- Spring Batch #4478은 `OPEN`, `type: bug` 라벨과 maintainer의 “bug” 인정 코멘트가 있음
- Spring Cloud Gateway #3311 / #4024도 본인 코멘트와 maintainer 응답이 확인됨

다만 이력서에는 Armeria를 아직 “리뷰 중”처럼 쓰는 흔적이 있어 최신 상태로 바꾸는 것이 좋다.

## 제출 전 반드시 고쳐야 할 리스크

### 1. GitHub 링크가 다수 깨져 있다

가장 먼저 고쳐야 한다. `commerce-*` repo 자체는 존재하지만, 이력서의 여러 blob 링크가 실제 파일 경로와 맞지 않는다. 담당자가 클릭했을 때 404가 나면 내용 전체 신뢰도가 바로 떨어진다.

예시:

- `commerce-comment-platform-be/docs/adr/ADR-004-distributed-lock.md` 링크가 이력서에 있지만, 현재 repo tree에는 `docs/adr/` 파일들이 보이지 않고 `docs/learning-notes/`와 `docs/study-guide/` 중심이다.
- `ADR-005-outbox-cdc.md`로 링크했지만 실제 파일은 `docs/adr/ADR-005-outbox-polling-to-cdc.md`
- `ADR-MQ-008-consumer-idempotent.md`로 링크했지만 실제 파일은 `docs/adr/ADR-MQ-008-consumer-idempotency-dlq.md`
- `ADR-MQ-007-reader-4.md`로 링크했지만 실제 파일은 `docs/adr/ADR-MQ-007-reader-strategy.md`
- `ADR-SCR-009-session-cache.md`로 링크했지만 실제 파일은 `docs/adr/ADR-SCR-009-3-layer-session-cache.md`
- `ADR-SCR-010-bulkhead.md`로 링크했지만 실제 파일은 `docs/adr/ADR-SCR-010-bulkhead-isolation.md`
- `ADR-007-cb-threshold.md`로 링크했지만 실제 파일은 `docs/adr/ADR-007-circuit-breaker-thresholds.md`
- `EXP-WC-01-webclient.md`로 링크했지만 실제 파일은 `docs/experiments/webclient-async-vs-sync-lab/EXP-WC-01-throughput.md`
- `ADR-SCR-008-single-flight.md`로 링크했지만 실제 파일은 `docs/adr/ADR-SCR-008-single-flight-coordinator.md`

수정 방향:

- 제출 전 `resume_v16.md`의 GitHub 링크를 전부 실제 repo tree와 맞춰야 한다.
- 외부 담당자가 접근할 수 없는 private repo라면 링크를 그대로 넣는 게 오히려 손해다.
- private repo를 공개하지 않을 거면, 링크는 공개 가능한 `portfolio-docs` 또는 블로그/OSS PR 중심으로 줄여야 한다.

### 2. portfolio-docs의 현재 상태와 이력서의 주장이 충돌한다

`portfolio-docs/README.md`는 2026-04-30 기준으로 “구현 repo 미생성 / 실측값 0%”라고 쓰여 있다. 반면 이력서에서는 `commerce-*` 저장소, ADR 49건, 실험 47건, 여러 실측 링크를 현재 자산처럼 말한다.

물론 현재 GitHub에는 `commerce-comment-platform-be`, `commerce-batch-orchestrator`, `commerce-external-gateway-kt` repo가 존재한다. 문제는 `portfolio-docs` README가 오래된 상태로 남아 있다는 점이다.

수정 방향:

- `portfolio-docs`가 외부에 노출된다면 README의 현재 상태를 먼저 업데이트해야 한다.
- 이력서에는 `운영 실측`, `재설계 실험`, `가설`, `외부 사례`를 명확히 구분해야 한다.
- 특히 `실측`이라는 단어는 검증 가능한 파일/그래프가 있을 때만 써야 한다.

### 3. 현재 문서는 “제출 이력서”가 아니라 “마스터 원고”다

658라인짜리 이력서에 15개 사례, 다이어그램, JVM/Spring 재설계, OSS, 기술 스택, 이전 경력까지 모두 들어 있다. 이건 정보량이 너무 많다.

실제 담당자 관점:

- 1차 스크리닝에서는 전체를 다 읽지 않는다.
- 첫 1~2페이지에서 포지션 매칭이 보여야 한다.
- 너무 많은 사례가 있으면 핵심 강점이 흐려진다.
- 모든 사례가 비슷한 깊이로 설명되면, 무엇이 진짜 대표 성과인지 모른다.

이 원고는 “나의 원천 데이터”로는 좋다. 하지만 회사 제출본은 여기서 잘라야 한다.

### 4. JVM/Spring 재설계가 너무 자주 반복된다

각 사례마다 `JVM/Spring 재설계`가 붙어 있다. 의도는 좋다. Node/Nest 운영 경험을 JVM 백엔드 JD에 맞게 번역하려는 전략이다.

하지만 반복되면 역효과가 있다.

- “실제 Spring 운영 경험인가, 학습/재현 프로젝트인가?”가 헷갈린다.
- 매 사례마다 재설계를 붙이면 본문 흐름이 끊긴다.
- 진짜 운영 성과와 개인 재설계 실험이 같은 무게로 보일 수 있다.

수정 방향:

- 본문에서는 운영 사례 중심으로 쓰고, `JVM/Spring 재설계`는 별도 섹션 하나로 합친다.
- 각 사례에는 “Spring/JVM 면접 연결 키워드” 한 줄만 남긴다.
- 예: `Spring 매핑: @Transactional 경계, Redisson, QueryDSL, ShedLock`

### 5. “봇 탐지 우회”는 전면 배치에 신중해야 한다

Akamai, stealth fork, human-like mouse jitter, Click Loop는 기술적으로 깊지만, 대기업 백엔드 담당자에게는 애매하게 읽힐 수 있다.

위험:

- 보안/정책 우회 느낌이 강하다.
- 백엔드 역량보다 크롤링/우회 역량으로 포지셔닝될 수 있다.
- 결제/정합성/Kafka/Spring 쪽 메시지를 밀어낸다.

수정 방향:

- 제목과 자기소개에서는 `봇 탐지 우회`를 전면에 두지 않는 편이 낫다.
- `외부 의존성 격리`, `세션 안정성`, `장애 격리`, `외부 플랫폼 가용성`으로 표현을 바꾸는 게 안전하다.
- Akamai 상세 구현은 부록이나 포트폴리오 상세 사례로 보내는 게 좋다.

## 무엇을 남기고 무엇을 줄일지

### 최종 제출본에 남길 핵심 5개

1. **결제 webhook 멱등성 + reconciliation**
   - Toss / NaverPay / KakaoPay / Coupang Pay 계열에 가장 강하게 맞는다.
   - 현재 사례 1과 사례 2는 합치는 편이 낫다.
   - 메시지: “중복 결제 방어 + 사후 정합성 탐지까지 end-to-end로 설계”

2. **RDS queue / 작업 큐 / 계정 단위 동시성**
   - 대규모 작업 처리, 멀티 워커, CAS, 장애 복구를 보여준다.
   - 사례 5와 사례 6을 하나의 “대량 작업 처리” 사례로 묶을 수 있다.
   - 메시지: “외부 플랫폼 제약 때문에 계정 단위 순차 / 계정 간 병렬로 처리량을 확보”

3. **세션 락 레지스트리 또는 Single-Flight**
   - 둘 다 남기면 비슷하게 느껴진다.
   - 제출본에는 하나만 깊게 남기고, 다른 하나는 한 줄 보조 사례로 돌리는 게 좋다.
   - 당근/라인/Kotlin/Coroutines 쪽은 Single-Flight가 더 좋고, 운영 안정성 쪽은 세션 락이 더 좋다.

4. **IP 평판 시스템 / 외부 의존성 격리**
   - 비용 절감 수치가 강하다: 월 800만 → 90만, 성공률 70% → 98%.
   - 다만 “프록시”와 “우회” 느낌보다 “외부 의존 제거 / 장애 격리 / 비용 최적화”로 써야 한다.

5. **BIZ 대시보드 2단계 쿼리 / SQL VIEW / QueryDSL 매핑**
   - 우아한형제들, 카카오, 네이버 쪽에서 JPA/QueryDSL/SQL 역량을 보여주기 좋다.
   - 결제/외부 의존성만 있으면 “운영 스크립트형 백엔드”로 보일 수 있는데, 이 사례가 일반적인 API/DB 설계 역량을 보완한다.

### 줄이거나 부록으로 보낼 사례

- 쿠폰 멱등 적용: 결제 멱등성 사례에 흡수 가능
- 매장 일괄 등록: 비관락 사례로 좋지만 우선순위는 낮음
- 고사양 헤드리스 브라우저 물리서버 운영: 강하지만 너무 특수함. 한 줄 운영 스케일로 축약
- Akamai Bot Manager 우회: 상세 구현은 부록. 제출본 전면에는 비추천
- 부정 리뷰 탐지: AI/ML 역할 지원이 아니면 우선순위 낮음
- SafeCron: 좋은 운영 패턴이지만 핵심 사례보다는 공통 인프라 한 줄
- 자동 답글 파이프라인: 운영 자동화 사례로 좋지만 결제/동시성/외부 격리보다 후순위

## JD별 맞춤 제출 방향

### Toss / TossPayments

가장 강하게 밀어야 할 것:

- 결제 webhook 멱등성
- reconciliation
- 트랜잭션 경계
- 외부 PG 호출 보호
- Kafka/Outbox 재설계는 보조

보강할 것:

- “ACK와 실제 처리 완료의 분리”를 더 명확히 쓰면 좋다.
- 결제 도메인에서 왜 `락만으로 부족한지`, 왜 `키만으로 부족한지`를 2문장으로 정리해야 한다.
- `운영 실측`과 `재설계 실험`을 분리해야 한다.

### NaverPay / Line

가장 강하게 밀어야 할 것:

- 대량 트래픽 처리
- 외부 의존성 격리
- 관측/부하 테스트
- Armeria OSS
- nGrinder / JFR / WebClient 비동기 실험

보강할 것:

- 현재 이력서에는 nGrinder가 기술 스택에는 있지만 대표 사례에는 약하다.
- `p95/p99`, `처리량`, `가용률`, `consumer lag` 같은 수치가 더 전면에 필요하다.
- Armeria PR은 “리뷰 중”이 아니라 “MERGED”로 고쳐야 한다.

### Daangn Pay

가장 강하게 밀어야 할 것:

- Java + Kotlin 양쪽 가능
- Kotlin Coroutines
- Single-Flight
- Resilience4j
- 외부 PG/외부 API adapter 설계

보강할 것:

- K8s 경험 약점을 정직하게 처리해야 한다.
- Docker Compose / 물리서버 운영을 “K8s 대체 경험”처럼 과장하지 말고, 자원 격리와 무중단 배포의 추상 패턴으로 설명하는 편이 낫다.

### Woowa / KakaoPay / KakaoBank

가장 강하게 밀어야 할 것:

- Spring/JPA/QueryDSL
- 트랜잭션 전파/격리수준
- Spring Batch
- Kafka / Outbox / DLQ
- 결제/정산 정합성

보강할 것:

- 현재 이력서의 실무 메인 스택은 NestJS/TypeORM이다. Spring/JPA는 OSS + 재설계 프로젝트라는 점을 숨기면 안 된다.
- 대신 “운영 문제를 JVM/Spring으로 재현하고 검증했다”는 포지셔닝으로 가야 한다.
- QueryDSL/Batch/Outbox 관련 링크가 깨지지 않도록 정리해야 한다.

## 문서 구조 제안

최종 제출본은 아래 구조가 좋다.

```md
# 김면수 | Backend Engineer

## Summary
- 5년차 백엔드, 결제 정합성 / 대량 배치 / 외부 의존성 격리 중심
- 운영 수치 3개
- JVM/Spring 전환 시그널 1개
- OSS 시그널 1개

## Core Impact
| 영역 | 성과 | 근거 |

## Open Source
- Kotest 6 PR merged
- Armeria #6683 merged
- Spring Batch / SCG issue analysis

## Experience
### Lemong
1. 결제 멱등성 + reconciliation
2. 대량 작업 큐 + 계정 단위 동시성
3. 외부 의존성 격리 + 세션 안정성
4. DB/API 설계: BIZ 대시보드 2단계 쿼리

### JVM/Spring Re-design
- Node 운영 자산을 Java/Kotlin/Spring으로 재현
- repo 3개, ADR/실험 수치, 대표 링크

### I-BRICKS
- Kafka/Nifi/Elasticsearch 데이터 파이프라인
```

## 자기소개/첫 페이지 피드백

현재 자기소개는 강하지만 키워드가 너무 많다.

현재 첫 문장:

> 결제·배치·외부 플랫폼 연동·분산 워커 환경에서 멱등성, 트랜잭션 정합성, 동시성 제어, 장애 격리, 봇 탐지 우회를 설계해 온 5년차 백엔드 엔지니어입니다.

추천 방향:

```md
결제 정합성, 대량 배치, 외부 의존성 격리를 중심으로 운영 시스템을 설계해 온 5년차 백엔드 엔지니어입니다. 
NestJS 기반 SaaS 운영에서 얻은 멱등성·트랜잭션·분산락·작업 큐 패턴을 Java/Kotlin/Spring 환경으로 재설계하며 JVM 백엔드 역량을 확장하고 있습니다.
```

`봇 탐지 우회`는 첫 문장에서 빼는 게 낫다. 이력서 본문에서 외부 플랫폼 안정화 사례로 보여주면 충분하다.

## 기술 스택 피드백

현재 기술 스택 표는 너무 넓다. `알고 있는 것`, `운영한 것`, `재설계한 것`, `실험한 것`이 섞여 있다.

수정 방향:

- `Production`: TypeScript/NestJS, TypeORM, MySQL/Postgres, Redis, RabbitMQ/Quorum Queue, Docker, Grafana/APM
- `JVM/Spring`: Java/Kotlin, Spring Boot, JPA, QueryDSL, Spring Batch, Redisson, Resilience4j, Kafka
- `Evidence`: Kotest, Armeria, ADR/experiments, Testcontainers/JUnit/Kotest

이렇게 나누면 “Spring 실무를 과장한다”는 느낌이 줄고, 전환 전략이 더 정직하게 보인다.

## 보강해야 할 내용

### 1. 내 역할 범위

각 사례에서 본인이 어떤 범위를 책임졌는지 더 명확해야 한다.

예:

- 설계 주도 / 구현 / 운영 배포 / 장애 대응 / 모니터링 구축 중 어디까지 했는가
- 혼자 했는가, 팀과 했는가
- 의사결정권이 있었는가, 개선 제안이었는가

국내 대기업 담당자는 “기술을 아는 사람”보다 “실제 책임을 져본 사람”인지 본다.

### 2. 운영 수치의 성격

현재 수치가 많지만 성격이 섞여 있다.

- 운영 실측
- 운영 로그 기반
- 재설계 실험
- 외부 사례 기반
- 추정

이 다섯 가지를 구분해야 한다. 특히 `실측`이라는 단어는 강한 만큼 검증 리스크도 크다.

### 3. Spring/JPA 실전성

JVM JD를 노리는 방향은 맞다. 다만 핵심 약점은 “실무 메인 스택이 NestJS이고, Spring/JPA는 재설계/OSS/학습 자산이라는 점”이다.

이를 숨기지 말고 이렇게 처리하는 게 낫다.

```md
운영 문제는 NestJS 환경에서 직접 겪었고, 동일 문제를 Java/Kotlin/Spring/JPA 환경에서 재현하며 ADR과 실험으로 검증했습니다.
```

이 문장이 있으면 오히려 정직하고 강하다.

### 4. Kafka 운영 깊이

JD 문서상 Kafka/Outbox는 핵심이다. 이력서에도 Kafka가 나오지만, 현재 Lemong 사례는 메시지 큐/Quorum Queue와 RDS queue 중심이고 Kafka는 재설계 프로젝트 쪽 비중이 크다. I-BRICKS EBS 파이프라인에는 Kafka 경험이 있으니, 이걸 더 명확히 살리는 게 좋다.

보강 방향:

- I-BRICKS 경력에서 Kafka/Nifi/Elasticsearch 파이프라인의 역할과 장애/처리량을 1~2줄 더 구체화
- 재설계 프로젝트에서는 Kafka/Outbox를 “운영 경험”이 아니라 “재현/실험/ADR”로 명확히 표기

## 최종 제출 전 체크리스트

1. GitHub 링크 전수 클릭 검증
2. private repo 링크 제거 또는 public mirror 준비
3. `portfolio-docs` README 현재 상태 업데이트
4. Armeria #6683 상태를 `MERGED`로 수정
5. 15개 사례를 4~6개 핵심 사례로 압축
6. `봇 탐지 우회` 표현을 첫 페이지에서 제거
7. `운영 실측 / 재설계 실험 / 가설 / 외부 사례` 라벨 분리
8. `JVM/Spring 재설계` 반복 섹션을 하나로 통합
9. 기술 스택을 Production / JVM Re-design / Evidence 로 분리
10. 회사별 제출본을 최소 2개로 나누기

## 최종 판단

이력서의 방향은 맞다. 실제 문제를 많이 써서 깊이를 보여주려는 전략도 맞다. 다만 최종 제출본에서는 모든 깊이를 본문에 다 넣으면 안 된다. 깊이는 “대표 사례 4~6개 + 검증 가능한 링크”로 보여줘야 한다.

현재 원고는 raw material로는 좋고, 제출본으로는 아직 과하다. 특히 깨진 링크와 private repo 접근 문제는 제출 전에 반드시 막아야 한다. 이 두 가지를 고치지 않으면, 내용이 좋아도 담당자가 검증하는 순간 신뢰 손실이 생긴다.
