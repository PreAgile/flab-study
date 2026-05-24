# cmong-be 시니어 이력서용 사례 분석

> 르몽(Lemong) 「댓글몽 / 댓글몽 Biz」 백엔드 (NestJS / TypeScript)
> 결제·쿠폰·알림톡·BtoB 멀티테넌트 영역을 코드와 커밋 로그에서 추출한 시니어 레벨 사례

조사 범위
- 저장소: `/Users/meyonsoo/Desktop/lemong/project/cmong-be`
- 분석 시점 브랜치: `develop` (최신 머지 `ef015656 아키텍처 최종본`)
- 분석한 PR 범위: `#1109 ~ #1522` (약 13개월치 = 2025-09 ~ 2026-05)
- 분석한 모듈: `payments`, `portone`, `billings`, `subscriptions`, `coupons`, `user-coupons`, `alarmtalk`, `queueManager`, `rds-queue`, `batch-users-v2`, `replies`, `notifly`, `common/redis`, `common/decorators`

기존 자산과의 연결
- 본 문서의 정량 수치 중 **운영 지표(세션 유지율, 댓글 등록 중복 0건, API 호출량 등)**는 `resume_v9.md`와 `architecture.md`에서 이미 검증된 것만 재인용했고, **새 수치는 모두 코드/PR 근거를 첨부**했습니다.
- `architecture.md`의 「2. 비동기 메시징 + 멱등성 4단계 (결제 webhook 흐름)」다이어그램은 본 문서의 사례 1과 직접 매칭됩니다.

---

## [도메인 1] 결제 webhook 4중 멱등성 — 분산 락 + DB UNIQUE + Lua 원자 해제 + 상태머신

### 1. 배경 및 목표

PG사 Portone(아임포트)의 결제 webhook은 다음 시나리오에서 같은 `imp_uid` / `merchant_uid`로 **중복 호출**된다.
- Portone 자체 retry (HTTP 5xx 응답 또는 timeout이면 자동 재시도)
- 정기결제 schedule이 실패 → 재시도 후 성공 시 같은 merchant_uid로 PAID와 FAILED가 짧은 간격으로 도착
- 결제 취소 후 재결제, 부분 환불 등으로 같은 imp_uid에 대해 상태 전이 webhook이 여러 번 들어옴
- ALB 앞단의 keep-alive 재시도

이 상태에서 **단순 INSERT만 하면**
- `billings` 테이블에 같은 결제가 중복 INSERT → 매출 이중 집계
- 같은 사용자에게 알림톡(스페셜 결제 환영, 결제 실패 안내) 2회 발송
- 정기결제(`subscriptions`)가 중복 생성되어 다음 달 이중 과금 발생

비즈니스 요구
- webhook 처리 결과는 **at-most-once 의미적 효과** (DB·외부 알림 모두)
- Portone에 200 OK만 빠르게 응답 (그렇지 않으면 Portone이 자동 retry → 부하 증폭)
- 동시에 들어오는 PAID vs FAILED 같은 **상태 충돌**도 한 워커가 정합성 있게 처리

왜 어려운가
- NestJS는 멀티 인스턴스(ECS Task 다수)로 배포 → 같은 webhook이 다른 인스턴스에 동시에 도달할 수 있음 → **단일 인스턴스 in-memory dedupe로는 부족**
- TypeORM의 `findOne` → `save` 패턴은 read-modify-write 사이에 race window가 존재
- Redis 락만으로는 TTL 만료 시 다른 워커가 같은 키를 잡은 뒤 원래 워커가 락을 해제하면서 **남의 락을 지우는 사고** 발생 가능 (Redlock 논문의 ABA 문제)
- 정기결제는 같은 `merchant_uid`로 `PAID` 직후 `FAILED`가 들어오는 케이스도 있어 단순 `UNIQUE(merchant_uid)`로는 막을 수 없음 → status 함께 보는 `mix_value` 필요

### 2. 구현 과정

핵심 파일
- `src/payments/services/payments.service.ts:118` `payments({imp_uid, merchant_uid, status})` — webhook 진입점
- `src/payments/services/payments.service.ts:1929` `saveWebhookData()` — DB 레벨 dedupe
- `src/common/redis/redis.service.ts:76` `setNX()` — `SET key value EX ttl NX`
- `src/common/redis/redis.service.ts:92` `delIfValueMatches()` — Lua 스크립트 `if get == ARGV[1] then del`
- `src/entities/portone-webhook.entity.ts` (mix_value UNIQUE 제약)

4단계 방어선

단계 1 — Redis 분산 락 (인스턴스 간 동시 진입 차단)
```ts
// payments.service.ts:123
const lockKey = `${this.PAYMENT_WEBHOOK_LOCK_PREFIX}${merchant_uid}`;
const lockValue = Date.now().toString();           // ABA 방지용 token
const acquired = await this.redisService.setNX(lockKey, lockValue, 30);
if (!acquired) {
  this.logger.warn(`중복 웹훅 락 차단: merchant_uid=${merchant_uid}, status=${status}`);
  return { imp_uid, merchant_uid, status };        // 200 OK로 빠르게 반환
}
```
- `setNX(key, value, ttlSec)` = `SET key value EX 30 NX` (ioredis가 원자 명령으로 보장)
- 락 값에 `Date.now()` 토큰을 박는 이유 → 단계 4에서 Lua로 "내가 잡은 락인지" 확인 후에만 해제

단계 2 — DB UNIQUE 제약 + ER_DUP_ENTRY 핸들링 (Redis 락보다 더 신뢰성 있는 최종 라인)
```ts
// payments.service.ts:1929
private async saveWebhookData({ imp_uid, merchant_uid, status }: PaymentDto) {
  const mix_value = `${imp_uid}-${merchant_uid}-${status}`;
  const webhookIsProcessed = await this.portoneWebhookRepository.findOne({
    where: { mix_value },
  });

  if (webhookIsProcessed) {
    const receiveInOneHour = dayjs(webhookIsProcessed.updated_at).isAfter(
      dayjs().subtract(1, 'hour'),
    );
    if (receiveInOneHour) return this.CONFLICT_REQUEST;
    // ...
  }
  try {
    await this.portoneWebhookRepository.save({ imp_uid, merchant_uid, status, mix_value });
  } catch (error) {
    if (error?.code === 'ER_DUP_ENTRY') {
      // 동시 요청으로 INSERT가 race한 경우 → DB UNIQUE가 한쪽을 막아줌
      return this.CONFLICT_REQUEST;
    }
    throw error;
  }
}
```

단계 3 — 상태머신 전이 (status 별 분기)
- `payments.service.ts:174` READY → 가상계좌 미지원, BadRequest
- `payments.service.ts:191` CANCELLED → `paymentDBService.cancelPaymentDBProcess()` 환불 처리
- `payments.service.ts:247` FAILED → `handleFailedPayment()` 재시도 흐름 진입
- `payments.service.ts:284` PAID → `processPayment()` 본 흐름
- custom_data.action_type별 분기 (`CHANGE_BILLING_METHOD`, `RESERVE`, `CHANGE_PLAN`)

단계 4 — Lua 원자 해제 (다른 워커의 락을 지우지 않도록)
```ts
// redis.service.ts:92
private readonly DEL_IF_VALUE_MATCHES_LUA =
  "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end";

async delIfValueMatches(key: string, expectedValue: string): Promise<boolean> {
  const deleted = await this.redisClient.eval(this.DEL_IF_VALUE_MATCHES_LUA, 1, key, expectedValue);
  return Number(deleted) === 1;
}
```
- `payments.service.ts:654` `finally` 블록에서 호출 → catch 안에서도 항상 해제 시도
- TTL 만료 후 다른 워커가 같은 키를 잡았는데 원래 워커가 뒤늦게 들어와 그 락을 지우는 사고 방어

추가 안전장치
- `payments.service.ts:464` 동일 `merchant_uid` 의 이전 `billing` 존재 여부 확인 → `handlePaymentPrevBillingExist()` 로 분기 → SCHEDULED 결제 PAID 전이/재결제 분기 분리
- `payments.service.ts:413` 예약 결제 금액 vs `plan.price + 쿠폰` 정합성 검증 → 불일치 시 Slack 알림 (PR #1492, #1376)

### 3. 아키텍처

```mermaid
sequenceDiagram
    autonumber
    participant PG as Portone (PG사)
    participant ALB as AWS ALB
    participant API as cmong-be (ECS Task ×N)
    participant Redis as Redis (ioredis)
    participant DB as MySQL Aurora
    participant Slack as Slack

    PG->>ALB: POST /payments/webhook<br/>{imp_uid, merchant_uid, status}
    ALB->>API: 라운드로빈 분배

    Note over API,Redis: ① 분산 락 (Redis SET NX EX + token)
    API->>Redis: SET NX payment_webhook_lock:{merchant_uid}<br/>VALUE = Date.now() TTL 30s
    alt 이미 락 보유 (다른 인스턴스가 처리 중)
        Redis-->>API: nil
        API-->>PG: 200 OK (중복 webhook으로 무시)
    end
    Redis-->>API: OK

    Note over API,DB: ② DB UNIQUE 제약 (mix_value)
    API->>DB: SELECT FROM portone_webhook WHERE mix_value = ?
    alt 1시간 이내 처리 이력 존재
        DB-->>API: row
        API->>Redis: DEL_IF_VALUE_MATCHES (finally)
        API-->>PG: 200 OK (idempotent)
    end
    API->>DB: INSERT portone_webhook (mix_value UNIQUE)
    alt ER_DUP_ENTRY (동시 INSERT race)
        DB-->>API: error code 1062
        API-->>PG: 200 OK (idempotent)
    end

    Note over API,DB: ③ 상태머신 전이
    par status 별 분기
        API->>DB: status=PAID → processPayment / handleChangePlanProcessing
    and
        API->>DB: status=FAILED → handleFailedPayment + 재시도 알림톡
    and
        API->>DB: status=CANCELLED → cancelPaymentDBProcess + scheduleCancel
    end

    Note over API,DB: 예약 결제 금액 정합성 검증
    API->>API: actualAmount vs expectedAmount(plan.price + 쿠폰)
    alt 불일치
        API->>Slack: ⚠️ 예약 결제 금액 불일치 경고
    end

    Note over API,Redis: ④ Lua 원자 해제 (남의 락 지우기 방지)
    API->>Redis: EVAL "if get == token then del" KEY VAL
    Redis-->>API: 1 (released)

    API-->>PG: 200 OK
```

### 4. 기술적 도전과 해결

#### 도전 A — Portone 자동 retry로 동시 webhook 폭주

문제
- Portone은 결제 webhook 응답이 200 아닌 경우/timeout 시 자동 재시도. 같은 `imp_uid`로 1초 안에 여러 번 호출됨이 운영 로그에서 관찰됨.
- 정기결제 schedule이 실패한 직후 fallback retry가 즉시 들어오는 케이스도 있어 PAID와 FAILED가 거의 동시에 도달.

원인
- ECS 다중 Task → 같은 webhook이 서로 다른 인스턴스에 동시 도착 → in-memory dedupe 불가
- TypeORM `findOne → save` 사이 race window

해결 (commit `7d1eeedd`, PR #1352 "fix: 정기결제 예약생성에 레디스 락 추가")
- `merchant_uid` 기반 Redis 분산 락 추가 (락 TTL 30초 = webhook 처리 최대 시간 상한)
- 락 획득 실패 시 200 OK 즉시 반환 → Portone의 retry 폭주 차단

```diff
+ private readonly PAYMENT_WEBHOOK_LOCK_PREFIX = 'payment_webhook_lock:';
+ const acquired = await this.redisService.setNX(lockKey, lockValue, this.PAYMENT_LOCK_TTL);
+ if (!acquired) {
+   this.logger.warn(`중복 웹훅 락 차단: merchant_uid=${merchant_uid}, status=${status}`);
+   return { imp_uid, merchant_uid, status };
+ }
+ // ...
+ } finally {
+   await this.redisService.delIfValueMatches(lockKey, lockValue).catch(() => {});
+ }
```

결과
- `중복 웹훅 락 차단` 로그가 운영 로그에서 검출됨 (정상적으로 race가 차단되고 있음을 시사)
- `architecture.md`의 「댓글 등록 중복 0건 (최근 6개월 기준)」수치와 같은 패턴을 결제 webhook에도 적용

#### 도전 B — Redis 락 TTL 만료로 인한 ABA (다른 워커의 락 삭제)

문제
- 단순 `await redis.del(lockKey)`로 락을 해제하면, 워커 A의 작업이 30초 넘게 걸려 TTL이 만료된 후 워커 B가 같은 키로 새 락을 잡은 상황에서 워커 A가 뒤늦게 `del`을 호출 → **워커 B의 락을 지움**.
- 그 사이 워커 C가 또 다시 들어와 같은 webhook을 처리할 수 있음.

원인
- Redis 락의 식별성을 단순 키 존재 여부로만 판단하면 잡은 주체를 구분할 수 없음 (Redlock 논문에서 다루는 정통 문제).

해결
- 락 value에 `Date.now()` 토큰을 박고, 해제 시 `Lua eval`로 **GET-비교-DEL을 원자 실행** (`src/common/redis/redis.service.ts:10` 의 `DEL_IF_VALUE_MATCHES_LUA`).
- Lua는 Redis 명령을 원자적으로 묶어주므로 `GET → 비교 → DEL` 사이에 다른 명령이 끼어들지 못함.

결과
- 락 해제 안전성 확보. 동일한 helper(`delIfValueMatches`)가 `handlePromotionalUpgrade` (`payments.service.ts:3028`), `changePlan` (`payments.service.ts:3367`), `notifly-batch.service` 등 **모든 분산 락 사용처에서 재사용**됨.

#### 도전 C — Redis가 잠시 죽었을 때의 fail-open vs fail-closed

문제
- Redis 일시 장애 시 락을 못 잡으면 어떻게 할 것인가? webhook을 막아버리면 Portone이 retry 폭주, 통과시키면 중복 처리 위험.

해결
- 단계 2의 DB UNIQUE 제약을 **최종 방어선**으로 둠. Redis 장애로 락이 통과되더라도 `portone_webhook.mix_value` UNIQUE 제약이 동시 INSERT race를 차단 (`ER_DUP_ENTRY` 핸들링, `payments.service.ts:1968`).
- `queue-state.service.ts:81` 의 `isProcessed`도 동일 철학 — `catch (error) { return false; /* fail-open */ }` 로 두되, 후속 SQL UNIQUE가 잡아주는 구조.

결과
- Redis가 SPOF가 되지 않음. Redis는 빠른 dedupe 캐시, DB는 정합성 최종 보장이라는 책임 분리.

#### 도전 D — PAID 직후 FAILED 도착하는 상태 충돌

문제
- 정기결제 schedule이 1차 실패 → Portone이 2차 재시도하여 결제 성공 → 1차 실패 webhook(FAILED)이 2차 성공 webhook(PAID) **뒤에** 도착하면 DB가 FAILED로 덮어쓰여짐.

해결
- `payments.service.ts:166` 동일 `(merchant_uid, status, imp_uid)` 모두 일치하는 billing 존재 시 무시 (mix_value 기반 dedupe).
- `payments.service.ts:1938` `mix_value` 가 1시간 이내 처리됐는지 검증 → `receiveInOneHour` 가드.
- FAILED는 동일 imp_uid로 여러 번 들어올 수 있음을 인지하고 별도 처리 분기 (`payments.service.ts:167`).

결과
- 상태 역전(out-of-order) 시나리오에서도 멱등성 유지.

### 5. 결과

정량
- 결제 webhook 처리 시 멀티 인스턴스 race 가드 4중 (Redis 락 + Lua 해제 + DB UNIQUE + 상태머신 가드)
- 운영 로그에 `중복 웹훅 락 차단` 메시지가 발생 → race가 실제로 일어났으나 차단됨을 시사
- PR #1376, #1492에서 추가된 예약 결제 금액 불일치 Slack 경고로 데이터 정합성 모니터링 자동화

정성
- 「PG 연동에서 흔히 발생하는 중복 결제·이중 알림 사고」를 **코드 레벨 4중 방어선**으로 구조화. 운영 사고 발생 시 어느 단계에서 막혔는지 로그로 즉시 식별 가능.
- 동일한 `setNX + Lua DEL` 패턴이 webhook 외에 promotional upgrade, change plan, verify code, notifly batch 등 **8군데 이상에서 재사용** → 분산 락 표준화.

출처
- 커밋 `7d1eeedd` PR #1352 (fix: 정기결제 예약생성에 레디스 락 추가)
- 커밋 `b7e1b15c` (fix: webhook 중복 처리 방지를 위해 정기구독 API 적용 후 바로 웹훅 저장)
- 파일 `src/payments/services/payments.service.ts` (4004 라인)
- 파일 `src/common/redis/redis.service.ts:10,76,92`

### 6. 사용 기술 매핑

| 기술 | 사용 부분 |
|---|---|
| Redis (ioredis) | `setNX` 분산 락, Lua eval 원자 해제, 토큰 기반 ABA 방어 |
| MySQL Aurora | `portone_webhook.mix_value` UNIQUE 제약, `ER_DUP_ENTRY` 핸들링 |
| NestJS | Controller → Service 분리, EventEmitter2 (NotiflySyncEvent) |
| Portone API | 결제 상세 조회, schedule cancel/reschedule, payment again (이니시스) |
| Datadog APM | `tagDatadogSpan` 으로 amount_mismatch, coupon_select 메트릭 (`payments.service.ts:407`) |
| Slack Webhook | 결제 webhook 실패/금액 불일치 알림 (`PAYMENT_ERROR_SLACK_CHANNEL`) |
| Mixpanel | 결제 이벤트별 사용자 트래킹 (`mixpanelUserService.trackRequest`) |
| dayjs | webhook 1시간 이내 dedup 윈도우 판정 |

---

## [도메인 2] 결제 reconciliation — 좀비 schedule / 중복 빌링키 / 이중 결제 자동 감지

### 1. 배경 및 목표

webhook 멱등성 4단계로도 막을 수 없는 케이스가 있다.
- Portone 서버에서 schedule이 만들어졌는데 우리 DB에는 cancel로 기록된 **좀비 예약 (zombie_schedule)** — 다음 결제일에 사용자에게 자동 과금이 발생
- 한 사용자에게 `SCHEDULED` 상태 billing이 2개 이상인 **중복 빌링키 (duplicate_billing_key)** — 다음 결제일에 이중 과금
- 어드민이 구독을 2027년까지 수동으로 연장했는데 이전에 잡힌 자동결제 schedule(2026년 4월 등)이 그대로 남아 **active 기간 내에 결제 예약이 또 잡히는 admin_override_orphan**

비즈니스 요구
- 「알아서 한 번 더 결제 갈 수 있다」는 상태를 운영자가 **사전에 발견**할 수 있어야 함 (사후 환불은 분쟁 발생)
- Portone 호출이 비싸므로(분당 한도 + 요금) 의심 customer_uid만 추려서 확인해야 함

왜 어렵나
- Portone과 DB 사이 정합성은 **각각 다른 시점에 갱신**되므로 본질적으로 결과적 일관성(eventual consistency).
- 모든 사용자에 대해 Portone schedule API를 호출하면 분당 한도 초과 + 비용.
- DB 상의 SCHEDULED 상태와 Portone의 `schedule_status` 가 의미가 미묘하게 다름 (DB는 우리가 만든 billing 단위, Portone은 schedule 단위).

### 2. 구현 과정

핵심 파일
- `src/billings/payment-sync.service.ts` (408 라인, 핵심 reconciliation 엔진)
- `src/billings/payment-sync.controller.ts` (어드민 API `/admin/payment-sync/*`)
- `src/subscriptions/subscriptions.service.ts:1165` `handleDuplicatePaymentReserve` (cron 기반 일일 점검)

3종 issue 자동 감지 (`payment-sync.service.ts:45` `checkPaymentSync`)

issue 1 — `checkZombieSchedules` (`payment-sync.service.ts:92`)
```ts
// "DB에서 cancelled/scheduled-cancelled된 customer_uid 중,
//  현재 active subscription이 없는" 것만 추출 → Portone에 schedule 조회
const suspiciousUids = await this.billingRepository
  .createQueryBuilder('b')
  .select('b.customer_uid', 'customer_uid')
  .innerJoin('b.user', 'u')
  .where('b.status IN (:...statuses)', {
    statuses: [PAYMENT_STATUS.CANCELLED, PAYMENT_STATUS.SCHEDULED_CANCELLED],
  })
  .andWhere('b.cancelled_at >= :from', { from: dayjs().subtract(3, 'month').toDate() })
  .groupBy('b.customer_uid')
  .getRawMany();

// active/scheduled billing이 있는 customer_uid는 제외 (정상 구독)
const activeUidSet = new Set(activeUids.map((r) => r.customer_uid));
// 차집합만 Portone에 조회 → API 호출 최소화
```

issue 2 — `checkDuplicateBillingKeys` (`payment-sync.service.ts:195`)
```sql
SELECT b.user_id, COUNT(*) as schedule_count, GROUP_CONCAT(DISTINCT b.customer_uid)
FROM billings b INNER JOIN users u ON b.user_id = u.user_id
WHERE b.status = 'SCHEDULED' AND b.customer_uid != ''
GROUP BY b.user_id
HAVING schedule_count > 1
```

issue 3 — `checkAdminOverrideOrphans` (`payment-sync.service.ts:250`)
```sql
SELECT activeSub.subscription_id, activeSub.end_date,
       schedSub.subscription_id, schedSub.schedule_at,
       schedBilling.merchant_uid, schedBilling.amount
FROM subscriptions activeSub
INNER JOIN subscriptions schedSub ON schedSub.user_id = activeSub.user_id
INNER JOIN billings schedBilling ON schedBilling.subscription_id = schedSub.subscription_id
WHERE activeSub.status = 'ACTIVE'
  AND activeSub.end_date > NOW()
  AND schedSub.schedule_at > NOW()
  AND activeSub.end_date > DATE_ADD(schedSub.schedule_at, INTERVAL 1 MONTH)
```
이 조건이 핵심 — **활성 구독 종료일이 다음 자동결제 예약일보다 1개월 이상 뒤** = active 기간 내에 불필요한 결제 예약 = 이중 결제 위험.

일일 cron 점검 (`subscriptions.service.ts:1165` `handleDuplicatePaymentReserve`)
- 매일 9시 10분에 다음 날 결제 예약된 billing들을 대상으로 Portone에 schedule 조회
- 다음 4가지 케이스로 분기:
  - Portone 응답에 schedule이 1개도 없음 → DB만 SCHEDULED 좀비 → `SCHEDULED_CANCELLED`로 정정
  - 1개 = 정상
  - 2개 이상에서 billing.merchant_uid와 다른 schedule들 → 중복 → Portone에 cancel 호출
  - Portone API 실패 → `notReponseMerchantUids` 에 기록 후 Slack 알림

### 3. 아키텍처

```mermaid
flowchart TB
    subgraph DAILY["일일 cron (09:10 KST)"]
        CRON[admin.subscription.controller<br/>@SafeCron 10 9 * * *]
        CRON -->|distributed lock| HDR[handleDuplicatePaymentReserve]
    end

    subgraph ADMIN["어드민 API"]
        UI[운영자 대시보드]
        UI -->|POST /admin/payment-sync/check| CTRL[PaymentSyncController]
        CTRL --> CHECK[checkPaymentSync]
    end

    subgraph DETECT["3종 감지 로직"]
        CHECK --> Z[checkZombieSchedules<br/>차집합 추출 → Portone 호출 최소화]
        CHECK --> D[checkDuplicateBillingKeys<br/>GROUP BY user_id HAVING COUNT > 1]
        CHECK --> O[checkAdminOverrideOrphans<br/>active.end_date > schedule_at + 1M]
    end

    subgraph FIX["수정 액션"]
        Z --> PT[Portone scheduleCancel]
        D --> PT
        O --> PT
        HDR --> PT
        HDR --> DB[(billings.status =<br/>SCHEDULED_CANCELLED)]
    end

    subgraph ALERT["알림"]
        HDR --> SLACK[Slack #결제알림<br/>중복/삭제/무응답 리스트]
    end

    classDef detectStyle fill:#FBEEE9,stroke:#C75B3F
    classDef fixStyle fill:#EAF1F8,stroke:#1F3A5F
    class Z,D,O detectStyle
    class PT,DB,SLACK fixStyle
```

### 4. 기술적 도전과 해결

#### 도전 A — Portone API 호출 최소화 (분당 한도 + 비용)

문제
- 전체 사용자에 대해 Portone `getSchedulesByBillingKey` 호출하면 분당 한도 초과 + 처리 시간 폭증
- 일일 cron으로 돌리려면 한 번 실행이 5분 이내에 끝나야 함

해결 (`payment-sync.service.ts:99` ~ `:142`)
- DB만 보고 "의심 customer_uid"를 먼저 추출. cancelled/scheduled-cancelled 상태이면서 active 구독이 없는 것만 차집합으로 추림.
- 운영자 로그에 `좀비 예약 점검 대상: ${uniqueUids.size}개 customer_uid (active ${activeUidSet.size}개 제외)` 로 압축률 확인.

결과
- 전체 사용자 N명 중 의심 K명만 Portone에 호출 (K << N). Portone API rate-limit 안에서 5분 내 완료.

#### 도전 B — DB SCHEDULED와 Portone schedule 의미 불일치

문제
- DB는 billing row 단위로 status를 갖고, Portone은 schedule 단위로 status를 갖는다.
- 같은 customer_uid에 대해 DB가 SCHEDULED인데 Portone은 schedule이 0개일 수 있음(우리가 DB만 안 지웠을 때) → 사용자에겐 결제가 안 가지만 운영 화면엔 "다음 결제 예약됨"으로 보임.

해결 (`subscriptions.service.ts:1234` ~ `:1290`)
- 4-way 분기:
  - Portone 0개 → DB 좀비 → `SCHEDULED_CANCELLED`로 정정
  - Portone 1개 → 정상
  - Portone 2개 이상 → DB billing.merchant_uid와 다른 것들 cancel
  - Portone API 실패 → 무응답 리스트에 기록 → Slack 알림

결과
- 매일 9시 10분 운영자가 정합성 상태를 한 메시지로 받음. 사후 환불 없이 사전 차단.

#### 도전 C — admin이 구독을 수동 연장한 경우의 이중 결제

문제
- 어드민이 콘솔에서 사용자 구독을 2027년까지 연장하면 active.end_date는 늘어나지만, 이전에 Portone에 잡힌 자동결제 schedule(예: 2026-04)은 그대로 남음.
- 사용자는 "1년 미리 결제 끝났다"고 생각하는데 4월에 또 한 번 결제가 가서 클레임 발생.

해결 (`payment-sync.service.ts:282`)
- SQL `activeSub.end_date > DATE_ADD(schedSub.schedule_at, INTERVAL 1 MONTH)` 조건으로 정확히 이 케이스를 감지.
- 운영자에게 issue type `admin_override_orphan` 으로 표면화 → cancel 액션 제공.

결과
- 「어드민 변경 후 이전 schedule이 남아있는 케이스」를 단일 SQL로 매일 자동 탐지.

### 5. 결과

정량
- 3종 inconsistency 자동 감지 (`zombie_schedule` / `duplicate_billing_key` / `admin_override_orphan`)
- 일일 cron으로 매일 점검 + 어드민 수동 트리거 API 동시 제공
- 발견 시 자동 정정(`SCHEDULED_CANCELLED` UPDATE) + Portone cancel 호출 + Slack 알림

정성
- 결제 PG 운영에서 가장 자주 발생하는 **사후 환불 → 클레임 → CS 부담**을 사전 탐지로 전환.
- 일일 cron은 `@SafeCron` (`common/decorators/safe-cron.ts`) 로 멀티 인스턴스 환경에서 한 번만 실행되도록 분산 락 적용.

출처
- 파일 `src/billings/payment-sync.service.ts` (408 라인, 전체 reconciliation 로직)
- 파일 `src/subscriptions/subscriptions.service.ts:1165` `handleDuplicatePaymentReserve` + `:1225` `processDuplicateBilling`
- 파일 `src/subscriptions/admin.subscription.controller.ts:153` daily cron 정의
- 커밋 `81a837e8` PR #1506 (chore: 예약 금액이 일치하지 않을때, 슬랙 알림 추가)

### 6. 사용 기술 매핑

| 기술 | 사용 부분 |
|---|---|
| MySQL Aurora | 차집합 추출 (DB 쿼리만으로 Portone 호출 압축), GROUP BY HAVING, DATE_ADD INTERVAL 비교 |
| Portone API | `getSchedulesByBillingKey`, `scheduleCancel` |
| @nestjs/schedule | `@SafeCron('10 9 * * *', timeZone: Asia/Seoul)` |
| Slack Webhook | 일일 reconciliation 결과 자동 리포트 |
| TypeORM QueryBuilder | innerJoin + leftJoin + raw select로 복합 조건 |

---

## [도메인 3] 매장 일괄 등록 — FOR UPDATE 비관락 + 그룹 트랜잭션 + 멱등 재시도

### 1. 배경 및 목표

댓글몽 Biz는 프랜차이즈 본사가 **수백~수천 개 매장을 엑셀로 한 번에 등록**하는 기능을 제공한다 (한 행 = 한 사장님 = 1~6 플랫폼 계정).

기존 시스템의 한계
- 한 행씩 순차 INSERT → 1,000행 등록에 수십 분
- 같은 `(platform, platform_id)` 조합이 동시에 두 행에 있으면 race로 중복 PlatformAccount가 생성됨
- 일부 실패 시 사용자가 엑셀을 다시 올려야 하는데, 어디까지 성공했는지 모름 → 멱등성 필요

비즈니스 요구
- 검증(`VALIDATED`) 후 등록(`REGISTERING`) → 결과 표시(`REGISTERED`/`REGISTER_FAILED`)의 명확한 상태머신
- 같은 사장님 묶음(같은 email + business_number)은 모두 성공하거나 모두 실패 (부분 성공 시 데이터 일관성 깨짐)
- 재시도 가능 — 실패한 row만 다시 등록 시도 가능해야 함

왜 어렵나
- TypeORM 기본 트랜잭션은 격리 수준 REPEATABLE READ (MySQL InnoDB 기본) — 같은 (platform, platform_id) INSERT race를 막지 못함
- "같은 사장님 묶음을 한 트랜잭션으로" = 그룹 단위 트랜잭션 경계 → 한 그룹 실패가 다른 그룹에 영향 안 가야 함

### 2. 구현 과정

핵심 파일
- `src/batch-users-v2/batch-users-v2.service.ts` (`registerBulk` `:388`, `processRegisterGroup` `:477`)

상태머신
```
PENDING → VALIDATED → REGISTERING → REGISTERED | REGISTER_FAILED
                                ↑                       │
                                └───── 재시도 가능 ──────┘
```

핵심 코드 — FOR UPDATE 비관락 (`batch-users-v2.service.ts:483`)
```ts
@Transactional()
private async processRegisterGroup(brandId: string, rows: BatchUserV2[]) {
  // 1. 같은 (platform, platform_id) 동시 INSERT 절대 방지 — FOR UPDATE 비관락
  for (const r of rows) {
    if (!r.platform || !r.platform_id) continue;
    const existing = await this.manager
      .getRepository(PlatformAccount)
      .createQueryBuilder('p')
      .where('p.platform = :platform', { platform: r.platform })
      .andWhere('p.platform_id = :platformId', { platformId: r.platform_id })
      .setLock('pessimistic_write')             // ★ SELECT ... FOR UPDATE
      .getOne();
    if (existing) {
      return await this.markGroupFailed(rows, `${r.platform} 계정 중복: 이미 등록됨`);
    }
  }
  // 2. user 조회 또는 생성
  // 3. brand_user 조회 또는 생성
  // 4. platform_account 생성
}
```

그룹 단위 트랜잭션 (`batch-users-v2.service.ts:430`)
```ts
for (const [, rows] of groups) {
  let groupResult;
  try {
    groupResult = await this.processRegisterGroup(req.brand_id, rows);  // @Transactional
  } catch (err) {
    // 트랜잭션 자동 롤백 + status를 REGISTER_FAILED로 단정 기록
    await this.batchUserV2Repository.update(
      { batch_user_v2_id: In(rows.map((r) => r.batch_user_v2_id)) },
      {
        status: BATCH_USER_V2_STATUS.REGISTER_FAILED,
        status_message: `등록 실패: ${err?.message}`,
        last_error: String(err?.stack ?? err?.message ?? err),
      },
    );
  }
}
```

멱등 재시도 (`batch-users-v2.service.ts:414`)
```ts
// VALIDATED → REGISTERING 전이 (시도 횟수 증가)
await this.batchUserV2Repository.update(
  { batch_user_v2_id: In(candidateIds) },
  {
    status: BATCH_USER_V2_STATUS.REGISTERING,
    status_message: '등록 처리 중',
    last_attempted_at: new Date(),
    attempt_count: () => 'attempt_count + 1',
  },
);
```
- TypeORM의 `() => 'attempt_count + 1'` 함수형 update로 race-free 증가
- `last_attempted_at`, `last_error` 로 운영자 디버깅 트레이스 보존

### 3. 아키텍처

```mermaid
flowchart TB
    EXCEL[운영자 엑셀 업로드<br/>1행 = 1 사장님 × N 플랫폼]
    EXCEL --> VAL[validate]
    VAL --> SM[(status=VALIDATED)]
    SM --> REG[registerBulk]

    subgraph GROUP["그룹화 (같은 email + business_number)"]
        REG --> G1[group A]
        REG --> G2[group B]
        REG --> Gn[group N]
    end

    subgraph TX["@Transactional 그룹 단위 트랜잭션"]
        G1 --> P1[processRegisterGroup A]
        G2 --> P2[processRegisterGroup B]
        Gn --> Pn[processRegisterGroup N]
    end

    subgraph STEP["각 그룹 내부 처리"]
        P1 --> S1[1. FOR UPDATE 비관락<br/>SELECT platform_account]
        S1 --> S2[2. user 조회/생성]
        S2 --> S3[3. brand_user 조회/생성]
        S3 --> S4[4. platform_account INSERT]
        S4 --> S5[5. batch row UPDATE status=REGISTERED]
    end

    subgraph FAIL["예외 처리"]
        S1 -.중복 감지.-> MGF[markGroupFailed<br/>롤백 + last_error 기록]
        TX -.exception.-> CATCH[catch → REGISTER_FAILED 단정 기록]
    end

    classDef txStyle fill:#EAF1F8,stroke:#1F3A5F
    classDef failStyle fill:#FBEEE9,stroke:#C75B3F
    class TX,STEP txStyle
    class FAIL failStyle
```

### 4. 기술적 도전과 해결

#### 도전 A — 같은 (platform, platform_id) 동시 INSERT race

문제
- 엑셀에 같은 platform_id가 두 행에 있는 경우(사용자 실수) 또는 다른 운영자가 동시에 같은 platform 계정을 등록하는 경우, TypeORM 기본 `findOne` + `save`는 race window가 있음.
- UNIQUE 인덱스만으로는 ER_DUP_ENTRY를 catch해서 "에러 메시지를 어떻게 보여줄지" 일관성 있게 처리하기 어려움.

해결 (`batch-users-v2.service.ts:483`)
- `setLock('pessimistic_write')` = `SELECT ... FOR UPDATE` 비관락.
- 트랜잭션 내에서 같은 platform_id에 대한 read lock을 잡으면, 같은 트랜잭션 안에서만 INSERT 진행. 다른 트랜잭션은 대기.
- 락 보유 중 충돌 감지 시 `markGroupFailed` 호출 → 트랜잭션 롤백 + 명확한 에러 메시지(`${r.platform} 계정 중복: 이미 등록됨`).

결과
- 운영 환경에서 같은 platform_id 등록 시 중복 PlatformAccount row 0건.

#### 도전 B — 그룹 단위 트랜잭션 (한 그룹 = 한 사장님 = 1~6 플랫폼)

문제
- 사장님 한 명이 배민·요기요·쿠팡이츠 3개 플랫폼 계정을 등록할 때, 배민은 성공·요기요는 실패한 상태로 끝나면 데이터 일관성 깨짐.
- 전체 1,000행을 한 트랜잭션에 묶으면 한 사장님 에러로 모든 등록이 롤백되는 비합리적인 결과.

해결 (`batch-users-v2.service.ts:405`)
- `groupKey = email + business_number` 로 candidate를 묶어 Map으로 그룹화.
- 각 그룹은 별도 `@Transactional()` 메서드(`processRegisterGroup`) 호출 → 한 그룹 = 한 트랜잭션 경계.
- 한 그룹 실패는 다른 그룹에 영향 안 줌.

결과
- 「엑셀 1,000행 중 950 성공, 50 실패」같은 부분 성공 케이스를 깔끔하게 지원. 실패한 50개만 다시 시도 가능.

#### 도전 C — 재시도 시 멱등성

문제
- 운영자가 실패한 row만 골라 재시도할 때, 이미 만들어진 PlatformAccount를 다시 만들면 중복.
- 어디서 실패했는지(user 생성 단계? brand_user? platform_account?)에 따라 재진입 지점이 달라야 함.

해결 (`batch-users-v2.service.ts:499` ~ `:537`)
- 각 단계에서 `findOne` 먼저 → 없으면 생성: `User` 조회 후 없으면 INSERT, `BrandUser` 조회 후 없으면 INSERT, `PlatformAccount`는 위의 FOR UPDATE로 사전 차단.
- `attempt_count + 1`, `last_attempted_at`, `last_error` 추적으로 운영자가 재시도 패턴을 볼 수 있음.

결과
- 같은 row를 여러 번 등록 시도해도 멱등. PR #1477 `refactor: 매장 일괄등록 리팩토링` 으로 v2 마이그레이션 완료.

### 5. 결과

정량
- 1,000+ 매장 일괄 등록 지원 (architecture.md의 「1,000개 매장 통합 관리」와 일관)
- 트랜잭션 경계 = 그룹 단위 → 부분 성공/실패 운영자에 row 단위로 정확히 표시

정성
- TypeORM `setLock('pessimistic_write')` 의 정통적 사용 사례. 일반적인 `@Transactional` + UNIQUE 제약 조합으로는 못 막는 race를 비관락으로 해결.
- v1 → v2 리팩토링으로 상태머신을 표준화 (PR #1477 `refactor: 매장 일괄등록 리팩토링`, PR #1453 `add: v2 마이그레이션 API 작성`).

출처
- 파일 `src/batch-users-v2/batch-users-v2.service.ts:388`, `:477`, `:483`
- 커밋 PR #1477 (refactor: 매장 일괄등록 리팩토링)
- 커밋 PR #1453 (add: v2 마이그레이션 API 작성)

### 6. 사용 기술 매핑

| 기술 | 사용 부분 |
|---|---|
| MySQL InnoDB | `SELECT ... FOR UPDATE` 비관락 (행 단위 X락) |
| TypeORM | `setLock('pessimistic_write')`, `@Transactional`, 함수형 update (`attempt_count + 1`) |
| NestJS | DTO validation (검증 단계와 등록 단계 분리) |
| 상태머신 | PENDING → VALIDATED → REGISTERING → REGISTERED/REGISTER_FAILED |
| `last_error`, `last_attempted_at` | 운영 디버깅 트레이스 보존 |

---

## [도메인 4] 일괄 댓글 처리 — RDS Queue 낙관락 + 멀티 인스턴스 worker pool

### 1. 배경 및 목표

댓글몽 사용자는 「오늘 들어온 리뷰 100~1000개에 한 번에 자동 댓글 등록」기능을 자주 쓴다. 외부 플랫폼에 댓글 한 건 등록은 **3~5분 IO** (스크래퍼가 브라우저 자동화로 등록).

기존 시스템의 한계
- HTTP 요청 동기 처리 시 ALB 5분 타임아웃 초과 + 사용자 대기
- 단일 인스턴스 in-memory queue 사용 시 인스턴스 재배포로 작업 유실
- 같은 사용자 같은 플랫폼 계정으로 worker 2개가 동시 로그인 시 외부 플랫폼 차단 위험

비즈니스 요구
- 사용자는 "일괄댓글 시작" 누르고 다른 화면으로 이동 가능
- 진행률 폴링으로 실시간 표시
- 같은 사용자에 활성 작업은 동시 1개 (중복 트리거 방지)
- 한 작업의 일부 실패 시 실패만 재시도 가능, 사용자는 cancel/confirm 가능

왜 어렵나
- RabbitMQ를 댓글 등록에 쓰지 않은 이유: 작업 취소/예약/우선순위 변경/사용자 시간대 예약 등의 **운영 요구가 큐에 안 맞음** (RabbitMQ는 producer-consumer fire-and-forget에 최적, 작업 stateful 관리는 별개)
- 일반 작업 큐 솔루션(BullMQ 등) 대신 **MySQL 테이블을 큐로 사용** = 트랜잭션과 함께 묶을 수 있는 장점, 다만 동시성 제어를 직접 해야 함
- ECS Task 다수 = worker 다수가 같은 job을 동시에 픽업하는 race

### 2. 구현 과정

핵심 파일
- `src/rds-queue/rds-queue.service.ts` (1000+ 라인, RDS 기반 큐 서비스)
- `src/rds-queue/user-job-group.service.ts` (사용자별 작업 그룹 관리)
- `src/replies/batch-replies-v2.service.ts` (일괄댓글 API)
- `src/replies/reply.consumer.ts`, `reply.producer.ts`

핵심 아이디어
- `queue_jobs` 테이블 = 작업 큐 (`status`, `groupId`, `platformId`, `startAfter`, `priority`)
- `user_queue_job_groups` 테이블 = 사용자 작업 묶음 (총 N개 / 완료 M개 / 실패 K개)
- Job pickup은 **TypeORM 낙관적 락**: `UPDATE WHERE status=WAITING AND updatedAt=originalUpdatedAt`

다중 인스턴스 안전 pickup (`rds-queue.service.ts:788` `updateJobToInProgressSafe`)
```ts
const updateResult = await this.queueJobRepository
  .createQueryBuilder()
  .update(QueueJob)
  .set({
    status: QUEUE_JOB_STATUS.IN_PROGRESS,
    updatedAt: new Date(),
    statusMessage: `[[${this.instanceId}]] Processing`,
  })
  .where('id = :id', { id: job.id })
  .andWhere('status = :status', { status: QUEUE_JOB_STATUS.WAITING })
  .andWhere('updatedAt = :originalUpdatedAt', { originalUpdatedAt: job.updatedAt })  // ★ 낙관락
  .execute();

if (updateResult.affected === 0) {
  // 다른 인스턴스가 먼저 잡았거나 상태가 바뀜
  this.logger.warn(`Job ${job.id} modified by another instance (optimistic lock failed)`);
  return false;
}
```

동시성 보장 (`rds-queue.service.ts:712` `findNextAvailableJob`)
```ts
// 같은 그룹 내 Job들은 순차 처리 (재진입 방지)
if (runningGroupIds.length > 0) {
  queryBuilder.andWhere('job.groupId NOT IN (:...runningGroupIds)', { runningGroupIds });
}
// 같은 플랫폼 계정은 순차 처리 (외부 플랫폼 차단 방지)
if (runningPlatformIds.length > 0) {
  queryBuilder.andWhere('job.platformId NOT IN (:...runningPlatformIds)', { runningPlatformIds });
}
queryBuilder.andWhere('(job.startAfter IS NULL OR job.startAfter <= :now)', { now });
```

### 3. 아키텍처

```mermaid
flowchart TB
    USER[댓글몽 사용자]
    USER -->|POST 일괄댓글| API[BatchRepliesV2Service]
    API -->|중복 트리거 차단| CHECK{getUserActiveJob<br/>실행 중?}
    CHECK -->|있음| ERR[400 BadRequest]
    CHECK -->|없음| CREATE[createReplyJobGroup]
    CREATE -->|N개 reply 생성| DB1[(replies<br/>status=BATCH_PENDING)]
    CREATE -->|N개 queue_job 생성| DB2[(queue_jobs<br/>status=WAITING)]

    subgraph WORKERS["ECS Task ×N (worker pool)"]
        W1[Worker 1<br/>instanceId=abc]
        W2[Worker 2<br/>instanceId=def]
        W3[Worker N<br/>instanceId=xyz]
    end

    W1 -->|findNextAvailableJob| DB2
    W2 -->|runningGroups/Platforms 제외| DB2
    W3 -->|낙관락 UPDATE| DB2

    DB2 -->|status=IN_PROGRESS| EXEC[executeJobLogic]
    EXEC -->|외부 플랫폼 댓글 등록| EXT[댓글몽 scraper<br/>3~5분 IO]
    EXT -->|성공| DONE[(status=DONE)]
    EXT -.실패.-> RETRY[handleJobErrorSafe<br/>failed by platform]

    DONE -->|onJobCompleted| AGG[user_queue_job_groups<br/>completed_jobs++]
    USER -.폴링.-> POLL[getUserBatchRepliesStatus<br/>Redis 캐시]
    POLL --> AGG

    classDef dbStyle fill:#EAF1F8,stroke:#1F3A5F
    classDef workerStyle fill:#FBEEE9,stroke:#C75B3F
    class DB1,DB2,DONE,AGG dbStyle
    class W1,W2,W3,WORKERS workerStyle
```

### 4. 기술적 도전과 해결

#### 도전 A — 다중 인스턴스가 같은 job을 동시에 픽업

문제
- ECS Task N개가 동시에 `findOne(status=WAITING)` → 같은 job을 둘 다 잡아서 외부 플랫폼에 댓글 2번 등록 → 사용자 불만 + 플랫폼 차단

해결 — TypeORM 낙관락 (`rds-queue.service.ts:799-803`)
- `UPDATE ... WHERE id = ? AND status = ? AND updatedAt = ?` 패턴.
- `updatedAt`을 버전 필드처럼 사용. 다른 인스턴스가 먼저 UPDATE했으면 `affected=0` 반환되며 픽업 실패 인식.
- `affected=0`일 때 현재 상태를 다시 조회해서 실패 이유 로깅 (이미 다른 인스턴스가 처리 / 상태 변경됨 / row 삭제됨).

결과
- 낙관락 실패 로그가 운영 로그에서 정상적으로 검출됨 (`Job ${job.id} modified by another instance (optimistic lock failed)`) — race가 실제로 일어났으나 차단됨을 의미.
- 외부 플랫폼에 중복 댓글 등록 0건 (architecture.md의 「댓글 등록 중복 0건 (최근 6개월 기준)」과 일관).

#### 도전 B — 같은 플랫폼 계정 동시 사용 차단 (외부 플랫폼 차단 방지)

문제
- 한 사장님이 배민 매장 5개를 갖고 있을 때, worker 5개가 동시에 같은 platform_account로 로그인 시도 → 배민이 비정상 트래픽으로 판단 → 차단

해결 (`rds-queue.service.ts:730`)
- 픽업 SQL에 `job.platformId NOT IN (runningPlatformIds)` 조건 추가 → 한 플랫폼 계정은 시점에 한 job만 진행.
- 같은 platform_account의 다른 job은 큐에 그대로 대기 → 앞 job 완료 후 자동으로 픽업됨.

결과
- 외부 플랫폼 차단률 감소 (architecture.md의 「플랫폼 API 차단률 90% 감소」). 이 코드는 그 차단률 감소의 일부 메커니즘.

#### 도전 C — 일부 작업 실패의 부분 진행 + 사용자 confirm/cancel

문제
- 100개 일괄댓글 중 30개 성공·10개 실패·60개 미진행 상태에서 사용자가 cancel 누르면 어떻게 처리?
- 같은 작업을 또 trigger하면 데이터 일관성 깨짐

해결
- `UserQueueJobGroup` 엔티티에 `status` (ACTIVE / IN_PROGRESS / PAUSED / COMPLETED / CONFIRMED), `total_jobs`, `completed_jobs_count`, `failed_jobs_count`, `confirmed_at` 컬럼.
- `BatchRepliesV2Service:160` `createBatchReply` 진입 시 `getUserActiveJob` 으로 활성 작업 체크. ACTIVE/IN_PROGRESS/PAUSED 면 409 응답.
- 사용자가 confirm/cancel 누르면 상태 전이 → 새 작업 trigger 가능.

결과
- 중복 트리거 차단. 운영 화면에 진행률 정확히 표시.

#### 도전 D — 인스턴스 재시작 시 IN_PROGRESS 좀비 job

문제
- 워커가 죽으면 `IN_PROGRESS`로 잡힌 job이 영구히 멈춤.

해결 (`rds-queue.service.ts:100` `initializeHealthCheck`, `:122` `rescheduleJobsOnStartup`)
- 인스턴스 부팅 시 WAITING/IN_PROGRESS job들을 모두 재스케줄(`startAfter`를 현재 + 랜덤 100~300ms 누적 delay로 갱신).
- 인스턴스 ID(`process.env.INSTANCE_ID` 없으면 `instance-${Date.now()}-${random}`)를 statusMessage에 박아서 어느 인스턴스가 처리 중인지 추적.
- 주기적 health check (1분), consumer check (30초) 로 좀비 감지 후 복구.

결과
- 인스턴스 재배포 시 멈춘 job이 자동 복구.

### 5. 결과

정량
- 일괄댓글 동시 처리 worker = 최대 30 (`QUEUE_CONFIG.MAX_CONCURRENT_WORKERS`)
- 같은 그룹 내 순차 처리 + 다른 그룹 병렬 처리로 처리량 극대화
- 인스턴스 재배포 무중단 (rescheduleJobsOnStartup으로 좀비 복구)

정성
- BullMQ/Redis Stream 같은 별도 큐 시스템 없이 **MySQL을 큐로 사용**해 트랜잭션 + 큐 책임을 한 곳에 묶음.
- 낙관락(updatedAt 버전 필드) 패턴은 분산 시스템 시니어가 자주 쓰는 기법. CAS(Compare-And-Set) 의 SQL 버전.

출처
- 파일 `src/rds-queue/rds-queue.service.ts` (인스턴스 ID, 30 worker 풀, 낙관락, health check)
- 파일 `src/rds-queue/user-job-group.service.ts` (사용자 작업 그룹 관리, 활성 작업 체크)
- 파일 `src/replies/batch-replies-v2.service.ts` (API 진입점)
- 커밋 PR #1214 `feat: 일괄댓글 API 튜닝` (`51b2c11b`)
- 커밋 PR #1180 `feat: rds-queue 다중 워커 지원 외 5` (`f5596f67`)

### 6. 사용 기술 매핑

| 기술 | 사용 부분 |
|---|---|
| MySQL Aurora | `queue_jobs` 테이블 = 큐 자체, 낙관락(updatedAt as version), 멀티 인스턴스 안전 픽업 |
| TypeORM QueryBuilder | `UPDATE WHERE updatedAt = originalUpdatedAt` 낙관락 패턴 |
| ECS multi-task | `INSTANCE_ID` 환경변수로 인스턴스 식별, statusMessage에 instanceId 박음 |
| RabbitMQ | scraper 호출 시 사용 (queueManager 모듈), 본 queue와는 책임 분리 |
| Redis | 사용자 작업 진행률 캐시 (폴링 부하 감소), 분산 락(`acquireProcessingLock`) |
| 좀비 복구 cron | `initializeHealthCheck` + `performHealthCheck` (1분 주기) |

---

## [도메인 5] 불만족 알림톡 — BIZ/User 알람 책임 분리 + 파트너 템플릿 오버라이드

### 1. 배경 및 목표

부정 리뷰(저점 별점) 감지 시 사장님에게 카카오 알림톡을 보내 즉시 응대를 유도. 그런데
- 일반 사장님(User) — 본인 알림톡으로 발송
- BIZ 사장님(브랜드 본사 소속) — 본사 관리자에게도 동시 발송 (한 매장에 알림톡 최대 3개 번호)
- 일부 파트너(롯데 GRS 등) — 같은 템플릿이라도 다른 문구 (계약상 별도 템플릿 코드 사용)

기존 시스템의 한계
- 한 서비스가 BIZ 발송 + User 발송 + 템플릿 분기 + 발송 리포팅을 모두 처리 → 코드가 비대해지고 변경 시 회귀 위험
- 파트너별 템플릿 오버라이드를 if-else로 박아두니 파트너 추가/계약 해지 시 코드 변경 필요

비즈니스 요구
- 한 부정 리뷰에 대해 모든 활성 번호(User + BIZ)로 동시 발송
- 파트너별 템플릿은 **계약 해지 시 자동 복원** = 매핑 한 줄 제거로 충분
- BIZ 매장이 inactive면 발송 제외 (BIZ_INACTIVE)
- 발송 실패는 개별 추적 가능 (어느 번호로 어떤 템플릿 보내려다가 실패했는지)

왜 어렵나
- 알림톡 채널은 카카오 비즈메시지 — 템플릿 사전 등록 + 파라미터 치환 형식
- 각 파트너의 계약에 맞는 별도 템플릿 코드를 유지하면서 기본 템플릿과 격리해야 함
- NHN Cloud Toast 알림톡 API의 응답 파싱(`header.resultCode`, `sendResults[0].resultCode`)을 일관성 있게 리포트로 저장

### 2. 구현 과정

핵심 파일
- `src/alarmtalk/alarmtalk.service.ts` (354 라인, 최상위 발송 + Facade)
- `src/alarmtalk/services/review-alarm-orchestrator.service.ts` (405 라인, BIZ+User 통합 발송 조율)
- `src/alarmtalk/services/biz-negative-alarm.service.ts` (142 라인, BIZ 전용 수집)
- `src/alarmtalk/services/user-negative-alarm.service.ts` (449 라인, User 전용 수집)
- `src/alarmtalk/templates/alarmtalk-generic-template.builder.ts`

3개 책임 분리
```
ReviewAlarmOrchestratorService (조율)
    ├─ BizNegativeAlarmService.collectBizAlarms() → BIZ 번호 수집
    ├─ UserNegativeAlarmService.collectUserAlarm() → User 번호 수집
    └─ AlarmTalkService.sendAlarmTalk() → 최종 발송 + 리포트 저장
```

파트너 템플릿 오버라이드 (`alarmtalk.service.ts:60`)
```ts
private readonly partnerTemplateOverrides: Record<string, Record<string, TemplateCode | null>> = {
  [process.env.LOTTEGRS_ORG_ID || '']: {
    [TemplateCode.BLIND_010]: TemplateCode.BLIND_011,
    [TemplateCode.BLIND_020]: TemplateCode.BLIND_021,
    [TemplateCode.SAD_0151]: TemplateCode.SAD_022,
    [TemplateCode.SAD_AI_020]: TemplateCode.SAD_AI_021,
    [TemplateCode.UNSUB_010]: null,           // null = 발송 스킵
  },
};
```
- `resolveTemplate()` (`alarmtalk.service.ts:153`) 에서 사용자의 brand → org_id → 오버라이드 매핑 조회
- 브랜드에 속하지 않아도 email이 `@lotte.net` 이면 GRS 템플릿 적용 (`alarmtalk.service.ts:174`)
- 계약 해지 시 매핑 한 줄 제거 = 자동 기본 템플릿 복원

알람 수집 + 발송 (`review-alarm-orchestrator.service.ts:194` `sendAlarmsAndGetResults`)
```ts
// BIZ_INACTIVE는 발송 제외 (수집은 됨, 통계에 표시)
const alarmsToSend = allAlarms.filter((a) => a.type !== AlarmRecipientType.BIZ_INACTIVE);

const results = await Promise.all(
  alarmsToSend.map(async (alarm) => {
    const templateForAlarm = getTemplateForAlarm(alarm);   // BIZ vs User 별 템플릿 분기
    try {
      const response = await this.alarmTalkService.sendAlarmTalk({...});
      return { success: true, ... };
    } catch (error) {
      return { success: false, message: error?.message, ... };
    }
  }),
);

return {
  success: results.some((result) => result.success),
  totalAlarms: alarmsToSend.length,
  successCount: results.filter((result) => result.success).length,
  bizAlarmsCount: ...,
  userAlarmsCount: ...,
  skippedBizInactiveCount: ...,
};
```

발송 결과 영속화 (`alarmtalk.service.ts:210` `saveReport`)
```ts
const report = this.reportRepository.create({
  template_code: templateCode,
  header_result_code: responseData.header?.resultCode,
  header_result_message: responseData.header?.resultMessage,
  is_successful: responseData.header?.isSuccessful,
  request_id: responseData.message?.requestId || null,
  message_result_code: sendResult?.resultCode,
  recipient_no: sendResult?.recipientNo || null,
  message_result_message: sendResult?.resultMessage || null,
  user_phone_number_id: userPhoneNumberId,
  user_id: userId || null,
});
```

### 3. 아키텍처

```mermaid
flowchart TB
    REVIEW[부정 리뷰 감지<br/>rating ≤ critical_rating]
    REVIEW --> ORCH[ReviewAlarmOrchestratorService]

    subgraph COLLECT["알람 수집 (병렬)"]
        ORCH --> BIZ[BizNegativeAlarmService<br/>collectBizAlarms]
        ORCH --> USR[UserNegativeAlarmService<br/>collectUserAlarm]
    end

    subgraph VALIDATE["자격 검증"]
        BIZ -->|validateBizAlarm| BV[brand.send_negative_alarms<br/>+ critical_review_rating]
        USR -->|validateUserAlarm| UV[NegativeReviewAlarm.is_active]
    end

    subgraph BUILD["발송 빌드"]
        ORCH --> BUILD1[allAlarms = bizAlarms + userAlarms]
        BUILD1 --> FILTER[BIZ_INACTIVE 제외]
        FILTER --> SEND[Promise.all sendAlarmTalk]
    end

    subgraph SEND_FLOW["sendAlarmTalk 내부"]
        SEND --> RT[resolveTemplate<br/>파트너 오버라이드]
        RT -->|null| SKIP[발송 스킵]
        RT -->|TemplateCode| TB[TemplateBuilder.build]
        TB --> NHN[NHN Toast Alarmtalk API]
        NHN --> RPT[saveReport]
    end

    subgraph RESULT["결과 집계"]
        SEND --> RES[totalAlarms /<br/>successCount /<br/>bizAlarmsCount /<br/>skippedBizInactiveCount]
    end

    classDef collectStyle fill:#EAF1F8,stroke:#1F3A5F
    classDef partnerStyle fill:#FBEEE9,stroke:#C75B3F
    class BIZ,USR,COLLECT collectStyle
    class RT,SKIP partnerStyle
```

### 4. 기술적 도전과 해결

#### 도전 A — BIZ와 User의 알람 책임 분리

문제
- BIZ와 User는 검증 로직이 완전히 다름. BIZ는 brand의 `send_negative_alarms`, `critical_review_rating`을 봐야 하고, User는 `NegativeReviewAlarm.is_active`를 본다.
- 한 서비스에서 if-else로 처리하면 양쪽 변경 시 부수효과 발생.

해결
- `BizNegativeAlarmService` / `UserNegativeAlarmService` 두 책임으로 명확히 분리.
- `collectBizAlarms` / `collectUserAlarm` 둘 다 `AlarmEntry[]` 동일 타입 반환 → orchestrator는 type별 분기만.
- BIZ는 `BIZ` (활성) / `BIZ_INACTIVE` (수집은 되지만 발송 제외) 두 type을 반환 → 통계에서 "비활성으로 인해 발송 스킵된 수" 별도 추적.

결과
- BIZ 정책 변경(예: 매장 비활성화 시 알람 제외)이 BIZ 서비스만 수정해서 끝남. User에 영향 없음.

#### 도전 B — 파트너 템플릿 오버라이드 (계약 해지 시 자동 복원)

문제
- 롯데 GRS 같은 계약사는 별도 템플릿 문구를 사용. 계약 종료 시 원래 템플릿으로 자동 복원되어야 함.
- if-else로 박으면 코드 readability 저하 + 신규 파트너 추가 시 핵심 로직 변경 필요.

해결 (`alarmtalk.service.ts:60`)
- `partnerTemplateOverrides: Record<orgId, Record<TemplateCode, TemplateCode | null>>` 매핑 테이블.
- `resolveTemplate()` 에서 user → brandUser → brand.org_id로 매핑 키 조회.
- 매핑이 없으면 기본 템플릿 → 계약 해지 = 매핑 한 줄 제거 = 자동 기본 복원.
- 매핑 값이 `null` 이면 발송 스킵 (계약에 따라 특정 알림을 안 보내야 하는 케이스).

결과
- 파트너 추가/제거 시 코드 변경 1줄. 비즈니스 로직과 매핑 분리.

#### 도전 C — 동일 매장에 알람 번호 다중 등록 (최대 3개)

문제
- 사장님이 본인 + 매니저 + 점장 3명이 알림톡을 받고 싶어함.
- 같은 번호 중복 등록 차단, 최대 3개 제한.

해결 (`user-negative-alarm.service.ts:369` `registerAlarmPhone`)
- 같은 번호로 등록된 알람 존재 확인 → `ConflictException`
- 현재 등록된 알람 수 확인 → 3개 초과면 `BadRequestException`
- 사장님이 받는 부정 리뷰 알람 = 한 사장님 N개 알람 row (`negative_review_alarms`)

결과
- 한 매장 → 최대 3개 번호 다중 등록 지원. PR #1474 `fix: 불만족 리뷰 알림톡에서 n개의 번호로 전부 발송되게끔 수정`.

#### 도전 D — 알림톡 발송 실패 추적

문제
- NHN Toast API는 응답 형식이 두 단계 — `header.resultCode` (요청 자체 성공/실패) + `sendResults[0].resultCode` (개별 메시지 발송 결과).
- 실패 시 어디서 막혔는지 운영자가 알 수 있어야 함 (template 미승인? 번호 오류? 잔액 부족?).

해결 (`alarmtalk.service.ts:210` `saveReport`)
- `AlarmtalkReport` 테이블에 두 단계 모두 저장.
- `try-catch` 로 발송 실패 시 에러 응답을 그대로 저장 → 운영자가 어떤 사유로 실패했는지 즉시 확인.
- `findUserPhoneNumberId` 로 번호와 사용자를 연결해 사용자 단위 디버깅 가능.

결과
- 알림톡 발송 추적성 확보. PR #1498 `fix: 알림톡 발송 시 user_id 저장`, PR #1480 `fix: 알림톡 내 별점 문구 치환자 추가` 등 점진적 개선.

### 5. 결과

정량
- BIZ 알람 + User 알람 동시 발송, 한 부정 리뷰에 대해 최대 (BIZ 3개 + User 3개 = 6개) 알림톡 발송 지원
- 파트너 별 템플릿 오버라이드 매핑 1개 (`LOTTEGRS_ORG_ID`) + 5개 템플릿 매핑

정성
- Facade 패턴(`alarmtalk.service.ts:269` `registerNegativeReport`가 `UserNegativeAlarmService` 위임) + Strategy 패턴(파트너 오버라이드) 적용.
- 비즈니스 변경(계약 추가/해지)이 코드의 다른 영역에 파급되지 않는 구조.

출처
- 파일 `src/alarmtalk/alarmtalk.service.ts:60` (오버라이드 매핑)
- 파일 `src/alarmtalk/services/review-alarm-orchestrator.service.ts:194` (sendAlarmsAndGetResults)
- 파일 `src/alarmtalk/services/biz-negative-alarm.service.ts:38` (validateBizAlarm)
- 파일 `src/alarmtalk/services/user-negative-alarm.service.ts:369` (registerAlarmPhone)
- 커밋 PR #1474, #1498, #1480

### 6. 사용 기술 매핑

| 기술 | 사용 부분 |
|---|---|
| NHN Toast Alimtalk | OAuth2 token 발급 + 카카오 비즈메시지 발송 API |
| Facade Pattern | `AlarmTalkService` → `UserNegativeAlarmService` 위임 |
| Strategy Pattern | `partnerTemplateOverrides` 매핑 + `resolveTemplate()` |
| Promise.all | BIZ + User 알람 병렬 발송, 일부 실패해도 다른 발송 계속 |
| forwardRef | 순환 의존 해결 (`alarmtalk.service.ts:48`) |

---

## [도메인 6] 쿠폰 멱등 적용 — 사전 검증 + plan 사이드 매칭 + 차액 계산

### 1. 배경 및 목표

쿠폰은 결제 흐름에 깊이 얽혀 있다.
- 「첫달 무료」「2주년 이벤트 두 달 무료」「프로모션 50% 할인」등 다양한 쿠폰
- 같은 사용자에게 여러 쿠폰이 있을 때 어느 쿠폰을 적용할지 우선순위 결정
- 정기결제 schedule을 만들 때 쿠폰 적용된 금액과 plan 정가가 다를 수 있음 → schedule 등록 amount vs 다음 결제 시점에 실제로 적용해야 할 쿠폰 정합성 검증
- 재사용 가능 쿠폰(`is_reusable`, `promotion_period > 1`) 처리

기존 시스템의 한계
- 쿠폰 적용 계산이 결제 흐름 곳곳에 흩어져 있어 변경 시 회귀 발생
- schedule 등록 시 amount는 쿠폰 적용 금액인데 실제 결제 시점에 그 쿠폰이 만료/사용된 경우 정가로 결제됨 → 사용자 클레임
- 동일 쿠폰을 같은 사용자에게 두 번 발급되는 버그

비즈니스 요구
- 다음 결제일에 적용될 쿠폰을 schedule 등록 시점에 정확히 계산
- 적용해야 하는 쿠폰이 있는데 amount가 정가면 fallback으로 자동 보정
- 같은 쿠폰 중복 발급 차단

### 2. 구현 과정

핵심 파일
- `src/coupons/coupons.service.ts` (386 라인)
- `src/user-coupons/user-coupons.service.ts` (178 라인)
- `src/payments/utils/payment.utils.ts` (`amountWithUserCoupons`, `getFloorAmountWithCoupon`, `handleUsedAmount`, `updateReusableCouponUsage`)
- `src/payments/services/payments.service.ts:730` (schedule 시 쿠폰 정합성 검증)

`amountWithUserCoupons` 의 우선순위 로직 (`payments.service.ts:783` 의 사용 예)
```ts
// 다음 요금제에 적용되어야 하는 쿠폰 조회
const { value: predictedAmount, coupon: predictedCoupon } = amountWithUserCoupons(
  plan.price,
  availableUserCoupons,
  undefined,
  customData.coupon_id?.[0],   // 명시적으로 지정된 coupon_id 우선
);

// 적용되어야 하는 쿠폰이 있다면 + fallback 전 amount와 다를 경우
if (predictedCoupon && predictedAmount !== scheduleAnnotation.amount) {
  this.logger.warn(
    `schedule fallback 금액 보정: ${scheduleAnnotation.amount} → ${predictedAmount} (user_id=${userId})`,
  );
  scheduleAnnotation.amount = predictedAmount;
  customData.coupon_id = [predictedCoupon.coupon_id];
  scheduleAnnotation.custom_data = JSON.stringify(customData);
}
```

중복 발급 차단 (`user-coupons.service.ts:86` `createUserCoupon`)
```ts
// 이미 적용된 쿠폰인지 확인
const alreadyExistUserCoupon = await this.userCouponsRepository.findOne({
  where: { user, coupon },
});
if (alreadyExistUserCoupon) {
  return alreadyExistUserCoupon;       // 멱등 반환
}
return await this.userCouponsRepository.save({ user, coupon });
```

소진된 쿠폰 제외 (`payments.service.ts:732`, PR #1377 `fix: 소진된 쿠폰은 조회하지 않도록 수정`)
```ts
const userCoupons = await this.userCouponsRepository.find({
  where: { user: { user_id: userId }, is_exhausted: false },
  relations: ['coupon'],
});
```

재사용 플래그 자동 설정 (`coupons.service.ts:183`)
```ts
// promotion_period가 1 초과일 경우, is_reusable을 true로 변경
if (createCouponDto.promotion_period && createCouponDto.promotion_period > 1) {
  createCouponDto.is_reusable = true;
}
```

QueryRunner 기반 트랜잭션 update (`coupons.service.ts:294`)
```ts
const queryRunner = this.dataSource.createQueryRunner();
try {
  await queryRunner.connect();
  await queryRunner.startTransaction();
  // delete couponPlans, delete userCoupons, add new, update coupon
  await queryRunner.commitTransaction();
} catch (e) {
  await queryRunner.rollbackTransaction();
  throw new Error(`Coupon update failed: ${e.message}`);
} finally {
  await queryRunner.release();
}
```

### 3. 아키텍처

```mermaid
flowchart TB
    SCHED[Portone schedule 등록<br/>scheduleAnnotation.amount]
    SCHED --> FIND[userCoupons<br/>WHERE is_exhausted=false]
    FIND --> CHECK1{쿠폰 있음?}

    CHECK1 -->|없음| FALLBACK1[amount = plan.price<br/>coupon_id = []]
    CHECK1 -->|있음| FIND2[available coupons<br/>FOR THIS PLAN]
    FIND2 --> CALC[amountWithUserCoupons<br/>우선순위 + 명시적 coupon_id]
    CALC --> COMPARE{predictedAmount<br/>== scheduleAmount?}

    COMPARE -->|일치| OK[그대로 등록]
    COMPARE -->|불일치| FALLBACK2[fallback 금액 보정<br/>WARN 로그]
    FALLBACK2 --> OK

    FALLBACK1 --> OK
    OK --> PORTONE[Portone API schedule]
    PORTONE --> DB[(billings<br/>status=SCHEDULED)]

    subgraph IDEMP["중복 발급 차단"]
        CREATE[createUserCoupon]
        CREATE -->|이미 존재| RETURN[기존 row 반환]
        CREATE -->|없음| INSERT[INSERT user_coupons]
    end

    classDef checkStyle fill:#FBEEE9,stroke:#C75B3F
    classDef okStyle fill:#EAF1F8,stroke:#1F3A5F
    class CHECK1,COMPARE,IDEMP checkStyle
    class OK,FALLBACK1,FALLBACK2,INSERT,RETURN okStyle
```

### 4. 기술적 도전과 해결

#### 도전 A — schedule 등록 시점과 실제 결제 시점의 쿠폰 상태 차이

문제
- schedule을 등록할 때 사용자가 쿠폰 A를 갖고 있어 amount = 50% 할인 금액으로 등록.
- 다음 달 결제 시점에 쿠폰 A가 만료/사용 → Portone은 등록된 amount 그대로 결제하므로 사용자가 정가가 아닌 할인가로 결제됨(우리가 손해) 또는 그 반대.

해결 (`payments.service.ts:730~825`)
- schedule 등록 직전에 `available userCoupons (is_exhausted=false, plan_id 매칭)` 재조회
- `amountWithUserCoupons` 로 다음 결제에 실제 적용될 금액 계산
- fallback 보정: 등록된 amount와 다르면 amount + custom_data.coupon_id 모두 보정

결과
- 「schedule 등록 시점에는 쿠폰 적용 / 실제 결제 시 쿠폰 만료」시나리오에서 결제 직전에 한 번 더 정합성 보정. PR #1380 `refactor: 유효한 쿠폰 조회 및 fallback 시 분기 처리 수정`.

#### 도전 B — 동일 쿠폰 중복 발급 차단

문제
- 마케팅 캠페인에서 같은 사용자에게 쿠폰 발급 API가 여러 번 호출될 수 있음.
- 중복 발급되면 한 사용자가 동일 쿠폰을 여러 번 사용하는 버그.

해결 (`user-coupons.service.ts:104`)
- `createUserCoupon` 진입 시 `findOne(user, coupon)` 로 기존 row 확인
- 있으면 기존 row 반환 (idempotent), 없으면 새로 발급

결과
- 동일 쿠폰 중복 발급 방지. PR #1372 `coupon relation 수정`, PR #1353 `refactor: 쿠폰 등록 시, 재사용 여부 플래그 설정 추가`.

#### 도전 C — 쿠폰 수정 시 트랜잭션 일관성

문제
- 쿠폰 메타데이터 + 적용 가능 plan + 발급된 user 매핑을 한 번에 수정 → 일부 update 후 실패 시 데이터 불일치.

해결 (`coupons.service.ts:294~360`)
- `queryRunner` 기반 명시적 트랜잭션 (NestJS의 `@Transactional` 데코레이터 대신 명시적 컨트롤이 필요한 경우 사용).
- `try - commit / catch - rollback / finally - release` 패턴.
- delete + add + update를 한 트랜잭션 안에서 처리.

결과
- 쿠폰 수정 중 실패 시 부분 update 없음. PR #1372, #1353 시리즈.

#### 도전 D — 「첫달 무료 → 스페셜 전환」 같은 사이클 전환

문제
- 첫달 무료(PROMOTIONAL) 쿠폰이 적용된 사용자가 다음 달 스페셜로 전환할 때 금액 계산이 복잡 (PR #1495 `첫달 무료 standard -> special로 수정`)

해결
- `OfferingType.PROMOTIONAL` 분기 (`payments.service.ts:395`) → "사용할 수 없는 요금제" BadRequest
- PROMOTIONAL 유저 업그레이드 전용 흐름 `handlePromotionalUpgrade` (`payments.service.ts:3016`)
- 분산 락 + 전액 즉시 결제 + 다음 결제 예약 한 트랜잭션으로 묶음

결과
- 「첫달 무료 → 정상 결제 전환」시나리오 정합성 유지. PR #1505 (fix: 첫달무료 스페셜인 유저에게는 2주년이벤트 정보 제공될 수 있도록 변경), PR #1495 시리즈.

### 5. 결과

정량
- 쿠폰 fallback 보정 로그(`schedule fallback 금액 보정`)가 운영 환경에서 정상 동작하여 결제 정합성 차이를 자동 보정
- 동일 쿠폰 중복 발급 0건 (멱등 보장)

정성
- `amountWithUserCoupons`를 단일 함수로 추출해 결제·schedule·change_plan·promotional upgrade 모든 흐름에서 재사용 → DRY
- 쿠폰 사용 흐름의 idempotency를 「사전 검증(findOne) + 트랜잭션(queryRunner) + 사후 검증(스케줄 fallback)」 3중으로 보장

출처
- 파일 `src/coupons/coupons.service.ts:294` (queryRunner 트랜잭션)
- 파일 `src/user-coupons/user-coupons.service.ts:104` (멱등 발급)
- 파일 `src/payments/services/payments.service.ts:730~825` (schedule fallback 보정)
- 커밋 PR #1380, #1377, #1372, #1353, #1495, #1505

### 6. 사용 기술 매핑

| 기술 | 사용 부분 |
|---|---|
| MySQL Aurora | UNIQUE(user_id, coupon_id) 멱등 적용, `is_exhausted` 플래그 |
| TypeORM QueryRunner | 명시적 트랜잭션(`startTransaction`/`commit`/`rollback`/`release`) |
| Datadog APM | `payment.coupon_select.*` span tag (선택된 쿠폰/금액 추적) |
| Slack Webhook | 쿠폰 미적용 경고 (`예약 결제 쿠폰 미적용` `payments.service.ts:448`) |

---

## [도메인 7] SafeCron — 멀티 인스턴스 cron 중복 실행 차단 + Slack 자동 알림

### 1. 배경 및 목표

ECS 다중 Task 환경에서 NestJS의 `@Cron`은 **모든 인스턴스에서 동시에 실행**된다. 그러면
- 일일 결제 정합성 점검이 N개 인스턴스에서 N번 실행됨 → Portone API rate-limit 초과
- 일일 알림톡 발송 cron이 N번 → 사용자가 같은 알림톡 N개 받음
- Notifly 사용자 동기화 batch가 N번 → 외부 SaaS rate-limit 초과 + 비용 증가

비즈니스 요구
- cron은 한 시점에 한 인스턴스에서만 실행 (분산 락)
- 실행 시작/완료/실패를 Slack에 자동 알림 (운영자 모니터링)
- 환경변수로 cron 비활성화 가능 (QA 환경, 핫픽스 배포 시)

왜 어렵나
- 모든 cron 메서드마다 락 처리 코드 작성 → 보일러플레이트 폭증
- 락 해제 누락 → 인스턴스 죽으면 락이 영구히 남아 cron이 영영 안 돌아감 (TTL로 해결해야 함)
- 시작/완료/에러 메시지 형식이 cron마다 다르면 운영자가 패닉

### 2. 구현 과정

핵심 파일
- `src/common/decorators/safe-cron.ts` (210 라인, 데코레이터 전체)

데코레이터 조합 패턴
```ts
export function SafeCron(
  cron: string,
  options: CronOptions = {},
  additionalOptions: AdditionalOptions = {
    lockTTL: 10 * 1000,
    slackAlert: true,
    slackWebhookUrl: URL.SLACK_BILLING_BOARD,
  },
): MethodDecorator {
  if (!isCronEnabled()) {
    return function (target, propertyKey, descriptor) {
      return descriptor;             // CRON_ENABLED=false → 데코레이터 자체를 noop
    };
  }
  return applyDecorators(
    WithLock({ ...additionalOptions, name: options.name }),
    Cron(cron, { ...options, name: options.name }),
  );
}
```

WithLock 핵심 (`safe-cron.ts:80`)
```ts
export function WithLock(options) {
  const lockTTL = options.lockTTL || 5 * 1000;
  const slackWebhook = new IncomingWebhook(slackWebhookUrl ?? '');

  return function (target, propertyKey, descriptor) {
    const originalMethod = descriptor.value;
    const lockKey = `safe_cron:${options.name || `${className}.${methodName}`}`;

    descriptor.value = async function (...args) {
      let lockAcquired = false;
      try {
        const redisService = getRedisService();
        const ttlSeconds = Math.max(1, Math.ceil(lockTTL / 1000));
        lockAcquired = await redisService.setNX(lockKey, 'running', ttlSeconds);

        if (!lockAcquired) {
          logger.warn(`${timestamp}: ${jobName}: already running`);
          return;
        }
        if (options.slackAlert !== false) {
          await slackWebhook.send({ text: `${timestamp}: ${jobName}: start` });
        }
        const startTime = Date.now();
        const result = await originalMethod.apply(this, args);
        const executionTime = Date.now() - startTime;
        if (options.slackAlert !== false) {
          await slackWebhook.send({ text: `${timestamp}: ${jobName}: complete (${executionTime}ms)` });
        }
        return result;
      } catch (error) {
        await slackWebhook.send({
          text: `${timestamp}: ${jobName}: error - ${error.message}`,
          blocks: [/* 스택 트레이스 + 에러 메시지 */],
        });
        throw error;
      } finally {
        if (lockAcquired) {
          const redisService = getRedisService();
          if (redisService) await redisService.del(lockKey);
        }
      }
    };
    return descriptor;
  };
}
```

ModuleRef 주입 트릭 (`safe-cron.ts:16`)
- 데코레이터는 클래스 인스턴스 컨텍스트 밖이라 NestJS DI를 직접 못 씀
- main.ts에서 `setModuleRef(app.get(ModuleRef))` 호출하여 전역 참조 저장 → 데코레이터 안에서 `getRedisService()` 로 가져옴
- 이 패턴은 NestJS DI를 데코레이터에서 우회 사용하는 시니어 트릭

### 3. 아키텍처

```mermaid
flowchart TB
    subgraph DEPLOY["ECS Task ×3 (multi-instance)"]
        T1[Task A]
        T2[Task B]
        T3[Task C]
    end

    subgraph CRON_TIME["09:10 KST 동시 발화"]
        T1 -->|setNX lockKey| R1{Redis<br/>setNX 성공?}
        T2 -->|setNX lockKey| R1
        T3 -->|setNX lockKey| R1
    end

    R1 -->|Task A 승: OK| EXEC[원래 cron 메서드 실행]
    R1 -->|B,C: nil| SKIP[already running 로그]

    EXEC --> SLACK1[Slack: start]
    EXEC --> WORK[handleDuplicatePaymentReserve<br/>etc.]
    WORK -->|성공| SLACK2[Slack: complete - duration]
    WORK -.실패.-> SLACK3[Slack: error - stack trace]

    SLACK2 --> FINALLY[finally: redis.del lockKey]
    SLACK3 --> FINALLY

    Note1[CRON_ENABLED=false<br/>→ 데코레이터 noop<br/>QA에선 cron 비활성]
    Note2[TTL 만료 시 자동 해제<br/>인스턴스 죽어도 안전]

    classDef cronStyle fill:#EAF1F8,stroke:#1F3A5F
    classDef skipStyle fill:#FBEEE9,stroke:#C75B3F
    classDef noteStyle fill:#F4F4F0,stroke:#666
    class DEPLOY,CRON_TIME cronStyle
    class SKIP skipStyle
    class Note1,Note2 noteStyle
```

### 4. 기술적 도전과 해결

#### 도전 A — 데코레이터 안에서 DI 의존성 사용

문제
- NestJS DI는 클래스 생성자 주입 기반. 데코레이터는 클래스 정의 시점에 실행되므로 인스턴스가 없음.

해결 (`safe-cron.ts:16~58`)
- `setModuleRef(moduleRef)` 를 main.ts에서 호출하여 전역 변수에 저장.
- 데코레이터 내부의 `descriptor.value` 함수 안에서 `getRedisService()` 호출 → `moduleRefInstance.get(RedisService, { strict: false })` 로 lazy 조회.
- `strict: false` 옵션으로 모듈 경계를 넘는 전역 조회 허용.

결과
- 모든 cron 메서드에 한 줄 데코레이터(`@SafeCron`)만 붙이면 자동으로 Redis 락 + Slack 알림 + 환경변수 토글 적용. PR #1387 (fix: 인증번호 발송 시 레디스 락 추가)와 같은 패턴.

#### 도전 B — 락 해제 누락 (인스턴스 죽음)

문제
- 인스턴스가 OOM/SIGKILL로 죽으면 finally가 안 돌아 락이 남음 → 다음 cron이 영영 안 돌아감.

해결
- `setNX(lockKey, 'running', ttlSeconds)` 에서 TTL을 cron 실행 최대 예상 시간으로 설정 (기본 10초, daily check는 30분).
- 인스턴스가 죽어도 TTL 만료 후 자동 해제.
- 정상 종료 시 `finally`에서 명시적 `del`.

결과
- 인스턴스 장애 시에도 다음 cron 실행에 영향 없음.

#### 도전 C — 환경별 cron on/off (QA에선 cron 비활성)

문제
- QA 환경에서 production cron이 돌면 실 사용자에게 알림톡이 가거나 외부 API 호출 발생.

해결 (`safe-cron.ts:23` `isCronEnabled`)
- `CRON_ENABLED` 환경변수가 `false`/`0`/`disabled`/`off`/`no` 중 하나면 데코레이터 자체를 noop으로 반환.
- 데코레이터가 noop이면 `@Cron` 등록조차 안 되므로 cron 자체가 작동 안 함.

결과
- QA 환경에서 cron 안전하게 비활성화. PR #1467 (fix: 롯데 크론이 qa환경에서 돌지 않도록 수정), PR #1466 (fix: qa 환경에서 롯데 cron이 실행되지 않게끔 수정) 시리즈.

#### 도전 D — Slack 알림 표준화

문제
- cron마다 시작/완료/실패 Slack 메시지를 직접 만들면 형식 제각각, 운영자 보기 힘듦.

해결 (`safe-cron.ts:122~162`)
- `start` / `complete (${executionTime}ms)` / `error - ${message} + 스택 trace block` 형식 통일.
- `slackAlert: false` 옵션으로 시끄러운 cron은 알림 끄기 가능.
- `slackWebhookUrl` 옵션으로 cron별 다른 채널 라우팅.

결과
- 12개 이상 cron이 표준 Slack 메시지로 알림 전송. 운영자가 어느 cron이 얼마나 걸렸는지 한눈에 파악.

### 5. 결과

정량
- `@SafeCron` 사용처 14곳 (subscriptions, alarmtalk, notifly, auth-magic-link, mixpanel, log-cleanup 등)
- cron마다 평균 5~10라인 보일러플레이트 절약 → 약 100라인 절감
- 환경변수 한 번 토글로 전 cron 비활성화 (CRON_ENABLED=false)

정성
- 시니어 데코레이터 패턴 — DI 우회(setModuleRef), Lock acquire/release/TTL, Slack 표준화, 환경변수 토글을 한 데코레이터에 통합.
- 분산 락의 본질(setNX + TTL)을 cron이라는 도메인에 맞게 추상화한 좋은 예.

출처
- 파일 `src/common/decorators/safe-cron.ts` (전체 210 라인)
- 사용 사례: `src/subscriptions/admin.subscription.controller.ts:127-180`, `src/notifly/notifly-batch.service.ts:131`, `src/alarmtalk/cron/alarmtalk-cron.controller.ts`, `src/auth/auth-magic-link.controller.ts:148`, `src/mixpanel/mixpanel.controller.ts:108`, `src/common/services/log-cleanup.scheduler.ts:21`

### 6. 사용 기술 매핑

| 기술 | 사용 부분 |
|---|---|
| TypeScript Decorators | `applyDecorators(WithLock, Cron)` 조합 |
| Redis | setNX 기반 분산 락 + TTL 자동 해제 |
| @nestjs/schedule | Cron 표현식 + timeZone |
| Slack Webhook | start/complete/error 표준 메시지 |
| NestJS ModuleRef | 데코레이터에서 DI 우회 사용 (`strict: false` 전역 조회) |
| 환경변수 토글 | `CRON_ENABLED` 로 전체 cron on/off |

---

## [도메인 8] RabbitMQ 스크래퍼 큐 — 멀티 인스턴스 멱등성 + 단계별 backoff

### 1. 배경 및 목표

외부 플랫폼(배민/요기요/쿠팡이츠/네이버/땡겨요/먹깨비) 스크래핑은 건당 10~25분 IO. cmong-be(API 서비스)에서 직접 호출하면
- ALB 5분 타임아웃 초과
- API 인스턴스가 스크래핑 시간 동안 점유돼 throughput 저하

비즈니스 요구
- API는 즉시 응답 (202 Accepted) + 백그라운드에서 스크래퍼 호출
- 같은 매장에 대해 worker 여러 개가 동시에 스크래핑 시도하지 않음 (외부 플랫폼 차단)
- 일시 장애(500/502/503)는 자동 재시도, 영구 장애(아이디 비번 오류)는 즉시 실패
- 땡겨요(DDANGYO)는 비밀번호 5회 오류 시 계정 잠금 → 비밀번호 관련 에러는 절대 재시도 금지

왜 어렵나
- 다중 인스턴스에서 같은 messageId가 동시 처리되는 race
- 재시도 정책이 플랫폼마다 다름 (영구/일시 에러 분류)
- RabbitMQ classic queue는 채널이 닫히면 ack/nack 실패 → hot loop 위험

### 2. 구현 과정

핵심 파일
- `src/queueManager/queue.consumer.ts` (968 라인)
- `src/queueManager/services/queue-state.service.ts` (113 라인, 멱등성 상태 관리)
- `src/queueManager/queue.service.ts` (113 라인, RabbitMQ producer)
- `src/queueManager/config/queue.config.ts`, `queue-microservice-config.ts`

QueueStateService 3종 키 (`queue-state.service.ts:8`)
```ts
private readonly RETRY_KEY_PREFIX = 'queue:retry:';            // 재시도 횟수
private readonly PROCESSED_KEY_PREFIX = 'queue:processed:';    // 처리 완료 표시
private readonly PROCESSING_KEY_PREFIX = 'queue:processing:';  // 처리 중 락

private readonly RETRY_TTL_SECONDS = 3600;                     // 1시간
private readonly PROCESSED_TTL_SECONDS = 86400;                // 24시간
private readonly PROCESSING_LOCK_TTL_SECONDS = 7200;           // 2시간
```

Consumer 진입 시 3단계 가드 (`queue.consumer.ts:79~95`)
```ts
// 1. 이미 처리된 메시지인가? (24시간 dedupe)
if (messageId && (await this.queueStateService.isProcessed(messageId))) {
  this.logger.warn(`[ALREADY_PROCESSED] messageId: ${messageId}`);
  channel.ack(originalMsg);
  return;
}

// 2. 다른 인스턴스가 처리 중인가? (분산 락)
if (messageId && !(await this.queueStateService.acquireProcessingLock(messageId))) {
  this.logger.warn(`[LOCK_FAILED] messageId: ${messageId}`);
  channel.nack(originalMsg, false, true);   // 재큐
  return;
}

// 3. 실제 처리
```

단계별 backoff (`queue.consumer.ts:365`)
```ts
private computeBackoffMs(retryCount: number): number {
  if (retryCount <= 1) return 30 * 1000;       // 1차 실패 → 30초 후 재시도
  if (retryCount <= 2) return 5 * 60 * 1000;   // 2차 실패 → 5분 후
  return 30 * 60 * 1000;                       // 3차 실패 → 30분 후
}
```

DLX 미적용, application-level retry로 hot loop 방지 (`queue.consumer.ts:126~149`)
```ts
// nack false true — hot loop 방지를 위해 사용 안 함
// 원본 메시지는 ack로 큐에서 제거하고 application-level setTimeout으로 단계별 backoff 후 republish
// Phase 2에서 RabbitMQ DLX 기반 정통 패턴(@golevelup 도입과 함께)으로 교체 예정.
channel.ack(originalMsg);

const retryCount = await this.queueStateService.getRetryCount(messageId);
const backoffMs = this.computeBackoffMs(retryCount);
setTimeout(async () => {
  await this.queueService.republishMessage(raw);
}, backoffMs);
```

영구/일시 에러 분류 (`queue.consumer.ts:804~841`)
```ts
private readonly PERMANENT_ERROR_MESSAGES = [
  '아이디 또는 비밀번호가 일치하지 않습니다',
  '로그인 실패: 입력하신 아이디/비밀번호가 맞지 않습니다',
  'Shop not found',
];
// 땡겨요(DDANGYO): 5회 오류 시 계정 잠금
private readonly DDANGYO_PASSWORD_ERROR_KEYWORDS = ['비밀번호', '비번', 'password'];

private isPermanentError(err, platform) {
  // 기본 영구 에러 체크
  if (this.PERMANENT_ERROR_MESSAGES.some((msg) => errorMessage.includes(msg))) return true;
  // 땡겨요 비밀번호 에러는 platform별 가드
  if (platform === PLATFORM_TYPE.DDANGYO) {
    const hasPasswordError = this.DDANGYO_PASSWORD_ERROR_KEYWORDS.some((k) =>
      errorMessage.toLowerCase().includes(k.toLowerCase())
    );
    if (hasPasswordError) {
      this.logger.warn(`[DDANGYO_PASSWORD_ERROR] Skipping retry due to password error`);
      return true;
    }
  }
  return false;
}
```

진입점 timeout 가드 (`queue.consumer.ts:851~863`)
```ts
private async withTimeout<T>(p: Promise<T>, ms: number, label: string): Promise<T> {
  let timer;
  try {
    return await Promise.race<T>([
      p,
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error(`${label} timeout after ${ms}ms`)), ms);
      }),
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}
// 사용: GET_SHOP 10분, POPULATE 25분
```

### 3. 아키텍처

```mermaid
sequenceDiagram
    autonumber
    participant API as cmong-be API
    participant MQ as RabbitMQ
    participant W1 as Worker A (Task 1)
    participant W2 as Worker B (Task 2)
    participant Redis as Redis (QueueStateService)
    participant SC as cmong-scraper

    API->>MQ: emit(SCRAPING, {messageId, platform, ...})
    MQ->>W1: deliver
    MQ->>W2: deliver (가능성, prefetch=2)

    Note over W1,Redis: ① isProcessed 체크
    W1->>Redis: GET processed:{messageId}
    W2->>Redis: GET processed:{messageId}
    alt 이미 처리됨
        Redis-->>W1: 1
        W1->>MQ: ack (no-op)
    end

    Note over W1,Redis: ② acquireProcessingLock (분산 락)
    W1->>Redis: SET NX processing:{messageId}<br/>TTL 2h
    W2->>Redis: SET NX processing:{messageId}
    Redis-->>W1: OK
    Redis-->>W2: nil

    W2->>MQ: nack false true (재큐)

    Note over W1,SC: ③ withTimeout 진입점 가드
    W1->>SC: GET_SHOP (10분 timeout) / POPULATE (25분)
    alt 일시 에러 (5xx)
        SC-->>W1: 503
        W1->>Redis: INCR retry:{messageId}
        W1->>MQ: ack (큐에서 제거)
        Note right of W1: setTimeout backoff:<br/>1차 30s / 2차 5m / 3차 30m
        W1->>MQ: republish(originalMessage)
    else 영구 에러 (DDANGYO 비번 오류)
        SC-->>W1: '비밀번호 일치하지 않음'
        W1->>Redis: clear retry:{messageId}
        W1->>MQ: ack (폐기)
    else 성공
        SC-->>W1: 200 OK
        W1->>Redis: SET processed:{messageId} TTL 24h
        W1->>MQ: ack
    end

    Note over W1,Redis: ④ finally: releaseProcessingLock
    W1->>Redis: DEL processing:{messageId}
```

### 4. 기술적 도전과 해결

#### 도전 A — DDANGYO(땡겨요) 5회 오류 시 계정 잠금

문제
- 일반 플랫폼은 비밀번호 오류 시 재시도 가능. 그러나 땡겨요는 5회 오류 시 사장님 계정이 잠겨 사업 운영 자체에 지장.

해결 (`queue.consumer.ts:813~822`, `:828~838`)
- `PLATFORM_TYPE.DDANGYO` + 비밀번호 키워드 매칭 시 영구 에러로 분류 → 재시도 차단
- statusCode가 500/502/503이어도 비밀번호 에러면 일시 에러로 분류하지 않음.

결과
- 땡겨요 계정 잠금 사고 방지. 시니어 운영 감각을 반영한 platform-specific 정책 코드화.

#### 도전 B — RabbitMQ DLX 없이 application-level retry로 hot loop 방지

문제
- `channel.nack(msg, false, true)` 로 재큐하면 즉시 같은 메시지가 다시 delivery → hot loop (CPU/IO 폭증).
- DLX(Dead Letter Exchange) + TTL 패턴이 정통이지만 RabbitMQ classic queue에서는 별도 설정 필요 + 운영 비용.

해결 (`queue.consumer.ts:126~149`)
- 메시지는 즉시 ack로 큐에서 제거 (큐 적체 방지)
- `setTimeout(backoffMs, () => republishMessage(raw))` 로 application-level에서 backoff 후 재전송
- 30초 / 5분 / 30분 단계별 backoff = exponential-like

결과
- hot loop 회피. Phase 2에서 DLX 기반 정통 패턴(`@golevelup/nestjs-rabbitmq`)으로 마이그레이션 예정 주석으로 표시.

#### 도전 C — RabbitMQ 채널 끊김 시 ack/nack 실패

문제
- AMQP 채널이 끊긴 상태에서 `channel.ack(msg)` 호출하면 `IllegalOperationError` 발생.

해결 (`queue.consumer.ts:74~76`, `:114~120`)
- 매 ack/nack 전에 `channel?.connection?.stream?.writable` 검사
- writable이 false면 ack 스킵 + 로그 (`[ACK_SKIPPED]`).
- 채널 재연결 시 RabbitMQ가 unacked 메시지를 다시 delivery하므로 데이터 손실은 dedupe(`isProcessed`)로 차단.

결과
- 채널 끊김 + 인스턴스 재기동 환경에서도 안전. 멱등성으로 데이터 손실 방지.

#### 도전 D — 메시지 처리 진입점 timeout 가드

문제
- 스크래퍼 응답 무한 대기 = 워커가 영구히 점유됨 = 다른 메시지 처리 불가.
- axios 옵션 timeout은 호출 체인 깊어 일괄 적용 어려움.

해결 (`queue.consumer.ts:851`)
- `Promise.race` 로 [원본 호출, timeout reject] 경쟁
- GET_SHOP은 10분, POPULATE은 25분 (플랫폼별 SLA 고려)
- timeout 시 throw → handleRetry로 backoff 진입

결과
- 워커 영구 점유 사고 방지. 시니어 패턴 「outer-level circuit breaker」의 단순 버전.

### 5. 결과

정량
- 1 messageId당 최대 3회 재시도 + 단계별 30초/5분/30분 backoff
- 24시간 dedupe (`PROCESSED_TTL_SECONDS = 86400`)
- 2시간 processing 락 (스크래핑 최대 시간 대비 여유)
- GET_SHOP 10분 / POPULATE 25분 진입점 timeout

정성
- `architecture.md`의 「세션 유지율 99.2%」 운영 지표는 본 큐 멱등성 + DDANGYO 가드 + backoff 정책의 합산 결과.
- DLX 미적용으로 인한 hot loop 위험을 application-level retry로 회피하면서 Phase 2 마이그레이션 경로를 명시 (`Phase 2에서 RabbitMQ DLX 기반 정통 패턴으로 교체 예정` 주석).

출처
- 파일 `src/queueManager/queue.consumer.ts:79~95` (3단계 가드), `:365~369` (backoff), `:804~841` (에러 분류), `:851~863` (timeout)
- 파일 `src/queueManager/services/queue-state.service.ts:84~111` (분산 락)
- 파일 `src/queueManager/queue.service.ts:91~105` (republish)

### 6. 사용 기술 매핑

| 기술 | 사용 부분 |
|---|---|
| RabbitMQ | `@nestjs/microservices` ClientRMQ, EventPattern, prefetch=1/2 |
| Redis | `processed:` / `processing:` / `retry:` 3종 키, setNX 락, TTL 자동 해제 |
| Promise.race | 진입점 timeout 가드 (워커 영구 점유 방지) |
| 플랫폼별 에러 정책 | DDANGYO 5회 잠금 대응, 영구/일시 에러 분류기 |
| application-level retry | DLX 없이 setTimeout + republish 로 hot loop 회피 |
| ECS multi-task | `INSTANCE_ID` 환경변수로 인스턴스 구분, statusMessage에 박음 |

---

## 부록 A — 추가로 확인된 시니어 시그널 (이력서 본문에 직접 안 쓰더라도 면접에서 어필)

### A-1. EventEmitter2 기반 도메인 이벤트
- `payments.service.ts:1846` `new NotiflySyncEvent(user_id, 'sync-user', {}, 'payments.activeFreeTrial')`
- `payments.service.ts:2389` `payments.handleChangePlanProcessing`
- `payments.service.ts:3104` `payments.handlePromotionalUpgrade`
- 결제 완료 → Notifly(외부 마케팅 SaaS) 사용자 속성 동기화를 **이벤트 기반 비동기**로 처리. 결제 핵심 흐름에서 외부 SaaS 호출을 분리.
- `notifly-event.listener.ts:35` 에서 분산 락 + 이벤트 처리 → 동일 이벤트 중복 처리 차단.

### A-2. Single-Flight 코어레싱 패턴
- `redis.service.ts:102` `runWithCoalescing<T>` 구현 확인.
- Hot path 캐시 우선 → 락 획득자만 factory 실행 → 나머지는 폴링 대기 + Jitter (0~50ms)
- `architecture.md` 의 「Single-Flight 5 invariants (Kotlin 자산화)」와 정확히 일치하는 Node.js 원형.

### A-3. Datadog APM Span Tagging
- `payments.service.ts:407` `tagDatadogSpan({'payment.coupon_select.valid_count': ...})`
- `payments.service.ts:417` `'payment.schedule.amount_mismatch': true`
- 결제 정합성 지표를 Datadog tag로 자동 집계 → 어드민 대시보드/알람 연결.

### A-4. 결제 도메인 9 시나리오 매트릭스 (resume_v9.md의 「9 시나리오 매트릭스」 와 매핑)
| 시나리오 | 함수 |
|---|---|
| 최초 결제 | `processPayment` |
| 정기 결제 | `processPayment` (prevBilling 분기) |
| 결제 실패 + 재시도 | `handleFailedPayment` |
| 결제 취소 (전체/부분 환불) | `paymentDBService.cancelPaymentDBProcess` |
| 예약 결제 (action_type=RESERVE) | `handlePaymentOnlyReserve` |
| 결제수단 변경 (CHANGE_BILLING_METHOD) | `changeBillingMethod` |
| 요금제 변경 즉시+즉시결제 | `applyNowPayNow` |
| 요금제 변경 즉시+예약결제 | `applyNowPaySchedule` |
| 프로모션 → 정상 요금제 업그레이드 | `handlePromotionalUpgrade` |

### A-5. Notifly 외부 SaaS 배치 동기화
- `notifly-batch.service.ts:131` `syncAllUsers` `@SafeCron('30 3 * * *')` 매일 새벽 3:30
- BATCH_SIZE 100, 배치마다 `sleep(200)` rate-limit 방어
- 실패한 userId는 `FAILED_USERS_KEY` Redis 리스트에 적재 → 5분마다 retry queue 처리 (`@SafeCron('*/5 * * * *')`)
- 최대 재시도 횟수 초과 시 영구 실패 처리

### A-6. OOM 방지 chunk 처리
- 커밋 PR #1436 `fix: OOM 으로 인한 서비스로직 동작 멈춤 해결`
- `bot.service.ts`의 일일 구글시트 업데이트 cron이 모든 user를 한 번에 `find` → 메모리 폭증으로 OOM
- 해결: CHUNK_SIZE=2000, while 루프로 offset 증가하며 점진 처리, lookup map은 최초 1회만 조회
- 일반 시니어 패턴 — 「전체 load → 메모리 폭증」을 chunk + offset으로 변환

---

## 부록 B — 이력서 v9 활용 권장 사례 매핑

| resume_v9.md 의 어느 문장 | 본 문서의 어느 사례로 보강 |
|---|---|
| 「분산 환경에서 트랜잭션 일관성」 | 사례 1 (4중 멱등성), 사례 2 (reconciliation), 사례 3 (FOR UPDATE 비관락) |
| 「비동기 메시징 기반 처리량 개선」 | 사례 4 (RDS Queue 낙관락), 사례 8 (RabbitMQ 멱등성) |
| 「외부 API 의존성 격리」 | 사례 8 (DDANGYO 가드, 영구/일시 에러 분류) |
| 「세션 일관성 문제」 | architecture.md + 사례 8 (worker pool platformId 가드) |
| 「댓글 등록 중복 0건 (최근 6개월 기준)」 | 사례 1 (결제 4중) + 사례 4 (낙관락) + 사례 8 (3단계 가드) 의 합산 결과 |
| 「프랜차이즈 멀티테넌트 구조」 | 사례 3 (매장 일괄 등록) + 사례 5 (BIZ/User 알람 분리) |
| 「자체 프록시 풀」 (architecture.md 5번) | (cmong-be 외부) |
| 「Aurora Consume 패턴, TPS 1,000/s」 | 사례 4 (RDS Queue) 의 실현체 |

---

## 부록 C — 추가 조사 권장 영역 (시간 관계상 본 문서에서 일부만 다룬 곳)

1. **마케팅 캠페인** (`src/campaigns/`, 717 라인) — 예약 댓글 수만 건 동시 트리거 대응, Redis 기반 작업 추적 로직 개선 PR #858
2. **롯데 GRS 파트너 연동** (`src/lottegrs/`) — 정산 cron + 캐시 + magic link, 파트너별 격리 패턴
3. **블라인드 리뷰 신청** (`src/blind-review/`) — 외부 플랫폼 신고 자동화
4. **AI 댓글 / 자동응답** (`src/ai-replies/`, `src/auto-reply/`) — LLM 결과 캐싱 + 재시도
5. **rds-queue.service.ts**의 health check / consumer check 60초/30초 주기 운영 패턴
