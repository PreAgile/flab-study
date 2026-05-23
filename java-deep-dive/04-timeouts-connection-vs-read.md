# 04. Timeouts — Connection vs Read vs Write vs Total

> "HttpClient에 timeout 걸었어요." — 어떤 timeout인가? Connection? Read? Pool wait?
> 시니어가 알아야 할 것: **production hang의 1순위 원인은 timeout 누락**. 외부 호출 한 줄에 timeout이 누락되면, hang된 thread가 Tomcat thread pool을 점령하고, 새 요청은 503을 받고, 캐스케이딩 실패로 시스템이 무너진다.
> 본질은 **"어디서 어떻게 blocking되는가"**를 OS syscall → JVM Socket → HTTP client → application 4계층에서 매핑하는 일이다.

---

## 이 문서의 사용법

1. **0장 마인드맵을 먼저 외운다** (4가지 timeout + 4계층).
2. **1~7장을 순서대로 학습한다**.
3. **8장 면접 워크플로우** + **9장 꼬리질문**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"Timeout은 hang을 끊는 안전판이다. Connection은 TCP 3-way까지, Read는 syscall recv()의 idle 시간, Write는 send buffer flush, Total은 전체 요청. timeout 누락 → thread 무한 점유 → pool 고갈 → 503 폭증. 외부 호출은 무조건 4가지 timeout 모두 명시."**

### 5개 가지 — 순서를 외운다

```
              [ROOT: Timeout = hang을 끊는 안전판 + 4종 + 4계층]
                                  │
       ┌──────────┬───────────────┼───────────────┬──────────┐
       │          │               │               │          │
      ① 4종      ② 4계층          ③ HTTP 클라     ④ JDBC     ⑤ 함정·패턴
   (Connect/   (OS syscall →     (Apache/        (Hikari+   (cascading,
    Read/      Socket(BIO/NIO)→  OkHttp/         driver+    pool wait,
    Write/     HTTP client →     WebClient/      query+     keepalive,
    Total)     application)      Feign/gRPC)     DB)        circuit)
       │          │               │               │          │
   ┌───┼───┐  ┌──┼──┐         ┌───┼───┐       ┌──┼──┐    ┌───┼───┐
  TCP    SO_   recv()        pool  conn        socket    cascading
  SYN→   TIMEOUT  syscall    wait  request     vs        thread
  ACK    (idle)  blocking         pool req     query     pool 고갈
```

### 가지별 핵심 키워드

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① 4종** | Connection (TCP 3-way) | Read (recv idle) | Total (callTimeout) |
| **② 4계층** | OS recv() syscall | java.net.Socket / NIO | HTTP client / JDBC |
| **③ HTTP** | Apache HttpClient | OkHttp callTimeout | WebClient responseTimeout |
| **④ JDBC** | Hikari connectionTimeout | driver socketTimeout | Statement.setQueryTimeout |
| **⑤ 함정** | cascading failure | stale connection | pool wait < op |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 해당 가지 → 키워드 3개 → 인접 가지로 확장

---

## 1. 가지 ①: 4가지 timeout의 정의 — 어디서 어떻게 끊나

### 1.1 핵심 질문

> "외부 호출에 timeout이 필요한 이유는? 어떤 종류가 있나?"

### 1.2 한 장 그림 — 시간축에서 4가지가 다른 곳에 위치한다

```
시간축 →

  client                                         server
   │                                              │
   │── SYN ─────────────────────────────────────►│  ┐
   │◄──────────────────────────── SYN-ACK ───────│  ├ Connection
   │── ACK ─────────────────────────────────────►│  │  Timeout
   │                                              │  ┘  (TCP 3-way handshake)
   │── HTTP request (header + body) ────────────►│  ┐
   │      send buffer flush                       │  ├ Write Timeout
   │                                              │  ┘  (send buffer 안 비워질 때)
   │                                              │
   │   (server processing — DB query, etc.)       │
   │                                              │
   │◄────────── HTTP response chunk 1 ────────────│  ┐
   │   ← recv() 첫 byte                            │  │
   │◄────────── chunk 2 ───────────────────────────│  ├ Read Timeout
   │   ← recv() 다음 byte                           │  │  (한 recv() 호출의 idle)
   │◄────────── chunk N (last) ────────────────────│  ┘
   │                                              │
   │── close ──────────────────────────────────►│
   │                                              │
   ◄═══════════════════ Total / Call Timeout ═════►
                  (connect + send + recv 전체)
```

### 1.3 키워드 1 — Connection timeout (TCP 3-way까지)

```
[정의]
  client → server TCP connection을 establish할 때까지의 시간.
  SYN → SYN-ACK → ACK 3-way handshake 완료까지.

[OS 레벨]
  connect() syscall이 EINPROGRESS → poll/select wait → connected
  
[Java 레벨]
  Socket.connect(addr, timeoutMs)
  
[timeout 미설정 시]
  TCP retransmission: 1s, 2s, 4s, 8s, 16s, 32s, ...
  Linux 기본 tcp_syn_retries=6 → 최대 ~127초 대기

[3가지 케이스]
  1. 정상 — SYN-ACK 빠르게 옴 (수 ms ~ 수십 ms)
  2. 방화벽 DROP (응답 없음) — timeout까지 무한 대기
  3. 방화벽 REJECT (RST) 또는 호스트 unreachable — 즉시 ConnectException
```

### 1.4 키워드 2 — Read timeout (= SO_TIMEOUT, recv idle)

```
[정의]
  한 번의 recv()/read() 호출이 데이터를 받기까지의 idle 시간.

[중요 — 흔한 오해]
  Read timeout은 "전체 응답 시간"이 아니다.
  매 recv()마다 새로 측정됨. 응답이 천천히 흘러들어와도 byte 사이 간격이 
  timeout보다 짧으면 영원히 read 호출이 끝나지 않을 수 있다.
  
  예: read timeout = 5초, server가 4초마다 1 byte씩 보냄
      → 영원히 안 끊김 (각 recv()는 4초 안에 1 byte 받음)
  
  → 그래서 Total/Call timeout이 별도로 필요.

[OS 레벨]
  recv() syscall이 kernel TCP receive buffer 확인
  buffer empty → process를 sleep 큐에 넣음
  buffer에 데이터 오거나 timer 만료까지 sleep
  timer 만료 → recv() returns -1, errno = EAGAIN/ETIMEDOUT

[Java 레벨 — BIO]
  Socket.setSoTimeout(ms)
  → SocketInputStream.read() blocks up to that ms
  → SocketTimeoutException
```

### 1.5 키워드 3 — Write timeout

```
[정의]
  한 번의 send()/write() 호출이 kernel send buffer를 비우기까지의 시간.

[언제 일어나나]
  - TCP send buffer (kernel)가 가득 차서 추가 데이터 못 받음
  - peer가 ACK를 안 보내거나 receive window가 0인 경우
  - 큰 request body를 보낼 때 자주 발생

[OS 레벨]
  send() syscall이 buffer가 가득 차면 block
  (non-blocking이면 EAGAIN)

[Java 레벨]
  표준 java.net.Socket에는 write timeout 직접 옵션 없음.
  HTTP client 라이브러리가 Selector / async I/O로 자체 구현.
  - OkHttp.writeTimeout
  - Reactor Netty channel write timeout
  - Apache HttpClient는 socketTimeout이 read와 write 둘 다 영향
```

### 1.6 키워드 4 — Total / Call / Request timeout

```
[정의]
  요청 전체 (connect + send + receive) 시간 상한.

[왜 필요]
  Connection + Read timeout만으로는 한계:
  - Read timeout은 매 recv()마다 reset → 누적 시간 무제한
  - Redirect 따라가면 또 다른 connect + send + recv 사이클
  - Retry 정책이 있으면 더 누적

[Java 레벨]
  - OkHttp: callTimeout (강력 권장)
  - Java 11 HttpClient: HttpRequest.timeout
  - WebClient: Mono.timeout() operator
  - gRPC: per-call deadline
  - 일반 BIO Socket: 직접 구현 어려움 → wrapper thread 또는 ScheduledExecutor
```

### 1.7 4종 요약 표 + 책임 매핑

| Timeout | 끊는 단계 | OS 메커니즘 | Java API | 미설정 시 위험 |
|---|---|---|---|---|
| **Connection** | TCP SYN→ACK | `connect()` + poll timer | `Socket.connect(addr, ms)` | ~127초 대기 (Linux 기본) |
| **Read** | recv idle | `recv()` + SO_RCVTIMEO | `Socket.setSoTimeout(ms)` | 무한 (서버가 끊지 않는 한) |
| **Write** | send buffer flush | `send()` + SO_SNDTIMEO | client lib 별 옵션 | 무한 (peer가 ACK 안 줄 때) |
| **Total** | 전체 요청 | 사용자 영역 timer | `OkHttp.callTimeout` 등 | 무한 누적 가능 |

→ **외부 호출은 4가지 모두 명시**가 원칙. 특히 Total/Call timeout이 최후 보루.

---

## 2. 가지 ②: 4계층에서 timeout이 어떻게 구현되는가

### 2.1 핵심 질문

> "Socket.read()가 어디서 blocking되나? timeout은 어디서 측정되나?"

### 2.2 한 장 그림 — 호출 스택의 4계층

```
┌──────────────────────────────────────────────────────────┐
│ ④ Application (Spring Controller, Service)                │
│    - 외부 API 호출, DB 호출                                 │
│    - 비즈니스 timeout (deadline propagation, circuit)      │
└─────────────────────────┬────────────────────────────────┘
                          │
┌─────────────────────────▼────────────────────────────────┐
│ ③ HTTP client / JDBC driver                                │
│    - Apache HttpClient, OkHttp, Spring RestTemplate        │
│    - HikariCP, postgresql-jdbc                             │
│    - Connection pool, retry, redirect, response parsing    │
│    - 자체 timeout: callTimeout, queryTimeout, ...           │
└─────────────────────────┬────────────────────────────────┘
                          │
┌─────────────────────────▼────────────────────────────────┐
│ ② JVM Socket layer                                         │
│    - java.net.Socket (BIO) — blocking read/write           │
│    - java.nio.SocketChannel + Selector — non-blocking      │
│    - AsynchronousSocketChannel (NIO.2) — completion        │
│    - SO_TIMEOUT, CONNECT_TIMEOUT 옵션                       │
└─────────────────────────┬────────────────────────────────┘
                          │ syscall
┌─────────────────────────▼────────────────────────────────┐
│ ① OS Kernel (Linux/BSD)                                    │
│    - connect(), send(), recv(), epoll_wait()               │
│    - TCP state machine, retransmission, receive buffer     │
│    - SO_RCVTIMEO, SO_SNDTIMEO, TCP_USER_TIMEOUT            │
│    - tcp_syn_retries, tcp_keepalive_time                   │
└──────────────────────────────────────────────────────────┘
```

### 2.3 키워드 1 — ① OS Kernel 계층

```
[recv() syscall 흐름]

  user space                 kernel space
  ──────────                 ────────────
                             
  recv(fd, buf, len) ──────► sys_recvfrom()
                              │
                              ├─ socket fd → struct sock 찾기
                              │
                              ├─ TCP receive queue 확인
                              │   ├─ 데이터 있음 → copy_to_user(buf) → return n
                              │   └─ 비어있음 → ▼
                              │
                              ├─ SO_RCVTIMEO 확인 → timer 설정
                              │
                              ├─ schedule_timeout() — process sleep
                              │   ├─ 데이터 도착 → wake_up → copy → return
                              │   ├─ timer 만료 → return -1, errno=EAGAIN
                              │   └─ signal 도착 → return -1, errno=EINTR

[connect() syscall 흐름]

  connect(fd, addr) ────────► sys_connect()
                              │
                              ├─ TCP state: CLOSED → SYN_SENT (SYN 전송)
                              │
                              ├─ SO_SNDTIMEO 또는 connect timer
                              │
                              ├─ wait for SYN-ACK
                              │   ├─ SYN-ACK 수신 → SYN_SENT → ESTABLISHED → return 0
                              │   ├─ retransmit (1s, 2s, 4s, ... tcp_syn_retries)
                              │   ├─ RST 수신 → return -1, errno=ECONNREFUSED
                              │   └─ timer 만료 → return -1, errno=ETIMEDOUT
```

→ 모든 timeout은 결국 **kernel timer + sleeping process의 wake-up 메커니즘**.

### 2.4 키워드 2 — ② JVM Socket layer

**BIO (java.net.Socket)**:
```java
// 내부 구현 (단순화)
public int read() throws IOException {
    // SocketInputStream.read()
    // → SocketImpl.read()
    // → native socketRead0(fd, buf, len, timeout)
    // → JNI에서 recv() syscall
}
```

OpenJDK 소스 (`src/java.base/share/native/libnet/SocketImpl.c`):
- `socketRead0()` JNI 함수
- `select()` / `poll()`로 timeout 측정 후 `recv()` 호출
- 또는 `SO_RCVTIMEO` socket option 설정 후 직접 `recv()`

**NIO (java.nio.SocketChannel + Selector)**:
```java
SocketChannel ch = SocketChannel.open();
ch.configureBlocking(false);   // non-blocking
Selector sel = Selector.open();
ch.register(sel, OP_READ);

sel.select(timeoutMs);   // ← timeout은 epoll_wait에서 측정
                          // → epoll_wait(epfd, events, ..., timeoutMs)
```

→ Selector 기반은 한 thread가 수천 connection의 timeout을 일괄 관리.

**AsynchronousSocketChannel (NIO.2, JDK 7+)**:
```java
asyncCh.read(buf, timeout, TimeUnit.MILLISECONDS, attachment, handler);
// → completion callback으로 결과 전달
// → 내부적으로 OS의 epoll/kqueue + thread pool
```

### 2.5 키워드 3 — ③ HTTP client / JDBC driver

| Layer | 옵션 이름 | 매핑되는 OS 계층 |
|---|---|---|
| Apache `connectTimeout` | TCP connect | `connect()` + timer |
| Apache `socketTimeout` | recv idle | SO_RCVTIMEO |
| Apache `connectionRequestTimeout` | **pool wait** | application timer (kernel 무관) |
| OkHttp `callTimeout` | 전체 호출 | application timer (Executor + Future.cancel) |
| HikariCP `connectionTimeout` | pool에서 connection 빌리기 | application timer |
| HikariCP `validationTimeout` | connection ping | TCP + DB protocol |
| JDBC `socketTimeout` | recv idle | SO_RCVTIMEO |
| JDBC `Statement.setQueryTimeout` | DB가 SQL 강제 종료 | DB 측 cancel signal |

→ HTTP client / JDBC의 옵션들은 결국 **kernel timer + application timer의 조합**.

### 2.6 키워드 4 — ④ Application 계층

```java
// deadline propagation 패턴
@RestController
class OrderController {
    @GetMapping("/order/{id}")
    Order get(@PathVariable Long id) {
        long deadline = System.currentTimeMillis() + 3000;
        
        // 각 외부 호출에 deadline 까지의 남은 시간만 허용
        long remaining = deadline - System.currentTimeMillis();
        User u = userClient.get(id, remaining);
        
        remaining = deadline - System.currentTimeMillis();
        Inventory inv = invClient.get(id, remaining);
        // ...
    }
}
```

→ gRPC, Envoy/Istio mesh가 이 패턴을 자동화 (header로 deadline 전파).

---

## 3. 가지 ③: HTTP Client별 timeout 옵션 ⭐

### 3.1 핵심 질문

> "Spring RestTemplate, OkHttp, WebClient 각각의 timeout 옵션은? 무엇이 어디로 매핑되나?"

### 3.2 한 장 그림 — 라이브러리별 매핑

```
                  Connect    Read       Write     Pool wait   Total
                  =========  =========  ========  ==========  ========
Apache HttpClient connect    socket     socket    connection  ✗
                  Timeout    Timeout    Timeout   Request     (5.0에서
                                                  Timeout      ResponseTimeout)
                                                                
OkHttp            connect    read       write     -           call
                  Timeout    Timeout    Timeout   (pool 내장)  Timeout ★
                                                                
Java 11 HttpClient connect   -          -         -           HttpRequest
                  Timeout                                       .timeout ★
                                                                
WebClient         CONNECT_   response   -         maxIdle     Mono
(Reactor Netty)   TIMEOUT_   Timeout                          .timeout()
                  MILLIS
                                                                
Feign             connect    read       -         -           -
                  Timeout    Timeout
                                                                
gRPC              channel    -          -         -           deadline ★
                  shutdown                                      (per-call)
```

★ = 권장 (전체를 끊을 수 있는 옵션)

### 3.3 Apache HttpClient (PoolingHttpClient)

**4.x (legacy)**:
```java
RequestConfig config = RequestConfig.custom()
    .setConnectTimeout(3000)              // TCP 3-way
    .setSocketTimeout(5000)               // SO_TIMEOUT (read idle)
    .setConnectionRequestTimeout(2000)    // ★ pool에서 빌리기 wait
    .build();

CloseableHttpClient client = HttpClients.custom()
    .setDefaultRequestConfig(config)
    .setConnectionManager(new PoolingHttpClientConnectionManager())
    .build();
```

**핵심 옵션**:
- `connectTimeout` — TCP 3-way handshake
- `socketTimeout` — recv idle (SO_TIMEOUT)
- `connectionRequestTimeout` — **pool에서 connection 빌리는 시간** (★ 누락 빈번)

**Apache 5.x**:
```java
RequestConfig config = RequestConfig.custom()
    .setConnectTimeout(Timeout.ofSeconds(3))
    .setResponseTimeout(Timeout.ofSeconds(5))  // 전체 응답 timeout (신규)
    .setConnectionRequestTimeout(Timeout.ofSeconds(2))
    .build();
```

- 5.x는 `socketTimeout` → `responseTimeout`으로 의미 명확화

### 3.4 OkHttp ⭐ 가장 단순하고 강력

```java
OkHttpClient client = new OkHttpClient.Builder()
    .connectTimeout(3, TimeUnit.SECONDS)    // TCP 3-way
    .readTimeout(5, TimeUnit.SECONDS)        // recv idle
    .writeTimeout(5, TimeUnit.SECONDS)       // send buffer
    .callTimeout(10, TimeUnit.SECONDS)       // ★ 전체 호출 (강력 권장)
    .build();
```

**callTimeout이 핵심**:
- redirect 따라가도, retry해도, 전체 시간 상한.
- 내부 구현: `Dispatcher` 안의 `ScheduledExecutorService`로 `cancel()` 호출.
- 모든 외부 호출에 **반드시 명시** (OkHttp 4.x+).

### 3.5 Java 11 HttpClient (java.net.http)

```java
HttpClient client = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(3))   // builder-level
    .build();

HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create("https://api.example.com/x"))
    .timeout(Duration.ofSeconds(10))         // ★ request-level total
    .GET()
    .build();
```

- `connectTimeout`은 builder-level (모든 request 공통)
- `HttpRequest.timeout`은 request-level total (가장 중요)
- Read timeout / Write timeout 별도 옵션 **없음** — 전체 timeout만 있음 (단순)

### 3.6 Spring RestTemplate

`RestTemplate`은 `ClientHttpRequestFactory`에 따라 다르다.

**SimpleClientHttpRequestFactory (URLConnection 기반)**:
```java
SimpleClientHttpRequestFactory f = new SimpleClientHttpRequestFactory();
f.setConnectTimeout(3000);  // → URLConnection.setConnectTimeout
f.setReadTimeout(5000);     // → URLConnection.setReadTimeout
RestTemplate rt = new RestTemplate(f);
```

- pool 없음 → 매 요청마다 새 connection (성능 나쁨, 보통 안 씀)

**HttpComponentsClientHttpRequestFactory (Apache HttpClient 기반)**:
```java
PoolingHttpClientConnectionManager cm = new PoolingHttpClientConnectionManager();
cm.setMaxTotal(200);
cm.setDefaultMaxPerRoute(20);

CloseableHttpClient http = HttpClients.custom()
    .setConnectionManager(cm)
    .setDefaultRequestConfig(RequestConfig.custom()
        .setConnectTimeout(3000)
        .setSocketTimeout(5000)
        .setConnectionRequestTimeout(2000)  // ★ 잊지 마라
        .build())
    .build();

HttpComponentsClientHttpRequestFactory f = new HttpComponentsClientHttpRequestFactory(http);
RestTemplate rt = new RestTemplate(f);
```

- Apache HttpClient의 모든 옵션 사용 가능
- 대부분의 Spring 앱 (Boot 2.x)이 사용

### 3.7 Spring WebClient (Reactor Netty)

```java
HttpClient httpClient = HttpClient.create(ConnectionProvider.builder("pool")
        .maxConnections(200)
        .pendingAcquireTimeout(Duration.ofSeconds(2))   // pool wait
        .maxIdleTime(Duration.ofSeconds(30))             // idle 후 close
        .build())
    .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 3000)  // TCP connect
    .responseTimeout(Duration.ofSeconds(5))               // 응답 timeout
    .doOnConnected(conn -> conn
        .addHandlerLast(new ReadTimeoutHandler(5))         // Netty handler
        .addHandlerLast(new WriteTimeoutHandler(5)));

WebClient client = WebClient.builder()
    .clientConnector(new ReactorClientHttpConnector(httpClient))
    .build();

// 호출 시 reactive timeout (★ 최후 보루)
Mono<Response> resp = client.get()
    .uri("/x")
    .retrieve()
    .bodyToMono(Response.class)
    .timeout(Duration.ofSeconds(10));  // ★ 전체 mono timeout
```

**WebClient는 옵션이 많고 흩어져 있다** — 누락 빈번:
- `ChannelOption.CONNECT_TIMEOUT_MILLIS` — TCP connect
- `responseTimeout` — Reactor Netty의 응답 timeout
- `ReadTimeoutHandler` — Netty channel level
- `pendingAcquireTimeout` — connection pool wait
- `Mono.timeout()` — reactive operator (최후 보루)

→ 다 빼먹으면 영원히 hang.

### 3.8 Feign / OpenFeign

```java
@FeignClient(name = "user-service",
    configuration = UserClientConfig.class)
interface UserClient {
    @GetMapping("/user/{id}")
    User get(@PathVariable Long id);
}

class UserClientConfig {
    @Bean Request.Options requestOptions() {
        return new Request.Options(
            3000, TimeUnit.MILLISECONDS,   // connectTimeout
            5000, TimeUnit.MILLISECONDS,   // readTimeout
            true);                          // followRedirects
    }
}
```

- 내부적으로 Apache HttpClient / OkHttp / Java 11 HttpClient 중 선택
- Resilience4j / Hystrix와 같이 쓰는 게 일반적

### 3.9 gRPC ⭐ deadline propagation의 모범

```java
// per-call deadline (★ 권장)
ManagedChannel channel = ManagedChannelBuilder.forAddress("host", 50051).build();
UserServiceGrpc.UserServiceBlockingStub stub = UserServiceGrpc.newBlockingStub(channel)
    .withDeadlineAfter(5, TimeUnit.SECONDS);  // ★

User user = stub.getUser(req);
```

**deadline propagation**:
- gRPC는 deadline을 HTTP header로 전파.
- Service A → B → C 호출 체인에서, A가 5초 deadline이면 B/C도 같은 deadline 인식.
- C에서 남은 시간이 음수면 RPC 시작 자체 안 함.
- → 캐스케이딩 hang 자동 방지.

```
A (deadline=5s) ─► B (남은 3s) ─► C (남은 1s)
                                   │
                                   └─ DB query에 1s timeout 자동 설정
```

→ REST + manual timeout보다 훨씬 우수. 마이크로서비스 권장.

---

## 4. 가지 ④: JDBC timeout — 4개의 중첩 ⭐

### 4.1 핵심 질문

> "DB hang이 발생하면 어떤 timeout이 끊어야 하나?"

### 4.2 한 장 그림 — 4개의 timeout이 중첩

```
┌─────────────────────────────────────────────────────────────────┐
│ App 코드: connection.prepareStatement(sql).executeQuery()        │
│                                                                  │
│ ① HikariCP.getConnection() — pool에서 connection 빌리기            │
│    │                                                              │
│    └─ connectionTimeout (default 30s)                             │
│       └─ pool 고갈 시 여기서 막힘                                  │
│                                                                  │
│ ② 새 connection 만들 때 (pool에 없으면)                            │
│    └─ driver의 connectTimeout                                     │
│       └─ DB로 TCP 3-way handshake                                 │
│                                                                  │
│ ③ Statement.executeQuery() 호출                                   │
│    └─ Statement.setQueryTimeout(N)  ★ DB가 SQL 강제 종료            │
│    └─ socketTimeout — TCP recv idle                               │
│       └─ DB가 응답을 안 보내면 여기서 끊김                          │
│                                                                  │
│ ④ DB 측 자체 timeout                                              │
│    └─ PostgreSQL: statement_timeout                               │
│    └─ MySQL: max_execution_time, wait_timeout                     │
│       └─ DB가 자기 SQL을 죽임                                       │
└─────────────────────────────────────────────────────────────────┘
```

### 4.3 키워드 1 — HikariCP connectionTimeout (pool wait)

```java
HikariConfig config = new HikariConfig();
config.setJdbcUrl("jdbc:postgresql://db:5432/app");
config.setMaximumPoolSize(20);
config.setConnectionTimeout(3000);   // ★ pool wait (default 30000)
config.setValidationTimeout(2000);   // connection ping
config.setIdleTimeout(600000);       // 10분 후 idle conn close
config.setMaxLifetime(1800000);      // 30분 후 강제 교체 (★ 중요)
config.setLeakDetectionThreshold(5000);  // 5초 잡고 안 놓으면 stack 출력
```

**connectionTimeout**:
- pool에 idle connection이 있고 다 사용 중 → `getConnection()`이 wait.
- 이 시간 안에 못 받으면 `SQLTransientConnectionException`.
- default 30초 — production에서 너무 김. 3~5초 권장.

### 4.4 키워드 2 — driver의 socketTimeout (recv idle)

JDBC URL에 옵션으로:
```
jdbc:postgresql://db:5432/app?connectTimeout=3&socketTimeout=10
jdbc:mysql://db:3306/app?connectTimeout=3000&socketTimeout=10000
```

또는 HikariCP의 `dataSourceProperties`:
```java
config.addDataSourceProperty("socketTimeout", 10);  // seconds (postgres)
config.addDataSourceProperty("connectTimeout", 3);  // seconds (postgres)
```

**socketTimeout 누락 시**:
- DB가 hang (예: VACUUM full, lock wait)되면 client는 영원히 recv() block.
- HikariCP가 connection을 회수도 못 함 (사용 중이므로).
- 결국 pool 고갈.

### 4.5 키워드 3 — Statement.setQueryTimeout (★ 최후 보루)

```java
PreparedStatement ps = conn.prepareStatement(sql);
ps.setQueryTimeout(5);  // ★ 5초 (seconds, ms 아님 주의)
ResultSet rs = ps.executeQuery();
```

**어떻게 동작하나**:
- JDBC driver가 별도 timer thread를 띄움.
- Timeout 만료 → `Statement.cancel()` 호출 → DB에 cancel 요청 송신.
- DB가 그 query를 죽임 (PostgreSQL: `pg_cancel_backend`).
- driver는 `SQLException` throw.

**왜 socketTimeout과 별도로 필요한가**:
- DB가 lock wait 중이면 **socket으로는 정상 통신 중**. recv()가 idle 아님.
- → socketTimeout으로는 못 잡음.
- queryTimeout만이 잡을 수 있음.

### 4.6 키워드 4 — DB 측 statement_timeout

```sql
-- PostgreSQL: 세션 단위
SET statement_timeout = '5s';

-- 또는 RDS/postgresql.conf:
statement_timeout = 5000   -- ms

-- MySQL:
SET SESSION max_execution_time = 5000;   -- ms
```

**왜 필요**:
- client side queryTimeout은 client가 살아있을 때만 동작.
- client가 죽거나 (kill -9), 네트워크 단절 → cancel 못 보냄.
- DB는 그 query를 영원히 실행.
- → DB 측 timeout이 백업 방어선.

**Best practice**: client-side queryTimeout (예: 5s) < DB statement_timeout (예: 10s) — client가 먼저 시도하고, 안 되면 DB가 죽임.

### 4.7 4개 중첩 — 최후 안전 순서

```
요청 시작
   │
   ▼
┌──────────────────────────────────────────────┐
│ ① HikariCP.getConnection(timeout=3s)         │
│   pool wait                                  │
└──────────────┬───────────────────────────────┘
               │ 빌림 성공
               ▼
┌──────────────────────────────────────────────┐
│ ② Statement.setQueryTimeout(5s)              │
│   → client-side timer 시작                    │
└──────────────┬───────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────┐
│ ③ socket으로 query 전송, recv() wait          │
│   socketTimeout=10s — recv idle              │
└──────────────┬───────────────────────────────┘
               │
               ▼
┌──────────────────────────────────────────────┐
│ ④ DB 측 statement_timeout=10s — 자기 query 죽임 │
└──────────────────────────────────────────────┘

권장 시간 관계:
  HikariCP connectionTimeout (3s)
    < Statement queryTimeout (5s) 
    < socketTimeout (10s) 
    < DB statement_timeout (10s)
    
앞에서 끊는 게 좋음. 외부에서 응답성 유지.
```

### 4.8 운영 함정 사례

```
시나리오: "장애 발생 시 HikariCP가 자꾸 connection 30초 timeout 후 끊김"

원인 분석:
  - socketTimeout 안 걸음
  - DB hang (lock wait)
  - 기존 사용 중 connection들은 영원히 recv() block
  - 새 요청이 pool에서 connection 빌리려고 wait
  - 30초 후 connectionTimeout
  
근본 해결:
  - JDBC URL에 socketTimeout=10
  - Statement.setQueryTimeout(5) (또는 Spring @Transactional(timeout=5))
  - DB statement_timeout=10s (백업)
```

---

## 5. 가지 ⑤: 함정과 패턴 — Cascading, Pool wait, Stale connection

### 5.1 핵심 질문

> "외부 호출 timeout을 빼먹으면 production에서 어떤 장애가 나나?"

### 5.2 키워드 1 — Cascading failure (★ 가장 흔한 장애)

```
[정상 상태]
┌────────────┐     ┌────────────┐     ┌────────────┐
│ Tomcat     │     │ 외부 API    │     │ DB         │
│ thread=200 │────►│ p99=100ms  │────►│ p99=20ms   │
│ qps=500    │     │ ok         │     │ ok         │
└────────────┘     └────────────┘     └────────────┘
   요청 처리 속도: 평균 120ms
   동시 in-flight: 500 * 0.12 = 60 thread

[외부 API 응답이 느려짐]
┌────────────┐     ┌────────────┐     ┌────────────┐
│ Tomcat     │     │ 외부 API    │     │ DB         │
│ thread=200 │────►│ 응답=30초   │     │ 정상        │
│            │     │ (혹은 hang) │     │            │
└────────────┘     └────────────┘     └────────────┘

[timeout 미설정 시]
  - thread 1: 외부 API 30초 대기 중
  - thread 2: 외부 API 30초 대기 중
  - ...
  - thread 200: 외부 API 30초 대기 중
  
  → 모든 thread가 외부 API recv() block
  → 새 요청 → "queue full" → 503
  → Health check도 응답 못 함 → LB가 instance kill
  → 옆 instance로 load 이동 → 같은 증상
  → 시스템 전체 마비
```

**해결 4단계**:
1. **timeout 명시** (모든 외부 호출).
2. **circuit breaker** (실패 누적 시 fast-fail).
3. **bulkhead** (외부 호출별 별도 thread pool).
4. **graceful degradation** (외부 API 실패 시 fallback 응답).

### 5.3 키워드 2 — Stale connection ("Connection reset by peer")

```
[시나리오]
1. Service가 DB pool에서 connection을 빌려 idle 상태로 풀에 반납
2. 방화벽/NAT/AWS NLB가 idle connection을 ~5분 후 silent drop
   (응답 없이 connection table에서 제거)
3. Service가 다음에 그 connection을 pool에서 꺼냄
4. SQL 쿼리 전송 → peer 측은 모르는 connection → RST 응답
5. "Connection reset by peer" SQLException
6. App 에러
```

**해결**:
- HikariCP `maxLifetime` 짧게 (방화벽 idle timeout보다 짧게)
- HikariCP `keepaliveTime` 활성화 — 주기적 ping
- TCP `SO_KEEPALIVE` (kernel keepalive)
- HTTP client는 connection validation on borrow

```java
config.setMaxLifetime(900_000);    // 15분 (NLB idle=350s 가정)
config.setKeepaliveTime(60_000);   // 60초마다 ping
```

### 5.4 키워드 3 — Pool wait < Operation timeout

**잘못된 설정 예**:
```
HikariCP connectionTimeout = 30s
Tomcat connection-timeout (요청 처리) = 20s
```

→ 요청은 20초에 죽는데, pool wait이 30초 → 다음 요청이 그 connection을 못 받음.

**올바른 순서**:
```
HikariCP connectionTimeout (3s)
  < socket read timeout (10s)
  < Statement queryTimeout (5s)  
  < @Transactional timeout (15s)
  < Tomcat connection-timeout (20s)
  < LB upstream timeout (30s)
  < User patience (3min)
```

→ **안쪽 timeout이 바깥쪽보다 짧아야** 한다. 안쪽이 먼저 fail하고 응답을 빨리 돌려야 자원 회수.

### 5.5 키워드 4 — Circuit breaker 패턴

```java
// Resilience4j 예시
CircuitBreakerConfig cbConfig = CircuitBreakerConfig.custom()
    .failureRateThreshold(50)              // 50% 실패 시 open
    .slidingWindowSize(20)
    .waitDurationInOpenState(Duration.ofSeconds(30))
    .build();

TimeLimiterConfig tlConfig = TimeLimiterConfig.custom()
    .timeoutDuration(Duration.ofSeconds(3))  // ★ 호출 전체 timeout
    .build();

// 사용
Supplier<User> supplier = CircuitBreaker
    .decorateSupplier(cb, () -> userClient.get(id));
supplier = TimeLimiter
    .decorateFutureSupplier(tl, () -> CompletableFuture.supplyAsync(supplier));
```

**circuit breaker가 timeout과 같이 동작하는 이유**:
- timeout 단독: 매 호출마다 N초 대기 후 fail → resource (thread, connection) 낭비.
- circuit + timeout: 일정 실패 누적 후 N초 동안 호출 자체 차단 → resource 보호.

### 5.6 키워드 5 — Reactive (WebFlux)의 함정

```java
// 잘못된 예 (timeout 누락)
public Mono<Order> getOrder(Long id) {
    return webClient.get().uri("/order/{id}", id)
        .retrieve()
        .bodyToMono(Order.class);
        // ★ Mono.timeout() 없음 → 무한 대기 가능
}
```

→ Reactor의 hang은 thread pool 고갈 대신 **event loop hang**.
→ Netty event loop가 응답 대기 → 그 loop에 할당된 모든 connection이 stuck.
→ "thread만 늘리면 되겠지" 통하지 않음 (event loop는 적은 수의 thread).

**올바른 예**:
```java
public Mono<Order> getOrder(Long id) {
    return webClient.get().uri("/order/{id}", id)
        .retrieve()
        .bodyToMono(Order.class)
        .timeout(Duration.ofSeconds(3))      // ★ 필수
        .onErrorResume(TimeoutException.class, e -> Mono.just(Order.empty()));
}
```

### 5.7 함정 요약 표

| 함정 | 증상 | 해결 |
|---|---|---|
| **timeout 누락** | Thread pool 고갈, 503 | 4종 timeout 명시 |
| **cascading failure** | 전체 시스템 마비 | timeout + circuit + bulkhead |
| **stale connection** | "Connection reset" | maxLifetime, keepalive |
| **pool wait > op** | 자원 회수 못 함 | 안쪽 < 바깥쪽 순서 |
| **WebFlux hang** | event loop stuck | Mono.timeout() |

---

## 6. 역사 — BIO Socket → NIO Selector → HTTP client → Reactive

### 6.1 진화 타임라인

```
JDK 1.0 (1996)
   java.net.Socket — BIO
   timeout API 없음. infinite hang 가능
   ↓
JDK 1.4 (2002) — NIO
   java.nio.SocketChannel + Selector
   non-blocking, select(timeout)
   → 한 thread가 수천 connection의 timeout 일괄 관리
   ↓
JDK 5 (2004)
   Apache HttpClient 3.x (Jakarta Commons)
   외부 라이브러리로 timeout / retry / pool 추상화
   ↓
JDK 7 (2011) — NIO.2
   AsynchronousSocketChannel — completion handler
   timeout 인자 직접 지원
   ↓
JDK 8 (2014)
   Apache HttpClient 4.x — 표준화된 RequestConfig
   OkHttp 등장 (Square, 2013)
   ↓
JDK 9 (2017) — HTTP/2 incubator
   ↓
JDK 11 (2018) — java.net.http (표준 HttpClient)
   HTTP/2 지원, async + sync API
   Request.timeout 표준화
   ↓
JDK 17~21 (2021~)
   Virtual Thread (JDK 21) — BIO 모델 부활
   "이제는 thread 수가 안 비싸니 BIO도 OK"
   단, timeout 누락의 위험은 그대로
```

### 6.2 왜 timeout 모델이 진화했나

```
BIO 시대 (~JDK 1.3): 
   문제: thread per connection. timeout 누락 = thread 무한 점유.
   limit: thread당 ~1MB stack → 수천 thread 어려움.

NIO 시대 (JDK 1.4+):
   해결: Selector + 한 thread가 수만 connection 관리.
   timeout: select(timeoutMs) 단위로 측정.
   비용: 코드 복잡 (state machine).

Reactive (RxJava, Reactor, ~2015):
   해결: 코드 가독성 + non-blocking.
   timeout: Mono.timeout() operator.
   비용: debugging 어려움, async stack trace.

Virtual Thread (JDK 21):
   해결: BIO 코드 그대로 + 수십만 thread.
   timeout: 여전히 명시 필요.
   비용: pinning 함정 (synchronized + 외부 I/O).
```

→ **timeout 명시의 필요성은 모든 시대를 관통한다**.

---

## 7. 측정·진단 — strace, tcpdump, jstack, JFR

### 7.1 strace — kernel syscall 직접 관찰

```bash
# 특정 JVM process의 network syscall 추적
strace -f -e trace=network,read,write -p <pid> 2>&1 | head -50

# 출력 예시:
# [pid 12345] connect(7, {sa_family=AF_INET, sin_port=htons(443), 
#             sin_addr=inet_addr("1.2.3.4")}, 16) = -1 EINPROGRESS
# [pid 12345] poll([{fd=7, events=POLLOUT}], 1, 3000) = 0 (Timeout)
# [pid 12345] close(7) = 0
# → connect()가 3초 timeout으로 끊김

# read timeout 진단
# [pid 12345] recvfrom(7, ...) = -1 EAGAIN (Resource temporarily unavailable)
# → SO_RCVTIMEO 만료
```

**언제 쓰나**:
- "Java 코드에는 timeout 설정했는데 정말 끊기나?" 검증
- "어디서 hang이 발생하나" (connect / recv / send?)

### 7.2 tcpdump — wire-level 검증

```bash
# DB 통신 캡처
sudo tcpdump -i any 'port 5432' -w db.pcap

# Wireshark에서 분석:
# - SYN → SYN-ACK 시간 확인 (network latency)
# - Server 응답이 늦은지, network latency가 큰지 구분
# - RST 발생 시점 — 누가 끊었나
```

**구분 핵심**:
```
SYN 보냈는데 SYN-ACK 안 옴
   → connection timeout 영역 (방화벽 drop, host down)

SYN-ACK 빨리 옴, 그 후 long pause
   → DB / 서버 측 처리 지연 → query timeout 또는 socket timeout 영역

RST가 client에서 보냄
   → client측 timeout 만료로 close
   
RST가 server에서 보냄  
   → server측 timeout (예: keepalive 만료, idle close)
```

### 7.3 ss — 현재 TCP 상태

```bash
# 특정 port의 연결 상태
ss -tn state established '( dport = :5432 or sport = :5432 )'

# 출력:
# State    Recv-Q Send-Q  Local Address:Port   Peer Address:Port
# ESTAB    0      0       10.0.0.5:54321       10.0.0.10:5432

# Recv-Q > 0: 우리가 아직 read 안 한 데이터 있음 (app이 안 읽는 중?)
# Send-Q > 0: 우리가 보냈지만 peer가 ACK 안 한 데이터 (peer 느림?)

# pool에 stale connection이 얼마나 있나
ss -tn state established | wc -l

# TIME_WAIT 누적 (단명 connection이 많을 때)
ss -tn state time-wait | wc -l
```

### 7.4 jstack — Java thread가 어디서 막혔나

```bash
jstack <pid> > thread_dump.txt
```

**Socket read에서 막힌 thread**:
```
"http-nio-8080-exec-3" #45 daemon prio=5 os_prio=0 tid=0x... nid=0x...
   java.lang.Thread.State: RUNNABLE
   at sun.nio.ch.SocketDispatcher.read0(Native Method)
   at sun.nio.ch.SocketDispatcher.read(SocketDispatcher.java:46)
   at sun.nio.ch.IOUtil.readIntoNativeBuffer(IOUtil.java:227)
   ...
   at java.net.Socket$SocketInputStream.read(...)
   at org.postgresql.core.PGStream.receiveInteger4(...)
   at org.postgresql.core.v3.QueryExecutorImpl.processResults(...)
   ★ DB 응답 대기 중!
```

**HTTP client에서 막힌 thread**:
```
   at sun.nio.ch.SocketDispatcher.read0(Native Method)
   ...
   at org.apache.http.impl.io.SessionInputBufferImpl.read(...)
   at org.apache.http.impl.io.DefaultHttpResponseParser.parseHead(...)
   ★ HTTP 응답 대기 중!
```

**Pool wait에서 막힌 thread**:
```
"http-nio-8080-exec-7" #49
   java.lang.Thread.State: TIMED_WAITING (parking)
   at jdk.internal.misc.Unsafe.park(Native Method)
   at java.util.concurrent.locks.LockSupport.parkNanos(...)
   at com.zaxxer.hikari.util.ConcurrentBag.borrow(...)
   ★ HikariCP pool wait!
```

**진단 패턴**:
- jstack 100개 떴는데 90개가 같은 stack → 거기가 병목
- BLOCKED 많으면 lock contention
- TIMED_WAITING 많으면 pool wait
- RUNNABLE인데 socket read → DB / 외부 응답 대기

### 7.5 JFR — Socket Read/Write events (JDK 11+)

```bash
# 60초 기록
jcmd <pid> JFR.start name=net duration=60s filename=net.jfr

# JFR Mission Control 또는 jfr 명령으로 분석
jfr print --events jdk.SocketRead,jdk.SocketWrite net.jfr | head -50
```

**`jdk.SocketRead` event**:
- duration (얼마 걸렸나)
- host, port
- bytesRead
- stack trace

→ "어느 외부 호출이 느린가" 정량 분석. p99/p999 측정 가능.

### 7.6 async-profiler — wallclock mode

```bash
# wall-clock profiling (CPU + blocking 둘 다)
async-profiler -d 60 -e wall -f wall.html <pid>
```

CPU profiler는 RUNNABLE만 보임. wall-clock은 **blocking 시간 포함** → socket read에서 시간을 얼마나 쓰는지 보임.

### 7.7 chaos engineering — Toxiproxy, Pumba

```bash
# Toxiproxy: 의도적으로 latency 추가
toxiproxy-cli create -l 0.0.0.0:5433 -u db:5432 db_proxy
toxiproxy-cli toxic add -t latency -a latency=5000 db_proxy
# → 모든 DB 통신에 5초 지연. timeout 동작 검증.

# Pumba: 컨테이너 네트워크 chaos
pumba netem --duration 60s --tc-image gaiadocker/iproute2 delay --time 3000 app_container
```

→ 운영 전에 "timeout이 정말 동작하는가" 검증.

### 7.8 진단 시나리오 — "외부 API 호출 시 503 폭증"

```
1. 증상 — Tomcat thread 200 모두 점유. /actuator/health도 응답 못 함.

2. jstack 100개 채취 → 90개가 같은 stack:
     at SocketDispatcher.read0(Native Method)
     at ...
     at OkHttpCallExecutor.execute(...)
   → 외부 API 호출 read에서 막힘.

3. tcpdump 캡처:
     SYN → SYN-ACK 정상 (connect OK)
     POST request 전송 후 응답 없음 (peer가 처리 중)

4. 외부 API 측 확인 → DB lock 때문에 응답 못 보냄.

5. 우리 측 코드 확인 → OkHttp callTimeout 누락.

6. 조치:
     - OkHttp.callTimeout(3s) 추가
     - Resilience4j circuit breaker 추가
     - Fallback 응답 정의
     - 외부 API 측에는 별도 채널로 issue 제기

7. 검증:
     - Toxiproxy로 외부 API에 10초 지연 주입
     - 우리 측 응답이 3초 후 fallback 동작 확인
     - thread pool 안 막힘 확인
```

---

## 8. 면접 답변 워크플로우

### 8.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "Connection vs Read timeout 차이?" | ① 4종 | TCP 3-way vs recv idle |
| "Socket.read()가 어디서 막히나?" | ② 4계층 | OS recv() + SO_RCVTIMEO |
| "OkHttp / Apache 어떻게 다른가?" | ③ HTTP | callTimeout vs RequestConfig |
| "JDBC timeout 옵션이 왜 이렇게 많나?" | ④ JDBC | pool / driver / query / DB |
| "외부 API hang에 503 폭증?" | ⑤ 함정 | cascading + timeout 누락 |
| "stale connection / Connection reset?" | ⑤ 함정 | maxLifetime, keepalive |
| "WebClient에 timeout 어떻게 거나?" | ③ WebClient | 4-5개 옵션의 조합 |

### 8.2 답변 템플릿

예: "Connection timeout과 Read timeout이 어떻게 다른가요?"

> "Timeout은 hang을 끊는 안전판입니다 (← 루트).
> 4종이 있고 각각 OS의 다른 계층에서 발생합니다 (← 가지 ①).
> 
> **Connection timeout**은 TCP 3-way handshake — SYN → SYN-ACK → ACK까지의 시간. OS의 `connect()` syscall이 측정. Linux는 timeout 미설정 시 tcp_syn_retries=6으로 최대 127초까지 SYN 재전송.
> 
> **Read timeout**은 한 번의 `recv()` 호출이 데이터를 받기까지의 idle 시간. `setSoTimeout` 또는 `SO_RCVTIMEO`. 흔한 오해는 'Read timeout이 전체 응답 시간'이라는 것. 매 recv()마다 reset되므로 천천히 흘러들어오는 응답은 영원히 끊기지 않을 수 있습니다.
> 
> 그래서 외부 호출에는 두 개 외에 **Total/Call timeout**도 명시해야 합니다 — OkHttp의 callTimeout, Java 11 HttpClient의 HttpRequest.timeout, gRPC deadline.
> 
> 운영적으로 가장 흔한 장애는 timeout 누락에서 옵니다 (← 가지 ⑤). 외부 API hang → Tomcat thread 200개 점유 → 503 폭증 → 캐스케이딩 실패. circuit breaker + bulkhead와 같이 가야 안전합니다."

---

## 9. 꼬리질문 트리

### Q1 [가지 ①]. Connection timeout과 Read timeout이 어떻게 다른가요?

> Connection은 TCP 3-way (SYN→SYN-ACK→ACK)까지. `connect()` syscall + kernel timer.
> Read는 한 recv()의 idle 시간. SO_RCVTIMEO. 매 recv()마다 reset되므로 전체 응답 시간 아님.
> Total / Call timeout이 별도로 필요 — OkHttp.callTimeout, HttpRequest.timeout, gRPC deadline.

**🪝 Q1-1: Read timeout이 5초인데 응답이 1 byte씩 4초 간격으로 오면?**
> 영원히 끊기지 않음. 각 recv()는 4초 안에 1 byte 받으므로 timeout 미발동.
> → callTimeout / responseTimeout / Mono.timeout()가 최후 보루.

**🪝 Q1-2: connection timeout 미설정 시 Linux에서 얼마나 기다리나?**
> tcp_syn_retries=6 (default) → 1+2+4+8+16+32+64 = ~127초.
> 그 동안 thread가 점유됨.

### Q2 [가지 ②]. Java에서 Socket.read()가 정확히 어디서 blocking되나요?

> JVM → JNI native 함수 → kernel recv() syscall → kernel TCP receive queue 확인 → 비어있으면 process를 sleep 큐에 → 데이터 도착 또는 SO_RCVTIMEO timer 만료까지 sleep.
> Timer 만료 시 syscall은 -1 + EAGAIN → JNI에서 SocketTimeoutException으로 변환.

**🪝 Q2-1: NIO Selector에서는 어떻게 다른가?**
> non-blocking SocketChannel + Selector.select(timeoutMs).
> select() 내부는 epoll_wait(timeoutMs). 한 thread가 수만 connection의 timeout을 동시 관리.

### Q3 [가지 ③]. OkHttp와 Apache HttpClient의 timeout 옵션이 어떻게 다른가요?

> Apache (4.x): connectTimeout, socketTimeout, connectionRequestTimeout (★ pool wait).
> OkHttp: connectTimeout, readTimeout, writeTimeout, callTimeout (★ 전체 호출).
> OkHttp의 callTimeout은 redirect/retry 다 포함해서 전체 끊음 → 가장 권장.
> Apache는 5.x에서 responseTimeout 추가로 의미 명확화.

**🪝 Q3-1: Spring WebClient에 어떤 timeout을 어떻게 거나?**
> 4-5개 다 걸어야:
> - ChannelOption.CONNECT_TIMEOUT_MILLIS (TCP connect)
> - HttpClient.responseTimeout (응답 timeout)
> - ReadTimeoutHandler / WriteTimeoutHandler (Netty handler)
> - ConnectionProvider.pendingAcquireTimeout (pool wait)
> - Mono.timeout() (★ 최후 보루)
> 다 빼먹으면 event loop가 hang. WebFlux는 thread pool 늘려도 해결 안 됨.

### Q4 [가지 ④]. JDBC timeout이 왜 4개가 필요한가요?

> 각각 다른 단계를 보호:
> 1. HikariCP.connectionTimeout — pool에서 connection 빌리기. pool 고갈 방어.
> 2. driver.connectTimeout — TCP connect to DB. DB 다운 시 방어.
> 3. driver.socketTimeout — recv idle. DB 응답 없음 방어.
> 4. Statement.setQueryTimeout — DB가 SQL 죽임. DB lock wait 방어.
> 
> 추가로 DB 측 statement_timeout — client 죽었을 때 DB가 자기 query 죽임.
> 
> 핵심: socketTimeout만으로는 lock wait를 못 잡음 — DB가 정상적으로 응답 처리 중이므로 socket이 idle 아님. queryTimeout이 마지막 방어선.

**🪝 Q4-1: 권장 시간 관계는?**
> HikariCP connectionTimeout (3s) < Statement queryTimeout (5s) < socketTimeout (10s) < DB statement_timeout (10s).
> 안쪽이 먼저 fail해야 자원 회수 빠름.

### Q5 [가지 ⑤]. 외부 API hang으로 503 폭증이 일어나는 메커니즘은?

> 1. 외부 API 응답 느려짐.
> 2. timeout 없으면 매 호출이 30초+ 점유.
> 3. Tomcat thread 200개 모두 외부 API recv() block.
> 4. 새 요청 → "queue full" → 503.
> 5. Health check도 응답 못 함 → LB가 instance kill.
> 6. 옆 instance로 load 이동 → 같은 증상 → 캐스케이딩 마비.
> 
> 해결: timeout 명시 + circuit breaker + bulkhead + fallback.

**🪝 Q5-1: circuit breaker가 timeout과 어떻게 같이 동작하나?**
> timeout만 있으면 매 호출마다 N초 낭비. circuit breaker는 실패 누적 후 호출 자체 차단 (open state) → resource 보호.
> 일반 패턴: TimeLimiter (timeout) + CircuitBreaker (실패 누적) + Retry (선별적) + Bulkhead (격리).

**🪝 Q5-2: "Connection reset by peer"는 왜 일어나나?**
> Stale connection. pool에 idle 상태로 남아있던 connection을 방화벽/NLB가 silent drop (idle timeout 후). 다음 query 전송 시 peer가 모르는 connection → RST.
> 해결: maxLifetime 짧게 (방화벽 idle보다 짧게), keepalive, validation on borrow.

### Q6 (Killer) [모든 가지]. 외부 API 호출에서 어떤 thread는 5초에 끊기고 어떤 thread는 30초+ 점유합니다. 어떻게 진단합니까?

> **가설 후보**:
> 1. timeout이 일관되게 설정되지 않음 (코드 경로 분기)
> 2. retry 정책으로 누적
> 3. circuit breaker open 시 빠른 fail vs closed 시 정상 timeout
> 4. DNS lookup이 hang
> 5. NIO Selector 한 thread가 여러 connection 처리 중 일부만 영향
> 
> **진단 단계**:
> 1. **jstack 다회 채취** (5초 간격 5회) → hang된 thread의 stack 일관성 확인.
>    - 같은 stack에 30초+ 있으면 progress 없음.
>    - 다른 위치면 process는 진행 중.
> 
> 2. **5초에 끊기는 thread의 stack** → 어떤 timeout이 동작했나 확인 (Apache vs OkHttp vs JDBC).
> 
> 3. **strace로 syscall 수준 확인** — connect() / recv() 호출 시 timeout 인자가 정말 5초인지.
> 
> 4. **JFR `jdk.SocketRead` event** → host/port별 duration 분포. 특정 endpoint만 느린가?
> 
> 5. **tcpdump** → 5초 끊기는 case와 30초 hang case의 wire 차이 비교.
>    - 5초: client RST 보냄 (timeout 동작)
>    - 30초: client가 아무 RST 안 보냄 (timeout 미설정 또는 다른 경로)
> 
> 6. **코드 경로 분석**:
>    - 직접 호출 vs proxy/interceptor 거치는 경로
>    - 같은 client 인스턴스 vs 다른 인스턴스 (다른 RequestConfig)
>    - retry 라이브러리가 별도 client 사용?
> 
> 7. **가설 검증**: 의심 경로에 logging 추가, 또는 chaos injection (Toxiproxy로 의도적 hang)으로 timeout 동작 검증.
> 
> **흔한 답**: 메인 client는 timeout 설정 잘 됨, 하지만 error handler 안의 fallback client / metrics client / logging client가 default(=무한)로 설정됨. 부속 client들이 hang.

---

## 10. 학습 체크리스트

- [ ] 0장 마인드맵을 1분 이내로 그릴 수 있다 (루트 + 5가지 + 키워드 3개)
- [ ] 가지 ①: 4종 timeout을 시간축 그림에 위치시킬 수 있다 (connection / read / write / total)
- [ ] 가지 ①: Read timeout이 "전체 응답 시간이 아닌" 이유를 설명한다
- [ ] 가지 ②: Socket.read()의 4계층 호출 스택 (Kernel → JVM Socket → HTTP client → App)을 그린다
- [ ] 가지 ②: recv() syscall의 kernel 동작 (sleep queue + SO_RCVTIMEO timer)을 그린다
- [ ] 가지 ③: Apache HttpClient의 3 + 1 옵션 (connectionRequestTimeout 포함)을 외운다
- [ ] 가지 ③: OkHttp의 callTimeout이 왜 권장되는지 설명한다
- [ ] 가지 ③: WebClient에 timeout 거는 5가지 위치를 나열한다
- [ ] 가지 ④: JDBC 4개 timeout (pool wait / driver connect / driver socket / queryTimeout)의 책임 영역을 매핑한다
- [ ] 가지 ④: DB lock wait가 socketTimeout으로 안 잡히는 이유를 설명한다
- [ ] 가지 ⑤: cascading failure의 5단계 시나리오를 인용한다
- [ ] 가지 ⑤: stale connection의 해결책 (maxLifetime, keepalive)을 설명한다
- [ ] 7단 측정: strace, tcpdump, jstack, JFR로 timeout 동작을 검증하는 방법을 안다
- [ ] 9장 꼬리질문 6개에 답한다

---

## 11. 한 줄 요약 — 시니어가 배워가야 할 본질

> **"외부 호출에 timeout을 명시하지 않은 코드는 production에서 cascading hang으로 503 폭증을 일으킨다.**
> **Connection timeout은 TCP 3-way, Read timeout은 recv() idle, Write는 send buffer flush, Total은 전체 호출.**
> **4가지를 다 명시하고, pool wait < op < transaction < tomcat < LB 순서로 안쪽이 짧게.**
> **JDBC는 socketTimeout으로 DB lock wait를 못 잡으므로 Statement.setQueryTimeout이 최후 보루.**
> **circuit breaker + bulkhead + fallback과 함께 가야 안전. Chaos engineering으로 timeout 동작 검증."**

---

## 참고

- **OkHttp Timeout docs**: https://square.github.io/okhttp/recipes/#timeouts-kt-java
- **Apache HttpClient 5 Tutorial**: https://hc.apache.org/httpcomponents-client-5.2.x/
- **HikariCP Configuration**: https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby
- **gRPC Deadlines**: https://grpc.io/blog/deadlines/
- **Resilience4j**: https://resilience4j.readme.io/
- **Toxiproxy (chaos)**: https://github.com/Shopify/toxiproxy
- **Reactor Netty HttpClient**: https://projectreactor.io/docs/netty/release/reference/index.html#http-client
- **PostgreSQL JDBC properties**: https://jdbc.postgresql.org/documentation/use/#connection-parameters
