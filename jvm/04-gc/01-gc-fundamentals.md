# 04-01. GC Fundamentals — Reachability + Mark/Sweep/Compact

> GC 알고리즘은 30년간 진화했지만 **본질은 두 질문에 답하는 것**: "어떤 객체가 살아있는가?" + "죽은 객체의 메모리를 어떻게 회수하는가?"
> 답: **Reachability** (GC Roots에서 도달 가능) + **3가지 회수 변환** (Mark-Sweep / Mark-Compact / Copying).
> 시니어가 알아야 할 것: 모든 GC 알고리즘은 이 기본의 변형이다. Serial부터 ZGC까지의 차이는 "STW를 어떻게 줄였나"의 변천사.

---

## 🗺️ JVM 아키텍처 안에서 이 챕터의 위치

본 챕터는 GC의 모든 변종이 공유하는 기본을 다룬다.

![gc fundamentals](./_excalidraw/01-gc-fundamentals.svg)

---

## 📍 학습 목표

1. **Reachability**가 GC의 "살아있다" 정의인 이유 — 참조 카운팅 vs reachability.
2. **GC Roots 4종** — Stack local + Static field + JNI global + Active thread.
3. **Mark-Sweep / Mark-Compact / Copying** 세 가지 변환의 차이와 적합한 영역.
4. **Weak Generational Hypothesis** — "대부분 객체는 일찍 죽는다" 가설이 generational GC를 만든 이유.
5. **STW (Stop-The-World)** 가 왜 필요한지 + 30년 GC 진화가 STW 축소에 집중된 이유.
6. **Write Barrier / Read Barrier** — GC와 mutator의 협력 메커니즘.
7. **Safepoint** — STW를 안전하게 진입하는 메커니즘 ([Chapter 05 Threading](../05-threading/) 와 연결).
8. **Card Table / Remembered Set** — Old → Young 참조 추적 ([Chapter 02-06 GC bookkeeping](../02-runtime-data-areas/06-gc-bookkeeping-and-others.md)).
9. **Compaction의 비용 vs 이득** — fragmentation 대비.
10. **Live ratio** 가 GC 효율에 미치는 영향 — Young GC가 빠른 이유.

---

## 🎨 1단계: 백지 그리기 가이드

### Step 1: Reachability 그래프

```
[GC Roots]
   - Stack (local + operand)
   - Static fields
   - JNI globals
   - Active threads
        │
        ▼ 참조 따라가기
[Reachable 객체들] = 살아있음
        │
[Unreachable 객체들] = 죽음 → 회수
```

### Step 2: 3가지 변환

```
[Mark-Sweep]
[살][죽][살][죽][살]  →  [살][free][살][free][살]
→ Fragmentation. 빠름.

[Mark-Compact]
[살][죽][살][죽][살]  →  [살][살][살][free][free]
→ Fragmentation 0. 느림 (객체 이동).

[Copying]
영역A: [살][죽][살][죽][살]
영역B: (비어있음)
        │ Copy
        ▼
영역A: (비어있음)  →  다음 GC 시 영역으로 사용
영역B: [살][살][살]
→ 살아있는 객체 적으면 매우 빠름.
```

### 정답 그림

위의 [01-gc-fundamentals.svg](./_excalidraw/01-gc-fundamentals.svg) 참조.

---

## 🧠 2단계: 직관

### 핵심 비유

> **창고 정리 비유**:
> - **Reachability** = 출입구(GC Roots)에서 시작해 사용 중인 물건들 표시. 표시 안 된 건 버릴 것.
> - **Mark-Sweep** = 버릴 물건 그 자리에서 폐기. 빈 공간이 흩어짐.
> - **Mark-Compact** = 사용할 물건을 한 쪽으로 모음. 빈 공간이 한 군데로.
> - **Copying** = 사용할 물건만 새 창고로 옮김. 옛 창고는 통째 비움.

### 정확한 정의 (비유와 분리)

| 용어 | 정의 |
|---|---|
| **Reachability** | 객체 그래프에서 GC Roots로부터 도달 가능한지. "살아있음"의 GC적 정의. |
| **GC Roots** | reachability 분석의 시작점. Stack local/operand + Static field + JNI global ref + Active thread/monitor. |
| **Mark-Sweep** | reachable 객체 mark → unreachable 객체 sweep (free list 반환). Fragmentation 있음. |
| **Mark-Compact** | mark → 살아있는 객체를 한 쪽으로 compact. Fragmentation 0이지만 객체 이동 비용. |
| **Copying** | 두 영역 사용. mark + copy 동시. 살아있는 객체가 적을수록 효율적. |
| **STW (Stop-The-World)** | GC 중 모든 application thread 정지. Mark 정확성 + Compact 안전 보장. |
| **Concurrent GC** | mutator와 동시 동작. STW 최소화. SATB/IU 같은 메커니즘 필요. |
| **Write Barrier** | mutator의 ref 쓰기 시 추가 코드 실행. GC가 변경 알도록. ([Chapter 02-06](../02-runtime-data-areas/06-gc-bookkeeping-and-others.md)). |
| **Read Barrier** | mutator의 ref 읽기 시 추가 코드. ZGC/Shenandoah가 사용. |
| **Live Ratio** | 한 영역에서 살아있는 객체의 비율. Young은 낮음 (~5%), Old는 높음 (~80%+). |

### 왜 Reachability인가 — Reference Counting의 한계

```
Reference Counting (Python, Swift):
  - 각 객체에 ref count 유지.
  - 0이 되면 즉시 회수.
  + 즉시성 (STW 없음).
  + 단순.
  - 순환 참조 못 회수 (a→b→a 경우 둘 다 count > 0).
  - ref 변경 시마다 count 갱신 → 성능 영향.
  - Thread-safe하려면 atomic 증감.

Reachability (Java, Go):
  + 순환 참조 회수 가능.
  + Mutator overhead 작음 (write barrier만, count 안 함).
  - 주기적 GC 사이클 필요.
  - STW 또는 concurrent 필요.

→ Java의 선택: Reachability. 순환 참조 + 멀티스레드 친화.
```

### 왜 STW가 필요한가

```
[STW 없이 Mark 시도]
GC thread: 객체 A를 reachable로 mark
        │
        ▼ 동시에
Mutator: a.field = newObj   ← A의 reference 변경
        │
        ▼
GC thread: A의 reference 따라가서 newObj 발견 못 함
        │
        ▼
잘못 회수 → 메모리 손상 → crash

[STW 적용]
GC 시작 → 모든 thread 정지 → 정확한 mark → 회수 → resume
```

→ **정확성 보장의 가장 단순한 방법이 STW**. 그러나 모든 thread 정지는 latency 비용. 30년 진화가 "정확성을 유지하며 STW를 어떻게 줄일까"에 집중.

### 왜 3가지 회수 변환이 모두 필요한가

```
Mark-Sweep: 객체 이동 안 함 → 안전, 빠름. 단점: fragmentation.
   → 적합: 큰 객체 별로 없고 free list로 충분히 관리 가능.
   → 옛 CMS Old gen.

Mark-Compact: 객체 이동 → fragmentation 0.
   → 적합: 큰 객체 자주 할당, 메모리 효율 중요.
   → Serial/Parallel Old, G1 Full GC.

Copying: 살아있는 객체 적으면 매우 효율.
   → 적합: live ratio 낮음 (보통 Young gen ~5%).
   → 모든 Young GC.
```

→ 모든 GC는 영역(Young/Old)별로 다른 변환 조합. **한 GC = 영역별 변환 조합**.

---

## 🔬 3단계: 구조

### GC Roots의 정확한 종류

```
1. Stack 기반 roots (per-thread):
   - JVM Stack의 local variable slot에 있는 oop
   - Operand stack의 oop
   - 모든 스레드 별로 OopMap이 어느 slot이 oop인지 알려줌

2. Class 기반 roots:
   - 각 InstanceKlass의 static field
   - String pool (interned String)
   - Symbol table (옛 PermGen 시절 흔적)

3. Native 기반 roots:
   - JNI Global Reference (NewGlobalRef)
   - JNI Weak Reference (보조적)

4. Thread/Monitor 기반:
   - Active thread의 ContextClassLoader
   - Locked object (synchronized)
   - Thread local

5. JFR/JVMTI:
   - 모니터링 도구가 잡는 객체
```

### Mark Phase 흐름

```
1. GC Roots 식별 (모든 스레드 stack scan 등)
2. Roots를 worklist에 enqueue
3. while worklist not empty:
     obj = worklist.pop()
     if not obj.marked:
         obj.marked = true
         for each ref in obj.fields:
             worklist.push(ref)
4. 끝나면 marked = reachable, !marked = dead
```

마킹 시간 ≈ 살아있는 객체 수에 비례. **Live ratio가 GC 비용의 핵심**.

### Card Table — Young/Old 분리 시 필수

Young GC가 효율적이려면 Old gen 전체를 스캔하면 안 됨. 그러나 Old → Young 참조도 reachability 계산에 필요:

```
Old gen 객체 O가 Young gen 객체 Y를 가리킴
→ Y는 살아있어야 함 (O가 reachable이라면)

해결: Card Table
   - Heap을 512B 카드로 나눔
   - Old의 어느 카드에 Young 참조 변경? → 그 카드 dirty 표시 (Write Barrier)
   - Young GC 시 dirty 카드만 scan → Old 전체 안 봄
```

자세히는 [Chapter 02-06 GC Bookkeeping](../02-runtime-data-areas/06-gc-bookkeeping-and-others.md).

### Safepoint — STW 진입 메커니즘

STW 시작 = JVM이 "지금 멈춰" 신호 → 모든 thread가 safepoint에서 자발적 정지:

```
1. JVM이 polling page를 mprotect(PROT_NONE)
2. 인터프리터: 특정 명령(메서드 진입/exit, loop back-edge)에 poll instruction
   - polling page 읽음 → SEGV → signal handler → thread 정지
3. JIT 컴파일된 코드: 메서드 prologue/epilogue, loop back-edge에 poll
4. 모든 thread가 safepoint blocking 상태 → GC 진행
```

자세히는 [Chapter 05 Threading](../05-threading/).

### Generational GC의 동기 — Weak Generational Hypothesis

> **"대부분의 객체는 일찍 죽는다"** — Lieberman & Hewitt 1983.

실측:
- Java 앱의 80~98%의 객체가 첫 Young GC를 못 넘긴다.
- 이걸 활용: Young만 자주 청소 (대부분 dead) + Old는 가끔 (대부분 alive).

```
Young GC (Copying):
  - Eden + Survivor에서 살아있는 객체만 복사
  - 살아있는 객체 ~5% → 95%의 메모리를 매우 빠르게 회수
  - 빈도: 수 초마다, ~10~50ms

Old GC (Major):
  - Old gen이 차면 Mark-Sweep 또는 Mark-Compact
  - 살아있는 객체 ~80%+ → 회수 효율 낮음
  - 빈도: 수 분~수 시간마다, ~수백 ms ~ 수 초
```

---

## 🧬 4단계: 내부 구현 — HotSpot

### CollectedHeap 추상

위치: `src/hotspot/share/gc/shared/collectedHeap.hpp`

```cpp
class CollectedHeap : public CHeapObj<mtGC> {
public:
    virtual void collect(GCCause::Cause cause) = 0;
    virtual HeapWord* allocate_new_tlab(...) = 0;
    virtual void object_iterate(ObjectClosure* cl) = 0;
    // ... 모든 GC가 구현해야 할 API
};

// 각 GC 구현
class SerialHeap : public CollectedHeap { ... };
class ParallelScavengeHeap : public CollectedHeap { ... };
class G1CollectedHeap : public CollectedHeap { ... };
class ZCollectedHeap : public CollectedHeap { ... };
class ShenandoahHeap : public CollectedHeap { ... };
```

→ GC가 다양하지만 같은 인터페이스. JVM의 다른 부분 (allocator, JIT, interpreter)이 GC 종류 신경 안 씀.

### Reachability 분석 — Closure 패턴

```cpp
// Mark 함수의 일반화
class MarkingClosure : public OopClosure {
public:
    void do_oop(oop* p) override {
        oop o = *p;
        if (o != nullptr && !o->is_gc_marked()) {
            o->set_gc_marked();
            worklist->push(o);
        }
    }
};

// GC Roots iterate
void iterate_roots(MarkingClosure* cl) {
    Threads::oops_do(cl, ...);      // stack
    SystemDictionary::oops_do(cl);  // static
    JNIHandles::oops_do(cl);         // JNI
    // ...
}
```

### Write Barrier (G1 기준 예시)

위치: `src/hotspot/share/gc/g1/g1BarrierSet.cpp`

```cpp
// JIT가 obj.field = newRef 호출 시 inline
void g1_write_barrier(oop* field, oop new_value) {
    // 1. Pre-barrier (SATB)
    if (G1MarkingActive) {
        oop old_val = *field;
        if (old_val != nullptr) {
            satb_queue->enqueue(old_val);
        }
    }
    
    // 2. Store
    *field = new_value;
    
    // 3. Post-barrier (Card Table)
    if (cross_region(field, new_value)) {
        mark_card_dirty(field);
        dirty_card_queue->enqueue(card);
    }
}
```

→ 모든 ref 쓰기에 추가 코드. 약 5~10% 성능 비용 — concurrent GC 위해 필요.

---

## 📜 5단계: 역사

| 연도 | 변화 | 이유 |
|---|---|---|
| 1959 | McCarthy — Mark-Sweep (Lisp) | GC의 시작 |
| 1969 | Cheney — Copying GC | 살아있는 객체 적은 영역 |
| 1983 | Lieberman & Hewitt — Generational | Weak Generational Hypothesis |
| 1996 | JDK 1.0 — Serial GC | Mark-Compact + Copying |
| 2002 | JDK 1.4 — Parallel GC | 멀티코어 활용 |
| 2002 | JDK 1.4 — CMS | Concurrent Mark-Sweep, low latency |
| 2009 | JDK 7 — G1 (실험) | Region 기반, 예측 가능한 STW |
| 2017 | JDK 9 — G1 기본 GC | CMS 대체 |
| 2018 | JDK 11 — ZGC 실험 | sub-ms STW |
| 2019 | JDK 12 — Shenandoah | ZGC 대안 |
| 2020 | JDK 14 — CMS 제거 | G1으로 통합 |
| 2023 | JDK 21 — Generational ZGC | Weak Hypothesis를 ZGC에 |

---

## ⚖️ 6단계: 트레이드오프

### 회수 변환별 트레이드오프

| | Mark-Sweep | Mark-Compact | Copying |
|---|---|---|---|
| 속도 | 빠름 | 느림 (이동 비용) | 매우 빠름 (low live ratio) |
| Fragmentation | 있음 | 없음 | 없음 |
| 메모리 사용 | 100% | 100% | 50% (두 영역) |
| Live ratio 적합 | 모든 | 모든 | 낮을수록 좋음 |
| 적용 영역 | 옛 CMS Old | Serial/Parallel Old, G1 Full | 모든 Young |

---

## 📊 7단계: 측정·진단

### GC log 활성화

```bash
java -Xlog:gc*:file=gc.log:time:filesize=10M -jar app.jar
```

각 GC 이벤트의 상세 시간 + size + cause 기록.

### JFR GC 이벤트

```bash
jcmd <pid> JFR.start name=gc duration=300s settings=profile
jfr summary gc.jfr | grep -i 'gc\|allocation'
```

핵심 이벤트:
- `jdk.GarbageCollection` — 각 GC 발생.
- `jdk.GCHeapSummary` — 주기 heap 사용량.
- `jdk.ObjectAllocationInNewTLAB` — allocation rate.

### 운영 시나리오

| 증상 | 진단 | 가능 원인 |
|---|---|---|
| Young GC 시간 ↑ | GC log Young pause | live ratio ↑ — survivor 부족 |
| Full GC 빈발 | GC log Full GC cause | Old gen 압박 |
| Allocation rate ↑ | JFR allocation events | 코드 변경 후 객체 증가 |

---

## ⚔️ 8단계: 꼬리질문 트리

### Q1. Java GC가 reference counting 안 쓰는 이유는?

> 1. 순환 참조 못 회수 (a→b→a 둘 다 count > 0).
> 2. ref 변경 시마다 count 갱신 → 성능.
> 3. Thread-safe atomic 증감 비용.
> Reachability는 이 모든 문제를 회피. STW 또는 concurrent 필요.

### Q2. STW가 왜 필요한가요?

> Mutator가 mark 중 객체 그래프 변경 시 incorrect mark 결과.
> 정확성 보장의 가장 단순한 방법.
> 그러나 latency 비용 → concurrent GC가 SATB/IU로 정확성 유지하며 STW 줄임.

### Q3. Young GC가 Old GC보다 빠른 이유는?

> Live ratio 차이:
> - Young: ~5% 살아있음 → Copying이 매우 효율.
> - Old: ~80%+ 살아있음 → Copying 비효율, Mark-Sweep/Compact 사용.
> Weak Generational Hypothesis가 이 분할의 근거.

### Q4. Write Barrier가 무엇이고 왜 필요한가요?

> Mutator의 ref 쓰기에 추가되는 GC 협력 코드.
> 역할:
> - Card Table 갱신 (Old → Young 참조 추적).
> - SATB queue (concurrent marking).
> - Cross-region 정보 (G1 RSet).
> 비용: 일반 ~5~10% 성능. Concurrent GC의 전제.

---

## 🔗 다음 단계

- → [02. Generational + Serial/Parallel](./02-generational-and-serial-parallel.md)
- → [03. CMS and G1](./03-cms-and-g1.md)
- → [04. ZGC and Shenandoah](./04-zgc-and-shenandoah.md)
- → [05. Generational ZGC](./05-generational-zgc.md)
- → [06. GC Tuning and Ops](./06-gc-tuning-and-ops.md)
- ← [Chapter 02-06 GC Bookkeeping](../02-runtime-data-areas/06-gc-bookkeeping-and-others.md)
