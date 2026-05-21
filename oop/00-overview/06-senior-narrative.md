# 06. 시니어 운영 시각으로 풀어쓰는 OOP — 종합편

> **이 문서의 한 줄 목표**: 80명짜리 팀에서 5년 운영해본 시니어가 OOP를 "쭉" 풀어내듯, 본질·장단점·함수형과의 관계·자바의 하이브리드 진화까지 한 호흡에 잡는다.

---

## 0. 이 문서를 읽는 법

이 문서는 챕터별 깊이 학습(`01~12`)에 들어가기 전, **"시니어가 머릿속에 갖고 있는 OOP 지도"** 를 통째로 옮긴 거예요. 각 섹션은 이후 챕터 어디에서 깊이 들어가는지 링크로 연결돼 있어요.

```
[Excalidraw: OOP-마인드맵]
                   "사람 문제 해법" (협업)
                          │
              ┌───────────┴───────────┐
        4대 특성                   5대 원칙(SOLID)
        ├ 캡슐화 ★ (진짜 핵심)         ├ SRP
        ├ 다형성 ★ (진짜 핵심)         ├ OCP ★ (제일 중요)
        ├ 추상화 △ (양날의 검)         ├ LSP
        └ 상속   ✗ (현장에선 회피)     ├ ISP
                                     └ DIP
                          │
              ┌───────────┴───────────┐
        장점 영역                    함정 영역
        ├ 신입 온보딩 ↑              ├ 추상화 세금
        ├ 변경 격리                  ├ Mock Hell
        ├ 도메인 모델링              ├ Fragile Base Class
        └ 협업 계약                  └ 동시성 취약
                          │
                   현대의 해답: 하이브리드
                   (Kotlin / Java 8+ / Scala / C#)
```

---

## 1. OOP는 사실 기술이 아니라 "사람 문제" 해법

4대 특성 외우는 거 의미 없어요. 본질은 **"수십~수백 명이 같은 코드베이스 만지는데 어떻게 안 부딪치게 할까"** 에서 출발한다는 것.

90년대 C 시절, 누가 전역변수 하나 건드리면 다른 팀 모듈이 죽었어요. 그래서 코드 레벨에서 사회적 계약을 강제한 게 OOP예요.

- **내 데이터 너 못 만져** → 캡슐화
- **인터페이스만 약속해** → 추상화
- **기존 거 안 건드리고 확장만 해** → 다형성

대형 프랜차이즈에서 80명 팀 굴려보면 진짜 와닿아요. 신입이 `OrderService` 클래스 이름만 봐도 "아 주문 도메인이구나" — 인지 부하가 확 줄어요. 함수형으로 평평하게 깔린 코드베이스에서 신입한테 "Order 관련 어디 있어요?" 물어보면 grep 해야 돼요.

> **OOP의 진짜 가치는 런타임이 아니라 신입 온보딩 시간에 있어요.**

→ 깊이 학습: [01-object-and-collaboration](../01-object-and-collaboration/), [03-responsibility-assignment](../03-responsibility-assignment/)

---

## 2. OOP의 함정 — 추상화 세금이 비싸요

```
[Excalidraw: 추상화-세금]
   Controller → Facade → Service → Manager → Processor → Repository → SQL
       │         │         │         │           │            │          │
     1단계     2단계     3단계     4단계       5단계        6단계      실제 한 줄
   ────────────────────────────────────────────────────────────────────────────
   "여기 한 줄 고치고 싶어요"
   → 인터페이스 4개, 구현체 4개, 테스트 8개 같이 수정해야 함
   → 추상화가 변화를 막아요, 도와주는 게 아니라
```

운영해보면 알아요:

- **상속은 현장에선 거의 안 써요.** `extends`는 함정이라는 게 2010년대 이후 합의(Effective Java 아이템 18 — "상속보다는 컴포지션"). 레거시에 5단계 깊이 상속 트리가 도사리고 있고, 부모 클래스 하나 바꾸면 어디서 터질지 몰라요 — **fragile base class problem**.
- **추상화도 마찬가지.** "쓰지도 않을 확장점"이 코드 전체에 박혀있어요. YAGNI 위반.

그래서 시니어 스타일은 **"4대 특성 다 쓰는 게 잘 쓰는 거"가 아니에요.**

| 특성 | 시니어의 사용 빈도 | 이유 |
|---|---|---|
| 캡슐화 | ★★★★★ 항상 | 변경 격리의 핵심 |
| 다형성(인터페이스) | ★★★★★ 항상 | 확장점, 테스트성 |
| 추상화 | ★★★ 선택적 | 정말 변할 축에만 핀포인트 |
| 상속 | ★ 거의 회피 | 컴포지션으로 대체 |

→ 깊이 학습: [08-inheritance-vs-composition](../08-inheritance-vs-composition/)

---

## 3. 테스트 — OOP의 가장 큰 장점이자 가장 큰 거짓말

**맞는 부분**: 인터페이스 기반으로 짜면 DI가 자연스럽고, mock으로 단위 테스트 격리가 쉬워요. Spring이 DI를 1급 시민으로 박은 이유 — 테스트성을 프레임워크 레벨에서 강제한 거.

**틀린 부분**: 현장에선 **mock hell**이 와요.

```java
// 단위 테스트 하나 짜는데...
@Mock OrderRepository orderRepo;
@Mock PaymentGateway paymentGw;
@Mock InventoryService inventory;
@Mock NotificationService notif;
@Mock UserService userSvc;
@Mock CouponService couponSvc;
@Mock AuditLogger audit;
// → mock 7개 세팅, given/when/then 30줄
// → 정작 검증하는 건 "내가 짠 코드가 내가 mock한 대로 동작하더라"
// → 동어반복. 리팩토링 한 번에 다 깨짐
```

> **운영해보면 — mock 기반 단위 테스트 1000개보다 진짜 DB 띄운 통합 테스트 50개가 더 가치 있어요.**

함수형은 여기가 달라요. 순수 함수라 mock이 필요 없어요. 입력 → 출력만 보면 돼요. "OOP의 테스트성은 만들어낸 문제를 풀고 있는 거다" — 함수형 진영의 이 비판, 일리가 있어요.

---

## 4. OCP/SOLID — 진리지만 비용이 있다

### 4-1. 5대 원칙 한 줄 정리

| 원칙 | 한 줄 정의 | 현장 가치 |
|---|---|---|
| **S**RP — 단일 책임 | 한 클래스는 한 가지 변경 이유만 | ★★★ 좋은 클래스 분리의 기본 |
| **O**CP — 개방-폐쇄 | 확장엔 열려, 수정엔 닫혀 | ★★★★★ 가장 중요 |
| **L**SP — 리스코프 치환 | 자식이 부모 자리에서 깨지면 안 됨 | ★★ 상속 안 쓰면 신경 덜 씀 |
| **I**SP — 인터페이스 분리 | 안 쓰는 메서드에 의존하지 마라 | ★★★ 인터페이스 비대화 방지 |
| **D**IP — 의존성 역전 | 구현 말고 추상에 의존 | ★★★★ DI 컨테이너의 철학 |

### 4-2. 시니어가 보는 OCP가 제일 중요한 이유

결제 모듈에 카드사 하나 추가될 때마다 기존 코드 까서 if문 추가하면 1년 안에 죽어요.

```java
// ❌ OCP 위반 — 신규 카드사마다 이 메서드 수정
if (card.equals("KB")) { ... }
else if (card.equals("Shinhan")) { ... }
else if (card.equals("Hyundai")) { ... }
// 6개월 뒤: else if 47개...

// ✅ OCP 준수 — 인터페이스 + Strategy
interface PaymentProcessor { Result process(Payment p); }
// 신규 카드사: 구현체 하나 추가, 기존 코드 0줄 수정
```

### 4-3. 그런데 OCP가 만능이 아닌 이유

YAGNI(You Ain't Gonna Need It). 변할지 안 변할지 모르는 축에 인터페이스 박아두면, 비용만 있고 이득은 없어요. 코드는 길어지고 가독성은 떨어지고 새로 들어온 사람은 헷갈려요.

> **시니어의 일은 "이 축은 진짜 변한다"는 도메인 직관을 길러서 거기에만 추상화를 박는 것.** 이게 주니어/시니어 갈리는 지점.

판단 기준 한 가지:

- **3번 이상 같은 패턴으로 변경된 적이 있나?** → 추상화 박을 자격 있음
- **"앞으로 변할 것 같은데?"** 만으로는 박지 마세요 → 100% 안 변함

→ 깊이 학습: [07-flexible-design](../07-flexible-design/), [22-tradeoff-master-table](../22-tradeoff-master-table/)

---

## 5. 함수형 vs OOP — 본질은 "상태(State)를 어떻게 다루느냐"

표면적으로는 "데이터+행위 묶음 vs 분리"라고 배우는데, 본질은 **상태 처리 방식**이에요.

```
[Excalidraw: OOP-vs-FP-상태처리]

         OOP                            함수형(FP)
   ┌─────────────────┐              ┌─────────────────┐
   │  Account 객체    │              │  account_v1     │
   │  ─────────────  │              │  ↓ deposit(100) │
   │  balance: 1000  │   →deposit→  │  account_v2     │
   │  변이!          │              │  (새 객체)       │
   │  balance: 1100  │              │  ↓ deposit(50)  │
   └─────────────────┘              │  account_v3     │
   같은 객체, 시간에 따라 변함        └─────────────────┘
                                    매번 새 객체, 과거 상태 보존

   "시간"이 객체 안에 있음            "시간"이 데이터 흐름에 있음
```

- **OOP**: 상태를 객체에 캡슐화하고, 메서드로 변이(mutate). 시간에 따라 변하는 세계 모델링에 강함 (주문 상태머신, 게임 캐릭터, 사용자 세션).
- **함수형**: 상태를 불변(immutable)으로 두고, **새 상태를 만들어내요**. 동시성/분산/시간여행 디버깅에 강함.

---

## 6. 동시성 시대에 왜 OOP가 무너지는가 — 메커니즘 깊이 보기

이게 사용자가 부가 설명 요청한 핵심 포인트예요. 한 단계씩 짚어볼게요.

### 6-1. 객체 = 가변 상태(state)의 캡슐 → 멀티스레드에서 폭탄

```java
class Counter {
    private int count = 0;  // ← 가변 상태
    public void increment() { count++; }  // ← 비원자 연산
}
// 스레드 100개가 increment() 동시 호출 → 결과는 100이 아니라 73, 89, ...
// 이유: count++ 는 read → +1 → write 3단계, 중간에 다른 스레드가 끼어듦
```

해법은 `synchronized`, `AtomicInteger`, `ReentrantLock`. 근데 이건 시작에 불과해요.

### 6-2. 깊은 객체 그래프 + 가변성 → 동기화 경계를 설정할 수 없음

```
Order ─┬─ User
       ├─ List<Item>
       ├─ Payment ─── Card
       └─ Shipping ── Address ── Zone
```

이 객체 그래프 중 어디까지 락을 걸어야 안전한가? 답이 없어요. 락 범위를 좁히면 race condition, 넓히면 성능 폭망. **시니어 5명이 모여서 토론해도 답이 안 나오는 게 정상이에요.**

### 6-3. 락 순서가 코드 전체에 흩어져 → 데드락 분석 불가

```
스레드 A: Order 락 → Payment 락 요청
스레드 B: Payment 락 → Order 락 요청
→ 데드락. 둘 다 영원히 기다림
```

대형 시스템에서 객체가 1000개, 메서드가 10000개면 락 순서 추적이 인간의 인지 범위를 넘어요. **"이 시스템은 데드락이 안 난다"고 확신할 수 있는 사람이 없어요.**

### 6-4. 스레드당 1요청 모델 → 톰캣 200 스레드 한계

전통 OOP 서버는 요청마다 스레드 하나 잡아요(Servlet 모델). I/O 블로킹 중에도 스레드는 점유. 동시 사용자 10000명? 스레드 10000개 못 만들어요 (메모리, 컨텍스트 스위칭 비용). 200~500이 한계.

→ 이걸 뚫으려고 **비동기/논블로킹** 도입 → 콜백 헬 → **함수형 합성**(CompletableFuture, Mono/Flux)이 답으로 등장.

### 6-5. 액터 모델로 우회? 그건 OOP 위에 함수형 메시지 패싱을 얹은 것

Akka, Erlang OTP가 "객체 = 액터, 통신 = 메시지"로 동시성 문제를 해결했는데, 자세히 보면:

- 액터 내부 상태는 외부에서 못 만짐 → **극단적 캡슐화**
- 액터끼리는 불변 메시지만 주고받음 → **불변성**
- 메시지 처리 = 한 번에 하나씩 → **순차성**

이건 OOP라기보다 **OOP의 좋은 부분만 남기고 나머지를 함수형 원칙으로 채운** 모델이에요. **Alan Kay가 1970년대에 말한 "진짜 OOP"가 이 모습이었고**, 우리가 90년대부터 써온 Java식 OOP는 사실 그 정신의 변형/타락이라는 비판도 있어요.

→ 깊이 학습: [01-object-and-collaboration](../01-object-and-collaboration/) (메시지 중심 OOP)

---

## 7. 함수형이 동시성 시대에 살아남는 이유

대칭적으로 풀어볼게요.

### 7-1. 불변(Immutability) → 공유해도 안전, 락 불필요

```java
record Point(int x, int y) {}  // 불변
// 스레드 1000개가 같은 Point를 동시에 읽어도 절대 안전
// 변경이 필요하면? 새 Point 만들기. 원본은 그대로
```

락이 필요한 이유는 "공유 + 변이" 때문. **변이를 없애면 락이 필요 없어요.** 가장 단순하고 가장 강력한 해법.

### 7-2. 순수 함수(Pure Function) → 시점 무관, 어디서 호출해도 같음

```java
int add(int a, int b) { return a + b; }
// 스레드 1번이 호출하든, 1000개가 동시에 호출하든, 1시간 뒤에 호출하든
// 같은 입력 (3, 5) → 같은 출력 8
// → 캐싱 가능, 병렬화 가능, 재시도 안전
```

### 7-3. 부작용 격리 → 안전 영역과 위험 영역 명확히 분리

함수형 언어는 부작용(I/O, DB 쓰기, 네트워크)을 **타입 시스템으로 격리**해요. Haskell의 `IO Monad`, Scala의 `IO/ZIO`. 위험한 코드와 안전한 코드의 경계가 컴파일러 레벨에서 보장돼요.

### 7-4. 함수가 1급 시민 → 작업(work)을 데이터처럼 전달

```java
Stream.of(orders)
    .parallel()                  // ← 함수형이라 자동 병렬화 안전
    .map(this::validate)         // 함수를 데이터처럼 전달
    .filter(Order::isValid)
    .forEach(this::process);
```

함수가 값이라서 **스레드풀, 액터, 파이프라인에 자연스럽게 흘러갈 수 있어요.** OOP에선 작업을 전달하려면 `Runnable`, `Callable`로 객체화해야 해요 — 어색.

### 7-5. 데이터 흐름 중심 → 스트림/리액티브와 자연 매칭

함수형은 "데이터가 함수들의 파이프를 흐른다"는 모델이라, 스트림 처리(Kafka, Flink, Spark), 리액티브(WebFlux, RxJava), 백프레셔(backpressure)와 사고 방식이 같아요. **현대 대규모 시스템의 모양이 이미 함수형이에요.**

---

## 8. Java/Spring은 왜 OOP를 선택했나 — 역사적 맥락

- **Java(1995)**: C++의 복잡함(다중상속, 포인터, 수동 메모리) 빼고 OOP 좋은 부분만 + GC + JVM 이식성. **타겟이 엔터프라이즈 SI 시장이었어요.** "수백 명이 같이 짜는 거대 시스템" — OOP가 사회적 계약 코드라서 딱 맞았음.
- **Spring(2003)**: J2EE EJB의 무거움에 반발. DI + AOP + POJO로 엔터프라이즈 OOP를 정제. 트랜잭션·보안·로깅 같은 횡단 관심사를 AOP로 빼고, 비즈니스 로직은 POJO로 — **OOP 이상에 가장 가까운 프레임워크**.

본질 — **"수많은 개발자가 협업하는 SI 시장"이 OOP를 선택한 거예요.** Java/Spring은 그 시장에 답을 준 거고요.

---

## 9. 그럼 다른 언어들은 왜 다르게 갔나

| 언어 | OOP 채택도 | 이유 |
|---|---|---|
| **Go** | 거의 안 채택 (클래스 X, 상속 X) | 구글 내부 C++ deep-inheritance 트라우마. 단순함이 최우선 |
| **Rust** | 부분 채택 (trait만, 상속 X) | 안전성 + 성능. "공유된 가변 상태"를 컴파일 타임에 차단 |
| **JavaScript** | 외형만 채택 (ES6 class는 prototype 위 설탕) | 동적 + 비동기 우선 |
| **Kotlin** | 하이브리드 (OOP + FP 균형) | Java 호환성 유지하며 FP 흡수 |
| **Scala** | 강한 하이브리드 (OOP + FP 동등) | 학술적 완성도 + JVM |
| **Erlang/Elixir** | Alan Kay 원형 (액터 + 메시지) | 통신사 99.999% 가용성 요구 |
| **Haskell** | OOP 거부 (순수 FP) | 학술/연구. 부작용 격리 극단 |

> **핵심 통찰**: 언어의 OOP 채택도는 **타겟 시장의 협업 규모와 동시성 요구**에 비례해요. SI 시장 = OOP 강함. 시스템/동시성 시장 = FP/하이브리드.

---

## 10. Java 람다 — 하이브리드 진화는 살아남기 위한 수단인가?

사용자가 정확히 짚은 포인트. 결론부터: **둘 다 맞아요. 명백한 생존 전략 + 동시에 진짜 하이브리드.**

### 10-1. 시점 정정: 람다는 JDK 11이 아니라 JDK 8 (2014년)

| JDK 버전 | 출시 | 함수형/현대화 기능 |
|---|---|---|
| **JDK 8** | 2014.03 | **Lambda, Stream API, Optional, CompletableFuture, java.time** ← 핵심 |
| JDK 9 | 2017.09 | Module, JShell |
| JDK 11 | 2018.09 | `var` (지역변수 타입추론), HTTP Client, ZGC |
| JDK 14 | 2020.03 | Records (preview), Switch Expression |
| JDK 16 | 2021.03 | Records (정식) |
| JDK 17 LTS | 2021.09 | Sealed Class (정식), Pattern Matching (preview) |
| JDK 21 LTS | 2023.09 | **Virtual Thread (정식), Pattern Matching, Sequenced Collection** ← 핵심 |
| JDK 25 LTS | 2025.09 | Stable Values, Module Import |

> 람다가 들어온 건 **2014년 JDK 8**. JDK 11(2018)에는 `var`가 추가됐어요 — 람다와 헷갈리기 쉬운 부분이에요.

### 10-2. 왜 2014년이 그렇게 늦었나 — Oracle의 위기감

```
[Excalidraw: Java-FP-흡수-타임라인]

  2004 ─── Scala 출시 (JVM 위 FP)
  2007 ─── Clojure 출시 (JVM 위 LISP)
  2009 ─── Node.js (콜백 + 함수형)
  2011 ─── Kotlin 발표
  2013 ─── Spring Reactor 시작 (리액티브 등장)
  ─────────────────────────────────────
  2014 ─── ★ Java 8 Lambda + Stream  ← Oracle "이제는 안 되겠다"
  ─────────────────────────────────────
  2016 ─── Kotlin 1.0
  2017 ─── Google Android Kotlin 공식
  2018 ─── Spring WebFlux 정식
  2023 ─── Java 21 Virtual Thread
```

- Scala는 이미 2004년부터 JVM 위에서 함수형을 했고
- Clojure도 있었고
- Node.js는 비동기 + 함수형으로 백엔드 시장을 흔들었고
- Kotlin이 나와서 Java를 위협하고 있었음

**Oracle은 Java가 "낡은 언어"가 될까봐 두려웠어요.** Scala/Kotlin이 JVM 위에서 잘 돌아가니까, "JVM은 살리고 Java는 죽이는" 시나리오가 가능했거든요. 그래서 람다 + Stream + Optional + CompletableFuture를 **한꺼번에** 박았어요. 이건 명백한 생존 전략.

### 10-3. 그런데 동시에 진짜 하이브리드이기도 해요

생존 전략으로 시작했지만, 결과적으로 Java는 **진정한 하이브리드 언어**가 됐어요. 이후 흐름을 보면:

| 기능 | 도입 | 어느 패러다임? |
|---|---|---|
| Lambda | Java 8 | FP — 함수 일급 시민화 |
| Stream API | Java 8 | FP — map/filter/reduce |
| Optional | Java 8 | FP — null의 모나드적 처리 |
| CompletableFuture | Java 8 | FP — 함수 합성 기반 비동기 |
| Records | Java 16 | FP — 불변 데이터 클래스 |
| Sealed Class | Java 17 | FP — Sum Type (ADT) |
| Pattern Matching | Java 21 | FP — 구조 분해 매칭 |
| Virtual Thread | Java 21 | 동시성 — 스레드 모델 자체 변경 |

**OOP가 죽은 게 아니라, OOP가 함수형을 흡수해서 더 강해진 거예요.** Records + Sealed + Pattern Matching 조합은 사실상 Scala/Kotlin과 같은 표현력이에요.

### 10-4. 그런데 "진짜 함수형"은 아니에요 — 한계 짚기

Java의 하이브리드에는 명확한 한계가 있어요:

- **함수가 완전한 1급 시민이 아님**: 함수 타입은 사실 `Function<T,R>` 같은 SAM(Single Abstract Method) 인터페이스의 인스턴스. 진짜 first-class function이 아니라 객체 위 설탕.
- **불변성 강제 안 함**: `record`는 권장이지 강제가 아님. `final` 안 붙은 필드 여전히 자유.
- **부작용 격리 안 함**: 어디서든 I/O, DB 쓰기, 시간 함수 호출 가능. 타입 시스템이 부작용을 추적 못 함 (Haskell의 IO Monad와 비교).
- **꼬리 재귀 최적화 없음**: 깊은 재귀 짜면 StackOverflow.

> **즉, Java의 하이브리드는 "FP의 형식은 가져왔지만 정신은 다 못 가져왔어요."** Kotlin/Scala가 한 발 더 나가있고, 진짜 FP를 원하면 Haskell/F#으로 가야 돼요.

### 10-5. 결론 — "살아남기 위한 수단"이자 "시대정신의 정답"

```
[Excalidraw: 패러다임-생존-그래프]

  순수 OOP ↘
            ↘
              ↘ 동시성 시대 도래
                ↘
                  └─→ 하이브리드(Java 8+/Kotlin/Scala/C#/Swift/Rust) ← 살아남는 영역
                  ┌─→
                ↗
              ↗
            ↗
  순수 FP  ↗
  (진입장벽 + 산업 채택 어려움)
```

- **순수 OOP**는 동시성 시대를 못 넘김
- **순수 FP**는 진입장벽 + 도메인 모델링 어색해서 산업 표준 못 됨
- **결국 살아남는 건 두 패러다임을 다 흡수한 언어** — Java 8+, Kotlin, Scala, C#, Swift, Rust, TypeScript

그러니까 사용자 질문에 답하면 — **"맞아요. Java의 람다/Stream/Virtual Thread는 살아남기 위한 생존 수단이자 동시에 옳은 방향이었어요."** Oracle이 위기감 없었다면 안 했을 거고, 그랬다면 Java는 2020년대에 COBOL 같은 운명이 됐을 거예요.

→ 깊이 학습: [09-functional-paradigm](../09-functional-paradigm/), [10-java-evolution](../10-java-evolution/), [11-kotlin-paradigm](../11-kotlin-paradigm/)

---

## 11. 정리 — 시니어가 본 OOP의 본질 (한 줄씩)

1. OOP는 **기술이 아니라 사회 시스템**. 수많은 개발자가 같은 코드를 안 부수고 협업하게 만드는 사회적 계약 코드.
2. 4대 특성 중 **캡슐화·다형성**만 진짜 핵심. 상속은 위험, 추상화는 양날의 검.
3. 테스트성은 신화 반, 진실 반. mock hell을 피하려면 함수형의 불변성을 받아들여야 함.
4. **OCP가 SOLID에서 가장 중요.** 단 YAGNI와 균형 — "어디에 추상화를 박을지 안목"이 시니어의 일.
5. 함수형과의 차이는 **상태 처리 방식**. OOP는 변이, FP는 불변+새 객체.
6. 동시성 시대에 OOP가 무너지는 이유: 가변 상태 공유 → 락 → 데드락 → 분석 불가.
7. 함수형이 살아남는 이유: 불변 + 순수 함수 + 부작용 격리 = 락 없는 동시성.
8. Java/Spring의 OOP 선택은 **엔터프라이즈 SI 시장**의 답. Go/Rust가 안 한 건 **다른 시장**을 노렸기 때문.
9. **Java 8 람다(2014)는 생존 전략이자 옳은 방향**. JDK 11이 아니라 JDK 8이에요.
10. 살아남는 언어 = **하이브리드 언어**. Java/Kotlin/Scala/C#/Swift/Rust.

> **결론**: "OOP를 마스터한다"는 건 4대 특성을 다 외우는 게 아니라, **어디서 쓰고 어디서 뺄지 판단하는 안목을 기르는 것.** 이게 코드베이스 수명을 10년 vs 3년으로 가르는 차이.

---

## 다음으로

- 각 챕터 깊이 학습: [README.md](./README.md) 의 파일 목록 참조
- 트레이드오프 마스터 테이블: [22-tradeoff-master-table](../22-tradeoff-master-table/)
- 운영 시나리오: [20-ops-scenarios](../20-ops-scenarios/)
- 모의 면접: [30-mock-interviews](../30-mock-interviews/)
