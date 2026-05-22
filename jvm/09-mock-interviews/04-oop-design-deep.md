# 09-04. OOP & Design Principles — 시니어 깊이 답변 8문항

> **이 문서의 한 줄 목표**: SOLID·DDD·Clean Architecture·MSA를 "원칙 외우는" 수준이 아니라, **운영해본 사람이 왜 이걸 골랐고 어디서 깨졌나** 의 결을 따라 줄줄 답할 수 있게 만든다.

---

## 0. 8문항 한눈에

```
[Excalidraw: OOP-면접-8문항-지도]

       (1) 가장 중요한 원칙           ── "OCP + DIP, 그리고 둘은 사실 한 몸"
            │
       (2) 원칙끼리 충돌              ── "SRP 폭증 vs OCP 추상화 세금 vs YAGNI"
            │
       (3) 위반이 만든 장애           ── "God Object · Fragile Base · 강결합 cascade"
            │
       (4) DDD / Clean / Hexagonal   ── "Aggregate=SRP, Repo=DIP, UseCase=OCP"
            │
       (5) 테스트                    ── "DIP=mocking, SRP=단위분리, ISP=fake 단순화"
            │
       (6) 리팩토링 Before/After     ── "if-else 폭탄 → Strategy, new 직접 → DI"
            │
       (7) OOP + FP 혼용             ── "도메인은 OOP, 변환은 FP, 부작용은 격리"
            │
       (8) MSA로 확장                ── "Bounded Context=서비스 경계, Saga, Choreo vs Orch"
```

각 문항은 **한 줄 정의 → 코드 → 실무 적용 → 트레이드오프 → 한 줄 정리** 구조로 답합니다.

---

## 1. 가장 중요한 원칙은 무엇이고, 어떻게 적용했는가

### 1-1. 한 줄 정의

**OCP(개방-폐쇄)와 DIP(의존성 역전)는 사실 한 몸이고, 둘이 합쳐져야 "확장 가능한 시스템"이 됩니다.** SRP가 가장 기본이지만, 가장 임팩트가 큰 건 OCP+DIP입니다.

### 1-2. 왜 OCP+DIP인가

- **SRP**는 "잘 쪼개라" — 좋은 습관이지만 잘 쪼개도 변경에 닫혀있지 않으면 모든 곳을 고쳐야 합니다.
- **OCP**는 "확장에는 열고 수정에는 닫아라" — 진짜 가치는 여기 있습니다. 운영 중 새 결제수단·새 알림채널·새 정산 룰이 추가될 때 기존 코드를 안 건드리고 확장만 추가하느냐가 운영 비용을 결정합니다.
- **DIP**는 OCP를 가능케 하는 메커니즘입니다. 추상(인터페이스)에 의존해야 확장점이 생깁니다.

### 1-3. Before — OCP 위반 코드

```java
public class PaymentService {
    public void pay(Order order, String method) {
        if (method.equals("CARD")) {
            // 카드 결제 로직 50줄
            tossPayClient.charge(order);
        } else if (method.equals("KAKAO")) {
            // 카카오 결제 로직 50줄
            kakaoPayClient.charge(order);
        } else if (method.equals("NAVER")) {
            // 네이버 결제 로직 50줄
            naverPayClient.charge(order);
        }
        // 새 결제수단 추가 시 → 이 메서드 또 까서 if 추가
        // → 기존 카드/카카오 회귀 테스트 다시 돌려야 함
    }
}
```

**문제**: 새 결제수단 = 기존 코드 수정 = 전체 회귀 리스크. 운영 중 PG사 추가가 PG팀 영역인데 우리 코드 전체를 흔듭니다.

### 1-4. After — OCP+DIP 적용

```java
public interface PaymentMethod {
    PaymentResult charge(Order order);
    boolean supports(String code);
}

@Component
public class TossCardPayment implements PaymentMethod { /* ... */ }
@Component
public class KakaoPayPayment implements PaymentMethod { /* ... */ }
@Component
public class NaverPayPayment implements PaymentMethod { /* ... */ }

@Service
public class PaymentService {
    private final List<PaymentMethod> methods;  // Spring이 모든 구현체 주입

    public PaymentResult pay(Order order, String code) {
        return methods.stream()
            .filter(m -> m.supports(code))
            .findFirst()
            .orElseThrow(() -> new UnsupportedPaymentException(code))
            .charge(order);
    }
}
```

**효과**: 새 결제수단은 새 클래스 하나 추가 + `@Component`만 붙이면 끝. `PaymentService`는 손 안 댑니다. 회귀 영향 0.

### 1-5. 내가 실제 적용한 사례

이커머스 정산 시스템에서 **수수료 정책 30종**을 if-else로 들고 있던 코드가 있었습니다. 매월 정산 룰이 바뀌고, 신규 셀러 유형이 추가될 때마다 `FeeCalculator`를 까야 했고, 한 번 잘못 건드려서 **기존 셀러 수수료 전체가 0원으로 나간 사고**가 있었습니다.

그래서 `FeeRule` 인터페이스 + `applicable(SellerType, Period)` + `calculate(Amount)` 로 추상화하고, 룰을 DB에 메타데이터로 저장 → 런타임에 `Map<RuleKey, FeeRule>` 로딩하는 구조로 바꿨습니다. 이후 **6개월간 정산 코드 수정 0건, 룰 추가 12건**으로 완전 분리됐습니다.

### 1-6. 트레이드오프

| 측면 | 얻은 것 | 잃은 것 |
|---|---|---|
| 변경 격리 | 신규 룰 추가가 기존 코드 안 건드림 | 인터페이스 1개 + 구현 30개 = 클래스 폭증 |
| 테스트 | 룰별 단위 테스트 독립 | 통합 테스트는 더 어려워짐 |
| 인지 부하 | 룰 하나만 보면 됨 | "전체 흐름"을 한 화면에서 못 봄 |
| 성능 | 거의 동일 | 동적 디스패치 1회 (무시 가능) |

### 1-7. 한 줄 정리

**OCP+DIP는 "내일 무언가가 추가될 곳"에만 핀포인트로 적용합니다. 모든 곳에 다 적용하면 추상화 세금이 운영 비용을 잡아먹습니다.**

---

## 2. 원칙끼리 충돌할 때의 트레이드오프

### 2-1. 한 줄 정의

**SOLID는 서로 직교하지 않습니다. SRP를 극단까지 밀면 OCP의 추상화와 충돌하고, OCP를 극단까지 밀면 YAGNI와 충돌합니다.** 시니어의 핵심 역량은 "어디서 멈출지" 입니다.

### 2-2. 충돌 사례 — SRP의 극단화 → 클래스 폭증

```java
// SRP 광신도 코드
class OrderValidator { /* 검증만 */ }
class OrderPriceCalculator { /* 가격 계산만 */ }
class OrderDiscountApplier { /* 할인 적용만 */ }
class OrderTaxCalculator { /* 세금 계산만 */ }
class OrderShippingFeeCalculator { /* 배송비만 */ }
class OrderFinalAmountAggregator { /* 합산만 */ }
class OrderPersister { /* 저장만 */ }
class OrderEventPublisher { /* 이벤트 발행만 */ }
class OrderNotificationSender { /* 알림만 */ }
class OrderAuditLogger { /* 감사 로그만 */ }
// → 주문 1건 처리에 10개 클래스. 흐름이 어디로 가는지 추적 불가
// → Facade 또 만들어야 함 → 추상화의 추상화
```

**실무 결과**: 주문 한 건 디버깅하는데 10개 파일 왔다 갔다. **"클래스 수"가 적정점을 넘으면 인지 부하가 폭증**합니다.

### 2-3. 충돌 사례 — OCP의 극단화 → YAGNI 위반

```java
// "혹시 미래에 결제수단 더 생길지 모르니"
public interface PaymentMethod { ... }
public interface PaymentMethodFactory { ... }
public interface PaymentMethodRegistry { ... }
public interface PaymentMethodResolver { ... }
public interface PaymentMethodChain { ... }
// 3년이 지나도 결제수단은 카드 하나뿐
// 결국 카드 결제 한 줄 고치려고 인터페이스 5개 통과
```

YAGNI(You Aren't Gonna Need It): **"필요해질 때까지 만들지 마라"**. OCP는 "변할 곳"에만 적용해야지, "변할지도 모를 곳"에 다 적용하면 골격만 남고 살이 안 붙습니다.

### 2-4. 충돌 사례 — DIP가 ISP를 깨는 케이스

거대한 `Repository` 인터페이스를 만들고 모두가 의존하게 하면 DIP는 만족하지만, 실제로는 한 메서드만 쓰는데 인터페이스 30개 메서드를 다 mock 해야 합니다. ISP 위반.

```java
// DIP만 만족, ISP는 위반
public interface UserRepository {
    User findById(Long id);
    List<User> findAll();
    List<User> findByStatus(Status s);
    Page<User> search(SearchCriteria c);
    long countActive();
    void save(User u);
    void delete(Long id);
    // ... 30개 더
}

// Reader/Writer로 쪼개야 ISP까지 만족
public interface UserReader { User findById(Long id); }
public interface UserWriter { void save(User u); }
```

### 2-5. 시니어가 쓰는 판단 기준

| 상황 | 우선 원칙 | 멈출 지점 |
|---|---|---|
| 신규 도메인 설계 | SRP > OCP | 클래스 5~7개 넘어가면 통합 검토 |
| 외부 시스템 어댑터 | DIP > 전부 | 어댑터마다 인터페이스 1개씩 (당연) |
| 도메인 내부 정책 | OCP | "지금 2번째 변형"이 보일 때만 추상화 (Rule of Three) |
| 유틸/공통 모듈 | SRP > ISP | 인터페이스 메서드 5개 넘으면 분리 |
| 프로토타입/실험 | YAGNI > 전부 | 일단 동작하는 한 클래스 |

### 2-6. 내가 실제 만난 충돌

대형 프로젝트에서 한 후배가 SRP에 광신했습니다. **`OrderService` 메서드 하나당 클래스 하나**를 만들었어요. `PlaceOrderHandler`, `CancelOrderHandler`, `RefundOrderHandler`, ... 50개. 처음엔 깔끔해 보였는데, 6개월 뒤 신규 입사자가 "주문 취소 흐름을 따라가는 데 1시간" 걸렸습니다. **명령(Command) 패턴 + 한 Service**로 합쳤더니 가독성이 살아났습니다.

### 2-7. 한 줄 정리

**"원칙은 합쳐지지 않습니다. 어디서 멈출지가 시니어의 일입니다." Rule of Three — 같은 패턴이 3번 나타나기 전에 추상화하지 않습니다.**

---

## 3. 원칙 위반이 만든 실제 장애와 해결

### 3-1. God Object — 한 클래스가 전부 알고 있는 사고

#### 시나리오

레거시 `MemberService`가 회원가입·로그인·프로필 수정·결제수단 관리·포인트 적립·등급 산정·탈퇴·이메일 발송까지 **2500줄, 메서드 80개**. 어느 날 등급 산정 로직을 손봤는데, 회원가입 시 부가 처리 중 등급 산정 메서드가 호출되고 있어서 **신규 가입자 전원에게 VIP 등급이 부여되는 사고**가 났습니다.

#### 왜 일어났나

- SRP 위반: "Member 관련"이라는 이유로 모든 책임이 한 곳에.
- 사이드 이펙트의 그물: 한 메서드가 다른 메서드를 부르고, 그게 또 다른 메서드를 부름.
- 테스트 어려움: 한 메서드 테스트하려고 mock 20개 필요 → 결국 안 짠 테스트가 많음.

#### 해결

1. **명사 추출**: Member, Auth, Profile, PaymentMethod, Point, Grade, Notification — 7개 도메인 경계 도출.
2. **이벤트로 분리**: 회원가입 → `MemberRegisteredEvent` 발행 → 등급/포인트/이메일은 리스너에서 처리. **동기 직접 호출을 끊었습니다.**
3. **점진적 마이그레이션**: 한 번에 다 못 합니다. 새 기능부터 새 서비스로 빼고, 기존 호출은 Facade로 위임 → 6개월 동안 점진 분리.

```java
// Before
class MemberService {
    void register(...) {
        // 저장
        // 등급 계산 (사고 지점)
        // 포인트 지급
        // 이메일 발송
        // ...
    }
}

// After
class MemberService {
    void register(...) {
        Member m = memberRepo.save(...);
        events.publish(new MemberRegisteredEvent(m.id()));  // 끝
    }
}

@EventListener
class GradeCalculator {
    void on(MemberRegisteredEvent e) { ... }  // 기본 등급만 부여
}
```

### 3-2. 잘못된 상속 — Fragile Base Class

#### 시나리오

`BaseEntity` → `User` → `AdminUser` → `SuperAdminUser` 4단 상속. `BaseEntity.save()` 안에서 `validate()` 가 호출되는데, 누가 `AdminUser.validate()` 를 오버라이드하면서 super 호출을 빼먹었습니다. **결과**: 어드민 계정 저장 시 검증이 통째로 스킵 → 비밀번호 검증 우회 권한 상승 취약점.

#### 왜 일어났나

- 상속은 부모의 호출 시퀀스(template method)에 자식이 묶이는 강결합.
- 부모가 자식의 모든 오버라이드를 예측하기 어려움 — fragile base class problem.

#### 해결

- 상속 트리 폐기, **컴포지션으로 전환**: `User` 클래스 하나 + `Role` 컬렉션. 어드민 권한은 데이터(Role)로 표현.
- 검증은 `Validator` 인터페이스 + 권한별 구현체 주입 — 오버라이드가 아니라 합성.

```java
// Before — 상속 함정
abstract class BaseEntity {
    public final void save() { validate(); doSave(); }
    protected abstract void validate();
}
class AdminUser extends BaseEntity {
    protected void validate() {
        // super.validate() 빼먹음 → 사고
    }
}

// After — 컴포지션
class User {
    private final Set<Role> roles;
    public void save(List<Validator> validators) {
        validators.forEach(v -> v.validate(this));
        repo.save(this);
    }
}
```

### 3-3. Tight Coupling — Cascade Failure

#### 시나리오

주문 API가 결제 → 재고 → 알림 → 정산 → 추천 시스템 업데이트까지 **동기로 직접 호출**. 추천 시스템 응답이 10초 늘어지자 주문 API 전체가 풀이 막혀 다운. **타임아웃 cascade**.

#### 왜 일어났나

- 직접 의존 — 추천 시스템이 어떻게 죽든 주문 API에 그대로 전파.
- 동기 호출 — 한 곳 느려지면 줄줄이 막힘.

#### 해결

- **DIP + 비동기 경계**: 비즈니스에 필수가 아닌 호출(알림, 추천 업데이트)은 이벤트 발행으로 전환. 결제·재고는 사가(Saga)로 보상 로직 포함.
- **Bulkhead 패턴**: 호출별 스레드 풀 분리 — 추천 시스템 호출이 막혀도 결제 호출에 영향 없음.
- **서킷 브레이커**: Resilience4j로 추천 호출 보호 — 임계치 초과 시 자동 차단.

```java
// Before — 동기 직접 호출
class OrderService {
    void place(Order o) {
        paymentClient.pay(o);
        inventoryClient.reserve(o);
        notificationClient.send(o);  // 여기 느려지면 전체 다운
        recommendationClient.update(o);  // 여기도
    }
}

// After — 핵심만 동기, 나머지는 이벤트
class OrderService {
    void place(Order o) {
        paymentClient.pay(o);
        inventoryClient.reserve(o);
        events.publish(new OrderPlacedEvent(o.id()));  // 알림/추천은 비동기
    }
}
```

### 3-4. 한 줄 정리

**God Object는 SRP 부재, Fragile Base는 상속 남용, Cascade Failure는 DIP+경계 부재. 세 사고 모두 "원칙을 안 지킨" 비용이 운영에서 청구됩니다.**

---

## 4. DDD / Clean Architecture / Hexagonal과 OOP 원칙의 접점

### 4-1. 한 줄 정의

**현대 아키텍처 패턴(DDD, Clean, Hexagonal)은 SOLID를 "큰 단위"로 적용한 것입니다.** 클래스 레벨 SRP/DIP가 모듈/계층 레벨 Bounded Context/Port-Adapter로 확장됐을 뿐 본질은 같습니다.

### 4-2. 매핑표

| DDD/Clean 개념 | OOP 원칙 | 의미 |
|---|---|---|
| Bounded Context | SRP (모듈 단위) | 한 컨텍스트는 한 가지 책임 |
| Aggregate | SRP + 캡슐화 | 일관성 경계, 외부는 루트만 접근 |
| Repository | DIP | 도메인이 인프라(JPA/MyBatis)를 모름 |
| Use Case (Interactor) | SRP + OCP | 한 시나리오 = 한 클래스, 신규 시나리오 = 새 클래스 |
| Port (in/out) | DIP + ISP | 도메인이 외부와 닿는 작은 인터페이스 |
| Adapter | OCP | 새 외부 시스템 = 새 어댑터, 도메인 무관 |
| Application Layer | Facade + SRP | 시나리오 오케스트레이션 |
| Domain Event | OCP + 느슨한 결합 | 다른 컨텍스트는 이벤트로만 반응 |

### 4-3. Hexagonal — 구조

```
[Excalidraw: Hexagonal-Architecture]

        ┌─────────────────────────────────────┐
        │       Adapter (외부 입출력)         │
        │  ┌──────────┐         ┌──────────┐  │
        │  │ Web Ctrl │         │ JPA Repo │  │
        │  │ (in)     │         │ (out)    │  │
        │  └────┬─────┘         └─────▲────┘  │
        │       │ Port               │ Port  │
        │  ┌────▼─────────────────────┴────┐  │
        │  │   Application (Use Case)     │  │
        │  │  ┌────────────────────────┐  │  │
        │  │  │  Domain (순수 OOP)     │  │  │
        │  │  │  Aggregate, Entity,    │  │  │
        │  │  │  Value Object, 정책    │  │  │
        │  │  └────────────────────────┘  │  │
        │  └──────────────────────────────┘  │
        └─────────────────────────────────────┘

    화살표는 항상 안쪽(Domain)을 향함 — DIP의 시각화
```

### 4-4. 코드로 본 Aggregate + Repository (DIP)

```java
// Domain Layer — 순수 자바, 프레임워크/DB 모름
public class Order {  // Aggregate Root
    private final OrderId id;
    private final List<OrderLine> lines;  // 외부에 노출 안 함 (캡슐화)
    private OrderStatus status;

    public void cancel() {
        if (status == OrderStatus.SHIPPED) throw new IllegalStateException();
        this.status = OrderStatus.CANCELED;
        // 상태 변경의 일관성은 Aggregate가 보장
    }

    public Money totalAmount() {
        return lines.stream().map(OrderLine::amount).reduce(Money.ZERO, Money::add);
    }
}

// Domain Port — 도메인이 정의하는 인터페이스
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}

// Application — 시나리오 (Use Case)
@Service
public class CancelOrderUseCase {
    private final OrderRepository orders;  // DIP — 인터페이스에만 의존

    public void cancel(OrderId id) {
        Order order = orders.findById(id).orElseThrow();
        order.cancel();  // 도메인이 비즈니스 룰 보유
        orders.save(order);
    }
}

// Infrastructure Adapter — JPA 구현 (도메인에서 안 보임)
@Repository
public class JpaOrderRepository implements OrderRepository {
    private final OrderJpaEntityRepo jpa;
    public Optional<Order> findById(OrderId id) {
        return jpa.findById(id.value()).map(this::toDomain);
    }
    // ...
}
```

### 4-5. Bounded Context와 SRP의 확장

DDD의 Bounded Context는 **모듈 단위 SRP**입니다.

- "주문" 컨텍스트의 `Product`와 "카탈로그" 컨텍스트의 `Product`는 같은 이름이지만 다른 클래스 — 각자의 책임이 다르기 때문.
- 컨텍스트 간 통신은 **이벤트 또는 ACL(Anti-Corruption Layer)** — 직접 모델 공유 금지.

### 4-6. 실무에서 본 함정

- **Anemic Domain Model**: Entity는 getter/setter만, 로직은 전부 Service에. → 절차지향 코드 + JPA 엔티티. DDD라고 부르지만 OOP가 아닙니다. 캡슐화 부재.
- **거대 Aggregate**: 일관성 욕심에 Order에 모든 걸 다 넣으면 락 경합·메모리 폭증. Aggregate는 **트랜잭션 일관성 경계**만큼만.
- **Layer 광신**: Controller → Service → Domain → Repository 4계층을 모든 모듈에 강제. CRUD 화면 하나에 4개 파일이 같은 내용 반복.

### 4-7. 한 줄 정리

**DDD/Clean/Hexagonal은 "SOLID를 모듈 레벨로 끌어올린 것". 핵심은 의존성 방향이 항상 도메인(안쪽)을 향한다는 것 — DIP의 거대한 시각화입니다.**

---

## 5. 테스트 코드에서 객체지향 원칙이 어떻게 반영되는가

### 5-1. 한 줄 정의

**테스트 가능성은 OOP 원칙의 부산물입니다.** DIP를 따르면 mocking이 자연스럽고, SRP를 따르면 단위 테스트가 작아지고, ISP를 따르면 fake 객체가 단순해집니다. **반대로, 테스트가 어려우면 설계가 잘못된 신호입니다.**

### 5-2. DIP → Mocking이 가능해짐

```java
// DIP 위반 — new로 직접 생성
public class OrderService {
    private final PaymentGateway gw = new TossPaymentGateway();  // 강결합
    public void pay(Order o) { gw.charge(o); }
}
// 테스트: 진짜 Toss API 호출하지 않으면 못 짬

// DIP 적용
public class OrderService {
    private final PaymentGateway gw;  // 인터페이스
    public OrderService(PaymentGateway gw) { this.gw = gw; }
    public void pay(Order o) { gw.charge(o); }
}
// 테스트
@Test
void pay_charges_gateway() {
    PaymentGateway mock = mock(PaymentGateway.class);
    OrderService svc = new OrderService(mock);
    svc.pay(order);
    verify(mock).charge(order);
}
```

### 5-3. SRP → 단위 테스트가 작아짐

```java
// SRP 위반 — 한 메서드가 검증+계산+저장+이벤트 발행
class OrderService {
    void place(Order o) {
        validate(o);
        calculatePrice(o);
        applyDiscount(o);
        save(o);
        publishEvent(o);
    }
}
// 단위 테스트 하나당 "전체 흐름"을 다 셋업해야 함
// → 테스트 1개에 mock 5개, given 30줄

// SRP 적용 — 책임 분리
class OrderValidator { boolean validate(Order o) { ... } }
class PriceCalculator { Money calculate(Order o) { ... } }
// → 각각 mock 0~1개로 테스트 가능
```

### 5-4. ISP → Fake 객체가 단순해짐

```java
// ISP 위반 — 30개 메서드 인터페이스
interface UserRepository {
    User findById(Long id);
    List<User> findAll();
    // ... 28개 더
}
class UserServiceTest {
    // findById만 쓰는데 fake 만들려면 30개 다 구현 (UnsupportedOperationException 도배)
    UserRepository fake = new UserRepository() { ... };
}

// ISP 적용
interface UserReader { User findById(Long id); }
class UserServiceTest {
    UserReader fake = id -> testUser;  // 람다 한 줄로 끝
}
```

### 5-5. LSP → 테스트 더블의 신뢰성

LSP를 어긴 Mock은 **테스트는 통과해도 운영에서 깨집니다**. 예: `Map` 인터페이스를 구현한 Mock이 null을 허용하면, 운영에서 `HashMap`이 NPE 던지는데 테스트는 통과.

→ 시니어는 **Stub/Fake는 실제 구현체의 제약을 따라야 한다**고 생각합니다. Mockito로 아무거나 리턴하게 만드는 건 위험합니다.

### 5-6. OCP → 테스트 추가가 기존 테스트를 깨지 않음

새 PaymentMethod 구현체를 추가했을 때, **기존 결제수단 테스트가 깨지면 안 됩니다.** OCP를 잘 지킨 설계는 테스트도 격리됩니다.

### 5-7. 시니어가 본 실무 함정 — Mock Hell

```java
// 안티패턴
@Mock A a; @Mock B b; @Mock C c; @Mock D d; @Mock E e; @Mock F f;
when(a.foo()).thenReturn(...);
when(b.bar()).thenReturn(...);
// ... given 50줄
svc.run();
verify(a).foo(); verify(b).bar(); // ... 검증 30줄
// → 결국 "내가 mock한 대로 동작한다"는 동어반복
// → 리팩토링 한 번에 다 깨짐 → 테스트가 변경을 막는 짐이 됨
```

**해결**: 통합 테스트(Testcontainers + 실제 DB) 위주로 가고, 단위 테스트는 **순수 도메인 로직(VO, 계산, 정책)**에만 집중. 도메인이 외부에서 분리돼 있으면(Hexagonal) 도메인 단위 테스트는 mock 0개로 가능합니다.

### 5-8. 한 줄 정리

**테스트 가능성은 OOP 원칙을 잘 지킨 코드의 부산물이지, 따로 만드는 게 아닙니다. Mock이 많이 필요하다 = 설계가 강결합돼 있다는 신호입니다.**

---

## 6. SOLID 리팩토링 Before/After

### 6-1. 한 줄 정의

**리팩토링의 본질은 "if-else의 점진적 폭증 → 객체로 분리"와 "직접 의존 → 인터페이스 의존" 두 가지 변환입니다.** 패턴 이름(Strategy, Factory)은 결과지 원인이 아닙니다.

### 6-2. Case 1 — Strategy 패턴 도입 (if-else → 객체 분리)

#### Before — OCP 위반

```java
class Shipper {
    public Money calculateFee(Order o, String courier) {
        if (courier.equals("CJ")) {
            return o.weight() < 5 ? Money.of(3000) : Money.of(5000);
        } else if (courier.equals("HANJIN")) {
            return o.weight() < 3 ? Money.of(2500) : Money.of(4500);
        } else if (courier.equals("LOTTE")) {
            // 30줄짜리 복잡 로직 + 도서산간 가중치
            ...
        } else if (courier.equals("LOGEN")) {
            ...
        }
        throw new IllegalArgumentException();
    }
}
// 신규 택배사 추가 = 이 메서드 또 까기
// 테스트: courier 종류만큼 case 분기 다 커버 필요
```

#### After — Strategy + OCP

```java
public interface ShippingFeePolicy {
    Money fee(Order o);
    boolean supports(Courier c);
}

@Component class CjShippingPolicy implements ShippingFeePolicy { ... }
@Component class HanjinShippingPolicy implements ShippingFeePolicy { ... }
@Component class LotteShippingPolicy implements ShippingFeePolicy { ... }

@Service
public class Shipper {
    private final Map<Courier, ShippingFeePolicy> policies;
    public Shipper(List<ShippingFeePolicy> all) {
        this.policies = all.stream()
            .collect(toMap(p -> /*supports로부터 키*/, identity()));
    }
    public Money calculateFee(Order o, Courier c) {
        return Optional.ofNullable(policies.get(c))
            .orElseThrow(() -> new UnsupportedCourierException(c))
            .fee(o);
    }
}
```

#### 변화

| 측면 | Before | After |
|---|---|---|
| 신규 택배사 추가 | 기존 메서드 수정 | 새 클래스 추가만 |
| 회귀 리스크 | 전체 분기 영향 | 신규 클래스만 |
| 테스트 | 1개 메서드 N개 case | 각 정책 독립 테스트 |
| 가독성 | 한 메서드 200줄 | 각 정책 30줄 |
| 성능 | if 분기 | Map lookup O(1) — 동일 |

### 6-3. Case 2 — DIP로 인터페이스 분리

#### Before — 강결합

```java
@Service
public class ReportService {
    private final JdbcTemplate jdbc = ...;  // 인프라 직접 의존
    private final RestTemplate http = new RestTemplate();  // 외부 API 직접

    public void generateReport(LocalDate d) {
        List<Sale> sales = jdbc.query("SELECT ...", ...);  // SQL 박힘
        String fxRate = http.getForObject("https://fx.com/...", String.class);  // URL 박힘
        Report r = build(sales, fxRate);
        Files.write(Path.of("/data/report.csv"), r.toCsv().getBytes());  // 경로 박힘
    }
}
// 단위 테스트: DB·외부 API·파일시스템 다 필요
// 외부 환율 API가 바뀌면? → ReportService 수정
```

#### After — DIP

```java
public interface SaleRepository { List<Sale> findByDate(LocalDate d); }
public interface FxRateProvider { BigDecimal usdToKrw(LocalDate d); }
public interface ReportStorage { void save(String name, String content); }

@Service
public class ReportService {
    private final SaleRepository sales;
    private final FxRateProvider fx;
    private final ReportStorage storage;

    public void generateReport(LocalDate d) {
        Report r = Report.build(sales.findByDate(d), fx.usdToKrw(d));
        storage.save("report-" + d + ".csv", r.toCsv());
    }
}
```

#### 변화

- **테스트**: 3개 인터페이스 fake로 100% 단위 테스트.
- **유연성**: DB → MongoDB로 바꿔도 `ReportService` 손 안 댐.
- **장애 격리**: 환율 API 장애 시 `FxRateProvider` 구현체만 fallback 추가.

### 6-4. Case 3 — Builder 도입 (생성자 폭발)

```java
// Before
new Order(userId, addressId, items, couponId, paymentMethodId, deliveryDate,
          memo, gift, recurring, parentOrderId);  // 인자 10개, 순서 헷갈림

// After
Order.builder()
    .userId(userId)
    .items(items)
    .couponId(couponId)
    // 필요한 것만 명시
    .build();
```

OOP 원칙 자체보다 가독성·유지보수성을 확 끌어올립니다.

### 6-5. 성능 변화

OOP 리팩토링은 대부분 **성능에 거의 영향 없습니다**:

- 메서드 호출 한 단 추가 = JIT 인라이닝 후 사실상 동일
- 동적 디스패치 1회 = vtable lookup 1ns 미만 (Strategy 패턴)
- 추상화 비용 < 변경 비용

**예외**: 핫루프(초당 수십만 번) 안에서 다형성 호출이 메가모픽으로 빠지면 인라이닝 실패 → 5~10배 느려질 수 있음. 그 경우만 핫스팟 한정으로 다시 합칩니다.

### 6-6. 한 줄 정리

**리팩토링은 "변할 축을 객체로 빼고, 의존을 인터페이스로 뒤집는" 두 동작의 반복입니다. 패턴 이름은 결과지 출발점이 아닙니다.**

---

## 7. OOP + FP 혼용 — 도메인은 OOP, 변환은 FP, 부작용은 격리

### 7-1. 한 줄 정의

**현대 자바는 OOP 골격에 FP 도구를 끼워 쓰는 게 정답입니다.** 도메인 모델은 OOP(캡슐화·다형성), 데이터 변환은 Stream/Optional, 부작용은 끝단에 격리.

### 7-2. 왜 혼용인가

- **OOP 단독**: 작은 변환 로직에 클래스 만들기 과합 → 보일러플레이트.
- **FP 단독**: 100명 팀에서 도메인 경계가 흐려짐 → 어디에 뭐가 있는지 grep 신세.
- **혼용**: 도메인 객체에 비즈니스 룰 캡슐화 + 컬렉션 변환은 Stream + 부작용은 어댑터로 밀어냄.

### 7-3. 코드 — Stream + Immutable Value + Optional

```java
// Value Object — record로 불변
public record Money(BigDecimal amount, Currency currency) {
    public Money add(Money other) {
        if (!currency.equals(other.currency)) throw new IllegalArgumentException();
        return new Money(amount.add(other.amount), currency);  // 새 객체 반환 — 불변
    }
}

// 도메인 객체 — 캡슐화된 OOP
public class Order {
    private final List<OrderLine> lines;
    private final Money discount;

    public Money totalAmount() {
        return lines.stream()
            .map(OrderLine::amount)
            .reduce(Money.ZERO, Money::add)
            .subtract(discount);  // FP 스타일 변환, OOP 객체에 캡슐화
    }

    public Optional<OrderLine> findLine(ProductId id) {
        return lines.stream()
            .filter(l -> l.productId().equals(id))
            .findFirst();  // Optional로 null 회피
    }
}
```

### 7-4. 부작용 격리 — Functional Core, Imperative Shell

```
[Excalidraw: Functional-Core-Imperative-Shell]

  외부 ── Shell (어댑터, I/O) ──┬── DB
                               ├── HTTP
                               └── Queue
            │
            ▼
       Core (순수 함수, 도메인)
       - 입력 → 출력
       - 부작용 없음
       - 테스트: mock 0개
```

```java
// Shell — 부작용 (얇은 어댑터)
@Service
public class PlaceOrderHandler {
    private final OrderRepository orders;
    private final EventPublisher events;

    @Transactional
    public OrderId place(PlaceOrderCommand cmd) {
        // 1. 데이터 끌어오기
        Customer c = customers.findById(cmd.customerId()).orElseThrow();
        // 2. 순수 도메인 호출 (Core)
        Order order = Order.create(c, cmd.items(), cmd.couponCode());
        // 3. 부작용
        orders.save(order);
        events.publish(new OrderPlacedEvent(order.id()));
        return order.id();
    }
}

// Core — 순수, 부작용 없음 (테스트 100%)
public class Order {
    public static Order create(Customer c, List<Item> items, String coupon) {
        // 검증, 계산, 정책 적용 — 순수 계산
        // DB·HTTP 호출 없음
        return new Order(...);
    }
}
```

### 7-5. 혼용의 트레이드오프

| 측면 | 장점 | 함정 |
|---|---|---|
| 가독성 | Stream으로 컬렉션 처리 간결 | 3단 이상 중첩 Stream은 디버깅 지옥 |
| 불변성 | thread-safe, 추론 쉬움 | 객체 생성 비용 (대부분 escape analysis로 제거됨) |
| 테스트 | 순수 함수는 mock 0개 | "어디까지 순수로 갈지" 경계 잡기 어려움 |
| Optional | NPE 방지 | 도메인에 `Optional<Optional<X>>` 같은 괴물 등장 |
| Stream | 선언적 | 디버거에서 step-into 어려움, 스택트레이스 난해 |

### 7-6. 실무에서 본 안티패턴

```java
// 안티 1 — Stream으로 부작용
list.stream().forEach(item -> repository.save(item));
// → 부작용을 Stream에 박음. 평범한 for 루프가 더 나음

// 안티 2 — Optional을 필드/파라미터에
public void process(Optional<User> userOpt) { ... }
// → Optional은 반환값 전용. 파라미터·필드는 NPE만 더 키움

// 안티 3 — 무한 메서드 체인
list.stream()
    .filter(...).map(...).filter(...).map(...)
    .collect(groupingBy(..., mapping(..., counting())));
// → 한 줄로 짠 30단계 변환. 디버거 진입 불가
// → 중간에 변수로 끊기
```

### 7-7. 한 줄 정리

**도메인은 캡슐화된 OOP로, 데이터 변환은 FP로, 부작용은 끝단(어댑터)에 격리합니다. "Functional Core, Imperative Shell"이 현대 자바의 정답입니다.**

---

## 8. MSA에서 객체지향 원칙의 확장

### 8-1. 한 줄 정의

**MSA는 SOLID를 프로세스 경계 너머로 확장한 것입니다.** Bounded Context는 SRP, 서비스간 통신은 DIP, Saga는 OCP의 분산 버전입니다. 다만 **네트워크 경계가 끼어들면서 트레이드오프가 완전히 달라집니다.**

### 8-2. 매핑

| OOP 원칙 (단일 프로세스) | MSA에서의 형태 |
|---|---|
| SRP (클래스) | Bounded Context (서비스) |
| DIP (인터페이스 의존) | API 계약 (OpenAPI, gRPC IDL, Event Schema) |
| OCP (확장 닫힌 코드) | 이벤트 기반 확장 (새 컨슈머만 추가) |
| 캡슐화 | 데이터 소유권 (한 서비스만 자기 DB 쓰기) |
| LSP (자식 치환) | API 버전 호환 (v2가 v1을 깨면 안 됨) |
| ISP | API endpoint 분리, BFF 패턴 |

### 8-3. Bounded Context = 서비스 경계

DDD의 Bounded Context를 그대로 서비스 경계로 옮긴 게 MSA의 출발점입니다.

```
[Excalidraw: MSA-Bounded-Context]

  ┌────────────────┐   Event   ┌────────────────┐
  │ Order Service  │──────────▶│ Shipping Svc   │
  │  (Order Agg)   │           │ (Shipment Agg) │
  │  own DB        │           │  own DB        │
  └────────┬───────┘           └────────────────┘
           │ Event
           ▼
  ┌────────────────┐
  │ Inventory Svc  │
  │ (Stock Agg)    │
  │ own DB         │
  └────────────────┘
       각 서비스 = 캡슐화된 객체
       서비스간 = 인터페이스(이벤트/API)로만 통신
```

**핵심**: 각 서비스는 자기 DB를 직접 소유. 다른 서비스가 직접 DB에 붙으면 캡슐화 깨짐 → "공유 DB 안티패턴".

### 8-4. DIP의 확장 — API 계약

단일 프로세스에서 `interface PaymentGateway`에 의존했듯, MSA에서는 **OpenAPI 스펙**이나 **이벤트 스키마**에 의존합니다.

```yaml
# 결제 서비스의 API 계약 (OpenAPI)
paths:
  /payments:
    post:
      requestBody: { ... }
      responses: { 200: { ... } }
```

소비자는 구현이 아닌 계약에 의존 → 결제 서비스 내부가 Kotlin이든 Go든 무관. **언어 경계를 넘은 DIP**.

### 8-5. Saga 패턴 — 분산 트랜잭션의 OCP

#### 문제

단일 프로세스에서는 `@Transactional`로 끝. MSA에서는 결제·재고·배송이 다른 서비스 → 분산 트랜잭션이 필요한데 2PC는 가용성 죽임.

#### 해결 — Saga

각 단계를 **로컬 트랜잭션 + 보상 트랜잭션**으로 분해. 한 단계 실패 시 이전 단계의 보상을 차례로 호출.

```
주문생성 → 결제승인 → 재고차감 → 배송시작
   │         │         │         │
   ▼         ▼         ▼         ▼
주문취소 ← 결제취소 ← 재고복구 ← (배송실패시)
```

#### Choreography vs Orchestration

```
[Excalidraw: Choreography-vs-Orchestration]

Choreography (안무) — 각자 이벤트 듣고 자율 행동
  Order ── OrderPlaced ──▶ Payment ── PaymentApproved ──▶ Inventory
                               │
                          (각 서비스가 다음 서비스를 모름)

  + 결합도 최저, 새 컨슈머 추가 = OCP 확장
  - 전체 흐름 추적 어려움 (분산 추적 필수)

Orchestration (지휘) — 중앙 코디네이터가 명령
  Saga Orchestrator
    │
    ├─▶ Payment.charge()
    ├─▶ Inventory.reserve()
    └─▶ Shipping.start()

  + 흐름 가시성 ↑, 디버깅 쉬움
  - 코디네이터가 God Object 위험
```

#### 시니어 선택 기준

| 상황 | 선택 |
|---|---|
| 흐름이 단순(2~3단계), 자율성 중요 | Choreography |
| 흐름이 복잡(5단계+), 가시성 필요 | Orchestration |
| 정해진 비즈니스 SLA, 보상 룰 명확 | Orchestration (Camunda, Temporal) |
| 발견적·확장적 시스템 | Choreography |

### 8-6. MSA에서 OOP 원칙이 깨지는 지점

- **LSP가 무너짐**: 네트워크 지연·실패·중복이 끼어들어 "원격 호출이 로컬 호출처럼 LSP를 만족할 수 없음" — 8 Fallacies of Distributed Computing.
- **트랜잭션 일관성 포기**: ACID → BASE(Eventually Consistent). 도메인 모델링 시 "최종 일관성"을 명시적으로 다뤄야 함.
- **테스트 가능성 폭락**: 단일 프로세스에서 mock 5개로 끝나던 게, MSA에선 Contract Test(Pact) + 통합 테스트(Testcontainers) + E2E 분리 필요.

### 8-7. 시니어의 MSA OOP 체크리스트

| 항목 | 확인 |
|---|---|
| 서비스 경계 = Bounded Context인가 | 경계 잘못 그으면 분산 모놀리스 |
| 각 서비스 자기 DB만 쓰는가 | 공유 DB = 캡슐화 위반 |
| API 변경 시 하위 호환 보장 | LSP 위반 = 컨슈머 다 깨짐 |
| 이벤트 스키마에 버전 있나 | 없으면 이벤트 변경 = 전체 장애 |
| 보상 트랜잭션 다 있나 | Saga 한 단계라도 보상 빠지면 데이터 깨짐 |
| 분산 추적(Trace ID) 다 흐르는가 | Choreography에서 필수 |
| Idempotency 키 있나 | 네트워크 재시도 시 중복 처리 |
| Circuit Breaker 깔려있나 | 한 서비스 장애가 전체로 전파 안 되게 |

### 8-8. 실무에서 본 함정

- **분산 모놀리스**: 서비스를 쪼갰는데 서로 동기 호출로 묶여서 한 서비스 죽으면 전부 죽음. **결합도 더 나쁨**.
- **공유 라이브러리 지옥**: 도메인 모델을 공유 jar로 빼면 한 모델 바꾸면 전 서비스 재배포. 이러면 MSA 아닙니다.
- **이벤트 폭격**: "이벤트 = 좋은 거"라고 다 이벤트로 빼면 흐름 추적 불가 + 디버깅 지옥.
- **데이터 일관성 무지**: "결제됐는데 재고 안 빠짐" — 보상 트랜잭션 없이 출시한 사례.

### 8-9. 한 줄 정리

**MSA는 SOLID를 프로세스 경계로 확장한 것. Bounded Context = SRP, API 계약 = DIP, 이벤트 기반 = OCP. 다만 네트워크가 끼면 LSP와 ACID는 포기해야 하고, 그 대가로 Saga·Idempotency·Circuit Breaker라는 새 도구를 들여야 합니다.**

---

## 9. 8문항 종합 — 시니어 한 줄씩

1. **가장 중요한 원칙**: OCP+DIP는 한 몸. "내일 변할 곳"에만 핀포인트로 적용.
2. **원칙 충돌**: SRP 폭증 vs OCP 추상화세금 vs YAGNI. Rule of Three가 시니어의 멈춤 지점.
3. **위반이 만든 장애**: God Object(SRP), Fragile Base(상속), Cascade Failure(강결합+동기) — 운영 청구서.
4. **DDD/Clean/Hexagonal**: SOLID를 모듈 레벨로 확장. 의존 방향이 항상 도메인을 향함.
5. **테스트**: 테스트 가능성은 OOP 잘 지킨 코드의 부산물. Mock 많이 필요 = 설계 강결합 신호.
6. **리팩토링**: "변할 축을 객체로 빼기" + "의존을 인터페이스로 뒤집기" 두 동작. 성능 영향 거의 없음.
7. **OOP+FP 혼용**: 도메인은 OOP, 변환은 FP, 부작용은 끝단 격리 — Functional Core, Imperative Shell.
8. **MSA로 확장**: Bounded Context = SRP, API = DIP, Saga = 분산 OCP. 네트워크가 끼면 LSP·ACID는 포기, Saga·Idempotency·Circuit Breaker 도입.

---

## 10. 면접 답변 시 강조 포인트

- **"원칙을 다 지킨다"는 답은 신입의 답입니다.** 시니어의 답은 "어디서 멈출지"입니다.
- **추상화는 공짜가 아닙니다.** 인지 부하, 디버깅 비용, 변경 비용을 늘릴 수 있습니다.
- **"내가 운영하다가 사고 났던 케이스"** 를 항상 곁들이세요. 이론만 답하면 책 읽은 사람과 구별 안 됩니다.
- **OOP는 도구**, 목적은 **변경 비용 최소화** 입니다. OOP가 변경을 더 어렵게 만들면 안 쓰는 게 맞습니다.
- **MSA는 "OOP 원칙을 거대 스케일로 검증하는 시험대"** 입니다. 잘 지킨 원칙은 분산 환경에서도 유효하고, 못 지킨 원칙은 분산 환경에서 폭발합니다.
