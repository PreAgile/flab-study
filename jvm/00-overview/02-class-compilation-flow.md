# 02. 컴파일 흐름 — `.java`가 CPU 명령어가 되기까지

> "Java는 컴파일 언어인가요, 인터프리트 언어인가요?" 라는 함정 질문에 "둘 다요"라고 답할 수 있어야 한다.
> 더 정확히는: **"javac로 한 번, JIT으로 한 번 — 두 번 컴파일한다. 그 사이엔 인터프리트한다."**
> AOT(컴파일 언어)는 예측이고 JIT은 관측이다. JVM이 30년째 살아남은 핵심 비결이 바로 이 "한 번 더의 컴파일 = 실측 기반 최적화"다.

---

## 이 문서의 사용법

이 문서는 면접용 마인드맵을 따라 선형으로 펼친 구조다. 학습 순서 = 면접 답변 순서 = 백지에 그리는 순서.

1. **0장 마인드맵을 먼저 외운다** — 루트 한 문장 + 6가지 가지 + 각 가지의 키워드 3개.
2. **1~6장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 정확히 대응.
3. **7장 면접 워크플로우로 검증** — 질문을 보면 어느 가지로 가야 하는지 매핑.
4. **8장 꼬리질문으로 깊이 점검**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **".java가 CPU에 닿기까지 두 번 컴파일된다 — javac가 만든 ClassFile bytecode를, JVM이 Interpreter로 시작했다가 hot 메서드만 JIT으로 native code 변환한다. 이 'AOT(예측) + Interpreter(시작 빠름) + JIT(관측)' 조합이 1995년 이래 JVM의 본질이다."**

이 한 문장에서 모든 답변이 출발한다. 어떤 질문이 와도 이 문장부터 말하고 적절한 가지로 분기.

### 6개 가지 — 순서를 외운다

```
                  [ROOT: .java→CPU = 두 번 컴파일 + 사이엔 Interpreter]
                                    │
       ┌────────┬───────────┬───────┼───────┬───────────┬────────┐
       │        │           │       │       │           │        │
      ① WHY   ② javac     ③ Class  ④ Interp ⑤ JIT      ⑥ Deopt
   AOT/JIT/   4단계        File    카운터   C1+C2     가정 깨짐
   Interp     Lex→Parse→  포맷    →Tier 트리거 Tiered  →Interp
   3 비교     APT→Gen     컨테이너          (C1/C2)    복귀
       │        │           │       │       │           │
       │    ┌───┼───┐   ┌───┼───┐   PC      ┌───┼───┐   Eager/
    예측 vs Lex AST APT  Magic CP  Counter  C1빠름 C2깊은 Lazy
    관측  토큰화 트리 Lombok 메서드 ★      Linear Sea of  OSR
                          Bytecode         Scan   Nodes
```

### 가지별 핵심 키워드 (각 가지 3개씩만)

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① WHY 3 비교** | AOT = 예측 | JIT = 관측 | Interpreter = 변환 안 함 |
| **② javac 4단계** | Lex → Parser → APT → Gen | AST는 트리 | Lombok이 끼어드는 자리 |
| **③ ClassFile** | Magic 0xCAFEBABE | Constant Pool | bytecode + stack/locals |
| **④ Interpreter** | Template (HotSpot) | 카운터 누적 | hot 감지 → JIT 큐 |
| **⑤ JIT C1+C2** | C1 = ms 단위, 빠른 코드 | C2 = Sea of Nodes, 공격적 | Tiered L0~L4 |
| **⑥ Deopt** | speculation 깨짐 | 인터프리터로 복귀 | OSR 역방향 + Eager/Lazy |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 질문에 맞는 가지 1개 선택 → 그 가지의 키워드 3개 순서대로 설명 → 듣는 사람의 관심에 따라 인접 가지로 확장

"Java는 컴파일 vs 인터프리트?" → ① WHY. "javac가 뭐 하는지?" → ② javac. "ClassFile은?" → ③. "JIT 어떻게 트리거?" → ④→⑤. "Code Cache full 진단" → ⑤ 운영. "역최적화는?" → ⑥.

---

## 1. 가지 ①: WHY — AOT / JIT / Interpreter 3 비교

### 1.1 핵심 질문

> "Java는 컴파일 언어인가, 인터프리트 언어인가? 왜 두 번 컴파일하나?"

### 1.2 키워드 1 — 세 단어는 같은 축의 시점 차이

세 단어는 **"native code로 변환하는 시점이 언제냐"**라는 한 축 위에 있다.

| 방식 | 풀어 쓰기 | 변환 시점 | 대표 |
|---|---|---|---|
| **AOT** | Ahead-of-Time | 빌드 시 (실행 전 미리) | C, C++, Rust, Go, **GraalVM Native Image** |
| **JIT** | Just-in-Time | 실행 중 (필요한 시점에 딱) | **JVM(HotSpot)**, .NET, V8 |
| **Interpreter** | (약자 아님) | 변환 안 함 | 옛 Python, 1995년 Java 1.0 |

**JVM은 Interpreter + JIT 조합** — 둘 다 쓴다.

### 1.3 키워드 2 — AOT는 예측, JIT은 관측

**핵심 통찰**: AOT는 컴파일 시점에 "런타임에 무엇이 일어날지"를 예측해야 한다. 반면 JIT은 실제 실행을 본 결과(실측 프로파일)로 가정을 깐다 — AOT가 절대 못 하는 일.

JIT이 활용하는 **5가지 실측 정보**:

| 정보 | 활용 |
|---|---|
| **타입 프로파일** | virtual call의 receiver가 99% Dog 클래스라면 → devirtualize + inline |
| **분기 빈도** | if-else에서 한쪽이 95%면 → branch prediction hint |
| **null 빈도** | 항상 non-null이라 관측 → null check 제거 + speculation |
| **escape 정보** | 메서드 밖으로 안 새는 객체 → 스택/register로 (Escape Analysis) |
| **루프 카운트** | 어떤 루프가 평균 1000회 도는지 → unrolling/vectorization 결정 |

이 정보들은 `MethodData` 객체에 저장되고(Metaspace), C2가 그 데이터를 받아 공격적 가정을 깐다.

### 1.4 키워드 3 — 왜 두 번 컴파일하나 (트레이드오프 비교)

| 옵션 | 방식 | 장점 | 약점 |
|---|---|---|---|
| **A** | 전부 AOT | 시작 빠름 (C/C++ 방식) | 포팅 어려움, **동적 정보 활용 못 함** |
| **B** | 전부 인터프리트 | 단순 (1995 JVM 1.0) | **느림** (C++ 대비 20~50배) |
| **C** | AOT + 인터프리트 | 효율적 | **JVM 동적 기능**(reflection, dynamic class loading) 약함 |
| **D** | **javac(bytecode) + JIT** | 이식성 + 실측 최적화 + 동적 기능 | warmup 비용 + 메모리 |

**D가 현재 JVM 방식**. javac가 플랫폼 독립적 중간 표현(bytecode)으로 컴파일 → JVM이 런타임에 실측 프로파일로 추가 컴파일.

### 1.5 비유로 굳히기

> **인터프리터** = 동시통역사. 한 문장 듣고 한 문장 통역. 즉시. 하지만 같은 문장이 100번 나오면 100번 통역.
> **JIT** = 번역가. 한 문단을 모아서 정성껏 번역. 처음엔 느리지만 같은 문단이 또 나오면 즉시 재사용.
> **JVM은 두 사람 다 고용한다.** 처음엔 인터프리터로 빠르게 시작(warmup 빠름), 자주 나오는 문단은 번역가에게 맡긴다(steady-state 빠름).

### 1.6 bytecode가 stack-based인 이유

JVM의 bytecode는 register가 없다. 모든 연산이 operand stack에서 일어난다.
- **단순함**: 1바이트 opcode, 명령어 짧음.
- **플랫폼 독립**: register 개수가 CPU마다 다름 → 추상화에 유리.
- **검증 용이**: stack-based는 타입 추론이 simpler.

대가: 같은 연산에 더 많은 instruction → JIT이 register allocation을 새로 해야 함. 그래서 **JIT이 필수적**.

### 1.7 7-Stage 전체 흐름

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
                          └────────┬────────┘         │
                                   │ 더 hot           │
                                   ▼                  │
                          ┌─────────────────┐         │
                          │   C2 JIT        │         │
                          └────────┬────────┘         │
                                   ▼                  │
                          ┌─────────────────┐         │
                          │  Code Cache     │         │
                          └────────┬────────┘         │
                                   │ 직접 호출         │
                                   ▼                  ▼
                          ┌──────────────────────────────────┐
                          │             CPU                   │
                          └──────────────────────────────────┘

 ★ Deoptimization: speculation이 깨지면 Interpreter로 복귀
```

→ 더 깊이는 [부록 E — AOT vs JIT + JIT의 5가지 실측 최적화](./02-deep-dive/E-aot-jit-optimizations.md).

---

## 2. 가지 ②: javac — `.java` → bytecode의 4단계

### 2.1 핵심 질문

> "javac가 정확히 뭐 하나요? Lombok은 왜 작동하나요?"

### 2.2 키워드 1 — javac는 Java로 작성된 컴파일러다

> 함정: `javac`는 JDK 도구이지 JVM의 일부가 아니다. **Java로 작성된 컴파일러** (`src/jdk.compiler/share/classes/com/sun/tools/javac/`).
> 입력 `.java` 텍스트, 출력 `.class` 바이너리. 내부에서 4단계(엄밀히 5단계)를 거친다.

```
   .java 소스
        │
        ▼
   [1. Lexer (토큰화)]
        │
        ▼
   [2. Parser (AST 생성)]
        │
        ▼
   [3. Annotation Processor — Lombok, MapStruct, Dagger]
        │  (라운드 반복 가능 — 새 코드 생성되면 다시)
        ▼
   [4a. Semantic Analysis — 타입검사, scope, flow]
        │
        ▼
   [4b. Desugar — for-each, lambda, generics erasure]
        │
        ▼
   [4c. Bytecode Generation]
        │
        ▼
   .class 출력
```

`JavaCompiler.compile()`의 진짜 코드:
```java
parseFiles(sources);           // Lex + Parse
enterTrees(roots);             // 심볼 테이블 구축
processAnnotations(roots);     // APT 라운드 반복
attribute(todo);               // 타입 검사
flow(todo);                    // definite assignment, exception
desugar(todo);                 // lambda → invokedynamic, foreach → iterator
generate(todo);                // bytecode emit
```

### 2.3 키워드 2 — Lex → Parser (토큰 → AST)

**Lexer (= Tokenizer = Scanner)**: 글자 시퀀스를 의미 있는 단어 단위(토큰)로 자르는 단계.

```
"int c = a + b;"
       ↓ Lexer
[INT, IDENT(c), =, IDENT(a), +, IDENT(b), ;]
```

처리: 공백/주석 제거, 예약어 인식, 문자열/숫자 리터럴, `==`/`>=` 같은 다중문자 연산자. 위치: `com.sun.tools.javac.parser.Scanner`.

**Parser**: 토큰 시퀀스를 문법 규칙에 맞춰 AST(트리)로 조립.

```
[int, c, =, a, +, b, ;]
       ↓ Parser
VariableDeclaration
├─ type: int
├─ name: c
└─ init: BinaryOp(+)
         ├─ left:  Identifier(a)
         └─ right: Identifier(b)
```

처리: JLS grammar(BNF) 매칭, 연산자 우선순위(`a+b*c` → `a+(b*c)`), 문법 오류 검출, AST 노드 생성. **Recursive descent parser** — 함수가 자기 자신을 부르며 트리 생성. AST 본질은 → [부록 C](./02-deep-dive/C-ast.md).

### 2.4 키워드 3 — Annotation Processor (Lombok의 자리)

AST가 만들어진 직후, bytecode 생성 전에 끼어드는 플러그인 단계.

| 처리기 | 어노테이션 | 하는 일 |
|---|---|---|
| **Lombok** | `@Getter`, `@Data` | AST에 직접 getter/setter 메서드 노드 삽입 (★ 내부 API 사용) |
| **MapStruct** | `@Mapper` | DTO ↔ Entity 변환 코드를 별도 `.java` 파일로 생성 |
| **Dagger / Hilt** | `@Inject`, `@Module` | DI 그래프 코드 생성 |
| **AutoValue** | `@Value.Immutable` | 불변 클래스 구현체 생성 |

**라운드를 반복**한다. 처리기가 새 코드를 생성하면 그 코드도 다시 Lex+Parse → 또 처리. Lombok은 공식 API가 아닌 내부 javac AST를 직접 건드림 → 그래서 "마법"처럼 보임 (정식 처리기는 보통 새 파일만 생성).

> IDE에서 Lombok 플러그인을 따로 깔아야 하는 이유: javac는 알아도 IDE는 모르니까.

### 2.5 Semantic Analysis & Desugar & Bytecode Gen

**Semantic Analysis** — "AST가 문법은 맞지만 의미가 맞나?"
- 타입 검사, 스코프, 흐름 분석(definite assignment), 예외 검사, 이름 해결.
- 각 AST 노드에 타입 정보가 부착됨.

**Desugar** — 문법적 설탕을 단순한 형태로:

| 문법 설탕 | 풀어쓰기 |
|---|---|
| `for (X x : list)` | `Iterator + while` |
| `() -> doStuff()` (람다) | `invokedynamic + LambdaMetafactory` |
| `"a" + b + "c"` | `StringBuilder` 또는 `StringConcatFactory` (JDK 9+) |
| `try-with-resources` | `try-finally + close()` |
| Generics | type erasure (런타임에 raw type) |

**Bytecode Generation** — Desugar된 AST를 후위순회하면서 명령어 emit. 동시에 Constant Pool 채우기, Stack Map Frame 계산, Line Number Table 생성.

### 2.6 왜 4단계로 쪼갰나

- **Lexer 재사용**: IDE의 syntax highlighting, code formatter도 같은 lexer를 씀.
- **Parser 재사용**: AST는 Lombok, IntelliJ, ErrorProne 모두 javac AST API 호출.
- **Annotation Processor 끼어듦**: "AST 만들어진 다음, bytecode 생성 전"에 외부 코드가 끼어들 수 있음 → Lombok/Dagger 생태계 가능.
- **Semantic Analysis 분리**: 타입 검사 알고리즘이 복잡 → AST 생성과 섞으면 디버깅 불가.

---

## 3. 가지 ③: ClassFile — bytecode의 컨테이너 포맷

### 3.1 핵심 질문

> "`.class` 파일은 어떻게 생겼나요? 첫 4바이트가 뭐죠?"

### 3.2 키워드 1 — Magic + Version + ClassFile 구조

`.class` 파일은 단순한 "바이트코드 덤프"가 아니라 **잘 정의된 컨테이너 포맷**.

```
ClassFile {
    u4             magic;            // 0xCAFEBABE
    u2             minor_version;
    u2             major_version;    // JDK 21 = 65
    u2             constant_pool_count;
    cp_info        constant_pool[count - 1];   // 1-indexed!
    u2             access_flags;     // public, final, abstract
    u2             this_class;       // CP index
    u2             super_class;
    u2             interfaces_count;
    u2             interfaces[];
    u2             fields_count;
    field_info     fields[];
    u2             methods_count;
    method_info    methods[];        // ★ 각 메서드의 bytecode 여기
    u2             attributes_count;
    attribute_info attributes[];     // SourceFile, InnerClasses
}
```

major_version 매핑: JDK 5 = 49, JDK 8 = 52, JDK 11 = 55, JDK 17 = 61, JDK 21 = 65. 공식: `major - 44 = JDK 버전` (JDK 5+).

### 3.3 키워드 2 — Constant Pool (가장 중요한 메타데이터)

`.class`의 거의 모든 참조는 Constant Pool의 인덱스로 가리킨다. **1-indexed라는 함정** — 0번은 안 씀.

주요 tag:
- **Utf8** (1): UTF-8 인코딩 문자열 (modified UTF-8 — null byte를 2바이트로)
- **Integer/Float/Long/Double** (3~6): 숫자 리터럴. Long/Double은 **슬롯 2개 차지** (역사적 실수, JVMS §4.4.5: "a poor choice")
- **Class** (7): name_index
- **String** (8)
- **Fieldref / Methodref / InterfaceMethodref** (9/10/11)
- **NameAndType** (12)
- **MethodHandle / MethodType / InvokeDynamic** (15/16/18): JDK 7+
- **Module / Package** (19/20): JDK 9+

### 3.4 키워드 3 — bytecode + stack/locals

각 메서드의 Code attribute에는:
```
Code:
  stack=2, locals=1, args_size=1
  0: aload_0
  1: invokespecial #1     // Object."<init>":()V
  4: return
```

- **stack** = operand stack 최대 깊이.
- **locals** = local variable slot 수 (this 포함).
- **각 줄 첫 숫자** = bytecode 오프셋 (1바이트 opcode + 2바이트 operand → 0→1→4 점프).

**javac가 미리 계산**한다. JVM은 이 값을 보고 stack frame 크기를 한 번에 정확히 할당 → 동적 stack growth 없음. JDK 6+부터는 **StackMapTable**도 미리 채워 둠 → Verifier가 O(n) linear 검사로 끝.

→ bytecode 1바이트 opcode 구조, 디스패치 메커니즘은 → [부록 D](./02-deep-dive/D-opcode-dispatch.md).

### 3.5 `javap -c -p` 출력 해석

```java
System.out.println("Hello, World!");
```
↓
```
0: getstatic     #7      // System.out 필드 push
3: ldc           #13     // "Hello, World!" 문자열 push
5: invokevirtual #15     // PrintStream.println 호출
8: return
```

→ Constant Pool의 #7, #13, #15가 각각 어떤 심볼인지 `javap -v`로 보면 전체 그림.

---

## 4. 가지 ④: Interpreter — 첫 실행은 한 줄씩 해석

### 4.1 핵심 질문

> "ClassLoader가 메모리에 올린 다음, 첫 실행은 어떻게 시작되나요?"

### 4.2 키워드 1 — ClassLoader (3단계: Load → Link → Init)

> JVM 스펙 §5. 단순히 "파일 읽음"이 아니라 **Loading → Linking → Initialization**.

**Loading**: byte[] 얻기 (파일 시스템 / 네트워크(옛 애플릿) / 메모리 내 생성(동적 프록시) / 부모 위임).

**Linking** (3 부속 단계):
- **(a) Verification**: bytecode 안전성 점검 — Magic 검사, CP 인덱스 범위, operand stack underflow/overflow, final 상속 금지, 타입 캐스팅 검사. 실패 시 `VerifyError`.
- **(b) Preparation**: static 필드를 기본값으로 (`x=0`, `name=null`). 아직 `42`, `"hello"` 안 들어감.
- **(c) Resolution**: Constant Pool의 심볼 참조를 실제 참조로. **Lazy 허용** — HotSpot은 처음 호출/접근 시 resolve.

**Initialization**: `<clinit>` 실행. static 초기화 블록 + static 필드 할당 코드. 트리거:
- `new Foo()` 첫 호출
- `Foo.staticMethod()` 첫 호출
- `Foo.STATIC_FIELD` 첫 접근 (단, compile-time constant는 제외 — inline됨)
- `Class.forName("Foo")` 호출
- 서브클래스가 초기화될 때 부모도 (재귀적)

> **클래스 로드 ≠ 초기화** — Loading은 한참 전에 일어났을 수 있고, Initialization은 처음 쓸 때까지 미뤄짐.

**부모 위임 모델**:
```
Bootstrap CL          (JVM 자체, java.lang.*, C++로 구현)
       ↑
Platform CL           (구 Extension, JDK 9+, java.sql/xml 등 모듈)
       ↑
Application CL        (= System CL, 클래스패스/모듈패스)
       ↑
Custom CL             (Tomcat 웹앱별, OSGi 번들별)
```

자식이 부모에게 먼저 묻고 못 찾으면 자기가 찾음. 보안(`java.lang.String` 위조 방지) + 공유(같은 `Object` 인스턴스) + 격리(웹앱별 다른 버전).

Loading 끝나면 Metaspace에 들어가는 것: `java.lang.Class` 인스턴스, resolved Constant Pool, 메서드 메타데이터(시그니처/bytecode/카운터/MethodData), 필드 레이아웃, vtable/itable.

### 4.3 키워드 2 — Template Interpreter의 PC 디스패치 루프

메서드가 처음 호출되는 순간:
1. vtable lookup으로 `bar` 메서드 메타데이터 찾기.
2. entry pointer 확인 — JIT 안 됨? 인터프리터 entry. 됐다면 Code Cache native entry.
3. 인터프리터로 가는 경우, Template Interpreter의 메서드 시작점으로 점프.

메서드 시작 시: operand stack 초기화 (max_stack만큼), local variable table 초기화 (max_locals만큼), PC = bytecode 0번 오프셋.

**디스패치 루프** (이 루프 자체가 어셈블리로 generate돼 있음):
```
1. pc가 가리키는 opcode 1바이트 읽기
2. 점프 테이블에서 그 opcode의 핸들러 어셈블리 주소 찾기
3. 그 주소로 점프 → 핸들러 실행
4. 핸들러 끝에서 pc 증가하고 1번으로 돌아감
```

**Template Interpreter**가 부팅 시점에 자기 자신을 어셈블리로 generate하는 게 HotSpot의 특이점 (`src/hotspot/share/interpreter/templateInterpreter.cpp`):
```cpp
void TemplateTable::iadd() {
  __ pop_i(rax);
  __ addl(at_tos(), rax);  // x86 asm 한 줄을 generate
}
```

→ 4가지 인터프리터 방식(Switch/Direct-Threaded/Template/AST) 비교 → [부록 A](./02-deep-dive/A-interpreter-implementations.md).

### 4.4 키워드 3 — 카운터 누적 → JIT 트리거

핸들러 실행 시마다:
- 메서드 entry 진입 → **invocation counter ++**
- 백워드 점프(루프 회전) → **back-edge counter ++**

카운터가 임계치를 넘으면 **JIT 컴파일 큐에 메서드 제출**. 인터프리터는 계속 실행하면서 백그라운드 컴파일러 스레드가 native code를 만들어둠. 다음번 호출부턴 자동으로 native.

→ 카운터 임계치, MethodData 구조 → [부록 E](./02-deep-dive/E-aot-jit-optimizations.md).

---

## 5. 가지 ⑤: JIT C1 + C2 — Tiered Compilation

### 5.1 핵심 질문

> "왜 C1, C2 둘 다 두나요? Tiered 5단은 뭐죠?"

### 5.2 키워드 1 — C1 = 빠른 컴파일, C2 = 공격적 최적화

| 축 | C1 (Client) | C2 (Server) |
|---|---|---|
| **목표** | 빠른 컴파일 (ms 단위) | 최고 성능 (수십~수백 ms) |
| **IR** | HIR + LIR (선형) | **Sea of Nodes** (그래프) |
| **Register Allocation** | Linear Scan O(n) | Graph Coloring O(n²+) |
| **최적화 깊이** | 가벼움 (10개 미만) | 공격적 (20개 이상) |
| **컴파일 시간** | 1~10 ms | 10~수백 ms |
| **결과 성능** | Interp의 5~10배, C2의 50~70% | C/C++ 동급 또는 더 빠름 |
| **Profile 활용** | 일부 (Level 3에서 수집) | 전적으로 의존 |
| **Deopt 가능?** | 가능 | 가능 |

**C1 위치**: `src/hotspot/share/c1/`. HIR (value-based SSA) → LIR → Linear Scan RA → machine code.

**C2 위치**: `src/hotspot/share/opto/`. **Sea of Nodes** (1999 Cliff Click 박사 논문) — Control flow와 Data flow가 한 그래프에 통합. 노드들이 의존성만으로 연결, 위치는 스케줄링 단계에서 결정.

C2의 핵심 흐름:
```cpp
Parse                        // bytecode → Ideal Graph
IterGVN                      // Global Value Numbering
PhaseIdealLoop               // Loop opts (unrolling, vectorization)
Escape::do_analysis          // Escape Analysis
PhaseMacroExpand             // 매크로 노드 풀기
PhaseCFG::do_global_code_motion  // Schedule
PhaseChaitin::Register_Allocate  // Graph coloring RA
Output                       // Emit machine code
```

C2가 활용하는 5가지 실측 최적화:

| 패스 | 무엇을 |
|---|---|
| **Inlining** | 작은 hot 메서드 본문을 호출 사이트에 끼워넣음 |
| **Devirtualization** | 가상 호출 → 정적 호출 (CHA + type profile) |
| **Escape Analysis + Scalar Replacement** | 안 새는 객체를 스택/register로 분해 |
| **Branch Prediction (Profile-Guided)** | 자주 잡히는 분기를 fast path로 |
| **Vectorization (SuperWord)** | SIMD로 변환 (AVX, NEON) |
| **추가** | GVN, Loop Unrolling, Range Check Elimination, Lock Elision |

### 5.3 키워드 2 — Tiered Compilation L0 ~ L4

```
┌────────────────────────────────────────────────────────────┐
│  Level 0 │ Interpreter, no profiling                       │
│  Level 1 │ C1, no profiling   — trivial getter/setter      │
│  Level 2 │ C1, with counters  — C2 큐 막힘 시 우회           │
│  Level 3 │ C1, full profiling — MethodData 채움             │
│  Level 4 │ C2, with profile data — 공격적 최적화             │
└────────────────────────────────────────────────────────────┘
```

**일반 경로**: L0 → L3 → L4 (대부분 메서드).
**Trivial 메서드**: L0 → L1 (computed by `is_trivial` heuristic).
**C2 큐 막힘 시**: L0 → L2 → L3 → L4.

### 5.4 키워드 3 — 왜 두 컴파일러를 다 두나

**옵션 A — C2만**: 컴파일이 느려서 시작이 느림. 메서드 호출 1만 번 동안 인터프리터만 도니까 warmup이 김. 컴파일 결과가 한 번에 너무 큼 → Code Cache 부담.

**옵션 B — C1만**: Peak throughput 부족 → 서버에서 C/C++보다 늘 느림.

**옵션 C (HotSpot 선택) — 둘 다**:
- C1: warmup 단계의 native 코드를 빠르게 공급.
- C2: 정말 hot한 메서드만 깊은 최적화.
- **Profile 데이터는 C1 Level 3에서 모음** → C2가 그 데이터로 공격적 가정.

### 5.5 가상 호출 + Inline Cache (IC)

```java
Animal a = ...;
a.speak();  // Dog일 수도, Cat일 수도
```

가상 호출은 vtable lookup이 필요해 느림. JIT은 **Inline Cache** 트릭:
```asm
cmp    [rax+8], 0x12345678  ; receiver의 클래스가 Dog인가?
jne    miss                  ; 다르면 vtable로 fallback
call   0xabcdef00           ; 맞으면 Dog.speak() 직접 호출
```

→ 99% Dog로 들어오면 vtable 조회를 건너뜀 → 정적 호출만큼 빠름.

**Polymorphic Inline Cache (PIC)**: 2~3개 타입이 번갈아 들어오면 IC가 표 형태로 확장. 그 이상이면 megamorphic → vtable.

### 5.6 Code Cache (native code 저장소)

JDK 9+ **Segmented Code Cache**:
- **Non-method**: 인터프리터 어셈블리, adapter, stub
- **Profiled methods**: C1 코드 (deopt 가능성 있음)
- **Non-profiled methods**: C2 코드 (안정)

기본 크기 **240MB**. `-XX:ReservedCodeCacheSize=512m` 조정.

**Code Cache full** → JIT 중단 → 인터프리터로 fallback → 성능 5~10배 저하. 진단: `jcmd <pid> Compiler.codecache`, JFR `jdk.CodeCacheStatistics`. `-XX:+UseCodeCacheFlushing` 기본 on.

**Code Cache가 빨리 차는 상황**:
- 너무 많은 메서드 (수백만 줄 코드베이스)
- **dynamic class generation** (Mockito, Spring AOP/CGLib, ByteBuddy)
- frequent class redefinition (JRebel, JVMTI agents)
- Spring 앱은 특히 — `@Service`/`@Transactional` 빈마다 CGLib subclass 또는 JDK Dynamic Proxy → 각 proxy 메서드 JIT → Tiered Compilation은 각 메서드를 **두 번 (C1, C2)** 컴파일 → 2배 사용.

### 5.7 메서드 호출이 native로 점프하는 메커니즘

HotSpot은 메서드마다 4개 entry를 둠:
```
_i2i_entry           - interp → interp 호출
_i2c_entry           - interp → compiled 호출 (adapter)
_c2i_entry           - compiled → interp 호출
_from_compiled_entry - compiled → compiled
```

컴파일이 완료되면 **entry pointer를 갈아끼운다**. 다음 호출부터 자동으로 native로. 호출자 코드는 안 바꿈.

---

## 6. 가지 ⑥: Deoptimization — 가정이 깨질 때 인터프리터로 복귀

### 6.1 핵심 질문

> "C2가 깐 가정이 깨지면 어떻게 되나요? 비용은?"

### 6.2 키워드 1 — speculation이 깨지는 5가지 트리거

| 트리거 | 예시 |
|---|---|
| **Class hierarchy change** | 새 서브클래스 로드 → CHA 가정 깨짐 → 가상 호출 inline 무효 |
| **Type speculation 실패** | 항상 `String`이 오던 곳에 `Integer` 옴 → uncommon trap |
| **Class redefinition** | JVMTI agent가 클래스 재정의 (JRebel) |
| **Null check 실패** | 항상 non-null 가정 → null 옴 |
| **Range check 실패** | 항상 in-range 가정 → out-of-bounds |

### 6.3 키워드 2 — Deopt가 일어나는 순서

```
[C2 native code 실행 중]
        │
        ▼ trap! (가정 깨짐 감지)
[Deoptimization 핸들러 진입]
        │
        ▼
[스택 프레임 재구성]                ★ 핵심
  - native code의 register 상태를
    인터프리터 frame 모양으로 변환
  - inlined된 메서드들을 각각
    별도 frame으로 펼침
        │
        ▼
[인터프리터로 점프 → safe point부터 재실행]
        │
        ▼
[원래 native code는 무효 마킹]
  - 카운터 리셋, 충분히 hot해지면 재컴파일
```

가장 신기한 부분: native register에 흩어진 값들을 **bytecode 오프셋 기준의 stack frame**으로 재구성. 가능한 이유는 C2가 컴파일 시 **OopMap**과 **debug info**를 같이 저장하기 때문 (`src/hotspot/share/runtime/deoptimization.cpp`).

### 6.4 키워드 3 — Eager / Lazy + OSR

**Eager deopt**: 즉시 발생. trap이 일어나면 그 자리에서 frame 재구성하고 인터프리터로.
**Lazy deopt**: 메서드가 반환할 때까지 미뤄짐. 활성 frame은 그대로, 다음 호출부터 인터프리터로 가도록 entry pointer만 갱신.

**OSR (On-Stack Replacement)**: Deopt의 **역방향**. 인터프리터로 실행 중인 **루프**가 hot해지면 루프 도중에 컴파일된 코드로 전환. 메서드 입구가 아니라 백엣지(loop back-edge)에서 점프. 일반 JIT은 메서드 진입 시에만 가능하지만 OSR은 이미 시작된 메서드에 작용.

### 6.5 운영 진단

**Deopt 비용**: 한 번 일어나면 수 µs ~ 수십 µs (스택 재구성 + 명령어 캐시 미스). 빈번하면 P99 latency 폭증. 한 메서드에서 자주 deopt → 그 메서드는 영영 C2 컴파일 안 될 수도 (`Tier4InvocationThreshold` 도달 못함).

진단 명령:
```
-XX:+PrintCompilation
-XX:+PrintInlining
-XX:+PrintDeoptimization
JFR: jdk.Deoptimization 이벤트
```

---

## 7. 면접 답변 워크플로우

### 7.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "Java는 컴파일 vs 인터프리트?" | ① WHY (3 비교) | ⑤ JIT |
| "AOT vs JIT 차이?" | ① (예측 vs 관측) | ⑤ 5가지 실측 정보 |
| "javac가 뭐 하나?" | ② javac 4단계 | ② Lombok |
| "Lombok이 왜 작동하나?" | ② APT 라운드 | ② AST |
| "ClassFile 첫 4바이트?" | ③ Magic | ③ CP |
| "Long이 슬롯 2개 차지하는 이유?" | ③ CP | — |
| "lambda는 어떻게 컴파일?" | ② Desugar | invokedynamic |
| "JIT 트리거 시점?" | ④ 카운터 | ⑤ Tier |
| "C1과 C2를 왜 둘 다?" | ⑤ Tiered | ⑤ Profile |
| "Sea of Nodes가 뭔가?" | ⑤ C2 IR | — |
| "Inline Cache가 뭔가?" | ⑤ 가상 호출 | ⑥ deopt |
| "역최적화는?" | ⑥ Deopt | ⑤ speculation |
| "Code Cache full?" | ⑤ 운영 | dynamic CL |
| "stack=2 locals=1 의미?" | ③ Code attr | ④ StackMapTable |

### 7.2 답변 템플릿

> **루트 문장 한 줄 → 해당 가지 키워드 3개 순서대로 → 듣는 사람 표정 보고 인접 가지로**

예: "Java는 컴파일 언어인가요 인터프리트 언어인가요?"

> "둘 다입니다. 정확히는 **javac로 한 번 컴파일하고, JIT으로 한 번 더 컴파일하며, 그 사이엔 인터프리트**합니다. (← 루트)
> 첫째, **AOT, JIT, Interpreter는 'native code로 변환하는 시점이 언제냐'라는 한 축의 세 점**입니다. AOT는 빌드 시, JIT은 실행 중, Interpreter는 변환 안 함.
> 둘째, **AOT는 예측 컴파일이고 JIT은 관측 컴파일**입니다 — JIT은 실제 실행을 본 프로파일로 devirtualization, inlining, escape analysis 같은 공격적 가정을 깝니다. AOT는 절대 못 합니다.
> 셋째, **둘 다 쓰는 이유는 트레이드오프 균형**입니다. 전부 인터프리트는 20~50배 느리고, 전부 AOT는 동적 기능을 못 살리며, javac + JIT 조합이 이식성 + 실측 최적화 + 동적 기능을 다 잡는 답이었습니다."

→ 면접관이 "JIT은 뭐를 관측하죠?" 물으면 ⑤로, "AOT는 진짜 못 하나?" 물으면 GraalVM Native Image로.

---

## 8. 꼬리질문 트리 (가지별)

### Q1 [가지 ①]. `.java`가 어떻게 `.class`가 되고 어떻게 실행되나?

> javac가 .java를 Lex/Parse/타입검사/Bytecode Gen 거쳐 .class로. JVM이 ClassLoader로 메모리에 로드. Interpreter가 한 줄씩. hot 메서드는 C1/C2 JIT으로 native → Code Cache.

**🪝 Q1-1: .class 첫 4바이트?**
> `0xCAFEBABE`. James Gosling이 자주 가던 카페 이름.

**🪝🪝 Q1-1-1: 그 뒤엔?**
> minor/major version → constant_pool_count → CP 엔트리(1-indexed, 0번 안 씀) → access_flags → this/super → interfaces → fields → methods → attributes.

**🪝🪝🪝 Q1-1-1-1: Long/Double이 슬롯 2개 차지하는 이유?**
> JVM 초기 설계 실수. JVMS §4.4.5에 "in retrospect, a poor choice"라고 명시. 호환성 때문에 못 고침.

**🪝 Q1-2: lambda는 어떻게 컴파일?**
> JDK 8부터 **invokedynamic + LambdaMetafactory**. javac는 lambda 본문을 private static 메서드로 추출(`lambda$0`), invokedynamic 명령으로 호출 시점에 `LambdaMetafactory.metafactory` 부르고, factory가 **hidden class**를 동적 생성.

**🪝🪝 Q1-2-1: 왜 익명 클래스가 아니라 invokedynamic?**
> (1) 미래에 lambda 구현 바꿔도 bytecode는 그대로. (2) lazy: 메모리 효율. (3) JIT이 lambda body를 호출 사이트에 inline 가능. (4) invokedynamic 인프라가 JRuby/Scala가 이미 쓰던 것.

### Q2 [가지 ⑤]. Tiered Compilation 5단계?

> L0(Interp) → L3(C1 full profile) → L4(C2)가 메인. Trivial은 L0 → L1. C2 큐 막히면 L0 → L2 → L3 → L4. 전환은 invocation/back-edge counter가 임계치 넘을 때.

**🪝 Q2-1: 왜 C1과 C2 둘 다?**
> C2는 컴파일이 느림(수백 ms). 모든 메서드 C2면 warmup 느림. C1은 ms 단위 + 어느 정도 빠른 코드. C1 Level 3에서 profile 수집 → C2가 그 데이터로 더 공격적.

**🪝🪝 Q2-1-1: C2가 어떤 profile을 활용?**
> Branch frequency(prediction hint), Virtual call target(devirt + inline), Type profile, Null check 빈도, Loop iteration count. 모두 MethodData(Metaspace)에 저장.

### Q3 [가지 ⑥]. Deoptimization은 언제 어떻게?

> C2 가정이 깨질 때 — CHA 위반, type speculation 실패, null/range check 실패, class redefinition. 일어나는 법: trap → register/stack 재구성(debug info 기반) → 인터프리터로 점프 → 카운터 리셋 → 충분히 hot이면 재컴파일.

**🪝 Q3-1: Deopt 비용?**
> 1회 수 µs ~ 수십 µs. 빈번하면 P99 latency 폭증. 한 메서드에서 자주 deopt하면 그 메서드는 영영 C2 컴파일 안 될 수도. `-XX:+PrintDeoptimization` 또는 JFR `jdk.Deoptimization`로 감지.

**🪝🪝 Q3-1-1: OSR이 뭐?**
> **On-Stack Replacement**. 인터프리터로 실행 중인 루프가 hot해지면 루프 도중에 컴파일된 코드로 전환. 메서드 입구가 아닌 백엣지에서 점프. Deopt의 역방향. 구현은 인터프리터 frame → native frame 변환.

### Q4 [가지 ⑤]. Code Cache가 가득 차면?

> `CodeCache is full. Compiler has been disabled.` warning → 새 JIT 중단 → 기존 컴파일 코드는 계속 실행되지만 새 hot 메서드는 인터프리터만 → 5~10배 저하. 방지: `-XX:ReservedCodeCacheSize=512m`, `-XX:+UseCodeCacheFlushing`(기본 on), `jcmd Compiler.codecache` 모니터링.

**🪝 Q4-1: 가득 찰 만한 상황?**
> 너무 많은 메서드, dynamic class generation(Mockito, Spring AOP, CGLib, ByteBuddy), frequent class redefinition(JRebel, JVMTI), 너무 작은 ReservedCodeCacheSize.

**🪝🪝 Q4-1-1: Spring 앱이 빨리 차는 이유?**
> Spring AOP가 각 `@Service`/`@Transactional` 빈마다 CGLib subclass 또는 JDK Dynamic Proxy 생성 → 각 proxy 메서드도 JIT → 수천 클래스 × 수만 메서드 × Tiered의 2배 컴파일 = 폭발.

### Q5 (Killer) [가지 ③]. `javap -v`의 `stack=2, locals=1`은?

> operand stack 최대 깊이=2, local variable slots=1(this 포함). **javac가 미리 계산**해서 ClassFile Code attribute에 박아둠 → JVM이 frame을 한 번에 정확한 크기로 할당 → stack-based지만 frame allocation이 빠른 이유.

**🪝 Q5-1: 잘못된 값을 넣으면?**
> Verifier가 잡음. Linking 단계의 Verify가 각 bytecode 위치에서 stack 상태를 추론 → max_stack 초과 발견 시 `VerifyError`. JDK 6+ StackMapTable로 javac가 미리 채워둠 → JVM은 type 검사만 O(n) linear.

**🪝🪝 Q5-1-1: StackMapTable이 도입된 이유?**
> JDK 5까지의 verification은 **fixed-point iteration**으로 각 basic block의 타입을 수렴 → O(n²)~O(n³), 큰 메서드에서 느림. JDK 6+는 javac가 StackMapTable을 미리 채워 linear 검사로 끝. JDK 7부턴 필수 (`-target 1.7`+ class에서 StackMapTable 없으면 verify 실패).

### Q6 [가지 ①]. 역사적 5가지 제약과 그 흔적?

> 1995년 Java가 풀어야 했던 제약: **이종 하드웨어** → bytecode(가상 CPU); **네트워크 다운로드** → 작은 .class(1바이트 opcode); **저사양 메모리** → Interpreter 출발(JIT은 메모리 큼); **샌드박스 보안** → Verifier + SecurityManager + ClassLoader 격리; **출시 속도** → "인터프리터 먼저, JIT 나중" 단계 전략. 오늘날 SecurityManager(deprecated), 부모 위임 모델, Verifier 엄격성, `.class` 컴팩트함이 모두 이 시대의 흔적.

**🪝 Q6-1: 애플릿은 왜 사라졌나?**
> 2005~2008 Flash/Ajax 대안 부상 → 2010~2013 보안 취약점 폭발 → 2015 Oracle이 Java Plug-in deprecate → 2017 JDK 9에서 제거 → 2018 JDK 11에서 `java.applet` deprecated for removal. **애플릿 = 90년대판 WebAssembly** — 같은 발상을 2020년대 WASM이 다시 풀고 있음.

---

## 9. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 이내로 그릴 수 있다 (루트 + 6가지 + 각 키워드 3개)
- [ ] 가지 ① WHY: AOT/JIT/Interpreter의 시점 축을 그린다
- [ ] 가지 ① WHY: AOT=예측, JIT=관측 차이를 5가지 실측 정보로 설명한다
- [ ] 가지 ② javac: 4단계(Lex/Parse/APT/Gen)를 그리고 Lombok 자리를 가리킨다
- [ ] 가지 ② javac: Desugar에서 lambda → invokedynamic, foreach → iterator 변환을 말한다
- [ ] 가지 ③ ClassFile: Magic/CP/Code attribute의 구조를 그린다
- [ ] 가지 ③ ClassFile: stack/locals/StackMapTable의 의미와 javac의 책임을 설명한다
- [ ] 가지 ④ Interpreter: Loading/Linking/Init 3단계 + 부모 위임 모델을 그린다
- [ ] 가지 ④ Interpreter: Template Interpreter의 PC 루프 + 카운터 누적을 설명한다
- [ ] 가지 ⑤ JIT: C1 vs C2 비교표를 적고 Sea of Nodes를 말한다
- [ ] 가지 ⑤ JIT: Tiered 5단(L0~L4)과 일반/Trivial/C2-막힘 경로를 구분한다
- [ ] 가지 ⑤ JIT: Inline Cache + PIC + megamorphic 전환을 설명한다
- [ ] 가지 ⑤ 운영: Code Cache full 진단 + Spring AOP 폭발 원인을 말한다
- [ ] 가지 ⑥ Deopt: 5가지 trigger + Eager/Lazy + OSR을 구분한다
- [ ] 8장 꼬리질문 6개에 막힘없이 답한다

---

## 부록 — 깊이 들어가는 토글들

| 부록 | 다루는 것 | 본문 어디서 진입? |
|---|---|---|
| [A. 인터프리터 구현 4가지 방식](./02-deep-dive/A-interpreter-implementations.md) | Switch / Direct-Threaded / Template / AST | 가지 ④ |
| [B. JVM 구현체 비교](./02-deep-dive/B-jvm-implementations.md) | HotSpot/OpenJDK/GraalVM/OpenJ9/Azul/ART | 가지 ① |
| [C. AST 자료구조](./02-deep-dive/C-ast.md) | javac/Lombok/IDE 리팩토링의 출발점 | 가지 ② |
| [D. opcode 디스패치 메커니즘](./02-deep-dive/D-opcode-dispatch.md) | 1바이트 opcode + 점프 테이블 + branch predictor | 가지 ③, ④ |
| [E. AOT vs JIT + JIT의 5가지 실측 최적화](./02-deep-dive/E-aot-jit-optimizations.md) | inlining/devirt/branch pred/EA/vectorization | 가지 ①, ⑤ |

---

## 다음 단계

- → [03. JVM 아키텍처 큰 그림](./03-jvm-architecture-bigpicture.md): 이 챕터 단계가 JVM 4대 서브시스템 어디에 매핑되는지
- → 01-class-lifecycle: ClassLoader 부모 위임 + Verification/Preparation/Resolution/Init 풀버전
- → 03-execution-engine: Template Interpreter, C1, C2 풀버전

## 참고

- **JVMS §4 (ClassFile Format)**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html
- **JVMS §6 (Bytecode Instructions)**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html
- **Tiered Compilation (JEP 165)**: https://openjdk.org/jeps/165
- **Cliff Click — Sea of Nodes paper (1995)**: https://www.oracle.com/technetwork/java/javase/tech/c2-ir95-150110.pdf
- **HotSpot Glossary**: https://openjdk.org/groups/hotspot/docs/HotSpotGlossary.html
