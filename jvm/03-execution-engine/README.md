# 03. Execution Engine — Bytecode를 native code로

> "JVM은 bytecode를 인터프리터로 실행한다" — 이건 **1996년의 답**이다.
> 1999년 HotSpot이 등장한 이후 30년간, **자주 호출되는 메서드는 native machine code로 컴파일되어 실행**된다. 그 컴파일이 **JIT (Just-In-Time)** 이고, JVM의 성능 80%가 여기에 있다.
> 시니어 JVM 엔지니어에게 "JIT는 무엇인가" 라고 물으면, 단일 답은 없다 — HotSpot에는 **두 개의 컴파일러(C1/C2) + Template Interpreter + Tiered Compilation + Sea-of-Nodes + Inline Cache + Escape Analysis + Speculative Optimization + Deoptimization** 이 함께 동작한다. 이 챕터는 그 모든 것을 깊이 파헤친다.

---

## 🗺️ JVM 아키텍처 안에서 이 챕터의 위치

```
┌─────────────────────────────────────────────────────────────────┐
│ ① ClassLoader Subsystem (Chapter 01)                              │
│    .class → InstanceKlass (Metaspace)                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ ② Runtime Data Areas (Chapter 02)                                 │
│    Heap, Metaspace, Stack, PC, Code Cache, Direct Memory          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ ③ Execution Engine ★ 이 챕터 ★                                    │
│    Bytecode → 실행 → native code                                  │
│                                                                   │
│    [Interpreter]  ─────►  [Tiered Compilation]                   │
│       │                       │                                   │
│       │                  ┌────┴────┐                              │
│       │                  ▼          ▼                              │
│       │              [C1 JIT]   [C2 JIT]                          │
│       │                  │          │                              │
│       │                  ▼          ▼                              │
│       └───────────►  Code Cache (Chapter 02-04)                  │
│                                                                   │
│    동시에: Inline Cache, Escape Analysis, Speculative Opt,         │
│            Loop Unrolling, Lock Coarsening, Deoptimization        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ ④ Memory Management (Chapter 04 GC)                                │
└─────────────────────────────────────────────────────────────────┘
```

**이전 챕터와의 연결**:
- ← [Chapter 01](../01-class-lifecycle/): bytecode가 적재된 InstanceKlass가 이 엔진의 입력.
- ← [Chapter 02-04 Code Cache](../02-runtime-data-areas/04-code-cache.md): JIT 결과가 저장되는 곳. 본 챕터에서 컴파일 후 어디 가는지 답이 거기.

**관련 챕터**:
- → Chapter 04 GC: deoptimization이 safepoint에서 일어난다는 점에서 연결.
- → Chapter 05 Threading: Lock 최적화 (Biased/Lightweight/Heavyweight)는 양쪽에서 다룬다 — 본 챕터는 코드 생성 측면, 05는 동시성 의미 측면.
- → Chapter 07 HotSpot Internals: 본 챕터가 C++ 코드를 발췌하지만, 07이 풀버전 소스 투어.

---

## 📍 챕터 학습 목표

이 챕터(8개 sub-chapter)를 마치면 다음을 모두 답할 수 있다.

1. JVM이 한 메서드를 처음 호출하는 순간부터 native code로 컴파일되어 실행되기까지의 전체 흐름을 그릴 수 있다.
2. HotSpot의 **Template Interpreter**가 왜 일반 switch-case 인터프리터보다 2~3배 빠른지, 어떻게 native template을 생성하는지 안다.
3. **Tiered Compilation의 5단계** (Tier 0~4)와 각 tier의 역할, 호출 임계값을 안다.
4. **C1과 C2의 차이** — 어느 IR을 쓰고, 어떤 최적화를 하고, 어느 메서드가 어디로 가는지.
5. **Sea-of-Nodes IR**이 왜 전통적 CFG 기반보다 공격적 최적화에 유리한지 안다.
6. C2의 **phase 순서** (Parse → IterGVN → Loop opts → Macro Expand → CCP → Scheduling → RA → Output)를 안다.
7. **Inlining**이 왜 가장 중요한 최적화인지, MaxInlineSize/FreqInlineSize 옵션의 의미를 안다.
8. **Inline Cache의 4단계** (monomorphic / bimorphic / polymorphic / megamorphic) 진화와 CHA의 관계를 안다.
9. **Escape Analysis**가 무엇이고 scalar replacement, stack allocation, lock elision으로 어떻게 이어지는지 안다.
10. **Loop Unrolling**, **Range Check Elimination**, **SuperWord(SIMD vectorization)** 같은 loop 최적화의 동작 원리를 안다.
11. **Speculative Optimization**과 **Deoptimization**의 메커니즘 — uncommon trap, OSR의 역방향, native frame → interpreter frame 변환.
12. `-XX:+PrintCompilation`, `-XX:+PrintInlining`, `-XX:+PrintAssembly`, JITWatch로 컴파일 활동을 분석할 수 있다.

---

## 📚 Sub-chapter 목록

| # | 파일 | 핵심 질문 | 상태 |
|---|---|---|---|
| 01 | [01-execution-overview.md](./01-execution-overview.md) | Bytecode 한 줄이 native instruction이 되기까지 전체 흐름. Interpreter ↔ JIT switching, OSR. | ✅ |
| 02 | [02-template-interpreter.md](./02-template-interpreter.md) | Template Interpreter 내부 — opcode별 native template, dispatch, MDO. | ✅ |
| 03 | [03-tiered-compilation.md](./03-tiered-compilation.md) | Tier 0~4, Compile Broker, CompilerThread, 호출 임계값. | ✅ |
| 04 | [04-c1-and-c2.md](./04-c1-and-c2.md) | C1 (HIR/LIR) vs C2 (Sea-of-Nodes). 각 phase 순서. | ✅ |
| 05 | [05-inlining-and-ic.md](./05-inlining-and-ic.md) | Inlining 휴리스틱 + Inline Cache 4단계 + CHA. | ✅ |
| 06 | [06-escape-analysis.md](./06-escape-analysis.md) | EA 알고리즘 + Scalar Replacement + Stack Allocation + Lock Elision. | ✅ |
| 07 | [07-loop-and-vector.md](./07-loop-and-vector.md) | Loop Unrolling, RCE, LICM, SuperWord (SIMD). | ✅ |
| 08 | [08-speculative-and-deopt.md](./08-speculative-and-deopt.md) | Speculative opt, Uncommon Trap, Deopt 메커니즘. | ✅ |

---

## 🎯 학습 흐름

```
                  [01. Execution Overview]
                          │
                          ▼
              [02. Template Interpreter]
                          │
                          ▼
              [03. Tiered Compilation]
                          │
                          ▼
                [04. C1 and C2]
                          │
                          ▼
       ┌──────────────────┼──────────────────┐
       ▼                  ▼                  ▼
  [05. Inlining]   [06. Escape Analysis]  [07. Loop & Vector]
       │                  │                  │
       └──────────────────┼──────────────────┘
                          ▼
              [08. Speculative & Deopt]
                          │
                          ▼
                  → Chapter 04 (GC)
                  → Chapter 07 (HotSpot Internals)
```

- 01~04는 **순차 학습** (전체 구조 이해).
- 05~07은 **병렬 가능** (각 최적화는 독립적이지만 서로 연결).
- 08은 **위 모든 것의 운영적 귀결** — 잘못된 speculation의 deopt.

---

## 🔧 사전 학습

- [Chapter 02-04 Code Cache](../02-runtime-data-areas/04-code-cache.md) — JIT 결과가 어디 저장되는지.
- [Chapter 02-06 GC Bookkeeping](../02-runtime-data-areas/06-gc-bookkeeping-and-others.md) — Write Barrier가 JIT 코드에 어떻게 들어가는지.
- [00-overview/02-class-compilation-flow](../00-overview/02-class-compilation-flow.md) — 7-stage 흐름의 ⑥ Bytecode interpretation/JIT.
- [00-overview/02-deep-dive/D opcode-dispatch](../00-overview/02-deep-dive/D-opcode-dispatch.md) — Template Interpreter 부록.

---

## 📏 작성 표준 룰

이 챕터의 모든 sub-chapter는 [`../../AGENTS.md`](../../AGENTS.md) (프로젝트 루트)의 5가지 표준 룰을 따른다:
1. 개념 누락 금지 (본질·왜·연결까지)
2. 시니어 JVM 운영 마스터 관점 (production 진단·해결로 매핑)
3. 표면 디테일(hex/비트/옵션 값) 외우기 제외
4. Excalidraw 다이어그램 필수 (백지 학습 가능)
5. JVM을 백지에서 줄줄 설명할 수 있는 마스터 수준 목표

---

## 📐 7단 레이어 적용 — 이 챕터의 모든 sub-chapter에서

각 sub-chapter는 다음 7단을 거친다:

| 단계 | 내용 |
|---|---|
| 1. 백지 그리기 | 컴파일 phase 또는 최적화 변환을 종이에 그려보기 |
| 2. 직관 | 한 줄 비유 + 정확한 정의 (예: "Inlining = 함수 호출의 인라인 복사") |
| 3. 구조 | bytecode → IR → IR' → machine code의 단계별 변환 |
| 4. 내부 구현 | HotSpot C++ (compile.cpp, escape.cpp 등) 핵심 함수 |
| 5. 역사 | Sun JIT → C1/C2 → Tiered → Graal의 진화 |
| 6. 트레이드오프 | warmup vs peak, throughput vs latency, footprint vs speed |
| 7. 측정·진단 | `-XX:+PrintCompilation`, `-XX:+PrintInlining`, JITWatch, JFR, async-profiler |
| + 꼬리질문 | 면접/실무 시뮬레이션 |

---

## 🏢 운영 관점 — 시니어가 이 챕터에서 얻어야 할 능력

이 챕터의 모든 sub-chapter가 결국 답하려는 운영 질문:

1. **Warmup이 왜 이렇게 오래 걸리는가?**
   → 03, 04 (Tier 승격, C2 컴파일 시간).
2. **P99 latency가 가끔 튀는 이유는?**
   → 08 (Deoptimization), 03 (Tier 승격 중).
3. **메서드를 inline하고 싶은데 왜 안 되는가?**
   → 05 (MaxInlineSize, callee too big, speculation 실패).
4. **Stream/Lambda가 코드 짧은데 왜 느린가?**
   → 05 (메가모르픽 IC), 06 (escape).
5. **synchronized가 왜 빠른가/느린가?**
   → 06 (Lock Elision), 추후 05 챕터 (Mark Word 승격).
6. **VectorAPI를 쓰면 진짜 더 빠른가?**
   → 07 (SuperWord 자동 vs VectorAPI 수동).
7. **JFR/async-profiler의 stack trace가 가끔 "wrong"으로 보이는 이유?**
   → 02 (Template Interpreter의 PC), 08 (deopt 중간 상태).

---

## 🔗 다음 단계

- → [01. Execution Overview](./01-execution-overview.md): 다음 sub-chapter 시작점
- ← [Chapter 02. Runtime Data Areas](../02-runtime-data-areas/): Code Cache가 어디 있는지 알면 들어오기 수월

## 📚 참고

- **HotSpot Glossary**: https://openjdk.org/groups/hotspot/docs/HotSpotGlossary.html
- **Cliff Click — Sea-of-Nodes 원논문 (1995)**: "Combining Analyses, Combining Optimizations"
- **Aleksey Shipilëv — JVM Anatomy Quarks**: https://shipilev.net/jvm/anatomy-quarks/
- **JITWatch (시각화)**: https://github.com/AdoptOpenJDK/jitwatch
- **HotSpot src/hotspot/share/compiler**: https://github.com/openjdk/jdk/tree/master/src/hotspot/share/compiler
- **HotSpot src/hotspot/share/opto** (C2): https://github.com/openjdk/jdk/tree/master/src/hotspot/share/opto
- **HotSpot src/hotspot/share/c1** (C1): https://github.com/openjdk/jdk/tree/master/src/hotspot/share/c1
