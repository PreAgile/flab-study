# 03-08. Speculative Optimization + Deoptimization

> C2의 모든 공격적 최적화는 **speculation (가정)** 위에 세워진다. CHA로 monomorphic 가정, type profile로 receiver 가정, branch profile로 분기 가정, RCE로 range 가정.
> 가정이 **항상 맞다고 보장 못 함**. 안전판이 **Deoptimization** — 가정 깨지면 native code 폐기 + 인터프리터 복귀 + 재컴파일.
> 시니어가 알아야 할 것: P99 spike의 가장 흔한 원인이 deopt다. JFR `jdk.Deoptimization` 이벤트의 `reason`을 읽고 코드 어디서 가정이 깨지는지 짚어낼 수 있어야 한다.

---

## 이 문서의 사용법

1. **0장 마인드맵을 먼저 외운다** — 루트 + 5가지 + 키워드.
2. **1~5장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 대응.
3. **6장 면접 워크플로우**, **7장 꼬리질문**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"Speculation은 'almost always true' 가정으로 공격적 최적화, Uncommon Trap은 안전판이다. 깨지면 Deopt 4단계 — 위반 감지 → not_entrant → vframe 변환 (Native frame을 Interpreter frame으로) → 인터프리터 재개. 같은 메서드+reason이 4번 반복되면 make_not_compilable — P99 영구 spike의 근본 원인."**

### 5개 가지 — 순서를 외운다

```
              [ROOT: Speculation + Uncommon Trap + Deopt 4단계 + make_not_compilable]
                                  │
       ┌──────────────┬───────────┼───────────┬──────────────┐
       │              │           │           │              │
      ① WHY         ② WHAT       ③ HOW       ④ 운영        ⑤ OSR vs
   왜 speculation    Speculation  Deopt 4단계 (시니어       Deopt 비교
   이 필수?         4종 + Trap    + vframe    진단)
                                  변환
       │              │           │           │              │
       │         ┌────┼────┐  ┌───┼───┐  ┌────┼────┐         │
   동적 dispatch CHA   Type    위반→     JFR    Per     OSR:   Deopt:
   비용 회피/   /Branch/Null/  not_entrant jdk.  Method  Int→  Native→
   peak 성능    Range          → vframe   Deopt  Trap    Native Int
   /Deopt 안전판/Uncommon       → 인터프   imization Limit  Loop  가정
   /Self 원조   Trap             리터      reason  =100    진입  깨짐
                                                            +       +
                                                            ScopeDesc
```

### 가지별 핵심 키워드 (각 가지 3개씩만)

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① WHY** | 동적 dispatch 비용 회피 | peak 성능의 기반 | Deopt가 정확성 안전판 |
| **② WHAT 4종 + Trap** | CHA / Type / Branch / Null+Range | Uncommon Trap (native code 안 stub) | profile-guided speculation |
| **③ HOW 4단계** | 위반 감지 + not_entrant | vframe 변환 (ScopeDesc + OopMap) | 인터프리터 재개 |
| **④ 운영** | JFR `jdk.Deoptimization` reason | `made not entrant` 로그 | PerMethodTrapLimit + make_not_compilable |
| **⑤ OSR vs Deopt** | OSR: Int → Native (가속) | Deopt: Native → Int (감속) | 공통: stack frame 변환 |

### 면접 답변 흐름

> 면접관 질문 → 루트 → 가지 → 키워드 3개 → 인접

---

## 1. 가지 ①: WHY — 왜 Speculation이 필수인가

### 1.1 핵심 질문

> "C2가 가정 없이 정직하게만 컴파일하면 안 되나요? Speculation의 위험을 감수하면서 왜 쓰나요?"

### 1.2 키워드 1 — 동적 Dispatch 비용 회피

```
[Speculation 없으면]
모든 메서드 호출:
  - vtable lookup (1 indirect load)
  - indirect call (branch predictor 못 맞춤)
  - 매번 type check, null check, range check
  → 단순 dispatch에 ~20 cycles

[Speculation 있으면 (monomorphic 가정)]
호출:
  - klass check 1번
  - 직접 jump
  - 추가로 inline → cross-method 최적화
  → ~3 cycles + 큰 후속 이득
```

→ Speculation 없으면 Java가 인터프리티드 언어 수준. **Speculation + Deopt가 Java peak 성능의 핵심**.

### 1.3 키워드 2 — Peak 성능의 기반

Speculation 4가지를 합쳐서:
- CHA로 monomorphic 가정 → inline.
- Type profile로 receiver 가정 → vtable 제거.
- Branch profile로 분기 가정 → uncommon path 분리.
- RCE로 range 가정 → bound check 제거.

각각이 단독으로는 작은 이득이지만 합쳐지면 **인터프리터 대비 50~100× peak 성능**.

### 1.4 키워드 3 — Deopt가 정확성 안전판

```
Speculation 한 번 깨졌을 때:
  - 깨진 곳 어느 native frame이든 안전하게 인터프리터로 전이.
  - 사용자 코드 결과는 정확 (gradient 없음).
  - 단지 그 호출 한 번이 느림.
  - 시간 지나 재컴파일 → 다시 빨라짐.

→ "최악의 경우에도 정확성 보장 + 임시 성능 저하"
→ 그래서 C2가 매우 공격적인 speculation 가능
```

Deopt가 없으면 잘못된 native code가 잘못된 결과 → 사용자 데이터 손상. **Deopt가 안전판이라 적극적 speculation 가능**.

### 1.5 비유로 굳히기

> **시험 답안지 비유**: Speculation = "이 문제는 항상 A가 답"이라 외워두고 채점 시간 절약. Uncommon trap = "혹시 B나 C가 나오면 정식 풀이로" 안전판. Deopt = B/C가 나옴 → 외운 답 폐기 + 처음부터 정식 풀이 (인터프리터 복귀). make_not_compilable = "이 문제는 답이 너무 자주 바뀌니까 외우지 말고 영원히 정식 풀이로" → 영원히 느림.

---

## 2. 가지 ②: WHAT — Speculation 4종 + Uncommon Trap

### 2.1 핵심 질문

> "C2가 활용하는 speculation 종류는 무엇이고, 깨지면 어떻게 진입하나요?"

### 2.2 키워드 1 — Speculation 4종

**1. CHA-based (Class Hierarchy Analysis)**:
```java
interface Foo { void method(); }
class FooImpl implements Foo { void method() { ... } }

foo.method();   // CHA: "현재 Foo 구현체 1개" → monomorphic 가정 → inline
                // → 새 BarImpl 로드 시 CHA 위반 → deopt
```

**2. Type Profile**:
```java
void process(Object obj) {
    String s = (String) obj;   // MDO: 95% String, 5% StringBuilder
    use(s);
}
// C2: "95% String"으로 speculation + uncommon trap
// → 5% StringBuilder 도달 시 deopt
```

**3. Branch Profile**:
```java
void check(int x) {
    if (x > 0) {   // 99% true (profile)
        normalPath(x);
    } else {
        errorPath();   // uncommon path로
    }
}
// false 케이스 도달 시 deopt 트리거
```

**4. Null check / Range check**:
```java
for (int i = 0; i < n; i++) {
    sum += arr[i];   // RCE: n <= arr.length 가정
}
// loop 시작 전 predicate hoisting
// 가정 깨지면 (out of bounds) uncommon trap → deopt
```

### 2.3 키워드 2 — Uncommon Trap

```
[C2 컴파일된 함수의 모습]

normal_path_code:
   ; 자주 실행되는 hot path
   ...
   jmp end

uncommon_path:
   ; 거의 안 실행되는 cold path
   call deoptimize_handler   ; deopt trigger
```

Uncommon trap은 nmethod 내부에 작은 stub. 호출되면 deopt 진행. 평소엔 fall-through 안 됨 (branch predictor가 "절대 안 감"으로 학습).

### 2.4 키워드 3 — Profile-Guided Speculation

```
호출 사이트 A의 IC를 컴파일 시 확인:
  profile (MDO)에 receiver type 히스토그램 있음
  예: [FooImpl: 9800회, BarImpl: 200회]
  
C2 결정:
  - 100% monomorphic (FooImpl만) → 무조건 inline
  - 98% FooImpl + 2% BarImpl → "FooImpl 가정 + uncommon trap"으로 inline
    → 2% BarImpl 케이스에서 deopt 트리거
    → 그러나 98% 빠름이 더 큰 이득
  - 50/50 → bimorphic, 양쪽 inline 시도
  - 다양 → polymorphic 또는 megamorphic (speculation 불가)
```

이게 **type profile guided inlining**의 핵심.

### 2.5 Deopt Reason 주요 5가지

| Reason | 의미 |
|---|---|
| `unstable_if` | branch profile 가정 깨짐 (95% true → 자주 false) |
| `class_check` | CHA 위반 (새 구현체 등장) |
| `unreached` | 도달 안 함 표시 path 도달 |
| `null_check` | null 아님 가정 깨짐 |
| `range_check` | RCE 가정 깨짐 (out of bounds) |

JFR `jdk.Deoptimization` 이벤트의 `reason` 필드.

---

## 3. 가지 ③: HOW — Deopt 4단계 + vframe 변환

### 3.1 핵심 질문

> "Speculation이 깨졌을 때 정확히 어떤 단계로 native code가 폐기되고 인터프리터로 돌아가나요?"

### 3.2 키워드 1 — 위반 감지 + not_entrant

```
1. 가정 위반 감지
   - Uncommon trap 도달
   - 또는 새 클래스 로드로 CHA 위반
   - 또는 다른 메커니즘
        ↓
2. 영향받는 nmethod에 not_entrant 플래그 set
   - 다음 호출은 인터프리터로
   - 이미 실행 중인 스레드는 여전히 native code 실행
```

위치: `src/hotspot/share/runtime/deoptimization.cpp`:

```cpp
JRT_ENTRY(void, Deoptimization::uncommon_trap(JavaThread* thread, jint trap_request)) {
    DeoptReason reason = trap_request_reason(trap_request);
    DeoptAction action = trap_request_action(trap_request);
    
    nmethod* nm = ...;
    if (action == Action::make_not_entrant) {
        nm->make_not_entrant();
    }
    // ...
}
```

### 3.3 키워드 2 — vframe 변환 (ScopeDesc + OopMap)

```
[Native frame의 정보]
- 현재 PC (native instruction pointer)
- Register 값들
- Stack slot 값들

[변환에 필요한 정보 3종]
1. OopMap: 어느 register/stack slot이 oop인지 — GC가 안전하게 처리
2. ScopeDesc: 그 native PC가 어느 메서드의 어느 bytecode index인지
3. Local variable / operand stack의 위치 정보

[변환 과정]
1. Native frame의 PC를 ScopeDesc로 해석
   → "메서드 M의 bytecode index 42"
2. ScopeDesc가 알려주는 위치에서 local/operand 값 추출
3. Interpreter frame 새로 만들기 (max_locals + max_stack 크기)
4. 추출한 값들을 interpreter slot에 복원
5. PC를 bytecode index 42로 설정
```

**Inlined 메서드의 deopt — Nested vframe**:
```
[Caller가 callee를 inline해서 한 nmethod로 컴파일]
caller_method() {
    callee_method() {   // ← inline됨
        deopt 트리거    // 여기서 deopt
    }
}

[Deopt 결과]
- 한 native frame → 두 interpreter frame
- 깊이 N 만큼 inline됐으면 N개 frame 생성
```

→ 깊은 inline 후 deopt는 매우 비싼 작업. Deopt 비용이 단순 "느려짐" 이상.

위치: `src/hotspot/share/runtime/vframeArray.hpp`:

```cpp
class vframeArray : public CHeapObj<mtCompiler> {
    int _frames;                    // inline 깊이
    vframeArrayElement _elements[]; // 각 inline level
};

class vframeArrayElement {
    Method* _method;
    int _bci;
    StackValueCollection* _locals;
    StackValueCollection* _expressions;
};
```

### 3.4 키워드 3 — 인터프리터 재개

```
3. Interpreter frame 설치
   - Stack 위에서 native frame을 unwind
   - Interpreter frame들을 push
        ↓
4. 인터프리터 entry로 jump
   - PC를 bytecode index로 설정
   - 인터프리터가 그 위치부터 실행 재개
   - MDO 갱신 (profile 재수집)
        ↓
5. 시간 지나 재컴파일
   - 같은 reason이 N번 반복되면 make_not_compilable
```

### 3.5 Deopt Action 결정

```
make_not_entrant: 옛 nmethod 즉시 폐기. 다음 호출은 인터프리터.
maybe_recompile: 일정 시간 후 profile 재수집 후 재컴파일.
reinterpret: 한동안 인터프리터로만, 그 후 재시도.
make_not_compilable: ★ 영원히 컴파일 안 함.

결정 알고리즘:
  - 같은 메서드 + 같은 reason의 deopt 횟수 카운트.
  - N번 (기본 4) 도달 → make_not_compilable.
  - 메서드별 별도 카운트.
```

옵션:
- `-XX:PerMethodTrapLimit=N` (기본 100) — 메서드별 trap 한계.
- `-XX:PerBytecodeTrapLimit=N` (기본 4) — bytecode 위치별 trap 한계.

---

## 4. 가지 ④: 운영 — 시니어 진단

### 4.1 핵심 질문

> "P99 spike가 deopt인지, 영구 느려짐이 make_not_compilable인지 어떻게 진단하나요?"

### 4.2 키워드 1 — JFR `jdk.Deoptimization` Reason

```bash
jcmd <pid> JFR.start name=deopt duration=300s settings=profile filename=deopt.jfr
jfr print --events jdk.Deoptimization deopt.jfr | head -30
```

각 이벤트:
- `compileId` — 어느 nmethod.
- `method` — 어느 메서드.
- `bci` — bytecode index.
- `reason` — unstable_if 등.
- `action` — make_not_entrant 등.

분석:
- 시간순 burst → speculation 깨짐 burst.
- 같은 메서드 + 같은 reason 반복 → make_not_compilable 위험.

### 4.3 키워드 2 — `-XX:+PrintCompilation`의 `made not entrant`

```
2100    5       4 made not entrant   MyApp::hotMethod (50 bytes)
2105    6       4               MyApp::hotMethod (50 bytes)   ← 즉시 재컴파일
```

- `made not entrant` = 옛 nmethod 폐기.
- 그 직후 새 컴파일 시도면 정상.
- 같은 메서드의 not_entrant 빈도 ↑ = 반복 deopt 의심.

**`made not compilable`** 메시지 검색:
```bash
$ grep "made not compilable" hotspot.log
"PaymentService::process made not compilable: too many deopts"
```

이 메시지 보이면 영구 인터프리터 — JVM 재시작 외 회복 안 됨.

### 4.4 키워드 3 — PerMethodTrapLimit + make_not_compilable

```
시나리오:
  메서드 M에 대해 C2 컴파일 → speculation X → 깨짐 → deopt → 재컴파일
                                              → speculation X' → 깨짐 → deopt → ...
                                              
N번 (기본 4번) 반복 후:
  Action::make_not_compilable
  → M은 영원히 인터프리터
  → 그 메서드를 거치는 모든 traffic이 5~10× 느림
```

운영자 관점:
- 같은 메서드의 deopt가 자주 보이면 즉시 조사.
- 코드 audit 또는 `-XX:CompileCommand=exclude`로 임시 회피.
- 근본 원인: speculation이 신뢰성 없는 코드 패턴 (dynamic proxy, type pollution).

회복: **JVM 재시작 (카운터 초기화)**.

### 4.5 운영 시나리오 매트릭스

| 증상 | 진단 | 가능 원인 |
|---|---|---|
| P99 spike, 단발 | JFR deopt burst | speculation 깨짐 (정상 복구) |
| P99 영구 ↑ | `make_not_compilable` 메서드 | 반복 deopt 한계 도달 |
| 특정 메서드 영원히 느림 | `-XX:+PrintCompilation`에서 컴파일 없음 | not_compilable |
| Hot reload 후 deopt 폭주 | JFR reason: class_check | CHA 위반 |
| Stream API 코드 deopt | reason: unstable_if 또는 class_check | type pollution |

### 4.6 시나리오 1: P99 영구 spike — make_not_compilable

```
환경: Spring 앱, 어느 시점부터 특정 endpoint P99 영구 200ms (정상 30ms)
증상: 평소 빠르던 메서드가 5× 느려진 채로 회복 안 됨

진단:
$ -XX:+PrintCompilation 로그 검색
"PaymentService::process made not compilable: too many deopts"   ← ★

$ JFR jdk.Deoptimization 시간순:
2024-01-15 10:00:01  reason=class_check  count=1
2024-01-15 10:00:02  reason=class_check  count=2
2024-01-15 10:00:03  reason=class_check  count=3
2024-01-15 10:00:04  reason=class_check  count=4 → make_not_compilable

원인: dynamic class loading이 CHA 의존성을 자주 깸 (Spring AOP proxy 등)

조치:
1. 코드 audit: dynamic proxy 사용량 ↓
2. -XX:PerMethodTrapLimit=200 (한계 ↑, 더 인내)
3. JVM 재시작 — make_not_compilable 카운터 초기화
4. 근본: 안정적 코드 패턴 (sealed interface, 명시 분기)
```

### 4.7 시나리오 2: 단발 P99 spike — 정상 deopt

```
환경: 정상 운영 중 5분에 1번씩 P99 spike
증상: 평소 50ms, spike 시 500ms, 단발

진단:
JFR jdk.Deoptimization:
   spike 시점에 burst (10~50 deopt)
   reason: unstable_if 다양
   action: maybe_recompile

원인: 정상 speculation 깨짐. 시간 지나 재컴파일하면서 일시적 느림.

조치: 
- 보통 정상. 무시 가능.
- 빈도 ↑ 시: 코드 audit (branch instability).
- Latency-critical이면: warmup 시간 ↑ 또는 sealed interface로 안정화.
```

---

## 5. 가지 ⑤: OSR vs Deopt 비교

### 5.1 핵심 질문

> "OSR과 Deopt는 둘 다 stack 위에서 frame을 변환하는데, 어떻게 다른가요?"

### 5.2 키워드 1 — OSR: Interpreter → Native (가속)

```
[Interpreter 실행 중, loop hot]
  for (int i = 0; i < 1e9; i++) ...
  ↓ back-edge counter 임계 도달
[OSR variant 컴파일]
  특정 bytecode index에서 진입 가능한 nmethod
  ↓
[Interpreter frame → Native frame 변환]
  local/operand stack 값을 native register/stack에 mapping
  ↓
Loop 나머지를 native로 실행
```

방향: **Interpreter → Native** (가속).
트리거: Loop back-edge counter.
성능: slow → fast.

### 5.3 키워드 2 — Deopt: Native → Interpreter (감속)

```
[Native code 실행 중, speculation 깨짐]
  uncommon trap 도달 또는 CHA 위반
  ↓
[Native frame → Interpreter frame 변환]
  ScopeDesc + OopMap으로 register/stack 값 해석
  ↓
인터프리터 재개 + profile 재수집 + 재컴파일
```

방향: **Native → Interpreter** (감속).
트리거: Speculation 위반.
성능: fast → slow.

### 5.4 키워드 3 — 공통: Stack Frame 변환

| | OSR | Deopt |
|---|---|---|
| 방향 | Interpreter → Native | Native → Interpreter |
| 트리거 | Loop back-edge 카운터 | Speculation 위반 |
| Frame 변환 | Interpreter → Native | Native → Interpreter |
| 빈도 | 긴 loop 진입 시 1회 | 가정 깨질 때마다 |
| 성능 영향 | 가속 (slow → fast) | 감속 (fast → slow) |

**공통**: ScopeDesc / OopMap 사용. Local/operand stack 값 보존. HotSpot이 stack 위의 frame을 통째 다른 형태로 바꾸는 가장 정교한 메커니즘.

### 5.5 역사

| 연도 | 변화 | 의의 |
|---|---|---|
| 1991 | Self language — first deopt | Speculation + deopt의 원조 |
| 1992 | Hölzle, Chambers, Ungar 논문 | Type inference + Deopt |
| 1999 | HotSpot 1.0 — C2 deopt | Java 적용 |
| 2008 | JDK 6 — uncommon trap 정교화 | reason 분류 |
| 2014 | JDK 8 — Tiered + 다양한 speculation | C1→C2 deopt 흐름 |
| 2020 | JDK 14 — Helpful NullPointerException | null_check deopt 정보 개선 |
| 2023 | JDK 21 — deopt 정보 더 풍부 | 디버깅 개선 |

David Ungar의 Self (1991)가 speculation + deopt의 원조. 동적 type 언어인데 정적 type처럼 빠르게 — Polymorphic Inline Cache + Type-aware compilation + Deopt. HotSpot이 이 기법을 Java에 적용.

---

## 6. 면접 답변 워크플로우

### 6.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "Deopt가 뭔가요?" | ① WHY (안전판) | ③ HOW 4단계 |
| "Speculation 종류?" | ② WHAT | ③ HOW vframe |
| "Uncommon Trap?" | ② WHAT (trap) | ① 안전판 |
| "Deopt 어떻게 동작?" | ③ HOW (4단계) | ④ 운영 진단 |
| "vframe 변환?" | ③ HOW | ScopeDesc + OopMap |
| "make_not_compilable이 뭔가요?" | ④ 운영 | ⑤ OSR 비교 |
| "P99 영구 spike 진단" | ④ Killer | ⑤ |
| "OSR과 Deopt 차이?" | ⑤ 비교 | ③ frame 변환 공통 |

### 6.2 답변 템플릿

> 루트 → 가지 키워드 3개 → 인접

예: "Deopt가 일어나면 정확히 무슨 일이 일어나나요?"

> "Deopt는 C2의 speculation 가정이 깨졌을 때 native code를 폐기하고 인터프리터로 복귀하는 메커니즘입니다. (← 루트)
> 4단계로 일어납니다.
> 첫째, **위반 감지**: uncommon trap 도달 또는 새 클래스 로드로 CHA 위반.
> 둘째, **not_entrant 표시**: 영향받는 nmethod에 플래그 set → 다음 호출은 인터프리터로. 이미 실행 중인 스레드는 다음 safepoint에서 처리.
> 셋째, **vframe 변환**: Native frame의 PC를 ScopeDesc로 해석해 "메서드 M의 bytecode index N"으로 변환. OopMap으로 register/stack의 어느 slot이 oop인지 식별. Local/operand stack 값을 추출해 새 Interpreter frame slot에 복원. Inline됐던 메서드는 inline 깊이만큼 여러 Interpreter frame 생성.
> 넷째, **인터프리터 재개**: PC를 bytecode index로 설정 후 인터프리터가 그 위치부터 실행. MDO 갱신, 시간 지나 재컴파일.
> 위험: 같은 메서드 + 같은 reason이 4번 반복되면 `make_not_compilable` 발동 → 영원히 인터프리터 → P99 영구 spike. 회복은 JVM 재시작뿐."

---

## 7. 꼬리질문 트리 (가지별)

### Q1 [가지 ①]. Deopt가 무엇이고 왜 필요한가요?

> C2의 speculation 가정이 깨졌을 때 native code 폐기 + 인터프리터 복귀.
> 필요 이유: C2는 매우 공격적으로 speculation. 가정 깨질 가능성 항상 있음. Deopt가 없으면 잘못된 native code 실행 → 정확성 위반.
> Deopt가 안전판이라 C2가 적극적으로 가정 가능 → peak 성능. **Deopt가 없으면 speculation 자체가 불가능**.

### Q2 [가지 ③]. Native frame을 interpreter frame으로 어떻게 변환하나요?

> 핵심: **vframe + ScopeDesc + OopMap**.
> 1. ScopeDesc로 현재 native PC가 어느 메서드의 어느 bytecode index인지 파악.
> 2. OopMap으로 register/stack의 어느 slot이 oop인지 식별.
> 3. ScopeDesc의 local/expression value 위치 정보로 값 추출.
> 4. Interpreter frame 새로 만들고 local/operand stack에 복원.
> 5. PC를 bytecode index로 설정 후 인터프리터 재개.
> Inlined 메서드 안에서 deopt 시 inline 깊이만큼 interpreter frame 여러 개 생성.

### Q3 [가지 ②]. Deopt reason 주요 5가지를 알려주세요.

> 1. **unstable_if** — branch profile 가정 깨짐 (95% true → 자주 false).
> 2. **class_check** — CHA 위반 (새 구현체 등장).
> 3. **unreached** — 도달 안 함 표시 path 도달.
> 4. **null_check** — null 아님 가정 깨짐.
> 5. **range_check** — RCE 가정 깨짐 (out of bounds).
> JFR `jdk.Deoptimization` 이벤트의 `reason` 필드.

### Q4 [가지 ④]. make_not_compilable이 무엇이고 운영에서 왜 위험한가요?

> 같은 메서드 + 같은 reason으로 반복 deopt 시 발동 (기본 4번).
> 효과: **영원히 인터프리터로만 실행**. 재컴파일 시도 안 함.
> 결과: 그 메서드의 모든 호출이 5~10× 느림 → P99 영구 spike.
> 회복: JVM 재시작 (카운터 초기화).
> 근본 원인: 코드 패턴이 speculation 신뢰성 없음 — dynamic proxy 빈번, type pollution 등.

### Q5 [가지 ⑤]. OSR과 Deopt의 차이는?

> 둘 다 **stack 위에서 frame을 변환**하는 정교한 메커니즘. 방향이 반대:
> - **OSR**: Interpreter → Native. Long loop의 hot 진입. 가속.
> - **Deopt**: Native → Interpreter. Speculation 위반. 감속.
> 공통: ScopeDesc / OopMap 사용. Local/operand stack 값 보존. HotSpot의 stack 위 frame 변환 메커니즘의 두 방향.

### Q6 (Killer) [가지 ④]. 운영 중 어느 endpoint의 P99가 갑자기 영구히 5× 증가했습니다. 어떻게 진단하시겠어요?

> 1. **Compilation 상태 확인**:
>    ```
>    -XX:+PrintCompilation 로그 grep 그 메서드
>    "made not compilable" 메시지 찾기
>    ```
>    있다면 → make_not_compilable 발동.
> 2. **Deopt history**:
>    ```
>    JFR jdk.Deoptimization 이벤트 그 메서드 검색
>    reason 분포 + 시간순 추세
>    ```
> 3. **원인 분류**:
>    - class_check 다수 → 새 구현체 dynamic load.
>    - unstable_if 다수 → branch profile 부정확.
>    - null_check 다수 → null 분포 변화.
> 4. **단기 조치**:
>    - JVM 재시작 (make_not_compilable 초기화).
>    - `-XX:PerMethodTrapLimit=200` (한계 ↑).
> 5. **장기 조치**:
>    - 코드 audit (dynamic proxy 줄이기, sealed interface, branch stability).
>    - 부하 환경 변화 추적 (입력 type 분포 변화).

**🪝 Q6-1: Deopt 자체를 모니터링 지표로 두려면?**
> Prometheus + JMX 또는 JFR streaming:
> - `jvm.deoptimization.count` — 누적 deopt 수.
> - 분당 deopt rate 추세.
> - 알람: 분당 100+ deopt 또는 같은 메서드 분당 10+ deopt.
> JFR continuous recording — 24/7 deopt 이벤트 수집 후 사후 분석.

### Q7 [가지 ②]. Type Profile guided inlining이란?

> 호출 사이트 A의 IC를 컴파일 시 MDO의 receiver type 히스토그램 확인 (예: [FooImpl: 9800회, BarImpl: 200회]).
> C2 결정:
> - 100% monomorphic → 무조건 inline.
> - 98% + 2% → "98% type 가정 + uncommon trap"으로 inline. 2% 케이스에서 deopt.
> - 50/50 → bimorphic, 양쪽 inline 시도.
> - 다양 → polymorphic/megamorphic (speculation 불가).
> 핵심: **profile이 부정확하면 deopt 빈발**. 인터프리터 + C1 단계에서 profile 충분히 수집 후 C2가 결정.

---

## 8. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 이내로 그릴 수 있다 (루트 + 5가지 + 키워드 3개)
- [ ] 가지 ① WHY: Deopt가 정확성 안전판 + speculation 가능 조건 설명한다
- [ ] 가지 ② WHAT: Speculation 4종 (CHA/Type/Branch/Null+Range) 코드 예시 든다
- [ ] 가지 ② WHAT: Uncommon Trap이 nmethod 안 stub인 구조 그린다
- [ ] 가지 ② WHAT: Deopt reason 5가지 (unstable_if/class_check/unreached/null_check/range_check) 외운다
- [ ] 가지 ③ HOW: Deopt 4단계 (감지 → not_entrant → vframe 변환 → 인터프리터 재개) 말한다
- [ ] 가지 ③ HOW: vframe 변환 3요소 (ScopeDesc, OopMap, value 위치) 설명한다
- [ ] 가지 ③ HOW: Inlined 메서드 deopt가 여러 interpreter frame 생성 그린다
- [ ] 가지 ④ 운영: P99 영구 spike → make_not_compilable 진단 절차 5단계 말한다
- [ ] 가지 ④ 운영: 단발 spike vs 영구 spike 구분 기준 (Action) 설명한다
- [ ] 가지 ⑤ OSR vs Deopt: 방향, 트리거, 성능 영향 표 그린다
- [ ] 7장 꼬리질문 7개에 막힘없이 답한다

---

## 다음 단계

03-execution-engine 챕터 종료. 다음 챕터로:
- → [Chapter 04. GC](../04-gc/): Memory management
- → [Chapter 05. Threading](../05-threading/): JMM, Memory Barriers
- → [Chapter 07. HotSpot Internals](../07-hotspot-internals/): C2 phase 풀버전 + Sea-of-Nodes 노드들

## 참고

- **HotSpot src `deoptimization.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/deoptimization.cpp
- **HotSpot src `vframeArray.hpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/vframeArray.hpp
- **HotSpot src `scopeDesc.hpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/code/scopeDesc.hpp
- **Hölzle, Chambers, Ungar — Type Inference / Deopt 논문 (1992)**: Self language
- **Aleksey Shipilëv — Deopt anatomy**: https://shipilev.net/jvm/anatomy-quarks/
