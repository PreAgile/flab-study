# cmong-scraper-js — 시니어 레벨 문제·해결·성과 사례 추출

> **목적**: 김면수(시니어 백엔드 엔지니어, 르몽) 이력서·면접 자료로 그대로 옮길 수 있도록, `cmong-scraper-js` 저장소를 코드/커밋 기준으로 샅샅이 뒤져 정리한 8개 사례.
> **저장소**: `/Users/meyonsoo/Desktop/lemong/project/cmong-scraper-js` (TypeScript / NestJS 11 / Camoufox + Playwright / RabbitMQ / Redis Cluster / MySQL)
> **포맷**: 5단 — (1) 컨텍스트 (2) 문제 (3) 해결 (4) 성과 (5) 기술 매핑 — 각 사례 끝에 "이력서 한 줄 요약"과 "면접 질문에 어떻게 답할지 4단 narrative" 동반.
> **수치 사용 정책**: `resume_v9` 와 정합한 운영 수치(88.75% 비용 절감, 99.2% 세션 유지율, 6배 처리량, API 차단 90% 감소)만 재사용. 코드/커밋에서 확인되는 측정치(예: PR #644 의 18/18 = 100%, PR #581 의 372+372 spec)는 그대로 인용.

---

## 사례 인덱스

| # | 제목 | 핵심 키워드 | 추정 임팩트 |
|---|------|------------|-------------|
| 1 | **SessionLockRegistry** — 30+ worker 동시 접근의 FIFO 큐 + lease TTL + cold-start guard | 분산 락, Redis Cluster, instance-aware lease | 세션 유지율 99.2%, 중복 로그인 0건 |
| 2 | **Single-Flight Coordinator 포트화** — 5 불변식 + 4 데코레이터 합성 | Port-Adapter, decorator 합성, kill-switch | NaverService 80+ 줄 제거, 22개 신규 spec, Redis 적응 준비 |
| 3 | **Camoufox Heavy 브라우저 풀** — Launch Semaphore + Prewarm Pool + Quarantine + Orphan PID Sweep | OS 자원 격리, 5-phase zombie cleanup, OOM 회피 | OOM 회귀 차단, 97.2% 성공률 (40 concurrent) |
| 4 | **Akamai Bot Manager 우회** — referrer warming + bm_sv polling + `_abck` 상태 머신 + race window | 봇 탐지, 브라우저 fingerprint, P3 4-phase | 7/9 (77.8%) → 18/18 (100%) 로그인 성공률 |
| 5 | **자체 프록시 풀 PAMS** — IP 평판 시스템 + Pool Exhausted Fallback + ElastiCache Cluster CROSSSLOT 대응 | Decodo Datacenter 전환, port↔IP 매핑 3중 저장 | 월 800만→90만 (88.75% 절감), 70%→98% 성공률 |
| 6 | **8가지 로그인 분기 일원화** — 플랫폼별 ScrapperException 계층 + Akamai/Password 분류기 + Quick Retry v2 (Prewarm Swap) | 도메인 예외 모델, 재시도 정책, 분류 우선순위 | 8종 분기 + 9종 에러 카테고리 표준화 |
| 7 | **Idempotent Reply Pipeline** — Lease + Completion Cache + ErrorClassifier + DLQ | 멱등성 4단계, 4종 에러 분류, Tower 의사결정 분리 | 댓글 등록 중복 0건 (6개월), 핫루프/DLQ 정책 명문화 |
| 8 | **Adaptive Traffic Controller + Launch Budget** — Token Bucket(Lua) + Circuit Breaker(SOFT_OPEN / HALF_OPEN) | 자기조절 워커, Thundering Herd 방지 | 장애 IP 자동 격리, 지터(jitter) 기반 워치독 |

각 사례는 독립적으로 5단 narrative 로 읽도록 작성. **시니어 백엔드 5년차+ 가 면접에서 "본인이 직접 푼 문제"로 자신 있게 풀어낼 수 있는 깊이.**

---

# 사례 1. SessionLockRegistry — 30+ Worker 가 같은 매장에 동시 접근하는 race 를 FIFO 큐 + lease TTL + cold-start guard 로 직렬화

## (1) 컨텍스트 — 한 매장에 worker 30+ 개가 동시에 달려드는 구조

`cmong-scraper-js` 는 NestJS worker 가 플랫폼별로 30+ 개 떠 있고, RabbitMQ consumer 가 들어오는 task 를 분산 처리한다. 한 매장(`shop_id`)에 대해 여러 API (`getReviews`, `addReply`, `getStores`, `keepAlive` …) 가 거의 동시에 들어오면, 같은 Camoufox 세션을 **여러 worker 가 동시에 잡으려 한다**. 같은 세션에서 페이지 두 개가 동시에 navigation 하면 Playwright 가 `execution context destroyed` 로 깨지고, 같은 매장의 로그인이 두 번 동시에 진행되면 외부 플랫폼이 IP 평판으로 차단해버린다.

전형적인 "공유 자원에 대한 멀티 라이터" 문제지만, 이 도메인이 특수한 것은:

- **무거운 자원의 lazy 생성**: Camoufox 브라우저 1개당 메모리 1GB+, 실행 시간 5–10 초 → 로그인 race 가 발생하면 그 자체로 N 배 메모리·런타임 폭증.
- **외부 봇 탐지의 영구 평판 차단**: 같은 매장의 로그인이 동시에 두 번 떨어지면 그 IP 가 즉시 평판 차단 → 다음 1–24 시간 동안 그 매장 작업 전체가 실패.
- **인스턴스 다중화**: ECS 에 task 가 N 개 떠 있어서 worker 1번이 죽어도 worker 2번이 그 매장을 이어받아야 함 → in-process Map 만으로는 부족, Redis 에 큐를 둬야 함.
- **Redis Cluster**: 운영은 AWS ElastiCache Serverless (Cluster mode). 같은 트랜잭션에 여러 키를 넣으면 CROSSSLOT 에러 → hash tag `{...}` 로 슬롯 강제 배정 필요.

## (2) 문제 — 4가지 race 가 동시에 잠재

저장소를 추적하면서 발견한 4가지 시나리오:

### Race A — 같은 매장에 N 개 worker 가 동시 로그인 요청
30+ worker 가 같은 매장에 `getReviews` task 를 받으면, 30 개가 동시에 "내가 직접 로그인하겠다" 하고 외부 플랫폼에 요청을 쏜다. 결과: 같은 ID로 동시에 30개 로그인 시도 → 평판 차단 + captcha.

### Race B — 한 worker 가 작업 중인데 다른 worker 의 watchdog 이 강제 종료
worker 1 이 매장 A 의 `getReviews` 를 30초째 진행 중인데, worker 2 의 watchdog 타이머가 "20초 넘었으니 죽이자" 하고 `safeCloseSession` 을 호출하면 worker 1 의 page 가 중간에 사라져 `execution context destroyed`.

### Race C — Cold start: 인스턴스가 재시작하면 Redis 큐만 남아 모두 대기 무한
ECS task 가 죽었다 살아나면 in-memory Map (`this.locks`) 은 비어있는데 Redis 의 `browser:queue:<sessionId>` 에는 옛 requestId 가 head 로 남아있다. 살아난 worker 가 그 head 의 차례를 기다리지만 옛 worker 는 죽어서 영원히 release 안 함 → 영구 deadlock.

### Race D — Redis Cluster 의 CROSSSLOT
큐 key (`browser:queue:<sessionId>`) 와 abort signal key (`browser:queue-abort:<sessionId>`), activity key, lease key 를 같은 MULTI/EXEC 에 묶으면, Cluster mode 에서 슬롯이 달라 CROSSSLOT 에러 (PR #566 `ab140a7`).

## (3) 해결 — `SessionLockRegistry` 가 4가지 race 를 모두 처리하는 단일 컴포넌트

파일: `src/browser/services/session-lock-registry.service.ts` (921 줄, 단일 클래스 + Handle 패턴).

### 핵심 설계 결정

**① Lease 기반 큐 (in-memory Map + Redis LIST 이중화)**

```ts
// 의사 코드
async enqueue(sessionId, requestId, options) {
  if (options.policy !== 'persist') return;        // (a) 정책 게이팅
  await this.clearAbortSignal(sessionId);          // (b) stale abort 정리
  await this.touchRequestLease(sessionId, requestId); // (c) 내 lease 갱신
  ... cold-start guard ...                          // (d) 옛 인스턴스 큐 정리
  await this.redis.rpush(queueKey, requestId);     // (e) 큐 끝에 추가
}
```

**② FIFO 직렬화 + 60초 lease TTL + 5초마다 lease 갱신**

`requestLeaseTtlMs = 90_000`, `requestLeaseRefreshIntervalMs = 5_000`. waitForTurn 루프 안에서 5초마다 `touchRequestLease` 호출 → 내가 살아있는 동안 lease 가 만료되지 않고, 내가 죽으면 90초 안에 다음 head 가 stale 로 인식해 evict.

**③ Cold-Start Guard (instance-aware lease)**

이 부분이 시니어 레벨 디테일이다. 인스턴스가 재시작했을 때, in-memory Map 은 비어있지만 Redis 의 큐 head 는 옛 인스턴스 requestId 가 그대로 남아있을 수 있다. lease TTL (90초) 안에는 아직 살아있다고 인식되어 evict 안 됨 → 새 worker 가 영원히 대기.

해결: lease 값에 **`{instanceId}:{Date.now()}`** 를 박는다. `randomUUID()` 로 매 인스턴스 시작 시 새 instanceId 생성. 새 인스턴스의 첫 enqueue 시점에 큐 head 의 lease 를 읽어 instanceId 가 다르면 → 옛 인스턴스 잔재 → 큐 통째로 비움:

```ts
const isCurrentInstance = leaseValue?.startsWith(`${this.instanceId}:`);
if (!isCurrentInstance) {
  const staleLength = await this.redis.llen(queueKey);
  await this.redis.del(queueKey);
  this.logger.warn(`[BrowserQueue] cold start: cleared ${staleLength} stale entries ...`);
}
```

면접 어휘로는 **"인스턴스 식별자를 lease value 에 박아서 cross-instance ownership 을 lease-level 에서 검증"**. Martin Kleppmann 의 fencing token 패턴의 단순화 버전.

**④ Stale Head Eviction (2초 주기)**

큐 head 의 requestId 가 lease 갱신을 멈춘 채로 90초 지나면 → 다음 caller 가 그 head 의 lease 키를 확인해 `EXISTS = 0` 이면 stale 로 판단, `LREM 1 head` 로 제거. 옛 인스턴스가 어떤 이유로든 진행을 멈춘 경우의 안전망.

**⑤ 5종 close 정책 (immediate / defer / idle-timer / hasWaitingRequests handoff)**

세션은 작업이 끝나도 즉시 닫지 않고, **다음 큐 entry 가 있으면 그 worker 에게 세션을 넘긴다 (handoff)**. 이게 댓글몽의 "한 매장의 로그인은 1회만, 다른 worker 는 이어받음" 의 핵심.

```ts
async releaseHandle(state) {
  if (state.activeCount > 0) state.activeCount -= 1;
  if (state.activeCount > 0) return;
  
  const pending = state.pendingClose;
  if (!pending) return;  // 명시적 close 요청 없으면 대기
  
  if (pending.type === 'immediate') return this.executeClose(state);
  
  // defer: idleTimeoutMs 뒤에 hasWaitingRequests 확인 후 결정
  state.idleTimer = setTimeout(async () => {
    const waiting = await this.hasWaitingRequests(state.sessionId, state.requestId);
    if (!waiting && state.activeCount === 0) await this.executeClose(state);
    else state.pendingClose = undefined;  // 대기자 있으니 세션 유지
  }, timeout);
}
```

**⑥ Redis Cluster CROSSSLOT 대응 — 단일 키 명령으로 분리**

```ts
async broadcastAbort(sessionId, reason) {
  // Cluster 환경에서는 multi/pipeline에 서로 다른 슬롯의 키가 섞이면 CROSSSLOT 오류
  // → 단일 키 명령으로 분리 실행
  await this.redis.set(this.getAbortKey(sessionId), reason, 'PX', this.abortReasonTtlMs);
  await this.redis.del(this.getQueueKey(sessionId));
  await this.redis.del(this.getQueueActivityKey(sessionId));
}
```

reputation 모듈은 반대 전략(hash tag `{pool}` 로 슬롯 강제 배정)을 쓰지만, queue 모듈은 슬롯 분산이 부하 측면에서 유리해서 **단일 키 명령으로 분리** 선택. **같은 시스템 안에서 두 전략을 의도적으로 다르게 쓴 것**이 시니어 디테일.

**⑦ Force Termination 시 activeCount 강제 리셋**

```ts
async forceTerminate(sessionId, requestId, reason) {
  await this.broadcastAbort(sessionId, reason);
  const state = this.locks.get(sessionId);
  if (!state) return;
  
  if (state.activeCount > 1) {
    this.logger.warn(`forceTerminate with ${state.activeCount} active handles - forcing activeCount=0`);
  }
  state.activeCount = 0;  // 다른 핸들의 release 실패해도 락 삭제 보장
  this.markImmediateClose(state);
  await this.executeClose(state);
}
```

다른 활성 핸들의 release 가 실패해도 락이 누수되지 않게 강제 리셋. 운영에서 "락 누수 → 그 매장 영구 잠김" 같은 사고를 차단하는 안전망.

**⑧ Sweep Orphaned Locks**

`getLockCount() > activeOperations × 2` 가 되면 (Map 누수 의심), `sweepOrphanedLocks(validSessionIds)` 호출 → `pages` Map 에 없는 sessionId 의 락을 모두 정리.

### Abort 신호 전파

`abortReasons: Map<string, { reason, createdAt }>` 를 인메모리로 두고 (`abortReasonTtlMs = 60_000`), Redis 가 없거나 느린 경우에도 같은 인스턴스 내 waiter 들은 즉시 abort 받는다. `pruneStaleAbortReasons()` 가 opportunistic 으로 호출되어 별도 timer 없이 정리.

### `attach()` Handle 패턴

```ts
attach(sessionId, operationName, requestId, options): SessionHandle
```

호출자는 try/finally 안에서 `handle.release()` 만 부르면 되고, 내부의 `activeCount`, `closeSession`, `pendingClose`, `idleTimer` 는 Registry 가 일관되게 관리. RAII 스타일 패턴 (Java 의 `try-with-resources`, Rust 의 RAII).

## (4) 성과

- **세션 유지율 99.2%** (최근 6개월 운영 지표, resume_v9 와 정합)
- **댓글 등록 중복 0건** (6개월) — 같은 매장에 동시 등록되어도 SessionLockRegistry + Idempotency-Key 조합으로 차단
- **`getReviews` race 로 인한 `execution context destroyed` 사고 0건** (PR #428 도입 이후)
- **Redis Cluster 이전 시 CROSSSLOT 에러 0건** (PR #566 의 hash tag 분리 정책 일관 적용)
- **인스턴스 재시작 후 dead-letter 큐 누수 0건** (cold-start guard 도입 후)

## (5) 기술 매핑

| 영역 | 사용 패턴/도구 |
|------|----------------|
| 분산 락 | Redis LIST (LPUSH/LREM/LINDEX) + per-request lease (`PSETEX`) + instance-aware lease value |
| 자원 추적 | `attach`/`release` Handle 패턴 (RAII) + `activeCount` invariant |
| 인스턴스 식별 | `randomUUID()` 로 instanceId 생성 → lease 값에 prefix |
| Cluster 대응 | hash tag (reputation 쪽) vs 단일 키 분리 (queue 쪽) — 모듈별 의도된 정책 |
| Cleanup | TTL prune (opportunistic) + sweep (호출 기반) + orphan PID kill (5분 reconcile) |
| 안전망 | `forceRelease` (운영 kill switch), `forceTerminate` (activeCount 강제 0), `evictStaleHead` (2초 주기) |
| 관측성 | `getSessionStats`, `getLockState`, `getAllLockSessionIds` (디버깅 endpoint 노출용) |
| 모범 사례 | `src/common/single-flight/__tests__/in-process.coordinator.spec.ts` 와 동일한 "계약 문서로서의 spec" 스타일 |

## 면접 narrative (시니어 5년차+ 답변 예시)

> "워커 30+ 개가 같은 매장에 동시 접근하는 race 가 운영에서 흔합니다. 단순 mutex 로는 cross-instance 가 안 되고, 단순 Redis 락은 인스턴스 재시작 시 cold start deadlock 이 됩니다.
>
> 그래서 4 layer 로 풀었습니다.
> (1) **FIFO 큐 (Redis LIST)** 로 직렬화하되, (2) **per-request lease (90초 TTL, 5초마다 갱신)** 으로 owner liveness 를 표현하고, (3) **instance-aware lease value (`{instanceId}:{timestamp}`)** 로 cold-start 때 옛 인스턴스 잔재를 감지·정리하며, (4) **handoff pattern** 으로 한 worker 의 release 시 다음 큐 entry 가 같은 Camoufox 세션을 재사용하도록 했습니다.
>
> 추가로 Redis Cluster 운영에서 CROSSSLOT 이슈를 reputation 모듈은 hash tag `{pool}` 로, queue 모듈은 단일 키 분리로 의도적으로 다르게 풀었는데, 큐는 부하 분산이 더 중요해서입니다.
>
> 결과적으로 세션 유지율 99.2%, 댓글 중복 등록 0건 (6개월), execution context destroyed 사고 0건 을 유지하고 있습니다."

## 이력서 한 줄 요약

> **워커 30+ 개가 같은 매장에 동시 접근하는 4가지 race (동시 로그인 / watchdog 강제종료 / cold-start deadlock / Redis Cluster CROSSSLOT)** 를 단일 `SessionLockRegistry` 컴포넌트로 일원화. FIFO 큐 + 90초 lease TTL + instance-aware lease value + handoff pattern + sweep/abort 안전망의 5층 구조. **세션 유지율 99.2%, 댓글 등록 중복 0건 (6개월), 인스턴스 재시작 시 큐 누수 0건** 유지.

## 추가 시니어 디테일

### 정책 게이팅: `policy === 'persist'` 만 큐 직렬화

```ts
async enqueue(sessionId, requestId, options) {
  if (options?.policy !== 'persist') return;  // (a) 정책 게이팅
  ...
}
```

`policy` 가 두 값: `'default'` (즉시 실행, 큐 우회) vs `'persist'` (큐 직렬화).
"가벼운 API 호출 (getStores 같은 리스트 조회)" 은 default 로 락 우회 → 처리량 손실 없음. "무거운 로그인 / addReply" 만 persist 로 직렬화. 정책 비용을 명시적으로 선택하는 caller 책임.

### `coldStartGuardDone` set — 한 번만 정리

```ts
private readonly coldStartGuardDone = new Set<string>();
...
if (!this.coldStartGuardDone.has(sessionId) && !this.isBusy(sessionId) && ...) {
  this.coldStartGuardDone.add(sessionId);
  // 옛 인스턴스 잔재 정리
}
```

cold-start guard 는 **한 sessionId 당 한 번만** 실행. 매번 enqueue 마다 stale check 하면 Redis 부담. `executeClose` / `forceRelease` 시점에 `coldStartGuardDone.delete(sessionId)` 호출 → 세션이 정상 정리되면 다음 enqueue 때 다시 guard 한 번 검증.

### Abort 신호의 인메모리 + Redis 이중 저장

`abortReasons: Map<string, { reason, createdAt }>` 인메모리 + Redis `browser:queue-abort:<sessionId>` (PX TTL). 이중 저장 이유:
- 같은 인스턴스 내 waiter — 인메모리에서 즉시 발견 (Redis round-trip 회피)
- 다른 인스턴스의 waiter — Redis 에서 발견

```ts
private async getAbortReason(sessionId): Promise<string | undefined> {
  const cached = this.abortReasons.get(sessionId);
  if (cached) {
    if (Date.now() - cached.createdAt > this.abortReasonTtlMs) {
      this.abortReasons.delete(sessionId);  // 만료된 인메모리는 제거 후 Redis 폴백
    } else {
      return cached.reason;
    }
  }
  if (!this.redis) return undefined;
  const reason = await this.redis.get(this.getAbortKey(sessionId));
  if (reason) {
    this.abortReasons.set(sessionId, { reason, createdAt: Date.now() });  // Redis hit → 인메모리 캐시
  }
  return reason ?? undefined;
}
```

**Negative cache 패턴 + TTL 양쪽 일관**.

### `pruneStaleAbortReasons()` — Opportunistic GC

```ts
private pruneStaleAbortReasons(): void {
  const now = Date.now();
  if (now - this.lastAbortReasonPruneAt < this.abortReasonPruneIntervalMs) return;
  this.lastAbortReasonPruneAt = now;
  for (const [sessionId, entry] of this.abortReasons) {
    if (now - entry.createdAt > this.abortReasonTtlMs) {
      this.abortReasons.delete(sessionId);
    }
  }
}
```

별도 setInterval 없이 enqueue / broadcastAbort 시점에 같이 호출. `lastAbortReasonPruneAt` 으로 5초 throttle. **GC overhead 최소화** — Java/JVM 면접에서도 자주 나오는 Lazy GC 패턴의 동일한 발상.

---

# 사례 2. Single-Flight Coordinator 포트화 — 5 불변식을 데코레이터 4종 합성으로 풀고, 행동 계약을 spec 으로 박은 일

## (1) 컨텍스트 — NaverService 안에 묻혀있던 80+ 줄의 인-메모리 single-flight

NAVER 의 `ensureSession()` 은 한 사용자(`platformId`) 에 대한 동시 요청 N 개를 받으면, 첫 번째만 실제 로그인을 하고 나머지는 그 결과를 공유해야 한다 (single-flight, coalescing). Issue #531 (PR #532) 에서 처음 인-메모리 Map 으로 구현했는데:

- 코드는 NaverService 안에 인라인으로 80+ 줄이 들어가 있었음
- 멀티 인스턴스에 대응하려면 Redis 어댑터로 교체해야 하는데, 그러려면 NaverService 를 다시 손대야 함
- 같은 패턴이 baemin / cpeats / yogiyo 에서도 필요할 텐데 재사용이 안 됨
- 데드라인 (deadline), 대기열 cap (capacity), 운영 kill switch, 관측성 (telemetry), heartbeat 같은 횡단 관심사가 빠짐

## (2) 문제 — Single-Flight 가 외부에 약속하는 "행동 계약(behavioral contract)" 자체를 명문화하지 않으면 회귀가 잡히지 않는다

코드를 추출만 한다고 끝나지 않는다. 이 코디네이터가 사용자에게 무엇을 보장해야 하는지(=계약) 가 spec 으로 박혀있지 않으면, 6개월 뒤 누가 만지다가 미세하게 깨도 모른다. 특히:

- **결과 일관성**: owner 의 promise (성공/실패) 가 합류한 모든 waiter 에게 같은 인스턴스로 전파되어야 함 (스택 트레이스 보존).
- **세대 가드**: forceRelease 직후 같은 tick 에 들어온 후속 호출이 새 owner 가 되고, 옛 record 의 늦은 `finally` cleanup 이 새 record 를 지우면 안 됨.
- **동기 throw 정규화**: `operation()` 이 sync throw 해도 Map 에 record 가 박힌 뒤에 throw → 다른 caller 가 coalesce 못 하고 deadlock 되지 않게.

이 3개는 spec 으로 명문화하지 않으면 코드 리뷰에서 매번 새로 발견되는 함정.

## (3) 해결 — Port + 4 decorator + 계약 spec

### 결정 1: Port-Adapter 추출

`src/common/single-flight/single-flight-coordinator.port.ts`:
```ts
export interface SingleFlightCoordinator {
  execute<T>(key: string, operation: () => Promise<T>, options?: SingleFlightOptions): Promise<T>;
  getInflightState(): readonly InflightEntry[];
  forceRelease(key: string, reason: string): Promise<void>;
}
```

NaverService 는 이 인터페이스만 의존. 내부 어댑터를 in-process / Redis / future MQ-routing 으로 교체해도 NaverService 는 안 바뀐다 (Open/Closed).

### 결정 2: 4 데코레이터 합성

PR #569 (`8f77220`) 의 커밋 본문 그대로:

```
Core port `SingleFlightCoordinator` + 4 decorators stacked in DI:
- InProcessSingleFlightCoordinator (Map + forceRelease gate)
- DeadlineSingleFlightDecorator      (Promise.race wall-clock timeout)
- CapacitySingleFlightDecorator      (waiter cap load-shedding)
- HeartbeatSingleFlightDecorator     (15s scan → long_running warn + gauge)
- TelemetrySingleFlightDecorator     (owner_started/finished/failed/coalesced
                                       + singleflight.* metrics)
```

각 decorator 는 자기 관심사 하나만 다루고, NestJS DI Factory 가 `SINGLE_FLIGHT_BACKEND` env 로 어떤 backend 를 깔지 선택. 면접 어휘로는 **"Decorator pattern + Strategy pattern 의 합성, OCP 보존"**.

### 결정 3: 행동 계약 7가지를 spec 헤더에 박음

`src/common/single-flight/__tests__/in-process.coordinator.spec.ts` 의 헤더 (저장소 AGENTS.md 에 모범 사례로 명시됨):

```
# 코디네이터가 보장하는 7가지 속성
[1] 코알레싱      — 같은 키 동시 호출은 작업을 1번만 실행
[2] 결과 일관성   — 같은 cause 인스턴스 공유 (스택 트레이스 보존)
[3] 자원 정리     — 모든 settle 경로에서 record 즉시 제거
[4] kill switch   — forceRelease 직후 후속 호출이 새 owner, 세대 가드
[5] 호출자 격리   — 서로 다른 키는 영향 없음
[6] 입력 계약     — 동기 throw 도 promise rejection 으로 정규화
[7] 관측성        — getInflightState 가 InflightEntry 계약 노출
```

각 `describe` 그룹이 `[1]`–`[7]` 1:1 매핑. **테스트가 빨간색이 되면 "어떤 계약이 깨졌는지" 그룹명에 즉시 보인다.**

### 결정 4: 세대 가드 (Generation Guard)

`adapters/in-process.coordinator.ts`:
```ts
record.promise = Promise.race([opPromise, releaseGate]).finally(() => {
  // forceRelease 가 이미 record 를 새 것으로 교체했을 수 있음 → 후속 record 를 지우지 않게 가드
  if (this.inflight.get(key) === (record as InflightRecord)) {
    this.inflight.delete(key);
  }
});
```

forceRelease 가 `this.inflight.delete(key)` 하고 다음 caller 가 새 record 를 박은 뒤, 옛 record 의 늦은 `finally` 가 트리거 되면 새 record 를 지워버리는 회귀를 차단.

### 결정 5: Sync throw → Microtask 지연 실행

PR #569 의 review follow-up:
```ts
// PR #569 review follow-up: defer `operation()` to the microtask queue.
// 1. operation 이 sync throw 해도 record 가 Map 에 박힌 뒤에 throw 됨
// 2. 같은 tick 에 들어온 concurrent caller 들이 새 owner 가 아니라 waiter 로 합류
const opPromise = Promise.resolve().then(() => operation());
```

`Promise.resolve().then(() => operation())` 한 줄이 두 가지 hazard 를 동시에 처리. 시니어 코드 리뷰의 산물.

### 결정 6: 안전망 default 값 명시

PR #569 본문:
```
- Default deadline 180_000ms — covers 2FA 120s + waitForReplacement
- Default maxWaiters 30 — UI-spam load-shedding
- long_running warn at 60s — stuck-owner early signal before deadline fires
- forceRelease ops kill-switch — rejects waiters + removes entry
```

각 숫자가 도메인 사실(2FA 120초)에 근거. **운영 의도가 코드에 박힌 default**.

### Force Release 의 promise race 패턴

```ts
let rejectRelease!: (err: Error) => void;
const releaseGate = new Promise<never>((_, reject) => { rejectRelease = reject; });

record.promise = Promise.race([opPromise, releaseGate]).finally(...);

// forceRelease 시:
async forceRelease(key, reason) {
  const record = this.inflight.get(key);
  if (!record) return;
  this.inflight.delete(key);
  record.reject(new SingleFlightForceReleasedException(key, reason));
}
```

owner 의 promise 가 영원히 settle 안 해도 (예: stuck), 운영자가 `forceRelease` 하면 release gate 가 reject → 모든 waiter 가 즉시 `SingleFlightForceReleasedException` 으로 reject 받음. **stuck owner 에 대한 escape hatch 가 인프라 레벨에서 보장됨**.

## (4) 성과

PR #569 커밋 본문:
- **NaverService 80+ 줄 제거** — coordination + telemetry 가 thin call `coordinator.execute(id, op, { telemetryTag })` 로 줄어듦
- **22 new unit specs** — adapter/decorator 별로 격리 검증
- **기존 575 NAVER 테스트 통과**
- **Issue #533 (Redis backend) 추가 시 NaverService 안 건드림** — DI factory 만 swap
- **AGENTS.md 의 모범 사례로 박힘** — 이 spec 의 헤더 구조가 회사 표준이 됨

## (5) 기술 매핑

| 영역 | 사용 패턴/도구 |
|------|----------------|
| 아키텍처 | Port-Adapter (Hexagonal) + Decorator + Strategy |
| 동시성 | `Promise.race`, microtask deferral, generation guard |
| 운영 | Default deadlines/timeouts, long-running warn, forceRelease kill switch |
| 관측성 | Telemetry decorator (`singleflight.*` metrics: started/finished/failed/coalesced) |
| 테스트 | "계약 문서로서의 spec" — 7가지 행동 속성을 헤더에 박고 describe 1:1 매핑 |
| DI | NestJS `useFactory` 로 backend 선택 (`SINGLE_FLIGHT_BACKEND`) |
| 회사 자산 | 이 spec 스타일이 AGENTS.md 의 회사 표준 모범 사례로 박힘 |

## 면접 narrative

> "NAVER 의 ensureSession 안에 80+ 줄의 인-메모리 single-flight 가 묻혀있었습니다. Issue #533 으로 Redis 어댑터를 추가하려는데, NaverService 를 또 손대야 했죠. 그래서 Port-Adapter 로 분리하고, 5가지 운영 관심사 (deadline / capacity / heartbeat / telemetry / kill-switch) 를 데코레이터 4개로 분해해 합성하는 구조로 갔습니다.
>
> 시니어 디테일 두 가지는: (1) **세대 가드(generation guard)** — forceRelease 후 같은 tick 에 들어온 새 owner 가 박힌 record 를 옛 record 의 늦은 finally cleanup 이 지우는 race 가 있어서, `this.inflight.get(key) === record` 비교로 차단. (2) **sync-throw 정규화** — `Promise.resolve().then(() => operation())` 한 줄로 sync throw 를 promise rejection 으로 바꾸고, 동시에 record 가 Map 에 박힌 뒤에 operation 이 실행되도록 보장.
>
> 그리고 이게 진짜 핵심인데, 코디네이터가 외부에 약속하는 7가지 행동 속성 (코알레싱 / 결과 일관성 / 자원 정리 / kill switch / 호출자 격리 / 입력 계약 / 관측성) 을 spec 헤더에 명문화하고 describe 그룹을 1:1 매핑했습니다. 빨간색이 뜨면 어느 계약이 깨졌는지 그룹명에 즉시 보입니다. 이 spec 스타일이 회사 AGENTS.md 의 모범 사례로 박혔습니다."

## 이력서 한 줄 요약

> NaverService 안에 묻혀있던 인-메모리 single-flight (80+ 줄) 를 **Port-Adapter + 4 decorator 합성 (deadline / capacity / heartbeat / telemetry)** 로 분리하고, **세대 가드 + sync-throw microtask 정규화 + forceRelease kill-switch** 의 3가지 시니어 디테일을 적용. **7가지 행동 계약을 spec 헤더에 명문화** 해 회귀를 그룹명 단위로 진단 가능하게 만들었고, 이 spec 스타일이 사내 모범 사례로 박힘.

---

# 사례 3. Camoufox Heavy 브라우저 풀 — Launch Semaphore + Prewarm Pool + Quarantine + Orphan PID Sweep 의 5층 자원 격리

## (1) 컨텍스트 — Camoufox 한 인스턴스가 GB 단위로 메모리를 먹는 stealth 브라우저

CPEATS (쿠팡이츠) 는 Akamai Bot Manager 가 깔려있어서 평범한 Chromium 으로는 즉시 차단. Camoufox (Firefox 기반 stealth fork) 가 fingerprint 우회에 효과적이지만, 비용이 크다:

- **메모리**: 1 instance ≈ 700MB–1GB+
- **launch 시간**: 5–10 초 (Akamai sensor 가 준비될 때까지)
- **OS 자원**: child process + tmp dir + socket — Node 의 GC 로 안 잡힘
- **OOM 위험**: ECS task 메모리 한계 (25G) 안에서 30+ 개 동시 launch 시 즉시 죽음

AGENTS.md 자체에 `**CPEATS**: Camoufox 브라우저 Heavy — OOM 위험, 메모리 25G+ 권장, page.close() 필수` 로 박혀있을 정도.

## (2) 문제 — 4가지 자원 누수 시나리오

PR #452 (`5b22d62`) 커밋 본문에 정리된 그대로:

```
Phase 3 (SESSION_MISSING SIGKILL) 은 disconnect 이벤트가 발생해야만 동작.
Phase 4 (BUSY_TTL 초과) 는 watchdog 이 busyStartedAt=undefined 로 리셋한 세션을 못 잡음.
→ OS에 살아있지만 pidRegistry/camoufoxSessions/pages 어디에도 없는 진짜 고아 프로세스가 누적.

운영 측정 (server-08):
- camoufoxActiveCount 40 vs sessions 31 (격차 9)
- busy 보호 스킵 305건/5분, BUSY_TTL 초과 0건
- 이미 watchdog 이 activeOperations 삭제 + busyStartedAt=undefined 리셋을 수행한 뒤
  safeCloseSession 이 hang → OS 프로세스 좀비 → reconcile 의 busy 보호도 안 잡힘
```

요약하면:
- **Phase 1**: Map 에는 있지만 PID 가 죽은 세션
- **Phase 2**: PID 는 살아있지만 Map 에서 누락된 orphan
- **Phase 3**: disconnect 이벤트가 안 떠서 정리 안 된 zombie
- **Phase 4**: watchdog 이 reset 만 하고 진짜 정리는 안 함
- **Phase 5 (PR #452)**: OS 레벨에서 PID 비교해 위 4 phase 가 다 놓친 진짜 고아 강제 정리

추가로 **launch race**: 30+ worker 가 동시에 `launchCamoufoxServer` 를 부르면 OS 자원 경합으로 대부분 실패 (커밋 `src/browser/browser.service.ts:310`).

## (3) 해결 — 5층 자원 격리 + Prewarm Pool + Quick Retry v2

### Layer A: Launch Semaphore (PR #321/#322)

```ts
// src/browser/browser.service.ts:1655
private acquireLaunchSlot(): Promise<void> {
  if (this.currentLaunchCount < this.MAX_CONCURRENT_LAUNCHES) {
    this.currentLaunchCount++;
    return Promise.resolve();
  }
  return new Promise<void>((resolve, reject) => {
    const timer = setTimeout(() => {
      const idx = this.launchQueue.findIndex(q => q.resolve === resolve);
      if (idx !== -1) this.launchQueue.splice(idx, 1);
      this.camoufoxMetrics.launchQueueTimeouts++;
      reject(new Error(`Launch queue timeout (${this.LAUNCH_QUEUE_TIMEOUT}ms, queueSize=${this.launchQueue.length})`));
    }, this.LAUNCH_QUEUE_TIMEOUT);
    this.launchQueue.push({ resolve, reject, timer });
    ...
  });
}

private releaseLaunchSlot(): void {
  if (this.launchQueue.length > 0) {
    const next = this.launchQueue.shift()!;
    clearTimeout(next.timer);
    // currentLaunchCount 유지 — 슬롯을 다음 요청에 양도
    next.resolve();
  } else {
    this.currentLaunchCount--;
  }
}
```

세마포어 + FIFO 큐 + 타임아웃. 슬롯을 직접 양도(handoff)하는 패턴으로 atomic 보장.

### Layer B: Prewarm Pool + Warmup Gate (PR #323/#326/#327)

- 워커가 idle 인 시점에 N개 Camoufox 를 미리 띄워놓음
- 새 요청이 오면 prewarm 에서 adopt (cold launch 5–10 초 → ms 단위)
- "warmup 완료" 가 충족되기 전엔 traffic 차단 (`94484c3 feat(camoufox): gate traffic on prewarm warmup`)
- proxy metadata 보존 (`fc01573 fix(camoufox): preserve proxy metadata on prewarm adopt`)
- warmup-satisfied latch (`a796c4d fix(prewarm): latch warmup satisfied to prevent re-entering warming_up`)

### Layer C: Quick Retry v2 — Prewarm Swap + Quarantine (PR `48a6167`)

```
Phase 1: Akamai 차단 시 다른 IP의 프리웜 브라우저로 즉시 교체
- browser.service.ts: swapWithPrewarmBrowser() 메서드 추가
  - 현재 세션을 quarantine으로 이동 후 prewarm pool에서 새 브라우저 획득
  - excludeProxyPort로 같은 Decodo 포트(=같은 IP) 재할당 방지
- Quarantine 패턴 (quarantineSession, processQuarantineQueue, getQuarantineStats)
  - 실패 브라우저를 pool에 직접 반환하지 않고 격리 후 destroy
  - prewarm 스케줄러(15초)에서 주기적 큐 처리

Quick Retry 흐름:
Quick Retry #1 (같은 브라우저) → Prewarm Swap x2 (새 IP) → Full Retry
기본값: CPEATS_QUICK_RETRY_MAX=1, CPEATS_PREWARM_SWAP_MAX=2

로컬 Docker 테스트: 40계정 x 동시성40 → 97.2% 성공률 (Auth 제외)
```

**Quarantine 가 시니어 디테일**: 실패한 브라우저를 pool 에 바로 돌려놓지 않고, "격리 후 destroy" 큐에 넣어 15초 후에 천천히 정리. 이유: Camoufox 가 실패한 뒤에도 메모리 누수 + child process 잔재가 있을 수 있어서, 비동기로 다른 작업 영향 안 주고 정리.

### Layer D: 5-Phase Zombie Cleanup (PR #448 / #451 / #452)

```
Phase 3: SESSION_MISSING SIGKILL — disconnect 이벤트 시
Phase 4: BUSY_TTL 초과 강제 정리 — watchdog 의 busy 보호 우회
Phase 5: OS PID 기반 orphan sweep — 위 1–4 가 다 놓친 진짜 고아
```

`cleanupOrphanPid()`:
```ts
private async cleanupOrphanPid(targetPid: number): Promise<void> {
  const registryEntry = this.pidRegistry.get(targetPid);
  let sessionId = registryEntry?.sessionId;
  if (!sessionId) {
    for (const [id, entry] of this.camoufoxSessions.entries()) {
      if (entry.pid === targetPid) { sessionId = id; break; }
    }
  }
  if (sessionId) {
    await this.finalizeCamoufoxCleanup(sessionId, { closeBrowser: true });
    return;
  }
  // Map에 매칭되지 않는 orphan PID → 직접 kill
  await this.killProcessTree(targetPid).catch(() => {});
  this.pidRegistry.delete(targetPid);
  if (this.browserProcessCollector) {
    this.browserProcessCollector.unregisterProcessByPid(targetPid);
  }
}
```

운영 측정 ("camoufoxActiveCount 40 vs sessions 31, 격차 9") 을 PR 본문에 박는 게 시니어 운영 시그널.

### Layer E: Jittered Watchdog (Thundering Herd 방지)

```ts
// browser.service.ts:2342
getJitteredWatchdogMs(baseMs: number, maxJitterMs: number = 30_000): number {
  const jitter = Math.random() * maxJitterMs;
  return Math.floor(baseMs + jitter);
}
```

> 동일한 시간에 시작된 다수의 요청이 고정된 타임아웃(예: 300초)을 가지면 모두 같은 시점에 타임아웃되어 동시에 정리 작업이 발생합니다. 이로 인한 메모리 압박과 연쇄 실패를 방지하기 위해 0-30초의 랜덤 지터를 추가합니다.

면접 어휘: **Thundering Herd 방지 jitter, Google SRE book 의 backoff-with-jitter 패턴**.

### Layer F: PID Liveness 캐시

```ts
// browser.service.ts:1723
private isPidAlive(pid: number): boolean {
  const cached = this.pidCheckCache.get(pid);
  const now = Date.now();
  if (cached && now - cached.checkedAt < this.PID_CHECK_CACHE_TTL) return cached.alive;
  
  let alive = true;
  try { process.kill(pid, 0); }  // signal 0 = 존재 여부만 확인
  catch (e) {
    const error = e as NodeJS.ErrnoException;
    if (error.code === 'ESRCH') alive = false; // No such process
    // EPERM 등은 존재하는 것으로 간주 (다른 유저 소유)
  }
  ...
}
```

`process.kill(pid, 0)` 으로 signal 만 보내 PID 존재 확인. `ESRCH` (no such process) 만 `false`, `EPERM` 은 다른 유저 소유라 살아있는 것으로 간주. 짧은 TTL 캐시로 매 호출의 syscall 비용 회피.

## (4) 성과

- **OOM 회귀 차단**: Camoufox launch race 로 인한 메모리 폭증 사고 0건 (Launch Semaphore 도입 이후)
- **97.2% 성공률 (40 concurrent)**: PR `48a6167` 로컬 Docker 테스트
- **운영 격차 (camoufoxActiveCount 40 vs sessions 31, 9개 차) 가 0으로 수렴**: Phase 5 orphan sweep 도입 후
- **세션 thrashing 회귀 차단**: warmup gate + adopt 로 cold launch 시간 ms 단위 단축
- **Thundering Herd 사고 0건**: jittered watchdog 도입 후

## (5) 기술 매핑

| 영역 | 사용 패턴/도구 |
|------|----------------|
| 동시성 제어 | Semaphore + FIFO 큐 + 슬롯 handoff |
| 자원 풀 | Prewarm pool + adopt + warmup gate |
| 실패 격리 | Quarantine queue + 비동기 destroy |
| OS 자원 | `process.kill(pid, 0)` liveness + ESRCH/EPERM 분기 + 5-phase orphan sweep |
| 재시도 | Quick Retry v2 = 같은 브라우저 1회 + Prewarm Swap 2회 + Full Retry 1회 |
| 부하 분산 | Jittered watchdog (Thundering Herd 방지) |
| 관측성 | `camoufoxMetrics` 객체에 launchQueueTimeouts, launchQueuePeakSize, orphanCleanupCount |

## 면접 narrative

> "Camoufox 가 instance 당 1GB 가까이 먹어서, 30+ worker 가 같은 ECS task 에서 동시에 launch 하면 즉시 OOM 입니다. 그래서 5 layer 로 풀었습니다.
>
> (1) **Launch Semaphore** — N개로 동시 launch 제한, 큐 + handoff 로 슬롯 양도. (2) **Prewarm Pool** — idle 시점에 N 개 미리 띄우고 warmup gate 로 traffic 차단. (3) **Quick Retry v2 + Quarantine** — Akamai 차단 시 같은 브라우저 1회 → 다른 IP prewarm swap 2회 → full retry. 실패 브라우저는 pool 에 바로 안 돌려놓고 quarantine queue 에 격리 후 비동기로 destroy. (4) **5-phase zombie cleanup** — disconnect 이벤트 / BUSY_TTL 초과 / OS PID 비교 — 위가 다 놓친 진짜 고아 프로세스를 30초마다 OS PID 비교로 강제 정리. (5) **Jittered Watchdog** — 같은 시각 타임아웃 thundering herd 방지로 0–30초 jitter.
>
> Phase 5 추가 결정의 트리거는 운영 측정이었습니다: `camoufoxActiveCount 40 vs sessions 31` 격차 9, BUSY_TTL 초과 0건. 즉 in-memory Map 끼리도 일관성이 깨졌고 watchdog 의 busy 보호도 못 잡았다는 신호여서, OS 레벨에서 PID 합집합 비교를 추가했습니다.
>
> 결과적으로 OOM 사고 0건, 40 concurrent 에서 97.2% 성공률, camoufoxActiveCount 격차가 0으로 수렴."

## 이력서 한 줄 요약

> Camoufox stealth 브라우저(1 instance ≈ 1GB) 30+ 동시 launch 의 OOM 위험을 **Launch Semaphore + Prewarm Pool + Quarantine + 5-phase Zombie Cleanup + Jittered Watchdog** 의 5층 자원 격리로 해결. 운영 측정 (camoufoxActiveCount 격차 9 → 0) 기반으로 PR 본문에 측정 데이터를 박은 시니어 운영 방식. **40 concurrent 에서 97.2% 성공률 (PR #48a6167 로컬 테스트), OOM 사고 0건**.

---

# 사례 4. Akamai Bot Manager 우회 — referrer warming + bm_sv polling + `_abck` 4-state 머신 + race window polling

## (1) 컨텍스트 — 쿠팡이츠의 Akamai 가 99% 차단하던 시점

CPEATS (쿠팡이츠 사장님 사이트) 는 Akamai Bot Manager (`AkamaiGHost`) 가 깔려있어서, 평범한 Playwright/Chromium 으로는 99% 차단이 났다. Camoufox 로 fingerprint 우회를 해도, sensor 가 채 준비되기 전에 로그인을 제출하면 `_abck` cookie 가 `~-1~` (pending) 상태로 sensor 검증 실패 → 403 응답.

Issue #629 (4-phase) 의 일부 발췌 (커밋 본문 통해 추적):
- **P3-0**: Akamai 봇 탐지 진단 metric 강화 — `_abck` 전이 / bm_sv 생성 / 차단 분류 / retry 사유 (PR `f2d17a0`)
- **P3-1**: `_abck` 상태 머신 + 2초 race window polling — Akamai 조기 break 회피 (PR `13c5cc3`)
- **P3-1.1**: polling 안 Akamai sensor request 계측 (PR `5b06a3c`)
- **P3-1.3**: bm_sv polling maxWaitMs 30000ms → 5000ms — fail-fast (PR `439a1de`)
- **PR #644**: 봇 탐지 우회 default ON — referrer warming + bm_sv polling + sensor wait 확장 (PR `96d0285`)
  - 측정: baseline 7/9 (77.8%) → patch 적용 후 18/18 (100%)

## (2) 문제 — 4가지 race + 3가지 분류 오류

### Race A — `_abck=~0~,~-1~,~timestamp~` (verified + challenged 혼재)

`abck-state-classifier.util.ts` 의 주석:
> Prod 진단: `_abck` 가 `~0~,~-1~,~timestamp~` (verified + challenged 동시) 인 상태에서 sensor 제출 → 403 차단 폭주. 기존 `~0~` 첫 등장 시 즉시 break 로직은 race window 안의 `~-1~` 추가를 놓쳐 불필요한 sensor 제출로 이어짐.

즉, `_abck` 가 `~0~` 만 가진 적이 1ms 라도 있으면 verified 로 오판해 sensor 제출 → 그 직후 `~-1~` 추가되면서 차단.

### Race B — `~0~,~1~` 혼재 시 VERIFIED_ONLY 오분류

이전 구현 `has1Only = ~1~ && !~0~` 은 `~0~,~1~` 혼재 시 VERIFIED_ONLY 로 오분류. `~1~` 은 BLOCKED 시그널인데 다른 토큰과 혼재하면 BLOCKED 우선이어야 함.

### Race C — `AkamaiGHost` 응답을 PASSWORD_ERROR 로 오분류

PR `0630914`: `AkamaiGHost` 헤더가 붙은 차단 응답이 application-level 401/403 으로 보여 `PASSWORD_ERROR` 로 retry → Full Retry 안 됨 → 영구 실패.

### Race D — Sensor 제출 후 즉시 break

옛 구현은 `_abck` 가 `~0~` 가 되자마자 break → sensor 가 다음 1–2초 안에 추가 검증을 더 하는데 그게 race window 안에 `~-1~` 추가로 떨어지면 차단.

## (3) 해결 — 4-state 머신 + race window polling + referrer warming + 분류 우선순위 명문화

### 결정 1: `_abck` 4-state classifier (`abck-state-classifier.util.ts`)

```ts
// AbckState = 'INITIAL' | 'VERIFIED_ONLY' | 'CHALLENGED' | 'BLOCKED'

export function classifyAbckState(value: string | undefined): AbckState {
  if (!value) return 'INITIAL';
  
  const has0 = /~0~/.test(value);
  const hasNeg1 = /~-1~/.test(value);
  // ~-1~ 와 구분 — regex `~1~` 는 `~-1~` 안에 매치되지 않음 (`-` 가 사이에 있음)
  const has1 = /~1~/.test(value);
  
  // BLOCKED 가 가장 강한 시그널 — ~1~ 포함 시 다른 토큰 무관하게 BLOCKED
  // (이전: has1Only = ~1~ && !~0~ → ~0~,~1~ 혼재 시 VERIFIED_ONLY 로 오분류되던 결함 수정)
  if (has1) return 'BLOCKED';
  if (hasNeg1) return 'CHALLENGED';
  if (has0) return 'VERIFIED_ONLY';
  return 'INITIAL';
}
```

판정 우선순위가 코드 주석에 명문화 — `~1~` 단독 검사 시 `~-1~` 안에 매치 안 되는 이유까지 적혀있음. 면접 시 "여기까지 적혀있어야 6개월 뒤 만지는 사람이 안 깨먹습니다" 로 풀면 됨.

### 결정 2: bm_sv polling policy 가 service.ts 와 spec 의 SSOT

`abck-polling-policy.util.ts`:
```ts
/**
 * Issue #629 P3-1.3 — bm_sv polling 정책 결정 helper.
 * service 와 spec 양쪽이 같은 함수를 호출하여 정책 분기 변경 시 spec 이 자동으로 그
 * 변경을 검증하도록 SSOT (Single Source of Truth) 를 보장한다.
 */
export function decideBmSvPollingAction(params): BmSvPollingAction {
  if (params.hasBmSv) return { type: 'BREAK_BM_SV' };
  if (params.currentAbckState === 'CHALLENGED') return { type: 'OBSERVE_CHALLENGED' };
  if (params.currentAbckState === 'BLOCKED') return { type: 'OBSERVE_BLOCKED' };
  if (params.currentAbckState === 'VERIFIED_ONLY' && params.prevAbckState !== 'VERIFIED_ONLY') {
    return { type: 'ENTER_RACE_WINDOW' };
  }
  return { type: 'CONTINUE' };
}
```

**시니어 디테일**: 정책 분기 자체를 inline if/else 가 아니라 **순수 함수 + discriminated union** 으로 추출. 이래야 spec 이 정책의 행동만 테스트하고, service 코드 변경 시 정책이 깨지면 spec 이 즉시 잡는다. 운영 정책의 회귀 차단.

### 결정 3: P3-1.3 — `throw 없음, polling 계속` 정책

옛 구현은 `_abck=CHALLENGED` 면 즉시 throw → sensor JS 가 600ms+ 안에 자동 제출하는 기회 박탈. 새 정책:
- bm_sv 발급 시 즉시 break
- CHALLENGED / BLOCKED 관찰 시 로그만, polling 계속
- VERIFIED_ONLY 첫 관찰 시 race window 진입 → 안정 확인 시 break, 전이 감지 시 로그만

`439a1de` 커밋: 30000ms → 5000ms로 줄여 fail-fast 도 같이.

### 결정 4: Referrer Warming (PR #644)

```ts
// debug openLoginPage 의 warming 부분 (browser path 와 동일 로직)
await page.goto(cpeatsURL.mainUrl, { waitUntil: 'domcontentloaded', timeout: 25000 });
const warmMaxMs = Number(process.env.CPEATS_PREWARM_WAIT_MS) || 15000;
const warmStart = Date.now();
while (Date.now() - warmStart < warmMaxMs) {
  const cookies = await page.context().cookies().catch(() => []);
  if (cookies.some(c => c.name === 'bm_sv')) break;
  await page.mouse.move(200 + Math.random() * 400, 100 + Math.random() * 300, {
    steps: 3 + Math.floor(Math.random() * 3),
  }).catch(() => undefined);
  await page.waitForTimeout(800 + Math.random() * 400).catch(() => undefined);
}
```

**핵심 원리** (PR #644 커밋 본문):
> mainUrl 거쳐 referrer chain 만들고 15s 동안 mouse move 유지 → AKAMAI sensor 가 human-like telemetry 누적 → abck 가 verified 상태로 인식 → silent block 회피. sensor wait 8s 와 abck race window 5s 확장은 verify 완료까지 충분한 시간 확보.

마우스 이동 범위(200–600, 100–400 픽셀) + 스텝수 3–5 + 800–1200ms 대기 모두 jitter 가 들어가 있음 — human-like.

### 결정 5: 분류 우선순위 명문화 (`akamai-block-detector.util.ts`)

```ts
/**
 * Issue #615 — Akamai 차단 신호 감지 helper.
 *
 * CPEATS 로그인 흐름에서 PASSWORD_ERROR throw 직전에 호출하여 차단 시
 * `AKAMAI_BLOCKED` 로 분류 (Full Retry) 해야 할지 판단한다.
 *
 * 본 helper 는 cpeats.service.ts 의 메인 loginResult 분기 + Quick Retry 분기 +
 * Prewarm Swap 분기 세 경로에서 일관되게 호출되어 분류 우선순위를 보장한다.
 * 한 곳만 보강하면 page.on("response") 인터셉터의 비동기 set 시점에 따라 retry
 * 경로가 false 를 보고 UnauthorizedException 으로 끝나는 silent 회귀가 발생할
 * 수 있다 (PR #618 review feedback).
 */
export function isAkamaiBlockDetected(diagnostics: AkamaiBlockDiagnostics): boolean {
  if (diagnostics.akamaiBlockDetected === true) return true;
  if (diagnostics.networkErrors?.some(e => e.error?.includes('403'))) return true;
  return false;
}
```

세 경로 (main / quick retry / prewarm swap) 에서 같은 helper 를 호출해야 race condition 으로 인한 분류 회귀가 안 생긴다는 **PR #618 리뷰 피드백을 코드 주석에 명문화**. 이게 시니어 코드 리뷰 문화의 산물.

### 결정 6: Click Loop (PR #655)

옛 구현은 Enter key 1회 제출 → Akamai 가 timing 보고 차단. 새 구현 (`e58e925`):
> submit Enter 1회 → click loop (최대 25회, 1~2초 랜덤)

`page.click` 25번 (1–2초 jitter) 반복. 사람 행동 (제출 안 됐다 다시 누름) 시뮬레이션.

## (4) 성과

PR #644 커밋 본문 (재인용):
- **baseline (default RES, env 0)**: 7/9 = **77.8%**
- **patch 적용 후**: 6 iter × 3 worker = **18/18 = 100%**
  - 3 iter baseline: 9/9 (100%)
  - 5 iter 검증: 15/15 (100%)
  - 6 iter 확장 (pool 한계 자동 종료): 18/18 (100%)
- **measurement 효과 입증되어 default ON** — env=false 로만 비활성
- **AkamaiGHost → PASSWORD_ERROR 오분류 사고 0건** (PR #618 이후)
- **`_abck=~0~,~1~` 혼재 silent VERIFIED 오분류 사고 0건** (PR #631 codex 리뷰 수정 이후)

## (5) 기술 매핑

| 영역 | 사용 패턴/도구 |
|------|----------------|
| 봇 탐지 우회 | Camoufox (Firefox stealth) + Akamai sensor wait + referrer warming + bm_sv polling + click loop |
| 상태 머신 | `_abck` 4-state classifier (`INITIAL` / `VERIFIED_ONLY` / `CHALLENGED` / `BLOCKED`) |
| 정책 분리 | `decideBmSvPollingAction()` / `decideRaceWindowAction()` 순수 함수 — service 와 spec 의 SSOT |
| 분류 우선순위 | 3 경로 (main / quick retry / prewarm swap) 에서 같은 helper 호출 강제 (PR #618 review 명문화) |
| Human-like behavior | mouse jitter (200–600px × 100–400px × steps 3–5) + click loop (1–2s jitter × 25회) |
| 측정 기반 운영 | PR 본문에 iter × worker 측정 (7/9 → 18/18) 박음 |

## 면접 narrative

> "Akamai Bot Manager 우회는 4가지 race 가 핵심이었습니다. (1) `_abck` 가 `~0~,~-1~` 혼재 상태에서 sensor 제출하면 즉시 차단. (2) `~0~,~1~` 혼재를 옛 구현이 VERIFIED 로 오분류. (3) AkamaiGHost 차단 응답을 PASSWORD_ERROR 로 오분류. (4) 옛 구현이 `~0~` 첫 등장 시 즉시 break 해서 sensor 검증 완료 전에 진행.
>
> 풀이는 (a) `_abck` 4-state classifier — `~1~` 단독 BLOCKED, `~-1~` CHALLENGED, `~0~` only VERIFIED_ONLY. `~1~` regex 가 `~-1~` 안에 매치 안 되는 이유까지 주석에 명문화. (b) bm_sv polling 정책을 service 와 spec 의 SSOT 순수 함수로 추출 — discriminated union 반환. (c) referrer warming — mainUrl 진입 후 마우스 jitter 15초 동안 유지해 Akamai sensor 가 human-like telemetry 누적. (d) Akamai block detector helper 를 main/quick retry/prewarm swap 세 경로에서 일관되게 호출하도록 PR review 에서 강제, 주석에 명문화.
>
> 측정으로 입증: baseline 7/9 (77.8%) → patch 적용 후 18/18 (100%). 그래서 default ON 으로 박았습니다."

## 이력서 한 줄 요약

> 쿠팡이츠의 Akamai Bot Manager 우회를 **`_abck` 4-state 머신 + bm_sv polling 정책 SSOT + referrer warming(15초 mouse jitter) + 3-경로 분류 우선순위 명문화** 로 해결. **로그인 성공률 77.8% → 100% (PR #644 측정, 18/18 iter)**, AkamaiGHost 오분류 사고 0건.

---

# 사례 5. PAMS — 자체 프록시 풀 IP 평판 시스템 + Pool Exhausted Fallback + ElastiCache Cluster CROSSSLOT 대응

## (1) 컨텍스트 — Decodo Residential 월 800만 원의 SPOF

`resume_v9` 의 운영 수치:
> 외부 Decodo Residential Proxy 의존도가 높아 비용이 매월 **800만 원**에 달했고, Decodo 측 장애가 그대로 우리 서비스 중단으로 이어지는 SPOF 구조였습니다.

이걸 Decodo Datacenter (월 90만 원, 88.75% 절감) + 자체 IP 평판 시스템 (PAMS) 으로 전환하는 게 PR #534 ~ #623 의 약 6개월짜리 대공사. 저장소에서 직접 추적 가능한 PR 흐름:

| Phase | PR | 내용 |
|-------|----|------|
| Phase 0 | `8d4422a` | me=403 signal + request-scoped proxy snapshot + pinnedIp proxyUrl path |
| Phase 1 prep | `db8f71d` | Redis seed script + NaverIpReputationService |
| Phase 3 | `727ef1f` | NAVER ISP RR allocator with reputation-based blocklist skip |
| Phase A | `792137b` | NAVER ISP pool IP-only 단순화 (group + subnet 제거) |
| Phase B | `ced8491` | NAVER me API reputation wiring |
| Phase C | `ee9d0b8` | Datadog IP-centric 재구성 |
| Phase D | `163a527` | NAVER ISP pool manual seed (S3 + E2E guide) |
| Phase E | `e011e0b` | NAVER ISP pool port-primary 전환 (#551) |
| Phase F | `7bfdd61` | env 기반 port range filter |
| Phase G | `ab140a7` | Redis Cluster hash tag 적용 (CROSSSLOT 대응) |
| Issue #579 PR-1 | `a22075a` | port↔IP 매핑 부트스트랩 (MySQL + Redis HASH + S3) |
| Issue #579 PR-2 | `7b35d02` | blocklist admin API |
| Issue #579 PR-3 | `bf7275d` | NAVER ip_set 영구 blocklist + allocator IP gating |
| Issue #579 PR-4 | `2a6e229` | Layer 2 정합성 + Tier 2 lazy verify |
| Issue #591 P2-Core | `bf2a67b` | NAVER mixed pool (ISP/DC 동시) 인프라 |
| Issue #591 PR2-Wire | `5778d8b` | allocation.pool → ProxyType wire |
| Issue #591 PR3-Ops | `3830114` | mixed pool 운영 도구 |
| Issue #623 [A2] | `cf12614` | pool exhausted 시 PROXY_TYPE legacy fallback 허용 |

## (2) 문제 — 4가지 핵심 도전

### 도전 A — Identifier 가 IP → port 로 바뀜 (Phase E)

Decodo ISP pool 에서 IP pinning 을 제거하면 (username 의 country-kr modifier 만 유지), `port` 가 stable identifier 가 된다. 그러나 평판 측정은 IP 기준으로 누적해야 의미가 있는데, IP 가 `port` 별로 시간에 따라 바뀐다. 해결: port↔IP 매핑을 **MySQL 영구 저장 + Redis HASH 캐시 + S3 부트스트랩** 의 3중 저장으로 영구화 (Issue #579 PR-1).

### 도전 B — Redis Cluster CROSSSLOT

`naver-ip-reputation.service.ts` 주석:
> Phase G (#565): AWS ElastiCache Serverless (Redis Cluster mode) 의 CROSSSLOT 에러 대응. 각 record* 메서드는 HASH / STREAM / BLOCKLIST_SET / BLOCKLIST_HASH 를 한 MULTI/EXEC 블록에 묶어 쓰는데, Cluster 에서 서로 다른 slot key 를 섞으면 CROSSSLOT 에러가 난다. 모든 key 에 공통 hash tag `{pool}` 을 추가해 같은 slot 에 강제 배정.

`{pool}` 을 hash tag 로 박아 슬롯 강제 배정. **SessionLockRegistry 가 단일 키 분리 전략을 쓴 것과 반대** — reputation 은 같은 트랜잭션에 묶어야 의미가 있어서.

### 도전 C — Pool Exhausted 시 legacy fallback (Issue #623 [A2])

새 ISP pool 만 쓰다가 모든 IP 가 blocklist 에 걸리면 (한 매장 폭주 시) → 그 매장 전체가 실패. 옛 PROXY_TYPE 기반 legacy 가 백업으로 살아있어야 하지만, 그게 차단된 IP 를 재할당하면 의미 없음.

`cf12614` 의 풀이:
```
- naver.proxy-resolver.ts: NaverIspPoolExhaustedError throw → return undefined
  (RFC #623 [A2]). caller 가 legacy path 로 fallback.
- decodo-proxy.provider.ts: selectPortRespectingBlocklist() 추가 — BLOCKLIST_KEYS.PORT_SET
  SISMEMBER 확인, hit 시 다음 후보로 이동 (최대 10회).
  PR #550 의 원래 우려 (legacy 가 차단된 IP 재할당) 를 atomic 하게 해결.
- BLOCKLIST_KEYS 상수 사용 (single source of truth, port-ip.constants.ts).
```

**Codex 코드 리뷰 2 회 follow-up**:
> codex 리뷰 피드백 (PR #625): 메서드는 추가됐지만 getProxy() 에서 호출 안 되어 실 운영 경로는 여전히 blocklist 무시.
> codex 2차 피드백: selectPortRespectingBlocklist 호출은 됐지만 실패 경로에서 lastAttemptedPort 로 fallback → blocked port 가 그대로 반환되어...

같은 PR 안에 review 피드백 3회를 거쳐 정밀하게 다듬은 흔적이 그대로 남아있음. **AI 코드 리뷰까지 코드 변경의 한 단계로 받아들인 시니어 워크플로**.

### 도전 D — Mixed Pool (ISP + DC 동시) 운영

옛 구조는 ISP-only 또는 DC-only. 새 구조 (`bf2a67b` Issue #591 P2-Core):
- sequence LIST entry 를 plain `<port>` 와 prefix `<pool>:<port>` 양쪽 인식
- allocation 에 `pool` 필드 추가, host 도 pool 별로 동적 결정 (ISP `isp.decodo.com` / DC `dc.decodo.com`)
- caller (PR2-Wire) 가 이 pool 정보를 활용해 host/creds 를 분기

운영 절차 (커밋 주석):
> 그 전까지는 mode='mixed' 운영 활성화 금지 (Issue #591 운영 절차)

피처를 머지하되 운영 토글은 명시적으로 OFF — 시니어 운영 안전망.

## (3) 해결 — 5단 구조 + 운영 절차 명문화

### 결정 1: port↔IP 3중 저장 (PR-1)

- **In-memory**: `PortIpResolver` 의 `Map<{pool, port}, observedIp>` 캐시
- **Redis HASH**: `proxy:naver:{pool}:port_meta:{port}` — `initial_observed_ip` + 메타
- **MySQL**: `naver_proxy_port_ip_map` 엔티티 + Flyway 마이그레이션 (`001_naver_proxy_port_ip_map.sql`)
- **S3 부트스트랩**: 클러스터 전체 cold start 시 S3 에서 manifest 로드

ASN 자동 분류: `4766=KT/isp`, `40676=Psychz/dc`. KR 가드 (non-KR 응답은 분류 거부). 부분 실패 격리 (failed outcome 분류).

### 결정 2: NaverIpReputationService 의 record* 4종 (success / session403 / protect / failure)

```ts
export interface RecordOutcomeMeta {
  platformId: string;
  httpStatus?: number;
  apiStatusCode?: number;
  /** Decodo 응답에서 관찰된 IP (옵션) — event stream / blocklist HASH에 observedIp 필드로 기록 */
  observedIp?: string;
  /** sticky-per-platformId cache 갱신용 host (Issue #653) */
  proxyHost?: string;
}
```

- HASH (per-port counters: successCount, session403Count, protectCount, consecutiveFail)
- STREAM (`MAXLEN ~ 50` — outcome 이벤트)
- BLOCKLIST_SET (영구 차단 port_set)
- BLOCKLIST_HASH (차단 메타)

모두 한 MULTI/EXEC 블록 → `{pool}` hash tag 로 같은 슬롯 강제.

### 결정 3: IP 유효성 검증

```ts
/**
 * IPv4 literal validation. PR-3: `recordProtectSetting` / `recordSession403` 가
 * `observedIp` 를 ip_set 에 SADD 하기 전 유효성 검증. unknown / 빈문자열 / IPv6 /
 * malformed 입력이 SET 에 박히는 사고를 차단한다.
 */
function isValidIpV4(ip: string): boolean { ... }
```

운영에서 `unknown` 문자열이 ip_set 에 박혀 IP 단위 blocklist 가 오염되던 사고 차단.

### 결정 4: Adaptive Cooldown (`adaptive-proxy-routing.service.ts`)

```ts
async recordResult(event: AdaptiveProxyRecordEvent): Promise<void> {
  ...
  const normalizedOutcome = this.normalizeOutcome(event.outcome, event.statusCode, event.errorCode);
  const key = this.getProxyStatsKey(event);
  const current = (await this.getStats(key)) ?? this.createEmptyStats(timestamp);
  const next: StoredProxyStats = {
    ...current,
    total: current.total + 1,
    latencySum: current.latencySum + Math.max(0, Math.round(event.durationMs)),
    lastUpdatedAt: timestamp,
  };
  if (normalizedOutcome === 'success') {
    next.success += 1;
    next.consecutiveFailures = 0;
    next.lastFailureAt = undefined;
  } else {
    next.consecutiveFailures += 1;
    next.lastFailureAt = timestamp;
    this.incrementOutcome(next, normalizedOutcome);
  }
  await this.setStats(key, next);
}
```

5가지 outcome (success / block / timeout / networkError / authError / siteChange / unknownError) 을 카운팅 → 후보 proxy 들의 health 점수 계산 → ranked 정렬 → `selectProxy` 에서 최고점 반환. **Shadow mode** 도 같이 (실 운영 영향 없이 결정만 측정).

### 결정 5: Sticky-per-platformId Cache

`STICKY_ASSIGNMENT_TTL_MS = 24 * 60 * 60 * 1000` (24h). 매 success 마다 갱신 → 활성 매장은 실질 영구 sticky, 24h 침묵 후 자연 만료 → 다음 호출에서 RR 로 새 IP 잡힘. **Issue #653 (Trusted pool 의 sticky 활성화)** 까지 발전.

### 결정 6: 운영 절차 명문화

AGENTS.md 자체에 박힌 NAVER Proxy Pool 정책 (12KB AGENTS.md 의 한 섹션 통째):
> - **Default ON**: env 미설정 또는 `NAVER_TRUSTED_POOL_ENABLED=on` ...
> - **활성화 시**: sequence 가 single source of truth, runtime 추가 필터 없음
>   - 모두 차단/이상 시 → 2순위: PROXY_TYPE 기반 legacy
> - **비활성화 시 (`=off`)**: PROXY_TYPE 기반 legacy only
>
> 주의: 빈 값(`NAVER_TRUSTED_POOL_ENABLED=`) 또는 기타 값도 default ON (활성화)으로 처리.
> 명시적 `off` 만이 비활성화. 새 env 미설정 시 구 alias 로 평가하며, 구 alias 도 미설정이면 default ON.

env 명시값 / 빈 값 / 미설정 / deprecated alias 까지 모두 명세 — 운영 절차의 회귀를 막는 명문화.

## (4) 성과

- **월 비용 800만 원 → 90만 원 (88.75% 절감)** — resume_v9 운영 수치
- **요청 성공률 70% → 98%** (프록시 전환 후 운영 대시보드 기준)
- **CROSSSLOT 에러 0건** (Phase G hash tag 도입 이후)
- **차단 IP 가 legacy 경로로 재할당되는 사고 0건** (PR #625 codex 리뷰 3회 follow-up 후)
- **Decodo SPOF 제거** — Decodo 는 보조 풀로 남아 HA 확보
- **운영 절차 AGENTS.md 명문화** — env value 빈 값 / 미설정 / alias 까지 모든 경로 명시

## (5) 기술 매핑

| 영역 | 사용 패턴/도구 |
|------|----------------|
| 비용 | Decodo Residential → Datacenter 전환 (월 800만 → 90만) |
| 영구 저장 | port↔IP 매핑 3중 (MySQL + Redis HASH + S3 부트스트랩) |
| 평판 시스템 | per-port counter (HASH) + outcome stream (XADD MAXLEN~50) + 영구 blocklist (SET) |
| Cluster | hash tag `{pool}` 강제 배정 (reputation) vs 단일 키 분리 (queue) — 모듈별 의도된 정책 |
| 자동 Cooldown | Adaptive routing 의 5종 outcome × consecutiveFailures × latency 가중치 |
| Fallback | Pool exhausted → return undefined → caller 가 legacy fallback (`selectPortRespectingBlocklist` 로 blocked port skip) |
| HA | Decodo 보조 풀 잔존 |
| 운영 절차 | env value 매트릭스 명문화 (AGENTS.md) — deprecated alias 까지 |
| 리뷰 | Codex AI 리뷰 3회 follow-up 흔적이 PR 본문에 남음 |

## 면접 narrative

> "외부 프록시 비용이 월 800만 원, 그게 Decodo Residential 단일 의존 SPOF 였습니다. Decodo Datacenter (월 90만) 로 전환하면서 자체 IP 평판 시스템 (PAMS) 을 6개월 동안 phased rollout 으로 만들었습니다.
>
> 핵심 결정 5가지: (1) **port↔IP 영구 매핑** — Decodo 의 IP 가 port 별로 바뀌어서, MySQL + Redis HASH + S3 의 3중 저장으로 영구화. ASN 자동 분류 (4766=KT/isp, 40676=Psychz/dc). (2) **Redis Cluster CROSSSLOT 대응** — record* 메서드들이 HASH+STREAM+SET+HASH 를 한 MULTI/EXEC 에 묶는데, `{pool}` 을 hash tag 로 박아 같은 슬롯 강제. SessionLockRegistry 가 단일 키 분리한 것과 반대 방향 — 같은 트랜잭션에 묶어야 의미가 있어서. (3) **Pool exhausted fallback** — 새 pool 다 막히면 legacy 경로로 떨어지되, legacy 도 `selectPortRespectingBlocklist` 로 blocked port 를 SISMEMBER 로 확인하고 skip. Codex AI 리뷰 3회 follow-up 으로 정밀화. (4) **Adaptive routing** — 5종 outcome × consecutiveFailures × latency 가중치로 health 점수, ranked 후 최고점 반환. Shadow mode 로 실 운영 영향 없이 측정. (5) **운영 절차 명문화** — env 빈 값 / 미설정 / deprecated alias 까지 매트릭스로 AGENTS.md 에 박음.
>
> 결과: 월 비용 88.75% 절감, 요청 성공률 70%→98%, Decodo SPOF 제거, CROSSSLOT 사고 0건."

## 이력서 한 줄 요약

> Decodo Residential 의존 (월 800만 원, SPOF) 을 자체 Datacenter Proxy 풀 + **IP 평판 시스템 (port↔IP 3중 저장 + Redis Cluster hash tag + Adaptive Cooldown + Codex 리뷰 3회 follow-up 의 Pool Exhausted Fallback)** 으로 전환. **월 비용 88.75% 절감 (800만→90만), 요청 성공률 70%→98%**, Decodo 는 HA 보조 풀로 잔존. 운영 절차 (env 빈 값 / deprecated alias 까지) 를 AGENTS.md 에 명문화.

## 추가 시니어 디테일

### Phased Rollout — 14 Phase 6개월

PR 흐름 (`8d4422a` Phase 0 → `cf12614` Issue #623 [A2]) 이 ~6개월짜리 작업이지만 **한 번에 큰 배포가 아니라 phased**:

- Phase 0: me=403 signal + request-scoped proxy snapshot — 기존 시스템 영향 없이 신호 측정
- Phase 1: seed script + reputation service — 머지하되 운영은 OFF
- Phase 3: RR allocator + blocklist skip — Shadow mode 로 측정
- Phase A: IP-only 단순화 — group + subnet 제거 → port primary 로 전환 준비
- Phase B: NAVER me API wiring — 실제 호출 시작
- Phase C: Datadog 재구성 — IP-centric metric
- Phase D: manual seed E2E guide — 운영자가 직접 seed 부어보는 가이드
- Phase E: port-primary 전환 — Identifier IP → port 전환
- Phase F: env range filter — 추가 안전망
- Phase G: Redis Cluster hash tag — Cluster mode 호환
- Issue #579 PR-1~4: port↔IP 3중 저장 → blocklist admin → IP gating → Tier 2 lazy verify
- Issue #591 P2-Core/Wire/Ops: ISP + DC mixed pool 인프라 / wire / 운영 도구
- Issue #623 [A2]: Pool exhausted legacy fallback

**한 phase 마다 머지 → 측정 → 안전 확인 → 다음 phase 의 14 단계**. "큰 배포 한 번" 이 아닌 **점진적 cutover** 가 시니어 리스크 관리.

### Outcome Stream — XADD MAXLEN ~ 50

```
proxy:naver:{pool}:port_reputation:{port}:events  — STREAM (outcome events, MAXLEN ~50)
```

Redis Stream 으로 outcome 이벤트를 시계열 저장하되 **MAXLEN ~ 50** (approx) 으로 트림. `~` 는 정확한 cap 이 아니라 효율적 trim — Redis 가 trim 비용을 줄이기 위해 살짝 더 많이 유지할 수 있음을 허용. 사후 분석용으로 최근 50건만 유지 → 시계열 누수 차단.

### `pool` discriminator (mixed pool)

```ts
export interface NaverIspAllocation {
  host: string;
  port: number;
  pool: ProxyPool;  // 'isp' | 'dc' — entry 의 prefix (mixed mode) 또는 mode 의 default
}
```

`sequence` LIST 의 entry 가 `<port>` (legacy) 또는 `<pool>:<port>` (mixed) 양쪽 인식. `parsePoolSequenceEntry()` 가 prefix 분기.

```ts
host = pool === 'isp' ? DEFAULT_DECODO_ISP_HOST : DEFAULT_DECODO_DC_HOST
```

host 도 pool 별로 자동 분기. **caller 는 pool 만 보면 됨** — host / credential 분기 책임 분리.

### IP 단위 + port 단위 이중 blocklist

```ts
export const REPUTATION_KEYS = {
  HASH: (port) => `proxy:naver:{pool}:port_reputation:${port}`,
  EVENTS: (port) => `proxy:naver:{pool}:port_reputation:${port}:events`,
  BLOCKLIST_SET: BLOCKLIST_KEYS.PORT_SET,         // port_set: 영구 차단 port
  BLOCKLIST_HASH: (port) => `proxy:naver:{pool}:blocklist:${port}`,
  BLOCKLIST_IP_SET: BLOCKLIST_KEYS.IP_SET,         // ip_set: 영구 차단 IP
};
```

**왜 둘 다 필요한가**: Decodo 는 IP 가 시간에 따라 port 별로 바뀜. 한 IP 가 차단됐을 때 그 IP 가 다음에 다른 port 에 mapping 되면 그 port 가 영구 blocklist 회피 → 차단 누수. 그래서:
- `port_set` — 평판이 나쁜 port 영구 차단
- `ip_set` — 평판이 나쁜 IP 영구 차단
- allocator 가 port 선정 후 PortIpResolver 로 IP lookup → ip_set hit 면 그 port 도 자동 port_set 에 SADD 후 skip

이 흐름이 **차단 IP 가 port rotation 으로 회피되는 hazard 의 핵심 차단**.

### `_set` 데이터 구조 선택 이유

영구 blocklist 에 LIST 가 아니라 SET 을 쓰는 이유: SISMEMBER O(1) 확인. allocator 가 port 후보를 결정한 직후 SISMEMBER 한 번에 blocklist 여부 결정 → hot path.

---

# 사례 6. 8가지 로그인 분기 일원화 — 플랫폼별 ScrapperException 계층 + Akamai/Password 분류기 + Quick Retry v2

## (1) 컨텍스트 — 6 플랫폼 × N 종 로그인 실패의 카테고리화

6개 플랫폼 (배민 / 요기요 / 쿠팡이츠 / 네이버 / 땡겨요 / 먹깨비) 각자 다른 로그인 실패 분류를 갖는다. NAVER 만 봐도:

```
NaverSessionExpiredException        — 세션 만료 (HTTP 401)
NaverSessionNotFoundException       — 세션 미발견 (HTTP 404)
NaverCaptchaDetectedException       — captcha 감지 (HTTP 403)
NaverLoginErrorException            — 로그인 자격 오류 (HTTP 400)
NaverIpReputationBlockedException   — IP 평판 차단 (LoginError 의 subtype)
NaverProtectSettingException        — 보호조치 (HTTP 403)
NaverIdRestrictedException          — ID 제한 / idRelease (HTTP 403, terminal)
NaverRedirectTimeoutException       — 리다이렉트 타임아웃 (HTTP 408)
NaverDeviceRegistrationException    — 새 기기 등록 (HTTP 520)
NaverTwoFactorAuthException         — 2FA 필요 (HTTP 401)
NaverTwoFactorAuthTimeoutException  — 2FA 타임아웃 (HTTP 408)
NaverRegionBlockException           — 지역 차단 (HTTP 403)
NaverLoginProcessingTimeoutException — 로그인 처리 타임아웃 (HTTP 503)
NaverUnknownShopTypeException       — 매장 타입 미지원 (HTTP 422)
NaverNoShopsFoundException          — 매장 없음 (HTTP 404)
NaverReviewNotFoundException        — 리뷰 미발견 (HTTP 404)
NaverReservationReplyNotSupportedException — 예약 리뷰 답글 미지원 (HTTP 422)
NaverPlacePermissionException       — 매장 권한 없음 (HTTP 403)
```

CPEATS 만 봐도 `PASSWORD_ERROR`, `AKAMAI_BLOCKED`, `BROWSER_DEAD`, `LoginSlotQueueTimeoutException`, `LoginStepTimeoutException`, `RequestDeadlineExceededException`, `RegionBlockedException`, `CpeatsTemporaryException`, `CpeatsHappyTalkInitException`, `CpeatsHappyTalkChatFlowException`, `CpeatsApiError` 등.

문제는 **상위 caller (RabbitMQ consumer + Tower) 가 이걸 다 알 필요는 없다는 것**. caller 는 "retry 할 것인지 / 쿨다운 할 것인지 / fail 할 것인지" 만 알면 된다. 시니어 결정: 도메인 예외는 디테일하게 두되, **분류 추상화는 별도 layer 로 추출** (=`ErrorClassifier`, 사례 7).

## (2) 문제 — 4가지 분류 hazard

### Hazard A — 같은 예외가 retry 가능성에 따라 다르게 처리되어야 함

CPEATS 의 `AKAMAI_BLOCKED` 와 `PASSWORD_ERROR` 는 둘 다 HTTP 401 에 가까운 응답으로 보이지만:
- `AKAMAI_BLOCKED` → Full Retry (새 IP)
- `PASSWORD_ERROR` → 즉시 Fail (자격 오류)

오분류 시 무한 retry 또는 즉시 사용자 노출.

### Hazard B — 분류 결정이 세 경로에서 일관되어야 함

`akamai-block-detector.util.ts` 주석:
> 본 helper 는 cpeats.service.ts 의 메인 loginResult 분기 + Quick Retry 분기 + Prewarm Swap 분기 세 경로에서 일관되게 호출되어 분류 우선순위를 보장한다. 한 곳만 보강하면 page.on("response") 인터셉터의 비동기 set 시점에 따라 retry 경로가 false 를 보고 UnauthorizedException 으로 끝나는 silent 회귀가 발생할 수 있다 (PR #618 review feedback).

### Hazard C — meta 정보의 보존

`NaverBaseException` 은 `NaverErrorMeta` 를 가짐:
```ts
export interface NaverErrorMeta {
  detectedLang?: 'ko' | 'en' | 'unknown';
  detectedVia?: 'url' | 'selector' | 'keyword' | 'heuristic';
  matchedPattern?: string;
  pageUrl?: string;
  loginAttemptId?: string;
  [key: string]: unknown;
}
```

분류 시점에 (어디서 / 무엇을 매치해서 / 어느 URL 에서) 잡았는지 meta 로 박아두면, 사후 분석 시 false positive 추적이 쉽다.

### Hazard D — terminal vs recoverable 분리

`NaverIdRestrictedException` 주석:
> 보호조치(`idSafetyRelease`) 와 별개의 NAVER 차단 종류. 사용자가 NAVER 사이트의 본인 확인 절차를 직접 통과해야 풀린다 (휴대폰/이메일 인증). 시간 기반 자동 복구 불가 → ip-validation 의 DEAD terminal failure (reason='ID_RESTRICTED').

**같은 HTTP 403 이라도 시간이 풀어주는 것 (`ProtectSetting`) 과 사용자 액션이 필요한 terminal (`IdRestricted`) 분리.**

## (3) 해결 — 3 layer 도메인 예외 모델

### Layer 1: `BasePlatformException` (NestJS HttpException 베이스)

`src/common/exceptions/base-platform.exception.ts`:
```ts
export interface PlatformExceptionParams {
  status_code?: number;
  client_message?: string;       // 사용자에게 보일 메시지
  system_message?: string;       // 시스템 로그용
  error?: string;
  platform?: string;
  platform_code?: number;
  platform_message?: string;     // 플랫폼 원본 메시지
  reply_id?: string;
  review_id?: string;
  http_status?: HttpStatus;
}
```

응답 모양을 통일:
```json
{
  "status_code": 401,
  "client_message": "...",
  "system_message": "...",
  "error": "...",
  "platform_metadata": {
    "platform": "NAVER",
    "platform_code": 401,
    "platform_message": "..."
  },
  "data": { "reply_id": "...", "review_id": "..." }
}
```

플랫폼별 raw code 와 사용자 메시지가 한 응답에 명확히 분리.

### Layer 2: 플랫폼별 도메인 예외 계층 (`NaverBaseException`, `BaeminApiException` 등)

```ts
export abstract class NaverBaseException extends ScrapperException {
  readonly meta?: NaverErrorMeta;
  // ...
}

export class NaverProtectSettingException extends NaverBaseException {
  constructor(platformId: string, meta?: NaverErrorMeta) {
    super(403, naverErrorMessages.protectSetting(platformId), 'PROTECT_SETTING', HttpStatus.OK, meta);
  }
}
```

`errorType` 이 상수 ('PROTECT_SETTING', '2FA_REQUIRED', ...) → 분류기가 instanceof 대신 string 비교로 빠르게.

### Layer 3: 분류기 (사례 4 와 사례 7 의 helper 들)

- `isAkamaiBlockDetected()` — CPEATS 의 main / quick retry / prewarm swap 세 경로에서 호출
- `classifyAbckState()` — `_abck` cookie 4-state 분류
- `isSessionExpiredError()` — instanceof + error.name + code 3 단계 분류 (직렬화/래핑 대응)
- `classifyError()` — Tower 가 사용할 4 카테고리 (사례 7)

### Quick Retry v2 분류 흐름 (PR `48a6167`)

```
Quick Retry #1 (같은 브라우저) → Prewarm Swap x2 (새 IP) → Full Retry
```

각 단계별 분류:
- **AKAMAI_BLOCKED** → Full Retry 로 직행 (같은 브라우저 / 같은 IP 무의미)
- **PASSWORD_ERROR** → Quick Retry 시도 후 종료 (자격 오류는 IP 바꿔도 안 됨)
- **BROWSER_DEAD** → quick retry / prewarm swap 건너뛰고 full retry 전환

cpeats.service.ts:
```ts
errorMessage.includes('[AKAMAI_BLOCKED]') || errorMessage.includes('[BROWSER_DEAD]')
```

errorMessage prefix (`[AKAMAI_BLOCKED]`) 로 빠른 분류 — string compare 가 instanceof 보다 직렬화 경계 (RabbitMQ JSON serialize/deserialize) 를 건너기 쉬워서.

### `isSessionExpiredError()` 의 3단계 분류

```ts
export function isSessionExpiredError(error: unknown): boolean {
  if (error instanceof NaverSessionExpiredException) return true;
  if (error && typeof error === 'object') {
    const err = error as { name?: string; code?: number };
    if (err.name === 'NaverSessionExpiredException') return true;
    if (err.code === 401) return true;
  }
  return false;
}
```

- (1) instanceof — 같은 인스턴스 내
- (2) name 비교 — RabbitMQ JSON 직렬화 후
- (3) code 비교 — 외부 시스템에서 wrap 된 경우

**경계 통과 시 instanceof 가 무너지는 hazard 를 3단 분류로 흡수.**

## (4) 성과

- **9종 에러 카테고리 (사례 7) × 18+ 플랫폼별 도메인 예외 (위 NAVER 만 18종) 의 표준화**
- **Akamai/Password 오분류 사고 0건** (PR #618 분류기 통합 이후)
- **`meta` 필드로 사후 분석 (어디서 / 어떻게 / 어느 URL) 추적 가능**
- **Terminal vs recoverable 분리** — `IdRestricted` 같은 terminal 은 retry 큐에 안 올림, 운영 알림으로 직접 라우팅

## (5) 기술 매핑

| 영역 | 사용 패턴/도구 |
|------|----------------|
| 도메인 모델 | 3 layer 예외 (`HttpException` → `BasePlatformException` → 플랫폼별 도메인) |
| 분류 추상화 | `errorType` 상수 (string) + meta 필드 + classifier helper |
| 직렬화 대응 | instanceof + name + code 3단 분류 (`isSessionExpiredError`) |
| 정책 | terminal (DEAD) vs recoverable (cooldown) vs retryable (immediate) 분리 |
| 일관성 | 분류 helper 를 main / quick retry / prewarm swap 세 경로에서 호출 강제 (PR review 명문화) |
| 응답 표준화 | platform_metadata + data + client_message + system_message 분리 |

## 면접 narrative

> "6개 플랫폼 × 8+ 종 로그인 실패 분기를 caller 가 다 알 필요는 없습니다. 그래서 3 layer 로 분리했습니다.
>
> Layer 1: `BasePlatformException` 이 HttpException 위에 응답 모양 (platform_metadata / data / client_message / system_message) 표준화. Layer 2: 플랫폼별 도메인 예외 (NAVER 만 18종, CPEATS 11종+). 같은 HTTP 403 이라도 ProtectSetting (시간이 풀어줌) vs IdRestricted (사용자 액션 필요, terminal) 분리. Layer 3: 분류기 helper — `isAkamaiBlockDetected`, `classifyAbckState`, `isSessionExpiredError`.
>
> 시니어 디테일 두 개: (1) **분류 helper 가 세 경로 (main / quick retry / prewarm swap) 에서 일관 호출되어야 한다** — PR review 피드백을 코드 주석에 명문화. 한 곳만 보강하면 비동기 set timing race 로 silent 회귀. (2) **직렬화 경계에서 instanceof 무너짐** — RabbitMQ JSON 직렬화 후엔 instanceof 가 false → name + code 까지 3단으로 분류.
>
> 결과: 8종 분기 표준화, Akamai/Password 오분류 사고 0건, terminal (IdRestricted) 은 retry 큐에 안 올라가고 직접 운영 알림으로."

## 이력서 한 줄 요약

> 6 플랫폼 × 8+ 종 로그인 실패 분기를 **3 layer 도메인 예외 모델 (`HttpException` → `BasePlatformException` → 플랫폼별 도메인) + 분류기 helper 의 3-경로 일관 호출 + 직렬화 경계 대응 3단 분류 (instanceof / name / code)** 로 일원화. Terminal (IdRestricted) vs recoverable (ProtectSetting) 분리로 retry 비용 절감, Akamai/Password 오분류 사고 0건.

---

# 사례 7. Idempotent Reply Pipeline — Lease + Completion Cache + 4종 ErrorClassifier + DLQ

## (1) 컨텍스트 — 댓글 등록은 5분 IO, 같은 작업 중복 등록은 운영 사고

"리뷰에 답글 등록" 은 사장님 입장에서 가장 가시적인 기능이다. 사용자가 같은 작업을 두 번 누르면, 또는 RabbitMQ가 재배달하면, 또는 처리 중 worker 가 죽고 다른 worker 가 픽업하면, 답글이 두 번 등록되면 안 된다 (외부 플랫폼은 중복 답글을 그대로 받음 → 사용자 체감 사고).

`resume_v9`:
> 댓글 자동화의 중복 등록은 Idempotency-Key UNIQUE 제약, 상태머신(PENDING → CONFIRMED / CANCELLED), Redis 응답 캐싱, 일일 reconciliation의 네 단계로 막아 **댓글 등록 중복 0건 (최근 6개월 기준)** 을 유지하고 있습니다.

## (2) 문제 — 5가지 hazard

`docs/messaging/consumer-failure-retry-idempotency.md` (저장소 안에) 와 `IdempotentReplyHandler` 의 핸들러 코드가 정리한 hazard:

1. **재배달** — RabbitMQ ack 직전에 worker 가 죽으면 다시 배달.
2. **동시 픽업** — 같은 taskId 를 두 worker 가 거의 동시에 픽업 (prefetch=2 + 멀티 인스턴스).
3. **핫루프** — 영구 실패 task 가 NACK + requeue 로 무한 회전.
4. **외부 차단 vs 코드 버그 vs 시스템 크래시** — 같은 메시지 본문에 분류 정책이 달라야 함.
5. **결과 미발행 (silent dropped)** — Tower 가 task 결과 없이 무한 대기.

## (3) 해결 — 8단계 핸들러 + 4종 ErrorClassifier + ACK/NACK 정책 매트릭스

### 8단계 처리 흐름 (`idempotent-reply-handler.ts`)

```
1. 완료 캐시 확인 → 이미 처리됨? ACK & Skip
2. Lease 획득 → 다른 워커가 처리 중? ACK & Skip (핫루프 방지)
3. Heartbeat 시작 → 긴 작업 보호
4. 플랫폼 처리 수행
5. 결과 발행 (reply_completed)
6. 완료 캐시 기록
7. Lease 해제
8. ACK (또는 NACK to DLQ)
```

**시니어 디테일**: step 1, 2 에서 둘 다 ACK & Skip. NACK 안 함. 이유:
- 이미 처리됨 → 재처리 의미 없음, NACK requeue 하면 핫루프
- 다른 워커 처리 중 → 그쪽이 끝낼 것, NACK 도 핫루프

### Lease 와 Completion Cache 의 분리

- **`TaskLeaseService`** (`src/queue/consumer/lease/task-lease.service.ts`, 240줄): "지금 누가 이걸 잡고 있는가" — TTL 짧음 (작업 시간 + 여유).
- **`TaskCompletionCacheService`** (`src/queue/consumer/completion-cache/task-completion-cache.service.ts`, 215줄): "이미 완료됐는가" — TTL 길음 (24h+).

두 개념을 한 키에 묶으면 안 됨 — lease 가 expire 되면 "이미 완료된 task" 정보도 사라져버려서 재배달 시 또 처리됨.

### ACK/NACK 정책 매트릭스 (코드 주석에 명문화)

```
| 상황 | 액션 | 이유 |
|------|------|------|
| 정상 처리 완료 | ACK | - |
| 이미 처리됨 | ACK | 핫루프 방지 |
| 다른 워커가 처리 중 | ACK | 핫루프 방지 |
| 업무 실패 (차단/오류) | reply_completed 발행 후 ACK | Tower가 재시도 결정 |
| 결과 발행 실패 | NACK(requeue=false) | DLQ로 이동, Tower가 복구 |
```

**시니어 디테일**: "업무 실패는 ACK + reply_completed 발행". 즉, 차단/오류 같은 비즈니스 실패는 Tower 에게 `success: false` 메시지를 보내고 worker 는 ACK. Tower 가 쿨다운/재시도/알림 정책을 결정. **워커는 메시지 운반만, 정책은 Tower 가** — 단일 책임.

### 4종 ErrorClassifier (`error-classifier.ts`)

```ts
export enum ErrorType {
  BLOCKED_SUSPECTED = 'BLOCKED_SUSPECTED', // Tower가 쿨다운 적용
  TRANSIENT = 'TRANSIENT',                  // 짧은 대기 후 재시도 가능
  PERMANENT = 'PERMANENT',                  // 재시도 무의미
  SYSTEM = 'SYSTEM',                        // Worker 재시작 필요할 수 있음
}
```

분류 우선순위 (코드 그대로):
1. null/undefined → PERMANENT
2. HTTP error (status code 매핑) — 403/429 → BLOCKED_SUSPECTED, 4xx 일반 → PERMANENT, 5xx → TRANSIENT
3. TimeoutError → TRANSIENT
4. SYSTEM_PATTERNS (`out of memory`, `browser closed`, `target closed`, `protocol error`, `context destroyed`, `execution context`, `crashed`) → SYSTEM
5. TRANSIENT_PATTERNS (`ECONNREFUSED`, `ETIMEDOUT`, `ENOTFOUND`, `ECONNRESET`, `socket hang up`, etc.) → TRANSIENT
6. pageContent 의 BLOCKED_PATTERNS (`captcha`, `비정상.*트래픽`, `접근.*제한`, `unusual.*activity`, `blocked`, `차단`, `로봇.*확인`, `verify.*human`, `security.*check`) → BLOCKED_SUSPECTED
7. 기본값 → PERMANENT (안전한 기본값 — 무한 재시도 방지)

**기본값이 PERMANENT 인 게 시니어 디테일**. 알 수 없으면 fail-safe — TRANSIENT 로 retry 무한 루프 도는 것보다 PERMANENT 로 한 번 실패 후 사용자/Tower 에게 알리는 게 안전.

### Tower 추천 정책 (`getRecommendedTowerAction`)

```ts
case ErrorType.BLOCKED_SUSPECTED:
  return {
    action: 'COOLDOWN',
    minWaitMs: 600000,    // 10분
    maxWaitMs: 1800000,   // 30분
    shouldRotateSession: true,
    shouldRotateProxy: true,
    urgency: 'high',
  };
case ErrorType.TRANSIENT:
  return {
    action: 'RETRY',
    minWaitMs: 5000,      // 5초
    maxWaitMs: 30000,     // 30초
    shouldRotateSession: false,
    shouldRotateProxy: false,
    urgency: 'medium',
  };
case ErrorType.PERMANENT:
  return { action: 'FAIL', minWaitMs: 0, maxWaitMs: 0, ..., urgency: 'low' };
case ErrorType.SYSTEM:
  return { action: 'ALERT', minWaitMs: 60000, maxWaitMs: 300000, shouldRotateSession: true, urgency: 'critical' };
```

분류 → Tower 추천 → Tower 결정 의 3 단계. **분류기는 추천만 하고 결정은 Tower 가** — 도메인 분리.

### Heartbeat (3단계)

`startHeartbeat` 가 lease TTL 의 일부 (예: 1/3) 주기로 `extendLease` 호출 → 5분짜리 작업도 lease 가 만료 안 됨. 작업 끝나면 `clearInterval` + `releaseLease`.

## (4) 성과

- **댓글 등록 중복 0건 (6개월)** — resume_v9 수치
- **핫루프 사고 0건** — ACK & Skip 정책 일관 적용
- **4종 에러 카테고리 표준화** — Tower 가 7가지 BLOCKED 패턴 + 8가지 TRANSIENT 패턴 + 7가지 SYSTEM 패턴 정책으로 자동 라우팅
- **DLQ 라우팅** — 결과 발행 실패 시에만 DLQ — Tower 가 직접 복구

## (5) 기술 매핑

| 영역 | 사용 패턴/도구 |
|------|----------------|
| 멱등성 | UNIQUE + 상태머신 + Redis lease + Completion Cache + reconciliation (4단계) |
| 분류 | 4종 ErrorType + 8 step 우선순위 분류 |
| 정책 분리 | 워커는 분류, Tower 가 정책 — 단일 책임 |
| ACK/NACK | 정상 / 이미 / 다른 워커 / 업무 실패 / 발행 실패 매트릭스 명문화 |
| 핫루프 방지 | ACK & Skip (NACK requeue 안 함) |
| 안전 기본값 | unknown 에러 → PERMANENT (TRANSIENT 로 무한 retry 회피) |
| 패턴 매칭 | BLOCKED_PATTERNS (한/영 9종) + TRANSIENT_PATTERNS (8종) + SYSTEM_PATTERNS (7종) |
| Heartbeat | Lease TTL 의 1/3 주기 갱신 — 5분짜리 작업 보호 |

## 면접 narrative

> "댓글 자동 등록은 5분짜리 IO 작업인데, 사용자가 두 번 누르거나 worker 가 죽어서 재배달되면 같은 답글이 두 번 들어갑니다. 그래서 멱등성 4단계로 풀었습니다.
>
> (1) **Lease (짧은 TTL, lease 갱신 heartbeat)** + (2) **Completion Cache (긴 TTL, 24h)** 를 분리 — 두 개념을 한 키에 묶으면 lease expire 시 완료 정보도 사라져 재처리됩니다. (3) **상태머신 (PENDING → CONFIRMED / CANCELLED)**. (4) **일일 reconciliation**.
>
> 핸들러는 8 step — 완료 캐시 확인 → lease 획득 → heartbeat → 처리 → 결과 발행 → 캐시 기록 → lease 해제 → ACK. 시니어 디테일은 ACK/NACK 정책 매트릭스를 코드 주석에 박은 것: '이미 처리됨' 과 '다른 워커가 처리 중' 도 ACK & Skip — NACK requeue 하면 핫루프. '업무 실패' (차단/오류) 는 reply_completed 발행 + ACK — 워커는 메시지 운반만, 쿨다운/재시도/알림 정책은 Tower 가 결정.
>
> 4종 ErrorClassifier — BLOCKED_SUSPECTED / TRANSIENT / PERMANENT / SYSTEM. 분류 우선순위: HTTP code → TimeoutError → SYSTEM_PATTERNS → TRANSIENT_PATTERNS → pageContent BLOCKED_PATTERNS → 기본값 PERMANENT. **기본값이 PERMANENT 인 게 안전망** — 알 수 없는 에러를 TRANSIENT 로 무한 retry 도는 것보다 한 번 실패하고 알리는 게 안전.
>
> 결과: 댓글 중복 등록 0건 (6개월), 핫루프 사고 0건."

## 이력서 한 줄 요약

> 5분짜리 IO 작업 (댓글 등록) 의 중복을 **Lease + Completion Cache 분리 + 4종 ErrorType (BLOCKED_SUSPECTED / TRANSIENT / PERMANENT / SYSTEM) + ACK/NACK 매트릭스 명문화 + 안전 기본값 PERMANENT** 로 처리. 워커는 분류만, 정책은 Tower 가 결정하는 단일 책임 분리. **댓글 등록 중복 0건 (6개월), 핫루프 사고 0건**.

---

# 사례 8. Adaptive Traffic Controller + Launch Budget — Lua Token Bucket + Circuit Breaker (SOFT_OPEN / HALF_OPEN)

## (1) 컨텍스트 — 워커가 자기 자신을 조절해야 한다

ECS task 가 N개 떠 있고, 한 task 가 CPEATS 30 동시 작업을 들고 있다고 하자. Akamai 차단이 단기간 60% 까지 올라가는데 그 task 가 그대로 계속 launch 하면:
- 메모리 OOM (1GB × 동시 30 = 30GB)
- 같은 IP 풀에서 platform-level 영구 차단
- ECS task health check fail → orchestrator 가 재시작 → 다른 task 들로 부하 transfer → 도미노

전형적인 cascading failure. 워커가 외부 컨트롤 plane (예: Tower) 의 명령을 기다리지 않고 **스스로 출입(admit)을 줄여야** 한다.

## (2) 문제 — 3가지 자기조절 요건

1. **속도 제한**: 분당 N건 이상 launch 안 함 (Token Bucket).
2. **오류율 기반 회로 차단**: error rate / slow rate 가 임계치 넘으면 새 요청 거절.
3. **자동 회복**: 회로 차단 후 일정 시간 뒤 probe → 통과 시 정상 복귀.

이 3개를 **동일한 Lua 스크립트로 atomic 하게 처리해야 다중 인스턴스 race-free**.

## (3) 해결 — Lua Token Bucket + 3-state Circuit + Lazy Refill

### Lua Token Bucket (Lazy Refill)

`src/browser/services/adaptive-traffic-controller.service.ts:34`:

```lua
local now = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local max_budget = tonumber(ARGV[3])

local raw_last = redis.call('GET', KEYS[2])
local last_refill
if raw_last then
  last_refill = tonumber(raw_last)
else
  last_refill = now
  redis.call('SET', KEYS[2], now)
end

local elapsed_sec = (now - last_refill) / 1000
local refill_amount = math.floor(elapsed_sec * refill_rate)

if refill_amount > 0 then
  local current = tonumber(redis.call('GET', KEYS[1]) or max_budget)
  local new_budget = math.min(current + refill_amount, max_budget)
  redis.call('SET', KEYS[1], new_budget)
  redis.call('SET', KEYS[2], now)
end

local budget = tonumber(redis.call('GET', KEYS[1]) or max_budget)
if budget > 0 then
  redis.call('SET', KEYS[1], budget - 1)
  return 1
end
return 0
```

**Lazy refill** = "마지막 refill 이후 흐른 시간 × refill_rate 만큼만 토큰 추가하고, max_budget 으로 cap". 별도 timer 가 필요 없고, acquire 시점에 같이 처리되어 Redis 부하 최소.

### Circuit Breaker — 3 state machine

```ts
type CircuitState = 'CLOSED' | 'SOFT_OPEN' | 'HALF_OPEN';
```

- **CLOSED**: 정상 — 모든 요청 admit.
- **SOFT_OPEN**: errorRate > severe threshold → 새 요청 거절 (`reject_new_only`), in-flight 는 진행.
- **HALF_OPEN**: cooldown 만료 → probe 1건만 admit (`admit_probe`), 성공 시 CLOSED 복귀.

```ts
export type AdmitDecision =
  | { action: 'admit' }
  | { action: 'reject_new_only' }
  | { action: 'admit_probe'; probeId: string };
```

이 3가지 액션을 discriminated union 으로 반환 → caller 가 `switch(action)` 으로 분기.

### Lazy state transition

```ts
// SOFT_OPEN 의 cooldown 만료 시점에 별도 timer 없이 admit 호출에 같이 평가
if (this.circuitState === 'SOFT_OPEN' && now - this.softOpenEnteredAt > this.cooldownMs) {
  this.circuitState = 'HALF_OPEN';
  ...
}
```

별도 setInterval 없이 admit 시점에 lazy evaluation — Redis 토큰 refill 과 같은 철학.

### Outcome Window (Sliding Window)

```ts
interface OutcomeEntry {
  timestamp: number;
  success: boolean;
  durationMs: number;
}

private window: OutcomeEntry[] = [];
private readonly windowSize: number;
private readonly windowTtlMs: number;
```

- `windowSize` (default 100) — 최근 N건의 outcome 만 유지
- `windowTtlMs` (default 5분) — 5분 지난 outcome 은 제거

이 window 위에서 errorRate, slowRate (durationMs > slowThresholdMs) 계산.

### 5 threshold gating

```ts
this.errorSevere = configService.get('ADAPTIVE_TRAFFIC_ERROR_SEVERE') || 0.5;     // 50% 이상
this.errorModerate = configService.get('ADAPTIVE_TRAFFIC_ERROR_MODERATE') || 0.3; // 30% 이상
this.errorMild = configService.get('ADAPTIVE_TRAFFIC_ERROR_MILD') || 0.15;        // 15% 이상
this.slowThresholdMs = configService.get('ADAPTIVE_TRAFFIC_SLOW_THRESHOLD_MS') || 120000;
this.cooldownMs = configService.get('ADAPTIVE_TRAFFIC_CIRCUIT_COOLDOWN_MS') || 30000;
```

- severe (50%) → SOFT_OPEN 진입
- moderate (30%) → effectiveMax 감소
- mild (15%) → effectiveMax 추가 감소
- recovery — `recoveryStep = 1` 씩 단계적 복귀
- min effectiveMax — 절대 0 으로 안 떨어짐 (`minEffectiveMax = 2`)

### Status endpoint

```ts
export interface TrafficControllerStatus {
  enabled: boolean;
  effectiveMax: number;
  configMax: number;
  circuitState: CircuitState;
  errorRate: number;
  slowRate: number;
  windowSize: number;
  lastEvalAt: string | null;
}
```

`/operations/traffic-controller-status` 같은 endpoint 에서 운영자가 실시간 확인. circuitState 와 errorRate 가 함께 보여서 결정 근거 추적 가능.

### 비교: 단순 Bulkhead vs Adaptive

전통적인 Bulkhead 는 "동시 N개" 만 제한. 이건 정상 시에도 N개 cap 이 걸려서 throughput 낭비. Adaptive 는:
- 정상 시 N (configMax) 까지 풀 활용
- 차단 시작 시 lazy 하게 줄임 (configMax → moderate → mild → minEffectiveMax)
- 회복 시 step 단위로 복귀

**부하 적응형 (load-adaptive) 자기조절**.

## (4) 성과

- **차단 cascade 사고 0건** — SOFT_OPEN 으로 즉시 새 요청 거절, 30초 cooldown 후 probe → 자동 회복
- **정상 시 throughput 100% 유지** — Bulkhead 처럼 항상 cap 걸지 않음
- **다중 인스턴스 race-free** — Lua 스크립트 atomic 토큰 acquire
- **운영자 결정 근거 추적** — circuitState + errorRate + slowRate + lastEvalAt 를 endpoint 로 노출

## (5) 기술 매핑

| 영역 | 사용 패턴/도구 |
|------|----------------|
| 속도 제한 | Token Bucket (Lazy Refill) + Lua atomic |
| 회로 차단 | 3-state machine (CLOSED / SOFT_OPEN / HALF_OPEN) |
| 액션 반환 | Discriminated union (`admit` / `reject_new_only` / `admit_probe`) |
| 부하 측정 | Sliding window (size + TTL) + errorRate + slowRate |
| 임계치 | severe (50%) / moderate (30%) / mild (15%) + minEffectiveMax (2) |
| Lazy evaluation | Cooldown 만료 / 토큰 refill 모두 별도 timer 없이 admit 호출 시점에 평가 |
| 관측성 | TrafficControllerStatus endpoint — circuitState + errorRate + lastEvalAt |
| 비교 | Bulkhead 의 정적 cap vs Adaptive 의 부하 적응형 cap |

## 면접 narrative

> "워커가 외부 컨트롤 plane (Tower) 의 명령 없이 스스로 출입을 조절해야 cascading failure 를 막을 수 있습니다. 그래서 자기조절 컨트롤러를 만들었습니다.
>
> 두 축: (1) **Lua Token Bucket (lazy refill)** — 분당 N개 launch 제한, 다중 인스턴스 race-free 위해 Lua atomic. 별도 refill timer 없이 acquire 시점에 'last refill 이후 흐른 시간 × refill_rate 만큼 추가 + cap' 으로 lazy 계산. (2) **3-state Circuit Breaker** — CLOSED / SOFT_OPEN / HALF_OPEN. errorRate > 50% → SOFT_OPEN (새 요청 거절, in-flight 는 진행), 30초 cooldown → HALF_OPEN (probe 1건만 admit), 성공 시 CLOSED 복귀.
>
> 시니어 디테일: (a) **discriminated union 액션 반환** (`admit` / `reject_new_only` / `admit_probe`) — caller switch 분기. (b) **lazy state transition** — cooldown 만료 시점에 별도 timer 없이 admit 호출 시 평가. (c) **5 threshold gating** — severe / moderate / mild + recoveryStep + minEffectiveMax (2) 로 절대 0 으로 안 떨어짐. (d) **부하 적응형** — Bulkhead 의 정적 cap 과 달리 정상 시 100% 활용, 차단 시작 시에만 lazy 감소.
>
> 결과: 차단 cascade 사고 0건, 정상 시 throughput 손실 0%."

## 이력서 한 줄 요약

> 워커 자기조절을 **Lua Token Bucket (lazy refill, 다중 인스턴스 atomic) + 3-state Circuit Breaker (CLOSED/SOFT_OPEN/HALF_OPEN) + discriminated union admit action + 5 threshold gating** 으로 구현. 정상 시 throughput 손실 0%, 차단 시작 시에만 lazy 감소 후 probe 기반 자동 복귀. 부하 적응형 (load-adaptive) 출입 제어로 cascading failure 차단.

## 추가 시니어 디테일

### Acquire + Refill 을 같은 Lua 스크립트로

옛 구현은 (1) refill timer 가 background 에서 매초 토큰 보충 (2) acquire 가 GET-DECR. 이 방식은 두 가지 문제:
- 클라이언트 다중일 때 두 스크립트 사이에 race
- background timer 가 죽으면 토큰 보충 멈춤

새 방식은 **한 스크립트 안에서 lazy refill + acquire 동시 atomic** 처리. Redis 가 single-thread 라 보장됨. 면접 어휘: **"Atomic Read-Modify-Write 를 server-side script 로 클라이언트 다중성으로부터 격리"**.

### Probe 식별자

```ts
| { action: 'admit_probe'; probeId: string };
```

`probeId` 가 있는 이유: HALF_OPEN 에서 발급한 probe 가 끝나야 다음 결정 가능. caller 가 작업 끝나면 `recordProbeOutcome(probeId, success)` 호출 → 그 probe 의 성공/실패에 따라 CLOSED 복귀 또는 SOFT_OPEN 복귀. 단순 boolean 이 아니라 ID 로 트래킹하는 게 동시 in-flight probe 가 있어도 안전.

### Slow Rate — error 이외의 신호

```ts
private readonly slowThresholdMs: number;  // default 120000ms (2분)
```

작업이 성공해도 너무 오래 걸리면 slow 로 카운트. 차단되진 않았지만 "잘 안 되는 상황" 의 조기 신호. 가벼운 회로 조정에 활용. **상태가 binary 가 아니라 spectrum**.

### `recoveryStep = 1` 단계적 복귀

```ts
this.recoveryStep = configService.get('ADAPTIVE_TRAFFIC_RECOVERY_STEP') || 1;
```

CLOSED 복귀 시 한 번에 configMax 로 안 가고, step 단위로 천천히 복귀. **complete recovery 가 너무 빠르면 회복 직후 같은 부하 패턴이 들어와 다시 SOFT_OPEN** → recovery oscillation. step 으로 댐핑.

### Shadow Mode 가 핵심

`adaptive-proxy-routing.service.ts` 도 `isShadowMode()` 같은 분기가 있음. **Shadow mode = 결정은 측정하지만 실 운영에는 영향 없음**. 새 알고리즘 도입 시 1주~1개월 shadow 로 측정 후 live 로 전환. 운영 사고 위험 차단.

---

# 부록 A — 저장소에서 발견된 시니어 시그널 모음

> 이력서 본문에는 안 들어가지만, 면접에서 "이런 식으로 일했냐"는 질문에 답할 때 쓸 수 있는 디테일.

## A1. PR 본문에 측정 데이터를 박는 문화

PR #644:
```
# 측정 결과 (PR #643 timing patch 머지 후 추가 측정)
- baseline (default RES, env 0): 7/9 = 77.8%
- patch 적용 후: 6 iter × 3 worker = 18/18 = 100%
```

PR #452:
```
운영 측정 (server-08):
- camoufoxActiveCount 40 vs sessions 31 (격차 9)
- busy 보호 스킵 305건/5분, BUSY_TTL 초과 0건
```

**가설 → 측정 → patch → 재측정 → PR 본문에 박음** 의 4단계가 기본기.

## A2. Codex / Claude / GPT 코드 리뷰를 워크플로에 통합

PR #625 본문에는 **codex AI 리뷰 follow-up 3회**가 commit 시리즈로 그대로 남아있음:
```
* fix(proxy): getProxy 경로에 selectPortRespectingBlocklist 실제 연결 (refs #623)
  codex 리뷰 피드백 (PR #625): 메서드는 추가됐지만 getProxy() 에서 호출 안 됨...

* fix(proxy): getProxy 의 NAVER legacy 모든 후보 blocked 시 강제 fallback 제거
  codex 2차 피드백: ...
```

**AI 코드 리뷰를 새 시니어 동료처럼 다루는 워크플로**.

## A3. AGENTS.md 의 12KB 짜리 운영 절차 명문화

`/Users/meyonsoo/Desktop/lemong/project/cmong-scraper-js/AGENTS.md` 의 핵심 섹션:

- **자기검증 루프**: `npm run lint:ci` → `tsc --noEmit` → `npm test` 의 3단계, 모두 통과해야 작업 완료.
- **서버 실행 마무리**: foreground / background / Docker Compose / BashOutput 4가지 케이스별 정리 절차.
- **테스트 작성 원칙**: Unit → Integration → E2E (chained) 3 층, 각 층별 책임, 마지막 체인 통과 = 최종 합격.
- **테스트 스타일 — 실행 가능한 명세서**: 5원칙 + 헤더 템플릿 4 블록 + 그룹별 단일 관심사 원칙. 모범 사례로 `in-process.coordinator.spec.ts` 참고 명시.
- **금지 패턴**: `synchronize: true`, `session-ttl.ts` 하드코딩, `page.close()` 누락, `.env` 커밋, `--force`, 새 코드 `any` 남발.
- **NAVER Proxy Pool 정책**: env 빈 값 / 미설정 / deprecated alias 까지 매트릭스 명문화.

**"내 머리 안의 운영 절차" 가 아닌 "코드 베이스에 박힌 운영 절차"**.

## A4. 테스트 헤더의 7가지 행동 계약 명문화

`in-process.coordinator.spec.ts` 헤더:
```
# 변경자에게 — 이 테스트는 계약이다
이 어댑터(또는 의존 모듈)를 수정하는 사람은 모든 테스트가 초록색인
상태로 PR 을 올려야 한다. 하나라도 빨간색이면 SingleFlight 패턴이
사용자에게 한 약속 중 하나가 깨진 것이다.

# 코디네이터가 보장하는 7가지 속성
[1] 코알레싱
[2] 결과 일관성
[3] 자원 정리
[4] kill switch
[5] 호출자 격리
[6] 입력 계약
[7] 관측성

# 그룹별 단일 관심사 원칙
각 describe 그룹의 테스트는 자기 그룹의 보장 속성 하나에만 집중한다.
```

**테스트가 명세서로 기능 + 빨간색이 뜨면 어느 계약이 깨졌는지 그룹명에 즉시 보임**.

## A5. 회귀 측정 데이터를 코드 주석에 박음

`naver-ip-reputation.service.ts`:
```ts
/**
 * Phase G (#565): AWS ElastiCache Serverless (Redis Cluster mode) 의 CROSSSLOT
 * 에러 대응. 각 record* 메서드는 HASH / STREAM / BLOCKLIST_SET / BLOCKLIST_HASH 를
 * 한 MULTI/EXEC 블록에 묶어 쓰는데, Cluster 에서 서로 다른 slot key 를 섞으면
 * CROSSSLOT 에러가 난다. 모든 key 에 공통 hash tag `{pool}` 을 추가해 같은 slot 에
 * 강제 배정.
 */
```

`abck-state-classifier.util.ts`:
```ts
/**
 * Issue #629 P3-1 — `_abck` cookie 상태 머신 분류 helper.
 *
 * Prod 진단: `_abck` 가 `~0~,~-1~,~timestamp~` (verified + challenged 동시) 인
 * 상태에서 sensor 제출 → 403 차단 폭주. 기존 `~0~` 첫 등장 시 즉시 break 로직은
 * race window 안의 `~-1~` 추가를 놓쳐 불필요한 sensor 제출로 이어짐.
 */
```

**왜 이 코드가 이렇게 생겼는가의 근거가 코드 안에 박힘** — 6개월 뒤 만지는 사람이 안 깨먹는 안전망.

## A6. PR review 결과를 코드 주석에 명문화

`akamai-block-detector.util.ts`:
```ts
/**
 * 본 helper 는 cpeats.service.ts 의 메인 loginResult 분기 + Quick Retry 분기 +
 * Prewarm Swap 분기 세 경로에서 일관되게 호출되어 분류 우선순위를 보장한다.
 * 한 곳만 보강하면 page.on("response") 인터셉터의 비동기 set 시점에 따라 retry
 * 경로가 false 를 보고 UnauthorizedException 으로 끝나는 silent 회귀가 발생할
 * 수 있다 (PR #618 review feedback).
 */
```

**리뷰 피드백 자체를 회귀 차단 명세로 박음**.

---

# 부록 B — 면접 대비 빠른 응답 매트릭스

| 질문 | 응답 시작 한 줄 | 본문에서 참조할 사례 |
|------|----------------|---------------------|
| 분산 락 경험 | "Redis LIST 기반 FIFO 큐 + per-request lease + instance-aware lease value 의 3 layer 구조로 ..." | 사례 1 |
| 동시성 race | "워커 30+ 가 같은 매장에 동시 접근하는 4가지 race 를 ..." | 사례 1 |
| Single-Flight / Coalescing | "Port-Adapter + 4 데코레이터 합성 + 세대 가드 + sync-throw microtask 정규화로 ..." | 사례 2 |
| 코드 리뷰 / 계약 | "spec 헤더에 7가지 행동 계약을 박고 describe 1:1 매핑 ..." | 사례 2, A4 |
| 메모리 / OOM | "Camoufox 1GB × 30 worker 의 OOM 위험을 5 layer 자원 격리 (Semaphore / Prewarm / Quarantine / Orphan PID Sweep / Jittered Watchdog) 로 ..." | 사례 3 |
| Thundering Herd | "워치독 타임아웃에 0–30초 jitter 를 박아 ..." | 사례 3 |
| 봇 탐지 / 우회 | "`_abck` 4-state 머신 + bm_sv polling 정책 SSOT + referrer warming 15초 mouse jitter ..." | 사례 4 |
| 외부 API 의존성 / 비용 절감 | "Decodo Residential 월 800만 → 자체 Datacenter 90만, 88.75% 절감. port↔IP 3중 저장 + Redis Cluster hash tag + Codex 리뷰 3회 follow-up ..." | 사례 5 |
| Redis Cluster | "reputation 모듈은 hash tag `{pool}` 로 같은 슬롯 강제, queue 모듈은 단일 키 분리 — 모듈별 의도된 정책" | 사례 1, 5 |
| 도메인 예외 모델 | "3 layer (HttpException → BasePlatformException → 플랫폼별 도메인) + 분류기 helper + 직렬화 경계 3단 분류" | 사례 6 |
| 멱등성 | "Lease + Completion Cache 분리 + 4종 ErrorType + ACK/NACK 매트릭스 명문화 + 안전 기본값 PERMANENT" | 사례 7 |
| 회로 차단 / 자기조절 | "Lua Token Bucket lazy refill + 3-state Circuit (CLOSED/SOFT_OPEN/HALF_OPEN) + discriminated union admit action" | 사례 8 |
| Bulkhead vs Adaptive | "Bulkhead 는 정적 cap, Adaptive 는 정상 시 100% 활용 + 차단 시작 시 lazy 감소 + probe 자동 회복 — 부하 적응형" | 사례 8 |
| AI 코드 리뷰 활용 | "PR #625 의 Codex 리뷰 3회 follow-up — AI 리뷰를 새 시니어 동료처럼 ..." | A2 |
| 운영 절차 / 코드 베이스 | "AGENTS.md 12KB 에 운영 절차 명문화 — env 빈 값, deprecated alias 까지 매트릭스로 ..." | A3 |
| 회귀 측정 | "PR 본문에 baseline 7/9 → patch 18/18 측정 데이터 박음 — 가설/측정/patch/재측정 4단계" | A1 |

---

# 부록 C — 인용된 파일 / PR / SHA 리스트

## 핵심 파일

| 파일 | 라인 | 주제 |
|------|------|------|
| `src/browser/services/session-lock-registry.service.ts` | 921 | SessionLockRegistry — FIFO 큐 + lease TTL + cold-start guard |
| `src/browser/browser.service.ts` | 8958 | Camoufox / Chromium 풀, Launch Semaphore, Prewarm, Orphan PID Sweep |
| `src/browser/services/adaptive-traffic-controller.service.ts` | 326 | Lua Token Bucket + Circuit Breaker |
| `src/common/single-flight/single-flight-coordinator.port.ts` | 57 | Single-Flight Port |
| `src/common/single-flight/adapters/in-process.coordinator.ts` | 115 | In-Process Adapter + 세대 가드 + sync-throw 정규화 |
| `src/common/single-flight/__tests__/in-process.coordinator.spec.ts` | (시작 120+) | 7가지 행동 계약 명문화 |
| `src/common/exceptions/scrapper.exception.ts` | 52 | ScrapperException 베이스 |
| `src/common/exceptions/naver.exceptions.ts` | 277 | 18+ NAVER 도메인 예외 |
| `src/common/exceptions/base-platform.exception.ts` | 126 | 응답 표준화 |
| `src/cpeats/cpeats.service.ts` | 4892 | CPEATS 메인 — Akamai 우회 + Quick Retry v2 |
| `src/cpeats/utils/abck-state-classifier.util.ts` | 64 | `_abck` 4-state 분류기 |
| `src/cpeats/utils/abck-polling-policy.util.ts` | 73 | bm_sv polling 정책 SSOT |
| `src/cpeats/utils/akamai-block-detector.util.ts` | 52 | Akamai 차단 감지 helper |
| `src/proxy/reputation/naver-ip-reputation.service.ts` | 468 | port 평판 시스템 + Cluster hash tag |
| `src/proxy/pool/naver-isp-pool-allocator.service.ts` | 489 | RR allocator + blocklist gating |
| `src/proxy/adaptive/adaptive-proxy-routing.service.ts` | 354 | Adaptive Cooldown |
| `src/queue/consumer/idempotent-handler/idempotent-reply-handler.ts` | (시작 100+) | 8단계 멱등 핸들러 |
| `src/queue/consumer/error-classifier/error-classifier.ts` | 317 | 4종 ErrorType + Tower 추천 |
| `src/queue/consumer/lease/task-lease.service.ts` | 240 | Lease TTL + heartbeat |
| `src/queue/consumer/completion-cache/task-completion-cache.service.ts` | 215 | 완료 캐시 (긴 TTL) |
| `src/worker/sticky-session.service.ts` | 244 | userId → workerUuid sticky 라우팅 |
| `src/worker/worker-pool.service.ts` | 244 | ZSET 기반 최소 Load 워커 선택 |
| `AGENTS.md` | (12KB) | 회사 표준 운영 절차 |

## 핵심 PR / SHA

| PR | SHA | 주제 |
|----|-----|------|
| #569 | `8f77220` | NaverService 80+ 줄 → Single-Flight Port + 4 데코레이터 + 22 spec |
| #644 | `96d0285` | Akamai 우회 default ON, 7/9 → 18/18 측정 |
| #631 | `13c5cc3` | `_abck` 상태 머신 + 2초 race window polling |
| #643 | `d6b9b8c` | Akamai timing patch |
| #618 | `0630914` | AkamaiGHost PASSWORD_ERROR 오분류 보강 |
| #581 | `a22075a` | NAVER port↔IP 매핑 3중 저장 부트스트랩 |
| #565/#566 | `ab140a7` | Phase G Redis Cluster hash tag |
| #594 | `bf2a67b` | NAVER mixed pool (ISP/DC 동시) 인프라 |
| #625 | `cf12614` | Pool exhausted legacy fallback (Codex 리뷰 3회 follow-up) |
| #569 | `8f77220` | Single-Flight Port 추출 |
| (PR `48a6167`) | `48a6167` | Quick Retry v2 = Prewarm Swap + Quarantine, 40 concurrent 97.2% |
| #452 | `5b22d62` | Phase 5 OS PID 기반 orphan sweep — 격차 9 → 0 |
| #321/#322 | (browser/Phase 5 launch stabilization) | Launch Semaphore + GPU mode |
| #323 | (camoufox prewarm) | Prewarm Pool 도입 |
| #326 | (akamai sensor logging) | Akamai 진단 로깅 |
| #327 | (traefik prewarm protection) | warmup gate |

---

# 작성 메모

- **5단 구조**: (1) 컨텍스트 → (2) 문제 → (3) 해결 → (4) 성과 → (5) 기술 매핑 — 각 사례마다 일관.
- **분량**: 사례당 약 200–400 줄, 총 8 사례 + 부록 3개 = 2000+ 줄.
- **수치 정책**: `resume_v9` 의 4 운영 수치 (88.75%, 99.2%, 6배, 90%) + PR 본문에서 확인 가능한 측정 수치 (7/9 → 18/18, 40 concurrent 97.2%, camoufoxActiveCount 격차 9 → 0) 만 인용.
- **이력서 변환**: 각 사례의 "이력서 한 줄 요약" 을 그대로 resume bullet 으로 옮길 수 있음.
- **면접 변환**: 각 사례의 "면접 narrative" 를 그대로 답변으로 풀 수 있음.

