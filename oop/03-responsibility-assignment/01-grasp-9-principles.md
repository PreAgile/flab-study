# 03-01. GRASP 9 원칙 — 책임 할당의 사고법

> SOLID는 결과적 규칙, **GRASP는 도착하는 사고법**.
> "이 책임은 누구에게?"를 결정할 때 GRASP 9원칙으로 30초 안에 답.

## 📍 9 GRASP 원칙

### ① Information Expert
> 책임을 수행할 정보를 가진 객체에게.

```java
// Bad: OrderService가 총액 계산
class OrderService {
    Money calculateTotal(Order order) { ... }
}

// Good: Order가 자기 정보로 계산
class Order {
    Money total() { ... }   // 자기 lines 정보 보유
}
```

### ② Creator
> A가 B의 인스턴스를 생성할 책임을 가지는 조건:
> - A가 B를 포함 (composition).
> - A가 B를 기록.
> - A가 B를 밀접하게 사용.
> - A가 B 생성에 필요한 데이터를 가짐.

```java
class Order {
    // Order가 OrderLine을 포함 → Order가 OrderLine 생성
    OrderLine addLine(Product p, int qty) {
        OrderLine line = new OrderLine(p, qty);
        lines.add(line);
        return line;
    }
}
```

### ③ Low Coupling
> 객체 간 결합도 낮게.

```java
// High coupling
class Order {
    private PaymentGatewayImpl gateway;   // 구체 클래스에 의존
}

// Low coupling
class Order {
    private PaymentGateway gateway;        // 인터페이스에 의존
}
```

### ④ High Cohesion
> 한 객체의 책임이 응집되어 있어야.

```java
// Low cohesion
class Order {
    void processPayment();
    void sendEmail();         // ← Order 책임 아님
    void logToDatabase();      // ← Order 책임 아님
}

// High cohesion
class Order {
    void process();   // 주문 본질
}
class EmailService { void sendOrderConfirm(Order o); }
class OrderRepository { void save(Order o); }
```

### ⑤ Controller
> UI/외부 요청을 받는 책임을 한 객체에 위임.

```java
@RestController
class OrderController {   // ← Controller 역할
    @PostMapping("/orders")
    public OrderDto create(@RequestBody OrderRequest req) {
        return orderService.create(req);
    }
}
```

### ⑥ Polymorphism
> 타입별 분기 대신 다형성.

```java
// Bad
if (animal.type == DOG) bark();
else if (animal.type == CAT) meow();

// Good
animal.makeSound();   // 다형성
```

### ⑦ Pure Fabrication
> 도메인에 없는 인공 객체로 high cohesion + low coupling.

```java
// Order에 DB 접근 로직 추가 → Order의 cohesion ↓
// 해결: OrderRepository (도메인에 없지만 인공 객체)
class OrderRepository {
    void save(Order o);
    Order findById(Long id);
}
```

### ⑧ Indirection
> 직접 결합 대신 중간 객체 통해 결합도 ↓.

```java
// Adapter pattern
class LegacyPaymentSystem { /* 옛 API */ }

class PaymentAdapter implements PaymentGateway {
    private LegacyPaymentSystem legacy;
    void pay(Money amount) {
        legacy.executePayment(amount.cents());   // 변환
    }
}
```

### ⑨ Protected Variations
> 변경 가능 점을 인터페이스로 보호.

```java
// 결제 방식이 변경 가능 → 인터페이스로 추상화
interface PaymentMethod { void pay(Money amount); }
// 새 결제 방식 추가 = 새 구현체. 기존 코드 영향 0.
```

## 🛠️ GRASP 사고법 사용 예

**도메인**: 영화 예매 시스템.

**문제**: "할인을 누가 계산해야?"

GRASP 적용:
1. **Information Expert**: 할인 정보(쿠폰, 할인 정책)는 누가 가짐?
   - Movie? Showtime? Coupon?
2. **High Cohesion**: 할인 계산 책임이 어디에 응집되면 자연스러운가?
   - Discount 객체로 분리?
3. **Polymorphism**: 할인 종류가 다양 → 다형성?
   - PercentDiscount, AmountDiscount, FreeShipping ...

결론: `Discount` 인터페이스 + 구현체들. `Movie.applyDiscount(Discount d)`.

## ⚔️ 꼬리질문

### Q. GRASP vs SOLID의 차이는?

> SOLID: 결과적 규칙 (5개).
> GRASP: 도착하는 사고법 (9개).
> 
> 좋은 OOP 설계 = GRASP 사고법 → 결과적으로 SOLID 만족.

### Q. (Killer) 새 도메인 받았을 때 GRASP 적용 순서?

> 1. **명사 추출** → 후보 객체.
> 2. **Information Expert**로 책임 할당.
> 3. **Creator**로 생성 책임.
> 4. **High Cohesion** 점검 — 한 객체에 너무 많이?
> 5. **Low Coupling** 점검 — 객체 간 의존성?
> 6. **Polymorphism** 적용 — 분기 대신.
> 7. **Pure Fabrication** 도입 — Repository, Service 등.
> 8. **Indirection** — 외부 시스템 Adapter.
> 9. **Protected Variations** — 변경 가능 점 인터페이스화.

## 🔗 다음

- → [04. Message & Interface](../04-message-and-interface/)
