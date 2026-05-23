# 03. Java Threads — 사용자 코드 관점의 Thread 마스터

> "Thread를 만들어 쓴다" 한 줄로 끝낼 수 있는 시대는 끝났다.
> Thread 하나가 1MB stack을 먹는 **OS 자원**이라는 사실, ExecutorService가 어떤 큐 정책을 쓰느냐에 따라 production이 **OOM**이 되느냐 **reject**가 되느냐, ThreadLocal이 Tomcat ThreadPool에서 어떻게 **누수**를 만드는가, jstack을 어떻게 읽으면 **deadlock**과 **lock contention**과 **thread starvation**을 구분하는가 — 이게 시니어의 Thread 지식이다.
> 이 문서는 **Java 사용자 코드 관점**에서 Thread API, ExecutorService, ForkJoinPool, ThreadLocal, race condition, CompletableFuture, Virtual Thread를 다룬다. JVM 내부(JMM, Memory Barrier, Mark Word)는 [jvm/05-threading/](../jvm/05-threading/)에서 다룬다.

---

## 이 문서의 사용법

1. **0장 마인드맵을 먼저 외운다**.
2. **1~7장 7단 레이어를 순서대로 학습**.
3. **8장 운영 시나리오 + 9장 꼬리질문**으로 검증.

---

## 0. 마인드맵 — 백지에 그릴 그림

### 루트 한 문장 (anchor)

> **"Java Thread = OS Thread (1:1, 1MB stack). 비싼 자원이라 풀로 재사용한다. ExecutorService는 큐 정책으로 OOM/reject 트레이드오프를 정한다. ForkJoinPool은 work-stealing으로 CPU-bound 분할 정복. ThreadLocal은 풀에 재사용되는 thread 때문에 누수의 단골. jstack은 thread state로 진단한다."**

### 6개 가지

```
              [ROOT: Thread = 비싼 OS 자원 + 풀 재사용 + state 진단]
                                  │
   ┌────────┬────────┬────────────┼────────────┬────────┬────────┐
   │        │        │            │            │        │        │
  ① 본질   ② 생성    ③ 상태       ④ Executor   ⑤ FJP   ⑥ 동기화 ⑦ 진단
 (1:1,1MB) (4방식)  (RUNNABLE/    (4가지+직접)  (work    (sync/   (jstack,
            구식 X   BLOCKED/      OOM vs       steal)   Lock/   JFR,
            ↓        WAITING/      reject       managed  Atomic/ async-
           Executor  TIMED)        Tomcat 변종) Blocker  volatile)profiler)
```

### 가지별 핵심 키워드

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① 본질** | OS thread 1:1 | 1MB stack | unable to create native thread |
| **② 생성** | new Thread (X) | ExecutorService | CompletableFuture / VirtualThread |
| **③ 상태** | NEW→RUNNABLE→BLOCKED/WAITING/TIMED→TERMINATED | Socket.read는 RUNNABLE(!) | jstack mapping |
| **④ Executor** | Fixed/Cached/Single/Scheduled | ThreadPoolExecutor 권장 | Tomcat TaskQueue 변종 |
| **⑤ FJP** | compute()/fork()/join() | deque + work-stealing | ManagedBlocker (parallel stream 함정) |
| **⑥ 동기화** | sync/ReentrantLock/RW/Stamped | Atomic+CAS, LongAdder | volatile visibility |
| **⑦ 진단** | jstack, thread name | thread dump 패턴 (BLOCKED 군집) | async-profiler wallclock |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 해당 가지 → 키워드 3개 → 운영 시나리오로 확장

---

## 1. 백지 그리기 — 손그림 가이드

### 1.1 Thread의 본질 그림

```
[Java 코드 관점]                [OS 관점]
                                
    Thread t = new Thread(r);  ──▶  pthread_create(...)
    t.start();                       │
                                     ▼
                                 ┌─────────────┐
                                 │ OS Thread   │  ← Kernel scheduler가 관리
                                 │ TID = 12345 │
                                 ├─────────────┤
                                 │ Stack (1MB) │  ← -Xss 옵션
                                 │  - frame    │
                                 │  - frame    │
                                 │  - ...      │
                                 ├─────────────┤
                                 │ PC, regs    │
                                 └─────────────┘
                                
    1 Java Thread = 1 OS Thread (Platform Thread)
    cf. Virtual Thread (JDK 21+) = M:N
```

### 1.2 ThreadPoolExecutor 흐름

```
                  submit(task)
                       │
                       ▼
         ┌──────────────────────────┐
         │ workerCount < corePool ? │──Yes──▶ 새 worker 생성 (core)
         └──────────────────────────┘
                       │ No
                       ▼
         ┌──────────────────────────┐
         │  queue.offer(task) OK ?  │──Yes──▶ queue에 대기
         └──────────────────────────┘
                       │ No (queue full)
                       ▼
         ┌──────────────────────────┐
         │ workerCount < maxPool ?  │──Yes──▶ 새 worker 생성 (over-core)
         └──────────────────────────┘
                       │ No
                       ▼
              RejectedExecutionHandler
              (Abort / CallerRuns / Discard / DiscardOldest)
```

### 1.3 Work-Stealing 그림

```
[ForkJoinPool: 각 worker 자기 deque 소유]

  Worker-1                Worker-2               Worker-3 (idle)
  ┌───────┐               ┌───────┐              ┌───────┐
  │  T11  │ ◀── push/pop  │  T21  │              │       │
  │  T12  │     (LIFO,    │  T22  │              │       │
  │  T13  │      head)    │  T23  │              │       │
  │  T14  │               │  T24  │ ◀────────────┤ steal │
  └───────┘               └───────┘              │ (FIFO, │
                                                 │  tail) │
                                                 └───────┘
   own work: head (LIFO)        steal: tail (FIFO)
   → cache locality              → contention 최소화
```

### 1.4 ThreadLocal 그림

```
[Thread 객체 안의 ThreadLocalMap]

  Thread-A                      Thread-B
  ┌────────────────────┐        ┌────────────────────┐
  │ Thread.threadLocals│        │ Thread.threadLocals│
  │ = ThreadLocalMap   │        │ = ThreadLocalMap   │
  │ ┌────────────────┐ │        │ ┌────────────────┐ │
  │ │TL1(weak) → vA1 │ │        │ │TL1(weak) → vB1 │ │
  │ │TL2(weak) → vA2 │ │        │ │TL2(weak) → vB2 │ │
  │ └────────────────┘ │        │ └────────────────┘ │
  └────────────────────┘        └────────────────────┘
  
  - Key는 WeakReference → ThreadLocal 객체 GC되면 key=null
  - Value entry는 hash slot에 그대로 남음 (Map 청소 안 됨)
  - Tomcat thread는 재사용되므로 자동 정리 없음 → remove() 필수
```

### 1.5 Deadlock 그림

```
[순환 대기]

  Thread-1                       Thread-2
  hold:  LockA   ─────┐          hold:  LockB   ─────┐
  wait:  LockB        │          wait:  LockA        │
                      │                              │
                      └──────────────┬───────────────┘
                                     │
                              Circular wait
                              (Lock 순서 다름)
                                     │
                                     ▼
                    jstack: "Found one Java-level deadlock"
```

### 1.6 Virtual Thread 비교

```
[Platform Thread]                 [Virtual Thread]
1 Java Thread = 1 OS Thread       M Virtual : N Carrier
1MB stack (OS)                    ~수KB stack chunk (Heap)
~1만 개 한계                       ~수십만 개 가능
context switch: OS                context switch: JVM scheduler
                                  
                                  carrier (OS, FJP) ─┐
                                                     ├─ Heap stack chunk
                                  VT freeze/thaw ────┘
```

---

## 2. 직관 — 한 줄 비유 + 정의

### 2.1 Thread (Platform Thread)

- **비유**: 공장의 정직원. 책상(stack 1MB)을 차지하고 출퇴근(context switch)에 비용이 든다. 함부로 늘리면 사무실(메모리)이 터진다.
- **정의**: Java `java.lang.Thread` 객체 1개에 OS thread 1개가 1:1로 매핑된 실행 단위. OS scheduler가 실제 CPU 할당.

### 2.2 ExecutorService

- **비유**: 인력 사무소. 일감(Task)을 받아 정직원(worker)에게 배치하고, 모자라면 대기열, 더 모자라면 거절.
- **정의**: Thread 풀과 작업 큐를 추상화한 인터페이스 (`java.util.concurrent.ExecutorService`). `submit()` / `invokeAll()` / `shutdown()` 제공.

### 2.3 ForkJoinPool

- **비유**: 자율 협업 팀. 자기 일감 다 끝낸 사람이 옆 사람 일을 빼앗아 (steal) 도와준다.
- **정의**: 각 worker가 자신의 deque를 소유하고, idle worker가 다른 worker의 deque tail에서 task를 훔치는 work-stealing pool. `compute()`-`fork()`-`join()`으로 재귀 분할 정복.

### 2.4 ThreadLocal

- **비유**: 사물함. 같은 사무실(JVM)에서 일하지만 각자 자기 사물함(thread별 storage)에 짐을 보관. 사람이 퇴근해도 사물함 안 비우면 다음 사람이 들어와 옛 짐을 발견.
- **정의**: 각 Thread의 `ThreadLocalMap`에 `(ThreadLocal key → 값)`로 thread-local 변수를 저장. 풀 환경에서 reuse 시 누수의 단골.

### 2.5 synchronized / Lock

- **비유**: 화장실 한 칸. 한 사람이 들어가면 잠그고, 나오면 풀어준다. `synchronized`는 자동 잠금/해제, `ReentrantLock`은 수동(`unlock()` 책임).
- **정의**: 임계 구역(critical section)을 mutual exclusion으로 보호하는 메커니즘.

### 2.6 Atomic

- **비유**: 원샷 시계. `compareAndSet(old, new)`로 "내가 기억한 값이 그대로면 새 값으로 갈아끼우기" — 한 번의 CPU 명령(CAS)으로 처리.
- **정의**: lock 없이 CAS(Compare-And-Swap)로 원자적 read-modify-write를 보장하는 클래스 (`AtomicInteger`, `AtomicReference`...).

### 2.7 volatile

- **비유**: 게시판. 누가 글 올리면 모두에게 즉시 보인다. 단, **여러 명이 동시에 카운터 += 1**은 보장 안 됨 (그건 Atomic).
- **정의**: visibility 보장 + happens-before 관계 형성. atomicity는 미보장.

### 2.8 CompletableFuture

- **비유**: 약속 어음. "나중에 결과 줄게" 표를 받아두고, "결과 나오면 이것도 해줘(`thenApply`)", "안 되면 이거(`exceptionally`)"로 파이프라인 구성.
- **정의**: 비동기 작업 결과의 promise/future + 콜백 체이닝 API (JDK 8+).

### 2.9 Virtual Thread

- **비유**: 알바생. 정직원(carrier)이 자기 책상을 빌려주고, 알바가 잠깐 쉬는(blocking) 동안 책상에 다른 알바가 앉는다.
- **정의**: JVM scheduler가 carrier OS thread 위에서 다중 실행하는 lightweight thread. blocking I/O 시 freeze/thaw로 carrier 양보. (자세히는 [jvm/05-threading/04-virtual-threads-and-loom.md](../jvm/05-threading/04-virtual-threads-and-loom.md))

---

## 3. 구조 — Thread의 본질과 한계

### 3.1 OS Thread 1:1 매핑 (Platform Thread)

`new Thread(...).start()` 가 호출되면 일어나는 일:

```
Java:    Thread.start()
            ↓
JVM:     Thread::start0() (native)
            ↓
OS:      pthread_create(...) (Linux)
         CreateThread(...)   (Windows)
            ↓
Kernel:  TID 할당, stack 영역 매핑, scheduler 큐에 등록
```

→ Java Thread 1개 = OS Thread 1개. 절대 더 적지도 많지도 않다.

### 3.2 한 Thread의 비용

| 항목 | 크기 / 비용 |
|---|---|
| Stack | 기본 1MB (`-Xss1m`). 32-bit JVM은 320KB |
| TLAB | Eden 안에 thread별 ~수십KB 할당 |
| ThreadLocalMap | 사용 시 해당 thread에 별도 객체 |
| Context switch | OS scheduler, ~수 μs |
| 생성 비용 | pthread_create + JVM 초기화, ~수십~수백 μs |

→ Thread는 **비싸다**. 10만 개 = 100GB stack — 불가능. 그래서 풀로 재사용한다.

### 3.3 한계: 컨테이너 환경의 함정

```
[Production 사고]
ERROR: java.lang.OutOfMemoryError: unable to create native thread
```

원인 후보:
1. **JVM heap이 아님** — OS thread를 못 만든다는 뜻.
2. `ulimit -u` (max user processes) 초과 — 컨테이너의 nproc 제한.
3. `/proc/sys/kernel/pid_max` 초과.
4. `/proc/sys/kernel/threads-max` 초과.
5. memory 자체가 부족해 stack 매핑 실패.

진단:
```bash
# 컨테이너 안에서
cat /proc/sys/kernel/threads-max
ulimit -u
ps -eLf | wc -l    # 현재 thread 수
```

→ "JVM 메모리 늘려도 안 됨" — 시스템 한도가 원인.

### 3.4 Thread Group, Daemon

- **ThreadGroup**: 옛 API (logging/management용). 현대 코드에서는 거의 안 씀.
- **Daemon Thread**: 모든 non-daemon thread가 종료되면 JVM이 강제 종료. GC thread, JIT compile thread가 daemon.
  - `t.setDaemon(true)` 는 `start()` 전에만 가능.
  - 사용자 코드의 worker는 보통 non-daemon으로 두어 shutdown hook이 작동하게 한다.

---

## 4. Thread 생성 방법 — 4가지 + 권장

### 4.1 방법 ①: `new Thread(Runnable)` — 옛 방식, 권장 X

```java
new Thread(() -> doWork()).start();
```

문제점:
- 생성 비용 그대로 노출 (재사용 X).
- 예외 처리 정책 없음.
- 이름/우선순위 관리 직접.
- 종료/취소 메커니즘 없음.

> 시니어 코드에선 거의 안 보인다. 보이면 "왜 풀 안 썼느냐" 묻는다.

### 4.2 방법 ②: `ExecutorService.submit()` — 현대 표준

```java
ExecutorService es = Executors.newFixedThreadPool(8);
Future<Result> f = es.submit(() -> compute());
Result r = f.get();
es.shutdown();
```

장점:
- Thread 재사용.
- `Future`로 결과/예외 받기.
- `shutdown()` / `awaitTermination()` 종료 제어.

### 4.3 방법 ③: `CompletableFuture.supplyAsync()` — 비동기 파이프라인

```java
CompletableFuture<Integer> f = CompletableFuture
    .supplyAsync(() -> fetchUser(id))
    .thenApply(u -> u.score)
    .exceptionally(ex -> 0);
```

특징:
- 기본 executor는 `ForkJoinPool.commonPool()`.
- IO 작업이면 별도 executor 명시 권장: `supplyAsync(task, ioExecutor)`.

### 4.4 방법 ④: Virtual Thread (JDK 21+)

```java
Thread.startVirtualThread(() -> doWork());

// 또는
try (var es = Executors.newVirtualThreadPerTaskExecutor()) {
    es.submit(() -> doWork());
}
```

특징:
- 생성 비용 거의 0 (Heap 객체 + stack chunk).
- I/O blocking 시 carrier에서 unmount → 다른 VT가 사용.
- thread-per-request 패턴 부활.
- 자세히 [jvm/05-threading/04-virtual-threads-and-loom.md](../jvm/05-threading/04-virtual-threads-and-loom.md).

### 4.5 선택 가이드

| 상황 | 선택 |
|---|---|
| 일회성 비동기 (script) | `CompletableFuture.supplyAsync` |
| 서버 worker pool (CPU bound) | `ThreadPoolExecutor` (직접 구성) |
| 분할 정복 (CPU 분산) | `ForkJoinPool` / parallel stream |
| 다수 I/O blocking (HTTP, DB) | Virtual Thread (JDK 21+) |
| 옛날 코드 호환 | `Executors.newFixedThreadPool` |

---

## 5. Thread Lifecycle — `Thread.State`와 jstack

### 5.1 6가지 상태 (Thread.State enum)

```
                ┌─────┐
         new T  │ NEW │
                └──┬──┘
              start()
                   ▼
              ┌──────────┐
              │ RUNNABLE │ ◀───── notify / unpark / sleep timeout
              └────┬─────┘
       ┌───────────┼───────────┬─────────────────┐
       │           │           │                 │
   sync 대기   wait()/park   sleep(t)         run() 종료
       ▼           ▼           ▼                 ▼
   ┌─────────┐ ┌─────────┐ ┌──────────────┐ ┌────────────┐
   │ BLOCKED │ │ WAITING │ │TIMED_WAITING │ │ TERMINATED │
   └─────────┘ └─────────┘ └──────────────┘ └────────────┘
```

### 5.2 상태별 의미 + jstack 출력

| State | 의미 | 만드는 코드 | jstack 출력 |
|---|---|---|---|
| **NEW** | 아직 `start()` 안 함 | `new Thread(r)` | (대부분 보이지 않음) |
| **RUNNABLE** | CPU 받을 자격 (실행 중 or 준비) | 일반 코드 | `java.lang.Thread.State: RUNNABLE` |
| **BLOCKED** | monitor 진입 대기 | `synchronized` 진입 직전 | `BLOCKED (on object monitor)` + `waiting to lock <0x..>` |
| **WAITING** | 무한정 대기 | `Object.wait()`, `LockSupport.park()`, `Thread.join()` | `WAITING (on object monitor)` 또는 `WAITING (parking)` |
| **TIMED_WAITING** | 시간 제한 대기 | `Thread.sleep`, `wait(timeout)`, `future.get(timeout)`, `parkNanos` | `TIMED_WAITING (sleeping/parking)` |
| **TERMINATED** | `run()` 종료 | run 끝 / 예외 | (사라짐) |

### 5.3 ⚠️ Socket.read는 RUNNABLE이다 — 운영자 함정

```
[코드]
InputStream is = socket.getInputStream();
int b = is.read();   // 데이터 올 때까지 blocking

[jstack 출력]
"http-nio-8080-exec-5" #45 daemon prio=5
   java.lang.Thread.State: RUNNABLE
        at sun.nio.ch.Net.poll(Native Method)
        at sun.nio.ch.NioSocketImpl.timedRead(...)
        at sun.nio.ch.NioSocketImpl.implRead(...)
        ...
```

→ **kernel에서 blocking 중인데도 Thread.State는 RUNNABLE**.
→ 이유: `Thread.State` enum은 **Java level monitor 상태**만 반영. native syscall blocking은 RUNNABLE로 보고됨.
→ 운영 함정: "CPU 사용률 0%인데 jstack에 RUNNABLE이 100개" — 실제로는 다 socket read에서 자고 있는 것. **CPU bound 오판 금지**.

진단법:
- `RUNNABLE` + stack top이 `Net.poll`, `socketRead0`, `epollWait` → I/O wait.
- `RUNNABLE` + stack top이 사용자 메서드 → 진짜 CPU 사용 중.
- 더 정확히 보려면 async-profiler **wallclock mode** (`-e wall`).

### 5.4 BLOCKED vs WAITING 차이

```
BLOCKED:
    synchronized (lockObj) { ... }
    └── lockObj의 monitor가 이미 다른 thread에 점유됨
    → "다른 사람이 화장실에 있어서 문 앞에서 기다림"

WAITING:
    lockObj.wait();   // synchronized 안에서
    └── 이미 lock은 release하고, 누가 notify 해주길 기다림
    → "내가 잠깐 자리 비우니 깨워줘"
```

→ BLOCKED 군집이 보이면 **lock contention**, WAITING 군집은 **producer 부족** 또는 condition variable 대기.

---

## 6. ExecutorService 종류 — `Executors.*` 분해

### 6.1 5가지 factory + 직접 구성

```
Executors.newFixedThreadPool(N)
  = ThreadPoolExecutor(N, N, 0, MILLISECONDS, new LinkedBlockingQueue<>())
                                              ↑
                                       무제한 큐 (Integer.MAX_VALUE)
                                       → task 폭주 시 OOM

Executors.newCachedThreadPool()
  = ThreadPoolExecutor(0, Integer.MAX_VALUE, 60s, new SynchronousQueue<>())
                          ↑
                   무제한 thread
                   → request 폭주 시 thread 폭주 → OOM "unable to create native thread"

Executors.newSingleThreadExecutor()
  = ThreadPoolExecutor(1, 1, 0, new LinkedBlockingQueue<>())
                                  ↑
                            순서 보장 (단일 thread)
                            큐 무제한 — 동일하게 OOM 위험

Executors.newScheduledThreadPool(N)
  = ScheduledThreadPoolExecutor(N)
                                  ↑
                       지연 실행 / 주기 실행
                       DelayedWorkQueue 사용
                       cf. Timer 클래스는 deprecated 권장

Executors.newWorkStealingPool()  // JDK 8+
  = ForkJoinPool(parallelism)
                   ↑
            CPU 코어 수 기본
            work-stealing 적용
```

### 6.2 왜 `Executors.*` 대신 `ThreadPoolExecutor` 직접 구성하나 (Goetz)

Brian Goetz "Java Concurrency in Practice" 이래 공식 권장:

```java
ThreadPoolExecutor pool = new ThreadPoolExecutor(
    /* corePoolSize  */ 8,
    /* maxPoolSize   */ 32,
    /* keepAliveTime */ 60, TimeUnit.SECONDS,
    /* workQueue     */ new ArrayBlockingQueue<>(200),   // ← 유한 큐!
    /* threadFactory */ new NamedThreadFactory("worker"),
    /* handler       */ new ThreadPoolExecutor.CallerRunsPolicy()  // ← 명시
);
```

이유:
1. **큐 크기를 유한하게** 명시 → OOM 방지.
2. **RejectedExecutionHandler** 명시 → 폭주 시 정책 결정.
3. **ThreadFactory** 명시 → thread 이름 (jstack 분석 가능), uncaughtExceptionHandler 지정.
4. `Executors.*`는 큐 무제한 / thread 무제한 중 하나의 함정이 있다.

### 6.3 ThreadPoolExecutor 내부 동작

```
submit(task)
   │
   ├── 1) workerCount < corePoolSize  → 새 core worker 생성
   │       (core thread는 idle여도 유지)
   │
   ├── 2) workerCount >= corePoolSize → workQueue.offer(task)
   │       성공 → 큐에 대기
   │
   ├── 3) queue 가득 + workerCount < maxPoolSize → 새 worker 생성 (over-core)
   │       (over-core thread는 keepAliveTime idle 후 종료)
   │
   └── 4) 다 실패 → RejectedExecutionHandler 호출
```

### 6.4 RejectedExecutionHandler 4종

| 정책 | 동작 | 사용처 |
|---|---|---|
| **AbortPolicy** (default) | `RejectedExecutionException` 던짐 | 명시적 backpressure 신호 |
| **CallerRunsPolicy** | submit 호출한 thread가 직접 실행 | 자연스러운 throttling (Tomcat 추천) |
| **DiscardPolicy** | 조용히 버림 | log 같은 비필수 |
| **DiscardOldestPolicy** | 큐 head 버리고 다시 시도 | 최신 우선 (실시간) |

→ production에서 **CallerRunsPolicy**가 자주 쓰임. submit하던 thread가 잠시 일을 떠맡아 자연스럽게 인입 속도를 늦춤.

### 6.5 큐 4종의 의미

| 큐 | 특성 | 효과 |
|---|---|---|
| **SynchronousQueue** | 용량 0, hand-off | 들어오는 즉시 worker에 전달, 없으면 즉시 새 worker (→ cachedThreadPool) |
| **LinkedBlockingQueue (무제한)** | Integer.MAX | fixed pool의 디폴트, **OOM 위험** |
| **LinkedBlockingQueue (제한)** | 명시 용량 | backpressure |
| **ArrayBlockingQueue** | 고정 배열 | 약간 더 빠름, 명시 용량 |
| **PriorityBlockingQueue** | 우선순위 힙 | task에 우선순위 |

---

## 7. Tomcat의 변종 ThreadPool ⭐

표준 `ThreadPoolExecutor`는 "core 차면 queue, queue 차면 maxPool" 순서지만, Tomcat의 `org.apache.tomcat.util.threads.TaskQueue` + `ThreadPoolExecutor`는 다르다.

### 7.1 Tomcat 정책: thread 먼저 늘리고 queue 사용

```
표준 정책:                          Tomcat 정책:
1. core 가득?                       1. core 가득?
2. queue에 넣기 (가능하면)            2. maxPool까지 thread 늘리기
3. 큐 full → max까지 thread           3. 그래도 안 되면 queue (LinkedBlockingQueue)
4. 다 full → reject                  4. queue도 full → reject
```

구현: `TaskQueue.offer()` 가 `parent.getPoolSize() < parent.getMaximumPoolSize()` 일 때 일부러 `false`를 반환 → ThreadPoolExecutor가 "큐 full"로 인식 → maxPool까지 thread 늘림.

### 7.2 왜 이렇게 — request latency 우선

```
[표준 정책 효과]
요청이 적당히 오면 → core만 사용. 나머지는 큐 대기 → latency↑
요청이 폭주하면 → 큐 가득 → max로 늘어남

[Tomcat 정책 효과]
요청이 오면 → 가능한 한 즉시 새 thread 생성 → latency↓
maxPool 다 차면 → 그때 큐
```

Tomcat은 **request latency 우선** 서버라 thread 생성을 적극적으로 한다.

자세한 내부는 [network-request-lifecycle/06-tomcat-internals.md](../network-request-lifecycle/06-tomcat-internals.md).

---

## 8. ForkJoinPool과 Work-Stealing ⭐

### 8.1 핵심 아이디어

```
[일반 ThreadPool]                  [ForkJoinPool]
       ┌────────────┐                Worker-1: own deque
       │  shared    │                Worker-2: own deque
       │  queue     │                ...
       └────────────┘                  ↑ worker가 idle이면
       ▲ ▲ ▲ ▲                          다른 worker의 deque tail에서 steal
       │ │ │ │ contention!
      W W W W
      
      모든 worker가 한 큐에 push/pop  vs   각자 deque + steal (lock-free, cache-locality)
```

### 8.2 ForkJoinTask 사용 패턴

```java
class Sum extends RecursiveTask<Long> {
    final long[] arr; final int lo, hi;
    Sum(long[] arr, int lo, int hi) { ... }
    protected Long compute() {
        if (hi - lo <= THRESHOLD) {
            // base case: 직접 계산
            long s = 0; for (int i=lo; i<hi; i++) s += arr[i]; return s;
        }
        int mid = (lo + hi) / 2;
        Sum left  = new Sum(arr, lo, mid);
        Sum right = new Sum(arr, mid, hi);
        left.fork();              // 새 task로 submit (자기 deque에 push)
        long r = right.compute(); // 직접 처리
        long l = left.join();     // 기다림
        return l + r;
    }
}
ForkJoinPool.commonPool().invoke(new Sum(arr, 0, arr.length));
```

### 8.3 Deque 동작 — LIFO push/pop on own, FIFO steal

```
[Worker-1의 deque]
   head ─────────────── tail
    ↑                    ↑
    own push/pop         steal from other workers
    (LIFO)               (FIFO)
```

왜:
- **own LIFO**: 방금 생성한 task가 가장 hot한 cache 상태 → cache locality.
- **steal FIFO**: 가장 오래된 task = 가장 큰 task일 가능성 (재귀 분할이므로 깊은 task가 작음, 큰 task가 root 가까이) → load balancing 효과.

### 8.4 `commonPool` — parallel stream의 기반

```java
list.parallelStream().map(...).reduce(...);
   // 내부적으로 ForkJoinPool.commonPool() 사용

ForkJoinPool.commonPool().getParallelism();
   // 기본 = Runtime.getRuntime().availableProcessors() - 1
```

⚠️ 함정:
- `commonPool`은 **JVM 전체가 공유** — 한 곳에서 잡으면 다른 라이브러리도 영향.
- I/O blocking task를 commonPool에 던지면 starvation. parallel stream에 HTTP 호출 같은 거 넣지 말 것.

### 8.5 ManagedBlocker — blocking task를 안전하게

```java
ForkJoinPool.managedBlock(new ForkJoinPool.ManagedBlocker() {
    public boolean block() { /* 실제 blocking 작업 */ return true; }
    public boolean isReleasable() { return done; }
});
```

→ FJP가 "이 worker는 잠시 blocking이니 다른 worker를 더 생성하라"를 인지. parallel stream에 어쩔 수 없이 blocking이 들어가야 한다면 ManagedBlocker로 감싼다.

---

## 9. ThreadLocal — 본질과 누수 ⭐⭐

### 9.1 본질: thread별 storage

```java
static ThreadLocal<SimpleDateFormat> TL =
    ThreadLocal.withInitial(() -> new SimpleDateFormat("yyyy-MM-dd"));

String s = TL.get().format(new Date());
```

내부:
```
Thread t = Thread.currentThread();
t.threadLocals : Thread.ThreadLocalMap
                  Entry[] table — open-addressing hash map
                  Entry(WeakReference<ThreadLocal>, Object value)
```

→ 각 Thread 객체 안에 `ThreadLocalMap`이 있고, key는 `ThreadLocal` 인스턴스, value는 thread별 값.

### 9.2 주요 사용처

| 사용처 | 이유 |
|---|---|
| `SimpleDateFormat` thread-safety | DateFormat이 mutable → thread별 인스턴스 |
| MDC (logback) | 요청 trace ID를 thread-local에 — log pattern `%X{traceId}` |
| Spring SecurityContext | 요청자 정보를 thread-local에 |
| Hibernate Session | per-request session |
| TransactionSynchronizationManager | per-thread transaction state |

### 9.3 ⚠️ 누수 패턴 1: Tomcat 풀에서 thread 재사용

```
[흐름]
Request 1 → Thread-A 잡음 → TL.set("user-A-info")
            → 응답 후 thread는 풀로 복귀
            → ThreadLocal 정리 안 함
Request 2 → Thread-A 재배정 → TL.get() → "user-A-info" 반환!  ← 누수
```

→ 다른 요청자의 정보가 흘러나옴. Security 사고.

**대응**:
```java
try {
    SecurityContext.set(currentUser);
    return chain.proceed();
} finally {
    SecurityContext.remove();   // ← 필수
}
```

Spring의 `SecurityContextPersistenceFilter` 등도 finally에서 `clearContext()`.

### 9.4 ⚠️ 누수 패턴 2: WeakReference + Entry table

```
[ThreadLocalMap entry]
key   = WeakReference<ThreadLocal>
value = Object (strong)

[ThreadLocal 객체가 GC됨]
key.get() == null  ← weak ref은 GC됨
value는 hash slot에 그대로 남아있음

→ ThreadLocalMap.set()이 호출될 때 stale entry 정리되지만,
  추가 set/get이 없으면 영원히 남음
→ webapp redeploy 시 ClassLoader 누수의 원인
  (값이 옛 ClassLoader의 클래스 instance)
```

→ Tomcat이 webapp undeploy 시 "WebappClassLoader leak" warning을 자주 띄우는 원인 중 하나.

**대응**:
- 명시적 `remove()` 호출.
- ThreadLocal을 `static final` 단 하나만 두기 (인스턴스마다 만들지 말기).
- `InheritableThreadLocal` 신중히 사용.

### 9.5 `InheritableThreadLocal` 함정

```java
static InheritableThreadLocal<String> CTX = new InheritableThreadLocal<>();
CTX.set("parent-context");
new Thread(() -> CTX.get()).start();   // → "parent-context" 받음
```

→ child thread 생성 시점에 부모의 값을 **얕은 복사**.

함정:
- `ExecutorService`로 제출한 task는 이미 풀에 있는 thread → 새 thread 생성이 아님 → **상속 안 됨**.
- ForkJoinPool worker는 풀 시작 시 한 번만 상속.

→ MDC를 자식 thread에 전달하려면 보통 **수동 전달** (decorator로 task wrap).

---

## 10. synchronized vs ReentrantLock vs ReadWriteLock vs StampedLock

### 10.1 synchronized — 언어 기능

```java
synchronized (lockObj) {
    // critical section
}
```

장점:
- 자동 release (예외 발생해도).
- JVM 최적화 (biased / lightweight / heavyweight 승격, [jvm/05-threading/03](../jvm/05-threading/03-synchronized-and-mark-word.md)).
- 코드 간결.

단점:
- timeout 못 줌.
- interruptible 아님 (Thread.interrupt() 무시).
- Condition 1개만 (`wait`/`notify`).
- fairness 옵션 없음.

### 10.2 ReentrantLock — API 기반 lock

```java
private final ReentrantLock lock = new ReentrantLock();
lock.lock();
try {
    // critical section
} finally {
    lock.unlock();   // ← finally 필수
}
```

장점:
- `tryLock(timeout)` — timeout 가능.
- `lockInterruptibly()` — interrupt 가능.
- `new ReentrantLock(true)` — fairness (옛 waiter 우선) — 단 throughput↓.
- Condition 여러 개 (`newCondition()`).

단점:
- 수동 unlock — 빠뜨리면 영구 lock.
- JVM 최적화 덜 받음.

### 10.3 ReadWriteLock — read 동시 허용

```java
ReadWriteLock rw = new ReentrantReadWriteLock();
rw.readLock().lock();    // 여러 reader 동시 가능
rw.writeLock().lock();   // writer는 단독
```

→ read-heavy 자료구조 (cache, config). 단, writer가 starvation 위험.

### 10.4 StampedLock (JDK 8) — optimistic read

```java
StampedLock sl = new StampedLock();
long stamp = sl.tryOptimisticRead();
int v = state;                       // lock 없이 read
if (!sl.validate(stamp)) {           // write가 끼었는지 검사
    stamp = sl.readLock();
    try { v = state; } finally { sl.unlockRead(stamp); }
}
```

→ 가장 빠른 read (lock 안 잡음). 단 reentrant 아님, Condition 없음. 신중히.

### 10.5 선택 가이드

| 상황 | 선택 |
|---|---|
| 간단한 mutex | `synchronized` |
| timeout, interrupt 필요 | `ReentrantLock` |
| read >> write | `ReadWriteLock` |
| 매우 짧은 read + 매우 가끔 write | `StampedLock` |
| 여러 Condition (producer/consumer 분리) | `ReentrantLock + Condition` |

---

## 11. Atomic 클래스 — CAS 기반

(JVM 내부 CAS 메커니즘은 [jvm/05-threading/02-memory-barriers.md](../jvm/05-threading/02-memory-barriers.md) 참조)

### 11.1 종류

```
AtomicInteger / AtomicLong / AtomicBoolean
AtomicReference<T>
AtomicReferenceArray<T>
AtomicIntegerArray
AtomicIntegerFieldUpdater (reflection 기반)

LongAdder / DoubleAdder           ← JDK 8
LongAccumulator                    ← JDK 8

AtomicStampedReference<T>          ← ABA 문제 해결
AtomicMarkableReference<T>
```

### 11.2 사용 패턴

```java
AtomicInteger counter = new AtomicInteger(0);
counter.incrementAndGet();        // atomic ++
counter.compareAndSet(5, 10);     // 5면 10으로 교체
counter.updateAndGet(v -> v * 2); // lambda 적용 (내부 CAS loop)
```

### 11.3 LongAdder vs AtomicLong — high contention 시

```
[AtomicLong]                       [LongAdder]
모든 thread가 같은 long에 CAS       각 thread가 자기 cell에 +=
   → high contention에 CAS 실패↑     → cell 충돌 적음
                                    sum() 시 모든 cell 합산
                                    
처리량:                              처리량:
~1억/s까지 OK                        ~10억/s 가능
그 이상 contention → 급락             가산은 빠름, 정확한 sum이 가끔 비쌈
```

→ **카운터/메트릭은 LongAdder**, **정확한 순서가 필요한 ID 생성은 AtomicLong**.

### 11.4 ABA 문제

```
[시나리오]
1) Thread-1: x를 읽음 → A
2) Thread-2: x를 B로 바꿈
3) Thread-2: x를 다시 A로 바꿈
4) Thread-1: compareAndSet(A, ...) → 성공!
   "내가 봤을 때부터 안 바뀌었다고 착각"
```

해결:
```java
AtomicStampedReference<Node> ref = new AtomicStampedReference<>(node, 0);
ref.compareAndSet(expectedRef, newRef, expectedStamp, newStamp);
// stamp(버전 카운터)도 함께 검증
```

→ lock-free stack/queue 구현 시 필수.

---

## 12. volatile — visibility, 단 atomic 아님

### 12.1 보장 / 미보장

| 보장 | 미보장 |
|---|---|
| 다른 thread가 즉시 본다 (visibility) | `i++` 같은 read-modify-write atomicity |
| happens-before 형성 (write→read) | 복합 연산 |
| reordering 차단 (memory barrier) | |

### 12.2 happens-before 메커니즘

```
[Thread 1]                     [Thread 2]
x = 1;                         while (!ready) {}
ready = true;   // volatile    int v = x;       // ready=true 보면 x=1 보장
```

JMM 규칙: volatile write → volatile read는 happens-before. write 이전의 모든 메모리 효과가 read 이후 코드에서 보인다.

JVM 내부적으로 volatile write 뒤 `StoreLoad` barrier 삽입, read 앞 `LoadLoad/LoadStore` 삽입. (자세히 [jvm/05-threading/02](../jvm/05-threading/02-memory-barriers.md))

### 12.3 함정: volatile 배열의 element

```java
volatile int[] arr = new int[10];
arr[0] = 5;        // ← 이건 element write. volatile 안 됨!
```

→ 배열 참조 자체는 volatile이지만 element는 아님. `AtomicIntegerArray` 사용.

### 12.4 함정: 64bit long/double의 non-atomic write

JLS 17.7: long/double의 read/write는 32bit JVM에서 non-atomic 허용. → 두 thread가 동시에 write 하면 high/low 32bit가 섞일 수 있다.

→ `volatile long` / `volatile double` 또는 `AtomicLong` 사용. (64bit JVM은 거의 다 atomic 보장.)

---

## 13. Thread Communication — wait/notify, Condition, BlockingQueue, 동기화기

### 13.1 wait / notify (legacy)

```java
synchronized (q) {
    while (q.isEmpty()) q.wait();   // ← while loop 필수 (spurious wakeup)
    return q.poll();
}
// producer
synchronized (q) {
    q.add(x);
    q.notifyAll();
}
```

함정:
- `if (q.isEmpty()) q.wait()` 은 잘못. spurious wakeup 가능.
- `notify()` vs `notifyAll()`: 하나만 깨우려면 `notify`, 안전하게는 `notifyAll`.
- `wait`은 반드시 synchronized 안에서.

### 13.2 Condition (현대)

```java
ReentrantLock lock = new ReentrantLock();
Condition notEmpty = lock.newCondition();
Condition notFull  = lock.newCondition();

lock.lock();
try {
    while (q.isFull()) notFull.await();   // 분리된 condition
    q.add(x);
    notEmpty.signalAll();
} finally { lock.unlock(); }
```

→ Producer와 Consumer를 다른 Condition으로 분리 → 불필요한 wakeup 줄임.

### 13.3 BlockingQueue — producer/consumer의 정답

```java
BlockingQueue<Task> q = new LinkedBlockingQueue<>(1000);
// producer
q.put(task);            // 큐 가득이면 block
// consumer
Task t = q.take();      // 큐 비면 block
```

종류:
| 큐 | 특성 |
|---|---|
| `LinkedBlockingQueue` | 무제한(기본) 또는 제한, linked list |
| `ArrayBlockingQueue` | 고정 배열 |
| `SynchronousQueue` | 용량 0, hand-off |
| `LinkedTransferQueue` | hand-off 시도 + fallback to queue |
| `PriorityBlockingQueue` | heap |
| `DelayQueue` | 시간 도달한 element만 take |

### 13.4 동기화기 (synchronizers)

| 동기화기 | 의미 | 예 |
|---|---|---|
| **CountDownLatch** | N번 countDown 후 await 해제 | 초기화 완료 신호 |
| **CyclicBarrier** | N개 thread가 도달하면 같이 통과, 재사용 가능 | phase 동기화 |
| **Semaphore** | N개 permit, 동시 접근 N개로 제한 | rate limit, connection pool |
| **Phaser** | 여러 단계의 barrier, 동적 가입/탈퇴 | 복잡한 phase 작업 |
| **Exchanger** | 두 thread가 값 교환 | producer/consumer 한 쌍 |

---

## 14. CompletableFuture (JDK 8+) — 비동기 파이프라인

### 14.1 핵심 메서드

```java
CompletableFuture.supplyAsync(() -> fetchUser(id))     // 비동기 시작
    .thenApply(u -> u.name)                            // 동기 변환
    .thenApplyAsync(name -> enrich(name), ioExec)      // 비동기 변환
    .thenCompose(name -> CompletableFuture.supplyAsync(() -> lookup(name)))  // flatMap
    .thenCombine(other, (a, b) -> a + b)               // 두 결과 결합
    .exceptionally(ex -> "default")                    // 예외 복구
    .whenComplete((v, ex) -> log(v, ex))               // tap (finally)
    .orTimeout(5, TimeUnit.SECONDS);                   // 타임아웃 (JDK 9+)

CompletableFuture.allOf(f1, f2, f3).join();    // 모두 완료 대기
CompletableFuture.anyOf(f1, f2, f3).join();    // 아무거나 먼저
```

### 14.2 기본 executor — `ForkJoinPool.commonPool()` 함정

```java
CompletableFuture.supplyAsync(() -> {
    return httpClient.get("...");  // ← blocking I/O를 commonPool에!
});
```

→ commonPool은 CPU 코어 수만큼만 worker. blocking을 던지면 parallel stream도 같이 starvation.

**해결**: 명시적 executor 지정.
```java
ExecutorService ioExec = Executors.newFixedThreadPool(50);
CompletableFuture.supplyAsync(() -> httpClient.get("..."), ioExec);
```

### 14.3 `get()` deadlock 함정

```java
// ❌ 함정
CompletableFuture<X> f = ...;
X x = f.get();   // 현재 thread가 commonPool worker라면, 자기 자신을 기다림 → deadlock 가능
```

→ chain 안에서 `get()`/`join()` 호출 피하기. 끝에서만 호출.

### 14.4 `thenApply` vs `thenApplyAsync`

| 메서드 | 실행 위치 |
|---|---|
| `thenApply` | **호출한 thread** (즉, 이전 stage 완료시킨 thread) |
| `thenApplyAsync` (no executor) | `commonPool` |
| `thenApplyAsync(fn, exec)` | 지정한 executor |

→ 무거운 작업이면 무조건 `Async` + 명시 executor.

---

## 15. Race Condition 패턴 — 4가지 단골

### 15.1 Check-then-act

```java
// ❌
if (!map.containsKey(k)) {
    map.put(k, compute(k));   // 두 thread가 동시에 들어와 둘 다 put
}

// ✅
map.computeIfAbsent(k, this::compute);   // ConcurrentHashMap이 atomic 보장
```

### 15.2 Read-modify-write

```java
// ❌
counter++;   // = read + add + write 3단계

// ✅
counter.incrementAndGet();   // AtomicInteger
counter.add(1);              // LongAdder
```

### 15.3 Lazy init — Double-checked locking 함정

```java
// ❌ JDK 5 이전, 또는 volatile 없으면 깨짐
private Singleton instance;
public Singleton get() {
    if (instance == null) {
        synchronized (this) {
            if (instance == null) instance = new Singleton();
        }
    }
    return instance;
}
```

문제: `new Singleton()`이 1) 메모리 할당, 2) 생성자 실행, 3) instance 변수에 할당 — 이 3단계가 reorder 가능. 다른 thread가 partial-init 객체를 봄.

```java
// ✅ JDK 5+ volatile로 해결
private volatile Singleton instance;
```

또는 더 간단히:
```java
// ✅ Holder idiom (가장 권장)
private static class Holder { static final Singleton INSTANCE = new Singleton(); }
public static Singleton get() { return Holder.INSTANCE; }
```

→ 클래스 초기화는 JVM이 thread-safe하게 보장하므로 lock 불필요.

### 15.4 Iteration during modification

```java
// ❌
List<X> list = new ArrayList<>();
for (X x : list) {       // ConcurrentModificationException 가능
    if (cond) list.remove(x);
}

// ✅ Iterator.remove() 또는 removeIf
list.removeIf(x -> cond);

// ✅ 동시 iteration
ConcurrentHashMap<K, V> map = ...;
for (var e : map.entrySet()) { ... }  // weakly consistent — 예외 안 던짐
```

`ConcurrentHashMap`/`CopyOnWriteArrayList`의 iterator는 **weakly consistent**: 시작 시점의 snapshot 비슷한 뷰를 제공, 예외 안 던짐.

---

## 16. Deadlock과 진단

### 16.1 Deadlock 4 필요조건 (Coffman conditions)

1. **Mutual exclusion** — 자원이 한 번에 한 thread.
2. **Hold and wait** — 이미 잡은 채로 추가 자원 대기.
3. **No preemption** — OS가 강제로 뺏지 않음.
4. **Circular wait** — A→B→A 형태의 순환.

→ 4개 중 하나만 깨면 deadlock 없음. 보통 **circular wait**을 깬다 (lock 순서 강제).

### 16.2 전형적 예시

```java
synchronized (lockA) {
    synchronized (lockB) { ... }
}

// 다른 thread
synchronized (lockB) {
    synchronized (lockA) { ... }    // ← 반대 순서
}
```

### 16.3 jstack 출력

```
Found one Java-level deadlock:
=============================
"Thread-1":
  waiting to lock monitor 0x00007f88c0001234 (object 0x000000076ab8e7f8, a java.lang.Object),
  which is held by "Thread-2"
"Thread-2":
  waiting to lock monitor 0x00007f88c0005678 (object 0x000000076ab8e810, a java.lang.Object),
  which is held by "Thread-1"

Java stack information for the threads listed above:
===================================================
"Thread-1":
    at com.foo.App.doWork(App.java:42)
    - waiting to lock <0x000000076ab8e7f8>
    - locked <0x000000076ab8e810>
"Thread-2":
    ...
```

→ "Found one Java-level deadlock" 메시지가 직접 보인다. JVM이 wait-for 그래프 분석.

### 16.4 ThreadMXBean으로 프로그램 안에서 감지

```java
ThreadMXBean tmx = ManagementFactory.getThreadMXBean();
long[] ids = tmx.findDeadlockedThreads();
if (ids != null) {
    ThreadInfo[] infos = tmx.getThreadInfo(ids);
    // 알림 / 로깅
}
```

→ health check endpoint에 통합 가능.

### 16.5 예방

1. **Lock 순서 강제** — 항상 같은 순서로 acquire.
2. **`tryLock(timeout)`** — 못 잡으면 포기.
3. **Lock 잡은 시간 최소화** — 외부 호출(I/O, callback) 절대 lock 안에서 X.
4. **고수준 동시성 도구 사용** — `ConcurrentHashMap`, `BlockingQueue` 등.

---

## 17. Virtual Thread (JDK 21+) — 짧게 (자세히는 cross-link)

### 17.1 사용법

```java
// 1) 일회성
Thread.startVirtualThread(() -> doWork());

// 2) Executor
try (var es = Executors.newVirtualThreadPerTaskExecutor()) {
    for (var req : requests) es.submit(() -> handle(req));
}

// 3) Thread.Builder
Thread.ofVirtual().name("vt-", 0).start(() -> ...);
```

### 17.2 핵심 차이

```
[Platform Thread]                  [Virtual Thread]
- 1:1 OS thread                    - M:N (carrier 위에서)
- Stack 1MB                        - Stack chunk in Heap (~수 KB)
- ~수만 개 한계                     - ~수십만 개 가능
- blocking I/O = OS thread 점거    - blocking I/O = freeze, carrier 양보
- ThreadLocal 값 ~수만             - 수십만 × ThreadLocal = 메모리 부담
```

### 17.3 Pinning 함정

```java
synchronized (obj) {
    httpClient.get(url);   // ← blocking I/O가 synchronized 안에서
}
```

→ JDK 21~23에서는 carrier가 **pinned**되어 다른 VT를 carry 못 함. 결국 platform thread 1:1로 회귀.

JDK 24+에서 synchronized pinning은 해소됨. JNI native call은 여전히 pin.

진단:
```bash
-Djdk.tracePinnedThreads=full
```

### 17.4 ScopedValue (preview) — ThreadLocal 대체

```java
static final ScopedValue<User> USER = ScopedValue.newInstance();

ScopedValue.where(USER, currentUser).run(() -> {
    handle();   // 이 안에서 USER.get() 가능
});             // 자동 해제 — try-finally 불필요
```

→ 수십만 VT에 ThreadLocal 쓰면 메모리 부담. ScopedValue는 immutable + scope 한정 → VT에 친화적.

자세한 내용은 [jvm/05-threading/04-virtual-threads-and-loom.md](../jvm/05-threading/04-virtual-threads-and-loom.md).

---

## 18. 측정·진단 도구 ⭐

### 18.1 `jstack` — Thread dump의 기본기

```bash
jstack <pid>                    # 일반
jstack -l <pid>                 # lock 정보 포함 (synchronized + j.u.c.Lock)
jcmd <pid> Thread.print         # 같은 출력 (jcmd 권장)
kill -3 <pid>                   # SIGQUIT — stdout에 dump
```

### 18.2 Thread name convention (운영 시 식별)

| 이름 패턴 | 출처 |
|---|---|
| `main` | main thread |
| `Thread-N` | 이름 안 준 thread (피해야) |
| `http-nio-8080-exec-N` | Tomcat NIO connector worker |
| `http-nio-8080-Acceptor` | Tomcat acceptor |
| `HikariPool-1-housekeeper` | HikariCP housekeeper |
| `HikariPool-1-Connection-Adder` | HikariCP add thread |
| `ForkJoinPool.commonPool-worker-N` | FJP common pool |
| `pool-N-thread-M` | 이름 안 준 ThreadPoolExecutor |
| `Reference Handler`, `Finalizer` | GC 관련 |
| `C1 CompilerThread`, `C2 CompilerThread` | JIT |
| `G1 Young RemSet Sampling` 등 | GC worker |
| `VM Thread`, `VM Periodic Task Thread` | JVM 내부 |

→ ThreadFactory로 의미있는 이름 주는 것이 시니어 코드.

```java
ThreadFactory tf = r -> {
    Thread t = new Thread(r, "order-worker-" + counter.incrementAndGet());
    t.setUncaughtExceptionHandler(...);
    return t;
};
```

### 18.3 Thread dump 분석 패턴

#### 패턴 1: 같은 stack이 여러 thread에 → hot path

```
"http-nio-8080-exec-1" RUNNABLE
   at com.foo.UserService.findById(UserService.java:42)
   ...
"http-nio-8080-exec-2" RUNNABLE
   at com.foo.UserService.findById(UserService.java:42)
   ...
(60개 thread가 같은 위치)
```

→ `UserService.findById` 가 hot path. 성능 문제의 진원지일 수 있음.

#### 패턴 2: BLOCKED 군집 → lock contention

```
"worker-3" BLOCKED on <0x...> owned by "worker-1"
"worker-4" BLOCKED on <0x...> owned by "worker-1"
"worker-5" BLOCKED on <0x...> owned by "worker-1"
```

→ worker-1이 잡은 lock을 모두가 기다림. lock 범위 축소 필요.

#### 패턴 3: WAITING on parking → 풀 idle / starvation 모두 가능

```
"worker-1" WAITING (parking)
   at jdk.internal.misc.Unsafe.park
   at LockSupport.park
   at AbstractQueuedSynchronizer.acquire
   at LinkedBlockingQueue.take
```

→ task 없어서 worker가 대기 중. 정상 idle.

```
"FJP-1-worker-3" WAITING (parking)
   at LockSupport.parkNanos
   at ForkJoinPool.awaitJoin
```

→ FJP에서 join 대기. 다른 worker가 처리 중이면 정상.

#### 패턴 4: TIMED_WAITING 군집 with HTTP stack → upstream 느림

```
"http-nio-exec-N" TIMED_WAITING
   at sun.nio.ch.NioSocketImpl.timedRead
   ...
   at org.apache.http.impl.io.AbstractMessageParser.parse
   ...
   at com.foo.RemoteApiClient.call
```

→ upstream API가 느림. 모든 worker가 같은 외부 호출에서 자고 있음.

### 18.4 JFR (Java Flight Recorder) thread events

```
jdk.JavaMonitorEnter          synchronized 진입 — duration
jdk.JavaMonitorWait           wait() — duration
jdk.JavaErrorThrow            예외 발생
jdk.ThreadStart / ThreadEnd   thread 라이프사이클
jdk.ThreadPark                LockSupport.park duration
jdk.ThreadSleep               Thread.sleep
jdk.ThreadDump                주기적 dump (저비용)
```

threshold 설정 (기본 10ms 이상만 기록):
```bash
jcmd <pid> JFR.start name=app duration=60s settings=profile
```

JMC에서 "Lock Instances" 뷰로 hottest contended lock 확인.

### 18.5 async-profiler — wallclock mode

```bash
# CPU profile
asprof -d 30 -f cpu.html <pid>

# Wall-clock (blocking 포함)
asprof -d 30 -e wall -f wall.html <pid>

# Lock profile
asprof -d 30 -e lock -f lock.html <pid>
```

→ `-e wall`이 핵심. CPU profile은 RUNNABLE만 보지만 wallclock은 BLOCKED/WAITING도 시간 비례로 보임. **"왜 latency 길까?"** 답을 찾는 1순위.

### 18.6 `ThreadMXBean` 프로그램 안 조회

```java
ThreadMXBean tmx = ManagementFactory.getThreadMXBean();
int n = tmx.getThreadCount();                  // 현재 thread 수
int peak = tmx.getPeakThreadCount();           // 피크
long[] deadlocked = tmx.findDeadlockedThreads();
long cpuTime = tmx.getThreadCpuTime(tid);
ThreadInfo[] infos = tmx.dumpAllThreads(true, true);
```

→ Prometheus exporter / Spring actuator에 노출.

---

## 19. 운영 시나리오 ⭐

### 19.1 시나리오 1: Thread leak

**증상**: `Thread.activeCount()` 또는 `jvm_threads_live_threads` 메트릭이 계속 증가. 결국 OOM "unable to create native thread".

**원인 후보**:
1. `ExecutorService.shutdown()` 호출 안 함 — 매 요청마다 `Executors.newFixedThreadPool()` 만들고 안 닫음.
2. ScheduledExecutorService에 schedule 등록 후 cancel 안 함.
3. `new Thread(...).start()` 를 무한 루프에서 호출.
4. third-party library의 background thread (Kafka consumer, OkHttp dispatcher 등) 정리 안 됨.

**진단**:
- `jstack`으로 thread name 패턴 보기 → 어떤 풀이 늘어나나.
- `peak vs current` 비교.

**대응**:
- ExecutorService는 항상 try-with-resources(JDK 19+) 또는 명시적 shutdown.
- shutdown hook으로 graceful close.
- 메트릭으로 threadCount 모니터링.

### 19.2 시나리오 2: Deadlock

**증상**: 응답 안 함, 일부 요청만 hang. CPU 사용률 정상(낮음).

**진단**:
```bash
jstack -l <pid> | grep -A2 "Java-level deadlock"
```

또는:
```java
long[] ids = ManagementFactory.getThreadMXBean().findDeadlockedThreads();
```

**대응**: 즉시 — 둘 중 한 thread interrupt 또는 재시작. 항구적 — lock 순서 강제, tryLock(timeout).

### 19.3 시나리오 3: Thread starvation in ForkJoinPool

**증상**: parallel stream이 멈춤, commonPool worker가 다 blocking에 빠짐.

**전형적 코드**:
```java
list.parallelStream().forEach(item -> {
    httpClient.get(item.url);   // ❌ blocking I/O를 commonPool에
});
```

**대응**:
- 별도 executor 사용. `parallelStream` 대신 `CompletableFuture + ioExecutor`.
- 어쩔 수 없으면 `ForkJoinPool.managedBlock`.
- 또는 Virtual Thread.

### 19.4 시나리오 4: OOM "unable to create native thread"

**증상**:
```
java.lang.OutOfMemoryError: unable to create native thread:
   possibly out of memory or process/resource limits reached
```

**진단**:
```bash
cat /proc/<pid>/status | grep Threads
ulimit -u
cat /proc/sys/kernel/threads-max
cat /proc/sys/kernel/pid_max
```

**원인**:
- thread leak (위 시나리오 1).
- 컨테이너 `nproc`/`pid_max` 너무 작음.
- 시스템 메모리 부족으로 stack 매핑 실패 (이때는 `-Xss` 줄이기 검토).

### 19.5 시나리오 5: 100% CPU 한 thread

**증상**: 1 core 풀 사용. 다른 thread는 정상.

**진단**:
```bash
# Linux
top -H -p <pid>      # thread별 CPU
# 가장 높은 TID를 확인 → 16진수 변환
printf "%x\n" <tid>
# jstack에서 해당 nid 검색
jstack <pid> | grep -A 20 "nid=0x<hex>"
```

**원인 후보**:
- Infinite loop / busy wait (`while (true) { /* no sleep */ }`).
- `HashMap` resizing in concurrent context (JDK 7 무한 loop 버그, 8에서 fix).
- GC thread (G1 mark 등) — 잠시 정상.

### 19.6 시나리오 6: MDC 로깅에 다른 요청의 trace ID

**증상**: 요청 A의 로그에 요청 B의 trace ID가 섞임.

**원인**: Tomcat thread 재사용. 응답 후 `MDC.clear()` 안 함.

**대응**:
```java
// filter
try {
    MDC.put("traceId", id);
    chain.doFilter(req, res);
} finally {
    MDC.clear();   // ← 필수
}
```

또는 `MDC.MDCCloseable`:
```java
try (var c = MDC.putCloseable("traceId", id)) {
    chain.doFilter(req, res);
}
```

### 19.7 시나리오 7: Tomcat thread pool 가득

**증상**: 새 요청이 ACCEPT 큐에 쌓임. p99 latency 폭증.

**진단**:
- `jstack`에서 `http-nio-8080-exec-*` thread 전부 RUNNABLE — 어디서 대기?
- 보통 외부 API 호출 또는 DB query에서 stuck.

**대응**:
- 외부 호출에 timeout 강제 ([04-timeouts-connection-vs-read.md](./04-timeouts-connection-vs-read.md)).
- maxThreads 증설 (`server.tomcat.threads.max`).
- 또는 Virtual Thread + thread-per-request (Spring Boot 3.2+ `spring.threads.virtual.enabled=true`).

### 19.8 시나리오 8: Hikari pool 고갈 + thread stack 모두 동일 패턴

**증상**:
```
HikariPool-1 - Connection is not available, request timed out after 30000ms
```

jstack:
```
"http-nio-exec-N" (다수)
   at HikariPool.getConnection
   at LockSupport.parkNanos
```

→ DB connection pool 부족 + DB query 느림. thread는 DB 응답을 기다림.

**대응**:
- query 최적화.
- pool size 적정화 (서비스 ↔ DB throughput 곱).
- connection timeout 명시.
- [network-request-lifecycle/07-connection-pools-master.md](../network-request-lifecycle/07-connection-pools-master.md) 참조.

---

## 20. 역사 — JDK Thread API 진화

```
JDK 1.0 (1996)   Thread 클래스, Runnable, synchronized, wait/notify, ThreadGroup
                  → 너무 low-level. ThreadGroup은 거의 실패.

JDK 1.2 (1998)   ThreadLocal 도입.
                  Native Thread 모델 채택 (green thread 폐기, 1:1 모델).

JDK 1.5 (2004)   ⭐ java.util.concurrent (Doug Lea)
                  - ExecutorService, ThreadPoolExecutor
                  - Lock, ReentrantLock, ReadWriteLock, Condition
                  - Atomic* (CAS 기반)
                  - BlockingQueue, ConcurrentHashMap
                  - CountDownLatch, Semaphore, CyclicBarrier, Exchanger
                  - Callable, Future
                  - JMM 재정의 (JSR-133)
                  → 동시성 프로그래밍 패러다임 전환

JDK 1.6 (2006)   synchronized 최적화 (Biased / Lightweight lock — Mark Word)
                  Phaser 후속작.

JDK 7 (2011)     ⭐ ForkJoinPool, RecursiveTask, RecursiveAction (Doug Lea)
                  ConcurrentHashMap 재구현 (segment 기반)
                  Phaser
                  TransferQueue

JDK 8 (2014)     ⭐ CompletableFuture
                  StampedLock (optimistic read)
                  LongAdder / DoubleAdder
                  Parallel Stream (ForkJoinPool.commonPool)
                  ConcurrentHashMap CAS 기반 재구현 (segment 폐기)

JDK 9 (2017)     CompletableFuture 보강 (orTimeout, delayedExecutor)
                  Flow API (Reactive Streams)
                  VarHandle (Unsafe 대안)

JDK 11 (2018)    ExecutorService.toFuture 등 소소한 개선

JDK 14 (2020)    Biased Locking deprecated, JDK 15에서 disabled by default

JDK 16 (2021)    Strong encapsulation — Unsafe 사용에 경고

JDK 17 (2021)    LTS, Biased Locking 완전 폐기 흐름

JDK 19 (2022)    Virtual Thread (preview), Structured Concurrency (incubator)
                  ExecutorService AutoCloseable (try-with-resources)

JDK 21 (2023)    ⭐ Virtual Thread stable
                  Structured Concurrency preview
                  ScopedValue preview (ThreadLocal 대체)

JDK 24 (2025)    synchronized + blocking에서의 pinning 해소

JDK 25+          Structured Concurrency, ScopedValue stable 예정
```

**큰 변곡점 3개**:
1. **JDK 5 (2004) j.u.c.** — lock 직접 짜던 시대 → 추상화된 동시성 도구.
2. **JDK 8 (2014) CompletableFuture + parallel stream** — 비동기 파이프라인의 표준.
3. **JDK 21 (2023) Virtual Thread** — 1:1 모델 25년 만의 깨짐. thread-per-request 부활.

---

## 21. 트레이드오프 정리 ⭐

### 21.1 Thread 생성 — new Thread vs ExecutorService vs VT

| 항목 | new Thread | ThreadPoolExecutor | Virtual Thread |
|---|---|---|---|
| 생성 비용 | 비쌈 (OS) | 풀 재사용 | 거의 0 |
| 메모리 | 1MB stack | 1MB × pool size | ~수KB chunk |
| 적합 | (거의 없음) | CPU bound | I/O bound (수만~) |
| 결과 받기 | join | Future | join / Future |
| 종료 제어 | interrupt만 | shutdown / awaitTerm | 동일 |

### 21.2 동기화 도구

| 도구 | 성능 | 기능 | 사용처 |
|---|---|---|---|
| `synchronized` | 빠름 (Mark Word) | 단순 | 짧은 critical section |
| `ReentrantLock` | 거의 동일 | timeout/interrupt/fairness | 복잡한 lock 정책 |
| `ReadWriteLock` | read 많을 때↑ | 차별 | cache류 |
| `StampedLock` | 가장 빠른 read | 복잡, non-reentrant | hot read path |
| `Atomic*` + CAS | 가장 빠름 | atomic 변수만 | 카운터, flag |
| `LongAdder` | high contention 최적 | sum 시점만 비쌈 | 메트릭 |
| `volatile` | 0 cost read | visibility만 | flag, publication |

### 21.3 Executor 선택

| 상황 | 선택 |
|---|---|
| CPU bound, 짧은 task | `ThreadPoolExecutor(cores, cores)` |
| Mixed, 가끔 폭주 | `ThreadPoolExecutor(core, max, ArrayBlockingQueue)` + `CallerRuns` |
| 재귀 분할 정복 | `ForkJoinPool` / `parallelStream` (단, blocking 금지) |
| I/O bound 다량 | Virtual Thread (JDK 21+) 또는 큰 fixed pool |
| 주기 작업 | `ScheduledThreadPoolExecutor` |
| 비동기 chain | `CompletableFuture` + 명시 executor |

### 21.4 ThreadLocal vs ScopedValue (JDK 21+)

| 측면 | ThreadLocal | ScopedValue |
|---|---|---|
| 가변성 | mutable (`set` 가능) | immutable per scope |
| 정리 | `remove()` 명시 | scope 종료 자동 |
| 상속 | InheritableThreadLocal | StructuredTaskScope 통합 |
| VT 친화성 | 메모리 부담 | 권장 |
| API 안정성 | stable | preview |

---

## 22. 면접 워크플로우 — 30초 답변 패턴

### 22.1 "Thread를 어떻게 만드나요?"

> "옛 방식은 `new Thread(Runnable).start()`지만 OS thread를 직접 만드는 비싼 호출이라 거의 안 씁니다. 현대는 `ExecutorService.submit()` — 풀에서 재사용합니다. 비동기 파이프라인은 `CompletableFuture.supplyAsync(task, executor)`. JDK 21+ 다량 I/O는 `Executors.newVirtualThreadPerTaskExecutor()`. 단 `Executors.newFixedThreadPool()`은 큐가 무제한이라 OOM 위험이 있어, 실무에서는 `ThreadPoolExecutor`를 직접 구성하고 유한 큐 + CallerRunsPolicy를 명시합니다."

### 22.2 "synchronized vs ReentrantLock?"

> "synchronized는 언어 기능이라 JVM이 Mark Word를 통해 biased / lightweight / heavyweight로 승격시키며 최적화하고, 예외 발생해도 자동 해제됩니다. ReentrantLock은 API라 `tryLock(timeout)`, `lockInterruptibly`, fairness, 다중 Condition 같은 기능을 제공합니다. 단 `unlock()` 책임은 사용자. 단순 mutex는 synchronized, 정책 제어가 필요하면 ReentrantLock입니다."

### 22.3 "ThreadLocal 누수?"

> "Tomcat 같은 풀은 thread를 재사용하므로 응답 후 `remove()` 안 하면 다음 요청의 thread에 옛 값이 살아있습니다. 또 `ThreadLocalMap`의 key는 weak reference라 ThreadLocal 객체가 GC돼도 value entry는 hash slot에 남아 webapp redeploy 시 ClassLoader 누수가 됩니다. 필터/인터셉터에서 try-finally로 `remove()` 또는 `MDCCloseable` 같은 try-with-resources 패턴을 강제합니다."

### 22.4 "Thread dump 어떻게 읽나요?"

> "먼저 `jcmd <pid> Thread.print`로 dump를 받고, 1) Thread name 패턴을 봅니다 — `http-nio-exec-*`, `HikariCP-*`, `ForkJoinPool-*` 등으로 어떤 풀이 문제인지. 2) State 분포 — BLOCKED 군집이면 lock contention, RUNNABLE이 socket read 위에 있으면 사실 I/O wait. 3) 같은 stack이 다수면 hot path. 4) 'Found one Java-level deadlock' 메시지가 있으면 deadlock. 더 깊게는 async-profiler wallclock 모드로 시간 비례 시각화합니다."

### 22.5 "ForkJoinPool의 work-stealing은 왜 빠른가요?"

> "각 worker가 자기 deque를 가지고, idle worker는 다른 worker의 deque tail에서 task를 훔칩니다. 자기 일은 LIFO로 push/pop — 방금 만든 task가 cache hot 상태라 cache locality가 좋고, steal은 FIFO로 가장 오래된 큰 task를 뺏어와 load balancing이 됩니다. 단 한 worker가 blocking에 빠지면 다른 task까지 stuck될 수 있어 parallel stream 안에 blocking I/O를 넣으면 안 됩니다 — `ManagedBlocker` 또는 별도 executor 사용."

---

## 23. 꼬리질문 (3단)

### 23.1 1단 — 개념

Q1. `Thread.State.RUNNABLE`이라고 jstack에 나왔는데 실제로는 socket read에서 자고 있다. 왜?
> Thread.State는 Java level monitor 기준이지 OS level이 아니라서다. native syscall에서 block 중이어도 RUNNABLE로 분류. 진단할 때 stack top이 `Net.poll` / `socketRead0` / `epollWait` 같은 native 호출이면 I/O wait. async-profiler `-e wall`이 더 정확.

Q2. `Executors.newFixedThreadPool(8)`이 왜 위험할 수 있나?
> 내부적으로 `LinkedBlockingQueue` (`Integer.MAX_VALUE` 용량) 사용. task가 처리보다 빠르게 들어오면 큐가 무한히 자라며 OOM. 직접 `ThreadPoolExecutor`로 구성해 유한 큐 + `CallerRunsPolicy` 또는 `AbortPolicy` 명시해야.

Q3. `ConcurrentHashMap.computeIfAbsent`는 atomic인가?
> Yes. key별로 atomic — 두 thread가 같은 key로 동시에 호출해도 compute는 한 번만 실행되고 둘 다 같은 결과를 받음. 단 compute 함수 안에서 다른 key를 건드리면 ('lock during compute') 데드락 가능 (JDK 8 ~9 함정, recursive update 차단됨).

### 23.2 2단 — 운영/진단

Q4. Production에서 갑자기 응답 안 하는데, CPU는 5%다. 어떻게 진단하나?
> 1) `jcmd Thread.print` 두 번 (간격 두고) — 모두 같은 위치에서 자고 있으면 hang. 2) "Java-level deadlock" 메시지 검색. 3) DB pool / HTTP client pool 고갈 확인 (HikariPool log). 4) Tomcat acceptor 큐 가득 차 있나 (`server.tomcat.accept-count` 한도). 5) GC pause (JFR 또는 GC log). 6) async-profiler wallclock 30초 — blocking 시간 시각화. 보통 외부 API timeout 미설정 + thread pool 고갈 패턴.

Q5. `LongAdder` vs `AtomicLong`을 어떻게 선택하나?
> 메트릭/카운터처럼 가산이 많고 정확한 sum이 가끔이면 LongAdder — 각 thread가 자기 cell에 += 하므로 contention 최소. ID 생성처럼 매 호출마다 정확한 값이 필요하면 AtomicLong — sum이 항상 정확. 차이는 high contention에서 10~100배 throughput 차이.

Q6. `synchronized` 안에서 외부 API 호출하면 왜 위험한가?
> 1) Lock 잡은 시간 = API latency. 다른 thread는 그 동안 BLOCKED. 2) API hang 하면 모든 thread가 BLOCKED 누적 → thread pool 고갈. 3) Virtual Thread에서는 pinning까지. 4) deadlock 확률↑ — API 호출이 다른 lock 잡을 수 있음. 원칙: critical section에는 메모리 연산만, I/O는 밖으로.

### 23.3 3단 — 심화

Q7. `volatile int counter; counter++;`는 왜 thread-safe하지 않나, 그러나 `volatile boolean flag; flag = true;`는 왜 OK인가?
> `counter++`는 read + add + write 3단계 — volatile이 보장하는 건 각 step의 visibility지 3단계 묶음의 atomicity는 아님. 두 thread가 동시에 read해서 같은 값에 +1 하면 1번만 증가. 반면 boolean 단일 write/read는 단일 명령이라 atomic. visibility(volatile) + atomicity(단일 write) 둘 다 충족.

Q8. `CompletableFuture.thenApply` 안의 lambda가 어떤 thread에서 실행되나?
> 이전 stage가 이미 완료됐으면 — `thenApply`를 호출한 thread (현재 thread). 아직 진행 중이면 — 이전 stage를 완료시킨 thread. 무거운 작업이면 의도치 않은 thread (예: HTTP client의 NIO selector thread)에서 실행될 수 있어 latency나 starvation 위험. 무조건 `thenApplyAsync(fn, executor)`로 명시.

Q9. ForkJoinPool에 100개 task를 던졌는데 worker가 8개고 그 중 5개가 동시에 blocking I/O에 들어가면 어떻게 되나?
> 8개 worker 중 5개가 native blocking에 들어가면 FJP는 이를 모름 (Thread.State RUNNABLE). 남은 3개가 95개 task를 처리. 만약 ManagedBlocker로 감싸면 FJP가 인지하고 추가 worker를 spawn (`maximumPoolSize`까지). 일반 blocking I/O를 commonPool에 던지면 starvation. parallel stream에 HTTP 호출 같은 거 절대 X.

Q10. Virtual Thread가 1만 개 떠 있는데 ThreadLocal로 SecurityContext를 저장한다. 메모리에 어떤 일?
> 각 VT마다 `ThreadLocalMap`이 별도 Heap 객체로 존재. 10000 × (entry table 평균 16 slot × 16바이트 + 값 객체) = 수 MB ~ 수십 MB. Platform Thread (수백 개)에선 무시할 수준이지만 VT 수십만에서는 비례 증가. 그래서 ScopedValue가 권장됨 — immutable + scope 한정으로 메모리 효율적.

---

## 24. 마무리 — 백지 마스터 체크리스트

이 문서를 닫고 백지에 다음을 그릴 수 있는가?

- [ ] Thread.State 6개 상태 다이어그램 + 각 상태를 만드는 코드
- [ ] ThreadPoolExecutor의 task 처리 흐름 (core → queue → max → reject)
- [ ] `Executors.newFixedThreadPool` vs `newCachedThreadPool`의 차이와 각각의 OOM 시나리오
- [ ] Tomcat TaskQueue가 표준 정책과 다른 점 (thread 먼저 늘림)
- [ ] ForkJoinPool work-stealing — own LIFO, steal FIFO
- [ ] ThreadLocal 누수 2가지 패턴 (thread 재사용, weak reference value)
- [ ] synchronized vs ReentrantLock vs StampedLock 트레이드오프
- [ ] CAS / AtomicLong / LongAdder 차이 + ABA 문제
- [ ] volatile의 보장과 미보장 (visibility O, atomicity X)
- [ ] Double-checked locking에 왜 volatile이 필요한가
- [ ] Deadlock 4 조건 + jstack 메시지 형태
- [ ] CompletableFuture에서 `commonPool` 사용 함정과 명시 executor 지정 이유
- [ ] Virtual Thread vs Platform Thread 메모리/생성/I/O 비교
- [ ] jstack thread name 패턴 5가지 (http-nio-exec, HikariCP, FJP common pool, ...)
- [ ] Thread dump 분석 4가지 패턴 (hot path, BLOCKED 군집, WAITING parking, TIMED_WAITING + socket read)
- [ ] 운영 시나리오 8개를 진단 흐름과 대응까지 줄줄

다 답할 수 있으면 이 문서를 마스터한 것. 못 답하는 항목이 있으면 해당 장으로 돌아가 다시 학습.

---

## 🔗 관련 문서

- [jvm/05-threading/01-jmm-and-happens-before.md](../jvm/05-threading/01-jmm-and-happens-before.md) — JMM, happens-before 13규칙
- [jvm/05-threading/02-memory-barriers.md](../jvm/05-threading/02-memory-barriers.md) — Memory Barrier, CAS 내부
- [jvm/05-threading/03-synchronized-and-mark-word.md](../jvm/05-threading/03-synchronized-and-mark-word.md) — Mark Word lock 승격
- [jvm/05-threading/04-virtual-threads-and-loom.md](../jvm/05-threading/04-virtual-threads-and-loom.md) — Continuation, Pinning
- [network-request-lifecycle/06-tomcat-internals.md](../network-request-lifecycle/06-tomcat-internals.md) — Tomcat NIO connector + TaskQueue
- [network-request-lifecycle/07-connection-pools-master.md](../network-request-lifecycle/07-connection-pools-master.md) — HikariCP, HTTP client pool
- [java-deep-dive/04-timeouts-connection-vs-read.md](./04-timeouts-connection-vs-read.md) — connect/read/write timeout (예정)
