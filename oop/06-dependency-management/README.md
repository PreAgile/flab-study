# 06. Dependency Management — DIP, DI, IoC

> **이 챕터의 한 줄 목표**: Spring을 쓰지 않고 순수 Java로 자체 IoC 컨테이너를 30줄로 구현해서, Spring의 마법이 사실은 단순한 위임 패턴임을 보일 수 있다. DI 4방식의 트레이드오프와 그중 생성자 주입이 권장되는 4가지 이유를 즉답할 수 있다.

## 📖 이론적 골격

| 책 | 핵심 |
|---|---|
| 조영호 『오브젝트』 8장 | 의존성 관리 — 종류와 해결 |
| Robert Martin 『Clean Architecture』 | DIP — Dependency Rule |
| Martin Fowler "Inversion of Control Containers and the Dependency Injection Pattern" (2004) | DI vs Service Locator |
| Spring Framework Reference | Spring IoC 컨테이너 |

## 학습 목표

1. **의존성의 종류** 5가지 (Class, Method, Field, Inheritance, Generic) 식별.
2. **DIP의 진짜 의미** — "상위 모듈이 하위 모듈에 의존하지 않는다"가 코드에서 어떻게 보이는지.
3. **DI 4가지 방식** (Constructor, Setter, Field, Method) 비교 + 왜 Constructor 권장.
4. **IoC vs DI vs Service Locator** 구분.
5. **Spring 없는 자체 컨테이너** 30줄 구현.

## 파일 목록

| # | 파일 | 핵심 질문 |
|---|---|---|
| 01 | [01-dependency-types.md](./01-dependency-types.md) | 의존성 5종류와 위험도 |
| 02 | [02-dip-principle.md](./02-dip-principle.md) | DIP — 상위/하위 모듈 + 추상화 의존 |
| 03 | [03-di-four-ways.md](./03-di-four-ways.md) | Constructor / Setter / Field / Method DI 비교 |
| 04 | [04-ioc-vs-di-vs-service-locator.md](./04-ioc-vs-di-vs-service-locator.md) | 세 개념의 정확한 구분 |
| 05 | [05-build-your-own-ioc.md](./05-build-your-own-ioc.md) | 30줄 자체 IoC 컨테이너 |

## 7단 학습 레이어

### 1단. 백지 그리기

```
[그림 1] 의존성의 종류
    ┌─────────────────────────────────────────────────┐
    │ 1. 클래스 의존  : new B()                          │
    │ 2. 메서드 의존  : b.doSomething()                   │
    │ 3. 필드 의존    : private B b                      │
    │ 4. 상속 의존    : class A extends B                 │
    │ 5. 제네릭 의존  : List<B>                          │
    └─────────────────────────────────────────────────┘
    위험도: 상속 > 클래스 > 필드 > 메서드 > 제네릭

[그림 2] DIP (의존성 역전 원칙)
   Before (의존성 폭발):                After (DIP 적용):
   ┌───────────────┐                  ┌───────────────┐
   │ OrderService  │                  │ OrderService  │
   └───────┬───────┘                  └───────┬───────┘
           │ new                              │ depends on
           ▼                                  ▼
   ┌───────────────┐                  ┌───────────────┐
   │ MySqlOrderRepo│                  │ <<interface>>  │  ← 추상화
   └───────────────┘                  │ OrderRepository│
                                      └───────▲───────┘
                                              │ implements
                                      ┌───────┴────────┐
                                      │  MySqlOrderRepo│
                                      └────────────────┘
   상위가 하위 알아야 함 ✗            상위는 추상화만 알면 됨 ✓

[그림 3] IoC 흐름
   전통적 흐름:                          IoC 흐름:
   ─────────────                       ──────────────
   1. main()                            1. Container 시작
   2. Service 생성                       2. Container가 객체들 생성
   3. Repository 생성                    3. Container가 의존성 주입
   4. Service.setRepository()           4. Container가 lifecycle 관리
   5. Service 호출                       5. 사용자는 빈을 꺼내 사용

   "제어권이 main"                      "제어권이 Container"
```

### 2단. 직관

- **DIP**: "추상화에 의존하라" — 구체 클래스 직접 import 금지.
- **DI**: "의존을 외부에서 받아라" — `new` 직접 호출 금지.
- **IoC**: "제어권 역전" — 객체 생명주기를 외부 컨테이너가.
- **Service Locator (안티)**: "필요할 때 컨테이너에 묻기" — 컨테이너 자체에 의존.

### 3단. 구조 — DI 4방식 비교

```java
// === Constructor Injection (권장) ===
public class OrderService {
    private final OrderRepository repository;
    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }
}
// 장점: 불변, 필수 의존성 강제, 순환 의존 컴파일 타임 감지(생성 시점)
// 단점: 의존성 많아지면 생성자 비대 (but 그건 SRP 위반 신호)

// === Setter Injection ===
public class OrderService {
    private OrderRepository repository;
    public void setRepository(OrderRepository repository) { this.repository = repository; }
}
// 장점: 선택적 의존성, 런타임 교체
// 단점: 가변, 호출 전 누락 가능 (NPE)

// === Field Injection (Spring 한정, 비권장) ===
public class OrderService {
    @Autowired
    private OrderRepository repository;
}
// 장점: 코드 짧음
// 단점: final 불가, 테스트 시 reflection 필요, DI 컨테이너에 종속

// === Method Injection (Spring 특수) ===
public abstract class OrderService {
    @Lookup
    public abstract Order createOrder();
}
// 장점: prototype 빈 매번 새로 받기
// 단점: 거의 안 씀, Spring 한정
```

### 4단. 내부 구현 — 30줄 자체 IoC 컨테이너

```java
public class MiniContainer {
    private final Map<Class<?>, Object> singletons = new ConcurrentHashMap<>();
    private final Map<Class<?>, Class<?>> bindings = new ConcurrentHashMap<>();

    public <T> void bind(Class<T> iface, Class<? extends T> impl) {
        bindings.put(iface, impl);
    }

    @SuppressWarnings("unchecked")
    public <T> T get(Class<T> type) {
        if (singletons.containsKey(type)) return (T) singletons.get(type);
        Class<?> impl = bindings.getOrDefault(type, type);
        try {
            Constructor<?> ctor = impl.getDeclaredConstructors()[0];
            Object[] args = Arrays.stream(ctor.getParameterTypes())
                .map(this::get)  // 재귀적으로 의존성 해결
                .toArray();
            Object instance = ctor.newInstance(args);
            singletons.put(type, instance);
            return (T) instance;
        } catch (Exception e) {
            throw new RuntimeException("Failed to create " + type, e);
        }
    }
}

// 사용
MiniContainer c = new MiniContainer();
c.bind(OrderRepository.class, MySqlOrderRepository.class);
OrderService service = c.get(OrderService.class);
```

→ Spring의 본질은 이것 + (lifecycle, AOP, configuration, scope, ...). 핵심 아이디어는 단순.

### 5단. 역사

- **1988 R.E. Sweet**: "The Mesa Programming Environment" — IoC 원형.
- **1996 Java Servlet**: 컨테이너가 Servlet 생명주기 관리 (IoC 사례).
- **1998 EJB**: 무거운 컨테이너 + XML 디스크립터.
- **2002 Rod Johnson 『Expert One-on-One J2EE』**: POJO 기반 가벼운 컨테이너 제안.
- **2003 Spring 1.0**: XML + setter injection 중심.
- **2004 Martin Fowler "Inversion of Control Containers and the Dependency Injection Pattern"**: 용어 정리 (IoC가 너무 광범위, DI라는 좁은 의미 명명).
- **2009 Spring 3.0**: Java Config + 어노테이션.
- **2014 Spring Boot**: Convention over Configuration.
- **2024 Spring 6 + GraalVM Native**: AOT compilation 지원.

### 6단. 트레이드오프 — DI 방식 결정 매트릭스

| 축 | Constructor | Setter | Field |
|---|---|---|---|
| **불변성** | ✓ (final) | ✗ | ✗ (final 불가) |
| **필수 의존성 강제** | ✓ (컴파일) | ✗ (런타임 NPE) | ✗ |
| **순환 의존 감지** | ✓ (생성 시) | ✗ (감춰짐) | ✗ |
| **테스트 용이성** | ✓ (직접 생성) | ✓ (setter 호출) | ✗ (reflection) |
| **DI 컨테이너 의존** | X (POJO) | X | ✓ (Spring 종속) |
| **코드 길이** | 길다 | 보통 | 짧다 |

→ **Spring 공식 권장 (Spring 4.3+)**: **Constructor Injection**. 단일 생성자는 `@Autowired` 생략 가능.

### 7단. 운영 진단

- **순환 의존 진단**:
  - Spring Boot 로그에 `BeanCurrentlyInCreationException` → 순환 의존
  - 원인: 두 빈이 서로의 생성자에서 서로를 요구
  - 해결: 책임 분리 (Pure Fabrication으로 제3의 클래스 추출) 또는 `@Lazy`
- **`@Autowired` 필드 남용 진단**:
  - 의존성이 6개 이상의 빈 → SRP 위반
  - 테스트 코드가 `@SpringBootTest` 강제 → 단위 테스트 어려움
  - → 생성자 주입 + 책임 분해
- **Service Locator 안티패턴 진단**:
  - `ApplicationContext.getBean(...)` 코드 패턴
  - 의존성이 코드 안에 숨어 있음 (시그니처에 드러나지 않음)
  - → 생성자 주입으로 의존성 명시화

## 꼬리질문

### Junior
1. **Q**: DI와 IoC의 차이가 뭔가요?
   → IoC가 더 큰 개념. "객체 생명주기/실행 제어를 외부가". DI는 IoC의 한 구현 방식 — "의존 객체를 외부가 주입".

### Senior
2. **Q**: 왜 Spring은 field injection을 권장하지 않게 되었나요?
   → 4가지 이유:
   1. `final` 불가 → 불변성 깨짐
   2. NPE 가능 (DI 컨테이너 없이 생성하면)
   3. 테스트 시 reflection 또는 Spring context 필요
   4. 의존성 숨김 → SRP 위반 신호 안 보임
3. **꼬리**: 그럼 Lombok `@RequiredArgsConstructor`가 가장 깔끔한 답인가요?
   → 그렇다. 생성자 주입의 boilerplate를 컴파일 타임에 해결. Kotlin은 primary constructor로 언어 자체에 있음.
4. **꼬리의 꼬리**: 생성자 주입을 쓰는데 의존이 10개로 늘면 어떻게 하나요?
   → 그건 신호다. 책임이 너무 많음 (SRP 위반). 분해: Pure Fabrication으로 응집도 높은 그룹 추출, Facade 패턴 도입 등.

### Principal
5. **Q**: Spring 없이 순수 Java로 DI를 구현할 때 가장 어려운 부분은?
   → **생명주기 + AOP**. Singleton/Prototype/Request/Session scope, `@PostConstruct`/`@PreDestroy`, 트랜잭션 프록시 — 이 모두를 자체 구현하면 Spring과 비슷한 무게가 됨. → "왜 Spring을 쓰는가"의 진짜 답: 컨테이너 자체가 아니라 그 부속물(AOP, Transaction, Web MVC 등) 때문.
6. **꼬리**: Native Image (GraalVM)에서 Spring DI는 어떻게 동작하나요?
   → 리플렉션을 컴파일 타임에 분석 + AOT compile. Spring 6+의 `@AotProcessor`가 빈 정의를 코드 생성. 런타임 리플렉션 비용 제거. 단, 동적 빈 등록은 제한.
7. **꼬리의 꼬리**: 그렇다면 GraalVM 시대에 DI 컨테이너의 미래는?
   → "런타임 DI"는 줄고, "컴파일 타임 DI" 증가 (Dagger 2 같은 사전 컴파일 DI). Kotlin은 `koin` (런타임) vs `kotlin-inject` (컴파일 타임) 분기. Java도 미시적으로 같은 방향.

## 다음 챕터로

- [07-flexible-design](../07-flexible-design/) — SOLID + 디자인 패턴
