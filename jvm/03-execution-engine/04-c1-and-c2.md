# 03-04. C1 and C2 — 두 컴파일러의 IR과 phase 순서

> HotSpot 안에는 컴파일러가 두 개 있다.
> **C1 (Client Compiler)** — 빠른 컴파일. HIR/LIR, CFG 기반. 1999년 Sun, ~3,000줄 C++.
> **C2 (Server Compiler)** — 공격적 최적화. Sea-of-Nodes, 1995년 Cliff Click 박사 논문. ~50,000줄 C++.
> 같은 bytecode를 받아 다른 IR로 변환하고 다른 phase를 거쳐 다른 성능 특성의 native code를 만든다.
> 시니어가 알아야 할 것: 단순히 "C1은 빠르고 C2는 깊다"가 아니라, **각 IR이 어떤 최적화를 가능하게 하는지** + **C2 phase 순서**가 운영 시 측정·진단의 기반이다.

---

## 이 문서의 사용법

1. **0장 마인드맵을 먼저 외운다** — 루트 + 4가지 + 키워드.
2. **1~4장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 대응.
3. **5장 면접 워크플로우**, **6장 꼬리질문**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"C1은 HIR/LIR CFG 기반 + Linear Scan RA → 수 ms 컴파일 + ~50% 성능. C2는 Sea-of-Nodes + Graph Coloring RA + 7-phase pipeline → 수십~수백 ms 컴파일 + peak 성능. IR이 다른 게 본질 — Sea-of-Nodes는 노드 위치를 마지막 scheduling phase까지 미뤄서 자유로운 최적화를 가능하게 한다."**

### 4개 가지 — 순서를 외운다

```
                  [ROOT: 두 컴파일러, 두 IR, 다른 phase pipeline]
                                  │
       ┌──────────────┬───────────┼───────────┬──────────────┐
       │              │           │           │              │
      ① WHY 두 IR    ② WHAT C2    ③ HOW       ④ 운영
   왜 다른 IR을      phase 7단계  Register    (시니어
   쓰는가?                        Allocation  진단)
       │              │           │           │
       │         ┌────┼────┐  ┌───┼───┐  ┌────┼────┐
   CFG 단순/    Parse  Inline+EA  Scheduling C1:    Print  C1 stuck/
   빠름 vs      IterGVN Loop      Linear    Linear  Compil C2 timeout/
   Sea-of-      Macro+  Schedule  Scan      Scan   ation  -XX:Compile
   Nodes 공격적 CCP    +RA+Output                   /Print Command
   /node       Output                       C2:    Assembly
   위치 자유                                Graph  /JITWatch
                                            Coloring
                                            (Chaitin)
```

### 가지별 핵심 키워드 (각 가지 3개씩만)

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① WHY 두 IR** | CFG 단순/빠름 (C1) | Sea-of-Nodes 자유 노드 이동 (C2) | 트레이드오프 (~ms vs ~10ms) |
| **② WHAT C2 phase 7단계** | Parse → IterGVN | Inline+EA → Loop opts → Macro+CCP | Scheduling + RA → Output |
| **③ HOW Register Allocation** | C1: Linear Scan O(n log n) | C2: Graph Coloring O(n²~n³) Chaitin | spill 차이 (memory access) |
| **④ 운영** | -XX:+PrintCompilation tier | C1 stuck / C2 timeout | JITWatch + PrintAssembly |

### 면접 답변 흐름

> 면접관 질문 → 루트 → 적절한 가지 → 키워드 3개 → 인접 가지

---

## 1. 가지 ①: WHY — 왜 두 IR을 쓰는가

### 1.1 핵심 질문

> "한 컴파일러로 통일하지 않고 C1과 C2를 둘 다 두는 이유, 그리고 두 IR이 본질적으로 다른 이유는?"

### 1.2 키워드 1 — CFG 기반 (C1): 단순 + 빠름

```
CFG (Control Flow Graph) 기반 IR:
- basic block 명시
- 각 instruction이 어느 block 소속 명확
- control flow와 data flow가 분리
- 최적화는 각 block 안 또는 block들 사이
- 분석/변환이 단순 → 컴파일 시간 ~수 ms
- 단점: cross-block 최적화 제약 (code motion 어려움)
```

C1의 흐름: bytecode → HIR (High-level IR, SSA + CFG) → LIR (Low-level IR, instruction selection 근접) → Linear Scan RA → native code.

### 1.3 키워드 2 — Sea-of-Nodes (C2): 자유로운 노드 이동

```
Sea-of-Nodes:
- basic block 명시 안 함
- control flow와 data flow가 한 그래프
- 노드 사이는 dependency edge로만 연결
- 노드의 실제 위치는 "Scheduling" phase에서 결정
- → 노드를 자유롭게 옮기는 최적화 자연스러움
```

**자유 노드 이동의 가치**:

```
[CFG의 한계]
basic block A:                basic block B:
  x = expensive_calc()         y = x + 1

→ x의 계산이 A에 묶임. B에서만 쓰인다면 B로 옮기는 게 좋지만
   별도 "code motion" 패스가 필요하고 제약 많음.

[Sea-of-Nodes의 우위]
expensive_calc(), x+1이 노드로 존재. basic block 미정.
  → scheduling phase에서 "B에서만 쓰인다면 B에 두자"
  → 자연스럽게 code motion
  → loop hoisting, dead code elimination도 같은 방식
```

### 1.4 키워드 3 — 트레이드오프

| | C1 | C2 |
|---|---|---|
| 메서드당 컴파일 시간 | ~수 ms | ~수십~수백 ms |
| Peak 성능 (vs 인터프리터) | ~10~30× | ~50~100× |
| nmethod 크기 | 작음 | 큼 (inlining 등) |
| 컴파일 시 메모리 (per task) | ~수 MB | ~수십~수백 MB |
| 코드 크기 (컴파일러 자체) | ~3,000줄 | ~50,000줄 |

C1은 "충분히 빠른 baseline + profile 수집기" 역할. C2는 peak 성능. 둘 다 필요.

### 1.5 비유로 굳히기

> **건축 설계 비유**: C1 = 미리 정해진 도면 위에 자재 배치. 1층은 1층 자재만. 옮길 범위 제한. C2 = 자재들의 의존 관계만 정의 ("기둥은 바닥 다음에 설치"). 어느 층에 둘지는 scheduling phase에서 결정. 자유로운 이동.

### 1.6 핵심 용어 깊이 사전

> 1.2~1.4에서 쓴 용어들의 본질을 밑바닥부터 쌓아 올린다. **IR → basic block → CFG → HIR/LIR → SSA → code motion 제약 → RA** 순서로 읽으면 "왜 IR이 다르면 모든 게 달라지는지" 한 번에 잡힘.

#### 1.6.1 IR (Intermediate Representation) — 컴파일러의 "중간 언어"

> **IR = 소스 코드(bytecode)와 native code 사이의 중간 표현.** 컴파일러는 bytecode를 바로 native로 안 바꿈. 먼저 IR로 변환 → IR 위에서 최적화 → 그다음 native.

```
[IR 없는 가상]
bytecode → 직접 native code        ← 최적화 거의 불가능 (어떻게 합치고 옮기지?)

[IR 사용 (실제)]
bytecode → IR로 변환
   ↓ IR 위에서 패스 수십~수백 개
   ↓ "이 변수는 안 쓰임" "이 두 계산은 같음" 분석/변환
IR → native code
```

HotSpot의 IR:
- **C1**: bytecode → **HIR** → **LIR** → native (두 단계 IR)
- **C2**: bytecode → **Sea-of-Nodes** → native (한 단계, 다른 구조)

#### 1.6.2 Basic Block — "일직선으로 실행되는 instruction 묶음"

> **Basic block = 처음부터 끝까지 분기 없이 일직선 실행되는 instruction 묶음.** 중간에 점프 안 들어옴, 중간에 점프 안 나감.

```java
int example(int a, int b) {
    int x = a + b;        // ┐
    int y = x * 2;        // ├─ Block 1: 일직선
    int z = y - 3;        // ┘
    if (z > 0) {          // ← Block 1의 끝 (분기)
        return z;         // ─── Block 2: return
    } else {
        return -z;        // ─── Block 3: return
    }
}
```

**규칙**: 시작점 = 메서드 entry / branch target / branch 바로 다음. 끝 = branch 명령어 (jmp, if, return, throw). **block 안에서는 마지막까지 무조건 순차 실행** — 그래서 "기본 단위(basic)".

#### 1.6.3 CFG (Control Flow Graph) — basic block들의 연결 그래프

> **CFG = basic block들이 노드, 분기가 edge인 directed graph.** "프로그램이 어떤 순서로 흘러갈 수 있나"를 그림으로.

```
        ┌─────────────────────┐
        │ Block 1             │
        │  x = a + b          │
        │  y = x * 2          │
        │  z = y - 3          │
        │  if (z > 0) ────────┼──┬─→
        └────────┬────────────┘  │
                 │ (z > 0)       │ (z ≤ 0)
                 ▼               ▼
        ┌────────────────┐  ┌────────────────┐
        │ Block 2        │  │ Block 3        │
        │  return z      │  │  return -z     │
        └────────────────┘  └────────────────┘
```

CFG에서 알 수 있는 것: **Control flow** (어디로 갈 수 있나) + **Dominance** (X 가려면 반드시 Y 거쳐야) + **Reachability** (도달 가능한가, 아니면 dead code).

→ **CFG는 컴파일러가 코드를 분석하는 가장 기본적인 그림**. 거의 모든 분석이 CFG 위에서 시작.

#### 1.6.4 HIR vs LIR — 추상화 수준

> **HIR = high-level (자바 의미 가까움)**, **LIR = low-level (CPU 명령어 가까움)**. C1은 두 단계를 거치면서 점점 lower한 표현으로.

```
HIR (자바 의미 그대로)              LIR (CPU 명령어 가까움)
━━━━━━━━━━━━━━━━━━━━              ━━━━━━━━━━━━━━━━━━━

v1 = LoadField(this, "x")    ───→  reg_a = LoadObject(this)
   (한 노드)                         reg_b = LoadInt[reg_a + 16]
                                     (이미 mov 명령에 가까움)

v2 = NewArray(int, n)        ───→  reg = TLAB_top
   (한 노드)                         TLAB_top += n * 4 + 16
                                     [reg + 0] = ArrayKlass
                                     [reg + 8] = n
                                     ...

v3 = InvokeVirtual(...)      ───→  reg_klass = [this + klass_offset]
   (한 노드)                         reg_method = [reg_klass + vtable + idx*8]
                                     call reg_method
```

→ **HIR이 "자바가 보는 그림"이면 LIR은 "CPU가 보는 그림"**. C1은 HIR에서 high-level 최적화 → LIR로 풀어서 instruction-level 결정.

#### 1.6.5 SSA (Static Single Assignment) — "한 변수는 한 번만 할당"

> **SSA = 모든 변수가 정확히 한 번만 대입되는 IR 형태.** 같은 이름 변수가 여러 번 대입되지 않게 매번 새 이름.

```
[원본]                          [SSA]
x = 1;                          x_1 = 1;
x = x + 2;                      x_2 = x_1 + 2;
x = x * 3;                      x_3 = x_2 * 3;
print(x);                       print(x_3);
```

**왜 SSA인가**:
```
[비-SSA]
"x가 무슨 값?" → 코드 따라가 봐야 함
"x의 모든 정의 찾기" → 전체 스캔

[SSA]
"x_2가 무슨 값?" → 단 한 곳의 정의만 봄
"x_2의 모든 사용처" → use-def chain 한 방
```

**Phi 노드** — 분기 합치는 자리에서 "어느 path로 왔냐"에 따라 값 선택:

```java
if (cond) { x = 1; } else { x = 2; }
print(x);

→ SSA:
if (cond) { x_1 = 1; } else { x_2 = 2; }
x_3 = phi(x_1, x_2);   ★ Phi: cond에 따라 x_1 또는 x_2
print(x_3);
```

→ **현대 컴파일러 IR은 거의 다 SSA**. C1 HIR도 SSA, C2 Sea-of-Nodes도 SSA.

#### 1.6.6 Cross-block 최적화 제약 — CFG의 본질적 한계

> **Cross-block 최적화 = basic block 경계 넘는 최적화** (LICM, code motion 등). CFG에서는 instruction이 특정 block에 묶여있어 어려움.

```
[CFG의 묶임 문제]
Block 1:                       Block 2:
  x = expensive_calc()           y = x + 1   ← Block 2에서만 x 사용
  cond = ...                     return y

→ x 계산을 Block 2로 옮기면 좋음 (필요할 때만 계산)
→ 그러나 CFG에서 x = ...는 "Block 1 instruction list의 [0]"에 묶임
→ 옮기려면 별도 패스(code motion)가:
   1. Block 1 list에서 제거
   2. Block 2 list 어디에 넣을지 결정
   3. data dependency 검증
   4. control dependency 검증
→ 패스 복잡 + 제약 많음
```

**Sea-of-Nodes는 이 문제 없음**: basic block을 명시하지 않고 dependency edge만 있어, **마지막 scheduling phase에서 처음으로 block 배치 결정**. 옮기는 게 아니라 처음부터 자유로움.

#### 1.6.7 Code Motion — "코드 실행 위치를 옮기는 최적화"

> **Code motion = 코드의 실행 위치를 옮겨 빠르게 만드는 최적화 기법들의 총칭.** Loop 안에서 밖으로, 자주 안 실행되는 자리로 미루기 등.

**대표 1: LICM (Loop Invariant Code Motion)**
```java
// [원본]
for (int i = 0; i < n; i++) {
    int x = a * b;           ★ 매 iteration 같은 값 반복 계산
    result[i] = i + x;
}

// [LICM 적용]
int x = a * b;               // loop 밖으로
for (int i = 0; i < n; i++) {
    result[i] = i + x;
}
// → n번 → 1번
```

**대표 2: Lazy Computation**
```java
// [원본]
int x = expensive_calc();
if (rare_condition) { use(x); }
// → x는 1%만 필요한데 매번 계산

// [Lazy로 이동]
if (rare_condition) {
    int x = expensive_calc();
    use(x);
}
// → 1%로 줄어듦
```

**Sea-of-Nodes에서 왜 자연스러운가**:
```
Sea-of-Nodes의 노드는 위치 미정
   ↓
Scheduling phase가 "가능한 한 늦은 자리(use 직전)에 두자"
   ↓
자동으로 if 분기 안에 배치
   ↓
별도 LICM 패스 없이 자연 code motion
```

CFG 기반(C1)은 LICM 전용 패스를 따로 짜야 함. Sea-of-Nodes(C2)는 scheduling phase 하나가 거의 다 처리.

#### 1.6.8 Register Allocation 깊이 — Linear Scan vs Graph Coloring

**배경**: IR은 무한 개 virtual register 가정 (x_1, ..., x_1000). Native code의 진짜 register는 ~16개. → 매핑 필요. 부족하면 **spill**(memory에 임시 보관).

**Live Interval** = "이 변수가 언제부터 언제까지 쓰이나":
```
1: x_1 = ...           x_1: [1, 2]
2: x_2 = x_1 + 1       x_2: [2, 3]
3: x_3 = x_2 * 2       x_3: [3, 4]
4: print(x_3)
```
→ 같은 시점 동시 live인 변수 수가 register 부족 trigger.

**Linear Scan (C1)** — 빠른 휴리스틱:
```
1. 모든 interval 계산
2. 시작 시점 순 정렬 (O(n log n))
3. 정렬 순서로 linear scan:
   - 끝난 interval의 register free
   - free에서 하나 할당
   - free 없으면 → 가장 멀리 쓰일 register spill
4. 시간 O(n log n), 공간 단순
```
**특징**: 빠름, 결과 약간 부족, spill 더 자주.

**Graph Coloring (C2, Chaitin)** — 느린 정밀:
```
1. Interference graph 구축:
   - virtual reg = node
   - 동시 live = edge로 연결 (같은 색 못 가짐)
2. Simplification: degree < K 인 node 제거 (stack push)
3. Spill: degree ≥ K 인 node를 spill 후보
4. Selection: stack pop하며 색칠
5. Coalescing: move 명령 제거
6. NP-hard → 휴리스틱
7. 시간 O(n²~n³)
```
**특징**: 느림, 결과 거의 최적, spill 최소.

**결과 차이 — 같은 코드, 다른 nmethod**:
```
[C1 Linear Scan 결과]               [C2 Graph Coloring 결과]
mov  rax, [rbp-8]    ; spill load   add  rax, rbx        ; register만
add  rax, rbx                        add  rcx, rax
mov  [rbp-16], rax   ; spill store   ...
... 메모리 접근 빈번                  ... 메모리 접근 거의 없음
```

→ RA 차이가 peak 성능에 직접 영향. **C2 nmethod가 빠른 본질의 절반은 좋은 RA**.

#### 1.6.9 전체 흐름 — 두 컴파일러를 한 줄로

```
bytecode 한 메서드
    │
    ├─ C1 path:
    │    bytecode → HIR (자바 의미, SSA, CFG 형태)
    │              ↓ HIR 위 high-level 최적화 (CFG 한계로 cross-block 제약)
    │              ↓ HIR → LIR (CPU instruction 가까움)
    │              ↓ LIR 위 Linear Scan RA
    │              ↓ → native code (~수 ms, spill 자주, ~50% 성능)
    │
    └─ C2 path:
         bytecode → Sea-of-Nodes (basic block 미정, dependency만, SSA)
                   ↓ IterGVN → Inline+EA → Loop opts → Macro+CCP
                   ↓ (자유 code motion — 추가 패스 거의 없이)
                   ↓ Scheduling phase가 노드 위치 결정 (처음 block 배치)
                   ↓ Graph Coloring RA
                   ↓ → native code (~수십~수백 ms, spill 적음, peak)
```

#### 1.6.10 한 줄씩 종합

| 용어 | 한 줄 |
|---|---|
| **IR** | 소스(bytecode)와 native code 사이의 중간 표현. 컴파일러가 최적화하는 자료구조 |
| **Basic block** | 처음부터 끝까지 분기 없이 일직선 실행되는 instruction 묶음 |
| **CFG** | basic block이 노드, 분기가 edge인 그래프. "어떤 순서로 흘러갈 수 있나" |
| **HIR** | 자바 의미 가까운 high-level IR. invokevirtual, newarray가 한 노드 |
| **LIR** | CPU 명령어 가까운 low-level IR. HIR 한 노드가 LIR 여러 노드로 풀림 |
| **SSA** | 한 변수가 한 번만 할당되는 IR 형태. Phi 노드로 분기 합침. 분석 쉬움 |
| **Cross-block 최적화 제약** | CFG에서는 instruction이 특정 block에 묶여 있어 block 경계 넘는 최적화가 별도 패스 + 제약 많음 |
| **Code motion** | 코드 실행 위치 옮기는 최적화 (LICM, lazy). CFG에선 어렵고 Sea-of-Nodes에선 scheduling으로 자연스러움 |
| **Register Allocation** | 무한 virtual register를 한정된 physical register에 배정. 부족하면 memory에 spill |
| **Linear Scan (C1)** | live interval 시작 시점 순 linear scan. O(n log n), 빠름, spill 자주 |
| **Graph Coloring (C2)** | interference graph로 K-coloring (Chaitin). O(n²~n³), 느림, spill 최소, native code 빠름 |

### 1.7 설계 동기 — 왜 C1은 CFG, C2는 Sea-of-Nodes인가

> 1.6에서 "두 IR이 무엇인가"를 다뤘다면, 여기는 "왜 이 IR이 이 컴파일러에 최적인가"의 깊이 답. **"역할이 다르니 IR도 다르다"** — 우연이 아닌 설계.

#### 1.7.1 두 컴파일러의 사명이 다르다

```
C1의 사명:
  "수 ms 안에 baseline 성능의 native code를 만들어라"
  + Tiered에서 profile 수집기 역할

C2의 사명:
  "peak 성능. 컴파일 시간 비싸도 좋다.
   한 번 컴파일하면 평생 실행되니까"
```

→ 사명이 다르면 무엇을 최적화해야 하는지가 다름. IR도 다른 게 자연.

#### 1.7.2 C1이 CFG를 선택한 5가지 이유

**① 컴파일 시간이 짧아야 한다**
- CFG: basic block + edges = 단순. 패스 대부분 O(n) ~ O(n log n)
- Sea-of-Nodes: 전체 그래프 spanning 분석 많음. O(n²) 흔함
- Tier 3 컴파일이 ~수 ms 안에 끝나야 Tiered 의미. CFG가 시간 안에 들어옴.

**② 메모리를 적게 쓴다**
- CFG: 컴파일 task당 ~수 MB
- Sea-of-Nodes: 노드별 edge + def-use chain + type lattice → ~수십~수백 MB
- C1이 메모리 많이 쓰면 동시 CompilerThread task 수 제한 → Tier 3 처리율 ↓

**③ 구현이 단순하다 — 3,000 vs 50,000줄**
- CFG: 1970년대부터 잘 알려진 알고리즘 풍부
- Sea-of-Nodes: 1995년 Cliff Click 박사 논문이 효시, 정교/어려움
- C1은 거의 항상 호출되는 컴포넌트 → 버그 적고 단순해야 안정

**④ Profile-instrumented 코드 생성이 자연스럽다**
- Tier 3 = C1 with full profiling — native code에 counter 박아야 함
- CFG: instruction이 특정 block에 묶임 → "여기 박아라" 명확
- Sea-of-Nodes: 노드 위치가 scheduling 전까지 미정 → instrumentation 위치 보장 까다로움

**⑤ 보수적 최적화 목표라 CFG 한계가 문제 안 됨**
- C1 목표: ~50% of peak (단순 GVN, dead code, simple inlining)
- 공격적 cross-block code motion, 전역 EA, SIMD는 어차피 C2 일
- "못 하는 게 아니라 안 하는" — 단순한 CFG가 최적

#### 1.7.3 C2가 Sea-of-Nodes를 선택한 5가지 이유

**① 공격적 code motion이 자연스럽다**
```
[CFG라면 (가상)]                    [Sea-of-Nodes (실제)]
LICM:    전용 패스 필요              노드 위치 미정 + dependency만
Lazy:    전용 패스 필요              ↓
Dead:    별도 패스                  Scheduling phase 하나가 처리:
Const:   별도 패스                    schedule_early + schedule_late
                                     자동으로 LICM + lazy + dead 적용
```
→ 여러 최적화가 **IR 자체의 속성으로 자동**. C2 핵심 우위.

**② GVN + Constant Folding이 강력하다**
- SSA + dependency edge → 같은 값 노드 hash로 찾아 통합
- IterGVN이 fixpoint까지 cascade 잡음
- Cliff Click 박사 논문 제목 **"Combining Analyses, Combining Optimizations"** — Sea-of-Nodes가 그 결합을 가능하게 함

**③ 전역 분석 (Escape Analysis)에 강하다**
- 한 객체의 모든 사용처 = 노드의 모든 outgoing edge
- SSA + 한 그래프 → use-def chain 한 방으로 추적
- CFG였다면 block 경계 넘어 추적 — 복잡

**④ Inlining 후 cross-method 최적화가 강력**
- Inlining 후 caller + callee가 한 그래프로 합쳐짐
- Sea-of-Nodes는 block 자체가 없음 → 경계 사라짐
- type propagation, dead code, GVN이 cross-method 자유 흐름
- CFG였다면 block 경계 남아 inlining 가치 절반

**⑤ Tier 4는 컴파일 시간 amortized**
```
Tier 4 진입: 10K+ 호출 + profile 안정 → 진짜 hot
→ 한 번 컴파일 → 평생 실행

100ms 더 써서 peak 1% 빠르면?
  그 메서드 10억 회 더 호출
  1% × 10억 = 1000만 사이클 절약 ≫ 100ms 비용
→ 컴파일 시간 신경 안 써도 됨
```

#### 1.7.4 특성 매트릭스 — 어느 IR이 무엇에 강한가

| 특성 | CFG (C1) | Sea-of-Nodes (C2) |
|---|---|---|
| 컴파일 속도 | ★ 빠름 (~ms) | 느림 (~10~100ms) |
| 메모리 사용 | ★ 적음 (수 MB) | 많음 (수십~수백 MB) |
| 구현 복잡도 | ★ 단순 (3K줄) | 복잡 (50K줄) |
| Profile instrumentation | ★ 자연 | 어색 |
| Cross-block 최적화 | 약함 | ★ 자연 |
| GVN + Constant folding | 패스로 | ★ IR 속성 |
| Code motion (LICM 등) | 별도 패스 | ★ Scheduling 하나로 |
| Escape Analysis | 어려움 | ★ 자연 |
| Inlining 후 추가 최적화 | 제약 | ★ 강력 |
| Speculation 기반 최적화 | 어려움 | ★ 가능 |
| SIMD vectorization | 거의 불가 | ★ SuperWord |

→ **C1이 강한 곳에 CFG가 강하고, C2가 강해야 할 곳에 Sea-of-Nodes가 강함**. 정확히 반대 영역에 특화.

#### 1.7.5 Tiered의 본질 — 다른 IR이 양립을 만든다

> **C1/C2가 다른 컴파일러인 이유와 IR이 다른 이유는 같은 동기.**

```
Tiered의 본질:
  "한 컴파일러로는 startup + peak 양립 못 한다"
   ↓
  단계 분리: T3 (빠른 baseline) + T4 (느린 peak)
   ↓
  각 단계의 IR도 분리: T3 = CFG, T4 = Sea-of-Nodes
   ↓
  단계별 최적 도구를 쓰는 게 전체 최적
```

**만약 같은 IR이었다면?**
- 둘 다 CFG → T4 peak 부족 → C2 의미 없음 → Tiered 무력화
- 둘 다 Sea-of-Nodes → T3 컴파일 너무 느림 → warmup 우위 상실 → -server only와 동일

→ **다른 IR이 Tiered 양립의 핵심 자체**. 트레이드오프가 아니라 설계의 본질.

#### 1.7.6 사고 실험 — 만약 바꿨다면?

**"C1이 Sea-of-Nodes를 쓴다면?"**
- 컴파일 시간 ~수 ms → ~수십 ms 폭증
- Tier 3가 ~1500 호출 시점에 못 끝남 → 큐 적체
- 메모리 ↑↑ → 동시 task 제한 → 처리율 ↓
- 결과: Tiered의 warmup 우위 상실

**"C2가 CFG를 쓴다면?"**
- LICM, lazy 등 전용 패스 따로 다 짜야 함
- EA 어려움 → Scalar Replacement 약화
- Inlining 후 cross-block 제약 → inlining 가치 절반 ↓
- SuperWord (SIMD) 불가 → loop 성능 큰 손해
- 결과: peak 성능 ~80% 손해 → C2 의미 없음

→ **둘 중 하나만 바꿔도 시스템 전체 무너짐**. 두 IR의 분리가 의도적 설계.

#### 1.7.7 역사적 맥락

```
1995  Cliff Click 박사 논문 (Rice University)
       "Combining Analyses, Combining Optimizations"
       → Sea-of-Nodes 제안

1999  HotSpot 1.0 — C1 도입 (Client)
       전통 CFG 기반 (1990년대 표준)

2000  HotSpot 1.3 — C2 도입 (Server)
       Cliff Click이 Sun 합류, 박사 논문 구현 → Sea-of-Nodes 채택

2007  JDK 6u20 — Tiered 실험
2014  JDK 8 — Tiered 기본 on
       역할 분담 표준 정착
```

→ **Sea-of-Nodes는 "서버 peak"이 목적인 박사 논문 산물 — C2가 채택한 게 자연.**
→ **CFG는 "client 빠른 시작"에 충분 — C1이 굳이 박사 논문급 구조 가져올 이유 없음.**

#### 1.7.8 한 줄 요약

| 질문 | 한 줄 답 |
|---|---|
| **왜 C1은 CFG?** | 사명이 "수 ms baseline + profile 수집". CFG가 단순·빠름·메모리 적음·instrumentation 쉬움. 보수적 최적화에 충분 |
| **왜 C2는 Sea-of-Nodes?** | 사명이 "peak, 시간 비싸도 좋음". Sea-of-Nodes가 code motion·GVN·EA·inlining 후 최적화에 자연 |
| **두 IR 분리가 우연?** | 아니. **Tiered의 양립(빠른 baseline + 깊은 peak)이 두 IR 분리 위에 성립**. 같은 IR이면 둘 중 하나 무력화 |
| **시니어 한 줄** | "역할이 다르니 IR도 다르다. CFG는 단순·빠름이 본질, Sea-of-Nodes는 자유·공격이 본질. 두 컴파일러가 자기 사명에 맞는 IR을 골랐고, 그게 모여 Tiered의 양립을 만든다" |

---

## 2. 가지 ②: WHAT — C2 Phase 7단계

### 2.1 핵심 질문

> "C2가 bytecode를 받아 native code를 만들기까지 어떤 phase들을 거치나요?"

### 2.2 키워드 1 — Parse → IterGVN

```
1. Parse — bytecode → Sea-of-Nodes
   - 각 bytecode가 노드로
   - data dependency만 표현, basic block 미정
   - Type system 초기화

2. IterGVN (Iterative Global Value Numbering)
   - 같은 값을 계산하는 노드 통합
   - Constant folding fixpoint
   - Type propagation
   - ★ 가장 자주 호출되는 최적화
```

**IterGVN 예시**:
```
초기: a = 3 + 4 ; b = a * 2 ; c = 3 + 4 ; d = b + 1

1차 (constant fold):
  a = 7 ; b = 14 ; c = 7 ; d = 15

2차 (GVN, hash-table에서 같은 값 찾기):
  c == a → c를 a로 통합

최종: a = 7 ; b = 14 ; d = 15 (c는 a로 통합되어 사라짐)
```

`iterative`인 이유: 한 패스의 결과가 다른 최적화 기회 생성 → fixpoint까지 반복.

### 2.3 키워드 2 — Inline+EA → Loop opts → Macro+CCP

```
3. Inlining + Escape Analysis
   - 호출 사이트의 callee를 caller에 펼침 (inlining)
   - 객체가 escape하는지 분석 → Scalar Replacement
   - 자세히: 05-inlining-and-ic, 06-escape-analysis

4. Loop Optimizations
   - LICM (Loop Invariant Code Motion)
   - RCE (Range Check Elimination)
   - Loop Unrolling
   - SuperWord (SIMD vectorization)
   - 자세히: 07-loop-and-vector

5. Macro Expand
   - 고수준 노드(ArrayAlloc, ConstantPoolNode 등)를 lower
   - 예: array allocation을 malloc + 초기화로 풀어 씀

6. CCP (Conditional Constant Propagation)
   - branch 결과 기반 상수성 추론
   - if (x == 0) 안에서는 x = 0이라 알 수 있음
```

### 2.4 키워드 3 — Scheduling + RA → Output

```
7. Scheduling (Global Code Motion, GCM)
   - Sea-of-Nodes 노드들을 basic block에 배치
   - data dependency 만족하면서 최적 위치
   - 가능한 한 늦은 위치 (lazy computation)
   - Cliff Click의 schedule_early / schedule_late 2-pass

8. Register Allocation (Graph Coloring, Chaitin)
   - virtual register들로 interference graph
   - NP-hard → 휴리스틱

9. Output
   - native instruction 생성
   - nmethod, Code Cache (Non-profiled segment)에 저장
```

### 2.5 C2 진입점 코드

위치: `src/hotspot/share/opto/compile.cpp`:

```cpp
Compile::Compile(ciEnv* env, ciMethod* target, ...) {
    parser.parse();                              // 1. Parse
    PhaseIterGVN igvn(...);  igvn.optimize();    // 2. IterGVN
    inline_incrementally();                      // 3. Inlining
    PhaseMacroExpand mex(igvn);                  // 3-4. EA + Macro
    PhaseIdealLoop::optimize(igvn, ...);         // 4. Loop opts
    PhaseCCP ccp(igvn);  ccp.do_transform();     // 6. CCP
    PhaseCFG cfg(...);  cfg.do_global_code_motion(); // 7. Scheduling
    PhaseChaitin allocator(...);                 // 8. RA
    allocator.Register_Allocate();
    output();                                    // 9. Output
}
```

각 `Phase*` 클래스가 한 phase. Pipeline 구조.

### 2.6 Sea-of-Nodes 주요 노드 종류

```cpp
class StartNode      // 메서드 entry
class RegionNode     // basic block boundary
class PhiNode        // SSA phi
class IfNode         // 분기
class ProjNode       // 결과 추출 (multi-output용)
class CallNode       // 메서드 호출
class AddINode       // int 덧셈
class LoadNode/StoreNode  // memory 접근
class MemBarNode     // memory barrier (volatile 등)
class SafePointNode  // safepoint 후보 지점
// ... 수백 종
```

모든 노드는 input edges (data dependency) + output edges. 기본 클래스 `Node`.

---

## 3. 가지 ③: HOW — Register Allocation 차이

### 3.1 핵심 질문

> "C1과 C2의 register allocator가 다른 이유는? 알고리즘 차이가 결과에 어떻게 나타나나요?"

### 3.2 키워드 1 — C1: Linear Scan O(n log n)

```
1. virtual register들의 live interval 계산
2. intervals를 시작 시점 순으로 linear scan
3. 각 시점에 free register pool에서 할당
4. 충돌 시 가장 멀리 쓰일 register를 spill
5. 시간 O(n log n) — 빠름
6. 결과: 좋음, 최적은 아님
```

위치: `src/hotspot/share/c1/c1_LinearScan.cpp`.

### 3.3 키워드 2 — C2: Graph Coloring O(n²~n³) Chaitin

```
1. virtual register들로 interference graph 구성
   - 각 virtual reg가 node
   - 동시 live인 reg pair가 edge
2. Simplification (degree < k 인 node 제거, stack에 push)
3. Spill (degree ≥ k 인 node를 spill 후보)
4. Selection (stack pop하며 색칠)
5. Coalescing (move instruction 제거)
6. graph coloring은 NP-hard → 휴리스틱
7. 시간 O(n²~n³) — 느림
8. 결과: 거의 최적
```

위치: `src/hotspot/share/opto/chaitin.cpp`. Chaitin's algorithm (1982 IBM 논문).

### 3.4 키워드 3 — Spill 차이 (Memory Access)

| | Linear Scan (C1) | Graph Coloring (C2) |
|---|---|---|
| 시간 복잡도 | O(n log n) | O(n²~n³) |
| 결과 품질 | 약간 부족 | 거의 최적 |
| Spill 발생 | 더 자주 | 적음 |
| Memory access | 빈번 → 약간 느림 | 적음 → 빠름 |

→ C2가 더 좋은 RA → register spill 줄임 → memory access 줄임 → 빠른 native code. C1은 컴파일 시간 우선, C2는 결과 품질 우선.

### 3.5 어느 메서드가 C1에서 멈추나

```
C1만 머무는 케이스:
1. 너무 작은 메서드 (~few bytes) — C2가 inline해버리므로 별도 컴파일 무의미
2. C2 컴파일 실패 (NULL pointer, type error 등)
3. -XX:CompileCommand=dontinline 등 옵션 명시 제외
4. C2 큐 적체 — 우선순위 낮으면 영원히 대기
5. Profile 불안정 — C2 컴파일 안전 못 보장
6. 매우 큰 메서드 — C2가 거부 (IR 노드 수 한계 초과)
```

진단:
- `-XX:+PrintCompilation` 같은 메서드의 Tier 3만 보이고 Tier 4 없음.
- JFR `jdk.Compilation` 의 `succeeded` 필드.

---

## 4. 가지 ④: 운영 — 시니어 진단

### 4.1 핵심 질문

> "어느 메서드가 어느 컴파일러까지 갔는지, C2 결과 native code가 정상인지 어떻게 확인하나요?"

### 4.2 키워드 1 — `-XX:+PrintCompilation` tier 정보

```
142    3 %   4       MyApp::process @ 12 (123 bytes)   ← Tier 4, OSR
150    4       4     MyApp::process (123 bytes)        ← Tier 4 일반
```

- Tier 3 = C1, Tier 4 = C2.
- `%` = OSR.
- `made not entrant` = 옛 nmethod 폐기 (C1 → C2 승격 또는 deopt).

### 4.3 키워드 2 — C1 stuck / C2 timeout 진단

```bash
# C2 컴파일 시간 매우 김 (특정 메서드만)
$ jcmd <pid> JFR.start name=jit duration=300s settings=profile
$ jfr print --events jdk.Compilation jit.jfr | sort -k 4 -n -r | head
# 시간 ↑ 메서드 식별
```

원인:
- 거대한 hot method + 깊은 inlining → IR 노드 수 폭발.
- IterGVN이 fixpoint 도달 못 함 (극단 케이스).

조치:
- 코드 audit (큰 메서드 분할).
- `-XX:CompileCommand=exclude` 로 그 메서드 컴파일 제외 (인터프리터 유지).
- `-XX:TieredStopAtLevel=3` 으로 C1까지만.
- `-XX:MaxInlineLevel=8` (기본 9) — inline 깊이 제한.

### 4.4 키워드 3 — JITWatch + PrintAssembly

**JITWatch**:
```bash
java -XX:+UnlockDiagnosticVMOptions \
     -XX:+TraceClassLoading \
     -XX:+LogCompilation \
     -jar app.jar
# hotspot_pid<n>.log 생성 → JITWatch에서 열기
```

기능: 메서드별 컴파일 결과, inlining tree, deopt 위치 시각화.

**PrintAssembly** (특정 메서드 native 확인):
```bash
# hsdis-amd64.so 플러그인 필요
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintAssembly \
     -XX:CompileCommand=print,MyApp::hotMethod \
     -jar app.jar
```

C2 최적화 결과를 직접 확인 (SIMD instruction, inlined call 등).

**PrintIdealGraph** (C2 IR 시각화):
```bash
java -XX:+UnlockDiagnosticVMOptions \
     -XX:+PrintIdealGraphLevel=4 \
     -XX:PrintIdealGraphFile=/tmp/ig.xml \
     -jar app.jar
```

XML을 **IdealGraphVisualizer** (Oracle Labs)로 시각화.

### 4.5 운영 시나리오 매트릭스

| 증상 | 진단 | 가능 원인 |
|---|---|---|
| 특정 메서드가 영원히 Tier 3 | PrintCompilation 의 Tier 4 부재 | 너무 큼, deopt 반복, C2 실패 |
| C2 컴파일 시간 매우 김 | JFR `jdk.Compilation` duration | 거대 메서드 + 깊은 inlining |
| C2 nmethod 비정상 (deopt) | JFR `jdk.Deoptimization` reason | speculation 깨짐 |
| async-profiler 비정상 | JITWatch로 cross-check | C2 최적화로 inlined 코드 |
| C2 메모리 폭증 | `jcmd VM.native_memory`의 Compiler 영역 | 큰 compile task |

### 4.6 Killer 시나리오 — 특정 메서드만 영원히 Tier 3

```
환경: Spring 거대 컨트롤러 메서드
증상: 그 메서드가 PrintCompilation 로그에 Tier 3만 보임. Tier 4 없음.

진단:
1. 메서드 크기 확인 — javap -v 의 Code attribute size
   (15KB 이상이면 C2 거부 가능성)
2. -XX:+PrintInlining 으로 inlining 시도 확인
   "too big" 메시지 다수
3. JFR jdk.Compilation 의 success 확인
   C2 시도했다가 timeout 또는 실패?

원인: 큰 메서드 + 깊은 호출 그래프 → C2가 inlining 후 IR 노드 수 한계 초과

조치:
- 메서드 분할 (refactor)
- -XX:MaxInlineLevel, -XX:MaxInlineSize 튜닝 (신중)
- -XX:CompileCommand=inline,MyClass::method 로 강제 inlining
- 또는 -XX:CompileCommand=exclude 로 그 메서드 컴파일 제외 (인터프리터)
```

---

## 5. 면접 답변 워크플로우

### 5.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "C1과 C2의 차이?" | ① WHY | ② C2 phase |
| "Sea-of-Nodes가 뭔가요?" | ① WHY (자유 노드 이동) | ② phase scheduling |
| "C2 phase 순서?" | ② WHAT | ④ 운영 측정 |
| "IterGVN이 iterative인 이유?" | ② WHAT (IterGVN) | constant fold cascade |
| "C1/C2 RA 차이?" | ③ HOW | spill 비용 |
| "C2 컴파일 느림 진단" | ④ 운영 | 메서드 분할 조치 |
| "어느 메서드가 C1에서 멈춤?" | ③ HOW (어디서 멈춤) | ④ 진단 |

### 5.2 답변 템플릿

> 루트 → 가지 키워드 3개 → 인접

예: "C1과 C2의 IR이 본질적으로 다른 이유와 그 차이가 왜 중요한가요?"

> "C1은 HIR/LIR을 사용하는 CFG 기반, C2는 Sea-of-Nodes 기반입니다. (← 루트 IR 차이)
> CFG는 basic block 명시 — 각 instruction이 한 block에 묶임. 분석/변환이 단순해 컴파일 ~수 ms. 단, cross-block 최적화 제약.
> Sea-of-Nodes는 basic block을 명시하지 않고 노드 간 dependency edge만 표현. 노드의 실제 위치는 마지막 scheduling phase에서 결정. 결과: 노드를 자유롭게 옮기는 최적화가 자연스러움 (code motion, GVN, dead code).
> 트레이드오프: C1 ~수 ms vs C2 ~수십~수백 ms. C1은 ~50% 성능, C2는 peak. 그래서 Tiered로 둘 다 사용 — C1으로 빠르게 baseline + C2로 깊게 peak."

---

## 6. 꼬리질문 트리 (가지별)

### Q1 [가지 ①]. C1과 C2의 IR이 어떻게 다르고 그 차이가 왜 중요한가요?

> - C1: HIR + LIR, CFG 기반. basic block 명시. 각 instruction이 한 block에 속함. SSA.
> - C2: Sea-of-Nodes. basic block 미명시. 노드 간 dependency edge만. 노드 위치는 scheduling phase에서 결정.
> 차이의 의미: CFG는 단순 — 패스가 block 단위. 빠르지만 cross-block 최적화 제약. Sea-of-Nodes는 복잡 — 그러나 노드 자유 이동으로 공격적 최적화 가능. 결과: C1 ~수 ms 컴파일, C2 ~수십~수백 ms — 공격적 최적화의 비용.

### Q2 [가지 ②]. C2의 phase 순서를 알려주세요.

> 운영자 관점 7단계:
> 1. **Parse** — bytecode → Sea-of-Nodes.
> 2. **IterGVN** — 같은 값 통합 + constant folding fixpoint.
> 3. **Inlining + Escape Analysis**.
> 4. **Loop opts** — Unrolling, RCE, LICM, SuperWord.
> 5. **Macro Expand + CCP** — 고수준 노드 풀어 씀, 조건부 상수 전파.
> 6. **Scheduling (GCM) + Register Allocation (Graph Coloring)**.
> 7. **Output** — native instruction, nmethod.

**🪝 Q2-1: IterGVN이 "iterative"인 이유는?**
> 한 패스의 결과가 다른 최적화 기회 생성. 예: constant folding으로 `if (3 == 3)`가 true가 되면 else branch가 dead code → 제거 → 안의 다른 계산도 dead → 추가 제거. 이런 cascade를 잡기 위해 fixpoint (변화 없음)까지 반복.

### Q3 [가지 ③]. C1과 C2의 register allocator가 다른 이유는?

> - C1: **Linear Scan** — O(n log n), 빠름, 결과 약간 부족 (spill 더 자주).
> - C2: **Graph Coloring (Chaitin)** — O(n²~n³), 느림, 거의 최적.
> C1은 컴파일 시간 우선 (Tier 3, ~수 ms). C2는 결과 품질 우선 (Tier 4, peak).
> Trade-off: C1 nmethod는 spill이 더 많아 memory access 빈번 → 약간 느림. C2는 spill 적어 register에서 거의 다 처리.

### Q4 [가지 ②]. Sea-of-Nodes는 어떤 노드들로 구성되나요?

> 주요 노드 (수백 개 중 핵심):
> - **StartNode**: 메서드 entry.
> - **RegionNode**: control flow merge point (basic block boundary).
> - **PhiNode**: SSA phi.
> - **IfNode**: 분기.
> - **CallNode**: 메서드 호출.
> - **AddINode / SubINode / ...**: 산술.
> - **LoadNode / StoreNode**: memory 접근.
> - **MemBarNode**: memory barrier (volatile).
> - **SafePointNode**: safepoint 후보 지점.
> 모든 노드는 input edges (data dependency) + output edges. 기본 클래스 `Node`.

### Q5 [가지 ③]. 어떤 메서드가 C2에 안 가고 C1에서 멈추나요?

> 1. 너무 작은 메서드 — C2 inline 대상.
> 2. 너무 큰 메서드 — C2 IR 노드 한계 초과로 거부.
> 3. 컴파일 실패 (NULL ptr, type error).
> 4. `-XX:CompileCommand=exclude/dontcompile` 명시 제외.
> 5. 반복 deopt — C2가 안정 못 보장.
> 6. C2 큐 적체 + 우선순위 낮음.
> 진단: `-XX:+PrintCompilation` 의 같은 메서드에 Tier 4 부재.

### Q6 [가지 ④]. C2의 결과 native code를 직접 확인하려면?

> 1. **PrintAssembly**:
>    ```
>    -XX:+UnlockDiagnosticVMOptions -XX:+PrintAssembly
>    -XX:CompileCommand=print,MyApp::hotMethod
>    ```
>    hsdis 플러그인 필요. SIMD instruction (vpaddd 등), inlined call 직접 확인.
> 2. **JITWatch**: `-XX:+LogCompilation` 로 `hotspot_pid<n>.log` 생성 → JITWatch에서 메서드별 inlining tree, deopt 위치 시각화.
> 3. **PrintIdealGraph**: C2 IR을 XML로 dump → IdealGraphVisualizer (Oracle Labs)에서 그래프 시각화.

### Q7 (Killer) [가지 ④]. Spring Boot의 큰 컨트롤러 메서드 한 개가 C2 컴파일에 1초가 걸려 warmup이 길어집니다. 어떻게 진단하시겠어요?

> 단계적:
> 1. **메서드 식별**: `-XX:+PrintCompilation` 로그에서 시간 ↑ 메서드.
> 2. **메서드 분석**:
>    - 크기 (`javap -v` 의 Code length).
>    - 호출 사이트 수 (큰 메서드 = 큰 그래프).
>    - 컨트롤러는 보통 여러 service 호출 — inlining 후 그래프 폭발.
> 3. **Inlining 깊이**: `-XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining` — 그 메서드에서 호출되는 모든 메서드의 inline 결정.
> 4. **조치**:
>    - **단기**: `-XX:MaxInlineLevel=8` (기본 9) — inline 깊이 제한.
>    - **장기**: 메서드 분할 (controller → service → repository로 자연 분리).
>    - **최후**: `-XX:CompileCommand=exclude` 로 그 메서드 컴파일 제외 (인터프리터 영원, trade-off).
> 5. **시각화**: JITWatch로 그 메서드의 inlining tree. 거대한 tree면 분할.

---

## 7. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 이내로 그릴 수 있다 (루트 + 4가지 + 키워드 3개)
- [ ] 가지 ① WHY: CFG vs Sea-of-Nodes의 본질적 차이 (노드 위치 결정 시점) 설명한다
- [ ] 가지 ① 용어: IR / basic block / CFG / HIR / LIR / SSA 각자 한 줄 정의 말한다
- [ ] 가지 ① 용어: cross-block 최적화 제약이 왜 생기는지, code motion이 왜 CFG에서 어렵고 Sea-of-Nodes에서 자연스러운지 설명한다
- [ ] 가지 ① 용어: SSA의 Phi 노드가 무엇이고 왜 필요한지 말한다
- [ ] 가지 ① 설계: 왜 C1은 CFG, C2는 Sea-of-Nodes인가 — 두 컴파일러의 사명 차이로 설명한다 (각 5가지 이유)
- [ ] 가지 ① 설계: "둘이 같은 IR이면 Tiered 무너진다" 사고 실험 말한다
- [ ] 가지 ② WHAT: C2 7단계 phase 순서 외운다 (Parse → IterGVN → Inline+EA → Loop → Macro+CCP → Sched+RA → Output)
- [ ] 가지 ② WHAT: IterGVN이 fixpoint까지 반복하는 이유 (cascade) 설명한다
- [ ] 가지 ② WHAT: Sea-of-Nodes 주요 노드 종류 5개 이상 말한다
- [ ] 가지 ③ HOW: Linear Scan vs Graph Coloring 시간 복잡도와 spill 빈도 비교한다
- [ ] 가지 ③ HOW: 메서드가 C1에서 멈추는 6가지 케이스 말한다
- [ ] 가지 ④ 운영: PrintCompilation tier 정보 해석한다
- [ ] 가지 ④ 운영: JITWatch + PrintAssembly + PrintIdealGraph 세 도구의 용도 구분한다
- [ ] 가지 ④ 운영: 거대 메서드 C2 컴파일 느림 진단 절차 5단계 말한다
- [ ] 6장 꼬리질문 7개에 막힘없이 답한다

---

## 다음 단계

- → [05. Inlining and IC](./05-inlining-and-ic.md): C2의 가장 강력한 최적화 — Inlining + Inline Cache
- → [06. Escape Analysis](./06-escape-analysis.md): Scalar Replacement
- → [07. Loop and Vector](./07-loop-and-vector.md): Loop opts, SIMD
- ← [03. Tiered Compilation](./03-tiered-compilation.md): 어느 메서드가 어디 가는지
- → [Chapter 07. HotSpot Internals](../07-hotspot-internals/): C2 phase 풀버전 코드 투어

## 참고

- **Cliff Click — "Combining Analyses, Combining Optimizations" (1995)**: 박사 논문
- **HotSpot src `c1_Compiler.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/c1/c1_Compiler.cpp
- **HotSpot src `compile.cpp` (C2)**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/opto/compile.cpp
- **HotSpot src `node.hpp` (Sea-of-Nodes)**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/opto/node.hpp
- **HotSpot src `chaitin.cpp` (Graph Coloring RA)**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/opto/chaitin.cpp
- **JITWatch**: https://github.com/AdoptOpenJDK/jitwatch
- **IdealGraphVisualizer**: Oracle Labs 도구
- **Aleksey Shipilëv — Compilation Internals**: https://shipilev.net/jvm/anatomy-quarks/
