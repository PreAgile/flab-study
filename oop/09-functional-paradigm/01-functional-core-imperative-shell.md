# 09-01. Functional Core, Imperative Shell

> FP가 OOP의 어떤 약점에 답하는가?
> **상태 변경 격리 + 추론 가능성**.
> 그러나 100% FP는 어색 — "함수형 코어, 명령형 셸" 패턴이 답.

## 📍 학습 목표

1. **순수함수 + 불변성** — FP의 기반.
2. **참조 투명성** — 같은 입력 = 같은 출력.
3. **모나드** — 사이드 이펙트 추상화.
4. **Functional Core, Imperative Shell** 패턴.
5. **Java/Kotlin이 FP 흡수한 방식**.

## 🎯 FP의 기반

### 순수함수

```java
// 순수
int add(int a, int b) { return a + b; }   // 입력만으로 결정

// 불순
int total = 0;
int addToTotal(int n) { total += n; return total; }   // 외부 상태 의존
```

### 참조 투명성

```java
// 참조 투명: f(x) 호출을 결과값으로 치환 가능
int x = add(2, 3);
int y = 5;
// 위 두 라인이 같음

// 비참조 투명
int x = addToTotal(2);   // 결과가 호출 시점에 따라 다름
```

### 불변성

```java
// 가변 — 위험
List<Integer> list = new ArrayList<>();
list.add(1); list.add(2);

// 불변 — 안전
List<Integer> list = List.of(1, 2);   // immutable
```

## 🎁 Monad — 사이드 이펙트 추상화

```java
// Optional Monad — null 안전
Optional<User> user = userRepo.findById(id);
String name = user.map(User::getName)
                   .orElse("Unknown");

// Stream Monad — collection 변환
List<String> names = users.stream()
    .filter(u -> u.isActive())
    .map(User::getName)
    .toList();

// CompletableFuture Monad — async
CompletableFuture<Data> data = fetchAsync()
    .thenApply(this::transform)
    .thenCompose(this::saveAsync);
```

특징:
- `map`, `flatMap` 메서드 + 단위 함수.
- 사이드 이펙트(null, async, fail)를 chain 가능하게.

## 🏛️ Functional Core, Imperative Shell

```
[Imperative Shell]
   - 외부 세계 입출력 (HTTP, DB, file)
   - 상태 변경
   - 에러 처리
       │
       ▼
[Functional Core]
   - 순수 비즈니스 로직
   - 입력 → 출력 변환
   - 테스트 매우 쉬움
       ▲
       │
[Imperative Shell]
   - 결과 반환 (HTTP response, DB save)
```

### 예시: 주문 처리

```java
// Imperative Shell
@RestController
class OrderController {
    @PostMapping("/orders")
    public OrderDto create(@RequestBody OrderRequest req) {
        Order order = repo.findById(req.orderId());   // I/O
        
        // Functional Core
        Order updated = OrderRules.apply(order, req.action());   // 순수
        
        repo.save(updated);   // I/O
        return OrderDto.from(updated);
    }
}

class OrderRules {
    // 순수 — 입력 두 개 → 출력 하나. 사이드 이펙트 없음.
    public static Order apply(Order order, Action action) {
        return switch (action) {
            case Pay p -> order.withStatus(PAID);
            case Cancel c -> order.withStatus(CANCELED);
        };
    }
}
```

장점:
- Core 테스트 쉬움 (input/output 비교).
- Shell만 mock 필요.
- 동시성 안전 (core는 불변).

## 🛠️ Java FP 흡수

| 기능 | 도입 | 의미 |
|---|---|---|
| Lambda | Java 8 (2014) | 함수 전달 |
| Stream | Java 8 | Collection 변환 chain |
| Optional | Java 8 | null 안전 |
| CompletableFuture | Java 8 | async monad |
| Record | Java 16 | Immutable data |
| Sealed | Java 17 | Sum type (FP의 ADT) |
| Pattern matching | Java 21 | 함수형 매칭 |

## ⚔️ 꼬리질문

### Q. 모든 코드를 FP로 작성하면 안 되나요?

> 100% FP는 어색.
> - I/O (DB, file, network)는 사이드 이펙트 본질.
> - UI 상태 관리.
> - 일부 알고리즘 (mutable 자료구조 효율적).
> 
> 답: Functional Core, Imperative Shell. 핵심 로직만 FP.

### Q. (Killer) Java의 Stream API가 진짜 FP인가요?

> 부분적으로.
> - Pure functional 시각: 사이드 이펙트 없는 transformation chain.
> - 그러나 Stream 자체는 mutable internal state.
> - `forEach` 안에서 사이드 이펙트 흔하게 사용 → 안티패턴.
> 
> 진짜 FP는 Haskell, Clojure 수준의 immutability + 합성.
> Java Stream은 "FP 영감" 정도.

## 🔗 다음

- → [10. Java Evolution](../10-java-evolution/)
- → [11. Kotlin Paradigm](../11-kotlin-paradigm/)
