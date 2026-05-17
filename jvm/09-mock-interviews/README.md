# 09. Mock Interviews — 챕터별 꼬리질문 트리

> 이 챕터는 **jvm/ 디렉터리에서 학습한 모든 내용을 면접 형식으로 자가 점검**하는 자리다.
>
> - 질문은 **표면 → 깊이 → 운영 → 함정** 순으로 꼬리에 꼬리를 문다.
> - 모든 답은 토글(`<details>`)로 감춰뒀다. 먼저 자기 입으로 답해본 뒤 펴라.
> - 모든 답의 근거는 **jvm/00~12 챕터 본문 어딘가에 있다**. 답이 부족하면 출처 챕터로 돌아가 그 부분을 다시 읽어라.
> - 레벨 표기:
>   - 🟢 = Junior (1~3년) — 개념·정의
>   - 🟡 = Senior (3~10년) — 구조·운영
>   - 🔴 = Principal (10년+) — 트레이드오프·시스템 결정

---

## 🗺️ 사용 가이드

1. **챕터 순서대로 풀어도 좋고, 약한 영역만 골라 풀어도 좋다.**
2. 답을 본 뒤 "이 답이 어떤 챕터·문단의 어떤 그림으로 그릴 수 있나?"를 같이 떠올려라. 백지에 그릴 수 없으면 그 챕터로 돌아간다.
3. 마지막의 **종합 시나리오**는 챕터를 가로질러 묻는다. 챕터별 트리에 자신 있으면 그쪽으로.

---

# 📖 Part 1 — 챕터별 꼬리질문 트리

## Ch 00. JVM 개요 (`00-overview/`)

### Q0-1. 🟢 JVM·JRE·JDK 셋의 차이는?

<details>
<summary>모범 답 (펼치기)</summary>

- **JVM**: bytecode를 실행하는 가상 머신. HotSpot, OpenJ9, GraalVM 등 여러 구현.
- **JRE**: JVM + 표준 라이브러리(`java.*`, `javax.*` 등).
- **JDK**: JRE + 개발 도구(`javac`, `jcmd`, `jstack`, `jfr`).

JDK 9+부터 JRE 별도 배포는 종료. 개념적 구분만 남았고, 운영에선 **JDK 배포본 하나 = JRE+도구 모두 포함**으로 본다.

> 출처: `00-overview/01-what-is-jvm-jre-jdk.md`

</details>

#### 🪝 Q0-1-1. 🟡 javac가 만든 `.class`는 JVM마다 다른가? 같은가?

<details>
<summary>답</summary>

**같다.** `.class`는 JVM 명세(JVMS)에 따른 표준 포맷. 어느 JVM 구현(HotSpot/OpenJ9/Graal)에서도 동일한 바이트 시퀀스가 동작.
다른 건 **JVM 내부의 GC·JIT·런타임 자료구조(InstanceKlass 등)** — 이건 구현마다 다르다.

> 출처: `00-overview/02-class-compilation-flow.md`, `00-overview/03-jvm-architecture-bigpicture.md`

</details>

##### 🪝 Q0-1-1-1. 🔴 그럼 GraalVM Native Image로 만든 바이너리는 어디에 속하나?

<details>
<summary>답</summary>

**JVM 위에서 실행되는 게 아니다.** Native Image는 빌드 시점에 AOT(Ahead-Of-Time) 컴파일로 `.class`를 native 실행파일로 번역해 둔다. JVM도, 인터프리터도, JIT도 런타임에 없음.
- 장점: 부팅 ms 단위, 메모리 작음.
- 단점: 런타임 클래스 로딩·reflection 제한적, 빌드 시간 김.

> 출처: `08-graalvm/README.md`

</details>

### Q0-2. 🟢 자바 코드 한 줄이 실행되기까지의 흐름을 한 번에 그려라.

<details>
<summary>모범 답</summary>

```
.java ──javac──► .class (bytecode + ConstantPool)
                    │
                    ▼  (이 챕터의 출발점)
                Loading       ← ClassLoader가 .class를 InstanceKlass로 변환
                    │
                    ▼
                Linking (Verification → Preparation → Resolution)
                    │
                    ▼
                Initialization (<clinit>)
                    │
                    ▼
                Execution (Interpreter → JIT)
                    │
                    ▼
                GC가 Heap·Metaspace 회수, ClassLoader unload
```

> 출처: `00-overview/02-class-compilation-flow.md`, `01-class-lifecycle/README.md`

</details>

---

## Ch 01. Class Lifecycle (`01-class-lifecycle/`)

### Q1-1. 🟢 ClassFile의 `magic` 값 `0xCAFEBABE`가 무엇이고 왜 존재하나?

<details>
<summary>답</summary>

`.class` 파일의 첫 4바이트. "이 파일이 자바 클래스 파일이오"라는 자기 선언(매직 넘버). 다른 값이면 `ClassFormatError` 즉시 — 파싱조차 시도하지 않음.
- 어원: 1991년 자바 팀 농담("CAFE BABE"). 깊은 기술 의미는 없고 **외부 파일·전송 중 깨진 파일을 거르는 첫 관문**.
- 다른 포맷도 자기 매직 넘버를 갖는다: PNG `89 50 4E 47`, ZIP `50 4B 03 04`.

> 출처: `01-class-lifecycle/01-classfile-format.md`, `03-linking.md`(Pass 1 토글)

</details>

#### 🪝 Q1-1-1. 🟡 ConstantPool(CP)이 뭐고, 왜 필요한가? — 면접 답변 흐름

<details>
<summary>답 (5단계 흐름)</summary>

면접에서 강한 답의 핵심 프레임: **"CP는 단순한 상수 저장소가 아니라, Linking의 Resolution이 일하는 작업 테이블이다"**. 이 한 줄로 시작하면 "왜 있는지·어디서 연결되는지"가 한 번에 풀린다.

##### 1단계 — 정의: "CP는 사전이다"

ConstantPool은 `.class` 파일 안에 들어있는, **그 클래스가 참조하는 모든 외부 이름·문자열·숫자의 사전**. javac가 컴파일 시점에 만들어 박아두고, 클래스 안의 모든 bytecode가 이 사전의 **인덱스 번호로 외부 참조를 가리킨다**.

##### 2단계 — 무엇이 들어있나: "참조될 만한 건 다 있다"

CP 항목은 첫 바이트의 **tag**로 종류 구분:

| Tag | 종류 | 예 |
|---|---|---|
| 1 | Utf8 | `"println"`, `"(Ljava/lang/String;)V"` (실제 문자열 데이터) |
| 3/4/5/6 | Integer/Float/Long/Double | 숫자 상수 |
| 7 | Class | `"java/io/PrintStream"` |
| 8 | String | String 리터럴 |
| 9/10/11 | Fieldref/Methodref/InterfaceMethodref | (class_index, name_and_type_index) 쌍 |
| 12 | NameAndType | (name_index, descriptor_index) 쌍 |
| 15/16/17/18 | MethodHandle/MethodType/Dynamic/InvokeDynamic | JDK 7/11+ |
| 19/20 | Module/Package | JDK 9+ |

Methodref 같은 복합 항목은 **다른 CP 항목들을 가리키는 인덱스 쌍**으로 표현 → Methodref → (Class CP 항목, NameAndType CP 항목) → 그 안에서 또 Utf8들로 분해. **정규화된 사전 그래프**.

##### 3단계 — 어떻게 쓰이나: "bytecode는 CP 인덱스로 말한다"

```java
System.out.println("hello");
```
컴파일된 bytecode (개략):
```
ldc            #5    ← "CP[5]를 stack에 push"  → CP[5] = String "hello"
getstatic      #2    ← "CP[2]가 가리키는 static 필드" → System.out
invokevirtual  #4    ← "CP[4]가 가리키는 메서드 호출" → PrintStream.println
```

CP 안의 항목들이 서로 가리키며 펼쳐진 구조:
```
CP[2] = Fieldref     → (Class CP[3], NameAndType CP[7])
CP[3] = Class        → Utf8 CP[8]  "java/lang/System"
CP[4] = Methodref    → (Class CP[9], NameAndType CP[10])
CP[5] = String       → Utf8 CP[11] "hello"
CP[7] = NameAndType  → (Utf8 CP[12] "out", Utf8 CP[13] "Ljava/io/PrintStream;")
CP[9] = Class        → Utf8 CP[14] "java/io/PrintStream"
CP[10]= NameAndType  → (Utf8 CP[15] "println", Utf8 CP[16] "(Ljava/lang/String;)V")
```

핵심: bytecode 안에 `"java/lang/System"`이라는 문자열이 직접 박혀 있지 않다. **모든 외부 참조는 CP 인덱스를 통한 간접 참조**.

##### 4단계 — ★ Linking의 어느 단계에서 연결되나: Resolution ★

이게 면접 답변의 핵심:

```
javac 시점: CP[4] = Methodref → 그저 "PrintStream.println:(String)V"라는
                                 ★ 심볼릭 참조 ★ (문자열 기반)
                              │
                              ▼  ★ Resolution 단계 ★
                  1. owner class "java/io/PrintStream" resolve
                     → ClassLoader가 로드 → InstanceKlass*
                  2. 그 클래스에서 (이름="println", descriptor="(String)V") 검색
                     → invokevirtual의 검색 규칙(class + super class + super interface)
                  3. 결과를 Method* 포인터로 변환
                  4. CP 슬롯에 그 직접 참조를 ★ 캐싱 ★ (resolved_methodref_at)
                              │
                              ▼
다음 같은 호출부터: CP[4]에서 직접 Method* 포인터를 꺼냄. 검색 생략.
```

한 문장 정리:
> **"CP는 javac가 만들어둔 심볼릭 참조의 그릇이고, Resolution이 그 그릇을 직접 참조(`Klass*`, `Method*`, `Field*`)로 채워가는 작업을 한다. HotSpot은 lazy — 그 참조가 처음 사용될 때만 — 수행하고 결과를 CP 슬롯에 캐싱한다."**

각 instruction이 어느 CP 항목을 트리거하는지:

| Instruction | 트리거되는 CP 항목 | Resolution 결과 |
|---|---|---|
| `getstatic`/`putstatic` | Fieldref | static field offset |
| `getfield`/`putfield` | Fieldref | instance field offset |
| `invokevirtual`/`invokespecial`/`invokestatic` | Methodref | Method* + vtable index |
| `invokeinterface` | InterfaceMethodref | Method* + itable lookup info |
| `new` | Class | InstanceKlass* |
| `checkcast`/`instanceof` | Class | InstanceKlass* |
| `ldc` of CONSTANT_Class | Class | InstanceKlass* 또는 java.lang.Class oop |

##### 5단계 — 왜 굳이 이런 구조인가: 세 가지 이유

1. **압축**: 같은 메서드 이름·시그니처가 한 클래스 안에서 수십 번 나와도 CP에 한 번만 저장하고 모두 인덱스를 참조 → `.class` 파일 크기 절약.
2. **중앙 치환점**: 모든 외부 참조가 CP 한 곳에 모여 있어 Resolution이 **CP 슬롯 단위로 캐시**를 갱신 가능. bytecode에 문자열이 흩어져 있었다면 매 호출마다 검색해야 했을 것.
3. **lazy linking 가능**: javac가 만든 시점엔 참조 대상 클래스가 존재하지 않아도 됨 — 심볼릭 참조니까. 런타임에 그 참조를 처음 사용할 때만 클래스 로드·검색 수행. **자바의 dynamic loading이 이 구조 덕에 가능**.

##### + Verification과의 경계도 같이 말하면 100점

- Verification(Linking 첫 단계)은 CP의 **형식**만 본다:
  - tag가 유효한 종류인지(Pass 1)
  - 인덱스가 범위 안인지(Pass 1)
  - bytecode가 CP 항목을 타입 맞게 참조하는지(Pass 3, 예: `getstatic`은 반드시 Fieldref를 가리켜야 함)
- **그 심볼이 진짜 가리키는 클래스·메서드가 존재하는지는 Resolution의 일**.
- 그래서 "심볼릭 참조 검증"을 verification으로 묶으면 JVMS 단계 구분과 안 맞는다.

> 출처: `01-class-lifecycle/01-classfile-format.md`, `03-linking.md`

</details>

<details>
<summary>면접용 30~60초 압축 버전 (외워서 말하기 좋게)</summary>

> "ConstantPool은 .class 안에 박혀 있는 그 클래스의 참조 사전입니다. bytecode는 외부 클래스·메서드·필드를 직접 문자열로 박지 않고 CP의 인덱스로 가리킵니다 — 예를 들어 `invokevirtual #4`는 'CP의 4번이 가리키는 메서드를 호출'이라는 뜻이죠.
>
> javac가 만들어둔 시점엔 CP의 각 항목은 그냥 'PrintStream.println:(String)V' 같은 문자열 기반 심볼릭 참조입니다. **Linking의 Resolution 단계**가 그 심볼릭 참조를 실제 `Method*`·`Klass*` 같은 직접 포인터로 변환해서 같은 CP 슬롯에 캐싱합니다. HotSpot은 이걸 lazy하게 — 그 참조가 처음 사용될 때만 — 수행하기 때문에, 시작은 빠르고 자주 호출되는 곳만 점점 직접 참조로 굳어집니다.
>
> Verification은 CP의 형식과 인덱스 범위까지만 검사하고, 실제 그 심볼이 존재하는지는 Resolution이 봅니다. 그래서 CP는 단순한 '상수 저장소'라기보다 **Resolution이 일하는 작업 테이블**로 보는 게 정확합니다."

</details>

##### 🪝 Q1-1-1-1. 🟡 Pass 1의 "CP 인덱스가 범위 안 (1 ~ count-1)" 검사가 정확히 뭘 보는가?

<details>
<summary>답</summary>

CP 항목은 자주 다른 CP 항목을 가리킨다(`CONSTANT_String → #6` 식). 그 가리키는 번호가 사전 길이 안인지 검사.
- 인덱스 0은 예약(사용 금지).
- 유효 범위는 1 ~ `constant_pool_count-1`.
- 함정: tag 5(Long), 6(Double)은 **CP 슬롯 2개** 차지 → 다음 유효 인덱스는 +2.
- 범위 밖 인덱스면 `ClassFormatError`.

> 출처: `03-linking.md`(Pass 1 토글)

</details>

### Q1-2. 🟢 ClassLoader 부모 위임 모델이 보장하는 두 가지는?

<details>
<summary>답</summary>

1. **보안(Class spoofing 방지)**: 공격자가 `java.lang.String`이라는 가짜를 classpath에 심어도, AppCL이 먼저 Bootstrap에 위임 → Bootstrap이 진짜 String 로드 → 가짜 무시.
2. **유일성(Type identity)**: JVM은 클래스를 `(이름, 정의한 ClassLoader)` 쌍으로 식별. 부모 위임이 같은 클래스를 여러 CL이 정의하는 걸 막아 type identity 유지.

> 출처: `01-class-lifecycle/02-classloader-hierarchy.md`

</details>

#### 🪝 Q1-2-1. 🟡 일반 Spring Boot 앱(`java -jar app.jar`)에서 만들어지는 CL을 위→아래로 그려라.

<details>
<summary>답</summary>

```
Bootstrap CL        (C++, java.base의 java.lang.* 등)
   ↑
Platform CL         (java.sql, java.xml, java.naming 등 JDK 표준 비핵심)
   ↑
Application CL      (fat jar 자체. org/springframework/boot/loader/* 만 봄)
   ↑
LaunchedURLClassLoader  ← Spring Boot가 만든 자식 CL.
                          BOOT-INF/classes(내 코드) + BOOT-INF/lib/*.jar(의존성) 봄.
```

핵심:
- Spring·Hibernate·Jackson·내 코드 → 전부 **LaunchedURLClassLoader**가 로드.
- `java.sql.Driver`(인터페이스) → Platform CL이 로드. `com.mysql.cj.jdbc.Driver`(구현) → LaunchedURLClassLoader. 이 비대칭이 TCCL 문제의 출발점.
- IDE/`mvn spring-boot:run`은 `LaunchedURLClassLoader` 안 만듦 — fat jar 풀 일이 없어 AppCL이 다 로드.

> 출처: `02-classloader-hierarchy.md`(Spring Boot 부팅·로딩 전체 흐름 섹션)

</details>

##### 🪝 Q1-2-1-1. 🟡 Spring Boot DevTools가 켜지면 CL이 어떻게 늘어나고 무슨 부작용이 있는가?

<details>
<summary>답</summary>

```
... → AppCL → Base CL          (변경 거의 안 됨: Spring/Hibernate/Jackson)
              → Restart CL     (자주 바뀜: 내 코드. 매 재시작마다 새 인스턴스)
```

코드 저장 → DevTools가 RestartCL만 버리고 새로 만듦 → Base는 살아남음 → 재시작 빠름.

부작용:
- **ClassCastException "X cannot be cast to X"**: Base CL의 캐시(예: Caffeine static)에 옛 RestartCL의 인스턴스가 들어가 있고, 새 RestartCL로 다시 꺼낼 때 같은 FQCN인데 CL이 다른 두 Class → 캐스트 실패.
- **Metaspace 누수**: 옛 RestartCL이 어딘가(ThreadLocal, JDBC `DriverManager.registeredDrivers`)에 참조돼 GC 안 됨 → 재시작 누적 → `OutOfMemoryError: Metaspace`.

> 출처: `02-classloader-hierarchy.md`(DevTools 섹션 + 실전 에러 8종)

</details>

###### 🪝 Q1-2-1-1-1. 🔴 DevTools 환경의 JDBC Driver 누수를 코드로 어떻게 막는가?

<details>
<summary>답</summary>

종료 시점에 내 CL이 등록한 Driver를 직접 deregister:

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

원리: `DriverManager.registeredDrivers`(Platform CL의 static 리스트)가 RestartCL의 Driver 참조를 들고 있으면, RestartCL 전체가 GC root에 잡혀 unload 못 함. 명시적으로 끊어줘야 한다.

> 출처: `02-classloader-hierarchy.md`(꼬리 Q3-1-1)

</details>

### Q1-3. 🟡 Linking의 3단계 Verification·Preparation·Resolution을 설명하고, 각 단계가 일으키는 대표 에러는?

<details>
<summary>답</summary>

| 단계 | 무엇 | 대표 에러 |
|---|---|---|
| Verification | bytecode 타입 안전성 증명 (Pass 1 구조 / Pass 2 의미 / Pass 3 bytecode) | `ClassFormatError`, `VerifyError` |
| Preparation | static 필드에 default 값(0/null/false) 할당. **사용자 코드 실행 X** | (사실상 없음) |
| Resolution | 심볼릭 참조(`"java/lang/System.out"`) → 직접 참조(`Klass*`/`Method*`)로 변환. HotSpot은 lazy | `NoClassDefFoundError`, `NoSuchFieldError`, `NoSuchMethodError`, `IllegalAccessError`, `IncompatibleClassChangeError`, `AbstractMethodError` |

주의: "심볼릭 참조 검증"은 verification이 아니라 **Resolution 단계의 일**. 옛 교재의 "Pass 4: Symbolic Reference Verification" 표현은 JVMS의 단계 구분과 안 맞는다.

> 출처: `03-linking.md`

</details>

#### 🪝 Q1-3-1. 🟡 invoke* 4종(static/special/virtual/interface)의 resolution 규칙 차이는?

<details>
<summary>답</summary>

| opcode | 검색 | dispatch |
|---|---|---|
| `invokestatic` | owner class + super interfaces. 못 찾으면 `IncompatibleClassChangeError` | static binding (컴파일 시 확정) |
| `invokespecial` | `<init>`, `super.x()`, private. owner 또는 직계 super부터 위로 | static binding |
| `invokevirtual` | owner class + super class 사슬, 그래도 없으면 super interfaces의 가장 구체적 non-abstract 메서드 | **dynamic dispatch** (런타임 실제 객체로 vtable lookup) |
| `invokeinterface` | owner는 interface. interface + super interfaces + `Object`의 public 메서드 | **dynamic dispatch** (itable lookup) |

핵심: `invokestatic`/`invokespecial`은 검색 결과 = 실행할 메서드. `invokevirtual`/`invokeinterface`는 "어떤 시그니처"만 결정하고 **실제 어느 구현이 실행될지는 런타임에 결정**.

> 출처: `03-linking.md`(Method resolution opcode별 표)

</details>

##### 🪝 Q1-3-1-1. 🟡 그럼 vtable과 itable은 정확히 뭔가?

<details>
<summary>답</summary>

- **vtable** = 한 클래스의 인스턴스에서 dynamic dispatch될 수 있는 **메서드 함수 포인터 배열**. 부모-자식이 **같은 시그니처를 같은 인덱스**에 둔다. override 시 자식이 같은 인덱스를 자기 포인터로 덮어씀. invokevirtual은 인덱스 한 번으로 O(1).
- **itable** = 인터페이스 전용. `(interface, method) → 함수 포인터` 매핑. 한 클래스가 여러 인터페이스를 implement해도 충돌 안 나게 인터페이스마다 구역을 따로 둔다. invokeinterface는 인터페이스 구역 찾는 한 단계가 더 듦.
- 실전 속도 비슷한 이유: JIT의 **inline cache**가 호출 사이트마다 "최근 dispatch 결과"를 캐싱해 monomorphic/bimorphic이면 vtable과 동일 속도. **megamorphic(3+ 타입)** 이면 캐시 포기 + 인라인 실패 → 성능 급락.

> 출처: `03-linking.md`(vtable/itable 섹션)

</details>

###### 🪝 Q1-3-1-1-1. 🔴 megamorphic call이 hot path에 있을 때 어떻게 진단하나?

<details>
<summary>답</summary>

`-XX:+PrintInlining` 추가 후 로그에서 `callee is megamorphic, inlining cancelled` 또는 `not inlineable` 메시지가 찍힌 콜 사이트를 찾는다. JFR의 `MethodProfilingSample`도 동일 정보 제공.

대응:
1. hot path를 한 구현으로 좁힌다 (인터페이스 → 구체 클래스 변수).
2. JIT가 다양성을 학습 못 하게 분기 전 type check 명시.
3. 너무 다형인 캐시·디스패치 테이블이 hot path에 있으면 design 재검토.

> 출처: `03-execution-engine/05-inlining-and-ic.md`

</details>

### Q1-4. 🟢 클래스가 unload되려면 무엇이 GC 가능해야 하는가?

<details>
<summary>답</summary>

다음이 모두 unreachable이어야 ClassLoader → 그 안의 모든 Class → 모든 InstanceKlass → Metaspace chunk가 통째로 해제:
1. ClassLoader 객체 자체.
2. 그 CL이 로드한 클래스의 모든 인스턴스.
3. 그 CL이 로드한 모든 Class 객체.
4. 다른 CL이 그 클래스를 참조하지 않음.

한 가지라도 도달 가능하면 누수.

> 출처: `04-initialization-and-unload.md`, `02-classloader-hierarchy.md`(꼬리 Q5)

</details>

---

## Ch 02. Runtime Data Areas (`02-runtime-data-areas/`)

### Q2-1. 🟢 JVM 메모리 영역 6개를 그리고 각 영역의 공유 범위·GC 여부를 말해라.

<details>
<summary>답</summary>

| 영역 | 공유 범위 | GC 대상? | 무엇 |
|---|---|---|---|
| **Heap** | thread 공유 | ★ Yes | 객체 인스턴스, 배열 |
| **Metaspace** (+Class Space) | thread 공유 | (CL 단위로 unload) | Klass, Method, ConstantPool 등 클래스 메타데이터 |
| **Stack** | per-thread | No (스레드 종료 시 해제) | Stack Frame(메서드 호출당 1개): 지역 변수, operand stack, return address |
| **PC Register** | per-thread | No | 현재 실행 중인 bytecode 위치 |
| **Native Method Stack** | per-thread | No | JNI 호출용 |
| **Code Cache** | thread 공유 | (JIT가 관리) | JIT가 생성한 native 코드 |

추가: **Direct Memory** (NIO ByteBuffer.allocateDirect), **GC Bookkeeping**(Card Table, Remembered Set 등).

> 출처: `02-runtime-data-areas/README.md`, 각 하위 챕터

</details>

#### 🪝 Q2-1-1. 🟢 Heap이 더 잘게 쪼개진다고 들었다. Young/Old, Eden/Survivor가 뭐고 왜 나누나?

<details>
<summary>답</summary>

**Generational hypothesis**: 대부분 객체는 짧게 살고 죽는다. 오래 살아남은 객체는 앞으로도 오래 살 확률이 높다.

→ Heap을 세대(generation)로 나눠 각자에 맞는 GC를 적용:

```
Young Gen
   ├── Eden         ← 새 객체 할당 위치
   ├── Survivor 0   ┐
   └── Survivor 1   ┘ Minor GC 시 살아남으면 옮기는 두 공간 (copy)
Old Gen              ← Survivor에서 N번 살아남으면 promote
```

Minor GC: Young만 → 짧고 자주.
Major/Full GC: Old 포함 → 길고 드물게.

이 분리 덕에 "짧은 객체는 빨리 회수, 오래 사는 객체는 자주 안 보기" 전략이 성립.

> 출처: `02-runtime-data-areas/01-heap-and-tlab.md`, `04-gc/02-generational-and-serial-parallel.md`

</details>

##### 🪝 Q2-1-1-1. 🟡 TLAB이 뭐고 왜 필요한가?

<details>
<summary>답</summary>

**TLAB = Thread-Local Allocation Buffer**. 각 스레드가 Eden의 일부를 자기 전용 버퍼로 받아두고, 그 안에서만 객체를 할당하는 영역.

왜 필요:
- Heap 할당이 공유라면 매 `new`마다 lock/CAS 필요 → 컨테션 폭발.
- TLAB은 스레드 전용이라 **pointer bump 한 줄로 할당 끝** → fast path가 거의 무료.
- 가득 차면 그 스레드가 새 TLAB을 받음(이 단계만 짧게 동기화).

운영 신호: `-XX:+PrintTLAB`로 refill 빈도·낭비율 관찰. 큰 객체가 TLAB을 넘어가면 slow path로 빠짐.

> 출처: `02-runtime-data-areas/01-heap-and-tlab.md`

</details>

### Q2-2. 🟡 Metaspace는 PermGen과 뭐가 다르고 왜 바뀌었나?

<details>
<summary>답</summary>

| 항목 | PermGen (JDK 7-) | Metaspace (JDK 8+) |
|---|---|---|
| 위치 | Heap 안의 고정 영역 | Heap 밖, **native 메모리** |
| 크기 | 고정 (`-XX:MaxPermSize`) | 기본 unlimited, `-XX:MaxMetaspaceSize`로 제한 |
| 단위 | 전체 PermGen 한 덩어리 | **ClassLoaderData 단위 chunk** |
| 회수 | Full GC 시에만 | CL이 GC되면 그 CLD chunk 통째로 |

바뀐 이유:
- PermGen 고정 크기는 동적 클래스 생성(Spring AOP, Groovy, JVM 언어들)에서 자주 `OutOfMemoryError: PermGen`.
- 동적 클래스 누수 = 고정 크기 빨리 채움.
- Metaspace는 native 메모리 + CL 단위 회수라 누수가 한 CL에 국한되고, 그 CL이 GC되면 깔끔히 회수됨.

> 출처: `02-runtime-data-areas/02-metaspace-and-class-space.md`

</details>

#### 🪝 Q2-2-1. 🟡 Compressed Class Space는 또 뭔가?

<details>
<summary>답</summary>

64비트 JVM에서 `Klass*` 포인터를 8바이트로 두면 메타데이터 메모리가 커진다. Compressed Class Space는 별도 native 영역에 Klass들을 두고 **32비트 오프셋으로 가리키는 압축 포인터** 사용 → 메모리 절약.

- 기본 1GB(`-XX:CompressedClassSpaceSize`).
- Metaspace 안의 일부가 아니라 **별도 영역**. NMT에서도 별도 표기.
- `-XX:-UseCompressedClassPointers`로 끄면 다시 64비트 포인터.

> 출처: `02-runtime-data-areas/02-metaspace-and-class-space.md`

</details>

### Q2-3. 🟡 Code Cache는 뭐고 가득 차면 어떤 일이 일어나는가?

<details>
<summary>답</summary>

JIT가 생성한 native 코드를 두는 영역. 기본 240MB.

가득 차면:
1. JIT 컴파일 중단 → 새 메서드는 **인터프리터로만** 실행 → 성능 급락.
2. `CodeCache is full. Compiler has been disabled.` 경고.
3. 회피책: `-XX:ReservedCodeCacheSize=512m` 등으로 늘리거나, 사용 안 되는 코드 회수 활성화(`-XX:+UseCodeCacheFlushing`, 기본 on).

운영: JFR/JMX의 `MemoryPoolMXBean(name="CodeCache")`로 사용량 모니터링.

> 출처: `02-runtime-data-areas/04-code-cache.md`

</details>

### Q2-4. 🟡 Direct Memory는 Heap에 안 잡히는데 어떻게 회수되나? 누수가 잘 나는 이유는?

<details>
<summary>답</summary>

`ByteBuffer.allocateDirect(N)` 같은 호출은 native 메모리(OS의 malloc 영역)에 N바이트를 받아온다. Java 객체는 그 native 영역을 가리키는 **얇은 wrapper** 일뿐.

회수 경로:
1. wrapper 객체가 GC됨.
2. 거기 붙은 `Cleaner` 또는 `PhantomReference`가 처리 큐에 들어감.
3. Reference Handler 스레드가 native free 호출.

누수가 잘 나는 이유:
- wrapper가 작아서 GC가 자주 안 일어남 → 큰 native 메모리는 살아남음.
- wrapper에 강한 참조(`static` 컬렉션 등)가 있으면 영원히 해제 안 됨.
- `-XX:MaxDirectMemorySize`로 상한 설정 안 하면 OS RSS 폭발.

운영 신호: container RSS는 늘어나는데 Heap은 평온. NMT(Native Memory Tracking)로 `Other`/`Direct` 영역 확인.

> 출처: `02-runtime-data-areas/05-direct-memory.md`

</details>

---

## Ch 03. Execution Engine (`03-execution-engine/`)

### Q3-1. 🟢 자바 바이트코드는 CPU가 직접 실행하나?

<details>
<summary>답</summary>

**아니다.** 바이트코드는 **JVM이라는 가상 머신**의 명령어. 물리 CPU(x86/ARM)는 못 알아듣는다.

물리 CPU까지 가는 두 경로:
1. **Interpreter**: JVM이 opcode 하나씩 읽고 해당 C++ 핸들러를 실행 → 그 C++가 이미 CPU 명령으로 컴파일돼 있어 결과적으로 CPU가 실행. HotSpot은 Template Interpreter(opcode별 어셈블리 조각 + jump table).
2. **JIT**: 자주 도는 hot 메서드를 통째로 native 어셈블리로 번역해 Code Cache에 적재 → 이후 그 native 코드 직접 실행.

HotSpot은 두 경로를 동시에 갖는 **mixed mode**. 처음 인터프리터로 시작 → hot은 JIT로 옮김.

> 출처: `03-execution-engine/01-execution-overview.md`, `02-template-interpreter.md`, `03-linking.md`(opcode 토글)

</details>

#### 🪝 Q3-1-1. 🟡 Tiered Compilation의 5단계(Level 0~4)를 설명하라.

<details>
<summary>답</summary>

| Level | 누가 | 특징 |
|---|---|---|
| 0 | Interpreter | Template Interpreter. 프로파일링 정보 수집. |
| 1 | C1 | 최소 최적화, **프로파일링 안 함**. 트리비얼 메서드용. |
| 2 | C1 | 가벼운 최적화 + **invocation/backedge counter만** 프로파일링. |
| 3 | C1 | 완전 프로파일링(branch taken%, type profile). 대부분의 메서드가 여기로. |
| 4 | C2 | 풀 최적화 (인라이닝, 이스케이프 분석, 루프 unroll, SIMD). Level 3의 프로파일 데이터를 입력으로. |

흐름: 0 → 3 → 4. 1·2는 C2 큐가 가득 찼을 때의 백업 경로.

> 출처: `03-execution-engine/03-tiered-compilation.md`

</details>

##### 🪝 Q3-1-1-1. 🟡 C1과 C2의 본질적 차이는?

<details>
<summary>답</summary>

- **C1 (Client Compiler)**: 짧은 컴파일 시간, 단순 최적화. 결과 코드 품질은 중간. **빠르게 native로 가는 것**이 목적.
- **C2 (Server Compiler)**: 긴 컴파일 시간, **공격적 최적화**. 인라이닝·EA·loop unroll·SIMD·deoptimization. C1의 5~10배 시간 들지만 결과는 훨씬 빠름.

C1은 IR로 HIR(High-level IR)·LIR(Low-level IR)을 짧게 거침. C2는 **Sea-of-Nodes** 그래프 기반으로 전역 최적화.

> 출처: `03-execution-engine/04-c1-and-c2.md`

</details>

###### 🪝 Q3-1-1-1-1. 🔴 GraalVM JIT은 C2를 어떻게 대체하나?

<details>
<summary>답</summary>

GraalVM의 Graal Compiler는 **Java로 작성된 JIT**. C2와 같은 자리(Level 4)에 끼우는 형태:
- `-XX:+UseJVMCICompiler` 또는 GraalVM 배포본 사용 시 Graal이 C2 대체.
- 장점: Java로 짜서 유지보수 쉬움, partial escape analysis, 더 공격적 인라이닝.
- 단점: 시작은 느림(자기도 JIT 대상이니 워밍업 필요). 일부 워크로드는 C2가 여전히 빠름.

같은 GraalVM이라도 **Native Image는 다른 길** — AOT로 컴파일해 JIT 자체를 빼버림.

> 출처: `08-graalvm/README.md`

</details>

### Q3-2. 🟡 Escape Analysis(EA)가 뭐고 어떤 최적화를 활성화하나?

<details>
<summary>답</summary>

**EA**: 메서드 안에서 생성된 객체의 참조가 그 메서드 바깥으로 "탈출(escape)" 하는지 분석.

세 가지 결론:
1. **NoEscape**: 메서드 안에서만 살고 사라짐 → **Scalar Replacement**(객체를 만들지 않고 필드를 레지스터로 분해), **Lock Elision**(synchronized 자체 제거).
2. **ArgEscape**: 다른 메서드에 인자로 전달 → 일부 최적화 가능.
3. **GlobalEscape**: heap에 저장되거나 다른 스레드로 빠짐 → 최적화 못 함.

운영 효과: 짧은 라이프사이클의 임시 객체(`Optional`, 작은 wrapper 등)가 사실상 **할당 0**이 된다. allocation rate 그래프가 EA 활성/비활성에 따라 크게 달라짐.

> 출처: `03-execution-engine/06-escape-analysis.md`

</details>

#### 🪝 Q3-2-1. 🟡 Deoptimization은 언제 일어나고, 일어나면 어떻게 되나?

<details>
<summary>답</summary>

JIT가 **speculative optimization**(예: "이 메서드는 늘 ArrayList만 받는다고 가정")을 했는데 가정이 깨졌을 때 일어난다.

원인:
- Class hierarchy 변경(새 클래스 로드로 polymorphism 증가).
- Profile-guided 분기가 틀린 방향으로 잡힘.
- `null check` 우회가 NPE를 만남.
- Exception path 진입.

동작:
1. native 코드 실행 중단.
2. **스택 프레임을 인터프리터 프레임으로 재구성**(deopt).
3. 인터프리터로 fall back. 다시 hot해지면 재컴파일.

운영: `-XX:+PrintCompilation -XX:+TraceDeoptimization`으로 추적. P99 spike의 흔한 원인.

> 출처: `03-execution-engine/08-speculative-and-deopt.md`

</details>

### Q3-3. 🔴 Inlining이 왜 JIT 최적화의 "왕"인가?

<details>
<summary>답</summary>

인라이닝 = 호출 대상의 코드를 호출 위치에 직접 펼치기. 표면적으로는 호출 오버헤드 제거지만, 진짜 가치는 **그 다음 최적화의 문**:

- 펼친 코드에서 **상수 전파**(caller가 넘긴 상수가 callee로 흐름) → dead code elimination.
- 펼친 후 **타입이 좁아짐** → devirtualization → 또 다른 인라이닝 가능.
- **escape analysis가 넓어짐** → scalar replacement.
- **loop fusion**·**code motion**이 메서드 경계를 넘어 가능해짐.

즉 인라이닝 한 번이 그 뒤 모든 최적화의 입력 품질을 끌어올린다. 그래서 **인라인 실패 = 최적화 사슬 전체가 끊김**.

기본 한계: `-XX:MaxInlineSize=35`, `-XX:FreqInlineSize=325`. monomorphic이고 hot이면 거의 항상 인라인.

> 출처: `03-execution-engine/05-inlining-and-ic.md`

</details>

---

## Ch 04. GC (`04-gc/`)

### Q4-1. 🟢 "Reachability"가 무슨 뜻이고 GC Roots는 어디인가?

<details>
<summary>답</summary>

객체가 **GC Root에서 참조 체인을 따라 도달 가능**하면 살아 있는 것, 도달 불가면 죽은 것. 도달 불가능한 객체만 회수.

GC Roots:
- 각 스레드의 **stack frame의 local variable / operand stack**.
- **static 필드** (Class 객체가 가진 영역).
- **JNI local / global handle**.
- **synchronized monitor**로 잡힌 객체.
- 일부 시스템 클래스(`Thread`, `ClassLoader`, primitives의 박싱 캐시).

이 집합에서 시작해 BFS/DFS로 표시하는 게 GC의 mark 단계.

> 출처: `04-gc/01-gc-fundamentals.md`

</details>

#### 🪝 Q4-1-1. 🟡 Card Table과 Remembered Set은 뭐고 왜 필요한가?

<details>
<summary>답</summary>

Minor GC는 Young만 본다. 그런데 **Old → Young 참조**가 있으면 Young의 살아있는 객체를 GC가 모를 수 있다. 그렇다고 Minor GC마다 Old 전체를 스캔하면 Minor의 의미가 사라짐.

해결:
- **Card Table** (Serial/Parallel/CMS/G1 일부): Heap을 512바이트 카드로 나눠, 카드 안에 cross-gen 참조가 있을 수 있으면 그 카드만 dirty 표시. Minor GC는 dirty 카드만 스캔.
- **Remembered Set** (G1): 각 region이 "나를 가리키는 region들"의 카드 정보를 들고 있음 → 그 region을 GC할 때 그 카드만 보면 됨.

운영: write barrier가 Card Table을 갱신하므로 약간의 런타임 오버헤드를 늘 낸다 — 이게 GC가 단순한 mark-sweep을 못 쓰는 본질적 비용.

> 출처: `04-gc/01-gc-fundamentals.md`, `04-gc/03-cms-and-g1.md`

</details>

### Q4-2. 🟡 G1 GC의 동작을 한 그림으로 설명하라.

<details>
<summary>답</summary>

```
Heap = 1~2MB region 수천 개
       각 region에 라벨: Eden / Survivor / Old / Humongous

[1] Concurrent Marking (백그라운드)
    GC Roots부터 시작 → 살아있는 객체 표시. 앱과 동시에.

[2] Young GC (STW, 짧음)
    Eden + Survivor region을 골라 살아있는 객체를 다른 region으로 evacuate.
    evacuate 후 옛 region은 통째로 free.

[3] Mixed GC (STW, Young + 일부 Old region)
    Concurrent marking이 발견한 "garbage 비율 높은 Old region"을 골라 같이 evacuate.
    → Full GC 회피.

목표: -XX:MaxGCPauseMillis (기본 200ms) 안에 끝낼 만큼만 region을 고름.
```

핵심: G1은 **region 단위 evacuation + concurrent marking + pause budget 기반 region 선택**의 조합. "Garbage First"라는 이름은 garbage 비율 높은 region을 우선 회수한다는 뜻.

> 출처: `04-gc/03-cms-and-g1.md`

</details>

#### 🪝 Q4-2-1. 🟡 ZGC는 G1과 무엇이 본질적으로 다른가?

<details>
<summary>답</summary>

ZGC의 차별점:
1. **모든 phase가 concurrent**: marking·relocation·remapping을 앱과 동시에. STW는 **root scan 단계만**(보통 < 1ms).
2. **Colored Pointer**: 64비트 포인터의 상위 bits에 GC 상태(marked, remapped 등)를 박아 **load barrier**로 처리. 객체에 mark bit 따로 안 둠.
3. **Region 크기 가변**: small/medium/large region.

결과: P99 STW를 ms 미만으로 둘 수 있다(대형 heap에서도). 단, throughput은 단일세대 ZGC가 G1 대비 10~15% 낮을 수 있음 → **Generational ZGC**(JDK 21+)가 이 격차를 거의 좁혔다.

> 출처: `04-gc/04-zgc-and-shenandoah.md`, `04-gc/05-generational-zgc.md`

</details>

##### 🪝 Q4-2-1-1. 🔴 G1 vs ZGC vs Generational ZGC 선택 기준은?

<details>
<summary>답</summary>

| Heap / 목표 | 추천 |
|---|---|
| Heap < 32GB, P99 < 200ms 허용 | **G1** (안정, 운영 도구 성숙) |
| Heap 32~128GB, P99 < 10ms 목표 | **ZGC** 또는 **Generational ZGC** |
| Heap > 128GB | **Generational ZGC** (JDK 21+) |
| Throughput 최우선 (배치 잡 등) | Parallel GC 또는 G1 |
| Tail latency 최우선 (트레이딩, 광고 입찰) | ZGC/Shenandoah |

JDK 21+의 Generational ZGC가 거의 모든 면에서 G1을 따라잡아 차세대 default 후보. 다만 운영 도구·경험치는 G1이 여전히 두텁다.

> 출처: `04-gc/06-gc-tuning-and-ops.md`, `12-tradeoff-master-table/README.md`

</details>

### Q4-3. 🔴 Production에서 OOM이 났다. 진단 절차 전체를 말하라.

<details>
<summary>답</summary>

1. **Heap dump 확보**: `-XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/var/dumps`(사전 필수). 사후라면 `jcmd <pid> GC.heap_dump`.
2. **MAT(Eclipse Memory Analyzer) 분석**:
   - Leak Suspects 리포트로 1차 가설.
   - Dominator Tree로 큰 객체 식별.
   - Path to GC Roots로 누가 잡고 있는지.
3. **5대 누수 패턴 점검**:
   - static 컬렉션 무한 추가, ThreadLocal 미해제, Listener 미해제, 만료 정책 없는 Cache, JDBC Driver 등록 해제 누락.
4. **OOM 종류 확인**:
   - `Java heap space` → Heap 누수.
   - `Metaspace` → ClassLoader 누수(특히 DevTools, 동적 클래스 생성).
   - `Direct buffer memory` → NIO/Netty.
   - `unable to create new native thread` → 스레드 풀 폭주.
5. **사후 보강**: GC log·JFR continuous·NMT 활성화, Old gen 80% 알람.

> 출처: `04-gc/06-gc-tuning-and-ops.md`, `10-ops-scenarios/00-real-world-cases.md`

</details>

---

## Ch 05. Threading (`05-threading/`)

### Q5-1. 🟢 JMM(Java Memory Model)이 보장하는 게 무엇이고, 왜 필요한가?

<details>
<summary>답</summary>

JMM은 **"하나의 스레드가 쓴 값을 다른 스레드가 언제 볼 수 있는지"** 를 정의하는 규칙. 

왜 필요:
- 현대 CPU는 캐시·write buffer·OoO(out-of-order) 실행으로 메모리 쓰기 순서가 코드 순서와 다르다.
- 컴파일러/JIT도 명령어 reorder를 한다.
- 명시적 동기화 없이는 한 스레드의 쓰기가 다른 스레드에 영영 안 보일 수도 있다.

JMM은 그 가시성·순서 보장을 **happens-before 관계**로 정의:
- `volatile` 쓰기는 그 뒤의 같은 변수 읽기보다 happens-before.
- `synchronized` unlock은 같은 monitor의 다음 lock보다 happens-before.
- `Thread.start()` 이후 코드는 새 스레드의 첫 실행보다 happens-before.

> 출처: `05-threading/01-jmm-and-happens-before.md`

</details>

#### 🪝 Q5-1-1. 🟡 `synchronized`와 `volatile`의 차이는?

<details>
<summary>답</summary>

| 항목 | volatile | synchronized |
|---|---|---|
| 가시성 | ✅ | ✅ |
| atomicity | ❌ (단일 read/write만) | ✅ |
| mutual exclusion | ❌ | ✅ |
| 비용 | 가벼움 | 무거움 (monitor enter/exit) |

쓰임:
- 단순 flag, "한 번 쓰고 여러 번 읽음": volatile.
- 복합 mutate(`count++`, "if-then" 패턴): synchronized 또는 `AtomicXxx`.

`count++`는 read-modify-write → volatile만으로는 race condition. AtomicInteger의 `incrementAndGet`가 정답.

> 출처: `05-threading/01-jmm-and-happens-before.md`, `02-memory-barriers.md`

</details>

##### 🪝 Q5-1-1-1. 🟡 Mark Word는 뭐고 lock 단계 변화를 설명하라.

<details>
<summary>답</summary>

객체 헤더의 8바이트 영역. 최근 hashCode·age·**lock 상태**·forwarding pointer를 비트로 packing.

Lock 상태 진화(경합 없을 때부터 늘어남):
1. **Biased Lock**(JDK 15에서 deprecated, 17에서 제거 진행): "한 스레드만 lock한다"고 가정 → Mark Word에 그 스레드 ID만 적어두고 CAS도 생략.
2. **Lightweight Lock**: 짧은 경합 → CAS로 Mark Word를 자기 스택 프레임 주소로 바꿈.
3. **Heavyweight Lock**: 경합 지속 → OS 수준 monitor 객체(ObjectMonitor)를 만들어 wait 큐 운영.

이 단계가 자동으로 inflation 됨. 짧은 critical section은 거의 lightweight에서 끝나서 synchronized가 생각보다 가볍다.

> 출처: `05-threading/03-synchronized-and-mark-word.md`

</details>

### Q5-2. 🔴 Virtual Thread(JEP 444, JDK 21)가 어떻게 동작하는가?

<details>
<summary>답</summary>

**VT = JVM이 스케줄링하는 경량 스레드**. OS 스레드 1개에 수천 개의 VT를 swap-in/out.

- **Carrier Thread**: 실제 OS 스레드(ForkJoinPool의 worker). VT는 여기 올라타서 실행.
- **Mount/Unmount**: VT가 blocking I/O를 만나면 unmount → carrier는 다른 VT를 mount해서 일 계속. 옛 모델에선 OS 스레드가 통째로 block됐던 자리.
- **Continuation**: VT의 실행 상태(stack frame)는 Heap에 객체로 저장 → unmount/remount 시 swap.

장점:
- "Color of function" 문제 해결: sync API 그대로 수만 동시성.
- 디버깅 자연스러움(stack trace 평범).
- Reactive 복잡도 회피.

함정:
- **Pinning**: `synchronized` 안에서 blocking I/O → VT가 carrier에 박혀 unmount 못 함(JEP 491에서 해소 예정). `ReentrantLock`은 안전.
- ThreadLocal 폭증 → 메모리 증가.
- CPU-bound 작업엔 효과 없음(스레드 수 늘리는 게 의미 없음).

> 출처: `05-threading/04-virtual-threads-and-loom.md`

</details>

#### 🪝 Q5-2-1. 🔴 그럼 Reactive(Reactor, RxJava)는 더 이상 필요 없나?

<details>
<summary>답</summary>

**부분적으로 의미 약화**. "Color of function 회피"라는 동기 만든 동기가 사라짐 — VT로 sync 코드 그대로 동시성 확보 가능.

여전히 가치 있는 경우:
- **backpressure**가 본질인 스트리밍 처리(Kafka consumer → 변환 → sink).
- **operator-rich data pipeline**(map/filter/window/timeout 등 조합).
- 이미 reactive로 짜인 레거시.

새 프로젝트라면 sync + VT가 더 단순하고 디버깅 쉬움. Spring Boot 3.2+는 VT를 기본 지원(`spring.threads.virtual.enabled=true`).

> 출처: `05-threading/04-virtual-threads-and-loom.md`

</details>

---

## Ch 06-08. 버전사 · HotSpot 내부 · GraalVM

### Q6-1. 🟡 JDK 8 → 17 마이그레이션의 핵심 체크리스트는?

<details>
<summary>답</summary>

1. **JPMS 캡슐화**: `sun.misc.*` 등 내부 API 접근 차단 → `--add-opens java.base/java.lang=ALL-UNNAMED` 등으로 임시 회피, 장기적으론 제거.
2. **Java EE 모듈 제거**: `javax.xml.bind`, `javax.activation`, `javax.annotation` 등은 JDK 9에서 빠짐 → 별도 dependency(`jakarta.xml.bind-api` 등).
3. **클래스 이름 변경**: `sun.misc.Launcher$AppClassLoader` → `jdk.internal.loader.ClassLoaders$AppClassLoader`.
4. **Default GC 변경**: Parallel → G1. `-XX:+UseG1GC` 명시 또는 옵션 재검토.
5. **Strong encapsulation** (JDK 16+): reflection 접근 제한 강화 → CGLib, ByteBuddy 옛 버전 깨질 수 있음.
6. **`Unsafe` 제거 진행**: `VarHandle`로 대체 권장.
7. **단계적 canary**: 한 인스턴스부터 마이그 → JFR로 비교 → 점진 확대.

> 출처: `06-version-history/README.md`

</details>

### Q7-1. 🔴 HotSpot의 SystemDictionary가 무엇이고 어디서 등장하는가?

<details>
<summary>답</summary>

**SystemDictionary** = HotSpot 안의 **"`(이름, ClassLoader)` → `InstanceKlass*`" 매핑 자료구조**. 클래스 로딩의 사실상 캐시이자 등록부.

등장 지점:
- `ClassLoader.loadClass`가 위임을 다 돌고 결과 클래스를 만들면 → SystemDictionary에 등록.
- 두 번째 `loadClass` 호출 → 먼저 SystemDictionary에서 lookup → 있으면 그대로 반환(중복 정의 방지).
- 클래스 unloading 시 SystemDictionary에서 entry 제거 + 그 CLD의 Metaspace chunk 회수.

운영 관점: `jcmd <pid> VM.classloader_stats`로 SystemDictionary 통계 확인 가능. 한 CL이 너무 많은 클래스를 로드하면 여기서 보임.

> 출처: `07-hotspot-internals/README.md`

</details>

### Q8-1. 🔴 GraalVM Native Image의 한계는?

<details>
<summary>답</summary>

빌드 시점에 reachable한 모든 코드를 AOT 컴파일하기 때문에:
1. **런타임 reflection 제한**: 사용할 클래스/메서드를 `reflect-config.json`에 미리 등록해야 함. Spring Boot Native가 자동화하지만 third-party 라이브러리는 별도 작업 필요.
2. **동적 클래스 로딩 불가**: `URLClassLoader`로 새 jar 로드 같은 것 못 함. Plugin 시스템에 부적합.
3. **`MethodHandle.invokeExact` 같은 동적 API 제약**.
4. **빌드 시간 김**: 메서드 수십만 개를 한 번에 분석 → 5~15분.
5. **메모리 폭증** 빌드 시(빌드 머신에 8~16GB 이상).
6. **JIT 없음**: profile-guided 최적화 부재 → 일부 워크로드는 JIT 풀워밍업 후의 HotSpot보다 느림.

쓰는 자리: **부팅 시간이 critical**한 곳(serverless, CLI, sidecar). 장기 running하면서 JIT가 깊이 최적화하는 워크로드(트레이딩, 큰 웹 서버)는 HotSpot이 더 유리할 수 있음.

> 출처: `08-graalvm/README.md`

</details>

---

# 🎯 Part 2 — 레벨별 종합 면접

## 🟢 Junior 종합 5문

<details>
<summary><b>Q-J1. JVM이 뭐고 JRE/JDK와 차이는?</b></summary>

JVM = bytecode 실행 가상 머신. JRE = JVM + 표준 라이브러리. JDK = JRE + 개발 도구. JDK 9+부터 JRE 별도 배포는 종료.

</details>

<details>
<summary><b>Q-J2. Heap vs Stack 차이는?</b></summary>

Heap: thread 공유, 객체 인스턴스, GC 대상. Stack: per-thread, 메서드 호출당 1프레임(지역 변수·operand stack·return address), 스레드 종료 시 해제. GC는 stack을 직접 회수하지 않지만 stack의 변수는 **GC root**로 작동.

</details>

<details>
<summary><b>Q-J3. GC가 뭐고 왜 필요한가?</b></summary>

미사용 객체 자동 회수. C/C++의 manual free 실수(use-after-free, double free, leak) 회피. 기본 알고리즘: **Reachability** — GC Root에서 도달 불가능하면 죽음. 살아있는 객체만 표시하고 나머지를 일괄 회수.

</details>

<details>
<summary><b>Q-J4. ArrayList vs LinkedList?</b></summary>

ArrayList: 배열 기반, random access O(1), 끝 add/remove O(1) amortized. LinkedList: 노드 기반, random access O(n), 양끝 add/remove O(1). 거의 모든 경우 ArrayList가 우세(cache locality + GC 부하 적음). LinkedList는 양끝 자주 변경하는 큐/덱 외엔 거의 안 씀.

</details>

<details>
<summary><b>Q-J5. synchronized와 volatile의 차이?</b></summary>

synchronized = mutual exclusion + visibility + atomicity. volatile = visibility + happens-before, atomicity 없음. 단순 flag → volatile, 복합 mutate(count++) → synchronized 또는 AtomicXxx.

</details>

## 🟡 Senior 종합 5문

<details>
<summary><b>Q-S1. JDK 8 → 17 마이그레이션 경험은?</b></summary>

핵심: 모든 dependency 17 호환 확인 → `sun.misc.Unsafe` 사용처 제거 → Java EE 모듈 별도 dependency 추가 → strong encapsulation 우회 옵션(`--add-opens`) → default GC 변경(Parallel → G1) 옵션 재검토 → canary 배포 + JFR 메트릭 비교 + 점진 확대.

</details>

<details>
<summary><b>Q-S2. G1 vs ZGC 선택 기준?</b></summary>

Heap < 32GB · P99 200ms 허용 → G1. Heap 32~128GB · P99 < 10ms → ZGC. Heap > 128GB → Generational ZGC(JDK 21+). Throughput 최우선 → Parallel/G1. Tail latency 최우선 → ZGC.

</details>

<details>
<summary><b>Q-S3. Production OOM 진단 절차?</b></summary>

Heap dump 확보(`-XX:+HeapDumpOnOutOfMemoryError`) → MAT로 Leak Suspects/Dominator Tree/GC Roots → 5대 누수 패턴(static, ThreadLocal, Listener, Cache, JDBC) → OOM 종류 확인(Heap/Metaspace/Direct/Thread) → 코드 수정 + 알람 + GC log/JFR/NMT 사후 보강.

</details>

<details>
<summary><b>Q-S4. Container 환경 JVM 메모리 설정 가이드?</b></summary>

Container limit 5GB 기준 예:
- `-Xmx2g` (40%) · `-XX:MaxDirectMemorySize=1g` · `-XX:MaxMetaspaceSize=512m` · `-XX:ReservedCodeCacheSize=256m`
- Thread stacks 500 × 1MB = 500m
- 여유 700m (JVM internal + kernel + libs)

모니터링: cgroup `memory.current`(RSS), NMT(`-XX:NativeMemoryTracking=summary` + `jcmd VM.native_memory`).

</details>

<details>
<summary><b>Q-S5. Virtual Thread를 운영에 도입한다면 무엇을 점검할까?</b></summary>

1. JDK 21+ 필수.
2. **Pinning 위험**: hot path의 `synchronized` 안 blocking I/O → ReentrantLock로 교체 또는 JEP 491 대기.
3. **ThreadLocal 사용량**: VT 수만 개면 ThreadLocal 메모리 폭증 → ScopedValue 검토.
4. **Connection pool 크기**: 옛 모델은 thread 수 = pool 상한이었지만 VT는 그 가정이 깨짐. DB·HTTP client pool 한계 재산정.
5. **모니터링**: VT는 OS 스레드처럼 안 보임 → JFR 이벤트 `jdk.VirtualThreadStart` 등 새 메트릭 도입.

</details>

## 🔴 Principal 종합 5문

<details>
<summary><b>Q-P1. JDK 25(다음 LTS)에서 책임자라면 어떤 변화를 우선?</b></summary>

1. **JEP 491 (synchronized pinning 해소)** — VT 본격 채택의 마지막 장벽.
2. **Project Lilliput stable** — Mark Word 압축, footprint 5~10% ↓.
3. **Vector API stable** — SuperWord 보완, SIMD 표준화.
4. **Project Leyden 진전** — AOT 표준화, Native Image와 HotSpot의 경계 흐려짐.
5. **Generational ZGC default 검토** — G1 대체 가능성 평가.
6. **Project Valhalla preview 확대** — value types, generic specialization.

</details>

<details>
<summary><b>Q-P2. 차세대 default GC 결정 기준?</b></summary>

평가 차원: Latency(P99 STW 분포) · Throughput · Footprint · Maintenance(코드 복잡도, 커뮤니티) · 호환성(워크로드/OS/CPU) · 운영 도구(모니터링·디버깅 성숙도).

후보: G1(안정, throughput, STW 예측 가능) vs Generational ZGC(차세대, 거의 모든 면에서 G1 동등 + sub-ms STW). 결정 로드맵: JDK 25에서 Gen-ZGC 검증 → JDK 27에서 default 전환 검토.

</details>

<details>
<summary><b>Q-P3. 100대 규모 Production Java 서비스의 메모리/GC 표준화 전략?</b></summary>

1. **메트릭 표준화**: Prometheus + Grafana 통일, JFR continuous, 알람 기준(GC time%, Full GC 빈도, allocation rate).
2. **JDK 버전 통일**: 8→17/21 로드맵, LTS만(8/11/17/21).
3. **GC 선택 표준**: 일반 → G1 + `MaxGCPauseMillis=200`. Latency-critical → ZGC. 큰 Heap → Gen-ZGC.
4. **자동화**: heap dump auto on OOM, container limit ↔ JVM 옵션 자동 매핑, GC log retention.
5. **운영 능력**: 팀당 시니어 1+, 사고 playbook, quarterly perf review.

</details>

<details>
<summary><b>Q-P4. Virtual Thread의 30년 만의 영향 평가?</b></summary>

긍정: Color-of-function 해결, reactive 복잡도 회피, 디버깅 자연스러움, Spring 3.2+ 기본 지원.
부정/주의: Pinning 함정, 옛 라이브러리 호환성, CPU-bound 부적합, ThreadLocal 대량 사용 시 메모리↑.
운영: microservice 동시성 한계↑, connection pool 재검토, 모니터링 확장.
장기: Reactive 프레임워크 의미 약화, sync 코드 + VT 추세.

</details>

<details>
<summary><b>Q-P5. (Killer) 글로벌 fintech의 JVM 인프라 책임자, 첫 100일 plan?</b></summary>

**Day 1-30 진단**: 인프라 audit(JDK, GC, 메트릭) · 사고 history(P99 spike, OOM, downtime) · 부하 패턴 모델링 · 팀 역량 평가.
**Day 31-60 표준화**: JVM 옵션 template · 메트릭+알람 표준 · GC log/JFR retention · 사고 playbook.
**Day 61-90 개선**: 가장 큰 risk 서비스부터 마이그 · canary 절차 · 모니터링 대시보드 통합 · 시니어 hire/train.
**Day 91-100 최적화**: 메트릭 기반 GC/JIT 튜닝 · Native Image 검토 · 차세대 JDK plan.

</details>

---

# ⚔️ Part 3 — 1시간 종합 시뮬레이션

| 시간대 | 주제 | 관련 챕터 |
|---|---|---|
| 0-10분 | Self-intro + 기본: "JVM 메모리 영역을 그려보세요" / "GC 알고리즘 하나 깊이" | Ch 02, Ch 04 |
| 10-30분 | Deep dive: "JIT 컴파일 흐름 + Tiered" / "Virtual Thread 동작 원리" | Ch 03, Ch 05 |
| 30-50분 | Production: "P99 latency spike 진단 절차" / "Container OOM-killed 분석" | Ch 10 |
| 50-60분 | 시스템 설계: "100대 서비스의 JVM 표준화 전략" | Principal |

면접관 입장에서 이 흐름은 **표면 → 내부 → 운영 → 결정**으로 깊이가 한 칸씩 늘어난다. 답하는 사람은 각 단계마다 "그림 1개 + 한 문장 결론 + 트레이드오프"를 같이 내야 한다.

---

# 🧪 Part 4 — 실전 받았던 질문 40문 (5트랙)

> 실제 면접 자리에서 받은 질문들을 트랙별로 묶었다. 모든 답은 토글 안에 있고, **답의 근거는 jvm/ 또는 oop/ 디렉터리 본문에서 모두 커버 가능**하다. 출처 챕터를 함께 표기했으니 약한 답이 나오면 그 챕터로 돌아가라.

## Track A — JVM 메모리 & GC (8문)

### A1. 🟡 JVM의 메모리 구조(Heap, Stack, Method Area 등)와 각 영역의 역할, 그리고 GC가 각 영역에 어떻게 작동하는지 상세히 설명해보세요.

<details>
<summary>답</summary>

**6개 주요 영역**:

| 영역 | 공유 | GC 대상 | 무엇 |
|---|---|---|---|
| **Heap** | thread 공유 | ✅ 직접 회수 | 객체 인스턴스, 배열 |
| **Method Area = Metaspace** (JDK 8+) | thread 공유 | CL 단위 unload | Klass, Method, ConstantPool 등 메타데이터 |
| **Stack** | per-thread | ❌ (스레드 종료 시 해제, GC root) | Stack Frame: 지역변수, operand stack, return address |
| **PC Register** | per-thread | ❌ | 현재 bytecode 위치 |
| **Native Method Stack** | per-thread | ❌ | JNI 호출용 |
| **Code Cache** | thread 공유 | JIT가 관리 | JIT가 만든 native 코드 |
| (보조) **Direct Memory** | thread 공유 | wrapper GC + Cleaner | NIO ByteBuffer.allocateDirect |

**GC가 각 영역에 작용하는 방식**:
- **Heap**: GC의 주 대상. Reachability(Stack/static을 root로 mark) → unreachable 회수. Young/Old 세대로 분리.
- **Metaspace**: ClassLoader가 GC되면 그 CLD의 chunk 통째로 회수. PermGen과 달리 native 메모리 → unbounded 가능.
- **Stack/PC/Native**: GC가 직접 회수하지 않음. 단, **stack frame의 local variable이 GC root**라 stack을 훑어 root set을 구성.
- **Code Cache**: JIT가 자체 관리 (`-XX:+UseCodeCacheFlushing`). GC와 별개.

> 출처: `02-runtime-data-areas/README.md`, `04-gc/01-gc-fundamentals.md`

</details>

### A2. 🟡 GC의 Young Generation과 Old Generation의 차이와 각각의 GC 알고리즘(JVM별로) 동작 방식은?

<details>
<summary>답</summary>

**전제 — Generational Hypothesis**: 대부분 객체는 짧게 살고 죽는다, 오래 산 객체는 앞으로도 오래 산다.

```
Young Gen
  ├ Eden          ← 새 객체 할당
  ├ Survivor 0    ┐
  └ Survivor 1    ┘ Minor GC 때 살아남은 객체를 옮기는 두 공간
Old Gen           ← Survivor에서 N번 살아남으면 promote
```

**Minor GC** (Young만): 짧고 자주. 대부분 Copying 알고리즘 — 살아있는 것만 다른 공간으로 복사 → 옛 영역 통째로 비움.
**Major/Full GC** (Old 포함): 길고 드물게.

| GC | Young 알고리즘 | Old 알고리즘 |
|---|---|---|
| **Serial** | Copying (단일 스레드) | Mark-Sweep-Compact (단일) |
| **Parallel** | Copying (멀티 스레드) | Mark-Sweep-Compact (멀티) — 처리량 최적 |
| **CMS** (deprecated JDK 9, 제거 JDK 14) | Copying | Concurrent Mark-Sweep (대부분 동시) |
| **G1** | Region 단위 evacuation (멀티) | Concurrent marking + Mixed GC로 Old region 점진 회수 |
| **ZGC / Shenandoah** | 세대 구분 없음(JDK 21 Gen-ZGC부터 다시 도입) — 모든 phase concurrent | 모든 phase concurrent + colored pointer / load barrier |

> 출처: `04-gc/02-generational-and-serial-parallel.md`, `04-gc/03-cms-and-g1.md`

</details>

### A3. 🟡 G1 GC, CMS, ZGC 등 최신 GC 알고리즘의 내부 동작 원리와 장단점은?

<details>
<summary>답</summary>

**CMS (Concurrent Mark-Sweep)** — *deprecated JDK 9, 제거 JDK 14*
- 동작: Initial Mark(STW) → Concurrent Mark → Remark(STW) → Concurrent Sweep.
- 장: Old GC를 거의 동시에 → pause 짧음.
- 단: Compaction 없음 → 단편화 누적 → Promotion Failure 시 Full GC(STW 길어짐). 코드 복잡도 ↑.

**G1 (Garbage First)** — JDK 9+ default
- 동작: Heap을 region(1~32MB)으로 분할 → Concurrent Marking으로 region별 garbage 양 산출 → garbage가 많은 region부터 evacuate.
- `-XX:MaxGCPauseMillis=200` 목표 안에 끝낼 만큼만 region 선택.
- 장: pause 예측 가능, 큰 heap에 적합, Compaction 포함.
- 단: write barrier 비용, P99 sub-ms는 어려움.

**ZGC**
- 동작: 모든 phase concurrent. STW는 root scan만(< 1ms). **Colored Pointer**(64bit 포인터에 GC 상태 비트 내장) + Load Barrier로 처리.
- 장: 대형 heap(TB급)에서도 P99 sub-ms.
- 단: throughput이 G1 대비 10~15% 낮을 수 있음 → JDK 21 **Generational ZGC**가 이 격차를 거의 없앰.

**Shenandoah**
- 동작: ZGC와 유사. Brooks Pointer로 객체 forwarding.
- 장단: ZGC와 비슷, 운영 도구 성숙도는 ZGC가 더 높음.

> 출처: `04-gc/03-cms-and-g1.md`, `04-gc/04-zgc-and-shenandoah.md`, `04-gc/05-generational-zgc.md`

</details>

### A4. 🟡 JVM 튜닝 시 메모리 영역별 파라미터 조정이 성능에 미치는 영향은?

<details>
<summary>답</summary>

| 파라미터 | 영향 |
|---|---|
| `-Xms` / `-Xmx` | Heap 시작/최대. 같게 두면 startup에 한 번에 할당 → 런타임 확장 비용 0. |
| `-XX:NewRatio` / `-Xmn` | Young/Old 비율. Young 크면 Minor GC 길지만 promotion ↓. 작으면 promotion 빨라져 Old 부담 ↑. |
| `-XX:SurvivorRatio` | Eden vs Survivor 비율. Survivor 작으면 promotion 빨라짐. |
| `-XX:MaxTenuringThreshold` | Survivor에서 promote까지의 GC 횟수. 큰 값 = 오래 Young에 머묾. |
| `-XX:MaxMetaspaceSize` | Metaspace 상한. 무한이면 native 메모리 폭증 위험. 컨테이너에선 반드시 설정. |
| `-XX:ReservedCodeCacheSize` | Code Cache 크기. 가득 차면 JIT 중단 → 인터프리터 fall back → 성능 급락. |
| `-XX:MaxDirectMemorySize` | Direct Memory 상한. NIO/Netty 워크로드 필수. |
| `-XX:MaxGCPauseMillis` | G1 목표 pause. 작게 두면 자주 짧게 GC. |
| `-XX:G1HeapRegionSize` | G1 region 크기. Humongous 객체 회피용. |

원칙: **트레이드오프는 항상 throughput ↔ latency ↔ footprint** 셋 중 둘만 잡힘. 메트릭(GC time%, allocation rate, P99)을 보고 조정.

> 출처: `04-gc/06-gc-tuning-and-ops.md`

</details>

### A5. 🟡 메모리 릭이 발생하는 구체적 시나리오와 이를 탐지/해결하는 방법은?

<details>
<summary>답</summary>

**5대 누수 패턴**:

| 패턴 | 시나리오 |
|---|---|
| **Static collection** | `static Map cache = new HashMap<>();` 무한 put, eviction 없음 |
| **ThreadLocal 미해제** | 풀의 스레드가 옛 객체를 영원히 들고 있음 |
| **Listener/Callback 미해제** | UI/event 등록 후 `removeListener` 안 함 |
| **Cache 무한 성장** | Caffeine/Guava maxSize 안 정함 |
| **JDBC Driver 등록** | DriverManager가 Driver(Webapp/Restart CL) 참조 → CL 누수 |

**탐지**:
1. `-XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/var/dumps`.
2. `jcmd <pid> GC.heap_dump` (사후 수집).
3. MAT(Eclipse Memory Analyzer): Leak Suspects → Dominator Tree → Path to GC Roots.
4. 정기 heap dump diff(`jhat`, MAT compare): 사이즈 증가 객체 식별.
5. JFR `ObjectAllocationInNewTLAB` continuous로 allocation hot path.

**해결**: 누수 시점에 명시 cleanup (`@PreDestroy`, `ApplicationListener<ContextClosedEvent>`).

> 출처: `04-gc/06-gc-tuning-and-ops.md`, `02-classloader-hierarchy.md`(실전 에러 8종 토글)

</details>

### A6. 🟡 JVM에서 Native Memory Tracking(NMT)의 활용법과 실전 적용 사례는?

<details>
<summary>답</summary>

**NMT** = Heap **외부** 메모리(Metaspace, Code Cache, Direct, Thread stacks, GC bookkeeping 등)를 카테고리별로 추적하는 JVM 기능.

**활성화**:
```
-XX:NativeMemoryTracking=summary    # 또는 detail
```
런타임 조회:
```
jcmd <pid> VM.native_memory summary
jcmd <pid> VM.native_memory baseline           # 기준점 저장
jcmd <pid> VM.native_memory summary.diff       # 기준점과 비교
```

**출력 예시**:
```
Total: reserved=4GB, committed=2.1GB
  Java Heap:    reserved=2GB, committed=1.5GB
  Class:        reserved=1GB, committed=200MB  (Metaspace + Class Space)
  Thread:       reserved=500MB, committed=500MB (스레드 × 1MB stack)
  Code:         reserved=250MB, committed=80MB  (Code Cache)
  GC:           reserved=80MB                   (Card Table, RSet 등)
  Internal:     ...
```

**실전 사례**:
1. **Container OOM-killed인데 Heap은 평온** → NMT로 Direct 또는 Thread 영역 폭증 발견.
2. **Metaspace 누수**: `Class` 영역 증가 추적 → CL 누수.
3. **스레드 폭증**: `Thread` 영역 = 스레드 수 × `-Xss`. 풀 한도 점검.
4. **Compressed Class Space 부족**: `Class - class space` 분리 확인.

> 출처: `02-runtime-data-areas/06-gc-bookkeeping-and-others.md`, `04-gc/06-gc-tuning-and-ops.md`

</details>

### A7. 🟡 GC Pause Time을 줄이기 위한 실무적 전략은?

<details>
<summary>답</summary>

**1) Allocation rate 줄이기** (가장 효과 큼)
- Escape Analysis가 잡히도록 작은 객체는 메서드 안에서만.
- 큰 컬렉션 reuse(`clear()`), object pool은 큰 객체에만(작은 건 EA가 더 빠름).
- Stream의 boxing 회피(`mapToInt` 등).

**2) Young Gen 적절히 키우기**
- 짧은 객체가 Young에서 죽도록 충분히 크게 → promotion 회피.
- 단 Young 너무 크면 Minor GC 길어짐 — 측정으로 sweet spot.

**3) GC 알고리즘 선택**
- Heap < 32GB, P99 200ms 허용: G1.
- P99 < 10ms 목표: ZGC/Shenandoah.
- 큰 heap + tail latency: Generational ZGC.

**4) Humongous 객체 회피**
- G1에서 region size의 절반 초과 객체는 Humongous → 별도 처리, 비용 큼.
- 큰 byte[] 자주 만들면 `-XX:G1HeapRegionSize` 키우거나 chunk 분할.

**5) Concurrent cycle 충분히 시작**
- G1 `-XX:InitiatingHeapOccupancyPercent` 낮춰 동시 마킹 미리 시작.
- Old gen 채워지기 전에 끝나야 Full GC 회피.

**6) 운영 보강**
- GC log + JFR continuous로 STW 분포 추적.
- P99 spike와 GC pause 시각 cross-check.

> 출처: `04-gc/06-gc-tuning-and-ops.md`

</details>

### A8. 🟡 JVM 메모리 구조가 컨테이너 환경(Docker 등)에서 어떻게 달라지는지 설명해보세요.

<details>
<summary>답</summary>

**JDK 10+ 이전**의 함정: JVM이 호스트의 CPU/메모리를 보고 `-Xmx`/`-XX:ParallelGCThreads`를 결정 → 컨테이너 limit과 무관한 큰 값 → cgroup에 의해 OOM-killed.

**JDK 10+ (실질 JDK 11+)**: cgroup 인식 활성화. `UseContainerSupport`(기본 on).
- `-Xmx`/`-Xms` 미지정 시 cgroup memory limit 기준으로 자동 산정 (`MaxRAMPercentage=25%` 기본).
- CPU set 인식 → `availableProcessors()`가 cgroup quota 반영.

**컨테이너 메모리 설정 템플릿** (5GB limit 예):
```
-Xmx2g                     (Heap 40%)
-XX:MaxDirectMemorySize=1g (Direct 20%)
-XX:MaxMetaspaceSize=512m  (10%)
-XX:ReservedCodeCacheSize=256m
-Xss1m                     (× 스레드 수 = stacks)
여유 700m: JVM internal + kernel + libs + RSS overhead
```

**모니터링**: cgroup `memory.current`(RSS), NMT, container의 OOM-killer log.

**흔한 함정**:
- `-XX:+AlwaysPreTouch` 안 켜면 RSS가 lazy하게 증가 → 갑작스런 OOM-kill.
- Direct Memory 상한 미설정 → Heap 평온한데 RSS 폭증.
- `-Xss`(스레드 stack)가 작아 보여도 스레드 수가 많으면 합산이 큼.

> 출처: `02-runtime-data-areas/05-direct-memory.md`, `04-gc/06-gc-tuning-and-ops.md`

</details>

---

## Track B — JIT & AOT (8문)

### B1. 🟡 JIT 컴파일러와 AOT 컴파일러의 차이, 그리고 HotSpot JVM에서의 JIT 최적화 기법(예: 인라이닝, 루프 언롤링 등)에 대해 설명해보세요.

<details>
<summary>답</summary>

| 항목 | JIT (Just-In-Time) | AOT (Ahead-Of-Time) |
|---|---|---|
| 컴파일 시점 | 런타임 (자주 실행되면) | 빌드 시점 |
| 입력 | bytecode + 런타임 프로파일 | bytecode (또는 소스) |
| 최적화 자료 | 실제 실행 통계 (branch%, type profile) | 정적 분석만 |
| 결과 | Code Cache의 native 코드 | OS native 실행 파일 |
| 장점 | 실제 사용 패턴에 맞춤. speculative optimization 가능 | 부팅 즉시 풀스피드, JIT 없어 메모리 ↓ |
| 단점 | 워밍업 필요. JIT 자체 비용 | 실행 패턴 미반영. reflection·동적 로딩 제약 |

**HotSpot JIT 주요 최적화 기법**:
1. **Inlining** — 호출 대상을 호출 위치에 펼침. 최적화 사슬의 출발점.
2. **Loop Unrolling** — 루프 반복을 N번 복사해 분기 비용↓ + SIMD 기회.
3. **Loop Vectorization (SuperWord)** — 루프 안 연속 연산을 SIMD(AVX/NEON)로 변환.
4. **Escape Analysis + Scalar Replacement** — 도망 안 가는 객체를 레지스터로 분해.
5. **Lock Elision / Coarsening** — synchronized가 무의미하면 제거, 인접 lock 합침.
6. **Dead Code Elimination** + **Constant Folding** + **Copy Propagation**.
7. **Devirtualization** — monomorphic call site의 virtual 호출을 static 호출로 변환.
8. **Branch Prediction Hint** — profile 기반 hot/cold branch 분리.
9. **Inline Caching (PIC)** — virtual/interface call의 dispatch 결과 캐싱.

> 출처: `03-execution-engine/01-execution-overview.md`, `05-inlining-and-ic.md`, `06-escape-analysis.md`, `07-loop-and-vector.md`

</details>

### B2. 🟡 JIT 컴파일러의 옵티마이저 단계별 동작 원리와 실전에서의 튜닝 포인트는?

<details>
<summary>답</summary>

**HotSpot Tiered Compilation** (Level 0~4):

| Level | 누가 | 동작 | 비고 |
|---|---|---|---|
| 0 | Interpreter | Template Interpreter, 프로파일 수집 | 시작점 |
| 1 | C1 | 최소 최적화, 프로파일 X | 트리비얼 메서드 |
| 2 | C1 | invocation/backedge counter만 | C2 대기 큐 백업 |
| 3 | C1 | 완전 프로파일링 | 대부분 여기로 |
| 4 | C2 | 풀 최적화 (인라이닝, EA, unroll, SIMD) | 가장 hot한 코드 |

기본 흐름: 0 → 3 → 4. 1·2는 C2 큐가 가득 찼을 때.

**튜닝 포인트**:
- `-XX:ReservedCodeCacheSize`: Code Cache 부족 시 JIT 중단 → 늘림.
- `-XX:CICompilerCount`: 컴파일러 스레드 수. CPU 많은 머신에선 늘려서 워밍업 단축.
- `-XX:CompileThreshold`: Tier 4 진입 임계. 보통 default 둠.
- `-XX:+TieredCompilation` (기본 on). off 하면 인터프리터 → C2 직행(워밍업 느림).
- `-XX:MaxInlineSize=35`, `-XX:FreqInlineSize=325`: 인라인 한계. 너무 키우면 Code Cache 폭증.

**관찰**:
- `-XX:+PrintCompilation`: 메서드별 컴파일 이벤트.
- `-XX:+PrintInlining`: 인라인 실패 원인.
- JFR `CompilerStatistics`, `CompilerInlining`.

> 출처: `03-execution-engine/03-tiered-compilation.md`, `05-inlining-and-ic.md`

</details>

### B3. 🟡 C1, C2 컴파일러의 차이와 각각의 장단점은?

<details>
<summary>답</summary>

| 항목 | C1 (Client) | C2 (Server) |
|---|---|---|
| 목적 | 빠르게 native로 가기 | 최고 품질의 코드 |
| 컴파일 시간 | 짧음 (수 ms) | 김 (수십~수백 ms) |
| 최적화 강도 | 가벼움 | 공격적 (인라이닝, EA, unroll, SIMD, 추측 최적화) |
| IR | HIR(High-level) + LIR(Low-level) | **Sea-of-Nodes** 그래프 |
| 프로파일 | Tier 2/3에서 수집 | 입력으로 사용 |
| Deoptimization | 거의 안 함 | 자주 함 (추측이 깨지면) |

**C1 장점**: 빠른 워밍업, 작은 메모리.
**C2 장점**: 풀 최적화로 sustained throughput 최대.

**Tiered**(JDK 8+ default)는 두 컴파일러를 함께 굴려 **C1으로 빨리 native로 간 뒤 hot한 곳만 C2로** 다시 컴파일하는 형태.

JDK 9+ GraalVM JIT는 C2 자리를 대체할 수 있는 옵션. Java로 짜여 유지보수 쉽고, partial escape analysis 같은 더 공격적 최적화 제공.

> 출처: `03-execution-engine/04-c1-and-c2.md`, `08-graalvm/README.md`

</details>

### B4. 🟡 JIT 컴파일러의 프로파일링 데이터 수집 방식과 실제 코드 최적화에 미치는 영향은?

<details>
<summary>답</summary>

**수집 방식** (Tier 0/3에서):
- **Invocation counter**: 메서드 호출 횟수.
- **Backedge counter**: 루프 반복 횟수(루프 자체가 hot이면 OSR 트리거).
- **Type profile**: virtual/interface call 사이트에서 실제 들어온 receiver 타입 분포.
- **Branch profile**: if/switch의 taken 빈도.
- **Null check stats**: NPE 발생 여부.

**최적화에 미치는 영향**:
- **Type profile → Devirtualization**: 한 타입만 들어오면(monomorphic) virtual call → static call. 인라인까지 연결.
- **Branch profile**: hot branch를 fall-through, cold branch를 jump → branch predictor 친화적.
- **Null check**: NPE가 한 번도 안 났으면 implicit null check(SIGSEGV trap) 사용 → 명시 비교 제거.
- **Backedge counter → OSR(On-Stack Replacement)**: 루프 안에서 컴파일된 코드로 점프해 들어감 → 메서드 첫 호출까지 안 기다림.

**실전 영향**:
- 워밍업 안 된 프로세스에서 benchmark 돌리면 의미 없음 — 프로파일이 부족해 최적화 안 됨.
- `MethodHandle` 같이 reflection-heavy 코드는 profile pollution → polymorphic으로 분류 → 최적화 약화.

> 출처: `03-execution-engine/03-tiered-compilation.md`, `05-inlining-and-ic.md`

</details>

### B5. 🟡 AOT 컴파일이 JVM 기반 대규모 서비스에 미치는 장단점은?

<details>
<summary>답</summary>

**장점**:
- **부팅 시간 급감** (수 초 → ms 단위). serverless, sidecar, CLI에 결정적.
- **메모리 footprint 작음**: JIT, Code Cache, profile data 없음.
- **예측 가능한 성능**: 워밍업 없이 첫 요청부터 풀스피드.
- **컨테이너 이미지 작음** (JRE 없이 native binary).

**단점**:
- **빌드 시간 길고 메모리 많이 씀** (5~15분, 8~16GB).
- **런타임 reflection 제약**: `reflect-config.json` 사전 등록 필요. Spring Boot Native가 자동화하지만 third-party는 별도 작업.
- **동적 클래스 로딩 불가**: `URLClassLoader`로 새 jar 로드 불가 → 플러그인 아키텍처 부적합.
- **프로파일-가이드 최적화 부재**: long-running 워크로드는 풀워밍업된 HotSpot이 더 빠를 수 있음.
- **디버깅·툴링 미성숙**: JFR, jcmd 등 일부 기능 제한.

**적합/부적합**:
- 적합: AWS Lambda, GCP Cloud Run의 짧은 컨테이너, kubectl-같은 CLI, gateway/proxy sidecar.
- 부적합: 트레이딩 시스템, 큰 웹 서버(profile-driven 최적화 이득이 큼), 동적 클래스 로딩 필요한 앱.

> 출처: `08-graalvm/README.md`

</details>

### B6. 🟡 JIT 컴파일러의 Deoptimization(역최적화) 상황과 그 원인은?

<details>
<summary>답</summary>

**Deoptimization** = JIT가 했던 추측이 깨져 native 코드 실행을 중단하고 인터프리터로 fall back하는 동작.

**원인**:
1. **Class Hierarchy 변경**: 새 클래스 로드로 polymorphism 증가 → "monomorphic이라 인라인했다"는 가정 깨짐.
2. **Unstable type profile**: 새 타입이 호출 사이트에 들어옴 → devirtualization 무효.
3. **Implicit Null check**: 한 번도 안 나던 NPE가 발생 → 명시 검사로 재컴파일.
4. **Branch profile 변화**: cold로 분류했던 분기가 자주 타게 됨.
5. **Class redefinition**: JVMTI/디버거가 클래스 재정의.
6. **Uncommon trap**: speculation이 명시적으로 실패(예: array bound check).

**동작**:
1. native 코드 실행 중단.
2. 스택 프레임을 **인터프리터 프레임으로 재구성**.
3. 인터프리터로 fall back.
4. 다시 hot해지면 새 프로파일로 재컴파일.

**관찰**:
```
-XX:+PrintCompilation -XX:+TraceDeoptimization
```
JFR `CompilerDeoptimization` 이벤트. P99 spike의 흔한 원인 — deopt 자체 비용 + 인터프리터 잠시 머묾.

> 출처: `03-execution-engine/08-speculative-and-deopt.md`

</details>

### B7. 🟡 JVM에서 JIT 컴파일러의 동작을 실시간으로 모니터링하는 방법은?

<details>
<summary>답</summary>

**1. JVM 옵션 (로깅)**:
```
-XX:+PrintCompilation            # 메서드별 컴파일/deopt 이벤트
-XX:+PrintInlining               # 인라인 결정/실패 이유
-XX:+UnlockDiagnosticVMOptions
-XX:+PrintCompilation2           # 더 상세
-XX:+LogCompilation              # XML로 출력(JITWatch가 이걸 읽음)
```

**2. JFR (Java Flight Recorder)** — 운영에서 가장 자주 씀
```
jcmd <pid> JFR.start name=jit duration=60s filename=/tmp/jit.jfr
```
JFR 이벤트:
- `Compilation`, `CompilerInlining`, `CompilerStatistics`, `CompilerDeoptimization`.
- JDK Mission Control(JMC)로 열어 메서드별 컴파일 시간·deopt 빈도 시각화.

**3. jcmd 즉시 조회**:
```
jcmd <pid> Compiler.codecache               # Code Cache 사용량
jcmd <pid> Compiler.queue                   # 컴파일 큐 길이
jcmd <pid> VM.flags                         # 현재 JIT 옵션
```

**4. JITWatch** (오픈소스): `-XX:+LogCompilation` 출력 분석. 인라인 트리, IR 시각화.

**5. perf + perf-map-agent**: Linux perf로 native CPU 프로파일 → JIT가 만든 메서드 이름까지 표시.

> 출처: `03-execution-engine/03-tiered-compilation.md`, `04-c1-and-c2.md`

</details>

### B8. 🟡 JIT와 GC의 상호작용이 성능에 미치는 영향은?

<details>
<summary>답</summary>

**서로의 영향**:

1. **JIT가 GC root scan을 무겁게 만듦**:
   - JIT 컴파일된 메서드의 스택 프레임은 인터프리터보다 layout이 복잡 → root scan 비용 ↑.
   - HotSpot은 `OopMap`을 미리 생성해 안전점에서 어느 슬롯이 oop인지 빠르게 식별.

2. **GC가 JIT 코드를 무효화 가능**:
   - 클래스 unload 시 그 클래스에 의존하던 컴파일 코드 모두 invalidate → deopt.
   - CMS/G1/ZGC 모두 nmethod sweeper로 이 청소를 수행.

3. **Safepoint 동기화**:
   - GC 시작 전 모든 스레드가 safepoint에 도달해야 STW 가능.
   - JIT 코드는 safepoint poll 명령을 루프 백엣지·메서드 진입에 박아둠 → 너무 빽빽하면 throughput↓, 너무 드물면 STW 도달 지연.
   - `-XX:+UseCountedLoopSafepoints` 등으로 조정.

4. **Code Cache vs Heap 압력**:
   - JIT가 인라인 많이 하면 Code Cache 증가 → 차면 JIT 중단.
   - GC와 JIT는 서로 다른 메모리 영역을 쓰지만 같은 RSS 안에서 경쟁.

5. **EA가 GC 부담을 직접 줄임**:
   - Scalar Replacement된 객체는 heap에 안 가서 GC가 볼 일이 없음 → allocation rate ↓.
   - "EA가 잘 잡힌 코드" = "GC가 거의 안 도는 코드".

> 출처: `03-execution-engine/06-escape-analysis.md`, `04-gc/06-gc-tuning-and-ops.md`

</details>

---

## Track C — 자바 버전 (8문)

### C1. 🟡 자바 8, 9, 11, 17, 21 버전에서의 주요 변화와, 각 버전별로 실무 시스템 설계에 미치는 영향에 대해 설명해보세요.

<details>
<summary>답</summary>

| 버전 | 주요 변화 | 실무 영향 |
|---|---|---|
| **8 (2014, LTS)** | Lambda, Stream, Optional, default method, Metaspace(PermGen 제거), Nashorn | 함수형 스타일 도입. 많은 레거시가 여전히 8. |
| **9 (2017)** | **JPMS(Jigsaw)**, jlink, jshell, G1 default, `sun.misc.*` 캡슐화 | 비-LTS. 모듈 시스템 진입점. 대부분 8에서 11로 점프. |
| **11 (2018, LTS)** | `var`, HTTP Client 표준, ZGC experimental, Epsilon GC, AppCDS, `Files.readString` | 8 → 11이 가장 흔한 마이그레이션 점프. |
| **17 (2021, LTS)** | Sealed, Pattern matching for instanceof, Records 표준화, Strong encapsulation 강제, ZGC production | Spring Boot 3 baseline. 21로 가기 전 디딤돌. |
| **21 (2023, LTS)** | **Virtual Threads**(stable), Pattern matching for switch, Sequenced Collections, Generational ZGC | 동시성 모델 변혁. Spring Boot 3.2+ 기본 지원. |

**설계 영향**:
- 8 → 11/17/21로 갈수록 **함수형 도구 확대 + 모듈 캡슐화 강화 + GC/스레딩 변혁**.
- 8 기준 코드는 reflection으로 `sun.misc.*` 건드는 라이브러리 많음 → 17+에서 깨짐.
- VT 도입 후 connection pool·threadpool 사이즈 가정이 다 바뀜.

> 출처: `06-version-history/README.md`

</details>

### C2. 🟡 자바 8의 람다, 스트림, Optional 등 함수형 프로그래밍 도입이 기존 설계 패턴에 미친 영향은?

<details>
<summary>답</summary>

**Lambda + Functional Interface**:
- Anonymous class 보일러플레이트 제거 → Strategy/Command 패턴이 1줄로 표현.
- `Runnable`, `Comparator`, `Function<T,R>` 등이 함수형으로 자연스러워짐.
- 이로 인해 **GoF 패턴 23개 중 절반의 무게가 가벼워짐** (Strategy, Command, Observer, Template Method).

**Stream**:
- 컬렉션 처리의 선언적 표현 (`filter/map/collect`).
- Iterator/while 패턴 대거 사라짐.
- 단점: 디버깅 어려움, primitive boxing 비용, parallel stream 함정.

**Optional**:
- "null 가능"을 타입으로 표현 → API 시그니처에 명시.
- 단점: 필드/파라미터로 쓰면 안티패턴 (반환값 전용).

**기존 패턴과의 충돌**:
- 옛 Builder 패턴은 여전히 유효(record + lombok도 비슷).
- Visitor 패턴은 Sealed + Pattern matching(17+)로 더 우아하게.

**부작용**:
- Stream/Lambda 남용 시 stack trace 읽기 어려움 — 익명 람다가 `lambda$mtd$0` 같은 이름으로 잡힘.
- JIT 인라인이 lambda 호출 사이트를 어떻게 다루는지 알면 hot path 디자인이 바뀜.

> 출처: `06-version-history/README.md`, `oop/`

</details>

### C3. 🟡 자바 9의 모듈 시스템(Jigsaw) 도입이 대규모 프로젝트에 미치는 영향과 실제 마이그레이션 사례는?

<details>
<summary>답</summary>

**JPMS 핵심**: `module-info.java`로 명시적 `requires`/`exports` 선언. 패키지 단위가 아니라 모듈 단위 캡슐화.

**대규모 영향**:
1. **JDK 자체 분할**: `rt.jar` 60MB → `java.base`, `java.sql`, `java.xml` 등 60+개 모듈.
2. **`sun.misc.*` 등 내부 패키지 reflection 차단** → 기존 라이브러리 깨짐.
3. **`Class.forName`으로 다른 모듈의 비-export 클래스 접근 불가**.
4. **classpath와 module-path 공존**: 점진 마이그 가능.

**마이그레이션 사례 패턴**:
- 1단계: 클래스패스 그대로 두고 JDK 11/17로 올림 → `--add-opens`로 임시 우회.
- 2단계: Automatic Module(빈 module-info에 jar 자동 매핑) → 핵심 모듈만 `module-info.java` 작성.
- 3단계: 전체 모듈화.

대부분의 기업은 **2단계에서 멈춤**. 풀 JPMS 마이그는 ROI가 낮아 잘 안 함. 대신 `jlink`로 모듈 기반 커스텀 JRE 만드는 용도로는 활용.

**실제 깨지는 사례**:
- Hibernate, Mockito, Lombok이 `--add-opens java.base/java.lang=ALL-UNNAMED` 필요했음.
- Reflection-heavy 코드는 JDK 17+에서 IllegalAccessException 폭증.

> 출처: `06-version-history/README.md`, `02-classloader-hierarchy.md`

</details>

### C4. 🟡 자바 11, 17, 21에서의 GC, 스레드, 언어 기능 변화가 대규모 서비스 운영에 미치는 영향은?

<details>
<summary>답</summary>

**11**:
- ZGC experimental → 큰 heap 실험 가능.
- Epsilon GC(no-op) → 벤치마크에서 GC 영향 분리.
- HTTP Client 표준 → Apache HttpClient 의존 줄어듦.

**17**:
- ZGC production-ready → 트레이딩 등 latency-critical 서비스 점진 도입.
- Strong encapsulation 기본화 → 호환성 검증 필수.
- Sealed/Records → 도메인 모델 표현력↑, DTO 보일러플레이트 ↓.

**21**:
- **Virtual Threads stable**: connection pool·threadpool 가정이 바뀜.
- **Generational ZGC**: G1 대비 throughput 격차 거의 사라짐 → 차세대 default 후보.
- Pattern matching for switch → 도메인 분기 표현력↑.

**대규모 운영 영향**:
- GC 선택지 다양화 → 워크로드별 최적 GC 다름. 표준화 가이드 필요.
- VT 도입 시 모니터링 도구(JFR `VirtualThreadStart` 등) 확장.
- Sealed 도입은 도메인 패턴 표현을 단순화하지만 hierarchy 변경 시 컴파일러가 강하게 검증 → 마이그 시 점진적 수용.

> 출처: `04-gc/04-zgc-and-shenandoah.md`, `05-threading/04-virtual-threads-and-loom.md`, `06-version-history/README.md`

</details>

### C5. 🟡 각 버전별로 Deprecated/Removed Feature가 실무에 미치는 리스크는?

<details>
<summary>답</summary>

| 버전 | 제거/Deprecated | 실무 리스크 |
|---|---|---|
| 9 | `sun.misc.Unsafe` 캡슐화 시작, Applet/JNLP deprecated | reflection-heavy 라이브러리 다수 깨짐 |
| 11 | Java EE 모듈(`javax.xml.bind`, `javax.activation`) 제거 | 별도 dependency 추가 필요(`jakarta.xml.bind-api`) |
| 14 | CMS GC 제거 | CMS 운영 중이던 서비스 강제 마이그 |
| 15 | Nashorn JavaScript 엔진 제거 | JS 임베딩 서비스 GraalJS로 이동 |
| 17 | RMI activation, Security Manager deprecated | 보안 정책 재설계 필요 |
| 21 | Thread.stop/suspend/resume 제거 | 옛 스레드 제어 코드 마이그 |

**리스크 관리 패턴**:
1. **dependency 호환성 매트릭스**를 사전 확인 (Spring Boot starter는 버전 호환표 명확).
2. **`-Xlint:deprecation` + 코드 정적 분석**으로 사용처 파악.
3. **canary 배포** 후 메트릭 비교.
4. **migration 가이드** (Oracle/Adoptium 공식 문서)를 따라 단계 진행.

> 출처: `06-version-history/README.md`

</details>

### C6. 🟡 LTS(Long Term Support) 버전 선택 전략과 실제 서비스 운영에서의 고려사항은?

<details>
<summary>답</summary>

**LTS 주기**: 약 2년마다. 8(2014) → 11(2018) → 17(2021) → 21(2023) → 25(2025 예정).

**선택 기준**:
1. **벤더 지원 기간**: Oracle 8년, Adoptium/Eclipse Temurin은 더 김. 회사의 SLA와 맞는지.
2. **에코시스템 호환성**: Spring Boot 3는 17+, Spring Boot 2는 8/11. 핵심 framework가 어느 LTS를 요구하는지.
3. **GC 선택지**: 21이 G1/ZGC/Gen-ZGC 모두 production. 17은 ZGC까지.
4. **VT 사용 여부**: 21+ 필요.
5. **마이그 비용**: 8→11보다 8→17이 어렵고, 8→21이 더 어렵지만 한 번에 가는 게 총비용 적을 수 있음.

**운영 고려**:
- **JDK 배포본 선택**: Oracle JDK(상용 라이선스 검토 필요), Temurin/Corretto/Zulu(무료).
- **컨테이너 베이스 이미지**: distroless + Temurin/Corretto가 표준.
- **회사 표준화**: 100대 서비스에 LTS 두 개(예: 17 + 21) 정도가 한계. 그 이상 분산되면 운영 불가능.
- **마이그 캘린더**: LTS 끝나기 6~12개월 전 다음 버전 검증 시작.

> 출처: `06-version-history/README.md`

</details>

### C7. 🟡 버전 업그레이드 시 호환성 이슈와 이를 해결한 실전 사례는?

<details>
<summary>답</summary>

**8 → 17 마이그의 단골 이슈**:

| 이슈 | 원인 | 해결 |
|---|---|---|
| `IllegalAccessException` on `setAccessible` | strong encapsulation | `--add-opens java.base/java.lang=ALL-UNNAMED` 임시. 장기적 reflection 제거 |
| `NoClassDefFoundError: javax/xml/bind/...` | Java EE 모듈 제거(11) | `jakarta.xml.bind-api` 의존 추가 |
| `sun.misc.Unsafe` 차단 | 캡슐화 강화 | `VarHandle`로 교체 |
| `ClassCastException` after class redef | JIT speculation 깨짐 | dependency 버전 통일 |
| GC log 포맷 변경(9+) | Unified Logging | `-Xlog:gc*` 새 문법 |
| Default GC 변경 | Parallel → G1 | 옵션 명시 또는 G1 전제 튜닝 |
| `String.intern` 동작 차이 | StringTable 크기 변경 | `-XX:StringTableSize` 조정 |

**실전 절차**:
1. **빌드** 호환성 먼저: maven/gradle을 새 JDK로 컴파일 → 컴파일 에러 정리.
2. **테스트 환경**에서 dependency 호환 확인.
3. **JFR로 baseline 캡처** (8에서 1주일치).
4. **canary 배포** (한 인스턴스만 새 JDK) → 메트릭 비교.
5. **롤백 절차** 준비.
6. **점진 확대** 후 전체 전환.

> 출처: `06-version-history/README.md`, `10-ops-scenarios/00-real-world-cases.md`

</details>

### C8. 🔴 최신 자바 버전의 Virtual Thread(프로젝트 Loom) 도입이 서버 아키텍처에 미치는 영향은?

<details>
<summary>답</summary>

**근본 변화**: OS thread 1개에 수천 VT를 swap-in/out. blocking I/O 만나면 VT만 unmount, carrier thread는 다른 VT 실행 → **sync 코드로 수만 동시성**.

**서버 아키텍처 영향**:

1. **Thread pool 사이즈 가정 붕괴**:
   - 옛: thread = OS 자원. pool 200 정도.
   - 신: VT 수만 개 가능. **pool 사이즈는 더 이상 동시성 한계가 아님**.
   - Connection pool은 여전히 DB 부하로 한계가 있음 → 이게 새 bottleneck.

2. **Reactive 프레임워크 의미 약화**:
   - WebFlux/Reactor의 주 동기였던 "non-blocking으로 동시성↑"가 sync + VT로 풀림.
   - 새 프로젝트는 sync + VT가 단순.
   - 기존 reactive 자산이 큰 곳은 유지 — operator-rich pipeline은 여전히 유효.

3. **모니터링 변화**:
   - VT는 OS thread처럼 안 보임 → JFR `VirtualThreadPinned`, `VirtualThreadSubmitFailed` 이벤트로 모니터.
   - Stack trace는 자연스러움 (옛 reactive처럼 끊기지 않음).

4. **Pinning 함정**:
   - `synchronized` 안 blocking I/O → VT가 carrier에 박혀 unmount 못 함.
   - JEP 491(JDK 25 예정)에서 해소. 그 전엔 `ReentrantLock` 사용.

5. **Connection pool 재산정**:
   - 옛 가정: pool = thread = 동시성 한계.
   - 새 가정: VT가 수만이지만 DB connection 1개당 1개만 점유. pool 100 두고 5만 VT가 차례로 사용.
   - HikariCP, R2DBC 등 driver 호환성 점검 필요.

6. **ThreadLocal 폭증**:
   - VT마다 ThreadLocal 인스턴스 → 메모리 비례 증가.
   - **ScopedValue**(JDK 21 preview)로 대체 권장.

7. **Spring 3.2+**: `spring.threads.virtual.enabled=true` 한 줄로 Tomcat/Servlet 처리를 VT로.

> 출처: `05-threading/04-virtual-threads-and-loom.md`

</details>

---

## Track D — OOP 설계 원칙 (8문)

### D1. 🟡 객체지향 설계 원칙(SOLID 등) 중 본인이 가장 중요하게 생각하는 원칙과, 이를 실제 코드 및 시스템 설계에 어떻게 적용했는지 구체적으로 설명해보세요.

<details>
<summary>답</summary>

**가장 중요: DIP (Dependency Inversion Principle)**.
- 이유: SRP/OCP/LSP/ISP 모두 결국 "변하지 않는 추상에 의존하고 변하는 구체는 갈아낄 수 있게" 라는 DIP의 변주.
- DIP가 잡히면 테스트(mock 주입), 확장(새 구현 추가), 마이그(구현 교체) 모두 가능.

**적용 예 — 결제 도메인**:
```java
// domain (의존 X)
public interface PaymentGateway {
    PaymentResult charge(Money amount, Card card);
}

// application (도메인에만 의존)
public class CheckoutService {
    private final PaymentGateway gateway;   // 인터페이스에 의존
    // ...
}

// infrastructure (구체 구현)
public class StripeGateway implements PaymentGateway { ... }
public class TossGateway   implements PaymentGateway { ... }
```

이 구조의 효과:
- **테스트**: `FakePaymentGateway`로 단위 테스트.
- **확장**: Toss 추가는 새 구현만, application/domain 코드 0 수정 → OCP까지 동시 만족.
- **롤백**: 장애 시 인터페이스 구현만 swap.

> 출처: `oop/03-solid-principles/`

</details>

### D2. 🔴 SRP, OCP, DIP 등 각 원칙이 대규모 시스템에서 충돌할 때의 트레이드오프 사례는?

<details>
<summary>답</summary>

**충돌 시나리오**:

1. **SRP vs OCP**:
   - SRP: 한 클래스는 한 책임. → 클래스 잘게 쪼갬.
   - OCP: 새 기능 추가는 기존 코드 수정 X → 인터페이스 + 다형성.
   - 충돌: 책임을 잘게 쪼개면 변경 시 여러 인터페이스 동시 수정 필요 → OCP가 깨질 수 있음.
   - 트레이드오프: 도메인 변경 빈도가 잦은 영역은 OCP를 좀 양보(클래스 한 곳 수정), 안정적 영역은 SRP 강하게.

2. **DIP vs YAGNI**:
   - DIP: 인터페이스 도입.
   - YAGNI: 필요해질 때까지 미루기.
   - 충돌: 모든 구체에 인터페이스를 미리 도입하면 1:1 인터페이스 폭증.
   - 트레이드오프: **외부 시스템 경계**(DB, 외부 API, 외부 큐)는 DIP 필수. 도메인 내부는 1:1이면 인터페이스 안 만들고 구체 클래스 그대로.

3. **ISP vs 인터페이스 단순성**:
   - ISP: 클라이언트별로 작은 인터페이스.
   - 충돌: 인터페이스 분할이 너무 잘면 callsite마다 wiring 폭증.
   - 트레이드오프: "한 가지 일을 하는" 자연스러운 경계까지만.

**MSA에서의 특수 충돌**:
- DIP를 너무 강하게 → 마이크로서비스 간 인터페이스 추상화가 분산 시스템 복잡도와 충돌.
- 해결: bounded context 단위로 DIP 유지, 서비스 간 통신은 schema(Protobuf/Avro)로.

> 출처: `oop/03-solid-principles/`, `oop/05-architecture-patterns/`

</details>

### D3. 🟡 객체지향 설계 원칙 위반이 실무에서 발생시킨 장애 사례와 해결 방법은?

<details>
<summary>답</summary>

**사례 1 — LSP 위반**: `Square extends Rectangle`. Square가 setWidth 시 height도 바꿔 LSP 깬다. → 호출자가 "사각형이니 width/height 독립적"이라 가정한 곳에서 invariant 깨짐.
- 장애: 면적 계산 캐시가 한 면 변경 시 양쪽 다 무효화 필요한데 한쪽만 무효화 → 잘못된 가격 계산.
- 해결: `Shape` 인터페이스로 변경. Square/Rectangle은 형제 관계.

**사례 2 — DIP 위반**: Service가 구체 `MySqlRepository`에 직접 의존.
- 장애: DB 마이그(MySQL → PostgreSQL) 시 Service 코드 50군데 수정.
- 해결: `OrderRepository` 인터페이스 + 구현 swap. 마이그 시 새 구현체만 추가.

**사례 3 — SRP 위반**: `UserService`가 인증·프로필·결제 다 처리.
- 장애: 결제 모듈 변경이 인증 테스트를 깨뜨림. 한 곳 수정에 광범위 회귀.
- 해결: `AuthService`, `ProfileService`, `PaymentService`로 분리.

**사례 4 — OCP 위반**: 새 할인 정책 추가 시 `DiscountCalculator` 안 if-else 추가.
- 장애: 신규 정책 출시마다 기존 정책 회귀 테스트 필요. 배포 사고.
- 해결: `DiscountPolicy` 인터페이스 + 구현체 + Spring `List<DiscountPolicy>` 주입.

> 출처: `oop/03-solid-principles/`

</details>

### D4. 🔴 DDD, Clean Architecture 등 현대 아키텍처 패턴과 객체지향 원칙의 접점은?

<details>
<summary>답</summary>

**Clean Architecture의 본질** = DIP를 시스템 전체에 적용한 형태.
```
[Entities (도메인)]   ← 가장 안쪽, 외부 의존 0
       ↑ depends
[Use Cases]
       ↑
[Interface Adapters (Controller, Presenter, Gateway impl)]
       ↑
[Frameworks & Drivers (Spring, JDBC, Web)]
```
의존성은 **항상 안쪽으로만**. DIP가 시스템 레벨로 확장.

**DDD의 본질** = SRP + Bounded Context.
- Aggregate: SRP의 도메인 적용 (한 aggregate는 한 invariant).
- Repository: DIP (도메인이 인터페이스, infra가 구현).
- Domain Event: OCP (이벤트 발행으로 새 핸들러 추가 가능).
- Value Object: 불변·동치성 → 객체지향의 "값"을 제대로 표현.

**OOP 원칙과의 맵핑**:
| 패턴 | 핵심 OOP 원칙 |
|---|---|
| Entity / Aggregate | SRP, encapsulation |
| Repository | DIP |
| Domain Service | SRP |
| Domain Event | OCP, observer |
| Hexagonal Port-Adapter | DIP (port는 도메인이 정의, adapter가 구현) |
| Use Case | SRP (한 use case = 한 시나리오) |

**접점 한 줄**: Clean/DDD 같은 패턴은 **SOLID를 시스템 구조에 끌어올린 적용 방식**.

> 출처: `oop/05-architecture-patterns/`

</details>

### D5. 🟡 테스트 코드 작성 시 객체지향 원칙이 어떻게 반영되는지 구체적 예시는?

<details>
<summary>답</summary>

테스트 가능성은 **DIP의 결과**. 테스트 어려운 코드 = DIP 안 지킨 코드.

**구체 예시**:

```java
// 나쁨: SRP·DIP 위반. DB·시계·외부 API 다 직접 호출.
class OrderService {
    public void placeOrder(Order o) {
        long now = System.currentTimeMillis();             // ← 시계 직접
        Connection conn = DriverManager.getConnection(...); // ← DB 직접
        HttpClient.send("...payment-api...");               // ← API 직접
    }
}
// 테스트 어려움: DB 띄우고, 외부 API mock 서버 띄우고, 시계 못 고정.

// 좋음: DIP 적용. 추상에 의존.
class OrderService {
    private final OrderRepository repo;
    private final PaymentGateway gateway;
    private final Clock clock;

    public void placeOrder(Order o) {
        long now = clock.millis();
        repo.save(o);
        gateway.charge(o.total(), o.card());
    }
}
// 테스트 쉬움: Fake 구현체 주입.
@Test void placeOrder_charges_payment() {
    var repo = new InMemoryOrderRepo();
    var gw   = new FakePaymentGateway();
    var clock = Clock.fixed(Instant.parse("2026-05-17T00:00:00Z"), UTC);
    new OrderService(repo, gw, clock).placeOrder(order);
    assertThat(gw.chargedAmount()).isEqualTo(order.total());
}
```

**원칙별 반영**:
- **DIP**: 인터페이스 주입 → mock/fake 가능.
- **SRP**: 한 책임이면 테스트 한 가지만 검증 → 테스트 짧음.
- **OCP**: 새 케이스는 새 테스트 클래스 추가, 기존 수정 X.
- **LSP**: Fake가 진짜처럼 동작해야 → contract test로 검증.

> 출처: `oop/03-solid-principles/`, `oop/06-testing/`

</details>

### D6. 🟡 SOLID 원칙을 적용한 리팩토링 전후의 코드 비교와 성능/유지보수성 변화는?

<details>
<summary>답</summary>

**Before — 모든 원칙 위반**:
```java
class ReportService {
    void generate(String type, User user, OutputStream out) {
        // SRP/OCP/DIP 다 위반
        Connection c = DriverManager.getConnection(...);   // 직접 DB
        List<Data> data = c.createStatement()
            .executeQuery("SELECT ...").stream()... ;
        if (type.equals("pdf")) {
            // 50줄 PDF 생성 인라인
        } else if (type.equals("excel")) {
            // 50줄 Excel 생성 인라인
        } else if (type.equals("csv")) { ... }
        // 새 포맷 = 메서드 안 수정
    }
}
```

**After — SOLID 적용**:
```java
interface DataSource { List<Data> fetch(User u); }
interface ReportRenderer { void render(List<Data> data, OutputStream out); }

class ReportService {                                    // SRP: 조정만
    private final DataSource source;
    private final Map<String, ReportRenderer> renderers; // OCP: 새 포맷 = 새 구현

    void generate(String type, User user, OutputStream out) {
        renderers.get(type).render(source.fetch(user), out);
    }
}
class PdfRenderer implements ReportRenderer { ... }      // SRP
class ExcelRenderer implements ReportRenderer { ... }
```

**변화**:
| 지표 | Before | After |
|---|---|---|
| 새 포맷 추가 | 메서드 수정, 회귀 위험 | 새 클래스 추가만 (OCP) |
| 단위 테스트 | DB+파일 시스템 필요 | Fake DataSource로 충분 (DIP) |
| 코드 크기 | 한 메서드 200줄 | 클래스 5개 × 40줄 |
| 성능 | 비슷 (JIT 인라인이 충분) | 비슷 |

성능은 거의 동일 — SOLID는 **유지보수성 + 변경 비용** 개선이 본질. 단, hot path에 너무 많은 다형성을 넣으면 megamorphic call로 인라인 실패 → SOLID와 hot path 최적화는 trade-off.

> 출처: `oop/03-solid-principles/`, `03-execution-engine/05-inlining-and-ic.md`

</details>

### D7. 🔴 실제 서비스에서 OOP와 FP(함수형 프로그래밍) 혼용 사례와 그 장단점은?

<details>
<summary>답</summary>

**혼용 패턴**:
1. **객체로 구조, 함수로 연산**:
   - 도메인 모델은 OOP (`Order`, `Customer` 클래스).
   - 컬렉션 변환·파이프라인은 Stream/lambda.
   ```java
   List<OrderSummary> summaries = orders.stream()
       .filter(Order::isPaid)
       .map(o -> new OrderSummary(o.id(), o.total()))
       .toList();
   ```

2. **불변 + Record (FP의 값 개념을 OOP에 흡수)**:
   - `record OrderSummary(...)` — equals/hashCode 자동, 불변.
   - DTO/Value Object에 자연스러움.

3. **Sealed + Pattern matching (대수적 자료형)**:
   ```java
   sealed interface Result<T> permits Ok, Err {}
   Result<Order> r = service.placeOrder(...);
   String msg = switch (r) {
       case Ok<Order> ok   -> "Created: " + ok.value().id();
       case Err<Order> err -> "Failed: " + err.reason();
   };
   ```

4. **함수형 코어 + 명령형 셸**: 순수 함수로 비즈니스 로직, 외부 effect(DB/HTTP)는 가장자리에서.

**장점**:
- 도메인 표현력↑ (record, sealed, pattern matching).
- 컬렉션 변환 짧고 명확.
- 불변성으로 동시성 안전.

**단점**:
- 학습 곡선 (팀 차이).
- Stream의 디버깅 어려움(`lambda$mtd$0`).
- Hot path에서 Stream의 boxing/iterator 비용.
- 두 패러다임이 섞이면 코드 스타일 일관성 깨질 위험 — 팀 가이드라인 필요.

> 출처: `oop/04-oop-vs-fp/`, `06-version-history/README.md`

</details>

### D8. 🔴 객체지향 설계 원칙이 MSA 환경에서 어떻게 적용/변형되는지 설명해보세요.

<details>
<summary>답</summary>

**MSA에서의 변형**:

1. **SRP → 마이크로서비스 단위**: "한 서비스는 한 비즈니스 capability". 모놀리식의 클래스 단위 SRP가 서비스 단위로 올라감.

2. **DIP → API contract**:
   - 서비스 간 통신은 직접 클래스 참조 불가 → REST/gRPC/Kafka contract.
   - 인터페이스의 역할을 **OpenAPI/Protobuf schema**가 대체.
   - "도메인이 schema를 정의, 구현이 따른다"는 의미에서 DIP의 분산 버전.

3. **OCP → versioning**:
   - 새 기능 추가는 기존 endpoint 변경 X → v2 endpoint.
   - schema evolution(Avro/Protobuf의 backward compatibility).

4. **LSP → contract test**:
   - 서비스 구현 교체 시 contract test가 동치 보장.

5. **ISP → small APIs**:
   - 한 서비스가 노출하는 endpoint를 client-specific하게.
   - BFF(Backend for Frontend) 패턴.

**MSA만의 추가 원칙**:
- **Bounded Context** (DDD에서 차용): 서비스 경계 = 도메인 경계.
- **Eventual Consistency**: 분산 트랜잭션 회피, 이벤트로 동기화.
- **자율성 (Autonomy)**: 한 서비스가 다른 서비스의 DB를 직접 보지 않음.

**충돌과 트레이드오프**:
- 너무 작은 서비스 → 분산 복잡도 폭증 (network, observability, ops).
- 너무 큰 서비스 → 모놀리식의 단점 재현.
- 적정선: "팀 1개가 운영 가능한 단위" (2-pizza team).

**객체지향 원칙이 살아남는 곳**: 각 서비스 내부의 도메인 모델은 여전히 SOLID 적용. 서비스 경계만 schema로.

> 출처: `oop/05-architecture-patterns/`, `00-overview/`

</details>

---

## Track E — 동시성 & 스레드 (8문)

### E1. 🟡 JVM에서 스레드 관리 및 동시성 제어(synchronized, volatile, java.util.concurrent 등) 방식과, 실무에서 발생할 수 있는 동시성 이슈 및 해결 경험을 설명해보세요.

<details>
<summary>답</summary>

**JVM의 동시성 도구 스택** (가벼움 → 무거움):

| 도구 | 무엇 | 비용 |
|---|---|---|
| `volatile` | 가시성 + happens-before | 거의 무료 (memory barrier만) |
| `Atomic*` | CAS 기반 원자 연산 | 가벼움 (lock-free) |
| `synchronized` | mutex + visibility + atomicity | 경합 없으면 가벼움(biased/lightweight), 경합 시 무거움(heavyweight) |
| `ReentrantLock` | synchronized 대안 + interruptible/tryLock | synchronized 비슷 |
| `StampedLock` | optimistic read + write | 최적화된 read-heavy 케이스 |
| `j.u.c.locks.LockSupport` + AQS | 기반 framework | 위 도구들의 토대 |
| Concurrent collection | `ConcurrentHashMap`, `CopyOnWriteArrayList` | 자료구조 자체로 동시성 |
| `Executor`, `Future`, `CompletableFuture` | 비동기 태스크 추상화 | 풀 운영 비용 |

**실무 이슈와 해결**:
1. **race condition on counter**: `int count++` → `AtomicInteger.incrementAndGet`.
2. **stale read**: `boolean stopped` → `volatile boolean stopped`.
3. **deadlock**: 두 lock 순서 다름 → 항상 같은 순서로 acquire 또는 `tryLock` + timeout.
4. **thread leak**: ExecutorService shutdown 안 함 → `@PreDestroy`에서 shutdown + awaitTermination.
5. **livelock**: 두 thread가 양보만 함 → backoff + jitter.
6. **DB connection pool starvation**: hot endpoint가 모든 conn 점유 → pool 사이즈 + timeout 조정.

> 출처: `05-threading/01-jmm-and-happens-before.md`, `02-memory-barriers.md`, `03-synchronized-and-mark-word.md`

</details>

### E2. 🟡 JVM의 스레드 스케줄링 방식과 OS 레벨 스레드와의 차이는?

<details>
<summary>답</summary>

**JDK 21 이전 (Platform Thread만)**:
- Java `Thread` = OS thread 1:1 매핑.
- 스케줄링은 **OS 커널**이 함 (자바는 우선순위 hint만 줄 뿐).
- 컨텍스트 스위치 비용은 OS 수준 (수 μs).
- 동시 thread 수는 RAM × thread stack(`-Xss`)로 제한. 보통 1만 미만.

**JDK 21+ (Virtual Thread)**:
- VT는 **JVM이 스케줄링** (ForkJoinPool의 carrier).
- VT의 컨텍스트 스위치 = 자바 객체 swap (수십 ns~수백 ns).
- 동시 VT 수는 메모리 한도까지(수십만 가능).
- blocking I/O 만나면 VT unmount → carrier는 다른 VT mount.

**차이 요약**:
| 항목 | Platform Thread | Virtual Thread |
|---|---|---|
| 매핑 | 1:1 OS thread | N:M (carrier에 mount) |
| 스케줄러 | OS kernel | JVM |
| 생성 비용 | 큼 (수 MB) | 작음 (수 KB) |
| 컨텍스트 스위치 | μs 단위 | ns 단위 |
| 동시 가능 수 | 수천 | 수십만 |
| 적합 워크로드 | CPU-bound | I/O-bound |

> 출처: `05-threading/04-virtual-threads-and-loom.md`

</details>

### E3. 🟡 synchronized, ReentrantLock, StampedLock 등 동기화 방식의 내부 동작과 성능 차이는?

<details>
<summary>답</summary>

**synchronized**:
- JVM 내장. Mark Word의 lock 상태 비트 사용.
- 진화: biased → lightweight (CAS) → heavyweight (OS monitor).
- 짧은 critical section은 거의 항상 lightweight에서 끝남.
- 단점: interruptible 아님, tryLock 없음, fairness 옵션 없음.

**ReentrantLock**:
- `java.util.concurrent.locks` 패키지. AQS(AbstractQueuedSynchronizer) 기반.
- 기능: `lock`, `tryLock(timeout)`, `lockInterruptibly`, fair 옵션.
- 성능: synchronized와 비슷. 미세 우위는 워크로드별로.
- 단점: try-finally로 unlock 명시 필요(잊으면 영구 lock).

**StampedLock**:
- read-heavy 워크로드 최적화. Optimistic read 지원.
- 동작:
  ```java
  long stamp = lock.tryOptimisticRead();
  // ... read fields
  if (!lock.validate(stamp)) {
      stamp = lock.readLock();    // optimistic 실패 → 정식 read lock
      try { ... } finally { lock.unlockRead(stamp); }
  }
  ```
- 장: optimistic이 성공하면 lock 자체 안 잡음 → 최고 성능.
- 단: reentrancy X, condition X, deadlock 회피 까다로움.

**성능 차이 한 줄**: 짧은 critical section + 낮은 경합 = synchronized. 복잡한 패턴(timeout, interruptible) = ReentrantLock. read-heavy = StampedLock.

> 출처: `05-threading/03-synchronized-and-mark-word.md`

</details>

### E4. 🟢 volatile 키워드의 메모리 가시성 보장 방식과 한계는?

<details>
<summary>답</summary>

**보장**:
- **가시성**: write가 즉시 main memory로 flush, read는 main memory에서. 다른 스레드가 옛 캐시 값 보지 않음.
- **happens-before**: volatile write는 그 뒤의 같은 변수 read보다 happens-before. write 이전의 모든 쓰기가 read 이후에 보임.
- **재정렬 금지**: volatile 변수 주변의 명령 재정렬 제한 (memory barrier 삽입).

**구현**:
- x86: write 후 store barrier(보통 lock 접두사 없는 mov로 충분). read는 추가 비용 거의 없음.
- ARM: 더 강한 barrier 필요(dmb).

**한계**:
- **atomicity 없음**: `count++` = read + add + write 3단계. 다른 스레드가 사이에 끼면 race. → `AtomicInteger.incrementAndGet`.
- **복합 invariant 못 보호**: 두 필드의 일관성 보장 X. → synchronized 또는 lock.
- **무한 루프 변수**:
  ```java
  while (!stopped) { ... }  // stopped를 volatile 안 두면 JIT가 캐시 → 영원 루프
  ```
  이 케이스가 volatile의 대표 용도.

**한 줄**: volatile = "단일 read/write의 가시성 + 순서 보장". 그 이상의 atomicity나 복합 mutate는 다른 도구 필요.

> 출처: `05-threading/01-jmm-and-happens-before.md`, `02-memory-barriers.md`

</details>

### E5. 🟡 java.util.concurrent 패키지의 주요 클래스별(Executor, Future, CompletableFuture) 동작 원리와 실전 적용 사례는?

<details>
<summary>답</summary>

**Executor / ExecutorService**:
- thread pool 추상화. `submit(Runnable/Callable)` → 풀의 thread가 실행.
- 구현: `ThreadPoolExecutor`(코어/맥스/큐/스레드팩토리), `ScheduledThreadPoolExecutor`(주기).
- 실전: `Executors.newFixedThreadPool(N)` 같은 팩토리 대신 **ThreadPoolExecutor 직접 생성 권장**(unbounded queue 함정 회피).

**Future / FutureTask**:
- 비동기 결과 표현. `get()`은 blocking. `isDone()`/`get(timeout)`도 가능.
- 한계: chaining 어려움 → CompletableFuture로 발전.

**CompletableFuture**:
- 비동기 + 조합 가능.
  ```java
  CompletableFuture.supplyAsync(() -> fetchUser(id))
      .thenApply(user -> enrich(user))
      .thenCompose(enriched -> CompletableFuture.supplyAsync(() -> save(enriched)))
      .exceptionally(ex -> fallback(ex));
  ```
- `thenApply` / `thenCompose` / `thenCombine` / `allOf` / `anyOf`.
- 함정: `get()` 잘못 쓰면 풀 스레드 starve. `join()`도 마찬가지.
- 실전: 외부 API 병렬 호출 + aggregation. `allOf` + `thenApply`로 fan-out/fan-in.

**Virtual Thread 시대**:
- VT가 stable해지면 `CompletableFuture.supplyAsync` 같은 비동기 표현이 덜 필요해짐 → sync 코드 + `Thread.ofVirtual().start(...)` 또는 `Executors.newVirtualThreadPerTaskExecutor()`.

> 출처: `05-threading/04-virtual-threads-and-loom.md`

</details>

### E6. 🟡 데드락, 라이브락, 스타베이션 등 동시성 장애의 실전 발생 사례와 해결 전략은?

<details>
<summary>답</summary>

**Deadlock**: 두 thread가 서로의 lock을 기다림.
- 사례: TransferService가 A→B 송금 시 (accountA lock, accountB lock), 다른 thread가 B→A 시 (accountB lock, accountA lock) → 데드락.
- 해결:
  1. **항상 같은 순서로 lock acquire** (id 오름차순 등).
  2. `tryLock(timeout)` + 실패 시 backoff.
  3. lock-free 자료구조(`ConcurrentHashMap`)로 회피.
  4. 진단: `jstack <pid>` 또는 `jcmd <pid> Thread.print` → `Found deadlock` 메시지.

**Livelock**: 두 thread가 양보만 반복하며 진행 안 됨.
- 사례: 두 thread가 lock을 잡고 충돌 감지 → 둘 다 즉시 양보 → 다시 잡음 → 다시 양보. 무한.
- 해결: **backoff + jitter**. 양보 시간을 random하게.

**Starvation**: 한 thread가 자원을 영원히 못 받음.
- 사례: 우선순위 낮은 thread가 fair 옵션 없는 lock에서 영영 못 잡음.
- 해결: `new ReentrantLock(true)` 같은 fair lock, 또는 priority 재설계.

**진단 도구**:
- `jstack` / `jcmd Thread.print`: 스레드 dump → BLOCKED 상태 + 어떤 lock을 기다리는지.
- JFR `JavaMonitorWait` / `JavaMonitorEnter` 이벤트.
- `-XX:+PrintConcurrentLocks`.

> 출처: `05-threading/03-synchronized-and-mark-word.md`, `10-ops-scenarios/00-real-world-cases.md`

</details>

### E7. 🔴 Fork/Join 프레임워크와 Parallel Stream의 내부 동작 차이와 실무 적용 시 고려사항은?

<details>
<summary>답</summary>

**Fork/Join 프레임워크**:
- `ForkJoinPool` + `RecursiveTask/RecursiveAction`.
- 핵심: **work-stealing**. idle worker가 다른 worker의 큐 뒤에서 작업 훔침.
- 사용: 큰 문제를 재귀적으로 분할 → 합치기.
  ```java
  class SumTask extends RecursiveTask<Long> {
      protected Long compute() {
          if (small) return directSum();
          var left = new SumTask(...); left.fork();
          var right = new SumTask(...);
          return right.compute() + left.join();
      }
  }
  ```

**Parallel Stream**:
- 내부적으로 **공용 ForkJoinPool**(`ForkJoinPool.commonPool()`)을 사용.
- `stream.parallel().map(...).reduce(...)` 같은 자동 분할.
- 분할 단위는 spliterator가 결정.

**실무 고려**:
1. **공용 풀 공유**: parallel stream 여러 곳에서 동시 사용 → 한 곳의 느린 작업이 다른 곳까지 지연. 격리 필요하면 `forkJoinPool.submit(() -> stream.parallel()...).get()` 패턴.
2. **blocking I/O 금지**: ForkJoinPool은 CPU-bound 가정. blocking I/O 두면 풀 starvation. → VT나 별도 풀 사용.
3. **분할 비용 vs 이득**: 작은 컬렉션은 parallel이 더 느림. heuristic: 수십만+ 요소, 변환 비용 큼.
4. **결합성 (associativity)**: reduce 연산은 결합 가능해야. `(a+b)+c == a+(b+c)`.
5. **stateful 연산 금지**: `forEach`에서 외부 변수 mutate → race.

**Virtual Thread 시대**:
- I/O-bound는 VT가 더 자연스러움. parallel stream은 여전히 CPU-bound에 유효.

> 출처: `05-threading/04-virtual-threads-and-loom.md`

</details>

### E8. 🔴 JVM에서 스레드 Dump 분석을 통한 병목 진단 및 해결 경험은?

<details>
<summary>답</summary>

**Thread dump 수집**:
```bash
jcmd <pid> Thread.print            # 표준
jstack -l <pid>                    # lock 정보 포함
kill -3 <pid>                      # SIGQUIT (stdout으로)
```

**dump의 핵심 정보**:
- 각 thread의 상태: `RUNNABLE` / `BLOCKED` / `WAITING` / `TIMED_WAITING`.
- stack trace.
- 어떤 lock을 보유 중 (`holding`) / 어떤 lock 기다림 (`waiting on`).
- `Found deadlock` 자동 감지 섹션.

**병목 진단 패턴**:

1. **CPU 100% 단일 스레드**:
   - RUNNABLE 상태 + 같은 메서드가 dump 여러 번에 걸쳐 반복.
   - 의심: 무한 루프, 비효율 알고리즘. JFR로 CPU sampling 추가.

2. **대량 thread가 한 lock 대기**:
   - BLOCKED 상태 thread 수십~수백 + 공통 `waiting on <0x...>`.
   - 의심: 잘못된 단일 monitor. CRITICAL section 줄이거나 ReadWriteLock으로 분리.

3. **JDBC pool 대기**:
   - WAITING thread가 `HikariCP - PoolEntry` 류에 대기.
   - 의심: pool 사이즈 부족, 쿼리 느림. pool 사이즈 / DB 인덱스 점검.

4. **GC log와 cross-check**:
   - dump 시각 = GC pause 시각이면 thread 전부 BLOCKED일 수 있음(safepoint).

5. **Deadlock**:
   - `Found 2 deadlocks:` 섹션에서 정확히 어느 thread/lock인지 출력.

**실전 사례 예**:
- 결제 API P99 spike → thread dump 3개 1초 간격 수집 → 모든 dump에서 200 thread가 `Logger.log` 안의 `synchronized` 대기 → 로깅 lib 버전 버그 → 비동기 appender로 교체 → 해결.

> 출처: `05-threading/`, `10-ops-scenarios/00-real-world-cases.md`

</details>

---

## 📚 자료

- 본 챕터는 **00~12 전 챕터의 통합 평가**.
- 답이 부족한 영역은 해당 챕터로 돌아가 본문 + Excalidraw 다이어그램을 다시 살펴라.
- 백지에 그림이 안 그려지면 그 주제는 아직 안 외운 거다.
