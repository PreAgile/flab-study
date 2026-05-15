# 12. Spring & Framework — OOP를 운영 가능하게

> **이 챕터의 한 줄 목표**: Spring IoC 컨테이너의 내부(BeanDefinition → BeanFactory → ApplicationContext)를 한 호흡에 설명할 수 있다. `@Transactional`의 함정 5가지(self-invocation, private, propagation, exception, default isolation)와 그 원인이 모두 OOP 메커니즘(프록시 = 합성)에서 비롯됨을 설명할 수 있다.

## 📖 이론적 골격

| 자료 | 핵심 |
|---|---|
| Rod Johnson 『Expert One-on-One J2EE』 (2002) | Spring의 사상적 출발점 |
| Spring Framework Reference Documentation | 공식 |
| 『Spring in Action』 (Craig Walls) | Spring 입문 결정판 |
| Juergen Hoeller 발표들 | 핵심 개발자 인터뷰 |

## 학습 목표

1. **Spring IoC 컨테이너 내부** — BeanDefinition, BeanFactory, ApplicationContext.
2. **DI 처리 흐름** — 빈 생성, 의존성 주입, 라이프사이클.
3. **Spring AOP의 프록시 메커니즘** — JDK Dynamic Proxy vs CGLIB.
4. **`@Transactional`의 5대 함정** — 모두 프록시(합성)의 한계에서 비롯.
5. **Spring과 OOP 원칙의 관계** — Spring이 DIP, OCP, SRP를 어떻게 실현하나.
6. **Spring 안티패턴** — `@Autowired` 필드, `ApplicationContext.getBean()`, 어노테이션 지옥.

## 파일 목록

| # | 파일 | 핵심 질문 |
|---|---|---|
| 01 | [01-spring-ioc-internals.md](./01-spring-ioc-internals.md) | BeanDefinition → BeanFactory → ApplicationContext |
| 02 | [02-spring-di-deep.md](./02-spring-di-deep.md) | DI 처리 흐름 + 빈 생성 단계 |
| 03 | [03-spring-aop-and-proxy.md](./03-spring-aop-and-proxy.md) | JDK Dynamic Proxy vs CGLIB |
| 04 | [04-transactional-pitfalls.md](./04-transactional-pitfalls.md) | `@Transactional` 5대 함정 |
| 05 | [05-spring-and-oop-principles.md](./05-spring-and-oop-principles.md) | Spring과 SOLID의 관계 |
| 06 | [06-spring-antipatterns.md](./06-spring-antipatterns.md) | 어노테이션 지옥, 빈 폭발, Service-Locator |
| 07 | [07-domain-vs-application-service.md](./07-domain-vs-application-service.md) | Domain Service / Application Service / Use Case |

## 7단 학습 레이어

### 1단. 백지 그리기

```
[그림 1] Spring IoC Container 내부
   ┌──────────────────────────────────────────────────────────────┐
   │  ApplicationContext (확장된 BeanFactory)                       │
   │  ┌────────────────────────────────────────────────────────┐  │
   │  │  BeanFactory (기본)                                      │  │
   │  │  ┌───────────────────────────────────────────────┐    │  │
   │  │  │  BeanDefinition Registry                      │    │  │
   │  │  │  ┌─────────────────────────────────────┐     │    │  │
   │  │  │  │  Map<String, BeanDefinition>        │     │    │  │
   │  │  │  │   - orderService → BeanDefinition    │     │    │  │
   │  │  │  │   - orderRepository → BeanDefinition │     │    │  │
   │  │  │  └─────────────────────────────────────┘     │    │  │
   │  │  └───────────────────────────────────────────────┘    │  │
   │  │  + Singleton Cache: Map<String, Object>                │  │
   │  │  + BeanPostProcessor 체인                              │  │
   │  └────────────────────────────────────────────────────────┘  │
   │  + 이벤트 발행 (ApplicationEvent)                              │
   │  + 메시지 소스 (i18n)                                         │
   │  + 리소스 로딩 (classpath:, file:)                            │
   │  + 환경 (Environment, Profile)                                │
   └──────────────────────────────────────────────────────────────┘

[그림 2] 빈 생성 라이프사이클 (10단계)
   1. Class 스캔 (@ComponentScan)
   2. BeanDefinition 등록
   3. 생성자 호출 (인스턴스화)
   4. 의존성 주입 (setter/field)
   5. *Aware 인터페이스 콜백 (BeanNameAware 등)
   6. BeanPostProcessor.postProcessBeforeInit
   7. @PostConstruct, InitializingBean.afterPropertiesSet, init-method
   8. BeanPostProcessor.postProcessAfterInit  ← AOP 프록시 여기서 wrapping
   9. 사용
   10. @PreDestroy, DisposableBean.destroy, destroy-method

[그림 3] AOP 프록시
   클라이언트                                 실제 객체
       │                                       │
       │ orderService.process(order)             │
       │ ─────────────────────────────────►    │
                │                              │
                ▼                              │
        ┌──────────────────┐                   │
        │  Spring AOP Proxy │                  │
        │  (CGLIB or JDK)  │                   │
        ├──────────────────┤                   │
        │  before: 트랜잭션 시작 │ ───────►  ┌──────────────┐
        │                  │              │ OrderService  │
        │  invoke target   │              │ (실제)         │
        │                  │              └──────────────┘
        │  after: commit    │ ◄───────  
        └──────────────────┘
       │
       │ 결과 반환
       │ ◄─────────────────────────────────
       ▼
   클라이언트
```

### 2단. 직관

- **Spring IoC**: "객체 그래프 조립을 외부 컨테이너가" — DI Container.
- **Spring AOP**: "관심사를 어드바이스로 분리" — 프록시로 끼워넣기.
- **본질**: 둘 다 OOP의 **합성** 메커니즘의 산업적 실용화.

### 3단. 구조 — DI 처리 흐름 (코드 추적)

```java
// 사용자 코드
@Service
public class OrderService {
    private final OrderRepository repository;
    public OrderService(OrderRepository repository) {  // 생성자 주입
        this.repository = repository;
    }
}

// Spring 내부 동작
// 1. ConfigurationClassPostProcessor가 @Service 스캔
// 2. AnnotatedBeanDefinitionReader.register() 호출
//    → BeanDefinition(class=OrderService, scope=singleton, ...)
// 3. BeanDefinitionRegistry에 등록
//
// 첫 사용 시:
// 4. DefaultListableBeanFactory.getBean("orderService")
// 5. createBean() 호출
//    → instantiateBean() : 생성자 결정
//      - Constructor 1개: 자동 선택
//      - 여러 개: @Autowired 또는 @Primary 또는 가장 적합한 것
//    → resolveDependency() : 파라미터 타입(OrderRepository) → bean lookup
//      - getBean("orderRepository") 재귀 호출
//    → ConstructorResolver.autowireConstructor()
//      - 의존성 다 모이면 reflection으로 new OrderService(repository)
// 6. populateBean() : @Autowired field/setter 처리
// 7. initializeBean() : BeanPostProcessor + init 메서드
//    - 여기서 AOP 프록시 wrapping (AbstractAutoProxyCreator)
// 8. singletonObjects 캐시에 등록
```

### 4단. 내부 구현 — `@Transactional` 5대 함정

```java
@Service
public class OrderService {

    // === 함정 1: self-invocation ===
    @Transactional
    public void publicMethod() {
        this.privateMethod();  // 프록시 우회 → @Transactional 무효
    }

    @Transactional(propagation = REQUIRES_NEW)
    private void privateMethod() {
        // 새 트랜잭션 안 열림 (private + self-invocation 둘 다 문제)
    }

    // === 함정 2: private 메서드 ===
    // CGLIB/JDK 프록시는 public 메서드만 가로챔
    // 해결: public으로 + 동작 분리

    // === 함정 3: 잘못된 propagation ===
    @Transactional  // 기본 REQUIRED — 외부 트랜잭션에 join
    public void method() {
        try {
            externalApi.call();
        } catch (Exception e) {
            // 예외 무시 — 하지만 트랜잭션은 이미 rollback-only로 마킹됨
            // 다음 commit에서 UnexpectedRollbackException
        }
    }

    // === 함정 4: Checked Exception rollback ===
    @Transactional  // 기본: RuntimeException만 rollback, Checked는 commit
    public void method() throws IOException {
        // IOException 던지면 rollback 안 됨
        // 해결: @Transactional(rollbackFor = Exception.class)
    }

    // === 함정 5: default isolation ===
    @Transactional  // DB 기본 (보통 READ_COMMITTED)
    public void method() {
        // Phantom read, non-repeatable read 가능
        // 해결: isolation 명시 또는 SELECT FOR UPDATE
    }
}
```

→ **모든 함정의 공통 원인**: AOP 프록시 = **합성** 메커니즘. 합성은 외부에서 가로채는 것이라 내부 호출은 못 잡음. 상속 기반 AOP라면 self-invocation 작동하지만, Spring은 의도적으로 합성 선택 (Effective Java 18조 — 상속보다 합성).

### 5단. 역사

| 연도 | 사건 | 트리거 |
|---|---|---|
| 1997 | EJB 1.0 | Sun의 엔터프라이즈 표준 시도 |
| 2002 | Rod Johnson 책 | "EJB는 너무 무겁다, POJO + 가벼운 컨테이너로 충분" |
| 2003 | Spring 1.0 | XML + setter injection |
| 2006 | Spring 2.0 | XML namespace, AspectJ |
| 2009 | Spring 3.0 | Java Config, REST |
| 2013 | Spring 4.0 + Spring Boot 1.0 | Convention over Configuration |
| 2017 | Spring 5.0 + WebFlux | Reactive Programming |
| 2022 | Spring 6.0 + Spring Boot 3.0 | Java 17 baseline, AOT, GraalVM Native |
| 2024 | Spring Boot 3.3 | Virtual Thread 정식 지원 |

### 6단. 트레이드오프 — Spring과 대안

| 비교 | Spring | Micronaut | Quarkus | Helidon |
|---|---|---|---|---|
| **DI 처리 시점** | 런타임 (리플렉션) | 컴파일 타임 | 컴파일 타임 | 런타임 |
| **시작 시간** | 느림 | 빠름 | 빠름 (Native 더) | 중간 |
| **GraalVM Native** | 6+ 지원 (까다로움) | 처음부터 | 처음부터 (RedHat) | 지원 |
| **에코시스템** | 압도적 | 중간 | 중간 | 작음 |
| **러닝 커브** | 큼 | 중간 | 중간 | 작음 |
| **Kubernetes 친화** | 보통 | 좋음 | 매우 좋음 | 좋음 |

→ **결정 기준**: 레거시 + 큰 에코시스템 → Spring. 마이크로서비스 + 빠른 시작 → Micronaut/Quarkus.

### 7단. 운영 진단 — Spring 안티패턴

- **어노테이션 지옥**:
  - 한 클래스에 어노테이션 10개 이상
  - 동작이 어노테이션에 숨어 추적 어려움
  - → Java Config (`@Configuration` + `@Bean`) 사용, 명시적 코드 우선
- **빈 폭발 (Bean Explosion)**:
  - 모든 클래스가 `@Service`/`@Component`
  - Spring context 시작 시간 수십 초
  - → 도메인 객체는 빈 X, 기술 어댑터(Repository, Controller, Gateway)만 빈
- **`ApplicationContext.getBean()` 사용**:
  - Service Locator 안티패턴
  - 의존성이 코드에 숨음 → SRP 검증 불가
  - → 생성자 주입으로 명시화
- **순환 의존 (BeanCurrentlyInCreationException)**:
  - A가 B를, B가 A를 생성자 주입
  - → 책임 분리 또는 `@Lazy` (임시방편) 또는 setter injection
- **`@Component`로 도메인 객체 만들기**:
  - 도메인 객체는 매번 새로 생성되는데 빈은 싱글톤
  - 충돌 → ScopedProxy로 우회하지만 복잡
  - → 도메인은 POJO, Factory 빈에서 `new`

## 꼬리질문

### Junior
1. **Q**: Spring DI가 뭔가요?
   → 의존 객체를 직접 생성하지 않고 외부 컨테이너가 주입하는 패턴.

### Senior
2. **Q**: Spring AOP에서 JDK Dynamic Proxy vs CGLIB의 차이는?
   → JDK는 **인터페이스 기반** (Proxy.newProxyInstance) — 구현체가 인터페이스 가져야 함. CGLIB은 **클래스 상속 기반** — final class 못 함, private/static 메서드 못 잡음. Spring Boot 2.0+는 기본 CGLIB.
3. **꼬리**: 그럼 Kotlin은 클래스가 기본 final인데 Spring AOP가 어떻게 동작하나요?
   → `kotlin-spring` 컴파일러 플러그인이 `@Component`, `@Service`, `@Configuration`, `@Bean` 등이 붙은 클래스를 자동으로 `open`. 또는 `allopen` 플러그인으로 특정 어노테이션 지정.
4. **꼬리의 꼬리**: GraalVM Native Image에서 Spring AOP는 어떻게 동작하나요?
   → 런타임 프록시 생성 불가 → AOT 단계에서 미리 프록시 코드 생성. Spring 6+의 `@AotProcessor`. 단, 동적 프록시 (런타임 결정)는 제한.

### Principal
5. **Q**: Spring DI를 사용하면서도 OOP를 지키려면 도메인 계층은 어떻게 설계해야 하나요?
   → **Hexagonal Architecture**:
   - **도메인 (POJO)**: Spring 무관. `@Service` X. 순수 Java/Kotlin 객체.
   - **포트 (인터페이스)**: 도메인이 외부에게 명령하는 추상화 (`OrderRepository`, `PaymentGateway`).
   - **어댑터 (Spring Bean)**: 포트 구현체. `@Repository`, `@RestController`, `@Component`로 빈 등록.
   - **Application Service**: 유스케이스. 도메인 + 포트를 조율. `@Service`.
   → 도메인이 Spring을 import하지 않으면 단위 테스트 시 Spring 띄울 필요 없음.
6. **꼬리**: 그렇다면 트랜잭션은 어디에서 시작되어야 하나요?
   → **Application Service**가 트랜잭션 경계. 도메인 메서드는 트랜잭션 모름. → `@Transactional`은 `@Service` 메서드에만. 도메인은 순수.
7. **꼬리의 꼬리**: 도메인 이벤트를 Spring `ApplicationEventPublisher`로 발행하면 도메인이 Spring을 알게 되는데, 어떻게 분리하나요?
   → **Domain Events Pattern**: 도메인은 `DomainEvents.raise(event)` 같은 자체 인터페이스 사용. Spring 어댑터가 그 인터페이스를 구현하면서 `ApplicationEventPublisher`로 위임. → 도메인은 Spring 모름, 어댑터만 알음. 또는 Aggregate에 `@DomainEvents` 메서드 (Spring Data 표준).

## 다음 챕터로

- [20-ops-scenarios](../20-ops-scenarios/) — 안티패턴 운영 시나리오
- [21-hands-on-workbook](../21-hands-on-workbook/) — 조영호 예제 직접 구현
- [22-tradeoff-master-table](../22-tradeoff-master-table/) — cross-chapter 종합 비교
