# 02. Reflection — 런타임에 자기 자신을 들여다보는 코드

> "Reflection? `Method.invoke()` 같은 거" 라고 답하면 입문자.
> "Reflection은 java.lang.reflect 패키지를 통해 ClassLoader가 Metaspace에 로드해둔 InstanceKlass 메타데이터를 Heap의 Class<?> mirror로 노출하는 메타프로그래밍 facility다. Method.invoke()는 처음 15회까지는 NativeMethodAccessorImpl이 JNI로 처리하다가 inflationThreshold를 넘으면 GeneratedMethodAccessor라는 bytecode를 동적으로 만들어 Code Cache에 올리고 그 다음부터는 invokevirtual로 직접 dispatch한다. 그래도 호출 사이트가 megamorphic이고 invoke target이 컴파일 상수가 아니라서 JIT inline이 안 된다. JDK 7의 MethodHandle은 static final로 잡으면 invoke target이 상수처럼 취급되어 inline 가능, JDK 8의 LambdaMetafactory는 invokedynamic CallSite로 Functional Interface 구현체를 1회 만들고 그 다음부터는 직접 호출 수준 빠르다" 라고 말할 수 있다면 그 다음 단계.
> 이 문서의 목표는 후자다.

---

## 이 문서의 사용법

이 문서는 **면접용 마인드맵 + 7단 레이어**를 따라 선형으로 펼친 구조다.

1. **0장 마인드맵을 먼저 외운다** — 루트 한 문장 + 7가지 가지 + 키워드 3개.
2. **1~7장을 순서대로 학습** — 각 장이 한 가지에 정확히 대응.
3. **8장 운영 시나리오로 검증** — 진단 → 해결까지.
4. **9장 꼬리질문으로 깊이 점검**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"Reflection은 런타임에 Class 메타데이터를 들여다보고 조작하는 메타프로그래밍 facility다. compile-time에 모르는 클래스/메서드/필드를 Class<?> mirror를 통해 InstanceKlass에 도달해 호출·접근한다. 비용의 본질은 JIT inline 불가(megamorphic call site)와 inflation 비용. MethodHandle/LambdaMetafactory/Bytecode generation이 그 한계를 깬다."**

이 한 문장에서 모든 답변이 출발한다.

### 7개 가지 — 순서를 외운다

```
                       [ROOT: Reflection = 런타임 메타프로그래밍, JIT inline 불가]
                                              │
       ┌────────────┬───────────┬───────┬─────┴────┬───────────┬───────────┬───────────┐
       │            │           │       │          │           │           │           │
      ① WHY        ② WHAT      ③ HOW   ④ 비용     ⑤ Module    ⑥ 대안       ⑦ 운영
   메타프로그램    java.lang.   Class    inflation  JDK 9+      MH / Lambda  Framework
   plugin/IoC     reflect      mirror   megamorph  setAccess   /Bytecode   사용 패턴
       │            │           │       │          │           │           │
   ┌───┼───┐    ┌──┼──┐     ┌──┼──┐  ┌─┼─┐    ┌──┼──┐    ┌──┼──┐    ┌──┼──┐
   Spring  Hib  Class      Klass   Native  15회   add-     MH       Spring
   Jackson      Method     mirror  ─→Gen.  inflate opens   Lambda   Jackson
   Mockito      Field      양방향  Accessor JNI            Bytebuddy Hibernate
                Constructor                CodeCache
                Annotation
```

### 가지별 핵심 키워드 (각 가지 3개씩만)

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① WHY** | 메타프로그래밍 | compile-time 모르는 코드 | plugin / IoC / serialization |
| **② WHAT** | java.lang.reflect 패키지 | Class·Method·Field·Constructor | AnnotatedElement / Modifier / Array |
| **③ HOW** | Class<?> = Heap mirror | _klass → Metaspace InstanceKlass | Class.forName vs ClassLoader.loadClass |
| **④ 비용** | NativeAccessor → GeneratedAccessor inflation | JIT inline 불가 (megamorphic) | 10~100x slowdown |
| **⑤ Module** | JDK 9 strong encapsulation | --add-opens / illegal access | JDK 17 Error로 격상 |
| **⑥ 대안** | MethodHandle (static final → inline) | LambdaMetafactory (invokedynamic) | ByteBuddy / ASM bytecode gen |
| **⑦ 운영** | Spring (BeanDef + DI) | Jackson (getter/setter) | Hibernate (PropertyAccessor) |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 질문에 맞는 가지 1개 선택 → 그 가지의 키워드 3개 순서대로 설명 → 인접 가지로 확장

---

## 1. 백지 그리기 — 그림 4장

### 그림 1: Reflection의 메모리 그림 (mirror ↔ Klass)

```
[Java 코드]
   Class<String> c = String.class;
   Method m = c.getMethod("length");
   m.invoke("hello");
                                ↓ 해석

JVM Process
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

┌─────────────────────────────┐   ┌──────────────────────────────────┐
│ Heap                          │   │ Metaspace                          │
│                               │   │                                    │
│  ┌───────────────────────┐   │   │  ┌────────────────────────────┐   │
│  │ Class<String> mirror   │   │   │  │ InstanceKlass for String   │   │
│  │  ├ _klass ─────────────┼───┼───┼─►│  ├ _java_mirror ◄──────────┤   │
│  │  ├ name "String"       │   │   │  │  ├ _methods[length, ...]   │   │
│  │  ├ classLoader = null  │   │   │  │  ├ _fields                  │   │
│  │  └ ...                 │   │   │  │  ├ _constants (CP)          │   │
│  └───────────────────────┘   │   │  │  └ vtable / itable          │   │
│                               │   │  └────────────────────────────┘   │
│  ┌───────────────────────┐   │   │                                    │
│  │ Method "length"        │   │   │  ┌────────────────────────────┐   │
│  │  ├ clazz ──────────────┼───┼──►│ Method 메타 (Metaspace)      │   │
│  │  ├ name "length"       │   │   │  │  ├ bytecode pointer         │   │
│  │  ├ root (cache)        │   │   │  │  ├ _code (nmethod 주소)     │   │
│  │  └ methodAccessor ─────┼─┐ │   │  │  └ MDO                       │   │
│  └───────────────────────┘ │ │   │  └────────────────────────────┘   │
│                              │ │   │                                    │
│  ┌────────────────────────┐ │ │   │  ┌────────────────────────────┐   │
│  │ NativeMethodAccessor   │◄┘ │   │  │ Compressed Class Space     │   │
│  │ (처음 15회)             │   │   │  │  (Klass 포인터 압축)         │   │
│  └────────────────────────┘   │   │  └────────────────────────────┘   │
│         ↓ inflation             │   │                                    │
│  ┌────────────────────────┐   │   │                                    │
│  │ GeneratedMethodAccessor│   │   │                                    │
│  │ 5  (동적 bytecode)      │───┼───┼───┐                                │
│  └────────────────────────┘   │   │   │                                │
└─────────────────────────────┘   └───┼────────────────────────────────┘
                                       │
                                       ▼
                            ┌─────────────────────────┐
                            │ Code Cache               │
                            │  GeneratedAccessor5의    │
                            │  bytecode → JIT compile  │
                            │  → 실제 native invoke     │
                            └─────────────────────────┘
```

### 그림 2: Method.invoke()의 두 경로 (inflation 전 vs 후)

```
[처음 15회 호출] — Native 경로
─────────────────────────────────
Java Code
    Method.invoke(obj, args)
        │
        ▼
sun.reflect.NativeMethodAccessorImpl.invoke()
        │
        ▼
   JNI native call ───→ HotSpot C++ Reflection::invoke()
        │                     │
        │                     ├─ 인자 unbox
        │                     ├─ access check
        │                     ├─ vtable/itable lookup
        │                     └─ interpreter/JIT entry로 jump
        ▼
   return value boxing


[16회+ 호출] — Generated 경로
─────────────────────────────────
Java Code
    Method.invoke(obj, args)
        │
        ▼
GeneratedMethodAccessor5.invoke(obj, args)  ← 동적 생성된 클래스
   public Object invoke(Object obj, Object[] args) {
       String target = (String) obj;           ← 정적 캐스트
       int result = target.length();            ← 직접 invokevirtual!
       return Integer.valueOf(result);          ← boxing
   }
        │
        ▼
   normal invokevirtual ─→ Code Cache의 nmethod 직접 호출
        │
        ▼
   return value
```

### 그림 3: Reflection vs MethodHandle vs LambdaMetafactory (호출 비용)

```
[직접 호출]                  cycles ≈ 1~3
  obj.method()
   └→ call [Method._code]   ◄── 직접 native jump

[LambdaMetafactory]          cycles ≈ 3~5
  func.apply(obj)
   └→ Functional Interface  ◄── invokedynamic CallSite
       구현체의 method()         (1회 만들고 static)
       → 직접 invokevirtual

[MethodHandle (static final)] cycles ≈ 5~10
  MH.invokeExact(obj)
   └→ JIT이 MH를 상수로 인식 ◄── final + LambdaForm + 인라인
       → 직접 호출로 인라인

[MethodHandle (지역 변수)]    cycles ≈ 30~50
  mh.invokeExact(obj)
   └→ JIT이 상수 못 잡음     ◄── 매 호출마다 dispatch

[Reflection (inflated)]      cycles ≈ 50~100
  method.invoke(obj)
   └→ GeneratedAccessor 거침 ◄── boxing, access check,
       megamorphic invoke         JIT inline 안 됨

[Reflection (native)]        cycles ≈ 500~1000
  method.invoke(obj)         처음 15회만
   └→ JNI transition         ◄── 가장 느림
       native dispatch
```

### 그림 4: Dynamic Proxy vs CGLIB

```
[JDK Dynamic Proxy]                  [CGLIB]
─────────────────────                 ───────────
인터페이스만 가능                       클래스 subclass 생성
                                      (final 클래스/메서드 불가)

interface UserService {}              class UserService {}
   ▲                                      ▲
   │                                      │
   │ implements                           │ extends
   │                                      │
$Proxy0 extends Proxy                  UserService$$EnhancerByCGLIB
   ├ InvocationHandler h               (ASM이 동적 생성)
   └ 모든 method →                       │
      h.invoke(proxy, method, args)     모든 method override →
                                          MethodInterceptor.intercept()

런타임 클래스 생성:                     런타임 클래스 생성:
java.lang.reflect.Proxy                cglib.ProxyGenerator (ASM)
↓                                       ↓
ClassLoader.defineClass()              ClassLoader.defineClass()
↓                                       ↓
Metaspace에 $Proxy0 InstanceKlass      Metaspace에 EnhancerByCGLIB
↓                                       ↓
Heap에 mirror                          Heap에 mirror
↓                                       ↓
Heap에 instance                        Heap에 instance
```

---

## 2. 직관 — Reflection이란 무엇인가

### 2.1 한 줄 비유

> **Reflection = 거울을 보며 자기 옷을 매만지는 코드**
>
> 실행 중인 프로그램이 **자기 자신**(클래스·메서드·필드)을 들여다보고 조작.

### 2.2 정확한 정의

> **Reflection (메타프로그래밍 facility)**
> 컴파일 시점에 알지 못하는 타입의 객체를, 런타임에 그 타입 정보를 조회·생성·조작할 수 있게 하는 표준 라이브러리. java.lang.reflect 패키지를 통해 노출.

### 2.3 왜 존재하나 — Reflection 없으면 못 하는 것

```
[Reflection 없는 세계]                  [Reflection 있는 세계]
─────────────────                       ─────────────────
모든 타입은 compile-time에 알아야        compile-time에 모르는 타입도
                                         런타임에 접근 가능

UserService s = new UserService();      Class<?> c = Class.forName(name);
s.save(user);                            Object s = c.getConstructor().newInstance();
                                         c.getMethod("save", User.class)
                                          .invoke(s, user);

→ Spring 없음                            → Spring DI
→ JSON 직렬화는 케이스별 코딩             → Jackson (자동 매핑)
→ ORM은 case-by-case SQL                 → Hibernate (자동 매핑)
→ Plugin/Extension 불가                  → ServiceLoader, OSGi
→ Mock 라이브러리 불가                    → Mockito (subclass 생성)
```

**한 줄**: Reflection은 **"코드를 다루는 코드"**를 가능하게 한다. 그래서 framework·library의 표준 기술.

### 2.4 메타프로그래밍이란

> **Metaprogramming**: 프로그램이 다른 프로그램(또는 자기 자신)을 데이터처럼 다루는 기법.

| 메타프로그래밍 형태 | 언어 예시 |
|---|---|
| **컴파일 시점 매크로** | C의 `#define`, Rust의 macro, Lisp의 macro |
| **컴파일 시점 코드 생성** | Java의 Annotation Processor (Lombok), Kotlin의 KSP |
| **런타임 메타 조회** | **Java Reflection**, Python의 `getattr`/`type` |
| **런타임 코드 생성** | **Java의 ByteBuddy/ASM/CGLIB**, JS의 `eval` |
| **AOP** | AspectJ, Spring AOP |

→ Java Reflection은 **런타임 메타 조회 + 일부 동적 코드 생성**의 표준.

---

## 3. 구조 — java.lang.reflect 패키지

### 3.1 핵심 클래스 분해

```
java.lang.Class<T>                          ← 모든 reflection의 진입점
  ├ Class.forName(name)                     클래스 로드 + 초기화
  ├ ClassLoader.loadClass(name)             클래스 로드만 (초기화 X)
  ├ getMethod(name, params...)              public method
  ├ getDeclaredMethod(name, params...)      모든 visibility
  ├ getField / getDeclaredField             필드
  ├ getConstructor / getDeclaredConstructor 생성자
  ├ getAnnotation / getAnnotations          annotation
  └ getInterfaces / getSuperclass           상속 관계

java.lang.reflect 패키지
  ├ Method        → invoke(obj, args)
  ├ Field         → get(obj) / set(obj, value)
  ├ Constructor   → newInstance(args)
  ├ Parameter     → JDK 8+ 메서드 파라미터 메타
  ├ Modifier      → public/static/final 등 bitmask 조회
  ├ Array         → newInstance(componentType, length) / get/set
  ├ Proxy         → 동적 인터페이스 구현체 생성
  ├ InvocationHandler → Proxy의 호출 처리기
  └ AccessibleObject → setAccessible (private 우회)

java.lang.reflect.AnnotatedElement (인터페이스)
  Class, Method, Field, Constructor, Parameter가 모두 implement
  → getAnnotation, getAnnotations, isAnnotationPresent
```

### 3.2 Class.forName vs ClassLoader.loadClass

```
Class.forName("com.foo.Bar")               ClassLoader.loadClass("com.foo.Bar")
─────────────────────────                  ─────────────────────────
1. 클래스 로드                              1. 클래스 로드
2. ★ Initialization (static {} 실행)        2. ★ Initialization 안 함
                                               (이후 사용 시 lazy)

용도: JDBC 드라이버 등록                    용도: 단순 로드 (예: 존재 확인)
  Class.forName("org.h2.Driver")           - DriverManager 자동 등록 안 됨
  → static { DriverManager.register(...) }   - 검사용

3-arg 버전:
Class.forName(name, initialize, loader)
  - initialize=false로 만들면 loadClass와 유사
  - loader 지정 가능 (default: caller's CL)
```

**시니어 함정**: Spring에서 `Class.forName("com.foo.NotExist")`를 component scan 시 호출하면 클래스 없을 때 ClassNotFoundException + initialization 실행. 단지 "있는지만 확인"이라면 `ClassLoader.loadClass(name, false)` 또는 `Class.forName(name, false, loader)`로 초기화 회피.

### 3.3 Foo.class 리터럴은 어떻게 동작?

```java
Class<String> c = String.class;
```

이건 메서드 호출이 아니라 **bytecode 명령**:

```
ldc_w #ConstantPool[ClassRef "java/lang/String"]
   ↓
JVM이 Constant Pool의 CONSTANT_Class_info를
ClassLoader로 resolve
   ↓
Metaspace의 InstanceKlass 확보
   ↓
그것의 _java_mirror (Heap의 Class<String>) push to stack
```

**시니어 한 줄**: `Foo.class`는 **컴파일 타임에 Constant Pool entry로 박힘** → 첫 사용 시 ClassLoader resolve → Heap의 mirror 반환. `Class.forName("Foo")`처럼 String lookup이 아님.

### 3.4 Object.getClass()

```java
Object obj = "hello";
Class<?> c = obj.getClass();  // Class<String>
```

```
[모든 Java 객체의 헤더]
─────────────────────────
   Mark Word    (8 byte, lock/hash/age)
   Klass Ptr ───→ Metaspace의 InstanceKlass  ★ 여기에 직접 가리킴
   (4 byte compressed or 8 byte)
   .........
   필드들

Object.getClass() 구현:
   intrinsic으로 Klass Ptr → _java_mirror 반환
   = Heap의 Class<?> 객체
```

→ `getClass()`는 객체 헤더의 Klass Ptr 한 번 dereferencing. **거의 무비용**.

---

## 4. 내부 구현 — Method.invoke()의 두 경로 ⭐⭐

### 4.1 핵심 질문

> "Method.invoke()는 왜 호출 횟수에 따라 빠르게 또는 느리게 동작하나?"

### 4.2 두 가지 구현 경로

HotSpot의 `Method.invoke()`는 내부에 **MethodAccessor** 인터페이스를 둠. 처음과 그 이후가 다른 구현체를 쓴다.

```
java.lang.reflect.Method
  └ methodAccessor: MethodAccessor (lazy init)
        │
        ├──[초기]─→ NativeMethodAccessorImpl
        │              └ JNI native call
        │
        └──[15회 이후]─→ GeneratedMethodAccessor (런타임 bytecode gen)
                          └ 직접 invokevirtual
```

### 4.3 NativeMethodAccessorImpl (처음 15회)

```java
// sun.reflect.NativeMethodAccessorImpl (간략화)
class NativeMethodAccessorImpl extends MethodAccessorImpl {
    private DelegatingMethodAccessorImpl parent;
    private int numInvocations;

    public Object invoke(Object obj, Object[] args) {
        if (++numInvocations > ReflectionFactory.inflationThreshold()) {
            // 임계 도달 → GeneratedAccessor로 inflate
            MethodAccessorImpl gen = (MethodAccessorImpl)
                new MethodAccessorGenerator().generateMethod(...);
            parent.setDelegate(gen);
        }
        return invoke0(method, obj, args);  // ★ JNI native
    }

    private static native Object invoke0(Method m, Object obj, Object[] args);
}
```

**JNI 비용**:
1. **Argument boxing**: int → Integer 등 모든 primitive를 wrapper로
2. **Access check**: SecurityManager + module 검사
3. **Vtable/itable lookup**: virtual call이면 receiver 타입 dispatch
4. **Native transition**: JVM stack → native stack 전환 (수십 cycle 비용)
5. **Result boxing**: 반환값도 wrapper로

**왜 처음에는 native?**: 동적 클래스 생성 자체가 비싸다(~수십 ms). 한두 번 호출되고 끝날 reflection을 위해 클래스 만들면 손해. → 트레이드오프로 임계 도입.

### 4.4 GeneratedMethodAccessor (16회 이후, inflation)

`sun.reflect.MethodAccessorGenerator`가 ASM 비슷한 방식으로 **즉석에서 bytecode 생성**해 ClassLoader에 정의.

```java
// 동적으로 생성되는 클래스 (예: GeneratedMethodAccessor5)
public class GeneratedMethodAccessor5 extends MethodAccessorImpl {
    @Override
    public Object invoke(Object obj, Object[] args)
            throws InvocationTargetException {
        try {
            // 정적 캐스트로 receiver 타입 고정
            String target = (String) obj;
            // 정적 캐스트로 인자 unbox
            int arg0 = ((Integer) args[0]).intValue();
            // ★ 직접 invokevirtual — JVM 일반 호출 경로
            int result = target.charAt(arg0);
            // 결과 boxing
            return Integer.valueOf(result);
        } catch (Throwable t) {
            throw new InvocationTargetException(t);
        }
    }
}
```

**핵심**:
- 생성된 클래스는 **새 ClassLoader**(MagicAccessorImpl 계열)에 정의 → access check 우회.
- `invokevirtual`은 JVM의 일반 dispatch → C2 컴파일 대상 → Code Cache 진입.
- 하지만 **호출 사이트가 megamorphic** (다양한 GeneratedAccessor가 같은 invoke 사이트로 들어옴) → C2 inline 거의 불가.

**inflationThreshold** (기본 15):
```bash
-Dsun.reflect.inflationThreshold=15      # default
-Dsun.reflect.inflationThreshold=0       # 즉시 generate (warmup 짧게)
-Dsun.reflect.noInflation=true           # inflation 자체 끔 (native만)
```

### 4.5 DelegatingMethodAccessorImpl — 두 경로 사이의 다리

```java
// 실제 Method 객체가 들고 있는 건 Delegating
class DelegatingMethodAccessorImpl extends MethodAccessorImpl {
    private MethodAccessorImpl delegate;  // 처음엔 Native, 나중에 Generated

    public Object invoke(Object obj, Object[] args) {
        return delegate.invoke(obj, args);
    }

    void setDelegate(MethodAccessorImpl gen) {
        this.delegate = gen;
    }
}
```

→ inflation이 일어나면 `delegate` 필드 교체만으로 Native → Generated 전환. 같은 Method 객체를 들고 있는 모든 caller가 자동으로 빠른 경로로.

### 4.6 JDK 18+: MethodHandle 기반으로 통합

**JEP는 따로 없음**, 내부 구현 변경이지만 시니어가 알아야 할 변화:

```
[JDK 17 이전]                              [JDK 18+]
─────────────                              ─────────────
NativeMethodAccessor                       MethodHandleAccessor
   ↓ JNI                                       ↓
GeneratedMethodAccessor                    MethodHandle.invokeExact
(동적 bytecode 생성)                         (이미 빠른 메커니즘 활용)
```

장점: Code Cache 압박 감소 (GeneratedAccessor 클래스 폭증이 사라짐), warmup 단축.

### 4.7 Field, Constructor도 같은 구조

| | 처음 N회 | inflation 후 |
|---|---|---|
| `Method.invoke` | NativeMethodAccessor | GeneratedMethodAccessor |
| `Field.get/set` | NativeFieldAccessor | GeneratedFieldAccessor |
| `Constructor.newInstance` | NativeConstructorAccessor | GeneratedConstructorAccessor |

모두 동일 패턴: native → inflation 임계 → 동적 bytecode generation.

---

## 5. 역사 — Reflection의 진화

### 5.1 타임라인

| 연도 | 릴리스 | 변화 | 의미 |
|---|---|---|---|
| 1997 | **JDK 1.1** | java.lang.reflect 도입 | 메타프로그래밍 표준 진입 |
| 1999 | JDK 1.2 | Proxy (인터페이스 동적 구현) | Spring AOP의 기반 |
| 2002 | JDK 1.4 | Logging, NIO와 함께 reflection 성숙 | |
| 2004 | **JDK 5** | Annotation + Generics + `getGenericType` | Spring/Hibernate의 entity scanning 기반 |
| 2011 | **JDK 7** | **MethodHandle (java.lang.invoke)** | invoke target을 상수처럼 다루는 새 길 |
| 2014 | **JDK 8** | **LambdaMetafactory (invokedynamic)** | Lambda 효율 구현 + reflection 대안 |
| 2017 | **JDK 9** | **Module + strong encapsulation** | `setAccessible` 큰 제약 (`--add-opens`) |
| 2018 | JDK 9 | VarHandle (Field의 MethodHandle 버전) | atomic operations 표준화 |
| 2021 | **JDK 17** | "illegal reflective access" warning → **error** | JDK 8 코드의 마이그레이션 강제 |
| 2022 | JDK 18+ | MethodAccessor를 MH 기반으로 통합 | Code Cache 압박 감소, warmup ↑ |
| 2024+ | 진행 중 | Project Leyden | reflection의 AOT 친화화 |

### 5.2 왜 JDK 7에서 MethodHandle?

**JDK 7 (JEP 292 — invokedynamic)**: JVM의 표준 호출 명령 5개(invokestatic/special/virtual/interface)에 **invokedynamic**을 추가.

```
invokedynamic의 본질:
   첫 호출 → bootstrap method 호출 → CallSite 반환
                                        └ target: MethodHandle
   이후 호출 → CallSite.target.invoke(args)
              (target 교체 가능, mutable)
```

→ MethodHandle은 이 invokedynamic의 핵심. JIT이 target이 **final**이면 상수로 가정 inline.

### 5.3 왜 JDK 8에서 LambdaMetafactory?

JDK 8 lambda를 **익명 클래스**로 구현하면 너무 비쌈 (lambda마다 클래스 생성 + 객체 생성). **invokedynamic + LambdaMetafactory**로 우회:

```
Function<String, Integer> f = s -> s.length();

[컴파일 결과 (간략)]
invokedynamic apply()Ljava/util/function/Function;
   bootstrap: LambdaMetafactory.metafactory(...)
   args: targetMethod = "lambda$0" 가리키는 MethodHandle
```

런타임 동작:
1. 첫 호출 시 LambdaMetafactory가 Functional Interface (Function) 구현 클래스를 **한 번** 생성.
2. CallSite의 target은 그 클래스의 인스턴스를 반환하는 MethodHandle.
3. 이후엔 그냥 인스턴스 반환 + invokevirtual.

→ Reflection 없이 Method를 Function/Supplier/Consumer로 wrapping 가능. **현대 Spring 5+ 일부 영역이 이 메커니즘으로 Reflection 호출을 대체**.

### 5.4 JDK 9 Module — Reflection의 가장 큰 변화

**Problem**: JDK 1.1~8의 Reflection은 `setAccessible(true)`로 private 필드까지 접근 가능 → "캡슐화는 그저 권장사항".

**JDK 9 JPMS (Java Platform Module System)**:
- 모든 모듈은 명시적으로 `exports`, `opens`한 패키지만 외부에서 접근 가능.
- `exports`: 컴파일 + 일반 reflection 허용.
- `opens`: 그 위에 setAccessible(true)로 deep reflection까지 허용.

```
JDK 8 코드:
   Field f = String.class.getDeclaredField("value");
   f.setAccessible(true);          // ★ 무조건 가능
   char[] v = (char[]) f.get(s);

JDK 9+:
   같은 코드 → 경고:
   WARNING: Illegal reflective access by ... to field java.lang.String.value

JDK 17+:
   같은 코드 → InaccessibleObjectException (Error로 격상)
```

**해결**: 실행 시 `--add-opens` 옵션 명시.
```bash
--add-opens java.base/java.lang=ALL-UNNAMED
```

framework들은 이걸 module-info.java 또는 자동 옵션으로 처리.

### 5.5 Project Leyden — Reflection의 AOT 친화화

목표: "static analysis로 reflection target을 미리 파악해 AOT compile에 활용".
- GraalVM Native Image는 reflection metadata를 build 시점에 `reflect-config.json`으로 명시 필요.
- Leyden은 좀 더 자연스럽게 — JFR로 reflection을 기록해 다음 실행에 재사용.

---

## 6. 트레이드오프 ⭐⭐ — Reflection vs MethodHandle vs LambdaMetafactory vs Bytecode gen

### 6.1 비교표

| | Reflection | MethodHandle | LambdaMetafactory | ByteBuddy/ASM |
|---|---|---|---|---|
| **도입** | JDK 1.1 | JDK 7 | JDK 8 | external lib |
| **JIT inline** | ❌ (megamorphic) | ✅ (static final이면) | ✅ | ✅ (생성 후 일반 호출) |
| **호출 비용** | 50~100x slower | 5~10x slower (static final), 30x (지역) | 3x slower | 1x (직접 호출과 동일) |
| **첫 호출 비용** | 15회까지 JNI (가장 느림) | lookup 1회 비싸지만 그 이후 빠름 | metafactory call 1회 | 클래스 generation 1회 (~수십 ms) |
| **메모리** | GeneratedAccessor 클래스 폭증 | LambdaForm 일부 | Functional Interface 인스턴스 1개 | 생성한 클래스만 |
| **사용 난이도** | 쉬움 (직관적 API) | 중간 (LambdaForm 이해 필요) | 어려움 (직접 쓰는 경우) | 어려움 (bytecode 지식) |
| **표현력** | 모든 메서드 호출 | 모든 메서드 호출 | Functional Interface만 | 무제한 |
| **module 제약** | --add-opens 필요 | Lookup.privateLookup 필요 | Lookup.privateLookup 필요 | defineClass 권한 필요 |
| **대표 사용처** | Spring, Jackson, Hibernate | java.lang.invoke 내부, 일부 Spring | java.util.function | Mockito, Hibernate proxy |

### 6.2 결정 매트릭스

```
"이 호출 사이트의 target이 컴파일 타임에 알려져 있나?"
   │
   ├─ Yes (정적) ─→ 직접 호출. Reflection 쓸 이유 없음.
   │
   └─ No (동적) ─→ "런타임에 한 번만 결정되고 그 후엔 안 바뀌나?"
              │
              ├─ Yes (안 바뀜) ─→ "Functional Interface로 wrap 가능?"
              │                       │
              │                       ├─ Yes ─→ LambdaMetafactory (가장 빠름)
              │                       │
              │                       └─ No  ─→ MethodHandle (static final로 잡기)
              │
              └─ No (자주 바뀜) ─→ "성능이 critical?"
                                     │
                                     ├─ Yes ─→ ByteBuddy로 클래스 생성 후 일반 호출
                                     │
                                     └─ No  ─→ Reflection (간단함 우선)
```

### 6.3 시니어 한 줄

> "Reflection은 **편의성**, MethodHandle은 **성능**, LambdaMetafactory는 **함수형 API와의 통합**, ByteBuddy는 **무제한 표현력**. 실전에서는 layered — Spring은 일반 호출에 Reflection, 자주 호출되는 곳은 MethodHandle, AOP 프록시는 ByteBuddy."

---

## 7. 측정·진단 ⭐ — JFR, async-profiler, PrintCompilation

### 7.1 JFR로 reflection 추적

```bash
# JFR 시작 (300초 기록)
jcmd <pid> JFR.start name=reflect duration=300s settings=profile filename=reflect.jfr

# 핵심 이벤트
- jdk.ReflectiveAccess               # JDK 17+: illegal access 추적
- jdk.JavaErrorThrow                  # InvocationTargetException, IllegalAccessException
- jdk.ClassDefine                     # GeneratedAccessor 클래스 동적 생성
- jdk.Compilation                     # JIT 컴파일 (inflation generated class 포함)
```

JFR 분석:
```bash
# JMC 또는 jfr 명령
jfr print --events jdk.ClassDefine reflect.jfr
# → "GeneratedMethodAccessor47" 같은 동적 클래스가 얼마나 생성됐나
```

### 7.2 async-profiler로 hot path 추적

```bash
async-profiler -d 60 -e cpu -f reflect.html <pid>
```

flame graph에서 찾을 패턴:
```
java/lang/reflect/Method.invoke               ← Reflection 진입점
└ sun/reflect/DelegatingMethodAccessorImpl.invoke
   └ sun/reflect/NativeMethodAccessorImpl.invoke   ★ 처음 15회 (가장 비쌈)
        └ Method::invoke_native                     JNI transition
   또는
   └ sun/reflect/GeneratedMethodAccessor47.invoke   ★ inflation 후
        └ 실제 target method
```

**시니어 신호**:
- `NativeMethodAccessorImpl::invoke`가 hot에 보이면 → reflection을 매번 새 Method 객체로 부른다는 뜻 (캐싱 안 함).
- `GeneratedMethodAccessor` 클래스 수가 수만 → reflection 호출 사이트 폭증, Code Cache 압박 가능.

### 7.3 -XX:+PrintCompilation으로 JIT 추적

```bash
java -XX:+PrintCompilation -XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining ...
```

출력 해석:
```
1234   234   3       sun.reflect.GeneratedMethodAccessor47::invoke (47 bytes)
                       @ 12 com.foo.MyClass::myMethod (8 bytes)   inline (hot)
                       @ 19 java.lang.Integer::valueOf (32 bytes) inline (hot)
```

- `3` = C1 tier 3 컴파일
- GeneratedMethodAccessor가 hot이 됐다 = reflection이 자주 호출됐다는 신호
- inline이 됐다면 좋은 신호, "callee is too large" 같은 메시지면 inline 실패

**또 하나의 신호**:
```
1234  234  not entrant  sun.reflect.GeneratedMethodAccessor47::invoke
```
"not entrant"는 deopt 발생 — receiver 타입이 가정 깨졌다는 뜻.

### 7.4 GeneratedAccessor 클래스 수 측정

```bash
# 동적 생성된 reflection accessor 클래스 수
jcmd <pid> GC.class_histogram | grep -i Accessor
# → GeneratedMethodAccessor, GeneratedConstructorAccessor 등

# Class 전체 수
jcmd <pid> VM.classloader_stats
```

수만 단위면 inflation이 과도하게 일어남 — `-Dsun.reflect.inflationThreshold` 조정 검토.

### 7.5 마이크로벤치마크 (JMH)

```java
@State(Scope.Benchmark)
public class ReflectBench {
    String target = "hello world";
    Method method;
    MethodHandle handle;
    Function<String, Integer> lambda;

    @Setup
    public void setup() throws Exception {
        method = String.class.getMethod("length");
        method.setAccessible(true);

        MethodHandles.Lookup lookup = MethodHandles.lookup();
        handle = lookup.findVirtual(String.class, "length",
                                    MethodType.methodType(int.class));

        CallSite cs = LambdaMetafactory.metafactory(
            lookup, "apply",
            MethodType.methodType(Function.class),
            MethodType.methodType(Object.class, Object.class),
            handle,
            MethodType.methodType(Integer.class, String.class));
        lambda = (Function<String, Integer>) cs.getTarget().invokeExact();
    }

    @Benchmark public int direct() { return target.length(); }
    @Benchmark public int reflect() throws Exception { return (int) method.invoke(target); }
    @Benchmark public int mh() throws Throwable { return (int) handle.invokeExact(target); }
    @Benchmark public int lambdaApply() { return lambda.apply(target); }
}
```

**의사 결과 (i7, JDK 21)**:
```
Benchmark              Mode  Cnt    Score    Error  Units
direct                 avgt   10    1.012 ±  0.020  ns/op
lambdaApply            avgt   10    1.890 ±  0.050  ns/op    ← LambdaMetafactory 거의 직접
mh                     avgt   10    2.510 ±  0.080  ns/op    ← static final MH도 inline
reflect (inflated)     avgt   10   18.300 ±  0.700  ns/op    ← 18x slower
reflect (no cache)     avgt   10  250.000 ± 30.000  ns/op    ← 매번 getMethod
```

핵심 신호: **Method 객체를 캐싱 안 하면 250배, 캐싱해도 18배**. MethodHandle/LambdaMetafactory는 직접 호출의 2~3배.

---

## 8. 운영 — Framework가 Reflection을 쓰는 패턴

### 8.1 Spring — DI와 BeanDefinition

```
[Spring 시작 시]
─────────────────────────────────
ComponentScan
   │
   ▼
ClassLoader로 .class 스캔 (asm으로 attribute만 읽음, load X)
   │
   ▼
@Component / @Service / @Repository 발견
   │
   ▼
BeanDefinition 생성
   │
   ▼
런타임 instantiation:
   Class<?> c = Class.forName(beanDef.className);
   Constructor<?> ctor = c.getDeclaredConstructor(...);
   Object bean = ctor.newInstance(args);
   │
   ▼
의존성 주입:
   Field f = c.getDeclaredField("userRepository");
   f.setAccessible(true);          ← module 시대에 큰 변화
   f.set(bean, userRepository);
```

**성능 영향**:
- Spring Boot 평균 시작 5~10초의 30~50%가 reflection.
- Field/Method 객체는 BeanDefinition에 캐싱 → 2번째부터는 inflation된 GeneratedAccessor 사용.
- GraalVM Native Image는 build 시점에 reflect-config.json으로 전부 명시 → 시작 즉시.

### 8.2 Jackson — JSON 직렬화

```java
ObjectMapper mapper = new ObjectMapper();
User user = mapper.readValue(json, User.class);
```

내부:
```
1. Class<User>를 받음
2. BeanIntrospector로 getter/setter 추출:
     for (Method m : clazz.getDeclaredMethods()) {
         if (m.getName().startsWith("get") || ...) ...
     }
3. JsonNode 파싱
4. 각 필드:
     - Field 또는 setter Method.invoke(instance, value)
     - 또는 ctor.newInstance(...) (record/immutable)
```

**최적화 패턴**:
- Jackson은 Class<?> → ObjectReader/ObjectWriter 캐시.
- AFTERBURNER 모듈은 ASM으로 직접 클래스 생성 → reflection 회피 (1.5~2x 빠름).
- Blackbird (JDK 11+) — LambdaMetafactory 기반 후속.

### 8.3 Hibernate — ORM 매핑

```
Entity:
  @Entity class User { @Id Long id; String name; ... }

Hibernate 초기화:
  1. @Entity 스캔 → EntityType 메타 생성
  2. PropertyAccessor 생성:
        - Field 접근: reflection (Field.get/set)
        - getter/setter 접근: reflection (Method.invoke)
        - bytecode enhanced: 컴파일 시점에 access method 추가 (Lazy 프록시)

  3. SELECT 결과:
        Object instance = ctor.newInstance();
        for each column:
            propertyAccessor.set(instance, value);  ← reflection
```

**Lazy proxy**: `@OneToMany(fetch = LAZY)`의 collection은 PersistentBag 등 reflection 기반 lazy proxy. ByteBuddy로 entity subclass 생성해 getter 가로채기.

### 8.4 Mockito — Mock 객체 생성

```java
@Mock UserService service;
when(service.findById(1L)).thenReturn(user);
```

내부:
```
1. ByteBuddy로 UserService의 subclass 동적 생성:
      class UserService$$EnhancerByMockito extends UserService {
          MockHandler handler;
          public User findById(Long id) {
              return (User) handler.handle(this, "findById", id);
          }
          ... 모든 public method
      }

2. ClassLoader.defineClass()로 Metaspace에 로드
3. instance 생성 → 모든 호출이 handler로 라우팅
```

**문제**: `final` 클래스나 `final` 메서드는 override 불가 → mock 못 함.
**해결**: Mockito 2+에서 ByteBuddy의 retransform 또는 Java Agent로 우회 (`mockito-inline`).

### 8.5 Spring AOP — JDK Proxy vs CGLIB

```
ProxyFactory.getProxy(target)
   │
   ▼
target에 인터페이스가 있나?
   │
   ├─ Yes (proxyTargetClass=false) ─→ JDK Dynamic Proxy
   │                                     - 인터페이스 구현 클래스 동적 생성
   │                                     - InvocationHandler로 라우팅
   │
   └─ No or proxyTargetClass=true  ─→ CGLIB
                                         - 클래스 subclass 동적 생성 (ASM)
                                         - MethodInterceptor로 라우팅
                                         - final 클래스 불가
```

**Spring Boot 2.x+ 기본**: `proxyTargetClass=true` → 항상 CGLIB. 이유는 일관성과 `@Transactional` 등의 일반 메서드 가로채기.

### 8.6 운영 시나리오 5가지

#### 시나리오 1: Spring 시작이 느림

> "Spring Boot 시작이 30초나 걸린다"

**진단**:
```bash
# 시작 트레이스
java -XX:+PrintGCDetails -Xlog:class+load:file=load.log ...

# 클래스 로드 수
wc -l load.log
# → 1만 개 이상이면 component scan 범위 과도

# JFR
jcmd <pid> JFR.start ...
# → jdk.ClassDefine 이벤트로 GeneratedAccessor 폭증 확인
```

**원인**:
- 너무 광범위한 `@ComponentScan(basePackages = "com")`
- Reflection inflation으로 클래스 폭증

**해결**:
- ComponentScan 범위 축소
- `spring-context-indexer`로 build 시점 인덱스 생성
- `-Dsun.reflect.inflationThreshold=0`로 즉시 generate (warmup 단축)

#### 시나리오 2: Code Cache 압박

> "production에서 `CodeCache is full` warning, JIT 컴파일 중단"

**진단**:
```bash
jcmd <pid> Compiler.codecache
# → Profiled / Non-profiled 사용량
# → Number of methods 비정상적으로 많으면 GeneratedAccessor 의심

jcmd <pid> GC.class_histogram | grep Accessor | wc -l
# → 수만 개 이상이면 reflection inflation 폭주
```

**원인**: Hot reload + 매번 다른 Method 객체 + inflation으로 GeneratedAccessor가 끝없이 생성.

**해결**:
- Method/Field를 ConcurrentMap에 캐싱
- `-XX:ReservedCodeCacheSize=512m`
- `-Dsun.reflect.noInflation=true` (debug 용도 / native만 사용)

#### 시나리오 3: JDK 8 → 17 마이그레이션 폭증

> "JDK 17 올렸더니 InaccessibleObjectException 폭주"

**증상**:
```
Caused by: java.lang.reflect.InaccessibleObjectException:
  Unable to make field private final byte[] java.lang.String.value
  accessible: module java.base does not "opens java.lang" to unnamed module
```

**해결**:
```bash
# 임시 (전체 module 풀기)
--add-opens java.base/java.lang=ALL-UNNAMED
--add-opens java.base/java.util=ALL-UNNAMED
--add-opens java.base/sun.reflect=ALL-UNNAMED

# 영구 (library 업그레이드)
- Lombok 1.18.30+
- Hibernate 6+
- Mockito 5+
- Spring 6+ (auto add-opens)
```

#### 시나리오 4: ThreadLocal + Reflection의 누수

```java
// 흔한 패턴
static ThreadLocal<Map<Class<?>, MethodHandle>> CACHE = new ThreadLocal<>();
```

문제: Map의 key가 `Class<?>` → 동적으로 로드된 클래스가 ClassLoader를 잡음 → CLD unload 안 됨 → OOM:Metaspace.

**해결**: `WeakHashMap<Class<?>, MethodHandle>` 또는 `ClassValue<MethodHandle>` 사용.

#### 시나리오 5: private 필드 접근 실패

```java
Field f = String.class.getDeclaredField("value");
f.setAccessible(true);  // JDK 17에서 InaccessibleObjectException
```

**해결**: 애초에 안 하는 게 정답. JDK 가이드는 private API 직접 접근을 금지.
- VarHandle (Field의 MethodHandle 버전)으로 public field 다루기
- Records (JDK 16+)로 immutable 데이터 객체 — accessor가 자동 생성

---

## 9. 꼬리질문 트리 (가지별)

### Q1 [가지 ②]. `String.class`는 어디에 있고 어떻게 동작합니까?

> Heap의 `Class<String>` mirror 객체. JVM이 String 클래스를 로드할 때 Metaspace의 InstanceKlass와 동시에 Heap에 mirror 생성. `String.class` 리터럴은 bytecode `ldc_w`로 Constant Pool의 ClassRef를 resolve해서 mirror push. 메서드 호출 아님, 컴파일 타임에 상수.

**🪝 Q1-1: mirror와 InstanceKlass는 어떻게 연결되어 있나요?**
> 양방향. mirror에 `_klass` 필드 → InstanceKlass. InstanceKlass에 `_java_mirror` 필드 → mirror. 객체 헤더의 Klass Pointer는 mirror가 아니라 **InstanceKlass를 직접** 가리킴.

**🪝🪝 Q1-1-1: `obj.getClass()`는 어떻게 동작?**
> 객체 헤더의 Klass Ptr 한 번 dereferencing 후 그것의 `_java_mirror` 반환. HotSpot intrinsic으로 거의 무비용. compressed oop이면 4-byte load + base + shift.

### Q2 [가지 ④]. Method.invoke()가 왜 느린가요?

> 다섯 가지 비용:
> 1. **Argument boxing** — primitive를 wrapper로 (Integer.valueOf 등)
> 2. **Access check** — SecurityManager / module 검사
> 3. **Megamorphic call site** — 다양한 GeneratedAccessor가 같은 invoke 사이트로 → C2 inline 불가
> 4. **첫 15회 JNI** — native transition은 일반 호출의 50배
> 5. **Result boxing** — 반환값도 wrapper로

**🪝 Q2-1: NativeMethodAccessor와 GeneratedMethodAccessor는 뭐가 다른가요?**
> 처음 15회는 NativeMethodAccessor가 JNI로 처리. 16회 넘으면 inflation으로 GeneratedMethodAccessor라는 새 클래스를 ASM 비슷한 방식으로 동적 생성 → 그 안에 정적 캐스트 + 직접 invokevirtual 박힘. JNI 비용 사라지고 일반 dispatch. `-Dsun.reflect.inflationThreshold=N`으로 조정.

**🪝🪝 Q2-1-1: GeneratedAccessor 클래스는 어디에 살죠?**
> 새 ClassLoader (MagicAccessorImpl 계열)에 정의 → Metaspace에 InstanceKlass + Heap에 mirror. bytecode는 JIT 컴파일 후 Code Cache. Method 객체에 수만 개 invoke 사이트가 있으면 GeneratedAccessor도 수만 개 → Code Cache 압박.

### Q3 [가지 ⑥]. MethodHandle은 왜 Reflection보다 빠른가요?

> 두 가지 이유:
> 1. **invoke target이 상수처럼 취급** — static final MethodHandle을 JIT이 inline. invoke 자체가 사라짐.
> 2. **LambdaForm 메커니즘** — MethodHandle의 invoke는 내부적으로 LambdaForm IR로 표현되어 JIT-friendly.
>
> 단, MethodHandle이 지역 변수면 JIT이 상수로 못 잡음 → reflection만큼 느려질 수 있음. 반드시 `static final`.

**🪝 Q3-1: VarHandle은 뭔가요?**
> JDK 9+ Field 접근의 MethodHandle 버전. `AtomicInteger`처럼 volatile read/write + CAS를 표준 API로. AtomicReferenceFieldUpdater의 진화형. setAccessible 우회 가능 (privateLookup).

**🪝🪝 Q3-1-1: VarHandle이 Atomic*보다 좋은 점은?**
> ① 모든 필드에 적용 가능 (Atomic*는 자기 자신만), ② boxing 없음 (Atomic<Integer> vs VarHandle int), ③ MemoryOrder를 세밀히 (acquire/release/opaque/plain). 단점은 코드가 verbose해짐.

### Q4 [가지 ⑥]. LambdaMetafactory는 어떻게 Reflection을 대체하나요?

> JDK 8+ `invokedynamic`으로 Method → Functional Interface 구현체 변환.
>
> ```java
> CallSite cs = LambdaMetafactory.metafactory(
>     lookup, "apply", invokedType, samMethodType, implMethod, instantiatedMethodType);
> Function<String, Integer> f = (Function<String, Integer>) cs.getTarget().invokeExact();
> ```
>
> 첫 호출 시 metafactory가 Functional Interface 구현 클래스를 **딱 한 번** 생성, 그 후 호출은 일반 invokevirtual. 직접 호출의 2~3배 비용 (boxing만). Spring 5+ 일부 영역이 이 방식으로 Reflection 호출 대체.

**🪝 Q4-1: 그럼 모든 Reflection을 LambdaMetafactory로 바꾸면 안 되나요?**
> 못 함. LambdaMetafactory는 **Functional Interface (SAM)**만 wrap 가능. 일반 `Method.invoke(obj, args)`처럼 가변 인자 + 동적 타입은 불가. Spring DI 같은 곳은 인자 수가 다양해서 일반 Reflection 또는 MethodHandle.invokeWithArguments 사용.

### Q5 [가지 ⑤]. JDK 9 Module이 Reflection에 어떤 영향을 줬나요?

> setAccessible(true)가 더 이상 "무조건 가능"이 아님. 모듈이 `opens java.lang to ALL-UNNAMED` 같이 명시해야 deep reflection 가능. JDK 17부터는 warning이 InaccessibleObjectException으로 격상.
>
> 해결: 실행 시 `--add-opens java.base/java.lang=ALL-UNNAMED`. 또는 자기 모듈이 직접 `opens` 선언. Spring/Hibernate/Lombok 등은 알아서 처리.

**🪝 Q5-1: --add-opens와 --add-exports의 차이?**
> `--add-exports`: 컴파일 + 일반 reflection 허용. `--add-opens`: 그 위에 setAccessible(true)로 private 접근까지. 둘 다 module을 외부로 푸는 escape hatch — 신규 코드는 안 쓰는 게 정답.

**🪝🪝 Q5-1-1: Lombok 같은 도구는 어떻게 살아남나요?**
> Lombok은 javac annotation processor를 통해 **컴파일 시점**에 bytecode 추가 — reflection 안 함. 다만 일부 내부 처리에서 `com.sun.tools.javac.*` 접근이 필요 → JDK 16+에서 `--add-opens jdk.compiler/com.sun.tools.javac.*=ALL-UNNAMED` 명시.

### Q6 [가지 ⑦]. Dynamic Proxy vs CGLIB의 차이는?

> **JDK Dynamic Proxy**: `java.lang.reflect.Proxy.newProxyInstance(loader, interfaces, handler)`. 인터페이스 구현 클래스를 동적 생성. **인터페이스만 가능**, 클래스의 일반 메서드는 가로채기 불가.
>
> **CGLIB**: ASM 라이브러리로 클래스의 subclass를 동적 생성. `MethodInterceptor.intercept()`로 모든 호출 가로채기. **final 클래스/메서드 불가**. Spring Boot 2.x+의 기본 AOP 메커니즘.
>
> Spring `ProxyFactory`: 인터페이스 있고 `proxyTargetClass=false` → JDK Proxy. 아니면 CGLIB. 일관성 위해 보통 CGLIB 강제.

**🪝 Q6-1: CGLIB은 어떤 라이브러리로 대체되고 있나요?**
> ByteBuddy. CGLIB은 마지막 릴리스가 2019년, ASM 의존성과 JDK 호환성 문제. Mockito가 ByteBuddy로 갈아탔고, Hibernate도 이미. Spring 6+도 일부 영역 ByteBuddy 검토 중. ByteBuddy는 fluent API + retransform 지원 + JDK 호환성 ↑.

### Q7 [가지 ⑦]. Spring Boot 시작이 갑자기 30초로 늘었습니다. 진단?

> 단계:
> 1. `-Xlog:class+load:file=load.log` — 로드된 클래스 수가 1만 이상이면 component scan 과도.
> 2. `jcmd <pid> GC.class_histogram` — GeneratedMethodAccessor가 수천 개면 reflection inflation 폭증.
> 3. JFR `jdk.ClassDefine` 이벤트 — 어떤 클래스가 어디서 생성되는지.
> 4. `jcmd <pid> Compiler.codecache` — Code Cache 사용량.
> 5. async-profiler로 시작 구간 캡쳐 — Reflection이 hot인지 확인.
>
> **흔한 원인**:
> - `@ComponentScan(basePackages = "com")` 너무 넓음
> - JPA EntityManagerFactory 초기화 (수많은 @Entity reflection 스캔)
> - Jackson ObjectMapper의 default deserializer 등록 폭증
> - JDK 8 → 17 마이그레이션 시 module 경고로 인한 retry 폭주
>
> **해결**:
> - ComponentScan 범위 좁히기
> - spring-context-indexer (build 시점 META-INF/spring.components 생성)
> - `-Dsun.reflect.inflationThreshold=0` (즉시 generate)
> - Lazy bean (`@Lazy`) 적극 활용
> - 궁극적: GraalVM Native Image (시작 50~100ms)

### Q8 (Killer) [통합]. "Reflection이 megamorphic이라 JIT inline 못 한다"의 정확한 의미는?

> JIT의 inline은 **호출 사이트의 target이 충분히 일관됨**을 전제. 호출 사이트의 receiver 타입이:
> - **Monomorphic** (1종) → 직접 inline
> - **Bimorphic** (2종) → if-else로 두 path 모두 inline
> - **Megamorphic** (3종+) → vtable lookup으로만 처리, inline 불가
>
> Reflection의 `Method.invoke()` 호출 사이트는 framework 전역에서 공유 → 수십·수백 종의 GeneratedAccessor가 같은 호출 사이트로 들어옴 → megamorphic 확정 → C2가 inline 포기 → vtable lookup이 매번 발생.
>
> MethodHandle은 이걸 해결 — `static final MethodHandle mh`는 JIT이 mh 자체를 상수로 인식 → invoke target이 컴파일 타임 상수처럼 취급 → inline 가능. 그래서 같은 reflection 같은 결과인데 MH가 빠르다.

**🪝 Q8-1: 그럼 Method 객체를 static final로 잡으면 어떻게 되나요?**
> Method 객체가 final이어도 `method.invoke()`의 내부 dispatch가 DelegatingAccessor → GeneratedAccessor 경로를 거쳐서 **invoke 사이트 자체는 megamorphic 그대로**. JIT이 Method 객체의 final성을 활용해 inline 못 함. → static final 효과는 MethodHandle 한정.

**🪝🪝 Q8-1-1: 그럼 `MethodHandle.invokeExact`와 `MethodHandle.invoke`의 차이는?**
> `invokeExact`는 signature가 정확히 일치해야 함 (컴파일 타임 검증) → JIT이 더 공격적으로 inline. `invoke`는 signature 변환을 자동 → 약간 느림. 성능 critical하면 invokeExact + 정확한 MethodType.

### Q9 [가지 ⑤]. `setAccessible(true)`는 JDK 17 이후로 어떻게 동작하나요?

> Module이 명시적으로 `opens` 한 패키지가 아니면 `InaccessibleObjectException`. JDK 9~16은 warning. JDK 17부터는 error. 
> 우회 방법:
> 1. `--add-opens` JVM 옵션 (런타임).
> 2. 자기 모듈의 module-info.java에 `opens` 선언 (영구).
> 3. `Lookup.privateLookupIn(targetClass, originalLookup)` → MethodHandle/VarHandle로 우회.
> 
> 단, java.base 같은 시스템 모듈을 무리하게 풀면 다음 LTS에서 막힐 위험. JDK 21+ Foreign Function & Memory API가 sun.misc.Unsafe 대체로 진행 중 — 그게 끝나면 reflective access는 점점 더 제한.

---

## 10. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 1분 안에 그릴 수 있다 (루트 + 7가지 + 각 키워드 3개)
- [ ] 가지 ①: Reflection이 왜 존재하나 (compile-time에 모르는 타입 + 메타프로그래밍 + framework 기반)
- [ ] 가지 ②: java.lang.reflect 패키지 핵심 7개 클래스 (Class/Method/Field/Constructor/Proxy/InvocationHandler/AccessibleObject)
- [ ] 가지 ③: Class.forName vs ClassLoader.loadClass의 initialization 차이
- [ ] 가지 ③: Foo.class 리터럴이 어떻게 동작 (ldc_w bytecode)
- [ ] 가지 ④: Method.invoke의 두 경로 (Native 15회 → Generated inflation) + 각 비용 5가지
- [ ] 가지 ④: 왜 JIT inline 못 하나 (megamorphic call site)
- [ ] 가지 ⑤: JDK 9 Module이 setAccessible에 준 변화 + JDK 17 Error 격상
- [ ] 가지 ⑥: MethodHandle이 Reflection보다 빠른 이유 2가지 (static final inline + LambdaForm)
- [ ] 가지 ⑥: LambdaMetafactory가 Reflection을 어떻게 대체 (invokedynamic + Functional Interface)
- [ ] 가지 ⑥: Dynamic Proxy vs CGLIB vs ByteBuddy
- [ ] 가지 ⑦: Spring/Jackson/Hibernate/Mockito가 각각 어떤 패턴으로 reflection을 쓰나
- [ ] 운영 시나리오 5가지: 시작 느림 / Code Cache 압박 / JDK 마이그레이션 / ThreadLocal 누수 / private 필드 접근
- [ ] 측정: JFR(jdk.ClassDefine, ReflectiveAccess), async-profiler(GeneratedAccessor 식별), PrintCompilation(inline 여부)
- [ ] 9장 꼬리질문 9개에 막힘없이 답한다

---

## 다음 단계

- → [03. Threads](./03-threads.md): Thread/ExecutorService/ForkJoinPool/Virtual Thread
- ← [01. Generics](./01-generics.md): type erasure와 Signature attribute
- ← [jvm/02-runtime-data-areas/02-metaspace-and-class-space.md](../jvm/02-runtime-data-areas/02-metaspace-and-class-space.md): Class<?> mirror ↔ InstanceKlass 양방향
- ← [jvm/02-runtime-data-areas/04-code-cache.md](../jvm/02-runtime-data-areas/04-code-cache.md): GeneratedAccessor가 사는 Code Cache, JIT inline의 본질

## 참고

- **JEP 292 — invokedynamic**: https://openjdk.org/jeps/292
- **JEP 274 — Enhanced Method Handles**: https://openjdk.org/jeps/274
- **JEP 261 — Module System**: https://openjdk.org/jeps/261
- **JEP 396 — Strongly Encapsulate JDK Internals**: https://openjdk.org/jeps/396 (JDK 16, warning)
- **JEP 403 — Strongly Encapsulate JDK Internals** (JDK 17, error): https://openjdk.org/jeps/403
- **JEP 416 — Reimplement Core Reflection with Method Handles** (JDK 18): https://openjdk.org/jeps/416
- **HotSpot Reflection 소스**: https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/jdk/internal/reflect/
- **MethodHandles & LambdaMetafactory JavaDoc**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/package-summary.html
- **ByteBuddy 공식 가이드**: https://bytebuddy.net/
- **Aleksey Shipilëv — The Black Magic of (Java 9) String Concatenation**: https://shipilev.net/blog/2014/string-concatenation-by-the-numbers/ (invokedynamic 실전 분석)
- **John Rose — invokedynamic 설계**: https://blogs.oracle.com/javamagazine/post/behind-the-scenes-how-do-lambda-expressions-really-work-in-java
- **Spring Boot Native Image — Reflection Hints**: https://docs.spring.io/spring-boot/docs/current/reference/html/native-image.html
