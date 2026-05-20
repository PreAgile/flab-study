# 05-03. synchronized + Mark Word 승격 (Biased → Lightweight → Heavyweight)

> `synchronized`는 **하나의 lock이 아니다**. Contention에 따라 자동 승격되는 **3단계 lock 메커니즘**.
> Biased (uncontended) → Lightweight (light contention) → Heavyweight (heavy contention). Mark Word의 2비트가 현재 상태를 표시.
> 시니어가 알아야 할 것: JDK 15+에서 Biased 제거됨. 현대 워크로드는 Lightweight ↔ Heavyweight 두 단계. **jstack의 BLOCKED는 Heavyweight monitor 대기**.

---

## 이 문서의 사용법

1. **0장 마인드맵을 먼저 외운다**.
2. **1~4장을 순서대로 학습한다**.
3. **5장 면접 워크플로우** + **6장 꼬리질문**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"synchronized는 Mark Word의 2비트로 상태 표시되는 3단계 lock이다. Biased (JDK 15-) → Lightweight (CAS) → Heavyweight (OS mutex + park). Contention에 따라 자동 승격."**

### 4개 가지 — 순서를 외운다

```
              [ROOT: Mark Word 2비트 + 3단계 자동 승격]
                                  │
       ┌──────────────────┬──────────────────┬──────────────────┐
       │                  │                  │                  │
     ① Mark Word       ② 3단계 승격         ③ 진단              ④ synchronized vs
     (객체 헤더)          (Biased/Light/      (jstack /            ReentrantLock
                          Heavy)              JFR)
       │                  │                  │                  │
   ┌───┼───┐         ┌────┼────┐         ┌───┼───┐         ┌────┼────┐
  Lock GC age   Biased  Light  Heavy   BLOCKED  WAITING    JVM lock  Java lock
  state hash    (제거)  CAS    OS      (Heavy)  (park)     vs        try/fair/
  2비트         JDK 15+ Stack  mutex                       AQS       Cond
                        LockRec park
```

### 가지별 핵심 키워드

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① Mark Word** | 객체 헤더 첫 8 byte | lock state 2 bits | GC age + hash 인코딩 |
| **② 3단계 승격** | Biased (JDK 15+ deprecated) | Lightweight (CAS + LockRecord) | Heavyweight (OS mutex + park) |
| **③ 진단** | jstack BLOCKED (Heavyweight) | jstack WAITING (parking) | JFR JavaMonitorEnter/Wait |
| **④ synchronized vs ReentrantLock** | JVM-level vs Java-level (AQS) | Try-lock / 인터럽트 / Condition | Virtual Thread Pinning 차이 |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 해당 가지 → 키워드 3개 → 인접 가지로 확장

---

## 1. 가지 ①: Mark Word — 객체 헤더의 8 byte

### 1.1 핵심 질문

> "Mark Word가 무엇이고 어떤 정보를 담나요?"

### 1.2 키워드 1 — 객체 헤더 구조

```
Java 객체 메모리 layout:
   [Mark Word: 8 byte][Klass pointer: 4 또는 8][instance fields...]
                                  ↑
                                  객체의 클래스 정보

Mark Word: 객체 헤더의 첫 8 byte. lock 상태 + GC age + hash 인코딩.
```

### 1.3 키워드 2 — 상태별 인코딩 (개념)

Mark Word의 lock state 2 bits로 4가지 상태 표시:

```
상태:
   Unlocked (또는 Biased Disabled): 일반 객체
   Biased Locked (JDK 15-):          단일 thread bias
   Lightweight Locked:                CAS lock (LockRecord 포인터)
   Heavyweight Locked:                OS mutex (ObjectMonitor 포인터)
   GC marked:                         GC 진행 중
```

→ 표면 디테일 (몇 bit이 어디 인코딩) 외우지 말고 **"2비트로 4상태 구분, 나머지 영역이 GC age / hash / lock pointer 보관"** 정도만.

### 1.4 키워드 3 — lock state 외 정보

```
Mark Word에 함께 인코딩되는 정보:
   - GC age (4 bits): Young GC에서 tenuring 결정
   - identity hash code: Object.hashCode() 결과
   - lock 정보: 위 3가지 상태
   
충돌 처리:
   - hash code가 한 번 계산되면 Mark Word에 박힘
   - 그 후 biased lock 못 함 (slot 충돌)
   - lightweight lock 시에는 displaced mark word 사용
```

→ **Mark Word는 정보 밀집**. 객체당 헤더 비용 최소화를 위한 설계.

### 1.5 Project Lilliput (JDK 21+ 진행 중)

```
목표: Mark Word 64 bit → 8 bit 압축
   - 객체 헤더 12 byte → 4 byte 가능
   - Heap footprint 5~10% 절감

방법:
   lock 정보를 별도 자료구조로 이동
   GC age 압축
   hash 별도 저장

모든 lock 메커니즘이 새 Mark Word에 적응 필요
→ Biased 제거(JDK 15+)가 Lilliput의 사전 작업
```

---

## 2. 가지 ②: 3단계 승격 — Biased / Lightweight / Heavyweight

### 2.1 핵심 질문

> "synchronized의 3단계 lock 메커니즘은 어떻게 동작하나요?"

### 2.2 키워드 1 — Biased Lock (JDK 15- deprecated)

```
용도: 단일 thread가 같은 lock을 반복 진입할 때 최적화

동작:
   1. 첫 lock 시 owner thread ID를 Mark Word에 기록
   2. 같은 thread 재진입 시: thread ID 비교만 (~수 cycles)
   3. CAS 없음 → 거의 free

장점: uncontended single-thread 워크로드에 매우 빠름.

단점:
   - 다른 thread가 시도 시 revoke 비용 큼 (STW 비슷)
   - 현대 멀티스레드 워크로드에서 효과 작음
   - 코드 복잡도

→ JDK 15 deprecated (JEP 374), JDK 18+ 사실상 비활성
```

### 2.3 키워드 2 — Lightweight Lock (CAS + Stack LockRecord)

```
용도: Light contention. 짧은 critical section.

동작:
1. T의 stack에 LockRecord 할당:
   LockRecord {
       displaced_mark_word;   // 옛 Mark Word 백업
   }

2. T가 obj의 Mark Word를 read.

3. LockRecord.displaced_mark_word = obj.mark_word.

4. CAS:
   obj.mark_word ← LockRecord 포인터 + lock state
   expected ← 옛 mark word (Unlocked 상태)

5a. CAS 성공 → lock 획득 ✅
    → 비용: ~10~20 cycles (가지 ⑤ Memory Barriers의 CAS 비용)

5b. CAS 실패:
    5b1. Self-recursive (LockRecord가 T의 stack 안):
         재진입 count + 1
    5b2. 다른 thread가 lock 잡음:
         → Heavyweight로 inflate
         → ObjectMonitor 생성
```

### 2.4 키워드 3 — Heavyweight Lock (Monitor + park/unpark)

```
용도: Heavy contention. 긴 critical section 또는 많은 waiter.

ObjectMonitor (C++ 객체):
class ObjectMonitor {
    Thread* _owner;
    int _recursions;            // 재진입 횟수
    ObjectWaiter* _WaitSet;      // wait() 대기 thread들
    ObjectWaiter* _EntryList;    // lock 대기 thread들
};

Lock 진입 흐름:
   1. CAS로 _owner = self 시도
   2. 실패 → 잠시 spin
   3. 그래도 실패 → _EntryList에 추가, park (CPU yield)

Lock release:
   1. _owner = null
   2. _EntryList에서 한 thread unpark

wait() / notify():
   - wait(): _WaitSet에 추가, park
   - notify(): _WaitSet → _EntryList 이동, unpark

park/unpark 구현:
   - native LockSupport.park/unpark
   - Linux: pthread_cond_wait/signal
   - 비용: ~수 us
```

### 2.5 승격 흐름

```
[Initial: Unlocked]
   │ 첫 lock
   ▼
[Biased Lock] (JDK 15- only, 단일 thread)
   │ 다른 thread 시도
   ▼ revoke
[Lightweight Lock] (CAS)
   │ CAS 실패 (contention)
   ▼ inflate
[Heavyweight Lock] (Monitor + park/unpark)
```

→ Contention에 따라 **자동 승격**. 운영자가 명시 안 함.

### 2.6 왜 3단계 (단일 Heavyweight가 아닌 이유)

```
[모든 lock을 Heavyweight로]
   - 매 진입/exit에 OS mutex (~수십 cycles)
   - park/unpark 비용 (~수 us)
   - 99%의 uncontended 경우도 같은 비용
   → 성능 손실

[3단계 최적화]
   Biased — uncontended: ~수 cycles
   Lightweight — light contention: ~10~20 cycles
   Heavyweight — heavy contention: ~수 us (단, 진짜 sleep해서 CPU 사용 0)

→ 워크로드별로 적절한 비용
```

### 2.7 JDK 15+ Biased 제거 이유 (JEP 374)

```
2000년대 Biased 도입 의의:
   - 단일 thread 워크로드 (UI app 등)에 효과적
   - 옛 thread library의 비용 큼

2020년대 상황:
   - 멀티스레드 워크로드 보편
   - Biased revoke 비용이 ↑ (다른 thread 시도 시)
   - 코드 복잡도 (HotSpot 유지보수)
   - Project Lilliput (Mark Word 압축)에 방해

→ JDK 15 deprecated, JDK 18+ 사실상 비활성
```

---

## 3. 가지 ③: 진단 — jstack + JFR

### 3.1 핵심 질문

> "synchronized의 lock contention을 어떻게 진단하나요?"

### 3.2 키워드 1 — jstack의 BLOCKED (Heavyweight monitor)

```
"worker-1" #45 daemon
   java.lang.Thread.State: BLOCKED (on object monitor)
        at com.foo.Service.method(Service.java:42)
        - waiting to lock <0x...> (a java.lang.Object)
        - locked by "worker-2"
```

해독:
- `BLOCKED` = Heavyweight monitor 대기.
- `waiting to lock` = ObjectMonitor의 _EntryList에 있음.
- `locked by` = 현재 owner thread.

→ Lock contention 진단의 가장 직접적 정보.

### 3.3 키워드 2 — jstack의 WAITING (parking, AQS lock)

```
"worker-1" #45
   java.lang.Thread.State: WAITING (parking)
        at jdk.internal.misc.Unsafe.park(Native Method)
        - parking to wait for <0x...> (a java.util.concurrent.locks.ReentrantLock$NonfairSync)
```

해독:
- `WAITING (parking)` = LockSupport.park.
- ReentrantLock, AQS 기반 lock.
- synchronized의 BLOCKED와 다른 메커니즘.

### 3.4 키워드 3 — JFR Monitor 이벤트

```bash
jcmd <pid> JFR.start name=lock duration=60s settings=profile
```

핵심 이벤트:
- `jdk.JavaMonitorEnter` — synchronized 진입 (대기 시간 포함).
- `jdk.JavaMonitorWait` — Object.wait().
- 임계 (기본 10ms 이상) 만 기록 — production-safe.

분석:
- Lock 별 대기 시간 분포.
- Contention hotspot 식별.
- Wait 패턴 (잠시 wait vs 오래 wait).

### 3.5 BLOCKED vs WAITING 비교

| | BLOCKED | WAITING (parking) |
|---|---|---|
| 메커니즘 | Heavyweight monitor | LockSupport.park |
| 사용 lock | synchronized | ReentrantLock, AQS |
| jstack 시그니처 | "BLOCKED (on object monitor)" | "WAITING (parking)" |
| 대기 자료구조 | _EntryList | AQS 큐 |

→ 진단 시 어느 lock인지 식별 — 메커니즘 다름.

### 3.6 운영 시나리오: Lock contention 진단

```
환경: 멀티스레드 web 서비스
증상: 응답 느림, jstack에 BLOCKED 다수

진단:
1. jstack에 같은 lock의 BLOCKED waiters
2. "locked by"로 owner thread 식별
3. JFR jdk.JavaMonitorEnter 시간 분포

조치:
- Lock 범위 축소 (synchronized block 작게)
- ConcurrentHashMap 등 lock-free 자료구조
- ReentrantLock + ReadWriteLock (read heavy)
- Lock-free (CAS, AtomicXxx)
```

---

## 4. 가지 ④: synchronized vs ReentrantLock — 선택 기준

### 4.1 핵심 질문

> "synchronized와 ReentrantLock 중 무엇을 선택해야 하나요?"

### 4.2 키워드 1 — 메커니즘 차이

```
synchronized:
   - JVM 내장 (Mark Word + ObjectMonitor)
   - monitorenter / monitorexit bytecode
   - JIT 최적화 친화 (Lock Coarsening, Elision)

ReentrantLock:
   - Java 라이브러리 (java.util.concurrent.locks)
   - AbstractQueuedSynchronizer (AQS) 기반
   - LockSupport.park/unpark 활용
```

### 4.3 키워드 2 — 기능 비교 표

| | synchronized | ReentrantLock |
|---|---|---|
| 메커니즘 | JVM Mark Word | Java AQS |
| 진입 | monitorenter bytecode | Lock.lock() 메서드 |
| 공정성 | 비공정 | fair/non-fair 선택 |
| Try-lock | 없음 | tryLock |
| 인터럽트 | 없음 | lockInterruptibly |
| Condition | wait/notify만 | 여러 Condition |
| Virtual Thread pinning | 있음 (JDK 21~23) | 없음 |
| 코드 단순성 | 단순 | 복잡 (try/finally 필수) |

### 4.4 키워드 3 — Virtual Thread Pinning 차이 (중요)

```
Virtual Thread (JDK 21+) 환경에서:
   synchronized + blocking → Pinning 발생
      (carrier thread도 같이 block, 가지 ⑤ Threading 04)
   
   ReentrantLock + blocking → Pinning 안 함
      (Java-level lock, carrier에 묶이지 않음)
```

→ **Virtual Thread 사용 시 synchronized 안의 I/O는 위험**. ReentrantLock으로 대체.

JDK 24+ (JEP 491)에서 synchronized pinning 해소 예정.

### 4.5 선택 가이드

```
synchronized:
   - 단순 mutual exclusion
   - 짧은 critical section
   - Virtual Thread 없는 환경

ReentrantLock:
   - Try-lock 필요 (timeout)
   - 인터럽트 가능한 lock
   - 여러 Condition (producer/consumer 분리)
   - Virtual Thread 환경 + blocking 호출
   - fair lock 필요
```

### 4.6 HotSpot 내부 (참고)

**Mark Word** (`src/hotspot/share/oops/markWord.hpp`):
```cpp
class markWord {
    uintptr_t _value;
    
    bool is_unlocked() const;
    bool has_monitor() const;
    bool is_biased_anonymously() const;  // JDK 15-
};
```

**Monitorenter 구현** (`src/hotspot/share/runtime/synchronizer.cpp`):
```cpp
void ObjectSynchronizer::enter(Handle obj, BasicLock* lock, JavaThread* thread) {
    if (UseBiasedLocking) {
        if (revoke_or_rebias(...) == HAS_CAS) return;
    }
    
    if (fast_enter(obj, lock, ...)) return;   // Lightweight
    
    ObjectMonitor* monitor = inflate(obj);    // Heavyweight
    monitor->enter(thread);
}
```

**ObjectMonitor::enter**:
```cpp
void ObjectMonitor::enter(JavaThread* current) {
    if (Atomic::cmpxchg(&_owner, NULL, current) == NULL) return;  // CAS
    if (try_spin(current)) return;                                  // spin
    enqueue_and_park(current);                                      // park
}
```

---

## 5. 면접 답변 워크플로우

### 5.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "Mark Word가 뭐?" | ① Mark Word | 정보 인코딩 |
| "synchronized 3단계?" | ② 3단계 승격 | 자동 승격 |
| "Biased Lock 제거 이유?" | ② Biased | JEP 374 |
| "BLOCKED vs WAITING?" | ③ 진단 | jstack 패턴 |
| "Lock contention 진단?" | ③ 진단 | JFR |
| "synchronized vs ReentrantLock?" | ④ 비교 | VT pinning |
| "Lock-free 자료구조?" | ④ + 다른 chapter | CAS |

### 5.2 답변 템플릿

예: "synchronized의 3단계 lock 메커니즘은?"

> "synchronized는 Mark Word 2비트로 상태 표시되는 3단계 lock입니다 (← 루트).
> 가지 ②의 키워드 3개로 설명:
> 첫째, **Biased** (JDK 15- only, deprecated). 단일 thread bias. thread ID 비교만 ~수 cycles.
> 둘째, **Lightweight**. CAS + Stack LockRecord. ~10~20 cycles. 짧은 critical section.
> 셋째, **Heavyweight**. ObjectMonitor + park/unpark. ~수 us이지만 진짜 sleep해서 CPU 사용 0.
> Contention에 따라 자동 승격. JDK 15+ Biased는 JEP 374로 제거, 현대 워크로드는 Lightweight ↔ Heavyweight 두 단계.
> jstack에서 BLOCKED 보이면 Heavyweight monitor 대기 (가지 ③로 연결)."

---

## 6. 꼬리질문 트리

### Q1 [가지 ②]. synchronized의 3단계 lock 메커니즘은?

> Biased → Lightweight → Heavyweight.
> 1. Biased (JDK 15-): 단일 thread bias. CAS 없음, thread ID 비교만.
> 2. Lightweight: CAS + Stack LockRecord.
> 3. Heavyweight: OS mutex + park/unpark (ObjectMonitor).
>
> Contention에 따라 자동 승격. JDK 15+에서 Biased deprecated.

### Q2 [가지 ②]. Biased Lock이 제거된 이유는?

> 1. 현대 멀티스레드 워크로드에서 효과 작음.
> 2. Revoke 비용이 큼 (다른 thread 시도 시).
> 3. 코드 복잡도, Lilliput 같은 차세대 기능에 방해.
> 4. JEP 374 (JDK 15) deprecated, JDK 18+ 사실상 제거.

**🪝 Q2-1: Project Lilliput이 뭐?**
> Mark Word 64 bit → 8 bit 압축 프로젝트. 객체 헤더 12 byte → 4 byte 가능 → Heap footprint 5~10% 절감. Biased 제거가 사전 작업.

### Q3 [가지 ③]. jstack의 BLOCKED와 WAITING(parking)의 차이는?

> - **BLOCKED**: synchronized monitor 대기. ObjectMonitor의 _EntryList에 있음.
> - **WAITING (parking)**: LockSupport.park. ReentrantLock, AQS 기반.
>
> 둘 다 lock 대기지만 메커니즘 다름. 진단 시 어느 lock인지 식별.

### Q4 [가지 ④]. synchronized vs ReentrantLock 선택은?

> 단순 mutual exclusion: synchronized.
> Try-lock, 인터럽트, 여러 Condition: ReentrantLock.
> Virtual Thread 사용 + synchronized 안의 blocking: ReentrantLock (pinning 회피).
> JDK 24+ 이후엔 synchronized pinning 해소될 예정 (JEP 491).

### Q5 (Killer) [모든 가지]. 멀티스레드 서비스의 lock contention을 어떻게 진단하고 해결?

> 1. **jstack**으로 BLOCKED/WAITING 분포 확인.
> 2. **같은 lock의 waiter 다수** = contention hotspot.
> 3. **JFR jdk.JavaMonitorEnter** 시간 분포.
> 4. **해결**:
>    - Lock 범위 축소 (synchronized block 작게).
>    - ConcurrentHashMap, AtomicXxx로 lock-free.
>    - ReentrantLock + ReadWriteLock (read heavy).
>    - Lock-free 알고리즘 (CAS).

---

## 7. 학습 체크리스트

- [ ] 0장 마인드맵을 1분 이내로 그릴 수 있다
- [ ] 가지 ①: Mark Word가 객체 헤더 첫 8 byte이고 lock/age/hash를 인코딩함을 설명한다
- [ ] 가지 ①: Project Lilliput의 목표 (12 byte → 4 byte)를 인용한다
- [ ] 가지 ②: 3단계 승격 (Biased → Light → Heavy) 흐름을 그린다
- [ ] 가지 ②: Lightweight Lock의 LockRecord + displaced mark word를 설명한다
- [ ] 가지 ②: Heavyweight Lock의 ObjectMonitor (_owner, _EntryList, _WaitSet)를 그린다
- [ ] 가지 ②: Biased 제거 이유 (JEP 374)를 말한다
- [ ] 가지 ③: jstack BLOCKED vs WAITING(parking) 차이를 비교한다
- [ ] 가지 ③: JFR JavaMonitorEnter/Wait 이벤트를 인용한다
- [ ] 가지 ④: synchronized vs ReentrantLock 표를 그린다
- [ ] 가지 ④: Virtual Thread Pinning 차이 (synchronized는 pinning, ReentrantLock은 없음)를 설명한다
- [ ] 6장 꼬리질문 5개에 답한다

---

## 다음 단계

- → [04. Virtual Threads + Loom](./04-virtual-threads-and-loom.md): M:N 모델 + Pinning
- ← [02. Memory Barriers](./02-memory-barriers.md)

## 참고

- **JEP 374 — Disable and Deprecate Biased Locking**: https://openjdk.org/jeps/374
- **Project Lilliput**: https://wiki.openjdk.org/display/lilliput
- **HotSpot `markWord.hpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/oops/markWord.hpp
- **HotSpot `synchronizer.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/synchronizer.cpp
- **HotSpot `objectMonitor.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/objectMonitor.cpp
