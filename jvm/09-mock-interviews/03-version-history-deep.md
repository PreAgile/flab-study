# 09-03. Java Version History — 시니어 깊이 답변 8문항

> JDK는 LTS(8/11/17/21) 중심으로 진화하며, 각 LTS마다 **언어/JVM/GC**가 함께 변한다.
> 시니어 면접의 핵심은 "어느 버전에서 무엇이 변했나"가 아니라 **"그 변화가 우리 운영 시스템에 어떻게 박히는가"**.
> 8개 질문은 다음 흐름으로 답한다: **언어/JVM 변천 → JPMS → 운영 영향 → Deprecation 리스크 → LTS 선택 → 마이그레이션 함정 → Loom**.

---

## 사용 가이드

각 질문은 다음 4단 구조로 답한다.

```
[1] 한 줄 정의       — 면접관 첫 응답 (5초 안)
[2] 본론 상세        — 시간순/축별 정리 (코드·도식 포함)
[3] 운영 영향 매핑   — production에서 어떤 문제로 드러나나
[4] 한 줄 정리       — 면접관 머리에 남기는 마지막 문장
```

레벨 표기:
- 🟢 Junior — 정의·개념
- 🟡 Senior — 구조·운영
- 🔴 Principal — 시스템 결정·트레이드오프

---

## Q1. 🟡 Java 8 → 21 LTS 각 버전의 주요 변화와 실무 시스템 설계에 미치는 영향

### [1] 한 줄 정의

> **JDK는 8(Lambda+Metaspace), 9-11(JPMS+G1 default), 17(ZGC production+sealed), 21(Virtual Thread+GenZGC) 네 변곡점으로 압축된다. 각 변곡점이 시스템 설계에서 바꾸는 축이 다르다 — 8은 코드 스타일, 11은 모듈 경계, 17은 GC/캡슐화, 21은 동시성 모델.**

### [2] 본론 상세 — 4개 LTS 변곡점

```
JDK 8 ━━━━━━━━ 9~11 ━━━━━━━━ 17 ━━━━━━━━ 21
2014           2018          2021         2023

언어 │ Lambda    var           sealed        Pattern Switch
    │ Stream    HTTP Client   Records       Record Patterns
    │ Optional  switch expr   instanceof    Sequenced Coll.
    │           (preview)     pattern
─────┼──────────────────────────────────────────────────
JVM  │ Tiered    JPMS         Strong        Virtual Thread
     │ default   AppCDS       encap.        FFM API
     │ Metaspace JLink        macOS/AArch64 Scoped Values
─────┼──────────────────────────────────────────────────
GC   │ G1 사용  G1 default    ZGC prod      Generational
     │ 가능     CMS deprecate sub-ms STW    ZGC
     │ Parallel CMS removed
     │ default  (JDK14)
```

#### JDK 8 — 함수형 도입과 Heap-internal PermGen 폐지

- **언어**: Lambda + Stream + Optional + default method. 컬렉션 처리 패러다임 전환.
- **JVM**: PermGen → Metaspace (class metadata를 native memory로). Tiered Compilation 기본 on.
- **GC**: G1 사용 가능하지만 default는 Parallel.
- **설계 영향**: Service/Repository 인터페이스에 default method 추가 가능 → 인터페이스 진화 비용 ↓. Stream으로 컬렉션 처리 코드 단축. PermGen OOM 사라짐 — 동적 클래스 생성(Spring AOP/Groovy)에 안전.

#### JDK 11 — 모듈 시스템 정착, G1 default, JEE 분리

- **언어**: `var` (JDK 10에서), HTTP Client 표준화, String API 강화.
- **JVM**: JPMS 안정(9 도입), AppCDS 무료화, `jlink`로 최소 runtime 패키징.
- **GC**: **G1 default**, ZGC experimental, Epsilon(no-op GC).
- **JEE 모듈 제거**: `javax.xml.bind`, `javax.annotation`, `javax.activation`, CORBA, JTA 등이 JDK에서 분리됨 → 별도 dependency 필요.
- **설계 영향**: 라이브러리 경계가 module-info로 명시 가능. Default GC 변경으로 GC 옵션 일제 재검토 필요. 컨테이너 메모리 인식(`UseContainerSupport`) 기본 on → `-Xmx` 자동 산정 작동.

#### JDK 17 — ZGC production, Strong Encapsulation, Records/Sealed

- **언어**: Records (불변 DTO), Sealed Classes (닫힌 상속), Pattern matching for instanceof, Text blocks.
- **JVM**: **Strong encapsulation**(JEP 403) — `sun.misc.*` 등 internal API 봉인. `--add-opens`/`--add-exports` 명시 없으면 reflection 실패. Apple Silicon 정식 지원.
- **GC**: **ZGC production-ready** (JDK 15부터), sub-ms STW. Shenandoah도 안정.
- **설계 영향**: Records로 DTO/Value Object 보일러플레이트 제거 → DDD 친화. Sealed로 ADT(Algebraic Data Type) 표현 가능 → Visitor 패턴 거의 불필요. Spring Boot 3 require → 마이그레이션 압력. ZGC로 8GB+ Heap latency-critical 서비스가 GC 걱정 없이 운영 가능.

#### JDK 21 — Virtual Thread, Generational ZGC, Pattern Switch

- **언어**: Pattern matching for switch, Record Patterns, Sequenced Collections.
- **JVM**: **Virtual Threads** (JEP 444) — Loom 프로젝트의 결실. 수십만 동시 thread. **Generational ZGC** — sub-ms pause + G1 동등 throughput. FFM API (JNI 대체).
- **설계 영향**: thread-per-request 부활 — Reactive(WebFlux)의 복잡한 콜백/Mono/Flux 없이도 수십만 동시 요청 처리 가능. 새로 시작하는 프로젝트의 default 선택지가 Spring MVC + Virtual Thread.

### [3] 운영 영향 매핑

| 버전 | production에서 가장 자주 보이는 문제 |
|---|---|
| 8 | PermGen 사라졌지만 Metaspace 무한 증가 (CL 누수). 옛 JEE jar들이 9+에서 깨질 거라는 잠재 부채. |
| 11 | `--illegal-access=warn` → deny 전환에 따른 reflection 깨짐. JEE 모듈 분리로 인한 `ClassNotFoundException`. |
| 17 | `--add-opens` 미설정으로 Spring/Hibernate/Mockito reflection 실패. ARM(Apple Silicon) native 빌드. |
| 21 | Virtual Thread + synchronized 조합에서 carrier thread pinning → 처리량 저하. ConnectionPool 사이즈 재설계 필요. |

### [4] 한 줄 정리

> **8은 코드 스타일, 11은 모듈 경계와 default GC, 17은 강한 캡슐화와 ZGC, 21은 동시성 모델 — 시니어는 "이 시스템은 어느 변곡점에 발이 묶여 있나"부터 진단한다.**

---

## Q2. 🟡 Java 8 함수형 도입이 GoF 패턴(Strategy, Iterator, Visitor 등)에 미친 영향

### [1] 한 줄 정의

> **Lambda + 함수형 인터페이스가 도입되면서 "동작을 객체로 감싸는" GoF 패턴들(Strategy, Command, Observer, Template Method, Iterator, Visitor)이 일급 함수로 압축됐다. 패턴의 의도는 살아있지만 구현 보일러플레이트는 사라졌고, 더 중요한 건 합성(composition) 가능성이 폭발적으로 늘었다는 점.**

### [2] 본론 상세 — 패턴별 변화

#### Strategy 패턴 — Lambda로 완전 압축

```java
// JDK 7 이전
public interface DiscountStrategy {
    BigDecimal apply(BigDecimal price);
}
public class TenPercentDiscount implements DiscountStrategy {
    public BigDecimal apply(BigDecimal price) { return price.multiply(BigDecimal.valueOf(0.9)); }
}
order.setDiscountStrategy(new TenPercentDiscount());

// JDK 8+
order.setDiscountStrategy(price -> price.multiply(BigDecimal.valueOf(0.9)));
```

- 핵심 변화: 클래스 정의 → 표현식 한 줄. **Function<T, R>**, **Predicate<T>**, **Consumer<T>** 같은 표준 함수형 인터페이스가 도메인별 인터페이스를 대체.
- 더 중요한 효과: `discount1.andThen(discount2)` 같은 **함수 합성**이 가능해짐 — 전략 자체를 조합.

#### Command 패턴 — Runnable/Supplier로 대체

```java
// JDK 7
public interface Command { void execute(); }
queue.add(new SaveCommand(order));

// JDK 8+
queue.add(() -> repository.save(order));
```

- `Runnable`, `Callable`, `Supplier`가 사실상 Command. `ExecutorService.submit(() -> ...)` 패턴이 대표적.

#### Observer 패턴 — EventBus + Consumer로

```java
// JDK 7
listener.addOrderListener(new OrderListener() {
    public void onCreated(Order o) { ... }
});

// JDK 8+
eventBus.on(OrderCreatedEvent.class, event -> notificationService.send(event));
```

- Spring `ApplicationEventPublisher`도 `@EventListener` + 메서드 참조로 단순화.

#### Template Method — 일부는 Lambda로, 핵심은 살아있음

```java
// 옛날
abstract class AbstractDao { 
    void execute() { begin(); doWork(); commit(); }
    abstract void doWork();
}

// JDK 8+ — Lambda 주입
class TxTemplate {
    void execute(Runnable work) { begin(); work.run(); commit(); }
}
txTemplate.execute(() -> repository.save(order));
```

- Spring `JdbcTemplate.query(sql, rowMapper)`, `TransactionTemplate.execute(...)` — 이미 함수형 스타일.
- 다만 "여러 hook이 있고 hook 사이에 상속 관계가 있는" 본격 Template Method는 여전히 상속이 자연스러움.

#### Iterator 패턴 — Stream에 완전히 흡수

```java
// 외부 iteration
for (Order o : orders) {
    if (o.isPaid()) total = total.add(o.amount);
}

// 내부 iteration + 합성
BigDecimal total = orders.stream()
    .filter(Order::isPaid)
    .map(Order::amount)
    .reduce(BigDecimal.ZERO, BigDecimal::add);
```

- Iterator 패턴은 사실상 Stream/Collector로 흡수. 외부 iteration → 내부 iteration.
- 부가 효과: `parallelStream()`으로 병렬화 진입 비용 한 줄.

#### Visitor 패턴 — sealed + Pattern Switch (JDK 17/21)로 완전 대체

```java
// JDK 7 Visitor
interface Shape { <R> R accept(Visitor<R> v); }
interface Visitor<R> { R visit(Circle c); R visit(Square s); }

// JDK 21
sealed interface Shape permits Circle, Square {}
record Circle(double r) implements Shape {}
record Square(double side) implements Shape {}

double area(Shape s) {
    return switch (s) {
        case Circle c -> Math.PI * c.r() * c.r();
        case Square sq -> sq.side() * sq.side();
    };
}
```

- Visitor의 의도(타입별 동작 + 새 동작 추가)가 `sealed` + Pattern Switch로 더 간결하게 표현됨.
- 컴파일러가 exhaustiveness 검사 → 새 sub-type 추가 시 모든 switch 강제로 검토.

#### Optional — Null Object 패턴의 표준화

- `Optional<T>`이 도입되면서 "값이 없을 수 있다"는 의도를 타입에 박았다.
- `map`/`flatMap`/`orElse`로 NPE 방어 코드가 declarative하게 변함.
- 단, 필드/파라미터에 `Optional` 쓰는 건 안티패턴 — 반환 타입에만 사용.

### [3] 운영 영향 매핑

- **코드 베이스 가독성**: 함수형으로 코드 라인 수 절반. 도메인 로직이 잘 드러남.
- **JIT 최적화와의 관계**: Lambda는 `invokedynamic` + LambdaMetafactory로 구현 → 캐시되고 인라인 친화적. 단, `Stream` 파이프라인이 깊으면 JIT 인라인 한계(`MaxInlineLevel=9`)를 넘을 수 있어 hot path에선 단순 for-loop가 빠를 수 있음.
- **디버깅**: Stack trace에 `Lambda$1234/0x...` 형태로 찍혀 가독성 ↓. 메서드 참조(`Order::isPaid`) 쓰면 stack에 정확한 이름 남아 디버깅 유리.
- **테스트**: Lambda를 인자로 받는 코드는 mocking이 단순 — 표준 함수형 인터페이스라 mock 라이브러리도 자연스럽게 처리.
- **함정**: `Stream`을 hot loop에서 매번 만들면 short-lived 객체 폭증 → allocation rate ↑ → Minor GC 빈도 ↑. EA가 잡으면 0이 되지만, 복잡한 파이프라인은 EA 실패 가능.

### [4] 한 줄 정리

> **"동작을 객체로 감싸는" 패턴 대다수가 Lambda로 한 줄이 됐고, Visitor는 sealed+Pattern Switch로 더 안전하게 표현된다. 패턴의 의도는 살아있지만 보일러플레이트는 죽었다 — 시니어는 의도(intent)와 구현(implementation)을 분리해서 읽어야 한다.**

---

## Q3. 🟡 Java 9 모듈 시스템(JPMS/Jigsaw)의 도입과 대규모 프로젝트 영향

### [1] 한 줄 정의

> **JPMS는 "어떤 패키지를 누구에게 노출하고, 누구로부터 무엇을 요구하는지"를 module-info.java에 명시하는 강한 캡슐화 메커니즘이다. classpath의 "모두에게 모든 게 보임" 문제를 해결하지만, 옛 라이브러리들이 reflection으로 internal API 찌르던 패턴을 일제히 깨뜨려 8→11 마이그레이션의 가장 큰 함정이 됐다.**

### [2] 본론 상세

#### 왜 모듈 시스템이 필요했나

```
[Classpath 시대 (JDK 1.0 ~ 8)]
모든 jar = "모든 public class가 전역 노출"
   ↓
1. internal API 접근 막을 수 없음 (sun.misc.Unsafe 남발)
2. 동일 패키지를 두 jar가 가지면 충돌 ("classpath hell")
3. JDK가 하나의 거대한 rt.jar — 일부만 떼서 못 씀

[Module 시대 (JDK 9+)]
모듈 = 패키지 묶음 + 명시적 경계
   ↓
1. exports로 노출 패키지 명시 (그 외는 internal)
2. requires로 의존 모듈 명시
3. JDK 자체가 ~75개 모듈로 쪼개짐 → jlink로 필요한 것만 추출
```

#### module-info.java 핵심 문법

```java
module com.example.order {
    requires com.example.common;            // 의존
    requires transitive java.sql;           // 이 모듈을 require하는 쪽도 java.sql 자동 require
    exports com.example.order.api;          // 이 패키지만 외부 공개
    exports com.example.order.internal to com.example.payment;  // 특정 모듈에만 공개
    opens com.example.order.entity;         // reflection 허용 (Hibernate/Jackson용)
    opens com.example.order.entity to com.fasterxml.jackson.databind;
    uses com.example.order.PaymentProvider; // ServiceLoader 소비자
    provides com.example.order.PaymentProvider 
        with com.example.order.impl.StripeProvider;  // ServiceLoader 제공자
}
```

#### 4가지 모듈 종류 — 면접 빈출

| 종류 | 정의 | 동작 |
|---|---|---|
| **Named module** | module-info.java가 있는 정식 모듈 | exports/requires 정확히 적용 |
| **Automatic module** | module-info 없는 jar를 modulepath에 둠 | jar 이름에서 자동 모듈명 추론, 모든 패키지 export, 모든 모듈 require — JPMS 마이그레이션 가교 |
| **Unnamed module** | classpath에 둔 jar | classpath의 모든 코드가 한 unnamed module로 묶임. named module이 unnamed를 require할 수 없음(중요) |
| **Platform module** | JDK 자체 모듈 (java.base, java.sql 등) | java.base만 자동 require |

#### classpath → modulepath 전환의 함정

```
JDK 8: java -cp lib/* MainApp
JDK 9+: java -p mods -m com.example.app/com.example.app.Main
        또는 여전히 -cp 사용 (unnamed module)
```

- 한꺼번에 다 옮기는 건 비현실적 → 보통 **혼합 모드**(자기 코드는 named module, 옛 라이브러리는 automatic module 또는 classpath)로 시작.
- 같은 패키지를 두 모듈이 export하면 **split package 에러** → 옛 라이브러리들이 이걸로 자주 깨짐.

#### Strong Encapsulation 단계적 강화

```
JDK 9   --illegal-access=permit  (default, 경고도 안 함)
JDK 10  --illegal-access=warn    (default)
JDK 16  --illegal-access=deny    (default)
JDK 17  옵션 자체 제거. --add-opens 명시 없으면 무조건 실패
```

- "옛 라이브러리가 reflection으로 java.lang internal 찌르던 코드"가 JDK 17에서 일제히 깨짐.
- Spring Framework 5.3 미만, Hibernate 5.2 미만 등이 17에서 실행 안 됨 — 업그레이드 강제.

### [3] 운영 영향 매핑

#### 마이그레이션 사례 — 100만 LOC 모놀리스

1. **현황 진단**:
   ```bash
   jdeps --jdk-internals --multi-release 17 app.jar
   # 어떤 클래스가 internal API 쓰는지 출력
   ```
2. **단계적 전환**:
   - Phase 1: 모든 jar를 classpath에 둔 채 JDK 17로만 빌드/실행 (`--add-opens` 다발)
   - Phase 2: 자기 코드만 module-info 추가, 외부 라이브러리는 automatic module
   - Phase 3: 외부 라이브러리도 named module로 점진 전환 (보통 미완)
3. **`jlink` 활용**:
   - 필요한 JDK 모듈만 추출해 **30MB 미만 runtime** 생성 가능 → 컨테이너 이미지 크기 절감.
   - 단, automatic module은 `jlink` 불가 → 라이브러리 모두 named가 돼야 함.

#### 마이그레이션 시 자주 깨지는 패턴

| 패턴 | 증상 | 해결 |
|---|---|---|
| reflection 으로 `Field.setAccessible(true)` | `InaccessibleObjectException` | `--add-opens java.base/java.lang=ALL-UNNAMED` |
| `sun.misc.Unsafe` 직접 사용 | `ClassNotFoundException` (일부) / 경고 (`jdk.unsupported`로 이전) | `VarHandle`로 대체 |
| `javax.xml.bind` (JAXB) | `ClassNotFoundException` | `jakarta.xml.bind-api` + 구현체 추가 |
| `com.sun.*` API | 동작 안 함 | 공식 API로 이전 |
| split package | `ResolutionException` | 같은 패키지를 둘 다 갖는 라이브러리 중 하나 제거 |

#### 대규모 모놀리스에 JPMS 도입 — 실제로 잘 안 됨

- 현실에선 자기 코드를 module화한 회사는 드뭄. 이유:
  1. **빌드 도구 복잡도** — Maven/Gradle plugin 설정 복잡.
  2. **테스트 프레임워크 충돌** — JUnit/Mockito가 reflection으로 private 접근 → `opens` 폭증.
  3. **이득이 모호** — 자기 코드 안에선 package-private 이미 있고, 라이브러리 경계엔 어차피 별도 빌드 단위.
- 잘 활용된 곳: **JDK 자체**(java.base/java.sql 등), **JavaFX**, **Spring Boot Native**의 일부 영역, `jlink`로 작은 runtime 만드는 CLI.

### [4] 한 줄 정리

> **JPMS는 "강한 캡슐화"라는 이상이고 jlink/JDK 분할로 실현됐지만, 응용 모놀리스에선 ROI가 낮아 적극 채택은 드물다. 시니어가 알아야 할 건 "내 코드를 module화하는 법"이 아니라 "외부 라이브러리가 internal API에 손대서 깨질 때 진단·우회하는 법"이다.**

---

## Q4. 🟡 Java 11/17/21 GC·스레드·언어 기능이 대규모 서비스 운영에 미치는 영향

### [1] 한 줄 정의

> **11은 G1 default와 컨테이너 인식, 17은 ZGC production과 Records/Sealed로 데이터 모델 단순화, 21은 Virtual Thread와 Generational ZGC로 동시성 모델과 latency를 동시에 혁신했다. 시니어는 "11/17/21을 차례로 채택했을 때 코드/인프라/SLO가 어떻게 변하는가"를 줄줄이 말할 수 있어야 한다.**

### [2] 본론 상세

#### GC 진화 축

```
JDK 8        JDK 11        JDK 15-17     JDK 21
─────        ─────         ──────        ─────
Parallel     G1 default    ZGC           Generational
default      CMS deprecate production    ZGC
              (JDK 9)      sub-ms STW    (sub-ms +
              CMS removed                 throughput)
              (JDK 14)
```

- **JDK 11 G1 default**: pause 예측 가능 (`-XX:MaxGCPauseMillis`). 일반 웹 서비스의 P99가 즉시 좋아짐. 단, 8GB 미만에선 Parallel이 throughput 더 높을 수 있음.
- **JDK 17 ZGC production**: heap 32GB~수 TB에서도 STW < 10ms (15부터), < 1ms (17부터). 트레이딩/광고입찰처럼 tail latency가 매출인 시스템의 GC 고민을 사실상 종결.
- **JDK 21 Generational ZGC**: ZGC가 G1 대비 throughput 10-15% 낮던 격차를 거의 없앰. 단일세대 ZGC 대비 CPU 사용량도 줄음 (young 영역만 자주 회수). 새 프로젝트의 사실상 default 후보.

#### Threading 모델 — Virtual Thread의 본질

```
[Platform Thread (옛 Java)]
1 Java thread = 1 OS thread (1:1)
   ↓
스레드당 ~1MB stack → 수천 스레드 = 수 GB
context switch 비용 큼
Tomcat 200 스레드 한계 → 동시 요청 200 한계

[Virtual Thread (JDK 21)]
M Java thread : N OS thread (carrier 풀)
   ↓
스레드당 ~수 KB (heap에 stack)
blocking I/O 시 carrier에서 unmount → 다른 VT 실행
수십만 동시 thread 가능
thread-per-request가 다시 살아남
```

#### JDK 17 Records/Sealed — 데이터 모델 영향

```java
// 옛날 DTO
public class OrderDto {
    private final String id;
    private final BigDecimal amount;
    public OrderDto(String id, BigDecimal amount) {...}
    public String getId() {...}
    public BigDecimal getAmount() {...}
    @Override public boolean equals(Object o) {...}
    @Override public int hashCode() {...}
    @Override public String toString() {...}
}

// JDK 17 Record
public record OrderDto(String id, BigDecimal amount) {}
```

- **운영 효과**:
  - DTO 코드량 80% 감소 → 도메인 모델이 명확히 보임.
  - `equals/hashCode` 자동 생성 → `HashMap` key로 안전.
  - **불변성 보장** → 동시성 안전 (Virtual Thread와 자연스러운 짝).
  - **Pattern matching 친화** — `case OrderDto(var id, var amount) ->` 형태 destructuring.

#### JDK 17 Sealed Classes — ADT 표현

```java
sealed interface PaymentResult permits Success, Pending, Failed {}
record Success(String txId) implements PaymentResult {}
record Pending(Instant retryAt) implements PaymentResult {}
record Failed(String reason) implements PaymentResult {}

// 사용처에서 exhaustiveness 강제됨
String describe(PaymentResult r) {
    return switch (r) {
        case Success s -> "OK: " + s.txId();
        case Pending p -> "Retry at " + p.retryAt();
        case Failed f -> "Failed: " + f.reason();
        // 새로운 상태 추가 시 컴파일 에러 → 모든 switch를 고치게 강제
    };
}
```

- 새로운 `PaymentResult` sub-type 추가 시 **컴파일러가 모든 switch를 강제로 갱신**시킴 → null/missing case 버그 제거.
- DDD에서 "상태가 유한한 enum-like type"을 깔끔하게 표현 (Success/Pending/Failed 같은 비즈니스 결과).

### [3] 운영 영향 매핑

| 변화 | production에서 직접 보이는 효과 |
|---|---|
| **G1 default (11)** | P99 GC pause가 Parallel 대비 1/3 (대형 heap). MaxGCPauseMillis로 예측 가능. |
| **ZGC production (17)** | 64GB+ heap에서도 P99 STW < 1ms. 캐시 서버, real-time bidding 시스템 운영 가능. |
| **Generational ZGC (21)** | ZGC 같은 latency + G1 같은 throughput. CPU 사용량도 single-gen ZGC 대비 ~25% ↓. |
| **Virtual Thread (21)** | thread pool 한계 사라짐. Tomcat 200 → 100,000 동시 요청. Connection pool과 downstream 한계가 새 병목. |
| **Records (16)** | DTO/Value Object 표준 — Jackson/Hibernate가 record 지원하면서 도메인 모델 라인 수 절반. |
| **Sealed (17)** | 결제/주문 상태 같은 도메인 ADT 표현 — switch 누락 버그 제거. |
| **Pattern Switch (21)** | 옛 instanceof + cast의 boilerplate 사라짐. Visitor 패턴 거의 불필요. |

#### 실제 회사 사례 패턴

- **광고 입찰 (real-time bidding)**: JDK 11 G1으로 P99 100ms → JDK 17 ZGC로 P99 < 5ms. 입찰 손실율 절반.
- **Spring Boot 웹 서비스**: JDK 17로 가면서 Spring Boot 3로 강제 업그레이드 → Jakarta EE namespace 전환 같이 발생.
- **Kafka Consumer**: JDK 21 Virtual Thread로 수만 파티션을 thread-per-partition으로 처리 — 옛날엔 reactive로만 가능했던 패턴.

### [4] 한 줄 정리

> **11은 안정성, 17은 latency와 데이터 모델, 21은 동시성 — 세 LTS가 각자 다른 SLO 축을 끌어올렸다. 시니어는 우리 서비스의 병목이 무엇이냐(throughput? P99? 동시 요청 수?)에 따라 어느 LTS로 점프할지 판단한다.**

---

## Q5. 🟡 각 버전별 Deprecated/Removed Feature가 실무에 미치는 리스크

### [1] 한 줄 정의

> **Deprecation은 "지금은 동작하지만 곧 깨진다"는 시한폭탄이다. JDK 9 이후 deprecation은 `forRemoval=true`로 명시되며 보통 3-5개 LTS 안에 제거된다. 시니어는 deprecation 경고를 단순 cleanup이 아니라 **마이그레이션 데드라인**으로 읽는다.**

### [2] 본론 상세 — 주요 Deprecation 타임라인

```
JDK 9          11          14         17          21
──────         ─────       ─────      ─────       ─────
Applet         JEE         CMS        Security    Thread.stop
deprecated     modules     removed    Manager     stop(Throwable)
               removed                deprecated  removed
sun.misc       Nashorn               Applet      Finalize
Unsafe         deprecated            removed     terminally
일부 strict                                       deprecated
encap

CMS            javax.*     ParNew     RMI
deprecated     removed     removed    Activation
                                      removed
```

#### 1. JEE 모듈 제거 (JDK 11)

- 제거된 패키지: `javax.xml.bind` (JAXB), `javax.annotation` (Common Annotations), `javax.activation`, `javax.transaction`, `javax.xml.ws` (JAX-WS), CORBA.
- **리스크**: Spring/Hibernate 옛 버전은 이들에 의존 → JDK 11에서 `ClassNotFoundException`.
- **해결**: 별도 dependency 추가 (`jakarta.xml.bind-api` + glassfish jaxb impl). Jakarta namespace로 이름까지 바뀜 — `javax.xml.bind` → `jakarta.xml.bind` (Jakarta EE 9+).
- **운영 함정**: 옛 코드에서 `import javax.xml.bind.*` 그대로 두고 JDK 11에 던지면 빌드는 통과(별도 jar로 들어오니), 런타임에 깨질 수 있음 — 의도치 않게 두 버전이 충돌.

#### 2. sun.misc.Unsafe — JDK 9 deprecate, 점진 제거

- **현황**: 여전히 `jdk.unsupported` 모듈에 남아있지만 strong encapsulation으로 보호됨. `--add-opens` 없이는 reflection으로 접근 불가.
- **대체**:
  - `Unsafe.allocateMemory` → `MemorySegment` (FFM API, JDK 21+)
  - `Unsafe.compareAndSwap*` → `VarHandle` (JDK 9+)
  - `Unsafe.park`/`unpark` → `LockSupport`
- **리스크**: Netty, Cassandra, Hadoop 등 고성능 라이브러리가 internal에 Unsafe 사용. 라이브러리 버전 안 올리면 어느 JDK에선가 깨짐.
- **JEP 471 (JDK 23+)**: memory-access 메서드 deprecate, JDK 26+에서 제거 예고. **2026 시점에 가장 active한 deprecation**.

#### 3. SecurityManager (JDK 17 deprecate, JEP 411)

- **현황**: JDK 17에서 `forRemoval=true`로 deprecate. 향후 LTS에서 제거 예정.
- **리스크**: Applet, Tomcat의 보안 격리, 일부 multi-tenant Java 시스템이 SecurityManager에 의존.
- **대체**: OS-level isolation (Container/Sandbox), 별도 process 격리.
- **운영 함정**: SecurityManager 켜진 환경에서 돌던 옛 서비스는 JDK 마이그레이션 시 보안 모델 자체 재설계 필요.

#### 4. finalize() — JDK 9 deprecate, JDK 18 terminally deprecate

- **이유**: finalizer는 비결정적, GC 부담, security hole.
- **대체**: `try-with-resources` + `AutoCloseable`, `java.lang.ref.Cleaner`.
- **리스크**: 옛 코드에서 `Object#finalize()` override한 클래스가 JDK 26+ 어디선가 동작 안 함.
- **운영 신호**: `java.lang.ref.Finalizer$FinalizerThread`가 stack에 보이면 잠재 부채.

#### 5. CMS GC — JDK 9 deprecate, JDK 14 제거

- **리스크**: 옛 서비스가 `-XX:+UseConcMarkSweepGC` 옵션으로 기동 → JDK 14+에서 옵션 자체 무시 + 경고, default GC(G1)로 돌게 됨.
- **함정**: 운영팀이 "CMS인 줄 알고 튜닝"하지만 실제로는 G1 — pause profile이 완전히 다르므로 잘못된 진단.
- **해결**: JDK 업그레이드 전 GC 옵션 일괄 grep해 deprecated 옵션 정리.

#### 6. Thread.stop, Thread.suspend, Thread.resume — JDK 21 제거

- **현황**: 오래 deprecate 상태였다가 JDK 21에서 `stop()`이 실제로 동작 안 함 (UnsupportedOperationException).
- **대체**: Interrupt + volatile flag.
- **리스크**: 옛 batch/agent 시스템이 thread를 강제 종료하던 패턴 → 동작 안 함.

#### 7. RMI Activation, Nashorn JS Engine, Applet — JDK 17 제거

- **리스크**: 옛 enterprise에서 RMI 기반 분산 시스템 → 더 이상 마이그레이션 불가.
- **대체**: gRPC, REST, Kafka 등.

### [3] 운영 영향 매핑

#### Deprecation 모니터링 체크리스트 (CI/CD)

```bash
# 1. 빌드 시 deprecation 경고 → 에러로
javac -Werror -Xlint:deprecation,removal ...

# 2. JEP 277 forRemoval=true만 골라내기
javac -Xlint:removal ...

# 3. JDK internal API 사용 스캔
jdeps --jdk-internals --multi-release 21 app.jar

# 4. 의존 라이브러리의 deprecated 사용 (간접 의존성도)
jdeps -recursive --jdk-internals app.jar
```

#### 시한폭탄 우선순위

| 우선순위 | 이슈 | 데드라인 |
|---|---|---|
| 🔴 즉시 | JEE 모듈 직접 사용 | 이미 11에서 제거 |
| 🔴 즉시 | finalize() override | 18에서 terminally deprecated |
| 🟡 1-2년 | Unsafe 직접 사용 | 23부터 memory API deprecate, 26+ 제거 |
| 🟡 1-2년 | SecurityManager 의존 | 다음 LTS에서 제거 가능성 |
| 🟢 장기 | sun.misc.* reflection | strong encap.로 사실상 깨짐, --add-opens로 연명 가능 |

#### 실제 사고 사례 패턴

- **Hadoop/Spark 클러스터**: 옛 버전이 sun.misc.Unsafe로 native memory 다룸 → JDK 11+ 마이그레이션 보류 → 보안 패치 못 받는 상태 누적.
- **Spring 4 → Spring 6**: javax → jakarta 네임스페이스 전환 + Reflection 의존 → JDK 17 강제 업그레이드와 같이 발생.

### [4] 한 줄 정리

> **Deprecation은 cleanup이 아니라 마이그레이션 데드라인이다. 시니어는 빌드 로그의 deprecation 경고를 Jira 티켓으로 끊어 LTS 한 cycle 안에 제거 — 이 습관이 없으면 어느 날 LTS 점프에서 시스템 전체가 멈춘다.**

---

## Q6. 🔴 LTS 선택 전략과 OpenJDK 배포판 비교

### [1] 한 줄 정의

> **LTS 선택은 "기능"이 아니라 **EoL 일정 × 배포판 지원 × 보안 패치 주기 × 라이브러리 호환성**의 4축 의사결정이다. 시니어는 회사 규모/규제/지원계약을 보고 Temurin(default), Corretto(AWS), Liberica(GraalVM 통합), Oracle(상용 지원) 중 선택한다.**

### [2] 본론 상세

#### LTS 일정 (2026년 5월 기준)

```
JDK 8   ──────────────────────────────────╮ 2030 (Oracle Premier)
                                          │ 일부 vendor 2032까지
JDK 11  ──────────────────────────────────╮ 2032 (Temurin)
                                          │ Oracle Extended 2026
JDK 17  ──────────────────────────────────╮ 2029 (Oracle Premier)
                                          │ Temurin 2027
JDK 21  ──────────────────────────────────╮ 2031 (Oracle Premier)
                                          │ 신규 default
JDK 25  ──────────── (2025-09 release) ───╮ 2033+ 예상 (LTS)
```

- 핵심: **EoL은 배포판마다 다르다**. Oracle JDK Premier Support는 LTS 출시 후 5년 + Extended 3년. Temurin/Corretto는 보통 4년+.

#### 주요 OpenJDK 배포판 비교

| 배포판 | 회사 | 특징 | 추천 상황 |
|---|---|---|---|
| **Oracle JDK** | Oracle | 상용 라이선스(NFTC) — 비프로덕션 무료, 프로덕션은 유료(직원 수 기준) | 상용 지원 필요한 대기업 |
| **Eclipse Temurin** | Eclipse Adoptium | 옛 AdoptOpenJDK. TCK 통과한 OpenJDK 빌드. Apache 2.0. | **default 선택** (대부분의 회사) |
| **Amazon Corretto** | AWS | AWS가 자체 패치 적용 + 무료 LTS 지원. AL2/AL2023과 통합. | AWS 환경 |
| **Azul Zulu** | Azul | Community(무료) + Prime(유료, ZGC 변종 ZING). Azul Platform Prime은 C4 GC 등 자체 기술 | Azul 상용 계약 회사 |
| **BellSoft Liberica** | BellSoft | Spring 공식 추천. NIK(Native Image Kit)로 GraalVM 통합 | Spring Boot Native 사용 |
| **Microsoft Build** | Microsoft | Azure 환경 최적화. JDK 11/17만 | Azure 환경 |
| **GraalVM CE/EE** | Oracle | Native Image 제공. EE는 유료(GFTC) | AOT 컴파일 필요 |
| **IBM Semeru** | IBM | OpenJ9 VM 사용 (HotSpot 아님). 메모리 footprint 작음 | IBM 클라우드, 메모리 제약 환경 |

#### 라이선스 함정 — 매우 중요

- **Oracle JDK 라이선스 변천**:
  - JDK 8 (2019 이전): 무료
  - JDK 8 (2019 이후) / JDK 11 ~ 16: Oracle Technology Network License — **프로덕션 유료**
  - JDK 17+: NFTC (No-Fee Terms and Conditions) — **다음 LTS 출시 + 1년까지 무료**
  - 즉 JDK 21은 JDK 25 출시 후 1년(~2026) 후부터 유료. **시간 함수다**.
- **실제 사고**: 회사가 Oracle JDK 8을 무료라 믿고 수천 서버 배포 → Oracle Audit → 수십억 라이선스비 청구. 2019~2023년 한국/일본 대기업 다수 사례.
- **안전한 선택**: **Temurin/Corretto**가 default — Apache 2.0/GPL+CE 라이선스로 사실상 무제한 무료.

#### EoL 후 운영 리스크

```
EoL 후 = CVE 패치 안 받음
   ↓
1. 보안 감사 통과 못 함 (PCI-DSS, ISO27001 등)
2. 새 CVE 발견 시 우회 패치 직접 만들거나 무방비
3. 상용 라이선스(Oracle Extended Support) 외에는 패치 없음
```

- **JDK 8 EoL 후 운영**: 2030 이후 Oracle Extended Support는 매우 비싸므로, **2030 전에 17/21로 마이그레이션** 필수.
- **JDK 11도 2026 이후 일부 vendor만 지원** — Temurin도 2027 종료.

### [3] 운영 영향 매핑

#### 선택 의사결정 트리

```
질문 1: 회사가 Oracle 상용 계약 보유?
├── Yes → Oracle JDK (Premier/Extended 활용)
└── No
     ↓
질문 2: AWS 환경?
├── Yes → Corretto (AWS Linux와 통합, 무료 보안 패치)
└── No
     ↓
질문 3: Spring Boot Native 사용?
├── Yes → Liberica NIK (Spring 공식)
└── No
     ↓
질문 4: 메모리 제약 (수백 MB 컨테이너)?
├── Yes → IBM Semeru (OpenJ9, RSS 작음)
└── No
     ↓
→ Eclipse Temurin (default, 가장 보편적)
```

#### LTS 점프 의사결정

| 현재 | 2026 시점 권장 | 이유 |
|---|---|---|
| JDK 8 | → **JDK 17 또는 21** | 2030 EoL 임박, 가능하면 한 번에 21로 |
| JDK 11 | → **JDK 21** | 11 vendor 지원 2027 종료, GenZGC + VT 이득 |
| JDK 17 | → **JDK 21 (선택)** | 즉시 점프 불필요. VT 필요하면 21 |
| JDK 21 | → **JDK 25** (2025-09 출시 후 안정화 시) | 25가 다음 LTS — 채택 시기는 라이브러리 준비도 보고 |

#### 라이브러리 호환성 체크 (마이그레이션 전 필수)

```bash
# 의존 라이브러리가 target JDK 지원하는지 일괄 점검
mvn versions:display-dependency-updates
gradle dependencyUpdates

# JDK internal API 사용 라이브러리 식별
jdeps --jdk-internals --multi-release 21 fat.jar
```

- **Spring Boot 3+** = JDK 17 require
- **Hibernate 6+** = JDK 17 require + Jakarta namespace
- **Lombok**: 매 JDK 출시마다 호환성 갱신 필요 — JDK 22+에서 1.18.32+ 강제 같은 패턴

### [4] 한 줄 정리

> **LTS 선택은 "최신 기능"이 아니라 "라이선스 × EoL × 배포판 지원"의 의사결정이다. 시니어는 Temurin/Corretto를 default로 두고, Oracle 상용 지원이 필요한 경우만 Oracle JDK를 선택한다. JDK 8 머문 시스템은 2030 데드라인을 카운트다운으로 잡고 마이그레이션을 시작해야 한다.**

---

## Q7. 🔴 버전 업그레이드 시 호환성 이슈와 실전 해결 사례

### [1] 한 줄 정의

> **JDK 업그레이드의 호환성 이슈는 "컴파일 호환 × 런타임 호환 × 도구 호환 × 의존성 호환"의 4축에서 발생한다. 가장 큰 함정은 reflection 기반 라이브러리(Spring/Hibernate/Mockito)가 strong encapsulation에 막혀 런타임에만 깨지는 케이스 — 빌드는 통과하니 canary에서야 발견된다.**

### [2] 본론 상세

#### 호환성 4축

```
[1] 컴파일 호환    — 소스가 컴파일되나? → javac --release N
[2] 바이트코드 호환 — class file 버전이 target JDK에서 로드되나?
[3] 런타임 호환    — reflection/internal API가 동작하나?
[4] 도구 호환     — Gradle/Maven/Lombok/QueryDSL 등 빌드 도구가 지원하나?
```

#### `--release` vs `--source/--target` — 자주 틀리는 부분

```bash
# 옛 방식 — 컴파일러 버전과 무관하게 source/target 지정
javac --source 8 --target 8 ...
# 문제: API는 JDK 17 stdlib을 보고 컴파일됨 → JDK 17에만 있는 API 호출 가능 → JDK 8 런타임에서 NoSuchMethodError

# JDK 9+ 권장 방식
javac --release 8 ...
# 효과: source/target/bootclasspath까지 JDK 8로 묶음 → JDK 8 API만 보임
```

- 운영 함정: 라이브러리 빌드 시 `--release` 안 쓰고 `--source/--target`만 쓰면 → "Java 8 호환 jar" 라는데 실제론 Java 11 API 호출 → 사용자가 런타임에 발견.

#### Reflection 호환성 — 가장 큰 함정

```
JDK 8: 어떤 클래스도 setAccessible(true) 통과
   ↓ (JEP 261)
JDK 9-16: --illegal-access=permit/warn — 통과하되 경고
   ↓ (JEP 403)
JDK 17+: --add-opens 없으면 InaccessibleObjectException
```

##### 실전 예 1: Spring 4 + JDK 17

```
java.lang.reflect.InaccessibleObjectException: 
  Unable to make field private final java.util.HashMap java.util.Optional.value
  accessible: module java.base does not "opens java.util" to unnamed module
```

해결:
```bash
java --add-opens java.base/java.util=ALL-UNNAMED \
     --add-opens java.base/java.lang=ALL-UNNAMED \
     -jar app.jar
```

본질 해결: Spring 5.3+/6+로 업그레이드 (reflection 사용처를 VarHandle/MethodHandle로 리팩토링됨).

##### 실전 예 2: Lombok + JDK 21

```
java.lang.IllegalAccessError: class lombok.javac.JavacTransformer 
  cannot access class com.sun.tools.javac.processing.JavacProcessingEnvironment
```

Lombok 1.18.30 이하 + JDK 21 = 빌드 실패. 1.18.32+로 올려야 함. **빌드 도구 자체가 internal API에 손대는 케이스** — 라이브러리 작성자가 패치 안 하면 사용자는 답이 없음.

#### Classpath/Modulepath 충돌

```
[증상]
ResolutionException: Modules a and b export package com.example
```

- **원인**: 같은 패키지를 두 jar/모듈이 가짐 (split package).
- **해결**:
  - Maven `<exclusions>` 또는 Gradle `exclude`로 중복 제거.
  - shade/relocate로 패키지명 변경.
- **빈출 사례**: `javax.annotation` — `javax.annotation-api` (Jakarta)와 `findbugs-jsr305`가 같은 패키지 export.

#### `jlink` — 작은 runtime 만들기

```bash
# JDK 모듈 + 내 모듈을 묶어 30MB runtime 생성
jlink \
    --module-path $JAVA_HOME/jmods:./mods \
    --add-modules com.example.app \
    --output ./runtime \
    --strip-debug --no-man-pages --compress=2

# 결과: ./runtime/bin/java로 내 앱만 실행 가능 — 작은 컨테이너 이미지
```

- **장점**: 컨테이너 이미지 200MB → 80MB.
- **함정**: automatic module은 jlink 불가 → 모든 의존 라이브러리가 named module이어야 함. 현실에선 거의 안 됨.

#### Multi-release JAR (JDK 9+)

```
my.jar
├── com/example/Foo.class           ← JDK 8 호환
├── META-INF/versions/11/
│   └── com/example/Foo.class       ← JDK 11+에서만 사용
└── META-INF/versions/17/
    └── com/example/Foo.class       ← JDK 17+에서만 사용
```

- 같은 jar 안에 여러 JDK 버전용 class 포함. 런타임 JDK가 알아서 자기 버전 선택.
- 라이브러리 작성자가 옛/새 JDK 동시 지원 시 사용.

### [3] 운영 영향 매핑

#### 마이그레이션 실전 절차 (Canary 기반)

```
[1] 빌드 호환성 확인 (오프라인)
    ├ javac --release N 빌드
    ├ jdeps --jdk-internals로 internal API 사용 스캔
    └ dependency tree 호환성 (mvn versions:display-dependency-updates)

[2] 단위/통합 테스트 (target JDK)
    ├ 모든 테스트 통과?
    └ Reflection 의존 라이브러리(Mockito, Jackson, Hibernate) 통과?

[3] Canary 배포 (1대)
    ├ 비교 메트릭: P99, throughput, RSS, GC pause, error rate
    ├ JFR continuous 켜고 24시간 관찰
    └ 차이가 미세하면 10%로 확대

[4] 10% / 50% / 100% 단계적 확대
    ├ 단계마다 24h+ 관찰
    └ rollback 즉시 가능 상태 유지 (옛 image 보관)

[5] 사후 보강
    ├ deprecated API 사용 코드 cleanup
    ├ JVM 옵션 재조정 (default GC 변경 반영)
    └ 모니터링 알람 임계값 조정
```

#### 자주 실패하는 패턴 5가지

| 패턴 | 증상 | 해결 |
|---|---|---|
| Reflection internal | `InaccessibleObjectException` | `--add-opens` 또는 라이브러리 업그레이드 |
| Split package | `ResolutionException` | 중복 의존 제거 |
| Lombok 옛 버전 | 컴파일 실패 | Lombok 1.18.32+ |
| `javax.*` 옛 패키지 | `ClassNotFoundException` | Jakarta namespace로 이전 또는 별도 jar 추가 |
| GC 옵션 deprecated | 옵션 무시 + 경고 | `-XX:+UseG1GC` 등 명시 |

#### 실제 사례 — Spring Boot 2 → 3 + JDK 17

```
1. Spring Boot 2.7 (JDK 8/11/17 지원) → Spring Boot 3.0 (JDK 17+ only)
2. 자동으로 따라오는 변화:
   - javax.* → jakarta.* (servlet, persistence, validation 등 다수)
   - Hibernate 5 → 6
   - Spring Security 6 (lambda DSL only)
3. 마이그레이션 도구:
   - openrewrite recipe (org.openrewrite.java.spring.boot3)
   - Spring Boot Migrator
4. 평균 작업 기간: 100k LOC 모놀리스 기준 2-4주
```

### [4] 한 줄 정리

> **JDK 업그레이드는 컴파일이 아니라 reflection이 깨고, 도구가 깨고, 의존 라이브러리가 깬다. 시니어는 jdeps + canary + JFR로 무장하고, "한 번에 다 옮기지 않고 layer별로 점진 전환"하는 절차를 표준화한다.**

---

## Q8. 🔴 Virtual Thread (Project Loom)와 서버 아키텍처 변화

### [1] 한 줄 정의

> **Virtual Thread는 "thread를 OS 자원에서 JVM 자원으로 끌어내려" thread-per-request 모델을 다시 가능하게 만든 동시성 혁명이다. 수십만 동시 thread + blocking I/O가 단순 코드로 가능해지면서, Reactive(WebFlux)의 콜백/Mono/Flux 없이 sequential 코드로 같은 처리량을 달성한다. 단, synchronized + I/O 조합의 pinning과 ThreadLocal 비용, downstream 자원 한계가 새로운 함정이다.**

### [2] 본론 상세

#### Platform Thread vs Virtual Thread — 본질 차이

```
[Platform Thread] (옛 java.lang.Thread)
JVM Thread = OS Thread (1:1)
   ↓
스레드당 ~1MB stack (OS 메모리)
context switch = OS scheduler (μs 단위)
1만 스레드 = 10GB stack → 불가능
→ Tomcat 200 스레드 한계가 동시 요청 수 한계

[Virtual Thread] (JDK 21+)
M:N — 수많은 VT가 적은 carrier(OS thread)에 mount/unmount
   ↓
스레드당 ~수 KB (heap에 stack chunk)
blocking I/O 시 VT가 carrier에서 unmount → 다른 VT 실행
context switch = JVM 내부 (ns 단위)
100만 VT = 수 GB heap → 가능
→ thread-per-request 부활
```

#### 동작 메커니즘

```
Carrier Pool (ForkJoinPool, CPU 코어 수만큼)
┌──────┬──────┬──────┐
│ C0   │ C1   │ C2   │   ← OS thread (carrier)
└──────┴──────┴──────┘
   ↑       ↑      ↑
   │       │      │
 V12     V47    V103     ← Virtual Thread (현재 실행 중)
 V13     V48    V104
 V14     V49    V105     ← parked (blocking I/O 대기)
 ...     ...    ...

[Mount/Unmount 사이클]
1. VT가 socket.read() 같은 blocking 호출
2. JVM이 VT의 stack을 heap으로 push (Continuation)
3. VT가 carrier에서 unmount → carrier는 다음 VT 실행
4. I/O 완료 시 VT는 ready 큐로 → carrier가 mount → 재개
```

#### Pinning — 가장 큰 함정

```java
synchronized (lock) {
    // 이 블록 안에서 blocking I/O를 하면
    socket.read();  // ← carrier에서 unmount 불가능!
}
// → carrier가 같이 block → carrier 풀 고갈 → 처리량 저하
```

- **이유**: `synchronized` 모니터는 OS thread에 종속 — VT를 unmount하면 모니터 소유권 혼란.
- **해결**:
  - `synchronized` → `ReentrantLock` (Lock은 VT 친화적, unmount 가능)
  - JDK 24+ JEP 491: synchronized + I/O도 unmount 가능하도록 개선 예정
- **진단**:
  ```bash
  -Djdk.tracePinnedThreads=full    # pinning 발생 시 stack trace 출력
  ```
  JFR `jdk.VirtualThreadPinned` 이벤트.

#### thread-per-request 부활 — 코드 비교

```java
// [Reactive (WebFlux)] — 옛날 방식
public Mono<Order> getOrder(String id) {
    return userRepo.findById(id)
        .flatMap(u -> orderRepo.findByUser(u))
        .zipWith(paymentRepo.findByUser(u), (orders, payments) -> 
            merge(orders, payments))
        .onErrorResume(e -> Mono.error(...));
}

// [Virtual Thread] — JDK 21
public Order getOrder(String id) {
    var user = userRepo.findById(id);      // blocking, but VT unmounts
    var orders = orderRepo.findByUser(user);
    var payments = paymentRepo.findByUser(user);
    return merge(orders, payments);
}
```

- 같은 처리량 + 같은 동시성. 단, Virtual Thread는 sequential 코드 — debugger, stack trace, exception이 직관적.

#### Structured Concurrency (preview, JEP 462)

```java
try (var scope = new StructuredTaskScope.ShutdownOnFailure()) {
    var user = scope.fork(() -> userRepo.findById(id));
    var orders = scope.fork(() -> orderRepo.findByUser(id));
    var payments = scope.fork(() -> paymentRepo.findByUser(id));
    
    scope.join();              // 모든 subtask 완료 대기
    scope.throwIfFailed();     // 하나라도 실패하면 나머지 cancel + throw
    
    return merge(user.get(), orders.get(), payments.get());
}
```

- **본질**: subtask들의 lifecycle을 parent scope에 묶음 → exception/cancellation이 일관되게 전파.
- **차이**: CompletableFuture는 "fire and forget" 가능 → leak 위험. SC는 scope 안에서 모든 task가 끝나야 빠져나갈 수 있음.
- **Go의 errgroup, Kotlin의 coroutine scope와 동일 패러다임**.

#### Scoped Values (preview, JEP 446)

```java
// 옛 ThreadLocal — VT에서는 GC 부담
private static final ThreadLocal<User> CURRENT_USER = new ThreadLocal<>();

// 새 ScopedValue — VT 친화, immutable, 자동 cleanup
private static final ScopedValue<User> CURRENT_USER = ScopedValue.newInstance();

ScopedValue.where(CURRENT_USER, user).run(() -> {
    // 이 람다 안에서만 CURRENT_USER.get() 가능
    // 람다 종료 후 자동 cleanup
});
```

- **왜 필요한가**: ThreadLocal은 mutable + per-thread 인스턴스 → VT 100만 개 = ThreadLocal 100만 개 = heap 폭발.
- **ScopedValue**: immutable + scope 단위 → VT가 끝나면 자동 정리.

#### Virtual Thread vs async/await (Kotlin/JS/Python)

| 항목 | Virtual Thread | async/await |
|---|---|---|
| 코드 색깔 | 모든 함수 동일 (color-blind) | async 함수와 일반 함수 분리 ("function coloring problem") |
| 라이브러리 마이그레이션 | 기존 blocking I/O 그대로 작동 | 라이브러리 전부 async 버전으로 다시 작성 필요 |
| 스택 추적 | 기존과 동일 | 비동기 경계마다 끊김 |
| 학습 곡선 | 평탄 (Thread 그대로) | 가파름 (coroutine 개념) |
| 단점 | Pinning, ThreadLocal 비용 | Function coloring, 호환성 |

- **Java의 선택이 더 큰 베팅**: 기존 수십억 줄의 blocking 코드를 그대로 살려 VT만 갈아끼우는 전략.

### [3] 운영 영향 매핑

#### 아키텍처 변화 시나리오

```
[Before — Reactive 강제]
Tomcat 200 thread × Spring MVC = 동시 200 요청 한계
   ↓ 더 가려면
WebFlux + Reactor + non-blocking driver (r2dbc, reactor-kafka)
   ↓ 비용
콜백 지옥, 학습 곡선, 디버깅 어려움, 일부 라이브러리 미지원

[After — Virtual Thread (JDK 21+)]
Spring MVC + Tomcat (VT executor) = 동시 100,000+ 요청
   ↓ 코드는 그대로 blocking
WebFlux 필요성 사라짐 (대부분 케이스에서)
```

#### Spring Boot 3.2+ Virtual Thread 활성화

```yaml
# application.yml
spring:
  threads:
    virtual:
      enabled: true
```

- Tomcat의 request worker가 VT로 전환됨.
- `@Async` 메서드도 VT 사용.

#### 새로운 병목 — Connection Pool 재설계

```
[옛날]
Tomcat 200 thread → HikariCP 50 connection → DB 100 connection
   ↓ thread가 connection 대기 (50:200 비율 = block 자주)

[Virtual Thread]
VT 100,000 → HikariCP 50 → DB
   ↓ 100,000개가 50개 connection을 대기 → DB가 새 병목

해결:
- Connection pool 크기를 VT에 맞춰 늘리되, DB 부담 고려
- Semaphore로 downstream 호출 제한 (rate limiter)
- DB connection을 짧게 잡고 빨리 반환
```

#### Pinning 진단 — production 운영 체크리스트

```bash
# 1. JFR로 pinning 이벤트 수집
jcmd <pid> JFR.start name=vt duration=10m \
    settings=profile filename=/tmp/vt.jfr

# 2. JFR 이벤트 확인
jfr print --events jdk.VirtualThreadPinned /tmp/vt.jfr

# 3. 옛 라이브러리의 synchronized 식별
# - JDBC driver (HikariCP getConnection 안에 synchronized 있음 → JDK 21 patch 됐는지 확인)
# - 일부 logging framework
# - 옛 connection pool
```

#### 마이그레이션 권장 순서

1. **JDK 21 도입** (Spring Boot 3.2+)
2. **`spring.threads.virtual.enabled=true`** — 옵션 켜기
3. **부하 테스트** — 옛 P99/throughput과 비교
4. **JFR로 pinning 모니터링** — 24h 이상 관찰
5. **pinning 핫스팟 식별 → synchronized → ReentrantLock 리팩토링**
6. **Connection pool 사이즈 재산정** — VT가 만드는 부하 패턴 반영
7. **WebFlux 사용처 점진 제거** (선택) — 사실상 대다수 케이스에서 VT로 충분

### [4] 한 줄 정리

> **Virtual Thread는 "비싼 OS thread를 가짜 JVM thread로 대체"해 thread-per-request 모델을 부활시킨 혁명이다. 코드는 sequential blocking, 처리량은 reactive 수준. 시니어가 알아야 할 함정은 synchronized pinning, ThreadLocal 비용, downstream connection pool 재설계 세 가지 — 이게 production에서 새 병목으로 나타난다.**

---

## 종합 — 8문항을 한 흐름으로

```
8 (Lambda/Stream + Metaspace)
   ↓ 코드 스타일 + PermGen 폐지
패턴이 함수형으로 압축됨 (Q2)
   ↓
11 (G1 default + JPMS + JEE 분리)
   ↓ 모듈 경계 + reflection 깨짐 시작
JPMS의 ROI 논쟁 (Q3) + Deprecation 데드라인 (Q5)
   ↓
17 (ZGC production + Strong Encap + Records/Sealed)
   ↓ latency + 데이터 모델 + 마이그레이션 함정
sub-ms GC + DDD 친화 + Reflection 깨짐 (Q4, Q7)
   ↓
21 (Virtual Thread + Generational ZGC + Pattern Switch)
   ↓ 동시성 모델 혁명
thread-per-request 부활 + WebFlux 대체 가능 (Q8)
   ↓
LTS 선택 (Q6) — Temurin/Corretto default + 2030 데드라인
```

### 시니어가 백지에서 그릴 수 있어야 하는 그림

```
JDK 8 ─── 11 ─── 17 ─── 21 ─── 25(LTS)
2014   2018    2021   2023    2025

Lang:  Lambda  var     Records  VT
       Stream  switch  Sealed   Pattern Switch
       Opt.    expr    Pattern  Record Pattern

JVM:   Metaspace JPMS  Strong   FFM
       Tiered   AppCDS encap.   Loom
                       MacAArch64

GC:    G1 사용  G1 def  ZGC     GenZGC
       Parallel CMS    sub-ms   sub-ms+throughput
       default  remove

운영  PermGen   --illegal Spring  synchronized
함정  OOM 사라짐 access    Boot 3   pinning
                deprecate Jakarta  ThreadLocal
                          namespace
```

이 그림 하나에 8개 질문의 답이 다 들어있다 — 시니어는 면접에서 이 그림을 그리고 어느 가지에 대한 질문이든 거기서 출발한다.
