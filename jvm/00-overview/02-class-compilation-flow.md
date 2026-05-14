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

### 핵심 비유 — 통역사 vs 번역가

> - **인터프리터** = 동시통역사. 한 문장 듣고 한 문장 통역. 즉시. 하지만 같은 문장이 100번 나오면 100번 통역.
> - **JIT** = 번역가. 한 문단을 모아서 정성껏 번역. 처음엔 느리지만 같은 문단이 또 나오면 즉시 재사용.
> - **JVM은 두 사람 다 고용한다.** 처음엔 인터프리터로 빠르게 시작(warmup 빠름), 자주 나오는 문단은 번역가에게 맡긴다(steady-state 빠름).

### 정확한 정의 — Interpreter / JIT / AOT

세 단어는 **"native code로 변환하는 시점이 언제냐"** 라는 한 축 위에 있다:

| 방식 | 풀어 쓰기 | 변환 시점 | 대표 |
|---|---|---|---|
| **AOT** | Ahead-of-Time | 빌드 시 (실행 전 미리) | C, C++, Rust, Go, **GraalVM Native Image** |
| **JIT** | Just-in-Time | 실행 중 (필요한 시점에 딱) | **JVM(HotSpot)**, .NET, V8 |
| **Interpreter** | (약자 아님) | 변환 안 함 | 옛 Python, 1995년 Java 1.0 |

JVM은 **Interpreter + JIT 조합**. 둘 다 쓴다.

**구체적 정의**:
- **인터프리터**: bytecode 명령어를 한 번에 하나씩 해석해 실행하는 방식. HotSpot은 **Template Interpreter 변형**을 쓰지만, 다른 JVM 구현은 다른 방식일 수 있다 → [부록 A](./02-deep-dive/A-interpreter-implementations.md), [부록 B](./02-deep-dive/B-jvm-implementations.md).
- **JIT 컴파일러**: 런타임에 bytecode(또는 그 일부)를 native machine code로 변환하는 컴파일러. HotSpot은 **C1**(빠른 컴파일)과 **C2**(공격적 최적화)를 **Tiered Compilation**으로 조합한다.
- **두 방식 공존의 이유**: 컴파일 비용 vs 실행 성능의 균형. 자주 안 쓰이는 코드까지 컴파일하면 시동이 느려진다.

### 왜 두 번 컴파일하나 — 4가지 옵션 비교

**트레이드오프의 균형**이다.

| 옵션 | 방식 | 장점 | 약점 |
|---|---|---|---|
| **A** | 전부 AOT | 시작 빠름 (C/C++ 방식) | 포팅 어려움, **동적 정보 활용 못 함** |
| **B** | 전부 인터프리트 | 단순 (1995 JVM 1.0) | **느림** (C++ 대비 20~50배) |
| **C** | AOT + 인터프리트 | 효율적 | **JVM 동적 기능**(reflection, dynamic class loading) 약함 |
| **D** | **javac(bytecode) + JIT** | 이식성 + 실측 최적화 + 동적 기능 | warmup 비용 + 메모리 |

**D가 현재 JVM 방식**. javac가 플랫폼 독립적 중간 표현(bytecode)으로 컴파일 → JVM이 런타임에 실측 프로파일로 추가 컴파일.

> 핵심: **AOT는 "예측 컴파일", JIT은 "관측 컴파일"**. JIT은 실제 실행을 본 결과(실측 프로파일)로 devirtualization·escape analysis·branch prediction을 한다 — AOT가 절대 못 하는 일.
>
> JIT이 활용하는 5가지 실측 정보(inlining/devirt/branch pred/EA/vectorization)와 동적 컴파일 라이프사이클의 본격 설명은 → [부록 E — AOT vs JIT + JIT의 5가지 실측 최적화](./02-deep-dive/E-aot-jit-optimizations.md).

### "Java는 컴파일 언어인가요, 인터프리트 언어인가요?" — 함정 질문에 답하기

> **"둘 다입니다. 정확히는 javac로 한 번 컴파일하고, JIT으로 한 번 더 컴파일하며, 그 사이엔 인터프리트합니다."**
>
> - **1차 컴파일 (javac)**: `.java` → `.class` (bytecode). 정적, 빌드 시점.
> - **인터프리트 (Template Interpreter)**: 실행 시작 즉시. 워밍업 없음.
> - **2차 컴파일 (JIT, C1+C2)**: hot 메서드만 native code로. 실측 프로파일 기반.
> - **역최적화 (Deopt)**: JIT의 가정이 깨지면 인터프리터로 복귀.

### Bytecode가 왜 stack-based인가?

JVM의 bytecode는 register가 없다. 모든 연산이 **operand stack**에서 일어난다.

**이유**:
- **단순함**: 명령어가 짧다. 1바이트 opcode가 대부분.
- **플랫폼 독립**: register 개수가 CPU마다 다르다. 추상화하기 좋다.
- **검증 용이**: Stack-based는 타입 추론이 simpler.

**대가**:
- 같은 연산에 더 많은 instruction이 필요 (push, pop)
- → JIT이 register allocation을 새로 해야 함

> **참고**: Lua VM, CPython, .NET CLR도 stack-based.
> Dalvik(Android), LuaJIT는 register-based.

### 더 깊이 들어가고 싶다면 — 부록

| 부록 | 다루는 것 |
|---|---|
| [A. 인터프리터 구현 4가지 방식](./02-deep-dive/A-interpreter-implementations.md) | Switch / Direct-Threaded / Template / AST. HotSpot이 "어셈블리를 부팅 시 generate"한다는 게 정확히 뭔가 |
| [B. JVM 구현체 비교](./02-deep-dive/B-jvm-implementations.md) | HotSpot/OpenJDK/GraalVM/OpenJ9/Azul/ART 차이. "GraalVM이 C2만 갈아끼운 이유" |
| [C. AST 자료구조](./02-deep-dive/C-ast.md) | 코드를 트리로 표현. javac/Lombok/IDE 리팩토링의 출발점. Truffle이 AST를 IR로 쓰는 이유 |
| [D. opcode 디스패치 메커니즘](./02-deep-dive/D-opcode-dispatch.md) | opcode 1바이트, 핸들러 점프 테이블, branch predictor 학습 |
| [E. AOT vs JIT + JIT의 5가지 실측 최적화](./02-deep-dive/E-aot-jit-optimizations.md) | inlining / devirt / branch prediction / EA / vectorization |

---

## 🔬 3단계: 구조 — `.java`가 CPU에서 실행되기까지 (단계별)

> 1단계 백지 그리기에서 그린 7개 박스를 **하나씩 풀어쓴다**.

### 전체 흐름 한눈에

![.java → CPU 7-Stage 전체 흐름](./_excalidraw/02f-7-stage-flow.svg)

> 편집: [02f-7-stage-flow.excalidraw](./_excalidraw/02f-7-stage-flow.excalidraw)를 [excalidraw.com](https://excalidraw.com/)에서 "Open"으로.

<details>
<summary>🔎 ASCII 버전 (텍스트로 보고 싶을 때)</summary>

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

</details>

---

### Stage 1 — javac: `.java` → bytecode (4단계 분해)

`javac`("자바씨", Java Compiler)는 **Java로 작성된 컴파일러**다. 입력 `.java` 텍스트, 출력 `.class` 바이너리. 내부에서 4단계(엄밀히는 5단계)를 거친다.

#### javac의 내부 4단계

![javac 5단계](./_excalidraw/02a-javac-stages.svg)

> 편집: [02a-javac-stages.excalidraw](./_excalidraw/02a-javac-stages.excalidraw)

> Annotation Processing은 다단계 가능 (한 라운드에서 생성된 코드를 다음 라운드에서 또 처리).
> Lombok이 `@Getter` 어노테이션을 AST에 직접 삽입할 수 있는 이유.

<details>
<summary>🔎 ASCII 버전</summary>

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

</details>

#### 1.1 Lexing (Tokenization) — 글자를 토큰으로

> **Lexer(렉서) = "글자 시퀀스를 의미 있는 단어 단위(토큰)로 자르는 단계"**.

자바 소스는 컴퓨터 입장에선 그냥 **글자 시퀀스**(`i`, `n`, `t`, ` `, `c`, ...)다. 이걸 의미 있는 단위로 잘라야 다음 단계가 작업 가능.

```
입력:  "int c = a + b;"
       ↓ Lexer
출력:  [TOKEN(KEYWORD, "int"),
        TOKEN(IDENT,   "c"),
        TOKEN(OP,      "="),
        TOKEN(IDENT,   "a"),
        TOKEN(OP,      "+"),
        TOKEN(IDENT,   "b"),
        TOKEN(SEMI,    ";")]
```

각 토큰은 두 가지를 들고 다닌다:
- **종류** (keyword, identifier, operator, number literal, string literal, ...)
- **원문 텍스트** (필요할 때 참조용)

Lexer가 처리하는 것:
- 공백·줄바꿈·들여쓰기 **제거** (의미 없음)
- `// ...`, `/* ... */` 주석 **제거**
- `if`, `while`, `class`, `int` 같은 **예약어 인식**
- `"hello"` 같은 **문자열 리터럴 묶기** (따옴표 안의 공백은 그대로)
- `123`, `0xFF`, `3.14f` 같은 **숫자 리터럴 파싱**
- `==`, `>=`, `++` 같은 **다중 문자 연산자** 식별

위치: `com.sun.tools.javac.parser.Scanner`, `JavaTokenizer`

> 💡 다른 이름: **Tokenizer**(토크나이저) = **Scanner**(스캐너). 같은 것. Compilers 책에서는 "Scanner"라고도 함.

#### 1.2 Parsing — 토큰을 AST로

> **Parser(파서) = "토큰 시퀀스를 문법 규칙에 맞춰 AST(트리)로 조립하는 단계"**.

토큰 시퀀스만으로는 중첩 관계가 안 보인다. **트리 구조**로 만들어야 "이 표현식 안에 저 표현식이 들어있다"는 게 명시됨.

```
입력:  [int, c, =, a, +, b, ;]
       ↓ Parser
출력:  VariableDeclaration
       ├─ type: int
       ├─ name: c
       └─ init: BinaryOp(+)
                ├─ left:  Identifier(a)
                └─ right: Identifier(b)
```

이게 바로 **AST (Abstract Syntax Tree)**. AST의 정의·왜 트리여야 하는가·다른 도구들에서의 활용은 → [부록 C — AST 자료구조](./02-deep-dive/C-ast.md).

Parser가 하는 일:
- **문법 규칙 적용**: Java Language Specification(JLS)의 grammar(BNF) 따라 매칭
- **연산자 우선순위**: `a + b * c`를 `(a + b) * c`가 아니라 `a + (b * c)`로 트리 구조에 반영
- **문법 오류 검출**: `int = ;` 같은 깨진 코드면 여기서 컴파일 에러
- **AST 노드 생성**: 각 노드는 자바 클래스 (`JCVariableDecl`, `JCBinary` 등)

위치: `com.sun.tools.javac.parser.JavacParser`

> 💡 자바는 **recursive descent parser** — 함수가 자기 자신을 부르면서 트리를 만드는 가장 단순한 방식.

#### 1.3 Annotation Processing — Lombok이 마법을 부리는 곳

> **Annotation Processor = "AST가 만들어진 직후에 끼어들어 코드를 추가/변환하는 플러그인"**.

실제 사례:

| 처리기 | 어노테이션 | 하는 일 |
|---|---|---|
| **Lombok** | `@Getter`, `@Setter`, `@Data` | AST에 직접 getter/setter 메서드 노드 삽입 |
| **MapStruct** | `@Mapper` | DTO ↔ Entity 변환 코드를 별도 `.java` 파일로 생성 |
| **Dagger / Hilt** | `@Inject`, `@Module` | DI 그래프 코드 생성 |
| **Hibernate JPA Meta** | `@Entity` | `Person_.java` 같은 metamodel 클래스 생성 |
| **AutoValue / Immutables** | `@Value.Immutable` | 불변 클래스 구현체 생성 |

처리 흐름:
```
[AST 1차 생성]
     │
     ▼
[Annotation Processor 라운드 1]
  - @Getter 발견 → getter 메서드를 AST에 추가
  - @Mapper 발견 → 새 .java 파일 생성
     │
     ▼
[새 .java가 생겼다면 다시 Lex+Parse]
     │
     ▼
[Annotation Processor 라운드 2]
  - 새 파일의 어노테이션 처리
     │
     ▼
[더 생성된 코드 없으면 종료]
```

**중요 포인트**:
- 라운드를 **반복**한다. 처리기가 새 코드를 생성하면 그 코드도 다시 처리됨
- Lombok은 **공식 API가 아닌 내부 javac AST를 직접 건드림**. 그래서 "마법"처럼 보임 (정식 처리기는 보통 새 파일만 생성)

위치: `com.sun.tools.javac.processing.JavacProcessingEnvironment`

> 💡 IDE에서 Lombok 플러그인을 따로 깔아야 하는 이유: javac는 알아도 IDE는 모르니까. IntelliJ/Eclipse가 코드를 분석할 때 Lombok이 어떤 메서드를 만들어줬는지 알려줘야 자동완성·"go to definition"이 동작.

#### 1.4 Semantic Analysis & Bytecode Generation

Annotation processing이 끝나면 마지막 두 단계:

**(a) Semantic Analysis (의미 분석)**

> "AST가 문법은 맞지만, **의미가 맞나**?"를 검사.

- **타입 검사**: `int x = "hello"` → 컴파일 에러
- **스코프 검사**: 정의 안 된 변수 사용 → 에러
- **흐름 분석 (Flow Analysis)**: 반환값 누락, 도달 불가 코드, definite assignment(`final` 변수가 한 번만 할당되는가)
- **예외 검사**: checked exception을 `throws`로 선언했나
- **이름 해결 (Symbol Resolution)**: `System.out.println`에서 `System`이 어느 패키지의 어느 클래스인지 결정

이 단계에서 AST의 각 노드에 **타입 정보가 부착**된다 (`a` Identifier 노드에 "이건 int 타입" 같은 메타데이터).

**(b) Desugar (당분 제거)**

> "문법적 설탕(syntactic sugar)을 풀어쓰는 단계".

자바엔 "사람 쓰기 좋게 만든 단축 표기"가 많다. 이걸 더 단순한 형태로 변환:

| 문법 설탕 | 풀어쓰기 |
|---|---|
| `for (X x : list) { ... }` | `Iterator<X> it = list.iterator(); while(it.hasNext()) { X x = it.next(); ... }` |
| `() -> doStuff()` (람다) | `invokedynamic` + `LambdaMetafactory` |
| `String s = "a" + b + "c"` | `StringBuilder` 또는 `StringConcatFactory` (JDK 9+) |
| `try-with-resources` | `try-finally`에 `close()` 호출 |
| `switch expression` | `switch statement` + `yield` |
| Generics | type erasure (런타임에 raw type) |

이 단계 끝나면 AST가 훨씬 "기계적"인 형태가 된다.

**(c) Bytecode Generation**

> "Desugar된 AST를 후위순회하면서 bytecode 명령어를 차례로 emit".

`int c = a + b` AST를 후위순회:
```
1. left subtree 방문  → iload_1 emit  (a를 스택에 push)
2. right subtree 방문 → iload_2 emit  (b를 스택에 push)
3. + 연산 노드 처리   → iadd emit     (스택 top 둘 더해서 push)
4. assignment 노드   → istore_3 emit (스택 top을 c에 저장)
```

결과: `1B 1C 60 3E` 4바이트.

이때 동시에:
- **Constant Pool 채우기**: 메서드 참조, 문자열 리터럴 등을 CP에 등록하고 인덱스로 참조
- **Stack Map Frame 계산**: 각 분기점에서 operand stack 상태를 기록 (검증기 빠르게 돌리기 위함)
- **Line Number Table**: 디버거가 "이 bytecode가 .java의 몇 줄에 해당하는가"를 알도록

최종 산출물: `.class` 파일 1개.

위치: `com.sun.tools.javac.jvm.Gen`, `ClassWriter`

#### 왜 4단계로 쪼갰나

답: **각 단계가 한 가지 일만 하면 (a) 재사용성·확장성이 좋고, (b) 외부 도구가 끼어들 수 있어서**.

- **Lexer 재사용**: IDE의 syntax highlighting, code formatter도 같은 lexer를 씀
- **Parser 재사용**: AST는 javac만 쓰는 게 아님. Lombok, IntelliJ, ErrorProne 모두 javac AST API를 호출
- **Annotation Processor 끼어듦**: 4단계로 쪼개졌기 때문에 "AST 만들어진 다음, bytecode 생성 전"에 외부 코드가 끼어들 수 있음 → Lombok/Dagger 생태계 가능
- **Semantic Analysis 분리**: 타입 검사 알고리즘이 복잡한데, AST 생성과 섞으면 디버깅 불가능

> 더 깊은 javac 내부 구조(`JavaCompiler.compile()`의 실제 코드)는 [§ 4단계: 내부 구현](#-4단계-내부-구현-hotspot)의 `javac는 JVM이 아니다` 항목 참고.

---

### Stage 2 — `.class` 파일: 바이트코드의 컨테이너

`.class` 파일은 단순한 "바이트코드 덤프"가 아니라 **잘 정의된 컨테이너 포맷**이다. 클래스의 메타데이터(상수 풀, 필드, 메서드 시그니처)와 각 메서드의 바이트코드를 한 파일에 묶는다.

> 바이트코드의 1바이트 opcode 구조 자체는 → [부록 D — opcode 디스패치 메커니즘](./02-deep-dive/D-opcode-dispatch.md)에 자세히.

#### ClassFile 포맷 (.class)

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

#### major_version 매핑

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

#### `javap -c -p` 실제 출력 해석

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

---

### Stage 3 — ClassLoader: `.class`를 메모리로 (가장 헷갈리는 단계)

> **ClassLoader = ".class 파일을 byte[]로 읽고, 검증하고, 메모리에 클래스 객체로 등록하는 컴포넌트"**.
>
> 단순히 "파일을 읽는다"가 아니다. **JVM 스펙이 정의한 3단계**(Loading → Linking → Initialization)를 거친다.

![ClassLoader 3단계 + 부모 위임](./_excalidraw/02b-classloader-flow.svg)

> 편집: [02b-classloader-flow.excalidraw](./_excalidraw/02b-classloader-flow.excalidraw)

#### 3.1 Loading — byte[]를 메모리로

질문: "**.class 파일이 디스크에 있는데, 어떻게 JVM 메모리에 들어가나?**"

답: ClassLoader가 다음 중 하나의 방법으로 byte[]를 얻는다:
- **파일 시스템**: `~/.m2/repository/.../foo.jar` 안의 `Foo.class`를 읽음
- **네트워크**: 옛 애플릿/RMI는 HTTP로 받았음 (→ [§ 역사 — 애플릿](#사라진-시나리오-애플릿) 참고)
- **메모리 내 생성**: 동적 프록시, ASM/Byte Buddy로 런타임 생성한 byte[]
- **부모 ClassLoader에 위임**: 자기가 못 찾으면 부모에게 부탁 (아래 "부모 위임 모델")

읽어들인 byte[]는 **검증되지 않은 상태**다. 다음 단계로 넘긴다.

#### 3.2 Linking — 3단계로 쪼개진다

JVM 스펙 §5.4. Linking은 **3개 부속 단계**:

**(a) Verification (검증)**

> "이 bytecode가 안전한가?"를 점검.

- Magic number가 `0xCAFEBABE`인가?
- Constant Pool 인덱스가 범위 안인가?
- 모든 메서드의 operand stack이 underflow/overflow하지 않는가?
- final 클래스를 상속하지 않는가?
- private 필드를 외부에서 직접 건드리지 않는가?
- 타입이 안 맞는 캐스팅이 없는가?

검증 실패 → `VerifyError`. 이게 1995년 애플릿 보안 모델의 핵심이었다.

JDK 7+는 **StackMapTable**(`.class`에 미리 계산돼 있음)을 이용해 검증을 빠르게 한다. 자세한 건 [Q5 꼬리질문](#q5-killer-javap--v의-출력에서-stack2-locals1은-무슨-뜻이고-그-값은-어떻게-결정되나요)에.

**(b) Preparation (준비)**

> "static 필드를 기본값으로 초기화".

```java
class Foo {
    static int x = 42;
    static String name = "hello";
}
```

Preparation 단계에선:
- `x = 0` (int 기본값)
- `name = null` (참조 기본값)

**아직 `42`, `"hello"` 안 들어감**. 이건 Initialization 단계의 일.

**(c) Resolution (해결)** — 게으르게(lazy)

> "Constant Pool의 심볼 참조를 실제 참조로 바꾸기".

`.class`엔 `"java/lang/String"` 같은 **문자열 형태의 심볼**이 들어있다. 이걸 진짜 `String` 클래스의 메모리 주소·메서드 슬롯 번호로 바꾸는 게 Resolution.

JVM 스펙은 **lazy**를 허용. HotSpot은 메서드가 처음 호출될 때, 필드가 처음 접근될 때 그제서야 resolve한다.

#### 3.3 Initialization — `<clinit>` 실행

> "static 초기화 블록과 static 필드 할당 코드를 실행".

```java
class Foo {
    static int x = 42;          // ← 여기
    static int y;
    static { y = x * 2; }       // ← 여기
}
```

이 두 줄을 모은 **`<clinit>`** ("class initializer")이라는 특수 메서드가 자동 생성돼 있다. Initialization 단계에서 이걸 실행:
```
x = 42;
y = x * 2;   // y = 84
```

**Initialization 트리거** (JVM 스펙 §5.5):
- `new Foo()` 첫 호출
- `Foo.staticMethod()` 첫 호출
- `Foo.STATIC_FIELD` 첫 접근 (단, compile-time constant는 제외 — inline됨)
- `Class.forName("Foo")` 호출
- 서브클래스가 초기화될 때 부모도 (재귀적)

> 💡 면접 단골: "**클래스 로드 ≠ 초기화**". Loading은 한참 전에 일어났을 수 있고, Initialization은 처음 쓸 때까지 미뤄진다.
>
> 예: `Class.forName("Foo", false, ...)`로 로드만 하고 초기화는 안 시키는 것도 가능.

#### 부모 위임 모델 (Parent Delegation)

JVM 안에는 ClassLoader가 **여러 개** 있다. 위 SVG 오른쪽의 트리가 이 구조 — 자식이 부모에게 먼저 물어보는 위임 흐름.

<details>
<summary>🔎 ASCII 버전 (트리)</summary>

```
Bootstrap ClassLoader   (JVM 자체. java.lang.*, java.util.* 로드. C++로 구현)
       ↑
Platform ClassLoader    (구 Extension. JDK 9+. java.sql, java.xml 등 모듈)
       ↑
Application ClassLoader (= System ClassLoader. 클래스패스/모듈패스에서 로드)
       ↑
[Custom ClassLoader 1] [Custom ClassLoader 2]   (Tomcat 웹앱별, OSGi 번들별 등)
```

</details>

클래스를 로드할 때:
1. **자식이 부모에게 먼저 물어봄** ("이 클래스 갖고 있어?")
2. 부모가 없으면 또 그 부모에게
3. 최상단(Bootstrap)도 없으면 그제서야 자식이 직접 찾음

**왜 이런 구조?**
- **보안**: 사용자가 `java.lang.String`을 위조해도 Bootstrap이 먼저 로드해버리니 안전
- **공유**: `java.lang.Object`는 어디서나 같은 인스턴스 → 메모리 절약
- **격리**: Tomcat이 웹앱마다 다른 ClassLoader를 줘서 같은 클래스의 다른 버전을 같은 JVM에서 돌릴 수 있음

#### Loading 끝나면 Metaspace에 무엇이 들어가나

`.class`를 byte[]로 읽었지만 **그대로 들고 있지 않는다**. JVM이 자기 내부 구조로 변환해서 **Metaspace**(클래스 메타데이터 영역)에 저장:

- **Class 객체** (`java.lang.Class` 인스턴스 1개)
- **Constant Pool** (resolved된 형태로 변환)
- **메서드 메타데이터** (시그니처, bytecode, exception table, 카운터, MethodData)
- **필드 레이아웃** (오프셋, 타입, modifier)
- **vtable / itable** (가상 호출 디스패치용)

> 💡 JDK 7까지는 **PermGen**(힙의 한 영역, 크기 고정), JDK 8부터 **Metaspace**(Native 메모리, OS 한도까지 확장 가능). OOM이 덜 일어남.

---

### Stage 4 — Interpreter: 첫 실행은 한 줄씩 해석

#### 메서드가 처음 호출되는 순간

```java
foo.bar();   // 처음 호출
```

JVM이 하는 일:
1. `foo`의 클래스에서 `bar` 메서드 메타데이터 찾기 (vtable lookup)
2. 그 메서드의 entry point가 어디인지 확인
   - 아직 JIT 컴파일 안 됨? → **인터프리터 entry**로
   - 이미 컴파일됨? → **Code Cache의 native entry**로 (Stage 6에서 자세히)
3. 인터프리터로 가는 경우 → Template Interpreter의 메서드 시작점으로 점프

#### Template Interpreter가 받아서 디스패치 시작

메서드 시작 시:
- **operand stack** 초기화 (메서드의 `max_stack`만큼 공간 확보)
- **local variable table** 초기화 (`max_locals`만큼)
- **pc (program counter)** = 메서드 bytecode의 0번 오프셋

그 다음은 **무한 루프** (이 루프 자체가 어셈블리로 generate돼 있음):
```
1. pc가 가리키는 opcode 1바이트 읽기
2. 점프 테이블에서 그 opcode의 핸들러 어셈블리 주소 찾기
3. 그 주소로 점프 → 핸들러 실행
4. 핸들러 끝에서 pc 증가하고 1번으로 돌아감
```

> Template Interpreter가 부팅 시점에 자기 자신을 어셈블리로 generate하는 메커니즘, opcode 핸들러 점프 테이블의 작동 원리는 → [부록 A](./02-deep-dive/A-interpreter-implementations.md) + [부록 D](./02-deep-dive/D-opcode-dispatch.md).

#### 카운터 누적 → JIT 트리거

핸들러가 실행될 때마다:
- 메서드 entry에 진입 → **invocation counter ++**
- 백워드 점프(루프 회전) → **back-edge counter ++**

카운터가 임계치를 넘으면 **JIT 컴파일 큐에 메서드 제출**. 인터프리터는 계속 실행하면서, 백그라운드 컴파일러 스레드가 native code를 만들어둠. 다음번 호출부턴 자동으로 native로 감.

> 카운터 임계치와 MethodData 구조는 → [부록 E — JIT 5가지 실측 최적화](./02-deep-dive/E-aot-jit-optimizations.md)의 "카운터 시스템" 절.

---

### Stage 5 — JIT 컴파일러: C1과 C2

> JIT = **메서드 단위로** bytecode를 native code로 변환하는 컴파일러. HotSpot은 두 종류를 둔다 — **C1과 C2**.

#### 5.1 C1 — Client Compiler (빠른 컴파일)

**설계 의도**: "빠르게 컴파일해서 일단 native 성능을 얻자. 최적화는 적당히."

**원래 이름**: HotSpot Client VM. 데스크탑 클라이언트 앱(스윙)에서 **시작이 빨라야 한다**는 요구로 만들어짐.

**IR (Intermediate Representation) 구조**:
- **HIR (High-level IR)** — bytecode와 비슷하지만 SSA(Static Single Assignment) 형태. value-based
- **LIR (Low-level IR)** — 어셈블리에 가까운 형태. register와 명령어 형태

**알고리즘**:
- **Linear Scan Register Allocation** — register를 빠르게 배정. 최적은 아니지만 O(n)
- 단순한 최적화: constant folding, null check 제거, 명백한 devirtualization

**컴파일 시간**: 메서드당 **1~10 ms**

**결과 성능**: 인터프리터의 ~5~10배. C2의 ~50~70% 수준

위치: `src/hotspot/share/c1/`

#### 5.2 C2 — Server Compiler (공격적 최적화)

**설계 의도**: "**컴파일은 오래 걸려도 좋다. 일단 가장 빠른 native code를 만들어라.**"

**원래 이름**: HotSpot Server VM. 서버 앱(JBoss 등)에서 **throughput이 최우선**이라는 요구로 만들어짐.

**IR 구조**:
- **Sea of Nodes** — 1999년 Cliff Click 박사 논문. **Control flow와 Data flow가 한 그래프에 통합**된 IR
- 노드들이 의존성만으로 연결, 위치는 스케줄링 단계에서 결정

**최적화 패스 (20개 이상)**:

| 패스 | 무엇을 하나 |
|---|---|
| **Inlining** | 작은 hot 메서드 본문을 호출 사이트에 끼워넣음 |
| **GVN (Global Value Numbering)** | 같은 계산 재사용 |
| **Escape Analysis** | 메서드 밖으로 안 새는 객체를 스택/register로 |
| **Scalar Replacement** | 객체를 필드별 register로 분해 |
| **Loop Unrolling** | 루프를 4/8배 펼침 |
| **Vectorization (SuperWord)** | SIMD로 변환 (AVX, NEON) |
| **Range Check Elimination** | 배열 인덱스 검사 제거 |
| **Devirtualization** | 가상 호출을 정적 호출로 |
| **Lock Elision** | 경합 없는 락 제거 |

**알고리즘**:
- **Graph Coloring Register Allocation** (Chaitin 알고리즘) — 최적이지만 O(n²) 이상
- **Profile-guided optimization** — MethodData에서 받은 실측 데이터로 분기/타입 가정

**컴파일 시간**: 메서드당 **10~수백 ms**

**결과 성능**: C1의 ~1.5~3배. C/C++ AOT와 동급이거나 일부 더 빠름

위치: `src/hotspot/share/opto/`

> C2가 실제로 활용하는 5가지 실측 정보(inlining/devirt/branch prediction/EA/vectorization)의 코드 예시 → [부록 E](./02-deep-dive/E-aot-jit-optimizations.md).

#### 5.3 C1 vs C2 — 나란히 비교

| 축 | C1 (Client) | C2 (Server) |
|---|---|---|
| **목표** | 빠른 컴파일 | 최고 성능 |
| **IR** | HIR + LIR (선형) | Sea of Nodes (그래프) |
| **Register Allocation** | Linear Scan O(n) | Graph Coloring O(n²+) |
| **최적화 깊이** | 가벼움 (10개 미만) | 공격적 (20개 이상) |
| **컴파일 시간** | 1~10 ms | 10~수백 ms |
| **생성 코드 크기** | bytecode의 3~5배 | 10~30배 (inline 때문) |
| **Profile 활용** | 일부 | 전적으로 의존 |
| **언제 트리거** | 카운터 ≥ ~2000 (Tier 3) | 카운터 ≥ ~15000 (Tier 4) |
| **워밍업 단계** | 1차 | 2차 (peak) |
| **Deopt 가능?** | ✅ | ✅ |

#### 5.4 Tiered Compilation — C1과 C2가 협업하는 방식 (5단)

![Tiered Compilation 5단 사다리](./_excalidraw/02c-tiered-compilation.svg)

> 편집: [02c-tiered-compilation.excalidraw](./_excalidraw/02c-tiered-compilation.excalidraw)

**일반적 승격 경로**: L0 → L3 → L4 (대부분 메서드)
**Trivial 메서드**: L0 → L1 (computed by `is_trivial` heuristic)
**C2 큐 막힘 시**: L0 → L2 → L3 → L4 (C2가 바빠 미뤄지면 L2로 우회)

<details>
<summary>🔎 ASCII 버전</summary>

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

</details>

#### 왜 두 컴파일러를 둘 다 두나

**옵션 A: C2만 쓰기**
- 컴파일이 느려서 시작이 느림. 메서드 호출 1만 번 동안 인터프리터만 도니까 warmup이 김
- 또 컴파일 결과가 한 번에 너무 큼 → Code Cache 부담

**옵션 B: C1만 쓰기**
- Peak throughput이 부족 → 서버에서 늘 C/C++보다 느림

**옵션 C (HotSpot의 선택): 둘 다 쓰기**
- C1: warmup 단계의 native 코드를 빠르게 공급 (인터프리터 → C1)
- C2: 정말 hot한 메서드만 깊은 최적화 (C1 → C2)
- **Profile 데이터는 C1 단계(Level 3)에서 모음** → C2가 그 데이터로 공격적 가정 가능

> 더 깊은 꼬리질문은 [§ Q2-1: 왜 C1과 C2를 둘 다 두나요](#-꼬리-q2-1-왜-c1과-c2를-둘-다-두나요-c2만-쓰면-안-되나요)에.

---

### Stage 6 — Native Code: CPU가 직접 실행하는 코드

#### 6.1 Native code가 정확히 뭔가

> **Native code = 현재 CPU 아키텍처(x86_64, aarch64, ...)가 직접 디코딩해서 실행할 수 있는 기계어 명령어 시퀀스**.

JIT 컴파일이 끝나면 bytecode `iload_1 iload_2 iadd istore_3`가 이런 native code로 변환된다:

```asm
; x86_64 native code 예시 (단순화)
mov eax, [rbp-4]    ; 지역변수 1번 (a) → eax register
add eax, [rbp-8]    ; eax += 지역변수 2번 (b)
mov [rbp-12], eax   ; eax → 지역변수 3번 (c)
```

위 어셈블리는 인간 표기. 진짜 메모리엔 **기계어 바이트** (`8B 45 FC 03 45 F8 89 45 F4`)가 들어간다. CPU가 한 사이클당 하나씩 디코딩해서 실행.

**핵심 차이**:
- **bytecode** = JVM이 **해석**해야 실행됨. 플랫폼 독립
- **native code** = **CPU가 직접 실행**. 플랫폼 종속 (x86_64용은 ARM에서 못 돔)

> 어셈블리·기계어·bytecode 4층 구조는 → [부록 A — 인터프리터 구현 4가지 방식](./02-deep-dive/A-interpreter-implementations.md)의 1번 절에 더 자세히.

#### 6.2 어디에 저장되나 — Code Cache

JIT이 만든 native code는 JVM 프로세스의 **Code Cache**라는 메모리 영역에 저장된다.

![JVM 메모리 레이아웃 + Code Cache 내부](./_excalidraw/02e-jvm-memory.svg)

> 편집: [02e-jvm-memory.excalidraw](./_excalidraw/02e-jvm-memory.excalidraw)

JDK 9+는 **Segmented Code Cache** (3개 영역, 위 SVG 오른쪽):
- **Non-method**: 인터프리터 어셈블리, adapter, stub
- **Profiled methods**: C1이 만든 코드 (deopt 가능성 있음)
- **Non-profiled methods**: C2가 만든 코드 (안정)

기본 크기: **240MB**. `-XX:ReservedCodeCacheSize=512m`로 조정.

<details>
<summary>🔎 ASCII 버전</summary>

```
JVM 프로세스의 메모리 레이아웃:
┌─────────────────────────────┐
│  Heap (객체)                  │
├─────────────────────────────┤
│  Metaspace (클래스 메타)       │
├─────────────────────────────┤
│  Code Cache (native code) ★  │  ← JIT 산출물이 여기
├─────────────────────────────┤
│  JVM Stack (스레드별)          │
├─────────────────────────────┤
│  Native Stack                │
└─────────────────────────────┘
```

</details>

#### 6.3 메서드 호출이 native로 점프하는 흐름

가장 헷갈리는 부분. **같은 자바 코드 `foo.bar()`가 어떨 땐 인터프리터로, 어떨 땐 native로 가는 메커니즘**:

![메서드 호출 4-entry 디스패치](./_excalidraw/02d-method-call-entries.svg)

> 편집: [02d-method-call-entries.excalidraw](./_excalidraw/02d-method-call-entries.excalidraw)

**컴파일이 완료되면 entry pointer를 갈아끼운다**. 다음 호출부턴 자동으로 native로 감. 호출자 코드는 안 바꿈 — entry pointer 한 줄만 갱신.

<details>
<summary>🔎 ASCII 버전</summary>

```
foo.bar() 호출:
       │
       ▼
[메서드 메타데이터의 entry pointer 읽기]
       │
       │ ┌──────────────────────────────────────────────┐
       │ │ HotSpot이 각 메서드마다 들고 다니는 4개 entry: │
       │ │  _i2i_entry          - interp → interp 호출  │
       │ │  _i2c_entry          - interp → compiled 호출 (adapter) │
       │ │  _c2i_entry          - compiled → interp 호출 │
       │ │  _from_compiled_entry - compiled → compiled  │
       │ └──────────────────────────────────────────────┘
       │
       ▼
[해당 entry로 점프]
       │
       ├─→ 아직 컴파일 안 됨: 인터프리터 시작점으로
       │
       └─→ 컴파일 완료: Code Cache의 해당 메서드 native code로 직접 점프
```

</details>

#### 6.4 가상 호출은 어떻게? — Inline Cache

```java
Animal a = ...;
a.speak();   // Dog일 수도, Cat일 수도
```

가상 호출은 vtable lookup이 필요해서 느리다. JIT은 **Inline Cache (IC)** 라는 트릭을 씀:

```asm
; 첫 호출: vtable 조회 후 inline cache에 결과 캐싱
; 두 번째 호출부터:
cmp    [rax+8], 0x12345678   ; receiver의 클래스가 Dog 클래스인가?
jne    miss                   ; 다르면 vtable로 fallback (miss)
call   0xabcdef00            ; 맞으면 Dog.speak() 어셈블리로 직접 call
```

→ 첫 호출 후 같은 타입이 계속 오면 vtable 조회를 **건너뛴다**. 99% Dog로 들어오던 가상 호출이 정적 호출만큼 빨라지는 이유.

**Polymorphic Inline Cache (PIC)**: 2~3개 타입이 번갈아 들어오면 IC가 표 형태로 확장. 그 이상이면 megamorphic으로 떨어져서 vtable 사용.

#### Native code의 수명

- **만들어지면 Code Cache에 머문다** (메서드 unload, deopt, Code Cache eviction 전까지)
- **메서드 unload**: ClassLoader가 GC되면 → 그 클래스의 native code도 폐기
- **Deopt**: speculation이 깨지면 native code 무효화 → 인터프리터로 복귀 → 카운터 누적되면 재컴파일 (Stage 7)
- **Code Cache 가득 참**: 새 컴파일 거부, 기존 코드 evict 시작 → 성능 폭락 ([§ Q4](#q4-code-cache가-가득-차면-어떻게-되나요) 참고)

---

### Stage 7 — Deoptimization: 가정이 깨질 때 인터프리터로 복귀

C2(또는 C1)가 한 **가정(speculation)** 이 런타임에 깨지면 그 native code는 무효화되고 L0(인터프리터)로 떨어진다. 이게 **deoptimization**.

#### 깨지는 가정의 종류

| 트리거 | 예시 |
|---|---|
| **Class hierarchy change** | 새 서브클래스 로드 → CHA 가정 깨짐 → 가상 호출 inline 무효 |
| **Type speculation 실패** | 항상 `String`이 오던 곳에 `Integer`가 옴 → uncommon trap |
| **Class redefinition** | JVMTI agent가 클래스 재정의 |
| **Null check 실패** | 항상 non-null이라 가정 → null이 옴 |
| **Range check 실패** | 항상 in-range 가정 → out-of-bounds |

#### 일어나는 순서

```
[C2 native code 실행 중]
        │
        ▼ trap! (가정이 깨짐을 감지)
[Deoptimization 핸들러 진입]
        │
        ▼
[스택 프레임 재구성]
  - native code의 register 상태를 인터프리터 frame 모양으로 변환
  - inlined된 메서드들을 각각 별도 frame으로 펼침
        │
        ▼
[인터프리터로 점프]
  - 해당 메서드의 bytecode 위치(safe point)부터 재실행
        │
        ▼
[원래 native code는 무효 마킹]
  - 다음 호출자도 인터프리터/C1으로 fallback
  - 카운터 리셋, 충분히 hot해지면 재컴파일
```

> 💡 deopt 비용은 **공짜가 아니다**. 한 메서드에서 deopt가 자주 일어나면 그 메서드는 영영 C2 컴파일이 안 될 수도 있음 (`Tier4InvocationThreshold` 도달 못함). 자세한 비용 분석은 [§ Q3-1 꼬리질문](#-꼬리-q3-1-역최적화-비용은-얼마나-큰가요).

#### Deopt의 종류 두 가지

- **Eager deopt**: 즉시 발생. trap이 일어나면 그 자리에서 frame 재구성하고 인터프리터로
- **Lazy deopt**: 메서드가 반환할 때까지 미뤄짐. 활성 frame은 그대로 두고, 다음 호출부터 인터프리터로 가도록 entry pointer만 갱신

> Deopt 구현의 실제 C++ 코드는 [§ 4단계: 내부 구현](#-4단계-내부-구현-hotspot)의 `Deoptimization 구현` 항목에.

---

## 🧬 4단계: 내부 구현 (HotSpot)

> §3 구조에서 본 7-Stage가 HotSpot 코드베이스의 어디에 살고 있는지 — **파일 경로와 핵심 진입점**만 본다. 메커니즘의 깊은 설명은 부록으로.

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

### Template Interpreter — 핵심 코드 위치

위치: `src/hotspot/share/interpreter/templateInterpreter.cpp`

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
>
> 메커니즘 본격 설명 → [부록 A](./02-deep-dive/A-interpreter-implementations.md), [부록 D](./02-deep-dive/D-opcode-dispatch.md).

### C1 컴파일러 — 핵심 코드 위치

위치: `src/hotspot/share/c1/`

흐름:
1. Bytecode → HIR (High-level IR, value-based SSA)
2. HIR 단순 최적화 (constant folding, null check 제거, devirtualization)
3. HIR → LIR (Low-level IR)
4. Register allocation (Linear Scan)
5. Machine code emit

목표: **빠른 컴파일** (수 ms ~ 수십 ms). 최적화는 적당히.

### C2 컴파일러 — Sea of Nodes

위치: `src/hotspot/share/opto/`

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

> C2의 진짜 강점은 **inlining**, **escape analysis**, **branch prediction**. 작은 메서드를 마구잡이로 inline하면서 큰 메서드 하나처럼 만든 다음, 한꺼번에 최적화한다.
>
> 5가지 실측 최적화의 코드 예시 → [부록 E](./02-deep-dive/E-aot-jit-optimizations.md).

### Code Cache 구현

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

### 1995년 — 자바가 풀려야 했던 5가지 제약

Java(1991~1995)는 처음부터 "C++ 대체 범용 언어"가 아니었다. 시작은 **셋톱박스(Star7)·케이블 박스·인터랙티브 TV** 용 임베디드 언어였다. 1995년 인터넷 붐을 만나 "웹 브라우저 안에서 도는 애플릿"으로 방향이 바뀐다.

이 시나리오에 깔린 제약:

| 제약 | 의미 | JVM에 강제된 설계 |
|---|---|---|
| **이종 하드웨어** | 셋톱박스 칩이 SPARC/MIPS/x86 등 제각각 | bytecode = 가상 CPU 명령어 → 플랫폼 독립 |
| **네트워크 다운로드** | 바이너리는 인터넷으로 떨어짐 | `.class` 작아야 함 → 1바이트 opcode |
| **저사양 메모리** | 셋톱박스 RAM 수 MB, PC도 16~32MB | **인터프리터로 출발** (JIT은 메모리 큼) |
| **샌드박스 보안** | 신뢰 못 할 코드가 OS 망가뜨리면 안 됨 | BytecodeVerifier + SecurityManager + ClassLoader 격리 |
| **출시 속도** | 1995년에 시장을 만들어야 함 | "인터프리터로 먼저 출시, JIT은 나중에" 단계 전략 |

C/C++ 식 **AOT 네이티브 바이너리**로는 이걸 한 번에 풀 수 없었다. 그래서 **"bytecode + interpreter"** 라는 답이 나왔다.

> 더 깊은 트레이드오프(왜 AOT 안 썼나, 지금도 인터프리터 안 빼는 이유)는 → [부록 E — AOT vs JIT](./02-deep-dive/E-aot-jit-optimizations.md).

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

### 2018: JDK 11 — AOT 시도와 실패 (JEP 295)

- `jaotc` 도구: 클래스를 미리 native로 컴파일.
- 잘 안 쓰임. JDK 17에서 GraalVM Native Image로 사실상 대체. JDK 16에서 제거.

### 2020~: GraalVM Native Image의 부상

- 빌드 시점 전체 AOT. 시작 ms 단위, 메모리 1/10.
- Spring Boot 3.0+ 공식 지원. AWS Lambda·Cloud Run에서 표준화.
- 1995년에 거부했던 AOT가 2020년대 "콜드 스타트" 문제로 다시 복귀 → [부록 B](./02-deep-dive/B-jvm-implementations.md), [부록 E](./02-deep-dive/E-aot-jit-optimizations.md).

### 2023: JDK 21 — Generational ZGC

- ZGC가 generation을 가짐. Young/Old 분리.
- Code Cache와 직접 관련은 없지만, GC가 컴파일된 코드 내부의 oop 참조를 어떻게 처리하는지 변화.

### 사라진 시나리오: 애플릿

> **애플릿** = 1995~2017년 사이에 존재했던, 웹 브라우저 안에 박혀서 실행되던 작은 자바 프로그램. 지금은 사실상 사라진 기술이지만, **JVM 설계의 절반이 이걸 위해 만들어졌다**.

```html
<applet code="StockChart.class" width="600" height="400">
  이 브라우저는 자바를 지원하지 않습니다.
</applet>
```

브라우저가 페이지를 받으면 `.class`를 다운로드 → JVM 깨우기 → ClassLoader 로드 → BytecodeVerifier 검증 → SecurityManager 샌드박스 → 인터프리터로 `init/start/paint` 호출.

**오늘날 우리가 쓰는 JVM의 "이상해 보이는 설계들"이 대부분 애플릿 시대의 흔적**:
- `SecurityManager` (JDK 17 deprecated) — 샌드박스용으로 만들어진 것
- `ClassLoader`의 부모 위임 모델 — 여러 애플릿 격리용
- `Bytecode Verifier`의 엄격함 — 신뢰 못 할 다운로드 코드 전제
- `.class` 파일 포맷의 컴팩트함 — 모뎀 다운로드 전제
- **인터프리터 기반 출발** — 브라우저 안에 들어가야 했으니까

**왜 사라졌나**:
- 2005~2008: Flash·Ajax가 인터랙티브 웹의 대안으로
- 2010~2013: 보안 취약점 연속 폭발
- 2015: Oracle이 Java Plug-in deprecate 공식 선언
- 2017: JDK 9에서 Java Plug-in 제거
- 2018: JDK 11에서 `java.applet` 패키지 자체가 deprecated for removal

> 비유: **애플릿 = 90년대판 WebAssembly**. "브라우저 안에서, 신뢰 못 할 코드를, 안전하게, 어떤 OS에서도 돌리자"는 발상은 2020년대 WebAssembly가 거의 똑같이 풀고 있다.

### 미래: Project Leyden — Static Java

- AOT + closed-world assumption + size 감소
- 2024~ 단계별 도입 (JEP 483 AOT Method Profiling, JEP 514 AOT Code Caching)
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

## 📎 부록 — 깊이 들어가는 토글들

본문 직관/구조에서 잘라낸 깊은 토픽을 별도 파일로 분리해두었다. 각각 독립적으로 읽을 수 있다.

| 부록 | 다루는 것 | 본문 어디서 진입? |
|---|---|---|
| [A. 인터프리터 구현 4가지 방식](./02-deep-dive/A-interpreter-implementations.md) | Switch / Direct-Threaded / Template / AST. 어셈블리·미리 generate·점프 테이블·"매우 단순한 JIT" 개념 풀이 | §2 정의, §3 Stage 4, §4 Template Interpreter |
| [B. JVM 구현체 비교](./02-deep-dive/B-jvm-implementations.md) | HotSpot/OpenJDK/GraalVM/OpenJ9/Azul Zing/Android ART 차이. "GraalVM이 C2만 갈아끼운 이유" | §2 정의, §5 역사(2020~) |
| [C. AST 자료구조](./02-deep-dive/C-ast.md) | 코드를 트리로 표현. javac/Lombok/IDE 리팩토링의 출발점. Truffle이 AST를 IR로 쓰는 이유 | §3 Stage 1.2 Parsing |
| [D. opcode 디스패치 메커니즘](./02-deep-dive/D-opcode-dispatch.md) | opcode 1바이트, 핸들러 점프 테이블, branch predictor 학습, 직접 점프(goto)의 비용 | §3 Stage 2, §3 Stage 4 |
| [E. AOT vs JIT + JIT의 5가지 실측 최적화](./02-deep-dive/E-aot-jit-optimizations.md) | AOT 정의/트레이드오프, inlining/devirt/branch prediction/EA/vectorization, MethodData 라이프사이클 | §2 "왜 두 번 컴파일", §3 Stage 5, §5 역사 |

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
