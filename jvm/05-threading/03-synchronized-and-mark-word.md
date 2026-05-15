# 05-03. synchronized + Mark Word 승격 (Biased → Lightweight → Heavyweight)

> `synchronized`는 **하나의 lock이 아니다**. Contention에 따라 자동 승격되는 **3단계 lock 메커니즘**.
> Biased (uncontended) → Lightweight (light contention) → Heavyweight (heavy contention). Mark Word의 2비트가 현재 상태를 표시.
> 시니어가 알아야 할 것: JDK 15+에서 Biased 제거됨. 현대 워크로드는 Lightweight ↔ Heavyweight 두 단계. 운영 진단 시 jstack의 BLOCKED는 Heavyweight monitor 대기.

---

## 🗺️ 위치

![mark word lock](./_excalidraw/03-synchronized-mark-word.svg)

---

## 📍 학습 목표

1. **Mark Word** — 객체 헤더 첫 8 byte. lock 상태 + GC age + hash 인코딩.
2. **3단계 Lock** 승격 메커니즘.
3. **Biased Lock의 동작과 제거 이유** — JDK 15+ deprecated.
4. **Lightweight Lock** — CAS + Stack의 LockRecord.
5. **Heavyweight Lock (Monitor)** — OS-level mutex, park/unpark.
6. **Park/Unpark 의 native 구현** — pthread_cond_wait/signal.
7. **synchronized vs ReentrantLock** — JVM lock vs Java-level lock.
8. **Lock Coarsening / Lock Elision** ([Chapter 03-06](../03-execution-engine/06-escape-analysis.md) 와 연결).
9. **jstack의 BLOCKED 상태** — Heavyweight monitor 대기.
10. 운영 시나리오: Lock contention 진단 / synchronized vs ReentrantLock 선택 / Virtual Thread + synchronized pinning ([04](./04-virtual-threads-and-loom.md)).

---

## 🎨 1단계: 백지 그리기 가이드

### Step 1: Mark Word 구조

```
64-bit Mark Word (Compressed Oops):
[unused:25][hash:31][unused:1][age:4][biased:1][lock:2]

lock:2 비트 의미:
   00: Lightweight (locked)
   01: Unlocked / Biased
   10: Heavyweight (Monitor)
   11: GC marked
```

### Step 2: 3단계 승격 흐름

```
[Initial: Unlocked]
   │ 첫 lock
   ▼
[Biased Lock] (단일 thread)
   │ 다른 thread 시도
   ▼ revoke
[Lightweight Lock] (CAS)
   │ CAS 실패 (contention)
   ▼
[Heavyweight Lock] (Monitor)
   │ Park/Unpark
```

### Step 3: JDK 15+ 변화

```
JDK 15-: Biased → Lightweight → Heavyweight
JDK 15+: (Biased deprecated) → Lightweight → Heavyweight
JDK 21+: Project Lilliput — Mark Word 압축 진행
```

### 정답 그림

위의 [03-synchronized-mark-word.svg](./_excalidraw/03-synchronized-mark-word.svg) 참조.

---

## 🧠 2단계: 직관

### 핵심 비유

> **회의실 예약 비유**:
> - **Biased** = 한 사람이 항상 사용 → 명패만 붙임 (가장 빠름).
> - **Lightweight** = 가끔 다른 사람도 사용 → 명패 갈아 끼움 (CAS, 빠름).
> - **Heavyweight** = 많은 사람이 경쟁 → 대기 명단 + 알림 (OS mutex, 느림).

### 정확한 정의

| 용어 | 정의 |
|---|---|
| **Mark Word** | 객체 헤더 첫 8 byte. lock 상태, GC age, hash code 인코딩. |
| **Biased Lock** | 단일 thread bias. 같은 thread 재진입 시 CAS 없이 그냥 owner check. JDK 15+ deprecated. |
| **Lightweight Lock** | CAS로 Mark Word를 LockRecord 포인터로 교환. Stack의 LockRecord 사용. |
| **LockRecord** | Stack frame에 할당되는 작은 자료구조. Lightweight lock의 owner 정보. |
| **Heavyweight Lock (Monitor)** | OS mutex 기반. ObjectMonitor 객체 + park/unpark. |
| **ObjectMonitor** | C++ 객체. wait queue + lock queue + owner 등. |
| **Park / Unpark** | LockSupport.park/unpark의 native 구현. pthread_cond_wait/signal. |
| **Inflation** | Lightweight → Heavyweight 승격. ObjectMonitor 생성. |

### 왜 3단계 승격인가

```
[모든 lock을 Heavyweight로]
   - 매 진입/exit에 OS mutex (~수십 cycles)
   - park/unpark 비용 (~수 us)
   - 99%의 uncontended 경우도 같은 비용
   → 성능 손실

[Biased — uncontended 최적화]
   - 같은 thread 재진입 시 단순 비교 (~수 cycles)
   - Contention 없으면 사실상 free
   
[Lightweight — light contention]
   - CAS 1번 (~10-20 cycles)
   - 다른 thread 대기 안 함 (자기 stack의 LockRecord)
   
[Heavyweight — heavy contention]
   - OS mutex + park/unpark
   - Thread 진짜 sleep → CPU 사용 0

→ 단계별 최적화로 모든 워크로드 효율
```

### JDK 15+ Biased 제거 이유 (JEP 374)

```
2000년대 Biased 도입 의의:
   - 단일 thread 워크로드 (UI app 등)에 효과적
   - 옛 thread library의 비용 큼

2020년대 상황:
   - 멀티스레드 워크로드 보편
   - Biased revoke 비용이 ↑ (다른 thread 시도 시 STW 비슷)
   - 코드 복잡도 (HotSpot 유지보수)
   - Project Lilliput (Mark Word 압축)에 방해

→ JDK 15 deprecated, JDK 18+ 사실상 비활성
```

---

## 🔬 3단계: 구조

### Mark Word의 상태별 인코딩

```
Unlocked (또는 Biased Disabled):
   [unused:25][hash:31][unused:1][age:4][biased:1=0][lock:2=01]

Biased (JDK 15-):
   [thread_id:54][epoch:2][unused:1][age:4][biased:1=1][lock:2=01]

Lightweight Locked:
   [lock_record_ptr:62][lock:2=00]

Heavyweight Locked:
   [monitor_ptr:62][lock:2=10]

GC marked:
   [forwarding_ptr:62][lock:2=11]
```

### Lightweight Lock 흐름

```
[Thread T가 obj의 synchronized 진입]

1. T의 stack에 LockRecord 할당:
   LockRecord {
       displaced_mark_word;   // 옛 Mark Word
   }

2. T가 obj의 Mark Word를 read.

3. LockRecord.displaced_mark_word = obj.mark_word.

4. CAS:
   obj.mark_word ← LockRecord 포인터 + lock:00
   expected ← 옛 mark word (Unlocked 상태)
   
5a. CAS 성공 → lock 획득 ✅

5b. CAS 실패:
    5b1. 만약 self-recursive (LockRecord가 T의 stack 안):
         재진입 count + 1
    5b2. 다른 thread가 lock 잡음:
         → Heavyweight로 inflate
         → ObjectMonitor 생성
         → wait queue 진입
```

### Heavyweight Lock (Monitor) 동작

```
[ObjectMonitor 객체]
class ObjectMonitor {
    Thread* _owner;
    int _recursions;        // 재진입 횟수
    ObjectWaiter* _WaitSet;  // wait() 대기 thread들
    ObjectWaiter* _EntryList; // lock 대기 thread들
};

[Lock acquire]
1. CAS로 _owner = self.
2. 실패 → _EntryList에 추가, park.

[Lock release]
1. _owner = null.
2. _EntryList에서 한 thread unpark.

[wait()]
1. _WaitSet에 추가, park.
2. notify()/notifyAll() 시 _EntryList로 이동, unpark.
```

### 운영 의미 — jstack의 BLOCKED

```
"worker-1" #45 daemon
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.foo.Service.method(Service.java:42)
        - waiting to lock <0x...> (a java.lang.Object)
        - locked by "worker-2"
```

- `BLOCKED` = Heavyweight monitor 대기 중.
- `waiting to lock` = ObjectMonitor의 EntryList 에 있음.
- `locked by` = 현재 owner thread.

→ Lock contention 진단의 가장 직접적 정보.

### 운영 의미 — jstack의 WAITING (parking)

```
"worker-1" #45
   java.lang.Thread.State: WAITING (parking)
        at jdk.internal.misc.Unsafe.park(Native Method)
        - parking to wait for <0x...> (a java.util.concurrent.locks.ReentrantLock$NonfairSync)
```

- `WAITING (parking)` = LockSupport.park.
- ReentrantLock, AQS 기반 lock.
- synchronized의 BLOCKED와 다른 메커니즘.

---

## 🧬 4단계: 내부 구현 — HotSpot

### Mark Word

위치: `src/hotspot/share/oops/markWord.hpp`

```cpp
class markWord {
    uintptr_t _value;
    
    static const int lock_bits = 2;
    static const int biased_lock_bits = 1;
    
    bool is_unlocked() const { return (_value & lock_mask) == unlocked_value; }
    bool is_biased_anonymously() const { ... }
    bool has_monitor() const { return (_value & lock_mask) == monitor_value; }
};
```

### Monitorenter 구현

위치: `src/hotspot/share/runtime/synchronizer.cpp`

```cpp
void ObjectSynchronizer::enter(Handle obj, BasicLock* lock, JavaThread* thread) {
    if (UseBiasedLocking) {
        // Biased 시도
        if (revoke_or_rebias(...) == HAS_CAS) return;
    }
    
    // Lightweight 시도
    if (fast_enter(obj, lock, ...)) return;
    
    // Heavyweight (inflate)
    ObjectMonitor* monitor = inflate(obj);
    monitor->enter(thread);
}
```

### ObjectMonitor::enter

```cpp
void ObjectMonitor::enter(JavaThread* current) {
    // 1. CAS로 owner = self 시도
    if (Atomic::cmpxchg(&_owner, NULL, current) == NULL) {
        return;  // acquired
    }
    
    // 2. 실패 → spin (잠시)
    if (try_spin(current)) return;
    
    // 3. 그래도 실패 → EntryList 추가 + park
    enqueue_and_park(current);
}
```

---

## 📜 5단계: 역사

| 연도 | 변화 |
|---|---|
| 2006 | JDK 6 — Biased Lock 도입 |
| 2014 | JDK 8 — Biased 기본 on |
| 2020 | JDK 15 — Biased deprecated (JEP 374) |
| 2022 | JDK 18 — Biased 사실상 비활성 |
| 2023 | JDK 21 — Project Lilliput 진행 (Mark Word 압축) |

### Project Lilliput

목표: Mark Word를 64 bit → 8 bit으로 압축.
- 옛 Mark Word의 lock state, GC age, hash 등 압축.
- 객체 헤더 12 byte → 4 byte 가능.
- Heap footprint 5~10% 절감.
- 모든 lock 메커니즘이 새 Mark Word에 적응 필요.

---

## ⚖️ 6단계: 트레이드오프

### synchronized vs ReentrantLock

| | synchronized | ReentrantLock |
|---|---|---|
| 메커니즘 | JVM Mark Word | Java AQS (AbstractQueuedSynchronizer) |
| 진입 | monitorenter bytecode | Lock.lock() 메서드 |
| 공정성 | 비공정 | fair/non-fair 선택 |
| Try-lock | ❌ | ✅ tryLock |
| 인터럽트 | ❌ | ✅ lockInterruptibly |
| Condition | ❌ (wait/notify만) | ✅ 여러 Condition |
| Virtual Thread pinning | ❌ (JDK 21~23) | ✅ pinning 안 함 |
| 코드 단순성 | 단순 | 복잡 (try/finally) |

운영 가이드:
- 단순 mutual exclusion: synchronized.
- Try-lock, 인터럽트, 여러 Condition 필요: ReentrantLock.
- Virtual Thread 사용 + synchronized 안의 blocking: ReentrantLock (pinning 회피).

---

## 📊 7단계: 측정·진단

### jstack으로 lock contention 분석

```bash
jstack <pid> | grep -A 5 BLOCKED
```

BLOCKED 다수 = synchronized contention.

### JFR Monitor 이벤트

```bash
jcmd <pid> JFR.start name=lock duration=60s settings=profile
```

이벤트:
- `jdk.JavaMonitorEnter` — synchronized 진입 (대기 시간 포함).
- `jdk.JavaMonitorWait` — Object.wait().
- 임계 (기본 10ms 이상) 만 기록.

### 운영 시나리오: Lock contention

```
환경: 멀티스레드 web 서비스
증상: 응답 느림, jstack에 BLOCKED 다수

진단:
1. jstack에 같은 lock의 BLOCKED waiters
2. "locked by"로 owner 식별
3. JFR jdk.JavaMonitorEnter 시간 분포

조치:
- Lock 범위 축소 (synchronized block 작게)
- ConcurrentHashMap 등 lock-free 자료구조
- ReentrantLock + ReadWriteLock (read heavy)
- Lock-free (CAS, AtomicXxx)
```

---

## ⚔️ 8단계: 꼬리질문 트리

### Q1. synchronized의 3단계 lock 메커니즘은?

> Biased → Lightweight → Heavyweight.
> 1. Biased (JDK 15-): 단일 thread bias. CAS 없음.
> 2. Lightweight: CAS + Stack LockRecord.
> 3. Heavyweight: OS mutex + park/unpark.
> 
> Contention에 따라 자동 승격. JDK 15+에서 Biased deprecated.

### Q2. Biased Lock이 제거된 이유는?

> 1. 현대 멀티스레드 워크로드에서 효과 작음.
> 2. Revoke 비용이 큼 (다른 thread 시도 시).
> 3. 코드 복잡도, Lilliput 같은 차세대 기능에 방해.
> 4. JEP 374 (JDK 15) deprecated, JDK 18+ 사실상 제거.

### Q3. jstack의 BLOCKED와 WAITING(parking)의 차이는?

> - **BLOCKED**: synchronized monitor 대기. ObjectMonitor의 EntryList에 있음.
> - **WAITING (parking)**: LockSupport.park. ReentrantLock, AQS 기반.
> 
> 둘 다 lock 대기지만 메커니즘 다름. 진단 시 어느 lock인지 식별.

### Q4. (Killer) 멀티스레드 서비스의 lock contention을 어떻게 진단하고 해결하나요?

> 1. **jstack**으로 BLOCKED/WAITING 분포 확인.
> 2. **같은 lock의 waiter 다수** = contention hotspot.
> 3. **JFR jdk.JavaMonitorEnter** 시간 분포.
> 4. **해결**:
>    - Lock 범위 축소.
>    - ConcurrentHashMap, AtomicXxx로 lock-free.
>    - ReentrantLock + ReadWriteLock (read heavy).
>    - Lock-free 알고리즘 (CAS).

---

## 🔗 다음 단계

- → [04. Virtual Threads](./04-virtual-threads-and-loom.md)
- ← [02. Memory Barriers](./02-memory-barriers.md)
