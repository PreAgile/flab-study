# 안티패턴 퀵 레퍼런스 (코드 리뷰용)

> 코드 리뷰 시 즉석으로 찾아볼 수 있는 안티패턴 사전.
> 각 항목: **증상 → 원칙 위반 → 리팩토링 패턴**.

## 1. God Object / God Service
**증상**:
- 클래스 1000줄 넘음
- 메서드 30개 이상
- 의존성 7개 이상 주입
- 클래스 이름이 `*Manager`, `*Service`, `*Util`, `*Helper`

**위반**: SRP

**리팩토링**: Extract Class → CRC 카드 워크숍 → 책임별 새 클래스로

**참조**: [03-responsibility-assignment](../03-responsibility-assignment/)

---

## 2. Anemic Domain Model
**증상**:
- Entity에 `get*` / `set*` 만 있음
- 비즈니스 동사 메서드 (`cancel`, `pay`, `apply`) 0개
- 비즈니스 로직이 Service에 잔뜩

**위반**: Tell Don't Ask, 정보 전문가, 캡슐화

**리팩토링**:
1. Service의 메서드 중 Entity 데이터만 사용하는 것 → Move Method
2. Service는 트랜잭션·이벤트·외부 호출만 책임

**참조**: [01-object-and-collaboration](../01-object-and-collaboration/), [04-message-and-interface](../04-message-and-interface/)

---

## 3. Feature Envy
**증상**:
- `b.getX().doSomething(a.getY())` 같은 코드
- 한 클래스가 다른 클래스의 getter를 5회+ 호출
- 메서드의 절반 이상이 다른 객체 데이터 조작

**위반**: 정보 전문가, Demeter

**리팩토링**: Move Method 또는 위임 메서드 추가

**참조**: [04-message-and-interface/02-law-of-demeter.md](../04-message-and-interface/)

---

## 4. Inappropriate Intimacy (부적절한 친밀)
**증상**:
- 두 클래스가 서로의 private 데이터에 접근
- inner class로 외부 클래스 필드 직접 접근
- 친구 클래스 패턴 (C++ friend, Kotlin internal 남용)

**위반**: 캡슐화

**리팩토링**: Extract Class (공통 데이터를 새 클래스로) 또는 Move Field

---

## 5. Refused Bequest (거부된 유산)
**증상**:
- 자식 클래스가 부모의 메서드 중 절반을 빈 구현 / UnsupportedOperationException
- 부모 메서드를 `@Deprecated` 또는 final로 막음

**위반**: LSP

**리팩토링**: Replace Inheritance with Delegation, ISP 적용

**참조**: [08-inheritance-vs-composition](../08-inheritance-vs-composition/)

---

## 6. Shotgun Surgery (산탄총 수술)
**증상**:
- 한 요구사항 변경 시 10곳 이상 파일 수정
- 같은 if/switch 분기가 여러 곳에 반복

**위반**: OCP, DRY

**리팩토링**: Move Method → Inline Class 또는 Extract Class. Replace Conditional with Polymorphism.

**참조**: [07-flexible-design](../07-flexible-design/)

---

## 7. Divergent Change (분기 발산)
**증상**:
- 한 클래스가 다양한 이유로 자주 변경됨
- 같은 클래스 안의 메서드들이 서로 다른 stakeholder의 요구로 변경

**위반**: SRP

**리팩토링**: Extract Class

---

## 8. Magic String / Magic Number
**증상**:
- `"VIP"`, `"PENDING"`, `"COMPLETED"` 같은 문자열 분기
- `if (status == 1)` 같은 숫자 비교

**위반**: 캡슐화, 타입 안전성

**리팩토링**: enum 또는 sealed class. Replace Type Code with Class/Subclass.

---

## 9. Primitive Obsession (원시 타입 집착)
**증상**:
- `String email`, `String phoneNumber`, `int amount` 잔뜩
- 메서드 시그니처에 `int, int, int, int` 같이 의미 모호한 파라미터

**위반**: 도메인 표현력 부족

**리팩토링**: Replace Primitive with Object. Value Object 도입 (`Email`, `Money`, `PhoneNumber`).

---

## 10. Long Parameter List
**증상**:
- 메서드 파라미터 5개 이상
- 같은 4~5개 파라미터가 여러 메서드에 반복

**위반**: 캡슐화

**리팩토링**: Introduce Parameter Object. Preserve Whole Object.

---

## 11. Switch Statement (조건문 의존)
**증상**:
- `switch (type) { case A: ... case B: ... }` 같은 분기
- 같은 분기가 여러 메서드에 반복

**위반**: OCP

**리팩토링**: Replace Conditional with Polymorphism (Strategy 패턴) 또는 sealed + pattern matching.

**참조**: [05-object-decomposition](../05-object-decomposition/)

---

## 12. Spring 어노테이션 지옥
**증상**:
- 한 클래스에 어노테이션 8개 이상
- `@Service @Transactional @Validated @Cacheable @Async @EventListener @Retryable @CircuitBreaker`

**위반**: SRP, 가독성

**리팩토링**:
- 트랜잭션은 Application Service만
- 캐시는 Decorator 패턴 또는 별도 어댑터
- 비동기는 Domain Event + Listener
- 회로 차단기는 외부 Gateway에

**참조**: [12-spring-and-framework](../12-spring-and-framework/)

---

## 13. `@Autowired` 필드 주입
**증상**:
```java
@Autowired
private OrderRepository repository;
```

**위반**: 4가지 (final 불가, NPE 가능, 테스트 어려움, 의존성 숨김)

**리팩토링**: Constructor Injection + Lombok `@RequiredArgsConstructor` 또는 Kotlin primary constructor

**참조**: [06-dependency-management](../06-dependency-management/)

---

## 14. `ApplicationContext.getBean()` 사용 (Service Locator)
**증상**:
```java
applicationContext.getBean(OrderService.class)
```

**위반**: 의존성 숨김, 테스트 어려움

**리팩토링**: 생성자 주입으로 명시화. 동적 빈이 필요하면 `ObjectProvider<T>` 사용.

---

## 15. 순환 의존
**증상**:
- `BeanCurrentlyInCreationException`
- 클래스 A의 import에 B, B의 import에 A

**위반**: DIP, Acyclic Dependencies Principle

**리팩토링**:
1. Pure Fabrication — 공통 책임을 제3의 클래스로 추출
2. Domain Event로 비동기화
3. 임시방편: `@Lazy`

---

## 16. self-invocation으로 `@Transactional` 우회
**증상**:
```java
@Transactional
public void publicMethod() {
    this.privateMethod();  // 새 트랜잭션 안 열림
}
```

**위반**: AOP 프록시 메커니즘 이해 부족

**리팩토링**:
1. 메서드를 별도 클래스로 분리 (외부에서 호출되도록)
2. `((MyService) AopContext.currentProxy()).privateMethod()` (권장 X)
3. ApplicationEvent로 비동기화

---

## 17. Pattern Overdose (패턴 남용)
**증상**:
- `AbstractOrderProcessorFactoryBean`
- 5개 이상 디자인 패턴 한 도메인에 적용
- 비즈니스 어휘가 패턴 명칭에 묻힘

**위반**: YAGNI, 가독성

**리팩토링**: Inline Class. 패턴 제거하고 단순 클래스/메서드로.

---

## 18. Null Object 없이 Null 반환
**증상**:
```java
public User findByEmail(String email) {
    return null;  // 호출자가 null 체크
}
```

**위반**: NPE 위험

**리팩토링**:
- Java: `Optional<User>`
- Kotlin: `User?`
- 또는 Null Object 패턴: `User.NONE`

---

## 19. Lazy Loading 폭발 (JPA)
**증상**:
- N+1 쿼리
- `LazyInitializationException`

**위반**: 도메인 - 영속성 결합

**리팩토링**:
- DTO Projection
- Fetch Join
- `@EntityGraph`
- Open Session in View 의존 X

---

## 20. 도메인 객체에 Spring 어노테이션
**증상**:
```java
@Component
public class Order { ... }
```

**위반**: 도메인 순수성, 도메인-Spring 결합

**리팩토링**: 도메인은 POJO, 기술 어댑터(Repository, Controller)만 빈. Hexagonal Architecture.

---

## 빠른 진단 매트릭스

| 코드 신호 | 첫 의심 안티패턴 | 참조 챕터 |
|---|---|---|
| `getX().getY().doZ()` | Feature Envy / Demeter 위반 | 04 |
| 메서드 200줄 넘음 | God Object / Long Method | 03 |
| Entity 메서드 0개 (getter 제외) | Anemic Domain | 01, 02 |
| `extends` 4단 이상 | Inheritance 남용 | 08 |
| Service 의존성 7개+ | God Service / SRP 위반 | 03 |
| 어노테이션 8개+ | Spring 어노테이션 지옥 | 12 |
| `@Autowired private` | Field Injection 안티패턴 | 06 |
| `if (type == "VIP")` | Magic String + Switch | 07 |
| 같은 분기 5곳 이상 반복 | Shotgun Surgery | 07 |
| `BeanCurrentlyInCreation` | 순환 의존 | 06 |
| `LazyInitializationException` | JPA Lazy 폭발 | 20 |
