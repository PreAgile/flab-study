# 02-03. Stack & PC & Native Method Stack — 스레드 하나당 받는 메모리

> `-Xmx2g` 짜리 JVM이 RSS 5GB를 쓴다? 그 차이의 상당 부분이 **스레드 수 × 1MB**다.
> 한 스레드가 만들어질 때마다 JVM은 OS로부터 **JVM Stack + PC Register + Native Method Stack** 세 가지 영역을 따로 할당받는다. Heap과 무관, GC와도 무관, `-Xmx`로도 제어 안 됨.
> 500 스레드 × 1MB = 500MB. 이게 "왜 우리 JVM이 메모리를 많이 쓰지?"의 가장 흔한 답이다.

---

## 📍 학습 목표

이 챕터를 마치면 다음을 모두 답할 수 있다.

1. JVM의 메모리 영역 중 **per-thread(스레드별)** 인 것 3가지를 외운다 — JVM Stack, PC Register, Native Method Stack.
2. Stack Frame 안의 3가지 구성요소(Local Variable Array, Operand Stack, Frame Data) 각각의 역할과 크기 결정 방식을 안다.
3. `max_locals`와 `max_stack`이 ClassFile의 Code attribute에 미리 적혀 있어, JVM이 **동적 stack growth 없이** Frame을 한 번에 할당하는 이유를 안다.
4. PC Register가 왜 스레드별이어야 하는지 (멀티스레드의 본질) + native 메서드 실행 중에는 PC가 undefined인 이유를 안다.
5. Native Method Stack이 무엇이고, JNI 호출 시 어떤 메모리를 쓰는지 안다.
6. **Virtual Thread (JDK 21+)** 의 stack이 일반 platform thread와 어떻게 다른지 — stack chunk가 Heap에 저장됨 + Continuation 개념.
7. `StackOverflowError` (스택 깊이 초과)와 `OutOfMemoryError: unable to create new native thread` (스레드 수 초과)의 차이.
8. `-Xss` 옵션의 의미와 트레이드오프 — 작게 잡으면 스레드 더 많이, 크게 잡으면 재귀 더 깊게.
9. `jstack` 출력의 스레드 상태 (RUNNABLE, BLOCKED, WAITING, TIMED_WAITING)와 stack trace 해석 방법.
10. Virtual Thread **pinning** 문제 — synchronized + native call이 carrier thread를 잡는 메커니즘.

---

## 🎨 1단계: 백지 그리기 가이드

### Step 1: JVM 프로세스의 가장 큰 박스

- 큰 사각형. 우측 상단에 "JVM Process Memory (RSS)".
- 좌측에는 **Shared (Heap, Metaspace, Code Cache)** — 모든 스레드가 같이 씀.
- 우측에는 **Per-Thread** — 스레드마다 별도 할당.

### Step 2: Per-Thread 영역 — 3개의 박스

- **JVM Stack** (가장 큼, 기본 1MB) — Java 메서드 호출의 Stack Frame들이 LIFO로 쌓임.
- **PC Register** (매우 작음, native word 1개) — 현재 실행 중인 bytecode 명령의 주소.
- **Native Method Stack** (보통 OS 기본, ~수백 KB ~ 8MB) — JNI 호출 시 C/C++ 스택.

### Step 3: 스레드 N개로 곱해보기

```
Thread #1: [JVM Stack 1MB][PC 8B][Native Stack 512KB]
Thread #2: [JVM Stack 1MB][PC 8B][Native Stack 512KB]
Thread #3: [JVM Stack 1MB][PC 8B][Native Stack 512KB]
...
Thread #500: ...
```

= 약 500 × 1.5MB ≈ **750MB의 per-thread footprint**. `-Xmx`와 완전 무관.

### Step 4: JVM Stack 내부 줌인 — Stack Frame들

```
JVM Stack (한 스레드의)
━━━━━━━━━━━━━━━━━━━━━━

┌────────────────────────┐ ← Stack의 top (가장 최근 호출)
│ Frame: main(...)        │
│  ├─ Local Variable Array│
│  ├─ Operand Stack       │
│  └─ Frame Data          │
├────────────────────────┤
│ Frame: foo(...)         │
│  ├─ Local Variable Array│
│  ├─ Operand Stack       │
│  └─ Frame Data          │
├────────────────────────┤
│ Frame: bar(...)         │  ← 현재 실행 중인 메서드
│  ├─ Local Variable Array│
│  ├─ Operand Stack       │
│  └─ Frame Data          │
└────────────────────────┘ ← Stack의 bottom (오래된 호출은 위, 새 호출은 아래)
```

> 메서드를 호출하면 새 Frame이 push, return 시 pop. Stack overflow는 push할 자리가 없을 때.

### Step 5: 하나의 Frame 줌인 — 3가지 영역

```
Stack Frame (메서드 1개)
━━━━━━━━━━━━━━━━━━━━━━━

┌─────────────────────────────────────┐
│ Local Variable Array                  │
│  slot[0] = this (인스턴스 메서드 시)   │
│  slot[1] = args[0]                    │
│  slot[2] = args[1]                    │
│  ... (max_locals 크기로 고정)          │
├─────────────────────────────────────┤
│ Operand Stack                          │
│  (top) [int 42]                       │  ← bytecode 실행 중 push/pop
│        [ref to "Hello"]               │
│        [int 100]                      │
│  (bottom)                              │
│  ... (max_stack 깊이로 고정)            │
├─────────────────────────────────────┤
│ Frame Data                             │
│  ├─ Constant Pool Reference            │  현재 메서드의 CP 가리킴
│  ├─ Return PC (caller로 돌아갈 주소)    │
│  └─ Previous Frame Pointer             │
└─────────────────────────────────────┘
```

### Step 6: Virtual Thread (JDK 21+) — 다른 모델

- Platform thread: OS 스레드 1:1. JVM Stack은 OS가 할당.
- Virtual thread: M개 virtual : N개 carrier(OS). JVM Stack 대신 **stack chunk가 Heap에 저장**.
- 그림: Heap 안에 작은 stack chunk 박스들 + virtual thread N개가 carrier thread P개를 공유.

### 정답 그림 (ASCII로 통합)

```
JVM Process Memory
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Shared 영역]                           [Per-Thread 영역 × N]

┌─────────────┐                         Thread #1:
│ Java Heap    │                         ┌─────────────────┐
│ (-Xmx)      │                         │ JVM Stack (1MB)  │
└─────────────┘                         │  Frame: main     │
┌─────────────┐                         │  Frame: foo      │
│ Metaspace    │                         │  Frame: bar      │
└─────────────┘                         ├─────────────────┤
┌─────────────┐                         │ PC Register      │
│ Code Cache   │                         ├─────────────────┤
└─────────────┘                         │ Native Stack     │
                                        └─────────────────┘
                                        Thread #2: ... (반복)
                                        Thread #N: ...

총 메모리 = Shared + (Per-Thread 크기 × 스레드 수)
            ↑                ↑
            -Xmx 등으로 제어    -Xss(JVM Stack) + OS(Native) + 스레드 수
```

---

## 🧠 2단계: 직관

### 핵심 비유

> **콜택시 회사 비유**:
> - **Heap** = 회사 공용 차고 (모든 기사가 같이 씀, 차들이 들락거림 = 객체).
> - **JVM Stack** = 각 기사의 개인 운행일지 책 — 어디서 출발해 어디로 가는지 page마다 적음 (page = Stack Frame). 한 기사 한 책.
> - **PC Register** = 각 기사가 들고 다니는 "지금 어느 page의 어느 줄을 보고 있는지" 책갈피.
> - **Native Method Stack** = 회사 외부 기사(C/JNI)를 부를 때 그쪽 회사의 별도 일지.
> - **Stack Frame** = 한 page. 메모할 줄 수(max_locals)와 빈 칸 수(max_stack)가 미리 정해져 있어 page 크기가 일정.
> - **Virtual Thread** = 한 기사가 여러 운행을 동시에 관리. 운행일지가 한 책에서 다른 책으로 옮겨 다닐 수 있음 (stack chunk가 Heap에).

### 정확한 정의 (비유와 분리)

| 용어 | 정의 |
|---|---|
| **JVM Stack** | 스레드별로 1개씩 존재. Java 메서드 호출의 Stack Frame들을 LIFO로 관리. `-Xss`로 크기 지정 (기본 OS·플랫폼 따라 512KB~1MB). |
| **Stack Frame** | 메서드 1회 호출당 1개. Local Variable Array + Operand Stack + Frame Data로 구성. ClassFile의 Code attribute에 적힌 `max_locals`, `max_stack`으로 크기 결정. |
| **Local Variable Array** | 메서드의 파라미터와 로컬 변수 저장. 0번 slot은 인스턴스 메서드면 `this`, static이면 첫 파라미터. long/double은 2 slot 차지. |
| **Operand Stack** | bytecode 명령이 push/pop으로 사용. `iadd`라면 "stack top 2개 pop → 더해서 push". `max_stack`으로 깊이 제한. |
| **Frame Data** | 현재 메서드의 CP 참조 + return PC (caller로 돌아갈 주소) + 이전 Frame의 포인터 + dynamic linking 정보. |
| **PC Register** | 스레드별 1개. 현재 실행 중인 bytecode 명령의 주소 또는 인덱스. Native 메서드 실행 중에는 undefined. |
| **Native Method Stack** | 스레드별 1개. JNI 등 native (C/C++) 메서드 호출 시 OS가 관리하는 일반 thread stack. |
| **Stack chunk** (JDK 21+) | Virtual Thread의 stack 데이터를 Heap에 저장하는 자료구조. 일반 객체와 동일하게 GC 대상. |
| **Continuation** (JDK 21+) | Virtual Thread를 멈추고(park) 다시 재개(unpark)할 수 있게 하는 메커니즘. stack chunk를 들고 다님. |

### 왜 per-thread인가 — 가장 본질적 이유

```
[shared로 만들면 (가상)]                   [per-thread로 만든 실제]
━━━━━━━━━━━━━━━━━━━                       ━━━━━━━━━━━━━━━━━━━━━

Thread 1: foo() 호출 중                    Thread 1의 Stack: foo()의 Frame
  └→ 공유 Stack에 Frame push (락!)         Thread 2의 Stack: bar()의 Frame
Thread 2: bar() 호출 중                    Thread 3의 Stack: baz()의 Frame
  └→ 공유 Stack에 Frame push (대기...)
Thread 3: baz() 호출 중                    완전 독립, lock 불필요
  └→ 대기...
━━━━━━━━━━━━━━━━━━━                       ━━━━━━━━━━━━━━━━━━━━━

함수 호출마다 lock contention 발생         lock-free, 진정한 병렬 실행
```

→ **함수 호출이 멀티스레드 환경에서 직렬화되지 않으려면** stack은 본질적으로 per-thread여야 함. JVM 설계 초기부터의 결정.

### 왜 Operand Stack이 따로 있나 — Stack-based VM의 본질

JVM은 **register-based가 아닌 stack-based VM**. 그 이유:

```
Register-based (x86, ARM):                Stack-based (JVM):
━━━━━━━━━━━━━━━━━━━                       ━━━━━━━━━━━━━━━━━

ADD R3, R1, R2     ; R3 = R1 + R2          iload_1            ; push local[1]
                                            iload_2            ; push local[2]
                                            iadd               ; pop 2, push sum
                                            istore_3           ; pop, store local[3]

명령어 길이: ~6 byte (operand 인코딩)      명령어 길이: 1 byte 각
명령어 수: 적음                            명령어 수: 많음
플랫폼 종속: 레지스터 수가 CPU마다 다름     플랫폼 독립: stack은 추상
```

**stack-based 선택의 이유**:
1. **플랫폼 독립**: register 수가 x86(16개)/ARM(31개)/RISC-V(32개)로 다 다름. stack은 "n개 push/pop"으로 어디서나 동일.
2. **명령어 인코딩 단순**: operand 없이 1바이트 명령 다수 → bytecode 파싱 빠름.
3. **컴파일러 단순**: stack-based 코드 생성이 register allocation보다 훨씬 단순 (1995년 시점).

트레이드오프: 명령어 수가 많아 인터프리터 성능이 register-based보다 느림. 그래서 **JIT 컴파일이 필수** — JIT이 bytecode를 register-based native code로 변환하면서 사라지는 비용.

### 왜 max_stack/max_locals가 미리 정해져 있나

ClassFile의 Code attribute에는 메서드의 **max_stack**(operand stack 최대 깊이)과 **max_locals**(local variable 슬롯 수)가 javac에 의해 미리 계산되어 저장됨.

```text
public static void main(java.lang.String[]);
  Code:
    stack=2, locals=1, args_size=1   ← ★ max_stack=2, max_locals=1
```

→ JVM은 Frame을 만들 때 이 두 값을 보고 **한 번에 정확한 크기로 할당**. 메서드 실행 중 stack growth 같은 동적 확장 없음 → Frame allocation이 빠르고 deterministic.

이게 [01-classfile-format.md](../01-class-lifecycle/01-classfile-format.md)에서 강조한 "**Code attribute가 stack trace 해석의 핵심**"인 이유. Stack 동작을 이해하려면 ClassFile의 max_stack/max_locals를 이해해야 함.

---

## 🔬 3단계: 구조

### Stack Frame 내부의 정확한 구조

```
Stack Frame (한 메서드 호출)
━━━━━━━━━━━━━━━━━━━━━━━━━━

┌──────────────────────────────────────────────────┐
│ ① Local Variable Array                            │
│    크기: max_locals (Code attribute에서)          │
│    각 슬롯: 32-bit (int, float, ref, returnAddr) │
│            ★ long/double은 2 슬롯 차지            │
│                                                    │
│    인덱스 규칙:                                     │
│    - 인스턴스 메서드: slot[0] = this              │
│    - static 메서드:   slot[0] = 첫 파라미터        │
│    - 그 뒤로 파라미터들, 그 뒤로 로컬 변수들        │
├──────────────────────────────────────────────────┤
│ ② Operand Stack                                   │
│    크기: max_stack (Code attribute에서)           │
│    bytecode 실행 중 push/pop                     │
│    예: iadd = "top 2개 pop → 더해서 push"         │
├──────────────────────────────────────────────────┤
│ ③ Frame Data                                      │
│    - Constant Pool Reference (현재 메서드의 CP)    │
│    - Return PC (caller bytecode 주소)             │
│    - Previous Frame Pointer                       │
│    - Dynamic Linking 정보 (vtable lookup 캐시 등) │
└──────────────────────────────────────────────────┘
```

### Local Variable Array의 슬롯 사용 예시

```java
public int compute(long a, String s, int b) {
    int local = a + b;
    return local;
}
```

`max_locals = 5`, 슬롯 레이아웃:

```
slot[0] = this        (4 bytes — 인스턴스 메서드라서)
slot[1] = a (long, low)  ┐
slot[2] = a (long, high) ┘ ← long은 2 슬롯
slot[3] = s (reference)
slot[4] = b (int)
slot[5] = local (int)
```

> 잠깐, max_locals = 5인데 slot[5]까지 쓴다? 슬롯 인덱스는 0부터이므로 slot[0]~slot[4] = 5 슬롯. local이 slot[5]면 6 슬롯이 필요 — 위 예제가 부정확. javac는 `compute` 끝나기 전 `a`/`s`/`b`의 슬롯을 재사용해서 max_locals=4로 최적화하기도 함. **javac가 슬롯 재사용으로 max_locals를 최소화**한다는 사실 자체가 중요.

### Operand Stack 동작 예시

```java
int result = a + b;
```

```text
bytecode:                operand stack 상태:
                         (초기)  []
0: iload  a              [a]
1: iload  b              [a, b]
2: iadd                  [a+b]           ← top 2개 pop, sum push
3: istore result         []              ← pop, slot[result]에 저장
```

→ `iadd`는 "stack top 2개를 pop, 더해서 push". 모든 산술 명령이 이 패턴. **operand stack은 임시 계산 공간**.

### PC Register의 역할

```
스레드 1: foo() 실행 중
  PC = 0x... (bytecode offset 8, 현재 실행 명령)

스레드 2: bar() 실행 중
  PC = 0x... (다른 메서드, 다른 offset)
```

**왜 스레드별인가**:
- 멀티스레드는 본질적으로 "여러 곳의 명령을 동시에 실행" — 각 스레드가 자기 "현재 위치"를 들고 있어야 함.
- 컨텍스트 스위치 시 OS가 PC를 저장/복원.

**Native 메서드 실행 중 PC = undefined**:
- Java 메서드의 PC는 bytecode offset. Native (C/C++) 메서드는 native instruction에서 실행 — bytecode offset 개념 없음.
- 그 동안 JVM의 PC Register는 의미 없는 상태.

### Native Method Stack — JNI의 입구

```
JNI 호출 흐름:
━━━━━━━━━━━━

Java 코드: System.loadLibrary("foo");
                  System.foo_native_method();
                              │
                              ▼
                  JNI 진입 (JVM이 native 함수 주소 lookup)
                              │
                              ▼
                  Native Method Stack에 C/C++ 함수의 stack frame push
                  - 일반 OS thread stack과 같은 메커니즘
                  - C 컴파일러가 생성한 prologue/epilogue
                              │
                              ▼
                  Native 코드 실행 (C/C++로 작성됨)
                              │
                              ▼
                  return 시 Native Method Stack frame pop
                              │
                              ▼
                  Java로 복귀, JVM Stack의 호출 지점에서 재개
```

**HotSpot 구현 디테일**: 실제로 HotSpot은 **JVM Stack과 Native Method Stack을 같은 OS thread stack에 통합**한다 — 두 영역의 경계는 논리적. JNI 호출 시 native frame이 JVM frame 위에 자연스럽게 쌓임.

### 🎯 스택 3개의 통합 그림 — "물리적으론 스택 1개"

#### 가장 흔한 오해

"JVM Stack", "Native Method Stack", "Operand Stack" 이 3개 이름이 각각 별개의 메모리 영역인 것처럼 들린다. **실제로는 하나의 물리적 stack 안에 층위만 다른 데이터**.

| Spec 용어 | 물리적 실체 |
|---|---|
| **JVM Stack** | OS thread stack의 **Java Frame들이 쌓이는 부분** |
| **Native Method Stack** | OS thread stack의 **C Frame들이 쌓이는 부분** (★ 같은 stack) |
| **Operand Stack** | 각 Java Frame **내부의** 작은 임시 계산 영역 (★ thread-level 아님) |

→ 스레드 1개 = OS가 할당한 **stack 1개 (예: 1MB)**. 그 안에 Java Frame과 C Frame이 LIFO로 **섞여서** 쌓임. JVM Spec이 "이 영역은 JVM Stack, 저 영역은 Native Method Stack"이라 부를 뿐.

#### 통합 그림 — 한 스레드의 stack 전체

```
스레드 1개 = OS가 할당한 stack 1MB (★ 물리적으로 1개의 연속 메모리)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[stack top — SP 가리킴, 새 호출이 여기로 push]
┌──────────────────────────────────────────┐
│ C Frame: greet (JNI native 함수)            │ ┐
│ ├ 인자: JNIEnv*, jclass, jstring            │ │ "Native Method
│ ├ 지역 변수                                   │ ├  Stack" 영역
│ └ return addr → JNI stub                    │ │ (논리적)
├──────────────────────────────────────────┤ │
│ JNI stub Frame (Java↔Native 전환)            │ ┘
├──────────────────────────────────────────┤
│ Java Frame: Main.main(args)                 │ ┐
│ ┌────────────────────────────────────┐  │ │
│ │ Local Var Array                      │  │ │
│ │  slot[0] = args   slot[1] = x        │  │ │
│ ├────────────────────────────────────┤  │ │
│ │ ★ Operand Stack ★                    │  │ │ "JVM Stack"
│ │  (top) [...]                         │  │ ├  영역
│ │        [...]                         │  │ │ (논리적)
│ │  (bot) [...]                         │  │ │
│ ├────────────────────────────────────┤  │ │ ★ Operand Stack은
│ │ Frame Data                           │  │ │   별개 영역이 아니라
│ │ ├ CP ref  ├ return PC  └ prev FP     │  │ │   Java Frame **내부**의
│ └────────────────────────────────────┘  │ │   한 부분
├──────────────────────────────────────────┤ │
│ Java Frame: Main.<clinit> (static init)     │ ┘
├──────────────────────────────────────────┤
│ C Frame: JavaMain (JVM 진입 코드)             │ ┐
├──────────────────────────────────────────┤ │ "Native Method
│ C Frame: java launcher main()                │ ├  Stack" 영역
├──────────────────────────────────────────┤ │ (다시)
│ C Frame: _start, __libc_start_main           │ ┘
└──────────────────────────────────────────┘
[stack bottom — OS 할당 시작점]

▲ 물리적 메모리는 연속된 1개. 점선 영역은 "논리적 분류"일 뿐.
▲ Java Frame과 C Frame은 같은 stack에 LIFO로 섞여 쌓일 수 있음.
▲ ★ Operand Stack은 thread-level이 아니라 Frame-level 영역.
```

#### 핵심 규칙 3가지

1. **물리적 1개 stack** — OS가 thread 생성 시 1MB 정도를 한 번에 할당. 모든 frame이 이 안에 들어감.
2. **Frame 종류는 2개** — Java Frame (HotSpot이 만듦, Operand Stack 포함) / C Frame (C 컴파일러가 만듦, 일반 stack frame).
3. **Operand Stack은 Frame 부속물** — 각 Java Frame 안의 작은 LIFO 영역. bytecode 명령(iadd, iload 등)이 여기서만 작동.

---

#### 실행 추적 — 한 단계씩 토글로

예제 코드:

```java
public class Main {
    public static native void greet(String name);   // JNI
    public static int add(int a, int b) { return a + b; }
    public static void main(String[] args) {
        int x = add(3, 4);
        System.loadLibrary("nativelib");
        greet("World");
    }
}
```

<details>
<summary><b>Step 0: 프로그램 시작 — OS가 stack 1MB 할당</b></summary>

```
$ java Main 실행
  ↓
OS가 java 프로세스 + main thread 생성
  ↓
OS가 main thread용 stack 1MB 할당
  (예: 가상주소 0x7fff_f000 ~ 0x7fff_0000)
```

stack 상태:
```
[stack top = 0x7fff_f000] ← SP 여기
┌──────────────────────┐
│                      │
│     (비어 있음)        │
│      1MB 공간          │
│                      │
└──────────────────────┘
[stack bottom = 0x7fff_0000]
```

★ 아직 frame 0개. SP(stack pointer)가 top을 가리킴.
★ stack은 **위에서 아래로 자람** (관례적 표현). 실제 메모리 주소는 감소 방향.

</details>

<details>
<summary><b>Step 1: JVM 부트스트랩 — C frame들이 먼저 쌓임</b></summary>

OS가 `_start` → `java` 런처의 C `main()` → JVM 초기화 → `JavaMain()`을 호출.

```
[stack top]
┌──────────────────────────┐
│ C Frame: JavaMain          │ ← JVM이 Java main 호출 직전
├──────────────────────────┤
│ C Frame: java launcher     │
├──────────────────────────┤
│ C Frame: _start            │
└──────────────────────────┘
[stack bottom]
```

★ 이 영역은 모두 "Native Method Stack" 영역 (논리적 분류).
★ 평범한 C 함수 호출 prologue/epilogue로 쌓임. HotSpot 관여 안 함.

</details>

<details>
<summary><b>Step 2: Main.main() 호출 — 첫 Java Frame push</b></summary>

`JavaMain`이 Java `Main.main`을 찾아 호출하면서 **Java Frame**을 push.

```
[stack top]
┌──────────────────────────────┐
│ Java Frame: Main.main(args)   │ ← ★ 새 Java Frame
│ ├ max_locals=2                │
│ │  slot[0] = args (ref)       │
│ │  slot[1] = x (아직 빈 칸)    │
│ ├ max_stack=2                 │
│ │  Operand Stack: []          │   ★ 비어있음
│ └ Frame Data                  │
│    ├ return PC → JavaMain     │
│    └ prev FP                  │
├──────────────────────────────┤
│ C Frame: JavaMain              │
├──────────────────────────────┤
│ C Frames ...                   │
└──────────────────────────────┘
[stack bottom]
```

★ 여기서부터 "JVM Stack" 영역 시작.
★ Frame 안에 Operand Stack이 보임 — Frame **안**의 한 부분.

</details>

<details>
<summary><b>Step 3: add(3, 4) 호출 직전 — Operand Stack에 인자 push</b></summary>

main의 bytecode 실행:
```
iconst_3       ; Operand Stack에 3 push
iconst_4       ; Operand Stack에 4 push
```

```
Java Frame: main(args)
┌──────────────────────────────┐
│ Local Var: [args, _]          │
│ Operand Stack:                │
│   (top) [4]                   │ ← iconst_4로 push됨
│         [3]                   │ ← iconst_3로 push됨
│   (bot)                       │
└──────────────────────────────┘
```

★ Operand Stack에 인자를 쌓는 중. 아직 main Frame 하나뿐.
★ 이건 **Frame 내부**의 Operand Stack — 전체 OS stack의 SP가 움직이는 게 아님.

</details>

<details>
<summary><b>Step 4: add 호출 — 새 Java Frame push, 인자 자동 전달</b></summary>

`invokestatic add` 명령:
1. main의 Operand Stack에서 인자 2개 pop
2. add용 새 Java Frame 생성 + push (★ 이때 OS stack의 SP도 이동)
3. pop한 인자를 add의 Local Var에 넣음

```
[stack top]
┌──────────────────────────────┐
│ Java Frame: add(a=3, b=4)     │ ← ★ 새로 push
│ ├ Local Var                   │
│ │  slot[0] = 3 (a)            │   ← invokestatic이 자동으로 채움
│ │  slot[1] = 4 (b)            │
│ ├ Operand Stack: []           │
│ └ Frame Data                  │
│    └ return PC → main 다음 명령
├──────────────────────────────┤
│ Java Frame: main(args)        │
│ ├ Operand Stack: []           │ ← ★ 비어짐 (인자가 add로 옮겨감)
│ └ ...                         │
├──────────────────────────────┤
│ C Frames ...                   │
└──────────────────────────────┘
```

★ 인자가 **caller의 Operand Stack → callee의 Local Var**로 자동 전달.
★ Java Frame 2개가 같은 OS stack에 LIFO로 쌓임.

</details>

<details>
<summary><b>Step 5: add 안에서 bytecode 실행 — Operand Stack에서 계산</b></summary>

```
iload_0    ; slot[0]=3을 Operand Stack에 push   → [3]
iload_1    ; slot[1]=4을 push                   → [3,4]
iadd       ; top 2개 pop, 더해서 push            → [7]
ireturn    ; top 1개 pop, caller로 반환
```

iadd 직후 상태:
```
Java Frame: add(3, 4)
┌──────────────────────────────┐
│ Local Var: [3, 4]             │ ← 안 변함
│ Operand Stack:                │
│   (top) [7]                   │ ← iadd 결과
│   (bot)                       │
└──────────────────────────────┘
```

★ 산술은 **Operand Stack에서만** 발생. Local Var는 명시적 store 명령이 있어야 변함.

</details>

<details>
<summary><b>Step 6: add return — Frame pop, 결과가 caller로 자동 이동</b></summary>

`ireturn` 실행:
1. add의 Operand Stack에서 7 pop
2. **add Frame 통째로 pop** (사라짐, SP 이동)
3. main의 Operand Stack에 7 push (★ JVM이 자동 처리)
4. PC를 main의 return PC로 복원

```
[stack top]
┌──────────────────────────────┐
│ Java Frame: main(args)        │
│ ├ Local Var: [args, _]        │
│ ├ Operand Stack:              │
│ │   (top) [7]                 │ ← add의 반환값
│ └ ...                         │
├──────────────────────────────┤
│ C Frames ...                   │
└──────────────────────────────┘
```

다음 명령:
```
istore_1   ; Operand top pop → slot[1]에 저장 (x = 7)
```

★ 반환값은 **callee Operand → caller Operand**로 자동 전달.
★ 함수 호출/리턴의 모든 데이터 흐름이 **Operand Stack을 통해** 일어남.

</details>

<details>
<summary><b>Step 7: greet("World") — JNI 호출, C Frame이 Java Frame 위에 쌓임</b></summary>

bytecode:
```
ldc "World"            ; Operand Stack에 "World" 참조 push
invokestatic greet     ; ★ native 메서드
```

`invokestatic`이 native임을 감지 → JNI 경로로 분기:

```
[stack top]
┌──────────────────────────────┐
│ C Frame: greet (native lib)   │ ← ★ C 함수 frame
│ ├ JNIEnv*, jclass, jstring    │   (C 컴파일러 prologue로 push)
│ ├ 지역 변수                    │
│ └ return addr → JNI stub      │
├──────────────────────────────┤
│ JNI stub Frame                │ ← Java↔Native 전환 코드
│  (예외 체크, JNIEnv 준비)      │
├──────────────────────────────┤
│ Java Frame: main(args)        │
│ ├ Operand Stack: []           │ ← 인자("World") pop됨
│ └ ...                         │
├──────────────────────────────┤
│ C Frames ...                   │
└──────────────────────────────┘
```

★ 같은 OS thread stack에 **C Frame이 Java Frame 위에 자연스럽게 쌓임**.
★ 이 순간부터 **PC Register는 undefined** — bytecode가 아닌 native instruction 실행 중.
★ 여기 C Frame 영역이 "Native Method Stack"의 또 다른 부분.

</details>

<details>
<summary><b>Step 8: native C 함수 실행 — 평범한 C 호출 메커니즘</b></summary>

```c
JNIEXPORT void JNICALL Java_Main_greet(
    JNIEnv* env, jclass cls, jstring name) {
    const char* str = (*env)->GetStringUTFChars(env, name, NULL);
    printf("Hello, %s\n", str);          // 여기서 C frame 또 push/pop
    (*env)->ReleaseStringUTFChars(env, name, str);
}
```

`printf` 호출 시 또 C frame push, return 시 pop.

★ Operand Stack 같은 거 없음. C는 register-based — 인자/리턴값을 CPU 레지스터로 전달.
★ HotSpot 관여 안 함. OS thread stack을 평범한 C 함수처럼 사용.

</details>

<details>
<summary><b>Step 9: native return → Java 복귀</b></summary>

```
1. C 함수 return → C frame pop (C 컴파일러의 epilogue)
2. JNI stub이 정리 작업 (예외 전파, JNIEnv 해제)
3. JNI stub frame pop
4. PC Register를 main의 다음 bytecode로 복원
```

```
[stack top]
┌──────────────────────────────┐
│ Java Frame: main(args)        │ ← 다시 활성
│ └ 다음 bytecode부터 재개       │
├──────────────────────────────┤
│ C Frames ...                   │
└──────────────────────────────┘
```

★ PC가 다시 의미 있는 값(bytecode offset)을 가짐.

</details>

<details>
<summary><b>Step 10: main return → 스레드 종료</b></summary>

```
return (void)         ; main Frame pop
  ↓
JavaMain의 C 코드로 복귀
  ↓
JVM shutdown (GC 정리, JIT 종료, finalizer)
  ↓
모든 C Frame pop
  ↓
OS가 1MB stack 메모리 회수 (munmap)
  ↓
스레드 종료
```

★ stack은 마지막에 통째로 OS에 반환.

</details>

---

#### 한 줄 모델

> **한 스레드 = OS stack 1개. 그 위에 Java Frame(내부에 Operand Stack 포함)과 C Frame이 LIFO로 섞여 쌓임. "JVM Stack / Native Method Stack / Operand Stack"은 같은 stack을 다른 관점에서 부르는 이름.**

#### "어디로 가서 어떻게 쌓이고 어떻게 마무리?"의 답

| 질문 | 답 |
|---|---|
| 처음 실행 시 stack은? | OS가 thread 생성 시 1MB 통째로 할당 |
| 어디에 쌓이는가? | 그 1MB 안. Java Frame이든 C Frame이든 같은 stack |
| 어떻게 실행? | bytecode는 Java Frame의 Operand Stack에서 push/pop으로 계산. native는 C 호출 규약대로 |
| 함수 호출 시 인자 전달? | caller Operand Stack → callee Local Var (Java→Java) / Operand Stack → CPU 레지스터 (Java→C) |
| 함수 리턴 시? | callee Frame pop, 반환값을 caller Operand Stack으로 자동 이동 |
| 마무리? | main return → JVM shutdown → 모든 frame pop → OS가 stack 회수 |

### Virtual Thread의 stack 모델 (JDK 21+)

```
Platform Thread (전통적):                Virtual Thread (JDK 21+):
━━━━━━━━━━━━━━━━━━━━                    ━━━━━━━━━━━━━━━━━━━━━━

OS 스레드 1:1                            M개 virtual : N개 carrier(OS)

각 스레드:                                각 carrier:
  └── JVM Stack (1MB, 미리 할당)           └── JVM Stack (carrier 자기 것)

                                          각 virtual thread:
                                          └── Stack Chunk (Heap에 저장)
                                              ├── Frame들
                                              ├── 가변 크기 (실제 깊이만큼)
                                              └── 일반 객체처럼 GC 대상
```

**왜 Heap에?** Virtual Thread는 수십만~수백만 개 만들기 위해 도입 — platform thread당 1MB stack을 그대로 곱하면 100,000 thread × 1MB = 100GB로 불가능. Heap에 stack chunk로 보관하면:
- 실제 깊이만큼만 메모리 사용 (sparse allocation 안 함).
- park / unpark 시 stack chunk를 carrier로 옮기거나 다시 Heap으로 보내는 게 빠름.
- GC와 통합 — virtual thread가 unreachable이면 stack도 회수.

**Continuation 메커니즘**:

```
Virtual Thread T가 socket.read() 같은 blocking 호출
        │
        ▼
JDK 21+ I/O 코드가 "이건 block될 작업이다" 인식
        │
        ▼
T의 현재 stack을 stack chunk로 freeze → Heap에 저장
        │
        ▼
Carrier thread는 다른 virtual thread를 실행 (lock-free 스케줄링)
        │
        ▼
I/O 준비 완료 → 이벤트 발생
        │
        ▼
스케줄러가 T를 다시 carrier에 unfreeze → carrier의 JVM Stack에 stack chunk 복원
        │
        ▼
T가 socket.read() 다음 줄부터 재개
```

이 freeze/unfreeze가 **continuation**. T 입장에서는 그냥 함수 호출 한 번 — 그 동안 carrier가 다른 일을 한 것이 투명.

### Virtual Thread의 한계 — Pinning

```
Virtual Thread T가 synchronized 블록 진입:
        │
        ▼
synchronized는 carrier thread의 OS lock에 의존
        │
        ▼
T는 carrier에 "pinned" — freeze 불가
        │
        ▼
blocking 호출 시 stack을 Heap으로 못 옮김
        │
        ▼
carrier thread도 같이 block → 다른 virtual thread 실행 불가
        │
        ▼
처리량 ↓ — virtual thread의 이점 상실
```

**pinning의 트리거**:
- `synchronized` 메서드 / 블록 (JDK 21).
- Native (JNI) 호출 중인 동안.
- ★ JDK 24부터 `synchronized`도 pinning 해소 예정 (JEP 491).

**해결**: `synchronized` 대신 `ReentrantLock` 사용 — Java-level lock이라 pinning 안 함.

---

## 🧬 4단계: 내부 구현 — HotSpot

### JavaThread 객체 (HotSpot의 스레드 표현)

위치: `src/hotspot/share/runtime/javaThread.hpp`

```cpp
class JavaThread : public Thread {
private:
  // Stack 관련
  address          _stack_base;       // OS thread stack의 base
  size_t           _stack_size;       // OS thread stack의 크기

  // JVM Stack의 현재 top (frame pointer)
  frame            _last_Java_frame;

  // PC Register
  address          _saved_exception_pc; // 예외 발생 시 PC

  // Java 메서드 실행을 위한 JNI handle
  JNIHandleBlock*  _active_handles;

  // 스레드 상태
  JavaThreadState  _thread_state;

  // 이 스레드가 실행 중인 OS thread
  OSThread*        _osthread;

  // ...
};
```

→ HotSpot의 한 OS thread가 한 JavaThread 객체에 대응. JavaThread가 들고 있는 정보로 모든 스레드별 데이터(Stack base, PC 등)에 접근.

### Frame 객체 (HotSpot이 보는 Stack Frame)

위치: `src/hotspot/share/runtime/frame.hpp`

```cpp
class frame VALUE_OBJ_CLASS_SPEC {
private:
  intptr_t* _sp;       // Stack Pointer (현재 Frame의 base)
  address   _pc;       // Program Counter (현재 명령 주소)
  intptr_t* _fp;       // Frame Pointer (이전 Frame의 base)

  // ...
public:
  Method*   interpreter_frame_method() const;
  jint      interpreter_frame_bci() const;        // bytecode index
  intptr_t* interpreter_frame_local_at(int index) const;
  intptr_t* interpreter_frame_expression_stack() const;  // operand stack
};
```

→ HotSpot은 한 Frame을 `sp` + `fp` + `pc` 세 포인터로 본다. 인터프리터 frame은 추가로 method/bci/local/operand stack 정보를 가짐.

### 스레드 생성 시 stack 할당

위치: `src/hotspot/os/linux/os_linux.cpp` (Linux 기준)

```cpp
bool os::create_thread(Thread* thread, ThreadType thr_type, size_t stack_size) {
  pthread_attr_t attr;
  pthread_attr_init(&attr);

  // ★ stack 크기 결정
  if (stack_size == 0) {
    stack_size = os::Linux::default_stack_size(thr_type);  // -Xss 또는 OS 기본
  }
  pthread_attr_setstacksize(&attr, stack_size);

  // ★ OS에게 새 스레드 생성 요청
  int ret = pthread_create(&tid, &attr, (void* (*)(void*)) thread_native_entry, thread);

  if (ret != 0) {
    // 보통 "OutOfMemoryError: unable to create new native thread"
    return false;
  }
  return true;
}
```

→ `pthread_create`가 실패하는 흔한 이유:
- 시스템 thread 수 한계 (`ulimit -u`, `/proc/sys/kernel/threads-max`).
- 메모리 부족 (각 thread당 stack + native 자료구조).
- → `OutOfMemoryError: unable to create new native thread`.

### Stack overflow 감지

위치: `src/hotspot/share/runtime/stackOverflow.cpp`

HotSpot은 **stack의 끝 부근에 guard page**를 만들어 두고, stack이 거기까지 자라면 OS가 SEGV를 발생시킨다. signal handler가 SEGV를 catch하면 "stack overflow" 처리.

```cpp
// 매 메서드 진입 시 빠른 stack 체크
void JavaThread::stack_overflow_check() {
  if (_stack_pointer < _stack_overflow_limit) {
    // StackOverflowError throw
    THROW(vmSymbols::java_lang_StackOverflowError());
  }
}
```

→ guard page 메커니즘은 mprotect 기반. 00-overview의 Safepoint polling page와 같은 패턴 ("페이지 보호 위반을 신호 채널로 활용").

### Interpreter의 PC

HotSpot Template Interpreter (00-overview 02-deep-dive/D 참조):
- 각 bytecode 명령에 대응하는 native assembly template을 미리 생성.
- 현재 bytecode의 주소가 PC Register 역할 — 실제 native pc (template의 시작 주소).
- 다음 명령으로 가는 건 `pc += instruction_size`.

JIT 컴파일된 메서드:
- bytecode는 native code로 변환됨. 더 이상 bytecode offset 개념 없음.
- 그러나 GC/예외 처리를 위해 "이 native pc가 어느 bytecode offset에 대응하는지" 매핑 테이블 유지 (`PcDesc`).

### Virtual Thread Continuation 구현

위치: `src/hotspot/share/runtime/continuation.cpp`

```cpp
// Freeze: virtual thread의 stack을 Heap chunk로 옮김
freeze_result Continuation::freeze(JavaThread* thread, ...) {
  ContinuationEntry* cont = thread->last_continuation();

  // 1. 현재 stack frames 순회
  for (frame f = thread->last_frame(); !f.is_continuation_entry(); f = f.sender()) {
    // 2. 각 frame을 Heap의 stack chunk에 복사
    stackChunkOop chunk = ...;
    copy_frame_to_chunk(f, chunk);
  }

  // 3. OS thread stack은 비움 (또는 base까지 unwind)
  return freeze_ok;
}

// Thaw: stack chunk를 carrier의 OS thread stack에 복원
void Continuation::thaw(JavaThread* thread, stackChunkOop chunk) {
  // chunk의 frame들을 thread의 stack에 push
  for (each frame in chunk) {
    push_frame_to_stack(frame, thread);
  }
}
```

→ JEP 444 (JDK 21)의 핵심 구현. stack chunk는 일반 Java 객체 (`jdk.internal.vm.StackChunk` Klass 인스턴스) — Heap에 살고 GC 대상.

---

## 📜 5단계: 역사 — 스레드 모델의 진화

| 연도 | 릴리스 | 변화 | 이유 |
|---|---|---|---|
| 1996 | JDK 1.0 | Green Thread (M:1 user-level) | OS 스레드 지원 빈약, JVM이 직접 스케줄링 |
| 1998 | JDK 1.2 | **Native Thread (1:1)** | OS 스레드 모델 성숙, 멀티코어 활용 |
| 2002 | JDK 1.4 | NIO + Selector | I/O blocking 우회 (1:1 모델 안에서) |
| 2014 | JDK 8 | CompletableFuture | async 컴포지션, 여전히 1:1 |
| 2018 | Loom 프로젝트 시작 | — | M:N 모델 검토 |
| 2022 | JDK 19 (preview) | **Virtual Thread (preview)** | M:N + continuation |
| 2023 | JDK 21 (LTS, stable) | **Virtual Thread stable** ([JEP 444](https://openjdk.org/jeps/444)) | 수십만 thread 가능 |
| 2024 | JDK 23 | Pinning 일부 해소 | |
| 2025 | JDK 24 (예상) | synchronized pinning 제거 ([JEP 491](https://openjdk.org/jeps/491)) | virtual thread 더 자유 |

### Green Thread → Native Thread 전환의 의미

- **Green Thread (1996)**: JVM이 user-space에서 직접 스케줄링. OS 스레드 1개로 N개 Java 스레드 시뮬레이션. 멀티코어 활용 불가.
- **Native Thread (1998+)**: OS thread 1:1. 멀티코어 활용. 그러나 OS thread는 무겁고 비싸서 수만 개 만들기 어려움.

### Virtual Thread의 동기 — 1:1 모델의 한계

> 2010년대 마이크로서비스 시대 — 서버가 수만 개 동시 connection을 다뤄야 함.
> 1:1 thread 모델로는 수만 thread = 수십 GB stack → 불가능.
> 대안: NIO/Selector + CompletableFuture로 비동기 코드 작성 → "코드가 colorless 아닌 colored". 보통 코드와 async 코드가 다른 스타일.
> 
> Virtual Thread의 약속: "**평범한 synchronous 코드를 쓰면서 수십만 thread**" — colorless async.

### Continuation의 시대적 위치

Continuation은 사실 1970년대 Scheme의 `call/cc`까지 거슬러 가는 개념. JVM이 30년 만에 도입한 것은:
- Go의 goroutine, Erlang의 process, Kotlin Coroutine 등 다른 언어가 이미 성숙.
- JVM이 mainstream 백엔드 언어로 남으려면 이 기능이 필수가 됨.

---

## ⚖️ 6단계: 트레이드오프

### `-Xss` 트레이드오프 — Stack 크기 결정

| `-Xss` 작게 (256KB) | `-Xss` 크게 (4MB) |
|---|---|
| ✅ 스레드 더 많이 만들 수 있음 | ❌ 스레드 적게 |
| ❌ 깊은 재귀에서 StackOverflowError | ✅ 깊은 재귀 견딤 |
| ✅ 메모리 footprint 작음 | ❌ footprint 큼 |
| ❌ JIT 컴파일된 메서드의 inlined frame이 크면 위험 | ✅ |

**경험칙**:
- 일반 웹 서버: 기본 (`512KB` ~ `1MB`).
- 깊은 재귀 알고리즘 사용: 2~4MB.
- 스레드 수 매우 많이 필요 (~수천): 256~512KB. **단, virtual thread 고려가 더 나음**.

### Platform Thread vs Virtual Thread 트레이드오프

| | Platform Thread | Virtual Thread |
|---|---|---|
| OS 스레드 매핑 | 1:1 | M:N (carrier 공유) |
| Stack 위치 | OS thread stack (수동 할당) | Heap의 stack chunk |
| Stack 크기 | -Xss 고정 (보통 1MB) | 동적, 사용한 만큼만 |
| 최대 생성 가능 수 | ~수천 (OS 한계) | 수십만~수백만 |
| 생성 비용 | ~수 ms (OS syscall) | ~수 us (Heap object 생성) |
| Context switch | OS 영역 (~수 us) | JVM 영역 (~수 ns) |
| Blocking I/O 친화 | ❌ (thread 점유) | ✅ (자동 freeze) |
| CPU-bound 작업 | ✅ (전용 스레드) | △ (다른 vthread 차단) |
| synchronized | ✅ 정상 | ❌ pinning (JDK 24 해결 예상) |
| native call | ✅ 정상 | ❌ pinning |
| ThreadLocal | ✅ | △ (수가 많으면 메모리 ↑) |

**선택 가이드**:
- I/O bound (DB 호출, HTTP 클라이언트) + 평범한 동기 코드: **Virtual Thread**.
- CPU bound (이미지 처리, 계산): **Platform Thread (제한된 수)**.
- 둘 다 필요: hybrid — virtual thread + ExecutorService(`Executors.newFixedThreadPool`)로 CPU 작업은 platform pool에 위임.

### Stack-based vs Register-based VM (JVM vs Dalvik/ART)

| | Stack-based (JVM) | Register-based (Dalvik) |
|---|---|---|
| 명령어 길이 | 1 byte 다수 | ~4 byte |
| 명령어 수 | 많음 | 적음 |
| Bytecode 크기 | 작음 | 큼 (1.5~2배) |
| 인터프리터 성능 | 느림 | 빠름 |
| JIT 친화도 | 비슷 | 비슷 |
| 컴파일러 단순성 | ★ 단순 | 복잡 (register allocation 필요) |
| 플랫폼 독립 | ★ | 비슷 |

→ Android(Dalvik/ART)가 register-based를 택한 이유: 인터프리터 성능 + 모바일의 제한된 JIT 기회. 일반 JVM이 stack-based를 유지한 이유: 30년 호환성 + JIT이 어차피 register-based로 변환.

---

## 📊 7단계: 측정·진단

### `jstack` — 스레드 dump의 표준

```bash
# 전체 스레드 dump
jstack <pid>

# 락 contention 분석에 도움
jstack -l <pid>      # owned synchronizer 정보 포함
```

#### `jstack` 출력 해석

```
"http-nio-8080-exec-3" #45 daemon prio=5 os_prio=0 tid=0x00007f8a5c01a000 nid=0x4a23 waiting on condition [0x00007f8a5b3fe000]
   java.lang.Thread.State: WAITING (parking)
        at jdk.internal.misc.Unsafe.park(Native Method)
        - parking to wait for  <0x00000000e1f7e8c0> (a java.util.concurrent.locks.ReentrantLock$NonfairSync)
        at java.util.concurrent.locks.LockSupport.park(LockSupport.java:341)
        ...
```

**핵심 필드**:
- `"http-nio-8080-exec-3"` — 스레드 이름.
- `#45` — JVM 내부 ID.
- `daemon` — 데몬 스레드 (JVM 종료 시 강제 종료됨).
- `tid=0x...` — Java thread ID (16진수).
- `nid=0x...` — OS thread ID (`/proc/<pid>/task`에서 매칭 가능).
- `Thread.State` — 5가지 중 하나.

**Thread.State 5종**:

| State | 의미 | 흔한 원인 |
|---|---|---|
| `NEW` | 생성됐지만 start() 안 됨 | 코드 결함 |
| `RUNNABLE` | 실행 중 또는 가능 | 정상 |
| `BLOCKED` | synchronized lock 대기 | lock contention |
| `WAITING` | `Object.wait`, `Lock.lock`, `Thread.join` 등 | I/O blocking, lock 대기 |
| `TIMED_WAITING` | `Thread.sleep`, `wait(timeout)` 등 | 의도적 대기 |
| `TERMINATED` | 종료됨 | 정상 |

#### 데드락 진단

```bash
jstack <pid> | grep -A 5 'Found one Java-level deadlock'
```

JVM이 자동 감지해서 dump에 표시:
```
Found one Java-level deadlock:
=============================
"Thread-1":
  waiting to lock monitor 0x... (object 0x..., a java.lang.Object),
  which is held by "Thread-2"
"Thread-2":
  waiting to lock monitor 0x... (object 0x..., a java.lang.Object),
  which is held by "Thread-1"
```

### 스레드 수 측정

```bash
# 현재 thread 수
jcmd <pid> Thread.print | grep -c '^"'

# OS 레벨 (Linux)
ls /proc/<pid>/task | wc -l
```

### 메모리 별 스레드 영역 추정

```bash
# Native Memory Tracking 활성화 후
java -XX:NativeMemoryTracking=summary -jar app.jar
jcmd <pid> VM.native_memory summary

# 출력 중:
#   Thread (reserved=521MB, committed=521MB)
#         (thread #500)
#         (stack: reserved=520MB, committed=520MB)
```

→ 500 스레드 × 약 1MB = 520MB. 이게 RSS의 큰 부분.

### Virtual Thread pinning 감지

```bash
# JVM 옵션
java -Djdk.tracePinnedThreads=full -jar app.jar

# 출력 (pinning 발생 시):
# Thread[#23,virtual=Lambda$1234/0x..., ...]
#     java.base/java.lang.VirtualThread.runWith
#     at SynchronizedExample.method(SynchronizedExample.java:12)
#     <== monitors:1
```

`<== monitors:1`이 pinning 발생 — synchronized 블록 안에서 blocking 호출.

### JFR 이벤트

```bash
jcmd <pid> JFR.start name=threads duration=60s settings=profile filename=threads.jfr
jfr summary threads.jfr | grep -E 'Thread|VirtualThread'
```

**핵심 이벤트**:
- `jdk.JavaThreadStatistics` — 스레드 수 추세.
- `jdk.ThreadStart` / `jdk.ThreadEnd` — 스레드 생성/종료.
- `jdk.VirtualThreadStart` / `jdk.VirtualThreadEnd` (JDK 21+).
- `jdk.VirtualThreadPinned` — pinning 발생.
- `jdk.VirtualThreadSubmitFailed` — virtual thread 스케줄링 실패.

### 운영 시나리오 진단 매트릭스

| 증상 | 진단 명령 | 원인 |
|---|---|---|
| `StackOverflowError` | stack trace 본문 보기 | 무한 재귀 또는 깊이 너무 큼 |
| `OOM: unable to create new native thread` | `ulimit -u`, `/proc/sys/kernel/pid_max` | OS thread 한계 |
| RSS는 큰데 Heap은 작음 | `jcmd VM.native_memory summary` Thread 항목 | 스레드 수 폭증 |
| jstack에 `BLOCKED` 스레드 많음 | `jstack -l` | lock contention |
| Virtual Thread 도입 후 처리량 ↓ | `-Djdk.tracePinnedThreads=full` | pinning |
| 데드락 의심 | `jstack` | JVM이 자동 감지 |

---

## ⚔️ 8단계: 꼬리질문 트리

### Q1. JVM의 메모리 영역 중 per-thread 인 것은 무엇인가요?

**예상 답변**:
> 3가지: JVM Stack, PC Register, Native Method Stack.
> 모두 스레드가 생성될 때 OS로부터 할당받고, 스레드가 종료될 때 반환.
> Heap, Metaspace, Code Cache는 shared.

#### 🪝 Q1-1: JVM Stack과 OS thread stack은 같은 건가요?

> 논리적으론 다르지만 HotSpot 구현에서는 같은 OS thread stack에 통합됨.
> JVM Stack(Java method frames)과 Native Method Stack(JNI 호출 frames)이 같은 stack에 자연스럽게 쌓임. 경계는 논리적.

##### 🪝 Q1-1-1: 그럼 `-Xss`는 무엇을 제어하나요?

> OS thread stack 전체 크기. JVM frames + Native frames이 함께 쓰는 영역. 기본 OS/플랫폼 따라 512KB ~ 1MB.

### Q2. Stack Frame 안에는 무엇이 있고, 크기는 어떻게 결정되나요?

**예상 답변**:
> 3가지 영역:
> 1. **Local Variable Array** — 파라미터 + 로컬 변수. 크기는 ClassFile Code attribute의 `max_locals`.
> 2. **Operand Stack** — bytecode 실행 중 임시 계산 공간. 깊이는 `max_stack`.
> 3. **Frame Data** — CP 참조, return PC, 이전 frame pointer 등.
> 
> max_stack/max_locals는 javac가 미리 계산해서 ClassFile에 저장 → JVM이 Frame을 한 번에 정확한 크기로 할당.

#### 🪝 Q2-1: 그럼 long을 로컬 변수로 쓰면 어떻게 되나요?

> long과 double은 64비트 — Local Variable Array에서 **2 슬롯을 차지**. slot[N]에 long을 저장하면 slot[N+1]은 사용 불가.
> Operand Stack에서도 마찬가지로 2 슬롯.
> javac가 max_locals 계산 시 long/double을 2로 카운트.

### Q3. `StackOverflowError`와 `OutOfMemoryError: unable to create new native thread`의 차이는?

**예상 답변**:
> - `StackOverflowError`: **한 스레드의 stack 깊이가 -Xss 한계 초과**. 무한 재귀, 너무 깊은 호출 체인.
> - `OOM: unable to create new native thread`: **새 OS thread 생성 실패**. 시스템 thread 수 한계 또는 메모리 부족. 새 스레드 시도 시 발생.
> 
> 진단:
> - SOE: stack trace 본문에서 같은 메서드 반복 패턴.
> - OOM thread: `ulimit -u`, `/proc/sys/kernel/threads-max`, 현재 thread 수 확인.

#### 🪝 Q3-1: SOE를 잡으면 어떻게 되나요? 안전한가요?

> `StackOverflowError`는 `Error`이지만 catch는 가능. 단:
> 1. catch한 시점에 stack은 거의 다 찬 상태 — 그 안에서 또 다른 메서드 호출 시 다시 SOE.
> 2. 무한 재귀가 원인이면 catch해도 해결 안 됨 — 원인 코드 수정 필요.
> 3. JVM 상태 손상 가능성 — catch 후 정상 실행 보장 안 됨.
> 
> 일반 권장: catch하지 말고 코드 수정. recursive를 iterative로 변환 또는 tail call 비유사 패턴 사용.

### Q4. PC Register가 native 메서드 실행 중 undefined인 이유는?

**예상 답변**:
> Java 메서드의 PC는 **bytecode offset** 또는 그에 대응하는 interpreter native code pc.
> Native 메서드는 C/C++로 작성된 함수 — bytecode 없음, native instruction에서 직접 실행.
> 그동안 JVM의 PC Register는 의미 있는 값을 가질 수 없음 → undefined.
> Native 메서드 return 후 Java로 돌아오면 caller의 다음 bytecode를 가리킴.

### Q5. Virtual Thread와 Platform Thread의 가장 큰 차이는?

**예상 답변**:
> Stack 위치 + 스케줄링 주체:
> - Platform Thread: OS thread 1:1. Stack은 OS thread stack (1MB 정도). 스케줄링은 OS.
> - Virtual Thread: M개 virtual : N개 carrier OS thread. Stack은 **Heap의 stack chunk** (가변 크기). 스케줄링은 JVM.
> 
> 결과: virtual thread는 수십만 개 생성 가능, blocking 호출 시 자동으로 carrier에서 freeze되어 다른 vthread 실행.

#### 🪝 Q5-1: Stack chunk가 Heap에 있다는 게 무슨 의미인가요?

> Virtual thread가 freeze되면 그 stack 데이터(frame들)가 **`jdk.internal.vm.StackChunk` Java 객체**로 Heap에 저장.
> 일반 객체와 동일하게 GC 대상 — virtual thread가 unreachable이면 stack chunk도 회수.
> 깊이가 작은 vthread는 작은 chunk, 깊은 vthread는 큰 chunk — sparse하지 않게 실제 깊이만 사용.

##### 🪝 Q5-1-1: 그럼 virtual thread가 너무 많아지면 Heap이 부족해지나요?

> Yes. Virtual thread 수가 늘면 stack chunk 수도 늘어 Heap 사용량 증가.
> 그러나 platform thread × 1MB와 비교하면 훨씬 작음 — 평균 vthread stack은 수 KB.
> 진단: Heap dump에서 `jdk.internal.vm.StackChunk` 인스턴스 수.

### Q6. Virtual Thread Pinning이 무엇이고, 언제 발생하나요?

**예상 답변**:
> Pinning = virtual thread가 carrier thread에 묶여서 freeze 불가능한 상태.
> 트리거:
> 1. `synchronized` 메서드 또는 블록 안 (JDK 21~23).
> 2. JNI native call 실행 중.
> 
> Pinning 중에 blocking 호출이 일어나면 carrier도 함께 block → 다른 vthread 실행 불가 → 처리량 저하.
> 
> 해결:
> - `synchronized` → `ReentrantLock` (Java-level lock).
> - JDK 24+ (JEP 491) — synchronized pinning 제거.

#### 🪝 Q6-1: Pinning을 어떻게 진단하나요?

> `-Djdk.tracePinnedThreads=full` JVM 옵션. Pinning 발생 시 stack trace + monitor 정보 출력.
> 또는 JFR `jdk.VirtualThreadPinned` 이벤트.
> 출력에서 `<== monitors:1` 패턴이 synchronized 블록 내 pinning 표식.

### Q7. (Killer) JVM이 RSS 5GB를 쓰는데 `-Xmx`는 2GB로 잡았습니다. 나머지 3GB가 어디서 오는지 어떻게 진단하시겠어요?

**예상 답변**:
> 단계적 진단:
> 
> 1. **Native Memory Tracking 활성화**:
>    ```
>    java -XX:NativeMemoryTracking=summary -jar app.jar
>    jcmd <pid> VM.native_memory summary
>    ```
> 
> 2. **각 영역 committed 합계 확인** — 일반적 분포:
>    - Java Heap: 2GB (Xmx 그대로)
>    - Metaspace + Compressed Class Space: 200~400MB
>    - **Thread**: 스레드 수 × 1MB (이게 핵심) — 500 스레드면 500MB
>    - Code Cache: 240MB reserve, committed는 컴파일된 코드량
>    - GC 자료구조 (Card Table, Mark Bitmap): Heap의 1.5% 정도
>    - Direct Memory: NIO 사용량
>    - Internal (JVM 내부): 100~200MB
> 
> 3. **Thread 영역이 의외로 크면**:
>    - `jcmd <pid> Thread.print | grep -c '^"'` — 현재 thread 수.
>    - 수백 ~ 수천이면 thread pool 폭증 의심.
>    - 스레드 이름 패턴으로 누가 만들었는지 식별 (Netty, Tomcat, ForkJoinPool, application).
> 
> 4. **해결**:
>    - Thread pool 크기 제한 (`Executors.newFixedThreadPool(N)` 등).
>    - Virtual Thread로 마이그레이션 (I/O bound 작업이라면).
>    - `-Xss` 축소 (256KB ~ 512KB) — 단, SOE 위험 균형.
>    - 컨테이너 limit 재조정.

#### 🪝 Q7-1: Container OOM-killed인데 Heap dump는 정상이에요. 어떻게 진단하시겠어요?

> Heap 외 영역의 합이 container limit을 초과한 것.
> 1. NMT로 영역별 committed 합산.
> 2. 특히 의심:
>    - **Thread**: 스레드 수 폭증.
>    - **Metaspace**: ClassLoader 누수.
>    - **Code Cache**: 동적 클래스 많은 앱.
>    - **Direct Memory**: NIO/Netty 누수.
>    - **Native libraries**: JNI 라이브러리의 native allocation (NMT가 못 봄).
> 3. Container limit의 50~70%로 `-Xmx` 조정.
> 4. 모든 영역의 합이 limit 안에 들도록 명시 조정 (-Xmx, -XX:MaxMetaspaceSize, -XX:ReservedCodeCacheSize, -XX:MaxDirectMemorySize, -Xss × thread 수).

---

## 🔗 다음 단계

- → [04. Code Cache](./04-code-cache.md): JIT 결과 native code 저장소
- → [05. Direct Memory](./05-direct-memory.md): Off-heap NIO
- → [06. GC bookkeeping](./06-gc-bookkeeping-and-others.md): Card Table, RSet, Mark Bitmap
- ← [02. Metaspace & Class Space](./02-metaspace-and-class-space.md): Class 메타데이터
- ← [01. Heap & TLAB](./01-heap-and-tlab.md): Heap의 세대 구조

## 📚 참고

- **JVMS §2.5.2 (Java Virtual Machine Stacks)**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.5.2
- **JVMS §2.5.3 (Heap), §2.5.4 (Method Area), §2.5.5 (Runtime Constant Pool)**: 같은 페이지의 인접 섹션
- **JEP 444 Virtual Threads**: https://openjdk.org/jeps/444
- **JEP 491 (preview) Synchronize Virtual Threads without Pinning**: https://openjdk.org/jeps/491
- **HotSpot `frame.hpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/frame.hpp
- **HotSpot `javaThread.hpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/javaThread.hpp
- **HotSpot `continuation.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/continuation.cpp
- **Oracle — Virtual Threads guide**: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
- **Ron Pressler — Loom presentation**: JavaOne 2018+, Devoxx 시리즈
