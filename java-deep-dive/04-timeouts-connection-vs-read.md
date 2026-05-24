# 04. Timeouts — Connection vs Read vs Write vs Total

> "HttpClient에 timeout 걸었어요." — 어떤 timeout인가? Connection? Read? Pool wait?
> Production hang의 1순위 원인은 **timeout 누락**. 외부 호출 한 줄에 timeout이 빠지면, hang된 thread가 Tomcat thread pool을 점령하고 → 503 폭증 → 캐스케이딩 마비.
> 본질은 **"어디서 어떻게 blocking되는가"**를 OS syscall → JVM Socket → HTTP client → application 4계층에서 매핑하는 일.

---

## 0. 목차

1. **4가지 timeout 정의** (connect / read / write / total)
2. **OS 계층** — recv syscall, EAGAIN/ETIMEDOUT
3. **JVM Socket 계층** — BIO/NIO
4. **HTTP Client별 timeout 옵션** — 표 하나로
5. **JDBC 4계층 timeout** — 한 그림
6. **Cascading failure**
7. **운영 시나리오**
8. **꼬리질문**

---

## 1. 4가지 timeout — 시간축에서 어디를 끊나

```
client                                         server
  │── SYN ─────────────────────────────────────►│  ┐ Connection Timeout
  │◄──────── SYN-ACK ────────────────────────────│  │ (TCP 3-way)
  │── ACK ─────────────────────────────────────►│  ┘
  │── HTTP request (send buffer flush) ────────►│  ─ Write Timeout
  │                                              │
  │   (server processing — DB, etc.)             │
  │                                              │
  │◄──── HTTP response chunk 1 (recv()) ─────────│  ┐
  │◄──── chunk 2 (recv() again, idle reset) ─────│  │ Read Timeout
  │◄──── chunk N ────────────────────────────────│  ┘ (한 recv()의 idle)
  │── close ──────────────────────────────────►│
  ◄═══════════════ Total / Call Timeout ════════►
```

### 1.1 4종 요약 표

| Timeout | 끊는 단계 | OS 메커니즘 | Java API | 미설정 시 위험 |
|---|---|---|---|---|
| **Connection** | TCP SYN→ACK | `connect()` + poll timer | `Socket.connect(addr, ms)` | Linux 기본 ~127초 대기 (tcp_syn_retries=6) |
| **Read** | recv idle | `recv()` + SO_RCVTIMEO | `Socket.setSoTimeout(ms)` | 무한 (서버가 close 안 하는 한) |
| **Write** | send buffer flush | `send()` + SO_SNDTIMEO | client lib 별 옵션 | 무한 (peer가 ACK 안 줄 때) |
| **Total** | 전체 요청 | application timer | `OkHttp.callTimeout`, `HttpRequest.timeout`, gRPC deadline | redirect/retry로 무한 누적 가능 |

**핵심 함정 — Read timeout은 "전체 응답 시간"이 아니다**:
매 recv()마다 reset. read timeout=5초인데 server가 4초마다 1 byte씩 보내면 영원히 안 끊김. 그래서 **Total/Call timeout이 별도로 필요**.

### 1.2 각 timeout의 3가지 케이스

**Connection timeout 3 case**:
1. 정상 — SYN-ACK 빠르게 옴 (수 ms ~ 수십 ms)
2. 방화벽 DROP (응답 없음) — timeout까지 무한 대기 → 미설정 시 ~127초
3. 방화벽 REJECT(RST) 또는 host unreachable — 즉시 `ConnectException`

**Read timeout이 잡는 것 vs 못 잡는 것**:
- 잡음: 서버가 hang되어 한 byte도 안 보낼 때
- 못 잡음: 서버가 slow drip (4초마다 1 byte), 서버가 lock wait 중 (HTTP/DB 응답 없음 + idle 아님)
- 못 잡음: redirect/retry로 새 connection 시작 → read timeout reset

**Write timeout이 발생하는 조건**:
- TCP send buffer가 가득 차서 send()가 block
- peer가 ACK 안 보내거나 receive window=0
- 큰 request body (file upload 등)에서 빈발

---

## 2. OS 계층 — recv() syscall이 어디서 sleep하나

```
user space                 kernel space
recv(fd, buf, len) ──────► sys_recvfrom()
                            ├─ TCP receive queue 확인
                            │   ├─ 데이터 있음 → copy_to_user → return n
                            │   └─ 비어있음 → ▼
                            ├─ SO_RCVTIMEO timer 설정
                            ├─ schedule_timeout() — process sleep
                            │   ├─ 데이터 도착 → wake_up → return
                            │   ├─ timer 만료 → return -1, errno=EAGAIN
                            │   └─ signal → return -1, errno=EINTR

connect(fd, addr) ────────► sys_connect()
                            ├─ TCP: CLOSED → SYN_SENT (SYN 전송)
                            ├─ wait for SYN-ACK
                            │   ├─ SYN-ACK → ESTABLISHED → return 0
                            │   ├─ retransmit (1s, 2s, 4s, ... tcp_syn_retries)
                            │   ├─ RST → return -1, errno=ECONNREFUSED
                            │   └─ timer 만료 → return -1, errno=ETIMEDOUT
```

→ 모든 timeout의 본질은 **kernel timer + sleeping process wake-up**. recv()는 EAGAIN/ETIMEDOUT으로 끊고, JNI에서 `SocketTimeoutException`으로 변환.

---

## 3. JVM Socket 계층 — BIO vs NIO

**BIO (java.net.Socket, JDK 1.0~)**:
```java
Socket s = new Socket();
s.connect(new InetSocketAddress(host, port), 3000);  // connect timeout
s.setSoTimeout(5000);                                 // read timeout (SO_RCVTIMEO)
int n = s.getInputStream().read(buf);                 // blocking
```
SocketInputStream.read() → JNI native `socketRead0()` → 내부에서 `select()`/`poll()` + `recv()`. thread-per-connection. timeout 미설정 시 무한 block. 표준 Socket에는 **write timeout 옵션 없음** (HTTP client lib이 자체 구현).

**NIO (java.nio.SocketChannel + Selector, JDK 1.4~)**:
```java
ch.configureBlocking(false);
ch.register(sel, OP_READ);
sel.select(timeoutMs);   // ← 내부적으로 epoll_wait(epfd, events, ..., timeoutMs)
```
한 thread가 수만 connection의 timeout을 epoll로 일괄 관리. Reactor/Netty/Tomcat NIO connector의 기반. 단점: state machine 코드 복잡.

**NIO.2 (AsynchronousSocketChannel, JDK 7+)**:
`asyncCh.read(buf, timeout, TimeUnit.MS, attachment, handler)` — completion callback. 내부적으로 epoll/kqueue + thread pool.

**Virtual Thread (JDK 21)**: BIO 코드 그대로 + 수십만 thread. carrier thread를 점유하지 않으므로 thread pool 고갈은 사라짐. 그러나 **timeout 명시 필요성은 동일** — virtual thread도 추적/관리 비용이 있고, downstream(외부 API, DB)은 여전히 진짜 자원이라 hang 시 cascading.

---

## 4. HTTP Client별 timeout 옵션 — 표 하나로

| Client | Connect | Read | Write | Pool wait | **Total / Call ⭐** |
|---|---|---|---|---|---|
| **Apache HttpClient 4** | connectTimeout | socketTimeout | socketTimeout | connectionRequestTimeout | ✗ (5.x에서 responseTimeout) |
| **Apache HttpClient 5** | connectTimeout | responseTimeout | responseTimeout | connectionRequestTimeout | responseTimeout |
| **OkHttp** ⭐ | connectTimeout | readTimeout | writeTimeout | (pool 내장) | **callTimeout** |
| **Java 11 HttpClient** | connectTimeout (builder) | — | — | — | **HttpRequest.timeout** |
| **RestTemplate** | (factory에 따라) Apache/Simple | 동일 | 동일 | 동일 | 라이브러리 의존 |
| **WebClient (Reactor Netty)** | CONNECT_TIMEOUT_MILLIS | responseTimeout / ReadTimeoutHandler | WriteTimeoutHandler | pendingAcquireTimeout | **Mono.timeout()** |
| **Feign** | connectTimeout | readTimeout | — | — | Resilience4j 조합 |
| **gRPC** ⭐ | channel 생성 시 | — | — | — | **per-call deadline** (header 자동 전파) |

**규칙**:
- 외부 호출은 **반드시 Total/Call timeout 명시** (최후 보루) — redirect/retry까지 포함해서 끊음
- Apache는 `connectionRequestTimeout` (pool wait) 누락 빈번 — pool 고갈 시 여기서 막힘. kernel 무관, application timer
- WebClient는 5개 옵션이 흩어져 있어 누락 빈번 — `CONNECT_TIMEOUT_MILLIS` + `responseTimeout` + `ReadTimeoutHandler` + `pendingAcquireTimeout` + `Mono.timeout()`. 다 빼먹으면 event loop hang
- gRPC deadline propagation: A(deadline=5s) → B(남은 3s) → C(남은 1s) HTTP header로 자동 전파. C에서 남은 시간이 음수면 RPC 시작 자체 안 함 → 캐스케이딩 hang 자동 방지. 마이크로서비스 권장

**OkHttp callTimeout 내부 동작**: `Dispatcher` 안의 `ScheduledExecutorService`가 timer 등록 → 만료 시 `RealCall.cancel()` → socket close → `IOException("Canceled")`. redirect/retry/interceptor 다 포함해서 강제 종료.

---

## 5. JDBC timeout — 4계층 중첩

```
요청 시작
   │
   ▼
┌──────────────────────────────────────────────┐
│ ① HikariCP.getConnection()                    │
│   connectionTimeout (default 30s → 3~5s 권장)  │
│   → pool 고갈 시 여기서 막힘                    │
└──────────────┬───────────────────────────────┘
               │ 빌림 성공
               ▼
┌──────────────────────────────────────────────┐
│ ② driver.connectTimeout (새 connection 만들 때)│
│   → DB로 TCP 3-way                           │
└──────────────┬───────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────┐
│ ③ Statement.executeQuery()                    │
│   ├─ Statement.setQueryTimeout(5) ★ DB가 SQL 죽임│
│   └─ driver.socketTimeout (recv idle)        │
└──────────────┬───────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────┐
│ ④ DB 측 자체 timeout (백업 방어선)              │
│   PostgreSQL: statement_timeout              │
│   MySQL: max_execution_time                   │
└──────────────────────────────────────────────┘

권장 시간 관계 (안쪽이 짧게):
  HikariCP connectionTimeout (3s)
    < Statement queryTimeout (5s)
    < socketTimeout (10s)
    < DB statement_timeout (10s)
    < @Transactional (15s)
    < Tomcat connection-timeout (20s)
    < LB upstream timeout (30s)
```

### 5.1 왜 socketTimeout만으론 부족한가

DB가 **lock wait** 중이면 socket으로는 정상 통신 중 (idle 아님). recv()가 안 끊김.
→ `Statement.setQueryTimeout(N)`만이 잡을 수 있음 (driver가 timer로 cancel signal 전송 → DB가 query 죽임).

### 5.2 DB 측 statement_timeout이 왜 별도로 필요한가

client가 죽거나 (kill -9), 네트워크 단절 → driver가 cancel 못 보냄 → DB는 query 영원히 실행. DB 측 timeout이 백업.

**Best**: client queryTimeout(5s) < DB statement_timeout(10s). client가 먼저 끊고, 안 되면 DB가 강제 종료.

---

## 6. Cascading failure — 가장 흔한 장애

```
[정상]                          [외부 API 느려짐 + timeout 누락]
┌──────────┐                   ┌──────────┐
│ Tomcat   │                   │ Tomcat   │
│ thread   │──► 외부 API 100ms   │ thread   │──► 외부 API 30s+ hang
│ pool=200 │                   │ pool=200 │
└──────────┘                   └──────────┘
in-flight 60                   thread 200개 모두 recv() block
                                 │
                                 ▼
                               새 요청 → queue full → 503
                                 │
                                 ▼
                               /actuator/health 응답 못 함
                                 │
                                 ▼
                               LB가 instance kill → 옆 instance로 load
                                 │
                                 ▼
                               같은 증상 → 시스템 전체 마비
```

**해결 4단계**:
1. **timeout 명시** (모든 외부 호출, 특히 Total/Call)
2. **circuit breaker** (실패 누적 시 fast-fail, Resilience4j)
3. **bulkhead** (외부 호출별 별도 thread pool)
4. **graceful degradation** (fallback 응답)

**Stale connection ("Connection reset by peer")**: pool에 idle로 남은 connection을 방화벽/NLB가 silent drop → 다음 query 전송 시 peer가 모르는 connection → RST. 해결: `maxLifetime` 짧게 (방화벽 idle보다 짧게), `keepaliveTime` 활성.

**WebFlux 함정**: thread pool 고갈 대신 **event loop hang**. `Mono.timeout()` 누락 시 그 event loop에 할당된 모든 connection이 stuck. thread 늘려도 해결 안 됨.

### 6.1 Resilience4j 4종 세트 — timeout과 같이 가야 안전

| 패턴 | 책임 | timeout과의 관계 |
|---|---|---|
| **TimeLimiter** | 호출 전체 시간 상한 | timeout의 application 레이어 구현 (Future.cancel) |
| **CircuitBreaker** | 실패 누적 시 fast-fail (open state) | timeout 단독은 매 호출마다 N초 낭비 → resource 보호 추가 |
| **Bulkhead** | 외부 호출별 별도 thread pool / semaphore | hang이 다른 호출 경로로 번지지 않게 격리 |
| **Retry** | 일시적 실패 재시도 | 무한 재시도 금지 — 누적 timeout 폭발 주의 |
| **Fallback** | 실패 시 대체 응답 | 외부 의존이 죽어도 graceful degradation |

### 6.2 timeout 시간 계층 — 안쪽이 짧게

```
HikariCP connectionTimeout (3s)
  < socket read timeout (10s)
  < Statement queryTimeout (5s)
  < @Transactional timeout (15s)
  < Tomcat connection-timeout (20s)
  < LB upstream timeout (30s)
  < User patience (3min)
```
안쪽이 먼저 fail해야 자원 회수 빠르고 응답성 유지.

---

## 7. 운영 시나리오

### 7.1 외부 API hang → 503 폭증

```
증상: Tomcat thread 200 모두 점유. /actuator/health도 응답 못 함. LB가 instance kill.

진단 단계:
  1. jstack 100개 채취 (5초 간격 5회) → 90개가 같은 stack:
       at sun.nio.ch.SocketDispatcher.read0(Native Method)
       at org.apache.http.impl.io.SessionInputBufferImpl.read(...)
       at OkHttpCallExecutor.execute(...)
     → 외부 API 호출 read에서 막힘. progress 없음.
  2. tcpdump 캡처: SYN→SYN-ACK 정상. POST 후 server 응답 없음.
     → connect 문제 아님. peer 처리 지연.
  3. JFR jdk.SocketRead → 특정 endpoint만 p99 30s+
  4. 코드 확인 → OkHttp.Builder()에 callTimeout 누락.

조치 (Resilience4j 4종 세트):
  - OkHttp.callTimeout(3s) 추가 (1차 방어)
  - CircuitBreaker (실패 50% 누적 시 30s 차단)
  - TimeLimiter (호출 전체 3s)
  - Bulkhead (외부 호출 전용 thread pool 분리)
  - Fallback Mono.just(empty) 정의

검증 (chaos engineering):
  - Toxiproxy로 외부 API에 10초 지연 주입
  - 3초 후 fallback 동작 확인
  - Tomcat thread pool 정상 회수 확인
```

**흔한 함정**: 메인 OkHttpClient는 timeout 잘 설정. 그러나 error handler 안의 fallback client / metrics client / logging client가 default(=무한)로 설정 → 부속 client들이 hang.

### 7.2 HikariCP 30초 connectionTimeout 자꾸 발생

```
증상: 장애 발생 시 SQLTransientConnectionException 30초 후 빵빵 터짐.

원인 체인:
  - JDBC URL에 socketTimeout 누락
  - DB hang (VACUUM full / lock wait)
  - 기존 사용 중 connection들은 영원히 recv() block
  - HikariCP가 connection 회수 못 함 (사용 중)
  - 새 요청이 pool에서 wait → 30초 후 timeout

근본 해결:
  - JDBC URL: ?connectTimeout=3&socketTimeout=10
  - Statement.setQueryTimeout(5) — 또는 @Transactional(timeout=5)
  - DB statement_timeout=10s (PostgreSQL)
  - HikariCP connectionTimeout: 30s → 3s (응답성 우선)
```

### 7.3 "Connection reset by peer" 간헐 발생

```
시나리오:
  1. Service가 DB connection을 idle 상태로 pool에 반납
  2. AWS NLB가 350초 idle 후 silent drop
  3. 다음에 그 connection 꺼내 SQL 전송 → peer가 모르는 connection
  4. RST → SQLException

해결:
  config.setMaxLifetime(300_000);    // 5분 (NLB 350s보다 짧게)
  config.setKeepaliveTime(60_000);   // 60초마다 ping
  + TCP SO_KEEPALIVE (kernel 레벨)
```

---

## 8. 진단 도구 요약

| 도구 | 용도 | 핵심 신호 |
|---|---|---|
| `strace -e network,read,write -p PID` | syscall 수준 검증 | `poll([...], 1, 3000) = 0 (Timeout)` → 3s timeout 정말 동작 |
| `tcpdump 'port 5432'` | wire 수준 | SYN 후 SYN-ACK 안 옴=connect 문제 / SYN-ACK 빨리 옴 + long pause=server 처리 지연 / RST 주체=누가 끊었나 |
| `ss -tn state established` | TCP 상태 | Recv-Q>0 = app이 안 읽음, Send-Q>0 = peer가 ACK 안 줌 |
| `jstack PID` | Java thread stack | `SocketDispatcher.read0` = 외부 응답 대기 / `ConcurrentBag.borrow` = HikariCP pool wait / `LockSupport.parkNanos` = TIMED_WAITING |
| `jcmd PID JFR.start` + `jdk.SocketRead` | 정량 분석 | host/port별 duration p99/p999, "어느 외부 호출이 느린가" |
| async-profiler `-e wall` | wall-clock | CPU만 보는 profiler와 달리 blocking 시간 포함 — socket read 점유율 |
| Toxiproxy / Pumba | chaos injection | 운영 전 timeout이 정말 끊는지 검증 (의도적 latency / packet loss) |

**진단 패턴 — "5초 끊기는 thread vs 30초 hang thread 공존"**:
1. jstack 다회 채취 → 같은 stack에 30s+ 있으면 progress 없음 확정
2. 5s 끊기는 stack에서 어떤 timeout이 동작했나 (Apache vs OkHttp vs JDBC) 식별
3. tcpdump로 비교: 5s case는 client RST 보냄 / 30s case는 RST 없음 → timeout 미설정 경로
4. 의심: 메인 client는 OK, 부속 client(metrics/logging)가 default 무한

---

## 9. 꼬리질문

### Q1. Connection timeout과 Read timeout이 어떻게 다른가요?

> Connection은 TCP 3-way (SYN→SYN-ACK→ACK)까지. `connect()` syscall + kernel timer. Linux 미설정 시 tcp_syn_retries=6 → ~127초.
> Read는 한 recv()의 idle 시간. SO_RCVTIMEO. 매 recv()마다 reset → 전체 응답 시간 아님.
> → Total/Call timeout (OkHttp.callTimeout, HttpRequest.timeout, gRPC deadline)이 별도 최후 보루.

### Q2. Java Socket.read()가 정확히 어디서 blocking되나요?

> JVM → JNI → kernel `recv()` syscall → TCP receive queue 비어있으면 process를 sleep 큐에 → 데이터 도착 또는 SO_RCVTIMEO timer 만료까지 sleep. timer 만료 시 -1 + EAGAIN → JNI에서 SocketTimeoutException으로 변환.
> NIO는 `Selector.select(timeoutMs)` → `epoll_wait(timeoutMs)`로 한 thread가 수만 connection 일괄 관리.

### Q3. JDBC timeout이 왜 4개가 필요한가요?

> 각각 다른 단계 보호:
> 1. HikariCP.connectionTimeout — pool 고갈 방어
> 2. driver.connectTimeout — DB 다운 방어
> 3. driver.socketTimeout — DB 응답 없음 방어 (recv idle)
> 4. Statement.setQueryTimeout — **DB lock wait 방어** (socket은 idle 아니므로 socketTimeout으로 못 잡음)
> 추가로 DB statement_timeout — client 죽었을 때 백업.
> 권장: HikariCP(3s) < query(5s) < socket(10s) < DB statement(10s).

### Q4. 외부 API hang으로 503 폭증이 일어나는 메커니즘은?

> 외부 API 느려짐 → timeout 없으면 매 호출 30s+ 점유 → Tomcat thread 200개 모두 recv() block → 새 요청 queue full → 503 → /actuator/health도 응답 못 함 → LB가 instance kill → 옆 instance로 load → 캐스케이딩 마비.
> 해결: timeout + CircuitBreaker + Bulkhead + Fallback (Resilience4j 4종 세트).

### Q5. "Connection reset by peer"는 왜 일어나나?

> Stale connection. pool에 idle로 남은 connection을 방화벽/NLB가 idle timeout 후 silent drop. 다음 query 전송 시 peer가 모르는 connection → RST.
> 해결: `maxLifetime`을 방화벽 idle보다 짧게 (예: NLB 350s → maxLifetime 300s), `keepaliveTime` 활성 (60s 주기 ping), TCP SO_KEEPALIVE.

---

## 10. 한 줄 요약

> **외부 호출에 timeout을 명시하지 않은 코드는 production에서 cascading hang으로 503 폭증을 일으킨다.**
> **Connection = TCP 3-way, Read = recv() idle, Write = send buffer, Total = 전체 호출.**
> **JDBC는 socketTimeout으로 DB lock wait를 못 잡으므로 Statement.setQueryTimeout이 최후 보루.**
> **안쪽이 짧게 (pool < query < socket < transaction < tomcat < LB). CircuitBreaker + Bulkhead + Fallback과 함께. Chaos engineering으로 검증.**

---

## 참고

- OkHttp Timeouts: https://square.github.io/okhttp/recipes/#timeouts-kt-java
- HikariCP: https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby
- gRPC Deadlines: https://grpc.io/blog/deadlines/
- Resilience4j: https://resilience4j.readme.io/

> HTTP client별 timeout 옵션 풀(WebClient 5옵션, OkHttp callTimeout 등), gRPC deadline propagation, Toxiproxy chaos는 git 7e4a6c8 참조
