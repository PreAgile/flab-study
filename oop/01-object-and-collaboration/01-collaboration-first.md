# 01-01. Collaboration First — 객체보다 협력이 먼저

> 클래스 다이어그램을 먼저 그리는 OOP 설계는 거꾸로다.
> **CRC 카드 + 시퀀스 다이어그램으로 협력을 먼저 그리고, 그 협력에 필요한 객체를 도출**하는 것이 올바른 순서.

## 📍 학습 목표

1. **자율 객체**의 정확한 의미 — 데이터 + 행위 + 책임.
2. **메시지 기반 설계** — 메서드 호출 ≠ 메시지.
3. **CRC 카드** — 객체 도출 도구.
4. **시퀀스 다이어그램** — 협력 시각화.
5. 운영 관점: 협력 잘못 설계된 시스템의 함정.

## 🧠 자율 객체

```java
// 자율 객체 (좋음)
class Order {
    private List<OrderLine> lines;
    private Money discount;
    
    public Money totalPrice() {     // ← 자기 계산을 자기가 함
        return lines.stream()
                 .map(OrderLine::price)
                 .reduce(Money.ZERO, Money::add)
                 .subtract(discount);
    }
}

// vs.

// 비자율 (anemic)
class Order { /* getter/setter만 */ }
class OrderService {
    Money calculateTotal(Order order) {  // ← 외부가 계산
        // ...
    }
}
```

**자율의 3가지 조건**:
1. 자기 데이터를 자기가 보유 (캡슐화).
2. 자기 데이터에 대한 연산을 자기가 책임.
3. 외부는 메시지(메서드 호출)로만 접근.

## 📡 메시지

Alan Kay의 OOP 정의: "**객체 사이의 메시지 전달**".

```java
order.applyDiscount(coupon)  // 메시지
//    ↑          ↑
//    method     data
```

**메시지 = method + parameter**.

좋은 메시지 = "What" 표현, "How"는 객체에게.

```java
// Bad — How를 caller가 결정
if (order.getStatus() == PAID && order.getDelivery() == COMPLETED) {
    order.setStatus(SETTLED);
}

// Good — What을 caller가 요청
order.settle();   // Order가 How를 결정
```

## 🃏 CRC 카드 (Class-Responsibility-Collaborator)

객체 도출용 짧은 카드:

```
┌─────────────────────────────┐
│ Class: Order                 │
├─────────────────────────────┤
│ Responsibility:               │
│ • 총액 계산                    │
│ • 할인 적용                    │
│ • 결제 처리                    │
├─────────────────────────────┤
│ Collaborators:                │
│ • OrderLine                  │
│ • Coupon                     │
│ • PaymentGateway             │
└─────────────────────────────┘
```

설계 순서:
1. 도메인 분석 → 명사 추출 → 후보 클래스.
2. 각 후보의 **책임** 작성.
3. 책임 수행에 필요한 **협력자** 식별.
4. 시퀀스 다이어그램으로 협력 흐름 그림.
5. **그제야** 클래스 코드 작성.

## 📊 시퀀스 다이어그램

```
Customer    Order     OrderLine    Coupon    PaymentGateway
   │         │           │          │             │
   │ checkout│           │          │             │
   ├────────►│           │          │             │
   │         │ price()   │          │             │
   │         ├──────────►│          │             │
   │         │           │          │             │
   │         │ apply()   │          │             │
   │         ├──────────────────────►│             │
   │         │           │          │             │
   │         │ charge()  │          │             │
   │         ├──────────────────────────────────►│
   │         │           │          │             │
```

→ 시퀀스를 그리는 동안 "이 책임은 누구에게?" 결정.

## 🛠️ 잘못된 협력 설계의 함정

### 1. God Object

```java
class OrderManager {
    void process(Order o) {
        // 1000줄 — 모든 책임을 한 클래스에
    }
}
```

조치: 책임을 여러 객체로 분할.

### 2. 무자율 객체 (Anemic)

```java
class Order {
    // getter/setter만
}
class OrderService {
    void process(Order o) {
        if (o.getTotal() > 0 && o.getStatus() == ...) {
            o.setStatus(...);
        }
        // 모든 로직이 Service에
    }
}
```

조치: 로직을 Order로 이동 (자율화).

### 3. Train Wreck (Demeter 위반)

```java
String city = order.getCustomer().getAddress().getCity();
// → 객체 chain. caller가 내부 구조 다 알아야.
```

조치: Demeter 법칙 — "친구의 친구를 모른다".
```java
String city = order.deliveryCity();   // Order가 위임
```

## ⚔️ 꼬리질문

### Q. 클래스 다이어그램 vs 시퀀스 다이어그램 — 어느 게 먼저?

> 시퀀스 다이어그램.
> 시퀀스가 협력을 보여주고, 그 협력에서 객체와 메시지가 도출.
> 클래스 다이어그램은 결과로 얻어지는 것.

### Q. (Killer) Service 패턴이 자율 객체와 충돌하지 않나요?

> 부분적으로 그렇다.
> Spring의 `@Service`가 모든 로직 가져가면 도메인이 anemic.
> 답: Service는 **객체 간 조율 + 트랜잭션 경계**만. 도메인 로직은 도메인 객체에.
> → Hexagonal Architecture / DDD의 Application Service 정의.

## 🔗 다음

- → [02. Abstraction & Encapsulation](../02-abstraction-and-encapsulation/)
