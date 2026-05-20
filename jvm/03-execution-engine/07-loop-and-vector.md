# 03-07. Loop Optimizations + Vectorization — C2의 hot loop 최적화

> Hot loop는 거의 모든 Java 앱 성능의 90%다. C2의 **Loop opt phase**가 그 loop를 어떻게 다루느냐가 peak 성능을 결정한다.
> 4가지 변환: **LICM (Loop Invariant Code Motion)**, **RCE (Range Check Elimination)**, **Loop Unrolling**, **SuperWord (SIMD vectorization)**.
> 시니어가 알아야 할 것: 같은 알고리즘이라도 **loop 안에 if/method call/Object array** 가 들어가면 SuperWord가 깨져 성능 5~10× 차이. JFR로 hot loop의 SIMD 활용도를 측정할 수 있어야 한다.

---

## 이 문서의 사용법

1. **0장 마인드맵을 먼저 외운다** — 루트 + 4가지 + 키워드.
2. **1~4장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 대응.
3. **5장 면접 워크플로우**, **6장 꼬리질문**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"C2 Loop opt phase는 hot loop를 4단계 변환한다: LICM (invariant 밖으로) → RCE (bound check 제거) → Unrolling (body N배) → SuperWord (SIMD vectorization). 모두 counted loop 전제. if/method call/Object array가 loop 안에 있으면 SuperWord 깨짐 → 성능 5~10× 차이."**

### 4개 가지 — 순서를 외운다

```
              [ROOT: 4단계 loop 변환 + counted loop 전제]
                                  │
       ┌──────────────┬───────────┼───────────┬──────────────┐
       │              │           │           │              │
      ① WHY         ② WHAT       ③ HOW       ④ 운영
   왜 4단계가      4가지 변환    Counted loop  (시니어
   결정적인가?     (LICM/RCE/   인식 +        진단)
                   Unroll/      SuperWord
                   SuperWord)   깨짐
       │              │           │           │
       │         ┌────┼────┐  ┌───┼───┐  ┌────┼────┐
   90% 시간      LICM   RCE    counted  깨짐  Print  perf
   /array bound  invar  bound  loop     패턴  Assembly /IPC
   safety/IPC/   move   check  (for-i)  if    SIMD   SuperWord
   SIMD super    /Unroll/ AVX2  vs       /call  inst  off 비교
   power         body   ×8/16  iterator /Obj  확인
                 N times  ints  /Stream  array
                          AVX-  /Strip
                          512   mining
```

### 가지별 핵심 키워드 (각 가지 3개씩만)

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① WHY** | 90% 시간이 hot loop | array bound safety 비용 | SIMD = CPU 병렬 슈퍼파워 |
| **② WHAT 4변환** | LICM (invariant 밖으로) + RCE (bound check) | Unrolling (4-way) | SuperWord (AVX2 × 8 ints) |
| **③ HOW counted + 깨짐** | Counted loop (`for(i<n)`) 전제 | Iterator/Stream은 counted 아님 | if/call/Object array → SuperWord 깨짐 |
| **④ 운영** | PrintAssembly의 SIMD inst 확인 | perf의 IPC 측정 | Vector API vs SuperWord 비교 |

### 면접 답변 흐름

> 면접관 질문 → 루트 → 가지 → 키워드 3개 → 인접

---

## 1. 가지 ①: WHY — 왜 4단계 loop 변환이 결정적인가

### 1.1 핵심 질문

> "Hot loop의 어떤 비용이 4단계 변환으로 줄어드는 건가요?"

### 1.2 키워드 1 — 90% 시간이 Hot Loop

거의 모든 Java 앱의 hot path는 loop. peak 성능 = loop 성능. 따라서 C2가 가장 공을 들이는 phase가 loop opt.

```
Loop opt phase:
  ① LICM        — invariant code 밖으로
  ② RCE          — array bound check 제거
  ③ Unrolling    — body 복제
  ④ SuperWord    — SIMD 활용
```

### 1.3 키워드 2 — Array Bound Safety 비용 (Java vs C)

```java
// 모든 배열 접근에 JVM이 자동 추가:
if (i < 0 || i >= arr.length) throw new ArrayIndexOutOfBoundsException();
int x = arr[i];
```

- Tight loop의 모든 iteration에 추가 branch.
- C++의 raw array는 이 check 없음 → Java가 C보다 느린 한 이유.

**RCE 적용 후**:
```java
// loop 시작 전 한 번만 check
if (n > arr.length) throw;  // hoisted
for (int i = 0; i < n; i++) {
    int x = arr[i];   // bare load (no check)
}
```

→ Java가 C 수준 속도에 근접. 단, **RCE가 성공해야** 가능.

### 1.4 키워드 3 — SIMD = CPU 병렬 슈퍼파워

```
[일반 unroll - scalar]
4 iteration = 4번의 scalar 산술
즉 sum += arr[0]; sum += arr[1]; sum += arr[2]; sum += arr[3];

[SuperWord (AVX2)]
4 iteration = 1번의 SIMD 산술
vpaddd ymm1, ymm1, [arr]   ; int 4개 한 번에 더함

이론 4× 빠름. 실측 2~3× (memory bandwidth, alignment 영향).
AVX-512는 8× (int) ~ 16× (byte).
```

SIMD는 같은 cycle에 더 많은 일을 함. CPU의 "병렬 슈퍼파워". 옛 C/C++에서는 intrinsic(`_mm_add_epi32`) 명시 필요했지만 Java는 SuperWord 자동.

### 1.5 비유로 굳히기

> **공장 컨베이어 비유**: LICM = 매 제품마다 도구 가져오는 대신 작업장 옆에 미리 둠. RCE = "이 라인은 안전 검사 통과 보장" 후 매 제품의 안전 검사 생략. Unrolling = 한 사이클에 4개 제품 한꺼번에 처리. SuperWord = 4개 동일 작업을 SIMD 머신 1대로 동시에.

---

## 2. 가지 ②: WHAT — 4가지 변환 알고리즘

### 2.1 핵심 질문

> "각 변환이 어떻게 동작하나요? 변환 전후 코드 차이를 보여줄 수 있나요?"

### 2.2 키워드 1 — LICM + RCE

**LICM (Loop Invariant Code Motion)**:
```java
[변환 전]
for (int i = 0; i < n; i++) {
    arr[i] = compute(i) * Math.PI;   // Math.PI는 invariant
}

[변환 후]
double pi = Math.PI;   // hoisted
for (int i = 0; i < n; i++) {
    arr[i] = compute(i) * pi;
}
```

알고리즘:
1. Loop의 dominator 분석.
2. 각 instruction inputs가 모두 loop 밖 또는 invariant + side effect 없음 + safe to speculate? → hoist 가능.
3. Loop preheader로 이동.

**거의 항상 동작**. side effect 있는 함수는 LICM 안 됨 (안전).

**RCE (Range Check Elimination)**:
```
[변환 전]
for (int i = 0; i < n; i++) {
    if (i >= arr.length) throw;
    sum += arr[i];
}

[변환 후 (predicate hoisted)]
if (n > arr.length) {
    // fast loop with no checks (i < arr.length 안전)
    for (i = 0; i < arr.length; i++) sum += arr[i];
    throw new AIOOBE();   // i = arr.length 에서
} else {
    // fast loop, no checks
    for (i = 0; i < n; i++) sum += arr[i];
}
```

알고리즘: loop induction variable 식별 → 범위 추론 (i ∈ [0, n)) → arr.length와 비교 가능? → loop 시작 전 한 번만 check, loop 안 제거.

### 2.3 키워드 2 — Loop Unrolling (4-way)

```
[Unroll 없는 loop body 1회 iteration]
1. compare i < n  (1 cycle)
2. branch          (1~3 cycle, predicted)
3. compute body    (k cycles)
4. i++             (1 cycle)
5. jump back       (1 cycle)
                   = 약 k + 3~5 cycles per iteration

[4-way unroll]
4 iteration 분량 body + branch overhead 1번
                   = 약 4k + 3 cycles for 4 iteration
                   = (4k + 3) / 4 ≈ k + 0.75 cycles per iteration

→ branch/i++ overhead가 1/4로
→ CPU pipeline이 독립 instruction 병렬 실행 가능 (ILP)
```

알고리즘:
```
for (i = 0; i < n; i++) { body; }
  →
for (i = 0; i + factor <= n; i += factor) {
    body[i]; body[i+1]; ...; body[i+factor-1];
}
for (; i < n; i++) { body[i]; }   // tail handling
```

Unroll factor 보통 4 또는 8 (`-XX:LoopUnrollLimit=60`).

### 2.4 키워드 3 — SuperWord (SIMD)

```
1. Unrolled loop의 instruction들을 봄.
2. 같은 op + 인접 메모리 access인 instruction 그룹 식별:
   - sum += arr[i]   →  Add(sum, Load arr[i])
   - sum += arr[i+1] →  Add(sum, Load arr[i+1])
   - sum += arr[i+2] →  Add(sum, Load arr[i+2])
   - sum += arr[i+3] →  Add(sum, Load arr[i+3])
3. Pack 후보 검증:
   - 메모리 alignment (4-byte 정렬?)
   - 인접 (offset 0, 4, 8, 12)
   - 데이터 의존성 없음
   - CPU의 SIMD width와 일치 (4 ints = 16 bytes = SSE/AVX2)
4. SIMD instruction emit:
   vmovdqu ymm0, [arr + i*4]   ; 4 ints load
   vpaddd  ymm1, ymm1, ymm0     ; 4 ints add
```

위치: `src/hotspot/share/opto/superword.cpp`. `-XX:+UseSuperWord` 기본 on.

SIMD width:
- SSE2: 128-bit (int 4개)
- AVX2: 256-bit (int 8개)
- AVX-512: 512-bit (int 16개)

---

## 3. 가지 ③: HOW — Counted Loop 인식 + SuperWord 깨짐

### 3.1 핵심 질문

> "어떤 loop가 변환 대상이고, 어떤 패턴이 SuperWord를 깨뜨리나요?"

### 3.2 키워드 1 — Counted Loop 전제

C2의 모든 loop opt는 **counted loop**가 전제:
```java
for (int i = 0; i < n; i++) { ... }            // ✅ counted
for (int i = n - 1; i >= 0; i--) { ... }       // ✅ counted (backward)
for (long i = 0; i < n; i++) { ... }           // △ long counted, 일부 opt만
for (int i = 0; i < arr.size(); i++) { ... }   // △ size()가 inline + EA + LICM 되어야
while (it.hasNext()) { ... it.next(); ... }    // ❌ counted 아님
```

→ Iterator-based loop는 counted loop opt 못 받음. for-each도 내부적으로 Iterator라 함정.

운영: **hot loop는 가능한 한 indexed for-loop**. Iterator/Stream은 EA가 잘 동작할 때만 비슷.

### 3.3 키워드 2 — SuperWord 깨지는 패턴 4종

```java
// 1. Branch in loop
for (int i = 0; i < n; i++) {
    if (arr[i] > 0) sum += arr[i];   // ← branch → SuperWord 깨짐
}

// 2. Method call (inline 안 됨)
for (int i = 0; i < n; i++) {
    sum += complexCompute(arr[i]);   // call → SuperWord 깨짐
}

// 3. Object array (primitive만 SuperWord 가능)
String[] strs = ...;
for (int i = 0; i < n; i++) {
    process(strs[i]);   // Object array → SuperWord 안 됨
}

// 4. 복잡 indexing
int[][] grid = ...;
for (int i = 0; i < n; i++) {
    sum += grid[r][i];   // grid[r]를 매 iter에서 load → LICM 후 OK
}
```

운영: hot loop의 안에 분기 또는 method call이 들어가면 SuperWord 못 받음. 대안:
- 명시적 Vector API (JEP 414, JDK 16+ incubator).
- 또는 알고리즘 재구성 (분기를 loop 밖으로).

### 3.4 키워드 3 — Loop Strip Mining (긴 loop의 safepoint 최적화)

```java
[변환 전]
for (long i = 0; i < 1_000_000_000L; i++) {   // 10억
    sum += data[i % size];
}
// 각 iteration의 back-edge에 safepoint poll → 10억 번 poll
// → loop hot path에 oversized overhead

[Strip mining 후]
for (long outer = 0; outer < total; outer += stride) {
    // ★ safepoint poll outer에만
    for (long i = outer; i < outer + stride; i++) {
        sum += data[i % size];   // inner는 poll 없음
    }
}
```

→ Long-running computation의 latency 영향 ↓. JDK 11+ 도입.

### 3.5 Loop opt phase 진입 코드

위치: `src/hotspot/share/opto/loopnode.cpp`:

```cpp
void PhaseIdealLoop::optimize(...) {
    build_loop_tree();
    do_loop_invariants();           // 1. LICM
    insert_loop_predicates();       // 2. Loop predicate 삽입 (RCE 준비)
    eliminate_range_checks();       // 3. RCE
    do_unroll();                    // 4. Unrolling
    SuperWord sw(this);
    sw.transform_loop();            // 5. SuperWord
}
```

---

## 4. 가지 ④: 운영 — 시니어 진단

### 4.1 핵심 질문

> "Hot loop가 SIMD instruction을 실제로 쓰는지, 알고리즘 변경이 SuperWord에 어떤 영향인지 어떻게 측정하나요?"

### 4.2 키워드 1 — `-XX:+PrintAssembly`로 SIMD 확인

```bash
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintAssembly \
     -XX:CompileCommand=print,MyApp::sum \
     -jar app.jar | grep -iE 'vpaddd|vmovdqu|ymm|zmm'
```

출력에 SIMD instruction:
- `vpaddd ymm0, ymm1, ymm2` — AVX2 int 8개 add.
- `vmovdqu ymm0, [arr+i*4]` — AVX2 load.
- `zmm*` — AVX-512.

보이면 SuperWord 성공. 없으면 깨짐 — 원인 진단 필요.

### 4.3 키워드 2 — `perf`의 IPC 측정

```bash
perf stat -e instructions,cycles,cache-misses,L1-dcache-load-misses \
    java -jar app.jar
```

`insn per cycle (IPC)`:
- 1.0~2.0: 보통 scalar 코드.
- 3.0+: SIMD + unrolling 효과 좋음.
- 5.0+: 매우 좋은 vectorization.

IPC가 낮으면 cache miss 또는 branch misprediction 의심.

### 4.4 키워드 3 — Vector API vs SuperWord

```java
// JDK 21 (incubator)
import jdk.incubator.vector.IntVector;

void sum(int[] arr) {
    IntVector vsum = IntVector.zero(IntVector.SPECIES_256);
    for (int i = 0; i < arr.length; i += 8) {
        IntVector v = IntVector.fromArray(IntVector.SPECIES_256, arr, i);
        vsum = vsum.add(v);
    }
    int total = vsum.reduceLanes(VectorOperators.ADD);
}
```

| | SuperWord | Vector API |
|---|---|---|
| 작성 복잡도 | 낮음 (일반 코드) | 높음 (vector primitives) |
| 적용 조건 | 까다로움 (단순 loop만) | 자유로움 |
| Cross-platform | ✅ JVM 처리 | ✅ JVM 처리 |
| 최적화 보장 | △ (조건 미달 시 실패) | ✅ (명시적) |
| 사용처 | 일반 numerical | HPC, ML inference |

선택:
- 일반 numerical: SuperWord (자연스러운 코드).
- 복잡 SIMD (shuffle, gather, scatter): Vector API.
- SuperWord가 깨지는 알고리즘: Vector API로 강제.

### 4.5 운영 시나리오 매트릭스

| 증상 | 진단 | 가능 원인 |
|---|---|---|
| 알고리즘 같은데 C++ 대비 5× 느림 | PrintAssembly에 SIMD 없음 | SuperWord 실패 |
| Vector API 도입 효과 없음 | PrintAssembly 비교 | 이미 SuperWord 잘 됨 |
| AVX-512 자동 활용? | CPU info + PrintAssembly (`zmm`) | JDK 버전 + CPU 둘 다 지원? |
| 긴 loop의 GC pause 길음 | Loop Strip Mining 확인 | safepoint poll inner loop |

### 4.6 Killer 시나리오 — 같은 알고리즘 5× 차이

```
환경: 같은 알고리즘의 Java 코드 두 가지, 한 쪽이 5× 빠름

진단:
1. PrintAssembly로 native code 비교
   -XX:+UnlockDiagnosticVMOptions -XX:+PrintAssembly
   -XX:CompileCommand=print,...
   SIMD instruction (vpaddd, vmovdqu) 유무 확인

2. JITWatch로 inlining tree
   - 느린 쪽: 메서드 call이 inline 안 됨 → SuperWord 깨짐
   - 빠른 쪽: 모든 call inline → SuperWord 성공

3. 코드 차이 식별
   - if/else 분기 추가?
   - Iterator vs indexed loop?
   - Object array vs primitive array?

4. 수정 후 검증
   - 변경 후 PrintAssembly로 SIMD 재확인
   - JMH로 정량 측정
```

---

## 5. 면접 답변 워크플로우

### 5.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "C2의 loop 최적화?" | ② WHAT (4변환) | ① WHY 중요성 |
| "SuperWord가 뭔가요?" | ② WHAT (SIMD) | ③ HOW 깨짐 |
| "RCE가 왜 중요?" | ① WHY (bound safety) | ② RCE 알고리즘 |
| "Iterator/Stream loop opt?" | ③ HOW (counted 아님) | EA + inline |
| "Loop Strip Mining?" | ③ HOW | safepoint 영향 |
| "Vector API와 SuperWord?" | ④ 운영 (선택) | ③ 깨짐 패턴 |
| "5× 차이 원인 진단?" | ④ Killer | PrintAssembly + JITWatch |

### 5.2 답변 템플릿

> 루트 → 가지 키워드 3개 → 인접

예: "C2의 loop optimization phase는 어떤 변환을 하나요?"

> "C2의 Loop opt phase는 4가지 변환으로 hot loop를 다룹니다. (← 루트)
> 첫째, **LICM (Loop Invariant Code Motion)** — invariant computation을 loop 밖으로 hoist. `Math.PI * x` 같은 패턴.
> 둘째, **RCE (Range Check Elimination)** — Java의 모든 배열 접근에 자동 삽입되는 bound check를 loop 시작 전 한 번만 검사하도록 변환. Java가 C 수준 속도에 근접하는 핵심 메커니즘.
> 셋째, **Loop Unrolling** — body를 4 또는 8번 복제. branch overhead 1/N로 줄이고 CPU pipeline ILP 활용.
> 넷째, **SuperWord (SIMD Vectorization)** — unrolled loop의 인접 iteration을 SIMD instruction으로 packing. AVX2 256-bit으로 int 8개 한 번에 처리.
> 모든 변환의 전제는 **counted loop** (`for (int i = 0; i < n; i++)`). Iterator나 Stream은 counted 아니라 못 받음. SuperWord는 추가로 까다로워서 loop 안에 if, method call, Object array가 들어가면 깨짐 — 실측 5~10× 차이로 나타납니다."

---

## 6. 꼬리질문 트리 (가지별)

### Q1 [가지 ②]. SuperWord가 무엇이고 어떤 조건에서 동작하나요?

> C2의 auto-vectorization phase. Unrolled loop의 인접 iteration의 동일 연산을 SIMD instruction으로 packing.
> 조건:
> 1. Counted loop (`for (int i = 0; i < n; i++)`).
> 2. 단일 primitive type (int[], float[], double[] — Object[] 안 됨).
> 3. 단순 산술/load/store만 (call, branch 없음).
> 4. 인접 메모리 access + alignment.
> 5. CPU가 해당 SIMD width 지원 (AVX2 등).
> 깨지는 패턴: if/else in loop, inline 안 된 method call, Object array, complex indexing.

### Q2 [가지 ①]. RCE가 Java의 성능에 중요한 이유는?

> Java의 모든 배열 접근은 자동 bound check (`i < arr.length`). C/C++는 없음.
> Tight loop의 모든 iteration에 추가 branch → 성능 저하.
> RCE: loop 시작 전 한 번만 check, loop 안은 제거 → Java가 C 수준 속도.
> 단, RCE 성공 조건: induction variable의 범위가 arr.length 안에 있음을 증명 가능해야.

### Q3 [가지 ③]. Loop Strip Mining이 무엇이고 왜 도입됐나요?

> 매우 긴 loop의 safepoint poll 문제 해결.
> 문제: counted loop의 back-edge에 safepoint poll → 10억 iteration이면 10억 번 poll → loop hot path에 oversized overhead.
> 해결: outer + inner loop로 분리.
> - Outer loop에만 safepoint poll.
> - Inner loop는 poll 없이 빠르게.
> - Loop iteration N개씩 묶어 처리.
> JDK 11+ 도입. 긴 numerical computation의 latency 개선.

### Q4 [가지 ④]. Vector API와 SuperWord의 차이는?

> - **SuperWord**: 자동. 단순 loop에 적용. C2가 컴파일 시 결정.
> - **Vector API**: 수동. 명시적 SIMD primitive 사용. JDK 16+ incubator (JEP 414).
> 선택:
> - 일반 numerical: SuperWord (자연스러운 코드).
> - HPC/ML inference (복잡 SIMD 패턴 — shuffle, gather): Vector API.
> - SuperWord가 깨지는 알고리즘 (if 분기, method call): Vector API로 강제.

### Q5 [가지 ③]. Iterator-based loop는 왜 loop opt를 못 받나요?

> C2의 loop opt는 **counted loop** 전제 — induction variable의 trip count 추론 가능해야 함 (`for (int i = 0; i < n; i++)`).
> Iterator의 `hasNext() / next()` 패턴은 trip count 추론 불가 — 매 iteration마다 method call로 결정.
> for-each도 내부적으로 Iterator라 함정.
> 회피: hot loop는 가능한 한 indexed for-loop. Iterator/Stream은 EA + inline이 잘 동작할 때만 비슷한 성능.

### Q6 (Killer) [가지 ④]. 같은 알고리즘의 Java 코드가 두 가지인데 한 쪽이 5× 빠릅니다. 원인을 어떻게 찾을까요?

> 1. **PrintAssembly로 native code 비교**:
>    ```
>    -XX:+UnlockDiagnosticVMOptions -XX:+PrintAssembly
>    -XX:CompileCommand=print,...
>    ```
>    SIMD instruction (vpaddd, vmovdqu) 유무 확인.
> 2. **JITWatch로 inlining tree**:
>    - 느린 쪽: 메서드 call이 inline 안 됨 → SuperWord 깨짐.
>    - 빠른 쪽: 모든 call inline → SuperWord 성공.
> 3. **코드 차이 식별**:
>    - if/else 분기 추가?
>    - Iterator vs indexed loop?
>    - Object array vs primitive array?
>    - counted loop 깨짐?
> 4. **수정 후 검증**:
>    - 변경 후 PrintAssembly로 SIMD 재확인.
>    - JMH로 정량 측정.
>    - perf의 IPC 비교 (3.0+ → SIMD 성공).

---

## 7. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 이내로 그릴 수 있다 (루트 + 4가지 + 키워드 3개)
- [ ] 가지 ① WHY: 90% hot loop / array bound safety / SIMD 슈퍼파워 설명한다
- [ ] 가지 ② WHAT: 4변환 (LICM/RCE/Unroll/SuperWord) 각각 코드 변환 그린다
- [ ] 가지 ② WHAT: AVX2/AVX-512 width 차이 말한다 (8 ints vs 16 ints)
- [ ] 가지 ③ HOW: counted loop 인식 조건 + Iterator/Stream 함정 설명한다
- [ ] 가지 ③ HOW: SuperWord 깨지는 4가지 패턴 (if/call/Object array/complex idx) 외운다
- [ ] 가지 ③ HOW: Loop Strip Mining의 safepoint 최적화 설명한다
- [ ] 가지 ④ 운영: PrintAssembly로 SIMD inst 확인 방법 말한다
- [ ] 가지 ④ 운영: Vector API vs SuperWord 선택 기준 (HPC/복잡 vs 일반) 비교한다
- [ ] 가지 ④ 운영: 5× 차이 원인 진단 4단계 (PrintAssembly → JITWatch → 코드 → 검증) 말한다
- [ ] 6장 꼬리질문 6개에 막힘없이 답한다

---

## 다음 단계

- → [08. Speculative and Deopt](./08-speculative-and-deopt.md): Speculation 깨짐 시 deopt
- ← [04. C1 and C2](./04-c1-and-c2.md): Loop opt가 C2 phase ④
- ← [05. Inlining](./05-inlining-and-ic.md): inlining이 loop opt의 전제 (method call inline)
- ← [06. Escape Analysis](./06-escape-analysis.md): EA가 loop 안 객체 제거

## 참고

- **HotSpot src `loopnode.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/opto/loopnode.cpp
- **HotSpot src `superword.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/opto/superword.cpp
- **JEP 414 Vector API**: https://openjdk.org/jeps/414
- **Intel Intrinsics Guide** (SIMD 참조): https://www.intel.com/content/www/us/en/docs/intrinsics-guide/
- **Aleksey Shipilëv — Vectorization**: https://shipilev.net/jvm/anatomy-quarks/
