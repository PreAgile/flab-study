# 01-02. ClassLoader 계층 — 위임 모델과 그 위반자들

> "ClassLoader가 부모 위임 모델로 동작한다"는 한 줄은 답이 아니라 **시작**이다.
> Tomcat은 왜 그걸 깨고, OSGi는 왜 또 다르게 깨고, JDBC DriverManager는 왜 ThreadContextClassLoader를 도입했는가 — 이걸 답할 수 있어야 한다.

---

## 🗺️ JVM 라이프사이클 안에서 이 챕터의 위치

이 챕터는 클래스 라이프사이클 5단계 중 **Loading** — `.class` bytes를 메모리로 가져와 `InstanceKlass`로 변환하는 단계의 **주체(누가)** 를 다룬다.

![class lifecycle](./_excalidraw/04-class-lifecycle.svg)

```
   .java  ──javac──►  .class
                          │
                          ▼  ★ 이 챕터 ★ — ClassLoader가 .class를 어떻게 찾고, 누가 부모이고, 위임 모델
                      Loading
                          │
                          ▼
                      Linking (Verify, Prepare, Resolve)  → [03-linking](./03-linking.md)
                          │
                          ▼
                      Initialization (<clinit>)            → [04-initialization-and-unload](./04-initialization-and-unload.md)
                          │
                          ▼
                      Usage → Unloading
```

**이전 챕터와의 연결**:
- ← [01-classfile-format](./01-classfile-format.md): 이 챕터의 **입력**(`.class` 파일의 구조)이 무엇인지.
- → 이 챕터의 **출력**: `defineClass`가 만든 `InstanceKlass` — Metaspace에 저장됨. 풀버전은 [02-runtime-data-areas/02-metaspace](../02-runtime-data-areas/02-metaspace-and-class-space.md).

---

## 📍 학습 목표

1. JDK 9 이전(3계층)과 이후(Bootstrap/Platform/App) ClassLoader 변화를 안다.
2. 부모 위임 모델(parent delegation)의 **두 가지 보장**(중복 방지 + 보안)을 설명할 수 있다.
3. Tomcat WebappClassLoader가 위임을 어떻게 뒤집고 왜 그러는지 안다.
4. OSGi의 BundleClassLoader가 그래프 기반인 이유를 안다.
5. JDBC DriverManager가 ThreadContextClassLoader를 쓰는 SPI 패턴을 안다.
6. ClassLoader 누수(memory leak)의 원리와 진단법을 안다.
7. `defineClass`와 `findClass`의 차이, `loadClass` 호출 흐름을 코드로 그릴 수 있다.

---

## 🎨 1단계: 백지 그리기 가이드

### Step 1: 좌측 — JDK 9+ 표준 ClassLoader 계층

세로 트리:
```
        [Bootstrap CL] (C++)
              ↑
        [Platform CL]
              ↑
        [Application CL]
              ↑
        [User-defined CL ...]
```

각 CL 박스 옆에 "어디서 로드?" 메모.

### Step 2: 우측 — Tomcat WebappClassLoader 변형

```
        [Bootstrap CL]
              ↑
        [Platform CL]
              ↑
        [Application CL] ← Tomcat Common CL
              ↑
        [Catalina CL]
              ↑
        [Shared CL] (선택)
              ↑
        [WebApp #1 CL]   [WebApp #2 CL]   ...
```

WebApp CL에 화살표:
- 위로 가는 일반 위임은 점선
- 자기 자신을 먼저 검색 (역위임)은 두꺼운 빨간 화살표

### Step 3: 아래쪽 — OSGi BundleClassLoader 그래프

여러 Bundle이 서로 import/export를 가짐 → DAG.

### Step 4: 우상단 — SPI + ThreadContextCL

DriverManager가 ServiceLoader로 Driver를 검색할 때 어떻게 위임을 우회하는지.

### 정답 그림

![ClassLoader 위임과 변형](./_excalidraw/02-classloader-hierarchy.svg)

> 편집은 [02-classloader-hierarchy.excalidraw](./_excalidraw/02-classloader-hierarchy.excalidraw)을 [excalidraw.com](https://excalidraw.com/)에서 "Open"으로.

---

## 🧠 2단계: 직관

### 핵심 비유

> 도서관 비유:
> - 시립 도서관(Bootstrap) ← 학교 도서관(Platform) ← 학과 도서관(Application) ← 개인 책장(User)
> - 책(클래스)을 찾을 때 "내가 있는 가장 가까운 책장에서 찾기 전에, **항상 시립부터 묻고 내려와라**"
> - 이유: 시립이 들고 있는 표준 책을, 학교가 자기 카피본으로 덮어쓰면 일관성이 깨진다.

### 부모 위임의 두 가지 보장

> 1. **보안 (Class spoofing 방지)**:
>    공격자가 `java.lang.String`이라는 이름의 악성 클래스를 만들어 classpath에 두어도, AppCL이 먼저 Bootstrap에 위임 → Bootstrap이 진짜 String 로드 → 가짜 무시.
>
> 2. **유일성 (Type identity)**:
>    JVM은 **클래스 = (이름, 정의한 ClassLoader)** 라는 쌍으로 식별한다. 부모 위임은 같은 클래스가 여러 CL에 의해 정의되는 것을 막아 type identity를 유지.

### "왜 깨는 사람들이 있나"

- **Tomcat**: 한 JVM에 여러 웹앱 → 각 웹앱이 다른 버전의 라이브러리(Spring 4 vs 5)를 쓸 수 있어야 함 → AppCL의 한 버전이 모든 웹앱에 강제되면 안 됨 → **반전 위임** (자기 먼저, 그 다음 부모)
- **OSGi**: 모듈성 + 동적 로딩 → 트리 구조로는 표현 못 함 → **DAG 위임**
- **JDBC DriverManager**: SPI pattern. AppCL에 있는 Driver 구현을 Bootstrap에 있는 DriverManager가 사용해야 함. 일반 위임으로는 못 함 (자식의 코드를 부모가 찾을 수 없음) → **ThreadContextClassLoader**

---

## 🔬 3단계: 구조

### JDK 9+ 표준 3계층

| ClassLoader | 클래스 | 무엇을 로드 | 부모 |
|---|---|---|---|
| **Bootstrap** | (C++ HotSpot 내장) | `$JAVA_HOME/lib/modules`의 핵심 모듈 (`java.base`, `java.sql`, `java.xml` ...) | (없음) |
| **Platform** | `jdk.internal.loader.ClassLoaders$PlatformClassLoader` | 비핵심 표준 모듈, JDK 모듈 | Bootstrap |
| **Application** | `jdk.internal.loader.ClassLoaders$AppClassLoader` | `-classpath`, `-cp`, `--module-path`, `CLASSPATH` env | Platform |

JDK 8 이전:
- Bootstrap → Extension(`$JAVA_HOME/lib/ext`) → System(=Application)
- JDK 9에서 Extension 폐기 (모듈 시스템으로 대체), Platform CL이 그 역할.

### `getClassLoader()` 결과

```java
String.class.getClassLoader();   // null  (Bootstrap은 null 반환 — 약속)
javax.transaction.xa.XAResource.class.getClassLoader();
                                  // PlatformClassLoader
MyClass.class.getClassLoader();   // AppClassLoader
new URLClassLoader(...).getClass().getClassLoader();
                                  // AppClassLoader (이 CL을 정의한 CL)
```

> 함정: Bootstrap이 `null`인 이유 — Bootstrap은 Java 객체가 아니다(C++).  
> `null`을 "부모 없음"으로도 동시에 표현. JLS의 약속.

### 부모 위임 알고리즘

```java
// ClassLoader.java (JDK 21, 핵심)
protected Class<?> loadClass(String name, boolean resolve)
        throws ClassNotFoundException {
    synchronized (getClassLoadingLock(name)) {
        // 1. 이미 로드된 클래스인지 확인
        Class<?> c = findLoadedClass(name);

        if (c == null) {
            try {
                // 2. 부모에게 위임 (★ 핵심 ★)
                if (parent != null) {
                    c = parent.loadClass(name, false);
                } else {
                    // Bootstrap이 부모면 native로
                    c = findBootstrapClassOrNull(name);
                }
            } catch (ClassNotFoundException e) {
                // 부모가 못 찾았다 — 정상. 내가 찾으면 됨.
            }

            if (c == null) {
                // 3. 부모가 못 찾았으면 내가 찾는다
                long t1 = System.nanoTime();
                c = findClass(name);  // ★ subclass에서 override ★

                // record metrics
            }
        }
        if (resolve) {
            resolveClass(c);
        }
        return c;
    }
}
```

### 같은 클래스의 두 가지 정의 = 다른 타입

```java
// 같은 이름이지만 다른 ClassLoader가 로드 → 다른 Class 객체 → ClassCastException
URLClassLoader cl1 = new URLClassLoader(new URL[]{...});
URLClassLoader cl2 = new URLClassLoader(new URL[]{...});

Class<?> c1 = cl1.loadClass("com.example.Foo");
Class<?> c2 = cl2.loadClass("com.example.Foo");

c1 == c2;  // false!
c1.cast(c2.newInstance());  // ClassCastException
```

JVM의 클래스 동등성:
```
identity(Class) = (name, defining ClassLoader)
```

### `findClass` vs `defineClass` vs `loadClass`

| 메서드 | 누가 호출? | 역할 |
|---|---|---|
| `loadClass(name)` | 외부에서 호출 (보통 JVM) | 위임 알고리즘 실행 |
| `findClass(name)` | `loadClass`가 내부적으로 호출 | 실제로 .class 바이트 찾기 (subclass가 override) |
| `defineClass(name, bytes, ...)` | `findClass`가 내부에서 | byte[]를 `Class<?>` 객체로 변환 (native call) |

### 커스텀 ClassLoader 작성

```java
public class MyClassLoader extends ClassLoader {
    private final Path baseDir;

    public MyClassLoader(Path baseDir, ClassLoader parent) {
        super(parent);
        this.baseDir = baseDir;
    }

    @Override
    protected Class<?> findClass(String name) throws ClassNotFoundException {
        try {
            Path path = baseDir.resolve(name.replace('.', '/') + ".class");
            byte[] bytes = Files.readAllBytes(path);
            return defineClass(name, bytes, 0, bytes.length);
        } catch (IOException e) {
            throw new ClassNotFoundException(name, e);
        }
    }
}
```

> 일반적 패턴: `findClass`만 override, `loadClass`는 그대로 두면 표준 위임 모델 유지.

---

### 깨는 자들 ① — Tomcat WebappClassLoader

#### 구조

```
[Bootstrap]
    ↑
[Platform]
    ↑
[Application]  = Tomcat Common CL (Tomcat 내부 클래스 + 일부 라이브러리)
    ↑
[Catalina CL]
    ↑
[Shared CL]  (선택, 모든 웹앱이 공유할 라이브러리)
    ↑
[WebApp #1 CL]   [WebApp #2 CL]   [WebApp #3 CL]
```

#### 위임 반전

WebappCL의 `loadClass`:

```java
// Tomcat WebappClassLoaderBase.java (요약)
public Class<?> loadClass(String name, boolean resolve) {
    // 1. 이미 로드됐는지 확인
    Class<?> clazz = findLoadedClass0(name);
    if (clazz != null) return clazz;

    // 2. JVM core 클래스는 부모에게 (java.*, javax.*)
    if (filter(name)) {
        return parent.loadClass(name, resolve);  // 정상 위임
    }

    // 3. ★ 자기가 먼저 찾는다 ★
    clazz = findClass(name);
    if (clazz != null) return clazz;

    // 4. 자기가 없으면 부모에게
    return parent.loadClass(name, resolve);
}
```

핵심: **java.*/javax.* 외의 클래스는 자기가 먼저 찾는다.**

#### 왜 반전했나

| 상황 | 일반 위임이면 |
|---|---|
| WebApp #1이 Spring 4.3을 사용, WebApp #2가 Spring 5.3을 사용 | AppCL에 어느 버전을 둘지 결정 못 함 |
| WebApp의 servlet-api.jar가 잘못 들어있음 | 충돌. Tomcat이 제공하는 표준과 다른 버전 |
| WebApp이 자체 log4j를 묶음 | 다른 웹앱과 격리되어야 함 |

→ **각 웹앱이 자기만의 라이브러리 버전을 가질 수 있어야 함**.
→ 자기 WEB-INF/lib을 먼저 찾고, 없으면 부모에게.

#### 위임 부분이 막힌 패키지

Tomcat WebappCL의 `filter` 메서드는 다음 패키지는 **무조건 부모에게**:
- `java.*` (Bootstrap에서만)
- `javax.*` (Platform/Bootstrap)
- 일부 Tomcat 내부 패키지

이유: 보안 + JVM 일관성 (Tomcat이 제공한 `javax.servlet.*`을 강제).

---

### 깨는 자들 ② — OSGi

#### 구조: 그래프

OSGi(Open Service Gateway initiative)는 모듈 시스템.
각 **Bundle**(=모듈)이 자체 ClassLoader를 가짐.

```
Bundle A   Bundle B   Bundle C   Bundle D
  │          │          │          │
  │ exports  │ imports  │ exports  │ imports
  └──────────┴──────────┴──────────┘
             (선언적 의존성)
```

Bundle CL의 `loadClass`:
1. import한 패키지의 클래스 → **import 대상 Bundle의 CL**에 위임
2. 자기 Bundle 안의 클래스 → 자기가 로드
3. 시스템 클래스(java.*) → System CL(Bootstrap)

위임 트리가 아니라 **DAG**. 같은 패키지를 두 Bundle이 export하면 그 중 한쪽에 import 결정.

#### 장점/단점

- 장점: 진정한 모듈 격리, 같은 라이브러리의 여러 버전 공존, 동적 install/uninstall
- 단점: 복잡, 디버깅 어려움 (어느 Bundle에서 로드됐는지 추적 필요)

JDK 9 Module System은 OSGi의 영감을 받았지만 더 단순 (그래프가 아닌 트리, 정적 의존성).

---

### 깨는 자들 ③ — Thread Context ClassLoader (TCCL)

#### 문제: SPI 역참조

```
[Bootstrap CL]
    │
    ├─ java.sql.DriverManager  ← Bootstrap이 로드
    │
[App CL]
    │
    ├─ com.mysql.cj.jdbc.Driver  ← App CL이 로드
```

DriverManager가 ServiceLoader로 모든 Driver 구현체를 찾으려고 한다.
일반 위임으로는: Bootstrap이 자기 또는 자기 자손에게 묻기만 함 → MySQL Driver를 못 찾음.

#### 해결: Thread.currentThread().getContextClassLoader()

```java
// DriverManager.java (요약)
private static void loadInitialDrivers() {
    ServiceLoader<Driver> loadedDrivers = ServiceLoader.load(Driver.class);
    // ServiceLoader는 기본으로 Thread Context ClassLoader 사용
    Iterator<Driver> driversIterator = loadedDrivers.iterator();
    while (driversIterator.hasNext()) {
        driversIterator.next();
    }
}
```

`ServiceLoader.load(Driver.class)`는 내부적으로:
```java
return load(service, Thread.currentThread().getContextClassLoader());
```

Thread Context ClassLoader는 기본적으로 **App ClassLoader** (main 스레드 기준).
→ DriverManager(Bootstrap)이 AppCL을 통해 MySQL Driver 발견 가능.

#### 다른 SPI 사례

- JAXP (XML 파서)
- JNDI provider
- Java EE 컨테이너의 ResourceFactory
- Logging frameworks의 backend 검색
- Spring `META-INF/spring.factories` (Spring 자체 SPI)

#### 함정: TCCL 누수

```java
ExecutorService es = Executors.newFixedThreadPool(10);
es.submit(() -> { ... });

// 풀의 스레드는 main의 TCCL을 상속받음.
// 만약 main이 WebApp CL을 TCCL로 설정 후 task를 제출했다면,
// 풀 스레드가 그 TCCL 참조를 영구히 들고 있음
// → WebApp 종료 후에도 WebApp CL이 GC 안 됨
// → ClassLoader 누수
```

→ Tomcat 같은 환경에서 빈번한 누수 원인.

---

### 다른 ClassLoader 사례

#### URLClassLoader

```java
URL[] urls = { new URL("file:/path/to/lib.jar"), new URL("http://...") };
URLClassLoader cl = new URLClassLoader(urls, parent);
Class<?> c = cl.loadClass("com.example.Foo");
```

표준 위임 + URL에서 .class 파일/JAR을 검색. AppCL의 부모 클래스가 이거.

#### MethodHandles.Lookup.defineClass() / defineHiddenClass()

```java
MethodHandles.Lookup lookup = MethodHandles.lookup();
Class<?> c = lookup.defineHiddenClass(bytes, true).lookupClass();
```

JDK 15+. **Hidden Class**:
- ClassLoader에 등록 안 됨
- 일반 reflection으로 검색 불가
- 더 이상 참조 없으면 unload
- Lambda, ASM, ByteBuddy 5+에서 사용

#### 동적 클래스 생성 라이브러리

| 라이브러리 | 방식 |
|---|---|
| **CGLib** | `Enhancer`로 subclass 생성, native `defineClass` 호출 |
| **ByteBuddy** | `DynamicType.Builder` → `make()` → `Class.load()` |
| **ASM** | `ClassWriter` → byte[] → 직접 `defineClass` |
| **Javassist** | 소스 텍스트로 메서드 정의 + 컴파일 |
| **Spring AOP** | JDK Dynamic Proxy (인터페이스만) 또는 CGLib (클래스도) |

---

## 🗺️ 잠깐 — 우리는 라이프사이클 어디인가? (Reminder)

> 4단계로 내려가기 전에 다시 한 번. 지금까지 본 위임 모델·findClass·defineClass는 모두 **Loading** 단계의 일이다.
>
> ```
> .class ──[★ Loading: ClassLoader가 찾아 메모리로 ★]──► Linking ──► Init ──► Use ──► Unload
> ```
>
> 다음 4단계는 HotSpot 내부에서 이 Loading이 어떻게 구현되어 있는지(C++ 코드 레벨)다. Linking·Init은 [03-linking](./03-linking.md), [04-initialization-and-unload](./04-initialization-and-unload.md)에서.

---

## 🧬 4단계: 내부 구현 — HotSpot

### Bootstrap ClassLoader는 C++

위치: `src/hotspot/share/classfile/classLoader.cpp`

```cpp
// classLoader.cpp
ClassPathEntry* ClassLoader::_jrt_entry = NULL;  // JDK 9+ jrt:/ (jimage)

InstanceKlass* ClassLoader::load_class(Symbol* name, ...) {
  // 1. jrt: 검색 (JDK 9+ modules)
  if (_jrt_entry != NULL) {
    stream = _jrt_entry->open_stream(THREAD, file_name);
    if (stream != NULL) {
      return KlassFactory::create_from_stream(stream, name, loader_data, ...);
    }
  }
  // 2. -Xbootclasspath/a 추가 경로
  // 3. 못 찾으면 NULL
  return NULL;
}
```

#### jrt: 가상 파일시스템

JDK 9+: 모듈들이 `$JAVA_HOME/lib/modules`에 **jimage** 포맷으로 묶여 있음. `jrt:/` URL 스킴으로 접근.

```java
URI uri = URI.create("jrt:/java.base/java/lang/String.class");
try (InputStream in = uri.toURL().openStream()) {
    // ...
}
```

### Platform / Application ClassLoader는 Java

위치: `src/java.base/share/classes/jdk/internal/loader/BuiltinClassLoader.java`

```java
// BuiltinClassLoader.java
public final Class<?> loadClass(String cn, boolean resolve) throws ClassNotFoundException {
    Class<?> c = loadClassOrNull(cn, resolve);
    if (c == null) {
        throw new ClassNotFoundException(cn);
    }
    return c;
}

protected Class<?> loadClassOrNull(String cn, boolean resolve) {
    synchronized (getClassLoadingLock(cn)) {
        // 1. 이미 로드됐나
        Class<?> c = findLoadedClass(cn);

        if (c == null) {
            // 2. 모듈 이름이 결정되어 있나 (JPMS)
            LoadedModule loadedModule = findLoadedModule(cn);

            if (loadedModule != null) {
                // 모듈이 정해진 패키지 — 그 모듈을 정의한 CL이 로드
                BuiltinClassLoader loader = loadedModule.loader();
                if (loader == this) {
                    c = findClassInModuleOrNull(loadedModule, cn);
                } else {
                    c = loader.loadClassOrNull(cn);
                }
            } else {
                // 모듈 경계 밖 — 표준 위임
                if (parent != null) {
                    c = parent.loadClassOrNull(cn);
                }
                if (c == null) {
                    // classpath 검색
                    c = findClassOnClassPathOrNull(cn);
                }
            }
        }
        return c;
    }
}
```

> JDK 9+ 위임은 **모듈 우선**. 같은 클래스 이름이라도 모듈에 따라 다르게 해석.

### `defineClass`의 native

위치: `src/java.base/share/native/libjava/ClassLoader.c`

```c
// ClassLoader.c
JNIEXPORT jclass JNICALL
Java_java_lang_ClassLoader_defineClass1(JNIEnv *env, jclass cls,
                                         jobject loader, jstring name,
                                         jbyteArray data, jint offset, jint length,
                                         jobject pd, jstring source) {
    // 1. byte[] → native buffer
    jbyte *body = (*env)->GetPrimitiveArrayCritical(env, data, NULL);

    // 2. JVM_DefineClassWithSource 호출 (HotSpot 진입)
    jclass result = JVM_DefineClassWithSource(env, utfName, loader,
                                                 body + offset, length, pd, utfSource);

    // 3. cleanup
    (*env)->ReleasePrimitiveArrayCritical(env, data, body, 0);
    return result;
}
```

위치: `src/hotspot/share/prims/jvm.cpp`의 `JVM_DefineClassWithSource`:

```cpp
JVM_ENTRY(jclass, JVM_DefineClassWithSource(JNIEnv *env, const char *name,
                                              jobject loader, const jbyte *buf,
                                              jsize len, jobject pd, const char *source)) {
  return jvm_define_class_common(name, loader, buf, len, pd, source, THREAD);
}

static jclass jvm_define_class_common(...) {
  // 1. ClassLoaderData 찾기 또는 생성
  ClassLoaderData* loader_data = register_loader(class_loader);

  // 2. ClassFileParser로 .class 파싱
  ClassFileStream st((u1*)buf, len, source, ClassFileStream::verify);
  Handle protection_domain(THREAD, JNIHandles::resolve(pd));

  Klass* k = SystemDictionary::resolve_from_stream(
      &st, class_name, class_loader, loader_data,
      protection_domain, ...);

  // 3. 결과를 java.lang.Class oop으로 변환
  return (jclass)JNIHandles::make_local(THREAD, k->java_mirror());
}
```

### ClassLoaderData (CLD)

각 ClassLoader에는 **ClassLoaderData**라는 C++ 객체가 매핑되어 있다.

```cpp
// classLoaderData.hpp
class ClassLoaderData : public CHeapObj<mtClass> {
  oop _class_loader;                  // Java ClassLoader 객체 (weak ref)
  Klass* _klasses;                    // 이 CL이 로드한 클래스들 (linked list)
  Metaspace* _metaspace;              // ★ 이 CL 전용 Metaspace ★
  Dependencies _dependencies;         // 다른 CL과의 의존성
  // ...
};
```

> **Metaspace는 ClassLoaderData 단위로 chunk가 할당됨**.
> ClassLoader가 GC되면 그 CLD의 Metaspace chunk 통째로 해제.
> → CL 누수 = Metaspace 누수.

---

## 📜 5단계: 역사

### Java 1.0 — 단일 ClassLoader

처음엔 ClassLoader 하나. 모든 클래스를 그 CL이 로드.

### Java 1.2 (1998) — 3계층 도입

- **Bootstrap → ExtClassLoader → AppClassLoader** 3계층
- 부모 위임 모델 도입
- `URLClassLoader` 표준화

### Java 5 (2004) — `Class.getClassLoader()` 일반화

ClassLoader API가 안정화. ServiceLoader (JDK 6에서 정식)의 기반.

### Java 6 (2006) — ServiceLoader

`ServiceLoader<T>` 도입. `META-INF/services/`의 SPI 표준화. TCCL을 기본 사용.

### Java 7 (2011) — Parallel ClassLoader

JEP 168:
- 그 전: `loadClass`가 `synchronized` — 한 번에 한 클래스만 로드.
- 7부터: `parallelLockMap`으로 클래스별 lock → 동시 다른 클래스 로드 가능.
- 활성화: `ClassLoader.registerAsParallelCapable()` 호출.

### Java 8 (2014) — Lambda + 마지막 PermGen

- Lambda가 invokedynamic + hidden class 사용 (anonymous class CL 활용)
- PermGen → Metaspace 전환. 클래스 메타데이터가 ClassLoaderData 단위로 관리.

### Java 9 (2017) — Module System + Layer

JEP 261:
- **3계층 변화**: Bootstrap → Platform → Application
- **ExtClassLoader 폐기**
- **ModuleLayer**: 모듈 그래프 단위의 ClassLoader 묶음
- `sun.misc.Launcher$AppClassLoader` → `jdk.internal.loader.ClassLoaders$AppClassLoader`로 클래스 이름 변경

### Java 11 (2018) — NestHost/NestMembers

- 같은 nest의 private 접근 허용 → synthetic accessor 사라짐
- ClassLoader는 그대로지만 access check 로직 변경

### Java 15 (2020) — Hidden Class

JEP 371:
- `MethodHandles.Lookup.defineHiddenClass()`
- ClassLoader에 등록 안 됨, GC 가능
- Lambda 구현이 anonymous class 대신 hidden class로 전환

### Java 16+ — Strong Encapsulation

JEP 396, 403:
- Reflection으로 `jdk.internal.*` 접근 차단
- `--add-opens` 옵션 필요

---

## ⚔️ 6단계: 꼬리질문 트리

### Q1. 부모 위임 모델을 설명하세요.

**예상 답변**:
> 모든 ClassLoader는 부모 CL을 가진다. `loadClass` 호출 시:
> 1. 이미 로드된 클래스인지 확인.
> 2. 부모에게 먼저 위임 (재귀적).
> 3. 부모가 못 찾으면 자기가 찾는다 (`findClass`).
> 4. 최상위는 Bootstrap (`parent == null`).
>
> 보장:
> - **Class spoofing 방지**: 표준 클래스를 위조 못 함.
> - **Type identity**: 같은 클래스가 여러 CL에서 정의되지 않음.

#### 🪝 꼬리 Q1-1: "Bootstrap ClassLoader는 왜 Java로 안 만들고 C++인가요?"

**예상 답변**:
> Chicken-and-egg 문제.
> Bootstrap이 로드하는 클래스 = `java.lang.Object`, `java.lang.ClassLoader`, ...
> 즉 Bootstrap은 ClassLoader 클래스 자신을 로드해야 한다.
> → ClassLoader 클래스가 아직 메모리에 없는 상태에서 Java로 작성된 ClassLoader는 작동 불가.
> → Bootstrap은 JVM의 native 코드 (HotSpot C++)로 작성.
>
> `getClassLoader()` 결과가 `null`인 이유도 이것 — Java 객체가 아니라서.

#### 🪝 꼬리 Q1-2: "부모 위임이 깨지면 무슨 일이 생기나요?"

**예상 답변**:
> 1. **같은 클래스 두 번 로드** → 다른 Class 객체 → ClassCastException.
> 2. **표준 라이브러리 충돌** 가능 (악성 java.lang.String 같은 시도).
> 3. **Type identity 깨짐** → reflection, instanceof가 예상 외 결과.
>
> 단, 의도적으로 깨는 경우(Tomcat, OSGi)는 격리 목적. 잘 제어하면 OK.

##### 🪝 꼬리 Q1-2-1: "Tomcat에서 한 웹앱이 다른 웹앱의 클래스를 참조하면 어떻게 되나요?"

**예상 답변**:
> 직접 참조 못 함. 각 WebappCL이 격리되어 있어서 다른 WebappCL이 로드한 클래스는 보이지 않음.
> 공유하려면:
> 1. **Shared CL**에 라이브러리를 넣어 모든 웹앱이 공유.
> 2. **AppCL/Common CL**에 두면 모든 웹앱 + Tomcat 자체가 공유.
> 3. 또는 JNDI, MBean 등 cross-classloader 통신.

### Q2. Tomcat WebappClassLoader는 왜 위임을 깨나요?

**예상 답변**:
> 한 JVM에서 여러 웹앱을 실행할 때, 각 웹앱이 다른 버전의 라이브러리를 쓸 수 있어야 함.
> 일반 위임이면 AppCL(또는 Catalina CL)에 한 버전만 둘 수 있어 격리 불가.
> WebappCL은 **자기 WEB-INF/lib + WEB-INF/classes를 먼저** 검색, 없으면 부모로.
> 단, `java.*`, `javax.*`, Servlet API 같은 핵심은 무조건 부모로 보내서 일관성 유지.

#### 🪝 꼬리 Q2-1: "WebApp 두 개가 같은 패키지 다른 버전을 쓰면 메모리에 두 번 로드되겠네요?"

**예상 답변**:
> Yes. 같은 `org.apache.commons.lang3.StringUtils` 이름의 클래스가 두 WebappCL에서 각각 정의되어, JVM 안에 두 Class 객체 존재.
> Metaspace에 두 번 적재됨 → 메모리 사용량 증가.
> 단, 격리 보장됨 — WebApp 1의 StringUtils가 WebApp 2에 영향 안 줌.

##### 🪝 꼬리 Q2-1-1: "그럼 두 WebApp 간에 객체를 주고받으면?"

**예상 답변**:
> 직접 못 함. WebApp 1이 만든 StringUtils 인스턴스를 WebApp 2가 받으면 `ClassCastException` (그 인스턴스의 Class가 WebApp 2의 StringUtils와 다름).
> 회피책:
> 1. **공통 인터페이스를 Shared CL에 두기**: 양쪽이 같은 인터페이스 Class 공유.
> 2. **직렬화 사용**: byte[]로 변환 후 재구성.
> 3. **JNDI/RMI**: cross-CL 통신 메커니즘.

### Q3. ClassLoader 메모리 누수는 왜 발생하나요?

**예상 답변**:
> ClassLoader는 자기가 로드한 모든 클래스를 참조하고, 그 클래스들도 자기 ClassLoader를 역참조.
> 누구든 그 CL을 GC root에서 도달 가능한 곳에 들고 있으면, **전체 CL + 그 클래스들 + 그 인스턴스들이 모두 살아남음**.
>
> 흔한 원인:
> 1. **ThreadLocal**: Thread Pool의 스레드가 옛 CL이 로드한 클래스의 인스턴스를 ThreadLocal에 보관.
> 2. **JDBC Driver**: DriverManager(Bootstrap)에 등록된 Driver(AppCL/WebappCL)의 참조.
> 3. **Static 필드**: 부모 CL의 static collection에 자식 CL의 객체 보관.
> 4. **JMX**: MBeanServer에 등록된 객체.
> 5. **Logging**: Log4j MDC, SLF4J marker 등.
> 6. **Reflection cache**: `Class.getMethods()` 결과를 부모 CL이 캐시.

#### 🪝 꼬리 Q3-1: "Tomcat에서 hot redeploy 시 OutOfMemoryError: Metaspace가 나는데 어떻게 진단하나요?"

**예상 답변**:
> 1. **Tomcat의 ClassLoader leak detection**: `context.xml`에 `clearReferencesXxx` 설정. 자동 cleanup 시도.
> 2. **heap dump**: `jcmd <pid> GC.heap_dump file.hprof`.
> 3. **MAT (Eclipse Memory Analyzer)**:
>    - Histogram → ClassLoader 검색
>    - 옛 WebappCL이 살아있는지 확인
>    - 살아있다면 "Path to GC Roots" → 누가 들고 있는지
> 4. **흔한 범인**:
>    - `java.lang.Thread` (ThreadLocal 또는 ContextCL 참조)
>    - `java.beans.Introspector`의 BeanInfo 캐시
>    - JDBC Driver의 static 등록
>    - log4j-1.x의 자체 caching
> 5. **수정**: 누수 시점에 `ServletContextListener.contextDestroyed`에서 명시적 cleanup.

##### 🪝 꼬리 Q3-1-1: "JDBC Driver 누수는 어떻게 정확히 일어나나요?"

**예상 답변**:
> 1. WebApp이 `Class.forName("com.mysql.cj.jdbc.Driver")` 호출.
> 2. MySQL Driver의 static 초기화에서 `DriverManager.registerDriver(this)` 호출.
> 3. `DriverManager`는 Bootstrap이 로드 → AppCL/Bootstrap에 있는 Drivers 리스트에 WebappCL의 Driver 인스턴스 등록.
> 4. WebApp 종료 시 WebappCL을 unload하려 하지만 DriverManager의 Drivers 리스트가 WebappCL 참조를 들고 있음.
> 5. → CL 누수.
>
> 수정: `ServletContextListener.contextDestroyed`에서:
> ```java
> Enumeration<Driver> drivers = DriverManager.getDrivers();
> while (drivers.hasMoreElements()) {
>     Driver driver = drivers.nextElement();
>     if (driver.getClass().getClassLoader() == getClass().getClassLoader()) {
>         DriverManager.deregisterDriver(driver);
>     }
> }
> ```

###### 🪝 꼬리 Q3-1-1-1: "JDBC 4.0부터 `Class.forName` 안 해도 되는데, 누수 패턴은 동일한가요?"

**예상 답변**:
> JDBC 4.0+: `META-INF/services/java.sql.Driver`로 SPI 자동 등록 (TCCL 사용).
> 호출 코드는 `Class.forName` 없이도 첫 `DriverManager.getConnection()` 시 자동 로드.
>
> 하지만 누수는 동일:
> - ServiceLoader가 TCCL(=WebappCL)을 통해 Driver 클래스 로드.
> - 로드된 Driver의 static init이 DriverManager.registerDriver 호출.
> - 결과적으로 DriverManager가 WebappCL의 Driver 참조 보관.
>
> 수정 방식도 동일. JDK 21에서도 이 문제는 그대로 — DriverManager 설계의 근본적 한계.

### Q4. ThreadContextClassLoader는 언제 어떻게 쓰나요?

**예상 답변**:
> SPI 패턴에서 Bootstrap이 자식 CL의 코드를 사용해야 할 때.
> `Thread.currentThread().getContextClassLoader()` 결과 = 보통 AppClassLoader.
> 사용처:
> - JDBC DriverManager → Driver 검색
> - JAXP → XML 파서 구현 검색
> - JNDI → Provider 검색
> - Logging frameworks (SLF4J) → 백엔드 검색

#### 🪝 꼬리 Q4-1: "Thread Pool에서 TCCL을 어떻게 설정하나요?"

**예상 답변**:
> 풀의 스레드는 만들 때의 부모 스레드 TCCL을 상속받음.
> 변경하려면:
> ```java
> ClassLoader saved = Thread.currentThread().getContextClassLoader();
> try {
>     Thread.currentThread().setContextClassLoader(targetCL);
>     // task 실행
> } finally {
>     Thread.currentThread().setContextClassLoader(saved);  // ★ 반드시 복원 ★
> }
> ```
> 복원 안 하면 CL 누수 발생.
> Spring `@Async`, ExecutorService.submit() 등에서 흔한 패턴.

##### 🪝 꼬리 Q4-1-1: "Virtual Thread는 TCCL을 어떻게 처리하나요?"

**예상 답변**:
> JDK 21+: Virtual Thread는 부모 스레드의 TCCL을 그대로 사용. `Thread.setContextClassLoader()` 명시 변경도 가능.
> 다만 **carrier thread와의 분리**:
> - VThread A가 setContextClassLoader 호출 → A의 TCCL만 변경.
> - 같은 carrier thread에서 실행되는 다른 VThread B의 TCCL은 영향 없음.
> - 이건 ThreadLocal 처리와 동일한 원리 (JEP 444의 ScopedValue 영향).

### Q5. (Killer) `URLClassLoader.close()`를 호출하면 무슨 일이 일어나나요?

**예상 답변**:
> 1. 열려있는 JAR/URL stream을 닫음 — 파일 핸들 해제.
> 2. 그 CL이 더 이상 새 클래스를 로드 못 함 — 이후 `loadClass`는 `ClassNotFoundException`.
> 3. **하지만 이미 로드한 클래스는 메모리에 남음** — 누군가 그 CL이나 클래스 참조 있으면 GC 안 됨.
>
> 즉, `close()`는 **리소스 정리**일 뿐, **메모리 회수**가 아님.
> 메모리까지 회수하려면 그 CL 참조가 모두 사라져야 함 + GC 발생.

#### 🪝 꼬리 Q5-1: "ClassLoader는 언제 GC되나요?"

**예상 답변**:
> 다음 조건 모두 만족 시:
> 1. ClassLoader 객체에 대한 reachable reference 없음.
> 2. 그 CL이 로드한 모든 클래스의 인스턴스가 unreachable.
> 3. 그 CL이 로드한 모든 클래스의 Class 객체가 unreachable.
> 4. 다른 CL이 이 CL이 로드한 클래스를 참조하지 않음 (resolution dependency).
>
> 한 가지라도 깨지면 누수. 보통 ThreadLocal, static field, JMX 등이 문제.

##### 🪝 꼬리 Q5-1-1: "ClassLoader가 GC될 때 Metaspace는 어떻게 정리되나요?"

**예상 답변**:
> 1. ClassLoader oop이 GC된 것을 GC가 감지.
> 2. 그 CL의 `ClassLoaderData` 객체를 dead로 표시.
> 3. **다음 Metaspace GC 사이클**에서 그 CLD의 모든 Metaspace chunk를 free list로 반환.
> 4. Compressed Class Space의 entry도 함께 정리.
> 5. CLD가 들고 있던 InstanceKlass들도 모두 해제.
>
> 즉, 즉시 해제가 아니라 두 단계 (Java Heap GC → Metaspace cleanup).
> `-XX:+ClassUnloadingWithConcurrentMark`로 동시 마킹과 같이 처리 가능 (G1 기본 on).

###### 🪝 꼬리 Q5-1-1-1: "ZGC에서 ClassUnloading은 어떻게 다르나요?"

**예상 답변**:
> ZGC는 모든 phase가 concurrent — 별도 ClassUnloading STW 없음.
> 마킹 중에 reachable한 CLD를 표시 → 마킹 끝나면 unmarked CLD 발견 → 그것들을 free list로.
> 모두 백그라운드. `-XX:+ClassUnloading` (기본 on)으로 활성화.
> Shenandoah도 유사.

### Q6. JDK 9의 Module System은 ClassLoader 모델을 어떻게 바꿨나요?

**예상 답변**:
> 1. **Bootstrap의 역할 축소**: 옛 rt.jar(60MB)를 잘게 쪼개 모듈로 분리. Bootstrap이 로드하는 모듈은 `java.base` + 핵심.
> 2. **Platform CL 등장**: 표준이지만 핵심 외 모듈 담당 (`java.sql`, `java.xml`, ...).
> 3. **ExtClassLoader 폐기**.
> 4. **ModuleLayer 도입**: `Configuration.resolveAndBind` → `Module Graph` → `ModuleLayer` → CL 매핑.
> 5. **위임에 모듈 우선 검색**: 같은 클래스 이름이라도 모듈에 따라 다른 CL이 로드.
> 6. **`requires`/`exports`로 명시적 의존성**: 패키지 단위가 아니라 모듈 단위 캡슐화.

#### 🪝 꼬리 Q6-1: "왜 Module System이 ClassLoader를 완전히 대체하지 않았나요?"

**예상 답변**:
> 1. **하위 호환성**: 기존 라이브러리들이 모두 ClassLoader 기반. Module System은 그 위에 추가됨.
> 2. **다른 추상화 레벨**:
>    - ClassLoader = "어떻게 로드할지" (mechanism)
>    - Module = "무엇을 누구에게 공개할지" (policy)
> 3. **동적 로딩 호환**: Module은 정적, ClassLoader는 동적. 두 모델 공존 필요.
> 4. **OSGi 등 기존 모듈 시스템 호환성**: JPMS가 OSGi를 대체하려는 게 아님.

---

## 🔗 다음 단계

- → [03. Linking](./03-linking.md): 로드된 클래스를 검증·준비·해결하는 3단계
- → [04. Initialization](./04-initialization-and-unload.md): static 블록 실행 + CL unload

## 📚 참고

- **JLS §12 (Execution)**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html
- **JVMS §5 (Loading, Linking, Initializing)**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html
- **JEP 261 (Module System)**: https://openjdk.org/jeps/261
- **JEP 168 (Parallel ClassLoader)**: https://openjdk.org/jeps/168
- **JEP 371 (Hidden Classes)**: https://openjdk.org/jeps/371
- **Tomcat Classloader HOWTO**: https://tomcat.apache.org/tomcat-10.1-doc/class-loader-howto.html
- **OSGi Specification**: https://docs.osgi.org/specification/
- **Sangwook Han, ClassLoader 깊이 분석** (한국어 자료 검색 권장)
