# 부록 D — opcode 디스패치 메커니즘 (핸들러 테이블 + 직접 점프)

> **본문**: [02. 컴파일 흐름 — Stage 4 Interpreter](../02-class-compilation-flow.md#stage-4--interpreter-첫-실행은-한-줄씩-해석)에서 "Template Interpreter가 디스패치를 시작한다"고만 적었다. 여기선 **opcode가 정확히 뭐고, 왜 핸들러 주소 테이블을 만들어 직접 점프하는지** — 인터프리터의 hot loop가 어떻게 작동하는지 — 본다.

---

## 1. opcode란 무엇인가

> **opcode = "operation code"의 줄임말**. CPU나 가상 머신이 이해하는 **기본 명령어 단위**의 식별자.

JVM 바이트코드에서 한 명령은 보통:
- **1바이트 opcode** (0~255 중 하나의 숫자)
- **0~여러 바이트의 operand** (피연산자, 명령에 따라 가변)

예를 들어 `iconst_1` 명령은 **1바이트짜리 숫자 `0x04`** 한 개로 표현된다. 사람이 읽기 좋게 `iconst_1`이라는 이름을 붙였을 뿐, JVM이 보는 건 숫자 하나.

### JVM의 200여 개 opcode (대표적인 것들)

| 16진수 | 이름 | 동작 |
|---|---|---|
| `0x01` | `aconst_null` | null을 operand stack에 push |
| `0x03` | `iconst_0` | int 0을 stack에 push |
| `0x04` | `iconst_1` | int 1을 stack에 push |
| `0x1B` | `iload_1` | 지역변수 1번을 stack에 push |
| `0x3E` | `istore_3` | stack top을 지역변수 3번에 저장 |
| `0x60` | `iadd` | int 두 개 pop → 더해서 push |
| `0x99` | `ifeq` | stack top이 0이면 분기 |
| `0xB6` | `invokevirtual` | 가상 메서드 호출 |
| `0xB8` | `invokestatic` | static 메서드 호출 |
| `0xBA` | `invokedynamic` | 동적 메서드 호출 (JDK 7+) |
| `0xBB` | `new` | 객체 할당 |

### `.class` 파일에 실제로 들어있는 모습

```java
int c = a + b;
```

이 한 줄이 `.class` 파일에선 정확히 이런 4바이트로 들어간다:

```
1B 1C 60 3E
```

각 바이트의 의미:
- `0x1B` → `iload_1` (a를 push)
- `0x1C` → `iload_2` (b를 push)
- `0x60` → `iadd` (더하기)
- `0x3E` → `istore_3` (c에 저장)

`javap -c`가 보여주는 `iload_1` 같은 이름은 **사람을 위한 디스어셈블리 결과**일 뿐, 디스크에는 숫자 한 바이트로 저장돼 있다.

### 왜 1바이트인가

- **컴팩트함**: `.class` 파일이 작아짐 → 메모리/디스크/네트워크 효율
- **빠른 디스패치**: 1바이트면 0~255 → 256-entry 점프 테이블의 **인덱스로 바로 사용 가능**
- **단순한 디코딩**: 한 바이트만 읽으면 명령 종류가 결정됨

255개로 부족하지 않나? JVM은 현재 약 200여 개 opcode 사용. 여유 있음. 추가 인자 확장이 필요하면 `wide` opcode (`0xC4`) — "다음 명령의 인자를 2바이트로 확장"이라는 prefix가 있다.

> 📌 정리: **opcode = "이 1바이트가 어떤 동작을 의미하는가"를 식별하는 숫자**. JVM 인터프리터의 출발점은 매번 "이 바이트가 어느 opcode야?"를 묻는 것이다.

---

## 2. 핸들러 주소 테이블 — 왜 만들고, 왜 직접 점프하나

### 출발점: Switch 문은 왜 느린가?

가장 단순한 구현:

```c
while (true) {
    uint8_t opcode = *pc++;
    switch (opcode) {
        case 0x1B: /* iload_1 */ push(local[1]); break;
        case 0x1C: /* iload_2 */ push(local[2]); break;
        case 0x60: /* iadd */ { int b=pop(), a=pop(); push(a+b); } break;
        // ... 200여 개 case
    }
}
```

컴파일러는 보통 이걸 **점프 테이블**로 최적화한다:

```asm
jump_table:
    .quad case_iload_1     ; opcode 0x1B에 대응하는 코드 주소
    .quad case_iload_2     ; opcode 0x1C에 대응하는 코드 주소
    .quad case_iadd        ; opcode 0x60에 대응하는 코드 주소
    ...

main_loop:                  ; ← 모든 case가 여기로 돌아옴
    movzx eax, byte [pc]
    inc   pc
    jmp   [jump_table + rax*8]   ; ← 단 하나의 디스패치 지점

case_iload_1:
    push local[1]
    jmp main_loop           ; ← 다시 디스패치 지점으로

case_iload_2:
    push local[2]
    jmp main_loop           ; ← 또 다시 디스패치 지점으로

case_iadd:
    ...
    jmp main_loop           ; ← 항상 같은 곳으로 복귀
```

**문제**: 모든 디스패치가 `main_loop`의 단 한 줄 `jmp [jump_table + rax*8]`에서 일어난다.

이 한 줄은 매번 `rax` 값에 따라 다른 곳으로 점프한다 (indirect branch). CPU 입장에서:
- **branch predictor가 학습 못 함**: "여기선 다음에 어디로 갈까?"를 묻는데, 입력 패턴이 사실상 random
- → 거의 항상 **branch misprediction**
- → 파이프라인이 잘못된 명령을 prefetch했다가 버림 (수 사이클 손실)

200줄짜리 메서드 실행하면 200번 다 misprediction → 인터프리터가 느려지는 진짜 이유.

### 해결: 디스패치를 "분산"시킨다 — Direct-Threaded

> **핵심 아이디어**: 디스패치 지점을 한 곳에 모으지 말고, **각 핸들러 끝에 따로따로** 두자.

```c
// 각 라벨의 주소를 담은 테이블 (GCC 확장)
static void* handler_table[256] = {
    [0x1B] = &&handle_iload_1,    // && 는 라벨 주소를 얻는 GCC 문법
    [0x1C] = &&handle_iload_2,
    [0x60] = &&handle_iadd,
    // ...
};

// 시작: 첫 opcode를 읽고 그 핸들러로 점프
goto *handler_table[*pc++];

handle_iload_1:
    push(local[1]);
    goto *handler_table[*pc++];   // ← 이 핸들러 전용 디스패치 지점

handle_iload_2:
    push(local[2]);
    goto *handler_table[*pc++];   // ← 또 다른 디스패치 지점

handle_iadd:
    int b = pop(), a = pop();
    push(a + b);
    goto *handler_table[*pc++];   // ← 여기도 자기만의 디스패치 지점
```

이제 디스패치가 **200개 핸들러에 200개 분산**된다.

### 왜 이게 빠른가 — branch predictor의 학습

CPU의 indirect branch predictor는 **각 점프 명령마다 별도의 학습 기록**을 가진다.

- **Switch**: 디스패치 지점 = 1개 → 1개의 학습 기록에 200개 opcode 시퀀스를 다 우겨넣으려고 함 → 패턴 분간 못함
- **Direct-Threaded**: 디스패치 지점 = 200개 → 각 핸들러가 자기만의 학습 기록을 가짐

자바 코드의 실제 분포:
```
iload + iload + iadd + istore + iload + iload + iadd + istore + ...
```

이런 패턴이 흔하다. Direct-Threaded에선 `iload_1` 핸들러 끝의 디스패치 지점이 **"내 다음엔 iload_2가 자주 와"** 를 학습한다. Predictor 적중률이 급격히 올라감.

> 측정 결과: Direct-Threaded는 일반적으로 Switch보다 **20~50% 빠름**. Python 3.11이 이 방식으로 바꿔서 평균 25% 빨라진 이유.

### 왜 "주소 테이블"인가 — opcode를 인덱스로 쓰기 위해

핵심 질문: **opcode 값 `0x1B`를 받았을 때 어떻게 `handle_iload_1`로 가나?**

답: **opcode가 곧 테이블의 인덱스**. `handler_table[0x1B]`이 곧 `&&handle_iload_1`을 담고 있다.

```
opcode = 0x1B  →  handler_table[0x1B]  →  &&handle_iload_1 (주소)  →  jmp 그 주소
```

- 배열 인덱싱은 **O(1) 메모리 접근 한 번** — 사실상 register 연산 한두 개로 끝
- if-else 체인이면 O(N), 평균 N/2번 비교 — 200개면 100번 비교
- 점프 테이블이면 1번의 메모리 로드 + 1번의 점프

→ **opcode가 1바이트이고 0~255 범위인 것**과 **256-entry 테이블의 인덱스**가 정확히 맞물려서 설계됐다.

### 왜 "직접 점프(goto)"인가 — 함수 호출 비용 회피

대안 1: 핸들러를 함수로 만들기

```c
void handle_iload_1(VM* vm) { vm->push(vm->local[1]); }

while (true) {
    handler_funcs[*pc++](vm);   // 함수 포인터 호출
}
```

이 경우 매 핸들러마다 발생하는 비용:
- 함수 호출 prologue (스택 프레임 생성, callee-saved register 저장)
- 인자 전달 (calling convention)
- 핸들러 본문
- 함수 호출 epilogue (register 복원, 스택 정리)
- `ret` 명령
- 다시 루프로 돌아와 디스패치

대안 2: `goto *...`로 직접 점프

- 그냥 `jmp` 명령 한 번
- 함수 호출 prologue/epilogue **없음**
- 모든 핸들러가 **같은 함수 안에 있음** → 컴파일러가 operand stack pointer, frame pointer 같은 핵심 변수를 **register에 고정 배치 가능**
- 함수 호출이면 그 register들을 매번 save/restore 해야 함

→ goto 방식이 **함수 호출 비용 + register 트래픽 둘 다 0**.

---

## 3. HotSpot Template Interpreter는 이걸 한 단계 더 — 어셈블리 직접 생성

위에서 본 Direct-Threaded도 결국 C로 작성한 인터프리터다. 핸들러 **본문은 C 컴파일러가 만든 어셈블리**.

HotSpot은 거기서 한 발 더 나간다:
- C 코드를 거치지 않고
- **부팅 시점에 어셈블리를 직접 generate**
- 각 opcode별로 가장 효율적인 native instruction sequence를 손수 설계
- `r13` (bytecode pointer), `r14` (handler table base), `rsp` (operand stack) 같은 register를 **강제로 고정 배치**
- C 컴파일러가 절대 못 만드는 calling convention을 만들어서 JIT 코드와 호환되게 함

결과: C로 짠 인터프리터(Direct-Threaded 포함)보다 또 **2~3배 빠름**. 이게 HotSpot이 "Template Interpreter"라는 별도 카테고리로 분류되는 이유.

아래는 위 다섯 줄을 풀어쓴 것 — "왜 그래야만 했는지"에 대한 깊은 설명이다.

### 3.1 왜 특정 레지스터에 "고정"하는가

JVM 인터프리터의 hot loop는 매 opcode마다 **세 가지를 미친 듯이 반복**한다.

```
1. bytecode pointer 에서 다음 opcode 1바이트 읽기
2. handler table[opcode] 로 핸들러 주소 가져오기
3. operand stack 에 push / pop
```

이 세 가지에 쓰이는 변수가 매번 메모리에서 로드/저장되면:
- L1 cache hit여도 ~4 사이클
- 200줄 메서드 = 600번의 불필요한 메모리 접근

→ **이 변수들을 영구히 register에 박아두면** 메모리 접근 0번, register-to-register 연산만으로 디스패치 완료. opcode 1개 처리가 ~5 사이클까지 떨어진다.

HotSpot x86-64 인터프리터의 약속:

| 레지스터 | 용도 |
|---|---|
| `r13` | bytecode pointer (현재 명령 위치) |
| `r14` | handler table base |
| `rsp` | operand stack top |
| `rbp` | local variable base |

이 약속이 **인터프리터 전체에서 절대 깨지지 않아야** 빠르게 돌아간다.

### 3.2 C++ 인터프리터가 왜 문제였나

초기 자바가 느렸던 진짜 이유. C++로 switch 기반 인터프리터를 짜면:

```cpp
void interpret(Method* m) {
    while (true) {
        switch (*pc++) {
            case 0x60: { int b = pop(); int a = pop(); push(a+b); break; }
            // ...
        }
    }
}
```

C++ 컴파일러가 만드는 코드의 한계:
- **register allocation을 컴파일러가 결정** → `pc`, operand stack top이 매번 메모리에 spill됨
- **함수 호출이 끼면 callee-saved register가 매번 save/restore**
- **단일 switch 디스패치 지점** → branch misprediction 폭발 (이전 2절에서 본 문제)
- **GC가 stack을 스캔할 때 oop(object pointer) 위치를 컴파일러가 결정** → JVM이 통제 못함

결과: native C 코드 대비 10~50배 느림. 자바 "느린 언어" 평판의 근원.

### 3.3 그래서 왜 HotSpot은 Template Interpreter를 골랐나

위 문제들을 **다 해결하려면 결국 컴파일러를 우회해야** 한다. 즉:
- register를 강제 고정하고
- frame layout을 직접 통제하고
- calling convention을 자체 정의하고
- 각 opcode마다 가장 짧은 instruction sequence를 손으로 선택

이걸 가능하게 하는 유일한 방법이 **opcode 핸들러를 어셈블리 템플릿으로 미리 짜놓고, JVM 부팅 시 그걸 native code로 메모리에 emit**하는 것. 이게 Template Interpreter.

C++ switch 인터프리터 대비 **2~3배 빠름**.

### 3.4 Calling convention — 뭐고 왜 맞춰야 하나

**Calling convention = "함수를 호출할 때 인자를 어디에 넣고, 반환값을 어디로 받고, 어떤 register를 누가 보존할 책임인지"에 대한 약속.**

표준(System V x86-64 ABI):
- 인자 1~6번 → `rdi, rsi, rdx, rcx, r8, r9`
- 반환값 → `rax`
- callee-saved → `rbx, rbp, r12~r15`

#### JVM에서 왜 자체 convention이 필요한가

한 메서드 호출이 일어날 때, **호출자와 피호출자가 서로 다른 형태로 실행되고 있을 수 있다**:

```
                          Method A 호출 가능한 형태들
                         ┌──────────────────────────────────────────┐
Method A (인터프리터)    │ → Method B (인터프리터)                  │
Method A (C1 JIT 컴파일) │ → Method B (C2 JIT 컴파일)               │
Method A (C2 JIT 컴파일) │ → Method B (인터프리터, 아직 컴파일 안됨)│
                         └──────────────────────────────────────────┘
```

이게 가능하려면 **인터프리터든 JIT든 동일한 calling convention을 따라야** 한다. 만약 인터프리터는 "인자를 stack에 넣고 호출", JIT는 "인자가 `rdi`에 있다고 기대"하면 → 잘못된 값 읽고 crash.

또 표준 ABI로는 부족한 JVM 고유 요구:
- **oop(object reference) 위치를 GC에게 알려야 함** → frame 안 특정 슬롯이 oop인지 컴파일러가 모름
- **deoptimization**: JIT 코드 실행 중 가정이 깨지면 인터프리터로 "되돌아갈" 수 있어야 함 → frame layout 호환
- **safepoint poll**: 모든 메서드가 GC 시작 신호를 받을 수 있어야 함

→ 표준 ABI로는 이 셋 다 안 됨. **자체 convention 필요**.

### 3.5 C 컴파일러로는 왜 불가능한가

| 요구사항 | C 컴파일러로 가능한가 |
|---|---|
| register 영구 고정 (`r13` = bytecode ptr) | 불가 (GCC `register` 키워드 무시됨) |
| 함수 prologue/epilogue 제거 | 불가 (자동 생성, 끌 수 없음) |
| 자체 calling convention | 불가 (ABI 고정) |
| frame layout 통제 (oop 위치 명시) | 불가 (컴파일러가 결정) |
| opcode마다 최적 instruction sequence 선택 | 불가 (컴파일러 휴리스틱 따름) |
| GC barrier / safepoint를 정확한 지점에 삽입 | 불가 (매크로/intrinsic 수준 한계) |

C에 `asm()` 인라인 어셈블리가 있긴 하지만, 그건 함수 안의 일부분일 뿐 — 함수 경계를 넘어가는 순간 컴파일러가 register 보존을 강제하기 때문에 **인터프리터 전체를 어셈블리로 짜야만** 위 요구를 충족할 수 있다.

### 3.6 Native code란

**CPU가 직접 실행하는 기계어**. x86-64라면 `mov`, `add`, `jmp` 같은 instruction을 바이너리로 인코딩한 바이트 sequence.

```
어셈블리:     mov rax, rbx
              ↓ 어셈블러
Native code:  48 89 D8        ← CPU가 직접 fetch / execute하는 형태
```

층위 매핑:

| 층위 | 예시 |
|---|---|
| Java source | `int c = a + b;` |
| Java bytecode (.class) | `1B 1C 60 3E` (JVM 가상 ISA) |
| **Native code** | `48 89 D8 ...` (실제 CPU ISA) |

JVM은 자바 바이트코드를 처리하기 위해 **자기 자신을 native code 덩어리로 만들어** 메모리에 띄워놓고 그걸 실행한다.
- **Template Interpreter**: JVM 부팅 시 opcode 핸들러를 native code로 generate
- **JIT(C1, C2, Graal)**: hot 메서드를 native code로 compile

### 3.7 왜 "손수" 어셈블리 템플릿으로 짜놓나

C++ 컴파일러가 만드는 code 품질이 인터프리터 hot loop에는 부족하기 때문.

예: `iadd` 핸들러를 C++로 짜면 컴파일러가 만드는 코드는 대략 15~20 instruction. 손으로 짠 템플릿은:

```asm
; r13 = bytecode pointer (영구 고정)
; rsp = operand stack
; r14 = handler table

iadd_template:
    pop  rax                  ; b
    add  [rsp], eax           ; stack top += b
    movzx eax, byte [r13+1]   ; 다음 opcode
    inc  r13
    jmp  [r14 + rax*8]        ; 다음 핸들러로 직접 점프
```

**5 instruction**. register는 절대 안 흔들리고, 함수 호출 prologue/epilogue 없음, branch predictor가 이 디스패치 지점만 학습.

→ 200여 개 opcode 각각에 대해 이런 식의 손수 짠 어셈블리 template이 HotSpot 소스에 들어있다 (`src/hotspot/cpu/x86/templateTable_x86.cpp` 같은 파일).

### 3.8 부팅 시점에 무슨 일이 일어나나 — Template Interpreter의 동작

HotSpot의 `TemplateInterpreterGenerator`가 JVM 부팅 시 실행되면서:

```
JVM 프로세스 시작
    ↓
TemplateInterpreterGenerator 실행
    ↓
for each opcode in [0x00 ... 0xFF]:
    소스에 정의된 어셈블리 template 을 읽어와
    실제 native instruction 으로 emit
    핸들러 주소를 handler_table[opcode] 에 저장
    ↓
완성된 핸들러 테이블 + native code blob 이 메모리에 상주
    ↓
.class 의 바이트코드 한 줄씩 읽으면서
opcode 를 인덱스로 핸들러 native code 로 jmp ── 인터프리트 시작
```

용어 분해:
- **Template** = 손수 짜놓은 어셈블리 조각
- **Generator** = 부팅 시 그 조각들을 native code로 emit하는 코드
- **Interpreter** = 그렇게 만든 핸들러 테이블로 바이트코드를 실행하는 엔진

이 셋을 합쳐서 **Template Interpreter**.

> 한 줄 요약: "C/C++ 컴파일러는 register 고정·자체 calling convention·GC/JIT 호환 frame layout 같은 JVM 고유 요구를 만족시킬 수 없어서, HotSpot은 opcode별 어셈블리 템플릿을 사람이 손수 작성해두고 JVM 부팅 시 그걸 native code로 emit해 인터프리터를 만든다."

> Template Interpreter 자체의 더 깊은 설명은 [부록 A — 인터프리터 구현 4가지 방식](./A-interpreter-implementations.md)의 (3)번 절에.

---

## 한 줄 요약

- **opcode** = JVM이 이해하는 명령어의 1바이트 식별자 (0x1B = iload_1, 0x60 = iadd, ...). `.class`에 실제로 들어가는 건 이 숫자 하나
- **핸들러 테이블** = `handler_table[opcode]` → 그 opcode 처리 코드의 주소. opcode가 곧 인덱스
- **직접 점프(goto)** = 함수 호출 비용 회피 + register 고정 배치 가능 + branch predictor 학습 가능

세 가지가 합쳐져서 "C++의 switch 인터프리터보다 훨씬 빠른 native-speed dispatch"가 가능해진다. HotSpot은 거기서 한 발 더 나가 어셈블리를 직접 생성한다.

---

## 관련 부록

- [부록 A — 인터프리터 구현 4가지 방식](./A-interpreter-implementations.md): Template Interpreter가 (1)~(4) 어디에 위치하는가, "미리 generate / 점프 테이블 / 매우 단순한 JIT" 개념 풀이
- [부록 C — AST 자료구조](./C-ast.md): bytecode가 1차원이 되기 전 단계인 AST
