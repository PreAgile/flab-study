# 06-01. DI + IoC — DIP의 실천

> "Spring 없이 30줄로 IoC 컨테이너 구현" — DI의 마법이 사실 단순 위임.

## 📍 학습 목표

1. **DIP (Dependency Inversion Principle)** — 추상에 의존.
2. **DI (Dependency Injection)** — 의존성 외부 주입.
3. **IoC (Inversion of Control)** — 제어 흐름 역전.
4. **DI 4방식** + 생성자 주입 권장 이유.
5. 자체 IoC 컨테이너 구현.

## 🔁 DIP — 추상에 의존하라

```java
// Bad — 구체 의존
class OrderService {
    private MySQLOrderRepository repo = new MySQLOrderRepository();
    // → DB 변경 시 OrderService 수정
}

// Good — 추상 의존
class OrderService {
    private OrderRepository repo;   // 인터페이스
    
    OrderService(OrderRepository repo) {
        this.repo = repo;
    }
}
// → repo가 MySQL이든 Postgres든 OrderService 영향 없음
```

## 💉 DI 4방식

### 1. Constructor Injection (권장)

```java
class OrderService {
    private final OrderRepository repo;
    
    public OrderService(OrderRepository repo) {
        this.repo = repo;
    }
}
```

장점:
- final 필드 가능 (immutable).
- 필수 dependency 명시.
- 순환 의존 컴파일 에러로 잡힘.
- 테스트 쉬움 (mock 주입).

### 2. Setter Injection

```java
class OrderService {
    private OrderRepository repo;
    
    public void setRepo(OrderRepository repo) {
        this.repo = repo;
    }
}
```

단점: 가변, null 가능, 순환 의존 런타임에야 발견.

### 3. Field Injection (Spring `@Autowired`)

```java
class OrderService {
    @Autowired
    private OrderRepository repo;   // ← 안티패턴
}
```

문제:
- Spring 의존 (테스트 시 Spring context 필요).
- final 불가.
- 순환 의존 잡기 어려움.
- 의존성 명시 안 됨.

### 4. Method Injection

```java
class OrderService {
    @Lookup
    protected OrderRepository getRepo() { return null; }   // Spring이 override
}
```

거의 안 쓰임.

## 🎯 IoC — 제어 흐름 역전

```
[전통적 흐름]
Main → OrderService → OrderRepository → ...
   (caller가 callee 직접 생성)

[IoC]
Main → IoC Container → 모든 객체 등록 & 주입
                ↓
        OrderService (repo는 컨테이너가 주입)
```

→ "객체 생성 + 연결" 책임이 caller에서 컨테이너로 역전.

## 🛠️ 30줄 IoC 컨테이너

```java
public class SimpleContainer {
    private Map<Class<?>, Object> instances = new HashMap<>();
    
    public <T> void register(Class<T> type, T instance) {
        instances.put(type, instance);
    }
    
    public <T> T resolve(Class<T> type) {
        if (instances.containsKey(type)) {
            return type.cast(instances.get(type));
        }
        // 생성자 주입 — 첫 번째 생성자 찾고 파라미터 재귀 resolve
        Constructor<?> ctor = type.getConstructors()[0];
        Object[] args = Arrays.stream(ctor.getParameterTypes())
                              .map(this::resolve)
                              .toArray();
        try {
            T instance = (T) ctor.newInstance(args);
            instances.put(type, instance);
            return instance;
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
    }
}

// 사용
SimpleContainer c = new SimpleContainer();
c.register(OrderRepository.class, new MySQLOrderRepository());
OrderService service = c.resolve(OrderService.class);
// → service.repo가 MySQLOrderRepository로 주입됨
```

→ Spring의 핵심은 이 30줄의 정교한 확장. (BeanDefinition + ApplicationContext + AOP)

## 📊 DI vs Service Locator vs Singleton

| | DI | Service Locator | Singleton |
|---|---|---|---|
| 의존성 표현 | 생성자 (명시) | locator.get() (숨김) | 전역 access |
| 테스트 | 쉬움 (mock 주입) | locator mock 필요 | 어려움 (전역 상태) |
| 순환 의존 | 컴파일/생성 시 발견 | 런타임 | 런타임 |
| 권장 | ✅ | △ (DI 도입 어려운 경우) | ❌ |

## ⚔️ 꼬리질문

### Q. 생성자 주입이 권장되는 4가지 이유는?

> 1. **Final 가능** — immutable, thread-safe.
> 2. **필수 의존성 명시** — 생성자 시그니처가 contract.
> 3. **순환 의존 컴파일 에러** — 생성 시점에 발견.
> 4. **테스트 쉬움** — Spring 없이 new로 만들 수 있음.

### Q. (Killer) `@Autowired` field 주입이 안티패턴인 이유는?

> 1. Spring 의존 강제 — 단위 테스트 시 ApplicationContext 필요.
> 2. final 불가 — gerenak 변경 가능.
> 3. 순환 의존 런타임에야 발견.
> 4. 의존성 명시 안 됨 — 외부에서 OrderService 만들 때 누락 가능.
> 5. Reflection 기반 — 약간의 성능 영향.
> 
> 권장: 생성자 주입 + Lombok `@RequiredArgsConstructor`.

## 🔗 다음

- → [07. Flexible Design](../07-flexible-design/)
- → [Chapter 12. Spring](../12-spring-and-framework/)
