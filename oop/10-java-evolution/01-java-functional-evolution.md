# 10-01. Java의 함수형 흡수 — 왜 이 순서?

> Lambda → Optional → Stream → Record → Sealed → Pattern Matching → Virtual Thread.
> 각 기능의 도입 순서에는 이유가 있다.

## 📍 학습 목표

1. Java 8 ~ 21의 핵심 변화.
2. 각 기능이 어떤 산업적 압력의 답.
3. 각 기능의 바이트코드 수준 구현.
4. 함수형 + OOP의 통합 방식.

## 🌊 진화 순서와 이유

### Java 8 (2014) — Lambda + Stream + Optional

**산업적 압력**: Scala/Clojure/Kotlin이 함수형 표현력으로 인기. Java의 boilerplate 비판.

**핵심 도입**:
- **Lambda** — `(x) -> x * 2`.
- **Stream API** — Collection 변환 chain.
- **Optional** — null 안전.
- **CompletableFuture** — async monad.

**바이트코드**:
- Lambda는 `invokedynamic` + `LambdaMetafactory` (Chapter 03-05 JVM).
- 첫 호출 시 hidden class 생성.

### Java 9-10 (2017-2018) — Module + var

- **Module System (JEP 261)** — 큰 시스템의 모듈화.
- **`var`** — 타입 추론 (개발 생산성).

### Java 11 (2018, LTS) — HTTP Client + 향상된 var

- **HTTP Client (표준)** — 옛 HttpURLConnection 대체.
- 모듈/var 안정화.

### Java 14-16 — Switch Expression + Record + Sealed (preview)

```java
// Switch expression
String day = switch (dayOfWeek) {
    case MON, TUE, WED, THU, FRI -> "weekday";
    case SAT, SUN -> "weekend";
};

// Record
record Point(int x, int y) { }
// → 자동 생성: 생성자, getter, equals, hashCode, toString

// Sealed
sealed interface Shape permits Circle, Square, Triangle { }
```

**Record**: FP의 ADT (Algebraic Data Type) 도입.
**Sealed**: Sum type — `Shape` 구현체가 정확히 3개.

### Java 17 (2021, LTS) — Record + Sealed stable

- Record, Sealed 정식.
- Pattern matching for instanceof.

### Java 21 (2023, LTS) — Virtual Thread + Pattern Matching for Switch

```java
// Virtual Thread
Thread.startVirtualThread(() -> { ... });

// Pattern matching for switch
String description = switch (shape) {
    case Circle c -> "Circle radius " + c.radius();
    case Square s -> "Square side " + s.side();
    case Triangle t -> "Triangle base " + t.base();
};
```

→ Sealed + Pattern matching = OOP + FP의 통합.

## 📊 기능별 산업적 동기

| 기능 | 동기 | 대체된 패턴 |
|---|---|---|
| Lambda | 함수형 표현력 | 익명 클래스 |
| Stream | Collection 변환 boilerplate ↓ | for loop |
| Optional | null 안전 | null 체크 |
| Record | DTO boilerplate ↓ | getter/setter 자동 |
| Sealed | ADT 표현 | 큰 if-else 분기 |
| Pattern matching | 함수형 match | instanceof + cast |
| Virtual Thread | 동시성 폭발 | Reactor/RxJava callback |

## 🛠️ 운영 함의

### Lambda + Metaspace

각 lambda 호출 사이트가 hidden class 생성 — Metaspace 사용 ↑.
운영: hidden class 수 모니터링.

### Record의 운영 이점

```java
record OrderDto(Long id, String status, BigDecimal total) { }
```

- Immutable.
- Hashcode/equals 자동 — Map/Set key 안전.
- JSON serialization (Jackson 3+) 친화.
- DTO boilerplate 0.

### Sealed의 JIT 친화

```java
sealed interface PaymentMethod permits Card, Paypal, Stripe { }
```

- CHA 강력 — JIT이 inline 더 적극적.
- Pattern matching exhaustive check.
- Deopt 위험 ↓.

### Virtual Thread

[JVM Chapter 05-04](../../jvm/05-threading/04-virtual-threads-and-loom.md) 참조.

## ⚔️ 꼬리질문

### Q. Java가 함수형을 흡수한 순서가 왜 이건가요?

> 1. Lambda 먼저 — 다른 모든 함수형 기능의 기반.
> 2. Stream/Optional — Lambda 활용.
> 3. Record — DTO 표현력.
> 4. Sealed — Record와 같이 ADT 완성.
> 5. Pattern matching — Sealed 활용.
> 6. Virtual Thread — async 패러다임 답.
> 
> 점진적: 한 기능이 다음 기능의 전제.

### Q. (Killer) `sealed interface + pattern matching`이 OOP를 대체하나요?

> 부분적 대체.
> - Subtype polymorphism은 그대로.
> - 단, "분기 결정"이 외부 코드(switch)에서 — 약간 OCP 위반.
> - 정답: 두 패러다임 혼용. 
>   - 동작 다형성 (sound, move) → Subtype.
>   - 데이터 종류별 분기 → Sealed + Pattern.

## 🔗 다음

- → [11. Kotlin Paradigm](../11-kotlin-paradigm/)
