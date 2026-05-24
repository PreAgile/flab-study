# 02. Reflection — 런타임에 자기 자신을 들여다보는 코드

> "Reflection? `Method.invoke()` 같은 거" 라고 답하면 입문자.
> "Reflection은 java.lang.reflect 패키지를 통해 ClassLoader가 Metaspace에 로드해둔 InstanceKlass 메타데이터를 Heap의 Class<?> mirror로 노출하는 메타프로그래밍 facility다. Method.invoke()는 처음에는 NativeMethodAccessorImpl이 JNI로 처리하다가 inflationThreshold(기본 15)를 넘으면 GeneratedMethodAccessor bytecode를 동적으로 만들어 Code Cache에 올리고 그 다음부터는 invokevirtual로 직접 dispatch한다. 그래도 호출 사이트가 megamorphic이라 JIT inline은 안 된다. MethodHandle은 static final로 잡으면 invoke target이 상수로 취급되어 inline 가능, LambdaMetafactory는 invokedynamic CallSite로 Functional Interface 구현체를 1회 만들고 그 다음부터는 직접 호출 수준 빠르다." 라고 말할 수 있어야 한다.

---

## 목차

1. 정의와 존재 이유
2. java.lang.reflect 핵심 클래스 표
3. 메모리 그림 — Class mirror ↔ InstanceKlass
4. Method.invoke() 두 경로 (Native → Generated inflation)
5. Reflection vs MethodHandle vs LambdaMetafactory vs ByteBuddy
6. Dynamic Proxy vs CGLIB
7. JDK 9+ Module / setAccessible
8. Framework 사용 패턴 (Spring/Jackson/Hibernate/Mockito)
9. 측정·진단 (JFR, async-profiler, JMH 신호)
10. 운영 시나리오
11. 꼬리질문

---

## 1. 정의

**Reflection (메타프로그래밍 facility)**: 컴파일 시점에 알지 못하는 타입의 객체를 런타임에 조회·생성·조작할 수 있게 하는 표준 라이브러리. `java.lang.reflect` 패키지를 통해 노출. 본질은 Heap의 `Class<?>` mirror를 통해 Metaspace의 `InstanceKlass` 메타데이터에 도달하는 것. Spring DI, Jackson 직렬화, Hibernate ORM, Mockito mock이 모두 이 위에서 동작. 비용의 본질은 **JIT inline 불가(megamorphic call site)와 inflation 비용** — MethodHandle / LambdaMetafactory / Bytecode generation이 그 한계를 깬다.

비교: Reflection 없는 세계에서는 모든 타입을 compile-time에 알아야 하니 Spring DI도, Jackson 자동 매핑도, Hibernate ORM도, Mockito도 불가능. Reflection은 "코드를 다루는 코드"를 가능하게 하는 framework·library의 표준 기술.

---

## 2. java.lang.reflect 핵심 클래스

| 클래스 | 진입점 | 핵심 API | 비용 모델 |
|---|---|---|---|
| **Class<T>** | `Foo.class`, `Class.forName`, `obj.getClass()` | `getMethod`, `getField`, `getConstructor`, `getDeclared*`, `getAnnotation`, `getInterfaces`, `getSuperclass` | mirror lookup — 거의 무비용 |
| **Method** | `Class.getMethod(name, params)` | `invoke(obj, args)`, `setAccessible(true)`, `getReturnType` | inflation 후 ~18x slowdown |
| **Field** | `Class.getDeclaredField(name)` | `get(obj)`, `set(obj, value)`, `setAccessible` | NativeFieldAccessor → GeneratedFieldAccessor |
| **Constructor** | `Class.getDeclaredConstructor(params)` | `newInstance(args)` | NativeConstructorAccessor → GeneratedConstructorAccessor |
| **Proxy** | `Proxy.newProxyInstance(loader, ifaces, handler)` | InvocationHandler로 라우팅 | 인터페이스만 가능 |
| **AnnotatedElement** | Class/Method/Field/Constructor/Parameter 모두 implement | `getAnnotation`, `isAnnotationPresent` | 보조 |
| **Modifier / Array / Parameter** | static 유틸 | bitmask 조회 / 배열 생성 / JDK 8+ 파라미터 메타 | 보조 |

**Class.forName vs ClassLoader.loadClass**:
```
Class.forName("com.foo.Bar")                ClassLoader.loadClass("com.foo.Bar")
─────────────────────────                   ─────────────────────────
1. 클래스 로드                                1. 클래스 로드
2. ★ Initialization (static {} 실행)          2. ★ Initialization 안 함 (lazy)

용도: JDBC 드라이버 등록                       용도: 단순 로드, 존재 확인
  Class.forName("org.h2.Driver")              - DriverManager 자동 등록 안 됨
  → static { DriverManager.register(...) }

3-arg: Class.forName(name, initialize, loader) — initialize=false면 loadClass와 유사
```
**시니어 함정**: Spring component scan에서 `Class.forName("com.foo.NotExist")`를 호출하면 ClassNotFoundException + 있는 경우 static initialization까지 실행. 단지 존재만 확인하려면 `Class.forName(name, false, loader)` 또는 `ClassLoader.loadClass`로 초기화 회피.

**`Foo.class` 리터럴**: 메서드 호출이 아닌 `ldc_w` bytecode. 컴파일 시점에 ConstantPool entry로 박힘 → 첫 사용 시 ClassLoader resolve → Heap mirror 반환. `Class.forName("Foo")`의 String lookup과는 경로가 다름.

**`obj.getClass()`**: 객체 헤더의 Klass Pointer → `_java_mirror` 반환. HotSpot intrinsic으로 거의 무비용 (compressed oop이면 4-byte load + base + shift).

---

## 3. 메모리 그림 — Class mirror ↔ InstanceKlass

```
[Java 코드]
   Class<String> c = String.class;
   Method m = c.getMethod("length");
   m.invoke("hello");

JVM Process
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
┌─────────────────────────────┐   ┌──────────────────────────────────┐
│ Heap                          │   │ Metaspace                          │
│                               │   │                                    │
│  Class<String> mirror         │   │  InstanceKlass for String          │
│   ├ _klass ──────────────────►│──►│   ├ _java_mirror ◄────────────────┤
│   ├ name "String"             │   │   ├ _methods[length, ...]          │
│   └ classLoader               │   │   ├ _fields                         │
│                               │   │   ├ _constants (CP)                 │
│  Method "length"              │   │   └ vtable / itable                 │
│   ├ clazz ───────────────────►│──►│  Method 메타 (bytecode ptr, _code) │
│   └ methodAccessor ───┐       │   │                                    │
│                       │       │   │                                    │
│  NativeMethodAccessor◄┘       │   │  Compressed Class Space            │
│   (처음 15회, JNI)            │   │   (Klass 포인터 압축)               │
│                               │   │                                    │
│       ↓ inflation              │   │                                    │
│  GeneratedMethodAccessor5 ────┼───┼──► Code Cache                      │
│   (동적 bytecode)              │   │     bytecode → JIT compile         │
└─────────────────────────────┘   └──── → native invoke ─────────────────┘
```

**양방향 링크**: mirror의 `_klass` → InstanceKlass, InstanceKlass의 `_java_mirror` → mirror. 객체 헤더의 Klass Pointer는 **mirror가 아니라 InstanceKlass를 직접** 가리킴.

---

## 4. Method.invoke() 두 경로 — Inflation ⭐⭐

`Method`는 내부에 `MethodAccessor`를 lazy init. 처음과 임계 이후 구현이 다르다.

```
java.lang.reflect.Method
   │
   └ DelegatingMethodAccessorImpl  ← 양 경로 사이의 다리
         delegate: MethodAccessorImpl   (Native → Generated로 교체)
             │
             ├──[N ≤ 15]──→ NativeMethodAccessorImpl
             │                 │
             │                 └ invoke0() = JNI native call
             │                      HotSpot Reflection::invoke
             │                       1) argument unbox (Integer.intValue 등)
             │                       2) access check (SecurityManager / module)
             │                       3) vtable/itable lookup (virtual dispatch)
             │                       4) native transition (~수십 cycle)
             │                       5) interpreter/JIT entry로 jump
             │                       6) result boxing
             │
             └──[N = 16+, inflation]──→ GeneratedMethodAccessor5 (동적 생성)
                            public Object invoke(Object obj, Object[] args) {
                                String t = (String) obj;            // 정적 캐스트
                                int r = t.length();                  // 직접 invokevirtual
                                return Integer.valueOf(r);           // boxing
                            }
                            └ MagicAccessorImpl 계열 새 ClassLoader에 정의
                              → access check 우회, Code Cache 진입

호출 사이트 문제: framework 전역에서 Method.invoke() 사이트가 공유됨
→ 수많은 GeneratedAccessor (서로 다른 InstanceKlass) 가 같은 사이트로 들어옴
→ receiver 타입이 3종+ = megamorphic 확정
→ C2 inline 포기, vtable lookup 매번
```

**왜 처음엔 native?**: 동적 클래스 생성은 ~수십 ms로 비싸다. 한두 번 호출되고 끝날 reflection에 비용 들이면 손해 — 그래서 임계(`inflationThreshold`) 도입. `-Dsun.reflect.inflationThreshold=0` 즉시 generate (warmup 단축), `-Dsun.reflect.noInflation=true` 끔 (debug용).

**DelegatingMethodAccessorImpl**: 실제 Method가 들고 있는 건 Delegating 한 겹. inflation 시 `delegate` 필드만 Native → Generated로 교체하면 같은 Method 객체를 들고 있던 모든 caller가 자동으로 빠른 경로 진입.

**Field / Constructor도 같은 구조**: NativeFieldAccessor → GeneratedFieldAccessor, NativeConstructorAccessor → GeneratedConstructorAccessor. 모두 동일 패턴 — native → inflation 임계 → 동적 bytecode generation.

**JDK 18+ (JEP 416)**: MethodAccessor가 MethodHandle 기반으로 reimplement. GeneratedAccessor 클래스 폭증이 사라져 Code Cache 압박 감소, warmup 단축. 시니어가 알아야 할 변화.

**NativeMethodAccessorImpl 핵심 코드** (간략화):
```java
class NativeMethodAccessorImpl extends MethodAccessorImpl {
    private DelegatingMethodAccessorImpl parent;
    private int numInvocations;

    public Object invoke(Object obj, Object[] args) {
        if (++numInvocations > ReflectionFactory.inflationThreshold()) {
            // 임계 도달 → GeneratedAccessor로 inflate
            MethodAccessorImpl gen = (MethodAccessorImpl)
                new MethodAccessorGenerator().generateMethod(...);
            parent.setDelegate(gen);  // delegate 필드만 교체
        }
        return invoke0(method, obj, args);  // ★ JNI native
    }
    private static native Object invoke0(Method m, Object obj, Object[] args);
}
```
`parent.setDelegate(gen)` 한 줄로 모든 caller가 자동으로 빠른 경로로 전환되는 게 핵심.

---

## 5. Reflection vs MethodHandle vs LambdaMetafactory vs ByteBuddy ⭐⭐

| | Reflection | MethodHandle | LambdaMetafactory | ByteBuddy / ASM |
|---|---|---|---|---|
| **도입** | JDK 1.1 | JDK 7 (JEP 292 invokedynamic) | JDK 8 | external library |
| **JIT inline** | ❌ megamorphic | ✅ static final이면 | ✅ | ✅ (생성 후 일반 호출) |
| **호출 비용** | ~18x (inflated) / ~250x (no cache) | ~2.5x (static final), ~30x (지역 변수) | ~1.9x | 1x |
| **첫 호출** | 15회까지 JNI (가장 느림) | lookup 1회 비싸지만 이후 빠름 | metafactory 1회 | 클래스 generation ~수십 ms |
| **메모리** | GeneratedAccessor 클래스 폭증 | LambdaForm | FI 인스턴스 1개 | 생성한 클래스만 |
| **표현력** | 모든 메서드 호출 | 모든 메서드 호출 | Functional Interface (SAM)만 | 무제한 |
| **module** | `--add-opens` | `Lookup.privateLookupIn` | `Lookup.privateLookupIn` | `defineClass` 권한 |
| **사용처** | Spring/Jackson/Hibernate 일반 | java.lang.invoke 내부, Spring 일부 | java.util.function, lambda | Mockito, Hibernate proxy |

**호출 비용 시각화** (cycle 단위 근사):
```
직접 호출                    ≈ 1~3   obj.method() → call [_code]
LambdaMetafactory            ≈ 3~5   FI 구현체의 method() → invokevirtual
MethodHandle (static final)  ≈ 5~10  MH.invokeExact → JIT이 상수 인식 → inline
MethodHandle (지역 변수)      ≈ 30~50 상수 못 잡음 → 매 호출 dispatch
Reflection (inflated)        ≈ 50~100 GeneratedAccessor + megamorphic
Reflection (native, 첫 15회)  ≈ 500~1000 JNI transition, 가장 느림
```

**결정 매트릭스**:
- target이 컴파일 타임에 알려진다 → 직접 호출, Reflection 쓸 이유 없음
- 런타임 1회 결정 후 안 바뀜 + Functional Interface 가능 → **LambdaMetafactory** (가장 빠름)
- 런타임 1회 결정 후 안 바뀜 + 일반 호출 → **MethodHandle (static final)**
- 자주 바뀜 + 성능 critical → **ByteBuddy로 클래스 생성** 후 일반 호출
- 자주 바뀜 + 간단함 우선 → **Reflection**

**시니어 한 줄**: Reflection은 편의성, MethodHandle은 성능, LambdaMetafactory는 함수형 통합, ByteBuddy는 무제한 표현력. 실전에서는 layered — Spring은 일반 호출에 Reflection, hot path는 MethodHandle, AOP 프록시는 CGLIB / ByteBuddy.

**왜 LambdaMetafactory가 빠른가?**: JDK 8 lambda를 익명 클래스로 구현하면 매 lambda마다 클래스 + 객체 생성으로 비쌈. invokedynamic + LambdaMetafactory가 첫 호출 시 Functional Interface 구현 클래스를 **한 번** 생성하고 CallSite target은 그 인스턴스를 반환하는 MethodHandle. 이후엔 그냥 인스턴스 반환 + invokevirtual.

---

## 6. Dynamic Proxy vs CGLIB

**JDK Dynamic Proxy**는 **인터페이스만** 동적 구현. `Proxy.newProxyInstance`로 `$Proxy0 extends Proxy implements UserService`를 생성하고 모든 메서드를 `InvocationHandler.invoke(proxy, method, args)`로 라우팅. **CGLIB**은 ASM으로 **클래스의 subclass**를 생성 (`UserService$$EnhancerByCGLIB extends UserService`), `MethodInterceptor.intercept()`로 라우팅 — `final` 클래스 / `final` 메서드는 override 불가라 가로채기 불가. Spring Boot 2.x+는 `proxyTargetClass=true` 기본 → 항상 CGLIB. CGLIB는 사실상 동결(마지막 릴리스 2019), 후속은 ByteBuddy (Mockito 5+, Hibernate 6+ 채택, fluent API + retransform + JDK 호환성 우수).

```
[JDK Dynamic Proxy]                  [CGLIB]
───────────────────                   ──────────
인터페이스만 가능                       클래스 subclass 생성
                                      (final 클래스/메서드 불가)

interface UserService {}              class UserService {}
   ▲                                      ▲
   │ implements                           │ extends
   │                                      │
$Proxy0 extends Proxy                  UserService$$EnhancerByCGLIB
   ├ InvocationHandler h               (ASM이 동적 생성)
   └ 모든 method →                       │
      h.invoke(proxy, method, args)     모든 method override →
                                          MethodInterceptor.intercept()

생성: java.lang.reflect.Proxy          생성: cglib.ProxyGenerator (ASM)
  → ClassLoader.defineClass             → ClassLoader.defineClass
  → Metaspace InstanceKlass             → Metaspace InstanceKlass
  → Heap mirror & instance              → Heap mirror & instance
```

**Spring AOP 결정 흐름**:
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
                                         - final 클래스/메서드 불가
```
Spring Boot 2.x+는 `@Transactional` 등의 일반 메서드 가로채기 일관성을 위해 CGLIB 강제 (`proxyTargetClass=true` 기본).

---

## 7. JDK 9+ Module / setAccessible

JDK 1.1~8까지 `setAccessible(true)`는 무조건 성공해 "캡슐화는 권장사항"에 불과했다. **JDK 9 JPMS** (Java Platform Module System) 도입으로 모든 모듈은 명시적으로 `exports`(컴파일+일반 reflection 허용)와 `opens`(deep reflection까지 허용)한 패키지만 외부에 노출. JDK 9~16은 "Illegal reflective access" warning, **JDK 17부터 `InaccessibleObjectException` Error로 격상** (JEP 403 — Strongly Encapsulate JDK Internals). 우회는 ① 런타임 `--add-opens java.base/java.lang=ALL-UNNAMED`, ② 자기 모듈 module-info.java에서 `opens` 선언 (영구), ③ `Lookup.privateLookupIn(targetClass, lookup)`으로 MethodHandle / VarHandle 경유. Spring 6 / Hibernate 6 / Lombok 1.18.30+ / Mockito 5+는 알아서 처리. `--add-exports`는 컴파일+일반 reflection만, `--add-opens`는 그 위에 setAccessible까지 — 둘 다 escape hatch, 신규 코드는 안 쓰는 게 정답.

**파생**: VarHandle은 Field 접근의 MethodHandle 버전 (JDK 9+, JEP 193) — `Atomic*`보다 우월(모든 필드 대상, no boxing, MemoryOrder를 acquire/release/opaque/plain으로 세밀). invokedynamic은 JEP 292의 5번째 호출 명령으로 MethodHandle/LambdaMetafactory의 기반 — 첫 호출에 bootstrap method가 CallSite 반환, 이후엔 CallSite.target.invoke. SecurityManager는 JDK 17 deprecate (JEP 411), JDK 24+ 제거 예정 — module이 그 자리를 대체. Project Leyden은 reflection target을 build 시점에 미리 파악해 AOT 친화화 (GraalVM Native Image의 `reflect-config.json`을 더 자연스럽게).

---

## 8. Framework 사용 패턴

| Framework | 무엇에 reflection 사용 | 최적화 | 시니어 신호 |
|---|---|---|---|
| **Spring** | ComponentScan → `Class.forName` → `Constructor.newInstance` → Field 주입 (`f.setAccessible(true); f.set(bean, dep)`) | BeanDefinition에 Method/Field 캐시, `spring-context-indexer` (build 시 META-INF/spring.components 생성), GraalVM Native Image | 시작 5~10초의 30~50%가 reflection; 두 번째부터는 inflated GeneratedAccessor 사용 |
| **Jackson** | BeanIntrospector로 getter/setter 추출 → setter `Method.invoke` 또는 `Field.set` → record/immutable은 `ctor.newInstance` | Class<?> → ObjectReader/Writer 캐시; Afterburner (ASM 직접 클래스 생성, 1.5~2x 빠름); Blackbird (JDK 11+, LambdaMetafactory 기반) | reflection 회피 모듈로 latency-critical path 가속 |
| **Hibernate** | @Entity 스캔 → PropertyAccessor (Field 접근 또는 getter/setter Method) → `Constructor.newInstance` → 컬럼별 set | ByteBuddy로 entity enhanced (lazy proxy, dirty tracking); `@OneToMany(fetch = LAZY)` collection은 PersistentBag / ByteBuddy subclass | enhanced 안 한 entity는 매 컬럼이 reflection |
| **Mockito** | ByteBuddy로 target의 subclass 생성 → 모든 public method를 MockHandler로 라우팅 | `mockito-inline`은 Java Agent + retransform으로 `final` 우회 | `final` 클래스 mock 가능 여부가 라이브러리 분기점 |
| **Spring AOP** | `ProxyFactory.getProxy` — 인터페이스+`proxyTargetClass=false` → JDK Proxy, 아니면 CGLIB | Spring Boot 2.x+ 기본 CGLIB | `@Transactional` self-invocation 함정 — 같은 클래스 내부 호출은 proxy 우회 |

---

## 9. 측정·진단

### JFR로 reflection 추적
```bash
jcmd <pid> JFR.start name=reflect duration=300s settings=profile filename=reflect.jfr
# 핵심 이벤트:
#   jdk.ReflectiveAccess  — JDK 17+ illegal access 추적
#   jdk.ClassDefine       — GeneratedAccessor 동적 생성 (얼마나 생성됐나)
#   jdk.Compilation       — JIT 컴파일 (inflation generated class 포함)
jfr print --events jdk.ClassDefine reflect.jfr | grep Accessor
```

### async-profiler로 hot path 추적
```bash
async-profiler -d 60 -e cpu -f reflect.html <pid>
```
flame graph 패턴:
```
java/lang/reflect/Method.invoke
 └ DelegatingMethodAccessorImpl.invoke
    ├ NativeMethodAccessorImpl.invoke   ★ Method 객체 캐싱 안 함 (매번 첫 호출)
    │  └ Method::invoke_native            JNI transition
    └ GeneratedMethodAccessor47.invoke  ★ inflation 후, 정상 hot path
```
**시니어 신호**: `NativeMethodAccessorImpl::invoke`가 hot에 보이면 reflection을 매번 새 Method 객체로 부른다는 뜻 (캐싱 누락). `GeneratedMethodAccessor` 클래스가 수만 개면 reflection 호출 사이트 폭증, Code Cache 압박 가능.

### PrintCompilation으로 JIT 추적
```bash
java -XX:+PrintCompilation -XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining ...
# 1234 234 3  sun.reflect.GeneratedMethodAccessor47::invoke (47 bytes)
#               @ 12 com.foo.MyClass::myMethod (8 bytes)   inline (hot)
# 1234 234 not entrant  sun.reflect.GeneratedMethodAccessor47::invoke  ← deopt
```
"not entrant"는 receiver 타입 가정이 깨졌다는 뜻 — megamorphic 진행 신호.

### GeneratedAccessor 클래스 수 측정
```bash
jcmd <pid> GC.class_histogram | grep -i Accessor
# 수만 개면 inflation 폭주 — inflationThreshold 조정 또는 Method 캐싱 누수 의심
```

### JMH 의사 결과 (i7, JDK 21)
```
Benchmark              Mode  Cnt    Score    Error  Units
direct                 avgt   10    1.012 ±  0.020  ns/op
lambdaApply            avgt   10    1.890 ±  0.050  ns/op   ← LambdaMetafactory 거의 직접
mh (static final)      avgt   10    2.510 ±  0.080  ns/op   ← invokeExact inline
reflect (inflated)     avgt   10   18.300 ±  0.700  ns/op   ← 18x
reflect (no cache)     avgt   10  250.000 ± 30.000  ns/op   ← 매번 getMethod = 250x
```
**핵심 신호**: Method 객체를 캐싱 안 하면 250배, 캐싱해도 18배. MethodHandle / LambdaMetafactory는 직접 호출의 2~3배.

---

## 10. 운영 시나리오

### 시나리오 1 — Spring Boot 시작이 30초

**진단**:
```bash
java -Xlog:class+load:file=load.log ...        # 로드 클래스 수 (1만+ = scan 과도)
jcmd <pid> GC.class_histogram | grep Accessor   # GeneratedAccessor 폭증 확인
jcmd <pid> Compiler.codecache                   # Code Cache 사용량
async-profiler -d 30 -e cpu ...                 # 시작 구간에서 Method.invoke 핫스팟 확인
jcmd <pid> JFR.start ...                        # jdk.ClassDefine 이벤트로 동적 클래스 생성 추적
```

**흔한 원인**:
- `@ComponentScan(basePackages = "com")` 너무 넓음
- JPA EntityManagerFactory 초기화 시 수많은 @Entity reflection 스캔
- Jackson default deserializer 폭증
- JDK 8→17 마이그레이션 시 module 경고 retry

**해결**: ComponentScan 범위 축소 → `spring-context-indexer` (build 시 인덱스) → `-Dsun.reflect.inflationThreshold=0` (즉시 generate, warmup 단축) → `@Lazy` bean 적극 활용 → 궁극적으로 GraalVM Native Image (시작 50~100ms).

### 시나리오 2 — Code Cache 압박 (`CodeCache is full`, JIT 중단)

**진단**:
```bash
jcmd <pid> Compiler.codecache                          # Profiled/Non-profiled 사용량
jcmd <pid> GC.class_histogram | grep Accessor | wc -l  # 수만 개 = inflation 폭주
jcmd <pid> VM.classloader_stats                        # CLD 수 확인
```

**원인**: Hot reload + 매번 새 Method 객체 + inflation으로 GeneratedAccessor가 끝없이 생성. 또는 `Class.forName` 결과를 캐시 안 해서 같은 클래스가 다른 ClassLoader로 반복 로드.

**해결**:
- Method / Field를 `ConcurrentMap<String, MethodHandle>` 또는 `ClassValue`에 캐싱
- `-XX:ReservedCodeCacheSize=512m` 상향
- `-Dsun.reflect.noInflation=true`로 debug 후 caching 누수 위치 찾기
- 궁극적으로 JDK 18+ (JEP 416 — MethodAccessor가 MH 기반, GeneratedAccessor 클래스 폭증 없음)

### 시나리오 3 — JDK 8 → 17 마이그레이션 폭증

증상:
```
Caused by: java.lang.reflect.InaccessibleObjectException:
  Unable to make field private final byte[] java.lang.String.value
  accessible: module java.base does not "opens java.lang" to unnamed module
```
임시 해결 (전체 module 풀기):
```bash
--add-opens java.base/java.lang=ALL-UNNAMED
--add-opens java.base/java.util=ALL-UNNAMED
```
영구 해결: Lombok 1.18.30+ / Hibernate 6+ / Mockito 5+ / Spring 6+ (auto add-opens) 업그레이드. 새 라이브러리는 reflection 의존을 줄이고 ByteBuddy / MH로 이전 중.

### 시나리오 4 — ThreadLocal + Reflection 누수 → OOM:Metaspace

흔한 패턴:
```java
static ThreadLocal<Map<Class<?>, MethodHandle>> CACHE = new ThreadLocal<>();
```
**문제**: Map의 key가 `Class<?>` → 동적으로 로드된 클래스가 그 ClassLoader를 잡음 → ClassLoaderData (CLD) unload 안 됨 → Metaspace 무한 증가 → OOM:Metaspace. Web container의 hot reload 환경에서 특히 치명적.

**해결**:
- `WeakHashMap<Class<?>, MethodHandle>` — Class를 weak reference로
- 더 좋은 건 `ClassValue<MethodHandle>` — JVM이 Class 라이프사이클과 자동 연동, 동시성 안전
- ThreadLocal 자체를 끊기: webapp shutdown hook에서 `CACHE.remove()`

---

## 11. 꼬리질문

**Q1. Method.invoke가 왜 느린가?**
> 다섯 가지 비용: ① argument boxing (primitive → wrapper, `Integer.valueOf` 등), ② access check (SecurityManager / module), ③ megamorphic call site로 JIT inline 불가 (수많은 GeneratedAccessor가 같은 invoke 사이트 공유), ④ 첫 15회 JNI native transition (일반 호출의 50배), ⑤ result boxing. inflation 후에도 megamorphic 그대로라 inline 안 됨 — 그래서 inflated여도 직접 호출의 ~18배.

**Q2. MethodHandle이 Reflection보다 빠른 이유?**
> ① `static final MethodHandle`을 JIT이 invoke target을 컴파일 상수로 취급해 inline (Method 객체는 static final이어도 내부 DelegatingAccessor → GeneratedAccessor 경로 때문에 invoke 사이트 자체가 megamorphic 그대로 — final 효과 없음), ② 내부 LambdaForm IR이 JIT-friendly. 지역 변수면 JIT이 상수 못 잡아 reflection 수준으로 느려질 수 있음 — 반드시 `static final`. `invokeExact`는 signature 정확 일치 (컴파일 타임 검증)라 더 공격적 inline, `invoke`는 자동 변환으로 약간 느림.

**Q3. LambdaMetafactory가 Reflection을 어떻게 대체?**
> JDK 8 invokedynamic으로 Method → Functional Interface 구현체 변환. 첫 호출 시 metafactory가 FI 구현 클래스를 **딱 한 번** 생성하고 CallSite.target은 그 인스턴스를 반환하는 MethodHandle — 이후엔 그냥 인스턴스 반환 + 일반 invokevirtual. 직접 호출의 2~3배 (boxing만). Spring 5+ 일부 영역이 이 방식으로 Reflection 대체. 단 **Functional Interface (SAM)**만 wrap 가능 — `Method.invoke(obj, args)` 같은 가변 인자 + 동적 타입은 불가. Spring DI처럼 인자 수가 다양한 곳은 일반 Reflection 또는 `MethodHandle.invokeWithArguments`.

**Q4. JDK 17에서 `setAccessible(true)`가 왜 깨지나?**
> JDK 9 JPMS의 strong encapsulation. 모듈이 `opens` 안 한 패키지에는 deep reflection 불가, JDK 9~16 warning이 JDK 17부터 `InaccessibleObjectException` Error로 격상 (JEP 403). 우회: 런타임 `--add-opens java.base/java.lang=ALL-UNNAMED`, 자기 모듈 module-info.java에서 `opens` 선언, 또는 `Lookup.privateLookupIn`. Lombok은 javac annotation processor라 컴파일 시점에 bytecode 추가 — 일반 reflection은 안 하지만 내부 `com.sun.tools.javac.*` 접근 때문에 `--add-opens jdk.compiler/com.sun.tools.javac.*=ALL-UNNAMED` 필요.

**Q5. "Reflection이 megamorphic이라 JIT inline 못 한다"의 정확한 의미?**
> JIT inline은 호출 사이트 receiver 타입의 일관성을 전제 — monomorphic(1종)이면 직접 inline, bimorphic(2종)이면 if-else로 두 path 모두 inline, **megamorphic(3종+)이면 vtable lookup으로만 처리하고 inline 포기**. Reflection의 `Method.invoke` 사이트는 framework 전역(Spring, Jackson, Hibernate 등)에서 공유되어 수십·수백 종의 GeneratedAccessor가 같은 사이트로 들어옴 → 확정 megamorphic → C2가 inline 포기 → vtable lookup 매번 발생. MethodHandle이 static final이면 invoke target 자체가 컴파일 상수처럼 잡혀서 이 한계를 뚫음 — 같은 reflection 의미인데 MH가 빠른 본질적 이유.

---

> Method.invoke inflation 상세 흐름, JEP 번호 추적, ByteBuddy/ASM 비교는 git 7e4a6c8 참조.
