# 12-01. Spring IoC + @Transactional 함정

> Spring의 마법 = BeanDefinition + ApplicationContext + AOP (proxy).
> `@Transactional` 함정은 모두 proxy(합성) 메커니즘에서 비롯.

## 📍 학습 목표

1. Spring IoC 컨테이너 내부 흐름.
2. AOP의 proxy 메커니즘.
3. `@Transactional` 5가지 함정.

## 🏛️ Spring IoC 흐름

```
[1. 설정 로드]
   @Configuration, @Component, @Bean 스캔
        │
        ▼
[2. BeanDefinition 등록]
   각 빈의 클래스, 의존성, scope 정의
        │
        ▼
[3. BeanFactory 빈 생성]
   순환 의존 검사 + 생성 + DI
        │
        ▼
[4. ApplicationContext 시작]
   모든 빈 ready + ApplicationEvent
```

## 🎭 AOP — 모든 마법의 핵심

### @Transactional 동작

```java
@Service
class OrderService {
    @Transactional
    public void process(Order o) {
        // ...
    }
}

// 사용
orderService.process(order);
```

내부:
```
caller
   ↓
Spring이 만든 Proxy (CGLib 또는 JDK Dynamic Proxy)
   ↓
@Transactional 처리:
   - 시작: tx.begin()
   - 본문 실행
   - 끝: tx.commit() 또는 tx.rollback()
   ↓
실제 OrderService 메서드
```

→ proxy = 합성. `orderService` 변수는 사실 proxy.

## 💥 @Transactional 5가지 함정

### 1. Self-invocation

```java
@Service
class OrderService {
    public void outer() {
        this.inner();   // ★ proxy 통하지 않음
    }
    
    @Transactional
    public void inner() {
        // ...
    }
}

// 호출
orderService.outer();
// → outer는 proxy 통하지만 inner의 this.inner()는 원본 메서드
// → @Transactional 무시
```

해결: ApplicationContext에서 자기 proxy 주입 받거나, AspectJ 사용.

### 2. private 메서드

```java
@Transactional
private void method() { ... }
// → proxy가 private 메서드 가로채지 못함
// → @Transactional 무시
```

해결: public 으로.

### 3. Propagation 함정

```java
@Transactional   // 기본 REQUIRED
void a() {
    b();   // b의 @Transactional이 a의 tx와 합쳐짐
}

@Transactional(propagation = Propagation.REQUIRES_NEW)
void b() {
    // ← 새 tx 시작. a와 별도.
    throw new RuntimeException();   // b만 rollback, a는 그대로
}
```

함정: propagation 잘못 이해 → 의도와 다른 rollback.

### 4. Exception 종류

```java
@Transactional
void method() throws IOException {
    throw new IOException();   // ← checked exception
    // 기본은 RuntimeException + Error만 rollback
    // IOException은 rollback 안 됨
}
```

해결: `@Transactional(rollbackFor = Exception.class)`.

### 5. Default Isolation

```java
@Transactional   // 기본 isolation = DEFAULT (DB 설정 따름)
void method() { ... }
```

DB마다 default 다름:
- MySQL: REPEATABLE_READ.
- PostgreSQL: READ_COMMITTED.

→ 명시 권장: `@Transactional(isolation = READ_COMMITTED)`.

## ⚔️ 꼬리질문

### Q. CGLib vs JDK Dynamic Proxy의 차이?

> - **JDK Dynamic Proxy**: 인터페이스 기반. 인터페이스 구현체만 proxy.
> - **CGLib**: 클래스 상속. final class 못 proxy.
> 
> Spring 5+: 기본 CGLib (interface 없어도 OK).

### Q. (Killer) `@Transactional` self-invocation 함정의 근본 원인은?

> Proxy 패턴 = 합성.
> proxy.outer() 호출 시 proxy가 가로채 tx 시작.
> 그 안에서 this.inner() = 원본 객체의 inner.
> 원본 객체는 proxy 모르므로 inner의 @Transactional 무시.
> 
> 근본: AOP가 합성으로 구현 → method 호출이 객체 경계 안에서만 가로채짐.
> 
> 해결법:
> 1. ApplicationContext.getBean으로 자기 proxy 받기.
> 2. @Autowired로 자기 자신 주입 (Spring 4+).
> 3. AspectJ (compile-time weaving) — 모든 호출 가로챔.

## 🔗 다음

- → [20. Ops Scenarios](../20-ops-scenarios/)
