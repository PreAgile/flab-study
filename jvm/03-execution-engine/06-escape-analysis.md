# 03-06. Escape Analysis — 객체가 메서드 밖으로 나가나?

> "Java는 모든 객체가 Heap에 할당된다" — 한 줄 답은 절반 거짓이다.
> C2가 **Escape Analysis (EA)** 로 "이 객체는 메서드 밖으로 escape하지 않음"을 증명하면, **객체 자체가 만들어지지 않을 수도 있다** — field들을 register로 분해 (Scalar Replacement). Heap allocation 0회, GC 부담 0, 동기화 무시 (Lock Elision).
> 즉, Java도 사실상 stack allocation 효과를 얻는다 — 단, EA가 성공한 경우만.
> 시니어가 알아야 할 것: 단순해 보이는 코드가 EA 덕분에 매우 빠른 이유와, 한 줄만 바꿔도 EA가 깨져 갑자기 GC가 폭증하는 패턴.

---

## 이 문서의 사용법

1. **0장 마인드맵을 먼저 외운다** — 루트 + 4가지 + 키워드.
2. **1~4장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 대응.
3. **5장 면접 워크플로우**, **6장 꼬리질문**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"Escape Analysis는 객체 reference가 메서드 밖으로 escape하는지 분석한다. NoEscape면 Scalar Replacement (객체 안 만듦 + field를 register로) + Lock Elision (synchronized 제거) + Lock Coarsening. Inlining이 메서드 경계를 없애 EA의 정확도를 폭증시킨다 — '실효적 stack allocation'의 핵심."**

### 4개 가지 — 순서를 외운다

```
              [ROOT: 객체 escape 여부에 따른 3-tier 최적화]
                                  │
       ┌──────────────┬───────────┼───────────┬──────────────┐
       │              │           │           │              │
      ① WHY         ② WHAT        ③ HOW       ④ 운영
   왜 EA가          3 escape      Connection  (시니어
   결정적인가?      종류 + 3      Graph +     진단)
                    최적화        Inline의 역할
       │              │           │           │
       │         ┌────┼────┐  ┌───┼───┐  ┌────┼────┐
   Allocation    NoEscape     알고리즘   PrintEscape  EA  GlobalEscape
   비용 zero/    ArgEscape    (Choi 1999) Analysis   깨짐 패턴
   GC 부담 zero/ GlobalEscape  ↓                       (List.add,
   Stack 효과    + Scalar/    Inlining             /JFR  exception,
                 Lock Elide/   enabler           alloc  lambda
                 Coarsen                                 capture)
```

### 가지별 핵심 키워드 (각 가지 3개씩만)

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① WHY 결정적** | Allocation 비용 zero | GC 부담 zero | "implicit stack allocation" |
| **② WHAT 3종 + 3최적화** | NoEscape / ArgEscape / GlobalEscape | Scalar Replacement | Lock Elision + Lock Coarsening |
| **③ HOW 알고리즘** | Connection Graph (Choi 1999) | Escape state propagation fixpoint | Inlining이 EA enabler |
| **④ 운영** | -XX:+PrintEscapeAnalysis | JFR allocation rate | EA 깨짐 패턴 (add/exception/lambda) |

### 면접 답변 흐름

> 면접관 질문 → 루트 → 가지 → 키워드 3개 → 인접

---

## 1. 가지 ①: WHY — 왜 EA가 결정적인가

### 1.1 핵심 질문

> "Java는 객체를 Heap에 만든다는데, EA가 왜 그렇게 중요한가요? 작은 객체 하나 만드는 비용이 그렇게 큰가요?"

### 1.2 키워드 1 — Allocation 비용 Zero

```
[일반 객체 할당의 비용 (TLAB fast path 기준)]
1. TLAB top pointer 증가 (~3 instruction)
2. Heap에서 객체 메모리 zeroing
3. Object header 초기화 (Mark Word + Klass Pointer)
4. 생성자 코드 실행
   → fast path 총 ~10~20 instruction

[Scalar Replacement 후]
0. 아무것도 안 함. field 값이 register에 직접 들어감.
   → 0 instruction
```

→ Fast path도 absolutely 0보다는 비쌈. 매 호출마다 작은 객체를 만드는 hot loop라면, EA의 누적 효과 큼.

### 1.3 키워드 2 — GC 부담 Zero

```
[객체가 만들어지면]
- GC가 추후 추적해야 함
- Card Table에 표시 (write barrier 영향)
- Young Gen 채워지면 Minor GC 빈도 ↑
- GC pause 증가

[Scalar Replacement 후]
- 객체 자체가 없음 → GC 추적 대상 0
- Allocation rate 0 → Minor GC 부담 0
```

→ EA가 GC pause를 줄이는 가장 강력한 메커니즘. 한 줄 코드 변경으로 EA 깨지면 GC 빈도 5배 ↑ 가능.

### 1.4 키워드 3 — "Implicit Stack Allocation"

```
C++:
  Point p(1, 2);   // 명시적 stack allocation
  use(p.x + p.y);

Java + EA:
  Point p = new Point(1, 2);   // 형식상 Heap
  use(p.x + p.y);
  
  → EA가 NoEscape 판정 → Scalar Replacement
  → 실제 동작: int p_x = 1; int p_y = 2; use(p_x + p_y);
  → C++의 stack allocation과 효과 동일
```

Java 사용자가 명시적 stack allocation API를 안 가지지만, **EA 덕분에 실효적으로 stack allocation을 얻음**. C 수준 메모리 효율 가능.

### 1.5 비유로 굳히기

> **택배 상자 비유**: NoEscape = 받자마자 풀어서 안의 물건만 쓰고 상자 안 만듦 (Scalar Replacement). ArgEscape = 상자를 다른 방으로 옮김. 같은 집(inline)이면 결국 NoEscape. 다른 집(escape) 보내면 진짜 상자 필요. GlobalEscape = 창고(static)나 우체국(Heap)에 영구 보관.

---

## 2. 가지 ②: WHAT — 3가지 Escape 종류 + 3가지 최적화

### 2.1 핵심 질문

> "EA의 결과는 어떻게 분류되고, 각각 어떤 최적화로 이어지나요?"

### 2.2 키워드 1 — NoEscape / ArgEscape / GlobalEscape

```
[NoEscape]
void foo() {
    Point p = new Point(1, 2);
    int x = p.x;
    use(x);
    // p가 메서드 밖으로 나가지 않음
}

[ArgEscape]
void foo() {
    Point p = new Point(1, 2);
    log(p);   // 다른 메서드로 전달
    // log()가 inline되면 NoEscape로 승격 가능
}

[GlobalEscape]
static List<Point> cache;
void foo() {
    Point p = new Point(1, 2);
    cache.add(p);   // static 필드로 보관
}
```

| Escape 종류 | 정의 | 최적화 |
|---|---|---|
| NoEscape | 메서드 안에서만 사용 | Scalar Replacement, Lock Elision, Coarsening |
| ArgEscape | 다른 메서드 인자로 전달, 그 메서드도 escape 안 함 | callee inline 후 NoEscape 승격 가능 |
| GlobalEscape | static 필드, 다른 객체의 필드, 컬렉션 추가 등 | 최적화 거의 없음 |

### 2.3 키워드 2 — Scalar Replacement

```
[변환 전 IR]
n1 = AllocateNode(Point.class)
n2 = StoreField(n1, "x", const 1)
n3 = StoreField(n1, "y", const 2)
n4 = LoadField(n1, "x")
n5 = LoadField(n1, "y")
n6 = Add(n4, n5)

[Scalar Replacement 후]
// Allocation 자체 제거
n1_x = const 1   // x field를 별도 scalar (register)
n1_y = const 2   // y field를 별도 scalar
n6 = Add(n1_x, n1_y)
// = Add(1, 2) = const 3 (후속 constant fold)
```

Allocate 노드 자체가 그래프에서 제거됨. 후속 phase가 추가 최적화.

위치: `src/hotspot/share/opto/macro.cpp`:

```cpp
void PhaseMacroExpand::eliminate_allocate_node(AllocateNode* alloc) {
    extract_scalar_fields(alloc);     // field를 별도 scalar로
    igvn().replace_node(alloc, ...);  // AllocateNode 제거
    update_safepoints();              // SafePointNode oop map 갱신
}
```

### 2.4 키워드 3 — Lock Elision + Lock Coarsening

**Lock Elision**:
```java
public String concat(String a, String b) {
    StringBuffer sb = new StringBuffer();   // NoEscape
    sb.append(a);   // 내부적으로 synchronized
    sb.append(b);
    return sb.toString();
}
```

`sb`가 NoEscape → 다른 thread가 접근 불가능 → synchronized 안전 제거. **StringBuffer가 StringBuilder처럼 동작**.

**Lock Coarsening**:
```java
// 변환 전
synchronized(lock) { a(); }
synchronized(lock) { b(); }
synchronized(lock) { c(); }

// 변환 후
synchronized(lock) { a(); b(); c(); }
```

3번의 lock/unlock → 1번. CAS 비용 절감. 같은 lock 객체에 대해서만, 단일 메서드 가까운 위치에서만.

### 2.5 흔한 NoEscape vs GlobalEscape 패턴

```java
// NoEscape (EA 친화)
public int compute(int x, int y) {
    Point p = new Point(x, y);
    return p.distance(0, 0);   // distance()가 inline되면 EA OK
}

public Optional<String> findName(int id) {
    String name = lookup(id);
    return Optional.ofNullable(name);   // 호출 사이트에서 inline + EA
}

for (String s : list) {   // Iterator 객체 ← EA 성공 시 안 만들어짐
    process(s);
}

// GlobalEscape (EA 비친화)
List<Point> result = new ArrayList<>();
for (...) {
    Point p = new Point(x, y);
    result.add(p);   // ★ caller에 return될 수 있음 → GlobalEscape
}

throw new ValidationException(p);   // ★ exception은 stack 위로 escape
executor.submit(() -> use(p));      // ★ lambda capture → GlobalEscape
this.cachedPoint = p;                // ★ this의 필드 → GlobalEscape
```

---

## 3. 가지 ③: HOW — Connection Graph + Inlining의 역할

### 3.1 핵심 질문

> "EA는 정확히 어떤 알고리즘으로 동작하고, Inlining과는 어떤 관계인가요?"

### 3.2 키워드 1 — Connection Graph (Choi et al., 1999)

```
1. Build Escape Connection Graph
   - 각 객체 allocation site → 노드
   - reference 흐름 → edge
   - Field, array element, method parameter, return value 추적

2. Propagate escape state
   - 각 노드의 escape state 초기화 (NoEscape)
   - reference가 escape하면 그 노드 + 도달 가능한 모든 노드를 GlobalEscape
   - fixpoint까지 반복

3. Use result
   - NoEscape 노드: Scalar Replacement 후보
   - ArgEscape: 그 메서드 inline 후 재분석
   - GlobalEscape: 변경 없음
```

위치: `src/hotspot/share/opto/escape.cpp`:

```cpp
class ConnectionGraph {
public:
    static void do_analysis(Compile* C, PhaseIterGVN* igvn) {
        ConnectionGraph cg(C, igvn);
        cg.compute_escape();
        if (cg.has_non_escaping_obj()) {
            cg.split_unique_types();   // NoEscape 식별
        }
    }
};
```

### 3.3 키워드 2 — Escape State Propagation

```cpp
enum EscapeState {
    UnknownEscape,
    NoEscape,
    ArgEscape,
    GlobalEscape
};

class PointsToNode : public ResourceObj {
    EscapeState _escape_state;
    Node*       _ideal_node;
};
```

각 allocation site에 PointsToNode 1개. Reference 흐름이 connection graph의 edge. fixpoint 반복으로 propagation.

### 3.4 키워드 3 — Inlining이 EA Enabler

```
[Inline 안 됨]
void foo() {
    Point p = new Point(1, 2);
    Point.print(p);   // ★ print()의 본문 모름
                       // → p가 print() 안에서 어떻게 쓰이는지 불명
                       // → 보수적으로 GlobalEscape 간주
                       // → EA 실패
}

[Inline 됨 (print는 작아서 inline)]
void foo() {
    Point p = new Point(1, 2);
    // print() 본문이 여기에 펼쳐짐
    System.out.println(p.x);
    System.out.println(p.y);
    // ★ p는 메서드 안에서만 사용 → NoEscape
    // → Scalar Replacement
}
```

→ **EA의 정확도는 inlining 깊이에 직접 의존**. Inlining 막히면 EA도 같이 죽음. "Inlining is the mother of optimizations"의 한 측면.

### 3.5 Partial Escape Analysis (Graal only)

```java
void foo(boolean rare) {
    Point p = new Point(1, 2);
    if (rare) {
        cache.add(p);   // 1% 경우만 escape
    } else {
        use(p.x + p.y);   // 99% 경우는 NoEscape
    }
}
```

C2 EA: `p`가 한 path에서라도 escape → 전체를 GlobalEscape → 항상 allocation.

Graal Partial EA: escape하는 path에만 객체 생성 코드. non-escape path는 Scalar Replacement. 결과: 99% 경우 객체 안 만듦.

→ Graal이 C2보다 빠른 워크로드의 한 이유. C2가 안 하는 이유: 1990년대 설계, 구현 복잡도.

---

## 4. 가지 ④: 운영 — 시니어 진단

### 4.1 핵심 질문

> "EA가 잘 동작하는지, 코드 변경으로 EA가 깨졌는지 어떻게 측정하나요?"

### 4.2 키워드 1 — `-XX:+PrintEscapeAnalysis`

```bash
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintEscapeAnalysis -jar app.jar
```

출력:
```
======== Connection graph for com.foo.Service::compute
JavaObject(NoEscape) NodeIdx=23 Allocate java/awt/Point
   Field x:I JavaObject(NoEscape)
   Field y:I JavaObject(NoEscape)
JavaObject(GlobalEscape) NodeIdx=45 Allocate java/util/ArrayList
...
```

NoEscape 객체가 Scalar Replacement 후보.

### 4.3 키워드 2 — JFR Allocation Rate

```bash
jcmd <pid> JFR.start name=alloc duration=60s settings=profile filename=alloc.jfr
jfr summary alloc.jfr | grep -iE 'AllocationSample|TLAB'
```

핵심 이벤트:
- `jdk.ObjectAllocationInNewTLAB` — TLAB에 새 객체.
- `jdk.ObjectAllocationOutsideTLAB` — Eden 직접 할당 (큰 객체).

→ **EA가 잘 동작하면 allocation rate가 의외로 낮음**. Stream/Lambda heavy 코드인데 allocation 적으면 EA 성공.

async-profiler:
```bash
asprof -e alloc -d 60 -f alloc.html <pid>
```

Allocation flame graph. Hot allocation site 식별. 자주 할당되는 site의 코드를 audit해 EA 가능성 검토.

### 4.4 키워드 3 — EA 깨짐 패턴

```java
// 1. 컬렉션에 add
List<Point> result = new ArrayList<>();
for (...) {
    Point p = new Point(x, y);
    result.add(p);   // ★ result는 caller에 return될 수 있음 → GlobalEscape
}

// 2. Exception throw
if (invalid) {
    throw new ValidationException(p);   // ★ exception은 stack 위로 escape
}

// 3. 비동기 task로 전달
executor.submit(() -> use(p));   // ★ lambda capture → GlobalEscape

// 4. 다른 객체의 필드로 저장
this.cachedPoint = p;   // ★ this의 필드 → GlobalEscape

// 5. 한 줄 추가로 EA 깨짐
public int compute() {
    Point p = new Point(1, 2);
    int result = p.x + p.y;
    if (DEBUG) log(p);   // ← 이 한 줄로 GlobalEscape 가능
    return result;
}
```

→ **EA 의존 hot path는 변경 시 측정 필수**. JFR로 allocation rate 비교.

### 4.5 운영 시나리오 매트릭스

| 증상 | 진단 | 가능 원인 |
|---|---|---|
| GC 빈도 ↑ | JFR allocation rate | EA 실패 (코드 변경?) |
| Synchronized 코드인데 fast | EA Lock Elision 작동 | 정상 |
| Synchronized 코드가 갑자기 slow | EA 깨짐 | 객체가 escape하게 됨 |
| Stream API 코드 allocation 적음 | EA 성공 | 정상 |
| 일부만 빠른 path 있음 (rare) | Partial EA 없음 | C2 한계, Graal 검토 |

### 4.6 Killer 시나리오 — 코드 한 줄 추가 후 GC 빈도 ↑

```
환경: 평소 GC 분당 1회, 코드 한 줄 추가 후 분당 5회

진단:
1. JFR로 allocation 비교 (변경 전/후).
2. PrintEscapeAnalysis로 새 코드의 EA 결과 확인.
3. 결과: 새로 추가한 log(p) 호출로 인해 p가 GlobalEscape.

조치:
- log()를 inline 가능하게 (작게 유지).
- 또는 conditional log: if (LOG.isDebugEnabled()) log(p)
  → JIT가 LOG.isDebugEnabled 결과로 분기 → debug=false면 dead code 제거.
- 또는 hot path에서 log 제거.
```

---

## 5. 면접 답변 워크플로우

### 5.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "EA가 뭐고 왜 중요?" | ① WHY | ② 3종 escape |
| "NoEscape vs GlobalEscape" | ② WHAT | ④ 운영 패턴 |
| "Scalar Replacement?" | ② WHAT | ③ EA 알고리즘 |
| "Lock Elision 예시" | ② WHAT | StringBuffer 동작 |
| "Inlining과 EA 관계" | ③ HOW (enabler) | ① WHY |
| "Partial EA?" | ③ HOW (Graal only) | C2 한계 |
| "EA 깨짐 진단" | ④ 운영 | ② GlobalEscape 패턴 |

### 5.2 답변 템플릿

> 루트 → 가지 키워드 3개 → 인접

예: "Escape Analysis가 무엇이고 왜 중요한가요?"

> "Escape Analysis는 객체의 reference가 메서드 밖으로 escape하는지 분석하는 C2의 phase입니다. (← 루트)
> 3가지 escape 종류로 분류합니다.
> - **NoEscape**: 객체가 만들어진 메서드 안에서만 사용. 최적화 가장 적극.
> - **ArgEscape**: 다른 메서드 인자로 전달, 그 메서드도 escape 안 함. callee inline 시 NoEscape 승격.
> - **GlobalEscape**: static 필드, 컬렉션 추가, exception throw 등. 최적화 거의 없음.
> NoEscape일 때 3가지 최적화 가능:
> 1. **Scalar Replacement**: field를 register로 분해, 객체 안 만듦.
> 2. **Lock Elision**: synchronized 제거 (다른 thread 접근 불가).
> 3. **Lock Coarsening**: 인접 synchronized 통합.
> 결과: Java가 사실상 stack allocation 효과를 얻음 — Allocation 비용 zero, GC 부담 zero. EA 성공 + Inlining 깊이가 Java의 hidden performance의 핵심."

---

## 6. 꼬리질문 트리 (가지별)

### Q1 [가지 ①]. Escape Analysis가 무엇이고 왜 중요한가요?

> 객체의 reference가 메서드 밖으로 escape하는지 분석. 결과 3단계: NoEscape / ArgEscape / GlobalEscape.
> 가능하게 하는 최적화 3가지:
> 1. **Scalar Replacement**: NoEscape 객체의 field를 register로 분해 → 객체 자체 안 만듦.
> 2. **Lock Elision**: NoEscape 객체의 synchronized 제거.
> 3. **Lock Coarsening**: 인접 synchronized 통합.
> 중요성: Java가 사실상 stack allocation 효과를 얻는 핵심 메커니즘. EA 성공 시 GC 부담 0, 동기화 비용 0.

**🪝 Q1-1: NoEscape, ArgEscape, GlobalEscape의 차이는?**
> - NoEscape: 객체가 만들어진 메서드 안에서만 사용. 최적화 가장 적극.
> - ArgEscape: 다른 메서드 인자로 전달, 그러나 그 메서드도 escape 안 함. callee inline 시 NoEscape 승격.
> - GlobalEscape: static 필드, 다른 객체 필드, 컬렉션 추가 등. 최적화 거의 없음.

### Q2 [가지 ②]. Scalar Replacement가 무엇이고 왜 "implicit stack allocation"이라 불리나요?

> NoEscape 객체의 field들을 별도 scalar 변수(register 또는 stack slot)로 분해. 객체 자체는 만들어지지 않음.
> 예: `Point p = new Point(1, 2); int sum = p.x + p.y;` → `int p_x = 1; int p_y = 2; int sum = p_x + p_y;` → `= 3`.
> "implicit stack allocation"이라 부르는 이유: 객체가 Heap에 없고 마치 stack에 있는 것처럼 동작. C++의 stack allocation과 효과 동일. Java 사용자가 명시적 stack allocation API를 안 가지지만, EA 덕분에 실효적 stack allocation.

### Q3 [가지 ③]. Inlining과 EA의 관계는?

> EA는 객체가 메서드 밖으로 escape하는지 봄. 그러나 다른 메서드로 객체를 넘기면 그 메서드 본문을 모름 → 보수적으로 GlobalEscape 간주.
> Inlining이 그 메서드 본문을 caller에 펼치면:
> - 메서드 경계 사라짐.
> - EA가 객체 전체 lifetime을 한 메서드 안에서 추적.
> - ArgEscape → NoEscape 승격.
> - Scalar Replacement 가능.
> 결론: **EA의 정확도는 inlining 깊이에 직접 의존**. Inlining 막히면 EA도 같이 죽음.

### Q4 [가지 ②]. Lock Elision이 동작하는 흔한 예시는?

> `StringBuffer.append` — 옛 코드의 흔한 패턴.
> ```java
> public String concat(String a, String b) {
>     StringBuffer sb = new StringBuffer();   // NoEscape
>     sb.append(a);
>     sb.append(b);
>     return sb.toString();
> }
> ```
> `StringBuffer`는 thread-safe (모든 메서드 synchronized). 그러나 `sb`가 메서드 안에서만 사용 → NoEscape → 다른 thread 접근 불가 → synchronized 안전 제거.
> 결과: `StringBuffer`가 `StringBuilder`처럼 빠르게 동작. 옛 코드를 굳이 StringBuilder로 바꿀 필요 줄어듦 (EA 성공 가정).

### Q5 [가지 ③]. Partial Escape Analysis가 무엇이고 C2는 왜 안 하나요?

> Graal에 있는 더 정교한 EA. C2 미지원.
> 차이:
> - **C2 EA**: 객체가 한 path에서라도 escape하면 전체를 GlobalEscape 처리.
> - **Partial EA**: escape하는 path에만 객체 생성 코드, non-escape path는 Scalar Replacement.
> 예: 99% 경우 NoEscape, 1% 경우 escape. C2는 항상 allocation. Graal은 99% allocation 0, 1%만 allocation.
> C2가 안 하는 이유: 1990년대 설계, 구현 복잡도. Graal은 Java로 작성되어 더 정교한 알고리즘 적용 가능.

### Q6 (Killer) [가지 ④]. Stream API 코드가 List.add 코드보다 빠른 경우가 있는 이유는?

> EA가 핵심 차이:
> ```java
> // Stream
> int sum = list.stream().mapToInt(Integer::intValue).sum();
> 
> // List.add
> List<Integer> tmp = new ArrayList<>();
> for (Integer x : list) tmp.add(x);
> int sum = tmp.stream().mapToInt(...).sum();
> ```
> Stream 코드의 객체들 (Stream, IntStream, Spliterator 등):
> - 호출 사이트가 monomorphic이면 inline.
> - inline 후 EA가 NoEscape → Scalar Replacement.
> - 객체들이 사실상 사라지고 단순 loop로 변환.
> 
> List.add 코드:
> - `tmp` ArrayList → 누가 잡고 있을 수 있음 → GlobalEscape.
> - Allocation 그대로.
> - 각 Integer 박싱 → 또 allocation.
> 
> 결과: Stream이 더 빠를 수도 있음 (EA 효과). 단, lambda 다양성으로 megamorphic이면 반대.
> → **EA + Inlining의 조합이 Java의 hidden performance**.

---

## 7. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 이내로 그릴 수 있다 (루트 + 4가지 + 키워드 3개)
- [ ] 가지 ① WHY: Allocation 비용 + GC 부담 + implicit stack allocation 효과 설명한다
- [ ] 가지 ② WHAT: 3 escape (NoEscape/Arg/Global) 코드 예시로 분류한다
- [ ] 가지 ② WHAT: 3 최적화 (Scalar Replacement, Lock Elision, Coarsening) 각각 코드 변환을 그린다
- [ ] 가지 ③ HOW: Choi et al.(1999) Connection Graph 3단계 알고리즘 말한다
- [ ] 가지 ③ HOW: Inlining이 EA의 enabler인 이유 설명한다 (메서드 경계 제거)
- [ ] 가지 ③ HOW: Partial EA가 C2에 없는 이유와 Graal에 있는 이유 비교한다
- [ ] 가지 ④ 운영: EA 깨짐 5가지 패턴 (add/exception/lambda/this 필드/한 줄 추가) 말한다
- [ ] 가지 ④ 운영: 코드 변경 후 GC 빈도 ↑ 진단 절차 말한다
- [ ] 6장 꼬리질문 6개에 막힘없이 답한다

---

## 다음 단계

- → [07. Loop and Vector](./07-loop-and-vector.md): Inlining + EA의 cascade — Loop opts
- → [08. Speculative and Deopt](./08-speculative-and-deopt.md): EA speculation + Deopt
- ← [05. Inlining and IC](./05-inlining-and-ic.md): EA의 enabler
- ← [04. C1 and C2](./04-c1-and-c2.md): C2 phase 안에서 EA 위치
- 관련: [05. Threading](../05-threading/) — Lock Elision의 동시성 측면

## 참고

- **Choi et al. — "Escape Analysis for Java" (1999)**: IBM 논문, ECOOP
- **Whaley & Rinard — "Compositional Pointer and Escape Analysis"**: 1999 OOPSLA
- **HotSpot src `escape.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/opto/escape.cpp
- **HotSpot src `macro.cpp` (Scalar Replacement)**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/opto/macro.cpp
- **Graal Partial Escape Analysis 논문**: Stadler et al. 2014
- **Aleksey Shipilëv — EA Quark**: https://shipilev.net/jvm/anatomy-quarks/
