# 01-03. Linking — Verify, Prepare, Resolve

> "ClassLoader가 클래스를 로드하면 끝"이라고 생각하면 절반만 안 것이다.
> Loading 다음에는 Linking이 있다. 그리고 이 단계가 JVM의 진짜 안전망이다.
> `.class` 파일을 신뢰할 수 없다는 가정 하에 JVM은 **타입 안전성을 수학적으로 증명**한다. Verifier가 없으면 Java의 "safe by construction" 가정이 무너진다.

---

## 이 문서의 사용법

이 문서는 **면접용 마인드맵**을 따라 선형으로 펼친 구조다. 학습 순서 = 면접 답변 순서 = 백지에 그리는 순서.

1. **0장 마인드맵을 먼저 외운다** — 루트 한 문장 + 5가지 가지 + 각 가지의 키워드 3개.
2. **1~5장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 정확히 대응.
3. **6장 면접 워크플로우로 검증**.
4. **7장 꼬리질문으로 깊이 점검**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"Linking은 ClassLoader가 끝낸 뒤 JVM 본체가 이어받는 3단계 — Verify(안전성 증명) → Prepare(static default) → Resolve(심볼릭→직접, lazy)다. 락은 안 잡고 사용자 코드도 실행하지 않는다. 그 다음이 Initialization."**

이 한 문장에서 모든 답변이 출발한다. 어떤 질문이 와도 이 문장부터 말하고 적절한 가지로 분기.

### 5개 가지 — 순서를 외운다

```
                  [ROOT: Linking = Verify + Prepare + Resolve, by JVM]
                                    │
       ┌──────────┬─────────────────┼─────────────────┬──────────┐
       │          │                 │                 │          │
      ① WHY     ② Verify          ③ Prepare         ④ Resolve   ⑤ 운영
   책임경계    안전성증명         static default    심볼릭→직접   에러+성능
   락없음      3 Pass            ConstantValue    lazy + cache  CDS/AOT
       │          │                 │                 │          │
       │     ┌────┼────┐        ┌───┼───┐         ┌───┼───┐    ┌──┼──┐
   loading→   Pass 1     ConstantValue inline   Lazy 시점    VerifyError
   linking→   format     일반 static    static  ResolvedRef CNFE/NCDFE
   init       Pass 2 의미 default(0)  final ★  vtable/itable IncompatChange
              Pass 3 BC                        invoke 5종    AppCDS/Leyden
              StackMapTable                                   -Xverify:none
              JDK6 가속                                       binary compat
```

### 가지별 핵심 키워드 (각 가지 3개씩만)

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① WHY 책임경계** | JVM 본체가 함 | 락 없음 | Loading 다음 / Init 이전 |
| **② Verify** | Pass 1 (format) | Pass 2 (semantic) | Pass 3 (bytecode + StackMapTable) |
| **③ Prepare** | static default | ConstantValue 예외 | 사용자 코드 X |
| **④ Resolve** | lazy + cache | invoke 5종 검색 규칙 | vtable / itable |
| **⑤ 운영** | VerifyError / NCDFE | binary compatibility | AppCDS / Leyden |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 질문에 맞는 가지 1개 선택 → 그 가지의 키워드 3개 순서대로 설명 → 듣는 사람의 관심에 따라 인접 가지로 확장

---

## 1. 가지 ①: WHY — 책임 경계와 라이프사이클 위치

### 1.1 핵심 질문

> "Linking은 누가 하고, 언제 일어나는가? ClassLoader와 무엇이 다른가?"

### 1.2 키워드 1 — JVM 본체가 한다 (ClassLoader 아님)

```
   .java ──javac──► .class
                       │
                       ▼
                   Loading                ← ClassLoader (02장)
                       │
                       ▼  ★ 이 챕터 ★
                   Linking
                   ├─ Verification       ← JVM 본체
                   ├─ Preparation        ← JVM 본체
                   └─ Resolution         ← JVM 본체
                       │
                       ▼
                   Initialization        ← JVM Initializer (04장)
                       │
                       ▼
                   Usage → Unloading
```

| 단계 | 주체 | 락 사용 | 비고 |
|---|---|---|---|
| Loading | ClassLoader | ClassLoader 자기 락 (parallel CL) | `defineClass()`까지 |
| **Verification** | **JVM 본체** | 락 없음 | Loading 직후 자동 |
| **Preparation** | **JVM 본체** | 락 없음 | static 필드를 **타입 default**로 |
| **Resolution** | **JVM 본체** | 락 없음 (ResolvedReference 캐시는 atomic) | 심볼릭 → 직접, 첫 사용 시점 |
| Initialization | JVM Initializer | ★ per-Class init lock + 12-step | `<clinit>` 실행 (04장) |

### 1.3 키워드 2 — Linking은 락을 잡지 않는다

자주 헷갈리는 두 가지:

1. **"Verification이 타입 안전성을 증명한다"는 정적 증명이지, 락이 필요한 일이 아니다**. Verification은 바이트코드를 **데이터로 읽어 분석**할 뿐 실행은 안 한다. 동시성 이슈 없음 → 락 없음. JLS 12.4.2의 12-step 락은 여기 등장하지 않는다.

2. **Preparation의 "default 값"과 Initialization의 "진짜 값"은 다른 단계**.
   - Preparation: `static int x;`의 메모리를 확보하고 `0`으로 채움. **타입 default**.
   - Initialization: `<clinit>`을 돌려 `x = 42;`로 교체. **의미 있는 값**.
   - Active Use가 init을 강제하는 진짜 이유는 "타입 안전성"이 아니라 **"default 0/null로는 비즈니스 로직이 깨지기 때문"** (04장 Active vs Passive Use 참조).

### 1.4 키워드 3 — Loading 다음 / Initialization 이전

부동산 거래 비유:
- **Loading** = 등기부등본 받아오기 (서류 입수)
- **Verification** = 서류 위조 검사 (인감 진위, 권리 관계)
- **Preparation** = 명의 이전 준비 (계좌 개설, 빈 칸 양식 만들기)
- **Resolution** = 실제 권리자 찾기 (등기부의 이름으로 실제 사람 매칭)
- **Initialization** = 입주 (가구 들이기, 사람 살기)

핵심 한 줄: **Linking은 ClassLoader가 끝낸 뒤 JVM 본체가 이어받는 단계. 락은 안 잡고 `<clinit>`도 안 돌린다. 다음 단계인 Initialization에서 비로소 락이 등장한다.**

---

## 2. 가지 ②: Verify — 안전성 증명

### 2.1 핵심 질문

> "Verifier는 무엇을 검증하고, 왜 그렇게 엄격하며, StackMapTable이 왜 도입됐는가?"

### 2.2 키워드 1 — Pass 1: ClassFile Format

```cpp
// classFileParser.cpp의 책임
- magic이 ClassFile signature와 일치
- major_version이 지원 범위 안
- CP의 모든 tag가 유효
- CP 인덱스가 범위 안 (1 ~ count-1)
- attributes의 length 일관성
- 각 method의 Code attribute 존재
```

실패: 파싱 중 즉시 `ClassFormatError`.

**주요 검사 항목의 의미**:
- **magic**: 파일 첫 4바이트로 "이게 진짜 .class인가" 식별 (01장 가지 ② 참조). 다른 값이면 `ClassFormatError` 즉시.
- **major_version**: JDK 8=52, 11=55, 17=61, 21=65. JVM이 자기보다 나중에 컴파일된 클래스는 못 실행 → `UnsupportedClassVersionError`.
- **CP tag 유효성**: 각 항목 첫 바이트가 JVMS §4.4가 정의한 tag 번호인지 확인 (Long/Double은 슬롯 2개 차지 함정 포함).
- **attribute length 일관성**: `attribute_length` 필드와 실제 데이터 크기 매칭.
- **method의 Code attribute**: 일반 메서드는 Code 필수, `abstract`/`native`만 예외.

### 2.3 키워드 2 — Pass 2: Semantic / Pass 3: Bytecode

#### Pass 2 — 의미적 일관성

```cpp
- super_class가 final이면 안 됨
- interface는 super_class가 java.lang.Object여야 함
- 모든 메서드 시그니처 형식 유효
- ACC_INTERFACE 클래스의 메서드는 ACC_ABSTRACT만 (default method 제외)
- 같은 시그니처의 메서드 중복 금지
```

#### Pass 3 — Bytecode 타입 안전성 (핵심)

**목표**: 모든 메서드의 모든 bytecode 위치에서 **타입 안전성을 증명**.

**증명할 것**:
1. 모든 instruction이 valid opcode.
2. 모든 instruction의 stack/locals 사용이 max_stack/max_locals 안.
3. 각 instruction이 받는 타입이 올바름 (`iadd`는 stack 위에 int 둘).
4. 메서드 종료 시 stack이 비었거나 반환 타입과 매칭.
5. 모든 분기 대상이 valid instruction 시작 위치.

> Verifier가 보장하는 것: **검증된 bytecode는 native crash(segfault, memory corruption)를 일으킬 수 없다**. 1995년 Java applet 시대에 untrusted 코드 실행을 위한 보안 모델의 기반. JVM 보안의 첫 방어선.

**Type System** (JVMS §4.10.1):
```
                 top
                  │
       ┌──────────┴──────────┐
   oneWord                twoWord
       │                     │
  ┌────┴────┐          ┌─────┴─────┐
 int      ref         long       double
```

각 stack slot과 local variable slot이 어떤 타입인지 추적.

### 2.4 키워드 3 — StackMapTable (JDK 6+ 가속)

#### 옛 방식 (JDK 5 이하) — Type Inference

각 메서드의 모든 instruction에서:
1. 입력 stack/locals 타입 상태 (예: `[int, ref]`).
2. instruction 실행 후 상태 계산.
3. 분기점에서 여러 진입 경로의 상태를 **merge** — 공통 supertype으로 통합.
4. **fixed-point iteration**: 변화 없을 때까지 반복.

복잡도: O(n²)~O(n³). 큰 메서드에서 매우 느림.

#### 새 방식 (JDK 6+) — StackMapTable

핵심 아이디어: **javac가 미리 계산해서 ClassFile에 적어둔다.**

`StackMapTable` attribute (Code attribute 안):
```
StackMapTable {
    u2 number_of_entries;
    StackMapFrame entries[];
}
```

각 `StackMapFrame`은 **basic block 시작점**의 stack/locals 타입 상태를 명시.

JVM Verifier:
1. 첫 instruction 초기 상태 = 메서드 파라미터 타입.
2. 다음 instruction마다 시뮬레이션 (한 단계씩).
3. 분기점 도달 시: 현재 상태가 ClassFile의 StackMapFrame과 일치하는지 확인.
4. 불일치면 `VerifyError`.

복잡도: O(n). 매우 빠름.

**Verifier가 가짜 StackMapTable에 속을까?** 안 됨. Verifier는 **현재 상태에서 명시된 상태로의 transition이 valid한지** 검사. 가짜 frame이 명시되어도 시뮬레이션 결과와 불일치 → 거부.

#### Pass 3 예시

```java
public int example(int a) {
    int b = 0;
    if (a > 0) b = a;
    else b = -a;
    return b;
}
```

bytecode:
```
0:  iconst_0
1:  istore_2          // b = 0
2:  iload_1
3:  ifle 12           // 분기점
6:  iload_1           // (true branch)
7:  istore_2
8:  goto 16
12: iload_1           // (false branch) ★ StackMapFrame 필요
13: ineg
14: istore_2
16: iload_2           // (merge point) ★ StackMapFrame 필요
17: ireturn
```

StackMapTable:
```
Frame 1 (offset 12): same_frame
Frame 2 (offset 16): same_frame
```

Verifier가 12와 16에 도달 시 현재 상태와 명시 frame 비교 → 일치하면 OK.

### 2.5 Opcode와 bytecode 실행 모델 — 자주 헷갈리는 포인트

**오해 정정**: 자바 바이트코드는 물리 CPU가 직접 알아듣는 명령어가 **아니다**. **JVM이라는 가상 머신이 알아듣는 명령어 셋**이고, opcode는 그 명령어 한 종류를 가리키는 1바이트(0~255) 번호.

```
.class (바이트코드, opcode 시퀀스)
       │  ← 물리 CPU(x86/ARM)는 이해 못 함
       ▼
   ★ JVM ★ ← 가상 CPU. 바이트코드를 받아 실제 CPU 명령으로 번역
       │
       ▼
물리 CPU 명령어 (x86: mov, add, jmp / ARM: mov, ldr, b)
```

**두 가지 경로**:
- **Interpreter**: opcode 별 미리 컴파일된 C++ 핸들러를 switch로 실행. HotSpot은 Template Interpreter — opcode별 어셈블리 조각을 jump table로.
- **JIT**: hot 메서드를 통째로 물리 CPU 어셈블리로 번역해 메모리 적재. 이후 인터프리터 없이 직접 실행.

HotSpot은 둘 다 갖는 **혼합 모드(mixed mode)** — 처음엔 인터프리터, 자주 도는 메서드만 JIT.

**왜 stack machine인가**: 레지스터 머신은 CPU마다 레지스터 수/이름이 다름 → 호환성 ✕. Stack machine은 추상화된 "스택"만 가정 → CPU 종속성 0. 단점: 실제 실행은 레지스터 머신보다 느림 → JIT가 stack 연산을 레지스터로 매핑해 컴파일. 이 "stack machine 가정" 덕에 자바 바이트코드는 30년째 같은 포맷으로 호환.

### 2.6 VerifyError를 우회할 수 있나

- `-Xverify:none` (`-noverify`): JDK 13에서 deprecated, 21에서도 동작은 함. **production 금지**.
- `-Xverify:remote`: remote-loaded만 verify, local은 skip — 위험.
- `Unsafe.defineAnonymousClass` (JDK 17에서 제거) / hidden class: 일부 우회.
- Native code: verify 안 됨, JVM 안전성 깰 수 있음.

JDK 6+ StackMapTable 도입 후 verify가 매우 빨라져 끄는 효과 5~15%. **AppCDS / Generational ZGC가 더 큰 가속을 주므로 verify는 끄지 말 것**.

---

## 3. 가지 ③: Prepare — static 필드 default 할당

### 3.1 핵심 질문

> "Preparation에서 정확히 무엇이 일어나는가? static final은 다른가?"

### 3.2 키워드 1 — static default 할당

```java
class Foo {
    static int x = 42;       // Preparation 시: x = 0
                              // Initialization 시: x = 42
    static String s = "hi";   // Preparation 시: s = null
                              // Initialization 시: s = "hi"
    static final int CONST = 100;  // Preparation 시: 100 (compile-time constant)
}
```

**핵심 함정**: Preparation에서는 **사용자 코드를 실행하지 않는다**. static initializer는 Initialization에서.

### 3.3 키워드 2 — ConstantValue 예외

`static final` + compile-time constant (primitive 또는 String literal)는 **ClassFile의 `ConstantValue` attribute**로 박혀, Preparation에서 바로 할당.

| 케이스 | ConstantValue? | Preparation 시 값 |
|---|---|---|
| `static final int X = 10;` | 있음 | 10 |
| `static final int Y = compute();` | 없음 | 0 (default), Init에서 compute() |
| `static final String S = "hi";` | 있음 (literal) | "hi" |
| `static final String S = new String("hi");` | 없음 | null, Init에서 생성 |

### 3.4 키워드 3 — Constant Inlining의 운영 함정

```java
// A.java
class A { public static final int VERSION = 1; }

// B.java
class B { void print() { System.out.println(A.VERSION); } }
```

B.class의 bytecode에 `bipush 1`이 **직접 인라인**된다 (A.VERSION을 동적으로 안 읽음).
→ A.VERSION을 2로 바꾸고 A만 재컴파일하면, **B는 여전히 1을 출력** — 재컴파일 필요.

**운영 함정**: API의 `public static final`을 가볍게 바꾸면 dependent 모듈 모두 재컴파일하지 않으면 깨짐. **binary compatibility**의 영역 (가지 ⑤).

---

## 4. 가지 ④: Resolve — 심볼릭 → 직접

### 4.1 핵심 질문

> "심볼릭 참조는 어떻게 직접 참조로 바뀌고, lazy는 어떻게 동작하며, invoke 5종은 검색 규칙이 어떻게 다른가?"

### 4.2 키워드 1 — Lazy + ResolvedReference 캐시

```
Symbolic Reference (ClassFile 안):
  "java/lang/System" + "out" + "Ljava/io/PrintStream;"
       ↓
  CONSTANT_Fieldref CP 엔트리

Direct Reference (메모리 안):
  실제 InstanceKlass*, Field*, 또는 메모리 offset
```

**왜 lazy인가**: 모든 심볼릭 참조를 클래스 로드 시점에 미리 resolve하면 A→B→C→D 연쇄 로드. 사용 안 되는 클래스까지 모두 로드 → startup 느림 + 메모리 낭비.

**Lazy**: 참조가 실제로 처음 사용될 때 resolve. 사용 안 하면 안 함.

JVMS §5.4는 시점을 못 박지 않음 — 구현체 재량. HotSpot은 대체로 lazy 전략.

**캐싱**: 처음 resolve 후 결과를 CP 슬롯에 저장:
- `ConstantPool::klass_at_put` (Class)
- `ConstantPool::resolved_field_at_put` (Field)
- `ConstantPool::resolved_methodref_at` (Method)

같은 instruction의 두 번째 실행은 즉시 cached 결과 사용.

### 4.3 키워드 2 — invoke 5종 검색 규칙

각 instruction이 reference를 사용할 때 resolve가 트리거됨:
- `getstatic`, `putstatic`, `getfield`, `putfield`: 필드
- `invokevirtual`, `invokespecial`, `invokestatic`, `invokeinterface`, `invokedynamic`: 메서드
- `new`, `checkcast`, `instanceof`, `anewarray`: 클래스
- `ldc of CONSTANT_Class`: 클래스

**Method resolution: invoke opcode별 검색 규칙** (JVMS §5.4.3.3 / §5.4.3.4):

| Opcode | 사용 위치 | 검색 단계 | dispatch |
|---|---|---|---|
| **invokestatic** | static 메서드 | owner class에서 정확한 (이름, 시그니처) 검색 → super interface 탐색. 클래스에서 정의된 게 아니면 `IncompatibleClassChangeError`. | static binding |
| **invokespecial** | `<init>`, super, private | owner + supers에서 정확한 메서드 검색. `super.x()`는 현재 클래스의 직계 super에서 시작해 위로. | static binding |
| **invokevirtual** | 일반 instance 메서드 | owner class → super class 사슬 → super interfaces에서 가장 구체적 non-abstract. | **runtime dispatch (vtable)** |
| **invokeinterface** | interface 타입 reference | interface + super interfaces. 못 찾으면 `Object`의 public 메서드. | **runtime dispatch (itable)** |
| **invokedynamic** | lambda, indy 등 | BootstrapMethod 호출 → CallSite 반환 → target MethodHandle | 첫 호출에 사용자 정의 link, 이후 직접 |

**핵심 차이**:
- invokestatic / invokespecial: 검색 결과 = 호출될 메서드 (static binding).
- invokevirtual / invokeinterface: resolution은 "어떤 시그니처를 부를지" 결정, 실제 어느 클래스 구현이 실행될지는 **런타임에 인스턴스 타입을 보고 다시 결정** (dynamic dispatch).

운영에서 `IncompatibleClassChangeError`나 `AbstractMethodError`가 튀어나오는 원인이 이 opcode별 규칙에 박혀 있다.

### 4.4 키워드 3 — vtable / itable

Resolution은 "어떤 시그니처를 부를지"까지만 결정한다. **실제 어느 클래스의 구현이 실행될지를 즉석에서 고르는 동작 = dispatch**. vtable/itable은 그 dispatch를 매번 검색 없이 O(1)로 끝내기 위해 InstanceKlass에 미리 박아두는 자료구조.

#### vtable (Virtual Method Table)

한 클래스 인스턴스에서 dynamic dispatch될 수 있는 **메서드들의 함수 포인터 배열**.

```
Animal extends Object:
  [0] Object.equals
  [1] Object.hashCode
  [2] Animal.toString    ← Animal이 override → 같은 슬롯에 자기 포인터
  [3] Object.getClass
  [4] Animal.bark        ← Animal이 새로 추가

Dog extends Animal:
  [0] Object.equals
  [1] Object.hashCode
  [2] Animal.toString    ← 그대로 상속
  [3] Object.getClass
  [4] Dog.bark           ← ★ Dog override → 같은 슬롯[4]에 자기 포인터 ★
  [5] Dog.fetch          ← Dog가 새로 추가
```

**핵심 규칙**: 같은 시그니처의 부모-자식 override는 **반드시 같은 인덱스**. 호출자(`Animal a` 타입으로 컴파일)가 "vtable[4] 불러"만 알면, 실제 객체가 Animal이든 Dog든 올바른 포인터 잡힘.

```
a.bark() where a: Animal = new Dog()
  1. javac가 컴파일 시 Animal.bark의 vtable 인덱스 = 4 박는다
  2. 런타임: a → 실제 객체 헤더 → Dog의 InstanceKlass → vtable[4] = Dog.bark
  3. jump → Dog.bark 실행
```

검색 없이 **인덱스 한 번 → O(1)**.

#### itable (Interface Method Table)

인터페이스 메서드 dispatch 전용. **(인터페이스, 메서드) → 함수 포인터** 매핑.

**왜 vtable로 안 되나**: vtable의 "같은 시그니처는 같은 인덱스" 가정이 인터페이스에서 깨짐.
1. 한 클래스가 여러 인터페이스 implement → 인터페이스끼리 같은 인덱스에 다른 메서드면 충돌.
2. 같은 인터페이스를 여러 클래스가 implement → 클래스마다 vtable 위치가 달라짐.

해결: 인덱스 대신 **(interface, method) 쌍을 키**.

```
Dog.itable:
  Walkable 구역      Trainable 구역
    Walkable.walk      Trainable.train
    Walkable.stop      Trainable.reward
```

호출 흐름: w → InstanceKlass → itable → "Walkable" 구역 찾기 (검색) → 인덱스에서 포인터. vtable보다 인터페이스 구역 찾는 한 단계가 더 든다 → 약간 느림.

#### Inline Cache — itable이 실전에서 vtable급으로 빠른 이유

JIT는 호출 사이트마다 **최근 dispatch 결과를 캐싱**.

```
첫 호출:   w.walk()  →  itable 검색  →  Dog.walk  (캐시: "type=Dog → Dog.walk")
두 번째:   w.walk()  →  캐시 적중. type 확인만 하고 점프.
```

- **Monomorphic** (한 타입만): vtable과 동일 속도. JIT가 인라인 시도.
- **Bimorphic** (두 타입): 두 캐시 슬롯 비교.
- **Megamorphic** (3개+): 캐시 포기 → 매번 itable 풀스캔. **인라인 못 함 → 성능 급락**.

**운영 관점**: hot path에 `List`·`Collection` 같은 인터페이스 타입으로 너무 다양한 구현(ArrayList, LinkedList, HashSet 어댑터)을 섞어 받으면 megamorphic. JIT 로그(`-XX:+PrintInlining`)에 `callee is megamorphic, inlining cancelled` 찍히면 바로 그 자리.

#### InstanceKlass 메모리 레이아웃

```
[InstanceKlass 본체][vtable 슬롯들][itable 슬롯들][nonstatic_oop_maps]...
```

한 InstanceKlass에 vtable·itable·GC oop map까지 모두 inline — HotSpot이 dispatch와 GC를 모두 빠르게 처리하는 비결.

---

## 5. 가지 ⑤: 운영 — 에러와 성능

### 5.1 핵심 질문

> "Linking 관련 에러는 어떤 종류가 있고, startup 시간을 줄이려면 어떤 옵션이 있는가?"

### 5.2 키워드 1 — Linking 에러 6종

| 에러 | 시나리오 |
|---|---|
| `ClassFormatError` | Pass 1 실패. magic, 버전, CP 구조가 깨진 .class |
| `VerifyError` | Pass 2/3 실패. bytecode 타입 안전성 위배 |
| `NoClassDefFoundError` (NCDFE) | resolution/loading 실패, 또는 **이전에 그 클래스 `<clinit>` 실패**의 후속 증상 |
| `NoSuchFieldError` | 필드 (이름, 타입)이 owner 클래스(+ super 사슬)에 없음 — 컴파일/런타임 버전 불일치 |
| `NoSuchMethodError` | 메서드 (이름, 시그니처) 검색 실패 — 라이브러리 버전 불일치 |
| `IllegalAccessError` | private/package/protected 위반, JPMS 모듈 캡슐화 위반 |
| `IncompatibleClassChangeError` | static↔instance, class↔interface, sealed 위반, opcode 기대 형태와 다름 |
| `AbstractMethodError` | resolution은 통과, dispatch 시 구현 없는 abstract만 남음 (라이브러리 hierarchy 변경 후 재컴파일 누락) |

**ClassNotFoundException vs NoClassDefFoundError**:
- **CNFE**: checked. `Class.forName()`, `ClassLoader.loadClass()` 명시 검색 실패.
- **NCDFE**: error. 컴파일 시 존재했지만 런타임 사라짐 / 또는 **이전 `<clinit>` 실패의 후속**.

**ExceptionInInitializerError 함정**: `<clinit>` 실패한 클래스는 영구히 **erroneous** 상태. 이후 그 클래스에 대한 모든 접근에서 NCDFE throw.
- 첫 stacktrace의 `ExceptionInInitializerError`가 진짜 원인.
- 다음부터는 NCDFE만 보임 — 로그 첫 번째를 못 잡으면 영원히 헤맴.
- 회복 불가 — 그 ClassLoader 폐기 후 새 CL로 다시 로드해야 함.
- **왜 그렇게 가혹한가**: JLS 12.4.2가 init은 단 한 번. 부분 초기화 위험. Thread-safety (여러 스레드가 동시 시도하면 첫 실패를 다른 스레드도 같이 봐야 함).

### 5.3 키워드 2 — Binary Compatibility 함정

```java
// 컴파일 시
class A { public int x = 10; }
class B { void doIt() { System.out.println(new A().x); } }

// 실행 시 A를 교체
class A { public String x = "hello"; }   // 타입 변경!
```

B는 재컴파일 안 함. 실행 시:
- B.class의 CP에 `Fieldref A.x:I` (int).
- 새 A에는 `x:Ljava/lang/String;`만.
- Resolution → `NoSuchFieldError`.

JLS 13장의 **binary compatibility** 영역. 라이브러리 API 변경 시 절대 안전한 변경(메서드 추가, 새 클래스 추가)과 위험한 변경(필드 타입 변경, 메서드 시그니처 변경, sealed 클래스 변경)을 구분해야 한다.

#### Lazy resolution의 함정

1. **에러가 늦게 발견**: 컴파일 OK였지만 dependency 변경으로 깨진 reference가 있어도 실행 도중 발견 (`NoSuchMethodError`).
2. **불완전한 fail-fast**: startup에서 모든 reference 검증하면 빠르게 알 수 있지만, lazy면 production에서 한참 후 발견.
3. **테스트 어려움**: 일부 경로만 타는 코드의 resolution 실패가 운영에서 드러남.

회피: 의도적 warmup으로 모든 클래스 미리 로드.

### 5.4 키워드 3 — startup 가속: AppCDS / Leyden

JDK 21 환경에서 클래스 로딩/linking 시간 줄이는 옵션:

1. **AppCDS** (`-XX:SharedArchiveFile=...`): 사용 클래스들을 archive로 묶어 다음 실행 시 파싱/verify 스킵.
   - 빌드: `java -XX:DumpLoadedClassList=classes.lst MyApp`
   - 사용: `java -XX:SharedArchiveFile=archive.jsa MyApp`
2. **AppCDS가 archive하는 것**:
   - InstanceKlass 객체 (메타데이터)
   - Constant Pool (resolution 결과 포함)
   - Method bytecode + StackMapTable
   - vtable / itable
   - Klass에 연관된 oop들
3. 다음 실행 시 archive 파일을 **mmap**으로 매핑 → 파싱/verification 스킵, linking 일부 재사용.
4. **GraalVM Native Image / Project Leyden**: AOT 컴파일로 더 근본적 startup 가속. Container/Serverless 환경에서.

**AppCDS 함정**: archive 파일의 timestamp/checksum과 실제 .class가 다르면 archive invalidate → 일반 로딩으로 fallback. Dev 환경에서는 archive 안 쓰고, prod의 immutable image에서 사용.

### 5.5 invokedynamic의 특수 resolution

일반 invoke*는 CP의 Methodref resolve → 호출. invokedynamic은 CP의 `InvokeDynamic` 엔트리가 **bootstrap method 정보**를 가리킴.

첫 호출 시:
1. Bootstrap method 호출 (예: `LambdaMetafactory.metafactory`)
2. Bootstrap method가 `CallSite` 객체 반환
3. CallSite의 target MethodHandle을 호출 사이트에 link
4. 이후 호출은 link된 target으로 직접

CallSite 종류:
- **ConstantCallSite**: target 불변. JIT inline 최대화. Lambda 호출 사이트.
- **MutableCallSite**: target 교체 가능. Dynamic 언어(JRuby). `SwitchPoint`로 visibility 보장.
- **VolatileCallSite**: 매번 target 다시 읽음.

---

## 6. 면접 답변 워크플로우

### 6.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "Linking 3단계 설명" | ① WHY (락 없음) | ②③④ 각 단계 |
| "Verifier가 보장하는 것?" | ② Verify (Pass 3) | StackMapTable |
| "StackMapTable 왜 도입?" | ② Verify (가속) | JDK 6 역사 |
| "Preparation에서 사용자 코드?" | ③ Prepare | ConstantValue |
| "static final 인라인 함정?" | ③ Prepare | ⑤ binary compat |
| "lazy resolution 이유" | ④ Resolve | ⑤ 함정 |
| "invokevirtual vs invokeinterface" | ④ vtable/itable | inline cache |
| "AbstractMethodError 원인?" | ⑤ 에러 | ④ invoke 검색 |
| "NoClassDefFoundError 진단" | ⑤ ExceptionInInitializer | 04장 init |
| "AppCDS는 뭐 archive?" | ⑤ 성능 | InstanceKlass |
| "invokedynamic resolution?" | ④ 특수 | BootstrapMethods |

### 6.2 답변 템플릿

> **루트 문장 한 줄 → 해당 가지 키워드 3개 순서 → 듣는 사람 표정 보고 인접 가지로**

예: "Linking 3단계를 설명해주세요"

> "Linking은 ClassLoader가 끝낸 뒤 JVM 본체가 이어받는 3단계입니다 — Verify, Prepare, Resolve. 락을 안 잡고 사용자 코드도 실행하지 않습니다. (← 루트)
> 첫째, **Verification**은 안전성 증명입니다. Pass 1에서 ClassFile 구조(magic, 버전, CP), Pass 2에서 의미적 일관성(final 클래스 상속 금지 등), Pass 3에서 bytecode 타입 안전성을 봅니다. JDK 6부터 StackMapTable로 가속돼 O(n²)에서 O(n)으로 빨라졌습니다.
> 둘째, **Preparation**은 static 필드에 타입 default(`int=0`, `ref=null`)를 할당합니다. **사용자 코드는 실행 안 합니다** — static initializer는 다음 단계인 Initialization의 일입니다. 예외: `static final` + 컴파일 시간 상수는 ConstantValue attribute로 ClassFile에 박혀 여기서 바로 할당됩니다.
> 셋째, **Resolution**은 심볼릭 참조(이름, 시그니처)를 직접 참조(InstanceKlass 포인터, Field 오프셋)로 변환합니다. lazy + cache 전략 — 첫 사용 시점에 resolve하고 CP 슬롯에 결과 저장. invoke 5종마다 검색 규칙이 달라 운영의 IncompatibleClassChangeError나 AbstractMethodError의 진원지가 됩니다."

→ 면접관이 "StackMapTable 디테일?" 물으면 ② 키워드 3으로, "vtable vs itable?" 물으면 ④ 키워드 3으로.

---

## 7. 꼬리질문 트리 (가지별)

### Q1 [가지 ①]. Linking은 누가 하고, 락은 잡는가?

> JVM 본체가 한다. ClassLoader는 Loading까지(02장), Initialization은 JVM Initializer가(04장). **Linking은 락을 안 잡는다** — Verification은 데이터 분석일 뿐 실행 아님, Preparation은 단순 메모리 초기화, Resolution은 CP 캐시 update만 atomic. JLS 12.4.2의 12-step 락은 다음 단계인 Initialization에서 등장.

### Q2 [가지 ②]. Verification은 정확히 무엇을 보장하나?

> 3 Pass. (1) ClassFile 포맷(magic, 버전, CP 구조), (2) 의미적 일관성(final 상속 금지, interface 제약), (3) bytecode 타입 안전성 — StackMapTable과 비교. (심볼릭 참조 유효성은 verification이 아니라 Resolution 단계의 일.)
> Pass 3가 보장하는 것: 모든 instruction이 valid opcode, stack/locals 사용이 max 안, 각 instruction의 타입 적합(iadd는 int 둘), 분기 대상이 valid instruction 시작, 메서드 종료 시 stack 일관. → **verified bytecode는 native crash(segfault, memory corruption)를 일으킬 수 없다**.

**Q2-1: StackMapTable이 왜 도입됐나?**
> JDK 5 이하는 fixed-point iteration으로 type inference. O(n²)~O(n³). JDK 6부터 javac가 미리 각 basic block의 stack/locals 타입을 계산해 attribute에 저장 → Verifier는 linear(O(n)) 검증. JDK 7부터 필수.

**Q2-2: 가짜 StackMapTable로 verifier를 속일 수 있나?**
> 안 됨. Verifier는 **현재 상태에서 명시 frame으로의 transition이 valid한지** 검사. 가짜 frame이라도 시뮬레이션 결과와 불일치하면 VerifyError. StackMapTable은 힌트일 뿐, 검증을 우회하지 않음.

**Q2-3: -Xverify:none을 켜면 startup이 얼마나 빨라지나?**
> 5~15%. JDK 6+ StackMapTable로 verify가 빨라져 효과 작음(옛날엔 30%+). AppCDS / Generational ZGC가 더 큰 가속을 주므로 verify는 끄지 말 것. Container/Serverless면 GraalVM Native Image / Leyden이 근본 해결.

### Q3 [가지 ③]. Preparation에서 static final도 default 값인가?

> 케이스 분리.
> - `static final int X = 10;` (compile-time constant): ClassFile의 ConstantValue attribute. Preparation에서 바로 10.
> - `static final int Y = compute();`: ConstantValue 없음. Preparation에서 0, Init에서 compute().
> - `static final String S = "hi"`: literal이라 ConstantValue. 바로 "hi".
> - `static final String S = new String("hi")`: ConstantValue 아님.

**Q3-1: ConstantValue가 ClassFile에 박히면 부작용은?**
> 그 상수를 참조하는 다른 클래스의 ClassFile에 값이 **직접 인라인**된다(`bipush 1`). A의 VERSION을 2로 바꾸고 A만 재컴파일하면, B는 여전히 1 출력 — 재컴파일 필요. **운영 함정**: API의 public static final을 가볍게 바꾸면 dependent 모듈 모두 재컴파일하지 않으면 깨짐.

### Q4 [가지 ④]. Resolution은 언제 일어나고, lazy의 함정은?

> Lazy — 해당 reference를 처음 사용하는 instruction이 실행될 때. 결과는 CP에 cache → 두 번째부터 즉시. 클래스가 로드돼도 메서드 reference는 미해결 상태.
> 함정: (1) 에러가 늦게 발견 — 컴파일 OK였지만 dependency 변경으로 깨진 reference가 실행 도중 표면화(NSME), (2) 불완전한 fail-fast, (3) 일부 경로만 타는 코드의 resolution 실패가 운영에서 드러남. 회피: 의도적 warmup.

**Q4-1: invokevirtual과 invokeinterface는 검색 규칙이 어떻게 다른가?**
> invokevirtual: owner class → super class 사슬 → super interfaces에서 가장 구체적 non-abstract.
> invokeinterface: interface + super interfaces에서 검색, 못 찾으면 Object의 public 메서드.
> 둘 다 dispatch는 런타임 — vtable(invokevirtual)과 itable(invokeinterface). vtable은 인덱스 한 번 O(1), itable은 인터페이스 구역 찾는 한 단계가 더 듦. JIT의 inline cache가 monomorphic이면 itable도 vtable급 속도.

**Q4-2: invokedynamic의 resolution은?**
> CP의 InvokeDynamic 엔트리는 **bootstrap method 정보**를 가리킴. 첫 호출 시 bootstrap method 호출 → CallSite 반환 → target MethodHandle을 호출 사이트에 link → 이후 직접. ConstantCallSite(불변, lambda)/MutableCallSite(교체 가능, JRuby)/VolatileCallSite(매번 재읽기).

### Q5 [가지 ⑤]. NoClassDefFoundError와 ClassNotFoundException의 차이?

> CNFE는 checked exception, `Class.forName()`/`ClassLoader.loadClass()` 명시 검색 실패. NCDFE는 error, 컴파일 시 존재했지만 런타임 사라짐 / 또는 **이전 `<clinit>` 실패의 후속 증상**.
> 후자가 가장 오해되는 케이스 — 스택을 보면 "지금 X를 못 찾았다"처럼 보이지만, 진짜 원인은 그 이전 어딘가에서 X의 `<clinit>`이 예외로 실패한 것. **첫 번째로 발생한 ExceptionInInitializerError의 스택을 먼저 찾아야 한다**.

**Q5-1: ExceptionInInitializerError가 나면 그 클래스는?**
> 영구히 erroneous 상태. 이후 모든 접근에서 NCDFE. 회복 불가 — 그 ClassLoader 폐기 후 새 CL로 다시 로드해야 함.
> 왜 가혹: (1) JLS 12.4.2가 init은 단 한 번, (2) 부분 초기화 위험 (static 일부만 실행되면 잘못된 상태), (3) Thread-safety — 첫 실패를 다른 스레드도 같이 봐야 함.

### Q6 (Killer) [가지 ⑤]. JDK 21에서 클래스 로딩/linking 시간을 줄이는 옵션?

> 1. **AppCDS** (`-XX:SharedArchiveFile=...`): 사용 클래스 archive로 묶어 다음 실행 시 파싱/verify 스킵.
> 2. **GraalVM Native Image / Project Leyden**: AOT 컴파일로 근본 해결.
> 3. **`-Xverify:none`**: production 금지지만 실험용. 효과 5~15%.
> 4. **JIT 조정**: `-XX:-TieredCompilation`로 첫 컴파일 시간 단축(throughput은 감소).
> 5. **Tiered Compilation**: 기본 on, hot 메서드만 C2.

**Q6-1: AppCDS가 정확히 archive하는 것?**
> InstanceKlass 객체(메타데이터), Constant Pool(resolution 결과 포함), Method bytecode + StackMapTable, vtable/itable, Klass에 연관된 oop들. 다음 실행 시 archive 파일을 **mmap**으로 매핑 → 파싱/verification 스킵, linking 일부 재사용.

**Q6-2: AppCDS로 archive한 클래스를 수정하면?**
> Archive 파일의 timestamp/checksum과 실제 .class가 다르면 archive invalidate → 일반 로딩으로 fallback (warning). Dev 환경은 archive 안 씀, prod의 immutable image에서 사용.

### Q7 [가지 ④]. vtable과 itable의 차이?

> vtable: 클래스 dispatch용 함수 포인터 배열, 정수 인덱스 1개로 O(1). 부모-자식 같은 시그니처는 같은 인덱스 — Dog가 Animal.bark를 override하면 같은 슬롯에 자기 포인터.
> itable: 인터페이스 dispatch용, (interface, method) 쌍을 키. 인터페이스 구역 찾는 한 단계가 더 듦. 한 클래스가 여러 인터페이스를 implement하면 vtable의 "같은 시그니처는 같은 인덱스" 가정이 깨지기 때문에 별도 자료구조.
> Inline cache: JIT가 monomorphic이면 vtable급, megamorphic(3개+ 타입)이면 캐시 포기 + 인라인 못 함 → 성능 급락. hot path에 다양한 List 구현 섞으면 위험.

---

## 8. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 이내로 그릴 수 있다 (루트 + 5가지 + 각 키워드 3개)
- [ ] 가지 ① WHY: Linking 주체(JVM 본체), 락 없음, 라이프사이클 위치를 적는다
- [ ] 가지 ② Verify: Pass 1/2/3의 책임을 한 줄씩 말한다
- [ ] 가지 ② Verify: StackMapTable이 JDK 6에 도입된 이유(O(n²) → O(n))를 설명한다
- [ ] 가지 ② Verify: bytecode → JVM → 물리 CPU 흐름을 그린다 (왜 stack machine인지)
- [ ] 가지 ③ Prepare: static default vs ConstantValue 4가지 케이스를 적는다
- [ ] 가지 ③ Prepare: constant inlining이 binary compat에 미치는 영향을 설명한다
- [ ] 가지 ④ Resolve: lazy + cache 전략과 왜 lazy인지 설명한다
- [ ] 가지 ④ Resolve: invoke 5종의 검색 규칙 차이를 표로 적는다
- [ ] 가지 ④ Resolve: vtable / itable / inline cache (monomorphic/bimorphic/megamorphic)를 그린다
- [ ] 가지 ⑤ 운영: VerifyError/CNFE/NCDFE/NSME/IllegalAccess/IncompatibleClassChange/AbstractMethod 8종 구분
- [ ] 가지 ⑤ 운영: ExceptionInInitializerError 함정과 erroneous 상태를 설명한다
- [ ] 가지 ⑤ 운영: AppCDS가 archive하는 것 5가지를 적는다
- [ ] 7장 꼬리질문 7개에 막힘없이 답한다

---

## 다음 단계

- → [04. Initialization & Class Unload](./04-initialization-and-unload.md): clinit 실행 순서, JLS 12.4.2 lock, CL unload

## 참고

- **JVMS §5.4 Linking**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4
- **JVMS §4.10 Verification of class Files**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.10
- **JLS §13 Binary Compatibility**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html
- **JEP 309 Dynamic Class-File Constants**: https://openjdk.org/jeps/309
- **JEP 310 AppCDS**: https://openjdk.org/jeps/310
- **HotSpot verifier.cpp**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/classfile/verifier.cpp
- **HotSpot linkResolver.cpp**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/interpreter/linkResolver.cpp
