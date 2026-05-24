# 07. Connection Pools Master — 한 요청이 통과하는 모든 풀

> "Connection Pool = HikariCP" 라 답하면 절반은 모르는 것이다.
> 한 HTTP 요청은 **최소 7~13개의 풀**을 통과한다. 어느 한 풀이 작아도 전체가 hang 한다. 어느 한 풀이 너무 커도 하류 자원이 폭발한다.
> 이 챕터는 그 모든 풀을 한 자리에 모아 — "한 풀이 비면 다른 풀이 어떻게 무너지는가" 를 본다.

---

## 1. Pool의 본질

> **Pool = "생성 비용이 큰 자원을 미리 만들어 두고 빌려주는 컨테이너"**

생성 비용이 0이면 풀이 없다. 풀이 있는 이유 = 생성이 응답 시간을 잡아먹기 때문 (TCP 1~3 RTT, TLS 추가 1~2 RTT, DB 인증 + 세션 초기화 50~500ms, OS thread stack 1MB 할당 등).

**Goldilocks 문제** — 너무 작으면 wait queue 적체 → P99 폭발, 너무 크면 하류 자원 폭발 (DB max_connections 초과, context switch 부담). 적정 크기는 **측정**으로 찾는다 (§6 Little's Law).

---

## 2. 한 요청이 만나는 모든 풀 — 전체 흐름 ⭐⭐

```
   [Client]
      │  TCP SYN
      ▼
  ┌──────────────────────────────────────────────────┐
  │ #1. Kernel TCP backlog (LB 측)                   │  somaxconn, tcp_max_syn_backlog
  │     SYN_RECV queue / ACCEPT queue                │
  └────────────────┬─────────────────────────────────┘
                   ▼
  ┌──────────────────────────────────────────────────┐
  │ #2. LB conntrack table                            │  nf_conntrack_max
  └────────────────┬─────────────────────────────────┘
                   ▼
  ┌──────────────────────────────────────────────────┐
  │ #3. LB → backend keepalive pool                   │
  └────────────────┬─────────────────────────────────┘
                   ▼
  ┌──────────────────────────────────────────────────┐
  │ #4. Nginx worker_connections (per worker)         │
  └────────────────┬─────────────────────────────────┘
                   ▼
  ┌──────────────────────────────────────────────────┐
  │ #5. Nginx → Tomcat upstream keepalive             │  upstream { keepalive 32; }
  └────────────────┬─────────────────────────────────┘
                   ▼
  ┌──────────────────────────────────────────────────┐
  │ #6. Tomcat acceptCount  (kernel TCP backlog)      │  ★ kernel 측 한도
  │ #7. Tomcat maxConnections (socket 카운터)         │  ★ Tomcat 측 한도
  │ #8. Tomcat Executor maxThreads                    │  ★ worker thread
  └────────────────┬─────────────────────────────────┘
                   ▼
       [Spring Application]
          ┌────────┬────────┬────────┐
          ▼        ▼        ▼        ▼
       #9       #10      #11      #13
     HikariCP  HTTP    Redis    ForkJoinPool
     DB pool   client  pool     .commonPool /
                pool             @Async executor /
                                 CompletableFuture
                                 (앱 내부 worker)
          │        │        │
          │        ▼        ▼
          │   [외부 API]  [Redis 서버]
          ▼
  ┌──────────────────────────────────────────────────┐
  │ #12. DB max_connections  (server-side)            │  PostgreSQL 1 conn = 1 process
  │      앱 인스턴스 × pool size ≤ DB max × 80%        │  MySQL    1 conn = 1 thread
  └──────────────────────────────────────────────────┘
```

**가로지르는 한도**: 모든 connection은 FD를 1개씩 차지. `ulimit -n` (per-process), `fs.file-max` (system-wide) 한도를 넘으면 `Too many open files` → 어떤 pool도 새 conn 못 만듦. 컨테이너에서는 `LimitNOFILE=` 또는 `--ulimit nofile=` 명시 필요.

### 핵심 통찰

> **모든 풀이 사슬로 연결되어 있다. 어느 한 풀이 비면 위쪽이 적체된다. 가장 흔한 cascade는 아래에서 위로 거꾸로 올라온다 (§5).**

| # | 풀 | 가득 찼을 때 | 위로 전파되는 증상 |
|---|---|---|---|
| 1 | kernel SYN/ACCEPT | SYN drop | client connect timeout |
| 4 | Nginx worker_connections | accept 멈춤 | LB가 다른 backend로 |
| 5 | upstream keepalive | 매번 새 TCP | Tomcat 측 TIME_WAIT 폭증 |
| 6 | Tomcat acceptCount | SYN drop | client connection timeout |
| 7 | Tomcat maxConnections | accept 멈춤 | Nginx에서 적체 |
| 8 | Tomcat Executor | queue 대기 / reject | 503, slow response |
| 9 | HikariCP | getConnection 대기 → timeout | Tomcat thread도 hang → #8까지 hang |
| 12 | DB max_connections | "too many clients" | #9에서 신규 conn 실패 |

---

## 3. Tomcat — 가장 헷갈리는 3한도

```
[Client]
   │
   ▼
┌──────────────────────────────────────────┐
│ Tomcat Connector                          │
│                                            │
│  ┌──────────────────────────────────┐    │
│  │ acceptCount  → listen(fd, n)      │    │  ★ kernel TCP backlog
│  │   somaxconn 로 잘림               │    │
│  └────────────────┬─────────────────┘    │
│                   ▼                       │
│  ┌──────────────────────────────────┐    │
│  │ maxConnections                    │    │  ★ Tomcat 측 socket 카운터
│  │   keep-alive idle 포함            │    │
│  └────────────────┬─────────────────┘    │
│                   ▼                       │
│  ┌──────────────────────────────────┐    │
│  │ Executor maxThreads               │    │  ★ worker thread pool
│  │   한 thread = 한 request          │    │
│  └──────────────────────────────────┘    │
└──────────────────────────────────────────┘
```

| 한도 | 무엇을 제한 | 막히면 증상 |
|---|---|---|
| **acceptCount** | kernel ACCEPT queue 크기 (somaxconn으로 잘림) | SYN drop → client `connect timeout` |
| **maxConnections** | Tomcat이 든 socket 수 (keep-alive 포함) | accept() 일시 중지, Nginx 측 적체 |
| **maxThreads** | request 처리 worker 수 | Executor queue 대기, 503, slow response |

**NIO Connector의 분리**: Poller thread 1개가 수만 idle conn을 epoll로 감시 → maxConnections ≫ maxThreads 가능 (idle 많이 들고 처리는 maxThreads로). 그래서 keep-alive 켜면 `maxConnections` 충분히 크게.

```
keep-alive 미사용:  한 conn = 한 request → maxConnections = 동시 처리 한도
keep-alive 사용:   한 conn이 여러 request 순차 처리 (handshake 절약)
                   maxConnections 8192 중 7000개가 idle → 새 client 거부 위험
                   → maxConnections 충분히 크게
```

**권장 상대 관계**: `acceptCount(수백) < maxConnections(수천~수만) ≥ maxThreads(수백)`. `maxThreads`는 **하류 자원(DB pool) 처리 능력에 맞춤** — 너무 크면 cascading 위험. 또한 Tomcat acceptCount만 늘려도 sysctl `somaxconn`이 작으면 잘림 — 같이 늘려야.

---

## 4. HikariCP — 핵심만

### 4-1. 왜 표준이 됐나

`getConnection()` 평균 ~200ns (DBCP/c3p0은 수천~수만 ns). 빠른 이유 = **ConcurrentBag** 자료구조 + JIT 친화적 단순한 코드 (~130KB).

### 4-2. ConcurrentBag — Lock-free Pool

```
┌─────────────────────────────────────────────────────────────┐
│  ConcurrentBag<PoolEntry>                                     │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ sharedList: CopyOnWriteArrayList<PoolEntry>           │   │
│  │   - 모든 connection (전역)                             │   │
│  │   - reader 안에서는 lock 없음 (COW snapshot)           │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ threadList: ThreadLocal<List<WeakReference<...>>>     │   │
│  │   - 스레드별 최근 사용 conn (warm cache)              │   │
│  │   - 같은 스레드 재borrow → 같은 conn (CPU 캐시 친화)  │   │
│  │   - WeakReference → GC 방해 안 함                     │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ handoffQueue: SynchronousQueue<PoolEntry>             │   │
│  │   - 모든 conn in-use 일 때 borrow 요청 대기열         │   │
│  │   - "다음 release 일어나면 나에게 직접 넘겨라"         │   │
│  │   - wait/notify 의 효율적 대체                         │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

**borrow (getConnection) 흐름**:
```
1. threadList → CAS로 NOT_IN_USE → USE 마킹
       │  found
       ▼
   ★ FAST PATH: lock 없이 즉시 반환 (수십 ns)

2. 없으면 sharedList 순회 (read-side lock 없음)
       │  found
       ▼
   threadList 보충 + 반환

3. 여전히 없고 size < maxPoolSize
       │  yes
       ▼
   비동기 create trigger + handoffQueue.poll(timeout)

4. timeout 까지 못 받음
       ▼
   SQLException: Connection is not available, request timed out
```

**release (close)**: state CAS → `handoffQueue.tryTransfer()` (대기자 있으면 즉시 넘김) → 없으면 threadList 에서 유지 (warm).

### 4-3. 핵심 옵션 — 의미만

| 옵션 | 기본 | 의미 | 실무 권장 |
|---|---|---|---|
| `maximumPoolSize` | 10 | 최대 conn 수 | DB max / 인스턴스 수 × 80% |
| `minimumIdle` | == max | 항상 유지할 idle | **max와 동일** (warmup, 예측 가능) |
| `connectionTimeout` | 30000ms | `getConnection()` 대기 max | **3000ms** (cascading 방어, 빠른 실패) |
| `maxLifetime` | 30분 | conn 강제 갱신 주기 | **firewall idle보다 짧게** (보통 3분) |
| `leakDetectionThreshold` | 0 | leak 감지 시간 | **10000ms** (켜야 함) |

**`connectionTimeout`의 본질**: 30s 기본 → Tomcat thread가 30s 동안 점유됨 → cascading 폭발. **3s로 줄이면 "느린 정상" 대신 "빠른 실패"** → thread 즉시 해방.

**`maxLifetime`의 본질**: conn이 살아있는 최대 시간. 강제로 destroy + recreate 트리거. **firewall/NAT idle timeout보다 짧게** 둬야 §5의 "침묵의 살인자" 방어 가능.

**Proxy Connection**: `getConnection()`이 반환하는 건 `HikariProxyConnection` (PoolEntry 감싼 proxy). `conn.close()` 는 실제 close 아니라 **풀에 return**. try-with-resources 안전.

---

## 5. Firewall idle timeout — 침묵의 살인자

운영 환경 (AWS NAT Gateway, 사내 firewall) 은 보통 **300초(5분) idle** 후 conn 강제 close. **양쪽에 알려주지 않는다** (RST 없음).

```
앱 ─────TCP conn────▶ firewall ─────TCP conn────▶ DB
        ↑                                ↑
       "살아있음"                       "살아있음"

                       5분 idle
                          │
                          ▼
                    firewall이 entry 삭제 (양쪽엔 알림 없음)
                          │
                          ▼
                    두 endpoint는 "살아있다고 믿음"

   다음 query 보내면
   ──── packet ────▶ firewall (no entry) ──── DROP
                                                │
                                                ▼
                                       SO_TIMEOUT 까지 hang (수십 초~분)
```

**증상**:
- "오랜만에 호출하면 첫 query가 timeout"
- "새벽 첫 요청만 느림"
- HikariCP `Connection is not available` 가 간헐적
- 재시도하면 됨 (새 conn 만듦)

**해결**: `maxLifetime = firewall idle × 0.5` 정도. 5분 firewall → maxLifetime 3분. HikariCP가 firewall이 끊기 전에 먼저 destroy + recreate → stale conn 안 만남. (`keepaliveTime`도 보조로 — idle 중 SELECT 1.)

**TCP keepalive로 안 됨**: 일부 firewall은 TCP keepalive packet을 idle 카운트에서 제외 안 함 (data packet만 카운트). 그래서 keepalive 보내도 idle로 간주. **maxLifetime 줄이는 게 가장 확실**.

**3 layer keepalive 정리**:
| Layer | 메커니즘 | 기본 | 함정 |
|---|---|---|---|
| TCP keepalive (kernel) | `tcp_keepalive_time` etc. | 2시간 | 너무 길고 firewall이 카운트 안 할 수도 |
| HTTP keepalive (app) | `Connection: keep-alive`, `keepalive_timeout` | HTTP/1.1 default | Nginx에서 `proxy_http_version 1.1` + `Connection ""` 빠뜨림 = 0% 효과 |
| DB conn (HikariCP) | `maxLifetime`, `keepaliveTime` | 30분 / off | firewall idle 보다 길면 침묵 살인 |

---

## 6. Pool 튜닝 — Little's Law

> **L = λ × W** (동시 처리 중인 작업 수 = 도착률 × 평균 처리 시간)

1000 req/s × 50ms = 50 동시. → Tomcat maxThreads ≥ 50. HikariCP는 thread가 DB만 두드리는 게 아니므로 보통 더 작아도 OK.

**HikariCP 권장 공식**: `pool size = (core_count × 2) + spindle_count`. 8 core + SSD → 17. **너무 작아 보이지만 이게 실제 권장** — DB 동시 query 늘면 context switch 폭발해서 throughput이 오히려 떨어짐. 작은 pool로 빠른 turnover가 큰 pool로 느린 처리보다 빠름.

**큰 pool의 함정**:
```
[Pool=100]                         [Pool=20]
DB에 100 동시 query                DB에 20 동시 query
   ▼                                   ▼
context switch 폭증                 CPU 효율적 사용
DB CPU 100%                        DB CPU 70%
   ▼                                   ▼
각 query 평균 200ms                각 query 평균 50ms
   ▼                                   ▼
throughput ≈ 500 q/s               throughput ≈ 400 q/s
                                       ↑ 비슷한 throughput에 P99 훨씬 낮음
```

**측정 기반 해석**:
| utilization | wait_p99 | DB CPU | 진단 |
|---|---|---|---|
| < 50% | ≈ 0 | 정상 | pool 충분, 더 줄여도 OK |
| > 80% | 증가 | 정상 | pool 부족, 늘려야 |
| 100% | spike | 정상 | pool 부족 확정 |
| 100% | spike | 100% | **pool 늘려도 무의미** — SQL 튜닝, 인덱스, sharding |

---

## 7. Cascading Failure ⭐

```
[T0. 정상]
HikariCP active=5/20  Tomcat busy=50/200

[T1. DB 한 query slow (lock or slow plan)]
1s 쿼리가 30s 로 늘어남 → HikariCP conn 30s 점유

[T2. 점유 누적]
30s 동안 새 요청 계속 → 모두 같은 query → active=20/20 (MAX)
새 요청은 getConnection() 대기 → connectionTimeout 후 SQLException

[T3. Tomcat thread 점유]
대기 중인 Tomcat thread 들도 park → busy=200/200 (MAX)
새 요청은 Executor queue 적체 → maxConnections 도달 → accept 멈춤

[T4. Health check 실패]
LB health check endpoint 도 처리 못 함 → timeout
LB가 인스턴스 unhealthy 마킹 → 트래픽 끊음
남은 인스턴스에 부하 폭주 → 같은 cascade 반복

[T5. 전체 다운]
모든 인스턴스 unhealthy → LB가 503/504
```

**방어 4가지**:
1. **`connectionTimeout` 짧게** (3s) — "느린 정상" 대신 "빠른 실패", thread 즉시 해방
2. **Circuit Breaker** (Resilience4j) — 실패율 임계 넘으면 즉시 fallback, HikariCP 점유 방지. half-open으로 자동 회복
3. **Bulkhead** — 비싼 query는 별도 semaphore로 격리, 전체 thread 점유 방지
4. **Layered timeout** — **안쪽일수록 짧게**:
   ```
   client → LB:        30s   (max)
   LB → Nginx:         25s
   Nginx → Tomcat:     20s
   Tomcat → DB query:  10s    ← 가장 안쪽이 가장 짧게
   HikariCP getConn:    3s
   ```
   원칙: 외곽이 응답 못 받은 직후 즉시 다음 시도 가능하게.

---

## 8. 진단 도구 — 한 표 (ss / jstack / Micrometer)

| 레이어 | 명령 / 메트릭 | 본다 |
|---|---|---|
| TCP | `ss -tan state ...`, `netstat -s | grep listen` | TIME_WAIT 폭증, ACCEPT queue overflow |
| FD | `ls /proc/<pid>/fd | wc -l` vs `cat /proc/<pid>/limits` | FD leak, `Too many open files` |
| Java thread | `jstack <pid>` → `grep 'Thread.State'` 집계 | RUNNABLE vs WAITING(parking) 분포, HikariPool park |
| HikariCP | Micrometer `hikaricp.connections.{active,idle,pending,timeout,acquire}` | pending>0 지속 = 부족, acquire_p99 spike |
| Tomcat | Micrometer `tomcat.threads.busy`, `tomcat.connections.current` | busy/max 비율 |
| Nginx | `stub_status` → Active/Reading/Writing/Waiting | Waiting = keep-alive idle |
| DB | `pg_stat_activity` state 집계, `SHOW PROCESSLIST` | `idle in transaction` 위험 신호 |

**전형적 진단 패턴**:
```bash
# 1) TCP state 분포 — 어디서 막히는가
ss -tan | awk '{print $1}' | sort | uniq -c
#    2 ESTAB
#  432 TIME_WAIT      ← Nginx upstream keepalive 의심
#    8 CLOSE_WAIT     ← app socket leak

# 2) Java thread 어디서 park 중인가
jstack $(pgrep java) | grep 'java.lang.Thread.State' | sort | uniq -c
#  150 RUNNABLE
#  200 WAITING (parking)   ← HikariCP getConnection 의심
jstack $(pgrep java) | grep -B 5 'HikariPool\|getConnection'

# 3) HikariCP MXBean
HikariPoolMXBean pool = hds.getHikariPoolMXBean();
pool.getThreadsAwaitingConnection();   // 핵심 병목 지표

# 4) DB 측 (PostgreSQL)
SELECT state, count(*) FROM pg_stat_activity GROUP BY state;
-- active 45 / idle 30 / idle in transaction 2 (위험)
```

**핵심 알람 룰**:
- HikariCP `pending > 0 for 5m` → pool 부족 또는 DB 느림
- HikariCP `timeout > 0` → 즉시 알람 (절대 발생 X)
- HikariCP `acquire_p99 > 100ms` → pool 또는 DB 이상
- DB `idle in transaction` 1분 이상 → `@Transactional` 안에서 외부 호출 의심

---

## 9. Connection lifecycle — proxy 와 maxLifetime

```
   create ────▶ idle (in pool) ◀─────┐
                    │                  │
                    │ borrow            │ release (proxy.close())
                    ▼                  │
                in-use (with app) ─────┘
                    │
                    │ maxLifetime 도달
                    ▼
                marked for eviction
                    │ 다음 release 시 destroy
                    ▼
                destroy ────▶ DB FIN
```

`dataSource.getConnection()` 이 반환하는 객체는 **HikariProxyConnection** (PoolEntry 감싼 proxy). 매 borrow마다 새 proxy 인스턴스. proxy의 `close()` 가 실제 close 대신 풀에 return. → try-with-resources 로 안전하게 사용 가능 (실제 conn은 풀에 남음).

---

## 10. 나머지 풀 — 한 줄씩

### HTTP client pool

| 라이브러리 | Pool 모델 | 비고 |
|---|---|---|
| Apache HttpClient | `PoolingHttpClientConnectionManager` (per-route) | blocking, 가장 많이 씀 |
| OkHttp | `ConnectionPool` (per-host) | HTTP/2 지원 |
| Java 11 HttpClient | 내장 (per-origin) | 표준 (`java.net.http`) |
| Reactor Netty (WebClient) | `ConnectionProvider` (per-host) | non-blocking, multiplexing → pool size 작아도 OK |

**Per-route vs Global**: per-route는 한 host 느려져도 다른 host 영향 없음 (격리). Global은 모두 영향. 외부 의존 많으면 per-route 권장.

### Redis pool

**Jedis는 thread-unsafe → JedisPool 필수** (인스턴스 = TCP 1개). **Lettuce는 Netty 기반 thread-safe → multiplexing**: 한 socket 위에서 N개 command pipeline, pool 불필요. Spring Boot 2.x+ 기본은 Lettuce. 예외는 `BLPOP` 같은 blocking command — Lettuce가 자동으로 별도 conn 사용.

### DB max_connections

PostgreSQL은 1 conn = 1 OS process (heavy, ~10MB) — `max_connections=100` 정도가 흔함. MySQL은 1 conn = 1 thread (lighter). **계산**: `App 인스턴스 수 × HikariCP max ≤ DB max × 80%`. 인스턴스 30개 × HikariCP 20 = 600 vs DB max 200 → **PgBouncer transaction mode** 도입으로 multiplexing. 단, transaction mode는 PreparedStatement plan cache 깨짐.

---

## 11. 운영 시나리오 — 증상 → 진단 → 해결

### 시나리오 1. P99 latency가 갑자기 2초로 튀었다 (P50은 정상)

```
[진단]
1차: HikariCP wait time 메트릭 → acquire_p99 spike
2차: pg_stat_activity → 'idle in transaction' 50개

[원인]
@Transactional 안에서 외부 API 호출 → 외부가 느려져서 transaction 길어짐
→ DB conn 점유 길어짐 → HikariCP 고갈 → wait 폭증

[해결]
1. 즉시: maximumPoolSize 일시 증가 (응급)
2. 근본: @Transactional 메서드에서 외부 API 호출 분리
3. 모니터링: idle_in_transaction 알람
```

### 시나리오 2. 503 폭증 — Tomcat busy thread 100%

```
[진단]
1차: jstack → 대부분 HikariCP.getConnection() 에서 park
2차: hikaricp.connections.pending 100+ 대기
3차: pg_stat_activity → long-running query 1개가 lock 잡고 있음

[해결]
1. 즉시: pg_terminate_backend 로 long-running query KILL
2. 단기: connectionTimeout 30s → 3s (fast-fail로 cascading 차단)
3. 근본: 인덱스 추가, statement_timeout 설정, circuit breaker
```

### 시나리오 3. Connection reset / refused — 정상 시간대인데 간헐적

```
[증상]
- 클라이언트 측 ConnectException 또는 SocketException: Connection reset
- 오랜만에 첫 요청만 실패, 재시도 성공
- 새벽 트래픽 낮은 구간에 빈번

[진단]
1차: Tomcat 로그 → "Maximum number of threads" 메시지 없음
2차: ss -tan dst :8080 | wc -l → ESTAB 5000+ (Tomcat 측 idle 누적)
3차: HikariCP 로그 → "Connection is not available" 간헐적
4차: tcpdump → 갑작스러운 RST 또는 응답 없음 → SO_TIMEOUT

[원인 후보]
(a) Nginx upstream keepalive 미설정 → Tomcat maxConnections 도달
(b) HikariCP maxLifetime > firewall idle → §5 침묵 살인자

[해결]
(a) Nginx: upstream { keepalive 32; } + proxy_http_version 1.1 +
    proxy_set_header Connection "" + Tomcat keepAliveTimeout 10s
(b) HikariCP maxLifetime을 firewall idle × 0.5 (예: 3분) +
    keepaliveTime 켜기 (HikariCP 4.0+)
```

---

## 12. 꼬리질문

1. **HikariCP maxLifetime을 기본 30분으로 두면 어떤 사고가 흔한가?**
   → AWS NAT/firewall idle (5분)이 더 짧아 conn을 끊는다. HikariCP는 모름. 다음 query에 RST/timeout. 해결: maxLifetime을 firewall idle × 0.5 (3분 등).

2. **maximumPoolSize를 100으로 올렸더니 DB CPU 100% + 응답이 더 느려졌다. 왜?**
   → 동시 query 늘면 context switch 폭발 (특히 PostgreSQL process-based). Little's Law 관점에서 throughput 그대로지만 처리 시간 늘어남. 권장 `(core × 2) + spindle` 정도. 측정으로 knee point 찾기.

3. **Tomcat 503 폭증 + jstack 모두 HikariCP.getConnection park. 즉시 단계는?**
   → (a) DB long-running query KILL → (b) connectionTimeout 30s → 3s로 단축 (cascading 차단) → (c) 인스턴스 추가 → (d) statement_timeout/circuit breaker로 근본 차단.

4. **30 인스턴스 × HikariCP 20 = 600 conn 요청, DB max=200. 어떻게?**
   → PgBouncer transaction mode (600 client → 200 backend multiplexing). 트레이드오프: PreparedStatement plan cache 깨짐 → `prepareThreshold=0` 또는 `server_reset_query`.

5. **Tomcat `acceptCount=200`으로 늘렸는데 여전히 SYN drop. 왜? Lettuce가 pool이 없는 이유는?**
   → (a) `listen(fd, backlog)`의 backlog는 kernel `net.core.somaxconn` 으로 잘림. `somaxconn=128` 이면 200 → 128. `sysctl -w net.core.somaxconn=8192` 같이 늘려야. 컨테이너는 host 또는 securityContext sysctls 설정 필요.
   → (b) Lettuce는 Netty 기반 single channel multiplexing — 여러 thread가 한 socket에 pipeline. RESP protocol이 pipeline 친화적, Redis가 client 당 command 순서대로 처리. 예외는 `BLPOP` 같은 blocking — Lettuce가 자동으로 별도 conn 할당.

---

---

## 한 줄 마무리

> **풀은 비싼 자원을 미리 만들어 빌려주는 자료구조다. 한 요청은 7~13개 풀을 통과하고 어느 한 풀이 비면 위쪽이 적체된다. 마스터의 핵심은 (1) 각 풀의 위치와 한도, (2) cascading 방어 (timeout/circuit breaker/bulkhead/layered timeout), (3) Little's Law 기반 측정 튜닝, (4) maxLifetime vs firewall idle 의 침묵 살인자.**

---

> HikariCP ConcurrentBag 풀버전, HTTP client별 timeout 매핑, PgBouncer 3 모드, Lettuce multiplexing, kernel TCP SYN_RECV/ACCEPT 두 큐는 git 7e4a6c8 참조.
