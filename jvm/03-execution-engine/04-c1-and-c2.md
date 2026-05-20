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
