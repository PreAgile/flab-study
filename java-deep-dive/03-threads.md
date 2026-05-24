# 03. Java Threads — 사용자 코드 관점의 Thread 마스터

> Thread 1개 = OS thread 1개 = 1MB stack. 비싼 자원이라 풀로 재사용한다.
> ExecutorService 큐 정책에 따라 production은 OOM이 되거나 reject가 된다.
> ThreadLocal은 풀 thread가 재사용되며 누수를 만든다.
> jstack의 Thread.State로 BLOCKED / WAITING / RUNNABLE을 구분해 lock contention, deadlock, I/O wait를 진단한다.
> JVM 내부(JMM, Memory Barrier, Mark Word)는 [jvm/05-threading/](../jvm/05-threading/)에서 다룬다.

---

## 목차

1. Thread 본질 — OS thread 1:1
2. Thread.State 전이
3. ExecutorService 5종 + ThreadPoolExecutor 직접 구성
4. ForkJoinPool work-stealing
5. ThreadLocal과 누수
6. 동기화 — synchronized / Lock / Atomic / volatile
7. Thread Communication 한 표
8. Race Condition 4패턴 한 표
9. Virtual Thread (JDK 21+) 요약
10. 운영 시나리오 + 꼬리질문

---

## 1. Thread의 본질 — OS Thread 1:1 매핑

`Thread.start()`는 native `Thread::start0` → `pthread_create` / `CreateThread`로 이어진다. **Java Thread 1개 = OS Thread 1개** (Platform Thread). Kernel scheduler가 실제 CPU를 할당한다. 한 thread는 stack 1MB(`-Xss`), TLAB 수십KB, 생성 비용 수십~수백 μs를 소모한다. 10만 thread = 100GB stack — 불가능. 그래서 풀로 재사용한다.

```
[Java]                          [OS Kernel]
Thread t = new Thread(r);  ──▶  pthread_create
t.start();                       │
                                 ▼
                            ┌────────────┐
                            │ OS Thread  │  ← scheduler가 관리
                            │ Stack 1MB  │  ← -Xss
                            │ PC, regs   │
                            └────────────┘

cf. Virtual Thread (JDK 21+) = M Virtual : N Carrier (OS)
```

### 함정: "unable to create native thread"

```
java.lang.OutOfMemoryError: unable to create native thread
```

JVM heap이 아니라 **OS thread를 못 만든다**는 뜻. 원인은 `ulimit -u` (nproc), `/proc/sys/kernel/threads-max`, `pid_max`, 시스템 메모리 부족 중 하나. JVM heap 늘려도 안 된다.

```bash
cat /proc/sys/kernel/threads-max
ulimit -u
ps -eLf | wc -l    # 현재 thread 수
```

### Thread 생성 4방법 — 선택 가이드

| 상황 | 선택 |
|---|---|
| 일회성 비동기 (script) | `CompletableFuture.supplyAsync(task, exec)` |
| 서버 worker pool (CPU bound) | `ThreadPoolExecutor` 직접 구성 |
| 분할 정복 (CPU 분산) | `ForkJoinPool` / `parallelStream` (blocking 금지) |
| 다수 I/O blocking | Virtual Thread (JDK 21+) 또는 큰 fixed pool |
| 호환성 | `Executors.newFixedThreadPool` (단 큐 무제한 함정) |

`new Thread(...).start()`는 풀 재사용 X, 예외 정책 없음, 이름 관리 안 됨 — 시니어 코드에선 거의 안 보인다. **Daemon thread**(`setDaemon(true)` before `start()`)는 모든 non-daemon이 종료되면 JVM이 강제 종료한다. GC/JIT thread가 daemon, 사용자 worker는 보통 non-daemon으로 두어 shutdown hook이 작동하게 한다. ThreadGroup은 옛 API라 현대 코드에서 거의 안 쓴다.

---

## 2. Thread.State 전이

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

| State | 의미 | 만드는 코드 | jstack 출력 |
|---|---|---|---|
| **NEW** | start() 전 | `new Thread(r)` | (안 보임) |
| **RUNNABLE** | 실행 중 or 준비 | 일반 코드 | `RUNNABLE` |
| **BLOCKED** | monitor 진입 대기 | `synchronized` 진입 직전 | `BLOCKED (on object monitor)` + `waiting to lock <0x..>` |
| **WAITING** | 무한정 대기 | `wait()`, `park()`, `join()` | `WAITING (parking)` |
| **TIMED_WAITING** | 시간 제한 대기 | `sleep`, `wait(t)`, `parkNanos`, `future.get(t)` | `TIMED_WAITING` |
| **TERMINATED** | run() 종료 | run 끝 / 예외 | (사라짐) |

### Socket.read는 RUNNABLE이다 — 운영 함정

`Thread.State`는 **Java level monitor**만 반영한다. native syscall(`epoll_wait`, `Net.poll`, `socketRead0`) blocking은 RUNNABLE로 표시된다. "CPU 0%인데 jstack RUNNABLE 100개"는 보통 socket read에서 자고 있는 것. CPU bound 오판 금지. 정확히 보려면 **async-profiler wallclock** (`-e wall`).

### BLOCKED vs WAITING

- **BLOCKED**: `synchronized(lockObj)` 진입 대기 — "화장실 문 앞에서 대기". 군집이면 **lock contention**.
- **WAITING**: lock은 release한 후 `notify`를 기다림 — "잠시 자리 비움". 군집이면 producer 부족 또는 condition variable 대기.

---

## 3. ExecutorService — 5종 + ThreadPoolExecutor 직접 구성

### 3.1 `Executors.*` 5종

| 팩토리 | 내부 구성 | 함정 |
|---|---|---|
| `newFixedThreadPool(N)` | `ThreadPoolExecutor(N, N, 0, LinkedBlockingQueue(MAX))` | **큐 무제한 → OOM** |
| `newCachedThreadPool()` | `ThreadPoolExecutor(0, MAX, 60s, SynchronousQueue)` | **thread 무제한 → unable to create native thread** |
| `newSingleThreadExecutor()` | `ThreadPoolExecutor(1, 1, 0, LinkedBlockingQueue(MAX))` | 순서 보장, **큐 무제한 동일** |
| `newScheduledThreadPool(N)` | `ScheduledThreadPoolExecutor(N)` (DelayedWorkQueue) | Timer 대체용 |
| `newWorkStealingPool()` | `ForkJoinPool(parallelism)` | commonPool과 별개 |

### `newFixedThreadPool` OOM 함정

내부 큐는 `LinkedBlockingQueue` 용량 `Integer.MAX_VALUE`. task가 처리 속도보다 빠르게 들어오면 큐가 무한히 자라며 **OOM (heap)**. backpressure 없음. Brian Goetz "Java Concurrency in Practice" 이래 공식 권장은 **`ThreadPoolExecutor` 직접 구성**.

### 3.2 ThreadPoolExecutor 동작

```
submit(task)
   │
   ├── 1) workerCount < corePoolSize  → 새 core worker 생성 (idle여도 유지)
   ├── 2) corePool 가득 → workQueue.offer(task) 성공이면 대기
   ├── 3) 큐 full + workerCount < maxPoolSize → over-core worker 생성 (keepAliveTime 후 종료)
   └── 4) 다 실패 → RejectedExecutionHandler
```

권장 구성:

```java
new ThreadPoolExecutor(
    8, 32, 60, TimeUnit.SECONDS,
    new ArrayBlockingQueue<>(200),                       // 유한 큐
    new NamedThreadFactory("worker"),                    // 이름 명시
    new ThreadPoolExecutor.CallerRunsPolicy()            // backpressure
);
```

**RejectedExecutionHandler 4종**:

| 정책 | 동작 | 사용처 |
|---|---|---|
| `AbortPolicy` (default) | `RejectedExecutionException` 던짐 | 명시적 backpressure 신호 |
| `CallerRunsPolicy` | submit한 thread가 직접 실행 | Tomcat류 자연스러운 throttling |
| `DiscardPolicy` | 조용히 버림 | 비필수 (log) |
| `DiscardOldestPolicy` | 큐 head 버리고 재시도 | 실시간 우선 |

### 3.3 큐 4종 한 표

| 큐 | 특성 | 효과 |
|---|---|---|
| `SynchronousQueue` | 용량 0, hand-off | 즉시 worker로 전달, 없으면 즉시 새 worker (cachedThreadPool) |
| `LinkedBlockingQueue` (무제한) | `Integer.MAX_VALUE` | fixed pool 디폴트, **OOM 위험** |
| `LinkedBlockingQueue` (제한) / `ArrayBlockingQueue` | 명시 용량 | backpressure. Array가 약간 빠름 |
| `PriorityBlockingQueue` | 우선순위 힙 | task 우선순위 처리 |

### 3.4 Tomcat의 변종 TaskQueue

표준은 "core 차면 queue, queue 차면 max". 반면 Tomcat `org.apache.tomcat.util.threads.TaskQueue`는 `offer()`가 `poolSize < maximumPoolSize`일 때 일부러 `false`를 반환 → **thread를 maxPool까지 먼저 늘리고 그 다음에 queue**. 이유는 request latency 우선 — 큐 대기보다 thread 생성 비용이 낫다는 판단. 자세히 [network-request-lifecycle/06-tomcat-internals.md](../network-request-lifecycle/06-tomcat-internals.md).

---

## 4. ForkJoinPool — Work-Stealing

```
[ForkJoinPool: 각 worker가 자기 deque 소유]

  Worker-1                Worker-2               Worker-3 (idle)
  ┌───────┐               ┌───────┐              ┌───────┐
  │  T11  │ ◀── push/pop  │  T21  │              │       │
  │  T12  │   (LIFO,head) │  T22  │              │       │
  │  T13  │               │  T23  │              │       │
  │  T14  │               │  T24  │ ◀────────────┤ steal │
  └───────┘               └───────┘              │(FIFO, │
                                                 │ tail) │
                                                 └───────┘
   own: head LIFO (cache hot)    steal: tail FIFO (큰 task = load balance)
```

```java
class Sum extends RecursiveTask<Long> {
    protected Long compute() {
        if (hi - lo <= THRESHOLD) { /* base */ }
        int mid = (lo + hi) / 2;
        Sum left = new Sum(arr, lo, mid);
        Sum right = new Sum(arr, mid, hi);
        left.fork();                  // 자기 deque push
        long r = right.compute();
        long l = left.join();
        return l + r;
    }
}
```

### commonPool 함정

`parallelStream`, `CompletableFuture.supplyAsync(no executor)`는 `ForkJoinPool.commonPool()`을 공유한다. parallelism = `availableProcessors() - 1`. **blocking I/O를 던지면 starvation** — 한 곳에서 잡으면 JVM 전체 라이브러리가 영향받는다.

**왜 LIFO/FIFO 분리**:
- own LIFO — 방금 생성한 task가 cache hot 상태(부모 task의 변수 참조) → cache locality.
- steal FIFO — 재귀 분할이라 deque tail에 있는 task가 가장 큰 단위 → 한 번 훔치면 일이 많이 따라온다 → load balancing + steal 횟수 최소화.
- own과 steal이 deque 양 끝에서 일어나 lock-free contention 최소.

대응:
- 별도 executor 명시 (`supplyAsync(task, ioExec)`).
- 어쩔 수 없으면 `ForkJoinPool.managedBlock(...)` — FJP가 인지하고 `maximumPoolSize`까지 보충 worker spawn.
- 또는 Virtual Thread.

---

## 5. ThreadLocal — 누수의 단골

```
[Thread 객체 안의 ThreadLocalMap]

  Thread-A                      Thread-B
  ┌────────────────────┐        ┌────────────────────┐
  │ threadLocals       │        │ threadLocals       │
  │ = ThreadLocalMap   │        │ = ThreadLocalMap   │
  │ ┌────────────────┐ │        │ ┌────────────────┐ │
  │ │TL1(weak) → vA1 │ │        │ │TL1(weak) → vB1 │ │
  │ │TL2(weak) → vA2 │ │        │ │TL2(weak) → vB2 │ │
  │ └────────────────┘ │        │ └────────────────┘ │
  └────────────────────┘        └────────────────────┘
```

각 Thread 안에 `ThreadLocalMap`이 있고 key는 `WeakReference<ThreadLocal>`, value는 strong reference. 주요 사용처는 `SimpleDateFormat`, MDC(logback), Spring SecurityContext, Hibernate Session.

### 누수 패턴

1. **Thread 재사용 누수** — Tomcat thread는 응답 후 풀로 복귀하므로 자동 정리 없음. 다음 요청이 `TL.get()`하면 옛 값이 살아있어 다른 요청자 정보가 흘러나옴. **Security 사고**.
2. **WeakReference value 누수** — ThreadLocal 객체 자체가 GC돼도 key=null인 entry의 value는 hash slot에 그대로 남음. webapp redeploy 시 ClassLoader 누수 원인.

대응:
```java
try {
    SecurityContext.set(currentUser);
    return chain.proceed();
} finally {
    SecurityContext.remove();   // 필수
}
```

- ThreadLocal은 `static final` 1개만 (인스턴스마다 만들지 말기).
- `InheritableThreadLocal`은 새 thread 생성 시점에만 부모 값을 얕은 복사 — ExecutorService에 제출한 task는 풀 thread라 **상속 안 됨**. ForkJoinPool worker는 풀 시작 시 한 번만 상속.
- MDC를 비동기 task에 전파하려면 task wrap decorator 명시 (`TaskDecorator`, `MdcCopyingRunnable` 등).
- Tomcat undeploy 시 "WebappClassLoader leak" warning은 대부분 정리 안 된 ThreadLocal value가 옛 ClassLoader의 클래스 instance를 잡고 있어서 발생.

---

## 6. 동기화 — synchronized / Lock / Atomic / volatile

### 6.1 synchronized vs ReentrantLock 비교

| 측면 | `synchronized` | `ReentrantLock` |
|---|---|---|
| 형태 | 언어 기능 | API (`j.u.c.locks`) |
| release | 자동 (예외 발생해도) | 수동 (`finally`에서 `unlock()`) |
| timeout | 불가 | `tryLock(timeout)` |
| interrupt | 무시 | `lockInterruptibly()` |
| fairness | 불가 | `new ReentrantLock(true)` (throughput↓) |
| Condition | 1개 (`wait`/`notify`) | 여러 개 (`newCondition()`) |
| JVM 최적화 | Mark Word 승격 (biased/light/heavy) | 덜 받음 |
| 사용처 | 짧은 critical section | 정책 제어 필요할 때 |

추가로 **ReadWriteLock** (read-heavy cache, writer starvation 위험), **StampedLock** (optimistic read — 가장 빠른 read, non-reentrant, Condition 없음)이 있다.

### 6.2 Atomic / volatile

**Atomic** (`AtomicInteger`, `AtomicReference`, `LongAdder`...)은 lock 없이 **CAS**(Compare-And-Swap)로 원자적 read-modify-write 보장. `incrementAndGet()`, `compareAndSet(old, new)`, `updateAndGet(λ)`.

- **AtomicLong vs LongAdder**: AtomicLong은 모든 thread가 같은 long에 CAS → high contention 시 CAS 실패↑. LongAdder는 각 thread가 자기 cell에 += → 가산 빠름, sum() 시점만 비쌈. **메트릭/카운터는 LongAdder**, 정확한 순서가 필요한 ID 생성은 AtomicLong.
- **ABA 문제**: A→B→A 변경 후 CAS(A,_)가 성공해버림. lock-free stack/queue는 `AtomicStampedReference` (버전 스탬프)로 방지.

**volatile**은 **visibility + happens-before + reordering 차단**만 보장. **atomicity는 미보장** — `volatile int i; i++;`는 thread-safe 아님 (read+add+write 3단계). 단일 write/read는 atomic. JMM 규칙: volatile write 이전의 모든 메모리 효과가 volatile read 이후 코드에서 보인다. JVM은 write 뒤 `StoreLoad` barrier, read 앞 `LoadLoad/LoadStore` 삽입 ([jvm/05-threading/02](../jvm/05-threading/02-memory-barriers.md)).

함정: `volatile int[] arr`는 참조만 volatile, element는 아님 → `AtomicIntegerArray` 사용. 64bit JVM은 `long`/`double` write가 거의 atomic이지만 JLS 17.7은 32bit JVM에서 non-atomic 허용 → 두 thread가 동시에 write 하면 high/low 32bit가 섞일 수 있다. `volatile long` 또는 `AtomicLong`.

### 6.3 Double-checked locking

```java
private volatile Singleton instance;   // volatile 필수
public Singleton get() {
    if (instance == null) {
        synchronized (this) {
            if (instance == null) instance = new Singleton();
        }
    }
    return instance;
}
```

volatile 없으면 `new Singleton()` 3단계(할당/생성자/참조 대입)가 reorder되어 다른 thread가 partial-init 객체를 본다. **권장은 Holder idiom** — 클래스 초기화는 JVM이 thread-safe하게 보장.

```java
private static class Holder { static final Singleton INSTANCE = new Singleton(); }
public static Singleton get() { return Holder.INSTANCE; }
```

---

## 7. Thread Communication — 한 표

| 도구 | 의미 | 핵심 사용 패턴 / 함정 |
|---|---|---|
| `wait` / `notify` | legacy condition | 반드시 `synchronized` 안 + `while` loop (spurious wakeup), `notifyAll`이 안전 |
| `Condition` | ReentrantLock의 wait | producer/consumer를 별개 Condition으로 분리 → wakeup 최소화 |
| `BlockingQueue` | producer/consumer 정답 | `put`/`take`로 자동 blocking. Linked/Array/Synchronous/LinkedTransfer/Priority/Delay |
| `CountDownLatch` | N번 countDown 후 await 해제 | 초기화 완료 신호, 1회용 |
| `CyclicBarrier` | N개 thread 도달 시 통과, 재사용 | phase 동기화 |
| `Semaphore` | N개 permit | rate limit, connection pool |
| `Phaser` | 다단계 barrier, 동적 join | 복잡한 phase |
| `Exchanger` | 두 thread가 값 교환 | producer/consumer 한 쌍 |

### CompletableFuture 한 단락

JDK 8+ 비동기 파이프라인 promise/future. `supplyAsync`/`thenApply`/`thenCompose`/`thenCombine`/`exceptionally`/`allOf`/`orTimeout`. 기본 executor가 `commonPool`이라 **blocking I/O를 던지면 parallel stream과 함께 starvation**. 무조건 `Async` 변종 + 명시 executor 사용. `thenApply`(non-async)는 이전 stage 완료시킨 thread에서 실행되므로 NIO selector 같은 의도치 않은 thread에 무거운 작업이 떨어질 수 있다. chain 안에서 `get()`/`join()` 호출 시 self-deadlock 가능.

---

## 8. Race Condition — 4패턴 한 표

| 패턴 | 잘못된 코드 | 정답 |
|---|---|---|
| **Check-then-act** | `if (!map.containsKey(k)) map.put(k, v);` | `ConcurrentHashMap.computeIfAbsent(k, fn)` |
| **Read-modify-write** | `counter++;` | `AtomicInteger.incrementAndGet()` / `LongAdder.add(1)` |
| **Lazy init** | DCL without volatile | `private volatile T inst` 또는 Holder idiom |
| **Iter during modify** | `for(x:list) list.remove(x)` → CME | `removeIf`, `Iterator.remove`, `CopyOnWriteArrayList` (weakly consistent) |

### Deadlock 4 조건 (Coffman)

mutual exclusion + hold and wait + no preemption + **circular wait**. 보통 circular wait를 깬다 (lock 순서 강제). `tryLock(timeout)`, critical section 내 외부 I/O 금지, 고수준 동시성 도구(`ConcurrentHashMap`, `BlockingQueue`) 사용.

```
jstack:
Found one Java-level deadlock:
"Thread-1": waiting to lock <0x..A>, holds <0x..B>
"Thread-2": waiting to lock <0x..B>, holds <0x..A>
```

`ManagementFactory.getThreadMXBean().findDeadlockedThreads()`로 health check에 통합 가능.

---

## 9. Virtual Thread (JDK 21+) — 한 단락

```
[Platform Thread]                 [Virtual Thread]
1 Java = 1 OS thread              M Virtual : N Carrier (OS)
Stack 1MB (OS)                    Stack chunk in Heap (~수 KB)
~수만 개 한계                      ~수십만 개 가능
blocking I/O = OS thread 점거     blocking I/O = freeze, carrier 양보
context switch: OS                JVM scheduler
```

```java
Thread.startVirtualThread(() -> doWork());
try (var es = Executors.newVirtualThreadPerTaskExecutor()) {
    requests.forEach(r -> es.submit(() -> handle(r)));
}
```

다량 I/O blocking에서 thread-per-request 패턴 부활. 생성 비용 거의 0. **Pinning 함정**: JDK 21~23은 `synchronized` 안에서 blocking 시 carrier가 pinned되어 platform thread 1:1로 회귀 (JDK 24+에서 해소, JNI native call은 여전히 pin). 진단: `-Djdk.tracePinnedThreads=full`. **ScopedValue**(preview)가 VT에 친화적인 ThreadLocal 대체 — immutable + scope 종료 자동 해제. 수십만 VT × ThreadLocalMap은 메모리 부담. 자세히 [jvm/05-threading/04-virtual-threads-and-loom.md](../jvm/05-threading/04-virtual-threads-and-loom.md).

---

## 10. 운영 시나리오 + 진단

### 진단 도구 한 표

| 도구 | 용도 |
|---|---|
| `jcmd <pid> Thread.print` (또는 `jstack -l`) | thread dump. `-l`로 `j.u.c.Lock` 포함 |
| `kill -3 <pid>` | SIGQUIT → stdout dump |
| `top -H -p <pid>` + `printf %x` + `jstack` `nid=0x..` 검색 | 특정 thread의 CPU 추적 |
| async-profiler `-e wall` | wallclock — blocking 시간 시각화 (latency 진단 1순위) |
| async-profiler `-e lock` | lock contention hot path |
| JFR `jdk.JavaMonitorEnter` / `JavaMonitorWait` / `ThreadPark` | 저비용 lock/wait duration |
| `ThreadMXBean.findDeadlockedThreads()` | 프로그램 안에서 deadlock 감지 |

**Thread name convention** (식별):

| 이름 패턴 | 출처 |
|---|---|
| `main` | main thread |
| `Thread-N` | 이름 안 준 thread (피해야) |
| `http-nio-8080-exec-N` | Tomcat NIO connector worker |
| `http-nio-8080-Acceptor` | Tomcat acceptor |
| `HikariPool-1-*` | HikariCP housekeeper / Connection-Adder |
| `ForkJoinPool.commonPool-worker-N` | FJP common pool |
| `pool-N-thread-M` | 이름 안 준 ThreadPoolExecutor |
| `C1/C2 CompilerThread` | JIT |
| `G1 ...`, `VM Thread` | JVM 내부 |

시니어 코드는 `ThreadFactory`로 의미있는 이름 + `setUncaughtExceptionHandler` 강제:
```java
ThreadFactory tf = r -> {
    Thread t = new Thread(r, "order-worker-" + counter.incrementAndGet());
    t.setUncaughtExceptionHandler((th, ex) -> log.error("uncaught in {}", th, ex));
    return t;
};
```

**Dump 분석 4패턴**:
- 같은 stack 다수 thread (RUNNABLE) = **hot path** — 성능 문제의 진원지.
- BLOCKED 군집 + `waiting to lock <0x..>` 같은 monitor = **lock contention** — 한 thread가 잡은 lock을 다수가 기다림. lock 범위 축소.
- WAITING parking + `LinkedBlockingQueue.take` = 정상 **idle worker**.
- TIMED_WAITING + `Net.poll` / `socketRead0` / `RemoteApiClient` = **upstream 느림** — 외부 API 응답 대기.

또 deadlock일 때만 jstack 출력 상단에 "Found one Java-level deadlock" 메시지가 직접 표시된다 (JVM이 wait-for 그래프 분석).

### 시나리오 1: Thread leak

증상: `jvm_threads_live_threads` 메트릭이 단조 증가 → "unable to create native thread".
원인: `ExecutorService.shutdown()` 미호출, ScheduledExecutorService cancel 누락, 무한 루프에서 `new Thread().start()`, third-party 라이브러리 배경 thread 정리 안 됨.
진단: `jstack`에서 어떤 이름 패턴이 늘어나나 확인 + peak vs current 비교.
대응: try-with-resources(JDK 19+) 또는 shutdown hook, threadCount 메트릭 alert.

### 시나리오 2: Deadlock

증상: 응답 안 함, CPU 5%, p99 latency 무한대.
전형적 코드:
```java
synchronized (lockA) { synchronized (lockB) { ... } }
// 다른 thread
synchronized (lockB) { synchronized (lockA) { ... } }   // 반대 순서
```
진단: `jstack -l <pid> | grep -A2 "Java-level deadlock"`. 또는 health check endpoint에 `ThreadMXBean.findDeadlockedThreads()` 통합.
대응: 즉시 — thread interrupt 또는 재시작. 항구적 — lock 순서 강제 (자원 hashCode 순 등), `tryLock(timeout)`, critical section에 I/O 금지, 고수준 도구(`ConcurrentHashMap`, `BlockingQueue`)로 교체.

### 시나리오 3: MDC 로깅 누수 (다른 요청의 trace ID)

증상: 요청 A 로그에 요청 B의 traceId.
원인: Tomcat thread 재사용 + 응답 후 `MDC.clear()` 누락. `InheritableThreadLocal`이라 해도 ExecutorService에 제출된 비동기 작업은 풀 thread라 새 thread 생성이 아니라 상속 안 됨 → 더 큰 혼란.
대응:
```java
try (var c = MDC.putCloseable("traceId", id)) {
    chain.doFilter(req, res);
}
```
또는 filter finally에 `MDC.clear()`. SecurityContext, Hibernate Session, TransactionSynchronizationManager 등 모든 thread-local에 동일 원칙. 비동기로 trace 전파하려면 task wrap decorator (예: Spring `TaskDecorator`)로 명시 복사.

### 추가 참고 시나리오

- **Thread starvation in commonPool**: `parallelStream().forEach` 안에 HTTP 호출 → worker 다 blocking → 다른 라이브러리의 parallel stream까지 멈춤. 대응: 별도 executor + `CompletableFuture` 또는 Virtual Thread.
- **Hikari pool 고갈 + 동일 stack**: 모든 `http-nio-exec-*` thread가 `HikariPool.getConnection` + `parkNanos`. DB query 느림 + pool size 부족. query 최적화 + pool size 적정화 + connection timeout 명시.
- **100% CPU 단일 thread**: `top -H -p <pid>`로 TID → `printf "%x\n" <tid>` 16진수 → `jstack <pid> | grep -A 20 "nid=0x<hex>"`. 보통 infinite loop / busy wait, 드물게 GC mark thread (정상).

---

## 11. 꼬리질문 (3~5개)

**Q1. jstack에 RUNNABLE인데 실제 CPU 0%다. 왜?**
> `Thread.State`는 Java level monitor 기준이라 native syscall blocking(`epoll_wait`, `socketRead0`)은 RUNNABLE로 분류된다. stack top이 native면 I/O wait. async-profiler `-e wall`이 정확.

**Q2. `Executors.newFixedThreadPool(8)`이 왜 위험한가?**
> 내부 `LinkedBlockingQueue` 용량이 `Integer.MAX_VALUE`. task가 처리 속도보다 빠르면 큐가 무한 성장 → heap OOM. backpressure 신호 없음. `ThreadPoolExecutor`를 직접 구성해 유한 큐 + `CallerRunsPolicy` 명시.

**Q3. `synchronized` 안에서 외부 API 호출하면 왜 위험한가?**
> lock 보유 시간 = API latency. 다른 thread는 그동안 BLOCKED 누적 → thread pool 고갈. API hang 시 cascading. Virtual Thread에서는 pinning까지 발생. 원칙: critical section에는 메모리 연산만, I/O는 밖으로.

**Q4. `LongAdder` vs `AtomicLong` 선택 기준은?**
> 가산이 많고 정확한 sum이 가끔이면 LongAdder — 각 thread가 자기 cell에 += 하므로 contention 최소(high contention 10~100배 throughput 차이). 매 호출마다 정확한 단조 증가 값이 필요하면 AtomicLong.

**Q5. ForkJoinPool worker 8개 중 5개가 blocking I/O에 들어가면?**
> FJP는 native blocking을 모름 (RUNNABLE로 보임) → 남은 3개가 95개 task 처리, 사실상 starvation. `ManagedBlocker`로 감싸면 FJP가 인지하고 보충 worker spawn. parallel stream에 HTTP 호출은 절대 금지.

**Q6. Virtual Thread 1만 개에 ThreadLocal로 SecurityContext 저장하면?**
> 각 VT마다 `ThreadLocalMap`이 별도 Heap 객체로 존재한다. 10000 × (entry table + value) ≈ 수 MB ~ 수십 MB. Platform Thread 수백 개에선 무시했던 비용이 수십만 VT에서는 비례 증가. 그래서 `ScopedValue`(preview) 권장 — immutable + scope 한정으로 메모리 효율적.

---

## 12. JDK Thread API 진화 요약

- **JDK 1.0** Thread, synchronized, wait/notify — 너무 low-level.
- **JDK 1.2** ThreadLocal, native thread 1:1 모델 채택 (green thread 폐기).
- **JDK 5 (2004)** ⭐ `java.util.concurrent` (Doug Lea) + JMM 재정의 (JSR-133). ExecutorService, Atomic, BlockingQueue, ConcurrentHashMap, CountDownLatch 등 — 동시성 패러다임 전환.
- **JDK 6** synchronized 최적화 (Biased / Lightweight — Mark Word).
- **JDK 7** ForkJoinPool, RecursiveTask.
- **JDK 8 (2014)** ⭐ CompletableFuture, StampedLock, LongAdder, parallelStream, ConcurrentHashMap CAS 재구현.
- **JDK 9** orTimeout, Flow API, VarHandle.
- **JDK 15** Biased Locking disabled by default.
- **JDK 19** Virtual Thread (preview), Structured Concurrency (incubator), ExecutorService AutoCloseable.
- **JDK 21 (2023)** ⭐ Virtual Thread stable, ScopedValue preview.
- **JDK 24+** synchronized + blocking pinning 해소.

큰 변곡점 3개: **JDK 5 j.u.c. → JDK 8 CompletableFuture → JDK 21 Virtual Thread** (1:1 모델 25년 만에 깨짐, thread-per-request 부활).

---

## 관련 문서

- [jvm/05-threading/01-jmm-and-happens-before.md](../jvm/05-threading/01-jmm-and-happens-before.md) — JMM, happens-before
- [jvm/05-threading/02-memory-barriers.md](../jvm/05-threading/02-memory-barriers.md) — Memory Barrier, CAS 내부
- [jvm/05-threading/03-synchronized-and-mark-word.md](../jvm/05-threading/03-synchronized-and-mark-word.md) — Mark Word lock 승격
- [jvm/05-threading/04-virtual-threads-and-loom.md](../jvm/05-threading/04-virtual-threads-and-loom.md) — Continuation, Pinning 풀버전
- [network-request-lifecycle/06-tomcat-internals.md](../network-request-lifecycle/06-tomcat-internals.md) — Tomcat NIO connector + TaskQueue
- [network-request-lifecycle/07-connection-pools-master.md](../network-request-lifecycle/07-connection-pools-master.md) — HikariCP, HTTP client pool

> ThreadPoolExecutor 4 queue 종류, work-stealing deque LIFO/FIFO, Virtual Thread pinning 풀버전은 git 7e4a6c8 참조.
