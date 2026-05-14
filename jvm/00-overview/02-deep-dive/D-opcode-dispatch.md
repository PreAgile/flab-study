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
