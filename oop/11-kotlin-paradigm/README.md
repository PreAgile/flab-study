# 11. Kotlin Paradigm — Java를 넘어선 균형

> **이 챕터의 한 줄 목표**: "Kotlin = Java + syntactic sugar"는 틀린 시각이다. JetBrains가 Java의 어떤 결정을 의식적으로 뒤집었는지(Nullable 타입, val/var, primary constructor, 확장 함수, 코루틴 등) 각각의 **설계 의도와 트레이드오프**를 설명할 수 있다. Java 21과 Kotlin 1.9의 차이를 한 표로 정리.

## 📖 이론적 골격

| 자료 | 핵심 |
|---|---|
| 『Kotlin in Action』 (Dmitry Jemerov) | Kotlin 설계 철학 |
| 『Effective Kotlin』 (Marcin Moskala) | 36개 규칙 |
| JetBrains Blog "The Kotlin Programming Language" | 설계 결정 기록 |
| Andrey Breslav 발표들 | Kotlin 창시자 인터뷰 |

## 학습 목표

1. **Kotlin이 Java의 어떤 결정을 뒤집었나** — 6가지 핵심.
2. **Null Safety**의 타입 시스템 수준 통합 — Java `Optional`과의 차이.
3. **`val`/`var`** + **`data class`** + **`sealed class`** 균형.
4. **확장 함수, 스코프 함수, 위임** — Java에 없는 도구들.
5. **Coroutine vs Virtual Thread** — 동시성 모델 비교.
6. **Kotlin의 함수형 도입 깊이** — 일급 함수, 고차함수, 모나드 지원.

## 파일 목록

| # | 파일 | 핵심 질문 |
|---|---|---|
| 01 | [01-kotlin-design-philosophy.md](./01-kotlin-design-philosophy.md) | 6가지 핵심 결정 |
| 02 | [02-null-safety.md](./02-null-safety.md) | Optional을 넘어선 타입 시스템 |
| 03 | [03-data-class-vs-record.md](./03-data-class-vs-record.md) | data class vs Java record 비교 |
| 04 | [04-sealed-and-pattern.md](./04-sealed-and-pattern.md) | sealed + when의 6년 선행 |
| 05 | [05-extension-and-scope.md](./05-extension-and-scope.md) | 확장 함수 + 스코프 함수 |
| 06 | [06-delegation.md](./06-delegation.md) | `by` 키워드 — 위임의 언어 차원 |
| 07 | [07-coroutine-vs-vthread.md](./07-coroutine-vs-vthread.md) | 동시성 — 두 가지 답 |
| 08 | [08-kotlin-fp-features.md](./08-kotlin-fp-features.md) | 함수형 도구 — Arrow, sequences 등 |

## 7단 학습 레이어

### 1단. 백지 그리기

```
[그림 1] Kotlin이 Java를 뒤집은 6가지
   결정              Java              Kotlin              왜 뒤집었나
   ──────           ──────             ──────              ──────────
   null 처리         NullableEverywhere  Nullable 타입        NPE 80%가 null 처리 누락
   변수 선언         var (Java 10+)      val 기본 + var       불변 우선이 안전
   상속 가능성        open 기본          final 기본 (open 명시)  실수 상속 방지
   생성자           N개 오버로드         primary + secondary    명확한 주 진입점
   클래스 본문 vs 확장  메서드 추가 = 클래스 변경  확장 함수 (외부 추가)  open class를 안 만들고도 확장
   Equality         equals + ==        ==(structural) + ===(referential)  의도 명확

[그림 2] Null Safety 타입 시스템
   Java:
     String s = null;          // 컴파일 OK
     s.length();                // 런타임 NPE

   Kotlin:
     val s: String = null      // 컴파일 에러 ✗
     val s: String? = null     // OK (Nullable 타입)
     s.length                  // 컴파일 에러 ✗ (안전 호출 필요)
     s?.length                 // OK, 결과는 Int?
     s!!.length                // OK, null이면 KotlinNullPointerException

   → 컴파일러가 nullable/non-nullable 추적
   → "Optional 도입은 늦은 답, Kotlin은 타입 시스템 차원에서 해결"

[그림 3] data class vs record
   Kotlin (2016)                 Java (2021)
   ─────────────                 ─────────────
   data class Point(             record Point(
       val x: Int,                  int x,
       val y: Int                   int y
   )                             ) {}
                                  
   자동 생성                      자동 생성
   - equals/hashCode/toString    - equals/hashCode/toString
   - copy(x = 10)                - (copy 없음 — 명시적 생성)
   - componentN() destructuring  - record pattern (Java 21)

   상속 가능 (open 추가 시)        상속 금지 (final)
   var 가능                       모든 component final 강제
```

### 2단. 직관

- **Kotlin 한 줄**: "Java의 어색함을 의식적으로 뒤집은 언어. 100% 상호운용성 유지하면서."
- **JetBrains 동기**: "IntelliJ를 Java로 만드는 게 너무 고통. 더 나은 언어가 필요."
- **선언 우선순위**: 불변 > 가변, non-null > nullable, final > open.

### 3단. 구조 — Kotlin의 OOP 강화 + FP 강화

```kotlin
// === OOP 강화 ===
sealed class Result<out T> {
    data class Success<T>(val value: T) : Result<T>()
    data class Failure(val error: String) : Result<Nothing>()
}
// sealed + data + generic variance (`out T`) → Java보다 풍부한 타입

class OrderService(
    private val repository: OrderRepository,
    private val notifier: Notifier = DefaultNotifier(),  // 기본값
) {
    // primary constructor + DI 한 줄
}

// === FP 강화 ===
val result = listOf(1, 2, 3)
    .map { it * 2 }
    .filter { it > 2 }
    .sum()
// Stream 없이도 자연스러움

// 확장 함수
fun String.toSnakeCase(): String = ...
// String 자체를 변경하지 않고 메서드 추가

// 스코프 함수
order.apply {
    customerId = 1L
    items.add(item)
}.also {
    log.info("Order created: $it")
}
```

### 4단. 내부 구현 — Kotlin의 컴파일 결과

```kotlin
data class Point(val x: Int, val y: Int)
```

컴파일 후 (Java 디컴파일):
```java
public final class Point {
    private final int x;
    private final int y;
    public Point(int x, int y) { ... }
    public final int getX() { return this.x; }
    public final int getY() { return this.y; }
    public final int component1() { return this.x; }  // destructuring
    public final int component2() { return this.y; }
    public final Point copy(int x, int y) { return new Point(x, y); }
    public boolean equals(Object o) { ... }
    public int hashCode() { ... }
    public String toString() { ... }
}
```

→ Kotlin은 컴파일러가 boilerplate를 자동 생성. JVM 위에서는 일반 Java 클래스와 동일.

**Coroutine은 어떻게 가능한가**:
```kotlin
suspend fun fetchUser(id: Long): User { ... }
```
컴파일 후: state machine으로 변환. 매 `suspend` 지점에서 continuation 저장 + 외부에서 재개. → CPS (Continuation Passing Style) 변환. JVM 위에서 동작 가능.

### 5단. 역사

| 연도 | 사건 | 트리거 |
|---|---|---|
| 2010 | JetBrains 사내 결정 | "IntelliJ를 Java로 만드는 게 너무 고통" |
| 2011 | Kotlin 첫 발표 | Scala vs Kotlin 결정 — Scala는 컴파일 느림 |
| 2016 | Kotlin 1.0 GA | OOP + FP 균형 |
| 2017 | Google Android 공식 지원 | Android의 Java 7/8 한계 해결 |
| 2018 | Kotlin 1.3 + Coroutine 1.0 | 비동기 프로그래밍 |
| 2019 | Spring 5 + Coroutine 통합 | 서버 사이드 Kotlin 표준화 |
| 2022 | Kotlin 1.7 K2 컴파일러 | 성능 대폭 개선 |
| 2024 | Kotlin 2.0 | K2 default + Multiplatform 성숙 |

### 6단. 트레이드오프 — Java 21 vs Kotlin 1.9

| 축 | Java 21 | Kotlin 1.9 |
|---|---|---|
| **Null Safety** | Optional (런타임) | 타입 시스템 (컴파일 타임) |
| **불변 데이터** | record (Java 16+) | data class (2016~) |
| **Sealed Type** | sealed (Java 17+) | sealed class/interface (2016~) |
| **Pattern Matching** | record/type pattern (21+) | when + destructuring (2016~) |
| **확장** | (불가) | 확장 함수/프로퍼티 |
| **위임** | (보일러플레이트) | `by` 키워드 |
| **동시성** | Virtual Thread (21+) | Coroutine (2018~) |
| **함수형** | Stream + Optional | first-class function + Arrow |
| **DSL** | (제한) | DSL 친화적 (Gradle, Compose) |
| **컴파일 속도** | 빠름 | 느림 (K2 개선 중) |
| **런타임 성능** | 동일 (JVM) | 동일 (JVM) |
| **호환성** | 거의 완벽 | Java와 양방향 |
| **학습 곡선** | 낮음 | 중간 (FP 도구 많음) |
| **산업 채택** | 압도적 | 모바일 + 백엔드 일부 |

→ **결론**: Kotlin이 거의 모든 기능에서 6년 선행. Java는 호환성 + 산업 표준성으로 승부.

### 7단. 운영 진단 — Kotlin 운영 함정

- **Spring + Kotlin 함정**:
  - 모든 클래스 final → Spring AOP 프록시 불가
  - 해결: `kotlin-spring` 플러그인이 `@Component` 자동 open
  - 또는 `allopen` 플러그인
- **JPA + Kotlin 함정**:
  - 기본 생성자 없음 (모든 필드 val) → JPA reflection 실패
  - 해결: `kotlin-jpa` 플러그인 (no-arg constructor 자동 생성)
- **Coroutine + JDBC 함정**:
  - JDBC는 blocking → coroutine의 비동기 효과 무력화
  - 해결: R2DBC 또는 `withContext(Dispatchers.IO)`
- **Kotlin null 우회 안티패턴**:
  - `!!` 남용 → KotlinNullPointerException
  - `as?` 없이 강제 캐스팅 → ClassCastException
  - → `?.let`, Elvis 연산자(`?:`), `requireNotNull` 사용

## 꼬리질문

### Junior
1. **Q**: Kotlin이 Java보다 좋은 점은?
   → Null safety + 불변 우선 + 간결한 문법 + 함수형 친화. 모두 JVM 위에서 동일 성능.

### Senior
2. **Q**: Kotlin coroutine은 어떻게 동기 코드처럼 보이지만 비동기인가요?
   → 컴파일러가 `suspend` 함수를 **continuation passing style (CPS)** 로 변환. 매 suspend 지점에서 state machine으로 변환 + Continuation 인터페이스로 결과 콜백. 호출자에게는 동기처럼 보임. → 사실 Java의 virtual thread도 비슷한 원리(Continuation), 차이는 "**컴파일 타임 CPS (Kotlin)**" vs "**런타임 Continuation (Java Loom)**".
3. **꼬리**: 그럼 Kotlin coroutine과 Java virtual thread 중 무엇이 더 나은가요?
   → 트레이드오프:
   - **Coroutine**: 명시적 `suspend` 마킹 → 함수 시그니처에 비동기성 드러남. blocking 코드 호출 시 명시적 dispatcher 필요. 컴파일러 변환 비용.
   - **Virtual Thread**: 기존 Java 코드 그대로 (synchronized만 주의). 명시 없음 → 어디서 비동기인지 안 보임. JVM이 알아서.
   - 함수형 사고는 coroutine, OOP 사고는 virtual thread가 자연.

### Principal
4. **Q**: Kotlin이 JVM 외 플랫폼(Native, JS, WASM)도 지원하는데, 이게 OOP/FP 패러다임에 어떤 영향이 있나요?
   → **공통 코드를 작성하려면 플랫폼 의존성을 최소화** → 함수형 코어가 자연. JPA 등 JVM 전용은 공통 모듈에 못 들어감. → Kotlin Multiplatform 프로젝트에서는 "도메인 = 함수형 코어, 플랫폼 = 어댑터" 패턴이 강제됨.
5. **꼬리**: 그렇다면 Kotlin이 Java보다 함수형으로 더 기우는 방향으로 진화한다고 볼 수 있나요?
   → 그렇다. Kotlin 2.0+의 방향: Context Receiver, Value Class (inline class), Result type 등 모두 함수형 친화. Arrow 라이브러리도 1급 모나드 도입. → JetBrains는 "OOP/FP 둘 다 자연스럽게, but 함수형 표현력이 우세"를 지향.
6. **꼬리의 꼬리**: 그럼 Spring 같은 OOP 프레임워크와 Kotlin의 미래는?
   → Spring 6는 Kotlin first-class 지원 (Coroutine, DSL config 등). 다만 Spring 자체가 OOP 모델이라 충돌 영역 존재 (e.g., `@Service` 빈 vs 함수). → Ktor (JetBrains 자체 서버 프레임워크)가 함수형 친화. Kotlin 백엔드의 양대 산맥: Spring (OOP) vs Ktor (FP).

## 다음 챕터로

- [12-spring-and-framework](../12-spring-and-framework/) — OOP를 운영 가능하게
