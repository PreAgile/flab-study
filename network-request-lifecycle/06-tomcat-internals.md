# 06. Tomcat Internals — byte stream을 HttpServletRequest로 변환하는 파이프라인

> "Tomcat은 그냥 WAS다" 라고 답하면 입문자.
> "Tomcat은 ServerSocketChannel.accept()로 SYN-ACK 완료된 TCP 커넥션을 받은 Acceptor가 SocketChannel을 Poller의 NIO Selector에 OP_READ로 등록하고, epoll_wait가 깨우면 Poller가 SocketProcessor를 Executor에 제출하여 Http11InputBuffer가 CRLF로 request line과 header를 파싱한 후 CoyoteRequest를 RequestFacade로 감싸 StandardWrapperValve가 매핑한 Servlet의 service()를 호출하고, 응답은 OutputBuffer로 다시 byte로 직렬화된 다음 SocketWrapperBase.write()로 NIO write back된다" 라고 말할 수 있다면 그 다음 단계.
> 이 문서의 목표는 후자다.

---

## 이 문서의 사용법

이 문서는 **면접 마인드맵**을 따라 선형으로 펼친 구조다. 학습 순서 = 면접 답변 순서 = 백지에 그리는 순서.

1. **0장 마인드맵을 먼저 외운다** — 루트 한 문장 + 6가지 가지 + 각 가지의 키워드 3개.
2. **1~6장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 정확히 대응.
3. **7장 운영 장애 패턴**으로 시니어 진단 능력 확인.
4. **8장 측정·진단**으로 도구 숙달.
5. **9장 꼬리질문**으로 깊이 점검.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"Tomcat은 Server → Service → Connector + Engine → Host → Context → Wrapper(Servlet) 계층 구조이며, NIO Connector가 Acceptor(accept) → Poller(Selector) → Executor(Worker) 3단 파이프라인으로 byte stream을 HttpServletRequest 객체로 변환한 후 Filter chain을 거쳐 DispatcherServlet(Spring)으로 dispatch한다."**

이 한 문장에서 모든 답변이 출발한다.

### 6개 가지 — 순서를 외운다

```
                [ROOT: 계층 구조 + 3단 파이프라인 + Filter chain]
                                    │
       ┌────────┬─────────┬─────────┼─────────┬─────────┬────────┐
       │        │         │         │         │         │        │
      ① 구조   ② Connector ③ 파이프라인 ④ ThreadPool ⑤ 한도 ⑥ Request lifecycle
   (계층 7단)  (BIO/NIO/    (Acceptor→  (min/max,   (acceptCount  (byte →
       │       NIO2/APR)    Poller→     Tomcat 변형)  /maxConn/    HttpServletReq
       │        │           Executor)    │          maxThreads)   → Servlet → 응답)
   ┌───┼───┐  ┌─┼─┐       ┌─┼─┐        ┌─┼─┐        ┌─┼─┐        ┌─┼─┐
 Server  Engine BIO NIO  accept Selector worker Tomcat queue acceptCount header Filter
 Service Host  NIO2 APR  blocking non-bk Servlet TaskQueue offer maxConn  parse chain
 Connector     ProtocolHandler  Selector poll Executor maxThreads override maxThreads CRLF Servlet
                Endpoint                                            응답
```

### 가지별 핵심 키워드

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① 구조** | Server → Service → Connector + Engine | Host → Context → Wrapper | server.xml 계층 |
| **② Connector** | BIO/NIO/NIO2/APR | ProtocolHandler | Endpoint |
| **③ 파이프라인** | Acceptor (1~N, blocking) | Poller (Selector, non-blocking) | Executor (Worker) |
| **④ ThreadPool** | minSpareThreads / maxThreads | TaskQueue override | 표준 ThreadPoolExecutor와 반대 |
| **⑤ 한도 3종** | acceptCount (kernel backlog) | maxConnections (Tomcat 수용) | maxThreads (Worker 처리) |
| **⑥ Lifecycle** | byte → header parse | RequestFacade | Filter → Servlet → 응답 |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 질문에 맞는 가지 1~2개 → 키워드 3개 순서대로 → 듣는 사람 관심에 따라 인접 가지로 확장

---

## 1. 가지 ①: 구조 — Tomcat의 7층 계층

### 1.1 핵심 질문

> "Tomcat은 어떤 구성 요소들로 이루어져 있나요? server.xml은 왜 그런 구조인가요?"

### 1.2 백지 그리기

```
[Server]                  ← JVM 프로세스 하나 = Tomcat 인스턴스 하나
   │
   ├─ [GlobalNamingResources] (선택)
   │
   └─ [Service "Catalina"]   ← Connector들 + Engine 1개를 묶는 단위
        │
        ├─ [Connector port=8080 "HTTP/1.1"]
        │     └─ ProtocolHandler (Http11NioProtocol)
        │            └─ NioEndpoint
        │                   ├─ Acceptor thread(s)
        │                   ├─ Poller thread(s)
        │                   └─ Executor (worker pool)
        │
        ├─ [Connector port=8443 "HTTP/1.1" SSL]
        │
        ├─ [Connector port=8009 "AJP/1.3"]   ← legacy, Nginx 등과 통신
        │
        └─ [Engine "Catalina" defaultHost="localhost"]
               │
               └─ [Host name="localhost" appBase="webapps"]
                      │
                      ├─ [Context path="/api" docBase="api.war"]
                      │     ├─ Manager (Session)
                      │     ├─ WebappClassLoader
                      │     ├─ Filters (FilterChain)
                      │     └─ [Wrapper "DispatcherServlet"] ← Spring 진입
                      │
                      └─ [Context path="/admin" docBase="admin.war"]
                            └─ [Wrapper "AdminServlet"]
```

### 1.3 각 계층의 책임

| 계층 | 책임 | 인스턴스 수 |
|---|---|---|
| **Server** | JVM 프로세스. 8005 shutdown port listen, `await()` 메인 루프 | 1 (JVM 하나당) |
| **Service** | Connector(들) + Engine 1개를 그룹화 | 보통 1 (드물게 2+) |
| **Connector** | TCP 포트 listen, protocol 처리 (HTTP/1.1, HTTP/2, AJP) | 포트마다 1 (8080, 8443, 8009) |
| **Engine** | request 라우팅 진입점, defaultHost 결정 | Service당 1 |
| **Host** | 가상 호스트 (`Host: example.com` 매칭) | 도메인마다 1 |
| **Context** | 웹 애플리케이션 단위 = WAR/exploded dir = ServletContext | 앱마다 1 (`/api`, `/admin`) |
| **Wrapper** | Servlet 1개를 감싸는 컨테이너 (lifecycle, mapping, multi-threading 관리) | Servlet마다 1 |

### 1.4 server.xml 핵심 발췌 (표면 디테일 제외)

```xml
<Server port="8005" shutdown="SHUTDOWN">
  <Service name="Catalina">
    <!-- Executor를 Connector들이 공유 -->
    <Executor name="tomcatThreadPool"
              minSpareThreads="10"
              maxThreads="200"
              maxQueueSize="2147483647"/>

    <!-- HTTP/1.1 Connector — NIO -->
    <Connector port="8080"
               protocol="org.apache.coyote.http11.Http11NioProtocol"
               executor="tomcatThreadPool"
               acceptCount="100"
               maxConnections="10000"
               connectionTimeout="20000"/>

    <Engine name="Catalina" defaultHost="localhost">
      <Host name="localhost" appBase="webapps" autoDeploy="true">
        <!-- Context는 보통 META-INF/context.xml 또는 자동 -->
      </Host>
    </Engine>
  </Service>
</Server>
```

> 표면 디테일은 외우지 않는다. **계층 구조**가 본질이다.

### 1.5 왜 이렇게 분리되었나 — 역사적 이유

- **Server / Service 분리**: Tomcat 4 이전엔 한 프로세스에 여러 Service를 두어 격리하려 했으나, 현대는 컨테이너/JVM 격리가 더 강력 → Service는 사실상 1개.
- **Connector / Engine 분리**: protocol(HTTP, AJP, HTTP/2)이 늘어남에 따라 "TCP/protocol 처리"와 "Servlet 라우팅"을 분리. Connector를 갈아끼우면 같은 앱이 다른 protocol에서 동작.
- **Engine / Host / Context**: 한 Tomcat에 여러 도메인의 여러 앱을 띄우기 위한 가상 호스팅 계층. 현대 MSA에서는 컨테이너 하나에 앱 하나가 흔해서 Host도 1개, Context도 1개인 경우가 많다.
- **Wrapper**: Servlet 자체는 stateless여야 하므로 lifecycle/매핑/로깅을 Wrapper가 담당. Spring의 DispatcherServlet은 Wrapper 1개에 매핑된 Servlet이다 (즉 Spring 전체가 Tomcat 입장에서는 Servlet 하나).

### 1.6 비유로 굳히기

> **호텔 체인**: Server = 호텔 그룹 본사. Service = 한 호텔 건물. Connector = 정문/후문/배달구. Engine = 호텔 로비(요청 분배). Host = 층(가상 호스트). Context = 객실 단위 비즈니스(앱). Wrapper = 객실 안의 침대(Servlet). DispatcherServlet = "스위트룸 1개에 거실+침실+주방 다 들어있는" 통합 객실.

---

## 2. 가지 ②: Connector — Protocol 처리의 추상화

### 2.1 핵심 질문

> "Connector 종류가 BIO/NIO/NIO2/APR로 진화했다는데, 각각 뭐가 다른가요? 왜 NIO가 표준이 됐나요?"

### 2.2 키워드 1 — Connector의 3층 추상화

```
[Connector]                        ← server.xml의 단위
   │
   └─ [ProtocolHandler]            ← protocol-specific
        │   (Http11NioProtocol, Http11Nio2Protocol,
        │    Http11AprProtocol, Http2Protocol, AjpNioProtocol)
        │
        └─ [Endpoint]              ← socket I/O 처리
             (NioEndpoint, Nio2Endpoint, AprEndpoint)
                │
                ├─ Acceptor
                ├─ Poller (NIO만)
                └─ Executor
```

- **Connector**: "8080 포트에서 HTTP를 받는다"는 외부 인터페이스.
- **ProtocolHandler**: HTTP/1.1 파싱, HTTP/2 frame, AJP 등 wire format 처리.
- **Endpoint**: 실제 socket I/O 모델 (blocking vs non-blocking vs async vs native).

→ 이 3층 덕분에 같은 ProtocolHandler가 다른 Endpoint에서 돌 수 있고, 같은 Endpoint가 다른 protocol을 실어나를 수 있다.

### 2.3 키워드 2 — Connector 종류의 진화 (역사)

```
Tomcat 4 (2001)        BIO (Blocking I/O)
   └─ thread-per-connection (1 connection = 1 thread 점유)

Tomcat 6 (2007)        NIO 도입 (java.nio.Selector)
   └─ 1 Acceptor + N Pollers + Executor (thread 분리)

Tomcat 7 (2011)        NIO2 도입 (AsynchronousChannel)
   └─ Callback 기반, Selector 불필요 (OS의 IOCP/aio_*)

Tomcat 5.5+            APR (Apache Portable Runtime) 추가
   └─ Native lib (libtcnative + OpenSSL), C로 작성된 socket layer
   └─ SSL 성능 ↑ (JSSE보다 OpenSSL이 빠름, AES-NI 등 직접 활용)

Tomcat 8.5 (2016)      BIO 제거 ← thread-per-connection은 비효율
Tomcat 9 (2017)        HTTP/2 지원 (Http2Protocol)
Tomcat 10 (2020)       Jakarta EE namespace (javax → jakarta)
Tomcat 10.1+ (2022)    Virtual Thread Executor 지원 (JDK 21)
Tomcat 12 (예정)       APR Connector deprecate 검토 (JSSE의 OpenSSL provider 충분)
```

### 2.4 키워드 3 — 4종 Endpoint의 thread 모델 비교

| Endpoint | Acceptor | I/O 이벤트 감지 | 데이터 read/write | Servlet 실행 |
|---|---|---|---|---|
| **BIO** (제거됨) | 1+ thread, blocking accept | 없음 (read도 blocking) | Worker thread가 blocking read | Worker thread (= read thread) |
| **NIO** (표준) | 1+ thread, blocking accept | Poller thread, `Selector.select()` | Worker thread (blocking read on NIO channel) | Worker thread |
| **NIO2** | 1+ thread, async accept | OS callback (kqueue/IOCP) | OS가 buffer fill 후 callback | Worker thread (callback에서 dispatch) |
| **APR** | C native acceptor | C poller (epoll/kqueue 직접) | C로 socket read | Worker thread (Java로 jump) |

→ **NIO가 표준이 된 이유**: thread-per-connection 비효율 해결 + Java만으로 구현 가능 (네이티브 의존 없음) + epoll/kqueue를 Selector로 추상화 + 충분히 빠름.
→ **NIO2가 표준이 되지 못한 이유**: callback chain이 복잡 + JDK의 AsynchronousChannel 구현이 OS별로 일관성 부족 + 대부분 워크로드에서 NIO와 차이 없음.
→ **APR이 살아남은 이유**: 한때 JSSE의 SSL이 OpenSSL보다 느려서. 지금은 JSSE도 충분히 빠르고 OpenSSL provider도 있어서 점점 deprecate 추세.

### 2.5 비유로 굳히기

> **레스토랑 주문 받기**: BIO = 손님이 메뉴 고를 때까지 종업원이 옆에 서서 기다림 (thread 점유). NIO = 종업원 한 명이 모든 테이블 다니며 "결정했어요?" 물어보고 결정한 테이블만 주방으로 (Selector). NIO2 = 손님이 종업원 콜벨 누를 때까지 대기, 누르면 자동으로 호출 (callback). APR = 종업원이 한국어 대신 중국 본토 셰프 출신이라 주방 동작도 더 빠름 (native).

---

## 3. 가지 ③: NIO 3단 파이프라인 — Acceptor → Poller → Executor ⭐⭐ (가장 중요)

### 3.1 핵심 질문

> "Tomcat NIO Connector는 어떻게 동시에 수천 connection을 적은 thread로 처리하나요?"

### 3.2 백지 그리기 — 풀버전

```
                   [Client A, B, C, ... N]
                          │ TCP SYN
                          ▼
                   ┌──────────────────┐
                   │ Kernel TCP stack  │
                   │  ┌─ syn queue    │  (SYN_RECV 상태, half-open)
                   │  └─ accept queue │  ← acceptCount (somaxconn 한계)
                   │     [완성된 conn] │     SYN-ACK 끝난 ESTABLISHED
                   └────────┬─────────┘
                            │ ServerSocketChannel.accept()
                            │ (blocking, 1 call = 1 connection)
                            ▼
                ┌───────────────────────┐
                │ Acceptor thread (1~N) │  ← acceptorThreadCount (default 1)
                │  while (running):     │
                │   ch = serverSock     │
                │       .accept();      │  ★ blocking
                │   pollerQueue.add(ch) │  ★ Poller에 hand-off
                └──────────┬────────────┘
                           │ pollerQueue (lock-free queue)
                           ▼
                ┌───────────────────────────┐
                │ Poller thread (1~N)       │  ← pollerThreadCount (보통 1~2)
                │  selector = Selector.open │
                │  while (running):         │
                │   // 1. 새 채널 등록      │
                │   ch = pollerQueue.poll() │
                │   ch.register(selector,   │
                │      OP_READ)             │
                │   // 2. I/O 이벤트 대기   │
                │   n = selector.select()   │  ★ epoll_wait (non-blocking poll)
                │   for key in readyKeys:   │
                │     executor.execute(     │
                │       SocketProcessor(ch))│  ★ Worker에 hand-off
                └──────────┬────────────────┘
                           │ Executor task queue
                           ▼
                ┌────────────────────────────────────┐
                │ Worker thread (Executor pool)      │  ← maxThreads (default 200)
                │  http-nio-8080-exec-1, exec-2, ... │
                │                                    │
                │  processRequest(channel):          │
                │   1. byte read (non-blocking ok)   │
                │   2. Http11InputBuffer가 parse:    │
                │      - request line (METHOD URI)   │
                │      - header (CRLF separated)     │
                │      - body (Content-Length / chunked)│
                │   3. CoyoteRequest + RequestFacade │
                │   4. Mapper로 Wrapper(Servlet) 찾기│
                │   5. Filter chain 호출             │
                │   6. Servlet.service()             │
                │      → Spring DispatcherServlet    │
                │   7. response write (byte)         │
                │   8. keepalive면 다시 Poller로 등록│
                │      아니면 socket close            │
                └────────────────────────────────────┘
```

### 3.3 의사코드로 표현

```java
// === Acceptor ===
while (running) {
    SocketChannel ch = serverSocket.accept();   // blocking, 1 connection
    poller.register(ch);                        // pollerQueue.offer(ch)
}

// === Poller ===
while (running) {
    // 1) 새로 들어온 채널을 Selector에 등록
    SocketChannel ch;
    while ((ch = pollerQueue.poll()) != null) {
        ch.configureBlocking(false);
        ch.register(selector, SelectionKey.OP_READ);
    }
    // 2) 이벤트 감지
    int n = selector.select(1000);  // epoll_wait, 최대 1초 대기
    for (SelectionKey key : selector.selectedKeys()) {
        if (key.isReadable()) {
            key.interestOps(0);     // 중복 제출 방지
            executor.execute(new SocketProcessor((SocketChannel) key.channel()));
        }
    }
}

// === Worker (Executor) ===
class SocketProcessor implements Runnable {
    public void run() {
        // 1. byte read
        byte[] buf = readBytes(channel);
        // 2. HTTP parse
        Request req = http11InputBuffer.parse(buf);
        // 3. Servlet 호출
        Servlet servlet = mapper.findWrapper(req.uri());
        FilterChain chain = buildFilterChain(req);
        chain.doFilter(new RequestFacade(req), new ResponseFacade(resp));
        // 4. response write
        outputBuffer.write(resp);
        // 5. keepalive 처리
        if (req.isKeepAlive()) {
            poller.register(channel);  // 다음 요청 대기
        } else {
            channel.close();
        }
    }
}
```

### 3.4 왜 3단으로 나눴는가 — 본질

**핵심 원리**: 각 단계는 자기 성격에 맞는 thread 모델을 쓴다.

| 단계 | 작업 성격 | 왜 따로 thread? |
|---|---|---|
| **Acceptor** | `accept()`만, blocking I/O | TCP 3-way handshake 완료된 connection을 빠르게 빼야 kernel accept queue가 안 참 |
| **Poller** | `select()`만, non-blocking 다중 감시 | 수천 connection을 1 thread가 동시 감시 (epoll의 본질) |
| **Worker** | byte parse + Servlet 호출 + DB 호출 등 long-running | 비즈니스 로직은 시간이 들기 때문에 thread를 많이 둠 |

만약 한 thread가 다 한다면:
- accept 하는 동안 select 못 함 → 다른 connection의 read 이벤트 놓침
- select 하는 동안 Servlet 못 부름 → 처리 정체
- Servlet 부르는 동안 새 connection 못 받음 → backlog 폭증

→ **각 단계의 병목 특성이 다르므로 thread 분리**.

### 3.5 Tomcat 소스 위치

```
org.apache.tomcat.util.net.NioEndpoint          ← 메인 클래스
  ├─ Acceptor (inner class, Runnable)
  │   └─ run(): serverSock.accept()
  ├─ Poller (inner class, Runnable)
  │   └─ run(): selector.select() + executor.execute()
  └─ SocketProcessor (inner class, Runnable)
      └─ run(): handler.process(socketWrapper)

org.apache.coyote.http11.Http11Processor       ← HTTP/1.1 파서
  ├─ Http11InputBuffer.parseRequestLine()
  └─ Http11InputBuffer.parseHeaders()

org.apache.catalina.connector.CoyoteAdapter    ← Coyote(Connector) → Catalina(Servlet) 다리
  └─ service(request, response)
      └─ connector.getService().getContainer().getPipeline().getFirst().invoke()

org.apache.catalina.core.StandardWrapperValve  ← Servlet 호출
  └─ invoke(): filterChain.doFilter() → servlet.service()
```

→ Tomcat 코드를 처음 읽을 때 이 5개 클래스가 흐름의 척추다.

### 3.6 keepalive와 파이프라인

```
[첫 요청 처리]
Acceptor accept → Poller register → Worker process → response write
                                                            │
                                                            ▼
                                          [keepalive 결정: Connection: keep-alive]
                                                            │
                                                            ▼
                              ┌─────────────────────────────┘
                              │ Yes
                              ▼
                  Worker: poller.register(channel) ← 같은 채널 재등록
                              │
                              ▼
                  Poller: 다음 OP_READ 이벤트 대기
                              │
                              ▼
                  [같은 connection의 다음 요청 처리]
```

→ 한 connection이 여러 요청을 처리. **Worker thread를 매번 잡고 있는 게 아니다** — 응답 후 Poller로 돌려보낸다.

---

## 4. 가지 ④: ThreadPool — Tomcat의 특별한 Executor ⭐⭐

### 4.1 핵심 질문

> "Tomcat의 Executor는 표준 ThreadPoolExecutor랑 어떻게 다른가요? 왜 다르게 만들었나요?"

### 4.2 키워드 1 — 표준 ThreadPoolExecutor의 동작

```java
new ThreadPoolExecutor(corePoolSize, maxPoolSize, keepAlive, queue);

// 새 task 들어왔을 때:
1. core thread 수 미만이면 → 새 thread 생성
2. core thread 다 차면 → queue에 넣기
3. queue도 다 차면 → maxPoolSize까지 thread 추가 생성
4. max도 다 차면 → RejectedExecutionException
```

→ "queue가 차야 thread를 늘린다". `LinkedBlockingQueue` (unbounded)를 쓰면 **maxPoolSize는 영영 안 늘어남**. 이게 표준 JDK의 함정.

### 4.3 키워드 2 — Tomcat의 변형 (TaskQueue override)

```java
// org.apache.tomcat.util.threads.TaskQueue
public class TaskQueue extends LinkedBlockingQueue<Runnable> {
    private ThreadPoolExecutor parent;

    @Override
    public boolean offer(Runnable o) {
        // 1) Worker가 core보다 많으면 일단 queue에 (정상)
        if (parent.getPoolSize() == parent.getMaximumPoolSize()) {
            return super.offer(o);
        }
        // 2) 처리 중인 task < pool size 면 idle worker 있음 → queue로
        if (parent.getSubmittedCount() <= parent.getPoolSize()) {
            return super.offer(o);
        }
        // 3) pool이 max 미만이고 idle worker 없으면 → ★ queue offer 실패 반환!
        if (parent.getPoolSize() < parent.getMaximumPoolSize()) {
            return false;  // ★ ThreadPoolExecutor가 새 thread 생성하도록 유도
        }
        return super.offer(o);
    }
}
```

```java
// org.apache.tomcat.util.threads.ThreadPoolExecutor (Tomcat 변형)
public void execute(Runnable command) {
    submittedCount.incrementAndGet();
    try {
        super.execute(command);
    } catch (RejectedExecutionException rx) {
        // queue.offer(false) 반환 + max도 차면 여기 옴
        // 마지막 안전망: queue에 강제로 넣어보기
        if (!((TaskQueue) super.getQueue()).force(command)) {
            submittedCount.decrementAndGet();
            throw new RejectedExecutionException();
        }
    }
}
```

### 4.4 키워드 3 — 두 동작의 차이

```
[표준 ThreadPoolExecutor]
요청 1000개, core=10, max=200, queue=무한대
   → thread 10개 생성
   → 나머지 990개 queue에 쌓임
   → max=200은 영영 안 늘어남 (queue가 안 차니까)
   → 응답 시간 ↑ ↑ ↑ (queue 대기)

[Tomcat ThreadPoolExecutor]
요청 1000개, core=10, max=200, queue=무한대
   → thread 10개 생성 (core까지)
   → idle worker 없으면 queue.offer() → false 반환
   → ThreadPoolExecutor가 새 thread 만들어 처리 (200까지)
   → 200 thread 다 차면 그제서야 queue에 쌓음
   → 응답 시간 ↓ (thread 우선 확장)
```

→ **Tomcat은 "thread 먼저 늘리고, 부족할 때만 queue"** 전략. **요청 응답성(latency)이 처리량(throughput)보다 중요**한 웹 서버 특성.

### 4.5 동작 비교 그림

```
[표준 JDK]                          [Tomcat]
요청 → ───┐                          요청 → ───┐
         ▼                                    ▼
   ┌──────────┐                         ┌──────────┐
   │ thread 10 │ ◄── 사용 중              │ thread 200 │ ◄── 사용 중까지 확장
   └──────────┘                         └──────────┘
         │                                    │
         ▼                                    ▼
   ┌──────────┐                         ┌──────────┐
   │ queue ∞   │ ◄── 990개 대기          │ queue     │ ◄── 거의 비어있음
   └──────────┘                         └──────────┘
                                              │
                                              ▼ (200 다 차면)
                                        ┌──────────┐
                                        │  queue     │ ◄── 그제야 사용
                                        └──────────┘
```

### 4.6 운영 함의

- Tomcat default: `minSpareThreads=10`, `maxThreads=200`, `maxQueueSize=Integer.MAX_VALUE` (사실상 무한)
- maxQueueSize를 작게 설정하면 → max 도달 후 RejectedExecutionException → 503
- maxQueueSize 무한 + downstream(DB) 느림 → thread 점진적으로 max까지 차고, queue 적체
- 진단: JMX `Catalina:type=ThreadPool,name=...` 의 `currentThreadsBusy`, `currentThreadCount`

---

## 5. 가지 ⑤: acceptCount × maxConnections × maxThreads — 3대 한도

### 5.1 핵심 질문

> "Tomcat에는 acceptCount, maxConnections, maxThreads라는 비슷한 한도가 있는데 어떻게 다른가요? 각각 어디서 막힐 때 어떤 증상인가요?"

### 5.2 백지 그리기 — 한도 3종의 위치

```
[Client]
   │
   │ TCP SYN
   ▼
┌───────────────────────────────────────────────┐
│ Kernel (Linux)                                │
│  ┌──────────────────┐                          │
│  │ SYN queue        │ ← net.core.somaxconn (sys)│
│  │  (half-open)     │ ← tcp_max_syn_backlog     │
│  └──────────────────┘                          │
│         │ SYN-ACK 완료                          │
│         ▼                                      │
│  ┌──────────────────┐                          │
│  │ Accept queue     │ ◄══ ★ acceptCount       │
│  │  (ESTABLISHED)   │     (Tomcat이 listen()의 │
│  │                  │      backlog로 사용)      │
│  └────────┬─────────┘     min(acceptCount,     │
└───────────┼─────────              somaxconn)   │
            │ accept()                            │
            ▼                                     │
┌────────────────────────────────────────────────┐
│ Tomcat 프로세스                                  │
│                                                 │
│   ┌─────────────────┐                           │
│   │ Acceptor thread  │ accept() 후 connection  │
│   └────────┬────────┘ 카운트 증가 (LongAdder)   │
│            │                                    │
│            ▼                                    │
│   ┌─────────────────────────┐                    │
│   │ Connection 총수 검사     │ ◄══ ★ maxConnections │
│   │ if (count > max)        │     (default 10000) │
│   │    Acceptor 대기 latch  │     초과 시 Acceptor│
│   └────────┬────────────────┘     blocking      │
│            │ (latch open)                       │
│            ▼                                    │
│   ┌─────────────────┐                           │
│   │ Poller register │                           │
│   └────────┬────────┘                           │
│            │ OP_READ 이벤트                      │
│            ▼                                    │
│   ┌──────────────────────────┐                  │
│   │ Executor.execute()       │ ◄══ ★ maxThreads │
│   │  Worker pool: 200 (max)  │     (default 200)│
│   │  Queue: ∞ (또는 max)     │     초과 시 queue│
│   └──────────────────────────┘     적체          │
└────────────────────────────────────────────────┘
```

### 5.3 키워드 1 — acceptCount (kernel TCP backlog)

- **정의**: ServerSocket.listen(backlog)의 backlog 값. **kernel accept queue 크기**.
- **default**: 100
- **실효값**: `min(acceptCount, /proc/sys/net/core/somaxconn)`. Linux 5.4 이후 somaxconn default = 4096.
- **초과 시 증상**: 새 SYN 도착해도 accept queue 가득 → SYN 무시 or RST → **클라이언트가 "Connection refused" or "connection timed out"**
- **운영 함정**: somaxconn이 128(legacy default)이면 acceptCount=10000 줘도 무용지물.

### 5.4 키워드 2 — maxConnections (Tomcat 수용 한도)

- **정의**: Tomcat이 **동시에 보유 가능한 connection 수** (accept된 + Poller에 등록된 + Worker 처리 중 모두 포함).
- **default**: NIO 10000, BIO는 maxThreads와 동일했음 (legacy).
- **동작**: Acceptor가 accept()마다 LongAdder로 카운트 증가. `count > maxConnections`면 Acceptor가 latch에서 **blocking** (kernel queue에 connection이 쌓이게 함).
- **초과 시 증상**: 새 connection이 kernel accept queue에서 대기 (즉 LB/Nginx에서 backend connection이 hang) → 결국 acceptCount까지 차면 "Connection refused".
- **NIO에서만 의미**: BIO는 maxConnections = maxThreads (1 connection = 1 thread).

### 5.5 키워드 3 — maxThreads (Worker 처리 한도)

- **정의**: **Executor pool의 최대 thread 수** = 동시에 **처리 중인** 요청 수의 상한.
- **default**: 200
- **maxConnections ≥ maxThreads** 가 정상. NIO는 idle keepalive connection은 Worker 안 점유하므로 (Poller가 감시), maxConnections를 훨씬 크게 둘 수 있다 (10000 vs 200).
- **초과 시 증상**: Worker가 모두 사용 중 → queue에 task 쌓임 (Tomcat은 thread 먼저 늘리고 max 도달 후 queue 사용) → 응답 시간 폭증 → 결국 응답 직전까지의 처리 단계가 hang처럼 보임.
- **maxQueueSize 작게 설정 시**: queue 마저 차면 RejectedExecutionException → **HTTP 503**.

### 5.6 3대 한도 비교표

| 한도 | 위치 | 무엇을 제한 | 초과 시 | NIO/BIO 차이 |
|---|---|---|---|---|
| **acceptCount** | Kernel | accept queue 크기 | 새 SYN 거부 (Connection refused) | 동일 |
| **maxConnections** | Tomcat Acceptor | 보유 connection 수 | Acceptor block, kernel queue에 backlog | NIO만 의미 (BIO=maxThreads) |
| **maxThreads** | Tomcat Executor | 동시 처리 중 요청 수 | queue 적체, 응답 시간 ↑, 또는 503 | BIO에선 maxConnections와 같음 |

### 5.7 실전 튜닝 공식 (한 줄)

```
acceptCount ≥ 적당히 큰 값 (≥ somaxconn)
maxConnections >> maxThreads (NIO는 idle keepalive 수용)
maxThreads = 평균 동시 처리 요청 수 × (1 + I/O wait 비율)
```

예: 평균 동시 활성 요청 50개, 각 요청의 90%가 DB 대기 → `maxThreads ≈ 50 × 10 = 500` 정도.

### 5.8 흐름 시나리오 — 한 connection의 여정

```
1. Client: TCP SYN 전송
2. Kernel: SYN_RECV (SYN queue), SYN-ACK 전송
3. Client: ACK
4. Kernel: ESTABLISHED → accept queue로 (★ acceptCount 한도 검사)
5. Tomcat Acceptor: accept() 호출 (queue에서 빼냄)
   → connection count 증가 (★ maxConnections 한도 검사, 초과 시 Acceptor block)
6. Acceptor: Poller queue에 SocketChannel 넘김
7. Poller: Selector에 OP_READ로 register
8. Client: HTTP request 전송 (TCP segment)
9. Kernel: socket buffer에 데이터 도착, Selector wake up
10. Poller: select() return → executor.execute(SocketProcessor)
    → Executor가 Worker 할당 (★ maxThreads 한도 검사, 초과 시 queue 적체)
11. Worker: byte 읽기 + HTTP 파싱 + Servlet 호출 + 응답 write
12. Worker: keepalive면 Poller로 재등록, 아니면 close
13. close 시 connection count 감소 (maxConnections 카운트)
```

---

## 6. 가지 ⑥: Request Lifecycle — byte → HttpServletRequest → Servlet → 응답

### 6.1 핵심 질문

> "Nginx가 보낸 byte 더미가 어떻게 Spring Controller의 `@RequestParam String name`까지 도달하나요?"

### 6.2 전체 흐름 그림

```
[Kernel socket buffer]
  bytes:
  GET /api/users?name=%EA%B9%80%EB%A9%B4%EC%88%98 HTTP/1.1\r\n
  Host: example.com\r\n
  Cookie: JSESSIONID=ABC123\r\n
  Content-Length: 0\r\n
  \r\n
       │
       │ Worker thread reads bytes
       ▼
┌──────────────────────────────────────────────────┐
│ Http11InputBuffer (org.apache.coyote.http11)     │
│  - parseRequestLine() : METHOD + URI + protocol  │
│  - parseHeaders()     : CRLF로 분리, : 으로 key:v│
│  - body read는 lazy (Servlet이 getInputStream()) │
│  - maxHttpHeaderSize 초과 시 거부 (default 8KB)  │
│  - chunked transfer encoding 지원                │
└──────────────────┬───────────────────────────────┘
                   │ org.apache.coyote.Request 채워짐
                   ▼
┌──────────────────────────────────────────────────┐
│ Mapper (org.apache.catalina.mapper.Mapper)        │
│  URI → Host → Context → Wrapper(Servlet)         │
│  - Host header로 가상 호스트 결정                  │
│  - Context path 매칭 (/api → ApiContext)         │
│  - Wrapper 매칭 (/users → UsersServlet 또는       │
│                          DispatcherServlet)       │
└──────────────────┬───────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────┐
│ CoyoteAdapter.service()                           │
│  - Request → RequestFacade (Servlet API 래퍼)    │
│  - Response → ResponseFacade                     │
│  - container.getPipeline().getFirst().invoke()   │
└──────────────────┬───────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────┐
│ Engine/Host/Context/Wrapper Valves                │
│  - StandardEngineValve → StandardHostValve →      │
│    StandardContextValve → StandardWrapperValve   │
│  - 각 단계마다 access log, error page, sec        │
└──────────────────┬───────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────┐
│ StandardWrapperValve                              │
│  1. filterChain = ApplicationFilterFactory       │
│       .createFilterChain(req, wrapper, servlet)  │
│  2. filterChain.doFilter(req, resp)              │
│      → Filter1.doFilter()                         │
│      → Filter2.doFilter()                         │
│      → ...                                        │
│      → servlet.service(req, resp)                │
│           ↓                                       │
│      [DispatcherServlet (Spring)]                 │
│      [HandlerMapping → Controller → ViewResolver]│
└──────────────────┬───────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────┐
│ Controller 응답 (return ResponseEntity / String) │
│   → HttpMessageConverter (Jackson 등)             │
│   → response body byte로 직렬화                   │
└──────────────────┬───────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────┐
│ Http11OutputBuffer / SocketWrapperBase            │
│  - response status line + headers + body         │
│  - chunked or Content-Length 결정                 │
│  - SocketChannel.write() (NIO)                   │
└──────────────────┬───────────────────────────────┘
                   │ bytes 응답
                   ▼
                [Kernel socket buffer]
                   │
                   ▼ TCP segment
                [Client (Nginx → 브라우저)]
```

### 6.3 핵심 단계별 깊이

#### 6.3.1 HTTP header parsing — CRLF의 정확성

```
GET /api/users?name=foo HTTP/1.1\r\n   ← request line, \r\n으로 종료
Host: example.com\r\n                   ← header 1
Cookie: JSESSIONID=ABC\r\n              ← header 2
Content-Length: 5\r\n                   ← header 3
\r\n                                    ← header 끝 (빈 줄)
hello                                   ← body (Content-Length=5)
```

- 구분자는 **CRLF (\r\n)** 만. LF만 있는 것도 일부 허용 (관용)이지만 RFC 위반.
- header line folding (LWS로 시작하는 다음 줄을 이어붙이기) — HTTP/1.1에서 **deprecated** (Tomcat은 거부).
- `maxHttpHeaderSize` (default 8KB) 초과 시 → **400 Bad Request** 응답.
- 의심스러운 \0, control char 포함 시 거부 (HTTP request smuggling 방어).

#### 6.3.2 Body 처리 — lazy + chunked

- Tomcat은 **body를 미리 다 읽지 않는다**. Servlet이 `request.getInputStream()`을 호출할 때 그제야 read.
- 이유: 대용량 업로드를 메모리에 다 적재하면 OOM 위험. ServletInputStream으로 streaming.
- `Transfer-Encoding: chunked`: body가 `<size>\r\n<data>\r\n` 반복 + 마지막 `0\r\n\r\n`. Tomcat이 chunk 단위로 reader에 전달.
- `Content-Length` 헤더와 chunked 둘 다 있으면 **거부** (smuggling 방지).

#### 6.3.3 Request 객체 두 단계 — Coyote vs Catalina

```
org.apache.coyote.Request           ← Tomcat internal, gc 재사용
   │ wraps
   ▼
org.apache.catalina.connector.Request  ← Tomcat Catalina 계층
   │ wraps
   ▼
org.apache.catalina.connector.RequestFacade  ← Servlet API 표준 인터페이스
   │ implements
   ▼
jakarta.servlet.http.HttpServletRequest  ← 사용자 코드가 보는 것
```

→ **왜 RequestFacade?** 사용자 코드(Servlet, Filter)가 내부 Request 객체를 직접 잡으면 thread/lifecycle 침범 위험. Facade로 한 겹 감싸서 `recycle()` 후엔 접근 차단 가능 (`request.getXxx()` 호출 시 IllegalStateException).

#### 6.3.4 Parameter 파싱 — query string + form body

- `?name=foo&age=20` (query string) → 즉시 파싱.
- `Content-Type: application/x-www-form-urlencoded` body → `getParameter()` 호출 시 **lazy** 파싱 + body 소비.
- 그래서 `getInputStream()` 먼저 호출하고 `getParameter()` 호출하면 빈 값 (body 이미 소비).

#### 6.3.5 Cookie 파싱

- `Cookie: a=1; b=2` 헤더 파싱 → `jakarta.servlet.http.Cookie[]`.
- RFC 6265 (Tomcat 8+). 이전엔 RFC 2109 (더 엄격, 인용부호 등).
- 잘못된 cookie 값 (예: 큰따옴표 미닫힘)은 silently drop.

### 6.4 Filter chain — 순서가 중요

```
[Request 진입]
   │
   ▼
Filter A.doFilter() {
   // pre-processing
   chain.doFilter(req, resp);  ← 다음 Filter로
   // post-processing (응답 후)
}
   │
   ▼
Filter B.doFilter() {
   // pre
   chain.doFilter(req, resp);
   // post
}
   │
   ▼
Servlet.service() {
   // 비즈니스 로직 (Spring DispatcherServlet)
}
   │
   ▼ (응답 시 역순)
Filter B post
   │
   ▼
Filter A post
   │
   ▼
[Response 송신]
```

- Filter는 **재진입 가능** (`chain.doFilter()` 안 부르면 그대로 응답). 인증 실패 시 응답 후 chain 호출 안 하면 끝.
- Spring Security가 이걸 활용 (`DelegatingFilterProxy` → `FilterChainProxy` 내부에 여러 SecurityFilter).
- Filter 순서는 web.xml의 `<filter-mapping>` 순서 또는 Spring Boot의 `@Order`.

### 6.5 DispatcherServlet은 그냥 Servlet

Spring을 쓰면 마치 Spring이 직접 HTTP를 받는 것 같지만, **Tomcat 입장에서는**:

- DispatcherServlet은 Wrapper 1개에 매핑된 평범한 Servlet.
- URL pattern `/` (또는 `/*`)에 매핑되어 **모든 요청을 잡음**.
- DispatcherServlet 내부에서 `HandlerMapping` → `Controller` → `ViewResolver`를 자체적으로 돌림.
- Tomcat은 Spring을 모른다. Spring도 Tomcat을 모른다 (Servlet API만 사용).

```
Tomcat이 보는 것:                Spring이 보는 것:
[Wrapper: dispatcherServlet]    [DispatcherServlet]
    │                               │
    └─ service(req, resp)           ├─ HandlerMapping.getHandler()
                                    ├─ HandlerAdapter.handle()
                                    │   └─ @Controller method 호출
                                    └─ HttpMessageConverter.write()
```

→ 이게 Spring이 Tomcat 외에 Jetty/Undertow에서도 동작하는 이유.

---

## 7. 운영 장애 패턴 ⭐ — 시니어 진단 능력

### 7.1 패턴 1: "503 Service Unavailable" — Connection refused

```
증상:
  - LB/Nginx 로그: "upstream connect failed: Connection refused"
  - 클라이언트: 즉시 503

원인 후보:
  1. Tomcat 프로세스 죽음 → port 안 열림 (netstat 확인)
  2. acceptCount + maxConnections 모두 full → kernel queue 가득 →
     새 SYN에 대해 kernel이 RST 반환
  3. file descriptor limit (ulimit -n) 초과 → accept() 실패

진단:
  - ss -ltn  → backlog full 여부 (Recv-Q == backlog 면 가득)
  - ss -s    → TCP 통계 (overflows 카운트)
  - cat /proc/net/netstat | grep ListenOverflows → kernel overflow 카운트
  - lsof -p <tomcat_pid> | wc -l  → FD 사용량

해결:
  - acceptCount ↑ (sysctl net.core.somaxconn도 같이)
  - maxConnections ↑
  - ulimit -n ↑ (systemd LimitNOFILE)
  - 근본 원인: Worker thread가 slow downstream에 다 잡혔는지 (다음 패턴)
```

### 7.2 패턴 2: "Thread pool exhausted" — 처리 hang

```
증상:
  - 응답 시간 폭증 (P99 spike)
  - JMX: Catalina:type=ThreadPool currentThreadsBusy = maxThreads
  - jstack: http-nio-8080-exec-* 다수가 동일 위치에서 BLOCKED/WAITING

원인:
  - slow downstream (DB slow query, 외부 API timeout)
  - Worker가 응답 못 받고 thread 점유 → 새 요청은 queue에 적체

진단 (jstack 패턴):
  ─────────────────────────────────────────────
  "http-nio-8080-exec-1" #45 ... WAITING
     at sun.misc.Unsafe.park(Native Method)
     - parking to wait for <0x...> (java.util.concurrent.SynchronousQueue)
     at HikariCP.getConnection() ← ★ DB pool 대기
     at JpaRepository.findById()
     at MyService.foo()
  ─────────────────────────────────────────────
  → 200개 thread가 다 HikariCP 대기 = downstream 문제

  ─────────────────────────────────────────────
  "http-nio-8080-exec-99" #143 ... RUNNABLE
     at sun.nio.ch.SocketDispatcher.read(Native Method) ← read syscall
     at org.postgresql.core.PGStream.receive() ← DB가 응답 안 함
  ─────────────────────────────────────────────
  → DB는 응답 안 하는데 Worker는 socket read에서 대기 (timeout 없으면 영원히)

해결:
  - JDBC socket timeout 설정 (connectionTimeout, socketTimeout)
  - Hikari connectionTimeout
  - circuit breaker (Resilience4j)
  - maxThreads 늘리기는 임시방편 (근본 원인은 downstream)
```

### 7.3 패턴 3: "OutOfMemoryError: unable to create new native thread"

```
증상:
  - 어느 순간부터 Worker thread 생성 실패
  - JVM crash 또는 RejectedExecutionException 폭주
  - catalina.out: java.lang.OutOfMemoryError: unable to create new native thread

원인 (Heap 부족 아님!):
  - OS 한도: ulimit -u (max user processes) 초과
  - kernel pid_max 초과
  - 한 thread당 native stack 1MB × N → 가상 메모리 고갈 (32bit JVM)
  - cgroup pids.max 초과 (컨테이너)

진단:
  - cat /proc/<pid>/status | grep Threads
  - ps -eLf | grep <pid> | wc -l
  - ulimit -u (해당 user의 한도)
  - cat /proc/sys/kernel/threads-max
  - cgget -r pids.current,pids.max <cgroup>

해결:
  - ulimit -u ↑ (LimitNPROC in systemd)
  - kernel.threads-max ↑
  - pid_max ↑ (sysctl kernel.pid_max)
  - 근본 원인: thread leak 여부 확인 (jstack에서 비정상 thread 그룹)
```

### 7.4 패턴 4: "ClassNotFoundException after redeploy" — ClassLoader leak

```
증상:
  - hot deploy (war 재배포) 후 ClassNotFoundException
  - Metaspace 사용량 계속 증가 (재배포마다 +50MB)
  - 결국 OutOfMemoryError: Metaspace

원인:
  - 옛 WebappClassLoader가 GC되지 않음
  - 외부 객체(ThreadLocal, JDBC driver, JMX MBean, ShutdownHook, 캐시 등)가
    옛 ClassLoader가 로드한 클래스 참조 유지 → ClassLoader 못 죽음
  - 같은 클래스가 새 ClassLoader로 또 로드됨 (별개의 Class 객체)

진단:
  - jcmd <pid> GC.class_stats | grep MyClass  → MyClass가 여러 ClassLoader에 존재?
  - Heap dump → MAT의 "Leak Suspects" → ClassLoader root path 분석
  - VisualVM Threads tab → 옛 webapp의 thread 잔존 여부

해결:
  - ThreadLocal.remove() 호출 (특히 Filter의 ThreadLocal)
  - Driver.deregisterDriver() (JDBC)
  - ScheduledExecutor 등 stop
  - 가장 안전: 재배포 대신 컨테이너 교체 (blue-green, rolling)
  - 참조: jvm/01-class-lifecycle/02-classloader-hierarchy.md
```

### 7.5 패턴 5: "Request 처리 hang + queue 적체" — 도미노

```
증상:
  - 처음엔 일부 요청 느림 → 점점 모든 요청 느려짐 → 503
  - Worker thread 점진적으로 max 도달

시나리오 (전형적):
  T+0: DB slow query 1개 발생, Worker 1개 점유
  T+10s: 같은 endpoint 호출 늘어남, Worker 10개 DB 대기
  T+30s: maxThreads=200 다 점유
  T+45s: 새 요청은 queue에 적체 (maxQueueSize=∞)
  T+60s: queue 적체 → Tomcat OOM (queue가 메모리 잡음)
         또는 maxConnections 도달 → Acceptor block →
         kernel queue 가득 → 503

진단 흐름:
  1. Nginx access log: upstream response time 증가
  2. JMX: currentThreadsBusy 증가 추세
  3. jstack 다회 캡처 (5초 간격) → 같은 stack에서 머무는 thread 발견
  4. 그 stack의 downstream 확인 (DB, Redis, 외부 API)
  5. 해당 downstream 로그/metric 확인

해결:
  - downstream timeout 강제 (socketTimeout, connectionTimeout)
  - HikariCP의 leakDetectionThreshold (60000) → 빌린 connection 60초 이상 안 돌려주면 로그
  - Bulkhead pattern (downstream별 thread pool 격리)
  - rate limit (앞단 LB/Nginx에서 RPS 제한)
```

### 7.6 패턴 6: Virtual Thread Pinning (JDK 21+)

```
증상:
  - Tomcat 10.1+ Virtual Thread Executor 켰는데 처리량 안 늘어남
  - carrier thread가 다 점유된 듯한 행동

원인:
  - synchronized 블록 안에서 blocking I/O (JDK 21~23: pinning)
  - JNI native call 안에서 blocking
  - File I/O는 일부 OS에서 여전히 carrier 잡음

진단:
  -Djdk.tracePinnedThreads=full
  → stack에 "pinned" 표기 출력

  jcmd <pid> JFR.start name=pin settings=profile
  → JFR의 jdk.VirtualThreadPinned 이벤트 분석

해결:
  - synchronized → ReentrantLock 으로 교체 (Lock은 pinning 안 함)
  - JDK 24+ 에서 일부 pinning 해소 예정 (JEP 491)
  - 참조: jvm/05-threading/04-virtual-threads-and-loom.md
```

### 7.7 jstack 출력 읽는 법

```
"http-nio-8080-exec-1" #45 daemon prio=5 os_prio=0 tid=0x... nid=0x1234 state
   java.lang.Thread.State: <STATE>
        at <stack>

[Thread name 의미]
  - http-nio-8080-exec-N : NIO Worker (Executor pool, port 8080)
  - http-nio-8080-Acceptor : Acceptor thread
  - http-nio-8080-Poller   : Poller thread
  - ContainerBackgroundProcessor : 정기 lifecycle 작업 (war reload 등)

[State 의미]
  - RUNNABLE       : 실행 중 또는 OS read/write syscall (네트워크 read 중일 수도 있음 — 주의)
  - BLOCKED        : synchronized 락 대기
  - WAITING        : Object.wait(), LockSupport.park() (timeout 없음)
  - TIMED_WAITING  : Thread.sleep(N), Object.wait(N), park(N)

[진단 패턴]
  - 다수 Worker가 같은 stack에서 BLOCKED → 락 경합
  - 다수 Worker가 같은 stack에서 WAITING (특히 HikariCP, SocketRead) → downstream 정체
  - 다수 Worker가 RUNNABLE인데 응답 안 옴 → 네트워크 read (5초 후 다시 jstack 떠서 같은 stack이면 hang)
```

---

## 8. 측정·진단 ⭐

### 8.1 JMX MBean

```
[핵심 MBean]
Catalina:type=ThreadPool,name="http-nio-8080"
   - currentThreadCount    : 현재 thread 수
   - currentThreadsBusy    : 처리 중인 thread (= 동시 처리 요청)
   - maxThreads            : 설정값
   - keepAliveCount        : keepalive 대기 중인 connection (NIO만)

Catalina:type=Connector,port=8080
   - bytesReceived, bytesSent
   - requestCount, errorCount
   - processingTime (총 처리 시간)
   - maxTime (최대 처리 시간)

Catalina:type=GlobalRequestProcessor,name="http-nio-8080"
   - 위와 비슷, Connector 단위 집계

[접근법]
   - JConsole/VisualVM에서 직접 보기
   - jcmd <pid> ManagementAgent.start_local
   - Micrometer + Spring Actuator: /actuator/metrics/tomcat.threads.busy
```

### 8.2 Tomcat Manager App

```
http://host:8080/manager/status?XML=true

→ XML 응답에 currentThreadsBusy, currentThreadCount, requestCount,
  bytesReceived/sent, processingTime 등이 한 번에

→ 운영 환경에선 manager-script role + IP 제한 필수 (보안)
```

### 8.3 Access Log Valve

```xml
<Host ...>
   <Valve className="org.apache.catalina.valves.AccessLogValve"
          directory="logs"
          prefix="access" suffix=".log"
          pattern="%h %l %u %t &quot;%r&quot; %s %b %D"/>
</Host>

[pattern]
  %D : 처리 시간 (ms) ← 가장 중요
  %s : status code
  %b : 응답 byte
  %{X-Forwarded-For}i : 원본 IP (LB 뒤일 때)

→ %D로 outlier 추출:
   awk '$NF > 1000' access.log  ← 1초 이상 걸린 요청
```

### 8.4 catalina.out 패턴

```
[OutOfMemoryError: Java heap space]
   → Heap 부족. -Xmx 늘리거나 heap dump 분석

[OutOfMemoryError: Metaspace]
   → ClassLoader leak 가능성 ↑. -XX:MaxMetaspaceSize 늘리는 건 임시방편

[OutOfMemoryError: unable to create new native thread]
   → OS 한도. ulimit, pid_max 확인

[SEVERE: Socket accept failed]
   → FD 한계 또는 OS 한도

[WARNING: The web application appears to have started a thread but has failed to stop it]
   → ClassLoader leak 경고. 재배포 시 출력
```

### 8.5 Micrometer + Spring Actuator

```yaml
management.endpoints.web.exposure.include: metrics,health,prometheus
management.metrics.tags.application: my-app

[자동 수집되는 Tomcat metrics]
  tomcat.threads.busy
  tomcat.threads.current
  tomcat.threads.config.max
  tomcat.sessions.active.current
  tomcat.sessions.created
  tomcat.global.request.max
  tomcat.global.request (Timer)
  tomcat.global.error
  tomcat.global.received (bytes)
  tomcat.global.sent (bytes)
```

→ Prometheus + Grafana로 시계열 그래프. P99 alert는 `tomcat.global.request` histogram.

### 8.6 jcmd 실전 커맨드

```bash
jcmd <pid> Thread.print           # = jstack
jcmd <pid> VM.native_memory summary  # NMT (Native Memory Tracking)
jcmd <pid> GC.heap_info
jcmd <pid> VM.classloader_stats  # ClassLoader별 로드된 클래스 수
jcmd <pid> JFR.start name=tomcat duration=60s filename=/tmp/tomcat.jfr
   → JFR에서 jdk.SocketRead, jdk.JavaMonitorEnter 등 분석
```

---

## 9. Async Servlet + WebSocket + ClassLoader + Session

이번 절은 본 흐름의 보조이지만 시니어가 알아야 할 deeper topic들.

### 9.1 Async Servlet (Servlet 3.0+)

```java
@WebServlet(urlPatterns = "/long", asyncSupported = true)
public class LongServlet extends HttpServlet {
    protected void doGet(req, resp) {
        AsyncContext ctx = req.startAsync();    // ★ Worker thread 반납
        executor.submit(() -> {
            // 별도 thread에서 long task
            String result = slowDownstream();
            ctx.getResponse().getWriter().write(result);
            ctx.complete();                      // ★ 응답 완료
        });
        // doGet() 반환 → Worker thread는 즉시 다른 요청 처리
    }
}
```

```
[동기 Servlet 그림]                  [Async Servlet 그림]
Worker thread 점유                    Worker는 startAsync() 후 즉시 반납
   │                                    │
   ├ doGet() 진입                       ├ doGet() 진입
   ├ DB 호출 (3초 대기)                 ├ startAsync() → ctx 받음
   ├ 응답 write                          ├ executor.submit() (별도 thread)
   └ Worker 반납                         └ doGet() return → Worker 즉시 반납
                                       
                                       [별도 thread]
                                       ├ slow task
                                       ├ ctx.getResponse().write()
                                       └ ctx.complete() → 응답 전송 + connection close
```

→ **NIO와 잘 맞음**: 응답 byte는 SocketChannel.write()로 NIO가 처리. Worker는 작업 시작만 하고 반납.
→ Spring MVC의 `Callable`, `DeferredResult`, `WebAsyncTask`가 내부적으로 이걸 사용.
→ Spring WebFlux는 다른 모델 (Reactor + Netty 또는 Servlet 비동기).

### 9.2 WebSocket (HTTP Upgrade)

```
[Initial handshake]
Client → GET /chat HTTP/1.1
         Connection: Upgrade
         Upgrade: websocket
         Sec-WebSocket-Key: ...

Server → HTTP/1.1 101 Switching Protocols
         Connection: Upgrade
         Upgrade: websocket
         Sec-WebSocket-Accept: ...

[이후]
같은 TCP connection에서 양방향 frame 교환 (HTTP 아님)
```

- Tomcat의 WebSocket 구현: `org.apache.tomcat.websocket.server.WsServerContainer`.
- HTTP Upgrade 시 NIO Connector가 connection을 WebSocket 전용 처리로 넘김.
- WebSocket session은 **stateful** → 같은 서버에 다시 와야 함 → **sticky session** 또는 외부 message bus (Redis pub/sub) 필요.

### 9.3 ClassLoader 계층 (Tomcat 특화)

```
[Bootstrap]  ─── JDK core (java.lang.*, java.util.*)
   │
[Platform]   ─── JDK extensions (jdk.* 모듈)
   │
[System]     ─── $CATALINA_HOME/bin/*.jar (bootstrap.jar, tomcat-juli.jar)
   │
[Common]     ─── $CATALINA_HOME/lib/*.jar (Tomcat 자체, Servlet API)
   │
[Webapp-A]   ─── /webapps/A/WEB-INF/{classes,lib}
[Webapp-B]   ─── /webapps/B/WEB-INF/{classes,lib}
   │
   각 Webapp은 독립적 (sibling, parent-last 옵션 가능)
```

- 표준 Java는 **parent-first** (부모에서 못 찾으면 자식). Tomcat WebappClassLoader는 **parent-last** 옵션 — webapp의 classes/lib를 먼저 찾는다 (`<Loader delegate="false">`).
- **왜 parent-last**: webapp이 새 Spring 버전을 쓰는데 Tomcat lib에 옛 버전이 있으면 충돌 → webapp 자체 lib 우선.
- 재배포 시: 옛 WebappClassLoader는 GC되어야 정상. 안 되면 **ClassLoader leak** (앞 패턴 4 참조).
- 참조: `jvm/01-class-lifecycle/02-classloader-hierarchy.md`

### 9.4 Session Manager

```
[Tomcat Session 종류]
StandardManager   : in-memory (default). 서버 재시작 시 SESSIONS.ser로 직렬화 (선택)
PersistentManager : DB/file store에 swap (idle 오래된 session)
DeltaManager      : cluster mode, 변경분만 다른 노드에 broadcast (all-to-all)
BackupManager     : cluster mode, primary/backup 노드만 동기화 (확장성 ↑)

[운영 현실]
- 단일 서버: StandardManager + sticky session 또는 무상태(JWT)
- 다중 서버 + state 필요: 보통 Tomcat session 안 쓰고 Spring Session + Redis
  → JSESSIONID는 Redis key, session 데이터는 Redis hash
- session replication (DeltaManager)은 노드 늘면 N² 트래픽 → 6~8 노드가 한계
```

---

## 10. JDK 21 Virtual Thread 통합 (Tomcat 10.1+)

### 10.1 어떻게 켜는가

```xml
<Executor name="virtualThreadExecutor"
          className="org.apache.catalina.core.StandardVirtualThreadExecutor"/>

<Connector port="8080"
           protocol="org.apache.coyote.http11.Http11NioProtocol"
           executor="virtualThreadExecutor"/>
```

또는 Spring Boot 3.2+:
```yaml
spring.threads.virtual.enabled: true
```

### 10.2 무엇이 바뀌나

```
[전통: Platform Thread Pool]            [Virtual Thread]
maxThreads=200 고정                      maxThreads 제한 사실상 없음
   │                                       │
   ├ Worker가 DB blocking → thread 점유    ├ Worker가 DB blocking →
   │                                       │   Virtual Thread freeze →
   │                                       │   carrier 즉시 반납
   ├ 200개 동시 처리 한계                  ├ 수십만 동시 처리 가능
   └ I/O bound 워크로드에서 비효율          └ I/O bound 워크로드에 최적
```

### 10.3 함정 — Pinning

```
synchronized 블록 안에서 blocking I/O → Virtual Thread가 carrier에 "pinning"
   → carrier thread가 못 빠져나옴
   → 결국 carrier 수 (보통 CPU 수) 만큼만 동시 처리

원인:
  - synchronized + DB call
  - synchronized + Socket read
  - JNI (Native) call
  - 일부 file I/O

진단:
  -Djdk.tracePinnedThreads=full
  JFR jdk.VirtualThreadPinned 이벤트

해결:
  - synchronized → ReentrantLock (Lock은 pinning 안 함)
  - JDK 24+ JEP 491에서 일부 해소 예정
```

### 10.4 CPU bound 워크로드에는 부적합

- Virtual Thread는 **I/O bound** (네트워크/DB 대기 많은 작업)에 최적.
- **CPU bound** (이미지 처리, 암호화, 계산) 는 결국 carrier(CPU) 수에 묶임 → Virtual Thread 의미 없음, 오히려 overhead.
- 참조: `jvm/05-threading/04-virtual-threads-and-loom.md`

---

## 11. Lifecycle — Tomcat은 어떻게 시작하고 멈추나

### 11.1 부팅 단계

```
[startup.sh / catalina.sh]
   │
   ▼
java org.apache.catalina.startup.Bootstrap start
   │
   ▼
Bootstrap.init()                      ← ClassLoader 계층 구축
Bootstrap.load() → Catalina.load()    ← server.xml 파싱, MBean 등록
Bootstrap.start() → Catalina.start()  ← 컴포넌트 lifecycle 시작
   │
   ▼
StandardServer.start()
   ├─ Service.start()
   │   ├─ Connector.start()
   │   │   └─ ProtocolHandler.start()
   │   │       └─ NioEndpoint.start()
   │   │           ├─ ServerSocket.bind()
   │   │           ├─ Acceptor thread 시작
   │   │           ├─ Poller thread 시작
   │   │           └─ Executor 시작
   │   └─ Engine.start()
   │       └─ Host.start()
   │           └─ Context.start()      ← webapp 시작
   │               ├─ WebappClassLoader 생성
   │               ├─ web.xml 파싱
   │               ├─ Servlet init() (load-on-startup이면)
   │               └─ Filter init()
   │
   ▼
StandardServer.await()                ← ★ 메인 루프
   └─ 8005 포트에서 "SHUTDOWN" 문자열 대기
   └─ 받으면 stop() 실행 (역순 종료)
```

### 11.2 종료 단계

```
StandardServer.stop()
   └─ Service.stop()
       └─ Connector.stop()  ← 새 요청 안 받음
           └─ Endpoint.stop()
               ├─ Acceptor stop
               ├─ Poller stop (Selector close)
               └─ Executor.shutdown()  ← 진행 중 요청은 완료까지 대기
       └─ Engine.stop()
           └─ Context.stop()
               ├─ Servlet.destroy()
               ├─ Filter.destroy()
               └─ WebappClassLoader 폐기

→ graceful shutdown: 진행 중 요청 처리 완료 후 종료
→ TimeUnit: connector.stop() + executor.awaitTermination()
```

---

## 12. 면접 워크플로우

| 면접 질문 | 시작 가지 | 답변 흐름 |
|---|---|---|
| "Tomcat 구조를 설명해보세요" | ① 구조 | 7층 계층 → server.xml → 각 책임 |
| "BIO와 NIO 차이는?" | ② Connector | 3층 추상화 → 진화 → thread 모델 비교 |
| "Tomcat이 수많은 connection을 어떻게 처리하나요?" | ③ 파이프라인 | Acceptor/Poller/Executor 3단 → 의사코드 |
| "ThreadPoolExecutor와 Tomcat의 차이는?" | ④ ThreadPool | 표준 동작 → TaskQueue override → 왜 |
| "acceptCount, maxConnections, maxThreads 차이는?" | ⑤ 한도 | 위치 그림 → 각 초과 시 증상 → 튜닝 공식 |
| "HTTP 요청이 어떻게 Spring Controller까지 가나요?" | ⑥ Lifecycle | byte → header parse → Servlet → Filter → Dispatcher |
| "Tomcat 운영 장애 경험 있어요?" | 7장 | 503 / thread exhausted / OOM thread / CL leak 중 하나 |
| "Virtual Thread 써봤어요?" | 10장 | 켜는 법 → I/O bound 이점 → Pinning 함정 |

---

## 13. 꼬리질문 (3단)

### Q1. "Tomcat의 acceptCount는 무엇입니까?"

**예상답**: ServerSocket.listen(backlog)의 backlog. kernel accept queue 크기. default 100.

**꼬리 Q2**: "kernel의 somaxconn과는 어떻게 관계됩니까?"

**예상답**: 실효값은 `min(acceptCount, somaxconn)`. somaxconn이 작으면 acceptCount 늘려도 무용. Linux 5.4 이후 somaxconn default = 4096.

**꼬리 Q3**: "그럼 SYN flood 공격에는 어떤 한도가 관계됩니까?"

**예상답**: SYN flood는 accept queue가 아닌 **syn queue** (half-open) 공격. `tcp_max_syn_backlog`와 SYN cookie (`tcp_syncookies`)가 방어. accept queue는 ESTABLISHED만 들어가서 무관. 근본 방어는 LB/방화벽 단에서 rate limit + SYN cookie.

---

### Q1. "Tomcat이 표준 ThreadPoolExecutor와 왜 다른가요?"

**예상답**: 표준은 "queue 차면 thread 늘림" → unbounded queue면 maxPoolSize 영영 안 늘어남. Tomcat은 TaskQueue.offer()를 override해서 idle worker 없으면 false 반환 → ThreadPoolExecutor가 새 thread 만들도록 유도. "thread 먼저, queue 나중" 전략.

**꼬리 Q2**: "왜 그렇게 만들었을까요?"

**예상답**: 웹 서버는 latency가 throughput보다 중요. queue에 쌓이면 응답 지연. thread를 빨리 늘려서 즉시 처리하는 게 응답성에 유리. 단점은 thread 생성/context switch overhead가 더 클 수 있음 — 트레이드오프.

**꼬리 Q3**: "그러면 어떤 워크로드에서 표준 ThreadPoolExecutor가 더 나을까요?"

**예상답**: throughput이 절대적인 batch 처리. 응답 지연이 허용되고 thread 수 폭증을 막아야 하는 경우. 또는 thread 생성 비용이 크고 작업 자체는 짧은 경우 (CPU bound + 짧은 task) — queue로 흡수하는 게 효율. 또는 Virtual Thread를 쓰면 thread 생성 비용 자체가 거의 없어서 Tomcat 변형의 의미가 줄어듦.

---

### Q1. "Worker thread가 hang 걸렸다고 의심되면 어떻게 진단합니까?"

**예상답**: jstack 5초 간격으로 2~3회 캡처 → 같은 stack에서 머무는 thread 그룹 찾기. 그 stack의 마지막 native/blocking 호출이 downstream(DB, Redis, HTTP client). 거기 timeout 설정 여부 확인.

**꼬리 Q2**: "RUNNABLE 상태인데 hang일 수 있나요?"

**예상답**: 가능. socket read syscall이 epoll 없이 blocking으로 들어가면 JVM은 RUNNABLE로 표시 (커널 안에서 대기 중이라). 그래서 RUNNABLE이지만 진행 안 함. 여러 번 jstack 떠서 같은 read 지점에 머물면 hang.

**꼬리 Q3**: "그럼 어떻게 강제로 풀어줍니까?"

**예상답**: thread interrupt만으론 socket read 못 풀음 (blocking syscall). socket close해야 IOException 발생하며 풀림. 운영에서는 미리 socketTimeout 설정 (JDBC `socketTimeout`, HTTP client `readTimeout`)으로 강제 timeout. circuit breaker (Resilience4j)로 외부 호출 자체를 차단. 근본적으론 NIO/Reactive로 전환하면 timeout이 자연스러움.

---

### Q1. "Spring DispatcherServlet과 Tomcat은 어떻게 결합되나요?"

**예상답**: Spring Boot가 시작 시 embedded Tomcat을 띄우고, DispatcherServlet을 Wrapper로 등록해서 모든 path (`/`)에 매핑. Tomcat 입장에서 DispatcherServlet은 평범한 Servlet 1개. Servlet API만 사용하므로 Jetty/Undertow로 교체 가능.

**꼬리 Q2**: "Spring WebFlux는 다른가요?"

**예상답**: 다름. WebFlux는 Servlet API 안 씀. 기본 런타임이 Reactor Netty (NIO 기반, Servlet 없음). Tomcat에서도 띄울 수 있지만 그땐 Servlet 3.1 async API 위에 동작. WebFlux는 thread-per-request 모델을 버린 reactive 모델 — Mono/Flux 체인.

**꼬리 Q3**: "Spring MVC + Virtual Thread vs WebFlux 중 어떤 게 낫나요?"

**예상답**: 트레이드오프. 
- **MVC + Virtual Thread**: 기존 imperative 코드 그대로 + 수십만 동시 처리. 학습 비용 낮음. JDK 21+ 필요. Pinning 주의.
- **WebFlux**: reactive 함수 chain. 학습 비용 높음, debugging 어려움. backpressure 명시적 지원. Netty와 가장 잘 맞음.
- 대부분의 새 프로젝트는 **MVC + Virtual Thread**가 답. WebFlux는 backpressure 필요한 스트리밍/proxy/gateway 류에서 선택.

---

### Q1. "ClassLoader leak이 왜 일어나나요?"

**예상답**: 재배포 시 옛 WebappClassLoader는 GC되어야 하는데, 외부 객체(JDK 캐시, JDBC DriverManager, ThreadLocal, JMX MBean, ShutdownHook)가 그 ClassLoader가 로드한 클래스를 참조하고 있으면 GC 못 함. 누적되면 Metaspace OOM.

**꼬리 Q2**: "ThreadLocal이 어떻게 leak을 일으킵니까?"

**예상답**: Tomcat의 Worker thread는 풀에서 재사용. 한 요청에서 `ThreadLocal.set(value)` 하고 안 지우면, 그 value가 그 Worker가 죽을 때까지 살아 있음. value가 옛 WebappClassLoader가 로드한 클래스의 인스턴스면 → ClassLoader 참조 유지 → 재배포해도 ClassLoader GC 안 됨. Tomcat이 경고: "The web application appears to have started a thread but has failed to stop it".

**꼬리 Q3**: "왜 재배포 대신 컨테이너 교체가 안전한가요?"

**예상답**: 새 JVM 프로세스에서 시작하면 ClassLoader leak 영향 없음 (프로세스 죽으면 다 같이 죽음). Blue-Green deploy, rolling update가 이 원리. Tomcat의 hot deploy는 dev 환경에선 편리하지만 prod에선 위험 — Metaspace 사용량 모니터링 필수. 컨테이너(Docker) 시대에는 hot deploy 의미 거의 없음, 새 이미지로 교체가 표준.

---

## 14. 다음 학습

- 다음 챕터: `07-connection-pools-master.md` (Nginx upstream / Tomcat thread / HikariCP / kernel TCP backlog 종합)
- 관련: `jvm/05-threading/04-virtual-threads-and-loom.md` (Pinning 심층)
- 관련: `jvm/01-class-lifecycle/02-classloader-hierarchy.md` (ClassLoader leak)
- 관련: `jvm/02-runtime-data-areas/05-direct-memory.md` (NIO DirectBuffer)
- 관련: `java-deep-dive/04-timeouts-connection-vs-read.md` (timeout 종류)

---

## 한 줄 요약

> **Tomcat은 NIO Connector의 Acceptor → Poller → Executor 3단 파이프라인으로 TCP byte stream을 HttpServletRequest로 변환하고, acceptCount(kernel) × maxConnections(Tomcat) × maxThreads(Worker) 3대 한도가 connection의 여정을 통제하며, 표준 ThreadPoolExecutor를 TaskQueue override로 변형해 "thread 먼저, queue 나중" 전략을 쓴다. JDK 21+ Virtual Thread를 carrier로 사용하면 I/O bound 워크로드에서 maxThreads 한도가 사실상 사라진다.**
