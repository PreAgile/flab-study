# 30-01. Mock Interviews — Junior / Senior / Principal

> 한국 빅테크 (카카오/네이버/쿠팡/토스/당근)의 실제 OOP 면접 패턴 시뮬레이션.

## 🎯 Junior (1~3년)

### Q1. OOP의 4대 기둥은?
> 추상화, 캡슐화, 다형성, 상속 (또는 합성).

### Q2. 캡슐화가 왜 중요한가요?
> 변경의 격리. 내부 구현 변경이 외부에 영향 안 줌. 단순 "데이터 은닉"이 아니라 "변경 캡슐화".

### Q3. SOLID 5원칙을 알려주세요.
> S(SRP), O(OCP), L(LSP), I(ISP), D(DIP).
> 각각 변경 종류별 대응 전략.

### Q4. 상속과 합성의 차이?
> 상속: is-a 관계, 강한 결합, Fragile Base Class 위험.
> 합성: has-a, 약한 결합, 런타임 교체 가능.
> Effective Java 18조: "상속보다 컴포지션을".

### Q5. Spring `@Autowired` field 주입의 단점?
> 1. final 불가.
> 2. Spring 의존 (테스트 시 Spring context 필요).
> 3. 순환 의존 런타임에야 발견.
> 4. 의존성 명시 안 됨.

## 🎯 Senior (3~10년)

### Q1. Anemic Domain Model이 무엇이고 왜 안티패턴인가요?
> Entity가 getter/setter만, Service에 모든 로직.
> 사실상 절차지향 + Java syntax.
> 문제: Service 비대, 도메인 응집도 ↓, 테스트 어려움.
> 답: Rich Domain — 행위를 Entity로 이동.

### Q2. `@Transactional` self-invocation 문제는?
> Proxy 메커니즘:
> proxy.outer() 호출 → proxy 가로채기 → 원본 객체의 outer.
> outer 안의 this.inner()는 원본 메서드 직접 호출 → proxy 통하지 않음 → `@Transactional` 무시.
> 해결: getBean으로 자기 proxy 받기, AspectJ.

### Q3. Sealed Class + Pattern Matching이 OOP에 미친 영향?
> Sum Type (FP) + Subtype Polymorphism (OOP)의 통합.
> 데이터 종류 분기에 자연스러움.
> CHA 강력 — JIT inline 친화.
> 단, OCP는 약간 위반 (외부 switch).

### Q4. DDD의 Aggregate Root란?
> 일관성 경계 (transactional consistency).
> 외부는 Root를 통해서만 내부 객체 접근.
> 예: Order (Root) — OrderLine, Payment.
> 외부 코드가 OrderLine.add 직접 안 함, Order.addLine.

### Q5. (Killer) Service 클래스가 비대해진 시스템을 어떻게 리팩토링?
> 1. 책임 식별 — SRP 위반 지점.
> 2. Rich Domain 도입 — 비즈니스 로직 Entity로.
> 3. Use Case별 Application Service 분리.
> 4. Domain Service (다중 Aggregate 조율) 도입.
> 5. Repository 패턴 명확히.
> 6. Hexagonal Architecture 검토.

## 🎯 Principal (10년+)

### Q1. OOP와 FP의 통합 방향은?
> Java 21이 보여줌:
> - Subtype polymorphism (OOP) — 동작 다형성.
> - Sealed + Pattern Matching (FP) — 데이터 분기.
> - Record (FP) — Immutable data.
> - Virtual Thread — async도 sync 코드처럼.
> 
> 미래: 두 패러다임 경계 흐려짐. 도구로 함께 사용.

### Q2. 100대 규모 서비스의 OOP 코드 품질 관리 전략?
> 1. **Code Review 표준**:
>    - SOLID 점검 checklist.
>    - 안티패턴 카탈로그 (20-1 챕터).
> 2. **자동화 도구**:
>    - SonarQube, PMD, SpotBugs.
>    - Architecture decision records (ADR).
> 3. **DDD 전략**:
>    - 핵심 도메인 분리.
>    - Bounded Context 명시.
> 4. **테스트 전략**:
>    - Unit (도메인 객체 격리).
>    - Integration (Service + DB).
>    - Architecture test (ArchUnit).

### Q3. (Killer) "Spring을 안 쓴다면 OOP를 어떻게 설계하시겠어요?"
> Spring의 본질은 IoC + AOP.
> Spring 없이도 같은 효과:
> 1. **수동 의존 주입** — main()에서 객체 wire.
> 2. **자체 IoC 컨테이너** — Chapter 06 30줄 예제.
> 3. **AOP**:
>    - JDK Dynamic Proxy + InvocationHandler.
>    - 또는 데코레이터 패턴 명시.
> 4. **트랜잭션 경계** — Service 메서드 entry/exit에 try/finally.
> 5. **테스트** — Spring 없이 new로 만들 수 있어 오히려 쉬움.
> 
> 결론: Spring은 boilerplate를 줄이는 도구. 본질은 OOP 설계 원칙.

### Q4. 기술 부채를 OOP 관점에서 정의하면?
> 기술 부채 = "변경 비용의 누적".
> OOP는 변경 격리 도구 — 캡슐화, 다형성, DIP.
> 안티패턴 (Anemic, God Object 등) = 변경 격리 실패 = 부채 누적.
> 
> 측정:
> - 한 기능 변경의 영향 클래스 수.
> - 코드 리뷰 시간.
> - 테스트 추가 비용.
> 
> 갚는 방법: 리팩토링 — 안티패턴 → 좋은 OOP 패턴.

## ⚔️ 코드 리뷰 시뮬레이션

```java
@RestController
@RequestMapping("/orders")
public class OrderController {
    
    @Autowired
    private OrderRepository orderRepo;
    @Autowired
    private CustomerRepository customerRepo;
    @Autowired
    private PaymentService paymentService;
    @Autowired
    private EmailService emailService;
    
    @PostMapping
    public ResponseEntity<?> create(@RequestBody Map<String, Object> body) {
        Long customerId = ((Number) body.get("customerId")).longValue();
        List<Map<String, Object>> items = (List) body.get("items");
        
        Customer customer = customerRepo.findById(customerId).orElseThrow();
        Order order = new Order();
        order.setCustomer(customer);
        order.setStatus("PENDING");
        
        BigDecimal total = BigDecimal.ZERO;
        for (Map<String, Object> item : items) {
            OrderLine line = new OrderLine();
            line.setProductId(((Number) item.get("productId")).longValue());
            line.setQuantity(((Number) item.get("quantity")).intValue());
            line.setPrice(new BigDecimal(item.get("price").toString()));
            order.getLines().add(line);
            total = total.add(line.getPrice().multiply(new BigDecimal(line.getQuantity())));
        }
        order.setTotal(total);
        
        if (order.getCustomer().getVipLevel() > 5) {
            order.setTotal(order.getTotal().multiply(new BigDecimal("0.9")));
        }
        
        orderRepo.save(order);
        paymentService.process(order);
        emailService.sendOrderConfirm(customer.getEmail(), order);
        
        return ResponseEntity.ok(order);
    }
}
```

### 발견할 문제들

1. **Anemic Domain** — Order, OrderLine 모두 getter/setter.
2. **God Method** — Controller에 모든 로직.
3. **Primitive Obsession** — Map<String, Object> 입력.
4. **@Autowired field 주입** — 4개.
5. **Business logic in Controller** — VIP 할인.
6. **Tight coupling** — Payment, Email 동기 호출.
7. **No transaction boundary**.
8. **No error handling**.

### 리팩토링 plan

1. DTO 도입 (`OrderRequest`, `OrderResponse`).
2. Constructor injection.
3. Order Entity에 행위 (`Order.addLine`, `Order.applyDiscount`).
4. OrderService에 use case 분리.
5. @Transactional 추가.
6. EmailService 비동기 (CompletableFuture or @Async).

## 🔗 OOP 챕터 완료

모든 챕터의 cross-reference로 30분 면접 시뮬레이션 가능.
