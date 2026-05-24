# 05. Nginx Internals — 8 worker로 수만 동시 연결을 처리하는 비결

> "Nginx는 master/worker 프로세스 모델에서 각 worker가 자기 epoll 인스턴스를 들고 non-blocking I/O 기반 event loop를 돌리며, SO_REUSEPORT로 thundering herd를 커널에 위임하고, upstream keepalive pool로 backend TCP/TLS handshake를 절감하며, ngx_pool_t로 per-request 메모리를 통째 free한다."

---

## 0. 한 줄 목차 — 면접에서 풀어낼 흐름

`C10K → master/worker → event loop(epoll) → SO_REUSEPORT → HTTP 11-phase → upstream keepalive pool → 운영 장애(worker_connections/502/CPU)`

이 순서로 답하면 된다. 가지마다 키워드 3개를 들고 인접 가지로 확장.

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| C10K | thread-per-conn 불가능 | stack 8MB × 10K = 80GB | event-driven 해결 |
| Process | master = 관리 | worker = 요청 (1 per core) | reload = graceful drain |
| Event Loop | epoll_wait → handle → 재등록 | level vs edge triggered | SO_REUSEPORT 커널 분산 |
| Reverse Proxy | 11 phase 처리 | proxy_pass + upstream | buffering on/off |
| Upstream Pool | TCP/TLS handshake 절감 | keepalive 32 | HTTP/1.1 + Connection "" |
| 운영 장애 | worker_connections + ulimit | 502 keepalive race | $upstream_response_time |

---

## 1. C10K 문제 — Nginx가 태어난 이유

1999년 Dan Kegel의 "C10K problem": 한 서버가 1만 동시 연결을 처리할 수 있는가? 그때까지 답은 불가능.

```
[Apache prefork — 1 conn = 1 process]
  요청 10000개 → 자식 process 10000개
  stack 8MB × 10000 = 80GB    ← 1999년 RAM의 100배
  context switch us × 10000   ← CPU 절반 이상 switch에 낭비
  blocking I/O                ← read() 한 번에 한 thread 멈춤

[Nginx event-driven — 1 worker = N conn]
  worker 8개 (CPU 8 core) × epoll로 각 8000 fd 감시 → 6.4만 동시
  메모리 = 8MB × 8 worker + conn 별 작은 buffer ≈ 수백 MB
  context switch ≈ 0 (worker가 자기 fd만)
```

Apache가 늦은 이유: 모듈 ABI가 blocking 모델에 묶임, mod_php가 prefork만 지원(PHP not thread-safe), 1995년 레거시. **레거시는 새 패러다임을 따라가지 못한다** — 이게 Nginx 시대로 넘어간 진짜 이유.

---

## 2. Process 모델 — master/worker

```
            [systemd / init]
                  │
                  ▼
   ┌──────────────────────────────┐
   │   master process (root, 1개)  │
   │   - nginx.conf 로드/검증       │
   │   - listening socket 생성      │
   │   - worker 관리 / signal       │
   └────┬─────┬─────┬────┬─────────┘
        │ fork() + setuid(nginx)
        ▼     ▼     ▼    ▼
    [worker1][worker2]..[workerN]   (N = CPU core)
      epoll    epoll     epoll
      event    event     event
      loop     loop      loop
        │       │         │
        └───────┴─────────┘
              │
        공유 listening fd
       (master가 fork로 상속)

   [선택적 보조]
     cache manager  ← proxy_cache 만료 정리
     cache loader   ← 시작 시 디스크 캐시 인덱싱
```

**master**는 요청 처리를 하지 않는다. nginx.conf 로드, listening socket(`socket→bind→listen`) 생성, worker fork/관리, SIGHUP/SIGUSR2 처리. root로 떠서 80/443 bind, worker는 setuid로 권한 떨어뜨림.

**worker**는 CPU core 당 1개 권장(`worker_processes auto;`, 명시 추천 `worker_cpu_affinity auto;`로 pinning), 각자 epoll 인스턴스를 들고 독립 event loop를 돈다. listening fd만 master에서 fork로 상속. 한 worker가 죽어도 나머지는 무사.

```nginx
user nginx;
worker_processes auto;        # = CPU core
worker_rlimit_nofile 65535;   # 각 worker의 FD 한계
events {
    worker_connections 8192;  # 한 worker 동시 conn 상한
    # 실제 = min(worker_connections, ulimit -n)
}
```

**왜 multi-process(thread 아님)?** ① 격리(worker 하나 segfault나도 master가 다시 fork; thread면 프로세스 전체 사망), ② GIL/lock 없음(공유 메모리 없으니 동기화 비용 0), ③ CPU affinity 쉬움(OS scheduler가 process를 묶기 쉬움), ④ NUMA-friendly(worker를 NUMA node에 묶으면 memory locality 좋음). 단점은 상태 공유가 어려워 캐시·rate-limit 카운터 같은 건 `ngx_shm_t` shared memory 설계가 별도 필요.

보조 프로세스: **cache loader**(시작 시 1번, proxy_cache 디스크 스캔→메모리 인덱스), **cache manager**(주기 실행, 만료/LRU 정리).

---

## 3. Event Loop — 심장부

### 3.1 의사코드 (`ngx_process_events_and_timers()` 요지)

```c
// worker 시작 → 이 루프를 영원히 돈다
for (;;) {
    // 1) 다음 timer까지 남은 시간 계산 (없으면 500ms로 cap)
    timer = ngx_event_find_timer();

    // 2) (옛 방식) accept_mutex 시도 — SO_REUSEPORT면 skip
    if (ngx_use_accept_mutex) ngx_trylock_accept_mutex(cycle);

    // 3) epoll_wait — 커널에 "ready된 fd 있을 때까지 자라"
    n = epoll_wait(ep, events, N, timer);

    // 4) 받은 이벤트 dispatch
    for (i = 0; i < n; i++) {
        c = events[i].data.ptr;             // ngx_connection_t *
        if (events[i].events & (EPOLLERR|EPOLLHUP)) { /* 끊김 */ }
        if (events[i].events & EPOLLIN)  c->read->handler(c->read);
        if (events[i].events & EPOLLOUT) c->write->handler(c->write);
    }

    // 5) accept_mutex 해제 / 6) 시간·timer 갱신 / 7) post된 이벤트
    if (ngx_accept_mutex_held) ngx_shmtx_unlock(&ngx_accept_mutex);
    ngx_time_update();
    ngx_event_expire_timers();              // keepalive/proxy_read_timeout
    ngx_event_process_posted(&ngx_posted_events);
}
```

핵심: 각 connection이 read/write handler를 들고 있는 **state machine**. EAGAIN 만나면 다음 ready 이벤트로 점프 → 한 worker가 수천 conn 동시 진행. 모든 timeout(keepalive_timeout, send_timeout, proxy_read_timeout 등)이 timer로 관리되어 `epoll_wait`의 timeout 인자로 들어간다 — "자고 있다가 일감 생기면 깨어 일하는" 모델.

### 3.2 epoll = O(1), select/poll = O(N)

select/poll은 매 호출마다 감시 fd 전체를 커널에 복사 + linear scan(ready 1개여도 N개 검사). epoll은 `epoll_create1()`으로 인스턴스 만들고, `epoll_ctl(ADD/MOD/DEL)`로 한 번 등록(커널 red-black tree) → fd ready 시 커널이 ready list에 callback push → `epoll_wait()`은 ready 만큼만 복사 반환. **1만 fd 감시 시 select=매번 1만 검사, epoll=ready 100만 처리. 2배가 아니라 100배 차이.**

**Level vs Edge triggered**: LT는 ready 상태인 한 매번 알림(안전, 일부만 읽어도 다음 loop에 또), ET는 상태 "전환" 시점에만 1번(빠르지만 EAGAIN 날 때까지 모두 읽어야). Nginx는 **ET 사용** → read 패턴은:

```c
while (1) {
    n = read(fd, buf, size);
    if (n > 0) { /* 처리 */ continue; }
    if (n == -1 && errno == EAGAIN) break;   // 더 읽을 거 없음
    if (n == 0)                     break;   // 연결 종료
}
```

socket은 반드시 `O_NONBLOCK`(fcntl) — read가 데이터 없으면 EAGAIN 즉시 반환(블록 X). write 시도 → EAGAIN → epoll에 EPOLLOUT 등록 → ready 시 재시도 패턴이 곧 **state machine**.

OS별 추상화: Linux=epoll, FreeBSD/macOS=kqueue, Solaris=event ports, Windows=IOCP, fallback=select. `ngx_event_module_t` 인터페이스로 event loop 본체는 OS를 모름.

### 3.3 connection 객체 풀

`ngx_connection_t`는 worker 시작 시 `worker_connections` 만큼 **사전 할당**되어 free list에 들어 있다. 새 연결 = free list에서 꺼냄, 종료 = 반납. malloc/free 비용 0.

```c
struct ngx_connection_s {
    void          *data;       // HTTP는 ngx_http_request_t
    ngx_event_t   *read;       // 읽기 이벤트 (handler, timer, flags)
    ngx_event_t   *write;      // 쓰기 이벤트
    ngx_socket_t   fd;
    ngx_recv_pt    recv;       // TCP/SSL에 따라 다른 함수 포인터
    ngx_send_pt    send;
    ngx_pool_t    *pool;       // 이 conn 전용 memory pool
    ngx_buf_t     *buffer;
    ngx_queue_t    queue;      // free/reusable 리스트 링크
};
```

state machine의 "지속 상태"가 여기 들어 있어, event loop 어느 시점에 dump 떠도 conn이 어느 단계인지 명확하다.

---

## 4. Thundering Herd & Accept

N개 worker가 같은 listening fd를 epoll에 걸어두면 새 SYN에 모두 깨고 1개만 accept 성공, 나머지는 EAGAIN — **천둥에 놀란 가축 떼**. 옛 해결책 `accept_mutex`는 mutex 잡은 worker만 listening fd를 epoll에 등록(공정성·latency 저하). 현대는 **SO_REUSEPORT**(Linux 3.9+, `listen 80 reuseport`): worker별 독립 listening socket을 같은 포트에 bind, 커널이 4-tuple 해시로 분산 → 깨어나는 worker 1개. Nginx 1.9.1+ 표준이라 accept_mutex는 의미 없어졌다.

```
[Before — accept_mutex]                [SO_REUSEPORT]
  listening fd (1개, 공유)              lsn1 lsn2 lsn3 lsn4 lsn5
   │                                     ▼    ▼    ▼    ▼    ▼
   ├─→ w1 w2 w3 w4 w5 (모두 깸)          w1   w2   w3   w4   w5
                                        (커널이 직접 분산)
```

accept 이전에 커널에 두 큐가 있다: SYN_RECV queue(`net.ipv4.tcp_max_syn_backlog`, 3-way 진행 중)와 accept queue(`min(somaxconn, listen backlog)`, ESTABLISHED 후 user accept 대기). **운영 함정**: `worker_connections 65535`로 키워봤자 `somaxconn=128`이면 SYN burst 시 drop. `somaxconn`, `tcp_max_syn_backlog`, `worker_rlimit_nofile`, `ulimit -n`, `listen ... backlog=N`을 같이 봐야 한다.

---

## 5. HTTP 11-Phase — 간소 표

```
TCP accept → conn_t → epoll → 헤더 수신(EPOLLIN)
           ↓
  POST_READ → SERVER_REWRITE → FIND_CONFIG → REWRITE → POST_REWRITE
  → PREACCESS → ACCESS → POST_ACCESS → PRECONTENT → CONTENT ⭐ → LOG
           ↓
  응답 전송(EPOLLOUT) → keepalive면 헤더 대기, 아니면 close
```

| Phase | 주 module | 역할 |
|---|---|---|
| POST_READ | realip | 헤더 직후, 실제 client IP 복원 |
| SERVER_REWRITE | rewrite | server 레벨 rewrite |
| FIND_CONFIG | core | location 매칭 |
| REWRITE / POST_REWRITE | rewrite | location 안 rewrite, 무한 방지 |
| PREACCESS | limit_req, limit_conn | rate / conn limit |
| ACCESS / POST_ACCESS | access, auth_basic | allow/deny, auth, satisfy |
| PRECONTENT | try_files, mirror | content 전 분기 |
| **CONTENT** | static, proxy, fastcgi | **응답 생성** |
| LOG | log | access_log 기록 |

각 phase에 module이 handler를 등록 → 요청이 phase를 따라 흐르며 handler 호출. 모든 phase가 non-blocking이라 한 worker가 동시에 수천 요청을 **각기 다른 phase**에 들고 있다 — 요청 #1은 ACCESS에서 auth 서버 응답 대기, #2는 CONTENT에서 upstream 응답 대기, #3은 헤더 수신 중, #4는 sendfile 진행. EAGAIN 만나면 즉시 다음 ready 이벤트로 점프. **이게 event-driven의 진수.**

location 매칭 순서: ① `=` exact → ② `^~` prefix(regex 무시) → ③ 가장 긴 일반 prefix(저장) → ④ regex 위→아래 첫 매칭 → ⑤ 매칭 regex 없으면 ③ 사용. regex 많으면 매 요청 N개 시도 → CPU 폭증, `pcre_jit on;` + regex 수 통제 필수.

---

## 6. Upstream Keepalive Pool — 운영의 핵심

```
Client                Nginx                       Backend
  │  HTTP req ────►   │ POST_READ ~ ACCESS         │
  │                   │ CONTENT: proxy_pass        │
  │                   │ upstream 선택              │
  │                   │ ┌─ keepalive pool ───┐     │
  │                   │ │ idle conn1 (TLS done)│   │
  │                   │ │ idle conn2          │   │
  │                   │ │ idle conn3 ... 32   │   │
  │                   │ └─ 꺼냄 / 반납 ──────┘     │
  │                   │ 풀 비면 새 TCP connect ───►│
  │                   │ ◄──── HTTP response ─────  │
  │ ◄── HTTP resp ──  │ 풀에 반납 (32 초과면 close) │

[Keepalive 없음] req마다 TCP 3 RTT + TLS 2 RTT = 5ms 오버헤드, TIME_WAIT 폭발
[Keepalive 있음] handshake 0 RTT, port 재사용
```

```nginx
upstream backend {
    server b1:8080 weight=3;
    server b2:8080;
    server b3:8080 backup;            # 다른 게 다 죽으면

    keepalive 32;                     # ⭐ worker 당 풀 크기
    keepalive_requests 1000;          # 한 conn 재사용 횟수
    keepalive_timeout 60s;            # idle 후 close (Backend timeout보다 짧게!)
}
location /api/ {
    proxy_pass http://backend;
    proxy_http_version 1.1;           # ⭐ 안 적으면 HTTP/1.0 → 매번 close
    proxy_set_header Connection "";   # ⭐ client의 Connection: close 차단

    proxy_buffering         on;
    proxy_buffer_size       4k;
    proxy_buffers           8 4k;
    proxy_busy_buffers_size 8k;

    proxy_connect_timeout 5s;
    proxy_send_timeout    60s;
    proxy_read_timeout    60s;

    proxy_next_upstream   error timeout http_502 http_503;
}
```

### Keepalive 없음 vs 있음

```
[Keepalive 없음 — 매 요청 TCP+TLS handshake]
  req1: TCP(3 RTT) + TLS(2 RTT) + 처리
  req2: TCP + TLS + 처리       (반복)
  → RTT 1ms 환경에서 5ms/요청 오버헤드
  → 1000 RPS = 5초 worth of handshake/sec
  → TIME_WAIT 누적 → ephemeral port 고갈

[Keepalive 풀 있음]
  worker별 풀: [idle conn1, idle conn2, ...] (모두 TCP/TLS done)
  req1 → 풀에서 conn1 꺼냄 → 처리 → 풀 반납
  req2 → 풀에서 conn2 꺼냄 → ...
  → handshake 0 RTT, port 재사용 → TIME_WAIT 없음
```

### 502 keepalive race — 가장 흔한 함정

```
t=0    Nginx 풀: conn A (idle 30s)
t=31   Backend keepalive_timeout 30s → backend가 conn A를 FIN
t=31.5 Nginx가 conn A 꺼내 요청 전송
t=31.6 backend → RST (이미 닫힌 conn)
t=31.7 Nginx → 502 Bad Gateway

해결:
  Nginx keepalive_timeout < Backend idle timeout (예: 50s vs 75s)
  + proxy_next_upstream error timeout http_502;
  + proxy_next_upstream_tries 2;
```

`proxy_http_version 1.1` + `Connection ""` 두 줄을 안 쓰면 Nginx upstream default가 HTTP/1.0이라 backend 입장에서 매 요청마다 close → 풀 만들어도 즉시 닫혀 의미 없음. **운영 단골 함정**.

`keepalive_requests 1000`은 한 conn 재사용 횟수 한계(메모리 누수 방어 + sticky 재분산 기회). 풀 사이즈는 "P99 동시 backend 요청 수" 기준 — 32인데 동시 200이면 32만 재사용, 168은 매번 새 connect. backend 선택은 round-robin(default) · least_conn · ip_hash · hash $key consistent. **consistent**는 backend 추가/제거 시 cache 재분배 최소화.

---

## 7. 정적 파일 · TLS · 캐시 · 메모리 (통합)

**정적 파일 zero-copy**: `sendfile on` + `tcp_nopush on`은 file→socket을 kernel space에서 직접 처리(전통적 read→write는 user copy 2번 + context switch 2번). `aio threads`는 disk 미스가 worker 전체를 막지 않게 별도 thread pool로 위임(1.7.11+). `open_file_cache max=10000 inactive=60s;`로 fd/metadata syscall 절감.

**압축**: `gzip on; gzip_types text/css application/json; gzip_comp_level 5;` — 9는 CPU 폭증, 5~6이 sweet spot. `gzip_min_length 1000;`로 작은 응답은 오버헤드 회피.

**proxy_buffering**: on(default)은 backend 응답 통째 buffer 후 slow client에 맞춰 전송(slow client가 backend worker를 묶지 않음). off는 backend→Nginx→client 직통 streaming(SSE, WebSocket, 큰 다운로드, gRPC 필수). WebSocket은 `proxy_http_version 1.1` + Upgrade/Connection 헤더로 buffering 자동 off.

**proxy_cache**: `proxy_cache_lock on`은 cache miss 동시 100건 떠도 backend엔 1건만(thundering herd 방지). **microcaching**(`proxy_cache_valid 200 1s;`)만으로도 read-heavy origin RPS 폭주 흡수 — origin 보호 황금기법. `proxy_cache_background_update on; proxy_cache_use_stale updating;`는 stale 응답 + 비동기 갱신으로 P99 안정화. `add_header X-Cache-Status $upstream_cache_status;`로 HIT/MISS 가시화.

**TLS**: `ssl_session_cache shared:SSL:50m` + `ssl_session_tickets on`으로 session resumption(같은 client 재방문 시 abbreviated handshake, 1 RTT 절감). `ssl_stapling on; ssl_stapling_verify on;`는 OCSP revocation 검증을 Nginx가 미리 받아 응답에 동봉 → client가 OCSP 서버 안 가도 됨. TLS 1.3은 1 RTT handshake. HTTP/2는 `listen 443 ssl http2 reuseport;` — ALPN 협상, multiplexing(1 TCP에 N stream), HPACK 헤더 압축.

**메모리 — ngx_pool_t** (Nginx 설계의 숨은 보석): 요청 시작 시 `ngx_create_pool(4096, log)` → 처리 중 `ngx_palloc(pool, size)`만, 절대 개별 free 안 함 → 요청 끝나면 `ngx_destroy_pool()`로 **통째 회수**. fragmentation 없음, leak 거의 불가능, per-request locality(cache friendly). 단점: WebSocket/SSE 같은 long-conn은 pool이 오래 살아 RSS 증가. **worker RSS = sum(active conn pool 크기)** — `htop` per-worker 모니터링 필수.

---

## 8. 운영 시나리오

### S1. "worker_connections 늘렸는데 동접 효과 없음"

```
증상: worker_connections 65535로 올려도 active conn 1024 이상 안 감
원인: ulimit -n(default 1024) / somaxconn(128~4096) / tcp_max_syn_backlog / worker_rlimit_nofile 미설정

진단:
  cat /proc/$(pgrep nginx | head -1)/limits | grep "open files"
  sysctl net.core.somaxconn
  ss -ltn | grep :443    # Send-Q가 현재 accept queue, 한도가 backlog

해결: systemd unit LimitNOFILE=200000
      sysctl net.core.somaxconn=65535 / tcp_max_syn_backlog=65535
      nginx.conf: worker_rlimit_nofile 200000;
                  events { worker_connections 65535; }
                  listen 443 ssl http2 backlog=65535 reuseport;
```

### S2. "502 Bad Gateway 간헐적 1%"

```
증상: 504 아니라 502가 무작위
진단: tail -f error.log | grep upstream
      → "upstream prematurely closed connection while reading response header"
      → 거의 항상 keepalive race
      awk '$status==502 {print $upstream_addr}' access.log | sort | uniq -c

해결: Nginx keepalive_timeout < Backend idle timeout (안전 마진)
      proxy_next_upstream error timeout http_502;
      proxy_next_upstream_tries 2;
```

### S3. "high CPU — 한 worker가 100%, 나머지 한가"

```
원인 후보:
  ① load balancer가 한 worker로만 분산 → SO_REUSEPORT 미설정
  ② accept_mutex 없는데 한 worker가 다 받음
  ③ PCRE catastrophic backtracking (location ~ <복잡regex>)
  ④ PCRE JIT 비활성
  ⑤ SSL handshake 폭주 (keepalive 미설정으로 매번 full handshake)

진단:
  top -H -p $(pgrep nginx)     # worker별 CPU (-H로 thread/process 단위)
  strace -p <wpid> -c           # syscall 빈도: SSL_* 많으면 handshake,
                                #               read/epoll 많으면 정상
  perf top -p <wpid>            # function 단위 hot spot
                                # ngx_pcre_exec 많으면 regex 폭증

해결:
  listen 443 ssl http2 reuseport;   # 커널 분산
  pcre_jit on;                       # JIT 컴파일
  upstream keepalive 설정             # handshake 감소
  regex 단순화 + location 정렬
```

---

## 9. 진단 도구 한 표

| 명령/파일 | 무엇을 본다 |
|---|---|
| `nginx -V` | 컴파일 옵션, 빌드된 모듈, HTTP/2 여부 |
| `nginx -t` / `nginx -s reload` | 설정 syntax 검증 / graceful reload |
| `curl /nginx_status` (stub_status) | Active(현재 conn) / Reading(헤더 수신 중) / Writing(응답/upstream 송신) / Waiting(keepalive idle) |
| `access_log` 변수 | `$request_time`(총 latency), `$upstream_connect_time`(keepalive miss>0.001), `$upstream_header_time`(backend 처리 근사), `$upstream_response_time`(헤더+본문), `$upstream_addr`(실제 backend), `$upstream_cache_status`(HIT/MISS/STALE/UPDATING) |
| `error.log` 시그니처 | "upstream prematurely closed"=keepalive race, "upstream timed out"=backend hang, "Too many open files (24)"=FD limit, "worker_connections are not enough"=풀 부족, "SSL_do_handshake() failed"=TLS 문제 |
| `top -H -p $(pgrep nginx)` / `ls /proc/<wpid>/fd \| wc -l` / `strace -p <wpid> -c` / `perf top -p <wpid>` | worker별 CPU/MEM, 사용 중 FD, syscall 통계, function hot spot |

진단 공식:
```
$request_time - $upstream_response_time ≈ client↔Nginx (slow client?)
$upstream_response_time - $upstream_header_time ≈ backend 응답 본문 전송
$upstream_connect_time > 0.001         ≈ keepalive 풀 miss → 새 connect
awk '$status==502 {print $upstream_addr}' access.log | sort | uniq -c
awk '{print $status}' access.log | sort | uniq -c
```

stub_status 설정:
```nginx
location /nginx_status { stub_status; allow 127.0.0.1; deny all; }
```

---

## 10. Apache prefork vs Nginx (한 표)

| 측면 | Apache prefork | Nginx |
|---|---|---|
| 동시성 모델 | process/conn | event/worker (1:N) |
| 동시 연결 한도 | 수백 | 수만~수십만 |
| 메모리/conn | 8MB+ stack | 수 KB (event state) |
| Blocking I/O 영향 | 그 process만 | **worker 전체** ⚠ → `aio threads`로 완화 |
| 모듈 격리 | 강함 (process) | 약함 (worker crash = master refork) |
| `mod_php` | ✅ | ❌ (별도 php-fpm) |
| 코드 모델 | 동기 | 비동기 콜백 (state machine) |
| Reverse proxy | mod_proxy | **first-class** |
| Reload | graceful | graceful + USR2 hot upgrade |

Nginx의 약점(정직하게): ① blocking 작업(disk, sync DNS, sync Lua, regex backtracking)이 worker 전체를 막는다 — `aio threads`로 부분 완화. ② C 모듈은 비동기 콜백이라 진입장벽 높음 → OpenResty(Lua)/njs(JS) 스크립팅으로 우회. ③ 모듈 격리 약함 — third-party 모듈 버그가 worker crash시키면 그 사이 일부 요청 손실. ④ 동적 reconfig 약함 — upstream 변경에 reload 필요.

Apache가 맞는 자리: 레거시 mod_php 의존, .htaccess 필수, 모듈 격리 critical. 그러나 현대 표준은 **Nginx + php-fpm** 또는 **Nginx + 백엔드 앱서버**.

Nginx vs Envoy: edge/CDN origin·단순 reverse proxy=Nginx, service mesh internal·xDS 동적 reconfig·HTTP/3 first-class=Envoy. Kubernetes ingress는 ingress-nginx가 여전히 점유율 1위(OSS/Plus/OpenResty/Tengine/Angie 등 변종은 라이선스·동적 logic·국가별 사정으로 갈라짐).

---

## 11. 꼬리질문

**Q1. "1 worker로 10000 conn이 왜 가능? blocking으로 worker가 막히는 케이스는?"**
non-blocking + epoll로 ready된 fd만 다루고, 각 conn 메모리 ≈ 수 KB. backend 응답 대기도 backend fd를 worker의 epoll에 등록 → 다른 conn 동시 처리. blocking으로 worker 전체가 멈추는 경우는 ① disk I/O(sendfile/file read) — `aio threads`로 thread pool 위임 가능, ② sync DNS(builtin resolver는 async지만 third-party 모듈이 getaddrinfo 직접 쓰면 blocking), ③ OpenResty의 sync Lua I/O, ④ regex catastrophic backtracking(nested quantifier `(a+)+$` 같은 패턴 + 긴 입력 → 지수 시간; PCRE JIT 켜도 일부 패턴은 폭발).

**Q2. "keepalive 32인데 동시 200이면? 그냥 200으로 올리면 되나?"**
32만 재사용, 168은 매번 새 TCP connect → 풀 진입 못 함(끝나면 close). 답은 종합: (a) 풀 늘리기 — 단 **worker당** 풀이라 N worker × 200 = total backend conn, backend max conn 한계 확인 필요, 너무 크면 idle conn이 backend 메모리 차지. (b) 캐시 가능 응답이면 **microcaching + cache_lock**으로 backend 부하 자체를 줄임. (c) backend가 burst를 못 받으면 Nginx `limit_req`로 흘려보내기 조절. (d) spike가 단일 path면 `proxy_cache_background_update`로 stale + 비동기 갱신.

**Q3. "reload 후 502가 보이는 이유? zero-downtime이라며?"**
시나리오 3: ① 옛 worker가 graceful 종료하면서 upstream keepalive 풀의 idle conn도 close → 그 사이 새 요청이 그 conn 쓰면 RST → 502. ② `worker_shutdown_timeout` 초과 시 진행 중 요청 강제 종료. ③ WebSocket/SSE long-conn은 거의 항상 끊김. 진정한 zero-downtime은 `nginx -s USR2`(새 master + 새 worker가 추가로 뜸, listening fd는 옛 master가 fork로 전달) → 옛 master에 WINCH(옛 worker만 graceful) → QUIT(옛 master 종료). 다만 long-conn은 여전히 문제 → **client reconnect 로직**으로 푸는 게 정답.

**Q4. "epoll_wait가 100 fd 반환 — 처리 중 새 SYN은? handler가 오래 걸리면?"**
커널 accept queue에 쌓이고 다음 epoll_wait에서 listening fd가 ready로 반환. 사이클 1개 latency 추가. Nginx는 **post 메커니즘**으로 무거운 작업은 `ngx_post_event(&ngx_posted_events)`로 큐에 넣고 loop 끝에서 처리, accept event는 별도 우선순위 큐(`ngx_posted_accept_events`) — **accept 먼저** 패턴. 그래도 한 handler가 오래 걸릴 위험은? Nginx 코드는 **state machine**으로 작성 — 헤더 파싱도 한 번에 다 안 하고 "버퍼만큼만 → state 저장 → return → 다음 read에서 이어서". 즉 진짜 오래 걸리는 handler가 없음. 사고는 third-party/Lua에서 발생.

**Q5. "worker_connections를 무조건 키우면 되나?"**
안 됨. ① `ulimit -n`·`worker_rlimit_nofile`이 안 따라가면 fd 못 열어 의미 없음. ② `somaxconn`이 작으면 SYN burst 시 accept queue drop. ③ `tcp_max_syn_backlog`가 작으면 3-way 단계 drop. ④ 메모리는 ngx_connection_t 사전할당 + ngx_pool_t × 동시 active로 늘어남 → container memory limit과 충돌. ⑤ backend가 받을 수 있는지 확인 필요. **kernel limit + Nginx limit + container limit + backend limit 넷을 같이 본다.** systemd unit `LimitNOFILE=200000`, sysctl `net.core.somaxconn=65535`, nginx `worker_rlimit_nofile 200000; listen ... backlog=65535 reuseport;` 한 세트.

---

---

## 12. 한 장 종합 — Nginx의 정수

```
[사용자 요청]
    │
    ▼
[Kernel TCP stack]
    SYN queue → accept queue → SO_REUSEPORT 분산
    │
    ▼
[Nginx master] nginx.conf · worker fork · reload(HUP) · hot upgrade(USR2)
    │ fork + setuid
    ▼
[worker1] [worker2] ... [workerN]      [cache manager / loader]
  epoll loop (ET, non-blocking)
  11-phase HTTP
  ngx_pool_t (per-request)
  upstream keepalive pool (per-worker)
  open_file_cache
    │
    ▼  sendfile / proxy_pass
[static files]  [upstream backend 1..N]
                 keepalive 32 + HTTP/1.1 + Connection ""

[3개 사실만 외우면 됨]
  ① master는 관리, worker가 일한다 (CPU core 당 1개)
  ② worker = epoll + non-blocking + state machine (수천 conn 동시)
  ③ upstream keepalive 풀이 backend handshake 비용을 거의 0으로 만든다
```

---

## 마치며 — 시니어가 Nginx를 다룬다는 것

1. **메커니즘이 단순하다** — master/worker + epoll + non-blocking + pool. 외울 게 5개.
2. **state machine 기반** — 어떤 시점에도 dump 뜨면 conn 상태가 명확.
3. **메모리 모델이 보수적** — ngx_pool_t로 leak 거의 불가능.
4. **운영 신호가 풍부** — access_log, error_log, stub_status, $upstream_* 변수.

시니어가 Nginx를 다룬다는 건:
- worker_connections 늘려도 안 늘어나면 ulimit + somaxconn + worker_rlimit_nofile + backlog를 같이 본다.
- 간헐 502는 keepalive race를 의심한다(Nginx vs Backend timeout 차이 + Connection "" 누락).
- CPU 폭증 시 hot worker를 strace/perf로 까보고 SO_REUSEPORT/pcre_jit/keepalive 누락을 본다.
- reload는 zero-downtime이 아니다 — long-conn 끊김, USR2 한계를 안다.
- Envoy/Nginx Plus/OpenResty 중 무엇을 언제 쓸지 판단 근거가 있다.

이게 백지에서 그릴 수 있고 운영 사고를 분석할 수 있는 "Nginx 마스터 수준"이다.

---

---

## 부록 — 다른 챕터로의 연결

- **02-dns-and-routing** — 요청이 Nginx에 도달하기 전 단계(DNS, BGP, anycast).
- **03-osi-7-layers-and-tcp-tls** — Nginx의 listen socket이 받는 TCP/TLS 흐름.
- **04-load-balancer-deep-dive** — Nginx 자체도 L7 LB. L4 LB와의 협력(LB ─ Nginx ─ backend).
- **06-tomcat-internals** — Nginx가 proxy_pass로 보내는 backend 측 Tomcat의 Acceptor→Poller→Executor.
- **07-connection-pools-master** — Nginx upstream keepalive + Tomcat thread pool + HikariCP + kernel backlog 종합.

---

11-phase 각 module hook, OpenResty Lua 통합, 정적 파일 zero-copy 풀버전은 git 7e4a6c8 참조.
