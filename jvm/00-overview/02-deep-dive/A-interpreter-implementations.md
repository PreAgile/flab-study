# 부록 A — 인터프리터 구현 4가지 방식

> "인터프리터"라는 단어 하나가 가리는 4가지 구현 방식이 있다. HotSpot은 그중 Template Interpreter — "부팅 시 자기 자신을 어셈블리로 generate하는, 사실상 매우 단순한 JIT". 이걸 모르면 OSR/Deopt가 어떻게 가능한지 설명 못 한다.

---

## 이 문서의 사용법

본문 → [02. 컴파일 흐름](../02-class-compilation-flow.md)의 가지 ④ Interpreter에서 진입. "Template Interpreter 변형을 쓴다"는 한 줄을 풀어쓴 부록.

1. **0장 마인드맵을 먼저 외운다**.
2. **1~4장 4가지 방식을 순서대로 학습** — 같은 인터프리터인데 왜 4가지로 갈렸는지.
3. **5장 면접 답변 워크플로우**.

---

## 0. 마인드맵

### 루트 한 문장 (anchor)

> **"인터프리터는 native code로 변환 안 하는 게 정의지만, 실제 구현은 4가지 — Switch(1996), Direct-Threaded(CPython 3.11), Template(HotSpot), AST(GraalVM Truffle). HotSpot은 부팅 시 어셈블리를 미리 generate해서 점프 테이블로 디스패치하는 Template 방식이고, 이게 JIT과의 매끄러운 전환(OSR/Deopt)을 가능하게 한 결정적 설계다."**

### 4개 가지

```
              [ROOT: Interpreter 4 구현 방식]
                          │
       ┌─────────┬────────┼────────┬────────┐
      ① Switch  ② Threaded ③ Template ④ AST
                                    (Truffle)
       │         │         │         │
      C switch  goto*next  부팅시   AST를
      branch    GCC&&label asm gen  IR로
      mispred   CPython3.11 점프     실행
      Classic   Lua        테이블
      VM 1996                       
                          HotSpot
                          매우단순JIT
```

### 가지별 핵심 키워드

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① Switch** | C switch 문 | branch misprediction | Classic VM, 20~50배 느림 |
| **② Direct-Threaded** | `goto *next_handler` | GCC `&&label` 확장 | CPython 3.11+, Lua |
| **③ Template ★** | 부팅 시 어셈블리 generate | 256-entry 점프 테이블 | JIT과 calling convention 통일 |
| **④ AST (Truffle)** | bytecode 없음 | AST를 IR로 평생 들고 | 핫 서브트리 통째 JIT |

---

## 1. 가지 ①: Switch — 가장 순진한 방식

### 1.1 핵심 질문

> "왜 1996년 Classic VM이 C++ 대비 20~50배 느렸나?"

### 1.2 키워드 1 — C switch 문 디스패치

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

C/C++의 `switch` 문 하나에 모든 bytecode를 case로 나열. 단순.

### 1.3 키워드 2 — branch misprediction의 본질

매 bytecode마다 점프 테이블을 거치고, CPU의 **branch predictor가 다음 opcode를 예측 못 함** — 인덱스가 매번 다르니까. **indirect branch misprediction이 거의 항상** 발생.

현대 CPU는 파이프라인 + 추측 실행으로 빨라졌는데, predictor가 빗나가면 그 추측이 모두 무효 → 파이프라인 flush. 인터프리터에서 이게 매 bytecode마다 일어난다.

### 1.4 키워드 3 — Classic VM 1996

1996년 Classic VM이 이 방식. "Java is slow" 신화의 출발. C++ 대비 20~50배 느림.

→ 이 한계 때문에 1999년 HotSpot(JIT 도입) + Template Interpreter가 나왔다.

---

## 2. 가지 ②: Direct-Threaded — 살짝 진화

### 2.1 핵심 질문

> "switch보다 빠른 인터프리터를 표준 C에 안 갇히고 만드는 방법?"

### 2.2 키워드 1 — `goto *next_handler` 패턴

각 opcode 핸들러의 주소를 테이블에 저장하고, 각 핸들러 끝에서 다음 opcode 주소로 **직접 점프**.

```c
void* table[256] = {
    [ICONST_0] = &&h_iconst_0,
    [IADD]     = &&h_iadd,
    // ...
};

goto *table[*pc++];   // 디스패치

h_iadd:
    /* ... iadd 처리 ... */
    goto *table[*pc++];   // ★ 핸들러 끝에서 다시 직접 점프
```

### 2.3 키워드 2 — GCC `&&label` 확장

`&&label`은 GCC 확장 — labeled goto의 주소를 얻는 표준 C가 아닌 문법. Clang도 지원하지만 MSVC는 안 함.

### 2.4 키워드 3 — 왜 switch보다 빠른가

switch는 항상 한 곳(switch 본체)으로 돌아갔다가 다음으로 점프 → branch predictor가 그 한 곳의 다음 분기를 학습할 수밖에 없는데 그게 매번 달라서 학습 실패.

Direct-threaded는 **각 핸들러 끝마다 다음 점프 instruction이 따로** 있음 → predictor가 "iadd 끝에서는 보통 istore로 간다" 같은 **opcode 쌍 패턴**을 학습 가능 → hit rate ↑.

**대표 구현**: CPython 3.11+ (PEP 659), Lua. 표준 C 아니라서 portable 코드엔 못 쓰지만, 인터프리터 성능에 큰 도움.

→ 더 깊은 디스패치 메커니즘은 → [부록 D](./D-opcode-dispatch.md).

---

## 3. 가지 ③: Template Interpreter — HotSpot의 방식 (★ 핵심)

### 3.1 핵심 질문

> "HotSpot이 부팅 시 자기 인터프리터를 어셈블리로 generate한다는 게 정확히 뭔가?"

### 3.2 키워드 1 — 부팅 시 어셈블리 generate

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

`iadd` opcode를 만나면 HotSpot은 미리 generate해둔 어셈블리로 점프:
```asm
pop    rax                    ; operand stack에서 b를 register로
add    [rsp], eax             ; 첫번째 값과 더해서 stack top에 저장
movzbl eax, byte [r13+1]      ; 다음 bytecode opcode 읽기
inc    r13                    ; pc 1 증가
jmp    [r14 + rax*8]          ; ← 다음 opcode의 generated assembly로 점프
                              ;   r14 = 테이블 base, rax = opcode
```

**HotSpot 인터프리터는 부팅 시점에 자기 자신을 어셈블리로 컴파일한다**. 그래서 `templateInterpreter.cpp`가 길고 `__` 매크로(`MacroAssembler*`를 풀어쓴 것)를 쓴다.

### 3.3 키워드 2 — 256-entry 점프 테이블

opcode 1바이트(0~255) ↔ 256-entry 테이블 인덱스. **opcode 디자인 자체가 점프 테이블 디스패치를 전제**.

```
점프 테이블 (256개 슬롯의 배열):
┌──────────────────────────────────────────┐
│ index 0x00:  →  handle_nop 어셈블리      │
│ index 0x1B:  →  handle_iload_1 어셈블리  │
│ index 0x60:  →  handle_iadd 어셈블리     │  ← 부팅 시 generate된
│ ...                                       │     어셈블리 코드들
│ index 0xFF:  →  ...                       │
└──────────────────────────────────────────┘
         ↑
  opcode를 이 배열의 인덱스로 사용
```

매 핸들러 끝에 `jmp [r14 + rax*8]` 한 줄 — 이게 다음 opcode 디스패치. O(1).

### 3.4 키워드 3 — JIT과 calling convention 통일 (★ OSR/Deopt의 비결)

왜 부팅 시 generate하는가 — **세 가지 이유**:

**(1) C 컴파일러 한계 회피**
- C 컴파일러는 범용 → 인터프리터의 특수 패턴("한 줄 처리 후 분산 점프")에 최적화 못 함.
- register 배치, branch 배치, calling convention을 인터프리터 전용으로 손수 설계.
- 결과: C로 짠 인터프리터보다 **2~3배 빠름**.

**(2) 멀티 아키텍처 한 소스 관리**
- HotSpot은 x86_64, aarch64, ppc, s390 지원.
- 부팅 시 "이 CPU가 뭐냐" 보고 거기 맞는 어셈블리 generate → 하나의 소스로 여러 아키텍처.

**(3) JIT과 calling convention 통일 (★)**
- 인터프리터 ↔ JIT 코드 사이를 매끄럽게 점프하려면 둘이 **같은 register 규약, 같은 스택 레이아웃**.
- C 컴파일러는 이걸 강제 못 함. 어셈블리 직접 generate해야 강제 가능.
- 결과: **deoptimization** (JIT → 인터프리터로 복귀), **OSR** (인터프리터 → JIT 도중 전환) 가능.

비유: C 컴파일러가 만든 인터프리터 = 기성품 양복. Template Interpreter = 맞춤 양복. 부팅 시 한 번 만들고 평생 입는다.

### 3.5 자바 세계의 4층 구조 (어셈블리 위치)

| 층 | 예시 | 누가 실행/이해 |
|---|---|---|
| Java 소스 | `int c = a + b;` | 사람·javac |
| **Bytecode** | `iload_1 iload_2 iadd istore_3` | **JVM** |
| **어셈블리** | `mov eax, [rbp-4]` `add eax, [rbp-8]` ... | **CPU (변환 후)** |
| 기계어 | `8B 45 FC 03 45 F8 ...` | **CPU 직접** |

- **Bytecode**는 가상 CPU 명령어 → JVM이 해석. 플랫폼 독립.
- **어셈블리/기계어**는 실제 CPU 명령어 → 직접 실행. 플랫폼 종속.

x86_64 어셈블리는 ARM Mac에서 못 돈다. 그래서 자바가 bytecode 층을 둔 것.

### 3.6 "매우 단순한 JIT" 비교

Template Interpreter도 부팅 시점에 어셈블리를 동적 생성한다는 점에서 JIT의 정의에 부분적으로 해당. 그래서 "사실상 매우 단순한 JIT".

| 항목 | Template Interp | C1 JIT | C2 JIT |
|---|---|---|---|
| **언제 generate?** | JVM 부팅 시 **1회** | 메서드 hot 시점 (매번) | 더 hot 시점 (매번) |
| **무엇을** | 각 opcode 핸들러 (200개) | 한 메서드 전체 native | 한 메서드 + inlined |
| **최적화** | 거의 없음 (고정 템플릿) | 가벼움 | 공격적 (EA, vec, ...) |
| **컴파일 시간** | 부팅 시 수 ms | 1~10 ms | 10~수백 ms |
| **결과물 크기** | 메서드와 무관 (고정) | bytecode의 3~5배 | 10~30배 (inline) |
| **프로파일 활용?** | 안 함 | 일부 | 적극 활용 |
| **deopt 가능?** | N/A | 가능 | 가능 |

---

## 4. 가지 ④: AST + Self-optimizing (Truffle/GraalVM)

### 4.1 핵심 질문

> "bytecode 자체를 없애고 AST를 평생 들고 다니는 인터프리터가 있다?"

### 4.2 키워드 1 — bytecode 단계 없음

전통적 흐름: 소스 → bytecode → 인터프리터/JIT.
Truffle: 소스 → AST → **AST를 직접 인터프리트**. bytecode 단계가 아예 없다.

### 4.3 키워드 2 — AST를 IR로 평생 들고 다님

각 AST 노드가 `execute()` 메서드를 가지고, 자식 노드를 재귀 호출. AST 자체가 실행 가능한 IR.

```
[+ 노드]
├─ execute() — left.execute() + right.execute()
├─ [a 노드] — variable lookup
└─ [b 노드] — variable lookup
```

### 4.4 키워드 3 — 핫 서브트리 통째 JIT (Partial Evaluation)

Self-optimizing AST + Partial Evaluation: 인터프리트하면서 타입을 좁히고, hot 서브트리는 Graal JIT으로 통째 컴파일. 같은 인프라(Truffle)로 JavaScript, Python, R, Ruby, LLVM IR을 다 돌릴 수 있다.

→ Truffle이 AST를 IR로 쓰는 본격 설명은 → [부록 C](./C-ast.md).
→ Polyglot 구현 차이는 → [부록 B](./B-jvm-implementations.md).

---

## 5. 면접 답변 워크플로우

### 5.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 |
|---|---|
| "Classic VM이 왜 느렸나?" | ① Switch (branch mispred) |
| "CPython 3.11이 빨라진 이유?" | ② Threaded |
| "HotSpot 인터프리터가 일반 인터프리터와 뭐가 다른가?" | ③ Template |
| "OSR/Deopt가 어떻게 가능한가?" | ③ calling convention 통일 |
| "GraalVM Truffle이 뭐?" | ④ AST |

### 5.2 답변 템플릿

> "인터프리터에도 4가지 구현 방식이 있는데(← 루트), HotSpot은 Template Interpreter라는 매우 독특한 방식입니다.
> 부팅 시점에 각 bytecode opcode에 대응하는 어셈블리 시퀀스를 직접 generate해서 메모리에 배치하고, 256-entry 점프 테이블로 디스패치합니다.
> 일반 switch 인터프리터가 branch mispredictor 때문에 느린 걸 회피하고, 무엇보다 **JIT 컴파일된 코드와 calling convention을 통일**해서 인터프리터 ↔ JIT 사이의 매끄러운 전환(OSR/Deopt)을 가능하게 합니다."

---

## 6. 꼬리질문 트리

### Q1 [가지 ③]. Template Interpreter가 부팅 시 어셈블리를 generate하는 이유는?

> (1) C 컴파일러가 만든 인터프리터보다 2~3배 빠름. (2) 멀티 아키텍처(x86/ARM/...)를 한 소스로. (3) JIT과 calling convention 통일 → OSR/Deopt 가능.

**🪝 Q1-1: calling convention 통일이 정확히 뭔가?**
> 인터프리터와 JIT 코드가 같은 register 규약과 스택 레이아웃을 쓰는 것. C 컴파일러는 강제 못 함. 통일돼야 native frame ↔ interpreter frame 변환이 가능 (Deopt의 핵심).

### Q2 [가지 ①, ②]. switch가 왜 느리고 threaded가 왜 빠른가?

> switch는 항상 switch 본체(한 곳)로 돌아갔다가 다음으로 점프 → branch predictor가 그 한 곳의 분기를 학습할 수밖에 없는데 매번 달라서 학습 실패. Direct-threaded는 각 핸들러 끝마다 점프 instruction이 따로 → predictor가 "iadd 끝에서는 보통 istore" 같은 **opcode 쌍 패턴** 학습 가능.

### Q3 [가지 ③]. 256-entry 점프 테이블이 가능한 이유는?

> bytecode opcode가 1바이트(0~255)로 설계됐기 때문. opcode 디자인 자체가 점프 테이블 디스패치를 전제로 했음. `jmp [table_base + opcode*8]` 한 줄로 O(1) 디스패치.

---

## 7. 학습 체크리스트

- [ ] 인터프리터 4 방식(Switch/Threaded/Template/AST)을 한 줄씩 구분한다
- [ ] HotSpot이 부팅 시 어셈블리를 generate하는 3가지 이유를 말한다
- [ ] Template Interpreter의 OSR/Deopt가 가능한 결정적 이유(calling convention 통일)를 설명한다
- [ ] 256-entry 점프 테이블과 1바이트 opcode의 연결을 그린다
- [ ] Template Interpreter vs C1/C2 JIT 비교표를 적는다

---

## 관련 부록

- [부록 B — JVM 구현체 비교](./B-jvm-implementations.md): HotSpot/OpenJDK/GraalVM/OpenJ9/Azul/ART의 인터프리터·JIT 차이
- [부록 C — AST 자료구조](./C-ast.md): Truffle이 AST를 IR로 쓰는 (4) 방식의 본격 설명
- [부록 D — opcode 디스패치 메커니즘](./D-opcode-dispatch.md): switch vs threaded 본격 분석 (branch predictor 학습)
