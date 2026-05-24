# 김면수 ｜ Backend Engineer

`010-9101-5429`  ｜ `digle117@gmail.com` ｜ [github.com/PreAgile](https://github.com/PreAgile) ｜ [astro-paper-23v.pages.dev](https://astro-paper-23v.pages.dev)

---

## 자기소개

분산 환경에서 발생하는 **트랜잭션 일관성, 외부 의존성 격리, 세션 race condition, 봇 탐지 우회**의 네 축을 운영 트래픽 위에서 측정·검증해 온 5년차 백엔드 엔지니어입니다. 멀티 인스턴스 결제 webhook의 4중 멱등성, RDS Queue 낙관락 기반 worker pool, FIFO·lease TTL·cold-start guard로 직렬화되는 SessionLockRegistry, `_abck` 4-state 머신을 활용한 Akamai 우회를 한 시스템 안에서 모두 운영하고 있으며, 각 결정의 근거를 ADR과 PR 본문에 남기는 습관을 유지합니다.

현재 르몽에서 6개 배달 플랫폼(배달의민족·요기요·쿠팡이츠·네이버·땡겨요·먹깨비)을 통합 관리하는 리뷰 SaaS 「댓글몽」의 백엔드를 담당합니다. **일평균 API 호출 20만 건, 페이지 스크래핑 100만 건, 리뷰 수집 12만 건**을 4개 저장소(NestJS·Python·FastAPI·NestJS 워커)에서 RabbitMQ, Redis Cluster, Aurora MySQL, AWS ECS, Datadog 위에 운영합니다. 운영 자산을 Kotlin/Spring Boot/JPA 환경에서 동일 시나리오로 재설계하면서 결정 과정을 ADR로 남기는 작업을 병행하고 있으며, **Kotlin 테스트 프레임워크 Kotest의 organization 정식 멤버로 6개 PR을 머지**했고 **LINE Armeria**에 MDC export 확장 PR을, **Spring Batch**에는 4년 이상 누락되어 있던 chunk scanning 문서 보완 PR을 제출했습니다.

---

## 핵심 운영 지표

| 영역 | Before → After | 근거 |
|---|---|---|
| 프록시 풀 비용 | **월 800만 → 90만 원 (88.75% ↓)** | 자체 IP 평판 시스템 PAMS, 운영 청구서 |
| 요청 성공률 | **70% → 98%** | 프록시 전환 후 운영 대시보드 |
| 세션 유지율 | **99.2%** (최근 6개월) | SessionLockRegistry FIFO + lease TTL |
| 댓글 등록 중복 | **0건 / 6개월** | Idempotency-Key + 세션 락 조합 |
| Akamai 로그인 성공률 | **77.8% → 100%** (18/18 iter) | PR #644 Referrer Warming 측정 |
| 멀티 인스턴스 webhook race | **검출·차단 데이터 보유** | 운영 로그 `중복 웹훅 락 차단` |
| 오픈소스 | **Kotest 6 PR / Armeria 1 PR / Spring Batch 1 PR** | GitHub 머지 이력 |

---

## 오픈소스 기여

**Kotest** ｜ Kotlin 테스트 프레임워크 (GitHub 4.7k stars)
2026년 3월 메인테이너 sksamuel의 직접 초대로 organization 정식 멤버가 되어 약 한 달간 **6개 PR을 머지**했습니다. 가장 임팩트 있는 작업은 JVM/JS/Wasm/Native 멀티플랫폼 환경에서 Spec/Test/TestCase 계층을 통합하는 **타입 안전 Test Metadata Public API 신규 설계** (PR #5905, +355/-16) — 기존 sealed interface와의 호환성을 보존하면서 공개 API를 확장한 작업입니다. 그 외 JSON Schema anyOf/oneOf 표준 구현(#5807), Kotlin 내부 어노테이션 `@OnlyInputTypes`를 활용한 타입 안전 어설션(#5789), 컬렉션 data class 필드 단위 diff(#5835), JSON Matchers 커스텀 파서 지원(#5795), 어설션 체이닝(#5756)을 머지했습니다.

**Armeria** ｜ LINE의 Java 기반 비동기 RPC 프레임워크
RequestContextExporter의 BuiltInProperty에 request/response timing·content preview·serialization format·session protocol·host를 추가하고, Logback MDC export 경로의 테스트를 보강한 PR (#6683, +339/-5) 머지. 분산 트레이싱과 MDC를 한 곳에서 관리하기 위한 사내 요구에서 출발한 작업이었습니다.

**Spring Batch**
fault-tolerant step의 chunk scanning 메커니즘이 4년 이상 공식 문서에서 누락되어 있던 이슈 #3946을 해결하는 PR (#5395) 제출. retry 정책과 chunk scanning의 상호작용을 reference docs의 fault tolerance / scalability / chunk-oriented-processing 섹션에 보강, 메인테이너 응답을 대기 중입니다.

---

## 경력 — 르몽(Lemong) ｜ 백엔드 엔지니어 ｜ 2024.11 ~ 현재

### 시스템 개요

자영업자와 프랜차이즈 본사를 위한 리뷰 통합 관리 SaaS 「댓글몽 / 댓글몽 Biz」를 운영합니다. 일평균 **API 호출 20만 건, 페이지 스크래핑 100만 건, 리뷰 수집 12만 건** 규모를 처리하며, 플랫폼별 30개 이상의 worker가 병렬로 동작합니다. 책임은 4개 저장소로 분리되어 있습니다.

| 저장소 | 런타임 | 책임 영역 | 규모 |
|---|---|---|---|
| `cmong-be` | NestJS 11 / TypeScript | 사용자용 메인 API — 결제·쿠폰·알림톡·BIZ 멀티테넌트 | 137 controllers / 152 entities |
| `cmong-mq` | Python 3.9 | 배치 워커 — 2h cron · AI 스코어링 · 8색 Active-Active 배포 | 5,700+ 계정 / 13,000+ 매장 |
| `flow-be` | Python 3.12 / FastAPI | 운영 콘솔 · APScheduler · 잡 오케스트레이션 · BIZ 대시보드 | 잡 라이프사이클 Redis Hash·ZSet |
| `cmong-scraper-js` | NestJS 11 / Camoufox·Playwright | 6 플랫폼 스크래퍼 — SessionLockRegistry · Akamai 우회 · PAMS 프록시 풀 | Worker 30+/platform |

운영 인프라는 AWS ECS Fargate(`cmong-be`·`flow-be`) + Naver Cloud 자체 클러스터(`cmong-scraper-js` 8색) + RabbitMQ Quorum Queue + Redis Cluster(ElastiCache Serverless) + Aurora MySQL 8 위에 올라가며, 관측은 Datadog APM(span tagging), Prometheus + Grafana(프록시 풀 가용성), Slack Webhook(결제 정합성·cron 시작/완료/실패) 로 분산되어 있습니다.

> **[아키텍처 이미지 — A1] 전체 시스템 다이어그램**
> Excalidraw 추천 구성: Client(Web/Biz) → ALB → cmong-be(REST) → RabbitMQ(6 queue + DLQ) → cmong-scraper-js worker pool(SessionLockRegistry + Camoufox pool) → PAMS(IP 평판) → 6 외부 플랫폼. 옆 라인으로 cmong-mq 2h cron + flow-be 어드민. Observability 계층(Datadog/Prometheus/Slack)을 점선으로.

본문은 **결제·정산(A) → 멀티 워커 동시성·대량 데이터(B) → 외부 의존성 격리·봇 탐지 우회(C) → AI 파이프라인·운영 자동화(D)** 네 도메인 15개 사례를 **문제 → 해결 → 성과** 형태로 정리합니다.

---

## 도메인 A. 결제·정산 (`cmong-be`)

### 사례 1. 결제 webhook 4중 멱등성 — Redlock ABA + DB UNIQUE + Lua atomic release + 상태머신 ｜ 2025.09 ~ 운영 중

**문제** — PG사 Portone의 결제 webhook은 같은 `imp_uid`/`merchant_uid`로 **중복 호출되는 경로가 5종 이상** 존재합니다. ① Portone 자체 retry(5xx/timeout) ② 정기결제 schedule 1차 실패 후 fallback retry로 PAID/FAILED가 거의 동시 도착 ③ 결제 취소 후 재결제 ④ 부분 환불 상태 전이 ⑤ ALB keep-alive 재시도. 단순 INSERT 는 `billings` 이중 집계 → 매출 중복 → 알림톡 2회 발송 → `subscriptions` 중복 생성 → 다음 달 이중 과금까지 도미노로 이어집니다. ECS 다중 Task로 배포되므로 in-memory dedupe 가 불가능하고, TypeORM의 `findOne → save` 패턴은 read-modify-write 사이에 race window 가 존재합니다. Redis 락 단독으로는 TTL 만료 후 다른 워커의 락을 잘못 지우는 **ABA 문제**(Martin Kleppmann의 Redlock 분석에서 지적된 hazard)가 발생할 수 있고, DB UNIQUE 단독으로는 Portone retry 폭주를 1차에서 차단할 수 없으며, 상태머신만으로는 동시 INSERT race 를 막을 수 없습니다.

**해결** — 단일 도구로는 모든 race 를 막을 수 없다는 판단으로 **4중 방어선**을 의도적으로 곱셈으로 결합했습니다. ① Redis `SET NX EX` + `Date.now()` 토큰 = ABA-safe distributed lock(Stripe의 Idempotency Key 디자인과 같은 결, lock value 로 ownership 검증) ② DB UNIQUE on `mix_value = imp_uid + merchant_uid + status` = 최종 정합성 보루(1시간 dedupe window) ③ 상태머신 READY → PAID/FAILED/CANCELLED × action_type(CHANGE_BILLING_METHOD / RESERVE / CHANGE_PLAN) 분기 ④ Lua eval 로 `GET → 비교 → DEL` 원자 실행, 자신의 락만 해제. 각 방어선은 한 단계 약점을 다음 단계가 보완하도록 설계되었습니다 — Redis 가 일시 장애로 fail-open 되어도 DB UNIQUE 가 최종 차단, 상태 역전(PAID 뒤 FAILED 도착) 시 `mix_value` 가 다른 row 로 안전 격리.

```ts
// 4중 방어 — payments.service.ts:118
const lockValue = Date.now().toString();              // ① ABA-safe token
const acquired = await this.redis.setNX(lockKey, lockValue, 30);
if (!acquired) return { imp_uid, merchant_uid, status };   // 200 OK 즉시 — retry 폭주 차단

try {
  await this.portoneWebhookRepository.save({ ..., mix_value });  // ② DB UNIQUE
} catch (e) {
  if (e?.code === 'ER_DUP_ENTRY') return CONFLICT_REQUEST;
}
// ③ 상태머신 분기 (PAID/FAILED/CANCELLED × action_type)
// ④ Lua atomic release — 다른 워커의 락 보호
await this.redis.delIfValueMatches(lockKey, lockValue);
```

동일한 `setNX + Lua DEL` 패턴은 PR 후 `handlePromotionalUpgrade`, `changePlan`, `notifly-batch` 등 **8 곳 이상에서 재사용**되어 사내 분산 락 표준 라이브러리로 정착했습니다.

**성과**
- 운영 로그에 `중복 웹훅 락 차단: merchant_uid=..., status=...` 메시지가 정기적으로 검출되어 race 가 실제로 발생하고 코드 레벨에서 차단됨이 데이터로 입증됨.
- PR #1376, #1492 로 예약 결제 금액 불일치 시 Slack 자동 경고 추가 → 결제 정합성 모니터링 자동화.
- Datadog `tagDatadogSpan({'payment.amount_mismatch': true, 'payment.coupon_select.valid_count': N})` 으로 결제 정합성 메트릭이 APM 에 자동 집계.
- 사내 분산 락 패턴 표준화 — 동일 helper(`delIfValueMatches`) 8 곳 이상 재사용.

> **[아키텍처 이미지 — A2] webhook 4중 방어 시퀀스**
> Excalidraw 추천: Portone POST → ALB → API → ① Redis SET NX(token) → ② DB UNIQUE(mix_value) → ③ status 분기 → ④ Lua eval atomic DEL → 200 OK. 보완 라인으로 일일 reconciliation cron(사례 2). 각 단계가 어떤 hazard 를 막는지 주석.

---

### 사례 2. 결제 정합성 reconciliation — 좀비 schedule · 중복 빌링키 · admin override orphan 자동 탐지 ｜ 2025.10 ~ 운영 중

**문제** — 사례 1 의 4중 멱등성으로도 못 막는 **eventual inconsistency** 3종이 존재합니다. ① **좀비 schedule** — Portone 서버에는 schedule 이 살아있는데 DB 에는 cancel 로 기록 → 다음 결제일 자동 과금 ② **중복 빌링키** — 한 사용자에 `SCHEDULED` billing 이 2개 이상 잡혀 다음 결제일 이중 과금 ③ **admin override orphan** — 어드민이 구독을 2027년까지 수동 연장했는데 이전에 잡혔던 2026년 4월 자동결제 schedule 이 그대로 남아 active 기간 중에 또 결제. 셋 다 사용자 클레임과 환불 분쟁이 발생한 뒤에야 노출되는 「조용한 결함」 입니다. Portone API 호출은 분당 한도와 비용 제약이 있어 전체 N 명에 매일 호출은 불가능하고, DB 의 SCHEDULED 와 Portone 의 `schedule_status` 는 본질적으로 의미가 다른(DB 는 billing 단위, Portone 은 schedule 단위) eventual consistency 문제입니다.

**해결** — Stripe·Square 등 결제 PG 운영의 정석인 **「의심 대상 K << N 으로 압축 → 외부 호출 최소화 → 4-way 분기 자동 정정」** 패턴을 일일 cron + 어드민 수동 트리거 이중 진입점으로 구현. DB 차집합으로 의심 customer_uid 만 추리고, 추려진 K 명에 대해서만 Portone `getSchedulesByBillingKey` 호출, 응답을 4-way 분기 처리합니다.

```sql
-- issue 3: admin_override_orphan 정확 감지 — payment-sync.service.ts:250
SELECT activeSub.subscription_id, schedSub.schedule_at, schedBilling.merchant_uid
FROM subscriptions activeSub
INNER JOIN subscriptions schedSub ON schedSub.user_id = activeSub.user_id
INNER JOIN billings schedBilling ON schedBilling.subscription_id = schedSub.subscription_id
WHERE activeSub.status = 'ACTIVE'
  AND activeSub.end_date > NOW()
  AND schedSub.schedule_at > NOW()
  AND activeSub.end_date > DATE_ADD(schedSub.schedule_at, INTERVAL 1 MONTH);
-- 활성 구독 종료일이 다음 자동결제 예약보다 1개월 이상 뒤 = 이중결제 위험
```

응답 4-way 분기:
- Portone schedule 0개 → DB 좀비 → `SCHEDULED_CANCELLED` 정정
- 1개 → 정상
- 2개 이상 + billing.merchant_uid 와 다른 schedule → Portone scheduleCancel 호출
- API 무응답 → `notReponseMerchantUids` 기록 → Slack 알림

일일 cron 은 `@SafeCron` (사례 14) 으로 멀티 인스턴스 환경에서 한 번만 실행되도록 분산 락 적용.

**성과**
- 3종 inconsistency(`zombie_schedule` / `duplicate_billing_key` / `admin_override_orphan`) 자동 탐지 및 자동 정정.
- **사후 환불·CS 부담을 사전 탐지로 전환** — 매일 09:10 KST 운영자가 정합성 상태를 Slack 한 메시지로 수신.
- 운영 로그 `좀비 예약 점검 대상: K개 customer_uid (active S개 제외)` 로 압축률 명시 → Portone rate-limit 안에서 5분 cron 안에 완료.
- 같은 SQL 패턴(`end_date > DATE_ADD(schedule_at, INTERVAL 1 MONTH)`)이 단일 쿼리로 admin override 사고를 탐지.

---

### 사례 3. 쿠폰 멱등 적용 — 사전 검증 · 트랜잭션 · schedule fallback 보정의 3중 idempotency ｜ 2025.11 ~ 운영 중

**문제** — 쿠폰은 결제 흐름에 깊게 얽혀 있습니다(「첫달 무료」「2주년 두 달 무료」「프로모션 50%」 등 다양). 정기결제 schedule 등록 시점에 계산한 amount 와 **실제 결제 시점의 쿠폰 상태가 달라지는** silent failure 가 가장 위험합니다. schedule 등록 시 쿠폰 A 로 50% 할인 amount 로 등록했는데 다음 달 결제 시점에 쿠폰 A 가 만료/사용된 상태면 Portone 은 등록된 amount 그대로 결제 → 사용자가 손해. 추가로 마케팅 캠페인에서 같은 쿠폰 발급 API 가 중복 호출되어 동일 쿠폰이 두 번 발급되면 같은 쿠폰 다중 사용 버그가 발생합니다. 쿠폰 메타데이터 + 적용 가능 plan + 발급된 user 매핑을 한 번에 수정하는 어드민 API 는 부분 update 후 실패 시 데이터 정합성이 깨집니다.

**해결** — **3중 idempotency 레이어**: ① 사전 검증 — `createUserCoupon` 진입 시 `findOne(user, coupon)` 으로 기존 row 확인, 있으면 기존 row 를 그대로 반환(idempotent return) ② 트랜잭션 — 쿠폰 수정은 TypeORM `QueryRunner` 기반 명시적 트랜잭션(`startTransaction / commit / rollback / release`)으로 delete + add + update 를 한 단위로 묶음 ③ **schedule fallback 보정** — schedule 등록 직전에 `available userCoupons` 재조회 후 `amountWithUserCoupons` 로 다음 결제 시점에 실제 적용될 금액 계산 → 불일치 시 amount + `custom_data.coupon_id` 보정.

```ts
// schedule fallback 보정 — payments.service.ts:783
const { value: predictedAmount, coupon: predictedCoupon } = amountWithUserCoupons(
  plan.price, availableUserCoupons, undefined,
  customData.coupon_id?.[0],          // 명시적 coupon_id 우선
);
if (predictedCoupon && predictedAmount !== scheduleAnnotation.amount) {
  this.logger.warn(`schedule fallback 금액 보정: ${scheduleAnnotation.amount} → ${predictedAmount}`);
  scheduleAnnotation.amount = predictedAmount;
  customData.coupon_id = [predictedCoupon.coupon_id];
}
```

`amountWithUserCoupons` 단일 함수가 결제·schedule·change_plan·promotional upgrade 의 모든 흐름에서 재사용되어 DRY 유지. 「첫달 무료 → 스페셜 전환」 사이클은 `OfferingType.PROMOTIONAL` 분기로 `handlePromotionalUpgrade` 에 분산 락 + 전액 즉시 결제 + 다음 결제 예약을 한 트랜잭션으로 묶었습니다.

**성과**
- 운영 환경에서 `schedule fallback 금액 보정` 로그로 결제 정합성 차이가 사용자 손해 없이 자동 보정됨.
- 동일 쿠폰 중복 발급 0건 (UNIQUE(user_id, coupon_id) + `findOne` 사전 검증 결합).
- 쿠폰 수정 중 부분 update 사고 0건.
- PR #1380, #1377, #1372, #1353, #1495, #1505.

---

## 도메인 B. 멀티 워커 동시성 · 대량 데이터 처리

### 사례 4. 매장 일괄 등록 — `SELECT ... FOR UPDATE` 비관락 + 그룹 트랜잭션 경계 ｜ 2025.12 ~ 운영 중

**문제** — 댓글몽 Biz 는 프랜차이즈 본사가 **수백~수천 개 매장을 엑셀 1행 = 1 사장님 = 1~6 플랫폼 계정** 형식으로 한 번에 등록합니다. 한 행씩 순차 INSERT 는 1,000행에 수십 분이 걸리고, 같은 `(platform, platform_id)` 가 두 행에 있거나(사용자 실수) 다른 운영자가 동시 등록 시 `findOne → save` race 로 중복 PlatformAccount 가 생깁니다. TypeORM 기본 격리수준 REPEATABLE READ + UNIQUE 인덱스 조합은 race window 가 닫히지만 ER_DUP_ENTRY 에러 메시지의 사용자 가시성이 떨어지며, 1,000행을 한 트랜잭션으로 묶으면 한 사장님 에러로 전체 롤백되어 부분 성공/실패가 row 단위로 추적되지 않습니다.

**해결** — **`SELECT ... FOR UPDATE` 비관락 + 그룹 단위 트랜잭션 경계** 의 정통 패턴. 한 사장님(`groupKey = email + business_number`) 묶음을 별도 `@Transactional()` 메서드로 분리 — 그룹 = 트랜잭션 경계. 트랜잭션 내에서 `(platform, platform_id)` 행에 InnoDB X-lock 을 잡고, 충돌 시 `markGroupFailed` 가 그룹 전체를 명확한 사용자 메시지(`${platform} 계정 중복: 이미 등록됨`)로 marking. 재시도 멱등성은 단계별 `findOne` 우선 + 함수형 update(`attempt_count + 1`)로 race-free 카운터.

```ts
@Transactional()
private async processRegisterGroup(brandId: string, rows: BatchUserV2[]) {
  for (const r of rows) {
    const existing = await this.manager.getRepository(PlatformAccount)
      .createQueryBuilder('p')
      .where('p.platform = :platform AND p.platform_id = :platformId',
             { platform: r.platform, platformId: r.platform_id })
      .setLock('pessimistic_write')                    // SELECT ... FOR UPDATE
      .getOne();
    if (existing) return await this.markGroupFailed(rows, '중복: 이미 등록됨');
  }
  // user 조회/생성 → brand_user 조회/생성 → platform_account INSERT
}
```

상태머신은 `PENDING → VALIDATED → REGISTERING → REGISTERED | REGISTER_FAILED` 로 가시화하고, `last_error · last_attempted_at · attempt_count` 를 row 에 박아 운영자가 재업로드 없이 실패만 재시도할 수 있게 했습니다.

**성과**
- 1,000+ 매장 일괄 등록 지원, 부분 성공/실패가 row 단위로 정확히 표시.
- 같은 `platform_id` 동시 등록 시 중복 PlatformAccount row **0건**.
- 「엑셀 1,000행 중 950 성공, 50 실패」 시 실패한 50개만 재시도 가능 — 본사 운영 부하 절감.
- PR #1477 (refactor: 매장 일괄등록 v2 마이그레이션), PR #1453.

---

### 사례 5. 일괄 댓글 처리 — MySQL 을 큐로 쓰는 CAS 기반 RDS Queue ｜ 2025.10 ~ 운영 중

**문제** — 댓글몽 사용자는 「오늘 들어온 리뷰 100~1,000개에 한 번에 자동 댓글 등록」 을 자주 사용합니다. 외부 플랫폼 댓글 한 건 등록은 **3~5분 IO** — HTTP 동기 처리 시 ALB 5분 타임아웃 초과, 단일 인스턴스 in-memory queue 는 재배포 시 작업 유실, 같은 사용자 같은 플랫폼 계정으로 worker 2개가 동시 로그인하면 외부 플랫폼 봇 탐지에 걸려 그 계정 전체가 차단됩니다. RabbitMQ 는 stateful 관리·취소·예약·진행률 폴링에 안 맞고(fire-and-forget 에 최적), BullMQ 같은 외부 큐는 트랜잭션과 함께 묶기 어렵습니다.

**해결** — **MySQL 테이블을 큐로 사용**해 트랜잭션과 큐 책임을 한 곳에 묶고, 다중 워커 안전 픽업은 **TypeORM 낙관락 = CAS(Compare-And-Set)의 SQL 버전** 으로 구현. `updatedAt` 을 version 필드처럼 사용해 `UPDATE WHERE id=? AND status=WAITING AND updatedAt=originalUpdatedAt` 가 `affected=0` 이면 다른 인스턴스가 먼저 가져갔음을 인식합니다. 같은 플랫폼 계정 동시 사용은 픽업 SQL 에 `job.platformId NOT IN (runningPlatformIds)` 조건으로 차단 — 한 platform_account = 시점에 한 job.

```ts
// 다중 인스턴스 안전 픽업 — rds-queue.service.ts:788
const updateResult = await this.queueJobRepository.createQueryBuilder()
  .update(QueueJob)
  .set({ status: IN_PROGRESS, updatedAt: new Date(),
         statusMessage: `[[${this.instanceId}]] Processing` })
  .where('id = :id', { id: job.id })
  .andWhere('status = :status', { status: WAITING })
  .andWhere('updatedAt = :originalUpdatedAt',          // CAS
            { originalUpdatedAt: job.updatedAt })
  .execute();
if (updateResult.affected === 0) {
  this.logger.warn(`Job ${job.id} modified by another instance (optimistic lock failed)`);
  return false;
}
```

좀비 job 자동 복구는 부팅 시 `rescheduleJobsOnStartup` + 인스턴스 ID(`process.env.INSTANCE_ID`)를 `statusMessage` 에 박는 방식으로 처리. 진행률은 Redis 캐시 + `acquireProcessingLock` 분산 락으로 폴링 부하 감소.

**성과**
- 동시 처리 worker 최대 **30**(`QUEUE_CONFIG.MAX_CONCURRENT_WORKERS`), 같은 그룹 내 순차 + 다른 그룹 병렬로 처리량 극대화.
- 운영 로그 `Job ${id} modified by another instance (optimistic lock failed)` 정상 검출 — race 발생하나 차단됨이 데이터로 입증.
- **외부 플랫폼 중복 댓글 0건**, 인스턴스 재배포 무중단.
- `architecture.md` 「플랫폼 API 차단률 90% 감소」 의 핵심 메커니즘 — 동일 platform_account 직렬화.
- PR #1214 (feat: 일괄댓글 API 튜닝), PR #1180 (rds-queue 다중 워커 지원).

> **[아키텍처 이미지 — B1] RDS Queue + 진행률 캐시**
> Excalidraw 추천: 사용자 → BatchRepliesV2Service → (UserActiveJob 중복 트리거 차단) → reply N개 INSERT(BATCH_PENDING) + queue_job N개 INSERT(WAITING) → ECS Task ×N → findNextAvailableJob → 낙관락 UPDATE → 외부 플랫폼 → onJobCompleted → user_queue_job_groups++ → 사용자 폴링 ↔ Redis 캐시.

---

### 사례 6. 2시간 cron 리뷰 수집 — 5,700+ 계정 × 13,000+ 매장 hierarchical 동시성 ｜ 2025.10 ~ 운영 중

**문제** — `cmong-mq` 는 6개 외부 플랫폼에서 매장 사장님 리뷰를 2시간 주기로 가져와 Aurora MySQL 에 적재합니다. 운영 로그 기준 BAEMIN 단일 실행에서 **13,127 매장 / 5,719 `platform_id` 그룹 / 13,699 task**, CPEATS 단일 실행은 **5,989 매장 / 3,446 그룹** 을 처리합니다. 외부 플랫폼은 같은 계정으로 동시 다중 매장 호출 시 captcha/지역차단/세션 무효화(NAVER·CPEATS 특히 심함)되고, 매장 단위 ThreadPool 로 전부 동시 처리는 동일 계정 병렬 로그인 = 세션 충돌, 전부 순차는 13,000 × 3초 = 11시간으로 2시간 cron 안에 못 끝납니다.

**해결** — **「계정 단위 순차 / 계정 사이 병렬」 의 hierarchical 동시성 모델**. 외부 락 서비스 없이 process-local 자료구조 격리만으로 충분 — `(platform_id, platform_password)` 키로 매장을 묶은 그룹을 `ThreadPoolExecutor` 에 제출하면, 한 그룹은 한 worker thread 가 처음부터 끝까지 순차 처리합니다. Python GIL 이지만 I/O-bound(HTTP/DB)라 thread 가 적합하며, asyncio 대신 thread 를 택한 이유는 PonyORM 동기 API + 기존 `requests` 호환성.

```python
# 그룹 격리 — producer.py:569
def getPlatformIdGroupList(shop_ids):
    groups = {}
    for shop in shops:
        key = (shop.platform_id, shop.platform_password)
        groups.setdefault(key, {'shop_ids': [], 'platform': None})
        groups[key]['shop_ids'].append(shop.shop_id)
    return groups

# 그룹 사이 병렬, 그룹 내부 순차
with ThreadPoolExecutor(max_workers=W) as ex:
    for group in groups: ex.submit(process_review_group, group)

def process_review_group(group):
    for shop_id in group['shop_ids']:                 # 그룹 내부 순차
        get_review_by_shop(shop_id)
```

운영 워커 수는 BAEMIN 30, CPEATS 25, NAVER 4(브라우저 풀 사용량 제한). 첫 매장 인증 에러 시 **그룹 전체 즉시 차단**(`_deactivate_shops`) — 첫 매장 실패면 나머지 매장도 100% 실패 운명이라 봇 탐지 가속 회피를 위한 회로 차단(circuit breaker) 패턴.

**성과**
- 운영 처리량 — BAEMIN 13,127 → 8,690 필터링 → 13,699 task / 5,719 그룹을 2h cron 안에 완료.
- 동일 `platform_id` 동시 호출 **0건** (운영 로그 검증).
- NAVER 인증 에러 발생 그룹만 `is_active=4`, 다른 그룹 정상 진행 — 장애 격리 성공.
- 5,000+ 그룹 병렬 환경에서도 로그 인터리빙 문제를 `logBuffer` ordered flush 로 해결 — 운영자가 그룹별 처리 순서를 한 줄씩 추적.
- PR #233, #235, #413.

---

### 사례 7. 8색 Active-Active 무중단 배포 + NAVER 인증 에러 그룹 도미노 차단 ｜ 2026.02

**문제** — `cmong-scraper-js` 는 운영 트래픽 부담으로 무지개 8색(blue/green/yellow/purple/orange/cyan/white/black) Active-Active 배포로 확장. mqscript.sh 가 blue/green 만 처리하던 시기에는 나머지 6색이 관리 사각지대였고, 8개 컨테이너 동시 down/up 사이 traffic gap 동안 503 이 길게 발생했습니다. NAVER PR #494 로 보호조치·지역차단을 빠르게 throw 가능해진 뒤, mq 쪽도 이 신호를 받아 인증 에러 발생 그룹의 다른 매장도 동일 처리해야 도미노 효과(한 그룹 첫 매장 실패 → 봇 탐지 가속 → 같은 그룹 나머지 매장 7개도 같은 운명 → 단순 retry 는 21회 헛 호출)를 막을 수 있었습니다.

**해결** — **Traefik dynamic config 파일 단위 graceful drain** 의 5-step 파이프라인 + **platform 별 임계치 dict 기반 그룹 일괄 차단** 정책. NAVER 만 임계치 0(첫 인증 오류 = 영구 장애 가정)으로 두어 봇 탐지 가속을 최소화했습니다.

```bash
# Step 0: dynamic 디렉토리 정리 — Traefik이 폴더 안 모든 파일 로드하므로 .bak 잔여물 제거
find traefik/dynamic/ -type f ! -name "scraper.yml" -delete
# Step 1: Traefik에서 트래픽 차단 (컨테이너는 살아있음 → 503 명시)
echo "" > traefik/dynamic/scraper.yml && sleep 2
# Step 2-3: 8색 동시 down → ECR pull → 8색 순차 up
# Step 4: Health check (120 × 5s = 10min budget)
# Step 5: Traefik 라우팅 복원 + reload readiness 대기 (HTTP 200 polling, 최대 30s)

# NAVER 임계치 0 — 첫 인증 오류부터 그룹 전체 차단
PLATFORM_LOGIN_ERROR_COUNTS = {'NAVER': 0, 'BAEMIN': 3, 'YOGIYO': 2, 'CPEATS': 3}
```

**성과**
- 8색 컨테이너 동시 운영 환경에서 단일 `mqscript.sh` 로 안전 무중단 재시작 — 운영 서버 md5 일치 확인.
- NAVER 봇 탐지 회피 — 첫 매장 실패 시 그룹 전체 차단, 같은 계정 추가 요청 **0건**.
- CPEATS worker 증설 14 → 30 → 25 안정화.
- PR #412 (4a31cc0), PR #413 (00205a1).

---

### 사례 8. BIZ 대시보드 1,000매장 × 7일 — 2단계 쿼리 + DB-level pagination + SQL VIEW SSOT ｜ 2026.01

**문제** — 댓글몽 Biz 화면은 본사 1명이 산하 1,000매장을 한 화면에서 봅니다. 매장별 최근 7일 일별 주문, 매장별 광고 ROAS/클릭/전환, 매장별 일 매출 7일, 매장 크롤링 지연(stale) 표시, 브랜드 메타까지 한 응답에 담아야 합니다. 단순 JOIN 한 방으로 brand → ... → orders 까지 끌면 카디널리티 폭발(1,000 × 7 × 매장당 N) + 외부 광고/매출 IO 가 응답 경로에 끼면 응답 지연이 누적됩니다. Pony ORM 의 표현력으로는 4단 조인 + dynamic where + dynamic order by + dynamic LIMIT 조합의 가독성·일관성을 유지하기 어렵습니다.

**해결** — **「select shape 를 N+1 과 단일 거대 JOIN 사이의 sweet spot 인 2-스텝 batch select 로 옮긴다」** + **VIEW 를 정의 SSOT 로** + **외부 IO 는 응답 경로 밖으로**.

```sql
-- Step 1: shop 목록만 (LIMIT/OFFSET 적용, brand × brand_user × shop × brand_shop 4단 조인)
SELECT s.shop_id, ..., bs.created_at AS joined_at, bs.is_active, bs.deleted_at
FROM brands b
  INNER JOIN brand_users bu ON bu.brand_id = b.brand_id
  INNER JOIN shops s ON s.user_id = bu.user_id
  INNER JOIN brand_shops bs ON bs.shop_id = s.shop_id AND bs.brand_id = b.brand_id
WHERE b.is_active = 1 AND b.deleted_at IS NULL
  AND s.platform IN (...)
ORDER BY b.display_name, s.platform_shop_id
LIMIT %s+1 OFFSET %s;          -- has_more 판단용 +1 트릭

-- Step 2: Step 1에서 추린 shop_ids에 대해서만 group by
SELECT shop_id, sales_date, COUNT(order_id)
FROM orders
WHERE shop_id IN (...추린 20 shop_ids) AND sales_date BETWEEN ? AND ?
GROUP BY shop_id, sales_date;  -- 140행(20 × 7) 카디널리티 통제
```

매장은 **4상태**(`active` / `inactive` / `shop_deleted` / `brand_removed`)로 분류해 본사 운영자가 「주문 0인 이유」를 즉시 식별. stale 매장 판정은 `v_shop_crawling_status` SQL VIEW 로 두어 `cmong-be`·어드민 ad-hoc·BI 도구가 같은 정의를 공유(single source of truth). 외부 광고/매출은 별도 daily upsert + 4상태 머신(SUCCESS / PLATFORM_FAILED / SCRAPER_FAILED / FAILED)으로 적재하고 본사 화면은 적재된 테이블만 read.

**성과**
- 매장 1,000 × 7일 일별 주문 트렌드 페이지를 2단계 쿼리 + DB-level LIMIT/OFFSET 으로 카디널리티 통제 — 응답 경로 외부 IO **0건**.
- VIEW 기반 정의 공유로 stale 정책 변경 시 SQL 만 수정.
- 광고 15시간 컷 + 매출 idempotent re-fetch 로 외부 호출량 절감.
- 「대시보드만큼은 raw SQL 이 정답」 의 경계 설정을 운영 학습으로 명문화 — PR #20.

---

## 도메인 C. 외부 의존성 격리 · 봇 탐지 우회 (`cmong-scraper-js`)

### 사례 9. SessionLockRegistry — FIFO 큐 + lease TTL + cold-start guard 로 30+ worker 동시 로그인 race 직렬화 ｜ 2025.11 ~ 운영 중

**문제** — NestJS worker 30+ 개가 RabbitMQ consumer 로 분산 처리됩니다. 한 매장(`shop_id`)에 여러 API(`getReviews`, `addReply`, `getStores`, `keepAlive`)가 거의 동시에 진입하면 같은 Camoufox 세션을 여러 worker 가 동시에 잡으려 합니다. 같은 세션의 두 page 에서 동시 navigation 시 Playwright `execution context destroyed`, 같은 매장 동시 로그인 두 번은 외부 플랫폼 IP 평판 영구 차단(1~24시간 그 매장 작업 전체 실패). 도메인 특수성이 단순 mutex 로는 부족하게 만듭니다 — Camoufox 1 인스턴스 ≈ 1GB+, launch 5~10초 → race 시 N배 메모리·런타임 폭증. 인스턴스 다중화로 in-process Map 만으론 부족하고, Redis Cluster(ElastiCache Serverless)는 같은 트랜잭션 여러 키 사용 시 CROSSSLOT 에러를 던집니다. 가장 까다로운 hazard 는 **cold-start deadlock** — ECS task 가 죽었다 살아나면 in-memory Map 은 비어있는데 Redis 큐의 head 는 옛 인스턴스의 requestId 라, 살아난 worker 가 그 head 차례를 기다리지만 옛 worker 는 죽어서 영원히 release 안 됩니다.

**해결** — **4 layer 직렬화**: ① FIFO 큐(Redis LIST `LPUSH/LREM/LINDEX`) ② per-request lease(`PSETEX` 90s TTL, 5s 갱신) ③ **instance-aware lease value** `{instanceId}:{Date.now()}` (Martin Kleppmann 의 fencing token 패턴을 단순화 — 인스턴스 식별자를 lease value 에 박아 cross-instance ownership 을 lease-level 에서 검증) ④ handoff pattern (release 시 다음 큐 entry 가 같은 세션 재사용). Redis Cluster CROSSSLOT 은 **모듈별 의도된 정책 분기** 로 해결 — queue 는 단일 키 명령으로 분리, reputation(사례 10)은 hash tag `{pool}` 로 슬롯 강제 배정. 같은 시스템 안에 두 전략을 의도적으로 다르게 두는 이유는 queue 는 부하 분산 우선, reputation 은 트랜잭션 묶음 우선.

```ts
// Cold-Start Guard — instance-aware lease value
const isCurrentInstance = leaseValue?.startsWith(`${this.instanceId}:`);
if (!isCurrentInstance) {                              // 옛 인스턴스 잔재
  const staleLength = await this.redis.llen(queueKey);
  await this.redis.del(queueKey);
  this.logger.warn(`[BrowserQueue] cold start: cleared ${staleLength} stale entries`);
}

// Force Termination — activeCount 강제 리셋 (락 누수 차단)
async forceTerminate(sessionId, requestId, reason) {
  await this.broadcastAbort(sessionId, reason);
  const state = this.locks.get(sessionId);
  if (!state) return;
  state.activeCount = 0;                               // 다른 핸들 release 실패해도 락 삭제 보장
  this.markImmediateClose(state);
  await this.executeClose(state);
}
```

`attach`/`release` Handle 패턴(RAII)으로 `activeCount` invariant 를 유지하고, `pendingClose` 5종 정책(immediate / defer / idle-timer / hasWaitingRequests handoff / release)으로 다른 worker 의 핸들이 활성일 때 close 를 보류, 모든 release 후에만 closeSession. 안전망으로 `forceRelease`(운영 kill switch), `forceTerminate`(activeCount 강제 0), `evictStaleHead`(2초 주기 head 의 lease 키 EXISTS=0 체크 후 LREM).

**성과**
- **세션 유지율 99.2%** (최근 6개월 운영 지표).
- **댓글 등록 중복 0건 / 6개월** — SessionLockRegistry + Idempotency-Key 조합.
- `getReviews` race 로 인한 `execution context destroyed` 사고 **0건** (PR #428 이후).
- 인스턴스 재시작 후 dead-letter 큐 누수 **0건** (cold-start guard 도입 후).
- CROSSSLOT 에러 **0건** (PR #566 hash tag/단일 키 분리 정책 일관 적용).
- 동일 매장 동시 로그인 **0건**.

> **[아키텍처 이미지 — C1] SessionLockRegistry FIFO + handoff**
> Excalidraw 추천: Worker 1~30+ → acquire(shop_A) → FIFO 큐 + lease TTL + watchdog → granted/queued → handoff 시 세션 재사용. Cold-start guard 분기 표기. 4 layer (FIFO/lease/instance-aware/handoff)를 색상 구분.

---

### 사례 10. PAMS — 자체 IP 평판 시스템으로 프록시 비용 월 800만 → 90만 (88.75% 절감) ｜ 2025.07 ~ 운영 중

**문제** — 외부 Decodo Residential Proxy 의존도가 높아 비용이 매월 **800만 원**, Decodo 측 장애가 그대로 서비스 중단으로 이어지는 **SPOF** 구조였습니다. Decodo Datacenter(월 90만)로 전환하면 비용은 절감되지만 datacenter IP 는 시간에 따라 port 별로 IP 가 바뀌어(Identifier 가 IP 에서 port 로 전환됨) **평판 측정은 IP 기준이어야 의미 있는데 IP 는 stable 하지 않은** 본질적 불일치가 발생합니다. 추가로 Redis Cluster CROSSSLOT, pool exhausted 시 legacy fallback 의 함정(차단된 IP 재할당), 가장 미묘한 hazard 인 **port rotation 회피**(차단된 IP 가 다음에 다른 port 에 mapping 되면 그 port 가 영구 blocklist 를 회피)까지 6개월에 걸쳐 풀어야 했습니다.

**해결** — **14 phase phased rollout** (Phase 0 ~ G + Issue #579 PR-1~4 + #591 P2 + #623). 한 번의 큰 배포가 아니라 각 phase 머지 → 측정 → 안전 확인 → 다음 phase 의 점진적 cutover. 핵심 결정 4가지: ① **port↔IP 매핑 3중 저장**(In-memory Map + Redis HASH + MySQL `naver_proxy_port_ip_map` + S3 부트스트랩 manifest) — 클러스터 cold start 시 외부 의존 없이 복구 ② **이중 blocklist** — `port_set`(평판 나쁜 port 영구 차단) + `ip_set`(평판 나쁜 IP 영구 차단), allocator 가 port 선정 후 PortIpResolver 로 IP lookup → `ip_set` hit 시 그 port 도 자동 `port_set` 에 SADD 후 skip → **port rotation 회피 hazard 차단** ③ **Adaptive Cooldown** — 5종 outcome(success/block/timeout/networkError/authError/siteChange/unknownError) × consecutiveFailures × latency 가중치로 health 점수 → ranked 정렬 → 최고점 반환, Shadow mode 로 실 운영 영향 없이 결정 측정 ④ **Pool exhausted → legacy fallback** — `NaverIspPoolExhaustedError` throw → `return undefined` → caller 가 legacy path, legacy 도 `selectPortRespectingBlocklist` 로 `BLOCKLIST_KEYS.PORT_SET` SISMEMBER 확인하고 skip(최대 10회).

```ts
// Redis Cluster hash tag — record* 메서드가 HASH+STREAM+SET+HASH를 한 MULTI/EXEC에 묶음
// {pool}을 hash tag로 박아 같은 슬롯 강제 배정
export const REPUTATION_KEYS = {
  HASH:           (port) => `proxy:naver:{pool}:port_reputation:${port}`,
  EVENTS:         (port) => `proxy:naver:{pool}:port_reputation:${port}:events`,  // STREAM MAXLEN ~50
  BLOCKLIST_SET:                BLOCKLIST_KEYS.PORT_SET,         // 영구 차단 port
  BLOCKLIST_HASH: (port) => `proxy:naver:{pool}:blocklist:${port}`,
  BLOCKLIST_IP_SET:             BLOCKLIST_KEYS.IP_SET,           // 영구 차단 IP
};
```

운영 절차도 AGENTS.md 에 명문화 — env value 빈 값 / 미설정 / deprecated alias(`NAVER_ISP_POOL_ALLOCATOR`) 까지 모든 경로 명시, default ON 정책 일관. `selectPortRespectingBlocklist` 는 **Codex AI 코드 리뷰 3회 follow-up** 으로 정밀화한 흔적이 PR #625 본문에 남아있습니다 — 1차 머지 후 codex: "selectPortRespectingBlocklist 호출 안 됨", 2차: "lastAttemptedPort fallback 에서 blocked port 그대로 반환", 3차 수정. AI 코드 리뷰까지 코드 변경의 한 단계로 받아들이는 워크플로.

**성과**
- **월 비용 800만 → 90만 원 (88.75% 절감)** — 운영 청구서 기준.
- **요청 성공률 70% → 98%** — 프록시 전환 후 운영 대시보드.
- Decodo SPOF 제거(HA 보조 풀로 잔존), Prometheus + Grafana Health 대시보드 구축.
- 차단 IP 가 legacy 경로로 재할당되는 사고 **0건** (PR #625 codex 리뷰 3회 follow-up 후).
- CROSSSLOT 에러 **0건** (Phase G hash tag 도입 후).
- ASN 자동 분류(4766=KT/isp, 40676=Psychz/dc) + KR 가드(non-KR 응답 거부) + 부분 실패 격리(failed outcome 분류).

> **[아키텍처 이미지 — C2] PAMS Before/After 비용·성공률 비교**
> Excalidraw 추천: Before(Worker → Decodo Residential SPOF) vs After(Worker → Platform Resolver → NAVER IP Reputation sticky pool / Datacenter Proxy Pool + Cooldown → Health Monitor → Auto Cooldown → 외부 플랫폼). 우측에 「월 800만→90만, 70%→98%」 박스 강조.

---

### 사례 11. Akamai Bot Manager 우회 — `_abck` 4-state 머신 + referrer warming + bm_sv polling (77.8% → 100%) ｜ 2026.02

**문제** — CPEATS(쿠팡이츠 사장님 사이트)는 Akamai Bot Manager(`AkamaiGHost`)가 깔려있어 평범한 Playwright/Chromium 은 99% 차단됩니다. Camoufox(Firefox stealth fork)로 fingerprint 를 우회해도 sensor 가 채 준비되기 전 로그인 제출하면 `_abck` cookie 가 `~-1~`(pending) 상태로 sensor 검증 실패 → 403. 옛 구현의 4가지 silent 결함: ① `_abck=~0~,~-1~,~timestamp~`(verified + challenged 혼재) 시 `~0~` 첫 등장 즉시 break 하여 race window 안 추가된 `~-1~` 을 놓침 ② `~0~,~1~` 혼재를 VERIFIED_ONLY 로 오분류(`~1~` 은 BLOCKED 시그널) ③ `AkamaiGHost` 응답을 PASSWORD_ERROR 로 오분류해 Full Retry 못 함 ④ sensor 제출 후 즉시 break 하여 sensor 의 다음 1~2초 추가 검증 못 받음.

**해결** — Akamai 우회는 단일 트릭으로 안 되므로 4가지를 합성: (a) **`_abck` 상태 머신 명문화** + (b) 정책 분기를 **service 와 spec 의 SSOT 순수 함수** 로 추출 + (c) **referrer warming** 으로 human-like telemetry 누적 + (d) 분류 helper 의 3-경로 일관 호출 강제.

```ts
// _abck 4-state classifier — abck-state-classifier.util.ts
// AbckState = 'INITIAL' | 'VERIFIED_ONLY' | 'CHALLENGED' | 'BLOCKED'
// 우선순위: BLOCKED > CHALLENGED > VERIFIED_ONLY > INITIAL
export function classifyAbckState(value: string | undefined): AbckState {
  if (!value) return 'INITIAL';
  const has0 = /~0~/.test(value);
  const hasNeg1 = /~-1~/.test(value);
  // ~1~ 는 ~-1~ 안에 매치되지 않음 (`-`가 사이에 있음)
  const has1 = /~1~/.test(value);
  if (has1) return 'BLOCKED';            // ~0~,~1~ 혼재도 BLOCKED — 이전 VERIFIED 오분류 수정
  if (hasNeg1) return 'CHALLENGED';
  if (has0) return 'VERIFIED_ONLY';
  return 'INITIAL';
}

// 정책 분기 — service와 spec의 SSOT
export function decideBmSvPollingAction(p): BmSvPollingAction {
  if (p.hasBmSv) return { type: 'BREAK_BM_SV' };
  if (p.currentAbckState === 'CHALLENGED') return { type: 'OBSERVE_CHALLENGED' };
  if (p.currentAbckState === 'BLOCKED') return { type: 'OBSERVE_BLOCKED' };
  if (p.currentAbckState === 'VERIFIED_ONLY'
      && p.prevAbckState !== 'VERIFIED_ONLY') return { type: 'ENTER_RACE_WINDOW' };
  return { type: 'CONTINUE' };
}
```

Referrer Warming(PR #644) — mainUrl 거쳐 referrer chain 만들고 15초 동안 mouse jitter(200–600px × 100–400px × steps 3–5 × 800–1,200ms 대기) 유지 → Akamai sensor 가 human-like telemetry 누적 → `_abck` verified. Click Loop(PR #655) — submit Enter 1회 → `page.click` 25번(1~2초 jitter) 반복으로 사람 행동(제출 안 됐다 다시 누름) 시뮬레이션. `isAkamaiBlockDetected()` helper 는 cpeats.service.ts 의 메인 loginResult 분기 + Quick Retry 분기 + Prewarm Swap 분기 **세 경로에서 일관되게 호출** — 한 곳만 보강하면 `page.on("response")` 인터셉터 비동기 set 시점에 따라 silent 회귀 가능(PR #618 review feedback)을 코드 주석에 명문화.

**성과**
- **로그인 성공률 77.8% → 100%** (PR #644 측정, 18/18 iter, 6 iter × 3 worker, default ON 채택).
- `AkamaiGHost → PASSWORD_ERROR` 오분류 사고 **0건** (PR #618 이후).
- `_abck=~0~,~1~` 혼재 silent VERIFIED 오분류 사고 **0건** (PR #631 codex 리뷰 수정 이후).
- **「PR 본문에 iter × worker 측정 박는」 운영 문화 정착** — 7/9 → 18/18 형식의 정량 검증.

> **[아키텍처 이미지 — C3] Akamai 우회 시퀀스 + `_abck` 상태머신**
> Excalidraw 추천: 좌측에 시퀀스(CPEATS 진입 → Referrer Warming 15s jitter → Login Submit → `_abck` 변화 추적 → `decideBmSvPollingAction` → Click Loop 25회 → 성공/`AkamaiBlockDetector`). 우측에 `_abck` 4-state(INITIAL/VERIFIED_ONLY/CHALLENGED/BLOCKED) 우선순위 머신.

---

### 사례 12. Single-Flight Coordinator 포트화 — Hexagonal + Decorator 5종 합성, 7가지 행동 계약 spec 명문화 ｜ 2026.01

**문제** — NAVER `ensureSession()` 은 한 사용자(`platformId`)에 대한 동시 요청 N개를 받으면 첫 번째만 실제 로그인하고 나머지는 결과 공유해야 합니다(single-flight, coalescing). Issue #531 의 첫 구현은 NaverService 안에 인-메모리 Map 80+ 줄 인라인이었고, baemin/cpeats/yogiyo 도 같은 패턴이 필요한데 재사용되지 않았으며, Redis 어댑터 추가 시 NaverService 를 또 손대야 했습니다. 더 본질적인 문제는 **single-flight 가 외부에 약속하는 행동 계약 자체가 명문화되어 있지 않아 회귀를 잡을 수 없다는 점** — ① 결과 일관성(같은 cause 인스턴스 공유, 스택 트레이스 보존) ② 세대 가드(forceRelease 후 새 record 를 옛 record 의 늦은 finally cleanup 이 지우면 안 됨) ③ 동기 throw 정규화(operation 이 sync throw 해도 Map record 박힌 뒤 throw) 같은 미묘한 invariant 들.

**해결** — **Port-Adapter (Hexagonal Architecture, Alistair Cockburn) + Decorator + Strategy 합성** 으로 OCP 보존 + **계약 문서로서의 spec** 으로 7가지 행동 속성을 spec 헤더에 명문화하고 describe 1:1 매핑.

```ts
// Port 추출
export interface SingleFlightCoordinator {
  execute<T>(key: string, op: () => Promise<T>, opt?: Options): Promise<T>;
  getInflightState(): readonly InflightEntry[];
  forceRelease(key: string, reason: string): Promise<void>;
}

// 4 데코레이터 합성
// InProcessSingleFlightCoordinator (Map + forceRelease gate)
// + DeadlineSingleFlightDecorator   (Promise.race wall-clock timeout)
// + CapacitySingleFlightDecorator   (waiter cap load-shedding)
// + HeartbeatSingleFlightDecorator  (15s scan → long_running warn + gauge)
// + TelemetrySingleFlightDecorator  (owner_started/finished/failed/coalesced)

// 세대 가드 + Sync throw 정규화 (한 줄로 두 hazard 동시 처리)
const opPromise = Promise.resolve().then(() => operation());
record.promise = Promise.race([opPromise, releaseGate]).finally(() => {
  if (this.inflight.get(key) === record) this.inflight.delete(key);  // 세대 가드
});
```

**행동 계약 7가지를 spec 헤더에 명문화** (`__tests__/in-process.coordinator.spec.ts`) — 빨간색이 뜨면 어느 계약이 깨졌는지 그룹명에 즉시 보이도록 설계:

```
[1] 코알레싱      — 같은 키 동시 호출은 작업을 1번만 실행
[2] 결과 일관성   — 같은 cause 인스턴스 공유 (스택 트레이스 보존)
[3] 자원 정리     — 모든 settle 경로에서 record 즉시 제거
[4] kill switch   — forceRelease 직후 후속 호출이 새 owner, 세대 가드
[5] 호출자 격리   — 서로 다른 키는 영향 없음
[6] 입력 계약     — 동기 throw도 promise rejection으로 정규화
[7] 관측성        — getInflightState가 InflightEntry 계약 노출
```

안전망 default — deadline 180,000ms(2FA 120s + waitForReplacement), maxWaiters 30(UI-spam load-shedding), long_running warn at 60s(stuck-owner early signal), `forceRelease` ops kill-switch(rejects waiters + removes entry). NestJS DI Factory 가 `SINGLE_FLIGHT_BACKEND` env 로 backend 선택.

**성과**
- NaverService **80+ 줄 제거** — coordination + telemetry 가 thin call `coordinator.execute(id, op, { telemetryTag })` 로 축약.
- **22 new unit specs** — adapter/decorator 별 격리 검증, 기존 575 NAVER 테스트 통과.
- Issue #533(Redis backend) 추가 시 NaverService 안 건드리고 DI factory 만 swap.
- **사내 AGENTS.md 의 모범 사례로 박힘** — 「계약 문서로서의 spec 헤더 명문화」 스타일이 회사 표준이 됨.
- PR #569 (8f77220).

---

## 도메인 D. AI 파이프라인 · 운영 자동화

### 사례 13. 부정 리뷰 탐지 — 6신호 노이즈 필터 + 길이 가중치 + 별점·스코어 OR 분류 ｜ 2026.01 ~ 운영 중

**문제** — 자동 답글이 위험한 가장 큰 케이스 둘. ① 별점은 5점인데 본문은 컴플레인(sentiment 불일치 — 사장님 보복 두려움이나 라이더 평가용으로 약 30%가 5점 + 부정 내용) ② "ㅋㅋㅋㅋㅋㅋㅋㅋㅋㅋ" 같은 노이즈 리뷰에 진지한 답글. AI 호출은 비싸고 느려서 모든 리뷰를 ML 에 보내면 비용·지연 손해, AI 모델이 "문맥 파악 불가"로 0점 반환하는 케이스도 노이즈 분류 필요. 같은 텍스트라도 길이에 따라 신뢰도가 달라야 합니다 — 100자 "조금 짰어요" 는 신뢰도 높음, 5자 "별로" 는 노이즈에 가까움.

**해결** — **신호 처리 + 정보 이론 관점의 가중 합산** 으로 단일 임계 if-else 룰이 아닌 **6신호 가중치 합산** 노이즈 필터를 사전 컷으로 두어 비싼 ML 호출을 절감. 사후 가중은 **「신뢰도 shrink(Bell)」 와 「극성 증폭(Polarity Amplification)」 의 두 축을 분리** + **tanh ±35 sigmoidal squashing** 으로 운영 튜닝 노브를 독립 조정 가능하게 했습니다.

**노이즈 필터 6신호** (`ScoreProcessor._noise_filter`)

| 신호 | 계산 |
|---|---|
| 토큰 반복도(top word share) | `top_word_count / total_tokens` |
| Bigram / Trigram 반복도 | `most_common_ngram / total_ngrams` |
| **샤논 엔트로피** | `-Σ p log2 p` (문자 단위) |
| 문자 다양성 | `unique_chars / length` (40자 이상에서만) |
| **zlib 압축률** | `len(zlib.compress(text)) / len(text)` |
| 같은 문자 / 이모지 4회+ 연속 | regex `(.)\1{4,}`, `(emoji)\1{4,}` |

각 신호 가중치 곱한 합이 `NOISE_WEIGHTED_THRESHOLD=2.0` 넘으면 noise.

**길이 가중치 (Bell + Polarity Amplification + tanh box)**

```python
def _apply_length_weight(base_score, n):
    w_conf = _length_weight_bell(n)        # sweet spot 60~600, 짧으면 0.7+(n/60)^1.5
    w_pol = _polarity_amplify_weight(n)    # sweet spot 1.2x 증폭
    deviation = base_score - 50.0
    raw_push = deviation * w_conf * w_pol
    final_score = 50.0 + math.tanh(raw_push / 35.0) * 35.0        # 50±35 box
    bonus = _positive_length_bonus(base_score, n)                  # >=75 & 40~250자 → +5
    return max(0.0, min(100.0, final_score + bonus))
```

분류 정책 — `rating ≤ critical_rating` 일반 부정 OR `5점 + score in (min~max) + len ≥ 10` scoring-based 부정. 알람은 **BIZ(브랜드 `send_negative_alarms` + `critical_review_rating` 검증)**와 **User(`NegativeReviewAlarm.is_active`)**의 책임을 분리, 파트너 템플릿 오버라이드(`partnerTemplateOverrides: Record<orgId, Record<TemplateCode, TemplateCode | null>>`)는 계약 해지 시 매핑 한 줄 제거 = 자동 기본 복원으로 운영자 관여 최소화. 알고리즘 버전은 `SCORE_VERSION = "v1"` 컬럼을 PK 일부처럼 다뤄 같은 review_id 에 여러 버전 공존 → v2 백필 시 v1 의존 다운스트림 안 깨짐.

**성과**
- AI 비용 절감 — `existing_scores_map` pre-fetch 로 같은 SCORE_VERSION 중복 호출 차단 + 노이즈 사전 컷으로 짧은 리뷰 ML 호출 skip.
- **5점 부정 리뷰 캐치율 향상** — 평점 + 스코어링 OR 결합으로 약 30%의 "별점 ≠ 감정" 케이스 포착.
- 한 부정 리뷰에 최대 BIZ 3개 + User 3개 = 6개 알림톡 동시 발송.
- 임계치 운영자 직접 조정 가능 — `ReviewScoreThreshold` 테이블(레이블·구간) + `ScoreTuning` Enum(알고리즘 튜닝 노브) 이중 노브.
- PR #300, #331, #335, #337, #341 (cmong-mq), PR #1474, #1480, #1498 (cmong-be).

---

### 사례 14. SafeCron — 멀티 인스턴스 cron 중복 실행 차단 데코레이터 (14곳 적용) ｜ 2025.09 ~ 운영 중

**문제** — ECS 다중 Task 환경에서 NestJS 의 `@Cron` 은 **모든 인스턴스에서 동시 실행**. 일일 결제 정합성 점검이 N개 인스턴스에서 N번 → Portone API rate-limit 초과, 일일 알림톡 cron N번 → 사용자가 같은 알림톡 N개, Notifly 사용자 동기화 batch N번 → 외부 SaaS rate-limit + 비용. 모든 cron 마다 락 처리 코드를 직접 작성하면 보일러플레이트가 폭증하고, 락 해제 누락 시 인스턴스 죽으면 락이 영구 잔존해 cron 이 영영 안 돌게 됩니다.

**해결** — **TypeScript Decorator + NestJS DI 우회(`setModuleRef`)** 의 시니어 트릭으로 한 줄 데코레이터로 분산 락 + Slack 표준화 + 환경변수 토글을 자동화. 데코레이터는 클래스 정의 시점에 실행되어 인스턴스가 없으므로, main.ts 에서 `setModuleRef(app.get(ModuleRef))` 로 전역 참조를 저장한 뒤 데코레이터 안에서 `getRedisService()` 로 lazy 조회합니다. 락 TTL 자동 해제로 OOM/SIGKILL 시에도 다음 cron 정상 실행.

```ts
export function SafeCron(cron: string, options: CronOptions = {},
                         opts: AdditionalOptions = {
                           lockTTL: 10_000, slackAlert: true,
                           slackWebhookUrl: URL.SLACK_BILLING_BOARD,
                         }): MethodDecorator {
  if (!isCronEnabled()) return (t, k, d) => d;       // CRON_ENABLED=false → noop
  return applyDecorators(
    WithLock({ ...opts, name: options.name }),       // setNX + Slack + finally del
    Cron(cron, { ...options, name: options.name }),  // @nestjs/schedule
  );
}
// WithLock 내부 — setNX(lockKey, 'running', ttlSeconds)
//   - 락 획득 시: Slack start → originalMethod → Slack complete(${duration}ms) → finally del
//   - 락 실패 시: "already running" 로그 후 return
//   - 예외 시: Slack error + stack trace block → throw
```

표준화된 Slack 메시지 형식 — `start` / `complete (${executionTime}ms)` / `error - ${message} + 스택 trace block`. `slackAlert: false` 로 시끄러운 cron 알림 끄기, `slackWebhookUrl` 로 cron 별 다른 채널 라우팅. `CRON_ENABLED` 환경변수가 `false`/`0`/`disabled`/`off`/`no` 중 하나면 데코레이터 자체 noop → `@Cron` 등록조차 안 됨 → QA 안전.

**성과**
- `@SafeCron` 사용처 **14곳**(subscriptions, alarmtalk, notifly, auth-magic-link, mixpanel, log-cleanup 등).
- 평균 5~10라인 보일러플레이트 절약 → 약 **100라인 절감** + cron 별 형식 통일로 운영 가시성 확보.
- 환경변수 한 번 토글로 전 cron 비활성화 — QA에서 롯데 cron 안전 비활성화 (PR #1467, #1466).
- 시니어 데코레이터 패턴 — DI 우회(`setModuleRef`), Lock acquire/release/TTL, Slack 표준화, 환경변수 토글을 한 데코레이터에 통합.

---

### 사례 15. 자동 답글 종단 파이프라인 — 수집 → AI → 4단 TOCTOU 게이트 → API Key/JWT 이중 인증 게시 ｜ 2026.03

**문제** — 댓글몽 메인 가치 제안 「사장님이 안 달아도 AI 가 자동 답글」 의 위험 4가지. ① 잘못 달면 매장 평판 직격(별점 1점에 "맛있게 드셔서 감사" 자동 답글 = 사고) ② 같은 리뷰에 두 번 게시 ③ 매장별 홍보문구 합성(쿠폰 받으세요)을 AI 답글 위/아래에 어디? ④ 별점 컷오프(매장마다 "5점만" / "4점 이상만" 정책 다름). 추가로 Pony `@db_session` 안에서 60초 타임아웃 가능한 BE API 호출 시 커넥션 풀이 빠르게 고갈됩니다.

**해결** — **트랜잭션 경계 분리** + **API Key → JWT 이중 인증 fallback** + **TOCTOU 4단 게이트** 의 3중 안전망. payload 수집은 짧은 `@db_session`, 합성은 staticmethod, 게시는 async 의 3단 분리로 외부 호출 시간이 길어져도 DB 커넥션 점유 안 됨 (Java/Spring `@Transactional` 분리 패턴과 본질 동일).

```python
# 4단 TOCTOU 게이트 — populate_task.py:1099
@db_session
def _collect_auto_reply_payload(self, review_id, shop_context):
    review = Review.get(review_id=review_id)
    if review.is_replied: return None                                  # ① 게시 플래그
    if Reply.select(lambda r: r.review.review_id == review_id).count() > 0:
        return None                                                     # ② 기존 replies 카운트
    if not self._is_within_ai_reply_period(review.created_at, ...):
        return None                                                     # ③ AI 답글 기간 컷오프
    if not review.reply2_id: return None                                # ④ reply2 content
    ai_reply = AiReply.get(ai_reply_id=review.reply2_id)
    if not ai_reply or not ai_reply.content: return None
    return AutoReplyPayload(ai_reply_content=ai_reply.content, ...)

# 합성 — pure staticmethod, 테스트 6 케이스 검증
@staticmethod
def _assemble_reply_comment(p: AutoReplyPayload) -> str:
    comment = p.ai_reply_content
    if p.custom_reply_text:
        comment = (comment + "\n" + p.custom_reply_text) if p.custom_reply_position == "bottom" \
                  else (p.custom_reply_text + "\n" + comment)
    return comment.replace("(매장명)", p.shop_name).replace("(닉네임)", p.reviewer)
```

BE API 이중 인증 — API Key 우선 시도 → 401/403 응답 시 JWT 로그인(`be_auth_email`/`be_auth_password`)으로 폴백, 키 회전·만료 시에도 잡 안 죽음. 후처리 실행 순서 고정 — 리뷰 스코어링 → 알림톡 → 자동 답글(가장 마지막, 불만족 리뷰는 사장님이 먼저 인지하고 직접 대응할 시간 확보).

**Layered Idempotency 책임 분담**
- flow-be 측: 게시 전 4단 게이트로 같은 잡 안 두 번 호출 차단(잡 자체 결함 방어)
- cmong-be 측: `is_auto_reply=True` 플래그 받아 외부 플랫폼 게시 단계 멱등성 보장(같은 review_id 두 번 reply 안 됨)
- **flow-be 는 BE 를 신뢰, BE 는 플랫폼 응답으로 자기 멱등 보장** — "어디서 책임이 깨지면 어디서 알 수 있는가" 경계 명확화

**성과**
- 어드민 한 번 트리거로 **수집 → AI 생성 → 게시 종단 자동화**.
- 게시 직전 4단 가드로 **중복/오답글 위험 차단**, 합성 로직 staticmethod 분리로 6가지 케이스 단위 테스트 잠금.
- API Key → JWT fallback 으로 키 회전 시에도 잡 안 죽음.
- AI 생성 실패(`num_failed_ai_requests`) vs 실제 게시 성공(`num_total_auto_replies`) metrics 분리 — 운영자가 「AI 자체 실패」 vs 「게시 실패」 즉시 식별.
- PR #39 (b03352b).

---

## JVM 재설계 프로젝트 — Node.js 운영 자산을 Kotlin/Spring 으로 재현 + ADR 화

5년 동안 Node.js 로 운영하며 부딪힌 **분산 락 · 결제 멱등성 · 트랜잭션 분리 · 외부 의존성 격리** 문제를 Java/Kotlin/Spring 환경에서 동일한 시나리오로 다시 풀어보고, 결정 과정을 ADR 로 남기는 프로젝트입니다. 현재까지 **ADR 49건, 실험 47건, 기술 블로그 17편** 누적.

### Node 추상 패턴 ↔ Kotlin/Spring 자산화 매트릭스

| Node.js 자산 | Kotlin/Spring 자산화 |
|---|---|
| Redis SET NX + LUA 분산 락 | Redisson watchdog + Pub/Sub 4종 비교 |
| Idempotency Key + 상태머신 + Redis 캐싱 + reconciliation | ADR-006 결제 멱등성 4단계 + EXP-09b 9 시나리오 |
| SessionLockRegistry FIFO + lease TTL | Coroutines + supervisorScope + Single-Flight 5 invariants |
| Custom Error Strategy 5종 + 9종 카테고리 | Resilience4j 5종 + 9종 에러 분류기 |
| Camoufox PID Registry (OOM 회피) | JVM Heap/GC 튜닝 G1GC Region + Humongous |
| RabbitMQ classic queue (운영 5가지 한계 측정) | Kafka 마이그레이션 + Outbox Relay |

### 세 저장소

- **`commerce-comment-platform-be`** (Java / Spring Boot / JPA) — 결제 멱등성 4단계 재현, **분산 락 4종 비교(비관락 · 낙관락 · GET_LOCK · Redisson)**, MySQL InnoDB RR vs ANSI RR 의 차이 재현, 트랜잭션 분리 패턴 9 시나리오 매트릭스, No-offset Pagination.
- **`commerce-batch-orchestrator`** (Spring Batch + Kafka) — RabbitMQ 를 1주간 운영해 5가지 한계(replay 비용, prefetch HoL, x-overflow, publisher confirm 실패, DLQ 운영 비용)를 측정하고 Kafka 전환을 정당화하는 ADR 작성. Outbox Relay 의 polling vs CDC 지연 비교, Spring Batch Reader 4종 매트릭스.
- **`commerce-external-gateway-kt`** (Kotlin / Coroutines / Resilience4j) — 운영 자산을 Kotlin 으로 재설계. **Single-Flight 패턴의 다섯 불변식**(promise sharing, sync throw normalization, force release, deadline, capacity), 9종 에러 카테고리 분류기, Resilience4j 5 모듈(CircuitBreaker, Retry, Bulkhead, RateLimiter, TimeLimiter) 적용.

---

## 경력 — 아이브릭스(I-BRICKS) ｜ 백엔드 개발자 ｜ 2021.05 ~ 2024.11

한국어 자연어 처리 전문 기업에서 검색·추천 시스템, 데이터 파이프라인, 챗봇 개발을 담당했습니다.

- **한국 금융연수원 강의 검색·추천** — Elasticsearch + Logstash 기반 RDB → ES 파이프라인 구축, 사용자별 시청 시간·카테고리 선호도 가중치 부여로 검색·추천 경로를 한 인덱스에서 일관 처리.
- **EBS 학습 시스템 데이터 파이프라인** — 일일 **수천만 건** 로깅을 Kafka + Apache Nifi + Elasticsearch 클러스터로 처리. **쿼리 응답 시간 50% 단축**, 데이터 처리량 2배 증가에도 안정 동작.
- **대법원 챗봇 도우미** — React/Redux/SCSS 기반 사용자 UI, KWCAG 2.1 웹 접근성 준수.

---

## 부록 — 본문에서 다루지 않은 운영 사례

여기서는 본문 5단 구조로 다루지 않은 사례를 카테고리별로 한 줄씩 정리합니다.

**결제·트랜잭션**
- 결제 9 시나리오 매트릭스 — 최초/정기/실패·재시도/취소(전체·부분)/예약(RESERVE)/결제수단 변경/요금제 변경(즉시·예약)/프로모션 → 정상 업그레이드.
- 마케팅 댓글 예약 비동기 실행 — Aurora 기반 예약 큐 + `SELECT FOR UPDATE` 분산 처리 + Redis Pub/Sub 상태 추적 + 지수 백오프 멱등 재시도로 **TPS 100 → 1,000+, 처리 지연 5분 → 10초 미만, 예약 실패율 1% 이하** 유지.

**큐·메시징·재시도**
- RabbitMQ DLX 없이 application-level retry — `setTimeout + republishMessage` 로 hot loop 회피, 30s/5m/30m 단계별 backoff. Phase 2 에서 DLX 정통 패턴 마이그레이션 예정 명시.
- 멀티 워커 IntegrityError-aware upsert + Lock-timeout 지수 백오프 — Duplicate 은 break, Lock timeout 은 1s/2s/3s 점진 backoff, `BrandShops` 는 raw SQL `ON DUPLICATE KEY UPDATE` 전환 (PR #414).

**외부 의존성·회로 차단**
- Hyphen 외부 API quarantine — DB-backed state machine(OK / QUARANTINED) + 12h probe 자동 복구 + DB↔외부 매장 mismatch 감지(`STORE_MISMATCH_HYPHEN_MORE / DB_MORE / BOTH`).
- 외부 스크래퍼 에러 분류 + 매장 자동 비활성화 — `PlatformAuthError`(즉시 비활성 카운트++) / `ScraperAPIError`(scraper_code/message 보존) 2계층, `ShopDeactivationCount` 3회 누적 자동 비활성 + 성공 시 카운트 리셋 자가 치유.
- 8가지 로그인 분기 일원화 — NAVER 18종 + CPEATS 11종+ 도메인 예외 계층을 `BasePlatformException` → 플랫폼별 도메인 → classifier helper 의 3 layer 로. instanceof + name + code 3단 분류로 직렬화 경계 흡수.
- Idempotent Reply Pipeline — Lease + Completion Cache 분리 + 4종 ErrorClassifier(BLOCKED_SUSPECTED / TRANSIENT / PERMANENT / SYSTEM) + ACK/NACK 매트릭스 명문화. 기본값 PERMANENT(unknown 에러 무한 retry 방지).
- Adaptive Traffic Controller + Launch Budget — Lua Token Bucket + Circuit Breaker(SOFT_OPEN / HALF_OPEN) + jittered watchdog 으로 Thundering Herd 방지.

**자원 격리·메모리**
- Camoufox Heavy 브라우저 풀 — Launch Semaphore + Prewarm Pool + Quarantine + 5-phase Zombie Cleanup + Jittered Watchdog 5층 자원 격리. 40 concurrent 에서 **97.2% 성공률** (PR #48a6167).
- OOM 방지 chunk 처리 (PR #1436) — 일일 구글시트 cron 의 `find` 메모리 폭증을 CHUNK_SIZE=2000 while 루프 + lookup map 1회 캐싱으로 차단.
- 메모리 스파이크 평탄화 (flow-be PR #27/#28) — 톱니파 메모리를 30개 배치 + Semaphore 30 + 단일 db_session + 명시적 `gc.collect()` + 3슬롯 고정 자료구조로 계단형 평탄화. `_get_memory_mb()` 로깅으로 `gc.collect()` 명시 호출을 정당화.

**스케줄러·운영**
- 운영 잡 오케스트레이션 (flow-be) — 잡 라이프사이클을 Redis Hash + ZSet(생성순/상태별 인덱스) + TTL 상태별 차등(RUNNING 6h / COMPLETED 1h / FAILED 2h)로 저장. 서버 재시작 시 lifespan 에서 orphaned job 자동 재시도 (Semaphore 10 보수적 회복).
- APScheduler 24시간 선생성 + Config 당 RUNNING 1개 — 24시간 치 잡을 RDB 에 미리 박고 ±5분 윈도우 dedupe 로 중복 0건, Config 당 RUNNING 1개 보장 + 전역 워커 Semaphore(200).
- 2시간 cron 청크 분할 backfill — 플랫폼별 청크(BAEMIN/YOGIYO 7일, CPEATS 5일) + 사전 fetch in-memory set 으로 멱등성, AUTH_ERROR_PATTERNS 매칭으로 재시도 차단.

**도메인 이벤트·관측성**
- EventEmitter2 도메인 이벤트 + Notifly 외부 SaaS 비동기 동기화 — 결제 완료 → 사용자 속성 동기화를 이벤트 기반 비동기로 분리, 분산 락 + 5분 retry queue 로 멱등 보장.
- Datadog APM Span Tagging — `tagDatadogSpan({'payment.coupon_select.valid_count': N, 'payment.schedule.amount_mismatch': true})` 로 결제 정합성 메트릭 자동 집계.

---

## 기술 스택

| 영역 | 사용 기술 |
|---|---|
| **언어** | TypeScript, JavaScript, **Kotlin, Java**, Python 3.9 / 3.12 |
| **프레임워크** | NestJS 11, Node.js, **Spring Boot, Spring Batch**, FastAPI |
| **ORM** | TypeORM, Pony ORM, **JPA / Hibernate**, APScheduler |
| **데이터베이스** | MySQL 8 / Aurora, Oracle, PostgreSQL |
| **캐시 · 락** | Redis (ioredis, 분산 락, Lua eval, Token Bucket), Redis Cluster (ElastiCache Serverless), **Redisson** |
| **메시징** | RabbitMQ (Quorum Queue, DLX, classic queue 한계 측정), **Kafka** |
| **검색** | Elasticsearch, Logstash, Apache Nifi |
| **외부 의존성 격리** | **Resilience4j**, Custom Retry / Timeout, Single-Flight (Port-Adapter), Circuit Breaker (SOFT_OPEN / HALF_OPEN), Token Bucket |
| **헤드리스 브라우저** | Playwright, **Camoufox (Firefox stealth fork)** |
| **봇 탐지 우회** | Akamai `_abck` 4-state 머신, bm_sv polling, referrer warming, click loop jitter |
| **부하 · 관측** | Prometheus, Grafana, **Datadog APM** (dd-trace, span tagging), nGrinder, JFR |
| **테스트** | Jest, **Testcontainers, JUnit 5, Kotest**, Pytest, "계약 spec 헤더 명문화" 스타일 |
| **인프라** | Docker, Docker Compose × 8 color, Traefik dynamic config, **AWS ECS Fargate**, Naver Cloud, Jenkins, GitHub Actions |
| **마이그레이션** | Flyway, Liquibase 비교 |
| **알림** | Slack Webhook (Block Kit), NHN Toast Alimtalk (카카오 비즈메시지) |
| **AI / ML** | 자체 MLOps Score API + 6신호 노이즈 필터 (Shannon entropy, zlib 압축률, n-gram, emoji run) + 길이 가중치 (Bell + Polarity Amplification + tanh box) |
| **분산 시스템 패턴** | Redlock(Martin Kleppmann) ABA 대응 fencing token, Hexagonal Architecture(Port-Adapter), CQRS, Saga, Outbox, CAS, Bulkhead, Circuit Breaker, Single-Flight |

---

## 교육

**F-Lab Java Backend Mentoring** ｜ 2024.01 ~ 2024.07
Meta 시니어 개발자 멘토링 과정 수료. 객체지향 설계, 트랜잭션 처리, 클린 아키텍처 중심으로 동시성 제어, CQRS, 분산 트랜잭션을 심화 학습.

**경기대학교 컴퓨터과학과 졸업**

---

## 아키텍처 이미지 목록 (Excalidraw 작업용)

본 이력서에 삽입되는 다이어그램 목록 — Excalidraw 로 작성 후 SVG/PNG 로 export 하여 해당 위치에 임베드.

| ID | 위치 | 다이어그램 |
|---|---|---|
| A1 | 르몽 시스템 개요 | 전체 아키텍처 (4 저장소 × 외부 의존성 × 관측성) |
| A2 | 사례 1 | 결제 webhook 4중 방어 시퀀스 (Redis → DB UNIQUE → 상태머신 → Lua DEL) |
| B1 | 사례 5 | RDS Queue + 진행률 캐시 + 낙관락 CAS 흐름 |
| C1 | 사례 9 | SessionLockRegistry FIFO + lease TTL + handoff (4 layer) |
| C2 | 사례 10 | PAMS Before/After 비용·성공률 비교 |
| C3 | 사례 11 | Akamai 우회 시퀀스 + `_abck` 4-state 머신 |

> 각 이미지는 docx 본문 폭(약 16cm) 기준으로 가로 1,600px / 폰트 14pt 이상 / 한글 폰트 Pretendard 또는 Noto Sans KR 권장.

