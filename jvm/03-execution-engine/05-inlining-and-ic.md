# 03-05. Inlining + Inline Cache — JIT의 가장 강력한 최적화

> "**Inlining is the mother of optimizations**" — JIT 분야의 격언이다.
> 한 함수 호출을 caller에 펼치는 단순한 변환이 **다른 모든 최적화의 효과를 폭발적으로 키운다**. Constant propagation, dead code elimination, escape analysis, loop optimization — 모두 inline된 코드에 더 잘 적용된다.
> Inlining의 성공은 **Inline Cache (IC)의 상태**에 직접 의존. IC가 monomorphic이면 C2가 자유롭게 inline. Megamorphic이면 inline 불가 + 모든 cross-method 최적화 차단.
> 시니어가 알아야 할 것: P99 latency spike의 단골 원인이 **megamorphic call site**. 인터페이스 사용을 늘렸을 뿐인데 갑자기 느려졌다면 IC를 들여다보면 답이 보인다.

---

## 이 문서의 사용법

1. **0장 마인드맵을 먼저 외운다** — 루트 + 5가지 + 키워드.
2. **1~5장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 대응.
3. **6장 면접 워크플로우**, **7장 꼬리질문**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"Inlining은 callee를 caller에 펼쳐 넣는 변환이고 cross-method 최적화의 enabler다. 성공 여부는 Inline Cache의 4단계 (Mono/Bi/Poly/Megamorphic)와 메서드 크기/깊이 휴리스틱에 달림. CHA로 monomorphic 가정 → 강제 inline → 가정 깨지면 deopt — P99 spike의 단골 원인이 이 사이클."**

### 5개 가지 — 순서를 외운다

```
                  [ROOT: Inlining + IC 4단계 + CHA speculation]
                                  │
       ┌──────────────┬───────────┼───────────┬──────────────┐
       │              │           │           │              │
      ① WHY         ② WHAT IC    ③ HOW       ④ 운영        ⑤ 진화
   왜 mother of      4단계         Inlining   (시니어       (Smalltalk
   optimizations?    상태 +        휴리스틱   진단)         → Self
                     dispatch                                → HotSpot
                     비용                                    → Sealed)
       │              │           │           │              │
       │         ┌────┼────┐  ┌───┼───┐  ┌────┼────┐         │
   호출 overhead Mono  Bi    크기   누적   CHA   Print  1983  1991  2021
   /cross-method Poly  Mega  ≤Max  Desired 위반   Inlin  IC   PIC   sealed
   /EA/Type      check + dispatch Inline ed     Deopt  ing  intro intro
   sharpen/DCE   /vtable /3-20cyc Size  Method                       (CHA
   /Loop                          Limit  Stream                       강력)
                                        AOP
```

### 가지별 핵심 키워드 (각 가지 3개씩만)

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① WHY mother** | 호출 overhead 제거 | cross-method opt 활성 (constant fold, DCE) | EA/Type sharpen/Loop opt cascade |
| **② WHAT IC 4단계** | Monomorphic (3 cycle, inline ✓) | Bimorphic/Polymorphic | Megamorphic (vtable, inline ✗) |
| **③ HOW 휴리스틱** | MaxInlineSize 35 / FreqInlineSize 325 | DesiredMethodLimit 8KB / MaxInlineLevel 9 | IC 상태 + callee 종류 |
| **④ 운영** | -XX:+PrintInlining 메시지 | JITWatch inline tree | Stream API / Spring AOP 함정 |
| **⑤ 진화** | Smalltalk-80 IC (1983) | Self PIC (1991) | Sealed class CHA 강화 (JDK17) |

### 면접 답변 흐름

> 면접관 질문 → 루트 → 가지 → 키워드 3개 → 인접

---

## 1. 가지 ①: WHY — 왜 Inlining이 "mother of optimizations"

### 1.1 핵심 질문

> "함수 호출 펼치기 자체는 단순한 변환인데, 왜 그렇게 결정적인 최적화로 불리나요?"

### 1.2 키워드 1 — 호출 Overhead 제거 (자체 효과는 작음)

```
inline 전:
  prologue ~5 ns
  parameter passing ~수 ns
  epilogue ~5 ns

inline 후: 위 비용 0
```

→ 단순한 비용 자체는 ~10ns. 작아 보임. **진짜 가치는 cascade**.

### 1.3 키워드 2 — Cross-method Opt 활성 (Constant fold, DCE)

```
[Constant Propagation]
inline 전:
  foo() { x = bar(3); }
  bar(int n) { return n + 1; }
inline 후:
  foo() { x = 3 + 1; }   → C2가 즉시 constant fold → x = 4

[Dead Code Elimination]
inline 전:
  foo() { if (debug()) log("..."); }
inline 후 (debug()가 inline되어 false 반환):
  foo() { if (false) log("..."); }   → if/log 전체 제거
```

### 1.4 키워드 3 — EA / Type Sharpening / Loop Opt Cascade

```
[Escape Analysis 활성화]
inline 전:
  foo() { Point p = makePoint(); use(p); }   // p가 makePoint 안에서 escape?
inline 후:
  foo() {
      p = new Point();   // 메서드 안에서만 사용
      use(p);
  }
  → EA가 "p는 escape 안 함" 결론
  → Scalar Replacement: new Point 안 만들고 fields를 register로

[Type Sharpening]
inline 전:
  foo(Object o) { o.toString(); }
inline 후 (caller가 String만 넘긴다면):
  foo(String s) { s.toString(); }
  → String.toString 직접 호출 (vtable 안 거침)

[Loop opts 확장]
inline 전: loop 안에서 호출 → unrolling 효과 제한
inline 후: loop 안에서 직접 코드 → unrolling, vectorization 풍부
```

→ Inlining 1번이 위 5가지 효과를 폭발적으로 키움. **"Inlining이 막히면 다른 최적화 다 죽는다"**.

### 1.5 비유로 굳히기

> **요리 비유**: Inlining = 레시피의 "부재료 양념 준비"를 별도 단계로 두지 않고 main 레시피에 직접 풀어 쓰기. 단계 전환 비용 없음 + 그 양념에 다른 조정 가능 (예: 메인 재료 보고 양념 더 줄이기).

---

## 2. 가지 ②: WHAT — IC 4단계 + Dispatch 비용

### 2.1 핵심 질문

> "Inline Cache가 무엇이고, 4단계는 각각 어떤 dispatch 비용을 가지며, 어느 단계에서 inline이 가능한가요?"

### 2.2 키워드 1 — Monomorphic (3 cycle, inline 가능)

```
[메서드 첫 호출 시점]
컴파일된 nmethod의 invokevirtual 위치:
  call IC_uninitialized_handler   ; 첫 호출 시 type 정보 없음
        ↓ 첫 호출 receiver = FooImpl

[Monomorphic 상태]
  cmp [a.klass], FooImpl     ; 1 cmp
  jne IC_miss_handler         ; 1 branch (predicted not-taken)
  jmp FooImpl.foo             ; 1 jmp (direct)
                              = ~3 cycles
                              + inline 가능 → cross-method 최적화
```

가장 빠른 dispatch + inline 가능. C2의 공격적 최적화가 가능한 유일한 상태.

### 2.3 키워드 2 — Bimorphic / Polymorphic (중간)

```
[Bimorphic 또는 Polymorphic 상태]
  cmp [a.klass], FooImpl
  je  FooImpl.foo
  cmp [a.klass], BarImpl
  je  BarImpl.foo
  call IC_megamorphic_handler
                              = ~5~10 cycles
```

- Bimorphic (2 type): 조건부 inline 가능 (양쪽 시도).
- Polymorphic (3 type): branch table. inline 불가.

### 2.4 키워드 3 — Megamorphic (vtable, inline 불가)

```
[Megamorphic 상태]
  call vtable_dispatch_helper
  # vtable 또는 itable lookup
                              = ~10~20 cycles (cache miss 시 더)
                              + inline 불가 → 다른 최적화 효과 0
```

```
Monomorphic dispatch:
  cmp [a.klass], FooImpl   # 1 cmp
  jne miss                 # 1 branch
  jmp FooImpl.foo          # 1 direct jmp
                           = ~3 cycles + inline 가능

Megamorphic dispatch:
  load [a.klass]           # 1 load (cache miss 가능)
  load [klass + offset]    # 1 load
  jmp [function_ptr]       # 1 indirect jump (predictor 못 맞춤)
                           = ~10~20 cycles + inline 불가
                           → 실측 5~10× 차이 (cascade 효과 손실 포함)
```

**한 번 megamorphic 되면 자동 회복 안 됨** — nmethod 자체가 재컴파일되어야 회복.

### 2.5 IC의 동적 진화

```
uninitialized → first call → monomorphic
                                ↓ 다른 type 등장
                            bimorphic
                                ↓ 더 다양
                            polymorphic
                                ↓ 더 많음
                            megamorphic (vtable)
```

각 단계는 IC slot의 instruction을 patch — atomic word write로 동시 실행 안전.

위치: `src/hotspot/share/code/compiledIC.cpp`:

```cpp
void CompiledIC::set_to_monomorphic(CompiledICInfo& info) {
    NativeMovConstReg* mov = nativeMov_at(_call->instruction_address());
    mov->set_data((intptr_t) info.klass());
    NativeJump* jmp = nativeJump_at(_call->instruction_address() + offset);
    jmp->set_jump_destination(info.entry());
}
```

---

## 3. 가지 ③: HOW — Inlining 휴리스틱 6단계

### 3.1 핵심 질문

> "C2가 호출 사이트의 callee를 inline할지 결정할 때 어떤 기준을 보나요?"

### 3.2 키워드 1 — 크기 한계 (MaxInlineSize, FreqInlineSize)

```
1. B가 unsafe? (native, synchronized 일부)
   → no inline
        ↓
2. B 크기 확인
   - size ≤ MaxInlineSize (기본 35 bytes) → 무조건 inline
   - size ≤ FreqInlineSize (기본 325 bytes) + hot → inline
   - else: "too big"
```

작은 callee (getter, simple validator)는 무조건 inline. Hot 큰 callee도 inline 후보.

### 3.3 키워드 2 — 누적 한계 (DesiredMethodLimit, MaxInlineLevel)

```
3. caller A의 누적 크기 확인
   - inline 후 size ≤ DesiredMethodLimit (기본 8KB bytecode) → OK
   - 초과: "caller too big"
        ↓
4. inline 깊이 확인
   - level ≤ MaxInlineLevel (기본 9) → OK
   - 초과: "too deep"
```

깊은 inlining은 C2의 IR 노드 수 폭발 → 컴파일 시간 ↑.

### 3.4 키워드 3 — IC 상태 + Callee 종류

```
5. IC 상태 확인
   - monomorphic: 한 target → 후보 1개
   - bimorphic: 두 target → 후보 2개 (양쪽 inline 시도)
   - polymorphic+: inline 불가
        ↓
6. Type Profile + 다른 휴리스틱
   - 95% FooImpl + 5% BarImpl → "FooImpl로 가정 + uncommon trap"
     → 5% 케이스에서 deopt 트리거 (느려짐)
     → 그러나 95% 빠름이 더 큰 이득
```

위치: `src/hotspot/share/opto/bytecodeInfo.cpp` (`InlineTree`):

```cpp
InlineDecision try_to_inline(ciMethod* callee, ...) {
    if (callee->code_size() > MaxInlineSize && !is_hot(callee))
        return NOT_INLINED("too big");
    if (caller_size + callee_size > DesiredMethodLimit)
        return NOT_INLINED("caller too big");
    if (inline_depth > MaxInlineLevel)
        return NOT_INLINED("too deep");
    if (call_profile->morphism() > 2)
        return NOT_INLINED("megamorphic");
    // ...
    return INLINED("hot");
}
```

### 3.5 CHA (Class Hierarchy Analysis) — Speculation-based Inline

```
[현재 상태]
interface Foo의 구현체: FooImpl 만 로드됨

[C2 컴파일 시]
foo.method() 호출 사이트
  → CHA: "현재 Foo 구현체 1개" → monomorphic 으로 간주
  → 강제 inline (speculation)
  → 추가 최적화: constant fold, dead code 등

[새 구현체 로드 시점]
BarImpl implements Foo가 ClassLoader.defineClass로 로드
  → JVM의 CHA가 변화 감지

[Deopt 트리거]
영향받는 모든 nmethod → not_entrant
이미 실행 중인 스레드: 다음 safepoint에서 frame 변환
일시적으로 인터프리터로 회귀
```

위치: `src/hotspot/share/code/dependencies.cpp`:

```cpp
class Dependencies {
    void assert_leaf_type(ciKlass* k);
    void assert_unique_concrete_method(ciMethod* abstract, ciMethod* concrete);
};

void DependencyContext::invalidate_dependent_nmethods(...) {
    for (each nmethod with dependencies on this class hierarchy) {
        nmethod->mark_for_deoptimization();
    }
}
```

운영 의미:
- Spring AOP, Hibernate proxy, dynamic class generation이 새 클래스 추가하는 순간 deopt.
- 시작 후 dynamic class 폭주 시기에 P99 spike.
- 안정 후엔 모든 가능한 type이 IC에 등록되어 더 이상 deopt 없음.

---

## 4. 가지 ④: 운영 — 시니어 진단

### 4.1 핵심 질문

> "특정 메서드의 inline이 잘 됐는지, 어느 호출 사이트가 megamorphic인지 어떻게 확인하나요?"

### 4.2 키워드 1 — `-XX:+PrintInlining` 메시지

```bash
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining -jar app.jar
```

출력:
```
@ 5   java.lang.String::length (5 bytes)             inline (hot)
@ 12  java.lang.Integer::valueOf (32 bytes)          inline (hot)
@ 25  com.foo.expensive (200 bytes)                  too big
@ 30  com.foo.callback (50 bytes)                    polymorphic
```

각 라인: `@ N` bytecode index, 메서드, (size), 결정 + 이유.

흔한 메시지:
- `inline (hot)` — 정상.
- `too big` — callee size > Max/FreqInlineSize.
- `caller too big` — caller 누적 한계.
- `polymorphic` / `megamorphic` — IC 상태.
- `not inlineable` — native, synchronized.

### 4.3 키워드 2 — JITWatch Inline Tree

```bash
java -XX:+UnlockDiagnosticVMOptions \
     -XX:+TraceClassLoading \
     -XX:+LogCompilation \
     -jar app.jar
# hotspot_pid<n>.log 생성 → JITWatch에서 열기
```

기능: 메서드별 inline tree 시각화 — 어느 callee가 inline됐고 어느 게 막혔는지. "polymorphic — bailout" 메시지 + inline tree 단절 식별.

### 4.4 키워드 3 — Stream API / Spring AOP 함정

**Stream API의 IC 함정**:

```java
users.stream().map(User::getName).collect(...);       // Function: User → String
orders.stream().map(Order::getId).collect(...);       // Function: Order → Long
products.stream().map(Product::getCode).collect(...); // Function: Product → String
```

같은 stream API의 `map()` 안의 `Function.apply` 호출 사이트가 3가지 다른 lambda type을 받음 → **IC megamorphic**.

**Strategy 패턴의 IC**:

```java
interface PaymentProcessor { void process(Payment p); }
class CreditCardProcessor implements ... { }
class PaypalProcessor implements ... { }
class StripeProcessor implements ... { }

PaymentProcessor processor = selectProcessor(payment);
processor.process(payment);   // 구현체 3+ → megamorphic
```

해결:
- `sealed interface PaymentProcessor permits CreditCard, Paypal, Stripe` — 구현체 fix → CHA 강력.
- 또는 명시 switch 분기 (JIT 인지 쉬움).

### 4.5 JFR Inlining 이벤트

```bash
jcmd <pid> JFR.start name=inline duration=300s settings=profile
jfr summary inline.jfr | grep -iE 'Inlining|Deopt'
```

- `jdk.CompilerInlining` — inline 결정 + reason.
- `jdk.Deoptimization` — 결과 deopt (CHA 위반 등).

### 4.6 운영 시나리오 매트릭스

| 증상 | 진단 | 가능 원인 |
|---|---|---|
| 인터페이스 도입 후 응답 ↓ | PrintInlining → polymorphic/megamorphic | IC 함정 |
| Stream API 코드 느림 | JITWatch inline tree | lambda type pollution |
| Hot reload 후 P99 spike | JFR Deoptimization reason: class_check | CHA 위반 |
| 메서드가 inline 안 됨 | PrintInlining "too big" | 메서드 크기 |
| 같은 메서드 반복 deopt | jdk.Deoptimization burst | speculation 깨짐 반복 |

### 4.7 Killer 시나리오 — 인터페이스 도입 후 P99 ↑

```
환경: 직접 클래스 호출 → Strategy 패턴 리팩토링
증상: 평소 P99 30ms → 80ms

진단:
$ -XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining 2>&1 | grep "PaymentProcessor"
@ 15  com.foo.PaymentProcessor::process (50 bytes)   megamorphic   ← ★

원인: PaymentProcessor 구현체 4개 → IC megamorphic → C2 inline 불가
     → 모든 cross-method 최적화 차단 → 5~10× 느림

조치:
1. sealed interface 적용 (JDK 17+)
2. 또는 type별 명시 switch 분기 (각 case → monomorphic call site)
3. 핵심 hot path는 직접 클래스 호출 유지
```

---

## 5. 가지 ⑤: 진화

### 5.1 핵심 질문

> "Inline Cache 개념은 어디서 왔고, 현대 Java에서 어떻게 발전했나요?"

### 5.2 키워드 1 — Smalltalk-80 IC (1983)

Deutsch & Schiffman 논문:
- 동적 type 언어인데 정적 type처럼 빠르게.
- 첫 Inline Cache 도입.
- 한 type만 캐시 → monomorphic case에서 큰 가속.

### 5.3 키워드 2 — Self PIC (1991)

David Ungar의 Self language:
- Polymorphic Inline Cache (PIC) 도입 — 여러 type 캐시.
- 1, 2, 4, 8 등 여러 level의 IC 지원.
- HotSpot이 이 기법을 Java에 적용.

### 5.4 키워드 3 — Sealed Class CHA 강화 (JDK 17, 2021)

```java
sealed interface PaymentProcessor permits CreditCard, Paypal, Stripe { }
```

- 구현체 명시 → CHA가 "Foo의 구현체는 정확히 3개" 컴파일 시점에 확정.
- 새 구현체 로드 가능성 0 → speculation 더 강하게 가능.
- Pattern matching 친화.

### 5.5 역사 타임라인

| 연도 | 변화 | 의의 |
|---|---|---|
| 1983 | Smalltalk-80 IC | 개념 첫 등장 |
| 1991 | Self PIC | Polymorphic IC |
| 1999 | HotSpot 1.0 + C2 | Java에 IC + CHA |
| 2004 | JDK 5 generics + autobox | Lambda 없을 때라 IC 단순 |
| 2014 | JDK 8 Lambda + Stream | IC megamorphic 함정 등장 |
| 2018 | JDK 11 Graal | 더 정교한 inlining 휴리스틱 |
| 2021 | JDK 17 Sealed class | CHA에 도움 |
| 2023 | JDK 21 Pattern matching | type-stable dispatch |

---

## 6. 면접 답변 워크플로우

### 6.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "Inlining이 왜 중요?" | ① WHY (mother) | EA/Type sharpen cascade |
| "IC 4단계?" | ② WHAT | dispatch 비용 |
| "Megamorphic이 왜 느림?" | ② WHAT (dispatch) | ① cascade 손실 |
| "C2가 inline 결정 기준?" | ③ HOW (휴리스틱) | ② IC 상태 |
| "CHA가 뭔가요?" | ③ HOW (CHA) | Deopt 연결 |
| "Stream API 느림 원인?" | ④ 운영 (Stream 함정) | ② megamorphic |
| "sealed의 효과?" | ⑤ 진화 | ③ CHA 강화 |

### 6.2 답변 템플릿

> 루트 → 가지 키워드 3개 → 인접

예: "Inlining이 왜 'the mother of optimizations'인가요?"

> "Inlining은 callee 메서드 본문을 caller의 호출 사이트에 펼쳐 넣는 변환입니다. (← 루트)
> 단순한 호출 overhead 제거(~10ns)는 자체로 작은 이득이지만, 진짜 가치는 cascade 효과 5가지:
> 첫째, **호출 overhead 제거** — prologue/epilogue, parameter passing.
> 둘째, **Cross-method 최적화 활성화** — `bar(3)`이 inline되면 즉시 constant fold로 `4`가 됨. dead code 제거도 cross-method로.
> 셋째, **Escape Analysis 활성화** — 메서드 경계가 없어지면 객체가 escape 안 한다는 증명 가능 → Scalar Replacement.
> 넷째, **Type Sharpening** — caller의 type 정보로 callee의 instanceof/cast 제거.
> 다섯째, **Loop opts 확장** — inline된 loop에 unrolling, vectorization 적용.
> Inlining이 막히면 위 모든 효과 ↓ → 'the mother'. 그래서 IC가 megamorphic 되어 inline이 막히면 단순한 dispatch 비용 차이가 아니라 실측 5~10× 차이로 나타납니다."

---

## 7. 꼬리질문 트리 (가지별)

### Q1 [가지 ①]. Inlining이 왜 "the mother of optimizations"인가요?

> 단순한 함수 호출 펼치기지만 5가지 cascade 효과:
> 1. 호출 overhead 제거 (prologue/epilogue, parameter).
> 2. Cross-method 최적화 활성화 — constant propagation, dead code.
> 3. Escape Analysis 활성화 — 함수 경계 안에 객체 가둠 → Scalar Replacement.
> 4. Type Sharpening — caller의 type 정보로 callee의 instanceof/cast 제거.
> 5. Loop opts 확장 — inline된 loop에 unrolling, vectorization.
> Inlining 막히면 위 모든 효과 ↓ → "the mother".

### Q2 [가지 ②]. Inline Cache 4단계와 각각의 dispatch 비용 차이는?

> | 단계 | 동작 | 비용 | inline |
> |---|---|---|---|
> | Monomorphic | klass check 1번 + 직접 jump | ~3 cycles | ✅ |
> | Bimorphic | klass check 2번 + 분기 | ~5 cycles | 조건부 |
> | Polymorphic | branch table | ~7~10 cycles | ❌ |
> | Megamorphic | vtable/itable lookup | ~10~20 cycles | ❌ |
> Monomorphic ↔ Megamorphic 차이는 dispatch 자체뿐 아니라 inline 가능 여부 → cascade 효과 → 실측 5~10× 차이.

**🪝 Q2-1: 한 번 megamorphic 되면 회복 안 되나요?**
> Yes. IC의 monomorphic check 코드가 vtable dispatch stub으로 patch된 상태 — 자동 회복 안 됨. nmethod 자체가 재컴파일되어야 다시 monomorphic 가능 (그러나 같은 다양한 type이 계속 오면 다시 megamorphic).

### Q3 [가지 ③]. CHA가 무엇이고 왜 위험한가요?

> Class Hierarchy Analysis — 현재 로드된 클래스 계층을 분석해 "이 인터페이스/abstract 메서드의 구현이 N개"인지 파악.
> 활용: 현재 구현체 1개면 monomorphic으로 간주 → 강제 inline (speculation).
> 위험:
> - 새 구현체가 나중에 로드되면 CHA 가정 깨짐.
> - 영향받은 nmethod들 → deopt → 인터프리터 복귀 → 재컴파일.
> - P99 spike.
> 운영 패턴: Spring AOP/Hibernate proxy/Mockito 같은 dynamic class generation 후 deopt 폭주. Hot reload 후 deopt 폭주. 안정 후엔 IC가 모든 type 등록해 더 이상 deopt 없음.

### Q4 [가지 ④]. Stream API와 Lambda가 IC를 megamorphic으로 만드는 메커니즘은?

> `Function.apply()`, `Predicate.test()` 같은 인터페이스 메서드의 호출 사이트가 여러 lambda type을 받음 → IC megamorphic.
> 예:
> ```java
> users.stream().map(User::getName).collect(...);
> orders.stream().map(Order::getId).collect(...);
> products.stream().map(Product::getCode).collect(...);
> ```
> 같은 stream API의 map() 안 Function.apply 호출이 3가지 다른 lambda type 받음 → megamorphic.
> 결과: 각 stream pipeline 성능 ↓. Stream "느리다" 평판의 일부.
> 회피: 특정 type 위주 stream은 단일 lambda 패턴 유지. Hot path는 for-loop 또는 명시 코드.

### Q5 [가지 ④]. 메서드가 inline 안 되는 이유를 어떻게 진단하나요?

> `-XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining` 출력의 이유 메시지:
> - "inline (hot)" — 정상.
> - "too big" — callee 크기 > MaxInlineSize 또는 FreqInlineSize.
> - "caller too big" — caller 누적 크기 한계.
> - "polymorphic" / "megamorphic" — IC 상태.
> - "not inlineable" — native, synchronized.
> 해결: too big → 메서드 분할 또는 `-XX:MaxInlineSize=N` 튜닝. polymorphic+ → type pollution 해결 (sealed, 명시 분기). JITWatch로 inline tree 시각화 후 약한 부분 식별.

### Q6 [가지 ⑤]. Sealed class가 IC에 어떤 효과를 주나요?

> `sealed interface Foo permits A, B, C` — 구현체 명시.
> CHA가 더 강력 — "Foo의 구현체는 정확히 3개" 컴파일 시점에 확정.
> 새 구현체 로드 가능성 0 → speculation 더 강하게 가능.
> 또한 pattern matching 친화 — 각 case에 monomorphic call site → 모두 inline 가능.

### Q7 (Killer) [가지 ④]. Spring 앱이 Strategy 패턴 도입 후 P99가 30ms에서 100ms로 증가했습니다. 원인을 진단하고 해결하세요.

> 1. **IC 상태 확인**:
>    ```
>    -XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining
>    grep "PaymentProcessor::process" inline.log
>    # "polymorphic" 또는 "megamorphic" 확인
>    ```
> 2. **구현체 수 확인**: 코드 audit — 3+ implements → megamorphic 확정.
> 3. **JITWatch로 시각화**: PaymentProcessor.process() 호출 사이트의 inline tree. "polymorphic — bailout" + inline tree 단절.
> 4. **해결 옵션**:
>    A. **Sealed Interface (JDK 17+)**:
>       ```java
>       sealed interface PaymentProcessor permits CreditCard, Paypal, Stripe { }
>       ```
>       → CHA 강력, 일부 케이스 inline 회복.
>    B. **명시 switch 분기 (hot path)**:
>       ```java
>       switch (p.type()) {
>           case CREDIT_CARD -> creditCard.process(p);
>           case PAYPAL -> paypal.process(p);
>           ...
>       }
>       ```
>       → 각 case가 monomorphic call site → 모두 inline.
>    C. **Hot path 별도 처리**: 95% traffic이 CreditCard면 그 경우는 직접 호출.
> 5. **검증**: 변경 후 PrintInlining 다시 → "inline (hot)". 부하 테스트 → P99 회복.

---

## 8. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 이내로 그릴 수 있다 (루트 + 5가지 + 키워드 3개)
- [ ] 가지 ① WHY: Inlining의 5가지 cascade 효과 외운다 (호출/CMO/EA/TypeSharp/Loop)
- [ ] 가지 ② WHAT: IC 4단계 표 (Mono ~3cy/Bi-Poly/Mega ~10-20cy) 그린다
- [ ] 가지 ② WHAT: Mono → Mega 전이는 자동 회복 불가 — 설명한다
- [ ] 가지 ③ HOW: 6단계 휴리스틱 (unsafe/size/누적/depth/IC/profile) 말한다
- [ ] 가지 ③ HOW: CHA + deopt 연결고리 (Spring AOP, hot reload) 설명한다
- [ ] 가지 ④ 운영: PrintInlining 메시지 4종 해석한다
- [ ] 가지 ④ 운영: Strategy 패턴 P99 ↑ 진단 절차 5단계 말한다
- [ ] 가지 ⑤ 진화: Smalltalk(1983) → Self(1991) → HotSpot → Sealed(2021) 흐름 말한다
- [ ] 7장 꼬리질문 7개에 막힘없이 답한다

---

## 다음 단계

- → [06. Escape Analysis](./06-escape-analysis.md): Inline의 cascade 효과 중 EA + Scalar Replacement
- → [07. Loop and Vector](./07-loop-and-vector.md): Inline의 cascade 효과 중 loop opts
- → [08. Speculative and Deopt](./08-speculative-and-deopt.md): CHA 위반 → Deopt 풀버전
- ← [04. C1 and C2](./04-c1-and-c2.md): C2 phase 안에서 inlining 위치

## 참고

- **Deutsch & Schiffman — Smalltalk-80 IC**: 1983 논문
- **David Ungar — Self PIC**: 1991 박사 논문
- **HotSpot src `bytecodeInfo.cpp` (InlineTree)**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/opto/bytecodeInfo.cpp
- **HotSpot src `compiledIC.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/code/compiledIC.cpp
- **HotSpot src `dependencies.cpp` (CHA)**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/code/dependencies.cpp
- **JITWatch — Inline Tree Viewer**: https://github.com/AdoptOpenJDK/jitwatch
- **Aleksey Shipilëv — Inlining Anatomy**: https://shipilev.net/jvm/anatomy-quarks/
- **Brian Goetz — JEP 360 sealed**: https://openjdk.org/jeps/360
