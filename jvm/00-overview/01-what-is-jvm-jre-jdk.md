# 01. JVM, JRE, JDK — 세 단어를 세 레이어로 분리해 답할 수 있는가

> "JVM이 뭔가요?" 라고 물으면 90%가 "Java를 실행하는 가상 머신"이라고 답한다. 그건 위키피디아 첫 줄이다.
> 진짜 답은 세 레이어다 — **JVMS(명세 PDF)** / **HotSpot·OpenJ9 등 구현체** / **ClassFile(입력 포맷)**. 흔한 혼동은 이 셋을 한 덩어리로 뭉치는 것.
> 그리고 "JRE는 JDK 9에서 사라졌다"는 표현도 부정확하다. **배포 형태**가 사라진 것일 뿐 "실행에 필요한 최소 집합" 이라는 **개념**은 jlink 이미지로 그대로 살아 있다.

---

## 이 문서의 사용법

이 문서는 면접용 마인드맵을 따라 선형으로 펼친 구조다. 학습 순서 = 면접 답변 순서 = 백지에 그리는 순서.

1. **0장 마인드맵을 먼저 외운다** — 루트 한 문장 + 5가지 가지 + 각 가지의 키워드 3개.
2. **1~5장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 정확히 대응.
3. **6장 면접 워크플로우로 검증** — 질문을 보면 어느 가지로 가야 하는지 매핑.
4. **7장 꼬리질문으로 깊이 점검**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"JDK ⊃ JRE ⊃ JVM 의 포함 관계는 단순 트리가 아니라 명세(JVMS) / 구현(HotSpot) / 입력 포맷(ClassFile) 세 레이어의 분리고, 이 분리 자체가 1995년 임베디드 디바이스 제약에서 시작된 'Write Once Run Anywhere' 설계의 핵심이다."**

이 한 문장에서 모든 답변이 출발한다. 어떤 질문이 와도 이 문장부터 말하고 적절한 가지로 분기.

### 5개 가지 — 순서를 외운다

```
                  [ROOT: JDK⊃JRE⊃JVM = 명세/구현/입력 3레이어]
                                    │
       ┌─────────┬──────────────────┼──────────────────┬─────────┐
       │         │                  │                  │         │
      ① WHAT   ② WHY              ③ HOW              ④ 운영    ⑤ 진화
   3중 포함관계  분리 설계 철학    java→libjvm.so    (시니어 진단) (역사)
       │         │                  │                  │         │
       │    ┌────┼────┐         ┌───┼───┐         ┌────┼────┐    │
    JDK     1990s     사용자/    java     dlopen    JDK     dev vs JDK8 →
    JRE     제약      개발자     런처     libjvm    설치형   prod 9 → 11+
    JVM     보안축소  분리       =C코드   JNI_CrVM  vs jlink Container Native
            라이선스                                        Native    Image
            (4가지)
```

### 가지별 핵심 키워드 (각 가지 3개씩만)

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① WHAT 3중 포함관계** | JDK = JRE + 도구 | JRE = JVM + Lib | JVM = ClassLoader/Runtime/Exec/JNI |
| **② WHY 분리 철학** | 1990s 자원제약 | 사용자/개발자 분리 | 보안 표면 + 라이선스 |
| **③ HOW 시동 메커니즘** | java 런처 = C 프로그램 | dlopen(libjvm.so) | JNI_CreateJavaVM → Threads::create_vm |
| **④ 운영 시나리오** | dev = JDK 전체 | prod = jlink/Distroless | jar 4종 (Plain/Fat/Boot/Native) |
| **⑤ 진화 역사** | JDK 8 (rt.jar 단일) | JDK 9 (Module + jlink) | JDK 11+ (별도 JRE 종료) |

### 면접 답변 흐름

> 면접관 질문 → 루트 문장 → 질문에 맞는 가지 1개 선택 → 그 가지의 키워드 3개 순서대로 설명 → 듣는 사람의 관심에 따라 인접 가지로 확장

"JVM/JRE/JDK 차이" → ① WHAT. "왜 분리됐나" → ② WHY. "java 명령은 뭐가 일어나나" → ③ HOW. "prod에 뭐 깔까" → ④ 운영. "JDK 9에서 뭐가 바뀌었나" → ⑤ 진화.

---

## 1. 가지 ①: WHAT — 3중 포함관계와 그 안의 4대 서브시스템

### 1.1 핵심 질문

> "JVM, JRE, JDK 차이를 설명해보세요."

### 1.2 키워드 1 — JDK = JRE + 개발 도구

```
┌─────────────────────────────────────────────────────────────────┐
│ JDK (Java Development Kit)  — 개발자 배포본                       │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ JRE (Java Runtime Environment)  — 실행에 필요한 최소 집합    │  │
│  │                                                           │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │ JVM — bytecode 실행 런타임                            │  │  │
│  │  │   ① ClassLoader  ② Runtime Data Areas                │  │  │
│  │  │   ③ Execution Engine (Interpreter + JIT, ★ GC 별도)  │  │  │
│  │  │   ④ Native Interface (JNI)                           │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  │  + Class Libraries (java.base, java.sql, java.net.http, …)│  │
│  └───────────────────────────────────────────────────────────┘  │
│  + Development Tools                                            │
│     javac, javadoc, jdb, jar, jlink, jpackage,                  │
│     jstack, jmap, jstat, jcmd, jfr, javap, jdeps, ...            │
└─────────────────────────────────────────────────────────────────┘
```

**한 줄 비유**:
- **JVM** = 게임기 본체 (실행만)
- **JRE** = 본체 + 번들 게임팩 (실행 + 라이브러리)
- **JDK** = 본체 + 게임팩 + 개발 키트 (실행 + 라이브러리 + 개발 도구)

**정확한 정의**:
- **JVM**: bytecode를 실행하는 가상 머신. `java` 런처가 `libjvm` 라이브러리를 로드해 띄우는 런타임.
- **JRE**: JVM + 표준 클래스 라이브러리 + 실행 도구(`java`, `keytool`). JDK 8까지는 별도 배포, JDK 9+에서는 `jlink` 이미지로 대체되는 추세.
- **JDK**: JRE 구성 요소 + 개발 도구(`javac`, `jdb`, `jstack`, `jmap` 등).

### 1.3 키워드 2 — 명세 / 구현 / 입력 포맷의 3 레이어

흔한 혼동: "JVM = ClassFile 포맷의 구현체"라고 묶어버리는 것. 정확히는 다음 3 레이어다.

```
┌─────────────────────────────────────────────────────────┐
│  JVMS (The Java Virtual Machine Specification)          │
│  - ClassFile 포맷 (.class 바이트 구조)                    │
│  - 200여 개의 bytecode 명령어 의미론                      │
│  - Runtime Data Areas의 종류 (Heap, Stack, ...)         │
│  - Verifier 검증 규칙                                    │
│  - 동시성 모델 (JMM)                                     │
│                                                         │
│  → "PDF 문서". Oracle이 정의하고 모두가 따라야 함.        │
└────────────────────┬────────────────────────────────────┘
                     │ 구현
        ┌────────────┼────────────┬─────────────┐
        ▼            ▼            ▼             ▼
   ┌─────────┐  ┌─────────┐  ┌──────────┐  ┌──────┐
   │ HotSpot │  │ OpenJ9  │  │ GraalVM  │  │ Zing │
   │ Oracle  │  │ Eclipse │  │ Oracle   │  │ Azul │
   └─────────┘  └─────────┘  └──────────┘  └──────┘
```

- **JVMS**가 "어떤 입력을 받아 어떻게 실행하라"를 정의 — ClassFile 포맷 + bytecode 의미론 + 메모리 영역 종류.
- **GC를 어떻게 구현하라거나, JIT을 어떻게 만들라**는 명세가 안 정한다 → 그래서 HotSpot은 G1/ZGC를, OpenJ9은 Balanced GC를 만들 수 있음.
- **ClassFile은 JVM의 입력 포맷**이지 JVM의 일부가 아님. javac는 ClassFile을 만들고, JVM은 ClassFile을 먹는다.

**구현체 비교**:

| 구현 | 언어 | 만든 곳 | 특징 |
|---|---|---|---|
| **HotSpot** | C++ | Sun → Oracle / OpenJDK | de facto 표준, Template Interpreter + C1/C2 JIT |
| **OpenJ9** | C/C++ | IBM → Eclipse | 메모리 footprint 작음, Cloud-friendly |
| **GraalVM** | Java (JIT) + AOT 빌더 | Oracle Labs | Graal JIT(JVMCI plug-in) + Native Image(SVM) 묶음 |
| **Zing** | C++ | Azul Systems | C4 GC (pauseless), LLVM 기반 JIT |

> **GraalVM은 한 줄 정리 불가** — (1) HotSpot의 JIT을 Java로 작성한 Graal로 교체한 JDK 배포 + (2) JVMCI 인터페이스로 plug-in되는 Graal 컴파일러 + (3) AOT 빌더와 SVM(Substrate VM) 런타임. "GraalVM = HotSpot 대체" 라는 한 줄은 부정확.

### 1.4 키워드 3 — JVM 내부 4대 서브시스템

JVM 박스 안을 열면:

| 번호 | 서브시스템 | 역할 |
|---|---|---|
| ① | **Class Loader Subsystem** | Bootstrap → Platform → Application 위임 모델로 .class 로드/링크/초기화 |
| ② | **Runtime Data Areas** | Heap / JVM Stack / Method Area(Metaspace) / PC / Native Method Stack |
| ③ | **Execution Engine** | Interpreter + JIT(C1/C2). ★ GC는 별도 책임 |
| ④ | **Native Interface (JNI)** | C/C++ 라이브러리와의 통신 채널 |

> 이 4구역은 03번 챕터 ([03-jvm-architecture-bigpicture.md](./03-jvm-architecture-bigpicture.md))에서 깊이 다룬다.

### 1.5 "JVM = 가상 머신"의 진짜 뜻

| 가상 머신의 두 의미 | 설명 | 예시 |
|---|---|---|
| **System VM** | 진짜 하드웨어를 통째로 에뮬레이션 | VMware, QEMU |
| **Process VM** | 한 프로세스 안에서 가상 명령어를 실행 | JVM, CLR, V8 |

**JVM은 Process VM**이다. OS 위에서 그냥 하나의 프로세스로 돈다. Docker는 또 다른 카테고리(OS-level virtualization) — 셋은 같은 축이 아님.

---

## 2. 가지 ②: WHY — 왜 3중으로 분리됐나 (설계 철학)

### 2.1 핵심 질문

> "JVM, JRE, JDK, 개발 도구를 왜 각각 따로 분리하고 다운로드받게 했지? 그냥 하나로 합치는 게 제일 간단하잖아?"

### 2.2 키워드 1 — 1990년대의 물리적 제약

| 항목 | 1995년 | 2024년 |
|---|---|---|
| HDD 가격 | 1GB ≈ $200 | 1GB ≈ $0.02 |
| 가정용 인터넷 | 56kbps 모뎀 | 1Gbps 광 |
| JRE 100MB 다운로드 시간 | ≈ 4시간 | <1초 |

→ 사용자에게 "applet 하나 실행하려고 `javac`/`javadoc`/`jdb`까지 받으라"고 하면 **물리적으로 불가능**. JRE를 ~10MB 수준으로 가볍게 만들어야 했음.

### 2.3 키워드 2 — 사용자 vs 개발자 분리 사고

```
[일반 사용자]                 [개발자]
       │                        │
       ▼                        ▼
  웹브라우저 + JRE          IDE + JDK
  (applet 실행만)           (개발 + 디버깅 + 빌드)
       │                        │
       ▼                        ▼
  10MB 다운로드             80MB+ 다운로드
```

당시 가정: **Java 사용자 수가 개발자 수보다 100배 많다** (브라우저 applet 가정). 그래서 "사용자에게 가벼운 JRE만" 모델이 합리적.

### 2.4 키워드 3 — 보안 표면 + 라이선스

**보안 표면 축소** ("최소 권한 원칙"):
- `javac` 있음 → 악성 코드가 사용자 머신에서 새 클래스 컴파일.
- `jar` 있음 → signed jar 변조 + 재포장.
- `jdb` 있음 → 다른 Java 프로세스에 attach해서 메모리 읽기/수정.

**라이선스/배포 제어** (옛 Sun 시절):
- JRE는 누구나 무료 재배포 가능. JDK는 별도 라이선스 — 일부 상업 사용 제약.
- 게임 회사가 게임에 JRE 끼워 배포 가능, JDK는 못 끼움.

### 2.5 "그럼 지금은 왜 안 합치나?"

JDK 9+에서 합쳐지는 방향으로 가긴 했다 (`jre/` 폴더 사라짐, 별도 JRE 배포 종료). 그런데 **완전히 한 덩어리**로 안 가는 이유:

| 측면 | 합쳤을 때 손해 |
|---|---|
| **컨테이너 이미지 크기** | JDK 전체 ~300MB → 100MB 컨테이너 목표 불가 → 클라우드 비용 ↑ |
| **콜드스타트** | 더 많은 클래스 로딩 → 시동 느림 (FaaS 치명적) |
| **보안 표면** | 운영 컨테이너에 `jdb`, `jaotc` 다 있으면 공격 표면 확대 |
| **메모리 footprint** | 사용 안 하는 모듈도 Metaspace 차지 |
| **임베디드/IoT** | 라즈베리 파이급 디바이스에 200MB+ 부담 |

→ **"한 덩어리 = 편하다"는 dev 머신 한정**. prod / 임베디드 / cloud에서는 **여전히 모듈 분리가 가치 있음**.

### 2.6 분리의 입자가 진화했다

```
옛 분리 (JDK 8까지):              새 분리 (JDK 9+):
━━━━━━━━━━━━━━━━━━━━━              ━━━━━━━━━━━━━━━━━━━━━
디렉토리 레벨 분리                  모듈 레벨 분리
($JAVA_HOME/jre/ vs JDK)          (java.base, java.sql, jdk.compiler, ...)

거친 입자                          미세 조정 가능
"JRE 받기 vs JDK 받기"             "이 모듈을 require할지 선언"
                                  → jlink로 필요한 만큼만 묶음
```

**핵심 통찰**: 분리는 "최소한만 받자"는 1990s 제약이 만들었고, 안 합치는 이유는 그 원칙이 **클라우드·FaaS·임베디드 시대에 더 중요해졌기 때문**. 디렉토리 분리는 사라졌지만 모듈 분리(JPMS)는 강화됐다 — 입자가 더 미세해졌을 뿐, 철학은 동일.

### 2.7 다른 언어와 비교 — 분리가 정답은 아니다

| 언어 | 배포 모델 | 분리 vs 통합 |
|---|---|---|
| **Java / .NET** | SDK / Runtime 분리 (jlink 이미지로 진화) | 분리 + 모듈화 |
| **Go / Rust** | 단일 toolchain → 단일 바이너리 | 통합 (AOT 친화) |
| **Python / Node / Ruby** | 런타임 통합 + 의존성 외부 격리 (venv, npm) | 통합 |
| **C/C++** | 컴파일러 별도, 런타임은 OS 일부(glibc) | 분리 |

**관찰**: VM 기반 + 광범위한 호환성 언어는 분리 + 모듈화, AOT + 단일 바이너리 언어는 통합. **시나리오에 맞춰 결정**될 뿐 "분리가 무조건 옳다"가 아님.

---

## 3. 가지 ③: HOW — `java HelloWorld`가 일으키는 일

### 3.1 핵심 질문

> "java HelloWorld를 입력하면 무엇이 일어나나요?"

### 3.2 키워드 1 — `java`는 JVM이 아니다, 작은 C 런처다

가장 자주 틀리는 답: "java 명령이 JVM이다". **틀렸다**.
- `java` = 작은 C 런처 (수 MB).
- 진짜 JVM = **`libjvm.so` (Linux) / `jvm.dll` (Windows) / `libjvm.dylib` (macOS)** 라는 30MB짜리 공유 라이브러리.
- `find $JAVA_HOME -name "libjvm.*"` 해보면 한 줄 나온다.

런처가 하는 일은 단순하다:
```
1. -Xmx, -classpath 등 인자 파싱
2. libjvm.so 위치 결정 (server / client)
3. dlopen(libjvm.so)  ← 실행 시점에 동적 로드
4. dlsym으로 JNI_CreateJavaVM 함수 포인터 얻기
5. JNI_CreateJavaVM 호출 → 진짜 JVM 시작
6. main 메서드 찾아서 CallStaticVoidMethod 호출
7. 종료 시 DestroyJavaVM
```

### 3.3 키워드 2 — `dlopen`의 본질 (시동 메커니즘)

`dlopen(libjvm.so, RTLD_NOW)` 호출 시 OS가 하는 일:

```
[1] 파일 찾기 (LD_LIBRARY_PATH, /lib, /lib64)
[2] mmap으로 가상 메모리에 매핑 (.text=RX, .data=RW)
[3] 의존성 재귀 로드 (libpthread, libc, libdl)
[4] Relocation — GOT/PLT에 실제 주소 채움
[5] __attribute__((constructor)) 실행
[6] 심볼 테이블 등록 → dlsym으로 검색 가능
[7] 핸들 반환
```

**왜 dlopen 방식인가** (직접 static 링크 대신):

```
[직접 통합 모델 — 가상]                  [현재 모델 — 분리]
━━━━━━━━━━━━━━━━━━━━━━━                  ━━━━━━━━━━━━━━━━━
java = 런처 + JVM 전체 (~30MB)           java 런처 (수MB) + libjvm.so (30MB)
- -client vs -server 옵션 어려움         - 런처가 옵션 파싱 후 적절한 libjvm 선택
- GraalVM 같은 대체 JVM 끼우기 어려움     - GraalVM은 자기 libjvm.so 제공 → 끼움
- 시스템 전체에서 libjvm 공유 못 함       - 여러 java 프로세스가 코드 페이지 공유
```

또한 PIC(`-fPIC`) 코드라서 **여러 프로세스가 같은 `.so`의 코드 페이지를 메모리에서 공유** — 같은 머신에 java 10개 띄워도 libjvm 코드는 1번만 메모리에.

### 3.4 키워드 3 — `JNI_CreateJavaVM` → `Threads::create_vm`

런처가 `JNI_CreateJavaVM`을 호출하면 HotSpot의 진짜 main인 `Threads::create_vm`이 돈다 (`src/hotspot/share/runtime/threads.cpp`):

```
(1) Arguments::parse(args)             — -Xmx, -XX:+UseG1GC 파싱
(2) os::init() / os::init_2()          — 스레드 라이브러리, 신호, 페이지 크기
(3) init_globals()                     — Heap 생성, Bootstrap CL, String/Symbol table
(4) new JavaThread()                   — main 스레드 생성
(5) initialize_java_lang_classes(...)  — java.lang.Thread 인스턴스
(6) call_initPhase1(...)               — java.lang.System.initPhase1()
(7) Service threads 시작               — GC thread, Compiler thread
(8) CompileBroker::compilation_init()  — C1, C2 초기화
(9) main thread를 JNI에 등록 → 리턴
```

그 다음 런처가 main 클래스를 로드하고 `CallStaticVoidMethod`로 사용자 `main()`을 호출한다.

### 3.5 OS별 차이

| OS | 확장자 | 로딩 API | 헤더 |
|---|---|---|---|
| **Linux** | `.so` | `dlopen`, `dlsym`, `dlclose` | `<dlfcn.h>` |
| **macOS** | `.dylib` | `dlopen` 등 (POSIX 호환) | `<dlfcn.h>` |
| **Windows** | `.dll` | `LoadLibrary`, `GetProcAddress` | `<windows.h>` |

### 3.6 운영 함정

**흔한 에러**: `error while loading shared libraries: libjvm.so`

```bash
$ find / -name "libjvm.so" 2>/dev/null     # 어디 있나
$ ldd $(which java)                         # java가 의존하는 .so
$ echo $LD_LIBRARY_PATH                     # 동적 링커 경로
$ strace -e openat java -version 2>&1 | grep libjvm   # 어디서 찾으려 했나
```

**`LD_PRELOAD`** — JVM 운영에서 흔히 쓰는 패턴:
```bash
LD_PRELOAD=/usr/lib/libjemalloc.so java -jar app.jar
```

### 3.7 흔한 오해 정리

| 오해 | 사실 |
|---|---|
| "`java`가 JVM이다" | `java`는 런처. JVM은 `libjvm.so` 안에 있음 |
| "dlopen이 JVM 자체 기능" | POSIX 표준 함수, `libdl.so`에서 제공 |
| "정적 링크가 항상 빠르다" | 시동은 약간 빠를 수 있지만 메모리 공유 못 함 |
| "JVM 한 번 띄우면 libjvm 메모리 30MB 통째로 잡힘" | PIC + 페이지 공유 → 여러 프로세스가 코드 페이지 공유 |

---

## 4. 가지 ④: 운영 — dev vs prod에서 실제로 무엇이 도나

### 4.1 핵심 질문

> "IDE에서 Run 누르면 어떤 런타임이 도나요? prod 서버에는 뭘 깔아야 하나요? Spring Boot jar는 어떻게 실행되나요?"

### 4.2 키워드 1 — 시나리오별 런타임 비교표

| 시나리오 | 어떤 런타임? | 왜 |
|---|---|---|
| **IntelliJ Run / Debug** | Project SDK (JDK 전체) | 디버거 + JFR + 추가 도구 필요 |
| **`./gradlew run` / `test`** | `JAVA_HOME` 또는 Gradle Toolchain JDK 전체 | 빌드 + 테스트에 모든 도구 필요 |
| **`java -jar app.jar`** (전통 prod) | JDK 또는 JRE | "어떤 머신이든 자바만 깔려있으면" |
| **Docker `eclipse-temurin:21` 베이스** | JDK 전체 (베이스 포함) | 300~500MB 컨테이너 |
| **Docker + jlink 이미지** | 커스텀 런타임 이미지 | 100~150MB 컨테이너 |
| **GraalVM Native Image** | JVM 없음 (단일 바이너리) | 콜드스타트 ms, 메모리 ~수십MB |

**핵심**: dev에서는 jlink 이미지 따로 안 만들고 IntelliJ가 설정한 **JDK 전체**를 그대로 쓴다. prod에서는 jlink로 작게 만든다.

### 4.3 키워드 2 — 왜 dev에서는 jlink를 안 쓰나

1. **디버거 필요**: JDWP agent 등 추가 모듈.
2. **JFR / jstack / jmap**: 운영 진단 도구는 dev에서도 자주 씀.
3. **Hot reload / agent**: Spring DevTools, JRebel.
4. **빌드 속도**: jlink 자체가 수 초 — 매 Run마다 새로 만들면 비효율.
5. **개발 편의 > 이미지 크기**: dev 머신에 JDK 한 번 깔아두면 됨.

→ **prod는 정반대 우선순위** — 이미지 크기, 콜드 스타트, 보안 표면이 더 중요.

### 4.4 키워드 3 — JAR 4종과 ClassLoader 동작

JAR을 어떻게 묶느냐가 **배포 모델**을 결정한다. 사용하는 JDK 도구는 같지만(`javac` + `jar`), 결과물의 **내부 구조와 실행 방식**이 다르다.

| 종류 | 안에 뭐가 들어있나 | 실행 시 ClassLoader 동작 |
|---|---|---|
| **Plain jar** | 내 `.class`만 | AppClassLoader가 `-cp`에 지정된 jar들 순회 |
| **Fat jar (Shadow/Shade)** | 내 + dep `.class` **모두 평탄화** | AppClassLoader가 한 jar 안의 모든 클래스 검색 |
| **Spring Boot jar** | 내 `.class` + dep `.jar`을 **중첩 보관** | `JarLauncher` → `LaunchedURLClassLoader` → `BOOT-INF/lib/*.jar`를 **nested jar URL**로 로드 |
| **GraalVM Native Image** | 아예 jar 아님 — 단일 native 바이너리 | ClassLoader 거의 안 씀, AOT로 native에 박힘 |

**Spring Boot jar의 특별한 구조**:
```
app-boot.jar
├── META-INF/MANIFEST.MF
│     Main-Class: JarLauncher    ★
│     Start-Class: com.example.MyApplication
├── org/springframework/boot/loader/   ← Loader 클래스들
├── BOOT-INF/
│   ├── classes/                       ← 내 클래스 (평탄)
│   └── lib/                           ← dep jar들 (★ 풀지 않음 ★)
│       ├── spring-core-6.0.10.jar
│       └── ...
```

**왜 안 풀까**: 같은 클래스가 여러 dep에 있을 때 conflict 회피, signed jar 무결성 유지, 빌드 속도.

### 4.5 운영 가이드 — 언제 어떤 jar를 만드나

| 상황 | 권장 |
|---|---|
| 라이브러리 배포 (다른 프로젝트가 의존) | **Plain jar** + dependency 관리 |
| CLI 도구 / 단독 실행 | **Fat jar** |
| Spring Boot 앱 | **Spring Boot jar** (`bootJar`) |
| 컨테이너 이미지 최적화 (큰 Spring 앱) | **Spring Boot Layered jar** + Docker 멀티스테이지 + **jlink 베이스** |
| 콜드스타트 ms 단위 (FaaS / CLI) | **GraalVM Native Image** |
| 데스크탑 앱 (.exe/.dmg/.deb) | **jpackage** (jlink + OS 설치 패키지) |

**중요**: **빌드는 JDK 필요** (`javac`, `jar`). **실행은 java 런처만 있으면 OK** (JDK / JRE / jlink 이미지 / Native Image 자체 실행). **jlink와 Fat jar는 직교**한다 — "런타임 자체"를 작게 vs "앱 패키지"를 한 파일로, 둘은 같이 쓸 수 있다.

### 4.6 운영 시나리오 매트릭스

| 증상 | 진단 | 원인 |
|---|---|---|
| `error while loading shared libraries: libjvm.so` | `ldd $(which java)` | JAVA_HOME 잘못, LD_LIBRARY_PATH |
| `jstack`이 없다 (prod에서) | `which jstack` | JRE만 깔림 → JDK 또는 jlink + 진단 도구 |
| 컨테이너 300MB 이상 | `docker history` | JDK 전체 베이스 → jlink로 100MB대 |
| 콜드스타트 5초+ (FaaS) | JIT warm-up | Native Image 검토 |
| `--add-opens` 에러 폭증 | JDK 16+ 마이그레이션 | reflection default-deny 정책 |
| `sun.misc.Unsafe` 깨짐 | `jdeps --jdk-internals` | 내부 API 의존 (JDK 9+ 정리 대상) |

---

## 5. 가지 ⑤: 진화 — JDK 8 → 9 → 11+ 패키징 변화

### 5.1 핵심 질문

> "JDK 9에서 JRE가 사라졌다고 들었는데, 그럼 지금 사용자는 어떻게 실행하나요?"

### 5.2 키워드 1 — JDK 8까지: 전통적 3중 박스

**구조** (디렉토리 = 개념):
- `$JAVA_HOME/` = JDK
- `$JAVA_HOME/jre/` = **JRE가 진짜 폴더로 존재**
- `$JAVA_HOME/jre/lib/rt.jar` = 모든 표준 클래스가 묶인 단일 60MB jar
- `$JAVA_HOME/jre/lib/ext/` = Extension Mechanism

**한계가 드러난 시점**:
- 2010년대 초 — Android, IoT, 임베디드의 부상.
- 60MB짜리 `rt.jar`가 너무 크고, 모든 표준 클래스를 한꺼번에 가져야 함.
- `sun.misc.Unsafe` 같은 내부 API가 무분별하게 노출되어 라이브러리들이 의존 → 호환성 깨기 어려움.

### 5.3 키워드 2 — JDK 9~10: Module System + 평탄화

**구조 변화**:
- `$JAVA_HOME/` = JDK (평탄)
- **`jre/` 폴더 사라짐** — 옛 `jre/bin/java` 등이 `$JAVA_HOME/bin/`으로 통합
- `lib/modules` = **jimage 포맷** — 옛 `rt.jar`을 모듈 단위로 분해 + 압축
- `ext/` 폴더 폐기

**변화의 트리거**:
- **JEP 261 Module System (Project Jigsaw)**: 패키지보다 상위의 module 단위. `module-info.java`로 의존성 + export 명시.
- **JEP 282 jlink**: 필요한 모듈만 골라 "내 앱 전용 런타임 이미지" 생성.
- **JEP 220 Modular Run-Time Images**: `rt.jar` → `lib/modules` (jimage) 재구성.

**ClassLoader 모델 변화**:
- 그 전: Bootstrap → **Extension CL** (jre/lib/ext) → Application CL
- 그 후: Bootstrap → **Platform CL** → Application CL (Extension CL 폐기)

이 시대에는 **별도 JRE 배포가 아직 존재** — Oracle, AdoptOpenJDK가 JRE 빌드를 따로 배포.

### 5.4 키워드 3 — JDK 11+: 별도 JRE 배포 종료, jlink 시대

**왜 별도 JRE 배포가 종료됐나**:
- jlink가 "내 앱에 맞춤형 JRE"를 만들 수 있게 됨 → "범용 JRE 하나로 모두에게"의 가치 하락.
- Oracle은 **JDK 11부터** standalone JRE 별도 배포 중단.
- 컨테이너 시대(Docker, K8s) — 작은 이미지가 더 중요. jlink가 그 답.

**라이선스 격동기** (이해 필수):
- **2018.09 Oracle JDK 11**: 상업적 사용 유료화 → 대안 빌드 폭발 (AdoptOpenJDK→Temurin, Amazon Corretto, Azul Zulu, BellSoft Liberica, SapMachine, Red Hat OpenJDK).
- **2021.09 Oracle JDK 17**: "Oracle No-Fee Terms" — 재무료화 (2024년 9월에 또 조정).

**현재의 JRE 개념**:
- **JRE라는 단어**는 계속 쓰이지만, **표준화된 단일 형태**는 사라졌다.
- 각 앱이 jlink로 만드는 "내 앱 전용 런타임 이미지"가 사실상의 JRE.

### 5.5 한눈에 비교 — 시대별 패키징

| 측면 | JDK 8까지 | JDK 9~10 | JDK 11+ |
|---|---|---|---|
| **`jre/` 폴더** | 존재 | 사라짐 | 사라짐 |
| **`rt.jar`** | 60MB 단일 | `lib/modules` (jimage) | 동일 |
| **`ext/` 폴더 (Extension)** | 존재 | 폐기 | 폐기 |
| **별도 JRE 배포** | 표준 | 존재 | Oracle 기준 종료 |
| **Module System** | 없음 | JEP 261 | 있음 |
| **`jlink`** | 없음 | JEP 282 | 사실상 표준 |
| **ClassLoader 모델** | Boot → Ext → App | Boot → **Platform** → App | 동일 |
| **릴리스 주기** | 3~5년 | 6개월 (LTS 2~3년) | 6개월 (LTS 2~3년) |

### 5.6 25년 타임라인

| 연도 | 이정표 | 의미 |
|---|---|---|
| 1991 | Green Project (Oak) | 임베디드용 → "Write Once Run Anywhere" 동기 |
| 1995 | Java 1.0 | Interpreter only, 매우 느림 |
| 1999 | HotSpot 등장 (JDK 1.3) | JIT 컴파일러 — "핫스팟만 컴파일" 아이디어 |
| 2006 | OpenJDK 출범 | GPLv2 오픈소스화 |
| 2010 | Oracle, Sun 인수 | 소유권 이동 |
| 2014 | JDK 8 | Lambda + Stream, default method |
| 2017 | JDK 9 | **Module System (Jigsaw), 별도 JRE 종료 시작** |
| 2021 | JDK 17 LTS | Sealed classes, Records, Pattern matching |
| 2023 | JDK 21 LTS | **Virtual Thread (Loom)** |

### 5.7 시대별 prod 배포 진화 — 같은 철학의 다른 구현

- **2010년대까지**: 서버에 JDK/JRE 깔고 fat jar 배포.
- **2018년+**: Docker + JDK 베이스 이미지.
- **2020년+**: `jlink` 이미지 + Distroless / scratch — 100~150MB 컨테이너.
- **2022년+**: GraalVM Native Image — 콜드스타트 ms, 메모리 수십MB (FaaS 시장).

→ 각 시대마다 **"필요한 만큼만 받자"** 라는 같은 철학의 다른 구현.

### 5.8 운영 체크리스트 (시대별)

**JDK 8 운영**:
- `jre/lib/ext/`에 의존 라이브러리 꽂혀있지 않은지 확인 (보안 + 충돌).
- `rt.jar` 안의 `sun.misc.*` 의존 — JDK 9+ 마이그레이션 시 깨짐.

**JDK 9~10 마이그레이션**:
- `--add-modules`, `--add-opens`가 갑자기 필요.
- `jdeps --jdk-internals my-app.jar`로 내부 API 의존 검출.

**JDK 11+ 운영**:
- Docker 이미지 작게 만들려면 `jlink` 커스텀 런타임.
- prod에 JDK 받지 말고 jlink 이미지 + Distroless로 100MB대 목표.
- JDK 16부터 reflection default-deny, 17부터 더 엄격.

---

## 6. 면접 답변 워크플로우

### 6.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "JVM, JRE, JDK 차이?" | ① WHAT | ② WHY로 분리 이유 |
| "JVM이 가상 머신이라는 게 무슨 뜻?" | ① WHAT (Process VM) | ⑤ 역사 |
| "왜 처음부터 분리됐나?" | ② WHY | ⑤ 진화 (지금은 모듈 분리) |
| "java HelloWorld 들어가면?" | ③ HOW | ④ 운영 (어디서 도나) |
| "java 명령은 JVM인가?" | ③ HOW (런처 vs libjvm) | — |
| "prod에 JDK 깔까 JRE 깔까?" | ④ 운영 | ⑤ 진화 (별도 JRE 종료) |
| "Spring Boot jar는 어떻게 실행?" | ④ JAR 4종 | ③ HOW (ClassLoader) |
| "JDK 9에서 JRE 사라졌다?" | ⑤ 진화 | ② WHY (입자 미세화) |
| "GraalVM은 JVM인가?" | ① WHAT (구현체) | ⑤ Native Image |
| "Dalvik이 JVM인가?" | ① WHAT (.dex는 ClassFile 아님) | — |

### 6.2 답변 템플릿

> **루트 문장 한 줄 → 해당 가지 키워드 3개 순서대로 → 듣는 사람 표정 보고 인접 가지로**

예: "JDK 9에서 JRE가 사라졌다는데 사실인가요?"

> "사실인 부분과 아닌 부분이 섞여 있습니다 (← 후크).
> **JDK ⊃ JRE ⊃ JVM**의 포함 관계는 단순 트리가 아니라 명세·구현·입력 3 레이어의 분리고, JDK 9의 변화도 이 분리의 입자가 미세해진 것입니다 (← 루트).
> 첫째, **JDK 8까지**는 `$JAVA_HOME/jre/` 폴더가 진짜로 존재하고 `rt.jar` 60MB가 한 덩어리였습니다.
> 둘째, **JDK 9**에서 Module System(JEP 261)과 jlink(JEP 282)가 도입되면서 `jre/` 폴더는 사라지고 `lib/modules` (jimage)로 모듈 단위 분해됐습니다. 그러나 별도 JRE 배포 자체는 아직 존재했습니다.
> 셋째, **JDK 11**부터 Oracle은 standalone JRE 배포를 중단했고, 그 자리에 **jlink로 만드는 '내 앱 전용 런타임 이미지'**가 들어섰습니다.
> 결론: **JRE라는 디렉토리 형태는 사라졌지만, '실행에 필요한 최소 집합'이라는 개념은 jlink 이미지로 살아 있습니다.**"

→ 면접관이 "그럼 prod에는 뭐 깔죠?" 물으면 ④ 운영으로, "왜 모듈로 쪼갰죠?" 물으면 ② WHY로.

---

## 7. 꼬리질문 트리 (가지별)

### Q1 [가지 ①]. JVM, JRE, JDK의 차이를 설명하세요.

> JDK ⊃ JRE ⊃ JVM. JVM이 실행, JRE가 실행 + 라이브러리, JDK가 실행 + 라이브러리 + 개발 도구. 단, 이 포함 관계는 **명세(JVMS) / 구현(HotSpot) / 입력(ClassFile)** 3 레이어와 별개의 축이므로 같이 설명해야 함.

**🪝 Q1-1: JRE만 있어도 Java 프로그램을 컴파일할 수 있나요?**
> 못 한다. 컴파일은 `javac`인데 JDK에만 있다. JRE에는 실행기 `java`만.

**🪝🪝 Q1-1-1: IntelliJ에서 컴파일은 어디서 하나요?**
> IntelliJ는 자체 ECJ(Eclipse Compiler for Java)를 in-process로 쓰거나 설정된 JDK의 `javac`를 호출한다. 빌드 속도 때문에 ECJ를 쓰는 경우가 많음.

**🪝 Q1-2: JDK 9 이후 별도 JRE 배포가 사라졌는데 사용자는 어떻게 실행하나?**
> JDK를 받거나, `jlink`로 만든 커스텀 런타임 이미지를 배포받는다. JRE의 **개념**(실행에 필요한 최소 집합)은 살아있다.

**🪝🪝 Q1-2-1: jlink 런타임이 일반 JRE보다 작은 이유?**
> `rt.jar` 통째가 아니라 내 앱이 require하는 모듈만 포함. 또 `.class`를 `jimage` 포맷으로 압축. CDS도 같이 생성 가능.

### Q2 [가지 ①]. JVM은 가상 머신이라는데 VMware와 뭐가 다른가요?

> VMware = System VM (하드웨어 통째 에뮬레이션). JVM = Process VM (OS 위 한 프로세스에서 가상 명령어 실행). 두 카테고리.

**🪝 Q2-1: Docker는 어디?**
> 가상 머신이 아님. 컨테이너 = OS-level virtualization (커널 공유 + namespace + cgroup). 또 다른 카테고리.

### Q3 [가지 ①]. JVM 명세와 구현의 차이를 예시로 설명?

> JVMS는 ClassFile 포맷, bytecode 의미론, Runtime Data Areas의 종류를 정의. GC 구현 방식이나 JIT 알고리즘은 정의 안 함. 그래서 HotSpot은 G1/ZGC, OpenJ9은 Balanced GC. 둘 다 JVMS 준수.

**🪝 Q3-1: 명세를 어기는 구현이 있나?**
> 공식 TCK 통과하려면 따라야 함. Android의 Dalvik/ART는 **JVM이 아님** — bytecode 포맷부터 `.dex`로 다름. "Java 호환 VM"이라 부름.

**🪝🪝 Q3-1-1: Dalvik이 register-based인 이유?**
> ARM같은 register-rich CPU에서 적은 인스트럭션으로 같은 일. 모바일에서 코드 크기와 실행 효율 트레이드오프가 유리. ART의 AOT 도입으로 이 차이는 흐려짐.

### Q4 [가지 ③]. `java HelloWorld`를 입력하면?

> 1. 셸이 `java` 바이너리 exec.
> 2. `java` 런처가 `libjvm.so`를 **dlopen**으로 로드.
> 3. `dlsym`으로 `JNI_CreateJavaVM` 주소 얻어 호출 → `Threads::create_vm`.
> 4. 인자 파싱, OS init, Heap·ClassLoader·JIT 초기화.
> 5. Bootstrap CL이 `java.lang.Object` 등 로드.
> 6. AppClassLoader가 `HelloWorld.class` 로드 (-cp 또는 현재 디렉토리).
> 7. Verifier 검증.
> 8. `CallStaticVoidMethod`로 main 호출 → Interpreter 시작.
> 9. 호출 빈도 임계치 넘으면 C1 → C2 JIT.
> 10. 종료 시 DestroyJavaVM.

**🪝 Q4-1: ClassLoader가 .class를 어떻게 찾나?**
> **부모 위임 모델**: AppCL → PlatformCL → BootstrapCL 위로 올라가서 먼저 부모에게 묻고, 부모가 못 찾으면 자신이 찾는다. AppCL은 `-classpath` 또는 `CLASSPATH`에서 찾음.

**🪝🪝 Q4-1-1: 위임 모델 깨는 케이스?**
> Tomcat의 WebappClassLoader는 자기가 먼저 찾고 없으면 부모 — 웹앱마다 라이브러리 격리. JDBC DriverManager + ServiceLoader는 Thread Context ClassLoader 사용 (부모 위임으론 못 찾음). OSGi도 동일.

**🪝 Q4-2: JIT 컴파일된 코드는 어디 저장되나?**
> **Code Cache** — Metaspace와 별개의 native 영역. 기본 240MB. full이 되면 JIT 중단되고 인터프리터로만 → 성능 급락. JDK 9부터 Tiered: profiled / non-profiled / non-method 분리.

**🪝🪝 Q4-2-1: Code Cache full 감지?**
> `-XX:+PrintCodeCache`, JFR `jdk.CodeCacheStatistics`, JMX `MemoryPoolMXBean` "CodeCache". `-XX:+UseCodeCacheFlushing` 확인 (기본 on).

### Q5 [가지 ④]. Spring Boot jar는 안의 dep jar를 풀지 않는데 어떻게 실행되나?

> Manifest의 `Main-Class`가 `JarLauncher`. JarLauncher가 `LaunchedURLClassLoader`를 만들고 `BOOT-INF/lib/*.jar`를 **nested jar URL**로 추가. 그 CL이 클래스 검색. 풀지 않는 이유는 conflict 회피 + signed jar 무결성 + 빌드 속도.

**🪝 Q5-1: 그럼 일반 jar처럼 `-cp`로 못 쓰나?**
> 가능은 하지만 정상 동작 안 함. Spring Boot의 nested jar 구조는 표준 ClassLoader가 모름. `JarLauncher`를 거쳐야 함.

### Q6 (Killer) [가지 ⑤]. HotSpot, OpenJ9, GraalVM 중 prod에 뭐?

> 워크로드에 따라.
> - 장기 실행 서버 + Throughput → HotSpot C2 + G1/ZGC (검증된 조합).
> - 메모리 제약 + 빠른 startup → OpenJ9 또는 GraalVM Native Image.
> - CLI / FaaS / 콜드 스타트 → GraalVM Native Image (AOT, ms startup).
> - 초저지연 (<10ms tail) → Azul Zing C4 또는 OpenJDK Generational ZGC.
> - 단, Native Image는 reflection / dynamic class loading 제약 — Spring Boot도 reachability 메타데이터 필요.

**🪝 Q6-1: GraalVM은 JVM인가요?**
> 한 줄 답 어려움. (1) GraalVM JDK 배포는 HotSpot의 JIT을 Graal로 교체 — JVM의 일종. (2) Graal 컴파일러 자체는 JVMCI plug-in. (3) Native Image는 SVM이라는 별개 런타임 — HotSpot 자체를 안 씀. "GraalVM = HotSpot 대체"는 일부만 맞음.

---

## 8. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 이내로 그릴 수 있다 (루트 + 5가지 + 각 키워드 3개)
- [ ] 가지 ① WHAT: 3중 박스 + 4대 서브시스템 + 명세/구현/입력 3 레이어를 같이 그린다
- [ ] 가지 ① WHAT: Process VM vs System VM vs 컨테이너를 구분한다
- [ ] 가지 ② WHY: 분리의 4가지 동기(자원/사용자/보안/라이선스)를 말한다
- [ ] 가지 ② WHY: 합치지 않는 4가지 이유(컨테이너/콜드스타트/보안/임베디드)를 말한다
- [ ] 가지 ③ HOW: `java` 런처 → dlopen → JNI_CreateJavaVM → Threads::create_vm 흐름을 그린다
- [ ] 가지 ③ HOW: `java`는 C 런처이고 진짜 JVM은 `libjvm.so`임을 설명한다
- [ ] 가지 ④ 운영: dev (JDK 전체) vs prod (jlink) 차이를 말한다
- [ ] 가지 ④ 운영: jar 4종 (Plain/Fat/Boot/Native)의 ClassLoader 동작을 구분한다
- [ ] 가지 ⑤ 진화: JDK 8 / 9~10 / 11+ 비교표를 적는다
- [ ] 가지 ⑤ 진화: 별도 JRE 종료의 의미("배포는 종료, 개념은 살아있음")를 설명한다
- [ ] 7장 꼬리질문 6개에 막힘없이 답한다

---

## 다음 단계

- → [02. 컴파일 흐름](./02-class-compilation-flow.md): `.java`가 `.class`로, 그리고 native 코드로 변환되는 전체 여정
- → [03. JVM 아키텍처 큰 그림](./03-jvm-architecture-bigpicture.md): 4대 서브시스템 깊이
- → [04. JVM 역사](./04-jvm-history.md): 25년 진화 풀버전

## 참고

- **The Java Virtual Machine Specification, Java SE 21 Edition**: https://docs.oracle.com/javase/specs/jvms/se21/html/
- **OpenJDK source**: https://github.com/openjdk/jdk
- **HotSpot Glossary**: https://openjdk.org/groups/hotspot/docs/HotSpotGlossary.html
- **JEP Index**: https://openjdk.org/jeps/0
- **JEP 261 — Module System**: https://openjdk.org/jeps/261
- **JEP 282 — jlink**: https://openjdk.org/jeps/282
- **HotSpot `threads.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/runtime/threads.cpp
