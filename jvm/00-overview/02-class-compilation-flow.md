# 02. 컴파일 흐름 — .java가 CPU 명령어가 되기까지

> "Java는 컴파일 언어인가요, 인터프리트 언어인가요?" 라는 함정 질문에 "둘 다요" 라고 답할 수 있어야 한다.
> 더 정확히는: **"javac로 한 번, JIT으로 한 번 — 두 번 컴파일한다. 그 사이엔 인터프리트한다."**

---

## 📍 학습 목표

1. `.java` → `.class` → 메모리 → native 코드의 7단계를 머리에서 그릴 수 있다.
2. `javac`가 하는 일을 4단계로 분해할 수 있다 (Lexing → Parsing → Annotation Processing → Bytecode Gen).
3. `.class` 파일의 첫 4바이트가 왜 `CAFEBABE`인지, 그 뒤에 무엇이 오는지 안다.
4. Tiered Compilation의 Level 0~4를 설명하고, 왜 이렇게 5단계로 나눴는지 안다.
5. JIT 컴파일된 코드가 어디에 저장되며, 어떻게 폐기되는지 안다.
6. `javap -c -p HelloWorld`의 출력을 해석할 수 있다.

---

## 🎨 1단계: 백지 그리기 가이드

> 가로로 긴 흐름도다. A4를 가로로 놓고 그려라.

### Step 1: 좌우로 7개 박스 — 메인 흐름

```
[1) .java] → [2) javac] → [3) .class] → [4) ClassLoader] → [5) Interpreter] → [6) JIT] → [7) Native]
```

박스마다 색을 다르게 (파랑 → 보라 → 초록 → 주황 → 분홍 → 진주황 → 회색)

### Step 2: 단계 5(Interpreter) 아래에 갈래
- 인터프리트 후 호출 빈도 측정 → 임계치 넘으면 6a (C1), 더 핫하면 6b (C2)
- "역최적화(Deopt)" 화살표를 6b → 5로 점선으로 (가정 깨지면 인터프리터로 복귀)

### Step 3: 우측 하단에 5단 Tiered Compilation 사다리
- L0 → L1 → L2 → L3 → L4
- 각 단계 옆에 한 줄 설명

### Step 4: 좌하단에 javac 4단계
- Lexer / Parser / Annotation Processor / Bytecode Gen 박스를 javac 박스 안 작은 박스들로

### Step 5: 우상단 메모리 행선지 표
- Class 메타데이터 → Metaspace
- 객체 → Heap
- Native code → Code Cache
- 스택 프레임 → JVM Stack

### 정답 그림

![Java 컴파일/실행 흐름](./_excalidraw/02-compile-flow.svg)

> SVG로 직접 임베드된다. 편집하려면 [02-compile-flow.excalidraw](./_excalidraw/02-compile-flow.excalidraw)을 [excalidraw.com](https://excalidraw.com/)에서 "Open" 으로 열면 된다.

---

## 🧠 2단계: 직관

### 핵심 비유

> 통역사 비유:
> - 인터프리터 = 동시통역사. 한 문장 듣고 한 문장 통역. 즉시. 하지만 같은 문장이 100번 나오면 100번 통역.
> - JIT = 번역가. 한 문단을 모아서 정성껏 번역. 처음엔 느리지만 같은 문단이 또 나오면 즉시 재사용.
> - JVM은 **두 사람 다 고용**한다. 처음엔 인터프리터로 빠르게 시작 (warmup 빠름), 자주 나오는 문단은 번역가에게 맡긴다 (steady-state 빠름).

**정확한 정의** (비유와 분리):
- **인터프리터**: bytecode 명령어를 한 번에 하나씩 해석해 실행하는 방식. HotSpot은 Template Interpreter 변형을 쓰지만, 다른 JVM 구현은 다른 방식일 수 있다.
- **JIT (Just-In-Time) 컴파일러**: 런타임에 bytecode(또는 그 일부)를 native machine code로 변환하는 컴파일러. HotSpot은 C1(빠른 컴파일)과 C2(공격적 최적화)를 Tiered Compilation으로 조합한다.
- **두 방식 공존의 이유**: 컴파일 비용 vs 실행 성능의 균형. 자주 안 쓰이는 코드까지 컴파일하면 시동이 느려진다.

### 왜 두 번 컴파일하나?

> **답**: 트레이드오프의 균형.
>
> - 옵션 A: 전부 AOT (Ahead-of-Time) 컴파일 → C/C++ 방식. 시작은 빠르지만 **포팅 어려움**, **동적 정보 활용 못 함**.
> - 옵션 B: 전부 인터프리트 → 원조 JVM (1.0). 단순하지만 **느림**.
> - 옵션 C: AOT + 인터프리트 → 효율적이지만 **JVM의 동적 기능 (reflection, dynamic class loading) 약함**.
> - 옵션 D: javac (bytecode) + JIT — **현재 JVM 방식**. javac가 플랫폼 독립적 중간 표현으로 컴파일 → JVM이 런타임에 실측 프로파일로 추가 컴파일.

### "Bytecode가 왜 stack-based인가?"

JVM의 bytecode는 register가 없다. 모든 연산이 **operand stack**에서 일어난다.
이유:
- **단순함**: 명령어가 짧다. 1바이트 opcode가 대부분.
- **플랫폼 독립**: register 개수가 CPU마다 다르다. 추상화하기 좋다.
- **검증 용이**: Stack-based는 타입 추론이 simpler.

대가:
- 같은 연산에 더 많은 instruction이 필요 (push, pop)
- → JIT이 register allocation을 새로 해야 함

> **참고**: Lua VM, Python의 CPython, .NET CLR도 stack-based.
> Dalvik(Android), Lua 5.1+의 LuaJIT는 register-based.

---

## 🔬 3단계: 구조

### 전체 흐름 (.java → CPU)

```
 ┌──────────┐  javac    ┌──────────┐  ClassLoader  ┌──────────────┐
 │  .java   │ ────────> │  .class  │ ────────────> │  Method Area │
 │ (텍스트)  │           │ (binary) │               │  (Metaspace) │
 └──────────┘           └──────────┘               └──────┬───────┘
                                                          │ 첫 호출
                                                          ▼
                          ┌─────────────────────────────────────────┐
                          │           Interpreter                    │
                          │     (Template-based, HotSpot 기본)        │
                          └────────┬─────────────────┬──────────────┘
                                   │ hot 감지         │ interp 실행
                                   ▼                  │
                          ┌─────────────────┐         │
                          │   C1 JIT        │         │
                          │  (빠른 컴파일)    │         │
                          └────────┬────────┘         │
                                   │ 더 hot           │
                                   ▼                  │
                          ┌─────────────────┐         │
                          │   C2 JIT        │         │
                          │  (공격적 최적화)  │         │
                          └────────┬────────┘         │
                                   │                  │
                                   ▼                  │
                          ┌─────────────────┐         │
                          │  Code Cache     │         │
                          │  (native code)  │         │
                          └────────┬────────┘         │
                                   │ 직접 호출         │
                                   ▼                  ▼
                          ┌──────────────────────────────────┐
                          │             CPU                   │
                          └──────────────────────────────────┘

 ★ 역최적화 (Deoptimization): C1/C2의 speculation이 깨지면 Interpreter로 복귀
```

### javac의 내부 4단계

```
   ┌──────────────┐
   │  .java 소스   │
   └──────┬───────┘
          │
          ▼
   ┌──────────────────────┐
   │ 1. Lexer (Token화)    │
   └──────┬───────────────┘
          ▼
   ┌──────────────────────┐
   │ 2. Parser (AST 생성)  │
   └──────┬───────────────┘
          ▼
   ┌──────────────────────────────────────────────┐
   │ ★ 3. Annotation Processor                    │
   │     (Lombok, MapStruct, Dagger, ...)         │
   │     라운드 반복 가능 — 생성된 코드를 다시 처리   │
   └──────┬───────────────────────────────────────┘
          ▼
   ┌──────────────────────────────┐
   │ 4a. Semantic Analysis         │
   │     (타입 검사, scope, flow)   │
   └──────┬───────────────────────┘
          ▼
   ┌──────────────────────────────┐
   │ 4b. Bytecode Generation       │
   └──────┬───────────────────────┘
          ▼
   ┌──────────────┐
   │  .class 출력  │
   └──────────────┘
```

> Annotation Processing은 다단계 가능 (한 라운드에서 생성된 코드를 다음 라운드에서 또 처리).
> Lombok이 `@Getter` 어노테이션을 AST에 직접 삽입할 수 있는 이유.

### ClassFile 포맷 (.class)

```
ClassFile {
    u4             magic;            // 0xCAFEBABE  (4 bytes)
    u2             minor_version;    // ex: 0       (2 bytes)
    u2             major_version;    // 65 = JDK 21 (2 bytes)
    u2             constant_pool_count;
    cp_info        constant_pool[constant_pool_count - 1];   // 1-indexed!
    u2             access_flags;     // public, final, abstract, ...
    u2             this_class;       // CP index
    u2             super_class;      // CP index (Object면 java.lang.Object)
    u2             interfaces_count;
    u2             interfaces[interfaces_count];
    u2             fields_count;
    field_info     fields[fields_count];
    u2             methods_count;
    method_info    methods[methods_count];
    u2             attributes_count;
    attribute_info attributes[attributes_count];  // SourceFile, InnerClasses, ...
}
```

> `u4`는 4바이트 unsigned, `u2`는 2바이트 unsigned.
> Constant Pool은 1-indexed라는 함정. 0번 인덱스는 안 씀.

### major_version 매핑

| JDK | major | 출시 |
|---|---|---|
| 1.0 | 45 | 1996 |
| 5 | 49 | 2004 |
| 6 | 50 | 2006 |
| 7 | 51 | 2011 |
| 8 | 52 | 2014 |
| 11 | 55 | 2018 |
| 17 | 61 | 2021 |
| 21 | 65 | 2023 |

> 공식: `major - 44 = JDK 버전 (1.x 시리즈는 1.x = major - 44)`.
> JDK 5부터는 `major - 44 = 메이저 버전`.

### `javap -c -p` 실제 출력 해석

```java
public class HelloWorld {
    public static void main(String[] args) {
        System.out.println("Hello, World!");
    }
}
```

```bash
$ javac HelloWorld.java
$ javap -c -p HelloWorld
```

```
Compiled from "HelloWorld.java"
public class HelloWorld {
  public HelloWorld();
    Code:
       0: aload_0                  // this를 operand stack에 push
       1: invokespecial #1         // java/lang/Object."<init>":()V 호출
       4: return

  public static void main(java.lang.String[]);
    Code:
       0: getstatic     #7         // System.out 필드 push
       3: ldc           #13        // "Hello, World!" 문자열 push
       5: invokevirtual #15        // PrintStream.println 호출
       8: return
}
```

각 줄의 첫 숫자는 **bytecode 오프셋**. `aload_0`은 1바이트지만 `invokespecial`은 3바이트(opcode + 2바이트 CP 인덱스)라서 0 → 1 → 4 점프.

### Tiered Compilation (5단)

```
┌────────────────────────────────────────────────────────────┐
│  Level 0 │ Interpreter, no profiling                       │
│          │ → 모든 메서드의 출발점                            │
├──────────┼─────────────────────────────────────────────────┤
│  Level 1 │ C1, no profiling                                │
│          │ → 단순 메서드 (getter/setter 등) — 컴파일 후 끝   │
├──────────┼─────────────────────────────────────────────────┤
│  Level 2 │ C1, with invocation/back-edge counters          │
│          │ → C1이 잠시 컴파일, 카운터 누적                   │
├──────────┼─────────────────────────────────────────────────┤
│  Level 3 │ C1, full profiling                              │
│          │ → 메서드 인자 타입, 분기 빈도, null 빈도 등 수집    │
├──────────┼─────────────────────────────────────────────────┤
│  Level 4 │ C2, with profile data                           │
│          │ → 공격적 최적화: inline, EA, branch pred, vec    │
└──────────┴─────────────────────────────────────────────────┘
```

**일반적 승격 경로**: L0 → L3 → L4 (대부분 메서드)
**Trivial 메서드**: L0 → L1 (computed by `is_trivial` heuristic)
**C2 큐 막힘 시**: L0 → L2 → L3 → L4 (C2가 바빠 미뤄지면 L2로 우회)

### 역최적화(Deoptimization)

C2가 한 **가정(speculation)**이 깨지면 그 코드는 무효화되고 L0로 떨어진다.

| 트리거 | 예시 |
|---|---|
| **Class hierarchy change** | 새 서브클래스 로드 → CHA 가정 깨짐 → 가상 호출 inline 무효 |
| **Type speculation 실패** | 항상 `String`이 오던 곳에 `Integer`가 옴 → uncommon trap |
| **Class redefinition** | JVMTI agent가 클래스 재정의 |
| **Null check 실패** | 항상 non-null이라 가정 → null이 옴 |
| **Range check 실패** | 항상 in-range 가정 → out-of-bounds |

```
[C2 native code 실행 중] → trap! → [Deoptimization]
                                    → 스택 프레임 재구성
                                    → 인터프리터로 점프
                                    → 카운터 리셋, 재컴파일 대기
```

---

## 🧬 4단계: 내부 구현 (HotSpot)

### javac는 JVM이 아니다

> 함정: `javac`는 JDK 도구이지 JVM의 일부가 아니다.
> 실제로 `javac`는 **Java로 작성된 컴파일러**다. JDK 자체가 `javac`를 컴파일했다.
> 위치: `src/jdk.compiler/share/classes/com/sun/tools/javac/`.

```java
// com.sun.tools.javac.main.JavaCompiler 의 핵심 메서드 (요약)
public void compile(Collection<JavaFileObject> sourceFileObjects, ...) {
    // 1. Parse
    List<JCCompilationUnit> roots = parseFiles(sourceFileObjects);

    // 2. Enter (심볼 테이블 구축)
    enterTrees(roots);

    // 3. Annotation Processing (라운드 반복)
    if (processAnnotations) {
        processAnnotations(roots);
    }

    // 4. Attribute (타입 검사, 시멘틱)
    attribute(todo);

    // 5. Flow analysis (definite assignment, exception 검사)
    flow(todo);

    // 6. Desugar (lambda → invokedynamic, foreach → iterator, ...)
    desugar(todo);

    // 7. Generate bytecode
    generate(todo);
}
```

### Interpreter는 무엇으로 만들어졌나? — Template Interpreter

> HotSpot의 인터프리터는 **런타임에 어셈블리를 생성**한다. 이게 진짜 충격적인 부분.

위치: `src/hotspot/share/interpreter/templateInterpreter.cpp`

각 bytecode opcode마다 어셈블리 템플릿이 있다. JVM 시작 시:
1. CPU 아키텍처(x86_64/aarch64) 감지
2. 각 opcode에 대응하는 native code 시퀀스를 메모리에 generate
3. 그 메모리 영역을 "interpreter"로 사용

```cpp
// templateInterpreter.cpp의 핵심 흐름 (요약)
void TemplateInterpreterGenerator::generate_all() {
  // 각 bytecode마다 generator 호출
  set_entry_points_for_all_bytes();
  // ...
}

void TemplateTable::iconst(int value) {
  // int 상수를 operand stack에 push하는 어셈블리 생성
  __ push(value);  // x86_64 push 명령어 emit
}

void TemplateTable::iadd() {
  // operand stack 위 두 정수를 더해서 다시 push
  __ pop_i(rax);
  __ addl(at_tos(), rax);
}
```

> `__` 매크로는 `MacroAssembler*`를 풀어쓴 것. 한 줄이 x86 asm 한 줄을 생성한다.

### 결과: HotSpot 인터프리터는 사실상 매우 단순한 JIT

- 컴파일된 native 어셈블리가 메모리에 있다
- bytecode 실행 = 그 generated assembly로 점프
- 그래서 일반적인 "스위치-케이스 인터프리터"보다 훨씬 빠르다

### C1 컴파일러: 빠른 컴파일, 적당한 최적화

위치: `src/hotspot/share/c1/`

C1은 **선형 IR**을 쓴다. 옛 이름은 Linear Scan Register Allocation의 C1.

흐름:
1. Bytecode → HIR (High-level IR, value-based)
2. HIR 단순 최적화 (constant folding, null check 제거, devirtualization)
3. HIR → LIR (Low-level IR)
4. Register allocation (Linear Scan)
5. Machine code emit

목표: **빠른 컴파일** (수 ms ~ 수십 ms). 최적화는 적당히.

### C2 컴파일러: Sea of Nodes, 공격적 최적화

위치: `src/hotspot/share/opto/`

C2는 **Sea of Nodes** IR을 쓴다. 1999년 Cliff Click 박사 논문 기반.

핵심 아이디어:
- 모든 노드(연산, 값)가 평등한 그래프에 흩뿌려져 있음
- Control flow와 Data flow가 한 그래프에 통합
- 노드 간 의존성만 표현 — 위치는 스케줄링 단계에서 결정

```cpp
// opto/compile.cpp 핵심 진입
void Compile::Optimize() {
  // 1. Parse: bytecode → Ideal Graph
  Parse parse(this, igvn);

  // 2. Optimization passes
  IterGVN(...);          // Global Value Numbering
  PhaseIdealLoop(...);   // Loop opts (unrolling, vectorization)
  Escape::do_analysis(...); // Escape Analysis
  PhaseMacroExpand(...); // 매크로 노드 풀기

  // 3. Schedule: 노드 순서/블록 결정
  PhaseCFG::do_global_code_motion();

  // 4. Machine-specific lowering
  PhaseChaitin::Register_Allocate();  // Graph coloring RA

  // 5. Emit machine code
  Output();
}
```

> C2의 진짜 강점은 **inlining**, **escape analysis**, **branch prediction**.
> 작은 메서드를 마구잡이로 inline하면서 큰 메서드 하나처럼 만든 다음, 한꺼번에 최적화한다.

### JIT 결과: Code Cache

위치: `src/hotspot/share/code/codeCache.cpp`

```cpp
// codeCache.cpp
class CodeCache : public AllStatic {
  static GrowableArray<CodeHeap*>* _heaps;  // 3개 영역

  // JDK 9+ Segmented Code Cache:
  // - non-profiled methods (C2 컴파일 결과, GC root scan 제외)
  // - profiled methods (C1 컴파일 결과, 자주 deopt될 수 있음)
  // - non-methods (interpreter, adapter, stub)
};
```

기본 크기: 240 MB. `-XX:ReservedCodeCacheSize=512m`로 조정.

Code Cache가 차면 **CodeCacheFull warning** → JIT 중단 → 인터프리터로 fallback → 성능 폭락.

### Deoptimization 구현

위치: `src/hotspot/share/runtime/deoptimization.cpp`

```cpp
// deoptimization.cpp (핵심 흐름)
void Deoptimization::deoptimize(JavaThread* thread, frame& fr) {
  // 1. 어셈블된 native frame을 인터프리터 frame들로 "vframe-ize"
  GrowableArray<compiledVFrame*>* chunk = collect_chunk(thread, fr);

  // 2. 각 inlined call에 대해 interpreter frame을 새로 만들 준비
  UnrollBlock* info = fetch_unroll_info_helper(thread, ...);

  // 3. 스택 다시 쌓기 (각 vframe → interpreter frame)
  unpack_frames(thread, info);

  // 4. 다음에 호출되면 인터프리터에서 재실행
  // 5. 컴파일러에게 "이 메서드 다시 컴파일하지 마, 또 같은 trap 날 거야" 신호
  if (reason == reason_unstable_if) {
    // ...
  }
}
```

> 가장 신기한 부분: native register들에 흩어진 값들을 **bytecode 오프셋 기준의 stack frame**으로 재구성한다.
> 이게 가능한 이유는 C2가 컴파일 시 **OopMap**과 **debug info**를 같이 저장해두기 때문.

---

## 📜 5단계: 역사

### 1996: Classic VM — 순수 인터프리터

- bytecode를 switch-case로 디스패치. 한 줄 한 줄.
- C++ 대비 20~50배 느림. **"Java is slow"** 신화의 출발.

### 1999: HotSpot 1.0 (JDK 1.3) — JIT 등장

- Strongtalk VM(Smalltalk용) 만든 Animorphic Systems를 Sun이 1997년 인수
- "Hot Spot"이 의미하는 것: 자주 실행되는 코드(hot)만 컴파일. 차가운 코드는 인터프리트.
- **Pareto principle**: 10%의 코드가 90% 실행 시간을 차지 → 그 10%만 컴파일하면 충분

### 2000: Server VM (C2) 추가

- 1.3에서 C2 출시 (`-server` 옵션). 더 공격적인 최적화.
- 기본은 Client VM (C1). 서버 배포는 `-server` 명시해야 함.

### 2012: Tiered Compilation (JDK 7)

- 그 전까지: C1 또는 C2 중 하나만 선택 (`-client` vs `-server`).
- JDK 7부터 둘 다 사용. 처음엔 C1, hot해지면 C2로 승격.
- JDK 8부터 **기본 활성화**.

### 2014: JDK 8 — Metaspace, Lambda

- PermGen 제거, Metaspace 도입. Class 메타데이터는 GC 안 되는 native 메모리로.
- Lambda 컴파일: **invokedynamic**으로. lambdaMetafactory가 런타임에 hidden class 생성.

### 2018: JDK 11 — AOT (실험적, JEP 295)

- `jaotc` 도구: 클래스를 미리 native로 컴파일.
- 잘 안 쓰임. JDK 17에서 GraalVM Native Image로 사실상 대체. JDK 16에서 제거.

### 2020: JDK 16 — JEP 396 Strong Encapsulation

- 내부 API에 대한 reflection 접근이 deprecated → 19에서 막힘
- 이게 컴파일 흐름과 무관해 보이지만, **build tool(Maven/Gradle)에 큰 영향**

### 2023: JDK 21 — Generational ZGC

- ZGC가 generation을 가짐. Young/Old 분리.
- Code Cache와 직접 관련은 없지만, GC가 컴파일된 코드 내부의 oop 참조를 어떻게 처리하는지 변화.

### 미래: Project Leyden — Static Java

- AOT + closed-world assumption + size 감소
- 2026년경 첫 안정화 예상

---

## ⚔️ 6단계: 꼬리질문 트리

### Q1. `.java`가 어떻게 `.class`가 되고, 어떻게 실행되나요?

**예상 답변** (간단 버전):
> javac가 .java를 lexing/parsing/타입검사/bytecode 생성을 거쳐 .class로 변환.
> JVM이 ClassLoader로 .class를 메모리에 로드.
> Interpreter가 bytecode를 한 줄씩 실행.
> hot한 메서드는 C1/C2 JIT으로 native 코드로 컴파일 → Code Cache에 저장.

#### 🪝 꼬리 Q1-1: "그 .class 파일의 첫 4바이트가 뭐죠?"

**예상 답변**:
> `0xCAFEBABE`. James Gosling이 자주 가던 카페 이름에서 따왔다고 함.

##### 🪝 꼬리 Q1-1-1: "그 뒤엔 뭐가 오나요? Constant Pool 구조를 설명해보세요."

**예상 답변**:
> magic(4B) → minor_version(2B) → major_version(2B) → constant_pool_count(2B) → constant_pool 엔트리들.
> Constant Pool은 1-indexed (0번은 안 씀, 빈 슬롯). 각 엔트리는 tag(1B) + 가변 길이 데이터.
> 주요 tag:
> - CONSTANT_Utf8 (1): UTF-8 인코딩된 문자열 (modified UTF-8, null byte를 2바이트로)
> - CONSTANT_Integer (3), CONSTANT_Float (4): 4바이트 값
> - CONSTANT_Long (5), CONSTANT_Double (6): 8바이트 값 + **다음 슬롯 하나 비움** (역사적 실수)
> - CONSTANT_Class (7): name_index 가리킴
> - CONSTANT_String (8): string_index
> - CONSTANT_Fieldref/Methodref/InterfaceMethodref (9/10/11)
> - CONSTANT_NameAndType (12)
> - CONSTANT_MethodHandle (15), MethodType (16), Dynamic (17), InvokeDynamic (18): JDK 7+
> - CONSTANT_Module (19), Package (20): JDK 9+

###### 🪝 꼬리 Q1-1-1-1: "Long과 Double이 슬롯을 2개 차지하는 이유는?"

**예상 답변**:
> JVM 초기 설계 실수. JVMS Section 4.4.5에 명시되어 있다:
> "In retrospect, making 8-byte constants take two constant pool entries was a poor choice."
> 처음엔 Constant Pool 인덱스가 8바이트 값을 가리킬 수 있도록 stride를 맞추려 했으나, 결과적으로 복잡도만 늘었다.
> 호환성 때문에 못 고치고 그대로 유지.

#### 🪝 꼬리 Q1-2: "javac가 lambda를 어떻게 컴파일하나요?"

**예상 답변**:
> JDK 8부터 lambda는 **invokedynamic** + lambdaMetafactory로 처리.
> javac는 lambda 본문을 private static 메서드로 추출 (`lambda$0` 같은 이름).
> 그리고 invokedynamic 명령으로 호출 시점에 `LambdaMetafactory.metafactory`를 부르고, factory가 **hidden class**를 동적 생성해서 lambda 인스턴스를 반환.

##### 🪝 꼬리 Q1-2-1: "왜 익명 클래스(.class 미리 생성)가 아니라 invokedynamic을 썼나요?"

**예상 답변**:
> 1. **유연성**: 미래에 lambda 구현 방식을 바꿔도 bytecode는 그대로. (실제로 hidden class 변경됨)
> 2. **메모리 효율**: 익명 클래스는 클래스 로딩 + Metaspace 사용. invokedynamic은 lazy하게 한 번만.
> 3. **inlining**: lambda body가 작으면 JIT이 호출 사이트에 통째로 inline 가능.
> 4. **언어 진화**: invokedynamic은 JRuby, Scala 등 다른 언어가 이미 쓰던 것 — Java가 그 인프라를 활용.

### Q2. Tiered Compilation의 5단계를 설명하세요.

**예상 답변** (Q1 외 추가):
> L0(Interp) → L3(C1 full profile) → L4(C2)가 메인 경로.
> Trivial 메서드는 L0 → L1로 끝. C2 큐 막히면 L0 → L2(C1 with counters) → L3 → L4.
> 각 단계 전환은 invocation counter + back-edge counter가 임계치 넘을 때.

#### 🪝 꼬리 Q2-1: "왜 C1과 C2를 둘 다 두나요? C2만 쓰면 안 되나요?"

**예상 답변**:
> C2는 **컴파일이 느리다**. 큰 메서드 하나가 수백 ms 걸릴 수 있다.
> 모든 메서드를 C2로 컴파일하면 warmup이 매우 느림.
> C1은 **밀리세컨 단위 컴파일** + 어느 정도 빠른 코드 생성.
> 또한 C1에서 **profile** 수집 → C2가 그 데이터를 활용해 더 공격적 최적화 가능.
> "빠른 1차 컴파일 + 천천히 더 좋은 2차 컴파일"의 파이프라인.

##### 🪝 꼬리 Q2-1-1: "C2가 어떤 profile 정보를 활용하나요?"

**예상 답변**:
> - **Branch frequency**: if-else에서 어느 쪽이 자주 잡히는지 → branch prediction hint
> - **Virtual call target**: 가상 메서드 호출 시 실제 호출되는 클래스 분포 → monomorphic이면 inline, bimorphic이면 type-check + inline 두 개
> - **Type profile**: 메서드 인자가 항상 같은 클래스인지
> - **Null check 빈도**: 항상 non-null이면 null check 제거 + speculation
> - **Loop iteration count**: unrolling 결정
> 이걸 모두 `MethodData` 객체에 저장 (Metaspace).

### Q3. 역최적화(Deoptimization)는 언제 일어나고, 어떻게 일어나나요?

**예상 답변**:
> C2가 한 가정(speculation)이 깨질 때:
> - Class hierarchy change (새 서브클래스 로드)
> - Type speculation 실패
> - Null/Range check 실패
> - Class redefinition (JVMTI)
>
> 일어나는 방법:
> 1. C2 native code 실행 중 trap 발생
> 2. 어셈블된 register/stack 상태를 인터프리터 frame들로 재구성 (debug info 기반)
> 3. 인터프리터로 점프
> 4. 카운터 리셋, 일정 횟수 후 재컴파일 대기

#### 🪝 꼬리 Q3-1: "역최적화 비용은 얼마나 큰가요?"

**예상 답변**:
> 한 번 일어나면 수 µs ~ 수십 µs (스택 재구성 + 명령어 캐시 미스).
> 빈번하면 **OSR(On-Stack Replacement)도 못 따라가서** P99 latency 폭증.
> `-XX:+PrintCompilation` + `-XX:+PrintInlining` + `-XX:+PrintDeoptimization`로 감지.
> 또는 JFR `jdk.Deoptimization` 이벤트.

##### 🪝 꼬리 Q3-1-1: "OSR이 뭐죠?"

**예상 답변**:
> **On-Stack Replacement**: 인터프리터로 실행 중인 **루프**가 hot해졌을 때, **루프 도중에** 컴파일된 코드로 전환.
> 메서드 입구가 아니라 백엣지(loop back-edge)에서 점프.
> 일반적인 JIT 컴파일은 메서드 호출 진입 시에만 가능. OSR은 이미 시작된 메서드에 대해 동작.
> 구현: 인터프리터 frame을 native frame으로 변환 (Deopt의 역방향).

### Q4. Code Cache가 가득 차면 어떻게 되나요?

**예상 답변**:
> 1. `CodeCache is full. Compiler has been disabled.` 경고가 stderr에 나옴.
> 2. 새 JIT 컴파일이 중단됨.
> 3. 이미 컴파일된 코드는 계속 실행되지만, 새 hot 메서드는 인터프리터로만 동작.
> 4. 결과: **성능 5~10배 저하**.
>
> 방지:
> - `-XX:ReservedCodeCacheSize=512m`로 충분히 크게
> - `-XX:+UseCodeCacheFlushing` (기본 on): 오래된 코드 제거 시도
> - Segmented Code Cache 모니터링: `jcmd <pid> Compiler.codecache`

#### 🪝 꼬리 Q4-1: "Code Cache가 가득 찰 만한 상황은?"

**예상 답변**:
> - **너무 많은 메서드** (수백만 줄 코드베이스 + dependency)
> - **dynamic class generation** (Mockito, Spring AOP, CGLib, ByteBuddy로 매번 새 클래스)
> - **frequent class redefinition** (JRebel, JVMTI agents)
> - **너무 작은 `-XX:ReservedCodeCacheSize`** (기본 240MB가 부족한 경우)

##### 🪝 꼬리 Q4-1-1: "Spring 앱에서 Code Cache가 빨리 차는 이유는?"

**예상 답변**:
> 1. Spring AOP가 각 `@Service`/`@Transactional` 빈마다 **CGLib subclass** 또는 **JDK Dynamic Proxy** 생성.
> 2. 그 proxy의 각 메서드가 또 JIT 컴파일됨.
> 3. Spring Boot fat jar에는 수천 개 클래스 + 수만 개 메서드.
> 4. Tiered Compilation은 각 메서드를 **두 번 (C1, C2)** 컴파일 → Code Cache 사용량 2배.

### Q5. (Killer) `javap -v`의 출력에서 `stack=2, locals=1`은 무슨 뜻이고, 그 값은 어떻게 결정되나요?

**예상 답변**:
> 메서드의 **operand stack 최대 깊이 = 2**, **local variable slots = 1** (this 포함).
> `stack`은 javac가 bytecode 생성 시 각 instruction의 stack effect를 simulate해서 최대값을 계산.
> `locals`은 메서드 시그니처 + 메서드 내 선언된 변수로부터 결정.
>
> JVM은 이 값을 보고 **그 메서드의 stack frame 크기를 미리 정확히 할당**할 수 있다.
> 이게 JVM이 stack-based이면서도 빠른 이유 중 하나 — 동적 stack growth 없음.

#### 🪝 꼬리 Q5-1: "`stack`과 `locals`가 ClassFile에 저장된다는 건, javac가 그 계산을 한다는 뜻인데, 잘못된 값을 넣으면 어떻게 되나요?"

**예상 답변**:
> **Verifier가 잡는다**. ClassLoader의 Linking 단계에서 Verify가 동작:
> - 각 bytecode 위치에서 stack 상태를 추론 (type + 크기)
> - 선언된 `max_stack`을 초과하는 push 발견 시 `VerifyError` throw
> - JDK 6부터는 `StackMapTable` attribute로 javac가 검증 정보를 미리 채워두고, JVM은 type 검사만 수행 (이전: dataflow 분석)

##### 🪝 꼬리 Q5-1-1: "StackMapTable이 도입된 이유는?"

**예상 답변**:
> JDK 5까지의 verification은 **fixed-point iteration**으로 각 basic block의 타입 상태를 수렴시켰다. 시간 복잡도 O(n²) ~ O(n³). 큰 메서드에서 느림.
> JDK 6 + `-target 1.6` 부터 javac가 `StackMapTable`을 미리 채움. 각 분기 지점에서의 stack/locals 타입 상태를 명시.
> JVM은 그 정보를 신뢰하면서 **linear 검사**만 하면 됨. O(n).
> JDK 7부터는 필수가 됨 (`-target 1.7`+ class에서 StackMapTable 없으면 verify 실패).

---

## 🔗 다음 단계

- → [03. JVM 아키텍처 큰 그림](./03-jvm-architecture-bigpicture.md): 이 챕터의 각 단계가 JVM 내부의 어디에 매핑되는지
- → 01-class-lifecycle (예정): ClassLoader 부모 위임 + Verification/Preparation/Resolution/Initialization 풀버전
- → 03-execution-engine (예정): Template Interpreter, C1, C2 풀버전

## 📚 참고

- **JVMS §4 (ClassFile Format)**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html
- **JVMS §6 (Bytecode Instructions)**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html
- **Tiered Compilation (JEP 165)**: https://openjdk.org/jeps/165
- **Cliff Click — Sea of Nodes paper (1995)**: https://www.oracle.com/technetwork/java/javase/tech/c2-ir95-150110.pdf
- **HotSpot Glossary**: https://openjdk.org/groups/hotspot/docs/HotSpotGlossary.html
