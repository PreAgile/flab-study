# 객체지향 깊이 학습 — 백지에서 설계 권위자 수준까지

> "객체지향은 데이터와 메서드를 묶는 것이다" 라고 말할 수 있다면 입문자.
> "객체지향은 자율적인 객체들이 메시지로 협력하여 책임을 분담하는 패러다임이고, 절차지향이 데이터와 프로세스를 분리하면서 발생한 의존성 폭발 문제를 캡슐화·다형성·다이내믹 디스패치로 해결했지만 가변 상태 공유라는 부작용을 남겼기에 함수형의 불변성·순수함수가 보완 패러다임으로 부상했고, Java는 람다/Stream/Record/Sealed/Pattern Matching으로 점진적 하이브리드화되었으며 Kotlin은 처음부터 불변성/널 안전성/표현식 기반 설계로 그 균형을 언어 차원에 박았다" 라고 말할 수 있다면 그 다음 단계.
> 이 학습 경로의 목표는 후자다.

<details>
<summary><strong>📖 위 문장의 용어가 하나도 안 와닿는다면 → 클릭해서 펼치기</strong></summary>

지금 모르는 게 정상이다. 이 가이드 전체의 목표가 이 한 문장을 풀어내는 것이다.
각 용어를 짧게 풀고, 어느 챕터에서 깊이 다루는지 링크한다.

---

<details>
<summary><strong>1. 자율적인 객체 — 객체지향의 핵심 단위</strong></summary>

**정의**: 자기 상태를 스스로 관리하고, 외부의 요청(메시지)에 대해 **어떻게 처리할지 스스로 결정**하는 소프트웨어 단위.

**왜 자율인가**: 절차지향에서는 데이터(struct)와 프로세스(function)가 분리되어, 데이터의 처리 책임이 외부 함수에 있다. 객체지향은 그 책임을 데이터를 보유한 객체 자신에게 이양한다. → 외부는 "무엇을 해달라"만 알고, "어떻게"는 객체가 안다.

**조영호의 표현**: "객체는 자신의 데이터를 스스로 책임지는 자율적인 존재" — 『오브젝트』 2장.

**자세히**: [01-object-and-collaboration](./01-object-and-collaboration/)

</details>

<details>
<summary><strong>2. 메시지 — 객체 간의 유일한 소통 채널</strong></summary>

**정의**: 한 객체가 다른 객체에게 "이 일을 해달라"고 요청하는 행위. Java/Kotlin에서는 메서드 호출로 구현되지만, 개념적으로는 **메시지 송수신**이 우선이다.

**왜 메시지가 먼저인가**: Smalltalk를 만든 Alan Kay는 "OOP는 객체가 아니라 메시지가 핵심"이라고 말했다. 메시지(=인터페이스)를 먼저 정의하고, 그것을 받을 객체(=구현)는 나중에 정하는 사고 순서가 좋은 설계를 낳는다.

**Tell, Don't Ask**: "객체의 상태를 묻지(Ask) 말고 일을 시켜라(Tell)". 이 원칙이 깨지면 절차지향으로 회귀한다.

**자세히**: [04-message-and-interface](./04-message-and-interface/)

</details>

<details>
<summary><strong>3. 책임 — 객체가 알아야 할 것과 해야 할 것</strong></summary>

**정의**: 어떤 객체가 자기 영역 안에서 **알고 있는 것(knowing)**과 **할 수 있는 것(doing)**의 합.

**왜 책임이 중심인가**: 객체지향 설계의 본질은 "**어떤 책임을 누구에게 줄 것인가**"이다. 클래스/속성/메서드는 그 답을 표현하는 수단일 뿐.

**할당 원칙 (GRASP)**:
- **정보 전문가** — 그 일에 필요한 정보를 가장 많이 가진 객체에게 책임을 준다.
- **창조자** — 객체 A를 생성할 책임은 A를 사용하거나 A의 데이터를 가진 객체에게.
- 그 외 9가지.

**자세히**: [03-responsibility-assignment](./03-responsibility-assignment/)

</details>

<details>
<summary><strong>4. 협력 — 객체들이 함께 일하는 모습</strong></summary>

**정의**: 여러 객체가 메시지를 주고받으며 **하나의 기능**을 함께 완성하는 과정.

**왜 협력 중심인가**: 단일 객체로 의미 있는 시스템은 만들 수 없다. 시스템은 **객체들의 협력 구조**다. 이걸 그리는 도구가 **시퀀스 다이어그램**과 **CRC 카드**.

**조영호의 표현**: "객체는 협력 안에서만 의미를 가진다" — 『오브젝트』 1장.

**자세히**: [01-object-and-collaboration](./01-object-and-collaboration/)

</details>

<details>
<summary><strong>5. 절차지향 — OOP의 전 시대 패러다임</strong></summary>

**정의**: 데이터(struct/record)와 처리 함수가 분리되어 있고, 함수가 데이터를 받아 변환하는 방식. C, Pascal, COBOL이 대표.

**왜 한계가 왔나** (1970~80년대):
1. **데이터-함수 일관성 깨짐** — 데이터 구조가 바뀌면 그것을 다루는 함수 N개가 모두 변경.
2. **전역 상태 공유** — 함수 간 통신을 전역 변수로 → 사이드 이펙트 폭발.
3. **재사용 단위 부재** — 함수 시그니처가 묶이지 않아 라이브러리 단위가 비대.
4. **현실 모델링과의 간극** — 도메인 개념(고객, 주문, 영화)을 표현할 일급 단위 없음.

**해법**: 데이터와 그것을 다루는 메서드를 **하나의 모듈(클래스)** 로 묶는다 = 객체지향.

**자세히**: [00-overview/02-procedural-vs-oop.md](./00-overview/02-procedural-vs-oop.md), [05-object-decomposition](./05-object-decomposition/)

</details>

<details>
<summary><strong>6. 캡슐화 — 변경의 단위를 격리</strong></summary>

**정의**: 객체의 **내부 상태**(필드)를 외부로부터 숨기고, 외부는 **공개된 메서드(인터페이스)** 로만 접근하게 하는 원칙.

**왜 중요한가**:
- 내부 구현이 바뀌어도 외부에 영향을 안 주려면, 외부가 내부에 직접 접근하지 못해야 한다.
- `getter/setter`를 무분별하게 열면 캡슐화는 깨진다 — 그건 단지 "field access를 method로 바꾼 것" 일 뿐.

**조영호의 강조**: "캡슐화는 데이터 은닉이 아니라 **변경의 캡슐화**다." — 변경 가능성이 높은 부분을 외부로부터 격리하는 행위.

**자세히**: [02-abstraction-and-encapsulation](./02-abstraction-and-encapsulation/)

</details>

<details>
<summary><strong>7. 다형성 — 같은 메시지, 다른 행동</strong></summary>

**정의**: 동일한 메시지(메서드 호출)를 받은 객체들이 자신의 타입에 따라 **다른 방식으로 응답**하는 능력.

**3가지 종류**:
1. **Subtype Polymorphism** — `interface Animal` 을 구현한 `Dog`, `Cat`이 `speak()`를 다르게 응답. 가장 흔함.
2. **Parametric Polymorphism** — 제네릭. `List<T>`의 `T`가 무엇이든 동작.
3. **Ad-hoc Polymorphism** — 오버로딩, Kotlin 확장 함수, 타입 클래스(Haskell).

**런타임 메커니즘**: **다이내믹 디스패치** — 메서드 호출이 컴파일 타임이 아닌 **런타임의 객체 타입**에 따라 결정. JVM에서는 `invokevirtual` 바이트코드 + vtable.

**자세히**: [02-abstraction-and-encapsulation/03-polymorphism.md](./02-abstraction-and-encapsulation/03-polymorphism.md)

</details>

<details>
<summary><strong>8. 다이내믹 디스패치 — 런타임 메서드 선택</strong></summary>

**정의**: 메서드 호출 시 **실제 객체의 타입**을 보고 호출할 메서드를 결정하는 메커니즘.

**왜 필요한가**: 다형성을 가능하게 하는 핵심 메커니즘. 컴파일러는 `animal.speak()`가 어느 클래스의 `speak`를 부를지 모른다 — 런타임의 객체 타입에 따라 달라진다.

**JVM 구현**:
- `invokevirtual` 바이트코드 → vtable (virtual method table) lookup.
- HotSpot JIT의 **Inline Cache (IC)**: 자주 보는 타입을 캐싱해서 가상 호출을 직접 호출처럼 빠르게.
- **Megamorphic call site**: 너무 많은 타입이 들어오면 IC가 무력화 → vtable lookup fallback.

**왜 알아야 하나 (실무)**: 가상 호출이 인라이닝을 막아 P99 latency를 망치는 사례가 있다. `final` 또는 `sealed` 키워드로 단형성을 강제하면 JIT이 monomorphic으로 처리 → 성능 향상.

**JVM 연관**: [../jvm/03-execution-engine](../jvm/) (Inline Cache, Speculative Opt)

**자세히**: [02-abstraction-and-encapsulation/03-polymorphism.md](./02-abstraction-and-encapsulation/03-polymorphism.md)

</details>

<details>
<summary><strong>9. 의존성 폭발 — 객체지향이 자초한 그림자</strong></summary>

**정의**: 객체가 다른 객체를 직접 알면서(import, new), 그 객체가 바뀌면 같이 바뀌어야 하는 관계가 시스템 전체로 번지는 현상.

**왜 생기나**:
- 객체지향에서 한 객체는 다른 객체에게 메시지를 보내야 일이 진행된다.
- 그러려면 **상대를 알아야** 한다 → 의존.
- 의존이 많아지면 한 군데 변경이 N개로 전파.

**해결책 (의존성 관리)**:
1. **추상화에 의존** (DIP) — 구체 클래스가 아닌 인터페이스에 의존.
2. **의존성 주입** (DI) — 의존 객체를 직접 생성하지 않고 외부에서 받음.
3. **컨테이너의 IoC** — Spring 같은 프레임워크가 객체 그래프를 조립.

**자세히**: [06-dependency-management](./06-dependency-management/), [12-spring-and-framework](./12-spring-and-framework/)

</details>

<details>
<summary><strong>10. 가변 상태 공유 — OOP의 근본 부작용</strong></summary>

**정의**: 여러 객체가 같은 **변경 가능한 객체**를 참조할 때, 한 객체의 수정이 다른 객체에 영향을 주는 현상.

**왜 OOP에서 문제인가**:
- 객체는 본래 **상태를 가진다**. 그 상태가 외부에 노출되어 공유되면 누가 언제 바꿨는지 추적이 어려움.
- **동시성**: 멀티스레드 환경에서 가변 객체 공유는 race condition, deadlock의 원인.
- **테스트**: 상태에 따라 결과가 달라지면 테스트가 비결정적.

**OOP 자체의 답**: 캡슐화 + 메시지로 외부 접근 차단.
**함수형의 답**: 아예 **불변** 객체만 사용. 변경이 필요하면 새 객체를 만든다.
**Java의 답 (하이브리드)**: `final`, `record`, Stream, `CompletableFuture` 등으로 함수형을 흡수.
**Kotlin의 답**: `val`/`var` 명시적 구분, `data class` 자동 copy, `List`/`MutableList` 타입 분리.

**자세히**: [09-functional-paradigm/02-pure-function-and-immutability.md](./09-functional-paradigm/02-pure-function-and-immutability.md)

</details>

<details>
<summary><strong>11. 불변성 — 함수형의 핵심 무기</strong></summary>

**정의**: 객체가 생성된 후 그 상태가 **절대 변하지 않음**. 변경이 필요하면 새 객체를 만든다.

**왜 강력한가**:
1. **추론 가능성** — 어떤 시점에서든 객체 상태가 동일하므로 코드 이해가 쉽다.
2. **스레드 안전성** — 변경이 없으니 동기화도 필요 없다.
3. **시간 여행 디버깅** — 과거 상태를 모두 보존 가능 (Event Sourcing의 토대).
4. **컴파일러 최적화** — 변경 없음을 알면 캐싱/병렬화가 안전.

**비용**: 매번 새 객체 할당 → GC 압박. 하지만 현대 GC(G1, ZGC)는 단명 객체를 매우 효율적으로 처리.

**Java/Kotlin 표현**:
- Java: `final` 필드, `record`, `List.of()`, `Collections.unmodifiableList()`.
- Kotlin: `val`, `data class`, `listOf()`, `copy()`.

**자세히**: [09-functional-paradigm/02-pure-function-and-immutability.md](./09-functional-paradigm/02-pure-function-and-immutability.md)

</details>

<details>
<summary><strong>12. 순수함수 — 부작용 없는 계산</strong></summary>

**정의**: 같은 입력에 대해 **항상 같은 출력**을 내고, **외부 상태를 변경하지 않는** 함수.

**왜 중요한가**:
1. **참조 투명성** — `f(x)`를 그 결과값으로 치환해도 프로그램이 동일하게 동작.
2. **합성 가능** — 작은 순수함수들을 조립해 큰 함수를 만든다 → 함수형의 핵심 기법.
3. **테스트 용이** — 입출력만 보면 검증 가능. mock도 필요 없다.

**예시**:
```java
// 순수 X — 외부 상태(DB) 의존
int countActiveUsers() { return userRepo.findActive().size(); }

// 순수 O — 입력에서만 계산
int countActive(List<User> users) {
    return (int) users.stream().filter(User::isActive).count();
}
```

**자세히**: [09-functional-paradigm/02-pure-function-and-immutability.md](./09-functional-paradigm/02-pure-function-and-immutability.md)

</details>

<details>
<summary><strong>13. 람다 — Java가 함수형을 흡수한 첫 관문</strong></summary>

**정의**: 익명 함수 표현식. Java 8(2014)에서 도입.

**왜 추가됐나**:
- Java 7 까지는 함수를 일급 시민으로 다룰 수 없었다 → `Runnable`, `Comparator` 같은 익명 클래스 boilerplate 폭발.
- 멀티코어 시대, **병렬 컬렉션 처리**(Stream)를 위한 동작 파라미터화 필수.
- 다른 언어(Scala, C#, Python)가 모두 가지고 있는 상태에서 Java만 뒤처짐.

**JVM 구현 (`invokedynamic`)**:
- 람다는 단순히 익명 클래스의 syntactic sugar가 아니다.
- Java 8은 `invokedynamic` + `LambdaMetafactory`로 **런타임에 람다 클래스를 동적 생성**.
- 익명 클래스보다 빠르고 메모리 적음.

**Java 연관**: [10-java-evolution/02-java-8-lambda-stream.md](./10-java-evolution/02-java-8-lambda-stream.md)

</details>

<details>
<summary><strong>14. 하이브리드 패러다임 — Java/Kotlin이 택한 길</strong></summary>

**정의**: 한 언어 안에 OOP와 FP를 **둘 다** 표현 가능하게 한 설계.

**왜 하이브리드인가**:
- 도메인 모델링은 OOP가 직관적 (주문, 회원, 결제 등은 "상태를 가진 행위자"로 모델링이 자연스러움).
- 데이터 변환/스트림 처리/병렬화는 FP가 우월.
- 둘 다 필요한 게 현실 — 한 시스템 안에 도메인 로직과 데이터 처리가 공존.

**Java의 진화 (점진적)**:
- 8 (2014): 람다, Stream, Optional → 함수형 진입.
- 9~10: var, modular system.
- 14~16: switch expression, record, sealed → ADT(대수적 데이터 타입).
- 21 (2023): pattern matching, virtual thread → 표현식 기반 + 동시성.

**Kotlin의 선택 (처음부터)**:
- `val` 기본 + `var` 명시 → 불변 우선.
- `data class` → record와 유사하지만 6년 먼저(2016).
- `sealed class` + `when` → 닫힌 계층 + 패턴 매칭.
- 함수가 일급 시민(`(Int) -> Int` 타입).
- Null 안전성 → `Optional`보다 깊은 타입 시스템 수준 보장.

**자세히**: [10-java-evolution](./10-java-evolution/), [11-kotlin-paradigm](./11-kotlin-paradigm/)

</details>

<details>
<summary><strong>15. Spring DI/IoC — OOP를 운영 가능하게 만든 프레임워크</strong></summary>

**정의**: Spring은 **객체 그래프 조립**을 개발자 코드에서 분리하여 외부 컨테이너에 위임하는 IoC(Inversion of Control) 프레임워크.

**왜 등장**:
- 2000년대 초 EJB의 무거움 + XML 지옥.
- Rod Johnson의 "Expert One-on-One J2EE Design and Development" (2002) → "POJO 기반의 가벼운 컨테이너로 충분하다"는 주장.
- DI를 통해 객체가 **자기 의존성을 모름** → 테스트 용이, 교체 용이.

**OOP 원칙과의 관계**:
- DIP (의존성 역전 원칙) 실현 도구.
- 단일 책임 원칙 강화 — 객체 생성 책임을 객체 자신에서 분리.
- 개방-폐쇄 원칙 — 빈 등록만 바꾸면 동작 변경.

**AOP**:
- 횡단 관심사(로깅, 트랜잭션, 보안)를 메서드 본문이 아닌 어드바이스로 분리.
- 프록시 기반 (JDK Dynamic Proxy 또는 CGLIB).
- "객체지향이 못 푸는 영역"을 보조.

**자세히**: [12-spring-and-framework](./12-spring-and-framework/)

</details>

---

**큰 그림**: 이 문장의 흐름은 사실 한 줄로 요약된다.

```
절차지향이 데이터/함수 분리로 한계 → 객체지향이 캡슐화·다형성으로 해법 제시
                                  → but 가변 상태 공유라는 새 문제
                                  → 함수형(불변/순수)이 보완 패러다임으로 등장
                                  → Java가 점진적 하이브리드화 (lambda → record → sealed → pattern)
                                  → Kotlin이 처음부터 균형 잡힌 하이브리드
                                  → Spring DI/AOP가 객체지향 운영의 실제 도구
```

이 흐름을 한 문장에 담은 게 위 인용문이다. 이걸 자유롭게 풀어 말할 수 있게 되는 것이 이 가이드의 목표.

**한 단계 더**: 이 문장을 **풀어 설명**할 수 있다면 시니어. **실제 코드/시스템에서 적용·진단·리팩토링**할 수 있다면 설계 권위자 수준.
→ 본 챕터 (00~12)가 "설명 능력"을, 보강 챕터 (20/21/22)가 "실전 능력"을 만든다.

</details>

---

## 🏢 왜 OOP를 깊이 학습하나 — 실무 현장의 관점

> 이 가이드의 진짜 목적은 **객체지향 용어를 외우는 것이 아니다**.
> 새로운 도메인을 받았을 때 객체 청사진을 그릴 수 있고, 레거시 코드를 보고 무엇이 잘못됐는지 진단할 수 있고, 팀과 함께 변경에 강한 시스템을 점진적으로 발전시킬 수 있는 **설계 사고력**을 만드는 것이다.

### 실제 기업이 OOP 역량을 바라보는 시각

| 회사 관점 | 무엇을 본다 |
|---|---|
| **시니어/리드 채용 면접** | 도메인 모델링 (영화 예매, 주문, 결제 등 즉석 설계), CRC 카드, 시퀀스 다이어그램 |
| **코드 리뷰 문화** | God Object, Anemic Domain, Feature Envy, Shotgun Surgery 같은 안티패턴 식별·교정 |
| **아키텍처 회의** | DDD Bounded Context, Aggregate 경계, Domain Event, 의존 방향 |
| **테스트 코드 작성** | Mock 남용 vs 테스트 더블 종류 (Stub, Spy, Fake) 분리, 행위 검증 vs 상태 검증 |
| **MSA 분할 시점** | 결합도 분석, Bounded Context 식별, 데이터 일관성 vs 가용성 트레이드오프 |
| **레거시 리팩토링** | 점진적 추출 (Extract Class, Move Method), Strangler Fig 패턴 |

→ **"OOP 원칙을 안다" ≠ "OOP로 시스템을 설계한다"**. 두 번째가 진짜 가치.

### 흔히 마주치는 설계 안티패턴 7대 카테고리

이 가이드의 모든 챕터가 결국 답하려는 질문:

```
1. God Object — 한 클래스가 시스템의 모든 책임을 가짐
   → 챕터 03 (Responsibility Assignment), 20 (Ops Scenarios)

2. Anemic Domain Model — 도메인 객체가 데이터만 들고, 로직은 Service에 흩어짐
   → 챕터 01 (Object), 03 (Responsibility), 20 (Ops Scenarios)

3. Feature Envy — 한 클래스가 다른 클래스의 데이터에 과도하게 접근
   → 챕터 04 (Tell Don't Ask), 20 (Ops Scenarios)

4. Inheritance 남용 — 코드 재사용 목적으로 상속 → 깨지기 쉬운 계층
   → 챕터 08 (Inheritance vs Composition), 20 (Ops Scenarios)

5. 의존성 폭발 — 한 변경이 시스템 전체로 전파
   → 챕터 06 (Dependency Management), 22 (Tradeoff Table)

6. Spring 어노테이션 의존 — DI/IoC를 안 쓰는 것보다 더 위험한 "@Autowired everywhere"
   → 챕터 12 (Spring and Framework), 20 (Ops Scenarios)

7. OOP/FP 혼용 혼란 — 도메인은 절차지향, 데이터 처리는 OOP 같은 역방향 적용
   → 챕터 09 (Functional), 10 (Java), 11 (Kotlin), 22 (Tradeoff Table)
```

### 모든 챕터에 적용되는 "조영호 사고법 + 실전 사례" 원칙 ⭐

각 챕터의 **6단 (트레이드오프) + 7단 (운영 진단)** 은 단순 이론 나열이 아니라 **실제 코드 변경 시나리오**와 연결되어야 한다:

- ❌ "캡슐화는 데이터를 private으로 만들고 getter/setter를 제공하는 것이다." (잘못된 통념)
- ✅ "결제 도메인에서 `Order`가 `setStatus(PAID)`를 public으로 노출하면 외부 코드가 `validatePayment → setStatus(PAID)` 같이 호출 → 추후 결제 검증 로직이 추가되면 호출처 N개 수정. 대신 `order.pay(payment)` 한 메서드로 캡슐화하면 검증 로직 변경이 Order 안에 격리." (사례 + 변경 비용 + 트레이드오프)

각 챕터의 7단에 다음 4요소 포함을 권장:
1. **증상 코드** — 안티패턴이 어떻게 보이나
2. **냄새 진단** — 무엇이 잘못됐는지 명명 (Code Smell)
3. **리팩토링 패턴** — Fowler/조영호의 표준 기법
4. **공개 사례 참조** — 카카오/우아한기술블로그/Netflix/우아한형제들 도메인 모델링 사례

→ 상세 사례집은 [20-ops-scenarios](./20-ops-scenarios/) 챕터에서 종합.
→ **빅테크 7대 안티패턴 + 리팩토링**: [20-ops-scenarios/00-real-world-cases.md](./20-ops-scenarios/00-real-world-cases.md) ⭐

### 참조 — 국내/해외 빅테크 도메인 모델링 사례

각 사례·원칙·리팩토링은 다음 출처에서 검증한다.

**🇰🇷 국내** (우아한기술블로그 — 배달의민족 도메인 모델링, 카카오 tech, 네이버 D2 — 페이/쇼핑 도메인, 토스 tech — 금융 도메인, 라인 engineering, 쿠팡 engineering — 주문/결제, 컬리 helloworld, 당근 team, NHN Cloud 등)

**🌍 해외** (Martin Fowler refactoring.com, ThoughtWorks Technology Radar, Domain-Driven Design Reference — Eric Evans, Vaughn Vernon "Implementing DDD", Netflix Tech Blog, Uber Engineering, Stripe Engineering)

**📚 핵심 서적** (조영호 "오브젝트", 조영호 "객체지향의 사실과 오해", Eric Evans "Domain-Driven Design", Vaughn Vernon "Implementing DDD", Martin Fowler "Refactoring 2nd", Robert Martin "Clean Code"/"Clean Architecture", Joshua Bloch "Effective Java", "Kotlin in Action")

전체 URL과 핵심 콘텐츠 목록은 [20-ops-scenarios/00-real-world-cases.md](./20-ops-scenarios/00-real-world-cases.md) 상단 참조.

---

## 0. 학습 철학

### 7단 레이어 (모든 챕터의 통일된 깊이)

각 토픽은 다음 7단계를 **반드시** 거친다.
앞 5단은 "안다", 뒤 2단은 "할 줄 안다" — 둘 다 채워야 시니어급.

| 단계 | 무엇을 | 왜 |
|---|---|---|
| **1. 백지 그리기** | Excalidraw 지시문 + 그림 임베드 (CRC, 시퀀스, 클래스 다이어그램) | 손으로 그려야 머릿속에 박힌다 |
| **2. 직관** | 한 줄 비유, "왜 존재하는가" | 본질을 잡지 못하면 디테일은 무용지물 |
| **3. 구조** | ASCII/Mermaid로 객체 협력 분해 | 박스와 화살표로 사고하기 |
| **4. 내부 구현** | JVM 바이트코드 / Spring 컨테이너 / Kotlin 컴파일러 산출물 | "추상 → 실체" 점프 |
| **5. 역사** | 어떤 문제로 어떻게 진화했나 (Simula → Smalltalk → Java → Kotlin) | 현재 설계는 과거의 상처다 |
| **6. 트레이드오프** ⭐ | 다른 패러다임/패턴과 비교표 + 왜 이걸 선택했나 | "왜 X 대신 Y인가" 답변의 논거 무장 |
| **7. 운영 진단** ⭐ | 코드 리뷰 시 안티패턴 식별, 리팩토링 카타, 테스트 가능성 분석 | "안다"와 "할 줄 안다"의 차이 — 면접 차별화 |
| **+ 꼬리질문** | Q → 예상답 → 꼬리 → 더 깊은 꼬리 (3단+) | 면접/실무 양쪽 검증 |

> **6단·7단 ⭐ 표시**: 시니어/설계 권위자 수준에 도달하려면 필수 보강 영역. "외운 사람"과 "다뤄본 사람"의 경계.

### "왜" 중심 학습

> 모든 챕터는 다음 질문에 답해야 한다:
> 1. 이게 **없었던 시대**에는 어떻게 했나?
> 2. 어떤 **문제**가 이걸 만들게 했나?
> 3. **다른 대안**은 왜 안 됐나? (→ 6단 트레이드오프)
> 4. **현재의 한계**는 무엇이고, 다음 진화는?
> 5. **실제 코드/시스템**에서 어떻게 적용하고 어떻게 리팩토링하나? (→ 7단 운영 진단)

### 패러다임별 진화 다이어그램 컨벤션

각 챕터는 **자기 책임 영역의 시대별 변화**를 별도 그림으로 그린다.

| 챕터 | 시대별 그림 책임 영역 |
|---|---|
| **00-overview** | OOP 역사 타임라인 (Simula 1967 → Smalltalk 1972 → C++ 1985 → Java 1995 → Kotlin 2011) |
| **01-object-and-collaboration** | 객체 메타포 진화 (Alan Kay 생물학적 객체 → Java 데이터+메서드 객체 → DDD Aggregate) |
| **02-abstraction-and-encapsulation** | 다형성 구현 진화 (Smalltalk 메시지 디스패치 → C++ vtable → Java invokevirtual → Kotlin sealed) |
| **06-dependency-management** | DI 진화 (EJB heavy container → Spring XML → Spring annotation → Java config → Kotlin DSL) |
| **08-inheritance-vs-composition** | 코드 재사용 모델 (Java 단일상속+인터페이스 → Scala/Kotlin trait/mixin → Java default method) |
| **09-functional-paradigm** | FP 도입 타임라인 (LISP 1958 → Haskell 1990 → Java 8 lambda → Java 21 pattern matching) |
| **10-java-evolution** | Java 자체 진화 (Java 7 익명 클래스 → 8 lambda → 16 record → 17 sealed → 21 pattern) |
| **11-kotlin-paradigm** | Kotlin 설계 결정의 역사 (JetBrains 2010 결정 → 2016 1.0 → 2017 Android first-class) |

각 시대별 그림에는 **변화의 트리거(어떤 문제) + 핵심 개념 + 한계(다음 진화 트리거)** 를 함께 적는다.

---

## 1. 전체 학습 지도

### 의존 그래프

> 텍스트 트리 (SVG는 추후 `_diagrams/dependency-graph.svg`로 생성):

```
                       ┌──────────────────────┐
                       │   00. Overview        │  ← 시작점
                       │ (OOP는 왜 필요한가)    │
                       └──────────┬───────────┘
                                  │
                                  ▼
                       ┌──────────────────────┐
                       │ 01. Object & Collab  │  ← 조영호 1-2장: 객체/메시지/책임/협력
                       └──────────┬───────────┘
                                  │
                                  ▼
                       ┌──────────────────────┐
                       │ 02. Abstraction &     │  ← 조영호 5장: 캡슐화/다형성/상속
                       │    Encapsulation      │
                       └──────┬───────┬───────┘
                              │       │
                ┌─────────────┘       └─────────────┐
                ▼                                   ▼
       ┌──────────────────┐               ┌──────────────────┐
       │ 03. Responsibility│              │ 05. Object        │
       │    Assignment    │               │    Decomposition  │
       │ (GRASP)          │               │ (절차/데이터/객체) │
       └────────┬─────────┘               └──────────┬───────┘
                │                                    │
                ▼                                    │
       ┌──────────────────┐                          │
       │ 04. Message &     │                          │
       │    Interface     │                          │
       │ (Tell Don't Ask) │                          │
       └────────┬─────────┘                          │
                │                                    │
                └──────────────┬─────────────────────┘
                               ▼
                  ┌──────────────────────┐
                  │ 06. Dependency Mgmt   │  ← DIP / DI / IoC
                  └──────────┬───────────┘
                             ▼
                  ┌──────────────────────┐
                  │ 07. Flexible Design   │  ← SOLID / Design Patterns
                  └──────────┬───────────┘
                             ▼
                  ┌──────────────────────┐
                  │ 08. Inheritance vs    │
                  │    Composition       │
                  └──────────┬───────────┘
                             ▼
                  ┌──────────────────────┐
                  │ 09. Functional        │  ← OOP의 보완 패러다임
                  │    Paradigm          │
                  └──────────┬───────────┘
                             ▼
                  ┌──────────────────────┐
                  │ 10. Java Evolution    │  ← 람다/Record/Sealed/Pattern
                  └──────────┬───────────┘
                             ▼
                  ┌──────────────────────┐
                  │ 11. Kotlin Paradigm   │  ← Java를 넘어선 균형
                  └──────────┬───────────┘
                             ▼
                  ┌──────────────────────┐
                  │ 12. Spring &          │  ← OOP를 실제 운영 가능하게
                  │    Framework         │
                  └──────────┬───────────┘
                             │
                             │   ⭐ 보강 챕터 ⭐
                             │  ┌─────────────────────┐
                             │  │ 20. Ops Scenarios   │  ← 안티패턴/리팩토링 사례
                             │  ├─────────────────────┤
                             │  │ 21. Hands-on Workbook│ ← 조영호 영화 예매 등
                             │  ├─────────────────────┤
                             │  │ 22. Tradeoff Master │
                             │  └──────────┬──────────┘
                             ▼             ▼
                  ┌──────────────────────────┐
                  │ 🏁 30. Mock Interviews    │  ← 모든 챕터 통합
                  └──────────────────────────┘
```

**읽는 법**:
- **실선 의존**: 앞 챕터를 끝낸 후 다음으로 진입.
- **점선 의존**(20/21/22): 본 챕터의 운영·실습·비교를 다룬다 — 본 챕터 학습 후 진입.
- 03과 05는 어느 쪽 먼저 해도 OK.

### 챕터 목록

#### 📚 본 챕터 (이론 → 적용)

| # | 폴더 | 핵심 질문 | 상태 |
|---|---|---|---|
| 00 | [00-overview](./00-overview/) | "OOP가 뭐고, 왜 만들었고, 어떤 문제를 풀었나" | ⏳ |
| 01 | [01-object-and-collaboration](./01-object-and-collaboration/) | "객체는 무엇이고, 어떻게 협력하나 — 메시지/책임/역할" | ⏳ |
| 02 | [02-abstraction-and-encapsulation](./02-abstraction-and-encapsulation/) | "추상화/캡슐화/다형성/상속 — 4대 기둥의 본질과 JVM 구현" | ⏳ |
| 03 | [03-responsibility-assignment](./03-responsibility-assignment/) | "누구에게 책임을 줄 것인가 — GRASP 9원칙" | ⏳ |
| 04 | [04-message-and-interface](./04-message-and-interface/) | "Tell Don't Ask, Demeter, 인터페이스 설계의 원칙" | ⏳ |
| 05 | [05-object-decomposition](./05-object-decomposition/) | "절차 분해 vs 데이터 추상화 vs 객체지향 — 동일 문제를 셋이 어떻게 푸나" | ⏳ |
| 06 | [06-dependency-management](./06-dependency-management/) | "의존성의 종류, DIP, DI, IoC — Spring 이전과 이후" | ⏳ |
| 07 | [07-flexible-design](./07-flexible-design/) | "SOLID, OCP, 디자인 패턴 — 변경에 강한 설계" | ⏳ |
| 08 | [08-inheritance-vs-composition](./08-inheritance-vs-composition/) | "왜 'Composition over Inheritance'인가 — Effective Java 18조" | ⏳ |
| 09 | [09-functional-paradigm](./09-functional-paradigm/) | "OOP vs FP, 순수함수/불변성/고차함수가 OOP의 어떤 약점을 보완하나" | ⏳ |
| 10 | [10-java-evolution](./10-java-evolution/) | "Java 7→8→16→17→21 — 람다/Record/Sealed/Pattern, 왜 이 순서였나" | ⏳ |
| 11 | [11-kotlin-paradigm](./11-kotlin-paradigm/) | "Kotlin은 Java의 어떤 한계에 답했고, OOP/FP 균형을 어떻게 잡았나" | ⏳ |
| 12 | [12-spring-and-framework](./12-spring-and-framework/) | "Spring DI/AOP가 OOP 원칙을 어떻게 구현하나 — IoC 컨테이너 내부" | ⏳ |

#### 🎯 보강 챕터 (시니어/설계 권위자 수준 도달용)

| # | 폴더 | 핵심 질문 | 상태 |
|---|---|---|---|
| **20** | **[20-ops-scenarios](./20-ops-scenarios/)** | **"안티패턴 → 진단 → 리팩토링" 운영 시나리오. God Object, Anemic Domain, Feature Envy, Inheritance 남용, Spring 어노테이션 지옥 등** | ⏳ |
| **21** | **[21-hands-on-workbook](./21-hands-on-workbook/)** | **조영호 책의 영화 예매 시스템 + 요금제 청구 + 도메인 모델링 카타 직접 구현** | ⏳ |
| **22** | **[22-tradeoff-master-table](./22-tradeoff-master-table/)** | **cross-chapter 종합 비교: OOP vs FP / 상속 vs 합성 / Anemic vs Rich / Java vs Kotlin / DI 방식 4종** | ⏳ |

#### 🏁 종합

| # | 폴더 | 핵심 질문 | 상태 |
|---|---|---|---|
| 30 | [30-mock-interviews](./30-mock-interviews/) | "Junior/Senior/Principal 종합 면접 시나리오 + 즉석 도메인 모델링 시뮬레이션" | ⏳ |

---

## 2. 학습 순서 가이드 (16주 완전판)

> 12주로 압축도 가능하지만, "설계 권위자 수준" 목표라면 16주가 정직한 기간이다.
> 각 주차는 본 챕터 + 트레이드오프 표 + 코드 리팩토링 실습을 포함한다.

### Phase 1: 토대 (1~2주차)

**1주차: Overview (00번 챕터) — OOP가 왜 만들어졌나**
- Simula의 시뮬레이션 필요성 → Smalltalk의 생물학적 객체 모델 → C++의 정적 타입 객체 → Java의 JVM + 표준화
- 절차지향의 한계 사례 분석 (전역 변수 지옥, 데이터-함수 불일치)
- **실습**: 동일한 문제를 절차지향 C 코드와 Java OOP 코드로 작성 비교

**2주차: Object & Collaboration (01번) — 조영호 1~2장**
- 객체란 무엇인가, 클래스는 객체를 표현하는 도구일 뿐
- 메시지 우선 사고, 책임-주도 설계
- 역할/책임/협력 (RRC) 모델, CRC 카드
- **실습**: 영화 예매 시스템의 객체와 협력을 시퀀스 다이어그램으로 그리기

### Phase 2: 4대 기둥 (3~5주차)

**3주차: Abstraction & Encapsulation (02번)**
- 추상화 vs 캡슐화 — 자주 혼동되는 두 개념의 분리
- 다형성의 3종류 (Subtype, Parametric, Ad-hoc)
- 상속 vs 인터페이스 — 언제 무엇을 쓸 것인가
- **JVM 깊이**: `invokevirtual`, vtable, Inline Cache (JVM 챕터와 cross-reference)
- **실습**: `Comparable` vs `Comparator`, `instanceof` vs pattern matching 비교

**4주차: Responsibility Assignment (03번) — GRASP**
- 정보 전문가, 창조자, 컨트롤러, 낮은 결합도, 높은 응집도 등 9원칙
- 책임 할당의 안티패턴 (God Object, Anemic Domain)
- **실습**: Anemic Domain 코드를 Rich Domain으로 리팩토링

**5주차: Message & Interface (04번) — Tell Don't Ask**
- 인터페이스의 본질은 메시지 송수신 계약
- Demeter의 법칙, 디미터 위반 진단
- 좋은 인터페이스의 6가지 특성 (의도가 드러남, 사용 쉬움, 최소 노출 등)
- **실습**: `getter` chain 위반 코드를 `Tell` 방식으로 리팩토링

### Phase 3: 설계의 도구 (6~8주차)

**6주차: Object Decomposition (05번)**
- 절차 분해 (Functional Decomposition) — 한계 사례
- 데이터 추상화 (ADT) — Cargo Cult OOP의 함정
- 책임 기반 분해 (조영호식 OOP) — 가장 변경에 강한 방식
- **실습**: 동일한 ATM 시스템을 세 가지 방식으로 분해해 비교

**7주차: Dependency Management (06번)**
- 의존성의 종류 (Class, Method, Field, Inheritance, Generic 등)
- DIP — 추상화에 의존
- DI 방식 4종 (Constructor / Setter / Field / Method)
- Service Locator vs DI Container
- **실습**: Spring 없이 순수 Java로 IoC 컨테이너 직접 구현

**8주차: Flexible Design (07번) — SOLID + 패턴**
- SOLID 5원칙의 실제 코드 적용
- 변경의 종류와 각 SOLID 원칙의 매핑
- 핵심 패턴 (Strategy, Template Method, Observer, Decorator, Facade, Adapter)
- **실습**: 자주 변경되는 코드를 Strategy로 추출

### Phase 4: 상속의 함정 (9주차)

**9주차: Inheritance vs Composition (08번)** ⭐
- 상속의 4대 문제 (캡슐화 위반, 강한 결합, 다중 상속 불가, 깨지기 쉬운 기반 클래스)
- 합성/위임/Mixin/Trait — 대안의 스펙트럼
- Java/Kotlin/Scala의 mixin 비교
- **실습**: `extends` 남용 코드를 합성으로 리팩토링 + Lombok `@Delegate` 활용

### Phase 5: 함수형 통합 (10~11주차)

**10주차: Functional Paradigm (09번)** ⭐
- LISP에서 시작한 FP의 핵심 — 람다 칼큘러스, 참조 투명성
- 불변성/순수함수/고차함수가 OOP의 어떤 약점에 답하나
- Monad 입문 (Optional, Stream, CompletableFuture가 모두 monad)
- **실습**: 비순수 코드의 순수 영역 추출 (Functional Core, Imperative Shell)

**11주차: Java Evolution (10번)** ⭐
- Java 7 익명 클래스의 boilerplate → Java 8 lambda + Stream
- Java 8 `Optional`, `CompletableFuture`의 monadic 본질
- Java 14 switch expression, 16 record, 17 sealed → ADT 도입
- Java 21 pattern matching, virtual thread
- **실습**: Java 7 코드를 Java 21 표현식 기반으로 리팩토링

### Phase 6: Kotlin 균형 (12주차)

**12주차: Kotlin Paradigm (11번)** ⭐
- Kotlin이 Java의 어떤 결정을 뒤집었나 (Nullable, val/var, primary constructor 등)
- `data class` vs Java `record` — 6년의 시차
- `sealed class` + `when` — Pattern matching 원조
- 확장 함수, 스코프 함수, 위임 — Java에 없는 도구들
- Coroutine vs Virtual Thread — 동시성 모델 비교
- **실습**: 동일한 도메인을 Java/Kotlin으로 작성 비교

### Phase 7: 운영 가능한 OOP (13주차)

**13주차: Spring & Framework (12번)**
- Spring IoC 컨테이너 내부 (BeanDefinition, BeanFactory, ApplicationContext)
- DI 3 방식의 트레이드오프 (Constructor 권장 이유)
- Spring AOP의 프록시 메커니즘 (JDK Dynamic Proxy vs CGLIB)
- `@Transactional`의 함정 (private/self-invocation/Propagation)
- **실습**: Spring 어노테이션 없이 동일한 동작을 순수 Java로 구현

### Phase 8: 보강 — 안티패턴·실습·비교 (14~15주차) ⭐

**14주차: Ops Scenarios + Hands-on Workbook (20, 21번)** ⭐
- 빅테크 안티패턴 7대 사례 학습
- 조영호 영화 예매 시스템 직접 구현 (CRC → 클래스 → 시퀀스 → 코드)
- 요금제 청구 시스템 직접 구현
- 레거시 리팩토링 카타 (실제 GitHub 예제 사용)

**15주차: Tradeoff Master Table (22번)** ⭐
- OOP vs FP, 상속 vs 합성, Anemic vs Rich, DI 4방식, Java vs Kotlin
- 각 결정의 컨텍스트 (도메인 복잡도, 팀 성숙도, 변경 빈도 등)

### Phase 9: 종합 (16주차)

**16주차: Mock Interview (30번)** ⭐
- Junior/Senior/Principal 시나리오 풀이
- 즉석 도메인 모델링 (40분 안에 영화 예매 → CRC → 클래스 → 코드)
- "당신이 우아한기술블로그에 글을 쓴다면" 류의 글쓰기
- README 오프닝 문장을 자유롭게 풀어 설명할 수 있는지 자가 평가

---

## 3. 사용법

### 다이어그램 보기 / 편집

각 챕터의 `_excalidraw/` 폴더에는 두 형식의 파일이 들어간다.

| 형식 | 용도 |
|---|---|
| `*.svg` | md 파일에 인라인 임베드. GitHub/VSCode 미리보기에서 즉시 보임 |
| `*.excalidraw` | [excalidraw.com](https://excalidraw.com/)에서 "Open"으로 열어 직접 수정/확장 |

> **TIP**: 챕터를 처음 학습할 때는 SVG를 **보기 전에** 백지 그리기 가이드만 보면서 직접 그려본 다음, 정답 그림과 비교한다. 그래야 머리에 박힌다.

### 꼬리질문 활용

각 챕터 `_interview/` 폴더의 꼬리질문 트리는 **Q1만 보고 답을 만들어본 후** 예상 답안을 본다.
꼬리질문은 일부러 잔인하게 만들었다. 막혀도 정상이다.

### 코드 실습

각 챕터의 핵심 예제는 [21-hands-on-workbook](./21-hands-on-workbook/)에서 실제 Java/Kotlin 프로젝트로 구현.

---

## 4. 모드별 읽기 방식

| 모드 | 어떻게 읽나 |
|---|---|
| **학습 모드** | 7단 레이어를 순서대로, CRC 카드와 시퀀스 다이어그램을 직접 그리며 |
| **면접 복습 모드** | 각 챕터의 꼬리질문 트리만, 답을 떠올린 후 확인 |
| **코드 리뷰 모드** | 03(책임), 04(메시지), 06(의존성), 08(상속·합성), 20(안티패턴)을 cross-reference |
| **리팩토링 모드** | 20(시나리오)에서 시작, 해당 챕터의 4단·6단으로 진입 |

---

## 5. 진행 현황

### 본 챕터
- [x] README 작성 + 의존 그래프 + 용어 풀이 토글 (이 파일)
- [ ] 00-overview — OOP는 왜 만들어졌나
- [ ] 01-object-and-collaboration — 조영호 1~2장 기반
- [ ] 02-abstraction-and-encapsulation — 4대 기둥 + JVM 깊이
- [ ] 03-responsibility-assignment — GRASP
- [ ] 04-message-and-interface — Tell Don't Ask, Demeter
- [ ] 05-object-decomposition — 절차/데이터/객체 분해 비교
- [ ] 06-dependency-management — DIP, DI, IoC
- [ ] 07-flexible-design — SOLID, 디자인 패턴
- [ ] 08-inheritance-vs-composition — Effective Java 18조 풀버전
- [ ] 09-functional-paradigm — OOP/FP 보완 관계
- [ ] 10-java-evolution — Java 7→21 진화
- [ ] 11-kotlin-paradigm — JetBrains의 선택
- [ ] 12-spring-and-framework — IoC 컨테이너 내부

### 보강 챕터 ⭐
- [ ] 20-ops-scenarios — 안티패턴/리팩토링 사례집
- [ ] 21-hands-on-workbook — 조영호 예제 직접 구현
- [ ] 22-tradeoff-master-table — cross-chapter 종합 비교

### 종합
- [ ] 30-mock-interviews

> 이 파일은 학습 진행에 따라 계속 업데이트된다.

---

## 6. JVM 챕터와의 연계

이 OOP 가이드는 [../jvm/](../jvm/) 가이드와 cross-reference 되어야 한다.

| OOP 주제 | JVM 챕터 연결 |
|---|---|
| 다형성 / 다이내믹 디스패치 | jvm/03-execution-engine (Inline Cache, `invokevirtual`) |
| 람다 / `invokedynamic` | jvm/03-execution-engine + 01-class-lifecycle |
| Record / Sealed 바이트코드 | jvm/01-class-lifecycle (ClassFile 진화) |
| 가변 상태 / Memory Model | jvm/05-threading (happens-before) |
| Class Loading / Spring `@Component` 스캔 | jvm/01-class-lifecycle (ClassLoader) |
| GC와 불변 객체 / Escape Analysis | jvm/04-gc + 03-execution-engine |

→ 시니어 면접에서는 "이 OOP 개념의 JVM 구현은?" 류 꼬리질문이 거의 확실히 나온다.

---

## 7. 참고 문헌 (Required Reading)

### 한국어
- **조영호, 『오브젝트』** — 이 가이드의 1차 골격. 모든 챕터의 사고법.
- **조영호, 『객체지향의 사실과 오해』** — 객체/메시지/책임의 본질
- **마틴 파울러, 『리팩터링 2판』** — 안티패턴 진단·리팩토링

### 영어
- **Eric Evans, "Domain-Driven Design"** — 전략적/전술적 설계
- **Vaughn Vernon, "Implementing Domain-Driven Design"** — DDD 코드 구현
- **Joshua Bloch, "Effective Java 3rd"** — 18조 (상속 vs 합성), 22조 (인터페이스)
- **Robert Martin, "Clean Architecture"** — 의존성 규칙
- **Dmitry Jemerov, "Kotlin in Action"** — Kotlin 설계 철학

### 컨퍼런스/블로그
- 우아한기술블로그 — 도메인 모델링 시리즈
- 카카오 tech — 결제/메신저 도메인
- 토스 tech — 금융 시스템
- Netflix Tech Blog — MSA + DDD
- Martin Fowler refactoring.com
