# 09-05. JVM Concurrency — 시니어 깊이 답변 8문항

> JVM 동시성은 **세 층**으로 쌓여 있습니다. 위에서부터 (a) 언어 키워드 `synchronized`/`volatile`, (b) `java.util.concurrent` 라이브러리 (AQS, ConcurrentHashMap, ForkJoin), (c) OS 스레드와 JMM(Java Memory Model).
> 시니어 면접의 본질은 "위 키워드를 누르면 아래 어디까지 내려가는지"를 추적하는 능력입니다. `synchronized` 한 줄이 Mark Word → CAS → ObjectMonitor → `pthread_mutex_lock` → `futex(2)` → OS scheduler로 내려가는 길을, 그리고 `jstack`이 보여주는 BLOCKED·WAITING이 그 길의 어느 지점인지를 그릴 수 있어야 합니다.
> 이 문서는 OS-스레드 기반 동시성에 집중합니다. Virtual Thread(Loom)는 `06-version-history/03-version-history-deep.md`에서 별도로 다룹니다.

---

## 0. 8문항 한눈에

| # | 질문 | 핵심 키워드 |
|---|---|---|
| Q1 | JVM 스레드 관리 + 동시성 제어 전반 | synchronized / volatile / j.u.c, JMM 3층 모델 |
| Q2 | 스레드 스케줄링 + OS 스레드와의 관계 | 1:1 mapping, Thread.start native call, park/unpark, futex |
| Q3 | synchronized / ReentrantLock / StampedLock 내부 | Mark Word 승격, AQS state machine, optimistic read |
| Q4 | volatile 가시성과 한계 | happens-before, store-load barrier, compound action 불가 |
| Q5 | j.u.c 주요 클래스 동작 원리 | TPE, CompletableFuture, ConcurrentHashMap CAS, AQS Semaphore |
| Q6 | 데드락 / 라이브락 / 스타베이션 진단 | lock ordering, tryLock timeout, jstack cycle, JMC |
| Q7 | Fork/Join + Parallel Stream | work-stealing deque, commonPool, spliterator 함정 |
| Q8 | Thread Dump 분석 | jstack/jcmd, BLOCKED·WAITING 패턴, JFR |

---

## Q1. JVM 스레드 관리 및 동시성 제어 전반 — synchronized · volatile · j.u.c

### 한 줄 정의

> JVM의 동시성은 **3층 스택**입니다. 최상층은 언어 키워드(`synchronized`, `volatile`), 중간층은 `java.util.concurrent`(AQS, ConcurrentHashMap, ExecutorService), 최하층은 JMM(happens-before)과 OS 스레드. 셋 중 어느 하나만 알면 production 장애를 못 풉니다.

### 3층 스택 도식

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 3 — 언어 키워드                                       │
│    synchronized  →  Mark Word 기반 monitor                  │
│    volatile      →  JIT가 memory barrier 삽입               │
│    final         →  freeze action (생성자 끝 happens-before)│
└────────────────────────┬────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│  Layer 2 — java.util.concurrent                             │
│    ReentrantLock / Semaphore / CountDownLatch  →  AQS state │
│    ConcurrentHashMap                           →  CAS + bin │
│    ExecutorService / ThreadPoolExecutor        →  work queue│
│    CompletableFuture                           →  callback  │
│    ForkJoinPool                                →  WS deque  │
└────────────────────────┬────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│  Layer 1 — JMM + OS thread                                  │
│    happens-before 규칙                                       │
│    memory barrier (LoadStore / StoreLoad)                   │
│    park / unpark  →  pthread_cond / futex                   │
│    1:1 thread mapping (HotSpot)                             │
└─────────────────────────────────────────────────────────────┘
```

### 각 키워드의 역할 — 한 줄씩

- **`synchronized`**: **상호 배제 + 가시성**을 동시에 보장. monitor enter/exit에서 자동으로 acquire/release barrier. JDK 6부터 Biased/Lightweight/Heavyweight 승격. JDK 15+에서 Biased 제거.
- **`volatile`**: **가시성과 ordering**만 보장. 원자성 없음. JIT가 store 뒤에 StoreLoad barrier, load 앞에 LoadLoad/LoadStore barrier 삽입. `i++` 같은 compound 안전하지 않음.
- **`final` 필드**: 생성자 마지막에 freeze action — 다른 스레드가 안전하게 publish된 객체의 final 필드를 보는 것을 보장. immutable 객체의 thread-safety 토대.
- **`j.u.c.atomic`**: `AtomicInteger`, `LongAdder`, `AtomicReference` — CAS 기반의 lock-free primitive. ConcurrentHashMap 등 상위 자료구조의 빌딩 블록.
- **`j.u.c.locks`**: `ReentrantLock`, `ReadWriteLock`, `StampedLock` — AQS(AbstractQueuedSynchronizer) 위에 올린 Java-level lock. tryLock·인터럽트·Condition 등 OS 모니터로는 못 하는 것을 제공.
- **`j.u.c` 컬렉션·동기화 도구**: `ConcurrentHashMap`, `BlockingQueue`, `Semaphore`, `CountDownLatch`, `CyclicBarrier`, `Exchanger`, `Phaser`.
- **`Executor` 계열**: 스레드 생성과 작업 큐를 분리. 직접 `new Thread()` 호출은 production 안티패턴.

### 실무 동시성 이슈 — 5대 유형

1. **공유 변수 race condition** — `volatile` 없거나 synchronized 누락. `i++`를 두 스레드에서.
2. **이중 체크 락(DCL) 실패** — `volatile` 없는 singleton 초기화. 부분 생성 객체 publish.
3. **데드락** — 다른 순서로 두 lock을 잡음 (Q6 참조).
4. **라이브락 / 스타베이션** — `tryLock` 무한 retry, 또는 `synchronized`의 unfair monitor에서 한 스레드가 영원히 못 잡음.
5. **스레드 풀 고갈 (pool starvation)** — blocking IO를 fixed pool에서 호출, 모든 워커가 await 상태. 새 요청 큐에 쌓임 → SLA 위반.

### 운영 경험 매핑

| 증상 | 진단 명령 | 보통의 원인 |
|---|---|---|
| 응답 시간 spike + CPU 평온 | `jstack` → BLOCKED 다수 | synchronized 컨텐션 (Q6, Q8) |
| 모든 워커가 WAITING (parking) | `jstack` → `LockSupport.park` stack | 풀 고갈, 외부 IO blocking |
| 같은 값이 두 번 계산됨 | 코드 리뷰 | `volatile` 누락 DCL |
| OOM: unable to create new native thread | `cat /proc/<pid>/status` Threads | unbounded `newCachedThreadPool` |
| CPU 100% but 진척 없음 | async-profiler CPU profile | 라이브락 (CAS retry loop) |

### 한 줄 정리

> "동시성 답을 시작할 때 항상 3층 스택을 먼저 그립니다. 면접관이 어느 층 질문을 했는지 명시하고, 위→아래 인과 사슬을 끝까지 따라가는 게 시니어의 답입니다."

---

## Q2. JVM 스레드 스케줄링 + OS 스레드와의 관계

### 한 줄 정의

> HotSpot의 `java.lang.Thread`는 **OS native thread와 1:1 매핑**됩니다. JVM에는 자체 scheduler가 없습니다. `Thread.start()`는 결국 `pthread_create()` 같은 native call, `park/unpark`는 OS의 `futex` 또는 `pthread_cond`. 스케줄링은 100% OS에 위임됩니다.

### 1:1 매핑 도식

```
Java                    JVM (HotSpot)                  OS (Linux)
─────                   ──────────────                 ────────────
new Thread(r)
  ↓
.start()  ──────►  JVM_StartThread (jvm.cpp)
                     ↓
                   os::create_thread()
                     ↓
                   pthread_create() ───────►   clone(2) syscall
                                                 ↓
                                              kernel task (LWP)
                                                 ↓
                                              CFS scheduler

park()  ─────►   Unsafe.park  →  os::PlatformEvent::park
                                    ↓
                                  pthread_cond_wait
                                    ↓
                                  futex(FUTEX_WAIT)
                                    ↓
                                  스레드 RUNNING → INTERRUPTIBLE
                                  (CPU에서 내려옴)

unpark(t)  ─►   Unsafe.unpark  →  os::PlatformEvent::unpark
                                    ↓
                                  pthread_cond_signal
                                    ↓
                                  futex(FUTEX_WAKE)
                                    ↓
                                  OS scheduler가 runqueue에 추가
```

### 왜 1:1인가 — 역사

- **JDK 1.0~1.1**: M:N "green thread" — 사용자공간에서 JVM이 스케줄링. 멀티코어 활용 불가, blocking syscall 한 번에 전체 JVM stall.
- **JDK 1.2+ (HotSpot)**: 1:1 native thread로 전환. 멀티코어 즉시 활용, blocking syscall이 한 스레드만 멈춤. 단, 스레드당 메모리(stack ~1MB) + context switch 비용이 한계.
- **JDK 21 Loom (Virtual Thread)**: 다시 M:N으로 — 단, JVM이 carrier thread 위에서 continuation을 swap하는 형태. (별도 문서 참조)

### Thread state — Java vs OS

| Java state (`Thread.State`) | OS 상태 | 의미 |
|---|---|---|
| `NEW` | (생성 전) | `start()` 호출 전 |
| `RUNNABLE` | RUNNING 또는 RUNNABLE (runqueue) | CPU 위 또는 대기 중. Java는 둘을 구분 안 함 |
| `BLOCKED` | INTERRUPTIBLE | **synchronized monitor 진입 대기**. OS mutex 큐 |
| `WAITING` | INTERRUPTIBLE | `Object.wait()`, `LockSupport.park()`, `Thread.join()` |
| `TIMED_WAITING` | INTERRUPTIBLE (timeout) | `sleep`, `park(timeout)`, `wait(timeout)` |
| `TERMINATED` | (해제됨) | `run()` 종료 |

핵심 함정: **`RUNNABLE`은 CPU 위에 있다는 보장이 아닙니다.** OS의 runqueue에서 차례를 기다리는 것도 RUNNABLE. async-profiler의 wall-clock 모드로만 실제 on-CPU를 식별합니다.

### park / unpark 내부

```c
// HotSpot의 Unsafe.park 구현 (단순화)
void Unsafe_Park(jobject thread, jboolean isAbsolute, jlong time) {
    JavaThread* jt = ...;
    jt->parker()->park(isAbsolute, time);
    // ↑ 내부에서 pthread_mutex_lock + pthread_cond_wait
    //   → futex(FUTEX_WAIT) syscall
}
```

`park` semantics:
- **permit 1개짜리 binary semaphore**. `unpark`가 permit 1개를 주고, `park`가 1개를 소비.
- `unpark`가 `park`보다 먼저 와도 안전 — permit이 미리 쌓임.
- `Object.wait/notify`와 달리 monitor lock을 보유한 상태에서 호출할 필요 없음. AQS의 핵심.

### 운영 진단 — OS 레벨

```
# Java 스레드와 OS LWP 매핑
jstack <pid> | grep nid                  # nid가 OS의 LWP id (10진수로 변환 필요)
top -H -p <pid>                          # 스레드별 CPU%
ps -L -p <pid> -o pid,tid,stat,cmd       # OS 스레드 상태

# park 중인 스레드 추적
jstack <pid> | grep -A 5 "parking to wait for"
# nid 매칭 → top -H에서 그 nid가 sleep state(S)임을 확인
```

### 한 줄 정리

> "HotSpot의 Java 스레드는 OS 스레드와 1:1입니다. JVM에는 scheduler가 없고, park/unpark는 결국 futex로 내려갑니다. 그래서 `jstack`의 RUNNABLE은 'on-CPU'가 아니라 'OS runqueue 어딘가'를 의미하고, wall-clock profiler가 필요합니다."

---

## Q3. synchronized · ReentrantLock · StampedLock — 내부 동작과 성능 차이

### 한 줄 정의

> 셋 모두 상호 배제를 제공하지만 **레이어가 다릅니다**. `synchronized`는 JVM-level (Mark Word + ObjectMonitor), `ReentrantLock`은 Java-level (AQS state machine), `StampedLock`은 Java-level + optimistic read (versioned lock). 컨텐션 패턴에 따라 성능이 10배 차이 납니다.

### synchronized — Mark Word 승격 (JDK 6 → JDK 15+)

```
Mark Word (객체 헤더 첫 8 byte)의 lock state 2 bits로 4상태 표시.

[1] Unlocked
       │  첫 thread가 진입
       ▼
[2] Biased (JDK 15에서 deprecated, JDK 18에서 제거)
       │  다른 thread가 경쟁
       ▼
[3] Lightweight Locked (CAS + LockRecord)
       │  스핀 실패, 진짜 컨텐션
       ▼
[4] Heavyweight Locked (ObjectMonitor — OS mutex + wait queue)
       │  대기 thread는 park
       ▼  (jstack에서 BLOCKED)
   monitor exit → 다음 대기자 unpark
```

핵심 포인트:
- **Lightweight Lock**: CAS로 LockRecord(스택 위에 위치)의 포인터를 Mark Word에 박음. 스핀 몇 번 → 성공하면 OS 진입 없이 끝. 빠르다.
- **Heavyweight Lock**: `ObjectMonitor` 객체를 heap에 새로 할당, Mark Word는 그 포인터를 가리킴. 대기 스레드는 `pthread_cond_wait` → futex. `jstack`이 BLOCKED로 보여주는 게 이 단계.
- **Biased Lock 제거 이유**: revoke 비용이 컸고, 대부분의 현대 워크로드(reactive, 가상 스레드)에서 single-thread 가정이 깨짐. 유지 비용 > 이득.

### ReentrantLock — AQS state machine

```
AbstractQueuedSynchronizer (AQS) 구조:

  volatile int state;     // 0 = unlocked, N = 재진입 횟수
  Thread exclusiveOwner;  // 현재 잡고 있는 thread
  Node head, tail;        // CLH-style FIFO 대기 큐

lock():
  if (CAS(state, 0 → 1))                  // fast path
     owner = currentThread; return;
  if (owner == currentThread)             // reentrant
     state++; return;
  // 컨텐션:
  enqueue(currentThread);                 // FIFO에 노드 추가
  LockSupport.park(this);                 // futex 대기

unlock():
  if (--state == 0) {
     owner = null;
     LockSupport.unpark(head.next.thread); // 다음 대기자 깨움
  }
```

ReentrantLock이 `synchronized`보다 우월한 자리:
- **`tryLock(timeout)`** — synchronized로는 불가능. 데드락 회피의 핵심 도구.
- **`lockInterruptibly()`** — 대기 중 인터럽트 가능.
- **여러 `Condition`** — `notify`/`notifyAll`로 한 wait set에 묶인 synchronized와 달리, 생산자/소비자 등 역할별 condition 분리.
- **`fair=true`** — FIFO 보장. 단 throughput 30~50% 떨어짐.

### StampedLock — optimistic read

```
3가지 모드:
  writeLock()        — 배타. ReentrantLock과 유사.
  readLock()         — 공유. 다중 reader 허용.
  tryOptimisticRead() — lock을 잡지 않고 version stamp만 받음
                        → 읽기 후 validate(stamp)로 변경 여부 확인

흐름:
  long stamp = sl.tryOptimisticRead();   // lock X, stamp만 받음
  int x = field;                          // race 가능
  if (!sl.validate(stamp)) {              // 그 사이 write 있었나?
      stamp = sl.readLock();              // 정직하게 readLock 잡고 재읽기
      try { x = field; }
      finally { sl.unlockRead(stamp); }
  }
  // x 사용
```

핵심:
- read가 write보다 압도적으로 많은 워크로드(읽기 90%+)에서 ReadWriteLock보다 2~4배 빠름.
- 단, **재진입 안 됨**, **Condition 없음**, **잘못 쓰면 데이터 깨짐**. validate 빼먹으면 torn read.
- 인터페이스 호환성 없음 (Lock 인터페이스 구현 X). 라이브러리 코드에 끼우기 어려움.

### 셋의 성능·기능 비교

| 항목 | synchronized | ReentrantLock | StampedLock |
|---|---|---|---|
| 레이어 | JVM (Mark Word) | Java (AQS) | Java (versioned AQS) |
| Uncontended fast path | CAS 1번 (Lightweight) | CAS 1번 | CAS 1번 |
| Contended | OS mutex + park | park + FIFO | park + FIFO |
| 재진입 | O | O | **X** |
| tryLock | X | O | O |
| Timeout | X | O | O |
| Condition | 1개 (wait/notify) | N개 | X |
| Fair 옵션 | X (unfair만) | O | X |
| 가상 스레드 pinning | **O (carrier에 고정)** | X | X |
| 인터페이스 | language | `Lock` | (자체) |
| 권장 자리 | 짧고 간단한 critical section | 복잡한 lock 패턴, Condition 필요 | 읽기 압도적 + 짧은 critical section |

### 운영 진단

```
# synchronized 컨텐션
jstack <pid> | grep -c "BLOCKED"              # heavy contention 카운트
jstack <pid> | grep -B 2 "BLOCKED" | sort | uniq -c | sort -rn   # hot monitor

# AQS lock 컨텐션
jstack <pid> | grep "parking to wait for.*ReentrantLock"

# JFR이 가장 정확
jcmd <pid> JFR.start filename=lock.jfr settings=profile duration=60s
# JMC에서: Java Monitor Wait, Java Monitor Blocked 이벤트
```

### 한 줄 정리

> "synchronized는 JVM이 Mark Word로 짧게 끝내려 노력하다 진짜 컨텐션이면 OS mutex로 승격합니다. ReentrantLock은 같은 일을 Java의 AQS state machine으로 하되 tryLock/Condition을 추가로 줍니다. StampedLock은 읽기 압도적 워크로드에서 'lock 자체를 안 잡는' 길을 열어줍니다."

---

## Q4. volatile — 가시성 보장 방식과 한계

### 한 줄 정의

> `volatile`은 **가시성과 ordering**만 보장합니다. JIT가 store 뒤에 StoreLoad barrier, load 앞에 LoadLoad/LoadStore barrier를 삽입해 다른 코어가 즉시 최신 값을 보도록 만듭니다. **원자성은 없습니다** — `count++`는 read-modify-write 세 단계라 race 발생.

### JMM 관점 — happens-before

```
volatile write 와 volatile read 의 happens-before:

Thread A:                          Thread B:
   x = 42;                            // 시간상 A 다음에 실행됨
   flag = true;   // volatile         if (flag) {       // volatile
   //  ↓ happens-before                  // ↓ A의 x = 42가 보장됨
                                         use(x);
                                      }

규칙:
  volatile store(flag=true) HB volatile load(flag) HB use(x)
  → 전이성에 의해 A의 모든 이전 write 가 B 에 보임 (publication)
```

핵심: volatile은 **그 변수 자체**의 가시성만이 아니라, **그 store 이전의 모든 write의 가시성**까지 publish합니다. 이게 immutable 객체의 safe publication 토대.

### JIT가 삽입하는 memory barrier

```
volatile store (예: flag = true):
   ASM:  mov   [flag], 1
         mfence              ← StoreLoad barrier (x86 기준 가장 비싼 barrier)
         
volatile load (예: if (flag)):
   ASM:  mov   eax, [flag]
         // x86은 load-load ordering이 자동 보장이라 barrier 생략 가능
         // ARM/PowerPC는 명시 barrier 필요 (dmb ish 등)
```

x86 vs ARM 차이:
- **x86 (TSO)**: store-store, load-load, load-store 순서가 자동 보장. StoreLoad만 명시 barrier(mfence).
- **ARM (weak memory model)**: 모든 ordering을 명시 barrier로 강제. volatile 한 번에 더 많은 instruction 삽입.

### 원자성 없음 — compound action 실패

```java
volatile int counter = 0;

// 두 스레드가 동시에:
counter++;
// 내부:
//   1. r1 = load(counter)
//   2. r1 = r1 + 1
//   3. store(counter, r1)
// 두 스레드가 같은 r1을 읽고 같은 +1을 store하면 +1만 반영.
```

해결: `AtomicInteger.incrementAndGet()` — CAS loop로 원자성 확보.

### volatile이 빛나는 자리 — DCL 싱글톤

```java
class Singleton {
    private static volatile Singleton instance;   // ★ volatile 필수
    
    public static Singleton getInstance() {
        Singleton local = instance;
        if (local == null) {                       // 1차 체크 (lock 없이)
            synchronized (Singleton.class) {
                local = instance;
                if (local == null) {               // 2차 체크
                    local = new Singleton();        // ★ 부분 생성 publication
                    instance = local;
                }
            }
        }
        return local;
    }
}
```

`volatile` 없으면:
- `new Singleton()`은 (a) 메모리 할당, (b) 생성자 실행, (c) 참조 publish 세 단계.
- JIT가 (c)를 (b) 앞으로 reorder 가능 → 다른 스레드가 **부분 생성된 객체**를 봄.
- NPE보다 더 나쁨 — 생성자 초기화 안 된 필드를 사용. 디버깅 지옥.

### volatile의 진짜 한계 정리

1. **원자성 없음** — `++`, `--`, `+=` 등 compound 모두 안전하지 않음.
2. **다중 변수 일관성 없음** — `volatile int x, y;` 두 개를 함께 갱신하려면 lock 필요.
3. **long·double의 word tearing** — 32비트 JVM에서 non-volatile long은 두 번에 나눠 write 가능. volatile은 단일 atomic 보장.
4. **happens-before는 동기화 지점만** — 그 사이 reordering은 여전히 가능.

### 운영에서의 흔한 실수

| 코드 | 문제 |
|---|---|
| `volatile int hits; hits++;` | 카운트 누락. `LongAdder` 또는 `AtomicLong` 사용 |
| `volatile Map<K,V> map;` | map 자체 참조만 volatile, 내부 변경은 race. `ConcurrentHashMap` 사용 |
| volatile 없는 DCL | 부분 생성 객체 publication |
| `volatile boolean[] flags` | 배열 참조만 volatile, 원소 변경은 가시성 X. `AtomicReferenceArray` 사용 |

### 한 줄 정리

> "volatile은 ordering과 publication 도구이지 mutual exclusion 도구가 아닙니다. 단일 write를 publish하거나 single-writer/multi-reader 플래그에 쓰고, 카운터·다중 변수에는 절대 안 됩니다. 원자성이 필요하면 j.u.c.atomic, 일관성이 필요하면 lock입니다."

---

## Q5. java.util.concurrent — 주요 클래스 동작 원리와 실전 적용

### 한 줄 정의

> `j.u.c`는 **AQS(동기화 도구의 80%) + CAS-기반 컬렉션 + Executor 추상화** 세 묶음입니다. 한 클래스를 알면 같은 묶음의 형제들이 줄줄이 풀립니다.

### 5.1 ThreadPoolExecutor — work queue 모델

```
ThreadPoolExecutor의 핵심 파라미터:
  corePoolSize, maximumPoolSize, keepAliveTime,
  BlockingQueue<Runnable> workQueue,
  RejectedExecutionHandler

execute(task) 분기:
  ┌─────────────────────────────────────────┐
  │ 1. workerCount < corePoolSize?          │
  │    → 새 worker 생성, task 실행          │
  ├─────────────────────────────────────────┤
  │ 2. 큐에 offer 성공?                     │
  │    → task가 큐에 쌓임                   │
  ├─────────────────────────────────────────┤
  │ 3. workerCount < maximumPoolSize?       │
  │    → 새 worker 생성, task 실행          │
  ├─────────────────────────────────────────┤
  │ 4. 그 외                                │
  │    → RejectedExecutionHandler 호출      │
  │       (AbortPolicy/CallerRuns/Discard)  │
  └─────────────────────────────────────────┘
```

운영의 함정:
- **`Executors.newCachedThreadPool()`** = `max=Integer.MAX_VALUE` + `SynchronousQueue`. 부하 spike에서 스레드 무한 생성 → `unable to create new native thread`.
- **`Executors.newFixedThreadPool()`** = unbounded `LinkedBlockingQueue`. queue 무한 증가 → OOM.
- 권장: **직접 `new ThreadPoolExecutor(...)`** + bounded queue + `CallerRunsPolicy`(backpressure) 또는 별도 reject 정책.

### 5.2 Future · CompletableFuture

```
Future<T>:
  - get() 호출 시 blocking. 결과 또는 예외.
  - cancel() 가능하지만 외부 인터럽트만 가능. 작업 중단은 task 코드가 협조해야.

CompletableFuture<T>:
  - thenApply / thenCompose / thenCombine / handle / exceptionally
    → callback 체인. 각 단계가 별도 스레드에서 실행 가능.
  - default executor 는 ForkJoinPool.commonPool().
  - thenApplyAsync(fn, executor) 로 명시 executor 지정 권장.
```

함정:
- `thenApply`는 **이전 단계와 같은 스레드**에서 실행될 수도, 호출 스레드에서 실행될 수도 있음. `Async` suffix를 쓰지 않으면 비결정적.
- `commonPool` 크기 = CPU - 1. 여기서 blocking IO 하면 전체 reactive 코드 stall.

### 5.3 ConcurrentHashMap — segmented → CAS 진화

```
JDK 7-: Segment 배열 (기본 16개)
   각 Segment 는 ReentrantLock 보유 → 같은 segment 내에서만 lock contention
   → 16-way 분산. write 동시성 = segment 수.

JDK 8+: Segment 제거, bin 단위 lock
   table[i] (bin):
     - 비어 있으면 CAS로 첫 노드 삽입
     - 노드가 있으면 첫 노드를 synchronized 로 잡고 chain append
     - chain 이 길어지면 (TREEIFY_THRESHOLD=8) red-black tree 로 변환
   → 사실상 bin-level locking. 8-9 way 분산보다 훨씬 fine-grained.
   → resize 도 multi-thread cooperative (helpTransfer).
```

핵심 특성:
- **`get()`은 lock 없음**. volatile read만으로 안전.
- `compute / computeIfAbsent / merge` 가 atomic. **single-key 트랜잭션**의 핵심 API.
- iterator 는 weakly consistent — `ConcurrentModificationException` 안 던짐, 다만 동시 변경이 보일 수도 안 보일 수도 있음.

### 5.4 BlockingQueue — Producer/Consumer

```
ArrayBlockingQueue:  bounded, 단일 ReentrantLock + notFull/notEmpty Condition.
LinkedBlockingQueue: optionally bounded. Head/Tail에 2개의 lock (양쪽 동시 진행 가능).
SynchronousQueue:    버퍼 없음. put 한 스레드가 take 한 스레드를 직접 만남.
                     newCachedThreadPool 의 핵심 — 빈 큐가 즉시 새 worker 생성을 유발.
LinkedTransferQueue: 비차단 + 무경계. CAS 기반, 매우 빠름.
PriorityBlockingQueue: heap 기반 priority. unbounded.
DelayQueue:          만료 시간이 지난 원소만 take 가능. scheduling 용.
```

선택 기준:
- 처리량 우선 + 양방향 동시성: `LinkedBlockingQueue` (2-lock) 또는 `LinkedTransferQueue` (CAS).
- 메모리 안전 (bounded) 필수: `ArrayBlockingQueue`.
- 직접 handoff (worker 즉시 생성): `SynchronousQueue`.

### 5.5 동기화 도구 — Latch · Barrier · Semaphore

```
CountDownLatch(N):
   - countDown() N번 호출되면 await() 깨어남.
   - one-shot. 재사용 불가.
   - 용도: 시작 신호("모든 worker 준비됐을 때 동시 출발"), 종료 대기.

CyclicBarrier(N, action):
   - N개의 스레드가 await()에 모이면 모두 깨어남. action 실행 후 자동 reset.
   - 용도: phase별 병렬 계산 ("모든 worker 가 phase k 끝낸 뒤 phase k+1 진행").
   - 한 스레드라도 인터럽트되면 BrokenBarrierException → 전체 reset.

Semaphore(N):
   - N개의 permit. acquire/release로 동시 진입 제한.
   - 용도: 외부 API 호출 동시성 제한, connection pool, rate limiting.
   - fair=true 로 FIFO 보장 가능 (throughput 손해).

Phaser:
   - CyclicBarrier 확장. 동적으로 참가자 추가/제거 가능.
   - tree로 계층 구성해 큰 N 에서도 scalability 유지.

Exchanger<V>:
   - 두 스레드가 서로 값을 교환.
   - rarely used. 파이프라인의 double-buffering 등.
```

AQS 위에 얹힌 것들:
- `ReentrantLock`, `ReentrantReadWriteLock`, `Semaphore`, `CountDownLatch`, `SynchronousQueue`(부분), `FutureTask`, `StampedLock`(자체 변형).
- 한 줄 요약: **AQS의 `state` 필드를 클래스마다 다르게 해석**. `Semaphore`는 state=permit 수, `CountDownLatch`는 state=count, `ReentrantLock`은 state=재진입 횟수.

### 운영 진단 — j.u.c

```
# 풀 고갈 (모든 worker가 await 중)
jstack <pid> | grep -A 5 "java.util.concurrent" | grep -c "parking to wait"

# Latch/Barrier에 모인 스레드들
jstack <pid> | grep -B 2 "AbstractQueuedSynchronizer\$ConditionObject"

# ConcurrentHashMap resize 중 helpTransfer
jstack <pid> | grep "helpTransfer"   # 흔하진 않지만 발견되면 큰 resize 진행 중
```

### 한 줄 정리

> "j.u.c의 동기화 도구는 거의 모두 AQS의 state 해석을 다르게 한 변형입니다. 컬렉션 쪽은 segmented lock에서 CAS+bin-level lock으로 진화했습니다. ThreadPoolExecutor는 `Executors.newXxx` 헬퍼를 피하고 직접 bounded queue로 구성하는 게 시니어의 기본 자세입니다."

---

## Q6. 데드락 · 라이브락 · 스타베이션 — 실전 발생과 해결

### 한 줄 정의

> 셋은 모두 "스레드가 진행을 못 함" 증상이지만 원인이 다릅니다. **데드락**=상호 lock 보유로 순환 대기, **라이브락**=서로 양보하느라 진행 안 됨, **스타베이션**=특정 스레드만 영원히 lock 못 잡음. 진단 도구도 다르고 해결 전략도 다릅니다.

### 데드락 — Coffman's 4 conditions

```
4가지가 모두 만족하면 데드락 가능:
  1. Mutual Exclusion       — lock이 배타적
  2. Hold and Wait          — lock 잡은 채 다른 lock 대기
  3. No Preemption          — 외부가 lock 빼앗을 수 없음
  4. Circular Wait          — T1→L2 대기, T2→L1 대기 (cycle)

Java 에서는 1·2·3은 항상 참 (synchronized/Lock의 성질).
→ **4번 cycle을 깨는 것**이 유일한 예방책.
```

전형적 데드락 코드:

```java
// 두 스레드가 lock A, B를 다른 순서로 잡으면 cycle.
void transfer(Account a, Account b, int amount) {
    synchronized (a) {          // T1: a→b
        synchronized (b) {       // T2: b→a
            ...
        }
    }
}
```

해결 — **lock ordering**:

```java
void transfer(Account a, Account b, int amount) {
    // 항상 id 작은 쪽 먼저
    Account first = a.id < b.id ? a : b;
    Account second = a.id < b.id ? b : a;
    synchronized (first) {
        synchronized (second) {
            ...
        }
    }
}
```

대안 — **tryLock + timeout**:

```java
if (lockA.tryLock(1, TimeUnit.SECONDS)) {
    try {
        if (lockB.tryLock(1, TimeUnit.SECONDS)) {
            try { /* work */ } finally { lockB.unlock(); }
        } else { /* 양보, 재시도 */ }
    } finally { lockA.unlock(); }
}
```

진단 — `jstack`이 자동 cycle 탐지:

```
jstack -l <pid> 출력 마지막에:

Found one Java-level deadlock:
=============================
"Thread-1":
  waiting to lock monitor 0x...,
  which is held by "Thread-2"
"Thread-2":
  waiting to lock monitor 0x...,
  which is held by "Thread-1"

Java stack information for the threads:
"Thread-1": ...
"Thread-2": ...
```

`jconsole`, JMC, jcmd `Thread.print -l` 모두 같은 탐지를 제공합니다. **단, AQS 기반 lock(`ReentrantLock`)은 이 탐지가 100% 정확하지 않습니다** — JVM은 native monitor만 자동 cycle 분석. AQS는 `-l`로 lock owner 정보를 출력해 수동 추적.

### 라이브락

```
T1: lockA.tryLock() 성공 → lockB.tryLock() 실패 → lockA 풀고 yield
T2: lockB.tryLock() 성공 → lockA.tryLock() 실패 → lockB 풀고 yield
→ 둘 다 영원히 반복. CPU 100%, 진행 0%.
```

진단:
- `jstack` 두 번 떠보면 같은 자리 스핀 안 함 — RUNNABLE이지만 매번 다른 코드 라인.
- async-profiler CPU profile에서 `tryLock` 호출이 hot.
- BLOCKED 없음 (데드락과 다른 점).

해결:
- **랜덤 backoff**: `Thread.sleep(random.nextInt(jitter))`.
- 또는 deterministic lock ordering으로 회피.

### 스타베이션

```
원인 예:
  1. synchronized 의 unfair monitor → 한 스레드만 계속 잡음
  2. ReentrantLock fair=false (기본) 에서 운 나쁜 스레드
  3. ReadWriteLock 에서 reader 가 너무 많아 writer 영원히 못 잡음
  4. Priority가 낮은 스레드가 CPU 못 받음 (OS 레벨)
```

진단:
- `jstack` 여러 번 뜨면 같은 스레드가 항상 BLOCKED.
- 그 스레드의 CPU 시간이 다른 스레드의 1/10 이하.

해결:
- `ReentrantLock(true)` fair mode (throughput 30~50% 손해 감수).
- `StampedLock`의 write preference 옵션.
- 작업을 잘게 쪼개서 lock hold time 단축.

### 실전 케이스 매핑

| 실전 시나리오 | 유형 | 1차 도구 | 해결 |
|---|---|---|---|
| 결제 처리에서 두 계좌 동시 갱신, 가끔 멈춤 | 데드락 | `jstack -l` | lock ordering by id |
| DB connection pool에서 모두 awaitConnection | 데드락 (외부) | `jstack` + DB lock 확인 | 트랜잭션 짧게, query timeout |
| CAS retry loop CPU 100% | 라이브락 | async-profiler | backoff 또는 lock 으로 전환 |
| 모니터링 스레드만 매번 BLOCKED | 스타베이션 | jstack 반복 | fair lock 또는 RW lock 재설계 |
| Reader 가 많아 Writer 가 못 잡음 | 스타베이션 | jstack: 한 스레드 WAITING for write | StampedLock 또는 writer priority |

### 한 줄 정리

> "데드락은 자동 탐지(jstack)·예방(lock ordering)·복구(tryLock timeout) 세 카드, 라이브락은 backoff, 스타베이션은 fair lock 또는 잘게 쪼개기. 셋의 진단을 `jstack`의 BLOCKED 여부로 1차 분리합니다 — BLOCKED 다수면 데드락/컨텐션, BLOCKED 없는데 CPU 100%면 라이브락, 한 스레드만 BLOCKED 반복이면 스타베이션."

---

## Q7. Fork/Join 프레임워크 + Parallel Stream — 내부와 함정

### 한 줄 정의

> Fork/Join은 **divide-and-conquer 병렬 처리 프레임워크**. 핵심 자료구조는 **work-stealing deque** — 각 worker가 자기 deque의 한쪽 끝에서 작업을 push/pop, 다른 worker는 그 deque의 반대 끝에서 steal. Parallel Stream은 내부적으로 `ForkJoinPool.commonPool()`을 씁니다 — 그래서 함정이 큽니다.

### Work-Stealing Deque 도식

```
Worker W1                    Worker W2                  Worker W3
┌───────────┐               ┌───────────┐              ┌───────────┐
│ deque     │               │ deque     │              │ deque (empty)
│ ┌───────┐ │               │ ┌───────┐ │              │           │
│ │ task5 │ │ ← W1이 push   │ │ task3 │ │              │           │
│ │ task4 │ │               │ │ task2 │ │              │           │
│ │ task3 │ │               │ │ task1 │ │              │           │
│ │ task2 │ │               │ └───────┘ │              │           │
│ │ task1 │ │ ← W3가 steal  │           │              │           │
│ └───────┘ │     (반대 끝) │           │              │           │
│  ↑ W1 pop │               │           │              │           │
└───────────┘               └───────────┘              └───────────┘

규칙:
  - owner W1 은 LIFO (스택처럼). 최근 push 한 것을 먼저 pop.
    → 캐시 locality, 더 작은 subtask 먼저 처리.
  - thief W3 은 FIFO (큐의 반대 끝). 가장 오래된 task 를 steal.
    → 큰 subtask 를 가져가 자기가 다시 split. cache contention 최소.
  - deque 가 비면 thief 가 다른 worker 에게서 steal.
```

핵심 효과:
- Owner와 thief가 deque의 반대 끝을 만지니 lock 거의 안 필요 (CAS만).
- 큰 subtask가 stealing 대상이 되어 worker 간 load 자동 balance.
- 깊이 우선 분할로 working set이 작게 유지 → 캐시 친화.

### ForkJoinPool.commonPool() — 공유 인프라

```
JDK 8+ 부터 JVM 공통 ForkJoinPool 하나가 자동 존재.

크기: Runtime.getRuntime().availableProcessors() - 1
사용처:
  - parallelStream() 의 모든 호출
  - CompletableFuture 의 default executor
  - 일부 j.u.c 내부 (CompletableFuture, Arrays.parallelSort 등)

→ 한 곳에서 commonPool 을 점유하면 모든 곳이 영향.
```

### Parallel Stream의 6대 함정

1. **commonPool 공유** — `list.parallelStream().forEach(...)` 안에서 blocking IO 호출 → commonPool worker 점유 → 다른 parallelStream/CompletableFuture까지 stall.
   - 해결: `ForkJoinPool` 별도 생성 후 `customPool.submit(() -> stream.parallel().sum()).get()` 패턴.

2. **Spliterator 분할 비용** — `LinkedList.parallelStream()`은 sequential 보다 더 느림. 분할에 O(n) 걸림. `ArrayList`/`int[]`만 효과 큼.

3. **순서 보장 비용** — `forEach` vs `forEachOrdered`. 후자는 chunk 결과를 다시 직렬화 → 병렬 의미 반감.

4. **공유 가변 상태** — `parallelStream().forEach(x -> sharedList.add(x))` → race. `collect(toList())`로 reduce 형태로 모아야 안전.

5. **boxing 비용** — `Stream<Integer>.parallel().sum()`은 boxing이 hot path. `IntStream`을 쓰자.

6. **작업이 너무 짧음** — 작은 task가 너무 많으면 fork/join 오버헤드가 작업 자체보다 큼. 경험칙: 한 element 처리에 >100ns 정도면 의미 있음.

### Fork/Join 적용 예 — Recursive Task

```java
class SumTask extends RecursiveTask<Long> {
    final long[] arr;
    final int lo, hi;
    static final int THRESHOLD = 10_000;
    
    public Long compute() {
        if (hi - lo <= THRESHOLD) {              // base case
            long s = 0;
            for (int i = lo; i < hi; i++) s += arr[i];
            return s;
        }
        int mid = (lo + hi) >>> 1;
        SumTask left  = new SumTask(arr, lo, mid);
        SumTask right = new SumTask(arr, mid, hi);
        left.fork();                             // deque에 push, 다른 worker가 steal 가능
        long r = right.compute();                // 자기가 직접 (캐시 locality)
        long l = left.join();                    // left 결과 기다림
        return l + r;
    }
}
```

핵심 포인트:
- **`fork()` 1번 + `compute()` 직접 1번 + `join()` 1번** 패턴. 둘 다 fork하면 자기 deque에 그냥 쌓여서 stealing 효과 약화.
- THRESHOLD 가 너무 작으면 task 오버헤드 폭발, 너무 크면 병렬화 못 함.

### 운영 진단

```
# commonPool 점유 확인
jstack <pid> | grep -A 5 "ForkJoinPool.commonPool" | grep -v "Idle"
jstack <pid> | grep -c "RUNNABLE.*ForkJoinPool"

# parallelStream 안의 blocking IO 탐지
jstack <pid> | grep -B 3 "socketRead0\|SocketRead" | grep "ForkJoinPool"
# ↑ 이게 나오면 commonPool worker 가 IO blocking 중 = 안티패턴

# 별도 pool 사용 검증 — CompletableFuture 도 commonPool 쓰니까
```

### 한 줄 정리

> "Fork/Join은 work-stealing deque로 worker 간 load balance를 자동화합니다. Parallel Stream은 그 위에 얇게 얹힌 syntactic sugar지만 commonPool 공유 + blocking IO + 공유 가변 상태가 3대 지뢰입니다. 단순 `int[]` 합 같은 CPU-bound + immutable + 큰 데이터에서만 안전하게 효과 봅니다."

---

## Q8. Thread Dump 분석 — 병목 진단 방법

### 한 줄 정의

> Thread Dump는 **"순간"의 스냅샷**. 한 번 떠서는 정보가 부족하고, **3~5초 간격으로 3~5번** 뜨면 그 사이 스레드 state 변화로 hot 컨텐션·풀 고갈·데드락이 전부 드러납니다. JFR은 시계열로 같은 정보를 자동 기록합니다.

### Dump 채취 방법 — 4가지

```
# 1. jstack (가장 기본)
jstack <pid>                    # 모든 스레드 stack
jstack -l <pid>                 # + lock owner 정보 (deadlock 탐지 강화)
jstack -F <pid>                 # force (멈춘 JVM에 사용)

# 2. kill -3 (SIGQUIT)
kill -3 <pid>                   # JVM 의 stderr 에 thread dump 출력
                                # /proc/<pid>/fd/2 또는 stdout/stderr 리다이렉트 위치

# 3. jcmd (권장)
jcmd <pid> Thread.print -l      # jstack 과 동등, 더 안전 (force 모드 아님)

# 4. JFR (시계열, 운영 권장)
jcmd <pid> JFR.start name=t duration=60s filename=/tmp/t.jfr
# 이벤트: JavaThreadStatistics, ThreadDump, JavaMonitorEnter, JavaMonitorWait
```

### Thread State별 의미

```
RUNNABLE
  - CPU 위 또는 OS runqueue 대기.
  - "RUNNABLE이라고 일하는 게 아님" — IO syscall 대기 중도 RUNNABLE.
  - 실제 on-CPU 식별: async-profiler -e cpu 또는 perf.

BLOCKED (on object monitor)
  - synchronized monitor 진입 대기.
  - "waiting to lock <0x...>"  +  다른 스레드의 "locked <0x...>" 와 매칭.
  - Heavyweight Lock 단계 = OS mutex 큐 대기.

WAITING (parking)
  - LockSupport.park, Object.wait, Thread.join, CompletableFuture.get 등.
  - "parking to wait for <0x...>" + 그 사이클러스 추적.
  - AQS lock 대기, Condition.await, 풀 worker idle 등.

TIMED_WAITING
  - 위와 같지만 timeout 있음. sleep, park(timeout), wait(timeout).

TERMINATED, NEW
  - 거의 dump 에 안 나타남.
```

### 3대 패턴 — 빠른 분류 알고리즘

```
1. BLOCKED 많이 보임 (한 자물쇠에 모임)
   → synchronized 컨텐션 또는 데드락
   → "Found one Java-level deadlock" 확인
   → 없으면 hot monitor 찾기:
        jstack <pid> | grep "waiting to lock" | sort | uniq -c | sort -rn

2. WAITING (parking) 다수 + 큐 깊음
   → 풀 고갈 또는 외부 IO blocking
   → 풀 worker 들이 LinkedBlockingQueue.take 에서 park 면 정상 idle
   → DB JDBC 콜에서 park 면 외부 응답 지연
   → CompletableFuture.get 에서 park 면 async 체인 stall

3. RUNNABLE 다수 + CPU 100% + 진척 없음
   → CPU-bound 워크 (정상) 또는 라이브락 (이상)
   → async-profiler 로 hot stack:
        ./profiler.sh -d 30 -e cpu <pid>
   → tryLock retry 가 hot 이면 라이브락 확실
```

### 흔한 패턴별 stack 예시

```
[패턴 A — synchronized 컨텐션]
"http-nio-8080-exec-15" #345 daemon prio=5 ... waiting for monitor entry
   java.lang.Thread.State: BLOCKED (on object monitor)
   at com.foo.Service.process(Service.java:42)
   - waiting to lock <0x000000076c001234> (a com.foo.Cache)
   at ...

"http-nio-8080-exec-3" #333 daemon prio=5 ... runnable
   java.lang.Thread.State: RUNNABLE
   at com.foo.Service.process(Service.java:43)
   - locked <0x000000076c001234> (a com.foo.Cache)  ← 잡고 있는 자
   ...

→ exec-3 의 코드 라인 43 이 너무 오래 잡고 있음. critical section 축소 필요.
```

```
[패턴 B — DB connection pool 고갈]
"http-nio-8080-exec-21" ... waiting on condition
   java.lang.Thread.State: TIMED_WAITING (parking)
   at jdk.internal.misc.Unsafe.park(...)
   at java.util.concurrent.locks.LockSupport.parkNanos(...)
   at HikariCP.PoolBase.borrow(...)
   at HikariCP.HikariDataSource.getConnection(...)
   ...

→ HikariCP borrow 에서 park. connection 부족.
→ DB 의 slow query 또는 pool size 너무 작음.
```

```
[패턴 C — CompletableFuture 체인 stall]
"main" ... waiting on condition
   java.lang.Thread.State: WAITING (parking)
   at jdk.internal.misc.Unsafe.park(...)
   at java.util.concurrent.CompletableFuture.get(...)
   at ...

→ get() 이 외부 future 대기. 그 future 가 어디서 막혔는지 다른 스레드에서 추적.
   ForkJoinPool worker 들이 다 busy 면 commonPool 문제.
```

```
[패턴 D — 데드락 (jstack 자동 탐지)]
Found one Java-level deadlock:
=============================
"Thread-1":
  waiting to lock monitor 0x... (object 0x..., a java.lang.Object),
  which is held by "Thread-2"
"Thread-2":
  waiting to lock monitor 0x... (object 0x..., a java.lang.Object),
  which is held by "Thread-1"
```

### 시간축 분석 — 3번 뜨기

```
$ for i in 1 2 3; do jcmd <pid> Thread.print -l > dump-$i.txt; sleep 3; done

비교 포인트:
  - 같은 스레드가 같은 자리에서 3번 모두 RUNNABLE → 그 코드가 정말 hot
  - 같은 스레드가 매번 WAITING parking → idle 정상
  - 매번 다른 스레드가 BLOCKED for same monitor → 컨텐션 hot
```

### JFR — 시계열 자동 기록

```
jcmd <pid> JFR.start name=diag settings=profile duration=10m filename=/tmp/diag.jfr

JMC 로 열어 보기:
  - Java Application → Threads → Thread Latency
  - Java Application → Lock Instances (jdk.JavaMonitorEnter 이벤트)
  - Java Application → Java Thread Park (jdk.ThreadPark 이벤트)
  - jdk.JavaThreadStatistics (스레드 수 추세)

장점: thread dump 1회 vs JFR 의 수십~수백만 이벤트. P99 outlier 시점 정확히 찾을 수 있음.
```

### 실전 진단 워크플로우

```
1. SLA 위반 알람 ─┐
                  ↓
2. jcmd Thread.print 3번 (3초 간격)
                  ↓
3. State 분포 확인:
     - BLOCKED 다수 → 패턴 A (synchronized)
     - WAITING parking 다수 → 패턴 B (pool/IO)
     - RUNNABLE 다수 → 패턴 C (CPU-bound or 라이브락)
                  ↓
4. 패턴별 deep dive:
     A: hot monitor 식별, critical section 분석
     B: pool/외부 시스템 health check
     C: async-profiler CPU 프로파일 → hot stack
                  ↓
5. JFR 로 시간축 검증 (P99 spike 와 사건 매칭)
                  ↓
6. 가설 수립 → 수정 → 재현 → 검증
```

### 한 줄 정리

> "Thread Dump 분석의 핵심은 (a) 3번 떠서 변화 보기, (b) BLOCKED/WAITING/RUNNABLE 분포로 1차 분류, (c) 같은 monitor를 가리키는 스레드 묶음 찾기, (d) JFR로 시간축 검증. `jstack` 한 장으로 답을 내려 하지 말고, dump는 가설 검증의 도구일 뿐 진단 자체는 시계열에서 합니다."

---

## 종합 — 백지에서 줄줄 그릴 그림

```
┌──────────────────────────────────────────────────────────────────┐
│              JVM Concurrency — 한 장 마스터 맵                    │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  [언어 키워드]                                                    │
│    synchronized ─┐                                               │
│                  ├──► Mark Word ─► Lightweight (CAS) ─► Heavy   │
│    volatile ─────┴──► JIT barrier (StoreLoad/LoadLoad)          │
│                                                                  │
│  [j.u.c 라이브러리]                                              │
│    ReentrantLock ───► AQS state machine + park/unpark           │
│    Semaphore      ─┐                                             │
│    CountDownLatch ─┼─► 모두 AQS state 해석 다른 변형              │
│    StampedLock     ┘                                             │
│    CHM ─────► CAS + bin synchronized + cooperative resize       │
│    TPE ─────► corePoolSize ─► queue ─► maxPoolSize ─► reject    │
│    CF  ─────► commonPool ⚠️ (parallelStream 도 공유)             │
│    FJP ─────► work-stealing deque (LIFO owner, FIFO thief)      │
│                                                                  │
│  [JMM + OS]                                                      │
│    happens-before ─► safe publication                            │
│    park/unpark ───► futex ───► CFS scheduler                    │
│    1:1 thread mapping (HotSpot OS thread)                       │
│                                                                  │
│  [진단 도구]                                                      │
│    jstack/jcmd Thread.print ──► state 분포 1차 분류              │
│      BLOCKED 다수 → synchronized 컨텐션 / 데드락                  │
│      WAITING parking 다수 → 풀 고갈 / 외부 IO                    │
│      RUNNABLE + CPU 100% → CPU-bound or 라이브락                 │
│    JFR ───────────────────► 시계열, P99 outlier 정확             │
│    async-profiler ────────► CPU/wall-clock hot stack             │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 한 줄씩 종합 — 면접에서 던질 클로징

1. JVM 동시성은 언어 키워드 → j.u.c → JMM/OS 3층이고, 시니어의 답은 항상 위에서 아래로 인과를 따라갑니다.
2. HotSpot 스레드는 OS 스레드와 1:1이고 스케줄러는 OS에 위임됩니다 — RUNNABLE이 곧 on-CPU가 아님을 항상 인지합니다.
3. synchronized·ReentrantLock·StampedLock은 같은 mutual exclusion에 레이어가 다른 도구이며 워크로드 모양에 따라 선택합니다.
4. volatile은 publication·ordering 도구이지 mutex 도구가 아닙니다 — 원자성이 필요하면 atomic, 일관성은 lock입니다.
5. j.u.c의 동기화 도구는 AQS state 해석의 변형이며 컬렉션은 segmented → bin-level CAS로 진화했습니다.
6. 데드락은 자동 탐지·lock ordering·tryLock 세 카드, 라이브락은 backoff, 스타베이션은 fair 또는 작게 쪼개기입니다.
7. Parallel Stream은 commonPool 공유 + blocking IO + 공유 가변 상태 3대 지뢰를 늘 의심합니다.
8. Thread Dump 분석은 3번 떠서 시간축으로 보고, BLOCKED/WAITING/RUNNABLE 분포로 1차 분류한 뒤 JFR로 시간축 검증합니다.
