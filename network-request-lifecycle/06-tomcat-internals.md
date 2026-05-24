# 06. Tomcat Internals — byte stream을 HttpServletRequest로 변환하는 파이프라인

> "Tomcat은 NIO Connector의 Acceptor → Poller → Executor 3단 파이프라인으로 TCP byte stream을 HttpServletRequest로 변환하고, acceptCount × maxConnections × maxThreads 3대 한도가 connection의 여정을 통제한다."

---

## 0. 목차 — 백지에 그릴 6가지 가지

| 가지 | 핵심 |
|---|---|
| **① 구조** | Server → Service → Connector + Engine → Host → Context → Wrapper |
| **② Connector** | BIO/NIO/NIO2/APR (현재 NIO 표준), ProtocolHandler + Endpoint 추상화 |
| **③ 3단 파이프라인** | Acceptor (accept) → Poller (Selector) → Executor (Worker) |
| **④ ThreadPool** | TaskQueue override로 "thread 먼저, queue 나중" |
| **⑤ 한도 3종** | acceptCount(kernel) / maxConnections(Tomcat) / maxThreads(Worker) |
| **⑥ Lifecycle** | byte → header parse → RequestFacade → Filter → Servlet → 응답 |

---

## 1. 가지 ①: 구조 — Tomcat의 7층 계층

### 1.1 백지 그리기

```
[Server]                  ← JVM 프로세스 하나
   │
   └─ [Service "Catalina"]   ← Connector들 + Engine 1개
        ├─ [Connector port=8080 HTTP/1.1]
        │     └─ ProtocolHandler (Http11NioProtocol)
        │            └─ NioEndpoint (Acceptor + Poller + Executor)
        ├─ [Connector port=8443 SSL]
        └─ [Engine "Catalina"]
               └─ [Host "localhost"]
                      └─ [Context "/api"]
                             ├─ WebappClassLoader
                             ├─ Filters
                             └─ [Wrapper "DispatcherServlet"] ← Spring 진입
```

### 1.2 각 계층의 책임

| 계층 | 책임 | 인스턴스 수 |
|---|---|---|
| **Server** | JVM 프로세스. shutdown port listen, `await()` 메인 루프 | 1 |
| **Service** | Connector(들) + Engine 1개 그룹화 | 보통 1 |
| **Connector** | TCP 포트 listen, protocol 처리 | 포트마다 1 |
| **Engine** | request 라우팅 진입점 | Service당 1 |
| **Host** | 가상 호스트 (`Host:` 헤더 매칭) | 도메인마다 1 |
| **Context** | 웹 애플리케이션 = WAR = ServletContext | 앱마다 1 |
| **Wrapper** | Servlet 1개 감싸는 컨테이너 (lifecycle, mapping) | Servlet마다 1 |

> **DispatcherServlet은 Tomcat 입장에서 Wrapper 1개에 매핑된 평범한 Servlet.** Tomcat은 Spring을 모르고, Spring도 Tomcat을 모름 (Servlet API만 사용).

### 1.3 비유

> 호텔 체인: Server = 본사, Service = 호텔, Connector = 정문/후문, Engine = 로비, Host = 층, Context = 객실 사업, Wrapper = 객실 내 침대(Servlet).

---

## 2. 가지 ②: Connector — Protocol 처리의 추상화

### 2.1 3층 추상화

```
[Connector] ─── server.xml의 단위
   └─ [ProtocolHandler] ─── HTTP/1.1, HTTP/2, AJP 등 wire format
        └─ [Endpoint] ─── 실제 socket I/O 모델 (NIO/NIO2/APR)
             ├─ Acceptor
             ├─ Poller (NIO만)
             └─ Executor
```

이 3층 덕분에 같은 protocol을 다른 I/O 모델에서, 같은 I/O 모델로 다른 protocol을 실어나를 수 있다.

### 2.2 진화사 (한 문단)

Tomcat 4의 **BIO** (thread-per-connection)는 connection이 많아지면 thread 폭증. Tomcat 6의 **NIO** (Selector + 3단 분리)가 epoll/kqueue를 활용해 적은 thread로 수천 connection 처리. Tomcat 7의 **NIO2**는 OS native async (IOCP/aio)를 callback으로 노출했지만 일관성/디버깅 문제로 표준화 실패. **APR**(libtcnative + OpenSSL)은 SSL 성능 때문에 살아남았으나 JSSE 개선으로 점차 deprecate. Tomcat 8.5에서 BIO 제거, 9에서 HTTP/2, 10에서 Jakarta namespace, 10.1+에서 Virtual Thread Executor 지원. **현재 표준은 NIO**.

---

## 3. 가지 ③: NIO 3단 파이프라인 ⭐⭐ — 가장 중요

### 3.1 백지 그리기

```
                   [Client A, B, C, ... N]
                          │ TCP SYN
                          ▼
                   ┌────────────────────────┐
                   │ Kernel TCP stack        │
                   │  └─ accept queue       │ ← acceptCount
                   └────────┬───────────────┘
                            │ accept() blocking
                            ▼
                ┌───────────────────────┐
                │ Acceptor thread (1~N) │  ← serverSock.accept()
                │  → pollerQueue.add(ch)│  ★ Poller에 hand-off
                └──────────┬────────────┘
                           │
                           ▼
                ┌───────────────────────────┐
                │ Poller thread (1~N)        │  selector = Selector.open()
                │  ch.register(OP_READ)     │  ★ epoll_wait (non-blocking)
                │  selector.select()        │
                │  → executor.execute(...)  │  ★ Worker에 hand-off
                └──────────┬────────────────┘
                           │
                           ▼
                ┌────────────────────────────────────┐
                │ Worker thread (Executor pool)      │  ← maxThreads (default 200)
                │  http-nio-8080-exec-N              │
                │  1. byte read                      │
                │  2. Http11InputBuffer parse        │
                │  3. CoyoteRequest + RequestFacade  │
                │  4. Mapper → Wrapper → Filter      │
                │  5. Servlet.service()              │
                │  6. response write (byte)          │
                │  7. keepalive면 Poller 재등록      │
                └────────────────────────────────────┘
```

### 3.2 의사코드

```java
// === Acceptor ===
while (running) {
    SocketChannel ch = serverSocket.accept();   // blocking
    poller.register(ch);
}

// === Poller ===
while (running) {
    SocketChannel ch;
    while ((ch = pollerQueue.poll()) != null) {
        ch.configureBlocking(false);
        ch.register(selector, SelectionKey.OP_READ);
    }
    int n = selector.select(1000);  // epoll_wait
    for (SelectionKey key : selector.selectedKeys()) {
        if (key.isReadable()) {
            executor.execute(new SocketProcessor((SocketChannel) key.channel()));
        }
    }
}
```

### 3.3 왜 3단으로 나눴는가

각 단계의 병목 특성이 다르므로 thread 모델을 따로 둔다.

| 단계 | 작업 성격 | 왜 따로 thread? |
|---|---|---|
| **Acceptor** | `accept()` blocking | TCP 3-way handshake 완료 connection을 빠르게 빼야 kernel queue가 안 참 |
| **Poller** | `select()` non-blocking 다중 감시 | 수천 connection을 1 thread가 동시 감시 (epoll의 본질) |
| **Worker** | byte parse + Servlet + DB | 비즈니스 로직은 시간 들어서 thread 많이 둠 |

**keepalive**: Worker는 응답 write 후 채널을 다시 Poller로 register. 한 connection이 여러 요청을 처리하는 동안 Worker thread를 계속 잡고 있는 게 아니다.

### 3.4 소스 위치 (척추 5개)

```
org.apache.tomcat.util.net.NioEndpoint
   ├─ Acceptor (inner class, Runnable)         → serverSock.accept()
   ├─ Poller (inner class, Runnable)           → selector.select() + executor.execute()
   └─ SocketProcessor (inner class, Runnable)  → handler.process()

org.apache.coyote.http11.Http11Processor       → HTTP/1.1 처리 진입
   └─ Http11InputBuffer.parseRequestLine() / parseHeaders()

org.apache.catalina.connector.CoyoteAdapter    → Coyote → Catalina 다리
   └─ service() → pipeline.invoke()

org.apache.catalina.core.StandardWrapperValve  → 최종 Servlet 호출
   └─ filterChain.doFilter() → servlet.service()
```

Tomcat 코드 진입 시 이 5개 클래스가 흐름의 척추다.

### 3.5 한 connection의 여정 (단계 요약)

```
1. Client: TCP SYN
2. Kernel: SYN-ACK 완료 → accept queue (★ acceptCount)
3. Tomcat Acceptor: accept() → connection count++ (★ maxConnections)
4. Acceptor → pollerQueue
5. Poller: Selector.register(OP_READ)
6. Client: HTTP request → kernel socket buffer
7. Poller: select() wake up → executor.execute(SocketProcessor) (★ maxThreads)
8. Worker: read + parse + Servlet + write
9. keepalive면 Poller로 재등록, 아니면 close + count--
```

---

## 4. 가지 ④: ThreadPool — Tomcat의 특별한 Executor ⭐⭐

### 4.1 핵심 — TaskQueue override

표준 `ThreadPoolExecutor`는 "core 다 차면 queue에 넣고, queue 차면 그제야 max까지 thread 추가". `LinkedBlockingQueue` (unbounded)를 쓰면 maxPoolSize는 영영 안 늘어난다. Tomcat은 이 동작을 뒤집기 위해 `TaskQueue.offer()`를 override한다.

```java
// org.apache.tomcat.util.threads.TaskQueue
@Override
public boolean offer(Runnable o) {
    if (parent.getPoolSize() == parent.getMaximumPoolSize()) return super.offer(o);
    if (parent.getSubmittedCount() <= parent.getPoolSize())  return super.offer(o); // idle worker 있음
    if (parent.getPoolSize() < parent.getMaximumPoolSize())  return false;          // ★ thread 늘리도록 유도
    return super.offer(o);
}
```

→ **Tomcat 전략: "thread 먼저 늘리고, max 도달 후에만 queue 사용"**. 웹 서버는 throughput보다 latency가 중요하므로 응답성 우선.

### 4.2 동작 비교 그림

```
[표준 JDK ThreadPoolExecutor]              [Tomcat ThreadPoolExecutor]
요청 1000, core=10, max=200, queue=∞       요청 1000, core=10, max=200, queue=∞
   ▼                                          ▼
thread 10 사용 중                           thread 10 → idle worker 없음
   ▼                                          ▼ queue.offer() = false
queue ∞ ◄─ 990개 적체 (max 영영 안 늘어남)  thread 200까지 확장 ◄─ 즉시 처리
응답 시간 ↑↑↑ (queue 대기)                  ▼ 200 다 차면
                                            queue 사용 ◄─ 그제서야
                                            응답 시간 ↓ (thread 우선)
```

### 4.3 운영 함의

- Default: `minSpareThreads=10`, `maxThreads=200`, `maxQueueSize=Integer.MAX_VALUE`.
- maxQueueSize 작게 설정 + max 도달 → `RejectedExecutionException` → **HTTP 503**.
- maxQueueSize 무한 + downstream 느림 → thread 점진적으로 max까지 차고 queue 적체 → 메모리 부담 ↑.
- 진단: JMX `Catalina:type=ThreadPool` 의 `currentThreadsBusy`, `currentThreadCount`.

---

## 5. 가지 ⑤: acceptCount × maxConnections × maxThreads — 3대 한도

### 5.1 위치 그림

```
[Client] ─SYN─▶ [Kernel accept queue] ◄── ★ acceptCount
                        │ accept()
                        ▼
                [Tomcat Acceptor]
                connection count++ ◄── ★ maxConnections (초과 시 Acceptor block)
                        │
                        ▼
                [Poller register]
                        │ OP_READ event
                        ▼
                [Executor.execute()] ◄── ★ maxThreads (초과 시 queue 적체)
```

### 5.2 비교표

| 한도 | 위치 | 무엇을 제한 | 초과 시 증상 |
|---|---|---|---|
| **acceptCount** (default 100) | Kernel | accept queue 크기 (= listen backlog) | 새 SYN 거부 → 클라이언트 "Connection refused" |
| **maxConnections** (default NIO 10000) | Tomcat Acceptor | 보유 connection 총수 | Acceptor block → kernel queue 적체 → 결국 503 |
| **maxThreads** (default 200) | Tomcat Executor | 동시 처리 중 요청 수 | queue 적체 → 응답 시간 폭증, 또는 RejectedExecutionException → 503 |

- **acceptCount 실효값**: `min(acceptCount, /proc/sys/net/core/somaxconn)`. somaxconn이 작으면 acceptCount 늘려도 무용.
- **maxConnections >> maxThreads** 가 정상: NIO는 idle keepalive connection이 Worker를 점유하지 않으므로(Poller가 감시) 훨씬 크게 둘 수 있다.

### 5.3 튜닝 공식

```
acceptCount ≥ somaxconn
maxConnections >> maxThreads
maxThreads = 평균 동시 활성 요청 × (1 + I/O wait 비율)
```

예: 동시 활성 50, 90%가 DB 대기 → `maxThreads ≈ 50 × 10 = 500`.

---

## 6. 가지 ⑥: Request Lifecycle — byte → HttpServletRequest → Servlet → 응답

### 6.1 전체 흐름

```
[Kernel socket buffer]
  GET /api/users?name=foo HTTP/1.1\r\n
  Host: example.com\r\n
  ...\r\n\r\n
       │ Worker thread reads bytes
       ▼
┌──────────────────────────────────────────────────┐
│ Http11InputBuffer                                 │
│  parseRequestLine() + parseHeaders()             │ ← CRLF 단위, header 8KB 한도
│  body는 lazy (Servlet이 getInputStream() 시)     │
└──────────────────┬───────────────────────────────┘
                   ▼
┌──────────────────────────────────────────────────┐
│ Mapper: URI → Host → Context → Wrapper           │
└──────────────────┬───────────────────────────────┘
                   ▼
┌──────────────────────────────────────────────────┐
│ CoyoteAdapter.service()                           │
│   Request → RequestFacade (Servlet API 표준)     │ ← Facade로 lifecycle 격리
└──────────────────┬───────────────────────────────┘
                   ▼
┌──────────────────────────────────────────────────┐
│ Engine/Host/Context/WrapperValve 체인             │
│  StandardWrapperValve:                            │
│    filterChain.doFilter() → servlet.service()    │
│                              ↓                    │
│                      [DispatcherServlet]          │
│                      Spring Controller            │
└──────────────────┬───────────────────────────────┘
                   ▼
┌──────────────────────────────────────────────────┐
│ Http11OutputBuffer → SocketChannel.write() (NIO) │
└──────────────────────────────────────────────────┘
```

> **header/body/cookie/parameter 파싱 세부**는 CRLF 기준 + body는 lazy + form param은 `getInputStream()`과 충돌 가능. 자세한 13단계는 git 7e4a6c8 참조.

### 6.2 Request 객체 두 단계

```
org.apache.coyote.Request (gc 재사용)
   → org.apache.catalina.connector.Request
   → RequestFacade (사용자 코드가 보는 HttpServletRequest)
```

Facade로 한 겹 감싸서 `recycle()` 후 접근 차단 가능 — Servlet/Filter가 내부 Request를 잡으면 thread lifecycle 침범 위험.

### 6.3 Filter chain

```
Filter A.doFilter() {
   pre
   chain.doFilter()  ← 다음 Filter로 (호출 안 하면 그대로 응답)
   post
}
```

응답 시 역순으로 post-processing. Spring Security의 `FilterChainProxy`가 이 메커니즘 활용.

### 6.4 보조 토픽 (한 문단씩)

- **Async Servlet (3.0+)**: `req.startAsync()` 후 Worker 즉시 반납. 별도 thread에서 작업하고 `ctx.complete()`로 응답. Spring MVC의 `DeferredResult`/`Callable`이 내부적으로 사용.
- **WebSocket**: HTTP Upgrade로 같은 TCP에서 양방향 frame. session이 stateful → sticky session 또는 Redis pub/sub 필요.
- **ClassLoader 계층**: Bootstrap → Platform → System → Common → WebappClassLoader. Tomcat은 **parent-last** 옵션 지원 (webapp lib 우선). 재배포 시 옛 WebappClassLoader가 GC되어야 정상 — 안 되면 ClassLoader leak.
- **Session Manager**: StandardManager(in-memory), DeltaManager(cluster broadcast, N² 트래픽). 다중 서버 + 상태 필요 시 Spring Session + Redis가 표준.
- **JDK 21 Virtual Thread**: Tomcat 10.1+에서 `StandardVirtualThreadExecutor` 사용. Worker가 DB blocking 시 Virtual Thread freeze + carrier 즉시 반납 → maxThreads 제한 사실상 무한. 함정은 **pinning** (synchronized 안의 blocking I/O가 carrier 점유). 해결: `synchronized` → `ReentrantLock`. CPU bound 워크로드엔 무의미.

---

## 7. 운영 장애 패턴

### 7.1 패턴 1: "503 / Connection refused" — accept queue 가득

```
증상: LB 로그 "upstream connect failed: Connection refused", 클라이언트 즉시 503

진단:
  ss -ltn                                # Recv-Q == Send-Q면 accept queue full
  cat /proc/net/netstat | grep ListenOverflows  # kernel overflow 카운트
  lsof -p <tomcat_pid> | wc -l           # FD 사용량

원인:
  1. Tomcat 프로세스 죽음
  2. acceptCount + maxConnections full → kernel queue 가득 → SYN에 RST
  3. ulimit -n 초과 → accept() 실패

해결:
  - acceptCount ↑ (sysctl net.core.somaxconn 함께)
  - maxConnections ↑
  - 근본: Worker가 slow downstream에 잡혔는지 확인 (다음 패턴)
```

### 7.2 패턴 2: "Thread pool exhausted" — Worker hang

```
증상: P99 응답 시간 폭증, JMX currentThreadsBusy == maxThreads

jstack 패턴:
  "http-nio-8080-exec-1" ... WAITING
     at HikariCP.getConnection()         ← DB pool 대기
     at JpaRepository.findById()
  → 200개 thread가 다 같은 stack에서 대기 = downstream 문제

  "http-nio-8080-exec-99" ... RUNNABLE
     at sun.nio.ch.SocketDispatcher.read(Native Method)
     at PGStream.receive()               ← DB 응답 없음
  → RUNNABLE이지만 socket read에서 hang (5초 후 jstack 또 떠서 같은 stack이면 hang 확정)

해결:
  - JDBC socketTimeout, HikariCP connectionTimeout
  - circuit breaker (Resilience4j)
  - maxThreads 늘리기는 임시방편 (근본은 downstream)
```

### 7.3 패턴 3: "OOM: unable to create new native thread" — Heap 부족 아님

```
증상: 어느 순간부터 Worker 생성 실패, JVM crash 또는 RejectedExecutionException 폭주

진단:
  cat /proc/<pid>/status | grep Threads
  ps -eLf | grep <pid> | wc -l
  ulimit -u                              # max user processes
  cat /proc/sys/kernel/threads-max
  cgget -r pids.current,pids.max         # 컨테이너

원인:
  - ulimit -u 초과
  - kernel.pid_max 초과
  - cgroup pids.max 초과
  - 32bit JVM이라면 native stack × N으로 가상 메모리 고갈

해결:
  - LimitNPROC (systemd) ↑
  - sysctl kernel.pid_max ↑
  - 근본: thread leak 여부 (jstack에서 비정상 그룹)
```

---

## 8. 측정·진단

```
[JMX]
  Catalina:type=ThreadPool        currentThreadsBusy, currentThreadCount, keepAliveCount
  Catalina:type=GlobalRequestProcessor  requestCount, processingTime, maxTime, errorCount

[Micrometer / Actuator]
  tomcat.threads.busy, tomcat.threads.current, tomcat.global.request (Timer), tomcat.global.error

[Access Log Valve]
  pattern="%h %l %u %t \"%r\" %s %b %D"
  → awk '$NF > 1000' access.log   (1초 이상 outlier)

[jcmd]
  jcmd <pid> Thread.print              # jstack
  jcmd <pid> VM.native_memory summary  # NMT
  jcmd <pid> VM.classloader_stats      # ClassLoader leak 추적
  jcmd <pid> JFR.start duration=60s    # SocketRead, JavaMonitorEnter 이벤트

[jstack thread name]
  http-nio-8080-exec-N : NIO Worker
  http-nio-8080-Acceptor / Poller
  
[State 해석]
  RUNNABLE: 실행 중 또는 socket read syscall 안 (네트워크 hang일 수도 — 다회 캡처 비교 필요)
  WAITING (HikariCP, SocketRead) → downstream 정체
  BLOCKED → 락 경합
```

---

## 9. Lifecycle 요약

```
Bootstrap.start() → Catalina.start() → StandardServer.start()
  → Service.start()
     → Connector.start() → NioEndpoint.start()
                              ├─ ServerSocket.bind()
                              ├─ Acceptor / Poller / Executor 시작
     → Engine.start() → Host.start() → Context.start()
                                          ├─ WebappClassLoader 생성
                                          ├─ web.xml 파싱
                                          └─ Servlet/Filter init()
  → StandardServer.await()  ← 메인 루프 (shutdown 명령 대기)

종료 시 역순: Connector.stop() → Executor.shutdown() (graceful: 진행 중 완료 대기)
                            → Servlet.destroy() → WebappClassLoader 폐기
```

---

## 10. 꼬리질문

### Q1. "acceptCount와 kernel somaxconn은 어떻게 관계됩니까?"
실효값은 `min(acceptCount, somaxconn)`. somaxconn이 작으면 acceptCount 늘려도 무용. Linux 5.4+ somaxconn default = 4096. SYN flood는 다른 문제 — accept queue가 아닌 **syn queue** 공격이므로 `tcp_max_syn_backlog` + SYN cookie가 방어.

### Q2. "Tomcat이 표준 ThreadPoolExecutor와 왜 다른가요?"
표준은 "queue 차면 thread 늘림" → unbounded queue면 max 영영 안 늘어남. Tomcat은 `TaskQueue.offer()` override로 idle worker 없으면 false 반환 → 새 thread 만들도록 유도. 웹 서버는 latency가 throughput보다 중요해서 thread 먼저 늘리는 전략. throughput이 절대적인 batch엔 표준이 더 나음. Virtual Thread 시대엔 thread 생성 비용이 거의 0이라 의미가 줄어듦.

### Q3. "Worker가 RUNNABLE인데 hang일 수 있나요? 어떻게 강제로 풀어줍니까?"
가능. socket read syscall이 blocking이면 JVM은 RUNNABLE로 표시 (커널 안 대기). 5초 간격 jstack 2~3회 떠서 같은 stack이면 hang. interrupt로는 못 풀음 — socket close해야 IOException 발생. 운영에서는 미리 `socketTimeout` 설정 + circuit breaker로 차단. 근본적으론 NIO/Reactive로 전환하면 timeout이 자연스러움.

### Q4. "Spring DispatcherServlet과 Tomcat은 어떻게 결합되나요? Virtual Thread vs WebFlux는?"
Spring Boot가 embedded Tomcat을 띄우고 DispatcherServlet을 `/` Wrapper로 등록. Tomcat 입장에서 DispatcherServlet은 평범한 Servlet이라 Jetty/Undertow로 교체 가능. WebFlux는 Servlet API 안 쓰고 Reactor Netty 기반 reactive 모델. 대부분의 새 프로젝트는 **MVC + Virtual Thread**가 답 — imperative 코드 그대로 + 수십만 동시 처리. WebFlux는 backpressure 필요한 스트리밍/gateway에서.

### Q5. "ClassLoader leak이 왜 일어나고 ThreadLocal이 어떻게 leak을 일으킵니까?"
재배포 시 옛 WebappClassLoader가 GC되어야 하는데, 외부 객체(JDBC DriverManager, JMX MBean, ShutdownHook, ThreadLocal 등)가 참조 유지하면 GC 못 함. Worker thread는 풀에서 재사용 → `ThreadLocal.set(value)` 후 안 지우면 value가 Worker 죽을 때까지 살아 있고, value가 옛 ClassLoader가 로드한 클래스 인스턴스면 ClassLoader 참조 유지. 재배포 대신 컨테이너 교체(Blue-Green, rolling)가 안전 — 새 JVM 프로세스라 leak 영향 없음.

---

> **ThreadPool TaskQueue 풀버전, Request 13단계, Virtual Thread pinning 풀버전은 git 7e4a6c8 참조.**
