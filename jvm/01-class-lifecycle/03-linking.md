# 01-03. Linking — Verify, Prepare, Resolve

> "ClassLoader가 클래스를 로드하면 끝" 이라고 생각하면 절반만 안 것이다.
> Loading 다음에는 **Linking**이 있다. 그리고 이 단계가 JVM의 진짜 안전망이다.
> `.class` 파일을 신뢰할 수 없다는 가정 하에, JVM은 **타입 안전성을 수학적으로 증명**한다.

---

## 🗺️ JVM 라이프사이클 안에서 이 챕터의 위치

이 챕터는 클래스 라이프사이클 5단계 중 **Linking** — 로드된 `InstanceKlass`를 검증·준비·해결하는 3단계 서브 파이프라인을 다룬다.

![class lifecycle](./_excalidraw/04-class-lifecycle.svg)

```
   .java ──javac──► .class
                       │
                       ▼
                   Loading                                  → [02-classloader-hierarchy](./02-classloader-hierarchy.md)
                       │
                       ▼  ★ 이 챕터 ★
                   Linking
                   ├─ Verification  (bytecode 타입 안전 증명)
                   ├─ Preparation   (static 필드 default 할당)
                   └─ Resolution    (심볼릭 참조 → 실제 메모리 주소, lazy)
                       │
                       ▼
                   Initialization (<clinit>)                → [04-initialization-and-unload](./04-initialization-and-unload.md)
                       │
                       ▼
                   Usage → Unloading
```

**상세 다이어그램**: ![linking 3단계](./_excalidraw/03-linking-stages.svg)

**이전/다음 챕터와의 연결**:
- ← [01-classfile-format](./01-classfile-format.md): Verification이 검증하는 입력 (ClassFile의 구조).
- ← [02-classloader-hierarchy](./02-classloader-hierarchy.md): Linking의 입력(`InstanceKlass`)을 만든 주체.
- → [04-initialization-and-unload](./04-initialization-and-unload.md): Linking이 끝난 뒤 `<clinit>`이 실행되는 단계.

### 🎯 책임 경계 — Linking은 **JVM 본체**가 한다 (ClassLoader 아님)

> 4개 챕터 전체의 책임 경계는 [README.md의 책임 경계 표](./README.md#-가장-헷갈리는-한-가지--누가-무엇을-하는가-책임-경계)에 박혀있다. 여기서는 **Linking의 주체와 락 관계**를 명확히 한다.

| 단계 | 주체 | 락 사용 | 비고 |
|---|---|---|---|
| Loading (앞 챕터) | **ClassLoader** | ClassLoader 자기 락 (parallel CL) | `defineClass()`까지 |
| **Verification** (이 챕터) | **JVM 본체** | 락 없음 | Loading 직후 자동 |
| **Preparation** (이 챕터) | **JVM 본체** | 락 없음 | static 필드를 **타입 default**로 (`int=0`, `ref=null`) |
| **Resolution** (이 챕터) | **JVM 본체** | 락 없음 (단, lazy + ResolvedReference 캐시는 atomic) | 심볼릭 → 직접, 첫 사용 시점 |
| Initialization (다음 챕터) | **JVM Initializer** | ★ **per-Class init lock + 12-step** | `<clinit>` 실행 |

#### 자주 헷갈리는 두 가지

1. **"Verification이 타입 안전성을 증명한다"는 말은 정적 증명이지, 락이 필요한 일이 아니다**
   Verification은 바이트코드를 **데이터로 읽어 분석**할 뿐 실행은 안 한다. 동시성 이슈가 없으므로 락도 없다. JLS 12.4.2의 12-step 락은 여기 등장하지 않는다.

2. **Preparation의 "default 값"과 Initialization의 "진짜 값"은 다른 단계**
   - Preparation: `static int x;`의 메모리를 확보하고 `0`으로 채움. **타입 default**.
   - Initialization: `<clinit>`을 돌려 `x = 42;`로 교체. **의미 있는 값**.
   - 그래서 Active Use가 init을 강제하는 진짜 이유는 "타입 안전성"이 아니라 **"default 0/null로는 비즈니스 로직이 깨지기 때문"** ([04장의 Active vs Passive Use](./04-initialization-and-unload.md) 참조).

핵심 한 줄: **Linking은 ClassLoader가 끝낸 뒤 JVM 본체가 이어받는 단계. 락은 안 잡고, `<clinit>`도 안 돌린다. 다음 단계인 Initialization에서 비로소 락이 등장한다.**

---

## 📍 학습 목표

1. Loading → Linking → Initialization의 경계를 명확히 그릴 수 있다.
2. Linking의 3단계 **Verification / Preparation / Resolution**을 각각 한 줄로 설명할 수 있다.
3. Verifier가 무엇을 검증하는지, 4가지 패스(Pass 1~4)를 안다.
4. JDK 6의 StackMapTable이 왜 도입됐고, 어떻게 verification을 가속하는지 안다.
5. Resolution이 lazy인 이유와 caching 메커니즘을 안다.
6. `VerifyError` vs `NoClassDefFoundError` vs `IncompatibleClassChangeError`의 차이를 안다.

---

## 🎨 1단계: 백지 그리기 가이드

### Step 1: 가로 5단계 흐름
```
[Loading] → [Verification] → [Preparation] → [Resolution] → [Initialization]
              └──────── Linking (3단계) ─────────┘
```

### Step 2: 각 단계 아래에 박스로 설명
- Loading: .class 바이트 → InstanceKlass 객체
- Verification: 4 Pass로 바이트코드 안전성 증명
- Preparation: static 필드에 default 값 (0, null, false)
- Resolution: 심볼릭 참조 → 직접 참조 (lazy)
- Initialization: static block + static field initializer 실행

### Step 3: Verification 4 Pass 세부
1. Pass 1: ClassFile 포맷 (마법 넘버, 버전, CP 일관성)
2. Pass 2: 시멘틱 (final 클래스 상속 등)
3. Pass 3: ★ Bytecode 검증 (StackMapTable, type inference) ★
4. Pass 4: 심볼릭 참조 검증 (Resolution 시 수행)

### Step 4: Pass 3 안의 알고리즘
- StackMapFrame: 분기점마다의 stack/locals 타입 상태
- Type inference + 일관성 검증

### Step 5: Resolution 패턴
- Lazy: 처음 사용 시
- Caching: ResolvedRef 저장 후 재사용

### Step 6: 에러 매핑
- Pass 1 실패 → `ClassFormatError`
- Pass 2/3 실패 → `VerifyError`
- Pass 4 실패 → `NoSuchFieldError`, `NoSuchMethodError`, `IllegalAccessError`, ...

### 정답 그림

![Linking 5단계](./_excalidraw/03-linking-stages.svg)

> 편집은 [03-linking-stages.excalidraw](./_excalidraw/03-linking-stages.excalidraw)을 [excalidraw.com](https://excalidraw.com/)에서 "Open"으로.

---

## 🧠 2단계: 직관

### 핵심 비유

> 부동산 거래 비유:
> - **Loading** = 등기부등본 받아오기 (서류 입수)
> - **Verification** = 서류 위조 검사 (인감 진위, 권리 관계)
> - **Preparation** = 명의 이전 준비 (계좌 개설, 빈 칸 채울 양식 만들기)
> - **Resolution** = 실제 권리자 찾기 (등기부의 이름으로 실제 사람 매칭)
> - **Initialization** = 입주 (가구 들이기, 사람 살기)

### 왜 Verification이 그토록 엄격한가?

> 1995년 Java applet 시대: 브라우저가 untrusted 코드를 다운받아 실행. **악성 bytecode**가 JVM을 깨거나 메모리를 망가뜨릴 수 있음.
>
> 해결책: bytecode를 실행하기 전에 **수학적으로 타입 안전성을 증명**. 검증된 bytecode는 segfault 같은 native crash를 일으킬 수 없음을 보장.
>
> 즉 Verifier는 **JVM 보안의 첫 방어선**. 이게 없으면 Java의 "safe by construction" 가정이 무너진다.

### 왜 Resolution이 lazy인가?

> 모든 심볼릭 참조를 클래스 로드 시점에 미리 resolve하면:
> - Class A가 B를 참조 → B 로드 → B가 C를 참조 → C 로드 → 연쇄적으로 수많은 클래스 로드.
> - 사용하지 않는 클래스까지 모두 로드 → startup 느림 + 메모리 낭비.
>
> Lazy resolution: 그 reference를 **실제로 쓰는 순간** 해결. 사용 안 하면 안 함.

---

## 🔬 3단계: 구조

### 5단계 전체 흐름

```
                  ┌──────── Linking (3단계) ─────────┐
                  │                                   │
┌─────────┐   ┌──────────────┐  ┌───────────┐  ┌──────────┐   ┌──────────────┐
│ Loading │ → │ Verification │ →│Preparation│ →│Resolution│ → │Initialization│
└─────────┘   └──────────────┘  └───────────┘  └──────────┘   └──────────────┘
     │              │                 │              │                │
     ▼              ▼                 ▼              ▼                ▼
 .class bytes  타입 안전성 검증     static 필드     symbolic →       <clinit>
   → Instance  → VerifyError       default 값      direct           실행
     Klass       (Pass 1~4)        (0/null/false)  (lazy + cached)
     생성                                                           ↓
                                                              ExceptionIn
                                                              InitializerError
                                                              (가능)
```

---

## 1️⃣ Loading

**입력**: 클래스 이름  
**출력**: `.class` 바이트 → 메모리의 `InstanceKlass` 객체

핵심 동작:
1. ClassLoader가 `.class` 바이트 획득 (디스크/네트워크/byte[]).
2. ClassFileParser가 바이트를 파싱 → `InstanceKlass` 생성.
3. `java.lang.Class` mirror 객체 생성 (Heap에).
4. Metaspace의 SystemDictionary에 등록.

> 이 단계는 챕터 02 (ClassLoader)와 챕터 01 (ClassFile 포맷)에서 다뤘다.

---

## 2️⃣ Verification — 안전성 증명

### 3 Pass 구조

| Pass | 시점 | 검증 항목 | 실패 시 |
|---|---|---|---|
| **1** | Loading 직후 | ClassFile 구조 (magic, version, CP 형식) | `ClassFormatError` |
| **2** | Loading 직후 | 의미적 일관성 (final 클래스 상속 금지 등) | `VerifyError` |
| **3** | Linking 단계 | ★ Bytecode 검증 (타입 안전성) ★ | `VerifyError` |

> JVMS의 verification 범위는 **위 3 Pass(=bytecode/type safety)** 까지다. "심볼릭 참조가 실제로 존재하는지" 같은 검사는 verification이 아니라 **다음 단계인 Resolution**에서 일어난다. 둘은 자주 묶여 설명되지만 JVMS는 별개 단계로 분리한다 — 이 문서도 그 경계를 그대로 유지한다.

### Pass 1: ClassFile Format

```cpp
// classFileParser.cpp의 책임
- magic == 0xCAFEBABE
- major_version이 지원 범위 안
- CP의 모든 tag가 유효
- CP 인덱스가 범위 안 (1 ~ count-1)
- attributes의 length 일관성
- 각 method의 Code attribute 존재
```

실패: 파싱 중 즉시 `ClassFormatError`.

<details>
<summary><b>각 항목이 정확히 뭘 보는 건가? — 처음 보는 사람을 위한 용어 풀이</b> (펼치기)</summary>

#### `magic == 0xCAFEBABE` — "이 파일이 진짜 .class 파일인가"

- `.class` 파일의 **가장 첫 4바이트는 무조건 `CA FE BA BE`** 로 시작한다. 이를 **매직 넘버(magic number)** 라고 부른다.
- 의미: "내가 `.class` 파일이오"라는 자기 선언. JVM은 이걸 보고 "아, 자바 클래스 파일이구나" 확인한 뒤에야 다음 바이트를 해석한다.
- 다른 파일(jpg, exe 등)도 각자 매직 넘버를 가진다 — 예: PNG는 `89 50 4E 47`, ZIP은 `50 4B 03 04`.
- `0xCAFEBABE`는 사실 단어 장난. 자바 만든 팀이 1990년대 카페에서 회의하다가 "CAFE BABE"(예쁜 카페 손님 = "babe") 의미로 박은 농담. 깊은 의미는 없고 **외부에서 잘못 만든 파일·전송 중 깨진 파일을 거르는 첫 관문**이라는 역할만 기억하면 된다.
- 만약 다른 값이면 → `ClassFormatError` 즉시. 파싱을 시도조차 안 함.

#### `major_version`이 지원 범위 안 — "이 JVM이 이해할 수 있는 버전인가"

- `.class` 파일의 5~6번째 바이트는 minor, 7~8번째 바이트는 **major version**.
- major version은 자바 버전에 1:1로 대응: JDK 8 → 52, JDK 11 → 55, JDK 17 → 61, JDK 21 → 65.
- JVM은 자기보다 **나중에 컴파일된 클래스**는 실행 못 함 → JDK 17로 컴파일한 클래스를 JDK 11로 돌리면 `UnsupportedClassVersionError`.
- 반대로 옛 버전은 거의 항상 잘 돌아감(상위 호환).

#### CP가 뭔가 — `ConstantPool`(상수 풀)

- **CP = ConstantPool**. `.class` 파일 안에 들어 있는 **"이 클래스가 참조하는 모든 이름·문자열·숫자·타입의 사전"**.
- 자바 코드 `String s = "hello"; System.out.println(s);` 한 줄이 만드는 CP 예시:
  ```
  CP[1] = CONSTANT_Class    "java/lang/System"
  CP[2] = CONSTANT_Fieldref "java/lang/System.out:Ljava/io/PrintStream;"
  CP[3] = CONSTANT_Class    "java/io/PrintStream"
  CP[4] = CONSTANT_Methodref "java/io/PrintStream.println:(Ljava/lang/String;)V"
  CP[5] = CONSTANT_String   #6
  CP[6] = CONSTANT_Utf8     "hello"
  CP[7] = CONSTANT_Utf8     "java/lang/System"
  ...
  ```
- 비유: 문서 안에 같은 단어가 여러 번 나오면 매번 풀어 쓰는 대신 **각 단어에 번호를 붙인 뒤 번호만 본문에 박는 방식**. 클래스 파일 크기 줄이고, 같은 이름을 여러 번 참조할 때 효율적.
- bytecode가 클래스·메서드·필드를 부를 때는 항상 **CP 인덱스 번호**로 가리킨다. 예: `invokevirtual #4` = "CP의 4번 항목이 가리키는 메서드 호출".

#### CP의 모든 tag가 유효 — "각 사전 항목의 종류표가 맞나"

- CP의 각 항목은 **첫 바이트에 tag(종류 식별자)** 가 박혀 있다. JVMS §4.4가 정의한 tag 종류:
  ```
  1  = Utf8           (문자열 데이터)
  3  = Integer        (int 상수)
  4  = Float
  5  = Long
  6  = Double
  7  = Class          (클래스 참조)
  8  = String         (String 상수)
  9  = Fieldref       (필드 참조)
  10 = Methodref      (메서드 참조)
  11 = InterfaceMethodref
  12 = NameAndType
  15 = MethodHandle   (JDK 7+)
  16 = MethodType     (JDK 7+)
  17 = Dynamic        (JDK 11+)
  18 = InvokeDynamic  (JDK 7+)
  19 = Module         (JDK 9+)
  20 = Package        (JDK 9+)
  ```
- "tag가 유효" = 첫 바이트 값이 위 표에 있는 번호인지. 예를 들어 `99` 같은 정의되지 않은 tag가 박혀 있으면 `ClassFormatError`.
- 또한 tag별로 뒤따라야 할 바이트 구조가 정해져 있다(예: Methodref는 항상 4바이트 — class_index 2바이트 + name_and_type_index 2바이트). 그게 맞는지도 같이 본다.

#### CP 인덱스가 범위 안 (1 ~ count-1) — "참조 번호가 사전에 실제로 있는 번호인가"

- 한 CP 항목은 자주 **다른 CP 항목을 가리킨다** (위 예에서 `CP[5] CONSTANT_String → #6`처럼). 이때 가리키는 숫자가 CP 인덱스.
- CP의 항목 수가 `constant_pool_count`. 유효한 인덱스는 **`1 ~ count-1`** — 인덱스 0은 예약(사용 금지), `count`는 항목 개수+1이라 그 자체로는 인덱스가 아님.
- 만약 어떤 항목이 "CP[9999]를 봐"라고 가리키는데 사전 길이가 100이면? → 잘못된 참조 → `ClassFormatError`.
- 비유: 사전에 100개 단어밖에 없는데 "9999번 단어 봐"라고 적혀 있으면 무효한 책. 그걸 거르는 검사.

> **Long/Double 함정**: tag 5(Long), 6(Double)은 **CP 슬롯 2개**를 차지한다(역사적 유물). 그래서 `CP[5] = Long`이면 `CP[6]`은 비어 있고 다음 유효 인덱스는 `CP[7]`. Pass 1은 이 규칙도 같이 검사한다.

#### attributes의 length 일관성 — "각 부속 정보의 크기가 실제 데이터와 맞나"

- ClassFile은 본체 외에 여러 **attribute**(부속 정보)를 가진다. 각 attribute는 다음 구조:
  ```
  attribute_name_index (2바이트) — CP의 어떤 Utf8을 가리킴 (이름)
  attribute_length     (4바이트) — 뒤에 따라올 데이터 바이트 수
  info[attribute_length] — 실제 데이터
  ```
- 예: `Code` attribute 길이가 100바이트라고 적혀 있는데 실제로 50바이트만 들어 있으면 깨진 파일.
- 흔한 attribute: `Code`(메서드 바이트코드), `LineNumberTable`(디버깅용), `StackMapTable`(verification용), `SourceFile`(원본 .java 이름), `Signature`(제네릭 타입 정보), `ConstantValue`(static final 상수 값).
- 이 검사는 "선언한 길이"와 "실제 데이터 크기"가 맞는지 본다. 안 맞으면 파싱이 다음 위치를 못 찾아 그 뒤 전부 깨짐 → `ClassFormatError`.

#### 각 method의 Code attribute 존재 — "메서드는 코드를 들고 있어야 한다"

- `.class` 안의 각 method는 `Code` attribute 안에 **실제 bytecode + max_stack + max_locals + exception table** 을 담는다.
- `abstract` 또는 `native` 메서드만 예외 — 구현이 없으니 Code attribute도 없다.
- 일반 메서드가 Code attribute 없이 나오거나, abstract 메서드가 Code attribute를 들고 있으면 모순 → `ClassFormatError`.
- 이 검사는 "메서드 선언과 실제 코드 유무가 일치하는가"를 본다.

</details>

### Pass 2: Semantic Checks

```cpp
- super_class가 final이면 안 됨
- interface는 super_class가 java.lang.Object여야 함
- 모든 메서드 시그니처 형식 유효
- ACC_INTERFACE인 클래스의 메서드는 ACC_ABSTRACT만 (default method 제외)
- 같은 시그니처의 메서드 중복 금지
```

### Pass 3: Bytecode Verification — 핵심

**목표**: 모든 메서드의 모든 bytecode 위치에서 **타입 안전성을 증명**.

**증명할 것**:
1. 모든 instruction이 valid opcode.
2. 모든 instruction의 stack/locals 사용이 max_stack/max_locals 안.
3. 모든 instruction이 받는 타입이 올바름 (예: `iadd`는 stack 위에 int 둘이 있어야 함).
4. 메서드 종료 시 stack이 비어있거나 반환 타입과 맞음.
5. 모든 분기 대상이 유효한 instruction 시작 위치.

<details>
<summary><b>"opcode"가 정확히 뭐고, 바이트코드는 CPU에서 어떻게 실행되는가</b> (펼치기)</summary>

흔한 오해부터 정정: 자바 바이트코드는 **물리 CPU가 직접 알아듣는 명령어가 아니다.** **JVM이라는 가상 머신(virtual machine)이 알아듣는 명령어 셋**이고, opcode는 그 명령어 한 종류를 가리키는 식별 번호다.

#### Opcode 정의

**opcode = "Operation Code"의 줄임말**. JVM 명령어 한 종류를 가리키는 **1바이트(0~255) 숫자**.

JVMS §6에 정의된 opcode 예시(총 ~200개):

| opcode | 값(hex) | 의미 |
|---|---|---|
| `iconst_0` | `0x03` | stack에 int 0 push |
| `bipush` | `0x10` | 다음 1바이트를 int로 stack에 push |
| `iadd` | `0x60` | stack 위 int 두 개 pop → 더하기 → 결과 push |
| `invokevirtual` | `0xB6` | 다음 2바이트가 가리키는 메서드 호출 (virtual dispatch) |
| `return` | `0xB1` | 메서드 종료 |
| `getfield` | `0xB4` | 객체의 필드 값을 stack에 push |

#### 바이트코드의 실제 구조 = opcode + operand 시퀀스

```java
int sum = 1 + 42;
```
가 컴파일되면:
```
03            ← iconst_1     (1을 stack에 push)
10 2A         ← bipush 42    (0x2A = 42를 stack에 push)
60            ← iadd         (두 int 더해서 stack에 push)
3C            ← istore_1     (stack 값을 local var #1에 저장)
```
각 줄의 첫 바이트가 opcode, 뒤가 operand. 위 항목 1 "모든 instruction이 valid opcode"는 **이 첫 바이트들이 모두 JVMS가 정의한 유효 값**(0x00 ~ 약 0xCA 사이)인지를 본다. `0xFE`, `0xFF`(reserved), `0xCA`(breakpoint, 디버거 전용) 같은 게 일반 .class에 박혀 있으면 `VerifyError`.

#### 바이트코드 → 물리 CPU까지의 흐름

```
.class (바이트코드, opcode 시퀀스)
       │  ← 이걸 물리 CPU(x86/ARM)는 이해 못 함
       │     "JVM이라는 가상 CPU의 명령어"이기 때문
       ▼
   ★ JVM ★ ← 가상 CPU 역할. 바이트코드를 받아 실제 CPU가 할 일로 번역
       │
       ▼
물리 CPU 명령어 (x86: mov, add, jmp ... / ARM: mov, ldr, b ...)
```

자바의 "한 번 컴파일하면 어느 OS·CPU에서든 돌아간다(write once, run anywhere)"가 가능한 이유 — **바이트코드라는 중간 표현**을 두고 각 플랫폼은 JVM만 따로 구현하면 됨. .class 자체는 x86이든 ARM이든 RISC-V든 동일.

JVM이 바이트코드를 물리 CPU 명령으로 바꾸는 두 가지 경로:

##### ① Interpreter — 한 명령어씩 해석 (시작 빠름, 실행은 느림)

개념적으로는 거대한 switch 문:

```cpp
while (true) {
    uint8_t op = bytecode[pc++];
    switch (op) {
        case 0x60:  // iadd
            int b = stack.pop();
            int a = stack.pop();
            stack.push(a + b);   // ← 이 C++ 코드가 이미 x86 add로 컴파일돼 있음
            break;
        case 0xB6:  // invokevirtual
            // ... vtable dispatch
            break;
        // ... 모든 opcode에 대해 case
    }
}
```

각 opcode마다 미리 컴파일된 C++ 핸들러가 있어, JVM이 바이트코드를 읽으며 해당 핸들러를 실행 → 그 안의 C++가 이미 물리 CPU 명령으로 컴파일된 상태라 결과적으로 CPU가 실행.

HotSpot의 실제 인터프리터는 위 switch 대신 **Template Interpreter** — opcode별로 미리 만들어둔 어셈블리 조각을 jump table로 호출하는 최적화된 형태. 본질은 같다.

##### ② JIT Compiler — 통째로 네이티브 코드로 번역 (워밍업 필요, 이후 빠름)

자주 실행되는 "hot" 메서드를 발견하면 JVM은 그 메서드의 바이트코드를 통째로 **물리 CPU 어셈블리로 번역**해 메모리에 적재. 이후 호출부터는 인터프리터 없이 그 네이티브 코드를 직접 실행.

```
바이트코드 (총 4 opcode)         JIT 결과 (x86 어셈블리)
03                              mov  eax, 1
10 2A                            mov  ebx, 42
60                               add  eax, ebx
3C                               mov  [rsp+4], eax
```

원래 4개의 opcode를 인터프리터 switch로 해석하던 게 4개의 x86 명령으로 직역됨 → 인터프리터 오버헤드 사라짐.

> HotSpot은 두 경로를 모두 갖는다 = **혼합 모드(mixed mode)**. 처음엔 인터프리터로 시작 → 자주 도는 메서드만 JIT 컴파일 → 워밍업 끝나면 거의 모든 hot path가 네이티브로 실행되는 상태.

#### 정리 — "opcode로 CPU에 입력시킨다"의 정확한 그림

"opcode가 CPU 명령어"가 아니라:
> **JVM이** 바이트코드의 각 opcode를 보고, **그 opcode에 해당하는 동작을 물리 CPU 명령(인터프리터의 C++ 핸들러 또는 JIT가 번역한 네이티브 코드)으로 변환해서** CPU가 실행하게 한다.

- **opcode** = "무슨 동작을 해야 하는지 알려주는 식별 번호"
- **JVM** = "그 번호를 보고 실제 CPU 명령을 발행하는 통역사"
- **CPU** = 통역사가 발행한 실제 명령을 실행하는 물리 하드웨어

세 역할이 분리돼 있다.

#### 곁가지 — 왜 굳이 stack machine인가

JVM의 opcode 거의 모두가 **stack을 push/pop하는 형태**(`iadd`, `bipush`, `iload`). 왜?

- **레지스터 머신**(x86 등): CPU마다 레지스터 개수·이름이 다르다 → 바이트코드를 어느 CPU에도 못 박음.
- **stack machine**: 추상화된 "스택"만 가정 → CPU 종속성 0.
- 단점: 실제 실행 시엔 레지스터 머신보다 느림. 그래서 JIT가 stack 연산을 다시 CPU 레지스터로 매핑해 컴파일하는 게 큰 일.

이 "stack machine 가정" 덕분에 자바 바이트코드는 30년째 같은 포맷으로 호환된다.

</details>

#### Type System

JVMS §4.10.1의 verification type lattice:

```
                 top
                  │
       ┌──────────┴──────────┐
   oneWord                twoWord
       │                     │
  ┌────┴────┐          ┌─────┴─────┐
 int      ...        long       double
                       │           │
                  long2 (slot2)  double2 (slot2)
```

각 stack slot과 local variable slot이 어떤 타입인지 추적.

#### 알고리즘 1: 옛 방식 (JDK 5 이하) — Type Inference

각 메서드의 모든 instruction에서:
1. 입력 stack/locals 타입 상태 (예: `[int, ref]`, `int`).
2. instruction 실행 후 상태 계산.
3. 분기점에서 여러 진입 경로의 상태를 **merge** — 공통 supertype으로 통합.
4. **fixed-point iteration**: 변화 없을 때까지 반복.

복잡도: O(n²)~O(n³). 큰 메서드에서 매우 느림.

#### 알고리즘 2: 새 방식 (JDK 6+) — StackMapTable

핵심 아이디어: **javac가 미리 계산해서 ClassFile에 적어둔다.**

`StackMapTable` attribute (Code attribute 안):
```
StackMapTable {
    u2 number_of_entries;
    StackMapFrame entries[];
}
```

각 `StackMapFrame`은 **basic block 시작점**의 stack/locals 타입 상태를 명시.

JVM Verifier는:
1. 첫 instruction의 초기 상태 = 메서드 파라미터 타입.
2. 다음 instruction마다 시뮬레이션 (한 단계씩).
3. 분기점 도달 시: 현재 상태가 ClassFile에 명시된 StackMapFrame과 일치하는지만 확인.
4. 불일치면 `VerifyError`.

복잡도: O(n) (한 번만 훑음). 매우 빠름.

**Verifier가 가짜 StackMapTable에 속을까?** 안 됨. Verifier는 **현재 상태에서 명시된 상태로의 transition이 valid한지**를 검사. 가짜 frame이 명시되어도 시뮬레이션 결과와 불일치 → 거부.

#### Pass 3 예시

```java
public int example(int a) {
    int b = 0;
    if (a > 0) {
        b = a;
    } else {
        b = -a;
    }
    return b;
}
```

bytecode (개략):
```
0:  iconst_0
1:  istore_2          // b = 0, locals = [this:ref, a:int, b:int]
2:  iload_1           // stack = [int]
3:  ifle 12           // 분기점. stack = [], 양 분기로 갈라짐
6:  iload_1           // (true branch)
7:  istore_2
8:  goto 16
12: iload_1           // (false branch) ★ StackMapFrame 필요 ★
13: ineg
14: istore_2
16: iload_2           // (merge point) ★ StackMapFrame 필요 ★
17: ireturn
```

StackMapTable:
```
Frame 1 (offset 12):  same_frame   // locals/stack 변화 없음
Frame 2 (offset 16):  same_frame
```

Verifier가 12와 16에 도달 시 현재 상태와 명시된 frame을 비교 → 일치하면 OK.

> **"Pass 4"는 없다**: 옛 교재에서 종종 "Pass 4: Symbolic Reference Verification" 식으로 표현되지만, JVMS는 심볼릭 참조 해소를 verification이 아닌 **Resolution 단계**에 둔다. 본 문서는 그 경계를 그대로 따른다 — 심볼릭 참조 관련 검사는 아래 §4 Resolution에서.

---

## 3️⃣ Preparation — static 필드 초기화 준비

**무엇을**: static 필드에 **default 값**을 할당.

```java
class Foo {
    static int x = 42;       // Preparation 시: x = 0
                              // Initialization 시: x = 42
    static String s = "hi";   // Preparation 시: s = null
                              // Initialization 시: s = "hi"
    static final int CONST = 100;  // Preparation 시: 100 (compile-time constant)
}
```

> **함정**: Preparation에서는 **사용자 코드를 실행하지 않는다**. static initializer는 Initialization에서.
> 예외: `static final` + compile-time constant (primitive 또는 String literal)는 Preparation에서 바로 할당. ConstantValue attribute로 .class에 저장됨.

### `static final` 함정

```java
class A {
    static final int X = 10;          // ConstantValue attribute로 .class에 인라인
    static final int Y = computeY();  // ConstantValue 아님 — clinit에서 계산
}

class B {
    public static void main(String[] args) {
        System.out.println(A.X);  // A를 init하지 않음! (constant inlining)
        System.out.println(A.Y);  // A 초기화 트리거
    }
}
```

`A.X`는 **B의 ClassFile에 10이라는 값으로 직접 박힌다** — `ldc 10`.
→ B 컴파일 후 A의 X를 20으로 바꿔도, B는 여전히 10을 출력 (재컴파일 필요).

운영 함정: **버전 호환성 깨짐**. dependency의 `public static final`을 절대 가볍게 바꾸면 안 됨.

---

## 4️⃣ Resolution — 심볼릭 → 직접

### Symbolic Reference vs Direct Reference

```
Symbolic Reference (ClassFile 안):
  "java/lang/System" + "out" + "Ljava/io/PrintStream;"
       ↓
  CONSTANT_Fieldref CP 엔트리

Direct Reference (메모리 안):
  실제 InstanceKlass*, Field*, 또는 메모리 offset
```

Resolution = symbolic → direct 변환.

### Lazy Resolution

JVMS는 **resolution이 일어나는 정확한 시점에 자유도**를 둔다(§5.4 "may be performed when the reference is first used, or eagerly"). 즉 구현체 재량 — 참조 종류와 JVM 구현에 따라 다르다.

- 이론적으로 가능한 두 극단:
  1. **Eager**: Linking 시점에 모든 심볼릭 참조를 미리 resolve.
  2. **Lazy**: 그 참조가 실제로 처음 사용될 때 resolve.
- **HotSpot은 대체로 lazy**. 이유: startup 시간 단축 + 사용 안 되는 참조에 메모리·시간 안 씀.
- 예외적으로 일부 케이스(예: 클래스 hierarchy를 결정짓는 super 참조)는 lazy로 둘 수 없어 더 일찍 resolve된다.

> "JVMS가 eager/lazy 두 옵션을 둘 다 명시적으로 허용한다"보다는, **JVMS는 시점을 못 박지 않았고 HotSpot은 그 자유도 안에서 lazy 전략을 택했다**고 이해하는 게 더 정확하다.

### 첫 사용 시점

각 instruction이 reference를 사용할 때:
- `getstatic`, `putstatic`: static 필드 reference
- `getfield`, `putfield`: instance 필드 reference
- `invokevirtual`, `invokespecial`, `invokestatic`, `invokeinterface`: 메서드 reference
- `new`: 클래스 reference
- `checkcast`, `instanceof`: 클래스 reference
- `anewarray`, `multianewarray`: 컴포넌트 타입 reference
- `ldc` of CONSTANT_Class: 클래스 reference

### Resolution 단계

| reference 타입 | 단계 |
|---|---|
| **Class** | 1. CP에서 클래스 이름 가져옴. 2. 그 클래스의 ClassLoader가 로드 (트리거 가능). 3. 접근 권한 검사. |
| **Field** | 1. Field의 owner class resolve. 2. 그 클래스에서 (이름, 타입) 매칭 필드 검색. 3. 못 찾으면 super interfaces → super class 순으로 탐색. 4. 접근 권한 검사. |
| **Method** | 1. Method의 owner class resolve. 2. **호출 opcode별로 검색 규칙이 다름** (아래 표). 3. 접근 권한 검사. |

#### Method resolution: invoke opcode별 검색 규칙

JVMS §5.4.3.3 / §5.4.3.4 — `invoke*`마다 "어디서 메서드를 찾는가"와 "어디서 dispatch를 결정하는가"가 다르다.

| Opcode | 사용 위치 | 검색 단계 (JVMS §5.4.3.3 / §5.4.3.4) | dispatch |
|---|---|---|---|
| **`invokestatic`** | static 메서드 호출 | 1) owner class에서 정확한 (이름, 시그니처) 검색. 2) 못 찾으면 super interface도 탐색(§5.4.3.3). 3) 클래스에서 정의된 게 아니면 `IncompatibleClassChangeError`. | 컴파일/resolve 시점에 메서드 확정 (static binding). |
| **`invokespecial`** | `<init>`, `super.method()`, private | 1) owner class + supers에서 정확한 메서드 검색. 2) 특히 `super.x()`는 현재 클래스의 직계 super에서 시작해 위로 올라감. 3) interface default 호출이면 §5.4.3.4의 interface method resolution. | 컴파일 시점 확정 (static binding). |
| **`invokevirtual`** | 일반 instance 메서드 (class 타입 reference) | 1) owner class에서 정확한 메서드 검색 → 없으면 super class 사슬을 위로 탐색. 2) 그래도 없으면 super interfaces에서 가장 구체적인 non-abstract 메서드 검색. | **런타임 dispatch**: 실제 객체의 runtime class에서 시작해 같은 시그니처의 가장 구체적 메서드를 호출(vtable 사용). |
| **`invokeinterface`** | interface 타입 reference로 메서드 호출 | 1) owner는 반드시 interface. 2) 그 interface + super interfaces 사슬에서 검색. 3) 못 찾으면 `Object`의 public 메서드도 검색 대상에 포함. | **런타임 dispatch**: 실제 객체의 runtime class에서 시작해 itable로 dispatch. |

핵심 차이 한 줄 요약:
- **`invokestatic` / `invokespecial`**: 검색 결과 = 호출될 메서드 (static binding).
- **`invokevirtual` / `invokeinterface`**: resolution은 "어떤 메서드 시그니처를 부를지" 결정, 실제 어느 클래스의 구현이 실행될지는 **런타임에 인스턴스 타입을 보고 다시 결정**(dynamic dispatch).

> "그 클래스 + 부모에서 검색" 정도로 묶으면 invokestatic의 interface 검색, invokevirtual의 super-interface fallback(JDK 8의 default method 결과), invokespecial의 시작점 차이 같은 디테일이 사라진다. 운영에서 `IncompatibleClassChangeError`나 `AbstractMethodError`가 튀어나오는 원인이 이 opcode별 규칙에 박혀 있다.

### Caching: ResolvedReference

처음 resolve 후 결과를 CP 슬롯에 caching:
- `ConstantPool::klass_at_put` (Class)
- `ConstantPool::resolved_field_at_put` (Field)
- `ConstantPool::resolved_methodref_at` (Method)

같은 instruction이 두 번째 실행될 때는 즉시 cached 결과 사용.

### Resolution 에러

| 에러 | 시나리오 |
|---|---|
| `NoClassDefFoundError` | resolution/loading 자체가 실패했거나, **이전에 그 클래스의 초기화가 실패**해서 이후 접근이 전부 막힌 경우의 후속 증상. 즉 "지금 찾는 중 못 찾음" + "예전에 망가져서 더는 못 씀" 둘 다 포함. (반면 `ClassNotFoundException`은 reflection `Class.forName` 같은 명시 검색에서 클래스를 못 찾았을 때.) |
| `NoSuchFieldError` | 필드 이름/타입이 owner 클래스(및 super 사슬)에 없음 — 컴파일과 런타임 클래스 버전 불일치의 전형. |
| `NoSuchMethodError` | 메서드 (이름, 시그니처)가 검색 규칙대로 찾았는데 없음 — 라이브러리 버전 불일치의 전형. |
| `IllegalAccessError` | private/package/protected 가시성 위반. 또는 JPMS의 모듈 캡슐화 위반. |
| `IncompatibleClassChangeError` | static ↔ instance 변경, class ↔ interface 변경, sealed 위반, 메서드 검색 결과가 opcode가 기대하는 형태와 다른 경우 등. |
| `AbstractMethodError` | resolution은 통과했지만 실제 dispatch 시 구현이 없는 abstract 메서드만 남아있을 때 (보통 라이브러리 hierarchy 변경 후 재컴파일 누락). |

> 특히 `NoClassDefFoundError`는 운영에서 가장 오해되는 에러다. 스택을 보면 "지금 X를 못 찾았다"처럼 보이지만, 진짜 원인은 **그 이전 어딘가에서 X의 `<clinit>`이 예외로 실패**해서 X가 영구적으로 "초기화 실패" 상태가 된 케이스가 많다. 진단 시 항상 **첫 번째로 발생한 `ExceptionInInitializerError` 스택**을 먼저 찾아야 한다.

### Resolution 함정: 컴파일 시 vs 실행 시 불일치

```java
// 컴파일 시: A.java
class A {
    public int x = 10;
}

// 컴파일 시: B.java (A를 참조)
class B {
    void doIt() { System.out.println(new A().x); }
}

// 실행 시: A를 다음으로 교체
class A {
    public String x = "hello";  // 타입이 바뀜!
}
```

B는 재컴파일 안 함. 실행 시:
- B.class의 CP에 `Fieldref A.x:I` (int).
- 새 A에는 `x:Ljava/lang/String;` 만 있음.
- Resolution → `NoSuchFieldError`.

이게 **binary compatibility**의 영역. JLS 13장에서 자세히 정의.

---

## 🗺️ 잠깐 — 우리는 라이프사이클 어디인가? (Reminder)

> Verify/Prepare/Resolve 세 단계를 거치며 클래스가 **사용 가능한 상태에 가까워졌다**. 하지만 아직 `<clinit>`는 안 돌았다.
>
> ```
> Loading ──[★ Linking: 우리가 지금까지 본 곳 ★]──► Initialization ──► Use ──► Unload
> ```
>
> 다음 4단계는 위 3단계의 HotSpot 구현 코드. `<clinit>` 실행 자체는 [04-initialization-and-unload](./04-initialization-and-unload.md).

---

## 🧬 4단계: 내부 구현 — HotSpot

### Verification

위치: `src/hotspot/share/classfile/verifier.cpp` (3,000+ 줄)

```cpp
// verifier.cpp
class ClassVerifier : public StackObj {
public:
  void verify_class(TRAPS) {
    // Pass 2 — 의미적 검증
    verify_supertype(THREAD, CHECK);

    // Pass 3 — 메서드별 bytecode verify
    for (int index = 0; index < num_methods; index++) {
      Method* m = _klass->methods()->at(index);
      verify_method(methodHandle(THREAD, m), CHECK);
    }
  }

  void verify_method(const methodHandle& m, TRAPS) {
    // StackMapTable이 있으면 그걸 사용 (JDK 6+)
    StackMapTable stackmap_table(m->stackmap_data(), ...);

    // bytecode 시뮬레이션
    for (Bytecodes::Code opcode : m->bytecode_iter()) {
      switch (opcode) {
        case Bytecodes::_iadd:
          current_frame.pop_stack(VerificationType::integer_type(), CHECK);
          current_frame.pop_stack(VerificationType::integer_type(), CHECK);
          current_frame.push_stack(VerificationType::integer_type(), CHECK);
          break;
        case Bytecodes::_invokevirtual:
          verify_invoke_instructions(...);
          break;
        // ... 200+ opcodes
      }

      // 분기점에서 StackMapTable과 비교
      if (is_branch_target(bci)) {
        StackMapFrame* expected = stackmap_table.entry_for_bci(bci);
        if (!current_frame.is_assignable_to(expected)) {
          verify_error("Inconsistent stackmap frames", ...);
        }
      }
    }
  }
};
```

### Resolution

위치: `src/hotspot/share/oops/constantPool.cpp`

```cpp
// constantPool.cpp
Klass* ConstantPool::klass_at_impl(const constantPoolHandle& this_cp,
                                    int which, TRAPS) {
  // 1. 이미 resolved되어 있나
  CPKlassSlot kslot = this_cp->klass_slot_at(which);
  int resolved_klass_index = kslot.resolved_klass_index();
  Klass* klass = this_cp->resolved_klasses()->at(resolved_klass_index);
  if (klass != NULL) {
    return klass;  // ★ cache hit ★
  }

  // 2. 클래스 이름 가져옴
  Symbol* name = this_cp->klass_name_at(which);

  // 3. ClassLoader 통해 로드
  Klass* k = SystemDictionary::resolve_or_fail(
      name, Handle(THREAD, loader), domain, true /* throw error */, CHECK_NULL);

  // 4. 접근 권한 검사
  if (k->is_instance_klass()) {
    Reflection::VerifyClassAccessResults vca_result =
        Reflection::verify_class_access(this_cp->pool_holder(),
                                          InstanceKlass::cast(k), false);
    if (vca_result != Reflection::ACCESS_OK) {
      // IllegalAccessError throw
      ResourceMark rm(THREAD);
      char* msg = Reflection::verify_class_access_msg(...);
      THROW_MSG_NULL(vmSymbols::java_lang_IllegalAccessError(), msg);
    }
  }

  // 5. cache
  this_cp->klass_at_put(which, k);
  return k;
}
```

### Method Resolution — 가장 복잡

```cpp
// linkResolver.cpp
void LinkResolver::resolve_method(LinkInfo& result, Bytecodes::Code code, TRAPS) {
  // 1. invokestatic이면 정적 메서드만 검색
  // 2. invokevirtual이면 instance method (private 제외)
  // 3. invokespecial이면 정확한 메서드 (디스패치 안 함)
  // 4. invokeinterface이면 interface method

  Method* resolved_method = lookup_method_in_klasses(
      link_info, link_info.resolved_klass(),
      /*checkpolymorphism*/ true, /*in_imethod_resolve*/ false);

  if (resolved_method == NULL) {
    THROW_MSG(vmSymbols::java_lang_NoSuchMethodError(), ...);
  }

  // access check, abstract check
  if (resolved_method->is_abstract() && code == Bytecodes::_invokespecial) {
    THROW_MSG(vmSymbols::java_lang_AbstractMethodError(), ...);
  }

  result.set_resolved_method(resolved_method);
}
```

### vtable / itable 구축

Resolution은 "어떤 시그니처를 부를지"까지만 결정한다. **실제 어느 클래스의 구현 코드가 실행될지를 즉석에서 고르는 동작 = dispatch**. vtable/itable은 그 dispatch를 매번 검색 없이 O(1)로 끝내기 위해 InstanceKlass에 미리 박아두는 자료구조다.

#### 먼저: dispatch가 뭔가

```java
Animal a = new Dog();
a.bark();                  // ← 어느 클래스의 bark()가 실행될까?
                           //   참조 타입은 Animal, 실제 객체는 Dog → Dog.bark
                           //   이걸 결정하는 동작이 dispatch.
```

| 종류 | 결정 시점 | opcode | 예 |
|---|---|---|---|
| **Static dispatch** | 컴파일·resolve 시점에 호출 메서드 확정 | `invokestatic`, `invokespecial` | static, `<init>`, `super.foo()`, private |
| **Dynamic dispatch (= virtual dispatch)** | 런타임에 실제 객체 타입을 보고 결정 | `invokevirtual`, `invokeinterface` | 보통의 instance 메서드, interface 메서드 |

dispatch를 호출마다 "부모 사슬 따라 메서드 검색"으로 하면 O(N). 그래서 클래스를 만들 때 미리 dispatch 결과를 표로 굳혀 둔다 → vtable, itable.

#### vtable (Virtual Method Table)

**정의**: 한 클래스의 인스턴스에서 dynamic dispatch될 수 있는 **메서드들의 함수 포인터 배열**. C++(Stroustrup, 1980년대)에서 유래.

```
Object.vtable
  [0] Object.equals
  [1] Object.hashCode
  [2] Object.toString
  [3] Object.getClass
  ...

Animal extends Object:
  [0] Object.equals          ← override 안 함 → 부모 것 그대로 상속
  [1] Object.hashCode
  [2] Animal.toString        ← Animal이 override → 같은 슬롯에 자기 포인터로 덮어씀
  [3] Object.getClass
  [4] Animal.bark            ← Animal이 새로 추가한 슬롯
  [5] Animal.eat

Dog extends Animal:
  [0] Object.equals
  [1] Object.hashCode
  [2] Animal.toString        ← Dog가 override 안 함 → 그대로 상속
  [3] Object.getClass
  [4] Dog.bark               ← ★ Dog가 override → 같은 슬롯[4]에 자기 포인터 ★
  [5] Animal.eat
  [6] Dog.fetch              ← Dog가 새로 추가
```

**핵심 규칙**: 같은 시그니처의 부모 메서드와 자식 override는 **반드시 같은 인덱스**를 차지. 그래야 호출자(`Animal a` 타입으로 컴파일된 코드)가 "vtable[4] 불러"만 알면, 실제 객체가 Animal이든 Dog든 알아서 올바른 포인터가 잡힌다.

**호출 흐름**:
```
a.bark() where a: Animal = new Dog()
  1. javac가 컴파일 시 Animal.bark의 vtable 인덱스 = 4를 박는다
  2. 런타임: a → 실제 객체의 헤더 → Dog의 InstanceKlass → vtable[4] = Dog.bark 포인터
  3. jump → Dog.bark 실행
```
검색 없이 **인덱스 한 번 → O(1)**.

#### itable (Interface Method Table)

**정의**: 인터페이스 메서드 dispatch 전용 테이블. **(인터페이스, 메서드) → 함수 포인터** 매핑.

**왜 vtable로 안 되나** — vtable의 핵심 가정 "같은 시그니처는 부모-자식 사이에 같은 인덱스"가 인터페이스에서 깨진다:
1. 한 클래스가 여러 인터페이스를 implement → 인터페이스끼리 같은 인덱스에 다른 메서드가 있으면 충돌.
2. 같은 인터페이스를 여러 클래스가 implement → 클래스마다 인터페이스 메서드의 vtable 위치가 달라질 수 있음 → 호출자가 인덱스를 못 정함.

해결: **인덱스 대신 (interface, method) 쌍을 키**로 메서드 포인터를 찾는다.

```
Dog.itable:
  ┌─────────────────────────────────────────────┐
  │ Walkable interface 구역                       │
  │   [0] Walkable.walk     → Dog.walk 포인터     │
  │   [1] Walkable.stop     → Dog.stop 포인터     │
  ├─────────────────────────────────────────────┤
  │ Trainable interface 구역                      │
  │   [0] Trainable.train   → Dog.train 포인터    │
  │   [1] Trainable.reward  → Dog.reward 포인터   │
  └─────────────────────────────────────────────┘
```

**호출 흐름**:
```
w.walk() where w: Walkable = new Dog()
  1. w → Dog의 InstanceKlass → itable
  2. itable에서 "Walkable" 구역을 찾는다 (검색)
  3. 그 구역의 walk 인덱스에서 Dog.walk 포인터 꺼냄
  4. jump
```
vtable보다 **인터페이스 구역 찾는 한 단계가 더 든다** → 약간 느림. 단, JIT의 inline cache로 거의 0에 가깝게 만든다(아래).

#### vtable vs itable 한 줄 비교

| 항목 | vtable | itable |
|---|---|---|
| 용도 | `invokevirtual` (클래스 타입 dispatch) | `invokeinterface` (인터페이스 타입 dispatch) |
| 키 | 정수 인덱스 1개 | (interface, 메서드 인덱스) 쌍 |
| 검색 | O(1), 인덱스 한 번 | O(인터페이스 수) — 인터페이스 구역 찾기 |
| 부모 상속 | 부모 vtable을 복사해 확장 | 각 인터페이스 구역을 따로 채움 |

#### Inline Cache — itable이 실전에서 사실상 vtable만큼 빠른 이유

JIT는 각 호출 사이트마다 **최근 dispatch 결과를 캐싱**:

```
첫 호출:   w.walk()  →  itable 검색  →  Dog.walk  (캐시: "type=Dog → Dog.walk")
두 번째:   w.walk()  →  캐시 적중. type 확인만 하고 바로 점프. itable 검색 생략.
```

- **Monomorphic** (한 타입만 들어옴): 캐시 적중 → 거의 vtable과 동일 속도. JIT가 인라인까지 시도.
- **Bimorphic** (두 타입): 두 캐시 슬롯 비교 → 적중 시 점프. 여전히 빠름.
- **Megamorphic** (3개+ 타입): 캐시 포기 → 매번 itable 풀스캔. **인라인도 못 함 → 성능 급락**.

> **운영 관점**: hot path에 `List`·`Collection` 같은 인터페이스 타입으로 너무 다양한 구현(ArrayList, LinkedList, HashSet 어댑터 등)을 섞어 받으면 megamorphic이 된다. JIT 로그(`-XX:+PrintInlining`)에 `callee is megamorphic, inlining cancelled`가 찍히면 바로 그 자리.

#### HotSpot 안에서의 실제 모습

```cpp
// instanceKlass.hpp (개략)
class InstanceKlass : public Klass {
  int _vtable_len;       // vtable 슬롯 개수
  int _itable_len;       // itable 항목 수
  // 실제 vtable[]과 itable[]은 InstanceKlass 메모리 바로 뒤에 inline
};
```

InstanceKlass 객체의 메모리 레이아웃:
```
[InstanceKlass 본체][vtable 슬롯들][itable 슬롯들][nonstatic_oop_maps]...
```

한 InstanceKlass에 vtable·itable·GC oop map까지 모두 inline으로 붙어있는 게 HotSpot이 dispatch와 GC를 모두 빠르게 처리하는 비결.

#### 한 줄 요약

> **vtable**: "이 시그니처를 부르면 어느 함수가 실행될지를 **인덱스 한 번**으로 찾는 표".
> **itable**: "이 인터페이스의 이 시그니처를 부르면 어느 함수가 실행될지를 **(인터페이스, 메서드) 쌍**으로 찾는 표".
> 둘 다 Resolution이 "어떤 시그니처를 부를지"를 결정한 다음, **실제 어느 구현으로 갈지를 즉석에서 결정하는 dispatch 도구**다.

---

## 📜 5단계: 역사

### Java 1.0 — Verification 도입

처음부터 verification은 핵심. Java applet 보안 모델의 기반.

### Java 1.4 — Class Data Sharing 첫 등장 (Sun JDK)

자주 사용되는 시스템 클래스의 메타데이터를 archive로 묶어 다음 실행 시 재사용 → startup 가속.

### Java 5 — Stack Map Type Inference

Type inference 알고리즘 표준화. JVMS §4.10.2.

### Java 6 (2006) — StackMapTable + Split Verifier

- **StackMapTable** attribute 도입 (Code attribute의 sub-attribute).
- 두 종류 verifier가 공존: **old type inference**(compatibility 경로) + **new type checker**(StackMapTable 기반, fail-fast).
- JDK 6부터 **new verifier가 도입되고 StackMapTable 기반 검증이 일반화**됐다. 다만 "어떤 `-target` 조합이면 정확히 StackMapTable이 생긴다"는 식의 단정은 컴파일러·옵션 조합마다 예외가 있어 피한다 — JDK 7부터 빠지면 verify 실패로 강제된다(다음 항목).

### Java 7 (2011) — StackMapTable 필수

`-target 1.7`+ 클래스에서 StackMapTable 없으면 verify 실패.
JSR/RET 명령 (그 옛 finally 구현) 폐기.

### Java 8 — invokespecial 변경

Interface default method 도입과 함께 invokespecial의 의미 확장:
- super.defaultMethod() 호출 시 직접 super interface의 default method 호출.
- invokespecial이 interface method도 받을 수 있게.

### Java 11 — invokevirtual + Nest Access

같은 nest 안의 private 메서드를 invokevirtual로 직접 호출 가능. resolution 단계에서 NestHost/NestMembers 확인.

### Java 11 (2018) — Dynamic Class-File Constants (JEP 309)

`CONSTANT_Dynamic` (CP tag 17, "condy") 도입. invokedynamic과 유사한 부트스트랩 메커니즘으로 **상수도 런타임에 동적 계산**할 수 있게 됨. ClassFile 포맷 변경이라 JEP는 Java 11에서 ClassFile 버전 55에 정식 반영됐다.

### Java 17 — Sealed Class Resolution

Resolution 시 PermittedSubclasses 확인 — 허용 안 된 클래스가 sealed 클래스를 상속하면 `IncompatibleClassChangeError`.

---

## ⚔️ 6단계: 꼬리질문 트리

### Q1. Linking의 3단계를 설명하세요.

**예상 답변**:
> Verification, Preparation, Resolution.
> - **Verification**: ClassFile 구조 → 의미적 일관성 → bytecode 타입 안전성의 3 Pass로 구성. JDK 6+에서는 StackMapTable로 가속. (심볼릭 참조 해소는 verification이 아니라 Resolution 단계의 일.)
> - **Preparation**: static 필드에 default 값(0, null, false) 할당. 사용자 코드 실행 X.
> - **Resolution**: 심볼릭 참조를 직접 참조로 변환. lazy + caching.

#### 🪝 꼬리 Q1-1: "Preparation에서 static final도 default 값이 들어가나요?"

**예상 답변**:
> 케이스 분리.
> - `static final int X = 10;` (compile-time constant): ClassFile에 `ConstantValue` attribute. Preparation에서 바로 10 할당.
> - `static final int Y = compute();`: ConstantValue 없음. Preparation에서 0, Initialization에서 compute() 결과.
> - `static final String S = "hi"`: literal이라 ConstantValue. 바로 "hi".
> - `static final String S = new String("hi")`: ConstantValue 아님.

##### 🪝 꼬리 Q1-1-1: "ConstantValue가 ClassFile에 박히면 어떤 부작용이 있나요?"

**예상 답변**:
> 그 상수를 참조하는 다른 클래스의 ClassFile에 값이 **직접 인라인**된다.
> ```java
> // A.java
> class A { public static final int VERSION = 1; }
>
> // B.java
> class B { void print() { System.out.println(A.VERSION); } }
> ```
> B.class의 bytecode에 `bipush 1`이 들어감 (A.VERSION을 동적으로 안 읽음).
> 만약 A의 VERSION을 2로 바꾸고 A만 재컴파일하면, B는 여전히 1을 출력 — **재컴파일 필요**.
> 운영 함정: API의 public static final을 가볍게 바꾸면 dependent 모듈을 모두 재컴파일하지 않으면 깨짐.

### Q2. Verification은 무엇을 검증하나요?

**예상 답변**:
> 4 Pass:
> 1. ClassFile 포맷 (magic, version, CP 구조).
> 2. 의미적 일관성 (final 클래스 상속 금지, interface 제약 등).
> 3. ★ Bytecode 타입 안전성 ★ — StackMapTable과 비교.
> 4. 심볼릭 참조 유효성 (Resolution과 같이).

#### 🪝 꼬리 Q2-1: "Pass 3 bytecode verification이 정확히 뭘 보장하나요?"

**예상 답변**:
> 1. 모든 instruction이 valid opcode.
> 2. operand stack overflow/underflow 없음.
> 3. local variable 인덱스가 max_locals 안.
> 4. 각 instruction이 받는 stack 타입이 적합 (예: iadd는 int 두 개).
> 5. 분기 대상이 valid instruction 시작.
> 6. 메서드 종료 시 stack 상태 일관 (return 타입과 매칭).
> 7. `subroutine` (옛 jsr/ret) 사용 시 (JDK 6 이하) 일관성.
>
> 즉 verified bytecode는 **native crash를 일으킬 수 없다**.

##### 🪝 꼬리 Q2-1-1: "그런데 verification을 우회하는 방법이 있나요?"

**예상 답변**:
> 1. **`-Xverify:none`** (또는 `-noverify`): JDK 13까지 가능, JDK 13에서 deprecated, 21에서도 동작은 함. prod에서 절대 금지.
> 2. **`-Xverify:remote`**: remote-loaded (network) 클래스만 verify, local은 skip — 위험.
> 3. **`Unsafe.defineAnonymousClass`** (deprecated, JDK 17에서 제거) 또는 hidden class: 일부 verify 우회.
> 4. **JNI agents**: 클래스 transformation 후 verify가 다시 실행됨 (회피 어려움).
> 5. **Native code**: native 함수는 verify 안 됨, JVM 안전성 깰 수 있음.
>
> 우회는 가능하지만 **모든 안전성 보장이 무효**. 잘못된 bytecode 실행 시 segfault / 메모리 손상 / 보안 취약점.

###### 🪝 꼬리 Q2-1-1-1: "운영 환경에서 -Xverify:none을 켜면 startup이 얼마나 빨라지나요?"

**예상 답변**:
> 측정치마다 다르지만 일반적으로 5~15% 정도 startup 단축.
> JDK 6+ StackMapTable 도입 후 verify가 매우 빨라져서 효과가 크지 않음 (옛날엔 30%+).
> 또한 **AppCDS** (Application Class Data Sharing) + Generational ZGC가 더 큰 startup 가속을 제공하므로, verify 끄는 것보다 그쪽이 권장.
> Container/Serverless 환경에서는 GraalVM Native Image나 Project Leyden이 더 근본적 해결.

### Q3. StackMapTable이 도입된 이유는?

**예상 답변**:
> JDK 5 이하: verifier가 fixed-point iteration으로 type inference. O(n²)~O(n³). 큰 메서드/많은 메서드일 때 매우 느림.
> JDK 6: javac가 미리 각 basic block의 stack/locals 타입을 계산해서 StackMapTable attribute에 저장. Verifier는 linear (O(n))로 검증.

#### 🪝 꼬리 Q3-1: "javac가 가짜 StackMapTable을 만들어 넣으면 verifier를 속일 수 있나요?"

**예상 답변**:
> 안 됨. Verifier는 **현재 상태에서 다음 frame으로의 transition이 valid한지** 검사.
> 가짜 frame이 명시되어도 시뮬레이션 결과와 불일치하면 `VerifyError`.
> 즉 StackMapTable은 **힌트**일 뿐, 검증을 우회하지 않음.

### Q4. Resolution은 언제 일어나나요?

**예상 답변**:
> Lazy. 해당 reference를 처음 사용하는 instruction이 실행될 때.
> 예: `invokevirtual Foo.bar`가 처음 실행되면 그때 Foo와 bar 메서드를 resolve.
> 결과는 CP에 cache되어 두 번째부터 즉시 사용.

#### 🪝 꼬리 Q4-1: "그럼 클래스가 로드되어도 그 안의 메서드 참조는 resolve 안 되어 있다?"

**예상 답변**:
> Yes. Loading + Verification + Preparation까지는 메서드 호출이 안 일어남.
> Initialization 시 `<clinit>`이 실행되면서 호출되는 메서드들이 그때 resolve.
> static initializer가 없거나 짧으면, 메서드 reference들은 첫 호출까지 미해결 상태.

##### 🪝 꼬리 Q4-1-1: "Lazy resolution이 만드는 함정은?"

**예상 답변**:
> 1. **에러가 늦게 발견됨**: 컴파일 시 OK였지만 dependency 변경으로 깨진 reference가 있어도, 실행 도중에 발견 (`NoSuchMethodError`).
> 2. **불완전한 fail-fast**: startup에서 모든 reference 검증하면 빠르게 알 수 있지만, lazy면 production에서 한참 후에 발견.
> 3. **테스트 어려움**: 일부 경로만 타는 코드의 resolution 실패가 운영에서 드러남.
> 회피: `-Xverify:all` + 의도적 warmup으로 모든 클래스를 미리 로드.

### Q5. NoClassDefFoundError와 ClassNotFoundException의 차이?

**예상 답변**:
> - **ClassNotFoundException**: checked. `Class.forName()`, `ClassLoader.loadClass()`처럼 명시적으로 클래스를 찾을 때 실패.
> - **NoClassDefFoundError**: error (unchecked). 컴파일 시점엔 존재했지만 런타임에 사라진 경우. Resolution 단계 실패.
>
> 시나리오:
> - CNFE: classpath에 누락, plugin 못 찾음.
> - NCDFE: 빌드 시 있던 jar이 deploy에서 빠짐. 또는 static initializer 실패한 클래스 재접근.

#### 🪝 꼬리 Q5-1: "ExceptionInInitializerError가 나면 그 클래스는 어떻게 되나요?"

**예상 답변**:
> 그 클래스는 영구히 **erroneous** 상태로 마킹됨.
> 이후 그 클래스에 대한 **모든 접근**(메서드 호출, 필드 접근, instanceof 등)에서 `NoClassDefFoundError` throw.
> 첫 stacktrace의 ExceptionInInitializerError가 진짜 원인이고, 그 다음부터는 NCDFE만 보임 — **로그 첫 번째를 못 잡으면 영원히 헤매는 함정**.
> 회복 불가 — 그 ClassLoader 폐기 후 새 CL로 다시 로드해야 함.

##### 🪝 꼬리 Q5-1-1: "왜 그렇게 가혹한가요? 다시 init 시도해도 되지 않나요?"

**예상 답변**:
> 1. **JLS 12.4.2**: Initialization은 단 한 번. 재시도 명세상 없음.
> 2. **부분 초기화 위험**: static 블록이 일부만 실행되고 예외가 나면, 일부 static 필드가 잘못된 값 — 그 상태를 살리는 것보다 클래스 전체를 dead로 처리하는 게 안전.
> 3. **Thread-safety**: 여러 스레드가 동시에 init 시도 → 첫 시도가 실패하면 다른 스레드도 같은 결과를 봐야 함.

### Q6. (Killer) JDK 21에서 클래스 로딩 / linking / initialization 시간을 줄이려면 어떤 옵션이 있나요?

**예상 답변** (여러 옵션 조합):
> 1. **AppCDS** (`-XX:SharedArchiveFile=...`): 사용 클래스들을 archive로 묶어 다음 실행 시 파싱/verify 스킵.
>    - 빌드: `java -XX:DumpLoadedClassList=classes.lst MyApp`
>    - 사용: `java -XX:SharedArchiveFile=archive.jsa MyApp`
> 2. **Class Data Sharing의 confined area**: 시스템 클래스 외 사용자 클래스도 포함 (JDK 13+).
> 3. **CDS + Class Loader Hierarchy**: 여러 CL의 클래스를 archive (JDK 13+).
> 4. **AOT (deprecated)** → **GraalVM Native Image** 또는 **Project Leyden**.
> 5. **`-Xverify:none`** (production 금지지만 실험용): verify 스킵.
> 6. **`-XX:+UseAppCDS`** (JDK 11에서 기본 on).
> 7. **`-XX:+EnableJVMCI`** + GraalVM JIT.
> 8. **Tiered Compilation 조정** (`-XX:-TieredCompilation`로 첫 컴파일 시간 단축 가능, throughput은 감소).

#### 🪝 꼬리 Q6-1: "AppCDS가 정확히 무엇을 archive하나요?"

**예상 답변**:
> 1. **InstanceKlass 객체** (메타데이터): 파싱된 클래스 구조.
> 2. **Constant Pool**: 모든 CP 엔트리 (resolution 결과 포함).
> 3. **Method bytecode** + StackMapTable.
> 4. **vtable / itable**.
> 5. **Klass에 연관된 oop들** (java.lang.Class mirror 일부).
>
> 다음 실행 시:
> - archive 파일을 **mmap**으로 매핑 → Heap에 로드.
> - 파싱 / verification 스킵.
> - linking 일부 결과 재사용.

##### 🪝 꼬리 Q6-1-1: "AppCDS로 archive한 클래스를 수정하면 어떻게 되나요?"

**예상 답변**:
> Archive 파일의 timestamp/checksum과 실제 .class의 그것이 다르면 archive invalidate.
> JVM이 archive 사용 거부 → 일반 로딩으로 fallback (warning 메시지).
> 따라서 dev 환경에서는 archive 사용 안 하는 게 일반적, prod에서 immutable image에서 사용.

### Q7. invokedynamic의 resolution은 일반 메서드 호출과 어떻게 다른가요?

**예상 답변**:
> 일반 invokevirtual/invokespecial 등: CP의 Methodref를 resolve → 호출.
> invokedynamic: CP의 `InvokeDynamic` 엔트리는 **bootstrap method 정보**를 가리킴 (BootstrapMethods attribute).
> 첫 호출 시:
> 1. Bootstrap method 호출 (예: `LambdaMetafactory.metafactory`).
> 2. Bootstrap method가 `CallSite` 객체 반환.
> 3. CallSite의 target MethodHandle을 호출 사이트에 link.
> 4. 이후 호출은 link된 target으로 직접.
>
> 즉 invokedynamic은 **첫 호출에 사용자 정의 link 로직** 실행 → bytecode 변경 없이 동적 dispatch 가능.

#### 🪝 꼬리 Q7-1: "MutableCallSite와 ConstantCallSite의 차이?"

**예상 답변**:
> - **ConstantCallSite**: target이 한 번 설정되면 불변. JIT이 inline 최대화. Lambda 호출 사이트.
> - **MutableCallSite**: target 교체 가능. Dynamic 언어(JRuby 등)에서 사용. 교체 시 다른 스레드에 visibility 보장을 위해 `SwitchPoint` 메커니즘.
> - **VolatileCallSite**: 매번 target을 다시 읽음. 거의 안 씀.

---

## 🔗 다음 단계

- → [04. Initialization & Class Unload](./04-initialization-and-unload.md): clinit 실행 순서, JLS 12.4.2 lock, CL unload

## 📚 참고

- **JVMS §5.4 Linking**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.4
- **JVMS §4.10 Verification of class Files**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.10
- **JLS §13 Binary Compatibility**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html
- **JEP 309 Dynamic Class-File Constants**: https://openjdk.org/jeps/309
- **JEP 310 AppCDS**: https://openjdk.org/jeps/310
- **JEP 350 Dynamic CDS Archives**: https://openjdk.org/jeps/350
- **HotSpot verifier.cpp**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/classfile/verifier.cpp
- **HotSpot linkResolver.cpp**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/interpreter/linkResolver.cpp
