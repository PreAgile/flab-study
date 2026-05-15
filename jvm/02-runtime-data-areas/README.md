# 02. Runtime Data Areas — JVM이 OS로부터 받는 모든 메모리

> "JVM 메모리 = Heap" 이라고 답한 면접자는 절반은 모르는 것이다.
> JVM은 OS로부터 **7~10개 영역의 메모리**를 받아쓴다. 그래서 `-Xmx2g`인데 `top`의 RSS가 4GB가 나온다.
> 이 챕터는 그 모든 영역을 한 줄씩 따라간다.

---

## 📍 학습 목표

이 챕터를 마치면 다음을 막힘없이 답할 수 있다.

1. JVM 프로세스의 메모리 footprint를 구성하는 모든 영역을 종이에 그릴 수 있다.
2. `-Xmx2g`로 시작한 JVM이 RSS 4GB를 쓰는 이유를 영역별로 분해해 설명할 수 있다.
3. PermGen이 Metaspace로 바뀐 이유와 결과적 차이를 안다.
4. TLAB이 무엇이고 왜 bump-the-pointer 할당이 가능한지, 가득 차면 어떻게 되는지 안다.
5. Humongous Object가 무엇이고 왜 운영 함정인지 안다.
6. Code Cache가 가득 차면 무슨 일이 일어나는지, 어떻게 진단하는지 안다.
7. Direct Memory가 GC와 어떻게 상호작용하는지, 누수가 어떻게 발생하는지 안다.
8. Container 환경에서 `-Xmx`를 limit의 50~70%로 잡는 이유를 설명할 수 있다.

---

## 학습 흐름

```
┌───────────────────────────────────────────────────────────────┐
│ JVM Process 전체 메모리 (RSS = footprint)                      │
│                                                               │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ 01. Heap & TLAB                                           │ │
│  │     Young(Eden + Survivor) | Old | Humongous              │ │
│  │     ★ TLAB: Thread-Local Allocation Buffer                │ │
│  └──────────────────────────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ 02. Metaspace & Class Space                               │ │
│  │     Class 메타데이터, Method 정보, Constant Pool             │ │
│  │     PermGen → Metaspace (JDK 8), Compressed Class Space  │ │
│  └──────────────────────────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ 03. Stack & PC & Native Method Stack                      │ │
│  │     Per-Thread, Stack Frame, Operand Stack, Local Vars    │ │
│  │     Virtual Thread의 stack chunk (JDK 21+)                │ │
│  └──────────────────────────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ 04. Code Cache                                            │ │
│  │     JIT 컴파일 결과 native code 저장                         │ │
│  │     Segmented (JDK 9+): profiled / non-profiled / non-method│ │
│  └──────────────────────────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ 05. Direct Memory & MappedByteBuffer                      │ │
│  │     Off-heap, NIO, zero-copy I/O                          │ │
│  │     Cleaner 누수 패턴                                       │ │
│  └──────────────────────────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ 06. GC 부속 자료구조 & 기타                                  │ │
│  │     Card Table, Remembered Set, Mark Bitmap               │ │
│  │     JIT scratch, JVM internal                             │ │
│  └──────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────┘
```

---

## 챕터 목록

| # | 파일 | 핵심 질문 | 상태 |
|---|---|---|---|
| 01 | [01-heap-and-tlab.md](./01-heap-and-tlab.md) | "Heap은 어떻게 나뉘고, TLAB은 왜 필요한가, Humongous는 무엇인가" | ✅ |
| 02 | [02-metaspace-and-class-space.md](./02-metaspace-and-class-space.md) | "Metaspace는 Heap 밖에 있는데 어떻게 동작하나, PermGen은 왜 죽었나" | ✅ |
| 03 | [03-stack-pc-native.md](./03-stack-pc-native.md) | "Per-Thread 영역의 정확한 구조, Stack Frame 안에 뭐가 있나, Virtual Thread는 어떻게 다른가" | ✅ |
| 04 | [04-code-cache.md](./04-code-cache.md) | "JIT 결과는 어디에 저장되고, full이 되면 무슨 일이 일어나나" | ✅ |
| 05 | [05-direct-memory.md](./05-direct-memory.md) | "DirectBuffer는 왜 쓰고, 어떻게 누수되나" | ✅ |
| 06 | [06-gc-bookkeeping-and-others.md](./06-gc-bookkeeping-and-others.md) | "Card Table, RSet, Mark Bitmap이 차지하는 메모리" | ✅ |

---

## 사전 학습

- [00-overview/03-jvm-architecture-bigpicture.md](../00-overview/03-jvm-architecture-bigpicture.md) — 4대 서브시스템 큰 그림 (이 챕터는 ② Runtime Data Areas의 풀버전)
- [01-class-lifecycle](../01-class-lifecycle/) — ClassLoader가 Metaspace에 무엇을 적재하는지 미리 알면 02번 sub-chapter가 더 와닿음

## 핵심 통찰 — 챕터 들어가기 전에

### memory footprint = JVM 전체가 OS로부터 받는 메모리

```
JVM 프로세스의 RSS (Resident Set Size)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Java 영역]
├── Java Heap          ← -Xmx 로 제어 (Young + Old + Humongous)
├── Metaspace          ← Class 메타데이터 (native 메모리)
├── Compressed Class Space  ← 32비트 Klass 포인터용 (~1GB)
└── String Pool        ← interned String (Heap 안의 별도 영역)

[JIT/실행]
├── Code Cache         ← JIT 결과 native code (기본 240MB reserve)
└── JIT scratch        ← 컴파일 중 임시 메모리

[Per-Thread]
├── JVM Stack          ← 스레드별 ~1MB × N 스레드
└── Native Method Stack ← JNI 스택

[Off-Heap]
├── Direct Buffer      ← ByteBuffer.allocateDirect
└── MappedByteBuffer   ← mmap된 파일

[GC 자료구조]
├── Card Table         ← Heap 크기에 비례
├── Remembered Set     ← G1/ZGC
└── Mark Bitmap        ← GC 마킹용

[Native]
├── JVM 내부 자료구조   ← libjvm.so의 .data/.bss
└── 네이티브 라이브러리  ← libnio.so, libnet.so, JNI 라이브러리

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                 = footprint (RSS)
```

### 흔한 함정

| 함정 | 사실 |
|---|---|
| "memory footprint = `-Xmx`" | ❌ Heap은 일부일 뿐. footprint = RSS |
| "`-Xmx512m`인데 RSS 1GB는 메모리 누수" | ❌ 정상. 나머지는 Metaspace/Code Cache/Stacks 등 |
| "container limit = `-Xmx`로 주면 안전" | ❌ OOM-killed 위험. limit의 50~70%가 안전 |
| "Heap GC가 모든 메모리를 관리" | ❌ Heap만. Metaspace/Code Cache는 별도 정책 |
| "Direct Memory도 GC 대상" | △ 간접적. DirectBuffer 객체가 GC될 때 Cleaner가 native free |

### 측정 명령 모음

```bash
# 1. 전체 RSS
ps -o pid,rss,vsz,cmd -p $(pgrep -f my-app)

# 2. JVM 영역별 (Native Memory Tracking 활성화 필요)
java -XX:NativeMemoryTracking=summary -jar app.jar
jcmd <pid> VM.native_memory summary

# 3. Heap 상세
jcmd <pid> GC.heap_info
jstat -gc <pid> 1s

# 4. Metaspace
jcmd <pid> VM.metaspace summary

# 5. Code Cache
jcmd <pid> Compiler.codecache

# 6. ClassLoader / 클래스 통계
jcmd <pid> VM.classloader_stats
jcmd <pid> GC.class_histogram | head -30
```

---

## 7단 레이어 적용 (이 챕터의 모든 sub-chapter에서)

| 단계 | 내용 |
|---|---|
| 1. 백지 그리기 | 메모리 영역을 손으로 그리기 + SVG 정답 비교 |
| 2. 직관 | 왜 이 영역이 존재하는지 비유 + 정확한 정의 |
| 3. 구조 | 영역 내부 분할 (Young/Old, Eden/Survivor, ...) ASCII 다이어그램 |
| 4. 내부 구현 | HotSpot C++ 코드 (`universe.cpp`, `g1CollectedHeap.cpp` 등) |
| 5. 역사 | 시대별 변화 (PermGen→Metaspace, Code Cache 분할 등) |
| 6. 트레이드오프 | HotSpot vs OpenJ9 vs ZGC, 옵션별 비교 |
| 7. 측정·진단 | jcmd, NMT, JFR, GC log 활용법 |
| + 꼬리질문 | 면접 시뮬레이션 |
