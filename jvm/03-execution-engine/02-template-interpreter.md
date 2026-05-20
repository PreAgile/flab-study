# 03-02. Template Interpreter — JVM 시작 시 native template을 generate하는 인터프리터

> "인터프리터는 switch-case로 opcode 분기"라고 답하면 학부 수준 답이다.
> HotSpot의 인터프리터는 JVM 시작 시 **각 opcode마다 native assembly template을 직접 generate**해서 dispatch table에 등록. 실행 시에는 한 template 끝에서 다음 opcode template으로 inline jump. 일반 switch 대비 2~3배 빠르다.
> 시니어가 알아야 할 것: warmup 동안, Code Cache full 시, deopt 후 — 인터프리터가 실행하는 시간이 production에서 의외로 길다. 그 시간의 성능이 결국 사용자 응답이다.

---

## 이 문서의 사용법

1. **0장 마인드맵을 먼저 외운다** — 루트 + 4가지 + 키워드.
2. **1~4장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 대응.
3. **5장 면접 워크플로우로 검증**, **6장 꼬리질문으로 점검**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"Template Interpreter는 JVM 시작 시 각 opcode의 native assembly template을 generate해 dispatch table에 등록하고, 실행 시 한 template 끝에서 다음 opcode template으로 inline jump한다. 일반 switch 대비 2~3× 빠르고, 동시에 MDO에 profile을 수집해 JIT의 입력을 만드는 profiler 역할도 한다."**

### 4개 가지 — 순서를 외운다

```
              [ROOT: Template Interpreter = native template + threaded dispatch + profiler]
                                    │
       ┌──────────────┬─────────────┼─────────────┬──────────────┐
       │              │             │             │              │
      ① WHY         ② WHAT         ③ HOW         ④ 운영        (없음 - 4가지로 충분)
   왜 template       2단계 구조     Frame +       (시니어
   이 빠른가?        + dispatch     Safepoint +   진단)
                     table          MDO 수집
       │              │             │             │
       │         ┌────┼────┐    ┌───┼───┐    ┌────┼────┐
   no-dispatch-  Phase A    Phase B  invoc  back-  -Xint  Code   async-
   loop /        시작 시    실행 시  counter edge   재현    Cache  profiler
   branch        template   PC→     /type    counter         full→  unwind
   predictor /   generate   dispatch profile  → OSR          인터    문제
   asm 손작성    + dispatch  table             트리거         프리터
                 table 채움  jump
```

### 가지별 핵심 키워드 (각 가지 3개씩만)

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① WHY 빠른가** | no dispatch loop | branch predictor 친화 | asm 손작성 (TOS/BCP register cache) |
| **② WHAT 2단계 구조** | Phase A: 시작 시 template generate | Phase B: 실행 시 threaded dispatch | Dispatch table[256] |
| **③ HOW Frame+MDO** | invocation/backedge counter | type/branch profile (MDO) | safepoint poll inline |
| **④ 운영** | `-Xint` 재현/디버깅 | Code Cache full → 인터프리터 회귀 | async-profiler unwind 부정확 |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 적절한 가지 1개 → 키워드 3개 → 인접 가지

---

## 1. 가지 ①: WHY — 왜 Template이 빠른가

### 1.1 핵심 질문

> "switch-case 인터프리터와 비교해서 Template Interpreter가 빠른 이유는 무엇인가요? 본질적 차이가 뭔가요?"

### 1.2 키워드 1 — No Dispatch Loop

```c
// 일반 switch-case 인터프리터
while (running) {
    opcode = bytecode[pc++];
    switch (opcode) {
        case 0x15: /* iload */    handle_iload();    break;
        case 0x60: /* iadd */     handle_iadd();     break;
        // ... ~200개 case
    }
}
```

매 명령 후 `break` → loop 조건 체크 → 다음 iteration → switch dispatch. **dispatch overhead가 명령마다 발생**.

Template Interpreter:
```
각 template 마지막에 "다음 opcode 읽고 jump" 코드가 inline.
별도 loop 없음. control flow가 평탄.
명령 → 다음 명령으로 직접 점프.
```

### 1.3 키워드 2 — Branch Predictor 친화

```
[switch의 indirect branch]
한 곳(switch 위치)에서 ~200 곳으로 분기
→ branch predictor history 못 활용
→ 매 dispatch마다 misprediction 확률 높음

[Template의 inline dispatch]
각 template마다 별도 indirect jump
→ 각 지점에서 "이 opcode 다음 자주 오는 opcode" predict 가능
   예: iload 다음에 자주 iadd, iadd 다음에 자주 istore
→ branch predictor가 패턴 학습 → misprediction 감소
```

### 1.4 키워드 3 — Asm 손작성 (Register Caching)

일반 C 컴파일러는 generic 코드 생성. Template은 손으로 asm 작성:
- **TOS (Top of Stack) caching**: stack top을 register(`rax`)에 캐싱 → pop/push 줄임.
- **BCP (Bytecode Pointer) caching**: PC를 register(`r13`)에 영구 할당.
- **Dispatch table base caching**: table 주소를 register(`r14`)에 영구 할당.

```
iadd template (의사 코드):
  pop  rdx              ; 다음 → rdx
  pop  rax              ; top → rax (TOS register)
  add  rax, rdx         ; rax += rdx
  ; rax에 결과 = TOS caching 덕분에 push 불필요
  
  ; 다음 opcode로 inline dispatch
  movzx rbx, [r13]      ; r13(BCP)에서 다음 opcode 읽기
  inc r13               ; BCP++
  jmp [r14 + rbx*8]     ; r14(dispatch table base) + opcode 점프
```

→ 일반 switch 대비 **2~3× 빠름** (~10~20 cycles → ~3~5 cycles per opcode).

### 1.5 비교: Bytecode 인터프리터 dispatch 방식 6종

| 방식 | dispatch overhead | branch predict | 구현 복잡도 | 사용처 |
|---|---|---|---|---|
| Switch-case | 큼 | 나쁨 | 단순 | 학부, 작은 VM |
| Threaded (direct) | 작음 | 좋음 | 중간 | Forth |
| Threaded (indirect) | 작음 | 좋음 | 중간 | 옛 Java Quick |
| Computed-goto | 매우 작음 | 좋음 | GCC 확장 | Python (CPython), Ruby |
| Token-threaded | 중간 | 보통 | 단순 | 임베디드 |
| **Template** | 매우 작음 | 좋음 | 매우 복잡 | **HotSpot** |

HotSpot은 성능을 위해 구현 복잡도(CPU별 asm) 감수.

---

## 2. 가지 ②: WHAT — 2단계 구조 (Generation + Dispatch)

### 2.1 핵심 질문

> "Template Interpreter는 어떻게 구성되고, JVM 시작 시점과 실행 시점에 각각 무슨 일을 하나요?"

### 2.2 키워드 1 — Phase A: JVM 시작 시 Template Generate

```
JVM 부팅 시퀀스:
  ↓
TemplateInterpreterGenerator::generate_all() 호출
  ↓
각 opcode 순회 (~200개):
  for (opcode = 0; opcode < 256; opcode++) {
      generate_template(opcode);              // 그 opcode의 native asm 생성
      dispatch_table[opcode] = template_addr;  // table에 등록
  }
  ↓
모든 template이 Code Cache의 Non-method segment에 저장
  ↓
사용자 코드 실행 시 첫 메서드의 _from_interpreted_entry로 점프
  → 메서드 prolog → 첫 bytecode template로 dispatch
```

위치: `src/hotspot/cpu/x86/templateInterpreterGenerator_x86.cpp` (CPU별 구현).

```cpp
class TemplateInterpreterGenerator {
public:
    void generate_all() {
        for (int i = 0; i < 256; i++) {
            _dispatch_table[i] = generate_normal_template(i);
        }
        // 특수 entry points
        _entry_point_for_signature[normal] = generate_normal_entry();
        _entry_point_for_signature[synchronized] = generate_synchronized_entry();
        // ...
    }
};
```

### 2.3 키워드 2 — Phase B: 실행 시 Threaded Dispatch

```
PC가 가리키는 bytecode의 opcode 읽기
  ↓
dispatch_table[opcode] 점프
  ↓
template native code 실행 (3~10 instruction)
  ↓
마지막에 다음 opcode 읽고 다음 template로 inline jump
```

별도 dispatch loop 없음 — 각 template이 직접 다음 template로 점프. 이게 **threaded dispatch**의 본질.

### 2.4 키워드 3 — Dispatch Table[256]

```
dispatch_table[256]:   (opcode = 1바이트이므로 256개)
┌──────────────────────────────────┐
│ [0x00 nop]    → 0x...           │
│ [0x01 aconst_null] → 0x...      │
│ ...                              │
│ [0x15 iload]  → 0x0xA12FC8      │
│ [0x60 iadd]   → 0x0xA13380      │
│ [0xB6 invokevirtual] → 0x...    │
│ ...                              │
└──────────────────────────────────┘

크기: 256 × 8 byte (포인터) = 2KB
위치: Code Cache의 Non-method segment에 영구 보관
JVM이 한 번 generate 후 불변
```

### 2.5 메서드 호출 시점의 entry 선택

```
caller 코드:
  invokevirtual #15
       │
       ▼
nmethod 없음 → _from_interpreted_entry (인터프리터 stub)
                → interpreter frame 생성 (max_locals + max_stack 기반)
                → 파라미터를 caller에서 callee의 local slot으로 복사
                → 첫 bytecode template로 dispatch

nmethod 있음 → _from_compiled_entry (native code 진입)
                → native frame
```

### 2.6 한 template 내부 (iadd 예시)

```
iadd_template:
    ; 1. Operand stack 조작
    pop  rdx              ; 다음 → rdx
    pop  rax              ; top → rax (TOS caching)
    add  rax, rdx         ; rax += rdx
    
    ; 2. Profile / Safepoint (옵션, iadd는 보통 없음)
    
    ; 3. Dispatch — 다음 opcode로 점프
    movzx rbx, byte ptr [r13]   ; PC에서 다음 opcode 읽기 (r13=BCP)
    inc r13                      ; PC++
    jmp qword ptr [r14 + rbx*8]  ; r14=dispatch table base
```

---

## 3. 가지 ③: HOW — Frame + Safepoint + MDO 수집

### 3.1 핵심 질문

> "인터프리터가 실행하면서 동시에 무엇을 수집하나요? 그게 JIT에 어떻게 흘러가나요?"

### 3.2 키워드 1 — Invocation/Backedge Counter

```
[메서드 호출 시점 — invokevirtual template 안에 inline]
load  rax, [method_ptr + invocation_counter_offset]
inc   rax
store [method_ptr + invocation_counter_offset], rax
cmp   rax, Tier3InvocationThreshold
jge   request_compilation       ; → Compile Broker 호출

[Loop back-edge 시점 — branch backward template 안에 inline]
load  rax, [method_ptr + backedge_counter_offset]
inc   rax
store [method_ptr + backedge_counter_offset], rax
cmp   rax, Tier3BackEdgeThreshold
jge   request_OSR_compilation   ; → OSR variant 컴파일
```

위치: `src/hotspot/share/oops/methodCounters.hpp`:

```cpp
class MethodCounters : public Metadata {
private:
    InvocationCounter _invocation_counter;
    InvocationCounter _backedge_counter;
    // ...
};
```

→ **OSR이 인터프리터에서 트리거되는 이유**: 인터프리터의 backward branch template만 backedge counter를 증가시킴. 인터프리터가 없으면 OSR도 없음.

### 3.3 키워드 2 — Type/Branch Profile (MDO)

```
MDO (Method Data Object)
  ├─ Invocation Counter    (메서드 호출 += 1)
  ├─ Backedge Counter      (loop back-edge += 1) → OSR
  ├─ Type Profile          (invokevirtual call site별 receiver class)
  │     └─ 최대 2~3개 type 기록 (히스토그램)
  └─ Branch Profile        (if/switch의 taken/not taken 비율)
```

위치: `src/hotspot/share/oops/methodData.hpp`:

```cpp
class ReceiverTypeData {
  // invokevirtual call site의 receiver class 통계
  Klass* receiver(int row);
  uint   count(int row);
};

class BranchData {
  uint taken();
  uint not_taken();
};
```

C1/C2가 이 MDO를 읽어 inlining/speculation 결정. **MDO가 부족하면 C2의 최적화가 보수적**. 인터프리터는 단순한 "느린 실행기"가 아니라 **JIT의 정확한 입력을 만드는 profiler**.

### 3.4 키워드 3 — Safepoint Poll Inline

```
Concurrent GC가 모든 스레드를 정지시키려고 함:
  ↓
JVM이 polling page를 mprotect(PROT_NONE)으로 설정
  ↓
인터프리터의 backward branch template에 poll instruction이 inline:
    test rax, [polling_page_addr]   ; mprotect된 페이지 → SEGV
  ↓
SEGV 발생 → signal handler → 스레드를 safepoint blocking 상태로
  ↓
GC가 모든 스레드 정지 확인 후 GC 진행
```

→ Loop back-edge가 **safepoint poll + backedge counter + OSR 체크** 세 가지를 동시에 점검하는 가장 핵심적 위치.

### 3.5 Profile 수집 비용

```
인터프리터의 명령마다 profile 코드 (counter 증가):
  - 단순 명령 (iadd): ~0% overhead
  - 호출 명령 (invokevirtual): ~10~20% overhead
  - 분기 명령 (if): ~5~10% overhead

평균: 인터프리터 시간의 ~5% 정도가 profile 수집
```

작아 보이지만 인터프리터 시간 자체가 워낙 비싸므로 절대적으로는 큼. 그러나 그 profile이 C2의 좋은 최적화를 만들기에 가치가 큼.

---

## 4. 가지 ④: 운영 — 시니어 진단

### 4.1 핵심 질문

> "인터프리터가 실행하는 시간이 production에서 왜 중요한지, 어떻게 측정·진단하나요?"

### 4.2 키워드 1 — `-Xint` 옵션 (재현/디버깅)

```bash
java -Xint -jar app.jar
```

- JIT 완전 비활성. 인터프리터로만 실행.
- 일반 5~10× 느림. Production 사용 거의 없음.
- 사용처: JIT 버그 의심 재현, debugger 호환, 매우 빠른 startup (Code Cache 안 씀).
- **운영 함의**: Code Cache full 또는 deopt 폭주 시 사실상 `-Xint`와 비슷한 상태 도달 — 인터프리터로 도는 메서드의 성능이 곧 응답 성능.

### 4.3 키워드 2 — Code Cache full → 인터프리터 회귀

```bash
# 진단
jcmd <pid> Compiler.codecache | grep stopped
# stopped_count > 0 → JIT 한 번 멈춤

jcmd <pid> JFR.start duration=60s
jfr print --events jdk.ExecutionSample mp.jfr
# tier 분포에서 interpreter 비율 ↑ (정상 ~5%, 회귀 시 60%+)
```

원인: Code Cache 가득 차 새 컴파일 거부 → deopt된 메서드들이 인터프리터로 영구.

조치: `-XX:ReservedCodeCacheSize=512m`, 또는 `-XX:-TieredCompilation` (Code Cache 절약).

### 4.4 키워드 3 — async-profiler Unwind 부정확

```bash
asprof -e cpu -d 60 -f profile.html <pid>
```

문제:
- 컴파일된 nmethod는 frame layout이 표준 (RBP 기반) → unwinder 정확.
- 인터프리터 frame은 HotSpot 자체 layout (RBP가 다른 의미) → 일반 unwinder 혼란.
- 시작 직후 (warmup 중) 측정 → 인터프리터 frame 많아 flame graph 흐릿.

해결:
- `--cstack vm` 옵션 — HotSpot 내부 unwinder 사용.
- JFR로 대체 (`jdk.ExecutionSample`).
- **운영 함의**: warmup 끝난 후 측정하면 인터프리터 frame 적어 정확도 ↑.

### 4.5 운영 시나리오 진단 매트릭스

| 증상 | 진단 | 가능 원인 |
|---|---|---|
| 시작 후 첫 1~5분 응답 느림 | JFR `jdk.ExecutionSample`의 tier 분포 | 정상 — 인터프리터 비율 높은 warmup |
| 운영 중 갑자기 응답 5× 느림 | `jcmd Compiler.codecache` stopped_count | Code Cache full → 인터프리터로 회귀 |
| 특정 메서드만 영원히 느림 | `-XX:+PrintCompilation` `made not entrant` 빈도 | 그 메서드 deopt 후 재컴파일 못 함 (make_not_compilable) |
| async-profiler flame graph 흐릿 | 측정 시점 확인 | warmup 중 측정 — 끝나고 다시 |

### 4.6 Killer 시나리오 — Code Cache full → 인터프리터 회귀

```
환경: Spring Boot, JDK 21, -Xmx 2g
증상: 시작 30분 후 응답 5× 느려짐 (P99 50ms → 250ms)

진단:
1. jcmd Compiler.codecache | grep stopped
   stopped_count=1   ← JIT 한 번 멈춤
2. jcmd Compiler.codecache | grep non-profiled
   non-profiled: 117MB / 117MB (100%)   ← 가득 참
3. JFR jdk.ExecutionSample tier 분포
   interpreter: 60%, compiled: 40%      ← 정상은 ~5:95

원인: Code Cache full → 새 컴파일 안 됨 → deopt된 메서드들이 인터프리터로

조치:
- -XX:ReservedCodeCacheSize=512m
- 또는 -XX:-TieredCompilation (warmup 느림 트레이드오프)
- 근본: Lambda/proxy 폭주 → 동적 클래스 audit
```

---

## 5. 면접 답변 워크플로우

### 5.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "HotSpot 인터프리터가 왜 빠른가?" | ① WHY | ② WHAT의 template generate |
| "Template Interpreter 구조?" | ② WHAT | ③ HOW의 profile |
| "인터프리터가 수집하는 profile?" | ③ HOW (MDO) | C2 inlining 결정 (05장) |
| "OSR이 왜 인터프리터에서 트리거?" | ③ HOW (backedge counter) | OSR 풀버전 (01장) |
| "Code Cache full 진단" | ④ 운영 | 02-04 Code Cache |
| "async-profiler 흐릿한 이유" | ④ 운영 (unwind) | warmup 중 측정 |

### 5.2 답변 템플릿

> 루트 → 가지 키워드 3개 → 인접

예: "HotSpot의 Template Interpreter가 일반 switch-case 인터프리터보다 빠른 이유는?"

> "HotSpot의 Template Interpreter는 JVM 시작 시 각 opcode의 native assembly template을 generate해 dispatch table에 등록하고, 실행 시 한 template 끝에서 다음 opcode template으로 inline jump합니다. (← 루트)
> 일반 switch 대비 3가지 본질적 차이로 2~3배 빠릅니다.
> 첫째, **no dispatch loop**: switch는 매번 loop 시작으로 → loop overhead. Template은 각 명령이 직접 다음 명령으로 점프 → control flow 평탄.
> 둘째, **branch predictor 친화**: switch의 indirect branch는 한 곳에서 ~200 방향. Template의 inline dispatch는 각 위치마다 별도 indirect jump → 각 위치에서 다음 자주 오는 opcode를 predict 가능 (예: iload 다음 자주 iadd).
> 셋째, **asm 손작성**: TOS register caching, BCP register caching, dispatch table base register caching — 일반 C 컴파일러가 못 하는 최적화.
> 트레이드오프는 구현 복잡도 — CPU별로 asm을 따로 작성해야 함 (x86, ARM, RISC-V). 작은 VM은 cost 못 감당해 computed-goto로 절충 (Python, Ruby)."

---

## 6. 꼬리질문 트리 (가지별)

### Q1 [가지 ①]. HotSpot Template Interpreter가 switch보다 빠른 3가지 본질적 이유는?

> 1. **No dispatch loop**: 각 명령이 직접 다음 명령으로 jump → loop overhead 없음.
> 2. **Branch predictor 친화**: 각 template마다 별도 indirect jump → predictor가 패턴 학습 가능 (iload → iadd 등).
> 3. **손작성 asm**: TOS/BCP/dispatch table base를 register에 영구 캐싱.
> 결과: 일반 switch 대비 ~2~3× 빠름 (~10~20 cycles → ~3~5 cycles per opcode).

**🪝 Q1-1: 그럼 다른 VM은 왜 Template을 안 쓰나요?**
> 구현 복잡도와 이식성. CPU별로 asm 작성 필요 (x86, ARM, RISC-V). 작은 VM 프로젝트는 cost 못 감당. Python (CPython), Ruby (MRI)는 computed-goto로 절충 — 성능 일부 양보하고 이식성 ↑.

### Q2 [가지 ②]. JVM 시작 시 Template Interpreter는 어떻게 만들어지나요?

> TemplateInterpreterGenerator::generate_all()이 부팅 시 호출됨.
> 각 opcode 순회 (~200개):
> 1. 그 opcode의 native asm 생성 (MacroAssembler API).
> 2. dispatch_table[opcode] = template 주소.
> 모든 template이 Code Cache의 Non-method segment에 저장. 한 번 generate 후 불변.
> 시간 ~수십 ms, Code Cache의 ~2MB.

### Q3 [가지 ③]. 인터프리터가 수집하는 profile에는 무엇이 있고 왜 필요한가요?

> 4가지 핵심:
> 1. **Invocation Counter**: 메서드 호출 횟수 → 임계 도달 시 Tier 승격 트리거.
> 2. **Backedge Counter**: loop back-edge 횟수 → OSR 컴파일 트리거.
> 3. **Type Profile**: invokevirtual call site별 receiver 클래스 → C2의 inlining 결정.
> 4. **Branch Profile**: if/switch taken/not 비율 → C2의 speculation 결정.
> 인터프리터는 "느린 실행기"가 아니라 **JIT의 정확한 입력을 만드는 profiler**. profile 부족하면 C2 최적화 보수적 → peak ↓.

**🪝 Q3-1: OSR이 왜 인터프리터에서 트리거되나요?**
> 인터프리터의 backward branch template만 backedge counter를 증가시킴. 컴파일된 코드는 안 함. 따라서 메서드가 1번 호출이지만 loop가 hot한 경우 (`main { for (i < 1e9) ... }`), 인터프리터가 backedge counter로 OSR을 트리거하는 유일한 경로.

### Q4 [가지 ③]. Safepoint poll은 인터프리터의 어디서 발생하나요?

> Backward branch template에 poll instruction이 inline. `test rax, [polling_page_addr]` — mprotect된 페이지에 접근하면 SEGV 발생 → signal handler가 safepoint blocking 상태로 전환.
> 인터프리터는 자연스러운 polling 지점들이 많아 safepoint 진입이 빠름. JIT 컴파일된 코드는 별도 polling instruction 삽입 필요.

### Q5 [가지 ④]. `-Xint`를 운영에서 쓰는 경우는?

> 거의 없음 (5~10× 느림). 사용처:
> 1. JIT 버그 의심 시 재현/우회.
> 2. Debugger 호환 (일부 디버거가 native code에서 buggy).
> 3. 매우 빠른 startup이 필요한 batch (Code Cache 안 씀).
> Production에서는 `Code Cache full + JIT 비활성` 상태가 사실상 `-Xint`와 비슷한 결과 — 진단의 첫 의심.

### Q6 (Killer) [가지 ④]. Spring Boot 앱이 시작 30분 후 응답이 5배 느려졌습니다. 인터프리터 회귀를 의심하고 진단하세요.

> 1. **Code Cache 상태**:
>    ```
>    jcmd <pid> Compiler.codecache | grep -E 'stopped|non-profiled'
>    ```
>    stopped_count > 0 → JIT 한 번 멈춤. segment 100% → full.
> 2. **Tier 분포 (JFR)**:
>    ```
>    jcmd <pid> JFR.start duration=60s
>    jfr print --events jdk.ExecutionSample tier.jfr | awk '{print $7}' | sort | uniq -c
>    ```
>    interpreter 비율 정상(~5%)을 크게 넘으면 회귀.
> 3. **메서드별 상태**: `-XX:+PrintCompilation` 의 `made not entrant` 빈도.
> 4. **원인 식별**:
>    - Code Cache full → `ReservedCodeCacheSize ↑`.
>    - Deopt 폭주 → JFR `jdk.Deoptimization` reason 분석.
>    - cold path → `CompileThreshold` 낮춤 또는 `CompileCommand=compileonly` 강제.

**🪝 Q6-1: Code Cache full을 미리 모니터링하려면?**
> Prometheus + JMX: `jvm.code_cache.usage`, `java.lang:type=MemoryPool,name=CodeHeap.*` MBean. 80% 임계 알람. JFR 주기 dump + `jdk.CodeCacheStatistics` 이벤트로 사후 분석.

---

## 7. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 이내로 그릴 수 있다 (루트 + 4가지 + 키워드 3개)
- [ ] 가지 ① WHY: 3가지 본질적 이유 (no loop, predictor, asm) 말한다
- [ ] 가지 ② WHAT: Phase A (시작 시 generate) + Phase B (실행 시 dispatch) 그림 그린다
- [ ] 가지 ② WHAT: iadd template 의사 asm 코드 작성한다
- [ ] 가지 ③ HOW: MDO 4종 (invocation/backedge/type/branch) 설명한다
- [ ] 가지 ③ HOW: OSR이 인터프리터에서 트리거되는 이유 설명한다
- [ ] 가지 ④ 운영: Code Cache full → 인터프리터 회귀 4단계 진단 절차 말한다
- [ ] 가지 ④ 운영: async-profiler unwind 부정확 원인과 해결책 말한다
- [ ] 6장 꼬리질문 6개에 막힘없이 답한다

---

## 다음 단계

- → [03. Tiered Compilation](./03-tiered-compilation.md): Compile Broker + tier 결정 + CompilerThread
- → [04. C1 and C2](./04-c1-and-c2.md): C1/C2 컴파일러 비교 + Sea-of-Nodes
- → [08. Speculative and Deopt](./08-speculative-and-deopt.md): Deopt 후 인터프리터 복귀
- ← [01. Execution Overview](./01-execution-overview.md): 전체 흐름
- ← [Chapter 02-04 Code Cache](../02-runtime-data-areas/04-code-cache.md): Non-method segment에 template 저장

## 참고

- **HotSpot src `templateTable.hpp/cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/interpreter/templateTable.hpp
- **HotSpot src `templateInterpreterGenerator.hpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/interpreter/templateInterpreterGenerator.hpp
- **HotSpot src `methodData.hpp`** (MDO): https://github.com/openjdk/jdk/blob/master/src/hotspot/share/oops/methodData.hpp
- **JVM Anatomy Quark #2 — Template Interpreter** (Shipilëv): https://shipilev.net/jvm/anatomy-quarks/
- **Cliff Click — Why HotSpot is Fast**: 컨퍼런스 발표
- **HotSpot Glossary — Interpreter**: https://openjdk.org/groups/hotspot/docs/HotSpotGlossary.html
