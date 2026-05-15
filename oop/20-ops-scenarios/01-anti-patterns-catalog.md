# 20-01. OOP 안티패턴 카탈로그

> 레거시 코드를 보면 5초 안에 안티패턴 명명 + 3단계 리팩토링 계획.

## 📚 8대 안티패턴

### 1. God Object (만능 객체)

**증상**: 한 클래스가 수천 줄, 수십 책임.

```java
class OrderManager {
    void create();
    void update();
    void delete();
    void calculateDiscount();
    void sendEmail();
    void saveToDb();
    void exportPdf();
    // ... 50 메서드
}
```

**리팩토링**:
1. 책임 식별 (SRP).
2. 책임별 클래스 분리.
3. OrderManager는 조율만.

### 2. Anemic Domain Model (빈혈 도메인)

**증상**: Entity는 getter/setter, Service에 모든 로직.

```java
class Order {
    private Long id;
    private String status;
    // getter/setter
}

class OrderService {
    void process(Order o) {
        if (o.getStatus().equals("PENDING")) o.setStatus("PAID");
        // 비즈니스 로직 전부 Service
    }
}
```

**리팩토링**:
1. 비즈니스 로직 → Entity로 이동.
2. `Order.pay()`, `Order.cancel()` 같은 행위 메서드.
3. Service는 조율 + 트랜잭션 경계만.

### 3. Train Wreck (객체 chain)

**증상**: `a.getB().getC().getD()`.

**리팩토링**: Demeter 위임. `a.relevantInfo()`.

### 4. Long Method (긴 메서드)

**증상**: 한 메서드가 100+ 줄.

**리팩토링**: Extract Method. 의미 단위로 분할.

### 5. Switch Statement (분기 폭주)

**증상**: 같은 분기 패턴이 여러 곳.

```java
void process(Animal a) {
    if (a.type == DOG) ...
    else if (a.type == CAT) ...
}
void feed(Animal a) {
    if (a.type == DOG) ...
    else if (a.type == CAT) ...
}
```

**리팩토링**: 다형성. `animal.process()`, `animal.feed()`.

### 6. Primitive Obsession (원시 타입 집착)

**증상**: 모든 것을 String, int, BigDecimal로.

```java
class User {
    private String email;       // 검증 어디?
    private BigDecimal balance; // 음수 가능?
}
```

**리팩토링**: Value Object.

```java
record Email(String value) {
    public Email {
        if (!value.contains("@")) throw new IllegalArgumentException();
    }
}

record Money(BigDecimal amount, Currency currency) {
    public Money add(Money other) { ... }
}
```

### 7. Feature Envy (다른 객체 부러워함)

**증상**: 메서드가 자기 객체보다 다른 객체의 데이터를 더 많이 사용.

```java
class OrderService {
    void apply(Discount d, Order o) {
        if (o.getTotal() > 1000 && o.getStatus() == "PAID" && o.getCustomer().isVIP()) {
            // 모든 정보가 Order에서 옴
        }
    }
}
```

**리팩토링**: 로직을 Order로 이동.

### 8. Shotgun Surgery (산탄총 수술)

**증상**: 한 변경이 여러 클래스에 영향.

```java
// "VAT를 10% → 12%로 변경"
// → ProductService 수정
// → OrderService 수정
// → InvoiceService 수정
// → ... 10개 클래스
```

**리팩토링**: 변경 책임 응집. TaxPolicy 클래스 도입.

## 🛠️ 리팩토링 3단계 패턴

```
1. 안티패턴 식별 (이름 명명)
2. 가장 안전한 변환 1개 적용 (Extract Method 등)
3. 테스트 통과 확인 + 다음 변환
```

→ Martin Fowler의 "Refactoring" 책.

## ⚔️ 꼬리질문

### Q. 안티패턴이 의도된 경우는?

> 가능:
> - DTO/Record는 Anemic이 OK (데이터 컨테이너).
> - 작은 utility class는 God Object여도 OK.
> - Switch statement도 Sealed + Pattern matching 시 정당.
> 
> 컨텍스트 따라 판단.

### Q. (Killer) 레거시 코드의 리팩토링 우선순위?

> 1. **테스트 먼저** — 안전망 구축.
> 2. **가장 자주 변경되는 영역**부터 — ROI 큼.
> 3. **버그 hotspot**부터 — 안티패턴이 버그 원인일 가능성.
> 4. **God Object > Anemic > 기타** — 영향 큰 순.
> 5. **한 번에 작게** — 한 리팩토링당 commit 1개.

## 🔗 다음

- → [21. Hands-on Workbook](../21-hands-on-workbook/)
