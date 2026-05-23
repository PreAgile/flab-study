# 01. Generics — Type Erasure의 진실

> "제네릭? `List<String>` 같이 타입 안전하게 쓰는 거" 라고 답하면 입문자.
> 시니어가 제네릭을 안다는 건 **컴파일러에게 받는 일회용 영수증**임을 알고, `javap -v`로 `Signature` attribute를 짚어내며, `ClassCastException`이 한 줄 위쪽의 `(String)` 캐스트가 아니라 **컴파일러가 자동 삽입한 invisible cast**에서 터졌음을 알아본다. PECS도 "외우는 mnemonic"이 아니라 **타입 시스템의 sound rule**임을 설명할 수 있어야 한다.
> 이 문서는 byte offset과 옵션값을 외우지 않는다. 어떤 generics 지식이 어떤 production 문제를 푸는지만 매핑한다.

---

## 이 문서의 사용법

면접용 마인드맵을 선형으로 펼친 구조다. 학습 순서 = 면접 답변 순서 = 백지에 그리는 순서.

1. **0장 마인드맵을 먼저 외운다** — 루트 한 문장 + 6가지 가지 + 각 가지 키워드 3개.
2. **1~6장을 순서대로 학습** — 각 장이 마인드맵의 한 가지에 대응.
3. **7장 면접 워크플로우로 검증**.
4. **8장 꼬리질문 트리로 깊이 점검**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"제네릭은 컴파일 시점에만 존재하는 타입 안전 도구다. javac는 type erasure로 `<T>`를 지운 bytecode를 만들고, `Signature` attribute에 원형 타입을 별도 저장하며, 필요한 곳에 invisible cast와 bridge method를 끼워 넣는다. 런타임의 JVM은 generic을 거의 모른다."**

이 한 문장에서 모든 답변이 출발한다.

### 6개 가지 — 순서를 외운다

```
                [ROOT: Generics = compile-time only, erasure + Signature]
                                  │
       ┌──────────┬───────────────┼───────────────┬──────────┬──────────┐
       │          │               │               │          │          │
      ① WHY     ② WHAT          ③ HOW           ④ 제약      ⑤ 분산      ⑥ 진화
   JDK 5 도입  Erasure 본질    Signature/Bridge  4가지 금지  PECS/Wildcard JDK 5→17
       │          │               │               │          │          │
       │     ┌────┼────┐      ┌───┼───┐       ┌───┼───┐      │          │
   Object캐스트  T→Object       ClassFile  new T[] 불공변  diamond
   ClassCast    bounded→상한    Bridge   instanceof? extends Java vs C#
   1.4시대      raw type       Reflection T.class ? super  Valhalla
                                          overload Liskov
```

### 가지별 핵심 키워드

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① WHY JDK 5 도입** | Object 기반 cast 시대 | 사용자 코드에서 cast 제거 | ClassCastException 사전 방지 |
| **② WHAT Erasure** | `<T>` → Object | bounded → 상한 타입 | raw type = backward compat |
| **③ HOW Signature/Bridge** | ClassFile Signature attribute | Bridge method 자동 생성 | Reflection getGenericXxx |
| **④ 제약 4가지** | `new T[]` 불가 | `instanceof T` / `T.class` 불가 | overload 충돌 |
| **⑤ PECS/Wildcard** | 불공변(invariant) 기본 | `? extends T` Producer | `? super T` Consumer |
| **⑥ 진화** | JDK 5 도입 | JDK 7 diamond / JDK 8 target typing | Java vs C# / Valhalla |

### 면접 답변 흐름

> 질문 → 루트 문장 → 가지 1개 선택 → 그 가지 키워드 3개 → 인접 가지로 확장

---

## 1. 가지 ①: WHY — 왜 제네릭이 생겼나

### 1.1 핵심 질문

> "제네릭이 없었을 때는 어떻게 했나? 무엇이 불편해서 JDK 5에서 도입됐나?"

### 1.2 키워드 1 — Object 기반 cast 시대 (Java 1.4 이전)

```
// Java 1.4: 모든 collection이 Object 기반
List names = new ArrayList();
names.add("Alice");
names.add("Bob");
names.add(42);             // ★ 컴파일 OK. Object니까 뭐든 들어감
                            //   런타임에도 OK. 사고는 꺼낼 때 터짐

String s = (String) names.get(2);   // ClassCastException at runtime!
```

**문제 본질**:

```
타입 정보가 코드 어디에도 명시되지 않음
       ↓
컴파일러가 잘못된 사용 발견 불가
       ↓
런타임에 ClassCastException
       ↓
사용자가 매번 (String) 캐스트를 직접 박아야 함
       ↓
캐스트는 "내가 책임진다"는 선언 — 컴파일러는 침묵
```

### 1.3 키워드 2 — 사용자 코드에서 cast 제거

JDK 5의 generics 도입의 표면적 동기:

```java
// JDK 5+
List<String> names = new ArrayList<>();
names.add("Alice");
names.add(42);   // ★ 컴파일 에러: incompatible types

String s = names.get(0);  // 캐스트 없음. 컴파일러가 자동으로 끼워줌
```

핵심 인사이트: **사용자 코드에서 cast는 사라졌지만 cast 자체가 사라진 게 아니다**. 컴파일러가 보이지 않게 끼워 넣을 뿐. (→ 가지 ② 참조)

### 1.4 키워드 3 — ClassCastException 사전 방지

```
JDK 1.4:
   사용자 코드: ArrayList → 직접 cast → 런타임 검사 → CCE 가능
   컴파일러: "난 모르겠다. 너 책임"

JDK 5+:
   사용자 코드: List<String> → cast 안 보임
   컴파일러: "타입 추적해보니 너 안전. cast 자동 삽입"
   결과: 컴파일 에러는 늘었고 런타임 CCE는 거의 사라졌다
```

**철학의 전환**:
- Object 시대: "런타임에 검사" (defensive)
- Generic 시대: "컴파일에 증명" (proactive)

→ **타입 안전성을 컴파일 시점으로 끌어올림**. 이것이 generics의 본질이고, 모든 결과(erasure, PECS, bridge method)는 이 목표를 위한 trade-off.

---

## 2. 가지 ②: WHAT — Type Erasure의 본질

### 2.1 핵심 질문

> "`List<String>`은 ClassFile에 어떻게 저장되나? 런타임에 String은 어디 갔나?"

### 2.2 키워드 1 — `<T>` → Object로 지워진다

```java
// 사용자 코드
class Box<T> {
    private T value;
    public T get() { return value; }
    public void set(T v) { this.value = v; }
}
```

javac의 출력 (bytecode 레벨):

```java
// 컴파일러가 실제로 ClassFile에 박는 모양 (개념)
class Box {
    private Object value;
    public Object get() { return value; }
    public void set(Object v) { this.value = v; }
}
```

```
$ javap -p -c Box.class

class Box {
  private java.lang.Object value;        // ★ T가 Object로 erasure

  public Box();
  public java.lang.Object get();         // ★ 반환 타입 Object
  public void set(java.lang.Object);     // ★ 파라미터 Object
}
```

### 2.3 키워드 2 — Bounded는 상한으로 erasure

```java
class NumberBox<T extends Number> {
    public T value;
    public double sum(T other) { return value.doubleValue() + other.doubleValue(); }
}
```

```
$ javap -p NumberBox.class

class NumberBox {
  public java.lang.Number value;                    // ★ T extends Number → Number
  public double sum(java.lang.Number);              // ★ 파라미터도 Number
}
```

**규칙**:
- `<T>` → `Object`로 erasure.
- `<T extends X>` → `X`로 erasure (상한이 그대로 남음).
- `<T extends X & Y>` → 첫 번째 상한(`X`)으로 erasure. 나머지는 cast로 처리.

### 2.4 키워드 3 — 호출 지점에 invisible cast 삽입

`names.get(0)`이 String을 돌려주는 마법은 컴파일러가 cast를 끼워 넣기 때문.

```java
// 사용자 코드
List<String> names = ...;
String s = names.get(0);
```

```
$ javap -c UseList.class
   ...
   invokeinterface #X //InterfaceMethod List.get:(I)Ljava/lang/Object;
   checkcast       #Y // class java/lang/String   ★ 컴파일러가 자동 삽입
   astore_2
```

**의미**:
- bytecode 레벨에서 `List.get()`은 `Object`를 반환.
- 컴파일러가 호출 지점마다 `checkcast` 명령을 자동 삽입.
- 따라서 `String s = list.get(0)`이 자연스럽게 보임.
- 그러나 **cast 자체는 사라지지 않았다**. 다만 사용자가 안 쓸 뿐.

### 2.5 왜 erasure를 채택했나 — 하위 호환성

```
2004년 JDK 5 출시 시점:
  - 기존 Java 1.4 라이브러리/코드는 이미 운영 중인 시스템 수십만 개
  - 새 generics 도입하면서 "기존 코드 동작 보장" 필수
  - JVM 자체는 변경 최소화 (bytecode 호환성)

선택지:
  A. Reified Generics (런타임에 타입 정보 보존)
     → JVM 변경, ClassFile 포맷 변경, 기존 .class 호환 어려움
  B. Erased Generics (컴파일 시점만)
     → JVM 변경 최소, 기존 1.4 코드와 섞어 써도 동작
```

**결과**: JVM은 거의 그대로, javac만 똑똑해짐. 1.4 시대의 `List`도 JDK 5의 `List<String>`도 같은 `List` Klass로 통합. 다음 코드가 그 증거.

```java
List<String> typed = new ArrayList<>();
List raw = typed;   // ← unchecked warning이지만 컴파일 됨
raw.add(42);        // ← raw니까 OK
String s = typed.get(0);  // ★ ClassCastException
```

→ raw와 parameterized가 같은 런타임 타입이라는 직접 증명.

### 2.6 결정적 증명 — Class 객체가 같다

```java
List<String> strs = new ArrayList<>();
List<Integer> ints = new ArrayList<>();
System.out.println(strs.getClass() == ints.getClass());   // true
System.out.println(strs.getClass().getName());            // java.util.ArrayList
```

**런타임 JVM의 관점에서 `ArrayList<String>`과 `ArrayList<Integer>`는 같은 클래스다**. 이게 erasure의 핵심 결과.

---

## 3. 가지 ③: HOW — Signature attribute와 Bridge Method

### 3.1 핵심 질문

> "런타임에 generic 정보가 완전히 사라진다면 Reflection으로 어떻게 generic을 알아낼 수 있나?"

### 3.2 키워드 1 — ClassFile의 Signature attribute (JDK 5+ 추가)

erasure로 `Box<T>`가 `Box`가 된다면 generic 정보는 어디로 갔나? **ClassFile의 별도 attribute에 보존된다.**

```
ClassFile {
    u4              magic;
    u2              minor_version;
    u2              major_version;
    u2              constant_pool_count;
    cp_info         constant_pool[];
    u2              access_flags;
    u2              this_class;
    u2              super_class;
    u2              interfaces_count;
    u2              interfaces[];
    u2              fields_count;
    field_info      fields[];     ←─── each field can have Signature attribute
    u2              methods_count;
    method_info     methods[];    ←─── each method can have Signature attribute
    u2              attributes_count;
    attribute_info  attributes[]; ←─── class itself can have Signature attribute
}
```

**Signature attribute의 위치**:
- 클래스 단위 (class-level attributes) — `class Box<T>` 같은 generic class declaration
- 필드 단위 (field_info attributes) — `T value` 같은 generic field
- 메서드 단위 (method_info attributes) — `T get()` 같은 generic method signature

**예시 출력**:
```
$ javap -v Box.class
...
public class Box<T>
  Signature: #15                    // <T:Ljava/lang/Object;>Ljava/lang/Object;
                                     // ★ class-level: T는 Object 상한
public T get();
  descriptor: ()Ljava/lang/Object;   // ★ erased descriptor (JVM이 보는 것)
  Signature: #20                    // ()TT;
                                     // ★ generic signature (Reflection이 보는 것)
```

**핵심 분리**:

| | Descriptor | Signature |
|---|---|---|
| 누가 본다 | JVM (verify, link, invoke) | Reflection API (`getGenericReturnType` 등) |
| 어디에 | method_info 본체 | 별도 attribute |
| 형식 | erased (Object) | generic (`TT;`, `Ljava/util/List<Ljava/lang/String;>;`) |
| 필수성 | 항상 있어야 함 | 있을 수도 없을 수도 |

### 3.3 키워드 2 — Bridge Method 자동 생성

generic 메서드를 override할 때 erasure로 시그니처가 어긋나는 문제가 생긴다. 컴파일러는 **bridge method**를 자동 생성해 해결한다.

**상황**:
```java
class Node<T> {
    public void set(T value) { /* ... */ }
}

class StringNode extends Node<String> {
    @Override
    public void set(String value) { /* ... */ }
}
```

**문제**:
- `Node<T>` erasure → `Node`의 `set` 시그니처는 `set(Object)`.
- `StringNode`의 `set`은 `set(String)`.
- bytecode 레벨에서 **두 메서드는 다른 시그니처** (descriptor `(Ljava/lang/Object;)V` vs `(Ljava/lang/String;)V`).
- 그러면 다형성이 깨진다 (Node 타입 변수로 호출하면 set(Object)를 찾는데 StringNode엔 없음).

**해결 — bridge method**:
```
$ javap -p -c StringNode.class

class StringNode extends Node {
  public void set(java.lang.String);       // ★ 사용자가 작성한 override
  public void set(java.lang.Object);       // ★ 컴파일러가 합성한 bridge
    Code:
       0: aload_0
       1: aload_1
       2: checkcast     #X  // class java/lang/String
       5: invokevirtual #Y  // Method set:(Ljava/lang/String;)V    ★ 사용자 메서드로 위임
       8: return
    flags: ACC_PUBLIC, ACC_BRIDGE, ACC_SYNTHETIC
```

**Bridge method의 본질**:
- `ACC_BRIDGE` + `ACC_SYNTHETIC` flag로 표시.
- `Node.set(Object)` 호출 시 → bridge에 진입 → cast 후 실제 `set(String)`으로 위임.
- 사용자 코드에는 안 보이지만 stack trace에 가끔 나타남.

### 3.4 키워드 3 — Reflection으로 generic 정보 얻기

```java
class Container extends ArrayList<String> { }

Container c = new Container();

// 1. erased class — generic 안 보임
Class<?> klass = c.getClass();
System.out.println(klass.getSuperclass());          // class java.util.ArrayList ★ erased

// 2. generic superclass — Signature attribute를 읽어서
Type t = klass.getGenericSuperclass();
System.out.println(t);                              // java.util.ArrayList<java.lang.String> ★

// 3. ParameterizedType으로 캐스트
ParameterizedType pt = (ParameterizedType) t;
Type[] args = pt.getActualTypeArguments();
System.out.println(args[0]);                        // class java.lang.String
```

**왜 `new ArrayList<String>()`의 String은 못 얻나?**

```java
ArrayList<String> list = new ArrayList<>();
list.getClass().getGenericSuperclass();   // ★ AbstractList<E>
                                          //   String 정보 없음
```

이유: `new ArrayList<String>()`은 **생성자 호출**일 뿐. ClassFile은 변경되지 않음. Signature attribute는 **declared 타입**에만 있다.

→ **선언이 있어야 보존된다**. 변수 타입(`List<String> list`)이나 method 파라미터의 generic은 호출 지점이라 정보 없음.

### 3.5 TypeToken / TypeReference 패턴

위 한계 때문에 Jackson, Guice 등 라이브러리는 **anonymous subclass 트릭**으로 generic 정보를 잡는다.

```java
// Jackson
ObjectMapper mapper = new ObjectMapper();
List<User> users = mapper.readValue(json, new TypeReference<List<User>>() {});
//                                          ★ anonymous subclass! ↑

// 동작 원리:
//   new TypeReference<List<User>>() {} — 익명 subclass 생성
//   subclass의 ClassFile에는 "extends TypeReference<List<User>>" Signature 박힘
//   TypeReference 생성자가 this.getClass().getGenericSuperclass()로 추출
```

```java
abstract class TypeReference<T> {
    protected final Type type;
    protected TypeReference() {
        ParameterizedType pt = (ParameterizedType) getClass().getGenericSuperclass();
        this.type = pt.getActualTypeArguments()[0];
    }
}
```

→ "generic 정보를 보존하려면 named declaration이 필요"를 우회하는 일반적 패턴. Guice의 `TypeLiteral`, Spring의 `ParameterizedTypeReference`도 같은 원리.

---

## 4. 가지 ④: 제약 — Erasure가 만드는 4가지 금지

### 4.1 핵심 질문

> "왜 `new T[]`는 컴파일 에러인가? `instanceof T`는 왜 안 되나?"

### 4.2 키워드 1 — `new T[]` 불가 (배열은 reified)

```java
class Bag<T> {
    private T[] arr = new T[10];   // ★ 컴파일 에러
}
```

**왜?**
```
배열은 런타임에 자기 component type을 안다 — reified.
  - String[]은 storeStore에 String 외 객체 넣으면 ArrayStoreException
  - 이 검사를 위해 런타임에 component class를 유지해야 함

T는 런타임에 Object — erased.
  - T[]을 만들려면 component class를 알아야 하는데 T는 Object일 뿐
  - 결과: type-safe 배열 만들 수 없음
```

**우회법**:
```java
@SuppressWarnings("unchecked")
T[] arr = (T[]) new Object[10];   // ★ runtime은 Object[]지만 컴파일 cast로 속임
```

이건 **위험하다**. `arr`를 외부에 `String[]`로 노출하면 store 시 ArrayStoreException 안 터지고, get 시 cast로 CCE 발생. 그래서 `ArrayList`는 내부적으로 `Object[]`를 쓰고 외부에 generic 타입으로만 노출한다.

```java
// ArrayList.java
transient Object[] elementData;   // ★ 사실 Object[]이다

public E get(int index) {
    return (E) elementData[index];   // ★ 캐스트로 보여줌
}
```

### 4.3 키워드 2 — `instanceof T` 불가

```java
class Validator<T> {
    boolean check(Object o) {
        return o instanceof T;   // ★ 컴파일 에러
    }
}
```

**왜?**
- `instanceof`는 런타임에 객체의 실제 클래스를 type과 비교.
- T는 런타임에 Object일 뿐.
- "o가 Object인가?" 검사는 무의미 (모든 객체가 Object).

**우회법**: Class<T> 토큰을 받기.
```java
class Validator<T> {
    private final Class<T> klass;
    Validator(Class<T> klass) { this.klass = klass; }
    boolean check(Object o) {
        return klass.isInstance(o);   // ★ Class.isInstance는 reflection 기반
    }
}
```

### 4.4 키워드 3 — `T.class` / 같은 메서드 generic overload 불가

**`T.class` 불가**:
```java
class Holder<T> {
    Class<T> klass() {
        return T.class;   // ★ 컴파일 에러
    }
}
```

T가 런타임에 Object → `Object.class`만 알 수 있음. 의미 없음.

**Generic overload 불가**:
```java
class Service {
    void handle(List<String> strs) { }   // ★
    void handle(List<Integer> ints) { }  // ★ 컴파일 에러
}
```

둘 다 erasure 후 `handle(List)`가 되어 시그니처 충돌. ClassFile 레벨에서 같은 method가 두 개 = 검증 실패.

**해결**:
```java
class Service {
    void handleStrings(List<String> strs) { }
    void handleIntegers(List<Integer> ints) { }
    // 또는 어쩔 수 없이 raw type + instanceof
}
```

### 4.5 키워드 4 — Heap Pollution과 @SafeVarargs

generic + varargs 조합 시 erasure의 부작용이 더 위험하게 드러남.

```java
@SafeVarargs
static <T> List<T> asList(T... items) {
    return Arrays.asList(items);
}
```

**문제**:
- `T... items`는 erasure 후 `Object[] items`.
- 호출자는 `String[]`로 생각하는데 실제로는 `Object[]`.
- 누군가 그 배열에 Integer 넣으면 → heap pollution.

```java
List<String>[] arr = (List<String>[]) Arrays.asList(
    List.of(1, 2),   // List<Integer>인데
    List.of("a")     // List<String>인 척
).toArray();
// arr[0]을 String 기대하고 꺼내면 CCE
```

`@SafeVarargs`는 "내가 안전하게 썼다"는 선언. **컴파일러는 검증하지 않는다**.

---

## 5. 가지 ⑤: 분산(Variance)과 PECS

### 5.1 핵심 질문

> "PECS는 외우는 mnemonic이 아니다. 왜 그렇게 생겼나?"

### 5.2 키워드 1 — 불공변(invariant)이 기본인 이유

```java
List<String> strs = new ArrayList<>();
List<Object> objs = strs;   // ★ 컴파일 에러
```

**왜 막나?** 만약 허용된다면:

```java
List<String> strs = new ArrayList<>();
List<Object> objs = strs;    // 가상 — 허용된다 치자
objs.add(42);                 // ★ 컴파일러는 List<Object>로 보니 OK
String s = strs.get(0);       // ★ runtime: ClassCastException
```

타입 시스템이 깨진다. 그래서 generic은 **불공변(invariant)**: `List<String>`은 `List<Object>`가 아니다.

```
배열은 공변 — String[]은 Object[]
  - Java 1.0의 결정. ArrayStoreException으로 런타임에 검사.
  - covariant array는 type system의 약점으로 평가됨

Generic은 불공변
  - 더 sound한 설계.
  - 대신 표현력이 떨어져 wildcards로 보완.
```

### 5.3 키워드 2 — 공변 `? extends T` (Producer)

```java
List<? extends Number> numbers = ...;
// numbers는 List<Number>, List<Integer>, List<Double> 어떤 것이든 OK
```

**무엇을 할 수 있나?**

```java
Number n = numbers.get(0);   // OK — 무엇이든 Number 이상
numbers.add(42);              // ★ 컴파일 에러
```

**왜 add는 막나?**
- `numbers`는 사실 `List<Integer>`일 수도, `List<Double>`일 수도 있음.
- `add(42)`를 받는 쪽이 `List<Double>`이면 → Integer를 Double로 받음? 타입 깨짐.
- 안전하게는 **null만 add 가능** (null은 모든 타입의 subtype).

**의미**:
- `? extends T` = **Producer** — 꺼낼 수만 있다. 데이터의 출처(source).
- 함수형으로 표현하면: `() → T` (input 없는 producer).

### 5.4 키워드 3 — 반공변 `? super T` (Consumer)

```java
List<? super Integer> ints = ...;
// ints는 List<Integer>, List<Number>, List<Object> 어떤 것이든 OK
```

**무엇을 할 수 있나?**

```java
ints.add(42);              // OK — Integer를 어딘가에 넣음
ints.add(Integer.valueOf(1));   // OK
Integer i = ints.get(0);   // ★ 컴파일 에러
Object o = ints.get(0);    // OK — 항상 Object 반환
```

**왜 get은 Object만?**
- `ints`는 사실 `List<Number>`일 수도, `List<Object>`일 수도 있음.
- 꺼낸 게 Integer가 아닐 가능성.
- 컴파일러는 모든 generic의 공통 상한인 Object만 보장.

**의미**:
- `? super T` = **Consumer** — 넣을 수만 있다. 데이터의 도착지(sink).
- 함수형으로 표현하면: `T → ()` (output 없는 consumer).

### 5.5 PECS — Producer Extends, Consumer Super

```
                                T를 어떻게 쓰나?
                          ┌──────────┴──────────┐
                          │                     │
                       꺼낸다(Producer)        넣는다(Consumer)
                          │                     │
                          ▼                     ▼
                    ? extends T            ? super T
                    (공변)                  (반공변)
```

**고전 예 — Collections.copy**:
```java
public static <T> void copy(List<? super T> dest, List<? extends T> src) {
    //                       └─ Consumer ─┘       └─ Producer ─┘
    //                       dest는 T를 받음       src는 T를 줌
    for (int i = 0; i < src.size(); i++) {
        dest.set(i, src.get(i));
    }
}
```

```java
List<Number> dest = new ArrayList<>();
List<Integer> src = List.of(1, 2, 3);
Collections.copy(dest, src);
//                ↑      ↑
//                List<? super Integer>: List<Number>가 OK
//                List<? extends Integer>: List<Integer>가 OK
```

만약 시그니처가 `copy(List<T> dest, List<T> src)`였다면 dest와 src의 T가 같은 타입이어야만 했을 것. PECS로 분산을 표현해 유연성 확보.

### 5.6 unbounded wildcard `?`

```java
List<?> any = ...;   // any List
Object o = any.get(0);   // OK — 항상 Object
any.add(...);            // ★ null 빼고 컴파일 에러
```

`List<?>` ≈ `List<? extends Object>`. 가장 일반적인 producer.

| 표기 | 의미 | get | add |
|---|---|---|---|
| `List<T>` | 정확히 T | T | T 또는 subtype |
| `List<?>` | 알 수 없는 무엇 | Object | null만 |
| `List<? extends T>` | T 또는 그 subtype | T | null만 |
| `List<? super T>` | T 또는 그 supertype | Object | T 또는 subtype |

**Raw type과 `<?>`의 차이**:
- `List` (raw) — generic 검사를 **모두 우회**. unchecked warning. 옛 코드 호환용.
- `List<?>` — **타입 안전성 유지**. null 외 add 불가.

```java
List raw = new ArrayList<String>();
raw.add(42);   // unchecked warning, 컴파일 OK — heap pollution

List<?> any = new ArrayList<String>();
any.add(42);   // 컴파일 에러
```

→ `?`는 "타입을 모름 + 안전성 보호". raw는 "타입 안전성을 포기".

### 5.7 Liskov Substitution Principle과 연결

분산은 LSP의 generic 버전.
- LSP: B가 A의 subtype이면 A를 기대하는 곳에 B를 줘도 안전해야 함.
- Producer (covariant): 출력 위치는 subtype OK (더 구체적이어도 됨).
- Consumer (contravariant): 입력 위치는 supertype OK (더 일반적이어도 됨).

함수 타입에 적용:
- `Function<A, B>`는 A를 받아 B를 반환.
- A의 위치는 **반공변**: `Function<? super A, B>` 가능.
- B의 위치는 **공변**: `Function<A, ? extends B>` 가능.

→ Java 8의 `Stream.map(Function<? super T, ? extends R>)`이 이 원칙대로 설계.

---

## 6. 가지 ⑥: 진화 — JDK 5 도입부터 현재까지

### 6.1 핵심 질문

> "JDK 5 이후 generics는 어떻게 발전했나? Valhalla는 어디로 가나?"

### 6.2 키워드 1 — JDK 5 도입 (2004)

| | 변화 |
|---|---|
| 도입 | generic class/interface/method, wildcards, bounded type parameter |
| ClassFile | Signature attribute 추가 |
| Tools | javac가 erasure + bridge method 처리 |
| Java API | Collections framework 전체가 generic화 |

**이전과 비교**:
```java
// Java 1.4
Iterator it = list.iterator();
while (it.hasNext()) {
    String s = (String) it.next();
}

// Java 5
for (String s : list) { ... }   // ★ enhanced for + generic
```

### 6.3 키워드 2 — JDK 7 Diamond, JDK 8 Target Typing

**JDK 7 — Diamond operator**:
```java
Map<String, List<Integer>> map = new HashMap<String, List<Integer>>();   // 옛
Map<String, List<Integer>> map = new HashMap<>();                          // JDK 7+
```

**JDK 8 — Target typing**:
```java
List<String> empty = Collections.emptyList();   // T가 String으로 추론
//                                                옛엔: Collections.<String>emptyList()

// Lambda + generic method
list.stream().collect(Collectors.toMap(...));  // 더 강력한 target typing
```

### 6.4 키워드 3 — Record/Sealed/Nest (JDK 14+)

**Record (JDK 14 preview, 16 GA)**:
```java
record Pair<A, B>(A first, B second) {}
```
- generic class와 동일한 erasure.
- 자동 생성된 `equals`, `hashCode`, `toString`도 generic 안전.

**Sealed (JDK 17)**:
```java
sealed interface Result<T> permits Success<T>, Failure<T> {}
```
- generic + sealed의 결합으로 pattern matching 가능.

**Pattern matching for switch (JDK 21+)**:
```java
Object o = ...;
return switch (o) {
    case List<?> list -> "list of size " + list.size();
    // case List<String> -> ... ★ unchecked warning
    //                            erasure로 List<String>만의 패턴은 못 만든다
    case null -> "null";
    default -> "other";
};
```

→ generic + pattern matching의 한계도 erasure가 원인.

### 6.5 Java vs C# Generics 비교 ⭐

| 항목 | Java | C# |
|---|---|---|
| **메커니즘** | Erasure | Reification |
| **런타임 타입 정보** | 없음 (`getClass()`는 raw) | 있음 (`typeof(T)`) |
| **`new T()`** | ❌ 불가 | ✅ `where T : new()` 제약 |
| **`T.class`/`typeof(T)`** | ❌ | ✅ |
| **`instanceof T`** | ❌ | ✅ `obj is T` |
| **Primitive specialization** | ❌ (`List<int>` 불가, autobox) | ✅ `List<int>` 직접 |
| **하위 호환성** | ✅ 1.4 코드와 섞임 | ❌ .NET 1.x → 2.0 깰 수 있음 |
| **메모리** | 단일 Class 객체 | T마다 별도 (`List<int>` ≠ `List<string>`) |
| **JVM/CLR 변경** | 최소 (javac만) | 큼 (CLR 변경) |

```
Java 설계 철학:
  "1.4 시대의 수억 줄 코드를 깨지 않고 type safety를 추가하자"
       ↓
  Erasure 선택
       ↓
  결과: 4가지 제약 + bridge method + wildcards

C# 설계 철학:
  ".NET 1.x는 아직 출시 직후, 호환성 부담 적다. 처음부터 제대로 하자"
       ↓
  Reification 선택
       ↓
  결과: 풍부한 표현력, primitive 지원, 더 큰 메모리/CLR 부담
```

**누가 옳았나?** 둘 다. 각자의 제약에서 최선.

### 6.6 Project Valhalla — Java도 reified로 가나

Valhalla의 두 축:

**Value types (JEP 401 candidate)**:
```java
value class Point {
    int x;
    int y;
}
// Point는 identity 없음, primitive처럼 stack에 인라인 가능
```

**Primitive generics (JEP 402 candidate)**:
```java
ArrayList<int> ints = new ArrayList<>();   // ★ 미래
// autobox 없이 int 직접 저장
// 현재는 ArrayList<Integer>로 Integer 객체 wrapping
```

**왜 지금?**
- modern JIT이 더 똑똑해져서 reification의 성능 이득 더 크게 만들 수 있음.
- 메모리 효율 (특히 거대 collection).
- AOT (GraalVM Native Image)에서도 generic 정보 활용.

**언제?**
- 2026~2027 LTS(JDK 25/27)에서 점진 도입 예상.
- 기존 erased generic과 호환을 위한 복잡한 마이그레이션 전략 필요 (universal generics).

→ **Java도 결국 reified로 가는 중**. 단, 30년 호환성을 등에 진 채로.

---

## 7. 면접 답변 워크플로우

### 7.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "제네릭이 왜 도입됐나요?" | ① WHY | ⑥ 진화 |
| "Type erasure가 뭔가요?" | ② WHAT | ③ HOW Signature |
| "런타임에 generic 정보 어떻게 얻나?" | ③ HOW | ② WHAT erasure |
| "왜 `new T[]`이 안 되나요?" | ④ 제약 | ② WHAT erasure |
| "PECS가 뭔가요?" | ⑤ 분산 | ④ 제약 (불공변) |
| "Java와 C# generic 차이?" | ⑥ 진화 | ② WHAT erasure |
| "Bridge method가 뭔가요?" | ③ HOW | ② WHAT erasure |
| "`List<String>`이랑 `List<Integer>` 같은 클래스?" | ② WHAT | ③ HOW Signature |

### 7.2 답변 템플릿

> **루트 문장 한 줄 → 가지 키워드 3개 → 듣는 사람 표정 따라 인접 가지**

예: "제네릭은 어떻게 동작하나요?"

> "제네릭은 **컴파일 시점에만** 존재하는 타입 안전 도구입니다. (← 루트)
> 첫째, javac가 `<T>`를 Object로 erasure한 bytecode를 만듭니다 (bounded는 상한으로).
> 둘째, 원형 generic 정보는 ClassFile의 Signature attribute에 별도 저장됩니다. Reflection은 이걸 통해 generic을 봅니다.
> 셋째, 호출 지점마다 컴파일러가 invisible cast를 끼워 넣고, generic 메서드 override 시엔 bridge method를 자동 생성합니다.
> 결과로 4가지 제약이 생기는데, `new T[]`, `instanceof T`, `T.class`, generic overload 불가입니다.
> 이게 PECS의 본질이기도 합니다 — type system이 invariant이기 때문에 wildcard로 분산을 표현해야 합니다."

---

## 8. 꼬리질문 트리

### Q1 [가지 ②]. `List<String>`과 `List<Integer>`는 같은 클래스인가요?

> 네. `strs.getClass() == ints.getClass()`가 `true`입니다. erasure로 둘 다 `java.util.ArrayList`라는 같은 Class 객체. 런타임의 JVM은 generic 차이를 모릅니다. 다만 ClassFile의 Signature attribute에는 `<String>`, `<Integer>`가 각각 보존되어 Reflection으로 알 수 있습니다 (변수 선언 위치 등에서).

**🪝 Q1-1: 그럼 Reflection으로 `List<String>`에 Integer 넣을 수 있나요?**
> 네, 가능합니다. 다음 코드:
> ```java
> List<String> strs = new ArrayList<>();
> List rawList = strs;           // 또는 Method.invoke로 add 호출
> rawList.add(42);
> System.out.println(strs.size());   // 1
> String s = strs.get(0);        // ★ ClassCastException
> ```
> erasure 때문에 add 시점에는 런타임 검사가 없습니다. cast는 꺼낼 때 컴파일러가 자동 삽입한 `checkcast`에서 터집니다 — `strs.get(0)` 코드 한 줄 뒤에서 CCE가 나는 이유.

**🪝🪝 Q1-1-1: 이게 정상인가요? 버그인가요?**
> Java의 의도된 동작입니다. 이걸 **heap pollution**이라 부르며 raw type, varargs + generic 등에서 발생할 수 있습니다. 컴파일러는 unchecked warning으로 알려주지만 강제하진 않습니다. JDK 5의 backward-compatible 도입을 위한 의도된 타협 — "1.4 코드와 5의 코드가 한 프로그램에 섞일 수 있어야 한다".

### Q2 [가지 ②]. `<T extends Number>`는 어떻게 erasure되나요?

> Number로 erasure됩니다. bound가 있으면 그 상한이 그대로 남습니다. `<T>`는 Object로, `<T extends Number>`는 Number로, `<T extends A & B>`는 첫 번째 상한 A로. 나머지 상한은 호출 지점 cast로 처리합니다.

**🪝 Q2-1: 그럼 bounded type parameter는 왜 쓰나요?**
> 두 가지: ① 컴파일 시점에 T가 Number라는 정보로 `.doubleValue()` 같은 Number 메서드 호출 허용. ② JIT이 약간의 최적화 가능 (Number 가정으로 inline cache). 하지만 본질은 ①입니다 — "T는 Number 이상"이라는 컴파일러 계약.

### Q3 [가지 ③]. ClassFile의 Signature attribute는 정확히 무엇을 담나요?

> JDK 5에서 추가된 attribute. 세 위치에 붙을 수 있습니다:
> 1. **class-level** — `class Box<T>`의 generic class 선언. `<T:Ljava/lang/Object;>` 형식.
> 2. **field_info** — `T value` 같은 generic 필드. `TT;` 형식.
> 3. **method_info** — `T get()`의 generic signature. `()TT;` 형식.
>
> JVM 실행에는 안 쓰입니다 (verify, link, invoke는 descriptor만 봄). Reflection API(`getGenericXxx`)와 javac의 cross-compile 시 generic 호환성 확인에만 쓰입니다.

**🪝 Q3-1: 이걸 javap로 어떻게 보나요?**
> `javap -v Foo.class` 출력의 각 method/field/class 섹션에 "Signature:" 줄이 있으면 그게 generic 정보. 없으면 그 요소는 generic이 아니거나 raw로 선언됐다는 뜻.

**🪝🪝 Q3-1-1: javap -v 출력의 descriptor와 Signature가 다른 경우는?**
> generic 메서드에서 다릅니다.
> ```
> public T get();
>   descriptor: ()Ljava/lang/Object;    ← JVM이 invoke할 때 쓰는 것 (erased)
>   Signature: ()TT;                    ← reflection이 쓰는 것 (generic)
> ```
> JVM은 descriptor로 method resolution을 합니다. invoke 시 generic 정보는 무시. 그래서 erasure로 같아진 메서드 두 개는 같은 메서드로 보입니다 (generic overload 불가).

### Q4 [가지 ③]. Bridge method는 정확히 언제 생성되나요?

> generic 클래스를 extends하면서 override할 때 erasure로 시그니처가 어긋날 때.
> ```java
> class Node<T> { public void set(T v) {} }
> class StringNode extends Node<String> {
>     @Override public void set(String v) {}
> }
> ```
> StringNode의 bytecode에는 `set(String)`과 `set(Object)` 두 메서드. `set(Object)`가 bridge — `ACC_BRIDGE | ACC_SYNTHETIC` flag로 cast 후 실제 set(String)에 위임. 다형성 유지를 위함.

**🪝 Q4-1: covariant return type도 bridge가 생기나요?**
> 네. 같은 메커니즘.
> ```java
> class A { Object get() { ... } }
> class B extends A { @Override String get() { ... } }
> ```
> B에는 `get():String`(사용자)과 `get():Object`(bridge) 둘 다 생성. JDK 5에서 covariant return type 허용된 것도 generic의 부산물.

**🪝🪝 Q4-1-1: bridge가 stack trace에 보이나요?**
> 가끔 보입니다. `at com.foo.StringNode.set(StringNode.java)`처럼 line number 없이 클래스+메서드만 나오면 bridge일 가능성. `-XX:-OmitStackTraceInFastThrow`로 자세히 보면 ACC_BRIDGE 메서드는 line table이 없어 식별 가능.

### Q5 [가지 ④]. `new T[]`이 안 되는 본질적 이유는?

> 배열은 reified, generic은 erased. 배열은 런타임에 component type을 알아야 ArrayStoreException으로 store-time 검사를 합니다. T는 런타임에 Object일 뿐이라 component type을 모름. 그래서 `T[] arr = new T[10]` 불가.

**🪝 Q5-1: 그럼 ArrayList는 내부적으로 어떻게 구현했나요?**
> `Object[] elementData`를 들고 외부에 `E[] toArray()` 등으로 노출할 때 cast. heap pollution 방지를 위해 `toArray(T[] a)` 같이 user가 component type 토큰을 주는 메서드도 제공. 또는 `Arrays.newInstance(componentClass, size)`로 reflection 기반 배열 생성.

**🪝🪝 Q5-1-1: `Arrays.newInstance`는 어떻게 type-safe한가요?**
> 사용자가 `Class<T>` 토큰을 명시적으로 줍니다. JVM은 그 토큰으로 reified 배열을 생성. cast는 호출자 책임이지만 적어도 component type은 정확. `IntFunction<T[]>` 같은 generator 패턴도 같은 원리 (`Stream.toArray(String[]::new)`).

### Q6 [가지 ⑤]. PECS는 왜 그렇게 외쳐지나요?

> 외우는 mnemonic이 아닙니다. **type system의 sound rule**입니다.
>
> Producer Extends: `? extends T`에서 꺼내는 건 안전. 누가 채웠든 T 이상이니까. 넣는 건 위험. 정확한 타입을 모르니 null 외 불가.
>
> Consumer Super: `? super T`에 넣는 건 안전. T 이상의 그릇이니 T를 받음. 꺼내는 건 무용. 그릇이 Object일 수 있으니 Object만 보장.
>
> 본질은 covariance/contravariance의 메소드 단위 적용. 함수형으로 `(Producer → ()) `와 `(() → Consumer)`의 변환 규칙과 같음.

**🪝 Q6-1: `Function<? super T, ? extends R>`는 왜 그렇게 생겼나요?**
> Function의 input 위치(T)는 contravariant — 더 일반적인 input 받는 것 OK. Function의 output 위치(R)는 covariant — 더 구체적인 output 반환 OK. LSP의 함수 타입 적용. Stream.map(Function<? super T, ? extends R>)이 이를 따라 설계.

**🪝🪝 Q6-1-1: 그럼 BiFunction<? super T, ? super U, ? extends R>이 정확하겠네요?**
> 맞습니다. Java 8 Functional Interface들이 이 패턴을 정확히 따릅니다 — input은 super, output은 extends. Consumer는 `Consumer<? super T>`, Supplier는 `Supplier<? extends T>`로 받는 게 정석. Spring Reactor의 `Mono<T>`/`Flux<T>` operator들도 동일.

### Q7 [가지 ⑥]. Java vs C# generic, 누가 옳았나요?

> 둘 다 자신의 제약에서 최선이었습니다.
>
> **Java (2004)**: JDK 1.4 시절 수억 줄의 운영 코드가 있었음. 호환성 부담이 절대적. erasure로 JVM 변경 최소, 1.4 코드와 5 코드 한 프로그램에 섞일 수 있게. 대신 `new T[]`, primitive 지원 등 표현력 희생.
>
> **C# (2005)**: .NET 1.x 출시 직후, 호환성 부담 적음. CLR 변경 가능. reification으로 `List<int>` 직접 지원, `typeof(T)` 가능, `where T : new()`로 생성 가능. 대신 CLR 복잡도 증가, `List<int>`와 `List<string>`이 다른 타입이라 메모리 오버헤드.
>
> 30년 후 Java는 Valhalla로 reified의 일부를 가져오려 하고 있습니다 — 결국 reified가 더 좋다는 인정. 다만 호환성을 깨지 않으면서 가는 게 어려운 길.

**🪝 Q7-1: Valhalla는 정확히 뭐를 바꾸나요?**
> 두 축: ① Value types — `value class Point`로 identity 없는 객체를 primitive처럼 stack 인라인. ② Primitive generics — `ArrayList<int>` 직접 지원 (현재는 `ArrayList<Integer>`의 autobox). universal generics라는 마이그레이션 전략으로 기존 erased generic과 reified generic을 한 코드에서 섞을 수 있게.

**🪝🪝 Q7-1-1: 운영 코드에 어떤 영향이 오나요?**
> 단기는 거의 없습니다 (opt-in). 중장기로는: ① 거대 collection의 메모리/캐시 효율 개선, ② `Stream<int>`로 IntStream 통합 가능, ③ JFR/profiler가 generic 정보 더 정확히 표시. 다만 LTS 도입 후 2~3년은 라이브러리 호환성 이슈 예상. JDK 25/27 LTS에서 production 진입 예상.

---

## 9. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 1분 이내로 그릴 수 있다 (루트 + 6가지 + 키워드 3개)
- [ ] 가지 ① WHY: Java 1.4 Object cast 시대 → JDK 5 generics 도입 동기
- [ ] 가지 ② WHAT: `<T>` → Object, bounded → 상한, javap -v 출력에서 erasure 확인
- [ ] 가지 ② WHAT: invisible cast (checkcast) + raw type과의 호환
- [ ] 가지 ③ HOW: Signature attribute의 3위치 (class/field/method)
- [ ] 가지 ③ HOW: Bridge method 생성 조건, ACC_BRIDGE flag, stack trace 식별
- [ ] 가지 ③ HOW: Reflection으로 generic 얻기, TypeToken/TypeReference 패턴
- [ ] 가지 ④ 제약: `new T[]`, `instanceof T`, `T.class`, generic overload 각각의 이유
- [ ] 가지 ⑤ 분산: 불공변 기본 이유, PECS의 type system 근거, Liskov 연결
- [ ] 가지 ⑤ 분산: Collections.copy 시그니처와 Function/Consumer/Supplier 분산
- [ ] 가지 ⑥ 진화: JDK 5 → 7 diamond → 8 target typing → Record/Sealed
- [ ] 가지 ⑥ 진화: Java vs C# 8요소 비교표, Valhalla 두 축 (value type, primitive generic)
- [ ] 8장 꼬리질문 7개 막힘없이 답

---

## 10. 운영 시나리오 — 실제로 만나는 generic 사고

### 10.1 시나리오: "List<String>인데 Integer가 들어있다"

**증상**:
```
java.lang.ClassCastException: class java.lang.Integer cannot be cast to class java.lang.String
    at com.foo.UserService.getName(UserService.java:42)
```

**진단**:
1. UserService.java:42를 본다. `String name = users.get(i).getName();` 같은 평범한 코드.
2. 그 위에 cast가 안 보임 → erasure로 생긴 invisible checkcast가 터진 것.
3. 어디서 Integer가 들어갔나? `javap -c UserService`로 호출 흐름 추적.
4. 흔한 범인:
   - Jackson deserialize 시 raw type 사용
   - Reflection `Method.invoke`로 type 검사 우회
   - 외부 라이브러리(특히 옛 Java 1.4 호환 코드)의 raw type 리턴
   - `@SuppressWarnings("unchecked")`로 가린 cast

**해결**:
- raw type 제거, generic 명시.
- 외부 입력은 항상 `Class<T>` 토큰 받기.
- `-Xlint:unchecked`로 컴파일 시 warning 강제.

### 10.2 시나리오: "generic method가 inference 실패한다"

**증상**:
```java
Map<String, List<Integer>> map = someMethod();
// ★ compile error: incompatible types: Map<String, List<Object>> cannot be converted
```

**원인**:
- target typing이 약한 위치(예: 메서드 인자 안의 내부 표현식).
- diamond에서 너무 많은 추론을 요구.

**해결**:
```java
Map<String, List<Integer>> map = SomeClass.<String, List<Integer>>someMethod();   // 명시
// 또는 변수 분리
List<Integer> ints = ...;
Map<String, List<Integer>> map = Map.of("a", ints);
```

### 10.3 시나리오: "Reflection으로 generic 정보가 안 나옴"

**증상**:
```java
List<String> list = new ArrayList<>();
list.getClass().getGenericSuperclass();   // AbstractList<E> — String 안 보임
```

**원인**: 변수 선언 위치 정보는 ClassFile에 없음 (local variable의 generic은 Signature attribute에 부분적으로만).

**해결**: TypeReference / TypeLiteral 패턴.
```java
TypeReference<List<String>> ref = new TypeReference<List<String>>() {};
// 익명 subclass의 Signature에는 List<String>이 박혀있음
```

### 10.4 시나리오: "Mockito가 generic 메서드 mock 못 함"

**증상**:
```java
when(service.<String>find(any())).thenReturn("ok");   // ★ 종종 실패
```

**원인**: erasure로 generic 메서드의 type parameter는 런타임에 모름. Mockito는 인자의 실제 타입만 봄.

**해결**: 명시적 캐스트 또는 ArgumentMatcher 사용.

### 10.5 시나리오: "Spring `@RequestBody List<User>` 가 LinkedHashMap이 되는 이유"

**증상**:
```java
@PostMapping
public void create(@RequestBody List<User> users) {
    User first = users.get(0);   // ★ ClassCastException
    // 실제로는 LinkedHashMap이 들어있음
}
```

**원인**:
- Jackson이 generic 정보 없이 deserialize → 기본 객체(LinkedHashMap)로.
- Spring은 메서드 파라미터의 generic 정보를 `ParameterizedType`으로 얻어 Jackson에 전달하지만, 일부 우회 시 정보 손실.

**해결**: `@RequestBody`는 메서드 파라미터에서 generic 잘 얻음. 문제는 보통 raw List/Map을 중간에 거쳤을 때. ResolvableType / TypeReference 명시.

### 10.6 JIT 관점에서의 generic

**erasure가 JIT을 어떻게 보나**:
- JIT은 generic을 모름. `List.get`은 늘 `Object` 반환.
- 호출 지점의 checkcast가 별도 명령으로 들어있어 inline cache로 최적화.
- 같은 호출 지점이 같은 타입만 보면 monomorphic inline cache로 cast 비용 거의 0.

**측정 — `-XX:+PrintInlining`**:
```
$ java -XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining MyApp

@ 12   com.foo.Service::process (15 bytes)   inline (hot)
  @ 5   java.util.ArrayList::get (5 bytes)   inline (hot)
  @ 9   checkcast java/lang/String           ← JIT이 inline 처리
```

→ erasure가 런타임 비용 거의 안 만듦. checkcast는 cache되어 sub-nanosecond.

---

## 11. 다음 단계 — Reflection으로 이어지는 흐름

이 챕터의 핵심: **generic은 컴파일러에게 받는 일회용 영수증**. 런타임에 들고 갈 수 없다.

그렇다면 런타임에 타입 정보가 정말 필요할 때는 어떻게? → Reflection.

Reflection은 ClassFile에 박힌 모든 메타데이터를 동적으로 읽는 API. Signature attribute도 reflection을 통해서만 보인다. 그러나 reflection은 비싸다 — 왜? Method lookup, security check, access check를 매번 한다.

→ [02-reflection.md](./02-reflection.md): Reflection의 내부 동작, MethodHandle과의 차이, Dynamic Proxy/CGLIB 메커니즘.

---

## 참고

- **JLS §4.6 Type Erasure**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.6
- **JLS §5.1.10 Wildcard Capture**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.10
- **JVMS §4.7.9 Signature Attribute**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.9
- **JLS §8.4.5 Method Result Type / Bridge Methods**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.5
- **Naftalin & Wadler — Java Generics and Collections** (책)
- **Angelika Langer — Java Generics FAQ**: http://www.angelikalanger.com/GenericsFAQ/JavaGenericsFAQ.html
- **Project Valhalla — JEP 401 (Value Objects)**: https://openjdk.org/jeps/401
- **Project Valhalla — JEP 402 (Universal Generics)**: https://openjdk.org/jeps/402
- **Brian Goetz — State of Valhalla**: https://openjdk.org/projects/valhalla/design-notes/state-of-valhalla/01-background
- **C# Generics vs Java**: https://docs.microsoft.com/en-us/dotnet/standard/generics/
