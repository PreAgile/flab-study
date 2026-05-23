# 07. Connection Pools Master — 한 요청이 통과하는 모든 풀

> "Connection Pool 하나 = HikariCP" 라고 답한 면접자는 절반은 모르는 것이다.
> 한 HTTP 요청은 **최소 7~13개의 풀**을 통과한다. 커널 TCP backlog, file descriptor 한계, LB connection table, Nginx worker connections, Nginx upstream keepalive, Tomcat acceptCount/maxConnections/maxThreads, HikariCP, 외부 API HTTP client pool, Redis pool, DB의 max_connections, 앱 내부 ForkJoinPool...
> 어느 한 풀이 작아도 — **전체 응답이 hang 한다**. 어느 한 풀이 너무 커도 — **하류 자원이 폭발한다**.
> 이 챕터는 그 모든 풀을 한 자리에 모아 "한 풀이 비면 다른 풀이 어떻게 무너지는가" 를 본다.

---

## 📍 학습 목표

이 챕터를 마치면 다음을 막힘없이 답할 수 있다.

1. 한 요청이 클라이언트에서 DB까지 가는 동안 만나는 **모든 풀**을 순서대로 백지에 그릴 수 있다.
2. 각 풀이 **고갈됐을 때** 어떤 에러/증상이 나오는지, 그 에러가 위로 어떻게 전파되는지 안다.
3. HikariCP가 ConcurrentBag 자료구조로 **lock-free + thread-local handoff**를 어떻게 구현하는지 안다.
4. Tomcat의 `acceptCount`, `maxConnections`, `maxThreads` **세 한도의 차이**와 각각 어디서 막히면 어떤 에러가 나는지 안다.
5. **Cascading failure 시나리오** — DB hang → HikariCP 고갈 → Tomcat thread 점유 → LB health check 실패 → 인스턴스 격리 → 폭주 — 를 단계별로 설명할 수 있다.
6. Little's Law를 적용해서 **목표 동시성에 필요한 pool size**를 계산할 수 있다.
7. `maxLifetime`이 firewall idle timeout보다 짧아야 하는 이유와, 그 함정에 빠졌을 때 어떤 증상이 나오는지 안다.
8. `ss -tan`, `jcmd Thread.print`, HikariCP MXBean, Micrometer pool metrics로 풀 상태를 실시간 진단할 수 있다.

---

## 1. "Pool"의 본질 — 왜 풀이 존재하나

### 1-1. 한 줄 정의

> **Pool = "생성 비용이 큰 자원을 미리 만들어 두고 빌려주는 컨테이너"**

생성 비용이 거의 0이면 풀이 필요 없다. 매번 만든다. 풀이 존재하는 이유는 **생성 비용이 응답 시간을 잡아먹기 때문**.

### 1-2. "비싼 자원"의 정체

각 자원의 생성 비용 (대략적 수치, production 환경 기준):

| 자원 | 한 번 만드는 비용 | 무엇이 비싼가 |
|---|---|---|
| **TCP connection** | 1~3 RTT (~10~100ms) | 3-way handshake (SYN/SYN-ACK/ACK) |
| **TLS connection** | 추가 1~2 RTT (~50~200ms) | 인증서 검증, 키 교환, ChangeCipherSpec |
| **DB connection** | 50~500ms | TCP + TLS + DB 인증 (SCRAM/MD5) + session 초기화 (search_path, timezone, statement_timeout) |
| **HTTP/2 connection** | TCP + TLS + SETTINGS frame 교환 | multiplexing 사전 협상 |
| **OS thread** | 1~수 ms | stack 메모리(1MB) 할당, kernel task struct |
| **File descriptor** | 수 μs | 그러나 limit이 있고 leak되면 누적 |
| **Memory allocation** | 수 ns~수 μs | 작지만 GC 압박 |

### 1-3. 풀이 없으면 — 풀이 너무 작으면 — 풀이 너무 크면

```
[Pool 없음]                   [Pool 너무 작음]              [Pool 너무 큼]
─────────                    ──────────────              ─────────────
요청마다 새 connection       N개 동시 요청 > pool size    하류 자원 폭발
   │                            │                            │
   ▼                            ▼                            ▼
매번 100~500ms handshake     pool wait queue에 적체         DB max_connections 초과
응답 시간 = 비즈로직 + 핸드셰이크   요청은 들어왔는데              "FATAL: sorry, too many"
P99 폭발                       getConnection() 대기            DB CPU 100%
DB 측 인증 부하 폭증           connectionTimeout 후 SQLException  옆 서비스까지 영향
                                P99 폭발                       processes context switch 부담
```

**핵심 통찰**: 풀은 "Goldilocks 문제" — 너무 작아도, 너무 커도 응답 시간이 늘어난다. 적정 크기는 **측정으로** 찾아야 한다. (§13에서 Little's Law)

### 1-4. 비유 + 정확한 정의

> **비유**: 카페가 매번 새 바리스타를 채용하면 첫 주문에 한 달 걸린다. 미리 3명 고용해 두고 손님이 오면 바로 응대. 손님이 많으면 줄을 세우고, 줄이 너무 길면 손님이 떠난다.
> **정확한 정의**: Pool = 동적으로 (create/destroy) 만들기에는 비싸지만 동시 사용량은 제한된 자원에 대해, 미리 N개 만들어 두고 빌려준 후 반납받는 자료구조 + lifecycle 관리.

---

## 2. 한 요청이 만나는 모든 풀 — 전체 흐름 ⭐⭐

```
   [Client (Browser / Mobile / curl)]
              │
              │  TCP SYN
              ▼
  ┌─────────────────────────────────────────────────┐
  │ #1. Kernel TCP listen backlog (LB 측)            │  net.core.somaxconn
  │      - SYN_RECV queue (incomplete handshake)     │  tcp_max_syn_backlog
  │      - ACCEPT queue (complete handshake)         │  listen(fd, backlog)
  │      가득 차면 → SYN drop, RST or retry           │
  └────────────────────┬────────────────────────────┘
                       │
                       ▼
  ┌─────────────────────────────────────────────────┐
  │ #2. LB connection table (per-connection state)   │  conntrack 한도
  │      - L4 NAT 모드: per-connection NAT entry     │  net.netfilter.nf_conntrack_max
  │      - 풀이 아닌 "table" 이지만 한도 존재         │
  │      가득 차면 → "nf_conntrack: table full"      │
  └────────────────────┬────────────────────────────┘
                       │
                       ▼
  ┌─────────────────────────────────────────────────┐
  │ #3. LB → backend keepalive pool                  │
  │      - Nginx upstream keepalive                  │
  │      - HAProxy http-keep-alive                   │
  │      - AWS ALB는 자체 connection pool 유지       │
  │      가득 차면 → 새 TCP 매번 새로 — handshake 비용│
  └────────────────────┬────────────────────────────┘
                       │
                       ▼
  ┌─────────────────────────────────────────────────┐
  │ #4. Nginx worker_connections                     │  worker_connections 1024
  │      - 한 worker가 동시에 들 수 있는 connection  │  worker_processes 8
  │      - 이론적 한계 = 1024 × 8 = 8192             │
  │      가득 차면 → "1024 worker_connections" 로그  │
  │                    accept() 호출 멈춤             │
  └────────────────────┬────────────────────────────┘
                       │
                       ▼
  ┌─────────────────────────────────────────────────┐
  │ #5. Nginx → Tomcat upstream keepalive pool       │  upstream { keepalive 32; }
  │      - backend 당 idle connection 유지           │  keepalive_requests 1000
  │      - HTTP/1.1 + Connection: Keep-Alive         │  keepalive_timeout 60s
  │      미설정 → 매 요청마다 새 TCP                  │
  └────────────────────┬────────────────────────────┘
                       │
                       ▼
  ┌─────────────────────────────────────────────────┐
  │ #6. Tomcat acceptCount (kernel TCP backlog)      │  Connector acceptCount=100
  │      - JVM Connector가 listen(fd, acceptCount)   │  ★ kernel 한도
  │      - kernel ACCEPT queue 크기                  │
  │      가득 차면 → SYN drop → client 측 timeout    │
  └────────────────────┬────────────────────────────┘
                       │
                       ▼
  ┌─────────────────────────────────────────────────┐
  │ #7. Tomcat maxConnections (socket 수)            │  Connector maxConnections=8192
  │      - Tomcat이 직접 카운팅하는 connection 수     │  ★ Tomcat 측 한도
  │      - keep-alive 연결도 카운트됨                │
  │      가득 차면 → Acceptor가 accept() 일시 중지   │
  └────────────────────┬────────────────────────────┘
                       │
                       ▼
  ┌─────────────────────────────────────────────────┐
  │ #8. Tomcat Executor (thread pool)                │  Executor maxThreads=200
  │      - request 처리 worker thread pool           │  minSpareThreads=10
  │      - 한 thread = 한 request 처리 (동기 model)   │
  │      가득 차면 → request가 queue에서 대기         │
  │                    Executor 정책에 따라 reject    │
  └────────────────────┬────────────────────────────┘
                       │
                       ▼
   [Spring Application Code 진입]
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
  ┌──────────┐  ┌──────────┐  ┌──────────────┐
  │ #9.      │  │ #10.     │  │ #11.         │
  │ HikariCP │  │ HTTP     │  │ Redis Pool   │
  │ DB Pool  │  │ Client   │  │ (Jedis /     │
  │          │  │ Pool     │  │  Lettuce)    │
  │ maximum- │  │ (Apache/ │  │              │
  │ PoolSize │  │ OkHttp/  │  │              │
  │ =10      │  │ WebClient│  │              │
  │          │  │ )        │  │              │
  └────┬─────┘  └────┬─────┘  └──────┬───────┘
       │             │               │
       │             ▼               ▼
       │      [외부 API]       [Redis 서버]
       │
       ▼
  ┌─────────────────────────────────────────────────┐
  │ #12. DB max_connections (DB 측 한도)             │  postgresql.conf
  │      - PostgreSQL: 1 connection = 1 backend proc │  max_connections=100
  │      - MySQL: 1 connection = 1 thread            │
  │      - 앱 인스턴스 × pool size ≤ DB max          │
  │      초과 → "FATAL: too many clients already"    │
  └─────────────────────────────────────────────────┘

  + #13. App 내부 ForkJoinPool / ExecutorService
         - parallelStream의 commonPool
         - @Async의 ThreadPoolTaskExecutor
         - CompletableFuture의 default executor
```

### 핵심 통찰

> **모든 풀이 사슬로 연결되어 있다. 어느 한 풀이 비면 — 위쪽이 적체된다. 위쪽이 적체되면 — 더 위쪽까지 영향. 결국 LB가 health check 실패로 인스턴스를 빼면 — cascading failure.**

각 풀의 "비었을 때" 동작:

| # | 풀 | 빈 자원 / 가득 참 시 동작 | 위로 전파되는 증상 |
|---|---|---|---|
| 1 | kernel SYN backlog | SYN drop | client TCP retry → connect timeout |
| 2 | LB conntrack table | drop new flow | client connection refused |
| 3 | LB→backend keepalive | 매번 새 TCP | latency 증가 (handshake) |
| 4 | Nginx worker_connections | accept 멈춤 | LB가 다른 backend로 |
| 5 | upstream keepalive | 매번 새 TCP to Tomcat | Tomcat 측 TIME_WAIT 폭증 |
| 6 | Tomcat acceptCount | SYN drop | client connection timeout |
| 7 | Tomcat maxConnections | accept 멈춤 | upstream(Nginx)에서 적체 |
| 8 | Tomcat Executor | queue에서 대기 / reject | response timeout / 503 |
| 9 | HikariCP | getConnection 대기 → timeout | Tomcat thread도 hang → #8까지 hang |
| 10 | HTTP client pool | request 대기 → timeout | 같은 식으로 위로 hang |
| 11 | Redis pool | borrow 대기 → timeout | 같은 식 |
| 12 | DB max_connections | 거부 | 신규 connection 못 만듦 → #9 timeout |
| 13 | 앱 내부 thread pool | task queue 적체 / reject | 비동기 작업 지연 |

**가장 흔한 cascading**: #9 HikariCP 고갈 → #8 Tomcat thread 점유 → #7 Tomcat maxConnections 점유 → #6 acceptCount 적체 → LB health check 실패 → 인스턴스 ous → 남은 인스턴스에 부하 폭주 → 또 #9 고갈 → ... (§14에서 상세)

---

## 3. Kernel TCP Backlog — 가장 아래의 풀

### 3-1. 두 개의 큐

TCP listen() 호출 후 커널은 **두 개의 큐**를 관리한다.

```
[Client]                    [Server kernel]
   │  SYN ──────────────▶  ┌─────────────────────┐
   │                       │ SYN_RECV queue       │  ← incomplete handshake
   │  ◀────── SYN+ACK      │ (반쯤 만들어진 conn) │
   │                       └──────────┬──────────┘
   │  ACK ──────────────▶             │
   │                                   ▼
   │                       ┌─────────────────────┐
   │                       │ ACCEPT queue         │  ← complete handshake
   │                       │ (완성된 conn,         │     waiting for accept()
   │                       │  app이 accept() 호출 │
   │                       │  하길 대기)           │
   │                       └──────────┬──────────┘
   │                                   │
   │                                   ▼
   │                       ┌─────────────────────┐
   │                       │ app code            │
   │                       │ accept() →          │
   │                       │   new socket fd     │
   │                       └─────────────────────┘
```

### 3-2. 두 큐의 한도

| 큐 | 한도 (sysctl) | 한도 (코드) |
|---|---|---|
| SYN_RECV | `net.ipv4.tcp_max_syn_backlog` (보통 4096~8192) | — |
| ACCEPT | `net.core.somaxconn` (보통 4096) | `listen(fd, backlog)` 의 backlog |

실제 ACCEPT queue 크기 = `min(somaxconn, backlog)`. 그래서 **app이 listen(fd, 10000)** 으로 호출해도 `somaxconn=128` 이면 128로 잘린다.

### 3-3. 가득 차면

| 상황 | 결과 |
|---|---|
| SYN_RECV queue 가득 | 새 SYN drop. `tcp_syncookies=1`이면 cookie로 우회 |
| ACCEPT queue 가득 | 완성된 ACK 도착했는데 app이 accept() 안 하면 → 새 conn drop, client 측은 RST 또는 timeout |

**증상**: client 측에서 `connection refused` 또는 `connection timeout`. 서버 측 `netstat -s | grep -i listen` 에 `times the listen queue of a socket overflowed` 카운터 증가.

### 3-4. Tomcat의 acceptCount 와 연결

Tomcat의 `acceptCount=100` 은 결국 `listen(fd, 100)` 호출 시 backlog 인자. **그러나 `somaxconn` 으로 잘린다**. 그래서 Tomcat acceptCount 만 늘려도 효과가 없을 수 있다 — sysctl도 같이 늘려야.

```bash
# 현재 값 확인
sysctl net.core.somaxconn
sysctl net.ipv4.tcp_max_syn_backlog

# 늘리기 (root)
sysctl -w net.core.somaxconn=8192
sysctl -w net.ipv4.tcp_max_syn_backlog=8192

# 영구 적용
echo "net.core.somaxconn=8192" >> /etc/sysctl.conf
```

### 3-5. 진단

```bash
# ACCEPT queue overflow 카운터
nstat -az | grep -i listen
netstat -s | grep -i 'listen queue'

# 현재 listen queue 크기 + 사용량 (Recv-Q / Send-Q)
ss -tlnp
# State    Recv-Q   Send-Q   Local Address:Port
# LISTEN   0        128      0.0.0.0:8080
#          ↑        ↑
#          현재 큐  최대 큐 크기 (somaxconn 또는 backlog 인자)
```

Recv-Q 가 계속 큰 값 → app이 accept() 를 충분히 빨리 못 하고 있다는 신호. = Tomcat의 acceptor가 maxConnections 한도에 걸려 멈춤.

---

## 4. File Descriptor 한계 — 모든 connection의 카운터

### 4-1. 정의

> **모든 열린 socket, file, pipe, eventfd는 file descriptor (FD) 한 개**.
> 한 프로세스가 동시에 들 수 있는 FD 수에 OS 한도가 있다.

### 4-2. 두 단계 한도

```
[System-wide]                  [Per-process]
─────────────                  ─────────────
fs.file-max                    ulimit -n (soft)
(전체 OS의 한도)               ulimit -Hn (hard)
                               /etc/security/limits.conf
                               systemd LimitNOFILE=
보통 수십만~수백만              보통 1024 또는 65535
```

### 4-3. Java/JVM에서 FD가 뭘 쓰나

```
[JVM 프로세스의 FD]
├── stdin/stdout/stderr (3개)
├── classpath jar 파일들 (수십~수백)
├── log 파일들
├── socket: HTTP accept (listen socket, 1개)
├── socket: 활성 HTTP connection (N개)
├── socket: DB connection (HikariCP 풀 × 인스턴스)
├── socket: Redis connection (Lettuce 1개 또는 Jedis pool)
├── socket: 외부 HTTP API (HTTP client pool)
└── 기타 native library가 여는 파일
```

활성 connection이 많은 서버는 쉽게 수천~수만 FD 사용. 기본 `ulimit -n 1024` 로는 부족.

### 4-4. FD 부족 시 증상

```
java.net.SocketException: Too many open files
java.io.IOException: Too many open files

# Nginx 로그
1024 worker_connections are not enough

# 시스템 로그
VFS: file-max limit reached
```

### 4-5. 컨테이너 환경의 함정

Docker/k8s 컨테이너 내부의 `ulimit -n` 은 호스트 설정과 다를 수 있다. systemd 운영에서도 `LimitNOFILE=` 가 unit 파일에 명시되어야 적용된다.

```yaml
# k8s pod spec — securityContext / containers.resources 로는 직접 설정 못함
# initContainer 또는 image의 ENTRYPOINT 에서 ulimit 설정

# docker run --ulimit nofile=65536:65536 ...

# Dockerfile
# RUN ulimit -n 65536  ← 효과 없음 (shell 종료 시 사라짐)
# CMD ["sh", "-c", "ulimit -n 65536 && java -jar app.jar"]  ← 이렇게
```

### 4-6. 진단

```bash
# 현재 프로세스의 FD 한도
cat /proc/$(pgrep java)/limits | grep 'Max open files'

# 현재 사용 중인 FD 수
ls /proc/$(pgrep java)/fd | wc -l

# 어떤 종류가 많은지
ls -l /proc/$(pgrep java)/fd | awk '{print $11}' | sort | uniq -c | sort -rn | head

# system-wide
cat /proc/sys/fs/file-nr
# allocated   unused   max
# 12345       0        9223372036854775807
```

---

## 5. Nginx Worker Connections + Upstream Keepalive

### 5-1. worker_connections — Nginx 자체의 한도

```nginx
worker_processes 8;        # CPU 코어 수만큼
events {
    worker_connections 1024;
    use epoll;
}
```

- **한 worker가 동시에 들 수 있는 connection 수** = 1024
- 이론적 최대 = `worker_processes × worker_connections` = 8 × 1024 = 8192
- **단, 한 client 요청이 2 connection 차지**: client ↔ Nginx 1개 + Nginx ↔ upstream 1개
- 그래서 실제 동시 client 요청 ≈ 4096

### 5-2. worker_connections 와 FD 한계의 관계

```
worker_connections (1024) ≤ ulimit -n (per Nginx worker)
```

worker_connections 늘려도 ulimit -n 이 작으면 효과 없음.

```nginx
worker_rlimit_nofile 65536;  # nginx가 자체 ulimit -n 설정
```

### 5-3. Upstream Keepalive Pool — backend 측 connection 재사용

이것이 **Nginx → Tomcat 의 connection pool**.

```nginx
upstream backend {
    server tomcat1:8080;
    server tomcat2:8080;

    keepalive 32;              # 각 worker가 backend 당 유지하는 idle conn 수
    keepalive_requests 1000;   # 한 conn 으로 처리할 최대 request 수
    keepalive_timeout 60s;     # idle 상태 유지 시간
}

server {
    location / {
        proxy_pass http://backend;
        proxy_http_version 1.1;        # ★ keepalive는 HTTP/1.1 필수
        proxy_set_header Connection "";  # ★ "close" 헤더 제거
    }
}
```

**`proxy_http_version 1.1` 빠뜨리면 keepalive 0% 효과**. 매 요청마다 새 TCP. 가장 흔한 misconfig.

### 5-4. 가득 차면

| 시나리오 | 결과 |
|---|---|
| upstream keepalive 적음 | 자주 새 TCP — Tomcat 측 TIME_WAIT 폭증 |
| keepalive_requests 작음 | conn이 자주 reset — handshake 비용 누적 |
| keepalive_timeout 짧음 | idle conn 빨리 close — 다음 요청에 새 TCP |
| worker_connections 부족 | "1024 worker_connections" 로그 + 새 conn drop |

### 5-5. 진단

```bash
# Nginx stub_status
curl http://localhost/nginx_status
# Active connections: 2913
# server accepts handled requests
#  6398258 6398258 14127762
# Reading: 23  Writing: 167  Waiting: 2723

# Tomcat 측 TIME_WAIT 카운트 (Nginx에서 keepalive 안 되면 폭증)
ss -tan state time-wait | wc -l

# upstream keepalive 효과 확인
ss -tan dst :8080 state established | wc -l  # 활성 conn 수가 일정해야
```

---

## 6. Tomcat의 3가지 한도 — 가장 헷갈리는 부분 ⭐

### 6-1. 세 한도 위치

```
[Client]
   │
   ▼
┌──────────────────────────────────────────┐
│ Tomcat Connector                          │
│                                            │
│  ┌────────────────────────────────────┐  │
│  │ #6. acceptCount                     │  │  ★ kernel TCP backlog
│  │      = listen(fd, acceptCount)       │  │     (somaxconn 으로 잘림)
│  │      socket이 ACCEPT queue 에 대기  │  │
│  └────────────────┬───────────────────┘  │
│                   ▼                       │
│  ┌────────────────────────────────────┐  │
│  │ #7. maxConnections                  │  │  ★ Tomcat 측 conn 카운터
│  │      Tomcat이 직접 카운팅            │  │
│  │      = "현재 살아있는 socket 수"     │  │
│  │      keep-alive 연결 포함            │  │
│  └────────────────┬───────────────────┘  │
│                   ▼                       │
│  ┌────────────────────────────────────┐  │
│  │ #8. maxThreads (Executor)           │  │  ★ worker thread pool
│  │      request 처리 thread 수          │  │
│  │      한 thread = 한 request          │  │
│  │      (동기 servlet model)            │  │
│  └────────────────┬───────────────────┘  │
└───────────────────┼──────────────────────┘
                    ▼
            [Spring 비즈로직]
```

### 6-2. 한도별 의미 + 막힐 때 증상

| 한도 | 무엇을 제한 | 막히면 어디서 멈춤 | 증상 |
|---|---|---|---|
| **acceptCount** | kernel ACCEPT queue 크기 | TCP 레벨 | SYN drop → client `connect timeout` |
| **maxConnections** | Tomcat이 든 socket 수 | Tomcat이 accept() 일시 중지 | LB 측에서 connect 가능하지만 (kernel queue에 들어감) 처리 안 됨 |
| **maxThreads** | request 처리 worker 수 | Request가 Executor queue 대기 | response timeout, slow response, 503 |

### 6-3. HTTP keep-alive와 maxConnections의 상호작용

```
Tomcat NIO Connector + maxConnections=8192
─────────────────────────────────────────
keep-alive 미사용:
  - 한 conn = 한 request 처리 후 close
  - maxConnections 한도는 동시 처리 한도와 일치

keep-alive 사용:
  - 한 conn = 여러 request 순차 처리
  - 한 conn이 살아있는 시간 = request 처리 + idle 대기
  - maxConnections 8192 중 7000개가 idle → 새 client 거부

★ 그래서: keep-alive 켜면 maxConnections를 충분히 크게 설정해야
```

### 6-4. NIO Connector — 동시 conn vs 동시 처리의 분리

Tomcat의 **NIO Connector** (BIO 아닌)에서는:

- 한 thread (Poller)가 **수만 개의 idle conn** 을 epoll로 감시
- request 데이터가 도착한 conn 만 Executor thread로 넘김
- 그래서 maxConnections (idle 포함) ≫ maxThreads (실제 처리) 가능

```
maxConnections=10000  ← Poller가 epoll로 감시 가능
maxThreads=200        ← 실제 처리는 200 동시
```

BIO Connector (Tomcat 9에서 deprecated, 10에서 제거) 에서는 1 conn = 1 thread 였음.

### 6-5. 권장 설정 — 한도들의 상대 관계

```
acceptCount  <  maxConnections  ≥  maxThreads × keep-alive 배수
   (수백)        (수천~수만)         (수백)
```

원칙:
- `acceptCount` 는 임시 burst 흡수용. 크게 잡을 필요 없음 (200 정도).
- `maxConnections` 는 keep-alive로 idle 많이 들고 있게.
- `maxThreads` 는 **하류 자원 (DB pool, 외부 API)의 처리 능력에 맞춰**. 너무 크면 cascading 위험.

### 6-6. 진단

```bash
# Tomcat JMX MBean (jconsole 또는 micrometer)
Catalina:type=ThreadPool,name="http-nio-8080"
  - currentThreadCount         실제 thread 수
  - currentThreadsBusy         일하는 thread 수 (= 처리 중인 request)
  - maxThreads                 한도

Catalina:type=ProtocolHandler,name="http-nio-8080"
  - connectionCount            현재 conn 수
  - maxConnections             한도

# CLI로 확인
curl -u admin:pwd http://host:8080/manager/jmxproxy?qry=Catalina:type=ThreadPool,*

# jstack으로 thread 상태
jstack <pid> | grep 'http-nio-8080-exec' | sort | uniq -c
# RUNNABLE  vs  WAITING (parking)  분포 보기
```

---

## 7. HikariCP DB Pool — 가장 깊이 ⭐⭐

### 7-1. 왜 HikariCP가 표준이 됐나

| 기준 | DBCP / DBCP2 | c3p0 | Tomcat JDBC Pool | **HikariCP** |
|---|---|---|---|---|
| 출시 | 2001 / 2010 | 2003 | 2010 | 2012 |
| getConnection 평균 (ns) | 수천 | 수만 | 1500 | **~200** |
| Lock 방식 | synchronized | synchronized | ReentrantLock | **lock-free (ConcurrentBag)** |
| 코드 크기 | 무거움 | 무거움 | 중간 | **~130KB** (작음) |
| connection leak detection | 있음 (느림) | 있음 | 있음 | 있음 (가벼움) |
| 현황 | legacy | legacy | Tomcat 한정 | Spring Boot 2+ 기본 |

HikariCP가 빠른 이유 = **ConcurrentBag** 자료구조 + JIT 친화적 단순한 코드.

### 7-2. ConcurrentBag — Lock-free Pool 구현

```
┌─────────────────────────────────────────────────────────────┐
│                                                               │
│  ConcurrentBag<PoolEntry>                                     │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ sharedList: CopyOnWriteArrayList<PoolEntry>           │   │
│  │  - 모든 connection (전역)                              │   │
│  │  - reader 안에서는 lock 없음                           │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ threadList: ThreadLocal<List<WeakReference<PoolEntry>>>│  │
│  │  - 스레드별 최근 사용한 conn (warm cache)              │   │
│  │  - 같은 스레드가 다시 borrow하면 같은 conn 받을 확률↑   │   │
│  │  - WeakReference: GC에 방해 안 됨                      │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ handoffQueue: SynchronousQueue<PoolEntry>             │   │
│  │  - 모든 conn이 in-use이고 새 borrow 요청 시            │   │
│  │  - "다음 release 일어나면 나에게 직접 넘겨주세요"        │   │
│  │  - wait/notify의 효율적 대체                          │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

#### borrow (getConnection) 흐름

```
1. threadList 에서 STATE_NOT_IN_USE 인 conn 찾기 (CAS로 USE 마킹)
       │  found
       ▼
   ★ FAST PATH: lock 없이 즉시 반환 (수십 ns)

2. 없으면 sharedList 순회 (still no lock for read)
       │  found
       ▼
   threadList 에 보충 + 반환

3. 여전히 없으면 새 conn 만들 수 있나? (현재 size < maxPoolSize)
       │  yes
       ▼
   비동기로 새 conn 생성 trigger + handoffQueue 에 대기

4. 새 conn도 못 만듦 → handoffQueue.poll(timeout)
       │  누가 release하면 직접 넘김
       ▼
   받음 → 반환
       │
       │ timeout 까지 못 받음
       ▼
   SQLException: "HikariPool-1 - Connection is not available, request timed out after Xms"
```

#### release (close) 흐름

```
1. PoolEntry state를 STATE_NOT_IN_USE로 CAS
2. handoffQueue.tryTransfer() — 대기자 있으면 즉시 넘김
3. 없으면 threadList 에서는 그대로 유지 (warm)
```

### 7-3. HikariCP의 핵심 옵션

| 옵션 | 기본값 | 의미 | 실무 권장 |
|---|---|---|---|
| `maximumPoolSize` | 10 | 최대 conn 수 | DB max 의 (1/인스턴스 수)의 80% |
| `minimumIdle` | maximumPoolSize | 항상 유지할 idle 수 | == max 권장 (warmup 효과) |
| `connectionTimeout` | 30000ms | getConnection() 대기 max | **3000ms** (cascading 방지) |
| `idleTimeout` | 600000ms | idle conn 정리 시간 | minimumIdle == max이면 의미 없음 |
| `maxLifetime` | 1800000ms (30분) | conn 최대 수명 | **firewall idle보다 짧게** (10분 등) |
| `validationTimeout` | 5000ms | isValid() 검증 max | 보통 그대로 |
| `leakDetectionThreshold` | 0 (off) | leak 감지 시간 | **10000ms** (10초)로 enable |

### 7-4. Connection의 라이프사이클

```
   create ────▶ idle (in pool) ◀─────┐
                    │                  │
                    │ borrow            │ release (close)
                    ▼                  │
                in-use (with app) ─────┘
                    │
                    │ maxLifetime 도달
                    ▼
                marked for eviction
                    │ 다음 release 시 destroy
                    ▼
                destroy ────▶ DB는 BackendDie / FIN
```

### 7-5. Proxy Connection — close()가 실제 close가 아님

```java
Connection conn = dataSource.getConnection();
// 실제로는 HikariProxyConnection (PoolEntry 감싼 proxy)
conn.close();
// 실제로는 close()가 아니라 HikariCP 풀에 return
```

HikariCP는 `getConnection()` 시 **proxy를 새로 만들어** 반환한다. 그 proxy의 `close()` 는 진짜 close 대신 **풀에 return** 만 한다.

이게 중요한 이유: **try-with-resources 로 안전하게 close 가능**. 실제 conn은 풀에 그대로 남음.

```java
try (Connection conn = ds.getConnection();
     PreparedStatement ps = conn.prepareStatement(sql)) {
    // ... 사용
} // ← 자동 close = 자동 return to pool
```

### 7-6. DB의 max_connections와의 관계

```
[1개 PostgreSQL]
max_connections = 100
                                       (총 80% 이하 권장)

[N개 App 인스턴스] × [HikariCP maximumPoolSize]
            5      ×          16            = 80 ≤ 100 ✓

  → 인스턴스 늘리면 pool size 줄여야
  → 또는 PgBouncer 같은 multiplexer 사용
```

**가장 흔한 실수**: 인스턴스 10개 × HikariCP 20 = 200 connection을 DB(max=100)에 요청 → 절반은 거부. 운영팀이 "DB가 거부한다" 라고 보고하면 보통 이것.

### 7-7. PgBouncer / ProxySQL — Connection Multiplexer

DB 측 connection이 너무 비싸서 (PostgreSQL은 1 conn = 1 OS process) — 중간에 multiplexer.

```
[App * 100 instances]                  [PgBouncer]              [PostgreSQL]
HikariCP pool 20 each                  pool 1000                max=100
            │                              │                        │
            │  세션 모드                    │  실제 DB conn 100         │
            └─────────────────────────────▶│◀───────────────────────│
                                            │
                                            │  ★ 트랜잭션 끝나면
                                            │     실제 conn 재활용
                                            ▼
                                       PgBouncer가 transaction마다
                                       다른 DB conn 매핑 (transaction mode)
```

**모드 3가지**:
- **Session mode**: client conn = DB conn 1:1 (의미 없음, 기본)
- **Transaction mode**: 트랜잭션마다 새 mapping. **prepared statement 못 씀** (다음 트랜잭션에 다른 conn).
- **Statement mode**: SQL마다 새 mapping. 거의 안 씀.

운영 함정: Transaction mode + Spring `@PreparedStatement` → 작동 안 함.

### 7-8. 진단 — HikariCP의 상태 보기

```java
// HikariCP MXBean
HikariDataSource hds = ...;
HikariPoolMXBean pool = hds.getHikariPoolMXBean();

pool.getActiveConnections();    // 사용 중
pool.getIdleConnections();       // 풀에 idle
pool.getTotalConnections();      // = active + idle
pool.getThreadsAwaitingConnection();  // ★ 대기 중인 thread (병목 지표)
```

```java
// Micrometer
@Bean
MeterFilter hikariMetrics() {
    return MeterFilter.acceptNameStartsWith("hikaricp");
}

// 자동 노출되는 메트릭
// hikaricp.connections.active
// hikaricp.connections.idle
// hikaricp.connections.pending       ← 대기 thread 수
// hikaricp.connections.timeout       ← timeout 발생 횟수
// hikaricp.connections.acquire       ← acquire 시간 (Timer)
// hikaricp.connections.usage         ← 사용 시간 (Timer)
```

**핵심 메트릭**:
- `pending > 0` 이 지속 → pool 부족 또는 DB 느림
- `acquire P99` 가 ms 단위로 튀면 → pool 고갈 시점
- `usage P99` 가 100ms 넘으면 → SQL 자체가 느림 (pool 문제 아님)

---

## 8. HTTP Client Pool — 외부 API 호출의 풀

### 8-1. Java HTTP client 종류와 pool 모델

| 라이브러리 | Pool 클래스 | 모델 | 특징 |
|---|---|---|---|
| Apache HttpClient | `PoolingHttpClientConnectionManager` | per-route | 가장 많이 씀, blocking |
| OkHttp | `ConnectionPool` | per-host | Square 사, HTTP/2 지원 |
| Java 11 HttpClient | 내장 | per-origin | 표준 (`java.net.http`) |
| Reactor Netty (WebClient) | `ConnectionProvider` | per-host | non-blocking, Spring WebFlux |

### 8-2. Per-route vs Global Pool

```
[Per-route pool — Apache HttpClient]
                                       host A    host B    host C
ConnectionPool                          ┌────┐    ┌────┐    ┌────┐
  defaultMaxPerRoute=20  ────────────▶ │ 20 │    │ 20 │    │ 20 │
  maxTotal=100            ────────────▶ ┌────────────────────────┐
                                        │ 모든 host 합쳐 100      │
                                        └────────────────────────┘

[Global pool — 어떤 host든 한 pool 공유]
                                       host A + host B + host C
                                        ┌────────────────────────┐
                                        │ 한 풀에서 자원 경쟁      │
                                        └────────────────────────┘
```

운영 함정: 한 host가 느려지면 — per-route pool은 다른 host에 영향 없음 (격리됨). Global pool은 모두 영향.

### 8-3. Apache HttpClient 설정

```java
PoolingHttpClientConnectionManager cm = new PoolingHttpClientConnectionManager();
cm.setMaxTotal(200);             // 전체 max
cm.setDefaultMaxPerRoute(20);    // 한 route 당 max
cm.setValidateAfterInactivity(10000);  // 10초 idle 후 사용 전 검증

HttpClient client = HttpClients.custom()
    .setConnectionManager(cm)
    .setConnectionTimeToLive(60, TimeUnit.SECONDS)  // ★ maxLifetime
    .build();
```

### 8-4. TLS / HTTPS Connection Pool

HTTPS는 TCP + TLS handshake 모두 비용. **풀이 재사용하면 큰 이득** (수백 ms 절약).

추가로 TLS session resumption:
- Session ID
- Session Ticket (TLS 1.2)
- PSK (TLS 1.3)

이건 풀과 별개의 메커니즘. 풀이 끊겨도 같은 host에 다시 connect할 때 handshake 일부 생략.

### 8-5. WebClient (Reactor Netty)

```java
ConnectionProvider provider = ConnectionProvider.builder("custom")
    .maxConnections(500)
    .maxIdleTime(Duration.ofSeconds(20))
    .maxLifeTime(Duration.ofMinutes(10))
    .pendingAcquireTimeout(Duration.ofSeconds(5))
    .evictInBackground(Duration.ofSeconds(30))
    .build();

WebClient client = WebClient.builder()
    .clientConnector(new ReactorClientHttpConnector(
        HttpClient.create(provider)))
    .build();
```

**중요한 차이**: WebClient는 **non-blocking**. 한 connection이 multiplexing (HTTP/2) 가능. 그래서 pool size 더 작아도 됨.

### 8-6. 진단

```bash
# 외부 API 호출 connection 수
ss -tan dst :443 state established | wc -l

# Apache HttpClient JMX (활성화 필요)
# org.apache.http.impl.client:type=PoolStats
```

---

## 9. Redis Pool — Jedis vs Lettuce 의 근본적 차이

### 9-1. 왜 Jedis는 pool이 필요하고 Lettuce는 안 필요한가

```
[Jedis — thread-unsafe]
─────────────────────
Jedis 인스턴스 1개 = TCP socket 1개
   │
   │ 한 thread만 동시에 쓸 수 있음 (thread-unsafe)
   │
   ▼
JedisPool 필수: thread 마다 빌렸다가 반납
```

```
[Lettuce — thread-safe (Netty 기반)]
─────────────────────────────────
RedisClient → StatefulRedisConnection 1개
   │
   │ 여러 thread 동시 사용 가능 (multiplexing)
   │ Netty의 single channel 위에서 N개 command pipeline
   │
   ▼
풀 불필요 (default), 또는 작은 풀
```

### 9-2. Lettuce의 multiplexing 동작

```
Thread 1: client.get("a") ─┐
Thread 2: client.get("b") ─┼─▶ 한 TCP socket ─▶ Redis server
Thread 3: client.set("c")  ─┘    (Netty channel)
                                  │
                                  │ Redis는 한 client 당
                                  │ command 순서대로 처리
                                  ▼
                            response → Netty handler
                                  │
                                  │ pendingCommands queue
                                  ▼
                            각 thread의 future complete
```

순서가 보장되고 (RESP protocol은 pipeline 친화적), pool 없이 한 socket 만 써도 됨.

**예외**: `BLPOP` 같은 **blocking command**는 한 connection을 점유. 이 경우 별도 connection 필요. Lettuce는 자동으로 처리.

### 9-3. Spring Boot의 기본

Spring Boot 2.x+는 기본이 **Lettuce**. `spring-boot-starter-data-redis-jedis` 명시해야 Jedis 사용.

### 9-4. Cluster Mode

```
[Redis Cluster]
─────────────
node 1 (slot 0-5460)
node 2 (slot 5461-10922)
node 3 (slot 10923-16383)

Lettuce: 한 node 당 한 connection (총 3개)
         CRC16(key) % 16384 = slot → 해당 node connection으로

Jedis: JedisCluster — 각 node 별 JedisPool 보유 (총 3 pool)
```

### 9-5. 진단

```bash
# Redis 측 client 수
redis-cli CLIENT LIST | wc -l

# Lettuce JMX (활성화 필요)
io.lettuce.core:type=metrics

# 운영 확인 패턴
redis-cli INFO clients
# connected_clients: 23
# blocked_clients: 0     ← BLPOP 등으로 blocked
# tracking_clients: 0
```

---

## 10. Application 내부 Thread Pool

### 10-1. ExecutorService 종류

```
Executors.newFixedThreadPool(N)
  ├─ ThreadPoolExecutor
  │    corePoolSize=N, maximumPoolSize=N
  │    queue = LinkedBlockingQueue (★ unbounded!)
  └─ 함정: queue가 무한 → OOM 위험

Executors.newCachedThreadPool()
  ├─ ThreadPoolExecutor
  │    corePoolSize=0, maximumPoolSize=Integer.MAX_VALUE
  │    queue = SynchronousQueue (즉시 thread 생성)
  └─ 함정: thread 수 무한 → OS thread 폭발

Executors.newSingleThreadExecutor()
  └─ 직렬 처리. 한 작업 hang 하면 전부 멈춤

Executors.newScheduledThreadPool(N)
  └─ 주기 실행. ScheduledThreadPoolExecutor.
```

### 10-2. newFixedThreadPool의 OOM 함정

```java
ExecutorService es = Executors.newFixedThreadPool(10);
// 내부 queue가 LinkedBlockingQueue() — unbounded

while (true) {
    es.submit(() -> heavyTask());
}
// task 가 queue에 무한 적체 → Heap OOM
```

**올바른 방식**:

```java
new ThreadPoolExecutor(
    10, 10,                              // core, max
    0L, TimeUnit.MILLISECONDS,
    new LinkedBlockingQueue<>(1000),    // ★ bounded!
    new ThreadPoolExecutor.AbortPolicy() // queue 가득 → RejectedExecutionException
);
```

### 10-3. ForkJoinPool.commonPool — 숨겨진 풀

`parallelStream`, `CompletableFuture` 의 default executor가 **공유 풀**.

```java
list.parallelStream().map(...).collect(...);
// 내부적으로 ForkJoinPool.commonPool() 사용
// 크기 = Runtime.getRuntime().availableProcessors() - 1
```

**위험**: 같은 JVM의 다른 코드도 commonPool 사용. 한 곳에서 long task → 다른 곳 멈춤.

```java
// 해결: 자기 ForkJoinPool
ForkJoinPool customPool = new ForkJoinPool(8);
customPool.submit(() -> list.parallelStream().map(...).collect(...)).get();
```

### 10-4. Virtual Thread (JDK 21+)와의 관계

Platform thread (전통 OS thread)는 비싸서 pool 필요. Virtual thread는 가벼워서 (1 vthread ≈ 수 KB stack) **풀 없이** `Thread.startVirtualThread()` 마음껏 가능.

```java
// JDK 21+
Executors.newVirtualThreadPerTaskExecutor()
// 실제로는 pool이 아니라 매번 새 virtual thread
```

다만 **DB pool, HTTP pool 같은 외부 자원 pool은 여전히 필요** — 외부 자원은 virtual thread여도 비싸다.

### 10-5. 연결: jvm/05-threading 챕터

→ 자세한 thread 내부 (synchronized, JMM, virtual thread continuation) 은 `jvm/05-threading/` 챕터 참조.

---

## 11. DB 측 풀 — Server-side 한도

### 11-1. PostgreSQL vs MySQL의 connection 모델

```
[PostgreSQL]
1 connection = 1 OS backend process (fork-based, heavy)
   - 메모리: ~10MB per backend
   - max_connections=100 → 100 process
   - context switch 비용 큼

[MySQL]
1 connection = 1 OS thread (thread-based, lighter)
   - 메모리: ~256KB per thread (lighter)
   - max_connections=151 (default)
   - 그래도 100,000+ 는 무리
```

→ PostgreSQL이 conn 비용 더 비싸서 PgBouncer 더 흔히 씀.

### 11-2. max_connections 초과 시

```sql
-- PostgreSQL
FATAL: sorry, too many clients already

-- MySQL
ERROR 1040 (HY000): Too many connections
```

**superuser_reserved_connections**: PostgreSQL은 max 중 일부 (기본 3) 를 superuser용으로 예약. 일반 사용자가 다 차면 admin이 들어가서 진단 가능하도록.

### 11-3. DB의 idle connection 관리

```sql
-- PostgreSQL
SELECT pid, state, query_start, state_change
FROM pg_stat_activity
WHERE state = 'idle' AND now() - state_change > interval '1 hour';

-- 오래 idle인 connection을 강제 종료
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
WHERE state = 'idle' AND now() - state_change > interval '1 hour';

-- 또는 idle_in_transaction_session_timeout 설정으로 자동 종료
```

### 11-4. Connection Multiplexer (재방문)

§7-7 의 PgBouncer 외에:
- **ProxySQL** (MySQL용)
- **AWS RDS Proxy** (관리형, transaction mode)
- **Azure SQL Connection Pooling**

선택 기준:
- App 인스턴스 × HikariCP 크기 ≤ DB max → 불필요
- 그 이상 + transaction이 짧다 → PgBouncer transaction mode
- 그 이상 + prepared statement 의존 → session mode (재사용 효과 적음)

---

## 12. Connection Lifecycle와 Keepalive — 가장 흔한 운영 함정 ⭐

### 12-1. 3가지 layer의 keepalive

```
[Layer 1] TCP keepalive (커널 레벨)
─────────────────────────────────
net.ipv4.tcp_keepalive_time=7200      (2시간 idle 후 첫 probe)
net.ipv4.tcp_keepalive_intvl=75       (probe 간격)
net.ipv4.tcp_keepalive_probes=9       (실패 인정 횟수)

★ 기본 2시간은 너무 길어서 firewall이 먼저 끊음

[Layer 2] HTTP keepalive (application 레벨)
────────────────────────────────────────
HTTP/1.1: Connection: keep-alive (default)
HTTP/1.0: Connection: close (default)

Nginx keepalive_timeout 60s
Tomcat keepAliveTimeout 60000

[Layer 3] DB connection keepalive
──────────────────────────────
HikariCP keepaliveTime  (JDBC validation 주기)
HikariCP maxLifetime    (강제 갱신 주기)
```

### 12-2. Firewall / NAT idle timeout — 침묵의 살인자

운영 환경 (특히 AWS NAT Gateway, 사내 firewall) 은 보통 **300초 (5분)** idle 후 conn 강제 close. 양쪽에는 **알려주지 않음** (RST 보내지 않음).

```
앱 ─────TCP conn────▶ firewall ─────TCP conn────▶ DB
         ↑                              ↑
         "살아있음"                      "살아있음"
                          5분 idle
                              │
                              ▼
                         firewall이 entry 삭제
                              │
                              │ 양쪽엔 알림 없음
                              ▼
                         두 endpoint는 "살아있다고 믿음"

         다음 query 보내면
         ──── packet ────▶ firewall (no entry) ────▶ DROP
                                                       │
                                                       │ 응답 없음
                                                       ▼
                                              SO_TIMEOUT 까지 hang (보통 수십 초~분)
```

**증상**:
- "오랜만에 호출하면 첫 query가 timeout"
- "새벽 시간대 첫 요청만 느림"
- HikariCP 의 `Connection is not available` 가 간헐적
- 재시도하면 됨 (새 conn 만들어서)

### 12-3. 해결 — maxLifetime을 firewall idle 보다 짧게

```
firewall idle timeout: 300s (5분)
                ↓
HikariCP maxLifetime: 180000ms (3분) ← 더 짧게

  → HikariCP가 conn을 3분마다 강제 destroy + recreate
  → firewall이 끊기 전에 우리가 먼저 갱신
  → "stale conn" 못 만남
```

추가:
- `keepaliveTime` (HikariCP 4.0+): idle 중에도 주기적으로 SELECT 1 으로 살아있는지 확인
- TCP_KEEPALIVE 옵션도 같이 설정 (JDBC URL에 따라 다름)

### 12-4. 도식

```
[정상]
─────
   app                    firewall                  DB
    │                         │                      │
    │── conn create ─────────▶│─────────────────────▶│  (180s 후 destroy)
    │                         │                      │
    │── new conn ────────────▶│─────────────────────▶│
    │                         │                      │
    │                          ↑ 3분마다 갱신
    │                          ↑ firewall 5분 limit 안 침범

[문제 — maxLifetime > firewall idle]
──────────────────────────────────
   app                    firewall                  DB
    │                         │                      │
    │── conn create ─────────▶│─────────────────────▶│  (30분 후 destroy 예정)
    │                                                 │
    │     5분 idle                                    │
    │                          ↓ firewall entry 삭제 │
    │── query ───X (drop)      │                      │
    │                                                 │
    │  hang... timeout ⏰                              │
```

---

## 13. Pool 튜닝 — Little's Law

### 13-1. Little's Law (1961)

> **L = λ × W**
> 동시 처리 중인 작업 수 = 도착률 × 평균 처리 시간

### 13-2. Pool size 계산 응용

```
[목표] 1초당 1000 request 처리, 평균 처리 시간 50ms

L = 1000 req/s × 0.05 s = 50

→ 동시 50개 request가 시스템에 머무름
→ Tomcat maxThreads ≥ 50
→ 그 50 thread가 동시에 DB query 하면 → HikariCP ≥ 50 (이론적)
   실제로는 thread 가 DB call 만 하는 게 아니므로 더 작아도 OK
```

### 13-3. HikariCP의 권장 공식

HikariCP 위키에 적힌 공식:

> **pool size = ((core_count × 2) + effective_spindle_count)**

- core_count: DB 서버의 CPU 코어 수
- spindle_count: 디스크 수 (SSD면 1)

예: 8 core, SSD → `(8 × 2) + 1 = 17`. **너무 작아 보이지만** — 이게 실제 권장.

**왜 작은가**:
- DB는 동시 query 늘면 context switch 폭발 → throughput 떨어짐
- DB CPU 100% 도달하면 그 이상은 무의미 (queueing만 늘어남)
- 작은 pool로 빠른 turnover가 큰 pool로 느린 처리보다 빠름

### 13-4. "큰 pool"의 함정

```
[Pool = 100]                          [Pool = 20]
─────────                              ─────────
DB에 100 동시 query                    DB에 20 동시 query
   │                                       │
   ▼                                       ▼
context switch 폭증                     CPU 효율적 사용
DB CPU 100%                            DB CPU 70%
   │                                       │
   ▼                                       ▼
각 query 평균 200ms                     각 query 평균 50ms
   │                                       │
   ▼                                       ▼
throughput = 500 q/s                   throughput = 400 q/s
                                           ↑
                                       비슷한데 P99이 훨씬 낮음
```

### 13-5. 측정 기반 튜닝 — Wait Time + Utilization

```
[지표]
  pool.utilization = active / max
  pool.wait_time_p99 = getConnection() 의 P99

[해석]
utilization < 50% + wait_time ≈ 0
  → pool 충분, 더 줄여도 됨

utilization > 80% + wait_time 증가
  → pool 부족, 더 늘려야

utilization 100% + wait_time spike + DB CPU 정상
  → pool 부족이 맞음

utilization 100% + wait_time spike + DB CPU 100%
  → pool 늘려도 무의미 (DB가 병목)
     → SQL 튜닝, 인덱스, sharding
```

---

## 14. Pool 상호작용 — Cascading Failure 시나리오 ⭐⭐

### 14-1. 시나리오: "DB 한 query가 느려졌다"

```
[T0. 정상]
─────────
HikariCP: active=5, idle=15, max=20
Tomcat:   busy thread=50, max=200
Nginx:    upstream conn=8

[T1. DB 한 table에 lock 또는 slow query 발생]
─────────────────────────────────────────
한 query가 1s 걸리는 게 30s로 늘어남
HikariCP: 해당 connection이 30s 동안 점유됨
          active=15, idle=5
```

```
[T2. 점유가 누적]
───────────────
30s 동안 새 요청이 계속 들어옴
새 요청은 HikariCP에서 conn 빌림
   ↓
이 요청들도 모두 30s 걸림
   ↓
HikariCP: active=20 (MAX), idle=0
   ↓
새 요청은 getConnection() 대기
   ↓
connectionTimeout (30s 기본) 후 SQLException
```

```
[T3. Tomcat thread 점유]
────────────────────
HikariCP 에서 대기하는 Tomcat thread 들도
   ↓
모두 BLOCKED 상태 (park)
   ↓
Tomcat: busy thread = 200 (MAX), idle=0
   ↓
새 요청은 Executor queue에 적체
   ↓
maxConnections 도달 시 accept 멈춤
```

```
[T4. Health check 실패]
─────────────────────
LB의 health check (10s 주기) endpoint도 처리 못 함
   ↓
health check timeout
   ↓
LB가 이 인스턴스를 unhealthy 마킹 → 트래픽 끊음
   ↓
나머지 인스턴스에 부하 폭주
   ↓
나머지 인스턴스도 같은 cascade → 전체 down
```

```
[T5. 폭주]
────────
모든 인스턴스가 unhealthy
   ↓
LB가 503 또는 504 반환
   ↓
서비스 다운
```

### 14-2. 방어 패턴

**1. connectionTimeout 짧게**

```java
hikari.setConnectionTimeout(3000);  // 3초
```
- 기본 30s 면: 30s 동안 thread가 점유됨
- 3s 면: 3s 후 즉시 SQLException → thread 해방
- "느린 정상" 대신 "빠른 실패"

**2. Circuit Breaker (Resilience4j)**

```java
@CircuitBreaker(name = "db", fallbackMethod = "fallback")
public User getUser(Long id) {
    return userRepo.findById(id);
}

public User fallback(Long id, Throwable t) {
    return cache.get(id);  // 또는 default
}
```

- 일정 % 이상 실패 → circuit open
- open 상태에서는 즉시 fallback (DB 호출 안 함)
- HikariCP 점유 방지

**3. Bulkhead (격리)**

```java
@Bulkhead(name = "expensiveOp", type = SEMAPHORE)  // 동시 10개만
public List<...> expensiveQuery() { ... }
```

- 비싼 query는 별도 카운터로 격리
- 전체 thread 점유 방지

**4. Timeout 계층**

```
client → LB:        30s   (max)
LB → Nginx:         25s
Nginx → Tomcat:     20s
Tomcat → DB query:  10s    ← 가장 안쪽이 가장 짧게
HikariCP getConn:   3s
```

원칙: **안쪽일수록 짧은 timeout**. 그래야 외곽이 응답 받지 못한 후 즉시 다음 시도.

---

## 15. 진단 도구 — 풀 상태 실시간 보기

### 15-1. TCP 레벨

```bash
# State 분포
ss -tan | awk '{print $1}' | sort | uniq -c

# 결과 예
#   2   ESTAB
# 432   TIME_WAIT      ← 많으면 keep-alive 안 됨
#  21   LISTEN
#   3   SYN_SENT       ← 많으면 외부 API 응답 느림
#   8   CLOSE_WAIT     ← 많으면 app이 socket close 안 함 (leak)

# 특정 포트의 ESTAB conn 수
ss -tan dst :5432 state established | wc -l   # DB 측 conn

# TIME_WAIT 폭증 시 — Nginx upstream keepalive 미설정 의심
netstat -an | awk '{print $6}' | sort | uniq -c | sort -rn
```

### 15-2. Java/JVM 레벨

```bash
# Thread 상태 분포
jstack $(pgrep java) | grep 'java.lang.Thread.State' | sort | uniq -c

# 결과 예
# 150 java.lang.Thread.State: RUNNABLE
# 200 java.lang.Thread.State: WAITING (parking)     ← HikariCP 대기 의심
#  50 java.lang.Thread.State: TIMED_WAITING
#   5 java.lang.Thread.State: BLOCKED               ← synchronized 경합

# HikariCP 대기 thread 찾기
jstack $(pgrep java) | grep -B 5 'HikariPool\|getConnection'

# Tomcat thread 상태
jstack $(pgrep java) | grep -A 1 'http-nio-8080-exec' | grep 'State'
```

### 15-3. HikariCP 메트릭 (Micrometer)

```
hikaricp.connections.active{pool="HikariPool-1"}
hikaricp.connections.idle{pool="HikariPool-1"}
hikaricp.connections.pending{pool="HikariPool-1"}   ★ 대기자
hikaricp.connections.timeout{pool="HikariPool-1"}   ★ timeout 발생 횟수
hikaricp.connections.acquire{pool="HikariPool-1"}   ★ acquire latency (Timer)
hikaricp.connections.usage{pool="HikariPool-1"}     ★ usage latency
hikaricp.connections.creation                       ★ create 횟수
```

Grafana 알람 예:
- `pending > 0 for 5m` → pool 부족
- `timeout > 0` → 즉시 알람 (절대 발생하면 안 됨)
- `acquire_p99 > 100ms` → pool 또는 DB 이상

### 15-4. Nginx 메트릭

```bash
# stub_status (nginx 모듈 활성화 필요)
curl http://localhost/nginx_status
# Active connections: 291
# server accepts handled requests
#  639825 639825 1412776
# Reading: 23  Writing: 167  Waiting: 101
#                            ↑
#                            keep-alive 로 idle 한 conn 수

# Prometheus exporter
# nginx_connections_active
# nginx_connections_reading
# nginx_connections_writing
# nginx_connections_waiting
# nginx_http_requests_total
```

### 15-5. Tomcat 메트릭

```bash
# JMX via jcmd
jcmd $(pgrep java) JFR.start duration=60s filename=/tmp/recording.jfr
# JFR 분석에서 Tomcat thread 상태, request latency 확인

# 또는 Micrometer
# tomcat.threads.busy
# tomcat.threads.current
# tomcat.threads.config.max
# tomcat.connections.current
# tomcat.connections.config.max
```

### 15-6. DB 측

```sql
-- PostgreSQL: 현재 connection 상태
SELECT state, count(*) FROM pg_stat_activity GROUP BY state;
-- active        45
-- idle          30
-- idle in trans 2     ← 위험! transaction 안 끝남
-- waiting        0

-- 누가 conn 점유 중?
SELECT application_name, count(*) FROM pg_stat_activity GROUP BY application_name;

-- 오래 idle in transaction
SELECT pid, query, state_change FROM pg_stat_activity
WHERE state = 'idle in transaction' AND now() - state_change > interval '1 minute';

-- MySQL
SHOW PROCESSLIST;
SHOW STATUS LIKE 'Threads_connected';
SHOW STATUS LIKE 'Max_used_connections';
```

---

## 16. 운영 시나리오 — 증상 → 진단 → 해결

### 시나리오 1. "P99 latency가 갑자기 2초로 튀었다"

```
[증상] P99 200ms → 2000ms, P50은 변화 없음

[1차 의심] HikariCP wait time 증가
  jcmd $(pgrep java) JFR.dump filename=now.jfr
  → JFR Mission Control에서 jdk.JavaMonitorWait 이벤트 확인
  → "HikariPool-1" 의 wait 가 P99에 spike

[2차 진단] DB 측 상태
  SELECT state, count(*) FROM pg_stat_activity GROUP BY state;
  → idle in transaction 이 50개

[원인] @Transactional 안에서 외부 API 호출 → 외부 API 느려져서 transaction 길어짐
  → DB conn 점유 길어짐 → HikariCP 고갈 → wait 폭증

[해결]
  1. 즉시: HikariCP maximumPoolSize 일시 증가 (응급)
  2. 근본: @Transactional 메서드에서 외부 API 호출 분리
  3. 모니터링: pg_stat_activity.idle_in_transaction 알람 추가
```

### 시나리오 2. "503 폭증 — Tomcat busy thread 100%"

```
[증상] 503 Service Unavailable 폭증, jstack 보니 thread 200/200 BUSY

[1차 진단] thread 들이 무엇을 하고 있나
  jstack $(pgrep java) | grep -A 30 'http-nio-8080-exec-1'
  → 대부분 HikariCP.getConnection() 에서 park

[2차] HikariCP 측
  Micrometer hikaricp.connections.pending 메트릭
  → 100+ 대기

[3차] DB
  pg_stat_activity 의 active query 중 long-running 찾기

[원인] 한 slow query가 lock 잡고 있음 → 다른 query 들도 대기 → HikariCP 점유

[해결]
  1. 즉시: long-running query KILL (pg_terminate_backend)
  2. 단기: connectionTimeout 30s → 3s 로 줄여 fast-fail
  3. 근본: 해당 query 인덱스 추가, 또는 statement_timeout 설정
```

### 시나리오 3. "DB CPU는 정상인데 앱이 느림"

```
[증상] DB CPU 30%, 그런데 P99 latency 1s

[1차] HikariCP wait 보기
  → wait 가 거의 없음

[2차] thread 상태
  jstack → 외부 API 호출에서 wait 가 많음
  RestTemplate / WebClient stack

[3차] HTTP client pool 측
  Apache HttpClient JMX → "leased=200, available=0, max=200"

[원인] 외부 API 응답이 느림 + HTTP client pool 작음 → 대기

[해결]
  1. HTTP client pool 증가
  2. timeout 짧게 (외부 API 의 SLA 에 맞춰)
  3. circuit breaker 적용
  4. 외부 API 와 SLA 협상
```

### 시나리오 4. "Deploy 후 첫 요청들이 느림"

```
[증상] 배포 직후 5분간 P99 spike, 이후 정상

[원인 후보]
1. JIT warmup — Java 코드가 native compile 되기 전
2. HikariCP pool warmup — minimumIdle 미설정 → 첫 요청에 lazy create
3. Connection 캐시 비어있음 — Nginx upstream keepalive
4. DNS lookup — 첫 호출에 DNS resolve

[해결]
1. HikariCP: minimumIdle = maximumPoolSize 로 설정 → 부팅 시 다 만듦
2. Application 부팅 직후 warmup endpoint 호출
   @PostConstruct void warmup() {
       jdbcTemplate.queryForObject("SELECT 1", Integer.class);
       restTemplate.getForObject(externalApi + "/health", String.class);
   }
3. JIT warmup: AppCDS 또는 CRaC (Java 21+)
```

### 시나리오 5. "재배포 시 Metaspace OOM"

```
[증상] 핫 디플로이 환경 (Tomcat 등) 에서 N번 재배포 후 Metaspace OOM

[1차] jcmd VM.metaspace
  → Metaspace 사용량이 deploy 마다 증가, 회수 안 됨

[2차] heap dump → MAT
  → 옛날 ClassLoader 가 남아있음

[원인] static field 가 옛 ClassLoader 의 객체 가리킴
  - Hikari가 만든 thread (HouseKeeper 등) 가 옛 ClassLoader context
  - 외부 lib의 static cache

[해결]
1. application context shutdown 시 DataSource.close() 호출
2. Tomcat: ServletContextListener.contextDestroyed 에서 HikariDataSource.close()
3. 또는 hot deploy 포기, blue-green deploy
```

### 시나리오 6. "Connection refused — 정상 시간대인데"

```
[증상] 가끔 ConnectException: Connection refused

[1차] Tomcat 로그 — "Maximum number of threads (200) created"
  → maxThreads 한도 도달

[2차] OS — ss -tan | grep 8080 | wc -l
  → ESTAB 5000+ — keep-alive idle conn 누적

[원인] Nginx upstream keepalive 미설정 → Tomcat 측 conn 누적 → maxConnections 도달

[해결]
1. Nginx upstream keepalive 32 설정
2. proxy_http_version 1.1
3. Connection "" 헤더 (close 제거)
4. Tomcat keepAliveTimeout 짧게 (10s)
```

---

## 17. 백지 마스터 다이어그램 — 모든 풀 한 장에

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                       │
│                      한 요청이 만나는 모든 풀                         │
│                                                                       │
│  [Client]                                                             │
│     │                                                                 │
│     │ TCP SYN                                                         │
│     ▼                                                                 │
│  ┌────────────────────────────────────────────────────┐              │
│  │ LB 호스트                                            │              │
│  │   #1 kernel SYN/ACCEPT queue (somaxconn)            │              │
│  │   #2 conntrack table                                │              │
│  │   #3 LB → backend keepalive (LB 자체)               │              │
│  └─────────────────┬──────────────────────────────────┘              │
│                    │                                                  │
│                    ▼                                                  │
│  ┌────────────────────────────────────────────────────┐              │
│  │ Nginx                                               │              │
│  │   #4 worker_connections (per worker)                │              │
│  │   #5 upstream keepalive → Tomcat                    │              │
│  │   + 자체 FD 한도 (worker_rlimit_nofile)             │              │
│  └─────────────────┬──────────────────────────────────┘              │
│                    │                                                  │
│                    ▼                                                  │
│  ┌────────────────────────────────────────────────────┐              │
│  │ Tomcat (JVM)                                        │              │
│  │   #6 acceptCount (kernel backlog)                   │              │
│  │   #7 maxConnections (Tomcat 자체)                   │              │
│  │   #8 Executor maxThreads                            │              │
│  │   + JVM heap, Direct Memory, FD 한도                │              │
│  └─────────────────┬──────────────────────────────────┘              │
│                    │                                                  │
│                    ▼                                                  │
│  ┌────────────────────────────────────────────────────┐              │
│  │ Spring App                                          │              │
│  │   #9  HikariCP (maxPoolSize, connectionTimeout,     │              │
│  │       maxLifetime, ConcurrentBag)                   │              │
│  │   #10 HTTP client pool (Apache/OkHttp/WebClient)    │              │
│  │   #11 Redis pool (Jedis pool / Lettuce 단일)        │              │
│  │   #13 ForkJoinPool.commonPool, @Async executor      │              │
│  └─────────────────┬──────────────────────────────────┘              │
│                    │                                                  │
│         ┌──────────┴──────────┐                                       │
│         ▼                     ▼                                       │
│  ┌─────────────┐       ┌─────────────┐                                │
│  │ DB          │       │ Redis       │                                │
│  │  #12        │       │             │                                │
│  │  max_       │       │             │                                │
│  │  connections│       │             │                                │
│  └─────────────┘       └─────────────┘                                │
│                                                                       │
│  cascade 위험 방향: ←─── (아래가 막히면 위가 적체)                    │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

### 한 줄 정리

> **"한 요청은 kernel backlog → Nginx worker → upstream keepalive → Tomcat acceptCount/maxConnections/maxThreads → HikariCP/HTTPClient/Redis → DB max_connections 까지 7~13개 풀을 통과한다. 어느 한 풀이 비면 위쪽이 적체되고, 가장 흔한 cascade는 DB slow query → HikariCP 점유 → Tomcat thread 점유 → maxConnections 도달 → health check 실패 → 인스턴스 격리 → 나머지 인스턴스 폭주. 방어는 (1) 안쪽일수록 짧은 timeout, (2) circuit breaker, (3) bulkhead, (4) Little's Law 기반 측정 튜닝."**

---

## 18. 트레이드오프 마스터 표

### 18-1. Pool 크기

| pool 크다 | pool 작다 |
|---|---|
| 동시 처리량 ↑ | wait time ↑ |
| DB context switch ↑ → 평균 latency ↑ | turnover 빨라 latency ↓ |
| 메모리/FD 소비 ↑ | 자원 효율 ↑ |
| 하류 자원 (DB) 부하 ↑ | 안정적 |

### 18-2. Connection 모델

| Per-connection-per-thread (전통) | Multiplexing (Lettuce, HTTP/2, NIO) |
|---|---|
| 단순, debugging 쉬움 | 복잡, debugging 어려움 |
| pool 필수 | pool 거의 불필요 |
| connection 비용 큼 | connection 비용 작음 |
| thread blocking | non-blocking |

### 18-3. Timeout 정책

| 긴 timeout | 짧은 timeout |
|---|---|
| 일시적 지연도 처리 가능 | 빠른 실패 |
| cascading 위험 ↑ | cascading 방어 |
| 사용자는 오래 기다림 | 즉시 에러 (사용자 친화 ↓) |

원칙: **외곽 큰 timeout, 안쪽 작은 timeout**.

### 18-4. Static pool size vs Dynamic

| Static (HikariCP min=max) | Dynamic (DBCP min<max) |
|---|---|
| 부팅 시 다 만듦, warmup 효과 | lazy create, 처음 spike에 약함 |
| 자원 소비 일정 | 평시 자원 절약 |
| 운영 예측 가능 | 비예측적 (자동 확장/축소) |

HikariCP 권장: **min=max**. 이유는 예측 가능성.

---

## 19. 꼬리질문 트리

### Q1. "HikariCP 의 maxLifetime 을 30분 (기본) 으로 둘 때 발생하는 가장 흔한 문제는?"

**예상 답**: AWS NAT Gateway나 firewall의 idle timeout (보통 5분)이 30분보다 짧아서 — firewall이 먼저 conn을 끊는다. HikariCP는 모름. 다음 query 보낼 때 RST 또는 timeout. 해결은 maxLifetime을 firewall idle 보다 짧게.

#### 꼬리 1-1: "firewall이 끊은 걸 어떻게 감지하나?"

→ TCP keepalive (커널 옵션) 또는 JDBC validation query (`HikariCP.connectionTestQuery`). 그러나 둘 다 비용이 있고 100% 막진 못함. 가장 확실한 건 maxLifetime을 firewall idle 보다 짧게.

#### 꼬리 1-2: "그러면 maxLifetime 을 30초로 둬도 되나?"

→ 안 됨. 매 30초마다 conn destroy + recreate → DB 인증 부하 폭증. 보통 firewall idle (5분)의 절반 정도가 적절 (2~3분).

#### 꼬리 1-3: "TCP keepalive를 1분으로 설정하면 firewall 함정 해결되나?"

→ 부분적. TCP keepalive packet은 일부 firewall이 카운트 안 함 (only data packet). 그래서 keepalive packet 보내도 firewall은 여전히 idle로 봄. 그래서 maxLifetime 줄이는 게 더 확실.

---

### Q2. "HikariCP의 maximumPoolSize를 100으로 설정했더니 DB CPU가 100% 되고 응답이 더 느려졌다. 왜?"

**예상 답**: DB 측 동시 query 수가 너무 많아져서 context switch 비용 폭발. PostgreSQL 같은 process-based DB는 특히 심함. Little's Law: 동시 처리 늘려도 처리 시간이 그만큼 늘면 throughput 그대로. HikariCP 권장 공식 `(core × 2) + spindle` 정도가 보통 적정.

#### 꼬리 2-1: "그러면 pool size를 어떻게 정해야 하나?"

→ 측정 기반. (1) 부하 테스트로 P99 latency vs throughput 곡선 그리기 → "knee point" 찾기. (2) HikariCP 메트릭으로 `pending` (대기) 가 거의 0 + `utilization` 70~80% 인 지점. (3) DB CPU 80% 넘기지 않는 선.

#### 꼬리 2-2: "여러 마이크로서비스가 같은 DB 쓰면 어떻게 나눠야 하나?"

→ DB max_connections 의 80% 를 (인스턴스 수 × 서비스 수) 로 나눈 게 한 서비스의 한 인스턴스 pool size 상한. 또는 PgBouncer 같은 multiplexer 도입.

#### 꼬리 2-3: "DB가 PgBouncer transaction mode 인데 Spring `@Transactional` 안에서 PreparedStatement 가 작동 안 한다. 왜?"

→ PgBouncer transaction mode는 transaction 끝나면 client conn을 다른 DB backend에 mapping. PreparedStatement는 특정 DB backend 의 plan cache 에 의존. 다음 트랜잭션에서 다른 backend에 가면 plan cache 없음. 해결: session mode 쓰거나, JDBC URL `prepareThreshold=0` 으로 simple query 강제.

---

### Q3. "Tomcat 503 폭증인데, jstack 보니 모든 thread가 HikariCP.getConnection 에서 park 중. 즉시 어떻게 해야 하나?"

**예상 답**:
1. 즉시: DB에서 long-running query 찾아 KILL (`pg_terminate_backend` 또는 MySQL `KILL`)
2. 단기: HikariCP maximumPoolSize 일시 증가 (응급) + 인스턴스 추가
3. 근본: connectionTimeout 짧게 (cascading 방어) + circuit breaker 도입

#### 꼬리 3-1: "long-running query를 KILL 했는데 또 발생한다. 다음 단계는?"

→ application 코드에서 statement timeout 설정 (`@Transactional(timeout=10)` 또는 JDBC URL `socketTimeout=10000`). 또는 `statement_timeout` (PostgreSQL) 를 DB session level에서 강제. 동시에 slow query log 분석으로 근본 원인 (인덱스 부족, N+1 등) 찾기.

#### 꼬리 3-2: "Circuit breaker를 도입하면 잘못된 요청이 즉시 fallback. 그러나 정상 요청도 fallback 되는 false positive 가 발생. 어떻게 튜닝?"

→ Resilience4j의 경우 `failureRateThreshold` (기본 50%), `minimumNumberOfCalls` (충분한 표본), `slidingWindowSize` 조정. 또한 `slowCallRateThreshold` 를 같이 써서 "느린 호출" 도 failure로 카운트. 운영에서는 metric으로 false positive rate 모니터링.

#### 꼬리 3-3: "Circuit open 상태에서 갑자기 DB 정상화. 어떻게 자동 회복?"

→ half-open 상태 — 일정 시간 후 일부 요청을 흘려보냄. 그게 성공하면 closed, 실패하면 다시 open. `permittedNumberOfCallsInHalfOpenState`, `waitDurationInOpenState` 옵션. 자동 회복.

---

### Q4. "한 마이크로서비스 그룹이 모두 같은 PostgreSQL 쓴다. 30개 인스턴스 × HikariCP 20 = 600 connection 요청. PostgreSQL max_connections=200. 어떻게 해결?"

**예상 답**:
1. **PgBouncer 도입** (transaction mode) — 600 client conn → 200 DB conn 으로 multiplexing
2. 또는 인스턴스별 pool size 줄이기 (200/30 = ~6) — pending 늘 위험
3. 또는 DB sharding / read replica 로 분산

#### 꼬리 4-1: "PgBouncer transaction mode를 쓰면 무엇이 깨지나?"

→ session-level state (PreparedStatement plan cache, temp table, SET 명령, advisory lock, LISTEN/NOTIFY) 가 다음 transaction에서 보장 안 됨. Spring + HikariCP 환경에선 보통 `prepareThreshold=0` 또는 PgBouncer 의 `server_reset_query`로 해결. 그러나 일부 lib (예: pgvector의 일부 기능) 는 호환 안 될 수 있음.

#### 꼬리 4-2: "PgBouncer 자체가 single point of failure 이지 않나?"

→ 맞음. 해결: (1) PgBouncer 를 여러 개 띄우고 HAProxy 같은 LB로 분산, (2) AWS RDS Proxy 같은 managed service, (3) application-side에서 retry. 그러나 PgBouncer 자체는 매우 가벼워서 (수십 MB RAM, async) 잘 안 죽음.

#### 꼬리 4-3: "AWS RDS Proxy 와 직접 PgBouncer 의 차이는?"

→ RDS Proxy: managed (자동 HA, 자동 scaling, IAM auth, secrets manager 통합), 단점은 transaction mode 만, latency 추가 (~5ms). PgBouncer: 자체 운영 (HA 직접), session/transaction/statement mode 모두, latency 거의 0. 자체 운영 가능하면 PgBouncer, 안 되면 RDS Proxy.

---

## 20. 참조 — 다른 챕터와의 연결

| 외부 챕터 | 연결점 |
|---|---|
| `04-load-balancer-deep-dive.md` | LB connection table, health check (cascade의 출발점) |
| `05-nginx-internals.md` | Nginx worker_connections, upstream keepalive 풀버전 |
| `06-tomcat-internals.md` | acceptCount/maxConnections/maxThreads 의 NIO Connector 내부 |
| `08-db-connection-and-jdbc.md` | JDBC 드라이버, wire protocol, prepared statement |
| `jvm/05-threading/` | Tomcat thread, HikariCP의 thread synchronization |
| `jvm/02-runtime-data-areas/05-direct-memory.md` | Netty의 zero-copy, off-heap |
| `jvm/04-gc/` | DB ResultSet의 Heap 압박, GC 영향 |

---

## 21. 마무리 — 백지에서 풀 수 있는가

### 자가 점검 질문 (10개 — 모두 답할 수 있어야 마스터)

1. 한 요청이 거치는 13개 풀을 순서대로 백지에 그리기
2. 각 풀이 비었을 때 어떤 에러가 어디서 나타나나
3. Tomcat acceptCount, maxConnections, maxThreads의 차이를 한 줄씩
4. HikariCP의 ConcurrentBag 자료구조 설명 (sharedList, threadList, handoffQueue)
5. HikariCP maxLifetime을 firewall idle 보다 짧게 두는 이유
6. Little's Law로 HikariCP pool size 계산하기
7. Cascading failure 시나리오 한 사이클 (DB slow → ... → 폭주)
8. Cascading 방어 4가지 (timeout, circuit breaker, bulkhead, layered timeout)
9. Lettuce가 Jedis보다 효율적인 이유 (multiplexing)
10. PgBouncer transaction mode의 트레이드오프 (PreparedStatement 깨짐)

### 한 줄로 마무리

> **"풀은 비싼 자원을 미리 만들어 빌려주는 자료구조다. 한 요청은 7~13개의 풀을 통과하고, 어느 한 풀이 비면 위쪽이 적체된다. 마스터의 핵심은 각 풀의 위치와 한도를 알고, cascading 을 막는 timeout/circuit breaker/bulkhead 를 설계하고, Little's Law 와 측정 기반으로 적정 크기를 정하는 것."**

이걸 백지에 그리고 줄줄 풀 수 있으면 — **production에서 풀 관련 사고를 진단·해결할 수 있는 시니어**.
