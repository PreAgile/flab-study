# 04-01. Tell Don't Ask + Demeter — 메시지의 진짜 정의

> "객체에게 묻지 말고 시켜라" — OOP의 가장 강력한 원칙.
> getter chain은 즉시 안티패턴 신호.

## 📍 학습 목표

1. **Tell Don't Ask** — 묻지 말고 시켜라.
2. **Demeter 법칙** — 친구의 친구를 모른다.
3. **Train Wreck** — 객체 chain의 함정.
4. **위임 vs 직접 접근**.

## 🎯 Tell Don't Ask

```java
// Bad — Ask (get & decide)
if (account.getBalance() > amount) {
    account.setBalance(account.getBalance() - amount);
}

// Good — Tell (위임)
account.withdraw(amount);   // Account가 자기 책임으로 처리
```

### 차이의 의미

```
[Ask 패턴]
caller가 객체 내부 상태를 캐묻고 결정. 
객체는 "단순 데이터 저장소".
→ 절차지향. 캡슐화 위반.

[Tell 패턴]
caller가 객체에게 행동을 명령.
객체가 자기 상태로 결정.
→ OOP의 본질.
```

## 🚂 Train Wreck (객체 chain)

```java
// 안티패턴
String city = order.getCustomer().getAddress().getCity();

// → caller가 Order, Customer, Address 내부 구조 모두 알아야.
// → Customer가 Address를 다른 방식으로 보관하면 모든 caller 수정.
```

### Demeter 법칙 — 친구의 친구를 모른다

객체 M의 메서드 안에서 호출 가능한 것:
1. **자기 자신의** 메서드.
2. **파라미터**의 메서드.
3. **자기가 생성한** 객체의 메서드.
4. **자기 필드**의 메서드.

→ "다른 메서드의 결과값에 또 점(.)을 찍지 말라."

### 해결: 위임

```java
class Order {
    private Customer customer;
    
    public String deliveryCity() {     // ← Order가 위임
        return customer.deliveryCity();
    }
}

class Customer {
    private Address address;
    
    public String deliveryCity() {
        return address.city();
    }
}

// 사용
String city = order.deliveryCity();   // chain 없음
```

→ 내부 구조 변경 자유.

## 🛠️ 실무 적용

### getter chain → 위임

```java
// Bad
order.getCustomer().getAddress().getCity()
order.getCustomer().getName()
order.getOrderLines().stream().mapToInt(...)

// Good
order.deliveryCity()
order.customerName()
order.totalItems()
```

### Collection chain의 예외

Stream API는 chain 패턴이 자연스러움:
```java
order.lines().stream()
    .filter(l -> l.isShippable())
    .map(OrderLine::quantity)
    .sum()
```

→ Stream chain은 변환 pipeline. Demeter 위반 아님 (같은 Stream에 대한 호출).

### DTO/Record는 예외

```java
record AddressDto(String city, String street, String zip) { }

dto.city();   // OK — DTO는 데이터 컨테이너
```

→ DTO/Value Object/Record는 Tell Don't Ask 적용 안 함.

## ⚔️ 꼬리질문

### Q. getter는 항상 나쁜가요?

> 아니. 컨텍스트에 따라:
> - **Read-only getter** (불변 값 노출): OK.
> - **결정에 사용** (`if (obj.getX() > 0) {...}`): 위임으로 바꿀 것 (Tell Don't Ask).
> - **DTO/Record getter**: OK.

### Q. (Killer) Lombok @Data의 위험은?

> `@Data` = getter + setter + equals + hashCode + toString 자동 생성.
> 위험:
> 1. 모든 필드 getter/setter — anemic 강제.
> 2. setter — invariant 깨짐.
> 3. equals/hashCode 자동 — Entity의 정체성 위반.
> 4. toString — 순환 ref 시 stack overflow.
> 
> 권장:
> - Entity: 직접 작성 (행위 메서드 위주).
> - DTO: `@Value` (immutable) 또는 record.
> - 데이터 컨테이너만 `@Data`.

## 🔗 다음

- → [05. Object Decomposition](../05-object-decomposition/)
