# 03-03. Tiered Compilation — 5단계 점진 승격 + Compile Broker

> "C1으로 빠르게, C2로 깊게" 한 줄 답은 절반이다.
> 실제로는 **Tier 0~4의 5단계 + 동적 임계 조정 + Compile Broker의 우선순위 큐 + CompilerThread 풀 + Code Cache 압박 시 fallback** 까지 — 한 시스템으로 묶여 있다.
> 시니어가 알아야 할 것: warmup이 평소보다 느린데 코드는 그대로일 때, **Compile Broker의 큐 상태**가 첫 의심지점이다. 큐가 길면 동적 임계가 올라가 컴파일 요청이 줄어들고, 메서드가 인터프리터에 더 오래 머문다.

---

## 이 문서의 사용법

1. **0장 마인드맵을 먼저 외운다** — 루트 + 5가지 + 키워드.
2. **1~5장을 순서대로 학습한다** — 각 장이 마인드맵의 한 가지에 대응.
3. **6장 면접 워크플로우**, **7장 꼬리질문**.

---

## 0. 마인드맵 — 면접 종이에 그릴 그림

### 루트 한 문장 (anchor)

> **"Tiered Compilation은 Tier 0(Interpreter) → 3(C1+profile) → 4(C2) 의 5단계 점진 승격 시스템이다. TieredThresholdPolicy가 다음 tier 결정 → Compile Broker의 우선순위 큐에 push → CompilerThread가 pickup → 컴파일 후 Method._code를 atomic patch. 큐 길어지면 임계가 동적으로 올라가 시스템 부하에 적응한다."**

### 5개 가지 — 순서를 외운다

```
                  [ROOT: 5단계 점진 승격 + Compile Broker 시스템]
                                  │
       ┌──────────────┬───────────┼───────────┬──────────────┐
       │              │           │           │              │
      ① WHY         ② WHAT      ③ HOW        ④ 운영        ⑤ 진화
   왜 5단계인가?    5단계 정의   Compile      (시니어       (-server→
                                Broker       진단)         Tiered)
       │              │           │           │              │
       │         ┌────┼────┐  ┌───┼───┐  ┌────┼────┐         │
   profile-     T0    T3   T4 큐+   동적  Compi  큐      JDK7  JDK8
   guided opt   Inter C1   C2 Compiler 임계 ler.   적체   -server Tiered
   /점진 승격   /MDO  /prof    Thread 조정  queue  진단    /-client 기본on
   /부하 적응                  풀     load   /code        선택   /Graal
                                            cache         문제   옵션
```

### 가지별 핵심 키워드 (각 가지 3개씩만)

| 가지 | 키워드 1 | 키워드 2 | 키워드 3 |
|---|---|---|---|
| **① WHY 5단계** | profile-guided opt | warmup ↑ + peak ↑ 양립 | 부하 적응 |
| **② WHAT 5단계 정의** | T0 Interpreter | T3 C1+full profile | T4 C2 |
| **③ HOW Compile Broker** | 큐 (C1용/C2용 분리) | CompilerThread 풀 | atomic Method._code patch |
| **④ 운영** | Compiler.queue 적체 진단 | CICompilerCount 부족 | Code Cache 압박 시 fallback |
| **⑤ 진화** | -server/-client 선택 (~JDK7) | Tiered 기본 on (JDK8) | Graal 옵션 (JDK11+) |

### 면접 답변 흐름

> 면접관 질문 → 루트 → 적절한 가지 → 키워드 3개 → 인접 가지

---

## 1. 가지 ①: WHY — 왜 5단계 점진 승격인가

### 1.1 핵심 질문

> "C1과 C2 둘만 있으면 안 되나요? 왜 5개 tier를 두고 점진 승격하나요?"

### 1.2 키워드 1 — Profile-Guided Optimization

```
[직진: Tier 0 → 4만 (Tiered off)]
호출 N번 → 임계 도달 → C2 즉시 시작
  C2가 profile 없이 컴파일 → type guess 부정확 → deopt 빈발
  inlining 보수적 → peak 성능 ↓

[Tiered: Tier 0 → 3 → 4]
호출 ~1500 → T3 (C1+profile) 컴파일 (수 ms)
  → C1 native code 실행 시작 (인터프리터 대비 ~10× 빠름)
  → 그 동안 profile 안정화 (type, branch 히스토그램)
호출 ~10000 → T4 (C2) 컴파일
  → 정확한 profile 기반 공격적 inlining + speculation
  → peak 성능 ↑
```

→ **C1은 단순히 "약식 C2"가 아니라 profile 수집기**. C1 native code 안에서도 profile counter가 실행마다 증가 → C2가 그걸 활용.

### 1.3 키워드 2 — Warmup ↑ + Peak ↑ 양립

```
Throughput
     ▲
Peak │      ┌─────────────── C2 steady state
     │     ╱
     │    ╱
     │   ╱  ← C2 컴파일 진행 (수 분)
     │  ╱
     │ ╱
     │╱  ← C1 컴파일 진행 (수 초)
     │
   0 └──────────────────────────► time
     start
```

C1 단계가 있으면 인터프리터 → C1 단계로 빠르게 가속. C2 완료 전에도 충분히 빠름. 인터프리터에서 바로 C2로 가면 컴파일 동안 모두 인터프리터로 도는 시간이 길어짐.

### 1.4 키워드 3 — 부하 적응 (동적 임계)

```
시나리오: 트래픽 burst (10× 트래픽)
  → 모든 메서드 카운터가 동시에 임계 도달
  → 수백 개 메서드가 동시 컴파일 요청
  → CompileQueue 폭주 (CompilerThread 한정, 예: 4개)

[동적 임계 없으면]
  큐 1000개씩 적체 → 컴파일 대기 길어짐 → warmup 영구 지연

[동적 임계 (scale_for_load) 적용]
  큐 길이 보고 임계 ×2~5 임시 올림
  → 컴파일 요청 줄어듦 → 정말 hot한 메서드만 컴파일
  → CompilerThread capacity 안에서 처리 → 중요한 메서드 빨리 컴파일
```

→ "임계는 고정 숫자"가 아니라 **시스템 부하에 적응**. 시니어 운영자는 큐 상태도 모니터링 대상.

### 1.5 비유로 굳히기

> **음식점 주방 비유**: T0 = 인스턴트 라면 (즉시). T3 = 30분 일반 요리 (괜찮음, 빠름). T4 = 셰프 2시간 정통 (최고). Compile Broker = 주방 매니저 (요리 우선순위 결정). CompilerThread = 셰프들 (C1 셰프 / C2 셰프 분리). 동적 임계 = 주방이 바쁘면 "고급 요리는 조금 미루자".

---

## 2. 가지 ②: WHAT — 5단계 Tier 정의

### 2.1 핵심 질문

> "Tier 0부터 4까지 정확히 어떤 의미이고, 어느 게 일반 운영에서 쓰이나요?"

### 2.2 키워드 1 — Tier 0: Interpreter + MDO

| Tier | CompLevel | 컴파일러 | Profiling | Code Cache |
|---|---|---|---|---|
| **0** | `none` | (interpreter) | MDO 수집 | Non-method (template) |

모든 메서드의 시작점. Template Interpreter가 bytecode 실행하며 호출 카운터, backedge counter, type/branch profile 수집. (자세히 [02-template-interpreter](./02-template-interpreter.md).)

### 2.3 키워드 2 — Tier 3: C1 with Full Profile

| Tier | CompLevel | 컴파일러 | Profiling | Code Cache |
|---|---|---|---|---|
| **3** | `full_profile` | C1 | 전체 (type, branch) | Profiled |

**Tiered의 표준 C1 단계**. C1이 컴파일하지만 profiling instrumented native code 생성. 실행마다 counter 증가, type histogram 갱신. C2의 입력을 만드는 단계.

### 2.4 키워드 3 — Tier 4: C2 Fully Optimized

| Tier | CompLevel | 컴파일러 | Profiling | Code Cache |
|---|---|---|---|---|
| **4** | `full_optimization` | C2 | (사용만, 수집 안 함) | Non-profiled |

**최종 단계**. Sea-of-Nodes IR로 공격적 최적화: Inlining + Escape Analysis + Loop opts + SuperWord + Speculation. profile은 이미 수집된 것 사용.

### 2.5 Tier 1, 2 (운영자가 거의 의식 안 함)

| Tier | CompLevel | 사용 케이스 |
|---|---|---|
| **1** | `simple` (C1, no profile) | trivial method (getter), C2 큐 적체 시 fallback |
| **2** | `limited_profile` (C1, invocation only) | C2 가는 임시 단계 (rare) |

일반 흐름은 0 → 3 → 4. 1, 2는 특수 케이스.

### 2.6 일반 Tiered 흐름 vs 예외

```
일반: 0 → 3 → 4

예외:
- Trivial getter: 0 → 1 에서 끝 (더 최적화 불필요)
- C2 큐 적체: 0 → 3 → 2 → 4 (Tier 2로 우회)
- C2 컴파일 실패: 0 → 3에서 stuck
- OSR: 동시에 OSR variant도 별도 컴파일 (일반 entry와 다른 nmethod)
```

---

## 3. 가지 ③: HOW — Compile Broker 구조

### 3.1 핵심 질문

> "메서드의 호출 카운터가 임계 도달한 다음에 어떤 시스템이 컴파일을 트리거하고 결과를 설치하나요?"

### 3.2 키워드 1 — 큐 (C1용/C2용 분리)

```
Compile Broker (전역 singleton)
  │
  ├── CompileQueue _c1_compile_queue (Tier 1, 2, 3용)
  │     - 우선순위 큐 (호출 빈도 + 예상 이득)
  │     - CompileTask들 (메서드 + tier + 우선순위)
  │
  ├── CompileQueue _c2_compile_queue (Tier 4용)
  │     - 우선순위 큐
  │
  └── CompilerThread 풀
        ├── _c1_threads[CICompilerCount * 1/3]
        └── _c2_threads[CICompilerCount * 2/3]
```

진입점: `src/hotspot/share/compiler/compileBroker.cpp`:

```cpp
void CompileBroker::compile_method(const methodHandle& method, int level, ...) {
    if (method->queued_for_compilation()) return;
    if (!should_compile_new_jobs()) return;   // Code Cache full
    
    CompileTask* task = create_compile_task(method, level);
    CompileQueue* queue = (level <= 3) ? _c1_compile_queue : _c2_compile_queue;
    queue->add(task);
    queue->notify();  // CompilerThread 깨움
}
```

우선순위 결정:
1. 호출 빈도 (recent invocation rate).
2. 예상 이득 (메서드 크기, hot path 비율).
3. 대기 시간 (기아 방지).

### 3.3 키워드 2 — CompilerThread 풀

```cpp
void CompilerThread::thread_main() {
    while (!should_terminate()) {
        CompileTask* task = my_queue()->get();
        if (task == NULL) { wait(); continue; }
        
        if (task->comp_level() <= 3) {
            _c1_compiler->compile_method(task);
        } else {
            _c2_compiler->compile_method(task);
        }
        
        install_code(task->method(), task->nmethod());
        method->set_code(nmethod);
    }
}
```

- CompilerThread는 **별도 OS thread** (Java thread와 분리). 사용자 코드와 함께 실행되지 않음 → P99 spike 방지.
- `top -H -p <pid>`에서 "C1 CompilerThread", "C2 CompilerThread" 이름으로 보임.
- 기본 `CICompilerCount`: `max(2, log2(cpu) + 1)`.
- 8 코어 → ~4 (1 C1 + 3 C2). 16 코어 → ~6.
- **컨테이너 함정**: cgroup CPU limit 작으면 자동 CICompilerCount=1 — 큐 적체 원인.

### 3.4 키워드 3 — Atomic Method._code Patch

```cpp
void Method::set_code(CompiledMethod* code) {
    Atomic::release_store(&_from_compiled_entry, code->verified_entry_point());
    Atomic::release_store(&_code, code);
    
    // 동시에 다른 스레드가 호출 중이어도 안전:
    //   - 다음 호출은 새 entry 사용
    //   - 진행 중 호출은 옛 nmethod로 계속 (정상 완료)
}
```

→ Atomic word write는 x86_64, ARM64에서 단일 instruction. JVM 어디서나 안전한 호출 전이 가능한 이유.

### 3.5 TieredThresholdPolicy의 결정

```cpp
CompLevel decide_next_level(Method* method, CompLevel current) {
    int i = method->invocation_count();
    int b = method->backedge_count();
    double k = scale_for_load();   // 큐 길이 따라 [1.0, 5.0]
    
    switch (current) {
        case Tier 0:  // Interpreter
            if (i + b >= Tier3InvocationThreshold * k) return Tier 3;
            break;
        case Tier 3:  // C1+profile
            if (i + b >= Tier4InvocationThreshold * k &&
                profile_is_stable(method)) return Tier 4;
            break;
    }
    return current;
}

double scale_for_load() {
    int total = _c1_queue->size() + _c2_queue->size();
    return MAX2(1.0, total / (double)CICompilerCount);
}
```

`Tier3InvocationThreshold` 기본: Server VM 200, Client VM 2000.
`Tier4InvocationThreshold` 기본: Server VM 5000~15000.

→ 운영자가 외울 필요 없음. JVM이 동적 조정.

---

## 4. 가지 ④: 운영 — 시니어 진단

### 4.1 핵심 질문

> "Warmup 느림, 큐 적체, Tier 4 컴파일 안 됨 — 각각 어떻게 진단하나요?"

### 4.2 키워드 1 — `Compiler.queue` 적체 진단

```bash
jcmd <pid> Compiler.queue
```

출력:
```
Current compiles: 
  C1 CompilerThread1   3   3       java.lang.String::indexOf (95 bytes)
  C2 CompilerThread2   4   4       MyApp::hotPath (300 bytes)

C1 compile queue:
  4   3       MyApp::method1 (50 bytes)
  5   3       MyApp::method2 (30 bytes)

C2 compile queue:
  6   4       MyApp::method3 (200 bytes)
```

큐 길이가 운영 지표:
- 길면 (50+) warmup 지연.
- 항상 100+ → 동적 클래스 폭주 의심 (Hibernate proxy, Spring AOP, Mockito).

알람: 큐 길이 > 50 (10분 평균) → CompilerThread 부족 또는 burst.

### 4.3 키워드 2 — CICompilerCount 부족 진단

```bash
jcmd <pid> PerfCounter.print | grep -i CICompiler
```

K8s 컨테이너에서 0.5 CPU limit이면 자동으로 CICompilerCount=1 — 큐 적체의 단골 원인.

조치:
- CPU limit ↑ (1~2 코어) — 자연스러운 CICompilerCount 증가.
- 또는 `-XX:CICompilerCount=2` 명시.
- 또는 `-XX:TieredStopAtLevel=3` (C2 skip — Code Cache 절약 + 컴파일 부담 ↓).

### 4.4 키워드 3 — Code Cache 압박 시 fallback

```bash
jcmd <pid> Compiler.codecache | grep stopped
```

`stopped_count > 0` → JIT 한 번이라도 멈춤. Compile Broker가 `should_compile_new_jobs() == false` → 새 task 거부.

결과:
- 새 메서드는 영원히 인터프리터 (Tier 0).
- 이미 컴파일된 메서드는 그대로.
- Tier 3 → Tier 4 승격도 안 됨.
- JVM 경고: "CodeCache is full. Compiler has been disabled."

회복: `-XX:+UseCodeCacheFlushing` (기본 on) → Sweeper가 cold nmethod 회수. 공간 확보되면 컴파일 재개.

### 4.5 JFR Compilation 이벤트

```bash
jcmd <pid> JFR.start name=cc duration=300s settings=profile filename=cc.jfr
```

핵심 이벤트:
- `jdk.Compilation` — 각 컴파일 task의 시간 + tier + 결과.
- `jdk.CompilerQueueUtilization` — 큐 활용도.
- `jdk.CompilerStatistics` — 누적 통계.

Prometheus / JMX:
- `jvm.compilations.completed.total`.
- `jvm.compilations.failed.total` — 컴파일 실패.
- `jvm.compilations.standby.queue.size` — 큐 길이.

### 4.6 운영 시나리오 매트릭스

| 증상 | 명령 | 가능 원인 |
|---|---|---|
| K8s pod warmup 느림 | `Compiler.queue` 큐 길이 | CompilerThread 부족 (작은 컨테이너) |
| Tier 4 컴파일 없음 | `-XX:+PrintCompilation` Tier 4 빈도 | profile 안정화 못 됨 (deopt 반복?) |
| `made not entrant` 폭주 | JFR `jdk.Deoptimization` | speculation 깨짐 빈번 |
| 컴파일러가 CPU 50% 점유 | `top -H -p <pid>`, CompilerThread 식별 | CICompilerCount 과다 |
| 큐 항상 길음 | `Compiler.queue` 추세 | 동적 클래스 폭주 (Hibernate, Spring AOP) |

### 4.7 Killer 시나리오 — K8s pod warmup 매우 느림

```
환경: K8s 0.5 CPU limit, JDK 21, Spring Boot
증상: pod 시작 후 readiness 통과까지 평소 30초 → 3분

진단:
$ kubectl exec pod -- jcmd 1 Compiler.queue
C1 compile queue: 47 tasks
C2 compile queue: 23 tasks   ← 큐 적체

$ kubectl exec pod -- jcmd 1 PerfCounter.print | grep CICompiler
CICompilerCount = 1   ← ★ 1개만

원인: 0.5 CPU 컨테이너 → JDK가 cgroup 보고 CICompilerCount=1
       많은 메서드가 동시 컴파일 요청 → 큐 적체

조치:
1. CPU limit ↑ (1~2 코어) → 자연스러운 CICompilerCount 증가
2. 또는 -XX:CICompilerCount=2 명시
3. -XX:TieredStopAtLevel=3 (C2 skip — Code Cache 절약)
4. AppCDS 또는 AOT (warmup 시간 자체 단축)
```

---

## 5. 가지 ⑤: 진화 — `-server`/`-client` → Tiered → Graal

### 5.1 핵심 질문

> "Tiered Compilation이 도입되기 전에는 어땠고, 앞으로 어디로 가나요?"

### 5.2 키워드 1 — `-server` vs `-client` (~JDK 7)

| | -server | -client |
|---|---|---|
| 컴파일러 | C2만 | C1만 |
| Startup | 느림 | 빠름 |
| Peak | 빠름 | 느림 |

문제: 사용자가 둘 중 하나 선택. 거대 서버 앱은 startup도 peak도 둘 다 필요.

### 5.3 키워드 2 — Tiered 기본 on (JDK 8)

```
JDK 8 Tiered:
  - 한 JVM이 C1 + C2 둘 다 사용.
  - 사용자가 -server 입력해도 사실상 Tiered.
  - -client는 deprecated → 작은 시스템 (32-bit, 옛 모바일)만.
```

`compilationPolicy.cpp`로 통합 (JDK 16+).

### 5.4 키워드 3 — Graal 옵션 (JDK 11+)

| 연도 | 변화 |
|---|---|
| 2018 | JDK 11+ Graal 옵션 (`-XX:+UseJVMCICompiler`) |
| 2020 | JDK 14+ Compilation Policy 단순화 |
| 2023 | JDK 21+ 동적 임계 조정 정교화 (클라우드 환경) |

Graal:
- C2의 50,000줄 C++ 유지보수 어려움 → Oracle Labs가 Java로 재작성.
- 더 정교한 알고리즘 (Partial Escape Analysis 등).
- GraalVM의 Native Image와 함께 AOT 진영.

### 5.5 역사 타임라인

| 연도 | 릴리스 | 변화 |
|---|---|---|
| 1999 | HotSpot 1.0 | C1 (Client) JIT |
| 2000 | HotSpot 1.3 | C2 (Server) |
| 2007 | JDK 6u20 | **Tiered Compilation 실험** |
| 2014 | JDK 8 | **Tiered 기본 on** |
| 2017 | JDK 9 | TieredThresholdPolicy 정리 |
| 2018 | JDK 11+ | Graal 옵션 |
| 2020 | JDK 14+ | Policy 단순화 |
| 2023 | JDK 21+ | 동적 임계 조정 정교화 |

---

## 6. 면접 답변 워크플로우

### 6.1 질문 → 가지 매핑

| 면접 질문 | 진입 가지 | 인접 확장 |
|---|---|---|
| "Tiered Compilation이 뭔가요?" | ② WHAT | ① WHY로 동기 |
| "왜 5단계로 나뉘었나?" | ① WHY | ② WHAT |
| "Compile Broker 구조" | ③ HOW | ④ 운영 (큐 진단) |
| "CompilerThread가 왜 별도 OS thread?" | ③ HOW | ① WHY (P99 보호) |
| "K8s pod warmup 느림 진단" | ④ 운영 | ③ HOW (CICompilerCount) |
| "동적 임계가 뭔가요?" | ① WHY (부하 적응) | ③ HOW (scale_for_load) |
| "-server/-client는 어떻게 됐나?" | ⑤ 진화 | ② WHAT (Tier 통합) |

### 6.2 답변 템플릿

> 루트 → 가지 키워드 3개 → 인접 가지

예: "Tiered Compilation의 5단계와 Compile Broker 구조를 설명해보세요."

> "Tiered Compilation은 Tier 0(Interpreter) → 3(C1+profile) → 4(C2) 의 5단계 점진 승격 시스템입니다. (← 루트)
> 5단계 정의:
> - **Tier 0**: Interpreter + MDO 수집.
> - **Tier 1, 2**: C1 변형 (rare, fallback).
> - **Tier 3**: C1 with full profiling — Tiered 표준 C1.
> - **Tier 4**: C2 fully optimized — 최종.
> 일반 흐름은 0 → 3 → 4. 1, 2는 C2 큐 적체 등 특수 케이스.
> Compile Broker 구조:
> - C1용 / C2용 분리된 우선순위 큐.
> - CompilerThread 풀 (별도 OS thread, `CICompilerCount`개).
> - TieredThresholdPolicy가 다음 tier 결정 → 큐에 push → CompilerThread가 pickup → 컴파일 → Method._code를 atomic word write로 patch.
> 동적 임계 조정 (`scale_for_load`)이 큐 길이에 따라 임계를 ×2~5 올려 부하에 적응합니다."

---

## 7. 꼬리질문 트리 (가지별)

### Q1 [가지 ②]. Tier 0, 3, 4가 무엇이고 왜 5단계로 나뉘었나요?

> - Tier 0: Interpreter (MDO 수집).
> - Tier 1: C1 without profiling (rare).
> - Tier 2: C1 with limited profiling (rare).
> - Tier 3: C1 with full profiling — Tiered 표준 C1.
> - Tier 4: C2 fully optimized — 최종.
> 일반 운영자는 Tier 0/3/4만 의식. 1/2는 C2 fallback 등 특수 케이스.
> 5단계 이유: C1과 C2 사이에 profile 수집 단계를 두어 C2가 정확한 profile로 컴파일하게 함 → warmup + peak 양립.

**🪝 Q1-1: 항상 0 → 3 → 4 순서인가요?**
> 거의 그렇지만 예외: Trivial getter는 0 → 1 에서 끝. C2 큐 적체 시 0 → 3 → 2 → 4 (Tier 2 우회). C2 컴파일 실패 시 0 → 3에서 stuck. OSR은 동시에 OSR variant도 별도 컴파일.

### Q2 [가지 ③]. Compile Broker가 무엇이고 어떻게 동작하나요?

> JVM의 컴파일 task 관리자.
> 구조: CompileQueue (Tier 분리: C1용/C2용) + CompilerThread 풀 (`CICompilerCount`개 OS thread).
> 흐름:
> 1. TieredThresholdPolicy가 컴파일 필요 결정 → Compile Broker에 task push.
> 2. 우선순위 큐 (호출 빈도 + 예상 이득 + 대기 시간).
> 3. CompilerThread가 큐에서 pickup → C1 또는 C2 컴파일.
> 4. 결과 nmethod를 Code Cache에 설치 → Method._code 필드를 atomic word write로 patch.

**🪝 Q2-1: CompilerThread가 일반 Java thread와 별도여야 하는 이유는?**
> Java thread가 사용자 코드와 컴파일을 함께 하면 응답 시간에 컴파일 시간 포함 → P99 spike. 또는 사용자 코드가 컴파일을 차단 → 데드락 위험. CompilerThread는 별도 OS thread → 사용자 코드는 인터프리터 또는 옛 nmethod로 계속 실행, 백그라운드 컴파일 완료되면 Method._code 갱신 후 다음 호출부터 새 nmethod 사용.

### Q3 [가지 ①]. 동적 임계 조정이 무엇이고 왜 필요한가요?

> Tier 승격 임계가 고정 숫자가 아니라 **CompileQueue 길이에 따라 동적 조정**.
> `scale_for_load()`가 큐 길이 보고 임계를 ×2~5 임시 올림 → 컴파일 요청 줄임 → 큐 안정 → 정말 hot한 메서드만 처리.
> 왜 필요: 트래픽 burst 시 모든 메서드가 동시 임계 도달 → 큐 폭주. 동적 조정 없으면 큐 길어져 warmup 영구 지연. 운영자 관점에서 같은 코드인데 시간대마다 warmup 속도 다른 이유 = 큐 상태.

### Q4 [가지 ④]. Code Cache full이 되면 Tiered 동작이 어떻게 변하나요?

> Compile Broker가 `should_compile_new_jobs() == false` 반환 → 새 task 거부.
> 결과: 새 메서드는 영원히 인터프리터, 이미 컴파일된 메서드는 그대로, Tier 3 → 4 승격도 안 됨. JVM 경고: "CodeCache is full. Compiler has been disabled."
> 회복: `-XX:+UseCodeCacheFlushing` (기본 on) → Sweeper가 cold nmethod 회수. 공간 확보되면 컴파일 재개. 안 되면 JVM 재시작.
> 진단: `jcmd Compiler.codecache | grep stopped`.

### Q5 [가지 ④]. K8s 컨테이너에서 warmup이 평소보다 느릴 때 첫 의심은?

> 4가지 의심 (우선순위 순):
> 1. **CICompilerCount 부족**: cgroup CPU limit 작으면 자동 CICompilerCount=1. `jcmd PerfCounter.print | grep CICompiler` 확인.
> 2. **Code Cache 부족**: Spring Boot 거대 앱은 240MB 부족. `Compiler.codecache` 확인.
> 3. **트래픽 burst**: 동시에 많은 메서드 컴파일 요청 → 큐 적체. `Compiler.queue` 확인.
> 4. **메모리 부족**: cgroup memory limit 작아 GC 빈발 → CompilerThread 영향.

### Q6 [가지 ⑤]. `-XX:TieredStopAtLevel`은 어떤 효과인가요?

> | Level | 동작 |
> |---|---|
> | 1 | C1 (no profile) 까지만. 빠른 startup. 낮은 peak (~50%). |
> | 3 | C1 + profile 까지. C2 안 함. Peak ~70%. |
> | 4 (기본) | C1 + C2 (full). |
> 사용처: 컨테이너 256MB → 1, 컨테이너 512MB + warmup 중요 → 기본 4. Batch (warmup 무시) → `-TieredCompilation` (Tier 0 → 4 직접).

### Q7 (Killer) [가지 ④]. Production에서 같은 코드인데 어떤 인스턴스는 warmup 30초, 어떤 인스턴스는 5분입니다. 차이를 어떻게 진단하시겠어요?

> 환경/부하 차이 분리:
> 1. **자원 상태**: `cat /sys/fs/cgroup/cpu.max`, `memory.max` — 동일 limit인지. K8s VPA가 다르게 할당했을 가능성.
> 2. **CompilerThread 수**: `jcmd PerfCounter.print | grep CICompiler` — 같은가? 다르면 cgroup 인식 문제.
> 3. **컴파일 큐**: `jcmd Compiler.queue` — 한쪽 큐 길고 다른쪽 비어있는지.
> 4. **트래픽 패턴**: 두 pod에 같은 부하 분배인가? Load balancer 확인. Cold cache 차이 (Redis, DB pool)?
> 5. **JFR 시간대별 비교**: `jdk.Compilation`, `jdk.GarbageCollection` 분포.
> 6. **공통 원인 후보**: CPU 모델 차이 (Intel vs AMD), noisy neighbor (CPU throttling), cold storage volume.

---

## 8. 학습 체크리스트

면접 전 백지에서 다음을 다 해낼 수 있어야 마스터:

- [ ] 0장 마인드맵을 종이에 1분 이내로 그릴 수 있다 (루트 + 5가지 + 키워드 3개)
- [ ] 가지 ① WHY: 3가지 이유 (profile-guided, warmup+peak, 부하 적응) 말한다
- [ ] 가지 ② WHAT: Tier 0~4 표 그리고 일반 흐름 (0→3→4) 설명한다
- [ ] 가지 ③ HOW: Compile Broker 구조 그림 (큐 + CompilerThread 풀) 그린다
- [ ] 가지 ③ HOW: Method._code의 atomic patch 안전성 설명한다
- [ ] 가지 ③ HOW: TieredThresholdPolicy의 `scale_for_load` 의사 코드 작성한다
- [ ] 가지 ④ 운영: K8s warmup 느림 4가지 의심 우선순위 말한다
- [ ] 가지 ④ 운영: Code Cache full 시 Tiered 동작 변화 설명한다
- [ ] 가지 ⑤ 진화: -server/-client → Tiered (JDK 8) → Graal 흐름 말한다
- [ ] 7장 꼬리질문 7개에 막힘없이 답한다

---

## 다음 단계

- → [04. C1 and C2](./04-c1-and-c2.md): C1/C2 컴파일러 내부 비교 + IR
- → [05. Inlining and IC](./05-inlining-and-ic.md): Inlining 휴리스틱
- → [08. Speculative and Deopt](./08-speculative-and-deopt.md): Deopt 풀버전
- ← [01. Execution Overview](./01-execution-overview.md): 전체 흐름
- ← [02. Template Interpreter](./02-template-interpreter.md): Tier 0 깊이

## 참고

- **HotSpot src `compileBroker.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/compiler/compileBroker.cpp
- **HotSpot src `compilationPolicy.cpp`**: https://github.com/openjdk/jdk/blob/master/src/hotspot/share/compiler/compilationPolicy.cpp
- **HotSpot src `tieredThresholdPolicy.hpp`** (옛 path): https://github.com/openjdk/jdk/blob/master/src/hotspot/share/compiler/tieredThresholdPolicy.hpp
- **Oracle — Tiered Compilation Notes**: https://docs.oracle.com/en/java/javase/21/vm/java-hotspot-virtual-machine-performance-enhancements.html
- **JITWatch**: https://github.com/AdoptOpenJDK/jitwatch
- **Aleksey Shipilëv — Tier Compilation Internals**: https://shipilev.net/jvm/anatomy-quarks/
