# 05-02. Memory Barriers — happens-before의 CPU 구현

> JMM happens-before는 추상적 명세. CPU 레벨에서 실제로 강제하는 메커니즘이 **Memory Barrier** (또는 fence).
> Doug Lea가 명명한 4종 — **LoadLoad / StoreStore / LoadStore / StoreLoad**. x86은 대부분 자동, **StoreLoad만 mfence 필요** (~30 cycles).
> 시니어가 알아야 할 것: volatile write가 read보다 ~10× 비싼 이유, CAS의 lock prefix가 implicit full barrier인 이유, **x86 vs ARM의 메모리 모델 차이**.

---

## 이 문서의 사용법

1. **0장 마인드맵을 먼저 외운다**.
2. **1~4장을 순서대로 학습한다**.
3. **5장 면접 워크플로우** + **6장 꼬리질문**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"Happens-before를 CPU 레벨에서 강제하는 게 Memory Barrier 4종이다. x86은 TSO (Total Store Order)라 대부분 자동, StoreLoad만 mfence 필요. ARM은 Weakly Ordered라 모든 barrier 명시."**

### 4개 가지 — 순서를 외운다

```
              [ROOT: 4종 Barrier + x86 자동 / ARM 명시]
                                  │
       ┌──────────────────┬──────────────────┬──────────────────┐
       │                  │                  │                  │
     ① 4종 Barrier      ② x86 vs ARM       ③ Volatile/Lock/CAS  ④ Cookbook
     (Load/Store         (TSO vs Weakly       구현                 + 비용
      4조합)             Ordered)
       │                  │                  │                  │
   ┌───┼───┐         ┌────┼────┐         ┌───┼───┐         ┌────┼────┐
  LoadLoad LoadStore  TSO    Weakly       volatile  CAS lock   JSR-133  JMH
  StoreStore StoreLoad x86    ARM          write/   prefix    Cookbook  벤치
                              POWER        read     full       8 rule
                                          memory   barrier
                                          barrier
```

### 가지별 핵심 키워드

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① 4종 Barrier** | LoadLoad / StoreStore | LoadStore | StoreLoad (가장 비쌈) |
| **② x86 vs ARM** | x86 TSO (자동) | ARM Weakly (명시 dmb) | JIT이 platform별 삽입 |
| **③ Volatile/Lock/CAS** | volatile write에 mfence | monitor enter/exit | CAS의 lock prefix (implicit full) |
| **④ Cookbook + 비용** | JSR-133 (Doug Lea) | 8개 규칙 표 | JMH 측정 |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 해당 가지 → 키워드 3개 → 인접 가지로 확장

---

## 1. 가지 ①: 4종 Memory Barrier

### 1.1 핵심 질문

> "Memory Barrier가 무엇이고, 4종이 어떻게 다른가요?"

### 1.2 키워드 1 — Load/Store 4조합

```
LoadLoad   :  "이전 load가 이후 load보다 먼저 완료"
StoreStore :  "이전 store가 이후 store보다 먼저 완료"
LoadStore  :  "이전 load가 이후 store보다 먼저 완료"
StoreLoad  :  "이전 store가 이후 load보다 먼저 완료"  ← 가장 비쌈
```

### 1.3 키워드 2 — 각 barrier의 역할

```
LoadLoad: 
   read 순서 보장.
   예: header.flag read → header.data read
       → data가 옛 값 아닌지 보장

StoreStore:
   write 순서 보장.
   예: data write → flag write
       → 다른 thread가 flag 보고 옛 data 안 보게

LoadStore:
   read → write 순서 보장.
   드물게 사용.

StoreLoad:
   write → read 순서 보장.
   "내 write를 다른 thread가 본 후에 내가 다른 thread의 write 봄"
   양방향 동기화 → 가장 비쌈
```

### 1.4 키워드 3 — 왜 StoreLoad가 가장 비싼가

```
StoreLoad의 동작:
   store ...
   StoreLoad barrier
   load ...

CPU는 store를 Store Buffer에 임시 보관 (latency hiding):
   Store buffer를 다른 CPU와 분리

StoreLoad는:
   1. Store Buffer flush — 모든 pending store를 cache에 반영
   2. Cache 일관성 보장 (다른 CPU와)
   3. 이후 load는 완전 동기화된 cache에서

비용:
   x86 mfence: ~30 cycles
   ARM dmb sy: ~수십 cycles

→ volatile write 1번이 일반 store 대비 ~30× 비쌈
```

---

## 2. 가지 ②: x86 vs ARM — TSO vs Weakly Ordered

### 2.1 핵심 질문

> "x86과 ARM은 메모리 모델이 어떻게 다른가요?"

### 2.2 키워드 1 — x86 Total Store Order (TSO)

```
[x86 — Total Store Order]
대부분의 reorder 금지:
   - 다른 thread의 store는 동일 순서로 보임
   - 단 자기 load는 store 뒤로 갈 수 있음 (Store Buffering)
→ 단 StoreLoad만 명시 필요

자동 보장:
   LoadLoad   : 자동
   StoreStore : 자동
   LoadStore  : 자동
   StoreLoad  : ★ mfence 필요
```

### 2.3 키워드 2 — ARM Weakly Ordered

```
[ARM — Weakly Ordered (POWER도 비슷)]
거의 모든 reorder 허용:
   - LoadLoad, StoreStore, LoadStore 모두 명시 필요
   - 단, 같은 주소에 대한 ordering은 보존

→ 모든 sync에 dmb (Data Memory Barrier) 필요

dmb variant:
   dmb ld  — load barrier
   dmb st  — store barrier
   dmb sy  — full barrier
```

### 2.4 키워드 3 — JIT이 platform별 삽입

```
결과:
   x86은 단순 코드도 비교적 안전
   ARM은 더 명시적 barrier 필요

해결:
   Java가 두 platform에 같은 결과 보장하려고
   JIT이 platform별 적절한 barrier 삽입
   → 사용자는 x86/ARM 차이 의식 안 함

운영 함의:
   AWS Graviton (ARM), Apple Silicon (ARM)에서
   Java가 정확히 동작 — JIT이 dmb 적절히 삽입
   x86 대비 barrier 비용 약간 ↑
```

### 2.5 비교 표

| | x86 TSO | ARM Weakly Ordered |
|---|---|---|
| LoadLoad | 자동 | 명시 (dmb ld) |
| StoreStore | 자동 | 명시 (dmb st) |
| LoadStore | 자동 | 명시 |
| StoreLoad | mfence | dmb sy |
| 코드 안전성 | 단순 코드도 비교적 안전 | 명시 barrier 필수 |
| JIT 부담 | 적음 | 많음 |

---

## 3. 가지 ③: Volatile / Monitor / CAS의 Barrier 구현

### 3.1 핵심 질문

> "volatile, synchronized, CAS는 각각 어떤 barrier를 사용하나요?"

### 3.2 키워드 1 — Volatile의 barrier 배치

```
Required Barriers (JSR-133 Cookbook):

volatile write:
   - 이전 모든 작업 → 이 write 사이: StoreStore + LoadStore
   - 이 write → 이후 모든 작업 사이: StoreLoad ★

volatile read:
   - 이 read → 이후 모든 작업 사이: LoadLoad + LoadStore

x86 구현:
   volatile write:
      store v, val
      mfence       ← StoreLoad (다른 건 자동)
   
   volatile read:
      load v       ← LoadLoad 자동 (x86)
      (별도 barrier 없음)
```

→ **volatile write가 read보다 ~30× 비싼 이유**: StoreLoad (mfence ~30 cycles) vs 자동.

### 3.3 키워드 2 — Monitor (synchronized)의 barrier

```
synchronized 진입 (monitorenter):
   acquire lock
   [LoadLoad + LoadStore barrier]
   ... 안의 코드 ...

synchronized 끝 (monitorexit):
   ... 안의 코드 ...
   [StoreStore + LoadStore barrier]
   release lock
   [StoreLoad barrier]   ← 외부에서 새 lock 시 visibility 보장
```

→ Monitor의 unlock에 StoreLoad. happens-before의 monitor lock 규칙이 이걸로 강제.

### 3.4 키워드 3 — CAS의 lock prefix (implicit full barrier)

```
AtomicInteger.compareAndSet(expected, new):
   x86 어셈블리:
      lock cmpxchg [v], new_val   ; expected는 eax

   lock prefix의 효과:
      - cache line lock (atomicity)
      - implicit full barrier (StoreLoad 등 모두)
   
   비용:
      ~10~30 cycles (contention 없으면)
      ~수백 cycles (contention 시 cache bouncing)
```

→ CAS 한 번 = full barrier 한 번. AtomicXxx가 비싼 이유.

### 3.5 Final fields의 barrier

```
constructor body:
   final_field = ...;
[StoreStore barrier]   ← 생성자 종료 시 자동
return new object;
```

이 barrier가 final field publication 안전성 보장 (이전 챕터의 SC-DRF).

---

## 4. 가지 ④: Doug Lea Cookbook + 비용 측정

### 4.1 핵심 질문

> "어떤 코드에 어떤 barrier가 들어가나요?"

### 4.2 키워드 1 — JSR-133 Cookbook (Doug Lea, 2004)

JVM 구현자를 위한 가이드. JIT이 이 표를 따라 barrier 삽입.

| 시점 | Required barrier |
|---|---|
| Normal Load → Volatile Load | nothing |
| Normal Store → Volatile Store | StoreStore |
| Volatile Load → Normal Load | LoadLoad |
| Volatile Load → Normal Store | LoadStore |
| Volatile Store → Normal Load | StoreLoad |
| Volatile Store → Volatile Load | StoreLoad |
| Volatile Store → Volatile Store | StoreStore |
| Volatile Load → Volatile Load | LoadLoad |

→ 8가지 조합. 모든 JVM의 JIT이 이 표를 따라 적절한 barrier 삽입.

### 4.3 키워드 2 — 비용 표

| 비교 | 비용 (x86) |
|---|---|
| 일반 store | 0 cycles barrier |
| volatile read | ~1 ns (자동) |
| volatile store (mfence) | ~30 cycles (~10 ns) |
| CAS (lock cmpxchg, no contention) | ~10~30 cycles |
| synchronized (Lightweight, no contention) | ~수십 cycles |
| synchronized (Heavyweight, contention) | ~수 us (park/unpark) |

운영: hot path의 volatile/synchronized 누적 비용 측정 (JMH).

### 4.4 키워드 3 — JMH로 측정

```java
@Benchmark
public int volatileRead() { return v; }

@Benchmark
public void volatileWrite() { v = 1; }

@Benchmark
public boolean cas() { return ai.compareAndSet(0, 1); }
```

결과 (대략):
- volatile read ~1 ns
- volatile write ~10 ns
- CAS ~10~30 ns

→ **운영 함의**: hot path의 volatile **write**를 줄이는 게 더 효과적. read는 거의 무시.

### 4.5 HotSpot 구현 (참고)

**x86의 volatile 코드 emit** (`src/hotspot/cpu/x86/c1_LIRAssembler_x86.cpp`):
```cpp
void LIR_Assembler::volatile_move_op(...) {
    if (op->type() == longType) {
        __ movq(dest, src);   // 64-bit volatile move
    }
    
    if (is_volatile_store && op->type() != longType) {
        __ membar(Assembler::StoreLoad);   // ★ mfence
    }
}
```

**CAS 구현**:
```cpp
// HotSpot 구현
oop_old = atomic_cmpxchg(addr, new, expected);   // x86: lock cmpxchg
return oop_old == expected;
```

### 4.6 역사

- 1960s: 첫 multi-processor — cache coherence 문제 시작.
- 1990s: x86 Pentium Pro — Total Store Order 도입.
- 2004: **JSR-133 + Doug Lea's Cookbook** — Java 동시성 명세 ★.
- 2010s: ARM 멀티코어 보편화 — weakly ordered 모델 영향.
- 2020s: Apple Silicon (ARM)에서 Java — JIT이 적절한 dmb 삽입.

---

## 5. 면접 답변 워크플로우

### 5.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "4종 barrier?" | ① 4종 | StoreLoad가 가장 비쌈 |
| "x86 vs ARM?" | ② TSO vs Weakly | JIT 자동 |
| "volatile write 비용?" | ③ volatile | mfence |
| "CAS의 barrier?" | ③ CAS | lock prefix |
| "Cookbook?" | ④ JSR-133 | 8 규칙 |

### 5.2 답변 템플릿

예: "volatile write가 read보다 ~10× 느린 이유는?"

> "Happens-before는 추상 명세이고 CPU 레벨에서는 Memory Barrier로 강제됩니다 (← 루트).
> 가지 ①과 ③의 결합:
> 첫째, **volatile write 후 StoreLoad barrier** 필요 (Cookbook 규칙).
> 둘째, **x86의 StoreLoad = mfence ~30 cycles**.
> 셋째, **volatile read는 LoadLoad만 필요, x86은 자동 (0 cycles)**.
> 결과: write ~30~40 ns, read ~1~5 ns.
> 운영 함의: hot path의 volatile write를 줄이는 게 더 효과적. read는 거의 무시."

---

## 6. 꼬리질문 트리

### Q1 [가지 ①]. 4종 barrier 중 가장 비싼 건?

> StoreLoad. x86의 mfence ~30 cycles. CPU의 Store Buffer flush + cache 일관성 보장.
> volatile write, monitor unlock 후 자동 삽입.

### Q2 [가지 ②]. x86 vs ARM의 차이는?

> x86: Total Store Order (TSO). 대부분 자동, StoreLoad만 명시.
> ARM: Weakly Ordered. 모든 barrier 명시 (dmb ld/st/sy).
> Java는 JIT이 platform별 적절한 barrier 삽입 — 사용자는 의식 안 함.

**🪝 Q2-1: Apple Silicon에서 Java 동시성 이슈는?**
> JIT이 적절한 dmb 삽입해서 사용자 코드는 정확히 동작. 단, x86 대비 barrier 비용 약간 ↑ (~20~30% throughput 영향 가능).

### Q3 [가지 ③]. CAS가 어떤 barrier 효과를 주나요?

> x86 `lock cmpxchg`의 `lock` prefix가 implicit full barrier. StoreLoad 포함 모든 종류.
> + cache line lock (atomicity).
> 비용: no contention ~10~30 cycles. Contention 시 cache bouncing으로 ~수백 cycles.

### Q4 [가지 ③+④]. (Killer) volatile write가 read보다 ~10× 느린 이유는?

> Write 후 mfence (StoreLoad barrier) — ~30 cycles.
> Read는 x86 LoadLoad 자동 — 0 cycles.
> 결과: write ~30~40 ns, read ~1~5 ns.
>
> 운영 함의: hot path의 volatile write를 줄이는 게 더 효과적. read는 거의 무시.

### Q5 [가지 ④]. JSR-133 Cookbook이 무엇이고 누가 작성?

> Doug Lea 등이 2004년 작성한 JVM 구현자를 위한 메모리 barrier 배치 가이드.
> 8가지 조합 (Normal/Volatile × Load/Store) 별로 필요한 barrier 명시.
> 모든 JVM의 JIT이 이 표를 따라 barrier 삽입.

---

## 7. 학습 체크리스트

- [ ] 0장 마인드맵을 1분 이내로 그릴 수 있다
- [ ] 가지 ①: 4종 barrier (Load/Store 4조합)를 외운다
- [ ] 가지 ①: StoreLoad가 가장 비싼 이유 (Store Buffer flush + cache 일관성)를 설명한다
- [ ] 가지 ②: x86 TSO vs ARM Weakly Ordered를 비교한다
- [ ] 가지 ②: JIT이 platform별 적절한 barrier 삽입함을 인용한다
- [ ] 가지 ③: volatile write의 barrier 배치 (StoreStore + StoreLoad)를 그린다
- [ ] 가지 ③: monitor enter/exit의 barrier를 그린다
- [ ] 가지 ③: CAS의 lock prefix가 implicit full barrier임을 설명한다
- [ ] 가지 ④: JSR-133 Cookbook 8가지 규칙을 표로 적는다
- [ ] 가지 ④: JMH로 측정한 비용 (read ~1ns / write ~10ns / CAS ~10~30ns)을 인용한다
- [ ] 6장 꼬리질문 5개에 답한다

---

## 다음 단계

- → [03. Synchronized + Mark Word](./03-synchronized-and-mark-word.md): synchronized의 3단계 lock
- ← [01. JMM + Happens-Before](./01-jmm-and-happens-before.md)

## 참고

- **JSR-133 Cookbook (Doug Lea, 2004)**: https://gee.cs.oswego.edu/dl/jmm/cookbook.html
- **Intel x86 Memory Ordering Whitepaper**: Intel SDM Vol.3 §8.2
- **ARM Architecture Reference Manual — Memory Order**
- **HotSpot `assembler_x86.hpp` (membar)**: https://github.com/openjdk/jdk/blob/master/src/hotspot/cpu/x86/assembler_x86.hpp
