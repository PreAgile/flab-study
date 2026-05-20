# 01-04. Initialization & Class Unload — clinit의 함정과 ClassLoader 회수

> Initialization 한 줄짜리 설명: "static 블록 실행".
> 그런데 그 한 줄에 **JLS 12.4.2의 12단계 락 절차**, **순환 초기화의 데드락 회피**, **상속 시 초기화 순서**, **lazy initialization 패턴**의 모든 함정이 다 들어있다.
> 그리고 끝에는 클래스가 어떻게 죽는가 — ClassLoader unload.

---

## 이 문서의 사용법

이 문서는 **면접용 마인드맵**을 따라 선형으로 펼친 구조다. 학습 순서 = 면접 답변 순서 = 백지에 그리는 순서.

1. **0장 마인드맵을 먼저 외운다** — 루트 한 문장 + 6가지 가지 + 각 가지의 키워드 3개.
2. **1~6장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 정확히 대응.
3. **7장 면접 워크플로우로 검증**.
4. **8장 꼬리질문으로 깊이 점검**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"Initialization은 JVM Initializer가 Active Use 시점에 per-Class `_init_lock`을 잡고 12-step으로 `<clinit>`을 정확히 한 번 실행하는 단계다. 그 다음은 클래스의 죽음 — ClassLoader가 unreachable이 되면 CLD 단위로 회수된다."**

이 한 문장에서 모든 답변이 출발한다. 어떤 질문이 와도 이 문장부터 말하고 적절한 가지로 분기.

### 6개 가지 — 순서를 외운다

```
                  [ROOT: Init = JVM이 12-step으로 clinit 1회 / Unload = CL 단위]
                                  │
       ┌──────────┬──────────┬────┴─────┬──────────┬──────────┬──────────┐
       │          │          │          │          │          │          │
      ① WHY    ② 트리거   ③ clinit  ④ 12-step ⑤ Unload  ⑥ 운영    
   책임경계   Active Use  자동합성  락 절차    CL 단위    워밍업+leak
   JVM본체    6 케이스   소스순서  state머신  4조건     P99 진단
       │          │          │          │          │          │
       │     ┌────┼────┐  ┌──┼──┐    ┌──┼──┐   ┌───┼───┐  ┌───┼───┐
   ClassLoader Active 6   <clinit>  per-Class  4조건  Eager init
   Loading만   Passive 6  사용자     state     Bootstrap Synthetic
   _init_lock  ConstantValue 못호출  재진입OK   영원      AppCDS
   per-Class   배열X     소스순서   짧은락+notify Leak    GraalVM
              .classX                          5패턴     CRaC
```

### 가지별 핵심 키워드 (각 가지 3개씩만)

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① WHY 책임경계** | JVM Initializer | per-Class init_lock | Active Use 시점에만 |
| **② 트리거** | Active vs Passive | 6 Active | 6 Passive (ConstantValue, 배열, .class) |
| **③ clinit** | 자동 합성 | 소스 순서 | 사용자 호출 불가 |
| **④ 12-step** | per-Class 락 | 재진입 통과 | state machine + happens-before |
| **⑤ Unload** | CL 단위 | 4조건 | Bootstrap/Platform 영원 |
| **⑥ 운영** | P99 cold start | Leak 5패턴 | Warmup (AppCDS/Native/CRaC) |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 질문에 맞는 가지 1개 선택 → 그 가지의 키워드 3개 순서대로 설명 → 듣는 사람의 관심에 따라 인접 가지로 확장

---

## 1. 가지 ①: WHY — 책임 경계와 락의 정체

### 1.1 핵심 질문

> "Initialization은 누가 하고, 락은 누가 언제 어디에 잡는가?"

### 1.2 키워드 1 — JVM Initializer가 한다 (ClassLoader 아님)

| 시점 | 주체 | 무엇을 하나 |
|---|---|---|
| 컴파일 타임 | **javac** | `<clinit>`을 합성해 `.class`에 박음 (01장) |
| 런타임 - 첫 참조 | **ClassLoader** | `.class` → `Class` 객체 (Loading만, 02장) |
| 런타임 - Loading 직후 | **JVM Linker** | Verify · Prepare · Resolve (03장) |
| 런타임 - **Active Use 시점** | **JVM Initializer** | ★ 이 챕터 — `<clinit>` 실행, 12-step 락 |
| 런타임 - 마지막 | **GC + ClassLoader 회수** | Class Unloading (CLD 단위) |

자주 묻는 오해: "`.class`로 컴파일된 클래스를 ClassLoader가 초기화 과정 중에 락을 세팅하는 건가?" → **아니다**.

### 1.3 키워드 2 — `_init_lock`은 Class 객체에 항상 박혀 있다

```
Class 객체 (메모리에 1개, ClassLoader가 만들어 둔 것)
├─ _init_state    : not_initialized / being_initialized / fully_initialized / init_error
├─ _init_thread   : 지금 <clinit>을 돌리고 있는 스레드 (재진입 판별용)
└─ _init_lock     : ← ★ 12-step이 잡는 락 (per-Class 내부 모니터)
```

특징:
- **클래스마다 하나** (전역 락 아님 → 서로 다른 클래스의 init은 병렬 가능).
- **`synchronized(A.class)`로 사용자가 잡는 모니터와 별개** (사용자 코드에서 접근 불가).
- ClassLoader가 만드는 게 아니라, Class 객체가 만들어질 때 JVM이 자동 부여.

락은 "세팅되는" 게 아니라 **항상 박혀 있고**, 12-step은 그 박혀 있는 락을 **사용하는 절차**.

### 1.4 키워드 3 — Active Use 시점에만 락이 잡힌다

`new A()`, `A.staticMethod()`, `A.staticField`, `Class.forName(name, true)` 같은 트리거 바이트코드가 실행되는 순간, JVM이 그 클래스의 `_init_lock`을 잡고 12-step에 진입한다. **Active Use가 없으면 클래스가 로드돼 있어도 락은 안 잡힌다**.

핵심 한 줄: **javac가 `<clinit>`을 만들고, ClassLoader가 Class 객체를 메모리에 올리고, JVM Initializer가 Active Use 시점에 그 Class에 박혀 있는 `_init_lock`으로 12-step을 돌려 `<clinit>`을 정확히 한 번 실행한다.**

### 1.5 회사 입사 비유

- **Loading** = 이력서 제출
- **Verification** = 신원 조회
- **Preparation** = 책상/사원증 배정 (빈 상태)
- **Resolution** = 부서 배치 (lazy: 첫 업무 시)
- **Initialization** = OT (오리엔테이션) — **딱 한 번**만, **순서 있음** (부장님 OT 먼저, 그 다음 신입)

### 1.6 왜 Initialization은 단 한 번인가

JVMS §5.5: 트리거 조건이 만족되는 순간 한 번. 두 번은 절대 안 됨.

1. **Static 필드의 일관성**: 두 번 초기화하면 timestamp 같은 값이 달라져 비결정.
2. **Side effect 통제**: static 블록에서 외부 리소스(파일, DB) 할당 시 두 번 실행 = 누수.
3. **JMM 보장**: `<clinit>` 끝남 = 모든 static 필드 publish, happens-before. 두 번 실행은 이 보장을 깨뜨림.

---

## 2. 가지 ②: 트리거 — Active vs Passive Use

### 2.1 핵심 질문

> "언제 클래스 초기화가 일어나고, 언제는 일어나지 않는가? 그 기준은 무엇인가?"

### 2.2 키워드 1 — 핵심 원리: Active vs Passive

**JVM은 그 클래스의 `<clinit>` 결과(static 필드의 의미 있는 값, side effect)에 실제로 의존할 때만 init한다.** "타입 정보만" 또는 "이름만" 필요하면 init **안 함**.

JLS 12.4.1 옛 표현으로 **active use vs passive use**. 용어는 deprecate됐지만 개념은 그대로.

```
┌──────────────────────────────────────────────────────────────┐
│ 결정 질문:                                                    │
│ "그 클래스의 <clinit>이 만든 static state나 side effect를     │
│  실제로 사용해야 하는가?"                                     │
└──────────────────────────────────────────────────────────────┘
       │                                       │
       Yes (Active Use)                        No (Passive Use)
       │                                       │
       ▼                                       ▼
┌─────────────────────┐                ┌──────────────────────┐
│ init 트리거 발동    │                │ init 불필요          │
├─────────────────────┤                ├──────────────────────┤
│ • new A()           │                │ • A.X (ConstantValue)│
│ • A.staticMethod()  │                │ • new A[10]          │
│ • A.staticField     │                │ • forName(name,false)│
│ • forName(name,true)│                │ • A.class            │
│ • main 클래스       │                │ • obj instanceof A   │
│ • Subclass init     │                │ • (A) obj            │
└─────────────────────┘                └──────────────────────┘
```

**흔한 오해**: "Stack/Heap 위치"가 기준이라는 생각 → **틀림**. 반례: `A.class`는 Heap의 Class 객체를 사용하는데도 init 안 함. `new A[10]`도 Heap에 배열을 만드는데도 init 안 함. 기준은 **"코드/값이 의미 있게 사용되는가"**.

### 2.3 키워드 2 — Active Use 6가지

```java
1. new MyClass()                // 인스턴스 생성
2. MyClass.staticMethod()       // static 메서드 호출
3. MyClass.staticField          // static 필드 R/W (ConstantValue 제외)
4. Class.forName("MyClass")     // initialize=true (기본값)
5. JVM 시작 시 main 클래스       // java MyMainClass
6. Subclass 초기화 → Parent       // 부모 클래스도 (인터페이스는 조건부)
```

각 케이스가 왜 init이 필요한가:

| Active Use | 이유 |
|---|---|
| `new A()` | 생성자가 static 필드/메서드에 의존 가능. static state ready 안 되면 NPE. |
| `A.staticMethod()` | 메서드 body가 static 필드 사용 가능. `<clinit>` 안 돌면 default 상태. |
| `A.staticField` | 필드의 **값** 자체가 의미 있어야 함. Preparation의 default → Init의 진짜 값. |
| `Class.forName(name, true)` | API 명세상 init 완료 보장. JDBC Driver 등록의 `<clinit>` 활용. |
| main 클래스 | `main()` static 메서드 호출 → case 2와 동일. |
| Subclass | Child의 `<clinit>`이 Parent state 사용 가능. Parent 없이 Child 동작 불가. |

### 2.4 키워드 3 — Passive Use 6가지

```java
1. A.X                          // ConstantValue 박힌 final
2. new A[10]                    // 배열 생성
3. Class.forName("A", false, loader)  // initialize=false
4. A.class                      // .class literal
5. obj instanceof A             // 타입 검사
6. (A) obj                      // cast (검사만)
```

각 케이스가 왜 init이 불필요한가:

| Passive Use | 이유 |
|---|---|
| `A.X` (ConstantValue) | 컴파일러가 사용처에 **literal 인라이닝** (`bipush 10`). 런타임에 A를 안 봐도 됨. |
| `new A[10]` | 배열은 `[LA;`라는 별도 합성 클래스의 인스턴스. A 코드 한 줄도 안 돌림. |
| `forName(name, false)` | 호출자가 명시적 "init 안 함" 선언. |
| `A.class` | mirror Class 객체만 가져옴. Loading+Linking까지면 충분. |
| `obj instanceof A` | 타입 계층 검사만. Klass 메타데이터 검색. |
| `(A) obj` | 타입 검사만. A의 코드 실행 안 함. |

**ConstantValue가 박히는 조건**: `static final` + compile-time constant expression — primitive literal, String literal, primitive constant expression, 다른 ConstantValue 참조. **NOT**: `new String("hi")`, `compute()` 호출, `new Date()`, 배열.

### 2.5 시니어 운영 관점 — 이 원리가 풀어주는 의문들

1. **`Class.forName("com.mysql.cj.jdbc.Driver")`의 본질**: Driver의 `<clinit>`에서 `DriverManager.registerDriver(this)`를 호출하는 **side effect를 트리거**하려는 active use. `forName(name, false)`로 호출하면 등록 안 됨.

2. **Spring `ClassPathScanner`가 안 쓰는 클래스도 발견하는 이유**: `forName(name, false)`로 메타데이터만 읽어 빈 후보 추림. 실제 빈 생성 시 `new`로 active use.

3. **Lazy initialization 패턴**: `Class<?> c = A.class;`로 Loading만 끝내두고, 진짜 필요할 때 `c.getDeclaredConstructor().newInstance()`로 init.

4. **AppCDS와 Native Image 분기점**: CDS는 passive use 결과(Loading/Linking)를 archive. Native Image는 active use(`<clinit>`)까지 build-time에 실행 → environment-specific 값 함정.

5. **테스트 함정**: `Mockito.mock(A.class)`는 `A.class` literal만 사용 → passive → A의 static block 안 돎.

---

## 3. 가지 ③: `<clinit>` — JVM이 가져간 책임

### 3.1 핵심 질문

> "`<clinit>`는 무엇이고, 왜 javac가 자동으로 만들며, 어떤 순서로 합성되는가?"

### 3.2 키워드 1 — 자동 합성

- `<clinit>` = **"class initializer"** ("클리닛"). 그 클래스 전체의 초기화자.
- 짝: `<init>` = **"instance initializer"** = 생성자.
  - `<clinit>`: 클래스 단위, 1회.
  - `<init>`: 인스턴스 단위, 매 `new`마다.
- 왜 `<`로 시작? — **사용자가 자바 식별자로 못 만들 이름**이라서. "JVM 내부만의 메서드"의 강제 시그널.

### 3.3 키워드 2 — 왜 JVM이 가져갔는가

Static 초기화가 반드시 지켜야 하는 4가지:
1. **정확히 1회 실행**
2. **소스 코드 순서대로**
3. **끝나면 모든 static 필드가 모든 스레드에 visible** (happens-before)
4. **어느 스레드가 트리거했든 동일한 결과**

이걸 사용자가 직접 `initialize()` 메서드로 짜면:
- 누구는 호출 까먹음.
- 누구는 두 번 호출.
- thread-safety는 사용자가 매번 직접.
- 라이브러리 사용자는 그 존재조차 모름.

JVM의 선언: **"Static 초기화는 내가 책임진다. 너는 `static` 키워드만 써."**

세 가지 설계 결정:

| 결정 | 왜 |
|---|---|
| 모든 static initializer + static block을 **한 메서드에 통째로** 합성 | "끝났다/안 끝났다" 두 상태로 단순화. 단계별 트래킹 불필요. |
| **소스 코드 등장 순서대로** 합성 | 프로그래머 의도 보존. 의존성도 자연스럽게 해결. |
| 이름을 `<clinit>` — 사용자가 못 만들고 못 호출하는 이름 | "사용자 손대지 마"의 강제 메커니즘. |

### 3.4 키워드 3 — 합성 예시

```java
class Example {
    static int x = 1;          // static field initializer
    static int y;
    static String s = "hi";

    static {                    // static block
        y = 2;
        System.out.println("Initialized");
    }

    static int z = compute();   // 또 다른 initializer

    static int compute() { return 42; }
}
```

생성되는 `<clinit>`:
```
static void <clinit>() {
    x = 1;                    // line 2
    s = "hi";                  // line 4
    // static block
    y = 2;
    System.out.println("Initialized");
    // 다음 initializer
    z = compute();
}
```

**순서**: 소스 코드 등장 순서 그대로. static field initializer와 static block이 섞이면 등장 순서대로.

**명시적 호출 불가**: 사용자 코드에서 `invokestatic` 못 함. 이름이 `<`로 시작 — 일반 메서드 이름 규칙 위반.

---

## 4. 가지 ④: 12-step Lock 절차 (JLS 12.4.2)

### 4.1 핵심 질문

> "여러 스레드가 동시에 같은 클래스를 init하려 하면 어떻게 정확히 한 번만 실행되고, 데드락은 어떻게 회피하는가?"

### 4.2 키워드 1 — JLS 12.4.2의 정체

- **JLS** = Java Language Specification. 자바 언어의 공식 표준 문서.
- **§12.4** = "Initialization of Classes and Interfaces".
- **§12.4.2** = "Detailed Initialization Procedure". `<clinit>`을 정확히 어떤 락 순서로 실행해야 하는지 12 단계로 못박은 절.
- **JVMS §5.5**: 초기화 트리거 조건.

### 4.3 키워드 2 — 락이 보장하는 것

**락이 없으면 깨지는 3가지**:
1. **중복 실행** — `<clinit>` 두 번 → DB connect 두 번, 파일 핸들 두 번 → 자원 누수.
2. **결과 비결정** — 누가 늦게 끝났는지에 따라 static 필드 값이 달라짐.
3. **부분 상태 노출** — 다른 스레드가 만들다 만 객체를 봄 → NPE.

**락이 있으면 보장되는 3가지**:
1. **정확히 한 번 실행** — 한 스레드만 진짜 실행, 나머지는 완성된 결과만 봄.
2. **happens-before** — `<clinit>`의 모든 쓰기가 다른 스레드에 visible (notifyAll/wait 짝이 메모리 배리어).
3. **부분 상태 노출 없음** — 항상 완성된 결과만 노출.

### 4.4 키워드 3 — 세 가지 설계 결정

| 결정 | 왜 |
|---|---|
| **클래스마다 별도 락** (`InstanceKlass.init_lock`) | 전역 락 하나면 A의 `<clinit>`이 B를 트리거할 때 자기 락에 갇혀 데드락. |
| **같은 스레드의 재진입은 통과** | 순환 의존(`A.x = B.y; B.y = A.x;`)에서 자기 락을 다시 잡으면 자기 데드락 → "같은 스레드면 그냥 return". |
| **락은 짧게 잡고, `<clinit>` 본문은 락 없이 실행** | `<clinit>`은 수초~수분 걸릴 수 있음. 락은 **"누가 INITIALIZING의 주인인지 결정하는 진입 게이트"**일 뿐, 본문 직렬화 아님. |

가장 중요한 통찰: **락이 보호하는 건 "state transition"이지 "`<clinit>` 본문"이 아니다**. `<clinit>` 실행 중에는 `state = INITIALIZING` 마킹만 한 채로 락은 풀어둠.

### 4.5 12-step을 3축으로 이해하기

```
┌──────────────────────────────────────────┐
│ 축 1. State machine                       │
│   loaded → linked → INITIALIZING          │
│        → INITIALIZED                      │
│        → ERRONEOUS (영구 broken)          │
├──────────────────────────────────────────┤
│ 축 2. 진입 게이트 (락 잡고 state 확인)    │
│   - INITIALIZED → 통과                    │
│   - ERRONEOUS  → NoClassDefFoundError     │
│   - INITIALIZING(다른 스레드) → wait      │
│   - INITIALIZING(같은 스레드) → 통과(재귀)│
│   - 새로 시작 → INITIALIZING 마킹 후 락 해제│
├──────────────────────────────────────────┤
│ 축 3. 실행 + 결과 마킹                    │
│   부모 먼저 → <clinit> 실행                │
│   정상 → INITIALIZED + notifyAll          │
│   예외 → ERRONEOUS + 영구 broken          │
└──────────────────────────────────────────┘
```

**12-step의 각 단계는 이 3축의 자연스러운 구현일 뿐. "왜 이런 절차가 필요한가" 답할 수 있으면 시니어 시그널, "12-step 순서를 다 외웠다"는 그냥 외운 것.**

### 4.6 12 단계 (참고용)

```
Step 1. Class object의 init lock 획득 (각 Class마다 별도 락)
Step 2. 다른 스레드가 init 중이면 → wait, lock 풀고 끝나면 다시 가져옴
Step 3. 현재 스레드가 이미 이 클래스를 init 중이면 → unlock하고 종료 (재귀)
Step 4. 클래스가 이미 init 완료면 → unlock하고 종료
Step 5. 클래스가 erroneous면 → unlock + NoClassDefFoundError throw
Step 6. INITIALIZING으로 마킹
Step 7. lock 해제 (★ 여기서 풀어야 다른 스레드가 wait에 들어갈 수 있음)
Step 9. (인터페이스가 아니면) super 클래스 init (재귀)
       슈퍼 인터페이스 중 default method 가진 것 init
Step 10. <clinit> 실행
        - 정상 → state = INITIALIZED, lock 다시 잡고 notifyAll
        - 예외 → state = ERRONEOUS, ExceptionInInitializerError로 wrap
```

### 4.7 순환 의존 (Step 3 활용)

```java
class A { static int x = B.y; }   // B 초기화 트리거
class B { static int y = A.x; }   // A 초기화 트리거 — 순환!
```

스레드 T1이 A를 먼저 시작:
1. A의 락 잡음. state(A) = INITIALIZING.
2. A의 `<clinit>` 실행 → `B.y` 접근 → B 초기화 트리거.
3. B의 락 잡음. state(B) = INITIALIZING.
4. B의 `<clinit>` 실행 → `A.x` 접근 → A 초기화 시도.
5. **Step 3 매칭**: "이 스레드가 이미 A를 init 중이다" → 그냥 return.
6. A.x를 (아직 초기화 안 된 0) 값으로 읽음 → B.y = 0.
7. B 완료. A로 돌아옴 → A.x = B.y = 0.

**결과: 둘 다 0. 데드락은 아니지만 비직관적**.

### 4.8 진짜 데드락이 일어나는 경우

```java
// Thread T1
class A { static { B.foo(); } }   // B 초기화 트리거

// Thread T2
class B { static { A.foo(); } }   // A 초기화 트리거

T1.start();  // A 초기화 시작
T2.start();  // B 초기화 시작 (T1이 A 락 잡은 상태에서)
```

- T1: A의 락 잡음 → B 초기화 시도 → B의 락 시도 → 대기.
- T2: B의 락 잡음 → A 초기화 시도 → A의 락 시도 → 대기.
- → **데드락**.

JVM은 이 케이스를 감지 못 함. 진단: `jstack`으로 두 스레드가 서로의 Class init lock 대기 발견. 회피: static block에서 다른 클래스 호출 안 하거나, 한 방향으로만.

### 4.9 부모 vs 인터페이스 초기화

#### 부모 클래스 (extends) — 항상 먼저

JLS 12.4.1:
```java
class Parent { static { System.out.println("Parent init"); } }
class Child extends Parent { static { System.out.println("Child init"); } }

new Child();
// Parent init
// Child init
```

#### 인터페이스 (implements) — JDK 8+ default method만

JDK 7까지: 인터페이스는 코드 실행 없음 → 클래스 초기화 시 인터페이스는 init 안 함.
JDK 8+: default method 등장 → "실행 코드"를 가질 수 있음 → init 필요.

JLS 12.4.1 (JDK 8+): "A class or interface I is initialized just before ... if I has at least one **non-abstract** default method".

```java
interface IWithDefault {
    static int x = init();  // 실행됨
    default void foo() {}
}
interface IWithoutDefault {
    static int y = init();  // 실행 안 됨 — implements만으로는 init 안 함
}
class C implements IWithDefault, IWithoutDefault {}
new C();  // "Interface init"만 (IWithDefault만)
```

**왜 default method 있을 때만 init하나**:
- JDK 7 이전: 인터페이스는 static 필드만 — 그 필드를 실제 읽을 때 lazy init하면 충분.
- JDK 8+: default method = 실행 코드 → 그 인터페이스의 static initializer가 실제로 의미 있을 수 있음.
- 한 클래스가 수십 개 인터페이스 구현 가능 → 모두 미리 init하면 startup 느림. default 있는 것만 init.

### 4.10 ExceptionInInitializerError → 영구 erroneous

`<clinit>` 중 예외 → 그 클래스는 영구히 **erroneous** 상태. 이후 모든 접근에서 `NoClassDefFoundError`. 회복 불가 — 그 ClassLoader 폐기 후 새 CL로 다시 로드해야 함.

**왜 가혹한가**:
1. JLS 12.4.2: Init은 단 한 번. retry 명세상 없음.
2. **부분 초기화 위험**: static block이 일부 필드만 초기화하고 예외 → 일부 필드는 의도 값, 일부는 default. retry하면 일부는 두 번 초기화 → 일관성 깨짐.
3. **happens-before 보장**: `<clinit>` 완료 = 모든 static 필드 publish. 부분 실패는 이 보장을 깨뜨림.
4. **외부 자원**: static block에서 파일/DB 자원 할당 시 retry = 누수.

**안전한 static initializer**:
- 외부 자원 접근 금지.
- 실패 가능 작업은 try-catch + fallback.
- Lazy initialization holder 패턴 사용.
- 명시적 init 메서드로 retry 제어.

---

## 5. 가지 ⑤: Unload — 클래스의 죽음

### 5.1 핵심 질문

> "클래스는 어떻게 unload되고, 왜 ClassLoader 단위인가?"

### 5.2 키워드 1 — Unload는 CL 단위

> **클래스 자체가 unload의 단위가 아니라, ClassLoader가 단위.**

ClassLoader가 GC되면 → 그 CL이 로드한 모든 클래스가 함께 unload.

### 5.3 키워드 2 — 4가지 조건 (모두 만족)

1. ClassLoader 객체가 GC root에서 unreachable.
2. 그 CL이 로드한 모든 `java.lang.Class` 객체가 unreachable.
3. 그 클래스들의 모든 인스턴스가 unreachable.
4. 다른 CL의 클래스가 이 CL의 클래스를 reference로 들고 있지 않음.

| ClassLoader | unload? |
|---|---|
| Bootstrap | 영원 (JVM 종료까지) |
| Platform | 영원 |
| Application | 사실상 영원 (main 클래스 chain) |
| **Custom** | **unload 가능** |

→ 실무에서 "Class unload" = "Custom ClassLoader unload" (Tomcat WebappCL, Spring DevTools RestartCL, OSGi bundle, ASM/Javassist 동적 CL).

### 5.4 키워드 3 — Unload 절차

```
1. Heap GC 사이클 시작
2. Marking 중 ClassLoader oop이 unreachable로 판정
3. CL의 ClassLoaderData(CLD) 객체를 dead로 마킹
4. CLD가 가리키는 모든 InstanceKlass, ConstantPool, Method dead
5. GC별 처리:
   - G1: ClassUnloadingWithConcurrentMark (기본 on)에서 동시 처리
   - ZGC: concurrent class unloading
   - Shenandoah: concurrent
6. Metaspace GC 사이클: dead CLD의 chunk를 free list로 반환
7. Code Cache: 그 클래스의 JIT 코드 invalidate
8. SystemDictionary에서 entry 제거
```

### 5.5 Tomcat 핫 리로드 흐름

```
[v1 배포]
   Tomcat → WebappCL v1 생성 → app v1 로드 → 운영

[v2 새 WAR 배포]
   Tomcat → WebappCL v2 생성 → app v2 로드
          → 트래픽 v2로 전환
          → v1의 마지막 요청 끝나길 대기
          → WebappCL v1 참조 해제 ★
          → 다음 Full GC에 v1 통째 unload
```

### 5.6 Class Redefinition (JVMTI, JRebel, DevTools)

#### JVMTI RedefineClasses

제약:
- 메서드 body 변경 가능
- 메서드 시그니처/이름 변경 불가
- 필드 추가/삭제 불가
- 클래스 hierarchy 변경 불가
- 어노테이션 변경 불가

JDK 9에서 `RetransformClasses` 추가.

#### JRebel — 더 자유로움

JVMTI + 자체 ClassLoader transformation으로 **메서드 추가, 필드 추가**까지. 원리: 새 hidden class 생성 + 옛 클래스 reference를 invokedynamic으로 redirect. 같은 클래스가 여러 버전 메모리에 공존.

비용: agent attach 오버헤드, Metaspace 누수 가능성, Hibernate/JPA 같은 클래스 identity 가정 framework 충돌, 라이센스.

#### Spring DevTools

두 CL 분리:
- **Base CL**: 변경 안 되는 라이브러리 (Spring, libs)
- **Restart CL**: 변경되는 사용자 코드

코드 변경 → Restart CL만 폐기/재생성. Base CL 유지 → 1초 안 reload.

한계:
- Base CL의 라이브러리 변경 시 적용 안 됨 (앱 재시작 필요).
- 메모리 사용량: 옛 Restart CL reference 누수 시 점점 증가.

---

## 6. 가지 ⑥: 운영 — 워밍업과 Leak 진단

### 6.1 핵심 질문

> "배포 직후 P99 latency 스파이크는 왜 일어나고, ClassLoader Leak은 어떻게 진단하는가?"

### 6.2 키워드 1 — P99 cold start 진단

```
배포 직후 latency 그래프 모양:

  P99
   │   ▲▲▲▲           ← init + JIT 비용 폭주
   │  ▲    ▲▲▲
   │ ▲       ▲▲▲▲▲▲
   │▲              ▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲▲   ← 안정 상태
   └─────────────────────────────────► time
   배포                              30s 후
```

첫 호출 비용 = Loading + Linking + Initialization + JIT 컴파일 + 캐시 미스.

P50에는 안 보이지만 P99/P99.9에 그대로 드러남. 토스/카카오뱅크/네이버 같은 곳의 "배포 후 N초 P99 스파이크" 알람의 80%가 이 영역.

**진단**:
```bash
# 어떤 클래스가 언제 init됐는지
java -Xlog:class+init=info:file=init.log MyApp

# JFR로 init + JIT 컴파일 이벤트 수집
java -XX:StartFlightRecording=filename=warmup.jfr,duration=60s MyApp
# JMC에서 jdk.ClassLoad, jdk.Compilation 분석
```

### 6.3 키워드 2 — 워밍업 5가지 기법

#### 1. Eager initialization (코드 레벨)

자주 쓰일 클래스를 시작 시점에 강제 트리거:
```java
@Component
public class WarmUpRunner implements ApplicationRunner {
    public void run(ApplicationArguments args) {
        userService.findById(0L);
        productService.list(0, 10);
    }
}
```

#### 2. Synthetic traffic (워밍업 요청)

```
[배포] ──► [self warm-up loop 30s] ──► [readinessProbe OK] ──► [LB 트래픽]
```

K8s `readinessProbe`를 워밍업 끝난 후 OK로 응답하도록 구성. Netflix 등이 canary 전 워밍업으로 사용.

#### 3. AppCDS / Dynamic CDS

```bash
# 1단계: 사용 패턴 기록
java -XX:ArchiveClassesAtExit=app.jsa -jar app.jar
# 2단계: archive 사용
java -XX:SharedArchiveFile=app.jsa -jar app.jar
```

효과: Loading/Linking 미리 메모리 매핑 → startup -20~40%. **단, `<clinit>` 자체는 여전히 lazy** (CDS는 Load/Link만 archive).

#### 4. AOT (Ahead-of-Time)

- **GraalVM Native Image**: `--initialize-at-build-time=com.foo.Bar` → 빌드 시점에 `<clinit>` 실행, 결과를 native image에 박음. 런타임 init 비용 0.
- **JEP 483 (JDK 24+)**: Leyden의 AOT class loading.
- **함정**: build-time init한 클래스에 환경별 값(hostname, secret) 박으면 안 됨.

#### 5. CRaC (Coordinated Restore at Checkpoint)

JDK 21+ OpenJDK CRaC 지원. 안정 상태 JVM 메모리 snapshot 떠놓고 다음 부팅에서 restore.

### 6.4 키워드 3 — ClassLoader Leak 5패턴

> ClassLoader의 참조 chain이 어디선가 안 풀려서 unload가 안 되는 현상. **Metaspace 누수의 가장 흔한 원인**.

#### ① ThreadLocal leak (가장 흔함)

```java
public class WebappCode {
    static ThreadLocal<UserContext> ctx = new ThreadLocal<>();
}
```
Tomcat ThreadPool 스레드(재배포 후에도 살아있음) → ThreadLocal 값 → UserContext class → WebappClassLoader **영원히 잡힘**.

#### ② JDBC Driver 정적 등록

```java
DriverManager.registerDriver(new MyDriver());
```
JDK DriverManager(Bootstrap CL) → MyDriver 인스턴스 → MyDriver class → WebappClassLoader.

해결: `DriverManager.deregisterDriver()`를 webapp shutdown 시 호출.

#### ③ JNI / Native 핸들

JNI가 Java 객체 reference를 native 메모리에 저장 → JVM이 "잡혀 있다"로 인식.

#### ④ Shutdown Hook

```java
Runtime.getRuntime().addShutdownHook(new Thread(() -> { ... }));
```
람다 안에서 webapp 클래스 참조 → JVM의 shutdown hook chain이 영원히 잡음.

#### ⑤ 정적 캐시 / Singleton / Logger

JDK의 static 캐시 (`java.beans.Introspector` 등), Logger 정적 캐시, Caffeine static cache 등에 webapp 클래스 등록.

### 6.5 Leak 진단 흐름

```
"재배포할 때마다 메모리 늘어요"
   ↓
Q: "Heap입니까 Metaspace입니까?"
   ↓
Metaspace → ClassLoader Leak 의심
   ↓
jcmd <pid> VM.classloader_stats
   → 같은 webapp의 CL이 여러 개 살아있나?
   ↓
여러 개 → leak 확정
   ↓
jmap -dump:live,format=b,file=heap.bin <pid>
   ↓
Eclipse MAT으로 열기
   ↓
"Path to GC Roots"로 ClassLoader 추적
   ↓
대부분: ThreadLocal / JDBC / JNI / Shutdown Hook / 정적 캐시 중 하나
```

### 6.6 워밍업 함정 6가지

1. **Static block에서 외부 의존성 접근**: DB connect, 외부 API가 있으면 그 시스템 죽으면 앱이 안 뜸.
2. **ExceptionInInitializerError → 영구 broken**: 워밍업이 실패하면 그 클래스는 NCDFE로 이후 모든 접근 실패. Retry 불가.
3. **Startup time 증가**: 안 쓸 수도 있는 클래스까지 init하면 startup ↑. K8s liveness 타임아웃 위험.
4. **순환 의존**: 워밍업하려고 여러 클래스를 동시 트리거하면 데드락.
5. **GraalVM build-time init**: hostname/secret 등 환경별 값이 image에 하드코딩.
6. **워밍업 ≠ 캐시 hit**: DB/Redis 캐시는 별개. 클래스/JIT만 데우면 첫 요청은 여전히 캐시 miss로 느림.

**안전한 워밍업 원칙**: static block은 비어 있게, 외부 자원 접근은 명시적 init 메서드로. 워밍업 실패는 fatal로 처리(어차피 첫 요청에서도 터졌을 것).

### 6.7 의사결정 트리

```
P99 스파이크 측정 (배포 직후 vs 안정 상태)
   │
   ├─ 차이가 작다 (수십 ms) → 그냥 둠
   │
   └─ 차이가 크다 (수백 ms ~ 수 초)
       │
       ├─ 모놀리스 + 자주 재배포
       │    → Synthetic traffic + readinessProbe 분리
       │
       ├─ Cold start 민감 (FaaS, Serverless, K8s 잦은 스케일링)
       │    → GraalVM Native Image / Project CRaC
       │
       ├─ Spring Boot 일반
       │    → AppCDS + ApplicationRunner 워밍업
       │
       └─ 라이브러리 무거움 (Hibernate, Spring 풀스택)
            → Dynamic CDS + Eager bean init
```

---

## 7. 면접 답변 워크플로우

### 7.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "Init은 누가 하고 락은 어디?" | ① WHY | ④ 12-step |
| "Init 트리거 조건?" | ② Active/Passive | 6+6 케이스 |
| "ConstantValue는 왜 트리거 안 되나?" | ② Passive | 03장 Preparation |
| "`<clinit>`이 뭐고 어떻게 합성?" | ③ clinit | 소스 순서 |
| "JLS 12.4.2 12-step?" | ④ 12-step | 3축 (state/gate/exec) |
| "순환 의존 init은?" | ④ Step 3 재진입 | 데드락 차이 |
| "부모 vs 인터페이스 init 차이?" | ④ JDK 8 default | lazy 이유 |
| "ExceptionInInitializerError 후?" | ④ erroneous | 회복 불가 |
| "Unload 조건?" | ⑤ 4조건 | CL 단위 |
| "Tomcat hot reload?" | ⑤ WebappCL | Leak |
| "배포 직후 P99 스파이크?" | ⑥ cold start | 워밍업 5종 |
| "ClassLoader Leak 90%?" | ⑥ 5패턴 | MAT 진단 |

### 7.2 답변 템플릿

> **루트 문장 한 줄 → 해당 가지 키워드 3개 순서 → 듣는 사람 표정 보고 인접 가지로**

예: "JLS 12.4.2의 12-step lock을 설명해주세요"

> "Initialization은 JVM Initializer가 Active Use 시점에 per-Class `_init_lock`을 잡고 `<clinit>`을 정확히 한 번 실행하는 단계입니다. ClassLoader는 Loading까지만, 락은 Class 객체에 항상 박혀 있습니다. (← 루트)
> 12-step을 외우지 말고 3축으로 이해하는 게 정석입니다.
> 첫째, **state machine**: loaded → linked → INITIALIZING → INITIALIZED 또는 ERRONEOUS(영구).
> 둘째, **진입 게이트**: 락 잡고 state 확인 — INITIALIZED면 통과, ERRONEOUS면 NCDFE, 다른 스레드가 INITIALIZING이면 wait, 같은 스레드면 재귀 통과, 새로 시작이면 INITIALIZING 마킹 후 락 해제.
> 셋째, **실행 + 결과 마킹**: 부모 먼저 → `<clinit>` 실행 → 정상이면 INITIALIZED + notifyAll, 예외면 ERRONEOUS.
> 가장 중요한 통찰은 **락이 보호하는 건 state transition이지 `<clinit>` 본문이 아니다**라는 점입니다. `<clinit>`은 수초~수분 걸릴 수 있는데 그동안 락을 잡고 있으면 다른 클래스의 init도 막혀버립니다. 그래서 INITIALIZING 마킹만 한 채로 락은 풀어두고, 다른 스레드는 그 state를 보고 wait합니다."

→ 면접관이 "순환 의존?" 물으면 Step 3 재진입으로, "데드락은?" 물으면 두 스레드 시나리오로.

---

## 8. 꼬리질문 트리 (가지별)

### Q1 [가지 ①]. ClassLoader가 클래스를 초기화하는 건가?

> 아니다. ClassLoader는 Loading까지만(02장). `<clinit>` 실행과 락 절차는 JVM Initializer가 한다. ClassLoader.loadClass()가 끝났다고 init이 시작된 것도 아님.
> `_init_lock`은 Class 객체가 만들어질 때 JVM이 자동 부여한 per-Class 내부 모니터. `synchronized(A.class)`로 사용자가 잡는 모니터와 별개. 12-step은 이 박혀 있는 락을 **사용하는 절차**지 만드는 절차가 아니다.
> 락이 실제로 잡히는 시점은 Active Use 바이트코드(`new`, `getstatic`, `invokestatic`, `Class.forName(true)`)가 실행되는 순간.

### Q2 [가지 ②]. Initialization 트리거 6가지를 말해보세요.

> Active Use 6가지: `new A()`, `A.staticMethod()`, `A.staticField` 접근(ConstantValue 제외), `Class.forName(true)`, JVM 시작 시 main 클래스, Subclass init 시 Parent.
> Passive Use 6가지(트리거 X): `A.X` (ConstantValue), `new A[10]` (배열), `Class.forName(false)`, `A.class` literal, `obj instanceof A`, `(A) obj`.
> 기준은 메모리 위치(Stack/Heap)가 아니라 **그 클래스의 코드/값이 실제로 의미 있게 사용되는가**.

**Q2-1: 왜 `A.class`는 트리거 안 되나?**
> JLS 15.8.2: `T.class`는 그 클래스의 `java.lang.Class` mirror를 반환할 뿐, 클래스 자체를 사용하지 않음. Loading+Linking은 필요(Class 객체가 있어야), Initialization은 안 함. 그래서 reflection으로 lazy init이 가능: `Class<?> c = Foo.class; c.getDeclaredConstructor().newInstance();`에서 init은 `newInstance` 시점.

**Q2-2: ConstantValue가 박히는 조건?**
> `static final` + compile-time constant expression: primitive literal, String literal, primitive constant expression (`1 + 2`), 다른 ConstantValue 참조.
> NOT: `new String("hi")`, `compute()` 호출, `new Date()`, 배열(절대 ConstantValue 아님).

### Q3 [가지 ③]. 다음 코드의 출력은?

```java
class Parent { static { sout("P static"); } { sout("P inst"); } Parent() { sout("P ctor"); } }
class Child extends Parent { static { sout("C static"); } { sout("C inst"); } Child() { sout("C ctor"); } }
public class Test { public static void main(String[] args) { new Child(); new Child(); } }
```

> ```
> P static       ← Parent 초기화 (Child 트리거 → 부모 먼저)
> C static       ← Child 초기화
> P inst         ← 첫 new Child() — 부모 instance initializer
> P ctor
> C inst
> C ctor
> P inst         ← 두 번째 new Child() — static은 한 번뿐, instance는 매번
> P ctor
> C inst
> C ctor
> ```

**Q3-1: static vs instance initializer 실행 순서?**
> Static: 클래스 로드 시 한 번, 부모 → 자식. Instance: 인스턴스 생성 시 매번, 부모 → 자식. 한 클래스 안에서 static initializer와 static field initializer는 소스 순서대로. instance initializer도 마찬가지(생성자 본문보다 먼저).

### Q4 [가지 ④]. 순환 의존 초기화는?

> ```java
> class A { static int x = B.y; }
> class B { static int y = A.x; }
> ```
> JLS 12.4.2 Step 3: "이 스레드가 이미 그 클래스를 init 중이면 그냥 return".
> 시나리오: A 시작(state(A)=INITIALIZING) → B.y 접근 → B 시작 → A.x 접근 → state(A)==INITIALIZING이고 같은 스레드 → Step 3 return → A.x=0(default) → B.y=0 → B 완료 → A로 돌아옴 → A.x=B.y=0.
> 결과: 둘 다 0. 데드락 아니지만 비직관적.

**Q4-1: 두 스레드 다른 클래스로 데드락은?**
> 가능. T1이 A 락 잡고 init 중 → B 트리거 → B 락 대기. T2가 B 락 잡고 init 중 → A 트리거 → A 락 대기. → 데드락. JVM 자동 감지 안 함. `jstack`으로 두 스레드가 서로의 `<class init>` lock 대기로 보임. 회피: static block에서 다른 클래스 호출 안 하거나 한 방향 정렬.

### Q5 [가지 ④]. ExceptionInInitializerError가 나면?

> 영구 erroneous 상태. 이후 모든 접근에서 NoClassDefFoundError throw (원인: 이전 EIIE). 회복 불가 — 그 ClassLoader 폐기 후 새 CL로 다시 로드해야 함.
> **왜 retry 못 하나**: (1) JLS 12.4.2가 init은 단 한 번, (2) 부분 초기화 위험(static block이 일부만 실행되고 예외), (3) happens-before 보장 깨짐, (4) 외부 자원 누수.

**Q5-1: 안전한 static initializer는?**
> (1) 외부 자원 접근 금지(파일/DB/네트워크), (2) 실패 가능 작업은 try-catch + fallback, (3) Lazy init holder 패턴, (4) 명시적 init 메서드로 retry 제어.

### Q6 [가지 ④]. 인터페이스 init은 클래스와 어떻게 다른가?

> 클래스: 부모 클래스가 항상 먼저 초기화. 인터페이스: 일반적으로 implements한 클래스 초기화 시 함께 init **안 함**. 예외: JDK 8+의 **default method를 가진 인터페이스**만 그 인터페이스 구현 클래스 init 시 같이 init.
> 왜 default method 있을 때만: JDK 7 이전 인터페이스는 코드 실행 없음 → init 의미 없음. JDK 8+ default method = 실행 코드 → init이 의미 있을 수 있음. 한 클래스가 수십 개 인터페이스 구현 가능 → 모두 미리 init하면 startup 느림.

### Q7 [가지 ⑤]. ClassLoader unload 조건과 실제로 unload되는 CL은?

> 4조건 모두 만족: (1) CL 객체 unreachable, (2) 로드한 모든 Class 객체 unreachable, (3) 모든 인스턴스 unreachable, (4) 다른 CL의 코드가 이 CL 클래스 참조 안 함.
> 실제 unload되는 건 **Custom CL**(Tomcat WebappCL, Spring DevTools RestartCL, OSGi bundle, ASM/Javassist 동적 CL). Bootstrap/Platform/Application은 영원.
> 절차: Heap GC가 CL oop dead 판정 → CLD dead 마킹 → Metaspace cleanup에서 chunk free → Code Cache JIT 코드 invalidate → SystemDictionary entry 제거.

**Q7-1: Spring DevTools가 어떻게 빠른 reload를?**
> 두 CL 분리. Base CL(Spring, dependency — 변경 X)과 Restart CL(사용자 코드 — 변경 시 폐기/재생성). 파일 변경 감지 → Restart CL만 폐기 → 새 Restart CL 생성. Base CL 그대로 → init 비용 없음 → 1초 안 reload.
> 한계: Base CL 라이브러리 변경 시 적용 안 됨, JPA entity 메타데이터 변경 시 캐시 invalidate, 옛 Restart CL reference 누수 시 메모리 증가.

**Q7-2: JRebel과 DevTools 차이?**
> JRebel은 메서드 추가/필드 추가까지 지원. JVMTI agent + ClassLoader 우회로 새 hidden class 생성 + 옛 클래스 reference를 invokedynamic으로 redirect. 같은 클래스 여러 버전 공존.
> 비용: agent attach 오버헤드, Metaspace 증가(옛 버전 보존), Hibernate/JPA 같은 클래스 identity 가정 framework 충돌, 라이센스. DevTools는 ClassLoader 교체 방식이라 메서드 시그니처 변경 시 reload 안 됨.

### Q8 (Killer) [가지 ⑥]. 배포 직후 P99 latency가 3초 튀었다가 30초 후 200ms로 안정화. 진단과 해결?

> **원인**: 첫 트래픽이 받는 cold-start 비용. (1) Class Initialization — hot path 클래스의 `<clinit>`이 첫 요청에서 실행, static block에서 DB connection pool 초기화, config 로드. (2) JIT 컴파일 — 메서드가 C1/C2 임계값 넘기 전까지 interpreter로 실행. (3) 캐시 cold — CPU L1/L2, Spring bean, JDBC statement, Hibernate session factory 비어 있음.
>
> **진단**:
> ```bash
> java -Xlog:class+init=info:file=init.log MyApp
> java -XX:StartFlightRecording=filename=warmup.jfr,duration=60s MyApp
> # JMC에서 jdk.ClassLoad, jdk.Compilation 분석
> ```
>
> **해결 단계별**:
> 1. **Synthetic traffic + readinessProbe 분리**: K8s readinessProbe를 워밍업 끝난 후 OK로. LB 트래픽 안 붙은 상태에서 자기 자신에게 mock 요청 N번.
> 2. **Spring `ApplicationRunner`로 eager init**: 주요 빈을 직접 호출.
> 3. **AppCDS**: `-XX:ArchiveClassesAtExit=app.jsa` + `-XX:SharedArchiveFile=app.jsa`. Loading/Linking 빨라짐(init은 여전히 lazy).
> 4. **GraalVM Native Image**: cold start 0초 가능, reflection/dynamic load 제약 큼. Spring Boot 3+ `spring-aot`로 자동화.
> 5. **CRaC**: 안정 상태 JVM 메모리 snapshot 떠놓고 다음 부팅에서 restore.

**Q8-1: Eager init 함정?**
> (1) Static block에서 외부 의존성 접근 → 그 시스템 죽으면 앱 자체가 안 뜸, (2) ExceptionInInitializerError → 영구 broken, retry 불가, (3) Startup 증가, K8s liveness 위험, (4) 순환 의존 데드락, (5) GraalVM build-time init이 환경별 값(hostname/secret) 박힘, (6) 워밍업 ≠ 캐시 hit.

**Q8-2: GraalVM `--initialize-at-build-time` 동작과 함정?**
> 동작: 빌드 시점에 지정 클래스의 `<clinit>` 실행 → static 필드 상태를 native image binary에 박음 → 런타임 init 비용 0.
> 함정: (1) 환경별 값 하드코딩 — `static final String HOST = System.getenv("HOST");`이 빌드 머신 env 박힘, (2) Random/Time — `static final UUID ID = UUID.randomUUID();`가 모든 인스턴스 같은 UUID, (3) Resource 접근 — 빌드 머신 파일이 production에 없음.
> 해결: `@RuntimeInitialization`, reflection-config.json, Spring AOT.

### Q9 (Killer) [가지 ⑥]. ClassLoader Leak 90%는 어디서?

> 5패턴 중 하나.
> ① **ThreadLocal**: Tomcat ThreadPool 스레드(재배포 후에도 살아있음) → ThreadLocal 값 → 클래스 → 옛 WebappCL.
> ② **JDBC Driver**: `DriverManager.registerDriver()`로 Bootstrap CL이 driver 인스턴스 보관 → 옛 CL 잡음. 해결: `DriverManager.deregisterDriver()`를 shutdown 시.
> ③ **JNI/Native**: native가 Java reference 보관.
> ④ **Shutdown Hook**: 람다 안의 webapp 클래스 참조가 JVM hook chain에 영구.
> ⑤ **정적 캐시 / Logger**: JDK static 캐시(`Introspector` 등), Caffeine static, Logger 정적 캐시.
>
> **진단 흐름**: jcmd VM.classloader_stats로 중복 CL 확인 → heap dump → MAT의 Path to GC Roots로 ClassLoader 추적 → 5패턴 중 하나 식별.

### Q10 [가지 ②]. JVM 시작 시 모든 클래스가 자동 init되나요?

> 아니오. JVM은 **lazy initialization** 모델. 트리거가 없으면 영원히 init 안 함.
> 자동 init되는 건: (1) Bootstrap이 로드하는 핵심 클래스, (2) `main` 메서드 가진 클래스, (3) main() 실행 중 다른 트리거.
> Lazy인 이유: (1) Startup 가속 — classpath 수만 개 클래스를 모두 init하면 수십 초~수 분, (2) 자원 절약, (3) Metaspace 보호.
> 함정: startup-time 검증을 static block에 넣어도 그 클래스를 안 쓰면 검증 안 됨 → 첫 트래픽에서 ExceptionInInitializerError로 발견.

---

## 9. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 이내로 그릴 수 있다 (루트 + 6가지 + 각 키워드 3개)
- [ ] 가지 ① WHY: Initialization 주체(JVM Initializer)와 `_init_lock`의 정체를 설명한다
- [ ] 가지 ① WHY: 락은 Class 객체에 항상 박혀 있고 Active Use 시점에만 잡힌다는 사실을 말한다
- [ ] 가지 ② 트리거: Active 6 + Passive 6 케이스를 적고 각각 이유를 한 줄로 말한다
- [ ] 가지 ② 트리거: ConstantValue가 박히는 조건과 inline 부작용을 설명한다
- [ ] 가지 ③ clinit: 왜 javac가 자동으로 합성하는지 4가지 보장을 말한다
- [ ] 가지 ③ clinit: static initializer + static block 합성 순서를 그린다
- [ ] 가지 ④ 12-step: 3축(state machine / 진입 게이트 / 실행+마킹)으로 이해를 설명한다
- [ ] 가지 ④ 12-step: 락이 보호하는 건 state transition이지 `<clinit>` 본문이 아니라는 핵심 통찰을 말한다
- [ ] 가지 ④ 12-step: 순환 의존(같은 스레드 재진입)과 진짜 데드락(두 스레드 교차 락)을 구분한다
- [ ] 가지 ④ 12-step: 부모는 항상 먼저, 인터페이스는 default method 있을 때만 init하는 이유를 적는다
- [ ] 가지 ④ 12-step: ExceptionInInitializerError → 영구 erroneous, 회복 불가의 4가지 이유를 말한다
- [ ] 가지 ⑤ Unload: 4조건과 실제 unload되는 CL(Custom만)을 말한다
- [ ] 가지 ⑤ Unload: Tomcat 핫 리로드 흐름과 JVMTI/JRebel/DevTools 차이를 적는다
- [ ] 가지 ⑥ 운영: P99 cold start 진단 절차(Xlog/JFR)와 워밍업 5종을 적는다
- [ ] 가지 ⑥ 운영: ClassLoader Leak 5패턴(ThreadLocal/JDBC/JNI/Hook/정적캐시)을 적는다
- [ ] 가지 ⑥ 운영: Leak 진단 흐름(VM.classloader_stats → heap dump → MAT → Path to GC Roots)을 말한다
- [ ] 8장 꼬리질문 10개에 막힘없이 답한다

---

## 다음 단계

01-class-lifecycle 챕터 종료. 다음:
- → [02-runtime-data-areas](../02-runtime-data-areas/): Heap, Metaspace, Stack의 내부 구조
- → [03-execution-engine](../03-execution-engine/): Interpreter, JIT 풀버전

## 참고

- **JLS §12.4 Initialization**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.4
- **JVMS §5.5 Initialization**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.5
- **JLS §13 Binary Compatibility**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-13.html
- **JVMTI Specification**: https://docs.oracle.com/en/java/javase/21/docs/specs/jvmti.html
- **HotSpot instanceKlass.cpp**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/oops/instanceKlass.cpp
- **MAT (Eclipse Memory Analyzer)**: https://www.eclipse.org/mat/
- **Spring Boot DevTools**: https://docs.spring.io/spring-boot/docs/current/reference/html/using.html#using.devtools
- **OpenJDK CRaC**: https://openjdk.org/projects/crac/
