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

## 📚 자료

- 본 챕터는 **00~12 전 챕터의 통합 평가**.
- 답이 부족한 영역은 해당 챕터로 돌아가 본문 + Excalidraw 다이어그램을 다시 살펴라.
- 백지에 그림이 안 그려지면 그 주제는 아직 안 외운 거다.
