# 부록 D — opcode 디스패치 메커니즘

> "인터프리터가 느리다"의 진짜 원인은 branch misprediction이다. `.class` 안에 들어있는 1바이트 opcode를 어떻게 핸들러로 디스패치하는가 — Switch vs Direct-Threaded vs Template Interpreter — 의 차이가 인터프리터 성능 10배 격차를 만든다.

---

## 이 문서의 사용법

본문 → [02. 컴파일 흐름](../02-class-compilation-flow.md) 가지 ③(ClassFile)·④(Interpreter)에서 진입. opcode 1바이트가 어떻게 native instruction으로 도달하는지 본격 분석.

---

## 0. 마인드맵

### 루트 한 문장 (anchor)

> **"opcode는 1바이트 명령어 식별자고, 0~255 범위는 256-entry 점프 테이블의 인덱스와 정확히 맞물려 설계됐다. 인터프리터 속도는 디스패치 지점이 1개냐(switch, branch mispred 폭발) 200개냐(threaded, 핸들러별 predictor 학습)로 결정되고, HotSpot Template Interpreter는 거기서 한 발 더 나가 register 고정 + 자체 calling convention으로 또 2~3배 빠르게 만든다."**

### 3개 가지

```
        [ROOT: opcode 디스패치 = 인터프리터 hot loop]
                    │
       ┌────────────┼────────────┐
      ① WHAT       ② HOW         ③ HotSpot
   opcode란?     테이블 + 점프    어셈블리 직접
       │             │             generate
    1바이트       Switch 느림    register 고정
    0~255         (1 mispred)    rsp/r13/r14
    .class에     Threaded 빠름  자체 calling
    숫자로       (분산 학습)     convention
                                 →GC/Deopt
```

### 가지별 핵심 키워드

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① WHAT opcode** | 1바이트 식별자 | 0~255 → 256 테이블 인덱스 | `.class`엔 숫자만, 이름은 javap용 |
| **② HOW dispatch** | Switch = 1 mispred 지점 | Direct-Threaded = 분산 학습 | 함수 호출 회피 + register 고정 |
| **③ Template** | 어셈블리 직접 generate | register 영구 고정 | Calling convention 통일 (JIT/GC/Deopt) |

---

## 1. 가지 ①: WHAT — opcode란 무엇인가

### 1.1 핵심 질문

> "`.class` 파일 안에 정확히 뭐가 들어있죠? `iadd`는 어떻게 저장돼 있나요?"

### 1.2 키워드 1 — 1바이트 명령어 식별자

**opcode = "operation code"의 줄임말**. CPU나 가상 머신이 이해하는 기본 명령어 단위의 식별자.

JVM 바이트코드에서 한 명령은:
- **1바이트 opcode** (0~255 중 하나의 숫자)
- **0~여러 바이트의 operand** (피연산자, 명령에 따라 가변)

`iconst_1`은 **1바이트짜리 숫자** 한 개로 표현된다. 사람이 읽기 좋게 이름을 붙였을 뿐, JVM이 보는 건 숫자 하나.

대표 opcode들 (외울 필요는 없고 형태만):

| 이름 | 동작 |
|---|---|
| `aconst_null` | null을 operand stack에 push |
| `iconst_0` ~ `iconst_5` | 작은 int 상수 push |
| `iload_1` ~ `iload_3` | 지역변수 N번을 stack에 push |
| `istore_1` ~ `istore_3` | stack top을 지역변수 N번에 저장 |
| `iadd` | int 두 개 pop → 더해서 push |
| `ifeq` | stack top이 0이면 분기 |
| `invokevirtual` | 가상 메서드 호출 |
| `invokestatic` | static 메서드 호출 |
| `invokedynamic` | 동적 메서드 호출 (JDK 7+) |
| `new` | 객체 할당 |

### 1.3 키워드 2 — `.class`에 실제 들어 있는 모습

```java
int c = a + b;
```

이 한 줄이 `.class`에선 정확히 4바이트로:
- `iload_1` (a를 push)
- `iload_2` (b를 push)
- `iadd` (더하기)
- `istore_3` (c에 저장)

`javap -c`가 보여주는 `iload_1` 같은 이름은 **사람을 위한 디스어셈블리 결과**일 뿐, 디스크에는 숫자 한 바이트로 저장돼 있다.

### 1.4 키워드 3 — 왜 1바이트인가

- **컴팩트함**: `.class` 작아짐 → 메모리/디스크/네트워크 효율 (90년대 모뎀 다운로드 전제).
- **빠른 디스패치**: 1바이트 = 0~255 → **256-entry 점프 테이블의 인덱스로 바로 사용 가능**.
- **단순한 디코딩**: 한 바이트만 읽으면 명령 종류가 결정됨.

255개로 부족? JVM은 약 200여 개 사용. 여유 있음. 확장이 필요하면 `wide` opcode가 prefix로 붙어 다음 명령 인자를 2바이트로 확장.

> **핵심**: opcode가 1바이트인 것과 256-entry 점프 테이블 디스패치는 **같은 설계의 양면**. 점프 테이블을 전제로 1바이트로 설계됐다.

---

## 2. 가지 ②: HOW — 핸들러 테이블 + 직접 점프

### 2.1 핵심 질문

> "왜 switch 인터프리터가 느리고, 어떻게 빠르게 만드나?"

### 2.2 키워드 1 — Switch 문은 왜 느린가

가장 단순한 구현:
```c
while (true) {
    uint8_t opcode = *pc++;
    switch (opcode) {
        case 0x1B: /* iload_1 */ push(local[1]); break;
        case 0x60: /* iadd */ { int b=pop(), a=pop(); push(a+b); } break;
        // ... 200여 개 case
    }
}
```

컴파일러는 이걸 점프 테이블로 최적화해도, 결과 어셈블리는:
```asm
main_loop:                  ; ← 모든 case가 여기로 돌아옴
    movzx eax, byte [pc]
    inc   pc
    jmp   [jump_table + rax*8]   ; ← ★ 단 하나의 디스패치 지점

case_iload_1:
    push local[1]
    jmp main_loop           ; ← 다시 한 곳으로

case_iadd:
    ...
    jmp main_loop           ; ← 항상 같은 곳으로
```

**문제**: 모든 디스패치가 `main_loop`의 단 한 줄 `jmp`에서 일어남.

이 한 줄은 매번 다른 곳으로 점프 (indirect branch). CPU 입장:
- **branch predictor가 학습 못 함** — "여기선 다음에 어디로 갈까?" 묻는데 입력 패턴이 사실상 random.
- → 거의 항상 **branch misprediction**.
- → 파이프라인이 잘못된 명령을 prefetch했다가 버림 (수 사이클 손실).

200줄 메서드 = 200번 misprediction. 이게 Classic VM이 20~50배 느렸던 진짜 이유.

### 2.3 키워드 2 — Direct-Threaded: 디스패치 지점을 분산

**핵심 아이디어**: 디스패치 지점을 한 곳에 모으지 말고, **각 핸들러 끝에 따로따로** 두자.

```c
static void* handler_table[256] = {
    [0x1B] = &&handle_iload_1,    // GCC 확장 &&label
    [0x60] = &&handle_iadd,
    // ...
};

goto *handler_table[*pc++];   // 시작

handle_iload_1:
    push(local[1]);
    goto *handler_table[*pc++];   // ← 이 핸들러 전용 디스패치 지점

handle_iadd:
    int b = pop(), a = pop();
    push(a + b);
    goto *handler_table[*pc++];   // ← 여기도 자기만의 디스패치 지점
```

이제 디스패치가 **200개 핸들러에 200개 분산**.

**왜 이게 빠른가**: CPU의 indirect branch predictor는 **각 점프 명령마다 별도의 학습 기록**을 가짐.
- Switch: 디스패치 지점 1개 → 1개의 학습 기록에 200개 opcode 시퀀스 다 우겨넣음 → 패턴 분간 못함.
- Threaded: 디스패치 지점 200개 → 각 핸들러가 자기만의 학습 기록.

자바 코드 패턴 예: `iload + iload + iadd + istore + iload + iload + iadd + istore + ...`. Threaded에서 `iload_1` 핸들러 끝의 디스패치 지점이 **"내 다음엔 iload_2가 자주 와"**를 학습 → predictor 적중률 급격히 올라감.

측정: Direct-Threaded는 Switch보다 **20~50% 빠름**. Python 3.11이 이 방식으로 바꿔서 평균 25% 빨라진 이유.

### 2.4 키워드 3 — 직접 점프(goto)가 함수 호출보다 빠른 이유

**대안: 핸들러를 함수로 만들기**
```c
void handle_iload_1(VM* vm) { vm->push(vm->local[1]); }
while (true) {
    handler_funcs[*pc++](vm);   // 함수 포인터 호출
}
```

매 핸들러마다 발생 비용:
- 함수 호출 prologue (스택 프레임, callee-saved register 저장)
- 인자 전달 (calling convention)
- 핸들러 본문
- 함수 호출 epilogue (register 복원, 스택 정리)
- `ret`
- 다시 루프로 돌아와 디스패치

**`goto *...` 직접 점프**:
- 그냥 `jmp` 한 번
- 함수 호출 prologue/epilogue **없음**
- 모든 핸들러가 같은 함수 안에 있음 → 컴파일러가 operand stack pointer, frame pointer 같은 핵심 변수를 **register에 고정 배치 가능**
- 함수 호출이면 그 register들을 매번 save/restore 해야 함

→ goto 방식이 **함수 호출 비용 + register 트래픽 둘 다 0**.

### 2.5 왜 "주소 테이블"인가

핵심: opcode `0x1B`를 받았을 때 어떻게 `handle_iload_1`로 가나? 답: **opcode가 곧 테이블의 인덱스**.

```
opcode = 0x1B  →  handler_table[0x1B]  →  &&handle_iload_1 (주소)  →  jmp 그 주소
```

- 배열 인덱싱은 O(1) 메모리 접근 한 번 — 사실상 register 연산 한두 개.
- if-else 체인은 O(N), 200개면 평균 100번 비교.
- 점프 테이블은 1번의 메모리 로드 + 1번의 점프.

→ **opcode가 1바이트(0~255)인 것**과 **256-entry 테이블의 인덱스**가 정확히 맞물려 설계됐다.

---

## 3. 가지 ③: HotSpot Template Interpreter — 한 단계 더

### 3.1 핵심 질문

> "Direct-Threaded도 C로 짠 것인데, HotSpot은 거기서 또 뭘 더 하나? 왜 어셈블리를 직접 generate해야만 했나?"

### 3.2 키워드 1 — 어셈블리 직접 generate (C 컴파일러 우회)

Direct-Threaded도 결국 C로 작성한 인터프리터. **핸들러 본문은 C 컴파일러가 만든 어셈블리**.

HotSpot은 거기서 한 발 더:
- C 코드를 거치지 않고
- **부팅 시점에 어셈블리를 직접 generate**
- 각 opcode별로 가장 효율적인 native instruction sequence를 손수 설계
- `r13` (bytecode pointer), `r14` (handler table base), `rsp` (operand stack) 같은 register를 강제로 고정 배치
- C 컴파일러가 절대 못 만드는 calling convention을 만들어서 JIT 코드와 호환되게 함

결과: C로 짠 인터프리터(Direct-Threaded 포함)보다 또 **2~3배 빠름**.

손수 짠 `iadd` 템플릿 예:
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

**5 instruction**. register는 절대 안 흔들리고, 함수 호출 prologue/epilogue 없음.

### 3.3 키워드 2 — Register를 영구 고정하는 이유

JVM 인터프리터의 hot loop가 매 opcode마다 미친 듯이 반복하는 것:
1. bytecode pointer에서 다음 opcode 1바이트 읽기
2. handler table[opcode]로 핸들러 주소 가져오기
3. operand stack에 push / pop

이 세 가지에 쓰이는 변수가 매번 메모리에서 로드/저장되면:
- L1 cache hit여도 ~4 사이클
- 200줄 메서드 = 600번의 불필요한 메모리 접근

→ 이 변수들을 영구히 register에 박아두면 메모리 접근 0번, register-to-register 연산만으로 디스패치 완료. opcode 1개 처리가 ~5 사이클까지.

HotSpot x86-64 인터프리터의 약속:

| Register | 용도 |
|---|---|
| `r13` | bytecode pointer (현재 명령 위치) |
| `r14` | handler table base |
| `rsp` | operand stack top |
| `rbp` | local variable base |

이 약속이 **인터프리터 전체에서 절대 깨지지 않아야** 빠르게 돈다. C 컴파일러는 `register` 키워드 무시하고 자기 마음대로 spill해서 강제 불가능.

### 3.4 키워드 3 — Calling convention 통일 (JIT/GC/Deopt의 비결)

**Calling convention = 함수 호출 시 인자/반환값/register 보존 책임에 대한 약속.**

표준 (System V x86-64 ABI):
- 인자 1~6번 → `rdi, rsi, rdx, rcx, r8, r9`
- 반환값 → `rax`
- callee-saved → `rbx, rbp, r12~r15`

**JVM에서 왜 자체 convention이 필요한가** — 한 메서드 호출에서 호출자와 피호출자가 서로 다른 형태로 실행될 수 있다:

```
Method A (인터프리터)    → Method B (인터프리터)
Method A (C1 JIT)        → Method B (C2 JIT)
Method A (C2 JIT)        → Method B (인터프리터, 아직 컴파일 안됨)
```

이게 가능하려면 **인터프리터든 JIT든 동일한 calling convention**을 따라야 함. 만약 인터프리터는 "인자를 stack에", JIT는 "인자가 `rdi`에"라고 기대하면 → 잘못된 값 읽고 crash.

표준 ABI로는 부족한 JVM 고유 요구:
- **oop(object reference) 위치를 GC에게 알려야** — frame 안 특정 슬롯이 oop인지 컴파일러가 모름.
- **deoptimization** — JIT 코드 실행 중 가정이 깨지면 인터프리터로 되돌아갈 수 있어야 → frame layout 호환.
- **safepoint poll** — 모든 메서드가 GC 시작 신호를 받을 수 있어야.

→ 표준 ABI로 불가능. **자체 convention 필요** → C 컴파일러 우회 필요.

### 3.5 C 컴파일러로 왜 불가능한가 (정리)

| 요구사항 | C 컴파일러로 가능? |
|---|---|
| register 영구 고정 (`r13` = bytecode ptr) | 불가 (GCC `register` 키워드 무시) |
| 함수 prologue/epilogue 제거 | 불가 (자동 생성) |
| 자체 calling convention | 불가 (ABI 고정) |
| frame layout 통제 (oop 위치 명시) | 불가 (컴파일러가 결정) |
| opcode마다 최적 instruction sequence | 불가 (컴파일러 휴리스틱) |
| GC barrier / safepoint를 정확한 지점에 | 불가 (intrinsic 한계) |

C에 `asm()` 인라인 어셈블리가 있긴 하지만, 함수 경계를 넘는 순간 컴파일러가 register 보존을 강제 → **인터프리터 전체를 어셈블리로 짜야만** 충족.

### 3.6 부팅 시점에 일어나는 일

`TemplateInterpreterGenerator`가 JVM 부팅 시:
```
JVM 프로세스 시작
    ↓
TemplateInterpreterGenerator 실행
    ↓
for each opcode in [0x00 ... 0xFF]:
    소스의 어셈블리 template을 읽어와
    실제 native instruction으로 emit
    핸들러 주소를 handler_table[opcode]에 저장
    ↓
완성된 핸들러 테이블 + native code blob이 메모리에 상주
    ↓
.class의 바이트코드 한 줄씩 읽으면서
opcode를 인덱스로 핸들러 native code로 jmp ── 인터프리트 시작
```

용어 분해:
- **Template** = 손수 짜놓은 어셈블리 조각
- **Generator** = 부팅 시 그 조각들을 native code로 emit하는 코드
- **Interpreter** = 그렇게 만든 핸들러 테이블로 바이트코드를 실행하는 엔진

이 셋을 합쳐서 **Template Interpreter**.

> 한 줄 요약: "C/C++ 컴파일러는 register 고정·자체 calling convention·GC/JIT 호환 frame layout 같은 JVM 고유 요구를 만족 못 시켜서, HotSpot은 opcode별 어셈블리 템플릿을 사람이 손수 작성해두고 JVM 부팅 시 그걸 native code로 emit해 인터프리터를 만든다."

---

## 4. 면접 답변 워크플로우

### 4.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 |
|---|---|
| "opcode가 뭔가?" | ① WHAT |
| "왜 1바이트인가?" | ① (256 테이블 인덱스) |
| "switch 인터프리터가 왜 느리나?" | ② branch mispred |
| "CPython 3.11이 왜 빨라졌나?" | ② Direct-Threaded |
| "HotSpot이 어셈블리를 직접 generate하는 이유?" | ③ Calling convention |
| "OSR/Deopt가 어떻게 가능한가?" | ③ JIT/인터프리터 ABI 통일 |

### 4.2 답변 템플릿

> "opcode 디스패치는 인터프리터 hot loop의 본질입니다 (← 루트).
> opcode는 1바이트 명령어 식별자라서 0~255 범위인데, 이게 **256-entry 점프 테이블의 인덱스로 그대로 쓰이도록** 의도된 설계입니다.
> 가장 순진한 switch는 디스패치 지점이 한 곳뿐이라 branch predictor가 학습 불가 → 거의 매번 misprediction → 인터프리터가 10~50배 느려집니다.
> Direct-Threaded는 각 핸들러 끝에 디스패치를 분산해서 predictor가 'iload_1 다음엔 iload_2가 자주 온다' 같은 패턴을 학습하게 만들고, **함수 호출이 아닌 goto로 직접 점프**해서 register를 영구 고정합니다.
> HotSpot Template Interpreter는 거기서 더 나가 부팅 시 어셈블리를 직접 generate합니다. 이유는 **register 영구 고정 + 자체 calling convention + frame layout 통제**가 C 컴파일러로는 불가능하기 때문이고, 이 통일된 ABI 덕에 인터프리터와 JIT 사이의 매끄러운 전환(OSR/Deopt)이 가능해집니다."

---

## 5. 꼬리질문 트리

### Q1 [가지 ①]. opcode가 왜 1바이트인가?

> (1) `.class` 컴팩트함 (90년대 모뎀 다운로드 전제). (2) 256-entry 점프 테이블 인덱스로 바로 쓸 수 있어 O(1) 디스패치. (3) 디코딩 단순. JVM은 약 200개 opcode 사용 — 여유 있음.

### Q2 [가지 ②]. Switch와 Direct-Threaded의 성능 차이의 원인?

> CPU의 indirect branch predictor가 각 점프 명령마다 별도 학습 기록을 가짐. Switch는 디스패치 지점 1개 → 학습 기록 1개에 200개 패턴 우겨넣음 → 분간 불가 → 거의 매번 misprediction. Threaded는 200개 핸들러에 200개 디스패치 지점 → 각자 자기 학습 기록 → "iload_1 다음 iload_2 자주" 패턴 학습 → 적중률 ↑.

### Q3 [가지 ③]. HotSpot이 어셈블리를 직접 generate하는 3가지 이유?

> (1) **Register 영구 고정** — C 컴파일러는 `register` 키워드 무시. r13/r14/rsp를 인터프리터 전체에서 안 흔들리게 강제 필요. (2) **자체 calling convention** — 인터프리터 ↔ JIT 사이 매끄러운 전환을 위해 표준 ABI가 아닌 JVM 자체 약속 필요. (3) **GC/Deopt 호환** — oop 위치 명시, safepoint poll, frame layout 통제는 C 컴파일러로 불가.

**🪝 Q3-1: Calling convention 통일이 왜 그렇게 중요한가?**
> 한 메서드 호출에서 호출자가 JIT, 피호출자가 인터프리터(혹은 반대)인 경우가 흔함. 두 측이 다른 register/스택 약속을 쓰면 잘못된 값을 읽고 crash. 통일돼야 OSR(인터프리터 → JIT 도중 전환)과 Deopt(JIT → 인터프리터 복귀)가 가능.

---

## 6. 학습 체크리스트

- [ ] opcode가 1바이트인 이유 3가지(컴팩트/인덱스/디코딩)를 말한다
- [ ] Switch 인터프리터가 느린 본질적 원인(branch misprediction)을 설명한다
- [ ] Direct-Threaded가 빠른 이유(디스패치 지점 분산 → predictor 학습)를 설명한다
- [ ] goto가 함수 호출보다 빠른 이유(prologue/epilogue 0 + register 고정)를 말한다
- [ ] HotSpot Template Interpreter가 어셈블리를 직접 generate하는 3가지 이유를 말한다
- [ ] Calling convention 통일이 OSR/Deopt와 어떻게 연결되는지 그린다
- [ ] 256-entry 점프 테이블과 1바이트 opcode의 설계 일치를 그림으로 그린다

---

## 관련 부록

- [부록 A — 인터프리터 구현 4가지 방식](./A-interpreter-implementations.md): Template Interpreter가 (1)~(4) 어디에 위치하는가
- [부록 C — AST 자료구조](./C-ast.md): bytecode가 1차원이 되기 전 단계인 AST
