# 01. Generics — Type Erasure의 진실

> "제네릭? `List<String>` 같이 타입 안전하게 쓰는 거" 라고 답하면 입문자.
> 시니어는 generics를 **컴파일러에게 받는 일회용 영수증**으로 본다. `javap -v`로 Signature attribute를 짚고, `ClassCastException`이 사용자가 쓴 cast가 아니라 **컴파일러가 자동 삽입한 invisible cast**에서 터졌음을 알아본다. PECS도 mnemonic이 아니라 **type system의 sound rule**임을 설명할 수 있어야 한다.

---

## 목차

1. WHY — 제네릭 도입 동기
2. WHAT — Type Erasure 본질
3. HOW — Signature attribute & Bridge method
4. 제약 — Erasure의 4가지 금지
5. PECS — 분산(Variance)
6. Java vs C#
7. 운영 시나리오
8. 꼬리질문

---

## 1. WHY — 도입 동기

Java 1.4 시대엔 모든 collection이 Object 기반. 사용자가 직접 `(String)` cast를 박았고, 그게 틀리면 런타임에 `ClassCastException`. 컴파일러는 침묵했다.

```java
// Java 1.4
List names = new ArrayList();
names.add("Alice");
names.add(42);                       // 컴파일 OK
String s = (String) names.get(2);    // 런타임 CCE
```

JDK 5 generics의 본질은 **타입 안전성을 컴파일 시점으로 끌어올린 것**.

```java
// JDK 5+
List<String> names = new ArrayList<>();
names.add(42);                  // 컴파일 에러
String s = names.get(0);        // cast 없음 — 컴파일러가 자동 삽입
```

핵심 인사이트: 사용자 코드에서 cast가 사라진 게 아니라 **컴파일러가 보이지 않게 끼워 넣는 invisible cast**로 옮긴 것. 이게 erasure, PECS, bridge method 같은 모든 결과의 출발점이다.

- Object 시대: "런타임에 검사" (defensive)
- Generic 시대: "컴파일에 증명" (proactive)

---

## 2. WHAT — Type Erasure

### 2.1 `<T>`는 컴파일 시점에만 존재한다

javac는 `<T>`를 `Object`로(bounded면 상한으로) 지운 bytecode를 만들고, 호출 지점마다 invisible cast를 삽입한다.

**규칙**:
- `<T>` → `Object`
- `<T extends Number>` → `Number`
- `<T extends A & B>` → `A` (첫 상한), 나머지는 cast로 처리

```java
class Box<T> {
    private T value;
    public T get() { return value; }
    public void set(T v) { this.value = v; }
}
```

```
$ javap -p Box.class
class Box {
  private java.lang.Object value;        // T가 Object로 erasure
  public java.lang.Object get();
  public void set(java.lang.Object);
}
```

`<T extends Number>`면 `Number value`, `double sum(Number)` 형태로 상한이 그대로 남는다.

### 2.2 Invisible cast — checkcast가 어디서 들어가나

```java
List<String> names = ...;
String s = names.get(0);
```

```
$ javap -c UseList.class
   invokeinterface List.get:(I)Ljava/lang/Object;
   checkcast       java/lang/String        ← 컴파일러가 자동 삽입
   astore_2
```

bytecode 레벨의 `List.get()`은 Object 반환. cast 자체는 사라지지 않았고, 호출 지점마다 컴파일러가 `checkcast`를 박는다.

### 2.3 결정적 증명 — 런타임 클래스는 하나

```java
new ArrayList<String>().getClass() == new ArrayList<Integer>().getClass()  // true
```

런타임의 JVM 입장에선 `ArrayList<String>`과 `ArrayList<Integer>`는 같은 Class 객체. 하위 호환성(JVM/ClassFile 변경 최소화, 1.4 코드와 5 코드 혼용) 때문에 reified 대신 erasure를 선택한 결과.

2004년 JDK 5 출시 시점, 기존 1.4 라이브러리/코드는 이미 운영 중인 시스템 수십만 개였다. 선택지는 (A) Reified — JVM 변경, ClassFile 포맷 변경, 기존 .class 호환 어려움. (B) Erased — JVM 변경 최소, 1.4와 5 코드를 한 프로그램에 섞을 수 있음. Java는 (B)를 골랐고, 그 결과가 erasure + Signature attribute + bridge method의 조합으로 나타났다.

```java
List<String> typed = new ArrayList<>();
List raw = typed;             // unchecked warning, 컴파일 OK
raw.add(42);                  // raw니까 통과
String s = typed.get(0);      // CCE — raw와 parameterized가 같은 런타임 타입이라는 증명
```

### 2.4 Raw type / Generic method / Bounded — 한 단락씩

**Raw type**: `List` 같이 타입 인자 없는 generic. JDK 5 이전 코드 호환을 위해 유지되지만 타입 검사를 우회해 heap pollution의 주범. `-Xlint:unchecked`로 경고 강제하고 신규 코드에선 금지가 정석.

**Generic method**: `<T> T pick(List<T> l)`처럼 메서드 단위 type parameter. 호출 지점의 인자 타입으로 T가 추론된다. target typing이 약한 컨텍스트에선 `Foo.<String>pick(list)`로 명시. JDK 8 이후 target typing이 강화되어 명시 필요 빈도는 크게 줄었다.

**Bounded type parameter**: `<T extends Number>`는 컴파일 시점에 `.doubleValue()` 등 Number 메서드 호출을 허용한다. 본질은 "T는 Number 이상"이라는 컴파일러 계약. erasure 후엔 그 상한이 그대로 남아 JIT도 약간의 최적화를 할 수 있다(상한 가정 inline cache).

**Heap pollution / `@SafeVarargs`**: varargs + generic 시 `T[] items`가 사실은 `Object[]`라 외부에서 Integer 넣을 수 있음. `@SafeVarargs`는 컴파일러가 검증하지 않는 작성자 선언일 뿐 — 작성자가 array를 외부에 노출하지 않고 read-only로 쓰면 안전, 노출하면 위험.

---

## 3. HOW — Signature attribute & Bridge

### 3.1 Signature attribute (한 줄 요약)

generic 원형 타입은 ClassFile의 **Signature attribute**(JDK 5에서 추가)에 별도 저장된다 — class/field/method 단위에 붙으며, JVM 실행에는 안 쓰이고, Reflection API와 cross-compile 호환성 검사 전용. **런타임에 generic 정보를 보존하는 유일한 위치**.

```
public T get();
  descriptor: ()Ljava/lang/Object;   ← JVM이 invoke 시 보는 것 (erased)
  Signature: ()TT;                   ← Reflection이 보는 것 (generic)
```

| | Descriptor | Signature |
|---|---|---|
| 누가 본다 | JVM (verify, link, invoke) | Reflection (`getGenericXxx`) |
| 형식 | erased (Object) | generic (`TT;`, `Ljava/util/List<...>;`) |
| 필수성 | 항상 | 있을 수도 없을 수도 |

### 3.2 Bridge method

generic 부모를 override하면 erasure로 시그니처가 어긋나 다형성이 깨진다. 컴파일러는 **bridge method**를 자동 합성해 해결한다.

```java
class Node<T> { public void set(T v) {} }            // erasure: set(Object)
class StringNode extends Node<String> {
    @Override public void set(String v) {}            // set(String)
}
```

`Node<T>` erasure 후 `set(Object)` 시그니처. `StringNode`의 override는 `set(String)` 시그니처. 둘은 bytecode 레벨에서 **다른 메서드**(descriptor `(Ljava/lang/Object;)V` vs `(Ljava/lang/String;)V`). `Node` 타입 변수로 `set(...)` 호출 시 JVM은 `set(Object)`를 찾는데 StringNode에는 `set(String)`만 있다 → 다형성 깨짐. 그래서 bridge가 들어간다:

```
$ javap -p -c StringNode.class
class StringNode extends Node {
  public void set(java.lang.String);    // 사용자 작성 override
  public void set(java.lang.Object);    // 컴파일러 합성 bridge
    Code:
       aload_0
       aload_1
       checkcast     String
       invokevirtual set:(Ljava/lang/String;)V    // 실제 메서드로 위임
       return
    flags: ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC
```

`Node`로 호출 → bridge 진입 → cast → 실제 `set(String)`에 위임. 사용자 코드에는 안 보이지만 stack trace에 가끔 line number 없이 나타난다. covariant return type(`Object get()` → `String get()`)도 같은 메커니즘으로 처리된다 — JDK 5에서 covariant return이 허용된 것 자체가 generic의 부산물.

### 3.3 Reflection으로 generic 잡기

`new ArrayList<String>()` 같은 생성자 호출은 ClassFile에 generic 정보를 남기지 않는다. **선언이 있어야 보존**된다. 그래서 Jackson `TypeReference`, Spring `ParameterizedTypeReference`, Guice `TypeLiteral`은 모두 **익명 subclass 트릭**으로 generic을 잡는다.

```java
abstract class TypeReference<T> {
    protected final Type type;
    protected TypeReference() {
        ParameterizedType pt = (ParameterizedType) getClass().getGenericSuperclass();
        this.type = pt.getActualTypeArguments()[0];   // 익명 subclass의 Signature에서 추출
    }
}

List<User> users = mapper.readValue(json, new TypeReference<List<User>>() {});
```

---

## 4. 제약 — Erasure의 4가지 금지

| 금지 | 이유 | 우회 |
|---|---|---|
| `new T[]` | 배열은 reified (component type 검사), T는 erased Object | `Object[]` + cast, `Arrays.newInstance(klass, n)`, `IntFunction<T[]>` generator |
| `o instanceof T` | T는 런타임에 Object — 검사가 무의미 | `Class<T>` 토큰 + `klass.isInstance(o)` |
| `T.class` | T가 Object → `Object.class`만 나옴 | `Class<T>` 토큰을 명시적으로 보유 |
| generic overload (`m(List<String>) / m(List<Integer>)`) | 둘 다 erasure 후 `m(List)` — 시그니처 충돌 | 메서드 이름 분리 또는 raw + `instanceof` |

`ArrayList`가 내부적으로 `Object[] elementData`를 들고 외부엔 generic으로 노출하는 게 첫 제약의 우회 사례. heap pollution이 발생하는 표면 — `toArray(T[] a)`처럼 호출자가 component type 토큰을 주는 메서드를 함께 제공해서 안전성을 회복한다.

**핵심 한 줄**: 배열은 reified, generic은 erased. 이 둘이 한 코드에 섞이면 거의 항상 문제가 생긴다.

---

## 5. PECS — 분산(Variance)

### 5.1 불공변이 기본인 이유

generic은 **불공변(invariant)**: `List<String>`은 `List<Object>`가 아니다. 허용하면:

```java
List<Object> objs = strs;     // 가상 — 허용된다 치자
objs.add(42);                  // List<Object>로 보니 OK
String s = strs.get(0);        // 런타임 CCE
```

Java 배열의 covariant 설계는 약점으로 평가되며(ArrayStoreException으로 런타임에 막을 뿐), generic은 더 sound한 invariant로 가고 wildcards로 분산을 표현한다.

### 5.2 PECS 다이어그램

```
                       T를 어떻게 쓰나?
                  ┌──────────┴──────────┐
              꺼낸다(Producer)        넣는다(Consumer)
                  ▼                     ▼
            ? extends T            ? super T
            (공변)                  (반공변)
            get: T OK              get: Object만
            add: null만            add: T 또는 subtype OK
```

| 표기 | get | add |
|---|---|---|
| `List<T>` | T | T 또는 subtype |
| `List<?>` | Object | null만 |
| `List<? extends T>` | T | null만 |
| `List<? super T>` | Object | T 또는 subtype |

### 5.3 정석 예 — Collections.copy

```java
public static <T> void copy(List<? super T> dest, List<? extends T> src) {
    //                       └─ Consumer ─┘       └─ Producer ─┘
    for (int i = 0; i < src.size(); i++) dest.set(i, src.get(i));
}
```

`copy(List<T>, List<T>)`였다면 dest와 src의 T가 같아야 했을 것. PECS로 `List<Number> dest`에 `List<Integer> src`를 복사할 수 있다.

Java 8 `Stream.map(Function<? super T, ? extends R>)`이 LSP의 함수 타입 적용 — Function의 input 위치는 반공변, output 위치는 공변. `Consumer<? super T>`, `Supplier<? extends T>`, `BiFunction<? super T, ? super U, ? extends R>` 모두 같은 패턴.

### 5.4 Raw vs `<?>`

raw `List`는 타입 안전성 자체를 우회(unchecked, heap pollution). `List<?>`는 안전성 유지(null 외 add 불가). 옛 라이브러리 호환이 아니라면 raw는 절대 쓰지 않는다.

```java
List raw = new ArrayList<String>();
raw.add(42);               // 컴파일 OK — heap pollution

List<?> any = new ArrayList<String>();
any.add(42);               // 컴파일 에러
```

`?`는 "타입을 모름 + 안전성 보호"고 raw는 "타입 안전성 자체를 포기". 사용 의도가 명확히 다르다.

---

## 6. Java vs C# (진화 + 비교)

JDK 5 도입 이후의 generic 진화는 짧게: JDK 7 diamond(`new HashMap<>()`)로 우변 타입 생략, JDK 8 target typing 강화 + Stream/Lambda의 PECS 시그니처 정착, JDK 14+ Record / JDK 17 Sealed는 generic + pattern matching의 새 표면. JDK 21+ `case List<?> list ->`는 가능하지만 `case List<String> ->`는 erasure 때문에 여전히 불가. generic + pattern matching의 한계는 erasure가 원인.



| 항목 | Java | C# |
|---|---|---|
| 메커니즘 | Erasure | Reification |
| 런타임 타입 정보 | 없음 | 있음 (`typeof(T)`) |
| `new T()` | 불가 | `where T : new()` |
| `instanceof T` | 불가 | `obj is T` |
| Primitive | autobox (`List<Integer>`) | 직접 (`List<int>`) |
| 하위 호환 | 1.4 코드와 혼용 가능 | .NET 1.x 호환 일부 깸 |
| 메모리 | 단일 Class | T마다 별도 |
| 런타임 변경 | 최소 (javac만) | 큼 (CLR) |

Java는 2004년 1.4의 수억 줄 호환성 때문에 erasure를 택했고, C#은 1.x 출시 직후라 reification을 택했다. 둘 다 각자의 제약에서 최선. Java의 결정은 "JVM 변경 최소, 1.4와 5 코드가 한 프로그램에 섞일 수 있어야 함"이 절대 요구사항이었기 때문.

Project Valhalla(value types, primitive generics)로 Java도 점진적으로 reified의 일부를 가져오는 중 — 결국 reified가 더 좋다는 인정. universal generics 마이그레이션 전략으로 기존 erased와 신규 reified를 한 코드에서 섞을 수 있게 하는 게 핵심 난제. JDK 25/27 LTS 진입 예상이며 단기 영향은 거의 없고(opt-in), 중장기로는 거대 컬렉션 메모리/캐시 효율 개선, `Stream<int>`로 IntStream 통합, JFR/profiler에서 generic 정보 정확 표시 등의 효과가 예상된다.

---

## 7. 운영 시나리오

### 7.1 `(String) cast`가 한 줄 위에 없는 CCE

```
ClassCastException: class java.lang.Integer cannot be cast to class java.lang.String
    at com.foo.UserService.getName(UserService.java:42)
```

42번 줄을 보면 `String name = users.get(i).getName();`처럼 cast가 안 보인다. 범인은 **컴파일러가 자동 삽입한 checkcast**. erasure로 `get()`은 Object를 반환하고, 호출 지점에 invisible cast가 들어가 있다.

**진단 순서**:
1. 그 줄에 cast가 안 보임 → erasure로 생긴 invisible checkcast가 터진 것.
2. 어디서 Integer가 들어갔나? `javap -c`로 호출 흐름 추적, `users` 리스트의 출처를 거슬러 올라간다.
3. 흔한 범인 — (a) raw type 통과: `List rawList = ...; rawList.add(integer);` 후 generic 변수로 reassign. (b) Reflection `Method.invoke`로 타입 검사 우회. (c) `@SuppressWarnings("unchecked")`로 가린 cast가 잘못된 타입을 통과시킴. (d) 외부 1.4 호환 라이브러리의 raw 리턴. (e) Jackson/Gson이 generic 토큰 없이 deserialize.

**대응**:
- raw type 제거, generic 명시.
- 외부 입력 경로는 `Class<T>` 토큰 또는 `TypeReference` 받기.
- 빌드에 `-Xlint:unchecked -Werror`로 warning을 컴파일 실패로 강제.
- 의심 컬렉션은 사용 전 `Collections.checkedList(list, String.class)`로 wrap — store-time 검사를 강제해 사고 지점을 add 시점으로 옮긴다. fail-fast가 핵심: 잘못된 element가 들어간 즉시 터지면 stack trace로 범인 추적이 즉시 가능. erasure가 가린 사고 지점을 강제로 드러내는 운영 기법.

### 7.2 Jackson `@RequestBody List<User>`가 LinkedHashMap

```java
@PostMapping
public void create(@RequestBody List<User> users) {
    User first = users.get(0);   // CCE — 실제론 LinkedHashMap
}
```

Jackson은 generic 정보 없이 deserialize하면 기본 객체(LinkedHashMap)로 만든다. Spring은 메서드 파라미터의 `ParameterizedType`을 `MethodParameter` 통해 Jackson에 전달해서 보통은 OK인데, 다음 경우에 정보가 손실된다:

- 중간에 raw `List` / `Map`을 거친 wrapper 메서드.
- `@RequestBody` 대신 `HttpEntity<List<User>>` 같은 generic-of-generic을 거쳐 잘못 처리.
- 직접 `ObjectMapper.readValue(json, List.class)`처럼 Class 토큰만 전달.

**해결**:
- `ObjectMapper.readValue(json, new TypeReference<List<User>>() {})`로 명시.
- Spring 내부 호출은 `ParameterizedTypeReference<List<User>>` 사용.
- 가장 단단한 방법은 wrapper DTO(`class UserList { List<User> items; }`)로 받기 — generic이 ClassFile 선언에 박혀 Signature attribute로 보존된다.

증상이 production에서만 보이고 통합테스트에서 안 잡히는 이유는 컨트롤러 직통 테스트와 달리 raw map 경유 코드가 통합 환경에서만 활성화되는 경우가 많기 때문. `MockMvc`로 컨트롤러 직접 호출은 generic 보존되지만 `RestTemplate`/`WebClient` 경유로 다른 인스턴스에서 받을 때 정보가 사라진다.

### 7.3 JIT 관점의 generic — checkcast가 정말 비싼가

JIT은 generic을 모른다. `List.get`은 늘 Object 반환. 호출 지점의 checkcast는 별도 명령으로 들어있고, **monomorphic inline cache**(같은 호출 지점이 같은 타입만 보면)로 sub-nanosecond까지 최적화된다.

```
$ java -XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining MyApp
@ 12   Service::process (15 bytes)   inline (hot)
  @ 5   ArrayList::get (5 bytes)     inline (hot)
  @ 9   checkcast java/lang/String   ← inline 처리됨
```

erasure는 런타임 비용 거의 안 만든다. 단, **호출 지점이 megamorphic이 되면(여러 element 타입이 같은 callsite로 들어오면) inline cache가 풀려 cast 비용이 살아난다**. 흔한 사례:

- 공통 utility(`Collectors.toList`, 범용 mapper)에 다양한 element 타입이 흘러 들어가 callsite가 polymorphic 4 이상으로 bump.
- p99 latency가 갑자기 튀고 `-XX:+PrintInlining`에 `not inlineable: callee uses too much stack` 또는 `too many types` 로그.
- JFR profile에서 `checkcast` 또는 `instanceof` opcode가 hot으로 표시.
- C2가 hot callsite에 type guard를 박는데 guard 실패가 잦아 deoptimization 빈도 증가.

대응은 hot path 분리(타입별 전용 메서드), `@HotSpotIntrinsicCandidate` 호출의 wrap 제거, 캐스트가 stable한 위치로 옮기기. 일반 비즈니스 코드에선 거의 무시 가능 — 단 latency-sensitive critical path 1~2곳에서만 의식한다.

---

## 8.0 학습 체크리스트

면접 전 백지에서 다음을 줄줄 그릴 수 있어야 마스터:

- 루트 한 문장: "제네릭은 컴파일 시점에만 존재. javac가 erasure + Signature attribute + invisible cast + bridge로 구현. 런타임 JVM은 generic을 거의 모름."
- `<T>` / `<T extends X>` erasure 규칙, `javap -p`로 확인되는 모양.
- Descriptor vs Signature, Reflection이 generic을 보는 경로.
- Bridge method 생성 조건과 `ACC_BRIDGE | ACC_SYNTHETIC` flag, covariant return type 연결.
- 4 제약(`new T[]`, `instanceof T`, `T.class`, generic overload) 각각의 본질.
- 불공변 기본 이유와 PECS의 sound rule 근거.
- Java vs C# 8요소 비교, Valhalla의 두 축.
- 운영 시나리오 — invisible checkcast CCE 진단, Jackson LinkedHashMap, JIT megamorphic.

---

## 8. 꼬리질문

**Q1. `List<String>`과 `List<Integer>`는 같은 클래스인가?**
> 네. `getClass()`가 동일한 Class 객체 — `strs.getClass() == ints.getClass()`가 true. erasure로 둘 다 `java.util.ArrayList`. 다만 ClassFile Signature attribute에는 각각의 generic이 보존되어 Reflection(특히 선언된 위치)에서 보인다. 그래서 `new ArrayList<String>()` 생성자는 정보 손실되지만, `class UserList extends ArrayList<User> {}`나 익명 subclass는 generic이 박힌다.

**Q2. Reflection으로 `List<String>`에 Integer 넣을 수 있나?**
> 네. raw type 또는 `Method.invoke`로 가능. erasure 때문에 add 시점엔 검사가 없고, 꺼낼 때 컴파일러가 삽입한 `checkcast`에서 CCE가 터진다 — 이게 heap pollution. JDK 5의 backward-compatible 도입을 위한 의도된 타협이며 컴파일러는 unchecked warning으로만 알린다. `Collections.checkedList(list, String.class)`로 wrap하면 add 시점 검사를 강제할 수 있다.

**Q3. Bridge method는 stack trace에 보이나?**
> 가끔. `at StringNode.set(StringNode.java)`처럼 line number 없이 클래스+메서드만 찍히면 bridge일 가능성. `ACC_BRIDGE | ACC_SYNTHETIC` flag, line table 없음. covariant return type(`Object get()` → `String get()`)도 같은 메커니즘으로 bridge 생성 — JDK 5의 covariant return 허용 자체가 generic의 부산물. Mockito가 generic override를 mock할 때 bridge를 잘못 잡아 invocation이 두 번 기록되는 사고도 있다.

**Q4. `new T[]`이 안 되는 본질적 이유는?**
> 배열은 reified — 런타임에 component type을 알아야 ArrayStoreException으로 store-time 검사. T는 erased Object라 component type 불명. `ArrayList`처럼 내부 `Object[]` + cast로 우회하거나, `IntFunction<T[]>` generator 패턴(`stream.toArray(String[]::new)`)으로 호출자가 토큰을 주는 방식. `Arrays.newInstance(klass, n)`도 Class<T> 토큰을 받는 같은 원리.

**Q5. PECS가 왜 그렇게 외쳐지나?**
> mnemonic이 아니라 **type system sound rule**. `? extends T`는 무엇이 채웠든 T 이상이라 꺼내는 건 안전, 넣는 건 정확한 타입을 몰라 null 외 불가. `? super T`는 T 이상의 그릇이라 넣는 건 안전, 꺼내는 건 Object만 보장. LSP의 함수 타입 적용 — Function의 input 위치는 contravariant, output 위치는 covariant. `Stream.map(Function<? super T, ? extends R>)`가 이 원칙을 따른 표준 시그니처. API 설계 시 매개변수는 가급적 `? super T` / `? extends T`로 열어 호출자가 더 유연한 collection을 넘길 수 있게 하는 게 정석.

---

## 9. 다음 단계

이 챕터의 핵심: **generic은 컴파일러에게 받는 일회용 영수증**. 런타임에 들고 갈 수 없다. 런타임에 타입 정보가 정말 필요하면 Reflection으로 ClassFile 메타데이터를 읽는다 — Signature attribute도 reflection을 통해서만 보인다. 단 reflection은 비싸다(method lookup, security check, access check 매번). 다음은 [02-reflection.md](./02-reflection.md): Reflection 내부 동작, MethodHandle과의 차이, Dynamic Proxy/CGLIB 메커니즘.

---

## 참고

- JLS §4.6 Type Erasure
- JVMS §4.7.9 Signature Attribute
- JLS §8.4.5 Bridge Methods
- Naftalin & Wadler — *Java Generics and Collections*
- Project Valhalla — JEP 401 / 402

---

Signature attribute byte layout, bridge method bytecode, C# reified와 ABI 비교, Valhalla LW2/3는 git 7e4a6c8 참조.
