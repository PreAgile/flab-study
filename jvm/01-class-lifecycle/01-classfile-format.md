# 01-01. ClassFile 포맷 — JVM의 입력 파일

> "ClassFile 첫 4바이트가 CAFEBABE다"라고 답하는 건 입문자.
> 시니어가 ClassFile을 안다는 건 `UnsupportedClassVersionError`, `NoSuchMethodError`, Lambda Metaspace 누수, HotSwap 실패 같은 사고가 났을 때 `javap -v` 한 번으로 5분 안에 원인 가설을 세우는 능력이다.
> 이 문서는 byte offset을 외우지 않는다. 어떤 ClassFile 지식이 어떤 production 문제를 푸는지만 매핑한다.

---

## 이 문서의 사용법

이 문서는 **면접용 마인드맵**을 따라 선형으로 펼친 구조다. 학습 순서 = 면접 답변 순서 = 백지에 그리는 순서.

1. **0장 마인드맵을 먼저 외운다** — 루트 한 문장 + 6가지 가지 + 각 가지의 키워드 3개.
2. **1~6장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 정확히 대응.
3. **7장 면접 워크플로우로 검증** — 질문을 보면 어느 가지로 가야 하는지 매핑.
4. **8장 꼬리질문으로 깊이 점검**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"ClassFile은 javac가 만들고 JVM이 읽는 단일 입력 파일이다. 7개 블록의 순차적 묶음이고, 그 중심은 Constant Pool이라는 단일 출처와 메서드 본문을 담는 Code attribute다."**

이 한 문장에서 모든 답변이 출발한다. 어떤 질문이 와도 이 문장부터 말하고 적절한 가지로 분기.

### 6개 가지 — 순서를 외운다

```
                  [ROOT: ClassFile = javac 출력 = JVM 입력]
                                  │
       ┌──────────┬───────────────┼───────────────┬──────────┬──────────┐
       │          │               │               │          │          │
      ① WHY     ② WHAT          ③ HOW           ④ 운영     ⑤ 진화     ⑥ 도구
   javac결과물  7블록 구조      Code/Descriptor  진단시나리오 JDK별변천 javap/Bytecode
       │          │               │               │          │          │
       │     ┌────┼────┐      ┌───┼───┐       ┌───┼───┐      │          │
   책임경계  ① Header  ② CP    Code      Descriptor UCVE NSME Lambda    Signature  ASM/BB
   javac만   ③ Access ④ Iface  attribute  문법      Bridge HotSwap     Record     ClassFileAPI
   까지      ⑤ Field  ⑥ Method (max_stack)         CGLib/Mockito       Sealed     -g 옵션
            ⑦ ClassAttr                                                Nest
```

### 가지별 핵심 키워드 (각 가지 3개씩만)

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① WHY 책임 경계** | javac 산출물 | 락도 안 잡음 | clinit 합성까지만 |
| **② WHAT 7블록** | 헤더 / CP / Access | Field / Method | Class Attribute |
| **③ HOW Code/Descriptor** | Code attribute | Descriptor 문법 | invoke* 5종 |
| **④ 운영 진단** | UCVE / NSME | Lambda Metaspace | Bridge / HotSwap |
| **⑤ 진화** | Signature(JDK5) | invokedynamic(JDK7) | Record/Sealed/Nest |
| **⑥ 도구** | javap -v | ASM/ByteBuddy | Class-File API |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 질문에 맞는 가지 1개 선택 → 그 가지의 키워드 3개 순서대로 설명 → 듣는 사람의 관심에 따라 인접 가지로 확장

---

## 1. 가지 ①: WHY — 책임 경계 (javac가 어디까지 하나)

### 1.1 핵심 질문

> "ClassFile은 누가 만드는가? 클래스 라이프사이클 5단계 중 어디에 위치하는가?"

### 1.2 키워드 1 — javac의 산출물

```
.java  ──javac──►  .class (ClassFile)  ──ClassLoader.defineClass──► InstanceKlass (Metaspace)
                       │                          │
                       │                          ▼
                       │                  Linking (Verify, Prepare, Resolve)
                       │                          │
                       │                          ▼
                       │                  Initialization (<clinit>)
                       │                          │
                       │                          ▼
                       │                  Usage (메서드 호출, 객체 생성)
                       │                          │
                       │                          ▼
                       └─────────────────► Unloading (ClassLoader unreachable)
                       ★ 이 챕터 ★
```

ClassFile은 라이프사이클의 **Loading 진입 직전, JVM의 입력 자체**다. javac가 만들고 끝, 그 다음은 ClassLoader와 JVM의 몫.

### 1.3 키워드 2 — javac는 락도 안 잡고 Class 객체도 안 만든다

| 이 챕터가 다루는 것 (javac의 책임) | 이 챕터가 다루지 않는 것 |
|---|---|
| `.class` 파일 포맷 (magic, CP, attribute, descriptor) | ClassLoader가 어떻게 읽어들이나 → 02장 |
| `<clinit>` 메서드가 **합성되어 .class에 박히는 시점** | `<clinit>`이 **실행되는 시점/락 절차** → 04장 |
| ConstantValue 인라이닝, 메서드 디스크립터, BootstrapMethods | Verification/Resolution이 실제로 도는 시점 → 03장 |

핵심 한 줄: **javac는 `.class`를 만들고 끝. 락도 안 잡고, `Class` 객체도 안 만들고, `<clinit>`을 실행하지도 않는다.** 그 모든 일은 런타임에 ClassLoader(02장)와 JVM 본체(03·04장)의 몫.

### 1.4 키워드 3 — clinit 합성까지만

```java
class Foo {
    static int x = 10;
    static { System.out.println("init"); }
}
```

javac는 이 두 줄을 합쳐 `<clinit>()V`라는 합성 메서드를 ClassFile에 박는다. 그러나 **실행 시점**(누가 언제 호출하는가, 락은 어떻게 잡는가)은 04장에서 다룬다. javac의 책임은 "합성된 코드를 ClassFile에 넣기"까지.

### 1.5 이 챕터를 마치면 production에서 할 수 있는 것

1. `UnsupportedClassVersionError`를 받았을 때 어떤 라이브러리가 어떤 JDK로 빌드됐는지 `javap`로 식별
2. `NoSuchMethodError`가 정말 메서드 없음인지 **descriptor 불일치**인지 구분
3. Lambda를 많이 쓰는 앱의 Metaspace 증가가 정상인지 누수인지 판단 (invokedynamic + LambdaMetafactory + hidden class)
4. Generics erasure와 `Signature` attribute, **bridge method**가 stack trace에 보이는 이유 설명
5. HotSwap이 메서드 body는 바꾸지만 시그니처/필드 추가는 못 하는 ClassFile-level 이유 설명
6. ASM/ByteBuddy/Mockito가 동적 생성한 클래스의 stack trace 패턴 식별
7. `javap -v` 출력을 읽고 stack trace의 `Foo.java:42`가 어느 bytecode offset인지 매칭

---

## 2. 가지 ②: WHAT — ClassFile 7개 블록

### 2.1 핵심 질문

> "ClassFile은 어떤 구조로 되어 있는가? 각 블록은 왜 존재하는가?"

### 2.2 키워드 1 — 7개 블록의 정체

```
┌─────────────────────────────────┐
│ ① 헤더 (magic + version)         │  10바이트. magic + minor + major + cp_count
├─────────────────────────────────┤
│ ② Constant Pool                  │  가장 큼. 모든 이름·시그니처·문자열·숫자의 단일 출처
├─────────────────────────────────┤
│ ③ Access Flags + this/super      │  클래스 자체의 modifier + 자기/부모 이름
├─────────────────────────────────┤
│ ④ Interfaces                     │  implements 목록 (CP 인덱스 배열)
├─────────────────────────────────┤
│ ⑤ Fields                         │  필드 선언: access + 이름 + descriptor + attributes
├─────────────────────────────────┤
│ ⑥ Methods                        │  메서드 선언 + 본문(Code attribute)
│   └ Code attribute               │  ★ bytecode + max_stack/locals + exception_table
│                                  │    + LineNumberTable (stack trace의 line number 출처)
├─────────────────────────────────┤
│ ⑦ Class Attributes               │  SourceFile, BootstrapMethods, NestHost, Record, ...
└─────────────────────────────────┘
```

### 2.3 키워드 2 — Constant Pool은 단일 출처(single source)

ClassFile의 다른 모든 부분은 "이름"이나 "리터럴 값"을 직접 적지 않고 **CP에 한 번 정의된 엔트리를 인덱스로 참조**한다. `"Hello"` 문자열을 100번 써도 CP에는 1개 엔트리. 메서드 호출 `invokevirtual Foo.bar()`도 bytecode에 "Foo.bar"가 직접 들어가지 않고 CP 인덱스만.

```
Methodref (tag 10)               예: System.out.println(String) 호출
  ├─ class_index ──► Class (tag 7)
  │                    └─ name_index ──► Utf8 "java/io/PrintStream"
  └─ name_and_type_index ──► NameAndType (tag 12)
                              ├─ name_index ──► Utf8 "println"
                              └─ descriptor_index ──► Utf8 "(Ljava/lang/String;)V"
```

**왜 단일 통합 테이블인가**:
1. **중복 제거** — 같은 문자열을 N번 써도 CP에 1개. 파일 크기 ↓.
2. **고정 길이 명령** — bytecode 명령어가 가변 길이 문자열 대신 CP 인덱스(2바이트)만 안고 다님 → 인터프리터/JIT 빠름.
3. **Linking 분리** — Resolution이 CP 엔트리당 한 번만 처리 → 캐시 친화.

핵심 관찰:
- 모든 이름/시그니처는 **Utf8을 끝점**으로 가진다.
- **NameAndType은 (이름, 시그니처) 쌍** — overload된 메서드를 구분하는 단위.
- Methodref vs InterfaceMethodref 분리는 **vtable vs itable** dispatch 차이 때문.
- **InvokeDynamic 엔트리는 BootstrapMethods attribute 인덱스를 들고 있다** — Lambda Metaspace 추적의 핵심.

### 2.4 키워드 3 — Code attribute가 메서드 본문

⑤ Fields는 단순한 declaration(access + 이름 + descriptor + attributes). 그러나 ⑥ Methods는 본문을 가져야 한다. javac는 메서드 본문을 attributes 중 **Code attribute** 안에 넣는다.

```
Code attribute 내부:
- max_stack       : operand stack 최대 깊이 (Frame 크기 결정)
- max_locals      : 로컬 변수 슬롯 수
- bytecode        : 실제 명령 바이트 시퀀스
- exception_table : try-catch 범위 (start_pc, end_pc, handler_pc, catch_type)
- attributes 중   :
    - LineNumberTable      : ★ stack trace의 line number 출처
    - LocalVariableTable   : 디버거가 변수 이름 보는 source
    - StackMapTable        : Verifier(03장) 빠른 검증용
```

→ **stack trace의 line number는 LineNumberTable에서 온다**는 사실이 운영 직결.

### 2.5 외울 필요는 없지만 본질만 알아야 할 다섯 가지

> **원칙**: hex 값, 비트 자릿수, tag 번호 같은 표면 값은 javap가 풀어준다. 그러나 **왜 존재하고 어떻게 만들어졌는지**는 알아야 도구 출력을 읽을 수 있다.

#### (1) Magic Number — 파일 타입 시그니처

ClassFile 첫 4바이트는 다른 파일 형식과 구분되는 universal pattern. JVM은 이 값이 아니면 더 읽지 않고 `ClassFormatError`. James Gosling이 hex로 표현 가능한 영어 단어 중에 골랐다는 일화. 운영 의미: "ClassFormatError = 파일이 .class가 아니거나 손상됨" 한 줄이면 충분. `xxd | head -1`이나 `file Foo.class` 명령이 자동 확인.

#### (2) Constant Pool tag 18종

JDK 1.0~9까지 점진적으로 추가된 18가지 엔트리 종류 (tag 2, 13, 14는 reserved 빈자리). 운영자가 알아야 할 것: **모든 이름이 Utf8을 끝점으로 갖는다**, **NameAndType이 overload 구분의 단위**, **InvokeDynamic이 BootstrapMethods 인덱스를 들고 있다는 사실**. tag 번호는 javap가 `Methodref`, `InvokeDynamic` 같은 이름으로 풀어줌.

#### (3) access_flags 비트마스크

`public`, `static`, `final`, `abstract` 같은 modifier를 2바이트 비트마스크로 인코딩. 운영에서 중요한 것은 두 가지:
- **ACC_SYNTHETIC**: javac가 합성한 것 (소스에 없음). 예: inner class용 `access$000`, lambda body `lambda$main$0`, enum `values()`/`valueOf()`.
- **ACC_BRIDGE**: synthetic 중에서 covariant return / generics erasure로 생성된 위임 메서드. → stack trace에 같은 메서드가 두 번 나오면 이 플래그가 단서 (가지 ④ 시나리오).

`ACC_SUPER`는 JDK 1.0의 `invokespecial` 버그 수정 시 도입된 historical flag — JDK 24에서 무시 결정.

#### (4) Modified UTF-8

ClassFile의 Utf8 엔트리는 일반 UTF-8이 아닌 변형. 두 가지 차이:
- **`U+0000`을 2바이트(`0xC0 0x80`)로 인코딩** — 1995년 JNI와 C 코드의 null-terminated string 호환을 위해.
- **BMP 외부 문자(emoji 등)는 surrogate pair로 변환 후 각각 3바이트** — Java 내부 String(UTF-16)과 자연스러운 매핑.

운영 함정: `String.getBytes(UTF_8)`는 일반 UTF-8, `DataOutputStream.writeUTF()`가 mUTF-8. 한국어/일본어/중국어 식별자는 BMP 안이라 둘이 동일 → 대부분 문제 없음.

#### (5) Long/Double이 CP 슬롯 2개

JVMS §4.4.5가 **명시적으로 "poor choice"라고 인정**한 드문 케이스. 1995년 4바이트 정렬 직관의 산물. 30년 호환성 때문에 고치지 못함. 운영자는 ASM/ByteBuddy/Class-File API가 추상화하므로 직접 신경 안 써도 됨.

### 2.6 다섯 개념의 공통 메시지

이 다섯 항목은 모두 **JVM 설계자들의 시대적 결정**(1995년 JNI 호환, C 코드 호환, 4바이트 정렬 직관, 매직 넘버 관습)의 결과다. 30년 후 운영자가 매일 만지는 것이 아니라, **도구가 추상화하는 layer**. 운영자의 의무는 표면 hex 값을 외우는 것이 아니라, **이 layer 뒤에 무엇이 있는지** 정확히 이해해서 도구 출력을 읽는 것.

---

## 3. 가지 ③: HOW — Code attribute와 Descriptor

### 3.1 핵심 질문

> "메서드 본문은 어떻게 저장되고, 메서드 시그니처는 어떻게 인코딩되는가?"

### 3.2 키워드 1 — Code attribute의 내부 구조

`javap -v HelloWorld`의 main 메서드 출력:

```text
public static void main(java.lang.String[]);
  descriptor: ([Ljava/lang/String;)V          ← 시그니처 (descriptor)
  flags: (0x0009) ACC_PUBLIC, ACC_STATIC
  Code:                                        ← Code attribute
    stack=2, locals=1, args_size=1             ← max_stack, max_locals
       0: getstatic     #7     // System.out
       3: ldc           #13    // String Hello, World!
       5: invokevirtual #15    // PrintStream.println:(Ljava/lang/String;)V
       8: return
    LineNumberTable:                           ← stack trace 해석의 핵심
      line 3: 0      ← bytecode offset 0~4 = 소스 line 3
      line 4: 8      ← bytecode offset 5~7 = 소스 line 4
```

**핵심 관찰**:
- `max_stack`, `max_locals`는 javac가 미리 계산 → JVM이 Frame을 정확한 크기로 한 번에 할당 (Stack 챕터 참조).
- 명령어는 `opcode + CP index` 형태로 1~3바이트.
- **LineNumberTable이 없으면 stack trace에 line 안 나옴**. `-g:none`으로 컴파일하면 production 디버깅 지옥.

### 3.3 키워드 2 — Descriptor 문법

**시니어가 가장 자주 마주치는 ClassFile 디테일이 descriptor다**. `NoSuchMethodError` 디버깅의 결정적 정보.

```
Field descriptor (타입 1개):
  B = byte           Z = boolean
  I = int            J = long      ← long이 J인 이유: L은 객체 참조용
  F = float          D = double
  C = char           S = short
  Lpackage/Class;    = 객체 참조 (예: Ljava/lang/String;)
  [T                 = T 배열 (예: [I = int[], [[I = int[][])

Method descriptor:
  (ParamDescriptors) ReturnDescriptor
  V = void (return 전용)
```

**예시**:
```java
int main(String[] args)        → ([Ljava/lang/String;)I
void println(String s)          → (Ljava/lang/String;)V
long max(long a, long b)        → (JJ)J
Object[] toArray()              → ()[Ljava/lang/Object;
List<String> getNames()         → ()Ljava/util/List;    ← ★ Generics는 erasure로 사라짐!
```

**generics erasure의 흔적**: `List<String>`이 descriptor에서는 그냥 `Ljava/util/List;`. reflection은 `Method.getReturnType()`만으로는 generic 정보를 못 얻고, 별도 **Signature** attribute의 `getGenericReturnType()`을 써야 한다.

### 3.4 키워드 3 — invoke 명령 5종

bytecode 명령어는 ~200개지만 시니어가 의식적으로 구분하는 건 **메서드 호출 5종**:

| 명령 | 사용처 | Production 의미 |
|---|---|---|
| `invokevirtual` | 일반 인스턴스 메서드 | vtable 기반, JIT에서 monomorphic 추적 |
| `invokespecial` | 생성자, super, private | 정적 바인딩, JIT 인라인 친화 |
| `invokestatic` | static 메서드 | 인스턴스 없음, 가장 단순 |
| `invokeinterface` | 인터페이스 메서드 | itable lookup, CHA로 monomorphic이면 vtable급 |
| `invokedynamic` | lambda, switch on String, String concat, record | BootstrapMethod → CallSite 캐시. **Lambda Metaspace 누수의 진원지** |

→ invokedynamic의 운영 의미는 가지 ④의 Lambda Metaspace 시나리오에서.

### 3.5 Constant Pool과 Code attribute의 연결

`javap -v`의 `#13`, `#15` 같은 인덱스는 모두 CP를 가리킨다.

```text
Constant pool:
   #13 = String             #14         // Hello, World!
   #14 = Utf8               Hello, World!
   #15 = Methodref          #16.#17     // PrintStream.println:(...)
```

bytecode의 `ldc #13`은 "CP[13]을 가져와 operand stack에 push"라는 의미. CP가 단일 출처라는 사실이 여기서 실제로 작동한다.

---

## 4. 가지 ④: 운영 — 진단 시나리오

### 4.1 핵심 질문

> "ClassFile 지식이 실제 production 문제를 어떻게 푸는가?"

### 4.2 키워드 1 — UnsupportedClassVersionError (UCVE)

#### 증상
```
java.lang.UnsupportedClassVersionError:
  com/foo/Service has been compiled by a more recent version of the Java Runtime
  (class file version 61.0), this version of the Java Runtime only recognizes
  class file versions up to 55.0
```

#### 진단 절차
```bash
unzip -p service.jar com/foo/Service.class > /tmp/Service.class
javap -v /tmp/Service.class | head -5
#   major version: 61   ← JDK 17로 컴파일됨
#   minor version: 0    (65535이면 preview)
```

#### major → JDK 매핑 공식

**JDK N → major = N + 44**. 한 번만 외우면 됨.
- 52 = 8, 55 = 11, 61 = 17, 65 = 21

#### 사고 흐름
1. major 숫자로 컴파일 JDK 식별
2. 운영 JDK 한계와 비교 ("up to 55.0" = JDK 11)
3. 빌드 환경(`pom.xml`, `build.gradle`의 `targetCompatibility`, `--release`) 점검
4. 항구적 fix: CI에 `maven-enforcer-plugin` 등으로 target version 검증

minor_version 65535 = `--enable-preview`로 컴파일. 정확히 같은 major + `--enable-preview`에서만 실행 허용.

### 4.3 키워드 2 — NoSuchMethodError (NSME)

#### 증상
```
java.lang.NoSuchMethodError:
  'java.util.List com.foo.Repository.findAll(java.lang.String)'
```

분명히 `findAll(String)`은 존재하는데도 실패.

#### 핵심: descriptor 불일치

JVM은 메서드를 **이름 + descriptor 페어**로 식별. descriptor 한 글자라도 다르면 다른 메서드.

#### 진단
```bash
# caller 쪽
javap -v Caller.class | grep -A 2 findAll
# 5: invokevirtual #25 // Repository.findAll:(Ljava/lang/String;)Ljava/util/List;

# callee 쪽
javap -v Repository.class | grep findAll
# public java.util.Collection findAll(java.lang.String);
#   descriptor: (Ljava/lang/String;)Ljava/util/Collection;    ← ★ Collection!
```

→ caller는 `List` return 가정해 컴파일, 라이브러리는 `Collection` return. **descriptor의 return type이 다르면 다른 메서드**.

흔한 원인: 라이브러리 버전 mismatch, return type 변경(특히 generics), overload 변경.

### 4.4 키워드 3 — Lambda Metaspace (invokedynamic + hidden class)

#### 증상
```
[gc] Metaspace: used 480M, capacity 512M, ...
java.lang.OutOfMemoryError: Metaspace
```

Lambda를 많이 쓰는 reactive/stream 코드.

#### Lambda가 ClassFile에 컴파일되는 방식

```java
Runnable r = () -> System.out.println("hi");
```

javac:
1. lambda body를 **private static `lambda$main$0`** 메서드로 추출
2. lambda 위치에 **`invokedynamic`** emit
3. `BootstrapMethods` attribute에 `LambdaMetafactory.metafactory(...)` 호출 정보 저장

```text
0: invokedynamic #2,  0     // InvokeDynamic #0:run:()Ljava/lang/Runnable;
BootstrapMethods:
  0: #34 REF_invokeStatic java/lang/invoke/LambdaMetafactory.metafactory:(...)
    Method arguments:
      #35 ()V
      #36 REF_invokeStatic Main.lambda$main$0:()V
      #37 ()V
```

#### 런타임 동작

1. 첫 invokedynamic 실행 시 `LambdaMetafactory.metafactory` 호출
2. metafactory가 **hidden class** (`Main$$Lambda$1/0x...`) 동적 생성. 이 클래스가 `Runnable`을 구현하고 `lambda$main$0` 위임
3. `CallSite`에 인스턴스 묶어 캐싱
4. 다음 실행은 O(1) — 캐시 재사용

#### 정상 vs 누수 구분

- **정상**: invokedynamic 사이트 수만큼 hidden class. 보통 수백~수천.
- **anonymous inner class와 차이**: `new Runnable() {...}`은 `Main$1.class` 디스크 파일이 생기는 anonymous class. lambda는 **hidden class** — 디스크 없음, ClassLoader 등록 안 됨, GC 가능.
- **의심**: hidden class가 시간에 비례해 증가 → 매번 다른 lambda factory가 만들어지는 코드 (희귀).

#### 진단
```bash
jcmd <pid> VM.classloader_stats | grep -i 'hidden\|lambda'
jcmd <pid> JFR.start name=cl duration=60s settings=profile filename=cl.jfr
jfr summary cl.jfr | grep ClassLoad
```

### 4.5 Bridge method가 stack trace에 나오는 이유

#### 증상
```
ClassCastException: class String cannot be cast to class Integer
  at com.foo.Comp.compare(Comp.java:...)
  at com.foo.Comp.compare(Comp.java:1)    ← ★ 같은 메서드가 2번?
```

#### 원인

```java
class IntComparator implements Comparator<Integer> {
    @Override
    public int compare(Integer a, Integer b) { ... }
}
```

Generics erasure 후:
- 인터페이스 raw type: `int compare(Object, Object)` descriptor `(Ljava/lang/Object;Ljava/lang/Object;)I`
- 우리 메서드: descriptor `(Ljava/lang/Integer;Ljava/lang/Integer;)I`

두 descriptor가 달라 인터페이스 컨트랙트 충돌. javac가 **bridge method** 자동 생성:

```text
public int compare(java.lang.Object, java.lang.Object);
  flags: (0x1041) ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC
  Code:
    0: aload_0
    1: aload_1
    2: checkcast     #23  // class java/lang/Integer    ← cast → 여기서 CCE!
    5: aload_2
    6: checkcast     #23
    9: invokevirtual #25  // compare(Integer, Integer)I  ← 진짜 메서드 위임
    12: ireturn
```

#### Signature attribute가 reflection의 generic source

```text
private java.util.List<java.lang.String> names;
  descriptor: Ljava/util/List;                              ← erasure 결과
  Signature: #16   // Ljava/util/List<Ljava/lang/String;>;  ← ★ 별도 attribute
```

→ `Field.getGenericType()`는 Signature attribute를 파싱해서 generic 복원. Erasure는 bytecode만, ClassFile에는 metadata 형태로 generic 정보가 남아 있다.

### 4.6 HotSwap의 한계

#### 증상
```
Hot Swap Failed: Operation not supported by the VM:
  hierarchy changes are not implemented
```

#### ClassFile-level 이유

JVMTI `RedefineClasses`가 허용하는 변경은 **메서드 body만**.

| 변경 | 표준 HotSwap | 이유 |
|---|---|---|
| 메서드 body 수정 | OK | Code attribute 안의 bytecode만 변경, 다른 메타데이터 영향 없음 |
| 메서드 추가/삭제 | 불가 | vtable, itable 변경 → 컴파일된 호출 사이트 무효화 |
| 필드 추가/삭제 | 불가 | 객체 layout 변경 → 기존 인스턴스 메모리 재배치 불가 |
| 상속 변경 | 불가 | 전체 vtable 재구성 |
| Annotation 변경 | △ (JDK 14+) | RuntimeVisibleAnnotations attribute만 |

**도구별 우회**: JRebel(자체 변환 layer), DCEVM(JVM 패치), Spring DevTools(ClassLoader 재시작 = fast restart). Production은 hot reload 안 함, rolling deploy로 해결.

### 4.7 ASM/ByteBuddy/Mockito stack trace 디버깅

#### 증상
```
at com.foo.Service$$EnhancerByCGLIB$$abc12345.findAll(<generated>)
at com.foo.Service$$FastClassByCGLIB$$def67890.invoke(<generated>)
```

#### 프레임워크 식별 패턴

| 도구 | Stack trace 흔적 | 동작 |
|---|---|---|
| CGLib | `$$EnhancerByCGLIB$$...` | 대상 클래스 subclass를 ASM으로 동적 생성 |
| JDK Dynamic Proxy | `$Proxy0`, `$Proxy1` | 인터페이스 기반 `java.lang.reflect.Proxy` |
| ByteBuddy | `$ByteBuddy$...` | CGLib 후속, 더 유연 |
| Mockito (inline) | mocked 클래스 이름 그대로 | Instrumentation으로 retransform |
| Hibernate | `_$$_jvst...`, `HibernateProxy$...` | lazy loading proxy |
| Spring AOP | `$Proxy...` or `$$EnhancerBySpringCGLIB$$...` | JDK Proxy or CGLib |

#### 진단

```bash
# 클래스 dump 켜기
-Dcglib.debugLocation=/tmp/cglib
-Djdk.proxy.ProxyGenerator.saveGeneratedFiles=true
# ByteBuddy: 코드에서 .with(saveTo(...))
```

Dump된 .class를 `javap -v`로 분석.

### 4.8 LineNumberTable과 stack trace

stack trace의 `(Foo.java:42)`는 magic이 아니다. **각 메서드 Code attribute의 LineNumberTable**에서 옴.

```text
Code:
     0: getstatic     #7
     3: ldc           #13
     5: invokevirtual #15
     8: return
  LineNumberTable:
    line 3: 0      ← bytecode offset 0 ~ 4 → 소스 line 3
    line 4: 8      ← bytecode offset 5 ~ 7 → 소스 line 4
```

**컴파일 옵션 트레이드오프**:
- `-g:none`: nothing → stack trace에 line 없음. **production 금지**.
- `-g:source,lines`: SourceFile + LineNumberTable → 최소 권장.
- `-g:source,lines,vars`: + LocalVariableTable → 디버거 사용 시.

JDK 14+ **Helpful NullPointerExceptions** (JEP 358): `foo().bar().baz();` 한 줄에서 NPE 나도 "Cannot invoke .bar() because foo() is null" 형태로 정확히 가리킴.

---

## 5. 가지 ⑤: 진화 — JDK별 ClassFile 변천

### 5.1 핵심 질문

> "ClassFile 포맷은 어떻게 진화했고, 각 attribute는 언제 어떤 운영 변화를 가져왔나?"

### 5.2 운영자가 외울 만한 마일스톤

| 연도 | JDK (major) | 변화 | 운영 의미 |
|---|---|---|---|
| 2004 | 5 (49) | **Signature attribute** | Generics + Annotation. Reflection의 generic source. |
| 2011 | 7 (51) | **invokedynamic + BootstrapMethods** | JDK 7 미만에서는 lambda .class 못 돌림. StackMapTable 필수화. |
| 2014 | 8 (52) | **Lambda + MethodParameters** | `-parameters` 시 파라미터 이름 보존. |
| 2017 | 9 (53) | **Module + module-info.class** | `--module-path`. |
| 2018 | 11 (55) | **NestHost/NestMembers** | inner class용 synthetic accessor `access$000` 더 이상 생성 안 함. LTS. |
| 2021 | 16 (60) | **Record stable** | `Class.isRecord()`, ObjectMethods.bootstrap 활용. |
| 2021 | 17 (61) | **PermittedSubclasses (sealed)** | `Class.isSealed()`. LTS. |
| 2024 | 22+ | **Class-File API stable (JEP 484)** | JDK 표준으로 ClassFile 만들기. ASM 의존성 줄이는 추세. |

### 5.3 진화의 운영 의미

- **JDK 7 StackMapTable 필수화**: Verifier 속도 ↑ (03장 Linking 참조). 이전 ClassFile은 그대로 돌아가지만 새 컴파일러는 항상 StackMapTable 생성.
- **JDK 8 Lambda + invokedynamic**: Anonymous class 대신 invokedynamic. **운영 메모리 footprint 변화** — .class 파일 적어짐, hidden class 동적 생성.
- **JDK 11 Nest**: Inner class private 접근의 synthetic accessor 제거 → bytecode 크기 ↓, JIT 친화.
- **JDK 16+ Record**: ObjectMethods.bootstrap이 equals/hashCode/toString을 invokedynamic으로. 클래스당 메서드 수 ↓.

### 5.4 invokedynamic이 lambda 말고 또 쓰이는 곳

1. **String concat** (JDK 9+, JEP 280) — `"a" + b + "c"`도 invokedynamic. StringBuilder 호출 줄임.
2. **switch on String** (JDK 7+) — hashCode 기반 lookup.
3. **Record의 equals/hashCode/toString** (JDK 16+) — ObjectMethods.bootstrap.
4. **Pattern matching for switch** (JDK 21+).

---

## 6. 가지 ⑥: 도구 — javap, ASM, Class-File API

### 6.1 핵심 질문

> "ClassFile을 읽고 쓰는 도구는 무엇이 있고, 언제 무엇을 쓰는가?"

### 6.2 키워드 1 — javap는 ClassFile 진단의 시작

```bash
# 가장 자주 쓰는 옵션 조합
javap -v -p Foo.class            # -v 전체, -p private까지

# CP만 보기
javap -v Foo.class | sed -n '/Constant pool:/,/^{/p'

# 특정 메서드 Code만
javap -v -c Foo.class | grep -A 30 'main('

# jar 안의 .class
unzip -p app.jar com/foo/Foo.class | javap -v -
```

운영에서 ClassFile을 본다는 건 99% **`javap -v` 출력 해석**. byte editor로 hex 헤아리는 건 ClassFile API 개발자나 보안 분석가 영역.

### 6.3 키워드 2 — Bytecode 조작 라이브러리

| 도구 | 추상화 | 시니어가 만나는 곳 |
|---|---|---|
| **ASM** | low-level (visitor) | Hibernate(과거), Mockito 내부, Cglib 내부 |
| **ByteBuddy** | high-level (fluent DSL) | Mockito 2+, Hibernate(현재), Spring 일부 |
| **Javassist** | high-level (source string) | 오래된 프레임워크 |
| **CGLib** | mid-level | Spring AOP (인터페이스 없을 때) |
| **JDK 22+ Class-File API** | mid-level (표준) | 신규 프로젝트, 외부 의존 제거 |

**시니어의 결정 기준**: 신규는 **Class-File API**(JDK 22+) 또는 **ByteBuddy**. 기존 코드는 그 코드가 쓰는 도구.

### 6.4 키워드 3 — 런타임 진단 도구

```bash
# 클래스 계층 추적
jcmd <pid> VM.class_hierarchy com.foo.Service

# JFR — ClassLoad 이벤트
jcmd <pid> JFR.start name=cl duration=60s settings=profile filename=cl.jfr
jfr summary cl.jfr | grep -E 'ClassLoad|ClassUnload|ClassDefine'

# 직관적 로그
java -Xlog:class+load=info,class+unload=info -jar app.jar 2> classes.log
grep -i 'lambda\|hidden\|cglib\|enhance' classes.log
```

**핵심 이벤트**:
- `jdk.ClassLoad` — 클래스 로드 시점, 어떤 ClassLoader
- `jdk.ClassDefine` — 동적 클래스 생성 (hidden class 포함)
- `jdk.ClassUnload` — 클래스 unload

### 6.5 HotSpot 파서 — 운영자는 안 읽지만 알아둘 것

HotSpot의 ClassFile 파서는 `src/hotspot/share/classfile/classFileParser.cpp` 한 파일 약 6,000줄. 명세의 모든 코너 케이스가 여기 구현. 흐름:

```cpp
parse_stream(stream, ...);  // 1. magic + version 검증
parse_constant_pool(...);   // 2. CP
parse_access_flags(...);    // 3. access_flags + this/super/interfaces
parse_fields(...);          // 4. fields
parse_methods(...);         // 5. methods (Code attribute 포함)
parse_class_attributes(...);// 6. ClassFile attributes
post_process(...);          // 7. 검증 끝나면 InstanceKlass 생성
```

`guarantee_property(...)` — 검증 실패 시 즉시 `ClassFormatError`. `UnsupportedClassVersionError`는 ClassLoader가 아니라 이 파서가 던진다.

결과물: **InstanceKlass** (Metaspace에 저장) → 다음 챕터 02 ClassLoader의 끝점.

---

## 7. 면접 답변 워크플로우

### 7.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "ClassFile 구조 설명해주세요" | ② WHAT | ③ HOW (Code attribute) |
| "javac의 책임은 어디까지인가요?" | ① WHY | 04장 Initialization |
| "Constant Pool은 왜 있나요?" | ② WHAT | ③ HOW (bytecode 명령) |
| "Code attribute에 뭐가 있나요?" | ③ HOW | ④ 운영 (LineNumberTable) |
| "descriptor 문법은?" | ③ HOW | ④ NSME 시나리오 |
| "UCVE 진단" | ④ 운영 | ⑤ 진화 (major mapping) |
| "NSME 디버깅" | ④ 운영 | ③ HOW (descriptor) |
| "Lambda Metaspace 증가 정상?" | ④ 운영 | ⑤ invokedynamic |
| "stack trace에 같은 메서드 2번?" | ④ 운영 (Bridge) | ⑤ Signature |
| "HotSwap 한계 이유?" | ④ 운영 (HotSwap) | ② Code attribute 독립성 |
| "stack trace의 line number 출처?" | ④ LineNumberTable | ③ Code attribute |
| "invokedynamic은 lambda 말고?" | ⑤ 진화 | ④ Metaspace |
| "신규 프로젝트에서 bytecode 조작?" | ⑥ 도구 | ⑤ Class-File API |

### 7.2 답변 템플릿

> **루트 문장 한 줄 → 해당 가지 키워드 3개 순서 → 듣는 사람 표정 보고 인접 가지로**

예: "NoSuchMethodError 디버깅"

> "ClassFile은 javac가 만들고 JVM이 읽는 단일 입력이고, 그 중심은 Constant Pool과 Code attribute입니다. (← 루트)
> NSME의 핵심은 **JVM이 메서드를 이름 + descriptor 페어로 식별한다**는 사실입니다.
> 진단 절차는 셋입니다.
> 첫째, caller의 `javap -v`로 호출 명령의 `invokevirtual #N // Class.method:(...)`를 추출합니다.
> 둘째, callee의 `javap -v`로 실제 메서드 descriptor를 확인합니다.
> 셋째, 두 descriptor의 어느 부분(파라미터? return type?)이 다른지 식별합니다.
> 흔한 원인은 라이브러리 버전 mismatch, return type 변경(특히 generics), overload 변경입니다.
> Generics면 Signature attribute도 확인해서 erasure 전 정보를 봅니다."

→ 면접관이 "Signature attribute가 뭐죠?" 물으면 ⑤ 진화로, "Bridge method 본 적 있어요?" 물으면 ④ 시나리오로.

---

## 8. 꼬리질문 트리 (가지별)

### Q1 [가지 ①]. javac의 책임은 어디까지이고, 어디부터가 ClassLoader/JVM의 일인가요?

> javac는 `.class` 파일을 만들고 끝. 락도 안 잡고 Class 객체도 안 만들고 `<clinit>`을 실행하지도 않는다. javac는 `<clinit>` 메서드를 **합성해 ClassFile에 박는 것까지만**. 실행 시점/락 절차는 04장(Initialization)의 몫. ClassFile을 읽어 InstanceKlass로 만드는 것은 02장(ClassLoader)과 HotSpot의 classFileParser.cpp.

### Q2 [가지 ②]. Constant Pool은 왜 단일 출처로 만들어졌나요?

> 세 가지 설계 이유.
> 첫째, **중복 제거** — 같은 문자열이 여러 번 등장해도 CP에는 1개 엔트리.
> 둘째, **고정 길이 명령** — bytecode 명령어가 가변 길이 문자열 대신 CP 인덱스 2바이트만 안고 다님 → 인터프리터/JIT 빠름.
> 셋째, **Linking 분리** — Resolution이 CP 엔트리당 한 번만 처리 → 캐시 친화.
> 결과적으로 `invokevirtual #15`만 보면 클래스, 메서드 이름, 시그니처를 모두 따라갈 수 있는 그래프 노드 하나가 됨.

**Q2-1: Methodref와 InterfaceMethodref를 왜 따로 두나요?**
> dispatch 방식이 다르다. invokevirtual은 vtable lookup, invokeinterface는 itable lookup. 같은 메서드 이름이라도 dispatch 경로가 달라서 ClassFile-level에서 구분.

### Q3 [가지 ③]. Code attribute 안에 뭐가 있고, 왜 max_stack/max_locals를 미리 박아두나요?

> Code attribute는 메서드 본문 컨테이너로 5가지를 담는다.
> 첫째, **max_stack** — operand stack 최대 깊이.
> 둘째, **max_locals** — 로컬 변수 슬롯 수.
> 셋째, **bytecode** — 명령 바이트 시퀀스.
> 넷째, **exception_table** — try-catch 범위.
> 다섯째, **inner attributes** — LineNumberTable, LocalVariableTable, StackMapTable.
> max_stack/max_locals를 미리 박아두는 이유: JVM이 Stack Frame을 만들 때 **한 번에 정확한 크기로 할당**할 수 있게. 메서드 실행 중 stack growth 같은 동적 확장이 없어 Frame allocation이 빠르고 deterministic.

### Q4 [가지 ④]. UnsupportedClassVersionError 진단 절차?

> 메시지에 두 숫자가 있다 — "compiled by ... class file version X.0" 과 "recognizes up to Y.0". X가 컴파일 major, Y가 런타임 JVM 지원 한계.
> **JDK N → major = N + 44** (JDK 21 → 65, JDK 17 → 61, JDK 11 → 55, JDK 8 → 52).
> 의심 jar에서 .class 추출해 `javap -v ... | head -5`로 major 확인.
> 해결: JDK 업그레이드 또는 라이브러리 다운그레이드. CI에 enforcer-plugin 추가로 재발 방지.

**Q4-1: `minor_version: 65535`는?**
> `--enable-preview`로 컴파일된 ClassFile. 정확히 같은 major + `--enable-preview`에서만 실행. JDK 21 preview는 JDK 22에서도 거부.

### Q5 [가지 ④]. NoSuchMethodError 진단 절차?

> JVM은 메서드를 `이름 + descriptor` 페어로 식별. descriptor 한 글자라도 다르면 다른 메서드.
> 절차: (1) caller의 `javap -v`로 호출 명령 descriptor 추출, (2) callee의 `javap -v`로 실제 descriptor 확인, (3) 두 descriptor 차이 식별, (4) 흔한 원인은 라이브러리 버전 mismatch, return type 변경(특히 generics), overload 변경. 보너스로 covariant return의 bridge method도 의식.

**Q5-1: descriptor가 `(Ljava/util/List;)V`로 나오면 generic 정보는?**
> Erasure 결과라 descriptor엔 없음. 같은 메서드의 **Signature attribute**에 `(Ljava/util/List<Ljava/lang/String;>;)V`로 저장. javap -v로 메서드 아래 `Signature: #N` 라인. Reflection의 `Method.getGenericParameterTypes()`가 이걸 파싱.

### Q6 [가지 ④]. Lambda 많은 앱에서 Metaspace 증가가 정상인지 누수인지?

> Lambda 정상 메커니즘: javac가 invokedynamic + BootstrapMethods(LambdaMetafactory)로 컴파일 → 런타임 첫 invoke 시 hidden class 1개 생성 (사이트당) → 캐시.
> 정상: 사이트 수만큼 hidden class, 보통 수백~수천.
> 의심: hidden class가 시간에 비례해 증가 (희귀, 동적 lambda factory 패턴).
> 진단: `jcmd VM.classloader_stats`, `-Xlog:class+load=info` 에서 `lambda$` 패턴 빈도.

**Q6-1: invokedynamic이 lambda 말고 또?**
> String concat(JDK 9+), switch on String(JDK 7+), record의 equals/hashCode/toString(JDK 16+, ObjectMethods.bootstrap), pattern matching for switch(JDK 21+).

### Q7 [가지 ④]. stack trace에 같은 메서드가 두 번 나오는 경우?

> Bridge method 가능성. Generics + covariant return의 erasure 처리 결과 javac가 같은 이름의 두 메서드 생성 — 하나는 erased type 시그니처(`compare(Object, Object)`), 다른 하나는 우리가 작성한 것(`compare(Integer, Integer)`).
> 첫 번째는 `ACC_BRIDGE`, `ACC_SYNTHETIC` 플래그. 본문은 `checkcast` + 실제 메서드 위임.
> ClassCastException이 stack에 동일 메서드 두 번 나오는 패턴이면 bridge에서 checkcast 실패한 것 — raw-type 컨트랙트로 진입한 경로.

### Q8 [가지 ④]. HotSwap이 메서드 body는 바꿔도 시그니처는 못 바꾸는 이유?

> ClassFile 관점:
> - 메서드 body는 Code attribute라는 **독립적 단위** — bytecode + max_stack + max_locals + exception_table. 다른 부분과 결합 없음.
> - 메서드 시그니처 변경 = method_info 자체 변경 → InstanceKlass의 vtable/itable 재구성 필요.
> - 필드 추가 = 객체 layout 변경 → 이미 할당된 인스턴스 메모리 재배치 불가.
> - 상속 변경 = 전체 클래스 계층 재검증.
> JVMTI `RedefineClasses`는 안전한 범위(메서드 body)만 표준 지원. JRebel/DCEVM은 추가 indirection이나 JVM 패치로 더 광범위 변경. **Production에서는 hot reload 안 하고 rolling deploy로 해결**.

### Q9 (Killer) [가지 ④]. `<generated>` 또는 `$$EnhancerByCGLIB$$` stack frame 디버깅?

> 단계:
> 1. **프레임워크 식별**: `$$EnhancerByCGLIB$$`→ CGLib, `$ByteBuddy$`→ ByteBuddy, `$$Lambda$N/0x...`→ JDK Lambda hidden class, `$Proxy[0-9]+`→ JDK Dynamic Proxy, `HibernateProxy$...`/`_$$_jvst...`→ Hibernate.
> 2. **클래스 dump 켜기**: `-Dcglib.debugLocation=/tmp/cglib`, `-Djdk.proxy.ProxyGenerator.saveGeneratedFiles=true`, ByteBuddy는 `.with(saveTo(...))`.
> 3. **Dump된 .class를 `javap -v`로 분석** — 실제 generated bytecode 확인.
> 4. **컨텍스트 추적**: AOP advice chain, Hibernate lazy loading 등 어떤 인터셉션이 개입했는지.

**Q9-1: Mockito mock-maker-inline이 final class도 mock하는 메커니즘?**
> Java Agent의 Instrumentation API로 **기존 클래스 bytecode를 retransform**. final method를 인터셉트하도록 변경. 단점: JVM startup attach 비용, Metaspace 증가, 다른 agent(JaCoCo, JRebel)와 transformation 순서 충돌 가능.

### Q10 [가지 ⑤]. 운영자가 외울 필요 없는 ClassFile 디테일과, 외울 가치 있는 것?

> **외울 필요 없는 것**: magic의 hex 값, 모든 CONSTANT tag 번호, access_flags 비트 자릿수, Modified UTF-8 인코딩, Long/Double CP 슬롯 2개 디테일. 이유: 시대적 결정이라 운영 가치 없음. 도구가 추상화.
> **외울 가치 있는 것**:
> - major version → JDK 매핑 공식 (+44)
> - 7개 큰 블록의 이름과 역할
> - Code attribute가 메서드 본문이고 LineNumberTable이 stack trace line의 source
> - invokedynamic이 lambda, String concat, switch on String, record method에 쓰이는 사실
> - Signature attribute가 generic 정보를 reflection에 제공
> - Bridge method가 covariant return / generics erasure 때문에 생성됨

---

## 9. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 이내로 그릴 수 있다 (루트 + 6가지 + 각 키워드 3개)
- [ ] 가지 ① WHY: javac의 책임 경계와 클래스 라이프사이클 5단계를 그린다
- [ ] 가지 ② WHAT: 7개 블록을 위에서 아래로 적고 각 블록의 역할을 한 줄씩 말한다
- [ ] 가지 ② WHAT: Constant Pool의 단일 출처 그래프(Methodref → Class + NameAndType → Utf8)를 그린다
- [ ] 가지 ③ HOW: Code attribute 내부 5요소(max_stack/locals/bytecode/exception/inner attrs)를 적는다
- [ ] 가지 ③ HOW: descriptor 문법으로 `int main(String[])`을 `([Ljava/lang/String;)I`로 변환한다
- [ ] 가지 ③ HOW: invoke 5종을 사용처와 함께 적는다
- [ ] 가지 ④ 운영: UCVE 진단 절차 + major→JDK 매핑 공식(+44)을 말한다
- [ ] 가지 ④ 운영: NSME가 "이름 + descriptor 페어" 식별 실패라는 본질을 설명한다
- [ ] 가지 ④ 운영: Lambda Metaspace 정상/누수 구분 기준을 말한다
- [ ] 가지 ④ 운영: Bridge method가 generics erasure 산물임을 그림으로 설명한다
- [ ] 가지 ④ 운영: HotSwap이 메서드 body만 가능한 ClassFile-level 이유를 말한다
- [ ] 가지 ⑤ 진화: JDK 5 Signature, JDK 7 invokedynamic, JDK 11 Nest, JDK 16 Record, JDK 22 Class-File API 흐름을 적는다
- [ ] 가지 ⑥ 도구: javap -v / ASM / ByteBuddy / Class-File API 선택 기준을 말한다
- [ ] 8장 꼬리질문 10개에 막힘없이 답한다

---

## 다음 단계

- → [02. ClassLoader 계층](./02-classloader-hierarchy.md): 이 ClassFile을 **누가** 메모리에 가져오나
- → [03. Linking](./03-linking.md): 로드된 ClassFile을 어떻게 **검증·준비·해결**하나
- → [04. Initialization](./04-initialization-and-unload.md): 검증된 클래스를 **언제** 초기화하고 unload하나
- → [02-runtime-data-areas/02. Metaspace](../02-runtime-data-areas/02-metaspace-and-class-space.md): InstanceKlass가 사는 곳

## 참고

- **JVMS §4 ClassFile Format**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html
- **JVMS §6 JVM Instruction Set**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html
- **HotSpot classFileParser.cpp**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/classfile/classFileParser.cpp
- **JEP 181 Nest-Based Access Control**: https://openjdk.org/jeps/181
- **JEP 358 Helpful NullPointerExceptions**: https://openjdk.org/jeps/358
- **JEP 484 Class-File API**: https://openjdk.org/jeps/484
- **ASM**: https://asm.ow2.io/
- **ByteBuddy**: https://bytebuddy.net/
- **JVMTI RedefineClasses spec**: https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html#RedefineClasses
