# 01-02. ClassLoader 계층 — 누가 어디서 .class를 가져오는가

> "ClassLoader가 부모 위임 모델로 동작한다"는 한 줄은 답이 아니라 시작이다.
> Spring Boot 앱(`java -jar app.jar`) 한 번 띄울 때 어떤 CL이 몇 개 만들어지고, fat jar의 `BOOT-INF/classes`·`BOOT-INF/lib`와 어떻게 대응되고, 로딩이 망가지면 어떤 에러(ClassNotFoundException / NoClassDefFoundError / LinkageError)가 어디서 튀어나오는지까지 그릴 수 있어야 시니어다.
> JDBC DriverManager가 ThreadContextClassLoader로 위임을 우회하는 SPI 패턴도 같은 맥락에서 풀린다.

---

## 이 문서의 사용법

이 문서는 **면접용 마인드맵**을 따라 선형으로 펼친 구조다. 학습 순서 = 면접 답변 순서 = 백지에 그리는 순서.

1. **0장 마인드맵을 먼저 외운다** — 루트 한 문장 + 6가지 가지 + 각 가지의 키워드 3개.
2. **1~6장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 정확히 대응.
3. **7장 면접 워크플로우로 검증**.
4. **8장 꼬리질문으로 깊이 점검**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"ClassLoader는 `.class` 바이트를 찾아 `Class<?>` 객체로 변환하는 자다. 부모 위임 모델 위에서 3계층(Bootstrap → Platform → Application)이 표준이고, Spring Boot 같은 프레임워크는 그 위에 자기 CL을 한 겹 더 얹어 자기 문제를 푼다."**

이 한 문장에서 모든 답변이 출발한다. 어떤 질문이 와도 이 문장부터 말하고 적절한 가지로 분기.

### 6개 가지 — 순서를 외운다

```
                  [ROOT: ClassLoader = .class 찾는 자]
                                │
       ┌──────────┬─────────────┼─────────────┬──────────┬──────────┐
       │          │             │             │          │          │
      ① WHY     ② WHAT        ③ HOW         ④ Spring   ⑤ SPI/TCCL ⑥ 운영진단
   부모위임의   3계층 표준    위임알고리즘   Boot 부팅   ServiceLoader 에러+누수
   두가지보장  (JDK 9+)      defineClass    실제계층    DriverMgr   Metaspace
       │          │             │             │          │          │
       │     ┌────┼────┐    ┌───┼───┐     ┌───┼───┐  ┌──┼──┐    ┌──┼──┐
   spoofing  Bootstrap   loadClass    Launched     SPI=구현이  CNFE/NCDFE
   방지      Platform    findClass    URLCL        남이끼움    LinkageError
   typeId   Application  defineClass  DevTools     TCCL=       NoSuchMethod
   유일성    (CLD 단위)   parallel     Restart/Base 사이드채널 CL누수/Metaspace
                         Metaspace                            JPMS opens
```

### 가지별 핵심 키워드 (각 가지 3개씩만)

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① WHY 부모위임** | Class spoofing 방지 | type identity 유일성 | 책임 경계(Loading만) |
| **② WHAT 3계층** | Bootstrap (C++, null) | Platform (java.sql) | Application (-cp) |
| **③ HOW 위임** | loadClass | findClass | defineClass / CLD |
| **④ Spring Boot 부팅** | JarLauncher | LaunchedURLClassLoader | DevTools Restart/Base |
| **⑤ SPI/TCCL** | SPI = 남이 끼움 | Thread Context CL | DriverManager / ServiceLoader |
| **⑥ 운영진단** | CNFE/NCDFE/Linkage | CCE = 다른 CL | CL 누수 / Metaspace OOM |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 질문에 맞는 가지 1개 선택 → 그 가지의 키워드 3개 순서대로 설명 → 듣는 사람의 관심에 따라 인접 가지로 확장

---

## 1. 가지 ①: WHY — 부모 위임의 두 가지 보장

### 1.1 핵심 질문

> "왜 ClassLoader는 부모 위임 모델을 쓰는가? ClassLoader의 책임 경계는 어디까지인가?"

### 1.2 키워드 1 — Class spoofing 방지

도서관 비유:
> 시립 도서관(Bootstrap) ← 학교 도서관(Platform) ← 학과 도서관(Application) ← 개인 책장(User).
> 책(클래스)을 찾을 때 "내가 있는 가장 가까운 책장에서 찾기 전에, 항상 시립부터 묻고 내려와라". 이유: 시립이 들고 있는 표준 책을 학교 카피본으로 덮어쓰면 일관성이 깨진다.

공격자가 `java.lang.String`이라는 이름의 악성 클래스를 만들어 classpath에 두어도, App CL이 먼저 Bootstrap에 위임 → Bootstrap이 진짜 String 로드 → 가짜 무시.

### 1.3 키워드 2 — Type identity 유일성

JVM의 클래스 동등성:
```
identity(Class) = (name, defining ClassLoader)
```

즉, **같은 이름이지만 다른 ClassLoader가 정의한 클래스는 다른 타입**이다.

```java
URLClassLoader cl1 = new URLClassLoader(new URL[]{...});
URLClassLoader cl2 = new URLClassLoader(new URL[]{...});

Class<?> c1 = cl1.loadClass("com.example.Foo");
Class<?> c2 = cl2.loadClass("com.example.Foo");

c1 == c2;                       // false!
c1.cast(c2.newInstance());     // ClassCastException
```

부모 위임은 같은 클래스가 여러 CL에서 정의되는 것을 막아 type identity를 유지한다. → 가지 ⑥에서 다룰 `ClassCastException: X cannot be cast to X`의 본질.

### 1.4 키워드 3 — 책임 경계 (Loading까지만)

| ClassLoader가 하는 일 | ClassLoader가 안 하는 일 |
|---|---|
| `.class` 바이트 찾기 (디스크/네트워크/jar) | Verification → JVM 본체 → 03장 |
| `defineClass()` 호출 → `Class` 객체 생성 | Preparation (static default) → JVM → 03장 |
| 부모 위임 (parent delegation) | Resolution → JVM → 03장 |
| parallel CL의 per-class name 락 | `<clinit>` 실행, JLS 12-step init lock → JVM → 04장 |

**자주 헷갈리는 두 가지**:

1. **`ClassLoader.loadClass()`가 끝났다 ≠ 클래스가 초기화됐다**.
   `loadClass()`는 Loading만 보장. `Class` 객체로 메모리에 올라와 있어도 누가 Active Use(`new`, `getstatic` 등)를 트리거하기 전엔 `<clinit>` 안 돈다. → `Class.forName(name, false, loader)`가 동작하는 이유.

2. **ClassLoader가 쓰는 락 ≠ Initialization 락**.
   - ClassLoader 자기 락(parallel CL): `loadClass(name)` 동시성 보호 — **이름 단위** 락.
   - Initialization 락 (`InstanceKlass._init_lock`): `<clinit>` 게이트 — **Class 객체 단위** 락, JVM이 잡음, 04장.

핵심 한 줄: **ClassLoader는 "어디서 가져오나"를 책임지고, "어떻게 검증·초기화하나"는 JVM 본체가 책임진다.**

---

## 2. 가지 ②: WHAT — JDK 9+ 표준 3계층

### 2.1 핵심 질문

> "ClassLoader 3계층은 무엇이고 각각 어디서 무엇을 로드하는가?"

### 2.2 키워드 1 — Bootstrap (C++, null)

| 항목 | 값 |
|---|---|
| 구현 | C++ (HotSpot 내장) |
| 로드 대상 | `$JAVA_HOME/lib/modules`의 `java.base` 등 핵심 모듈 |
| `getClassLoader()` 결과 | **`null`** |
| 부모 | 없음 |

```java
String.class.getClassLoader();   // null
```

**Bootstrap이 왜 C++인가**: chicken-and-egg. Bootstrap이 로드하는 클래스 = `java.lang.Object`, `java.lang.ClassLoader`. 즉 Bootstrap은 ClassLoader 클래스 자신을 로드해야 한다. → Java로 작성된 ClassLoader는 작동 불가 → JVM의 native C++로 작성. `getClassLoader()`가 `null`인 이유도 이것 — Java 객체가 아니라서.

### 2.3 키워드 2 — Platform / Application

| ClassLoader | 클래스 | 로드 대상 | 부모 |
|---|---|---|---|
| **Platform** | `jdk.internal.loader.ClassLoaders$PlatformClassLoader` | `java.sql`, `java.xml`, `java.naming`, `java.logging` 등 비핵심 표준 모듈 | Bootstrap |
| **Application** | `jdk.internal.loader.ClassLoaders$AppClassLoader` | `-cp`, `--module-path`, `CLASSPATH` env | Platform |

**자주 헷갈리는 포인트: Spring Boot에서 가져오는 라이브러리는 Platform CL에 들어가나?**

**아니다. Application CL이다.** Platform은 JDK가 자체 제공하는 표준 모듈만 담당하는 **JDK 내부 슬롯**. Maven/Gradle로 가져온 외부 라이브러리는 절대 Platform에 안 들어간다.

```java
System.out.println(java.sql.Connection.class.getClassLoader());
// → PlatformClassLoader

System.out.println(org.springframework.context.ApplicationContext.class.getClassLoader());
// → LaunchedURLClassLoader (fat jar) 또는 AppClassLoader (IDE)
```

**오해 정정**:
- `java.sql.Driver` (인터페이스) → **Platform CL** (JDK가 정의한 표준 API라서)
- `com.mysql.cj.jdbc.Driver` (구현) → **Application/LaunchedURLClassLoader** (외부 라이브러리)
- 이 비대칭이 가지 ⑤의 **TCCL/SPI** 문제의 출발점.

### 2.4 키워드 3 — JDK 8 이하 옛 3계층과의 차이

```
JDK 1.2 ~ 8                          JDK 9+
─────────────                        ─────────────
[Bootstrap CL] (C++)                 [Bootstrap CL] (C++)
  rt.jar (60MB 한 덩어리)              $JAVA_HOME/lib/modules의 java.base
        ↑                                  ↑
[Extension CL]                       [Platform CL]
  $JAVA_HOME/lib/ext/*.jar             java.sql, java.xml, java.naming
        ↑                                  ↑
[System CL = AppClassLoader]         [Application CL = AppClassLoader]
  -cp / CLASSPATH                      -cp / --module-path
```

**무엇이 바뀐 이유 (JEP 220)**:
1. **rt.jar 해체**: 60MB 한 jar가 부팅·메모리·보안에 비효율 → 모듈로 분리.
2. **Extension 메커니즘 폐기**: `lib/ext`에 jar를 떨궈 모든 자바 앱에 강제 주입하는 방식이 보안 위험. JDK 9부터 사용 불가.
3. **이름 변경**: `sun.misc.Launcher$AppClassLoader` (JDK 8 이하) → `jdk.internal.loader.ClassLoaders$AppClassLoader` (JDK 9+). 옛 reflection 코드가 깨지는 흔한 마이그레이션 이슈.

운영자가 이 역사를 알아야 하는 이유: JDK 8 시스템이 아직 많고, 옛 라이브러리가 `sun.misc.Launcher$ExtClassLoader` reflection 접근 → JDK 9+에서 `ClassNotFoundException` 또는 `IllegalAccessError`.

### 2.5 ClassLoaderData (CLD) — Metaspace 단위

각 ClassLoader에 1:1로 붙는 HotSpot 내부 C++ 구조.

```cpp
class ClassLoaderData : public CHeapObj<mtClass> {
  oop _class_loader;            // Java ClassLoader 객체 (weak ref)
  Klass* _klasses;              // 이 CL이 로드한 클래스들
  Metaspace* _metaspace;        // ★ 이 CL 전용 Metaspace chunk ★
  Dependencies _dependencies;
};
```

**Metaspace는 CLD 단위로 chunk 할당** → CL이 GC되면 그 CLD의 chunk 통째로 해제. → **CL 누수 = Metaspace 누수** (가지 ⑥).

---

## 3. 가지 ③: HOW — 위임 알고리즘과 defineClass

### 3.1 핵심 질문

> "loadClass 알고리즘은 어떻게 동작하고, findClass/defineClass와 어떻게 다른가?"

### 3.2 키워드 1 — loadClass 알고리즘

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
                    c = findBootstrapClassOrNull(name);
                }
            } catch (ClassNotFoundException e) {
                // 부모가 못 찾았다 — 정상. 내가 찾으면 됨.
            }

            if (c == null) {
                // 3. 부모가 못 찾았으면 내가 찾는다
                c = findClass(name);  // ★ subclass에서 override ★
            }
        }
        if (resolve) resolveClass(c);
        return c;
    }
}
```

**알고리즘 3단계**:
1. 캐시 확인 (`findLoadedClass`)
2. 부모 위임 (재귀적으로 Bootstrap까지)
3. 내가 `findClass`

### 3.3 키워드 2 — findClass vs defineClass vs loadClass

| 메서드 | 누가 호출 | 역할 |
|---|---|---|
| `loadClass(name)` | 외부에서 (보통 JVM) | 위임 알고리즘 실행 |
| `findClass(name)` | `loadClass`가 내부적으로 | 실제로 .class 바이트 찾기 (subclass override) |
| `defineClass(name, bytes, ...)` | `findClass`가 내부에서 | byte[]를 `Class<?>` 객체로 변환 (native call) |

**커스텀 ClassLoader 작성 패턴**: `findClass`만 override, `loadClass`는 그대로 두면 표준 위임 모델 유지.

```java
public class MyClassLoader extends ClassLoader {
    @Override
    protected Class<?> findClass(String name) throws ClassNotFoundException {
        byte[] bytes = readBytesFromSomewhere(name);
        return defineClass(name, bytes, 0, bytes.length);
    }
}
```

### 3.4 키워드 3 — Parallel ClassLoader

JDK 7 (JEP 168) 이전:
- `loadClass`가 `synchronized` — 한 번에 한 클래스만 로드.

JDK 7+:
- `parallelLockMap`으로 **클래스별 lock** → 동시 다른 클래스 로드 가능.
- 활성화: `ClassLoader.registerAsParallelCapable()` 호출.

운영 의미: 큰 앱에서 클래스 수천 개 로드 시 부팅 시간 ↓. 단, 같은 이름 클래스 동시 로드는 여전히 직렬화.

### 3.5 HotSpot 내부 — defineClass의 native

```c
// ClassLoader.c
JNIEXPORT jclass JNICALL
Java_java_lang_ClassLoader_defineClass1(JNIEnv *env, ...) {
    // byte[] → native buffer → JVM_DefineClassWithSource 호출
    return JVM_DefineClassWithSource(env, ...);
}
```

```cpp
// jvm.cpp
static jclass jvm_define_class_common(...) {
  // 1. ClassLoaderData 찾기 또는 생성
  ClassLoaderData* loader_data = register_loader(class_loader);

  // 2. ClassFileParser로 .class 파싱 (01장)
  ClassFileStream st((u1*)buf, len, source, ...);
  Klass* k = SystemDictionary::resolve_from_stream(&st, ...);

  // 3. 결과를 java.lang.Class oop으로 변환
  return (jclass)JNIHandles::make_local(THREAD, k->java_mirror());
}
```

→ 01장 ClassFile 파싱이 여기서 일어남. 출력물 = `InstanceKlass`가 CLD의 Metaspace에 적재.

### 3.6 JDK 9+ 위임은 모듈 우선

```java
// BuiltinClassLoader.java (요약)
protected Class<?> loadClassOrNull(String cn, boolean resolve) {
    synchronized (getClassLoadingLock(cn)) {
        Class<?> c = findLoadedClass(cn);
        if (c == null) {
            // 모듈 이름이 결정되어 있나 (JPMS)
            LoadedModule loadedModule = findLoadedModule(cn);
            if (loadedModule != null) {
                // 그 모듈을 정의한 CL이 로드
                c = loadedModule.loader().loadClassOrNull(cn);
            } else {
                // 모듈 경계 밖 — 표준 위임
                if (parent != null) c = parent.loadClassOrNull(cn);
                if (c == null) c = findClassOnClassPathOrNull(cn);
            }
        }
        return c;
    }
}
```

→ 같은 클래스 이름이라도 모듈에 따라 다른 CL이 로드.

---

## 4. 가지 ④: Spring Boot — 실제 부팅 전체 흐름

### 4.1 핵심 질문

> "Spring Boot fat jar는 어떻게 부팅하고, 누가 무엇을 로드하는가?"

### 4.2 키워드 1 — fat jar 구조와 JarLauncher

```
shop-1.0.0.jar
├── META-INF/MANIFEST.MF
│     Main-Class: org.springframework.boot.loader.JarLauncher
│     Start-Class: com.example.shop.ShopApplication
├── org/springframework/boot/loader/         ★ 부트 로더 (압축 안 됨)
│   ├── JarLauncher.class
│   └── LaunchedURLClassLoader.class
├── BOOT-INF/
│   ├── classes/                              ★ 내가 짠 코드
│   └── lib/                                  ★ 의존성 jar들 (중첩 jar)
│       ├── spring-core-6.1.5.jar
│       ├── hibernate-core-6.4.4.jar
│       └── mysql-connector-j-8.3.0.jar
```

**핵심**:
- `Main-Class`는 우리가 만든 `ShopApplication`이 **아니라** Spring Boot의 `JarLauncher`.
- `Start-Class`에 진짜 메인 클래스가 따로 적혀 있다 (`JarLauncher`가 reflection으로 호출).
- `BOOT-INF/lib`의 jar들은 **중첩 jar** — 표준 JVM은 jar 안의 jar를 직접 못 푼다 → Spring Boot가 자기 CL을 끼움.

### 4.3 키워드 2 — LaunchedURLClassLoader

부팅 흐름:
```
[a] OS가 java 바이너리 실행
[b] HotSpot Bootstrap CL 생성 (C++, java.base 로드)
[c] Bootstrap → Platform CL 생성 (java.sql 등 준비)
[d] Platform → Application CL 생성 (-cp / jar 매니페스트 해석)
[e] AppCL이 MANIFEST의 Main-Class = "JarLauncher" 로드 → main() 호출
[f] JarLauncher가 LaunchedURLClassLoader(부모=AppCL) 생성       ★ Spring Boot 고유
[g] LaunchedURLClassLoader가 BOOT-INF/lib/*.jar + BOOT-INF/classes 등록
[h] JarLauncher가 TCCL을 LaunchedURLClassLoader로 설정
[i] JarLauncher가 Start-Class("ShopApplication") 로드 + main() reflection 호출
[j] SpringApplication.run(...) → 우리가 아는 부팅 시작
```

| CL | 부모 | 로드 예시 |
|---|---|---|
| **Bootstrap** | (없음) | `java.lang.Object`, `java.lang.String`, `java.lang.Thread` |
| **Platform** | Bootstrap | `java.sql.DriverManager`, `java.xml.parsers.SAXParser` |
| **Application** | Platform | `org.springframework.boot.loader.JarLauncher` 그 자체 |
| **LaunchedURLClassLoader** | Application | `ShopApplication`, `ApplicationContext`, `SessionFactory`, `ObjectMapper`, `com.mysql.cj.jdbc.Driver` |

**왜 굳이 이렇게 설계했나**:

| 대안 | 문제 |
|---|---|
| 의존성 jar를 별도 `lib/` 디렉터리에 풀기 | `-cp lib/*` 명령. Docker 이미지에 파일 수백 개. |
| 모든 클래스를 한 jar에 합치기 (shade) | 같은 패키지 다른 버전 충돌. `META-INF/services` 덮어쓰기. |
| 표준 `URLClassLoader`로 nested jar 읽기 | 불가 — 표준은 jar 안의 jar 못 봄. |

→ Spring Boot는 fat jar 구조를 유지하면서 클래스패스 시맨틱을 깨지 않으려고 자기 CL을 끼웠다. 위임 방향은 표준 그대로(부모 먼저).

### 4.4 키워드 3 — DevTools Restart/Base 분리

`spring-boot-devtools` 추가 시:

```
[Bootstrap] → [Platform] → [Application]
                              ↓
                  [Base ClassLoader]      ← jar 의존성 (변경 거의 안 됨)
                       Spring, Hibernate, Jackson ...
                              ↓
                  [Restart ClassLoader]   ← 매 재시작마다 새로 생성
                       내 코드 (BOOT-INF/classes 또는 build/classes)
```

코드 저장 → DevTools가 RestartClassLoader만 버리고 새로 생성 → 내 코드만 다시 로드. Base CL 살아남음 → 재시작 빠름.

**DevTools 분리의 부작용**:
- `instanceof` 거짓: 내 코드의 `Order`가 Base의 캐시 라이브러리에 들어갔다가 재시작하면, 캐시 안 옛 `Order`(옛 RestartCL)와 새 `Order`(새 RestartCL)가 다른 Class → `ClassCastException`.
- 옛 RestartCL이 어딘가 참조되면 GC 안 됨 → **Metaspace 누수** (재시작 10번 누적 시 OOM).

### 4.5 BOOT-INF/lib에서 클래스 1개 로드되는 순서

내 코드가 `new ObjectMapper()` 호출 시:

```
1. JVM이 "com.fasterxml.jackson.databind.ObjectMapper" 필요 인식
2. 호출자(OrderController)를 정의한 CL = LaunchedURLClassLoader에 위임
3. LaunchedURLClassLoader.loadClass:
   a. findLoadedClass — 캐시 확인
   b. parent.loadClass — AppCL → Platform → Bootstrap (다 없음)
   c. ★ findClass ★ — BOOT-INF/lib/jackson-databind-*.jar에서
      com/fasterxml/jackson/databind/ObjectMapper.class byte[] 추출
      → defineClass → InstanceKlass 생성
   d. CLD(LaunchedURLClassLoader)의 Metaspace chunk에 적재
4. Linking (Verify → Prepare → Resolve) — 03장
5. Initialization (static 블록) — 04장
6. 호출자에게 Class<?> 반환
```

이 순서가 **모든 외부 라이브러리 클래스가 메모리에 올라오는 표준 경로**다. 운영 에러 진단 시 어느 단계에서 깨졌는지 짚을 수 있어야 한다.

### 4.6 IDE 실행과의 차이

`LaunchedURLClassLoader`는 **`java -jar fat.jar`일 때만** 등장. IDE/Maven 플러그인(`mvn spring-boot:run`)은 의존성 jar를 `-cp`에 펼쳐 넘기므로 AppClassLoader가 직접 모두 로드.

→ "IDE에선 잘 되는데 운영에선 ClassNotFoundException"이 종종 발생하는 이유 (resource 경로 처리 차이 등).

---

## 5. 가지 ⑤: SPI와 ThreadContextClassLoader

### 5.1 핵심 질문

> "DriverManager는 왜 부모 위임을 우회해야 하고, TCCL은 어떻게 그 문제를 푸는가?"

### 5.2 키워드 1 — SPI는 "구현체를 남이 끼우는" 패턴

| 비교 | API | SPI |
|---|---|---|
| 누가 호출? | 내가 호출 | 내가 호출당함 (프레임워크/JDK가 호출) |
| 누가 구현? | 라이브러리, 내가 사용 | 내가 구현, 라이브러리가 사용 |
| 예시 | `List`, `Map` | `Driver`, `MessageBodyReader` |

**표준화된 SPI 등록 방법**: jar 안에 `META-INF/services/<인터페이스 FQCN>` 텍스트 파일.

```
mysql-connector-j.jar 안에:
META-INF/services/java.sql.Driver
  └─ com.mysql.cj.jdbc.Driver
```

`ServiceLoader.load(Driver.class)`가 이 파일을 읽어 구현체 발견.

**대표 SPI**: `java.sql.Driver`, `javax.xml.parsers.SAXParserFactory`, `javax.naming.spi.InitialContextFactory`, `org.slf4j.spi.SLF4JServiceProvider`, Spring `META-INF/spring.factories`.

### 5.3 키워드 2 — SPI 역참조 문제

```
[Platform CL]
    │
    ├─ java.sql.DriverManager       ← Platform CL이 로드 (JDK 표준)
    │
[Application CL]
    │
[LaunchedURLClassLoader]
    │
    ├─ com.mysql.cj.jdbc.Driver     ← BOOT-INF/lib/mysql-connector-j.jar
```

DriverManager가 `ServiceLoader.load(Driver.class)`로 모든 Driver 구현체를 찾으려고 한다.
**부모 위임은 자식이 부모에게 묻는 방향만 본다**. Platform 입장에서 LaunchedURL은 자기 자손 → 자손에게 묻는 경로가 위임 모델에 없음 → MySQL Driver 못 찾음.

### 5.4 키워드 3 — Thread Context ClassLoader

```java
public class Thread {
    private ClassLoader contextClassLoader;  // ★ 모든 스레드가 1개씩 ★
    public ClassLoader getContextClassLoader();
    public void setContextClassLoader(ClassLoader cl);
}
```

- **기본값**: 스레드 생성 시 부모 스레드 TCCL 복사. `main` 스레드의 TCCL = AppClassLoader (또는 LaunchedURL).
- **목적**: "지금 일하는 코드의 맥락 CL"을 위임 트리와 별개 슬롯으로 노출. → Bootstrap 코드도 `Thread.currentThread().getContextClassLoader()`만 부르면 자식 CL 손에 넣음.
- **위임 모델과의 관계**: TCCL은 위임을 **대체**하는 게 아니라 **우회**. 일반 클래스 로딩은 여전히 부모 위임. TCCL은 SPI처럼 정상 위임으로 못 푸는 케이스의 사이드채널.

```java
// DriverManager.java (요약)
private static void loadInitialDrivers() {
    ServiceLoader<Driver> loadedDrivers = ServiceLoader.load(Driver.class);
    // 내부적으로: ServiceLoader.load(service, Thread.currentThread().getContextClassLoader())
    for (Driver d : loadedDrivers) { /* register */ }
}
```

→ DriverManager(Platform)가 TCCL(=LaunchedURLClassLoader)을 통해 MySQL Driver 발견.

### 5.5 TCCL 누수 (DevTools/스레드 풀에서 자주)

```java
ExecutorService es = Executors.newFixedThreadPool(10);
es.submit(() -> { ... });

// 풀 스레드는 만들 당시 부모 스레드 TCCL을 그대로 들고 있음.
// DevTools 동작 중이면 그 TCCL은 RestartClassLoader.
// 재시작 → 새 RestartCL 생성. 풀 스레드는 안 죽음.
// 풀 스레드의 TCCL 필드가 옛 RestartCL을 계속 들고 있음
// → 옛 RestartCL이 GC root에 도달 가능
// → Metaspace에 옛 CL의 chunk 잔존 → 누수
```

해결: 풀 스레드의 TCCL을 명시 변경한 뒤 **반드시 finally에서 복원**.

```java
ClassLoader saved = Thread.currentThread().getContextClassLoader();
try {
    Thread.currentThread().setContextClassLoader(targetCL);
    // task 실행
} finally {
    Thread.currentThread().setContextClassLoader(saved);
}
```

### 5.6 Virtual Thread의 TCCL (JDK 21+)

- VThread는 부모 스레드 TCCL을 그대로 사용. `setContextClassLoader()` 명시 변경 가능.
- carrier thread와 분리됨: VThread A의 setContextClassLoader는 A의 TCCL만 변경. 같은 carrier에서 실행되는 다른 VThread B는 영향 없음.
- ThreadLocal 처리와 동일 원리 (JEP 444의 ScopedValue 영향).

---

## 6. 가지 ⑥: 운영 진단 — 에러와 누수

### 6.1 핵심 질문

> "로딩이 망가지면 어떤 에러가 어디서 발생하고 어떻게 진단하는가?"

### 6.2 키워드 1 — Spring Boot 로딩 에러 4가지

#### ClassNotFoundException (CNFE) — "그 클래스가 classpath에 없음"

발생: `loadClass`가 표준 위임을 다 돌고도 못 찾았을 때. 보통 `Class.forName(...)`이나 reflection에서 표면화.

원인:
1. 의존성 누락 (Maven `scope=provided`인데 fat jar에 안 들어감)
2. 모듈명 오타
3. JDK 9+에서 옛 내부 클래스 reflection (`sun.misc.Launcher$ExtClassLoader`)
4. JPMS의 `--add-modules` 누락

진단:
```bash
unzip -l shop-1.0.0.jar | grep ObjectMapper
jcmd <pid> VM.classloaders
```

#### NoClassDefFoundError (NCDFE) — "컴파일 땐 있었는데 런타임에 없음"

차이: CNFE는 *지금 처음 찾는 중 실패*, NCDFE는 *과거 로드는 됐는데 초기화 실패* 또는 *컴파일 때 보였던 게 런타임 classpath에 없음*. JVM이 던지는 `Error` 계열.

원인:
1. **연쇄적 초기화 실패**: 클래스 X의 `static {}` 블록이 예외를 던지면 이후 X 참조는 모두 NCDFE. 진짜 원인은 **첫 번째 `ExceptionInInitializerError`의 스택**.
2. **Provided scope 잘못 설정**: `javax.servlet-api`가 런타임에 없음.
3. **버전 다운그레이드**: 컴파일은 Spring 6.1, 배포는 6.0이라 추가된 클래스가 없음.

#### LinkageError / IncompatibleClassChangeError — "같은 클래스 다른 버전 충돌"

발생: 같은 이름 클래스가 두 CL에서 정의됐는데 서로 다른 시그니처/인터페이스를 가질 때.

전형적 원인 (Spring Boot 실전):
1. **transitive 의존성 버전 충돌**: 어떤 jar는 6.1 시그니처를 가정해 컴파일됐는데 런타임은 6.0 → `NoSuchMethodError` 또는 `LinkageError`.
2. **DevTools의 두 CL에 같은 클래스가 동시에**: include/exclude 설정 실수 → `LinkageError: loader constraint violation`.

진단:
```bash
./gradlew dependencyInsight --dependency spring-core
mvn dependency:tree -Dverbose | grep -A2 spring-core
```

#### ClassCastException "X cannot be cast to X" — 같은 이름 다른 CL

발생: 같은 FQCN인데 두 CL이 각각 정의한 Class 객체가 둘 있을 때. JVM 입장에서 `(name, defining loader)`가 다르면 다른 타입.

Spring Boot 실전:
1. **DevTools Restart/Base 경계 위반** (가장 흔함): Base CL의 Caffeine 캐시에 RestartCL의 `Order` 인스턴스를 put → 재시작 → 새 RestartCL의 `Order`로 get 시도 → CCE.
2. **부모-자식 양쪽에 같은 jar**: 사용자 코드가 `URLClassLoader` 직접 생성해 같은 jar 등록.

진단:
```java
System.out.println(obj1.getClass().getClassLoader());
System.out.println(obj2.getClass().getClassLoader());
// 둘이 다르면 그게 원인.
```

### 6.3 키워드 2 — CL 누수와 Metaspace OOM

#### 원리

ClassLoader는 자기가 로드한 모든 클래스를 참조, 클래스도 자기 CL을 역참조. 누구든 그 CL을 GC root에서 도달 가능한 곳에 들고 있으면 **전체 CL + 그 클래스들 + 그 인스턴스들이 모두 살아남음**.

#### 흔한 누수 원인 6가지

1. **ThreadLocal**: 풀 스레드가 옛 CL이 로드한 클래스 인스턴스를 ThreadLocal에 보관. 풀 스레드는 안 죽음 → 영원.
2. **JDBC Driver**: DriverManager(Platform)가 BOOT-INF/lib의 MySQL Driver(LaunchedURL/Restart CL) 참조 보관.
3. **JMX MBean**: 등록 해제 안 한 MBean이 옛 CL 클래스 참조.
4. **Static field**: 부모 CL의 static collection에 자식 CL 객체 보관.
5. **Logging**: Log4j MDC, SLF4J marker.
6. **Reflection cache**: `java.beans.Introspector`, Caffeine static 캐시.

#### 진단 흐름

```
1. heap dump: jcmd <pid> GC.heap_dump dump.hprof
2. MAT(Eclipse Memory Analyzer) 열기
3. Histogram에서 ClassLoader 검색
   → "RestartClassLoader" 인스턴스 개수 확인 (1개여야 정상)
4. 여러 개면 누수 — 마우스 우클릭 → "Path to GC Roots"
5. 보통 범인:
   - java.lang.Thread (TCCL 또는 ThreadLocal)
   - java.sql.DriverManager.registeredDrivers
   - 사용자 코드의 static field
```

#### JDBC Driver 누수 정확한 메커니즘 (Spring Boot 일반)

```
1. fat jar 실행 → Hibernate/HikariCP가 DriverManager.getConnection() 호출
2. DriverManager(Platform CL)가 TCCL(=LaunchedURL/RestartCL)을 통해
   META-INF/services/java.sql.Driver에서 MySQL Driver 발견
3. MySQL Driver의 <clinit>에서 DriverManager.registerDriver(this) 호출
4. DriverManager.registeredDrivers(Platform CL의 static 리스트)에 Driver 인스턴스
   (LaunchedURL/RestartCL이 정의한 클래스의 인스턴스) 들어감
5. Spring 컨텍스트 종료 시 LaunchedURL/RestartCL을 unload하고 싶어도
   위 리스트가 참조를 들고 있음 → CL 누수 → Metaspace 살아남음
```

해결 (`@PreDestroy`):
```java
@PreDestroy
public void deregisterDrivers() {
    ClassLoader myCL = getClass().getClassLoader();
    for (Driver d : Collections.list(DriverManager.getDrivers())) {
        if (d.getClass().getClassLoader() == myCL) {
            try { DriverManager.deregisterDriver(d); } catch (SQLException ignore) {}
        }
    }
}
```

일반 운영(앱이 떴다가 SIGTERM으로 죽음)에선 무해. DevTools나 테스트 컨텍스트 재로딩처럼 한 JVM 안에서 CL이 반복 생성되는 환경에서 표면화.

### 6.4 키워드 3 — ClassLoader GC와 Metaspace 정리

#### CL이 GC되는 조건

다음 **모두** 만족 시:
1. ClassLoader 객체에 대한 reachable reference 없음.
2. 그 CL이 로드한 모든 클래스의 인스턴스 unreachable.
3. 그 CL이 로드한 모든 클래스의 Class 객체 unreachable.
4. 다른 CL이 이 CL의 클래스를 참조하지 않음 (resolution dependency).

한 가지라도 깨지면 누수.

#### Metaspace 정리 흐름

1. ClassLoader oop이 GC된 것을 GC가 감지
2. CLD를 dead로 표시
3. **다음 Metaspace GC 사이클**에서 그 CLD의 모든 Metaspace chunk를 free list로 반환
4. Compressed Class Space entry도 함께 정리
5. CLD가 들고 있던 InstanceKlass들 모두 해제

즉, 즉시 해제가 아니라 두 단계 (Java Heap GC → Metaspace cleanup). `-XX:+ClassUnloadingWithConcurrentMark`로 동시 마킹과 같이 처리 (G1 기본 on).

**ZGC/Shenandoah**: 모든 phase가 concurrent — 별도 ClassUnloading STW 없음. 백그라운드에서 unmarked CLD 발견해 free list로.

#### URLClassLoader.close()의 의미

`close()`는 **리소스 정리**(파일 핸들)일 뿐, **메모리 회수** 아님.
- 열린 JAR/URL stream을 닫음.
- 이후 `loadClass`는 CNFE.
- **하지만 이미 로드한 클래스는 메모리에 남음**.

메모리까지 회수하려면 그 CL 참조가 모두 사라져야 함 + GC 발생.

### 6.5 JPMS opens / 캡슐화 에러

JDK 9+ `jdk.internal.*` reflection 차단 → `IllegalAccessError` / `InaccessibleObjectException`.

Spring Boot 3 + JDK 17+ 마이그레이션 시 자주:
```
--add-opens java.base/java.lang=ALL-UNNAMED
--add-opens java.base/sun.nio.ch=ALL-UNNAMED
```

옛 ByteBuddy/CGLib, `sun.misc.Unsafe` 사용 라이브러리에서 발생.

---

## 7. 면접 답변 워크플로우

### 7.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "부모 위임 모델 설명" | ① WHY | ② WHAT (3계층) |
| "Bootstrap이 왜 C++인가요?" | ② WHAT | ① chicken-and-egg |
| "Spring Boot 라이브러리는 어느 CL이 로드?" | ② WHAT | ④ LaunchedURLClassLoader |
| "loadClass / findClass / defineClass 차이?" | ③ HOW | ⑥ 커스텀 CL 작성 |
| "Spring Boot fat jar에서 LaunchedURLClassLoader가 왜 필요?" | ④ Spring Boot | ② AppCL과의 관계 |
| "DevTools로 CCE가 나는데 진단?" | ④ DevTools | ⑥ CL 경계 |
| "DriverManager는 어떻게 MySQL Driver 찾나?" | ⑤ SPI/TCCL | ② Platform vs App |
| "CL 메모리 누수 원인?" | ⑥ 누수 | ⑤ TCCL/JDBC |
| "DevTools 누적 후 Metaspace OOM 진단" | ⑥ Metaspace | MAT 사용 |
| "URLClassLoader.close()는 메모리 회수?" | ⑥ GC | ② CLD |
| "JDK 9 Module System은 CL을 어떻게 바꿨나?" | ② 옛/새 비교 | ③ 모듈 우선 위임 |

### 7.2 답변 템플릿

> **루트 문장 한 줄 → 해당 가지 키워드 3개 순서 → 듣는 사람 표정 보고 인접 가지로**

예: "Spring Boot fat jar에서 LaunchedURLClassLoader는 왜 필요?"

> "ClassLoader는 `.class` 바이트를 찾아 Class 객체로 변환하는 자고, 표준 3계층 위에 프레임워크가 자기 CL을 한 겹 더 얹는 패턴이 일반적입니다. (← 루트)
> Spring Boot의 fat jar는 의존성을 `BOOT-INF/lib/*.jar`라는 **중첩 jar**로 묶습니다. 표준 `URLClassLoader`는 jar 안의 jar를 직접 열어 클래스 바이트를 추출 못 합니다.
> 그래서 Spring Boot는 `LaunchedURLClassLoader`(AppCL의 자식)를 만들어 BOOT-INF/lib의 각 nested jar를 URL 후보로 등록하고, `findClass`가 호출되면 그 안에서 .class 바이트를 직접 꺼내 `defineClass`로 정의합니다.
> 위임 방향은 표준 그대로(부모 먼저) — 위임을 깨는 게 아니라 **표준 모델 위에 한 단계 더 얹는** 접근입니다.
> 단, IDE나 `mvn spring-boot:run`은 의존성 jar를 `-cp`에 펼쳐 넘기므로 LaunchedURLClassLoader가 안 만들어집니다 → 'IDE에선 잘 되는데 운영에선 ClassNotFoundException' 패턴의 원인입니다."

→ 면접관이 "DevTools가 켜지면?" 물으면 ④ Restart/Base로, "CCE가 났을 때는?" 물으면 ⑥ 경계 위반으로.

---

## 8. 꼬리질문 트리 (가지별)

### Q1 [가지 ①]. 부모 위임 모델을 설명하세요.

> 모든 ClassLoader는 부모 CL을 가진다. `loadClass` 호출 시: 캐시 확인 → 부모에게 위임(재귀) → 부모가 못 찾으면 `findClass`로 내가 찾는다. 최상위는 Bootstrap(`parent == null`).
> 보장: (1) **Class spoofing 방지** — 악성 `java.lang.String`도 진짜에 가려짐. (2) **Type identity** — 같은 클래스가 여러 CL에서 정의되지 않음, JVM의 클래스 동등성은 `(name, defining loader)`.

**Q1-1: Bootstrap은 왜 Java가 아닌 C++인가요?**
> Chicken-and-egg. Bootstrap이 로드하는 클래스 = `java.lang.Object`, `java.lang.ClassLoader`. Bootstrap은 ClassLoader 클래스 자신을 로드해야 한다 → ClassLoader 클래스가 메모리에 없는 상태에서 Java ClassLoader는 작동 불가. → JVM native C++로 작성. `getClassLoader()`가 null인 이유도 이것.

**Q1-2: 부모 위임이 깨지면?**
> 같은 클래스 두 번 로드 → 다른 Class 객체 → ClassCastException. 표준 라이브러리 위변조 가능. type identity 깨짐 → reflection/instanceof 예상 외 결과.

### Q2 [가지 ②]. JDK 9에서 ClassLoader 구조가 어떻게 바뀌었나요?

> Bootstrap → Platform → Application의 새 3계층. ExtClassLoader 폐기. 옛 60MB `rt.jar`를 모듈로 잘게 쪼갬(JEP 220). `$JAVA_HOME/lib/ext` 메커니즘도 보안 위험으로 폐기.
> 클래스 이름 변경: `sun.misc.Launcher$AppClassLoader` → `jdk.internal.loader.ClassLoaders$AppClassLoader`. 옛 reflection 코드 깨지는 마이그레이션 이슈.
> 위임 알고리즘도 **모듈 우선** — 같은 클래스 이름이라도 모듈에 따라 다른 CL이 로드.

**Q2-1: Spring Boot 라이브러리는 Platform에 들어가나요?**
> 아니다. Platform은 JDK 자체 제공 표준 모듈(`java.sql`, `java.xml`)만 담당하는 JDK 내부 슬롯. Maven/Gradle 외부 라이브러리는 절대 Platform 안 들어감, 모두 Application(또는 LaunchedURLClassLoader).
> 함정: `java.sql.Driver`(인터페이스)는 Platform, `com.mysql.cj.jdbc.Driver`(구현)는 Application. 이 비대칭이 TCCL/SPI 문제의 출발.

### Q3 [가지 ③]. loadClass / findClass / defineClass 차이?

> `loadClass(name)`: 외부 호출 진입점, 위임 알고리즘 실행. `findClass(name)`: 내가 실제로 .class 찾기, subclass에서 override. `defineClass(name, bytes, ...)`: byte[]를 Class<?>로 변환하는 native call.
> 커스텀 CL 작성 패턴: `findClass`만 override, `loadClass`는 그대로 → 표준 위임 모델 유지.

**Q3-1: Parallel ClassLoader는?**
> JDK 7 (JEP 168). 이전엔 `loadClass`가 synchronized — 한 번에 한 클래스만. 7부터 `parallelLockMap`으로 클래스별 lock → 동시 다른 클래스 로드 가능. `ClassLoader.registerAsParallelCapable()`로 활성화. 큰 앱 부팅 시간 ↓.

### Q4 [가지 ④]. Spring Boot fat jar에서 `LaunchedURLClassLoader`는 왜 필요?

> fat jar는 의존성을 `BOOT-INF/lib/*.jar`라는 **중첩 jar**로 묶음. 표준 `URLClassLoader`는 jar 안의 jar를 직접 못 푼다.
> Spring Boot가 `LaunchedURLClassLoader`(AppCL의 자식)를 만들어 BOOT-INF/lib의 각 nested jar를 URL 후보로 등록, `findClass`에서 .class 바이트 직접 추출 + `defineClass`. 위임 방향은 표준 그대로.

**Q4-1: IDE나 `mvn spring-boot:run`은?**
> LaunchedURLClassLoader 안 만들어짐. IDE/Maven 플러그인은 의존성 jar를 `-cp`에 펼쳐 넘김 → AppClassLoader가 직접 모두 로드.
> 운영 환경(Docker에서 `java -jar`)에서만 LaunchedURL 등장 → "IDE에선 되는데 운영에선 CNFE" 패턴의 원인.

**Q4-2: DevTools 켜졌을 때 CCE 자꾸 난다면?**
> 거의 항상 **Restart/Base 경계 위반**.
> 1. 두 Class의 `getClassLoader()` 비교: 같은 FQCN이지만 다른 CL이면 그게 원인.
> 2. 옛 RestartCL이 어디서 살아남았는지 추적: Base의 캐시(Caffeine static), ThreadLocal, JDBC DriverManager 등.
> 3. 해결: 변경되는 클래스를 Base 캐시에 넣지 않거나, `restart.exclude`로 영역 명확히 분리.

### Q5 [가지 ⑤]. DriverManager는 어떻게 MySQL Driver를 찾나? TCCL이 왜 필요?

> SPI 역참조 문제. DriverManager는 Platform CL, MySQL Driver는 LaunchedURL/AppCL. 부모 위임은 자식→부모 방향만 — Platform이 자손 LaunchedURL의 코드를 찾는 경로가 위임 모델에 없음.
> 해결: **Thread Context ClassLoader**. 모든 `Thread`가 `contextClassLoader` 필드 1개를 들고 있음. `ServiceLoader.load(Driver.class)`가 내부적으로 `Thread.currentThread().getContextClassLoader()` 사용 → 보통 LaunchedURL/App → BOOT-INF/lib의 Driver 발견.
> TCCL은 위임을 **대체**하는 게 아니라 **우회**하는 사이드채널.

**Q5-1: Thread Pool에서 TCCL 설정?**
> 풀 스레드는 만들 당시 부모 TCCL 상속. 변경 시:
> ```java
> ClassLoader saved = Thread.currentThread().getContextClassLoader();
> try {
>     Thread.currentThread().setContextClassLoader(targetCL);
> } finally {
>     Thread.currentThread().setContextClassLoader(saved);  // ★ 반드시 복원 ★
> }
> ```
> 복원 안 하면 옛 TCCL이 풀 스레드에 남아 CL 누수.

**Q5-2: Virtual Thread의 TCCL?**
> JDK 21+. VThread는 부모 TCCL 그대로 사용, 명시 변경 가능. carrier thread와 분리 — VThread A의 setContextClassLoader는 A에만 영향, 같은 carrier의 다른 VThread B는 별개. ThreadLocal 처리와 동일 원리.

### Q6 (Killer) [가지 ⑥]. Spring Boot DevTools로 재시작 누적하다 Metaspace OOM이 나면 진단?

> 1. **heap dump**: `jcmd <pid> GC.heap_dump file.hprof`
> 2. **MAT** 열기: Histogram → `RestartClassLoader` 검색. 정상이면 1개, 여러 개면 누수.
> 3. **"Path to GC Roots"** → 누가 옛 CL을 들고 있는지 추적.
> 4. **흔한 범인**:
>    - `java.lang.Thread.contextClassLoader` (옛 TCCL)
>    - `java.lang.Thread.threadLocals` (ThreadLocal에 옛 클래스 인스턴스)
>    - `java.sql.DriverManager.registeredDrivers`
>    - `java.beans.Introspector` BeanInfo 캐시
>    - 사용자 코드의 static collection
> 5. **수정**: `@PreDestroy`에서 Driver deregister, ThreadLocal cleanup, ExecutorService shutdown.

**Q6-1: JDBC Driver 누수가 정확히 어떻게 일어나는가?**
> (1) Hibernate/HikariCP가 `DriverManager.getConnection()` 호출
> (2) DriverManager(Platform)가 TCCL을 통해 META-INF/services/java.sql.Driver에서 MySQL Driver 발견
> (3) MySQL Driver `<clinit>`에서 `DriverManager.registerDriver(this)`
> (4) `DriverManager.registeredDrivers`(Platform의 static 리스트)에 Driver 인스턴스(LaunchedURL/Restart가 정의한 클래스의 인스턴스) 들어감
> (5) 컨텍스트 종료 시 LaunchedURL/Restart을 unload하고 싶어도 위 리스트가 참조 보관 → CL 누수.
> 수정: `@PreDestroy`에서 자기 CL이 정의한 Driver만 deregister.

### Q7 [가지 ⑥]. `URLClassLoader.close()`를 호출하면?

> 리소스 정리(JAR/URL 파일 핸들)일 뿐, 메모리 회수 아님. 이후 `loadClass`는 CNFE. **이미 로드한 클래스는 메모리에 남음** — 그 CL 참조가 모두 사라지고 GC가 발생해야 회수.

**Q7-1: ClassLoader가 GC되는 조건?**
> 모두 만족: (1) ClassLoader 객체에 reachable reference 없음, (2) 그 CL이 로드한 모든 클래스의 인스턴스 unreachable, (3) 그 CL이 로드한 모든 Class 객체 unreachable, (4) 다른 CL이 이 CL의 클래스를 참조하지 않음.
> 한 가지라도 깨지면 누수. ThreadLocal/static field/JMX/JDBC 등이 흔한 원인.

**Q7-2: Metaspace 정리는 어떻게?**
> 두 단계. (1) Java Heap GC가 ClassLoader oop dead 감지 → CLD를 dead 표시. (2) 다음 Metaspace GC 사이클에서 그 CLD의 모든 chunk를 free list로 반환. Compressed Class Space entry, InstanceKlass도 같이 해제. `-XX:+ClassUnloadingWithConcurrentMark`로 동시 마킹과 같이 처리(G1 기본 on). ZGC/Shenandoah는 모든 phase가 concurrent라 별도 STW 없음.

### Q8 [가지 ②]. JDK 9 Module System은 ClassLoader 모델을 어떻게 바꿨나?

> (1) Bootstrap 축소 — rt.jar(60MB) 모듈로 분리, java.base + 핵심만. (2) Platform CL 등장 — java.sql, java.xml 등. (3) ExtClassLoader 폐기. (4) ModuleLayer 도입 — Configuration → Module Graph → ModuleLayer → CL 매핑. (5) 위임에 모듈 우선 검색. (6) `requires`/`exports`로 모듈 단위 캡슐화.

**Q8-1: Module이 ClassLoader를 완전 대체하지 않은 이유?**
> (1) 하위 호환성 — 기존 라이브러리 모두 ClassLoader 기반. (2) 다른 추상화 레벨 — ClassLoader는 "어떻게 로드할지"(mechanism), Module은 "무엇을 누구에게 공개할지"(policy). (3) 동적 로딩 호환 — Module은 정적, ClassLoader는 동적. (4) Spring Boot의 LaunchedURLClassLoader처럼 런타임 동적 CL은 모듈 시스템 밖에서도 동작 필요.

---

## 9. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 이내로 그릴 수 있다 (루트 + 6가지 + 각 키워드 3개)
- [ ] 가지 ① WHY: 부모 위임의 두 가지 보장(spoofing 방지 / type identity)을 비유와 함께 설명한다
- [ ] 가지 ① WHY: ClassLoader 책임 경계(Loading까지만)와 Initialization 락이 별개임을 말한다
- [ ] 가지 ② WHAT: JDK 9+ 3계층을 그리고 각 CL의 로드 대상과 부모를 적는다
- [ ] 가지 ② WHAT: Bootstrap이 C++인 chicken-and-egg 이유와 `null` 반환을 설명한다
- [ ] 가지 ② WHAT: JDK 8 옛 3계층과 9+ 차이(rt.jar 해체, Extension 폐기, 이름 변경)를 적는다
- [ ] 가지 ③ HOW: loadClass 3단계 알고리즘(캐시→부모→findClass)을 코드로 그린다
- [ ] 가지 ③ HOW: findClass / defineClass / loadClass 역할을 표로 구분한다
- [ ] 가지 ④ Spring Boot: fat jar 부팅 [a]~[j] 흐름을 적는다
- [ ] 가지 ④ Spring Boot: LaunchedURLClassLoader가 BOOT-INF/lib을 어떻게 다루는지 설명한다
- [ ] 가지 ④ Spring Boot: DevTools Restart/Base 분리 이유와 부작용(CCE, 누수)을 적는다
- [ ] 가지 ⑤ SPI/TCCL: API와 SPI 차이, `META-INF/services` 등록 형식을 안다
- [ ] 가지 ⑤ SPI/TCCL: DriverManager가 TCCL을 쓰는 이유를 부모 위임 방향 문제로 설명한다
- [ ] 가지 ⑤ SPI/TCCL: 스레드 풀에서 TCCL 변경 시 finally 복원의 중요성을 말한다
- [ ] 가지 ⑥ 운영: CNFE / NCDFE / LinkageError / CCE의 차이와 원인을 구분한다
- [ ] 가지 ⑥ 운영: Metaspace OOM 진단 절차(heap dump → MAT → ClassLoader 검색)를 5단계로 적는다
- [ ] 가지 ⑥ 운영: JDBC Driver 누수의 5단계 메커니즘과 `@PreDestroy` 해결법을 말한다
- [ ] 가지 ⑥ 운영: URLClassLoader.close()는 리소스 정리일 뿐 메모리 회수 아님을 설명한다
- [ ] 8장 꼬리질문 8개에 막힘없이 답한다

---

## 다음 단계

- → [03. Linking](./03-linking.md): 로드된 클래스를 검증·준비·해결하는 3단계
- → [04. Initialization](./04-initialization-and-unload.md): static 블록 실행 + CL unload
- → [02-runtime-data-areas/02. Metaspace](../02-runtime-data-areas/02-metaspace-and-class-space.md): InstanceKlass가 사는 곳, CLD 단위 chunk 관리

## 참고

- **JLS §12 (Execution)**: https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html
- **JVMS §5 (Loading, Linking, Initializing)**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html
- **JEP 261 (Module System)**: https://openjdk.org/jeps/261
- **JEP 168 (Parallel ClassLoader)**: https://openjdk.org/jeps/168
- **JEP 371 (Hidden Classes)**: https://openjdk.org/jeps/371
- **Spring Boot Executable Jar Format**: https://docs.spring.io/spring-boot/specification/executable-jar/
- **Spring Boot DevTools (Restart vs Base CL)**: https://docs.spring.io/spring-boot/reference/using/devtools.html
