# 05. Nginx Internals — 8 worker로 수만 동시 연결을 처리하는 비결

> "Nginx는 빠른 웹서버다" 라고 답하면 입문자.
> "Nginx는 master/worker 프로세스 모델에서 각 worker가 자기 epoll 인스턴스를 들고 non-blocking I/O 기반 event loop를 돌리며, accept_mutex 시대를 지나 SO_REUSEPORT로 thundering herd를 커널에 위임했고, upstream keepalive pool로 backend TCP/TLS handshake를 절감하며, ngx_pool_t 기반 per-request memory pool로 RSS를 통제한다" 라고 말할 수 있다면 그 다음 단계.
> 이 챕터의 목표는 후자다.

---

## 이 문서의 사용법

1. **0장 마인드맵을 먼저 외운다** — 면접에서 종이에 그릴 그림.
2. **1~7장 순서대로 학습**.
3. **8장 운영 시나리오** + **9장 꼬리질문**으로 자가 검증.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"Nginx는 master/worker 프로세스 모델 + worker별 epoll event loop + non-blocking I/O + upstream keepalive pool로 C10K를 풀었다. accept_mutex → SO_REUSEPORT로 thundering herd를 해결하고, ngx_pool_t로 메모리를 통째 free한다."**

### 6개 가지 — 순서를 외운다

```
              [ROOT: C10K 해결자 — event-driven + non-blocking]
                                  │
       ┌──────────┬──────────────┼──────────────┬──────────┬──────────┐
       │          │              │              │          │          │
      ① C10K     ② Process       ③ Event       ④ Reverse  ⑤ Upstream ⑥ 운영
      문제      master/worker     Loop          Proxy      Keepalive   장애
       │          │              │              │          │          │
   ┌───┼───┐  ┌──┼──┐         ┌──┼──┐       ┌──┼──┐    ┌──┼──┐    ┌──┼──┐
  thread  사망   master worker  epoll NB I/O  11 phase  pool  TCP   502   high
  스택 8MB  cs   reload SIGNAL  edge level    proxy_pass 재사용 reset bad   CPU
  10000=80GB     hot deploy    REUSEPORT      buffering 32개   gw    keepalive
                                accept_mutex                          mismatch
```

### 가지별 핵심 키워드

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① C10K** | thread-per-conn 불가능 | stack 8MB × 10K = 80GB | event-driven 해결 |
| **② Process** | master = 설정/관리 | worker = 요청 처리 (1 per core) | reload = graceful drain |
| **③ Event Loop** | epoll_wait → handle → 재등록 | level vs edge triggered | SO_REUSEPORT 커널 분산 |
| **④ Reverse Proxy** | 11 phase 처리 | proxy_pass + upstream | buffering on/off |
| **⑤ Upstream Pool** | TCP/TLS handshake 절감 | keepalive 32 | HTTP/1.1 + Connection "" |
| **⑥ 운영 장애** | worker_connections + ulimit | 502 keepalive mismatch | $upstream_response_time |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 해당 가지 → 키워드 3개 → 인접 가지로 확장.
>
> 예: "Nginx 어떻게 수만 연결 처리?" → 루트 → ② process + ③ event loop → epoll/non-blocking → 자연스럽게 ⑤ upstream keepalive로 확장.

---

## 1. 가지 ①: C10K 문제 — Nginx가 태어난 이유

### 1.1 핵심 질문

> "Apache가 있는데 왜 Nginx가 등장했나?"

### 1.2 1999년 — C10K Problem이 제기되다

Dan Kegel의 글 "The C10K problem" (1999). 한 서버가 1만 동시 연결을 처리할 수 있는가? — 그때까지 답은 "**불가능**".

```
[Apache prefork 시대]
  요청1..10000 → 자식 프로세스 1..10000 (각 8MB stack, blocking I/O)
  메모리 = 8MB × 10000 = 80GB  ← 1999년 RAM의 100배
  context switch = us × 1만 = 초 단위 오버헤드
```

핵심 한계 3가지:

1. **메모리 폭발** — process/thread 당 stack 수 MB. 1만 동시 = 수십 GB.
2. **Context switch 비용** — CPU가 매번 register/MMU/TLB를 갈아끼움 (us 단위). 1만 thread = CPU 절반 이상 switch에 낭비.
3. **Blocking I/O 모델** — `read()` 한 번에 thread 하나가 멈춤.

### 1.3 패러다임 전환 — Event-driven + Non-blocking I/O

Igor Sysoev가 2004년 발표한 Nginx의 답:

> **"thread 하나가 수천 연결을 동시에 들고 있어도, 멈추지 않고 (non-blocking) 이벤트가 발생한 fd만 골라서 (epoll) 처리한다."**

```
[Nginx event-driven 시대]
  worker1..8 (CPU 8 core) × epoll로 각 8000 fd 감시 → 6.4만 동시 conn
  메모리 = 8MB × 8 + (conn 별 작은 buffer) ≈ 수백 MB
  context switch ≈ 거의 없음 (worker가 자기 fd만)
```

→ **C10K 해결**: 8 worker로 6만+ 동시 연결.

### 1.4 그런데 Apache는 왜 이렇게 못 했나?

Apache도 event MPM(이벤트 모드)을 추가했지만 늦었다. 핵심 이유 3가지:

1. **모듈 ABI** — Apache 모듈들이 blocking 모델에 의존해서 작성됨. event 모델로 바꾸면 모듈 호환 깨짐.
2. **mod_php** — 가장 인기 있는 모듈이 prefork만 지원. PHP가 not thread-safe였기 때문.
3. **레거시** — 1995년 코드베이스. event-driven으로 처음부터 다시 짜는 게 빠름 (= Nginx).

→ 이게 "Apache 대신 Nginx" 시대로 넘어간 진짜 이유. **레거시는 새 패러다임을 따라가지 못한다**.

---

## 2. 가지 ②: Process 모델 — master/worker

### 2.1 백지 그리기 — 1단계

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
    [worker1][worker2]..[workerN]   (nginx user, N = CPU core)
      epoll    epoll     epoll
      event    event     event
      loop     loop      loop
        │       │         │
        └───────┴─────────┘
              │
        공유 listening fd
       (master가 fork로 상속)

   [선택적 보조 프로세스]
     cache manager  ← proxy_cache 만료 정리
     cache loader   ← 시작 시 디스크 캐시 인덱싱
```

### 2.2 master process — 무엇을 하는가

master는 **요청 처리를 하지 않는다**. 오직 관리만.

- **설정 로드**: 시작 시 `nginx.conf` 파싱 → 메모리 구조 빌드. reload 시 새 설정으로 새 worker 띄움.
- **listening socket 생성**: `socket() → bind() → listen()`을 master가 한 번 한다. worker는 fork로 상속.
- **worker 관리**: 죽으면 다시 fork. SIGHUP/SIGTERM/SIGUSR2 같은 signal 처리.
- **권한**: 보통 root로 실행 (포트 80/443 bind 권한 때문). worker는 setuid로 권한 떨어뜨림.

핵심 nginx.conf 발췌:

```nginx
user nginx;             # worker가 떨어질 권한
worker_processes auto;  # = CPU core 수. 명시 추천: 4 / 8 / 16
worker_rlimit_nofile 65535;  # 각 worker의 FD 한계
```

### 2.3 worker process — 실제 일꾼

각 worker는 **독립적인 event loop**를 돈다. 서로 메모리 공유 없음 (멀티프로세스 이유).

- **CPU core 당 1개** 권장 — context switch 최소화. `worker_cpu_affinity auto;`로 pinning 가능.
- **각자 epoll 인스턴스**: worker N개 = epoll 인스턴스 N개. 한 worker가 죽어도 나머지는 무사.
- **shared listening fd**: master가 만든 socket을 fork로 받음. accept할 때 누가 받을지는 별도 메커니즘 (→ 4장).

```nginx
events {
    worker_connections 8192;  # 한 worker의 동시 연결 상한
    # 실제 한도 = min(worker_connections, ulimit -n)
}
```

### 2.4 왜 multi-thread가 아니라 multi-process인가?

이게 시니어 면접 단골 질문. 4가지 이유:

1. **격리** — worker 하나가 segfault나도 master가 다시 fork. thread면 프로세스 전체 사망.
2. **GIL/lock 없음** — process 간 공유 메모리가 없으니 동기화 비용 0. 각자 자기 일.
3. **CPU affinity** — process는 OS scheduler가 CPU에 묶기 쉬움. thread는 어렵다.
4. **NUMA-friendly** — 각 worker를 NUMA node 한 곳에 묶으면 memory locality 좋음.

대신 단점:
- **상태 공유 어려움** — 캐시, rate-limit 카운터 같은 거 공유하려면 shared memory(`ngx_shm_t`) 별도 설계.

### 2.5 보조 프로세스

```
cache loader   : nginx 시작 시 한 번 실행, proxy_cache 디스크 스캔해서 메모리 인덱스 빌드
cache manager  : 주기적 실행, 만료된 cache file 삭제, max_size 초과 시 LRU 제거
```

```nginx
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=mycache:10m max_size=10g
                 inactive=60m use_temp_path=off;
# levels=1:2 → 디렉토리 hash depth (한 디렉토리에 파일 폭증 방지)
# keys_zone → shared memory 영역 (cache index)
# max_size → cache manager가 LRU 정리하는 상한
```

---

## 3. 가지 ③: Event Loop — 심장부

### 3.1 백지 그리기 — 2단계

```
[한 worker 안의 event loop]

   ┌─ worker process ───────────────────────────────┐
   │  ngx_cycle_t  ← 전역 (config, connection 풀)    │
   │                                                │
   │  ┌─ EVENT LOOP (while true) ──────────────┐   │
   │  │ 1. timer = 가장 가까운 timeout 계산       │   │
   │  │ 2. epoll_wait(epfd, events, n, timer)  │   │
   │  │    └── 커널에서 ready된 fd 리스트         │   │
   │  │ 3. for each event:                     │   │
   │  │     accept ev → handle_accept()        │   │
   │  │     read ready → handle_read(c)        │   │
   │  │     write ready→ handle_write(c)       │   │
   │  │     timeout   → handle_timer(c)        │   │
   │  │ 4. expire_timers()                     │   │
   │  │ 5. process_posted_events()             │   │
   │  │ ⤺ goto 1                                │   │
   │  └────────────────────────────────────────┘   │
   │                                                │
   │  [conn1: state] [conn2: state] ... [connN]    │
   └────────────────────────────────────────────────┘
```

### 3.2 의사코드 — Nginx event loop 풀버전

`src/event/ngx_event.c`의 `ngx_process_events_and_timers()` 흐름을 풀면:

```c
// worker 시작 → 이 루프를 영원히 돈다
void worker_main_loop(ngx_cycle_t *cycle) {
    for (;;) {
        // 1) 다음 timer까지 남은 시간 계산
        ngx_msec_t timer = ngx_event_find_timer();
        if (timer == NGX_TIMER_INFINITE || timer > 500) timer = 500;

        // 2) accept_mutex 시도 (옛 방식, SO_REUSEPORT면 skip)
        if (ngx_use_accept_mutex) {
            if (ngx_trylock_accept_mutex(cycle) == NGX_ERROR) return;
        }

        // 3) epoll_wait — 커널에 "ready된 fd 있을 때까지 자라"
        //    timer ms 안에 아무 일 없으면 timeout으로 깨어남
        int n = epoll_wait(ep, event_list, NGX_EVENT_LIST_SIZE, timer);

        // 4) 받은 이벤트 dispatch — 두 단계로 나눠 처리
        for (i = 0; i < n; i++) {
            ngx_connection_t *c = event_list[i].data.ptr;
            uint32_t revents = event_list[i].events;

            if (revents & (EPOLLERR | EPOLLHUP)) {
                /* 에러/끊김 처리 */
            }
            if (revents & EPOLLIN)  c->read->handler(c->read);    // 읽기 가능
            if (revents & EPOLLOUT) c->write->handler(c->write);  // 쓰기 가능
        }

        // 5) accept_mutex 해제
        if (ngx_accept_mutex_held) ngx_shmtx_unlock(&ngx_accept_mutex);

        // 6) 시간 갱신 + 만료된 timer 처리
        ngx_time_update();
        ngx_event_expire_timers();

        // 7) post된 이벤트 (다음 루프로 넘긴 작업) 처리
        ngx_event_process_posted(cycle, &ngx_posted_events);
    }
}
```

핵심 포인트:

- **epoll_wait의 timer**: 다음 timer까지 자다가, fd가 ready 되면 즉시 깨어남. 즉 "**자고 있다가 일감 생기면 깨어 일하는**" 모델.
- **handler dispatch**: 각 connection은 read/write handler를 들고 있고 ready 되면 그게 호출됨. **state machine** 패턴.
- **timer**: keepalive timeout, send_timeout, proxy_read_timeout 등 모든 timeout이 timer로 관리.

### 3.3 epoll — Linux의 I/O multiplexing

epoll은 Linux 2.6의 **scalable I/O multiplexer**. select/poll의 후계자.

#### epoll API 3개

| API | 역할 | 빈도 |
|---|---|---|
| `epoll_create1()` | epoll 인스턴스 생성 | worker 시작 시 1번 |
| `epoll_ctl(ADD/MOD/DEL)` | fd 등록/수정/삭제 | connection 별로 N번 |
| `epoll_wait()` | ready된 fd 목록 받기 | event loop 매 iteration |

#### select/poll vs epoll — 왜 epoll인가?

```
[select/poll] — O(N)
   매번 호출 시 감시할 fd 전체를 커널에 복사
   커널이 모든 fd를 linear scan
   ready fd가 1개여도 N개 스캔 비용 발생

[epoll] — O(1) (ready event 개수 기준)
   epoll_ctl로 한 번 등록 → 커널이 red-black tree에 보관
   fd가 ready되면 커널이 ready list에 추가 (callback)
   epoll_wait는 ready list만 복사해서 반환
```

→ 1만 fd 감시 시: select는 매번 1만 fd 검사. epoll은 ready된 100개만 처리. **2배가 아니라 100배 차이**.

#### Level-triggered (LT) vs Edge-triggered (ET)

```
LT (default) : fd가 ready 상태인 한 epoll_wait가 계속 알림
              → "데이터 남아 있어!" 매번 외침
              → 안전, 일부만 읽어도 다음 loop에서 또 알림

ET           : fd 상태가 "변화"할 때만 알림
              → "방금 ready로 바뀜! 이번 한 번만 알린다"
              → 한 번에 EAGAIN 날 때까지 모두 읽어야 함
              → 알림 횟수 적음 = 더 빠름, 대신 코드 복잡
```

Nginx는 **ET (Edge-triggered) 사용**. 그래서 read/write handler 안에서 EAGAIN(읽을 거 없음) 날 때까지 loop 돌린다.

```c
// non-blocking read 패턴 (Nginx 스타일)
while (1) {
    n = read(fd, buf, size);
    if (n > 0) {
        // 처리
        continue;
    }
    if (n == -1 && errno == EAGAIN) break;  // 더 읽을 거 없음
    if (n == 0)                      break;  // 연결 종료
    if (n == -1)                     /* 에러 처리 */;
}
```

### 3.4 다른 OS의 multiplexer — 추상화 계층

Nginx는 OS별 best multiplexer를 골라 쓴다. `src/event/modules/` 에 OS별 모듈:

| OS | API | Nginx 모듈 |
|---|---|---|
| Linux | epoll | `ngx_epoll_module.c` |
| FreeBSD/macOS | kqueue | `ngx_kqueue_module.c` |
| Solaris | event ports | `ngx_eventport_module.c` |
| Windows | IOCP (제한적) | `ngx_iocp_module.c` |
| 모든 OS | select | `ngx_select_module.c` (fallback) |

`ngx_event_module_t` 인터페이스로 추상화 — event loop 본체는 OS 모르고 동작.

### 3.5 Non-blocking I/O — Nginx의 또 다른 핵심

epoll만으로는 부족하다. **socket이 non-blocking 모드여야** epoll과 짝이 맞는다 (`fcntl F_SETFL | O_NONBLOCK`).

이러면:
- `read()`가 데이터 없으면 → **EAGAIN/EWOULDBLOCK 즉시 반환** (블록 X)
- `write()`가 send buffer full이면 → **EAGAIN 즉시 반환**
- `accept()`가 대기 연결 없으면 → **EAGAIN**

Nginx 패턴:
```
write 시도 → EAGAIN → epoll에 EPOLLOUT 등록 → ready 시 재시도
read  시도 → EAGAIN → epoll에 EPOLLIN  등록 → ready 시 재시도
```

이 패턴이 곧 **state machine**. 각 connection은 "read 대기", "write 대기", "header 파싱 중", "upstream 연결 중" 등의 상태를 들고 있다.

### 3.6 Connection은 어떻게 추적되나 — ngx_connection_t

```c
struct ngx_connection_s {
    void               *data;           // 모듈별 컨텍스트 (HTTP는 ngx_http_request_t)
    ngx_event_t        *read;           // 읽기 이벤트 (handler, timer, flags)
    ngx_event_t        *write;          // 쓰기 이벤트
    ngx_socket_t        fd;             // 소켓 fd
    ngx_recv_pt         recv;           // 함수 포인터 (TCP/SSL에 따라 다름)
    ngx_send_pt         send;
    struct sockaddr    *sockaddr;       // peer 주소
    ngx_pool_t         *pool;           // 이 connection 전용 memory pool
    ngx_buf_t          *buffer;         // 입력 버퍼
    ngx_queue_t         queue;          // free/reusable 리스트 링크
    /* ... */
};
```

worker 시작 시 `worker_connections` 개수만큼 **사전 할당**되어 free list에 들어 있음. 새 연결 들어오면 free list에서 꺼내고, 끝나면 다시 free list로.

→ 즉 **connection 객체 자체는 객체 풀**. malloc/free 비용 없음.

---

## 4. 가지 ④: Accept 처리 + Thundering Herd

### 4.1 문제 상황 — Thundering herd

```
[N개 worker가 같은 listening socket을 들고 있을 때]

새 SYN 도착 → 커널이 listening socket을 "ready" 상태로
           → epoll_wait 중인 모든 worker가 동시에 깨어남
           → 1개만 accept() 성공, 나머지는 EAGAIN
           → "헛스윙" CPU 낭비 + cache 오염
```

이게 **thundering herd 문제**. "천둥에 놀란 가축 떼" — 모두가 동시에 깨지만 정작 일은 1마리만 한다.

### 4.2 옛 해결책 — accept_mutex

```nginx
events {
    accept_mutex on;          # 기본 off (1.11.3+)
    accept_mutex_delay 500ms;
}
```

작동 방식:
1. 모든 worker가 listening fd를 **항상은** epoll에 안 넣는다.
2. event loop 시작에 `ngx_trylock_accept_mutex()` 호출.
3. **mutex 잡은 worker만** listening fd를 epoll에 등록 → 그 worker만 깨어남.
4. 다음 iteration에서 다른 worker가 mutex 시도.

→ 한 번에 1 worker만 accept하니 thundering herd 사라짐. 그러나:
- **공정성 떨어짐** — mutex를 잡은 worker가 다 가져감.
- **latency 증가** — mutex 대기 시간 = `accept_mutex_delay`.

### 4.3 현대 해결책 — SO_REUSEPORT (Linux 3.9+, 2013)

```nginx
http {
    server {
        listen 80 reuseport;   # ← 이 한 글자
    }
}
```

커널 차원의 해결:
- 각 worker가 **독립적인** listening socket을 `bind()` (같은 포트에 N개 socket!).
- 커널이 SYN 도착 시 **socket hash**로 분산. 4-tuple(src_ip, src_port, dst_ip, dst_port) 해시.
- worker 하나만 깨어남, 나머지는 잠.

```
[Before SO_REUSEPORT — accept_mutex 시대]
   listening fd (1개, 공유)
        │
   ┌────┼────┬────┬────┐
   ▼    ▼    ▼    ▼    ▼
   w1   w2   w3   w4   w5    ← 모두 깨어남, 1만 성공

[With SO_REUSEPORT — 현대]
   lsn1  lsn2  lsn3  lsn4  lsn5    ← worker별 독립 socket
    ▼     ▼     ▼     ▼     ▼
    w1    w2    w3    w4    w5     ← 커널이 직접 분산
```

→ **Nginx 1.9.1+ 권장**. accept_mutex 자동으로 의미 없어짐.

### 4.4 SYN backlog — accept 이전 단계

accept()까지 가기 전에도 큐가 있다.

```
[클라이언트 SYN] → 커널 TCP stack
   ├─ SYN_RECV queue  (net.ipv4.tcp_max_syn_backlog)  ← 3-way 중
   ├─ ACK 받음 → ESTABLISHED
   └─ accept queue    (min(somaxconn, listen backlog)) ← user space 대기
                       │
                       ▼  Nginx worker가 accept()
```

운영 함정: `worker_connections 65535`로 키워봤자 `somaxconn=128`이면 SYN flood 시 drop. **함께 봐야 함**.

```bash
sysctl net.core.somaxconn          # default 128~4096
sysctl net.ipv4.tcp_max_syn_backlog
```

---

## 5. 가지 ⑤: HTTP Request 11-Phase 처리

### 5.1 백지 그리기 — 3단계

```
[Nginx HTTP Request 11-phase]

  TCP accept → connection_t → epoll 등록
              │
              ▼ 헤더 수신 (EPOLLIN)
   ┌──────────────────────────────────────────────┐
   │  POST_READ        ← 헤더 파싱 직후              │
   │  SERVER_REWRITE   ← server-level rewrite      │
   │  FIND_CONFIG      ← location 매칭              │
   │  REWRITE          ← location 안 rewrite       │
   │  POST_REWRITE     ← 무한 rewrite 방지           │
   │  PREACCESS        ← rate limit, conn limit    │
   │  ACCESS           ← allow/deny, auth          │
   │  POST_ACCESS      ← satisfy any/all           │
   │  PRECONTENT       ← try_files, mirror         │
   │  CONTENT  ⭐       ← static/proxy/fastcgi 응답  │
   │  LOG              ← access_log                │
   └──────────────────────────────────────────────┘
              │
              ▼  응답 전송 (EPOLLOUT)
        keepalive면 다시 헤더 대기, 아니면 close
```

### 5.2 phase 모델의 의미 — module 시스템

각 phase에 module이 **handler를 등록**한다. 요청이 phase를 따라 흐르며 등록된 handler들을 차례로 호출.

```c
// src/http/ngx_http_core_module.h
typedef enum {
    NGX_HTTP_POST_READ_PHASE = 0,
    NGX_HTTP_SERVER_REWRITE_PHASE,
    NGX_HTTP_FIND_CONFIG_PHASE,
    NGX_HTTP_REWRITE_PHASE,
    NGX_HTTP_POST_REWRITE_PHASE,
    NGX_HTTP_PREACCESS_PHASE,
    NGX_HTTP_ACCESS_PHASE,
    NGX_HTTP_POST_ACCESS_PHASE,
    NGX_HTTP_PRECONTENT_PHASE,
    NGX_HTTP_CONTENT_PHASE,
    NGX_HTTP_LOG_PHASE
} ngx_http_phases;
```

예시 module 배치:
- `ngx_http_realip_module` → POST_READ (실제 client IP 복원)
- `ngx_http_rewrite_module` → SERVER_REWRITE, REWRITE
- `ngx_http_limit_req_module` → PREACCESS (rate limit)
- `ngx_http_access_module` → ACCESS (allow/deny)
- `ngx_http_auth_basic_module` → ACCESS
- `ngx_http_static_module` → CONTENT (정적 파일)
- `ngx_http_proxy_module` → CONTENT (reverse proxy)
- `ngx_http_log_module` → LOG

### 5.3 핵심: 각 phase는 non-blocking — 그래서 한 worker가 수천 동시 처리

```
worker가 동시에 들고 있는 요청 1000개:
   - 요청 #1: ACCESS phase (auth 서버에 subrequest, 응답 대기 중)
   - 요청 #2: CONTENT phase (upstream에 proxy_pass, response 대기 중)
   - 요청 #3: 헤더 수신 중 (EPOLLIN 대기)
   - 요청 #4: 정적 파일 sendfile() 호출 중
   - ...

worker는 한 요청 끝날 때까지 안 기다림.
   EAGAIN 만나면 다음 ready 이벤트로 점프.
```

이게 **event-driven의 진수**. 1 thread, 1 epoll, 수천 요청 동시 진행.

### 5.4 location 매칭 — FIND_CONFIG phase

```nginx
server {
    location = /exact   { ... }   # 정확히 일치 (가장 우선)
    location ^~ /prefix { ... }   # prefix 매칭, regex보다 우선
    location ~  \.php$  { ... }   # case-sensitive regex
    location ~* \.jpg$  { ... }   # case-insensitive regex
    location /          { ... }   # 가장 긴 prefix가 매칭 (default)
}
```

매칭 순서:
1. `=` exact match → 있으면 종료.
2. `^~` prefix match (regex 무시) → 가장 긴 게 이김.
3. 일반 prefix match → 가장 긴 게 후보로 저장.
4. regex match (위에서 아래로 순서대로) → 첫 매칭 사용.
5. 매칭 regex 없으면 → 3에서 저장한 prefix 사용.

운영 함정: regex가 많으면 매 요청마다 N개 regex 시도 → **CPU 폭증**. PCRE JIT(`pcre_jit on;`) 활성화 + regex 수 통제.

---

## 6. 가지 ⑥: Reverse Proxy + Upstream Keepalive Pool ⭐⭐

### 6.1 백지 그리기 — Reverse Proxy 흐름

```
Client                Nginx                       Backend
  │  HTTP req ────►   │                              │
  │                   │ (1) POST_READ ~ ACCESS       │
  │                   │ (2) CONTENT: proxy_pass      │
  │                   │ (3) upstream 선택             │
  │                   │ (4) keepalive 풀에서 conn 차용│
  │                   │     없으면 새 TCP connect    │
  │                   │ ──── HTTP/1.1 req ─────►     │
  │                   │                              │ (5) 처리
  │                   │ ◄──── HTTP response ─────    │
  │                   │ (6) proxy_buffering 적용       │
  │                   │     on : 통째 받아 client 속도│
  │                   │     off: stream 직통          │
  │ ◄── HTTP resp ──  │ (7) conn 반납 (한도면 close)  │
```

### 6.2 핵심 directive 발췌

```nginx
upstream backend {
    server backend1.example.com:8080 weight=3;
    server backend2.example.com:8080;
    server backend3.example.com:8080 backup;     # 다른 게 다 죽으면

    keepalive 32;                # ⭐ 풀 크기 (worker 당)
    keepalive_requests 1000;     # 한 conn 재사용 횟수 한계
    keepalive_timeout 60s;       # idle 후 close
}

server {
    location /api/ {
        proxy_pass http://backend;

        # ⭐⭐ keepalive 작동 필수 조건
        proxy_http_version 1.1;
        proxy_set_header   Connection "";   # 기본 Connection: close 제거

        # buffer 설정
        proxy_buffering on;
        proxy_buffer_size       4k;
        proxy_buffers           8 4k;
        proxy_busy_buffers_size 8k;

        # timeout
        proxy_connect_timeout 5s;
        proxy_send_timeout    60s;
        proxy_read_timeout    60s;

        # backend가 50x 주면 다음 server 시도
        proxy_next_upstream error timeout http_502 http_503;
    }
}
```

### 6.3 upstream keepalive pool — 왜 이게 핵심인가

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

### 6.4 키워드 — proxy_http_version 1.1 + Connection ""

이게 운영 단골 함정. 두 줄 안 적으면 **keepalive 동작 안 함**.

```
HTTP/1.0 default: 매 요청 후 close
HTTP/1.1 default: keep-alive (Connection: keep-alive)

Nginx upstream default proxy_http_version: 1.0  ← !!
       proxy_set_header Connection: close 자동 추가 ← !!

→ proxy_http_version 1.1 안 적으면 → backend 입장 매번 close
→ keepalive 풀 만들어도 즉시 닫힘 = 의미 없음

[올바른 설정]
location /api {
    proxy_pass http://backend;
    proxy_http_version 1.1;
    proxy_set_header   Connection "";   # client의 Connection 헤더 차단
}
```

### 6.5 keepalive_requests / keepalive_timeout

```
keepalive_requests 1000:
   한 conn으로 1000 요청 처리 후 close
   - 메모리 누수 방어
   - sticky LB hash 재분산 기회

keepalive_timeout 60s:
   60초간 idle이면 close
   - backend의 idle timeout보다 짧게 (중요!)
   - 안 그러면 502 발생 (backend가 닫은 걸 모르고 재사용)
```

### 6.6 운영 단골 — 502 Bad Gateway의 keepalive race

```
시점 t=0    Nginx 풀: conn A (idle 30s)
시점 t=31   Backend의 keepalive_timeout 30s → backend가 conn A를 FIN
시점 t=31.5 Nginx가 conn A 꺼내 요청 전송
시점 t=31.6 backend → RST (이미 닫힌 conn)
시점 t=31.7 Nginx → 502 Bad Gateway

해결:
   Nginx keepalive_timeout < Backend keepalive_timeout
   (보통 Nginx 60s, Backend 75s 같이 안전 마진)
```

### 6.7 풀이 부족하면

```
keepalive 32 인데 동시 active 100개라면:
   32개는 풀에서 재사용
   68개는 매번 새 TCP connect (keepalive 풀 진입 못 함, 끝나면 close)

→ 풀 사이즈는 "P99 동시 backend 요청 수" 기준으로 잡아야
→ proxy_busy_connections, $upstream_connect_time 모니터링
```

### 6.8 backend 선택 알고리즘

```nginx
upstream backend {
    # 1) round-robin (default) — 순서대로
    # 2) least_conn          — active conn 적은 곳
    # 3) ip_hash             — client IP hash (sticky)
    # 4) hash $key consistent — consistent hashing (cache locality)
    least_conn;
    server a; server b; server c;
}
```

`consistent` = consistent hashing → backend 추가/제거 시 매핑 재분배 최소화. cache 효율 ↑.

### 6.9 proxy_buffering — on vs off

```
proxy_buffering on (default):
   1) backend 응답 전체를 Nginx의 buffer에 저장
   2) 끝까지 받은 후 client 속도에 맞춰 전송
   3) 장점: slow client가 backend resource 묶지 않음
   4) 단점: 메모리/디스크 사용, latency 추가, streaming 못 함

proxy_buffering off:
   1) backend → Nginx → client 직통 streaming
   2) SSE, WebSocket, 큰 다운로드, gRPC에 필요
   3) slow client = slow backend (backend worker가 묶임)
```

운영 판단:
- 일반 API: on (default 유지)
- SSE / streaming response: off
- 큰 파일 다운로드 (영상, archive): off + sendfile 활용
- WebSocket: `proxy_http_version 1.1` + `Upgrade/Connection` 헤더 추가, buffering 자동 off

---

## 7. 정적 파일 + 캐시 + SSL/TLS + 메모리

### 7.1 정적 파일 — sendfile zero-copy

전통적인 file → socket 전송:
```
read(file_fd, buf, ...)   ← kernel → user space로 복사
write(socket_fd, buf, ...) ← user → kernel space로 복사
```
2번 복사 + 2번 context switch.

**sendfile() 시스템 콜** — Linux 2.2+:
```
sendfile(out_fd, in_fd, ...) ← kernel 안에서 직접 file → socket
```
→ user space 거치지 않음 = **zero-copy**. CPU 절약, throughput 향상.

```nginx
sendfile           on;     # 정적 파일 sendfile() 사용
tcp_nopush         on;     # sendfile + Nagle 비활성 조합 (헤더와 본문을 한 패킷)
tcp_nodelay        on;     # Nagle 비활성 (latency 우선)
aio                on;     # async I/O (Linux + ext4/XFS) — 디스크 미스 시 worker 안 막힘
```

### 7.2 open_file_cache — fd/metadata 캐시

```nginx
open_file_cache max=10000 inactive=60s;
open_file_cache_valid 30s;
open_file_cache_min_uses 2;
open_file_cache_errors on;
```

매 요청마다 `open()` → `fstat()` → `read()` → `close()`를 반복하면 syscall 비용 폭증. 자주 쓰는 파일은 fd/metadata를 캐시.

### 7.3 gzip / brotli — on-the-fly compression

```nginx
gzip            on;
gzip_types      text/css application/javascript application/json;
gzip_comp_level 5;     # 1~9, 트레이드오프: CPU vs 크기
gzip_min_length 1000;  # 작은 응답 압축 안 함 (오버헤드)
```

운영 함정: `gzip_comp_level 9`로 올리면 CPU 폭증. 5~6이 sweet spot.

### 7.4 Reverse Proxy Cache

```nginx
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=apicache:100m
                 max_size=10g inactive=24h use_temp_path=off;

location /api/products {
    proxy_cache       apicache;
    proxy_cache_key   "$scheme$host$request_uri";
    proxy_cache_valid 200 5m;

    proxy_cache_lock          on;       # ⭐ thundering herd 방지
    proxy_cache_use_stale     error timeout updating;
    proxy_cache_background_update on;   # stale 주고 비동기 갱신

    add_header X-Cache-Status $upstream_cache_status;  # HIT/MISS/STALE
}
```

핵심 패턴:
- **microcaching** — `proxy_cache_valid 200 1s;` 만 줘도 동일 URL RPS 폭주를 backend가 안 맞음. read-heavy origin 보호의 황금기법.
- **cache_lock** — cache miss 동시 100건 떠도 backend엔 1건만.
- **background_update** — stale 응답 주면서 비동기 갱신 → P99 안정화.

### 7.5 SSL/TLS

```nginx
ssl_protocols       TLSv1.2 TLSv1.3;
ssl_ciphers         <strong-suite>;
ssl_session_cache   shared:SSL:50m;   # session resumption (handshake 절감)
ssl_session_tickets on;
ssl_stapling        on;               # OCSP stapling — 인증서 검증 RTT 절감
ssl_stapling_verify on;

# HTTP/2 — ALPN으로 협상
listen 443 ssl http2 reuseport;
```

핵심:
- **session resumption** — 같은 client 재방문 시 full handshake 대신 abbreviated (1 RTT 절감).
- **OCSP stapling** — 인증서 revocation 검증을 Nginx가 미리 받아 응답에 동봉 → client가 OCSP 서버 안 가도 됨.
- **HTTP/2** — multiplexing(1 TCP에 N stream) + HPACK 헤더 압축.

### 7.6 메모리 모델 — ngx_pool_t

이게 Nginx 설계의 숨은 보석. **per-request memory pool**.

```c
// 요청 시작 시
ngx_pool_t *pool = ngx_create_pool(4096, log);  // 4KB 짜리 pool

// 요청 처리 중 어디서나
char *s = ngx_palloc(pool, 100);   // 100 byte 빌려옴
struct foo *f = ngx_palloc(pool, sizeof(*f));
// ... free 절대 안 함

// 요청 끝나면
ngx_destroy_pool(pool);   // ⭐ pool 통째 free → 안에 있던 모든 할당이 한 번에 free
```

장점:
- **fragmentation 없음** — pool을 통째로 들고 통째로 버림.
- **leak 거의 불가능** — 개별 free 안 함, pool destroy면 모두 회수.
- **per-request locality** — 같은 요청 데이터가 메모리상 근접 → cache friendly.

운영 함정:
- 한 요청이 끝나기 전엔 안 풀림 → **장기 connection (WebSocket, SSE)** 은 pool이 오래 살아 RSS 증가.
- worker의 RSS = sum(active connection pool 크기). `htop`으로 worker RSS 모니터링 필요.

---

## 8. 가지 ⑥ 운영 장애 패턴 + 측정·진단 ⭐

### 8.1 정상 상태 베이스라인 — 알아두자

```bash
# 1) 빌드 정보 + 컴파일 옵션 + 모듈 목록
nginx -V                   # stderr로 옵션 출력 (HTTP/2, 어떤 module 빌드됐나)

# 2) 설정 검증
nginx -t

# 3) 현재 active 상태 (stub_status 모듈 필요)
curl http://localhost/nginx_status
# Active connections: 291
# server accepts handled requests
#  16630948 16630948 31070465
# Reading: 6  Writing: 179  Waiting: 106
```

```nginx
# stub_status 활성화
location /nginx_status {
    stub_status;
    allow 127.0.0.1;
    deny all;
}
```

값 의미:
- **Active**: 현재 worker가 들고 있는 connection 총합.
- **Reading**: 요청 헤더 읽는 중.
- **Writing**: 응답 보내는 중 (또는 upstream에 보내는 중 포함).
- **Waiting**: keepalive idle 상태. (Active - Reading - Writing)

### 8.2 access_log 필드 — 진단의 핵심

```nginx
log_format diag '$remote_addr - $remote_user [$time_local] '
                '"$request" $status $body_bytes_sent '
                '"$http_referer" "$http_user_agent" '
                'rt=$request_time uct=$upstream_connect_time '
                'uht=$upstream_header_time urt=$upstream_response_time '
                'uaddr=$upstream_addr ucs=$upstream_cache_status';

access_log /var/log/nginx/access.log diag;
```

핵심 변수:

| 변수 | 의미 |
|---|---|
| `$request_time` | client 첫 byte 수신 ~ 마지막 응답 byte 전송까지 (총 latency) |
| `$upstream_connect_time` | backend TCP connect 소요 (keepalive 재사용 시 0.000) |
| `$upstream_header_time` | backend가 응답 헤더 보내기까지 (backend 처리 시간 근사) |
| `$upstream_response_time` | backend 응답 헤더+본문 받는 데 걸린 시간 |
| `$upstream_addr` | 실제 선택된 backend (LB 결과 확인) |
| `$upstream_cache_status` | HIT/MISS/EXPIRED/STALE/UPDATING/BYPASS |

진단 공식:
```
$request_time - $upstream_response_time  ≈  client ↔ Nginx 구간 (slow client?)
$upstream_response_time - $upstream_header_time ≈ backend 응답 본문 전송 시간
$upstream_connect_time > 0.001         ≈ keepalive 풀 miss → 새 connect
```

### 8.3 운영 시나리오 톱 8

#### S1. "worker_connections 늘렸는데 동접 효과 없음"

```
증상: worker_connections 65535로 올렸는데 active conn 1024 이상 안 감
원인 후보:
   1. ulimit -n (FD limit, default 1024)
   2. sysctl net.core.somaxconn (accept queue)
   3. sysctl net.ipv4.tcp_max_syn_backlog (SYN queue)
   4. worker_rlimit_nofile 설정 안 함

진단:
   $ cat /proc/$(pgrep nginx | head -1)/limits | grep "open files"
   $ sysctl net.core.somaxconn
   $ ss -ltn | grep :443  # Send-Q가 backlog limit

해결:
   /etc/security/limits.conf 또는 systemd unit:
     LimitNOFILE=200000
   sysctl:
     net.core.somaxconn = 65535
     net.ipv4.tcp_max_syn_backlog = 65535
   nginx.conf:
     worker_rlimit_nofile 200000;
     events { worker_connections 65535; }
   listen 443 ssl http2 backlog=65535 reuseport;
```

#### S2. "502 Bad Gateway 간헐적"

```
증상: 503/504 아니라 502가 무작위로 1% 발생
원인 후보:
   1. backend가 keepalive idle conn 먼저 닫음 → Nginx가 재사용 시 RST → 502
   2. backend OOM-killed
   3. proxy_read_timeout 초과 (이건 보통 504)

진단:
   tail -f /var/log/nginx/error.log | grep upstream
   # "upstream prematurely closed connection while reading response header from upstream"
   # → 거의 항상 keepalive race
   
   access_log에서:
   awk '$status==502 {print $upstream_addr, $upstream_response_time}' access.log | sort | uniq -c

해결:
   1. Nginx keepalive_timeout < Backend의 idle timeout (안전 마진)
      예: Tomcat keepAliveTimeout 60s → Nginx upstream keepalive_timeout 50s
   2. proxy_next_upstream으로 자동 재시도
      proxy_next_upstream error timeout http_502;
      proxy_next_upstream_tries 2;
```

#### S3. "high CPU — 한 worker가 100%"

```
증상: 한 worker만 CPU 100%, 다른 worker는 한가
원인 후보:
   1. regex 폭증 (location ~ <복잡regex>)
   2. accept_mutex 없이 한 worker만 accept
   3. PCRE JIT 비활성
   4. SSL handshake 폭주 (keepalive 미설정으로 매번 handshake)

진단:
   top -p $(pgrep nginx) -H    # worker별 CPU
   strace -p <worker-pid> -c   # syscall 빈도 (read/write/epoll vs SSL_*)
   perf top -p <worker-pid>    # function 단위 hot spot

해결:
   - load balancer가 worker로 분산 못 함 → SO_REUSEPORT 활성화
   - PCRE JIT: pcre_jit on;
   - keepalive 설정으로 handshake 감소
   - regex 단순화
```

#### S4. "504 Gateway Timeout 다수"

```
증상: client가 504, error.log에 "upstream timed out"
원인 후보:
   1. backend slow query (DB lock, slow disk)
   2. proxy_read_timeout 기본 60s가 짧음
   3. backend 응답 stuck (deadlock)

진단:
   access_log에서 $upstream_response_time > 60s 비율 확인
   backend의 slow query log / APM 확인 (Nginx만으로 안 됨)

해결:
   - backend 문제는 backend에서 (Nginx는 증상만)
   - proxy_read_timeout 조정 (단, 길게 잡으면 worker가 묶임)
   - 503/504 시 정적 fallback page:
     error_page 504 /maintenance.html;
```

#### S5. "TLS handshake 부하 폭증"

```
증상: HTTPS만 응답 지연, CPU 폭증
원인: session resumption 미작동 → 매 요청 full handshake

진단:
   openssl s_client -connect host:443 -reconnect
   # "Reused" 로그 확인
   
   ss -tlnp | grep :443

해결:
   ssl_session_cache shared:SSL:50m;
   ssl_session_timeout 1d;
   ssl_session_tickets on;
   # TLS 1.3 사용 (1 RTT handshake)
```

#### S6. "Container OOM-killed (nginx worker)"

```
증상: worker가 갑자기 죽고 master가 재포크 반복
원인 후보:
   1. proxy_buffers 크게 잡은 상태에서 long-running connection 다수
   2. large request body (proxy_request_buffering, client_body_buffer_size)
   3. 메모리 leak (third-party 모듈, Lua scripts)

진단:
   dmesg | grep -i "killed process"
   for pid in $(pgrep -f "nginx: worker"); do
       echo "PID $pid: $(cat /proc/$pid/status | grep VmRSS)"
   done

해결:
   - worker RSS를 정기 모니터링 (per-worker)
   - container memory limit + worker_processes 보수적으로
   - reload 정기 실행 (메모리 reset, OpenResty Lua의 경우 효과적)
```

#### S7. "reload 후 옛 요청이 끊김"

```
증상: nginx -s reload 후 일부 요청 RST
원인 후보:
   1. worker_shutdown_timeout 짧음 → 진행 중 요청 강제 종료
   2. long-running connection (WebSocket, SSE)이 timeout 안에 안 끝남

진단:
   ps -ef | grep "nginx: worker process is shutting down"
   # graceful drain 중인 옛 worker 확인

해결:
   worker_shutdown_timeout 30s; (긴 timeout)
   long-conn 서비스라면 reload 빈도 낮추기
   binary upgrade는 nginx -s USR2로 (옛 worker 자연 종료 대기)
```

#### S8. "특정 backend로만 트래픽 쏠림"

```
증상: 8 backend 중 1개만 CPU 80%, 나머지 한가
원인 후보:
   1. ip_hash 사용 + client 분포 편향 (회사 NAT)
   2. consistent hash key 편향
   3. backend 자체 응답이 빠르다 (round-robin은 응답 시간 무관)

진단:
   access_log $upstream_addr 분포:
   awk '{print $upstream_addr}' access.log | sort | uniq -c

해결:
   - least_conn으로 변경 (active conn 적은 곳)
   - hash key 분포 점검 (request_id 같은 high-cardinality key)
   - sticky 필요 없으면 round-robin 또는 random two-choices
```

### 8.4 진단 도구 톱 7

```bash
# 1. 설정/빌드
nginx -V             # 컴파일 옵션, 모듈
nginx -t             # 설정 syntax 검증
nginx -s reload      # graceful reload

# 2. live 상태
curl http://localhost/nginx_status

# 3. access_log 분석
awk '$status >= 500 {print}' access.log | tail
awk '{print $status}' access.log | sort | uniq -c
sort -k<rt_field> -n access.log | tail -10   # 가장 느린 요청

# 4. error_log 핵심 메시지
# "upstream prematurely closed connection" → keepalive race
# "upstream timed out"                     → backend hang
# "open() failed (24: Too many open files)" → FD limit
# "worker_connections are not enough"      → worker_connections 부족
# "SSL_do_handshake() failed"              → TLS 문제

# 5. process / fd / syscall
top -p $(pgrep nginx) -H                # worker별 CPU/MEM
ls /proc/<worker-pid>/fd | wc -l         # 사용 중 FD
strace -p <worker-pid> -c -e network    # syscall 통계
perf top -p <worker-pid>                # function hot spot
```

---

## 9. 트레이드오프 — Apache prefork vs Nginx event-driven ⭐

### 9.1 한눈 비교

| 측면 | Apache prefork | Apache worker/event | Nginx |
|---|---|---|---|
| 동시성 모델 | process/conn | thread + event 혼합 | **event/worker (1:N)** |
| 동시 연결 한도 | 수백 | 수천 | **수만~수십만** |
| 메모리/conn | 8MB+ (process stack) | 수백 KB | **수 KB (event state)** |
| Blocking I/O 영향 | 그 process만 막힘 | 그 thread만 막힘 | **worker 전체 막힘** ⚠ |
| 모듈 격리 | 강함 | 보통 | 약함 |
| `mod_php` 호환 | ✅ | △ | ❌ (별도 php-fpm) |
| 코드 모델 | 동기 | 동기 | 비동기 (콜백) |
| 설정 reload | graceful | graceful | **graceful + USR2 hot upgrade** |
| 정적 파일 | OK | OK | **sendfile zero-copy** |
| Reverse proxy | mod_proxy | mod_proxy | **first-class** |

### 9.2 Nginx의 약점 — 정직하게 본다

- **blocking 작업이 worker 전체를 막는다** — disk read가 slow하면 그 worker가 들고 있는 수천 connection이 모두 멈춤. `aio threads` directive로 별도 thread pool에 위임 가능 (1.7.11+).
- **C 모듈 작성 어려움** — 비동기 콜백 모델은 진입장벽 높음 → OpenResty(Lua), njs(JavaScript) 같은 스크립팅 솔루션 등장.
- **모듈 격리 약함** — third-party 모듈 버그가 worker crash → master가 다시 fork하지만 그 사이 일부 요청 손실.
- **dynamic config 약함** — nginx-plus나 OpenResty 없이는 upstream 동적 변경이 어려움 (reload 필요).

### 9.3 언제 Apache가 맞나

- 레거시 mod_php 의존 시
- .htaccess 디렉토리별 설정이 필수일 때
- 모듈 격리가 critical할 때 (격리된 process 모델)

→ 그러나 현대 production은 **Nginx + php-fpm** 또는 **Nginx + 백엔드 앱서버** 조합이 표준.

### 9.4 Nginx vs Envoy — 차세대 비교

| 항목 | Nginx | Envoy |
|---|---|---|
| 정체성 | 1만 RPS 베테랑 | Service Mesh 시대 표준 |
| 확장 | C 모듈 + Lua | C++ + xDS API (동적) |
| Reconfig | reload (HUP, 잠깐 끊김) | hot update (무중단) |
| HTTP/3 | 제한적 | first-class |
| Service Discovery | 정적 weight | 동적 (Consul, EDS) |
| Observability | stub_status + 3rd-party | Prometheus first-class |
| 운영 | nginx.conf | xDS server 필요 |

판단 기준:
- **edge / CDN origin** → Nginx (성숙, 단순)
- **service mesh internal** → Envoy (동적, observability)
- **API gateway** → Kong/APISIX (OpenResty)
- **Kubernetes ingress** → ingress-nginx, Traefik, Envoy 기반 Contour

### 9.5 Nginx 생태 변종

| 변종 | 무엇 | 언제 |
|---|---|---|
| **Nginx OSS** | 무료, source 공개 | 표준 |
| **Nginx Plus** | 상용 — 동적 reconfig API, 활성 health check, JWT 등 | 엔터프라이즈 |
| **OpenResty** | Nginx + LuaJIT — 코드를 Lua로 | dynamic logic, API gateway (Kong이 이걸 씀) |
| **Tengine** | 알리바바 변종 | 대규모 트래픽 + dynamic module |
| **ingress-nginx (k8s)** | Lua + Go controller | Kubernetes |
| **Angie** | Nginx fork (러시아 vs F5 사태 후 분기) | 정치적/라이선스 이슈 회피 |

---

## 10. 꼬리질문 — 3단 깊이

### Q1. "Nginx 1 worker가 10000 connection 처리 가능하다는데, 어떻게?"

**예상답**:
- non-blocking socket + epoll로 ready된 fd만 다룸.
- worker가 blocking 안 함 → 한 thread가 수천 fd를 "왔다 갔다" 처리.
- 각 connection 메모리 ≈ 수 KB (ngx_connection_t + buffer).

**꼬리 1**: "그러면 한 connection이 SQL 결과 기다리면 worker가 어떻게 되나?"

→ Nginx 자체는 backend 응답을 **epoll로 기다림**. backend fd도 worker의 epoll에 등록되어 있어서 다른 connection 처리 가능. blocking 안 함.

**꼬리 2**: "blocking 시스템 콜이 worker 전체를 막는 케이스 있나?"

→ 있다.
1. **disk I/O** (sendfile, file read) — `aio` 또는 `aio threads`로 thread pool 위임 가능.
2. **DNS resolution** — Nginx의 builtin resolver는 async지만, OS getaddrinfo를 직접 쓰는 third-party 모듈은 blocking.
3. **synchronous Lua I/O** — OpenResty에서 잘못된 lua 코드.
4. **regex 폭증** (PCRE backtracking) — CPU bound지만 worker 묶음.

**꼬리 3**: "regex backtracking이 worker 묶는 시나리오는?"

→ Nested quantifier + catastrophic backtracking. 예: `(a+)+$` 같은 패턴에 `"aaaaaaaaaaaaaaaaX"` 입력 → 지수 시간. PCRE JIT 켜도 일부 패턴은 폭발. 운영 방어: regex 복잡도 제한 + `pcre_jit on;` + 응답 timeout(worker_shutdown_timeout과 별개로 keepalive_timeout/client_header_timeout).

---

### Q2. "upstream keepalive 32인데 동시 active 200 backend 요청이면?"

**예상답**:
- 32개는 풀에서 재사용.
- 168개는 새 TCP connect → 요청 끝나면 풀 들어갈 자리 없으면 close (32 초과는 풀 진입 못 함).
- 핸드셰이크 비용 168배 증가.

**꼬리 1**: "그럼 keepalive를 200으로 올리면 되나?"

→ 그게 답인 경우도 있지만 함정 3개:
1. **worker당** 풀이라 N worker × 200 = total backend conn. backend가 받을 수 있는지 확인 필요.
2. backend의 max conn 한계.
3. 너무 크면 idle conn이 backend 메모리 차지.

**꼬리 2**: "동시 backend 요청 수를 어떻게 측정하나?"

→ Nginx access_log의 `$upstream_addr` + timestamp 분석. 또는 backend의 active connection metric. Prometheus가 있으면 `histogram(upstream_request_duration)` × RPS.

**꼬리 3**: "P99 동시 backend 요청이 spike하면 keepalive를 늘리는 게 최선인가?"

→ 종합 판단:
- backend가 burst를 받을 능력 있으면 → 풀 늘림.
- backend 자체가 한계면 → Nginx에서 **rate limit** (`limit_req`) 으로 흘려보내기 조절.
- spike가 캐시 가능한 응답이면 → **microcaching** + cache_lock.
- spike가 단일 path면 → **proxy_cache_background_update**로 stale 응답 + 비동기 갱신.

---

### Q3. "Nginx reload 후 일부 요청이 502 되는 이유는?"

**예상답**:
- reload 시 master가 새 worker 띄우고, 옛 worker는 새 요청 안 받고 진행 중 요청 마무리 후 종료 (graceful drain).
- 새 listening fd는 새 worker만 받음.
- 보통 끊김 없음.

**꼬리 1**: "그런데 왜 502가 보이나?"

→ 시나리오 3:
1. **옛 worker의 upstream keepalive 풀** — 옛 worker가 죽으면서 풀 안의 idle conn도 close. 그 사이 새 요청이 그 conn 쓰려다 RST.
2. **worker_shutdown_timeout 초과** — 진행 중 요청이 시간 안에 안 끝나면 강제 종료.
3. **long-running connection** — WebSocket/SSE는 보통 reload 시 끊김.

**꼬리 2**: "끊김 없이 hot upgrade하려면?"

→ **nginx -s USR2** 패턴:
1. master에 USR2 → 새 master + 새 worker가 추가로 뜸 (옛 master 살아 있음).
2. 두 master가 listening fd 공유 (옛 master가 fork로 전달).
3. 옛 master에 WINCH → 옛 worker만 graceful 종료.
4. 옛 master 확인 후 QUIT → 완전 교체.
- 이게 진정한 zero-downtime binary upgrade. 다만 long-conn은 여전히 문제.

**꼬리 3**: "long-running WebSocket이 reload 시에도 안 끊기게 하려면?"

→ Nginx만으로는 어렵다. 옵션:
1. **worker_shutdown_timeout 충분히 길게** (예: 24h) — 그러나 reload 빈도 낮춰야.
2. **graceful drain layer 분리** — Envoy/HAProxy 같은 hot-config 도구를 앞에 두고, Nginx는 뒤에 두기.
3. **클라이언트 reconnect 로직** — 어차피 네트워크 끊김 시 재연결 필요. close 시 적절한 reason code(1001 going away).
- 결국 **WebSocket 끊김은 reconnect로 풀어야** — 인프라가 100% 보장 못 함.

---

### Q4. "epoll_wait가 ready된 fd 100개 반환했다. Nginx는 어떻게 처리?"

**예상답**:
- 반환된 event_list를 for loop으로 순회.
- 각 event의 `data.ptr` → ngx_connection_t.
- `EPOLLIN` → read handler, `EPOLLOUT` → write handler 호출.
- 각 handler는 non-blocking으로 처리 후 return.
- 다 끝나면 다시 epoll_wait.

**꼬리 1**: "100개를 처리하는 동안 새 SYN 들어오면?"

→ 그 SYN은 커널이 listening socket의 accept queue에 넣어둠. 다음 epoll_wait에서 listening fd가 ready로 반환되어 accept 처리. **사이클 1개 latency** 정도 추가.

**꼬리 2**: "그러면 100개를 처리하는 시간이 길면 새 accept가 지연되겠네?"

→ 정확하다. 그래서 Nginx는 **post 처리 메커니즘** 사용: 무거운 작업은 `ngx_post_event(ev, &ngx_posted_events)`로 큐에 넣고, event loop 끝에서 `ngx_event_process_posted()`로 처리. accept event는 우선순위 큐(`ngx_posted_accept_events`)에 따로 넣음. **accept 먼저, 그 외는 나중에** 패턴.

**꼬리 3**: "그래도 한 handler가 진짜 오래 걸리면 (예: 큰 응답 헤더 파싱)?"

→ Nginx 코드는 **state machine** 으로 작성됨. 헤더 파싱도 한 번에 다 안 하고 "버퍼만큼만 파싱 → 부족하면 state 저장하고 return → 다음 read에서 이어서". 즉 Nginx에서 "오래 걸리는 handler"는 거의 없음. 다만 third-party 모듈/Lua에서 잘못 작성하면 발생.

---

### Q5. "Nginx vs Envoy — Service Mesh에 Nginx 못 쓰나?"

**예상답**:
- 둘 다 L7 proxy인 건 맞음.
- Envoy는 xDS(Discovery Service) API로 **동적 reconfig** — service mesh에 적합.
- Nginx는 reload 필요 → mesh의 빠른 변화 대응 어려움.

**꼬리 1**: "Nginx Plus나 OpenResty로는 안 되나?"

→ Nginx Plus는 API로 upstream 동적 변경 가능 → 부분적으로 됨. OpenResty는 Lua로 service discovery 통합 가능 (etcd, Consul) → Kong이 이렇게 만든 거. 그러나:
- Envoy는 처음부터 mesh 위해 설계 (Lyft의 production 검증).
- Observability (Open Telemetry, Prometheus first-class) 격차.
- xDS의 표준화 (Istio, AWS App Mesh, Consul Connect 다 채택).

**꼬리 2**: "그러면 결국 Nginx의 자리는?"

→ 살아남는 자리:
1. **Edge proxy / Web server** — 정적 파일, 캐시, SSL termination.
2. **API gateway** — Kong/APISIX (OpenResty 기반).
3. **Kubernetes ingress** — ingress-nginx가 가장 많이 쓰임.
4. **Legacy 시스템** — 검증된 안정성.
5. **단순 reverse proxy** — Envoy는 오버킬일 때.

**꼬리 3**: "그럼 Envoy가 다 가져갈까?"

→ 아니다. 두 도구의 **운영 비용/복잡도** 차이가 크다.
- Envoy: xDS server 운영 필요, 학습 곡선 가파름, 메모리 사용 큼.
- Nginx: nginx.conf 한 장이면 됨, 익숙함, 메모리 효율.
- 결론: **소규모/중규모 + 단순 reverse proxy = Nginx, 대규모 mesh = Envoy**. 둘은 한동안 공존.

---

## 부록 A. 한 장 종합 — Nginx의 정수

```
[Nginx = master/worker × event-driven × non-blocking × pool 재사용]

  사용자 요청
    │
    ▼
  ┌─ Kernel TCP stack ────────────────────────────┐
  │  SYN queue → accept queue → SO_REUSEPORT 분산 │
  └─────────────┬─────────────────────────────────┘
                ▼
  ┌─ Nginx master ────────────────────────────────┐
  │  nginx.conf / worker fork / reload(HUP) / USR2│
  └─────────┬─────────────────────────────────────┘
            │ fork() + setuid
  ┌─────────┴─────────┬─────────────┬─────────────┐
  ▼                   ▼             ▼             ▼
[worker1]         [worker2]  ... [workerN]   [cache mgr]
  epoll loop        epoll        epoll
  11-phase HTTP
  ngx_pool_t
  keepalive pool
  open_file_cache
            │
            ▼  sendfile / proxy_pass
  [static]  [upstream backend 1..N]
            keepalive 32 + HTTP/1.1 + Connection ""

[3개 사실만 외우면 됨]
  1. master는 관리, worker가 일한다 (CPU core 당 1개)
  2. worker = epoll + non-blocking + state machine (수천 conn 동시)
  3. upstream keepalive 풀이 backend handshake 비용을 거의 0으로 만든다
```

---

## 부록 B. 다른 챕터로의 연결

- **02-dns-and-routing** — 요청이 Nginx에 도달하기 전 단계 (DNS, BGP, anycast).
- **03-osi-7-layers-and-tcp-tls** — Nginx의 listen socket이 받는 TCP/TLS 흐름.
- **04-load-balancer-deep-dive** — Nginx 자체도 L7 LB. L4 LB와의 협력 (LB ─ Nginx ─ backend).
- **06-tomcat-internals** — Nginx가 proxy_pass로 보내는 backend 측 Tomcat의 Acceptor→Poller→Executor.
- **07-connection-pools-master** — Nginx upstream keepalive + Tomcat thread pool + HikariCP + kernel backlog 종합.
- **jvm/05-threading** — Tomcat의 thread/Virtual Thread 모델. event loop vs thread per request 비교 관점.

---

## 마치며

Nginx는 1999년 C10K 문제에 대한 답으로 태어났다. 25년이 지난 지금도 답이 유효한 이유는:

1. **메커니즘이 단순하다** — master/worker + epoll + non-blocking + pool. 외울 게 5개.
2. **state machine 기반** — 어떤 시점에도 dump 뜨면 connection 상태가 명확.
3. **메모리 모델이 보수적** — ngx_pool_t로 leak 거의 불가능.
4. **운영 신호가 풍부** — access_log, error_log, stub_status, $upstream_* 변수.

시니어가 Nginx를 다룬다는 건:
- worker_connections 늘려도 안 늘어나면 ulimit + somaxconn + worker_rlimit_nofile을 같이 본다.
- 간헐 502는 keepalive race를 의심한다 (Nginx vs Backend timeout 차이).
- CPU 폭증 시 hot worker를 strace/perf로 까본다.
- reload는 zero-downtime이 아니다 — long-conn 끊김, USR2 한계를 안다.
- Envoy/Nginx Plus/OpenResty 중 무엇을 언제 쓸지 판단 근거가 있다.

이게 백지에서 그릴 수 있고 운영 사고를 분석할 수 있는 "Nginx 마스터 수준"이다.
