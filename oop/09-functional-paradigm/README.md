# 09. Functional Paradigm — OOP의 보완 패러다임

> **이 챕터의 한 줄 목표**: "함수형 = Stream + 람다"가 아니다. 람다 칼큘러스 → 참조 투명성 → 불변성 → 순수함수 → 모나드까지의 사슬을 이해하고, **함수형이 OOP의 어떤 약점에 어떻게 답하는지** 한 줄로 답한다. "함수형 코어, 명령형 셸" 패턴을 코드로 보일 수 있다.

## 📖 이론적 골격

| 책 | 핵심 |
|---|---|
| 『Functional Programming in Scala』 (Chiusano, Bjarnason) | FP 정수 |
| 『Grokking Simplicity』 (Eric Normand) | OOP → FP 점진적 전환 |
| Joshua Bloch, Brian Goetz 글들 | Java의 FP 흡수 |
| SICP (1985) | LISP, 고차함수의 고전 |

## 학습 목표

1. **함수형의 4대 기둥** — 순수함수, 불변성, 고차함수, 합성.
2. **OOP의 약점과 FP의 답** 매핑 (가변 상태 → 불변, 사이드 이펙트 → 순수함수, 동시성 → 자연스러운 안전성).
3. **모나드 직관** — `Optional`, `Stream`, `CompletableFuture`가 왜 모나드인가.
4. **"함수형 코어, 명령형 셸"** 패턴 적용.
5. **OOP/FP 하이브리드 — Java/Kotlin이 어떻게 가능한지**.

## 파일 목록

| # | 파일 | 핵심 질문 |
|---|---|---|
| 01 | [01-why-functional.md](./01-why-functional.md) | 함수형이 왜 부상했나 — 멀티코어와 동시성 |
| 02 | [02-pure-function-and-immutability.md](./02-pure-function-and-immutability.md) | 순수함수 + 불변성의 강력함 |
| 03 | [03-higher-order-and-composition.md](./03-higher-order-and-composition.md) | 고차함수와 함수 합성 |
| 04 | [04-monad-intuition.md](./04-monad-intuition.md) | 모나드의 직관 — Optional, Stream, Future |
| 05 | [05-functional-core-imperative-shell.md](./05-functional-core-imperative-shell.md) | OOP와 FP의 통합 패턴 |

## 7단 학습 레이어

### 1단. 백지 그리기

```
[그림 1] OOP의 약점과 FP의 답
   OOP 약점                            FP의 답
   ──────────────                     ─────────────────
   가변 상태 공유 → race condition       불변 객체 → 동시성 자연 안전
   사이드 이펙트 추적 어려움             순수함수 → 입출력만 보면 검증 끝
   계층 깊은 메서드 호출 → 흐름 안 보임   함수 합성 → 파이프라인 명시
   객체 식별성 → 동일성 비교 헷갈림        값 동등성 (record/data class)

[그림 2] 함수형의 4대 기둥
        ┌─────────────────────────────────────────────────┐
        │                                                  │
        │   ① 순수함수 (Pure Function)                       │
        │      f(x) = f(x) 보장, 사이드 이펙트 없음            │
        │                                                  │
        │   ② 불변성 (Immutability)                          │
        │      한 번 생성된 값은 변경 불가                       │
        │                                                  │
        │   ③ 고차함수 (Higher-Order Function)                 │
        │      함수가 함수를 인자/반환값으로                     │
        │                                                  │
        │   ④ 합성 (Composition)                            │
        │      f ∘ g 로 새로운 동작 생성                       │
        │                                                  │
        └─────────────────────────────────────────────────┘

[그림 3] Functional Core, Imperative Shell
   ┌─────────────────────────────────────────────────────────┐
   │  Imperative Shell (외곽)                                 │
   │  ┌──────────────────────────────────────┐               │
   │  │ Functional Core (내부)                 │               │
   │  │  - 순수함수만                          │               │
   │  │  - 비즈니스 로직                        │               │
   │  │  - 100% 단위 테스트                     │               │
   │  └──────────────────────────────────────┘               │
   │   외부 통신 (DB, API, FileSystem)                          │
   │   I/O, 부작용, 비순수                                       │
   │   통합 테스트                                              │
   └─────────────────────────────────────────────────────────┘
```

### 2단. 직관

- **순수함수**: "수학 공식. f(2,3)은 언제나 5."
- **불변성**: "스냅샷. 어제의 객체가 내일도 같음."
- **고차함수**: "함수도 데이터다."
- **합성**: "레고 블록. 작은 함수를 조립."
- **모나드 (직관)**: "값을 컨테이너에 담아서, 컨테이너끼리 안전하게 연결."

### 3단. 구조 — 모나드 직관

```java
// Optional이 모나드인 이유 — 두 연산을 가짐
Optional<User> findUser(Long id) { ... }
Optional<Order> findLatestOrder(User user) { ... }

// Without monad (절차)
Optional<User> userOpt = findUser(1L);
Optional<Order> orderOpt = Optional.empty();
if (userOpt.isPresent()) {
    orderOpt = findLatestOrder(userOpt.get());
}

// With monad (flatMap = bind)
Optional<Order> orderOpt = findUser(1L)
    .flatMap(this::findLatestOrder);
// null 체크가 사라짐. 컨테이너가 흡수.

// Stream도 모나드
Stream.of(1, 2, 3)
    .flatMap(n -> Stream.of(n, n * 10))
    .forEach(System.out::println);

// CompletableFuture도 모나드
CompletableFuture.supplyAsync(() -> findUser(1L))
    .thenCompose(this::findOrderAsync);
```

**모나드 = 두 함수**:
1. `of(value)`: 값을 컨테이너에 넣기 (Optional.of, Stream.of, CompletableFuture.completedFuture)
2. `flatMap(f)`: 컨테이너 안의 값을 변환하되 결과가 컨테이너 → 평탄화

이 추상화가 **사이드 이펙트, null, 비동기, 컬렉션 변환** 모두를 같은 방식으로 처리.

### 4단. 내부 구현 — Java 람다의 `invokedynamic`

```java
// 소스
Function<Integer, Integer> doubler = x -> x * 2;

// Java 7 이전 (익명 클래스)
Function<Integer, Integer> doubler = new Function<>() {
    public Integer apply(Integer x) { return x * 2; }
};
// 매번 새 클래스 파일 + 객체 생성

// Java 8+ (invokedynamic + LambdaMetafactory)
// bytecode: invokedynamic LambdaMetafactory.metafactory(...)
// 런타임에 LambdaMetafactory가 람다 클래스를 동적 생성 + 캐시
// 익명 클래스보다 메모리 ↓, 첫 호출 비용은 ↑
```

→ JVM 챕터 [../jvm/](../jvm/) cross-reference.

### 5단. 역사

| 연도 | 사건 | 트리거 |
|---|---|---|
| 1936 | Alonzo Church Lambda Calculus | 계산 가능성의 수학 모델 |
| 1958 | LISP (John McCarthy) | 첫 FP 언어 |
| 1973 | ML (Robin Milner) | 정적 타입 FP |
| 1985 | Haskell | 순수 FP의 표준 |
| 1995 | OCaml | OOP + FP 결합 |
| 2003 | Scala (Martin Odersky) | JVM 위 OOP + FP |
| 2007 | Clojure | JVM 위 LISP |
| 2010 | F# | .NET 위 ML |
| 2014 | Java 8 | 람다, Stream, Optional |
| 2016 | Kotlin 1.0 | 함수가 일급 시민 |
| 2023 | Java 21 | Pattern matching, Virtual Thread |

### 6단. 트레이드오프 — OOP vs FP

| 축 | OOP 우위 | FP 우위 |
|---|---|---|
| **도메인 모델링** | ✓ (자율 객체로 자연) | ✗ (값 + 함수로 표현 어색) |
| **상태 변화 표현** | ✓ (캡슐화) | ~ (Monad State, Lens 필요) |
| **데이터 변환 파이프라인** | ✗ (boilerplate) | ✓ (map/filter/reduce) |
| **동시성** | ✗ (락 필요) | ✓ (불변 자연 안전) |
| **테스트** | ~ (Mock 필요) | ✓ (입출력 검증) |
| **재사용 단위** | 클래스/컴포넌트 | 함수 (더 작음, 합성 가능) |
| **러닝 커브** | 중 | 높음 (모나드 등) |

→ **결론**: 둘 다 쓴다. **도메인은 OOP, 데이터 변환/I/O는 FP**.

### 7단. 운영 진단 — FP 안티패턴

- **"람다 흉내" 안티패턴**:
  - `forEach` 안에 부작용 잔뜩 — 진짜 FP 아님
  - `peek()` 안에 비즈니스 로직 — Stream 오용
  - → `map`/`filter`/`reduce`로 명시적 변환
- **"불변인 척" 안티패턴**:
  - `final List<User>` 했지만 List 내부 객체는 가변
  - 깊은 불변성 보장 안 됨
  - → 모든 필드 final + 깊은 복사 또는 record + 불변 컬렉션
- **모나드 남용**:
  - `Optional<Optional<User>>` → flatMap 안 씀
  - 모든 반환값 `Optional` 강제 → 가독성 ↓
  - → Optional은 "값이 없을 수 있다"가 정말 의미 있을 때만

## 꼬리질문

### Junior
1. **Q**: 함수형 프로그래밍이 뭔가요?
   → 순수함수와 불변 데이터를 중심으로 하는 패러다임. 사이드 이펙트 최소화.

### Senior
2. **Q**: `Optional`은 왜 모나드인가요?
   → 두 연산을 가짐: `of(x)`로 값 포장, `flatMap(f)`로 값 변환하면서 컨테이너 평탄화. 이 두 연산이 모나드 법칙(left identity, right identity, associativity)을 만족.
3. **꼬리**: Java의 `Optional`이 진짜 모나드라면 왜 `for-comprehension` 같은 문법 설탕이 없나요?
   → Java 언어 차원에서 모나드를 first-class로 보지 않음. Scala/Haskell은 `for { x <- xs; y <- ys } yield ...` 또는 do-notation 제공. Java는 명시적 `flatMap` 체이닝이 필요. → Java의 FP는 "함수형 자료구조 + 함수형 메서드"이지 "함수형 언어"가 아님.
4. **꼬리의 꼬리**: 그렇다면 Java로 진짜 함수형 코드를 쓰려면 어떤 라이브러리가 필요한가요?
   → Vavr (Functional Java) — `Either`, `Try`, `Validation`, `List`(persistent), `Tuple` 등 Scala 스타일. 또는 Arrow-kt (Kotlin) — `Either`, `IO`, monad transformer 등.

### Principal
5. **Q**: "Functional Core, Imperative Shell" 패턴을 도입했을 때 도메인 모델은 어떻게 변하나요?
   → 도메인 객체가 **불변 + 순수함수** 위주가 됨. `Order` 안의 `cancel()`이 `Order`를 변경하지 않고 새 `Order`를 반환 (또는 `Either<Error, Order>`). 사이드 이펙트(DB 저장, 이벤트 발행)는 외곽 셸이 책임. → 테스트가 매우 쉬워지지만 ORM과의 통합이 복잡해짐 (JPA Entity는 mutable 가정).
6. **꼬리**: JPA와 불변 도메인은 어떻게 공존하나요?
   → 두 가지 패턴:
   1. **Hexagonal**: Domain Model (불변 POJO) + Persistence Model (JPA Entity) 분리. Repository에서 mapping.
   2. **JPA Entity를 mutable로 두되 setter 노출 X**: 도메인 메서드만 노출, 내부에서 필드 수정. "참조 투명성"은 깨지지만 캡슐화는 유지.
7. **꼬리의 꼬리**: 그럼 Spring의 `@Transactional` 같은 사이드 이펙트는 함수형 관점에서 어떻게 보나요?
   → 가장 큰 부조화 지점. 함수형은 "효과(Effect)를 타입으로 표현" (IO, Reader, State monad). Spring은 어노테이션으로 외부에서 효과 주입 — **마법** + **암묵적**. → Kotlin/Scala 진영에서는 `Arrow` 같은 라이브러리로 IO monad 도입 시도하지만, 산업 보편화 X. JVM 진영의 미해결 과제.

## 다음 챕터로

- [10-java-evolution](../10-java-evolution/) — Java 7→21 진화
