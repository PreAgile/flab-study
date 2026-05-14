# 부록 A — 인터프리터 구현 4가지 방식

> **본문**: [02. 컴파일 흐름 — §2 직관](../02-class-compilation-flow.md#-2단계-직관)에서 "HotSpot은 Template Interpreter 변형을 쓴다"고만 적었다. 여기선 그 한 줄을 풀어 — **"인터프리터"라는 단어 하나가 가리는 4가지 구현 방식**을 본다.

---

## 인터프리터 구현 스펙트럼 — 4가지 방식

### (1) Switch-based Interpreter — 가장 순진한 방식

```c
while (true) {
    uint8_t opcode = *pc++;
    switch (opcode) {
        case ICONST_0: push(0); break;
        case ICONST_1: push(1); break;
        case IADD: { int b=pop(), a=pop(); push(a+b); } break;
        // ... 200여 개 case
    }
}
```

- C/C++의 `switch` 문 하나에 모든 bytecode를 case로 나열.
- **문제**: 매 bytecode마다 점프 테이블을 거치고, CPU의 **branch predictor가 다음 opcode를 예측 못 함** (인덱스가 매번 다름) → indirect branch misprediction이 거의 항상 발생.
- 1996년 Classic VM이 이 방식. **C++ 대비 20~50배 느렸던 이유**.

### (2) Direct-Threaded Interpreter — 살짝 진화

각 opcode 핸들러의 주소를 테이블에 저장하고, 각 핸들러 끝에서 다음 opcode 주소로 직접 점프 (`goto *next_handler`). GCC 확장 `&&label`을 쓴다. switch보다 빠르지만, 표준 C는 아님. **CPython 3.11+, Lua가 이 방식**.

> 더 깊은 설명(switch가 왜 느리고 threaded가 왜 빠른가, branch predictor 학습 메커니즘)은 [부록 D — opcode 디스패치](./D-opcode-dispatch.md)에.

### (3) Template Interpreter — HotSpot의 방식 ★

이게 핵심이다. **"인터프리터지만 사실상 매우 단순한 JIT"**.

```
JVM 시작 시:
1. CPU 아키텍처 감지 (x86_64인지 aarch64인지)
2. 각 bytecode opcode에 대해 "이 opcode에 해당하는 어셈블리 시퀀스"를 생성
3. 생성된 어셈블리를 메모리에 배치 (이게 진짜 인터프리터의 실체)
4. 각 어셈블리 끝에는 "다음 bytecode 위치 계산 → 그 핸들러로 점프" 코드 자동 추가

실행 시:
- bytecode를 만나면 → 해당 opcode의 generated assembly로 jump
- switch도, 함수 호출도 없음. 그냥 직접 점프.
```

**예시**: `iadd` opcode를 만나면 HotSpot은 미리 생성해둔 어셈블리로 점프:

```asm
pop     rax              ; operand stack에서 두번째 값
add     [rsp], eax       ; 첫번째 값과 더해서 stack top에 저장
movzbl  eax, [r13+1]     ; 다음 bytecode opcode 읽기
inc     r13              ; pc 증가
jmp     [r14 + rax*8]    ; 다음 opcode의 generated assembly로 점프
```

즉, **HotSpot 인터프리터는 부팅 시점에 자기 자신을 어셈블리로 컴파일한다**. 그래서 `templateInterpreter.cpp`가 그렇게 길고 이상한 매크로(`__`)를 쓴다.

**왜 이렇게 만들었나**:
- 일반 C++ switch보다 2~3배 빠름.
- JIT 컴파일된 코드와 **calling convention이 동일** → 인터프리터 ↔ JIT 코드 전환이 매끄러움 (OSR, Deopt이 가능한 결정적 이유).
- Register 사용도 직접 제어 가능 → operand stack pointer를 register에 고정 (x86_64에선 `rsp`/`r13` 등).

### (4) AST + Self-optimizing — Truffle (GraalVM)

이건 완전히 다른 발상. **AST 자체를 IR로 평생 들고 다니면서 직접 인터프리트하고, 핫한 서브트리는 통째로 JIT**한다. bytecode 단계가 아예 없다.

> 자세한 건 [부록 B — JVM 구현체](./B-jvm-implementations.md)의 GraalVM Truffle 절과 [부록 C — AST](./C-ast.md)의 "Truffle이 AST를 직접 JIT한다" 절에.

---

## "어셈블리·미리 generate·점프 테이블·매우 단순한 JIT" — 4개 단어 풀이

위 (3) Template Interpreter 설명에 등장한 4개 단어를 한 호흡에 풀어본다.

### 1. 어셈블리(Assembly) — "CPU가 직접 실행하는 기계어를 사람이 읽기 쉽게 쓴 것"

#### 기계어와 어셈블리의 관계

CPU가 진짜로 이해하는 건 **기계어(machine code) = 0과 1의 시퀀스**.

```
기계어 (x86_64):        01 D8         ← 진짜 CPU가 보는 것 (2바이트)
어셈블리:               add eax, ebx  ← 사람이 보는 표현
의미:                   eax = eax + ebx  (두 register를 더해라)
```

**같은 명령을 두 표기로 쓴 것**. 어셈블러(`as`, `nasm`)가 어셈블리 → 기계어로 1:1 변환. CPU 모델마다(x86, ARM, RISC-V, ...) 명령어 집합이 다르므로 어셈블리도 다르다.

#### 자바 세계의 4층 구조

| 층 | 예시 | 누가 실행/이해 |
|---|---|---|
| Java 소스 | `int c = a + b;` | 사람·javac |
| **Bytecode** | `iload_1 iload_2 iadd istore_3` | **JVM** |
| **어셈블리** | `mov eax, [rbp-4]` `add eax, [rbp-8]` ... | **CPU (변환 후)** |
| 기계어 | `8B 45 FC 03 45 F8 ...` | **CPU 직접** |

- **Bytecode는 가상 CPU의 명령어**. JVM이 해석해야 실행됨. 플랫폼 독립.
- **어셈블리/기계어는 실제 CPU의 명령어**. 직접 실행 가능. 플랫폼 종속.

x86_64 어셈블리는 ARM Mac에서 못 돈다. 그래서 자바가 bytecode 층을 두고 "한 번 컴파일, 어디서나 실행"을 가능하게 한 것.

---

### 2. "미리 generate"는 왜 하나 — 부팅 시점에 어셈블리를 만드는 이유

#### 두 가지 인터프리터 만드는 방식 비교

**방법 A — C 코드로 작성된 인터프리터** (Switch / Direct-Threaded)

```c
// JVM 빌드 시점에 이미 컴파일된 상태
while (true) {
    uint8_t op = *pc++;
    switch (op) {
        case IADD: { int b=pop(), a=pop(); push(a+b); } break;
        ...
    }
}
```

→ JVM **빌드할 때** C 컴파일러가 이걸 어셈블리로 변환. **JVM 바이너리는 자기 자신의 어셈블리만 들고 다님**. 부팅 시점에 아무것도 generate 안 함.

**방법 B — HotSpot Template Interpreter**

```cpp
// JVM 부팅 시점에 호출됨
void TemplateInterpreterGenerator::generate_all() {
  for (각 opcode) {
    이 opcode를 처리하는 어셈블리 시퀀스를 메모리에 생성;
  }
}
```

→ **JVM이 부팅하면서 자기가 쓸 인터프리터의 어셈블리를 그 자리에서 만든다**.

#### 왜 이렇게 하나 — 세 가지 이유

**(1) C 컴파일러가 만든 어셈블리가 충분히 최적이 아니라서**

- C 컴파일러는 범용. 인터프리터처럼 **"한 줄 처리 후 다음 opcode로 분산 점프"** 라는 특수 패턴에 최적화 못 함
- register 배치, branch 배치, calling convention을 **인터프리터 전용으로 손수 설계**하고 싶다
- 결과: C로 짠 인터프리터보다 **2~3배 빠름**

**(2) CPU 아키텍처별 코드를 한 소스로 관리하기 위해**

- HotSpot은 x86_64, aarch64, ppc, s390 등을 지원
- 각 아키텍처마다 어셈블리가 완전히 다름
- **부팅 시점에 "이 CPU가 뭐냐"를 보고 거기 맞는 어셈블리를 generate** → 하나의 소스로 여러 아키텍처 대응

**(3) JIT과 calling convention을 통일하기 위해**

- 인터프리터 ↔ JIT 코드 사이를 매끄럽게 점프하려면 둘이 **같은 register 규약, 같은 스택 레이아웃**을 써야 함
- C 컴파일러는 이걸 강제 못 함. 어셈블리를 직접 generate하면 강제 가능
- 결과: **deoptimization** (JIT 코드 → 인터프리터로 돌아가기) 이 가능해짐

> 비유: C 컴파일러가 만든 인터프리터 = 기성품 양복. Template Interpreter = 맞춤 양복. 맞춤이라 비쌀 것 같지만, **한 번만 만들어두면 평생 입는다** (부팅 시 한 번, 그 후엔 고정).

---

### 3. 점프 테이블(Jump Table) — "배열의 인덱스로 점프할 곳을 결정"

#### 일반 분기 vs 점프 테이블

**일반 if-else** (200개 비교):
```c
if (op == 0x1B) handle_iload_1();
else if (op == 0x1C) handle_iload_2();
else if (op == 0x60) handle_iadd();
... (200번 비교)
```

→ 최악 200번 비교. 평균 100번.

**점프 테이블** (O(1)):
```c
void* table[256] = {
    [0x1B] = &&handle_iload_1,   // opcode 0x1B의 처리 코드 주소
    [0x1C] = &&handle_iload_2,
    [0x60] = &&handle_iadd,
    ...
};

goto *table[opcode];   // 단 한 번의 메모리 로드 + 점프
```

→ **O(1)**. opcode가 곧 인덱스.

#### 그림으로 보면

```
점프 테이블 (256개 슬롯의 배열):
┌──────────────────────────────────────────┐
│ index 0x00:  →  handle_nop의 어셈블리    │ ─┐
│ index 0x01:  →  handle_aconst_null의 ... │  │
│ ...                                       │  │  메모리의
│ index 0x1B:  →  handle_iload_1의 어셈블리│  ├─ 어딘가에
│ index 0x1C:  →  handle_iload_2의 어셈블리│  │  있는
│ ...                                       │  │  어셈블리
│ index 0x60:  →  handle_iadd의 어셈블리   │  │  코드들
│ ...                                       │  │  (부팅 시
│ index 0xFF:  →  ...                       │ ─┘  generate됨)
└──────────────────────────────────────────┘
         ↑
  opcode를 이 배열의 인덱스로 사용
```

bytecode 실행 = "다음 opcode 읽기 → 테이블에서 주소 가져오기 → 그 주소로 점프" 무한 반복.

#### HotSpot의 실제 어셈블리

```asm
; iadd 처리 어셈블리 (단순화)
pop    rax                    ; 스택에서 b를 register로
add    [rsp], eax             ; 스택 top(a)에 더함
movzbl eax, byte [r13+1]      ; 다음 bytecode opcode 읽기
inc    r13                    ; pc 1 증가
jmp    [r14 + rax*8]          ; ← 여기가 점프 테이블 사용 지점
                              ;   r14 = 테이블 base, rax = opcode
```

마지막 `jmp [r14 + rax*8]` 한 줄이 "다음 opcode의 핸들러로 점프". **매 핸들러 끝에 이 패턴이 반복**됨.

> 핵심: opcode가 **1바이트(0~255 범위)인 것**과 **256-entry 점프 테이블의 인덱스**가 정확히 맞물려 설계됐다. opcode 디자인 자체가 점프 테이블 디스패치를 전제.

---

### 4. 왜 "매우 단순한 JIT"이라 부르나 — 진짜 JIT은 뭐가 복잡한가

Template Interpreter도 **결국 부팅 시점에 어셈블리를 동적 생성**한다. 이건 JIT의 정의(런타임에 코드 생성)에 부분적으로 해당. 그래서 "사실상 매우 단순한 JIT"이라고 표현한 것.

하지만 진짜 JIT(C1/C2)과는 차이가 크다:

| 항목 | Template Interpreter | C1 JIT | C2 JIT |
|---|---|---|---|
| **언제 generate?** | JVM 부팅 시 **1회** | 메서드가 hot해진 시점 (매번) | 더 hot해진 시점 (매번) |
| **무엇을 generate?** | 각 opcode의 핸들러 (200개) | 한 메서드 전체의 native code | 한 메서드 + inlined 메서드들 |
| **최적화** | 거의 없음 (정해진 템플릿) | constant folding, null 제거, 간단한 devirt | inline, EA, vectorization, loop unrolling, GVN, ... |
| **컴파일 시간** | 부팅 시 수 ms | 메서드당 1~10 ms | 메서드당 10~수백 ms |
| **결과물 크기** | 메서드 크기와 무관 (고정) | bytecode의 3~5배 | bytecode의 10~30배 (inline 때문) |
| **프로파일 활용?** | ❌ (실측 데이터 안 봄) | △ (수집은 하지만 활용 적음) | ✅ (MethodData를 적극 활용) |
| **deopt 가능?** | N/A | ✅ | ✅ |

#### "복잡한 JIT"이 정확히 뭘 하는지 — C2 예시

```java
int sumSquares(int n) {
    int s = 0;
    for (int i = 0; i < n; i++) s += i * i;
    return s;
}
```

C2가 hot 판정 후 만드는 어셈블리:

```asm
; Loop unrolling 4배 + SIMD 벡터화 후
vpmulld  ymm0, ymm1, ymm1    ; 8개 정수 제곱을 한 번에
vpaddd   ymm2, ymm2, ymm0    ; 8개 합산을 한 번에
add      eax, 32
cmp      eax, ecx
jl       loop
...
vphaddd  ymm2, ymm2, ymm2    ; horizontal add로 8개 합 → 1개
vextracti128 xmm3, ymm2, 1
...
```

이런 코드를 만들려면 **수십 가지 최적화 패스**가 돌아야 한다 (Sea of Nodes IR 생성 → GVN → loop opt → EA → vectorization → register allocation → scheduling → emit). **이게 "복잡한 JIT"의 의미**.

Template Interpreter는 그냥 `iload`, `iload`, `iadd` 핸들러를 차례로 점프하면서 매번 메모리 접근. SIMD는커녕 register 할당도 매번 새로.

---

## 한 줄 정리

- **어셈블리**: CPU가 직접 실행하는 기계어의 사람-친화 표현. 플랫폼 종속
- **미리 generate**: 부팅 시 어셈블리를 메모리에 만들어두기. C 컴파일러 한계 회피 + 멀티 아키텍처 + JIT과 calling convention 통일
- **점프 테이블**: opcode(0~255)를 인덱스로 핸들러 주소를 찾는 256-entry 배열. O(1) 디스패치
- **"매우 단순한 JIT"**: 부팅 시 어셈블리를 generate한다는 점에서만 JIT스럽다. 실측 프로파일도, inline도, EA도 없다. 진짜 JIT(C1/C2)은 메서드 단위로 매번 generate하고 수십 가지 최적화를 한다

---

## 한 줄 요약

- **인터프리터에도 여러 구현 방식이 있다** (switch / threaded / template / AST)
- **HotSpot은 Template Interpreter**: 부팅 시 각 opcode를 어셈블리로 미리 generate해서 그걸 점프 테이블처럼 쓴다. 사실상 매우 단순한 JIT.
- "Template Interpreter 변형"이라는 표현을 쓰는 이유: HotSpot의 구체적 구현 — `TemplateTable` 클래스, `MacroAssembler` 매크로, 부팅 시 `generate_all()` — 은 HotSpot 고유이므로 그렇게 한정.

---

## 관련 부록

- [부록 B — JVM 구현체 비교](./B-jvm-implementations.md): HotSpot/OpenJDK/GraalVM/OpenJ9/Azul/ART의 인터프리터·JIT 차이
- [부록 C — AST 자료구조](./C-ast.md): Truffle이 AST를 IR로 쓰는 (4) 방식의 본격 설명
- [부록 D — opcode 디스패치 메커니즘](./D-opcode-dispatch.md): switch가 느린 이유와 threaded가 빠른 이유의 본격 분석 (branch predictor 학습)
