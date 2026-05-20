# 07. HotSpot Internals — src/hotspot 풀 투어

> JVM의 모든 기능 (Class Loading, Interpreter, JIT, GC, Threading, Safepoint)이 `src/hotspot` 한 디렉토리에 있다. ~1.5M 줄 C++.
> 시니어가 알아야 할 것: OpenJDK bug report에 `src/hotspot/share/opto/escape.cpp:1234`라고 나오면 어느 컴포넌트인지 즉시 식별할 수 있어야 한다.
> 디렉토리 매핑 + C2 phase 11단계 + Safepoint mprotect 메커니즘 — 이 세 가지가 시니어의 디버깅 무기다.

---

## 이 문서의 사용법

이 문서는 **면접용 마인드맵**을 따라 선형으로 펼친 구조다. 학습 순서 = 면접 답변 순서 = 백지에 그리는 순서.

1. **0장 마인드맵을 먼저 외운다** — 루트 한 문장 + 4가지 가지 + 각 가지의 키워드 3개.
2. **1~4장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 정확히 대응.
3. **5장 면접 워크플로우로 검증** — 질문을 보면 어느 가지로 가야 하는지 매핑.
4. **6장 꼬리질문으로 깊이 점검**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"HotSpot의 소스는 share/(플랫폼 독립) + cpu/(아키텍처별) + os/(OS별) 3분할이며, share/ 안에 11개 핵심 디렉토리가 JVM의 모든 기능을 담는다."**

이 한 문장에서 모든 답변이 출발한다. 어떤 질문이 와도 이 문장부터 말하고 적절한 가지로 분기.

### 4개 가지 — 순서를 외운다

```
                  [ROOT: HotSpot = share + cpu + os]
                                 │
        ┌──────────────┬─────────┴─────────┬──────────────┐
        │              │                   │              │
       ① 3분할       ② share/ 11개       ③ C2 phase    ④ Safepoint
       (구조)        (디렉토리)           (11단계)      (mprotect)
        │              │                   │              │
     ┌──┼──┐        ┌──┼──┐            ┌───┼───┐       ┌──┼──┐
   share cpu os    classfile gc       Parse  IterGVN  polling  signal
   (90%) (5%)(5%)  interpreter        Inline  EA       page    handler
                   opto runtime      LoopOpt Output    PROT_   SEGV
                   code memory       Sched  RA         NONE    →safepoint
```

### 가지별 핵심 키워드 (각 가지 3개씩만)

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① 3분할** | share/ (90%) | cpu/ (CPU별 emit) | os/ (OS API wrap) |
| **② share/ 11개** | classfile/interpreter/c1/opto | gc/runtime/memory | code/oops/prims/compiler |
| **③ C2 phase** | Parse → IterGVN → Inline | EA → LoopOpt → CCP | Sched → RA → Output |
| **④ Safepoint** | polling page mprotect | JIT inline poll | SEGV → signal handler |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 질문에 맞는 가지 1개 선택 → 그 가지의 키워드 3개 순서대로 설명 → 듣는 사람의 관심에 따라 인접 가지로 확장

---

## 1. 가지 ①: 3분할 — share/cpu/os

### 1.1 핵심 질문

> "HotSpot 소스가 왜 share/cpu/os로 나뉘어 있나요?"

### 1.2 키워드 1 — share/ (Platform-independent, ~90%)

OS와 CPU에 무관한 로직. C++ 코드의 대부분.

- Bytecode interpretation 로직 (template만, 실제 명령은 cpu/)
- JIT의 IR과 최적화 알고리즘 (실제 코드 emit은 cpu/)
- GC 알고리즘 (G1, ZGC 등의 핵심 로직)
- ClassFile parsing, Heap management 등

**핵심 원칙**: "알고리즘은 share/에, 플랫폼 의존은 cpu/와 os/에".

### 1.3 키워드 2 — cpu/{x86, aarch64, riscv, ...}/

CPU별 구현. 새 CPU 지원을 추가할 때 작성해야 하는 부분.

| 무엇 | 왜 CPU별인가 |
|---|---|
| Template Interpreter의 opcode asm | bytecode 명령 하나하나를 native instruction으로 변환 |
| C1/C2의 code emit | IR을 실제 x86/ARM 명령으로 출력 |
| Memory barrier instruction | x86 `mfence`, ARM `dmb` 등 |
| Adapter (calling convention 변환) | C function ABI vs JVM 내부 ABI |
| Safepoint polling 명령 | x86 `test`, ARM `ldr` 등 |

**예시**: `cpu/x86/templateTable_x86.cpp` — bytecode `iadd`를 x86 `add eax, ebx`로 변환하는 코드.

### 1.4 키워드 3 — os/{linux, bsd, windows, ...}/

OS API wrapping. 같은 기능을 OS마다 다르게 부르는 부분.

| 무엇 | OS별 차이 |
|---|---|
| Thread 생성 | `pthread_create` vs Win32 `CreateThread` |
| Memory mapping | `mmap`/`mprotect` vs Win32 `VirtualAlloc`/`VirtualProtect` |
| Signal handler | POSIX `sigaction` vs Win32 SEH |
| I/O | `read`/`write` vs `ReadFile`/`WriteFile` |
| **cgroup awareness** | Linux container limit 인식 (Windows 없음) |

**예시**: `os/linux/os_linux.cpp` — `JVM_handle_linux_signal()`에서 SEGV를 받아 safepoint 또는 NPE로 변환.

### 1.5 디렉토리 비율의 의미

```
src/hotspot/
├── share/   ~1.4M lines  (90% — JVM의 본질)
├── cpu/     ~80K lines   (5% — 각 CPU 약 16K)
└── os/      ~70K lines   (5% — 각 OS 약 15K)
```

→ JVM의 진짜 복잡도는 share/에 있다. cpu/, os/는 "같은 알고리즘을 다른 명령어/API로 표현"하는 얇은 layer.

---

## 2. 가지 ②: share/ 11개 핵심 디렉토리

### 2.1 핵심 질문

> "share/ 안의 디렉토리 11개와 각자의 책임은?"

### 2.2 키워드 1 — Class lifecycle + Execution Engine

| 디렉토리 | 책임 | 핵심 파일 |
|---|---|---|
| `classfile/` | ClassFile parsing, ClassLoader, Symbol table | `classFileParser.cpp` ([Chapter 01-01](../01-class-lifecycle/01-classfile-format.md)) |
| `interpreter/` | Template Interpreter | `templateTable.cpp` ([Chapter 03-02](../03-execution-engine/02-interpreter.md)) |
| `c1/` | C1 compiler (HIR/LIR) | `c1_Compiler.cpp` ([Chapter 03-04](../03-execution-engine/04-c1-and-c2.md)) |
| `opto/` | C2 compiler (Sea-of-Nodes, ~50K 줄) | `compile.cpp` ([Chapter 03-04/06/07](../03-execution-engine/)) |
| `code/` | Code Cache, nmethod, Inline Cache | `codeCache.cpp` ([Chapter 02-04](../02-runtime-data-areas/04-code-cache.md)) |

### 2.3 키워드 2 — Memory + GC + Runtime

| 디렉토리 | 책임 | 핵심 파일 |
|---|---|---|
| `gc/shared/`, `gc/{serial,parallel,g1,z,shenandoah}/` | GC 알고리즘 | [Chapter 04](../04-garbage-collection/) |
| `runtime/` | Thread, frame, safepoint, deopt, lock | `safepoint.cpp` ([Chapter 04/05](../05-jvm-tuning/)) |
| `memory/` | Heap layout, Metaspace, Universe | `metaspace.cpp` ([Chapter 02-02](../02-runtime-data-areas/02-metaspace-and-class-space.md)) |
| `oops/` | InstanceKlass, Method, oop (Ordinary Object Pointer) | `klass.hpp` ([Chapter 02-02](../02-runtime-data-areas/02-metaspace-and-class-space.md)) |

### 2.4 키워드 3 — Interop + Compiler infra

| 디렉토리 | 책임 | 핵심 파일 |
|---|---|---|
| `prims/` | JNI, Unsafe, JVMTI | `unsafe.cpp` ([Chapter 02-05](../02-runtime-data-areas/05-direct-memory.md)) |
| `compiler/` | Compile Broker, JVMCI 인터페이스 | `compileBroker.cpp` ([Chapter 03-03](../03-execution-engine/03-tiered-compilation.md)) |
| `jvmci/` | 외부 JIT plugin 인터페이스 (Graal) | [Chapter 08](../08-graalvm/) |

### 2.5 디렉토리 ↔ 책 챕터 매핑

```
chapter 01 (Class lifecycle)  →  classfile/
chapter 02 (Memory regions)   →  memory/, oops/, code/, prims/
chapter 03 (Execution engine) →  interpreter/, c1/, opto/, compiler/
chapter 04 (GC)               →  gc/shared/, gc/{serial,parallel,g1,z,...}/
chapter 05 (Tuning)           →  runtime/ (safepoint, deopt, signal)
chapter 08 (GraalVM)          →  jvmci/
```

**시니어 활용**: bug report에 `src/hotspot/share/opto/escape.cpp` 나오면 → C2의 Escape Analysis ([Chapter 03-06](../03-execution-engine/06-c2-optimizations.md)) 코드. 즉시 어느 책 챕터로 갈지 안다.

---

## 3. 가지 ③: C2 phase 11단계

### 3.1 핵심 질문

> "C2 컴파일러는 어떤 단계로 bytecode를 native code로 변환하나요?"

### 3.2 위치

`src/hotspot/share/opto/compile.cpp`의 `Compile::Optimize()` 함수.

### 3.3 11단계 흐름

```
[bytecode] 
   ↓ Phase 1: Parse
[초기 Sea-of-Nodes 그래프]
   ↓ Phase 2: IterGVN (iterative Global Value Numbering)
[공통 부분 식 제거된 그래프]
   ↓ Phase 3: Inlining (incremental)
[메서드 호출이 펼쳐진 그래프]
   ↓ Phase 4: Macro Eliminate (EA 결과 적용)
   ↓ Phase 5: Escape Analysis
[stack allocation/lock elision 적용]
   ↓ Phase 6: Loop optimizations
[unrolling/RCE/LICM/SuperWord 적용]
   ↓ Phase 7: CCP (Conditional Constant Propagation)
[상수 전파된 그래프]
   ↓ Phase 8: Macro Expand 나머지
   ↓ Phase 9: Scheduling (Global Code Motion)
[basic block 배치 결정]
   ↓ Phase 10: Register Allocation (Graph Coloring, Chaitin)
[레지스터 할당 완료]
   ↓ Phase 11: Output (machine code emit)
[native code]
```

### 3.4 키워드 1 — Parse → IterGVN → Inline (graph 구축)

- **Parse**: bytecode를 Sea-of-Nodes (SoN) IR로 변환. 각 명령이 Node 객체로.
- **IterGVN**: 동일한 계산을 찾아 하나의 노드로 통합 (`x+y` 두 번 나오면 한 번만 계산).
- **Inlining**: 호출이 작은 메서드면 caller에 펼침. 후속 최적화의 가능성을 폭발적으로 키움.

### 3.5 키워드 2 — EA → LoopOpt → CCP (high-level 최적화)

- **Escape Analysis**: 객체가 메서드 밖으로 escape 안 하면 stack/inline 할당 가능. lock도 제거.
- **Loop optimizations**:
  - Loop unrolling — 작은 loop를 펼침
  - Range Check Elimination — `arr[i]` bounds check 제거
  - Loop Invariant Code Motion — loop 밖으로 이동 가능한 계산 제거
  - SuperWord — vectorization (SIMD 명령 사용)
- **CCP**: 조건문의 결과가 항상 상수면 dead branch 제거.

### 3.6 키워드 3 — Schedule → RA → Output (low-level)

- **Scheduling**: SoN 그래프를 basic block 시퀀스로 펼침. CPU 파이프라인 친화적 순서로.
- **Register Allocation**: Graph coloring (Chaitin algorithm)으로 가상 register를 물리 register에 매핑. 부족하면 stack spill.
- **Output**: 실제 native instruction byte 출력. `cpu/x86/` 또는 `cpu/aarch64/`의 코드가 호출됨.

### 3.7 풀버전 코드 위치

```cpp
// src/hotspot/share/opto/compile.cpp
void Compile::Optimize() {
    PhaseIterGVN igvn(initial_gvn());
    igvn.optimize();                              // Phase 2

    inline_incrementally();                       // Phase 3
    PhaseMacroExpand mex(igvn);
    mex.eliminate_macro_nodes();                  // Phase 4

    if (do_escape_analysis()) {                   // Phase 5
        ConnectionGraph::do_analysis(this, &igvn);
    }

    PhaseIdealLoop::optimize(igvn, ...);          // Phase 6

    PhaseCCP ccp(&igvn);                          // Phase 7
    ccp.do_transform();

    mex.expand_macro_nodes();                     // Phase 8

    PhaseCFG cfg(...);                            // Phase 9
    cfg.do_global_code_motion();

    PhaseChaitin allocator(...);                  // Phase 10
    allocator.Register_Allocate();

    output();                                     // Phase 11
}
```

→ 각 phase의 풀버전 설명은 [Chapter 03-04 C1 and C2](../03-execution-engine/04-c1-and-c2.md) 및 [Chapter 03-06 C2 optimizations](../03-execution-engine/06-c2-optimizations.md) 참조.

### 3.8 Sea-of-Nodes 노드 종류 (요약)

`src/hotspot/share/opto/node.hpp` 외.

- **Control**: StartNode, RegionNode, IfNode, ProjNode, JumpNode, ReturnNode
- **Data**: AddINode/AddLNode (산술), AndINode/OrINode (bitwise), CmpINode/CmpPNode (compare)
- **Memory**: LoadNode, StoreNode, MemBarNode
- **Call**: CallJavaNode, CallStaticJavaNode, CallDynamicJavaNode, CallRuntimeNode, CallLeafNode
- **SSA**: PhiNode, LoopNode
- **Safepoint/Alloc**: SafePointNode, AllocateNode, LockNode/UnlockNode

각 Node는 `_in[]` (input edges) + `_out[]` (output edges)로 연결 — 그래프 구조.

---

## 4. 가지 ④: Safepoint — mprotect + signal handler

### 4.1 핵심 질문

> "JIT 컴파일된 native code를 어떻게 안전하게 정지시켜 GC를 하나요?"

### 4.2 키워드 1 — Polling page (mprotect 트릭)

```
[정상 상태]                  [Safepoint 요청 시]
━━━━━━━━━                    ━━━━━━━━━━━━━━━

Polling page                 Polling page
PROT_READ                    PROT_NONE  ← JVM이 mprotect로 바꿈

test rax, [polling_page]     test rax, [polling_page]
    ↓                            ↓
정상 read                    SEGV (signal)
    ↓                            ↓
계속 실행                    Signal handler
                             → safepoint 진입
```

**핵심 트릭**: 메모리 page 하나를 두고, 거기를 읽기 권한 토글로 켜고 끄는 것만으로 모든 JIT 코드를 정지/재개시킬 수 있음.

위치: `src/hotspot/share/runtime/safepoint.cpp`.

```cpp
void SafepointSynchronize::begin() {
    Universe::heap()->arm_polling_page();   // mprotect(PROT_NONE)
    for (JavaThread* t : threads) {
        if (t->is_in_running_state()) {
            // 아직 진행 중 — wait
        }
    }
    // 모든 thread가 safepoint 도달 → GC 등 진행 OK
}
```

### 4.3 키워드 2 — JIT inline polling

JIT 컴파일러가 native code의 특정 지점에 polling 명령을 자동 삽입:

- 매 method entry
- 매 method exit (return)
- 매 loop back-edge

```
test rax, [polling_page]   ; polling page read
                            ; 정상 시: read 성공, cycle 1개
                            ; safepoint 요청 시: SEGV
```

**비용**: 정상 상태에서는 단순 read 1번 (~1 cycle). 거의 0 overhead.

**효과**: JIT 코드 어디서나 safepoint까지 도달 시간이 짧음 (loop 안이라도 back-edge마다 polling).

### 4.4 키워드 3 — Signal handler (SEGV → safepoint)

위치: `src/hotspot/os/linux/os_linux.cpp`.

```cpp
extern "C" int JVM_handle_linux_signal(int sig, siginfo_t* info, void* ucVoid, int abort_if_unrecognized) {
    if (sig == SIGSEGV) {
        if (info->si_addr == polling_page_base) {
            // ★ 정상 safepoint poll — thread 정지
            current_thread->block_for_safepoint();
            return true;
        }
        // 진짜 SEGV — JVM crash
    }
    return false;
}
```

→ "예외(SEGV)를 통신 채널로 사용". 정상 polling 호출 비용 0, 안전한 stop 시점 보장.

### 4.5 Safepoint의 다른 용도

같은 메커니즘이 GC 외에도:
- **Deoptimization** — JIT 가정 깨지면 interpreter로 fallback
- **Class redefinition** — JVMTI agent의 hot swap
- **Lock biasing revoke** (옛날) — synchronized 최적화
- **Thread dump** — jstack이 모든 스레드를 stop하고 dump

**연결**: [Chapter 03-08 Deoptimization](../03-execution-engine/08-deoptimization.md), [Chapter 04 GC](../04-garbage-collection/).

---

## 5. 보조: JVMCI + OpenJDK 소스 탐색

### 5.1 JVMCI (외부 JIT 인터페이스)

위치: `src/hotspot/share/jvmci/`.

- JEP 243 (JDK 9+).
- HotSpot이 외부 JIT compiler를 plugin으로 받음.
- **Graal**이 이걸 통해 동작 → C2 대체 가능.
- 활성화: `-XX:+UnlockExperimentalVMOptions -XX:+UseJVMCICompiler`.
- 풀버전: [Chapter 08 GraalVM](../08-graalvm/).

### 5.2 OpenJDK 소스 탐색 방법

```bash
git clone https://github.com/openjdk/jdk.git
cd jdk

# JEP 444 (Virtual Threads) 관련 commit
git log --all --grep="JEP 444" --oneline

# 특정 파일 history
git log --follow src/hotspot/share/runtime/continuation.cpp
```

### 5.3 Bug report 이해

OpenJDK Bug Tracker: https://bugs.openjdk.org/

각 bug에 source file path + line number 참조. 본 챕터의 매핑으로 즉시 어느 컴포넌트인지 식별 → 책 챕터로 점프 가능.

---

## 6. 면접 답변 워크플로우

### 6.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "HotSpot 소스 구조는?" | ① 3분할 | ② share/ 11개 |
| "C2의 phase 순서는?" | ③ C2 phase | ② opto/ 위치 |
| "Sea-of-Nodes란?" | ③ C2 phase | [Chapter 03-04] |
| "Safepoint는 어떻게 동작?" | ④ Safepoint | mprotect + signal |
| "GC 코드는 어디 있나요?" | ② share/ | gc/{g1,z,...} |
| "Class loading 코드는?" | ② share/ | classfile/ |
| "외부 JIT(Graal) 어떻게 연결?" | ⑤ JVMCI | [Chapter 08] |
| "Bug report source 추적?" | ⑤ OpenJDK 탐색 | ② 매핑 |
| "새 CPU 지원 추가 시 뭘 작성?" | ① 3분할 (cpu/) | TemplateTable, code emit |

### 6.2 답변 템플릿

> **루트 문장 한 줄 → 해당 가지 키워드 3개 순서대로 → 듣는 사람 표정 보고 인접 가지로**

예: "C2의 phase 순서는?"

> "HotSpot 소스의 opto/ 디렉토리에 C2가 있고, 컴파일은 Compile::Optimize() 함수에서 11단계로 진행됩니다.
> 크게 3그룹으로 나눠 외웁니다.
> 첫째, **그래프 구축** — Parse(bytecode → Sea-of-Nodes), IterGVN(중복 제거), Inlining(작은 메서드 펼침).
> 둘째, **high-level 최적화** — Escape Analysis(stack 할당 가능 여부), Loop optimizations(unrolling, RCE, LICM, SuperWord), CCP(상수 전파).
> 셋째, **low-level** — Scheduling(basic block 순서), Register Allocation(Chaitin graph coloring), Output(native code emit).
> 핵심은 SoN IR이 control과 data를 한 그래프로 통합해서 phase 사이 정보 공유가 효율적이라는 점입니다."

→ 면접관이 "EA 자세히"면 [Chapter 03-06]로, "Inline 기준?"이면 inlining heuristic으로.

---

## 7. 꼬리질문 트리 (가지별)

### Q1 [가지 ①]. HotSpot 소스가 share/cpu/os로 나뉜 이유는?

> "알고리즘은 share/, 플랫폼 의존은 cpu/와 os/"라는 분리 원칙. JIT 알고리즘, GC, ClassFile parsing 같은 본질 로직은 90%가 share/에. cpu/는 instruction emit과 calling convention. os/는 thread/memory/signal API wrap. 새 CPU 지원 시 cpu/만, 새 OS 지원 시 os/만 추가.

### Q2 [가지 ②]. C2의 코드는 share/의 어느 디렉토리에 있나요?

> `src/hotspot/share/opto/`. 약 50K 줄. 핵심 파일은 `compile.cpp` (Compile::Optimize), `node.hpp` (Sea-of-Nodes 노드 정의), `escape.cpp` (EA), `loopopts.cpp` (loop 최적화), `chaitin.cpp` (Register Allocation).

**🪝 Q2-1: 왜 이름이 opto인가요?**
> "Optimizing compiler". C1은 빠른 컴파일이 목표, C2는 강한 최적화가 목표 → opto/.

### Q3 [가지 ③]. C2 컴파일의 phase 순서는?

> 11단계, Compile::Optimize()에서: Parse → IterGVN → Inlining → Macro Eliminate → EA → Loop opts → CCP → Macro Expand → Scheduling → Register Allocation → Output. 3그룹으로 외움 (graph 구축 / high-level / low-level).

**🪝 Q3-1: Inlining이 왜 그렇게 빠른 시점에 있나요?**
> Inlining은 후속 최적화의 가능성을 폭발적으로 키움. caller-callee 경계가 사라지면 EA, CCP, Loop opt가 훨씬 많은 케이스를 잡아냄. 그래서 IterGVN 직후에 incremental하게 적용.

### Q4 [가지 ③]. Sea-of-Nodes IR의 장점은?

> Control flow와 data flow를 한 그래프로 통합. 전통적인 CFG + DAG 분리 방식보다:
> 1. Code motion이 자유로움 — 노드를 어느 basic block에 둘지를 Scheduling phase까지 미룸.
> 2. 최적화 phase 사이 정보 공유가 쉬움 — 같은 그래프를 모든 phase가 본다.
> 3. GVN, CCP 같은 최적화가 자연스럽게 표현됨.

### Q5 [가지 ④]. Safepoint polling이 어떻게 동작하나요?

> mprotect + SEGV 메커니즘:
> 1. JVM이 polling page를 정상 READ → safepoint 요청 시 PROT_NONE으로 토글.
> 2. JIT 코드가 매 method entry/exit/loop back-edge에 polling page read 명령 삽입.
> 3. PROT_NONE 상태에서 read → SEGV.
> 4. JVM signal handler가 catch → safepoint 진입.
>
> "예외를 통신 채널로" — 정상 polling 호출 비용 0, 안전한 stop 시점 보장.

**🪝 Q5-1: SEGV가 진짜 NPE인지 polling인지 어떻게 구분?**
> Signal handler에서 `info->si_addr`이 polling page 주소면 polling, 아니면 진짜 SEGV. polling page 주소는 JVM이 알고 있음. NPE도 같은 방식 — null 참조 SEGV의 si_addr이 0x0 (또는 작은 값)이면 NullPointerException으로 변환.

### Q6 [가지 ②/⑤]. 새 CPU(예: RISC-V) 지원을 HotSpot에 추가하려면?

> `src/hotspot/cpu/riscv/` 디렉토리에:
> - TemplateTable의 opcode asm (각 bytecode → RISC-V instruction)
> - C1/C2의 code emit
> - Memory barrier (RISC-V `fence` 명령)
> - Adapter (calling convention)
> - Safepoint polling instruction
>
> 약 16K 줄. share/는 그대로.

### Q7 (Killer) [가지 ⑤]. OpenJDK bug report에서 source 참조를 어떻게 따라가나요?

> 1. Bug description의 file path 확인 (예: `src/hotspot/share/opto/escape.cpp`).
> 2. 본 챕터 매핑으로 컴포넌트 식별 (opto/ → C2, escape.cpp → Escape Analysis).
> 3. 책의 어느 챕터인지 안다 ([Chapter 03-06 C2 optimizations]).
> 4. `git clone openjdk/jdk` 후 `git log --follow src/...`로 history.
> 5. PR commits 추적 — 어떤 변경이 bug fix.
> 6. JEP/RFE 번호 있으면 https://bugs.openjdk.org/ 검색.
>
> 시니어의 핵심: bug report를 보고 30초 안에 어느 컴포넌트인지 식별, 1분 안에 책의 어느 챕터에서 다루는지 안다.

**🪝 Q7-1: 매핑을 외우기 어렵다면?**
> 11개 디렉토리 이름을 영어 그대로 외움: classfile, interpreter, c1, opto, code, gc, runtime, memory, oops, prims, compiler. 각 이름이 이미 책임을 암시함. opto = optimizing compiler (C2), oops = ordinary object pointer (객체 표현), prims = primitive (JNI/Unsafe).

---

## 8. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 이내로 그릴 수 있다 (루트 + 4가지 + 각 키워드 3개)
- [ ] 가지 ① 3분할: share/cpu/os 각자의 책임을 1줄로 말한다
- [ ] 가지 ② share/: 11개 디렉토리 이름을 다 외운다 + 각자 책임 한 줄
- [ ] 가지 ② share/: 디렉토리 ↔ 책 챕터 매핑을 말한다
- [ ] 가지 ③ C2: 11단계를 순서대로 외운다 (3그룹으로)
- [ ] 가지 ③ C2: Sea-of-Nodes의 장점을 설명한다
- [ ] 가지 ④ Safepoint: mprotect + SEGV 흐름을 그린다
- [ ] OpenJDK bug report 추적 절차를 말한다
- [ ] 7장 꼬리질문 7개에 막힘없이 답한다

---

## 다음 단계

- → [Chapter 08. GraalVM](../08-graalvm/): JVMCI 활용 + Native Image
- ← [Chapter 03. Execution Engine](../03-execution-engine/): C1/C2/Tiered 풀버전
- ← [Chapter 04. GC](../04-garbage-collection/): gc/ 디렉토리 풀버전
- 본 챕터는 **모든 챕터의 C++ source reference** 역할

## 참고

- **OpenJDK source**: https://github.com/openjdk/jdk
- **OpenJDK Bug Tracker**: https://bugs.openjdk.org/
- **HotSpot Glossary**: https://openjdk.org/groups/hotspot/docs/HotSpotGlossary.html
- **OpenJDK Wiki**: https://wiki.openjdk.org/display/HotSpot
- **JVMCI (JEP 243)**: https://openjdk.org/jeps/243
- **HotSpot `compile.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/opto/compile.cpp
- **HotSpot `safepoint.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/safepoint.cpp
