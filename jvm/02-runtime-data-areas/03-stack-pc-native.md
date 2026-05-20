# 02-03. Stack & PC & Native Method Stack — 스레드 하나당 받는 메모리

> `-Xmx2g` 짜리 JVM이 RSS 5GB를 쓴다? 그 차이의 상당 부분이 **스레드 수 × 1MB**다.
> 한 스레드가 만들어질 때마다 JVM은 OS로부터 **JVM Stack + PC Register + Native Method Stack** 세 가지 영역을 따로 할당받는다. Heap과 무관, GC와도 무관, `-Xmx`로도 제어 안 됨.
> 500 스레드 × 1MB = 500MB. 이게 "왜 우리 JVM이 메모리를 많이 쓰지?"의 가장 흔한 답이다.

---

## 이 문서의 사용법

이 문서는 **면접용 마인드맵**을 따라 선형으로 펼친 구조다. 학습 순서 = 면접 답변 순서 = 백지에 그리는 순서.

1. **0장 마인드맵을 먼저 외운다** — 루트 한 문장 + 5가지 가지 + 각 가지의 키워드 3개.
2. **1~5장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 정확히 대응.
3. **6장 면접 워크플로우로 검증** — 질문을 보면 어느 가지로 가야 하는지 매핑.
4. **7장 꼬리질문으로 깊이 점검**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"JVM Stack은 per-thread LIFO 메모리다. 한 스레드당 OS가 1MB stack을 할당하고, 그 위에 Stack Frame들을 쌓고 빼며 메서드 호출을 진행한다."**

이 한 문장에서 모든 답변이 출발한다. 어떤 질문이 와도 이 문장부터 말하고 적절한 가지로 분기.

### 5개 가지 — 순서를 외운다

```
                      [ROOT: JVM Stack = per-thread LIFO]
                                    │
       ┌─────────┬──────────────────┼──────────────────┬─────────┐
       │         │                  │                  │         │
      ① WHY    ② WHAT             ③ HOW              ④ 운영    ⑤ 진화
   per-thread  3종 세트         Frame 내부       (시니어 진단) (역사)
       │         │                  │                  │         │
       │    ┌────┼────┐         ┌───┼───┐         ┌────┼────┐    │
    LIFO본성  JVM Stack       Local    Operand   -Xss   SOE  Green→Native→
    멀티격리  PC Register     Var Array Stack    트레이드  vs   Virtual
    Heap반대  Native M.S.    (max_     (stack-  jstack OOM-  Continuation
              ↑              locals)   based)   NMT   thread Pinning
         물리적으론
         OS stack 1개
```

### 가지별 핵심 키워드 (각 가지 3개씩만)

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① WHY per-thread** | 함수호출=LIFO | 멀티스레드 격리 | 락 회피 |
| **② WHAT 3종 세트** | JVM Stack / PC / Native | per-thread, 모두 | 물리적 stack 1개 |
| **③ HOW Frame 내부** | Local Var Array | Operand Stack | Frame Data |
| **④ 운영** | -Xss 트레이드오프 | SOE vs OOM-thread | jstack / NMT |
| **⑤ 진화** | Green→Native | Virtual Thread | Pinning |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 질문에 맞는 가지 1개 선택 → 그 가지의 키워드 3개 순서대로 설명 → 듣는 사람의 관심에 따라 인접 가지로 확장

---

## 1. 가지 ①: WHY per-thread — 왜 스레드마다 따로인가

### 1.1 핵심 질문

> "JVM이 Heap, Metaspace, Code Cache는 공유로 두면서 Stack만 스레드마다 따로 두는 이유는?"

### 1.2 키워드 1 — 함수 호출 자체가 LIFO

```
foo() 호출 → bar() 호출 → baz() 호출
        ↓             ↓             ↓
      push          push          push
                                    ↓
                                  return
                                    ↓
                                   pop
                              (가장 최근 호출이 먼저 끝남)
```

함수는 호출 순서의 **역순으로 종료**한다. 마지막에 호출된 함수가 가장 먼저 끝나고 caller로 돌아간다. 이건 본질적으로 LIFO 자료구조 = **Stack**. 다른 자료구조로 표현할 수 없는, 호출 의미론 그 자체.

### 1.3 키워드 2 — 멀티스레드 격리

```
[shared stack으로 만들면 (가상)]               [per-thread stack (실제)]
━━━━━━━━━━━━━━━━━━━━━━━━━                    ━━━━━━━━━━━━━━━━━━━━━━━

Thread 1: foo() 호출 중                       Thread 1의 Stack: foo()
  └→ 공유 stack에 push (락!)                  Thread 2의 Stack: bar()
Thread 2: bar() 호출 중                       Thread 3의 Stack: baz()
  └→ 공유 stack push 대기...
Thread 3: baz() 호출 중                       완전 독립, lock 불필요
  └→ 대기...

함수 호출마다 lock contention                  lock-free, 진정한 병렬 실행
```

**함수 호출은 가장 빈번한 연산**이다. 이걸 매번 락으로 직렬화하면 멀티스레드의 의미가 사라진다. 그래서 Stack은 본질적으로 per-thread여야 한다.

### 1.4 키워드 3 — Heap과 반대 수명

| 영역 | 데이터 수명 | 관리 방식 |
|---|---|---|
| **Stack** | 호출 범위와 함께 (메서드 끝나면 소멸) | LIFO push/pop, 컴파일 타임 결정 |
| **Heap** | 호출 범위와 무관 (참조 살아 있으면 유지) | GC, 런타임 추적 |

new로 만든 객체는 메서드가 끝나도 다른 곳에서 참조하면 살아 있어야 한다 → **Heap**.
지역 변수는 메서드가 끝나면 무조건 사라진다 → **Stack**.

수명 관리 모델 자체가 정반대이기 때문에 두 영역이 분리되었다.

### 1.5 비유로 굳히기

> **콜택시 회사**: Heap = 공용 차고 (모든 기사가 같이 씀, 차 = 객체). JVM Stack = 각 기사의 개인 운행일지 책 (page = Stack Frame). PC Register = 각 기사가 들고 있는 책갈피. Native Method Stack = 외부 기사 (C/JNI)를 부를 때 그쪽의 별도 일지.

---

## 2. 가지 ②: WHAT — per-thread 3종 세트

### 2.1 핵심 질문

> "스레드마다 따로 할당되는 게 정확히 뭐가 있나요? 셋의 관계는?"

### 2.2 키워드 1 — 3종 세트의 정체

| 영역 | 무엇 | 크기 | 채움 시점 |
|---|---|---|---|
| **JVM Stack** | Java 메서드 호출의 Stack Frame들 (LIFO) | `-Xss` (보통 512KB~1MB) | 메서드 호출 시 |
| **PC Register** | 현재 실행 중인 bytecode 명령의 주소 | native word 1개 (8B) | 매 명령 실행 시 |
| **Native Method Stack** | JNI 등 native(C/C++) 호출 시의 C Frame | OS thread stack과 공유 | JNI 진입 시 |

**3개 모두 스레드 생성 시 OS가 할당하고, 스레드 종료 시 반환**. Heap·Metaspace·Code Cache는 공유.

### 2.3 키워드 2 — per-thread × N의 의미

```
Thread #1: [JVM Stack 1MB][PC 8B][Native Stack ~]
Thread #2: [JVM Stack 1MB][PC 8B][Native Stack ~]
Thread #3: [JVM Stack 1MB][PC 8B][Native Stack ~]
...
Thread #500: ...

= 500 × 약 1MB ≈ 500MB의 per-thread footprint
  (-Xmx와 완전 무관)
```

이게 "RSS는 큰데 Heap dump는 정상"의 가장 흔한 답이다. NMT(Native Memory Tracking)의 `Thread` 항목으로 확인.

### 2.4 키워드 3 — 물리적으론 stack 1개 (가장 흔한 오해 해소)

"JVM Stack", "Native Method Stack", "Operand Stack" — 이 3개 이름이 각각 별개의 메모리 영역인 것처럼 들린다. **실제로는**:

| JVM Spec 용어 | 물리적 실체 |
|---|---|
| **JVM Stack** | OS thread stack의 **Java Frame들이 쌓이는 부분** |
| **Native Method Stack** | OS thread stack의 **C Frame들이 쌓이는 부분** (★ 같은 stack) |
| **Operand Stack** | 각 Java Frame **내부의** 작은 임시 계산 영역 (★ thread-level 아님) |

```
한 스레드 = OS가 할당한 stack 1MB (물리적으로 1개의 연속 메모리)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[stack top — SP가 가리킴, 새 호출이 여기로 push]
┌──────────────────────────────────────────┐
│ C Frame: JNI native 함수                  │ ┐
│   (인자, 지역변수, return addr)            │ │ "Native Method Stack"
├──────────────────────────────────────────┤ │  영역 (논리적)
│ JNI stub Frame (Java↔Native 전환)         │ ┘
├──────────────────────────────────────────┤
│ Java Frame: Main.main(args)               │ ┐
│ ┌──────────────────────────────────────┐ │ │
│ │ Local Var Array (slot[0..])          │ │ │
│ ├──────────────────────────────────────┤ │ │ "JVM Stack" 영역
│ │ ★ Operand Stack (push/pop)           │ │ ├  (논리적)
│ ├──────────────────────────────────────┤ │ │
│ │ Frame Data (CP ref, return PC, FP)   │ │ │ ★ Operand Stack은
│ └──────────────────────────────────────┘ │ │   thread-level 아닌
├──────────────────────────────────────────┤ │   Frame **내부** 영역
│ Java Frame: Main.<clinit>                 │ ┘
├──────────────────────────────────────────┤
│ C Frame: JavaMain (JVM 부트스트랩)         │ ┐
│ C Frame: java launcher main()             │ ├  "Native Method Stack"
│ C Frame: _start, __libc_start_main        │ ┘  (다시)
└──────────────────────────────────────────┘
[stack bottom — OS 할당 시작점]

▲ 물리적 메모리는 연속된 1개. 점선 영역은 "논리적 분류"일 뿐.
▲ Java Frame과 C Frame은 같은 stack에 LIFO로 섞여 쌓일 수 있음.
```

**핵심 규칙 3가지**:
1. **물리적 1개 stack** — OS가 thread 생성 시 1MB를 한 번에 할당. 모든 frame이 이 안에.
2. **Frame 종류는 2개** — Java Frame (HotSpot이 만듦, Operand Stack 포함) / C Frame (C 컴파일러가 만듦).
3. **Operand Stack은 Frame 부속물** — 각 Java Frame 안의 작은 LIFO 영역. 산술·논리 bytecode(iadd, imul 등)가 여기서 계산을 수행하고, load/store bytecode(iload, istore)가 Local Var와 Operand Stack 사이를 오간다.

### 2.5 자주 하는 오해 — "bytecode는 Frame 안에 들어있나?"

위 규칙에서 "Operand Stack은 Frame 부속물"이라는 표현 때문에 **"그럼 Java Frame은 bytecode 명령을 실행 안 하나?"** 라는 오해가 생기기 쉽다. 정확히 잡고 가자.

> **Java Frame은 bytecode를 "실행하는 장소"가 맞다. 단, bytecode 자체는 Frame 안이 아니라 Metaspace에 있고, Interpreter/JIT이 그것을 읽으며 Frame의 내용물을 만지는 방식으로 실행한다.**

#### 배우-대본-작업장 모델

| 역할 | 정체 | 위치 |
|---|---|---|
| **배우(실행자)** | Interpreter 또는 JIT'd native code | Code Cache / Interpreter template |
| **대본(명령)** | bytecode | **Metaspace** (Method의 Code attribute) |
| **작업장(데이터)** | Stack Frame = Local Var Array + Operand Stack + Frame Data | JVM Stack 안 |

bytecode 자체는 Frame 안에 들어있지 않다. **PC Register**가 "지금 어느 명령을 가리키는지" 추적하고, Interpreter(또는 JIT 코드)가 그 명령을 읽어서 **Frame의 내용물을 만지는 방식**으로 실행한다.

#### bytecode가 Frame을 어떻게 만지는가

```java
int sum = a + b;
```

이걸 컴파일하면 4개 bytecode가 나온다:

```
iload_1     ; "Local Var slot[1] 값을 Operand Stack에 push해라"
iload_2     ; "Local Var slot[2] 값을 Operand Stack에 push해라"
iadd        ; "Operand Stack top 2개 pop, 더해서 push해라"
istore_3    ; "Operand Stack top pop, Local Var slot[3]에 저장해라"
```

각 명령이 Frame의 어느 영역을 만지는지:

| Bytecode | Local Var | Operand Stack |
|---|---|---|
| `iload_1` | 읽음 (slot[1]) | push |
| `iload_2` | 읽음 (slot[2]) | push |
| `iadd` | 안 만짐 | pop 2 + push 1 |
| `istore_3` | 씀 (slot[3]) | pop |

→ **4개 명령 모두 Frame 안에서 작업한다**. Local Var와 Operand Stack은 둘 다 Frame의 영역. 산술(`iadd`)만 Operand Stack 위에서 일어나고, load/store는 두 영역 사이를 오간다.

#### 정확한 모델 그림

```
   ┌─ Metaspace ─────────────────────────┐
   │ Method "compute":                    │
   │   bytecode: [iload_1][iload_2]      │  ← 대본
   │            [iadd][istore_3][ireturn] │
   └──────────────────────────────────────┘
              ↑
              │ PC Register가 가리킴
              │ "지금 iadd 차례"
              │
   ┌─ Interpreter (or JIT'd code) ───────┐
   │ "iadd 들어왔다 → 현재 Frame의         │  ← 배우
   │  Operand Stack을 본다 →              │
   │  top 2개 pop → 더해서 → push"        │
   └──────────────────────────────────────┘
              │
              │ 만짐
              ↓
   ┌─ JVM Stack의 현재 Frame ─────────────┐
   │ Local Var Array: [_, a, b, _]        │
   │ Operand Stack:   [3, 4] → [7]        │  ← 작업장
   │ Frame Data: CP ref, return PC        │
   └──────────────────────────────────────┘
```

3개가 같이 움직여야 메서드 실행이 진행된다:
- **bytecode** (Metaspace) → 무엇을 할지
- **PC Register** (per-thread) → 지금 어디까지 왔는지
- **Frame** (JVM Stack) → 현재 데이터 상태

이 그림을 머릿속에 박아두면, "Frame이 bytecode를 실행하나, 안 하나?"라는 혼동이 영원히 사라진다. **Frame은 bytecode의 실행 무대다. 단지 bytecode 자체를 보관하는 곳은 아니다**.

### 2.6 PC Register가 native 메서드 중 undefined인 이유

- Java 메서드의 PC = bytecode offset (또는 interpreter native pc).
- Native 메서드는 C/C++ 함수 → bytecode 없음, native instruction 직접 실행.
- 그 동안 JVM의 PC Register는 의미 있는 값을 가질 수 없음 → **undefined**.
- Native return 후 Java로 돌아오면 caller의 다음 bytecode를 가리킴.

### 2.7 Virtual Thread는 다른 모델 (가지 ⑤에서 깊이 설명)

평범한 platform thread는 위처럼 OS stack을 그대로 쓴다. JDK 21+의 virtual thread는 **stack chunk를 Heap에 저장**한다. → 가지 ⑤로.

---

## 3. 가지 ③: HOW — Frame 내부 3영역

### 3.1 핵심 질문

> "Stack Frame 안에는 정확히 뭐가 들어있고, 크기는 어떻게 결정되나요?"

### 3.2 키워드 1 — Local Variable Array

```
Local Variable Array (Frame의 첫 영역)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

slot[0] = this        (인스턴스 메서드의 경우) 또는 첫 파라미터(static)
slot[1] = 파라미터 1
slot[2] = 파라미터 2
...
slot[N] = 지역 변수
slot[N+1] = 지역 변수
...

크기: max_locals (ClassFile의 Code attribute에 적힘)
각 슬롯: 32-bit 단위 (int, float, ref, returnAddress)
        ★ long/double은 2 슬롯 차지
```

**예시**:
```java
public int compute(long a, String s, int b) {
    int local = a + b;
    return local;
}
```

```
slot[0] = this       (인스턴스 메서드라서)
slot[1] = a (long, low)  ┐
slot[2] = a (long, high) ┘ ← long은 2 슬롯
slot[3] = s (reference)
slot[4] = b (int)
slot[5] = local (int)
```

**중요 사실**: javac는 슬롯 재사용으로 `max_locals`를 최소화한다. 메서드 후반에 안 쓰는 변수의 슬롯을 새 변수에 재할당. 이걸 알아야 `max_locals` 값이 직관과 다를 때 당황 안 한다.

### 3.3 키워드 2 — Operand Stack (stack-based VM의 본질)

```java
int result = a + b;
```

```
bytecode               Operand Stack 상태
                       (초기) []
iload  a               [a]
iload  b               [a, b]
iadd                   [a+b]      ← top 2개 pop, sum push
istore result          []         ← pop, slot[result]에 저장
```

**iadd = "stack top 2개를 pop, 더해서 push"**. 모든 산술이 이 패턴. Operand Stack은 임시 계산 공간.

#### 왜 register-based가 아니라 stack-based인가

```
Register-based (x86, ARM):           Stack-based (JVM):
━━━━━━━━━━━━━━━━━━━━                  ━━━━━━━━━━━━━━━━━

ADD R3, R1, R2                        iload_1    ; push local[1]
                                      iload_2    ; push local[2]
                                      iadd       ; pop 2, push sum
                                      istore_3   ; pop, store local[3]

명령 길이: ~6 byte                    명령 길이: 1 byte 각
플랫폼 종속: 레지스터 수가 CPU마다 다름  플랫폼 독립: stack은 추상
```

**stack-based 선택의 이유**:
1. **플랫폼 독립** — register 수가 x86/ARM/RISC-V마다 다 다름. stack은 "n개 push/pop"으로 어디서나 동일.
2. **명령어 인코딩 단순** — operand 없이 1바이트 명령 → bytecode 파싱 빠름.
3. **컴파일러 단순** — stack-based 코드 생성이 register allocation보다 훨씬 단순 (1995년 시점).

**트레이드오프**: 명령어 수가 많아 인터프리터 성능이 register-based보다 느림. 그래서 **JIT 컴파일이 필수** — JIT이 bytecode를 register-based native code로 변환하면서 이 비용이 사라짐.

### 3.4 키워드 3 — Frame Data

```
Frame Data (Frame의 마지막 영역)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- Constant Pool Reference  (현재 메서드의 CP 가리킴)
- Return PC                (caller의 bytecode로 돌아갈 주소)
- Previous Frame Pointer   (이전 Frame의 base)
- Dynamic Linking 정보     (vtable lookup 캐시 등)
```

이 영역이 함수 호출/리턴의 메커니즘을 담당. return 시 Return PC를 PC Register에 복원하면 caller의 다음 명령으로 자동 진행.

#### PC Register와 Return PC — 두 종류의 PC 구분

"PC"라는 단어가 두 군데서 나오기 때문에 혼동하기 쉽다. 정리:

| 구분 | 위치 | 역할 | 수명 |
|---|---|---|---|
| **PC Register** | per-thread (스레드별 1개) | **지금 이 스레드가 실행 중인 bytecode 주소** | 스레드 살아있는 동안 |
| **Return PC** | Frame Data 안 (Frame마다 1개) | **caller가 어디까지 갔다가 callee를 불렀는지 책갈피** | 그 frame 살아있는 동안 |

둘은 별개의 저장소지만, **함수 호출/리턴 시 서로 값을 주고받는다**. 이 핑퐁이 함수 호출 메커니즘 그 자체.

#### 호출 시 — PC Register → Return PC로 백업

```java
public void caller() {
    foo();           // ← bytecode offset 5에 invokestatic
    int x = 10;      // ← bytecode offset 8 (foo 끝나면 여기로 와야 함)
}
```

```
호출 직전:
  PC Register = 5  (caller의 invokestatic 명령 가리킴)
  caller Frame 활성

invokestatic foo 실행:
  ① PC Register를 다음 명령(8)으로 진행
  ② callee(foo)용 새 Frame 만들면서
     Frame Data에 Return PC = 8 박아둠   ← ★ 책갈피 저장
  ③ PC Register = foo의 첫 bytecode 주소

호출 직후:
  PC Register = (foo 첫 명령)
  foo Frame 활성
  foo Frame Data.Return PC = 8 (caller 책갈피)
```

#### 리턴 시 — Return PC → PC Register로 복원

```
foo 안에서 ireturn 실행:
  ① foo Operand Stack에서 반환값 pop
  ② foo Frame Data.Return PC = 8 을 읽음    ← ★ 책갈피 회수
  ③ foo Frame 통째로 pop (소멸)
  ④ PC Register = 8 로 복원                ← ★ 책갈피를 새 현재 위치로
  ⑤ caller Frame 다시 활성

복원 후:
  PC Register = 8 (caller의 다음 명령)
  caller가 마치 foo가 한 줄이었던 것처럼 자연스럽게 계속
```

#### 그림으로

```
[호출 전]                    [foo 실행 중]                    [리턴 후]
━━━━━━━━━                   ━━━━━━━━━━━━━                    ━━━━━━━━

JVM Stack:                   JVM Stack:                       JVM Stack:
┌──────────┐                 ┌──────────┐                     ┌──────────┐
│          │                 │ foo Frame│                     │          │
│ caller   │                 │ ├Local   │                     │ caller   │
│  Frame   │                 │ ├Operand │                     │  Frame   │
└──────────┘                 │ └Data    │                     └──────────┘
                             │   ↳Ret PC│ = 8 ★
PC Register:                 ├──────────┤                     PC Register:
  = 5                        │ caller   │                       = 8 ★
  (caller offset 5)          │  Frame   │                       (caller offset 8,
                             └──────────┘                        Return PC에서 복원)

                             PC Register:
                               = foo 첫 명령
```

★ **Return PC는 "임시 보관소"**. 평소엔 가만히 누워있다가, callee가 죽을 때 PC Register로 부활시켜 caller를 살린다.

#### 한 줄 정리

> **PC Register = "지금 어디 있는지" (per-thread, 1개). Return PC = "여기로 돌아와라" (각 Frame이 하나씩 들고 있는 책갈피). 호출 시 PC Register 값을 Return PC로 백업하고, 리턴 시 Return PC를 PC Register로 복원한다.**

### 3.5 Frame 크기가 미리 정해지는 이유 (max_stack / max_locals)

```text
javap -v Main.class

public static void main(java.lang.String[]);
  Code:
    stack=2, locals=1, args_size=1   ← ★ max_stack=2, max_locals=1
```

ClassFile의 Code attribute에 javac가 미리 계산해서 박아둠. JVM은 Frame을 만들 때 이 두 값을 보고 **한 번에 정확한 크기로 할당**. 메서드 실행 중 stack growth 같은 동적 확장 없음 → Frame allocation이 빠르고 deterministic.

→ Stack 동작을 이해하려면 ClassFile의 Code attribute를 이해해야 함. [01-classfile-format.md](../01-class-lifecycle/01-classfile-format.md) 참조.

### 3.6 실행 추적 — Java 호출 흐름 (compute(1, 2))

```
main Frame                            compute Frame (새로 push)
┌──────────────────┐                  ┌──────────────────┐
│ Operand Stack    │  invokestatic    │ Local Var        │
│  [2]             │  ─────────────→  │  slot[0] = 1 (a) │
│  [1]             │  (인자 자동 이동) │  slot[1] = 2 (b) │
└──────────────────┘                  ├──────────────────┤
                                      │ Operand Stack    │
                                      │  iload→iadd      │
                                      │  → [3]           │
                                      └──────────────────┘
                                          │ ireturn
                                          ↓
main Frame                            (compute Frame pop)
┌──────────────────┐
│ Operand Stack    │
│  [3]             │  ← compute 반환값이 caller Operand로
│ Local Var        │
│  slot[2] = 3     │  ← istore_2
└──────────────────┘
```

**핵심**: 인자는 **caller Operand → callee Local Var**, 반환값은 **callee Operand → caller Operand**로 자동 이동. 이게 invokestatic/ireturn 같은 bytecode 명령의 의미론.

이 호출은 Heap도 Metaspace도 안 건드림. JVM Stack 안에서 전부 처리 → 가장 빠른 코드 경로.

### 3.7 실행 추적 — JNI 호출 (Native Method Stack 진입)

```
println(user)
  ↓ JVM Stack에 Frame push
PrintStream.println
  ↓
BufferedWriter.write
  ↓
FileOutputStream.writeBytes  ← ★ 여기서 native 메서드
  ↓ JNI 진입
[Native Method Stack 영역]
JNI stub Frame push (Java↔Native 전환, 예외 체크)
  ↓
C Frame: Java_java_io_FileOutputStream_writeBytes push
  ↓
write(2) syscall → OS 커널
```

**이 순간부터 PC Register는 undefined** — bytecode가 아닌 native instruction 실행 중.
**같은 OS thread stack에 C Frame이 Java Frame 위에 자연스럽게 쌓임**.

### 3.8 HotSpot 내부 구현

**JavaThread 객체** (`src/hotspot/share/runtime/javaThread.hpp`):

```cpp
class JavaThread : public Thread {
private:
  address          _stack_base;       // OS thread stack의 base
  size_t           _stack_size;       // 크기
  frame            _last_Java_frame;  // 현재 top frame
  address          _saved_exception_pc;
  JNIHandleBlock*  _active_handles;
  JavaThreadState  _thread_state;
  OSThread*        _osthread;         // 대응하는 OS thread
};
```

**Frame 객체** (`src/hotspot/share/runtime/frame.hpp`):

```cpp
class frame {
private:
  intptr_t* _sp;       // Stack Pointer
  address   _pc;       // Program Counter
  intptr_t* _fp;       // Frame Pointer (이전 Frame의 base)
public:
  Method*   interpreter_frame_method() const;
  jint      interpreter_frame_bci() const;       // bytecode index
  intptr_t* interpreter_frame_local_at(int index) const;
  intptr_t* interpreter_frame_expression_stack() const;  // operand stack
};
```

→ HotSpot은 한 Frame을 `sp + fp + pc` 세 포인터로 본다. JavaThread가 들고 있는 정보로 모든 스레드별 데이터에 접근.

**스레드 생성 시 stack 할당** (`os_linux.cpp`):

```cpp
bool os::create_thread(...) {
  pthread_attr_setstacksize(&attr, stack_size);  // -Xss 또는 OS 기본
  int ret = pthread_create(&tid, &attr, thread_native_entry, thread);
  if (ret != 0) return false;  // → OOM: unable to create new native thread
  return true;
}
```

**Stack overflow 감지**: HotSpot은 stack 끝 부근에 **guard page**를 두고, 거기까지 자라면 OS가 SEGV → signal handler가 SOE로 변환. (Safepoint polling page와 같은 mprotect 패턴.)

---

## 4. 가지 ④: 운영 — 시니어 진단

### 4.1 핵심 질문

> "실무에서 stack 관련 문제를 만나면 어떻게 진단하고 해결하나요?"

### 4.2 키워드 1 — `-Xss` 트레이드오프

#### 잠깐, "메모리 footprint"가 뭔가요

"footprint"는 직역하면 발자국. **이 녀석이 RAM에서 차지하는 자리의 크기**를 뜻한다. RSS(프로세스 전체)와의 관계:

| 용어 | 범위 |
|---|---|
| **RSS** | JVM 프로세스 **전체** 메모리 footprint (OS가 측정) |
| **Thread footprint** | 스레드 영역만의 footprint = `-Xss × 스레드 수` |
| **Heap footprint** | Java Heap만의 footprint = `-Xmx` 한도 |

`-Xss`가 직접 영향 주는 건 **Thread footprint**. 구체적 계산:

| -Xss | 500 스레드 시 Thread footprint |
|---|---|
| 256KB | 500 × 256KB = **128MB** |
| 1MB (기본) | 500 × 1MB = **500MB** |
| 4MB | 500 × 4MB = **2GB** |

→ 같은 500 스레드라도 `-Xss` 값에 따라 footprint가 16배 차이. footprint가 작아야 좋은 이유: container limit 안 넘김 / 더 많은 스레드 가능 / swap 회피 / 다른 영역(Heap·Code Cache)에 메모리 양보.

#### 트레이드오프 표

| `-Xss` 작게 (256KB) | `-Xss` 크게 (4MB) |
|---|---|
| 스레드 더 많이 만들 수 있음 | 스레드 적게 |
| 깊은 재귀에서 SOE | 깊은 재귀 견딤 |
| Thread footprint 작음 (500 × 256KB = 128MB) | Thread footprint 큼 (500 × 4MB = 2GB) |
| JIT inlined frame이 크면 위험 | 안전 |

**경험칙**:
- 일반 웹 서버: 기본 (512KB~1MB)
- 깊은 재귀 알고리즘: 2~4MB
- 스레드 수 매우 많이 필요: 256~512KB. **단, virtual thread 고려가 더 나음**.

### 4.3 키워드 2 — SOE vs OOM-thread (가장 자주 혼동되는 에러 쌍)

| 에러 | 의미 | 원인 | 진단 |
|---|---|---|---|
| `StackOverflowError` | **한 스레드의 stack 깊이가 -Xss 초과** | 무한 재귀, 너무 깊은 호출 체인 | stack trace에서 같은 메서드 반복 패턴 |
| `OOM: unable to create new native thread` | **새 OS thread 생성 실패** | OS thread 수 한계, 메모리 부족 | `ulimit -u`, `/proc/sys/kernel/threads-max`, 현재 thread 수 |

**SOE를 catch하면 안전한가?**
- `Error`이지만 catch는 가능. 단:
  1. catch 시점에 stack은 거의 다 찬 상태 → catch 안에서 또 메서드 호출 시 다시 SOE.
  2. 무한 재귀 원인이면 catch해도 해결 안 됨 — 원인 수정 필요.
  3. JVM 상태 손상 가능성.
- 권장: catch 말고 코드 수정. recursive → iterative.

### 4.4 키워드 3 — 진단 도구

#### jstack — 스레드 dump

```bash
jstack <pid>           # 전체 thread dump
jstack -l <pid>        # owned synchronizer 포함 (lock 분석)
```

**출력 예시**:
```
"http-nio-8080-exec-3" #45 daemon prio=5 tid=0x... nid=0x4a23 waiting on condition
   java.lang.Thread.State: WAITING (parking)
        at jdk.internal.misc.Unsafe.park(Native Method)
        - parking to wait for <0x...> (a ReentrantLock$NonfairSync)
        ...
```

**핵심 필드**: 이름 / `#N` JVM ID / `daemon` 여부 / `tid` Java thread id / `nid` OS thread id (`/proc/<pid>/task`와 매칭) / `Thread.State`.

**Thread.State 5종**:

| State | 의미 | 흔한 원인 |
|---|---|---|
| `NEW` | start() 안 됨 | 코드 결함 |
| `RUNNABLE` | 실행 중/가능 | 정상 |
| `BLOCKED` | synchronized lock 대기 | lock contention |
| `WAITING` | wait/park/join | I/O blocking, lock 대기 |
| `TIMED_WAITING` | sleep, wait(timeout) | 의도적 대기 |
| `TERMINATED` | 종료 | 정상 |

#### 데드락 자동 감지

```bash
jstack <pid> | grep -A 5 'Found one Java-level deadlock'
```

JVM이 자동 감지해서 dump에 표시. "Thread-1이 잡은 lock을 Thread-2가 기다리고, 반대도 마찬가지" 패턴.

#### NMT (Native Memory Tracking) — Thread 영역 측정

```bash
java -XX:NativeMemoryTracking=summary -jar app.jar
jcmd <pid> VM.native_memory summary

# 출력 일부:
#   Thread (reserved=521MB, committed=521MB)
#         (thread #500)
#         (stack: reserved=520MB, committed=520MB)
```

→ 500 스레드 × 약 1MB = 520MB. RSS의 큰 부분이 여기서 옴.

#### 스레드 수 측정

```bash
jcmd <pid> Thread.print | grep -c '^"'   # JVM 레벨
ls /proc/<pid>/task | wc -l               # OS 레벨 (Linux)
```

#### JFR 이벤트

```bash
jcmd <pid> JFR.start name=threads duration=60s settings=profile filename=threads.jfr
```

**핵심 이벤트**:
- `jdk.JavaThreadStatistics` — 스레드 수 추세
- `jdk.ThreadStart` / `jdk.ThreadEnd`
- `jdk.VirtualThreadStart` / `jdk.VirtualThreadEnd` (JDK 21+)
- `jdk.VirtualThreadPinned`
- `jdk.VirtualThreadSubmitFailed`

### 4.5 운영 시나리오 매트릭스

| 증상 | 진단 명령 | 원인 |
|---|---|---|
| `StackOverflowError` | stack trace 본문 | 무한 재귀 또는 깊이 너무 큼 |
| `OOM: unable to create new native thread` | `ulimit -u`, `/proc/sys/kernel/pid_max` | OS thread 한계 |
| RSS는 큰데 Heap은 작음 | `jcmd VM.native_memory summary` | 스레드 수 폭증 |
| jstack에 `BLOCKED` 많음 | `jstack -l` | lock contention |
| Virtual Thread 도입 후 처리량 ↓ | `-Djdk.tracePinnedThreads=full` | pinning |
| 데드락 의심 | `jstack` | JVM이 자동 감지 |

### 4.6 Killer 시나리오 — "RSS 5GB인데 -Xmx는 2GB"

> **단계적 진단 절차**:
>
> 1. **NMT 활성화**:
>    ```
>    java -XX:NativeMemoryTracking=summary -jar app.jar
>    jcmd <pid> VM.native_memory summary
>    ```
>
> 2. **각 영역 committed 합계 확인** (일반 분포):
>    - Java Heap: 2GB (Xmx 그대로)
>    - Metaspace + Compressed Class Space: 200~400MB
>    - **Thread**: 스레드 수 × 1MB (이게 핵심) — 500 스레드면 500MB
>    - Code Cache: 240MB reserve, 실제는 컴파일된 코드량
>    - GC 자료구조 (Card Table, Mark Bitmap): Heap의 1.5%
>    - Direct Memory: NIO 사용량
>    - Internal: 100~200MB
>
> 3. **Thread 영역이 의외로 크면**:
>    - `jcmd <pid> Thread.print | grep -c '^"'` — 현재 thread 수
>    - 수백~수천이면 thread pool 폭증 의심
>    - 스레드 이름 패턴으로 누가 만들었는지 식별 (Netty, Tomcat, ForkJoinPool, app)
>
> 4. **해결**:
>    - Thread pool 크기 제한
>    - Virtual Thread로 마이그레이션 (I/O bound라면)
>    - `-Xss` 축소 (256~512KB) — SOE 위험 균형
>    - 컨테이너 limit 재조정

**Container OOM-killed인데 Heap dump 정상** → Heap 외 영역 합이 limit 초과. 의심 순서: Thread → Metaspace → Code Cache → Direct Memory → JNI native lib (NMT가 못 봄).

---

## 5. 가지 ⑤: 진화 — Green → Native → Virtual

### 5.1 핵심 질문

> "JVM의 스레드 모델은 어떻게 변해왔고, Virtual Thread는 왜 도입되었나요?"

### 5.2 키워드 1 — Green Thread → Native Thread (1996 → 1998)

| 시기 | 모델 | 특성 | 한계 |
|---|---|---|---|
| **JDK 1.0 (1996)** | Green Thread (M:1 user-level) | JVM이 직접 스케줄링, OS 스레드 1개로 시뮬레이션 | 멀티코어 활용 불가 |
| **JDK 1.2+ (1998)** | Native Thread (1:1) | OS thread 1:1, OS가 스케줄링 | 무겁고 비싸서 수만 개 못 만듦 |

전환의 의미: 멀티코어 활용을 얻은 대가로 "스레드는 비싼 자원"이라는 제약이 생김.

### 5.3 키워드 2 — Virtual Thread (JDK 21+)

**도입 동기**: 2010년대 마이크로서비스 시대 — 서버가 수만 개 동시 connection을 다뤄야 함.
- 1:1 thread × 수만 = 수십 GB stack → 불가능.
- 기존 대안: NIO + CompletableFuture 비동기 코드 → "colored function" 문제. 동기 코드와 async 코드 스타일이 다름.
- Virtual Thread의 약속: **평범한 synchronous 코드를 쓰면서 수십만 thread** — colorless async.

#### 잠깐, NIO와 Colored function이 뭔가요

**NIO (New I/O, JDK 1.4 / 2002)** = `Selector` + `epoll`/`kqueue` 기반의 non-blocking I/O. 한 thread가 수천 connection을 모니터링하면서 데이터 준비된 channel만 처리.

```java
// 전통 blocking I/O — 1 connection = 1 thread (무거움)
InputStream in = socket.getInputStream();
int b = in.read();   // 데이터 올 때까지 thread 잠듦

// NIO — 1 thread가 수천 channel 모니터링
selector.select();
for (SelectionKey key : selector.selectedKeys()) {
    if (key.isReadable()) handleRead(key);   // 준비된 것만
}
```

→ 메모리 절약은 했는데 **코드 스타일이 바뀜**. 그래서 `CompletableFuture`로 async 체인을 짜기 시작:

```java
// 동기 스타일 (전통)                       // 비동기 스타일 (NIO + CompletableFuture)
User u = fetchUser(id);                    fetchUser(id)
List<Order> os = fetchOrders(u.id);          .thenCompose(u -> fetchOrders(u.id))
int total = calculateTotal(os);              .thenApply(os -> calculateTotal(os))
respond(total);                              .thenAccept(t -> respond(t))
                                             .exceptionally(ex -> { log(ex); return null; });
```

**Colored function 문제** (Bob Nystrom, 2015):

> "함수에는 두 색깔이 있다 — **빨강(async)** 과 **파랑(일반)**. 빨강 함수는 빨강 컨텍스트에서만 호출 가능. 한 번 빨강 시작하면 caller 트리 전체가 빨강 됨 — 전염병처럼."

| 증상 | 설명 |
|---|---|
| **전염성** | `fetchUser`가 CompletableFuture 리턴 → caller 모두가 CompletableFuture 리턴해야 |
| **라이브러리 2배** | sync/async 버전 둘 다 필요 (ReactiveMongoTemplate vs MongoTemplate) |
| **디버깅 지옥** | stack trace가 ForkJoinPool worker에서 끝남 — 누가 호출했는지 추적 불가 |
| **try/catch 깨짐** | 예외 전파가 별도 메커니즘 (`exceptionally`) |
| **호환 불가** | 빨강 → 파랑 호출 시 `.get()` 써야 하는데, 그러면 다시 blocking |

→ **"비동기 코드는 좋은데, 그걸 평범하게 짜고 싶다"** 가 Virtual Thread의 출발점.

#### Virtual Thread는 어떻게 sync 코드로 수십만 thread를 가능케 했나

핵심 트릭: **"sync처럼 보이는 코드를 JVM이 자동으로 async로 변환한다."**

```java
// 사용자가 쓴 코드 (sync 스타일, 변경 0)
String response = httpClient.send(request);   // 평범한 blocking 호출

// JVM이 내부적으로 하는 일:
//  1. send 안에서 socket.read() 호출
//  2. read 안에서 "데이터 없네" → 그 자리에서 freeze (continuation)
//  3. carrier thread가 다른 virtual thread 픽업
//  4. epoll로 모니터링하던 socket에 데이터 도착
//  5. 이 virtual thread를 carrier에 unfreeze
//  6. read가 결과 리턴 → 사용자 코드 다음 줄로
```

이게 가능했던 이유: **JEP 444가 JDK 내부 구현 (`java.net.Socket`, `FileInputStream`, `HttpClient` 등)을 NIO 기반으로 다시 작성**. 사용자 API는 1996년부터 그대로지만, 안쪽이 바뀌어서 virtual thread 위에서 자동 yield 됨.

→ 사용자 입장: "왜 같은 코드인데 갑자기 수십만 thread가 가능?" — 답: "JDK가 NIO로 다시 짜졌다, 너 모르는 사이에."

**구조**:

```
Platform Thread (전통):                  Virtual Thread (JDK 21+):
━━━━━━━━━━━━━━━━━━━                     ━━━━━━━━━━━━━━━━━━━━

OS 스레드 1:1                            M개 virtual : N개 carrier(OS)

각 스레드:                                각 carrier:
  └── JVM Stack (1MB, 미리 할당)           └── JVM Stack (carrier 자기 것)

                                          각 virtual thread:
                                          └── Stack Chunk (★ Heap에 저장)
                                              ├── Frame들
                                              ├── 가변 크기 (실제 깊이만큼)
                                              └── 일반 객체처럼 GC 대상
```

**왜 stack을 Heap에?**
- 100,000 vthread × 1MB = 100GB → 불가능. Heap chunk로 옮기면:
- 실제 깊이만큼만 메모리 사용 (sparse 안 함).
- park/unpark 시 chunk를 carrier로 옮기거나 다시 Heap으로 보내는 게 빠름.
- GC와 통합 — vthread unreachable이면 stack도 회수.

### 5.4 Continuation 메커니즘 (freeze / unfreeze)

```
Virtual Thread T가 socket.read() 등 blocking 호출
        │
        ▼
JDK 21+ I/O 코드가 "이건 block될 작업"이라 인식
        │
        ▼
T의 현재 stack을 stack chunk로 freeze → Heap 저장
        │
        ▼
Carrier thread는 다른 virtual thread 실행 (lock-free 스케줄링)
        │
        ▼
I/O 준비 완료 → 이벤트 발생
        │
        ▼
스케줄러가 T를 carrier에 unfreeze → carrier JVM Stack에 chunk 복원
        │
        ▼
T가 socket.read() 다음 줄부터 재개
```

T 입장에서는 그냥 함수 호출 한 번 — 그 동안 carrier가 다른 일을 한 게 투명. 이게 **continuation**.

HotSpot 구현 (`continuation.cpp`):
```cpp
// Freeze
for (frame f = thread->last_frame(); ...; f = f.sender()) {
  copy_frame_to_chunk(f, chunk);   // Heap의 StackChunk 객체에 복사
}
// Thaw
for (each frame in chunk) {
  push_frame_to_stack(frame, thread);  // carrier stack에 복원
}
```

Stack chunk = `jdk.internal.vm.StackChunk` Klass의 인스턴스 = 일반 Java 객체.

#### Carrier Thread 정의

**Carrier thread = virtual thread를 실제로 실행하는 platform thread (OS thread)**. Virtual thread는 자체 OS thread가 없으므로 누군가가 실행해줘야 한다.

```
Platform Threads (OS thread, carrier 역할)
  ForkJoinPool worker pool
  기본 size = CPU 코어 수 (예: 8개)
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Carrier #1   Carrier #2   ...   Carrier #8

Virtual Threads (수십만 개, Heap에 stack chunk로 보관)
  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  vthread#1, vthread#2, ..., vthread#500000

스케줄링 흐름:
  carrier가 idle → ForkJoinPool에서 runnable vthread 1개 픽업
  → carrier의 OS stack에 vthread의 stack chunk를 thaw(복원)
  → carrier가 그 vthread 실행
  → 그 vthread가 blocking call 만나면 freeze → Heap으로 빠짐
  → carrier는 다음 vthread 픽업
```

→ **소수의 carrier(예: 8개)가 수십만 vthread를 시간 분할로 돌린다**. vthread의 stack은 평소 Heap에 누워 있다가, 실행 차례가 되면 carrier의 OS stack 위에 잠깐 펼쳐졌다가, blocking 만나면 다시 Heap으로 돌아감.

#### Stack Chunk와 Freeze의 정확한 의미

Stack chunk는 metaphor가 아니라 **진짜 Java 객체**. `jmap`으로 Heap dump 뜨면 `StackChunk` 인스턴스가 보인다.

```java
// jdk.internal.vm.StackChunk (JDK 21+)
class StackChunk {
    // 안에 frame들이 LIFO 순서로 저장됨
    // 각 frame = Local Var Array + Operand Stack + Frame Data
    // 일반 객체와 동일하게 Heap에 살고 GC 대상
}
```

**Freeze = carrier OS stack의 frame들을 통째로 Heap chunk로 복사하고 OS stack은 비우는 작업**:

```
[Freeze 직전 — carrier OS stack]            [Freeze 후 — Heap에 StackChunk]
┌──────────────────┐                       Heap:
│ Frame: read()    │ ← blocking 결정          StackChunk@0x...:
├──────────────────┤                           [Frame: read()]
│ Frame: send()    │     freeze              [Frame: send()]
├──────────────────┤   ─────────→            [Frame: handler()]
│ Frame: handler() │                          [Frame: vthread entry]
├──────────────────┤
│ Frame: vthread   │                       carrier OS stack: (영역 비워짐)
│  entry           │                       → carrier가 다른 vthread 픽업 가능
└──────────────────┘
```

상태가 동결된 vthread = **"parked"** 상태. 누가 깨워주기 전까지 가만히 있음.

**Unfreeze (Thaw) = Heap chunk → carrier stack 복원**. I/O 이벤트 발생 시 scheduler가 vthread를 runnable 큐에 넣음 → carrier가 픽업 → StackChunk의 frame들을 carrier OS stack 위에 다시 쌓음 → PC를 `read()` return 지점으로 설정 → `read()`가 결과 들고 리턴.

→ vthread 입장에서는 **그냥 `read()` 한 줄이 오래 걸린 것처럼 보임**. carrier 갈아탄 것도 모름.

#### 정말 장점만 있나 — Virtual Thread의 단점들

| | Platform Thread | Virtual Thread | 누가 유리 |
|---|---|---|---|
| 생성 비용 | ~수 ms | ~수 us | Virtual |
| 메모리/개 | 1MB (-Xss) | 수 KB | Virtual |
| 최대 개수 | ~수천 | 수십만~수백만 | Virtual |
| Context switch | OS (~수 us) | JVM (~수 ns) | Virtual |
| I/O blocking | thread 점유 | 자동 yield | Virtual |
| **CPU-bound** | ★ 전용 thread | carrier 점유 → 다른 vthread block | **Platform** |
| **synchronized** | 정상 | Pinning (5.5 참조) | **Platform** |
| **JNI native call** | 정상 | Pinning | **Platform** |
| **ThreadLocal** | 적음 (수천 × 슬롯) | 폭발 (수십만 × 슬롯) | **Platform** |
| **Heap 압박** | 없음 (stack은 OS) | StackChunk가 Heap 차지 → GC 부담 | **Platform** |
| **디버깅** | 익숙한 도구 | profiler 호환성 부족 | **Platform** |

**핵심 단점 정리**:

1. **CPU-bound 작업엔 부적합**: vthread가 CPU 계속 쓰면 carrier가 그 동안 다른 vthread 못 픽업 → 동시성 의미 없음. CPU 작업은 별도 platform pool로 위임.
2. **ThreadLocal 메모리 폭발**: 100,000 vthread × ThreadLocal 슬롯 = 거대한 메모리. JDK 21+는 대안으로 **ScopedValue** (JEP 446) 제공.
3. **Heap 압박**: vthread가 많을수록 StackChunk가 많아짐 → GC 대상 증가. -Xmx 설계 다시 해야.
4. **Pinning** (다음 섹션).
5. **관측 도구**: 기존 profiler가 수십만 vthread를 다 그리지 못함. JFR 같은 신형 도구 필요.

→ **만능 아님**. I/O-bound 작업에서만 진가 발휘.

### 5.5 키워드 3 — Pinning (Virtual Thread의 한계)

```
Virtual Thread T가 synchronized 진입
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
carrier도 같이 block → 다른 vthread 실행 불가
        │
        ▼
처리량 ↓ — virtual thread의 이점 상실
```

**트리거**:
- `synchronized` 메서드/블록 (JDK 21~23)
- JNI native 호출 중
- ★ JDK 24+ ([JEP 491](https://openjdk.org/jeps/491)) synchronized pinning 제거 예정

#### 왜 synchronized가 pinning을 일으키나 (메커니즘)

```java
synchronized (obj) {
    socket.read();   // blocking I/O
}
```

JVM 레벨에서 일어나는 일:

```
synchronized (obj) 진입
  ↓
JVM bytecode: monitorenter
  ↓
HotSpot 내부: obj.ObjectMonitor 획득
  ObjectMonitor (C++ struct in JVM):
    owner = "현재 OS thread ID"   ← ★ 여기가 문제
```

`ObjectMonitor`는 HotSpot의 C++ 구조체로, **OS thread ID를 owner로 기록**. JDK 21 시점 구현은 carrier thread ID를 박아둠.

만약 vthread를 freeze하면:
```
freeze 시도
  ↓
"이 vthread는 ObjectMonitor의 owner임"
  ↓
freeze하면 carrier가 다른 vthread를 픽업할 텐데...
  ↓
다른 vthread가 같은 obj에 synchronized 진입 시도 →
  ObjectMonitor.owner = carrier ID인데, 새 vthread도 같은 carrier에서 →
  "이미 나야!" 잘못된 동시 진입
  ↓
lock 정합성 깨짐 → JVM이 freeze 자체를 금지 → "pinned"
```

→ **synchronized의 owner 추적이 OS thread 단위라서**, vthread를 carrier에서 떼면 lock의 일관성이 깨진다. 그래서 JVM이 안전을 위해 freeze 자체를 금지.

JNI native call도 비슷: C 코드는 continuation 메커니즘을 모르고, C stack frame을 HotSpot이 freeze할 수 없음 → pinned.

#### 왜 문제인가 — 시나리오

```
시나리오: 8개 carrier, 10,000 vthread,
         모든 vthread가 synchronized 블록 안에서 DB 호출

vthread #1 → carrier #1 점유 + synchronized → DB blocking → carrier #1 잠듦
vthread #2 → carrier #2 점유 + synchronized → DB blocking → carrier #2 잠듦
...
vthread #8 → carrier #8 점유 + synchronized → DB blocking → carrier #8 잠듦

결과:
  - 모든 carrier가 잠듦 (vthread 떼어낼 수 없음)
  - runnable vthread 9992개가 모두 대기
  - 처리량 = 8개/초 (carrier 수와 같음)
  - virtual thread의 이점 완전 상실
```

극단적으로는 새 vthread를 시작도 못함 — carrier가 다 점유돼서.

#### 해결책 — ReentrantLock은 왜 안 pinning되나

`synchronized` 대신 `ReentrantLock` 사용:

```java
ReentrantLock lock = new ReentrantLock();
lock.lock();
try {
    socket.read();
} finally {
    lock.unlock();
}
```

**ReentrantLock은 순수 Java로 구현**. JVM의 `monitorenter` bytecode를 안 씀. 내부적으로 `AbstractQueuedSynchronizer` (AQS) + `LockSupport.park()` 사용.

```
ReentrantLock.lock() 호출
  ↓
AQS.acquire(1):
  CAS로 state(int) 변경 시도
    성공: owner = Thread.currentThread()   ← ★ vthread 객체 자체를 기록
    실패: queue에 대기 + LockSupport.park()
                          ↓
                    ★ park()가 핵심
                          ↓
              LockSupport.park()는 Virtual Thread 인식:
                - vthread면 → continuation yield (freeze!)
                - platform thread면 → OS-level park (futex)
                          ↓
              vthread는 Heap chunk로 freeze
              carrier는 다른 vthread 픽업 가능
```

**핵심 차이 — Owner 추적 방식**:

| | synchronized | ReentrantLock |
|---|---|---|
| Owner 추적 | OS thread ID (carrier ID) | **Thread 객체 자체** (vthread 객체) |
| Lock 메커니즘 | JVM 내부 `ObjectMonitor` (C++) | Java AQS + `LockSupport.park()` |
| park() 동작 | (synchronized는 park 안 씀) | Virtual Thread 인식 → freeze 가능 |
| Freeze 가능? | ❌ owner 정합성 깨짐 | ✅ owner가 vthread 객체라 carrier 무관 |

**정확히 왜 동작하나**:

ReentrantLock의 owner는 `Thread.currentThread()` 객체. Virtual Thread도 `Thread` 클래스의 인스턴스 (`Thread.ofVirtual().start(...)`)이므로:

```
vthread T1이 lock 획득 → owner = T1 (vthread 객체)
T1이 freeze → Heap chunk로 이동, owner = T1 그대로
carrier는 다른 vthread T2 픽업
T2가 같은 lock 시도 → owner(T1) ≠ currentThread(T2) → 정상적으로 대기
```

→ **owner가 vthread 객체이기 때문에 carrier 갈아타도 무관**. freeze 안전.

또한 `LockSupport.park()`가 Virtual Thread 인식 코드를 내장하고 있어, ReentrantLock뿐 아니라 **AQS 기반 모든 동기화 도구** (Semaphore, CountDownLatch, BlockingQueue 등)가 같은 혜택을 받음.

→ Virtual Thread 환경에서 `synchronized → ReentrantLock` 마이그레이션이 기본 권고. JDK 24+ ([JEP 491](https://openjdk.org/jeps/491))이 synchronized의 owner를 vthread 객체로 바꿔 pinning 자체를 제거할 예정이지만, 그전까지는 ReentrantLock이 안전책.

#### 진단
```bash
java -Djdk.tracePinnedThreads=full -jar app.jar

# 출력에 <== monitors:1 같은 표식이 보이면 pinning
```

또는 JFR `jdk.VirtualThreadPinned` 이벤트.

### 5.6 Platform vs Virtual Thread 선택

| | Platform Thread | Virtual Thread |
|---|---|---|
| OS 스레드 매핑 | 1:1 | M:N (carrier 공유) |
| Stack 위치 | OS thread stack | Heap의 stack chunk |
| Stack 크기 | -Xss 고정 (1MB) | 동적, 사용한 만큼 |
| 최대 생성 수 | ~수천 | 수십만~수백만 |
| 생성 비용 | ~수 ms (OS syscall) | ~수 us (Heap object) |
| Context switch | OS 영역 (~수 us) | JVM 영역 (~수 ns) |
| Blocking I/O 친화 | 나쁨 (thread 점유) | 좋음 (자동 freeze) |
| CPU-bound | 좋음 | 보통 (다른 vthread 차단) |
| synchronized | 정상 | pinning (JDK 24 해결 예상) |
| native call | 정상 | pinning |

**선택 가이드**:
- I/O bound (DB, HTTP) + 동기 코드 → **Virtual Thread**
- CPU bound → **Platform Thread (제한된 수)**
- 둘 다 → hybrid (CPU 작업만 platform pool로 위임)

### 5.7 역사 타임라인

| 연도 | 릴리스 | 변화 |
|---|---|---|
| 1996 | JDK 1.0 | Green Thread (M:1) |
| 1998 | JDK 1.2 | **Native Thread (1:1)** |
| 2002 | JDK 1.4 | NIO + Selector |
| 2014 | JDK 8 | CompletableFuture |
| 2018 | Loom 프로젝트 시작 | — |
| 2022 | JDK 19 (preview) | **Virtual Thread (preview)** |
| 2023 | JDK 21 (LTS) | **Virtual Thread stable** ([JEP 444](https://openjdk.org/jeps/444)) |
| 2024 | JDK 23 | Pinning 일부 해소 |
| 2025 | JDK 24 (예상) | synchronized pinning 제거 ([JEP 491](https://openjdk.org/jeps/491)) |

---

## 6. 면접 답변 워크플로우

### 6.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "JVM의 메모리 영역 설명해보세요" | ② WHAT | ① WHY로 분리 이유 |
| "스레드마다 따로 있는 메모리는?" | ② WHAT | ① WHY |
| "Stack Frame 안에 뭐가 있나요?" | ③ HOW | ② WHAT으로 위치 확인 |
| "max_locals/max_stack이 뭔가요?" | ③ HOW | ClassFile 연결 |
| "왜 stack-based VM인가요?" | ③ HOW (Operand Stack) | ⑤ 진화 (호환성) |
| "SOE랑 OOM-thread 차이?" | ④ 운영 | ③ HOW (stack 깊이) |
| "RSS가 큰 이유 진단" | ④ 운영 (Killer) | ② WHAT (per-thread × N) |
| "Virtual Thread 왜 쓰나요?" | ⑤ 진화 | ④ 운영 (pinning 진단) |
| "synchronized vs ReentrantLock in vthread" | ⑤ Pinning | ④ 진단 |

### 6.2 답변 템플릿

> **루트 문장 한 줄 → 해당 가지 키워드 3개 순서대로 → 듣는 사람 표정 보고 인접 가지로**

예: "Stack Frame 안에 뭐가 있나요?"

> "JVM Stack은 per-thread LIFO 메모리고, 그 안에 메서드 호출마다 Frame이 push됩니다. (← 루트)
> Frame 내부는 3영역으로 나뉩니다.
> 첫째, **Local Variable Array** — 파라미터와 지역 변수를 슬롯 단위로 저장합니다. 크기는 ClassFile의 max_locals.
> 둘째, **Operand Stack** — bytecode 실행 중 push/pop으로 쓰는 임시 계산 공간. 깊이는 max_stack.
> 셋째, **Frame Data** — Constant Pool 참조, return PC, 이전 Frame 포인터.
> max_stack과 max_locals는 javac가 미리 계산해서 ClassFile에 박아두기 때문에 JVM이 Frame을 한 번에 정확한 크기로 할당합니다. 이게 stack frame allocation이 빠른 이유입니다."

→ 면접관이 "long 변수는?" 물으면 ③의 슬롯 디테일로, "stack-based인 이유?"면 ③의 Operand Stack 깊이로.

---

## 7. 꼬리질문 트리 (가지별)

### Q1 [가지 ②]. JVM의 메모리 영역 중 per-thread 인 것은?

> 3가지: JVM Stack, PC Register, Native Method Stack. 스레드 생성 시 OS가 할당, 종료 시 반환. Heap, Metaspace, Code Cache는 shared.

**🪝 Q1-1: JVM Stack과 OS thread stack은 같은 건가요?**
> 논리적으론 다르지만 HotSpot 구현에서는 같은 OS thread stack에 통합됨. JVM Stack(Java frame)과 Native Method Stack(JNI frame)이 같은 stack에 자연스럽게 쌓임. 경계는 논리적.

**🪝🪝 Q1-1-1: 그럼 `-Xss`는?**
> OS thread stack 전체 크기. JVM frame + Native frame이 함께 쓰는 영역. 기본 512KB~1MB.

### Q2 [가지 ③]. Stack Frame 안에는 무엇이 있고, 크기 결정은?

> 3가지 영역: Local Variable Array (max_locals), Operand Stack (max_stack), Frame Data (CP ref, return PC, prev FP). max_stack/max_locals는 javac가 미리 계산해서 ClassFile Code attribute에 저장 → JVM이 한 번에 정확한 크기로 할당.

**🪝 Q2-1: long을 로컬 변수로 쓰면?**
> long/double은 64비트 → Local Variable Array에서 2 슬롯 차지. slot[N]에 long 저장하면 slot[N+1]은 사용 불가. Operand Stack에서도 마찬가지. javac가 max_locals 계산 시 long/double을 2로 카운트.

### Q3 [가지 ④]. `StackOverflowError`와 `OOM: unable to create new native thread` 차이?

> SOE = 한 스레드의 stack 깊이가 -Xss 초과 (무한 재귀, 너무 깊은 호출). OOM-thread = 새 OS thread 생성 실패 (시스템 thread 수 한계, 메모리 부족). 진단: SOE는 stack trace 본문, OOM-thread는 `ulimit -u`와 현재 thread 수.

**🪝 Q3-1: SOE를 catch하면 안전한가?**
> Error지만 catch 가능. 단 catch 시점에 stack이 거의 다 차 있어서 catch 안에서 또 호출 시 다시 SOE. 무한 재귀가 원인이면 catch해도 의미 없음. 권장: catch 말고 코드 수정 (recursive → iterative).

### Q4 [가지 ②]. PC Register가 native 메서드 실행 중 undefined인 이유는?

> Java 메서드의 PC = bytecode offset. Native 메서드는 C/C++ → bytecode 없음, native instruction 직접 실행. 그동안 PC Register는 의미 있는 값을 가질 수 없음. Native return 후 caller의 다음 bytecode를 다시 가리킴.

### Q5 [가지 ⑤]. Virtual Thread와 Platform Thread의 가장 큰 차이?

> Stack 위치 + 스케줄링 주체. Platform = OS 1:1, stack은 OS thread stack 1MB, 스케줄링은 OS. Virtual = M:N, stack은 Heap의 stack chunk(가변), 스케줄링은 JVM. 결과: 수십만 vthread 가능, blocking 시 자동 freeze.

**🪝 Q5-1: Stack chunk가 Heap에 있다는 의미는?**
> Virtual thread가 freeze되면 frame들이 `jdk.internal.vm.StackChunk` 객체로 Heap에 저장. 일반 객체와 동일하게 GC 대상. 깊이만큼만 사용 (sparse 아님).

**🪝🪝 Q5-1-1: vthread 많아지면 Heap 부족해지나?**
> Yes. 그러나 platform × 1MB와 비교하면 훨씬 작음 (평균 수 KB). Heap dump에서 `StackChunk` 인스턴스 수로 진단.

### Q6 [가지 ⑤]. Virtual Thread Pinning이 무엇이고, 언제 발생?

> Pinning = vthread가 carrier에 묶여 freeze 불가. 트리거: synchronized (JDK 21~23), JNI native 호출. Pinning 중 blocking 호출이 나면 carrier도 block → 다른 vthread 실행 불가 → 처리량 저하. 해결: synchronized → ReentrantLock. JDK 24+ JEP 491에서 synchronized pinning 제거 예정.

**🪝 Q6-1: Pinning 진단은?**
> `-Djdk.tracePinnedThreads=full` 옵션 또는 JFR `jdk.VirtualThreadPinned` 이벤트. 출력의 `<== monitors:1` 패턴.

### Q7 (Killer) [가지 ④]. RSS 5GB인데 -Xmx 2GB. 나머지 3GB 진단?

> 단계:
> 1. NMT 활성화 (`-XX:NativeMemoryTracking=summary`, `jcmd VM.native_memory summary`)
> 2. 영역별 committed 확인: Heap 2GB / Metaspace 200~400MB / **Thread = 스레드수 × 1MB** / Code Cache 240MB / GC bookkeeping (Heap의 1.5%) / Direct Memory / Internal
> 3. Thread가 크면: `jcmd Thread.print | grep -c '^"'`로 수 확인, 이름 패턴으로 누가 만들었는지 식별
> 4. 해결: pool 크기 제한, Virtual Thread 마이그레이션, -Xss 축소, container limit 조정

**🪝 Q7-1: Container OOM-killed인데 Heap dump 정상이면?**
> Heap 외 영역 합이 limit 초과. NMT로 영역별 committed 합산. 의심 순서: Thread → Metaspace (CL 누수) → Code Cache → Direct Memory → JNI native lib (NMT가 못 봄). Container limit의 50~70%로 -Xmx 조정.

---

## 8. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 이내로 그릴 수 있다 (루트 + 5가지 + 각 키워드 3개)
- [ ] 가지 ① WHY: per-thread인 본질적 이유 3가지를 말한다 (LIFO 본성, 격리, Heap반대 수명)
- [ ] 가지 ② WHAT: 3종 세트와 "물리적으론 stack 1개" 통합 그림을 그린다
- [ ] 가지 ③ HOW: Frame 3영역을 그리고 max_locals/max_stack의 의미를 설명한다
- [ ] 가지 ③ HOW: compute(1,2) 실행 추적을 Operand Stack push/pop으로 그린다
- [ ] 가지 ③ HOW: JNI 호출이 같은 OS stack에 C frame 쌓는 그림을 그린다
- [ ] 가지 ④ 운영: -Xss 트레이드오프 표를 적고 SOE vs OOM-thread를 구분한다
- [ ] 가지 ④ 운영: RSS 5GB 진단 절차 4단계를 말한다
- [ ] 가지 ⑤ 진화: Green → Native → Virtual의 전환 동기를 말한다
- [ ] 가지 ⑤ 진화: Continuation freeze/unfreeze 흐름과 Pinning을 설명한다
- [ ] 7장 꼬리질문 7개에 막힘없이 답한다

---

## 다음 단계

- → [04. Code Cache](./04-code-cache.md): JIT 결과 native code 저장소
- → [05. Direct Memory](./05-direct-memory.md): Off-heap NIO
- → [06. GC bookkeeping](./06-gc-bookkeeping-and-others.md): Card Table, RSet, Mark Bitmap
- ← [02. Metaspace & Class Space](./02-metaspace-and-class-space.md): Class 메타데이터
- ← [01. Heap & TLAB](./01-heap-and-tlab.md): Heap의 세대 구조

## 참고

- **JVMS §2.5.2 (Java Virtual Machine Stacks)**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-2.html#jvms-2.5.2
- **JEP 444 Virtual Threads**: https://openjdk.org/jeps/444
- **JEP 491 (preview) Synchronize Virtual Threads without Pinning**: https://openjdk.org/jeps/491
- **HotSpot `frame.hpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/frame.hpp
- **HotSpot `javaThread.hpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/javaThread.hpp
- **HotSpot `continuation.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/continuation.cpp
- **Oracle — Virtual Threads guide**: https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
- **Ron Pressler — Loom presentation**: JavaOne 2018+, Devoxx 시리즈
